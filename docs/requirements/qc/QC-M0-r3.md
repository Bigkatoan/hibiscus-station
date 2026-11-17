# QC M0 lần 3: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-16 và QD-17 của [lần 2](QC-M0-r2.md) đã sửa đúng về hành vi (QC thấy trên bản cài),
QD-1 – QD-15 vẫn đóng. Nhưng **lượt CI của đúng commit ứng viên đỏ**: job `python (windows)` hỏng ở chính test của bản
sửa QD-16 (QD-18), nên AT-2 không đạt. QC tìm thêm **1 lỗi mới mức Low** trong báo cáo `doctor` (QD-19, giờ của tệp
hiệu chỉnh hiện theo UTC mà không ghi múi giờ). Theo quy tắc không lỗi (zero-defect), F-63, phần M0 của F-1 / P-1 và
nền kiểm AT-2 **chưa đạt**; phần M0 của F-17 (D-1) **đạt**. Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `2fc77399e668abdce33d4f712bef70b491862d0d` (HEAD trên origin lúc QC bắt đầu và lúc kết thúc) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `d112f73889fe459ff7bc941bccccae868b3900adb7407fc64563ce48b0b61f93`, **trùng byte** với wheel trong artifact `release-assets` của CI; `install.ps1` sha256 `b6653d2e8c867b354f3d179f8bcd0bee93a46f3937c3a0af69202d422969f462` và `constraints.txt`, `hibiscus-0.1.1-py3-none-any.whl` cũng trùng byte |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git): **nội dung giống hệt** (`diff -r` hai bản giải nén: không khác), chỉ khác giờ / quyền tệp trong zip, nên `overrides.txt` (chứa sha256 của nó) và `SHA256SUMS` khác theo; `hibiscus_station-1.0.0a1.tar.gz` (sdist, không ai cài) khác ở phần đầu gzip. Vì vậy QC cài thêm **chính bộ tệp của CI** (dòng dưới) |
| Cách build + cài | `git archive 2fc7739` vào thư mục trống → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: build UI + assets, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống). Lần 2: `dry_run.sh --assets <artifact release-assets của CI> --port 18654`: cùng kết quả |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44065407754 (push `release/v1`, `head_sha` = `2fc77399…`, lần chạy 1) → **failure, 11 / 12 job xanh**, `python (windows)` đỏ (QD-18). Đây là workflow duy nhất chạy cho commit này |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty) |

Kết quả dry run (trích, cả hai lần giống nhau):

```
== 2b. installer output: no uv PATH warning, the PATH line in both languages (QD-17)
OK: no uv PATH warning
== 3. version
hibiscus-station 1.0.0a1
== 4. installed libraries == the tested set (uv.lock), 100 %
installed: 115 packages; tested set: 114
OK: 100 % identical to the tested set
== 5. smoke launch on 127.0.0.1:18650
healthy: hibiscus-station 1.0.0a1 state=disconnected
/assets/index-Do-kvUZI.js -> text/javascript; charset=utf-8
== DRY RUN OK: hibiscus-station 1.0.0a1 installs without git, with the locked libraries, and serves the UI
```

## 2. Bảng kết quả

