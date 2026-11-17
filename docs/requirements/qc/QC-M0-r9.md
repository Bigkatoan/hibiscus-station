# QC M0 lần 9: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-18

**Kết luận: M0 = FAIL.** QD-25, QD-26, QD-27 của [lần 8](QC-M0-r8.md) đã sửa đúng ở đúng tình huống đã báo: lượt CI
của đúng commit ứng viên **xanh 12 / 12**; trên bản cài, câu trả lời đến trễ (một lần, ngẫu nhiên, bộ chuyển chậm
4 – 200 ms) **không còn thành giá trị**: ở 922 lượt `doctor` của lưới QC, mọi giá trị thanh ghi, giá trị giải mã và
byte thô in ra đều **đúng sự thật hoặc là `?` / "no answer"** (0 giá trị sai); lần đọc thất bại là "could not read …
(a bus problem, not the calibration)", **0** lần "does not match … calibrate the arm again" khi tệp khớp; servo có trả
lời trên bus chập chờn không còn bị gọi "do not answer (power? cable?)" ở các tình huống QD-27. QD-1 – QD-27 đóng.
Wheel, sdist, `install.ps1`, `constraints.txt` QC tự build **trùng byte** với CI; mọi bước AT-77 [Vendor] đạt trên bản
cài; **0 lệnh ghi động cơ** qua 922 lượt. Nhưng lưới lỗi riêng của QC lần này thêm kiểu lỗi mới (byte hỏng ở bất kỳ vị
trí nào kể cả byte id, gói bị cắt cụt ở mọi câu trả lời, bộ chuyển chậm dạng đường ống, gói đến thành hai mảnh, bộ
chuyển dội lại lệnh, một lần khựng bus 300 ms) và tìm ra **4 lỗi mới (Low)** trong kết luận về động cơ của `doctor`:
**QD-28** một gói hỏng có byte id bị đổi làm servo **mất điện** thành "answers only with corrupted packets", không còn
"do not answer (power? cable?)"; **QD-29** khi mọi câu trả lời bị cụt, servo 2, 4, 6 bị kết luận `do not answer (power?
cable?)` trong khi dump thô của chính báo cáo ghi chúng gửi `malformed answer`; **QD-30** câu trả lời đến trễ bị tính
cho servo: một lần khựng bus 300 ms lúc quét làm servo 1 "answer only now and then" dù nó trả lời 20 / 20 sync read và
mọi thanh ghi; **QD-31** tốc độ bus đo sai khi bộ chuyển chậm bằng / hơn thời gian chờ (50 ms → `44.66 ms each` kèm
"unreliable bus … check the 3-pin cables"; 260 ms → `31.06 ms each`, `~24 Hz`). Theo quy tắc không lỗi
(zero-defect): **F-1 / P-1 phần M0 đạt**, **phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-28 –
QD-31). Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit. Lưới lỗi
là của riêng QC (tiến trình giả lập riêng dựa trên `tests/sts_emulator.py` chỉ để mô phỏng servo; các kiểu lỗi, phép
đối chiếu với sự thật và bộ đoán đúng / sai là của QC), không dùng lại lưới hay cơ chế "late" mới của dev trong
`tests/sts_emulator.py`.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `7a7f6c4e0c39ff01c080c13b733292d3d865e138` (HEAD trên origin lúc QC bắt đầu và lúc kết thúc) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44128881465 (push `release/v1`, `head_sha` = `7a7f6c4e…`, lần chạy 1) → **completed / success, 12 / 12 job xanh** (đã xong trước khi QC bắt đầu) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `4e68f5c77ca199361e6c61f4cb5e29d2ee5bef298a039be6ce76b578b63f34fd`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `e78ce3b53f603a95dc86a4209de1ee1fee92af3efe61fd964a45a18ba05b4aeb`, 283 mục, 0 mục `node_modules` / `tests/`: **trùng byte** với sdist của CI |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git; **nội dung 709 / 709 tệp trùng**, chỉ khác giờ / quyền trong zip như lần 3 – 8), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` → `pnpm install --frozen-lockfile` + `pnpm build` → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (không git, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock); giả lập: tiến trình riêng của QC (2 chuỗi STS3215 trên pty, phía slave đóng như bộ chuyển USB thật, đếm mọi lệnh) với các kiểu lỗi của QC (§3.6) |

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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-28 – QD-31) | Mọi bước AT-77 đạt trên bản cài (§3.1 – §3.5); 4 lỗi mới trong kết luận về động cơ (§3.6, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô 0–4, 13–15, 56–70; **0** dòng `DEBUG` |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ thật (tệp `token`, 43 ký tự), PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_XloD…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong 922 lượt doctor có đếm lệnh + các lượt AT-77 |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | Nhà demo do `--mock` của bản cài tạo (`127.0.0.1:18652`), `doctor --home …/station-demo --no-cameras` (exit 0): `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`, `! no profile for a real arm: Robot > New robot, pick the arm's serial port`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null`; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 3386507 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong stdout và `report.txt` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/22 is busy, held by pid 3386823: python3 -c … close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 3386507, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS ở bus sạch và ở lưới chính · **FAIL** ở các kiểu lỗi mới (QD-28 – QD-31) | Bus sạch: `calibration file vs motors: all 6 match`, `No likely problems found`; tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …`. Bus lỗi: §3.6 |
| **QD-25** câu trả lời trễ thành giá trị | **PASS** | §3.6.2: 0 giá trị sai ở 922 lượt |
| **QD-26** đọc lỗi = tệp không khớp | **PASS** | §3.6.3 |
| **QD-27** servo có trả lời bị gọi "do not answer" | **PASS** ở các tình huống đã báo | §3.6.4 (tình huống mới QD-29 là lỗi khác) |
| Lưới lỗi bus của QC (kết luận về động cơ) | **FAIL** (QD-28 – QD-31) | §3.6 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44128881465 xanh 12 / 12 (python linux / windows / macos, e2e Chromium / Firefox / Edge, cài Windows + `--mock` smoke, macOS cài smoke, image, web, deploy, release assets) |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git, libraries == uv.lock, --mock smoke)` xanh. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit (§4). Luồng chính bằng chuột trên **bản cài** (§3.5) |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test + giả lập bộ chuyển chậm) · chạy thật NOT VERIFIED | Bộ chuyển chậm 9 – 200 ms được báo `slow bus (… ms per read)` với lời khuyên "only if the adapter is an FTDI chip (USB VID 0403)"; 0 lần "slow bus" ở bộ chuyển nhanh. Tốc độ đo sai ở ≥ 50 ms: QD-31 |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2; mọi giá trị đúng hoặc `?` ở 922 lượt (§3.6.2) |
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
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Như lần 3 – 8 |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-28 – QD-31) | Không có dict / list / `None` / `True` / `False` / `Traceback` trong 922 stdout của lưới; giờ tệp hiệu chỉnh đúng ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` (v8.30.1) trên cây của commit (`git archive`): `no leaks found`; 4 commit mới `841f60c..7a7f6c4` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật; wheel và sdist không chứa đường dẫn home hay email |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`; CHANGELOG `[Unreleased]` có mục QD-25 / QD-26 / QD-27 |
| Vệ sinh phát hành: nội dung tài sản phát hành | PASS | §1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r9/…/user` mới cho mỗi lượt, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin`
(không đặt `TZ`). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy) do một
tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty và đếm `read`, `write`, `sync_read`,
`sync_write`. Hồ sơ `desk` (`so101_follower` / `so101_leader`). Ở lưới lỗi (§3.6) tệp hiệu chỉnh của follower nằm
**đúng chỗ Station dùng** và **khớp** EEPROM, nên mọi câu "does not match" đều sai; sự thật của từng thanh ghi (cả
`pos`, cố định trong giả lập) lấy từ lượt bus sạch `--verbose`.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-18 00:15:34 +0700
$ ls -l desk_follower.json              -> 2026-11-18 00:15:34 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
  follower desk_follower            so101_follower  2026-11-18 00:15:34 UTC+07:00  …
…
  desk follower on /dev/pts/20: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.77 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~3.0 ms
```

