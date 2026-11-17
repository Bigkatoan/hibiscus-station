# QC M0 lần 6: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-21 của [lần 5](QC-M0-r5.md) đã sửa đúng: lượt CI của đúng commit ứng viên **xanh 12 / 12**;
trên bản cài, động cơ không trả lời (cả tay follower, chỉ gripper, cả tay leader, cả hai tay) **không còn** bị báo
"slow bus", không còn lời khuyên bỏ hub / chỉnh latency timer và không còn ước lượng teleop từ lần đọc thất bại; bộ
chuyển chậm thật vẫn được báo "slow bus". QD-1 – QD-20 vẫn đóng. Wheel, sdist, `install.ps1`, `constraints.txt` QC tự
build **trùng byte** với CI; mọi bước AT-77 [Vendor] đạt trên bản cài; **0 lệnh ghi động cơ** qua 21 lượt `doctor` có
đếm lệnh. Nhưng QC tìm thêm **1 lỗi mới mức Low** (QD-22), sinh ra từ chính dòng chữ của bản sửa QD-21: khi bus **mất
gói ngẫu nhiên** (cả 6 động cơ đều trả lời ping), báo cáo ghi `teleop estimate: not measured (some motors did not
answer)` (người dùng hiểu là có động cơ chết, trong khi dòng ngay trên ghi `ids answering … 1-6`), và LIKELY PROBLEMS
không nêu gì dù 5 / 20 lần đọc thất bại, 18 lỗi bus. Theo quy tắc không lỗi (zero-defect): **F-1 / P-1 phần M0 đạt**,
**phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-22). Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `83c301e97d2d201f4f5d58d99766e72910d498a6` (HEAD trên origin lúc QC bắt đầu, 19:23, và lúc kết thúc, 19:53) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44082637692 (push `release/v1`, `head_sha` = `83c301e9…`, lần chạy 1) → **success, 12 / 12 job xanh** (QC chờ tới khi lượt chạy xong, 19:37, rồi mới kết luận) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `907f51813d4f4f8634c093e9f5607c8c2517cd99420378a88bd009fe2e7350b1`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `59d8b44e340efea6f8d8ce8a2243c30d42f92168fbefcb6738e0037a5ed70ea5`, 282 mục, 0 mục `node_modules` / `tests/`: **trùng byte** với sdist của CI |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git: 709 / 709 tệp cùng nội dung theo `diff -r`, chỉ khác giờ / quyền trong zip, như lần 3 – 5), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `pnpm install --frozen-lockfile` + `pnpm build`, `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty, có đếm lệnh) |

Kết quả dry run (trích):

```
== 1b. verify the assets (checksums; resolved set == uv.lock on Windows x64, Linux x86_64, macOS arm64)
x86_64-pc-windows-msvc: 91 packages, identical to uv.lock
x86_64-unknown-linux-gnu: 114 packages, identical to uv.lock
aarch64-apple-darwin: 90 packages, identical to uv.lock
release assets of 1.0.0a1 OK
== 2. install (no git on PATH, empty home)
[Hibiscus Station] Đang cài Hibiscus Station 1.0.0a1. Lần đầu có thể mất 5 – 15 phút (tải khoảng 1 GB).
[Hibiscus Station] Thư mục lệnh <dry-run>/home/.local/bin đã được thêm vào PATH (cửa sổ PowerShell mới sẽ thấy lệnh hibiscus-station).
                   The command folder <dry-run>/home/.local/bin is now on your PATH (a new PowerShell window finds hibiscus-station).
