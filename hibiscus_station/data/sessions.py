"""Per-session logs: ``sessions/<id>/{session.json, telemetry.jsonl.gz}`` and retention (spec §4.5.4)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import time
from pathlib import Path
from typing import Any

from hibiscus_station.data.sidecar import JsonlGz, read_lines, to_series
from hibiscus_station.settings import write_private


class SessionLog:
    def __init__(self, root: Path, session_id: str, meta: dict[str, Any]) -> None:
        self.dir = root / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = dict(meta)
        self.meta.setdefault("id", session_id)
        self.meta.setdefault("started_at", dt.datetime.now(dt.UTC).isoformat())
        self.telemetry = JsonlGz(self.dir / "telemetry.jsonl.gz")
        self.write_meta()

    def write_meta(self) -> None:
        write_private(self.dir / "session.json", json.dumps(self.meta, indent=2, default=str))

    def line(self, obj: dict[str, Any]) -> None:
        self.telemetry.write(obj)

    def close(self, **end: Any) -> None:
        self.telemetry.close()
        self.meta.update(end)
        self.meta.setdefault("ended_at", dt.datetime.now(dt.UTC).isoformat())
        self.write_meta()


def list_sessions(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir(), reverse=True):
        meta_path = d / "session.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except ValueError:
            continue
        row = {
            k: meta.get(k)
            for k in (
                "id",
                "kind",
                "started_at",
                "ended_at",
                "outcome",
                "reason",
                "dataset",
                "model",
                "robot",
            )
        }
        summary = _dict(meta.get("summary"))
        temps = [v for v in _dict(summary.get("max_temp_c")).values() if isinstance(v, (int, float))]
        eps = _dict(summary.get("summary")).get("episodes", _dict(summary.get("episode")).get("saved"))
        row["episodes"] = int(eps) if isinstance(eps, int) else None
        row["max_temp_c"] = max(temps) if temps else None
        out.append(row)
    return out


def _dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def session_series(root: Path, session_id: str) -> dict[str, Any] | None:
    d = root / session_id
    if not (d / "session.json").is_file():
        return None
    return to_series(read_lines(d / "telemetry.jsonl.gz"))


def prune(root: Path, max_age_days: int, max_bytes: int, now: float | None = None) -> list[str]:
    """Remove sessions older than ``max_age_days`` or beyond ``max_bytes`` in total, oldest first."""
    if not root.is_dir():
        return []
    now = time.time() if now is None else now
    dirs = sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime)
    removed = []
    sizes = {d: sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) for d in dirs}
    total = sum(sizes.values())
    for d in dirs:
        too_old = now - d.stat().st_mtime > max_age_days * 86400
        if too_old or total > max_bytes:
            total -= sizes[d]
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)
    return removed
