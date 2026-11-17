# Hibiscus Station: rà soát của Tech Lead · vòng 1 (2026-11-17)

Đầu vào: bản nháp v0.1 của BA ([FEATURES.md](FEATURES.md), [ACCEPTANCE.md](ACCEPTANCE.md), [SRS.md](SRS.md),
[REGRESSION.md](REGRESSION.md), [BRD.md](BRD.md) §9). Sản phẩm được đánh giá: Station **0.2.8**, nhánh
`docs/requirements-v1` (mã giống `main` `12f36da`), **đúng tệp người dùng cài** (wheel build từ mã này, cài vào
môi trường uv mới). Tech Lead đánh giá độc lập với SA; không sửa mã ở vòng này.

Tóm tắt một dòng: **phần lõi chạy tốt và có nền test vững (515 + 173 test xanh, lint / kiểu sạch), nhưng chưa đạt
chuẩn zero-defect: 18 lỗi (2 High, 6 Medium, 10 Low), test e2e của chính repo đang đỏ, và 16/71 tính năng chỉ
chứng minh được trên Windows + tay thật / máy chủ / Docker.** Ước lượng để đạt zero-defect toàn bộ 71 tính năng:
**khoảng 82 ngày công dev** (76 theo tính năng + 6 cho nền kiểm tự động; chưa tính QC ~30 % và thời gian chờ UAT),
chia 4 mốc (M0–M3) ở §5.

---

## 1. Đã kiểm gì, bằng gì (Linux x86_64, không có Windows / tay thật)

| Kiểm tra | Kết quả |
|---|---|
| `ruff check` · `ruff format --check` | 0 lỗi · 128 tệp đúng định dạng |
| `mypy --strict` (Linux, `--platform win32`, `--platform darwin`) | 0 lỗi trên 83 tệp nguồn, cả ba nền tảng |
| `pytest -q` (cấu hình mặc định của repo) | **515 passed, 1 skipped** (khoá byte-range chỉ có trên Windows), 2 deselected (e2e), 1 warning (Starlette deprecation), 605 s |
| Web: `eslint --max-warnings 0`, `prettier --check`, `tsc`, `check:api` | đều đạt |
| Web: `vitest` (coverage) | 13 tệp, **173 test passed**; statements 80,94 %, branches 80,36 %, functions 74,25 % |
| Web: `vite build` + kiểm CSP bundle | đạt; chunk lớn nhất BlocklyEditor 789 kB (202 kB gzip), TwinCanvas 682 kB (174 kB gzip), index 480 kB (148 kB gzip), đều lazy-load trừ index |
| Build wheel / sdist | `hibiscus_station-0.2.8-py3-none-any.whl` 1,55 MB (có UI), sdist 2,4 MB |
| Cài wheel vào môi trường mới (`uv tool install --python 3.12 --torch-backend cpu <wheel>`) | đạt; torch 2.15.0+cpu, lerobot 0.7.1; `hibiscus-station --version` = 0.2.8 |
| **Test e2e Playwright của repo** (`tests/e2e`, chạy với cổng cố định 18330) | **FAIL** (D-1): tìm thẻ "Follower" ở trang Hiệu chỉnh đã bị thay từ 0.2.7 |
| Station `--mock` trên 127.0.0.1:18310 | sẵn sàng (`health` = 0) sau **1,69 s**; trang Chào mừng tải 0,37–0,41 s |
| Station chế độ thật trên 127.0.0.1:18320 với 2 giả lập STS3215 pty (`tests/sts_emulator.py`, thời gian thật) | trả lời sau 0,56 s; kết nối hồ sơ 1,06 s; hiệu chỉnh 2 tay qua API; teleop 250 fps; e-stop; mất thiết bị |
| Đi giao diện bằng Playwright (Chromium, `vi-VN`) | 14 màn hình × sáng / tối × 1280 / 390 px = 56 ảnh: **0 cuộn ngang**, 0 chữ thô (`undefined`, `NaN`, `internal_error`…); 6/6 bước bị khoá hiện trang khoá, nút tắt |
| `tests/teleop_bench.py` (giả lập, latency timer 1 ms và 8 ms) | xem AT-31 và D-9 |
| Bộ chuỗi `vi` / `en` | 981 khoá mỗi bên, 0 khoá thiếu / trống; 6 chuỗi "Hiệu chuẩn" (K-3) |

Bằng chứng: 4 ảnh nhỏ trong [evidence/round1/](evidence/round1/); ảnh đầy đủ, log server, kết quả bench và
`doctor` nằm ở thư mục tạm của vendor (không đưa vào repo). Mọi server đã khởi động trong vòng này đã tắt.

**Không chạy được ở vòng này (và lý do):** Windows (không có máy; CI `windows-latest` chỉ chạy khi push, vòng này không
push); tay SO-101 thật, cổng COM, camera USB thật; máy chủ Hibiscus thử v0.1.1; Docker / Pi 5 / Jetson (quy định
không động vào container); chế độ LAN (quy định chỉ bind 127.0.0.1); "Kết nối lại" sau khi pty quay lại (giả lập pty
không phải thiết bị USB nên Station không dò lại được; test đơn vị `tests/test_device_lost.py` vẫn đạt).

