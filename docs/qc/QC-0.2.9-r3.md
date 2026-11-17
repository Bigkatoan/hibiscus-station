# QC report: Hibiscus Station hotfix 0.2.9, round 3 (hotfix gate, re-run in full)

* **Verdict: FAIL** (zero-defect rule). All six round-2 defects (QD-12 to QD-17) are fixed on the
  installed artifact as reported. Round 3 found **4 new Low defects (QD-18 to QD-21)**. None is a
  safety regression: Stop, the red e-stop, Space, relax, the dead-man stop and the thermal stop all
  behave safely, and every golden-path and neighbour journey completes.
* **Artifact tested:** branch `hotfix/0.2.9`, commit `77bc0cc5c237416eb73864b2dc18998feb46d892`.
  * Cloned fresh. UI built with `web/scripts/node.sh pnpm install --frozen-lockfile && pnpm build`
    (CSP check and locale-guard check passed).
  * Wheel built with `uv build --wheel`: `hibiscus_station-0.2.9-py3-none-any.whl`, sha256
    `0e27d9794d83eff0625409f55e3ccfe1589f29e9f94cfbb61a6626121a652c3c` (190 UI files inside).
  * Installed with `uv tool install --python 3.12 <wheel>` into an empty `UV_TOOL_DIR`.
    `hibiscus-station --version` prints `hibiscus-station 0.2.9`. The startup log says
    "Hibiscus Station 0.2.9: real hardware mode … real arms".
