# QC M0 lần 5: báo cáo kiểm soát chất lượng · Hibiscus Station · 2026-11-17

**Kết luận: M0 = FAIL.** QD-20 của [lần 4](QC-M0-r4.md) đã sửa đúng: lượt CI của đúng commit ứng viên **xanh 12 / 12**,
sdist mà QC build **sau `pnpm install`** (như `release.yml`, có `web/node_modules`: 608 gói trong `.pnpm`, 538 tệp `README.md`) chỉ còn 282 mục của
gói và **trùng byte** với sdist của CI; `verify_assets.py` từ chối sdist có tệp lạ. QD-1 – QD-19 vẫn đóng. Mọi bước
AT-77 [Vendor] đạt trên bản cài, **0 lệnh ghi động cơ** qua 15 lượt `doctor` có đếm lệnh. Nhưng QC tìm thêm **1 lỗi
mới mức Low** ở `doctor` (QD-21): khi động cơ **không trả lời** (tay chưa cấp điện, hoặc chỉ một servo lỏng cáp), báo
cáo còn kết luận **"slow bus (51 ms per read)"** và khuyên bỏ hub USB / chỉnh latency timer FTDI, kèm ước lượng teleop
`~14 Hz, latency ~104 ms`, trong khi 51 ms đó chỉ là thời gian chờ hết hạn của các lần đọc thất bại. Theo quy tắc không
lỗi (zero-defect): **F-1 / P-1 phần M0 đạt**, **phần M0 của F-17 (D-1) đạt**, **AT-2 đạt**; **F-63 chưa đạt** (QD-21).
Bản này **chưa** được giao cho khách làm UAT-0.

QC độc lập: QC không nhận kết luận của nhóm dev, chỉ dùng tài liệu đã duyệt (FEATURES-APPROVED, ACCEPTANCE,
REGRESSION, quy chuẩn chất lượng trong quy trình), bản cài mà người dùng sẽ cài và kết quả CI của đúng commit.

## 1. Bản được kiểm

| Mục | Giá trị |
|---|---|
| Nhánh / commit | `release/v1` @ `f34094d64c43b2c10c9372398f9c219d71d3bef6` (HEAD trên origin lúc QC bắt đầu và lúc kết thúc) |
| Lượt CI | https://github.com/Bigkatoan/hibiscus-station/actions/runs/44076695003 (push `release/v1`, `head_sha` = `f34094d6…`, lần chạy 1) → **success, 12 / 12 job xanh** (QC chờ tới khi lượt chạy xong, 19:00, rồi mới kết luận) |
| Wheel QC tự build | `hibiscus_station-1.0.0a1-py3-none-any.whl` sha256 `69ad5acfc06766b36dda9671fdde209e8eef232b529c279aa9cd857146f1164e`, **trùng byte** với wheel trong artifact `release-assets` của lượt CI trên (và với wheel của lần 4: commit mới không đổi mã của gói) |
| sdist QC tự build (có `web/node_modules`) | `hibiscus_station-1.0.0a1.tar.gz` sha256 `a76d5c39e51eb329887e8570b92895dec4619bf6079e43f23b817db9dafacdcd`, 282 mục, 1 506 013 byte: **trùng byte** với sdist của CI (lần 4: 1276 mục, khác CI). Build lại wheel từ chính sdist này (`uv build --wheel <sdist>`) ra đúng `69ad5acf…` |
| Tệp trùng byte khác | `install.ps1` (`b6653d2e…`), `constraints.txt` (`deb1eb14…`), `hibiscus-0.1.1-py3-none-any.whl` (`17abbb70…`) |
| Tệp không trùng byte | `lerobot-0.7.1-py3-none-any.whl` (build lại từ git: 709 / 709 mục cùng nội dung, chỉ khác giờ / quyền trong zip, như lần 3, 4), kéo theo dòng hash trong `overrides.txt` và `SHA256SUMS` |
| Cách build + cài | `git clone` sạch `release/v1` (có `.git`, như `actions/checkout`) → `tools/release/dry_run.sh --keep --port 18650 --out <scratch>/assets`: `pnpm install --frozen-lockfile` + `pnpm build` (nên `web/node_modules` có mặt lúc build sdist, đúng điều kiện của `release.yml`), `build_release.py`, `verify_assets.py`, rồi chạy **`install.ps1` thật** trong container PowerShell 7 (`mcr.microsoft.com/powershell:7.4-ubuntu-22.04`, **không có git**, HOME trống) |
| Môi trường QC | Linux x86_64 (Ubuntu 22.04 host, múi giờ máy `Asia/Ho_Chi_Minh`, +07), Python 3.12.16 do uv cài, Playwright (Chromium, Firefox của uv.lock), giả lập `tests/sts_emulator.py` (2 chuỗi STS3215 trên pty) |