---

## 2. Kết quả theo AT đã chạy được trên Linux

| AT | Kết quả vòng 1 | Ghi chú |
|---|---|---|
| AT-2 | **FAIL** (cục bộ) | e2e đỏ (D-1); job Windows / macOS không chạy được tại chỗ |
| AT-3 | PASS (phần wheel) | systemd chưa thử |
| AT-6 | **FAIL** | lần hai và `url` đúng; cổng bị chương trình khác giữ → lỗi thô, không gợi ý `--port` (D-3); `url` in liên kết chết khi Station đã tắt (D-4) |
| AT-7 | **FAIL** | demo: teleop bị từ chối `leader_far` ngẫu nhiên, kiểm tra hai tay luôn lệch (D-8) |
| AT-8 | PASS | không cookie → 401; `Host: evil.com` → `403 forbidden_host`; POST thiếu `X-Station` → `403 csrf`; Bearer token chạy |
| AT-9 | NOT RUN | cần bind ngoài loopback (quy định môi trường); test đơn vị có |
| AT-10 | **FAIL** | khoá đúng 6/6 bước, nút tắt, lý do e-stop đúng; nhưng "lý do của Station" là câu tiếng Anh kèm đường dẫn đầy đủ (D-5) |
| AT-16 | PASS (giả lập) | kết nối 1,06 s, 6 động cơ mỗi tay có nhiệt độ |
| AT-19 | PASS một phần | `error(device_lost)` sau 0,01 s, có tay / cổng / thông báo hệ thống, 0 dòng tắt mô-men lặp; kết nối lại vào pty mới: không kiểm được bằng wheel |
| AT-24 | PASS (API) | `finish_ranges` trước `set_home` → 422 |
| AT-26 | **FAIL** | kẹp đo bằng % nhưng câu báo "lệch hơn 20°"; luôn liệt kê cả 3 nguyên nhân (D-7) |
| AT-31 | **FAIL có điều kiện** | 1 ms: p50 4,6 ms, p95 7,3 ms, 228 Hz, 0 % bị cắt (đạt). 8 ms, cử động nhanh: 86 Hz, **84,6 % nhịp bị cắt**, trễ bám 83 ms so với LeLab 68 ms (D-9) |
| AT-32 | PASS (test) | |
| AT-36 / AT-88 (phần phần mềm) | PASS | sau khi bấm e-stop: đúng 1 lệnh sync-write (6 động cơ) lúc 6,8 ms (nhịp hiện tại), 0 lệnh sau 20 ms |
| AT-37 | **FAIL** | lần bấm thứ hai trong 2 s tắt mô-men đúng, nhưng giao diện **không** hiện "Hãy đỡ tay robot" (D-6) |
| AT-38 | PASS | phát lại không có giao diện → `estopped(ui_lost)` sau 1,05 s |
| AT-42 (phần giả lập) | PASS | 67 °C → `estopped(thermal)`; đặt lại khi còn nóng → `409 motor_hot` |
| AT-46 (F5) | PASS | tải lại trang giữa teleop: trạng thái giữ nguyên, nút Dừng có |
| AT-48 | PASS có lỗi kèm | ghi 2 tập bằng phím → "Đã lưu 2 tập"; trong lúc lưu tập, server trả 500 (D-2) |
| AT-57 (đường dẫn) | PASS | `/etc`, `/tmp` → `forbidden` (trong công việc nhập); gửi sai định dạng → 500 (D-16) |
| AT-70 (bước 1) | PASS | "Chương trình mới" mở form, con trỏ ở ô tên |
| AT-77 | **FAIL** | không ghi gì xuống động cơ, zip không có token / `hbp_`; nhưng: Station đã tắt → "ConnectError" thô; cổng bị giữ không vào LIKELY PROBLEMS; chưa đọc dòng / tải (K-11) (D-15) |
| AT-79 | PASS | đang chạy → 0; tắt → 1 sau 0,17 s |
| AT-80 (API) | PASS một phần | ngưỡng sai bị từ chối 422 với lý do; lý do là tiếng Anh (thuộc D-5) |
| AT-81 | PASS một phần | `vi-VN` → tiếng Việt; đổi ngôn ngữ giữa teleop không ảnh hưởng phiên; bộ khoá đủ |
| AT-82 | **FAIL** | 0 cuộn ngang; nhưng chip robot bị cắt chữ ở 390 px (D-14), nút e-stop che chú thích Robot 3D (D-13); axe chưa chạy |
| AT-87 (Linux) | PASS | 1,69 s (mock), 0,56 s (thật) ≤ 10 s; kết nối ≤ 5 s |

Các AT còn lại: chưa chạy tay ở vòng 1; test tự động tương ứng đều xanh (515 / 173).

---

## 3. Đánh giá theo tính năng

Trạng thái: **ĐẠT\*** = vòng 1 không thấy lỗi (test tự động xanh + phần chạy tay nếu có); *chưa phải PASS của QC*.
**LỖI** = có lỗi so với chuẩn (mã D-n ở §4 hoặc K-n của BA đã xác nhận). **KHÔNG KIỂM ĐƯỢC** = phần quyết định chỉ
chứng minh được trên Windows / tay thật / máy chủ / Docker (NOT VERIFIED cho tới UAT hoặc môi trường phù hợp).

