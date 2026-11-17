# QC M0 lần 8: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-23 và QD-24 của [lần 7](QC-M0-r7.md) đã sửa đúng ở đúng tình huống đã báo: lượt CI của
đúng commit ứng viên **xanh 12 / 12**; trên bản cài, khi mọi lần đọc mất mà cả 6 động cơ trả lời ping, báo cáo giờ nói
`teleop estimate: not measured (too few reads succeeded: 0 of 20)` (không còn "some motors did not answer"); dòng quét
`ids answering` khớp đúng các dòng `id N` (cả 691 báo cáo QC tạo); lỗi checksum được gọi là `got corrupted answers
(checksum)`, không còn "got no answer". QD-1 – QD-24 đóng. Wheel, sdist, `install.ps1`, `constraints.txt` QC tự build
**trùng byte** với CI; mọi bước AT-77 [Vendor] đạt trên bản cài; **0 lệnh ghi động cơ** qua 691 lượt `doctor` có đếm
lệnh; luồng chuột `mock-en`, `mock-vi`, `sts-vi` trên bản cài `3 passed`. Nhưng lưới lỗi riêng của QC (mất gói, sai
checksum, gói cụt, byte rác, servo im, servo chập chờn, servo sụt nguồn giữa chừng, bộ chuyển chậm, câu trả lời đến
trễ, 2 – 3 hạt giống) tìm ra **3 lỗi mới** trong kết luận về động cơ của `doctor`: **QD-25 (Medium)** một câu trả lời
đến trễ ~60 ms làm mọi lần đọc sau của servo đó lệch một nhịp: báo cáo ghi `80 C`, `341.3 V`, `status overheat,
overload`, giới hạn `44-684` và LIKELY PROBLEMS bảo **hiệu chỉnh lại tay** dù tệp hiệu chỉnh đúng và bus không có lỗi
nào khác; **QD-26 (Low)** một lần đọc thanh ghi thất bại bị coi là tệp hiệu chỉnh **không khớp** ("calibrate the arm
again") ở ngay tỉ lệ mất gói 5 % của QD-22; **QD-27 (Low)** trên bus chập chờn, một động cơ bị kết luận `do not answer
(power? cable?)` trong khi chính báo cáo cho thấy nó có trả lời (quét thấy, có lần sync read cả 6 id thành công, lỗi
là checksum), còn bus chập chờn thì không được nêu. Theo quy tắc không lỗi (zero-defect): **F-1 / P-1 phần M0 đạt**,
**phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-25, QD-26, QD-27). Bản này **chưa** được giao cho
khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit. Lưới lỗi
của QC là của riêng QC (tiến trình giả lập riêng, kiểu lỗi riêng, phép kiểm đối chiếu với sự thật của tình huống chứ
không với quy tắc trong mã), không dùng lại lưới `test_the_report_never_contradicts_itself` của dev.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `452b457fbcfa3f9d8597ba97b642d30d91655508` (HEAD trên origin lúc QC bắt đầu, 21:28, và lúc kết thúc, 22:11) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44100603335 (push `release/v1`, `head_sha` = `452b457f…`, lần chạy 1) → **completed / success, 12 / 12 job xanh** (đã xong trước khi QC bắt đầu) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `e18ba64fb15cfef8fd265d820e690d90fe3b110cfe176f1fb50d083983ca3748`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `73f4f0c75601aad913883bdc94643406f4c7fd1dc7bb3c3c972bc09238cae831`, 282 mục, 0 mục `node_modules` / `tests/`: **trùng byte** với sdist của CI |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git, chỉ khác giờ / quyền trong zip như lần 3 – 7), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` → `pnpm install --frozen-lockfile` + `pnpm build` → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock); giả lập: tiến trình riêng của QC dựa trên `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty, phía slave đóng như bộ chuyển USB thật, đếm mọi lệnh), thêm các kiểu lỗi của QC (§3.6) |

Kết quả dry run (trích):

```
== 1b. verify the assets (checksums; resolved set == uv.lock on Windows x64, Linux x86_64, macOS arm64)
release assets of 1.0.0a1 OK
== 2. install (no git on PATH, empty home)
[Hibiscus Station] Xong: hibiscus-station 1.0.0a1. Mở cửa sổ PowerShell mới rồi gõ: hibiscus-station
                   Done: hibiscus-station 1.0.0a1. Open a new PowerShell window and type: hibiscus-station
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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-25, QD-26, QD-27) | Mọi bước AT-77 đạt trên bản cài (§3.1 – §3.5); 3 lỗi mới trong kết luận về động cơ (§3.6, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô 0–4, 13–15, 56–70; **0** dòng `DEBUG` |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ thật (43 ký tự), PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_Gvde…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong 691 lượt doctor có đếm lệnh + các lượt AT-77 |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | Nhà demo do `--mock` của bản cài tạo (`127.0.0.1:18652`, dừng bằng SIGINT, exit 0), `doctor --home …/station-demo`: `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`, `! no profile for a real arm: Robot > New robot, pick the arm's serial port`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2968578 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong stdout và `report.txt` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2969159: python3 -c … close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2968578, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS ở bus sạch · **FAIL** khi bus lỗi (QD-25, QD-26) | Bus sạch: tệp đúng chỗ, khớp động cơ: `calibration file vs motors: all 6 match`, không có mục hiệu chỉnh trong LIKELY PROBLEMS; tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …`. Bus lỗi: §3.6 |
| **QD-23** mọi lần đọc mất, cả 6 động cơ trả lời | **PASS** | §3.6.1 |
| **QD-24** dòng quét / "every motor answers" / checksum | **PASS** | §3.6.1 |
| Lưới lỗi bus của QC (kết luận về động cơ) | **FAIL** (QD-25, QD-26, QD-27) | §3.6 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44100603335 xanh 12 / 12 (python linux / windows / macos, e2e Chromium / Firefox / Edge, cài Windows + `--mock` smoke, macOS cài smoke, image, web, deploy, release assets) |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git, libraries == uv.lock, --mock smoke)` xanh. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính bằng chuột trên **bản cài** (§3.5): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test + giả lập bộ chuyển chậm) · chạy thật NOT VERIFIED | §3.6.3: bộ chuyển chậm 6 – 46 ms được báo `slow bus (… ms per read)` với lời khuyên "only if the adapter is an FTDI chip (USB VID 0403)"; 0 lần báo "slow bus" ở bộ chuyển nhanh trong 691 báo cáo |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS ở bus sạch · giá trị sai khi có câu trả lời trễ (QD-25) | §3.2; §3.6.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.5) + CI |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng (CI) + local pytest và e2e: `skips on linux: all in the published list` |
| FL-12 dry run phát hành | **PASS** | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.5 |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows xanh |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần `doctor --verbose` từ tay của khách (UAT-0). Ghi chú: QD-25 cho thấy doctor có thể in nhiệt độ / điện áp sai khi bus có câu trả lời trễ |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3 – 7 |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-25 – QD-27) | Không có dict / list / `None` / `True` / `False` / `Traceback` trong 691 stdout của lưới, trừ thông điệp lỗi gốc của lerobot sau `last error:`; giờ tệp hiệu chỉnh đúng ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` (v8.30.1) trên cây của commit (`git archive`): `no leaks found`; 2 commit mới `617be62..452b457` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật; wheel và sdist không chứa đường dẫn home hay email |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục QD-23 / QD-24 ("The doctor's lines about the motors always agree") |
| Vệ sinh phát hành: nội dung tài sản phát hành | PASS | §1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r8/…/user` mới cho mỗi lượt, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin`
(không đặt `TZ`). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy) do một
tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty và đếm `read`, `write`, `sync_read`,
`sync_write`. Hồ sơ `desk` (`so101_follower` / `so101_leader`). Ở lưới lỗi (§3.6) tệp hiệu chỉnh của follower nằm
**đúng chỗ Station dùng** (`…/calibration/robots/so_follower/desk_follower.json`) và **khớp** EEPROM, nên mọi câu "does
not match" đều sai; ở AT-77 bước 1 tệp nằm trong thư mục của LeLab (`so101_follower`) như lần 7.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-17 21:36:39 +0700
$ ls -l desk_follower.json              -> 2026-11-17 21:36:39 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
  follower desk_follower            so101_follower  2026-11-17 21:36:39 UTC+07:00  …
…
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.79 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~3.1 ms
```

