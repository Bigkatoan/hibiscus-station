"""A serial device that goes away while connected (field report 0.2.5, Windows: "Access is denied"
on COM8 after calibrating): classified as *device lost*, never retried, explained, and reconnected
when the adapter is back (maybe under a new name)."""

from __future__ import annotations

import errno
import json
import logging
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import wait_for

from hibiscus_station.hw.portloss import (
    DeviceLostError,
    find_port,
    is_device_lost,
    port_identity,
    wait_for_ports,
)


# ------------------------------------------------------------------------------ classification
class _WinOSError(OSError):
    def __init__(self, winerror: int, msg: str) -> None:
        super().__init__(None, msg)
        self.winerror = winerror


def _wrapped(inner: BaseException, outer: str) -> ConnectionError:
    try:
        raise inner
    except BaseException as e:
        try:
            raise ConnectionError(outer) from e
        except ConnectionError as c:
            return c


@pytest.mark.parametrize(
    "exc",
    [
        # rustypot on Windows, wrapped by lerobot (the field report)
        _wrapped(
            RuntimeError("Access is denied."),
            "Failed to sync read 'Present_Position' from motor IDs [1, 2, 3, 4, 5, 6] after 1 tries. "
            "Access is denied.",
        ),
        # pyserial on Windows
        RuntimeError("ClearCommError failed (PermissionError(13, 'Access is denied.', None, 5))"),
        RuntimeError("WriteFile failed (PermissionError(13, 'The device does not recognize the command.'))"),
        PermissionError(13, "Access is denied"),
        _WinOSError(1167, "The device is not connected."),
        _WinOSError(22, "The device does not recognize the command."),
        RuntimeError("The device is not ready."),
        # Linux / macOS
        _wrapped(RuntimeError("I/O error"), "Failed to sync read 'Present_Position'. I/O error"),
        OSError(errno.EIO, "Input/output error"),
        OSError(errno.ENODEV, "No such device"),
        OSError(errno.ENXIO, "No such device or address"),
        RuntimeError("device reports readiness to read but returned no data (device disconnected?)"),
        # the mock's injected unplug
        OSError("device disconnected"),
    ],
)
def test_device_lost_errors(exc: BaseException) -> None:
    assert is_device_lost(exc)


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("Operation timed out"),
        RuntimeError("motor 1: Checksum error"),
        _wrapped(RuntimeError("motor 1: Operation timed out"), "Failed to sync read ... timed out"),
        ConnectionError("Failed to write 'Goal_Position' on id_=3 after 3 tries. [TxRxResult] no status"),
        OSError("timeout"),
        RuntimeError("Failed to sync read 'Present_Position': motor 3: overload error."),
    ],
)
def test_packet_errors_are_not_device_lost(exc: BaseException) -> None:
    assert not is_device_lost(exc)


# ------------------------------------------------------------------------------ finding it again
ROWS = [
    {
        "device": "COM5",
        "stable_path": None,
        "vid_pid": "1a86:55d3",
        "serial_number": "5A7A0187",
        "description": "",
    },
    {
        "device": "COM9",
        "stable_path": None,
        "vid_pid": "1a86:55d3",
        "serial_number": "5A7A0199",
        "description": "",
    },
]


def test_port_comes_back_under_a_new_com_number() -> None:
    ident = port_identity("com8", [{**ROWS[0], "device": "COM8"}])
    assert ident is not None and ident["serial_number"] == "5A7A0187"
    assert find_port("COM8", ident, ROWS) == "COM5"
    assert find_port("COM8", ident, ROWS[1:]) is None  # not back yet


def test_identical_adapters_without_serial_numbers_stay_ambiguous() -> None:
    rows = [{**r, "serial_number": None} for r in ROWS]
    ident = {"device": "COM8", "vid_pid": "1a86:55d3", "serial_number": None}
    assert find_port("COM8", ident, rows) is None
    assert find_port("COM8", ident, rows, exclude={"COM9"}) == "COM5"  # the leader keeps COM9
    assert find_port("COM9", ident, rows) == "COM9"  # the old name is back


