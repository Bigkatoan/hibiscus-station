# Hibiscus Station: hardware acceptance checklist (UAT)

Hibiscus Station was built and tested without any robot attached: every automated test runs on mock
motors, a mock leader, mock cameras and a tiny ACT policy. The items below can only be checked on a
real SO-101 (or SO-100) follower and leader. Run them once on your setup before relying on Station
for data collection, and again after a lerobot or firmware update.

Fill in the **Result** column (pass / fail / value) and keep this file with your lab notes. When an
item fails, open an issue with the session folder `~/.hibiscus/station/sessions/<id>/` attached
(it holds `session.json` and `telemetry.jsonl.gz`).

## 0. Before you start

* [ ] Power supply of the follower known (5 V, 7.4 V or 12 V kit): ______ V
* [ ] LeLab and every `lerobot-*` command closed (Station refuses a port another program holds).
* [ ] A thermometer (IR or probe) and a multimeter at hand.
* [ ] You can cut the arm's power by hand. The Station e-stop is software and never replaces this.
* [ ] Start Station: `hibiscus-station` (Python install) or `hibiscus-station-ctl up` (Docker). Note the
      version and image variant (`hibiscus-station-ctl status`): ______

## 1. Ports, connection, calibration

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 1.1 | Port list | Robot screen, port picker | Only USB serial ports, with VID:PID; `/dev/serial/by-id/...` paths offered | |
| 1.2 | Find by unplugging | "Find by unplugging", unplug the follower USB | The follower port is found within 15 s | |
| 1.3 | Find by moving | "Find by moving", move the leader arm | The leader port is found within 10 s | |
| 1.4 | Port in use | Start `lerobot-teleoperate` on the follower, then Connect in Station | Clear error "Another program (LeLab? lerobot?) is using this port" | |
| 1.5 | Connect | Connect the profile | State `idle`, 6 motors on each arm, temperatures shown | |
| 1.6 | Calibrate follower | Calibrate screen: home, then ranges, then Finish | File written under `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json`; `wrist_roll` marked full turn | |
| 1.7 | Calibrate leader | Same for the leader | File under `.../teleoperators/so_leader/<id>.json` | |
| 1.8 | Interop Station -> lerobot | `lerobot-teleoperate --robot.type=so101_follower --robot.id=<id> ...` with the Station files | Works without recalibration | |
| 1.9 | Interop lerobot/LeLab -> Station | Use a calibration made by lerobot or LeLab ("Use this calibration") | Positions look right in Station | |

## 2. Motor health telemetry (R1)

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 2.1 | Temperature unit | Compare a motor's Station value with the thermometer on its case after 10 min of teleop | Within ±2 °C (servo reads inside, may be warmer) | |
| 2.2 | Voltage unit | Multimeter on the bus supply vs Station `V` | Within ±0.2 V | |
| 2.3 | Current unit (6.5 mA/step, **unconfirmed**) | Stall the gripper on an object; compare with a clamp meter or bench supply reading | Same order of magnitude; note the ratio: ______ | |
| 2.4 | Load sign | Push a joint by hand both ways while torque is on | Load changes sign with the direction | |
| 2.5 | Status bits (**unconfirmed layout**) | Stall the gripper hard for several seconds | `overload` chip appears; Station stops the robot (critical) | |
| 2.6 | Leader voltage | Look at the leader voltage on a 5 V leader | No permanent voltage warning; if there is one, note `Min_Voltage_Limit`: ______ | |
| 2.7 | Limits read at connect | Health drawer tooltip | `Max_Temperature_Limit` shown (factory 70 °C) | |
| 2.8 | Loop timing with telemetry | Teleop 10 min at 30 Hz, then open the session summary | Overruns under 1 % of ticks, `telemetry_forced` small | |
| 2.9 | Read latency | `station.log` / session stats | p95 tick time under 36 ms at 30 Hz | |

