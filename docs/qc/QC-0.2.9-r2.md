# QC report: Hibiscus Station hotfix 0.2.9, round 2 (hotfix gate, re-run in full)

* **Verdict: FAIL** (zero-defect rule). All eleven defects of round 1 (QD-1 to QD-11) are fixed on
  the installed artifact. Round 2 found **6 new defects (QD-12 to QD-17)**. None of them is a
  safety regression: Stop, e-stop, relax and the thermal stop all behave safely.
* **Artifact tested:** branch `hotfix/0.2.9`, commit `bce592ee86f791751a556876651acdc58b31ccc7`.
  * Cloned fresh. UI built with `web/scripts/node.sh pnpm install --frozen-lockfile && pnpm build`
    (CSP check and locale-guard check passed).
  * Wheel built with `uv build --wheel`: `hibiscus_station-0.2.9-py3-none-any.whl`, sha256
    `0c00d3bfc8552112a185ba42b740013f5cddaaf15307512398fc6bdb479d81af`.
  * Installed with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`.
    `hibiscus-station --version` prints `hibiscus-station 0.2.9`. The startup log says
    "Hibiscus Station 0.2.9: real hardware mode … real arms".
* **Platform:** Linux x86-64, Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`). We
  drove the UI with the mouse. The keyboard was used only to type in text fields, to choose from
  native `<select>` lists, and to test the Space and Esc shortcuts.
* **Hardware stand-in:** the installed Station ran in real-hardware mode (no `--mock`) against two
  `tests/sts_emulator.py` pty chains with real wire timing (`realistic()`):
  * follower: 12.1 V, 35-37 °C;
  * leader: 5.3 V, temperature register 0 and current register 1000 raw on every motor, the same
    as the field leader.

  The robot profile had two `mock` cameras at 640x480, 30 fps. Arm movement "by hand" came from the
  emulator's hand function (still, gentle, sweep, mirror).
* **Date:** 2026-11-17. QC inspector: independent. Developer conclusions were not used. Round 1
  was used only for its list of checks and defects.

## Round 1 defects: re-test on the installed artifact

| QD | Round 1 defect | Result | Evidence |
|---|---|---|---|
| QD-1 | Version said 0.2.8 everywhere | **FIXED** | Wheel name, `--version`, startup log, `pyproject.toml`, `__init__.py`, `openapi.json` `info.version`, `web/package.json` and the README / README.vi `uv tool install` URLs all say 0.2.9 / v0.2.9. CHANGELOG has `## [0.2.9] - 2026-11-17`. The Docker install path is still pinned to 0.2.1 (new defect QD-13). |
| QD-2 | False "No problems found" on open | **FIXED** | Program "relax test" (relax arm → go Home) on a robot with no Home. In a fresh browser, and again after a reload, the Programs tab lists "Set Home for this robot first. · relax arm" and "… · go Home" with **Set Home now**, without pressing Check. "No problems found." never appears first. One click on Set Home now clears the list. evidence/01 |
| QD-3 | "[object Object]", "66 C" | **FIXED** | Reset while elbow_flex is at 66 °C: 409 `motor_hot`, and the page says "Motors too hot: follower elbow_flex 66 °C. Let them cool down first." The locked-step panel and the sidebar say "follower elbow_flex 66 °C". No raw server detail is shown. evidence/05 |
| QD-4 | "Holds its position" with torque off | **FIXED** | After a double Space (relax) and after a thermal stop, followed by reset: "Stopped. Torque is off: the arm is limp and does not hold its position." with "Return Home turns the torque back on…". Follower torque was 0 on all 6 motors. There is no Relax button and no "holds" text. In vi: "Đã dừng. Mô-men đã tắt: tay robot thả lỏng, không tự giữ vị trí." evidence/06 |
| QD-5 | Replay said "recording" / "moving to the leader pose" | **FIXED** | During the approach: "Moving to the start of episode 1…". Then "Replaying episode 1 · 7.0 / 30 s", and "Replaying episode 2" for #2. "recording" and "leader pose" never appear. Stop held the arm (torque 1, Present unchanged for 3 s). evidence/07 |
| QD-6 | Motor health tables overflow at 1280 | **FIXED** | With Robot 3D shown, all three tables have scrollWidth = clientWidth (608/608 at 1280, 768/768 at 1440, 318/318 at 390). All columns are visible at 1280. At 390 the A column is dropped by design, and the page does not scroll sideways. evidence/04 |
| QD-7 | Draft take: Play disabled with no reason | **FIXED** | We recorded "wave" and left the page before Save take. On reopening, the take shows "Draft" and "Not saved yet: open Edit, then press Save take to play it." Edit → Save take enables Play, and `traj_play` completed. evidence/08 |
| QD-8 | "1 episodes" | **FIXED** | End card "1 episode saved in dataset qr_stop1". Datasets list "1 episode · 304 frames" and "2 episodes · 527 frames". vi: "1 tập", "2 tập". |
| QD-9 | vi "Hiệu chuẩn" | **FIXED** | Robot → Sửa shows "Hiệu chỉnh tay follower / leader", "Hiệu chỉnh mới (…)". `vi.json` contains no "Hiệu chuẩn". evidence/14 |
| QD-10 | 404 console error for `/programs/{id}/state` | **FIXED** | `GET /programs/relax_test/state` before any run → 200 `null`. An unknown id still gives 404. No 4xx and no console error on Programs tab loads. |
| QD-11 | vi 390 end card squeezed | **FIXED** | vi, 390, dark. After 2 episodes the end card reads "Đã lưu 2 tập vào bộ dữ liệu qr_vi_390" on one line (318 px wide). The path is behind "Nằm ở đâu trên máy này?". The Tải lên / Ghi thêm buttons are below the text, and the page does not scroll sideways. evidence/03 |

