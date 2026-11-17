# QC M0: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** 15 lỗi mở (QD-1 – QD-15: 3 High · 6 Medium · 6 Low). Theo quy tắc không lỗi (zero-defect),
F-63, phần M0 của F-1 (P-1) và phần M0 của F-17 (D-1) **không đạt**. Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình) và bản cài mà người dùng sẽ cài.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `97c1a5d446c19451af263f2c3347f00746f8acd9` (lúc QC bắt đầu, nhánh **chưa có trên origin**; QC đẩy đúng commit này lên để CI chạy) |
| Wheel QC tự build | `hibiscus_station-0.2.8-py3-none-any.whl` sha256 `e3d0bd55314b1c81088adadcdc1a7beb903cf4306847ed168eb04f9ab3a5cbce`, **trùng byte** với wheel trong artifact `release-assets` của CI (cùng `install.ps1` sha256 `97ae9c39…`) |
| Cách build + cài | `git archive 97c1a5d` vào thư mục trống → `tools/release/dry_run.sh --keep --port 18381 --out <scratch>/assets`: build UI + assets, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44034901039 (push `release/v1`, `headSha` = `97c1a5d4…`) → **failure** |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host), Python 3.12.16 do uv cài, Chromium Playwright 1.49.1 (container `hibiscus-playwright:1.49.1`), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty) |

Kết quả dry run (trích):

```
== 3. version
hibiscus-station 0.2.8
== 4. installed libraries == the tested set (uv.lock), 100 %
installed: 115 packages; tested set: 114
OK: 100 % identical to the tested set
== 5. smoke launch on 127.0.0.1:18381
healthy: hibiscus-station 0.2.8 state=disconnected
/assets/index-Do-kvUZI.js -> text/javascript; charset=utf-8
== DRY RUN OK: hibiscus-station 0.2.8 installs without git, with the locked libraries, and serves the UI
```

## 2. Bảng kết quả

