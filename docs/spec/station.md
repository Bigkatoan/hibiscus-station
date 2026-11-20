# Hibiscus Station: specification (contract v0.1)

Status: implemented (Station 0.1.0, extended in 0.2.0). Date: 2026-11-15.

> This specification was written while Station lived in the Hibiscus monorepo. Paths are updated
> to this repository (`hibiscus_station/`, `tests/`, `web/`); paths under `cli/`, `worker/`, `api/`,
> `docs/adr/` (ADR-xxxx) and `docs/spec/bundle.md` refer to the
> [Hibiscus server repository](https://github.com/Bigkatoan/Hibiscus). The implementation plan in
> §10 is kept as history. Since 0.2.0 Station can be opened on the LAN, opt-in (§8.1).
Related: `docs/spec/bundle.md` (model bundle), ADR-0010 (chunked upload), ADR-0011 (no LeLab patch),
the Hibiscus design system (built files synced into `web/`), `cli/hibiscus/{upload,pull,credentials}.py`.
Licence of new code: AGPL-3.0 (same as the Hibiscus repo, github.com/Bigkatoan/Hibiscus).

Hibiscus Station is a local agent that runs on the computer wired to the robot. It covers the whole
data loop on that machine: connect the robot, calibrate, add cameras, teleoperate, record a LeRobot
dataset, push it to a Hibiscus workspace, open the training run on the server, pull the trained
bundle and **run it on the robot**. It replaces the LeLab workflow. LeLab is studied below (it is MIT
licensed), not forked, and not patched (ADR-0011 still holds: LeLab stays untouched).

Two requirements from the user sit above everything else in this spec. Each one is first-class in
the backend, in the API and in every screen that moves the robot:

* **R1 Motor health.** LeLab never shows motor temperature. Station reads temperature, voltage,
  current, load and the status (alarm) byte of every motor, on the follower and on the leader. It
  streams them, colours them against thresholds, warns through Hibi, stops the robot safely on a
  critical reading, and logs them per session and per episode in a sidecar file.
* **R2 Cameras while running a model.** LeLab can import a model and play it on the real robot, but
  it does not show the robot cameras while the model runs. Station's Run-model screen shows every
  configured camera live (the exact frames the policy receives, at preview resolution), next to
  joint state against the commanded action, motor temperatures, step, FPS, latency, episode timer
  and a big e-stop (also bound to Space). Camera previews are also shown during teleop, recording
  and replay.

> **About LeLab's model playback.** The user reports that LeLab can import a model and run it on the
> robot. The local LeLab backend (commit `3aa1149`, `app/*.py`) has no policy code
> path: `grep -n "pretrained\|policy.path" app/` only finds training flags. ADR-0011 also says LeLab
> has "no inference". The playback the user saw most likely comes from the remote frontend LeLab
> clones at runtime (`scripts/frontend.py:17`, `jurmy24/leLab-space`), which drives lerobot's
> rollout, or from a newer LeLab. In both cases the camera gap has one root cause, visible in the
> backend: the browser opens the cameras for preview with its own stack, and the backend has to wait
> for the browser to **release** them before lerobot can open them (`app/recording.py:193-198`,
> sleep 2 s; `app/recording.py:573-576`, "camera resource conflict"). So whenever lerobot holds the
> cameras (recording, model run), the UI cannot show them. Station fixes this by design (§4.6): one
> process owns each camera and fans its frames out to both the control loop and the UI.

---

## 1. Goals and non-goals

### 1.1 Goals
1. **One install, one command.** `uvx hibiscus-station` (or `uv tool install hibiscus-station`,
   then `hibiscus-station`) starts the agent on `127.0.0.1:18210` and opens the browser. The Hibiscus
   CLI gets an alias, `hibiscus station …`, that runs the same entry point (phase A8).
2. **The full pipeline in a wizard:** Robot, Calibrate, Cameras, Teleop, Record, Upload, Train (on
   the server), Run model. Each step can also be opened directly once its prerequisites are met.
3. **Motor health telemetry (R1)** on every screen that moves the robot, with automatic safe stop.
4. **Live cameras (R2)** wherever the robot moves: teleop, record, replay, run model.
5. **Run trained models on the robot** with safety controls: a per-joint cap on relative targets,
   e-stop, episode time limit, a dead-man heartbeat and a thermal cutoff. Models come from a local
   bundle or `pretrained_model` directory, or are pulled from the paired server.
6. **One owner per piece of hardware.** Exactly one thread talks to each serial bus. Exactly one
   object opens each camera. LeLab's "Port is in use" retries (`app/calibrating.py:79-90`,
   `:395-406`) and camera hand-over sleeps (`app/recording.py:193-198`) cannot happen here.
7. **Configuration in one place:** `~/.hibiscus/station/robots.yaml`. LeLab spreads its settings
   over five locations (`app/config.py:11-28`). Calibration files stay in lerobot's standard
   location, so `lerobot-*` CLIs and LeLab keep working with the same ids.
8. **Pairing with a Hibiscus server through a PAT.** Recorded datasets go straight into a workspace
   through the resumable chunked upload (reusing `cli/hibiscus/upload.py`). Bundles are pulled with
   `cli/hibiscus/pull.py`.
9. **Testable without hardware:** mock robot, teleoperator, camera and motor bus that satisfy the
   lerobot interfaces. CI runs every flow end to end on them.
10. **The same pixel design system** as the Hibiscus web app: the `web/` app (route tree in
    `web/src/station`), built with Vite and served by the Station itself.

### 1.2 Non-goals (v1)
* Training on the robot machine. LeLab does this (`app/training.py:112-119`, a local subprocess
  with flags that are now outdated). Station hands training to the server.
* Robots other than SO-100/SO-101 follower and leader arms (`so100_follower`, `so101_follower`,
  `so100_leader`, `so101_leader`). The design is generic over lerobot `Robot`/`Teleoperator`, but
  only these four are wired and tested. Bimanual, LeKiwi, Koch, keyboard or gamepad teleop come
  later.
* Motor ID or baudrate setup for new kits (`lerobot-setup-motors`). The Robot screen links to the
  CLI instead.
* Remote access: no Internet exposure, no multi-user support. LAN access is opt-in since 0.2.0
  (§8.1).
* Async, RTC or remote inference (`lerobot/inference/rtc.py`, `--inference.type=remote`). v1 uses
  synchronous single-step `select_action`, the path that ACT, Diffusion, VQ-BeT and SmolVLA (with
  its extra installed) all support.
* ONNX runtime inference on the robot. The bundle's `onnx/` stays for third-party use. Station uses
  `pretrained_model/` with PyTorch.
* Editing or merging datasets, and HF Hub push. The server already has merge and HF import.

---

## 2. What LeLab does, what to keep, what to fix

Every LeLab behaviour Station learns from, with its source. Paths are relative to the LeLab repository at commit `3aa1149`.
lerobot paths are relative to `.venv/lib/python3.12/site-packages/lerobot` (0.7.1, git
`fe1c545`, the same pin as `worker/pyproject.toml`).

| # | LeLab feature (source) | Weakness observed | Hibiscus Station equivalent and improvement |
|---|---|---|---|
| L1 | FastAPI app, routes for every feature (`app/main.py:68-644`), served by `uvicorn host="0.0.0.0" reload=True` (`scripts/backend.py:18`) | Listens on every interface, runs in reload mode, `allow_origins=["*"]` with credentials (`app/main.py:71-77`), no auth | Binds 127.0.0.1 only, uses a random per-launch token, a host-header allow-list and a CORS lock (§8). One versioned `/api/v1` with RFC 9457 errors. |
| L2 | Frontend is a separate repo cloned and `npm install`ed at runtime (`scripts/frontend.py:17`, `:62`, `:79`). Static dir is relative to cwd (`app/main.py:80-83`, `:211`) | Needs Node and network on the robot machine, breaks when cwd changes | The built SPA ships inside the wheel (`hibiscus_station/static/`). No Node on the robot machine. |
| L3 | Serial port list: on Linux, every `/dev/tty*` (`app/config.py:115-121`) | Lists about 100 useless ttys, and names change after a replug | `serial.tools.list_ports.comports()` filtered to USB, with VID:PID, serial number and description. Stores the stable `/dev/serial/by-id/...` path when one exists. |
| L4 | Port detection by unplugging: snapshot, then poll for the port that disappears within 15 s (`app/config.py:124-186`, `app/main.py:545-566`) | Two round trips, the result goes into a txt file per role (`app/config.py:189-205`) | Same unplug flow as one request (`POST /ports/detect`, `method=unplug`), plus a **motion** method: "move the leader arm" finds the port whose positions change, with no unplugging. The result goes into `robots.yaml`. |
| L5 | Saved port and config name per role in txt files (`app/config.py:20-28`, `:251-316`) | Config spread over five places, one leader and one follower only | One `robots.yaml` with named robot profiles (§7). |
| L6 | Calibration copy step `setup_calibration_files` (`app/config.py:30-74`) copies a file onto the path it already has | Dead complexity | Uses lerobot's `calibration_dir` default `HF_LEROBOT_CALIBRATION/<robots or teleoperators>/<name>/<id>.json` (`robots/robot.py:59-68`, `utils/constants.py:100-101`). Nothing is copied. |
| L7 | Web calibration in two steps: homing, then range recording, with `complete-calibration-step` (`app/calibrating.py:309-460`) | (a) `get_status()` reads the bus from the HTTP thread while the worker thread reads it too, which causes "Port is in use" retries (`:77-119`). (b) Hard-codes `drive_mode=0` and records a range for `wrist_roll` (`:473-480`), while lerobot treats `wrist_roll` as full-turn (`robots/so_follower/so_follower.py:140`). (c) Calls the private `_get_half_turn_homings(positions)` (`:338`), whose 0.7.1 signature needs `signs` (`motors/motors_bus.py:854`), so it breaks on 0.7.1. (d) Only SO-101 (`:241-252`) | Same two-step UX, rebuilt on lerobot's public API (`set_half_turn_homings`, `motors/motors_bus.py:820`), with the semantics of `record_calibration` (`motors/motors_bus.py:931-1008`): full-turn motors, drive modes. Min/pos/max values stream over WebSocket from the bus-owner thread. The range checks from `app/calibrating.py:443-457` are kept: equal min and max is an error, less than 100 steps a warning. SO-100 and SO-101 supported. |
| L8 | Camera discovery: `cv2.VideoCapture(i)` for i in 0..9 (`app/main.py:511-542`) | Opens devices that may be in use, misses `/dev/video10+`, has no stable ids, no RealSense | `OpenCVCamera.find_cameras()` (`cameras/opencv/camera_opencv.py:314`), which scans `/dev/video*` on Linux, plus `RealSenseCamera.find_cameras()` (`cameras/realsense/camera_realsense.py:308`) when installed. Stable `/dev/v4l/by-id` paths. Never probes a camera the Station already holds. |
| L9 | Browser previews cameras itself, then must release them before recording (`app/recording.py:193-198`, `:566-577`) | **No camera view while recording or running a model** (root cause of R2) | `CameraHub` owns each camera. The control loop and the UI preview read the same frames (§4.6). |
| L10 | Teleop: leader `get_action()`, then follower `send_action()` in a busy loop with `sleep(0.001)`; joints broadcast at 20 Hz as URDF radians (`app/teleoperating.py:109-163`, `:28-78`) | No fixed rate. The follower jumps to the leader pose on start. Stop calls `disconnect()` from the HTTP thread while the loop still uses the bus (`app/teleoperating.py:206-216`). No camera, no telemetry | Fixed-rate loop (default 30 Hz) with the tick anatomy of `record_loop` (`scripts/lerobot_record.py:232-392`). Smooth approach on start (`common/control_utils.py:234`, `follower_smooth_move_to`). Stop is a flag, read by the owner thread. Telemetry and camera preview are always shown. |
| L11 | WebSocket `/ws/joint-data`: one broadcast thread with its own event loop (`app/main.py:104-206`, `:265-294`), only fed by teleop (`app/teleoperating.py:157-158`) | Recording takes `websocket_manager` (`app/main.py:300`) but never uses it (`app/recording.py:130-245`), so there is no live data while recording | One control WebSocket, fed in every state (§5.3). Video on a second socket, so video congestion never delays an e-stop or an alert. |
| L12 | Recording with web-controlled events `exit_early`, `rerecord_episode`, `stop_recording` that replace lerobot's keyboard (`app/recording.py:168-173`, `:247-342`), phases preparing, recording, resetting, completed (`:34`, `:612-783`) | (a) **An episode that reaches its time limit is discarded and re-recorded** (`app/recording.py:654-658`), unlike lerobot, which saves it (`scripts/lerobot_record.py:510-562`). (b) The status is polled (`:345-400`). (c) Hard-codes SO-101 and opencv (`:79-103`). (d) Dataset location is implicit (HF cache and a timestamp suffix, `:155-156`) | Same three controls (buttons plus the →, ← and Esc keys of lerobot). On timeout the episode is **saved** by default (`on_timeout: save | discard`). Phase and timers are pushed over WebSocket. Explicit dataset root under `~/.hibiscus/station/datasets/`. Resume ("add episodes") is kept, with the `sanity_check_dataset_robot_compatibility` check that LeLab uses (`app/recording.py:542-552`). `dataset.finalize()` is always called (`datasets/lerobot_dataset.py:570`). |
| L13 | Upload to the HF Hub with `push_to_hub` (`app/recording.py:467-514`), with an auth hint (`:501-510`) | HF only, not resumable | Resumable chunked upload to the paired Hibiscus workspace (`cli/hibiscus/upload.py`), guarded by `check_recording` (`cli/hibiscus/recording.py:87`). |
| L14 | Dataset info (`app/recording.py:419-464`) | Loads the full dataset only to show its metadata | Reads `meta/info.json`, `meta/episodes` and the Station sidecar. Cheap. |
| L15 | Replay through `lerobot_replay.replay(cfg)` after a test connection (`app/replaying.py:96-166`) | Cannot be stopped ("will complete current episode", `app/replaying.py:238-249`). Connects twice. Hard-codes fps=30 (`:89`) | Station's own replay loop at the dataset fps, interruptible within one tick, with safety filter, telemetry and cameras. |
| L16 | Training as a local `lerobot_train` subprocess (`app/training.py:97-138`, `:188-207`) | Runs on the robot machine, often without a GPU. Flags are outdated (ADR-0011) | The Train step links to the paired server's New Run wizard with the uploaded dataset version preselected, and shows the runs for that dataset (§6.8). |
| L17 | Model playback (reported by the user, see the note at the top) | Cameras not visible while running | Run-model screen (§6.9), built around R2. |
| L18 | No telemetry: `grep -i "temperature\|voltage" app/` finds nothing | Thermal shutdown happens without warning: the STS3215 cuts its torque on its own and the arm drops | R1 (§4.5). |

