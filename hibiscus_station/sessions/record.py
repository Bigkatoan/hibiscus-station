"""Record session (spec §6.6, L12): countdown -> episode -> reset -> saving -> episode ... .

Same controls as lerobot (next / rerecord / stop). Differences from LeLab, on purpose:
an episode that reaches its time limit is **saved** by default (``on_timeout: save``), and
``dataset.finalize()`` always runs. The recorded ``action`` is the teleop action (lerobot semantics),
not the clipped command.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.sessions.base import MotionSession, TickInput
from hibiscus_station.sessions.recorder import DatasetRecorder
from hibiscus_station.sessions.teleop import blend

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner

log = logging.getLogger(__name__)


@dataclass
class RecordSession(MotionSession):
    recorder: DatasetRecorder | None = None
    num_episodes: int = 1
    episode_time_s: float = 30.0
    reset_time_s: float = 10.0
    countdown_s: float = 3.0
    on_timeout: str = "save"
    approach_s: float = 1.5
    pending: bool = False  # a completed episode is buffered, not saved yet
    paused: bool = False
    _phase_t0: float = 0.0
    _start_pose: dict[str, float] = field(default_factory=dict)
    _after_saving: str = "episode"
    discarded: int = 0
    timeouts: int = 0
    #: The operator pressed Stop: the episode being recorded (or buffered) is saved *inside* the
    #: session (phase ``saving``, the loop keeps running: cameras, telemetry, e-stop), then the
    #: session ends as ``stopped``. Field report 0.2.9: saving in the teardown froze the loop.
    stop_requested: bool = False

    def __post_init__(self) -> None:
        self.uses_leader = True
        self.episode.of = self.num_episodes
        self.episode.limit_s = self.episode_time_s

    @property
    def rec(self) -> DatasetRecorder:
        if self.recorder is None:
            raise StationError("internal_error", "record session without a dataset")
        return self.recorder

    # ------------------------------------------------------------------ phases
    def _enter(self, phase: str, now: float) -> None:
        self._phase_t0 = now
        self.set_phase(phase)
        self.recording_active = phase == "episode"
        if phase == "episode":
            self.episode.elapsed_s = 0.0
            self.episode.limit_s = self.episode_time_s
        elif phase == "reset":
            self.episode.elapsed_s = 0.0
            self.episode.limit_s = self.reset_time_s
        elif phase == "countdown":
            self.episode.limit_s = self.countdown_s

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self._start_pose = {k: float(v) for k, v in obs.items() if k.endswith(".pos")}
        self.episode.saved = 0
        self.episode.index = self.rec.next_episode_index
        self._enter("countdown", 0.0)

    def _end_episode(self, keep: bool, now: float) -> None:
        if keep and self.rec.frames_in_episode > 0:
            self.pending = True
        else:
            self.rec.discard()
            self.discarded += 1
            self.pending = False
        last = self.episode.saved + (1 if self.pending else 0) >= self.num_episodes
        if last:
            if self.pending:
                self._start_saving(now, after="done")
            else:
                self.finish("completed")
        else:
            self._enter("reset", now)

    def _start_saving(self, now: float, after: str) -> None:
        self.rec.save_async()
        self.pending = False
        self._after_saving = after
        self._enter("saving", now)

    def _end_reset(self, now: float) -> None:
        if self.pending:
            self._start_saving(now, after="episode")
        else:
            self._enter("episode", now)

    # ------------------------------------------------------------------ tick
    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        phase = self.episode.phase
        if phase == "saving" or inp.leader is None:
            return None  # hold: no new goals while encoding
        if phase == "countdown" and inp.t < self.approach_s:
            return blend(self._start_pose, inp.leader, inp.t / self.approach_s if self.approach_s else 1.0)
        return dict(inp.leader)

    def after_send(
        self, owner: HardwareOwner, inp: TickInput, action: dict[str, float], sent: dict[str, float]
    ) -> None:
        if self.episode.phase != "episode" or self.paused or inp.stale:
            self.paused = False
            return  # a stale camera pauses the episode clock: no frame with a missing image
        self.frame_index = self.rec.frames_in_episode
        self.rec.add(inp.obs, action, self.task)
        self.episode.elapsed_s = self.rec.frames_in_episode / self.fps

    def camera_stale(self, owner: HardwareOwner, names: list[str], stale_s: float) -> None:
        if self.episode.phase == "episode" and stale_s >= owner.settings.safety.camera_stale_pause_s:
            self.paused = True  # the episode clock does not advance; no frame is written

    def poll(self, owner: HardwareOwner, now: float) -> None:
        phase = self.episode.phase
        dt = now - self._phase_t0
        if phase == "countdown":
            self.episode.elapsed_s = dt
            if dt >= self.countdown_s:
                self._enter("episode", now)
        elif phase == "episode":
            if self.rec.frames_in_episode >= round(self.episode_time_s * self.fps):
                self.timeouts += 1
                self._end_episode(keep=self.on_timeout == "save", now=now)
        elif phase == "reset":
            self.episode.elapsed_s = dt
            if dt >= self.reset_time_s:
                self._end_reset(now)
        elif phase == "saving":
            fut = self.rec.saving
            if fut is not None and fut.done():
                self.rec.saving = None
                try:
                    fut.result()
                    self.episode.saved += 1
                except Exception as exc:
                    log.exception("save_episode failed")
                    owner.raise_alert("dataset", "critical", "record.save_failed", {"error": str(exc)[:200]})
                    self.finish("error")
                    return
                self.episode.index = self.rec.next_episode_index
                self.phase_changed = True
                if self.stop_requested:
                    self.finish("stopped")
                elif self._after_saving == "done" or self.episode.saved >= self.num_episodes:
                    self.finish("completed")
                else:
                    self._enter("episode", now)

    def control(self, owner: HardwareOwner, action: str) -> None:
        now = owner.session_now()
        phase = self.episode.phase
        if action == "stop":
            self.stop_requested = True
            if phase == "episode" and self.rec.frames_in_episode > 0:
                self._start_saving(now, after="done")  # a recorded episode is kept
            elif phase == "reset" and self.pending:
                self._start_saving(now, after="done")
            elif phase == "saving":
                self._after_saving = "done"
            else:
                if phase == "episode":
                    self.rec.discard()
                self.finish("stopped")
        elif action == "next":
            if phase == "episode":
                if self.rec.frames_in_episode == 0:
                    return  # nothing recorded yet: an empty episode cannot be saved
                self._end_episode(keep=True, now=now)
            elif phase == "reset":
                self._end_reset(now)
            elif phase == "countdown":
                self._enter("episode", now)
            else:
                raise StationError("busy", f"next is not available while {phase}", params={"state": phase})
        elif action == "rerecord":
            if phase == "episode":
                self.rec.discard()
                self.discarded += 1
                self._enter("reset", now)
            elif phase == "reset":
                if self.pending:
                    self.rec.discard()
                    self.discarded += 1
                    self.pending = False
            else:
                raise StationError(
                    "busy", f"rerecord is not available while {phase}", params={"state": phase}
                )
        else:
            raise StationError("validation_failed", f"unknown control {action!r}")

    def on_telemetry(self, line: dict[str, Any]) -> None:
        if self.episode.phase == "episode" and self.recorder is not None:
            self.rec.buffer.add({**line, "frame_index": self.rec.frames_in_episode})

    def controls(self) -> dict[str, bool]:
        phase = self.episode.phase
        return {
            "next": phase in ("episode", "reset", "countdown"),
            "rerecord": phase in ("episode", "reset"),
            "stop": True,
        }

    def end(self, owner: HardwareOwner, reason: str) -> None:
        if self.recorder is None:
            return
        rec = self.rec
        in_flight = rec.saving is not None
        pending = self.pending  # a fully recorded episode is kept, whatever ended the session
        self.pending = False
        if in_flight or pending:
            # e-stop / camera lost / error while an episode waits for the encoder: never in the
            # owner thread (a second e-stop press must relax at once); the next session on this
            # dataset waits for it (``wait_closed``).
            def failed(exc: BaseException) -> None:
                owner.raise_alert("dataset", "critical", "record.save_failed", {"error": str(exc)[:200]})

            rec.close_async(save_pending=pending, on_error=failed)
            self.episode.saved += int(in_flight) + int(pending)
            self.summary["finalizing"] = True
        else:
            rec.finalize()
        self.summary.update(
            {
                "dataset": rec.name,
                "saved": self.episode.saved,
                "discarded": self.discarded,
                "timeouts": self.timeouts,
                "root": str(rec.root),
                "save_s": list(rec.save_s),
            }
        )
