"""REST API ``/api/v1`` (spec §5.2). Handlers never touch hardware: they post owner commands."""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field

from hibiscus_station.api import schemas as wire
from hibiscus_station.data import datasets as ds_catalog
from hibiscus_station.data.sessions import list_sessions, session_series
from hibiscus_station.errors import StationError
from hibiscus_station.hw import ports as hwports
from hibiscus_station.hw.factory import calibration_files
from hibiscus_station.hw.locks import normalize_device
from hibiscus_station.profiles import CameraProfile, RobotProfile
from hibiscus_station.settings import Settings
from hibiscus_station.station import (
    RecordRequest,
    ReplayRequest,
    RunRequest,
    Station,
    TeleopRequest,
    UploadRequest,
)

MAX_ZIP = 4 * 1024**3


class DetectRequest(BaseModel):
    method: Literal["unplug", "motion"] = "unplug"
    ports_before: list[str] | None = None
    timeout_s: float = Field(15.0, gt=0, le=60)


class DisconnectRequest(BaseModel):
    relax: bool = False


class TorqueRequest(BaseModel):
    arm: Literal["follower", "leader"] = "follower"
    enabled: bool
    confirm: bool = False


class CalibrationStart(BaseModel):
    arm: Literal["follower", "leader"]
    id: str | None = None
    keep_existing: bool = False


class CalibrationStep(BaseModel):
    action: Literal["set_home", "finish_ranges", "cancel"]


class ControlRequest(BaseModel):
    action: Literal["next", "rerecord", "stop", "resume"]


class ModelPath(BaseModel):
    path: str
    name: str | None = None


class PullRequest(BaseModel):
    server_model_id: str


class LoadRequest(BaseModel):
    device: Literal["auto", "cpu", "cuda", "mps"] | None = None


class PairRequest(BaseModel):
    url: str
    token: str
    workspace_id: str | None = None


class ProbeRequest(CameraProfile):
    duration_s: float = Field(2.0, gt=0, le=10)


def _out[M: BaseModel](model: type[M], data: Any) -> M:
    """Validate a handler's dict against its wire model: drift is a 500 here and a test failure."""
    return model.model_validate(data)


def station(request: Request) -> Station:
    st: Station = request.app.state.station
    return st


