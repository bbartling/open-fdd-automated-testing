"""Unit tests for modbus_point_config.normalize_modbus_config."""

from openfdd_stack.platform.modbus_point_config import normalize_modbus_config


def test_normalize_minimal():
    n = normalize_modbus_config({"host": "10.0.0.1", "address": 100})
    assert n is not None
    assert n["host"] == "10.0.0.1"
    assert n["address"] == 100
    assert n["port"] == 502
    assert n["unit_id"] == 1
    assert n["function"] == "holding"
    assert n["count"] == 1


def test_normalize_rejects_bad_port():
    assert normalize_modbus_config({"host": "h", "address": 0, "port": 0}) is None
    assert normalize_modbus_config({"host": "h", "address": 0, "port": 70000}) is None


def test_normalize_rejects_bad_decode():
    assert normalize_modbus_config({"host": "h", "address": 0, "decode": "nope"}) is None


def test_normalize_coerces_float32_decode():
    n = normalize_modbus_config(
        {"host": "h", "address": 0, "count": 2, "function": "input", "decode": "float32"}
    )
    assert n is not None
    assert n["decode"] == "float32"


def _base(host: str = "10.0.0.1", address: int = 0):
    return {"host": host, "address": address}


def test_normalize_rejects_empty_or_whitespace_host():
    assert normalize_modbus_config({"host": "", "address": 0}) is None
    assert normalize_modbus_config({"host": "   ", "address": 0}) is None


def test_normalize_address_boundaries():
    assert normalize_modbus_config(_base(address=-1)) is None
    assert normalize_modbus_config(_base(address=65536)) is None
    assert normalize_modbus_config(_base(address=0)) is not None
    assert normalize_modbus_config(_base(address=65535)) is not None


def test_normalize_unit_id_upper_bound():
    assert normalize_modbus_config({**_base(), "unit_id": 248}) is None
    assert normalize_modbus_config({**_base(), "unit_id": 247}) is not None


def test_normalize_timeout_boundaries():
    assert normalize_modbus_config({**_base(), "timeout": 0.09}) is None
    assert normalize_modbus_config({**_base(), "timeout": 0.1}) is not None
    assert normalize_modbus_config({**_base(), "timeout": 120.0}) is not None
    assert normalize_modbus_config({**_base(), "timeout": 120.1}) is None


def test_normalize_count_boundaries():
    assert normalize_modbus_config({**_base(), "count": 0}) is None
    assert normalize_modbus_config({**_base(), "count": 1}) is not None
    assert normalize_modbus_config({**_base(), "count": 125}) is not None
    assert normalize_modbus_config({**_base(), "count": 126}) is None