…
[Hibiscus Station] Xong: hibiscus-station 1.0.0a1. Mở cửa sổ PowerShell mới rồi gõ: hibiscus-station
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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-22) | Mọi bước AT-77 đạt trên bản cài (§3); lỗi mới QD-22 khi bus mất gói ngẫu nhiên (§3.7, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô 0–4, 13–15, 56–70; không có dòng `DEBUG` khi bus không lỗi |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR6…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong cả 21 lượt doctor có đếm lệnh |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | Nhà demo do `--mock` của bản cài tạo: `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`, `! no profile for a real arm: Robot > New robot, pick the arm's serial port`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`; số lệnh giả lập nhận không đổi; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2602533 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong stdout và `report.txt` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2604582: …/hibiscus-station: close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2602533, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`, `calibration file vs motors: all 6 match` (2 tay); tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` |
| **QD-21** động cơ không trả lời (một servo, cả tay, cả hai tay) | **PASS** | §3.6 |
| Bus mất gói ngẫu nhiên (cả 6 động cơ trả lời) | **FAIL** (QD-22) | §3.7 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44082637692: pytest linux `621 passed, 1 skipped`, windows `590 passed, 6 skipped`, macos `590 passed, 6 skipped` (thêm test QD-21, chạy và xanh trên cả 3 nền tảng), mỗi job `skips on <os>: all in the published list`; e2e linux Chromium `7 passed`, linux Firefox `3 passed`, windows Edge `2 passed, 1 skipped` (STS cần pty, có trong danh sách); cài Windows + `--mock` smoke; macOS cài smoke; image; web; deploy; release assets |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: `The command folder C:\Users\runneradmin\.local\bin is now on your PATH …`, `installed: 92 packages; tested set: 91` / `OK: 100 % identical to the tested set`, `hibiscus-station 1.0.0a1`, `healthy: hibiscus-station 1.0.0a1 state=disconnected`. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính bằng chuột trên **bản cài** (§3.5): `3 passed` (hai lượt) |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test + giả lập bộ chuyển chậm) · chạy thật NOT VERIFIED | §3.6: bộ chuyển chậm thật (trả lời trễ 20 ms) vẫn được báo `slow bus (20.46 ms per read)` với lời khuyên "only if the adapter is an FTDI chip (USB VID 0403)"; không có bộ chuyển WCH |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.5) + CI linux; Windows Edge `mock-vi` xanh |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng + local: `all in the published list` |
| FL-12 dry run phát hành | **PASS** | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.5. Điểm thấy được vẫn là D-5 (M1), không ghi lại |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows: `healthy` sau `--mock` |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3 – 5 (ghi chú §6) |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-22) | Không có dict / list / `None` / `True` / `False` / `Traceback` trong 23 stdout QC lưu và 24 `report.txt` trong zip, trừ thông điệp lỗi gốc của lerobot sau `last error:`; `report.json` ghi `ms_per_read: null` khi không lần đọc nào thành công (đúng kiểu JSON); giờ tệp hiệu chỉnh đúng giờ máy kèm múi giờ ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` trên cây của commit: `no leaks found`; 2 commit mới `f34094d..83c301e` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật; wheel và sdist không chứa `/home/…`, email hay PAT |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục QD-21 ("A motor that does not answer is no longer reported as a slow USB adapter") |
| Vệ sinh phát hành: nội dung tài sản phát hành | PASS | §1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r6/user` trống, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin` (không đặt `TZ`,
nên dùng múi giờ của máy). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy)
do một tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty (như bộ chuyển USB thật, không ai giữ)
và đếm **mọi** lệnh nhận được (`ping`, `read`, `write`, `sync_read`, `sync_write`). Lần này bộ giả lập của QC có thêm
ba kiểu lỗi: servo **chết** (không trả lời gói nào: `dead`), bus **mất gói ngẫu nhiên** (`drop_rate` của giả lập, giống
cáp lỏng / nhiễu / sụt áp) và bộ chuyển **trả lời trễ** (`latency_s`, giống bộ chuyển chậm thật). Hồ sơ `desk`
(`so101_follower` / `so101_leader` trên hai pty); tệp hiệu chỉnh LeLab ở
`…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy ở `127.0.0.1:18651` để tạo token rồi
tắt bằng SIGINT (như Ctrl+C). Như các lần trước: sau `kill -9` pty còn cờ TIOCEXCL nên mở lại báo `EBUSY` (cổng USB
thật xoá cờ khi đóng lần cuối); QC dựng lại cặp pty mới cho bước 6.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-17 19:25:37 +0700
$ ls -l desk_follower.json              -> 2026-11-17 19:25:08 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Calibration files:
  follower desk_follower            so101_follower  2026-11-17 19:25:08 UTC+07:00  …/robots/so101_follower/desk_follower.json
…
Motor check (read only):
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.6 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
    motors carry the calibration of: …/robots/so101_follower/desk_follower.json
```

Lệnh giả lập nhận trong lượt này: follower `ping 1, read 144, sync_read 20`, leader như vậy, **write 0, sync_write 0**.