def build_router() -> APIRouter:
    r = APIRouter(
        prefix="/api/v1",
        responses={"default": {"model": wire.Problem, "description": "RFC 9457 problem (spec §5.1)"}},
    )

    # ------------------------------------------------------------------ system
    @r.get("/status", tags=["system"])
    def get_status(request: Request) -> wire.Status:
        return _out(wire.Status, station(request).status())

    @r.get("/settings", tags=["system"])
    def get_settings(request: Request) -> Settings:
        return station(request).settings

    @r.put("/settings", tags=["system"])
    def put_settings(request: Request, body: Settings) -> Settings:
        return station(request).update_settings(body)

    # ------------------------------------------------------------------ ports & robots
    @r.get("/ports", tags=["robots"])
    def get_ports(request: Request) -> wire.Ports:
        st = station(request)
        return _out(wire.Ports, {"ports": hwports.list_ports(_ports_in_use(st))})

    @r.post("/ports/detect", tags=["robots"])
    def detect_port(request: Request, body: DetectRequest) -> wire.DetectResponse:
        st = station(request)
        in_use = _ports_in_use(st)

        def lister() -> list[str]:
            return [p["device"] for p in hwports.list_ports(in_use)]

        if body.method == "unplug":
            if body.ports_before is None:
                return wire.DetectResponse(ports_before=lister())
            port = hwports.detect_unplug(body.ports_before, lister, timeout_s=body.timeout_s)
        else:
            held = {normalize_device(d) for d in in_use}
            candidates = [p for p in lister() if normalize_device(p) not in held]
            port = hwports.detect_motion(candidates, hwports.read_raw_positions, timeout_s=body.timeout_s)
        if port is None:
            raise StationError("not_found", "no port detected; try again", params={"method": body.method})
        rows = {p["device"]: p for p in hwports.list_ports(in_use)}
        fallback = {
            "device": port,
            "stable_path": None,
            "vid_pid": None,
            "serial_number": None,
            "description": "",
            "in_use_by": None,
        }
        return wire.DetectResponse(port=wire.Port.model_validate(rows.get(port, fallback)))

    @r.get("/robots", tags=["robots"])
    def get_robots(request: Request) -> wire.Robots:
        st = station(request)
        return wire.Robots(robots=st.profiles.list(), active=st.profiles.active)

    @r.put("/robots/{robot_id}", tags=["robots"])
    def put_robot(request: Request, robot_id: str, body: RobotProfile) -> RobotProfile:
        if body.id != robot_id:
            raise StationError("validation_failed", "id in the path and the body differ")
        return station(request).put_robot(body)

    @r.delete("/robots/{robot_id}", status_code=204, tags=["robots"])
    def delete_robot(request: Request, robot_id: str) -> Response:
        station(request).delete_robot(robot_id)
        return Response(status_code=204)

    @r.post("/robots/{robot_id}/connect", tags=["robots"])
    def connect(request: Request, robot_id: str) -> wire.Status:
        st = station(request)
        st.owner.call("connect", robot_id=robot_id, timeout=30.0)
        return _out(wire.Status, st.status())

    @r.post("/robots/disconnect", tags=["robots"])
    def disconnect(request: Request, body: DisconnectRequest | None = None) -> wire.Status:
        st = station(request)
        st.owner.call("disconnect", relax=bool(body and body.relax), timeout=30.0)
        return _out(wire.Status, st.status())

    @r.post("/robots/torque", tags=["robots"])
    def torque(request: Request, body: TorqueRequest) -> wire.Status:
        st = station(request)
        st.owner.call("torque", arm=body.arm, enabled=body.enabled, confirm=body.confirm)
        return _out(wire.Status, st.status())

    @r.post("/robots/rest-pose", tags=["robots"])
    def rest_pose(request: Request) -> wire.RestPose:
        return _out(wire.RestPose, station(request).owner.call("set_rest_pose"))

    # ------------------------------------------------------------------ calibration
    @r.get("/calibrations", tags=["calibration"])
    def get_calibrations(request: Request) -> wire.CalibrationFiles:
        return _out(wire.CalibrationFiles, {"files": calibration_files(station(request).cal_root)})

    @r.post("/calibration/start", tags=["calibration"])
    def calibration_start(request: Request, body: CalibrationStart) -> wire.Status:
        st = station(request)
        st.owner.call("calibration_start", arm=body.arm, keep_existing=body.keep_existing, timeout=15.0)
        return _out(wire.Status, st.status())

    @r.post("/calibration/step", tags=["calibration"])
    def calibration_step(request: Request, body: CalibrationStep) -> wire.CalibrationStepResponse:
        st = station(request)
        out = st.owner.call("calibration_step", action=body.action, timeout=15.0)
        status = st.status()
        if isinstance(out, dict) and "calibration" in out:
            status["calibration"] = out["calibration"]
        return _out(wire.CalibrationStepResponse, status)

    # ------------------------------------------------------------------ cameras
    @r.get("/cameras/discover", tags=["cameras"])
    def discover(request: Request) -> wire.DiscoveredCameras:
        st = station(request)
        return _out(wire.DiscoveredCameras, {"cameras": _discover(st)})

    @r.post("/cameras/probe", tags=["cameras"])
    def probe(request: Request, body: ProbeRequest) -> wire.ProbeResult:
        return _out(wire.ProbeResult, _probe(station(request), body))

    # ------------------------------------------------------------------ sessions
    @r.post("/sessions/teleop", tags=["sessions"])
    def teleop(request: Request, body: TeleopRequest | None = None) -> wire.Session:
        return _out(wire.Session, station(request).start_teleop(body or TeleopRequest()))

    @r.post("/sessions/record", tags=["sessions"])
    def record(request: Request, body: RecordRequest) -> wire.Session:
        return _out(wire.Session, station(request).start_record(body))

    @r.post("/sessions/replay", tags=["sessions"])
    def replay(request: Request, body: ReplayRequest) -> wire.Session:
        return _out(wire.Session, station(request).start_replay(body))

    @r.post("/sessions/run", tags=["sessions"])
    def run(request: Request, body: RunRequest) -> wire.Session:
        return _out(wire.Session, station(request).start_run(body))

    @r.post("/sessions/current/control", tags=["sessions"])
    def control(request: Request, body: ControlRequest) -> wire.Session:
        return _out(wire.Session, station(request).owner.call("control", action=body.action, timeout=60.0))

    @r.post("/estop", tags=["sessions"])
    def estop(request: Request) -> wire.Status:
        st = station(request)
        st.owner.press_estop("user")
        time.sleep(0.05)
        return _out(wire.Status, st.status())

    @r.post("/estop/reset", tags=["sessions"])
    def estop_reset(request: Request) -> wire.Status:
        st = station(request)
        st.owner.call("estop_reset")
        return _out(wire.Status, st.status())

    @r.get("/sessions", tags=["sessions"])
    def sessions(request: Request) -> wire.Sessions:
        return _out(wire.Sessions, {"sessions": list_sessions(station(request).paths.sessions)})

    @r.get("/sessions/{session_id}/telemetry", tags=["sessions"])
    def session_telemetry(request: Request, session_id: str) -> wire.TelemetrySeries:
        if any(c in session_id for c in "/\\:") or ".." in session_id:
            raise StationError("validation_failed", "bad session id")
        series = session_series(station(request).paths.sessions, session_id)
        if series is None:
            raise StationError("not_found", f"no session {session_id}")
        return _out(wire.TelemetrySeries, series)

    # ------------------------------------------------------------------ datasets
    @r.get("/datasets", tags=["datasets"])
    def datasets(request: Request) -> wire.LocalDatasets:
        return _out(
            wire.LocalDatasets, {"datasets": ds_catalog.list_datasets(station(request).paths.datasets)}
        )

    @r.get("/datasets/{name}", tags=["datasets"])
    def dataset_detail(request: Request, name: str) -> wire.LocalDatasetDetail:
        return _out(wire.LocalDatasetDetail, ds_catalog.detail(station(request).paths.datasets, name))

    @r.delete("/datasets/{name}", status_code=204, tags=["datasets"])
    def dataset_delete(request: Request, name: str) -> Response:
        station(request).delete_dataset(name)
        return Response(status_code=204)

    @r.get("/datasets/{name}/episodes/{index}/telemetry", tags=["datasets"])
    def episode_telemetry(request: Request, name: str, index: int) -> wire.TelemetrySeries:
        return _out(
            wire.TelemetrySeries, ds_catalog.episode_series(station(request).paths.datasets, name, index)
        )

    @r.post("/datasets/{name}/upload", tags=["datasets"])
    def upload(request: Request, name: str, body: UploadRequest) -> wire.Job:
        return _out(wire.Job, station(request).upload(name, body).view())

    # ------------------------------------------------------------------ models
    @r.get("/models", tags=["models"])
    def models(request: Request) -> wire.Models:
        st = station(request)
        lp = st.loaded
        return wire.Models(
            models=st.registry.list(),
            loaded=lp.key if lp else None,
            loaded_detail=wire.LoadedModel.model_validate(lp.view()) if lp else None,
        )

    @r.post("/models/import", tags=["models"])
    async def model_import(request: Request) -> wire.Job:
        st = station(request)
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            f = form.get("file")
            if not isinstance(f, UploadFile) and not hasattr(f, "read"):
                raise StationError("validation_failed", "multipart field 'file' is required")
            fd, tmp = tempfile.mkstemp(prefix="upload-", suffix=".zip", dir=st.paths.staging)
            size = 0
            out = os.fdopen(fd, "wb")
            try:
                while chunk := await f.read(1024 * 1024):  # type: ignore[union-attr]
                    size += len(chunk)
                    if size > MAX_ZIP:
                        raise StationError("validation_failed", "zip larger than 4 GiB")
                    await asyncio.to_thread(out.write, chunk)
            except BaseException:
                out.close()
                await asyncio.to_thread(os.unlink, tmp)
                raise
            out.close()
            name = form.get("name")
            job = st.import_model_zip(Path(tmp), str(name) if isinstance(name, str) else None)
            return _out(wire.Job, job.view())
        body = ModelPath.model_validate(await request.json())
        path = await asyncio.to_thread(lambda: Path(body.path).expanduser())
        return _out(wire.Job, st.import_model_path(path, body.name).view())

    @r.post("/models/pull", tags=["models"])
    def model_pull(request: Request, body: PullRequest) -> wire.Job:
        return _out(wire.Job, station(request).pull_model(body.server_model_id).view())

    @r.get("/models/{key}/compat", tags=["models"])
    def model_compat(request: Request, key: str, robot: str | None = Query(None)) -> wire.CompatReport:
        return _out(wire.CompatReport, station(request).compat(key, robot))

    @r.post("/models/{key}/load", tags=["models"])
    def model_load(request: Request, key: str, body: LoadRequest | None = None) -> wire.Job:
        return _out(wire.Job, station(request).load_model(key, body.device if body else None).view())

    @r.delete("/models/{key}", status_code=204, tags=["models"])
    def model_delete(request: Request, key: str) -> Response:
        station(request).delete_model(key)
        return Response(status_code=204)

    # ------------------------------------------------------------------ jobs
    @r.get("/jobs", tags=["jobs"])
    def jobs(request: Request) -> wire.Jobs:
        return _out(wire.Jobs, {"jobs": station(request).jobs.list()})

    @r.get("/jobs/{job_id}", tags=["jobs"])
    def job(request: Request, job_id: str) -> wire.Job:
        return _out(wire.Job, station(request).jobs.get(job_id).view())

    @r.post("/jobs/{job_id}/cancel", tags=["jobs"])
    def job_cancel(request: Request, job_id: str) -> wire.Job:
        return _out(wire.Job, station(request).jobs.cancel(job_id).view())

    # ------------------------------------------------------------------ server
    @r.get("/server", tags=["server"])
    def server(request: Request) -> wire.ServerLinkView:
        return _out(wire.ServerLinkView, station(request).server.view())

    @r.post("/server/pair", tags=["server"])
    def pair(request: Request, body: PairRequest) -> wire.ServerLinkView:
        return _out(
            wire.ServerLinkView, station(request).server.pair(body.url, body.token, body.workspace_id)
        )

    @r.delete("/server", status_code=204, tags=["server"])
    def unpair(request: Request) -> Response:
        station(request).server.unpair()
        return Response(status_code=204)

    @r.get("/server/datasets", tags=["server"])
    def server_datasets(request: Request) -> wire.ServerDatasets:
        return _out(wire.ServerDatasets, {"datasets": station(request).server.datasets()})

    @r.get("/server/models", tags=["server"])
    def server_models(request: Request) -> wire.ServerModels:
        return _out(wire.ServerModels, {"models": station(request).server.models()})

    @r.get("/server/runs", tags=["server"])
    def server_runs(request: Request, dataset_id: str | None = Query(None)) -> wire.ServerRuns:
        st = station(request)
        return _out(
            wire.ServerRuns, {"runs": st.server.runs(dataset_id), "new_run_url": st.server.train_link(None)}
        )

    return r


