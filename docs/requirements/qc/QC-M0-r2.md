# QC M0 lần 2: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-1 – QD-15 của [lần 1](QC-M0.md) đều **đã đóng** (bản sửa có test đỏ ở commit cha,
xanh ở commit sửa, hoặc lượt CI đỏ trước đó làm bằng chứng; QC chạy lại AT trên bản cài). QC tìm thêm **2 lỗi mới
mức Low** (QD-16, QD-17). Theo quy tắc không lỗi (zero-defect), F-63 và phần M0 của F-1 / P-1 **chưa đạt**; phần
M0 của F-17 (D-1) **đạt**. Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `bfe821d61e3a913c6ba642feffa320980255bf57` (HEAD trên origin lúc QC bắt đầu) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `b20a5ccdf3fac0e7ee6779f893dd6235c8dfd8fca635039d6b89514d305dea12`, **trùng byte** với wheel trong artifact `release-assets` của CI; `install.ps1` sha256 `0f948750815f516f82e1219031a2ceb95b30770e07f2263394998a7daf0e6a09`, cũng trùng byte |
| Cách build + cài | `git archive bfe821d` vào thư mục trống → `tools/release/dry_run.sh --keep --port 18510 --out <scratch>/assets`: build UI + assets, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44054326182 (push `release/v1`, `head_sha` = `bfe821d6…`, lần chạy 1) → **success, 12 / 12 job xanh**. Đây là workflow duy nhất chạy cho commit này (`gitleaks`, `codeql`, `docker` không chạy trên push nhánh) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host), Python 3.12.16 do uv cài, Playwright 1.63.0 (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty) |

Kết quả dry run (trích):

```
== 3. version
hibiscus-station 1.0.0a1
== 4. installed libraries == the tested set (uv.lock), 100 %
installed: 115 packages; tested set: 114
OK: 100 % identical to the tested set
== 5. smoke launch on 127.0.0.1:18510
healthy: hibiscus-station 1.0.0a1 state=disconnected
/assets/index-Do-kvUZI.js -> text/javascript; charset=utf-8
== DRY RUN OK: hibiscus-station 1.0.0a1 installs without git, with the locked libraries, and serves the UI
```

## 2. Bảng kết quả

