"""QC 0.2.10 round 2 (QH-7, QH-8, M1-2): every key of a dataset's ``meta/info.json``, every feature
and every feature field, set to 14 hostile values, against the list, the detail page, the episode
telemetry, append and replay. No 5xx anywhere, the damaged dataset's files are byte-identical
afterwards, and a healthy dataset next to it is unaffected.

The mutations and values are QC's ``fuzz_info.py`` (docs/requirements/qc/evidence/0210-r2/).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

from test_field_0210 import CAM, MOTORS, _recorder, _save, _tree

from hibiscus_station.errors import STATUS, StationError
from hibiscus_station.sessions.recorder import DatasetRecorder
from hibiscus_station.sessions.replay import load_episode_actions
from hibiscus_station.station import Station

HOSTILE: list[Any] = [
    None,
    True,
    0,
    -1,
    1.5,
    10**30,
    float("inf"),
    float("nan"),
    "x",
    "",
    [],
    [1],
    {},
    {"a": 1},
]


def _mutations(base: dict[str, Any]) -> list[tuple[list[str], Any]]:
    muts: list[tuple[list[str], Any]] = []
    for key in base:
        muts += [([key], v) for v in HOSTILE]
    for f, ft in base["features"].items():
        muts += [(["features", f], v) for v in HOSTILE]
        for sub in ft:
            muts += [(["features", f, sub], v) for v in HOSTILE]
    muts += [([], v) for v in (None, [], "x", 1)]
    return muts


def _apply(base: dict[str, Any], path: list[str], value: Any) -> Any:
    if not path:
        return value
    d = copy.deepcopy(base)
    t = d
    for k in path[:-1]:
        t = t[k]
    t[path[-1]] = value
    return d


def _label(path: list[str], value: Any) -> str:
    return f"{'.'.join(path) or '<root>'}={json.dumps(value) if value == value else 'NaN'}"


def _is_4xx(exc: BaseException) -> bool:
    return isinstance(exc, StationError) and STATUS.get(exc.code, 500) < 500


def test_hostile_info_json_never_gives_a_5xx(station: Station, client: Any, tmp_path: Path) -> None:
    datasets = station.paths.datasets
    rec = _recorder(datasets, "ok")
    _save(rec, 1, frames=3)
    rec.finalize()
    rec = _recorder(datasets, "x")
    _save(rec, 1, frames=3)
    rec.finalize()
    pristine = tmp_path / "pristine"
    shutil.copytree(datasets / "x", pristine / "x")
    shutil.copytree(datasets / "x.hibiscus", pristine / "x.hibiscus")
    base = json.loads((pristine / "x" / "meta" / "info.json").read_text(encoding="utf-8"))
    ok_before = _tree(datasets / "ok")
    failures: list[str] = []
    opened: list[str] = []  # appends the checks let through (a valid dataset under the mutation)

    def call(what: str, label: str, fn: Any) -> None:
        try:
            r = fn()
        except Exception as exc:
            if not _is_4xx(exc):
                failures.append(f"{what}: {type(exc).__name__} {label}")
            return
        status = getattr(r, "status_code", 200)
        if status >= 500:
            failures.append(f"{what}: HTTP {status} {label}")

    muts = _mutations(base)
    assert len(muts) > 400, len(muts)
    for path, value in muts:
        label = _label(path, value)
        for part in ("x", "x.hibiscus"):
            shutil.rmtree(datasets / part, ignore_errors=True)
            shutil.copytree(pristine / part, datasets / part)
        (datasets / "x" / "meta" / "info.json").write_text(
            json.dumps(_apply(base, path, value)), encoding="utf-8"
        )
        before = _tree(datasets / "x")

        def listing(label: str = label) -> Any:
            r = client.get("/api/v1/datasets")
            if r.status_code == 200:
                names = {d["name"]: d for d in r.json()["datasets"]}
                if "x" not in names or not names.get("ok", {}).get("finalized"):
                    failures.append(f"list: a dataset missing or the healthy one affected {label}")
            return r

        def ok_detail(label: str = label) -> Any:
            r = client.get("/api/v1/datasets/ok")
            if r.status_code != 200 or not r.json()["finalized"]:
                failures.append(f"healthy detail affected ({r.status_code}) {label}")
            return r

        def append(label: str = label) -> None:
            rec = DatasetRecorder(
                datasets, "x", fps=10, motor_keys=MOTORS, cam_shapes={"wrist": CAM}, mode="append"
            )
            rec.open()
            opened.append(label)
            rec.dataset.writer.stop_image_writer()  # nothing recorded: no finalize, nothing written

        call("list", label, listing)
        call("detail", label, lambda: client.get("/api/v1/datasets/x"))
        call("telemetry", label, lambda: client.get("/api/v1/datasets/x/episodes/0/telemetry"))
        call("healthy", label, ok_detail)
        call("append", label, append)

        def replay(label: str = label) -> None:
            fps, actions = load_episode_actions(datasets / "x", 0)
            # what the replay session runs at: QC saw fps 0 (ZeroDivisionError), 1e300, -5, "30"
            if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 1000 or not actions:
                failures.append(f"replay: accepted fps {fps!r} / {len(actions)} actions {label}")

        call("replay", label, replay)
        if _tree(datasets / "x") != before:
            failures.append(f"files changed {label}")
    assert _tree(datasets / "ok") == ok_before
    print(f"{len(muts)} mutations; append opened for {len(opened)}: {opened[:40]}")
    assert not failures, f"{len(failures)} failures:\n" + "\n".join(failures[:80])
