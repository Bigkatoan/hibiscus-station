# QC report: integration branch `m1/merge-0210`, round 1

* **Verdict: PASS.** The integration lost nothing and broke nothing that the component QC rounds had passed.
  * There is no 5xx, no blank page, no security problem and no data loss.
  * There is no regression compared with the component results: QC-0210-r4, QC-0.2.9 (and r2 to r5),
    QC-F072-r2 and QC-F029-r4.
  * We found 5 non-blocking items (QI-1 to QI-5) and put them in the M1 backlog. QI-1 is pre-existing:
    the released 0.2.10 shows it as often as this build, or more often.
* **Artifact tested:** `m1/merge-0210` at `5895c830da670eebdf5830767288d9036a155992`. This is release/v1
  (`b2ed862`) plus hotfix 0.2.9, hotfix 0.2.10, F-72 (with the macOS SVT-AV1 worker, ADR-15), the WebGL
  fallback (`0848468`) and the Windows-runnable QH-5 tests (`ebdd872`).
  * We cloned it fresh. After the build `git status` was empty.
  * `make web-install` and `make web` ran, and the CSP and locale-guard checks passed.
  * `uv build --wheel` gave `hibiscus_station-1.0.0a1-py3-none-any.whl`, sha256
    `96405c3a0afea6c85288d5608b7a05ac2cc8fc2de2d61bcd64ed8f7b38a4df8d`, with 190 UI files.
  * We installed it with `uv tool install --python 3.12` into an empty `UV_TOOL_DIR`. `--version` prints
    `hibiscus-station 1.0.0a1`, with PyAV 15.1.0.
  * Every check ran on that install as `hibiscus-station --mock`, with the bundled UI and 2 mock cameras.
    * Station A: the demo profile, `wrist` and `front` at 128×96, the same as the 0.2.10 rig.
    * Stations B, C and D: the `desk` profile, `front` at 640×480 and `wrist` at 320×240, the same as
      the F-72 and F029 rigs.
  * `HF_HOME` was set per home, and `HF_ENDPOINT` pointed at a logging trap. The trap logged
    **0 Hub requests**.
* **CI:** run 44758994820. We checked it with `gh api …/actions/runs/44758994820` and `…/jobs`.
  * `head_sha` = `5895c830…`, branch `m1/merge-0210`, attempt 1, `completed` / **success**.
  * **12 / 12 jobs succeeded:** python linux / macos / windows; web; deploy; image; release assets;
    e2e chromium / firefox / msedge; macOS and Windows install.
* **Browsers:**
  * Playwright 1.63.0 with Chromium 153.0.8010.12 and Firefox 155.0, the F-72 and F029 rigs.
  * Playwright 1.49.1 Chromium in the image `hibiscus-playwright:1.49.1`, the 0.2.10 rig.
* **Date:** 2026-11-20. QC is independent. We changed no product code, and pushed, tagged and released
  nothing.
* **Machine load:** another job (`stress_run.sh`) ran 12 busy loops through the whole session, and a
  GPU training job also ran. The load average stayed between 27 and 36 on 12 cores. Timing results
  below were measured under that load. Where a time looked slower, we compared it with the released
  0.2.10 under the same load.

## 1. Did the merge lose anything? (static)

* **Ancestry:** `release/v1` (b2ed862), `hotfix/0.2.10` (39b9c10), tag `v0.2.10` (d8c5356), tag
  `v0.2.9` (5477a22), the QC'd F-72 commit `46c7ca8` and `m1/episode-video` (0043635) are all ancestors
  of 5895c83.
  * `m1/episode-video-mac` (62e9454) is not an ancestor. Its only differences from 0043635 are a
    temporary CI proof change and the QC-F072-r2 document, which is present.
