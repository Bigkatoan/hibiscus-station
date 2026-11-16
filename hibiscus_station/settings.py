"""Paths (spec §7), thresholds and defaults (§4.5.3, §4.7), stored in ``settings.yaml``.

Every file written here is atomic (temp file + ``os.replace``) and private (0600, dirs 0700).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from hibiscus_station.oscompat import replace_file

DEFAULT_PORT = 18210


def station_home() -> Path:
    env = os.environ.get("HIBISCUS_STATION_HOME")
    return Path(env).expanduser() if env else Path.home() / ".hibiscus" / "station"


def calibration_root() -> Path:
    """lerobot's calibration root, resolved at call time (``utils/constants.py:93-101``)."""
    if env := os.environ.get("HF_LEROBOT_CALIBRATION"):
        return Path(env).expanduser()
    if home := os.environ.get("HF_LEROBOT_HOME"):
        return Path(home).expanduser() / "calibration"
    hf_home = os.environ.get("HF_HOME")
    cache = os.environ.get("XDG_CACHE_HOME")  # huggingface_hub honours it on every OS
    base = Path(hf_home).expanduser() if hf_home else Path(cache or Path.home() / ".cache") / "huggingface"
    return base / "lerobot" / "calibration"


def write_private(path: Path, data: str | bytes) -> None:
    """Atomic write with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data.encode("utf-8") if isinstance(data, str) else data)
        os.chmod(tmp, 0o600)
        replace_file(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class StationPaths:
    home: Path

    @property
    def settings(self) -> Path:
        return self.home / "settings.yaml"

    @property
    def robots(self) -> Path:
        return self.home / "robots.yaml"

    @property
    def pid(self) -> Path:
        return self.home / "station.pid"

    @property
    def lock(self) -> Path:
        return self.home / "station.lock"

    @property
    def token(self) -> Path:
        return self.home / "token"

    @property
    def server(self) -> Path:
        return self.home / "server.json"

    @property
    def locks(self) -> Path:
        return self.home / "locks"

    @property
    def datasets(self) -> Path:
        return self.home / "datasets"

    @property
    def models(self) -> Path:
        return self.home / "models"

    @property
    def sessions(self) -> Path:
        return self.home / "sessions"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def staging(self) -> Path:
        return self.home / "staging"

    def ensure(self) -> None:
        for d in (self.home, self.locks, self.datasets, self.models, self.sessions, self.logs, self.staging):
            d.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(d, 0o700)
            except OSError:  # pragma: no cover - foreign-owned dir
                pass


class Thresholds(BaseModel):
    """Motor health thresholds (§4.5.3). Validated against the motors' own limit at connect."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    temp_warn_c: float = 50.0
    temp_hot_c: float = 60.0
    temp_critical_c: float = 65.0
    hysteresis_c: float = 3.0
    critical_consecutive: int = Field(2, ge=1, le=10)
    voltage_margin_v: float = 0.5
    voltage_nominal_ratio: float = 0.85
    current_ratio: float = 0.8
    load_stall_pct: float = 90.0
    load_stall_s: float = 2.0

    @model_validator(mode="after")
    def _order(self) -> Thresholds:
        problems = threshold_problems(self, None)
        if problems:
            raise ValueError("; ".join(problems))
        return self


def threshold_problems(t: Thresholds, max_temperature_limit: float | None) -> list[str]:
    """Rules of §4.5.3: critical <= limit - 3, hot <= critical - 3, warn <= hot - 5."""
    out: list[str] = []
    if max_temperature_limit is not None and t.temp_critical_c > max_temperature_limit - 3:
        out.append(
            f"temp_critical_c {t.temp_critical_c} must be <= Max_Temperature_Limit - 3 "
            f"({max_temperature_limit - 3})"
        )
    if t.temp_hot_c > t.temp_critical_c - 3:
        out.append(f"temp_hot_c {t.temp_hot_c} must be <= temp_critical_c - 3 ({t.temp_critical_c - 3})")
    if t.temp_warn_c > t.temp_hot_c - 5:
        out.append(f"temp_warn_c {t.temp_warn_c} must be <= temp_hot_c - 5 ({t.temp_hot_c - 5})")
    return out


class TelemetrySettings(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    hot_hz: float = Field(2.0, gt=0, le=20)
    cool_hz: float = Field(1.0, gt=0, le=20)
    min_slack_ms: float = Field(6.0, ge=0)
    max_age_s: float = Field(2.0, gt=0)
    monitor_hz: float = Field(2.0, gt=0, le=20)
    joints_hz: float = Field(20.0, gt=0, le=60)


class PreviewSettings(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    fps: float = Field(12.0, gt=0, le=30)
    width: int = Field(320, ge=160, le=640)
    quality: int = Field(70, ge=20, le=95)


class SafetySettings(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    max_relative_target: float = Field(5.0, gt=0)
    teleop_max_relative_target: float = Field(
        30.0,
        gt=0,
        description=(
            "Cap on goal - present (deg) while the leader drives the follower (teleop, record). "
            "Larger than max_relative_target: a servo trails a quick human move by v x ~60 ms, and "
            "a smaller cap makes the follower chase the leader (lag). It still stops a leader "
            "reading that jumps (bad packet, wrong calibration)."
        ),
    )
    deadman_timeout_s: float = Field(1.0, gt=0)
    deadman_replay: bool = True
    estop_double_press_s: float = 2.0
    park_s: float = 1.5
    smooth_approach_s: float = 1.5
    stopping_deadline_s: float = 10.0
    camera_stale_pause_s: float = 0.5
    camera_lost_stop_s: float = 3.0
    overrun_pause_s: float = 5.0
    max_approach_deg: float = 30.0


class ProgramSettings(BaseModel):
    """Trajectories and block programs (station-programs.md §3-§6)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    require_dry_run: bool = Field(True, description="a hardware run needs a dry run of that version (§5.2)")
    condition_hz: float = Field(10.0, gt=0, le=10, description="max rate of wait until / while checks")
    wait_timeout_s: float = Field(30.0, gt=0, le=86400, description="default wait until timeout")
    approach_speed_deg_s: float = Field(30.0, gt=0, le=90, description="move-to-start / go home cap")
    approach_threshold_deg: float = Field(3.0, gt=0, le=30, description="farther than this: approach first")
    check_speed_pct: float = Field(25.0, ge=10, le=100, description="speed of a needs_check replay")
    traj_default_s: float = Field(60.0, gt=0, le=600)
    traj_max_s: float = Field(600.0, gt=0, le=600)
    idle_trim_deg: float = Field(0.5, ge=0, description="auto trim: joints moving less than this...")
    idle_trim_s: float = Field(0.5, ge=0, description="...for longer than this are idle")
    max_blocks: int = Field(2000, ge=1, le=20000)
    notify_webhook: str | None = Field(None, description="notify blocks with webhook on POST here")
    mqtt_url: str | None = Field(None, description="mqtt://host:port; null = no MQTT client")
    mqtt_topics: list[str] = Field(default_factory=list, description="topics fed into the signal bus")


class Settings(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    thresholds: Thresholds = Field(default_factory=Thresholds)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    preview: PreviewSettings = Field(default_factory=PreviewSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    programs: ProgramSettings = Field(default_factory=ProgramSettings)
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    session_retention_days: int = Field(30, ge=1)
    session_retention_bytes: int = Field(2 * 1024**3, ge=0)

    @classmethod
    def load(cls, path: Path) -> Settings:
        if not path.is_file():
            return cls()
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(raw)

    def save(self, path: Path) -> None:
        write_private(path, yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False))
