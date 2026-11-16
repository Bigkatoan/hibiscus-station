"""Motion session base: the owner's control loop drives one of these per tick (spec §4.5.1)."""

from __future__ import annotations

import datetime as dt
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hibiscus_station.errors import StationError

if TYPE_CHECKING:
    from hibiscus_station.hw.owner import HardwareOwner


def new_session_id() -> str:
    now = dt.datetime.now(dt.UTC)
    return f"s_{now:%Y%m%d_%H%M%S}_{secrets.token_hex(2)}"


def joint_keys(obs: dict[str, Any]) -> list[str]:
    return [k for k in obs if k.endswith(".pos")]


@dataclass
class TickInput:
    tick: int
    t: float  # seconds since session start
    obs: dict[str, Any]  # follower positions + camera frames (the policy / dataset input)
    frames: dict[str, Any]
    stale: list[str]
    leader: dict[str, float] | None = None


@dataclass
class EpisodeInfo:
    index: int = 0
    of: int = 0
    saved: int = 0
    phase: str | None = None
    elapsed_s: float = 0.0
    limit_s: float | None = None


@dataclass
class MotionSession:
    kind: str
    fps: int
    task: str = ""
    dataset: str | None = None
    model: str | None = None
    id: str = field(default_factory=new_session_id)
    started_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    t0: float = field(default_factory=time.monotonic)
    deadman: bool = False
    policy_input: bool = False
    uses_leader: bool = False
    episode: EpisodeInfo = field(default_factory=EpisodeInfo)
    finished: bool = False
    outcome: str = "running"
    phase_changed: bool = True
    recording_active: bool = False  # telemetry of this tick belongs to an episode being recorded
    frame_index: int = 0
    summary: dict[str, Any] = field(default_factory=dict)

    # ---- hooks (owner thread only) -------------------------------------------------------
    def begin(self, owner: HardwareOwner, obs: dict[str, Any]) -> None:
        return None

    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None:
        """Return the action for this tick, or ``None`` to send nothing (follower holds)."""
        raise NotImplementedError

    def after_send(
        self, owner: HardwareOwner, inp: TickInput, action: dict[str, float], sent: dict[str, float]
    ) -> None:
        return None

    def poll(self, owner: HardwareOwner, now: float) -> None:
        return None

    def control(self, owner: HardwareOwner, action: str) -> None:
        if action == "stop":
            self.finish("stopped")
            return
        raise StationError("validation_failed", f"control {action!r} is not available for {self.kind}")

    def on_telemetry(self, line: dict[str, Any]) -> None:
        return None

    def camera_stale(self, owner: HardwareOwner, names: list[str], stale_s: float) -> None:
        return None

    def end(self, owner: HardwareOwner, reason: str) -> None:
        """Teardown inside ``stopping`` (finalize datasets, write sidecars)."""
        return None

    # ---- helpers --------------------------------------------------------------------------
    def finish(self, outcome: str) -> None:
        self.finished = True
        if self.outcome == "running":
            self.outcome = outcome

    def set_phase(self, phase: str | None) -> None:
        if phase != self.episode.phase:
            self.episode.phase = phase
            self.phase_changed = True

    def controls(self) -> dict[str, bool]:
        return {"next": False, "rerecord": False, "stop": True}

    def view(self) -> dict[str, Any]:
        e = self.episode
        return {
            "id": self.id,
            "kind": self.kind,
            "started_at": self.started_at,
            "fps": self.fps,
            "episode": {
                "index": e.index,
                "of": e.of,
                "saved": e.saved,
                "phase": e.phase,
                "elapsed_s": round(e.elapsed_s, 2),
                "limit_s": e.limit_s,
            },
            "dataset": self.dataset,
            "model": self.model,
            "task": self.task,
            "controls": self.controls(),
            "outcome": self.outcome,
        }


def session_dir(sessions_root: Path, session_id: str) -> Path:
    return sessions_root / session_id
