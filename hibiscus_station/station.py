"""The Station: composes paths, settings, profiles, the hardware owner, cameras, models, jobs, server."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from hibiscus_station.data import datasets as ds_catalog
from hibiscus_station.data.sessions import prune
from hibiscus_station.errors import StationError
from hibiscus_station.hw.cameras import CameraHub, PreviewEncoder
from hibiscus_station.hw.owner import HardwareOwner
from hibiscus_station.jobs import Job, JobManager
from hibiscus_station.models import compat, importer
from hibiscus_station.models.loader import LoadedPolicy, load_policy
from hibiscus_station.models.registry import ModelEntry, ModelRegistry
from hibiscus_station.profiles import ProfileStore, RobotProfile
from hibiscus_station.programs.hub import ProgramsHub
from hibiscus_station.remote import ServerLink, pull_model, upload_dataset
from hibiscus_station.sessions.base import MotionSession
from hibiscus_station.sessions.record import RecordSession
from hibiscus_station.sessions.recorder import DatasetRecorder, check_name
from hibiscus_station.sessions.replay import ReplaySession, load_episode_actions
from hibiscus_station.sessions.run import RunSession
from hibiscus_station.sessions.teleop import TeleopSession
from hibiscus_station.settings import Settings, StationPaths, calibration_root

log = logging.getLogger(__name__)


class TeleopRequest(BaseModel):
    fps: int = Field(30, ge=1, le=60)


class RecordRequest(BaseModel):
    dataset: str
    mode: Literal["new", "append"] = "new"
    task: str = Field(..., min_length=1, max_length=500)
    num_episodes: int = Field(1, ge=1, le=1000)
    episode_time_s: float = Field(30.0, gt=0, le=600)
    reset_time_s: float = Field(10.0, ge=0, le=600)
    fps: int = Field(30, ge=1, le=60)
    video: bool = True
    on_timeout: Literal["save", "discard"] = "save"
    countdown_s: float = Field(3.0, ge=0, le=30)


class ReplayRequest(BaseModel):
    dataset: str
    episode: int = Field(0, ge=0)


class RunRequest(BaseModel):
    model: str
    task: str = ""
    fps: int | None = Field(None, ge=1, le=60)
    episode_time_s: float = Field(30.0, gt=0, le=600)
    num_episodes: int = Field(1, ge=1, le=100)
    reset_time_s: float = Field(10.0, ge=0, le=600)
    countdown_s: float = Field(3.0, ge=0, le=30)
    camera_map: dict[str, str] = Field(default_factory=dict)
    max_relative_target: float | None = Field(None, gt=0)
    reset_with_leader: bool = False
    record: bool = False
    dataset: str | None = None


class UploadRequest(BaseModel):
    new_dataset_name: str | None = None
    dataset_id: str | None = None

    @model_validator(mode="after")
    def _one(self) -> UploadRequest:
        if (self.new_dataset_name is None) == (self.dataset_id is None):
            raise ValueError("exactly one of new_dataset_name / dataset_id is required")
        return self


class Station:
    def __init__(
        self, home: Path, *, mock: bool = False, cal_root: Path | None = None, port: int = 18210
    ) -> None:
        self.paths = StationPaths(home)
        self.paths.ensure()
        self.mock = mock
        self.port = port
        self.cal_root = cal_root or calibration_root()
        self.settings = Settings.load(self.paths.settings)
        self.profiles = ProfileStore(self.paths.robots)
        self.hub = CameraHub(self.paths.locks)
        self.encoder = PreviewEncoder(self.hub, quality=self.settings.preview.quality)
        self.owner = HardwareOwner(
            self.paths, self.settings, self.profiles, self.hub, cal_root=self.cal_root, mock=mock
        )
        self.registry = ModelRegistry(self.paths.models)
        self.server = ServerLink(self.paths.server)
        self.jobs = JobManager(self.owner.emit)
        self.loaded: LoadedPolicy | None = None
        self._load_lock = threading.Lock()
        self.import_roots = [Path.home(), Path("/media"), Path("/mnt")]
        self.started = False
        self.owner.status_hook = self._decorate_status
        self.programs = ProgramsHub(self)  # trajectories, poses, detectors, signals, programs
        prune(
            self.paths.sessions, self.settings.session_retention_days, self.settings.session_retention_bytes
        )
        if mock and not self.profiles.list():
            self.profiles.put(demo_profile())

    def start(self) -> None:
        if not self.started:
            self.owner.start()
            self.encoder.start()
            self.programs.start()
            self.started = True

    def shutdown(self) -> None:
        if self.started:
            self.owner.shutdown()
            self.encoder.stop()
            self.jobs.shutdown()
            self.programs.shutdown()
            self.started = False

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        return self.owner.status()

    def _decorate_status(self, st: dict[str, Any]) -> None:
        st["station"]["device"] = self.settings.device
        st["station"]["home"] = str(self.paths.home)
        st["server"] = {
            "paired": self.server.paired,
            "url": self.server.data.get("web_url"),
            "workspace": self.server.data.get("workspace_slug"),
        }
        st["loaded_model"] = self.loaded.key if self.loaded else None
        hub = getattr(self, "programs", None)  # status may be asked before the hub exists
        st["program"] = hub.current_program() if hub is not None else None

    def update_settings(self, new: Settings) -> Settings:
        self.owner.call("set_thresholds", thresholds=new.thresholds)
        new.save(self.paths.settings)
        self.settings = new
        self.owner.settings = new
        self.owner.telemetry.settings = new.telemetry
        self.owner.estop.double_press_s = new.safety.estop_double_press_s
        self.owner.watchdog.timeout_s = new.safety.deadman_timeout_s
        self.encoder.quality = new.preview.quality
        self.programs.apply_settings()
        return new

    # ------------------------------------------------------------------ robots
    def put_robot(self, profile: RobotProfile) -> RobotProfile:
        if self.owner.profile is not None and self.owner.profile.id == profile.id:
            self.owner.call("update_profile", profile=profile, timeout=15.0)
        return self.profiles.put(profile)

    def delete_robot(self, robot_id: str) -> None:
        if (
            self.owner.profile is not None
            and self.owner.profile.id == robot_id
            and self.owner.follower is not None
        ):
            raise StationError("busy", "disconnect this robot first", params={"state": self.owner.state})
        if not self.profiles.delete(robot_id):
            raise StationError("not_found", f"no robot {robot_id}")

    # ------------------------------------------------------------------ sessions
    def _profile(self) -> RobotProfile:
        if self.owner.profile is None or self.owner.follower is None:
            raise StationError("not_connected", "connect a robot first")
        return self.owner.profile

    def start_teleop(self, req: TeleopRequest) -> dict[str, Any]:
        self._profile()

        def build(owner: HardwareOwner) -> MotionSession:
            return TeleopSession(
                kind="teleop", fps=req.fps, approach_s=self.settings.safety.smooth_approach_s
            )

        return self.owner.call(  # type: ignore[no-any-return]
            "start_session",
            kind="teleop",
            build=build,
            needs_leader=True,
            leader_check_deg=self.settings.safety.max_approach_deg,
            timeout=10.0,
        )

    def start_record(self, req: RecordRequest) -> dict[str, Any]:
        profile = self._profile()
        check_name(req.dataset)

        def build(owner: HardwareOwner) -> MotionSession:
            rec = DatasetRecorder(
                self.paths.datasets,
                req.dataset,
                fps=req.fps,
                motor_keys=[f"{m}.pos" for m in owner.follower.bus.motors],
                cam_shapes=self.hub.shapes(),
                use_video=req.video,
                mode=req.mode,
                robot_type=owner.follower.robot_type,
                task=req.task,
                profile_snapshot=profile.model_dump(mode="json"),
            )
            rec.open()
            return RecordSession(
                kind="record",
                fps=req.fps,
                task=req.task,
                dataset=req.dataset,
                recorder=rec,
                num_episodes=req.num_episodes,
                episode_time_s=req.episode_time_s,
                reset_time_s=req.reset_time_s,
                countdown_s=req.countdown_s,
                on_timeout=req.on_timeout,
                approach_s=min(self.settings.safety.smooth_approach_s, req.countdown_s),
            )

        return self.owner.call(  # type: ignore[no-any-return]
            "start_session",
            kind="record",
            build=build,
            needs_leader=True,
            leader_check_deg=self.settings.safety.max_approach_deg,
            timeout=20.0,
        )

    def start_replay(self, req: ReplayRequest) -> dict[str, Any]:
        self._profile()
        check_name(req.dataset)
        fps, actions = load_episode_actions(self.paths.datasets / req.dataset, req.episode)

        def build(owner: HardwareOwner) -> MotionSession:
            s = ReplaySession(
                kind="replay",
                fps=fps,
                dataset=req.dataset,
                actions=actions,
                episode_index=req.episode,
                approach_s=self.settings.safety.smooth_approach_s,
            )
            s.deadman = self.settings.safety.deadman_replay
            return s

        return self.owner.call(  # type: ignore[no-any-return]
            "start_session", kind="replay", build=build, needs_leader=False, timeout=10.0
        )

    def start_run(self, req: RunRequest) -> dict[str, Any]:
        profile = self._profile()
        entry = self.registry.get(req.model)
        if entry is None:
            raise StationError("not_found", f"no model {req.model}")
        lp = self.loaded
        if lp is None or lp.key != entry.key:
            raise StationError("model_not_loaded", "load the model first", params={"model": entry.key})
        report = compat.check(entry, profile, req.camera_map or None, device=lp.device)
        if not report["ok"]:
            raise StationError(
                "model_incompatible",
                "the model does not match this robot",
                errors=[c for c in report["checks"] if not c["ok"]],
            )
        fps = req.fps or entry.fps or 30
        task = req.task or entry.task or ""
        cmap: dict[str, str] = report["camera_map"]
        max_rel = req.max_relative_target
        prof_rel = profile.follower.max_relative_target
        if max_rel is not None and isinstance(prof_rel, float) and max_rel > prof_rel:
            max_rel = prof_rel  # editable down only
        dataset = req.dataset or (
            f"eval_{entry.key}_{time.strftime('%Y%m%d_%H%M%S')}" if req.record else None
        )
        if dataset is not None:
            dataset = dataset.lower().replace(".", "_")[:64]
            check_name(dataset)

        def build(owner: HardwareOwner) -> MotionSession:
            rec = None
            if dataset is not None:
                rec = DatasetRecorder(
                    self.paths.datasets,
                    dataset,
                    fps=fps,
                    motor_keys=[f"{m}.pos" for m in owner.follower.bus.motors],
                    cam_shapes=self.hub.shapes(),
                    use_video=True,
                    robot_type=owner.follower.robot_type,
                    task=task,
                    profile_snapshot=profile.model_dump(mode="json"),
                )
                rec.open()
            s = RunSession(
                kind="run",
                fps=fps,
                task=task,
                model=entry.key,
                dataset=dataset,
                loaded=lp,
                camera_map=cmap,
                num_episodes=req.num_episodes,
                episode_time_s=req.episode_time_s,
                reset_time_s=req.reset_time_s,
                countdown_s=req.countdown_s,
                reset_with_leader=req.reset_with_leader and owner.leader is not None,
                recorder=rec,
                robot_type=owner.follower.robot_type,
            )
            s.build_features([f"{m}.pos" for m in owner.follower.bus.motors], self.hub.shapes())
            return s

        return self.owner.call(  # type: ignore[no-any-return]
            "start_session",
            kind="run",
            build=build,
            needs_leader=req.reset_with_leader,
            max_relative_target=max_rel,
            timeout=20.0,
        )

    # ------------------------------------------------------------------ datasets
    def upload(self, name: str, req: UploadRequest) -> Job:
        check_name(name)
        root = self.paths.datasets / name
        if not (root / "meta" / "info.json").is_file():
            raise StationError("not_found", f"no dataset {name}")
        s = self.owner.session
        if s is not None and s.dataset == name:
            raise StationError("busy", "this dataset is being recorded", params={"state": self.owner.state})
        if not self.server.paired:
            raise StationError("not_paired", "pair Station with a Hibiscus server first")
        self.server.require_scope("datasets:write")

        def work(job: Job) -> dict[str, Any]:
            job.result = {"dataset": name}
            result = upload_dataset(
                self.server,
                self.jobs,
                job,
                root,
                new_dataset_name=req.new_dataset_name,
                dataset_id=req.dataset_id,
            )
            ds_catalog.record_upload(self.paths.datasets, name, self.server.data["url"], result)
            return {"dataset": name, **result}

        return self.jobs.submit("upload", work, subject=name)

    def delete_dataset(self, name: str) -> None:
        s = self.owner.session
        if s is not None and s.dataset == name:
            raise StationError("busy", "this dataset is being recorded", params={"state": self.owner.state})
        if self.jobs.busy("upload", "dataset", name):
            raise StationError("busy", "this dataset is being uploaded")
        ds_catalog.delete(self.paths.datasets, name)

    # ------------------------------------------------------------------ models
    def import_model_zip(self, zpath: Path, name: str | None = None) -> Job:
        def work(job: Job) -> dict[str, Any]:
            self.jobs.progress(job, phase="extracting")
            try:
                entry = importer.import_zip(self.registry, zpath, self.paths.staging, name=name)
            finally:
                zpath.unlink(missing_ok=True)
            return {"model": entry.key}

        return self.jobs.submit("import", work)

    def import_model_path(self, path: Path, name: str | None = None) -> Job:
        def work(job: Job) -> dict[str, Any]:
            self.jobs.progress(job, phase="copying")
            if path.is_file() and path.suffix == ".zip":
                if not importer.allowed(path, self.import_roots):
                    raise StationError("forbidden", "path not under an allowed root", status=403)
                entry = importer.import_zip(self.registry, path, self.paths.staging, name=name)
            else:
                entry = importer.import_dir(
                    self.registry, path, self.paths.staging, self.import_roots, name=name
                )
            return {"model": entry.key}

        return self.jobs.submit("import", work)

    def pull_model(self, server_model_id: str) -> Job:
        if not self.server.paired:
            raise StationError("not_paired", "pair Station with a Hibiscus server first")
        self.server.require_scope("models:read")

        def work(job: Job) -> dict[str, Any]:
            dest = self.paths.staging / f"pull-{job.id}"
            bundle = pull_model(self.server, self.jobs, job, server_model_id, dest)
            try:
                entry = importer.register_tree(
                    self.registry, bundle, name=bundle.name, source="server", server_model_id=server_model_id
                )
            finally:
                import shutil

                shutil.rmtree(dest, ignore_errors=True)
            return {"model": entry.key}

        return self.jobs.submit("pull", work, subject=server_model_id)

    def model_entry(self, key: str) -> ModelEntry:
        entry = self.registry.get(key)
        if entry is None:
            raise StationError("not_found", f"no model {key}")
        return entry

    def compat(self, key: str, robot_id: str | None) -> dict[str, Any]:
        entry = self.model_entry(key)
        profile = self.profiles.get(robot_id) if robot_id else self.owner.profile
        if profile is None:
            raise StationError("not_found", "no robot profile to check against")
        dev = self.loaded.device if self.loaded and self.loaded.key == key else self.settings.device
        return compat.check(entry, profile, device=dev)

    def load_model(self, key: str, device: str | None = None) -> Job:
        entry = self.model_entry(key)

        def work(job: Job) -> dict[str, Any]:
            self.jobs.progress(job, phase="loading")
            with self._load_lock:
                if self.owner.session is not None and self.owner.session.kind == "run":
                    raise StationError("busy", "a model is running")
                self.loaded = None
                self.owner.loaded_model = None
                lp = load_policy(
                    entry.key, self.registry.pretrained_dir(entry), device or self.settings.device
                )
                self.loaded = lp
                self.owner.loaded_model = lp.key
            self.owner.emit("state", self.status())
            return {"model": entry.key, **lp.view()}

        return self.jobs.submit("load", work, subject=entry.key)

    def delete_model(self, key: str) -> None:
        if self.loaded is not None and self.loaded.key == key:
            if self.owner.session is not None and self.owner.session.kind == "run":
                raise StationError("busy", "this model is running")
            self.loaded = None
            self.owner.loaded_model = None
        if not self.registry.remove(key):
            raise StationError("not_found", f"no model {key}")


def demo_profile() -> RobotProfile:
    """The ``--mock`` demo robot: mock arms and two mock cameras."""
    from hibiscus_station.profiles import CameraProfile, FollowerProfile, LeaderProfile

    return RobotProfile(
        id="demo_so101",
        name="Demo SO-101 (mock)",
        follower=FollowerProfile(
            type="hibiscus_mock_follower", port="mock://follower", calibration_id="demo_follower"
        ),
        leader=LeaderProfile(type="hibiscus_mock_leader", port="mock://leader", calibration_id="demo_leader"),
        cameras={
            "wrist": CameraProfile(type="mock", width=128, height=96, fps=30),
            "front": CameraProfile(type="mock", width=128, height=96, fps=30),
        },
    )
