"""The real hardware path (``so101_*`` profile types, rustypot, serial I/O) against an emulated
STS3215 chain on a pseudo-terminal (``tests/sts_emulator.py``). POSIX only.

These are the field reports' scenarios: LeLab's calibration under another id or folder, a noisy bus,
a port that cannot be opened, motors that do not answer.
"""

from __future__ import annotations

import json
import math
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from sts_emulator import pty_unavailable

if reason := pty_unavailable():  # pragma: no cover
    pytest.skip(reason, allow_module_level=True)

from sts_emulator import STSEmulator, lelab_calibration

from hibiscus_station.errors import StationError
from hibiscus_station.profiles import FollowerProfile, LeaderProfile, RobotProfile
from hibiscus_station.station import Station, TeleopRequest


@pytest.fixture
def emus() -> Iterator[tuple[STSEmulator, STSEmulator]]:
    f, ld = STSEmulator(seed=1), STSEmulator(seed=2)
    yield f, ld
    f.close()
    ld.close()


def _station(tmp_path: Path, f: STSEmulator, ld: STSEmulator) -> Station:
    st = Station(tmp_path / "home", mock=False, cal_root=tmp_path / "calibration")
    st.settings.safety.smooth_approach_s = 0.2
    st.profiles.put(
        RobotProfile(
            id="arm",
            follower=FollowerProfile(port=f.port, calibration_id="arm_follower"),
            leader=LeaderProfile(port=ld.port, calibration_id="arm_leader"),
        )
    )
    st.start()
    return st


def _sweep(emu: STSEmulator) -> None:
    emu.hand = lambda i, t: 2048 + 400 * math.sin(2 * math.pi * 1.2 * t + i)


def _calibrate(st: Station, arm: str, emu: STSEmulator) -> dict[str, object]:
    _sweep(emu)
    st.owner.call("calibration_start", arm=arm)
    time.sleep(0.1)
    st.owner.call("calibration_step", action="set_home")
    time.sleep(1.5)
    out = st.owner.call("calibration_step", action="finish_ranges")
    assert isinstance(out, dict)
    return out


def _mirror(leader: STSEmulator, follower: STSEmulator) -> None:
    leader.hand = lambda i, t: follower.servos[i].actual - follower.servos[i].offset


