"""Replay session: a recorded episode's actions drive the follower (spec L15).

Interruptible within one tick, at the dataset's fps, through the same safety filter, telemetry and
cameras as every other session. A smooth approach to the first action comes first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.sessions.base import MotionSession, TickInput
from hibiscus_station.sessions.teleop import blend

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner


def load_episode_actions(root: Path, episode: int) -> tuple[int, list[dict[str, float]]]:
    """(fps, actions) of one episode, read straight from the dataset parquet files."""
    import pyarrow.parquet as pq

    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        raise StationError("not_found", f"no dataset at {root}")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    names = list(info["features"]["action"]["names"])
    from hibiscus.recording import parquet_closed

    rows: list[tuple[int, list[float]]] = []
    being_written = False
    for f in sorted((root / "data").rglob("*.parquet")):
        if not parquet_closed(f):  # lerobot's writer is still open (dataset not finalized)
            being_written = True
            continue
        table = pq.read_table(f, columns=["episode_index", "frame_index", "action"])
        eps = table.column("episode_index").to_pylist()
        fis = table.column("frame_index").to_pylist()
        acts = table.column("action").to_pylist()
        for e, fi, a in zip(eps, fis, acts, strict=True):
            if int(e) == episode:
                rows.append((int(fi), [float(x) for x in a]))
    if not rows and being_written:
        raise StationError(
            "busy",
            "this episode is still being saved; try again when the dataset is finalized",
            params={"dataset": root.name, "state": "saving"},
        )
    if not rows:
        raise StationError("not_found", f"episode {episode} not found", params={"episode": episode})
    rows.sort(key=lambda r: r[0])
    return int(info["fps"]), [dict(zip(names, a, strict=True)) for _, a in rows]


@dataclass
class ReplaySession(MotionSession):
    actions: list[dict[str, float]] = field(default_factory=list)
    episode_index: int = 0
    approach_s: float = 1.5
    _start_pose: dict[str, float] = field(default_factory=dict)
    _cursor: int = 0
    _approach_t0: float | None = None

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self._start_pose = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        self.episode.index = self.episode_index
        self.episode.of = 1
        self.episode.limit_s = len(self.actions) / self.fps
        self.set_phase("approach" if self.approach_s > 0 else "replay")

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        if not self.actions:
            self.finish("completed")
            return None
        if self.episode.phase == "approach":
            if self._approach_t0 is None:
                self._approach_t0 = inp.t
            alpha = (inp.t - self._approach_t0) / self.approach_s
            if alpha >= 1.0:
                self.set_phase("replay")
            return blend(self._start_pose, self.actions[0], alpha)
        if self._cursor >= len(self.actions):
            self.finish("completed")
            return None
        a = self.actions[self._cursor]
        self._cursor += 1
        self.episode.elapsed_s = self._cursor / self.fps
        return dict(a)

    @property
    def cursor(self) -> int:
        return self._cursor