* **One-sided files:**
  * 295 files changed only on the 0.2.10 / WebGL side and 14 only on the F-72 side. All of them are
    byte-identical in the head, except the files the merge commit edited on purpose:
    * `data/video.py` now reads `meta/info.json` through the 0.2.10 validator (`read_info` +
      `info_problems`), so the video endpoints give 409 `dataset_unreadable` and never a 500.
    * `datasets.py` makes `read_info` public for that.
    * `EpisodeViewer.tsx` now formats its time label with `fmtFixed` (locale decimals).
    * Tests and documents changed to match.
  * 21 files changed on both sides. Their merged behaviour is covered by the checks below.
* **i18n:** `en.json` and `vi.json` have **1120 keys each**. No key is missing on either side, and
  every placeholder matches.
  * Against each component (v0.2.10, 0043635, b2ed862, 0848468), the only keys that are gone were
    replaced on purpose: `record.done` became `record.done_one` / `_other`, and the same for
    `datasets.summary`, `programs.run.steps`, `record.estimate` and `health.bit_angle_sensor`.
    `lock.pair_first` was removed by D-25.
  * None of the dropped keys is still used in the source.
  * The new strings (`twin.no_webgl`, `datasets.video_err_*`, `errors.dataset_unreadable`) have full
    Vietnamese diacritics.
  * Evidence: `i18n-parity.txt`.

## 2. Hotfix 0.2.10 (Station A, the 0.2.10 r4 scripts)