Lệnh giả lập nhận ở một lượt bus sạch: follower `read 144, sync_read 20`, leader như vậy, **write 0, sync_write 0**.

Khi Station (bản cài, `127.0.0.1:18651`) đang chạy và đã kết nối `desk` (`POST /api/v1/robots/desk/connect` → `200`):
`pid 2968578: mode real, state idle`; hai cổng `skipped, in use by Station (pid 2968578); stop it to ping the motors`;
mục **WHAT TO SEND / CẦN GỬI GÌ** có câu "The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi
của giả lập chỉ tăng lúc Station kết nối (69 / 36), không tăng trong lượt doctor (trước 69 / 36, sau 69 / 36).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ thật của Station (tệp `token`, 43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`;
một PAT đúng định dạng `hbp_<8>_<43>` (mới sinh) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến
môi trường `HF_TOKEN=hf_QCr8…`, `GITHUB_TOKEN=ghp_QCr8…`. Zip chứa `report.txt, report.json, station.log.tail,
robots.yaml, sessions/s-qc.json` và các tệp hiệu chỉnh. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_Gvde… used"
server.json trong zip: 0
```

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`2026-11-17 21:36:56 +0700`), `doctor --no-ping --no-cameras`:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-17 21:36:56 UTC+07:00` | `…-20261117-213658.zip` |
| `UTC` | `2026-11-17 14:36:56 UTC+00:00` | `…-20261117-143659.zip` |
| `Asia/Kolkata` | `2026-11-17 20:06:56 UTC+05:30` | `…-20261117-200700.zip` |
| `America/St_Johns` | `2026-11-17 11:06:56 UTC-03:30` | `…-20261117-110702.zip` |
| `Pacific/Chatham` | `2026-11-18 04:21:56 UTC+13:45` | `…-20261118-042203.zip` (qua ngày) |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (lệnh `hibiscus-station` của môi trường test được trỏ tạm về
`<dry-run>/home/.local/bin/hibiscus-station`, trả lại sau khi chạy) và giao diện tĩnh lấy từ **wheel đã cài**
(`site-packages/hibiscus_station/static`): `3 passed in 150.31s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối →
hiệu chỉnh follower → leader → Kiểm tra → camera → teleop → dừng an toàn → ghi tập → bộ dữ liệu → nạp model ACT → chạy
model → e-stop → Chương trình.

