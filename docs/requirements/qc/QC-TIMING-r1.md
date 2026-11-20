# QC report: `m1/ci-timing`, round 1

* **Verdict: PASS.** Both product changes do what they claim, on the installed artifact, and nothing regressed.
  * **NFR-2 (owner tick grid):** the fixed-rate loop now holds its target rate under heavy CPU load
    (30.00 Hz, against 29.2 – 29.5 Hz on 542ae73). After a 1 – 1.5 s process stall there is no burst of
    catch-up ticks. The e-stop still freezes within 1 tick, and the dead-man still trips within 1.0 s + 1 tick.
    Recorded datasets are frame-exact.
  * **QD-34 (doctor):** a steady 44 – 53 ms adapter is reported only as "slow bus". On 542ae73, with real
    wire timing, 10 of 38 runs (45 – 47 ms) said "reads failed … check the 3-pin cables"; on this branch, 0
    of 38. Drops, corruption, a dead servo, intermittent late answers and stalls are still reported exactly
    as before. The r10 fault grid shows no new false verdict about a servo.
  * There is no 5xx, no data loss, and no safety or timing guarantee broken. 4 non-blocking items
    (QT-1 to QT-4) go to the M1 backlog.
* **Artifact tested:** `m1/ci-timing` at `76cb925c198d67af8d1318865b1bdf99a46eeb3d`.
  * We cloned it fresh and ran `make web-install` and `make web` (the CSP and locale-guard checks passed).
    After the build `git status` was empty.
  * `uv build --wheel` gave `hibiscus_station-1.0.0a1-py3-none-any.whl`, sha256
    `5f1195135bba4363c0ad54ba105462ea648db72a68a381074bf64daf94454def`, with 190 UI files.
  * We installed it with `uv tool install --python 3.12` into an empty `UV_TOOL_DIR`, with PyAV 15.1.0.
  * The UI files in the wheel are byte-for-byte the same as in the 542ae73 wheel, and `web/` has no diff
    against 542ae73.
* **Comparison build:** `542ae73`, built the same way.
  * Its wheel sha256 is `96405c3a…a4df8d`, the same as the wheel that passed QC-INT-0210-r1, so the build
    is reproducible.
  * Every number marked "base" in this report comes from that install, run back to back with this branch
    under the same load.
* **CI:** we checked runs 44795033084, 44797905911 and 44801093749 with `gh api …/actions/runs/<id>` and
  `…/jobs`.
  * Each run has `head_sha` = `76cb925…`, branch `m1/ci-timing`, event `workflow_dispatch`, attempt 1,
    `completed` / **success**.
  * **12 / 12 jobs** succeeded in each run, every job at run_attempt 1, so nothing was re-run.
  * The diff adds no skip or xfail, and `tools/ci/allowed-skips.toml` is unchanged.
* **Date and independence:** 2026-11-21. QC is independent: we changed no product code, and pushed, tagged
  and released nothing.
* **How we timed the loop:**
  * To time the owner loop on the installed artifact, we started the installed package through a small
    probe, `scripts/shim.py`. It wraps `LoopStats.tick`, `SOFollower.send_action`, `press_estop`,
    `_enter_estop` and `heartbeat` and writes a `perf_counter` timestamp for each call. It calls the
    original functions unchanged.
  * We cross-checked the probe without it: the WebSocket `joints.tick` rate on a plain, uninstrumented
    `hibiscus-station --mock` gives the same result.
* **Load:**
  * "Load 24" means 24 busy shell loops on 12 cores (load average about 34).
  * "Load 48" means 48 loops (load average 56 – 58).

## 1. Owner loop (NFR-2), `hibiscus-station --mock`, 30 Hz

### 1.1 Rate and jitter