Effort = công dev để đạt zero-defect (sửa lỗi + tự động hoá AT của tính năng + tài liệu): **S** ≈ 0,5 ngày, **M** ≈ 2
ngày (1–3), **L** ≈ 5 ngày (4–7).
Mốc: xem §5.

| F | Trạng thái | Lỗi / ghi chú | Effort | Phụ thuộc thêm (ngoài cột Phụ thuộc của BA) | Mốc |
|---|---|---|---|---|---|
| F-1 | KHÔNG KIỂM ĐƯỢC | build + cài wheel đạt trên Linux; K-8 (cập nhật cần gõ lệnh có số phiên bản) | M | quy trình phát hành tạo wheel trên GitHub Releases (release.yml, chưa chạy thử); CI Windows xanh | M1 |
| F-2 | ĐẠT\* | systemd chưa thử | S | — | M1 |
| F-3 | LỖI | K-1 (README ghi image 0.2.1); Pi 5 / Jetson không có máy | M | máy Pi 5 / Jetson hoặc khách chấp nhận "chưa nghiệm thu" (Q-1) | M3 |
| F-4 | LỖI | D-3, D-4 | S | — | M1 |
| F-5 | LỖI | D-8 | M | — | M1 |
| F-6 | ĐẠT\* | phần cục bộ đạt (AT-8); LAN chưa chạy | S | môi trường QC có mạng cô lập cho AT-9 | M1 (LAN: M3) |
| F-7 | LỖI | D-5 (lý do thô, có đường dẫn) | S | FL-1 | M1 |
| F-8 | ĐẠT\* | | S | — | M1 |
| F-9 | KHÔNG KIỂM ĐƯỢC | pty không phải USB → danh sách trống (đúng thiết kế) | S | adapter USB thật (vendor có thể mua CH340 để kiểm phần không cần tay) | M1 |
| F-10 | KHÔNG KIỂM ĐƯỢC | test đơn vị `test_ports_roles.py` xanh | S | như F-9 | M1 |
| F-11 | KHÔNG KIỂM ĐƯỢC | `ports/probe` trên pty trả rỗng | S | như F-9 | M1 |
| F-12 | ĐẠT\* | | S | — | M1 |
| F-13 | KHÔNG KIỂM ĐƯỢC | phát hiện mất thiết bị đạt; kết nối lại cần thiết bị USB / COM thật | M | UAT Windows | M1 |
| F-14 | ĐẠT\* | | S | — | M1 |
| F-15 | ĐẠT\* | | S | — | M1 |
| F-16 | ĐẠT\* | | S | — | M1 |
| F-17 | LỖI | D-1 (e2e lỗi thời), D-17, K-2 | M | — | M0 (D-1) / M1 |
| F-18 | ĐẠT\* | | S | — | M1 |
| F-19 | LỖI | D-7 | M | FL-9 (bỏ phụ thuộc F-24 → F-19) | M1 |
| F-20 | KHÔNG KIỂM ĐƯỢC | cùng thư mục / định dạng với lerobot; cần lerobot + tay thật | S | UAT | M1 |
| F-21 | KHÔNG KIỂM ĐƯỢC | chỉ có camera giả lập | S | webcam USB cho QC (rẻ, nên mua) | M1 |
| F-22 | LỖI | D-10 (chữ "tick khung hình") | S | — | M1 |
| F-23 | KHÔNG KIỂM ĐƯỢC | test xanh; cần rút camera thật | S | webcam USB | M1 |
| F-24 | LỖI | D-9 (High), D-10, D-11 | L | FL-2 (định nghĩa lại NFR-1 / NFR-2); số đo độ trễ adapter của khách (doctor) | M1 |
| F-25 | LỖI | D-5 (câu tiếng Anh dưới câu Việt, thiếu "°") | S | — | M1 |
| F-26 | ĐẠT\* | cảnh báo đúng khi > 20 % nhịp bị cắt; sẽ bật ở 8 ms (hệ quả D-9) | S | F-24 / D-9 | M1 |
| F-27 | ĐẠT\* | | S | — | M2 |
| F-28 | LỖI | D-6, D-13 | M | — | M1 |
| F-29 | ĐẠT\* | 1,05 s | S | — | M1 |
| F-30 | LỖI | K-5 (hướng dẫn ghi 5° cho mọi chuyển động) | S | — | M1 |
| F-31 | KHÔNG KIỂM ĐƯỢC | REG-13 mở; độ chính xác cần dụng cụ đo | M | báo cáo `doctor` của khách sau khi sửa K-11 | M1 |
| F-32 | ĐẠT\* | | S | — | M1 |
| F-33 | KHÔNG KIỂM ĐƯỢC | hành vi trên giả lập đúng; chờ REG-13 + quyết định Q-5 | M | Q-5, REG-13 | M1 |
| F-34 | ĐẠT\* | | S | — | M1 |
| F-35 | ĐẠT\* | `interrupted` đặt đúng sau e-stop | S | — | M1 |
| F-36 | ĐẠT\* | | S | — | M1 |
| F-37 | ĐẠT\* | | S | — | M2 |
| F-38 | LỖI | D-2 | M | — | M1 |
| F-39 | ĐẠT\* | | S | — | M2 |
| F-40 | LỖI | D-2 | S | — | M1 |
| F-41 | KHÔNG KIỂM ĐƯỢC | test với server giả (respx) xanh | M | máy chủ Hibiscus thử v0.1.1 cho QC (container riêng) | M2 |
| F-42 | KHÔNG KIỂM ĐƯỢC | như F-41 | M | như F-41 | M2 |
| F-43 | KHÔNG KIỂM ĐƯỢC | | S | như F-41 | M2 |
| F-44 | KHÔNG KIỂM ĐƯỢC | | S | như F-41 | M2 |
| F-45 | LỖI | D-16 (Low); kiểm đường dẫn đạt | S | — | M1 |
| F-46 | ĐẠT\* | | S | — | M1 |
| F-47 | ĐẠT\* | | S | — | M1 |
| F-48 | ĐẠT\* | chưa chạy tay vòng 1; chạy trên tay thật là UAT | M | model ACT nhỏ chuẩn cho QC (đã có `make_dummy_act`) | M1 |
| F-49 | ĐẠT\* | | S | — | M2 |
| F-50 | ĐẠT\* | | S | — | M2 |
| F-51 | ĐẠT\* | | S | — | M2 |
| F-52 | ĐẠT\* | | S | — | M2 |
| F-53 | LỖI | D-12 ("Hiệu chuẩn đã đổi…" trong gợi ý quỹ đạo) | S | — | M2 |
| F-54 | ĐẠT\* | | S | — | M2 |
| F-55 | ĐẠT\* | chưa chạy tay | M | webcam USB | M2 |
| F-56 | ĐẠT\* | REG-9 bước 1 đạt | M | — | M2 |
| F-57 | ĐẠT\* | | S | — | M2 |
| F-58 | ĐẠT\* | | M | — | M2 |
| F-59 | ĐẠT\* | | M | broker MQTT thử cho QC | M3 |
| F-60 | ĐẠT\* | | S | F-48 | M3 |
| F-61 | ĐẠT\* | | S | — | M2 |
| F-62 | ĐẠT\* | | S | — | M2 |
| F-63 | LỖI | D-15, K-11 | M | **đường găng**: phải xong trước khi xin báo cáo của khách (REG-13) | M0 |
| F-64 | ĐẠT\* | | S | — | M1 |
| F-65 | ĐẠT\* | | S | — | M3 |
| F-66 | ĐẠT\* | lý do 422 là tiếng Anh (gộp trong D-5) | S | — | M1 |
| F-67 | LỖI | D-12, K-3, K-4 | M | Q-8 | M1 |
| F-68 | LỖI | D-13, D-14; axe / bàn phím chưa chạy | L | FL-7 (tự động hoá ma trận ảnh + axe) | M1 |
| F-69 | KHÔNG KIỂM ĐƯỢC | cần Windows; K-8 | M | Q-4; F-1 | M1 |
| F-70 | KHÔNG KIỂM ĐƯỢC | không chạy Docker ở vòng này | M | máy Linux riêng cho QC Docker | M3 |
| F-71 | ĐẠT\* | `token`, `robots.yaml` 0600; dữ liệu demo tách riêng | S | — | M1 |

