#!/usr/bin/env python3
"""
Fake Modbus TCP device for Open-FDD bench testing.

Purpose
-------
Provide a small but realistic HVAC + power-meter style Modbus device that can be
used with the Open-FDD stack's Modbus TCP feature work.

Design goals
------------
- standard-library only (no pymodbus dependency required)
- supports function codes 3 and 4 (holding/input register reads)
- serves realistic HVAC-ish and utility-ish signals
- values drift over time so repeated scrapes look alive
- exposes a stable register map suitable for Open-FDD point modeling/import

Example
-------
  python scripts/fake_modbus_device.py --host 127.0.0.1 --port 1502 --unit-id 1

Then point Open-FDD Modbus config at host=127.0.0.1, port=1502, unit_id=1.
"""

from __future__ import annotations

import argparse
import math
import signal
import socket
import socketserver
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable


def _u16(v: int) -> int:
    return int(v) & 0xFFFF


def _i16_words(v: int) -> list[int]:
    return [_u16(v)]


def _u16_words(v: int) -> list[int]:
    return [_u16(v)]


def _u32_words(v: int) -> list[int]:
    raw = int(v) & 0xFFFFFFFF
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


def _f32_words(v: float) -> list[int]:
    raw = struct.unpack(">I", struct.pack(">f", float(v)))[0]
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


@dataclass(frozen=True)
class RegisterDef:
    address: int
    function: str  # "holding" or "input"
    words_fn: Callable[[float], list[int]]
    value_fn: Callable[[float], float | int]
    point_name: str
    unit: str
    brick_type: str
    fdd_input: str
    description: str
    decode: str
    count: int

    def words(self, t: float) -> list[int]:
        return self.words_fn(self.value_fn(t))


