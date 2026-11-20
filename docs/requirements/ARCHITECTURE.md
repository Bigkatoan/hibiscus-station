# Hibiscus Station: Architecture v1.1 (2026-11-19) · trạng thái: **đã duyệt** (khách hàng duyệt ngày 2026-11-17, đường cơ sở; CR-1 duyệt ngày 2026-11-19, ADR-14)

Tài liệu kiến trúc cho **Hibiscus Station v1.0**. Người soạn: SA. Tham khảo: BA, Tech Lead. Khách hàng
duyệt phần ảnh hưởng tới chi phí / nền tảng (lựa chọn công nghệ là việc của nhà cung cấp).
Tài liệu cùng bộ: [BRD.md](BRD.md) v1.0 · [SRS.md](SRS.md) v1.0 · [FEATURES.md](FEATURES.md) v1.0 ·
[FEATURES-APPROVED.md](FEATURES-APPROVED.md) v1.0 · [ACCEPTANCE.md](ACCEPTANCE.md) v1.0 · [REGRESSION.md](REGRESSION.md) v1.0 · rà soát yêu cầu:
[REVIEW-SA.md](REVIEW-SA.md), [REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md).

> **v0.2 (BA, Reconcile vòng 1).** Nội dung kiến trúc giữ như v0.1 của SA. Các flag ở REVIEW-SA đã được BA
> đưa vào SRS v0.2 (NFR-1a – 1c, NFR-2, NFR-3a – 3c, NFR-4, NFR-9 – NFR-11, NFR-13 – NFR-18 viết lại; FR-1,
> FR-9, FR-12, FR-13, FR-20, FR-33, FR-47, FR-63, FR-69, FR-73, FR-75) và FEATURES v0.2 (đề xuất P-1 – P-8,
> lỗi D-19 – D-23). Bảng §6 còn ghi theo định nghĩa NFR v0.1; SA cập nhật §6 theo SRS v0.2 ở vòng 2. ADR-13
> chờ quyết định QĐ-3; nền tảng §3.4 theo QĐ-2; gói `hibiscus` theo QĐ-4 (BRD §9).

> **v1.0 (khách hàng duyệt 2026-11-17, QĐ-1 – QĐ-4 = A).** ADR-13 được chấp nhận (QĐ-3 = A: lệnh cài / cập nhật /
> quay lại một dòng, phụ thuộc cố định, không cần git). §3.4: Windows Must, Ubuntu Should, Docker Linux x86_64
> `-cpu` Could; Raspberry Pi 5, Jetson Orin, macOS, wheel arm64, Docker `-cuda` là **bản xem trước**, ngoài nghiệm
> thu (QĐ-2 = A, W-9). ADR-12: ghim Hibiscus CLI **v0.1.2, Apache-2.0** khi chủ sở hữu phát hành (QĐ-4 = A,
> phụ thuộc ngoài EXT-1). Việc còn mở của SA: cập nhật §6 theo SRS v1.0 và chốt tên `thermal_blind` / khoá cài
> đặt giới hạn 10 phút (QĐ-1 = A) — OI-3.

> **Cách đọc.** Đây là kiến trúc **như đã xây** của Station **0.2.8** (`main` `12f36da`), đúng với
> quyết định của khách hàng ngày 2026-11-17: v1.0 = tính năng hiện có đưa lên chuẩn chất lượng, không
> thêm tính năng. Vùng **Automation** (nhánh `feat/automation`) **không** có trong tài liệu này (Won't
> v1.0, W-1). Mỗi NFR ở §6 ghi rõ **đạt / chưa chứng minh / không đạt hôm nay**, kèm bằng chứng.
> Tài liệu kỹ thuật chi tiết cho dev vẫn là `docs/spec/station.md` và `docs/spec/station-programs.md`;
> khi hai nơi khác nhau, mã nguồn ở `12f36da` là sự thật và spec phải sửa (SRS K-7).

---

## 1. Bối cảnh (context)

```
                        ┌──────────────────────── Máy robot (Windows 10/11 · Linux · Pi 5 · Jetson) ───────────────────────┐
 Người dùng             │                                                                                                   │
 (người mới / kỹ sư) ── │ Trình duyệt (Edge/Chrome/Firefox) ──HTTP+WS 127.0.0.1:18210──► hibiscus-station (1 tiến trình Python)│
   tay cầm leader       │   giao diện React (đóng gói trong wheel)                       │  │  │                                 │
                        │                                                                │  │  └─► OpenCV / RealSense ──USB──► Camera UVC
                        │ Script / hệ thống ngoài ──REST /api/v1 (Bearer)  ─────────────►│  └────► rustypot (serialport-rs) ──USB-serial CH340/CH343──► bus Feetech
                        │ MQTT broker (tuỳ chọn) ◄──────────────────────────────────────►│                                   STS3215 ×6 follower · ×6 leader
                        │                                                                │
                        │ Ổ đĩa: ~/.hibiscus/station · thư mục hiệu chỉnh lerobot (dùng chung với LeLab / lerobot)          │
                        └──────────────────────────────────────────────────────────────────┬────────────────────────────────┘
                                                                                           │ HTTPS (chỉ khi ghép nối)
                                                                     Máy chủ Hibiscus API v0.1.1 (ngoài phạm vi v1.0)
                                                                     webhook (tuỳ chọn) · HF Hub (chỉ khi model cần tải backbone)
```

* **Một tiến trình, một máy.** Station chạy trên chính máy cắm tay robot; giao diện là trang web phục vụ
  từ `127.0.0.1`. Không có dịch vụ đám mây bắt buộc. Huấn luyện ở máy chủ Hibiscus (RULE-15).
* **Phần cứng:** SO-100 / SO-101, servo Feetech STS3215 (id 1–6, 1 Mbaud), bộ chuyển USB-serial WCH
  CH340 (`1a86:7523`, không có số serial) hoặc CH343 (`1a86:55d3`, có số serial). Follower cấp 7,4 V
  hoặc 12 V; leader thường 5 V.
* **Hệ thống liền kề:** LeLab / lerobot CLI (dùng chung tệp hiệu chỉnh, **tranh chấp cổng serial**),
  máy chủ Hibiscus (ghép nối, tải lên, kéo model), MQTT / webhook (khối chương trình, Could).

## 2. Bảng công nghệ (tech stack)

Phiên bản lấy từ `pyproject.toml`, `uv.lock` (`12f36da`) và `web/package.json`. Giấy phép đã kiểm với
metadata của gói đã cài. Station là **AGPL-3.0-or-later**; mọi giấy phép dưới đây tương thích khi phân
phối, **trừ một mục cần xử lý** (gói `hibiscus`, xem ADR-12 và flag SA-L1).

### 2.1 Máy chủ (Python)

