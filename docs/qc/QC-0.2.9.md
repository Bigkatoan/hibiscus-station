# QC report: Hibiscus Station hotfix 0.2.9 (hotfix gate)

* **Verdict: FAIL** (zero-defect rule: 11 open defects, QD-1 to QD-11; none is a safety
  regression).
* **Artifact tested:** branch `hotfix/0.2.9`, commit `f50f97e5166b6de6f587e9c8cf0e34b1ad56a3c5`.
  Cloned fresh, UI built with `web/scripts/node.sh pnpm install --frozen-lockfile && pnpm build`,
  wheel built with `uv build --wheel`. The result is `hibiscus_station-0.2.8-py3-none-any.whl`
  (sha256 `381de7d12aa31b16e3ee200d96ab7b707e99aa2564236550b0535995aed79c87`). It was installed fresh
  with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`. `hibiscus-station
  --version` prints `0.2.8` (see QD-1).
* **Platform:** Linux x86-64, Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`). We
  drove the UI with the mouse. The keyboard was used only for text fields and for testing the Space
  and Esc shortcuts.
* **Hardware stand-in:** the installed Station ran in real-hardware mode (no `--mock`) against two
  `tests/sts_emulator.py` pty chains with real wire timing (`realistic()`):
  * follower: 12.1 V, 35-37 °C;
  * leader: 5.3 V, temperature register 0 and current register ~1000 raw, the same as the field
    leader.
  
  The robot profile had two `mock` cameras at 640x480, 30 fps. Arm movement "by hand" came from the
  emulator's hand function. A second Station ran with `--mock` only to check the mock API.
* **Date:** 2026-11-17. QC inspector: independent, with no developer conclusions.

