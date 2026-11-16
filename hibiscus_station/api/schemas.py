"""The wire contract (spec §5.3, §5.4): REST responses, control WebSocket and video WebSocket messages.

Every shape the API sends is declared here and exported in ``station/openapi.json`` (WebSocket
messages under ``components.schemas`` too, see :func:`ws_schemas`). The web UI's TypeScript types
are generated from that file (``web: pnpm gen:api``) and the tests validate every REST
response and every emitted WebSocket message against these models (``extra="forbid"``), so a field
added on one side without the other fails CI.

Request bodies live next to their handlers (``api/routes.py``, ``station.py``); persisted models
(``Settings``, ``RobotProfile``, ``ModelEntry``) are reused as-is.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from hibiscus_station.models.registry import ModelEntry
from hibiscus_station.profiles import RobotProfile
from hibiscus_station.programs.schemas import (
    ClientProgramInput,
    ProgramLogMsg,
    ProgramState,
    ProgramStateMsg,
    SignalMsg,
    TrajectoryRecordMsg,
)

Arm = Literal["follower", "leader"]
Level = Literal["ok", "warn", "hot", "critical"]
AlertLevel = Literal["info", "warn", "hot", "critical"]
StationState = Literal[
    "disconnected",
    "connecting",
    "idle",
    "calibrating",
    "teleop",
    "recording",
    "replaying",
    "inferring",
    "recording_traj",  # station-programs.md §3.1: leader drives, follower goals stored as a trajectory
    "playing",  # §3.2: a stored trajectory drives the follower
    "programming",  # §5.1: a block program drives the follower
    "stopping",
    "estopped",
    "error",
]
# Sub-phase: the calibration step while ``calibrating``, else the session's episode phase.
Phase = Literal[
    "home",
    "ranges",
    "approach",
    "align",  # teleop with align=true: the follower moves slowly to the leader's pose first
    "teleop",
    "replay",
    "countdown",
    "warmup",
    "episode",
    "saving",
    "reset",
    "capture",  # recording_traj: the take is being stored
    "running",  # programming: executing statements
    "waiting",  # programming: wait / wait until / ask (Hibi sleeps)
    "paused",  # programming: paused by the operator
    "done",
]
SessionKind = Literal["teleop", "record", "replay", "run", "traj_record", "traj_play", "program", "rest"]
JobKind = Literal["upload", "pull", "import", "load"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
ControlAction = Literal["next", "rerecord", "stop", "resume"]


class Out(BaseModel):
    """Wire model: unknown fields are an error (tests catch drift), no implicit defaults."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- errors
class Problem(Out):
    """RFC 9457 problem (spec §5.1); ``application/problem+json``."""

    type: str
    title: str
    status: int
    code: str
    detail: str
    request_id: str
    params: dict[str, Any] | None = None
    errors: list[dict[str, Any]] | None = None


# --------------------------------------------------------------------------- status
class StationInfo(Out):
    version: str
    lerobot: str
    device: Literal["auto", "cpu", "cuda", "mps"]
    mock: bool
    home: str = Field(description="Station data dir (datasets, models, sessions)")


class ArmStatus(Out):
    port: str
    calibrated: bool
    calibration_id: str | None = None
    calibration_file: str | None = Field(None, description="the file lerobot reads for this arm")
    issue: str | None = Field(None, description="why the arm is not calibrated, in plain words")
    bus_errors: int = Field(0, description="failed bus calls since connect (retried ones included)")
    last_bus_error: str | None = None


class ArmsStatus(Out):
    follower: ArmStatus
    leader: ArmStatus | None = None


class RobotStatus(Out):
    id: str
    name: str
    mock: bool = Field(False, description="the profile drives SIMULATED arms (demo), not real ones")
    connected: bool
    follower_torque: bool
    arms: ArmsStatus


class CameraStatus(Out):
    name: str
    type: Literal["opencv", "realsense", "mock"]
    streaming: bool
    width: int
    height: int
    fps: int
    stale: bool
    error: str | None


class Hottest(Out):
    arm: Arm
    motor: str
    temp_c: float


class Health(Out):
    level: Level
    hottest: Hottest | None


class ServerStatus(Out):
    paired: bool
    url: str | None
    workspace: str | None


class Alert(Out):
    id: str
    t: float = Field(description="seconds since session start (0 outside sessions)")
    level: AlertLevel
    kind: Literal[
        "temperature",
        "voltage",
        "current",
        "load",
        "status",
        "camera",
        "loop",
        "telemetry_degraded",
        "policy_clipping",
        "teleop_clipping",
    ]
    arm: Arm | None
    motor: str | None
    camera: str | None
    value: float | None
    message_key: str
    params: dict[str, Any]
    active: bool


