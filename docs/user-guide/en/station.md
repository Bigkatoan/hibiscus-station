# Hibiscus Station: the robot-side app

Hibiscus Station runs on the computer the robot is plugged into. It replaces the LeLab workflow:
connect the arms, calibrate, add cameras, teleoperate, record a LeRobot dataset, upload it to your
Hibiscus workspace, train on the server, pull the trained model and run it on the robot.

Two things it adds over LeLab:

* **Motor health.** Every motor's temperature, voltage, current, load and alarm flags are shown on
  every screen that moves the robot. A motor that gets warm is shown in yellow (50 °C), hot in orange
  (60 °C: no new session can start), critical in red (65 °C twice in a row, or an overheat/overload
  alarm). On critical, Station holds the arm, parks it at Home if you set one, and turns
  the torque off before the servo's own 70 °C cutoff would drop it.
* **Cameras while a model runs.** The Run-model screen shows every camera live, with the exact
  frames the model receives, next to the joint positions, the commanded actions, the motor
  temperatures, the speed (FPS) and the inference time. Cameras are also shown during teleop,
  recording and replay.

## Install

Two ways, both described in the [deploy guide](../../deploy.md):

* **Docker (recommended)** on a PC or mini PC (x86_64, optionally with an NVIDIA GPU), an NVIDIA
  Jetson Orin (JetPack 6) or a Raspberry Pi 5:

  ```bash
  curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh
  bash install.sh
  ```

