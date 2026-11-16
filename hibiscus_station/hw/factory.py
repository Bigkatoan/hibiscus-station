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

    return SOFollower(
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


def build_leader(p: LeaderProfile, cal_root: Path) -> Any:
    cal_dir = leader_calibration_dir(cal_root)
    if p.type == "hibiscus_mock_leader":
        from hibiscus_station.mock.robots import MockLeader, MockLeaderConfig

        return MockLeader(MockLeaderConfig(port=p.port, id=p.calibration_id, calibration_dir=cal_dir))
    from lerobot.teleoperators.so_leader import SOLeader, SOLeaderTeleopConfig

    return SOLeader(
        SOLeaderTeleopConfig(port=p.port, id=p.calibration_id, calibration_dir=cal_dir, use_degrees=True)
    )


def calibration_files(cal_root: Path) -> list[dict[str, Any]]:
    """Calibration json files lerobot (and LeLab) wrote for SO followers and leaders."""
    import datetime as dt

    out: list[dict[str, Any]] = []
    for arm, d in (
        ("follower", follower_calibration_dir(cal_root)),
        ("leader", leader_calibration_dir(cal_root)),
    ):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            st = f.stat()
            out.append(
                {
                    "arm": arm,
                    "id": f.stem,
                    "path": str(f),
                    "modified_at": dt.datetime.fromtimestamp(st.st_mtime, dt.UTC).isoformat(),
                }
            )
    return out
