"""Unit tests for the schema pack loader.

Covers: field descriptor shorthand parsing, parent field flattening,
relationship edge annotations, and dependency-order pack registration.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openfdd_stack.platform.selene.schema_pack import (
    PackLoadError,
    load_pack_file,
    parse_field_descriptor,
    register_pack,
    register_packs_from_dir,
)

# ---------------------------------------------------------------------------
# Field descriptor parser
# ---------------------------------------------------------------------------


def test_parse_required_string():
    assert parse_field_descriptor("string!") == {
        "value_type": "String",
        "required": True,
        "default": None,
    }


def test_parse_optional_string_no_default():
    assert parse_field_descriptor("string") == {
        "value_type": "String",
        "required": False,
        "default": None,
    }


def test_parse_float_with_default():
    assert parse_field_descriptor("float = 72.5") == {
        "value_type": "Float",
        "required": False,
        "default": 72.5,
    }


def test_parse_int_with_default():
    assert parse_field_descriptor("int = 3120") == {
        "value_type": "Integer",
        "required": False,
        "default": 3120,
    }


def test_parse_bool_true_default():
    assert parse_field_descriptor("bool = true") == {
        "value_type": "Boolean",
        "required": False,
        "default": True,
    }


def test_parse_string_with_quoted_default():
    assert parse_field_descriptor("string = 'active'") == {
        "value_type": "String",
        "required": False,
        "default": "active",
    }


def test_parse_string_with_double_quoted_default():
    assert parse_field_descriptor('string = "active"') == {
        "value_type": "String",
        "required": False,
        "default": "active",
    }


def test_unknown_type_raises():
    with pytest.raises(PackLoadError):
        parse_field_descriptor("uuid!")


# ---------------------------------------------------------------------------
# Pack registration
# ---------------------------------------------------------------------------


def _simple_pack() -> dict:
    return {
        "name": "test-pack",
        "types": {
            "protocol_network": {
                "description": "generic network",
                "fields": {"name": "string!", "address": "string"},
            },
            "bacnet_network": {
                "description": "BACnet segment",
                "parent": "protocol_network",
                "fields": {"port": "int = 47808"},
            },
        },
        "relationships": {
            "hasNetwork": {
                "description": "source has a network",
                "source": ["data_source"],
                "target": ["protocol_network"],
                "fields": {"bound_at": "string"},
            }
        },
    }


def test_register_pack_inherits_parent_fields():
    client = MagicMock()
    register_pack(client, _simple_pack(), pack_label="test")

    # bacnet_network should include protocol_network's fields (name, address) + its own (port)
    calls = {c.kwargs["label"]: c for c in client.register_node_schema.call_args_list}
    bacnet_fields = {p["name"]: p for p in calls["bacnet_network"].kwargs["properties"]}
    assert "name" in bacnet_fields
    assert "address" in bacnet_fields
    assert "port" in bacnet_fields
    assert bacnet_fields["port"]["default"] == 47808


def test_register_pack_counts_nodes_and_edges():
    client = MagicMock()
    counts = register_pack(client, _simple_pack(), pack_label="test")
    assert counts == {"nodes_registered": 2, "edges_registered": 1, "failed": 0}


def test_register_pack_propagates_source_target_to_annotations():
    client = MagicMock()
    register_pack(client, _simple_pack(), pack_label="test")

    edge_call = client.register_edge_schema.call_args_list[0]
    assert edge_call.kwargs["label"] == "hasNetwork"
    assert edge_call.kwargs["annotations"] == {
        "source_labels": ["data_source"],
        "target_labels": ["protocol_network"],
    }


def test_register_pack_continues_after_per_type_failure():
    from openfdd_stack.platform.selene.exceptions import SeleneError

    client = MagicMock()
    client.register_node_schema.side_effect = [
        None,  # protocol_network succeeds
        SeleneError("boom"),  # bacnet_network fails
    ]
    counts = register_pack(client, _simple_pack(), pack_label="test")
    # Still tried all types + edges; failure counted.
    assert counts["nodes_registered"] == 1
    assert counts["failed"] == 1
    assert counts["edges_registered"] == 1


def test_inheritance_cycle_detected():
    client = MagicMock()
    pack = {
        "name": "cycle",
        "types": {
            "a": {"parent": "b", "fields": {}},
            "b": {"parent": "a", "fields": {}},
        },
        "relationships": {},
    }
    counts = register_pack(client, pack)
    # Cycle raised per-type; both counted as failed.
    assert counts["failed"] == 2
    assert counts["nodes_registered"] == 0


# ---------------------------------------------------------------------------
# Directory-based registration + order
# ---------------------------------------------------------------------------


def test_load_pack_file_reads_json(tmp_path: Path):
    p = tmp_path / "demo.json"
    p.write_text(json.dumps({"name": "demo", "types": {}, "relationships": {}}))
    assert load_pack_file(p)["name"] == "demo"


def test_register_packs_from_dir_honours_order(tmp_path: Path):
    (tmp_path / "a.json").write_text(
        json.dumps({"name": "a", "types": {}, "relationships": {}})
    )
    (tmp_path / "b.json").write_text(
        json.dumps({"name": "b", "types": {}, "relationships": {}})
    )
    (tmp_path / "c.json").write_text(
        json.dumps({"name": "c", "types": {}, "relationships": {}})
    )

    client = MagicMock()
    results = register_packs_from_dir(client, tmp_path, order=["b", "a"])
    assert list(results.keys()) == ["b", "a", "c"]


def test_register_packs_from_dir_missing_dir(tmp_path: Path):
    client = MagicMock()
    with pytest.raises(PackLoadError):
        register_packs_from_dir(client, tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# Real pinned packs sanity check
# ---------------------------------------------------------------------------


def test_real_hvac_fdd_pack_parses():
    """The pinned selenepack packs must parse without raising."""
    root = Path(__file__).resolve().parents[3]
    pack_dir = root / "config" / "schema_packs"
    if not (pack_dir / "hvac-fdd.json").exists():
        pytest.skip("schema packs not pinned in this checkout")

    client = MagicMock()
    results = register_packs_from_dir(
        client, pack_dir, order=["hvac-fdd", "bacnet-driver"]
    )
    for pack, counts in results.items():
        assert counts["failed"] == 0, f"pack {pack} had failures: {counts}"
        assert counts["nodes_registered"] > 0, f"pack {pack} registered zero types"
