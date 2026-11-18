"""Contract for trajectories, poses, detectors, signals and block programs (station-programs.md §2-§7).

Every REST body, REST response, WebSocket message and on-disk JSON document of the feature is a
pydantic model here (``extra="forbid"``) and is exported into ``openapi.json``; the web UI
types are generated from it. The program AST (§5) is a tree of discriminated unions keyed by
``kind``; the compiler (Blockly JSON → AST) and the interpreter both work on these classes only.

Changing a shape here is a contract change: regenerate ``openapi.json`` and the web UI types in the
same commit (``hibiscus-station openapi`` / ``pnpm gen:api``).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Ids chosen by the user or the server (programs, detectors, poses): same rule as robot ids.
ITEM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
#: Server-made trajectory ids: ``t_<yyyymmdd>_<hhmmss>_<4 hex>``.
TRAJECTORY_ID_RE = re.compile(r"^t_[0-9]{8}_[0-9]{6}_[0-9a-f]{4}$")
#: Signal names (``POST /signals/{name}``, ``signal [name] = [value]``).
SIGNAL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
#: Operator keys: 0-9 and a-z. Space is the e-stop and never a program key.
KEY_RE = re.compile(r"^[0-9a-z]$")
#: Program runs: ``r_<yyyymmdd>_<hhmmss>_<4 hex>`` (``runs/programs/<run_id>.jsonl``).
RUN_ID_RE = re.compile(r"^r_[0-9]{8}_[0-9]{6}_[0-9a-f]{4}$")

ItemId = Annotated[str, Field(pattern=ITEM_ID_RE.pattern)]
TrajectoryId = Annotated[str, Field(pattern=TRAJECTORY_ID_RE.pattern)]
SignalName = Annotated[str, Field(pattern=SIGNAL_NAME_RE.pattern)]
OperatorKey = Annotated[str, Field(pattern=KEY_RE.pattern)]
#: A value a variable or a signal can hold: a number or a text (booleans arrive as 1/0).
Scalar = float | str
#: Joint goals keyed like lerobot actions: ``"shoulder_pan.pos"`` ... ``"gripper.pos"``.
JointMap = dict[str, float]


class Wire(BaseModel):
    """Every model of this feature: unknown fields are an error on both sides."""

    model_config = ConfigDict(extra="forbid")


# =========================================================================== trajectories (§2, §3)
TrajectoryStatus = Literal["draft", "ready", "needs_check"]


class TrimRange(Wire):
    start_s: float = Field(ge=0, description="seconds cut from the start of the raw take")
    end_s: float = Field(ge=0, description="seconds cut from the end of the raw take")


class Trajectory(Wire):
    """``trajectories/<id>/trajectory.json``. The samples live next to it in ``samples.parquet``."""

    id: TrajectoryId
    name: str = Field(min_length=1, max_length=80)
    robot: str = Field(description="robot profile id the take belongs to")
    created_at: str
    updated_at: str
    fps: int = Field(ge=1, le=50, description="sample rate of samples.parquet (the record fps)")
    joints: list[str] = Field(description='parquet columns after "t", e.g. "shoulder_pan.pos"')
    samples: int = Field(ge=0, description="rows in samples.parquet (untrimmed)")
    raw_duration_s: float = Field(ge=0)
    trim: TrimRange
    suggested_trim: TrimRange = Field(description="idle start/end: all joints < 0.5° for > 0.5 s")
    duration_s: float = Field(ge=0, description="raw_duration_s minus the trim, at 100 % speed")
    start_pose: JointMap = Field(description="first sample after the trim")
    end_pose: JointMap = Field(description="last sample after the trim")
    max_speed_deg_s: float = Field(ge=0, description="peak joint speed after the trim (at 100 %)")
    calibration_hash: str = Field(description="follower calibration hash at record time")
    status: TrajectoryStatus = Field(
        description="draft: not saved yet; needs_check: calibration changed, replay at 25 % and confirm"
    )
    checked_at: str | None = Field(description="last confirm after a needs_check replay")
    keyframe_cameras: list[str] = Field(description="cameras with stored keyframes")
    keyframe_times: list[float] = Field(description="seconds from the raw start, one per keyframe index")
    samples_file: Literal["samples.parquet"] = "samples.parquet"


class TrajectorySummary(Trajectory):
    preview: dict[str, list[float]] = Field(
        description="joint -> 64 evenly spaced positions of the trimmed take (list thumbnail)"
    )


class TrajectorySeries(Wire):
    """Decimated samples for the joint plot (at most 600 points, raw time axis)."""

    t: list[float]
    joints: dict[str, list[float]]


class TrajectoryDetail(Trajectory):
    series: TrajectorySeries


class Trajectories(Wire):
    trajectories: list[TrajectorySummary]


class RecordTrajectoryRequest(Wire):
    name: str | None = Field(None, min_length=1, max_length=80, description='default "Take <time>"')
    fps: int = Field(30, ge=1, le=50)
    limit_s: float = Field(60.0, gt=0, le=600, description="time limit of the take")
    countdown_s: float = Field(3.0, ge=0, le=10)
    keyframe_hz: float = Field(1.0, ge=0, le=4, description="camera keyframes stored per second (0 = none)")


class TrajectoryUpdate(Wire):
    """``PUT /trajectories/{id}``: rename, trim, and (for a draft) save."""

    name: str | None = Field(None, min_length=1, max_length=80)
    trim: TrimRange | None = None
    save: bool = Field(False, description="draft -> ready")


class PlayTrajectoryRequest(Wire):
    speed_pct: float = Field(100.0, ge=10, le=150, description="> 100 needs follower.allow_fast_replay")
    approach_speed_deg_s: float | None = Field(
        None, gt=0, le=90, description="move-to-start cap; default settings.programs.approach_speed_deg_s"
    )
    check: bool = Field(
        False, description="the needs_check replay: forced to settings.programs.check_speed_pct"
    )


# =========================================================================== poses (§2)
PoseSource = Literal["live", "trajectory_start", "trajectory_end", "manual"]


class PoseInput(Wire):
    name: ItemId
    positions: JointMap
    source: PoseSource = "manual"
    trajectory: TrajectoryId | None = None


class Pose(PoseInput):
    calibration_hash: str
    created_at: str
    needs_check: bool = Field(description="calibration changed since the pose was saved")


class Poses(Wire):
    """``GET /poses`` and the on-disk ``poses.json``."""

    poses: list[Pose]


class PosesUpdate(Wire):
    """``PUT /poses``: the full list (replace)."""

    poses: list[PoseInput]


class CapturePoseRequest(Wire):
    name: ItemId


# =========================================================================== detectors (§4 camera)
class Roi(Wire):
    """Region of interest, normalised to the source frame (0..1, origin top left)."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class ColorRule(Wire):
    """One label = one OpenCV HSV range (H 0-179; ``h_min > h_max`` wraps around red)."""

    label: str = Field(min_length=1, max_length=40)
    h_min: int = Field(ge=0, le=179)
    h_max: int = Field(ge=0, le=179)
    s_min: int = Field(0, ge=0, le=255)
    s_max: int = Field(255, ge=0, le=255)
    v_min: int = Field(0, ge=0, le=255)
    v_max: int = Field(255, ge=0, le=255)
    min_fraction: float = Field(0.05, gt=0, le=1, description="share of ROI pixels needed to match")


