"""SeleneDB schema pack loader.

Reads JSON packs pinned under ``config/schema_packs/`` (selenepack-smartbuildings
format) and registers each type + relationship with SeleneDB via the HTTP
``/schemas/nodes`` and ``/schemas/edges`` endpoints.

Field descriptor shorthand (from the pack JSON) is parsed here:

    "string!"              -> required string
    "string = 'default'"   -> optional string, default 'default'
    "int = 5"              -> optional int, default 5
    "float = 0.0"          -> optional float, default 0.0
    "bool = true"          -> optional bool, default True
    "bool"                 -> optional bool, no default

Child types carrying ``"parent": "<label>"`` inherit the parent's fields —
the loader flattens them before registering, because the HTTP
``/schemas/nodes`` surface doesn't model inheritance (only the internal
schema engine does).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import SeleneError

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    "string": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
    "timestamp": "Timestamp",
    "bytes": "Bytes",
    "list": "String",  # lists stored as JSON strings per SeleneDB property convention
    "any": "String",
}

# "int = 5" / "string = 'foo'" / "bool = true"
_FIELD_WITH_DEFAULT = re.compile(r"^\s*(?P<type>\w+)\s*=\s*(?P<default>.+?)\s*$")


class PackLoadError(SeleneError):
    """Pack JSON is malformed or a type referenced a missing parent."""


def parse_field_descriptor(desc: str) -> dict[str, Any]:
    """Parse a shorthand field descriptor into a Selene property dict.

    >>> parse_field_descriptor("string!")
    {'value_type': 'String', 'required': True, 'default': None}
    >>> parse_field_descriptor("float = 72.5")
    {'value_type': 'Float', 'required': False, 'default': 72.5}
    >>> parse_field_descriptor("bool")
    {'value_type': 'Boolean', 'required': False, 'default': None}
    """
    descriptor = desc.strip()
    required = descriptor.endswith("!")
    if required:
        descriptor = descriptor[:-1].strip()

    default: Any = None
    match = _FIELD_WITH_DEFAULT.match(descriptor)
    if match:
        py_type = match.group("type").strip().lower()
        default = _parse_literal(match.group("default"), py_type)
    else:
        py_type = descriptor.strip().lower()

    if py_type not in _TYPE_MAP:
        raise PackLoadError(f"unknown field type {py_type!r} in descriptor {desc!r}")

    return {
        "value_type": _TYPE_MAP[py_type],
        "required": required,
        "default": default,
    }


def _parse_literal(raw: str, py_type: str) -> Any:
    """Parse the RHS of a field-with-default descriptor into a Python value."""
    raw = raw.strip()
    if py_type == "string":
        # Strip quotes (single or double)
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            return raw[1:-1]
        return raw
    if py_type == "int":
        return int(raw)
    if py_type == "float":
        return float(raw)
    if py_type == "bool":
        low = raw.lower()
        if low in ("true", "false"):
            return low == "true"
        raise PackLoadError(f"invalid boolean literal {raw!r}")
    # timestamp/bytes/list/any: store raw
    return raw


def _flatten_fields(
    type_name: str,
    type_def: dict[str, Any],
    all_types: dict[str, dict[str, Any]],
    _seen: set[str] | None = None,
) -> dict[str, str]:
    """Return merged fields (parent chain + own), child overrides parent."""
    seen = _seen if _seen is not None else set()
    if type_name in seen:
        raise PackLoadError(f"inheritance cycle detected at {type_name!r}")
    seen.add(type_name)

    parent_name = type_def.get("parent")
    merged: dict[str, str] = {}
    if parent_name:
        parent_def = all_types.get(parent_name)
        if parent_def is None:
            # Cross-pack parent (e.g. depends_on common) — skip silently; the
            # parent type is expected to already exist in SeleneDB.
            logger.debug(
                "type %s parent %s not in local pack; assuming registered",
                type_name,
                parent_name,
            )
        else:
            merged.update(_flatten_fields(parent_name, parent_def, all_types, seen))
    merged.update(type_def.get("fields", {}))
    return merged


def _type_to_properties(
    type_name: str,
    type_def: dict[str, Any],
    all_types: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    for field_name, descriptor in _flatten_fields(
        type_name, type_def, all_types
    ).items():
        parsed = parse_field_descriptor(descriptor)
        props.append(
            {
                "name": field_name,
                **parsed,
                "description": "",
                "indexed": False,
            }
        )
    return props


def load_pack_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise PackLoadError(f"failed to read pack {path}: {exc}") from exc


def register_pack(
    client: SeleneClient,
    pack: dict[str, Any],
    *,
    pack_label: str | None = None,
) -> dict[str, int]:
    """Register every type + relationship in ``pack`` with the server.

    Returns a counts dict. Errors on individual types are logged and counted
    under ``failed``; the caller decides whether to abort boot. The HTTP
    surface is idempotent (re-registration replaces), so running this on a
    healthy server repeatedly is safe.
    """
    name = pack_label or pack.get("name", "<unnamed>")
    types = pack.get("types", {}) or {}
    relationships = pack.get("relationships", {}) or {}

    counts = {"nodes_registered": 0, "edges_registered": 0, "failed": 0}

    for type_name, type_def in types.items():
        try:
            properties = _type_to_properties(type_name, type_def, types)
            client.register_node_schema(
                label=type_name,
                properties=properties,
                description=type_def.get("description", ""),
            )
            counts["nodes_registered"] += 1
            logger.info("pack %s: registered node schema %s", name, type_name)
        except SeleneError as exc:
            counts["failed"] += 1
            logger.warning(
                "pack %s: failed to register node schema %s: %s",
                name,
                type_name,
                exc,
            )

    for rel_name, rel_def in relationships.items():
        try:
            edge_fields = rel_def.get("fields", {}) or {}
            properties = [
                {
                    "name": fn,
                    **parse_field_descriptor(d),
                    "description": "",
                    "indexed": False,
                }
                for fn, d in edge_fields.items()
            ]
            annotations: dict[str, Any] = {}
            if rel_def.get("source"):
                annotations["source_labels"] = rel_def["source"]
            if rel_def.get("target"):
                annotations["target_labels"] = rel_def["target"]
            client.register_edge_schema(
                label=rel_name,
                properties=properties,
                description=rel_def.get("description", ""),
                annotations=annotations or None,
            )
            counts["edges_registered"] += 1
            logger.info("pack %s: registered edge schema %s", name, rel_name)
        except SeleneError as exc:
            counts["failed"] += 1
            logger.warning(
                "pack %s: failed to register edge schema %s: %s",
                name,
                rel_name,
                exc,
            )

    return counts


def register_packs_from_dir(
    client: SeleneClient,
    pack_dir: Path,
    *,
    order: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """Register every ``*.json`` pack under ``pack_dir``.

    ``order`` is a list of pack filenames (without extension) controlling
    registration order for dependency resolution. Packs not listed run last
    in sorted alphabetical order (``sorted(pack_dir.glob('*.json'))``).
    """
    if not pack_dir.is_dir():
        raise PackLoadError(f"schema pack dir {pack_dir} not found")

    all_packs = sorted(pack_dir.glob("*.json"))
    ordered: list[Path] = []
    if order:
        by_stem = {p.stem: p for p in all_packs}
        for name in order:
            if name in by_stem:
                ordered.append(by_stem.pop(name))
        ordered.extend(by_stem.values())
    else:
        ordered = all_packs

    results: dict[str, dict[str, int]] = {}
    for path in ordered:
        pack = load_pack_file(path)
        results[path.stem] = register_pack(client, pack, pack_label=path.stem)
    return results
