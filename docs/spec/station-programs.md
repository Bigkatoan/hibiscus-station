# Hibiscus Station: trajectories and block programs (draft spec v0.1)

Status: implemented in Station 0.2.0 (draft spec v0.1, 2026-11-16). Extends [station.md](station.md)
(contract v0.1); section numbers like §4.7 refer to that file.

Station today drives the arm in two ways: a human (teleop, record) or an AI policy (run model).
This adds a third way that needs no training: **record a motion once, replay it on demand, and
chain motions with conditions in a drag-and-drop block program.**

Example: record trajectories A and B. When the camera sees a red cube, run A;
when it sees a blue cube, run B; repeat.

## 1. Decisions (2026-11-16)

| Topic | Decision |
|---|---|
| Recording a trajectory | With the **leader arm**, the same way as teleop. Hand-guiding the follower and waypoint editing come later (§9) |
| Condition sources in v1 | **All four**: camera recognition, operator buttons/keys, robot state, external signals |
| Editor | Drag-and-drop blocks with if/else, loops, waits, variables |

## 2. Concepts

| Thing | What it is | Stored as |
|---|---|---|
| **Trajectory** | One recorded follower motion: joint and gripper goals sampled at the control rate (30–50 Hz), plus the start pose | `~/.hibiscus/station/trajectories/<id>/trajectory.json` + `samples.parquet` (`t, joint_1..n, gripper`) |
| **Pose** | One named joint configuration (e.g. `home`, `above_bin`). Taken from a trajectory's first/last frame or saved live | `poses.json` per robot profile |
| **Detector** | A named camera check that returns a label: colour-in-region, or an AI classifier | `detectors/<id>.json` (+ model file for classifiers) |
| **Program** | A block program (tree) that moves the arm, reads conditions and branches | `programs/<id>/program.json` (editor JSON + compiled AST) |

Trajectories, poses, detectors and programs belong to a **robot profile** (they depend on its
calibration). Changing the calibration marks them "needs check" (§6).

## 3. Recording and replaying a trajectory

### 3.1 Record (state `recording_traj`, new)
1. Start checks as §4.7 (calibration present, motors not hot, leader connected).
2. Countdown 3 s, then teleop at the profile fps. Every tick stores the **follower goal after the
   SafetyFilter**, so the replay never asks for more than was actually commanded.
3. Stop with the button, a key, or the time limit (60 s default, 600 s max).
4. The UI shows a joint plot and the camera frames from the take. The user names it, trims the
   start/end idle (auto-suggested: frames where all joints move < 0.5° for > 0.5 s), and saves.

### 3.2 Replay (state `playing`, extends the existing `replaying`)
* **Approach**: if the arm is more than 3° (any joint) from the trajectory's first frame, move there
  first with a smooth minimum-jerk approach at a capped speed (default 30°/s). The user sees "moving
  to start" and can stop.
* **Speed**: 10–150 % time scaling (resampled, not skipped frames). Above 100 % needs the profile
  flag `allow_fast_replay`.
* **Safety**: everything in §4.7 applies unchanged: relative-target cap, calibrated range clamp,
  ThermalGuard, e-stop (Space), dead-man heartbeat, loop overrun warning.
* **Mirror/offset (later)**: replay relative to the current pose instead of absolute.

## 4. Conditions (all four sources)

Every condition is evaluated in the program interpreter between motion steps, or continuously
in `wait until` and `while` blocks (at most 10 Hz, never inside the control tick).