class ColorDetectorSpec(Wire):
    """Label = the rule with the largest matching fraction ≥ its ``min_fraction``, else ``null``;
    confidence = that fraction (0..1)."""

    kind: Literal["color"]
    camera: str = Field(description="default camera (a block may name another)")
    roi: Roi
    rules: list[ColorRule] = Field(min_length=1, max_length=8)


class ClassifierDetectorSpec(Wire):
    """An ONNX image classifier: input ``1x3xSxS`` float32 RGB, output ``1xlen(labels)`` logits."""

    kind: Literal["classifier"]
    camera: str
    roi: Roi | None = None
    labels: list[str] = Field(min_length=2, max_length=64)
    input_size: int = Field(224, ge=32, le=640)
    mean: list[float] = Field(default_factory=lambda: [0.485, 0.456, 0.406], min_length=3, max_length=3)
    std: list[float] = Field(default_factory=lambda: [0.229, 0.224, 0.225], min_length=3, max_length=3)
    min_confidence: float = Field(0.5, ge=0, le=1, description="softmax below this -> label null")
    none_label: str | None = Field(None, description='a label meaning "nothing" (reported as null)')


DetectorSpec = Annotated[ColorDetectorSpec | ClassifierDetectorSpec, Field(discriminator="kind")]


class DetectorInput(Wire):
    name: str = Field(min_length=1, max_length=80)
    spec: DetectorSpec


