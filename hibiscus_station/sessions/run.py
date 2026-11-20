"""Run-model session (R2, spec §4.9 / §6.9): countdown -> episode -> reset -> ... with a policy.

Inference is inline in the owner thread: the observation (joints + camera frames of tick k) and its
action belong to the same tick. The frames given to the policy are the frames published to the
preview for that tick (``policy_input: true``), so the UI shows exactly what the model saw.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError
from hibiscus_station.models.loader import LoadedPolicy
from hibiscus_station.sessions.base import MotionSession, TickInput
from hibiscus_station.sessions.recorder import DatasetRecorder

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner

log = logging.getLogger(__name__)


@dataclass
class RunSession(MotionSession):
    loaded: LoadedPolicy | None = None
    camera_map: dict[str, str] = field(default_factory=dict)  # policy key -> hub camera
    num_episodes: int = 1
    episode_time_s: float = 30.0
    reset_time_s: float = 10.0
    countdown_s: float = 3.0
    reset_with_leader: bool = False
    recorder: DatasetRecorder | None = None
    robot_type: str = "so_follower"
    ds_features: dict[str, Any] = field(default_factory=dict)
    last_policy_tick: int = -1
    last_policy_frames: dict[str, Any] = field(default_factory=dict)
    policy_resets: int = 0
    inferences: int = 0
    paused_reason: str | None = None
    _phase_t0: float = 0.0
    _episode_ticks: int = 0

    def __post_init__(self) -> None:
        self.deadman = True
        self.policy_input = True
        self.uses_leader = self.reset_with_leader
        self.episode.of = self.num_episodes

    @property
    def lp(self) -> LoadedPolicy:
        if self.loaded is None:
            raise StationError("model_not_loaded", "no policy loaded for this run")
        return self.loaded

    def build_features(self, motor_keys: list[str], cam_shapes: dict[str, tuple[int, int, int]]) -> None:
        from lerobot.utils.feature_utils import hw_to_dataset_features

        motors = dict.fromkeys(motor_keys, float)
        policy_cams = {
            key.removeprefix("observation.images."): cam_shapes[cam]
            for key, cam in self.camera_map.items()
            if cam in cam_shapes
        }
        self.ds_features = {
            **hw_to_dataset_features(motors, "action", True),
            **hw_to_dataset_features({**motors, **policy_cams}, "observation", True),
        }

    def _enter(self, phase: str, now: float) -> None:
        self._phase_t0 = now
        self.set_phase(phase)
        self.recording_active = phase == "episode" and self.recorder is not None
        self.episode.elapsed_s = 0.0
        self.episode.limit_s = {
            "countdown": self.countdown_s,
            "episode": self.episode_time_s,
            "reset": self.reset_time_s,
        }.get(phase)
        if phase == "episode":
            self._episode_ticks = 0
            self.lp.reset()
            self.policy_resets += 1

    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        self.episode.index = 0
        self._enter("countdown", 0.0)

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        from lerobot.policies.utils import make_robot_action
        from lerobot.utils.feature_utils import build_dataset_frame

        phase = self.episode.phase
        if phase == "reset" and self.reset_with_leader and inp.leader is not None:
            return dict(inp.leader)
        if phase != "episode" or self.paused_reason:
            return None  # hold
        if inp.stale:
            return None  # never feed the policy a stale input; the clock pauses (camera_stale)
        values: dict[str, Any] = {k: v for k, v in inp.obs.items() if k.endswith(".pos")}
        for key, cam in self.camera_map.items():
            values[key.removeprefix("observation.images.")] = inp.frames[cam]
        frame = build_dataset_frame(self.ds_features, values, "observation")
        t0 = time.perf_counter()
        out = self.lp.predict(frame, task=self.task, robot_type=self.robot_type)
        ms = (time.perf_counter() - t0) * 1000.0
        owner.stats.inference_ms(t0, ms, 1.0 / self.fps)
        self.inferences += 1
        self.last_policy_tick = inp.tick
        self.last_policy_frames = {cam: inp.frames[cam] for cam in self.camera_map.values()}
        action: dict[str, float] = make_robot_action(out, self.ds_features)
        self._episode_ticks += 1
        self.episode.elapsed_s = self._episode_ticks / self.fps
        return action

    def after_send(
        self, owner: HardwareOwner, inp: TickInput, action: dict[str, float], sent: dict[str, float]
    ) -> None:
        if (
            self.recorder is not None
            and self.episode.phase == "episode"
            and self.last_policy_tick == inp.tick
        ):
            self.frame_index = self.recorder.frames_in_episode
            self.recorder.add(inp.obs, action, self.task)

    def poll(self, owner: HardwareOwner, now: float) -> None:
        phase = self.episode.phase
        dt = now - self._phase_t0
        slow = owner.stats.slow_inference_since
        if (
            phase == "episode"
            and slow is not None
            and time.perf_counter() - slow >= owner.settings.safety.overrun_pause_s
            and not self.paused_reason
        ):
            self.paused_reason = "model_too_slow"
            owner.raise_alert(
                "loop",
                "warn",
                "run.model_too_slow",
                {"fps": self.fps, "device": self.lp.device},
            )
            self.phase_changed = True
        if phase == "countdown":
            self.episode.elapsed_s = dt
            if dt >= self.countdown_s:
                self._enter("episode", now)
        elif phase == "episode":
            if self._episode_ticks >= round(self.episode_time_s * self.fps):
                self._end_episode(now)
        elif phase == "reset":
            self.episode.elapsed_s = dt
            if dt >= self.reset_time_s:
                self._enter("episode", now)
        elif phase == "saving":
            rec = self.recorder
            if rec is None or rec.saving is None or rec.saving.done():
                if rec is not None and rec.saving is not None:
                    rec.saving.result()
                    rec.saving = None
                self._after_episode(now)

    def _end_episode(self, now: float) -> None:
        if self.recorder is not None and self.recorder.frames_in_episode > 0:
            self.recorder.save_async()
            self._enter("saving", now)
            return
        self._after_episode(now)

    def _after_episode(self, now: float) -> None:
        self.episode.saved += 1
        self.episode.index += 1
        if self.episode.saved >= self.num_episodes:
            self.finish("completed")
        else:
            self._enter("reset", now)

    def control(self, owner: HardwareOwner, action: str) -> None:
        now = owner.session_now()
        if action == "stop":
            self.finish("stopped")
        elif action == "next":
            phase = self.episode.phase
            if phase == "episode":
                self._end_episode(now)
            elif phase in ("countdown", "reset"):
                self._enter("episode", now)
            else:
                raise StationError("busy", f"next is not available while {phase}", params={"state": phase})
        elif action == "resume" and self.paused_reason:
            self.paused_reason = None
            owner.stats.slow_inference_since = None
        else:
            raise StationError("validation_failed", f"control {action!r} is not available for run")

    def on_telemetry(self, line: dict[str, Any]) -> None:
        if self.recorder is not None and self.episode.phase == "episode":
            self.recorder.buffer.add({**line, "frame_index": self.recorder.frames_in_episode})

    def controls(self) -> dict[str, bool]:
        return {
            "next": self.episode.phase in ("countdown", "episode", "reset"),
            "rerecord": False,
            "stop": True,
        }

    def view(self) -> dict[str, Any]:
        v = super().view()
        v["paused"] = self.paused_reason
        v["policy"] = {"inferences": self.inferences, "last_policy_tick": self.last_policy_tick}
        return v

    def end(self, owner: HardwareOwner, reason: str) -> None:
        rec = self.recorder
        if rec is not None:
            pending = rec.saving is None and reason in ("stopped", "completed") and rec.frames_in_episode > 0
            if rec.saving is not None or pending:
                # never encode in the owner thread (field report 0.2.9): finish in the background

                def failed(exc: BaseException) -> None:
                    owner.raise_alert("dataset", "critical", "record.save_failed", {"error": str(exc)[:200]})

                rec.close_async(save_pending=pending, on_error=failed)
                self.summary["finalizing"] = True
            else:
                rec.finalize()
            self.summary["dataset"] = rec.name
        self.summary.update({"inferences": self.inferences, "episodes": self.episode.saved})