| Lớp | Lựa chọn | Phiên bản (lock) | Vì sao | Đã loại | Giấy phép |
|---|---|---|---|---|---|
| Ngôn ngữ | CPython | 3.12 (`>=3.12,<3.13`) | lerobot 0.7.1 cần 3.12; một phiên bản cho mọi nền tảng | 3.10/3.11 (lerobot không hỗ trợ), 3.13 (torch/onnxruntime trên ARM chưa đủ) | PSF |
| Robot / dataset / policy | **lerobot** `[feetech,dataset]` git `fe1c545` | 0.7.1 | Chuẩn của khách hàng (LeLab dùng lerobot); dataset LeRobot v3, policy ACT / Diffusion / SmolVLA; tệp hiệu chỉnh dùng chung (C-2) | Tự viết driver + định dạng (mất tương thích LeLab); vá LeLab (ADR-0011 cũ: LeLab không bị sửa) | Apache-2.0 |
| Bus servo | rustypot (qua lerobot) + serialport-rs | 1.13.1 | lerobot 0.7.1 đã chuyển từ `scservo_sdk` sang rustypot; Station bọc lại (`StationMotorsBus`) để thử lại và phát hiện mất thiết bị | `scservo_sdk` / pyserial trực tiếp (lệch khỏi lerobot) | Apache-2.0 |
| Liệt kê cổng | pyserial `list_ports` | 3.5 | VID:PID, số serial, mô tả trên cả ba OS | WMI trực tiếp | BSD-3-Clause |
| Web / API | FastAPI + Starlette | 0.163.1 / 1.10.0 | REST + WebSocket cùng một tiến trình, OpenAPI sinh tự động → kiểu TypeScript (`openapi.json`) | Flask (không WS bất đồng bộ), Electron (nặng, khó cài cho người mới) | MIT / BSD-3-Clause |
| Máy chủ ASGI | uvicorn `[standard]` | 0.54.0 | Nhẹ, chạy được trên Windows | hypercorn | BSD-3-Clause |
| Mô hình dữ liệu | pydantic / pydantic-settings | 2.14.3 | Kiểm đầu vào, lỗi 422 có cấu trúc | dataclass thủ công | MIT |
| CLI | typer | 0.29.1 | `hibiscus-station`, `doctor`, `health`, `url`, `openapi` | argparse | MIT |
| Camera | opencv-python-headless (+ RealSense tuỳ chọn) | 4.13.0.92 | Qua `lerobot.cameras`, cùng hành vi LeLab | ffmpeg trực tiếp | Apache-2.0 (wheel kèm FFmpeg LGPL-2.1) |
| Mã hoá video dataset | PyAV / torchcodec (qua lerobot) | 15.1.0 / 0.17.0 | Định dạng dataset lerobot | — | BSD-3-Clause (PyAV kèm FFmpeg LGPL) |
| Suy luận policy | PyTorch / torchvision | 2.15.0 / 0.29.2 (Docker cpu: 0.29.1+cpu) | Bắt buộc bởi lerobot; CPU / CUDA / MPS | ONNX cho policy (W-8) | BSD-3-Clause |
| Nhận diện (Chương trình) | onnxruntime (CPU) | 1.31.1 | Bộ phân loại ảnh nhỏ, không cần torch | torch | MIT |
| Tín hiệu | paho-mqtt | 2.1.0 | Khối "tín hiệu" / "nhận tin" (Could) | — | EPL-2.0 OR BSD-3-Clause (chọn BSD) |
| Bí mật | keyring (Docker: tệp 0600) | 25.7.0 | Token máy chủ không nằm trong tệp thường | tệp thường | MIT |
| HTTP ra ngoài | httpx | 0.28.1 | Dùng chung với Hibiscus CLI | requests | BSD-3-Clause |
| Liên kết máy chủ | `hibiscus` (Hibiscus CLI) git `v0.1.1` → `v0.1.2` | 0.1.1 → 0.1.2 | Dùng lại Uploader / Puller / HibiscusApi, không sao chép | Viết lại | 0.1.1: **"Proprietary" trong metadata**; QĐ-4 = A: **Apache-2.0** từ v0.1.2 (EXT-1, SA-L1) |
| Dataset I/O | datasets / pyarrow / huggingface-hub / safetensors | 5.2.0 / 26.0.1 / 1.33.0 / 0.8.0 | Qua lerobot | — | Apache-2.0 |
| Cấu hình lerobot | draccus | 0.11.6 | Qua lerobot | — | MIT |

### 2.2 Giao diện (web)

| Lớp | Lựa chọn | Phiên bản | Vì sao | Giấy phép |
|---|---|---|---|---|
| Runtime build | Node + pnpm | 22.12 / 9.15.0 | Chỉ khi build; người dùng không cần Node | MIT |
| Khung | React + React DOM | 18.3.1 | Hệ sinh thái, test | MIT |
| Định tuyến / dữ liệu | react-router-dom / @tanstack/react-query | 6.30.6 / 5.107.1 | | MIT |
| Ngôn ngữ | i18next / react-i18next | 24.2.1 / 15.7.4 | `vi` mặc định, `en` | MIT |
| Thành phần | Radix UI, Tailwind CSS 3.4.17, class-variance-authority, tailwind-merge | xem `web/package.json` | Truy cập được (a11y), hệ thiết kế pixel Hibiscus | MIT |
| Đồ thị | uPlot | 1.6.32 | Biểu đồ telemetry 120 s, nhẹ | MIT |
| Robot 3D | three / urdf-loader | 0.186.1 / 0.13.1 | Mô hình SO-101 (TheRobotStudio, Apache-2.0) | MIT / Apache-2.0 |
| Trình soạn khối | Blockly | 12.5.1 | Chương trình khối | Apache-2.0 |
| Build / test | Vite 6.4.6, TypeScript 5.7.3, Vitest 3.2.7, Testing Library, MSW 2.7.0, axe-core 4.14.0, ESLint 9.18.0 + jsx-a11y | | Kiểm CSP (không `eval`) sau build | MIT / MPL-2.0 (axe-core, chỉ khi dev) |
| Font / hình | Nunito (OFL-1.1), ảnh pixel và Hibi (© Bigkatoan, ASSETS-LICENSE, không thuộc AGPL) | | Đóng gói cục bộ, không gọi CDN | OFL-1.1 / riêng |

### 2.3 Đóng gói, CI, triển khai

| Lớp | Lựa chọn | Phiên bản | Ghi chú |
|---|---|---|---|
| Quản lý gói / cài đặt | uv (`uv tool install`, `uv sync --locked`) | CI 0.13.8 | Cài Python 3.12 tự động, không cần admin trên Windows |
| Build | hatchling + `hatch_build.py` | ≥ 1.27 | Wheel `py3-none-any`, nhúng `web/dist` thành `hibiscus_station/static` |
| CI | GitHub Actions: `ci.yml` (python, web, e2e, wheel, windows, macos, deploy-lint, image), `release.yml`, `docker.yml`, `codeql.yml`, `gitleaks.yml` | | Xem §6 NFR-18 về độ phủ Windows |
| Container | Debian trixie-slim (cpu, amd64 + arm64), `nvidia/cuda:13.2.0-base-ubuntu24.04` (cuda), `nvcr.io/nvidia/pytorch:26.02-py3-igpu` (jetson) | | Không root (uid 10001), HEALTHCHECK, quét Trivy (chỉ cpu amd64) |
| Hệ thống | systemd user unit, luật udev `99-hibiscus-station.rules` | | Chỉ Linux |

## 3. Thành phần và triển khai

### 3.1 Thành phần (gói `hibiscus_station/`)