class FakeBenchProfile:
    """Small pretend building profile with dynamic HVAC and energy signals."""

    def __init__(self) -> None:
        self.start = time.time()
        self._defs = self._build_defs()
        self._holding = {d.address: d for d in self._defs if d.function == "holding"}
        self._input = {d.address: d for d in self._defs if d.function == "input"}

    @property
    def defs(self) -> list[RegisterDef]:
        return list(self._defs)

    def _elapsed(self) -> float:
        return time.time() - self.start

    def _build_defs(self) -> list[RegisterDef]:
        return [
            RegisterDef(0, "holding", _f32_words, self.outside_air_temp_f, "Outside Air Temp", "degF", "Outside_Air_Temperature_Sensor", "outside_air_temperature_sensor", "Outdoor air temperature", "float32", 2),
            RegisterDef(2, "holding", _f32_words, self.return_air_temp_f, "Return Air Temp", "degF", "Return_Air_Temperature_Sensor", "return_air_temperature_sensor", "Return air temperature", "float32", 2),
            RegisterDef(4, "holding", _f32_words, self.mixed_air_temp_f, "Mixed Air Temp", "degF", "Mixed_Air_Temperature_Sensor", "mixed_air_temperature_sensor", "Mixed air temperature", "float32", 2),
            RegisterDef(6, "holding", _f32_words, self.supply_air_temp_f, "Supply Air Temp", "degF", "Supply_Air_Temperature_Sensor", "supply_air_temperature_sensor", "Supply air temperature", "float32", 2),
            RegisterDef(8, "holding", _f32_words, self.zone_air_temp_f, "Zone Air Temp", "degF", "Zone_Air_Temperature_Sensor", "zone_air_temperature_sensor", "Representative zone temperature", "float32", 2),
            RegisterDef(10, "holding", _f32_words, self.supply_fan_status, "Supply Fan Status", "bool-ish", "Fan_Status", "supply_fan_status", "0.0=off, 1.0=on", "float32", 2),
            RegisterDef(12, "holding", _f32_words, self.supply_fan_speed_pct, "Supply Fan Speed", "%", "Speed_Sensor", "supply_fan_speed_pct", "Supply fan speed percent", "float32", 2),
            RegisterDef(14, "holding", _f32_words, self.cooling_valve_pct, "Cooling Valve Cmd", "%", "Valve_Command", "cooling_valve_cmd_pct", "Cooling valve command percent", "float32", 2),
            RegisterDef(16, "holding", _f32_words, self.heating_valve_pct, "Heating Valve Cmd", "%", "Valve_Command", "heating_valve_cmd_pct", "Heating valve command percent", "float32", 2),
            RegisterDef(18, "holding", _f32_words, self.discharge_static_inwg, "Discharge Static", "in.wg", "Pressure_Sensor", "discharge_static_pressure_sensor", "Discharge static pressure", "float32", 2),
            RegisterDef(20, "holding", _f32_words, self.electrical_kw, "AHU Electric Power", "kW", "Power_Sensor", "ahu_power_kw", "AHU electrical demand", "float32", 2),
            RegisterDef(22, "holding", _f32_words, self.electrical_kwh, "AHU Electric Energy", "kWh", "Energy_Sensor", "ahu_energy_kwh", "Accumulated AHU energy", "float32", 2),
            RegisterDef(24, "holding", _f32_words, self.energy_cost_usd, "Energy Cost", "USD", "Cost_Sensor", "energy_cost_usd", "Accumulated energy cost", "float32", 2),
            RegisterDef(26, "holding", _f32_words, self.real_power_factor, "Power Factor", "ratio", "Power_Factor_Sensor", "power_factor", "Real power factor", "float32", 2),
            RegisterDef(28, "holding", _f32_words, self.line_voltage_v, "Line Voltage", "V", "Voltage_Sensor", "line_voltage_v", "Line voltage", "float32", 2),
            RegisterDef(30, "holding", _f32_words, self.line_current_a, "Line Current", "A", "Current_Sensor", "line_current_a", "Line current", "float32", 2),
            RegisterDef(32, "holding", _u32_words, self.runtime_seconds, "Supply Fan Runtime", "s", "Runtime_Sensor", "supply_fan_runtime_seconds", "Accumulated fan runtime", "uint32", 2),
            RegisterDef(34, "holding", _i16_words, self.alarm_code, "Alarm Code", "code", "Alarm_State", "alarm_code", "0 normal; 2 low SAT; 5 high OAT economizer stress", "int16", 1),
            RegisterDef(100, "input", _f32_words, self.schedule_enable, "Occupied Schedule", "bool-ish", "Schedule_Status", "occupied_schedule", "1.0 occupied weekdays 8-17, else 0.0", "float32", 2),
            RegisterDef(102, "input", _f32_words, self.outside_air_damper_pct, "OA Damper Cmd", "%", "Damper_Command", "outside_air_damper_cmd_pct", "Outside air damper command percent", "float32", 2),
            RegisterDef(104, "input", _f32_words, self.return_fan_speed_pct, "Return Fan Speed", "%", "Speed_Sensor", "return_fan_speed_pct", "Return fan speed percent", "float32", 2),
            RegisterDef(106, "input", _f32_words, self.rate_usd_per_kwh, "Energy Rate", "USD/kWh", "Price_Sensor", "energy_rate_usd_per_kwh", "Blended electric rate", "float32", 2),
        ]

    # --- behavior model ---
    def _day_fraction(self, t: float) -> float:
        return (t / 240.0) % 1.0

    def _weekday_index(self, t: float) -> int:
        return int((t / 240.0) // 1) % 7

    def _hour_of_day(self, t: float) -> float:
        return (self._day_fraction(t) * 24.0)

    def _occupied(self, t: float) -> bool:
        day = self._weekday_index(t)
        hour = self._hour_of_day(t)
        return day in [0, 1, 2, 3, 4] and 8.0 <= hour < 17.0

    def _weather_band(self, t: float) -> bool:
        oat = self.outside_air_temp_f(t)
        return 32.0 <= oat <= 85.0

    def outside_air_temp_f(self, t: float) -> float:
        base = 58.0 + 24.0 * math.sin((2.0 * math.pi * t) / 240.0)
        noise = 1.2 * math.sin((2.0 * math.pi * t) / 27.0)
        return round(base + noise, 2)

    def return_air_temp_f(self, t: float) -> float:
        return round(73.5 + 1.8 * math.sin((2.0 * math.pi * t) / 90.0), 2)

    def mixed_air_temp_f(self, t: float) -> float:
        oat = self.outside_air_temp_f(t)
        rat = self.return_air_temp_f(t)
        oa_frac = self.outside_air_damper_pct(t) / 100.0
        return round((oa_frac * oat) + ((1.0 - oa_frac) * rat), 2)

    def supply_air_temp_f(self, t: float) -> float:
        occupied = self._occupied(t)
        oat = self.outside_air_temp_f(t)
        sat = 55.0 if occupied else 62.0
        if oat > 85.0 and occupied:
            sat += 1.4
        if 32.0 > oat and occupied:
            sat -= 1.1
        sat += 0.5 * math.sin((2.0 * math.pi * t) / 41.0)
        return round(sat, 2)

    def zone_air_temp_f(self, t: float) -> float:
        occupied = self._occupied(t)
        target = 72.0 if occupied else 76.0
        drift = 1.4 * math.sin((2.0 * math.pi * t) / 75.0)
        return round(target + drift, 2)

    def schedule_enable(self, t: float) -> float:
        return 1.0 if self._occupied(t) else 0.0

    def supply_fan_status(self, t: float) -> float:
        return 1.0 if self._occupied(t) else 0.0

    def supply_fan_speed_pct(self, t: float) -> float:
        if not self._occupied(t):
            return 0.0
        spd = 62.0 + 9.0 * math.sin((2.0 * math.pi * t) / 53.0)
        return round(max(35.0, min(95.0, spd)), 2)

    def return_fan_speed_pct(self, t: float) -> float:
        if not self._occupied(t):
            return 0.0
        return round(max(30.0, self.supply_fan_speed_pct(t) - 7.0), 2)

    def cooling_valve_pct(self, t: float) -> float:
        if not self._occupied(t):
            return 0.0
        oat = self.outside_air_temp_f(t)
        val = max(0.0, min(100.0, (oat - 55.0) * 2.6))
        return round(val, 2)

    def heating_valve_pct(self, t: float) -> float:
        if not self._occupied(t):
            return 0.0
        oat = self.outside_air_temp_f(t)
        val = max(0.0, min(100.0, (50.0 - oat) * 2.7))
        return round(val, 2)

    def outside_air_damper_pct(self, t: float) -> float:
        occupied = self._occupied(t)
        if not occupied:
            return 10.0
        if self._weather_band(t):
            return round(35.0 + 20.0 * math.sin((2.0 * math.pi * t) / 67.0), 2)
        return 15.0

    def discharge_static_inwg(self, t: float) -> float:
        if not self._occupied(t):
            return 0.08
        return round(1.72 + 0.12 * math.sin((2.0 * math.pi * t) / 48.0), 3)

    def electrical_kw(self, t: float) -> float:
        fan = self.supply_fan_speed_pct(t) / 100.0
        cool = self.cooling_valve_pct(t) / 100.0
        heat = self.heating_valve_pct(t) / 100.0
        kw = (2.2 + 9.5 * fan**2.4 + 2.8 * cool + 1.6 * heat) if self._occupied(t) else 0.35
        return round(kw, 3)

    def electrical_kwh(self, t: float) -> float:
        elapsed_h = max(0.0, t / 3600.0)
        avg_kw = 4.8 if self._occupied(t) else 1.4
        return round(elapsed_h * avg_kw, 3)

    def rate_usd_per_kwh(self, t: float) -> float:
        hr = self._hour_of_day(t)
        if 13.0 <= hr < 18.0:
            return 0.18
        if 8.0 <= hr < 13.0:
            return 0.14
        return 0.09

    def energy_cost_usd(self, t: float) -> float:
        return round(self.electrical_kwh(t) * self.rate_usd_per_kwh(t), 3)

    def real_power_factor(self, t: float) -> float:
        return round(0.94 - 0.03 * abs(math.sin((2.0 * math.pi * t) / 120.0)), 3)

    def line_voltage_v(self, t: float) -> float:
        return round(480.0 + 4.5 * math.sin((2.0 * math.pi * t) / 38.0), 2)

    def line_current_a(self, t: float) -> float:
        kw = self.electrical_kw(t)
        return round((kw * 1000.0) / max(1.0, self.line_voltage_v(t) * 1.732 * self.real_power_factor(t)), 2)

    def runtime_seconds(self, t: float) -> int:
        return max(0, int(t * 0.72 if self._occupied(t) else t * 0.18))

    def alarm_code(self, t: float) -> int:
        oat = self.outside_air_temp_f(t)
        sat = self.supply_air_temp_f(t)
        if self._occupied(t) and sat < 53.5:
            return 2
        if self._occupied(t) and oat > 88.0:
            return 5
        return 0

    def read_words(self, function_code: int, address: int, count: int) -> list[int] | None:
        bank = self._holding if function_code == 3 else self._input if function_code == 4 else None
        if bank is None:
            return None
        t = self._elapsed()
        words: list[int] = []
        cursor = address
        remaining = count
        while remaining > 0:
            reg = bank.get(cursor)
            if reg is None:
                return None
            reg_words = reg.words(t)
            if len(reg_words) > remaining:
                return None
            words.extend(reg_words)
            cursor += len(reg_words)
            remaining -= len(reg_words)
        return words

    def register_table_markdown(self) -> str:
        lines = [
            "| Function | Address | Count | Decode | Point | fdd_input | Brick type | Unit | Description |",
            "|---|---:|---:|---|---|---|---|---|---|",
        ]
        for d in self._defs:
            lines.append(
                f"| {d.function} | {d.address} | {d.count} | {d.decode} | {d.point_name} | {d.fdd_input} | {d.brick_type} | {d.unit} | {d.description} |"
            )
        return "\n".join(lines)


class ModbusTCPHandler(socketserver.BaseRequestHandler):
    profile: FakeBenchProfile
    unit_id: int

    def handle(self) -> None:
        while True:
            header = self._recv_exact(7)
            if not header:
                return
            tx_id, proto_id, length, unit_id = struct.unpack(">HHHB", header)
            # MBAP length = unit id (1) + PDU; Modbus TCP PDU is capped (reject fuzzed huge reads).
            if proto_id != 0 or length < 2 or length > 254:
                return
            pdu = self._recv_exact(length - 1)
            if not pdu:
                return
            if unit_id != self.unit_id:
                self._send_exception(tx_id, unit_id, pdu[0], 11)
                continue
            func = pdu[0]
            if func not in (3, 4):
                self._send_exception(tx_id, unit_id, func, 1)
                continue
            if len(pdu) != 5:
                self._send_exception(tx_id, unit_id, func, 3)
                continue
            address, count = struct.unpack(">HH", pdu[1:5])
            if count < 1 or count > 125:
                self._send_exception(tx_id, unit_id, func, 3)
                continue
            words = self.profile.read_words(func, address, count)
            if words is None or len(words) != count:
                self._send_exception(tx_id, unit_id, func, 2)
                continue
            byte_count = count * 2
            resp_pdu = bytes([func, byte_count]) + b"".join(struct.pack(">H", w) for w in words)
            self._send_mbap(tx_id, unit_id, resp_pdu)

    def _recv_exact(self, n: int) -> bytes | None:
        data = b""
        while len(data) < n:
            chunk = self.request.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _send_mbap(self, tx_id: int, unit_id: int, pdu: bytes) -> None:
        mbap = struct.pack(">HHHB", tx_id, 0, len(pdu) + 1, unit_id)
        self.request.sendall(mbap + pdu)

    def _send_exception(self, tx_id: int, unit_id: int, func: int, exc_code: int) -> None:
        self._send_mbap(tx_id, unit_id, bytes([func | 0x80, exc_code]))


class ThreadedModbusTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _make_handler(profile: FakeBenchProfile, unit_id: int):
    class _Handler(ModbusTCPHandler):
        pass

    _Handler.profile = profile
    _Handler.unit_id = unit_id
    return _Handler


def _print_examples(profile: FakeBenchProfile, host: str, port: int, unit_id: int) -> None:
    print("\nOpen-FDD sample Modbus point rows (for data-model import or manual point creation):\n")
    for d in profile.defs[:8]:
        print(
            {
                "external_id": d.fdd_input,
                "fdd_input": d.fdd_input,
                "brick_type": d.brick_type,
                "unit": d.unit,
                "polling": True,
                "modbus_config": {
                    "host": host,
                    "port": port,
                    "unit_id": unit_id,
                    "timeout": 5,
                    "address": d.address,
                    "count": d.count,
                    "function": d.function,
                    "decode": d.decode,
                    "label": d.point_name,
                },
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fake Modbus TCP HVAC/power-meter device")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--print-map", action="store_true", help="Print markdown register table and exit")
    parser.add_argument("--print-sample-points", action="store_true", help="Print sample Open-FDD point payloads and exit")
    args = parser.parse_args()

    profile = FakeBenchProfile()
    if args.print_map:
        print(profile.register_table_markdown())
        return 0
    if args.print_sample_points:
        _print_examples(profile, args.host, args.port, args.unit_id)
        return 0

    handler = _make_handler(profile, args.unit_id)
    server = ThreadedModbusTCPServer((args.host, args.port), handler)
    stop = threading.Event()

    def _shutdown(*_unused):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    print(f"Fake Modbus device listening on {args.host}:{args.port} unit_id={args.unit_id}")
    print("Supports function codes 3 (holding) and 4 (input). Ctrl+C to stop.")
    print(profile.register_table_markdown())
    with server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        while not stop.is_set():
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