class MockInject(BaseModel):
    port: str = "mock://follower"
    motor: str | None = None
    temp_c: float | None = Field(None, ge=0, le=120)
    clear_temp: bool = False
    #: "follow": the arm's demo "hand" mirrors ``follow_port`` (e.g. leader holds the follower pose);
    #: "default": back to the normal hand (the sweep on a leader).
    hand: Literal["follow", "default"] | None = None
    follow_port: str = "mock://follower"
    #: station-programs.md §4: show a fake coloured cube on a mock camera ("none" removes it).
    camera: str | None = None
    cube: Literal["red", "blue", "green", "yellow", "none"] | None = None


def build_mock_router() -> APIRouter:
    """``--mock`` only (never in openapi.json): fault injection for demos and the e2e UI test."""
    r = APIRouter(prefix="/api/v1/mock", include_in_schema=False)

    @r.post("/inject")
    def inject(request: Request, body: MockInject) -> dict[str, Any]:
        from hibiscus_station.mock import get_world

        if not station(request).mock:
            raise StationError("not_found", "mock hardware is not enabled")
        if not body.port.startswith("mock://"):
            raise StationError("validation_failed", "only mock:// ports")
        world = get_world(body.port)
        world.inject(body.motor, temp_c=body.temp_c, clear_temp=body.clear_temp)
        if body.hand == "follow":
            if not body.follow_port.startswith("mock://"):
                raise StationError("validation_failed", "only mock:// ports")
            world.follow(get_world(body.follow_port))
        elif body.hand == "default":
            world.follow(None)
        if body.camera is not None and body.cube is not None:
            st = station(request)
            if body.camera not in st.hub.names:
                raise StationError("not_found", f"no camera {body.camera}")
            cam = st.hub.camera(body.camera)
            if not hasattr(cam, "show_cube"):
                raise StationError("validation_failed", "only mock cameras")
            cam.show_cube(None if body.cube == "none" else body.cube)
        return {"ok": True}

    return r