| Thành phần | Tệp | Trách nhiệm | FR |
|---|---|---|---|
| CLI | `cli.py` | Khởi động máy chủ, khoá một bản chạy, token, mở trình duyệt; `doctor`, `health`, `url`, `openapi` | FR-4, FR-63, FR-65 |
| Ứng dụng web | `app.py`, `api/routes.py`, `api/ws.py`, `api/security.py`, `programs/api_*.py` | REST `/api/v1` (86 thao tác), WS điều khiển, WS video, SPA tĩnh; kiểm Host / Origin / token / `X-Station`; lỗi RFC 9457 | FR-6, FR-73 |
| Station (facade) | `station.py`, `jobs.py` | Ghép các dịch vụ; tải lên / kéo / nạp model trong pool 2 luồng | FR-41 – FR-47 |
| **HardwareOwner** | `hw/owner.py` | **Luồng duy nhất chạm bus**; hàng đợi lệnh; máy trạng thái; vòng điều khiển; lịch telemetry; e-stop / dead-man; mất thiết bị; kết nối lại | FR-12 – FR-14, FR-24 – FR-36, FR-72, FR-74 |
| Bus | `hw/bus.py`, `hw/portloss.py`, `hw/feetech.py`, `hw/factory.py` | `StationMotorsBus` (lerobot `SerialMotorsBus` + thử lại 2 lần + đếm lỗi + `DeviceLostError`); bảng thanh ghi / đơn vị STS3215 ở **một** nơi | FR-12, FR-13, FR-31, FR-33 |
| An toàn | `hw/safety.py`, `hw/telemetry.py` | `SafetyFilter` (giới hạn bước + dải hiệu chỉnh), `EStop` (chốt, lần 2 = thả lỏng), `Watchdog` (dead-man), `TelemetryScheduler`, `ThermalGuard` (mức, trễ 3 °C, dừng an toàn) | FR-28 – FR-34 |
| Hiệu chỉnh | `hw/calibration.py` | Luồng hiệu chỉnh không tương tác, so EEPROM ↔ tệp, so hai tay | FR-16 – FR-20 |
| Cổng / khoá | `hw/ports.py`, `hw/locks.py` | Liệt kê, tìm theo cử động / rút cáp, dò điện áp; khoá tệp theo thiết bị (`flock` / `msvcrt.locking`) | FR-9 – FR-11 |
| Camera | `hw/cameras.py` | `CameraHub`: một chủ sở hữu mỗi camera, khung hình chung cho vòng điều khiển và xem trước; dò camera | FR-21 – FR-23 |
| Phiên | `sessions/*.py` | teleop, record (+ `recorder.py` luồng ghi), replay, run (suy luận **trong luồng owner**), quỹ đạo, chương trình, rest | FR-24 – FR-27, FR-38, FR-48, FR-52, FR-58 |
| Dữ liệu | `data/*.py`, `profiles.py`, `settings.py` | Danh mục dataset, telemetry đi kèm, lịch sử phiên (30 ngày / 2 GiB), hồ sơ robot, cài đặt, ghi nguyên tử | FR-37, FR-40, FR-66, FR-71 |
| Model | `models/*.py` | Nhập zip / thư mục an toàn, tương thích, nạp + khởi động, kho | FR-45 – FR-47, FR-51 |
| Máy chủ Hibiscus | `remote.py` | Ghép nối, tải lên theo phần (tiếp tục được), danh sách lượt, kéo model | FR-41 – FR-44 |
| Chương trình | `programs/*.py` | Quỹ đạo, tư thế, bộ nhận diện, trình biên dịch / thông dịch khối, chạy thử trên tay giả lập, tín hiệu | FR-52 – FR-60 |
| Giả lập | `mock/*.py`, `tests/sts_emulator.py` | `--mock` (tay / camera / policy giả); bộ giả lập STS3215 qua **pty** (chỉ POSIX) có thời gian dây thật | FR-5, test |
| Chẩn đoán | `doctor.py`, `logs.py` | Báo cáo zip, LIKELY PROBLEMS, nhật ký xoay vòng | FR-63, FR-64 |
| Tương thích OS | `oscompat.py` | MIME cố định, console UTF-8, timer 1 ms (Windows), `replace_file` có thử lại, gốc nhập model | REG-1, REG-17 – REG-19 |
| Giao diện | `web/src/station/**` | Thanh bước, các trang, e-stop, ngăn sức khoẻ, Robot 3D, i18n, Blockly | FR-7, FR-61, FR-62, FR-67, FR-68 |

### 3.2 Mô hình tiến trình và luồng

```
hibiscus-station (1 tiến trình)
 ├─ luồng chính asyncio: uvicorn + FastAPI (REST, /ws, /ws/video), SPA
 │     │ Command (queue, có giới hạn) ──►                ◄── sự kiện (call_soon_threadsafe)
 ├─ HardwareOwner (1 luồng, POSIX nice −5; Windows timeBeginPeriod(1))
 │     mỗi nhịp: e-stop? → đọc leader → SafetyFilter → ghi Goal follower
 │                → (≤ 30 Hz) quan sát follower + khung camera → (thời gian trống) 1 nhóm telemetry
 │     run: suy luận policy NGAY TRONG nhịp (đồng bộ); e-stop kiểm lại giữa suy luận và gửi lệnh
 ├─ CameraHub: mỗi camera một luồng đọc (lerobot) · PreviewEncoder: 1 luồng JPEG
 ├─ DatasetWriter: luồng ghi ảnh của lerobot + save_episode (mã hoá video) trong worker
 ├─ SidecarWriter: telemetry JSONL.gz
 └─ Jobs pool (2): tải lên, kéo model, nhập / nạp model
```

Quy tắc: handler REST không bao giờ chạm phần cứng (gửi Command, chờ ≤ 5 s → `504 hardware_timeout`);
e-stop là `threading.Event` đặt thẳng từ bất kỳ luồng nào (không qua hàng đợi). Mọi luồng dùng chung
**GIL** của CPython: luồng owner cạnh tranh với mã hoá JPEG xem trước, ghi dataset, asyncio. torch,
OpenCV và serialport-rs nhả GIL khi làm việc nặng; đây là rủi ro R-5 cho NFR-2 trên máy yếu.

### 3.3 Máy trạng thái

`disconnected → connecting → idle ⇄ {calibrating, teleop, recording, replaying, inferring,
recording_traj, playing, programming} → stopping → idle`; mọi trạng thái chuyển động → `estopped`
(lý do `user | thermal | electrical | ui_lost | camera_lost`); bus / thiết bị → `error`
(`bus_lost | device_lost`). Bảng đầy đủ: SRS §7. Mỗi lần bắt đầu và kết thúc phiên xoá mục tiêu của
phiên trước (`last_sent`) — sửa REG-10.

### 3.4 Triển khai theo nền tảng