| Mục (phạm vi M0) | Kết quả | Bằng chứng / lý do |
|---|---|---|
| **AT-77** (F-63) `doctor`, phần [Vendor] | **FAIL** | Mọi bước chức năng đạt (§3), nhưng còn lỗi mở QD-19 và test của F-63 đỏ trên Windows (QD-18) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh, log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô thanh ghi 0–4, 13–15, 56–70; không có dòng `DEBUG` của thư viện |
| AT-77 bước 2 (zip không có token, `hbp_`) + log lệnh không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **không tìm thấy** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR3…`. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) qua mọi lượt doctor (4 lần dựng giả lập, 12 lượt doctor) |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e openat`: không mở `/dev/pts/8`, `/dev/pts/9`, `/dev/video*` (chỉ `/dev/null`, `/dev/tty`); số lệnh của giả lập không đổi; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2301338 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2304682: python3 -c import os,… : close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2301338, motors not checked: stop Station …` |
| AT-77: VID:PID của cổng, lời khuyên WCH không nhắc latency timer (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. Cần UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`; tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` và `calibration file vs motors: 5 of 6 match; elbow_flex: homing_offset: file 300 motor 0` |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **FAIL** (QD-18) | Lượt 44065407754: `python (windows)` `1 failed, 586 passed, 6 skipped` (`test_report_text_has_no_python_containers_anywhere[loop]`). Các job khác xanh: pytest linux `617 passed, 1 skipped`, macos `587 passed, 6 skipped`, mỗi job `skips on <os>: all in the published list`; e2e linux Chromium `7 passed`, linux Firefox `3 passed`, windows Edge `2 passed, 1 skipped` (STS cần pty, có trong danh sách); cài Windows + `--mock` smoke + MIME `.js`; macOS cài smoke; image; web; deploy |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: git gỡ khỏi PATH, `install.ps1` chạy trong **Windows PowerShell 5.1** con, toàn bộ stdout + stderr được bắt lại: **không có** cảnh báo PATH của uv; có dòng `The command folder C:\Users\runneradmin\.local\bin is now on your PATH …` trước khi cài; `installed: 92 packages; tested set: 91` / `OK: 100 % identical`; `hibiscus-station --version` = `1.0.0a1`. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp v1.0.0a1. P-1 / F-1 vẫn FAIL vì AT-2 (QD-18) |
| D-1 (e2e Playwright của repo xanh) | PASS | CI: e2e 3 trình duyệt xanh (xem AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính (mock-en, mock-vi, sts-vi) chạy bằng chuột trên **bản cài** (§3.4): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test) · chạy thật NOT VERIFIED | Test vẫn xanh trong bộ test đầy đủ; không có bộ chuyển WCH |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.4) + CI linux; Windows Edge `mock-vi` xanh |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI linux chromium) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng: `all in the published list` |
| FL-12 dry run phát hành | PASS | §1 (hai lần: assets QC build và assets của CI) |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.4. Điểm thấy được là lỗi M1 đã có mã (D-5: chữ máy tiếng Anh có đường dẫn dưới bước bị khoá), không ghi lại |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows: `healthy: hibiscus-station 1.0.0a1 state=disconnected`, `MOCK (demo) mode` |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần báo cáo `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC, 2 lần dry run), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Unit test UTF-8 xanh trong `python (windows)`. Từ lượt này CI bắt đầu ra của trình cài vào tệp rồi đọc lại bằng `Get-Content` (cp1252), nên log CI hiện chữ Việt sai dạng `Äang cÃ i`; QC giải mã ngược (cp1252 → byte → UTF-8) thì ra đúng `Thư mục lệnh … đã được thêm vào PATH`, tức trình cài phát ra UTF-8 đúng, lỗi nằm ở cách CI đọc log (ghi chú §6). Chữ trên cửa sổ PowerShell thật của khách: UAT |
| Chữ của `doctor` (vi / en) | **FAIL** (QD-19) | QD-16 đã hết: không còn dict / list / `None` / `True` / `False` trong 12 báo cáo QC chạy (stdout và `report.txt` trong zip); nhưng giờ của tệp hiệu chỉnh sai múi giờ (QD-19) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` (v8.30.1) trên cây của commit: `no leaks found`; 4 commit mới `bfe821d..2fc7739` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home; wheel không chứa `/home/…`, PAT hay token |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor, UI cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục cho QD-16, QD-17 (ghi chú §6 về câu trích) |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r3/user` trống, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin`. Hai chuỗi
STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy) do một tiến trình riêng của QC phục
vụ; tiến trình này không giữ phía slave của pty và đếm mọi lệnh nhận được. `robots.yaml` có hồ sơ `desk`
(`so101_follower` / `so101_leader` trên hai pty). Tệp hiệu chỉnh LeLab ở `…/calibration/robots/so101_follower/desk_follower.json`.
Station (bản cài) chạy một lần ở `127.0.0.1:18651` rồi tắt bằng Ctrl+C.

Như lần 2: sau `kill -9` (hoặc khi chương trình giữ cổng bị tắt) pty vẫn giữ cờ độc quyền TIOCEXCL nên mở lại báo
`EBUSY`; cổng USB thật xoá cờ này khi đóng lần cuối. QC dựng lại cặp pty mới cho các bước sau (4 lần dựng).

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Calibration files:
  follower desk_follower            so101_follower  2026-11-17T10:35:15  …/robots/so101_follower/desk_follower.json

Robot profiles:
  desk (active): cameras none
    follower: so101_follower on /dev/pts/8, calibration 'desk_follower' in LeLab's folder (so101_follower), not used by Station yet
    leader: so101_leader on /dev/pts/9, calibration 'desk_leader' MISSING
…
Motor check (read only):
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
        -> fw 3.10 model 777 temperature raw 30 = 30.0 C (max limit 70 C) voltage raw 50 = 5.0 V current raw 12 = 0.078 A load raw 0 = 0.0 % status raw 0 ok
    sync read: 0/20 failed, 0.79 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~3.1 ms
    motors carry the calibration of: …/robots/so101_follower/desk_follower.json
…
The last 4 log lines are in the zip.
```

