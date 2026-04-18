"""Unit tests for CRUD sync helpers in openfdd_stack.platform.selene.graph_crud."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from openfdd_stack.platform.selene import (
    EQUIPMENT_LABEL,
    EXTERNAL_ID_PROP,
    POINT_LABEL,
    SITE_LABEL,
    SeleneClient,
    delete_equipment,
    delete_point,
    delete_site,
    upsert_equipment,
    upsert_point,
    upsert_site,
)


def _mock_client(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# upsert_site
# ---------------------------------------------------------------------------


def test_upsert_site_creates_node_when_absent():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            assert request.url.params["label"] == SITE_LABEL
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 3,
                    "labels": [SITE_LABEL],
                    "properties": captured["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        out = upsert_site(
            client,
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "HQ",
                "description": "Campus HQ",
                "metadata": {"climate_zone": "4A"},
            },
        )

    assert out["id"] == 3
    assert captured["body"]["labels"] == [SITE_LABEL]
    props = captured["body"]["properties"]
    assert props[EXTERNAL_ID_PROP] == "11111111-1111-1111-1111-111111111111"
    # Canonical kebab-lowercase for name; BAS-native label in display_name.
    assert props["name"] == "hq"
    assert props["display_name"] == "HQ"
    assert props["description"] == "Campus HQ"
    # metadata is JSON-serialized for Selene's flat property model
    assert json.loads(props["metadata_json"]) == {"climate_zone": "4A"}


def test_upsert_site_updates_existing_node_matched_by_external_id():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 5,
                            "labels": [SITE_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "11111111-1111-1111-1111-111111111111",
                                "name": "Old name",
                                "description": "To be removed",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "PUT" and request.url.path == "/nodes/5":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": 5,
                    "labels": [SITE_LABEL],
                    "properties": captured["body"]["set_properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        upsert_site(
            client,
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "HQ v2",
                # description omitted — tests stale-key removal
                "metadata": None,
            },
        )

    # Canonical for name, display_name carries the BAS label.
    assert captured["body"]["set_properties"]["name"] == "hq-v2"
    assert captured["body"]["set_properties"]["display_name"] == "HQ v2"
    # description should be removed (not present in new payload)
    assert "description" in captured["body"]["remove_properties"]


def test_upsert_site_ignores_other_sites_when_matching_external_id():
    """Multiple :site nodes may exist; we only touch the one with our external_id."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 1,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "other-site"},
                        },
                        {
                            "id": 2,
                            "labels": [SITE_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "target-site",
                                "name": "Target",
                            },
                        },
                    ],
                    "total": 2,
                },
            )
        assert request.url.path == "/nodes/2", request.url.path
        return httpx.Response(200, json={"id": 2, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "target-site", "name": "New Target"})


