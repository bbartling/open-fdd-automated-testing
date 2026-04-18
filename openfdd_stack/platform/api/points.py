"""Points CRUD API \u2014 data model for timeseries references.

Postgres is authoritative; when ``OFDD_STORAGE_BACKEND=selene`` a parallel
``:point`` node is upserted/deleted in SeleneDB after every mutation. Same
best-effort contract as the sites and equipment routers \u2014 sync failures log
with traceback and never fail the CRUD response.
"""

import logging
from uuid import UUID

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import Json

from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.database import get_conn
from openfdd_stack.platform.data_model_ttl import sync_ttl_to_file
from openfdd_stack.platform.api.models import PointCreate, PointRead, PointUpdate
from openfdd_stack.platform.realtime import emit, TOPIC_CRUD_POINT

router = APIRouter(prefix="/points", tags=["points"])
logger = logging.getLogger(__name__)


def _selene_enabled() -> bool:
    return getattr(get_platform_settings(), "storage_backend", "timescale") == "selene"


def _selene_upsert_point(row: dict) -> None:
    """Best-effort mirror of a points row into SeleneDB. Swallows all errors."""
    if not _selene_enabled():
        return
    point_id = row.get("id")
    try:
        from openfdd_stack.platform.selene import (
            make_selene_client_from_settings,
            upsert_point,
        )

        with make_selene_client_from_settings() as client:
            upsert_point(client, dict(row))
    except Exception:  # noqa: BLE001 \u2014 CRUD must succeed regardless
        logger.warning(
            "selene point sync skipped for point_id=%s; Postgres write "
            "remains authoritative.",
            point_id,
            exc_info=True,
        )


def _selene_delete_point(point_id: str) -> None:
    if not _selene_enabled():
        return
    try:
        from openfdd_stack.platform.selene import (
            delete_point,
            make_selene_client_from_settings,
        )

        with make_selene_client_from_settings() as client:
            delete_point(client, point_id)
    except Exception:  # noqa: BLE001
        logger.warning(
            "selene point delete sync skipped for point_id=%s; Postgres "
            "deletion stands.",
            point_id,
            exc_info=True,
        )


_COLS = (
    "id, site_id, external_id, brick_type, fdd_input, unit, description, equipment_id, "
    "bacnet_device_id, object_identifier, object_name, COALESCE(polling, true) AS polling, "
    "modbus_config, created_at"
)