* **Platform:** Linux x86-64, Chromium (Playwright 1.49.1, image `hibiscus-playwright:1.49.1`). We
  drove the UI with the mouse. The keyboard was used only to type in text fields, to choose from
  native `<select>` lists, and for the Space and Esc shortcuts. Safety buttons were clicked by exact
  identity (the red e-stop is `[data-testid=estop-dock] button[aria-keyshortcuts=Space]`, the
  screen's Stop by exact name "Stop"), and every press was confirmed by the resulting state.
* **Hardware stand-in:** the installed Station in real-hardware mode (no `--mock`) against two
  `tests/sts_emulator.py` pty chains with real wire timing (`realistic()`): follower 12.1 V,
  35-37 °C; leader 5.3 V, temperature register 0 and current register 1000 raw on every motor (the
  field leader). Two `mock` cameras, 640x480 at 30 fps. Arm movement "by hand" came from the
  emulator's hand function (still, gentle, sweep, mirror).
* **Date:** 2026-11-17. QC inspector: independent. Developer summaries and the CHANGELOG text were
  not used as evidence. Round 2 was used only for its list of checks and defects.

## Round 2 defects: re-test on the installed artifact

| QD | Round 2 defect | Result | Evidence |
|---|---|---|---|
| QD-12 | 0-episode session: "0 episodes saved" + Upload of a missing dataset | **FIXED** (on screen), residual console 404 → new **QD-18** | Red e-stop in episode 1 (mouse), Space in episode 1, red e-stop in the countdown, Space in the countdown: state `estopped`, torque 1 on all 6 motors, card "No episode was saved." + "Episode 1 was stopped (e-stop pressed), so it was not kept." (countdown: "The session ended (e-stop pressed) before an episode was recorded.") + "Nothing was written: the dataset … was not created." and **Record again**; no Upload. Stop in the countdown: `idle` within 0.4 s, "You stopped before the first episode was recorded." Red e-stop in episode 2: "1 episode saved in dataset qr3_red_ep2" + "Episode 2 was stopped (e-stop pressed), so it was not kept.", Upload offered, dataset 1 episode / 300 frames. The session summary now has `discarded 1, dropped_in_progress true, dataset_kept false`. Opening a deleted dataset says "There is no dataset … on this computer. It was deleted, or its recording kept no episode." with no stale numbers, Delete or Upload (en and vi). evidence/01, 02 |
| QD-13 | Docker route installs 0.2.1 | **FIXED** (text) | README / README.vi table, `deploy/install.sh` `VERSION="0.2.9"`, `deploy/.env.example` `STATION_TAG=0.2.9-cpu`, `deploy/compose.yml`, `docs/deploy.md`, `docs/first-boot-jetson.md`, systemd unit all name 0.2.9 / v0.2.9. `git grep` finds no older version in any install route. Pulling `ghcr.io/…:0.2.9-*` is NOT VERIFIED: the image is published by the release tag, which does not exist yet. |
| QD-14 | Sessions: raw `session.kind_*` keys, English "stopped" in vi | **FIXED** | 40 sessions of every kind. en: Teleop, Record, Replay, Run model, Program, Return Home, Record trajectory, Play trajectory; outcomes completed / stopped / e-stop pressed / motor too hot / UI connection lost. vi: Điều khiển tay, Ghi dữ liệu, Phát lại, Chạy model, Chương trình, Về Home, Ghi quỹ đạo, Phát quỹ đạo; hoàn tất / đã dừng / đã bấm dừng khẩn / động cơ quá nóng / mất kết nối giao diện. No raw key. evidence/03 |
| QD-15 | Cameras: "held · None" | **FIXED** | Discovered devices: "wrist · used by wrist", "front · used by front" (vi "đang dùng bởi …"), at 1280 and 390, light and dark. No `None`, no "held". evidence/04 |
| QD-16 | Program run duration grows after completion | **FIXED** | Run "relax test" completed in 9.4 s. Minutes later the panel reads "9.4 s · 2 steps · go Home" and `GET /programs/relax_test/state` `t` stays 9.4 over 15 s. |
| QD-17 | vi tooltip "vẫn đã kết nối"; "2 camera(s)" | **FIXED** | vi tooltip: "Tay leader đã kết nối, nhưng servo 5 V của tay leader không báo giá trị này. Tay vẫn hoạt động bình thường: …". en Record form: "About 3 MB per episode with 2 cameras, …" (`estimate_one` / `estimate_other`). The same plural shortcut survives elsewhere: see QD-20. |

**Fail-first check (by QC):** the candidate's changed tests were copied onto the pre-fix tree
`42ec4c7` (code identical to round 2's `bce592e`).
* vitest (`qc029r2.screens.test.tsx`, `i18n.domains.test.ts`, `station.unit.test.ts`,
  `screens.test.tsx`): **13 of 56 fail** before (QD-12 ×4, QD-14 ×2, QD-15 ×2, QD-17 ×2, raw-value
  sweep ×2, Record end card ×1); all pass on the candidate.
* pytest (`test_api.py`, `test_programs_api.py`, `test_release_version.py`, `test_sessions.py`):
  **5 fail** before: QD-15 `test_discover_lists_each_held_camera_without_a_none_path`, QD-16
  `test_a_finished_run_keeps_its_duration`, QD-13 `test_every_install_route_names_this_release` and
  `test_the_install_script_defaults_to_this_release`, QD-12
  `test_a_session_that_keeps_no_episode_says_so`. All pass on the candidate. (Import path checked:
  the pre-fix run imported `hibiscus_station` from the pre-fix tree.)

## Hotfix gate: item → result

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Fresh install of the patch artifact | PASS (wheel) | See the header. Docker image pull NOT VERIFIED (not published before the tag). |
| 2a | Field 1: Stop button during recording | PASS | Episode 1/1 of 30 s, Stop at 10.17 s: phase `saving` within 0.01 s with elapsed frozen at 10.2 s, torque 1, 0 "No fresh frames", `idle` after 6.7 s, card "1 episode saved in dataset qr_stop1", 306 frames (10.2 s × 30). |
| 2b | Field 1: Stop with Esc | PASS | Same: `saving` at once, `idle` after 6.8 s, `qr_stop_esc` 305 frames. |
| 2c | The arm holds after Stop | PASS | Torque 1 on all 6 motors and Present unchanged over 2 s while the leader keeps moving; card "Stopped. The arm holds its position." with Return Home and Relax. |
| 2d | Red e-stop and Space during recording, episode 1 and countdown | PASS (screen), with **QD-18** | See QD-12. Each press gave `estopped` within 0.4 s with torque held; reset → `idle`, torque 1. Every end-card button followed (Record again; after a saved episode: "Where is it on this computer?" → Copy path, Upload → `/datasets/<name>?upload=1` showing the dataset and the pairing form, Back). The browser console logs one 404 at the end of every 0-episode session (QD-18). |
| 2e | Page reopened during saving (vi, 390, dark) | PASS | Pressed Dừng 5.5 s into episode 2 and closed the browser. The reopened page shows "Đang lưu tập 2…", 00:05 / 00:12, "Dừng (Esc)" enabled, then "Đã lưu 2 tập vào bộ dữ liệu qr_vi_390" on one 318 px line, no sideways scroll. 524 frames (12 s + 5.47 s at 30 fps). |
| 2f | REG-21: Stop in countdown and reset phases | PASS | Countdown: see 2d. Reset phase: Stop → `saving` at once, episode 1 kept (300 frames). |
| 3a | Field 2: cameras deliver through 3 × 30 s | PASS (mock cameras) | 329 UI samples, 0 "No fresh frames". Summary: `stale_ticks` 0, 29.7 fps measured on both cameras, loop 29.8 fps. 2700 frames; each mp4 decodes (ffprobe) to 2700 frames at 640x480. |
| 3b | Cameras live while saving | PASS | Frame tick advanced during "Saving episode …"; 0 "No fresh frames" during every save. |
| 3c | Real Windows webcam | **NOT VERIFIED** | No Windows machine or USB webcam. |
| 3d | Frozen camera (REG-22 freeze path) | **NOT VERIFIED** on the UI | `/api/v1/mock/inject` still has no camera freeze. Automated test only. |
| 4 | Field 3: leader reads as connected | PASS | "Connected · 6/6 motors answer" / "Đã kết nối · 6/6 động cơ trả lời", "not measured" / "không đo" with the tooltip (QD-17). Follower 35-37 °C, 12.1 V plausible. |
| 5a | Set Home / Replace Home from the top bar | PASS | First Home via "Set Home now" on a blocked program. Top bar: "Replace Home? The follower's current position becomes the new Home." → `rest_pose` in `robots.yaml` changed to the current pose. |
| 5b | Return Home (Robot 3D panel, page, e-stop dock) | PASS | After teleop sweep: `playing` → `idle`, end pose within 1 step of Home. From the limp state (after thermal stop / double Space): torque back on, arrives at Home. |
| 5c | Home prompt after calibration | PASS | "Set this robot's Home" card after both arms were calibrated. |
| 5d | Blocked program block offers "Set Home now" | PASS | In a fresh browser and after reload, before any Check: "Set Home for this robot first. · relax arm / · go Home" with Set Home now; one click → "No problems found." |
| 6 | Relax asks to support the arm | PASS | Dialog "Support the arm … Cancel / I am holding it, relax"; torque stays 1 until confirmed; Cancel keeps the hold. Double Space → torque 0, "Support the arm. Torque is off."; after reset "Stopped. Torque is off: the arm is limp and does not hold its position." |
| 7 | Golden path end to end | PASS, with **QD-20** | Connect (pty) → calibrate both arms (Set middle, ranges on all 6 joints incl. wrist_roll, Save) → Check 0.0° → teleop (follower within 6 steps) → red e-stop → reset → record 3 × 30 s → Stop / Esc → Return Home → program "relax test" dry run "Completed · dry run 5.3 s" → run on robot Completed (4.5 s; 9.4 s from away) → Space mid-run `estopped`, log "1.5 end · E-stopped" → "I'm clear, reset" → rerun completed from the start. The e-stopped run reads "1.5 s · **1 steps** · relax arm" (QD-20). |
| 8a | Neighbour: replay | PASS | "Moving to the start of episode 1…" → "Replaying episode 1 · 6.8 / 30 s"; episode 2 likewise. Stop → `idle`, torque 1, Present unchanged over 2 s. Closing the browser mid-replay → dead-man stop "Robot stopped: UI connection lost." (by design; see QD-19 for its detail line). |
| 8b | Neighbour: run model (import .zip by file chooser, random-weight ACT) | PASS | Compatibility: joint state and action sizes match, cameras wrist/front. Loaded on CPU in 3 s. "Episode 1 / 1 · model running · 4.9 / 30 s", the arm moved, 0 "No fresh frames". Stop → `idle`, arm holds. |
| 8c | Neighbour: trajectory record / draft / play | PASS | "Starting in 3…" then "Recording · 3.4 / 60 s · 100 samples"; Stop → take "Draft" with "Not saved yet: open Edit, then press Save take to play it.", Play disabled; Edit → Save take → Play → `traj_play` completed. |
| 9 | Over-temperature stop (elbow_flex 66 °C during teleop) | PASS | The arm parked toward Home for ~0.5 s, then torque 0 on all 6: `estopped`, reason `thermal`. Banner "Motor critical: elbow_flex 66 °C. Robot stopped, torque off. Let it cool down." + "Support the arm. Torque is off.". Reset while hot → 409, "Motors too hot: follower elbow_flex 66 °C. Let them cool down first.". Cooled to 40 °C → reset works, limp-state card. |
| 10 | Plausibility of every number shown | **FAIL** (QD-21) | Telemetry, timers, frame counts, dataset sizes, run durations (stable, QD-16), teleop 221 Hz of 250 / ~5 ms are plausible. Record form for 1 × 5 s with 2 cameras: "About 3 MB per episode with 2 cameras, **0.00 GiB in total**." (QD-21). The per-episode MB estimate against real camera content is NOT VERIFIED (mock cameras are noise and compress differently: 12.4 MiB for a 5 s episode). |
| 11 | No English leftovers in vi; "Hiệu chỉnh" | **FAIL** (QD-19) | 17 pages (incl. Sessions, Cameras, Programs: Quỹ đạo / Nhận diện / Chương trình tabs, a deleted dataset) at 390 dark and 1280 light: only loanwords (camera, model, token) and the model's own task text. `vi.json` has no "Hiệu chuẩn". But the dead-man stop shows the English server text "no heartbeat from the UI for 1.0 s" under the vi banner (QD-19). |
| 12 | 1280 / 390, light / dark | PASS | No sideways scroll on any page in en/vi × 390/1280 × light/dark. No `None`, `null`, `undefined`, `NaN`, `[object Object]` or raw i18n key on any page. Motor health tables scrollWidth = clientWidth (608/608, 768/768, 318/318). |
| 13 | e2e suite | PASS | `HIBISCUS_E2E_REQUIRED=1 HIBISCUS_E2E_PORT=18610 uv run pytest tests/e2e -m e2e` on the fresh clone: **1 passed** in 48.7 s (the single end-to-end test: connect → calibrate → cameras → teleop → thermal stop → record → dataset → ACT run → Space). |
| 14 | Regression list smoke | see below | |
| 15 | Full automated suite (once, at the end) | see "Automated suite" | |

## Regression list smoke (REGRESSION.md v1.1)

| REG | Result | Evidence / reason |
|---|---|---|
| REG-1, 17, 18, 19, 20 | NOT VERIFIED (Windows) | Windows only; automated tests in the suite run. |
| REG-2 | PASS | Startup log "real hardware mode … real arms"; no demo profile. |
| REG-3 | PASS | Leader at 0 °C on every motor: no alarm, no stop; thresholds stay 50/60/65 °C. |
| REG-4 | PASS | Ranges recorded for all 6 joints incl. wrist_roll; Save only when all green. |
| REG-5 | PASS (emulator) | 250 Hz setting: 220.7 / 250, latency ~5 ms, follower within 6 steps. "Feels like LeLab" NOT VERIFIED. |
| REG-6, REG-8 | NOT VERIFIED on the UI | Pty ports are not listed by `list_ports`. Automated tests only. |
| REG-7 | PASS | Both arms calibrated + Check in under 3 minutes; teleop runs right after. |
| REG-9 | PASS | vi 390: "Gắp đỏ" → `gap_do`, "抓取" → `program_1opb0ik`; cursor in the name field. |
| REG-10 | PASS | Space mid-run → reset → rerun completes from the start (item 7). |
| REG-11, 13, 23 | PASS | Leader 1000 raw / 0 °C: "not measured", no alerts. REG-13 can be closed after the customer's UAT-0. |
| REG-12 | PASS | Disconnected, vi 390: Calibrate, Cameras, Teleop, Record, Run model show "Bước này đang bị khoá · Hãy kết nối robot trước." with "Tới Robot" and no enabled controls; Train shows the pairing lock; Upload (datasets) stays open by design. Also locked while e-stopped. |
| REG-14, 15, 16 | automated only | In the suite run. |
| REG-21 | PASS (button, Esc, red e-stop, Space, countdown, reset, reopened page) | Items 2a-2f. |
| REG-22 | PASS for normal cameras; freeze path NOT VERIFIED on the UI | Item 3d. |

## Automated suite (run once, at the end, from the fresh clone)

* `ruff check` and `ruff format --check`: clean. `mypy --strict hibiscus_station`: no issues (83 files).
* `pnpm lint`, `pnpm format:check`, `pnpm typecheck`: pass. `pnpm test` (vitest): **16 files, 205
  tests passed**.
* `pytest -q` (fresh clone at `77bc0cc`, `uv sync --locked`, run alone on QC's side; the machine
  load from other workflows was 3-4): **533 passed, 1 skipped (Windows lock semantics), 2
  deselected (e2e), 1 failed**, in 10 min 44 s. The failure:
  `tests/test_field_028.py::test_far_leader_is_refused_then_aligned`, `assert 29.36 < 10.0`: right
  after the align phase hands over to teleop, the follower's last observation was 29° from the
  leader. The align itself completed (the wait it got headroom for in `2b1a3b4` passed); the
  immediate tracking assertion that follows has no load headroom.
  * Re-run on a quieter machine (load 0.5-1.1), `tests/test_field_028.py` alone, three times:
    **15 passed each time**.
  * The behaviour is a follower that is still catching up for a few ticks after the blend (the
    blend is timed by the clock, the follower by its 5°-per-tick limit), which is expected under
    load and harmless. On the installed artifact, align and teleop behaved correctly (items 7, 9).
  * Counted as test timing under load, not a product defect (same handling as round 2). **Team
    action:** wait for the tracking condition (`wait_for(lambda: gap < 10, …)`) instead of asserting
    it on the first tick of teleop.
* e2e: see item 13 (1 passed).
* Fail-first: see "Round 2 defects".

## Defects (QD), round 3

| QD | Severity | Area | Steps → expected → actual | Evidence |
|---|---|---|---|---|
| QD-18 | Low (console error) | Record | End a record session with no episode kept (red e-stop or Space in episode 1, e-stop or Stop in the countdown). → Expected: no 4xx and no console error (the standard applied to QD-10). → Actual: when the session ends the page re-fetches `GET /api/v1/datasets/<name>` for the dataset Station has just removed; 404, and Chromium logs "Failed to load resource: … 404 (Not Found)". Seen in all 5 runs; trace: press at 10.56 s → request 10.64 s → 404 at 10.71 s. Not on screen. A normal session (episodes kept) logs nothing. | QC trace (Chromium request log): `GET /datasets/qr3_t404` 200 at session start, then after the press 404 |
| QD-19 | Low (i18n, raw server text) | Safety banner | Close the browser (or lose the page) during replay / a program run, then open Station in vi. → Expected: the stop explained in Vietnamese only. → Actual: under "Robot đã dừng: mất kết nối giao diện." the banner prints the server detail **"no heartbeat from the UI for 1.0 s"** in English (monospace). `Banners.tsx` renders `status.detail` raw; the locked-step reason in the sidebar uses the same `status.detail`. Source: `hw/owner.py` lines 778 and 879. | evidence/05 |
| QD-20 | Low (wording) | Programs | Run a program on the robot and e-stop it during its first block. → Expected: "1.5 s · 1 step · relax arm". → Actual: "1.5 s · **1 steps** · relax arm". Keys `programs.run.now` ("{{t}} s · {{steps}} steps · {{block}}") and `programs.run.steps` ("{{n}} steps") have no `_one` form. Same class as QD-8 / QD-17; the QD-17 plural sweep missed it. vi ("1 bước") is correct. | evidence/06 |
| QD-21 | Low (plausibility) | Record | Record form: 1 episode, 5 s, 2 cameras. → Expected: a total a user believes (e.g. "about 3 MB in total"). → Actual: "About 3 MB per episode with 2 cameras, **0.00 GiB in total**." The total is `(mb × episodes / 1024).toFixed(2)` and reads 0.00 for any total under 5 MB. | `RecordPage.tsx` line 373 |

Observations (not counted as defects):
* The Sessions subtitle says "with their motor telemetry", but rows only show the maximum
  temperature and are not clickable; per-episode telemetry is on the dataset page.
* The sidebar never marks Teleop done (`done: false` by design).
* `.github/ISSUE_TEMPLATE/bug_report.yml` placeholder still reads "0.2.1" (an example, not an install route).
* By design: closing the page during a motion e-stops (dead-man); an e-stop drops the episode in
  progress; at 390 px the A column of Motor health is hidden.

## What only the customer can verify (UAT, Windows + real SO-101)
1. REG-21 / REG-22 on Windows with two USB webcams: record 3 × 30 s, press Stop (button and Esc) at
   ~10 s; "Đang lưu tập…" at once, timer stops, cameras stay live, arm holds; ~10 s × 30 frames
   saved; no "Không có hình mới".
2. Red e-stop (and Space) in episode 1 and in the countdown: the card says nothing was saved and
   offers no Upload.
3. REG-23: "Đã kết nối · 6/6 động cơ trả lời", "không đo" and its tooltip.
4. CR-1 on the real arm: Stop holds without sagging, Về Home is slow, Thả lỏng asks first.
5. Over-temperature handling (emulator only here), the camera-freeze path, and the episode size
   estimate with real cameras.

## Escape review (round 3)
* **What round 2 missed:** QD-19, QD-20 and QD-21 were present in round 2. QD-18 existed too (round 2
  attributed the console 404 to the Upload page only).
  * QD-19: the vi sweep ran while the robot was idle; no page was swept in the `estopped` state
    with a server `detail`.
  * QD-20: the plural check covered datasets, episodes and cameras, not program steps; and the run
    panel was read only after complete runs (2 steps).
  * QD-21: the estimate was read only with the default sizes.
* **Checks added to the QC lists:**
  * Sweep vi pages in every stop state (user e-stop, thermal, dead-man, device lost) for English
    server text.
  * Grep both locale files for `{{…}} <noun>s` without an `_one` form, and look at every counter
    with the value 1 on screen.
  * Record form: check the estimate with 1 short episode and with the maximum.
  * Track 4xx responses and console errors through every end-of-session path, not only page loads.
* **Owner line:** round 3 finds no safety issue; four Low wording/console defects remain.

## Environment notes
* Servers used 127.0.0.1:18600 (Station on the emulator rig), 18601 (rig control) and 18610 (e2e
  Station). All were stopped before the automated suite ran.
* QC driver scripts and full-size screenshots stayed outside the repository. Only downsized
  screenshots under `docs/qc/evidence/0.2.9-r3/` are committed; they contain no personal paths or
  tokens.