| Mục (phạm vi M0) | Kết quả | Bằng chứng / lý do |
|---|---|---|
| **AT-77** (F-63) `doctor`, phần [Vendor] | **FAIL** | Chức năng chính đạt (xem §3), nhưng còn lỗi mở QD-10 – QD-14; bộ test `doctor` không chạy trên Windows (QD-4) và đỏ trên macOS (QD-7) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: báo cáo đủ phiên bản, hồ sơ, tệp hiệu chỉnh, log, từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô thanh ghi 0–4, 13–15, 56–70 |
| AT-77 bước 2 (zip không có token, `hbp_`) + log lệnh không có lệnh ghi | PASS | §3.3: token cục bộ, phần bí mật của PAT, mã 8 ký tự của PAT, `hf_…`, `ghp_…` cài sẵn: **không tìm thấy**; chỉ còn dạng đã che `hbp_QcPl…` (đúng dạng AT-8 cho phép). Giả lập: `read 144, sync_read 20`, **0 lệnh ghi** mỗi tay |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | `! MOCK PROFILE ACTIVE: 'demo' drives SIMULATED arms, the real arm will not move` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS (có QD-13) | `strace`: không mở `/dev/pts/6`, `/dev/pts/7`, `/dev/video*`; giả lập 0 giao dịch |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 1706695 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/6 is busy, held by pid … close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid …` |
| AT-77: VID:PID của cổng, lời khuyên WCH không nhắc latency timer (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. Chỉ có test tự động (fail-trước-pass-sau, §4). Cần UAT-0 trên PC của khách (CH340 / CH343) |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **FAIL** | Lượt CI 44034901039: 6 / 11 job đỏ (QD-2 – QD-8); ma trận CI chưa đúng AT-2 (QD-9) |
| **AT-1** phần [Vendor] (Windows 11 sạch, không git, bộ thư viện trùng 100 %) | **FAIL** | Job CI `windows (install.ps1 without git …)` (Windows PowerShell 5.1, git bị gỡ khỏi PATH) **đỏ** (QD-2); phiên bản in ra không phân biệt được với bản 0.2.8 đã phát hành (QD-1). Trên Linux (PowerShell 7, không git): cài được, 100 % trùng → PASS cho Linux. **VM Windows 11 sạch thật: NOT VERIFIED** |
| D-1 (e2e Playwright của repo xanh) | **FAIL** (chưa đóng) | Linux: QC chạy lại `tests/e2e -m e2e` = `7 passed`, CI e2e linux `7 passed`. Windows: CI e2e `test_station_ui_end_to_end[mock-en]` **đỏ** (QD-3) |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Chạy thật trên bản cài (bước 5, 6) + test fail-trước-pass-sau đã kiểm (§4: 5 test đỏ ở commit cha, xanh ở commit sửa) |
| D-21 (latency timer chỉ cho FTDI) | PASS (test) · chạy thật NOT VERIFIED | §4: 2 test đỏ ở commit cha, xanh ở commit sửa. Không có bộ chuyển WCH để chạy thật |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | Chạy thật trên giả lập (§3.2) + §4: 3 test đỏ ở commit cha, xanh ở commit sửa |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS Linux · FAIL Windows | Linux xanh (local + CI). Windows: QD-3 |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux) | `tests/e2e/test_screen_matrix.py` nằm trong `7 passed` (local và CI linux) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | **FAIL** | Linux: `skips on linux: all in the published list`. Windows: `SKIPPED, not in tools/ci/allowed-skips.toml for windows: tests.test_doctor (collection skipped)` (QD-4). macOS: 11 test pty đỏ thay vì skip (QD-7) |
| FL-12 dry run phát hành | PASS | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | ruff `All checks passed!`, format `141 files already formatted`, mypy `Success: no issues found in 83 source files`, pytest `563 passed, 1 skipped, 8 deselected` (skip nằm trong danh sách), e2e `7 passed`, eslint 0, tsc 0, `check:api` 0, vitest `173 passed (173)` |
| Lối đi người dùng bằng chuột (bản cài, `--mock`, 1280 px, `vi-VN`) | PASS cho phần M0 | Chào mừng → Thiết lập robot → Kết nối → **Hiệu chỉnh**: follower (Đặt home → Biên độ 6 / 6 → Lưu) → leader → Kiểm tra. Rời trang giữa chừng rồi quay lại: luồng tiếp tục đúng bước. Ảnh: [biên độ](evidence/m0/mock-hieu-chinh-bien-do.png), [kiểm tra hai tay](evidence/m0/mock-kiem-tra-hai-tay.png). Các điểm thấy được đều là lỗi M1 đã biết (D-5, D-7, D-8), không ghi lại |
| Lối đi trên giả lập STS (bản cài, không `--mock`) | PASS | Hồ sơ `so101` trên `/dev/pts/6`, `/dev/pts/7` → Kết nối (mouse) → bảng sức khoẻ: 30 °C, 5.0 V, 0.08 A, 0 % (hợp lý với giả lập) → trang Hiệu chỉnh nhận tệp LeLab |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | NOT VERIFIED | Job cài Windows dừng trước bước `--mock` smoke (QD-2). Unit test Windows (`test_platform.py`, 28 test) xanh trong job python (windows) |
| REG-2 (hồ sơ demo thay tay thật) | PASS | `doctor` báo `MOCK PROFILE ACTIVE` (bước 3); `tests/test_field_reports.py` xanh trong lượt pytest của QC |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần báo cáo `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS Linux / macOS · Windows NOT VERIFIED | `text/javascript` (dry run QC, CI release-assets, CI macOS). Windows: smoke không chạy tới (QD-2); `test_web_mimetypes_are_pinned` xanh trên Windows |
| REG-18 (UTF-8 trên Windows) | PASS (CI) · UAT NOT VERIFIED | `test_utf8_console_and_timer_do_not_fail`, `test_vietnamese_log_line_through_a_pipe` xanh trên `windows-latest` |
| Chữ của `doctor` (vi / en) | PASS | Mục cuối **WHAT TO SEND / CẦN GỬI GÌ** song ngữ, đúng dấu, khớp hướng dẫn `docs/user-guide/vi/station.md` ("Báo cáo bằng tiếng Anh (dành cho kỹ sư), trừ mục cuối"); 3 biến thể (đủ, thiếu kiểm động cơ, `--no-ping`) đều có câu tiếng Việt tương ứng |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` trên cây của commit: `no leaks found`; 37 commit đều tác giả `…@users.noreply.github.com`; wheel không chứa `/home/…`, PAT hay token |
| Vệ sinh phát hành: phiên bản, changelog | **FAIL** | QD-1, QD-15 |

## 3. Chi tiết AT-77 trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/user` trống. Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh
LeLab, leader nhà máy). `robots.yaml` có hồ sơ `desk` (`so101_follower` / `so101_leader` trên hai pty). Tệp hiệu chỉnh
LeLab đặt ở `…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy một lần ở
`127.0.0.1:18383` rồi tắt bằng Ctrl+C. Bộ giả lập được sửa nhỏ trong thư mục QC để không tự giữ pty (cổng USB thật
không có ai giữ khi chương trình đã tắt) và ghi lại mọi lệnh nhận được.

### 3.2 `hibiscus-station doctor --verbose` (Station tắt)

```
LIKELY PROBLEMS:
  ! desk follower: no calibration 'desk_follower' (files found: desk_follower - Calibrate > Use this file)
  ! desk leader: no calibration 'desk_leader'