---

## 3. lerobot 0.7.1 APIs Station uses (and how)

| Need | API (lerobot 0.7.1) | Note |
|---|---|---|
| Follower | `robots.so_follower.SOFollowerRobotConfig` (registered `so100_follower`/`so101_follower`), `SOFollower` (`robots/so_follower/config_so_follower.py`, `so_follower.py`) | Built with `cameras={}`: cameras belong to `CameraHub` (§4.6). `max_relative_target=None`, because Station clamps against the observation it already read, which avoids the second `sync_read` that `send_action` does (`so_follower.py:206-209`). `use_degrees=True` (the default). `disable_torque_on_disconnect` follows the profile. |
| Leader | `teleoperators.so_leader.SO101LeaderConfig` / `SO100LeaderConfig`, `SOLeader` (`teleoperators/so_leader/so_leader.py`) | `get_action()` reads `Present_Position`. Torque is off. |
| Bus I/O | `robot.bus` / `teleop.bus`: `SerialMotorsBus.sync_read(name, normalize=False, num_retry=)` (`motors/motors_bus.py:1194`), `read`, `write`, `disable_torque`, `enable_torque`, `set_operating_mode`, `set_half_turn_homings`, `write_calibration`, `disconnect(disable_torque)` (`:440`) | Called only from the owner thread (§4.3). |
| Telemetry registers | rustypot `STS3215` definition: `present_temperature` (63, 1 B), `present_voltage` (62, 1 B), `present_load` (60, 2 B, sign bit 10), `present_current` (69, 2 B), `status` (65, 1 B), `moving` (66), `max_temperature_limit` (13), `min/max_voltage_limit` (15/14) | Checked with `rustypot.find_model("sts3215")[1].register(...)`. `status_alarms_only=True`: on STS the status byte carries alarms only, so an alarm never makes a read fail (`motors/motors_bus.py:1128-1145`). |
| Cameras | `cameras.opencv.OpenCVCamera`/`OpenCVCameraConfig(index_or_path, fps, width, height, rotation, fourcc)`, `cameras.realsense.RealSenseCamera`, `Camera.read_latest(max_age_ms)` (`cameras/camera.py:153`), `find_cameras()` | `read_latest` does not block. That matches what `SOFollower.get_observation` does (`so_follower.py:171-176`). |
| Dataset | `datasets.LeRobotDataset.create(repo_id, fps, root, robot_type, features, use_videos, image_writer_threads)` (`datasets/lerobot_dataset.py:783`), `add_frame` (`:516`), `save_episode` (`:531`), `clear_episode_buffer` (`:548`), `finalize` (`:570`); `utils.feature_utils.hw_to_dataset_features` (`:48`), `build_dataset_frame` (`:111`) | Features are composed from the robot motor features plus `CameraHub` shapes `(h, w, 3)`, the same layout as `so_follower.py:88-96`. |
| Teleop/record pipeline | `processor.make_default_processors()` (identity pipelines, as LeLab uses at `app/recording.py:536`) | Kept, so recorded `action` equals the teleop action. That is lerobot semantics (`scripts/lerobot_record.py:361-371`). |
| Smooth approach | `common.control_utils.follower_smooth_move_to(robot, current, target, duration_s, fps)` (`:234`) | Used at teleop start, run start, and when parking at a rest pose. |
| Policy | `configs.policies.PreTrainedConfig.from_pretrained`, `policies.factory.get_policy_class` (`:63`), `make_pre_post_processors(cfg, pretrained_path, preprocessor_overrides={"device_processor": {"device": dev}})` (`:159`), `common.control_utils.predict_action` (`:48`), `policies.utils.make_robot_action` (`:192`) | The same loading as lerobot-rollout (`rollout/context.py:289`, `:625-631`). PEFT adapters: `PeftModel.from_pretrained` (`rollout/context.py:297-303`) when `adapter_config.json` is present. |
| Detection | `scripts/lerobot_find_port.find_available_ports` (`:30`), `lerobot_find_cameras` logic | The port finder is reimplemented without `input()`. |

Mocks: lerobot's test mocks (`tests/mocks/mock_robot.py`, `mock_teleop.py`, `mock_motors_bus`) are
**not shipped** in the wheel (only `utils/doctest_utils.py` is). Station ships its own (§9).
`robots/sim_robot` needs a sim environment and is not a substitute.

---

## 4. Architecture

### 4.1 Packages and dependencies
```
hibiscus-station/                         # repository root, Python 3.12, AGPL-3.0
├── pyproject.toml                        # name = "hibiscus-station", script hibiscus-station = hibiscus_station.cli:main
├── hibiscus_station/
│   ├── cli.py                            # typer: `hibiscus-station [--port 18210] [--no-browser] [--mock] [--home DIR]`
│   ├── app.py                            # FastAPI factory, static SPA, security middleware
│   ├── settings.py                       # paths (§7), thresholds, defaults (pydantic-settings, env HIBISCUS_STATION_*)
│   ├── api/                              # routers: system, ports, robots, calibration, cameras, sessions, datasets, models, server, ws
│   ├── hw/
│   │   ├── owner.py                      # HardwareOwner thread + command queue + state machine (§4.3, §4.4)
│   │   ├── loop.py                       # ControlLoop tick (§4.5) shared by teleop/record/replay/run
│   │   ├── safety.py                     # SafetyFilter, EStop latch, Watchdog
│   │   ├── telemetry.py                  # TelemetryScheduler, decode, thresholds, ThermalGuard
│   │   ├── feetech.py                    # register list, units, status-bit decode (one place)
│   │   ├── calibration.py                # non-interactive calibration state machine
│   │   ├── cameras.py                    # CameraHub, PreviewEncoder
│   │   ├── ports.py                      # list/detect ports
│   │   └── factory.py                    # profile -> lerobot configs/devices (real or mock)
│   ├── sessions/                         # teleop.py, record.py, replay.py, run.py (policy runner)
│   ├── data/                             # datasets.py (local catalog, finalize/check), sidecar.py (telemetry logs)
│   ├── models/                           # registry.py, importer.py (zip/dir), compat.py (policy vs robot check)
│   ├── remote/                           # pairing.py, uploads.py, pulls.py (wrap cli/hibiscus Uploader/Puller)
│   ├── mock/                             # MockMotorsBus, MockFollower, MockLeader, MockCamera (§9)
│   └── static/                           # built SPA (web/dist, force-included at wheel build)
├── tests/
└── openapi.json                          # exported from FastAPI, committed; frontend generates types from it
```
Dependencies (pinned like `worker/pyproject.toml`):
`lerobot[feetech,dataset]==0.7.1` from git `fe1c54594f6ba275fccf210b9f7b11f0e2324b89` (through
`[tool.uv.sources]`), `fastapi`, `uvicorn[standard]`, `pydantic>=2.9,<3`, `pyyaml`, `keyring`,
`platformdirs`, `httpx`, `opencv-python-headless` (already pulled by lerobot), and the
`hibiscus` CLI package as a path or git dependency, so `Uploader`, `Puller`, `HibiscusApi` and
`credentials` are reused, not copied. Optional extras: `realsense` → `lerobot[intelrealsense]`,
`smolvla` → `lerobot[smolvla]`, `diffusion` → `lerobot[diffusion]`, `pi` → `lerobot[pi]`.
Station tooling runs as `env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run …`.

### 4.2 Process and thread model
One OS process. The threads:

```
┌──────────────────────────── hibiscus-station (1 process) ─────────────────────────────┐
│ asyncio main thread: uvicorn + FastAPI (REST, /ws, /ws/video), static SPA               │
│     │ commands (queue.Queue, bounded)                    ▲ events (loop.call_soon_threadsafe)│
│     ▼                                                    │                               │
│ HardwareOwner thread ── the ONLY code that touches robot.bus / teleop.bus ───────────────│
│   state machine · ControlLoop ticks · TelemetryScheduler · ThermalGuard · SafetyFilter   │
│   PolicyRunner.predict (inline, same thread: obs→action must be one tick)                │
│     │ publishes FrameSet(tick, {cam: ndarray}) + JointSample + TelemetrySample           │
│     ▼                                                                                    │
│ CameraHub: one lerobot Camera per device; each has its own lerobot read thread           │
│ PreviewEncoder thread (one): resize + JPEG at preview_fps, latest-frame-wins per client  │
│ DatasetWriter: lerobot's image-writer threads + save_episode (video encode) in a worker  │
│ SidecarWriter thread: telemetry JSONL.gz append, flushed each second                     │
│ Jobs pool (ThreadPoolExecutor, 2): uploads (Uploader), pulls (Puller), model import/load │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Rules:
* REST handlers never touch hardware. They validate, post a `Command` to the owner, and await its
  `Future` (timeout 5 s, then `504 hardware_timeout`). The owner answers between ticks.
* The owner thread runs at `os.nice(-5)` when permitted, and never blocks on I/O other than the
  bus. `save_episode()` (video encoding, which can take seconds) runs while the state is
  `recording.saving`: the control loop keeps holding the follower (no new goals), and the arm and
  telemetry are still sampled at the idle rate.
* Policy inference runs inline in the owner thread. v1 is synchronous by design: an observation and
  its action belong to the same tick, and the measured inference latency is shown. When inference
  is slower than the tick, the loop runs slower and the UI flags it (§6.9). It does not queue stale
  actions.
* Policy loading (from_pretrained, processors, warm-up forward pass) runs in the jobs pool, before
  the session starts. A session never starts with an unloaded policy.

### 4.3 Hardware ownership and locking
* `HardwareOwner` is a singleton. It owns the follower (`SOFollower`), the leader (`SOLeader`, when
  configured) and their buses. Ownership never leaves this thread. The serial port is opened by
  `bus.connect()` in the owner and closed by `disconnect()` in the owner.
* An **OS-level lock** prevents a second Station or a lerobot CLI from opening the same port:
  `fcntl.flock(LOCK_EX|LOCK_NB)` on `~/.hibiscus/station/locks/<sha1(port realpath)>.lock`, taken
  before `connect()`. Station also checks `TIOCEXCL` on the tty after it opens, because rustypot
  opens the port itself. On conflict: `409 port_busy` with the PID that holds the lock file. A
  process outside Station (LeLab, `lerobot-teleoperate`) that holds the tty makes connect fail;
  that failure is mapped to `port_busy`, with the hint "close LeLab / lerobot".
* `CameraHub` owns cameras with the same lock-file scheme (key = device realpath or RealSense serial
  number). Cameras open when the robot profile is connected, or on demand from the Cameras screen,
  and stay open across sessions. No re-open between teleop and record, no 2-second wait.
* Single-instance guard: `~/.hibiscus/station/station.pid` plus a flock. A second launch prints the
  URL of the instance already running and exits 0.

### 4.4 State machine
The control state belongs to the owner thread and is broadcast on every change (`state` message,
§5.3).

| State | Meaning | Bus activity | Allowed commands |
|---|---|---|---|
| `disconnected` | no robot profile connected | none | connect, ports/cameras discovery, calibration files list |
| `connecting` | opening buses, handshake, `configure()`, cameras | connect | (wait) |
| `idle` | buses open, no motion session | monitor loop 10 Hz: positions + telemetry. Follower torque as left by the last session (hold or relaxed) | any session start, calibration start, torque on/off, disconnect |
| `calibrating` | calibration of one arm (sub-step `home` or `ranges`) | 50 Hz raw position reads, torque off | calibration step/cancel, e-stop |
| `teleop` | leader drives follower, nothing recorded | control loop at `fps` | stop, e-stop |
| `recording` | sub-phase `warmup`, `episode`, `saving`, `reset` | control loop (`saving`: hold at idle rate) | next, rerecord, stop, e-stop |
| `replaying` | dataset episode actions drive follower | control loop at dataset fps | stop, e-stop |
| `inferring` | policy drives follower; sub-phase `countdown`, `episode`, `reset` | control loop at `fps` | next, stop, e-stop |
| `stopping` | session teardown: finalize dataset, park, write sidecar | hold | (wait) |
| `estopped` | latched after e-stop or a thermal/fault cutoff | monitor loop (telemetry continues) | `estop/reset`, torque off, disconnect |
| `error` | connection lost or unrecoverable fault; `detail` carries the reason | none (buses closed) | disconnect, connect |

Transitions:
```
disconnected ──connect──▶ connecting ──ok──▶ idle ◀──────────── stopping ◀── stop/end ── {teleop, recording, replaying, inferring}
      ▲                        │ fail                  │ start_*                                         │
      │                        ▼                       ▼                                                  │ estop | thermal critical | fault
      └──────disconnect────── error ◀── bus lost ── {any}        idle ──calibrate──▶ calibrating ──done/cancel──▶ idle
                                                                 {any moving} ───────────────▶ estopped ──reset──▶ idle