## 3. Safety

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 3.1 | E-stop freeze | During teleop press Space (or the red button); film it with a phone at high frame rate | Arm freezes in under 100 ms, torque stays on, the arm does not fall | |
| 3.2 | E-stop relax | Press Space again within 2 s | Torque off; the dock says "Support the arm" | |
| 3.2a | Stop holds (CR-1) | Teleop, record, a program and a trajectory: press the screen's Stop (Esc while recording) | The arm stays exactly where it was (no drop, no move); the banner offers Return Home and Relax; Relax asks to support the arm first | |
| 3.2b | Record Stop (field 0.2.8) | Record a 30 s episode with two cameras, press Stop at ~10 s | At once: "Saving episode 1…", timer stops, cameras stay live; then the end card; the dataset holds ~10 s | |
| 3.3 | Reset | "I'm clear, reset" | Back to idle | |
| 3.4 | Thermal stop | Settings: lower `temp_critical_c` to (current temperature + 1), keep the rules (hot ≤ critical − 3, warn ≤ hot − 5); teleop until it triggers | Red banner, hold, park at Home (if set), torque off, state `estopped (thermal)`; reset refused while a motor is hot | |
| 3.5 | Home | Top bar: "Set Home at current position", then trigger 3.4 again | The arm moves Home before torque goes off | |
| 3.6 | Dead-man | During a model run, close the browser tab | Robot freezes within about 1 s (`ui_lost`) | |
| 3.7 | Relative target cap | Run a model or replay with max relative target 2.0 | Movements are slowed; clipped joints are flagged in the joint panel | |
| 3.8 | USB unplug | Unplug the follower USB during teleop | State `error (bus_lost)`, no crash; reconnect works | |

## 4. Cameras (R2)

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 4.1 | Discover and probe | Cameras screen | Each camera listed once with a snapshot; measured fps shown | |
| 4.2 | Two cameras on one hub | Add two 640×480@30 MJPG cameras | Both stream; warning if measured fps < 90 % | |
| 4.3 | Previews during recording | Record an episode | All cameras visible during the whole recording | |
| 4.4 | Previews during a model run | Run model | All cameras visible, labelled "policy input", tick numbers advancing | |
| 4.5 | Camera unplug while recording | Unplug a camera during an episode | Alert; the episode clock pauses; after 3 s the session stops (`camera_lost`); the dataset stays valid | |

## 5. Recording and upload

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 5.1 | Record 3 episodes | Record with →, ←, Esc and one timeout | Dataset under `~/.hibiscus/station/datasets/<name>`; the timed-out episode is saved | |
| 5.2 | Dataset valid | `python -c "from pathlib import Path; from lerobot.datasets import LeRobotDataset as D; print(D('local/<name>', root=Path.home()/'.hibiscus/station/datasets/<name>'))"` | Loads; episode count right | |
| 5.3 | Telemetry sidecar | Datasets screen, episode temperature chart | One chart per episode; nothing inside the LeRobot folder | |
| 5.4 | Upload | Pair with your Hibiscus server, Upload | Dataset version created on the server; validation passes | |
| 5.5 | Upload resume | Pull the network cable during an upload, plug it back, upload again | Resumes from the parts already sent | |

## 6. Models on the robot

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 6.1 | Import a bundle | Run model: Import a `.zip` from Hibiscus | "verified" badge; compat checklist green | |
| 6.2 | Pull from server | "From server", then Pull | Model appears and loads; device and warm-up latency shown | |
| 6.3 | Run one episode | Run 1 episode of 20 s | Robot moves; inference latency p50/p95 shown; summary with max temperature per joint | |
| 6.4 | CPU too slow | Run a heavy policy on CPU at 30 fps | Session pauses with "model too slow" instead of queueing stale actions | |
| 6.5 | Evaluation recording | Run with "record evaluation dataset" | `eval_...` dataset saved and loadable | |

## 7. Trajectories, programs and the 3D twin

