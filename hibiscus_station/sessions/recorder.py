"""LeRobotDataset writer shared by Record and Run (eval recording), spec §4.4 / §4.5.4 / L12."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from hibiscus_station.data.sidecar import EpisodeBuffer, episode_file, sidecar_dir
from hibiscus_station.errors import StationError
from hibiscus_station.settings import write_private

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


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

        def work() -> int:
            self.dataset.save_episode(parallel_encoding=False)
            eb = EpisodeBuffer()
            eb.lines = buffer_lines
            eb.save(episode_file(self.datasets_root, self.name, index))
            self.saved_episodes.append(index)
            log.info("saved episode %d of %s (%d frames)", index, self.name, frames)
            return index

        self.saving = self._pool.submit(work)
        return self.saving

    def discard(self) -> None:
        if self.dataset is not None and self.frames_in_episode:
            self.dataset.clear_episode_buffer()
        self.frames_in_episode = 0
        self.buffer.discard()

    def wait_saving(self, timeout: float | None = 60.0) -> None:
        if self.saving is not None:
            self.saving.result(timeout=timeout)
            self.saving = None

    def finalize(self) -> None:
        if self.finalized:
            return
        try:
            self.wait_saving()
        finally:
            self.discard()
            if self.dataset is not None:
                self.dataset.finalize()
            self._pool.shutdown(wait=True)
            self.finalized = True
            if self.dataset is not None and int(self.dataset.meta.total_episodes) == 0 and self.mode == "new":
                # nothing saved: leave no half-created dataset behind
                shutil.rmtree(self.root, ignore_errors=True)
                shutil.rmtree(sidecar_dir(self.datasets_root, self.name), ignore_errors=True)