```
* At most one motion session at a time. A `start_*` outside `idle` returns `409 busy`, with the
  current state.
* Leaving any motion state goes through `stopping`, which cannot be interrupted, with a 10 s
  deadline. After it the follower is "held" (torque on, goal = present position), unless the
  profile sets `on_session_end: relax`. That setting relaxes the arm after parking at `rest_pose`.
  A relax without a rest pose asks for confirmation in the UI.
* A bus failure (`ConnectionError` 3 ticks in a row) causes `error`. Station tries
  `disable_torque` as a best effort and closes the port.

### 4.5 Control loop tick and motor health telemetry (R1)

#### 4.5.1 Tick anatomy (same order as `record_loop`, `scripts/lerobot_record.py:298-392`)
```
tick k  (period T = 1/fps, deadline-scheduled with perf_counter; CycleTimer-like stats)
 1. obs    = follower.get_observation()                 # sync_read Present_Position (1 bus read)
             obs |= CameraHub.read_latest_all(max_age_ms=2*T_cam)   # same call so_follower makes
 2. action = source.next(obs)                           # teleop: leader.get_action() (leader bus read)
                                                        # replay: dataset frame k
                                                        # run:    predict_action → make_robot_action
 3. safe   = SafetyFilter(action, obs)                  # per-joint |Δ| cap vs obs, calibrated range clamp
 4. follower.send_action(safe)                          # sync_write Goal_Position (no answer, fast)
 5. dataset.add_frame(obs ⊕ action ⊕ task)              # recording only, episode phase only
 6. publish JointSample(tick, obs.pos, action, safe, clipped) and FrameSet(tick, cams)  → UI
 7. TelemetryScheduler.maybe_read(slack = deadline - now)   # ≤ 1 register read per tick (§4.5.2)
 8. ThermalGuard.evaluate() ; Watchdog.check() ; EStop.check()   # may switch state before next tick
 9. sleep until deadline (record overrun if negative)
```
The e-stop flag is checked at the start of every tick and between steps 2 and 4: a press that
arrives during inference still prevents step 4. It is a `threading.Event`, set straight from the
WebSocket or REST handler, without going through the command queue.

#### 4.5.2 Telemetry: what, how often, and how it fits in the loop
Registers per motor, follower and leader (Feetech STS3215, rustypot names):

| Field | Register (addr) | Raw → unit | Shown as |
|---|---|---|---|
| `temp_c` | `Present_Temperature` (63) | 1 = 1 °C | °C, coloured (§4.5.3) |
| `voltage_v` | `Present_Voltage` (62) | 1 = 0.1 V | V. Warn below `Min_Voltage_Limit`+0.5 V or under 85 % of the nominal voltage measured at connect |
| `current_a` | `Present_Current` (69) | 1 = 6.5 mA | A. Warn above 80 % of `Protection_Current` × 6.5 mA when that register is set (the gripper sets it to 250, `so_follower.py:156`) |
| `load_pct` | `Present_Load` (60, sign bit 10) | 1 = 0.1 % of max torque, signed | %, shown as a bar. Warn when \|load\| ≥ 90 % for more than 2 s (stall) |
| `status` | `Status` (65) | bit 0 voltage, bit 1 angle sensor, bit 2 overheat, bit 3 overcurrent, bit 5 overload | chips. `overheat` or `overload` is critical at once |
| `limits` (once, at connect) | `Max_Temperature_Limit` (13), `Min/Max_Voltage_Limit` (15/14), `Protection_Current` (28) | as above | tooltip |

The unit factors and status bits are written in **one table**, `hw/feetech.py`, taken from the
Feetech STS memory table. They are confirmed on real hardware in the HIL checklist (§9.4). Tests
pin the decode function, not the hardware.

Scheduling: a round robin, so the control loop timing is not disturbed.
* Groups per bus, each one `sync_read(register, normalize=False, num_retry=0)` (one packet for all
  6 motors): `temperature` and `status` at `telemetry.hot_hz` (default **2 Hz**), `voltage`,
  `current` and `load` at `telemetry.cool_hz` (default **1 Hz**). For two buses that makes
  2×(2×2 + 3×1) = **14 reads/s**: at 30 fps, fewer than one read every two ticks.
* `maybe_read(slack)` reads the most overdue group, and only when `slack ≥ telemetry.min_slack_ms`
  (default **6 ms**; a 6-motor STS sync read measures about 1–3 ms through the USB adapter). One
  read per tick at most.
* **Anti-starvation:** if a bus's temperature sample is older than `telemetry.max_age_s` (default
  2 s), the read happens even without slack. Safety comes before timing. Every forced read
  increments `telemetry_forced`, shown in the loop stats.
* The leader bus is a different serial port. Leader reads do not hold up the follower bus, but they
  run in the same thread and count toward the same slack.
* In `idle`, `estopped` and `calibrating`, no control loop is running. The monitor loop reads all
  groups at 2 Hz with no slack rule.
* A failed telemetry read (timeout or corrupted packet) is never fatal. It marks the sample `stale`.
  Three failures in a row on a group raise a `telemetry_degraded` warning alert. Only position reads
  and writes can push the state to `error`.
* Possible later optimisation: one block read of addresses 56–70 (position…current) per tick through
  rustypot's raw API. Out of scope for v1, which only uses lerobot's public `sync_read`.

#### 4.5.3 Thresholds and actions (ThermalGuard)
Defaults (all configurable globally in `settings.yaml`, and per robot profile):

| Level | Temperature | UI | Automatic action |
|---|---|---|---|
| `ok` | < 50 °C | green cell | none |
| `warn` | ≥ 50 °C | yellow cell, top-bar chip turns yellow, Hibi (`sad` mood) speech: "elbow_flex is getting warm (52 °C)" | none |
| `hot` | ≥ 60 °C | orange cell, sticky banner, Hibi `sad`; a new session **cannot start** while any motor is hot (`409 motor_hot`) | none during a session, apart from the banner and a soft chime |
| `critical` | ≥ 65 °C on **2 consecutive** samples, or the `overheat` or `overload` status bit set | red cell, full-width red banner "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down." | **safe stop** (below), then the state goes to `estopped` with `reason=thermal` |

* Why 65 °C: the STS3215's own protection is `Max_Temperature_Limit`, factory value 70 °C
  (EEPROM address 13; Station reads the real value at connect). At that point the servo cuts its
  torque by itself and the arm **drops without control**. Station's critical level sits below it,
  so Station's controlled stop always comes first. Rule enforced at load:
  `critical ≤ max_temperature_limit − 3`, `hot ≤ critical − 3`, `warn ≤ hot − 5`. Invalid
  configurations are rejected with `422`.
* Hysteresis: a level clears only once the temperature is 3 °C below its threshold. A latched
  `estopped(thermal)` can be reset only when every motor is below `hot`. The UI shows a cooling
  countdown estimate (linear fit over the last 60 s).
* **Safe stop sequence** for a critical follower motor (≤ 2 s total):
  1. Set the e-stop event. No new goals from teleop, policy or replay.
  2. Hold: `Goal_Position := Present_Position`, from the last observation.
  3. If the profile has a `rest_pose` and the critical motor is below `critical + 5` °C, move there
     smoothly over `safe_stop.park_s` (default 1.5 s) with `follower_smooth_move_to`. Each step is
     still clamped by the SafetyFilter.
  4. `bus.disable_torque(num_retry=5)` on the follower.
  5. Banner: "Support the arm. Torque is off".

  If the `overheat` bit is set, or the temperature is ≥ `critical + 5`, steps 2 and 3 are skipped and
  torque goes off at once.
* A critical **leader** motor: the leader has no torque to cut. The session stops (follower held,
  then parked as above), and the banner names the leader motor.
* Voltage below the minimum, or the `overcurrent` bit on any follower motor, follows the same path
  as critical, with `reason=electrical`.

#### 4.5.4 Telemetry logging
* **Per session:** `~/.hibiscus/station/sessions/<session_id>/telemetry.jsonl.gz`. One line per
  sample per arm:
  `{"t": 12.345, "tick": 370, "state": "recording", "arm": "follower", "temp_c": {...}, "voltage_v": {...}, "current_a": {...}, "load_pct": {...}, "status": {...}, "stale": [..]}`.
  Each alert transition gets its own line: `{"t":…, "alert": {...}}`. Session metadata goes in
  `session.json`: profile snapshot, thresholds, start and end, loop stats and outcome.
* **Per recorded episode (sidecar):** `~/.hibiscus/station/datasets/<name>.hibiscus/telemetry/episode_<index:06d>.jsonl.gz`.
  It contains the same lines as above, plus `frame_index` (the dataset frame of the tick), written
  between `episode` start and `save_episode()`. A rerecorded or discarded episode deletes its
  sidecar. The sidecar directory sits **next to** the LeRobot root, never inside it: the dataset
  stays byte-for-byte what lerobot writes. LeRobot or Hibiscus validation never sees an unknown
  file, and the Hibiscus upload sends only the LeRobot root (§4.8).
* Retention: sessions older than 30 days, or beyond 2 GiB in total, are pruned at startup, oldest
  first. Episode sidecars stay as long as their dataset.
* Review: `GET /api/v1/sessions/{id}/telemetry` and `GET /api/v1/datasets/{name}/episodes/{i}/telemetry`
  return the decoded series. The Datasets screen shows a per-joint temperature mini-chart for each
  episode.

### 4.6 Cameras (R2)
* `CameraHub` builds lerobot cameras from the profile's `cameras:` map (`OpenCVCameraConfig` or
  `RealSenseCameraConfig`) and calls `connect(warmup=True)`. Each lerobot camera keeps its own read
  thread.
* In the control loop, `read_latest_all()` returns `{name: ndarray(h, w, 3) RGB}`. These are the
  arrays merged into `obs`, written to the dataset and given to the policy. Right after step 1, the
  loop publishes a `FrameSet(tick, frames)` that **references those same arrays** (no copy; the
  arrays are not mutated afterwards).
* `PreviewEncoder` (one thread) takes the latest `FrameSet` (in `idle` it calls `read_latest` itself)
  at `preview.fps` (default 12, max 30). Per subscribed camera, it resizes to the client's
  requested width (default 320, allowed 160–640, aspect kept, `cv2.INTER_AREA`), encodes JPEG
  (quality 70) and sends one binary message per camera (§5.4). Latest frame wins: when a client's
  previous frame has not been flushed, the new one replaces it in that client's slot. Video
  therefore never queues, and never slows the loop.
* Every preview message carries the `tick` of the frames it came from, so the UI can show "frame
  tick 1834 · state tick 1834". In `inferring`, it says **"policy input"**, with the source
  resolution (for example 640×480 → preview 320×240).
* Health: a camera whose `read_latest` raises `TimeoutError` (stale frame, above `max_age_ms`) for
  more than 0.5 s gets `camera_stale`. In `recording` or `inferring`, this pauses the episode clock
  and raises an alert, because it would corrupt data or feed the policy stale input. After 3 s the
  session stops with `reason=camera_lost`.
* Cameras keep running when no client watches; encoding stops then.

### 4.7 Safety (all motion sessions)
| Mechanism | Default | Detail |
|---|---|---|
| Relative target cap (`max_relative_target`) | 5.0 per tick (degrees for joints because `use_degrees=True`; 0–100 range units for the gripper) | `SafetyFilter` clamps `goal - obs` per joint, the same semantics as `ensure_safe_goal_position` (`robots/utils.py:137-160`), but against the observation already read in step 1 (no extra bus read). The value is a float (lerobot rejects an int, `robots/utils.py:142-149`). Per joint in the profile. The number of clipped joints per second is published; above 30 % of ticks clipped for 2 s, a "policy is fighting the limiter" warning appears. |
| Calibrated range clamp | on | Goals are clamped into `[range_min, range_max]` of the calibration (normalised). |
| Smooth approach | 1.5 s | Teleop start: follower to leader pose. Run start: no move (the policy starts from the current pose), but the cap applies from tick 1. |
| Episode time limit | record 30 s, run 30 s (max 600 s) | Enforced by the owner, not the UI. |
| E-stop | Space key, on-screen button, `POST /estop`, WS `{"type":"estop"}` | **Freeze**: within the current tick, no more goals, `Goal_Position := Present_Position`, torque stays on (the arm does not fall), and the state latches to `estopped`. **Second press within 2 s, or the "Relax" button: torque off.** Reset with `POST /estop/reset` (UI button "I'm clear, reset"). |
| Dead-man heartbeat | `inferring` and `replaying`: on; `teleop`/`recording`: off (a human holds the leader) | The UI sends `{"type":"heartbeat"}` every 250 ms on the control WS. No heartbeat from any client for 1.0 s → e-stop (`reason=ui_lost`). Covers a closed tab, a crashed browser, a laptop lid. |
| Thermal/electrical | §4.5.3 | |
| Loop overrun | warn when p95 tick time > 1.2 T over 2 s | In `inferring`, if inference alone is above 2 T for 5 s, the session pauses with "model too slow for N fps on this machine (CPU)". Suggests a lower fps or a CUDA device. |
| Start checks | — | No session starts when: a motor is `hot`, a configured camera is not streaming, calibration is missing for an arm that is used, or (run) the policy compatibility check fails (§4.9). |

### 4.8 Server pairing, upload and pull
* Pairing: the user pastes the server URL and a PAT, created on the server's Account → Tokens page
  with scopes **`datasets:write`** (implies `datasets:read`, `backend/app/auth/pat.py:16-19`),
  **`models:read`**, and optionally **`runs:read`** (Train screen run list). `POST /server/pair`
  first refuses an address that is not http(s) (`server_url_invalid`) or a known share link
  (`server_url_file_share`: OneDrive / SharePoint / Office / Teams, Google Drive / Docs, Dropbox,
  Safe Links unwrapped) or plain `http://` to a public host (`server_url_insecure`: http only for
  localhost, loopback / private / link-local / CGNAT addresses, `*.local`, `*.lan`, single-label
  names), then **probes the candidate without credentials**: `GET <base>/auth/config` (the public
  login configuration of the released server), no redirect followed, one 5 s deadline over the
  whole exchange, `application/json` with the `AuthConfig` fields and types (`supported_locales`
  names vi or en; other languages and new fields are fine). Only a positive identity lets the token leave the
  Station; anything else is `server_not_hibiscus` (422, QC F029 QD-40). It then
  checks the token with `GET /auth/me` (401 / 403 → `server_unauthorized`; a malformed token is
  `token_format_invalid`, a missing scope `token_missing_scope`, several workspaces
  `workspace_required`) and the workspace list, and stores the token through
  `cli/hibiscus/credentials.save_token`: OS keyring first, otherwise `credentials.json` at 0600,
  refused when group or other can read it (`cli/hibiscus/credentials.py:1-8`). The CLI and Station
  share the stored token.