…
Running Station:
  Station is not running
…
  desk follower on /dev/pts/6: ids answering at 1 Mbps {'1': 777, '2': 777, '3': 777, '4': 777, '5': 777, '6': 777}
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status [] protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
        -> fw 3.10 model 777 temperature raw 30 = 30.0 C (max limit 70 C) voltage raw 50 = 5.0 V current raw 12 = 0.078 A load raw 0 = 0.0 % status raw 0 []
    sync read: 0/20 failed, 0.59 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
    motors carry the calibration of: ['…/robots/so101_follower/desk_follower.json']
```

Lệnh giả lập nhận trong lúc chạy: `follower {'read': 144, 'sync_read': 20} writes= 0`, `leader {'read': 144, 'sync_read': 20} writes= 0`.

Khi tệp hiệu chỉnh nằm đúng chỗ Station dùng (`so_follower`, `so_leader`): `LIKELY PROBLEMS:` / `No likely problems found` (FL-11 đạt).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự, đọc từ tệp `token`) ở dạng thô và sau `t=` trong `logs/station.log`; một PAT đúng định
dạng `hbp_<8>_<43>` trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi trường
`HF_TOKEN=hf_QC…`, `GITHUB_TOKEN=ghp_QC…`. Zip chứa `report.txt, report.json, station.log.tail, robots.yaml,
calibration/…, sessions/s-qc.json` (không có `token`, `server.json`). Kết quả:

```
local token (43 chars): not found
PAT secret part: not found
full PAT: not found
PAT 8-char id: not found
HF token: not found
GitHub token: not found
hbp_ occurrences: 5 [('report.json', 'hbp_QcPl\u20…'), ('station.log.tail', 'hbp_QcPl…'), ('sessions/s-qc.json', 'hbp_QcPl… ')]
```

Chuỗi `hbp_` còn lại là dạng đã che (`hbp_` + 4 ký tự + `…`), giống cách AT-8 mô tả token được che. Đánh giá: đạt.
Ghi chú cho BA: AT-77 bước 2 ghi "tìm chuỗi `hbp_` … (2) không tìm thấy"; nên sửa câu chữ AT thành "không có PAT đầy
đủ; chỉ dạng che `hbp_xxxx…`" để AT thực hiện được đúng như viết.

## 4. Kiểm fail-trước-pass-sau (đã checkout commit cha)

Mỗi commit sửa: chạy các test mà chính commit đó thêm vào, trên mã của **commit cha** (chỉ chép `tests/test_doctor.py`
của commit sửa) và trên **commit sửa**; `hibiscus_station` được nạp từ đúng cây đó (đã kiểm `__file__`).

| Lỗi | Commit sửa | Trên commit cha | Trên commit sửa |
|---|---|---|---|
| K-11 | `693ca5b` | `3 failed, 1 passed` (`KeyError: 'Present_Current'`, `StopIteration`, `no attribute 'raw_dump'`; test còn lại là test canh "không ghi" vốn đã đúng) | `4 passed` |
| D-15 | `81e9aac` | `5 failed` | `5 passed` |
| D-21 | `3a4a3fe` | `2 failed` (`teleop_estimate() takes 1 positional argument`, LIKELY PROBLEMS còn nhắc latency timer) | `2 passed` |

D-1 không kiểm lại trên commit cha (yêu cầu là ít nhất hai); D-1 vẫn mở vì Windows (QD-3).

## 5. Lỗi QC (QD-n)

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị. Lỗi nào cũng chặn PASS.

**QD-1 · High · F-1 / P-1, AT-1, vệ sinh phát hành · Bản ứng viên M0 mang phiên bản `0.2.8`, trùng bản đã phát hành.**
Bước: build commit `97c1a5d`, cài, `hibiscus-station --version`; đọc dòng cuối của `install.ps1`; mở liên kết trong đó.
Kỳ vọng: một phiên bản pre-release riêng (README / README.vi nói bản thử nghiệm M0 là `1.0.0a1`, cài bằng liên kết
`…/download/v1.0.0a1/install.ps1`), khác 0.2.8 ở mọi chỗ, để khách và `doctor` biết đang chạy bản nào.
Thực tế: `hibiscus-station 0.2.8`, UI `hibiscus-station-web@0.2.8`; trên GitHub tag `v0.2.8` đã phát hành (mã cũ, không có
`install.ps1`), nên không tạo được pre-release cho bản này với số đó. Trình cài in "Quay lại bản này: irm
https://github.com/Bigkatoan/hibiscus-station/releases/download/v0.2.8/install.ps1 | iex" → `curl` trả **404**
(liên kết `releases/latest/download/install.ps1` trong README cũng **404** hôm nay).

**QD-2 · High · F-1 / P-1, AT-1 [Vendor], AT-2, REG-1 · `install.ps1` dừng với lỗi trên Windows PowerShell 5.1 không git (CI).**
Bước: job CI `windows (install.ps1 without git, libraries == uv.lock, --mock smoke)` (lượt 44034901039, job
133877393390): gỡ git khỏi PATH, `Get-Content -Raw release\install.ps1 | Invoke-Expression` trong `powershell.exe`.
Kỳ vọng: "Xong: hibiscus-station <phiên bản>", rồi so thư viện và smoke `--mock`.
Thực tế: `uv tool install` xong ("Installed 1 executable: hibiscus-station"), sau đó:
```
Join-Path : Cannot find drive. A drive with the name 'C' does not exist.
At line:149 char:20
+         $got = (& (Join-Path $bin $exeName) --version | Out-String).T ...
```
Job đỏ; bước so thư viện và smoke `--mock` không chạy. (Gợi ý điều tra, chưa xác minh: chuỗi `$bin` lấy từ
`uv tool dir --bin` có thể mang ký tự điều khiển khi `FORCE_COLOR=1`; người dùng thật có thể gặp hoặc không.)

**QD-3 · High · F-17 / D-1, AT-2 · e2e Playwright trên `windows-latest` (`--mock`) đỏ.**
Bước: job CI `e2e (windows, Playwright, hibiscus-station --mock)` (133875828667).
Kỳ vọng: `mock-vi` và `mock-en` xanh. Thực tế: `FAILED tests/e2e/test_station_ui.py::test_station_ui_end_to_end[mock-en] -
AssertionError: timed out waiting for state in ('inferring',) (last: False)`, kèm `ConnectionResetError: [WinError 10054]`;
`1 failed, 1 passed, 1 skipped`. D-1 chưa đóng trên Windows.

**QD-4 · Medium · NFR-18, AT-2, F-63 · Cả `tests/test_doctor.py` bị bỏ qua trên Windows và không có trong danh sách.**
Bước: job CI `python (windows)` (133875306726). Kỳ vọng: mọi test `doctor` không cần pty chạy trên Windows (gồm
`test_a_port_another_program_holds_on_windows_is_a_likely_problem`, test riêng cho Windows của D-15); mọi skip có trong
`tools/ci/allowed-skips.toml`. Thực tế: `SKIPPED [1] tests\test_doctor.py:19: pseudo-terminals are POSIX only` (skip cả
module) → `##[error]SKIPPED, not in tools/ci/allowed-skips.toml for windows: tests.test_doctor (collection skipped)`.