| Nền tảng | Cách cài | Đường chạy | Cổng serial | Camera | Suy luận | Đã kiểm ở đâu (hôm nay) |
|---|---|---|---|---|---|---|
| **Windows 10/11 x64** (Must) | PowerShell: cài uv (không admin) → `uv tool install --python 3.12 [--torch-backend cpu] <wheel URL>`; lệnh `hibiscus-station` trong `%USERPROFILE%\.local\bin` | Cửa sổ console giữ tiến trình; trình duyệt mặc định (Edge) | `COM<n>`; Windows mở cổng **độc quyền** (tiến trình thứ hai nhận `Access is denied`); driver CH340 / CH343 của WCH (người dùng tự cài nếu Windows Update không có) | OpenCV backend MSMF → DSHOW theo số 0, 1, 2… (không có tên thiết bị) | CPU hoặc CUDA (nếu không thêm `--torch-backend cpu`) | CI `windows-latest`: pytest (bỏ qua test pty), build wheel, `uv tool install` + `--mock` smoke, MIME `.js`. **Chưa** chạy với cổng COM, camera, tay thật nào |
| **Ubuntu 22.04 / 24.04 x86_64** (Should) | `uv tool install <wheel>`; tuỳ chọn `deploy/systemd/hibiscus-station.service` (user) | systemd hoặc terminal | `/dev/ttyACM*` (CH343, cdc_acm) / `/dev/ttyUSB*` (CH340); cần nhóm `dialout`; luật udev chỉ do `install.sh` (Docker) cài | V4L2 `/dev/video*` (`by-id`) | CPU / CUDA | CI ubuntu-24.04: toàn bộ pytest (gồm giả lập STS3215 pty), vitest, e2e Playwright Chromium, wheel smoke |
| **Docker trên Linux x86_64** (Could: image `-cpu`; `-cuda` bản xem trước) | `deploy/install.sh` (dò máy, hỏi trước khi cài Docker) → image `-cpu` / `-cuda`; `hibiscus-station-ctl` | compose, `restart`, `stop_grace_period 30s`, uid 10001 | bind `/dev` + `device_cgroup_rules` (cắm / rút nóng), `/dev/hibiscus/arm-*` | `/dev/v4l/by-id` | cpu / cuda | CI: build + chạy `--mock` tới `healthy` (cpu amd64) + Trivy. `-cuda` chỉ build khi có tag, chưa chạy thử |
| **Raspberry Pi 5** (bản xem trước, W-9) | Docker `-cpu` arm64 qua `install.sh` (hoặc wheel aarch64) | như Docker | như Linux | như Linux | CPU (Cortex-A76): ACT chậm; FR-48 tạm dừng khi suy luận > 2 nhịp | Image arm64 chỉ build bằng QEMU khi có tag; chưa chạy trên Pi |
| **Jetson Orin, JetPack 6** (bản xem trước, W-9) | Docker `-jetson` (base NGC PyTorch iGPU) qua `install.sh` (L4T ≠ R36 → dùng `-cpu`) | như Docker + NVIDIA runtime | như Linux | như Linux | CUDA iGPU | Chỉ build trên runner arm64 khi có tag; **chưa chạy trên Jetson**; tương thích base `26.02-py3-igpu` với L4T R36 cần chứng minh (SP-6) |
| macOS 14+ (bản xem trước, W-9) | `uv tool install <wheel>` | terminal | `/dev/tty.usbmodem*` | AVFoundation theo số | CPU / MPS | CI macos-latest: chỉ cài + `--mock` smoke, **không** chạy pytest |
| Docker trên Windows | **Không hỗ trợ** (Docker Desktop không chuyển được USB serial; C-3) | — | — | — | — | — |

**Đường dữ liệu cài đặt wheel (quan trọng cho QC):** `uv tool install <wheel>` **không dùng `uv.lock`**.
Nó giải lại phụ thuộc theo khoảng trong `pyproject.toml` (`fastapi>=0.115,<1`, `uvicorn>=0.30`, torch theo
lerobot…) vào ngày cài, và lấy `lerobot` và `hibiscus` từ **git** (cần `git` trên máy, xem SP-3). Hai
khách cài cùng một wheel ở hai ngày khác nhau có thể nhận hai bộ thư viện khác nhau. Docker thì cố định
(xuất `requirements` từ lock). Hệ quả với chuẩn "ATs PASS trên đúng tệp người dùng cài": xem ADR-13 đề xuất
và flag SA-P1.

## 4. Dữ liệu, lưu trữ, tích hợp

### 4.1 Bố cục trên đĩa

Gốc dữ liệu `~/.hibiscus/station` (Windows `%USERPROFILE%\.hibiscus\station`; đổi bằng `--home` hoặc
`HIBISCUS_STATION_HOME`; `--mock` → `~/.hibiscus/station-demo`; Docker `/data`).

```
<home>/
├── settings.yaml            cài đặt (ngưỡng, tần suất, dead-man phát lại, …)     ghi nguyên tử
├── robots.yaml              hồ sơ robot + hồ sơ hoạt động                          ghi nguyên tử
├── token                    token cục bộ, mới mỗi lần chạy                         0600 (POSIX)
├── station.pid · station.lock   khoá một bản chạy
├── locks/<sha1(thiết bị)>.lock  khoá cổng / camera (flock | msvcrt.locking 1 byte @1 GiB)
├── datasets/<tên>/          LeRobot v3 đúng như lerobot ghi (meta/, data/, videos/)
├── datasets/<tên>.hibiscus/ dataset.json + telemetry/episode_*.jsonl.gz + video-cache/<camera>/ (F-72, ADR-14; không tải lên)
├── models/index.json · models/<key>/   pretrained_model + MANIFEST (đã / chưa xác minh)
├── sessions/<id>/{session.json, telemetry.jsonl.gz}   30 ngày / 2 GiB, xoá lúc khởi động
├── robots/<profile>/…       quỹ đạo, tư thế, bộ nhận diện, chương trình (phiên bản), lần chạy
├── staging/                 giải nén / tải dở
└── logs/station.log         UTF-8, 10 MiB × 5
<HF_LEROBOT_CALIBRATION>/    (mặc định ~/.cache/huggingface/lerobot/calibration, tôn trọng HF_LEROBOT_HOME / XDG_CACHE_HOME)
├── robots/so_follower/<id>.json · teleoperators/so_leader/<id>.json      Station ghi
└── robots/so101_follower/ … (thư mục cũ của LeLab / lerobot cũ)            Station chỉ đọc + "Dùng tệp này"
Token máy chủ Hibiscus: keyring hệ điều hành (Windows Credential Manager); Docker: hibiscus-cli/credentials.json 0600
```

* **Nguồn sự thật:** YAML cho cấu hình, thư mục LeRobot cho dataset, tệp lerobot cho hiệu chỉnh, EEPROM
  servo cho homing / giới hạn đang áp dụng (Station so hai bên, FR-16).
* **Di chuyển dữ liệu:** v1.0 không có định dạng mới; phải đọc mọi dữ liệu 0.2.x (FR-69). Không có số
  phiên bản lược đồ trong `robots.yaml` / `settings.yaml` hôm nay → rủi ro R-9 cho bản sau.
* **Quyền tệp trên Windows:** `chmod 0600` không có tác dụng (chỉ cờ chỉ-đọc); bảo vệ dựa vào ACL hồ sơ
  người dùng. Chấp nhận được cho máy một người dùng; ghi rõ trong NFR-14.

### 4.2 API và tích hợp

| Giao diện | Hợp đồng | Ghi chú |
|---|---|---|
| REST `/api/v1` | `openapi.json` (88 thao tác; v1.1: hai thao tác video của F-72), CI so khớp với mã + kiểu TS sinh | Lỗi RFC 9457 có `code` ổn định (`errors.py`) |
| WS điều khiển `/api/v1/ws` | trạng thái, telemetry, khớp, e-stop, nhịp dead-man 250 ms | Kiểm Origin + token (subprotocol) |
| WS video `/api/v1/ws/video` | JPEG xem trước, khung mới nhất thắng | ≤ 30 fps, 160–640 px |
| Máy chủ Hibiscus v0.1.1 | `/auth/me`, workspace, upload theo phần, model pull, runs (`tests/contract/hibiscus-v0.1.1`) | Qua gói `hibiscus` git `v0.1.1` |
| lerobot / LeLab | Tệp hiệu chỉnh JSON (`homing_offset`, `range_min/max`, `drive_mode`, `id`) | Tương thích hai chiều phải chứng minh theo **phiên bản** (SA-F3) |
| Bus Feetech | Giao thức STS (ping, read, write, sync_read, sync_write) qua rustypot | Thanh ghi: rustypot `STS3215` (63 nhiệt độ 1 B, 69 dòng 2 B, 60 tải 2 B bit dấu 10, 62 điện áp, 65 trạng thái) |
| MQTT / webhook / tín hiệu HTTP | `programs.mqtt_url`, webhook cấu hình, `POST /signals/<tên>` | Could |