**Đếm:** ĐẠT\* 37 · LỖI 18 · KHÔNG KIỂM ĐƯỢC 16 (tổng 71). Effort: 48 × S, 21 × M, 2 × L = 76 ngày công.

---

## 4. Danh sách lỗi (D-n)

Mức độ theo `requirements.md`: Critical → High → Medium → Low. Không có lỗi Critical. Theo quy tắc zero-defect,
**mọi** lỗi dưới đây chặn tính năng của nó cho tới khi sửa (hoặc khách miễn bằng văn bản theo mã).

**D-1 · High · F-17 (NFR-18, AT-2) · Test e2e của repo đang đỏ.**
Bước: `pytest -m e2e tests/e2e` (UI build từ mã hiện tại). Kỳ vọng: xanh như job `e2e` của CI. Thực tế: chờ thẻ
`tab "Follower"` ở trang Hiệu chỉnh 30 s rồi FAIL; trang đã đổi sang luồng có hướng dẫn từ 0.2.7 nhưng test chưa
cập nhật. Hệ quả: CI không xanh trên commit phát hành, và luồng chính (kết nối → hiệu chỉnh → teleop → dừng nhiệt →
ghi → nhập model) không có test trình duyệt nào đang chạy được.

**D-2 · Medium · F-38, F-40 · Trang Ghi dữ liệu gây lỗi 500 trong lúc lưu tập.**
Bước: `--mock`, ghi dataset mới 2 tập × 4 s. Kỳ vọng: không có lỗi 5xx. Thực tế: trang Ghi đọc
`GET /datasets/<tên>` khi tệp parquet của tập đang ghi mới có 4 byte → `500 internal_error` (`ArrowInvalid`), log có
traceback. Cùng lỗi xảy ra khi mở trang chi tiết dataset trong lúc đang ghi.