Lệnh giả lập nhận ở một lượt bus sạch: mỗi tay `read 42, sync_read 20`, **write 0, sync_write 0**.

Khi Station (bản cài, `127.0.0.1:18651`) đang chạy và đã kết nối `desk` (`POST /api/v1/robots/desk/connect` → `200`):
`pid 3386507: mode real, state idle`; hai cổng `skipped, in use by Station (pid 3386507); stop it to ping the motors`;
mục **WHAT TO SEND / CẦN GỬI GÌ** có câu "The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi
của giả lập chỉ tăng lúc Station kết nối (69 / 36), không tăng trong lượt doctor (trước 69 / 36, sau 69 / 36).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ thật của Station (tệp `token`, 43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`;
một PAT đúng định dạng `hbp_<8>_<43>` (mới sinh) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến
môi trường `HF_TOKEN=hf_QCr9…`, `GITHUB_TOKEN=ghp_QCr9…`. Zip chứa `robots.yaml, report.txt, report.json,
station.log.tail, sessions/s-qc.json` và các tệp hiệu chỉnh. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_XloD… used"
server.json trong zip: 0
```

Ghi chú: một chuỗi ngẫu nhiên **không phải** token của Station (lần chạy đầu của kịch bản, trước khi Station từng chạy
trong HOME đó nên chưa có tệp `token`) thì vẫn nằm nguyên trong `station.log.tail`: đúng, doctor không thể biết một
chuỗi bất kỳ là bí mật. Phép kiểm được làm lại với token thật như lần 8.

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`2026-11-18 00:15:46 +0700`), `doctor --no-ping --no-cameras`:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-18 00:15:46 UTC+07:00` | `…-20261118-001546.zip` |
| `UTC` | `2026-11-17 17:15:46 UTC+00:00` | `…-20261117-171547.zip` |
| `Asia/Kolkata` | `2026-11-17 22:45:46 UTC+05:30` | `…-20261117-224549.zip` |
| `America/St_Johns` | `2026-11-17 13:45:46 UTC-03:30` | `…-20261117-134550.zip` |
| `Pacific/Chatham` | `2026-11-18 07:00:46 UTC+13:45` | `…-20261118-070051.zip` |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (lệnh `hibiscus-station` của môi trường test được trỏ tạm về
`<dry-run>/home/.local/bin/hibiscus-station`, trả lại sau khi chạy) và giao diện tĩnh lấy từ **wheel đã cài**:
`3 passed in 148.57s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối → hiệu chỉnh follower → leader → Kiểm tra → camera
→ teleop → dừng an toàn → ghi tập → bộ dữ liệu → nạp model ACT → chạy model → e-stop → Chương trình.