## 5. Xuyên suốt

### 5.1 Xác thực và bảo mật
* Chỉ nghe `127.0.0.1:18210`; kiểm Host (`127.0.0.1`, `localhost`, `[::1]`) chống DNS rebinding; mỗi
  lần chạy một token mới; liên kết `/auth?t=` đặt cookie rồi chuyển hướng (token rời lịch sử); yêu cầu
  không phải GET cần `X-Station: 1` (chống CSRF); WS kiểm Origin.
* Chế độ LAN chỉ khi đủ `--host` khác loopback + token cố định ≥ 32 ký tự + danh sách tên máy; thiếu → thoát
  mã 2. Không có TLS trong LAN (ghi rõ: chỉ dùng mạng tin cậy).
* Token máy chủ không bao giờ tới trình duyệt; log che token; zip `doctor` không chứa token.
* Nhập model: zip an toàn (không đường dẫn tuyệt đối, `..`, symlink; giới hạn kích thước và tỉ lệ nén),
  từ chối pickle (`*.bin`, `*.pt`) — `safetensors` only.
* CI: CodeQL, gitleaks, Trivy (image cpu), `pnpm audit` (3 GHSA đang được bỏ qua trong `package.json`,
  phải được Security rà và ghi lý do trước v1.0).

### 5.2 Kiến trúc an toàn (mọi chuyển động)

An toàn được thiết kế theo **lớp**; một lớp hỏng không được làm hỏng lớp dưới nó.

| Lớp | Cơ chế | Ai đảm bảo | Phủ cái gì | Điểm yếu đã biết |
|---|---|---|---|---|
| L0 Nguồn | Người vận hành ngắt nguồn follower bằng tay (C-4) | Người dùng / phần cứng | Mọi lỗi phần mềm, treo PC | Không có công tắc dừng khẩn cứng trong kit SO-101 → khuyến nghị (SA-S2) |
| L1 Firmware servo | `Max_Temperature_Limit` (70 °C), `Protection_Current`, `Unloading_Condition`, giới hạn vị trí EEPROM | Feetech STS3215 | Quá nhiệt / quá dòng thật kể cả khi Station mù | Servo tự ngắt mô-men → **tay rơi** |
| L2 Bộ lọc mỗi nhịp | `SafetyFilter`: `|lệnh − quan sát| ≤ max_relative_target` (5° policy / phát lại / chương trình, 30° teleop / ghi), kẹp trong `[min, max]` hiệu chỉnh; giới hạn thời gian tập do máy chủ áp | Luồng owner | Policy / chương trình phát lệnh xa, tệp hiệu chỉnh sai | Không giới hạn vận tốc / gia tốc tuyệt đối (chỉ theo bước) |
| L3 Dừng | E-stop chốt (lần 1 giữ: `Goal := Present`; lần 2 / Thả lỏng: tắt mô-men), dead-man 1,0 s, `ThermalGuard` (≥ 65 °C × 2 mẫu → dừng an toàn ≤ 2 s), điện (2 lần đọc), mất camera (3 s), mất thiết bị | Luồng owner | Người bấm, mất giao diện, nhiệt, điện | (a) E-stop chỉ kiểm **giữa** các nhịp: với suy luận chậm, lệnh giữ được ghi sau khi suy luận xong (chuyển động vẫn bị chặn ≤ 5°); (b) bảo vệ nhiệt **tắt** khi servo báo 0 °C (REG-13, tay của khách); (c) Space chỉ có tác dụng khi tab Station đang được focus |
| L4 Điều kiện bắt đầu | Không bắt đầu khi: nóng, chưa hiệu chỉnh, e-stop, bận, camera thiếu, model không tương thích, leader xa > 30°, chương trình chưa chạy thử | Owner + API | Bắt đầu sai trạng thái | — |
| L5 Giao diện | Nút DỪNG cố định ≥ 96 px, Space / Esc, banner, khoá điều khiển khi mất WS | Web | Phản hồi cho người | Phụ thuộc trình duyệt và focus |

Bất biến (test tự động phải giữ): không lệnh vị trí nào sau nhịp có e-stop; e-stop / reset không ghi
EEPROM, không đổi tệp hiệu chỉnh (RULE-8); mỗi phiên bắt đầu từ trạng thái sạch (RULE-7); leader không bao
giờ gây dừng (RULE-6); số đo vô lý là "không rõ", không bao giờ gây dừng (RULE-5).

### 5.3 Nhật ký, chẩn đoán, cấu hình
* `logs/station.log` (UTF-8, 10 MiB × 5), dòng khởi động (chế độ, thư mục, hồ sơ, thiết bị), mọi lỗi bus
  (thao tác, thanh ghi, id). `-v` ra console. Không in dòng mỗi nhịp của lerobot.
* `hibiscus-station doctor`: không bao giờ ghi xuống động cơ; đọc từ Station đang chạy qua API, và chỉ mở
  cổng khi Station không giữ nó; LIKELY PROBLEMS; zip không token. **Thiếu**: `Present_Current`,
  `Present_Load` và bản dump thanh ghi thô (SRS K-11, cần cho REG-13).
* Cấu hình: `settings.yaml` (UI Cài đặt, 422 khi sai RULE-4), biến môi trường `HIBISCUS_STATION_*`,
  `HF_LEROBOT_*`. Không có cờ tính năng ẩn.

### 5.4 Ngôn ngữ
`web/src/station/i18n/{vi,en}.json` cùng bộ khoá; mặc định theo trình duyệt (`en*` → English, còn lại →
Tiếng Việt); mã lỗi máy chủ → câu dịch `errors.*`. Chuỗi do máy chủ sinh (CLI, `doctor`, log) là tiếng Anh
(dành cho kỹ sư / nhà cung cấp) — phải nói rõ trong NFR-10 (SA-U1).

### 5.5 Cập nhật và quay lại
* **Wheel:** chạy lại lệnh cài với wheel mới (`uv tool install --force …`); quay lại = cài lại wheel cũ.
  Dữ liệu ở `<home>` và thư mục hiệu chỉnh không bị đụng. Vì phụ thuộc trôi (§3.4), "cài lại wheel cũ"
  không đảm bảo ra **đúng** môi trường cũ → ADR-13.
* **Docker:** `hibiscus-station-ctl backup [--full] | restore | update [TAG] | rollback` — sao lưu, kéo,
  khởi động lại, kiểm sức khoẻ, tự quay lại khi không khoẻ.
* Không có cập nhật trong ứng dụng (W-6, Q-4).

### 5.6 Tắt máy
`lifespan` của FastAPI gọi `station.shutdown()` (dừng phiên, giữ / về nghỉ, tắt mô-men theo hồ sơ,
`finalize` dataset, nhả cổng / camera). Chạy khi: Ctrl+C, `SIGTERM` (`docker stop`, systemd). **Không** chạy
khi người dùng **đóng cửa sổ console** trên Windows (`CTRL_CLOSE_EVENT` không được xử lý; Windows kết thúc
tiến trình sau ~5 s) hoặc khi đăng xuất / tắt máy Windows. Khoá tệp vẫn được hệ điều hành nhả, nhưng tay
giữ mô-men ở mục tiêu cuối và dataset đang ghi có thể không được `finalize` (SA-W3).

