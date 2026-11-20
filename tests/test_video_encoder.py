"""ADR-15: LeRobot's SVT-AV1 episode encode runs in a worker process on macOS.

CI macOS died with SIGTRAP on 4 of 7 full runs of the M1 branch (and 6 of 10 repro jobs): SVT-AV1
3.0.0 (PyAV 15.1 wheels) frees libdispatch semaphores that are still in use when the encoder is torn
down, and libdispatch stops the process ("BUG IN CLIENT OF LIBDISPATCH: Semaphore object deallocated
while in use"; stack PyAV Stream dealloc -> svt_av1_enc_deinit_handle -> svt_destroy_semaphore ->
dispatch_release). Linux and Windows do not check, so these tests force the isolation to exercise it
everywhere: the encode happens in another process, a worker killed by that same signal is replaced
and the episode is encoded again, and the dataset is the one LeRobot would have written.
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from hibiscus_station.sessions import video_encoder
from hibiscus_station.sessions.recorder import DatasetRecorder


@pytest.fixture
def isolated_encoder() -> Iterator[None]:
    video_encoder.shutdown()
    assert video_encoder.isolate_video_encoding(force=True)
    yield
    video_encoder.shutdown()
    if sys.platform != "darwin":
        video_encoder.restore()


def _record(root: Path, name: str, episodes: int = 2, frames: int = 6) -> Path:
    rec = DatasetRecorder(
        root, name, fps=10, motor_keys=["shoulder_pan.pos"], cam_shapes={"front": (48, 64, 3)}, task="t"
    )
    rec.open()
    for ep in range(episodes):
        for f in range(frames):
            img = np.full((48, 64, 3), 40 * (ep + 1), dtype=np.uint8)
            img[:, f] = 255
            rec.add({"shoulder_pan.pos": float(f), "front": img}, {"shoulder_pan.pos": 0.0}, "t")
        rec.save_async().result(timeout=120)
    rec.finalize()
    return root / name


def _frames(path: Path) -> int:
    import av

    with av.open(str(path)) as c:
        return sum(1 for _ in c.decode(c.streams.video[0]))


def test_lerobot_still_calls_the_encode_function_station_isolates() -> None:
    """The seam (ADR-3 pin): a LeRobot upgrade that moves it must fail here, not crash a Mac."""
    from lerobot.datasets import dataset_writer

    src = inspect.getsource(dataset_writer.DatasetWriter._encode_temporary_episode_video)
    assert "_encode_video_worker(" in src
    params = list(
        inspect.signature(video_encoder._original or dataset_writer._encode_video_worker).parameters
    )
    assert params[:4] == ["video_key", "episode_index", "root", "fps"]


def test_isolation_is_on_by_default_only_on_macos() -> None:
    on = video_encoder.isolate_video_encoding()
    try:
        assert on is (sys.platform == "darwin")
    finally:
        if sys.platform != "darwin":
            video_encoder.restore()


def test_episodes_are_encoded_in_another_process(tmp_path: Path, isolated_encoder: None) -> None:
    root = _record(tmp_path, "iso")
    pool = video_encoder._pool
    assert pool is not None
    workers = [p.pid for p in pool._processes.values()]
    assert workers and os.getpid() not in workers
    files = sorted((root / "videos" / "observation.images.front").rglob("*.mp4"))
    assert len(files) == 1 and _frames(files[0]) == 12  # both episodes, every frame
    from lerobot.datasets import LeRobotDataset

    ds = LeRobotDataset("local/iso", root=root)
    assert ds.meta.total_episodes == 2 and ds.num_frames == 12
    assert tuple(ds[11]["observation.images.front"].shape) == (3, 48, 64)


def test_a_worker_killed_by_sigtrap_is_replaced_and_the_episode_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The macOS trap, simulated: the first worker kills itself with SIGTRAP mid-encode."""
    marker = tmp_path / "crashed-once"
    monkeypatch.setenv(video_encoder.CRASH_ONCE_ENV, str(marker))  # read by the spawned worker
    video_encoder.shutdown()
    assert video_encoder.isolate_video_encoding(force=True)
    try:
        with caplog.at_level(logging.WARNING, logger="hibiscus_station.sessions.video_encoder"):
            root = _record(tmp_path, "trap", episodes=2)
    finally:
        video_encoder.shutdown()
        if sys.platform != "darwin":
            video_encoder.restore()
    assert marker.is_file()  # a worker died
    assert "video encoder process died" in caplog.text
    [video] = (root / "videos" / "observation.images.front").rglob("*.mp4")
    assert _frames(video) == 12  # Station lived and both episodes were saved
    assert not list(root.rglob("*.png"))  # LeRobot removed the frames after the encode that worked


def test_opening_a_recording_starts_the_worker_before_the_first_episode(
    tmp_path: Path, isolated_encoder: None
) -> None:
    """A Stop waits for the episode's encode: the worker (seconds to spawn and import LeRobot on a
    Mac) is started when the recording opens, not by the first save. Station keeps it afterwards."""
    assert video_encoder._pool is None
    assert video_encoder.isolate_video_encoding()  # on: forced by the fixture (on macOS by default)
    rec = DatasetRecorder(
        tmp_path, "warm", fps=10, motor_keys=["shoulder_pan.pos"], cam_shapes={"front": (48, 64, 3)}, task="t"
    )
    rec.open()
    pool = video_encoder._pool
    assert pool is not None  # started by open(), before any frame
    rec.finalize()
    from hibiscus_station.station import Station

    st = Station(tmp_path / "home", mock=True, cal_root=tmp_path / "cal")
    st.start()
    st.shutdown()
    assert video_encoder._pool is pool  # a Station shutdown does not throw the warm worker away


def test_encode_errors_are_not_retried_as_crashes(isolated_encoder: None, tmp_path: Path) -> None:
    """An ordinary exception in the worker (no frames) surfaces at once; only a dead worker retries."""
    args: tuple[Any, ...] = ("observation.images.front", 0, tmp_path, 10, None, None)
    with pytest.raises(Exception) as ei:
        video_encoder.encode_isolated(*args)
    assert not isinstance(ei.value, RuntimeError) or "died" not in str(ei.value)
