# Changelog

All notable changes to Hibiscus Station are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions
may contain breaking changes; they are always called out under **Changed** or **Removed**.

Versions 0.1.0 and 0.1.1 were released inside the [Hibiscus](https://github.com/Bigkatoan/Hibiscus)
repository (`station/`); 0.2.0 is the first release of this standalone repository.

## [Unreleased]

These changes are in the test build **1.0.0a1** (a pre-release, the M0 milestone of 1.0). Install it
with its own line (see the README); GitHub never offers a pre-release as its "latest" release.

### Added
- **Windows: install, update and go back with one line in PowerShell.** No admin rights, no git and
  no Python needed: paste the line from the README into PowerShell and it installs uv (checked by
  SHA-256), Python 3.12 and Station with exactly the libraries we tested for this release, checked
  against the release's `SHA256SUMS`. Your profiles, calibration, datasets and models are kept.
  To update, paste a newer release's line; to go back, paste the line of the version you want.
- **`hibiscus-station doctor` reads more from every servo**: its current (A) and load (%) next to
  position, voltage and temperature, plus the exact bytes each servo answered (a raw register
  dump), so a wrong reading such as 0 °C or ~1000 current can be traced to the motor or to Station.
  Every USB serial port is checked, also one that no profile names. The doctor only reads: it never
  writes a motor register and never switches torque on.
- **The doctor shows calibration file times in your local time**, with the offset (for example
  `2026-11-17 17:35:15 UTC+07:00`), like the rest of the report.
- **A motor that does not answer is no longer reported as a slow USB adapter**: the doctor times only
  the reads that succeed, so a loose servo cable shows as "motor does not answer", not "slow bus".
- **The doctor report ends with what to send**, in English and Vietnamese (*WHAT TO SEND / CẦN GỬI
  GÌ*): the one zip file to send, what it holds, and, when the motor check could not finish, what
  to close and how to run the doctor again.

### Changed
- **Version 1.0.0a1.** The test build has its own version number everywhere (`hibiscus-station
  --version`, the web page, the doctor report, the Docker image tags `1.0.0a1-cpu` / `-cuda` /
  `-jetson`), so it can never be mistaken for 0.2.8. The Windows install line and the installer's
  "go back to this version" line point at this build's own release.
- **The doctor report always starts with LIKELY PROBLEMS**, or "No likely problems found".

### Fixed
- **The doctor said "ConnectError" when Station was not running.** After Station was closed (or
  killed and left its `station.pid` behind) the report now says "Station is not running".
- **A port held by another program is now a likely problem**, with that program's name and what to
  close (LeLab, a `lerobot-*` command, Feetech FD), or "held by Station" when Station has it.
- **The doctor told CH340 / CH343 users to set a "latency timer"**, which those chips (the SO-101
  boards' USB chip) do not have. A slow bus on them now says to plug the arm straight into the PC
  (no hub); the latency-timer advice is only given for FTDI adapters.
- **No login token in the doctor's zip.** The local token is removed from every file in the zip and
  from the printed report, wherever it was pasted (log, profiles, settings, sessions, calibration).
- **The Docker image did not start with `STATION_ARGS=--mock`.** The demo tried to create `/data-demo`,
  which the image's user may not write. With `HIBISCUS_STATION_HOME` set (the image sets `/data`)
  the demo now keeps its data in `<home>/demo`, and `hibiscus-station health` finds it there.
- **The doctor report printed raw program values** (`cameras []`, `{'1': 777, ...}`,
  `{'shoulder_pan': 'match', ...}`, `['…/desk_follower.json']`). It now reads as plain text:
  `cameras: front, wrist`, `ids answering at 1 Mbps: 1-6 (model 777)`, `calibration file vs motors:
  all 6 match`, `motors carry the calibration of: …/desk_follower.json`; the same for camera
  formats, servo status bits, bus errors and Station alerts.
- **The Windows installer showed an English warning from uv telling you to fix PATH** (`... is not
  on your PATH. To use installed tools, run ...`) right before "Done", on every first install. The
  installer puts the command folder on PATH itself before installing, so the warning is gone; it now
  says so in both languages, and you only open a new PowerShell window and type `hibiscus-station`.

## [0.2.8] - 2026-11-16

### Fixed
- **"After an e-stop during *Run on the robot*, the next run finishes the previous turn"** (field
  report 0.2.7, Windows, real SO-101). The goals of the interrupted session (`last_sent`) outlived
  it: the next motion that targets only some joints (gripper, a pose with fewer joints, the hold of
  the joints a primitive does not move) drove the others back to where the e-stopped run was going.
  The owner now forgets them on every teardown and session start, so the next program or trajectory
  run always starts fresh (approach to the first sample, then the take from t = 0).
- **E-stop / reset never touch the calibration.** Checked: no EEPROM write and no file change; the
  "recalibrate" in the report was the follower frozen far from a folded leader (shoulder_lift
  141.8 deg, elbow_flex 117.3 deg apart), which teleop refuses on purpose.
- **Leader telemetry nonsense** ("gripper draws a high current (6.422 A)", "Motor telemetry reads are
  failing", "ok stale" on every leader motor). Values no STS3215 can report are now *unknown*
  (shown as a dash), never alerts and never a failed read: current above 3.5 A, load beyond
  +/-100 %, voltage outside 3-16 V, as temperatures already were; Present_Current's direction bit
  (bit 15) is masked. The leader (moved by hand, torque off) never raises current, load, status or
  voltage alerts, its temperature never goes beyond "hot", and nothing from the leader stops the
  robot or refuses a start; every follower protection is unchanged. "stale" now means a read got no
  answer ("no reply", with an explanation).
- **Locked steps were still usable.** A locked wizard step now opens a page that says why (and the
  Station's exact reason), links to the step to do first, and disables the page's controls; the
  Train page keeps its pairing form. Same on desktop and phone widths.
- **"New program" seemed to do nothing** when no program existed yet (the form was already open
  and the button toggled it), or while the list was loading or failing. The button now always
  opens the form and focuses its name field; a failing list shows the error with "Try again".
  `GET /programs` never goes through the hardware owner, so it answers while the owner is busy,
  e-stopped or in error (tested).

### Added
- **Return to rest pose** (`POST /robots/rest`, session kind `rest`, state `playing`): after an
  e-stop ended a motion and the latch is reset (`Status.interrupted`), a banner offers one slow
  minimum-jerk move to the profile's rest pose (peak speed `programs.approach_speed_deg_s`, at most
  30 deg/s), dead-man heartbeat on, Space / Stop cancels it.
- **Align follower to leader** (`POST /sessions/teleop {"align": true}`, phase `align`): when the
  leader is more than `safety.max_approach_deg` (30 deg) from the follower, teleop still refuses
  (`leader_far`, now with `params.can_align`), and the UI offers to move the follower slowly
  (minimum jerk, at most 30 deg/s, dead-man, e-stop) to the leader's pose, then teleop starts.
- Mock: `POST /api/v1/mock/inject` takes `hand: "hold"` with `hold` offsets and `current_raw`.

## [0.2.7] - 2026-11-16

### Fixed
- **"Calibration is too complicated; after calibrating, teleop does not work"** (field report
  0.2.5, Windows). Calibrate is now one guided flow per robot: follower, then leader, then a check
  of both arms, then teleop.
  - On entering, Station reads each arm's EEPROM and compares it with every calibration file on the
    computer (`GET /calibration/check`). A calibrated arm says "calibrated: ready to use"; an arm
    whose motors already carry another file (LeLab's `so_101_follower.json`, ...) offers exactly
    that file in one click. The full file list sits under "Advanced", shows which file the motors
    carry, and never offers a file that matches the other arm's motors (a leader file in the
    follower folder).
  - Ranges step: a tick per joint (wrist_roll included) once it moved 100 steps (LeLab's rule);
    "Save" stays disabled, and the Station refuses `finish_ranges`, until every joint is ticked.
    The leader follows the follower automatically.
  - `GET /calibration/compare`: with the leader held in the follower's pose, the per-joint
    difference; more than 20 deg (gripper: 20 %) is flagged as a wrong file or swapped roles before
    teleop.
- **"Access is denied" on COM8, then 6 retries and `bus_lost`** (field report 0.2.5). A serial
  device that goes away (Windows `ERROR_ACCESS_DENIED`, `ClearCommError`, "device not ready",
  `PermissionError`; Linux `EIO` / `ENODEV` / `ENXIO`) is now *device lost*: no retries, no
  torque-off storm on the dead port, state `error` with reason `device_lost` and a `status.lost`
  object (arm, port, USB identity, OS message). The UI explains it in plain words with a checklist
  (USB cable, follower power, close LeLab, USB selective suspend, re-plug) and a hint when it
  happened right after torque-on or teleop start (a far jump can brown out the follower supply).
  "Reconnect" (`POST /robots/reconnect`) waits for the adapter to come back (same serial number,
  by-id path or VID:PID, possibly a new COM number), updates the profile's port and connects again,
  writing the calibration back to the motors.
- **"Cannot create a new program"**: a name with no Latin letter or digit now gets a valid, stable
  id (`program_<hash>`); the form says when no robot profile is active (programs are stored per
  profile) and for which profile a program is saved when the robot is not connected; an error that
  is not a Station Problem (a proxy page, a bare `{"detail": ...}`) still shows its HTTP status and
  body.

### Known
- Both arms of the 0.2.5 report read 0 C everywhere: these motors answer temperature reads with
  zeros. Station ignores them since 0.2.3 (unchanged).

## [0.2.6] - 2026-11-16

### Fixed
- **Teleop lag** (field report: the follower trails the leader, LeLab's does not). Measured on the
  STS3215 emulator with real wire timing (`tests/teleop_bench.py`: 1 Mbaud, return delays, 1 ms USB
  latency timer, ~300 deg/s servos), leader moving at up to 94 deg/s: 0.2.4 ran at 30 Hz and its 5 deg
  relative cap (against the observation read at the start of the tick) clipped every tick, so the
  follower chased the leader **127 ms** behind (186 ms on a quick 340 deg/s move); LeLab's loop trails
  by the servo's own 54 ms. 0.2.6: **55 ms** (54 ms on the quick move), 229 Hz, nothing clipped; the
  pose sent to the follower is 4.6 ms old (LeLab 4.0 ms, 0.2.4 19.5 ms). With an 8 ms USB adapter:
  65 ms (LeLab 67 ms, 0.2.4 188 ms).
  - Teleop runs a lean tick: e-stop check, leader read, safety filter, goal write. The follower
    observation and camera frames follow the write at 30 Hz (at most every other tick), telemetry
    on the other ticks. Default 250 Hz (`TeleopRequest.fps`, up to 300); a slower bus just runs
    slower.
  - Leader-driven sessions (teleop, record) use the new `safety.teleop_max_relative_target`
    (30 deg) instead of the 5 deg cap meant for policies. The calibrated-range clamp, the thermal
    guard and the one-tick e-stop are unchanged. If the cap still clips more than 20 % of the ticks,
    a "follower cannot keep up" warning says so.
- **Leader and follower swapped** when the arm found by "find by moving" was not the one the slot
  expected. Each slot now has its own "Find the follower arm" / "Find the leader arm" buttons
  (move or unplug); the port found goes into that slot, and moving detection never offers the port
  already given to the other arm. A swap button exchanges the two ports; calibration ids stay with
  their role.

### Added
- `POST /ports/probe`: read-only supply voltage, model and firmware of each free port, with a role
  hint (~5 V: usually the leader; >= 6.5 V: usually the follower). The robot form shows the hint
  under each port and warns when the follower reads ~5 V or the leader >= 7 V. It never swaps by
  itself.
- Measured leader -> follower latency and loop rate: `joints.loop.latency_ms_p50/p95` and
  `clip_fraction`, the session summary (`loop.fps`, `loop.latency_ms_p50/p95`), the Teleop screen
  ("latency ~X ms, Y Hz") and `hibiscus-station doctor` (last session, plus an estimate from the
  timed bus reads with a slow-adapter warning: set the USB latency timer to 1 ms).

## [0.2.5] - 2026-11-16

### Fixed
- The Calibrate screen still labelled `wrist_roll` "full turn, nothing to record": the UI had its own
  hard-coded list. It now follows the server's `full_turn` flag, so `wrist_roll` shows its recorded
  min | position | max like every other joint (the 0.2.4 server change was already in place).

## [0.2.4] - 2026-11-16

### Changed
- Calibration follows LeLab: `wrist_roll` is recorded through its range like every other joint
  instead of being given the whole encoder ("full turn, nothing to record"). Glitched position
  reads outside the encoder range are ignored while recording, as LeLab does. Existing calibration
  files keep working; recalibrate (or reuse a LeLab file) to get a recorded wrist_roll range.

## [0.2.3] - 2026-11-16

### Fixed
- A real arm whose servos report 0 °C (temperature or `Max_Temperature_Limit`) no longer lowers every
  thermal threshold to -3 °C and stops both arms as "critical". Implausible temperatures (outside
  1-150 °C) and limits (outside 40-150 °C) are ignored with a warning; when no motor reports a real
  temperature the read counts as failed (telemetry degraded warning), not as overheating.

## [0.2.2] - 2026-11-16

First field report on a real SO-101 (Windows): Station listed the arm's port, but calibrate, teleop,
record and run did nothing to the arm, while LeLab drove it. The `-v` log showed
`demo_follower MockFollower read state`: the active profile was the demo profile that an earlier
`hibiscus-station --mock` run had saved in `~/.hibiscus/station`, so every command went to the
simulated arm.

### Fixed
- **A real run never drives the demo arm.** `--mock` now keeps its data in `~/.hibiscus/station-demo`
  (unless `--home` is given). Without `--mock`, a demo profile left in the real data dir is no
  longer active (it is kept, marked **DEMO**), and connecting it is refused with `409 demo_profile`
  ("simulated arms: the real arm would not move; create a profile for the real arm").
- The UI says when the arm is simulated: a **DEMO / TAY GIẢ LẬP** chip in the top bar, a DEMO badge on
  demo profiles (Connect disabled outside `--mock`), and on the Robot page, when real serial ports
  are plugged in, a banner with **Create a profile for the real arm** that fills in the detected
  ports. The profile form lets you pick an existing calibration id (for example LeLab's) for each
  arm.
- **One bad packet no longer fails a connect or a calibration.** lerobot sends its configuration and
  calibration writes (and torque switches) without retries; every bus call Station makes now gets
  two retries unless it asks otherwise (telemetry does not), through `hw/bus.py`
  (`StationMotorsBus`). Tested against an STS3215 emulator with 1-2 % lost or corrupted answers.
- **Every failure says why.** Bus errors in any command are `502 bus_error` with the motor id,
  register and lerobot's message (they were `500 internal_error: ConnectionError`). Connect reports
  its step: the port does not open (`port_busy`, with the OS error), the motors fail lerobot's check
  (missing ids, wrong model, mixed firmware: `bus_error`, step `handshake`) or the settings cannot be
  written (step `configure`). The UI shows the server's detail under the translated message, a
  banner with the reason when the robot is in error or e-stopped, and the exact reason under each
  locked step of the sidebar.
- Each arm's status carries `calibration_id`, `calibration_file`, `issue` (no file, which other files
  exist, or which motor field does not keep the written calibration), `bus_errors` and
  `last_bus_error`.
- **LeLab calibrations are found and reused.** `GET /calibrations` also lists the legacy folders of
  lerobot < 0.4 (`so101_follower`, `so100_follower`, `so101_leader`, `so100_leader`) with a `dir`
  field; `POST /calibration/start` takes `source` (a listed file) to copy it to the arm's
  calibration id (an existing file is kept as `.bak-<time>`) and write it to the motors. The
  Calibrate page lists these files with **Use this file**.
- Teleop no longer needs every configured camera to stream (LeLab teleoperates without cameras);
  record, run and programs still do.
- The SO-101 gripper's overload bit is a warning, not a safe stop: lerobot sets the gripper's own
  overload protection (`Overload_Torque` 25 %) so that squeezing an object trips it. Overload /
  overcurrent status and low voltage now need two consecutive reads before a safe stop (overheat
  still stops at once).
- The status reports the installed lerobot version instead of a fixed `0.7.1`.
- OpenCV's backend noise while probing cameras on Windows (`VIDEOIO/FFMPEG: Failed list devices
  for backend dshow`) is no longer printed.

### Added
- `hibiscus-station doctor [--verbose] [--no-ping] [--no-cameras] [--out DIR]`: versions, USB serial
  ports (VID:PID, by-id path, which process holds them), cameras, calibration files (all lerobot
  folders), profiles and the file each expects, the running Station's state, the last 200 log lines,
  and a **read-only** check of every configured arm whose port is free (ids answering at 1 Mbps,
  model, firmware, voltage, temperature, status, EEPROM calibration vs. the file, which calibration
  file the motors carry, sync-read error rate and latency). It starts with **LIKELY PROBLEMS** (e.g.
  `MOCK PROFILE ACTIVE ... real serial ports present: COM3`) and writes
  `hibiscus-station-doctor-<time>.zip` without tokens.
- Startup log line: mode (mock / real hardware), data dir, active profile and its device types.
- Every failed bus call (operation, register, motor ids, error) goes to `station.log`; `--verbose`
  also prints them on the console. lerobot's per-tick timing lines stay out of the log.
- `tests/sts_emulator.py`: a Feetech STS3215 chain on a pseudo-terminal speaking the real protocol,
  so the real rustypot / lerobot / `so101_*` path is tested without hardware
  (`tests/test_real_stack.py`, POSIX).

## [0.2.1] - 2026-11-16

Windows 10/11 (x64, Python 3.12 via uv) is now a supported platform for the wheel install, tested in
CI on `windows-latest` (pytest, wheel build, `uv tool install` + `--mock` smoke test); macOS gets the
same install smoke test. The Docker deploy stays Linux only.

### Fixed
- **Station starts on Windows**: `hw/locks.py` imported `fcntl` and crashed at startup
  (`ModuleNotFoundError: No module named 'fcntl'`). Device and instance locks now use
  `msvcrt.locking` on Windows (one byte past the header, so a second Station still reads and reports
  the holder's pid; seek + read/write instead of `os.pread`/`os.pwrite`) and `flock` on POSIX as
  before. Lock files are opened in binary mode.
- Windows port names share one lock however they are written (`COM3`, `com3`, `\\.\COM3`), and the
  port list marks Station's own ports as in use with any spelling; `os.path.realpath` is no longer
  applied to `COMx` names.
- Camera discovery on Windows and macOS probes OpenCV indices (0, 1, 2... up to three misses in a row)
  instead of lerobot's 60, never opening a camera Station is streaming (Windows refuses a second
  open). A camera index picked in the UI (`"0"`) now opens as an index, not as a file named `0`.
- The UI no longer risks a blank page on Windows, where the registry often maps `.js` to
  `text/plain`: the MIME types of the bundle's files are pinned.
- Text files are read and written as UTF-8 everywhere (JSON metadata, detectors, logs, pid / token
  files) instead of the Windows code page; `station.log` is UTF-8; the console falls back to UTF-8
  when stdout/stderr are pipes or files on Windows, so Vietnamese text does not raise.
- Atomic writes (`settings.yaml`, profiles, tokens, trajectories) retry `os.replace` briefly on
  Windows sharing violations.
- The 30 Hz control loop keeps its rate on Windows, where queue timeouts wake on the 15.6 ms system
  tick: the hardware owner sets a 1 ms timer (`timeBeginPeriod`) and waits between ticks with
  high-resolution sleeps while polling its command queue; `os.nice` is skipped there.
- A request body FastAPI cannot parse (e.g. JSON nested past Python's C recursion limit, 3000 levels
  on Windows) answers `400 validation_failed` instead of `internal_error`.
- Path checks reject `\` and `:` in session ids and keyframe camera names (Windows separators and
  drive letters).
- Model import by path accepts the other drive letters on Windows (like `/media` and `/mnt` on Linux).
- The lerobot calibration directory honours `$XDG_CACHE_HOME`, like `huggingface_hub` does.

### Changed
- `hibiscus-station --help` names the port spellings per OS (`/dev/ttyACM0`, `/dev/tty.usbmodem...`,
  `COM3`) and asks to close LeLab first. README / README.vi / deploy guide: Windows quick start (uv,
  CH340/CH343 driver, COM ports, cameras); Docker deploy documented as Linux only.
- CI: `windows-latest` job (pytest, wheel, `uv tool install` smoke incl. the JS MIME type), macOS
  install smoke test, and mypy `--strict` also run for `--platform win32` and `darwin`.

## [0.2.0] - 2026-11-16

### Added
- **Standalone repository** `Bigkatoan/hibiscus-station`: the Python package at the root, the UI as
  its own Vite + React app in `web/` (only the shared components it uses, the built Hibiscus
  artwork, a CSP no-eval check of the bundle), the SO-101 model, docs, tests and CI. The server
  contract the remote features rely on is pinned and tested (`tests/contract/`, Hibiscus `v0.1.1`).
- **Device deployment.** Docker images `ghcr.io/bigkatoan/hibiscus-station:<version>-cpu`
  (linux/amd64 + linux/arm64, Raspberry Pi 5), `-cuda` (amd64, NVIDIA GPU) and `-jetson` (Jetson
  Orin, JetPack 6, on NVIDIA's NGC PyTorch for integrated GPUs). Non-root, health check, safe stop
  on `docker stop`. `deploy/install.sh` (detects the machine, installs Docker after asking, udev
  rule, compose files, autostart), `hibiscus-station-ctl` (status, logs, url, ports, backup,
  restore, update with automatic rollback, rollback), a udev rule for the servo bus adapters with
  stable `/dev/hibiscus/arm-*` names, and a systemd user unit for the wheel install. First-boot
  checklists for the Raspberry Pi 5 and Jetson.
- **LAN mode (opt-in).** `--host` other than loopback, only together with a fixed token
  (`HIBISCUS_STATION_TOKEN`, ≥ 32 characters) and the host names the browser uses (`--allow-host` /
  `HIBISCUS_STATION_ALLOWED_HOSTS`), which extend the Host and Origin allow-lists (spec §8.1).
- `hibiscus-station health`: exit 0 when the running instance answers `GET /api/v1/status` with its
  own token (used by the container and the systemd unit).
- **Trajectories and block programs** (docs/spec/station-programs.md). Record a follower motion
  with the leader arm and replay it at 10-150 % (minimum-jerk approach to the start, every safety
  path of a replay). Named poses. Camera detectors: colour-in-region (HSV + ROI) and ONNX
  classifiers. External signals over HTTP and MQTT. A "Programs / Chương trình" screen with a
  Blockly editor in the Hibiscus theme. Programs compile to a typed AST checked against the stores
  and the calibration, run as the `programming` motion session (pause, stop, an e-stop that aborts
  within one tick) and write a trace per run. A dry run on a simulated arm is required before the
  first hardware run of each version.
- **Robot 3D view** (display only). The SO-101 follower drawn from the live joint positions, each
  motor coloured by its temperature, next to the cameras and in the program run panel; a
  see-through ghost arm previews a trajectory. The model is TheRobotStudio's SO-ARM100
  (Apache-2.0), decimated.
- Hardware checklist: sections for trajectories, programs, the 3D twin and on-device deployment.

### Changed
- The UI entry imports the locale guard first, so the charts also work under `LANG=C`.
- `hibiscus-station url` and the "already running" message print the LAN login link in LAN mode.

## [0.1.1] - 2026-11-16 (in the Hibiscus repository)

### Changed
- Dependency updates shared with Hibiscus 0.1.1.

## [0.1.0] - 2026-11-16 (in the Hibiscus repository)

### Added
- First release: the local robot-side app for SO-100/SO-101. Port detection (unplug or move),
  lerobot-compatible calibration, cameras with one owner each, teleoperation, LeRobot dataset
  recording with keyboard episode controls, resumable upload to a Hibiscus workspace, model import
  and pull with a compatibility check, running a policy on the robot with live camera feeds,
  per-motor temperature / voltage / current / load telemetry, thermal auto-stop, a dead-man switch
  and a keyboard e-stop. Mock hardware for demos and CI; a hardware acceptance checklist.

[Unreleased]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.8...HEAD
[0.2.8]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Bigkatoan/hibiscus-station/releases/tag/v0.2.0
[0.1.1]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.1
[0.1.0]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.0
