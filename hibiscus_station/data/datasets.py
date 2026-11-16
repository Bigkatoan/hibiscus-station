"""Local dataset catalog under ``~/.hibiscus/station/datasets`` (spec §6.7, L14: cheap metadata reads)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from hibiscus_station.data.sidecar import episode_file, max_temps, read_lines, sidecar_dir, to_series
from hibiscus_station.errors import StationError
from hibiscus_station.sessions.recorder import check_name
from hibiscus_station.settings import write_private


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _meta(datasets_root: Path, name: str) -> dict[str, Any]:
    path = sidecar_dir(datasets_root, name) / "dataset.json"
    if path.is_file():
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return data
        except ValueError:
            return {}
    return {}


def summary(datasets_root: Path, name: str) -> dict[str, Any] | None:
    from hibiscus.recording import check_recording

    root = datasets_root / name
    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        return None
    info = json.loads(info_path.read_text(encoding="utf-8"))
    features = info.get("features", {})
    cams = [k.removeprefix("observation.images.") for k in features if k.startswith("observation.images.")]
    meta = _meta(datasets_root, name)
    st = check_recording(root)
    uploads = [_upload(u) for u in meta.get("uploads", []) if isinstance(u, dict)]
    fps = info.get("fps")
    return {
        "name": name,
        "root": str(root),
        "episodes": int(info.get("total_episodes", 0)),
        "frames": int(info.get("total_frames", 0)),
        "fps": int(fps) if isinstance(fps, (int, float)) else None,
        "robot_type": info.get("robot_type"),
        "cameras": cams,
        "video": any(v.get("dtype") == "video" for v in features.values() if isinstance(v, dict)),
        "size_bytes": _dir_size(root),
        "finalized": st.complete,
        "finalize_reasons": st.reasons,
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


def episodes(datasets_root: Path, name: str, fps: int | None = None) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    root = datasets_root / name
    rows: list[dict[str, Any]] = []
    for f in sorted((root / "meta" / "episodes").rglob("*.parquet")):
        cols = pq.read_schema(f).names
        want = [c for c in ("episode_index", "length", "tasks") if c in cols]
        t = pq.read_table(f, columns=want).to_pydict()
        for i in range(len(t.get("episode_index", []))):
            idx = int(t["episode_index"][i])
            lines = read_lines(episode_file(datasets_root, name, idx))
            frames = int(t["length"][i]) if "length" in t else None
            tasks = t["tasks"][i] if "tasks" in t else None
            rows.append(
                {
                    "index": idx,
                    "frames": frames,
                    "length_s": round(frames / fps, 3) if frames is not None and fps else None,
                    "tasks": [str(x) for x in tasks] if isinstance(tasks, list) else None,
                    "telemetry_lines": len(lines),
                    "max_temp_c": max_temps(lines),
                }
            )
    rows.sort(key=lambda r: r["index"])
    return rows


def detail(datasets_root: Path, name: str) -> dict[str, Any]:
    check_name(name)
    s = summary(datasets_root, name)
    if s is None:
        raise StationError("not_found", f"no dataset {name}")
    return {**s, "episode_list": episodes(datasets_root, name, s["fps"])}


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
