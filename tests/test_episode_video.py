"""F-72 / CR-1 (customer change request 2026-11-19): the camera video of each recorded episode.

LeRobot v3 concatenates many episodes into one mp4 per camera; ``meta/episodes`` gives each
episode's span in that file. Station records AV1 (LeRobot's default, ``libsvtav1``), which a stock
Windows Edge cannot decode, so ``GET .../videos/{camera}?format=`` serves the episode cut out of the
file (``source``, packets copied) or re-encoded to ``vp9`` (WebM) / ``h264`` (mp4), with HTTP Range
(ADR-14). The datasets here are real LeRobot datasets written by Station's own recorder: one through
a full mock record session, one by the recorder directly with a known picture per episode.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import connect_calibrated, mock_profile, wait_for

from hibiscus_station.station import RecordRequest, Station

API = "/api/v1"
#: grey level of episode k in the ``multi`` dataset (episode k shows a flat picture of this level)
LEVEL = (30, 120, 210)
FRAMES = (8, 12, 16)  # frames of each episode at 10 fps


def _decode(data: bytes) -> list[np.ndarray]:
    import av

    with av.open(io.BytesIO(data)) as c:
        return [f.to_ndarray(format="gray") for f in c.decode(c.streams.video[0])]


def _times(data: bytes) -> tuple[list[float], float]:
    """Each frame's time in seconds and the container's duration."""
    import av

    with av.open(io.BytesIO(data)) as c:
        ts = [float(f.pts * f.time_base) for f in c.decode(c.streams.video[0]) if f.pts is not None]
        return ts, (c.duration or 0) / 1e6


def _codec(data: bytes) -> str:
    import av

    with av.open(io.BytesIO(data)) as c:
        return str(c.streams.video[0].codec_context.name)


def make_multi(st: Station, name: str = "multi") -> Path:
    """Three episodes, two cameras, each episode a flat grey of its own level: LeRobot puts all of
    them in one ``file-000.mp4`` per camera."""
    from hibiscus_station.sessions.recorder import DatasetRecorder

    motors = ["shoulder_pan.pos", "gripper.pos"]
    rec = DatasetRecorder(
        st.paths.datasets,
        name,
        fps=10,
        motor_keys=motors,
        cam_shapes={"wrist": (48, 64, 3), "front": (48, 64, 3)},
        task="t",
    )
    rec.open()
    for ep, n in enumerate(FRAMES):
        for f in range(n):
            img = np.full((48, 64, 3), LEVEL[ep], dtype=np.uint8)
            rec.add(
                {**{m: float(f) for m in motors}, "wrist": img, "front": img}, dict.fromkeys(motors, 0.0), "t"
            )
        rec.save_async().result()
    rec.finalize()
    return st.paths.datasets / name


@pytest.fixture
def multi(station: Station) -> Path:
    return make_multi(station)


@pytest.fixture
def recorded(station: Station) -> Station:
    """Two episodes through a real (mock hardware) record session with two cameras."""
    connect_calibrated(station, mock_profile(cameras=2))
    station.start_record(
        RecordRequest(
            dataset="flow",
            task="Pick the cube",
            num_episodes=2,
            episode_time_s=0.8,
            reset_time_s=0.2,
            fps=15,
            countdown_s=0.2,
        )
    )
    wait_for(lambda: station.owner.state == "idle" and station.owner.last_session_summary is not None, 30)
    return station


def test_a_recorded_episode_lists_every_camera_with_its_codec(client: Any, recorded: Station) -> None:
    r = client.get(f"{API}/datasets/flow/episodes/0/videos")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataset"] == "flow" and body["episode"] == 0 and body["fps"] == 15
    cams = {c["camera"]: c for c in body["cameras"]}
    assert set(cams) == {"wrist", "front"}
    for c in cams.values():
        # LeRobot 0.7.1's default encoder, unchanged by Station (ADR-14)
        assert c["codec"] == "av1"
        assert c["mime"] == 'video/mp4; codecs="av01.0.05M.08"'
        assert c["error"] is None and c["formats"] == ["source", "vp9", "h264"]
        assert c["duration_s"] == pytest.approx(body["length_s"], abs=1 / 15)
    # every format of every camera decodes to the episode's frames
    detail = client.get(f"{API}/datasets/flow").json()
    frames = detail["episode_list"][1]["frames"]
    for cam in cams:
        for fmt, mt in (("source", "video/mp4"), ("vp9", "video/webm"), ("h264", "video/mp4")):
            v = client.get(f"{API}/datasets/flow/episodes/1/videos/{cam}", params={"format": fmt})
            assert v.status_code == 200, (cam, fmt, v.text)
            assert v.headers["content-type"] == mt
            assert len(_decode(v.content)) == frames, (cam, fmt)


def test_each_episode_is_cut_from_the_shared_file(client: Any, multi: Path) -> None:
    import pyarrow.parquet as pq

    [meta] = (multi / "meta" / "episodes").rglob("*.parquet")
    files = pq.read_table(meta, columns=["videos/observation.images.front/file_index"]).to_pydict()
    assert set(files["videos/observation.images.front/file_index"]) == {0}  # one file, three episodes
    assert len(list((multi / "videos" / "observation.images.front").rglob("*.mp4"))) == 1
    for ep in range(3):
        for fmt, codec in (("source", "libdav1d"), ("vp9", "vp9"), ("h264", "h264")):
            v = client.get(f"{API}/datasets/multi/episodes/{ep}/videos/front?format={fmt}")
            assert v.status_code == 200, v.text
            assert _codec(v.content).startswith(codec[:3]) or codec in _codec(v.content)
            pics = _decode(v.content)
            assert len(pics) == FRAMES[ep], (ep, fmt)
            # the browser's clock: frame k at k / fps from 0, and the file lasts the whole episode
            ts, duration = _times(v.content)
            assert ts == pytest.approx([k / 10 for k in range(FRAMES[ep])], abs=0.002), (ep, fmt, ts)
            assert duration == pytest.approx(FRAMES[ep] / 10, abs=0.06), (ep, fmt, duration)
            # the first and the last frame are this episode's picture, not a neighbour's
            assert abs(float(pics[0].mean()) - LEVEL[ep]) < 12, (ep, fmt, pics[0].mean())
            assert abs(float(pics[-1].mean()) - LEVEL[ep]) < 12, (ep, fmt, pics[-1].mean())


def test_range_requests(client: Any, multi: Path) -> None:
    url = f"{API}/datasets/multi/episodes/2/videos/wrist?format=vp9"
    full = client.get(url)
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    size = int(full.headers["content-length"])
    assert size == len(full.content) > 200
    part = client.get(url, headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 0-99/{size}"
    assert part.content == full.content[:100]
    tail = client.get(url, headers={"Range": "bytes=-50"})
    assert tail.status_code == 206 and tail.content == full.content[-50:]
    mid = client.get(url, headers={"Range": f"bytes=100-{size + 1000}"})
    assert mid.status_code == 206 and mid.content == full.content[100:]
    outside = client.get(url, headers={"Range": f"bytes={size + 10}-{size + 20}"})
    assert outside.status_code == 416


def test_a_cut_is_made_once_and_remade_when_the_file_changes(
    client: Any, multi: Path, station: Station
) -> None:
    url = f"{API}/datasets/multi/episodes/0/videos/front?format=h264"
    assert client.get(url).status_code == 200
    cache = station.paths.datasets / "multi.hibiscus" / "video-cache" / "front"
    [cut] = list(cache.glob("episode_000000.h264.*.mp4"))
    stamp = cut.stat().st_mtime_ns
    time.sleep(0.02)
    assert client.get(url).status_code == 200
    assert cut.stat().st_mtime_ns == stamp  # served from the cache
    # the LeRobot root is untouched: the cache lives in the sidecar
    assert not any("video-cache" in str(p) for p in multi.rglob("*"))
    src = multi / "videos" / "observation.images.front" / "chunk-000" / "file-000.mp4"
    src.touch()
    import os

    os.utime(src, ns=(stamp + 10**9, stamp + 10**9))
    assert client.get(url).status_code == 200
    [again] = list(cache.glob("episode_000000.h264.*.mp4"))
    assert again.with_name(again.name + ".json").is_file()  # its stamp (QV-2), the old one is gone
    assert len(list(cache.glob("episode_000000.h264.*.json"))) == 1
    assert again.name != cut.name  # a new key: the stale cut was replaced, not kept beside it


def test_a_missing_camera_file_is_reported_per_camera(client: Any, multi: Path) -> None:
    src = multi / "videos" / "observation.images.front" / "chunk-000" / "file-000.mp4"
    src.unlink()
    body = client.get(f"{API}/datasets/multi/episodes/1/videos").json()
    cams = {c["camera"]: c for c in body["cameras"]}
    assert cams["front"]["error"] == "video_missing" and cams["front"]["formats"] == []
    assert cams["wrist"]["error"] is None  # the other camera still plays
    r = client.get(f"{API}/datasets/multi/episodes/1/videos/front")
    assert r.status_code == 404 and r.json()["code"] == "video_missing"
    assert r.json()["params"] == {"camera": "front", "episode": 1}
    assert client.get(f"{API}/datasets/multi/episodes/1/videos/wrist").status_code == 200
    # a camera the dataset never had, an episode it never had
    r = client.get(f"{API}/datasets/multi/episodes/1/videos/side")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = client.get(f"{API}/datasets/multi/episodes/9/videos")
    assert r.status_code == 404 and r.json()["code"] == "not_found"


def test_an_unreadable_video_is_video_unavailable(client: Any, multi: Path) -> None:
    src = multi / "videos" / "observation.images.wrist" / "chunk-000" / "file-000.mp4"
    src.write_bytes(b"not an mp4 at all")
    for fmt in ("source", "vp9", "h264"):
        r = client.get(f"{API}/datasets/multi/episodes/0/videos/wrist?format={fmt}")
        assert r.status_code == 422 and r.json()["code"] == "video_unavailable", r.text


def test_a_dataset_being_recorded_answers_episode_saving(client: Any, station: Station) -> None:
    connect_calibrated(station, mock_profile(cameras=2, size=(64, 48)))
    station.start_record(RecordRequest(dataset="more", task="t", num_episodes=1, episode_time_s=30, fps=10))
    try:
        wait_for(lambda: station.owner.state == "recording", 10)
        wait_for(
            lambda: station.owner.session is not None and station.owner.session.episode.phase == "episode", 10
        )
        time.sleep(0.5)  # frames of episode 1: stop keeps them
        for url in (
            f"{API}/datasets/more/episodes/0/videos",
            f"{API}/datasets/more/episodes/0/videos/front",
            f"{API}/datasets/more/episodes/3/videos/front?format=vp9",
        ):
            r = client.get(url)
            assert r.status_code == 409, r.text
            assert r.json()["code"] == "episode_saving"
            assert r.json()["params"]["dataset"] == "more"
    finally:
        station.owner.call("control", action="stop")
        wait_for(lambda: station.owner.state == "idle", 30)
    assert client.get(f"{API}/datasets/more/episodes/0/videos/front").status_code == 200


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("/datasets/..%2Fmulti/episodes/0/videos", (404, 422)),
        ("/datasets/multi/episodes/0/videos/..%2F..%2Fmeta", (404, 422)),
        ("/datasets/multi/episodes/0/videos/..", (404, 422)),
        ("/datasets/multi/episodes/0/videos/front%2F..%2F..%2Finfo.json", (404, 422)),
        ("/datasets/multi/episodes/-1/videos/front", (422,)),
        ("/datasets/multi/episodes/x/videos/front", (422,)),
        ("/datasets/multi/episodes/0/videos/front?format=../../x", (422,)),
        ("/datasets/MULTI/episodes/0/videos/front", (422,)),
    ],
)
def test_names_cannot_leave_the_dataset(client: Any, multi: Path, url: str, status: tuple[int, ...]) -> None:
    r = client.get(API + url)
    assert r.status_code in status, (url, r.status_code, r.text)


def test_a_tampered_video_path_cannot_leave_the_dataset(client: Any, multi: Path, tmp_path: Path) -> None:
    secret = tmp_path / "outside" / "observation.images.front" / "chunk-000" / "file-000.mp4"
    secret.parent.mkdir(parents=True)
    src = multi / "videos" / "observation.images.front" / "chunk-000" / "file-000.mp4"
    secret.write_bytes(src.read_bytes())
    info_path = multi / "meta" / "info.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    hops = "../" * (len(multi.relative_to(tmp_path).parts))
    info["video_path"] = hops + "outside/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
    info_path.write_text(json.dumps(info), encoding="utf-8")
    # the shared info.json validator (hotfix 0.2.10, M1-2) refuses a template that leaves the root
    for url in (f"{API}/datasets/multi/episodes/0/videos", f"{API}/datasets/multi/episodes/0/videos/front"):
        r = client.get(url)
        assert r.status_code == 409 and r.json()["code"] == "dataset_unreadable", r.text
    # a symlink out of the dataset passes the template check: the path fence still holds
    info["video_path"] = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
    info_path.write_text(json.dumps(info), encoding="utf-8")
    cam = multi / "videos" / "observation.images.front"
    real = cam.with_name("front.real")
    cam.rename(real)
    try:
        cam.symlink_to(secret.parent.parent, target_is_directory=True)
    except OSError:  # Windows without the symlink privilege: the template check above is the test
        return
    body = client.get(f"{API}/datasets/multi/episodes/0/videos").json()
    front = next(c for c in body["cameras"] if c["camera"] == "front")
    assert front["error"] == "video_unavailable"
    r = client.get(f"{API}/datasets/multi/episodes/0/videos/front")
    assert r.status_code == 422 and r.json()["code"] == "video_unavailable"


def test_videos_need_the_session_cookie_or_token(client: Any, multi: Path) -> None:
    from fastapi.testclient import TestClient

    anon = TestClient(client.app, base_url=str(client.base_url))
    r = anon.get(f"{API}/datasets/multi/episodes/0/videos/front")
    assert r.status_code == 401 and r.json()["code"] == "unauthenticated"
    # the browser's <video> sends the HttpOnly session cookie, no header
    auth = client.auth_obj
    anon.cookies.set("hst", auth.new_cookie())
    assert anon.get(f"{API}/datasets/multi/episodes/0/videos/front").status_code == 200


def test_episode_telemetry_carries_the_frame_index_for_the_video_cursor(
    client: Any, recorded: Station
) -> None:
    tel = client.get(f"{API}/datasets/flow/episodes/0/telemetry").json()
    assert len(tel["frame_index"]) == len(tel["t"]) > 0
    fi = [f for f in tel["frame_index"] if f is not None]
    assert fi == sorted(fi) and fi[0] >= 0


def test_an_episode_whose_metadata_was_never_written_is_404_never_500(client: Any, multi: Path) -> None:
    """Hotfix 0.2.10 (D-2): a Station closed before ``finalize`` leaves a ``meta/episodes`` parquet
    without a footer, and LeRobot may be rewriting ``meta/info.json``. The viewer answers a clear
    code; episodes in closed files still play."""
    (multi / "meta" / "episodes" / "chunk-000" / "file-001.parquet").write_bytes(b"PAR1 no footer")
    assert client.get(f"{API}/datasets/multi/episodes/1/videos/front").status_code == 200
    r = client.get(f"{API}/datasets/multi/episodes/3/videos")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    (multi / "meta" / "info.json").write_text("", encoding="utf-8")
    r = client.get(f"{API}/datasets/multi/episodes/1/videos")
    assert r.status_code == 409 and r.json()["code"] == "dataset_unreadable"


def _set_info(multi: Path, change: Any) -> None:
    path = multi / "meta" / "info.json"
    info = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(change(info)), encoding="utf-8")


@pytest.mark.parametrize(
    "change",
    [
        lambda i: [i],  # not an object
        lambda i: {**i, "fps": "fast"},
        lambda i: {**i, "fps": 0},
        lambda i: {**i, "features": "cameras"},
        lambda i: {**i, "features": {**i["features"], "observation.images.front": ["video"]}},
        lambda i: {**i, "video_path": 7},
        lambda i: {**i, "total_episodes": 10**12},
        lambda i: {k: v for k, v in i.items() if k != "codebase_version"},
    ],
    ids=[
        "list",
        "fps_text",
        "fps_zero",
        "features_text",
        "feature_list",
        "video_path_int",
        "huge",
        "no_version",
    ],
)
def test_an_unreadable_dataset_is_a_clean_4xx_on_every_video_endpoint(
    client: Any, multi: Path, change: Any
) -> None:
    """Merge of F-72 with hotfix 0.2.10: the video endpoints read ``meta/info.json`` through the
    one validator of list, detail, append and replay (``data/info.py``), so a damaged dataset is
    409 ``dataset_unreadable`` with its reasons, never a 500."""
    _set_info(multi, change)
    urls = [f"{API}/datasets/multi/episodes/0/videos"]
    urls += [f"{API}/datasets/multi/episodes/0/videos/front?format={f}" for f in ("source", "vp9", "h264")]
    for url in urls:
        r = client.get(url)
        assert r.status_code == 409, (url, r.status_code, r.text)
        body = r.json()
        assert body["code"] == "dataset_unreadable" and body["params"]["reasons"], body


def test_odd_but_valid_camera_metadata_is_never_a_500(client: Any, multi: Path) -> None:
    """Values info_problems leaves alone (a camera's ``info`` block, the template's extra fields)."""

    def odd(i: dict[str, Any]) -> dict[str, Any]:
        i["features"]["observation.images.front"]["info"] = ["av1"]
        i["features"]["observation.images.wrist"]["info"] = {"video.codec": ["av1"]}
        return i

    _set_info(multi, odd)
    body = client.get(f"{API}/datasets/multi/episodes/0/videos").json()
    assert {c["camera"]: c["codec"] for c in body["cameras"]} == {"front": None, "wrist": None}
    _set_info(multi, lambda i: {**i, "video_path": "videos/{video_key}/{chunk_index}/{nope}.mp4"})
    body = client.get(f"{API}/datasets/multi/episodes/0/videos").json()
    assert {c["error"] for c in body["cameras"]} == {"video_unavailable"}
    r = client.get(f"{API}/datasets/multi/episodes/0/videos/front")
    assert r.status_code == 422 and r.json()["code"] == "video_unavailable"


def test_a_replay_of_the_dataset_does_not_block_its_videos(client: Any, recorded: Station) -> None:
    """QV-1 (QC F072 r1): a replay only reads the dataset, so its videos play; only a session that
    writes to the dataset (record, run-with-recording) answers 409 ``episode_saving``."""
    from hibiscus_station.station import ReplayRequest

    st = recorded
    st.start_replay(ReplayRequest(dataset="flow", episode=0))
    try:
        wait_for(lambda: st.owner.state == "replaying", 10)
        assert st.owner.session is not None and st.owner.session.dataset == "flow"
        assert client.get(f"{API}/datasets/flow/episodes/1/videos").status_code == 200
        r = client.get(f"{API}/datasets/flow/episodes/1/videos/front?format=source")
        assert r.status_code == 200, r.text
    finally:
        st.owner.call("control", action="stop")
        wait_for(lambda: st.owner.state == "idle", 20)


@pytest.mark.parametrize("damage", ["truncated", "empty", "garbage_same_size", "no_stamp"])
@pytest.mark.parametrize("fmt", ["source", "vp9", "h264"])
def test_a_damaged_cut_in_the_cache_is_cut_again(
    client: Any, multi: Path, station: Station, fmt: str, damage: str
) -> None:
    """QV-2 (QC F072 r1): a cut damaged on disk is never served; it is cut again (all frames)."""
    url = f"{API}/datasets/multi/episodes/2/videos/front?format={fmt}"
    good = client.get(url)
    assert good.status_code == 200 and len(_decode(good.content)) == FRAMES[2]
    cache = station.paths.datasets / "multi.hibiscus" / "video-cache" / "front"
    [cut] = [p for p in cache.glob(f"episode_000002.{fmt}.*") if not p.name.endswith(".json")]
    data = cut.read_bytes()
    if damage == "truncated":
        cut.write_bytes(data[: len(data) // 3])
    elif damage == "empty":
        cut.write_bytes(b"")
    elif damage == "garbage_same_size":
        cut.write_bytes(bytes(len(data)))
    else:
        cut.with_name(cut.name + ".json").unlink()
    again = client.get(url)
    assert again.status_code == 200
    assert len(_decode(again.content)) == FRAMES[2], (fmt, damage)
    # ranged reads of the healthy cut keep working
    part = client.get(url, headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and part.content == again.content[:100]


def test_a_dataset_recorded_without_video_says_so(client: Any, station: Station) -> None:
    """QV-5 (QC F072 r1): "Mã hoá video" off stores images, not video: the reason is ``no_video``
    ("This dataset has no video"), not "cannot be read"."""
    from hibiscus_station.sessions.recorder import DatasetRecorder

    motors = ["shoulder_pan.pos"]
    rec = DatasetRecorder(
        station.paths.datasets,
        "imgs",
        fps=10,
        motor_keys=motors,
        cam_shapes={"front": (48, 64, 3)},
        use_video=False,
    )
    rec.open()
    for _ in range(5):
        rec.add(
            {"shoulder_pan.pos": 0.0, "front": np.zeros((48, 64, 3), np.uint8)},
            {"shoulder_pan.pos": 0.0},
            "t",
        )
    rec.save_async().result()
    rec.finalize()
    body = client.get(f"{API}/datasets/imgs/episodes/0/videos").json()
    assert [(c["camera"], c["error"], c["formats"]) for c in body["cameras"]] == [("front", "no_video", [])]
    r = client.get(f"{API}/datasets/imgs/episodes/0/videos/front")
    assert r.status_code == 404 and r.json()["code"] == "no_video"
