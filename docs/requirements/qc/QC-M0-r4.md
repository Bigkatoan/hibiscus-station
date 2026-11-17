# QC M0 lần 4: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-18 và QD-19 của [lần 3](QC-M0-r3.md) đã sửa đúng: lượt CI của đúng commit ứng viên
**xanh 12 / 12**, giờ của tệp hiệu chỉnh trong `doctor` hiện theo giờ máy kèm múi giờ (QC thấy trên bản cài, ở 4 múi
giờ). QD-1 – QD-17 vẫn đóng. Mọi bước AT-77 [Vendor] đạt trên bản cài, 0 lệnh ghi động cơ qua 13 lượt `doctor`.
Nhưng QC tìm thêm **1 lỗi mới mức Low** về tài sản phát hành (QD-20): workflow `release.yml` build sdist
`hibiscus_station-1.0.0a1.tar.gz` sau `pnpm install` trong cùng job, nên sdist được đính vào bản phát hành sẽ chứa
**991 tệp LICENSE / README của bên thứ ba trong `web/node_modules`**; lượt CI mà QC so byte không build trong điều kiện
đó nên không thấy. Theo quy tắc không lỗi (zero-defect): **F-63 đạt**, **phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**;
**F-1 / P-1 phần M0 chưa đạt** (QD-20). Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `cca2a2b13e21a00443f563e557476fb26d018144` (HEAD trên origin lúc QC bắt đầu và lúc kết thúc) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44071549659 (push `release/v1`, `head_sha` = `cca2a2b1…`, lần chạy 1) → **success, 12 / 12 job xanh** (QC chờ tới khi lượt chạy xong rồi mới kết luận) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `69ad5acfc06766b36dda9671fdde209e8eef232b529c279aa9cd857146f1164e`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên; `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) cũng trùng byte |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git; chỉ khác giờ / quyền trong zip như lần 3), kéo theo `overrides.txt` và `SHA256SUMS`; `hibiscus_station-1.0.0a1.tar.gz` (sdist): **khác cả nội dung**, QC 1276 mục / 2 447 014 byte, CI 285 mục / 1 507 505 byte. 991 mục dư đều nằm dưới `web/node_modules/`, phần còn lại giống hệt: QD-20 |
| Cách build + cài | `git archive cca2a2b` vào thư mục trống → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: build UI + assets, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty) |

Kết quả dry run (trích):

```
== 2. install (no git on PATH, empty home)
[Hibiscus Station] Đang cài Hibiscus Station 1.0.0a1. Lần đầu có thể mất 5 – 15 phút (tải khoảng 1 GB).
[Hibiscus Station] Thư mục lệnh <dry-run>/home/.local/bin đã được thêm vào PATH (cửa sổ PowerShell mới sẽ thấy lệnh hibiscus-station).
                   The command folder <dry-run>/home/.local/bin is now on your PATH (a new PowerShell window finds hibiscus-station).