Record two short trajectories A and B first, a pose `home`, and a colour detector, then build the
"red → A, blue → B" example program from the user guide.

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 7.1 | wrist_roll sign in the twin | Robot screen, Robot 3D: turn the follower's `wrist_roll` by hand (torque off) a quarter turn clockwise seen from the gripper | The 3D wrist turns the same way, by about the same angle | |
| 7.2 | Zero offsets in the twin | Put the arm in the calibration middle pose (every joint mid-range) | The 3D arm shows the same pose within about 5° per joint; note any offset per joint: ______ | |
| 7.3 | E-stop during the approach | Start replaying A with the arm far from its start (> 30°); press Space while it is moving to the start | Arm freezes within one tick; no new goal is sent after the press (film it: the arm never moves again until Reset); state `estopped` | |
| 7.4 | E-stop during a replay | Replay A at 100 %; press Space half way | Same as 7.3; the program run ends with outcome `estopped` | |
| 7.5 | Thermal critical mid-program | Lower `temp_critical_c` as in 3.4 and run the program on the robot until it triggers | The program stops within one tick, the arm parks at Home, then torque off; state `estopped (thermal)`; the program run ends with outcome `estopped` | |
| 7.6 | Relax with a Home | Home set; after a session press *Relax* (or profile `on_session_end: relax`) | The arm moves Home first, then torque off; it does not drop | |
| 7.7 | Run a model with a camera unplugged | Run model, unplug a camera the policy uses | Alert; the run pauses; after `camera_lost_stop_s` (3 s) the session stops (`camera_lost`), arm held | |
| 7.8 | Re-record after recalibration | Recalibrate the follower | A, B, poses and the program are marked "needs check"; a hardware run is refused until A and B are re-recorded or confirmed with a slow check replay | |
| 7.9 | Dry run again after trimming | Trim A's start or end and save | The program version changes; "Run on robot" is refused until a new dry run passes | |
| 7.10 | Ghost preview | Trajectories tab, select A, play the 3D preview | The see-through arm moves like the real replay of A (same direction, same order of joints) | |
| 7.11 | Detector on the real camera | Detection tab: draw the region, show a red then a blue object | The live label changes red → blue → none within about 0.5 s | |
| 7.12 | Operator button and external signal | Add a button block and an HTTP signal (`POST /api/v1/signals/<name>` with the token) | The program reacts to both | |

## 8. On the device (Docker, Raspberry Pi 5, Jetson)

| # | Check | How | Expected | Result |
|---|---|---|---|---|
| 8.1 | Unplug detection inside Docker | Robot screen, "Find by unplugging" with the container running | The port disappears and comes back; found within 15 s | |
| 8.2 | Stable names | `hibiscus-station-ctl ports` | Each adapter shows a `/dev/serial/by-id/...` path, and `/dev/hibiscus/arm-...` once the udev rule is installed | |
| 8.3 | Arm unplugged at boot | Reboot with the arms unplugged, plug them in later | Container starts and is healthy; the arms connect after plugging in | |
| 8.4 | Autostart | Reboot, do not log in | `hibiscus-station-ctl status` shows `healthy` within 3 min | |
| 8.5 | Safe stop on shutdown | Teleop, then `hibiscus-station-ctl down` | Arm holds, parks at Home, torque off before the container exits | |
| 8.6 | Update and rollback | `hibiscus-station-ctl update <new tag>`, then `rollback` | Backup written; healthy on the new tag; rollback returns to the old tag with calibration, trajectories and programs intact | |
| 8.7 | LAN mode | Set `STATION_BIND`, token and allowed hosts; open the link from a laptop | Works from the listed name; any other name or IP gets `403 forbidden_host` | |
| 8.8 | Model speed on this device | Run the ACT example at 30 fps | Note p50/p95 inference: ______ / ______ ms (Pi 5 CPU: expect overruns for anything bigger than ACT) | |

Sign-off: name ______  date ______  Station version ______  lerobot 0.7.1 commit `fe1c545`
