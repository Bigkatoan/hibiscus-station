# QC M0 lần 10: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-18

**Kết luận: M0 = FAIL.** QD-28, QD-29, QD-30, QD-31 của [lần 9](QC-M0-r9.md) đã sửa đúng ở đúng tình huống đã báo
(17 / 17 lượt tái hiện của lần 9 nay đúng): lượt CI của đúng commit ứng viên **xanh 12 / 12**; wheel, sdist,
`install.ps1`, `constraints.txt` QC tự build **trùng byte** với CI; mọi bước AT-77 [Vendor] đạt trên bản cài. Trên bản
cài, **1 609 lượt** `doctor` (lưới lần 8 + lần 9 lặp lại: 922 lượt; lưới riêng của lần 10: 687 lượt) cho **0 giá trị
thanh ghi / giá trị giải mã / byte thô sai** (mọi giá trị in ra là đúng sự thật hoặc `?` / "no answer"), **0 lệnh ghi
động cơ**, 0 `Traceback`. Nhưng lưới riêng của QC lần này (nhiễu trên đường dây, khựng bus 0.35 – 1.5 s, bộ chuyển chậm
đều quanh hạn chờ 50 ms, bộ chuyển trễ ngẫu nhiên, servo có điện muộn, id lạ, mất mọi gói trong một khoảng, 300 tổ hợp
ngẫu nhiên của mọi kiểu lỗi) tìm ra **3 lỗi mới (Low)** trong kết luận về động cơ của `doctor`: **QD-32** một gói hỏng
lạc (nhiễu) trong lúc hỏi servo **mất điện** làm nó thành "answers only with corrupted packets", mất "do not answer
(power? cable?)", trong khi dump thô của chính báo cáo ghi "no answer" ở mọi khối; **QD-33** một lần khựng USB **từ 350
ms** đúng lúc ping (từ 700 ms lúc quét) làm servo trả lời mọi lệnh bị gọi "answer only now and then" kèm lời khuyên
kiểm cáp 3 chân và nguồn, dù cùng dòng ghi "answered the scan, 20 of 20 sync reads, 3 late answers" (QD-30 chỉ đóng tới
~300 ms); **QD-34** bộ chuyển chậm đều 49 ms (dạng đường ống) bị kết luận `unreliable bus: 1 of 20 reads failed (1 got
their answers only after the timeout) although every motor answers a ping; check the 3-pin cables …` cạnh `slow bus
(49.82 ms per read)` (cùng triệu chứng QD-31 ở mức 49 ms thay vì 50 ms). Theo quy tắc không lỗi (zero-defect): **F-1 /
P-1 phần M0 đạt**, **phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-32 – QD-34). Bản này **chưa**
được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit. Lưới lỗi
là của riêng QC: tiến trình giả lập riêng (dùng `tests/sts_emulator.py` chỉ để mô phỏng thanh ghi servo), các kiểu lỗi,
phép đối chiếu với sự thật và bộ đoán đúng / sai của QC; lần này giả lập của QC còn **đếm từng gói mỗi servo thật sự
gửi** để đối chiếu "servo nào im" với sự thật thay vì suy ra từ cấu hình.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `71ec53446c255dab4bf16c7976203551cbe4827d` (HEAD trên origin lúc QC bắt đầu và lúc kết thúc) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44175485057 (push `release/v1`, `head_sha` = `71ec5344…`, lần chạy 1) → **completed / success, 12 / 12 job xanh** (đã xong trước khi QC bắt đầu) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `b84cdd045249cb183bad5de80391a089b4464c70722c6023b94187c923ed0c08`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `823f73b9129366a8289b1178c5d1415467874e0a002e20e2fb0d96e6b02869d4`, 283 mục, 0 mục `node_modules` / `tests/`: **trùng byte** với sdist của CI |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git; **nội dung 709 / 709 tệp trùng**, chỉ khác giờ / quyền trong zip như lần 3 – 9), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` từ GitHub → `pnpm install --frozen-lockfile` + `pnpm build` → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (không git, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock); giả lập: tiến trình riêng của QC (2 chuỗi STS3215 trên pty, phía slave đóng như bộ chuyển USB thật, đếm mọi lệnh và mọi gói mỗi servo gửi) với các kiểu lỗi của QC (§3.6) |

Kết quả dry run (trích):

```
== 1b. verify the assets (checksums; resolved set == uv.lock on Windows x64, Linux x86_64, macOS arm64)
x86_64-pc-windows-msvc: 91 packages, identical to uv.lock
x86_64-unknown-linux-gnu: 114 packages, identical to uv.lock
aarch64-apple-darwin: 90 packages, identical to uv.lock
release assets of 1.0.0a1 OK
== 2. install (no git on PATH, empty home)
                   Done: hibiscus-station 1.0.0a1. Open a new PowerShell window and type: hibiscus-station