class EpisodeInfo(Out):
    index: int
    of: int
    saved: int
    phase: Phase | None
    elapsed_s: float
    limit_s: float | None


class Controls(Out):
    next: bool
    rerecord: bool
    stop: bool


class PolicyStats(Out):
    inferences: int
    last_policy_tick: int | None


class Session(Out):
    id: str
    kind: SessionKind
    started_at: str
    fps: int
    episode: EpisodeInfo
    dataset: str | None
    model: str | None
    task: str
    controls: Controls
    outcome: str = Field(description='"running" while active; then completed|stopped|<estop reason>')
    paused: str | None = Field(None, description="run only: why inference is paused (model_too_slow)")
    policy: PolicyStats | None = Field(None, description="run only")
    trajectory: str | None = Field(None, description="traj_record (the draft) / traj_play: trajectory id")
    program: str | None = Field(None, description="program only: program id")


class SessionLoop(Out):
    ticks: int
    overruns: int
    tick_ms_p95: float
    telemetry_reads: int
    telemetry_forced: int
    fps: float | None = Field(None, description="mean loop rate over the session")
    latency_ms_p50: float | None = Field(None, description="leader -> follower (leader-driven sessions)")
    latency_ms_p95: float | None = None


class SessionEnd(Session):
    """The last ended session (``Status.last_session``, and the final ``session`` message)."""

    reason: str
    summary: dict[str, Any]
    loop: SessionLoop
    max_temp_c: dict[str, float] = Field(description='peak temperature per "arm.motor"')


class PortIdentity(Out):
    device: str
    stable_path: str | None = None
    vid_pid: str | None = None
    serial_number: str | None = None
    description: str = ""


class DeviceLost(Out):
    """A serial device that went away while connected (unplugged, USB reset, brown-out, selective
    suspend, or another program took the port): state ``error``, reason ``device_lost``."""

    arm: Arm
    port: str
    error: str = Field(description='what the OS said, e.g. "Access is denied." or "I/O error"')
    identity: PortIdentity | None = Field(None, description="the USB adapter, to find it again")
    robot: str | None = None
    during: str = Field(description="session kind or state when it happened")
    after_torque_on: bool = Field(
        description="lost within seconds of the follower's torque coming on or a session start: a "
        "far jump may have browned out the follower supply"
    )
    t: float
    detail: str


class Status(Out):
    station: StationInfo
    state: StationState
    sub: Phase | None
    reason: str | None
    detail: str | None
    robot: RobotStatus | None
    cameras: list[CameraStatus]
    health: Health
    alerts: list[Alert] = Field(description="active alerts")
    session: Session | None
    last_session: SessionEnd | None
    server: ServerStatus
    loaded_model: str | None
    program: ProgramState | None = Field(None, description="the current program run (programming only)")
    lost: DeviceLost | None = Field(None, description="the serial device that was lost (state error)")
    interrupted: bool = Field(
        False,
        description="an e-stop / safe stop ended a motion: the arm stands where it froze (the UI offers "
        "POST /robots/rest until a session starts or the rest move completes)",
    )


# --------------------------------------------------------------------------- calibration
class CalibrationMotor(Out):
    min: int | None
    pos: int | None
    max: int | None
    full_turn: bool
    ok: bool = Field(False, description="moved through at least min_range steps (ranges step)")


class CalibrationView(Out):
    arm: Arm
    step: Literal["home", "ranges", "done"]
    motors: dict[str, CalibrationMotor]
    warnings: list[str]
    path: str | None = Field(None, description="written calibration file (step done)")
    min_range: int = Field(100, description="steps each joint must move before Save (LeLab's rule)")
    ready: bool = Field(False, description="every joint moved enough: Save is allowed")


class CalibrationStepResponse(Status):
    calibration: CalibrationView | None = None


class CalibrationFile(Out):
    arm: Arm
    id: str
    path: str
    modified_at: str
    dir: str = Field(
        "so_follower", description="lerobot's folder: so_follower, so_leader or a legacy so101_*"
    )


class CalibrationFiles(Out):
    files: list[CalibrationFile]


class CalibrationCandidate(CalibrationFile):
    own: bool = Field(description="the file this profile's calibration id reads")
    valid: bool = Field(description="a lerobot calibration json")
    matches_motors: bool = Field(description="this arm's motors carry exactly this calibration now")
    matches_other_arm: bool = Field(description="the OTHER arm's motors carry it: never use it here")


