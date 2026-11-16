"""Calibration as simple as LeLab (field report 0.2.5: "calib xong không teleop được").

Station reads the motors' EEPROM and tells which calibration file on disk they carry, so the user
adopts the right file in one click instead of guessing among ``so_101_follower`` / ``SO-ARM101`` /
the profile id; a file of the other arm is never offered; a pose check after calibrating catches a
wrong file before teleop.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from hibiscus_station.hw import calibration as calib

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("pseudo-terminals are POSIX only", allow_module_level=True)

from sts_emulator import STSEmulator, lelab_calibration

from hibiscus_station.api.schemas import CalibrationCheck, PoseCompare
from hibiscus_station.errors import StationError
from hibiscus_station.profiles import FollowerProfile, LeaderProfile, RobotProfile
from hibiscus_station.station import Station


def leader_calibration() -> dict[str, dict[str, Any]]:
    cal = lelab_calibration()
    return {
        m: {**v, "homing_offset": v["homing_offset"] + 100, "range_min": v["range_min"] + 20}
        for m, v in cal.items()
    }


@pytest.fixture
def emus() -> Iterator[tuple[STSEmulator, STSEmulator]]:
    f, ld = STSEmulator(seed=1), STSEmulator(seed=2)
    yield f, ld
    f.close()
    ld.close()


def _write(root: Path, folder: str, name: str, cal: dict[str, Any]) -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.json"
    p.write_text(json.dumps(cal, indent=4), encoding="utf-8")
    return p


def _station(tmp_path: Path, f: STSEmulator, ld: STSEmulator) -> Station:
    st = Station(tmp_path / "home", mock=False, cal_root=tmp_path / "calibration")
    st.profiles.put(
        RobotProfile(
            id="so_101_1",
            follower=FollowerProfile(port=f.port, calibration_id="so_101_1_follower"),
            leader=LeaderProfile(port=ld.port, calibration_id="so_101_1_leader"),
        )
    )
    st.start()
    return st


def test_check_finds_the_file_the_motors_carry_and_never_the_other_arms(
    tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]
) -> None:
    """The field report's disk: LeLab's so_101_follower / so_101_leader, an unrelated SO-ARM101, and a
    copy of the leader's file saved in the follower folder."""
    f, ld = emus
    root = tmp_path / "calibration"
    fcal, lcal = lelab_calibration(), leader_calibration()
    good_f = _write(root, "robots/so_follower", "so_101_follower", fcal)
    other = {m: {**v, "homing_offset": v["homing_offset"] - 300} for m, v in fcal.items()}
    _write(root, "robots/so_follower", "SO-ARM101", other)
    stray = _write(root, "robots/so_follower", "so_101_leader_copy", lcal)
    good_l = _write(root, "teleoperators/so_leader", "so_101_leader", lcal)
    f.preload_calibration(fcal)
    ld.preload_calibration(lcal)
    st = _station(tmp_path, f, ld)
    try:
        st.owner.call("connect", robot_id="so_101_1", timeout=30)
        chk = st.owner.call("calibration_check", timeout=10)
        CalibrationCheck.model_validate(chk)
        fol, lea = chk["arms"]["follower"], chk["arms"]["leader"]
        assert fol["state"] == "adopt" and fol["suggestion"]["path"] == str(good_f)
        assert lea["state"] == "adopt" and lea["suggestion"]["path"] == str(good_l)
        rows = {Path(r["path"]).name: r for r in fol["files"]}
        assert rows["SO-ARM101.json"]["matches_motors"] is False
        assert rows["so_101_leader_copy.json"]["matches_other_arm"] is True
        assert rows["so_101_leader_copy.json"]["matches_motors"] is False
        assert all(Path(r["path"]).parent.name == "so_leader" for r in lea["files"])  # never a follower file

        # One click: adopt the suggestion; afterwards the check says "calibrated, use it".
        st.owner.call("calibration_start", arm="follower", source=fol["suggestion"]["path"])
        st.owner.call("calibration_start", arm="leader", source=lea["suggestion"]["path"])
        chk = st.owner.call("calibration_check", timeout=10)
        assert chk["arms"]["follower"]["state"] == "ok" and chk["arms"]["leader"]["state"] == "ok"
        assert chk["arms"]["follower"]["files"][0]["own"] is True
        with pytest.raises(StationError):  # a follower-folder file is refused for the leader
            st.owner.call("calibration_start", arm="leader", source=str(stray))
    finally:
        st.shutdown()