**Fail-first check (by QC):** the candidate's changed web tests were copied onto the pre-fix
commit `25f59b4` and run with vitest. **13 tests fail**. They cover QD-2, 3, 4, 5, 7, 8, 9, 10 and
11, plus the Record Stop and thermal screens. All 191 pass on the candidate. The Python fail-first
results are in "Automated suite".

## Hotfix gate: item → result

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Fresh install of the patch artifact | PASS (wheel), with defect **QD-13** (Docker path) | See the header. The Docker route (`deploy/install.sh`) still installs 0.2.1. |
| 2a | Field 1: Stop button during recording | PASS | Episode 1/1, 30 s, Stop at 10.07 s. After 0.27 s: phase `saving` with elapsed frozen at 10.13 s, "Saving episode 1…", 00:10 / 00:30, and frame ticks still advancing. State `idle` after 6.2 s. Dataset `qr_stop1` has 304 frames (10.13 s × 30 = 303.9). evidence/02 |
| 2b | Field 1: Stop with Esc | PASS | Same flow: `saving` at once, then `idle`. `qr_stop_esc` has 303 frames. |
| 2c | Field 1: the arm holds after Stop | PASS | Torque stays 1 on all 6 motors and Present does not change for 3.5 s while the leader keeps moving. The card says "Stopped. The arm holds its position." with Return Home and Relax. |
| 2d | Field 1: red STOP / Space during recording | PASS (safety), with defect **QD-12** | The red STOP (clicked with the mouse) gives `estopped` with torque 1 on all 6 motors. A second Space within 2 s gives torque 0 and "Support the arm. Torque is off." The partial episode is dropped. That is acceptable for an e-stop, but the end card says "0 episodes saved in dataset qr_redstop" and offers Upload for a dataset that does not exist (QD-12). With one episode already saved and a red STOP in episode 2, the card correctly says "1 episode saved" (131 frames). *Correction to round 1:* its 2d script clicked the first button containing "STOP", which was the screen's Stop (Esc) button and not the red e-stop. The 155 frames it reported came from a Stop, not an e-stop. |
| 2e | Field 1: page reopened during saving | PASS | vi, 390, dark. We pressed Dừng 5 s into episode 2 and closed the browser. The reopened page showed "Đang lưu tập 2…", 00:05 / 00:12, and "Dừng (Esc)" was enabled. The end card followed. `qr_vi_390` has 2 episodes and 527 frames (12 s + 5.57 s at 30 fps). |
| 2f | REG-21: Stop in the countdown and reset phases | PASS (stop), with defect **QD-12** | Countdown: Stop → `idle` within 0.01 s, torque held, and no episode is saved. The card says "0 episodes saved in dataset qr_stop_countdown" and offers Upload for a dataset that does not exist (QD-12). Reset phase: Stop → `saving` within 0.03 s, and episode 1 is kept (180 frames = 6 s × 30). |
| 3a | Field 2: cameras deliver frames through 3 × 30 s | PASS (mock cameras) | 319 UI samples, 0 "No fresh frames". Session summary: `stale_ticks` 0 and 29.8 fps measured on both cameras. The dataset has 2700 frames, and each camera mp4 decodes to 2700 frames at 640x480. |
| 3b | Cameras stay live while saving | PASS | The frame tick advanced during "Saving episode 1…" (evidence/02). |
| 3c | Real Windows webcam (MSMF/DirectShow) | **NOT VERIFIED** | No Windows machine or USB webcam was available. |
| 3d | Frozen camera: page timer pauses, `camera_lost` after 3 s (REG-22) | **NOT VERIFIED** on the UI | `/api/v1/mock/inject` still has no camera-freeze injection, and the pty rig cannot freeze a mock camera. Covered only by the automated test `test_camera_stale_pauses_then_stops_recording`. |
| 4 | Field 3: leader telemetry reads as connected | PASS, with wording defect **QD-17** | "Connected · 6/6 motors answer" / "Đã kết nối · 6/6 động cơ trả lời". Temperature and current show "not measured" / "không đo" with a tooltip. No bare "–" appears. Follower values (35-37 °C, 12.1 V, 0.01 A, load 0) are plausible. The vi tooltip grammar is covered by QD-17. |
| 5a | Home: Set Home from the top bar | PASS | The dialog reads "Replace Home? The follower's current position becomes the new Home." After confirming, `rest_pose` in `robots.yaml` matches the current pose. |
| 5b | Home: Return Home from the Robot 3D panel | PASS | We moved the arm away with teleop, then pressed the panel's Return Home: `playing` → `idle`. The arm ends at the stored Home (within 1 step). |
| 5c | Home prompt after calibration | PASS | "Set this robot's Home" card with "Set Home at current position" after both arms were calibrated. |
| 5d | A blocked program block offers "Set Home now" | PASS | See QD-2. |
| 5e | "Rest pose" renamed to Home (vi + en) | PASS | No "rest pose" or "tư thế nghỉ" in either locale file. The calibration step is "Set middle". |
| 6 | Relax asks to support the arm | PASS | "Support the arm. Torque turns off and the arm goes limp where it is…", with Cancel and "I am holding it, relax". Torque stays 1 until confirmed, and Cancel keeps the hold. |
| 7 | Golden path end to end | PASS, with defect **QD-16** | Connect (pty), calibrate both arms (Set middle, ranges for all 6 joints including wrist_roll, Save), Check: 0.0° difference. Teleop: the follower tracks the leader. Record: 3 × 30 s, Stop, Esc, vi 390. Return Home. Program "relax test" passed the dry run (5.8 s) and ran on the robot to **Completed** (relax arm done 3.0 s, go Home done 3.3 s). E-stop with Space mid-run → `estopped`, run log "1.5 end · E-stopped" → "I'm clear, reset" → the rerun completed from the start. Closing the page mid-run stopped with "Robot stopped: UI connection lost." (dead-man, by design). Later, the completed run shows a growing duration (QD-16). |
| 8a | Neighbour: replay | PASS | See QD-5. |
| 8b | Neighbour: run model (import + run, random-weight ACT) | PASS | The .zip was imported through the file chooser. Compatibility: joint state and action sizes match, cameras wrist/front. Loaded on CPU in 4 s. "Episode 1 / 1 · model running · 4.7 / 30 s", the arm moved, and there were 0 "No fresh frames". Stop → `idle`, and the arm holds (torque 1, Present unchanged). |
| 8c | Neighbour: trajectory record / play | PASS | See QD-7. |
| 9 | Over-temperature stop (elbow_flex 66 °C injected during teleop) | PASS | The arm parked toward Home, then torque went off on all 6 motors: `estopped`, reason `thermal`. Banner: "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down." Reset while hot → 409 with a clear message (QD-3). After cooling to 40 °C the reset works, and the card says torque is off (QD-4). |
| 10 | Plausibility of every number shown | **FAIL** (QD-12, QD-15, QD-16) | Telemetry, timers, frame counts, dataset sizes and teleop rate (217 Hz of 250, latency ~5 ms) are plausible. The failures are "0 episodes saved" plus Upload for a missing dataset, "2.6 KiB" on a missing dataset, "None" on the Cameras page, and "360.7 s · 2 steps" for a 3.3 s run. |
| 11 | No English leftovers in vi; "Hiệu chỉnh" | **FAIL** (QD-14, QD-17) | 16 pages swept in vi at 390 dark and 1280 light. The Sessions page shows raw keys (`session.kind_program`, `session.kind_rest`, `session.kind_traj_play`, `session.kind_traj_record`) and the English outcome "stopped". "Hiệu chỉnh" is used everywhere. |
| 12 | 1280 / 390, light / dark | PASS | No page scrolls sideways at 390 (en light, vi dark) or at 1280 (en dark, vi light). No `undefined`, `NaN` or `[object Object]` anywhere. The only `None` is QD-15. |
| 13 | Regression list smoke (REG-1 … REG-23) | see below | |
| 14 | Full automated suite (once, at the end) | see "Automated suite" | |