## Hotfix gate: item → result

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Fresh install of the patch artifact | **FAIL** (QD-1) | Install works and the app starts. Wheel name, `--version`, startup log, `pyproject.toml`, `__init__.py`, `openapi.json`, `web/package.json` and the README install URLs all still say **0.2.8**. |
| 2a | Field 1: Stop during recording stops at once (button) | PASS | Episode 1/1, 30 s, Stop clicked at 10.0 s. Within 0.01 s phase=`saving` with elapsed frozen at 10.07 s, the page shows "Saving episode 1…" and 00:10 / 00:30, and the state is `idle` after 6 s. Dataset `qc_stop1` holds 302 frames (10.07 s × 30). evidence/04, 06 |
| 2b | Field 1: Stop with Esc | PASS | Same flow with Esc: saving at once, 301 frames. |
| 2c | Field 1: arm holds where it stopped | PASS | Follower torque stays 1/1/1/1/1/1 and Present stays unchanged for 3.5 s after Stop, while the leader keeps moving. The card reads "Stopped. The arm holds its position." with Return Home and Relax. |
| 2d | Field 1: red STOP / Space during recording | PASS | The red STOP holds the arm and saves the episode (155 frames). A second Space within 2 s relaxes, and the screen says "Support the arm. Torque is off." |
| 2e | Field 1: page reopened while recording | PASS | The browser closed mid-session. The reopened page in vi at 390 px showed "Đang lưu tập 2…", and Dừng (Esc) stayed pressable. |
| 3a | Field 2: cameras deliver frames through a whole 30 s episode and across 3 episodes | PASS (mock cameras) | 3 × 30 s: 320 UI samples with 0 "No fresh frames". Session evidence shows `stale_ticks` 0 on both cameras and 29.8 fps measured. The dataset has 2700 frames, and each camera mp4 decodes to 2700 frames. evidence/03 |
| 3b | Cameras stay live while the episode is saved | PASS | Frame tick went from 400 to 440 and the image changed during "Saving episode 1…". |
| 3c | Real Windows webcam (MSMF/DirectShow, lower real fps) | **NOT VERIFIED** | No Windows machine or USB webcam was available. The automated test `test_a_camera_slower_than_configured_never_reads_as_stale` exists. |
| 3d | Frozen camera: page timer pauses, `camera_lost` after 3 s (REG-22) | **NOT VERIFIED** on the UI | The mock API has no camera-freeze injection. Covered only by `tests/test_sessions.py::test_camera_stale_pauses_then_stops_recording`. |
| 4 | Field 3 / leader telemetry reads as connected | PASS with defect QD-6 | Leader heading "Connected · 6/6 motors answer" / "Đã kết nối · 6/6 động cơ trả lời". Temperature and current read "not measured" / "không đo" with a tooltip. No bare "–" in the leader section (Robot page, top-bar popover, Teleop, Record). Follower values (35-37 °C, 12.1 V, 0.01 A, load ±4 %) are plausible. Layout defect QD-6. evidence/01, 02 |
| 5a | Home: set from the top bar | PASS | "Set Home" asks "Replace Home?". After confirming, `rest_pose` changed to the current pose. evidence/11 |
| 5b | Home: set / Return Home from the Robot 3D panel | PASS | The Robot 3D panel's Return Home moved the arm (`playing` → `idle`) to the stored Home. |
| 5c | Home: prompt after calibration | PASS | "Set this robot's Home" card with "Set Home at current position" after both arms are calibrated. evidence/09 |
| 5d | Home: blocked program block offers "Set Home now" in place | PASS with defect QD-2 | After Check, the problems list shows "Set Home for this robot first. · relax arm" and "… · go Home", each with a **Set Home now** button. One click sets Home and the list clears. vi: "Đặt Home ngay". evidence/10 |
| 5e | "Rest pose" renamed to Home everywhere (vi + en) | PASS | No "rest pose" / "tư thế nghỉ" in the UI strings. The calibration step is now "Set middle". |
| 6 | Relax asks to support the arm | PASS | en "Support the arm … I am holding it, relax"; vi "Hãy đỡ tay robot … Đã đỡ tay, thả lỏng". Torque stays on until confirmed, and Cancel keeps the hold. evidence/07, 08 |
| 7 | Golden path end to end: connect → calibrate → teleop → record 2+ episodes → stop → Home → program with relax / go Home → e-stop → recover | PASS with defects QD-2, QD-3, QD-4 | Connect (pty), calibrate both arms (Set middle, ranges, Save), Check: 0.0° difference. Teleop: follower tracks the leader. Records: `qc_full3` (3 × 30 s), `qc_stop1`, `qc_stop_esc`, `qc_vi_390` (2 × 30 s). Return Home ran. Program "relax test" (relax arm → go Home) passed the dry run, then ran on the robot and **Completed** (log: relax arm done 3.4 s, go Home done 3.7 s). "relax only" ended with torque off. E-stop: UI lost / Space / red STOP → "I'm clear, reset" → rerun completed. evidence/12 |
| 8a | Neighbour: replay | PASS with defect QD-5 | Replay of `qc_full3` #1 moved the follower; Stop held it. Labels are wrong (QD-5). evidence/16 |
| 8b | Neighbour: run model (import + run, mock ACT policy) | PASS | A random-weight ACT (`make_dummy_act`, cameras wrist/front) imported from .zip through the file chooser. The compatibility list is all green, it loaded on CPU in 2 s, `inferring` moved the arm, and both cameras were live. Stop → hold. evidence/19 |
| 8c | Neighbour: trajectory record / play | PASS with defect QD-7 | Recorded "wave" with the leader, Stop → hold. Edit → Save take → Ready → Play: `traj_play` completed. |
| 9 | Danger stops keep safe behaviour (over-temperature injected in the emulator) | PASS with defect QD-3, QD-4 | elbow_flex set to 66 °C during teleop. After 2 samples the arm parked toward Home, then torque went off on all 6 motors: `estopped`, reason `thermal`. Banner: "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down. Support the arm. Torque is off." The top-bar chip turned red. Reset while hot was refused (409 `motor_hot`), and reset worked after cooling to 40 °C. evidence/13 |
| 10 | Plausibility of every number shown | **FAIL** (QD-3, QD-4, QD-5, QD-8) | Telemetry, timers, frame counts and dataset sizes are plausible. The failures are "[object Object]", "66 C", "recording" during a replay, "1 episodes", and "holds its position" with torque off. |
| 11 | No English leftovers in vi; term "Hiệu chỉnh" | **FAIL** (QD-9) | No English found on Home / Robot / Calibrate / Teleop / Record / Programs at 390 dark and 1280 light (apart from the agreed terms Home, Leader, Follower). Robot → Sửa shows "Hiệu chuẩn tay follower / leader", "Hiệu chuẩn mới". evidence/18 |
| 12 | 1280 / 390, light / dark | PASS with defects QD-6, QD-11 | No horizontal page scroll at 390. At 390 the top-bar Home buttons are hidden, but they are on the Robot page and in the Robot 3D panel. |
| 13 | Regression list smoke (REG-1 … REG-23) | see the table below | |
| 14 | Full automated suite (once, at the end) | see "Automated suite" | |