* **Python wheel** (Linux, Windows 10/11 or macOS with Python 3.12 through [uv](https://docs.astral.sh/uv/)):

  ```bash
  uv tool install https://github.com/Bigkatoan/hibiscus-station/releases/download/v1.0.0a1/hibiscus_station-1.0.0a1-py3-none-any.whl
  hibiscus-station
  ```

  On a machine without an NVIDIA GPU add `--torch-backend cpu` to skip the CUDA libraries.

* **Windows 10/11 and macOS**: the same wheel (Docker is Linux only). On Windows the arm's ports are
  `COM3`, `COM4`... and cameras are numbers (`0`, `1`...); the servo board may need the WCH
  CH340/CH343 driver. See the [README](../../../README.md#windows-1011).

Station starts on `http://127.0.0.1:18210` and opens your browser. It only accepts connections from
the same computer. If the browser does not open, run `hibiscus-station url` (Docker:
`hibiscus-station-ctl url`) and open the link it prints. From another computer use an SSH tunnel
(`ssh -L 18210:127.0.0.1:18210 user@robot-pc`), or turn on LAN mode as the deploy guide explains.
To try it without a robot: `hibiscus-station --mock` (simulated arms, marked **DEMO**; its profiles and
data stay in `~/.hibiscus/station-demo`). If the real arm does not move, run `hibiscus-station doctor`
(with Station stopped) and send the zip it writes.

Close LeLab and any `lerobot-*` command first: only one program can use a serial port.

## The steps

1. **Robot.** Create a profile: robot type, follower port, leader port (optional). Each slot has
   "Find the follower arm" / "Find the leader arm" buttons (move it, or unplug it): move (or unplug)
   only that arm and its port goes into that slot. Station reads each port's motor voltage (read
   only) and hints which arm it is: leaders usually run at ~5 V, followers at 7.4 V or 12 V. If the
   arms look mixed up, press "Swap follower ⇄ leader" (Station never swaps by itself). Connect. You now see the joint
   positions and motor temperatures. Put the follower in a safe folded pose and press **Set Home at
   current position** (top bar, Robot 3D panel or Robot page; the Calibrate page asks for it):
   **Return Home** moves there slowly, and Station parks there before a safe stop turns the torque off.
2. **Calibrate.** For each arm: move every joint to the middle of its range, press *Set middle*, then
   move each joint through its whole range and press *Finish*. Calibration files are stored where
   lerobot keeps them, so LeLab and `lerobot-*` commands can use them too. Existing files can be
   reused with *Use this calibration*.
3. **Cameras.** Add the discovered cameras. Their names (`wrist`, `front`, ...) are the names models
   will expect (`observation.images.<name>`).
4. **Teleop.** Move the leader, the follower follows. If the leader is far from the follower pose,
   Station asks you to bring it closer first. Teleop runs as fast as LeLab's (250 Hz by default:
   each tick only reads the leader and sends the follower its goal); the screen shows the measured
   "latency ~X ms, Y Hz". If the rate is low, run `hibiscus-station doctor` (see
   [Diagnostic report](#diagnostic-report-doctor)): it times the bus and says what to do for your USB
   adapter (plug it straight into the PC, without a hub; a 1 ms latency timer exists on FTDI adapters only).
5. **Record.** Choose a dataset name, the task sentence, the number of episodes and their length.
   Keys: **→** next (save and continue), **←** re-record, **Esc** stop. An episode that reaches its
   time limit is saved (unlike LeLab, which silently re-records it); you can change that to
   *discard*. **Stop** ends the episode at once: the page shows "Saving episode…" while it is written
   (cameras stay live, the arm holds its position), then the end card. The **e-stop** (Space)
   is different: it drops the episode in progress, because its last frames were taken while the
   arm was being stopped. If no episode was saved at all, the end card says so and why, and a new
   dataset with no episode is not kept (there is nothing to upload).
6. **Upload.** Pair Station with your Hibiscus server once (server URL and a personal access token
   with `datasets:write` and `models:read`; add `runs:read` to see runs). Then upload the dataset as
   a new dataset or a new version. Uploads resume after a network loss.
7. **Train.** "Open training on Hibiscus" opens the server's New Run page. Training runs on the
   server, never on the robot computer.
8. **Run model.** Import a bundle zip or a `pretrained_model` folder, or pull a model from the
   server. Station checks that it fits your robot (joints, camera names and resolutions) and offers
   fixes. Load it, set the task and episode length, and start.
9. **Programs** (no training needed). *Trajectories*: record a follower motion with the leader arm,
   trim it, preview it on the see-through 3D ghost arm, replay it at 10-150 %. *Detection*: teach
   a camera what to look for (a colour in a region, or an ONNX image classifier). *Program*: chain
   trajectories, poses, waits and camera / button / joint / signal conditions in a block editor. A
   new or edited program must pass a **dry run** on a simulated arm before it can run on the robot.
   Every safety rule of a replay applies, and Space aborts a running program within one tick.

**Robot 3D view.** Every screen that moves the arm shows the follower in 3D, drawn from its live
joint positions, each motor coloured by its temperature. If the 3D arm does not match the real one
(for example `wrist_roll` turns the other way), recalibrate before trusting replays.

## Diagnostic report (doctor)

When the arm does not work as it should, one report lets us find the cause on the first try:

1. Stop Station (Ctrl+C in its window) and close LeLab, Feetech FD and any `lerobot-*` command.
2. Plug both arms into the computer and power them.
3. Open PowerShell (Windows) or a terminal, copy and paste:

   ```
   hibiscus-station doctor --verbose
   ```

4. Wait about a minute. The end of the report, **WHAT TO SEND / CẦN GỬI GÌ**, gives the full path of
   `hibiscus-station-doctor-<time>.zip`: send that one file. If it says the motor check is
   incomplete, do what it says and run the command again.

The report is in English (for engineers), apart from its last section. It starts with **LIKELY
PROBLEMS** (or "No likely problems found"): for example a demo profile is active, a calibration file
is missing, LeLab's calibration file is there but Station does not use it yet (Calibrate > Use this
file), the calibration file does not match what the motors carry, another program holds a port
(named), Station was killed and left `station.pid` behind, the bus is slow, or motors report
impossible readings (0 °C, 6.5 A).

`doctor` is **read only**: it writes nothing to a motor and switches no torque on. On every USB serial
port (also ports no robot profile names) it reads each motor: model, firmware, position, voltage,
temperature, `Max_Temperature_Limit`, current (`Present_Current`), load (`Present_Load`), status,
EEPROM against the calibration file, bus speed; then it prints a **raw dump** of registers 0-4, 13-15
and 56-70 of each motor (the bytes exactly as the motor sent them) with the decoded values, in the
same units and with the same "unknown" rules as the motor health screen. The zip holds the report,
the last 200 log lines, the robot profiles, the settings, the calibration files and the last 5
sessions; never the login token or a Hibiscus access token.

Options: `--verbose` also prints every bus error (motor id, register) while the motors are read,
`--no-ping` does not open the serial ports (the report then says the motor check was skipped),
`--no-cameras` does not probe cameras, `--out <folder>` is where the zip goes (default: the current
folder).

## Safety

* **Stop:** the Stop button of a screen (or **Esc** while recording) stops the motion and the arm
  **holds where it is** (torque on, it never falls). Then choose **Return Home** (a slow move,
  Space stops it) or **Relax** (Station asks you to support the arm first).
* **E-stop:** the big red button or the **Space** key. First press: the arm freezes and keeps its
  torque. Second press within 2 s: torque off, so support the arm (the screen says so). *Relax* asks
  to support the arm first. *I'm clear, reset* returns to idle; after your own e-stop *Return Home*
  resets and moves the arm Home. After a temperature or electrical stop, reset only once the motors
  are safe.
* While a model runs, the browser must stay open: if Station stops hearing from it for 1 s, the
  robot freezes.
* Movements are limited per step (`max relative target`, 5 degrees by default).
* The e-stop is software. Keep a way to cut the robot's power by hand.

## Where things are

`~/.hibiscus/station/` holds the robot profiles (`robots.yaml`), settings, datasets
(`datasets/<name>/`, a normal LeRobot dataset, with motor telemetry next to it in
`datasets/<name>.hibiscus/`), models (`models/`), session logs (`sessions/`) and, per robot,
trajectories, poses, detectors and programs (`robots/<id>/`). Calibration files stay where lerobot
keeps them (`~/.cache/huggingface/lerobot/calibration/`). The server token is stored by the
Hibiscus CLI: in the system keyring for the Python install; in the Docker install, where there is
no keyring, in `~/.hibiscus/station/hibiscus-cli/credentials.json` (mode 0600).
`hibiscus-station-ctl backup` saves all of this except datasets and models (`--full` adds them).

Before relying on Station, run the hardware checklist: [station-hardware-uat.md](station-hardware-uat.md).