Khi Station đang chạy và đã kết nối (`POST /api/v1/robots/desk/connect` với `X-Station: 1` như giao diện, `200`):
`pid 2602533: mode real, state idle`, `connected profile desk (real arms)`, `follower: calibrated, bus errors 0`; hai
cổng `skipped, in use by Station (pid 2602533); stop it to ping the motors`; mục **WHAT TO SEND / CẦN GỬI GÌ** có câu
"The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi của giả lập chỉ tăng lúc Station kết
nối (69 / 36), không tăng trong lượt doctor (trước 69 / 36, sau 69 / 36).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` (mới sinh cho lần này) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi
trường `HF_TOKEN=hf_QCr6…`, `GITHUB_TOKEN=ghp_QCr6…`. Zip chứa `report.txt, report.json, station.log.tail,
robots.yaml, calibration/follower/so101_follower/desk_follower.json, sessions/s-qc.json`. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
hbp_ còn lại: 'hbp_QcR6…' (station.log.tail, report.json, sessions/s-qc.json)
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_QcR6… used"
```

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`ls -l`: `2026-11-17 19:25:08 +0700`), `doctor --no-ping --no-cameras`, so với tên zip của chính lượt đó:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-17 19:25:08 UTC+07:00` | `…-20261117-193010.zip` |
| `UTC` | `2026-11-17 12:25:08 UTC+00:00` | `…-20261117-123010.zip` |
| `Asia/Kolkata` | `2026-11-17 17:55:08 UTC+05:30` | `…-20261117-180011.zip` |
| `America/St_Johns` | `2026-11-17 08:55:08 UTC-03:30` | `…-20261117-090012.zip` |
| `Pacific/Chatham` | `2026-11-18 02:10:08 UTC+13:45` | `…-20261118-021513.zip` (qua ngày) |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (môi trường ảo của test chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`; QC thấy tiến trình Station của e2e chạy bằng
`<dry-run>/home/.local/share/uv/tools/hibiscus-station/bin/python`, cả `--mock` lẫn bus giả lập STS) và giao diện tĩnh
lấy từ **wheel đã cài** (`site-packages/hibiscus_station/static`): `3 passed in 152.11s` rồi lượt thứ hai
`3 passed in 141.45s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối → hiệu chỉnh follower → leader → Kiểm tra →
camera → teleop → dừng an toàn (nhiệt / Space e-stop) → ghi tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop →
Chương trình. QC đã xem ảnh chụp (48 ảnh, sáng / tối, vi / en): số đo hợp lý với giả lập (STS: 30 °C, 5.0 V, 0.08 A,
0 %; mock teleop 243.9 / 250 FPS, vòng lặp p95 3.8 ms, độ trễ ~4 ms), nhãn đúng ngôn ngữ, e-stop khoá các bước.

### 3.6 Động cơ không trả lời và bộ chuyển chậm (QD-21)

Cùng bản cài, `doctor --no-cameras`, Station tắt:

| Tình huống | LIKELY PROBLEMS (trích) | Motor check (trích) |
|---|---|---|
| Follower chưa cấp điện (6 servo im) | chỉ `! desk follower: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power? cable?)` | `ids answering at 1 Mbps: none` · `sync read: 20/20 failed, no read succeeded` · `teleop estimate: not measured (some motors did not answer)` |
| Chỉ servo 6 (gripper) im | chỉ `! desk follower: motor id(s) 6 do not answer (power? cable?)` | `ids answering at 1 Mbps: 1-5` · `sync read: 20/20 failed, no read succeeded` · `teleop estimate: not measured …` |
| Leader chưa cấp điện | chỉ `! desk leader: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power? cable?)` | leader `20/20 failed, no read succeeded`; follower `0/20 failed, 0.59 ms each`, `~250 Hz` |
| Cả hai tay chưa cấp điện | hai dòng `… do not answer (power? cable?)`, không gì khác | hai tay `20/20 failed, no read succeeded`, `not measured` |
| Đối chứng: bộ chuyển chậm thật (follower trả lời trễ 20 ms, cả 6 servo trả lời) | `! desk follower on /dev/pts/8: slow bus (20.46 ms per read): slow USB adapter / hub: plug the arm straight into the PC, without a hub; only if the adapter is an FTDI chip (USB VID 0403): …` | `sync read: 0/20 failed, 20.46 ms each` · `teleop estimate: ~36 Hz, leader -> follower latency ~41.6 ms  ! slow bus …` |

Không lượt nào có "slow bus", "latency timer" hay ước lượng Hz khi có động cơ im. `report.json`:
`{'reads': 20, 'failed': 20, 'ms_per_read': None}` (JSON `null`), `teleop_estimate: null`. 0 lệnh ghi trong cả 5 lượt.
**QD-21 đóng.**

### 3.7 Bus mất gói ngẫu nhiên (QD-22)

Cùng bản cài, follower có cả 6 servo trả lời nhưng giả lập bỏ ngẫu nhiên một phần câu trả lời (`drop_rate` 1 % và
5 %, hạt giống cố định), như cáp lỏng ở một khớp, nhiễu, hoặc nguồn sụt khi động cơ chạy:

| Tỉ lệ mất | LIKELY PROBLEMS | Motor check của follower (trích) |
|---|---|---|
| 1 % | chỉ hai dòng hiệu chỉnh (không có gì về bus) | `ids answering at 1 Mbps: 1-6` · `sync read: 1/20 failed, 0.86 ms each` · **`teleop estimate: not measured (some motors did not answer)`** · `bus errors: 3, 2 retried ok …` |
| 5 % | chỉ hai dòng hiệu chỉnh (không có gì về bus) | `ids answering at 1 Mbps: 1-3, 5-6` (id 4 vẫn có dòng thanh ghi đầy đủ ngay dưới) · `sync read: 5/20 failed, 2.0 ms each` · **`teleop estimate: not measured (some motors did not answer)`** · `bus errors: 18, 7 retried ok …` |

Đối chứng với bản lần 5 (`f34094d`, trước bản sửa QD-21) trên cùng bus, cùng hạt giống: `1/20 failed, 0.84 ms each` →
`~250 Hz`; `5/20 failed, 4.34 ms each` → `~162 Hz`; LIKELY PROBLEMS cũng không nêu gì. Như vậy câu "some motors did
not answer" là chữ mới của bản sửa QD-21, còn việc LIKELY PROBLEMS bỏ qua bus mất gói có từ trước (QC lần 1 – 5 chưa
thử tình huống này). Ở tỉ lệ 5 %, stdout còn in 3 dòng log `WARNING hibiscus_station.hw.bus: bus error on /dev/pts/8
after 2 tries: …` giữa các dòng tiến độ (cả bản lần 5 cũng vậy). 0 lệnh ghi.

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `83c301e`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `621 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách; gồm test mới `test_a_silent_motor_is_not_reported_as_a_slow_bus`) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 507.82s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 147.96s` |
| e2e trên bản cài (§3.5) | `3 passed in 152.11s`, `3 passed in 141.45s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng).

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-21

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (`check_versions.py`, `--version`, health, doctor) |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, thư viện 100 %, smoke `--mock`; dry run PowerShell 7 không git |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows `590 passed`, không skip module `test_doctor` |
| QD-5 | Đóng | Test nhịp đọc bus xanh trên Windows |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | pytest macos `590 passed, 6 skipped`, skip có trong danh sách |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`) |
| QD-12 | Đóng | §3.2: không có dòng `DEBUG` khi bus không lỗi |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | Đóng | Không còn giá trị Python trong 47 báo cáo; `ms_per_read` rỗng hiện là `no read succeeded`, không phải `None` |
| QD-17 | Đóng | Dry run PowerShell 7 + CI Windows PowerShell 5.1: không còn cảnh báo PATH của uv; dòng PATH song ngữ |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ, có múi lệch 30 / 45 phút và qua ngày) |
| QD-20 | Đóng | §1: sdist build sau `pnpm install` chỉ có gói (282 mục), trùng byte với CI |
| QD-21 | **Đóng** | §3.6: một servo im, cả tay follower im, cả tay leader im, cả hai tay im: không "slow bus", không ước lượng teleop; bộ chuyển chậm thật vẫn được báo; test mới xanh trên cả 3 nền tảng |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-22 · Low · F-63 (AT-77, FL-11; tính hợp lý của điều người dùng thấy) · Bus mất gói ngẫu nhiên: `doctor` nói "some
motors did not answer" dù cả 6 động cơ trả lời, và LIKELY PROBLEMS không nêu bus lỗi.**
Bước: hồ sơ có tay thật; cả 6 servo có điện và trả lời, nhưng bus mất một phần câu trả lời (cáp lỏng ở một khớp, nhiễu,
nguồn sụt); Station tắt; `hibiscus-station doctor --no-cameras` (QC: bản cài, giả lập STS với `drop_rate` 1 % và 5 %,
§3.7).
Kỳ vọng: chữ mô tả đúng điều đo được (ví dụ "x/20 reads failed: the bus loses answers") thay vì đổ cho động cơ không
trả lời; khi một phần đáng kể lần đọc thất bại hoặc có lỗi bus, LIKELY PROBLEMS có một mục chỉ ra bus chập chờn
(kiểm tra cáp giữa các servo, nguồn 5 / 12 V), vì teleop trên bus đó sẽ gặp lỗi đọc.
Thực tế: `ids answering at 1 Mbps: 1-6` rồi ngay dưới `teleop estimate: not measured (some motors did not answer)`;
ở 5 %: `sync read: 5/20 failed`, `bus errors: 18`, nhưng LIKELY PROBLEMS chỉ có hai dòng về tệp hiệu chỉnh. Người đọc
báo cáo (khách hoặc người hỗ trợ đọc zip) đi tìm động cơ chết không có, hoặc tin là bus ổn.
Nguyên nhân QC thấy: `hibiscus_station/doctor.py` `summary()` (khoảng dòng 1024–1027) in câu "some motors did not
answer" mỗi khi `failed > 0`, không phân biệt servo im hẳn (đã có mục `do not answer`) với lần đọc mất gói; `warnings()` (LIKELY PROBLEMS)
không có mục nào dựa trên `sync_read_present_position.failed` hay `bus_errors`. Phần thứ hai có từ trước bản sửa QD-21;
QC các lần 1 – 5 chưa thử bus mất gói (§6, rà lỗi lọt).

## 6. Ghi chú (không phải lỗi M0)

* **Rà lỗi lọt cho QD-22**: danh sách kiểm của QC cho `doctor` có "servo không trả lời" (từ lần 5) nhưng chưa có "bus
  mất gói ngẫu nhiên". Đã thêm vào cách kiểm của QC (§3.7, cùng đối chứng bộ chuyển chậm thật ở §3.6) và đề nghị BA thêm
  cả ba tình huống (servo im, bus mất gói, bộ chuyển chậm) vào danh sách hồi quy (REGRESSION) khi sửa.
* **Dòng log `WARNING hibiscus_station.hw.bus: …` in ra stdout** của `doctor` khi bus có lỗi, xen giữa các dòng tiến độ
  (§3.7; có từ trước). Không sai thông tin nhưng là chữ log thô; đề nghị gom vào mục `bus errors:` khi sửa QD-22.
* **Dòng thanh ghi có lỗi đọc nhúng nguyên thông điệp lỗi** (`limits 684-error: Failed to read 'Max_Position_Limit' …`)
  ở bus mất gói; có từ trước, vẫn đọc được.
* **Log CI của trình cài Windows vẫn hiện chữ Việt sai** (`Má»Ÿ cá»­a sá»• …`): `Get-Content` của PowerShell 5.1 đọc
  tệp UTF-8 bằng cp1252 (ghi chú lần 3 – 5, chưa đổi). Byte trình cài phát ra đúng.
* **Test của QD-19 không phủ dòng báo cáo** (ghi chú lần 4, 5, chưa đổi).
* **`verify_assets.py` không kiểm sdist khi thư mục không có sdist** (ghi chú lần 5, chưa đổi).
* **Dòng chương trình giữ cổng cắt ở 160 ký tự**: với đường dẫn rất dài của QC, tên chương trình bị cắt; như lần 3 – 5.
* **`lerobot-0.7.1-py3-none-any.whl` không tái lập byte** (như lần 3 – 5): nội dung giống hệt, chỉ khác giờ / quyền trong zip.
* **Cảnh báo `StarletteDeprecationWarning`** trong pytest của cả 3 nền tảng: chỉ ở môi trường test.
* **Dry run trong container in `warning: Failed to hardlink files`** của uv (bộ nhớ đệm gắn từ hệ tệp khác); không có
  trên Windows CI.
* Các ghi chú §6 của lần 2 – 5 còn nguyên: macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong
  README trả 404 cho người ngoài (phát hành nháp sau khi QC PASS), câu chữ AT-77 bước 2, danh sách cổng trống với pty,
  `hibiscus-station health` sau `kill -9` (F-65, M3), CHANGELOG dòng `cameras: front, wrist`, hai lượt doctor trong cùng
  một giây cho cùng tên zip.

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QC PASS.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong cửa sổ PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | **FAIL** (QD-22: bus mất gói ngẫu nhiên bị nói là "some motors did not answer", LIKELY PROBLEMS không nêu; QD-21 đã đóng; mọi bước AT-77 [Vendor] đạt trên bản cài; VID:PID / WCH thật NOT VERIFIED, UAT-0) |
| F-1 phần M0 (P-1) | **PASS** (AT-2 PASS; CI Windows 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED, UAT-0) |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | **PASS** (M0) |
| AT-2 / nền kiểm CI | PASS (12 / 12, lượt 44082637692) |

QC chạy lại cổng M0 trên commit mới khi QD-22 đã có bản sửa kèm test tự động (bus mất gói khi cả 6 động cơ trả lời:
chữ đúng điều đo được, LIKELY PROBLEMS có mục bus chập chờn; servo im vẫn không bị gọi là "slow bus"; bộ chuyển chậm
thật vẫn được báo), lượt CI của đúng commit đó xanh 12 / 12.

Máy chủ QC đã khởi động (`127.0.0.1:18650`, `18651`, e2e trong `18655` – `18669`) và bộ giả lập đều đã dừng.
