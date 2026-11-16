"""Record a trajectory with the leader arm (station-programs.md §3.1, state ``recording_traj``).

Phases: ``approach`` (follower eases onto the leader pose, like teleop) → ``countdown`` (teleop runs,
nothing stored) → ``capture`` → ``done``. During ``capture`` every tick stores the follower goal
**after** the SafetyFilter (``after_send``'s ``sent``), so a replay never asks for more than was
actually commanded. The take ends on stop (button, key, ``POST /trajectories/record/stop``), on the
time limit, or on e-stop; whatever was captured is saved as a ``draft`` during ``stopping``.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from hibiscus_station.programs.interfaces import TrajectorySamples
from hibiscus_station.sessions.base import TickInput
from hibiscus_station.sessions.teleop import TeleopSession

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner
    from hibiscus_station.programs.interfaces import TrajectoryStore

log = logging.getLogger(__name__)

KEYFRAME_MAX_W = 320
KEYFRAME_QUALITY = 80
MSG_HZ = 5.0


def default_take_name() -> str:
    return f"Take {dt.datetime.now():%H:%M:%S}"


def shrink(frame: Any, max_w: int = KEYFRAME_MAX_W) -> Any:
    """A ≤ ``max_w`` wide copy of an RGB frame (cheap enough for the control tick at a few Hz)."""
    import cv2

    arr = np.asarray(frame)
    h, w = arr.shape[:2]
    if w <= max_w:
        return arr.copy()
    new_h = max(1, round(h * max_w / w))
    return cv2.resize(arr, (max_w, new_h), interpolation=cv2.INTER_AREA)


def encode_jpeg(rgb: Any, quality: int = KEYFRAME_QUALITY) -> bytes:
    import cv2

    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:  # pragma: no cover - only on a corrupt frame
        raise ValueError("jpeg encode failed")
    return bytes(buf.tobytes())


@dataclass
class TrajRecordSession(TeleopSession):
    store: TrajectoryStore | None = None
    name: str = ""
    limit_s: float = 60.0
    countdown_s: float = 3.0
    keyframe_hz: float = 1.0
    trajectory_id: str | None = None
    names: list[str] = field(default_factory=list)
    t: list[float] = field(default_factory=list)
    rows: list[list[float]] = field(default_factory=list)
    keyframes: dict[str, list[Any]] = field(default_factory=dict)
    keyframe_times: list[float] = field(default_factory=list)
    _phase_t0: float = 0.0
    _next_keyframe: float = 0.0
    _last_msg: float = -1.0
    _msg_phase: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.deadman = False  # a human holds the leader (station.md §4.7)
        self.name = self.name or default_take_name()
        self.episode.of = 1
        self.episode.limit_s = self.limit_s

    # ---- owner thread
    def _enter(self, phase: str, now: float) -> None:
        self._phase_t0 = now
        self.set_phase(phase)
        self.episode.elapsed_s = 0.0
        self.episode.limit_s = self.countdown_s if phase == "countdown" else self.limit_s

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        if self.episode.phase == "approach":
            target = self.approach(inp)
            if self.approach_done(inp):
                self._enter("countdown", inp.t)
            return target
        return dict(inp.leader) if inp.leader is not None else None

    def after_send(
        self, owner: HardwareOwner, inp: TickInput, action: dict[str, float], sent: dict[str, float]
    ) -> None:
        if self.episode.phase != "capture":
            return
        t = inp.t - self._phase_t0
        if self.t and t <= self.t[-1]:
            return
        if not self.names:
            self.names = [k for k in sent if k.endswith(".pos")]
        if any(n not in sent for n in self.names):
            return
        self.t.append(t)
        self.rows.append([float(sent[n]) for n in self.names])
        if self.keyframe_hz > 0 and t >= self._next_keyframe and inp.frames:
            for cam, frame in inp.frames.items():
                if cam in inp.stale:
                    continue
                self.keyframes.setdefault(cam, []).append(shrink(frame))
            self.keyframe_times.append(t)
            # a camera that was stale this tick still needs an entry for every keyframe time
            for cam in inp.frames:
                frames = self.keyframes.setdefault(cam, [])
                while len(frames) < len(self.keyframe_times):
                    frames.append(None)
            self._next_keyframe = t + 1.0 / self.keyframe_hz

    def poll(self, owner: HardwareOwner, now: float) -> None:
        phase = self.episode.phase
        dt_s = now - self._phase_t0
        if phase == "countdown":
            self.episode.elapsed_s = dt_s
            if dt_s >= self.countdown_s:
                self._enter("capture", now)
        elif phase == "capture":
            self.episode.elapsed_s = dt_s
            if dt_s >= self.limit_s:
                self.finish("completed")  # time limit: the take is saved like a stop
        self._progress(owner, now)

    def _progress(self, owner: HardwareOwner, now: float) -> None:
        phase = self.episode.phase
        if phase not in ("countdown", "capture"):
            return
        if phase != self._msg_phase or now - self._last_msg >= 1.0 / MSG_HZ:
            self._msg_phase = phase
            self._last_msg = now
            owner.emit("trajectory_record", self.message(phase))

    def message(self, phase: str, *, ended: bool = False) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "phase": phase,
            "elapsed_s": round(
                self.episode.elapsed_s if phase != "done" else (self.t[-1] if self.t else 0.0), 3
            ),
            "limit_s": self.limit_s,
            "samples": len(self.t),
            "trajectory_id": self.trajectory_id,
            "ended": ended,
        }

    def end(self, owner: HardwareOwner, reason: str) -> None:
        """``stopping``: write the take as a draft (any end reason; an e-stopped take is still a
        useful draft, and every stored goal already passed the SafetyFilter)."""
        owner.emit("trajectory_record", self.message("saving"))
        self.summary.update({"samples": len(self.t), "trajectory": None})
        if len(self.t) >= 2 and self.store is not None:
            try:
                kf: dict[str, list[bytes]] = {}
                times: list[float] = []
                keep = [
                    i
                    for i in range(len(self.keyframe_times))
                    if all(self.keyframes[c][i] is not None for c in self.keyframes)
                ]
                for cam, frames in self.keyframes.items():
                    kf[cam] = [encode_jpeg(frames[i]) for i in keep]
                times = [self.keyframe_times[i] for i in keep]
                tr = self.store.create_draft(
                    name=self.name,
                    fps=self.fps,
                    samples=TrajectorySamples(fps=self.fps, names=self.names, t=self.t, rows=self.rows),
                    keyframes=kf,
                    keyframe_times=times,
                )
                self.trajectory_id = tr.id
                self.summary["trajectory"] = tr.id
            except Exception as exc:
                log.exception("saving the take failed")
                self.summary["save_error"] = str(exc)[:300]
        self.keyframes.clear()
        self.set_phase("done")
        owner.emit("trajectory_record", self.message("done", ended=True))

    def controls(self) -> dict[str, bool]:
        return {"next": False, "rerecord": False, "stop": True}

    def view(self) -> dict[str, Any]:
        v = super().view()
        v["trajectory"] = self.trajectory_id
        return v