### 3.6 Lưới lỗi của QC trên bản cài: kết luận của `doctor` về động cơ

922 lượt `hibiscus-station doctor --no-cameras` của bản cài, Station tắt, mỗi lượt một HOME và một cặp pty mới:

* **Lưới chính, 576 lượt** (lặp lại lưới lần 8): mất gói 0 / 1 / 5 / 10 / 20 / 30 / 40 / 60 / 100 % × sai checksum 0
  / 5 / 20 / 40 % × servo im (không, id 6, id 2 + 4, cả 6) × bộ chuyển (0.5 ms, 9 ms) × hạt giống 1, 2.
* **Lượt đặc biệt của lần 8, 91 lượt**: bộ chuyển chậm 4 – 100 ms; servo chập chờn (id 1, 4, 6 mất 10 / 30 / 60 / 90 %);
  gói cụt / byte rác 5 / 30 / 100 %; servo 4 sụt nguồn sau 5 – 300 giao dịch; leader lỗi, hai tay lỗi, `--verbose`; câu
  trả lời trễ ngẫu nhiên (0.5 % / 2 % trễ thêm 60 / 150 ms, hạt giống 1 – 3); đúng một câu trả lời trễ (quét, ping,
  sync read); đúng các tình huống QD-21 – QD-27 của lần 6 – 8.
* **Tấn công mới của lần 9, 238 lượt**: bộ chuyển chậm **dạng đường ống** (servo vẫn trả lời, byte ra trễ 2 – 300 ms,
  giữ thứ tự) và dạng chặn 48 – 260 ms quanh thời gian chờ 50 ms / 250 ms của doctor; gói đến **thành hai mảnh** (5 / 30
  / 100 %, mảnh sau trễ 1 – 120 ms, ngay trước / đúng / sau hạn chờ); **lật một bit ở bất kỳ byte nào** (kể cả byte id,
  độ dài) 1 / 5 / 20 % × hạt giống 1 – 3 × servo 6 sống / chết; bộ chuyển **dội lại lệnh** (riêng, + servo 6 chết, +
  chậm 20 / 60 ms, + mất 10 %, + cả 6 chết, + gói hai mảnh); **đúng một câu trả lời trễ** 60 / 120 / 300 ms cho từng
  khối thanh ghi mới của doctor (0–16, 28–33, 40, 55–70) và khối dump thô (0–4, 13–15, 56–70) của id 1, 3, 6, cho ping
  id 1 / 6, sync read, quét; khựng ngẫu nhiên 5 / 10 % × 40 / 60 / 100 / 300 ms × hạt giống 1 – 4; kết hợp (servo chết
  + khựng, servo chập chờn + khựng, servo chết + bộ chuyển 60 ms + mất 5 %); hạt giống 3 – 6 cho mất / checksum / servo
  chập chờn / lật bit.