# --------------------------------------------------------------------------- helpers
def _ports_in_use(st: Station) -> dict[str, str]:
    p = st.owner.profile
    if p is None or st.owner.follower is None:
        return {}
    out = {p.follower.port: "follower"}
    if p.leader is not None and st.owner.leader is not None:
        out[p.leader.port] = "leader"
    return out


def _discover(st: Station) -> list[dict[str, Any]]:
    holders = st.hub.holders()
    out: list[dict[str, Any]] = []
    found: list[dict[str, Any]] = []
    try:
        from hibiscus_station.hw.cameras import find_opencv_cameras

        # never probe a camera Station holds (Windows refuses a second open); listed below as in use
        found += [{**c, "type": "opencv"} for c in find_opencv_cameras(set(holders))]
    except Exception:  # noqa: S110 - no video stack: nothing to list
        pass
    try:
        from lerobot.cameras.realsense import RealSenseCamera

        found += [{**c, "type": "realsense"} for c in RealSenseCamera.find_cameras()]
    except Exception:  # noqa: S110 - pyrealsense2 not installed
        pass
    if st.mock:
        from hibiscus_station.mock.camera import MockCamera

        found += MockCamera.find_cameras()
    by_id = Path("/dev/v4l/by-id")
    stable: dict[str, str] = {}
    if by_id.is_dir():
        for link in by_id.iterdir():
            stable[os.path.realpath(link)] = str(link)
    for c in found:
        dev = str(c.get("id"))
        prof = c.get("default_stream_profile") or {}
        out.append(
            {
                "type": c.get("type", "opencv"),
                "id": dev,
                "stable_path": stable.get(os.path.realpath(dev)) if dev.startswith("/") else None,
                "name": c.get("name", dev),
                "default": {
                    "width": prof.get("width", 640),
                    "height": prof.get("height", 480),
                    "fps": int(prof.get("fps", 30) or 30),
                    "fourcc": "MJPG" if c.get("type") == "opencv" else None,
                },
                "in_use_by": None,
            }
        )
    for dev, name in holders.items():
        out.append(
            {"type": "held", "id": dev, "stable_path": None, "name": name, "default": None, "in_use_by": name}
        )
    return out


