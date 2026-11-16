"""Robot profiles: ``robots.yaml`` (spec §5.3 RobotProfile, §7)."""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hibiscus_station.settings import Thresholds, write_private

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
CAMERA_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,31}$")

FollowerType = Literal["so100_follower", "so101_follower", "hibiscus_mock_follower"]
LeaderType = Literal["so100_leader", "so101_leader", "hibiscus_mock_leader"]


class GripHold(BaseModel):
    """``gripper holding object`` (station-programs.md §4): after a close, holding = the gripper's
    goal-position gap is at least ``gap_min`` and |load| at least ``load_min_pct``. Calibrated on a
    test grasp (team B)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    gap_min: float = Field(3.0, ge=0, le=100, description="goal - present, gripper range units")
    load_min_pct: float = Field(15.0, ge=0, le=100)


class FollowerProfile(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    type: FollowerType = "so101_follower"
    port: str
    calibration_id: str
    max_relative_target: float | dict[str, float] | None = 5.0
    rest_pose: dict[str, float] | None = None
    on_session_end: Literal["hold", "relax"] = "hold"
    disable_torque_on_disconnect: bool = True
    allow_fast_replay: bool = Field(False, description="trajectory replay above 100 % (programs §3.2)")
    grip_hold: GripHold = Field(default_factory=GripHold)

    @field_validator("calibration_id")
    @classmethod
    def _cal_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("calibration_id must match [a-z0-9][a-z0-9_-]{0,63}")
        return v


class LeaderProfile(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    type: LeaderType = "so101_leader"
    port: str
    calibration_id: str

    @field_validator("calibration_id")
    @classmethod
    def _cal_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("calibration_id must match [a-z0-9][a-z0-9_-]{0,63}")
        return v


class CameraProfile(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    type: Literal["opencv", "realsense", "mock"] = "opencv"
    index_or_path: int | str | None = None
    serial_number_or_name: str | None = None
    width: int = Field(640, ge=16, le=4096)
    height: int = Field(480, ge=16, le=4096)
    fps: int = Field(30, ge=1, le=120)
    fourcc: str | None = None
    rotation: Literal[0, 90, 180, -90] = 0


class RobotProfile(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    name: str = ""
    follower: FollowerProfile
    leader: LeaderProfile | None = None
    cameras: dict[str, CameraProfile] = Field(default_factory=dict)
    thresholds: Thresholds | None = None
    safety_ack: bool = False

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("id must match [a-z0-9][a-z0-9_-]{0,63}")
        return v

    @field_validator("cameras")
    @classmethod
    def _cams(cls, v: dict[str, CameraProfile]) -> dict[str, CameraProfile]:
        for name in v:
            if not CAMERA_NAME_RE.match(name):
                raise ValueError(f"camera name {name!r} must match [a-z0-9][a-z0-9_]{{0,31}}")
        return v

    @property
    def is_mock(self) -> bool:
        return self.follower.type == "hibiscus_mock_follower"


class RobotsFile(BaseModel):
    version: int = 1
    active: str | None = None
    robots: list[RobotProfile] = Field(default_factory=list)


class ProfileStore:
    """Thread-safe load/save of ``robots.yaml``."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> RobotsFile:
        if not self.path.is_file():
            return RobotsFile()
        raw: Any = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        return RobotsFile.model_validate(raw)

    def _save(self) -> None:
        dumped = self._data.model_dump(mode="json", exclude_none=False)
        write_private(self.path, yaml.safe_dump(dumped, sort_keys=False))

    def list(self) -> list[RobotProfile]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._data.robots]

    @property
    def active(self) -> str | None:
        return self._data.active

    def get(self, robot_id: str) -> RobotProfile | None:
        with self._lock:
            for r in self._data.robots:
                if r.id == robot_id:
                    return r.model_copy(deep=True)
        return None

    def put(self, profile: RobotProfile) -> RobotProfile:
        with self._lock:
            robots = [r for r in self._data.robots if r.id != profile.id]
            robots.append(profile)
            self._data.robots = robots
            if self._data.active is None:
                self._data.active = profile.id
            self._save()
        return profile

    def delete(self, robot_id: str) -> bool:
        with self._lock:
            before = len(self._data.robots)
            self._data.robots = [r for r in self._data.robots if r.id != robot_id]
            if self._data.active == robot_id:
                self._data.active = self._data.robots[0].id if self._data.robots else None
            changed = len(self._data.robots) != before
            if changed:
                self._save()
            return changed

    def set_active(self, robot_id: str) -> None:
        with self._lock:
            self._data.active = robot_id
            self._save()
