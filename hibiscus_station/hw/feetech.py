"""Feetech STS3215 telemetry registers, units and status bits: the ONE place they live (spec §4.5.2).

Register names and addresses are checked against rustypot's ``sts3215`` definition (lerobot 0.7.1
uses rustypot 1.13.x): ``present_load`` 60 (2 B, sign bit 10), ``present_voltage`` 62,
``present_temperature`` 63, ``status`` 65, ``present_current`` 69, ``max_temperature_limit`` 13,
``max_voltage_limit`` 14, ``min_voltage_limit`` 15, ``protection_current`` 28.

**Not confirmed on hardware yet** (HIL checklist, docs/user-guide/*/station-hardware-uat.md):
the current unit (6.5 mA per step) and the status-bit layout come from Feetech's STS memory table,
not from lerobot. Tests pin these decode functions, not the hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# Telemetry groups: one lerobot ``sync_read(register, normalize=False)`` each (one packet / bus).
REG_TEMPERATURE: Final = "Present_Temperature"
REG_VOLTAGE: Final = "Present_Voltage"
REG_CURRENT: Final = "Present_Current"
REG_LOAD: Final = "Present_Load"
REG_STATUS: Final = "Status"

# Read once at connect.
REG_MAX_TEMPERATURE: Final = "Max_Temperature_Limit"
REG_MAX_VOLTAGE: Final = "Max_Voltage_Limit"
REG_MIN_VOLTAGE: Final = "Min_Voltage_Limit"
REG_PROTECTION_CURRENT: Final = "Protection_Current"


@dataclass(frozen=True)
class Group:
    name: str  # field name in samples: temp_c, voltage_v, current_a, load_pct, status
    register: str
    hot: bool  # hot groups are read at telemetry.hot_hz, the others at cool_hz


GROUPS: Final[tuple[Group, ...]] = (
    Group("temp_c", REG_TEMPERATURE, True),
    Group("status", REG_STATUS, True),
    Group("voltage_v", REG_VOLTAGE, False),
    Group("current_a", REG_CURRENT, False),
    Group("load_pct", REG_LOAD, False),
)
GROUP_BY_NAME: Final = {g.name: g for g in GROUPS}

VOLTAGE_UNIT_V: Final = 0.1
CURRENT_UNIT_A: Final = 0.0065
LOAD_UNIT_PCT: Final = 0.1
LOAD_SIGN_BIT: Final = 10

# Status (address 65) bit -> name. Feetech STS: bit 0 voltage, 1 angle sensor, 2 overheat,
# 3 overcurrent, 5 overload. Bits 4/6/7 are unused on the STS3215.
STATUS_BITS: Final[dict[int, str]] = {
    0: "voltage",
    1: "angle_sensor",
    2: "overheat",
    3: "overcurrent",
    5: "overload",
}
STATUS_CRITICAL: Final = frozenset({"overheat", "overload"})
STATUS_ELECTRICAL: Final = frozenset({"overcurrent"})
#: Motors whose overload bit is part of normal use (grasping), never a safe stop on its own.
GRASP_MOTORS: Final = frozenset({"gripper"})

DEFAULT_MAX_TEMPERATURE_C: Final = 70.0


def decode_temperature(raw: int) -> float:
    return float(raw)


def decode_voltage(raw: int) -> float:
    return round(raw * VOLTAGE_UNIT_V, 2)


def decode_current(raw: int) -> float:
    return round(raw * CURRENT_UNIT_A, 4)


def decode_load(raw: int) -> float:
    """Signed load in % of max torque. Bit 10 is the sign (sign-magnitude), unit 0.1 %.

    rustypot may already return a signed integer (it knows the sign bit); both forms decode alike.
    """
    if raw < 0:
        return round(raw * LOAD_UNIT_PCT, 1)
    magnitude = raw & ((1 << LOAD_SIGN_BIT) - 1)
    sign = -1 if raw & (1 << LOAD_SIGN_BIT) else 1
    return round(sign * magnitude * LOAD_UNIT_PCT, 1)


def encode_load(pct: float) -> int:
    """Inverse of :func:`decode_load` (used by the mock bus)."""
    mag = min(round(abs(pct) / LOAD_UNIT_PCT), (1 << LOAD_SIGN_BIT) - 1)
    return mag | (1 << LOAD_SIGN_BIT) if pct < 0 else mag


def decode_status(raw: int) -> list[str]:
    return [name for bit, name in sorted(STATUS_BITS.items()) if raw & (1 << bit)]


def encode_status(names: list[str] | tuple[str, ...] | set[str]) -> int:
    inv = {v: k for k, v in STATUS_BITS.items()}
    out = 0
    for n in names:
        out |= 1 << inv[n]
    return out


def decode(group: str, raw: int) -> float | list[str]:
    if group == "temp_c":
        return decode_temperature(raw)
    if group == "voltage_v":
        return decode_voltage(raw)
    if group == "current_a":
        return decode_current(raw)
    if group == "load_pct":
        return decode_load(raw)
    if group == "status":
        return decode_status(raw)
    raise KeyError(group)