### 3.6 Lưới lỗi của QC trên bản cài: kết luận của `doctor` về động cơ

691 lượt `hibiscus-station doctor --no-cameras` của bản cài, Station tắt, mỗi lượt một HOME và một cặp pty mới:

* **Lưới chính, 576 lượt**: mất gói `drop` 0 / 1 / 5 / 10 / 20 / 30 / 40 / 60 / 100 % × sai checksum `corrupt` 0 / 5 / 20
  / 40 % × servo im (không, id 6, id 2 + 4, cả 6) × bộ chuyển (0.5 ms, 9 ms mỗi câu trả lời) × hạt giống 1, 2.
* **Lượt đặc biệt, 115 lượt**: bộ chuyển chậm 4 / 6 / 9 / 16 / 20 / 30 / 34 / 38 / 42 / 46 / 50 / 100 ms; một servo
  chập chờn (id 1, 4, 6 mất 10 / 30 / 60 / 90 % câu trả lời); gói cụt 5 / 30 / 100 %; byte rác trước gói 5 / 30 / 100 %;
  servo 4 sụt nguồn sau 5 / 50 / 100 / 150 / 200 / 300 giao dịch; leader lỗi, cả hai tay lỗi, `--verbose`; câu trả lời
  đến trễ ngẫu nhiên (0.5 % / 2 % câu trả lời trễ thêm 60 / 150 ms); **đúng một** câu trả lời đến trễ (của lệnh đọc
  `Homing_Offset` id 1, của lệnh quét, của ping id 3, của một sync read); các tình huống QD-21 / QD-22 / QD-23 / QD-24
  của lần 6 – 7 (hạt giống 1, 3, 4).

Mỗi báo cáo được đối chiếu với **sự thật của tình huống** (động cơ nào có điện, tệp hiệu chỉnh khớp, bộ chuyển nhanh
hay chậm) và giữa các dòng của chính nó.