## Regression list smoke

| REG | Result | Evidence / reason |
|---|---|---|
| REG-1, 17, 18, 19, 20 | NOT VERIFIED (Windows) | Windows-only. Automated tests are in the suite run. |
| REG-2 | PASS (startup log) | Log says "real hardware mode … real arms". The demo profile is only in `--mock`. |
| REG-3 | PASS | The leader reads 0 °C: no alarm and no stop. Thresholds stay 50/60/65. |
| REG-4 | PASS | Calibration ranges for all 6 joints including wrist_roll. Save is enabled only when all are green. |
| REG-5 | PASS (emulator) | Teleop at 250 Hz, loop 221 fps measured. The follower tracks within a few steps. The customer's "feels like LeLab" check is NOT VERIFIED. |
| REG-6, REG-8 | NOT VERIFIED on the UI | Pty ports are not listed by `list_ports`, so port-finding by movement and unplug cannot be done on the UI. Automated tests only. |
| REG-7 | PASS | The calibration flow takes under 3 min. Check passes and teleop runs right after. |
| REG-9 | PASS | "Gắp đỏ" → `gap_do`, "抓取" → `program_1opb0ik`, at 390 vi. |
| REG-10 | PASS | E-stop during "Run on the robot" (UI lost) → reset → rerun completed from the start. |
| REG-11, REG-13, REG-23 | PASS | Leader 6.5 A / 0 °C are ignored, "not measured" is shown and there are no leader alerts. REG-13 can close on our side once the customer's UAT-0 doctor report confirms it. |
| REG-12 | PASS | While e-stopped, the Calibrate / Teleop / Record / Run model steps are locked with a reason. (QD-3 covers the "66 C" raw text.) |
| REG-14, 15, 16 | automated only | Covered in the suite run. |
| REG-21 | PASS (button, Esc, saving phase, reopened page) | Stop in the countdown and reset phases was not exercised by hand. |
| REG-22 | PASS for normal cameras; freeze path NOT VERIFIED on the UI | See item 3d. |

## Automated suite (run once, at the end)

* `pytest -q` (from a clean clone at `f50f97e`, `uv sync --locked`): **454 passed, 1 skipped, 2
  deselected (e2e), 1 failed** (`-x` stopped the run there). The failure was
  `test_teleop_latency.py::test_station_teleop_latency_matches_lelab`: station lag 65 ms against the
  limit of LeLab's 54 ms + 6. The machine was loaded at the time (QC servers, emulators and another
  workflow).
* After the QC servers stopped, the latency test and the 4 files after it were run once more on an
  idle machine: **71 passed**. This counts as timing flakiness under load, not a product defect, but
  the test should get headroom or retries on shared runners. It is not counted as a QD.
* `pnpm test` (vitest): **14 files, 182 tests passed**.
* UI build: CSP check and locale-guard check passed.

## Defects (QD)

