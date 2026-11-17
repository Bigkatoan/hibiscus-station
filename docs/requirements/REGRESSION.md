# Hibiscus Station: danh sách hồi quy v1.0 (2026-11-17) · trạng thái: **đã duyệt** (khách hàng duyệt ngày 2026-11-17, đường cơ sở)

Mỗi mục REG-n là một lỗi hiện trường đã xảy ra (người dùng Windows của khách hàng với tay SO-101
thật, bản 0.2.1 – 0.2.8) hoặc một lỗi đã sửa ghi trong `CHANGELOG.md` của sản phẩm. Theo chuẩn
zero-defect, **mọi REG phải đạt trên bản phát hành** (QC chạy lại ở mỗi bản ứng viên); một REG
không đạt là một lỗi mở và chặn phát hành của tính năng liên quan.

* **Bản sửa** = bản đã có bản sửa (theo CHANGELOG). **Test tự động** = test hiện có trong `tests/`
  hoặc `web/src` chứng minh phần có thể kiểm không cần phần cứng.
* **Nền tảng**: `[Vendor]` nhà cung cấp chứng minh được (Linux, giả lập STS3215, CI Windows không có
  tay); `[UAT-KH]` chỉ UAT của khách hàng trên Windows + SO-101 thật chứng minh được.
* Một REG chỉ **đóng** khi: test tự động đạt **và** bước tái hiện trên nền tảng gốc (cột cuối) đạt.
* v0.2: test pty (REG-4, REG-5, REG-7, REG-8, REG-14) hôm nay bị bỏ qua trên CI Windows; chúng nằm trong
  danh sách bỏ qua được công bố (NFR-18) và được UAT-1 phủ thay cho tới khi SP-2 chạy được trên cổng COM ảo.
  Lỗi D-9 (adapter chậm) có cùng triệu chứng với REG-5: REG-5 chỉ đóng khi D-9 đóng.

