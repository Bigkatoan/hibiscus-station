"""Serial port listing and detection (spec §2 L3/L4, §5.2 ``/ports``).

Linux names ports ``/dev/ttyACM0`` with a stable ``/dev/serial/by-id/...`` link; macOS
``/dev/tty.usbmodem...``; Windows ``COM3`` (no stable path: the number sticks to the USB adapter's
serial number, or to the USB socket for adapters without one).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hibiscus_station.hw.locks import normalize_device

BY_ID = Path("/dev/serial/by-id")


def _stable_paths() -> dict[str, str]:
    out: dict[str, str] = {}
    if BY_ID.is_dir():
        for link in BY_ID.iterdir():
            try:
                out[os.path.realpath(link)] = str(link)
            except OSError:  # pragma: no cover
                continue
    return out


def list_ports(in_use: dict[str, str] | None = None, *, usb_only: bool = True) -> list[dict[str, Any]]:
    """USB serial ports with VID:PID, serial number and the stable ``/dev/serial/by-id`` path
    (Linux only; ``None`` elsewhere)."""
    from serial.tools import list_ports as lp

    stable = _stable_paths()
    held = {normalize_device(k): v for k, v in (in_use or {}).items()}
    rows: list[dict[str, Any]] = []
    for p in lp.comports():
        vid, pid = getattr(p, "vid", None), getattr(p, "pid", None)
        if usb_only and vid is None:
            continue
        real = normalize_device(p.device)  # /dev symlinks resolved, COM names upper-cased
        stable_path = stable.get(real)
        holder = held.get(real)
        rows.append(
            {
                "device": p.device,
                "stable_path": stable_path,
                "vid_pid": f"{vid:04x}:{pid:04x}" if vid is not None and pid is not None else None,
                "serial_number": getattr(p, "serial_number", None),
                "description": getattr(p, "description", None) or "",
                "in_use_by": holder,
            }
        )
    rows.sort(key=lambda r: str(r["device"]))
    return rows


def detect_unplug(
    ports_before: list[str],
    lister: Callable[[], list[str]],
    timeout_s: float = 15.0,
    poll_s: float = 0.25,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """Poll until exactly one port of ``ports_before`` disappears (LeLab's unplug flow, one request)."""
    deadline = time.monotonic() + timeout_s
    before = set(ports_before)
    while time.monotonic() < deadline:
        gone = before - set(lister())
        if len(gone) == 1:
            return gone.pop()
        if len(gone) > 1:
            return None
        sleep(poll_s)
    return None


def detect_motion(
    candidates: list[str],
    read_positions: Callable[[str], dict[str, int] | None],
    timeout_s: float = 10.0,
    threshold_steps: int = 50,
    poll_s: float = 0.1,
) -> str | None:
    """Return the port whose raw positions change by more than ``threshold_steps`` ("move the arm")."""
    first: dict[str, dict[str, int]] = {}
    for port in candidates:
        pos = read_positions(port)
        if pos:
            first[port] = pos
    deadline = time.monotonic() + timeout_s
    while first and time.monotonic() < deadline:
        for port, base in first.items():
            pos = read_positions(port)
            if pos and any(abs(pos[m] - base.get(m, pos[m])) > threshold_steps for m in pos):
                return port
        time.sleep(poll_s)
    return None


#: SO-101 kits power the leader from 5 V (USB or a 5 V adapter) and the follower from 7.4 V or 12 V.
LEADER_MAX_V = 6.0
FOLLOWER_MIN_V = 6.5


def role_hint(voltage_v: float | None) -> str | None:
    """``"leader"`` (~5 V), ``"follower"`` (>= 6.5 V) or ``None``: a hint, never a decision."""
    if voltage_v is None:
        return None
    if voltage_v < LEADER_MAX_V:
        return "leader"
    if voltage_v >= FOLLOWER_MIN_V:
        return "follower"
    return None


def _open_probe_bus(port: str, mock: bool) -> Any:
    from lerobot.motors import Motor, MotorNormMode, SerialMotorsBus

    motors = {f"m{i}": Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for i in range(1, 7)}
    if mock or port.startswith("mock://"):
        from hibiscus_station.mock.fakebus import MockMotorsBus

        return MockMotorsBus(port, motors)
    return SerialMotorsBus(port, motors)


def probe_skeleton(port: str) -> dict[str, Any]:
    return {
        "device": port,
        "voltage_v": None,
        "motors": 0,
        "model_number": None,
        "firmware": None,
        "role_hint": None,
        "error": None,
    }


def probe_arm(port: str, mock: bool = False) -> dict[str, Any]:
    """Read only (no torque, no write): supply voltage, model and firmware of the motors on ``port``,
    and the role the voltage suggests. Errors are reported in ``error``, never raised."""
    out = probe_skeleton(port)
    bus = _open_probe_bus(port, mock)
    try:
        bus.connect(handshake=False)
        volts = bus.sync_read("Present_Voltage", normalize=False, num_retry=1)
        vals = sorted(float(v) * 0.1 for v in volts.values() if v)
        if vals:
            out["voltage_v"] = round(vals[len(vals) // 2], 1)
        out["motors"] = len(volts)
        out["model_number"] = bus.ping("m1", num_retry=1)
        major = bus.read("Firmware_Major_Version", "m1", normalize=False, num_retry=1)
        minor = bus.read("Firmware_Minor_Version", "m1", normalize=False, num_retry=1)
        out["firmware"] = f"{int(major)}.{int(minor)}"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        try:
            bus.disconnect(disable_torque=False)
        except Exception:  # noqa: S110 - best effort close of a probe
            pass
    out["role_hint"] = role_hint(out["voltage_v"])
    return out


def read_raw_positions(port: str, mock: bool = False) -> dict[str, int] | None:
    """Open a port at 1 Mbaud, read Present_Position of ids 1-6 raw, close. ``None`` on failure."""
    bus = _open_probe_bus(port, mock)
    try:
        bus.connect(handshake=False)
        vals = bus.sync_read("Present_Position", normalize=False, num_retry=1)
        return {k: int(v) for k, v in vals.items()}
    except Exception:
        return None
    finally:
        try:
            bus.disconnect(disable_torque=False)
        except Exception:  # noqa: S110 - best effort close of a probe
            pass