def test_fresh_arm_needs_calibration(tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]) -> None:
    f, ld = emus
    _write(tmp_path / "calibration", "robots/so_follower", "SO-ARM101", lelab_calibration())
    st = _station(tmp_path, f, ld)
    try:
        st.owner.call("connect", robot_id="so_101_1", timeout=30)
        chk = st.owner.call("calibration_check", timeout=10)
        assert chk["arms"]["follower"]["state"] == "needs_calibration"
        assert chk["arms"]["follower"]["suggestion"] is None
        assert chk["arms"]["leader"]["state"] == "needs_calibration"
    finally:
        st.shutdown()


def test_pose_compare_catches_a_wrong_file(tmp_path: Path, emus: tuple[STSEmulator, STSEmulator]) -> None:
    f, ld = emus
    cal = lelab_calibration()
    root = tmp_path / "calibration"
    _write(root, "robots/so_follower", "so_101_1_follower", cal)
    _write(root, "teleoperators/so_leader", "so_101_1_leader", cal)
    shift = {"n": 0.0}
    ld.hand = lambda i, t: f.servos[i].actual - f.servos[i].offset + (shift["n"] if i == 3 else 0.0)
    st = _station(tmp_path, f, ld)
    try:
        st.owner.call("connect", robot_id="so_101_1", timeout=30)
        out = st.owner.call("pose_compare", timeout=10)
        PoseCompare.model_validate(out)
        assert out["ok"] is True and out["max_diff"] < 2
        assert {j["unit"] for j in out["joints"]} == {"deg", "%"}
        shift["n"] = 400.0  # ~35 deg on elbow_flex: the leader file is not this arm's
        import time

        time.sleep(0.1)
        out = st.owner.call("pose_compare", timeout=10)
        assert out["ok"] is False and out["off"] == ["elbow_flex"] and out["worst"] == "elbow_flex"
    finally:
        st.shutdown()


# ------------------------------------------------------------------------------ LeLab's rules
class _Motor:
    def __init__(self, i: int) -> None:
        self.id = i
        self.model = "sts3215"


class _Bus:
    def __init__(self) -> None:
        self.motors = {m: _Motor(i) for i, m in enumerate(("a", "b"), 1)}
        self.pos = {"a": 2000, "b": 2000}

    def resolution(self, _model: str) -> int:
        return 4096

    def sync_read(self, *_a: Any, **_k: Any) -> dict[str, int]:
        return dict(self.pos)

    def set_half_turn_homings(self, motors: list[str]) -> dict[str, int]:
        return dict.fromkeys(motors, 0)


class _Dev:
    def __init__(self) -> None:
        self.bus = _Bus()


def test_save_needs_every_joint_moved() -> None:
    proc = calib.CalibrationProcess("follower", _Dev())
    proc.step = "home"
    proc.set_home()
    proc.device.bus.pos = {"a": 2400, "b": 2050}
    proc.sample()
    view = proc.view()
    assert view["motors"]["a"]["ok"] is True and view["motors"]["b"]["ok"] is False
    assert view["ready"] is False and view["min_range"] == calib.MIN_RANGE_STEPS
    with pytest.raises(calib.CalibrationError, match="b: moved 50 steps"):
        proc.finish()
    proc.device.bus.pos = {"a": 2400, "b": 2200}
    proc.sample()
    assert proc.view()["ready"] is True


def test_pose_compare_math() -> None:
    out = calib.pose_compare(
        {"elbow_flex": 10.0, "gripper": 50.0}, {"elbow_flex": 35.0, "gripper": 45.0}, {"gripper": "%"}
    )
    assert out["off"] == ["elbow_flex"] and out["max_diff"] == 25.0
    assert calib.eeprom_matches({}, None) is False