def test_by_id_path_and_wait_for_ports() -> None:
    by_id = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A7A0187-if00"
    rows = [{"device": "/dev/ttyACM3", "stable_path": by_id, "vid_pid": "1a86:55d3", "serial_number": None}]
    assert find_port(by_id, None, rows) == "/dev/ttyACM3"
    calls = {"n": 0}

    def lister() -> list[dict[str, Any]]:
        calls["n"] += 1
        return rows if calls["n"] >= 3 else []

    t = {"now": 0.0}
    found = wait_for_ports(
        {"follower": (by_id, None)},
        lister,
        timeout_s=10,
        sleep=lambda s: t.__setitem__("now", t["now"] + s),
        clock=lambda: t["now"],
    )
    assert found == {"follower": "/dev/ttyACM3"} and calls["n"] == 3
    assert (
        wait_for_ports(
            {"follower": (by_id, None)},
            lambda: [],
            timeout_s=2,
            sleep=lambda s: t.__setitem__("now", t["now"] + s),
            clock=lambda: t["now"],
        )
        is None
    )


# ------------------------------------------------------------------------------ mock owner
def test_mock_unplug_during_teleop_is_device_lost(connected: Any) -> None:
    from hibiscus_station.mock import get_world
    from hibiscus_station.station import TeleopRequest

    st = connected
    st.start_teleop(TeleopRequest(fps=30))
    get_world("mock://follower").inject(disconnect_after_s=0.2)
    wait_for(lambda: st.owner.state == "error", 4)
    s = st.status()
    assert s["reason"] == "device_lost"
    assert s["lost"]["arm"] == "follower" and s["lost"]["port"] == "mock://follower"
    assert s["lost"]["during"] == "teleop"
    assert s["lost"]["after_torque_on"] is True  # lost within seconds of the torque coming on
    from hibiscus_station.api.schemas import Status

    Status.model_validate(s)
    get_world("mock://follower").faults.disconnect_at = None  # the user plugged it back in
    out = st.reconnect(timeout_s=2)
    assert out["state"] == "idle" and out["lost"] is None
    assert out["robot"]["arms"]["follower"]["calibrated"] is True


# ------------------------------------------------------------------------------ real stack (pty)
posix = pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only")


@pytest.fixture
def emus() -> Iterator[tuple[Any, Any]]:
    if sys.platform == "win32":  # pragma: no cover
        pytest.skip("pseudo-terminals are POSIX only")
    from sts_emulator import STSEmulator

    f, ld = STSEmulator(seed=1), STSEmulator(seed=2)
    yield f, ld
    f.close()
    ld.close()


def _write_cal(root: Path, folder: str, name: str, cal: dict[str, Any]) -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps(cal, indent=4), encoding="utf-8")
    return p


@posix
def test_bus_stops_retrying_a_lost_device(emus: tuple[Any, Any], caplog: pytest.LogCaptureFixture) -> None:
    from lerobot.motors import Motor, MotorNormMode

    from hibiscus_station.hw.bus import StationMotorsBus

    f, _ = emus
    motors = {f"m{i}": Motor(i, "sts3215", MotorNormMode.RANGE_M100_100) for i in range(1, 7)}
    bus = StationMotorsBus(f.port, motors, arm="follower")
    bus.connect()
    assert bus.sync_read("Present_Position", normalize=False)
    f.close()  # the USB cable is pulled
    caplog.set_level(logging.WARNING)
    with pytest.raises(DeviceLostError) as ei:
        bus.sync_read("Present_Position", normalize=False)
    assert ei.value.arm == "follower" and "I/O error" in ei.value.cause
    assert bus.lost and sum(bus.errors.values()) == 1  # one attempt, no retries
    with pytest.raises(DeviceLostError):
        bus.disable_torque(num_retry=5)  # never touches the port again
    assert sum(bus.errors.values()) == 1
    assert not [r for r in caplog.records if "after" in r.getMessage() and "tries" in r.getMessage()]
    bus.disconnect(disable_torque=False)