| Phép kiểm của QC (691 báo cáo) | Số báo cáo sai |
|---|---|
| Lệnh ghi động cơ (`write`, `sync_write`) | **0** |
| `Traceback`, giá trị Python trong chữ (ngoài `last error:`) | **0** |
| Dòng quét `ids answering` ≠ tập id có dòng đầy đủ | **0** |
| Servo im thật không được nêu `do not answer` | **0** |
| "unreliable bus" cùng lúc với servo im | **0** |
| Có lần đọc thất bại, mọi servo trả lời, mà LIKELY PROBLEMS không nêu bus | **0** |
| "slow bus" ở bộ chuyển nhanh / bộ chuyển chậm (9 ms, bus sạch) không được báo | **0 / 0** |
| Tệp hiệu chỉnh **khớp** nhưng LIKELY PROBLEMS nói `does not match … calibrate the arm again` | **268 / 576** lưới chính + 52 / 115 lượt đặc biệt (QD-25, QD-26) |
| Giá trị thanh ghi sai in ra như thật (nhiệt độ, điện áp, status, offset, giới hạn) | 9 / 115 lượt đặc biệt (QD-25); 0 ở lưới chính |
| Servo có trả lời (quét thấy / sync read cả 6 id thành công / chỉ lỗi checksum) bị kết luận `do not answer (power? cable?)` | lưới chính: 12 có sync read cả 6 id thành công cạnh "do not answer", 32 có "answered the first scan" cạnh "power? cable?"; 7 lượt đặc biệt có sync read thành công cạnh "do not answer" (QD-27) |

#### 3.6.1 QD-23 và QD-24 (đã sửa)

| Lỗi bus (follower, cả 6 servo trả lời) | Motor check của follower (trích) |
|---|---|
| mất 35 % hạt giống 4 (tình huống QD-23) | `ids answering at 1 Mbps: 1-6 (model 777); 1-2, 4-5 answered only on a retry` · `sync read: 20/20 failed (1 got no answer, 19 got malformed answers (parse error: …)), no read succeeded` · `! unreliable bus: 20 of 20 reads failed (…) although every motor answers a ping` · **`teleop estimate: not measured (too few reads succeeded: 0 of 20)`** |
| mất 40 % hạt giống 3, 4; checksum 40 % | như trên; checksum: `20/20 failed (20 got corrupted answers (checksum))` |
| mất 5 % hạt giống 4 (tình huống QD-24) | `ids answering at 1 Mbps: 1-6 (model 777); 5 answered only on a retry` · `5/20 failed (5 got malformed answers …), 15 worked, 1.61 ms each` · `teleop estimate: ~250 Hz, … (speed of the 15 reads that worked)` |
| checksum 1 % / 5 % | `1 got corrupted answers (checksum)` / `5 got corrupted answers (checksum)`; không có "got no answer" |
| servo im (id 6; cả tay; leader; hai tay) | chỉ `motor id(s) … do not answer (power? cable?)`, `teleop estimate: not measured (motor id(s) … do not answer)`, không "unreliable bus", không Hz (QD-21 vẫn đóng) |
| bộ chuyển chậm 20 ms | `slow bus (20.4 ms per read)` + lời khuyên FTDI (D-21) |

`report.json` khớp chữ: ví dụ mất 35 % hạt giống 4: `sync_read_present_position {"reads": 20, "ok": 0, "failed": 20,
"no_answer": 1, "corrupt": 0, "garbled": 19, "other": 0, "ms_per_read": null}`, `bus_verdict.kind = "unreliable"`,
`teleop_estimate: null`. **QD-23, QD-24 đóng.**

#### 3.6.2 Câu trả lời đến trễ (QD-25)

Bus sạch, bộ chuyển nhanh; **đúng một** câu trả lời (lệnh đọc `Homing_Offset` của id 1) đến trễ thêm 60 ms. Hai lượt,
kết quả giống hệt:

```
LIKELY PROBLEMS:
  ! desk leader: no calibration 'desk_leader'
  ! desk follower: calibration file 'desk_follower' does not match the motors (1 of 6 motors: shoulder_pan range_min:
    file 684 motor 44); Connect writes the file to the motors: if it is not this arm's file, calibrate the arm again
…
  desk follower on /dev/pts/12: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 3413x0.1V (min 50 max 40) 80C (max 30) status 500 torque 0 lock 0 offset 44 limits 44-684
           current raw 70 = 0.455 A load raw 12 = 1.2 % temperature 80.0 C voltage 341.3 V (IMPLAUSIBLE: shown as unknown)
           status overheat, overload protection current raw 0
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
        -> fw 3.10 model 777 temperature raw 30 = 30.0 C (max limit 70 C) voltage raw 50 = 5.0 V current raw 12 = 0.078 A …
    sync read: 0/20 failed, 0.58 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
    calibration file vs motors: 5 of 6 match; shoulder_pan: range_min: file 684 motor 44; range_max: file 3413 motor 684
    bus errors: 1, 1 retried ok (read Homing_Offset [1] x1); …
```