def test_upsert_site_warns_on_duplicate_external_id(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 10,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "dup"},
                        },
                        {
                            "id": 11,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "dup"},
                        },
                    ],
                    "total": 2,
                },
            )
        return httpx.Response(200, json={"id": 10, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            upsert_site(client, {"id": "dup", "name": "x"})
    assert any("dup" in rec.message for rec in caplog.records)


def test_upsert_site_returns_none_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            result = upsert_site(client, {"id": "x", "name": "y"})
    assert result is None
    assert any("selene upsert_site failed" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# delete_site
# ---------------------------------------------------------------------------


def test_delete_site_removes_node_when_present():
    saw_delete = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 42,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "gone"},
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "DELETE" and request.url.path == "/nodes/42":
            saw_delete["called"] = True
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        assert delete_site(client, "gone") is True
    assert saw_delete["called"]


def test_delete_site_returns_false_when_node_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nodes": [], "total": 0})

    with _mock_client(handler) as client:
        assert delete_site(client, "not-there") is False


def test_delete_site_returns_false_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            assert delete_site(client, "x") is False
    assert any("selene delete_site failed" in rec.message for rec in caplog.records)


def test_upsert_site_finds_match_beyond_first_page():
    """Portfolios with >100 nodes of a label must still locate the match.

    Regression test for the original single-page query — the target node
    appears on page 2 and we expect a PUT to its id.
    """
    call_log: list[tuple[str, str]] = []
    # Build 100 filler nodes for page 1, then the target at the start of page 2.
    page1 = [
        {
            "id": i,
            "labels": [SITE_LABEL],
            "properties": {EXTERNAL_ID_PROP: f"other-{i}"},
        }
        for i in range(100)
    ]
    page2 = [
        {
            "id": 9001,
            "labels": [SITE_LABEL],
            "properties": {EXTERNAL_ID_PROP: "target", "name": "Target"},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path == "/nodes":
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(200, json={"nodes": page1, "total": 101})
            return httpx.Response(200, json={"nodes": page2, "total": 101})
        assert request.url.path == "/nodes/9001", request.url.path
        return httpx.Response(200, json={"id": 9001, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "target", "name": "New Name"})

    # At least two GET pages were walked.
    get_pages = [c for c in call_log if c[0] == "GET"]
    assert len(get_pages) >= 2


# ---------------------------------------------------------------------------
# upsert_equipment / delete_equipment
# ---------------------------------------------------------------------------


def test_upsert_equipment_serializes_full_row():
    """Equipment carries site_id, equipment_type, feed relationships, metadata."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            assert request.url.params["label"] == EQUIPMENT_LABEL
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 12,
                    "labels": [EQUIPMENT_LABEL],
                    "properties": captured["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        upsert_equipment(
            client,
            {
                "id": "eq-uuid",
                "site_id": "site-uuid",
                "name": "AHU-1",
                "description": "rooftop",
                "equipment_type": "AHU",
                "metadata": {"floor": 3},
                "feeds_equipment_id": "vav-uuid",
                "fed_by_equipment_id": None,
            },
        )

    assert captured["body"]["labels"] == [EQUIPMENT_LABEL]
    props = captured["body"]["properties"]
    assert props[EXTERNAL_ID_PROP] == "eq-uuid"
    assert props["name"] == "ahu-1"  # canonical kebab
    assert props["display_name"] == "AHU-1"  # BAS-native
    assert props["site_external_id"] == "site-uuid"
    assert props["description"] == "rooftop"
    assert props["equipment_type"] == "AHU"
    assert props["feeds_external_id"] == "vav-uuid"
    assert "fed_by_external_id" not in props  # None skipped
    assert json.loads(props["metadata_json"]) == {"floor": 3}


def test_upsert_equipment_omits_optional_fields_when_absent():
    """Minimal equipment row should produce only the required properties."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [EQUIPMENT_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_equipment(
            client,
            {
                "id": "eq-uuid",
                "site_id": "site-uuid",
                "name": "Bare equipment",  # will canonicalise to "bare-equipment"
                "description": None,
                "equipment_type": None,
                "metadata": None,
                "feeds_equipment_id": None,
                "fed_by_equipment_id": None,
            },
        )
    props = captured["body"]["properties"]
    assert props["name"] == "bare-equipment"
    assert props["display_name"] == "Bare equipment"
    assert set(props.keys()) == {
        EXTERNAL_ID_PROP,
        "name",
        "display_name",
        "site_external_id",
    }


def test_upsert_equipment_removes_stale_properties_on_rename():
    """Renaming equipment_type to None after a previous value must drop the property."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 4,
                            "labels": [EQUIPMENT_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "eq-uuid",
                                "site_external_id": "site-uuid",
                                "name": "Old",
                                "equipment_type": "AHU",
                                "description": "was here",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 4, "labels": [EQUIPMENT_LABEL]})

    with _mock_client(handler) as client:
        upsert_equipment(
            client,
            {
                "id": "eq-uuid",
                "site_id": "site-uuid",
                "name": "Renamed",
                "description": None,
                "equipment_type": None,
                "metadata": None,
                "feeds_equipment_id": None,
                "fed_by_equipment_id": None,
            },
        )
    assert captured["body"]["set_properties"]["name"] == "renamed"
    assert captured["body"]["set_properties"]["display_name"] == "Renamed"
    # equipment_type + description should both be scheduled for removal
    assert "equipment_type" in captured["body"]["remove_properties"]
    assert "description" in captured["body"]["remove_properties"]


def test_delete_equipment_removes_node_when_present():
    saw_delete = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 77,
                            "labels": [EQUIPMENT_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "eq-gone"},
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "DELETE" and request.url.path == "/nodes/77":
            saw_delete["called"] = True
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        assert delete_equipment(client, "eq-gone") is True
    assert saw_delete["called"]


def test_delete_equipment_returns_false_when_node_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nodes": [], "total": 0})

    with _mock_client(handler) as client:
        assert delete_equipment(client, "nope") is False


def test_upsert_equipment_returns_none_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            result = upsert_equipment(client, {"id": "x", "site_id": "s", "name": "y"})
    assert result is None
    assert any("selene upsert_equipment" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# upsert_point / delete_point
# ---------------------------------------------------------------------------


def test_upsert_point_serializes_full_row():
    """Point row exercises every optional field: BACnet + semantic + modbus."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.params["label"] == POINT_LABEL
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 22,
                "labels": [POINT_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_point(
            client,
            {
                "id": "point-uuid",
                "site_id": "site-uuid",
                "equipment_id": "equip-uuid",
                "external_id": "AHU_SA_Temp",  # BAS-native handle
                "brick_type": "Supply_Air_Temperature_Sensor",
                "fdd_input": "supply_air_temp",
                "unit": "degF",
                "description": "Supply air temperature sensor",
                "bacnet_device_id": "12345",
                "object_identifier": "analog-input,1",
                "object_name": "AHU1-SA-T",
                "polling": True,
                "modbus_config": {"host": "10.0.0.1", "address": 40001},
            },
        )

    assert captured["body"]["labels"] == [POINT_LABEL]
    props = captured["body"]["properties"]
    assert props[EXTERNAL_ID_PROP] == "point-uuid"
    # name is canonicalized from the BAS-native external_id
    assert props["name"] == "ahu-sa-temp"
    assert props["display_name"] == "AHU_SA_Temp"
    assert props["site_external_id"] == "site-uuid"
    assert props["equipment_external_id"] == "equip-uuid"
    assert props["brick_type"] == "Supply_Air_Temperature_Sensor"
    assert props["fdd_input"] == "supply_air_temp"
    assert props["unit"] == "degF"
    assert props["bacnet_device_id"] == "12345"
    assert props["object_identifier"] == "analog-input,1"
    assert props["polling"] is True
    assert json.loads(props["modbus_config_json"]) == {
        "host": "10.0.0.1",
        "address": 40001,
    }


def test_upsert_point_omits_optional_fields_when_absent():
    """Minimal row (site + external_id + id) produces only required properties."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [POINT_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_point(
            client,
            {
                "id": "p-uuid",
                "site_id": "s-uuid",
                "external_id": "already-canonical",  # no display_name needed
                "brick_type": None,
                "fdd_input": None,
                "unit": None,
                "description": None,
                "equipment_id": None,
                "bacnet_device_id": None,
                "object_identifier": None,
                "object_name": None,
                "polling": True,
                "modbus_config": None,
            },
        )

    props = captured["body"]["properties"]
    # Only the required fields + polling (always written) + site link
    assert set(props.keys()) == {
        EXTERNAL_ID_PROP,
        "name",
        "site_external_id",
        "polling",
    }
    assert props["name"] == "already-canonical"
    assert "display_name" not in props  # BAS handle equals canonical


def test_upsert_point_writes_polling_flag_false():
    """polling=False must be persisted; only None skips the field."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [POINT_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_point(
            client,
            {
                "id": "p",
                "site_id": "s",
                "external_id": "p1",
                "polling": False,
            },
        )

    assert captured["body"]["properties"]["polling"] is False


def test_upsert_point_removes_stale_brick_type_on_rename():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 4,
                            "labels": [POINT_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "p",
                                "name": "sa-temp",
                                "site_external_id": "s",
                                "brick_type": "Old_Class",
                                "fdd_input": "supply_air_temp",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 4, "labels": [POINT_LABEL]})

    with _mock_client(handler) as client:
        upsert_point(
            client,
            {
                "id": "p",
                "site_id": "s",
                "external_id": "sa-temp",
                "brick_type": None,
                "fdd_input": None,
                "polling": True,
            },
        )

    removed = set(captured["body"]["remove_properties"])
    assert "brick_type" in removed
    assert "fdd_input" in removed


def test_delete_point_removes_node_when_present():
    saw_delete = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 99,
                            "labels": [POINT_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "p-gone"},
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "DELETE" and request.url.path == "/nodes/99":
            saw_delete["called"] = True
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        assert delete_point(client, "p-gone") is True
    assert saw_delete["called"]


def test_delete_point_returns_false_when_node_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nodes": [], "total": 0})

    with _mock_client(handler) as client:
        assert delete_point(client, "nope") is False


def test_upsert_point_returns_none_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            result = upsert_point(
                client, {"id": "p", "site_id": "s", "external_id": "x"}
            )
    assert result is None
    assert any("selene upsert_point" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Invariants locked by PR #13 review feedback
# ---------------------------------------------------------------------------


def test_upsert_site_serializes_empty_metadata_as_empty_json():
    """Postgres `metadata jsonb DEFAULT '{}'` must round-trip as metadata_json='{}'.

    Regression guard for the 2.3b refactor \u2014 2.3a did serialize empty dicts so
    downstream Selene consumers could distinguish "metadata configured but
    empty" from "metadata absent".
    """
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [SITE_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "x", "name": "HQ", "metadata": {}})

    assert captured["body"]["properties"]["metadata_json"] == "{}"


def test_upsert_site_skips_metadata_when_none():
    """None (column NULL or absent) must NOT write metadata_json."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [SITE_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "x", "name": "HQ", "metadata": None})

    assert "metadata_json" not in captured["body"]["properties"]


def test_upsert_site_omits_display_name_when_raw_is_already_canonical():
    """When the BAS label is already canonical, no redundant display_name is written."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [SITE_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "x", "name": "hq-north"})

    props = captured["body"]["properties"]
    assert props["name"] == "hq-north"
    assert "display_name" not in props


def test_upsert_site_removes_stale_display_name_when_new_name_is_canonical():
    """Renaming from 'HQ North' to 'hq-north' should drop display_name from the node."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 3,
                            "labels": [SITE_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "x",
                                "name": "hq-north",
                                "display_name": "HQ North",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 3, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "x", "name": "hq-north"})

    assert "display_name" in captured["body"]["remove_properties"]


def test_upsert_enforces_external_id_invariant():
    """Even if a hypothetical caller omits external_id from the properties dict,
    the helper must write it so subsequent lookups by id succeed.

    Guards against future callers (likely copy-paste on new labels) drifting
    the persisted external_id away from the one used to locate the node.
    """
    from openfdd_stack.platform.selene.graph_crud import (
        _upsert_by_external_id,
    )

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": ["widget"],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        # Deliberately omit external_id from the properties dict.
        _upsert_by_external_id(
            client,
            "widget",
            "my-external-id",
            {"name": "only this"},
            op_name="test",
        )

    assert captured["body"]["properties"][EXTERNAL_ID_PROP] == "my-external-id"