Lệnh giả lập nhận trong lượt này: `follower {'read': 144, 'sync_read': 20} writes= 0`, `leader {'read': 144, 'sync_read': 20} writes= 0`.
QD-16: `cameras none`, `cameras front, wrist` (hồ sơ demo), `ids answering at 1 Mbps: 1-6 (model 777)`, `status ok`,
`calibration file vs motors: all 6 match` / `5 of 6 match; elbow_flex: …`, hai đường dẫn nối bằng dấu phẩy.
Giờ `2026-11-17T10:35:15` là UTC, đồng hồ máy lúc đó là 17:35 (+07): QD-19.

Khi Station đang chạy và đã kết nối (gọi `POST /api/v1/robots/desk/connect` như giao diện): `pid 2301338: mode real,
state idle`, `connected profile desk (real arms)`, `follower: not calibrated (no calibration file …; calibration files
found for this arm: desk_follower), bus errors 0`; hai cổng `skipped, in use by Station (pid 2301338)`; mục
**WHAT TO SEND / CẦN GỬI GÌ** có câu "The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi
của giả lập chỉ tăng lúc Station kết nối (69 / 36, Station ghi cấu hình khi kết nối), không tăng trong lượt doctor.

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi trường `HF_TOKEN=hf_QCr3…`,
`GITHUB_TOKEN=ghp_QCr3…`. Zip chứa `report.txt, report.json, robots.yaml, sessions/s-qc.json, station.log.tail,
calibration/follower/so101_follower/desk_follower.json` (không có `token`, `server.json`). Kết quả (zip / stdout):

```
local token   files=0 stdout=0
PAT secret    files=0 stdout=0
full PAT      files=0 stdout=0
PAT 8-char id files=0 stdout=0
HF token      files=0 stdout=0
GitHub token  files=0 stdout=0
hbp_ còn lại: 'hbp_QcR3…' (report.json, station.log.tail, sessions/s-qc.json)
station.log.tail: "token in log [local token removed]", "GET /auth?t=…", "cloud PAT hbp_QcR3… used"
```

### 3.4 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` (Playwright Chromium, chỉ bấm chuột / phím như người dùng) với **tệp chạy
`hibiscus-station` của bản cài** (môi trường Python ảo chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`; QC thấy tiến trình Station của e2e chạy từ
`…/home/.local/share/uv/tools/hibiscus-station/…`) và giao diện tĩnh lấy từ **wheel đã cài**
(`site-packages/hibiscus_station/static`): `3 passed in 161.09s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối →
hiệu chỉnh follower (Đặt home → Biên độ 6 / 6 → Lưu) → leader → Kiểm tra → camera → teleop → dừng an toàn (nhiệt /
Space e-stop) → ghi tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop → Chương trình. QC đã xem 48 ảnh chụp
(sáng / tối, vi / en): số đo hợp lý với giả lập (30 °C, 5.0 V, 0.08 A, 0 %; teleop ~236 Hz, độ trễ ~3 ms), nhãn đúng
ngôn ngữ; điểm còn thấy là D-5 (M1).

Thêm: `hibiscus-station --mock` của bản cài với HOME trống tạo dữ liệu ở `~/.hibiscus/station-demo`,
`hibiscus-station health --home …/station-demo` báo `healthy: hibiscus-station 1.0.0a1 state=disconnected`.

## 4. Bộ test tự động (QC tự chạy, Linux, worktree sạch ở `2fc7739`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `617 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 511.30s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 147.90s` |
| e2e trên bản cài (§3.4) | `3 passed` |

Worktree vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng).

### 4.1 Kiểm fail-trước-pass-sau (QD-16, QD-17)

Chạy test mà commit sửa thêm / đổi trên mã của **commit cha** (chỉ chép tệp `tests/` của commit sửa) và trên
**commit sửa**, mỗi bên một cây `git archive` riêng; `hibiscus_station` được nạp từ đúng cây đó (đã kiểm `__file__`).