| Source | Blocks | v1 implementation |
|---|---|---|
| **Camera** | `camera [cam] sees [detector] = [label]`, `[detector] confidence > [x]` | (a) **Colour in region**: HSV range + ROI drawn on the live preview, label = which colour rule matched, or none. Pure OpenCV, CPU, ~2 ms. (b) **Image classifier**: a small model (e.g. MobileNetV3/ResNet18 fine-tune) trained from frames grabbed in Station; training can run on the Hibiscus server later. v1 ships (a) and runs ONNX classifiers for (b); the training UI is a follow-up |
| **Operator** | `button [name] pressed`, `key [k] pressed`, `ask operator [question] → choice` | Buttons defined per program and shown big on the run screen; keys 0–9 and letters (Space stays e-stop) |
| **Robot state** | `gripper holding object`, `joint [j] [<,>] [deg]`, `near pose [P]`, `motor temperature [>] [°C]` | Holding = gripper goal–position gap and load above a per-profile threshold after closing; calibrated on a test grasp |
| **External** | `signal [name] = [value]`, `HTTP/MQTT message received` | `POST /api/v1/signals/{name}` on 127.0.0.1 (token as other API calls), optional MQTT client (broker URL in settings). GPIO via a small adapter later |

## 5. Block language

The editor is **Blockly** (Apache-2.0), themed with the Hibiscus design system (Nunito, palette
tokens, PxIcon glyphs in block labels, light/dark). Programs are saved as Blockly JSON and
**compiled to a typed AST on the server**; the browser never executes the program.

| Category | Blocks |
|---|---|
| Motion | `play trajectory [A] at [100]%`, `move to pose [P] at [30]°/s`, `gripper open / close / to [%]`, `go home`, `relax arm` |
| AI | `run model [policy] for [N] s` or `until [condition]` (existing `inferring` session) |
| Control | `if / else if / else`, `repeat [N] times`, `repeat forever`, `repeat while / until`, `wait [s]`, `wait until [condition] (timeout [s])`, `stop program` |
| Conditions | the §4 sources, `and / or / not`, compare numbers |
| Data | variables (number, text), `set / change by`, counters, `random` |
| Output | `log [text]`, `notify [text]` (toast + optional webhook), `set signal [name] = [value]` |

### 5.1 Interpreter
* Runs on the Station owner thread as a new motion session `programming` (state machine §4.4: one
  motion session at a time). Each motion block reuses the record/replay/infer code paths, so
  safety is identical.
* Step budget and loop guard: a `repeat forever` with no motion or wait inside is rejected at
  compile time; every loop iteration yields to the owner thread.
* **E-stop always wins**: e-stop freezes the arm (§4.7) and aborts the program; it does not resume
  by itself. `Pause` (UI) finishes the current motion block, then waits.
* `wait until` and every motion have a timeout (default 30 s for waits); on timeout the program
  goes to the block's `on timeout` branch or stops with a clear message.
* **Highlight**: the running block is highlighted live in the editor; variables and the last
  condition values are shown on the side.

### 5.2 Dry run
`Mock` mode (existing `--mock`) runs the whole program against the simulated arm and synthetic
camera, with buttons to fake conditions (e.g. "camera sees: red"). Required before the first run
on hardware after an edit (can be skipped by an admin setting). A dry run passes when it ends `completed`, or
`stopped` by the operator after at least one motion block completed in the simulation (a `repeat
forever` program never completes by itself; a program without motion blocks needs no motion), in
both cases without a fault; an e-stop, a fault or a timeout is no pass.

## 6. Validation and safety rules
* A program is checked before it runs: referenced trajectories/poses/detectors exist and match the
  profile's calibration hash; motion blocks are reachable only from the start; no infinite loop
  without a wait or motion; the first motion starts within the approach limits.
* Calibration changed since a trajectory was recorded → the trajectory is marked "needs check"
  and must be replayed once at 25 % speed and confirmed before programs can use it.
* Speed above 100 % and `relax arm` inside loops need explicit confirmation in the editor.
* `relax arm` and `go Home` need the robot's Home (`no_rest_pose`, an error). Decision 0.2.9
  (CR-2): a program never relaxes without a Home, because `relax arm` first parks at Home and only
  then turns torque off, so the arm never drops from a raised pose with nobody holding it. The
  editor's problem list offers "Set Home now" in place and re-checks the program. Outside programs
  every Relax button asks the operator to support the arm first.
* A Stop of a program run holds the arm where it is (CR-1); "Return Home" / "Relax" follow.
* Every run writes a log: program version, block trace, condition values, timings, faults
  (`runs/programs/<ts>.jsonl`), visible in the UI.