[Hibiscus Station] Đang cài thư viện (đúng bộ đã kiểm thử).
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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** | Mọi bước đạt trên bản cài (§3); QD-18, QD-19 đóng; không còn lỗi mở của F-63 |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô thanh ghi 0–4, 13–15, 56–70; không có dòng `DEBUG` |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR4…`. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong mọi lượt doctor (13 lượt, 2 lần dựng giả lập) |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`, `/dev/tty` (không `/dev/pts/8`, `/dev/pts/9`, `/dev/video*`); số lệnh giả lập nhận không đổi; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2405211 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong báo cáo |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2407185: python3 -c … : close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2405211, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`, `calibration file vs motors: all 6 match` (2 tay); tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44071549659: pytest linux `618 passed, 1 skipped`, windows `588 passed, 6 skipped`, macos `588 passed, 6 skipped`, mỗi job `skips on <os>: all in the published list`; e2e linux Chromium `7 passed`, linux Firefox `3 passed`, windows Edge `2 passed, 1 skipped` (STS cần pty, có trong danh sách); cài Windows + `--mock` smoke + MIME `.js`; macOS cài smoke; image; web; deploy. Log `python (windows)`: không còn cảnh báo `UnicodeDecodeError 'charmap'` |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: git gỡ khỏi PATH, Windows PowerShell 5.1, không có cảnh báo PATH của uv, dòng `The command folder C:\Users\runneradmin\.local\bin is now on your PATH …` trước khi cài; `installed: 92 packages; tested set: 91` / `OK: 100 % identical`; `hibiscus-station --version` = `1.0.0a1`; `healthy: hibiscus-station 1.0.0a1 state=disconnected`. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính bằng chuột trên **bản cài** (§3.4): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test) · chạy thật NOT VERIFIED | Test xanh trong bộ test đầy đủ; không có bộ chuyển WCH |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.4) + CI linux; Windows Edge `mock-vi` xanh |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng: `all in the published list` |
| FL-12 dry run phát hành | PASS cho wheel / trình cài · **FAIL** cho sdist (QD-20) | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.4. Điểm thấy được vẫn là D-5 (M1), không ghi lại |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows: `MOCK (demo) mode`, `healthy` |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3: log CI vẫn đọc tệp bằng cp1252 (`ThÆ° má»¥c lá»‡nh …`), giải mã ngược ra đúng `Thư mục lệnh …` (ghi chú §6) |
| Chữ của `doctor` (vi / en) | PASS | Không có dict / list / `None` / `True` / `False` trong 21 báo cáo (9 stdout QC lưu lại + 12 `report.txt` trong zip); giờ tệp hiệu chỉnh đúng giờ máy kèm múi giờ (QD-19, §3.2) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` (v8.30.1) trên cây của commit: `no leaks found`; 3 commit mới `2fc7739..cca2a2b` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home; wheel không chứa `/home/…`, PAT hay token |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor, UI cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục cho QD-19 với ví dụ đúng định dạng thật (`2026-11-17 17:35:15 UTC+07:00`) |
| Vệ sinh phát hành: nội dung tài sản phát hành | **FAIL** (QD-20) | §5.2 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r4/user` trống, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin` (không đặt `TZ`,
nên dùng múi giờ của máy). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy)
do một tiến trình riêng của QC phục vụ; tiến trình này không giữ phía slave của pty và đếm mọi lệnh nhận được.
`robots.yaml` có hồ sơ `desk` (`so101_follower` / `so101_leader` trên hai pty). Tệp hiệu chỉnh LeLab ở
`…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy một lần ở `127.0.0.1:18651` để tạo
token rồi tắt bằng Ctrl+C. Như lần 2, 3: sau `kill -9` pty còn cờ TIOCEXCL nên mở lại báo `EBUSY` (cổng USB thật xoá
cờ khi đóng lần cuối); QC dựng lại cặp pty mới cho bước 6.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt) và giờ của tệp hiệu chỉnh (QD-19)

```
$ date '+%F %T %z'                      -> 2026-11-17 18:12:30 +0700
$ ls -l desk_follower.json              -> 2026-11-17 18:12:12 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Calibration files:
  follower desk_follower            so101_follower  2026-11-17 18:12:12 UTC+07:00  …/robots/so101_follower/desk_follower.json
…
Motor check (read only):
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.83 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~3.1 ms
    motors carry the calibration of: …/robots/so101_follower/desk_follower.json