## 6. NFR → thiết kế đáp ứng thế nào (tình trạng hôm nay, `12f36da`)

Chú thích: **Đạt** = có thiết kế + bằng chứng đo / test; **Chưa chứng minh** = thiết kế có, chưa đo trên
nền tảng đích; **Không đạt** = thiết kế hiện tại không đáp ứng như yêu cầu đang viết.

| NFR | Thiết kế đáp ứng | Bằng chứng hôm nay | Tình trạng | Cần làm |
|---|---|---|---|---|
| NFR-1 độ trễ teleop | Vòng "lean" 250 Hz: đọc leader → lọc → ghi Goal; quan sát / camera ≤ 30 Hz; telemetry ở nhịp trống | `teleop_bench.py` (giả lập, 1 Mbaud, timer USB 1 ms): p50 **55 ms**, LeLab mô phỏng 54 ms; adapter 8 ms: 65 ms (LeLab 67) | Đạt trên giả lập; **chưa chứng minh** trên Windows + tay thật; **định nghĩa đo không khớp** (số trên màn hình là độ trễ phần mềm, không phải độ trễ vật lý) | SA-N1 |
| NFR-2 nhịp vòng | `Deadline` perf_counter, không dồn trễ; Windows `timeBeginPeriod(1)`; POSIX `nice −5` | 229 Hz trên giả lập; ghi 30 Hz trên Linux | Chưa chứng minh trên Windows; **"nhịp trễ < 1 %" không đạt theo định nghĩa** khi fps mục tiêu (250) vượt khả năng bus — mọi nhịp đều trễ | SA-N2 |
| NFR-3 e-stop | `Event` đặt từ mọi luồng, kiểm đầu nhịp + giữa suy luận và gửi lệnh; `Goal := Present` | `test_field_028.py`, test một nhịp | Phần mềm **đạt** cho teleop / quỹ đạo / chương trình; với suy luận chậm thời gian tới lệnh giữ = thời gian suy luận (chuyển động vẫn ≤ 5°); "tay đứng yên < 100 ms" vật lý **chưa chứng minh** | SA-N3 |
| NFR-4 dead-man | `Watchdog` 1,0 s, kiểm mỗi nhịp | test | Đạt khi nhịp ngắn; khi suy luận dài (SmolVLA CPU > 1 s) e-stop trễ tới hết suy luận | SA-N3 |
| NFR-5 khởi động | torch / policy nạp lười; import ứng dụng 0,5 s (Linux, đo vòng này) | Linux | Linux đạt (ước lượng); Windows **chưa chứng minh** (Defender quét lần đầu, MSMF mở camera chậm) | SA-W5 |
| NFR-6 dừng nhiệt ≤ 2 s | Nhiệt + trạng thái 2 Hz, bắt buộc đọc khi mẫu > 2 s; 2 mẫu → dừng an toàn (về nghỉ ≤ 1,5 s → tắt mô-men) | test với giả lập | Đạt trên giả lập; **không có tác dụng trên tay của khách** (0 °C ⇒ không có mẫu thật nào) | SA-S1, SP-1 |
| NFR-7 phục hồi | Mọi đường ở SRS §7 có lối ra; `device_lost` không thử lại; kết nối lại theo serial / VID:PID | `test_device_lost.py`, `test_field_028.py` | Linux đạt; Windows (COM thật, số COM đổi) **chưa chứng minh** — test pty bị bỏ qua trên Windows | SA-C1 |
| NFR-8 phiên dài | Danh sách thống kê có giới hạn (`all_latency` ≤ 100 000) | Không có test dài | **Chưa chứng minh** | Tech Lead: thêm job `slow` |
| NFR-9 nền tảng | §3.4 | CI smoke Windows / macOS; Linux đầy đủ | Windows: chỉ smoke + pytest một phần; Pi 5 / Jetson / cuda: **chưa chạy bao giờ** | SA-P2 |
| NFR-10 ngôn ngữ | Bộ khoá vi/en chung, `errors.*` | test khoá | **Không đạt** (K-3 "Hiệu chuẩn" còn 4 chỗ trong `vi.json`; K-4 chi tiết lỗi tiếng Anh) | sửa chuỗi |
| NFR-11 a11y | Radix, jsx-a11y, axe-core trong vitest | test giao diện | Chưa chứng minh toàn bộ; **trình soạn Blockly không đi được bằng bàn phím** | SA-U2 |
| NFR-12 thông tin đúng | Lọc hợp lý ở `feetech.plausible`, leader không cảnh báo | `test_field_028.py`, `test_units.py` | Thiết kế đạt; "0 cảnh báo giả 30 phút trên tay khách" chỉ UAT | — |
| NFR-13 độ chính xác telemetry | Bảng đơn vị một nơi (`feetech.py`) | Không | **Không đạt** trên tay của khách (0 °C, dòng ~1000 thô); đơn vị dòng 6,5 mA/bước chưa xác nhận | SP-1, SA-S1, SA-N4 |
| NFR-14 bảo mật | §5.1 | test bảo mật API, CodeQL, gitleaks, Trivy | Gần đạt; còn: giấy phép gói `hibiscus`, 3 GHSA bị bỏ qua, chưa rà soát độc lập | SA-L1 |
| NFR-15 dữ liệu | Ghi qua API `LeRobotDataset` của lerobot, `finalize` luôn gọi | test ghi | Đạt với lerobot 0.7.1; "mở được bằng lerobot của LeLab" phụ thuộc phiên bản LeLab | SA-F3 |
| NFR-16 ngoại tuyến | Không gọi mạng khi chạy, font / hình cục bộ | — | **Không đạt cho một số model**: SmolVLA và adapter PEFT tải backbone từ HF Hub lần đầu (`loader.py`) | SA-F4 |
| NFR-17 tải lên tiếp tục | Upload theo phần của Hibiscus CLI | `test_remote_e2e.py` (fake server) | Đạt với máy chủ giả | — |
| NFR-18 chất lượng mã / CI | ruff, mypy strict (×3 nền tảng), pytest, vitest, e2e | CI | **Không đạt**: Windows bỏ qua ≈ 16 test pty (REG-4/5/7/8/14), không vitest / e2e / Edge trên Windows; macOS không pytest; image arm64 / cuda / jetson không chạy | SA-C1, SA-C2 |

## 7. Rủi ro, spike, quyết định

### 7.1 Rủi ro kỹ thuật

