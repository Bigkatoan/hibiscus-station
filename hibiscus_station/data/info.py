"""One validator for a dataset's ``meta/info.json`` (QC 0.2.10 M1-2), used by the list, the detail
page, append and replay. A dataset whose info.json fails it is *unreadable*, with the reasons;
nothing reads a value from it that the validator did not accept.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, TypeGuard

#: A count at or above this is damage, not a recording (QH-1).
MAX_COUNT = 10**9
#: Frames are counted across every episode: a looser bound, still never allocated by.
MAX_FRAMES = 10**12


def plausible_fps(v: Any) -> TypeGuard[float]:
    """fps: an int or float (not a bool), finite, 1 to 1000."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 1 <= v <= 1000


def plausible_count(v: Any, limit: int = MAX_COUNT) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < limit


def _shape_ok(shape: Any) -> TypeGuard[list[int]]:
    return isinstance(shape, list) and all(
        isinstance(x, int) and not isinstance(x, bool) and 0 <= x < 1_000_000 for x in shape
    )


def info_problems(info: Any) -> list[str]:
    """Why ``info`` (the parsed meta/info.json) cannot be trusted; empty when it can."""
    if not isinstance(info, dict):
        return ["meta/info.json is not a JSON object"]
    out: list[str] = []
    if not plausible_fps(info.get("fps")):
        out.append("meta/info.json: fps is missing or not a number from 1 to 1000")
    if not plausible_count(info.get("total_episodes")):
        out.append("meta/info.json: total_episodes is not a plausible count")
    if not plausible_count(info.get("total_frames"), MAX_FRAMES):
        out.append("meta/info.json: total_frames is not a plausible count")
    if "total_tasks" in info and not plausible_count(info["total_tasks"]):
        out.append("meta/info.json: total_tasks is not a plausible count")
    version = info.get("codebase_version")
    if not isinstance(version, str) or not version.startswith("v3"):
        out.append("meta/info.json: codebase_version is not v3.x")
    # what LeRobot writes with when a session continues the dataset
    for key in ("chunks_size", "data_files_size_in_mb", "video_files_size_in_mb"):
        if key in info and not (plausible_count(info[key]) and info[key] > 0):
            out.append(f"meta/info.json: {key} is not a positive count")
    data_path, video_path = info.get("data_path"), info.get("video_path")
    if (
        not isinstance(data_path, str)
        or "{chunk_index" not in data_path
        or ".." in data_path
        or Path(data_path).is_absolute()
        or data_path.startswith(("/", "\\"))
    ):
        out.append("meta/info.json: data_path is not a LeRobot path template")
    if video_path is not None and (
        not isinstance(video_path, str)
        or "{video_key" not in video_path
        or ".." in video_path
        or Path(video_path).is_absolute()
        or video_path.startswith(("/", "\\"))
    ):
        out.append("meta/info.json: video_path is not a LeRobot path template")
    features = info.get("features")
    if not isinstance(features, dict) or not features:
        out.append("meta/info.json: features is missing or not an object")
        return out
    for key, ft in features.items():
        if not isinstance(ft, dict):
            out.append(f"meta/info.json: feature {key} is not an object")
            continue
        if not isinstance(ft.get("dtype"), str) or not ft["dtype"]:
            out.append(f"meta/info.json: feature {key} has no dtype")
        shape = ft.get("shape")
        if not _shape_ok(shape):
            out.append(f"meta/info.json: feature {key} has no valid shape")
            continue
        names = ft.get("names")
        if names is not None:
            if isinstance(names, list):
                if not all(isinstance(n, str) for n in names):
                    out.append(f"meta/info.json: feature {key} names are not text")
                elif len(shape) == 1 and len(names) != shape[0]:
                    out.append(f"meta/info.json: feature {key} has {len(names)} names for shape {shape}")
            elif not isinstance(names, dict):
                out.append(f"meta/info.json: feature {key} names are malformed")
    if (
        any(isinstance(ft, dict) and ft.get("dtype") == "video" for ft in features.values())
        and not video_path
    ):
        out.append("meta/info.json: video features without a video_path")
    action = features.get("action")
    if not isinstance(action, dict) or not isinstance(action.get("names"), list) or not action["names"]:
        out.append("meta/info.json: the action feature has no joint names")
    return out


def consistency_problems(root: Path, info: dict[str, Any]) -> list[str]:
    """Why the episode rows on disk disagree with ``info`` (QC 0.2.10 QH-9: a total_episodes lower
    than the rows let an append overwrite data/chunk-000/file-000.parquet). Expects ``info`` to
    have passed :func:`info_problems`; reads only the ``meta/episodes`` parquet files, which must
    all be closed (a footerless file is reported, never read)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from hibiscus.recording import parquet_closed

    total, frames = info["total_episodes"], info["total_frames"]
    video_keys = [k for k, ft in info["features"].items() if ft.get("dtype") == "video"]
    files = sorted((root / "meta" / "episodes").rglob("*.parquet"))
    if total > 0 and not files:
        return ["meta/episodes has no file"]
    wanted = ["episode_index", "length", "data/chunk_index", "data/file_index"]
    wanted += ["dataset_from_index", "dataset_to_index"]
    for k in video_keys:
        wanted += [f"videos/{k}/chunk_index", f"videos/{k}/file_index"]
    rows: dict[str, list[Any]] = {c: [] for c in wanted}
    for f in files:
        rel = f.relative_to(root)
        if not parquet_closed(f):
            return [f"{rel} is not finalized"]
        try:
            names = pq.read_schema(f).names
            missing = [c for c in wanted if c not in names]
            if missing:
                return [f"{rel} lacks {', '.join(missing[:3])}"]
            t = pq.read_table(f, columns=wanted).to_pydict()
        except (OSError, ValueError, pa.ArrowException) as exc:
            return [f"{rel} cannot be read: {type(exc).__name__}"]
        for c in wanted:
            rows[c] += t[c]
    out: list[str] = []
    n = len(rows["episode_index"])
    if n != total:
        out.append(f"meta/info.json counts {total} episodes, meta/episodes holds {n}")
    try:
        order = sorted(range(n), key=lambda i: int(rows["episode_index"][i]))
        if [int(rows["episode_index"][i]) for i in order] != list(range(n)):
            out.append("the episode indexes are not 0..N-1 without gaps")
        lengths = [int(rows["length"][i]) for i in order]
        if sum(lengths) != frames:
            out.append(f"meta/info.json counts {frames} frames, the episodes hold {sum(lengths)}")
        expect = 0
        for i in order:
            if int(rows["dataset_from_index"][i]) != expect:
                out.append("the episodes' frame ranges are not contiguous")
                break
            expect = int(rows["dataset_to_index"][i])
        refs: set[str] = set()
        for i in order:
            ci, fi = int(rows["data/chunk_index"][i]), int(rows["data/file_index"][i])
            refs.add(info["data_path"].format(chunk_index=ci, file_index=fi))
            for k in video_keys:
                vc, vf = int(rows[f"videos/{k}/chunk_index"][i]), int(rows[f"videos/{k}/file_index"][i])
                refs.add(info["video_path"].format(video_key=k, chunk_index=vc, file_index=vf))
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        return [*out, f"meta/episodes holds malformed values ({type(exc).__name__})"]
    gone = sorted(r for r in refs if not (root / r).is_file())
    if gone:
        out.append(f"missing files: {', '.join(gone[:3])}")
    return out
