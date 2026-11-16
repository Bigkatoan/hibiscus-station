"""Non-interactive two-step calibration on lerobot's public bus API (spec §2 L7, §6.3).

Same semantics as ``SerialMotorsBus.record_calibration`` (``motors_bus.py:931-1008``) without
``input()``: torque off, position mode, Feetech drive mode 0 (software), ``set_half_turn_homings``
at "Set home", then min/max of raw positions per motor.

Like LeLab (``app/calibrating.py``), EVERY motor's range is recorded, ``wrist_roll`` included
(lerobot's own CLI treats ``wrist_roll`` as full-turn; the owner chose LeLab's behaviour so the
roll joint gets real limits). Glitched reads outside 0..resolution are ignored, as LeLab does.
Runs only in the hardware-owner thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lerobot.motors import MotorCalibration

#: Motors given the whole encoder instead of a recorded range. Empty = LeLab behaviour.
FULL_TURN_MOTORS: tuple[str, ...] = ()
MIN_RANGE_STEPS = 100


class CalibrationError(Exception):
    pass


@dataclass
class CalibrationProcess:
    arm: str  # follower | leader
    device: Any  # SOFollower / SOLeader
    step: str = "home"
    homings: dict[str, int] = field(default_factory=dict)
    mins: dict[str, int] = field(default_factory=dict)
    maxes: dict[str, int] = field(default_factory=dict)
    pos: dict[str, int] = field(default_factory=dict)

    @property
    def bus(self) -> Any:
        return self.device.bus

    def start(self) -> None:
        motors = list(self.bus.motors)
        self.bus.disable_torque(motors)
        self.bus.set_operating_mode("position", motors)
        self.step = "home"
        self.sample()

    def sample(self) -> dict[str, int]:
        raw = self.bus.sync_read("Present_Position", normalize=False, num_retry=1)
        self.pos = {m: int(v) for m, v in raw.items()}
        if self.step == "ranges":
            for m, v in self.pos.items():
                if m in FULL_TURN_MOTORS:
                    continue
                if not 0 <= v < self.bus.resolution(self.bus.motors[m].model):
                    continue  # glitched read (LeLab skips these too)
                self.mins[m] = min(self.mins.get(m, v), v)
                self.maxes[m] = max(self.maxes.get(m, v), v)
        return self.pos

    def set_home(self) -> None:
        if self.step != "home":
            raise CalibrationError(f"set_home is only valid in step 'home' (now {self.step})")
        self.homings = self.bus.set_half_turn_homings(list(self.bus.motors))
        self.step = "ranges"
        self.mins, self.maxes = {}, {}
        self.sample()

    def range_ok(self, m: str) -> bool:
        lo, hi = self.mins.get(m), self.maxes.get(m)
        return m in FULL_TURN_MOTORS or (lo is not None and hi is not None and hi - lo >= MIN_RANGE_STEPS)

    def warnings(self) -> list[str]:
        out = []
        for m in self.bus.motors:
            if m in FULL_TURN_MOTORS:
                continue
            lo, hi = self.mins.get(m), self.maxes.get(m)
            if lo is None or hi is None:
                continue
            if hi - lo < MIN_RANGE_STEPS:
                out.append(
                    f"{m}: range {hi - lo} steps (< {MIN_RANGE_STEPS}); move it through its full range"
                )
        return out

    def view(self) -> dict[str, Any]:
        motors: dict[str, Any] = {}
        for m in self.bus.motors:
            full = m in FULL_TURN_MOTORS
            motors[m] = {
                "min": 0 if full and self.step == "ranges" else self.mins.get(m),
                "pos": self.pos.get(m),
                "max": self.bus.resolution(self.bus.motors[m].model) - 1
                if full and self.step == "ranges"
                else self.maxes.get(m),
                "full_turn": full,
                "ok": self.step == "ranges" and self.range_ok(m),
            }
        return {
            "arm": self.arm,
            "step": self.step,
            "motors": motors,
            "warnings": self.warnings(),
            "min_range": MIN_RANGE_STEPS,
            "ready": self.step == "ranges" and all(self.range_ok(m) for m in self.bus.motors),
        }

    def finish(self) -> tuple[dict[str, MotorCalibration], list[str]]:
        if self.step != "ranges":
            raise CalibrationError("finish_ranges is only valid in step 'ranges'")
        errors = []
        for m in self.bus.motors:
            if m in FULL_TURN_MOTORS:
                continue
            if self.mins.get(m) is None or self.mins.get(m) == self.maxes.get(m):
                errors.append(f"{m}: min and max are equal; move it through its range")
            elif not self.range_ok(m):
                errors.append(
                    f"{m}: moved {self.maxes[m] - self.mins[m]} steps (< {MIN_RANGE_STEPS}); "
                    "move it through its full range"
                )
        if errors:
            raise CalibrationError("; ".join(errors))
        cal: dict[str, MotorCalibration] = {}
        for m, motor in self.bus.motors.items():
            if m in FULL_TURN_MOTORS:
                lo, hi = 0, self.bus.resolution(motor.model) - 1
            else:
                lo, hi = self.mins[m], self.maxes[m]
            cal[m] = MotorCalibration(
                id=motor.id,
                drive_mode=0,
                homing_offset=int(self.homings[m]),
                range_min=int(lo),
                range_max=int(hi),
            )
        warnings = self.warnings()
        self.bus.write_calibration(cal)
        self.device.calibration = cal
        self.device._save_calibration()
        self.step = "done"
        return cal, warnings

    def cancel(self) -> None:
        self.step = "cancelled"


def apply_existing(device: Any) -> bool:
    """``keep_existing``: write the calibration file of this id to the motors (torque off)."""
    if not device.calibration:
        return False
    device.bus.disable_torque()
    device.bus.write_calibration(device.calibration)
    return True


def mismatch(device: Any) -> str:
    """Which motors read back other values than the calibration file (for error messages)."""
    try:
        actual = device.bus.read_calibration()
    except Exception as exc:
        return f"cannot read the motors back: {exc}"
    out = []
    for m, want in (device.calibration or {}).items():
        got = actual.get(m)
        if got is None:
            out.append(f"{m}: missing")
            continue
        fields = [
            f"{name} {getattr(got, name)} != {getattr(want, name)}"
            for name in ("homing_offset", "range_min", "range_max")
            if getattr(got, name) != getattr(want, name)
        ]
        if fields:
            out.append(f"{m} (id {want.id}): " + ", ".join(fields))
    return "; ".join(out) or "no difference found"


# ----------------------------------------------------------------------------- which file is it?
#: Leader and follower held in the same pose should read within this many degrees (percent for the
#: gripper) per joint once both are calibrated; more means a wrong file or swapped roles.
POSE_MATCH_DEG = 20.0
CAL_FIELDS = ("homing_offset", "range_min", "range_max")


def load_file(path: str | Path) -> dict[str, dict[str, Any]] | None:
    """A lerobot calibration json (``{motor: {id, drive_mode, homing_offset, range_min, range_max}}``),
    or ``None`` when it is not one."""
    import json

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    if not all(isinstance(v, dict) and all(k in v for k in CAL_FIELDS) for v in data.values()):
        return None
    return data


def eeprom_matches(eeprom: dict[str, MotorCalibration], cal: dict[str, dict[str, Any]] | None) -> bool:
    """Do the motors carry exactly this file's homing offsets and limits (the doctor's check)?"""
    if not cal or not eeprom or set(cal) != set(eeprom):
        return False
    for m, want in cal.items():
        got = eeprom[m]
        if "id" in want and int(want["id"]) != got.id:
            return False
        if any(int(want[k]) != int(getattr(got, k)) for k in CAL_FIELDS):
            return False
    return True


def pose_compare(
    follower: dict[str, float],
    leader: dict[str, float],
    units: dict[str, str],
    threshold: float = POSE_MATCH_DEG,
) -> dict[str, Any]:
    """Per-joint difference between the follower and the leader held in the same pose."""
    joints: list[dict[str, Any]] = []
    for m in follower:
        if m not in leader:
            continue
        diff = abs(float(follower[m]) - float(leader[m]))
        joints.append(
            {
                "joint": m,
                "follower": round(float(follower[m]), 1),
                "leader": round(float(leader[m]), 1),
                "diff": round(diff, 1),
                "unit": units.get(m, "deg"),
                "ok": diff <= threshold,
            }
        )
    bad = [j for j in joints if not j["ok"]]
    worst = max(joints, key=lambda j: float(j["diff"]), default=None)
    return {
        "joints": joints,
        "threshold": threshold,
        "ok": not bad,
        "off": [j["joint"] for j in bad],
        "worst": worst["joint"] if worst is not None and bad else None,
        "max_diff": worst["diff"] if worst is not None else 0.0,
    }
