from openfdd_stack.platform.drivers.open_meteo import (
    WEATHER_EQUIPMENT_NAME,
    WEATHER_EQUIPMENT_TYPE,
    ensure_weather_equipment,
)


def test_ensure_weather_equipment_uses_upsert_on_conflict():
    executed: list[tuple[str, tuple]] = []

    class FakeCursor:
        def execute(self, query, params=None):
            executed.append((query, params or ()))

        def fetchone(self):
            return {"id": "eq-weather"}

    cur = FakeCursor()
    out = ensure_weather_equipment("site-1", cur)
    assert out == "eq-weather"
    assert len(executed) == 1
    insert_sql = executed[0][0]
    assert "ON CONFLICT (site_id, name) DO UPDATE SET" in insert_sql
    assert WEATHER_EQUIPMENT_NAME in executed[0][1]
    assert WEATHER_EQUIPMENT_TYPE in executed[0][1]
