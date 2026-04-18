"""Tests for the canonical-name normaliser.

Mirrors ``selenepack-smartbuildings/src/naming.rs`` one-for-one. When the
upstream spec changes, update both implementations together.
"""

from __future__ import annotations

import pytest

from openfdd_stack.platform.selene import (
    canonical_bas_path,
    canonical_name,
    is_canonical,
)


def test_canonical_flat_equipment_names():
    assert canonical_name("AHU-1") == "ahu-1"
    assert canonical_name("VAV-203") == "vav-203"
    assert canonical_name("CHWP-01") == "chwp-01"
    assert canonical_name("RTU-2") == "rtu-2"
    assert canonical_name("Chiller-1") == "chiller-1"


def test_canonical_zone_and_room_names():
    assert canonical_name("Zone 101") == "zone-101"
    assert canonical_name("Mechanical Room") == "mechanical-room"
    assert canonical_name("Lobby") == "lobby"
    assert canonical_name("Zone  201") == "zone-201"


def test_canonical_floor_and_building_names():
    assert canonical_name("Floor 1") == "floor-1"
    assert canonical_name("Reference Building") == "reference-building"
    assert canonical_name("HQ North") == "hq-north"


def test_canonical_path_names_preserve_slash():
    assert canonical_name("AHU-1/SAT") == "ahu-1/sat"
    assert canonical_name("bldg-a/floor-3/zone-301") == "bldg-a/floor-3/zone-301"


def test_canonical_collapses_internal_runs():
    assert canonical_name("ahu___1") == "ahu-1"
    assert canonical_name("ahu---1") == "ahu-1"
    assert canonical_name("a..b..c") == "a-b-c"
    assert canonical_name("a__-__b") == "a-b"


def test_canonical_strips_whitespace_and_edges():
    assert canonical_name("  ahu-1  ") == "ahu-1"
    assert canonical_name("-ahu-1-") == "ahu-1"
    assert canonical_name("_zone_101_") == "zone-101"


def test_canonical_drops_empty_segments():
    assert canonical_name("ahu-1//sat") == "ahu-1/sat"
    assert canonical_name("/ahu-1/sat/") == "ahu-1/sat"
    assert canonical_name("///") == ""


def test_canonical_drops_non_ascii_silently():
    # en-dash dropped, so AHU1 collapses: AHU + (dropped –) + 1 = AHU1 \u2192 ahu1
    assert canonical_name("AHU\u20131") == "ahu1"
    # \u00f6 dropped, so Z\u00f6ne becomes Zne; space \u2192 -; 101 kept
    assert canonical_name("Z\u00f6ne 101") == "zne-101"


@pytest.mark.parametrize(
    "canonical_input",
    [
        "ahu-1",
        "ahu-1/sat",
        "zone-101",
        "floor-1",
        "mechanical-room",
        "bldg-a/ahu-1/sat",
    ],
)
def test_canonical_idempotent(canonical_input: str):
    """Already-canonical inputs must round-trip, and double-normalisation is stable."""
    assert canonical_name(canonical_input) == canonical_input
    assert canonical_name(canonical_name(canonical_input)) == canonical_input


def test_bas_path_folds_dot_to_slash():
    assert canonical_bas_path("AHU-1.SAT") == "ahu-1/sat"
    assert canonical_bas_path("VAV-203.DMPR") == "vav-203/dmpr"
    assert canonical_bas_path("Bldg-A.AHU-1.SAT") == "bldg-a/ahu-1/sat"
    assert canonical_bas_path("ahu-1/sat") == "ahu-1/sat"


@pytest.mark.parametrize(
    "good",
    [
        "ahu-1",
        "vav-203",
        "zone-101",
        "ahu-1/sat",
        "bldg-a/ahu-1/sat",
        "chwp-01",
    ],
)
def test_is_canonical_positive(good: str):
    assert is_canonical(good), f"should be canonical: {good}"


@pytest.mark.parametrize(
    "bad",
    [
        "AHU-1",
        "ahu 1",
        "ahu_1",
        "ahu-1/",
        "/ahu-1",
        "ahu--1",
        "Zone 101",
        "AHU-1.SAT",
    ],
)
def test_is_canonical_negative(bad: str):
    assert not is_canonical(bad), f"should NOT be canonical: {bad}"


def test_empty_input_yields_empty_string():
    assert canonical_name("") == ""
    assert canonical_name("   ") == ""
    assert canonical_name("---") == ""


def test_live_graph_reference_names_normalise_as_documented():
    """Typical BAS-native names seen in the field."""
    assert canonical_name("AHU-1") == "ahu-1"
    assert canonical_name("Chiller-1") == "chiller-1"
    assert canonical_name("VAV-201") == "vav-201"
    assert canonical_name("Zone 203") == "zone-203"
    assert canonical_name("Mechanical Room") == "mechanical-room"
    assert canonical_name("Floor 2") == "floor-2"
    assert canonical_name("Reference Building") == "reference-building"
    assert canonical_bas_path("AHU-1.SAT") == "ahu-1/sat"
    assert canonical_bas_path("VAV-101.DMPR") == "vav-101/dmpr"
    assert canonical_bas_path("Boiler-1.HWST_SP") == "boiler-1/hwst-sp"
