# QC report: Hibiscus Station hotfix 0.2.9, round 4 (hotfix gate, re-run in full)

* **Verdict: FAIL** (zero-defect rule). The four round-3 defects (QD-18 to QD-21) are fixed on the
  installed artifact, and QD-1 to QD-17 still pass. Round 4 found **2 new defects**:
  * **QD-23 (Medium):** after a thermal stop, the red "Motor critical … Robot stopped, torque off"
    banner stays on the open page after the motor has cooled and the robot is reset. It is still
    there while the arm moves again in teleop, and it cannot be dismissed.
  * **QD-22 (Low):** a vi locked-step hint uses the English word "reset".
  * Both defects already existed in rounds 1 to 3 (see the escape review).
  * None is an unsafe behaviour: Stop, the red e-stop, Space, relax, the dead-man stop, the thermal
    stop and device loss all stop the robot correctly. QD-23 is wrong safety information on screen.
* **Artifact tested:** branch `hotfix/0.2.9`, commit `1574e8132a1c7dbcb2567ed83b9686e40f4b56f4`
  (local worktree HEAD = `origin/hotfix/0.2.9`).
  * **CI:** GitHub Actions run `ci` 44086653715 for this exact commit is completed, and all 8 jobs
    succeeded: python, web, wheel, e2e, windows, macos, image, deploy. Checked with `gh api`.
  * Cloned fresh. UI built with `web/scripts/node.sh pnpm install --frozen-lockfile && pnpm build`.
    The CSP check and the locale-guard check passed.
  * Wheel built with `uv build --wheel`: `hibiscus_station-0.2.9-py3-none-any.whl`, sha256
    `0fbb39225965ffe4486d81583b5e3330a74da26fc7e0c8f9babb34f8fb1ac934` (190 UI files inside).
  * Installed with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`.
    `hibiscus-station --version` prints `hibiscus-station 0.2.9`. The startup log says
    "Hibiscus Station 0.2.9: real hardware mode … real arms".
* **Platform:** Linux x86-64, Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`).
  * We drove the UI with the mouse. The keyboard was used only to type in text fields, to choose
    from native `<select>` lists, and for the Space and Esc shortcuts.
  * Safety buttons were clicked by exact identity, and every press was confirmed by the resulting
    state.
  * The console was captured on every page: errors, warnings, and every HTTP response ≥ 400.
    Ignored: headless WebGL driver messages, and Chrome's "AudioContext was not allowed to start"
    autoplay warning from the Blockly editor (see Observations).
* **Hardware stand-in:** the installed Station in real-hardware mode (no `--mock`) against two
  `tests/sts_emulator.py` pty chains with real wire timing (`realistic()`).
  * Follower: 12.1 V, 35-37 °C.
  * Leader: 5.3 V, with temperature register 0 and current register 1000 raw on every motor (the
    field leader).
  * Two `mock` cameras, 640x480 at 30 fps.
  * Moving the arms "by hand" was done with the emulator's hand function (still, gentle, sweep,
    mirror). The QC rig added an "unplug" control that closes the follower's pty.
* **Date:** 2026-11-17. QC inspector: independent. Developer summaries and the CHANGELOG text were
  not used as evidence. Earlier QC reports were used only for their list of checks and defects.

## Round 3 defects: re-test on the installed artifact

