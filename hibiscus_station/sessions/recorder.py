"""LeRobotDataset writer shared by Record and Run (eval recording), spec §4.4 / §4.5.4 / L12."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import shutil
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hibiscus_station.data.sidecar import EpisodeBuffer, episode_file, sidecar_dir
from hibiscus_station.errors import StationError
from hibiscus_station.settings import write_private

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: Datasets whose last episodes are still being encoded / finalized after their session ended
#: (field report 0.2.9: never in the control loop). Keyed by dataset root.
_CLOSING: dict[Path, Future[None]] = {}
_CLOSING_LOCK = threading.Lock()


@dataclass
class LiveEpisode:
    """An episode a live recorder saved (or is saving) whose ``meta/episodes`` row is not on disk
    yet: lerobot keeps those rows in memory until ``finalize()`` (field report 0.2.10)."""

    frames: int
    saving: bool


#: dataset root -> episode index -> LiveEpisode, until the recorder of that root is finalized
_LIVE: dict[Path, dict[int, LiveEpisode]] = {}


def live_episodes(root: Path) -> dict[int, LiveEpisode]:
    """The episodes of ``root`` that a recorder of this process saved or is saving, not finalized."""
    with _CLOSING_LOCK:
        return {i: LiveEpisode(e.frames, e.saving) for i, e in _LIVE.get(root, {}).items()}


def wait_closed(root: Path, timeout: float) -> None:
    """Wait for a background finalize of ``root`` (a new session on the same dataset)."""
    with _CLOSING_LOCK:
        fut = _CLOSING.get(root)
    if fut is None:
        return
    try:
        fut.result(timeout=timeout)
    except TimeoutError as exc:
        raise StationError(
            "busy",
            "the last episode of this dataset is still being saved; try again in a moment",
            params={"dataset": root.name, "state": "saving"},
        ) from exc
    except Exception:  # noqa: S110 - the failure was reported (alert + log) by the closer
        pass


def check_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise StationError("validation_failed", "dataset name must match [a-z0-9][a-z0-9_-]{0,63}")
    return name


def build_features(
    motor_keys: list[str], cam_shapes: dict[str, tuple[int, int, int]], use_video: bool
) -> dict[str, Any]:
    from lerobot.utils.feature_utils import hw_to_dataset_features

    motors = dict.fromkeys(motor_keys, float)
    return {
        **hw_to_dataset_features(motors, "action", use_video),
        **hw_to_dataset_features({**motors, **cam_shapes}, "observation", use_video),
    }


def _norm_features(features: dict[str, Any]) -> dict[str, tuple[str, tuple[int, ...]]]:
    return {
        k: (str(v.get("dtype")), tuple(int(x) for x in v.get("shape", ())))
        for k, v in features.items()
        if k not in ("timestamp", "frame_index", "episode_index", "index", "task_index")
    }


class DatasetRecorder:
    def __init__(
        self,
        datasets_root: Path,
        name: str,
        *,
        fps: int,
        motor_keys: list[str],
        cam_shapes: dict[str, tuple[int, int, int]],
        use_video: bool = True,
        mode: str = "new",
        robot_type: str = "so_follower",
        task: str = "",
        profile_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self.datasets_root = datasets_root
        self.name = check_name(name)
        self.root = datasets_root / name
        self.fps = fps
        self.motor_keys = motor_keys
        self.cam_shapes = cam_shapes
        self.use_video = use_video
        self.mode = mode
        self.robot_type = robot_type
        self.task = task
        self.profile_snapshot = profile_snapshot or {}
        self.features = build_features(motor_keys, cam_shapes, use_video)
        self.dataset: Any = None
        self.buffer = EpisodeBuffer()
        self.frames_in_episode = 0
        self.saving: Future[int] | None = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"ds-{name}")
        self.saved_episodes: list[int] = []
        self.save_s: list[float] = []  # encode + write time of each saved episode (evidence)
        self.finalized = False

    # ------------------------------------------------------------------ open
    def open(self) -> None:
        from lerobot.datasets import LeRobotDataset

        repo_id = f"local/{self.name}"
        threads = 4 * max(1, len(self.cam_shapes))
        if self.mode == "append":
            info_path = self.root / "meta" / "info.json"
            if not info_path.is_file():
                raise StationError(
                    "not_found", f"dataset {self.name} does not exist", params={"dataset": self.name}
                )
            info = json.loads(info_path.read_text(encoding="utf-8"))
            mismatch = []
            if int(info.get("fps", 0)) != self.fps:
                mismatch.append(f"fps {info.get('fps')} != {self.fps}")
            if _norm_features(info.get("features", {})) != _norm_features(self.features):
                mismatch.append("features (cameras / joints / video) differ from the current robot setup")
            if mismatch:
                raise StationError("dataset_incompatible", "; ".join(mismatch), params={"dataset": self.name})
            self.dataset = LeRobotDataset.resume(repo_id, root=self.root, image_writer_threads=threads)
        else:
            if self.root.exists():
                raise StationError(
                    "dataset_exists", f"dataset {self.name} already exists", params={"dataset": self.name}
                )
            self.dataset = LeRobotDataset.create(
                repo_id,
                fps=self.fps,
                features=self.features,
                root=self.root,
                robot_type=self.robot_type,
                use_videos=self.use_video,
                image_writer_threads=threads,
            )
        self._write_meta()

    def _write_meta(self) -> None:
        sd = sidecar_dir(self.datasets_root, self.name)
        meta_path = sd / "dataset.json"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except ValueError:
                meta = {}
        meta.setdefault("created_at", dt.datetime.now(dt.UTC).isoformat())
        meta.setdefault("uploads", [])
        meta["task"] = self.task or meta.get("task", "")
        meta["profile"] = self.profile_snapshot
        meta["updated_at"] = dt.datetime.now(dt.UTC).isoformat()
        write_private(meta_path, json.dumps(meta, indent=2))

    # ------------------------------------------------------------------ frames
    @property
    def next_episode_index(self) -> int:
        return int(self.dataset.meta.total_episodes) if self.dataset is not None else 0

    def add(self, obs: dict[str, Any], action: dict[str, float], task: str) -> None:
        from lerobot.utils.feature_utils import build_dataset_frame

        frame = {
            **build_dataset_frame(self.features, obs, "observation"),
            **build_dataset_frame(self.features, action, "action"),
            "task": task,
        }
        self.dataset.add_frame(frame)
        self.frames_in_episode += 1

    def save_async(self) -> Future[int]:
        index = self.next_episode_index
        buffer_lines = self.buffer.lines
        self.buffer = EpisodeBuffer()
        frames = self.frames_in_episode
        self.frames_in_episode = 0

        live = LiveEpisode(frames, saving=True)
        with _CLOSING_LOCK:
            _LIVE.setdefault(self.root, {})[index] = live

        def work() -> int:
            t0 = time.monotonic()
            try:
                self.dataset.save_episode(parallel_encoding=False)
                eb = EpisodeBuffer()
                eb.lines = buffer_lines
                eb.save(episode_file(self.datasets_root, self.name, index))
            except BaseException:
                with _CLOSING_LOCK:
                    _LIVE.get(self.root, {}).pop(index, None)
                raise
            with _CLOSING_LOCK:
                live.saving = False
            self.saved_episodes.append(index)
            took = time.monotonic() - t0
            self.save_s.append(round(took, 2))
            log.info("saved episode %d of %s (%d frames) in %.1f s", index, self.name, frames, took)
            return index

        self.saving = self._pool.submit(work)
        return self.saving

    def discard(self) -> None:
        if self.dataset is not None and self.frames_in_episode:
            self.dataset.clear_episode_buffer()
        self.frames_in_episode = 0
        self.buffer.discard()

    def wait_saving(self, timeout: float | None = None) -> None:
        """Wait for the episode being saved. No default timeout: a slow encoder (a Windows laptop
        needs tens of seconds for a 30 s episode) must never abandon a save half written."""
        if self.saving is not None:
            self.saving.result(timeout=timeout)
            self.saving = None

    def close_async(self, save_pending: bool, on_error: Any = None) -> Future[None]:
        """Finish the save in flight, save the buffered episode when ``save_pending``, finalize:
        on a background thread, so the control loop (e-stop relax, telemetry, cameras) never waits
        for an encoder. :func:`wait_closed` lets the next session on this dataset wait for it."""
        fut: Future[None] = Future()

        def work() -> None:
            try:
                try:
                    self.wait_saving()
                    if save_pending:
                        self.save_async()
                        self.wait_saving()
                finally:
                    self.finalize()
            except BaseException as exc:
                log.exception("closing dataset %s failed", self.name)
                if on_error is not None:
                    on_error(exc)
                fut.set_exception(exc)
            else:
                fut.set_result(None)
            finally:
                with _CLOSING_LOCK:
                    if _CLOSING.get(self.root) is fut:
                        del _CLOSING[self.root]

        with _CLOSING_LOCK:
            _CLOSING[self.root] = fut
        threading.Thread(target=work, name=f"ds-close-{self.name}", daemon=False).start()
        return fut

    def finalize(self) -> None:
        if self.finalized:
            return
        try:
            self.wait_saving()
        finally:
            self.discard()
            try:
                if self.dataset is not None:
                    self.dataset.finalize()
            finally:
                with _CLOSING_LOCK:  # the rows are on disk now (or never will be)
                    _LIVE.pop(self.root, None)
            self._pool.shutdown(wait=True)
            self.finalized = True
            if self.dataset is not None and int(self.dataset.meta.total_episodes) == 0 and self.mode == "new":
                # nothing saved: leave no half-created dataset behind
                shutil.rmtree(self.root, ignore_errors=True)
                shutil.rmtree(sidecar_dir(self.datasets_root, self.name), ignore_errors=True)
