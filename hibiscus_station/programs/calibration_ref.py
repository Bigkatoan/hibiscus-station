"""Which calibration a trajectory or a pose was made with (station-programs.md §6).

The hash is the sha256 (first 16 hex digits) of the follower calibration file bytes, the same file
lerobot reads at connect. A recalibration rewrites the file, so every take and pose recorded before it
reads as ``needs_check`` until it is replayed once at low speed and confirmed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from hibiscus_station.hw.factory import follower_calibration_dir
from hibiscus_station.profiles import RobotProfile

NO_CALIBRATION = "none"


def calibration_file(cal_root: Path, profile: RobotProfile) -> Path:
    return follower_calibration_dir(cal_root) / f"{profile.follower.calibration_id}.json"


def calibration_hash(cal_root: Path, profile: RobotProfile) -> str:
    """sha256[:16] of the follower calibration file; ``"none"`` when there is no file yet."""
    f = calibration_file(cal_root, profile)
    try:
        data = f.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return NO_CALIBRATION
    return hashlib.sha256(data).hexdigest()[:16]