```

Lệnh giả lập nhận trong lượt này: `follower {'read': 144, 'sync_read': 20} writes= 0`, `leader {'read': 144, 'sync_read': 20} writes= 0`.
Zip `hibiscus-station-doctor-20261117-181232.zip`, `report.json`: `generated_at` `2026-11-17T18:12:30+0700`,
`modified_at` `2026-11-17T11:12:12.330311+00:00` (UTC, đúng), `report.txt` trong zip in `18:12:12 UTC+07:00` như stdout.

Cùng tệp, chạy `doctor --no-ping --no-cameras` với múi giờ khác (`TZ=…`), so với tên zip của chính lượt đó:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-17 18:12:12 UTC+07:00` | `…-20261117-181232.zip` |
| `UTC` | `2026-11-17 11:12:12 UTC+00:00` | `…-20261117-111249.zip` |
| `Asia/Kolkata` | `2026-11-17 16:42:12 UTC+05:30` | `…-20261117-164249.zip` |
| `America/St_Johns` | `2026-11-17 07:42:12 UTC-03:30` | `…-20261117-074249.zip` |

Khi Station đang chạy và đã kết nối (`POST /api/v1/robots/desk/connect` với `X-Station: 1` như giao diện):
`pid 2405211: mode real, state idle`, `connected profile desk (real arms)`, `follower: calibrated, bus errors 0`; hai
cổng `skipped, in use by Station (pid 2405211); stop it to ping the motors`; mục **WHAT TO SEND / CẦN GỬI GÌ** có câu
"The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi của giả lập chỉ tăng lúc Station kết
nối (69 / 102: Station ghi cấu hình và tệp leader lệch vào động cơ khi kết nối, đúng như cảnh báo của doctor), không
tăng trong lượt doctor (trước 69 / 102, sau 69 / 102).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` (mới sinh cho lần này) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi
trường `HF_TOKEN=hf_QCr4…`, `GITHUB_TOKEN=ghp_QCr4…`. Zip chứa `report.txt, report.json, robots.yaml,
sessions/s-qc.json, station.log.tail, calibration/follower/so101_follower/desk_follower.json`. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
hbp_ còn lại: 'hbp_QcR4…' (station.log.tail, report.json, sessions/s-qc.json)
station.log.tail: "token in log [local token removed]", "GET /auth?t=…", "cloud PAT hbp_QcR4… used"
```

