# QC check: are QD-24 to QD-27 already in the published v0.2.8?

* **Question:** round 5 of the 0.2.9 hotfix gate (`QC-0.2.9-r5.md`) found QD-24 (Medium) and
  QD-25, QD-26, QD-27 (Low). Do these defects also exist in the release that users have now,
  v0.2.8? If so, 0.2.9 does not introduce them.
* **Answer: all four already exist in v0.2.8.** The same steps on the published 0.2.8 wheel give
  the same wrong or stale text. Sometimes the words differ a little. 0.2.9 adds none of them.

| QD | Pre-existing in v0.2.8 | Short evidence |
|---|---|---|
| QD-24 | **Yes** | During the thermal park (torque 1, arm moving, top bar "Teleop", Stop enabled), the banner reads "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down." with "The arm is held in place." The banner is the same text as in 0.2.9. evidence/01 |
| QD-25 | **Yes** | After cooling to 40 °C (health `ok`, top-bar chip 40 °C), the page still shows the 66 °C banner and "Let it cool down" for 20 s, plus "follower elbow_flex 66 C" in the lock box and 4 sidebar steps. The dock says "Stopped: motor too hot". Nothing says that a reset is now possible. evidence/02 |
| QD-26 | **Yes** | After Disconnect, the top bar shows "Disconnected · elbow_flex 58°C" and Robot 3D shows the last temperatures, still after the real motor cooled to 36 °C. A reload shows "Motor health –". After a lost device, the chip "shoulder_lift 62°C" stays, and the Teleop stats freeze at "FPS 217.1 / 30". A reload shows "–". evidence/03, 04 |
| QD-27 | **Yes** | Disconnected: Teleop says "No camera configured." / "Chưa cấu hình camera nào.". Record says "About 0 MB per episode with 0 camera(s), 0.01 GiB in total." / "Khoảng 0 MB mỗi tập với 0 camera, tổng 0.01 GiB.". The profile has 2 cameras. evidence/05, 06 |

## Artifact and set-up