| Case | This branch (76cb925) | Base (542ae73) |
|---|---|---|
| Teleop, idle, 12 s (360 ticks) | **30.000 Hz**, median gap 33.333 ms, sd 0.024 ms, max 33.4 ms | 29.921 Hz, median 33.428 ms, sd 0.017 ms |
| Teleop, load 24, 12 s | **29.996 Hz** (WebSocket 29.988), sd 1.62 ms, p99 37.4 ms, max 39.6 ms, 0 gaps > 1.5 T | 29.495 Hz (WebSocket 29.528), sd 1.01 ms, p99 36.8 ms |
| Teleop, load 48, 15 s, 3 alternating rounds | **30.005 / 30.000 / 30.005 Hz**. Lag behind the nominal grid after 15 s: −2.7 / 0.0 / −2.7 ms | 29.335 / 29.254 / 29.221 Hz. Lag **332 / 373 / 388 ms** |
| Teleop, load 48, **no probe** (WebSocket tick rate only) | **30.001 Hz** | 29.494 Hz |
| Record at 30 fps, idle, one 20 s episode | 30.000 Hz, 600 frames in 19.93 s of wall time | 29.918 Hz, 600 frames |
| Record at 30 fps, load 24, 20 s | 29.995 Hz, sd 1.53 ms | 29.545 Hz, 600 frames in 20.27 s |
| Record at 30 fps, load 48, 15 s, 3 rounds | 29.997 / 29.853 / 29.998 Hz. **450 frames in 15.00 / 15.08 / 15.04 s** | 29.14 / 29.18 / 29.00 Hz. 450 frames in **15.46 / 15.44 / 15.55 s** |
| Record at 15 fps, load 48, 15 s | 14.997 Hz, 225 frames in 15.01 s | 14.735 Hz, 225 frames in 15.25 s |
| Replay (approach phase, before the dead-man test, about 2 s × 3) | idle 30.00 / 30.00 / 30.00 Hz; load 24: 30.02 / 30.00 / 29.98 Hz | idle 29.92 Hz × 3; load 24: 29.14 / 29.37 / 28.88 Hz |

* **The mean rate stays at the target.** Under heavy load the old loop ran 2 – 3 % slow, and its datasets
  said "15 s" for 15.5 s of real time. This branch holds 30 Hz, and recordings take the right wall time.
* **Gap jitter is higher under load,** by design: a tick that wakes up late is followed by a shorter one,
  which puts the loop back on the grid.
  * Load 48: sd 2.0 – 2.6 ms here, against 1.2 – 2.0 ms on the base build.
  * p99 is about the same on both builds: 38 – 40 ms.
* **Model runs:** we did not run one, because the mock has no model. They use the same `_tick_deadline()`
  as replay and recording.

### 1.2 Stalls (SIGSTOP / SIGCONT on the Station process, during teleop and recording)

| Stall | This branch: write gaps around the resume (ms) | Base |
|---|---|---|
| 1.5 s, teleop, idle | 1503.7 → **33.4, 33.4, 33.4, 33.3** | 1532.1 → 33.4, 33.4, 33.4 |
| 1.0 s, teleop, idle | 1033.1 → 33.5, 33.3, 33.3 | 1026.0 → 33.4, 33.4 |
| 1.5 s, teleop, load 24 | 1505.4 → 35.5, 34.0, 30.6, 33.3 | 1522.7 → 33.4, 33.4 |
| 1.5 s during recording (idle / load 24) | 1520.4 → 33.4, 33.3 / 1516.8 → 35.6, 33.7 | 1521.3 → 33.4 / 1530.1 → 35.9 |
| 20 ms (less than one period), teleop | 53.4 → **13.3**, 33.4 (one short tick) | 45.6 → 33.4 |

* After every stall of 1 s or longer, on both builds and under load, exactly **1 write** falls in the first
  period after the resume and 3 in the first 3 periods. That is a new grid, with no catch-up burst.
* A stall shorter than one period is caught up by **one** shorter tick (QT-1).
* Across all runs of this branch:
  * At most 2 short gaps (< 0.75 T) came in a row, once.
  * There were 0 gaps below 0.2 T.
  * There were at most 5 goal writes in any 100 ms window; the base build had at most 4.
* Evidence: `burst.txt`.

### 1.3 Recorded datasets

Each recorded dataset was checked offline with `ds_check.py` and with the F-72 checker.

* **Datasets checked:**
  * 16 datasets from the four experiment runs: idle, load 24, a 1.5 s stall, and Stop at 5 / 6 s. The four
    runs are this branch and the base, each idle and under load 24.
  * 10 from the load-48 rounds.
  * 2 on the F-72 rig (640×480 + 320×240): `tim_a` (3 + 2 appended episodes, so 2 data files) and `tim_b`.
* **Every dataset:**
  * Parquet rows = `total_frames` = the mp4 frames of each camera.
  * `timestamp == frame_index / fps`, monotonic within each episode.
  * `index` is contiguous.
  * The frame the training reader (`LeRobotDataset`) gives for every row equals the mp4 frame decoded
    directly, as a mock-camera counter.
