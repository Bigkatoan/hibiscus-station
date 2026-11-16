# Changelog

All notable changes to Hibiscus Station are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions
may contain breaking changes; they are always called out under **Changed** or **Removed**.

Versions 0.1.0 and 0.1.1 were released inside the [Hibiscus](https://github.com/Bigkatoan/Hibiscus)
repository (`station/`); 0.2.0 is the first release of this standalone repository.

## [Unreleased]

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

[Unreleased]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Bigkatoan/hibiscus-station/releases/tag/v0.2.0
[0.1.1]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.1
[0.1.0]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.0