Sự thật: servo 1 có 30 °C, 5.0 V, status 0, giới hạn 684 – 3413, khớp tệp. Sau một lần đọc hết giờ rồi "retried ok",
mọi thanh ghi đọc sau của id 1 lấy câu trả lời của lệnh đọc **trước** nó (`Min_Position_Limit` = 44 là offset,
`Present_Voltage` = 3413 là giới hạn trên, …). Cùng báo cáo vừa in `80.0 C` / `overheat, overload` vừa in dump thô
`30.0 C`, `status raw 0 ok`; LIKELY PROBLEMS không nêu bus mà bảo hiệu chỉnh lại. Biến thể QC thấy thêm:

* Bộ chuyển chậm ≥ 50 ms mỗi câu trả lời (bus sạch): `calibration file vs motors: 0 of 6 match`, `fw 777.3`, `status
  overheat, overload`, `voltage 341.3 V` ở cả 6 servo; dump thô lấy câu trả lời cũ còn trong bộ đệm (`id 1: [0-4] 00 08`:
  2 byte cho lệnh đọc 5 byte, giải ra `fw 0.8`). Ở 46 ms mọi thứ đúng; ở 100 ms cả 6 servo `do not answer (power?
  cable?)`.
* 2 % câu trả lời trễ thêm 60 ms (hạt giống 1, 3): `status overheat` / giới hạn lệch ở id 1, 5, 6 và mục hiệu chỉnh sai
  trong LIKELY PROBLEMS (lặp lại được với hạt giống 3).
* 2 % trễ thêm 150 ms (hạt giống 3), một lượt: `! desk follower: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power?
  cable?)`, mọi `id N: no answer`, trong khi cùng báo cáo có `sync read: 3/20 failed (…), 17 worked` (sync read cần cả 6
  id trả lời) và dump thô của id 2 – 6 đầy đủ, `30.0 C`, `status raw 0 ok`. Lượt chạy lại cùng hạt giống cho ra biến
  thể "giá trị lệch + calibrate again" (thời điểm khác nhau).

#### 3.6.3 Lần đọc thanh ghi thất bại bị coi là tệp không khớp (QD-26)

Mất 5 % hạt giống 1 (đúng tình huống QD-22), tệp đúng chỗ và khớp:

```
  ! desk follower: unreliable bus: 5 of 20 reads failed (1 got no answer, 4 got malformed answers (parse error: …)) although
    every motor answers a ping; check the 3-pin cables between the servos, …
  ! desk follower: calibration file 'desk_follower' does not match the motors (2 of 6 motors: shoulder_pan, gripper; first:
    shoulder_pan range_max: file 3413 motor error: Failed to read 'Max_Position_Limit' from motor ID 1 after 1 tries.
    Operation timed out); Connect writes the file to the motors: if it is not this arm's file, calibrate the arm again
    calibration file vs motors: 4 of 6 match; shoulder_pan: range_max: file 3413 motor error: Failed to read …
```

Không có giá trị nào khác nhau; động cơ chỉ không trả lời một lần đọc. Gặp ở 268 / 576 báo cáo lưới chính (mọi tỉ lệ
mất / checksum từ 1 % đến 60 %, cả khi có servo im) và ở checksum 5 %, gói cụt 5 %, byte rác 5 %, servo chập chờn 10 %,
bộ chuyển chậm 20 ms + mất 5 %. Người dùng làm theo sẽ hiệu chỉnh lại một tay đã hiệu chỉnh đúng.

#### 3.6.4 Servo có trả lời bị kết luận "do not answer (power? cable?)" (QD-27)

Mất 0 %, checksum 40 %, hạt giống 2 (mọi servo luôn trả lời, chỉ gói hỏng):

```
  ! desk follower: motor id(s) 5 do not answer (power? cable?)
  desk follower on /dev/pts/10: ids answering at 1 Mbps: 1-4, 6 (model 777); 2-4 answered only on a retry; 5 answered the
    first scan, then no ping
    id 5: no answer
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] no answer
    sync read: 19/20 failed (19 got corrupted answers (checksum)), 1 worked, 6.17 ms each
    teleop estimate: not measured (motor id(s) 5 do not answer)
```