* **Tái hiện xác định, 17 lượt** (§5.2).

Mỗi báo cáo được đối chiếu với **sự thật của tình huống**: từng trường của dòng `id N` và dòng giải mã phải bằng giá
trị thật hoặc `?`; từng khối dump thô phải là byte thật hoặc chữ báo lỗi; servo nào có điện; tệp hiệu chỉnh khớp; bộ
chuyển nhanh hay chậm; và giữa các dòng của chính nó.

| Phép kiểm của QC (922 báo cáo) | Số báo cáo sai |
|---|---|
| Lệnh ghi động cơ (`write`, `sync_write`) | **0** |
| `Traceback`, giá trị Python trong chữ | **0** |
| Giá trị thanh ghi / giá trị giải mã / byte thô sai in ra như thật | **0** (QD-25 đóng) |
| "status overheat / overload …" giả, "impossible …" trong LIKELY PROBLEMS | **0** |
| Tệp **khớp** mà LIKELY PROBLEMS nói `does not match … calibrate the arm again` | **0** (QD-26 đóng) |
| Dòng quét `ids answering` ≠ tập servo có dòng | **0** |
| "slow bus" ở bộ chuyển nhanh / bộ chuyển chậm (bus sạch) không được báo | **0 / 0** |
| Có lần đọc thất bại mà LIKELY PROBLEMS không nêu bus (trừ mất 100 %: mọi servo im, đúng) | **0** |
| Servo **mất điện** không được nêu `do not answer` | 4 (QD-28: lật bit 20 % hạt giống 2; 3 / 3 lượt tái hiện) |
| Servo có trả lời bị nêu `do not answer (power? cable?)` (trừ mất 100 % và một lượt servo 1 mất 90 % mà thật sự không gửi gì) | 5 (QD-29: gói cụt 100 %, 2 lượt lần 8 + 3 lượt tái hiện) |
| Servo trả lời mọi lệnh bị gọi "answer only now and then" | lượt khựng 300 ms lúc quét (2 / 2 tái hiện), bộ chuyển 200 – 300 ms (QD-30) |
| Tốc độ đo nhanh hơn bộ chuyển có thể | bộ chuyển 50 – 51 ms (`42 – 45 ms each`), 260 – 300 ms (`27 – 85 ms each`) (QD-31) |

#### 3.6.1 QD-21 – QD-24 (vẫn đóng)

Mất 35 % hạt giống 4: `unreliable bus: 19 of 20 reads failed (19 got no answer), motor id(s) 5 answer only now and
then (no valid answer to 3 pings)`, dòng servo 5 `answers only now and then: no valid answer to 3 pings, but answered
9 of 20 sync reads`, `teleop estimate: not measured (too few reads succeeded: 1 of 20)`. Mất 5 % hạt giống 1:
`9/20 failed (9 got no answer), 11 worked, 0.86 ms each`, `unreliable bus … although every motor answers a ping`,
`calibration file vs motors: all 6 match`. Servo 6 im: chỉ `motor id(s) 6 do not answer (power? cable?)`,
`teleop estimate: not measured (motor id(s) 6 do not answer)`, không Hz. Bộ chuyển 20 ms: `slow bus (20.45 ms per
read)` + lời khuyên FTDI.

#### 3.6.2 Câu trả lời đến trễ (QD-25 đóng)

Đúng một câu trả lời trễ 60 ms / 120 ms / 300 ms ở mọi khối thanh ghi và khối dump thô: giá trị đúng (lần thử lại lấy
được câu trả lời hợp lệ), LIKELY PROBLEMS `unreliable bus: 1 answer came too late and was discarded`; ở 300 ms khối
không đọc được hiện `?` và `could not read (no valid answer in 3 tries): …`, dump thô `no answer`, giải mã `-`. Bộ
chuyển chậm 4 – 200 ms (chặn hoặc đường ống), khựng ngẫu nhiên 5 – 10 %, gói hai mảnh, dội lệnh: **0** giá trị sai. Ví
dụ bộ chuyển đường ống 100 ms: `1-6 (model 777)`, `sync read: 0/20 failed, 100.97 ms each`, `~7 Hz`, `slow bus
(100.97 ms per read)`, `calibration file vs motors: all 6 match`.