**D-3 · Medium · F-4 (FR-4) · Cổng bị chương trình khác giữ: lỗi thô, link sai, không gợi ý.**
Bước: một chương trình khác nghe cổng P; chạy `hibiscus-station --port P`. Kỳ vọng: thông báo rõ + gợi ý `--port`.
Thực tế: in (và mở trình duyệt, nếu không có `--no-browser`) liên kết đăng nhập `http://127.0.0.1:P/auth?t=<token>`
**tới chương trình kia**, rồi `ERROR: [Errno 98] … address already in use` của uvicorn, thoát mã 3.

**D-4 · Low · F-4 · `hibiscus-station url` in liên kết chết.**
Bước: chạy Station rồi tắt (Ctrl+C / SIGTERM), hoặc lần chạy hỏng ở D-3; chạy `hibiscus-station url`. Kỳ vọng:
"Hibiscus Station is not running", mã ≠ 0. Thực tế: in liên kết cũ, mã 0 (tệp `token` / `station.pid` còn lại). Thêm:
`url` không có `--mock`, nên bản demo chạy không `--home` luôn báo "not running".

**D-5 · Medium · F-7, F-25, F-66 (FR-73, NFR-10; xác nhận K-4) · Chữ tiếng Anh / chữ máy dưới câu tiếng Việt.**
Ví dụ: teleop bị từ chối → "Đưa tay leader lại gần… (wrist_roll 32.7; lệch tối đa 30°)" + dòng monospace "Move the
leader arm closer to the follower pose first" (thiếu "°" sau 32.7); trang bước bị khoá hiện "no calibration file
<đường dẫn đầy đủ tới tệp>"; ngưỡng nhiệt sai → "temp_critical_c 69.0 must be <= Max_Temperature_Limit - 3 (67.0)".
Ảnh: [D-05](evidence/round1/D-05-leader-far-english-detail.png).

**D-6 · Medium · F-28 (AT-37) · Thả lỏng sau e-stop không nhắc đỡ tay.**
Bước: teleop → Space → Space trong 2 s. Kỳ vọng: mô-men tắt + banner "Hãy đỡ tay robot". Thực tế: mô-men tắt (kiểm
qua API: `follower_torque=false` ở 3/3 lần, khoảng cách 0,2 / 0,8 / 1,5 s) nhưng không có câu nhắc; câu
`banner.support_arm` chỉ hiện trong banner nguy hiểm (nhiệt / điện). Ảnh: [D-06](evidence/round1/D-06-relaxed-no-support-banner.png).

**D-7 · Medium · F-19 (AT-26) · Kiểm tra hai tay báo sai đơn vị và không nêu đúng nguyên nhân.**
Bước: hiệu chỉnh 2 tay (giả lập) → Kiểm tra. Kỳ vọng: mỗi trường hợp một lý do (sai tư thế / sai tệp / nhầm cổng).
Thực tế: tiêu đề "wrist_roll, gripper: lệch hơn 20°" trong khi kẹp đo bằng % (28,3 %); luôn liệt kê cả 3 nguyên nhân,
kể cả "Mọi khớp đều lệch: có thể đã nhầm cổng" khi chỉ 2/6 khớp lệch. Ảnh: [D-07](evidence/round1/D-07-check-gripper-unit-reasons.png).

**D-8 · Medium · F-5 (AT-7) · Chế độ demo: teleop / ghi bị từ chối ngẫu nhiên.**
Bước: `--mock` → hiệu chỉnh → Điều khiển tay → Bắt đầu. Kỳ vọng (người mới thử khi chưa có robot): chạy ngay. Thực tế:
"tay" leader giả lập quét liên tục nên lần bấm đầu bị `leader_far` (1/2 lần trong vòng này), "Kiểm tra" hai tay luôn
báo lệch; test e2e của repo phải dùng `POST /mock/inject {"hand":"follow"}` để vượt qua.

**D-9 · High · F-24 (NFR-1, NFR-2, AT-31; cùng triệu chứng REG-5) · Follower trễ / bị cắt khi adapter có latency 8 ms.**
Bước: `tests/teleop_bench.py --usb-in-ms 8` (giả lập 1 Mbaud, servo ~300°/s). Kỳ vọng: không chậm hơn LeLab quá 10 ms,
không cảnh báo "không theo kịp". Thực tế (cử động nhanh): Station 86 Hz, **84,6 % nhịp bị giới hạn 30° cắt**, trễ bám
83 ms (LeLab 68 ms, 0 % cắt), sai lệch đỉnh 30,2°; cảnh báo F-26 sẽ bật. Với 1 ms: đạt (4,6 ms p50, 228 Hz, 0 % cắt).
Adapter CH34x / FTDI trên Windows của khách có thể không ở 1 ms (FTDI mặc định 16 ms) → cần số đo của khách (FL-2).

**D-10 · Low · F-22, F-24 · Số và nhãn gây hiểu nhầm trên màn hình chuyển động.**
"FPS – / 30" khi ô FPS đang chọn 250 (nhanh nhất); nhãn "Bước 1292" là bộ đếm nhịp (trùng chữ "Bước" của thanh bước);
"tick khung hình 128", "tick trạng thái 128" lẫn thuật ngữ.

