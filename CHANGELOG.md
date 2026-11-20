# Changelog

All notable changes to Hibiscus Station are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions
may contain breaking changes; they are always called out under **Changed** or **Removed**.

Versions 0.1.0 and 0.1.1 were released inside the [Hibiscus](https://github.com/Bigkatoan/Hibiscus)
repository (`station/`); 0.2.0 is the first release of this standalone repository.

## [Unreleased]

## [0.2.10] - 2026-11-20

Hotfix for the field report on 0.2.9 (Windows, SO-101, 2026-11-19): "I cannot see the video and
the episodes I recorded." Known defect D-2.

### Fixed
- **The dataset page lists every recorded episode, also while the dataset is still being written.**
  Since 0.2.9 episodes are saved in the background, and LeRobot only writes the episode list
  (`meta/episodes`) when the dataset is finalized at the end of the session. Until then the page
  (and the Record page's saved-episode strip) showed no episode at all. From the 11th episode of a
  session, LeRobot's half-written episode file made the page answer "Internal error", and a Station
  closed in the middle of a session left a dataset whose page and the Datasets list answered
  "Internal error" for good. Now every episode shows as soon as it is saved; the episode being
  saved shows "Saving…" and the page refreshes by itself until it is written; an episode the
  Station never finished writing says so on its own row ("Cannot be read: the Station closed before
  this episode was fully saved. The other episodes are fine.") and the rest of the page works.
- **No more "Internal error" on the Datasets pages while an episode is saved.** Reading the dataset
  size while the encoder deleted its temporary frames, reading `meta/info.json` while LeRobot
  rewrote it, and a damaged telemetry file each failed the whole page.
- **Replay of an episode that is still being written** answers "Station is busy (saving)" instead
  of "Internal error"; its Replay button stays disabled until the episode is saved.
- A dataset page that fails to display keeps the menu and says so, with Reload and All datasets,
  instead of a blank error page.

### Changed
- API: each `episode_list` row of `GET /datasets/{name}` has a `state`: `saved`, `saving` or
  `unreadable` (openapi.json regenerated).

### Known issues
- Recording more episodes into a dataset left unfinalized by a Station closed mid-session
  (mode "append") still answers "Internal error"; record into a new dataset name instead.

## [0.2.9] - 2026-11-17

Field report on 0.2.8 (Windows, real SO-101, 2026-11-17) and the customer's decisions CR-1 and CR-2.

### Fixed
- **"I pressed Stop while recording but it ran to the end, and the cameras stopped."** Stop did end
  the episode at the press (the dataset in the report holds 22.5 s of the 30 s), but the episode was
  then encoded inside the control loop: for as long as the encoder ran (11 s for 22 s of two
  640x480 cameras on a fast PC, more on a laptop) Station sent no news, the cameras froze ("No fresh
  frames"), every button was greyed out and the timer kept counting to 00:30. Now Stop shows
  "Saving episode 1…" at once, the timer stops where you pressed, the cameras stay live and the arm
  holds its position while the episode is written, then the end card appears. An e-stop while an
  episode waits to be saved never delays the second Space (relax) any more, and a slow save is
  never cut off half written.
- **"No fresh frames" on a webcam that gives fewer pictures than asked** (common on Windows in low
  light or on a shared USB hub). A frame now counts as fresh for three camera periods (at least
  250 ms) instead of two, so these cameras no longer flicker or lose frames from the dataset. Each
  session now records, per camera, the measured frame rate, frame age, stale ticks and the camera
  driver (MSMF / DirectShow); the doctor zip carries it.
- **"The leader is still not recognised."** The leader's 5 V servos do not report temperature or
  current, and the bare "–" looked like a missing arm. The Leader heading now says
  "Connected · 6/6 motors answer" and those values read "not measured", with the reason on hover.
- **The stop card says whether the arm really holds.** After a double Space (relax) or a temperature
  safe stop the card said "Stopped. The arm holds its position." while the torque was off, and its
  hint mentioned a Relax button that was not there. It now follows the live torque state: held →
  "holds its position" with Return Home and Relax; off → "Torque is off: the arm is limp and does
  not hold its position" with Return Home only.
- **Programs: no false "No problems found".** A program is checked against the robot (its Home,
  calibration, trajectories) when it opens and after every save; until then the page says it is
  checking, never the all-clear.
- **Readable thermal messages.** "I'm clear, reset" while a motor is still hot says "Motors too hot:
  follower elbow_flex 66 °C. Let them cool down first." (was "[object Object]"), and the stop
  reason reads "66 °C" (was "66 C").
- **Replay page** says "Replaying episode N" (was "recording") and its "moving to the start" note
  ends with the approach (it said "Follower moving to the leader pose…" for the whole replay).
- **Record end card** says "N episodes saved in dataset <name>"; the folder on this computer is
  behind "Where is it on this computer?" with Copy path, and the card wraps properly at 390 px.
- Motor health tables fit beside Robot 3D on the Robot page at 1280 px; "1 episode" (was
  "1 episodes"); a draft trajectory says why Play is disabled (save the take first); Vietnamese
  says "Hiệu chỉnh" everywhere (was "Hiệu chuẩn" in a few places).
- **A recording that kept no episode says so.** An e-stop in episode 1, or Stop during the
  countdown, ended with "0 episodes saved" and an Upload button for a dataset that did not exist.
  The card now says "No episode was saved.", why (for example "Episode 1 was stopped (e-stop
  pressed), so it was not kept."), that the new dataset was not created, and offers Record again
  only. An e-stop in a later episode adds that line under "N episodes saved". The page of a
  dataset that no longer exists says so plainly.
- **The Docker route installs this release.** `install.sh`, the README image table,
  `deploy/.env.example`, `docs/deploy.md` and the systemd unit comment still named 0.2.1.
- **No raw words on screen.** The Sessions page showed keys such as `session.kind_program` and
  the English "stopped" in Vietnamese; the Cameras page showed "held · None" for a camera in use;
  some job phases, model compatibility problems and a motor fault bit showed their internal names.
- **A finished program run keeps its time** (it kept counting: "360.7 s" for a 3.3 s run).
- Wording: the Vietnamese leader tooltip reads naturally; "2 cameras", "1 episode · 2 alerts"
  (was "camera(s)", "episode(s)", "alert(s)").
- **No English server text under a translated banner.** The dead-man stop printed "no heartbeat
  from the UI for 1.0 s" under the Vietnamese banner and on the locked steps. Station's own lines
  (dead-man stop, hot motor, motor fault bits, low voltage, missing or refused calibration) now read
  in your language; any other server line (an error's detail, an OS error, a program fault) sits
  behind a closed "Technical details" / "Chi tiết kỹ thuật".
- **No console 404 after a recording that kept no episode** (the page asked again for the dataset
  Station had just removed).
- **Sizes in MB / GB.** The Record form said "0.00 GiB in total" for a short recording; it now says
  "about 3 MB in total". Dataset, model and upload sizes use decimal kB / MB / GB, and decimals
  follow the language ("1,5" in Vietnamese).
- **The Docker image's demo mode starts.** `--mock` in the image (HIBISCUS_STATION_HOME=/data) tried
  to create /data-demo, which the container user cannot, so the container never became healthy. With
  an explicit home the demo now lives in `<home>/demo`, and `hibiscus-station health` finds it.
- Counts: "1 step" in a program run, "1 sample" in a trajectory take, "1 frame" (were "1 steps",
  "1 samples", "1 frames"); speed hints read "°/s".
- **The red "Motor critical" banner goes away after the reset.** After a temperature stop, once the
  motor had cooled and you pressed "I'm clear, reset", the banner stayed on the open page (even
  while the arm moved again) until a reload, and in Vietnamese it said "about 0 s until cool
  enough". Every alert Station removes (reset, disconnect, unplugged USB) now leaves every open
  page at once; a page that reconnects starts from Station's current alerts; the countdown is
  hidden once the motor is cool. A motor warning from before an unplug no longer stays after the
  reconnect. Deleting the loaded model and pairing or unpairing also update other open pages.
- Vietnamese: "Hãy đặt lại nút dừng khẩn cấp trước." (was "reset"), "bộ dữ liệu" (was "dataset"),
  "điều khiển tay" (was "teleop"), "tệp", "mô-men"; the Calibrate step is "Kiểm tra hai tay".

### Changed
- **Stop holds the arm where it is (CR-1).** Pressing Stop in teleop, record, replay, run model,
  programs, trajectories or Return Home keeps the arm exactly in place with torque on: no further
  motion, no parking and no relax (even if the robot profile relaxes at the end of a session). You
  then choose **Return Home** (slow, Space stops it) or **Relax** (Station asks you to support the
  arm first). After your own e-stop the e-stop panel offers Return Home directly. Temperature or
  electrical safe stops and an unplugged USB keep their safe behaviour. A second Space within 2 s
  still relaxes at once and the screen says "Support the arm".
- **"Rest pose" is now "Home" (CR-2)** in English and Vietnamese. **Set Home at current position**
  and **Return Home** are in the top bar and under every Robot 3D panel (and on the Robot page);
  the Calibrate page asks you to set Home when you finish; a program block that needs Home
  (relax arm, go Home) shows **Set Home now** right in the list of problems. The calibration step
  that used to be called "Set home" (the middle of each joint) is now **Set middle**, so the two
  never mix. Saved profiles keep working (the stored field is still `rest_pose`).
- `GET /programs/{id}/state` answers `null` (200) for a program that has not run since the Station
  started (was 404, which browsers log as an error on every Programs tab load); 404 now means no
  such program.
- Programs: **relax arm** and **go Home** still need a Home. Relax first parks at Home so the arm
  never drops from a raised pose with nobody holding it; with no Home the program cannot start
  until you press "Set Home now" (one click). The Relax buttons outside programs always ask you to
  support the arm.

### Known issues (also in 0.2.8; waived by the customer for this hotfix, fixed in 1.0)
These four on-screen messages are wrong or out of date in 0.2.8 as well; 0.2.9 does not add them.
The robot itself always stops safely. Waived by the customer on 2026-11-17 (QC-0.2.9-r5,
QD-24 to QD-27).
- **QD-24:** during an over-temperature stop, the arm first moves back toward Home for about two
  seconds with torque on, but the red banner already says "Robot stopped, torque off" and "The arm
  is held in place". Keep clear of the arm until it is still.
- **QD-25:** after a hot motor has cooled down, the page still says it is at the old temperature
  (for example 66 °C) and "Let it cool down" until you press "I'm clear, reset". The reset works as
  soon as the motor is cool; the message does not tell you so.
- **QD-26:** after Disconnect or an unplugged USB cable, the open page keeps showing the last motor
  temperatures (and, after an unplug, the last FPS) as if they were live. Reload the page to see
  the real state.
- **QD-27:** while the robot is disconnected, Teleop says "No camera configured." and the Record
  estimate says "with 0 cameras" even though the profile has cameras. Connect the robot and the
  right numbers come back.

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

[Unreleased]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Bigkatoan/hibiscus-station/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Bigkatoan/hibiscus-station/releases/tag/v0.2.0
[0.1.1]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.1
[0.1.0]: https://github.com/Bigkatoan/Hibiscus/releases/tag/v0.1.0
