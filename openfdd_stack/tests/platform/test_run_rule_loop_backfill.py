from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from openfdd_stack.platform.config import PlatformSettings
from openfdd_stack.platform.drivers import run_rule_loop


def _settings() -> PlatformSettings:
    return PlatformSettings().model_copy(
        update={
            "open_meteo_enabled": False,
            "fdd_backfill_enabled": True,
            "fdd_backfill_start": "2026-04-01T00:00:00Z",
            "fdd_backfill_end": "2026-04-01T06:00:00Z",
            "fdd_backfill_step_hours": 3,
        }
    )


def _patch_common(monkeypatch, settings: object):
    monkeypatch.setattr(
        run_rule_loop.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(loop=False, verbose=False),
    )
    monkeypatch.setattr(run_rule_loop, "setup_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        run_rule_loop, "_runtime_loop_settings", lambda: (3.0, 10800, 3, "config/.run_fdd_now")
    )
    monkeypatch.setattr(run_rule_loop, "get_platform_settings", lambda: settings)
    monkeypatch.setattr(run_rule_loop, "resolve_site_uuid", lambda *_args, **_kwargs: None)


def test_main_runs_backfill_windows_then_normal_run(monkeypatch):
    settings = _settings()
    calls: list[tuple[datetime | None, datetime | None, int | None]] = []
    saves: list[datetime | None] = []
    _patch_common(monkeypatch, settings)
    monkeypatch.setattr(
        run_rule_loop,
        "_load_backfill_state",
        lambda _k: {
            "state_key": "fdd:global",
            "last_window_end": None,
            "cfg_start": None,
            "cfg_end": None,
        },
    )
    monkeypatch.setattr(
        run_rule_loop,
        "_save_backfill_state",
        lambda _key, last_end, _cfg_start, _cfg_end: saves.append(last_end),
    )
    monkeypatch.setattr(
        run_rule_loop,
        "run_fdd_loop",
        lambda **kwargs: calls.append(
            (kwargs.get("start_ts"), kwargs.get("end_ts"), kwargs.get("lookback_days"))
        )
        or [],
    )

    rc = run_rule_loop.main()

    assert rc == 0
    assert len(calls) == 3  # one-shot mode runs backfill windows then regular run
    assert calls[0][0] == datetime(2026, 4, 1, 0, tzinfo=timezone.utc)
    assert calls[0][1] == datetime(2026, 4, 1, 3, tzinfo=timezone.utc)
    assert calls[1][0] == datetime(2026, 4, 1, 3, tzinfo=timezone.utc)
    assert calls[1][1] == datetime(2026, 4, 1, 6, tzinfo=timezone.utc)
    assert saves and saves[-1] == datetime(2026, 4, 1, 6, tzinfo=timezone.utc)


def test_main_skips_completed_backfill_and_runs_normal(monkeypatch):
    settings = _settings()
    calls: list[tuple[datetime | None, datetime | None, int | None]] = []
    _patch_common(monkeypatch, settings)
    monkeypatch.setattr(
        run_rule_loop,
        "_load_backfill_state",
        lambda _k: {
            "state_key": "fdd:global",
            "last_window_end": datetime(2026, 4, 1, 6, tzinfo=timezone.utc) + timedelta(seconds=1),
            "cfg_start": "2026-04-01T00:00:00+00:00",
            "cfg_end": "2026-04-01T06:00:00+00:00",
        },
    )
    monkeypatch.setattr(run_rule_loop, "_save_backfill_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        run_rule_loop,
        "run_fdd_loop",
        lambda **kwargs: calls.append(
            (kwargs.get("start_ts"), kwargs.get("end_ts"), kwargs.get("lookback_days"))
        )
        or [],
    )

    rc = run_rule_loop.main()

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][0] is None and calls[0][1] is None and calls[0][2] == 3


def test_loop_mode_backfill_failure_continues_with_regular_run(monkeypatch):
    settings = _settings()
    calls: list[tuple[datetime | None, datetime | None, int | None]] = []
    saved_states: list[tuple] = []
    _patch_common(monkeypatch, settings)
    monkeypatch.setattr(
        run_rule_loop.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(loop=True, verbose=False),
    )
    monkeypatch.setattr(
        run_rule_loop,
        "_load_backfill_state",
        lambda _k: {
            "state_key": "fdd:global",
            "last_window_end": None,
            "cfg_start": None,
            "cfg_end": None,
        },
    )
    monkeypatch.setattr(
        run_rule_loop,
        "_save_backfill_state",
        lambda *args, **_kwargs: saved_states.append(args),
    )

    def fake_run_fdd_loop(**kwargs):
        if kwargs.get("start_ts") is not None and kwargs.get("end_ts") is not None:
            raise RuntimeError("backfill-fail")
        calls.append((kwargs.get("start_ts"), kwargs.get("end_ts"), kwargs.get("lookback_days")))
        return []

    monkeypatch.setattr(run_rule_loop, "run_fdd_loop", fake_run_fdd_loop)

    tick = {"count": 0}

    def _stop_after_one_cycle(_seconds):
        tick["count"] += 1
        if tick["count"] >= 1:
            raise RuntimeError("stop-loop")

    monkeypatch.setattr(run_rule_loop.time, "sleep", _stop_after_one_cycle)

    try:
        run_rule_loop.main()
    except RuntimeError as e:
        assert str(e) == "stop-loop"

    # Backfill window failed, but regular lookback run should still happen.
    assert tick["count"] == 1
    assert any(call[2] == 3 and call[0] is None and call[1] is None for call in calls)
    assert saved_states == []