## Regression list smoke

| REG | Result | Evidence / reason |
|---|---|---|
| REG-1, 17, 18, 19, 20 | NOT VERIFIED (Windows) | Windows-only. Automated tests are in the suite run. |
| REG-2 | PASS | The startup log says "real hardware mode … real arms". No demo profile. |
| REG-3 | PASS | The leader reads 0 °C on every motor: no alarm and no stop. |
| REG-4 | PASS | Calibration records the range of all 6 joints, including wrist_roll. Save is enabled only when all are green. |
| REG-5 | PASS (emulator) | Teleop at 250 Hz measured 217 Hz, latency ~5 ms, and the follower is within 6 steps of the leader. The customer's "feels like LeLab" check is NOT VERIFIED. |
| REG-6, REG-8 | NOT VERIFIED on the UI | Pty ports are not listed by `list_ports`. Automated tests only. |
| REG-7 | PASS | Calibration of both arms plus Check took under 3 minutes, and teleop runs right after. |
| REG-9 | PASS | vi, 390: "Gắp đỏ" → `gap_do` and "抓取" → `program_1opb0ik`. The form opens with the cursor in the name field. |
| REG-10 | PASS | Space mid-run → `estopped` → reset → the rerun completes from the start (see item 7). |
| REG-11, REG-13, REG-23 | PASS | Leader at 1000 raw current and 0 °C shows "not measured" and raises no alerts. REG-13 can be closed after the customer's UAT-0. |
| REG-12 | PASS | Disconnected at 390 in vi: Calibrate, Cameras, Teleop, Record and Run model show "Bước này đang bị khoá · Hãy kết nối robot trước." with "Tới Robot" and no enabled controls. Train shows the pairing reason and its form. Upload (the Datasets list) is not locked, because it needs no robot. Also locked while e-stopped (item 9). |
| REG-14, 15, 16 | automated only | Covered in the suite run. |
| REG-21 | PASS (button, Esc, red STOP, countdown, reset, saving, reopened page), with defect QD-12 | See items 2a to 2f. |
| REG-22 | PASS for normal cameras; the freeze path is NOT VERIFIED on the UI | See item 3d. |

