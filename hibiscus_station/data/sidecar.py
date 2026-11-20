"""Telemetry logs (R1, spec §4.5.4): per session and per recorded episode (sidecar next to the dataset).

The sidecar lives in ``<datasets>/<name>.hibiscus/``, never inside the LeRobot root, so the dataset
stays byte-for-byte what lerobot writes.
"""

from __future__ import annotations

import gzip
import io
import json
import shutil
import time
import zlib
from pathlib import Path
from typing import Any

from hibiscus_station.settings import write_private


def sidecar_dir(datasets_root: Path, name: str) -> Path:
    return datasets_root / f"{name}.hibiscus"


def episode_file(datasets_root: Path, name: str, index: int) -> Path:
    return sidecar_dir(datasets_root, name) / "telemetry" / f"episode_{index:06d}.jsonl.gz"


class JsonlGz:
    """Append-only gzip JSONL with a flush at most once per second."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._fh: Any = gzip.open(path, "at", encoding="utf-8")
        self._last_flush = time.monotonic()
        self.lines = 0

    def write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")
        self.lines += 1
        now = time.monotonic()
        if now - self._last_flush >= 1.0:
            self._fh.flush()
            self._last_flush = now

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class EpisodeBuffer:
    """Telemetry lines of the episode being recorded; written on save, dropped on discard."""

    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = []

    def add(self, obj: dict[str, Any]) -> None:
        self.lines.append(obj)

    def save(self, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for line in self.lines:
                gz.write((json.dumps(line, separators=(",", ":"), default=str) + "\n").encode())
        write_private(path, buf.getvalue())
        n = len(self.lines)
        self.lines = []
        return n

    def discard(self) -> None:
        self.lines = []


def read_lines(path: Path) -> list[dict[str, Any]]:
    """The log's lines; a truncated or damaged file (crash while writing) keeps what was readable."""
    if not path.is_file():
        return []
    out = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
    except (OSError, EOFError, ValueError, zlib.error):  # BadGzipFile is an OSError
        pass
    return out


def to_series(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """TelemetrySeries (§5.3) from log lines."""
    series: dict[str, Any] = {
        "arm_motors": {},
        "t": [],
        "frame_index": [],
        "temp_c": {},
        "voltage_v": {},
        "current_a": {},
        "load_pct": {},
        "alerts": [],
    }
    for line in lines:
        if "alert" in line:
            series["alerts"].append(line["alert"])
            continue
        arm = line.get("arm")
        if not arm:
            continue
        i = len(series["t"])
        series["t"].append(line.get("t"))
        fi = line.get("frame_index")
        series["frame_index"].append(int(fi) if isinstance(fi, (int, float)) else None)
        for field in ("temp_c", "voltage_v", "current_a", "load_pct"):
            vals = line.get(field)
            if not isinstance(vals, dict):
                continue
            arm_series = series[field].setdefault(arm, {})
            for motor, v in vals.items():
                col = arm_series.setdefault(motor, [])
                col.extend([None] * (i - len(col)))  # aligned with t: null where not sampled
                col.append(v)
                motors = series["arm_motors"].setdefault(arm, [])
                if motor not in motors:
                    motors.append(motor)
    n = len(series["t"])
    for field in ("temp_c", "voltage_v", "current_a", "load_pct"):
        for arm_series in series[field].values():
            for col in arm_series.values():
                col.extend([None] * (n - len(col)))
    return series


def max_temps(lines: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for line in lines:
        arm = line.get("arm")
        temps = line.get("temp_c")
        if not arm or not isinstance(temps, dict):
            continue
        for m, v in temps.items():
            if isinstance(v, (int, float)):
                out.setdefault(arm, {})[m] = max(out.get(arm, {}).get(m, float("-inf")), float(v))
    return out


def remove_sidecar(datasets_root: Path, name: str) -> None:
    shutil.rmtree(sidecar_dir(datasets_root, name), ignore_errors=True)