class Detector(DetectorInput):
    """``detectors/<id>.json`` (+ ``detectors/<id>.onnx`` for a classifier)."""

    id: ItemId
    robot: str
    created_at: str
    updated_at: str
    model_file: str | None = Field(description="classifier: stored ONNX file name, null until uploaded")
    model_sha256: str | None
    labels: list[str] = Field(description="every label the detector can return (rules or classes)")


class Detectors(Wire):
    detectors: list[Detector]


class DetectorTestRequest(Wire):
    camera: str | None = Field(None, description="default: the detector's camera")
    spec: DetectorSpec | None = Field(None, description="test an unsaved spec on this detector id")
    annotate: bool = Field(True, description="return a preview JPEG with the ROI and the match drawn")


class DetectorResult(Wire):
    detector: str | None
    camera: str
    label: str | None
    confidence: float = Field(ge=0, le=1)
    scores: dict[str, float] = Field(description="label -> fraction (color) or softmax (classifier)")
    ms: float = Field(description="evaluation time")
    tick: int = Field(description="control-loop tick of the frame (-1 outside sessions)")
    annotated_jpeg_b64: str | None


# =========================================================================== signals (§4 external)
SignalSource = Literal["http", "mqtt", "program", "ui"]


class SignalIn(Wire):
    """``POST /signals/{name}``."""

    value: Scalar


class Signal(Wire):
    name: SignalName
    value: Scalar
    source: SignalSource
    at: str
    seq: int = Field(description="bus-wide counter, +1 per set (message received = seq moved)")


class Signals(Wire):
    signals: list[Signal]


# =========================================================================== program AST (§4, §5)
# Every node carries ``id``: the Blockly block id it came from (live highlight, traces, issues).
# Values are numbers or texts; conditions are booleans. The compiler type-checks both.
class Node(Wire):
    id: str = Field(description="Blockly block id")


# ---------------------------------------------------------------- values (number / text)
class NumberLit(Node):
    kind: Literal["number"]
    value: float


class TextLit(Node):
    kind: Literal["text"]
    value: str = Field(max_length=500)


class VarRef(Node):
    kind: Literal["var"]
    name: str


class Arith(Node):
    kind: Literal["arith"]
    op: Literal["add", "sub", "mul", "div", "pow", "mod"]
    left: ValueExpr
    right: ValueExpr


class RandomInt(Node):
    kind: Literal["random_int"]
    low: ValueExpr
    high: ValueExpr


class Join(Node):
    kind: Literal["join"]
    parts: list[ValueExpr]


class JointValue(Node):
    """Present position of one follower joint (degrees; gripper 0-100)."""

    kind: Literal["joint_value"]
    joint: str = Field(description='motor name, e.g. "elbow_flex"')


class MotorTemp(Node):
    kind: Literal["motor_temp"]
    motor: str | None = Field(description="null = the hottest follower motor")


class DetectorConfidence(Node):
    kind: Literal["detector_confidence"]
    detector: ItemId
    camera: str | None = None
    label: str | None = Field(None, description="confidence of this label; null = of the best label")


class SignalValue(Node):
    kind: Literal["signal_value"]
    name: SignalName