## Automated suite (run once, at the end, from the fresh clone)

* `pytest -q` (fresh clone at `bce592e`, `uv sync --locked`): **527 passed, 1 skipped, 2 deselected
  (e2e), 2 failed**, in 10 min 56 s. The failures:
  * `tests/test_field_028.py::test_rest_move_is_slow_cancellable_and_needs_the_heartbeat`: the
    arm was 7.9° from Home after the stop, where the test expects more than 20°.
  * `tests/test_field_028.py::test_far_leader_is_refused_then_aligned`: the teleop did not start
    within 20 s.

  Both depend on wall-clock timing. While they ran, the machine was loaded by QC's own parallel
  vitest runs (a QC process error) and by another workflow. On a quiet machine (load 0.6-1.0),
  `tests/test_field_028.py` was run on its own three times: **15 passed each time**. On the
  installed artifact, Return Home was slow every time (item 5b, and the `playing` phase lasts
  several seconds). We count this as test timing under load, not a product defect, so it is not a
  QD. The team should give these two tests the same load headroom the teleop-latency test got
  in `9e3c1b8`.
* `pnpm test` (vitest): **14 files, 191 tests passed**. `pnpm typecheck`, `pnpm lint` and
  `pnpm format:check` passed. The UI build's CSP check and locale-guard check passed.