Cùng một báo cáo: id 5 "do not answer" nhưng đã trả lời lần quét, và 1 sync read của cả 6 id thành công (cần id 5 trả
lời); mọi lỗi đo được là checksum (servo có trả lời, gói hỏng), dump thô cũng gọi gói hỏng là `no answer`; LIKELY
PROBLEMS không nêu bus chập chờn, chỉ bảo kiểm tra nguồn / cáp của servo 5. Tương tự ở mất 20 % + checksum 5 % (id 4,
3 sync read thành công), mất 50 % hạt giống 1 (`1-2, 4-6 answered only on a retry; 3 answered the first scan, then no
ping` → chỉ `motor id(s) 3 do not answer`), servo 4 chập chờn 90 % (`2 worked`). Servo sụt nguồn thật sau lần quét
(`brown_after 5 / 50`) cũng in "answered the first scan, then no ping": ở đó kết luận đúng, nên chữ hiện tại không giúp
người đọc phân biệt hai trường hợp.

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `452b457`)

| Kiểm | Kết quả |
|---|---|
| `uv lock --check`, `uv sync --locked` | exit 0 |
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict (Linux, `--platform win32`, `--platform darwin`, `tools/release tools/ci`) | `Success: no issues found in 83 source files` ×3 · `in 5 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api, coverage | exit 0 cả năm |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `704 passed, 1 skipped, 311 deselected` (skip `tests/test_platform.py:163` Windows byte-range lock, có trong danh sách) · `skips on linux: all in the published list` |
| pytest lưới `slow` của dev (`tests/test_doctor.py -m slow`) | `303 passed` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 505.32s` · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 146.41s` |
| e2e trên bản cài (§3.5) | `3 passed in 150.31s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng). Các test của dev xanh nhưng không bắt được
QD-25 – QD-27: lưới của dev không có tệp hiệu chỉnh, không có câu trả lời trễ, và phép kiểm "silent" của nó chấp nhận
mọi kết luận "do not answer" của ping.

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-24

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (`check_versions.py`, `--version`, health, doctor) |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: job cài xanh; dry run PowerShell 7 không git (§1) |
| QD-3 | Đóng | CI e2e Windows Edge xanh |
| QD-4 | Đóng | CI pytest windows xanh |
| QD-5 | Đóng | CI pytest windows xanh |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | CI pytest macos xanh, skip trong danh sách |
| QD-8 | Đóng | CI `image (cpu, linux/amd64, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox (QC + CI), Windows Edge (CI) |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`) |
| QD-12 | Đóng | §3.2: 0 dòng `DEBUG` |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 ở bus sạch |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | Đóng | Không có giá trị Python trong 691 stdout; `ms_per_read` rỗng là `no read succeeded` |
| QD-17 | Đóng | Dry run: `OK: no uv PATH warning`; dòng PATH song ngữ |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ) |
| QD-20 | Đóng | §1: sdist 282 mục, trùng byte với CI |
| QD-21 | Đóng | §3.6.1: servo im không bị gọi "slow bus" / "unreliable bus", không Hz; bộ chuyển chậm vẫn được báo |
| QD-22 | Đóng | §3.6.1: mất gói / checksum 1 % – 5 %: mục `unreliable bus`, dòng `reads failed`, ước lượng tốc độ |
| QD-23 | **Đóng** | §3.6.1: mọi lần đọc mất khi cả 6 động cơ trả lời: `not measured (too few reads succeeded: 0 of 20)` |
| QD-24 | **Đóng** | §3.6.1: dòng quét = tập dòng `id` đầy đủ ở 691 / 691 báo cáo; checksum là `corrupted answers (checksum)` |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-25 · Medium · F-63 (AT-77, FL-11, K-11; tính hợp lý của điều người dùng thấy) · Một câu trả lời đến trễ làm
`doctor` đọc lệch một nhịp: in giá trị sai như thật (80 °C, 341 V, "overheat, overload") và bảo hiệu chỉnh lại tay.**
Bước: tay có tệp hiệu chỉnh đúng, bus sạch; trong lúc `doctor` đọc thanh ghi, một câu trả lời đến trễ hơn thời gian chờ
của thư viện (~50 ms: USB / hệ điều hành khựng, hub, bộ chuyển có latency lớn); `hibiscus-station doctor --no-cameras`
(QC: bản cài, giả lập STS, đúng một câu trả lời của lệnh đọc `Homing_Offset` id 1 trễ thêm 60 ms; §3.6.2).
Kỳ vọng: một câu trả lời trễ không bao giờ thành giá trị của thanh ghi khác: bỏ câu trả lời cũ còn trong bộ đệm trước
mỗi lần đọc (hoặc kiểm id / độ dài / thanh ghi của câu trả lời), lần đọc đó được báo là lỗi bus; không kết luận "tệp
không khớp" hay "quá nhiệt" từ giá trị đọc trên bus vừa có lỗi; dump thô chỉ nhận gói có đúng độ dài đã hỏi.
Thực tế: `id 1: … 3413x0.1V … 80C … status 500 … limits 44-684`, `temperature 80.0 C voltage 341.3 V (IMPLAUSIBLE …)
status overheat, overload`, dump thô cùng báo cáo `30.0 C … status raw 0 ok`; LIKELY PROBLEMS: `calibration file
'desk_follower' does not match the motors (… range_min: file 684 motor 44) … calibrate the arm again`, không có dòng nào
về bus. Biến thể: bộ chuyển ≥ 50 ms → `0 of 6 match`, dump thô `[0-4] 00 08` → `fw 0.8`; trễ 150 ms một lần → cả 6
servo `do not answer (power? cable?)` dù `17 worked` và dump thô đầy đủ.
Nguyên nhân QC thấy: các lần đọc của `ping_arm()` (`hibiscus_station/doctor.py`, qua `StationMotorsBus`) không xả bộ
đệm nhận trước mỗi lệnh nên câu trả lời trễ được nhận làm câu trả lời của lệnh sau; `_read_answer()` của dump thô chỉ
kiểm id, không kiểm độ dài, và bộ đệm còn câu trả lời cũ của phiên lerobot.

