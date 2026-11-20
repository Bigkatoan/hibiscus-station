"""Field report 0.2.9 → 0.2.10 (Windows, SO-101, 2026-11-19): "cannot see the video and the recorded
episodes" — the dataset detail answered 500 or showed no episode (known defect D-2).

0.2.9 saves episodes off the control loop, so the catalog is read while lerobot writes. Reproduced
against ``hibiscus-station --mock`` (see CHANGELOG 0.2.10):

1. lerobot keeps the rows of ``meta/episodes`` in memory until ``finalize()`` (and flushes them at
   10 episodes into a ParquetWriter that has no footer until it is closed): during a session the
   detail listed no episode, from the 11th episode on it answered 500, and a Station closed
   mid-session (no finalize) left a dataset whose detail and list answered 500 for good.
2. ``size_bytes`` stat'ed every file while the encoder deleted ``images/`` frames: 500.
3. lerobot rewrites ``meta/info.json`` in place: a read in between saw an empty file: 500.
4. A broken telemetry sidecar (crash while writing) failed the detail and the telemetry: 500.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import wait_for

from hibiscus_station.data import datasets as catalog
from hibiscus_station.data.sidecar import episode_file
from hibiscus_station.sessions.recorder import DatasetRecorder
from hibiscus_station.station import Station

MOTORS = [f"{m}.pos" for m in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "gripper")]
CAM = (48, 64, 3)


def _recorder(
    datasets: Path,
    name: str = "ds",
    mode: str = "new",
    motors: list[str] = MOTORS,
    fps: int = 10,
    cam: Any = CAM,
) -> DatasetRecorder:
    rec = DatasetRecorder(
        datasets, name, fps=fps, motor_keys=motors, cam_shapes={"wrist": tuple(cam)}, mode=mode, task="pick"
    )
    rec.open()
    return rec


def _record_episode(rec: DatasetRecorder, frames: int = 6) -> None:
    for i in range(frames):
        obs: dict[str, Any] = {m: float(i) for m in rec.motor_keys}
        obs["wrist"] = np.full(rec.cam_shapes["wrist"], 10 * i, dtype=np.uint8)
        rec.add(obs, {m: float(i) for m in rec.motor_keys}, "pick")
        rec.buffer.add({"t": i / 10, "arm": "follower", "temp_c": {"elbow_flex": 30.0 + i}})


def _save(rec: DatasetRecorder, n: int, frames: int = 6) -> None:
    for _ in range(n):
        _record_episode(rec, frames)
        rec.save_async().result(timeout=60)
        rec.saving = None


def _detail(client: Any, name: str = "ds") -> dict[str, Any]:
    r = client.get(f"/api/v1/datasets/{name}")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_saved_episodes_show_before_the_dataset_is_finalized(station: Station, client: Any) -> None:
    rec = _recorder(station.paths.datasets)
    try:
        _save(rec, 3)
        d = _detail(client)
        assert d["episodes"] == 3 and not d["finalized"]
        assert [(e["index"], e["state"], e["frames"]) for e in d["episode_list"]] == [
            (0, "saved", 6),
            (1, "saved", 6),
            (2, "saved", 6),
        ]
        for i in range(3):
            r = client.get(f"/api/v1/datasets/ds/episodes/{i}/telemetry")
            assert r.status_code == 200 and len(r.json()["t"]) == 6
    finally:
        rec.finalize()
    d = _detail(client)
    assert d["finalized"] and [e["state"] for e in d["episode_list"]] == ["saved"] * 3


def test_the_episode_being_saved_reads_as_saving(station: Station, client: Any) -> None:
    rec = _recorder(station.paths.datasets)
    try:
        _save(rec, 1)
        gate = threading.Event()
        real = rec.dataset.save_episode

        def slow(*a: Any, **kw: Any) -> Any:
            gate.wait(30)
            return real(*a, **kw)

        rec.dataset.save_episode = slow
        _record_episode(rec, 4)
        fut = rec.save_async()
        d = _detail(client)
        assert [(e["index"], e["state"]) for e in d["episode_list"]] == [(0, "saved"), (1, "saving")]
        saving = d["episode_list"][1]
        assert saving["frames"] == 4 and saving["telemetry_lines"] == 0
        assert client.get("/api/v1/datasets/ds/episodes/0/telemetry").status_code == 200
        gate.set()
        fut.result(timeout=60)
        d = _detail(client)
        assert [(e["index"], e["state"], e["frames"]) for e in d["episode_list"]] == [
            (0, "saved", 6),
            (1, "saved", 4),
        ]
    finally:
        gate.set()
        rec.finalize()


def test_more_than_ten_episodes_in_one_session(station: Station, client: Any) -> None:
    """lerobot flushes 10 episode rows into a ParquetWriter that has no footer before finalize."""
    rec = _recorder(station.paths.datasets)
    try:
        _save(rec, 11, frames=3)
        files = list((station.paths.datasets / "ds" / "meta" / "episodes").rglob("*.parquet"))
        assert files, "lerobot flushed the first 10 rows"
        d = _detail(client)
        assert [e["index"] for e in d["episode_list"]] == list(range(11))
        assert {e["state"] for e in d["episode_list"]} == {"saved"}
        assert client.get("/api/v1/datasets").status_code == 200
    finally:
        rec.finalize()
    assert len(_detail(client)["episode_list"]) == 11


CRASH = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
import json
from test_field_0210 import _recorder, _save
kw = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
rec = _recorder(Path(sys.argv[1]), **kw)
_save(rec, int(sys.argv[2]), frames=3)
os._exit(0)  # the console window closed: no finalize, no flush
"""