* **Artifact:** the published release asset
  `https://github.com/Bigkatoan/hibiscus-station/releases/download/v0.2.8/hibiscus_station-0.2.8-py3-none-any.whl`.
  * Downloaded fresh. sha256 `85a7c96379fdf212f07fff2703d4c00ea9c438eef7086abec94aa9665df8c831`.
  * Installed with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`.
  * `hibiscus-station --version` prints `hibiscus-station 0.2.8`. The startup log says
    "Hibiscus Station 0.2.8: real hardware mode … real arms".
* **Hardware stand-in:** the same QC rig as round 5. The installed Station ran in real-hardware
  mode (no `--mock`) against two `tests/sts_emulator.py` pty chains with `realistic()` wire
  timing.
  * Follower: 12.1 V, 35-37 °C.
  * Leader: 5.3 V, with temperature register 0 and current register 1000 raw.
  * Two `mock` cameras, 640x480 at 30 fps.
  * The arms were moved with the emulator's hand function. The rig's "unplug" control closes the
    follower pty.
  * The calibration files were copied from the round 5 rig (same emulator seeds).
* **Home:** 0.2.8 has no "Home" feature in the UI. The equivalent is the profile's
  `follower.rest_pose`, which 0.2.8 already uses for the thermal park (`HardwareOwner._critical` →
  `_park`). We set it in `robots.yaml` to the same pose as round 5's Home.
* **Platform:** Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`), en 1280 light,
  and vi for QD-27.
  * We drove the UI with the mouse (Connect, Start teleop, Disconnect, I'm clear, reset).
  * Station state came from `GET /api/v1/status`. Torque and positions came from the emulator
    registers.
  * Servers ran on 127.0.0.1:18704 (Station) and 18705 (rig control). Both were stopped
    afterwards.
* **Date:** 2026-11-17. QC inspector: independent.

## Steps and results

### QD-24: "torque off / held in place" while the arm parks (pre-existing)

1. Connect. Teleop at 250 Hz with the leader mirrored, then a 1.3 s sweep, so the follower is away
   from the rest pose.
2. Set follower elbow_flex to 66 °C. Sample every ~130 ms: Station state, the emulator torque and
   position registers, and the visible alerts.

Result:

* For 1.7 s (2.36 s → 4.04 s after the trigger) the state is still `teleop` and torque is 1 on all
  6 motors. The arm moves: shoulder_pan goes from 2507 to 1960 raw, about 48°, and elbow_flex from
  1164 to 2013 raw. The top bar says "so101 Teleop" and Stop is enabled.
* During all of this, the red banner reads "**Motor critical: elbow_flex 66 °C. Robot stopped,
  torque off.** Let it cool down." with "**The arm is held in place.**" under it.
* At 4.04 s the state becomes `estopped`/`thermal` with torque 0. The second line changes to
  "Support the arm. Torque is off."
* This matches round 5's QD-24 exactly, with the same text. Before the critical banner, 0.2.8
  showed "elbow_flex is hot (66 °C). New sessions cannot start until it cools down." for about
  2 s while teleop went on.

### QD-25: the page keeps 66 °C and "too hot" after cooling (pre-existing)

1. After the thermal stop above, set elbow_flex to 40 °C and keep the same page open without
   resetting. Sample at 5, 10, 15 and 20 s.

Result:

* For the whole 20 s, `GET /status` gives health `ok`, hottest elbow_flex 40.0 °C, and the
  top-bar chip says "elbow_flex 40°C". Yet:
  * the banner still says "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it
    cool down.";
  * the lock box and 4 sidebar steps say "follower elbow_flex 66 C";
  * the dock says "Stopped: motor too hot".
* Nothing tells the user that a reset is now possible.
* **Variant with a reset while hot.** Heat to 66 °C, press "I'm clear, reset" (409 `motor_hot`),
  then cool to 40 °C and wait 15 s.
  * The banner updates its number to "elbow_flex 40 °C" but still says "Let it cool down".
  * The lock box still says "66 C".
  * The dock and a second alert keep "**Motors too hot: [object Object].** Let them cool down
    first." (in 0.2.8 this text also had the QD-3 `[object Object]` defect, which 0.2.9 fixes).
* A reset after cooling gives `idle`, and the alerts clear.

### QD-26: stale temperatures and stats after Disconnect or a lost device (pre-existing)

1. On the Robot page (idle), set elbow_flex to 58 °C. The top bar shows "elbow_flex 58°C" and
   "elbow_flex is getting warm (58 °C)."
2. Press Disconnect.
   * Station: state `disconnected`, health `ok`, hottest `null`.
   * The page still shows the top bar "Disconnected · elbow_flex 58°C", the warm-motor text, and
     the Robot 3D "Live arm" list "36° 37° 58° 36° 37° 35°".
3. Set the real motor to 36 °C and wait 5 s. The page still says 58 °C.
4. A reload shows "Motor health –" and no temperatures.
5. Connect again. Teleop, then shoulder_lift at 62 °C ("shoulder_lift 62°C", FPS "216.5 / 250").
   Unplug the follower pty.
   * Station: `error`/`bus_lost`, health `ok`, hottest `null`.
   * The page keeps "shoulder_lift 62°C" in the top bar.
   * The Teleop stats freeze at "Step 990, **FPS 217.1 / 30**, Loop p95 7.2 ms, Latency ~5 ms,
     Overruns 221".
   * A reload shows "Motor health –" and "Step –, FPS – / 30".
6. The same class as in round 5.
   * 0.2.8 also kept the "shoulder_lift is hot (62 °C)" alert after the lost device, because the
     Station still listed it as active. That is the QD-23 class, which 0.2.9 fixes.

### QD-27: "No camera configured" and "0 cameras" while disconnected (pre-existing)

1. The active profile has 2 cameras (wrist, front). With the robot disconnected, open Teleop and
   Record in en and vi.

Result:

* Teleop: "No camera configured." / "Chưa cấu hình camera nào."
* Record: "About 0 MB per episode with 0 camera(s), 0.01 GiB in total." / "Khoảng 0 MB mỗi tập
  với 0 camera, tổng 0.01 GiB."
* The wording differs from 0.2.9 ("about 450 kB … with 0 cameras, about 9 MB"). The defect is the
  same: the page counts 0 cameras instead of the 2 that are configured.

## Conclusion for the waiver decision

* QD-24, QD-25, QD-26 and QD-27 are **pre-existing in v0.2.8**. The 0.2.9 hotfix does not
  introduce them, and it does not make any of them worse.
* On the same steps, 0.2.8 additionally shows defects that 0.2.9 fixes: `[object Object]` in the
  hot-reset message (QD-3) and a hot alert that outlives a lost device (QD-23 class).
* Severity is unchanged from round 5. QD-24 is wrong safety information on screen while the arm
  moves; the robot's own behaviour (park, then torque off) is correct in both versions.
* Whether to ship 0.2.9 with these as known issues is a customer decision. This report only
  establishes that they are not regressions.

## Evidence (`docs/qc/evidence/0.2.9-waiver/`, downsized)

* 01: QD-24, the banner "Robot stopped, torque off / The arm is held in place" with the top bar on
  "Teleop", "Follower moving to the leader pose…", and Stop enabled during the park.
* 02: QD-25, 20 s after cooling: the chip shows 40 °C, while the banner and the lock text show
  66 °C.
* 03: QD-26, disconnected with the chip on 58 °C and the Robot 3D temperatures.
* 04: QD-26, a lost device: the stale 62 °C chip and "FPS 217.1 / 30".
* 05: QD-27, Teleop disconnected: "No camera configured."
* 06: QD-27, Record disconnected: "with 0 camera(s)".

The full-size screenshots and the driver scripts stayed outside the repository.