| REG | Báo cáo hiện trường (lời của khách / log) | Bản lỗi → bản sửa | Tính năng | AT |
|---|---|---|---|---|
| REG-1 | Station không khởi động trên Windows: `ModuleNotFoundError: No module named 'fcntl'` | 0.2.0 → 0.2.1 | F-1, F-4 | AT-1, AT-5 |
| REG-2 | Calibrate, teleop, ghi, chạy không làm tay thật chuyển động, LeLab thì được; log `demo_follower MockFollower read state` (hồ sơ demo của lần `--mock` trước đang hoạt động) | 0.2.1 → 0.2.2 | F-5, F-15, F-63 | AT-7, AT-21, AT-77 |
| REG-3 | Servo báo 0 °C (nhiệt độ hoặc `Max_Temperature_Limit`) → mọi ngưỡng nhiệt hạ xuống −3 °C → cả hai tay bị dừng "nguy hiểm" | 0.2.2 → 0.2.3 | F-32, F-33 | AT-42, AT-43 |
| REG-4 | Trang Hiệu chỉnh ghi `wrist_roll` "xoay tròn, không cần ghi"; khách muốn chuẩn LeLab: ghi biên độ cho mọi khớp | 0.2.3 → 0.2.4 (máy chủ), 0.2.5 (giao diện) | F-17 | AT-23, AT-24 |
| REG-5 | Teleop trễ: follower chạy sau leader, LeLab thì không (vòng 30 Hz, giới hạn tương đối 5° mỗi nhịp cắt mọi nhịp: trễ 127 ms, 186 ms khi nhanh) | 0.2.4 → 0.2.6 | F-24, F-26 | AT-31, AT-34 |
| REG-6 | Leader và follower bị gán nhầm: "tìm bằng cách cử động" gán theo tay nào cử động trước, không theo ô đang tìm | 0.2.5 → 0.2.6 | F-10, F-11 | AT-13, AT-15 |
| REG-7 | "Hiệu chỉnh quá phức tạp; hiệu chỉnh xong teleop không chạy" | 0.2.5 → 0.2.7 | F-16, F-17, F-19, F-24 | AT-22, AT-23, AT-26, AT-31 |
| REG-8 | "Access is denied" trên COM8, rồi 6 lần thử lại và `bus_lost` trên Windows | 0.2.5 → 0.2.7 | F-13 | AT-18, AT-19 |
| REG-9 | Không tạo được chương trình mới: (a) tên không có chữ Latin / số không nhận được mã (0.2.7); (b) nút "Chương trình mới" như không làm gì khi form đã mở sẵn (chưa có chương trình), hoặc khi danh sách đang tải / lỗi (0.2.8) | 0.2.5 → 0.2.7, 0.2.7 → 0.2.8 | F-56, F-58 | AT-70 |
| REG-10 | E-stop khi "Chạy trên robot" → không có đường phục hồi; lần chạy sau "chạy tiếp lượt trước" (mục tiêu của phiên bị dừng còn sót lại, các khớp không được lệnh bị kéo về đích cũ) | 0.2.7 → 0.2.8 | F-28, F-35, F-53, F-58 | AT-37, AT-45, AT-72 |
| REG-11 | Telemetry tay leader vô lý: "gripper draws a high current (6.422 A)", "Motor telemetry reads are failing", "ok stale" trên mọi động cơ leader, 0 °C; báo động | 0.2.7 → 0.2.8 | F-31, F-33 | AT-41, AT-43 |
| REG-12 | Bước bị khoá trong thanh bước vẫn mở và dùng được | 0.2.7 → 0.2.8 | F-7 | AT-10 |
| REG-13 | **CHƯA GIẢI QUYẾT.** Cả hai tay của khách đọc 0 °C ở mọi động cơ và dòng khoảng 1000 (thô, ≈ 6,5 A theo đơn vị 6,5 mA/bước chưa xác nhận). Station đã bỏ qua các giá trị này (0.2.3, 0.2.8) nhưng chưa biết nguyên nhân (firmware? thanh ghi khác? bảng đơn vị sai? bộ chuyển?) | mở | F-31, F-33, F-63 | AT-40, AT-43, AT-77 |
| REG-14 | Một gói tin hỏng làm hỏng cả lần kết nối hoặc hiệu chỉnh (lerobot ghi cấu hình không thử lại); lỗi bus hiện `500 internal_error: ConnectionError` | 0.2.1 → 0.2.2 | F-12 | AT-16 |
| REG-15 | Teleop đòi mọi camera cấu hình phải đang phát (LeLab teleop không cần camera) | 0.2.1 → 0.2.2 | F-23, F-24 | AT-32 |
| REG-16 | Kẹp SO-101 bóp vật làm bật cờ quá tải → dừng an toàn giả | 0.2.1 → 0.2.2 | F-34 | AT-44 |
| REG-17 | Trang trắng trên Windows (registry ánh xạ `.js` thành `text/plain`) | 0.2.0 → 0.2.1 | F-1, F-4 | AT-2, AT-5 |
| REG-18 | Lỗi khi ghi / in tiếng Việt trên Windows (code page thay vì UTF-8) | 0.2.0 → 0.2.1 | F-64, F-71 | AT-78 |
| REG-19 | Vòng điều khiển 30 Hz không giữ nhịp trên Windows (đồng hồ hệ thống 15,6 ms) | 0.2.0 → 0.2.1 | F-24, F-38 | AT-89 |
| REG-20 | Camera chọn "0" trên giao diện mở như tệp tên `0`; dò camera mở lại camera đang dùng (Windows từ chối) | 0.2.0 → 0.2.1 | F-21 | AT-28 |

## Chi tiết từng mục (tái hiện → kỳ vọng)

### REG-1 — `fcntl` trên Windows
* **Tái hiện:** PC Windows 10/11 x64 sạch → cài theo README (uv + wheel) → `hibiscus-station`.
* **Kỳ vọng:** Station khởi động, trình duyệt mở trang Chào mừng; không có `ModuleNotFoundError`;
  chạy lần hai in liên kết của bản đang chạy (khoá một phiên bản hoạt động trên Windows).
* **Test tự động:** `tests/test_platform.py` (khoá Windows, `msvcrt`), CI `windows-latest` (pytest, wheel,
  `uv tool install` + `--mock`). **Nền tảng:** [Vendor] CI Windows; [UAT-KH] PC của khách.

### REG-2 — Hồ sơ demo thay cho tay thật
* **Tái hiện:** chạy `hibiscus-station --mock`, tạo / kết nối hồ sơ demo, thoát; cắm hai tay thật; chạy
  `hibiscus-station` (không `--mock`).
* **Kỳ vọng:** hồ sơ demo không hoạt động, mang nhãn DEMO, nút Kết nối tắt; banner "Đang dùng tay giả
  lập — tay thật (COMx) không chuyển động" + "Tạo hồ sơ cho tay thật" điền sẵn cổng; không có chip TAY
  GIẢ LẬP; dữ liệu demo nằm ở `~/.hibiscus/station-demo`; `doctor` báo `MOCK PROFILE ACTIVE` khi tình
  huống này xảy ra; dòng khởi động trong log ghi "real hardware".