| ID | Rủi ro | Xác suất / tác động | Giảm thiểu |
|---|---|---|---|
| R-1 | Nguyên nhân 0 °C / dòng ~1000 thô không tìm ra → bảo vệ nhiệt tắt vĩnh viễn trên tay của khách | Cao / Cao (an toàn) | SP-1; SA-S1 (hành vi khi mù nhiệt) |
| R-2 | Môi trường cài trên PC khách khác môi trường đã kiểm (phụ thuộc trôi, git) | Cao / Cao | ADR-13 (cố định phụ thuộc khi phát hành), SP-3 |
| R-3 | Lỗi chỉ lộ trên Windows + COM thật (đổi số COM, selective suspend, driver CH34x, MSMF) vì CI không phủ | Cao / Cao | SP-2 (Windows có cổng COM ảo trong CI), danh sách UAT ngắn có video |
| R-4 | lerobot thay đổi API riêng tư Station đang gọi (`bus._handshake`, `_scan`, `dev._load_calibration`, `super()._set_torque`, phân lớp `SerialMotorsBus`) khi nâng phiên bản | Trung bình / Cao | ADR-3 (ghim commit), lớp chống đổi (`StationMotorsBus`, `factory.py`), test hợp đồng lerobot trước mỗi lần nâng |
| R-5 | GIL + mã hoá JPEG / video + trình duyệt trên cùng PC yếu → nhịp không đều (NFR-2) | Trung bình / Trung bình | Đo trên PC khách (AT-89); giảm fps xem trước khi đang ghi |
| R-6 | Tranh chấp cổng với LeLab trên **Linux**: tty không độc quyền mặc định; nếu LeLab mở trước, Station có thể mở cùng cổng → hai bên cùng lái bus | Thấp / Cao | SP-5: kiểm `/proc/*/fd` trước khi mở, xác nhận serialport-rs đặt `TIOCEXCL` |
| R-7 | Tệp hiệu chỉnh không tương thích với phiên bản lerobot mà LeLab của khách đang dùng (LeLab không ghim lerobot) | Trung bình / Trung bình | SA-F3: ma trận phiên bản trong UAT |
| R-8 | Quy tắc zero-defect + 71 tính năng + UAT chỉ ở phía khách → vòng UAT dài, nhiều lượt | Cao / Trung bình | SA-Q1: UAT rút gọn, ưu tiên Must |
| R-9 | Không có số phiên bản lược đồ cho YAML → khó di chuyển dữ liệu ở bản sau | Thấp / Trung bình | Thêm `schema: 1` khi đọc / ghi (không đổi định dạng hiện tại) — đề xuất cho Tech Lead |
| R-10 | Base image Jetson / arm64 chưa từng chạy trên thiết bị thật | Cao / Thấp (Could) | SP-6 hoặc ghi "bản xem trước" |

### 7.2 Spike (phải chứng minh sớm, trước khi chốt mốc)

| ID | Câu hỏi | Cách làm | Ai / ở đâu | Đầu ra |
|---|---|---|---|---|
| **SP-1** | Vì sao servo của khách đọc 0 °C và dòng ~1000? | (1) `doctor` thêm bản dump thô từng servo bằng `read` **riêng lẻ** (không sync_read) của khối thanh ghi 56–70 và địa chỉ 0–3 (firmware, model), cùng `Present_Current`, `Present_Load`; (2) khách chạy công cụ **Feetech FD** chính hãng (Windows) trên cùng tay và chụp màn hình nhiệt độ / dòng — đối chứng độc lập với lerobot / rustypot; (3) so với tay giả lập STS3215 | Dev + khách (5 phút) | Kết luận: firmware / clone không có cảm biến, sai thanh ghi, sai giải mã, hay bộ chuyển. Đóng REG-13, quyết định NFR-13 |
| **SP-2** | Chạy được bộ giả lập STS3215 với cổng COM thật trên Windows CI không? | Cặp COM ảo (com0com / tương đương) trên `windows-latest`, `sts_emulator` nói ở một đầu, Station mở đầu kia; nếu runner không cho cài driver: runner Windows tự host có một bộ chuyển CH343 + vi điều khiển giả lập servo | DevOps | Test pty hiện bị bỏ qua chạy được trên Windows (SA-C1) |
| **SP-3** | `uv tool install <wheel>` trên Windows sạch (không có git, không có Python) có chạy không, và có cố định được phụ thuộc không? | VM Windows 11 sạch (Windows Sandbox / VM CI không có git): cài theo README; thử `--constraints <tệp từ uv.lock>` / `--exclude-newer` / wheelhouse đính kèm bản phát hành | DevOps | Lệnh cài đặt v1.0 (ADR-13) |
| SP-4 | Teleop đạt bao nhiêu Hz trên Windows + CH340 / CH343 thật? | `doctor` đã đo ms mỗi lần đọc; khách gửi `doctor` + tóm tắt phiên teleop 2 phút | Khách | Điều chỉnh đích NFR-1 / NFR-2 theo số đo (SA-N2) |
| SP-5 | Trên Linux, Station có phát hiện được LeLab đang giữ cùng tty? | Test với hai tiến trình trên pty và `/dev/ttyACM` thật | Dev | Hành vi `port_busy` đúng trên Linux |
| SP-6 | Image `-jetson` (NGC `26.02-py3-igpu`) chạy trên JetPack 6 / L4T R36? Image arm64 chạy trên Pi 5? | Chạy trên thiết bị mượn hoặc runner arm64; nếu không có thiết bị → hạ xuống "bản xem trước" | DevOps | Giữ / bỏ khỏi v1.0 |
| SP-7 | Đóng cửa sổ console Windows có dừng an toàn được không? | `SetConsoleCtrlHandler` bắt `CTRL_CLOSE_EVENT` / `CTRL_LOGOFF` / `CTRL_SHUTDOWN` → `station.shutdown()` trong ≤ 5 s | Dev | Đáp ứng FR-75 trên Windows (SA-W3) |

### 7.3 Nhật ký quyết định (ADR, quyết định đã có trong sản phẩm)

