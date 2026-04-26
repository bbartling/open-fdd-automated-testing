"""CSV upload/validation API."""

from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError

from openfdd_stack.platform.drivers.csv_driver import (
    ingest_csv_dataframe,
    validate_csv_dataframe,
)

router = APIRouter(prefix="/csv", tags=["csv"])
MAX_CSV_UPLOAD_BYTES = 10 * 1024 * 1024


def _safe_source_name(form_source: str | None, file_name: str | None) -> str:
    candidate = (form_source or "").strip()
    if not candidate:
        candidate = Path(file_name or "uploaded").stem
    candidate = re.sub(r"[\x00-\x1f\x7f/:\\\\]+", "_", candidate).strip(" ._-")
    return (candidate[:64] or "uploaded")


class CsvUploadForm(BaseModel):
    site_id: str = Field(..., min_length=1, description="Site name or UUID")
    create_points: bool = Field(
        True, description="When true, upload can auto-create missing CSV points"
    )
    source_name: str | None = Field(
        None, description="Optional source label used for point external_id prefixes"
    )
    dry_run: bool = Field(
        False, description="When true, only validate and return preview metadata"
    )


@router.post("/upload", summary="Upload CSV, validate schema, and ingest")
async def upload_csv(
    file: UploadFile = File(...),
    site_id: str = Form(...),
    create_points: bool = Form(True),
    source_name: str | None = Form(None),
    dry_run: bool = Form(False),
):
    try:
        form = CsvUploadForm(
            site_id=site_id,
            create_points=create_points,
            source_name=source_name,
            dry_run=dry_run,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CSV_FORM_VALIDATION_ERROR",
                "message": "CSV upload form validation failed",
                "details": {"errors": e.errors()},
            },
        ) from e

    if file.size is not None and int(file.size) > MAX_CSV_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CSV file too large (max {MAX_CSV_UPLOAD_BYTES} bytes)",
        )
    raw = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        raw.extend(chunk)
        if len(raw) > MAX_CSV_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"CSV file too large (max {MAX_CSV_UPLOAD_BYTES} bytes)",
            )
    raw_bytes = bytes(raw)
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty")
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="CSV must be UTF-8 encoded",
        ) from None

    try:
        import pandas as pd

        df = await asyncio.to_thread(pd.read_csv, io.StringIO(text))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}") from e

    validation = validate_csv_dataframe(df)
    if validation["errors"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CSV_VALIDATION_ERROR",
                "message": "CSV validation failed",
                "details": {
                    "errors": validation["errors"],
                    "warnings": validation.get("warnings", []),
                    "timestamp_column": validation.get("timestamp_column"),
                },
            },
        )

    preview = {
        "rows_total": int(validation["rows_total"]),
        "rows_with_valid_timestamp": int(validation["rows_with_valid_timestamp"]),
        "timestamp_column": validation.get("timestamp_column"),
        "metric_columns": validation.get("metric_columns", []),
        "warnings": validation.get("warnings", []),
    }
    if form.dry_run:
        return {"ok": True, "validated": True, "preview": preview}

    result = await asyncio.to_thread(
        ingest_csv_dataframe,
        site_id=form.site_id,
        df=df,
        source_name=_safe_source_name(form.source_name, file.filename),
        create_points=form.create_points,
    )
    return {"ok": True, "validated": True, "preview": preview, "ingest": result}