* **Test tự động:** `tests/test_field_reports.py` (5 test). **Nền tảng:** [Vendor] + [UAT-KH].

### REG-3 — 0 °C gây dừng nhiệt giả
* **Tái hiện:** tay (hoặc giả lập) báo `Present_Temperature = 0` và / hoặc `Max_Temperature_Limit = 0`;
  kết nối; teleop 5 phút.
* **Kỳ vọng:** không cảnh báo nhiệt, không dừng; ô nhiệt hiện "—" (không rõ) có giải thích; ngưỡng
  vẫn là 50 / 60 / 65 °C; khi không động cơ nào báo nhiệt thật → cảnh báo "Không đọc được thông số
  động cơ" (không phải quá nhiệt) — hành vi chạy theo QĐ-1 = A (AT-93).
* **Test tự động:** `tests/test_units.py`, `tests/test_field_028.py`. **Nền tảng:** [Vendor] giả lập;
  [UAT-KH] tay của khách (đang báo 0 °C).

### REG-4 — `wrist_roll` "xoay tròn, không cần ghi"
* **Tái hiện:** Hiệu chỉnh follower → bước Biên độ.
* **Kỳ vọng:** `wrist_roll` hiện `min | vị trí | max` như mọi khớp; được tick khi quay ≥ 100 bước; Lưu
  chỉ mở khi đủ 6 khớp; tệp lưu có dải `wrist_roll` đã ghi (không phải toàn encoder); không chuỗi
  "xoay tròn" nào xuất hiện. Tệp hiệu chỉnh cũ (wrist_roll toàn vòng) vẫn dùng được.
* **Test tự động:** `tests/test_calib_simple.py::test_save_needs_every_joint_moved`, test giao diện
  trang Hiệu chỉnh. **Nền tảng:** [Vendor] giả lập STS3215; [UAT-KH] tay thật.

### REG-5 — Teleop trễ
* **Tái hiện:** teleop, cử động leader nhanh (≈ 90 – 340°/s) qua lại 10 lần.
* **Kỳ vọng:** NFR-1a (giả lập: p50 ≤ 70 ms, ≤ tham chiếu LeLab + 10 ms ở adapter 1 ms **và** 8 ms), NFR-1b,
  NFR-1c (khách: "không chậm hơn LeLab"), NFR-2; không cảnh báo "không theo kịp" khi cử động bình thường;
  màn hình hiện "độ trễ ~X ms, Y Hz".
* **Test tự động:** `tests/test_teleop_latency.py`, `tests/test_teleop_lean.py`, `tests/teleop_bench.py`
  (giả lập có thời gian thật). **Nền tảng:** [Vendor] số đo giả lập; [UAT-KH] cảm nhận + số đo trên
  màn hình, so với LeLab trên cùng PC.

### REG-6 — Gán nhầm leader / follower
* **Tái hiện:** hồ sơ mới; bấm "Tìm tay follower (cử động)" rồi cử động **tay leader** trước, sau đó tay
  follower; lặp lại với "Tìm tay leader".
* **Kỳ vọng:** cổng tìm được chỉ vào ô đã bấm; lần tìm thứ hai không bao giờ đề xuất cổng đã gán cho
  tay kia; gợi ý điện áp hiện dưới mỗi cổng và cảnh báo khi có vẻ nhầm; "Đổi chỗ" đổi đúng hai cổng, mã
  hiệu chỉnh ở lại theo vai trò.
* **Test tự động:** `tests/test_ports_roles.py` (5 test). **Nền tảng:** [Vendor] giả lập; [UAT-KH] tay
  thật (điện áp thật 5 V / 7,4 V / 12 V).

### REG-7 — Hiệu chỉnh phức tạp, teleop hỏng sau hiệu chỉnh
* **Tái hiện:** (a) tay đã có tệp LeLab: mở Hiệu chỉnh; (b) tay chưa hiệu chỉnh: hiệu chỉnh follower →
  leader → Kiểm tra → Thử teleop; (c) cố tình dùng tệp sai cho leader → Kiểm tra.