**QD-5 · Medium · AT-2 (REG-5 / REG-19 liên quan) · Teleop lean trên Windows đọc bus quá số lần cho phép mỗi nhịp.**
Bước: job `python (windows)`. Kỳ vọng: `test_teleop_lean.py::test_lean_tick_never_reads_telemetry_and_observation_in_one_tick`
xanh (≤ 2 `sync_read` mỗi nhịp). Thực tế: `AssertionError: [5, 5, 5, 5, 8]`; phần lớn nhịp 4–5 lần đọc
(`1 failed, 532 passed, 7 skipped`). Linux xanh.

**QD-6 · Medium · AT-2 · Test thời gian `test_field_028` đỏ trên CI Linux.**
Bước: job `python (linux)` (133875306526). Thực tế: `FAILED tests/test_field_028.py::test_rest_move_is_slow_cancellable_and_needs_the_heartbeat - assert 4.57483516483515 > 20.0`
(`1 failed, 562 passed`). Cùng commit, máy QC: xanh → test phụ thuộc tốc độ máy (không ổn định); CI không xanh.

**QD-7 · Medium · AT-2, NFR-18, F-63 · Job `python (macos)` đỏ: 38 test.**
Bước: job 133875306683. Kỳ vọng: xanh, test pty bị bỏ qua có tên trong danh sách. Thực tế: `38 failed, 525 passed`;
gồm 11 lỗi pty `cannot open /dev/ttys000 (follower): Not a typewriter` (`test_real_stack`, `test_calib_simple`; danh sách
skip không có mục macOS nào), 5 test `doctor` (`KeyError: 'raw_dump'`, `KeyError: '3'`, `test_doctor_reports_ports_files_and_motors_without_secrets`),
và các test thời gian / camera (`test_sessions`, `test_program_session`, `test_owner`, `test_teleop_latency`). macOS là bản xem
trước (QĐ-2) nhưng tiêu chí M0 ghi "CI xanh Linux / Windows / macOS".

