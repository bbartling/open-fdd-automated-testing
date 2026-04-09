# Fake Modbus device for Open-FDD bench

This bench helper was added because the stack had Modbus client/driver/UI/backend support in flight, but no fake Modbus server/device harness comparable to the existing fake BACnet devices.

## What it is

- script: `openclaw/bench/scripts/fake_modbus_device.py`
- dependency profile: **standard library only**
- protocol support: Modbus TCP function codes **3** (holding registers) and **4** (input registers)
- default bind: `127.0.0.1:1502`, `unit_id=1`
- device personality: a small HVAC AHU + power meter profile with dynamic temperatures, schedule, fan status/speed, valve commands, kW, kWh, cost, rate, voltage, current, and alarm code

## Quick start

```powershell
python openclaw/bench/scripts/fake_modbus_device.py --host 127.0.0.1 --port 1502 --unit-id 1
```

Print just the register map:

```powershell
python openclaw/bench/scripts/fake_modbus_device.py --print-map
```

Print sample Open-FDD point payloads:

```powershell
python openclaw/bench/scripts/fake_modbus_device.py --print-sample-points
```

## Suggested Open-FDD bench use

1. Start the fake Modbus device on the same machine as the gateway or on a reachable bench host.
2. In Open-FDD BACnet tools → Modbus tab, test reads against:
   - host: `127.0.0.1`
   - port: `1502`
   - unit id: `1`
3. Add selected points to the data model.
4. Or adapt `openclaw/bench/modbus_fake_device_sample.json` for `PUT /data-model/import`.
5. Enable polling and verify values land in `timeseries_readings` through the shared scrape loop.

## Operator / modeling notes

- The fake device includes a schedule-like point at address `100` named `occupied_schedule`.
- `supply_fan_status` is emitted as `0.0`/`1.0` float32 so rules can use the example threshold `fan_on > 0.01`.
- `Outside_Air_Temperature_Sensor` is present for weather-band style logic (`32°F` to `85°F`).
- A simple energy-cost example is included in the sample JSON:
  - `ahu_energy_kwh * energy_rate_usd_per_kwh`

## Important caveat

This harness proves the **device side** of Modbus TCP benching. End-to-end Open-FDD success still depends on:

- live stack/gateway reachability
- auth/API keys
- BACnet gateway `/modbus/read_registers` implementation
- data-model import and frontend flows
- polling/scrape runtime configuration

So if the fake device responds but Open-FDD still fails, classify carefully:
- fake device responds locally + Open-FDD fails → likely stack/gateway/product or auth/runtime issue
- fake device cannot be reached from the gateway host → network/harness issue