**QD-26 · Low · F-63 (AT-77, FL-11) · Một lần đọc thanh ghi thất bại bị báo là tệp hiệu chỉnh không khớp, kèm lời
khuyên hiệu chỉnh lại.**
Bước: tay có tệp hiệu chỉnh đúng chỗ, khớp động cơ; bus mất hoặc làm hỏng vài phần trăm câu trả lời (tình huống QD-22);
`hibiscus-station doctor --no-cameras` (QC: mất 5 % hạt giống 1; §3.6.3).
Kỳ vọng: lần đọc lỗi là lỗi bus (đã có mục `unreliable bus`), dòng `calibration file vs motors` nói động cơ nào không
đọc được ("could not read"), LIKELY PROBLEMS không nói "does not match … calibrate the arm again" khi không có giá trị
nào khác nhau.
Thực tế: `! desk follower: calibration file 'desk_follower' does not match the motors (2 of 6 motors: shoulder_pan,
gripper; first: shoulder_pan range_max: file 3413 motor error: Failed to read 'Max_Position_Limit' … Operation timed
out); Connect writes the file to the motors: if it is not this arm's file, calibrate the arm again`. 268 / 576 báo cáo
lưới chính.
Nguyên nhân QC thấy: `_compare()` (`doctor.py` khoảng dòng 669–685) so `row.get(reg)` (chuỗi `"error: …"` khi đọc lỗi)
với số trong tệp và coi là khác; `warnings()` chỉ loại `NO_ANSWER`.

**QD-27 · Low · F-63 (AT-77; tính hợp lý của điều người dùng thấy) · Trên bus chập chờn, servo có trả lời bị kết luận
"do not answer (power? cable?)", và bus chập chờn không được nêu.**
Bước: cả 6 servo có điện; bus làm hỏng nhiều câu trả lời (checksum 40 %; hoặc mất 20 % + checksum 5 %; hoặc mất 50 %;
hoặc một servo chập chờn 90 %), cả 3 ping của một servo đều hỏng / mất; `hibiscus-station doctor --no-cameras` (§3.6.4).
Kỳ vọng: các dòng trong cùng báo cáo không ngược nhau: servo đã trả lời lần quét hoặc nằm trong một sync read thành
công thì không bị gọi là "do not answer"; servo chỉ trả lời gói hỏng là "answers with corrupted packets", không phải
"no answer"; LIKELY PROBLEMS nêu bus chập chờn khi lỗi đo được là của bus (checksum, nhiều servo phải thử lại).
Thực tế: `! desk follower: motor id(s) 5 do not answer (power? cable?)` cạnh `5 answered the first scan, then no ping`,
`sync read: 19/20 failed (19 got corrupted answers (checksum)), 1 worked`, dump thô gọi gói hỏng là `no answer`; LIKELY
PROBLEMS không có mục bus. 12 báo cáo lưới chính có sync read cả 6 id thành công cạnh "do not answer", 32 có "answered
the first scan" cạnh "power? cable?".
Nguyên nhân QC thấy: `bus_verdict()` cho servo im (theo ping) thắng mọi bằng chứng khác (quét, sync read thành công,
loại lỗi) và khi có servo im thì không bao giờ nêu bus; ping không phân loại lỗi checksum; dump thô gọi mọi gói không
hợp lệ là `no answer`.