@router.get("", response_model=list[PointRead])
def list_points(
    site_id: UUID | None = None,
    equipment_id: UUID | None = None,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """List points, optionally filtered by site or equipment. Supports limit/offset."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if equipment_id:
                cur.execute(
                    f"""SELECT {_COLS} FROM points WHERE equipment_id = %s ORDER BY external_id LIMIT %s OFFSET %s""",
                    (str(equipment_id), limit, offset),
                )
            elif site_id:
                cur.execute(
                    f"""SELECT {_COLS} FROM points WHERE site_id = %s ORDER BY external_id LIMIT %s OFFSET %s""",
                    (str(site_id), limit, offset),
                )
            else:
                cur.execute(
                    f"""SELECT {_COLS} FROM points ORDER BY site_id, external_id LIMIT %s OFFSET %s""",
                    (limit, offset),
                )
            rows = cur.fetchall()
    return [PointRead.model_validate(dict(r)) for r in rows]


_RETURNS = (
    "RETURNING id, site_id, external_id, brick_type, fdd_input, unit, description, equipment_id, "
    "bacnet_device_id, object_identifier, object_name, COALESCE(polling, true) AS polling, "
    "modbus_config, created_at"
)


@router.post("", response_model=PointRead)
def create_point(body: PointCreate):
    """Create a point. Idempotent: if external_id+site_id exists, returns existing (200)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT {_COLS} FROM points WHERE site_id = %s AND external_id = %s""",
                (str(body.site_id), body.external_id),
            )
            existing = cur.fetchone()
            if existing:
                return PointRead.model_validate(dict(existing))
            polling = body.polling if body.polling is not None else True
            mc = Json(body.modbus_config) if body.modbus_config is not None else None
            try:
                cur.execute(
                    f"""INSERT INTO points (site_id, external_id, brick_type, fdd_input, unit, description, equipment_id, bacnet_device_id, object_identifier, object_name, polling, modbus_config)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       {_RETURNS}""",
                    (
                        str(body.site_id),
                        body.external_id,
                        body.brick_type,
                        body.fdd_input,
                        body.unit,
                        body.description,
                        str(body.equipment_id) if body.equipment_id else None,
                        body.bacnet_device_id,
                        body.object_identifier,
                        body.object_name,
                        polling,
                        mc,
                    ),
                )
                row = cur.fetchone()
            except psycopg2.IntegrityError:
                conn.rollback()
                raise HTTPException(
                    409, "Point with this external_id already exists for this site"
                )
        conn.commit()
    try:
        sync_ttl_to_file()
    except Exception:
        logger.warning("sync_ttl_to_file failed after point create", exc_info=True)
    _selene_upsert_point(dict(row))
    emit(
        TOPIC_CRUD_POINT + ".created",
        {
            "id": str(row["id"]),
            "site_id": str(row["site_id"]),
            "external_id": row["external_id"],
        },
    )
    return PointRead.model_validate(dict(row))


@router.get("/{point_id}", response_model=PointRead)
def get_point(point_id: UUID):
    """Get a point by ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT {_COLS} FROM points WHERE id = %s""",
                (str(point_id),),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Point not found")
    return PointRead.model_validate(dict(row))


@router.patch("/{point_id}", response_model=PointRead)
def update_point(point_id: UUID, body: PointUpdate):
    """Update a point."""
    data = body.model_dump(exclude_unset=True)
    updates, params = [], []
    if "brick_type" in data:
        updates.append("brick_type = %s")
        params.append(data["brick_type"])
    if "fdd_input" in data:
        updates.append("fdd_input = %s")
        params.append(data["fdd_input"])
    if "unit" in data:
        updates.append("unit = %s")
        params.append(data["unit"])
    if "description" in data:
        updates.append("description = %s")
        params.append(data["description"])
    if "equipment_id" in data:
        updates.append("equipment_id = %s")
        params.append(
            str(data["equipment_id"]) if data["equipment_id"] is not None else None
        )
    if "bacnet_device_id" in data:
        updates.append("bacnet_device_id = %s")
        params.append(data["bacnet_device_id"])
    if "object_identifier" in data:
        updates.append("object_identifier = %s")
        params.append(data["object_identifier"])
    if "object_name" in data:
        updates.append("object_name = %s")
        params.append(data["object_name"])
    if "polling" in data:
        updates.append("polling = %s")
        params.append(data["polling"])
    if "modbus_config" in data:
        updates.append("modbus_config = %s")
        mc = data["modbus_config"]
        params.append(Json(mc) if mc is not None else None)
    if not updates:
        return get_point(point_id)
    params.append(str(point_id))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""UPDATE points SET {', '.join(updates)} WHERE id = %s
                    {_RETURNS}""",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(404, "Point not found")
    try:
        sync_ttl_to_file()
    except Exception:
        logger.warning("sync_ttl_to_file failed after point update", exc_info=True)
    _selene_upsert_point(dict(row))
    emit(TOPIC_CRUD_POINT + ".updated", {"id": str(point_id)})
    return PointRead.model_validate(dict(row))


@router.delete("/{point_id}")
def delete_point(point_id: UUID):
    """Delete a point and its timeseries (cascade)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM points WHERE id = %s RETURNING id", (str(point_id),)
            )
            if not cur.fetchone():
                raise HTTPException(404, "Point not found")
        conn.commit()
    try:
        sync_ttl_to_file()
    except Exception:
        logger.warning("sync_ttl_to_file failed after point delete", exc_info=True)
    _selene_delete_point(str(point_id))
    emit(TOPIC_CRUD_POINT + ".deleted", {"id": str(point_id)})
    return {"status": "deleted"}
