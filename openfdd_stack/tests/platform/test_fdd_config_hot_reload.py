"""Tests that FDD rule runner uses platform config and loads rules from disk every run (hot reload).

Protects: OpenFDD config (rules_dir, rule_interval_hours, lookback_days), GET /config and
GET /rules parity with the loop, and that run_fdd_loop does not cache rules (edit
YAML and see changes on next run).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openfdd_stack.platform.config import set_config_overlay
from openfdd_stack.platform.drivers.run_rule_loop import _runtime_loop_settings


@pytest.fixture(autouse=True)
def _clear_overlay():
    yield
    set_config_overlay({})


def _mock_conn_no_sites():
    """Context manager yielding a mock DB connection with no sites (so run_fdd_loop does not run rules)."""
    cur = MagicMock()
    cur.execute = MagicMock()
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_run_fdd_loop_loads_rules_from_disk_every_run(tmp_path):
    """run_fdd_loop calls load_rules_from_dir on every run (no cache); path comes from platform config."""
    (tmp_path / "one.yaml").write_text("name: one\ntype: bounds\n")
    set_config_overlay({"rules_dir": str(tmp_path.resolve())})

    load_calls = []

    def record_load(path):
        load_calls.append(Path(path).resolve())
        return []  # no rules so runner gets empty list

    with patch("openfdd_stack.platform.loop.get_conn", return_value=_mock_conn_no_sites()):
        with patch(
            "open_fdd.engine.runner.load_rules_from_dir", side_effect=record_load
        ):
            from openfdd_stack.platform.loop import run_fdd_loop

            run_fdd_loop()
            run_fdd_loop()
    assert (
        len(load_calls) == 2
    ), "load_rules_from_dir must be called every run (hot reload)"
    assert load_calls[0] == load_calls[1] == tmp_path.resolve()
    assert load_calls[0].name == tmp_path.name


def test_run_fdd_loop_uses_rules_dir_from_settings(tmp_path):
    """run_fdd_loop uses rules_dir from get_platform_settings() when not overridden."""
    (tmp_path / "x.yaml").write_text("name: x\n")
    set_config_overlay({"rules_dir": str(tmp_path.resolve())})

    with patch("openfdd_stack.platform.loop.get_conn", return_value=_mock_conn_no_sites()):
        with patch("open_fdd.engine.runner.load_rules_from_dir") as m:
            m.return_value = []
            from openfdd_stack.platform.loop import run_fdd_loop

            run_fdd_loop()
    m.assert_called_once()
    (call_path,) = m.call_args[0]
    assert Path(call_path).resolve() == tmp_path.resolve()


def test_rules_api_and_loop_resolve_same_path_for_relative_rules_dir():
    """API _rules_dir_resolved() and run_fdd_loop use the same repo-relative path for rules_dir."""
    set_config_overlay({"rules_dir": "stack/rules"})

    from openfdd_stack.platform import loop as loop_mod
    from openfdd_stack.platform.api import rules as rules_mod

    # Loop: repo_root from loop.py (open_fdd/platform/loop.py -> parent.parent.parent)
    loop_repo_root = Path(loop_mod.__file__).resolve().parent.parent.parent
    expected = (loop_repo_root / "stack" / "rules").resolve()

    api_resolved = rules_mod._rules_dir_resolved()
    assert (
        api_resolved == expected
    ), "GET /rules and FDD loop must resolve the same rules dir (API uses same repo_root logic)"


def test_runtime_loop_settings_reads_overlay_values():
    """Loop scheduling values come from current platform config (no restart required)."""
    with patch(
        "openfdd_stack.platform.drivers.run_rule_loop.load_from_file"
    ) as _load, patch(
        "openfdd_stack.platform.drivers.run_rule_loop.get_config_from_graph"
    ) as _cfg:
        _cfg.return_value = {
            "rule_interval_hours": 0.0,
            "lookback_days": 7,
            "fdd_trigger_file": "config/custom.trigger",
        }
        interval, sleep_sec, lookback, trigger = _runtime_loop_settings()
    assert interval == 0.0
    assert sleep_sec == 60  # floor to 60s for safety, even when interval is 0.0
    assert lookback == 7
    assert trigger == "config/custom.trigger"


def test_runtime_loop_settings_picks_up_config_changes_between_calls():
    """Subsequent calls observe updated /config overlay values."""
    with patch(
        "openfdd_stack.platform.drivers.run_rule_loop.load_from_file"
    ) as _load, patch(
        "openfdd_stack.platform.drivers.run_rule_loop.get_config_from_graph"
    ) as _cfg:
        _cfg.side_effect = [
            {"rule_interval_hours": 3.0, "lookback_days": 3},
            {"rule_interval_hours": 0.5, "lookback_days": 1},
        ]
        first = _runtime_loop_settings()
        second = _runtime_loop_settings()

    assert first[0] == 3.0
    assert first[1] == 10800
    assert first[2] == 3
    assert second[0] == 0.5
    assert second[1] == 1800
    assert second[2] == 1


def test_run_fdd_loop_honors_equipment_types_plural_and_hot_reload(tmp_path):
    """
    Regression: rules may declare `equipment_types` (plural). Ensure run_fdd_loop
    filters correctly and picks up create/delete edits each run.
    """
    set_config_overlay({"rules_dir": str(tmp_path.resolve())})
    ttl_path = tmp_path / "data_model.ttl"
    ttl_path.write_text(
        "@prefix ofdd: <http://openfdd.local/ontology#> .\n",
        encoding="utf-8",
    )

    load_return_sequence = [
        [{"name": "meter_rule", "flag": "meter_flag", "equipment_types": ["Electric_Meter"]}],
        [
            {"name": "meter_rule", "flag": "meter_flag", "equipment_types": ["Electric_Meter"]},
            {"name": "ahu_rule", "flag": "ahu_flag", "equipment_types": ["AHU"]},
        ],
        [{"name": "ahu_rule", "flag": "ahu_flag", "equipment_types": ["AHU"]}],
    ]
    seen_runner_rules: list[list[str]] = []

    class _FakeRunner:
        def __init__(self, rules):
            seen_runner_rules.append([r.get("flag", "") for r in rules if isinstance(r, dict)])

        def run(self, *_args, **_kwargs):
            return []

    with (
        patch("openfdd_stack.platform.loop.get_conn", return_value=_mock_conn_no_sites()),
        patch(
            "open_fdd.engine.runner.load_rules_from_dir",
            side_effect=load_return_sequence,
        ),
        patch("open_fdd.engine.runner.RuleRunner", side_effect=_FakeRunner),
        patch(
            "openfdd_stack.platform.brick_ttl_resolver.get_equipment_types_from_ttl",
            return_value=["Electric_Meter"],
        ),
        patch(
            "openfdd_stack.platform.brick_ttl_resolver.BrickTtlColumnMapResolver.build_column_map",
            return_value={},
        ),
        patch("openfdd_stack.platform.loop._sync_fault_definitions_from_rules", lambda _r: None),
        patch("openfdd_stack.platform.loop.get_ttl_path_resolved", return_value=str(ttl_path)),
    ):
        from openfdd_stack.platform.loop import run_fdd_loop

        run_fdd_loop()
        run_fdd_loop()
        run_fdd_loop()

    assert seen_runner_rules == [
        ["meter_flag"],  # first run: meter rule only
        ["meter_flag"],  # second run: ahu rule created, but filtered out
        [],  # third run: meter rule deleted, no applicable rules left
    ]
