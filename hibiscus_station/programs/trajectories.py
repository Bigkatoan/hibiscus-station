"""Trajectory storage (station-programs.md §2, §3, implementation map §2).

One take per directory ``robots/<robot>/trajectories/<id>/``:

* ``trajectory.json``: the :class:`~hibiscus_station.programs.schemas.Trajectory` document;
* ``samples.parquet``: ``t`` (float64 s from the first sample) + one float64 column per joint, the
  **untrimmed** take (the trim is metadata, so it can be changed back);
* ``keyframes/<camera>/<index:04d>.jpg``: small camera stills of the take (≤ 320 px wide).

The stored ``status`` is ``draft`` or ``ready``. ``needs_check`` is computed on every read: the stored
``calibration_hash`` no longer matches the follower calibration. A ``check`` replay at low speed
(:meth:`TrajectoryStore.note_check_replay`) then :meth:`TrajectoryStore.confirm` clears it.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
import secrets
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
import numpy.typing as npt

from hibiscus_station.errors import StationError
from hibiscus_station.programs.interfaces import TrajectorySamples
from hibiscus_station.programs.paths import RobotDataPaths
from hibiscus_station.programs.schemas import (
    TRAJECTORY_ID_RE,
    Trajectory,
    TrajectoryDetail,
    TrajectorySeries,
    TrajectorySummary,
    TrajectoryUpdate,
    TrimRange,
)
from hibiscus_station.settings import write_private

PREVIEW_POINTS = 64
SERIES_MAX_POINTS = 600
EPS = 1e-6
GRIPPER = "gripper.pos"

Array = npt.NDArray[np.float64]
TrimRule = Callable[[], tuple[float, float]]  # (idle_deg, idle_s), read at use (settings may change)


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def new_trajectory_id() -> str:
    now = dt.datetime.now(dt.UTC)
    return f"t_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


# =========================================================================== pure helpers
def check_samples(samples: TrajectorySamples) -> None:
    """A take the store accepts: ≥ 2 rows, one value per joint, strictly increasing finite times."""
    n = len(samples.t)
    if n < 2:
        raise StationError(
            "validation_failed", "a trajectory needs at least 2 samples", params={"samples": n}
        )
    if len(samples.rows) != n:
        raise StationError("validation_failed", "rows and times differ in length")
    if not samples.names or len(set(samples.names)) != len(samples.names):
        raise StationError("validation_failed", "joint names must be unique and non-empty")
    width = len(samples.names)
    for row in samples.rows:
        if len(row) != width or not all(math.isfinite(v) for v in row):
            raise StationError("validation_failed", "every row needs one finite value per joint")
    t = samples.t
    if not all(math.isfinite(x) for x in t) or any(b <= a for a, b in itertools.pairwise(t)):
        raise StationError("validation_failed", "sample times must be finite and strictly increasing")


def suggest_trim(samples: TrajectorySamples, idle_deg: float, idle_s: float) -> TrimRange:
    """Idle start/end of a take: the leading (trailing) run of samples where every joint stays within
    ``idle_deg`` of the first (last) sample, when that run lasts longer than ``idle_s``."""
    t = np.asarray(samples.t, dtype=np.float64)
    rows = np.asarray(samples.rows, dtype=np.float64)
    n = len(t)
    if n < 2:
        return TrimRange(start_s=0.0, end_s=0.0)
    still_start = np.all(np.abs(rows - rows[0]) <= idle_deg + EPS, axis=1)
    moving = np.flatnonzero(~still_start)
    if len(moving) == 0:  # the whole take is idle: nothing sensible to cut
        return TrimRange(start_s=0.0, end_s=0.0)
    first_move = int(moving[0])
    i_start = first_move - 1  # last idle sample: the motion starts from there
    start = float(t[i_start] - t[0]) if t[i_start] - t[0] > idle_s else 0.0
    still_end = np.all(np.abs(rows - rows[-1]) <= idle_deg + EPS, axis=1)
    last_move = int(np.flatnonzero(~still_end)[-1])
    i_end = last_move + 1  # first idle sample at the end: the motion has stopped there
    end = float(t[-1] - t[i_end]) if t[-1] - t[i_end] > idle_s else 0.0
    if t[-1] - t[0] - start - end < EPS:  # pragma: no cover - moving samples sit between the runs
        return TrimRange(start_s=0.0, end_s=0.0)
    return TrimRange(start_s=round(start, 6), end_s=round(end, 6))


def kept_slice(t: list[float] | Array, trim: TrimRange) -> slice:
    """Indices of the samples kept by ``trim`` (raw time axis, first sample at ``t[0]``)."""
    ta = np.asarray(t, dtype=np.float64)
    t0, t1 = float(ta[0]), float(ta[-1])
    lo = int(np.searchsorted(ta, t0 + trim.start_s - EPS, side="left"))
    hi = int(np.searchsorted(ta, t1 - trim.end_s + EPS, side="right"))
    return slice(lo, hi)


def apply_trim(samples: TrajectorySamples, trim: TrimRange) -> TrajectorySamples:
    sl = kept_slice(samples.t, trim)
    t = samples.t[sl]
    if len(t) < 2:
        raise StationError(
            "validation_failed",
            "the trim leaves fewer than 2 samples",
            params={"start_s": trim.start_s, "end_s": trim.end_s},
        )
    base = t[0]
    return TrajectorySamples(
        fps=samples.fps,
        names=list(samples.names),
        t=[round(x - base, 9) for x in t],
        rows=[list(r) for r in samples.rows[sl]],
    )


def max_joint_speed(samples: TrajectorySamples) -> float:
    """Peak joint speed in °/s (the gripper uses 0-100 units and is left out)."""
    cols = [i for i, n in enumerate(samples.names) if n != GRIPPER]
    if len(samples.t) < 2 or not cols:
        return 0.0
    rows = np.asarray(samples.rows, dtype=np.float64)[:, cols]
    dts = np.diff(np.asarray(samples.t, dtype=np.float64))
    speed = np.abs(np.diff(rows, axis=0)) / dts[:, None]
    return round(float(speed.max()), 3)


def preview(samples: TrajectorySamples, points: int = PREVIEW_POINTS) -> dict[str, list[float]]:
    """``points`` evenly spaced (in time) positions per joint, for the list thumbnail."""
    t = np.asarray(samples.t, dtype=np.float64)
    rows = np.asarray(samples.rows, dtype=np.float64)
    grid = np.linspace(t[0], t[-1], points)
    return {
        name: [round(float(v), 3) for v in np.interp(grid, t, rows[:, j])]
        for j, name in enumerate(samples.names)
    }


def series(samples: TrajectorySamples, max_points: int = SERIES_MAX_POINTS) -> TrajectorySeries:
    """The raw take decimated to at most ``max_points`` (the last sample always kept)."""
    n = len(samples.t)
    stride = max(1, math.ceil(n / max_points))
    idx = list(range(0, n, stride))
    if idx[-1] != n - 1:
        if len(idx) >= max_points:
            idx[-1] = n - 1
        else:
            idx.append(n - 1)
    return TrajectorySeries(
        t=[round(samples.t[i], 4) for i in idx],
        joints={name: [round(samples.rows[i][j], 3) for i in idx] for j, name in enumerate(samples.names)},
    )


def write_parquet(path: Path, samples: TrajectorySamples) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = np.asarray(samples.rows, dtype=np.float64)
    cols: dict[str, Array] = {"t": np.asarray(samples.t, dtype=np.float64)}
    for j, name in enumerate(samples.names):
        cols[name] = rows[:, j]
    table = pa.table(cols)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}")
    try:
        pq.write_table(table, tmp)
        tmp.chmod(0o600)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_parquet(path: Path, fps: int) -> TrajectorySamples:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    names = [c for c in table.column_names if c != "t"]
    t = [float(x) for x in table.column("t").to_pylist()]
    cols = [table.column(n).to_pylist() for n in names]
    rows = [[float(c[i]) for c in cols] for i in range(len(t))]
    return TrajectorySamples(fps=fps, names=names, t=t, rows=rows)


# =========================================================================== store
class TrajectoryStore:
    """Trajectories of one robot profile (``programs.interfaces.TrajectoryStore``); thread-safe."""

    def __init__(
        self,
        paths: RobotDataPaths,
        calibration_hash: Callable[[], str],
        *,
        trim_rule: TrimRule | None = None,
    ) -> None:
        self.paths = paths
        self.calibration_hash = calibration_hash
        self.trim_rule: TrimRule = trim_rule or (lambda: (0.5, 0.5))
        self._lock = threading.RLock()
        self._checked: dict[str, str] = {}  # trajectory id -> calibration hash of a completed check replay

    # ------------------------------------------------------------------ reading
    def _dir(self, trajectory_id: str) -> Path:
        d = self.paths.trajectory_dir(trajectory_id)
        if not (d / "trajectory.json").is_file():
            raise StationError(
                "not_found", f"no trajectory {trajectory_id}", params={"trajectory": trajectory_id}
            )
        return d

    def _load(self, trajectory_id: str) -> Trajectory:
        d = self._dir(trajectory_id)
        return Trajectory.model_validate_json((d / "trajectory.json").read_text(encoding="utf-8"))

    def _effective(self, tr: Trajectory, current: str | None = None) -> Trajectory:
        cur = current if current is not None else self.calibration_hash()
        if tr.calibration_hash != cur:
            return tr.model_copy(update={"status": "needs_check"})
        return tr

    def _raw(self, tr: Trajectory) -> TrajectorySamples:
        return read_parquet(self.paths.trajectory_samples(tr.id), tr.fps)

    def all(self) -> list[TrajectorySummary]:
        with self._lock:
            root = self.paths.trajectories
            if not root.is_dir():
                return []
            cur = self.calibration_hash()
            out: list[TrajectorySummary] = []
            for d in sorted(root.iterdir()):
                if not TRAJECTORY_ID_RE.fullmatch(d.name) or not (d / "trajectory.json").is_file():
                    continue
                try:
                    tr = self._effective(self._load(d.name), cur)
                    trimmed = apply_trim(self._raw(tr), tr.trim)
                except (StationError, ValueError, OSError):
                    continue  # a broken take must not hide the others
                out.append(TrajectorySummary(**tr.model_dump(), preview=preview(trimmed)))
            out.sort(key=lambda s: s.created_at, reverse=True)
            return out

    def get(self, trajectory_id: str) -> Trajectory:
        with self._lock:
            return self._effective(self._load(trajectory_id))

    def detail(self, trajectory_id: str) -> TrajectoryDetail:
        with self._lock:
            tr = self.get(trajectory_id)
            return TrajectoryDetail(**tr.model_dump(), series=series(self._raw(tr)))

    def samples(self, trajectory_id: str, *, trimmed: bool = True) -> TrajectorySamples:
        with self._lock:
            tr = self._load(trajectory_id)
            raw = self._raw(tr)
            return apply_trim(raw, tr.trim) if trimmed else raw

    def keyframe(self, trajectory_id: str, camera: str, index: int) -> bytes:
        with self._lock:
            self._dir(trajectory_id)
            f = self.paths.keyframe(trajectory_id, camera, index)
            if not f.is_file():
                raise StationError("not_found", "no such keyframe", params={"camera": camera, "index": index})
            return f.read_bytes()

    # ------------------------------------------------------------------ writing
    def _derived(self, tr: Trajectory, raw: TrajectorySamples) -> Trajectory:
        """Fill the fields computed from the samples and the trim."""
        kept = apply_trim(raw, tr.trim)
        start = dict(zip(kept.names, kept.rows[0], strict=True))
        end = dict(zip(kept.names, kept.rows[-1], strict=True))
        return tr.model_copy(
            update={
                "joints": list(raw.names),
                "samples": len(raw.t),
                "raw_duration_s": round(raw.t[-1] - raw.t[0], 6),
                "duration_s": round(kept.t[-1], 6),
                "start_pose": {k: round(v, 4) for k, v in start.items()},
                "end_pose": {k: round(v, 4) for k, v in end.items()},
                "max_speed_deg_s": max_joint_speed(kept),
            }
        )

    def _write(self, tr: Trajectory) -> None:
        stored = tr if tr.status != "needs_check" else tr.model_copy(update={"status": "ready"})
        write_private(self.paths.trajectory_json(tr.id), stored.model_dump_json(indent=2))

    def create_draft(
        self,
        *,
        name: str,
        fps: int,
        samples: TrajectorySamples,
        keyframes: dict[str, list[bytes]],
        keyframe_times: list[float],
    ) -> Trajectory:
        check_samples(samples)
        for cam, frames in keyframes.items():
            if len(frames) != len(keyframe_times):
                raise StationError(
                    "validation_failed", "one keyframe time per keyframe", params={"camera": cam}
                )
        base = samples.t[0]
        raw = TrajectorySamples(
            fps=fps,
            names=list(samples.names),
            t=[round(x - base, 9) for x in samples.t],
            rows=[list(r) for r in samples.rows],
        )
        idle_deg, idle_s = self.trim_rule()
        trim = suggest_trim(raw, idle_deg, idle_s)
        with self._lock:
            self.paths.ensure()
            tid = new_trajectory_id()
            while self.paths.trajectory_dir(tid).exists():  # pragma: no cover - same second, same hex
                tid = new_trajectory_id()
            d = self.paths.trajectory_dir(tid)
            d.mkdir(mode=0o700)
            stamp = now_iso()
            tr = Trajectory(
                id=tid,
                name=name,
                robot=self.paths.robot_id,
                created_at=stamp,
                updated_at=stamp,
                fps=fps,
                joints=list(raw.names),
                samples=len(raw.t),
                raw_duration_s=0.0,
                trim=trim,
                suggested_trim=trim,
                duration_s=0.0,
                start_pose={},
                end_pose={},
                max_speed_deg_s=0.0,
                calibration_hash=self.calibration_hash(),
                status="draft",
                checked_at=None,
                keyframe_cameras=sorted(c for c, f in keyframes.items() if f),
                keyframe_times=[round(x - base, 4) for x in keyframe_times],
            )
            tr = self._derived(tr, raw)
            try:
                write_parquet(self.paths.trajectory_samples(tid), raw)
                for cam, frames in keyframes.items():
                    for i, jpg in enumerate(frames):
                        f = self.paths.keyframe(tid, cam, i)
                        f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        write_private(f, jpg)
                self._write(tr)
            except BaseException:
                shutil.rmtree(d, ignore_errors=True)
                raise
            return self._effective(tr)

    def update(self, trajectory_id: str, upd: TrajectoryUpdate) -> Trajectory:
        with self._lock:
            tr = self._load(trajectory_id)
            changes: dict[str, object] = {"updated_at": now_iso()}
            if upd.name is not None:
                changes["name"] = upd.name
            if upd.trim is not None:
                if upd.trim.start_s + upd.trim.end_s >= tr.raw_duration_s - EPS:
                    raise StationError(
                        "validation_failed",
                        "the trim cuts the whole take",
                        params={"raw_duration_s": tr.raw_duration_s},
                    )
                changes["trim"] = upd.trim
            if upd.save:
                changes["status"] = "ready"
            new = tr.model_copy(update=changes)
            if upd.trim is not None:
                new = self._derived(new, self._raw(new))
            self._write(new)
            return self._effective(new)

    def delete(self, trajectory_id: str) -> None:
        with self._lock:
            d = self._dir(trajectory_id)
            shutil.rmtree(d)
            self._checked.pop(trajectory_id, None)

    def note_check_replay(self, trajectory_id: str) -> None:
        """A ``check`` replay of this take completed under the current calibration."""
        with self._lock:
            self._checked[trajectory_id] = self.calibration_hash()

    def confirm(self, trajectory_id: str) -> Trajectory:
        """``POST /trajectories/{id}/confirm``: needs_check → ready after a completed check replay."""
        with self._lock:
            tr = self.get(trajectory_id)
            if tr.status != "needs_check":
                return tr
            if self._checked.get(trajectory_id) != self.calibration_hash():
                raise StationError(
                    "needs_check",
                    "replay this trajectory once with check=true before confirming it",
                    params={"trajectory": trajectory_id},
                )
            return self.mark_checked(trajectory_id)

    def mark_checked(self, trajectory_id: str) -> Trajectory:
        with self._lock:
            tr = self._load(trajectory_id)
            stamp = now_iso()
            new = tr.model_copy(
                update={
                    "calibration_hash": self.calibration_hash(),
                    "checked_at": stamp,
                    "updated_at": stamp,
                    "status": "ready",
                }
            )
            self._write(new)
            self._checked.pop(trajectory_id, None)
            return self._effective(new)