**D-11 · Low · F-24 · Bảng Khớp không có đơn vị.** Trước hiệu chỉnh hiện bước encoder thô ("2078.0"), sau hiệu chỉnh
hiện độ / % — cùng cột, không đơn vị.

**D-12 · Low · F-53, F-67 (NFR-10; xác nhận K-3) · Thuật ngữ lẫn.** 6 chuỗi "Hiệu chuẩn" (`robot.cal_follower`,
`robot.cal_leader`, `robot.cal_new`, `programs.traj.needs_check_hint`, `programs.issues.*_needs_check`); "Hãy reset nút
dừng khẩn cấp" bên cạnh nút "Đã an toàn, đặt lại"; hướng dẫn USB suspend ghi tên menu Windows bằng tiếng Anh.

**D-13 · Low · F-28, F-68 · Nút DỪNG nổi che chú thích Robot 3D** (dòng giấy phép mô hình) ở 1280 px khi đang ghi.

**D-14 · Low · F-68 (AT-82) · Chữ bị cắt ở 390 px:** chip robot "Chưa kế…". Ảnh: [D-14](evidence/round1/D-14-390-dark-locked-teleop.png).

**D-15 · Low · F-63 (AT-77) · `doctor` báo sai / thiếu.** Station đã tắt nhưng `station.pid` còn → "Running Station: pid
N: ConnectError: [Errno 111] Connection refused" (nên là "không chạy"); cổng bị chương trình khác giữ chỉ ghi "skipped, in
use by pid …" mà không vào **LIKELY PROBLEMS** (mục này chỉ xuất hiện khi có cảnh báo); chưa đọc `Present_Current` /
`Present_Load` (K-11). Phần tốt: 0 lệnh ghi xuống động cơ, zip không có token cục bộ hay `hbp_`.

**D-16 · Low · F-45 (FR-73) · Yêu cầu sai định dạng → 500.** `POST /models/import` với body không phải JSON →
`500 internal_error` (`JSONDecodeError`) và kết nối keep-alive bị reset; phải là 4xx có `code`. (Chỉ qua API.)

**D-17 · Low · F-17 (REG-4) · Mã chết của `wrist_roll` "toàn vòng".** Chuỗi `calibrate.full_turn` = "xoay tròn, không
cần ghi" và nhánh `FULL_TURN_MOTORS` (rỗng) còn trong sản phẩm; không hiện ra hôm nay nhưng là chỗ REG-4 có thể quay lại.

**D-18 · Low · F-3, F-69 (FR-76; xác nhận K-1, K-6) · Phiên bản không thống nhất trong tài liệu.** README / README.vi
bảng Docker ghi `0.2.1-cpu…`, `hibiscus-station-ctl update 0.2.1-cpu`; CHANGELOG liên kết so sánh dừng ở 0.2.2.

Tổng: **18 lỗi: 2 High (D-1, D-9) · 6 Medium (D-2, D-3, D-5, D-6, D-7, D-8) · 10 Low (D-4, D-10 – D-18).** REG-13
(BA ghi, đang mở) không tính lại ở đây.

K-n của BA mà vòng này **xác nhận bằng chạy thử**: K-1, K-3, K-4, K-6, K-11. K-2, K-5, K-7, K-8, K-10 chưa kiểm lại (tài
liệu), giữ nguyên như BA ghi.

---

## 5. Mốc đề xuất

Nguyên tắc: sửa theo thứ tự đường găng và chuỗi phụ thuộc (một lỗi ở F-17 / F-19 / F-24 kéo theo ghi dữ liệu, chạy
model, chương trình). Mỗi mốc kết thúc bằng QC trên đúng wheel của mốc.

| Mốc | Nội dung | Effort dev (ước, ngày công) | Kết thúc khi |
|---|---|---|---|
| **M0 · Nền kiểm** (tuần 1) | D-1 (e2e xanh); CI xanh trên Linux / Windows / macOS cho đúng commit; biến lối đi Playwright tiếng Việt của vòng này thành test tự động (ma trận màn hình × sáng / tối × 1280 / 390 + kiểm cuộn ngang + axe); `doctor` đọc dòng / tải (K-11) + D-15; chạy thử quy trình phát hành (wheel lên Release nháp, cài bằng lệnh README) | 10 (4 tính năng F-17, F-63 + 6 nền kiểm) | khách nhận được lệnh `doctor` để gửi báo cáo REG-13 (song song với M1) |
| **M1 · Must** | 44 tính năng Must: D-2 … D-14, D-16 … D-18, K-2 … K-5, K-8 (tài liệu / lệnh cập nhật theo Q-4), D-9 (sau khi có số đo adapter của khách), REG-13 / Q-5 | 48 (45 tính năng) | QC nội bộ PASS mọi AT [Vendor] của Must → **UAT-1 của khách** (Windows + 2 tay) |
| **M2 · Should** | máy chủ Hibiscus (F-41 – F-44, cần máy chủ thử cho QC), Chương trình (F-52 – F-58, F-61, F-62), Phiên, Bộ dữ liệu nâng cao, phát lại | 17 (19 tính năng) | QC PASS → UAT-2 (cùng buổi với UAT-1 nếu kịp) |
| **M3 · Could** | Docker / Pi 5 / Jetson (F-3, F-70), LAN (F-6 phần LAN), tín hiệu ngoài (F-59), model trong chương trình (F-60), `health` (F-65) | 7 (5 tính năng) | đạt thì vào v1.0; không đạt thì ghi "chưa nghiệm thu", không chặn (theo Q-1 / Q-3 đề xuất của BA) |