## 7. API additions (`/api/v1`, Station)

| Method | Path | Purpose |
|---|---|---|
| POST | `/trajectories/record` (start), `/trajectories/record/stop` | record a take |
| GET/PUT/DELETE | `/trajectories`, `/trajectories/{id}` | list, rename/trim, delete |
| POST | `/trajectories/{id}/play` | replay with `speed` |
| GET/PUT | `/poses` | named poses |
| GET/PUT/DELETE | `/detectors`, `/detectors/{id}`; POST `/detectors/{id}/test` | define and test camera checks on a live frame |
| GET/PUT/DELETE | `/programs`, `/programs/{id}`; POST `/programs/{id}/check`, `/run`, `/pause`, `/stop` | edit, validate, run |
| POST | `/signals/{name}` | external signal in |
| WS | control WS: new messages `program_state` (current block id, variables), `program_log` | live view |

Everything stays on 127.0.0.1 with the existing token (§8 of station.md).

## 8. UI
New screen **"Chương trình"** with three tabs:
1. **Quỹ đạo**: record with the leader, list with thumbnail plot, play at a chosen speed, trim, rename.
2. **Nhận diện**: camera preview, draw a region, pick colours or choose a classifier, then see the
   live label and confidence.
3. **Chương trình**: Blockly editor in the Hibiscus theme, a run panel with big Start/Pause/Stop
   and the operator buttons, the camera previews, and a live trace (current block highlighted).

Hibi mood: `working` while a program runs, `sleep` while it waits for a condition, `sad` on stop
by fault or e-stop.

## 9. Out of scope for v1 (planned)
* Hand-guided recording (torque off, kinesthetic) and waypoint editing of trajectories.
* Classifier training UI inside Station (v1 runs an ONNX classifier exported elsewhere; a Hibiscus
  server job type "image classifier" is the natural follow-up).
* Cartesian moves / inverse kinematics, relative (offset) replay.
* GPIO adapters; multi-robot programs.
* Sharing programs through the Hibiscus server (upload/pull like models).

## 10. Delivery plan

| Step | Content | Done when |
|---|---|---|
| P1 | Trajectory record/replay (backend session + UI tab), poses | Record A and B with the leader, replay at 50/100 % in mock and on the real SO-101, e-stop works mid-replay |
| P2 | Interpreter + AST + validator, control/data/output blocks, operator buttons/keys, robot-state conditions | The A/B program runs with keys 1/2 in mock, with a trace |
| P3 | Blockly editor in Hibiscus theme, live highlight, dry run | Program built only with the mouse; screenshots light/dark, 1280 and 390 px |
| P4 | Camera detectors (colour-in-region, ONNX classifier), external signals (HTTP, MQTT) | Red/blue cube demo: camera picks A or B |
| P5 | Hardware UAT on SO-101 (checklist like station-hardware-uat.md) | Owner signs off |

## 11. State machine additions (contract)

Three motion states join station.md §4.4. They follow every rule there: one motion session at a
time, `start_*` outside `idle` is `409 busy`, every exit goes through `stopping`, any motion state
goes to `estopped` on e-stop / thermal critical / electrical fault and to `error` on bus loss.

| State | Session `kind` | Sub-phases (`Status.sub`) | Driven by | Dead-man | Allowed commands |
|---|---|---|---|---|---|
| `recording_traj` | `traj_record` | `approach` → `countdown` → `capture` → `done` | leader (teleop path); each tick stores the goal **after** the SafetyFilter | off (a human holds the leader) | record/stop, control `stop`, e-stop |
| `playing` | `traj_play` | `approach` (move to start) → `replay` → `done` | `TrajectoryPlayer` | on | control `stop`, e-stop |
| `programming` | `program` | `running` · `waiting` (wait, wait until, ask) · `paused` · `approach`/`replay`/`episode` while a motion block runs | `ProgramSession` + the program runner thread | on | programs pause/resume/stop/input, control `stop`, e-stop |