* **Kỳ vọng:** (a) "Tay này đang dùng hiệu chỉnh từ LeLab" + Dùng, không cần hiệu chỉnh lại; (b) cả
  luồng ≤ 3 phút, teleop chạy ngay sau Kiểm tra; (c) Kiểm tra báo lệch > 20° và lý do, trước khi teleop.
* **Test tự động:** `tests/test_calib_simple.py` (5 test). **Nền tảng:** [Vendor] giả lập; [UAT-KH].

### REG-8 — "Access is denied" trên COM8
* **Tái hiện:** đang teleop, rút cáp USB follower (hoặc để Windows cho cổng ngủ); cắm lại, có thể sang
  cổng COM khác.
* **Kỳ vọng:** trong ≤ 1 s trạng thái `error` lý do `device_lost` (không 6 lần thử lại, không chuỗi
  lỗi tắt mô-men), trang giải thích + danh sách kiểm tra; "Kết nối lại" chờ cổng, nhận số COM mới,
  cập nhật hồ sơ, kết nối lại và ghi hiệu chỉnh; teleop chạy lại được không cần khởi động lại Station.
  `Access is denied` lúc **mở** cổng (LeLab đang giữ) là `port_busy`, không phải `device_lost` (AT-17). Hai
  tay CH340 (không serial): Station hỏi tay nào là tay nào sau khi cắm lại (đúng thiết kế).
* **Test tự động:** `tests/test_device_lost.py` (8 test, gồm pty đóng giữa teleop và trở lại tên mới).
  **Nền tảng:** [Vendor] pty Linux; [UAT-KH] Windows COM thật.

### REG-9 — Không tạo được chương trình mới
* **Tái hiện:** hồ sơ mới chưa có chương trình → Chương trình → thẻ Chương trình → bấm "Chương trình
  mới" (một lần, hai lần); đặt tên toàn chữ có dấu / ký tự không Latin (ví dụ "Gắp đỏ", "抓取"); lặp lại
  khi danh sách đang tải và khi máy chủ trả lỗi; lặp lại khi robot đang e-stop.
* **Kỳ vọng:** mỗi lần bấm, form mở và con trỏ ở ô tên; lưu được với mã `program_<hash>` ổn định; form
  nói lưu cho hồ sơ nào; danh sách lỗi hiện lỗi + "Thử lại"; danh sách trả lời cả khi robot bận / e-stop.
* **Test tự động:** `web/src/station/field028.screens.test.tsx`, `tests/test_programs_api.py`,
  `tests/test_field_028.py::test_programs_list_never_waits_for_the_hardware_owner`. **Nền tảng:**
  [Vendor] + [UAT-KH].

### REG-10 — E-stop khi "Chạy trên robot"
* **Tái hiện:** chương trình (hoặc quỹ đạo) có chuyển động nhiều khớp và chuyển động chỉ kẹp; chạy trên
  robot; bấm Space giữa chừng; Thả lỏng (tuỳ chọn); Đặt lại; chạy lại.
* **Kỳ vọng:** tay dừng trong một nhịp; lần chạy kết thúc `estopped`; sau Đặt lại có banner "đã dừng giữa
  chừng" + "Về tư thế nghỉ" (chậm, Space huỷ được); lần chạy sau đi về điểm đầu rồi chạy từ đầu,
  **không** khớp nào bị kéo về đích của lần trước; hiệu chỉnh không thay đổi (tệp và EEPROM).
* **Test tự động:** `tests/test_field_028.py` (e-stop / relax / rerun, hiệu chỉnh không đổi, rest pose).
  **Nền tảng:** [Vendor] giả lập; [UAT-KH] tay thật (quay video).

### REG-11 — Telemetry leader vô lý
* **Tái hiện:** kết nối, teleop 10 phút; giả lập: `Present_Current` thô 1000 có bit 15, tải 120 %,
  điện áp 0.
* **Kỳ vọng:** giá trị vô lý hiện "—"; không cảnh báo nào từ leader (dòng, tải, trạng thái, điện áp),
  nhiệt leader không quá "nóng", không dừng robot, không chặn phiên; "không phản hồi" chỉ khi một lần đọc
  thực sự không có trả lời; bảo vệ follower không đổi.
* **Test tự động:** `tests/test_field_028.py` (5 test telemetry). **Nền tảng:** [Vendor] + [UAT-KH].

### REG-12 — Bước bị khoá vẫn dùng được
* **Tái hiện:** chưa kết nối robot → bấm Hiệu chỉnh, Camera, Điều khiển tay, Ghi dữ liệu, Tải lên, Huấn
  luyện, Chạy model trên thanh bước; gõ thẳng địa chỉ `/teleop`; lặp lại ở bề rộng 390 px; lặp lại khi
  robot đang e-stop.