| QD | Commit sửa | Trên commit cha | Trên commit sửa |
|---|---|---|---|
| QD-16 | `e2e410f` (`tests/test_doctor.py`, `tests/test_real_stack.py`) | `5 failed, 43 passed` (`test_report_text_has_no_python_containers_anywhere[loop/pty]`, `test_a_lelab_file_…[loop/pty]`, `test_doctor_reports_ports_files_and_motors_without_secrets`) | `48 passed` (Linux) · **Windows CI: 1 failed** (QD-18) |
| QD-17 | `de65b62` (`tests/test_release_tools.py`) | `1 failed, 40 passed` (`assert 143 < 132`: lệnh cài đứng trước các dòng PATH) | `41 passed` |

QD-17 còn có kiểm của `dry_run.sh` bước 2b (QC chạy hai lần trong PowerShell 7: `OK: no uv PATH warning`, có dòng
PATH hai thứ tiếng) và kiểm trong job Windows CI (PowerShell 5.1, xanh).

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-17

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ; trình cài: "Đây là bản thử nghiệm (pre-release)… Quay lại bản này sau khi cập nhật: irm …/releases/download/v1.0.0a1/install.ps1 \| iex" |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, so thư viện 100 %, smoke `--mock` |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows: không còn skip module `test_doctor`; các test doctor khác chạy và xanh trên Windows (lỗi duy nhất là QD-18) |
| QD-5 | Đóng | Test nhịp đọc bus xanh trên Windows |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | pytest macos `587 passed, 6 skipped`, skip có trong danh sách |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`; "The last 4 log lines" / "The last log line") |
| QD-12 | Đóng | §3.2 (không có `DEBUG`) |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | **Đóng về hành vi**, test của bản sửa đỏ trên Windows → theo dõi ở QD-18 | Không còn giá trị Python trong 12 báo cáo trên bản cài; fail-trước-pass-sau đạt trên Linux |
| QD-17 | Đóng | Dry run PowerShell 7 (hai lần) + CI Windows PowerShell 5.1: không còn cảnh báo PATH của uv; dòng PATH song ngữ đứng trước "Đang cài thư viện" |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị. Lỗi nào cũng chặn PASS.

**QD-18 · Low (lỗi ở test; chặn AT-2) · F-63, nền kiểm CI · Test của bản sửa QD-16 hỏng trên Windows, CI của commit ứng viên đỏ.**
Bước: lượt CI 44065407754 (push `release/v1` @ `2fc7739`), job `python (windows)` (133977720691).
Kỳ vọng: AT-2: pytest xanh trên Linux / Windows / macOS cho đúng commit.
Thực tế: `1 failed, 586 passed, 6 skipped`:
```
FAILED tests/test_doctor.py::test_report_text_has_no_python_containers_anywhere[loop] - AssertionError:
  ['    motors carry the calibration of: C:\\Users\\runneradmin\\AppData\\Local\\Temp\\pytest-of-runneradmin\\...
     \\calibration\\robots\\so101_follower\\arm_follower.json', '    motors carry the calibration of: no file found']
>       assert carry[0].endswith("so_follower/arm_follower.json, " + str(lelab / "arm_follower.json")), carry
```
`tests/test_doctor.py` dòng 999 ghép sẵn dấu `/` của POSIX; trên Windows đường dẫn dùng `\`. QC đánh giá báo cáo của
sản phẩm có thể đúng (dòng thực tế dài hơn một đường dẫn, pytest cắt ngắn), nhưng QC không thể ký "đúng trên Windows"
khi chính test kiểm điều đó đỏ. Bản sửa QD-16 đã được giao QC mà chưa qua CI Windows. Kèm theo (không tính là lỗi
riêng): `test_release_notes_of_the_pre_release_and_their_install_lines` trên Windows sinh 2 cảnh báo
`UnicodeDecodeError: 'charmap' codec can't decode byte 0x81` (đọc stdout của bước bash bằng cp1252, thiếu
`encoding="utf-8"`); test vẫn xanh vì đọc kết quả từ tệp, nhưng nên sửa cùng lúc.