**QD-8 · Medium · AT-2 · Smoke image Docker `-cpu` không healthy.**
Bước: job `image (cpu, linux/amd64, smoke test)` (133875425028). Kỳ vọng: container `--mock` healthy, trang chủ trả
`<title>Hibiscus Station</title>`. Thực tế: sau 60 × 3 s không healthy, `##[error]Process completed with exit code 1`; job
không in log container nên không biết lý do.

**QD-9 · Medium · AT-2 · CI chưa chạy đúng ma trận AT-2 ghi.**
AT-2: "Linux (… e2e Chromium + Firefox), `windows-latest` (… e2e Edge `--mock`)". `ci.yml`: Linux `playwright install
--with-deps chromium`, Windows `chromium`; không có Firefox, không có Edge. Hoặc sửa CI, hoặc BA sửa AT-2 (thay đổi
phải được khách duyệt).

**QD-10 · Low · F-63 (AT-77, quy tắc thông tin đúng) · `doctor` tự mâu thuẫn về tệp hiệu chỉnh của LeLab.**
Bước: tệp `desk_follower.json` của LeLab ở `calibration/robots/so101_follower/`, hồ sơ dùng `desk_follower`; chạy
`doctor --verbose`. Kỳ vọng: một câu đúng và dùng được, ví dụ "đã có tệp `desk_follower` của LeLab, Station chưa dùng:
Hiệu chỉnh > Dùng". Thực tế: cùng một báo cáo có `! desk follower: no calibration 'desk_follower' (files found:
desk_follower - Calibrate > Use this file)`, `calibration 'desk_follower' MISSING`, và `motors carry the calibration of:
['…/so101_follower/desk_follower.json']`.

**QD-11 · Low · F-63 · Giá trị Python thô và lỗi số nhiều trong báo cáo.**
Bước: chạy `doctor` khi Station đang chạy và đã kết nối. Thực tế: `pid 1697856: mode real, state idle reason None detail None`,
`follower: calibrated False issue no calibration file … bus errors 0 last None`; và `Last 1 log lines are in the zip.`
Kỳ vọng: không có chữ máy / placeholder (`None`, `False`), số nhiều đúng ("Last 1 log line").

**QD-12 · Low · F-63 · `doctor --verbose` in dòng DEBUG của thư viện khác.**
Thực tế: 6 dòng `DEBUG root: Detected pyserial version: 3.5`, `… rustypot …`, `… datasets …`, `… pandas …`, `… av …`
xen giữa các dòng tiến trình, trước `LIKELY PROBLEMS`. `--verbose` theo `--help` chỉ để "Print every bus error (motor id,
register)". Kỳ vọng: không có dòng debug của thư viện.

**QD-13 · Low · F-63 · `--no-ping` báo "no real arm in the profiles (or --no-ping)".**
Bước: hồ sơ có hai tay thật; `doctor --no-ping --no-cameras`. Thực tế: mục Motor check ghi `no real arm in the profiles
(or --no-ping)`. Kỳ vọng: nói đúng lý do đã biết ("skipped: --no-ping"), không gợi ý sai rằng không có tay thật.

**QD-14 · Low · F-63 (FL-11) · Tệp hiệu chỉnh của hồ sơ khác EEPROM động cơ nhưng LIKELY PROBLEMS ghi "No likely problems found".**
Bước: tệp `so_leader/desk_leader.json` có `elbow_flex.homing_offset = 300`, động cơ có 0; `doctor --no-cameras`.
Thực tế: thân báo cáo có `calibration file vs motors: {… 'elbow_flex': 'homing_offset: file 300 motor 0' …}` và
`motors carry the calibration of: no file found`, nhưng đầu báo cáo: `No likely problems found`. Kỳ vọng (FL-11: LIKELY
PROBLEMS khi có vấn đề): nêu "tệp hiệu chỉnh của leader không khớp động cơ". BA phân loại lỗi / CR nếu nhóm cho rằng
đây là hành vi đúng.

**QD-15 · Low · vệ sinh phát hành · CHANGELOG không ghi thay đổi của M0.**
`CHANGELOG.md`: `## [Unreleased]` trống; mục mới nhất là `[0.2.8] - 2026-11-16`. Các thay đổi người dùng thấy của bản này
(doctor: dòng / tải / dump thô, D-15, D-21, mục "CẦN GỬI GÌ"; lệnh cài một dòng PowerShell, P-1) không có trong changelog.