== 2b. installer output: no uv PATH warning, the PATH line in both languages (QD-17)
OK: no uv PATH warning
== 4. installed libraries == the tested set (uv.lock), 100 %
OK: 100 % identical to the tested set
== 5. smoke launch on 127.0.0.1:18650
healthy: hibiscus-station 1.0.0a1 state=disconnected
/assets/index-Do-kvUZI.js -> text/javascript; charset=utf-8
== DRY RUN OK: hibiscus-station 1.0.0a1 installs without git, with the locked libraries, and serves the UI
```

## 2. Bảng kết quả

| Mục (phạm vi M0) | Kết quả | Bằng chứng / lý do |
|---|---|---|
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-32 – QD-34) | Mọi bước AT-77 đạt trên bản cài (§3.1 – §3.5); 3 lỗi mới trong kết luận về động cơ (§3.6, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô 0–4, 13–15, 56–70; **0** dòng `DEBUG` |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ thật (tệp `token`, 43 ký tự), PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_hgcv…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong 1 609 lượt lưới + các lượt AT-77 |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | Nhà demo do `--mock` của bản cài tạo (`127.0.0.1:18652`), `doctor --home …/station-demo --no-cameras` (exit 0): `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`, `! no profile for a real arm: Robot > New robot, pick the arm's serial port`; `demo_so101 (active): cameras front, wrist`; `pid 4137692: mode MOCK, state disconnected` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 4105682 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 4105976: python3 -c … close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 4105682, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS ở bus sạch và ở lưới lần 8 / 9 · **FAIL** ở các kiểu lỗi mới (QD-32 – QD-34) | Bus sạch: `calibration file vs motors: all 6 match`, LIKELY PROBLEMS chỉ có `no calibration 'desk_leader'` (đúng: leader chưa hiệu chỉnh); tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …`; tệp follower lệch (pty mới): `gripper range_max: file 3000 motor 3231`, cả khi mất 10 % gói. Bus lỗi: §3.6 |
| **QD-28** gói hỏng đổi byte id | **PASS** | §3.6.2: 45 / 45 lượt đổi byte id (mọi servo 1 – 5 → 6, mọi độ dài câu trả lời doctor hỏi) + 3 / 3 tái hiện lần 9: servo 6 chết luôn là `do not answer (power? cable?)` |
| **QD-29** mọi câu trả lời bị cụt | **PASS** | §3.6.2: cả 6 servo `answer only with malformed packets`, kể cả leader, hai tay, servo 6 chết + cụt 100 % |
| **QD-30** câu trả lời trễ tính cho servo | **PASS** ở tình huống đã báo (khựng ≤ 300 ms, bộ chuyển 200 ms) · khựng dài hơn: QD-33 | §3.6.3 |
| **QD-31** tốc độ đo sai khi bộ chuyển chậm | **PASS** ở tình huống đã báo (50 ms, 260 ms, đường ống 300 ms) · 49 ms đường ống: QD-34 | §3.6.4 |
| Lưới lỗi bus của QC (kết luận về động cơ) | **FAIL** (QD-32 – QD-34) | §3.6 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44175485057 xanh 12 / 12 (python linux / windows / macos, e2e Chromium / Firefox / Edge, cài Windows + `--mock` smoke, macOS cài smoke, image, web, deploy, release assets) |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git, libraries == uv.lock, --mock smoke)` xanh. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit (§4). Luồng chính bằng chuột trên **bản cài** (§3.5) |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test + giả lập bộ chuyển chậm) · chạy thật NOT VERIFIED | Bộ chuyển chậm đều 30 – 240 ms: `slow bus (… ms per read)` với lời khuyên "only if the adapter is an FTDI chip (USB VID 0403)"; ≥ 250 ms: `slow bus (slower than the timeout: > 250 ms per read)`; 0 lần "slow bus" ở bộ chuyển nhanh. Lời khuyên sai ở 49 ms: QD-34 |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2; mọi giá trị đúng hoặc `?` ở 1 609 lượt (§3.6.1) |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.5) + CI |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng (CI) + local pytest và e2e: `skips on linux: all in the published list` |
| FL-12 dry run phát hành | **PASS** | §1 |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.5 |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows xanh |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3 – 9 |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-32 – QD-34) | Không có dict / list / `None` / `True` / `False` / `Traceback` trong 1 609 stdout của lưới; giờ tệp hiệu chỉnh đúng ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` trên cây của commit (`git archive`): `no leaks found`; 7 commit mới `2e65c94..71ec534` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật hay email; wheel và sdist không chứa đường dẫn home hay email |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục QD-28 – QD-31 |
| Vệ sinh phát hành: nội dung tài sản phát hành | PASS | §1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r10/…/user` mới cho mỗi lượt, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin`
(không đặt `TZ`). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy) do một
tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty, đếm `read`, `write`, `sync_read`, `sync_write`
và **số gói mỗi servo thật sự gửi**. Hồ sơ `desk` (`so101_follower` / `so101_leader`). Ở lưới lỗi (§3.6) tệp hiệu chỉnh
của follower nằm **đúng chỗ Station dùng** và **khớp** EEPROM, nên mọi câu "does not match" đều sai; sự thật của từng
thanh ghi lấy từ lượt bus sạch `--verbose` của chính bản cài.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-18 05:21:01 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
  follower desk_follower            so101_follower  2026-11-18 05:21:01 UTC+07:00  …
