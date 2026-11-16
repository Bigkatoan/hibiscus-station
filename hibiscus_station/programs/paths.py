"""On-disk layout of the feature (station-programs.md "Implementation map" §2).

```
~/.hibiscus/station/
├── robots/<robot_id>/                      # everything depends on that profile's calibration
│   ├── trajectories/<trajectory_id>/
│   │   ├── trajectory.json                 # Trajectory
│   │   ├── samples.parquet                 # t, <joint>.pos ... (float64), untrimmed
│   │   └── keyframes/<camera>/<index:04d>.jpg
│   ├── poses.json                          # Poses
│   ├── detectors/<detector_id>.json        # Detector
│   ├── detectors/<detector_id>.onnx        # classifier model
│   └── programs/<program_id>/program.json  # Program (editor JSON + AST)
└── runs/programs/<run_id>.jsonl            # ProgramLogLine per line (first: kind=start)
```
Same rules as the rest of Station: dirs 0700, files 0600, atomic writes (``write_private``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from hibiscus_station.errors import StationError
from hibiscus_station.programs.schemas import ITEM_ID_RE, RUN_ID_RE, TRAJECTORY_ID_RE


def _check(value: str, pattern: re.Pattern[str], what: str) -> str:
    if not pattern.fullmatch(value):
        raise StationError("validation_failed", f"bad {what} id", params={what: value})
    return value


@dataclass(frozen=True)
class RobotDataPaths:
    home: Path
    robot_id: str

    def __post_init__(self) -> None:
        _check(self.robot_id, ITEM_ID_RE, "robot")

    @property
    def root(self) -> Path:
        return self.home / "robots" / self.robot_id

    @property
    def trajectories(self) -> Path:
        return self.root / "trajectories"

    def trajectory_dir(self, trajectory_id: str) -> Path:
        return self.trajectories / _check(trajectory_id, TRAJECTORY_ID_RE, "trajectory")

    def trajectory_json(self, trajectory_id: str) -> Path:
        return self.trajectory_dir(trajectory_id) / "trajectory.json"

    def trajectory_samples(self, trajectory_id: str) -> Path:
        return self.trajectory_dir(trajectory_id) / "samples.parquet"

    def keyframe(self, trajectory_id: str, camera: str, index: int) -> Path:
        if "/" in camera or camera.startswith(".") or index < 0:
            raise StationError("validation_failed", "bad keyframe", params={"camera": camera, "index": index})
        return self.trajectory_dir(trajectory_id) / "keyframes" / camera / f"{index:04d}.jpg"

    @property
    def poses(self) -> Path:
        return self.root / "poses.json"

    @property
    def detectors(self) -> Path:
        return self.root / "detectors"

    def detector_json(self, detector_id: str) -> Path:
        return self.detectors / f"{_check(detector_id, ITEM_ID_RE, 'detector')}.json"

    def detector_model(self, detector_id: str) -> Path:
        return self.detectors / f"{_check(detector_id, ITEM_ID_RE, 'detector')}.onnx"

    @property
    def programs(self) -> Path:
        return self.root / "programs"

    def program_json(self, program_id: str) -> Path:
        return self.programs / _check(program_id, ITEM_ID_RE, "program") / "program.json"

    def ensure(self) -> None:
        for d in (self.root, self.trajectories, self.detectors, self.programs):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)


def program_runs_dir(home: Path) -> Path:
    return home / "runs" / "programs"


def program_run_log(home: Path, run_id: str) -> Path:
    return program_runs_dir(home) / f"{_check(run_id, RUN_ID_RE, 'run')}.jsonl"
