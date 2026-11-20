# QC report: Hibiscus Station hotfix 0.2.9, round 5 (hotfix gate, re-run in full)

* **Verdict: FAIL** (zero-defect rule). The two round-4 defects (QD-22, QD-23) are fixed on the
  installed artifact, and QD-1 to QD-21 still pass. Round 5 found **4 new defects**, all about
  what the open page says around a stop, a cool-down or a disconnect:
  * **QD-24 (Medium):** during a thermal stop, the red banner says "Robot stopped, torque off" and
    "The arm is held in place" while the arm is still moving to Home with torque on. This lasts
    about 1.7 s on the emulator, and the arm turns more than 100° in that time.
  * **QD-25 (Low):** after a thermal stop, once the motor has cooled (40 °C, health `ok`) and before
    the reset, the page still says "Motor critical: elbow_flex 66 °C … Let it cool down". The lock
    text and the e-stop dock also still say 66 °C and "Motors too hot". Nothing tells the user that
    a reset is now possible.
  * **QD-26 (Low):** after Disconnect or a lost device, the open page keeps showing the last motor
    temperatures as if they were live (for example a warning-coloured "elbow_flex 58°C" chip). After
    a lost device it also freezes the session numbers ("FPS 227.5 / 30"). The Station itself
    reports no data, and a reload shows "Motor health –". This is the same class as QD-23.
  * **QD-27 (Low):** while the robot is disconnected, Teleop says "No camera configured." and the
    Record estimate says "with 0 cameras". The profile has 2 cameras.
  * QD-24 to QD-26 already existed in round 4, because no round checked these moments (see the
    escape review). QD-27 was never checked in the disconnected state.
  * None is an unsafe behaviour of the robot. Stop, the red e-stop, Space, relax, the dead-man
    stop, the thermal stop and a lost device all stop the robot correctly. QD-24 is wrong safety
    information on screen while the robot moves.