### 3.4 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (môi trường Python ảo chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`; QC thấy tiến trình Station của e2e chạy từ
`<dry-run>/home/.local/share/uv/tools/hibiscus-station/…`) và giao diện tĩnh lấy từ **wheel đã cài**
(`site-packages/hibiscus_station/static`): `3 passed in 150.63s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối →
hiệu chỉnh follower → leader → Kiểm tra → camera → teleop → dừng an toàn (nhiệt / Space e-stop) → ghi tập → bộ dữ liệu
→ nạp model ACT → chạy model → e-stop → Chương trình. QC đã xem ảnh chụp (48 ảnh, sáng / tối, vi / en): số đo hợp lý
với giả lập (30 °C, 5.0 V, 0.08 A, 0 %; teleop 237.7 / 250 FPS, độ trễ ~3 ms; mock 28–34 °C, 7.4 V), nhãn đúng ngôn
ngữ, e-stop khoá các bước và hiện "I'm clear, reset" / "Relax (torque off)".

## 4. Bộ test tự động (QC tự chạy, Linux, worktree sạch ở `cca2a2b`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `618 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 504.83s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 143.49s` |
| e2e trên bản cài (§3.4) | `3 passed` |

Worktree vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng).

### 4.1 Kiểm fail-trước-pass-sau (QD-18, QD-19)

| QD | Commit sửa | Trước sửa | Sau sửa |
|---|---|---|---|
| QD-18 | `da7c260` (`tests/test_doctor.py`, `tests/test_release_tools.py`) | CI 44065407754 `python (windows)`: `1 failed` (`test_report_text_has_no_python_containers_anywhere[loop]`) + 2 cảnh báo `UnicodeDecodeError 'charmap'` | CI 44071549659 `python (windows)`: `588 passed, 6 skipped`, 0 cảnh báo `charmap` (đây là lỗi chỉ có trên Windows, nên bằng chứng là hai lượt CI) |
| QD-19 | `cca2a2b` (`hibiscus_station/doctor.py`, `tests/test_doctor.py`) | Cây `git archive da7c260` + `tests/test_doctor.py` của `cca2a2b`: `1 failed, 40 passed` (`test_calibration_file_times_are_local_with_their_offset`: `module 'hibiscus_station.doctor' has no attribute '_local_time'`) | Cây `git archive cca2a2b`: `41 passed`. `hibiscus_station` nạp từ đúng cây (đã kiểm `__file__`) |

Test của QD-19 chỉ kiểm hàm `_local_time`, không kiểm dòng **Calibration files** của báo cáo; QC kiểm dòng đó trực
tiếp trên bản cài (§3.2), nên không tính là lỗi, nhưng ghi để nhóm biết (§6).

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-19

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (`check_versions.py`, `--version`, health, doctor, UI) |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, thư viện 100 %, smoke `--mock` |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows `588 passed`, không skip module `test_doctor` |
| QD-5 | Đóng | Test nhịp đọc bus xanh trên Windows |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | pytest macos `588 passed, 6 skipped`, skip có trong danh sách |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`; "The last 4 log lines are in the zip.") |
| QD-12 | Đóng | §3.2 (không có `DEBUG`) |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | Đóng | Không còn giá trị Python trong 21 báo cáo; test của bản sửa xanh trên cả 3 nền tảng |
| QD-17 | Đóng | Dry run PowerShell 7 + CI Windows PowerShell 5.1: không còn cảnh báo PATH của uv; dòng PATH song ngữ đứng trước "Đang cài thư viện" |
| QD-18 | **Đóng** | §4.1; lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | **Đóng** | §3.2 (giờ máy + múi giờ, trùng `ls -l` và tên zip, ở 4 múi giờ), §4.1 |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-20 · Low · F-1 / P-1 (tài sản phát hành, FL-12, vệ sinh phát hành) · sdist của bản phát hành chứa tệp của `web/node_modules`.**
Bước: build tài sản phát hành như `.github/workflows/release.yml` làm: `cd web && pnpm install --frozen-lockfile &&
pnpm build`, rồi `tools/release/build_release.py --out …` trong cùng thư mục (QC: `dry_run.sh --out`, cũng build UI
rồi gọi `build_release.py`).
Kỳ vọng: `hibiscus_station-1.0.0a1.tar.gz` chỉ có mã của Station + UI đã build, giống sdist mà CI kiểm (285 mục).
Thực tế: 1276 mục, 2 447 014 byte (CI: 285 mục, 1 507 505 byte); 991 mục dư, toàn bộ là
`hibiscus_station-1.0.0a1/web/node_modules/.pnpm/<gói>/node_modules/<gói>/LICENSE` và `…/README.md` của thư viện JS bên
thứ ba; ngoài các mục đó hai sdist có cùng danh sách tệp. QC tái hiện cả trong một bản `git clone` sạch của
`release/v1` @ `cca2a2b` (có `.git`): thêm `web/node_modules/.pnpm/foo@1.0.0/node_modules/foo/{LICENSE,README.md}` rồi
`uv build --sdist` → hai tệp đó nằm trong sdist.
Nguyên nhân QC thấy: `pyproject.toml` `[tool.hatch.build.targets.sdist] include` có `"README.md"`, `"LICENSE"` không
neo về gốc, nên khớp mọi tệp cùng tên ở mọi thư mục; `node_modules/` chỉ bị bỏ qua trong `web/.gitignore`, còn hatch
chỉ đọc `.gitignore` ở gốc. Cùng nguyên nhân, sdist của CI cũng kéo theo `tests/contract/README.md`,
`tests/hil/README.md`, `web/public/blockly-media/README.md` (tests không thuộc sdist theo `include`).
Vì sao CI không thấy: job `release-assets` của `ci.yml` lấy `web/dist` từ artifact `web-dist`, không có `node_modules`;
còn `release.yml` (job đính tài sản vào bản nháp) chạy `pnpm install` trong cùng job. Nên tài sản mà QC so byte với CI
**không phải** tài sản sẽ được đính vào bản phát hành: wheel, `install.ps1`, `constraints.txt` trùng; sdist (và vì thế
`SHA256SUMS`) sẽ khác. Người dùng Windows không cài sdist, nhưng nó là tài sản công khai có trong `SHA256SUMS` của bản
phát hành mã nguồn mở. Đề nghị: neo các mục `include` về gốc (`"/README.md"`, `"/LICENSE"`, …) và thêm một kiểm trong
`verify_assets.py` (hoặc `dry_run.sh`) rằng sdist không có `node_modules` / chỉ có các đường dẫn cho phép.