def _crash_record(datasets: Path, n: int, **kw: Any) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "AMENT_PREFIX_PATH")}
    subprocess.run(  # noqa: S603 - our own test helper
        [sys.executable, "-c", CRASH, str(datasets), str(n), str(Path(__file__).parent), json.dumps(kw)],
        check=True,
        env=env,
        timeout=300,
    )


@pytest.mark.parametrize("n", [3, 12])
def test_a_station_closed_mid_session_leaves_a_readable_page(station: Station, client: Any, n: int) -> None:
    """No finalize: with < 10 episodes meta/episodes is missing, with more it has no footer. The
    page lists every episode the dataset counts; the ones lerobot never wrote say so, one by one."""
    _crash_record(station.paths.datasets, n)
    r = client.get("/api/v1/datasets")
    assert r.status_code == 200, r.text
    (ds,) = r.json()["datasets"]
    assert ds["episodes"] == n and not ds["finalized"]
    d = _detail(client)
    assert [e["index"] for e in d["episode_list"]] == list(range(n))
    assert {e["state"] for e in d["episode_list"]} == {"unreadable"}
    for e in d["episode_list"]:
        assert e["frames"] is None and e["length_s"] is None
        assert e["telemetry_lines"] == 3  # the telemetry sidecar was written: still shown
    assert client.get("/api/v1/datasets/ds/episodes/0/telemetry").status_code == 200