| Mục (phạm vi M0) | Kết quả | Bằng chứng / lý do |
|---|---|---|
| **AT-77** (F-63) `doctor`, phần [Vendor] | **FAIL** | Mọi bước chức năng đạt (§3), nhưng còn lỗi mở QD-16 |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh, log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô thanh ghi 0–4, 13–15, 56–70; không có dòng `DEBUG` của thư viện |
| AT-77 bước 2 (zip không có token, `hbp_`) + log lệnh không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **không tìm thấy** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR2…`. Giả lập: tổng cộng **0 lệnh ghi** (`write` / `sync_write`) qua mọi lượt doctor |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -e openat`: không mở `/dev/pts/10`, `/dev/pts/11`, `/dev/video*`; số giao dịch của giả lập không đổi; mục Motor check: `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2144537 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/10 is busy, held by pid 2148559: python3 -c … close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2144537, motors not checked: stop Station …` |
| AT-77: VID:PID của cổng, lời khuyên WCH không nhắc latency timer (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. Cần UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`; tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | PASS | Lượt 44054326182: 12 / 12 job xanh. pytest linux `613 passed, 1 skipped`, windows `584 passed, 6 skipped`, macos `584 passed, 6 skipped`; mỗi job: `skips on <os>: all in the published list`. e2e: linux Chromium `7 passed`, linux Firefox `3 passed`, windows **Edge** (`msedge`) `2 passed, 1 skipped` (STS cần pty, có trong danh sách). Cài Windows + `--mock` smoke + MIME `.js`; macOS cài smoke. Ghi chú §6 |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | **FAIL** (QD-17) · phần CI PASS · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: git bị gỡ khỏi PATH, `install.ps1` chạy trong **Windows PowerShell 5.1** (`powershell.EXE`) → `Xong: hibiscus-station 1.0.0a1`; `installed: 92 packages; tested set: 91` / `OK: 100 % identical`; `hibiscus-station --version` = `1.0.0a1`. Trình cài in cảnh báo sai cho người dùng (QD-17). Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` tải từ GitHub chưa thử được: chưa có bản nháp v1.0.0a1 (CI cài từ thư mục cục bộ) |
| D-1 (e2e Playwright của repo xanh) | PASS | CI: xem AT-2. QC chạy lại trên đúng commit: Chromium `tests/e2e` §4, Firefox §4. Luồng chính (mock-en, mock-vi, sts-vi) chạy bằng chuột trên **bản cài** (§3.4): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test) · chạy thật NOT VERIFIED | Test của lần 1 vẫn xanh trong bộ test đầy đủ; không có bộ chuyển WCH |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.4) + CI linux; Windows Edge `mock-vi` xanh |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI linux chromium) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng: `all in the published list`; `tests/test_doctor.py` chạy trên Windows và macOS (cổng loopback), không còn bị bỏ qua |
| FL-12 dry run phát hành | PASS | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.4. Các điểm thấy được là lỗi M1 đã có mã (D-5: chữ máy tiếng Anh có đường dẫn dưới bước bị khoá), không ghi lại |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows: `healthy: hibiscus-station 1.0.0a1 state=disconnected`, `MOCK (demo) mode` |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần báo cáo `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (CI) · UAT NOT VERIFIED | Unit test UTF-8 xanh trong `python (windows)`; chữ tiếng Việt của trình cài hiện đúng trong log PowerShell 5.1 (`install.ps1` chỉ có ASCII, chữ Việt dựng bằng `[char]`) |
| Chữ của `doctor` (vi / en) | **FAIL** (QD-16) | Mục **WHAT TO SEND / CẦN GỬI GÌ** đúng cả 3 biến thể; `None` / `False` / "Last 1 log lines" đã hết; nhưng thân báo cáo còn dict / list Python |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` (v8.30.1) trên cây của commit: `no leaks found`; 35 commit `97c1a5d^..bfe821d` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home; wheel không chứa `/home/…`, PAT hay token |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor, UI (`hibiscus-station-web@1.0.0a1`), image (`VERSION=1.0.0a1`) cùng `1.0.0a1`; README / README.vi / hướng dẫn chỉ dùng liên kết `…/download/v1.0.0a1/…`, không còn `releases/latest`; CHANGELOG `[Unreleased]` ghi các thay đổi của 1.0.0a1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/user` trống, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin`. Hai chuỗi STS3215
giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy) do một tiến trình riêng của QC phục vụ; tiến
trình này không giữ phía slave của pty (cổng USB thật không có ai giữ khi chương trình đã tắt) và đếm mọi lệnh nhận
được. `robots.yaml` có hồ sơ `desk` (`so101_follower` / `so101_leader` trên hai pty). Tệp hiệu chỉnh LeLab ở
`…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy một lần ở `127.0.0.1:18511` rồi tắt
bằng Ctrl+C (SIGINT).

Ghi chú về giả lập: sau `kill -9` Station, pty vẫn giữ cờ độc quyền (TIOCEXCL) nên mở lại báo `EBUSY` dù không tiến
trình nào giữ (đã kiểm `/proc/*/fd`). Cổng USB thật xoá cờ này khi đóng lần cuối, nên đây là giới hạn của pty, không
phải lỗi Station; QC dựng lại cặp pty mới cho các bước sau.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Robot profiles:
  desk (active): cameras []
    follower: so101_follower on /dev/pts/10, calibration 'desk_follower' in LeLab's folder (so101_follower), not used by Station yet
    leader: so101_leader on /dev/pts/11, calibration 'desk_leader' MISSING

Running Station:
  Station is not running

Motor check (read only):
  desk follower on /dev/pts/10: ids answering at 1 Mbps {'1': 777, '2': 777, '3': 777, '4': 777, '5': 777, '6': 777}
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status [] protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
        -> fw 3.10 model 777 temperature raw 30 = 30.0 C (max limit 70 C) voltage raw 50 = 5.0 V current raw 12 = 0.078 A load raw 0 = 0.0 % status raw 0 []
    sync read: 0/20 failed, 0.8 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~3.1 ms
    motors carry the calibration of: ['…/robots/so101_follower/desk_follower.json']
…
The last log line is in the zip.
```

Lệnh giả lập nhận: `follower {'read': 144, 'sync_read': 20} writes= 0`, `leader {'read': 144, 'sync_read': 20} writes= 0`.
QD-10 (một câu nhất quán về tệp LeLab), QD-12 (không có `DEBUG root: Detected …`) đã đóng.

Khi Station đang chạy và đã kết nối (QD-11): `pid 2144537: mode real, state idle`, `follower: not calibrated (no
calibration file …), bus errors 0`; không còn `None` / `False`. Lượt chạy với một dòng log in "The last log line is
in the zip."; với ba dòng, "The last 3 log lines are in the zip.".

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi trường `HF_TOKEN=hf_QCr2…`,
`GITHUB_TOKEN=ghp_QCr2…`. Zip chứa `report.txt, report.json, robots.yaml, sessions/s-qc.json, station.log.tail`
(không có `token`, `server.json`). Kết quả (zip / stdout):

```
local token   files=0 stdout=0
PAT secret    files=0 stdout=0
full PAT      files=0 stdout=0
PAT 8-char id files=0 stdout=0
HF token      files=0 stdout=0
GitHub token  files=0 stdout=0
hbp_ còn lại: 'hbp_QcR2…' (report.json, station.log.tail, sessions/s-qc.json)
```

Lượt chạy với HOME của người dùng giả: zip có thêm `calibration/follower/…`, `calibration/leader/…` như hướng dẫn nói.

### 3.4 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` (Playwright Chromium, chỉ bấm chuột / phím như người dùng) với **tệp chạy
`hibiscus-station` của bản cài** (môi trường Python ảo chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`) và giao diện tĩnh lấy từ **wheel đã cài**
(`site-packages/hibiscus_station/static`): `3 passed in 147.10s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối →
hiệu chỉnh follower (Đặt home → Biên độ 6 / 6 → Lưu) → leader → Kiểm tra (lệch 0.0) → camera → teleop → dừng an toàn
(nhiệt / Space e-stop) → ghi 2 tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop → Chương trình. QC đã xem ảnh
chụp (sáng / tối, vi / en): số đo hợp lý với giả lập (30 °C, 5.0 V, 0.08 A, 0 %), nhãn đúng ngôn ngữ; điểm còn thấy
là D-5 (M1).

Thêm: `hibiscus-station --mock` của bản cài với HOME trống tạo dữ liệu ở `~/.hibiscus/station-demo` (đúng README),
`hibiscus-station health` báo `healthy: hibiscus-station 1.0.0a1 state=disconnected`.

## 4. Bộ test tự động (QC tự chạy, Linux, worktree sạch ở `bfe821d`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `613 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 507.07s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 146.30s` (`mock-en`, `mock-vi`, `sts-vi`) |
| e2e trên bản cài (§3.4) | `3 passed` |

### 4.1 Kiểm fail-trước-pass-sau (QD-1 – QD-15)

Mỗi commit sửa: chạy các test mà commit đó thêm / sửa trên mã của **commit cha** (chỉ chép tệp `tests/` của commit
sửa) và trên **commit sửa**; `hibiscus_station` được nạp từ đúng cây đó (đã kiểm `__file__`).

| QD | Commit sửa | Trên commit cha | Trên commit sửa |
|---|---|---|---|
| QD-1 | `ebd89eb` (1.0.0a1, liên kết) | `11 failed, 1 passed` (`'0.2.8' == '1.0.0a1'`, …) | `12 passed` |
| QD-1 | `16d88bc` (tag image) | `1 failed, 2 passed` | `3 passed` |
| QD-1 | `90e8b03` (ghi chú phát hành pre-release) | `1 failed, 8 passed` | `9 passed` |
| QD-2 | `764e63a` (`--color never`) | `1 failed, 1 passed` (`test_installer_reads_uv_output_without_colour`) | `2 passed` |
| QD-3 | `92bb050` (camera đọc mới khi bắt đầu phiên) | `1 failed, 1 passed` (`StationError: a configu…`) | `2 passed` |
| QD-3 | `8baa527` (socket trình duyệt đóng) | `1 failed, 4 passed` | `5 passed` |
| QD-8 | `c7ea109` (`--mock` với home của image) | `2 failed, 1 passed` | `3 passed` |
| QD-10 | `9ba86d1` | `2 failed, 2 passed` | `4 passed` |
| QD-11 | `64f7a3b` | `4 failed, 2 passed` (`'None'`) | `6 passed` |
| QD-12 | `3a18bca` | `1 failed, 1 passed` (`Detected pyserial vers…`) | `2 passed` |
| QD-13 | `87794ff` | `2 failed, 1 passed` (`no real arm … --no-ping`) | `3 passed` |
| QD-14 | `0d40dca`, `6ca7b54` | `2 failed, 1 passed`; `3 failed` | `3 passed`; `3 passed` |
| QD-15 | `d222083` | `7 failed, 2 passed` | `9 passed` |

Lỗi chỉ có trên CI (bằng chứng là lượt CI đỏ 44034901039 và các lượt sửa sau đó, nay xanh ở 44054326182):
QD-4 (doctor trên Windows: `0a33aa8`, `e248a37`; nay pytest windows không còn skip module `test_doctor`),
QD-5 (`20b85c6`, `68d36a8`: đếm lần đọc bus theo từng nhịp; đổi `> 100` nhịp thành `> 20` nhưng vẫn kiểm **mọi**
nhịp `≤ 2` lần đọc; commit ghi đã tái hiện bằng đồng hồ 15.6 ms trên Linux và test bắt được khi sửa đổi mã đọc 2 lần),
QD-6 (`8f1cabd`: fixture hiệu chỉnh xác định, ngưỡng `> 20.0` giữ nguyên; trên máy QC test xanh ở cả hai phía, đúng như
lỗi chỉ phụ thuộc tốc độ máy), QD-7 (`7b0596b`, `183e7fd`, `d4197a0`; macOS `584 passed, 6 skipped`, skip có trong
danh sách), QD-9 (`689fa6c`, `879395b`, `6ff382c`; job e2e Firefox / Edge thật sự dùng `HIBISCUS_E2E_BROWSER`).

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-15 (lần 1)

| QD | Trạng thái | Kiểm lại |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (§2 vệ sinh phát hành); trình cài: "Đây là bản thử nghiệm (pre-release)… Quay lại bản này sau khi cập nhật: irm …/releases/download/v1.0.0a1/install.ps1 \| iex" |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, so thư viện 100 %, smoke `--mock` |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows: không còn `SKIPPED … tests\test_doctor.py`; skip đều trong danh sách |
| QD-5 | Đóng | pytest windows xanh |
| QD-6 | Đóng | pytest linux CI xanh; QC local xanh |
| QD-7 | Đóng | pytest macos xanh, 5 skip pty có lý do macOS trong danh sách (ghi chú §6) |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 |
| QD-11 | Đóng | §3.2 (`None` / `False` / số nhiều); xem QD-16 cho dạng dict / list còn lại |
| QD-12 | Đóng | §3.2 |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 trong §2 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị. Lỗi nào cũng chặn PASS.

**QD-16 · Low · F-63 (AT-77, quy chuẩn "thông tin đúng": không có chữ máy) · Thân báo cáo `doctor` còn in dict / list Python.**
Bước: hồ sơ `desk` có hai tay thật, không camera; tệp hiệu chỉnh của profile có ở `so_follower` / `so_leader`; Station
tắt; `hibiscus-station doctor --no-cameras`.
Kỳ vọng: báo cáo không có giá trị Python thô (cùng tinh thần QD-11, test của chính bản sửa có tên
`test_report_has_no_python_values…`), ví dụ `cameras: none`, `ids answering at 1 Mbps: 1-6 (model 777)`,
`calibration file vs motors: all 6 match`, `motors carry the calibration of: …/desk_follower.json`.
Thực tế:
```
  desk (active): cameras []
  demo_so101 (active): cameras ['front', 'wrist']
  desk follower on /dev/pts/10: ids answering at 1 Mbps {'1': 777, '2': 777, '3': 777, '4': 777, '5': 777, '6': 777}
    calibration file vs motors: {'shoulder_pan': 'match', 'shoulder_lift': 'match', 'elbow_flex': 'match', 'wrist_flex': 'match', 'wrist_roll': 'match', 'gripper': 'match'}
    motors carry the calibration of: ['…/so_follower/desk_follower.json', '…/so101_follower/desk_follower.json']
```
(`hibiscus_station/doctor.py` dòng 890, 968, 1002, 1004.) Báo cáo được hướng dẫn mô tả là "bằng tiếng Anh (dành
cho kỹ sư)"; nếu nhóm cho rằng dạng này chấp nhận được, BA đưa cho khách quyết (CR / miễn trừ), QC không tự miễn.

**QD-17 · Low · F-1 / P-1 (AT-1, quy chuẩn "thông điệp rõ") · Trình cài Windows in cảnh báo của uv bảo người dùng tự sửa PATH.**
Bước: Windows chưa từng cài uv / Station (job CI `windows (install.ps1 without git …)`, lượt 44054326182, job
133942100604), dán lệnh cài.
Kỳ vọng: chỉ có thông điệp của trình cài (song ngữ); vì trình cài tự chạy `uv tool update-shell`, người dùng không
được bảo làm thêm gì ngoài "Mở cửa sổ PowerShell mới rồi gõ: hibiscus-station".
Thực tế, ngay trước dòng "Xong", màu vàng, chỉ tiếng Anh:
```
Installed 1 executable: hibiscus-station
warning: `C:\Users\runneradmin\.local\bin` is not on your PATH. To use installed tools, run `$env:PATH = "C:\Users\runneradmin\.local\bin;$env:PATH"` or `uv tool update-shell`.

[Hibiscus Station] Xong: hibiscus-station 1.0.0a1. Mở cửa sổ PowerShell mới rồi gõ: hibiscus-station
```
Cùng dòng xuất hiện trong dry run PowerShell 7 của QC. Lần cài đầu trên máy sạch nào cũng gặp; người mới có thể làm
theo cảnh báo (dán lệnh lạ) hoặc nghĩ việc cài bị lỗi.

## 6. Ghi chú (không phải lỗi M0)

* **macOS (bản xem trước, không có AT):** job `python (macos)` xanh sau khi CI tắt gộp bộ hẹn giờ của VM
  (`sysctl kern.timer.coalescing_enabled=0`) và thêm địa chỉ loopback `127.0.0.2`; ngưỡng thời gian của test giữ nguyên.
  Máy Mac của người dùng mặc định bật gộp bộ hẹn giờ, nên nhịp điều khiển trên Mac thật **chưa được chứng minh**
  (VM CI trước khi tắt: vòng `sleep(1/30)` chỉ ~14 Hz). Ghi để BA biết khi macOS rời trạng thái xem trước.
* **AT-2 ghi "windows-latest (pytest, build wheel, …)":** wheel phát hành (thuần Python, `py3-none-any`) được build một
  lần trên Linux rồi chính tệp đó được cài trên Windows (đúng tệp người dùng cài); CI không build wheel trên Windows.
  QC coi phần người dùng thấy là đạt; đề nghị BA sửa câu chữ AT-2 cho khớp ("cài wheel phát hành") khi khách duyệt lần sau.
* e2e Firefox / Edge chạy luồng chính `test_station_ui.py`; ma trận ảnh + axe chỉ chạy Chromium. AT-2 không yêu cầu
  ma trận ảnh trên mọi trình duyệt.
* Chưa có bản nháp (draft pre-release) `v1.0.0a1` trên GitHub, nên dòng `irm …/releases/download/v1.0.0a1/install.ps1 | iex`
  trong README hiện trả 404 cho người ngoài. Theo ACCEPTANCE (Môi trường), bản ứng viên được phát hành nháp trước UAT;
  việc này làm sau khi QC PASS.
* Đề nghị lần 1 cho BA vẫn còn: sửa câu chữ AT-77 bước 2 thành "không có PAT đầy đủ; chỉ dạng che `hbp_xxxx…`".
* Danh sách cổng của `doctor` trống với pty (`(none) - is the arm's USB cable plugged in?`): đúng hành vi (pyserial không
  liệt kê pty).

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QD-17 đã sửa và QC chạy lại.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | FAIL (QD-16); mọi bước AT-77 [Vendor] đạt |
| F-1 phần M0 (P-1) | FAIL (QD-17); CI Windows 5.1 không git PASS; VM Windows 11 sạch: NOT VERIFIED |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | FAIL (QD-17) |
| AT-2 / nền kiểm CI | PASS |

QC chạy lại cổng M0 trên commit mới khi QD-16, QD-17 đã có bản sửa kèm test fail-trước-pass-sau.

Máy chủ QC đã khởi động (`127.0.0.1:18510`, `18511`, `18512`, `18513`, e2e trong `18514`–`18529`) và bộ giả lập đều đã dừng.
