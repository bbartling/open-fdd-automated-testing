#!/usr/bin/env python3
"""
Fake Modbus TCP energy meter for Open-FDD bench/lab testing.

Standard-library only. Supports Modbus function codes 3 and 4.

Run:
  python scripts/fake_modbus_device.py --host 0.0.0.0 --port 1502 --unit-id 1
"""

from __future__ import annotations

import argparse
import math
import signal
import socketserver
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable


def _u16(v: int) -> int:
    return int(v) & 0xFFFF


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

    def words(self, elapsed_seconds: float) -> list[int]:
        return self.words_fn(self.value_fn(elapsed_seconds))


class FakeEnergyMeterProfile:
    """Dynamic, realistic 3-phase electrical meter behavior."""

    def __init__(self) -> None:
        self.start = time.time()
        self._defs = self._build_defs()
        self._holding = {d.address: d for d in self._defs if d.function == "holding"}
        self._input = {d.address: d for d in self._defs if d.function == "input"}

    @property
    def defs(self) -> list[RegisterDef]:
        return list(self._defs)

    def _elapsed(self) -> float:
        return max(0.0, time.time() - self.start)

    def _build_defs(self) -> list[RegisterDef]:
        return [
            RegisterDef(0, "holding", _f32_words, self.voltage_ll_v, "Voltage L-L", "V", "Voltage_Sensor", "line_voltage_v", "3-phase line-line voltage", "float32", 2),
            RegisterDef(2, "holding", _f32_words, self.current_a, "Current", "A", "Current_Sensor", "line_current_a", "3-phase current", "float32", 2),
            RegisterDef(4, "holding", _f32_words, self.real_power_kw, "Real Power", "kW", "Power_Sensor", "meter_power_kw", "Instantaneous real power", "float32", 2),
            RegisterDef(6, "holding", _f32_words, self.reactive_power_kvar, "Reactive Power", "kVAR", "Reactive_Power_Sensor", "meter_reactive_power_kvar", "Instantaneous reactive power", "float32", 2),
            RegisterDef(8, "holding", _f32_words, self.apparent_power_kva, "Apparent Power", "kVA", "Apparent_Power_Sensor", "meter_apparent_power_kva", "Instantaneous apparent power", "float32", 2),
            RegisterDef(10, "holding", _f32_words, self.power_factor, "Power Factor", "ratio", "Power_Factor_Sensor", "power_factor", "True power factor", "float32", 2),
            RegisterDef(12, "holding", _f32_words, self.frequency_hz, "Frequency", "Hz", "Frequency_Sensor", "line_frequency_hz", "System line frequency", "float32", 2),
            RegisterDef(14, "holding", _f32_words, self.energy_import_kwh, "Energy Import", "kWh", "Energy_Sensor", "meter_energy_import_kwh", "Accumulated imported energy", "float32", 2),
            RegisterDef(16, "holding", _f32_words, self.energy_export_kwh, "Energy Export", "kWh", "Energy_Sensor", "meter_energy_export_kwh", "Accumulated exported energy", "float32", 2),
            RegisterDef(18, "holding", _f32_words, self.demand_kw_15m, "Demand 15m", "kW", "Demand_Sensor", "meter_demand_kw_15m", "Rolling 15-minute demand estimate", "float32", 2),
            RegisterDef(20, "holding", _u32_words, self.runtime_seconds, "Meter Runtime", "s", "Runtime_Sensor", "meter_runtime_seconds", "Runtime since process start", "uint32", 2),
            RegisterDef(100, "input", _f32_words, self.price_usd_per_kwh, "Tariff", "USD/kWh", "Price_Sensor", "energy_rate_usd_per_kwh", "Time-of-use tariff", "float32", 2),
            RegisterDef(102, "input", _f32_words, self.energy_cost_usd, "Energy Cost", "USD", "Cost_Sensor", "energy_cost_usd", "Imported energy cost estimate", "float32", 2),
        ]

    # ---- signal model ----
    def _base_load_kw(self, t: float) -> float:
        daily = 8.0 + 4.0 * math.sin((2.0 * math.pi * t) / 300.0)
        pulse = 2.2 if int(t) % 97 < 8 else 0.0
        jitter = 0.6 * math.sin((2.0 * math.pi * t) / 23.0)
        return max(1.2, daily + pulse + jitter)

    def voltage_ll_v(self, t: float) -> float:
        return round(480.0 + 3.5 * math.sin((2.0 * math.pi * t) / 41.0), 2)

    def power_factor(self, t: float) -> float:
        return round(0.95 - 0.03 * abs(math.sin((2.0 * math.pi * t) / 120.0)), 3)

    def frequency_hz(self, t: float) -> float:
        return round(60.0 + 0.03 * math.sin((2.0 * math.pi * t) / 51.0), 3)

    def real_power_kw(self, t: float) -> float:
        return round(self._base_load_kw(t), 3)

    def apparent_power_kva(self, t: float) -> float:
        pf = max(0.5, self.power_factor(t))
        return round(self.real_power_kw(t) / pf, 3)

    def reactive_power_kvar(self, t: float) -> float:
        kva = self.apparent_power_kva(t)
        kw = self.real_power_kw(t)
        kvar_sq = max(0.0, kva * kva - kw * kw)
        return round(math.sqrt(kvar_sq), 3)

    def current_a(self, t: float) -> float:
        denom = max(1.0, self.voltage_ll_v(t) * 1.732 * self.power_factor(t))
        amps = (self.real_power_kw(t) * 1000.0) / denom
        return round(amps, 3)

    def energy_import_kwh(self, t: float) -> float:
        # Approximate integrated energy from average demand profile.
        hours = t / 3600.0
        avg_kw = 7.8 + 1.1 * math.sin((2.0 * math.pi * t) / 900.0)
        return round(max(0.0, hours * avg_kw), 4)

    def energy_export_kwh(self, t: float) -> float:
        # Small occasional export for DER backfeed simulation.
        hours = t / 3600.0
        export_kw = 0.25 + 0.2 * max(0.0, math.sin((2.0 * math.pi * t) / 500.0))
        return round(hours * export_kw, 4)

    def demand_kw_15m(self, t: float) -> float:
        # Demand tracks power with mild smoothing offset.
        return round(max(0.0, self.real_power_kw(t) * 0.92 + 0.4), 3)

    def runtime_seconds(self, t: float) -> int:
        return int(max(0.0, t))

    def price_usd_per_kwh(self, t: float) -> float:
        hour = ((t / 300.0) % 1.0) * 24.0
        if 13.0 <= hour < 19.0:
            return 0.19
        if 7.0 <= hour < 13.0:
            return 0.13
        return 0.09

    def energy_cost_usd(self, t: float) -> float:
        return round(self.energy_import_kwh(t) * self.price_usd_per_kwh(t), 4)

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
    profile: FakeEnergyMeterProfile
    unit_id: int

    def handle(self) -> None:
        while True:
            header = self._recv_exact(7)
            if not header:
                return
            tx_id, proto_id, length, unit_id = struct.unpack(">HHHB", header)
            if proto_id != 0 or length < 2 or length > 254:
                return
            pdu = self._recv_exact(length - 1)
            if not pdu:
                return

            func = pdu[0]
            if unit_id != self.unit_id:
                self._send_exception(tx_id, unit_id, func, 11)
                continue
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

            resp_pdu = bytes([func, count * 2]) + b"".join(struct.pack(">H", w) for w in words)
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


def _make_handler(profile: FakeEnergyMeterProfile, unit_id: int):
    class _Handler(ModbusTCPHandler):
        pass

    _Handler.profile = profile
    _Handler.unit_id = unit_id
    return _Handler


def _print_sample_points(profile: FakeEnergyMeterProfile, host: str, port: int, unit_id: int) -> None:
    print("\nOpen-FDD sample point payloads (first 10):\n")
    for d in profile.defs[:10]:
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
    parser = argparse.ArgumentParser(description="Fake Modbus TCP energy meter")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1502)
    parser.add_argument("--unit-id", type=int, default=1)
    parser.add_argument("--print-map", action="store_true", help="Print markdown register map and exit")
    parser.add_argument("--print-sample-points", action="store_true", help="Print sample Open-FDD point payloads and exit")
    args = parser.parse_args()

    profile = FakeEnergyMeterProfile()
    if args.print_map:
        print(profile.register_table_markdown())
        return 0
    if args.print_sample_points:
        _print_sample_points(profile, args.host, args.port, args.unit_id)
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

    print(f"Fake Modbus energy meter listening on {args.host}:{args.port} unit_id={args.unit_id}")
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