| QD | Round 3 defect | Result | Evidence |
|---|---|---|---|
| QD-18 | Console 404 for the removed dataset when a session kept no episode | **FIXED** | We captured every HTTP response ≥ 400 and every console error across five runs: red e-stop in episode 1, Space in episode 1, red e-stop in the countdown, Space in the countdown, and Stop in the countdown. Result: **0 responses ≥ 400 and 0 console errors** in all five runs, including after reset and after reload. Each card says "No episode was saved.", gives the reason, then "Nothing was written: the dataset … was not created." and offers **Record again**. There is no Upload. The session summaries say `saved 0, dataset_kept false` (episode 1 also says `discarded 1, dropped_in_progress true`). A red e-stop in episode 2 gives "1 episode saved … Episode 2 was stopped (e-stop pressed), so it was not kept." with Upload; the dataset holds 1 episode / 300 frames. evidence/05 |
| QD-19 | English server detail under the vi stop banner | **FIXED** | We closed the browser during a replay and during a program run, then opened Station in vi. Banner: "Robot đã dừng: mất kết nối giao diện." + "Trang không gửi tín hiệu nào trong 1 giây (đã đóng, máy ngủ hoặc mất mạng), nên robot đã dừng để an toàn." The locked step and the sidebar use the same Vietnamese text. Same result for the thermal stop and device loss. For device loss, the server line is kept behind a closed "Chi tiết kỹ thuật" (Technical details) disclosure. evidence/03, 06 |
| QD-20 | "1 steps" | **FIXED** | We e-stopped a program run during its first block. en: "1.5 s · 1 step · relax arm"; the run list shows "1 step" and "2 steps". vi: "1,5 s · 1 bước · thả lỏng tay". evidence/04 |
| QD-21 | "0.00 GiB in total" | **FIXED** | Record form with 1 episode of 5 s and 2 cameras: "About 2.6 MB per episode with 2 cameras, about 2.6 MB in total." Default form in vi: "Khoảng 15 MB mỗi tập với 2 camera, tổng khoảng 309 MB." |

**Earlier defects, re-checked on this artifact.**

| QD | Result |
|---|---|
| QD-1 | PASS: 0.2.9 in the wheel, `--version` and the startup log. |
| QD-2 | PASS: "Set Home now" appears before Check, and again after a reload. |
| QD-3 | PASS: the motor and temperature are named in words; no `[object Object]`. |
| QD-4 | PASS: "Torque is off: the arm is limp" after a double Space and after a thermal stop. |
| QD-5 | PASS: "Moving to the start of episode 1…", then "Replaying episode 1 · 6.8 / 30 s". |
| QD-6 | PASS: table scrollWidth = clientWidth at 1280 (608), 1440 (768) and 390 (318). |
| QD-7 | PASS: the draft hint is shown, and Edit → Save take → Play works. |
| QD-8 | PASS: "1 episode", "2 episodes", "1 tập". |
| QD-9 | PASS: "Hiệu chỉnh" in the Sửa form; `vi.json` has 0 "Hiệu chuẩn" and 39 "Hiệu chỉnh". |
| QD-10 | PASS: Programs tab loads with no 4xx; `/programs/<id>/state` returns 200 `null` before any run. |
| QD-11 | PASS: vi 390 end card on one 318 px line. |
| QD-12 | PASS: see QD-18. |
| QD-13 | PASS: `git grep` finds no older version in any install route. `install.sh` has `VERSION="0.2.9"` and `.env.example` has `STATION_TAG=0.2.9-cpu`. |
| QD-14 | PASS: 51 sessions show 8 kinds and 5 outcomes in en and vi, with no raw key. |
| QD-15 | PASS: "used by wrist / front" and "đang dùng bởi …", with no `None`. |
| QD-16 | PASS: a finished run keeps "2.0 s" over 10 s on screen and in the API. |
| QD-17 | PASS: the vi tooltip text is correct, and the estimate says "with 2 cameras". |