* Upload: `Uploader.push(VirtualTar(<dataset root>), new_dataset_name=… | dataset_id=…)`
  (`cli/hibiscus/upload.py:124-180`). It is resumable, with a state file in the CLI's `state_dir`,
  part sha256 and backoff. Before the push: `check_recording(root)` (`cli/hibiscus/recording.py:87`)
  must pass (parquet closed, mp4 finalised); otherwise `409 dataset_not_finalized`. Progress events
  (`UploadEvents`) go out as `upload` WS messages. Telemetry sidecars are **not** uploaded in v1
  (§11 Q2).
* Pull: `Puller.pull(model_id, to=~/.hibiscus/station/models/)` (`cli/hibiscus/pull.py:204`). It
  resumes with Range and If-Range, and verifies `MANIFEST.json` sha256 values
  (`cli/hibiscus/pull.py:86`). It then registers the model (§4.9).
* Offline: everything except Upload, Train and Pull works without a server.

### 4.9 Models and the policy runner
* **Import sources:**
  1. A Hibiscus bundle zip or directory (`docs/spec/bundle.md` §2). Station verifies `MANIFEST.json`
     with the CLI's `verify_manifest`, and uses `<bundle>/pretrained_model`.
  2. A plain lerobot `pretrained_model` directory (`config.json` + `model.safetensors` +
     `policy_preprocessor.json` / `policy_postprocessor.json`, optional `train_config.json`), for
     example `outputs/train/<run>/checkpoints/<step>/pretrained_model`. Shown as "unverified" (no
     manifest).
  3. Pull from the paired server (§4.8).

  Imports are **copied** into `~/.hibiscus/station/models/<model_key>/`: zips are extracted with
  path-traversal checks (the CLI's `_safe_rel`); directories are copied with hardlinks when
  possible. A later change to the source can therefore not change a model while it runs. Zip
  upload from the browser: `POST /models/import` multipart (≤ 4 GiB, streamed to disk). Local path
  import: `{"path": "..."}`, resolved on the Station machine, and only under `$HOME` or `/media`,
  `/mnt`.
* **Registry** `models/index.json`:
  `{key, name, source: bundle|pretrained_dir|server, server_model_id?, policy_type, input_features, output_features, fps?, task?, robot_type?, verified, imported_at, size_bytes}`.
  `fps`, `task` and `robot_type` come from `train_config.json` (dataset fps and task) or the bundle's
  `MODEL_CARD`/`MANIFEST`, when present.
* **Compatibility check** (`GET /models/{key}/compat?robot=<profile>`; it runs again at
  `POST /sessions/run`):
  * `observation.state` dim = the number of follower motors (6), and `action` dim = 6. Error otherwise.
  * Every `observation.images.<cam>` of the policy maps to a configured camera. The camera map is
    the identity by name by default, and the UI offers a dropdown when the names differ. Error when
    one is missing.
  * Image shape `(3, H, W)` = camera `(height, width)`. On mismatch it is an **error, not a silent
    resize**: resizing changes the input distribution. The UI offers "set camera <cam> to W×H"
    (profile edit, then camera reopen).
  * `robot_type` (from the train config or dataset) not in `{so100_follower, so101_follower, so_follower}`:
    warning only.
  * Policy type has an installed extra (smolvla, pi, …). Error with the `uv tool install hibiscus-station[smolvla]` hint.
* **Load** (jobs pool), when the Run screen opens a model:
  `cfg = PreTrainedConfig.from_pretrained(dir)`, `cfg.device = settings.device` (`auto`: `cuda` if
  available, then `mps`, then `cpu`),
  `policy = get_policy_class(cfg.type).from_pretrained(dir, config=cfg)` (PEFT: as
  `rollout/context.py:297-303`), then `policy.eval()`,
  `pre, post = make_pre_post_processors(cfg, pretrained_path=dir, preprocessor_overrides={"device_processor": {"device": cfg.device}})`.
  Warm-up is one forward pass on a zero observation. Load time, device and warm-up latency go to the
  UI. Only one model is loaded at a time; it is unloaded when another model is loaded or after
  10 minutes idle.
* **Per tick** (step 2): `a = predict_action(obs_policy, policy, device, pre, post, use_amp=False, task=task, robot_type=robot.robot_type)`
  (`common/control_utils.py:48`), then `action = make_robot_action(a, ds_features)`
  (`policies/utils.py:192`), where `ds_features` = `hw_to_dataset_features` of the robot motors plus
  the cameras **renamed through the camera map** to the policy's keys. The time spent here is
  `inference_ms` (p50/p95 over 2 s).
* **Episode:** `policy.reset()` and `pre.reset()`/`post.reset()` at each episode start, so ACT
  action queues are cleared. Sequence: `countdown` (3 s, robot held, "Space = stop" overlay), then
  `episode` (≤ `episode_time_s`), then `reset` (`reset_time_s`, robot held, or the user drives it
  back with the leader when a leader is connected and `reset_with_leader` is set), then the next
  episode, up to `num_episodes`. "Next" ends the episode early; "Stop" ends the session.
* **Optional evaluation recording** (`record: true`): the same loop also writes a LeRobot dataset
  `eval_<model>_<date>` (naming as lerobot reserves `eval_`, `scripts/lerobot_record.py:469-474`),
  with telemetry sidecars, for upload and review.

---

## 5. API contract (`/api/v1`)

### 5.1 Conventions
* Base `http://127.0.0.1:18210/api/v1`. JSON UTF-8. Times are ISO-8601 UTC strings (REST) or float
  seconds since session start (`t` in streams).
* Auth: HttpOnly cookie `hst` (SameSite=Strict, Path=/), set by the bootstrap URL (§8). Scripts may
  use `Authorization: Bearer <local token>` instead. Every non-GET request also needs the header
  `X-Station: 1` (CSRF belt and braces, alongside SameSite).
* Errors follow RFC 9457 `Problem`, the same shape as the server (`api/openapi.yaml:3045-3069`):
  `{type, title, status, code, detail, request_id, params?, errors?}`. The frontend reuses
  `src/lib/errors.ts`. Station codes: `unauthenticated` 401, `forbidden_host` 403,
  `validation_failed` 422, `not_found` 404, `busy` 409 (`params.state`), `port_busy` 409
  (`params.port`, `params.holder`), `motor_hot` 409 (`params.motors`), `not_connected` 409,
  `not_calibrated` 409 (`params.arm`), `camera_unavailable` 409, `estopped` 409,
  `model_incompatible` 422 (`errors[]`), `dataset_not_finalized` 409, `episode_saving` 409
  (`params.dataset`, `params.episode`), `video_missing` 404 / `video_unavailable` 422 (`params.camera`,
  `params.episode`), `not_paired` 409,
  `server_error` 502 (`params.upstream_code`), `hardware_timeout` 504, `internal_error` 500.
* Hardware commands answer once the owner has accepted the transition (state already changed). The
  progress after that comes over the WebSocket.
* `openapi.json` is generated by FastAPI and committed at `openapi.json`. A contract test
  fails when the committed file is out of date. Every wire shape is a pydantic model in
  `hibiscus_station/api/schemas.py` (`extra="forbid"`); the WebSocket messages (§5.3, §5.4) are
  exported into `components.schemas` too (`ServerMessage`, `ClientMessage`, `VideoSubscribe`,
  `FrameHeader`, `CameraErrorMsg`). The frontend types are generated from that file
  (`pnpm gen:api` → `web/src/station/api/schema.d.ts`; CI runs
  `pnpm check:station-api`). REST handlers validate their output against the models, and the test
  suite validates every emitted WebSocket message with the JSON Schema from `openapi.json` and the
  pydantic union, so a field added on one side only fails CI. Persisted models used both ways
  (`Settings`, `RobotProfile`, `CameraProfile`, `Thresholds`) appear as `X-Input` (defaults optional)
  and `X-Output` (every field present).
* Extra Problem codes: `forbidden` 403 (import path outside the allowed roots), `csrf` 403 (missing
  `X-Station`), `leader_far` 409 (`params.joints` {joint: degrees}, `params.max_deg`),
  `model_not_loaded` 409 (`params.model`), `dataset_exists` 409, `dataset_incompatible` 422. The UI
  shows a localised string per `code` (a test checks every code has one in en and vi).
* Ports: Station `127.0.0.1:18210`; the Vite dev server for the UI `127.0.0.1:18211` proxies to it.
  The WebSockets live under the API base: `/api/v1/ws` and `/api/v1/ws/video`.

### 5.2 Endpoints

| Method & path | Body → Response | Notes |
|---|---|---|
| **System** | | |
| `GET /status` | → `Status` | full snapshot; the UI calls it on load and after a WS reconnect |
| `GET /settings` · `PUT /settings` | `Settings` ↔ `Settings` | thresholds, preview, device, safety defaults |
| **Ports & robots** | | |
| `GET /ports` | → `{ports: Port[]}` | |
| `POST /ports/detect` | `{method: "unplug"\|"motion", ports_before?: string[], timeout_s?: 15}` → `{port: Port}` | long-poll. `unplug`: call once without `ports_before` to get the snapshot (`{ports_before}`), then call again. `motion`: opens each candidate port at 1 Mbaud, pings ids 1–6, returns the one whose positions change by > 50 steps |
| `GET /robots` | → `{robots: RobotProfile[], active: string\|null}` | |
| `PUT /robots/{id}` | `RobotProfile` → `RobotProfile` | create or replace; refused while that profile is connected and in motion |
| `DELETE /robots/{id}` | → 204 | does not delete calibration files |
| `POST /robots/{id}/connect` | `{}` → `Status` | `disconnected → connecting → idle` |
| `POST /robots/disconnect` | `{relax?: bool}` → `Status` | |
| `POST /robots/torque` | `{arm: "follower", enabled: bool}` → `Status` | idle/estopped only; `enabled:false` needs `confirm: true` without a rest pose |
| **Calibration** | | |
| `GET /calibrations` | → `{files: CalibrationFile[]}` | scans lerobot's `HF_LEROBOT_CALIBRATION` for `so_follower`, `so_leader` |
| `POST /calibration/start` | `{arm: "follower"\|"leader", id: string, keep_existing?: bool}` → `Status` | `keep_existing`: writes the existing file to the motors and returns to idle (the UI form of `_keep_calibration_file`, `robots/robot.py:186-201`) |
| `POST /calibration/step` | `{action: "set_home"\|"finish_ranges"\|"cancel"}` → `Status` | progress through `calibration` WS messages |
| **Cameras** | | |
| `GET /cameras/discover` | → `{cameras: DiscoveredCamera[]}` | skips devices CameraHub holds (they are listed with `in_use_by: "<name>"`) |
| `POST /cameras/probe` | `CameraConfig` → `{ok, measured_fps, width, height, error?, snapshot_jpeg_b64}` | opens, grabs for 2 s, closes; disallowed for a held device |
| **Sessions** | | |
| `POST /sessions/teleop` | `{fps?: 30}` → `Session` | |
| `POST /sessions/record` | `RecordRequest` → `Session` | |
| `POST /sessions/replay` | `{dataset: string, episode: int}` → `Session` | |
| `POST /sessions/run` | `RunRequest` → `Session` | |
| `POST /sessions/current/control` | `{action: "next"\|"rerecord"\|"stop"}` → `Session` | `rerecord` only in `recording.episode`/`reset` |
| `POST /estop` | `{}` → `Status` | also through WS. Always allowed, even unauthenticated **from the same origin with a valid cookie**: auth is still required, no other exception |
| `POST /estop/reset` | `{}` → `Status` | refused while thermal conditions persist (`motor_hot`) |
| `GET /sessions` | → `{sessions: SessionSummary[]}` | history (session.json) |
| `GET /sessions/{id}/telemetry` | → `TelemetrySeries` | |
| **Datasets** | | |
| `GET /datasets` | → `{datasets: LocalDataset[]}` | |
| `GET /datasets/{name}` | → `LocalDatasetDetail` | episodes with length, task, sidecar summary (max temp per joint) |
| `DELETE /datasets/{name}` | → 204 | deletes the root and sidecars; refused while recording or uploading |
| `GET /datasets/{name}/episodes/{i}/telemetry` | → `TelemetrySeries` | `frame_index[]` aligned with `t` (video time = frame_index / fps, F-72) |
| `GET /datasets/{name}/episodes/{i}/videos` | → `EpisodeVideos` | F-72: every camera of the episode (recorded codec, RFC 6381 `mime` for `canPlayType`, duration, per-camera `error`, `formats`); 409 `episode_saving` while the dataset is being recorded |
| `GET /datasets/{name}/episodes/{i}/videos/{camera}?format=source\|h264\|vp9` | → `video/mp4` / `video/webm` | F-72, ADR-14: the episode cut out of LeRobot's shared mp4, t = 0 at its first frame; `source` copies the recorded packets, `h264` / `vp9` re-encode once (PyAV), cached in `<name>.hibiscus/video-cache/`; HTTP `Range` (206 / 416); `video_missing` 404, `video_unavailable` 422, `episode_saving` 409 |
| `POST /datasets/{name}/upload` | `{new_dataset_name?: string, dataset_id?: string}` → `Job` | exactly one of the two |
| **Models** | | |
| `GET /models` | → `{models: ModelEntry[], loaded: string\|null, loaded_detail: {key, device, policy_type, load_s, warmup_ms}\|null}` | |
| `POST /models/import` | multipart `file` (zip) **or** JSON `{path}` → `Job` | |
| `POST /models/pull` | `{server_model_id: string}` → `Job` | needs `models:read` |
| `GET /models/{key}/compat` | `?robot=<id>` → `CompatReport` | |
| `POST /models/{key}/load` | `{device?: "auto"\|"cpu"\|"cuda"\|"mps"}` → `Job` | |
| `DELETE /models/{key}` | → 204 | |
| **Jobs** | | |
| `GET /jobs` · `GET /jobs/{id}` · `POST /jobs/{id}/cancel` | → `{jobs: Job[]}` · `Job` · `Job` | uploads, pulls, imports, loads; progress on WS |
| **Server** | | |
| `GET /server` | → `ServerLink` | |
| `POST /server/pair` | `{url, token, workspace_id?}` → `ServerLink` | validates scopes |
| `DELETE /server` | → 204 | deletes the stored token |
| `GET /server/datasets` | → `{datasets: {id, name, latest_version}[]}` | proxy, used to pick an upload target |
| `GET /server/models` | → `{models: {id, name, status, policy_type, size_bytes, created_at}[]}` | proxy, `status=ready` first |
| `GET /server/runs` | `?dataset_id=` → `{runs: {id, number, status, policy_type, progress, model_id, url}[], new_run_url}` | proxy, needs `runs:read` (otherwise 409 `not_paired`, with `params.missing_scope`). `progress` is 0..1 (`current_step / total_steps`), `model_id` the model built from the final checkpoint (for "Pull & run") |
| `POST /robots/rest-pose` | `{}` → `{rest_pose}` | stores the current follower pose as the rest pose |
| `POST /mock/inject` | `{port, motor?, temp_c?, clear_temp?}` → `{ok}` | **`--mock` only**, not in `openapi.json`: fault injection for demos and the e2e UI test |
| **WebSocket** | | |
| `GET /ws` (upgrade, i.e. `/api/v1/ws`) | control/event stream §5.3 | cookie, `Authorization: Bearer`, or subprotocols `hst.v1, bearer.<token>`; Host and Origin checked |
| `GET /ws/video` (upgrade, i.e. `/api/v1/ws/video`) | binary camera stream §5.4 | same auth |

### 5.3 JSON shapes
```jsonc
// Status (GET /status, and the payload of WS "state")
{
  "station": {"version": "0.1.0", "lerobot": "0.7.1", "device": "cuda", "mock": false},
  "state": "recording",                     // §4.4
  "sub": "episode",                          // sub-phase or null
  "reason": null,                            // for estopped/error: "user"|"thermal"|"electrical"|"ui_lost"|"camera_lost"|"bus_lost"|...
  "detail": null,
  "robot": {"id": "desk_so101", "connected": true, "follower_torque": true,
            "arms": {"follower": {"port": "/dev/serial/by-id/usb-1a86_..-if00", "calibrated": true},
                     "leader":   {"port": "/dev/serial/by-id/usb-1a86_..-if00", "calibrated": true}}},
  "cameras": [{"name": "wrist", "streaming": true, "width": 640, "height": 480, "fps": 30, "stale": false}],
  "health": {"level": "warn", "hottest": {"arm": "follower", "motor": "elbow_flex", "temp_c": 52}},
  "session": null | Session,
  "server": {"paired": true, "url": "https://robot.example.com", "workspace": "lab"},
  "loaded_model": null | "so101_picknplace_act-r42-step10000"
}

// RobotProfile (robots.yaml entry, §7)
{
  "id": "desk_so101", "name": "Desk SO-101",
  "follower": {"type": "so101_follower", "port": "/dev/serial/by-id/...", "calibration_id": "desk_follower",
               "max_relative_target": 5.0 /* or {"shoulder_pan": 5.0, ...} */,
               "rest_pose": {"shoulder_pan.pos": 0.0, "...": 0.0} | null,
               "on_session_end": "hold" | "relax"},
  "leader":   {"type": "so101_leader", "port": "/dev/serial/by-id/...", "calibration_id": "desk_leader"} | null,
  "cameras":  {"wrist": {"type": "opencv", "index_or_path": "/dev/v4l/by-id/usb-..-video-index0",
                         "width": 640, "height": 480, "fps": 30, "fourcc": "MJPG", "rotation": 0},
               "front": {"type": "realsense", "serial_number_or_name": "1234", "width": 640, "height": 480, "fps": 30}},
  "thresholds": null | {"temp_warn_c": 50, "temp_hot_c": 60, "temp_critical_c": 65}
}

// Port
{"device": "/dev/ttyACM0", "stable_path": "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A46..-if00",
 "vid_pid": "1a86:55d3", "serial_number": "5A46...", "description": "USB Single Serial", "in_use_by": null | "follower"}

// DiscoveredCamera
{"type": "opencv", "id": "/dev/video2", "stable_path": "/dev/v4l/by-id/...", "name": "HD USB Camera",
 "default": {"width": 640, "height": 480, "fps": 30, "fourcc": "MJPG"}, "in_use_by": null}

// RecordRequest
{"dataset": "picknplace_red", "mode": "new" | "append", "task": "Pick the red cube and place it in the bowl",
 "num_episodes": 20, "episode_time_s": 30, "reset_time_s": 10, "fps": 30, "video": true,
 "on_timeout": "save" | "discard", "countdown_s": 3}

// RunRequest
{"model": "<model key>", "task": "Pick the red cube ...", "fps": 30, "episode_time_s": 30, "num_episodes": 1,
 "reset_time_s": 10, "camera_map": {"observation.images.wrist": "wrist"}, "max_relative_target": null | 5.0,
 "reset_with_leader": false, "record": false, "dataset": null | "eval_picknplace_act_20261115"}

// Session
{"id": "s_20261115_101501_a1b2", "kind": "teleop" | "record" | "replay" | "run", "started_at": "...",
 "fps": 30, "episode": {"index": 3, "of": 20, "saved": 3, "phase": "episode", "elapsed_s": 12.4, "limit_s": 30},
 "dataset": null | "picknplace_red", "model": null | "<key>", "task": "...",
 "controls": {"next": true, "rerecord": true, "stop": true}}

// Job
{"id": "j_...", "kind": "upload" | "pull" | "import" | "load", "status": "queued" | "running" | "succeeded" | "failed" | "cancelled",
 "progress": {"done": 123456789, "total": 987654321, "unit": "bytes", "phase": "hashing" | "uploading" | "verifying" | "loading"},
 "result": null | {"dataset_id": "...", "version": 2, "server_url": "https://.../datasets/..."} | {"model": "<key>"},
 "error": null | Problem}

// CompatReport
{"ok": false, "policy_type": "act", "device": "cuda",
 "checks": [{"id": "state_dim", "ok": true}, {"id": "camera:observation.images.wrist", "ok": false,
             "code": "shape_mismatch", "expected": [3, 480, 640], "actual": [3, 360, 640],
             "fix": {"kind": "set_camera", "camera": "wrist", "width": 640, "height": 480}}],
 "warnings": ["robot_type so_follower in train config; profile is so101_follower (ok)"],
 "defaults": {"fps": 30, "task": "Pick the red cube ..."}}

// TelemetrySeries
{"arm_motors": {"follower": ["shoulder_pan", "..."], "leader": ["..."]},
 "t": [0.0, 0.5, ...], "temp_c": {"follower": {"shoulder_pan": [31, 31, ...]}}, "voltage_v": {...}, "current_a": {...},
 "load_pct": {...}, "alerts": [{"t": 12.0, "level": "warn", "arm": "follower", "motor": "elbow_flex", "kind": "temperature", "value": 51}]}
```

**Control WebSocket `/ws`** (JSON text frames; `v` = 1). The server sends `hello` first. The
client then sends `hello`; the server waits 2 s for it before closing with 4401.

| Direction | `type` | Payload | Rate |
|---|---|---|---|
| S→C | `hello` | `{v:1, status: Status}` | once |
| S→C | `state` | `Status` | on change |
| S→C | `joints` | `{t, tick, arms: {follower: {"shoulder_pan.pos": 12.3, ...}, leader?: {...}}, action?: {...}, sent?: {...}, clipped: ["wrist_flex"], loop: {fps: 29.8, tick_ms_p95: 31.2, inference_ms_p50?: 18.0, inference_ms_p95?: 24.5, overruns: 0, telemetry_forced: 0}}` | `joints_hz` (default 20; one in N ticks) |
| S→C | `telemetry` | `{t, arm: "follower", motors: {"elbow_flex": {temp_c: 52, voltage_v: 7.3, current_a: 0.42, load_pct: -31.5, status: [], level: "warn", stale: false}}, limits?: {max_temp_c: 70, min_voltage_v: 4.0}}` | per group read (about 3–5 msg/s) |
| S→C | `alert` | `{id, t, level: "info"\|"warn"\|"hot"\|"critical", kind: "temperature"\|"voltage"\|"current"\|"load"\|"status"\|"camera"\|"loop"\|"telemetry_degraded"\|"policy_clipping", arm?, motor?, camera?, value?, message_key, params, active: bool}` | on edge (raise, clear) |
| S→C | `calibration` | `{arm, step: "home"\|"ranges"\|"done", motors: {"shoulder_pan": {min, pos, max}}, warnings: [...]}` | 10 Hz during `ranges` |
| S→C | `session` | `Session` | on phase change + 1 Hz while running |
| S→C | `job` | `Job` | on progress (≤ 4 Hz per job) |
| C→S | `hello` | `{v:1, client: "station-ui", heartbeat: true}` | once |
| C→S | `heartbeat` | `{}` | every 250 ms (dead-man, §4.7) |
| C→S | `estop` | `{}` | on Space/button. Takes effect without a queue, in under one tick |
| C→S | `control` | `{action: "next"\|"rerecord"\|"stop"}` | same as REST |

**Final contract details (v0.1, where the shapes above were silent; `schemas.py` is normative):**

* Every server message is flat: `{"type": <kind>, ...payload}`. `state` is `{type, ...Status}`,
  `session` is `{type, ...Session}`, `job` is `{type, ...Job}`. Only `hello` wraps: `{type, v, status}`.
  The server also sends `{type:"error", action, detail}` (a failed `control` from this client) and
  `{type:"pong"}`. The client may send `{type:"ping"}` and `{type:"estop", relax?: bool}`.
* `Status` also carries `station.home` (data dir), `robot.name`, `cameras[].type|error`,
  `alerts` (the active `Alert`s, same shape as the `alert` message without `type`) and
  `last_session` (`SessionEnd`, below). `sub` is one of `home|ranges` (calibrating) or the session
  phase `approach|teleop|replay|countdown|warmup|episode|saving|reset|done`.
* `Session.episode` is always an object (teleop: `{index:0, of:0, phase:"approach"→"teleop"}`).
  `Session` adds `outcome` (`running` while active), and for runs `paused` (`model_too_slow`|null)
  and `policy: {inferences, last_policy_tick}`. `task` is a string (`""` when none).
* End of a session: state `stopping`, then one final `session` message with `ended: true`,
  `episode.phase:"done"` and the saved count, plus `reason`, `summary`, `loop: {ticks, overruns,
  tick_ms_p95, telemetry_reads, telemetry_forced}` and `max_temp_c` (`"arm.motor"` → peak °C); then
  the new state (`idle` or `estopped`). The same object (without `type`/`ended`) is
  `Status.last_session`.
* `joints.loop` is `null` outside motion sessions (the idle monitor still sends positions);
  `telemetry` adds `group` (the register group read), `forced` and `limits: {max_temp_c,
  min_voltage_v, max_voltage_v, nominal_voltage_v, protection_current_a: {motor: A}}`.
* `Alert.message_key` (UI string `alerts.<message_key>`): `motor.temp.{ok,warn,hot,critical}`,
  `motor.{status,voltage,current,load}.<level>`, `motor.critical.stopped`, `camera.stale`,
  `camera.open_failed`, `record.save_failed`, `run.model_too_slow`, `safety.clipping`,
  `telemetry.degraded`. `arm`, `motor`, `camera`, `value` are always present (`null` when n/a).
* `Job` adds `subject` (dataset name for uploads, model key for loads, server model id for pulls).
  `progress.phase` is `queued|extracting|copying|hashing|uploading|downloading|verifying|loading`,
  optional `resumed_bytes`, `retries`. `result`: upload → `{dataset, dataset_id, dataset_name,
  version_id, version, resumed_parts, sent_parts, server_url, train_url}`; import/pull → `{model}`;
  load → `{model, key, device, policy_type, load_s, warmup_ms}`.
* `LocalDataset`: `{name, root, episodes, frames, fps, robot_type, cameras, video, size_bytes,
  finalized, finalize_reasons, task, uploads: UploadRecord[], uploaded: UploadRecord|null}` with
  `UploadRecord {server, dataset_id, version_id, version, at, server_url, train_url}`.
  `LocalDatasetDetail` adds `episode_list: {index, frames, length_s, tasks, telemetry_lines,
  max_temp_c: {arm: {motor: °C}}}[]`.
* `TelemetrySeries`: every value list has the length of `t` (`null` where that register group was
  not sampled on that line).
* `Settings` (GET/PUT): `{thresholds: {temp_warn_c, temp_hot_c, temp_critical_c, hysteresis_c,
  critical_consecutive, voltage_margin_v, voltage_nominal_ratio, current_ratio, load_stall_pct,
  load_stall_s}, telemetry: {hot_hz, cool_hz, min_slack_ms, max_age_s, monitor_hz, joints_hz},
  preview: {fps, width, quality}, safety: {max_relative_target, deadman_timeout_s, deadman_replay,
  estop_double_press_s, park_s, smooth_approach_s, stopping_deadline_s, camera_stale_pause_s,
  camera_lost_stop_s, overrun_pause_s, max_approach_deg}, device, session_retention_days,
  session_retention_bytes}`.
* `SessionSummary` (`GET /sessions`): `{id, kind, started_at, ended_at, outcome, reason, dataset,
  model, robot, episodes, max_temp_c}`.
* Heartbeat: the UI sends one every 250 ms; the dead-man timeout is `safety.deadman_timeout_s`
  (1.0 s). E-stop goes over the control WS (no queue); the UI falls back to `POST /estop` when the
  socket is not open.
* Camera `rotation` is lerobot's `0|90|180|-90` (the UI shows -90 as 270°).

### 5.4 Video WebSocket `/ws/video`
* C→S (text): `{"type":"subscribe","cameras":["wrist","front"],"width":320,"fps":12}`. A new message
  replaces the previous subscription. `cameras:[]` pauses. `width` (160–640) and `fps` (≤ 30) are
  optional and default to `settings.preview`.
* S→C (binary), one message per frame:
  `"HSF1"` (4 bytes) | `u16 BE header_len` | header JSON |
  JPEG bytes. Header: `{"cam":"wrist","tick":1834,"t":61.13,"w":320,"h":240,"src_w":640,"src_h":480,"policy_input":true,"stale":false}`
  (`FrameHeader`; `tick` is `-1` outside motion sessions).
* S→C (text) `{"type":"camera_error","cam":"front","code":"camera_stale"}`.
* Frontend decoding: `createImageBitmap(new Blob([jpeg], {type:"image/jpeg"}))`, drawn onto a
  `<canvas>`. Never through `<img src>` object URLs piling up.

---

## 6. UI flow, screen by screen

Route tree: `web/src/station/` (separate entry, `index.html` → `src/station/main.tsx`,
own router under `/`. Built with `vite build` into `web/dist`).
It reuses `components/ui/*`, the synced `hibiscus/PixelAnim` (`Sprite`, `PixelAnim`, `PxIcon`, `Garden`), `components/Mascot.tsx`, `lib/pixelTheme.ts`,
`lib/errors.ts`, `components/charts/LineChart.tsx`. Strings live in
`web/src/station/i18n/{en,vi}.json`, registered with `i18n.addResourceBundle(lang, "station", …)`
at the station entry, so the server's `translation.json` is never edited. Day and night themes,
WCAG AA as in `docs/ux/pixel-style.md`.

### 6.0 Shell (all screens)
* **Top bar** (dark wood): Hibiscus logo + "Station"; robot chip (profile, connected/disconnected,
  state icon; Hibi's mood (sidebar garden, pages): idle → `idle`, teleop/record/run → `working`,
  estopped/error → `sad`, warn/hot → `sad` (the flower wilts), disconnected → `sleep`); **motor health chip** (hottest motor,
  coloured, click opens the health drawer); server chip (paired workspace, or "offline"); language
  and theme toggles.
* **Left rail = wizard:** Robot · Calibrate · Cameras · Teleop · Record · Upload · Train · Run model,
  with a ✓ when a step's prerequisite is met (robot profile saved; both arms calibrated; at least
  one camera streaming; a dataset with at least 1 episode; uploaded; a model imported). A locked
  step shows why ("Calibrate the follower first"). Extra links: Datasets, Models, Sessions,
  Settings.