```
idle ──POST /trajectories/record──▶ recording_traj ──stop | limit──▶ stopping ──▶ idle   (draft saved)
idle ──POST /trajectories/{id}/play──▶ playing ──end | stop──▶ stopping ──▶ idle
idle ──POST /programs/{id}/run──▶ programming ──completed | stop | fault | timeout──▶ stopping ──▶ idle
{recording_traj, playing, programming} ──estop | thermal critical | electrical──▶ estopped ──reset──▶ idle
{recording_traj, playing, programming} ──bus lost──▶ error
programming.running ⇄ programming.waiting        (runner, ≤ condition_hz)
programming.running ──pause──▶ (finish motion block) ──▶ programming.paused ──resume──▶ programming.running
```
* Start checks (station.md §4.7) apply to all three; `recording_traj` also needs the leader
  (`leader_far` as teleop). `playing` and `programming` refuse `motor_hot`, `not_calibrated`, and
  `needs_check` (a trajectory whose calibration hash changed; only a `check` replay is allowed).
* `playing` above 100 % needs `follower.allow_fast_replay` (`409 fast_replay_not_allowed`).
* E-stop: the owner freezes the arm within the tick, then `stopping` → `estopped`. In
  `programming` the teardown calls `ProgramRuntime.abort("estopped")`; the program never resumes
  by itself. In `playing` the player is dropped at the same tick.