* **Frame count = duration × fps:**
  * 600 frames for 20 s at 30 fps; 450 for 15 s; 225 for 15 s at 15 fps.
  * 120, 90 and 150 frames for the 4, 3 and 5 s F-72 episodes.
  * The stalled episode also has 600 frames, because the episode limit counts ticks, not wall time.
* **F-72, frame-exact** (`verify_frames.py`, over HTTP from the installed Station): 2 datasets ×
  7 episodes × 2 cameras × `source` / `h264` / `vp9` = **42 / 42 clips exact, 0 failures**.
* **Camera frames per row under load:**
  * At load 48, a few rows repeat the previous camera frame: 0 – 24 per 450 rows here, 4 – 12 on the base
    build.
  * The base build skips a frame more often: 15 – 24 skips against 0 – 24 here.
  * At idle, this branch has 0 repeats and 0 skips.
  * See QT-1.

### 1.4 Safety timing

| Check | This branch | Base |
|---|---|---|
| **E-stop** during teleop, 5 presses × idle / load 24 | Press → `estopped` in **0.04 – 4.4 ms**. **0 goal writes after the press**, 0 ticks completed in between | 0.04 – 0.52 ms, 0 writes |
| **Dead-man** during replay (heartbeat stopped), 3 × idle / load 24 | Last heartbeat → `estopped` `ui_lost`: **1.0003 – 1.025 s** (limit 1.0 s + 1 tick = 1.033 s). 0 ticks started past the timeout | 1.0053 – **1.034 s** |
| **Stop during recording (0.2.9)**, API, 2 × idle / load 24 | Answer in 0.005 – 0.027 s, phase `saving` at once. Idle after 0.63 – 0.64 s (idle) and 2.47 – 2.58 s (load). Datasets 151 / 180 frames for 5 / 6 s (153 / 182 under load) | 0.005 – 0.021 s; idle after 0.63 – 0.69 s / 2.34 s |
| Stop from the UI button (`cr.py`, EN 1280 light and VI 390 dark) | `saving` **0.04 s** after the click, at 6.1 s elapsed, **183 frames**. Hold after Stop: pose change 0.000 over 3 s | the same as QC-INT-0210-r1 |

## 2. Doctor (QD-34)

We reused the QC-M0-r10 tooling: an emulator process that reuses `tests/sts_emulator.py`, the r10 fault
grids, and `oracle10.py`. Every run used the installed `hibiscus-station doctor --no-cameras`, with the
Station off and a fresh HOME and pty pair per run.

| Set | This branch | Base 542ae73 |
|---|---|---|
| **Steady adapter with real wire timing** (`realistic()`, 1 ms USB timer, `adapter_delay_s` 44 – 53 ms in 0.5 ms steps, 2 seeds = 38 runs) | **38 / 38 only "slow bus"**, with no "unreliable bus" or "3-pin cables". The measured speed is right, e.g. 54.3 ms per read for 49 ms plus the wire | **10 / 38 with "unreliable bus: 1 of 20 reads failed … check the 3-pin cables"** next to "slow bus" (45 – 47 ms, both seeds: the bug reproduces) |
| Steady adapter, QC pipe and blocking emulation, 44 – 53 ms in 0.5 ms steps × 3 seeds (114 runs) | 114 / 114 only "slow bus" | the same (the bug does not reproduce without wire timing) |
| **Real faults** behind a 47 – 51 ms adapter and on a fast one (dead servo 6, 10 % and 30 % drops, 10 % corruption, 5 % of answers 300 ms late, 10 % of answers 120 ms late, one 300 ms stall at a sync read, servo 3 losing 60 %, the leader; 98 + 30 runs) | dead servo → `motor id(s) 6 do not answer (power? cable?)`. Drops → `N of 20 reads failed … 3-pin cables`. Corruption → also "corrupted". Late answers and stalls → `answers came late … stalled`. **Verdicts identical, class by class, to the base build** | identical |
| r10 invariant grids: main 576, random 300, attack10 249, special 91, attack 238, edge 43, against the clean `--verbose` truth | The oracle findings equal r10's in every class (known: 100 % drop and QD-32), **except**: QD-34 hits gone (attack 1 → 0, edge 3 → 0), and "failed reads, no bus problem named" +2 in attack10 and +1 in edge (QT-2 and the fixed edge `pipe0.047-r2`). 0 motor writes, 0 tracebacks, 0 wrong values | — |
| `pytest -m slow tests/test_doctor.py` (the invariant fault grid of the repo, fresh clone) | **436 passed** | — |
| Dev tests for this change (`test_owner.py`, `test_doctor.py` grid / steady / speed / estop subsets) | 20 passed | — |