def test_a_file_deleted_while_the_size_is_summed(
    station: Station, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The encoder deletes images/ frames while the catalog sums the dataset size."""
    rec = _recorder(station.paths.datasets)
    try:
        _save(rec, 1)
        frame = station.paths.datasets / "ds" / "images" / "frame-000001.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"x")
        real_stat = os.stat

        def stat(path: Any, *a: Any, **kw: Any) -> os.stat_result:
            if os.fspath(path) == str(frame):  # listed by the walk, gone (Windows: delete pending)
                raise FileNotFoundError(2, "No such file or directory", str(path))
            return real_stat(path, *a, **kw)

        monkeypatch.setattr(os, "stat", stat)
        # 0.2.9 asked is_file() first: it was still there then
        monkeypatch.setattr(Path, "is_file", lambda self: self == frame or os.path.isfile(self))
        assert client.get("/api/v1/datasets").status_code == 200
        assert _detail(client)["size_bytes"] > 0
    finally:
        monkeypatch.undo()
        rec.finalize()


def test_info_json_read_while_lerobot_rewrites_it(
    station: Station, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = _recorder(station.paths.datasets)
    _save(rec, 2)
    rec.finalize()
    info = station.paths.datasets / "ds" / "meta" / "info.json"
    real = Path.read_text
    torn = {"left": 2}

    def read_text(self: Path, *a: Any, **kw: Any) -> str:
        if self == info and torn["left"] > 0:  # lerobot: open("w") then json.dump
            torn["left"] -= 1
            return ""
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", read_text)
    d = _detail(client)
    assert d["episodes"] == 2 and len(d["episode_list"]) == 2
    monkeypatch.undo()
    info.write_text("", encoding="utf-8")  # broken for good: listed, never a 500
    r = client.get("/api/v1/datasets")
    assert r.status_code == 200, r.text
    (ds,) = r.json()["datasets"]
    assert not ds["finalized"] and ds["finalize_reasons"]
    d = _detail(client)  # the rows lerobot wrote still show
    assert d["episodes"] == 0 and [e["state"] for e in d["episode_list"]] == ["saved"] * 2


def test_a_broken_telemetry_sidecar(station: Station, client: Any) -> None:
    rec = _recorder(station.paths.datasets)
    _save(rec, 3)
    rec.finalize()
    root = station.paths.datasets
    episode_file(root, "ds", 0).write_bytes(b"not a gzip file")
    good = gzip.compress(b'{"t":0.0,"arm":"follower","temp_c":{"elbow_flex":31}}\n{"t":0.1,"ar')
    episode_file(root, "ds", 1).write_bytes(good)
    d = _detail(client)
    assert [e["state"] for e in d["episode_list"]] == ["saved"] * 3
    assert [e["telemetry_lines"] for e in d["episode_list"]] == [0, 1, 6]
    r = client.get("/api/v1/datasets/ds/episodes/0/telemetry")
    assert r.status_code == 200 and r.json()["t"] == []
    r = client.get("/api/v1/datasets/ds/episodes/1/telemetry")
    assert r.status_code == 200 and r.json()["t"] == [0.0]


def test_resume_lists_the_old_and_the_new_episodes(station: Station, client: Any) -> None:
    rec = _recorder(station.paths.datasets)
    _save(rec, 2)
    rec.finalize()
    rec = _recorder(station.paths.datasets, mode="append")
    try:
        _save(rec, 2, frames=4)
        d = _detail(client)
        assert [(e["index"], e["frames"]) for e in d["episode_list"]] == [(0, 6), (1, 6), (2, 4), (3, 4)]
        assert [e["state"] for e in d["episode_list"]] == ["saved"] * 4
    finally:
        rec.finalize()
    d = _detail(client)
    assert d["finalized"] and [e["frames"] for e in d["episode_list"]] == [6, 6, 4, 4]


def test_replay_of_an_episode_still_being_written_is_refused_not_a_500(station: Station, client: Any) -> None:
    rec = _recorder(station.paths.datasets)
    try:
        _save(rec, 1)
        from hibiscus_station.sessions.replay import load_episode_actions

        with pytest.raises(Exception) as ei:
            load_episode_actions(station.paths.datasets / "ds", 0)
        assert getattr(ei.value, "code", None) == "busy", repr(ei.value)
    finally:
        rec.finalize()


def test_record_session_detail_during_and_after(connected: Station, client: Any) -> None:
    """The real Record flow (mock arm, camera): every read during the session answers 200 and
    lists each saved episode; after the background finalize everything is there."""
    from hibiscus_station.station import RecordRequest

    st = connected
    problems: list[str] = []
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            try:
                r = client.get("/api/v1/datasets/live")
            except Exception as exc:  # the TestClient re-raises a server error (a 500)
                problems.append(f"500 {exc!r}"[:200])
                continue
            if r.status_code not in (200, 404):
                problems.append(f"{r.status_code} {r.text[:200]}")
            elif r.status_code == 200:
                d = r.json()
                # lerobot counts an episode in info.json before its telemetry is written: that
                # row may still read "saving"; never missing, never unreadable while live
                rows = [e for e in d["episode_list"] if e.get("state", "saved") in ("saved", "saving")]
                if len(rows) < d["episodes"] or len(rows) != len(d["episode_list"]):
                    problems.append(f"episodes={d['episodes']} rows={d['episode_list']}"[:300])
            time.sleep(0.02)

    th = threading.Thread(target=poll, daemon=True)
    th.start()
    try:
        st.start_record(
            RecordRequest(
                dataset="live",
                task="pick",
                fps=15,
                num_episodes=3,
                episode_time_s=0.6,
                reset_time_s=0.1,
                countdown_s=0.2,
            )
        )
        wait_for(lambda: st.owner.state == "idle" and st.owner.last_session_summary is not None, 60)
        wait_for(lambda: catalog.summary(st.paths.datasets, "live")["finalized"], 60)  # type: ignore[index]
    finally:
        stop.set()
        th.join(5)
    assert not problems, problems[:5]
    d = _detail(client, "live")
    assert d["episodes"] == 3 and [e["state"] for e in d["episode_list"]] == ["saved"] * 3
    assert json.dumps(d)


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.mark.parametrize("n", [3, 12])
def test_recording_more_into_a_dataset_a_crash_left_unfinalized(station: Station, n: int) -> None:
    """LeRobotDataset.resume raised ArrowInvalid / FileNotFoundError (a 500). The episode rows were
    in memory only and the data file has no footer: no safe repair. Refused with 409
    dataset_not_finalized, and not one byte of the customer's dataset changes."""
    from hibiscus_station.errors import StationError

    _crash_record(station.paths.datasets, n)
    before = _tree(station.paths.datasets)
    rec = DatasetRecorder(
        station.paths.datasets, "ds", fps=10, motor_keys=MOTORS, cam_shapes={"wrist": CAM}, mode="append"
    )
    with pytest.raises(StationError) as ei:
        rec.open()
    assert ei.value.code == "dataset_not_finalized", repr(ei.value)
    assert ei.value.params["dataset"] == "ds" and ei.value.params["reasons"]
    assert _tree(station.paths.datasets) == before


@pytest.mark.parametrize("n", [2, 12])  # 0.2.9: 502 "bus_error" (resume asked the HF Hub), 500
def test_record_append_into_an_unfinalized_dataset_answers_409(
    connected: Station, client: Any, n: int
) -> None:
    """The customer's flow: the console closed mid-session, then Record → "Add to an existing
    dataset" on the same robot (same joints and camera as the crashed dataset)."""
    st = connected
    assert st.owner.follower is not None
    motors = [f"{m}.pos" for m in st.owner.follower.bus.motors]
    (shape,) = st.hub.shapes().values()
    _crash_record(st.paths.datasets, n, motors=motors, fps=15, cam=list(shape))
    before = _tree(st.paths.datasets / "ds")
    r = client.post(
        "/api/v1/sessions/record",
        json={"dataset": "ds", "mode": "append", "task": "pick", "fps": 15, "countdown_s": 0},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "dataset_not_finalized" and body["params"]["dataset"] == "ds", body
    assert _tree(st.paths.datasets / "ds") == before
    assert st.owner.state == "idle"


# --------------------------------------------------------------------------- QC 0.2.10 round 1
def _finalized(datasets: Path, n: int = 2) -> Path:
    rec = _recorder(datasets)
    _save(rec, n)
    rec.finalize()
    return datasets / "ds" / "meta" / "info.json"


def _set_info(info: Path, **kw: Any) -> None:
    data = json.loads(info.read_text(encoding="utf-8"))
    data.update(kw)
    info.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("total", [10**9, 10**8, 2**62, -5, "3", True, 1.5, None])
def test_a_damaged_episode_count_never_allocates_by_it(station: Station, client: Any, total: Any) -> None:
    """QH-1: total_episodes 1e9 in info.json made the detail build set(range(1e9)): the Station
    was OOM-killed. Rows are bounded by what is on disk; an absurd count is reported, not used."""
    import tracemalloc

    info = _finalized(station.paths.datasets)
    _set_info(info, total_episodes=total)
    tracemalloc.start()
    t0 = time.monotonic()
    try:
        r = client.get("/api/v1/datasets/ds")
        lst = client.get("/api/v1/datasets")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert time.monotonic() - t0 < 5
    assert peak < 50 * 2**20, peak
    assert r.status_code == 200 and lst.status_code == 200, (r.text, lst.text)
    d = r.json()
    assert len(d["episode_list"]) <= 3
    assert [e["state"] for e in d["episode_list"][:2]] == ["saved", "saved"]
    if not (isinstance(total, int) and not isinstance(total, bool) and 0 <= total < 10**9):
        assert d["episodes"] == 0 and not d["finalized"]
        assert any("total_episodes" in x for x in d["finalize_reasons"]), d["finalize_reasons"]


def _append(datasets: Path) -> DatasetRecorder:
    return DatasetRecorder(
        datasets, "ds", fps=10, motor_keys=MOTORS, cam_shapes={"wrist": CAM}, mode="append", task="pick"
    )


BROKEN_INFO = {
    "empty": "",
    "cut_short": '{"codebase_version": "v3.0", "fps": 10, "feat',
    "list": "[]",
    "action_null": None,  # features.action: null
    "features_list": None,  # features: []
    "shape_text": None,  # features.action.shape: "abc"
    "fps_text": None,  # fps: "fast"
    "total_negative": None,  # total_episodes: -1
}


@pytest.mark.parametrize("case", list(BROKEN_INFO))
def test_append_into_a_dataset_with_a_broken_info_json_is_a_clean_4xx(station: Station, case: str) -> None:
    """QH-2: 500 (JSONDecodeError / AttributeError in open()) on 0.2.9 and 0.2.10. Now
    dataset_unreadable (409), the Record page offers a new dataset, and no file changes."""
    from hibiscus_station.errors import STATUS, StationError

    info = _finalized(station.paths.datasets)
    text = BROKEN_INFO[case]
    if text is not None:
        info.write_text(text, encoding="utf-8")
    else:
        data = json.loads(info.read_text(encoding="utf-8"))
        if case == "action_null":
            data["features"]["action"] = None
        elif case == "features_list":
            data["features"] = []
        elif case == "shape_text":
            data["features"]["action"]["shape"] = "abc"
        elif case == "fps_text":
            data["fps"] = "fast"
        elif case == "total_negative":
            data["total_episodes"] = -1
        info.write_text(json.dumps(data), encoding="utf-8")
    before = _tree(station.paths.datasets)
    with pytest.raises(StationError) as ei:
        _append(station.paths.datasets).open()
    assert ei.value.code == "dataset_unreadable", repr(ei.value)
    assert STATUS[ei.value.code] == 409 and ei.value.params["dataset"] == "ds"
    assert _tree(station.paths.datasets) == before


def _deny(monkeypatch: pytest.MonkeyPatch, inside: Path, *, writes_only: bool) -> None:
    """The OS refuses access to ``inside`` (a file, or everything under a folder) with
    PermissionError, as chmod 000 / a read-only folder does on POSIX and an ACL does on Windows.
    Patched at the os / io layer every Python file access goes through, so the product code runs
    unchanged on every OS (NFR-18: no "POSIX permissions" skip on Windows)."""
    import builtins
    import io

    def norm(path: Any) -> str:  # realpath: Windows 8.3 short names (RUNNER~1) and symlinks
        return os.path.normcase(os.path.realpath(os.fsdecode(path)))

    root = norm(inside)

    def hit(path: Any) -> bool:
        if isinstance(path, int):
            return False
        p = norm(path)
        return p == root or p.startswith(root + os.sep)

    def refuse(path: Any) -> PermissionError:
        return PermissionError(13, "Permission denied", os.fsdecode(path))

    real_open, real_os_open, real_mkdir = io.open, os.open, os.mkdir

    def fake_open(file: Any, mode: str = "r", *a: Any, **kw: Any) -> Any:
        writing = any(c in mode for c in "wax+")
        if hit(file) and (writing or not writes_only):
            raise refuse(file)
        return real_open(file, mode, *a, **kw)

    def fake_os_open(path: Any, flags: int, *a: Any, **kw: Any) -> int:
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        if hit(path) and (writing or not writes_only):
            raise refuse(path)
        return real_os_open(path, flags, *a, **kw)

    def fake_mkdir(path: Any, *a: Any, **kw: Any) -> None:
        if hit(path) and norm(path) != root:
            raise refuse(path)
        real_mkdir(path, *a, **kw)

    monkeypatch.setattr(io, "open", fake_open)
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(os, "open", fake_os_open)
    monkeypatch.setattr(os, "mkdir", fake_mkdir)


def _append_to_unreadable_info(st: Station, client: Any, deny: Any) -> Any:
    motors = [f"{m}.pos" for m in st.owner.follower.bus.motors]  # type: ignore[union-attr]
    (shape,) = st.hub.shapes().values()
    rec = _recorder(st.paths.datasets, motors=motors, fps=15, cam=shape)
    _save(rec, 1)
    rec.finalize()
    info = st.paths.datasets / "ds" / "meta" / "info.json"
    with deny(info):
        return client.post(
            "/api/v1/sessions/record",
            json={"dataset": "ds", "mode": "append", "task": "pick", "fps": 15, "countdown_s": 0},
        )


def test_an_unreadable_info_json_is_a_dataset_error_not_a_motor_error(
    connected: Station, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QH-5: an info.json the OS refuses to open, then append: 502 bus_error ("A motor did not
    answer"). Runs on every OS: the refusal is simulated (see _deny)."""

    @contextlib.contextmanager
    def deny(path: Path) -> Iterator[None]:
        with monkeypatch.context() as m:
            _deny(m, path, writes_only=False)
            yield

    r = _append_to_unreadable_info(connected, client, deny)
    assert r.status_code == 409 and r.json()["code"] == "dataset_unreadable", r.text
    assert "cannot be opened" in r.json()["detail"], r.text  # the refusal was hit, not a later check
    assert connected.owner.state == "idle"


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions")
def test_an_unreadable_info_json_real_chmod(connected: Station, client: Any) -> None:
    """The same as above with a real chmod 000 (POSIX, not root): the OS error itself."""

    @contextlib.contextmanager
    def deny(path: Path) -> Iterator[None]:
        path.chmod(0)
        try:
            yield
        finally:
            path.chmod(0o644)

    r = _append_to_unreadable_info(connected, client, deny)
    assert r.status_code == 409 and r.json()["code"] == "dataset_unreadable", r.text
    assert connected.owner.state == "idle"


def test_a_datasets_folder_that_cannot_be_written_is_not_a_motor_error(
    connected: Station, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """QH-5, the same class on the "new dataset" path: a datasets folder the OS refuses to write
    into. Runs on every OS: the refusal is simulated (see _deny)."""
    st = connected
    st.paths.datasets.mkdir(parents=True, exist_ok=True)
    with monkeypatch.context() as m:
        _deny(m, st.paths.datasets, writes_only=True)
        r = client.post(
            "/api/v1/sessions/record",
            json={"dataset": "ro", "task": "pick", "fps": 15, "countdown_s": 0},
        )
    assert r.status_code == 409 and r.json()["code"] == "dataset_io_error", r.text
    assert st.owner.state == "idle"
    assert not (st.paths.datasets / "ro").exists()


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="POSIX permissions")
def test_a_datasets_folder_that_cannot_be_written_real_chmod(connected: Station, client: Any) -> None:
    """The same as above with a real read-only folder (POSIX chmod 0o500, not root)."""
    st = connected
    st.paths.datasets.mkdir(parents=True, exist_ok=True)
    st.paths.datasets.chmod(0o500)
    try:
        r = client.post(
            "/api/v1/sessions/record",
            json={"dataset": "ro", "task": "pick", "fps": 15, "countdown_s": 0},
        )
    finally:
        st.paths.datasets.chmod(0o755)
    assert r.status_code == 409 and r.json()["code"] == "dataset_io_error", r.text
    assert st.owner.state == "idle"


def test_replay_of_a_crash_left_episode_says_unreadable_not_saving(station: Station, client: Any) -> None:
    """QH-4: a crash-left dataset answered 409 busy "still being saved; try again when the dataset
    is finalized", which never happens."""
    from hibiscus_station.errors import StationError
    from hibiscus_station.sessions.replay import load_episode_actions

    _crash_record(station.paths.datasets, 3)
    for ep in (0, 99):
        with pytest.raises(StationError) as ei:
            load_episode_actions(station.paths.datasets / "ds", ep)
        assert ei.value.code == "dataset_unreadable", repr(ei.value)
        assert "try again" not in str(ei.value)


@pytest.mark.parametrize("text", ["", "[]", '{"features": {"action": null}, "fps": 10}'])
def test_replay_with_a_broken_info_json_is_a_clean_4xx(station: Station, text: str) -> None:
    from hibiscus_station.errors import StationError
    from hibiscus_station.sessions.replay import load_episode_actions

    info = _finalized(station.paths.datasets)
    info.write_text(text, encoding="utf-8")
    with pytest.raises(StationError) as ei:
        load_episode_actions(station.paths.datasets / "ds", 0)
    assert ei.value.code == "dataset_unreadable", repr(ei.value)
