"""Local dataset catalog under ``~/.hibiscus/station/datasets`` (spec §6.7, L14: cheap metadata reads)."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from hibiscus_station.data.sidecar import episode_file, max_temps, read_lines, sidecar_dir, to_series
from hibiscus_station.errors import StationError
from hibiscus_station.sessions.recorder import check_name, live_episodes
from hibiscus_station.settings import write_private


def _dir_size(p: Path) -> int:
    """Bytes under ``p``. The encoder deletes ``images/`` frames meanwhile (a file listed by the
    walk may be gone, or on Windows pending deletion, by the time it is stat'ed): skipped."""
    total = 0
    for dirpath, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.stat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def _read_info(path: Path, attempts: int = 5) -> dict[str, Any] | None:
    """``meta/info.json``, or None when it is unreadable. lerobot rewrites it in place (truncate,
    then write) on every saved episode, so a read in between sees an empty or half file: retried."""
    for i in range(attempts):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            if i < attempts - 1:
                time.sleep(0.05)
            continue
        return data if isinstance(data, dict) else None
    return None


def _meta(datasets_root: Path, name: str) -> dict[str, Any]:
    path = sidecar_dir(datasets_root, name) / "dataset.json"
    if path.is_file():
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
        except (OSError, ValueError):
            return {}
    return {}


#: More episodes or frames than any recording holds: the value in info.json is damaged (QC QH-1).
_ABSURD = 10**9


def _count(v: Any) -> int | None:
    """A count from info.json, or None when it is not a plausible non-negative integer."""
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < _ABSURD:
        return None
    return v


def _sidecar_indexes(datasets_root: Path, name: str) -> set[int]:
    """Episode indexes that have a telemetry sidecar (written right after each saved episode)."""
    out: set[int] = set()
    try:
        with os.scandir(sidecar_dir(datasets_root, name) / "telemetry") as it:
            for e in it:
                stem = e.name.removesuffix(".jsonl.gz")
                if stem.startswith("episode_") and stem[8:].isdigit():
                    out.add(int(stem[8:]))
    except OSError:
        pass
    return out


def summary(datasets_root: Path, name: str) -> dict[str, Any] | None:
    from hibiscus.recording import check_recording

    root = datasets_root / name
    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        return None
    info = _read_info(info_path) or {}
    features: dict[str, Any] = info["features"] if isinstance(info.get("features"), dict) else {}
    cams = [k.removeprefix("observation.images.") for k in features if k.startswith("observation.images.")]
    meta = _meta(datasets_root, name)
    st = check_recording(root)
    uploads = [_upload(u) for u in meta.get("uploads", []) if isinstance(u, dict)]
    fps = info.get("fps")
    episodes, frames = _count(info.get("total_episodes")), _count(info.get("total_frames"))
    reasons = list(st.reasons)
    for key, val in (("total_episodes", episodes), ("total_frames", frames)):
        if val is None and info:
            reasons.append(f"meta/info.json: {key} is not a plausible count")
    return {
        "name": name,
        "root": str(root),
        "episodes": episodes or 0,
        "frames": frames or 0,
        "fps": int(fps)
        if isinstance(fps, (int, float)) and not isinstance(fps, bool) and 0 < fps < 1000
        else None,
        "robot_type": info.get("robot_type"),
        "cameras": cams,
        "video": any(v.get("dtype") == "video" for v in features.values() if isinstance(v, dict)),
        "size_bytes": _dir_size(root),
        "finalized": st.complete and reasons == st.reasons,
        "finalize_reasons": reasons,
        "task": meta.get("task"),
        "uploads": uploads,
        "uploaded": uploads[-1] if uploads else None,
    }


def _upload(u: dict[str, Any]) -> dict[str, Any]:
    keys = ("server", "dataset_id", "version_id", "version", "at", "server_url", "train_url")
    return {k: u.get(k) for k in keys}


def list_datasets(datasets_root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not datasets_root.is_dir():
        return out
    for d in sorted(datasets_root.iterdir()):
        if d.is_dir() and not d.name.endswith(".hibiscus"):
            s = summary(datasets_root, d.name)
            if s is not None:
                out.append(s)
    return out


def _written_rows(root: Path) -> dict[int, tuple[int | None, list[str] | None]]:
    """episode index -> (frames, tasks) from the ``meta/episodes`` files that are complete. A file
    without its parquet footer is lerobot's open writer (it flushes 10 rows at a time and closes
    the file in ``finalize()``) or what a Station closed mid-session left: skipped, never a 500."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from hibiscus.recording import parquet_closed

    rows: dict[int, tuple[int | None, list[str] | None]] = {}
    for f in sorted((root / "meta" / "episodes").rglob("*.parquet")):
        if not parquet_closed(f):
            continue
        try:
            cols = pq.read_schema(f).names
            want = [c for c in ("episode_index", "length", "tasks") if c in cols]
            t = pq.read_table(f, columns=want).to_pydict()
        except (OSError, ValueError, pa.ArrowException):
            continue
        for i in range(len(t.get("episode_index", []))):
            tasks = t["tasks"][i] if "tasks" in t else None
            rows[int(t["episode_index"][i])] = (
                int(t["length"][i]) if "length" in t and t["length"][i] is not None else None,
                [str(x) for x in tasks] if isinstance(tasks, list) else None,
            )
    return rows


def episodes(datasets_root: Path, name: str, fps: int | None = None, total: int = 0) -> list[dict[str, Any]]:
    """One row per episode the dataset counts (``total``, from ``meta/info.json``) or a recorder
    is saving. ``state``: ``saved``; ``saving`` (being encoded and written now); ``unreadable``
    (counted, but lerobot never wrote its row: the Station closed before the dataset was
    finalized)."""
    root = datasets_root / name
    live = live_episodes(root)  # before the files: a finalize in between leaves its rows on disk
    written = _written_rows(root)
    # Unwritten episodes are listed up to what the disk shows (rows, sidecars, a live recorder,
    # plus the one counted just before its sidecar was written), never up to the count in
    # info.json alone: a damaged count must not allocate (QC QH-1).
    seen = set(written) | set(live) | _sidecar_indexes(datasets_root, name)
    counted = range(min(total, max(seen, default=-1) + 2))
    out: list[dict[str, Any]] = []
    for idx in sorted(seen | set(counted)):
        tasks: list[str] | None = None
        if idx in written:
            frames, tasks = written[idx]
            state = "saved"
        elif idx in live:
            frames = live[idx].frames
            state = "saving" if live[idx].saving else "saved"
        else:
            frames, state = None, "unreadable"
        lines = read_lines(episode_file(datasets_root, name, idx)) if state != "saving" else []
        out.append(
            {
                "index": idx,
                "state": state,
                "frames": frames,
                "length_s": round(frames / fps, 3) if frames is not None and fps else None,
                "tasks": tasks,
                "telemetry_lines": len(lines),
                "max_temp_c": max_temps(lines),
            }
        )
    return out


def detail(datasets_root: Path, name: str) -> dict[str, Any]:
    check_name(name)
    s = summary(datasets_root, name)
    if s is None:
        raise StationError("not_found", f"no dataset {name}")
    return {**s, "episode_list": episodes(datasets_root, name, s["fps"], s["episodes"])}


def episode_series(datasets_root: Path, name: str, index: int) -> dict[str, Any]:
    check_name(name)
    path = episode_file(datasets_root, name, index)
    if not path.is_file():
        raise StationError("not_found", f"no telemetry for episode {index} of {name}")
    return to_series(read_lines(path))


def delete(datasets_root: Path, name: str) -> None:
    check_name(name)
    root = datasets_root / name
    if not root.exists():
        raise StationError("not_found", f"no dataset {name}")
    shutil.rmtree(root)
    shutil.rmtree(sidecar_dir(datasets_root, name), ignore_errors=True)


def record_upload(datasets_root: Path, name: str, server: str, result: dict[str, Any]) -> None:
    import datetime as dt

    path = sidecar_dir(datasets_root, name) / "dataset.json"
    meta = _meta(datasets_root, name)
    meta.setdefault("uploads", []).append(
        {
            "server": server,
            "dataset_id": result.get("dataset_id"),
            "version_id": result.get("version_id"),
            "version": result.get("version"),
            "server_url": result.get("server_url"),
            "train_url": result.get("train_url"),
            "at": dt.datetime.now(dt.UTC).isoformat(),
        }
    )
    write_private(path, json.dumps(meta, indent=2))