class ArmCalibrationCheck(Out):
    arm: Arm
    state: Literal["ok", "adopt", "mismatch", "needs_calibration"] = Field(
        description="ok: calibrated; adopt: the motors carry another file (e.g. LeLab's), use it; "
        "mismatch: the own file exists but the motors do not keep it; needs_calibration: no file"
    )
    calibrated: bool
    calibration_id: str
    file: str
    file_exists: bool
    suggestion: CalibrationCandidate | None = None
    files: list[CalibrationCandidate]
    issue: str | None = None


class CalibrationCheckArms(Out):
    follower: ArmCalibrationCheck | None = None
    leader: ArmCalibrationCheck | None = None


class CalibrationCheck(Out):
    arms: CalibrationCheckArms


class PoseJoint(Out):
    joint: str
    follower: float
    leader: float
    diff: float
    unit: Literal["deg", "%"]
    ok: bool


class PoseCompare(Out):
    """Leader held in the follower's pose: per-joint difference after calibration."""

    joints: list[PoseJoint]
    threshold: float
    ok: bool
    off: list[str] = Field(description="joints further apart than the threshold")
    worst: str | None
    max_diff: float


class ReconnectResult(Status):
    ports: dict[str, str] = Field(description="arm -> serial device now")
    port_changes: dict[str, str] = Field(description="arms whose device name changed (new COM number)")


# --------------------------------------------------------------------------- ports & robots
class Port(Out):
    device: str
    stable_path: str | None
    vid_pid: str | None
    serial_number: str | None
    description: str
    in_use_by: str | None


class Ports(Out):
    ports: list[Port]


class DetectResponse(Out):
    """``unplug`` without ``ports_before`` answers the snapshot; otherwise the detected port."""

    port: Port | None = None
    ports_before: list[str] | None = None


class PortProbe(Out):
    device: str
    voltage_v: float | None = Field(description="median Present_Voltage of the motors")
    motors: int
    model_number: int | None
    firmware: str | None
    role_hint: Literal["leader", "follower"] | None = Field(
        description="~5 V: usually the leader; >= 6.5 V: usually the follower (a hint only)"
    )
    error: str | None
    in_use_by: str | None


class PortProbes(Out):
    ports: list[PortProbe]


class Robots(Out):
    robots: list[RobotProfile]
    active: str | None


class RestPose(Out):
    rest_pose: dict[str, float] | None


# --------------------------------------------------------------------------- cameras
class CameraDefault(Out):
    width: int
    height: int
    fps: int
    fourcc: str | None


class DiscoveredCamera(Out):
    type: Literal["opencv", "realsense", "mock", "held"]
    id: str
    stable_path: str | None
    name: str
    default: CameraDefault | None
    in_use_by: str | None


class DiscoveredCameras(Out):
    cameras: list[DiscoveredCamera]


class ProbeResult(Out):
    ok: bool
    measured_fps: float
    width: int
    height: int
    error: str | None
    warning: Literal["usb_bandwidth"] | None
    snapshot_jpeg_b64: str | None


# --------------------------------------------------------------------------- sessions history
class SessionSummary(Out):
    id: str
    kind: SessionKind | None
    started_at: str | None
    ended_at: str | None
    outcome: str | None
    reason: str | None
    dataset: str | None
    model: str | None
    robot: str | None
    episodes: int | None
    max_temp_c: float | None


class Sessions(Out):
    sessions: list[SessionSummary]


class TelemetrySeries(Out):
    """Aligned series: every value list has the length of ``t`` (``null`` where not sampled)."""

    arm_motors: dict[str, list[str]]
    t: list[float]
    temp_c: dict[str, dict[str, list[float | None]]]
    voltage_v: dict[str, dict[str, list[float | None]]]
    current_a: dict[str, dict[str, list[float | None]]]
    load_pct: dict[str, dict[str, list[float | None]]]
    alerts: list[Alert]


# --------------------------------------------------------------------------- datasets
class UploadRecord(Out):
    server: str
    dataset_id: str | None
    version_id: str | None
    version: int | None
    at: str
    server_url: str | None = None
    train_url: str | None = Field(
        None, description="server New-run wizard with this version preselected (?version=<id>)"
    )