Evidence: `qd34r.txt`, `qd34r_base_repro.txt`, `qd34_head.txt`, `qd34_base.txt`, `r10grid_oracle.txt`,
`pytest_doctor_slow.tail.txt`, `doctor/` (scenario files, classifier, the emulator with the added `realistic`
option).

## 3. Firefox e2e console guard

We ran `served_png_is_whole()` from `tests/e2e/e2e_support.py` against a local server.

| Served file | Result |
|---|---|
| Whole PNG | True |
| Truncated, bad CRC, missing IEND, trailing bytes, not a PNG, `.jpg`, 404, non-local URL | False |
| `Content-Length` larger than the body | **raises `http.client.IncompleteRead`** (QT-3) |

A truly broken image therefore still fails the test, either through the problem list or through the
exception.

## 4. Short regression of the integration list (this branch's install)

| Check | Result |
|---|---|
| Dataset pages (`ui_static`: healthy, crash-left, damaged, missing; EN / VI, 1280 / 390) | Same as QC-INT-0210-r1, field by field. The only difference before any Stop was one fewer svg in the episode view: the CR-1 banner. It matched again after a Stop. 0 5xx |
| `ui_flow` EN 1280 light and VI 390 dark (UI replay, append, Stop, error element) | Same as INT, field by field. UI Stop-to-idle 0.38 s (INT, under load: 1.54 / 1.04 s) |
| **F-72 viewer** | 42 / 42 clips frame-exact (§1.3) |
| **D-24 / D-25** (`ui_r2_d24` full EN light 1280 and VI dark 390, `ui_d25 robot`) | D-24: the note is gone 0.0 – 0.3 s after a disconnect, back after 0.54 – 0.55 s on reconnect, gone 3.04 s after the joint stream is cut. 0 dialogs on dry run and robot run. 0 page errors. D-25: `lock_gate` 0, the EN / VI hint exact, no horizontal scroll; file-share and `javascript:` URLs keep Pair disabled; 0 page errors |
| **0.2.9 Stop / Home** (`cr.py`, both configs) | Stop is prompt (§1.4). Hold 0.000. Return Home → `completed`, 0.085 from Home. The leader table shows 6/6 motors, 0 overflowing. Relax asks first. relax / go-home program: dry run and robot run `completed`. 0 page errors, 0 5xx |
| **WebGL fallback** (`webgl.py`: Chromium without WebGL EN 1280 / VI 390, Firefox EN 1280 / VI 390, Chromium with WebGL) | Every page shows one `no-webgl` panel with the exact `twin.no_webgl` text. Teleop from the UI runs and stops. Firefox prints only its own WebGL warning (QI-4). With WebGL: `ready` everywhere. 0 5xx |
| **i18n sweep** (`ui_sweep8`: 19 pages × EN / VI × light / dark × 1280 / 390) | **0 bad pages, 0 horizontal scroll, 0 console errors, 0 5xx** in all 8 configs. `en.json` / `vi.json` 1120 keys each, 0 missing, 0 placeholder mismatch |
| Station logs (every QC Station of this round) | 0 `Traceback`, 0 `ERROR` lines |

## 5. Items (non-blocking, M1 backlog)

| ID | Sev | Area | Summary |
|---|---|---|---|
| QT-1 | Low | product, `hw/owner.py` | A tick that wakes up late by less than one period is followed by a shortened tick, so goal writes can come 7 – 15 ms apart under heavy load (base: never below 20 ms) and a recording row can repeat the previous camera frame |
| QT-2 | Low | product, `doctor.py` | A very slow and jittery adapter (200 – 300 ms random) whose reads time out 30 – 45 % of the time is now summarised only as "slow bus"; the failed share shows only in the motor-check line |
| QT-3 | Low | test only | `served_png_is_whole()` raises `http.client.IncompleteRead` instead of returning False when the body is shorter than `Content-Length` |
| QT-4 | Low | test / docs | The NFR-2 integration test checks the median gap (±5 %), which the old drifting loop also passes; FEATURES-APPROVED still says "mean gap = 1/30 s ± 2 %" |