#### 3.6.3 Lần đọc lỗi không còn là "không khớp" (QD-26 đóng)

Mọi tỉ lệ mất / checksum / gói cụt / byte rác / lật bit: thanh ghi không đọc được là `calibration file vs motors: 5 of
6 match; gripper: could not read Homing_Offset, Min_Position_Limit, Max_Position_Limit` và LIKELY PROBLEMS `could not
read register(s) … (a bus problem, not the calibration): the calibration file 'desk_follower' could not be checked for
1 of 6 motors; fix the bus and run the doctor again`; `motors carry the calibration of: not known (some calibration
registers could not be read)`.

#### 3.6.4 Servo có trả lời trên bus chập chờn (QD-27 đóng ở tình huống đã báo)

Checksum 40 % hạt giống 2 (tình huống QD-27): không còn "do not answer"; `unreliable bus: 20 of 20 reads failed (20
got corrupted answers (checksum)) although every motor answers a ping`. Mất 20 % + checksum 5 %, mất 50 %, servo 4
chập chờn 90 %: servo có trả lời là "answered only on a retry" hoặc "answer only now and then … but answered N of 20
sync reads"; "do not answer" chỉ còn cho servo im thật. Servo sụt nguồn thật sau lần quét vẫn là "do not answer".

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `7a7f6c4`)

| Kiểm | Kết quả |
|---|---|
| `uv lock --check`, `uv sync --locked` | exit 0 |
| ruff check / format | `All checks passed!` · `142 files already formatted` |
| mypy --strict (Linux, `--platform win32`, `--platform darwin`, `tools/release tools/ci`) | `Success: no issues found in 84 source files` ×3 · `in 5 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api, coverage | exit 0 cả năm |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `732 passed, 1 skipped, 429 deselected` (skip trong danh sách) · `skips on linux: all in the published list` |
| pytest lưới `slow` của dev (`tests/test_doctor.py -m slow`) | `421 passed` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 504.35s` · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 147.05s` |
| e2e trên bản cài (§3.5) | `3 passed in 148.57s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng). Các test của dev xanh nhưng không bắt được
QD-28 – QD-31: giả lập của dev chỉ làm hỏng byte checksum (không bao giờ byte id), cắt gói không có ở mọi câu trả lời,
và cơ chế "late" của dev không đo tốc độ khi bộ chuyển chậm hơn thời gian chờ.

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-27

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
| QD-16 | Đóng | Không có giá trị Python trong 922 stdout; `ms_per_read` rỗng là `no read succeeded` |
| QD-17 | Đóng | Dry run: `OK: no uv PATH warning`; dòng PATH song ngữ |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ) |
| QD-20 | Đóng | §1: sdist 283 mục, trùng byte với CI |
| QD-21 | Đóng | §3.6.1 |
| QD-22 | Đóng | §3.6.1 |
| QD-23 | Đóng | §3.6.1 |
| QD-24 | Đóng | Dòng quét = tập dòng servo ở 922 / 922 báo cáo; checksum là `corrupted answers (checksum)` |
| QD-25 | **Đóng** | §3.6.2: 0 giá trị sai ở 922 lượt, kể cả câu trả lời trễ ở mọi khối, bộ chuyển chậm tới 300 ms |
| QD-26 | **Đóng** | §3.6.3: 0 "does not match" khi tệp khớp; "could not read … (a bus problem, not the calibration)" |
| QD-27 | **Đóng** | §3.6.4 (ở tình huống đã báo; QD-29 là tình huống khác, nguyên nhân khác) |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-28 · Low · F-63 (AT-77, FL-11; tính hợp lý của điều người dùng thấy) · Một gói hỏng có byte id bị đổi làm servo
mất điện thành "answers only with corrupted packets"; "do not answer (power? cable?)" biến mất.**
Bước: servo 6 không có điện / rút cáp; bus làm hỏng một byte trong **một** câu trả lời của servo khác sao cho byte id
thành 6 (một bit: 2 → 6 hoặc 4 → 6); `hibiscus-station doctor --no-cameras` (QC: bản cài, giả lập, servo 6 chết, đúng
một câu trả lời 17 byte của servo 2 có byte id = 6; 3 / 3 lượt; cũng gặp ngẫu nhiên ở lật bit 20 % hạt giống 2).
Kỳ vọng: gói sai checksum không chứng minh được nó đến từ servo nào (byte id cũng có thể hỏng); servo không gửi một gói
hợp lệ nào trong ~30 lệnh hỏi nó vẫn là `do not answer (power? cable?)` (kèm `unreliable bus` nếu có lỗi khác).
Thực tế: `! desk follower: unreliable bus: 20 of 20 reads failed (20 got no answer), motor id(s) 6 answer only with
corrupted packets (checksum); check the 3-pin cables …` và `! desk follower: could not read register(s) Homing_Offset,
Min_Position_Limit, Max_Position_Limit of gripper (a bus problem, not the calibration) …`; dòng quét `1-5 (model 777);
6 (model ?); 6 answer only with corrupted packets`; dòng `id 6: answers only with corrupted packets (checksum)` trong
khi dump thô cùng báo cáo `id 6: [0-4] no answer  [13-15] no answer  [56-70] no answer` và `bus errors: … ping [6] x3,
read 0-16 [6] x3, …` (mọi lệnh hỏi servo 6 đều không có gì). Không còn dòng nào nói servo 6 im.
Nguyên nhân QC thấy: `Probe._note()` / `_take()` (`hibiscus_station/hw/probe.py`) ghi `evidence[frame.id].corrupt`
theo byte id của gói **đã sai checksum**, và `_conclude()` (`doctor.py`) coi `ev.heard` là servo có trả lời.

