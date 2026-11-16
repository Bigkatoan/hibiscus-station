"""Robot profile -> lerobot devices, real or mock (spec §3, §4.1 ``factory.py``).

Followers are built with ``cameras={}`` (cameras belong to CameraHub) and
``max_relative_target=None`` (Station clamps against the observation it already read).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hibiscus_station.profiles import FollowerProfile, LeaderProfile

ROBOTS_DIR = "robots"
TELEOPS_DIR = "teleoperators"
FOLLOWER_NAME = "so_follower"
LEADER_NAME = "so_leader"


def follower_calibration_dir(cal_root: Path) -> Path:
    return cal_root / ROBOTS_DIR / FOLLOWER_NAME


def leader_calibration_dir(cal_root: Path) -> Path:
    return cal_root / TELEOPS_DIR / LEADER_NAME


def build_follower(p: FollowerProfile, cal_root: Path) -> Any:
    cal_dir = follower_calibration_dir(cal_root)
    if p.type == "hibiscus_mock_follower":
        from hibiscus_station.mock.robots import MockFollower, MockFollowerConfig

        return MockFollower(
            MockFollowerConfig(
                port=p.port,
                id=p.calibration_id,
                calibration_dir=cal_dir,
                cameras={},
                max_relative_target=None,
                disable_torque_on_disconnect=p.disable_torque_on_disconnect,
            )
        )
    from lerobot.robots.so_follower import SOFollower, SOFollowerRobotConfig

    robot = SOFollower(
        SOFollowerRobotConfig(
            port=p.port,
            id=p.calibration_id,
            calibration_dir=cal_dir,
            cameras={},
            max_relative_target=None,
            disable_torque_on_disconnect=p.disable_torque_on_disconnect,
            use_degrees=True,
        )
    )
    robot.bus = _station_bus(robot, "follower")
    return robot


def _station_bus(device: Any, arm: str) -> Any:
    """The device's lerobot bus, rebuilt as a :class:`StationMotorsBus` (same motors and calibration)."""
    from hibiscus_station.hw.bus import StationMotorsBus

    old = device.bus
    return StationMotorsBus(old.port, dict(old.motors), device.calibration, arm=arm)


def build_leader(p: LeaderProfile, cal_root: Path) -> Any:
    cal_dir = leader_calibration_dir(cal_root)
    if p.type == "hibiscus_mock_leader":
        from hibiscus_station.mock.robots import MockLeader, MockLeaderConfig

        return MockLeader(MockLeaderConfig(port=p.port, id=p.calibration_id, calibration_dir=cal_dir))
    from lerobot.teleoperators.so_leader import SOLeader, SOLeaderTeleopConfig

    teleop = SOLeader(
        SOLeaderTeleopConfig(port=p.port, id=p.calibration_id, calibration_dir=cal_dir, use_degrees=True)
    )
    teleop.bus = _station_bus(teleop, "leader")
    return teleop


#: lerobot folder names: the current ones first, then the per-model folders of lerobot < 0.4
#: (``so101_follower``...), where an older LeLab or lerobot install left its files.
FOLLOWER_DIRS = (FOLLOWER_NAME, "so101_follower", "so100_follower")
LEADER_DIRS = (LEADER_NAME, "so101_leader", "so100_leader")


def calibration_files(cal_root: Path) -> list[dict[str, Any]]:
    """Calibration json files lerobot (and LeLab) wrote for SO followers and leaders."""
    import datetime as dt

    out: list[dict[str, Any]] = []
    for arm, top, names in (("follower", ROBOTS_DIR, FOLLOWER_DIRS), ("leader", TELEOPS_DIR, LEADER_DIRS)):
        for name in names:
            d = cal_root / top / name
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.json")):
                try:
                    st = f.stat()
                except OSError:  # pragma: no cover
                    continue
                out.append(
                    {
                        "arm": arm,
                        "id": f.stem,
                        "path": str(f),
                        "modified_at": dt.datetime.fromtimestamp(st.st_mtime, dt.UTC).isoformat(),
                        "dir": name,
                    }
                )
    return out