**QD-19 · Low · F-63 (AT-77, quy chuẩn "thông tin đúng / hợp lý") · Giờ của tệp hiệu chỉnh trong báo cáo `doctor` là UTC nhưng không ghi múi giờ.**
Bước: máy ở múi giờ +07; lưu một tệp hiệu chỉnh lúc 17:35 giờ máy; `hibiscus-station doctor --no-cameras`.
Kỳ vọng: mục **Calibration files** cho biết tệp được sửa lúc 17:35 (giờ của máy, như tên zip
`hibiscus-station-doctor-20261117-173528.zip` và `generated_at` `2026-11-17T17:35:26+0700`), hoặc ghi rõ `UTC`.
Thực tế:
```
Calibration files:
  follower desk_follower            so_follower     2026-11-17T10:37:45  …/robots/so_follower/desk_follower.json
  follower desk_follower            so101_follower  2026-11-17T10:35:15  …/robots/so101_follower/desk_follower.json
```
`hibiscus_station/hw/factory.py` dòng 109 ghi `modified_at` theo UTC (`…T10:35:15.887185+00:00` trong `report.json`,
đúng), còn `hibiscus_station/doctor.py` dòng 881 cắt `modified_at[:19]`, bỏ mất `+00:00`. Báo cáo này dùng để biết
tệp nào là lần hiệu chỉnh mới nhất (ví dụ hai bản `so_follower` / `so101_follower` như trên); ở Việt Nam mọi giờ lệch
7 tiếng, một tệp vừa hiệu chỉnh trông như từ sáng. Lỗi có từ trước (lần 2 cũng in `09:37:32` lúc 16:37), QC lần 2 bỏ sót.

## 6. Ghi chú (không phải lỗi M0)

* **Log CI của trình cài Windows hiện chữ Việt sai** (`[Hibiscus Station] Äang cÃ i …`) từ khi job bắt ra vào tệp
  (bản sửa QD-17): `Get-Content $out, $err` của PowerShell 5.1 đọc tệp UTF-8 bằng cp1252. Byte trình cài phát ra là
  UTF-8 đúng (QC giải mã ngược được), nên đây là cách đọc log của CI, không phải điều người dùng thấy; nhưng nó làm mất
  bằng chứng REG-18 trên console mà lần 2 có. Đề nghị: `Get-Content -Encoding UTF8`.
* **`lerobot-0.7.1-py3-none-any.whl` không tái lập byte** giữa hai lần build (giờ / quyền tệp trong zip), nội dung giống
  hệt. Người dùng cài đúng tệp của CI (đã kiểm sha256 trong `SHA256SUMS` / `overrides.txt`), QC đã cài thử chính tệp
  đó. Không có AT yêu cầu build tái lập; ghi để nhóm biết khi so byte.
* **Dry run trong container in `warning: Failed to hardlink files; falling back to full copy`** của uv: do bộ nhớ đệm
  uv được gắn từ hệ tệp khác vào container. Trên Windows CI không có dòng này.
* **`hibiscus-station health` sau `kill -9` in `unhealthy: ConnectError`** (tên lớp lỗi thô). F-65 thuộc M3 (`not
  tested`), không thuộc M0; ghi để BA đưa vào QC M3.
* **Chương trình giữ cổng có dòng lệnh nhiều dòng** (ví dụ `python3 -c "…"` có xuống dòng) thì `doctor` in nguyên các
  dòng đó vào LIKELY PROBLEMS. LeLab, `lerobot-*`, Feetech FD, Arduino IDE không có dòng lệnh như vậy; ghi để biết.
* CHANGELOG trích `cameras: front, wrist`, báo cáo thật in `cameras front, wrist` (không có dấu hai chấm).
* Commit `2fc7739` sửa câu chữ AT-2 trong ACCEPTANCE theo đề nghị §6 của lần 2 ("CI build wheel một lần, Windows cài
  đúng tệp đó"); không đổi phạm vi; khách xác nhận ở lần duyệt sau.
* Các ghi chú §6 của lần 2 còn nguyên: macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong
  README trả 404 cho người ngoài (phát hành nháp sau khi QC PASS), câu chữ AT-77 bước 2, danh sách cổng trống với pty.

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QC PASS.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong cửa sổ PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | FAIL (QD-18, QD-19); mọi bước AT-77 [Vendor] đạt trên bản cài; QD-16 đóng về hành vi |
| F-1 phần M0 (P-1) | FAIL (AT-2 đỏ: QD-18); QD-17 đóng; CI Windows 5.1 không git PASS; VM Windows 11 sạch: NOT VERIFIED |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | FAIL (AT-2 đỏ: QD-18); QD-17 đóng |
| AT-2 / nền kiểm CI | FAIL (QD-18) |

QC chạy lại cổng M0 trên commit mới khi QD-18, QD-19 đã có bản sửa kèm test fail-trước-pass-sau và lượt CI của đúng
commit đó xanh 12 / 12.

Máy chủ QC đã khởi động (`127.0.0.1:18650` – `18654`, e2e trong `18655` – `18669`) và bộ giả lập đều đã dừng.
