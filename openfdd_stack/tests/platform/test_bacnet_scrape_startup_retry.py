from unittest.mock import patch

from openfdd_stack.platform.drivers import run_bacnet_scrape as scrape


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


def test_fetch_platform_config_with_startup_retry_recovers():
    log = _DummyLogger()
    calls = {"n": 0}

    def _fake_fetch(_log):
        calls["n"] += 1
        if calls["n"] < 3:
            return None
        return {"bacnet_scrape_interval_min": 5}

    with patch(
        "openfdd_stack.platform.drivers.run_bacnet_scrape._fetch_platform_config",
        side_effect=_fake_fetch,
    ), patch("time.sleep"):
        out = scrape._fetch_platform_config_with_startup_retry(
            log, attempts=5, base_delay_sec=0.01
        )

    assert out == {"bacnet_scrape_interval_min": 5}
    assert calls["n"] == 3


def test_fetch_platform_config_with_startup_retry_exhausts():
    log = _DummyLogger()
    with patch(
        "openfdd_stack.platform.drivers.run_bacnet_scrape._fetch_platform_config",
        return_value=None,
    ), patch("time.sleep") as mocked_sleep:
        out = scrape._fetch_platform_config_with_startup_retry(
            log, attempts=4, base_delay_sec=0.01
        )

    assert out is None
    assert mocked_sleep.call_count == 3


def test_fetch_platform_config_with_startup_retry_succeeds_first_attempt_no_sleep():
    log = _DummyLogger()
    expected = {"bacnet_scrape_interval_min": 5}
    with patch(
        "openfdd_stack.platform.drivers.run_bacnet_scrape._fetch_platform_config",
        return_value=expected,
    ) as mocked_fetch, patch("time.sleep") as mocked_sleep:
        out = scrape._fetch_platform_config_with_startup_retry(
            log, attempts=5, base_delay_sec=0.01
        )
    assert out == expected
    mocked_fetch.assert_called_once()
    mocked_sleep.assert_not_called()

