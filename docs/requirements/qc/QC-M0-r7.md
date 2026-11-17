# QC M0 lần 7: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-22 của [lần 6](QC-M0-r6.md) đã sửa đúng ở đúng tình huống đã báo: lượt CI của đúng commit
ứng viên **xanh 12 / 12**; trên bản cài, bus mất gói 1 % và 5 % khi cả 6 động cơ trả lời giờ có mục **`unreliable
bus`** trong LIKELY PROBLEMS, một dòng **`! N of 20 reads lost although every motor answers`** và vẫn có **ước lượng
tốc độ** (`~250 Hz`); lỗi checksum (`corrupt_rate` 1 %, 5 %) cũng được báo như vậy. QD-1 – QD-21 vẫn đóng (QD-21: động
cơ im không bị gọi là "slow bus"; bộ chuyển chậm thật vẫn được báo). Wheel, sdist, `install.ps1`, `constraints.txt`
QC tự build **trùng byte** với CI; mọi bước AT-77 [Vendor] đạt trên bản cài; **0 lệnh ghi động cơ** qua 31 lượt
`doctor` có đếm lệnh; luồng chuột `mock-en`, `mock-vi`, `sts-vi` trên bản cài `3 passed`. Nhưng QC tìm thêm **2 lỗi
mới mức Low**, cả hai ở chính phần chữ của bản sửa QD-22 khi bus lỗi nặng hơn hoặc lỗi kiểu khác:
**QD-23** (mọi lần đọc mất dù cả 6 động cơ trả lời ping: dòng cũ `teleop estimate: not measured (some motors did not
answer)` quay lại, mâu thuẫn với `unreliable bus: 20 of 20 reads got no answer although every motor answers` ở
LIKELY PROBLEMS) và **QD-24** (cùng một báo cáo nói `ids answering at 1 Mbps: 1-3, 5-6` rồi `although every motor
answers`; lỗi checksum bị gọi là "got no answer"). Theo quy tắc không lỗi (zero-defect): **F-1 / P-1 phần M0 đạt**,
**phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-23, QD-24). Bản này **chưa** được giao cho khách
làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `617be628b4e4b03a66cb32b3854b18dae6af5ba4` (HEAD trên origin lúc QC bắt đầu, 19:58, và lúc kết thúc, 20:42) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44088045317 (push `release/v1`, `head_sha` = `617be628…`, lần chạy 1) → **success, 12 / 12 job xanh** (QC chờ tới khi lượt chạy xong, 20:12, rồi mới kết luận) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `5766d272fbc7478e17731919ad920476a70ff733622674d5668a2c1a6ab7498f`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `0195df4f15182efaf49e0f29ddb9d42f16f16c2bb0498f623671ee345a9c5b0c`, 282 mục, 0 mục `node_modules` / `tests/`: **trùng byte** với sdist của CI |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git: 709 / 709 tệp cùng nội dung theo `diff -r`, chỉ khác giờ / quyền trong zip, như lần 3 – 6), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `pnpm install --frozen-lockfile` + `pnpm build`, `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty, có đếm lệnh, có `dead`, `drop_rate`, `corrupt_rate`, `latency_s`) |

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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-23, QD-24) | Mọi bước AT-77 đạt trên bản cài (§3); 2 lỗi mới khi bus lỗi nặng hơn / lỗi checksum (§3.7, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô 0–4, 13–15, 56–70; không có dòng `DEBUG` khi bus không lỗi |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR7…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong cả 31 lượt doctor có đếm lệnh |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | Nhà demo do `--mock` của bản cài tạo (Station mock ở `127.0.0.1:18652`, dừng bằng SIGINT, exit 0): `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`, `! no profile for a real arm: Robot > New robot, pick the arm's serial port`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`; số lệnh giả lập nhận không đổi; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2696580 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong stdout và `report.txt` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2700260: python3 -c … /dev/pts/8: close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2696580, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`, `calibration file vs motors: all 6 match` (2 tay); tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` |
| **QD-21** động cơ không trả lời (một servo, cả tay, cả hai tay) | **PASS** | §3.6 |
| **QD-22** bus mất gói 1 % / 5 %, lỗi checksum 1 % / 5 % (cả 6 động cơ trả lời) | **PASS** | §3.7 |
| Bus mất gói nặng (mọi lần đọc mất) / chữ khi bus lỗi | **FAIL** (QD-23, QD-24) | §3.7, §5.2 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44088045317: pytest linux `623 passed, 1 skipped`, windows `591 passed, 6 skipped`, macos `591 passed, 6 skipped` (có test QD-22 `test_a_bus_that_loses_answers_is_a_likely_problem`), mỗi job `skips on <os>: all in the published list`; e2e linux Chromium `7 passed`, linux Firefox `3 passed`, windows Edge `2 passed, 1 skipped` (STS cần pty, có trong danh sách); cài Windows + `--mock` smoke; macOS cài smoke; image; web; deploy; release assets |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: `installed: 92 packages; tested set: 91` / `OK: 100 % identical to the tested set`, `healthy: hibiscus-station 1.0.0a1 state=disconnected`. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính bằng chuột trên **bản cài** (§3.5): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test + giả lập bộ chuyển chậm) · chạy thật NOT VERIFIED | §3.6: bộ chuyển chậm (trả lời trễ 20 ms) được báo `slow bus (20.55 ms per read)` với lời khuyên "only if the adapter is an FTDI chip (USB VID 0403)"; không có bộ chuyển WCH |
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
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3 – 6 (ghi chú §6) |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-23, QD-24) | Không có dict / list / `None` / `True` / `False` / `Traceback` trong 31 stdout QC lưu và 35 `report.txt` trong zip, trừ thông điệp lỗi gốc của lerobot sau `last error:`; giờ tệp hiệu chỉnh đúng giờ máy kèm múi giờ ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` trên cây của commit (`git archive`): `no leaks found`; 2 commit mới `83c301e..617be62` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật; wheel và sdist không chứa `/home/…`, email hay PAT |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục QD-22 ("The doctor flags an unreliable bus") |
| Vệ sinh phát hành: nội dung tài sản phát hành | PASS | §1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r7/user` mới, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin` (không đặt `TZ`,
nên dùng múi giờ của máy). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy)
do một tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty (như bộ chuyển USB thật) và đếm **mọi**
lệnh nhận được (`ping`, `read`, `write`, `sync_read`, `sync_write`). Kiểu lỗi QC dựng được: servo **chết**
(`dead`), bus **mất gói ngẫu nhiên** (`drop_rate`), gói trả lời **sai checksum** (`corrupt_rate`, mới ở lần này) và
bộ chuyển **trả lời trễ** (`latency_s`). Hồ sơ `desk` (`so101_follower` / `so101_leader` trên hai pty); tệp hiệu chỉnh
LeLab ở `…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy ở `127.0.0.1:18651`, kết nối
`desk` qua `POST /api/v1/robots/desk/connect` (`X-Station: 1`, `200`) rồi bị `kill -9` cho bước 5. Như các lần trước:
sau `kill -9` pty còn cờ TIOCEXCL nên mở lại báo `EBUSY` (cổng USB thật xoá cờ khi đóng lần cuối); QC dựng lại cặp pty
mới cho bước 6.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-17 20:00:19 +0700
$ ls -l desk_follower.json              -> 2026-11-17 20:00:14 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Calibration files:
  follower desk_follower            so101_follower  2026-11-17 20:00:14 UTC+07:00  …/robots/so101_follower/desk_follower.json