| QD | Severity | Area | Steps → expected → actual | Evidence |
|---|---|---|---|---|
| QD-1 | Medium (release hygiene) | Version | Build the wheel from `hotfix/0.2.9` HEAD → expected 0.2.9 everywhere → actual: wheel `hibiscus_station-0.2.8-py3-none-any.whl`, `hibiscus-station --version` = 0.2.8, startup log "Hibiscus Station 0.2.8". Same in `pyproject.toml`, `hibiscus_station/__init__.py`, `openapi.json`, `web/package.json`, README / README.vi / user guide install URLs (v0.2.8). CHANGELOG says "0.2.9 - unreleased". The customer could not tell the fixed build from the broken one. | `hibiscus-station --version` |
| QD-2 | Medium | Programs | Program with relax arm + go Home, robot without Home → open the Programs tab (reload) → expected the problems list (or "not checked yet") → actual "No problems found." until the user presses Check. Dry run then says "The program has errors". This false all-clear is the screen of field report 4. | console capture; evidence/10 (after Check) |
| QD-3 | Medium (correct information) | E-stop / thermal | Thermal stop → press "I'm clear, reset" while the motor is still ≥ hot → expected a clear message naming the motor and temperature → actual "Motors too hot: **[object Object]**. Let them cool down first." plus the raw server detail "a motor is still hot; let it cool down" in monospace. The locked-step panel and the sidebar show the raw reason "follower elbow_flex 66 C" (no °). | evidence/14 |
| QD-4 | Medium (correct information, safety wording) | Stop card | (a) Double Space (relax), or (b) a thermal safe stop (torque off), then reset → expected wording that says the arm is limp / torque off → actual headline "**Stopped. The arm holds its position.**" / "Đã dừng. Tay robot giữ nguyên vị trí." next to "Support the arm. Torque is off." while all 6 follower motors have torque 0. The text also mentions Relax, but no Relax button is shown. A user may trust the arm to hold and let go. | evidence/15, 20 |
| QD-5 | Low (correct information) | Replay | Datasets → qc_full3 → Replay → expected "Replaying episode …" → actual "Episode 1 / 1 · **recording** · 7.0 / 30 s" and "**Follower moving to the leader pose…**" for the whole replay (phase `replay`). Nothing is recorded and no leader is used. | evidence/16 |
| QD-6 | Low (layout) | Motor health | Robot page at 1280 with Robot 3D shown (default) → expected the full table → actual: the Motor health tables scroll sideways inside the card. The header reads "Loa", the Load % and Status columns are hidden, and the new leader value is cut to "measure". At 1440 the leader table still overflows (388 px table in a 352 px card). | evidence/01 |
| QD-7 | Low (UX dead end) | Trajectories | Record a take, leave the page before "Save take" → the take shows **Draft** and **Play** is disabled with no reason. Expected a hint ("Save the take first", Edit → Save). Actual: no message. | evidence/17 |
| QD-8 | Low (wording) | Record / Datasets | Record 1 episode → "**1 episodes** saved in …"; dataset list "1 episodes · 302 frames". The same text is in the customer's own screenshot. | evidence/21 |
| QD-9 | Low (terminology, vi) | Robot → Sửa | vi shows "Hiệu chuẩn tay follower", "Hiệu chuẩn tay leader", "Hiệu chuẩn mới (…)". It must be "Hiệu chỉnh". Also in `vi.json` keys `needs_check_hint`, `trajectory_needs_check`, `pose_needs_check` ("hiệu chuẩn đã đổi"). | evidence/18 |
| QD-10 | Low | Programs | Every load of the Programs tab logs `404 GET /api/v1/programs/<id>/state` as a console error for a program that has not run yet. It is not visible to the user, but it is an error on a normal path. | console capture |
| QD-11 | Low (layout, 390 px) | Record end card | vi at 390 px: record 2 episodes → end card "Đã lưu 2 tập trong <dataset path>" → expected the text to wrap under the buttons → actual: the text squeezes into a one-word-wide column ("2 / tập / trong / …"), runs ~15 lines, and the "Tải lên" button overlaps it. The full local path is also shown, which is long and unhelpful. (Path redacted in the evidence.) | evidence/08 (lower part) |

Not counted as defects (by design, noted):
* Closing the browser during Return Home or a program run e-stops: "Robot stopped: UI connection
  lost" (dead-man). This is by design, but a hand-off note for the customer helps.
* At 390 px the top-bar Home buttons are hidden. They are on the Robot page and in the Robot 3D
  panel.