**QD-29 · Low · F-63 (AT-77; tính hợp lý, báo cáo không tự mâu thuẫn) · Khi mọi câu trả lời bị cụt, servo 2, 4, 6 bị
kết luận "do not answer (power? cable?)" dù chính báo cáo ghi chúng gửi gói cụt.**
Bước: cả 6 servo có điện; mọi câu trả lời mất 2 byte cuối (ví dụ bộ chuyển bán song công đổi chiều quá sớm);
`hibiscus-station doctor --no-cameras` (QC: gói cụt 100 %, follower hoặc leader, mọi hạt giống: 5 / 5 lượt giống nhau).
Kỳ vọng: servo gửi byte về cho mọi lệnh không phải "do not answer"; cả 6 cùng một trạng thái (gói hỏng / cụt), LIKELY
PROBLEMS nêu bus.
Thực tế: `! desk follower: motor id(s) 2, 4, 6 do not answer (power? cable?)` cạnh `motor id(s) 1, 3, 5 answer only
with corrupted packets (checksum)`; dòng `id 2: no answer` nhưng dump thô cùng báo cáo `id 2: [0-4] malformed answer
(cut short or the wrong length)  [13-15] malformed answer …  [56-70] malformed answer …`; `teleop estimate: not measured
(motor id(s) 2, 4, 6 do not answer)`; `calibration file vs motors: … shoulder_lift: motor did not answer`.
`report.json`: servo 2 `evidence {"corrupt": 0, "garbled": 0, …}`, `state "silent"`.
Nguyên nhân QC thấy: gói cụt còn dở ở hạn chờ được ghi `GARBLED` cho lần hỏi nhưng không vào `Evidence.garbled`;
`_drain()` bỏ phần dở đó; trong sync read gói cụt của servo lẻ nuốt đầu gói servo chẵn nên servo lẻ thành "corrupt",
servo chẵn không còn dấu vết.