* **Python fail-first (by QC):** the candidate's `tests/test_release_version.py`,
  `tests/test_programs_api.py` and `tests/test_owner.py` were run against the pre-fix commit
  `25f59b4`. 4 tests fail there:
  * QD-1: the CHANGELOG version, 0.2.8 against 0.2.9;
  * QD-10: `/state` answers 404, not 200;
  * QD-3: "66 C" without °;
  * `test_ab_program_with_keys_dry_run_then_real_run`.

  All pass on the candidate.
* The e2e tests (QD-6 and QD-11 layout checks in `tests/e2e/test_station_ui.py`) are deselected by
  default and were not run. Their behaviour was checked by hand on the installed artifact (QD-6,
  QD-11 above).

## Defects (QD), round 2

| QD | Severity | Area | Steps → expected → actual | Evidence |
|---|---|---|---|---|
| QD-12 | Medium (correct information) | Record | Start recording and end the session before any episode is saved: (a) red STOP / Space during episode 1, or (b) Stop during the countdown. → Expected: the end card says no episode was kept, and why (for example "The e-stop discarded the episode in progress. Nothing was saved."), with no Upload. → Actual: "0 episodes saved in dataset qr_redstop" with an enabled **Upload**. Station has already deleted the half-created dataset. Upload opens `/datasets/qr_redstop5?upload=1`, which shows "0 episodes · 0 frames · 30 fps · 2.6 KiB", Delete, "Not found." and the raw server detail "no dataset qr_redstop5", plus the pairing form. The browser console logs `404 GET /api/v1/datasets/<name>`, and the Record step keeps its ✓. The session summary has `saved 0, discarded 0`, so the e-stopped episode is not even counted as discarded. | evidence/09, 10 |
| QD-13 | Medium (release hygiene) | Docker install | The README "Your machine → What install.sh picks" table (en and vi) lists `ghcr.io/bigkatoan/hibiscus-station:0.2.1-cpu/-cuda/-jetson`. `deploy/install.sh` has `VERSION="0.2.1"` (and pulls its compose files from tag v0.2.1). `deploy/.env.example` has `STATION_TAG=0.2.1-cpu`. `docs/deploy.md` and the systemd unit comment install the v0.2.1 wheel. Images are published on every tag (docker workflow green for v0.2.2 … v0.2.8). → Expected: the Docker route installs 0.2.9. → Actual: a user following the README's Docker route gets 0.2.1, without any field fix since. | `grep -rn 0.2.1 README.md README.vi.md deploy/ docs/deploy.md` |
| QD-14 | Low (i18n) | Sessions | Open Sessions after a program run, Return Home and a trajectory. → Expected: words such as "Program", "Return Home", "Trajectory play". → Actual: the Kind column shows the raw keys `session.kind_program`, `session.kind_rest`, `session.kind_traj_play` and `session.kind_traj_record` in en and vi. The Outcome column shows the English "stopped" in vi (no `reasons.stopped` key). | evidence/11 |
| QD-15 | Low (plausibility) | Cameras | Cameras → Discovered devices while the profile's mock cameras are open. → Expected: a device name or "in use". → Actual: the row reads "front · **held** · **None** · used by front": a raw type "held" (also in vi) and a Python `None` as the path. Seen with mock cameras. Whether a real webcam shows the same is NOT VERIFIED. | evidence/12 |
| QD-16 | Medium (plausibility) | Programs | Run "relax test" on the robot (it completes in 3.3 s), then open the Programs tab some minutes later. → Expected: "3.3 s · 2 steps · go Home". → Actual: "58.7 s · …" and later "360.7 s · 2 steps · go Home". `GET /programs/relax_test/state` returns `status: completed` with a `t` that keeps growing (362.6 → 367.6 → 372.6 s, 5 s apart). The run panel shows the value from page load. | evidence/13 |
| QD-17 | Low (wording) | Robot / Record | (a) vi tooltip on the leader's "không đo": "Tay leader **vẫn đã kết nối** và hoạt động bình thường" is not natural Vietnamese ("vẫn đang kết nối" or "vẫn kết nối"); key `not_measured_title`. (b) en Record form: "About 15 MB per episode with **2 camera(s)**". The same class of shortcut as "1 episodes" (QD-8). | `vi.json` `not_measured_title`; Record page |