Kết quả dry run (trích):

```
== 1b. verify the assets (checksums; resolved set == uv.lock on Windows x64, Linux x86_64, macOS arm64)
x86_64-pc-windows-msvc: 91 packages, identical to uv.lock
x86_64-unknown-linux-gnu: 114 packages, identical to uv.lock
aarch64-apple-darwin: 90 packages, identical to uv.lock
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
| **AT-77** (F-63) `doctor`, phần [Vendor] | **PASS** từng bước · F-63 **FAIL** (QD-21) | Mọi bước AT-77 đạt trên bản cài (§3); lỗi mới QD-21 ở trường hợp động cơ không trả lời (§3.6, §5.2) |
| AT-77 bước 1 (`doctor --verbose`, Station tắt, hai tay cắm) | PASS | §3.2: đủ phiên bản, hồ sơ, tệp hiệu chỉnh (giờ máy + múi giờ), log; từng servo có `current raw 12 = 0.078 A`, `load raw 0 = 0.0 %`, dump thô thanh ghi 0–4, 13–15, 56–70; không có dòng `DEBUG` khi bus không lỗi |
| AT-77 bước 2 (zip không có token, `hbp_`) + không có lệnh ghi | PASS | §3.3: token cục bộ, PAT đủ, phần bí mật của PAT, mã 8 ký tự, `hf_…`, `ghp_…`: **0** trong zip lẫn stdout; chỉ còn dạng che `hbp_QcR5…`; `server.json` không vào zip. Giả lập: **0 lệnh ghi** (`write` / `sync_write`) trong cả 15 lượt doctor có đếm lệnh |
| AT-77 bước 3 (hồ sơ demo hoạt động) | PASS | `! MOCK PROFILE ACTIVE: 'demo_so101' drives SIMULATED arms, the real arm will not move`; `demo_so101 (active): cameras front, wrist` |
| AT-77 bước 4 (`--no-ping --no-cameras`) | PASS | `strace -f -e trace=openat`: thiết bị duy nhất được mở là `/dev/null` (không `/dev/pts/*`, `/dev/video*`); số lệnh giả lập nhận không đổi; `skipped (--no-ping): the serial ports were not opened` |
| AT-77 bước 5 (`kill -9`, còn `station.pid`) | PASS | `Station is not running (station.pid of pid 2505801 left behind, nothing answers)`; 0 dòng `ConnectError` / `Traceback` trong stdout và `report.txt` |
| AT-77 bước 6 (chương trình khác giữ cổng) | PASS | `! desk follower on /dev/pts/8 is busy, held by pid 2509124: …/hibiscus-station/bin: close that program (LeLab, a lerobot-* command, Feetech FD) and run the doctor again`; khi Station giữ: `held by Station pid 2505801, motors not checked: stop Station and run \`hibiscus-station doctor --verbose\` again` |
| AT-77: VID:PID, lời khuyên WCH (D-21) khi chạy thật | NOT VERIFIED | Máy QC không có bộ chuyển USB-serial; pty không có VID:PID. UAT-0 trên PC của khách (CH340 / CH343) |
| FL-11 (LIKELY PROBLEMS đúng) | PASS | Tệp đúng chỗ, khớp động cơ: `No likely problems found`, `calibration file vs motors: all 6 match` (2 tay); tệp leader lệch 1 động cơ: `! desk leader: calibration file 'desk_leader' does not match the motors (1 of 6 motors: elbow_flex homing_offset: file 300 motor 0) …` |
| Động cơ không trả lời (tay chưa cấp điện / một servo lỏng cáp) | **FAIL** (QD-21) | §3.6 |
| **AT-2** CI Linux / Windows / macOS xanh, e2e xanh, 0 skip ngoài danh sách | **PASS** | Lượt 44076695003: pytest linux `619 passed, 1 skipped`, windows `589 passed, 6 skipped`, macos `589 passed, 6 skipped` (thêm test QD-20, chạy và xanh trên cả 3 nền tảng), mỗi job `skips on <os>: all in the published list`; e2e linux Chromium `7 passed`, linux Firefox `3 passed`, windows Edge `2 passed, 1 skipped` (STS cần pty, có trong danh sách); cài Windows + `--mock` smoke; macOS cài smoke; image; web; deploy; release assets |
| **AT-1** phần [Vendor] (Windows sạch, không git, bộ thư viện trùng 100 %) | PASS phần CI · VM Windows 11 sạch NOT VERIFIED | Job `windows (install.ps1 without git …)`: dòng `The command folder C:\Users\runneradmin\.local\bin is now on your PATH …`, không có cảnh báo PATH của uv; `installed: 92 packages; tested set: 91` / `OK: 100 % identical`; `hibiscus-station 1.0.0a1`; `healthy: hibiscus-station 1.0.0a1 state=disconnected`. Lệnh `irm …/v1.0.0a1/install.ps1 \| iex` từ GitHub chưa thử được: chưa có bản nháp |
| D-1 (e2e Playwright của repo xanh) | PASS | CI 3 trình duyệt xanh (AT-2). QC chạy lại trên đúng commit: Chromium `tests/e2e` `7 passed`, Firefox `3 passed` (§4). Luồng chính bằng chuột trên **bản cài** (§3.5): `3 passed` |
| D-15 (`ConnectError`, cổng bị giữ) | PASS | Bước 5, 6 trên bản cài |
| D-21 (latency timer chỉ cho FTDI) | PASS (test) · chạy thật NOT VERIFIED | Test xanh trong bộ test đầy đủ; không có bộ chuyển WCH. Lời khuyên "slow bus" bị dùng sai chỗ khi động cơ không trả lời: QD-21 |
| K-11 (`Present_Current`, `Present_Load`, dump thô) | PASS | §3.2 |
| Nền kiểm: e2e tiếng Việt luồng người mới (`mock-vi`, `sts-vi`) | PASS | Bản cài (§3.5) + CI linux; Windows Edge `mock-vi` xanh |
| Nền kiểm: ma trận ảnh + axe (FL-7) | PASS (Linux Chromium) | `tests/e2e/test_screen_matrix.py` trong `tests/e2e` (local + CI) |
| Nền kiểm: danh sách skip theo nền tảng (NFR-18) | PASS | 3 nền tảng + local: `all in the published list` |
| FL-12 dry run phát hành | **PASS** | §1: wheel, sdist (trong điều kiện của `release.yml`), trình cài, thư viện 100 % |
| Bộ test tự động QC tự chạy (Linux, đúng commit) | PASS | §4 |
| Lối đi người dùng bằng chuột (bản cài, `--mock` và giả lập STS) | PASS cho phần M0 | §3.5. Điểm thấy được vẫn là D-5 (M1), không ghi lại |
| REG-1 (`fcntl` trên Windows, cài + `--mock`) | PASS (CI) | Job cài Windows: `healthy` sau `--mock` |
| REG-2 (hồ sơ demo thay tay thật) | PASS | Bước 3 |
| REG-13 (0 °C, dòng ~1000) | NOT VERIFIED | Cần `doctor --verbose` từ tay của khách (UAT-0) |
| REG-17 (MIME `.js`) | PASS | `text/javascript; charset=utf-8` trên Linux (QC), Windows và macOS (CI) |
| REG-18 (UTF-8 trên Windows) | PASS (byte UTF-8 đúng) · hiển thị trên console NOT VERIFIED | Log CI vẫn đọc tệp bằng cp1252 (`Má»Ÿ cá»­a sá»• …`), như lần 3, 4 (ghi chú §6) |
| Chữ của `doctor` (vi / en) | PASS (trừ QD-21) | Không có dict / list / `None` / `True` / `False` trong 35 báo cáo (17 stdout QC lưu lại + 18 `report.txt` trong zip), trừ thông điệp lỗi gốc của lerobot được trích sau `last error:` (`… from motor IDs [1, 2, 3, 4, 5, 6] after 1 tries`), là trích dẫn lỗi có chủ đích; giờ tệp hiệu chỉnh đúng giờ máy kèm múi giờ ở 5 múi giờ (§3.4) |
| Vệ sinh phát hành: bí mật / dữ liệu cá nhân | PASS | `gitleaks dir` trên cây của commit: `no leaks found`; 2 commit mới `cca2a2b..f34094d` đều tác giả / người commit `…@users.noreply.github.com`; diff mới không có đường dẫn home thật; wheel và sdist không chứa `/home/…`, email hay PAT |
| Vệ sinh phát hành: phiên bản, changelog | PASS | `check_versions.py`: `version 1.0.0a1: consistent`; `--version`, health, doctor cùng `1.0.0a1`. QD-20 không đổi gì người dùng thấy nên không cần mục CHANGELOG (ghi chú §6) |
| Vệ sinh phát hành: nội dung tài sản phát hành | **PASS** (QD-20 đóng) | §1, §4.1 |

## 3. Chi tiết trên bản cài

### 3.1 Dựng tình huống

Người dùng giả: `HOME=<scratch>/r5/user` trống, chạy bản cài bằng `env -i HOME=… PATH=/usr/bin:/bin` (không đặt `TZ`,
nên dùng múi giờ của máy). Hai chuỗi STS3215 giả lập (follower có EEPROM của một lần hiệu chỉnh LeLab, leader nhà máy)
do một tiến trình riêng của QC phục vụ; tiến trình này đóng phía slave của pty (như bộ chuyển USB thật, không ai giữ)
và đếm **mọi** lệnh nhận được (`ping`, `read`, `write`, `sync_read`, `sync_write`). Hồ sơ `desk` (`so101_follower` /
`so101_leader` trên hai pty) được tạo bằng chính Python của bản cài. Tệp hiệu chỉnh LeLab ở
`…/calibration/robots/so101_follower/desk_follower.json`. Station (bản cài) chạy một lần ở `127.0.0.1:18651` để tạo
token rồi tắt bằng Ctrl+C. Như các lần trước: sau `kill -9` pty còn cờ TIOCEXCL nên mở lại báo `EBUSY` (cổng USB thật
xoá cờ khi đóng lần cuối); QC dựng lại cặp pty mới cho bước 6 và cho §3.6.

### 3.2 `hibiscus-station doctor --verbose --no-cameras` (Station tắt)

```
$ date '+%F %T %z'                      -> 2026-11-17 18:47:53 +0700
$ ls -l desk_follower.json              -> 2026-11-17 18:46:31 +0700
LIKELY PROBLEMS:
  ! desk follower: calibration 'desk_follower' is in LeLab's folder (so101_follower), Station does not use it yet: Calibrate > Use this file
  ! desk leader: no calibration 'desk_leader'
…
Calibration files:
  follower desk_follower            so101_follower  2026-11-17 18:46:31 UTC+07:00  …/robots/so101_follower/desk_follower.json
…
Motor check (read only):
  desk follower on /dev/pts/10: ids answering at 1 Mbps: 1-6 (model 777)
    id 1: model 777 fw 3.10 pos 2048 50x0.1V (min 40 max 80) 30C (max 70) status 0 torque 0 lock 1 offset 44 limits 684-3413
           current raw 12 = 0.078 A load raw 0 = 0.0 % temperature 30.0 C voltage 5.0 V status ok protection current raw 500
    raw register dump (READ per block, 1000000 baud, hex bytes):
      id 1: [0-4] 03 0a 00 09 03  [13-15] 46 50 28  [56-70] 00 08 00 00 00 00 32 1e 00 00 00 00 00 0c 00
    sync read: 0/20 failed, 0.56 ms each
    teleop estimate: ~250 Hz, leader -> follower latency ~2.8 ms
    motors carry the calibration of: …/robots/so101_follower/desk_follower.json
```

Lệnh giả lập nhận trong lượt này: follower `ping 1, read 144, sync_read 20`, leader như vậy, **write 0, sync_write 0**.

Khi Station đang chạy và đã kết nối (`POST /api/v1/robots/desk/connect` với `X-Station: 1` như giao diện):
`pid 2505801: mode real, state idle`, `connected profile desk (real arms)`, `follower: calibrated, bus errors 0`; hai
cổng `skipped, in use by Station (pid 2505801); stop it to ping the motors`; mục **WHAT TO SEND / CẦN GỬI GÌ** có câu
"The motor check is incomplete … / Phần kiểm tra động cơ chưa đủ …". Lệnh ghi của giả lập chỉ tăng lúc Station kết
nối (69 / 102), không tăng trong lượt doctor (trước 69 / 102, sau 69 / 102).

### 3.3 Cài bí mật rồi tìm trong zip

Đã cài: token cục bộ (43 ký tự) ở dạng thô và sau `auth?t=` trong `logs/station.log`; một PAT đúng định dạng
`hbp_<8>_<43>` (mới sinh cho lần này) trong `station.log`, `server.json`, `sessions/s-qc/session.json`; biến môi
trường `HF_TOKEN=hf_QCr5…`, `GITHUB_TOKEN=ghp_QCr5…`. Zip chứa `report.txt, report.json, station.log.tail,
robots.yaml, calibration/follower/so101_follower/desk_follower.json, sessions/s-qc.json`. Kết quả (zip / stdout):

```
local token    files=0 stdout=0
PAT secret     files=0 stdout=0
full PAT       files=0 stdout=0
PAT 8-char id  files=0 stdout=0
HF token       files=0 stdout=0
GitHub token   files=0 stdout=0
hbp_ còn lại: 'hbp_QcR5…' (station.log.tail, report.json, sessions/s-qc.json)
station.log.tail: "token in log [local token removed]", "GET /auth?t=… HTTP/1.1", "cloud PAT hbp_QcR5… used"
```

### 3.4 Giờ của tệp hiệu chỉnh ở nhiều múi giờ (QD-19)

Cùng tệp (`ls -l`: `2026-11-17 18:46:31 +0700`), `doctor --no-ping --no-cameras`, so với tên zip của chính lượt đó:

| `TZ` | Giờ tệp trong báo cáo | Tên zip |
|---|---|---|
| (máy, +07) | `2026-11-17 18:46:31 UTC+07:00` | `…-20261117-185008.zip` |
| `UTC` | `2026-11-17 11:46:31 UTC+00:00` | `…-20261117-115010.zip` |
| `Asia/Kolkata` | `2026-11-17 17:16:31 UTC+05:30` | `…-20261117-172012.zip` |
| `America/St_Johns` | `2026-11-17 08:16:31 UTC-03:30` | `…-20261117-082014.zip` |
| `Pacific/Chatham` | `2026-11-18 01:31:31 UTC+13:45` | `…-20261118-013516.zip` (qua ngày) |

### 3.5 Lối đi người dùng bằng chuột trên bản cài

QC chạy `tests/e2e/test_station_ui.py` của commit ứng viên (Playwright Chromium, chỉ bấm chuột / phím như người
dùng) với **tệp chạy `hibiscus-station` của bản cài** (môi trường Python ảo của test chỉ trỏ lệnh `hibiscus-station` về
`<dry-run>/home/.local/bin/hibiscus-station`; QC thấy tiến trình Station của e2e chạy bằng
`<dry-run>/home/.local/share/uv/tools/hibiscus-station/bin/python`) và giao diện tĩnh lấy từ **wheel đã cài**
(`site-packages/hibiscus_station/static`): `3 passed in 155.60s` (`mock-en`, `mock-vi`, `sts-vi`). Luồng: kết nối →
hiệu chỉnh follower → leader → Kiểm tra → camera → teleop → dừng an toàn (nhiệt / Space e-stop) → ghi tập → bộ dữ liệu
→ nạp model ACT → chạy model → e-stop → Chương trình. QC đã xem ảnh chụp (48 ảnh, sáng / tối, vi / en): số đo hợp lý
với giả lập (30 °C, 5.0 V, 0.08 A, 0 %; teleop 239.2 / 250 FPS, vòng lặp p95 2.8 ms, độ trễ ~3 ms; mock: dừng vì
`elbow_flex 67 °C`, "I'm clear, reset"), nhãn đúng ngôn ngữ, e-stop khoá các bước.

### 3.6 Động cơ không trả lời (QD-21)

Cùng bản cài, giả lập cho servo "chết" (không trả lời gói nào, như tay chưa cắm nguồn 5 / 12 V hoặc servo lỏng cáp):

| Tình huống | LIKELY PROBLEMS (trích) | Motor check (trích) |
|---|---|---|
| Follower chưa cấp điện (6 servo im) | `! desk follower: motor id(s) 1, 2, 3, 4, 5, 6 do not answer (power? cable?)` **và** `! desk follower on /dev/pts/8: slow bus (50.39 ms per read): slow USB adapter / hub: plug the arm straight into the PC, without a hub; only if the adapter is an FTDI chip (USB VID 0403): set the FTDI adapter's latency timer to 1 ms …` | `sync read: 20/20 failed, 50.39 ms each` · `teleop estimate: ~15 Hz, leader -> follower latency ~102.2 ms  ! slow bus …` |
| Chỉ servo 6 (gripper) im | `! desk follower: motor id(s) 6 do not answer (power? cable?)` **và** `! desk follower on /dev/pts/8: slow bus (51.44 ms per read): …` | `ids answering at 1 Mbps: 1-5` · `sync read: 20/20 failed, 51.44 ms each` · `teleop estimate: ~14 Hz, leader -> follower latency ~104.3 ms` |

Leader (servo trả lời) trong cùng lượt: `sync read: 0/20 failed, 0.58 ms each`, `~250 Hz`. Cùng một bus, cùng bộ
chuyển: bus không chậm, chỉ là 20 lần `sync_read` đều thất bại và mỗi lần chờ hết hạn ~50 ms. `report.json`:
`{'reads': 20, 'failed': 20, 'ms_per_read': 51.44}`, `teleop_estimate.warning = "slow bus (51.44 ms per read) …"`.
0 lệnh ghi trong cả hai lượt.

## 4. Bộ test tự động (QC tự chạy, Linux, bản `git clone` sạch ở `f34094d`)

| Kiểm | Kết quả |
|---|---|
| ruff check / format | `All checks passed!` · `141 files already formatted` |
| mypy --strict | `Success: no issues found in 83 source files` |
| một phiên bản | `version 1.0.0a1: consistent` |
| openapi.json | trùng với bản sinh lại |
| web: eslint, prettier, tsc, check:api | exit 0 cả bốn |
| vitest | `13 passed (13)` tệp, `173 passed (173)` test |
| build UI + CSP | `CSP check: no eval / new Function in dist/assets` |
| pytest | `619 passed, 1 skipped, 8 deselected` (skip `test_windows_lock_is_a_byte_past_the_header`, có trong danh sách) · `skips on linux: all in the published list` |
| e2e Chromium (`tests/e2e -m e2e`) | `7 passed in 506.00s` (gồm ma trận ảnh + axe) · `skips on linux: all in the published list` |
| e2e Firefox (`test_station_ui.py`) | `3 passed in 145.88s` |
| e2e trên bản cài (§3.5) | `3 passed in 155.60s` |

Bản clone vẫn sạch sau khi chạy (`git status --porcelain`: 0 dòng).

### 4.1 Kiểm fail-trước-pass-sau (QD-20)

| Kiểm | Trước sửa | Sau sửa |
|---|---|---|
| Test mới `test_sdist_holds_only_the_package_even_with_web_node_modules` | Cây `f34094d` với `pyproject.toml` của `cca2a2b`: `1 failed` (`assert not ['hibiscus_station-1.0.0a1/we…` = tệp `web/node_modules` cài vào nằm trong sdist) | Cây `f34094d`: `1 passed` |
| `verify_assets.py` với sdist kiểu cũ (build từ `pyproject.toml` của `cca2a2b` + `web/node_modules/.pnpm/foo@1.0.0/…`, `SHA256SUMS` tính lại) | — | Báo lỗi: `hibiscus_station-1.0.0a1.tar.gz: 5 files outside the package, e.g. ['tests/contract/README.md', 'tests/hil/README.md', 'web/node_modules/.pnpm/foo@1.0.0/node_modules/foo/LICENSE']` |
| sdist thật của dry run (`web/node_modules` có 608 gói) | lần 4: 1276 mục, 991 mục `web/node_modules` | 282 mục, 0 `node_modules`, 0 `tests/`, trùng byte với CI |

## 5. Trạng thái lỗi

### 5.1 QD-1 – QD-20

| QD | Trạng thái | Kiểm lại lần này |
|---|---|---|
| QD-1 | Đóng | `1.0.0a1` ở mọi chỗ (`check_versions.py`, `--version`, health, doctor) |
| QD-2 | Đóng | CI Windows PowerShell 5.1 không git: cài xong, thư viện 100 %, smoke `--mock`; dry run PowerShell 7 không git |
| QD-3 | Đóng | CI e2e Windows Edge `2 passed, 1 skipped` |
| QD-4 | Đóng | pytest windows `589 passed`, không skip module `test_doctor` |
| QD-5 | Đóng | Test nhịp đọc bus xanh trên Windows |
| QD-6 | Đóng | pytest linux CI + QC local xanh |
| QD-7 | Đóng | pytest macos `589 passed, 6 skipped`, skip có trong danh sách |
| QD-8 | Đóng | CI `image (cpu …, smoke test)` xanh |
| QD-9 | Đóng | e2e Linux Chromium + Firefox, Windows Edge |
| QD-10 | Đóng | §3.2 (một câu nhất quán về tệp LeLab) |
| QD-11 | Đóng | §3.2 (Station chạy + kết nối, không `None` / `False`; "The last 4 log lines are in the zip.") |
| QD-12 | Đóng | §3.2: không có dòng `DEBUG` của thư viện. Với `--verbose` và bus có lỗi, dòng `DEBUG hibiscus_station.hw.bus: bus error …` là đúng chức năng `--verbose` ("Print every bus error"), không phải QD-12 |
| QD-13 | Đóng | AT-77 bước 4 |
| QD-14 | Đóng | FL-11 |
| QD-15 | Đóng | CHANGELOG `[Unreleased]` |
| QD-16 | Đóng | Không còn giá trị Python trong 35 báo cáo; test của bản sửa xanh trên cả 3 nền tảng |
| QD-17 | Đóng | Dry run PowerShell 7 + CI Windows PowerShell 5.1: không còn cảnh báo PATH của uv; dòng PATH song ngữ đứng trước "Đang cài thư viện" |
| QD-18 | Đóng | Lượt CI của commit ứng viên xanh 12 / 12 |
| QD-19 | Đóng | §3.4 (5 múi giờ, có múi lệch 30 / 45 phút và qua ngày) |
| QD-20 | **Đóng** | §1, §4.1: sdist build sau `pnpm install` chỉ có gói, trùng byte với CI; test fail-trước-pass-sau; `verify_assets.py` chặn tệp lạ |

### 5.2 Lỗi mới

Mức độ theo quy trình: High = không làm xong được luồng chính; Medium = cần đường vòng / sai ở trường hợp biên; Low =
chữ, hiển thị, vệ sinh. Lỗi nào cũng chặn PASS.

**QD-21 · Low · F-63 (AT-77, FL-11, D-21; tính hợp lý của điều người dùng thấy) · Khi động cơ không trả lời, `doctor`
kết luận thêm "slow bus" và khuyên bỏ hub / chỉnh latency timer.**
Bước: hồ sơ có tay thật; tay follower cắm USB nhưng chưa cấp điện (hoặc chỉ một servo lỏng cáp); Station tắt;
`hibiscus-station doctor --no-cameras` (QC: bản cài, giả lập STS cho servo không trả lời, §3.6).
Kỳ vọng: LIKELY PROBLEMS chỉ nêu nguyên nhân thật (`motor id(s) … do not answer (power? cable?)`); không đưa ra
kết luận về tốc độ bus và ước lượng teleop khi các lần đọc đo được đều thất bại (hoặc ghi rõ là không đo được).
Thực tế: thêm một mục `! desk follower on /dev/pts/8: slow bus (51.44 ms per read): slow USB adapter / hub: plug the arm
straight into the PC, without a hub; only if the adapter is an FTDI chip (USB VID 0403): set the FTDI adapter's latency
timer to 1 ms …`, và dòng `teleop estimate: ~14 Hz, leader -> follower latency ~104.3 ms`, cả khi chỉ servo 6 im. Người
dùng (hoặc người hỗ trợ đọc zip) sẽ đi tìm hub USB / bộ chuyển chậm, trong khi bus cùng loại ở tay kia đo `0.58 ms`.
Đây là một tình huống ngày đầu rất hay gặp (quên cắm nguồn tay, lỏng cáp gripper).
Nguyên nhân QC thấy: `hibiscus_station/doctor.py` (khoảng dòng 407–422) đo `ms_per_read` trên cả 20 lần `sync_read`,
kể cả lần thất bại (mỗi lần chờ hết hạn ~50 ms), rồi `teleop_estimate()` / `slow_bus_advice()` dùng con số đó dù
`failed == reads`. Mã này không đổi từ lần 4; các lần trước QC chỉ chạy với servo trả lời đủ, nên không thấy (§6, rà
lỗi lọt).

## 6. Ghi chú (không phải lỗi M0)

* **Rà lỗi lọt cho QD-21**: lỗi có từ trước lần 4; danh sách kiểm của QC cho `doctor` chưa có tình huống "tay chưa cấp
  điện / servo không trả lời". Đã thêm vào cách kiểm của QC (§3.6) và đề nghị BA thêm vào danh sách hồi quy
  (REGRESSION) khi sửa.
* **Log CI của trình cài Windows vẫn hiện chữ Việt sai** (`Má»Ÿ cá»­a sá»• …`): `Get-Content` của PowerShell 5.1
  đọc tệp UTF-8 bằng cp1252 (ghi chú lần 3, 4, chưa đổi). Byte trình cài phát ra đúng. Đề nghị `Get-Content -Encoding UTF8`.
* **Test của QD-19 không phủ dòng báo cáo** (ghi chú lần 4, chưa đổi).
* **CHANGELOG không có mục cho QD-20**: thay đổi chỉ ở nội dung sdist, người dùng ứng dụng không thấy; không tính là lỗi.
* **`verify_assets.py` không kiểm sdist khi thư mục không có sdist** (vòng lặp `glob` rỗng thì bỏ qua). `build_release.py`
  luôn tạo sdist nên không ảnh hưởng bản phát hành.
* **Dòng chương trình giữ cổng cắt ở 160 ký tự** (`held by pid …: …/hibiscus-station/bin`): với đường dẫn rất dài của QC,
  tên chương trình (`python -c …`) bị cắt mất; đường dẫn thật của người dùng ngắn hơn nhiều. Như lần 3, 4: lệnh nhiều dòng
  được in nguyên.
* **`lerobot-0.7.1-py3-none-any.whl` không tái lập byte** (như lần 3, 4): nội dung giống hệt, chỉ khác giờ / quyền trong zip.
* **Cảnh báo `StarletteDeprecationWarning`** (`httpx` với `starlette.testclient`) trong pytest của cả 3 nền tảng: chỉ ở môi
  trường test, không có trong bản cài.
* **Dry run trong container in `warning: Failed to hardlink files`** của uv (bộ nhớ đệm gắn từ hệ tệp khác); không có
  trên Windows CI.
* Hồ sơ demo hiện `calibration 'demo_follower' MISSING` trong mục Robot profiles của doctor (tay giả lập không cần tệp);
  đã có dòng `MOCK PROFILE ACTIVE` ở đầu nên không gây hiểu sai.
* Các ghi chú §6 của lần 2 – 4 còn nguyên: macOS (bộ hẹn giờ của VM), chưa có bản nháp `v1.0.0a1` nên dòng `irm` trong
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
| F-63 `doctor` | **FAIL** (QD-21: kết luận "slow bus" khi động cơ không trả lời; mọi bước AT-77 [Vendor] đạt trên bản cài; VID:PID / WCH thật NOT VERIFIED, UAT-0) |
| F-1 phần M0 (P-1) | **PASS** (QD-20 đóng; AT-2 PASS; CI Windows 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED, UAT-0) |
| F-17 phần M0 (D-1) | PASS |
| P-1 (cài) | **PASS** (M0) |
| AT-2 / nền kiểm CI | PASS (12 / 12, lượt 44076695003) |

QC chạy lại cổng M0 trên commit mới khi QD-21 đã có bản sửa kèm test tự động (servo không trả lời: không có "slow bus",
không có ước lượng teleop từ lần đọc thất bại; một servo im và cả tay im), lượt CI của đúng commit đó xanh 12 / 12.

Máy chủ QC đã khởi động (`127.0.0.1:18650`, `18651`, e2e trong `18655` – `18669`) và bộ giả lập đều đã dừng.