class LocalDataset(Out):
    name: str
    root: str
    episodes: int
    frames: int
    fps: int | None
    robot_type: str | None
    cameras: list[str]
    video: bool
    size_bytes: int
    finalized: bool
    finalize_reasons: list[str]
    task: str | None
    uploads: list[UploadRecord]
    uploaded: UploadRecord | None = Field(description="the latest upload, if any")


class EpisodeSummary(Out):
    index: int
    frames: int | None
    length_s: float | None
    tasks: list[str] | None
    telemetry_lines: int
    max_temp_c: dict[str, dict[str, float]] = Field(description="arm -> motor -> peak °C (sidecar)")


class LocalDatasetDetail(LocalDataset):
    episode_list: list[EpisodeSummary]


class LocalDatasets(Out):
    datasets: list[LocalDataset]


# --------------------------------------------------------------------------- jobs
class JobProgress(Out):
    done: int
    total: int
    unit: Literal["bytes", "steps"]
    phase: Literal[
        "queued", "extracting", "copying", "hashing", "uploading", "downloading", "verifying", "loading"
    ]
    resumed_bytes: int | None = None
    retries: int | None = None


class JobResult(Out):
    """Kind-specific: upload → dataset fields, import/pull → ``model``, load → ``model`` + timings."""

    dataset: str | None = None
    dataset_id: str | None = None
    dataset_name: str | None = None
    version_id: str | None = None
    version: int | None = None
    resumed_parts: int | None = None
    sent_parts: int | None = None
    server_url: str | None = None
    train_url: str | None = None
    model: str | None = None
    key: str | None = None
    device: str | None = None
    policy_type: str | None = None
    load_s: float | None = None
    warmup_ms: float | None = None


class Job(Out):
    id: str
    kind: JobKind
    status: JobStatus
    subject: str | None = Field(description="dataset name (upload) or model key (load); else null")
    progress: JobProgress
    result: JobResult | None
    error: Problem | None


class Jobs(Out):
    jobs: list[Job]


# --------------------------------------------------------------------------- models
class LoadedModel(Out):
    key: str
    device: str
    policy_type: str | None
    load_s: float
    warmup_ms: float


class Models(Out):
    models: list[ModelEntry]
    loaded: str | None = Field(description="key of the loaded model")
    loaded_detail: LoadedModel | None


class CompatFix(Out):
    kind: Literal["set_camera", "map_camera"]
    camera: str | None = None
    key: str | None = None
    width: int | None = None
    height: int | None = None


class CompatCheck(Out):
    id: str
    ok: bool
    code: str | None = None
    expected: list[int] | None = None
    actual: list[int] | None = None
    camera: str | None = None
    available: list[str] | None = None
    fix: CompatFix | None = None
    hint: str | None = None


class CompatDefaults(Out):
    fps: int | None
    task: str | None


class CompatReport(Out):
    ok: bool
    policy_type: str
    device: str
    checks: list[CompatCheck]
    warnings: list[str]
    camera_map: dict[str, str] = Field(description="policy image key -> Station camera name")
    defaults: CompatDefaults


# --------------------------------------------------------------------------- server
class ServerLinkView(Out):
    paired: bool
    url: str | None
    web_url: str | None
    workspace_id: str | None
    workspace: str | None
    workspace_name: str | None
    token_prefix: str | None
    scopes: list[str]


class ServerDataset(Out):
    id: str
    name: str
    latest_version: int | None


class ServerDatasets(Out):
    datasets: list[ServerDataset]


class ServerModel(Out):
    id: str
    name: str
    status: str
    policy_type: str | None
    size_bytes: int | None
    created_at: str | None


class ServerModels(Out):
    models: list[ServerModel]


class ServerRun(Out):
    id: str
    number: int
    status: str
    policy_type: str | None
    progress: float | None = Field(description="0..1 (current_step / total_steps)")
    model_id: str | None = Field(description="model built from the final checkpoint, when ready")
    url: str


class ServerRuns(Out):
    runs: list[ServerRun]
    new_run_url: str


# =========================================================================== control WebSocket (§5.3)
class LoopStats(Out):
    fps: float
    tick_ms_p95: float
    overruns: int
    telemetry_forced: int
    latency_ms_p50: float | None = Field(
        None, description="leader read -> goal sent, plus half a tick (leader-driven sessions)"
    )
    latency_ms_p95: float | None = None
    clip_fraction: float | None = Field(None, description="share of ticks the safety filter changed")
    inference_ms_p50: float | None = None
    inference_ms_p95: float | None = None


class JointArms(Out):
    follower: dict[str, float]
    leader: dict[str, float] | None = None