**Fail-first check (by QC).** We copied the candidate's new and changed tests onto the pre-fix
tree `77bc0cc` (round 3's artifact).

* **vitest.** Files run: `qc029r3.screens.test.tsx`, `rawtext.test.ts`, `station.unit.test.ts`,
  `units.test.ts`, `lib/format.test.ts`, `lib/i18n.test.ts`.
  * Before the fix: **14 tests fail**, and `units.test.ts` fails to import.
    * QD-18: 2 tests.
    * QD-19: 4 tests, plus the raw-text sweep.
    * QD-20: 3 tests.
    * QD-21: 4 tests.
  * On the candidate, all of them pass.
* **pytest.** `test_cli_serve.py::test_mock_in_the_docker_layout_starts_and_is_healthy` fails
  before the fix and passes on the candidate. The import path was checked: the pre-fix run imported
  `hibiscus_station` from the pre-fix tree.

## Hotfix gate: item → result

| # | Item | Result | Evidence |
|---|---|---|---|
| 0 | CI for the exact commit | PASS | Run 44086653715: 8/8 jobs `success`. |
| 1 | Fresh install of the patch artifact | PASS (wheel) | See the header. Pulling the Docker image is NOT VERIFIED (it is published with the release tag). The new `--mock` home rule was checked on the installed CLI: with `HIBISCUS_STATION_HOME` set to a folder whose parent is read-only, the demo lives in `<home>/demo` and `health` says "healthy … 0.2.9". Without it, the demo lives in `~/.hibiscus/station-demo` (temporary HOME) and `health` also finds it. |
| 2a | Field 1: Stop button during recording | PASS | Episode of 30 s, Stop at 10.03 s: phase `saving` within 0.01 s and the timer frozen at 10.03 s. Torque 1, Present unchanged over 2 s, 0 "No fresh frames". `idle` after 6.3 s. "1 episode saved in dataset qr_stop_click", 301 frames. |
| 2b | Field 1: Stop with Esc | PASS | Same behaviour. `idle` after 6.0 s; `qr_stop_esc` has 301 frames. |
| 2c | The arm holds after Stop | PASS | Torque 1 on all 6 motors and Present unchanged over 2 s. Card: "Stopped. The arm holds its position." with Return Home and Relax. |
| 2d | Red e-stop and Space during recording, in episode 1 and in the countdown | PASS | See QD-18. Each press gave `estopped` within 0.42 s with torque held on all 6 motors. Reset → `idle`, torque 1. |
| 2e | Page reopened during saving (vi, 390, dark) | PASS | Pressed Dừng 5.6 s into episode 2 and closed the browser. The reopened page shows "Đang lưu tập 2…" with "Dừng (Esc)" enabled, then "Đã lưu 2 tập vào bộ dữ liệu qr_vi_390" on one 318 px line. No sideways scroll. 527 frames (12 s + 5.57 s at 30 fps). |
| 2f | REG-21: Stop in the countdown and reset phases | PASS | Countdown: `idle` within 0.01 s, "You stopped before the first episode was recorded.", nothing written. Reset phase: `saving` within 0.02 s, episode 1 kept (180 frames = 6 s). |
| 3a | Field 2: cameras deliver through 3 × 30 s | PASS (mock cameras) | 320 UI samples with 0 "No fresh frames". Session summary: `stale_ticks` 0, 29.8 fps measured. 2700 frames; each mp4 decodes (ffprobe) to 2700 frames at 640x480. |
| 3b | Cameras live while saving | PASS | 0 "No fresh frames" during every save. FPS 29.9 / 30 on the reopened saving page. |
| 3c | Real Windows webcam | **NOT VERIFIED** | No Windows machine or USB webcam. |
| 3d | Frozen camera (REG-22 freeze path) | **NOT VERIFIED** on the UI | The mock has no camera freeze. Automated test only. |
| 4 | Field 3: leader reads as connected | PASS | "Connected · 6/6 motors answer" / "Đã kết nối · 6/6 động cơ trả lời", and "not measured" / "không đo" with the tooltip. The follower reads 35-37 °C and 12.1 V, which is plausible. |
| 5a | Set Home / Replace Home from the top bar | PASS | First Home via "Set Home now" on a blocked program. Top bar: "Replace Home? The follower's current position becomes the new Home." → `rest_pose` in `robots.yaml` changed to the current pose. |
| 5b | Return Home (Robot page, Robot 3D panel, e-stop dock) | PASS | After a teleop sweep: `playing` → `idle`, end pose within 1 step of Home. From the limp state (after a thermal stop or a double Space) the torque comes back on and the arm arrives at Home. |
| 5c | Home prompt after calibration | PASS | "Set this robot's Home" card after both arms were calibrated. |
| 5d | Blocked program offers "Set Home now" | PASS | In a fresh browser and after a reload, before any Check: "Set Home for this robot first. · relax arm / · go Home". One click → "No problems found." |
| 6 | Relax asks to support the arm | PASS | Dialog "Support the arm … Cancel / I am holding it, relax". Torque stays 1 until confirmed, and Cancel keeps the hold. Double Space → torque 0, "Support the arm. Torque is off."; after reset, the limp-state card. |
| 7 | Golden path end to end | PASS | Connect (pty) → calibrate both arms (Set middle, ranges on all 6 joints incl. wrist_roll, Save) → Check 0.0 → teleop (follower within 7 steps) → red e-stop → reset → record 3 × 30 s → Stop / Esc → Return Home → program "relax test" by mouse drag → "Set Home now" → dry run "Completed · dry run" → run on robot "Completed" (0.7 s from Home, 2.9 s from away) → Space mid-run → `estopped`, "1.5 end · E-stopped" → "I'm clear, reset" → rerun completes from the start. |
| 8a | Neighbour: replay | PASS | "Moving to the start of episode 1…" → "Replaying episode 1 · 6.8 / 30 s"; episode 2 likewise. Stop → `idle`, torque 1, Present unchanged over 2 s. Closing the browser mid-replay triggers the dead-man stop (see QD-19). |
| 8b | Neighbour: run model (import .zip through the file chooser, random-weight ACT) | PASS | Compatibility: joint state and action sizes match; cameras wrist and front. Loaded on CPU in 3 s. "Episode 1 / 1 · model running · 5.0 / 30 s"; the arm moved; 0 "No fresh frames". Stop → `idle`, the arm holds. |
| 8c | Neighbour: trajectory record / draft / play | PASS | "Recording · 1.9 / 60 s · 56 samples". Stop → take "Draft" with "Not saved yet: open Edit, then press Save take to play it." and Play disabled. Edit → Save take → Play → `traj_play` completed. |
| 9 | Over-temperature stop (elbow_flex 66 °C during teleop) | PASS for the stop; **FAIL** after recovery (QD-23) | The arm parked toward Home, then torque 0 on all 6 motors: `estopped`, reason `thermal`. Banner: "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down." Reset while hot → 409 with "Motors too hot: follower elbow_flex 66 °C …" (vi "Động cơ quá nóng: …"). After cooling to 40 °C, reset works. But the critical banner stays on the open page (QD-23). |
| 9b | Dead-man stop during replay and during a program run | PASS | Browser closed mid-run → `estopped` with reason "UI connection lost" within 1 s. Program run log: "2.0 s · 1 step · relax arm". |
| 9c | Device lost (follower pty closed during teleop) | PASS | `error` / `bus_lost` within 1.3 s. en: "Robot disconnected: motor bus lost. Check the USB cable and the arm's power supply, then connect again." vi: "Robot đã ngắt kết nối: mất kết nối bus động cơ. …". Pages are locked with "Go to Robot". Replugging is NOT VERIFIED (a closed pty cannot come back). |
| 10 | Plausibility of every number shown | **FAIL** (QD-23) | Mostly plausible: telemetry, timers, frame counts, dataset sizes, the stable run durations (QD-16), the estimate (QD-21), and teleop at 218.7 / 250 Hz with ~5 ms latency. After recovery from a thermal stop, the banner says "elbow_flex 66 °C" and "Robot stopped, torque off" while the arm is at 40 °C and moving. The vi banner adds "Khoảng 0 giây nữa đủ nguội để đặt lại" (about 0 s until cool enough to reset). The per-episode MB estimate against real camera content is NOT VERIFIED (mock cameras are noise: 13 MB for a 5 s episode). |
| 11 | No English leftovers in vi; "Hiệu chỉnh" | **FAIL** (QD-22) | We checked 17 pages at 390 dark and 1280 light, plus the stop states (user e-stop, dead-man, thermal, device lost). Only loanwords appear (camera, model, token, policy, telemetry, Station), plus the model's own task text. `vi.json` has no "Hiệu chuẩn". But every locked step in an e-stop state reads "Hãy **reset** nút dừng khẩn cấp trước." (QD-22). |
| 12 | 1280 / 390, light / dark | PASS | No sideways scroll on any page in en/vi × 390/1280 × light/dark (6 combinations × 17 pages). No `None`, `null`, `undefined`, `NaN`, `[object Object]` or raw i18n key. Programs tabs are clean in 4 combinations. |
| 13 | e2e suite | PASS | `HIBISCUS_E2E_REQUIRED=1 HIBISCUS_E2E_PORT=18610 uv run pytest tests/e2e -m e2e` on the fresh clone: **1 passed** in 56 s. |
| 14 | Regression list smoke | see below | |
| 15 | Full automated suite (once, at the end) | see "Automated suite" | |

## Regression list smoke (REGRESSION.md v1.1, unchanged since round 3)

| REG | Result | Evidence / reason |
|---|---|---|
| REG-1, 17, 18, 19, 20 | NOT VERIFIED (Windows) | Windows only. The automated tests run in the suite. |
| REG-2 | PASS | The startup log says "real hardware mode … real arms"; no demo profile. |
| REG-3 | PASS | The leader reads 0 °C on every motor: no alarm and no stop. The thresholds stay at 50/60/65 °C. |
| REG-4 | PASS | Ranges were recorded for all 6 joints, including wrist_roll. Save is offered only when all are green. |
| REG-5 | PASS (emulator) | At the 250 Hz setting: 218.7 / 250, latency ~5 ms. "Feels like LeLab" is NOT VERIFIED. |
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

* `ruff check` and `ruff format --check`: clean (130 files). `mypy --strict hibiscus_station`: no
  issues (83 files).
* `pnpm lint`, `pnpm format:check`, `pnpm typecheck`: pass. `pnpm test` (vitest): **19 files, 224
  tests passed**.
* `pytest -q` (fresh clone at `1574e81`, `uv sync --locked`, run alone; machine load 0.9-3.9):
  **535 passed, 1 skipped (Windows lock semantics), 2 deselected (e2e), 0 failed** in 10 min 39 s.
  The round-3 load flake in `tests/test_field_028.py` did not recur.
* e2e: see item 13 (1 passed).
* Fail-first: see "Round 3 defects".

## Defects (QD), round 4

| QD | Severity | Area | Steps → expected → actual | Evidence |
|---|---|---|---|---|
| QD-23 | Medium (correct information, safety banner) | Thermal stop recovery | **Steps:** teleop; follower elbow_flex reaches 66 °C → thermal stop. Let it cool to 40 °C, press "I'm clear, reset", then Return Home and start teleop again, all on the same open page. **Expected:** the critical banner goes away once the reset is accepted. **Actual:** the full-width red banner "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down. The arm is held in place." stays. It was still there after 15 s, and it is still there while teleop runs with health `ok` and the top bar showing elbow_flex 40 °C. vi: "Động cơ nguy hiểm: elbow_flex 66 °C. Robot đã dừng, đã tắt mô-men … Khoảng 0 giây nữa đủ nguội để đặt lại." The banner has no dismiss button. Only a reload clears it. **Cause (read in the code):** the thermal stop raises alert `temperature:motor.critical.stopped` (`hw/owner.py` around line 609). `_cmd_estop_reset` (line 1703) removes it from `self.alerts` with `pop` but emits no `active: false` alert event, so the open page keeps it (`ws/store.ts` drops an alert only on such an event; `Banners.tsx` `criticalInfo` shows any critical alert). The same silent removal is in `_cmd_disconnect` (`self.alerts.clear()`). | evidence/01, 02 |
| QD-22 | Low (i18n, vi) | Locked steps | **Steps:** any e-stop state in vi (red e-stop, Space, dead-man, thermal). Open a locked page (Record, Teleop, Run model, Programs, Home) and look at the sidebar. **Expected:** Vietnamese only, using the word the reset button uses. **Actual:** "Hãy **reset** nút dừng khẩn cấp trước." (`vi.json` `lock.estopped`), right above the button "Đã an toàn, đặt lại". Every other vi string says "đặt lại" (`errors.estopped`: "… Hãy đặt lại trước.", `programs.run.robot_estopped`: "… cần đặt lại trước khi chạy chương trình."). Same class, found in the source but not seen on screen: `errors.dataset_exists` ("Đã có dataset với tên này.") and `errors.dataset_incompatible` ("Dataset này không khớp …") say "dataset" where the UI says "bộ dữ liệu". The record form's own check shows the correct "Đã có bộ dữ liệu tên này. Hãy chọn ghi thêm." | evidence/03 |

Observations (not counted as defects):
* Chrome logs "The AudioContext was not allowed to start" warnings when the Programs page (Blockly)
  loads without a user gesture, for example on a reload. This is a library message.
* Opening `/datasets/<name>` for a dataset that does not exist logs one 404 in the console, and the
  page explains that the dataset is gone. No link in the app leads there (Sessions rows are not
  links). The 404 is correct HTTP for a typed or bookmarked URL.
* The electrical (overcurrent) stop could not be triggered through the emulator's status register
  on this rig: NOT VERIFIED on the UI. It shares the banner and reset code with the thermal stop,
  so QD-23 probably applies to it too.
* The run-model loop measured 19.1 fps of 30 on the cameras while a random-weight ACT ran on the CPU
  of this shared machine (0 stale ticks). This depends on the machine; it is not a defect of the
  artifact.
* At 390 px the floating e-stop dock covers part of the record form while it is locked (by design:
  the safety buttons stay on screen).
* From round 3, unchanged: Sessions rows are not clickable; the sidebar never marks Teleop done;
  `.github/ISSUE_TEMPLATE/bug_report.yml` has "0.2.1" as an example.

## What only the customer can verify (UAT, Windows + real SO-101)
1. REG-21 / REG-22 on Windows with two USB webcams. Record 3 × 30 s and press Stop (button and Esc)
   at ~10 s. Expected: "Đang lưu tập…" at once, the timer stops, the cameras stay live, the arm
   holds, ~10 s × 30 frames are saved, and "Không có hình mới" never appears.
2. Red e-stop (and Space) in episode 1 and in the countdown: the card says nothing was saved and
   offers no Upload.
3. REG-23: "Đã kết nối · 6/6 động cơ trả lời", "không đo" and its tooltip.
4. CR-1 on the real arm: Stop holds without sagging, Về Home is slow, Thả lỏng asks first.
5. These were checked only on the emulator or not at all: over-temperature handling, the electrical
   stop, the camera-freeze path, unplug/replug of the real USB cable, and the episode size estimate
   with real cameras.

## Escape review (round 4)
* **What rounds 1-3 missed:** QD-22 (`vi.json` since 2026-11-16) and QD-23 (the reset code since
  0.2.0) were present in every earlier round.
  * QD-22: each vi sweep allowed "reset" as an unflagged word. The English-word filter treated it
    as a loanword, and nobody compared it with the button's own label.
  * QD-23: the thermal check read the main card after reset, or a freshly loaded page. Nobody
    watched the banner on the same open page after recovery, or during the next motion.
* **Checks added to the QC lists:**
  * After every stop → recover path, keep the same page open and read every banner for at least
    10 s and during the next motion. The banner must match the live state.
  * Scan `vi.json` for English words with a word list, not only the rendered pages, and compare
    each action word with the label of the button it names.
* **Owner line:** round 4 finds no unsafe behaviour. One Medium wrong-information banner after
  thermal recovery (QD-23) and one Low vi wording defect (QD-22) remain.

## Environment notes
* Servers used 127.0.0.1:18604 (Station on the emulator rig), 18605 (rig control), 18606 (`--mock`
  home checks) and 18610 (e2e Station). All were stopped before the automated suite ran.
* QC driver scripts and full-size screenshots stayed outside the repository. Only downsized
  screenshots under `docs/qc/evidence/0.2.9-r4/` are committed; they contain no personal paths or
  tokens.