* **Dry runs** (`RunProgramRequest.dry_run`) never enter `programming` and never touch the owner:
  the runner drives a `SimMotionPort` (simulated arm + synthetic camera + `FakeConditions`). The
  Station state stays as it is (`idle` or `disconnected`); `program_state` messages carry
  `dry_run: true`. The runner still aborts on an e-stop press (`SimMotionPort.aborted` follows the
  owner's e-stop event).
* Hibi mood: `working` in all three states, `sleep` when `programming.waiting`, `sad` on an end by
  fault or e-stop.

## 12. Implementation map

### 12.1 Module layout and ownership

Contract files (architect; a team that needs a change asks for it, and the change regenerates
`openapi.json` + `schema.d.ts` in the same commit):
`hibiscus_station/programs/{schemas,interfaces,blocks,paths,api_common,hub}.py`, the
additions in `api/schemas.py`, `errors.py`, `settings.py` (`ProgramSettings`), `profiles.py`
(`allow_fast_replay`, `grip_hold`), `hw/owner.py` (`MOTION_STATES`), `openapi.json`,
`web/src/station/api/{schema.d.ts,types.ts}`, `tests/test_programs_contract.py`.

| Team | Owns (creates / fills) | Tests |
|---|---|---|
| **A** backend: trajectories, poses, motion | `programs/calibration_ref.py` (`calibration_hash`), `programs/trajectories.py` (`TrajectoryStore`: parquet I/O, trim + idle suggestion, preview/series decimation, keyframes, needs_check), `programs/poses.py` (`PoseStore`), `programs/motion.py` (minimum-jerk `PoseMove`, `GripperMove`, `GoHome`, `RelaxArm`, `PolicyMotion` reusing `sessions/run.py`), `programs/player.py` (`TrajectoryPlayer`), `programs/sim_port.py` (`SimMotionPort` for dry runs), `sessions/traj_record.py`, `sessions/traj_play.py`, `sessions/program.py` (`ProgramSession`, implements `MotionPort`), `programs/api_trajectories.py` (fill the stubs), `ProgramsHub.trajectories/poses/calibration_hash` | `tests/test_trajectories.py`, `tests/test_traj_sessions.py` (record A and B in mock, replay 50/100 %, e-stop mid-replay within one tick, approach), `tests/test_program_session.py` (fake `ProgramRuntime`) |
| **B** backend: detectors, signals, conditions, programs | `programs/detectors.py` (`DetectorStore`, `load_detector` → colour / ONNX runtimes; `onnxruntime` pinned exact), `programs/signals.py` (`SignalBus`, optional MQTT client pinned exact), `programs/conditions.py` (all §4 conditions incl. robot state from `RobotSnapshot`, operator latches, fakes), `programs/compiler.py` (Blockly JSON → `ProgramAst` + issues, per `blocks.py`), `programs/validator.py` (`CheckReport` against stores, profile, settings), `programs/interpreter.py` (`ProgramRuntime`, runner thread), `programs/runlog.py` (`RunLog`), `programs/store.py` (`ProgramStore`), `programs/api_detectors.py`, `programs/api_programs.py` (fill the stubs; `Station.start_program` lives in `api_programs.py` or a new `programs/service.py`), the `program_input` branch of `api/ws.py`, `ProgramsHub.detectors/programs/signals` | `tests/test_detectors.py`, `tests/test_signals.py`, `tests/test_compiler.py`, `tests/test_interpreter.py` (fake `MotionPort`), `tests/test_programs_api.py` (the A/B program with keys 1/2 in mock, trace) |
| **C** frontend | `web/src/station/pages/programs/*` (screen "Chương trình": tabs Quỹ đạo, Nhận diện, Chương trình), `web/src/station/programs/blockly/*` (Hibiscus theme, block definitions generated from `GET /programs/blocks`, toolbox), new hooks in `api/hooks.ts`, WS handling of `program_state`/`program_log`/`trajectory_record`/`signal` in `ws/store.ts`, nav entry and route, MSW handlers + sim (`mock/handlers.ts`, `mock/sim.ts`), `i18n/{en,vi}.json` section `programs.*` (incl. `programs.issues.<IssueCode>`); `blockly` pinned exact | vitest per component + screens; light/dark screenshots at 1280 and 390 px |

Shared-file rule: `station.py`, `app.py`, `api/ws.py` and `hw/owner.py` get small additive edits
only (one method or one branch), each in a separate hunk, so the three branches merge cleanly.

### 12.2 Storage on disk
```
~/.hibiscus/station/
├── robots/<robot_id>/                              # RobotDataPaths(home, robot_id)
│   ├── trajectories/<t_yyyymmdd_hhmmss_xxxx>/
│   │   ├── trajectory.json                         # Trajectory
│   │   ├── samples.parquet                         # t (float64 s) + one float64 column per joint name, untrimmed
│   │   └── keyframes/<camera>/<index:04d>.jpg      # ≤ 320 px wide, at RecordTrajectoryRequest.keyframe_hz
│   ├── poses.json                                  # Poses
│   ├── detectors/<id>.json  (+ <id>.onnx)          # Detector
│   └── programs/<id>/program.json                  # Program (editor JSON + AST + issues)
└── runs/programs/<r_yyyymmdd_hhmmss_xxxx>.jsonl    # ProgramLogLine per line; first kind=start, last kind=end
```
Dirs 0700, files 0600, atomic writes (`settings.write_private`). Ids are validated by
`programs/paths.py` (no traversal). Joint names are lerobot action keys (`shoulder_pan.pos` …
`gripper.pos`), not `joint_1..n`.

### 12.3 Interfaces between the teams (normative text in `programs/interfaces.py`)

**Owner thread (A) ↔ runner thread (B).**
```python
class MotionPort(Protocol):                       # sessions/program.py ProgramSession, programs/sim_port.py
    @property
    def aborted(self) -> bool: ...
    def submit(self, stmt: MotionStmt) -> MotionHandle: ...
    def snapshot(self) -> RobotSnapshot: ...

class MotionHandle(Protocol):
    def wait(self, timeout: float | None = None) -> MotionResult | None: ...
    def cancel(self) -> None: ...
    @property
    def result(self) -> MotionResult | None: ...

@dataclass(frozen=True)
class MotionResult:
    outcome: Literal["completed", "cancelled", "timeout", "aborted", "failed"]
    detail: str | None = None
    elapsed_s: float = 0.0

class ProgramRuntime(Protocol):                   # programs/interpreter.py
    def start(self, port: MotionPort) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self, reason: str = "stopped") -> None: ...
    def abort(self, reason: str) -> None: ...
    def input(self, ev: OperatorInput) -> None: ...
    def fake(self, fakes: FakeConditions) -> None: ...
    @property
    def finished(self) -> bool: ...
    @property
    def outcome(self) -> str | None: ...
    def state(self) -> ProgramState: ...
```
`ProgramSession` (A) calls `runtime.start(self)` in `begin`, polls `runtime.finished` in `poll`
(then `finish(runtime.outcome)`), and calls `runtime.abort(reason)` in `end` after resolving every
open `MotionHandle` with `aborted`. `submit` never blocks the owner: it queues the statement under
a lock and the owner starts it at the next tick. `RunModelStmt.until` is evaluated by the runner,
which calls `handle.cancel()`. Every goal a primitive returns goes through `SafetyFilter` in the
owner (`_motion_tick` step 3) like any other session.

**Motion primitives (A, owner thread).**
```python
class MotionPrimitive(Protocol):
    phase: Literal["approach", "replay", "episode"]
    done: bool
    outcome: MotionOutcome | None
    def begin(self, owner: HardwareOwner, obs: dict[str, float]) -> None: ...
    def step(self, owner: HardwareOwner, inp: TickInput) -> dict[str, float] | None: ...
    def cancel(self) -> None: ...

TrajectoryPlayer(samples: TrajectorySamples, *, speed_pct: float, fps: int,
                 approach_speed_deg_s: float, approach_threshold_deg: float = 3.0) -> MotionPrimitive
```
`TrajectoryPlaySession` and `ProgramSession` both drive a `TrajectoryPlayer`, so `playing` and the
`play trajectory` block are the same code path.

**Stores (A and B, any thread, per robot profile, through `Station.programs: ProgramsHub`).**
```python
class ProgramsHub:                                # programs/hub.py
    def robot_id(self) -> str: ...
    def robot_paths(self, robot_id: str | None = None) -> RobotDataPaths: ...
    def trajectories(self, robot_id: str | None = None) -> TrajectoryStore: ...   # A
    def poses(self, robot_id: str | None = None) -> PoseStore: ...                # A
    def calibration_hash(self, robot_id: str | None = None) -> str: ...           # A
    def detectors(self, robot_id: str | None = None) -> DetectorStore: ...        # B
    def programs(self, robot_id: str | None = None) -> ProgramStore: ...          # B
    @property
    def signals(self) -> SignalBus: ...                                           # B

class TrajectoryStore(Protocol):
    def all(self) -> list[TrajectorySummary]: ...
    def get(self, trajectory_id: str) -> Trajectory: ...
    def detail(self, trajectory_id: str) -> TrajectoryDetail: ...
    def samples(self, trajectory_id: str, *, trimmed: bool = True) -> TrajectorySamples: ...
    def create_draft(self, *, name: str, fps: int, samples: TrajectorySamples,
                     keyframes: dict[str, list[bytes]], keyframe_times: list[float]) -> Trajectory: ...
    def update(self, trajectory_id: str, upd: TrajectoryUpdate) -> Trajectory: ...
    def delete(self, trajectory_id: str) -> None: ...
    def mark_checked(self, trajectory_id: str) -> Trajectory: ...
    def keyframe(self, trajectory_id: str, camera: str, index: int) -> bytes: ...

class PoseStore(Protocol):
    def all(self) -> list[Pose]: ...
    def get(self, name: str) -> Pose: ...
    def replace(self, poses: list[PoseInput]) -> list[Pose]: ...
    def capture(self, name: str, positions: dict[str, float]) -> Pose: ...

class DetectorStore(Protocol):
    def all(self) -> list[Detector]: ...
    def get(self, detector_id: str) -> Detector: ...
    def put(self, detector_id: str, body: DetectorInput) -> Detector: ...
    def delete(self, detector_id: str) -> None: ...
    def set_model(self, detector_id: str, onnx: bytes) -> Detector: ...
    def runtime(self, detector_id: str) -> DetectorRuntime: ...

class ProgramStore(Protocol):
    def all(self) -> list[ProgramSummary]: ...
    def get(self, program_id: str) -> Program: ...
    def put(self, program_id: str, body: ProgramInput) -> Program: ...
    def delete(self, program_id: str) -> None: ...
    def mark_dry_run(self, program_id: str, version: int) -> None: ...

def calibration_hash(cal_root: Path, profile: RobotProfile) -> str: ...   # programs/calibration_ref.py (A)
```

**Conditions (B).**
```python
class DetectorRuntime(Protocol):
    def evaluate(self, frame: Frame, *, tick: int = -1) -> DetectorResult: ...   # never in the owner thread
    def close(self) -> None: ...

class SignalBus(Protocol):
    def set(self, name: str, value: Scalar, source: SignalSource) -> Signal: ...
    def get(self, name: str) -> Signal | None: ...
    def all(self) -> list[Signal]: ...
    @property
    def seq(self) -> int: ...
    def last_seq(self, name: str, source: Literal["http", "mqtt"]) -> int: ...
    def subscribe(self, fn: Callable[[Signal], None]) -> Callable[[], None]: ...

@dataclass(frozen=True)
class RobotSnapshot:                              # filled by A after each tick, read by B
    t: float; tick: int
    positions: dict[str, float]; goal: dict[str, float]
    load_pct: dict[str, float | None]; temp_c: dict[str, float | None]
    frames: dict[str, Frame]; frame_tick: int
    stale_cameras: list[str] = []
```
`gripper holding` = after a close, `goal["gripper.pos"] - positions["gripper.pos"] ≥ grip_hold.gap_min`
and `|load_pct["gripper"]| ≥ grip_hold.load_min_pct` (profile `follower.grip_hold`).

**Backend ↔ frontend (C).** Everything in `openapi.json`: REST §7 plus
`GET /programs/blocks` (block catalogue, normative), `GET /programs/{id}/state`,
`/programs/{id}/{pause,resume,stop,input,fake}`, `/programs/{id}/runs[/{run_id}]`,
`POST /trajectories/{id}/confirm`, `GET /trajectories/{id}/keyframes/{camera}/{index}` (JPEG),
`POST /poses/capture`, `GET /signals`, `POST /detectors/{id}/model` (multipart ONNX). WS server
messages `program_state` (on every block change, status change, and ≤ 5 Hz while waiting),
`program_log` (every log line), `trajectory_record` (≤ 5 Hz + phase changes + final with
`trajectory_id`), `signal` (every set); client message `program_input`. `Status.program` carries
the current run for reconnects. New Problem codes: `not_implemented` 501, `program_invalid` 422
(`errors` = the blocking `CheckIssue`s), `needs_check` 409, `dry_run_required` 409,
`fast_replay_not_allowed` 409, `detector_invalid` 422.

### 12.4 Blockly ↔ AST

`programs/blocks.py` is the normative catalogue (served by `GET /programs/blocks`): block type,
category, output (`statement`/`number`/`text`/`boolean`/`hat`), the AST kind it compiles to, and
its field and input names. Rules for the compiler (B) and the editor (C):
* The program is the stack under the single top-level `hb_start` block; other top-level stacks are
  `unreachable` warnings; zero or several `hb_start` blocks are errors.
* Every AST node's `id` is the Blockly block id (live highlight, traces, issue markers).
* Built-in Blockly blocks keep their names and serialization (`controls_if` with
  `extraState.elseIfCount/hasElse` and inputs `IF0/DO0…/ELSE`, `logic_compare`, `math_arithmetic`,
  `variables_get/set`, `math_change`, `text_join` with `extraState.itemCount`). Variables are
  Blockly typed variables, type `"Number"` or `"String"`.
* `hb_joint_compare` and `hb_motor_temp_compare` compile to `compare` (the spec's one-block
  conditions); `hb_motor_temp`, `hb_joint_value`, `hb_signal_value`, `hb_detector_confidence` are the
  value forms.
* Operator buttons are not blocks: they are `ProgramInput.buttons`, edited next to the workspace.
* The compiler never executes anything; validation (`CheckReport`) runs on the saved version.