@posix
def test_pty_closed_mid_teleop_then_back_under_a_new_name(
    tmp_path: Path, emus: tuple[Any, Any], caplog: pytest.LogCaptureFixture
) -> None:
    from sts_emulator import STSEmulator, lelab_calibration

    from hibiscus_station.errors import StationError
    from hibiscus_station.profiles import FollowerProfile, LeaderProfile, RobotProfile
    from hibiscus_station.station import Station, TeleopRequest

    f, ld = emus
    cal = lelab_calibration()
    root = tmp_path / "calibration"
    _write_cal(root, "robots/so_follower", "arm_follower", cal)
    _write_cal(root, "teleoperators/so_leader", "arm_leader", cal)
    f.preload_calibration(cal)
    ld.preload_calibration(cal)
    ld.hand = lambda i, t: f.servos[i].actual - f.servos[i].offset  # leader mirrors the follower
    st = Station(tmp_path / "home", mock=False, cal_root=root)
    st.settings.safety.smooth_approach_s = 0.2
    st.profiles.put(
        RobotProfile(
            id="arm",
            follower=FollowerProfile(port=f.port, calibration_id="arm_follower"),
            leader=LeaderProfile(port=ld.port, calibration_id="arm_leader"),
        )
    )
    st.start()
    f2 = None
    try:
        s = st.owner.call("connect", robot_id="arm", timeout=30)
        assert s["robot"]["arms"]["follower"]["calibrated"] and s["robot"]["arms"]["leader"]["calibrated"]
        st.start_teleop(TeleopRequest(fps=30))
        time.sleep(0.3)
        caplog.set_level(logging.WARNING)
        f2 = STSEmulator(seed=3)  # opened first so that it gets another pty name than the lost one
        t0 = time.monotonic()
        f.close()  # brown-out right after torque-on: the follower's adapter disappears
        wait_for(lambda: st.owner.state == "error", 3)
        assert time.monotonic() - t0 < 1.0  # no 6 x retries before giving up
        s = st.status()
        assert s["reason"] == "device_lost"
        assert s["lost"]["arm"] == "follower" and s["lost"]["port"] == f.port
        assert s["lost"]["after_torque_on"] is True
        assert not [r for r in caplog.records if "disable_torque failed" in r.getMessage()]
        assert not [r for r in caplog.records if "after 6 tries" in r.getMessage()]
        with pytest.raises(StationError) as ei:  # nothing listed yet
            st.reconnect(timeout_s=0.3, lister=lambda: [])
        assert ei.value.code == "device_lost"

        # The adapter is back as another device (Windows: COM8 -> COM5), same serial number.
        f2.preload_calibration(cal)
        st.owner.port_ids = {
            "follower": {"device": f.port, "vid_pid": "1a86:55d3", "serial_number": "SN-F"},
            "leader": {"device": ld.port, "vid_pid": "1a86:55d3", "serial_number": "SN-L"},
        }
        rows = [
            {"device": f2.port, "stable_path": None, "vid_pid": "1a86:55d3", "serial_number": "SN-F"},
            {"device": ld.port, "stable_path": None, "vid_pid": "1a86:55d3", "serial_number": "SN-L"},
        ]
        out = st.reconnect(timeout_s=2, lister=lambda: rows)
        assert out["state"] == "idle" and out["lost"] is None
        assert out["port_changes"] == {"follower": f2.port}
        assert st.profiles.get("arm").follower.port == f2.port  # type: ignore[union-attr]
        assert out["robot"]["arms"]["follower"]["calibrated"] is True
    finally:
        st.shutdown()
        if f2 is not None:
            f2.close()