…
Motor check (read only):
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.58 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
    motors carry the calibration of: …/robots/so101_follower/desk_follower.json
```

Lệnh giả lập nhận trong lượt này: follower `ping 1, read 144, sync_read 20`, leader như vậy, **write 0, sync_write 0**.

Khi Station đang chạy và đã kết nối: `pid 2696580: mode real, state idle`, `connected profile desk (real arms)`,
`follower: calibrated, bus errors 0`; hai cổng `skipped, in use by Station (pid 2696580); stop it to ping the motors`;
mục **WHAT TO SEND / CẦN GỬI GÌ** có câu "The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi
của giả lập chỉ tăng lúc Station kết nối (69 / 36), không tăng trong lượt doctor (trước 69 / 36, sau 69 / 36).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` (mới sinh cho lần này) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi
trường `HF_TOKEN=hf_QCr7…`, `GITHUB_TOKEN=ghp_QCr7…`. Zip chứa `report.txt, report.json, station.log.tail,
robots.yaml, calibration/follower/so_follower/desk_follower.json, calibration/follower/so101_follower/desk_follower.json,
calibration/leader/so_leader/desk_leader.json, sessions/s-qc.json`. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
hbp_ còn lại: 'hbp_QcR7…' (station.log.tail, report.json, sessions/s-qc.json)
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_QcR7… used"
```

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`ls -l`: `2026-11-17 20:00:14 +0700`), `doctor --no-ping --no-cameras`, so với tên zip của chính lượt đó:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-17 20:00:14 UTC+07:00` | `…-20261117-200700.zip` |
| `UTC` | `2026-11-17 13:00:14 UTC+00:00` | `…-20261117-130701.zip` |
| `Asia/Kolkata` | `2026-11-17 18:30:14 UTC+05:30` | `…-20261117-183702.zip` |
| `America/St_Johns` | `2026-11-17 09:30:14 UTC-03:30` | `…-20261117-093703.zip` |
| `Pacific/Chatham` | `2026-11-18 02:45:14 UTC+13:45` | `…-20261118-025203.zip` (qua ngày) |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (môi trường ảo của test chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`; tiến trình Station của e2e chạy bằng
`<dry-run>/home/.local/share/uv/tools/hibiscus-station/bin/python`, cả `--mock` lẫn bus giả lập STS) và giao diện tĩnh
lấy từ **wheel đã cài** (`site-packages/hibiscus_station/static`): `3 passed in 155.99s` (`mock-en`, `mock-vi`,
`sts-vi`). Luồng: kết nối → hiệu chỉnh follower → leader → Kiểm tra → camera → teleop → dừng an toàn (nhiệt / Space
e-stop) → ghi tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop → Chương trình. QC đã xem ảnh chụp (48 ảnh, sáng /
tối, vi / en): số đo hợp lý với giả lập (STS: 30 °C, 5.0 V, 0.08 A, tải 0 / -2 – -6 %; mock teleop 243.6 / 250 FPS,
vòng lặp p95 3.9 ms, độ trễ ~4 ms; STS teleop 239.4 / 250 FPS), nhãn đúng ngôn ngữ, e-stop khoá các bước.

### 3.6 Động cơ không trả lời và bộ chuyển chậm (QD-21)

Cùng bản cài, `doctor --no-cameras`, Station tắt:

| Tình huống | LIKELY PROBLEMS (ngoài 2 dòng hiệu chỉnh) | Motor check (trích) |
|---|---|---|
| Follower chưa cấp điện (6 servo im) | chỉ `! desk follower: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power? cable?)` | `ids answering at 1 Mbps: none` · `sync read: 20/20 failed, no read succeeded` · `teleop estimate: not measured (some motors did not answer)` |
| Chỉ servo 6 (gripper) im | chỉ `! desk follower: motor id(s) 6 do not answer (power? cable?)` | `ids answering at 1 Mbps: 1-5` · `20/20 failed, no read succeeded` · `not measured …` |
| Leader chưa cấp điện | chỉ `! desk leader: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power? cable?)` | leader `20/20 failed`; follower `0/20 failed, 0.57 ms each`, `~250 Hz` |
| Cả hai tay chưa cấp điện | hai dòng `… do not answer (power? cable?)`, không gì khác | hai tay `20/20 failed, no read succeeded`, `not measured` |
| Đối chứng: bộ chuyển chậm thật (follower trả lời trễ 20 ms, cả 6 servo trả lời) | `! desk follower on /dev/pts/8: slow bus (20.55 ms per read): slow USB adapter / hub: plug the arm straight into the PC, without a hub; only if the adapter is an FTDI chip (USB VID 0403): …` | `sync read: 0/20 failed, 20.55 ms each` · `teleop estimate: ~36 Hz, leader -> follower latency ~41.8 ms  ! slow bus …` |

Không lượt nào có "slow bus", "latency timer", "unreliable bus" hay ước lượng Hz khi có động cơ im. 0 lệnh ghi.
**QD-21 vẫn đóng.**

### 3.7 Bus mất gói / sai checksum (QD-22) và bus lỗi nặng (QD-23, QD-24)

Cùng bản cài, follower có cả 6 servo trả lời, giả lập bỏ ngẫu nhiên (`drop_rate`) hoặc làm sai checksum
(`corrupt_rate`) một phần câu trả lời của follower (hạt giống cố định); leader bình thường.

| Lỗi bus | LIKELY PROBLEMS (ngoài 2 dòng hiệu chỉnh) | Motor check của follower (trích) |
|---|---|---|
| mất 1 % | `! desk follower: unreliable bus: 1 of 20 reads got no answer although every motor answers; check the 3-pin cables between the servos, the power supply (it may drop under load) and plug the USB adapter straight into the PC` | `ids answering at 1 Mbps: 1-6` · `sync read: 1/20 failed, 0.87 ms each` · `! 1 of 20 reads lost although every motor answers` · `teleop estimate: ~250 Hz, leader -> follower latency ~3.2 ms` · `bus errors: 3, 2 retried ok …` |
| mất 5 % | `… unreliable bus: 5 of 20 reads got no answer although every motor answers; …` | **`ids answering at 1 Mbps: 1-3, 5-6`** (id 4 có dòng thanh ghi đầy đủ ngay dưới) · `sync read: 5/20 failed, 2.09 ms each` · `! 5 of 20 reads lost although every motor answers` · `~250 Hz, … ~4.8 ms` · `bus errors: 18, 7 retried ok …` |
| checksum 1 % | `… unreliable bus: 1 of 20 reads got no answer although every motor answers; …` | `1-6` · `1/20 failed, 0.85 ms each` · `! 1 of 20 reads lost …` · `~250 Hz` |
| checksum 5 % | **`… unreliable bus: 5 of 20 reads got no answer …`** | `ids answering at 1 Mbps: 1-3, 5-6` · `5/20 failed, 1.59 ms each` · `! 5 of 20 reads lost …` · `~250 Hz` · `last error: … motor 2: Checksum error` |
| mất 30 % | `… unreliable bus: 19 of 20 reads got no answer …` | `ids answering at 1 Mbps: 2-3` · `19/20 failed, 1.37 ms each` · `! 19 of 20 reads lost …` · `teleop estimate: ~250 Hz` |
| **mất 35 % (hạt giống 4)** | **`… unreliable bus: 20 of 20 reads got no answer although every motor answers; …`** | `ids answering at 1 Mbps: 3, 6` · `sync read: 20/20 failed, no read succeeded` · **`teleop estimate: not measured (some motors did not answer)`** |
| mất 40 % (hạt giống 3, 4) | như trên (`20 of 20`) | như trên |
| **checksum 40 %** | **`… unreliable bus: 20 of 20 reads got no answer although every motor answers; …`** | `ids answering at 1 Mbps: 2-3` · `20/20 failed, no read succeeded` · **`teleop estimate: not measured (some motors did not answer)`** |
| mất 50 % | `! desk follower: motor id(s) 3 do not answer (power? cable?)` (ping 3 lần đều mất) | `ids answering at 1 Mbps: 2-3` · `id 3: no answer` · `20/20 failed` · `not measured …` |

Ở tỉ lệ 1 % và 5 % (cả mất gói lẫn checksum) các yêu cầu của QD-22 đều đạt: có mục bus chập chờn trong LIKELY
PROBLEMS, dòng số lần đọc mất, và ước lượng tốc độ. **QD-22 đóng.** Nhưng khi mọi lần đọc đều mất trong lúc ping cả 6
động cơ vẫn trả lời (mất 35 – 40 %, checksum 40 %), dòng cũ "some motors did not answer" quay lại ngay dưới
`ids answering`, mâu thuẫn với LIKELY PROBLEMS của chính báo cáo (QD-23). Ở 5 %, dòng quét `1-3, 5-6` mâu thuẫn với
"although every motor answers" ở hai chỗ, và lỗi checksum bị gọi là "got no answer" (QD-24). `report.json` của lượt
mất 35 %: `sync_read_present_position {"reads": 20, "failed": 20, "ms_per_read": null}`, `teleop_estimate: null`,
`scan_1mbps {"3": 777, "6": 777}`. 0 lệnh ghi trong mọi lượt.

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `617be62`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `623 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách; gồm test mới `test_a_bus_that_loses_answers_is_a_likely_problem`) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 510.94s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 145.40s` |
| e2e trên bản cài (§3.5) | `3 passed in 155.99s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng).

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-22

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (`check_versions.py`, `--version`, health, doctor) |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, thư viện 100 %, smoke `--mock`; dry run PowerShell 7 không git |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows `591 passed`, không skip module `test_doctor` |
| QD-5 | Đóng | Test nhịp đọc bus xanh trên Windows |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | pytest macos `591 passed, 6 skipped`, skip có trong danh sách |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`) |
| QD-12 | Đóng | §3.2: không có dòng `DEBUG` khi bus không lỗi |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | Đóng | Không có giá trị Python trong 31 stdout và 35 báo cáo; `ms_per_read` rỗng là `no read succeeded` |
| QD-17 | Đóng | Dry run PowerShell 7 + CI Windows PowerShell 5.1: không có cảnh báo PATH của uv; dòng PATH song ngữ |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ, có múi lệch 30 / 45 phút và qua ngày) |
| QD-20 | Đóng | §1: sdist build sau `pnpm install` chỉ có gói (282 mục), trùng byte với CI |
| QD-21 | Đóng | §3.6: servo im, cả tay im, hai tay im: không "slow bus", không "unreliable bus", không ước lượng teleop; bộ chuyển chậm vẫn được báo |
| QD-22 | **Đóng** | §3.7: mất gói 1 % / 5 % và checksum 1 % / 5 % khi cả 6 động cơ trả lời: mục `unreliable bus` trong LIKELY PROBLEMS, dòng `reads lost`, ước lượng tốc độ; không còn "some motors did not answer" ở các tỉ lệ này; test mới xanh trên cả 3 nền tảng |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-23 · Low · F-63 (AT-77, FL-11; tính hợp lý của điều người dùng thấy) · Mọi lần đọc mất dù cả 6 động cơ trả lời:
`doctor` lại nói "some motors did not answer", trái với LIKELY PROBLEMS của chính báo cáo.**
Bước: hồ sơ có tay thật; cả 6 servo có điện và trả lời ping, nhưng bus mất hoặc làm hỏng phần lớn câu trả lời (cáp 3
chân lỏng ở khớp gần bộ chuyển, nguồn sụt mạnh, nhiễu); Station tắt; `hibiscus-station doctor --no-cameras` (QC: bản
cài, giả lập STS `drop_rate` 0.35 hạt giống 4, `drop_rate` 0.4 hạt giống 3 và 4, `corrupt_rate` 0.4; §3.7).
Kỳ vọng: như QD-22: chữ mô tả đúng điều đo được (ví dụ `teleop estimate: not measured (no read succeeded: the bus
loses answers)`), không đổ cho động cơ không trả lời khi không động cơ nào bị báo `no answer`.
Thực tế: LIKELY PROBLEMS: `! desk follower: unreliable bus: 20 of 20 reads got no answer although every motor answers;
…`; Motor check: `sync read: 20/20 failed, no read succeeded` rồi `teleop estimate: not measured (some motors did not
answer)`, không có dòng `id N: no answer` nào. Hai câu trong cùng một báo cáo nói ngược nhau; người hỗ trợ đọc zip đi
tìm động cơ chết không có.
Nguyên nhân QC thấy: `hibiscus_station/doctor.py` `summary()` (khoảng dòng 1035–1038) chọn câu "some motors did not
answer" mỗi khi `failed > 0` và không có `teleop_estimate`; `ping_arm()` để `teleop_estimate = None` cả khi có động cơ
im lẫn khi `ok_ms` rỗng, nên trường hợp "không động cơ nào im, không lần đọc nào thành công" rơi vào câu của động cơ im.
Test `test_a_bus_that_loses_answers_is_a_likely_problem` chỉ phủ 5 % (còn lần đọc thành công).

**QD-24 · Low · F-63 (AT-77; tính hợp lý của điều người dùng thấy) · Bus chập chờn: báo cáo vừa nói id 4 không trả lời
vừa nói "every motor answers"; lỗi checksum bị gọi là "got no answer".**
Bước: như QD-22 ở tỉ lệ thường gặp: cả 6 servo trả lời, bus mất 5 % câu trả lời hoặc 5 % câu trả lời sai checksum
(§3.7); `hibiscus-station doctor --no-cameras`.
Kỳ vọng: những dòng trong cùng một báo cáo không mâu thuẫn nhau: dòng quét chỉ ra id đã trả lời ở bước sau (hoặc nói
rõ là quét một lần, có thể sót trên bus chập chờn), và câu trong LIKELY PROBLEMS đúng với loại lỗi đo được (mất câu trả
lời / câu trả lời hỏng).
Thực tế: `desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-3, 5-6 (model 777)` rồi `id 4: model 777 fw 3.10 …`
đầy đủ, `! 5 of 20 reads lost although every motor answers` và LIKELY PROBLEMS `… although every motor answers`. Với
`corrupt_rate` 5 %: LIKELY PROBLEMS `unreliable bus: 5 of 20 reads got no answer`, trong khi `bus errors` của cùng báo
cáo ghi `last error: … motor 2: Checksum error` (động cơ có trả lời, gói hỏng). Người đọc không biết id 4 có trả lời
hay không và có thể đi tìm cáp đứt thay vì nhiễu / nguồn.
Nguyên nhân QC thấy: dòng `ids answering` lấy từ một lần `bus._scan` không thử lại; "every motor answers" dựa trên
`ping` (thử lại 2 lần); `warnings()` (khoảng dòng 780–786) luôn viết "got no answer" cho mọi `sync_read` thất bại.
Dòng quét sót id đã có ở lần 6 (§3.7 lần 6) nhưng chưa thành mâu thuẫn vì chưa có câu "every motor answers".

## 6. Ghi chú (không phải lỗi M0)

* **Rà lỗi lọt cho QD-23 / QD-24**: QC lần 6 thử bus mất gói ở 1 % và 5 % nhưng không thử tỉ lệ làm mọi lần đọc mất,
  cũng chưa thử lỗi checksum. Đã thêm vào cách kiểm của QC: thang lỗi bus 1 / 5 / 30 / 35 – 40 / 50 % cho cả mất gói và
  checksum, và đối chiếu từng câu của báo cáo với nhau (dòng quét, dòng `id`, dòng `reads lost`, LIKELY PROBLEMS). Đề
  nghị BA thêm "servo im / bus mất gói nhẹ / bus mất mọi lần đọc / checksum / bộ chuyển chậm" vào REGRESSION khi sửa.
* **`teleop estimate: ~250 Hz` khi 19 / 20 lần đọc mất** (mất 30 %, §3.7): đúng ý QD-22 (tốc độ của các lần đọc thành
  công) và LIKELY PROBLEMS đã nêu bus chập chờn, nhưng con số dễ làm người đọc tin teleop sẽ chạy 250 Hz. Đề nghị khi sửa
  QD-23 / QD-24 cân nhắc ghi kèm "speed of the reads that worked".
* **Dòng log `WARNING hibiscus_station.hw.bus: …` in ra stdout** của `doctor` khi bus có lỗi, xen giữa các dòng tiến độ
  (có từ trước; ghi chú lần 6, chưa đổi).
* **Dòng thanh ghi có lỗi đọc nhúng nguyên thông điệp lỗi**, có khi chen giữa hai số (`fw error: Failed to read
  'Firmware_Major_Version' … timed out.10`) ở bus lỗi nặng; có từ trước (ghi chú lần 6), vẫn đọc được.
* **Log CI của trình cài Windows vẫn hiện chữ Việt sai** (`Get-Content` của PowerShell 5.1 đọc UTF-8 bằng cp1252; ghi
  chú lần 3 – 6, chưa đổi). Byte trình cài phát ra đúng.
* **Test của QD-19 không phủ dòng báo cáo**; **`verify_assets.py` không kiểm sdist khi thư mục không có sdist**; **dòng
  chương trình giữ cổng cắt ở 160 ký tự**; **`lerobot-0.7.1-py3-none-any.whl` không tái lập byte**; **cảnh báo
  `StarletteDeprecationWarning`** trong pytest; **`warning: Failed to hardlink files`** của uv trong container: như lần
  4 – 6, chưa đổi.
* Các ghi chú §6 của lần 2 – 6 còn nguyên: macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong
  README trả 404 cho người ngoài (phát hành nháp sau khi QC PASS), câu chữ AT-77 bước 2, danh sách cổng trống với pty,
  `hibiscus-station health` sau `kill -9` (F-65, M3), CHANGELOG dòng `cameras: front, wrist`, hai lượt doctor trong cùng
  một giây cho cùng tên zip, hồ sơ demo ghi `calibration 'demo_follower' MISSING`.

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QC PASS.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong cửa sổ PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | **FAIL** (QD-23: mọi lần đọc mất dù cả 6 động cơ trả lời → "some motors did not answer", trái LIKELY PROBLEMS; QD-24: dòng quét `1-3, 5-6` cạnh "every motor answers", checksum bị gọi là "got no answer"; QD-22 đã đóng; mọi bước AT-77 [Vendor] đạt trên bản cài; VID:PID / WCH thật NOT VERIFIED, UAT-0) |
| F-1 phần M0 (P-1) | **PASS** (AT-2 PASS; CI Windows 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED, UAT-0) |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | **PASS** (M0) |
| AT-2 / nền kiểm CI | PASS (12 / 12, lượt 44088045317) |

QC chạy lại cổng M0 trên commit mới khi QD-23 và QD-24 đã có bản sửa kèm test tự động (mọi lần đọc mất khi cả 6 động
cơ trả lời; dòng quét không mâu thuẫn với dòng `id`; lỗi checksum), lượt CI của đúng commit đó xanh 12 / 12.

Máy chủ QC đã khởi động (`127.0.0.1:18650`, `18651`, `18652`, e2e trong `18655` – `18669`) và bộ giả lập đều đã dừng.