| ADR | Quyết định | Lý do | Hệ quả / điều kiện xét lại |
|---|---|---|---|
| ADR-1 | Ứng dụng web cục bộ (FastAPI + React) trong **một** tiến trình Python, mở bằng trình duyệt | Cài bằng một lệnh, chạy cả trên máy không màn hình (Pi / Jetson) và điều khiển từ điện thoại trong LAN | Không có cửa sổ ứng dụng riêng; tắt cửa sổ console = tắt Station (SA-W3) |
| ADR-2 | Phân phối Windows / Linux / macOS bằng **wheel + `uv tool install`**; Docker chỉ cho Linux | uv tự cài Python 3.12, không cần admin; Docker Desktop không chuyển được USB serial | Phụ thuộc trôi (ADR-13); cần git (SP-3) |
| ADR-3 | Ghim `lerobot` ở git `fe1c545` (0.7.1), không vendor, không fork, không vá LeLab | Cùng hành vi / định dạng với lerobot; lerobot 0.7.1 không có trên PyPI | Nâng lerobot = CR có kiểm hợp đồng (R-4) |
| ADR-4 | **Một luồng sở hữu phần cứng** (`HardwareOwner`); REST / WS chỉ gửi lệnh; e-stop là cờ đặt trực tiếp | Không bao giờ có hai bên ghi bus; e-stop không chờ hàng đợi | Mọi thao tác phần cứng tuần tự; handler chờ ≤ 5 s |
| ADR-5 | Suy luận policy **đồng bộ trong nhịp** | Quan sát và lệnh thuộc cùng một nhịp; không dồn lệnh cũ | E-stop / dead-man trễ bằng thời gian suy luận (SA-N3); suy luận bất đồng bộ là W-8 |
| ADR-6 | Vòng teleop "lean" 250 Hz (quan sát / camera ≤ 30 Hz, telemetry ở nhịp trống), giới hạn bước teleop 30° | Sửa REG-5: ngang LeLab trên giả lập | Đích Hz phụ thuộc bus thật (SA-N2) |
| ADR-7 | Mọi thanh ghi / đơn vị / bit trạng thái Feetech ở **một** tệp (`hw/feetech.py`); số đo vô lý = "không rõ" | Sửa REG-3 / REG-11; dễ sửa khi SP-1 có kết quả | Đơn vị dòng và bit trạng thái chưa xác nhận trên phần cứng |
| ADR-8 | Thử lại 2 lần mọi lệnh bus (trừ telemetry), **không** thử lại khi thiết bị mất | Sửa REG-14 (gói hỏng) và REG-8 (Access is denied) | Phân loại dựa trên chuỗi lỗi của OS / rustypot (cần test khi nâng rustypot) |
| ADR-9 | Khoá thiết bị bằng tệp khoá theo hệ điều hành (`flock` / `msvcrt.locking` 1 byte ở 1 GiB) | Hai Station không bao giờ mở cùng cổng; đọc được PID người giữ | Không chặn tiến trình ngoài Station trên Linux (R-6) |
| ADR-10 | Chạy thử (dry run) trên tay giả lập bắt buộc trước khi chạy chương trình trên robot | An toàn cho người mới | Kỹ sư tắt được (`programs.require_dry_run`) |
| ADR-11 | Chỉ nhận trọng số `safetensors`; giải nén zip an toàn | Pickle chạy mã tuỳ ý | Model `.bin` / `.pt` phải chuyển đổi trước |
| ADR-12 | Dùng lại gói `hibiscus` (Hibiscus CLI) cho liên kết máy chủ, ghim `v0.1.1` → `v0.1.2` | Không sao chép mã tải lên / kéo | Metadata v0.1.1 ghi "Proprietary"; QĐ-4 = A: chủ sở hữu phát hành v0.1.2 Apache-2.0 (EXT-1), Station ghim lại (SA-L1, AT-98) |
| ADR-13 *(chấp nhận, QĐ-3 = A, 2026-11-17)* | Bản phát hành v1.0 cố định toàn bộ phụ thuộc của wheel theo `uv.lock` (tệp constraints / wheelhouse đính kèm release) và không cần git trên máy khách | Chuẩn "kiểm đúng tệp người dùng cài"; quay lại ra đúng môi trường cũ | Cần SP-3; thay đổi lệnh cài trong README |
| ADR-14 *(v1.1, CR-1, 2026-11-19)* | **Video từng tập (F-72): giữ nguyên cách ghi AV1 của LeRobot; Station cắt tập ra khỏi tệp mp4 chung và, khi trình duyệt không phát được AV1, chuyển sang H.264 / VP9 một lần, lưu tạm.** Ghi: LeRobot 0.7.1 mã hoá bằng `VideoEncoderConfig` mặc định = `libsvtav1` (AV1, `yuv420p`, g = 2, crf 30, preset 12; `meta/info.json`: `"video.codec": "av1"`); Station không truyền `rgb_encoder`. Xem: `GET …/episodes/{i}/videos` (codec, chuỗi `mime` RFC 6381 `av01.0.05M.08`, thời lượng, lỗi) và `GET …/videos/{camera}?format=source\|h264\|vp9` (`hibiscus_station/data/video.py`): `source` = chép các gói của `[from_timestamp, to_timestamp)` từ khung khoá đầu tập (LeRobot mã hoá từng tập riêng rồi nối, nên tập bắt đầu bằng khung khoá) sang mp4 nhỏ, không mã hoá lại (≈ 0,2 s / 30 s 640×480); `h264` = libx264 `veryfast` + `zerolatency` (không B-frame; libopenh264 nếu thiếu x264) mp4 `faststart`; `vp9` = libvpx-vp9 `realtime` WebM; khung khoá mỗi giây. Tất cả bắt đầu ở t = 0 = khung đầu của tập. Bản cắt nằm ở `<tên>.hibiscus/video-cache/<camera>/episode_<i>.<định dạng>.<khoá>.*`, khoá = băm (tên tệp, kích thước, mtime, from, to) → tệp gốc đổi (ghi thêm, ghi lại) thì cắt lại; khoá theo tệp đích, ghi nguyên tử. Trình duyệt: `canPlayType` chọn `source` → `h264` → `vp9`; `error` của `<video>` → thử định dạng sau; hỏi lại `Range: bytes=0-0` để đọc mã lỗi (`video_missing`, `episode_saving` dừng thử). Đồng bộ: camera đầu tiên phát được là đồng hồ chủ, camera khác bị kéo về khi lệch > 0,25 s; biểu đồ telemetry dùng `frame_index / fps` (trường mới `TelemetrySeries.frame_index`) làm trục thời gian. Phục vụ bằng `FileResponse` của Starlette (Range 206 / 416, ETag); cùng middleware xác thực (cookie HttpOnly `hst` mà `<video>` tự gửi, hoặc Bearer). Đang ghi: phiên đang mở dataset → 409 `episode_saving` (LeRobot giữ chỉ mục tập trong bộ đệm tới `finalize` và nối tập mới vào tệp mp4 đang mở). | (1) Edge trên Windows 11 cài sẵn không giải mã AV1 (cần "AV1 Video Extension" của Store); Chrome, Firefox có dav1d sẵn. VP9 được cả ba trình duyệt tự giải mã (không cần Media Foundation, cả Windows N); H.264 nhẹ và nhanh hơn VP9 khi có Media Foundation. (2) **Không** ghi bằng H.264: LeRobot cho phép (`rgb_encoder.vcodec="h264"`), và huấn luyện / máy chủ Hibiscus đọc được (hợp đồng máy chủ v0.1.1 ghi `codec: av1` và `browser_playable_hint`), nhưng (a) mọi dataset 0.2.x đã ghi AV1 vẫn phải xem được, (b) "ghi thêm" (F-39) không được trộn codec trong cùng tệp mp4 nối (LeRobot nối bằng chép gói), (c) đổi định dạng dataset là đổi hành vi lerobot (ADR-3), (d) H.264 cùng chất lượng thường lớn hơn AV1 (đĩa, thời gian tải lên). (3) Cắt theo tập thay vì phục vụ cả tệp nối: thời gian video = thời gian tập, không lộ tập khác, không đọc tệp đang được nối. (4) Bộ mã hoá đi kèm PyAV (đã là phụ thuộc của lerobot): không thêm gói, không cần ffmpeg hệ thống. | Mã hoá lại lần đầu tốn CPU: đo trên PC dev 12 luồng, 30 s 640×480 30 fps khung nhiễu (trường hợp xấu nhất) ≈ 6 s H.264, ≈ 11 s VP9 mỗi camera; cảnh camera thật nén nhanh hơn; Pi 5 / Jetson chậm hơn nhiều (bản xem trước, W-9). Bộ đệm không giới hạn dung lượng (≈ cỡ video gốc mỗi định dạng đã xem), xoá cùng dataset; xoá tay được bất cứ lúc nào. Xét lại khi: lerobot đổi codec mặc định, Edge có AV1 sẵn, hoặc khách cần xem ngay khi đang ghi. Chưa kiểm trên Edge thật của Windows 11 cài sẵn (UAT-1 bước 16, AT-99 bước 8); CI chỉ có Edge của `windows-latest` (Windows Server). |

## 8. Rà soát yêu cầu

Danh sách flag đầy đủ (mã yêu cầu · vấn đề · đề xuất thay thế): **[REVIEW-SA.md](REVIEW-SA.md)**. Tóm tắt
các mục chặn duyệt: SA-S1 (Q-5, chạy khi mù nhiệt), SA-P1 (môi trường cài không cố định), SA-C1 (CI Windows
bỏ qua test bus), SA-N1 / SA-N2 / SA-N3 (NFR hiệu năng và e-stop đo không được như đang viết), SA-L1 (giấy phép
gói `hibiscus`), SA-Q1 (danh sách UAT của khách quá dài).