* **Artifact tested:** branch `hotfix/0.2.9`, commit `7962181a15529aa4f74a60179762df699474d085`
  (local worktree HEAD = `origin/hotfix/0.2.9`).
  * **CI:** GitHub Actions run `ci` 44107157358 (workflow_dispatch, attempt 1) for this exact
    commit is completed, and all 8 jobs succeeded: python, web, deploy, image, wheel, e2e, windows,
    macos. Checked with `gh api …/actions/runs?head_sha=…` and `…/runs/44107157358/jobs`.
  * Cloned fresh from GitHub. UI built with
    `web/scripts/node.sh pnpm install --frozen-lockfile && pnpm build`. The CSP check and the
    locale-guard check passed.
  * Wheel built with `uv build --wheel`: `hibiscus_station-0.2.9-py3-none-any.whl`, sha256
    `f12cf5bca5304ece8f3d9aa9c5cc0bf2d2f56281d957f7d9c1bd665ee407b52f` (190 UI files inside).
  * Installed with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`.
    `hibiscus-station --version` prints `hibiscus-station 0.2.9`. The startup log says
    "Hibiscus Station 0.2.9: real hardware mode … real arms".
* **Platform:** Linux x86-64, Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`).
  * We drove the UI with the mouse. The keyboard was used only to type in text fields, to choose
    from native `<select>` lists, and for the Space and Esc shortcuts.
  * Safety buttons were clicked by exact identity, and every press was confirmed by the resulting
    state (Station status and the emulator's torque and position registers).
  * The console was captured on every page: errors, warnings, and every HTTP response ≥ 400.
    Ignored: headless WebGL driver messages, and Chrome's "AudioContext was not allowed to start"
    autoplay warning from the Blockly editor.
* **Hardware stand-in:** the installed Station in real-hardware mode (no `--mock`) against two
  `tests/sts_emulator.py` pty chains with real wire timing (`realistic()`).
  * Follower: 12.1 V, 35-37 °C.
  * Leader: 5.3 V, with temperature register 0 and current register 1000 raw on every motor (the
    field leader).
  * Two `mock` cameras, 640x480 at 30 fps.
  * The arms were moved "by hand" with the emulator's hand function (still, gentle, sweep, mirror).
    The QC rig also has an "unplug" control that closes the follower's pty.
* **Date:** 2026-11-17. QC inspector: independent. Developer summaries and the CHANGELOG text were
  not used as evidence. Earlier QC reports were used only for their list of checks and defects.

## Customer waiver (2026-11-17)

* **Date:** 2026-11-17.
* **Customer's choice:** "Phát hành ngay, lỗi cũ vào M1" (release now, old defects go to M1). The
  option read: confirm on 0.2.8, waive by defect id, release 0.2.9, fix in M1.
* **Basis:** `QC-0.2.9-waiver-check.md` reproduced QD-24, QD-25, QD-26 and QD-27 on the published
  v0.2.8 wheel. They are pre-existing, not regressions of 0.2.9.
* **Waived for 0.2.9, by defect id:** QD-24 (Medium), QD-25 (Low), QD-26 (Low), QD-27 (Low).
  Every other hotfix-gate item passed on commit `7962181`. No other defect is waived.
* **Follow-up:** all four are fixed in M1 (1.0). They are listed under "Known issues" in the
  CHANGELOG 0.2.9 section and in the release notes.
* **Decision:** the Lead released 0.2.9 on this waiver.

## Round 4 defects: re-test on the installed artifact

| QD | Round 4 defect | Result | Evidence |
|---|---|---|---|
| QD-23 | Critical banner stays on the open page after cool-down and reset | **FIXED** | We kept one page open (en 1280 light, then vi 390 dark) through the whole path: teleop → elbow_flex at 66 °C → thermal stop (torque 0 on all 6 motors, `estopped`/`thermal`) → reset while hot → 409 "A motor is too hot" → cool to 40 °C → "I'm clear, reset" → 200. **The banner was gone at the first sample (1 s) after the accepted reset** and stayed gone over 10 s of samples, during Return Home, during 4 s of new teleop and after Stop, with health `ok`. A reload shows the same. The "about 0 s" countdown no longer appears. We also checked warning (55 °C) and hot (62 °C) alerts while idle: the hot banner "elbow_flex is hot (62 °C) …" came and went with the temperature, without a reset. **Disconnect/reconnect with an alert active:** with shoulder_lift at 62 °C, Disconnect removed the hot banner (the Station reports no alert). Reconnect brought it back, because the motor was still hot, and cooling removed it. A thermal e-stop, then Disconnect, then Connect while still hot gave `estopped`/`thermal` again with the critical banner. After cooling and reset, everything was clean. A lost device (follower pty closed during teleop, with a hot alert active) removed the motor banner. But the top-bar temperature stays: see QD-26. evidence/07 |
| QD-22 | vi "reset" / "dataset" wording | **FIXED** | In every e-stop state (red e-stop, Space, dead-man, thermal) the vi lock reads "Hãy đặt lại nút dừng khẩn cấp trước.", matching the button "Đã an toàn, đặt lại". We scanned all strings in `vi.json` against an English word list. The only hit is the Windows setting names quoted in `lost.check_suspend` (Control Panel paths), which is acceptable: they are the names the user must click. There are 0 "Hiệu chuẩn" and 41 "Hiệu chỉnh". The rendered-page scan of 17 pages at 390 dark and 1280 light found only loanwords (camera, model, token, policy, telemetry, Station) and the model's own task text. |

**Earlier defects, re-checked on this artifact.**

| QD | Result |
|---|---|
| QD-1 | PASS: 0.2.9 in the wheel, `--version`, the startup log, `pyproject.toml`, `__version__`, CHANGELOG. |
| QD-2 | PASS: "Set Home for this robot first. · relax arm / · go Home" with "Set Home now" before Check, and again after a reload. One click → "No problems found." |
| QD-3 | PASS: the motor and temperature are named in words ("Motor critical: elbow_flex 66 °C"); no `[object Object]`. |
| QD-4 | PASS: "Stopped. Torque is off: the arm is limp and does not hold its position." after a double Space. |
| QD-5 | PASS: "Moving to the start of episode 1…", then "Replaying episode 1 · 0.5 / 30 s". |
| QD-6 | PASS: table scrollWidth = clientWidth at 1280 (608), 1440 (768) and 390 (318), en and vi. |
| QD-7 | PASS: "Draft" with "Not saved yet: open Edit, then press Save take to play it." and Play disabled. Edit → Save take → Play → `traj_play` completed. |
| QD-8 | PASS: "1 episode", "3 episodes", "1 tập", "3 tập". |
| QD-9 | PASS: "Hiệu chỉnh tay follower" / "Hiệu chỉnh mới (so101_follower)" in the Sửa form; no "Hiệu chuẩn". |
| QD-10 | PASS: Programs tab loads with no 4xx; `/programs/relax_test/state` returns 200 `null` before any run. |
| QD-11 | PASS: vi 390 end card "Đã lưu 2 tập vào bộ dữ liệu qr_vi_390" on one 318 px line (24 px high). |
| QD-12 | PASS: see QD-18. |
| QD-13 | PASS: `install.sh` has `VERSION="0.2.9"`; `compose.yml` example `0.2.9-cpu`; no older version in the install routes. |
| QD-14 | PASS: 47 sessions show 8 kinds and 5 outcomes in en and vi, with no raw key. |
| QD-15 | PASS: "used by wrist / front" and "đang dùng bởi wrist / front", with no `None`. |
| QD-16 | PASS: a finished run keeps "8.3 s · 2 steps" over 10 s on screen and in the API. |
| QD-17 | PASS: the vi "không đo" tooltip is correct, and the estimate says "with 2 cameras" (when connected; see QD-27 for the disconnected state). |
| QD-18 | PASS: red e-stop and Space, in episode 1 and in the countdown: 0 responses ≥ 400 and 0 console errors, also after reset and reload. Each card says "No episode was saved." and gives the reason ("Episode 1 was stopped (e-stop pressed), so it was not kept." or "The session ended (e-stop pressed) before an episode was recorded."). Then it says "Nothing was written: the dataset … was not created." and offers **Record again**, with no Upload. Session summaries: `saved 0, dataset_kept false` (episode 1 also `discarded 1, dropped_in_progress true`). A red e-stop in episode 2 shows "1 episode saved … Episode 2 was stopped (e-stop pressed), so it was not kept." with Upload; 300 frames. |
| QD-19 | PASS: closing the browser during a replay, then opening Station in vi 390 dark, shows "Robot đã dừng: mất kết nối giao diện." with the Vietnamese explanation; the dock says "Đã dừng: mất kết nối giao diện". The same happens for a program run (en: "Robot stopped: UI connection lost."). evidence/08 |
| QD-20 | PASS: "1 step" / "2 steps" (en) and "1 bước" / "2 bước" (vi) in the run list. |
| QD-21 | PASS: 1 episode of 5 s with 2 cameras: "About 2.6 MB per episode with 2 cameras, about 2.6 MB in total." Default vi form: "Khoảng 15 MB mỗi tập với 2 camera, tổng khoảng 309 MB." |

**Fail-first check (by QC).** We copied the candidate's new tests onto the pre-fix tree `1574e81`
(round 4's artifact, unpacked with `git archive`, fresh `uv sync --locked` and `pnpm install`).

* **pytest** `tests/test_ui_mirror.py`. The import path was checked: it is the pre-fix tree.
  **5 of 5 tests fail before the fix**:
  * thermal stop → cool → reset;
  * disconnect drops every alert;
  * device lost → reconnect;
  * deleting the loaded model;
  * unpairing.
* **vitest** `qc029r4.screens.test.tsx` and `i18n.glossary.test.ts`: **6 of 8 fail before the
  fix**:
  * the QD-22 glossary check;
  * the hello replaces alerts;
  * the countdown never reads 0 s (en and vi);
  * thermal stop → cool → reset on one open page;
  * device lost removes the motor alerts.

  The 2 that pass are guard tests on the glossary itself.
* On the candidate, all of them pass (see "Automated suite").

## Hotfix gate: item → result

| # | Item | Result | Evidence |
|---|---|---|---|
| 0 | CI for the exact commit | PASS | Run 44107157358: 8/8 jobs `success`, head_sha `7962181…`. |
| 1 | Fresh install of the patch artifact | PASS (wheel) | See the header. Pulling the Docker image is NOT VERIFIED (it is published with the release tag); the CI `image` job built and smoke-tested it. |
| 2a | Field 1: Stop button during recording | PASS | Episode of 30 s, Stop at 10.07 s: phase `saving` at the first sample (0.27 s), the timer frozen at 10.07 s. Torque 1, Present unchanged over 2 s, 0 "No fresh frames". `idle` after 6.5 s. "1 episode saved in dataset qr_stop_click", 302 frames. |
| 2b | Field 1: Stop with Esc | PASS | Same behaviour, frozen at 10.0 s. `idle` after 6.0 s; `qr_stop_esc` has 300 frames. |
| 2c | The arm holds after Stop | PASS | Torque 1 on all 6 motors, Present unchanged over 2 s. Card: "Stopped. The arm holds its position." with Return Home and Relax. |
| 2d | Red e-stop and Space during recording, in episode 1 and in the countdown | PASS | See QD-18. Each press gave `estopped` within 0.42 s with torque held on all 6 motors. Reset → `idle`, torque 1. |
| 2e | Page reopened during saving (vi, 390, dark) | PASS | Pressed Dừng 5 s into episode 2 and closed the browser. The reopened page shows "Đang lưu tập 2…" with "Dừng (Esc)" enabled and FPS "29,9 / 30", then "Đã lưu 2 tập vào bộ dữ liệu qr_vi_390" on one 318 px line. No sideways scroll. |
| 2f | REG-21: Stop in the countdown and reset phases | PASS | Countdown: `idle` within 0.12 s, "You stopped before the first episode was recorded.", nothing written. Reset phase: `saving` within 0.12 s, episode 1 kept (180 frames = 6 s). |
| 3a | Field 2: cameras deliver through 3 × 30 s | PASS (mock cameras) | 324 UI samples, 0 "No fresh frames". 2700 frames; each mp4 decodes (ffprobe) to 2700 frames at 640x480. 29.7 fps measured. |
| 3b | Cameras live while saving | PASS | 0 "No fresh frames" during every save; FPS 29.9 / 30 on the reopened saving page. |
| 3c | Real Windows webcam | **NOT VERIFIED** | No Windows machine or USB webcam. |
| 3d | Frozen camera (REG-22 freeze path) | **NOT VERIFIED** on the UI | The mock camera cannot freeze. Covered by an automated test only. |
| 4 | Field 3: leader reads as connected | PASS | "Connected · 6/6 motors answer" / "Đã kết nối · 6/6 động cơ trả lời", "not measured" / "không đo" with the tooltip. The follower reads 35-37 °C and 12.1 V. |
| 5a | Set Home / Replace Home from the top bar | PASS | "Set Home now" on the blocked program set the first Home. Top bar: "Replace Home? The follower's current position becomes the new Home." → `rest_pose` in `robots.yaml` changed to the current pose. |
| 5b | Return Home (Robot page, Robot 3D panel, from limp) | PASS | From a sweep pose: `playing` → `idle`, end pose = Home. From the limp state after a double Space: torque comes back on and the arm reaches Home in 4.5 s. |
| 5c | Home prompt after calibration | PASS | "Set this robot's Home" card after both arms were calibrated. |
| 5d | Blocked program offers "Set Home now" | PASS | See QD-2. |
| 6 | Relax asks to support the arm | PASS | "Support the arm … Cancel / I am holding it, relax". Torque stays 1 until confirmed; Cancel keeps the hold. Double Space → torque 0, "Support the arm. Torque is off." |
| 7 | Golden path end to end | PASS | Connect (pty) → calibrate both arms (Set middle, ranges on all 6 joints including wrist_roll, Save) → Check 0.0° → teleop (follower within 7 steps, 226 Hz, ~5 ms) → red e-stop → reset → record 3 × 30 s → Stop / Esc → Return Home → program "relax test" built by mouse drag → "Set Home now" → dry run "Completed · dry run" (5.3 s) → run on the robot "Completed" (0.7 s from Home) → from away, Space mid-run → `estopped`, "1.5 end · E-stopped" → "I'm clear, reset" → the rerun completes from the start (8.3 s · 2 steps). |
| 8a | Neighbour: replay | PASS | "Moving to the start of episode 1…" → "Replaying episode 1 · 7.0 / 30 s", same for episodes 2 and 3. Stop → `idle`, torque 1, Present unchanged over 2 s. Closing the browser mid-replay → dead-man stop (QD-19). |
| 8b | Neighbour: run model (import .zip through the file chooser, random-weight ACT) | PASS | Joint state size and action size match; cameras wrist and front. Loaded on CPU in 3 s. "Episode 1 / 1 · model running · 5.0 / 30 s"; the arm moved; 0 "No fresh frames". Stop → `idle`, the arm holds. |
| 8c | Neighbour: trajectory record / draft / play | PASS | "Recording · 1.8 / 60 s · 53 samples" → Stop → "Draft", "2.4 s · 30 fps · peak 11°/s", Play disabled. Edit → Save take → Play → `traj_play` completed. |
| 9 | Over-temperature stop (elbow_flex 66 °C during teleop) | PASS for the stop and the reset; **FAIL** on what the page says (QD-24, QD-25) | The arm parks toward Home, then torque goes to 0 on all 6 motors: `estopped`, reason `thermal`. Reset while hot → 409 "Motors too hot: follower elbow_flex 66 °C. Let them cool down first." Reset after cooling → `idle`, and the banner clears at once (QD-23 fixed). But during the park the banner already says "Robot stopped, torque off" (QD-24). After cooling and before the reset, the page still says the motor is at 66 °C and too hot (QD-25). |
| 9b | Dead-man stop during replay and during a program run | PASS | Browser closed mid-replay and mid-run → `estopped`, reason `ui_lost` ("no heartbeat from the UI for 1.0 s"), torque held. The run log shows "1.8 end · E-stopped". Teleop has no dead-man, by design (spec: a human holds the leader). |
| 9c | Device lost (follower pty closed during teleop) | PASS for the stop; **FAIL** for the stale numbers (QD-26) | `error` / `device_lost` within 1.3 s. en: "Lost the USB connection to the Follower arm (/dev/pts/12)" with the checklist and Reconnect; vi: "Mất kết nối USB với Tay follower …". Pages are locked with "Go to Robot". Replugging is NOT VERIFIED (a closed pty cannot come back). |
| 9d | Disconnect / reconnect with alerts active | PASS for alerts; **FAIL** for the temperature display (QD-26) | See QD-23 above. |
| 10 | Plausibility of every number shown | **FAIL** (QD-24 to QD-27) | Telemetry, timers, frame counts, dataset sizes, run durations, estimates (when connected) and teleop at 219-228 / 250 Hz with ~5 ms latency are plausible. Not plausible: "torque off" while moving (QD-24); 66 °C and "too hot" next to a 40 °C chip (QD-25); stale temperatures and "FPS 227.5 / 30" for a disconnected or lost robot (QD-26); "0 cameras" (QD-27). The per-episode MB estimate against real camera content is NOT VERIFIED (mock cameras are noise: 13 MB for a 5 s episode against an estimate of 2.6 MB). |
| 11 | No English leftovers in vi; "Hiệu chỉnh" | PASS | See QD-22. |
| 12 | 1280 / 390, light / dark, all pages, en / vi | PASS (layout) | 17 pages × {en 390 light, en 1280 dark, vi 1280 dark, vi 390 light, en 1280 light, vi 390 dark}: no sideways scroll, no `None` / `null` / `undefined` / `NaN` / `[object Object]`, no raw i18n key, 0 console errors. The Programs tabs are clean in 4 combinations. |
| 13 | e2e suite | PASS | `HIBISCUS_E2E_REQUIRED=1 HIBISCUS_E2E_PORT=18610 uv run pytest tests/e2e -m e2e` on the fresh clone: **1 passed** in 57 s. |
| 14 | Regression list smoke | see below | |
| 15 | Full automated suite (once, at the end) | see "Automated suite" | |

## Regression list smoke (REGRESSION.md v1.1, unchanged since round 3)

| REG | Result | Evidence / reason |
|---|---|---|
| REG-1, 17, 18, 19, 20 | NOT VERIFIED (Windows) | Windows only. The automated tests run in the suite and in the CI `windows` job. |
| REG-2 | PASS | The startup log says "real hardware mode … real arms"; no demo profile. |
| REG-3 | PASS | The leader reads 0 °C on every motor: no alarm and no stop. The thresholds stay at 50/60/65 °C (warn at 55, hot at 62 and the stop at 66 behaved as expected). |
| REG-4 | PASS | Ranges were recorded for all 6 joints, including wrist_roll. Save is offered only when all are green. |
| REG-5 | PASS (emulator) | 250 Hz setting: 219.4 / 250, latency ~5 ms. "Feels like LeLab" is NOT VERIFIED. |
| REG-6, REG-8 | NOT VERIFIED on the UI | `list_ports` does not list pty ports. Automated tests only. |
| REG-7 | PASS | Both arms calibrated and checked within the first minutes; teleop runs right after. |
| REG-9 | PASS | vi at 390: "Gắp đỏ" → `gap_do`, "抓取" → `program_1opb0ik`, with the cursor in the name field. |
| REG-10 | PASS | Space mid-run → reset → the rerun completes from the start (item 7). |
| REG-11, 13, 23 | PASS | Leader at 1000 raw / 0 °C: "not measured", no alerts. |
| REG-12 | PASS | Disconnected, vi at 390: Calibrate, Cameras, Teleop, Record and Run model show "Bước này đang bị khoá · Hãy kết nối robot trước." with "Tới Robot" and no enabled controls. Train shows the pairing lock. Upload (datasets) stays open by design. Steps are also locked while e-stopped. |
| REG-14, 15, 16 | automated only | Run in the suite. |
| REG-21 | PASS (button, Esc, red e-stop, Space, countdown, reset, reopened page) | Items 2a-2f. |
| REG-22 | PASS for normal cameras; freeze path NOT VERIFIED on the UI | Item 3d. |

## Automated suite (run once, at the end, from the fresh clone)

* `ruff check`: all checks passed. `ruff format --check`: 131 files already formatted.
  `mypy --strict hibiscus_station`: no issues (83 files).
* `pnpm lint`, `pnpm format:check`, `pnpm typecheck`: pass. `pnpm test` (vitest): **21 files, 232
  tests passed**.
* `pytest -q` (fresh clone at `7962181`, `uv sync --locked`, run alone; machine load 0.8-3.5):
  **540 passed, 1 skipped (Windows lock semantics), 2 deselected (e2e), 0 failed** in 10 min 56 s.
* e2e: see item 13 (1 passed).
* Fail-first: see "Round 4 defects".

## Defects (QD), round 5

| QD | Severity | Area | Steps → expected → actual | Evidence |
|---|---|---|---|---|
| QD-24 | Medium (wrong safety information while the robot moves) | Thermal stop | **Steps:** teleop with the follower away from Home (after a sweep). Raise follower elbow_flex to 66 °C. Watch the page while the Station parks the arm. **Expected:** while the arm is still moving to Home with torque on, the banner says that: a motor is too hot and the robot is moving to Home before the torque goes off. "Stopped, torque off" appears only when it is true. **Actual:** for the whole park (1.7 s here: shoulder_pan 1386 → 2710 raw, about 116°; on a real arm far from Home it can take longer) the full-width red banner reads "Motor critical: elbow_flex 66 °C. **Robot stopped, torque off.** Let it cool down." and, below it, "**The arm is held in place.**" At the same time the top bar says "Teleop", the teleop timer is running, Stop is enabled, the torque is 1 and the arm moves. vi: "Robot đã dừng, đã tắt mô-men … Tay robot đang được giữ nguyên vị trí." Only after `estopped` (torque 0) does the second line change to "Support the arm. Torque is off." **Cause (read in the code):** the telemetry guard raises a critical temperature alert as soon as the motor is critical. `Banners.tsx` shows `banner.critical` ("Robot stopped, torque off") for any critical alert. `HardwareOwner._critical` (`hw/owner.py` around line 600) only then holds, parks (`_park`) and turns the torque off. | evidence/01 |
| QD-25 | Low (plausibility, recovery guidance) | Thermal stop recovery | **Steps:** thermal stop as above (optionally press "I'm clear, reset" while hot → 409). Cool the motor to 40 °C and keep the same page open for 20 s without resetting. **Expected:** the page shows that the motor has cooled and that the user can now reset, or at least it stops saying the motor is hot. **Actual:** for the whole 20 s (health `ok`, top-bar chip "elbow_flex 40°C"), the banner still says "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. **Let it cool down.**" The lock box and four sidebar steps say "Follower elbow_flex: 66 °C." If a reset was tried while hot, the e-stop dock keeps "**Motors too hot**: follower elbow_flex 66 °C. Let them cool down first." The screen shows two temperatures for one motor, and nothing tells the user to press reset. The countdown is gone, which is correct. vi says the same ("Hãy để động cơ nguội", "Tay follower elbow_flex: 66 °C."). | evidence/02 |
| QD-26 | Low (stale data on an open page; QD-23 class) | Disconnect, device lost | **Steps:** with a motor warm (58 °C) or hot (62 or 66 °C), press Disconnect, or lose the follower USB during teleop. Keep the page open. **Expected:** the same as a fresh page: "Motor health –" and no per-motor temperatures, because the Station no longer reads the motors. **Actual:** the open page keeps the last values as if live. The top-bar chip "elbow_flex 58°C" stays in warning colour (or "66°C" in red after a thermal stop). Robot 3D lists every motor's last temperature under "Live arm". After the real motor cooled to 36 °C the page still said 58 °C. After a lost device, the Teleop stats also freeze at "FPS **227.5 / 30**", "Overruns 193". `GET /status` says health `ok`, hottest `null`, alerts `[]`. A reload shows "Motor health –". Seen in en and vi (vi top bar "Chưa kết nối · 62°C"). | evidence/03, 04 |
| QD-27 | Low (plausibility) | Teleop, Record while disconnected | **Steps:** the active profile has 2 cameras (wrist, front). Disconnect the robot and open Teleop and Record. **Expected:** the pages say that the robot (and its cameras) must be connected first, as the Cameras page does ("Connect a robot first."), or they count the configured cameras. **Actual:** Teleop says "**No camera configured.**" / "Chưa cấu hình camera nào." Record says "About 450 kB per episode with **0 cameras**, about 9 MB in total." / "… với 0 camera, tổng khoảng 9 MB." Connected, the same form says "with 2 cameras, about 309 MB". | evidence/05, 06 |

Observations (not counted as defects):
* Run model: "Episode 1 / 1 · model running · **5.0** / 30 s" was shown next to the timer
  "**00:04** / 00:30" in the same capture. One rounds and the other truncates, so they can differ by
  up to 1 s. Replay shows the same pair (for example "7.0 / 30 s" with "00:07").
* "I'm clear, reset" while a motor is still hot is enabled, and its 409 reply logs one browser
  console error "Failed to load resource … 409". The UI explains the refusal, so the 409 is a correct
  HTTP answer to a user action.
* With "250 (fastest)" selected, the idle Teleop stats read "FPS – / 30".
* While disconnected, the Calibrate step loses its check mark (the Station reports
  `calibrated: false` while it cannot read the arm). It comes back on connect.
* A program's "relax arm" block took 8.0 s from a far pose (about 126° on shoulder_pan). It is
  slow by design (at most 30°/s).
* An emulated leader at 66 °C during teleop shows the hot banner but never stops the robot, by
  design. When the register drops back to 0 (meaning "not measured"), the last value is kept. A real
  leader cannot report 66 °C and then 0, so we did not count it.
* From earlier rounds, unchanged: Sessions rows are not links; the sidebar never marks Teleop
  done; `.github/ISSUE_TEMPLATE/bug_report.yml` has "0.2.1" as an example; the electrical
  (overcurrent) stop could not be triggered on this rig; at 390 px the e-stop dock covers part of
  a locked form.

## What only the customer can verify (UAT, Windows + real SO-101)
1. REG-21 / REG-22 on Windows with two USB webcams. Record 3 × 30 s and press Stop (button and Esc)
   at ~10 s. Expected: "Đang lưu tập…" at once, the timer stops, the cameras stay live, the arm
   holds, ~10 s × 30 frames are saved, and "Không có hình mới" never appears.
2. Red e-stop (and Space) in episode 1 and in the countdown: the card says nothing was saved and
   offers no Upload.
3. REG-23: "Đã kết nối · 6/6 động cơ trả lời", "không đo" and its tooltip.
4. CR-1 on the real arm: Stop holds without sagging, Về Home is slow, Thả lỏng asks first.
5. These were checked only on the emulator or not at all: over-temperature handling and the park
   time on a real arm, the electrical stop, the camera-freeze path, unplugging and replugging the
   real USB cable, and the episode size estimate with real cameras.

## Escape review (round 5)
* **What rounds 1-4 missed:** QD-24, QD-25 and QD-26 were present in round 4's artifact:
  * the banner text and the park order have not changed in this round;
  * the stale chip comes from the page's own store, which never clears the temperatures.
  QD-27 likely too.
  * QD-24: every thermal check read the banner only after `estopped`. Nobody sampled the screen
    *during* the park, with the arm away from Home.
  * QD-25: round 4 checked the banner after the reset. Nobody watched the cooled, not-yet-reset
    state for long enough to compare the banner with the top bar.
  * QD-26: the QD-23 sweep checked the alerts after Disconnect, not every other live value
    (temperature chip, Robot 3D temperatures, session stats).
  * QD-27: the disconnected-state sweep (REG-12) checked only the locks and buttons, not the
    sentences under them.
* **Checks added to the QC lists:**
  * For every automatic stop (thermal, electrical, dead-man, device lost), sample the screen every
    200 ms from the trigger until the final state, with the arm away from Home. Every sentence must
    match the measured torque and motion at that moment.
  * Between "condition gone" and "reset", wait at least 15 s on the same page. Every number for the
    same quantity must agree.
  * After Disconnect and after a lost device, compare the open page with a freshly loaded page,
    value by value (top bar, Robot 3D, stats, cameras). Any difference is a defect.
  * In the disconnected state, read every sentence on the locked pages, not only the buttons.
* **Owner line:** round 5 finds no unsafe robot behaviour. One Medium wrong-information banner
  during the thermal park (QD-24) and three Low wrong or stale on-screen values (QD-25 to QD-27)
  remain.

## Environment notes
* Servers used 127.0.0.1:18604 (Station on the emulator rig), 18605 (rig control) and 18610 (e2e
  Station). The rig was restarted once after the device-lost test (new ptys, same home and
  calibration). All servers were stopped before the automated suite ran.
* QC driver scripts and full-size screenshots stayed outside the repository. Only downsized
  screenshots under `docs/qc/evidence/0.2.9-r5/` are committed; they contain no personal paths or
  tokens.