**Tổng effort dev ≈ 82 ngày công** (48 S + 21 M + 2 L = 76, cộng 6 cho nền kiểm M0), chưa tính QC (ước thêm ~30 %) và
thời gian chờ UAT của khách. Khoảng 1/3 là sửa lỗi, 2/3 là tự động hoá AT để chứng minh zero-defect trên mỗi bản. Với 3
dev song song (backend / frontend / phần cứng + QC tự động) ≈ 6–7 tuần lịch. Đường găng: báo cáo `doctor` của khách (REG-13, F-31 / F-33) và số đo adapter (D-9, F-24).

Phát hành v1.0 = M0 + M1 + M2 đạt (M3 nếu đạt). Một Must FAIL chặn cả bản (quy tắc), nên M1 ưu tiên trước M2.

---

## 6. Cách kiểm (test approach)

**Tự động hoá (vendor, chạy trên mỗi bản ứng viên trong CI):**
* Hiện có, giữ: `pytest` 515 test (mock + giả lập pty STS3215 với thời gian thật), `vitest` 173 test, ruff, mypy ×3
  nền tảng, eslint / prettier / tsc / kiểm hợp đồng API, kiểm CSP, smoke cài wheel trên Linux / Windows / macOS.
* Sửa / thêm ở M0: e2e Playwright xanh lại; e2e **tiếng Việt** đi hết luồng người mới (Robot → Hiệu chỉnh → Camera →
  Teleop → e-stop → thả lỏng → đặt lại → Ghi → Bộ dữ liệu → Chạy model → Chương trình); ma trận ảnh mọi trang × trạng
  thái × sáng / tối × 1280 / 390 với kiểm cuộn ngang, chữ bị cắt, chữ thô và **axe** (AT-82); đi bằng bàn phím (AT-83);
  e2e chạy trên `windows-latest` (không có tay) để phủ trang trắng / MIME / mã hoá (REG-17, REG-18).
* Kiểm chuỗi: khoá `vi` = `en`, cấm "Hiệu chuẩn", không có `detail` tiếng Anh hiển thị ở chế độ `vi` (AT-91).
* Hiệu năng: `teleop_bench.py` thành test `slow` có ngưỡng (1 ms và 8 ms) — NFR-1 / NFR-2 / REG-5; e-stop (đếm lệnh
  ghi sau nhịp) — NFR-3; phiên dài 30 phút (AT-90) chạy hằng đêm.
* Mỗi lỗi D-n đóng bằng một test fail-trước-pass-sau, như quy tắc.

**Vendor chạy tay (cần môi trường riêng):** máy chủ Hibiscus thử v0.1.1 trong container riêng (F-41 – F-44); webcam
USB và adapter CH340 rẻ cho F-9 – F-11, F-21, F-23 (phần không cần tay); mạng cô lập cho chế độ LAN (AT-9); Docker trên
máy Linux riêng (F-3, F-70); Pi 5 / Jetson nếu có máy (nếu không: "chưa nghiệm thu").

**UAT của khách (Windows 10/11 + SO-101 leader + follower thật):** chia ba buổi để giảm vòng lặp:
* **UAT-0** (ngay sau M0, ~15 phút): cài bản M0, chạy `hibiscus-station doctor --verbose`, gửi zip → đóng REG-13,
  biết độ trễ đọc của adapter (D-9). Không cần thử tính năng.
* **UAT-1** (sau M1): AT-1, AT-5, AT-12 – AT-18, AT-20 – AT-23, AT-26 – AT-31, AT-33, AT-35 – AT-38, AT-40, AT-42,
  AT-44, AT-45, AT-48, AT-59, AT-60, AT-77, AT-78, AT-84, AT-87 – AT-89, AT-92 (danh sách BA, phần Must).
* **UAT-2** (sau M2): AT-52 (nếu có tài khoản), AT-65, AT-66, AT-69, AT-70, AT-72, AT-75, AT-76.
Video: điện thoại quay chậm (slow-motion 120–240 fps) là đủ cho AT-31 / AT-36 / AT-88 (FL-3).

---

## 7. Mục "oái oăm" (flag)

Cùng định dạng với SA: mã · vấn đề · đề xuất thay thế vẫn giữ mục tiêu của khách.