Not counted as defects (by design, noted):
* Closing the browser during Return Home or a program run e-stops with "Robot stopped: UI connection
  lost" (dead-man).
* An e-stop during an episode drops that episode instead of saving it. That is acceptable for an
  e-stop, but the screen must say so (QD-12).
* "Return Home" stays enabled while e-stopped after the user's own e-stop, as documented: it resets
  and moves the arm Home.
* At 390 px the Motor health A column is hidden, and the top-bar Home buttons are on the Robot page
  and in the Robot 3D panel.

## What only the customer can verify (UAT, Windows + real SO-101)
1. REG-21 / REG-22 on Windows with two USB webcams:
   * record 3 × 30 s;
   * press Stop (button and Esc) at ~10 s;
   * check "Đang lưu tập…" appears at once, the timer stops, the cameras stay live and the arm
     holds;
   * check the dataset holds ~10 s × 30 frames;
   * check no tile shows "Không có hình mới".
2. REG-23: the leader reads "Đã kết nối · 6/6 động cơ trả lời", with "không đo" and its tooltip.
3. CR-1 on the real arm: Stop holds without sagging, Về Home is slow, Thả lỏng asks first, and the
   card after a relax says torque is off.
4. Over-temperature handling (emulator only here) and the camera-freeze path (REG-22 3d).

## Escape review (round 2)
* **What round 1 missed:** QD-12, QD-13, QD-14, QD-15 and QD-16 were all present when round 1 ran.
  None of them comes from the round-1 fixes.
  * QD-12: round 1's "red STOP during recording" step clicked the wrong button (a case-insensitive
    "STOP" match hit the screen's Stop) and never ended a session with 0 episodes.
  * QD-13: the hygiene check grepped for the old patch version (0.2.8) only, not for every older
    version in the deploy files.
  * QD-14 and QD-16 need a page opened *after* other journeys: Sessions after a program, or
    Programs minutes after a run. Round 1 never opened Sessions and read run times only at once.
  * QD-15: the Cameras page was not swept for raw values.
* **Checks added to the QC lists:**
  * Click safety buttons by exact accessible name, and confirm with the state (`estopped`) that the
    intended button was hit.
  * Recovery: end a record session with 0 episodes (Stop in the countdown, e-stop in episode 1), and
    follow every button on the end card.
  * Hygiene: `grep -rnE '0\.2\.[0-9]'` across README*, deploy/ and docs/deploy.md. Every install
    route must name the release being shipped.
  * After the journeys: sweep every page in en and vi for raw keys (`\w+\.\w+_\w+`), `None`,
    `null`, `undefined`, `NaN` and `[object Object]`, and re-open Programs and Sessions to check that
    durations and labels are stable.
  * Recommended to the team: add `camera: freeze` to `/api/v1/mock/inject`, so the REG-22 freeze
    path can be checked on the UI.
* **Owner line:** round 1 passed the e-stop-during-recording check on the wrong button. Round 2
  clicks it by exact name and checks the `estopped` state.

## Environment notes
* Servers used 127.0.0.1:18550 (Station on the emulator rig) and 18551 (rig control). Both were
  stopped before the automated suite ran.
* The QC driver scripts and full-size screenshots stayed outside the repository. Only the downsized
  screenshots under `docs/qc/evidence/0.2.9-r2/` are committed. They contain no personal paths or
  tokens.