## 6. Ghi chú (không phải lỗi M0)

* **Rà lỗi lọt cho QD-25 – QD-27**: lần 7 dùng tệp hiệu chỉnh trong thư mục LeLab (Station không so EEPROM với tệp đó)
  và không thử câu trả lời đến trễ, nên không thấy QD-25, QD-26. Đã thêm vào cách kiểm của QC: tệp hiệu chỉnh đúng chỗ
  và khớp trong mọi lượt lưới lỗi; "một câu trả lời trễ" và "bộ chuyển ≥ 50 ms"; đối chiếu giá trị thanh ghi in ra với
  EEPROM thật và với dump thô của chính báo cáo; đối chiếu "do not answer" với dòng quét và sync read. Đề nghị BA thêm
  "câu trả lời trễ một lần / tệp hiệu chỉnh khớp trên bus lỗi" vào REGRESSION khi sửa.
* **Bộ chuyển chậm ≥ 100 ms mỗi câu trả lời**: mọi servo `do not answer (power? cable?)` (§3.6.2). Bộ chuyển như vậy
  hiếm; ghi nhận để xét cùng QD-25 (thời gian chờ của thư viện).
* **`--verbose` / bus lỗi**: dòng log `WARNING hibiscus_station.hw.bus: …` vẫn in ra stdout xen giữa các dòng tiến độ;
  dòng thanh ghi có lỗi đọc nhúng nguyên thông điệp lỗi của lerobot (`last error: … motor IDs [1, 2, 3, 4, 5, 6]`): như
  lần 6 – 7.
* Các ghi chú §6 của lần 2 – 7 còn nguyên: log CI của trình cài Windows hiện chữ Việt sai (`Get-Content` của PowerShell
  5.1), test của QD-19 không phủ dòng báo cáo, `verify_assets.py` không kiểm sdist khi thư mục không có sdist, dòng
  chương trình giữ cổng cắt ở 160 ký tự, `lerobot-0.7.1-py3-none-any.whl` không tái lập byte, cảnh báo
  `StarletteDeprecationWarning`, macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong README
  trả 404 cho người ngoài, `hibiscus-station health` sau `kill -9` (F-65, M3), hồ sơ demo ghi `calibration
  'demo_follower' MISSING`.

## 7. Việc người dùng phải kiểm thay QC (chỉ mục NOT VERIFIED)

* AT-1: trên Windows 10/11 x64 sạch không git, dán lệnh một dòng từ bản nháp `v1.0.0a1`, `hibiscus-station --version`
  (UAT-0 / UAT-1 bước 1), sau khi QC PASS.
* AT-77 / D-21 / REG-13: `hibiscus-station doctor --verbose` với hai tay thật (CH340 / CH343), gửi zip + ảnh Feetech FD (UAT-0).
* REG-18 trên máy của khách: chữ tiếng Việt của trình cài và của Station hiện đúng trong cửa sổ PowerShell.

## 8. Kết luận cho từng mục M0

| Mục | QC result |
|---|---|
| F-63 `doctor` | **FAIL** (QD-25: một câu trả lời trễ → giá trị sai như thật (80 °C, 341 V, "overheat") và "calibrate the arm again"; QD-26: lần đọc lỗi bị báo là tệp hiệu chỉnh không khớp; QD-27: servo có trả lời bị gọi "do not answer (power? cable?)", bus chập chờn không được nêu; QD-23, QD-24 đã đóng; mọi bước AT-77 [Vendor] đạt trên bản cài; VID:PID / WCH thật NOT VERIFIED, UAT-0) |
| F-1 phần M0 (P-1) | **PASS** (AT-2 PASS; CI Windows 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED, UAT-0) |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | **PASS** (M0) |
| AT-2 / nền kiểm CI | PASS (12 / 12, lượt 44100603335) |

QC chạy lại cổng M0 trên commit mới khi QD-25, QD-26 và QD-27 đã có bản sửa kèm test tự động (một câu trả lời trễ
trong lúc đọc thanh ghi, trên bus sạch; tệp hiệu chỉnh khớp trên bus mất gói / checksum; servo chỉ trả lời gói hỏng
hoặc đã trả lời lần quét / sync read), lượt CI của đúng commit đó xanh 12 / 12.

Máy chủ QC đã khởi động (`127.0.0.1:18650`, `18651`, `18652`, e2e trong `18655` – `18669`) và bộ giả lập đều đã dừng.