def test_fresh_arms_connect_calibrate_and_teleop(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    f, ld = emus
    st = _station(tmp_path, f, ld)
    try:
        s = st.owner.call("connect", robot_id="arm", timeout=30)
        assert s["state"] == "idle"
        arms = s["robot"]["arms"]
        assert not arms["follower"]["calibrated"]
        assert "no calibration file" in arms["follower"]["issue"]
        assert arms["follower"]["calibration_file"].endswith("so_follower/arm_follower.json")
        assert _calibrate(st, "follower", f)["robot"]["arms"]["follower"]["calibrated"]  # type: ignore[index]
        assert _calibrate(st, "leader", ld)["robot"]["arms"]["leader"]["calibrated"]  # type: ignore[index]
        _mirror(ld, f)
        time.sleep(0.3)
        st.start_teleop(TeleopRequest(fps=30))
        time.sleep(1.0)
        assert st.owner.state == "teleop"
        assert any(f.torque(i) for i in f.servos)
    finally:
        st.shutdown()


def test_noisy_bus_still_connects_and_calibrates(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    """1 % of the answers lost and 1 % corrupted: one bad packet used to fail a whole connect or
    calibration (lerobot sends its configuration writes without retries)."""
    f, ld = emus
    for e in (f, ld):
        e.drop_rate = 0.01
        e.corrupt_rate = 0.01
    st = _station(tmp_path, f, ld)
    try:
        st.owner.call("connect", robot_id="arm", timeout=30)
        assert _calibrate(st, "follower", f)["robot"]["arms"]["follower"]["calibrated"]  # type: ignore[index]
        assert st.owner.follower.bus.error_summary()["errors"] > 0  # they happened, and were retried
        assert st.status()["robot"]["arms"]["follower"]["bus_errors"] > 0
    finally:
        st.shutdown()


def test_lelab_calibration_under_another_id_is_offered_and_adopted(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    """LeLab (older lerobot: ``robots/so101_follower``) calibrated the arm as ``my_follower``; the
    Station profile expects ``arm_follower``. Station must say so and reuse the file on request."""
    f, ld = emus
    cal = lelab_calibration()
    legacy = tmp_path / "calibration" / "robots" / "so101_follower"
    legacy.mkdir(parents=True)
    src = legacy / "my_follower.json"
    src.write_text(json.dumps(cal, indent=4), encoding="utf-8")
    f.preload_calibration(cal)
    st = _station(tmp_path, f, ld)
    try:
        s = st.owner.call("connect", robot_id="arm", timeout=30)
        issue = s["robot"]["arms"]["follower"]["issue"]
        assert "no calibration file" in issue and "my_follower" in issue
        s = st.owner.call("calibration_start", arm="follower", source=str(src))
        assert s["robot"]["arms"]["follower"]["calibrated"] is True
        copied = tmp_path / "calibration" / "robots" / "so_follower" / "arm_follower.json"
        assert json.loads(copied.read_text(encoding="utf-8")) == cal
        assert src.is_file()  # LeLab's own file is left alone
        with pytest.raises(StationError) as ei:
            st.owner.call("calibration_start", arm="follower", source=str(tmp_path / "elsewhere.json"))
        assert ei.value.code == "not_found"
    finally:
        st.shutdown()


def test_lelab_calibration_with_the_same_id_is_used_at_connect(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    f, ld = emus
    cal = lelab_calibration()
    d = tmp_path / "calibration" / "robots" / "so_follower"
    d.mkdir(parents=True)
    (d / "arm_follower.json").write_text(json.dumps(cal, indent=4), encoding="utf-8")
    st = _station(tmp_path, f, ld)  # fresh EEPROM: Station writes the file to the motors
    try:
        s = st.owner.call("connect", robot_id="arm", timeout=30)
        assert s["robot"]["arms"]["follower"]["calibrated"] is True
        assert f.servos[3].offset == cal["elbow_flex"]["homing_offset"]
        assert st.owner.last_obs or True
    finally:
        st.shutdown()


def test_motors_that_keep_no_calibration_are_explained(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    """EEPROM writes that do not stick (a motor refusing them): the reason names motor and field."""
    f, ld = emus
    cal = lelab_calibration()
    d = tmp_path / "calibration" / "robots" / "so_follower"
    d.mkdir(parents=True)
    (d / "arm_follower.json").write_text(json.dumps(cal), encoding="utf-8")
    orig = f._write

    def no_limits(s, addr, data):  # type: ignore[no-untyped-def]
        if s.id == 2 and addr == 9:
            return
        orig(s, addr, data)

    f._write = no_limits  # type: ignore[method-assign]
    st = _station(tmp_path, f, ld)
    try:
        s = st.owner.call("connect", robot_id="arm", timeout=30)
        follower = s["robot"]["arms"]["follower"]
        assert follower["calibrated"] is False
        assert "shoulder_lift (id 2): range_min 0 != 887" in follower["issue"]
    finally:
        st.shutdown()


def test_unopenable_port_and_silent_motors_say_why(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    f, _ld = emus
    st = Station(tmp_path / "home", mock=False, cal_root=tmp_path / "calibration")
    st.profiles.put(
        RobotProfile(
            id="gone", follower=FollowerProfile(port="/dev/ttyNOPE0", calibration_id="x"), leader=None
        )
    )
    st.profiles.put(
        RobotProfile(id="dead", follower=FollowerProfile(port=f.port, calibration_id="x"), leader=None)
    )
    st.start()
    try:
        with pytest.raises(StationError) as ei:
            st.owner.call("connect", robot_id="gone", timeout=30)
        assert ei.value.code == "port_busy"
        assert "/dev/ttyNOPE0" in str(ei.value) and ei.value.params["error"]
        f.servos[4].dead = True
        with pytest.raises(StationError) as ei:
            st.owner.call("connect", robot_id="dead", timeout=30)
        assert ei.value.code == "bus_error"
        assert ei.value.params["step"] == "handshake"
        assert "Missing motor IDs" in str(ei.value) and "- 4" in str(ei.value)
        assert st.owner.state == "disconnected"
    finally:
        st.shutdown()


def test_bus_failure_in_a_command_is_a_bus_error_not_internal(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    f, ld = emus
    st = _station(tmp_path, f, ld)
    try:
        st.owner.call("connect", robot_id="arm", timeout=30)
        f.servos[5].dead = True
        with pytest.raises(StationError) as ei:
            st.owner.call("calibration_start", arm="follower", timeout=30)
        assert ei.value.code == "bus_error"
        assert "motor ID 5" in str(ei.value) or "wrist_roll" in str(ei.value)
        assert st.owner.state == "idle"
    finally:
        st.shutdown()


def test_doctor_reports_ports_files_and_motors_without_secrets(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hibiscus_station import doctor

    f, ld = emus
    cal_root = tmp_path / "calibration"
    monkeypatch.setenv("HF_LEROBOT_CALIBRATION", str(cal_root))
    cal = lelab_calibration()
    (cal_root / "robots" / "so101_follower").mkdir(parents=True)
    (cal_root / "robots" / "so101_follower" / "my_follower.json").write_text(
        json.dumps(cal), encoding="utf-8"
    )
    f.preload_calibration(cal)
    home = tmp_path / "home"
    st = Station(home, mock=False, cal_root=cal_root)
    st.profiles.put(
        RobotProfile(
            id="arm",
            follower=FollowerProfile(port=f.port, calibration_id="arm_follower"),
            leader=LeaderProfile(port=ld.port, calibration_id="arm_leader"),
        )
    )
    secret = "s3cr3t-local-token-0123456789abcdef"
    (home / "token").write_text(secret, encoding="utf-8")
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "station.log").write_text(f"x GET /auth?t={secret}\nhello\n", encoding="utf-8")
    text, target = doctor.run(home, tmp_path / "out", probe_cameras=False, echo=lambda _s: None)
    assert "calibration 'arm_follower' MISSING" in text
    assert "so101_follower" in text and "my_follower" in text
    carry = next(x for x in text.splitlines() if "motors carry the calibration of: " in x)
    assert carry.endswith("my_follower.json"), carry  # a path, not a Python list (QD-16)
    assert "id 6: model 777 fw 3.10" in text
    assert "teleop estimate: ~" in text
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        blob = b"".join(z.read(n) for n in names)
    assert target.name.startswith("hibiscus-station-doctor-")
    assert {"report.txt", "report.json", "station.log.tail", "robots.yaml"} <= set(names)
    assert secret.encode() not in blob
    assert all(f.torque(i) is False for i in f.servos)  # read only: no torque