class MotorSample(Out):
    temp_c: float | None
    voltage_v: float | None
    current_a: float | None
    load_pct: float | None
    status: list[str]
    level: Level
    stale: bool


class MotorLimits(Out):
    max_temp_c: float | None
    min_voltage_v: float | None
    max_voltage_v: float | None
    nominal_voltage_v: float | None
    protection_current_a: dict[str, float]


class HelloMsg(Out):
    type: Literal["hello"]
    v: Literal[1]
    status: Status


class StateMsg(Status):
    type: Literal["state"]


class JointsMsg(Out):
    type: Literal["joints"]
    t: float
    tick: int
    arms: JointArms
    action: dict[str, float] | None = None
    sent: dict[str, float] | None = None
    clipped: list[str]
    loop: LoopStats | None = Field(description="null outside motion sessions")


class TelemetryMsg(Out):
    type: Literal["telemetry"]
    t: float
    arm: Arm
    group: str
    motors: dict[str, MotorSample]
    limits: MotorLimits
    forced: bool


class AlertMsg(Alert):
    type: Literal["alert"]


class CalibrationMsg(CalibrationView):
    type: Literal["calibration"]


class SessionMsg(Session):
    """Session progress; the last one of a session has ``ended: true`` and the end fields."""

    type: Literal["session"]
    ended: bool = False
    reason: str | None = None
    summary: dict[str, Any] | None = None
    loop: SessionLoop | None = None
    max_temp_c: dict[str, float] | None = None


class JobMsg(Job):
    type: Literal["job"]


class ErrorMsg(Out):
    type: Literal["error"]
    action: str
    detail: str


class PongMsg(Out):
    type: Literal["pong"]


ServerMessage = Annotated[
    HelloMsg
    | StateMsg
    | JointsMsg
    | TelemetryMsg
    | AlertMsg
    | CalibrationMsg
    | SessionMsg
    | JobMsg
    | ErrorMsg
    | PongMsg
    | ProgramStateMsg
    | ProgramLogMsg
    | TrajectoryRecordMsg
    | SignalMsg,
    Field(discriminator="type"),
]


class ClientHello(Out):
    type: Literal["hello"]
    v: Literal[1]
    client: str
    heartbeat: bool = False


class ClientHeartbeat(Out):
    type: Literal["heartbeat"]


class ClientEstop(Out):
    type: Literal["estop"]
    relax: bool = False


class ClientControl(Out):
    type: Literal["control"]
    action: ControlAction


class ClientPing(Out):
    type: Literal["ping"]


ClientMessage = Annotated[
    ClientHello | ClientHeartbeat | ClientEstop | ClientControl | ClientPing | ClientProgramInput,
    Field(discriminator="type"),
]


# =========================================================================== video WebSocket (§5.4)
class VideoSubscribe(Out):
    type: Literal["subscribe"]
    cameras: list[str]
    width: int | None = Field(None, ge=160, le=640)
    fps: float | None = Field(None, gt=0, le=30)


class FrameHeader(Out):
    """JSON header of a binary frame: ``"HSF1" | u16 BE header_len | header | JPEG``."""

    cam: str
    tick: int = Field(description="control-loop tick of the frame (-1 outside sessions)")
    t: float
    w: int
    h: int
    src_w: int
    src_h: int
    policy_input: bool
    stale: bool


class CameraErrorMsg(Out):
    type: Literal["camera_error"]
    cam: str
    code: str


class WsSchemas(Out):
    """Container used only to export the WebSocket message schemas into OpenAPI."""

    server_message: ServerMessage
    client_message: ClientMessage
    video_subscribe: VideoSubscribe
    frame_header: FrameHeader
    camera_error: CameraErrorMsg


SERVER_MESSAGE: TypeAdapter[Any] = TypeAdapter(ServerMessage)
CLIENT_MESSAGE: TypeAdapter[Any] = TypeAdapter(ClientMessage)

WS_SCHEMA_NAMES = {"server_message": "ServerMessage", "client_message": "ClientMessage"}


def ws_schemas(ref_template: str = "#/components/schemas/{model}") -> dict[str, Any]:
    """Every WebSocket schema keyed by name, refs pointing at ``components.schemas``."""
    doc = WsSchemas.model_json_schema(ref_template=ref_template)
    defs: dict[str, Any] = dict(doc.get("$defs", {}))
    for prop, name in WS_SCHEMA_NAMES.items():
        defs[name] = doc["properties"][prop]
    defs.pop("WsSchemas", None)
    return defs