## 6. Ghi chú (không phải lỗi M0)

* **Log CI của trình cài Windows vẫn hiện chữ Việt sai** (`ThÆ° má»¥c lá»‡nh …`): `Get-Content` của PowerShell 5.1
  đọc tệp UTF-8 bằng cp1252 (ghi chú lần 3, chưa đổi). Byte trình cài phát ra đúng. Đề nghị `Get-Content -Encoding UTF8`.
* **Test của QD-19 không phủ dòng báo cáo**: nếu sau này `summary()` thôi gọi `_local_time`, test vẫn xanh. Đề nghị
  thêm một dòng kiểm trong test báo cáo đầy đủ (`test_report_text_has_no_python_containers_anywhere`).
* **Định dạng giờ khác nhau trong cùng zip**: `report.txt` in `2026-11-17 18:12:12 UTC+07:00`, `report.json` có
  `generated_at` `2026-11-17T18:12:30+0700` và `modified_at` UTC ISO. Đều đúng và ghi rõ múi giờ; không gây hiểu sai.
* **`lerobot-0.7.1-py3-none-any.whl` không tái lập byte** (như lần 3): nội dung giống hệt, chỉ khác giờ / quyền trong zip.
* **Dry run trong container in `warning: Failed to hardlink files`** của uv (bộ nhớ đệm gắn từ hệ tệp khác); không có
  trên Windows CI.
* **`hibiscus-station health` sau `kill -9` in `unhealthy: ConnectError`** (F-65, M3, `not tested`): ghi để BA đưa vào QC M3.
* **Chương trình giữ cổng có dòng lệnh nhiều dòng** thì `doctor` in nguyên các dòng đó (như lần 3).
* CHANGELOG (dòng 56) vẫn trích `cameras: front, wrist`, báo cáo thật in `cameras front, wrist` (như lần 3).
* Hai lượt `doctor` trong cùng một giây vào cùng thư mục cho cùng tên zip, lượt sau ghi đè (QC gặp khi chạy liền 4 múi
  giờ bằng script); người dùng không chạy như vậy.
* Các ghi chú §6 của lần 2, 3 còn nguyên: macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong
  README trả 404 cho người ngoài (phát hành nháp sau khi QC PASS), câu chữ AT-77 bước 2, danh sách cổng trống với pty.

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QC PASS.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong cửa sổ PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | **PASS** (AT-77 [Vendor] đạt trên bản cài; QD-18, QD-19 đóng; VID:PID / WCH thật NOT VERIFIED, UAT-0) |
| F-1 phần M0 (P-1) | FAIL (QD-20: sdist của bản phát hành chứa `web/node_modules`); AT-2 PASS; CI Windows 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | FAIL (QD-20) |
| AT-2 / nền kiểm CI | PASS (12 / 12, lượt 44071549659) |

QC chạy lại cổng M0 trên commit mới khi QD-20 đã có bản sửa kèm kiểm tự động (sdist không có `node_modules`), lượt CI
của đúng commit đó xanh 12 / 12, và QC build sdist trong điều kiện của `release.yml` (có `web/node_modules`).

Máy chủ QC đã khởi động (`127.0.0.1:18650` – `18652`, e2e trong `18655` – `18662`) và bộ giả lập đều đã dừng.