| Flag | Mục | Vấn đề | Đề xuất |
|---|---|---|---|
| FL-1 | FR-7, AT-10 ("lý do chính xác của Station") ↔ FR-73, NFR-10 | Yêu cầu hiện lý do thô của Station mâu thuẫn với "không chữ máy / không tiếng Anh"; lý do thô còn chứa đường dẫn đầy đủ trên máy | Người dùng chỉ thấy câu dịch theo `code`; lý do thô nằm trong mục "Chi tiết kỹ thuật" thu gọn (cho kỹ sư) và trong log / `doctor`. Sửa AT-10 tương ứng |
| FL-2 | NFR-1, NFR-2, AT-31, AT-89 | "≥ 100 Hz" chỉ đúng với latency timer 1 ms; Windows FTDI mặc định 16 ms, người mới không chỉnh được; "độ trễ" chưa định nghĩa (lệnh hay bám) | NFR-1 đo hai số trên **cùng PC với LeLab**: độ trễ lệnh p50 / p95 và trễ bám (tracking lag), tiêu chí chính "≤ LeLab + 10 ms"; NFR-2 nêu theo lớp adapter (1 ms: ≥ 100 Hz; 8–16 ms: ≥ LeLab); lấy số đo adapter của khách ở UAT-0 |
| FL-3 | AT-31, AT-36, AT-88 "video 240 fps" | Khách có thể không có máy quay 240 fps | Cho phép quay chậm bằng điện thoại (120 / 240 fps) + số đo trong log / màn hình là bằng chứng chính |
| FL-4 | NFR-13, AT-40 (nhiệt ±2 °C bằng nhiệt kế) | Nhiệt vỏ servo trễ và thấp hơn cảm biến trong vài °C khi đang tải → không đo được như viết | So ở trạng thái nguội (để yên 30 phút, so với nhiệt độ phòng ±2 °C) và kiểm xu hướng khi tải (tăng đơn điệu, không nhảy); điện áp ±0,2 V giữ nguyên |
| FL-5 | F-63, REG-13, BRD "không lệnh nào ngoài cài đặt" | Người mới phải gõ `hibiscus-station doctor`; bản 0.2.8 lại chưa đọc dòng / tải nên một lần chạy không đủ | v1.0: giữ lệnh `doctor` (chép-dán từ hướng dẫn tiếng Việt, coi như lệnh hỗ trợ cùng loại lệnh cài); sửa K-11 ở M0 trước khi xin báo cáo (UAT-0). Nút "Tạo báo cáo chẩn đoán" trong Cài đặt = CR cho bản sau |
| FL-6 | ~40 AT chỉ khách chứng minh được + zero-defect | Mỗi lỗi khách tìm ra = thêm một vòng sửa → QC → UAT; dễ trễ | Lịch UAT 3 buổi (§6) do khách xác nhận trước; QC nội bộ thêm Windows CI có trình duyệt; khách chốt Q-1 – Q-3 ở vòng này để lỗi ở Should / Could không chặn bản |
| FL-7 | AT-82, NFR-11 ("chụp mọi trang ở mọi trạng thái", "axe 0 lỗi") | Khoảng 15 trang × ~5 trạng thái × 2 chủ đề × 2 bề rộng ≈ 300 ảnh: không làm tay được mỗi bản | Tự động bằng Playwright + axe trong CI (M0); QC xem tay một mẫu cố định (trang chính × trạng thái lỗi / trống) |
| FL-8 | AT-9 (LAN) | Cần bind ngoài loopback; môi trường QC chỉ cho 127.0.0.1 | Chạy trong mạng cô lập (network namespace / VM) hoặc chấp nhận test đơn vị + tự kiểm khi khách bật LAN (Could) |
| FL-9 | FEATURES: F-24 phụ thuộc F-19 | Teleop chạy được không cần bước Kiểm tra ("Vẫn thử teleop"); phụ thuộc này làm một lỗi Low ở F-19 loại cả teleop, ghi, chạy model, chương trình | F-24 chỉ phụ thuộc F-17; F-19 là bước khuyến nghị |
| FL-10 | AT-7, F-5 ("mọi bước chạy" ở demo) | Tay leader giả lập quét liên tục nên bước Kiểm tra / bắt đầu teleop không ổn định (D-8) | Ghi rõ hành vi demo mong muốn: ở `--mock`, tay leader giả lập đứng theo follower khi bắt đầu phiên và khi Kiểm tra (chỉ trong demo) |
| FL-11 | AT-77 ("bắt đầu bằng LIKELY PROBLEMS") | Mục này chỉ có khi có vấn đề | "Mở đầu bằng LIKELY PROBLEMS **khi có**; khi không có: dòng 'No likely problems found'" |
| FL-12 | F-1, AT-1, AT-84 | AT cài đặt cần wheel trên GitHub Releases; quy trình phát hành chưa chạy thử trong vòng này (không push / tag) | Thêm vào M0 một lần chạy thử phát hành nháp (pre-release) để AT-1 có tệp đúng cho khách |

---

## 8. Cam kết của nhóm dev

Với phạm vi v1.0 = 71 tính năng hiện có và các đề xuất ở §7 được BA / khách chốt, nhóm dev cam kết giao **mọi tính năng
đã duyệt** theo mốc ở §5. Không bắt đầu sửa mã khi chưa có phê duyệt của khách; mỗi D-n khi sửa có test tự động
fail-trước-pass-sau và QC chạy lại AT của tính năng cùng danh sách hồi quy.