* **E-stop** (`EStopButton`): a 96×96 red pixel button, fixed bottom-right on every screen while
  `state ∈ {teleop, recording, replaying, inferring, calibrating}`. Space triggers it from anywhere
  (it never scrolls the page; it is ignored only while focus is in a text input, where Esc does the
  same). A second press, or the "Relax" button that appears, turns torque off. In `estopped`, the
  button becomes "Reset" (green) with the reason.
* **Banners:** critical (red, full width, cannot be dismissed until it clears), hot (orange),
  info. Hibi speech bubble on the right for warnings (`HibiAlert`), with the joint name and value.
* **Health drawer** (`MotorHealthPanel` large): for each arm, a table motor × {temp, V, A, load,
  status}, with sparklines of the last 120 s, the thresholds as dashed lines, and the `limits` from
  the motors.
* Reconnect: on WS loss the UI shows "Reconnecting…" and greys out controls. Because of the
  dead-man heartbeat, a run in progress stops on its own (§4.7).

### 6.1 Welcome / pair (first launch)
Hibi idle. "Station runs next to your robot. Data stays on this machine until you upload it."
Two cards: **Set up a robot** → Robot. **Pair with a Hibiscus server** (URL + PAT field, a "create
a token" link that opens `<server>/account/tokens?scopes=datasets:write,models:read,runs:read`).
Pairing can be skipped and done later from Settings.

### 6.2 Robot
* List of profiles, plus "New robot". The form: name; robot type (SO-101 / SO-100); **Follower
  port**, **Leader port** (optional: no leader means run-model-only use).
* Port picker: a list of USB serial ports (`GET /ports`) with description and VID:PID, the stable
  path preferred. Two helpers: **"Find by unplugging"** (modal: "Unplug the follower USB… now", a
  progress ring, then the found port) and **"Find by moving"** ("Move the leader arm a bit", 10 s).
* "Connect" → `connecting` (progress: open port, handshake: "6 motors found (ids 1–6, STS3215,
  firmware x)", configure). On failure: the Problem code mapped to copy, for example `port_busy`
  "Another program (LeLab? lerobot?) is using this port".
* Once connected: a live **joint table** (positions) and the **MotorHealthPanel**, compact, for each
  arm. This is the first place the user sees temperatures (R1).
* Rest pose: "Use current follower pose as rest pose" (saved in the profile; used for parking and
  safe stop).

### 6.3 Calibrate
* Per arm (Follower | Leader tabs): the existing calibration file for `calibration_id`, if any
  (date, path in lerobot's folder), with **"Use this calibration"** (`keep_existing`) or
  **"Recalibrate"**.
* Step 1 **Home**: an illustration (pixel SO-101 at mid pose), "Move every joint to the middle of
  its range, then press Set home". Torque is off (banner "the follower is limp, hold it").
* Step 2 **Ranges**: per motor, a horizontal bar with live `min | pos | max` (10 Hz WS),
  `wrist_roll` marked "full turn, nothing to record". Rows turn green when the range is ≥ 100 steps
  (warning otherwise, as in `app/calibrating.py:448-457`). "Finish" saves and writes to the motors.
  The calibration file path is shown.
* Calibrate both arms, then "Next: Cameras".

### 6.4 Cameras
* **Discovered** list (`GET /cameras/discover`): name, stable path, default mode, with a
  thumbnail through `POST /cameras/probe` (snapshot). **Configured** list: the cameras of the
  profile, with live previews (`/ws/video`), each with name (the dataset key: `wrist`, `front`, …),
  resolution, fps, fourcc, rotation.
* "Add" from a discovered camera opens a form (default 640×480@30 MJPG) and probes. When the
  measured fps < 90 % of the requested fps, a warning appears ("USB bandwidth; try MJPG or a lower
  resolution").
* The camera names here are the keys policies will expect (`observation.images.<name>`), which the
  screen says.

### 6.5 Teleop
Layout (desktop, 1280 px or wider): **CameraGrid** (all cameras, 2 columns) top left; **JointPanel**
top right (per joint: leader value, follower value, a mini bar, a clipped indicator); **MotorHealthPanel**
for follower and leader at the bottom; controls on the right: fps (15/30), Start, Stop, the
**session timer**, and loop stats (FPS, p95 tick). Narrow screens stack: cameras first, then health,
then joints. Start runs a 1.5 s smooth approach with the overlay "Follower moving to leader pose".

### 6.6 Record
* Setup form: dataset (new name, or append to an existing local dataset with a compatible schema),
  task (one line, kept per dataset), episodes, episode length, reset length, fps, video on/off, on
  timeout save/discard. Disk estimate (MB/episode from cameras × fps × length) and free space.
* The running view is the same as Teleop (cameras, joints, health), plus:
  * **phase header**: "Episode 4 / 20 · recording · 12.4 / 30 s" with a pixel progress bar; in
    `reset`: "Reset the scene · 6 / 10 s"; in `saving`: "Saving episode 4…" (Hibi working).
  * **Episode controls**: big buttons **Next →** (save and continue), **← Re-record**,
    **Stop (Esc)**. Same keys as lerobot: →, ←, Esc.
  * Per-episode strip: saved episodes as tiles with their length, and a temperature max icon from
    the sidecar.
* At the end: "20 episodes saved in `~/.hibiscus/station/datasets/picknplace_red`" → **Upload**
  (primary) or **Record more**.

### 6.7 Upload (and Datasets)
* The Datasets list (local): name, episodes, frames, fps, cameras, size, finalized ✓, uploaded ✓
  (server dataset/version link). The detail view shows episodes and their telemetry review chart
  (temperature per joint over the episode, alerts as markers), plus delete.
* Upload: target **New dataset on server** (name prefilled) or **New version of** (picker from
  `GET /server/datasets`). The progress bar shows hashing, uploading (parts sent/resumed, MB/s,
  retries) and done, with a link to the server dataset version and its validation status. The
  upload resumes after a restart of Station or after a network loss (state file reused).
* Not paired: the screen shows the pairing card instead.

### 6.8 Train (on the server)
* No local training. A card with the uploaded dataset, and the button **"Open training on Hibiscus"**,
  which deep-links to `<server>/w/<workspace>/runs/new?version=<dataset_version_id>` (the existing
  `NewRunWizard`, which preselects that version and opens on the policy step). Station returns the
  link as `train_url` in the upload job result and in `LocalDataset.uploaded`. It opens in a new tab.
* "Runs for this dataset" list (`GET /server/runs?dataset_id=`, when `runs:read` is granted):
  status, progress, and, once the run has exported a model, **"Pull & run"**, which pulls the model
  and opens Run model with it selected.

### 6.9 Run model (R2)
* **Model picker:** local models (name, policy type, source badge bundle/dir/server, verified ✓),
  the **Import** button (drop a zip, or enter a local path), and **"From server"** (list
  `GET /server/models`, then pull with a progress bar). Selecting a model runs `compat` and shows
  the check list, with one-click fixes (camera resolution, camera mapping dropdowns). **Load**
  shows the device, the load time and the warm-up latency.
* **Run setup:** task (prefilled from the model), fps (prefilled from training), episode length,
  episodes, max relative target (prefilled from the profile, editable down only, unless "advanced"
  is opened), record evaluation dataset on/off.
* **Running view:** this is where R2 lives. Every element is required:
  * **CameraGrid of ALL configured cameras**, labelled "policy input · 640×480 → 320×240", tick-stamped.
    A stale camera shows a striped overlay and an alert.
  * **Joint state vs commanded action:** per joint, a row with the current position, the policy
    action, the sent (clipped) value, and a 10-second LineChart (`components/charts/LineChart.tsx`)
    with two series, observed and commanded. A clipped tick is marked.
  * **MotorHealthPanel** (follower; leader when connected).
  * **Stats:** step (tick) and episode index; FPS actual vs target; inference latency p50/p95;
    loop p95; clipped %.
  * **Episode timer** with countdown, then the episode progress bar, then reset.
  * **E-stop:** the big button, larger here (128 px), and Space. **Next** and **Stop** buttons.
* After the run: a summary (duration, episodes, max temperature per joint, alerts), and a link to
  the session telemetry and, if recording was on, to the eval dataset.

### 6.10 Settings
Thresholds (temp warn/hot/critical with the validation rules of §4.5.3, voltage, load), telemetry
rates, preview width/fps, inference device, dead-man on/off for replay (always on for run), server
pairing, "open data folder", Station version and lerobot version.

### 6.11 Pixel assets
The Station sprites live in the Hibiscus design system (hibiscus-assets `design/icons_extra.py`) and
are synced into `web/public/pixel/` with the rest: `icon_thermo_ok/_hot/_critical`
(thermometer, 3 fill levels), `icon_camera`, `icon_estop` / `icon_estop_pressed` (red mushroom
button), `icon_plug` (port), `icon_calibrate` (ruler + screw), `icon_teleop` (joystick),
`ui_button_estop` (12×12 frame for the big button), `arm_home` (32×24 calibration illustration),
plus 8×8 glyphs (`thermo`, `estop`, `camera`, `plug`, …). Colours: ok = leaf `g`, warn = pollen `y`,
hot = orange `Y`, critical = hibiscus `r`. Text on them follows the AA pairs of the style guide (a
contrast test is added in `web/src/station/theme.test.ts`).

---

## 7. Data layout on disk

```
~/.hibiscus/station/                         # $HIBISCUS_STATION_HOME overrides; dir 0700
├── settings.yaml                            # global settings (thresholds, preview, device, port)
├── robots.yaml                              # robot profiles (RobotProfile list) + active profile id
├── station.pid / station.lock               # single instance
├── token                                    # local API token, 0600, regenerated at every launch
├── locks/<sha1>.lock                        # per serial port / camera device locks (§4.3)
├── datasets/
│   ├── picknplace_red/                      # LeRobotDataset root, exactly what lerobot writes (repo_id "local/picknplace_red")
│   │   ├── meta/ (info.json, stats.json, tasks.parquet, episodes/...)
│   │   ├── data/chunk-000/file-000.parquet
│   │   └── videos/observation.images.wrist/chunk-000/file-000.mp4
│   └── picknplace_red.hibiscus/             # Station sidecar, never inside the LeRobot root
│       ├── dataset.json                     # profile snapshot, task, created_at, uploads [{server, dataset_id, version, at}]
│       └── telemetry/episode_000000.jsonl.gz
├── models/
│   ├── index.json
│   └── so101_picknplace_act-r42-step10000/  # bundle tree (bundle.md §2) or {pretrained_model/} for plain dirs
├── sessions/<session_id>/{session.json, telemetry.jsonl.gz, station.log}
└── logs/station.log                         # rotating, 10 MiB × 5
```
* **Calibration** is not stored here. It lives in lerobot's location, respecting
  `HF_LEROBOT_CALIBRATION` / `HF_LEROBOT_HOME` (`utils/constants.py:93-101`):
  `<HF_LEROBOT_CALIBRATION>/robots/so_follower/<calibration_id>.json` and
  `<HF_LEROBOT_CALIBRATION>/teleoperators/so_leader/<calibration_id>.json` (the directory names
  come from `SOFollower.name = "so_follower"`, `SOLeader.name = "so_leader"`; LeLab uses the same,
  `app/config.py:17-18`). Files LeLab created are listed and reusable as they are.
* **robots.yaml** example:
```yaml
version: 1
active: desk_so101
robots:
  - id: desk_so101
    name: Desk SO-101
    follower: {type: so101_follower, port: /dev/serial/by-id/usb-1a86_USB_Single_Serial_5A46-if00,
               calibration_id: desk_follower, max_relative_target: 5.0, on_session_end: hold,
               rest_pose: {shoulder_pan.pos: 0.0, shoulder_lift.pos: -95.0, elbow_flex.pos: 95.0,
                           wrist_flex.pos: 60.0, wrist_roll.pos: 0.0, gripper.pos: 2.0}}
    leader:   {type: so101_leader, port: /dev/serial/by-id/usb-1a86_USB_Single_Serial_5A47-if00,
               calibration_id: desk_leader}
    cameras:
      wrist: {type: opencv, index_or_path: /dev/v4l/by-id/usb-HD_USB_Camera-video-index0, width: 640, height: 480, fps: 30, fourcc: MJPG}
      front: {type: opencv, index_or_path: /dev/v4l/by-id/usb-Logitech_C920-video-index0, width: 640, height: 480, fps: 30}
```
* Writes are atomic (temp file + `os.replace`), and files are 0600.
* The PAT is **not** in `~/.hibiscus/station`. It lives in the CLI credential store (keyring, or
  `<platformdirs config>/hibiscus/credentials.json` at 0600), shared with `hibiscus login`.

---

## 8. Security
* **Bind `127.0.0.1` by default.** `--host` accepts `127.0.0.1` or `::1`; any other address is
  LAN mode (§8.1) and exits with an error unless LAN mode is fully configured.
* **Local token:** 32 random bytes (`secrets.token_urlsafe(32)`), regenerated at each launch,
  written to `~/.hibiscus/station/token` (0600). The browser is opened at
  `http://127.0.0.1:18210/auth?t=<token>`, which sets the HttpOnly `hst` cookie (SameSite=Strict)
  and redirects to `/` (the token disappears from history). The cookie holds an HMAC session id, not
  the token. `hibiscus-station url` prints a fresh login URL for a running instance (it reads the
  token file).
* **Host header allow-list:** `127.0.0.1:<port>`, `localhost:<port>`, `[::1]:<port>`. Anything else
  gets `403 forbidden_host`. This blocks DNS rebinding.
* **CORS** off (same-origin SPA). There is no `Access-Control-Allow-Origin`. WS upgrades check that
  `Origin` equals `http://127.0.0.1:<port>` or `http://localhost:<port>`, and require the cookie (or
  `Sec-WebSocket-Protocol: hst.v1, bearer.<token>` for scripts).
* CSRF: SameSite=Strict, plus the required `X-Station: 1` on non-GET requests (a cross-site form
  cannot set it).
* **PAT handling:** the PAT is never sent to the browser. `GET /server` returns only the URL,
  workspace, token prefix (`hbp_ab12cd34…`) and scopes. Server proxy routes add the PAT on the
  server side. The minimum scopes are asked for and shown.
* **Files:** imported zip paths are checked (no absolute paths, no `..`, no symlinks); zip-bomb
  guards (total uncompressed size ≤ 20 GiB, ratio ≤ 200). `POST /models/import {path}` is limited to
  allowed roots. Dataset names match `[a-z0-9][a-z0-9_-]{0,63}`.
* **Models are code-adjacent:** `from_pretrained` loads safetensors (no pickle). Station refuses
  `*.bin`/`*.pt` pickle checkpoints in v1 (`model_incompatible`, `code=unsafe_weights`).
* Logs redact tokens (`hbp_` prefix + 4 chars).
* Physical safety is in §4.7. The UI states that the e-stop is software and does not replace power
  cut-off (copy on the first run of Run model, with an acknowledgement checkbox stored per profile).

### 8.1 LAN mode (0.2.0, opt-in)
Station on a Raspberry Pi or a Jetson usually has no screen, so the owner may open it from a laptop
on the same network. The model above stays; three settings must all be present, otherwise the
launch fails with exit code 2:
* `--host 0.0.0.0` (or one LAN address), set by `STATION_BIND` in the Docker `.env`;
* a **fixed token** in `$HIBISCUS_STATION_TOKEN`, at least 32 characters of `[A-Za-z0-9_-]`
  (`secrets.token_urlsafe(32)`), instead of the per-launch random one. It is still written to the
  token file; the login link becomes `http://<first allowed host>/auth?t=<token>`;
* the **names the browser uses**, `--allow-host` (repeatable) or `$HIBISCUS_STATION_ALLOWED_HOSTS`
  (comma-separated): `robot-pi.local` allows `robot-pi.local:<port>` and `robot-pi.local` (a TLS
  proxy on 443); `name:port` is taken as given. They extend the Host allow-list and the WS Origin
  allow-list (`http://` and `https://`). Wildcards are refused, so DNS rebinding stays blocked.

Cookie, CSRF header, Origin checks and the PAT rules are unchanged. The traffic is plain HTTP: the
token and the session cookie are readable by anyone who can sniff the network, and anyone with the
token can move the robot. The deploy guide therefore recommends an SSH tunnel first, LAN mode only
on a trusted network, and a TLS reverse proxy for anything wider. `hibiscus-station health` reads
the token file and calls `GET /api/v1/status` with it (container and service health checks).

---

## 9. Testing without hardware

### 9.1 Mocks (shipped in `hibiscus_station/mock/`, also used by `--mock` demo mode)
* `MockMotorsBus`: the `SerialMotorsBus` method surface that Station calls (`connect`,
  `disconnect(disable_torque)`, `sync_read(name, motors, normalize, num_retry)`, `read`, `write`,
  `sync_write`, `enable_torque`, `disable_torque`, `torque_disabled()` context, `set_operating_mode`,
  `set_half_turn_homings`, `write_calibration`, `is_calibrated`, `motors`, `calibration`). It is
  backed by a register dict per motor, with a simple physics: goal → present position with
  first-order lag and speed limit; a temperature model `dT/dt = k1·|load| − k2·(T − T_amb)`; load
  rises when goal and present differ (stall) or under a gripper squeeze; voltage sags under current.
  Fault injection: `inject(motor, temp_c=…, status_bits=…, timeout_rate=…, disconnect_after_s=…)`.
  Read latency is configurable (default 1.5 ms per sync read, `time.sleep`) so loop timing can be
  tested.
* `MockFollower(Robot)` / `MockLeader(Teleoperator)`: real subclasses of lerobot `Robot` /
  `Teleoperator` with `config_class` registered as `hibiscus_mock_follower` / `hibiscus_mock_leader`
  (`RobotConfig.register_subclass`), the same motor names and norm modes as SO-101, `bus = MockMotorsBus`.
  `MockLeader.get_action()` replays a scripted trajectory (sine per joint, or a recorded CSV) and
  can be driven from tests.
* `MockCamera(Camera)`: a lerobot `Camera` subclass. `read_latest`/`async_read`/`read` return
  generated RGB frames (a moving pixel-art scene with the frame counter drawn in, so tests can
  assert *which* frame reached the policy, the dataset and the preview), at a configured fps, with
  fault injection (stale, disconnect). `find_cameras()` returns fake devices.
* `DummyPolicy`: a tiny `PreTrainedPolicy`-compatible ACT checkpoint generated in a fixture
  (`ACTConfig` with `dim_model=32`, `chunk_size=5`, random weights, saved with `save_pretrained`
  and processors from `make_pre_post_processors`), so loading, the compatibility check and
  `predict_action` use real lerobot code paths on CPU in under 1 s. The real ACT checkpoint from
  `docs/spec/bundle.md` (Hibiscus repo; any ACT `pretrained_model` set in
  `HIBISCUS_ACT_CHECKPOINT`) is used in an opt-in `@slow` test.
* `FakeHibiscus` (reuse `cli/tests/fake_server.py`) for pairing, upload and pull.

### 9.2 Test layers (`tests`, pytest, `-m "not hil and not slow"` by default)
| Layer | What | Examples |
|---|---|---|
| Unit | pure logic | Feetech decode (units, sign bit 10, status bits); threshold validation and hysteresis; SafetyFilter clamp equivalence with `ensure_safe_goal_position` on random vectors; TelemetryScheduler (14 reads/s, never more than 1 per tick, forced read after `max_age_s`, skipped when slack < min); state-machine transition table (every illegal command → `busy`); robots.yaml round-trip; zip-import traversal guard |
| Owner integration (mocks, real threads) | timing and ownership | 30 Hz teleop for 10 s: p95 tick ≤ 36 ms with telemetry on (mock 1.5 ms reads); **no bus call from a thread other than the owner** (MockMotorsBus asserts `threading.get_ident()`); e-stop latency (WS estop → no `sync_write Goal_Position` after the current tick); thermal: inject 66 °C twice → hold, park, torque off within 2 s, state `estopped(thermal)`, reset refused while ≥ hot; overheat bit → torque off on the same tick; leader critical → session stops |
| Session flows | lerobot data correctness | record 3 episodes with next, rerecord and timeout (save/discard): `LeRobotDataset(root)` loads, `num_episodes`, frames = fps × duration ± 1, the `observation.images.wrist` frame counter matches the tick sequence, sidecar line count = telemetry reads during the episode, rerecorded episode sidecar removed, `finalize()` called, `check_recording` passes; replay stops within 1 tick; run with DummyPolicy: `policy.reset()` per episode, the preview frame tick equals the tick of the frames given to the policy (R2 "exact frames"), dead-man: no heartbeat for 1 s → estop |
| API contract | REST + WS | `openapi.json` up to date; every endpoint's Problem codes; WS hello and auth (4401), message schemas validated with JSON Schemas generated from the pydantic models; video WS binary header parse; host-header and Origin rejection; non-GET without `X-Station` → 403 |
| Remote | pairing/upload/pull against `FakeHibiscus` | upload resumes after a killed job; pull verifies the manifest; scope missing → `not_paired` + `missing_scope` |
| Frontend (Phase B) | vitest + MSW | the station MSW handlers implement the API and a scripted WS (mock-socket); screens render each state; Space triggers estop, ignored in text inputs except Esc; critical alert renders the banner + a wilting (`sad`) Hibi; CameraGrid draws binary frames; theme contrast tests |
| E2E demo | `hibiscus-station --mock` + Playwright via `web/scripts/node.sh` | golden path: create profile → calibrate both → add 2 cameras → teleop 5 s → record 2 episodes → upload to FakeHibiscus → import DummyPolicy zip → run 1 episode with cameras visible → inject heat → banner + estop |

### 9.3 CI
`station` job: `env -u PYTHONPATH -u AMENT_PREFIX_PATH uv run pytest` (CPU, no GPU, no devices),
`ruff`, `mypy --strict` (lerobot ignored like `worker/pyproject.toml`). The frontend job adds
`vite build` and its vitest suite.

### 9.4 Hardware-in-the-loop checklist (`tests/hil/README.md`, marker `hil`, manual)
On a real SO-101 pair: measured sync-read latency per register; units checked against a
thermometer and a multimeter (temperature ±2 °C, voltage ±0.2 V); status bits by stalling the
gripper (overload); 10-minute teleop at 30 Hz with telemetry (no overruns > 1 %); thermal stop by
lowering `temp_critical_c` to the current temperature + 1; e-stop latency with a high-speed phone
video (< 100 ms to freeze); camera unplug during recording; calibration interop (calibrate in
Station → `lerobot-teleoperate --robot.id=…` works, and the reverse).

---

## 10. Implementation plan

Two agents, one pass each, in this order: A1–A3 can start at once. B starts from `openapi.json` +
§5 and its own MSW mocks, so it does not wait for A to be finished. All work goes into new
directories: `station/`, `web/src/station/`, `web/vite.config.ts`,
`web/index.html`. **Existing files are not
edited**, apart from these, done last and kept to a few lines:
`frontend/package.json` (scripts `build:station`, `dev:station`), CI workflow (one job), and
optionally `cli/hibiscus/main.py` (A8, the `hibiscus station` alias).

### Phase A: station backend package `station/` (Python 3.12, FastAPI, lerobot pinned to git `fe1c545`)
| Task | Content | Done when |
|---|---|---|
| A1 Skeleton | pyproject (deps §4.1, `[tool.uv.sources]` lerobot rev + `hibiscus` path dep), `cli.py` (port, `--mock`, `--no-browser`, `url`), `app.py` (static SPA, Problem errors, security middleware §8: host allow-list, cookie/bearer auth, `X-Station`, bootstrap `/auth`), `settings.py`, paths §7, single-instance lock, `GET /status`, `GET/PUT /settings`, `openapi.json` export + contract test | `uvx --from . hibiscus-station --mock --no-browser` serves `/api/v1/status`; security tests pass |
| A2 Mocks | `mock/` §9.1 (MockMotorsBus with physics and faults, MockFollower/MockLeader registered with lerobot, MockCamera, DummyPolicy fixture) | unit tests of the mocks; `factory.py` builds real or mock devices from a profile |
| A3 Hardware owner | `hw/owner.py` (thread, command queue, state machine §4.4, e-stop Event), `hw/loop.py` (tick §4.5.1 with stats), `hw/safety.py`, `hw/feetech.py`, `hw/telemetry.py` (scheduler, ThermalGuard §4.5.3, safe stop), `hw/ports.py`, `hw/cameras.py` (CameraHub, PreviewEncoder), port and camera locks; robots CRUD + connect/disconnect/torque endpoints; `/ws` (hello, state, joints, telemetry, alert, heartbeat, estop) and `/ws/video` | owner-integration tests §9.2 pass on mocks, including the thermal and e-stop tests |
| A4 Calibration | `hw/calibration.py` (home/ranges per §2 L7, full-turn `wrist_roll`, `write_calibration` + `_save_calibration` into lerobot's dir), `GET /calibrations`, `POST /calibration/start|step`, WS `calibration` | calibration file written by the mock is loadable by `SOFollower(config).calibration` |
| A5 Sessions | `sessions/teleop.py`, `record.py` (LeRobotDataset create/append, features from robot + CameraHub, phases, next/rerecord/stop, on_timeout, `finalize`, sidecars), `replay.py`, `data/datasets.py`, `data/sidecar.py`, session history + telemetry endpoints | session-flow tests §9.2 pass |
| A6 Models & run | `models/importer.py` (zip/dir/bundle with manifest verify), `registry.py`, `compat.py`, load job (device auto, PEFT), `sessions/run.py` (countdown/episode/reset, `predict_action`, camera map, dead-man, overrun pause, optional eval recording) | DummyPolicy run test: actions applied, clipped, preview tick = policy tick; compat errors for wrong shape or missing camera |
| A7 Remote | `remote/pairing.py` (credentials reuse, scope check), `uploads.py` (Uploader + check_recording + progress → Job/WS), `pulls.py` (Puller → import), `/server/*` proxies, jobs endpoints | remote tests against `FakeHibiscus` pass |
| A8 Packaging | wheel build force-includes `web/dist` as `hibiscus_station/static/` (hatch build hook, which fails when the dist is missing, unless `HIBISCUS_STATION_ALLOW_NO_WEB=1`); `hibiscus station` alias (`cli/hibiscus/main.py`: `os.execvp("hibiscus-station", …)` when installed, otherwise print the install hint); HIL README | `uv build` produces a wheel; `uvx --from dist/*.whl hibiscus-station --mock` opens the UI |

### Phase B: station frontend (`web/src/station/`)
| Task | Content | Done when |
|---|---|---|
| B1 Build target | `index.html`, `vite.config.ts` (input `index.html`, outDir `dist`, dev server `127.0.0.1:18211` proxying `/api` (REST and both WebSockets) and `/auth` to `127.0.0.1:18210`, rewriting `Host` and `Origin` to the Station origin), `web/src/station/main.tsx` (i18n bundle `station`, router), `api/` (types generated with openapi-typescript from `openapi.json` into `web/src/station/api/schema.d.ts`, fetch wrapper with `X-Station` + Problem parsing via `lib/errors.ts`), `ws/` (control socket with hello, heartbeat 250 ms, reconnect backoff, a zustand-style store for status/joints/telemetry/alerts/session/jobs; video socket client with HSF1 parser) | `pnpm build` via `web/scripts/node.sh` produces `dist` |
| B2 Mock mode | MSW handlers for every §5.2 endpoint plus a scripted fake WS (states, telemetry with a heating scenario, generated JPEG frames) for `vite --mode mock` | screens are clickable without a backend |
| B3 Shell + shared components | top bar chips, wizard rail with locks, `EStopButton` (Space/Esc rules, double press = relax, reset), banners, `HibiAlert`, `MotorHealthPanel` (compact + drawer with sparklines and threshold lines), `CameraGrid` (canvas, policy-input label, stale overlay), `JointPanel` (+ observed vs commanded LineChart), `SessionTimer`, `LoopStats`; new sprites from the Hibiscus design system (synced) | component tests for thresholds/colours, Space behaviour, binary frame drawing |
| B4 Screens 1 | Welcome/pair, Robot (port picker with unplug/motion detect, connect progress, live joints and health, rest pose), Calibrate (home/ranges bars), Cameras (discover, probe, configured previews) | vitest per screen on MSW |
| B5 Screens 2 | Teleop, Record (setup, phase header, controls + keys, episode strip, end card), Datasets/Upload (list, detail with telemetry chart, upload progress), Train (deep link, runs list, pull and run) | vitest per screen |
| B6 Run model | model picker (import zip/path, from server, compat checklist with fixes, load), run setup, running view with **all cameras**, joints vs commands chart, health, stats, timer, e-stop, summary | vitest: all configured cameras rendered while `inferring`; critical alert → banner, controls disabled |
| B7 E2E | Playwright golden path on `hibiscus-station --mock` (§9.2) | green in CI |

---

## 11. Risks and open questions
1. **STS3215 unit factors** (current 6.5 mA/unit, status bit layout) come from the Feetech memory
   table, not from lerobot. They are isolated in `hw/feetech.py` and confirmed in HIL (§9.4).
   Voltage nominal differs between follower (7.4 V or 12 V kit) and leader (5 V/7.4 V), so
   thresholds are relative to the value read at connect, not absolute.
2. **Sidecar upload:** the server has no place for telemetry yet. v1 keeps sidecars local. A later
   server change could accept `hibiscus/telemetry/*` next to a dataset version (needs a contract
   bump on the server).
3. **Inference on CPU-only robot machines:** ACT at 30 Hz fits a recent CPU. Diffusion or SmolVLA
   often do not, which the overrun guard handles by pausing. Async/RTC (`lerobot/inference`) is the
   v2 path.
4. **Train deep link** (resolved): the server's New Run wizard already accepts `?version=<dataset
   version id>`; Station links there (`train_url`).
5. **USB bandwidth** with two or more 640×480@30 cameras on one hub: the Cameras screen measures and
   warns (fps < 90 %). MJPG is the default fourcc for that reason.
6. **Leader smooth approach:** SO leaders have no torque, so the follower always goes to the leader
   pose. When the follower is far away (> 30° on any joint), teleop start asks the user to move the
   leader closer first, instead of a long automatic move.