## 6. Ghi chú (không phải lỗi M0)

* Các điểm thấy khi đi luồng bằng chuột đều là lỗi M1 đã có mã: chữ máy tiếng Anh có đường dẫn đầy đủ dưới bước bị khoá
  (D-5), "gripper: lệch hơn 20°" với cột đơn vị % và luôn liệt kê cả ba nguyên nhân (D-7), tay leader giả không theo
  follower ở Kiểm tra (D-8 / P-4).
* Wheel `lerobot-0.7.1` và `hibiscus_station-0.2.8.tar.gz` build lại khác byte giữa máy QC và CI (dấu thời gian trong
  wheel); wheel Station trùng byte. Không có yêu cầu nào về build tái lập; ghi để biết rằng bản phát hành phải lấy từ CI.
* Danh sách cổng của `doctor` trống với pty (`(none) - is the arm's USB cable plugged in?`): đúng hành vi (pyserial không
  liệt kê pty), không phải lỗi.
* QC đã đẩy `release/v1` lên origin (nhánh trước đó chưa có trên GitHub, nên chưa có CI cho commit này).

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng, `hibiscus-station --version` (UAT-0 / UAT-1 bước 1),
  sau khi QD-1, QD-2 đã sửa và QC chạy lại.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-1, REG-17 trên Windows: Station mở được giao diện sau khi cài (sau khi QD-2 sửa, CI Windows phải chứng minh trước).

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | FAIL (QD-4, QD-7, QD-10 – QD-14) |
| F-1 phần M0 (P-1) | FAIL (QD-1, QD-2); VM Windows 11 sạch: NOT VERIFIED |
| F-17 phần M0 (D-1) | FAIL (QD-3) |
| P-1 (cài) | FAIL (QD-1, QD-2) |
| AT-2 / nền kiểm CI | FAIL (QD-2 – QD-9) |

QC chạy lại toàn bộ cổng M0 trên commit mới khi mọi QD đã có bản sửa kèm test fail-trước-pass-sau.

Máy chủ QC đã khởi động (`127.0.0.1:18381`, `18383`, `18384`, `18385`) và bộ giả lập đều đã dừng.
