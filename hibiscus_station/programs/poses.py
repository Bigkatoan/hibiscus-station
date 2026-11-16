"""Named poses of one robot profile: ``robots/<robot>/poses.json`` (station-programs.md §2).

A pose is one joint configuration (``"shoulder_pan.pos"`` → degrees, gripper 0-100). It keeps the
calibration hash it was saved with; ``needs_check`` is computed on read like trajectories.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable

from hibiscus_station.errors import StationError
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.schemas import ITEM_ID_RE, Pose, PoseInput, Poses
from hibiscus_station.programs.trajectories import now_iso
from hibiscus_station.settings import write_private

MAX_POSES = 200


def check_positions(positions: dict[str, float], what: str = "pose") -> dict[str, float]:
    if not positions:
        raise StationError("validation_failed", f"{what} has no joints")
    for k, v in positions.items():
        if not k.endswith(".pos") or not math.isfinite(v):
            raise StationError(
                "validation_failed",
                f'{what}: joints are "<motor>.pos" with finite values',
                params={"joint": k},
            )
    return {k: float(v) for k, v in positions.items()}


class PoseStore:
    """``programs.interfaces.PoseStore``; thread-safe."""

    def __init__(self, paths: RobotDataPaths, calibration_hash: Callable[[], str]) -> None:
        self.paths = paths
        self.calibration_hash = calibration_hash
        self._lock = threading.RLock()

    def _read(self) -> list[Pose]:
        f = self.paths.poses
        if not f.is_file():
            return []
        return Poses.model_validate_json(f.read_text(encoding="utf-8")).poses

    def _save(self, poses: list[Pose]) -> None:
        stored = [p.model_copy(update={"needs_check": False}) for p in poses]
        self.paths.root.mkdir(parents=True, exist_ok=True)
        write_private(self.paths.poses, Poses(poses=stored).model_dump_json(indent=2))

    def _effective(self, poses: list[Pose]) -> list[Pose]:
        cur = self.calibration_hash()
        return [p.model_copy(update={"needs_check": p.calibration_hash != cur}) for p in poses]

    def all(self) -> list[Pose]:
        with self._lock:
            return self._effective(self._read())

    def get(self, name: str) -> Pose:
        with self._lock:
            for p in self.all():
                if p.name == name:
                    return p
        raise StationError("not_found", f"no pose {name}", params={"pose": name})

    def replace(self, poses: list[PoseInput]) -> list[Pose]:
        names = [p.name for p in poses]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            raise StationError("validation_failed", "pose names must be unique", params={"names": dup})
        if len(poses) > MAX_POSES:
            raise StationError("validation_failed", f"at most {MAX_POSES} poses")
        with self._lock:
            old = {p.name: p for p in self._read()}
            cur = self.calibration_hash()
            stamp = now_iso()
            out: list[Pose] = []
            for p in poses:
                positions = check_positions(p.positions, p.name)
                prev = old.get(p.name)
                if prev is not None and prev.positions == positions:
                    # unchanged: keep when (and with which calibration) it was taken
                    out.append(prev.model_copy(update={"source": p.source, "trajectory": p.trajectory}))
                    continue
                out.append(
                    Pose(
                        name=p.name,
                        positions=positions,
                        source=p.source,
                        trajectory=p.trajectory,
                        calibration_hash=cur,
                        created_at=stamp,
                        needs_check=False,
                    )
                )
            self._save(out)
            return self._effective(out)

    def capture(self, name: str, positions: dict[str, float]) -> Pose:
        if not ITEM_ID_RE.fullmatch(name):
            raise StationError("validation_failed", "bad pose name", params={"pose": name})
        pos = check_positions(positions, name)
        with self._lock:
            poses = [p for p in self._read() if p.name != name]
            if len(poses) >= MAX_POSES:
                raise StationError("validation_failed", f"at most {MAX_POSES} poses")
            pose = Pose(
                name=name,
                positions={k: round(v, 3) for k, v in pos.items()},
                source="live",
                trajectory=None,
                calibration_hash=self.calibration_hash(),
                created_at=now_iso(),
                needs_check=False,
            )
            poses.append(pose)
            self._save(poses)
            return pose