def _probe(st: Station, body: ProbeRequest) -> dict[str, Any]:
    from hibiscus_station.hw.cameras import build_camera, device_key, encode_preview

    profile = CameraProfile.model_validate(body.model_dump(exclude={"duration_s"}))
    if device_key(profile) in st.hub.holders():
        raise StationError("camera_unavailable", "this camera is held by Station; it is already streaming")
    cam = build_camera("probe", profile)
    try:
        cam.connect(warmup=True)
    except Exception as exc:
        return {
            "ok": False,
            "measured_fps": 0.0,
            "width": profile.width,
            "height": profile.height,
            "error": str(exc)[:300],
            "warning": None,
            "snapshot_jpeg_b64": None,
        }
    frames = 0
    last = None
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < body.duration_s:
            try:
                last = cam.async_read(timeout_ms=500)
                frames += 1
            except TimeoutError:
                continue
    finally:
        cam.disconnect()
    elapsed = max(1e-6, time.monotonic() - t0)
    snapshot = None
    w, h = profile.width, profile.height
    if last is not None:
        h, w = int(last.shape[0]), int(last.shape[1])
        jpeg, _, _ = encode_preview(last, min(320, w), 70)
        snapshot = base64.b64encode(jpeg).decode()
    fps = round(frames / elapsed, 2)
    warn = fps < 0.9 * profile.fps
    return {
        "ok": last is not None,
        "measured_fps": fps,
        "width": w,
        "height": h,
        "error": None if last is not None else "no frame",
        "warning": "usb_bandwidth" if warn else None,
        "snapshot_jpeg_b64": snapshot,
    }


def cleanup_staging(st: Station) -> None:
    shutil.rmtree(st.paths.staging, ignore_errors=True)
    st.paths.staging.mkdir(parents=True, exist_ok=True)