### QT-1: one short catch-up tick after a sub-period delay
* **Repro:** run teleop at 30 Hz under load 48, or SIGSTOP the Station for 20 ms.
* **Actual:**
  * Write gaps are 53 → 13 ms after a 20 ms stall.
  * Under load 48, the minimum write gap was 7.0 – 19.6 ms per 15 s run, with 8 – 16 gaps below 0.75 T per
    run, at most 2 in a row, and at most 5 writes in any 100 ms window.
  * On the base build the minimum was 20 – 26 ms.
  * In recording, some rows repeat the previous camera frame: 0 – 24 of 450 rows here, 4 – 12 on base,
    which skips more frames instead.
* **Why it does not block:**
  * It is by design: the `_tick_deadline` docstring and `test_fixed_rate_ticks_end_on_the_session_grid`
    describe it.
  * The mean rate is right, and no catch-up run follows a stall of a period or more.
  * The e-stop and the dead-man are unaffected.
  * The safety filter clamps every command, so no command exceeds `max_relative_target`.
* **Suggestion:**
  * Give a tick a minimum length, e.g. `deadline = max(grid end, t_start + T/2)`.
  * Confirm that `max_relative_target` is meant per command, not per unit of time.

### QT-2: a jittery very slow adapter loses the "reads failed" line
* **Scenario:** r10 `attack10` `jit0.2-0.3-s1` / `-s2`: every answer 200 – 300 ms late, random.
* **Base build:**
  > unreliable bus: 9 of 20 reads failed (9 got their answers only after the timeout) … check the 3-pin
  > cables …

  followed by "slow bus (226 ms per read)".
* **This branch:** only "slow bus (226.13 ms per read)". The motor-check line still says
  `sync read: 9/20 failed … 11 worked`.
* **Why:** `steady_slow()` accepts late answers up to max(1.5 × ms, ms + 10), so these reads now count as
  "slow only". The advice is arguably better: the remedy is the adapter, not the cables.
* **Suggestion:** keep the failed share in the slow-bus line, e.g. "slow bus (226 ms per read, 9 of 20
  reads timed out)".

### QT-3: the PNG guard raises on a short body
`urllib`'s `r.read()` raises `http.client.IncompleteRead`, which is an `HTTPException`, not an `OSError`.
The guard does not catch it, so the exception escapes from the Playwright console handler and the message is
never recorded as a problem. Suggestion: catch `http.client.HTTPException` too.

### QT-4: the integration timing check does not catch the drift it was written for
`test_teleop_timing_ownership_and_telemetry` asserts the median gap = T ± 5 %.

* The base build under load has a median gap of 33.4 ms, so it would pass, while running at 29.2 Hz.
* The drift is guarded only by the exact made-up-times test of `_tick_deadline`. That test is good, but
  it does not cover the loop that calls `_tick_deadline`.
* The telemetry lower bound also went from 30 reads in 3 s to 0.5 × 14 × span.
* The FEATURES-APPROVED "CI timing" row still describes the mean ±2 % check, which commit `1e9c3fb` replaced.

**Suggestion:** assert the lag behind the grid. Under load 48 this branch shows ±3 ms after 15 s and the
base build 330 – 390 ms. Then update the FEATURES row.

## 6. Not verified here
* Model runs at a fixed rate: there is no model on the mock. They use the same code path as replay and
  recording.
* macOS and Windows timing. CI covers it: 3 × 12 / 12 green on the three OS.
* The real SO-101 and a real slow USB adapter.

## Evidence
* **In the repository:** `docs/requirements/qc/evidence/timing-r1/`, with the token replaced by
  `<QC_TOKEN>`.
  * Summaries: `exp_summary.txt`, `rate_L48.log`, `burst.txt`, `ds_check.txt`, `replay_rate.txt`,
    `png_guard.txt`, the `qd34*.txt` files, `r10grid_oracle.txt`, `i18n-parity.txt`, and the wheel sha256 files.
  * `runs/`: the per-run JSON of both builds.
  * `scripts/`: the probe shim, the drivers, `ds_check.py` and the PNG test.
  * `doctor/`: the QD-34 scenarios, the classifier and the emulator.
  * `ui/`: the regression outputs and `f72-frames.json`.
* **Full scratch** (probe logs, homes, datasets, doctor run directories):
  `/tmp/claude-1000/-home-bigkatoan-lelab/a1dcb981-a281-4451-90bf-5197e9a286c9/scratchpad/qc-timing/`.
* QC Stations used ports 18611, 18631, 18641 and 18901 – 18904. All were stopped at the end.