## What only the customer can verify (UAT, Windows + real SO-101)
1. REG-21 / REG-22 on Windows with two USB webcams:
   * record 3 × 30 s;
   * press Stop (button and Esc) at ~10 s;
   * check "Đang lưu tập…" at once, the timer stops, the cameras stay live, the arm holds, and the
     dataset holds ~10 s × 30 frames;
   * check that no camera tile shows "Không có hình mới" during normal recording (MSMF and DirectShow).
2. REG-23: the leader heading reads "Đã kết nối · 6/6 động cơ trả lời", with "không đo" and its tooltip.
3. CR-1 on the real arm: Stop holds with no sag, Về Home is slow, and Thả lỏng asks first.
4. Over-temperature handling is emulator-only here.

## Escape review: why 0.2.8 shipped with Stop-during-recording broken and cameras stalling
* **Should have caught it:** golden path "record → **stop mid-episode**" (a recovery path) and
  plausibility checks "cameras stay live while recording" and "the page timer matches the
  dataset".
* **Why it didn't:**
  1. *Check missing.* The 0.2.8 gate recorded episodes only to their time limit, or stopped the last
     episode with Esc on a mock with tiny 128x96 cameras. On a mock, encoding takes milliseconds, so
     the control-loop freeze while encoding (11 s for 22 s of two 640x480 cameras) never showed.
  2. *Ran on mock / wrong platform.* No check used realistic camera sizes, and nothing measured
     camera freshness or frame counts against episode length. Windows MSMF webcams at reduced real
     fps were never tested.
  3. *Unit tests green ≠ product.* No test asserted that the loop keeps publishing during a save.
* **Checks now added (QC lists):**
  * Golden path G-REC: record 3 × 30 s with two 640x480 cameras. Assert 0 "No fresh frames"
    samples, `stale_ticks` = 0, and dataset and per-camera video frame counts = 900 per episode.
    Also press Stop at 10 s with the button and with Esc: phase `saving` within 0.5 s, frozen timer,
    camera tick still advancing, torque on and Present constant, frames = 10 s × fps ± 1.
  * Recovery: reopen the page during saving.
  * Field platform item: Windows webcams NOT VERIFIED until UAT.
* **Automated tests that exist for it:**
  * `tests/test_field_029.py::test_stop_during_episode_answers_at_once_and_the_loop_keeps_running`.
    It makes `save_episode` take 2 s and checks Stop answers within a tick, the phase is `saving`,
    camera ticks keep flowing and the episode is saved.
  * In the same file: `test_stop_while_a_previous_episode_saves_keeps_both`,
    `test_estop_while_an_episode_saves_never_blocks_the_relax`,
    `test_a_camera_slower_than_configured_never_reads_as_stale`,
    `test_record_summary_carries_camera_evidence`, `test_record_stop_holds_while_saving_and_after`.
  * UI: `web/src/station/field029.screens.test.tsx`, "ends the episode at the press …" and "never
    runs more than 2 s ahead of the last message from the Station".
  * **QC verified fail-first:** `tests/test_field_029.py` from the candidate was run against the
    **v0.2.8** source tree and **9 of 10 tests fail**, for example "Stop blocked the control loop
    for 2.14 s", "the arm was relaxed", and phase `None` instead of `saving`. On the candidate all
    10 pass.
  * Gap: the two camera tests fail on 0.2.8 only through a `KeyError: 'cameras'` (missing evidence
    key), not through a stale-frame assertion. The REG-22 freeze path (page timer pauses,
    `camera_lost`) has no mock injection, so QC cannot exercise it on the UI. Recommended: add
    `camera: freeze` to `/api/v1/mock/inject` and an e2e step for it.
* **Owner line:** 0.2.8 shipped because QC never stopped a recording mid-episode with real-size
  cameras. That check is now on the golden-path list, with a failing-first automated test.

## Environment notes
* Servers used 127.0.0.1:18430 (Station, emulator rig), 18431 (rig control) and 18432 (`--mock`
  Station). All were stopped at the end.
* The QC driver scripts and full-size screenshots stayed outside the repository. Only the downsized
  screenshots under `docs/qc/evidence/0.2.9/` are committed.