* **Kỳ vọng:** trang "Bước này đang bị khoá" với lý do bằng lời, lý do chính xác của Station, nút "Tới
  <bước>"; mọi nút trên trang tắt; trang Huấn luyện vẫn có form ghép nối.
* **Test tự động:** `web/src/station/field028.screens.test.tsx`, `screens.test.tsx`. **Nền tảng:**
  [Vendor].

### REG-13 — 0 °C và dòng ~1000 thô trên tay của khách (CHƯA GIẢI QUYẾT)
* **Đầu vào cần (UAT-0):** báo cáo `hibiscus-station doctor --verbose` **của bản M0** (đã đọc
  `Present_Current` / `Present_Load` và dump thô từng servo bằng `read` riêng lẻ, K-11, SP-1) từ PC của khách
  (hai tay cắm, Station và LeLab đã tắt), kèm ảnh chụp công cụ Feetech FD trên cùng servo (đối chứng độc lập
  với lerobot / rustypot).
* **Hạn:** nếu 1 tuần sau ngày hẹn UAT-0 vẫn chưa có dữ liệu: đóng với kết luận "servo không báo nhiệt (chưa
  rõ vì sao)" và áp hành vi QĐ-1 = A (BRD G-4).
* **Kỳ vọng để đóng:** (1) nguyên nhân được xác định và ghi lại (firmware / thanh ghi / đơn vị / phần
  cứng); (2) nếu là lỗi của Station: sửa, Station hiện đúng nhiệt độ và dòng của tay khách (NFR-13); nếu
  là đặc tính của servo: Station hiện "không rõ" (đã có) và hành vi chạy theo QĐ-1 = A (AT-93), kèm lời giải thích
  cho người dùng; (3) mục HIL "đơn vị dòng 6,5 mA/bước" và "bố cục bit Status" được xác nhận hoặc sửa.
* **Nền tảng:** [UAT-KH] (chỉ tay của khách tái hiện được).

### REG-14 … REG-20 (từ CHANGELOG)
| REG | Tái hiện | Kỳ vọng | Test tự động | Nền tảng |
|---|---|---|---|---|
| REG-14 | Giả lập STS3215 mất / hỏng 1–2 % gói; kết nối, hiệu chỉnh 10 lần | 10/10 thành công; lỗi bus thật hiện `bus_error` với id động cơ, thanh ghi, bước | `tests/test_real_stack.py::test_noisy_bus_still_connects_and_calibrates`, `::test_bus_failure_in_a_command_is_a_bus_error_not_internal` (POSIX) | [Vendor] |
| REG-15 | Hồ sơ có camera nhưng rút camera; bắt đầu teleop | Teleop chạy; ghi / chạy model thì từ chối `camera_unavailable` | `tests/test_owner.py::test_teleop_runs_without_cameras_record_needs_them` | [Vendor] |
| REG-16 | Kẹp bóp chặt một vật 5 s khi teleop | Cảnh báo, không dừng an toàn; quá dòng / điện áp thấp cần 2 lần đọc liên tiếp | `tests/test_units.py::test_gripper_overload_is_a_grasp_not_a_fault` | [Vendor] + [UAT-KH] |
| REG-17 | Windows với `.js` ánh xạ `text/plain` trong registry; mở Station | Giao diện tải đầy đủ | `tests/test_platform.py::test_web_mimetypes_are_pinned`, CI Windows | [Vendor] CI |
| REG-18 | Windows; tên dataset / nhiệm vụ / chương trình tiếng Việt; chạy với stdout chuyển hướng vào tệp | Không lỗi mã hoá; log UTF-8 | `tests/test_platform.py` (UTF-8) | [Vendor] CI + [UAT-KH] |
| REG-19 | Windows; ghi 1 tập 30 s ở 30 fps | p95 thời gian nhịp ≤ 36 ms, nhịp trễ < 1 % | `tests/test_platform.py::test_utf8_console_and_timer_do_not_fail` (chỉ khởi tạo timer) | [UAT-KH] |
| REG-20 | Windows; chọn camera "0"; dò camera khi đang phát | Mở đúng camera số 0; dò không mở lại camera đang dùng | `tests/test_platform.py` (camera index) | [Vendor] + [UAT-KH] |