**QD-30 · Low · F-63 (AT-77, FL-11; tính hợp lý) · Câu trả lời đến trễ bị tính cho servo: servo trả lời mọi lệnh bị
gọi "answer only now and then" và LIKELY PROBLEMS chỉ vào servo đó.**
Bước: bus sạch, một lần khựng USB 300 ms đúng lúc lệnh quét (Windows / hub có thể khựng như vậy); hoặc bộ chuyển chậm
200 – 300 ms; `hibiscus-station doctor --no-cameras` (QC: 2 / 2 lượt khựng 300 ms lúc quét; bộ chuyển chặn 200 ms 2 / 2).
Kỳ vọng: câu trả lời trễ cho ping là câu trả lời (servo có điện, nối đúng); servo đã trả lời 20 / 20 sync read và mọi
thanh ghi không bị gọi chập chờn; lỗi nêu ở mức bus (khựng / chậm), không chỉ vào một servo.
Thực tế (khựng 300 ms): `! desk follower: unreliable bus: motor id(s) 1 answer only now and then (no valid answer to 3
pings), 10 answers came too late and were discarded; check the 3-pin cables …`; dòng servo 1 `answers only now and
then: no valid answer to 3 pings, but answered 20 of 20 sync reads, 4 late answers`; `sync read: 0/20 failed, 0.64 ms
each`, `~250 Hz`. Bộ chuyển 200 ms: `motor id(s) 2 answer only now and then … but answered 18 of 20 sync reads, 20 late
answers`. Bộ chuyển đường ống 60 ms + servo 6 chết: `unreliable bus: 5 answers came too late and were discarded; check
the 3-pin cables …`, không có dòng "slow bus" (bộ chuyển chậm bị gọi là cáp lỏng).
Nguyên nhân QC thấy: `ping()` chỉ nhận câu trả lời trong cửa sổ của lần thử; câu trả lời trễ chỉ thành `ev.late` và
servo không có ping hợp lệ thành `flaky` (`_conclude()`), dù `late` / sync read cho thấy nó trả lời mọi lần.

**QD-31 · Low · F-63 (AT-77, D-21; tính hợp lý của số liệu) · Tốc độ bus đo sai khi bộ chuyển chậm bằng hoặc hơn thời
gian chờ: câu trả lời trễ của lần sync read trước được tính giờ như câu trả lời của lần này.**
Bước: bus sạch, bộ chuyển trả lời đều 50 ms (đúng ngưỡng CHANGELOG hứa "50 ms or more per answer is measured and
reported as a slow bus") hoặc 260 ms; `hibiscus-station doctor --no-cameras` (QC: 2 / 2 lượt mỗi mức).
Kỳ vọng: `slow bus (≈50 ms per read)` (không nhanh hơn bộ chuyển), không nêu "unreliable bus … check the 3-pin cables"
khi mọi servo trả lời đều; ở 260 ms ước lượng ≈ 2 – 3 Hz hoặc "not measured".
Thực tế: 50 ms: `sync read: 2/20 failed (2 got no answer), 18 worked, 44.66 ms each` (lượt 2: `44.62`), `! desk
follower: unreliable bus: 2 of 20 reads failed (2 got no answer) although every motor answers a ping, 13 answers came
too late and were discarded; check the 3-pin cables between the servos, the power supply …` cạnh `slow bus (44.66 ms per
read)`; 49 ms và 52 ms thì đúng (`49.19`, `52.44 ms each`, chỉ "slow bus"). 260 ms: `13/20 failed, 7 worked, 31.06 ms
each`, `teleop estimate: ~24 Hz, leader -> follower latency ~63.0 ms` (sự thật ≈ 2 Hz), kèm "motor id(s) 1, 3, 4, 5, 6
answer only now and then". Đường ống 300 ms: `76.8 ms each`.
Nguyên nhân QC thấy: `Probe.exchange()` nhận câu trả lời trùng lệnh (mọi sync read giống hệt nhau) dù nó trả lời lệnh
trước, và đo `ms` từ lúc gửi lệnh này; `_slower()` chỉ tăng thời gian chờ sau khi đã có câu trả lời trễ. Ghi chú hiện
thực: bộ chuyển ≥ 50 ms mỗi câu trả lời hiếm gặp; lỗi là số liệu sai và lời khuyên sai ở đúng ngưỡng sản phẩm tự công
bố.

### 5.3 Ghi nhận (không phải lỗi)

* Chương trình giữ cổng có dòng lệnh chứa ký tự xuống dòng (chương trình QC tự dựng `python3 -c "\nimport …"`) làm mục
  "busy, held by pid …" trong LIKELY PROBLEMS xuống dòng giữa chừng. Có từ lần 8; chương trình thật (LeLab, lerobot-*,
  Feetech FD) không có dòng lệnh như vậy.
* Dòng giải mã dump thô dùng `-` cho giá trị không đọc được, dòng `id N` dùng `?`: không sai, chỉ khác ký hiệu.

## 6. Người dùng cần kiểm giúp (NOT VERIFIED)

Như lần 8: VM Windows 11 sạch với lệnh `irm … | iex` từ bản nháp GitHub; VID:PID và lời khuyên WCH với bộ chuyển CH340
/ CH343 thật; `doctor --verbose` trên tay thật của khách (REG-13); hiển thị UTF-8 trên console Windows. Chỉ giao UAT-0
khi F-63 PASS.