…
  desk follower on /dev/pts/8: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.59 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
```

Lệnh giả lập nhận ở một lượt bus sạch: mỗi tay `read 42, sync_read 20`, **write 0, sync_write 0**.

Khi Station (bản cài, `127.0.0.1:18651`) đang chạy và đã kết nối `desk` (`POST /api/v1/robots/desk/connect` → `200`):
`pid 4105682: mode real, state idle`; hai cổng `skipped, in use by Station (pid 4105682); stop it to ping the motors`;
mục **WHAT TO SEND / CẦN GỬI GÌ** có câu "The motor check is incomplete …". Lệnh ghi của giả lập chỉ tăng lúc Station
kết nối (69 / 36), không tăng trong lượt doctor (trước 69 / 36, sau 69 / 36; `sync_read` tăng là vòng đọc của chính
Station).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài (sau khi Station đã chạy trong HOME đó, nên tệp `token` là token thật): token cục bộ ở dạng thô và sau
`auth?t=` trong `logs/station.log`; một PAT đúng định dạng `hbp_<8>_<43>` (mới sinh) trong `station.log`,
`server.json`, `sessions/s-qc/session.json`; biến môi trường `HF_TOKEN=hf_QCr10…`, `GITHUB_TOKEN=ghp_QCr10…`. Zip chứa
`robots.yaml, report.txt, report.json, station.log.tail, sessions/s-qc.json` và tệp hiệu chỉnh. Kết quả (zip / stdout):

```
token file chars: 43
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_hgcv… used"
server.json trong zip: 0
```

Như lần 9: lượt đầu của kịch bản (trước khi Station từng chạy, chưa có tệp `token`) dùng một chuỗi ngẫu nhiên không
phải token của Station và chuỗi đó vẫn nằm trong `station.log.tail` / `report.json` (2 tệp): đúng, doctor không thể
biết một chuỗi bất kỳ là bí mật.

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`2026-11-18 05:21:11 +0700`), `doctor --no-ping --no-cameras`:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-18 05:21:11 UTC+07:00` | `…-20261118-052111.zip` |
| `UTC` | `2026-11-17 22:21:11 UTC+00:00` | `…-20261117-222113.zip` |
| `Asia/Kolkata` | `2026-11-18 03:51:11 UTC+05:30` | `…-20261118-035114.zip` |
| `America/St_Johns` | `2026-11-17 18:51:11 UTC-03:30` | `…-20261117-185115.zip` |
| `Pacific/Chatham` | `2026-11-18 12:06:11 UTC+13:45` | `…-20261118-120616.zip` |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (lệnh `hibiscus-station` của môi trường test được trỏ tạm về
`<dry-run>/home/.local/bin/hibiscus-station`, trả lại sau khi chạy) và giao diện tĩnh lấy từ **wheel đã cài**:
`3 passed in 151.13s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối → hiệu chỉnh follower → leader → Kiểm tra → camera
→ teleop → dừng an toàn → ghi tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop → Chương trình.

### 3.6 Lưới lỗi của QC trên bản cài: kết luận của `doctor` về động cơ

1 609 lượt `hibiscus-station doctor --no-cameras` của bản cài, Station tắt, mỗi lượt một HOME và một cặp pty mới:

* **Lưới lần 8 / lần 9 lặp lại, 922 lượt**: lưới chính 576 (mất gói 0 – 100 % × sai checksum 0 – 40 % × servo im
  không / 6 / 2 + 4 / cả 6 × bộ chuyển 0.5 / 9 ms × hạt giống 1, 2); lượt đặc biệt lần 8, 91; tấn công lần 9, 238 (bộ
  chuyển đường ống / chặn 2 – 300 ms, gói hai mảnh, lật bit ở mọi byte, dội lệnh, đúng một câu trả lời trễ ở mọi khối
  thanh ghi, khựng ngẫu nhiên); tái hiện lần 9, 17.
* **Tấn công mới của lần 10, 687 lượt**:
  * nhiễu trên đường dây (một khung rác có đầu `FF FF`, id ngẫu nhiên hoặc id 6, checksum sai, sau 1 / 2 / 5 / 20 %
    lệnh) × servo sống / 6 chết / cả 6 chết × hạt giống;
  * bộ chuyển trễ ngẫu nhiên (đều trong 0 – 20, 0 – 60, 30 – 70, 40 – 60, 0 – 300, 200 – 300 ms) ± servo 6 chết;
  * servo có điện muộn (id 3 / 6 im trong 1 – 60 giao dịch đầu); một id lạ (7) trên bus ± mất gói / servo 6 chết /
    bộ chuyển 60 ms; mất mọi câu trả lời trong một khoảng giao dịch (rung cáp) ± servo 6 chết;
  * QD-28: câu trả lời của servo 1 – 5 có byte id thành 6 (hoặc 3) ở **mọi độ dài** doctor hỏi (0, 1, 2, 3, 5, 6, 15,
    16, 17 byte), servo đích chết / sống, 57 lượt;
  * QD-29: gói cụt 50 / 80 / 100 % × hạt giống 1 – 4 ± servo 6 chết, leader, hai tay, byte rác 100 % + servo 6 chết;
  * QD-30: đúng một lần khựng 60 ms – 1.5 s ở lệnh quét / ping id 1 / ping id 3 / sync read / đọc thanh ghi, ± servo 6
    chết; khựng ngẫu nhiên 2 / 5 % × 300 / 600 ms; khựng 400 ms ở ping id 1 × 10 hạt giống;
  * QD-31: bộ chuyển chậm đều (chặn và đường ống) 30 – 400 ms, 45 – 52 ms từng ms × 3 lần, ± servo 6 chết, ± mất 10 %,
    leader;
  * tổ hợp: servo 6 chết + khựng + lật bit / sai checksum / trễ ngẫu nhiên (30 lượt); gói hai mảnh 16 / 60 ms ± dội
    lệnh ± đường ống + servo 6 chết (24 lượt);
  * **300 tổ hợp ngẫu nhiên** (hạt giống cố định) của mọi kiểu lỗi trên (mất, checksum, lật bit, cụt, rác, nhiễu, trễ,
    đường ống, khựng, hai mảnh, dội lệnh, trễ ngẫu nhiên, servo chết, servo chập chờn), follower hoặc leader.

Mỗi báo cáo được đối chiếu với **sự thật của tình huống**: từng trường của dòng `id N` và dòng giải mã phải bằng giá
trị thật hoặc `?`; từng khối dump thô phải là byte thật hoặc chữ báo lỗi; servo nào thật sự gửi gói (đếm ở giả lập);
tệp hiệu chỉnh khớp; bộ chuyển nhanh hay chậm, chậm đều hay khựng; và giữa các dòng của chính nó.

| Phép kiểm của QC (1 609 báo cáo) | Số báo cáo sai |
|---|---|
| Lệnh ghi động cơ (`write`, `sync_write`) | **0** |
| `Traceback`, giá trị Python trong chữ | **0** |
| Giá trị thanh ghi / giá trị giải mã / byte thô sai in ra như thật | **0** |
| "status overheat / overload …" giả, "impossible …" trong LIKELY PROBLEMS | **0** |
| Tệp **khớp** mà LIKELY PROBLEMS nói `does not match … calibrate the arm again` | **0** |
| Dòng quét `ids answering` ≠ tập servo có dòng; id lạ 7 không được nêu "other ids on the bus" | **0 / 0** |
| "slow bus" ở bộ chuyển nhanh; bộ chuyển chậm đều không được báo "slow bus"; số đo nhanh hơn bộ chuyển có thể; số Hz ở bộ chuyển chậm hơn thời gian chờ dài nhất | **0 / 0 / 0 / 0** |
| Servo nêu `do not answer (power? cable?)` mà giả lập ghi nó **có** gửi gói | **0** (mọi lượt bị nêu, kể cả servo mất 90 % và servo có điện muộn, giả lập đếm 0 gói) |
| Servo nêu `do not answer` mà dump thô / dòng giá trị của chính báo cáo có câu trả lời | **0** (QD-29 đóng) |
| Servo **mất điện** (giả lập: 0 gói) không được nêu `do not answer` | **8** (QD-32: nhiễu 2 – 20 %, 5 hạt giống / tổ hợp; 3 / 3 lượt chạy lại giống hệt) |
| Lỗi chỉ về thời gian (khựng / chậm), không servo nào lỗi, mà một servo bị gọi "answer only now and then" | **24** (QD-33: khựng ≥ 350 ms ở ping, ≥ 700 ms ở quét, khựng ngẫu nhiên 600 ms) |
| Bộ chuyển chậm đều được khuyên kiểm cáp 3 chân / nguồn | **4** (QD-34: đường ống 49 ms, 4 / 4 lượt) |

#### 3.6.1 Giá trị đúng hoặc `?` (QD-25 vẫn đóng)

Ở 1 609 lượt, kể cả khựng 1.5 s, nhiễu, trễ ngẫu nhiên 0 – 300 ms, gói hai mảnh, dội lệnh và 300 tổ hợp ngẫu nhiên:
**0** giá trị sai. Khối không đọc được là `?` / `could not read (no valid answer in 3 tries)`, dump thô `no answer` /
`corrupted answer (checksum)` / `malformed answer …`, giải mã `-`.

#### 3.6.2 QD-28, QD-29 (đóng)

Byte id bị đổi (một câu trả lời của servo 2 thành "servo 6", servo 6 chết; 45 biến thể mọi servo × mọi độ dài):
`! desk follower: motor id(s) 6 do not answer (power? cable?)`, `ids answering at 1 Mbps: 1-5 (model 777)`, `id 6: no
answer`; ở lần đọc của servo bị đổi byte: `5 answered only on a retry` (đúng). Gói cụt 100 %: `motor id(s) 1, 2, 3, 4,
5, 6 answer only with malformed packets (cut short or the wrong length)`, mỗi dòng `id N: answers only with malformed
packets …, no register could be read`, dump thô `malformed answer` ở mọi khối, `sync read: 20/20 failed (20 got
malformed answers …)`; với servo 6 chết: `motor id(s) 6 do not answer (power? cable?)` + `1, 2, 3, 4, 5 answer only
with malformed packets`.

#### 3.6.3 QD-30 (đóng ở tình huống đã báo)

Khựng 300 ms lúc quét (2 / 2): `! desk follower: unreliable bus: 6 answers came late (up to 301 ms after the request:
the USB adapter or a hub stalled); plug the USB adapter straight into the PC, without a hub, and run the doctor
again`, không servo nào bị gọi chập chờn. Bộ chuyển chặn 200 ms: chỉ `slow bus (200.42 ms per read)`, `~4 Hz`. Đường
ống 60 ms + servo 6 chết: chỉ `motor id(s) 6 do not answer (power? cable?)`, không còn "check the 3-pin cables". Khựng
dài hơn: QD-33.

#### 3.6.4 QD-31 (đóng ở tình huống đã báo)

Bộ chuyển đều 50 ms: `sync read: 0/20 failed, 50.34 ms each`, `~15 Hz`, chỉ `slow bus (50.34 ms per read)`. 260 ms và
đường ống 300 ms: `sync read: 20/20 answered only after the timeout, slower than the timeout (> 250 ms per read)`,
`teleop estimate: not measured (slower than the timeout (> 250 ms per read))` + lời khuyên slow bus. Chặn 45 – 52 ms
(từng ms, 3 lần): đúng `45.4 – 52.4 ms each`, chỉ "slow bus". Đường ống 45 – 48 và 50 – 52 ms: đúng. Đường ống 49 ms:
QD-34.

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `71ec534`)

| Kiểm | Kết quả |
|---|---|
| `uv lock --check`, `uv sync --locked` | exit 0 |
| ruff check / format | `All checks passed!` · `142 files already formatted` |
| mypy --strict (Linux, `--platform win32`, `--platform darwin`, `tools/release tools/ci`) | `Success: no issues found in 84 source files` ×3 · `in 5 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api, coverage | exit 0 cả năm |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `761 passed, 1 skipped, 444 deselected, 1 warning` (skip trong danh sách) · `skips on linux: all in the published list` |
| pytest lưới `slow` của dev (`tests/test_doctor.py -m slow`) | `436 passed, 183 deselected in 2320.79s` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 504.03s` · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 146.32s` |
| e2e trên bản cài (§3.5) | `3 passed in 151.13s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng). Các test của dev xanh nhưng không bắt
được QD-32 – QD-34: giả lập của dev không có khung nhiễu ngoài câu trả lời, các lần khựng của dev ngắn hơn ba lần thử
ping, và không có bộ chuyển đường ống ở đúng ngưỡng 49 ms.

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-31

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
| QD-16 | Đóng | Không có giá trị Python trong 1 609 stdout |
| QD-17 | Đóng | Dry run: `OK: no uv PATH warning`; dòng PATH song ngữ |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ) |
| QD-20 | Đóng | §1: sdist 283 mục, trùng byte với CI |
| QD-21 | Đóng | Lưới lần 8 (servo 6 im, cả tay im, leader im, bộ chuyển 20 ms) |
| QD-22 | Đóng | Lưới lần 8 (mất 5 % hạt giống 1, 4; checksum 5 %) |
| QD-23 | Đóng | Lưới lần 8 (mất 35 % hạt giống 4) |
| QD-24 | Đóng | Dòng quét = tập dòng servo ở 1 609 / 1 609 báo cáo |
| QD-25 | Đóng | §3.6.1 |
| QD-26 | Đóng | 0 "does not match" khi tệp khớp ở 1 609 lượt |
| QD-27 | Đóng | Lưới lần 8 (checksum 40 % hạt giống 2, mất 20 % + checksum 5 %, mất 50 %, servo 4 chập chờn 90 %) |
| QD-28 | **Đóng** | §3.6.2 (3 / 3 tái hiện + 57 biến thể đổi byte id; QD-32 là nguồn gói hỏng khác) |
| QD-29 | **Đóng** | §3.6.2 |
| QD-30 | **Đóng** ở tình huống đã báo | §3.6.3 (khựng dài hơn: QD-33) |
| QD-31 | **Đóng** ở tình huống đã báo | §3.6.4 (49 ms đường ống: QD-34) |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-32 · Low · F-63 (AT-77, FL-11; tính hợp lý, báo cáo không tự mâu thuẫn) · Một gói hỏng lạc trên đường dây (nhiễu)
trong lúc hỏi servo mất điện làm nó thành "answers only with corrupted packets"; "do not answer (power? cable?)" biến
mất.**
Bước: servo 6 không có điện / rút cáp; đường dây có nhiễu thỉnh thoảng tạo một khung có đầu `FF FF` và checksum sai
(cáp dài, nguồn servo bẩn, servo không nguồn nhưng còn nối dây tín hiệu); `hibiscus-station doctor --no-cameras` (QC:
bản cài, giả lập, servo 6 chết, khung nhiễu sau 2 / 5 / 20 % lệnh; 8 lượt ở các hạt giống / tổ hợp khác nhau, 3 / 3 lượt
chạy lại giống hệt; giả lập đếm **0 gói** từ servo 6, chỉ 2 khung nhiễu trong cả lượt `dead6-noise0.02-s3`).
Kỳ vọng (như kỳ vọng đã ghi ở QD-28 lần 9): servo không gửi một gói hợp lệ nào trong ~25 lệnh hỏi nó vẫn là `do not
answer (power? cable?)`, kèm `unreliable bus` cho gói hỏng; "answers only with corrupted packets" chỉ khi gói hỏng là
câu trả lời thường xuyên của servo đó (như QD-29: mọi lệnh đều có gói cụt).
Thực tế: `! desk follower: unreliable bus: 20 of 20 reads failed (19 got no answer, 1 got corrupted answers (checksum)),
motor id(s) 6 answer only with corrupted packets (checksum); check the 3-pin cables …`; dòng quét `1-5 (model 777); 6
(model ?); 6 answer only with corrupted packets`; dòng `id 6: answers only with corrupted packets (checksum), no register
could be read` trong khi cùng báo cáo: dump thô `id 6: [0-4] no answer  [13-15] no answer  [56-70] no answer`, `bus
errors: 44 … (sync_read 56-57 [6] x20, ping [6] x3, read 0-16 [6] x3, read 28-33 [6] x3, read 40-40 [6] x3, read 55-70
[6] x3, read 0-4 [6] x3, read 13-15 [6] x3, read 56-70 [6] x3)` (24 lệnh hỏi riêng servo 6, không lệnh nào có câu trả
lời) và `sync read: … 19 got no answer`. `report.json`: servo 6 `evidence {"corrupt": 1, "valid": 0, "late": 0, …}`,
`state "corrupt"`. Không còn dòng nào nói servo 6 im hay mất nguồn.
Nguyên nhân QC thấy: `Probe._damage()` (`hibiscus_station/hw/probe.py`) tính mọi gói hỏng đến trong lúc hỏi một servo
cho servo đó (`ev.corrupt += 1`), và `motor_state()` / `bus_verdict()` (`doctor.py`) coi **một** gói hỏng là đủ để servo
thành `corrupt` (không còn `silent`), bất kể bao nhiêu lệnh hỏi nó không có gì.

**QD-33 · Low · F-63 (AT-77, FL-11; tính hợp lý, báo cáo không tự mâu thuẫn) · Một lần khựng USB từ 350 ms lúc ping
(từ 700 ms lúc quét) làm servo trả lời mọi lệnh bị gọi "answer only now and then", kèm lời khuyên kiểm cáp 3 chân và
nguồn.**
Bước: bus sạch, mọi servo có điện; một lần khựng USB 350 ms – 1.5 s đúng lúc doctor ping một servo (hoặc 700 ms – 1.5 s
lúc lệnh quét); `hibiscus-station doctor --no-cameras` (QC: ping id 3 khựng 350 / 400 / 450 / 500 / 600 / 700 ms, ping
id 1 khựng 400 ms × 10 hạt giống, 500 / 900 ms / 1.5 s, quét 700 / 900 ms / 1.5 s, khựng ngẫu nhiên 2 – 5 % × 600 ms:
24 lượt, xác định; khựng 300 ms thì đúng).
Kỳ vọng (như kỳ vọng QD-30 lần 9): câu trả lời trễ cho ping là câu trả lời (servo có điện, nối đúng; `LATE_HORIZON_S`
của chính probe là 2 s); servo đã trả lời lần quét, 20 / 20 sync read và mọi thanh ghi không bị gọi chập chờn; lỗi nêu ở
mức bus (khựng USB) với lời khuyên về USB.
Thực tế (ping id 3 khựng 350 ms): `! desk follower: unreliable bus: motor id(s) 3 answer only now and then (no valid
answer to 3 pings), 3 answers came late (up to 351 ms after the request: the USB adapter or a hub stalled); check the
3-pin cables between the servos, the power supply (it may drop under load) and plug the USB adapter straight into the
PC`; dòng quét `1-6 (model 777); 3 answer only now and then (no ping answered)`; dòng servo 3 `answers only now and
then: no valid answer to 3 pings, but answered the scan, 20 of 20 sync reads, 3 late answers`; `bus errors: 3, 0
retried ok, 3 late answers (ping [3] x3)`, `late_ms [350.59, 249.62, 148.23]` (cả ba câu trả lời ping đều đến và được
ghép đúng ping của chúng); `sync read: 0/20 failed, 0.74 ms each`, `~250 Hz`. Khựng quét 1.5 s: cả 6 servo "answer only
now and then" + `1 of 20 reads failed`.
Nguyên nhân QC thấy: `Probe.ping()` trả `False` sau ba lần thử (mỗi lần chờ tối đa hạn chờ, cộng một hạn chờ nữa nếu
servo đã từng trả lời: ~300 ms), trước khi câu trả lời trễ đến; câu trả lời đó sau này được ghép đúng ping của nó
(`late`), nhưng `motor_state()` vẫn dựa vào `ping_ok` nên servo thành `flaky`; `bus_verdict()` khi có servo `flaky`
chọn `BUS_ADVICE` (cáp, nguồn) thay vì `USB_ADVICE`.

**QD-34 · Low · F-63 (AT-77, D-21; tính hợp lý của lời khuyên) · Bộ chuyển chậm đều 49 ms (dạng đường ống) bị kết luận
"unreliable bus … check the 3-pin cables between the servos, the power supply".**
Bước: bus sạch, bộ chuyển USB trả mọi câu trả lời đều 49 ms sau lệnh (đệm, giữ thứ tự: hub / bộ chuyển chậm);
`hibiscus-station doctor --no-cameras` (QC: đường ống 49 ms, 4 / 4 lượt, xác định; 45 – 48 và 50 – 52 ms thì đúng).
Kỳ vọng (như kỳ vọng QD-31 lần 9): `slow bus (≈50 ms per read)`, không nêu "unreliable bus … check the 3-pin cables"
khi mọi servo trả lời đều và câu trả lời trễ là của một bộ chuyển chậm đều (như nhánh có servo im đã làm: "an answer
that came late, from an adapter slow every time, is not a failure of the bus").
Thực tế: `! desk follower: unreliable bus: 1 of 20 reads failed (1 got their answers only after the timeout) although
every motor answers a ping; check the 3-pin cables between the servos, the power supply (it may drop under load) and
plug the USB adapter straight into the PC` cạnh `! desk follower on /dev/pts/12: slow bus (49.82 ms per read) …`;
`sync read: 1/20 failed (1 got their answers only after the timeout), 19 worked, 49.82 ms each`; `late_ms` 6 × `50.14`
(chỉ hơn hạn chờ 50 ms một chút, `steady_slow()` = đúng).
Nguyên nhân QC thấy: `bus_verdict()` (`doctor.py`) chỉ bỏ các lần sync read thất bại do câu trả lời trễ của bộ chuyển
chậm đều ở nhánh có servo im (`others = … set(r.values()) != {"late"}`); ở nhánh không có servo im, `failed` vẫn gồm lần
"late" đó và thành `1 of 20 reads failed … although every motor answers a ping` với `BUS_ADVICE`. Ghi chú hiện thực:
cửa sổ ~1 ms quanh hạn chờ (lần sync read đầu, gói dài hơn ping một chút, vượt 50 ms), hiếm gặp; lỗi là lời khuyên sai
(cáp, nguồn) cho một bộ chuyển chậm.

### 5.3 Ghi nhận (không phải lỗi)

* Bộ chuyển chậm đều **và** có servo im (ví dụ 260 ms + servo 6 chết): LIKELY PROBLEMS chỉ nêu `motor id(s) 6 do not
  answer (power? cable?)`, không nêu slow bus (dòng sync read ghi `20 got their answers only after the timeout`). Đúng
  bảng kết luận đã duyệt (servo im: "slow-bus advice never"); khách sửa servo rồi chạy lại sẽ thấy slow bus.
* Lưới `win5-200` (mọi câu trả lời mất sau giao dịch thứ 5): servo 4 – 6 "answer only now and then … but answered the
  scan", servo 1 – 3 có ping, mọi thanh ghi `?`: đúng sự thật (chúng đã trả lời trước khi mất).
* Chương trình giữ cổng có dòng lệnh chứa ký tự xuống dòng làm mục "busy, held by pid …" xuống dòng giữa chừng (từ lần
  8; chương trình thật không có dòng lệnh như vậy).
* pytest local báo `1 warning` (lần 9 không có); không làm test nào fail, QC chưa xem nội dung (lệnh của QC chỉ giữ 6 dòng
  cuối).
* Kịch bản AT-77 của QC đọc `station.pid` dạng một số; tệp nay là JSON (`{"pid": …, "port": …}`), QC sửa kịch bản và chạy
  lại bước 5 (doctor của bản cài đọc đúng tệp này: "station.pid of pid … left behind").

## 6. Người dùng cần kiểm giúp (NOT VERIFIED)

Như lần 9: VM Windows 11 sạch với lệnh `irm … | iex` từ bản nháp GitHub; VID:PID và lời khuyên WCH với bộ chuyển CH340
/ CH343 thật; `doctor --verbose` trên tay thật của khách (REG-13); hiển thị UTF-8 trên console Windows. Chỉ giao UAT-0
khi F-63 PASS.