| Check | Result | Matches r4 |
|---|---|---|
| Datasets list and detail **during and after recording**: 1 / 3 / 10 / 11 / 15 episodes, with list, detail and telemetry polled the whole time | All finalized, rows = total, all `saved`. **0 responses ≥ 500** | yes |
| Stress: 12 × 3 s, two clients polling without pause | About 2 × 463 list and detail calls and about 1900 telemetry calls. **0 ≥ 500**. 12 saved | yes |
| Re-record, Next, Stop, Stop while saving | All work, with nothing lost. Stop answers in 0.01 s (API) and the phase is `saving` at once. Idle after 1.24 s (r4: 0.62 s, see §6) | yes |
| Resume | 3→5→6 and 11→23 episodes, index 0..N-1, all saved | yes |
| **kill -9** (3 and 12 saved) | List and detail 200, all rows `unreadable`. Append 409 `dataset_not_finalized`, replay 409 `dataset_unreadable`. **The 30 files are byte-identical** (`crash_before.sha` = `crash_after.sha`) | yes |
| **QH-9**: inconsistent counts on a 6-episode, 180-frame dataset with 3 data files | `total_episodes` 0 / 1 / 3 / 8, `total_frames` ±1, an index gap, a missing data file and a missing video file: each shows "not finalized" with the precise reason, and the append is **409 `dataset_unreadable` with byte-identical files**. The consistent copy appends 6→7 and stays finalized | identical rows to `r4_qh9.txt` |
| **info.json fuzz, short pass** (every 7th of the 825 mutations = 118). The video endpoints were **added** to each mutation | list, detail, healthy neighbour, telemetry: 118 × 200 each. `/videos` and `/videos/front?format=source`: 101 × 409 `dataset_unreadable`, 17 × 200. Append: 101 × 409, 2 × 422 `dataset_incompatible`, 15 × 200. **FAILS 0**: no 5xx, no call over 5 s, no append or replay on a not-finalized dataset, the healthy neighbour is byte-identical | yes |
| UI (`ui_static`, `ui_live` EN 1280 / VI 390, `ui_flow` EN / VI, `ui_robot`) | Same results as r4, field by field. Live recording: rows refresh on their own and all are `saved` after Stop without a reload. Error element, 409 append cards, UI replay all work. **0 5xx**. The console messages are the same set as r4 (QC's forced error-element render, the expected 409s and 404s). Only the Stop-to-idle time differs: 1.54 s / 1.04 s, against 0.35 s / 0.41 s in r4 (see §6) | yes |
| **D-26** profile delete (fresh home, `s_d26.py`) | Output is **identical to `r4_d26.json`**: 409 when connected, in a session and while calibrating; deleting another profile gives 204; calibration and datasets are kept; a new profile with the same calibration ids connects calibrated. UI: the Delete button is disabled with its hint (EN / VI) | yes |

Evidence: `batchA.log`, `crash_*.sha`, `fuzz_int.txt`, `ui_static.json`, `ui_flow_*.json`,
`ui_robot.json`, `d26.json`, `batchUI.log`, scripts `batchA.sh`, `mk_qh9.py`, `fuzz_int.py`.

## 3. Hotfix 0.2.9 fixes (Station D, `cr.py`, EN 1280 light and VI 390 dark)

| 0.2.9 item | Result |
|---|---|
| **Stop during recording is prompt** | API: Stop answers in 0.01 s with phase `saving`. UI button: in VI, phase `saving` 0.10 s after the click, at elapsed 6.17 s, and the dataset holds **185 frames** (6.17 s × 30). In EN, the Playwright click itself took 1.9 s under load; the episode was cut at the press (elapsed 9.9 s → **297 frames**), not at its 20 s limit |
| **Camera frames** (640×480 + 320×240) | Record summary: `stale_ticks` **0 / 539** and **0 / 404** on both cameras, 28.3 – 28.7 fps measured. F-72 frame check (§4): every camera mp4 decodes to exactly the episode's frames, 120 / 120 |
| **Leader table** | Robot page: "Connected · 6/6 motors answer" / VI equivalent. 3 motor tables, **0 overflowing** their card at 1280 and at 390 (QD-6 stays fixed) |
| **Stop holds in place (CR-1)** | After Stop, with the leader still sweeping: follower torque on, **pose change 0.000** over 3 s (EN and VI) |
| **Home button (CR-2)** | Return Home from the Robot page: `playing` (kind `rest`) → idle `completed`. The arm went from 35 – 49° away to **0.005 – 0.085** from Home |
| **relax / go-home blocks** | A program "relax arm → go Home" on a robot without Home: on opening the Programs tab, **without pressing Check**, the problems list shows "Set Home for this robot first." twice, with 2 **Set Home now** buttons (QD-2 stays fixed). One click sets Home and the list clears. Dry run `completed`, then the run on the robot `completed` |
| Relax asks first | The dialog "Support the arm" / "I am holding it, relax" (VI too). Cancel keeps the torque on; confirming turns it off |

* 0 page errors and 0 5xx.
* Evidence: `cr-en-1280-light.json`, `cr-vi-390-dark.json`, and in `shots/`:
  `blocks-no-home-vi-390-dark.png`, `record-stop-saving-en-1280-light.png`,
  `robot-page-en-1280-light.png`.

## 4. F-72 episode video viewer (Station B, the F072 r1/r2 scripts)

| Check | Result |
|---|---|
| **Right frames**: 2 datasets × 2 cameras × 3 formats | `five` (8 episodes, including an append into `file-001`) and `twelve` (12) × `front` / `wrist` × `source` / `h264` / `vp9`: **120 / 120 clips frame-exact** against `LeRobotDataset`. 0 mismatches, every pts starts at 0, durations right |
| **Sync with the chart** (`ui_matrix`, Chromium EN light 1280, Firefox VI dark 390) | All sync checks pass in both: the cursor moves with playback and matches the video time; the scrubber seeks every camera; a chart click seeks every camera (~2.70 s → frame ~81, also while playing); the two cameras stay in step; `slow15` (15 fps) is right; no horizontal scroll at 390; 0 page errors; 0 5xx. The 4 remaining "fails" are QC expectations, listed below |
| QV-5, QV-6, QV-9 (`qv_ui`, Chromium VI, Firefox EN) | Chromium VI **21 / 21**. Firefox EN 19 / 21. Its 2 "fails" (QV-2 Firefox cache, QV-6 "being recorded" substring) are the same known script artefacts as in QC-F072-r2 §4.2 and §4.3 |
| **QV-1: replay does not block** | During a replay of `long30`, `long30` #1 (the episode being replayed) and `five` #3 open with both tiles ready, start at frame 0 and play. `source`, `h264`, `vp9` and `/videos` give 200, and no "being recorded" sentence shows. Under this machine's load the replay itself was later stopped by the dead-man (`ui_lost`); see QI-1 |
| **409 while recording** | `qv1_phases`: 409 `episode_saving` for `/videos` and for a camera in **every phase** (`countdown`, `episode`, `reset`, `saving`), while another dataset gives 200, and 200 after the session. `saving409`: the same for a new dataset (`fresh`) and an append (`twelve`), then 200 |
| **No video for non-`saved` rows** | `novid`: 404 `no_video`, and the UI shows the single sentence with 0 tiles. Crash-left rows (`crasha`, `crashb`) and the `unreadable` rows of inconsistent datasets (`te8` #6, `gap` #5): 404 `not_found`. Their UI buttons are disabled (`ui_static`: 3 / 3 and 12 / 12) |
| **Video endpoints on an unreadable dataset** | Empty, truncated, non-object, implausible or unreadable `info.json` (`dmgi1` – `dmgi4`, `dmgx`): **clean 409 `dataset_unreadable` with reasons** on `/videos` and on every format. Missing videos: 404 `video_missing`. 23 damaged or crash-left datasets × 4 endpoints: **0 5xx**, 0 tracebacks. The fuzz above adds 118 mutations × 2 video endpoints, also 0 5xx |
| **Cache excluded from upload** | `VirtualTar(five)`, built exactly as `upload_dataset` sends it, with 98 MB of cache next to it: 11 files and **0 members** with `video-cache` or `.hibiscus` |
| Security (`security.py`) | 401 without auth. 23 traversal and bad-input paths give 404 / 422 with no content. Symlinks (source mp4, cache cut) do not leak. Range requests are right. The 4 "tamper `video_path`" cases now give **409 `dataset_unreadable`** instead of the 404 / 422 the r2 script expects: the 0.2.10 validator now refuses a template that leaves the dataset. This is stricter, as intended by the merge commit, and its own test was updated. No file content is served |

**QC expectations, not product defects:**
* Firefox VI shows the time label as "0,0 / 3,0 giây" because of the merge's `fmtFixed`, where the r2
  script expects "0.0 / 3.0" (3 checks).
* "Play again restarts from start" read t = 0.98 – 1.00 s against a < 1.0 s limit after a fixed
  400 ms wait under load. Playback did restart from the start.
* The chart scripts first clicked below the fold: the CR-1 "Stopped" banner now sits above the viewer
  (QI-3). QC added `scroll_into_view_if_needed`; after that, every chart check passes.

Evidence: `f72/` (frames, record runs, `runv*.log`, `qv-ui` and `ui` JSON, `security.json`,
`saving409.json`, `qv1-*`), `video_unreadable.txt`, `upload-tar-members.txt`.

## 5. D-24 / D-25 (Station C behind the QC proxy and fakes, the F029 r4 scripts)

| Check | Result (r4 in brackets) |
|---|---|
| **D-24 info line** (EN light 1280 and VI dark 390, full) | Disconnect: the note is gone after **0.3 s** (0.3). Reconnect: back after 0.62 – 0.64 s (0.39 – 0.57). Reconnect race: back after 1.2 – 1.43 s (1.15 – 1.18). Joint stream cut: gone after 2.74 – 2.76 s (3.07 – 3.27). 0 dialogs on dry run and robot run; the note is gone when the arm is at the start. 0 page errors |
| **D-25 Train prompt** (4 configs, with the robot connected and with it disconnected) | Train is **not locked** (`lock_gate` 0). The neutral hint reads "Connect to a Hibiscus server to train (no robot needed)." / "Kết nối máy chủ Hibiscus để huấn luyện (không cần robot).". No horizontal scroll. 0 page errors |
| **Pairing URL checks** | File-share links (OneDrive, SharePoint, Google Docs and Drive, Dropbox, …) show the error and keep **Pair** disabled. `ftp`, a URL without a scheme and `javascript:` are refused. Only the valid URLs enable Pair. API: 40 × `server_url_file_share`, 15 × `server_url_insecure`, 7 × `server_url_invalid` |
| **Identity probe, no token leak** (`api_pair3`, 134 URLs) | The proxy saw **47 requests, 0 with `Authorization`** (r4: 47 / 0). The fakes received the token only on the **7 hosts that passed the probe**, once each (the same 7 as r4). Redirects are not followed |

Evidence: `d24-*.json`, `reconnect_race.json`, `d25-robot.json`, `d25-norobot.json`,
`api_pair4.json`, `proxy.log`.

## 6. WebGL fallback (Station D, `webgl.py`)

* **Configs:** Chromium with `--disable-webgl --disable-3d-apis` (EN 1280, VI 390) and headless
  Firefox (EN 1280, VI 390). In all four, the page's `getContext('webgl2')` probe gives false.
* **Pages:** Teleop, Record, Run model, the Programs run panel, and the Trajectories tab with a saved
  trajectory (the ghost preview card and its player are present).
* **Result:**
  * Every page shows **exactly one Robot 3D panel with `data-state="no-webgl"`**, with the exact text
    of `twin.no_webgl`:
    * EN: "This computer cannot show the 3D model (the browser does not support WebGL). Everything else
      still works."
    * VI: "Máy này không hiển thị được mô hình 3D (trình duyệt không hỗ trợ WebGL). Mọi chức năng khác
      vẫn dùng được."
  * At 390 px it shows inline or in the collapsible section.
  * **0 console errors and 0 page errors** in all four configs. The THREE.WebGLRenderer error that
    QC-F072 r1 / r2 saw on Firefox is gone.
  * Firefox still prints its own console **warning** "Failed to create WebGL context … AllowWebgl2:false"
    when the probe asks (see QI-4).
* **Everything else works:** in all four configs, Start teleop from the page runs the session (the
  fallback stays shown) and Stop returns to idle. No 5xx.
* **Control:** normal Chromium (WebGL available) shows `data-state="ready"` on every page, with no
  fallback note.
* **Evidence:** `webgl-*.json`, `shots/webgl-firefox-vi-390_teleop.png`,
  `shots/webgl-chromium-nowebgl-en-1280_programs_tab-trajectories.png`.

## 7. General

* **UI sweep** (`ui_sweep8.py`): 19 pages × **8 configs** (EN / VI × light / dark × 1280 / 390). The
  pages include all menu pages, the 3 Programs tabs, a healthy, a crash-left and a damaged dataset, and
  an open episode with its video viewer.
  * In every config: **0 blank or broken pages, menu always present, 0 horizontal scroll, 0 console
    errors, 0 5xx**.
  * Evidence: `ui_sweep8.json`, `shots/episode_cnt15-vi-390-dark.png`.
* **i18n:** parity and diacritics as in §1.
* **Station logs:** all 7 Station logs of this round (A, B, C, D × 3 homes, E) have **0 `Traceback`,
  0 `ERROR` lines and 0 unhandled errors**. Station B logged only the expected WARNINGs: camera fps
  under load, and QC's damaged cuts.
* **Timing under load, compared with the released 0.2.10** (`stop_compare.txt`): the API Stop-to-idle
  time was measured on fresh 0.2.10 and 1.0.0a1 Stations, back to back, 2 × 3 times each.
  * 0.2.10: 0.92 – 1.23 s.
  * This build: 0.92 – 1.24 s.
  * They are the same, so the slower times against r4 come from the machine, not the merge. ADR-15
    changes macOS only (`sys.platform == "darwin"`).

## 8. Items (non-blocking, M1 backlog)

| ID | Sev | Origin | Summary |
|---|---|---|---|
| QI-1 | Low | pre-existing (0.2.10 the same or worse) | Under heavy CPU load, a Replay or Return Home started from the UI is sometimes stopped by the dead-man ("no heartbeat from the UI for 1.0 s", `ui_lost`) |
| QI-2 | Low | merge (F-72 `fmtFixed` meets the D-24 notes) | VI decimal separators are mixed: the video time shows "0,0 / 3,0 giây" and the motor table "7,4", but the program note says "cách 52.7°" |
| QI-3 | Low | integration of 0.2.9 CR-1 with F-72 | After any Stop the "Stopped. The arm holds its position." banner stays on every page, including Datasets, until the next motion. At 1280×900 it pushes the episode viewer's chart below the fold, so the user has to scroll to click the chart |
| QI-4 | Info | browser | Firefox without WebGL logs its own console warning "Failed to create WebGL context … AllowWebgl2:false" when the probe runs. It is a warning, not an error, and the e2e guard accepts it |
| QI-5 | Low | not F-72 (page level) | axe reports `color-contrast` (serious) on the episode page in Chromium EN light: the Robot 3D panel caption and the NOTICE / LICENSE links. 0 issues in the F-72 cards and none in the Firefox VI dark run |

### QI-1: dead-man trips UI-started Replay and Return Home under heavy load (pre-existing)
* **Repro:** with the load average about 30 on 12 cores, open `/datasets/<ds>`, click **Replay** (or
  Return Home on the Robot page), and keep the page open.
* **Actual:** some runs end `estopped`, reason `ui_lost`, after 1 – 2 s. The browser's 250 ms
  heartbeat showed gaps up to 1.08 s.
* **Same load, alternating builds** (`scripts/hb_cmp.py`, `run.sh`, `deadman_compare.log`): 2 rounds × 5 replays and
  5 Return Home per build.
  * 0.2.10: **3 / 10** replays and **2 / 10** Return Home trips.
  * 1.0.0a1: **2 / 10** replays and **1 / 10** Return Home trips.
  * In the Station D runs of this build, Return Home tripped 1 time in 11 tries.
* The dead-man code (`ws/control.ts`, `api/ws.py`, the watchdog, `deadman_timeout_s` 1.0) is unchanged
  since v0.2.9.
* **Why it does not block:** this is not a regression. The dead-man fails safe (it stops and holds). It
  needs extreme CPU starvation, and 0 trips happened in the 0.2.10 r4 and F072 r2 rounds on a normal
  load.
* **Suggestion:** measure the heartbeat on the field PCs, and consider a 1.5 – 2 s timeout or a worker
  timer for the heartbeat.

### QI-3: the Stop banner pushes the episode viewer down
* **Repro:**
  1. Stop any session (teleop, record or replay).
  2. Open Datasets → an episode at 1280×900.
* **Actual:** the CR-1 banner (with Return Home / Relax / Set Home) sits above the page, and the
  temperature chart starts below the viewport.
* This is by design of CR-1, but it now meets the F-72 page. A user must scroll before clicking the
  chart. Nothing is broken.
* **Suggestion:** show the banner only on motion pages, or make it compact.

## 9. Not verified here (as in the component rounds)

* Windows and macOS installs on real hardware. CI covers them: the macOS and Windows install jobs, and
  the e2e msedge job on Windows.
* Edge on Windows 11 without the AV1 Video Extension (AT-99 b.8).
* The real SO-101 and USB webcams.

These wait for the customer's UAT.

## Evidence
* **In the repository:** `docs/requirements/qc/evidence/int-0210-r1/`, with the token replaced by
  `<QC_TOKEN>`. It holds the JSON and log files named above, `f72/`, `scripts/` (the new QC scripts of
  this round) and 6 downsized screenshots in `shots/`.
* **Full scratch** (scripts, homes, screenshots):
  `/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-int/`.
* QC Stations used ports 18611, 18621, 18631, 18641, 18651, 18652, 18661, 18671 and 18672. All were
  stopped at the end.