ValueExpr = Annotated[
    NumberLit
    | TextLit
    | VarRef
    | Arith
    | RandomInt
    | Join
    | JointValue
    | MotorTemp
    | DetectorConfidence
    | SignalValue,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------- conditions (boolean)
class BoolLit(Node):
    kind: Literal["bool"]
    value: bool


class Not(Node):
    kind: Literal["not"]
    operand: CondExpr


class Logic(Node):
    kind: Literal["logic"]
    op: Literal["and", "or"]
    left: CondExpr
    right: CondExpr


class Compare(Node):
    """Numbers compare numerically; texts only with eq/ne. Covers ``joint [j] [<,>] [deg]``,
    ``motor temperature [>] [°C]`` and ``[detector] confidence > [x]``."""

    kind: Literal["compare"]
    op: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    left: ValueExpr
    right: ValueExpr


class CameraSees(Node):
    kind: Literal["camera_sees"]
    detector: ItemId
    camera: str | None = Field(None, description="null = the detector's camera")
    label: str


class ButtonPressed(Node):
    """True once per press: a press latches until a condition reads it (then it is consumed)."""

    kind: Literal["button_pressed"]
    button: ItemId


class KeyPressed(Node):
    kind: Literal["key_pressed"]
    key: OperatorKey


class GripperHolding(Node):
    kind: Literal["gripper_holding"]


class NearPose(Node):
    kind: Literal["near_pose"]
    pose: ItemId
    tolerance_deg: float = Field(3.0, gt=0, le=45)


class SignalEquals(Node):
    kind: Literal["signal_equals"]
    name: SignalName
    value: Scalar


class MessageReceived(Node):
    """True when a new message arrived since the previous evaluation of this node (run start for the
    first one). ``source`` http = ``POST /signals/{name}``; mqtt = topic ``name``."""

    kind: Literal["message_received"]
    source: Literal["http", "mqtt"]
    name: str = Field(min_length=1, max_length=200)


CondExpr = Annotated[
    BoolLit
    | Not
    | Logic
    | Compare
    | CameraSees
    | ButtonPressed
    | KeyPressed
    | GripperHolding
    | NearPose
    | SignalEquals
    | MessageReceived,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------- statements
class MotionNode(Node):
    timeout_s: float | None = Field(
        None, gt=0, le=3600, description="null = automatic (expected duration + approach + 5 s)"
    )


class PlayTrajectoryStmt(MotionNode):
    kind: Literal["play_trajectory"]
    trajectory: TrajectoryId
    speed_pct: float = Field(100.0, ge=10, le=150)


class MoveToPoseStmt(MotionNode):
    kind: Literal["move_to_pose"]
    pose: ItemId
    speed_deg_s: float = Field(30.0, gt=0, le=90)


class GripperStmt(MotionNode):
    kind: Literal["gripper"]
    action: Literal["open", "close", "set"]
    percent: float | None = Field(None, ge=0, le=100, description="set only (0 closed, 100 open)")


class GoHomeStmt(MotionNode):
    """To the profile's ``rest_pose`` at ``settings.programs.approach_speed_deg_s``."""

    kind: Literal["go_home"]


class RelaxArmStmt(MotionNode):
    """Park (rest pose) and torque off; the next motion block turns torque back on."""

    kind: Literal["relax_arm"]


class RunModelStmt(MotionNode):
    """The existing policy runner (``inferring`` code path) inside the program. Exactly one of
    ``duration_s`` / ``until``. ``timeout_s`` bounds the ``until`` form (default 30 s)."""

    kind: Literal["run_model"]
    model: str = Field(description="model key (models/index.json)")
    task: str = Field("", max_length=500)
    duration_s: float | None = Field(None, gt=0, le=600)
    until: CondExpr | None = None
    on_timeout: list[Stmt] | None = Field(None, description="null = stop the program on timeout")


class IfBranch(Wire):
    cond: CondExpr
    body: list[Stmt]


class IfStmt(Node):
    kind: Literal["if"]
    branches: list[IfBranch] = Field(min_length=1, description="if / else if ...")
    else_body: list[Stmt] | None = None


class RepeatStmt(Node):
    kind: Literal["repeat"]
    times: ValueExpr
    body: list[Stmt]


class ForeverStmt(Node):
    """Rejected at compile time when the body has no motion and no wait (busy loop)."""

    kind: Literal["forever"]
    body: list[Stmt]


class WhileStmt(Node):
    kind: Literal["while"]
    mode: Literal["while", "until"]
    cond: CondExpr
    body: list[Stmt]


class WaitStmt(Node):
    kind: Literal["wait"]
    seconds: ValueExpr


class WaitUntilStmt(Node):
    kind: Literal["wait_until"]
    cond: CondExpr
    timeout_s: float = Field(30.0, gt=0, le=86400)
    on_timeout: list[Stmt] | None = Field(None, description="null = stop the program on timeout")


class StopStmt(Node):
    kind: Literal["stop"]


class SetVarStmt(Node):
    kind: Literal["set_var"]
    name: str
    value: ValueExpr


class ChangeVarStmt(Node):
    kind: Literal["change_var"]
    name: str
    by: ValueExpr


class AskStmt(Node):
    """``ask operator [question] → choice``: shows the choices on the run screen and stores the
    chosen text in the text variable ``var``."""

    kind: Literal["ask"]
    question: str = Field(min_length=1, max_length=200)
    choices: list[str] = Field(min_length=1, max_length=8)
    var: str
    timeout_s: float | None = Field(None, gt=0, le=86400, description="null = wait forever")


class LogStmt(Node):
    kind: Literal["log"]
    text: ValueExpr


class NotifyStmt(Node):
    kind: Literal["notify"]
    text: ValueExpr
    webhook: bool = Field(False, description="also POST to settings.programs.notify_webhook")


class SetSignalStmt(Node):
    kind: Literal["set_signal"]
    name: SignalName
    value: ValueExpr


Stmt = Annotated[
    PlayTrajectoryStmt
    | MoveToPoseStmt
    | GripperStmt
    | GoHomeStmt
    | RelaxArmStmt
    | RunModelStmt
    | IfStmt
    | RepeatStmt
    | ForeverStmt
    | WhileStmt
    | WaitStmt
    | WaitUntilStmt
    | StopStmt
    | SetVarStmt
    | ChangeVarStmt
    | AskStmt
    | LogStmt
    | NotifyStmt
    | SetSignalStmt,
    Field(discriminator="kind"),
]
#: The motion statements: the interpreter hands exactly these to ``MotionPort.submit``.
MotionStmt = PlayTrajectoryStmt | MoveToPoseStmt | GripperStmt | GoHomeStmt | RelaxArmStmt | RunModelStmt
MOTION_KINDS = frozenset({"play_trajectory", "move_to_pose", "gripper", "go_home", "relax_arm", "run_model"})


class VarDecl(Wire):
    name: str = Field(min_length=1, max_length=40)
    type: Literal["number", "text"]
    initial: Scalar


class OperatorButton(Wire):
    name: ItemId
    label: str = Field(min_length=1, max_length=40)


class ProgramAst(Wire):
    """The compiled program. ``body`` is the stack under the single ``hb_start`` block."""

    version: Literal[1] = 1
    variables: list[VarDecl]
    buttons: list[OperatorButton]
    keys: list[OperatorKey] = Field(description="keys the program reads (shown on the run screen)")
    body: list[Stmt]


# =========================================================================== programs (§5, §6)
IssueCode = Literal[
    "no_start_block",
    "many_start_blocks",
    "unknown_block",
    "missing_input",
    "bad_field",
    "type_mismatch",
    "unknown_variable",
    "unknown_trajectory",
    "trajectory_draft",
    "trajectory_needs_check",
    "unknown_pose",
    "pose_needs_check",
    "no_rest_pose",
    "unknown_detector",
    "detector_no_model",
    "unknown_label",
    "unknown_camera",
    "unknown_model",
    "unknown_button",
    "unknown_joint",
    "busy_loop",
    "unreachable",
    "first_motion_far",
    "fast_replay",
    "fast_replay_not_allowed",
    "relax_in_loop",
    "too_many_blocks",
]


class CheckIssue(Wire):
    id: str = Field(description='stable "<code>:<block_id>"; confirmations echo it in RunProgramRequest')
    code: IssueCode
    severity: Literal["error", "warning", "confirm", "info"] = Field(
        description="error blocks a run; confirm needs an explicit ack in the run request; warning and "
        "info never block (info is not a problem: it says what the run will do, e.g. the slow approach "
        "to the first motion)"
    )
    block_id: str | None
    message_key: str = Field(description='UI string "programs.issues.<code>"')
    params: dict[str, Any]


class ProgramRefs(Wire):
    trajectories: list[str]
    poses: list[str]
    detectors: list[str]
    models: list[str]
    signals: list[str]
    cameras: list[str]


class ProgramInput(Wire):
    """``PUT /programs/{id}``: the editor document; the server compiles it."""

    name: str = Field(min_length=1, max_length=80)
    editor: dict[str, Any] = Field(description="Blockly.serialization.workspaces.save() output")
    buttons: list[OperatorButton] = Field(default_factory=list, max_length=12)


class Program(Wire):
    """``programs/<id>/program.json``: editor JSON + compiled AST (null while it does not compile)."""

    id: ItemId
    name: str
    robot: str
    version: int = Field(ge=1, description="+1 on every save")
    created_at: str
    updated_at: str
    editor: dict[str, Any]
    buttons: list[OperatorButton]
    ast: ProgramAst | None
    issues: list[CheckIssue]
    refs: ProgramRefs
    dry_run_version: int | None = Field(description="the last version that completed a dry run")


ProgramOutcome = Literal["completed", "stopped", "failed", "estopped", "timeout"]


class ProgramRunSummary(Wire):
    run_id: str
    program_id: str
    version: int
    started_at: str
    ended_at: str | None
    outcome: ProgramOutcome | None = Field(description="null while running")
    dry_run: bool
    steps: int = Field(description="statements executed")
    faults: int


class ProgramSummary(Wire):
    id: ItemId
    name: str
    version: int
    updated_at: str
    ok: bool = Field(description="compiles and has no error issue")
    refs: ProgramRefs
    dry_run_version: int | None
    last_run: ProgramRunSummary | None


class Programs(Wire):
    programs: list[ProgramSummary]


class CheckReport(Wire):
    """``POST /programs/{id}/check``: compile + validate against the live stores and profile."""

    ok: bool = Field(description="no error issue (confirm issues still need an ack to run)")
    version: int
    issues: list[CheckIssue]
    ast: ProgramAst | None
    dry_run_required: bool = Field(description="hardware run refused until this version passes a dry run")


class RunProgramRequest(Wire):
    dry_run: bool = Field(False, description="mock arm + synthetic camera + fake-able conditions (§5.2)")
    confirm: list[str] = Field(default_factory=list, description="ids of the confirm issues acknowledged")
    fps: int = Field(30, ge=1, le=50)


ProgramStatus = Literal[
    "starting",
    "running",
    "waiting",
    "pausing",
    "paused",
    "stopping",
    "completed",
    "stopped",
    "failed",
    "estopped",
    "timeout",
]


class WaitInfo(Wire):
    kind: Literal["wait", "wait_until", "ask", "motion", "run_model"]
    block_id: str
    since_s: float = Field(description="seconds since the program started, when the wait began")
    timeout_s: float | None


class AskPrompt(Wire):
    block_id: str
    question: str
    choices: list[str]


class ConditionValue(Wire):
    block_id: str
    value: bool | float | str | None = Field(description="null = could not be evaluated (see message)")
    t: float
    message: str | None = None


class ProgramState(Wire):
    """Live view of the running program (REST answers of pause/resume/stop/input, WS program_state)."""

    run_id: str
    program_id: str
    version: int
    dry_run: bool
    status: ProgramStatus
    block_id: str | None = Field(description="the statement being executed (highlight)")
    block_kind: str | None
    t: float = Field(description="seconds since the program started")
    steps: int
    variables: dict[str, Scalar]
    conditions: list[ConditionValue] = Field(description="the last value of each evaluated condition")
    waiting: WaitInfo | None
    ask: AskPrompt | None
    buttons: list[OperatorButton]
    keys: list[OperatorKey]
    message: str | None = Field(description="end reason or fault text")


class OperatorInput(Wire):
    """``POST /programs/current/input`` and WS ``program_input``."""

    kind: Literal["button", "key", "answer"]
    value: str = Field(min_length=1, max_length=80, description="button name, key, or chosen answer")


class FakeDetector(Wire):
    label: str | None
    confidence: float = Field(1.0, ge=0, le=1)


class FakeConditions(Wire):
    """``POST /programs/current/fake``: dry runs only. Overrides stay until cleared or the run ends."""

    detectors: dict[str, FakeDetector] = Field(default_factory=dict, description="detector id -> result")
    gripper_holding: bool | None = None
    clear: bool = Field(False, description="drop every override first")


ProgramLogKind = Literal[
    "start",
    "block",
    "condition",
    "variable",
    "motion",
    "input",
    "log",
    "notify",
    "signal",
    "timeout",
    "fault",
    "end",
]


class ProgramLogLine(Wire):
    """One line of ``runs/programs/<run_id>.jsonl`` (also WS ``program_log``)."""

    run_id: str
    seq: int
    t: float
    level: Literal["info", "warn", "error"]
    kind: ProgramLogKind
    block_id: str | None
    message: str
    data: dict[str, Any]


class ProgramRuns(Wire):
    runs: list[ProgramRunSummary]


class ProgramRunLog(Wire):
    summary: ProgramRunSummary
    lines: list[ProgramLogLine]


# =========================================================================== block catalogue (§5)
BlockInputKind = Literal["value", "condition", "statement"]
BlockFieldKind = Literal[
    "number",
    "text",
    "checkbox",
    "dropdown",
    "variable",
    "trajectory",
    "pose",
    "detector",
    "label",
    "camera",
    "model",
    "button",
    "key",
    "joint",
    "motor",
    "signal",
]


class BlockField(Wire):
    name: str
    kind: BlockFieldKind
    options: list[str] | None = Field(None, description="dropdown values (the serialized field value)")
    min: float | None = None
    max: float | None = None
    default: Scalar | bool | None = None
    optional: bool = False


class BlockInput(Wire):
    name: str
    kind: BlockInputKind
    check: Literal["number", "text", "any"] | None = Field(None, description="value inputs only")
    optional: bool = False
    repeated: bool = Field(False, description='numbered inputs "<name>0", "<name>1"... (mutator)')


class BlockSpec(Wire):
    type: str = Field(description="Blockly block type in the serialized JSON")
    category: Literal["start", "motion", "ai", "control", "conditions", "data", "output", "operator"]
    output: Literal["statement", "number", "text", "boolean", "hat"]
    ast: str = Field(description="AST kind it compiles to (an expression kind for value blocks)")
    fields: list[BlockField]
    inputs: list[BlockInput]


class BlockCatalog(Wire):
    """``GET /programs/blocks``: the blocks the server compiler accepts (normative for the editor)."""

    version: Literal[1] = 1
    blocks: list[BlockSpec]


# =========================================================================== control WebSocket additions
class ProgramStateMsg(ProgramState):
    type: Literal["program_state"]


class ProgramLogMsg(ProgramLogLine):
    type: Literal["program_log"]


class TrajectoryRecordMsg(Wire):
    """Progress of a ``recording_traj`` session (≤ 5 Hz, plus phase changes and the final one)."""

    type: Literal["trajectory_record"]
    session_id: str
    phase: Literal["countdown", "capture", "saving", "done"]
    elapsed_s: float
    limit_s: float
    samples: int
    trajectory_id: TrajectoryId | None = Field(description="set on the final message (the draft)")
    ended: bool


class SignalMsg(Signal):
    type: Literal["signal"]


class ClientProgramInput(OperatorInput):
    type: Literal["program_input"]


for _m in (
    Arith,
    RandomInt,
    Join,
    Not,
    Logic,
    Compare,
    RunModelStmt,
    IfBranch,
    IfStmt,
    RepeatStmt,
    ForeverStmt,
    WhileStmt,
    WaitUntilStmt,
    ProgramAst,
    Program,
    CheckReport,
):
    _m.model_rebuild()
