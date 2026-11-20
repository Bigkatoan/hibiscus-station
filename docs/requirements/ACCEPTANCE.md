# Hibiscus Station: tài liệu nghiệm thu v1.1 (2026-11-19) · trạng thái: **đã duyệt** (khách hàng duyệt ngày 2026-11-17, đường cơ sở; CR-1 duyệt ngày 2026-11-19)

BA viết; QC rà soát trước khi duyệt ("kiểm được như đã viết không?"); QC chạy sau khi xây. v0.2: mỗi AT
ghi rõ công cụ và lệnh để chạy đúng như viết (test tự động có tên, lệnh chèn lỗi `POST /api/v1/mock/inject`
chỉ với `--mock`, máy chủ thử); bỏ yêu cầu nhiệt kế, đồng hồ vạn năng và video 240 fps (thay bằng công cụ
Feetech FD và quan sát; video quay chậm điện thoại là tuỳ chọn); thêm AT-93 – AT-98; UAT của khách rút còn ba
buổi ngắn (cuối tài liệu). Mỗi AT kiểm
một tính năng F-n trong [FEATURES.md](FEATURES.md) hoặc một NFR trong [SRS.md](SRS.md). Danh sách hồi quy
[REGRESSION.md](REGRESSION.md) chạy cùng. Kết quả QC từng tính năng ghi ở
[FEATURES-APPROVED.md](FEATURES-APPROVED.md).

v1.0: khách hàng chọn QĐ-1 – QĐ-4 = A và duyệt bộ tài liệu (2026-11-17). AT-1, AT-4, AT-84, AT-93, AT-98 và Kế
hoạch UAT viết theo các quyết định đã chốt; mọi bước "phương án B" đã bỏ.

v1.1 (2026-11-19): CR-1 ("Có, thêm vào M1") thêm **AT-99** (F-72, xem video từng tập) và bước 16 của UAT-1.

## Môi trường

* **Bản kiểm:** đúng tệp người dùng cài: wheel `hibiscus_station-<v>-py3-none-any.whl` của bản ứng viên
  cài bằng **lệnh trong hướng dẫn của chính bản đó** (QĐ-3 = A: lệnh một dòng với bộ phụ thuộc cố định) trên
  máy / VM sạch; Docker image cùng phiên bản cho AT Docker. Bản ứng viên được phát hành nháp (pre-release)
  để AT-1 có đúng tệp (FL-12).
* **Nền tảng:**
  * **[Vendor]**: Linux x86_64 (Ubuntu 24.04) với `--mock`, giả lập STS3215 (`tests/sts_emulator.py`,
    pty, thời gian thật), camera giả lập / webcam; CI `windows-latest` và macOS (không có tay).
  * **[UAT-KH]**: chỉ UAT của khách hàng chứng minh được: PC Windows 10/11 x64 của khách + SO-101
    leader + follower thật + camera USB thật. Nhà cung cấp không có Windows và tay thật, nên các AT này là
    **NOT VERIFIED** ở QC nội bộ và chỉ đạt khi khách hàng chạy (hoặc xem video) và ghi kết quả.
  * Một AT có cả hai nhãn: QC chạy phần [Vendor] trước; khách hàng chạy lại trên nền tảng của mình.
  * **Nền tảng thuộc nghiệm thu (QĐ-2 = A):** Windows 10/11 x64 (Must, [UAT-KH]); Ubuntu 22.04 / 24.04 x86_64
    (Should, [Vendor]); Docker trên PC Linux x86_64 image `-cpu` (Could, [Vendor]). macOS, wheel Linux arm64, Docker
    `-cuda`, Raspberry Pi 5, Jetson Orin là **bản xem trước** (W-9): không có AT, không thuộc nghiệm thu; QC chỉ kiểm
    README / ghi chú phát hành / `install.sh` ghi đúng nhãn "bản xem trước" (AT-4).
* **Công cụ của vendor:** giả lập STS3215 `tests/sts_emulator.py` (pty, thời gian thật), `tests/teleop_bench.py`,
  `POST /api/v1/mock/inject` (chỉ `--mock`: nhiệt độ, dòng thô, "tay" leader giữ / theo follower, vật màu trên
  camera giả); webcam USB và một bộ chuyển CH340 / CH343 rẻ (không cần tay) cho F-9 – F-11, F-21, F-23; máy chủ
  Hibiscus thử v0.1.1 trong container riêng; broker MQTT thử (mosquitto) và máy nhận webhook thử; mạng cô lập
  (network namespace / VM) cho AT-9; VM Windows 11 sạch không git (SP-3); Playwright + axe.
* **Công cụ của khách:** PC Windows, hai tay SO-101, ≥ 1 camera USB, LeLab đang dùng, công cụ **Feetech FD**
  chính hãng, (khuyến nghị) công tắc ngắt nguồn trên dây nguồn follower, điện thoại để quay (tuỳ chọn).
* **Dữ liệu thử:** hồ sơ `desk_so101`; tệp hiệu chỉnh LeLab mẫu (`so_101_follower.json` /
  `so_101_leader.json`); model ACT nhỏ (gói zip) và một thư mục `pretrained_model`; máy chủ Hibiscus thử
  v0.1.1 với token có `datasets:write`, `models:read`, `runs:read` (cho F-41 – F-44).
* **Bằng chứng giữ lại:** ảnh chụp (đánh số theo AT), video khi ghi chú "video", `station.log`, thư mục
  phiên, zip `doctor` khi AT yêu cầu.
* **Kết quả:** PASS / FAIL / NOT VERIFIED (lý do) · người kiểm · ngày · phiên bản. Một AT FAIL = tính
  năng FAIL (quy tắc zero-defect).

Viết tắt: "Space" = phím cách; "≤ N s" đo bằng đồng hồ hoặc dấu thời gian log; "inject {…}" = `curl -X POST
-H 'X-Station: 1' -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' -d '{…}'
http://127.0.0.1:18210/api/v1/mock/inject` (token trong tệp `token` của thư mục dữ liệu demo).

---

## A. Cài đặt và khởi động

**AT-1 (F-1, REG-1) Cài đặt sạch trên Windows** · [UAT-KH] (+ [Vendor] VM Windows 11 sạch không có git, SP-3)
Tiền điều kiện: Windows 10/11 x64 chưa từng cài Station, chưa có uv, **không có git**; tay chưa cắm; mạng
≥ 20 Mbps.
1. Mở PowerShell (không cần admin), dán **một** lệnh cài trong hướng dẫn tiếng Việt của bản ứng viên (QĐ-3
   = A).
2. Khi lệnh xong, gõ `hibiscus-station --version`.
3. [Vendor] Trên VM, chạy `uv pip list --python "$(uv tool dir)\hibiscus-station\Scripts\python.exe"` và so với
   danh sách thư viện của bản phát hành.
Kỳ vọng: lệnh xong không lỗi, không đòi git hay quyền admin; in đúng phiên bản bản ứng viên; không cần gõ lệnh
nào khác; hướng dẫn tiếng Việt đủ để làm mà không cần hỏi; (3) bộ thư viện trùng 100 % với bản QC đã kiểm.
Bằng chứng: ảnh PowerShell; (Vendor) tệp so sánh.

**AT-2 (F-1, NFR-18, REG-17) CI trên Linux / Windows / macOS** · [Vendor]
1. Mở lần chạy CI của commit phát hành. 2. Mở danh sách test được phép bỏ qua theo nền tảng (trong repo,
NFR-18). 3. Trong log pytest của từng job, lọc các dòng `SKIPPED`.
Kỳ vọng: mọi job xanh: Linux (pytest, vitest, e2e Chromium + Firefox, build bộ tệp phát hành một lần: wheel
thuần Python `py3-none-any`, `install.ps1`, `SHA256SUMS`), `windows-latest` (pytest, cài **chính tệp wheel phát
hành đó** bằng `install.ps1` + `--mock` smoke, kiểm MIME `.js`, e2e Edge `--mock`), macOS (cài smoke cùng bộ
tệp); mỗi test `SKIPPED` có trong danh
sách với lý do và AT / UAT phủ thay; 0 test bỏ qua ngoài danh sách; e2e của repo xanh (D-1). Bằng chứng: liên
kết CI + danh sách bỏ qua.

**AT-3 (F-2) Cài đặt Linux** · [Vendor]
1. Ubuntu 24.04 sạch: cài uv, cài wheel theo README. 2. `hibiscus-station --mock`.
3. (Tuỳ chọn) cài unit systemd trong `deploy/systemd/`, khởi động lại máy.
Kỳ vọng: giao diện mở; với systemd, Station tự chạy và `hibiscus-station health` thoát 0.

**AT-4 (F-3) Docker** · [Vendor] (PC Linux x86_64, image `-cpu`; QĐ-2 = A)
1. `bash install.sh` trên PC Linux x86_64 sạch, đồng ý cài Docker. 2. `hibiscus-station-ctl status`, `url`, `ports`.
3. Khởi động lại máy chưa cắm tay, cắm tay sau. 4. Đọc README / README.vi, ghi chú phát hành và lời nhắc của
`install.sh` khi chọn `-cuda` / `-jetson` (không cần máy đó).
Kỳ vọng: image `-cpu`; `healthy` trong ≤ 3 phút sau khởi động lại; cắm tay sau vẫn kết nối được;
`ports` hiện `/dev/serial/by-id/…` và `/dev/hibiscus/arm-*`; (4) `-cuda`, Pi 5, Jetson (và macOS, wheel
arm64 trong README) ghi "bản xem trước, không thuộc nghiệm thu v1.0" kèm lỗi đã biết (W-9).

**AT-5 (F-4, REG-1, REG-17) Khởi động và đăng nhập** · [Vendor] + [UAT-KH]
1. Chạy `hibiscus-station`. 2. Quan sát trình duyệt. 3. Xem thanh địa chỉ và lịch sử.
Kỳ vọng: trình duyệt tự mở trang Chào mừng bằng tiếng Việt (trình duyệt tiếng Việt); không lỗi
`fcntl`; không trang trắng; địa chỉ không còn chứa token; log có dòng khởi động "real hardware".

**AT-6 (F-4) Một phiên bản, liên kết lại, cổng bận** · [Vendor]
1. Khi Station đang chạy, chạy `hibiscus-station` lần hai. 2. Chạy `hibiscus-station url`, mở liên kết trong
cửa sổ ẩn danh. 3. Tắt Station (Ctrl+C), chạy `hibiscus-station url`, xem mã thoát. 4. Giữ cổng bằng chương
trình khác: `python -m http.server 18210 --bind 127.0.0.1`; chạy `hibiscus-station`. 5. Chạy
`hibiscus-station --mock`, rồi ở cửa sổ khác `hibiscus-station url`.
Kỳ vọng: (1) in liên kết của bản đang chạy, thoát 0, không mở bản thứ hai; (2) liên kết mới đăng nhập được; (3)
"Hibiscus Station is not running", mã ≠ 0; (4) không in / mở liên kết đăng nhập nào, một câu rõ có gợi ý
`--port`, mã ≠ 0, không traceback uvicorn (D-3); (5) in liên kết của bản demo (D-4).

**AT-7 (F-5, REG-2) Chế độ demo** · [Vendor]
1. `hibiscus-station --mock`. 2. Robot → Kết nối → Hiệu chỉnh (cả hai tay) → Kiểm tra → Điều khiển tay →
Bắt đầu → Dừng → Ghi 1 tập. Lặp lại bước 2 năm lần, mỗi lần bấm Bắt đầu / Kiểm tra **một** lần.
3. Thoát. 4. Liệt kê `~/.hibiscus/station-demo` và `~/.hibiscus/station` (so thời gian sửa với trước bước 1).
Kỳ vọng: chip **TAY GIẢ LẬP** luôn hiện; 5 / 5 lần Kiểm tra báo "Hai tay khớp nhau" và teleop bắt đầu ngay ở lần
bấm đầu, không `leader_far` (P-4, D-8), không cần `POST /mock/inject`; dữ liệu chỉ nằm trong `station-demo`, thư
mục thật không đổi.

**AT-8 (F-6, NFR-14) Chỉ cục bộ** · [Vendor]
1. Station đang chạy: `ss -ltnp | grep 18210` (Windows: `netstat -ano | findstr 18210`). 2. `curl -s -o /dev/null
-w '%{http_code}' http://127.0.0.1:18210/api/v1/status` (không cookie). 3. `curl -H 'Host: evil.com'
http://127.0.0.1:18210/api/v1/status`. 4. Gọi `POST /api/v1/estop` có Bearer token nhưng không có `X-Station`.
5. Ghép nối máy chủ thử, mở `logs/station.log` và gọi `GET /api/v1/server`.
Kỳ vọng: (1) chỉ nghe trên `127.0.0.1` (hoặc `::1`), không `0.0.0.0`; (2) `401`; (3) `403 forbidden_host`; (4)
`403 csrf`; (5) token máy chủ bị che (`hbp_xxxx…`), `GET /server` không chứa token.

**AT-9 (F-6) Chế độ LAN** · [Vendor] trong mạng cô lập (network namespace hoặc VM, FL-8)
1. Trong namespace / VM có địa chỉ riêng: `hibiscus-station --host 0.0.0.0` (không token) → quan sát mã thoát.
2. `HIBISCUS_STATION_TOKEN=<32 ký tự [A-Za-z0-9_-]> hibiscus-station --host 0.0.0.0 --allow-host robot.local`.
3. Từ namespace / VM thứ hai trong cùng mạng: `curl -H 'Host: robot.local:18210' -H 'Authorization: Bearer
<token>' http://<ip>:18210/api/v1/status`; rồi cùng lệnh với `Host: <ip>:18210`.
Kỳ vọng: (1) thoát mã 2 với lời giải thích cần token và tên máy; (3) `robot.local` → 200; bằng IP → `403
forbidden_host`.

**AT-10 (F-7, REG-12) Thanh bước và bước bị khoá** · [Vendor]
1. Chưa có hồ sơ: lần lượt bấm 8 bước trên thanh bước. 2. Gõ thẳng `/run`. 3. Thu hẹp còn 390 px, lặp lại.
4. Kết nối robot (giả lập), e-stop, bấm Ghi dữ liệu. 5. Ở trang bị khoá, mở "Chi tiết kỹ thuật".
Kỳ vọng: bước bị khoá hiện lý do dưới tên; trang "Bước này đang bị khoá" với lý do bằng lời tiếng Việt + nút
"Tới <bước>", mọi nút trên trang tắt; **không** có dòng tiếng Anh / đường dẫn hiện sẵn (P-5, D-5); Huấn luyện vẫn
có form ghép nối; (4) lý do "Hãy đặt lại sau khi dừng khẩn cấp" (không có chữ "reset", D-12); (5) lý do thô của
Station chỉ thấy khi mở mục này; ✓ xuất hiện đúng khi điều kiện xong.

## B. Robot và cổng

**AT-11 (F-8) Hồ sơ robot** · [Vendor]
1. Robot → Robot mới; điền tên, SO-101, cổng follower, "Không có leader", lưu. 2. Sửa: thêm leader, chọn mã
hiệu chỉnh có sẵn của LeLab, "Về tư thế nghỉ rồi thả lỏng"; lưu. 3. Khi đang teleop thử sửa. 4. Xoá hồ sơ.
Kỳ vọng: lưu / sửa đúng; (3) bị từ chối với lý do; (4) hồ sơ mất, tệp hiệu chỉnh vẫn còn.

**AT-12 (F-9) Danh sách cổng** · [Vendor] (adapter USB-serial CH340 / CH343 cắm vào máy Linux, không cần tay) + [UAT-KH]
1. Cắm hai bộ chuyển; mở chọn cổng; bấm Làm mới. 2. Kết nối hồ sơ dùng một cổng, Làm mới. 3. [UAT-KH] Mở
LeLab giữ cổng follower, bấm Kết nối trong Station.
Kỳ vọng: (1) chỉ cổng USB serial với mô tả và VID:PID (Windows `COMx`, Linux đường dẫn `by-id`); (2) cổng đó hiện
"đang dùng bởi Station (Tay follower)"; (3) Windows: "đang bận — có thể LeLab / lerobot đang mở" sau khi Kết nối
thất bại; Linux: nêu tên tiến trình (SA-W1).

**AT-13 (F-10, REG-6) Tìm theo vai trò bằng cử động** · [Vendor] (test tự động `tests/test_ports_roles.py`) + [UAT-KH]
1. Bấm "Tìm tay follower (cử động)" → Bắt đầu; cử động **leader** trước rồi follower.
2. Bấm "Tìm tay leader (cử động)" → cử động leader. 3. Lặp lại khi không cử động gì 15 s.
Kỳ vọng: (1) ô follower nhận đúng cổng follower trong ≤ 15 s (không lấy cổng leader); (2) không bao giờ đề
xuất cổng đã gán cho follower; (3) "Không tìm thấy", không treo, thử lại được. [Vendor]: test tự động xanh trên
bản ứng viên (danh sách cổng giả lập pty không phải USB nên không chạy tay được).

**AT-14 (F-10) Tìm bằng rút cáp** · [UAT-KH]
1. "Tìm tay leader (rút cáp)" → Bắt đầu → rút USB leader. 2. Cắm lại.
Kỳ vọng: cổng leader được gán vào ô leader trong ≤ 15 s.

**AT-15 (F-11, REG-6) Gợi ý vai trò và đổi chỗ** · [Vendor] (test tự động `tests/test_ports_roles.py::test_role_hint_from_voltage`, `::test_probe_reads_voltage_model_and_firmware_read_only`) + [UAT-KH]
1. Gán cố ý cổng leader (5 V) vào ô follower và ngược lại. 2. Xem gợi ý dưới cổng. 3. Bấm "Đổi chỗ
follower ⇄ leader".
Kỳ vọng: cảnh báo "Cổng follower đọc 5,0 V: có vẻ đây là tay leader…"; Station không tự đổi; sau Đổi chỗ
hai cổng đổi nhau, mã hiệu chỉnh vẫn theo vai trò; cổng không đọc được → "Không đọc được điện áp…"; dò cổng không
ghi thanh ghi nào, không bật mô-men (log lệnh của giả lập: chỉ ping / read).

**AT-16 (F-12, REG-14) Kết nối và lỗi theo bước** · [Vendor] + [UAT-KH]
1. Kết nối hồ sơ đúng (giả lập pty `tests/sts_emulator.py` / tay thật). 2. [Vendor] Chạy
`tests/test_real_stack.py::test_noisy_bus_still_connects_and_calibrates` (giả lập hỏng 1–2 % gói, 10 lần kết nối
+ hiệu chỉnh). 3. [Vendor] Chạy `tests/test_real_stack.py::test_bus_failure_in_a_command_is_a_bus_error_not_internal`
và giả lập thiếu động cơ id 4 (khởi động `sts_emulator` không có id 4), bấm Kết nối. 4. Ngắt kết nối.
Kỳ vọng: (1) tiến trình mở cổng → bắt tay → cấu hình; `Sẵn sàng`, mỗi tay 6 động cơ, có nhiệt độ; ≤ 5 s
(không camera); (2) test xanh (10 / 10); (3) lỗi nói bước "handshake", động cơ thiếu, bằng tiếng Việt, không
`internal_error`; (4) về Chưa kết nối.

**AT-17 (F-12, F-13) Cổng bận trên Windows** · [UAT-KH]
1. Mở LeLab (hoặc `lerobot-teleoperate`) trên follower. 2. Kết nối trong Station. 3. Đóng LeLab, bấm Kết nối.
Kỳ vọng: (2) "Một chương trình khác (LeLab? lerobot?) đang dùng COMx." với lời nhắc đóng LeLab; trạng thái là
`port_busy`, **không** phải "Mất kết nối USB" / `device_lost` (SA-W2); (3) kết nối được ngay.

**AT-18 (F-13, REG-8) Rút USB khi teleop trên Windows** · [UAT-KH] (quay video màn hình + tay bằng điện thoại)
Tiền điều kiện: ghi loại bộ chuyển của từng tay (VID:PID trong báo cáo `doctor`: `1a86:7523` = CH340, `1a86:55d3`
= CH343).
1. Teleop. 2. Rút USB follower. 3. Đọc trang. 4. Cắm vào **ổ USB khác** trên PC. 5. "Kết nối lại". 6. Teleop.
7. Nếu cả hai tay là CH340: rút cả hai, cắm lại, Kết nối lại.
Kỳ vọng: ≤ 1 s trạng thái lỗi "Mất kết nối USB với Tay follower (COMx)" + danh sách kiểm tra, không có
"Access is denied" thô làm thông báo chính, không 6 lần thử lại; Kết nối lại chờ cổng, nhận số COM mới
("Tay follower giờ ở cổng COMy"), kết nối; teleop chạy lại không khởi động lại Station; (7) Station hỏi tay nào
là tay nào (đúng thiết kế, FR-13), sau khi chọn teleop chạy.

**AT-19 (F-13, NFR-7, REG-8) Mất thiết bị trên giả lập** · [Vendor]
1. Station với giả lập pty: teleop, rồi đóng pty của follower (dừng tiến trình `sts_emulator`). 2. Đọc
trạng thái (`GET /api/v1/status`) và log giả lập. 3. Chạy `tests/test_device_lost.py` (gồm pty đóng giữa teleop,
trở lại dưới tên mới, gói hỏng đơn lẻ, hai bộ chuyển giống hệt không serial).
Kỳ vọng: (2) `error(device_lost)` có tay, cổng, thông báo hệ thống trong ≤ 1 s; 0 lệnh tắt mô-men lặp; (3) test
xanh. (Kết nối lại vào pty mới không chạy tay được bằng wheel vì pty không phải thiết bị USB; phần đó phủ bởi
test tự động và AT-18.)

**AT-20 (F-14) Mô-men và tư thế nghỉ** · [Vendor] + [UAT-KH]
1. Kết nối, chưa có tư thế nghỉ: "Thả lỏng (tắt mô-men)". 2. Huỷ; đặt tay gập, "Lấy tư thế hiện tại làm tư
thế nghỉ". 3. Thả lỏng lại; Bật mô-men.
Kỳ vọng: (1) hộp xác nhận "tay robot sẽ rũ xuống tại chỗ…"; (2) "Đã lưu tư thế nghỉ…"; (3) không còn hộp
xác nhận; bật mô-men giữ tay tại chỗ, không giật.

**AT-21 (F-15, REG-2) Hồ sơ demo còn sót** · [Vendor] + [UAT-KH]
1. Chạy `--mock --home <thư mục thật>` tạo hồ sơ demo, thoát. 2. Cắm tay thật, chạy `hibiscus-station`.
3. Bấm Kết nối hồ sơ demo. 4. Bấm "Tạo hồ sơ cho tay thật".
Kỳ vọng: hồ sơ demo có nhãn DEMO, không hoạt động, Kết nối tắt với lý do; banner "Đang dùng tay giả lập —
tay thật (COMx) không chuyển động"; (4) form điền sẵn cổng thật.

## C. Hiệu chỉnh

**AT-22 (F-16, REG-7) Dùng lại tệp LeLab** · [Vendor] (giả lập) + [UAT-KH]
Tiền điều kiện: tay đã hiệu chỉnh bằng LeLab (tệp `so_101_follower.json`), mã trong hồ sơ khác.
1. Kết nối, mở Hiệu chỉnh.
Kỳ vọng: "Tay này đang dùng hiệu chỉnh từ LeLab: so_101_follower.json" + "Dùng"; bấm Dùng → "đã hiệu chỉnh
— dùng luôn", có bản sao mang mã của robot; không đề xuất tệp của tay kia; tay đã đúng tệp → "đã hiệu chỉnh
— dùng luôn" ngay.

**AT-23 (F-17, REG-4, REG-7) Luồng hiệu chỉnh đầy đủ** · [UAT-KH] (quay video)
1. Hiệu chỉnh lại follower: Đặt home (tay ở giữa như hình). 2. Bước Biên độ: quay từng khớp, **kể cả
wrist_roll**, hết hành trình. 3. Lưu. 4. Làm tương tự leader. 5. Kiểm tra hai tay → Thử teleop.
Kỳ vọng: mọi khớp hiện `min | vị trí | max`, không có chữ "xoay tròn"; tick khi đủ 100 bước; "Đã xong 6 / 6";
Lưu chỉ mở khi đủ; tệp nằm ở `%USERPROFILE%\.cache\huggingface\lerobot\calibration\robots\so_follower\<id>.json`
(mở bằng Notepad: có `range_min` / `range_max` của `wrist_roll` khác 0 / 4095); toàn bộ ≤ 3 phút mỗi tay; teleop
chạy ngay sau đó.

**AT-24 (F-17, REG-4) Lưu bị chặn tới khi đủ khớp** · [Vendor]
1. Giả lập: quay 5 khớp, bỏ gripper. 2. Bấm Lưu; gọi `POST /calibration/step {"action":"finish_ranges"}`.
3. Huỷ giữa chừng; e-stop giữa chừng.
Kỳ vọng: Lưu tắt với "Nút Lưu mở khi mọi khớp đã được đánh dấu"; API từ chối; huỷ / e-stop về trạng thái
trước, tệp cũ không đổi; số đọc ngoài dải encoder bị bỏ.

**AT-25 (F-18) Tệp hiệu chỉnh nâng cao** · [Vendor]
1. Mở "Nâng cao: các tệp hiệu chỉnh" với nhiều tệp (gồm thư mục cũ `so101_follower`, một tệp của leader trong
thư mục follower, một tệp hỏng). 2. "Dùng tệp này" một tệp.
Kỳ vọng: nhãn đúng ("của robot này", "động cơ đang dùng", "thuộc tay leader", "không phải tệp hiệu chỉnh");
tệp của tay kia không có nút Dùng; sau Dùng, tệp cũ còn dưới `.bak-<thời gian>`.

**AT-26 (F-19, REG-7) Kiểm tra hai tay** · [Vendor] + [UAT-KH]
1. Đặt leader giống follower, Kiểm tra. 2. Lệch cố ý khớp `elbow_flex` 40°, Kiểm tra. 3. Mở kẹp leader hết cỡ
khi kẹp follower đóng, Kiểm tra. 4. [Vendor] Dùng tệp hiệu chỉnh của tay khác cho leader. 5. [Vendor] Đổi cổng
hai tay trong hồ sơ.
Kỳ vọng: (1) "Hai tay khớp nhau (lệch lớn nhất X)" + Thử teleop; (2) chỉ `elbow_flex` "lệch hơn 20°" + "Đặt lại
tay leader…", không nhắc nhầm cổng; (3) kẹp báo bằng **%** ("lệch hơn 20 %"), không "°" (D-7); (4) "có thể đang
dùng nhầm tệp hiệu chỉnh" + Hiệu chỉnh lại; (5) "Mọi khớp đều lệch: có thể đã nhầm cổng…"; mỗi trường hợp chỉ một
lý do; luôn có "Vẫn thử teleop".

**AT-27 (F-20, NFR-15) Dùng chung với lerobot và LeLab** · [Vendor] (lerobot 0.7.1) + [UAT-KH] (LeLab của khách)
1. [Vendor] Sau hiệu chỉnh trên giả lập, chạy `tests/test_owner.py::test_calibration_files_are_loadable_by_lerobot`;
nạp một tệp do lerobot 0.7.1 ghi vào Station. 2. [UAT-KH] Ghi phiên bản lerobot của LeLab trên PC (mục
"lerobot" trong báo cáo `doctor`). 3. [UAT-KH] Tắt Station; mở LeLab, chọn đúng mã tay (id) đã hiệu chỉnh trong
Station, teleop. 4. [UAT-KH] Hiệu chỉnh một tay bằng LeLab; trong Station mở Hiệu chỉnh.
Kỳ vọng: (1) test xanh, vị trí khớp hợp lý; (3) LeLab teleop không đòi hiệu chỉnh lại; (4) Station đề xuất "Tay
này đang dùng hiệu chỉnh từ LeLab" (hoặc tệp hiện trong "Nâng cao: các tệp hiệu chỉnh" nếu LeLab dùng thư mục cũ)
và sau "Dùng" vị trí khớp hợp lý (Robot 3D cùng tư thế). Nếu (3) thất bại vì LeLab dùng thư mục cũ: ghi lại
phiên bản; đó là CR, không phải lỗi v1.0 (FR-20).

## D. Camera

**AT-28 (F-21, REG-20) Tìm và thử camera** · [Vendor] (webcam USB) + [UAT-KH]
1. Camera → Quét lại. 2. Thử từng camera. 3. Thử 1920×1080@30 trên camera USB 2.0.
4. Khi một camera đang được dùng, Quét lại. 5. [UAT-KH, nếu có hai webcam] Khởi động lại PC (hoặc rút / cắm cả
hai), mở Station, Thử từng camera.
Kỳ vọng: mỗi camera một lần (Windows: 0, 1…), có ảnh chụp và fps đo; (3) cảnh báo "Camera chậm hơn yêu cầu…";
(4) camera đó hiện "đang dùng bởi <tên>", không bị mở lại; không có lỗi OpenCV in ra console; (5) ghi lại số
của từng camera trước / sau; nếu đổi số, ảnh Thử cho thấy đúng camera và hướng dẫn có bước kiểm này (SA-W4).

**AT-29 (F-22) Cấu hình và xem camera** · [Vendor] + [UAT-KH]
1. Thêm camera tên `front` 640×480@30 MJPG; thêm `Front!` (tên sai), thêm trùng `front`. 2. Xoay 180°.
3. Mở Teleop, Ghi, Chạy model.
Kỳ vọng: tên sai / trùng bị từ chối với lời giải thích; trang nói "Tên camera là khoá mà policy cần…"; hình
trực tiếp ở mọi màn hình chuyển động, xoay đúng.

**AT-30 (F-23, REG-15) Camera mất khi ghi** · [UAT-KH] (+ [Vendor] test tự động + webcam USB)
1. Ghi một tập; giữa tập rút một camera. 2. Mở dataset sau đó.
3. [Vendor] Chạy `tests/test_sessions.py::test_camera_stale_pauses_then_stops_recording`; lặp bước 1–2 với webcam
USB trên Linux.
Kỳ vọng: ≤ 0,5 s cảnh báo "Camera … không gửi hình. Đồng hồ tập đang tạm dừng", lớp sọc; sau 3 s phiên dừng
(`mất camera`), tay được giữ; dataset mở được bằng lerobot, đúng số tập đã lưu; (3) xanh.

## E. Teleop và phát lại

**AT-31 (F-24, NFR-1a, NFR-1b, NFR-1c, NFR-2, REG-5, REG-7) Độ trễ và nhịp teleop** · [Vendor] (số đo) + [UAT-KH] (A/B với LeLab)
1. [Vendor] `tests/teleop_bench.py` trên giả lập (1 Mbaud, servo ~300°/s), adapter 1 ms và 8 ms, cử động chậm và
nhanh; ghi trễ bám p50 / p95 của Station và của vòng tham chiếu kiểu LeLab, Hz, % nhịp bị cắt.
2. [UAT-KH] Teleop 2 phút, cử động leader nhanh qua lại; đọc "độ trễ ~X ms, Y Hz" trên màn hình; sau khi dừng,
mở Phiên → phiên đó, ghi `latency_ms_p50` / `_p95` và `loop.fps`.
3. [UAT-KH] Tắt Station; cùng PC, cùng tay, cùng động tác 2 phút với LeLab. Video quay chậm bằng điện thoại: tuỳ
chọn.
Kỳ vọng: (1) p50 ≤ 70 ms, p95 ≤ 100 ms, ≤ tham chiếu + 10 ms ở cả 1 ms và 8 ms (NFR-1a); (2) p50 ≤ 15 ms, p95 ≤ 30
ms khi `doctor` báo ≤ 3 ms mỗi lần đọc; Hz theo NFR-2; không cảnh báo "không theo kịp" khi cử động bình thường;
(3) khách ghi "không chậm hơn LeLab" (hoặc mô tả khác biệt).

**AT-32 (F-24, REG-15) Teleop không cần camera** · [Vendor]
1. Hồ sơ có 2 camera, rút cả hai. 2. Bắt đầu teleop. 3. Bắt đầu ghi.
Kỳ vọng: teleop chạy; ghi bị từ chối "Có camera đã cấu hình nhưng không truyền hình."

**AT-33 (F-25) Leader xa và căn tay** · [Vendor] + [UAT-KH]
1. Gập leader, để follower duỗi (lệch > 30°) ([Vendor] `--mock`: inject `{"port":"mock://leader","hand":"hold",
"hold":{"elbow_flex":600}}`). 2. Bắt đầu điều khiển. 3. "Đưa tay follower về tư thế tay leader".
4. Lặp lại, bấm Space giữa lúc căn.
Kỳ vọng: (2) từ chối bằng một câu tiếng Việt có khớp, độ lệch kèm "°" và nút căn, không dòng tiếng Anh hiện
sẵn (D-5); (3) follower đi chậm (≤ 30°/s), rồi teleop bắt đầu;
(4) dừng ngay, `estopped`; trang Ghi không bao giờ đề nghị căn.

**AT-34 (F-26, REG-5) Cảnh báo không theo kịp** · [Vendor]
1. `tests/teleop_bench.py` với adapter 16 ms và cử động nhanh (servo chậm hơn leader); xem cảnh báo trên Station
nối vào giả lập đó.
Kỳ vọng: khi > 20 % nhịp bị cắt: cảnh báo "Tay follower chạy sau tay leader quá giới hạn an toàn 30°…".

**AT-35 (F-27) Phát lại tập** · [Vendor] + [UAT-KH]
1. Bộ dữ liệu → một dataset → Phát lại tập 0. 2. Bấm Dừng giữa chừng. 3. Phát lại, đóng tab.
Kỳ vọng: follower lặp lại chuyển động; Dừng trong một nhịp; đóng tab → dừng ≤ 1 s (`ui_lost`).

## F. An toàn

**AT-36 (F-28, NFR-3a, NFR-3c) E-stop đóng băng** · [Vendor] + [UAT-KH]
1. [Vendor] Chạy `tests/test_owner.py::test_estop_freezes_within_one_tick_then_relaxes`,
`tests/test_teleop_lean.py::test_estop_in_the_lean_loop_freezes_within_one_tick`,
`tests/test_traj_sessions.py::test_estop_mid_replay_stops_within_one_tick`,
`tests/test_program_session.py::test_estop_aborts_the_program_within_one_tick`,
`tests/test_field_028.py::test_align_honours_the_estop`. 2. Teleop cử động liên tục; bấm Space. 3. Lặp lại khi
đang ghi, chạy model, phát quỹ đạo, chương trình, về tư thế nghỉ, căn tay, hiệu chỉnh. 4. Lặp lại khi con trỏ
đang trong ô chữ (dùng Esc). 5. Bấm vào một cửa sổ khác (ví dụ Notepad) rồi bấm Space.
Kỳ vọng: (1) xanh: không lệnh vị trí nào sau ≤ 1 nhịp (≤ 1 nhịp + 1 lần suy luận khi chạy model); (2)–(4) tay dừng
ngay, vẫn giữ mô-men, không rơi; trạng thái "Đã dừng khẩn" với lý do; Space không cuộn trang; (5) Space không có
tác dụng (đúng thiết kế, hướng dẫn nói rõ); bấm lại vào cửa sổ Station rồi Space thì dừng.

**AT-37 (F-28, NFR-7, REG-10) Thả lỏng, đặt lại, hiệu chỉnh không đổi** · [Vendor] + [UAT-KH]
1. Trước bước 2, [Vendor] lưu hash SHA-256 của tệp hiệu chỉnh và bản đọc EEPROM (`doctor --verbose`). 2. Sau
AT-36, bấm Space lần hai trong 2 s. 3. Đỡ tay; "Đã an toàn, đặt lại". 4. So hash và EEPROM sau; [Vendor] chạy
`tests/test_field_028.py::test_estop_and_reset_never_touch_the_calibration`.
Kỳ vọng: (2) mô-men tắt, banner "Hãy đỡ tay robot" hiện (D-6); (3) về Sẵn sàng; (4) không thay đổi; test xanh.

**AT-38 (F-29, NFR-4) Dead-man** · [Vendor] + [UAT-KH]
1. Chạy model; đóng tab. 2. Lặp lại với phát lại, chương trình, về tư thế nghỉ. 3. Mở lại trang. 4. [Vendor]
Đo thời gian từ đóng tab tới `estopped(ui_lost)` trong log (dấu thời gian).
Kỳ vọng: robot dừng trong ≤ 1,0 s + 1 nhịp (+ 1 lần suy luận khi chạy model), lý do "mất kết nối giao diện"; mở lại
trang thấy trạng thái dừng và nút đặt lại.

**AT-39 (F-30) Giới hạn an toàn và điều kiện bắt đầu** · [Vendor]
1. Chạy model (giả lập) với bước tối đa 2.0. 2. Trên Chạy model nhập bước lớn hơn hồ sơ. 3. Bắt đầu phiên
khi: động cơ nóng (`POST /api/v1/mock/inject {"motor":"elbow_flex","temp_c":61}`); tay chưa hiệu chỉnh; đang
e-stop; đang teleop. 4. Chạy `tests/test_units.py` (bộ lọc an toàn: lệnh vượt dải hiệu chỉnh bị kẹp).
Kỳ vọng: (1) chuyển động chậm, khớp bị cắt đánh dấu; (2) "Vượt mức X của hồ sơ. Mở Nâng cao để tăng"; (3) từ
chối với câu tương ứng (`motor_hot`, `not_calibrated`, `estopped`, `busy`); (4) test xanh.

**AT-40 (F-31, NFR-13, REG-13) Độ chính xác telemetry so với Feetech FD** · [UAT-KH]
Tiền điều kiện: công cụ Feetech FD trên cùng PC; Station và LeLab đã tắt khi dùng FD (cổng COM độc quyền).
1. Để tay nguội 30 phút. Mở FD, đọc nhiệt độ, điện áp, dòng của servo `elbow_flex` follower; chụp màn hình;
đóng FD. 2. Mở Station, kết nối, mở ngăn sức khoẻ, chụp màn hình cùng servo. 3. Teleop 10 phút; lặp lại 1–2
(tắt Station trước khi mở FD). 4. Kẹp chặt một vật, xem dòng và tải; đẩy một khớp hai chiều khi có mô-men, xem
tải.
Kỳ vọng: nhiệt ±3 °C và điện áp ±0,2 V so với FD; khi tải, nhiệt tăng đều, không nhảy; dòng ±20 % so với FD nếu SP-1
đã xác nhận đơn vị, nếu không: dòng hiện "—" ở mọi nơi (P-8); tải đổi dấu khi đẩy hai chiều; nếu servo báo 0 °C
(cả trên FD): ô hiện "—", không cảnh báo giả, ghi kết quả vào REG-13. Bằng chứng: các ảnh chụp.

**AT-41 (F-31, REG-11) Bảng và ngăn sức khoẻ** · [Vendor]
1. `--mock`: kết nối; xem bảng gọn trên Robot, Teleop, Ghi, Chạy model, Chương trình. 2. Bấm chip động cơ nóng
nhất. 3. Chạy `tests/test_field_028.py` (5 test telemetry: một lần đọc không trả lời, ba lần liên tiếp, leader).
Kỳ vọng: đủ 5 đại lượng mỗi động cơ, đơn vị đúng; ngăn chi tiết có 120 s, ngưỡng nét đứt, giới hạn từ động
cơ; (3) xanh: "không phản hồi" có tooltip; ba lần → cảnh báo "Không đọc được thông số động cơ"; leader có ghi
chú "chỉ để tham khảo".

**AT-42 (F-32, NFR-6, REG-3) Dừng an toàn nhiệt** · [Vendor] (giả lập) + [UAT-KH] (chỉ khi servo của khách báo nhiệt thật)
1. Cài đặt: hạ ngưỡng nguy hiểm xuống nhiệt hiện tại + 1 (giữ RULE-4); lưu tư thế nghỉ. [Vendor] `--mock`:
`POST /api/v1/mock/inject {"motor":"elbow_flex","temp_c":67}` hai lần cách 1 s. 2. Teleop tới khi kích hoạt.
3. Bấm đặt lại khi còn nóng. 4. Chờ nguội ([Vendor] `{"motor":"elbow_flex","clear_temp":true}`), đặt lại.
5. [Vendor] Chạy `tests/test_owner.py::test_thermal_critical_safe_stop_and_reset_refused` và
`tests/test_units.py::test_zero_temperature_readings_never_trip_the_thermal_guard`.
Kỳ vọng: (2) sau mẫu nguy hiểm thứ hai: giữ → về tư thế nghỉ → tắt mô-men trong ≤ 2 s; banner đỏ đúng chữ;
"Đã dừng vì nhiệt"; ước lượng thời gian nguội; (3) bị từ chối `409 motor_hot`; (4) về Sẵn sàng; (5) xanh (0 °C và
`Max_Temperature_Limit = 0` không gây dừng, ngưỡng không đổi). [UAT-KH] trên tay không báo nhiệt: ghi "không áp
dụng — servo không báo nhiệt" có chữ ký khách (theo mã AT-42), và AT-93 phải đạt.

**AT-43 (F-33, NFR-12, REG-3, REG-11, REG-13) Số đo vô lý** · [Vendor]
1. `--mock`: `POST /api/v1/mock/inject` lần lượt `{"port":"mock://follower","temp_c":0}`, `{"port":"mock://leader",
"current_raw":33768}` (1000 + bit 15); xem màn hình và Robot 3D. 2. Teleop 5 phút. 3. Leader `temp_c` 62, rồi 70.
4. Chạy `tests/test_units.py` và `tests/test_field_028.py` (nhiệt 200 °C, tải 120 %, điện áp 0 và 20 V).
Kỳ vọng: giá trị vô lý hiện "—" với tooltip "Không có giá trị…"; 0 cảnh báo, 0 dừng, lần đọc không bị coi là
lỗi; leader 62 °C → "nóng" không chặn phiên, 70 °C vẫn tối đa "nóng", không dừng; Robot 3D tô "chưa có số đo" cho
giá trị không rõ; (4) xanh.

**AT-44 (F-34, REG-16) Dừng vì điện, kẹp quá tải** · [Vendor] + [UAT-KH]
1. [Vendor] Chạy `tests/test_units.py::test_guard_status_and_voltage_critical` (điện áp dưới tối thiểu 1 lần, rồi 2
lần liên tiếp), `::test_gripper_overload_is_a_grasp_not_a_fault`, `::test_guard_load_stall_and_current`.
2. [UAT-KH] Teleop, bóp kẹp chặt một vật 5 s. 3. [UAT-KH] Giữ một khớp follower bằng tay khi leader kéo nó đi > 2 s.
Kỳ vọng: (1) xanh (1 lần: cảnh báo; 2 lần: dừng an toàn "lỗi điện"); (2) không dừng (chỉ cảnh báo nếu có); (3)
cảnh báo "bị kẹt".

**AT-45 (F-35, NFR-7, REG-10) Về tư thế nghỉ sau khi dừng giữa chừng** · [Vendor] + [UAT-KH]
1. Phát một quỹ đạo (UAT-1: chạy model, vì quỹ đạo là Should); e-stop giữa chừng; đặt lại. 2. Bấm "Về tư thế nghỉ"; bấm Space giữa đường; lặp lại để
đi hết. 3. Hồ sơ chưa có tư thế nghỉ: lặp bước 1.
Kỳ vọng: banner "Tay robot đã dừng giữa chừng…" + "Về tư thế nghỉ"; chuyển động chậm ≤ 30°/s, Space huỷ; (3)
"Hãy lưu tư thế nghỉ ở trang Robot…".

**AT-46 (F-36) Thông báo và kết nối lại giao diện** · [Vendor]
1. Đang teleop (`--mock`), tải lại trang (F5). 2. Tắt Station (Ctrl+C) khi trang đang mở; chạy lại. 3. `POST
/api/v1/mock/inject {"motor":"elbow_flex","temp_c":61}`, rồi `67` hai lần.
Kỳ vọng: (1) trang khôi phục đúng trạng thái; (2) "Đang kết nối lại… các nút điều khiển tạm khoá…", tự kết nối
lại khi Station chạy (mở liên kết đăng nhập mới nếu token đổi); (3) banner cam / đỏ đúng chữ; đỏ không ẩn được
khi còn nguy hiểm; Hibi nói tên khớp và giá trị.

**AT-47 (F-37, NFR-15) Lịch sử phiên** · [Vendor]
1. `--mock`: chạy teleop, ghi, chạy model. 2. Mở Phiên. 3. Tắt Station; đổi thời gian sửa của một thư mục
`sessions/<id>` về 31 ngày trước (`touch -d '31 days ago' <thư mục>`); khởi động lại. 4. Chạy
`tests/test_units.py::test_session_retention` (vượt 2 GiB).
Kỳ vọng: mỗi phiên một dòng với loại, thời gian, kết quả, nhiệt độ cao nhất; xem telemetry được; (3) phiên đó bị
xoá; (4) xanh.

## G. Ghi dữ liệu

**AT-48 (F-38) Ghi 3 tập với phím** · [Vendor] + [UAT-KH]
1. Ghi: dataset mới `thu_nghiem`, nhiệm vụ tiếng Việt, 3 tập × 10 s, đặt lại 5 s. 2. Tập 1 bấm →; tập 2 bấm ←
rồi ghi lại; tập 3 để hết giờ. 3. Lặp lại một lần ghi, bấm Esc giữa tập; một lần e-stop giữa tập. 4. [Vendor]
Trong suốt bước 1–3, lọc `station.log` và log truy cập tìm phản hồi 5xx.
Kỳ vọng: tiêu đề pha đúng ("Tập 1 / 3 · đang ghi · …", "Đặt lại cảnh", "Đang lưu tập…"); tập hết giờ được
lưu; kết thúc "Đã lưu 3 tập trong …" + Tải lên / Ghi thêm; (3) dataset vẫn hoàn tất và mở được; (4) 0 phản hồi 5xx
(D-2).

**AT-49 (F-38, NFR-15) Dataset hợp lệ** · [Vendor]
1. Mở dataset của AT-48 bằng lerobot 0.7.1 (`LeRobotDataset('local/thu_nghiem', root=…)`).
2. Liệt kê tệp trong thư mục dataset.
Kỳ vọng: mở được, đúng số tập và camera; không tệp lạ trong thư mục LeRobot; telemetry nằm trong
`thu_nghiem.hibiscus/`.

**AT-50 (F-39) Ghi thêm** · [Vendor]
1. Ghi thêm 2 tập vào `thu_nghiem`. 2. Thêm một camera giả (`--mock`, Camera → Thêm), ghi thêm lần nữa. 3. Dataset mới trùng tên.
Kỳ vọng: (1) 5 tập; (2) từ chối "Dataset này không khớp với robot…"; (3) "Đã có bộ dữ liệu tên này. Hãy chọn ghi
thêm".

**AT-51 (F-40) Bộ dữ liệu** · [Vendor]
1. Mở Bộ dữ liệu, chi tiết `thu_nghiem`, chọn từng tập. 2. Xoá (Huỷ, rồi Xoá vĩnh viễn). 3. Bắt đầu ghi một
dataset khác; trong lúc đang lưu tập, mở chi tiết của dataset đó và thử Xoá.
Kỳ vọng: số tập, khung hình, fps, dung lượng đúng; biểu đồ nhiệt mỗi tập; "Tập này không có telemetry" khi
thiếu; xoá cần xác nhận; (3) trang chi tiết mở không lỗi (tập đang lưu hiện "Đang lưu…", 0 phản hồi 5xx, D-2), Xoá
bị từ chối.

**AT-99 (F-72, FR-77, NFR-10, NFR-11, REG-27, CR-1) Xem video từng tập** · [Vendor] + [UAT-KH]
Tiền điều kiện: dataset `thu_nghiem` của AT-48 (3 tập, ≥ 2 camera; LeRobot gộp các tập vào **một** tệp mp4 mỗi camera).
1. [Vendor] Bộ dữ liệu → `thu_nghiem` → bấm **#2**. Bấm **Phát**; để chạy hết tập. Bấm **Phát** lần nữa; giữa tập bấm
   **Tạm dừng**; kéo thanh "Thời điểm trong tập" tới khoảng giữa; bấm vào biểu đồ nhiệt độ gần cuối tập.
2. [Vendor] Bấm #1 rồi #3; so khung đầu / cuối của mỗi camera với tập đó (`LeRobotDataset('local/thu_nghiem', root=…)[i]`
   ở khung đầu và cuối của tập, hoặc nhìn cảnh).
3. [Vendor] Đổi trình duyệt: Chromium, Firefox (Linux, Playwright) và **Microsoft Edge trên CI `windows-latest`** (e2e
   `tests/e2e/test_station_ui.py`, bước 7): mỗi camera ở trạng thái "đã phát" và thời gian video tăng khi Phát; ghi lại
   định dạng được dùng (`data-format` = `source` / `h264` / `vp9`) và kết quả `canPlayType` của AV1.
4. [Vendor] Xoá tệp mp4 của một camera (bản sao của dataset), mở lại tập; ghi đè tệp mp4 của camera kia bằng vài byte rác.
5. [Vendor] Bắt đầu ghi một dataset mới (`--mock`); trong lúc đang ghi, mở chi tiết dataset đó và bấm một tập; gọi
   `GET /api/v1/datasets/<tên>/episodes/0/videos/<camera>`.
6. [Vendor] API: `Range: bytes=0-99`, `Range: bytes=-50`, một khoảng ngoài tệp; tên dataset / camera có `..`, `%2F`, chữ
   hoa; `format=../../x`; không cookie / token; `meta/info.json` sửa `video_path` trỏ ra ngoài thư mục dataset.
7. [Vendor] Lặp bước 1 ở 1280 px và 390 px, sáng và tối, tiếng Việt và English (ma trận ảnh Playwright + axe).
8. **[UAT-KH] PC Windows 11 của khách, Edge cài sẵn (chưa cài "AV1 Video Extension"; kiểm ở Cài đặt → Ứng dụng):**
   Bộ dữ liệu → một dataset ghi bằng tay thật (≥ 2 camera) → bấm một tập → Phát hết tập; Tạm dừng; kéo thanh thời gian;
   bấm vào biểu đồ. Lặp lại với Chrome và Firefox trên cùng PC.
Kỳ vọng: (1) mọi camera phát cùng lúc, lệch nhau ≤ 0,25 s; "t / d giây" và con trỏ đỏ trên biểu đồ chạy theo video;
hết tập thì dừng ở cuối, Phát lại từ đầu; Tạm dừng dừng mọi camera; kéo thanh / bấm biểu đồ → mọi camera và con trỏ tới
đúng thời điểm đó. (2) Mỗi tập chỉ có khung của chính nó (không lẫn tập bên cạnh), số khung = số khung của tập. (3) Cả ba
trình duyệt phát được; Edge không có AV1 dùng `h264` hoặc `vp9`. (4) Camera thiếu tệp: "Camera này không có tệp video cho
tập này."; tệp hỏng: "Không đọc được video của camera này."; camera còn lại vẫn phát. (5) Trang không lỗi; khung video
báo "Bộ dữ liệu này đang được ghi. Video mở được khi phiên ghi kết thúc."; API 409 `episode_saving`; sau khi dừng ghi, video
mở được; 0 phản hồi 5xx. (6) 206 với `Content-Range` đúng; 416 ngoài tệp; tên lạ / `..` → 404 hoặc 422, không đọc tệp
ngoài dataset (`video_unavailable`); không xác thực → 401. (7) Không cuộn ngang, chữ đúng ngôn ngữ, 0 vi phạm axe
serious / critical. (8) Như (1) trên cả Edge, Chrome, Firefox của khách; không phải cài thêm gì. Thư mục LeRobot không đổi
(AT-49).

## H. Liên kết máy chủ Hibiscus

**AT-52 (F-41) Ghép nối** · [Vendor] (máy chủ thử, token tạo sẵn với từng bộ quyền) + [UAT-KH] nếu khách có tài khoản
1. Chào mừng → Ghép nối: địa chỉ + token đúng. 2. Token thiếu `models:read`. 3. Token sai. 4. Huỷ ghép nối;
[Vendor] xem kho khoá (`keyring get` / Windows Credential Manager).
Kỳ vọng: (1) "Đã ghép nối với … (workspace …)", chip máy chủ; (2) nêu quyền thiếu; (3) "Máy chủ từ chối token
này."; (4) chip "Ngoại tuyến", token bị xoá khỏi kho.

**AT-53 (F-42) Tải lên** · [Vendor]
1. Tải `thu_nghiem` thành dataset mới. 2. Tải lại thành phiên bản mới. 3. Tải dataset chưa hoàn tất.
Kỳ vọng: tiến độ băm → tải lên → kiểm tra → "Đã tải lên thành phiên bản N" + "Mở trên máy chủ"; danh sách hiện
"đã tải lên vN"; (3) "Bộ dữ liệu chưa hoàn tất."; telemetry không được gửi.

**AT-54 (F-42, NFR-7, NFR-17) Tải tiếp sau mất mạng** · [Vendor] (máy chủ Hibiscus thử v0.1.1 trong container riêng)
1. Tải một dataset ≥ 200 MB; dừng container máy chủ thử giữa chừng. 2. Chạy lại container, bấm Tải lên.
3. Lặp lại, lần này tắt và chạy lại Station giữa chừng.
Kỳ vọng: công việc báo lỗi bằng lời + "Bấm tải lên lần nữa để tiếp tục…"; tải tiếp không gửi lại phần đã xác
nhận (log máy chủ thử: số phần nhận được = tổng số phần, không phần nào hai lần).

**AT-55 (F-43) Huấn luyện** · [Vendor]
1. Huấn luyện → "Mở huấn luyện trên Hibiscus". 2. Xem danh sách lượt. 3. "Tải về và chạy" ở lượt đã xong.
Kỳ vọng: thẻ mới mở trình tạo lượt với phiên bản đã chọn; lượt có trạng thái, tiến độ; (3) model được kéo về và
Chạy model mở với model đó.

**AT-56 (F-44) Kéo model từ máy chủ** · [Vendor] (máy chủ thử)
1. Chạy model → Từ máy chủ → Tải về. 2. Dừng container máy chủ thử giữa chừng, chạy lại, Tải về lần nữa.
3. Trên máy chủ thử, sửa một byte của tệp model (sha256 không còn khớp MANIFEST), Tải về.
Kỳ vọng: tiến độ, model xuất hiện với nguồn "máy chủ", "đã xác minh"; (2) tải tiếp được; (3) từ chối với lý do.

## I. Chạy model

**AT-57 (F-45, NFR-14) Nhập model** · [Vendor]
1. Nhập gói zip. 2. Nhập thư mục `pretrained_model` bằng đường dẫn trong home; đường dẫn `C:\Windows` /
`/etc`. 3. Nhập zip có `../` và zip chứa `*.pt`. 4. `curl -X POST -H 'X-Station: 1' -H 'Authorization: Bearer
<token>' --data 'abc' http://127.0.0.1:18210/api/v1/models/import`.
Kỳ vọng: (1) "đã xác minh"; (2) "chưa xác minh"; ngoài thư mục cho phép → "Đường dẫn này không được phép…";
(3) từ chối với lý do; không tệp nào ghi ra ngoài kho model; (4) 4xx có `code`, không 500 (D-16).

**AT-58 (F-46) Tương thích và sửa một cú bấm** · [Vendor]
1. Chọn model cần camera `front` 640×480 khi camera là 320×240. 2. Bấm "Đặt front thành 640×480".
3. Model cần `wrist` mà hồ sơ có `cam1`: chọn tương ứng.
Kỳ vọng: danh sách kiểm có mục "có vấn đề" với lý do; sau sửa → "ổn"; không bao giờ tự resize; bắt đầu chạy kiểm
lại.

**AT-59 (F-47) Nạp model** · [Vendor] + [UAT-KH]
1. Nạp với Tự động. 2. Nạp với CPU. 3. [Vendor] Tắt mạng (`unshare -n` hoặc rút mạng), nạp một model SmolVLA
chưa có backbone trong cache.
Kỳ vọng: "Đã nạp trên <thiết bị> trong X giây · khởi động Y ms"; một model tại một lúc; "Chạy trên robot" bị
tắt khi chưa nạp ("Hãy nạp model trước."); (3) "Model này cần tải thành phần từ Internet ở lần nạp đầu", không lỗi
thô (D-23).

**AT-60 (F-48) Chạy model trên robot** · [UAT-KH] (video) + [Vendor] (mock)
1. Chạy 2 tập × 20 s; lần đầu đánh dấu xác nhận e-stop phần mềm. 2. Quan sát màn hình. 3. Bấm Tiếp ở tập 1;
Dừng ở tập 2.
Kỳ vọng: đếm ngược 3 s; mọi camera với nhãn "đầu vào policy · W×H → w×h" và tick tăng; khớp đo được / lệnh /
đã gửi + biểu đồ 10 s; FPS, suy luận p50 / p95, % cắt; nút DỪNG 128 px; Tiếp / Dừng đúng; robot chuyển động
theo model.

**AT-61 (F-48) Model quá chậm khi đang chạy** · [Vendor]
1. Chạy test tự động của phiên chạy model với policy giả có suy luận 200 ms ở 30 fps (`tests/test_sessions.py`;
nếu chưa có test tên riêng, Tech Lead thêm ở M1 và ghi tên vào đây).
Kỳ vọng: sau 5 s phiên tạm dừng với "Model quá chậm cho fps này trên máy này. Hãy giảm fps hoặc dùng CUDA.";
không lệnh cũ nào được gửi dồn.

**AT-62 (F-49) Dataset đánh giá** · [Vendor]
1. `--mock`: chạy model với "Ghi bộ dữ liệu đánh giá", 2 tập. 2. Mở dataset bằng lerobot 0.7.1 như AT-49.
Kỳ vọng: dataset `eval_…` mở được bằng lerobot, đúng 2 tập, có telemetry trong `eval_….hibiscus/`.

**AT-63 (F-50) Tóm tắt lượt chạy** · [Vendor]
1. Sau AT-60. Kỳ vọng: thời lượng, số tập, số cảnh báo, nhiệt cao nhất từng khớp, liên kết telemetry và dataset
đánh giá; số liệu khớp với trang Phiên.

**AT-64 (F-51) Trang Model** · [Vendor]
1. Model → Chạy một model; Xoá một model. Kỳ vọng: mở Chạy model với model đó; xoá cần xác nhận, model đang nạp
được gỡ trước.

## J. Chương trình

**AT-65 (F-52) Ghi và cắt quỹ đạo** · [Vendor] + [UAT-KH]
1. Chương trình → Quỹ đạo → Ghi (tên "A", 20 s); dừng sớm. 2. Dùng gợi ý cắt; chỉnh cắt; Lưu. 3. Ghi "B", Bỏ.
4. Hồ sơ không có leader.
Kỳ vọng: đếm ngược, "Đang ghi · X / 20 s · N mẫu"; vùng xám, gợi ý đúng đoạn đứng yên, "Giữ X s trên Y s"; A ở
"Sẵn sàng"; B không lưu; (4) "Robot này không có tay leader…".

**AT-66 (F-53) Phát quỹ đạo** · [Vendor] + [UAT-KH] (video)
1. Đặt tay cách điểm đầu > 30°; phát A 100 %. 2. Phát 10 %, 150 % (hồ sơ chưa bật). 3. E-stop giữa lúc về điểm đầu
và giữa lúc phát.
Kỳ vọng: đi chậm về điểm đầu rồi phát; 10 % chậm đúng; 150 % bị từ chối "Robot này chưa bật tốc độ trên 100 %."; (3)
dừng trong một nhịp, không chuyển động lại tới khi đặt lại.

**AT-67 (F-53, RULE-10) Cần kiểm tra sau hiệu chỉnh lại** · [Vendor]
1. Hiệu chỉnh lại follower. 2. Xem A, tư thế, chương trình dùng A. 3. Chạy chương trình trên robot. 4. "Kiểm tra ở
25 %" → "Đã đúng".
Kỳ vọng: A và tư thế "Cần kiểm tra"; chạy bị từ chối với "Hiệu chỉnh đã thay đổi…"; sau xác nhận chạy được.

**AT-68 (F-54) Tư thế** · [Vendor]
1. Lưu tư thế `home` từ tay; "Lưu điểm đầu làm tư thế" từ A; tên `Home!`. 2. Xoá.
Kỳ vọng: nguồn hiện "từ tay thật" / "đầu quỹ đạo"; tên sai bị từ chối; xoá được.

**AT-69 (F-55) Nhận diện** · [Vendor] + [UAT-KH]
1. Nhận diện → màu trong vùng: vẽ vùng, quy tắc đỏ / xanh; đưa vật đỏ, xanh, bỏ ra. 2. ONNX: tải model + nhãn,
thử. 3. Tải tệp không phải ONNX.
Kỳ vọng: nhãn trực tiếp đổi đỏ → xanh → không có trong ≤ 0,5 s; ONNX hiện nhãn và độ tin cậy; (3) "Không dùng
được bộ nhận diện này…".

**AT-70 (F-56, REG-9) Tạo chương trình mới** · [Vendor] + [UAT-KH]
1. Hồ sơ mới, chưa có chương trình: bấm "Chương trình mới" một lần, hai lần. 2. Tên "Gắp đỏ", rồi "抓取"; lưu.
3. Giả lập danh sách đang tải và lỗi; bấm lại. 4. Robot đang e-stop: mở danh sách. 5. Kéo khối "khi chương
trình bắt đầu" + "phát quỹ đạo A ở 50 %", lưu; thêm khối thiếu tham số, Kiểm tra. 6. Chưa có hồ sơ hoạt động.
Kỳ vọng: mỗi lần bấm form mở và con trỏ ở ô tên; tên không Latin lưu được với mã ổn định; form nói lưu cho hồ sơ
nào; lỗi danh sách + "Thử lại"; danh sách trả lời khi e-stop; khối lỗi được đánh dấu với lý do; (6) form báo
chưa có hồ sơ.

**AT-71 (F-57) Chạy thử bắt buộc** · [Vendor]
1. Chương trình "đỏ → A, xanh → B": bấm Chạy trên robot. 2. Chạy thử, giả lập "camera thấy đỏ", rồi "xanh".
3. Chạy trên robot. 4. Sửa một khối, lưu, Chạy trên robot.
Kỳ vọng: (1) chặn "Chạy trên robot cần phiên bản này đã chạy thử thành công."; (2) nhánh đúng chạy trên tay giả
lập, tay thật không chuyển động; (3) được phép; (4) bị chặn lại.

**AT-72 (F-58, NFR-7, REG-10) Chạy trên robot, e-stop, chạy lại** · [UAT-KH] (video) + [Vendor]
1. Chạy chương trình có khối hỏi người vận hành và chờ phím; trả lời bằng bảng người vận hành. 2. Tạm dừng,
Tiếp tục. 3. Giữa một chuyển động nhiều khớp bấm Space; Thả lỏng; Đặt lại. 4. Chạy lại. 5. Xem nhật ký và
lịch sử lần chạy. 6. [Vendor] hạ ngưỡng nhiệt, chạy tới khi kích hoạt.
Kỳ vọng: trạng thái hiện khối đang chạy và "đang chờ …"; (3) dừng trong một nhịp, lần chạy kết thúc `estopped`,
có "Về tư thế nghỉ"; (4) đi về điểm đầu rồi chạy từ đầu, không khớp nào bị kéo về đích cũ; (5) nhật ký và lần
chạy có đủ; (6) dừng một nhịp, về nghỉ, tắt mô-men, lần chạy `estopped`.

**AT-73 (F-59) Tín hiệu ngoài** · [Vendor] (broker MQTT thử, ví dụ mosquitto trên 127.0.0.1; máy nhận webhook thử)
1. Chương trình chờ "tín hiệu door = open". 2. `curl -X POST -H 'Authorization: Bearer <token>' -H 'X-Station: 1'
-H 'Content-Type: application/json' http://127.0.0.1:18210/api/v1/signals/door -d '{"value":"open"}'`; lặp lại
không token. 3. MQTT: cấu hình broker, `mosquitto_pub` vào topic đã cấu hình. 4. Khối thông báo với webhook trỏ
tới máy nhận thử.
Kỳ vọng: chương trình tiếp tục khi nhận tín hiệu; không token bị từ chối `401`; MQTT cũng vậy; máy nhận thử ghi
được một POST.

**AT-74 (F-60) Chạy model trong chương trình** · [Vendor]
1. `--mock`: khối "chạy mô hình M nhiệm vụ T trong 10 s", rồi "… đến khi kẹp đang giữ vật (hết giờ 20 s)"; chạy
thử (giả lập "kẹp giữ vật" ở bảng điều kiện), chạy trên tay giả lập. 2. Chạy
`tests/test_programs_safety.py::test_estop_during_run_model`, `tests/test_program_session.py::test_run_model_block_uses_the_inferring_path`. Kỳ vọng: model chạy đúng thời gian / tới khi điều kiện; hết giờ thì sang khối sau; an toàn của
F-48 áp dụng (e-stop, dead-man).

## K. Robot 3D

**AT-75 (F-61) Robot 3D** · [Vendor] + [UAT-KH]
1. Robot → Robot 3D; thả lỏng, xoay `wrist_roll` một phần tư vòng; đặt tay ở tư thế giữa. 2. Kéo xoay, phóng to,
Đặt lại góc nhìn, Ẩn / Hiện. 3. [Vendor] `POST /api/v1/mock/inject {"motor":"elbow_flex","temp_c":61}`.
4. [Vendor] Mở Station trong Chrome chạy với `--disable-webgl` (hoặc Firefox `webgl.disabled = true`).
Kỳ vọng: tay 3D cùng chiều, lệch < 5° mỗi khớp (so bằng mắt với tay thật / số khớp trên bảng); điều khiển góc nhìn
chạy; (3) khuỷu màu cam, tooltip "<động cơ>: 61 °C, Nóng"; (4) ẩn với "Trình duyệt này không vẽ được 3D…".

**AT-76 (F-62) Xem trước bằng tay mờ** · [Vendor] + [UAT-KH]
1. Quỹ đạo A → Xem 3D → Phát xem trước; kéo vị trí. 2. Phát A thật.
Kỳ vọng: tay mờ chạy cạnh tay đặc, "t / tổng giây"; chuyển động cùng chiều và thứ tự khớp như lúc phát thật.

## L. Chẩn đoán

**AT-77 (F-63, REG-2, REG-13) Doctor** · [Vendor] + [UAT-KH] (UAT-0)
1. Station tắt, hai tay cắm: `hibiscus-station doctor --verbose`. 2. Mở zip; tìm chuỗi `hbp_` và token cục bộ
(nội dung tệp `token` trước khi tắt). 3. Có hồ sơ demo hoạt động và cổng thật: chạy lại. 4. `--no-ping
--no-cameras`. 5. [Vendor] Tắt Station bằng `kill -9` (để `station.pid` còn), chạy `doctor`. 6. [Vendor] Một
chương trình khác giữ cổng của tay, chạy `doctor`.
Kỳ vọng: đầu báo cáo là LIKELY PROBLEMS khi có vấn đề, hoặc dòng "No likely problems found" (FL-11); có phiên
bản (Station, lerobot), cổng (VID:PID, ai giữ), camera, tệp hiệu chỉnh, hồ sơ, 200 dòng log, kiểm tra từng tay
(id, firmware, điện áp, nhiệt, **dòng, tải**, trạng thái, EEPROM so với tệp, độ trễ đọc, ước lượng teleop) và bản
dump thô từng servo (K-11, SP-1); (2) không tìm thấy; log lệnh (giả lập) không có lệnh ghi nào; (3) `MOCK PROFILE
ACTIVE …`; (4) không mở cổng / camera; (5) "Station is not running", không "ConnectError" (D-15); (6) cổng đó nằm
trong LIKELY PROBLEMS (D-15); với bộ chuyển WCH lời khuyên không nhắc "latency timer" (D-21).

**AT-78 (F-64, REG-18) Nhật ký** · [Vendor] + [UAT-KH]
1. Chạy `hibiscus-station -v`; tạo dataset tên có dấu; rút USB một lần. 2. Mở `station.log`.
Kỳ vọng: dòng khởi động (chế độ, thư mục, hồ sơ); lỗi bus có thao tác, thanh ghi, id; UTF-8, tiếng Việt đúng;
không dòng thời gian mỗi nhịp; không lỗi mã hoá trên console Windows.

**AT-79 (F-65) Health** · [Vendor]
1. Station đang chạy: `hibiscus-station health; echo $?`. 2. Tắt Station, chạy lại lệnh, đo thời gian.
Kỳ vọng: (1) 0; (2) khác 0 trong ≤ 5 s.

## M. Cài đặt, ngôn ngữ, giao diện

**AT-80 (F-66) Cài đặt** · [Vendor]
1. Đặt ngưỡng nguy hiểm 69 khi động cơ tự ngắt 70; nóng 64 khi nguy hiểm 65; ấm 58 khi nóng 60. 2. Đặt hợp lệ, lưu.
3. Đổi rộng xem trước 640, fps 30. 4. Xem dòng phiên bản.
Kỳ vọng: (1) mỗi lỗi có câu tiếng Việt tương ứng, có đơn vị "°C", không dòng tiếng Anh hiện sẵn (D-5), không lưu; (2)
"Đã lưu."; (3) xem trước đổi; (4) phiên bản Station đúng, lerobot là phiên bản thực đã cài.

**AT-81 (F-67, NFR-10) Song ngữ** · [Vendor]
1. Trình duyệt tiếng Việt: mở Station. 2. Trình duyệt `en-US`. 3. Đổi ngôn ngữ trên thanh trên ở giữa phiên
teleop. 4. Kiểm bộ khoá `vi` và `en`.
Kỳ vọng: (1) tiếng Việt; (2) English; (3) đổi ngay không tải lại, phiên không bị ảnh hưởng; (4) cùng bộ khoá,
không khoá trống.

**AT-82 (F-68, NFR-11) Chủ đề và bề rộng** · [Vendor]
1. Chạy bộ ma trận ảnh Playwright + axe trong CI (mọi trang × trạng thái trống / đang tải / lỗi / thành công / bị
tắt có lý do × sáng / tối × 1280 / 390 px; FL-7). 2. QC xem tay mẫu cố định: Robot, Hiệu chỉnh, Teleop, Ghi, Chạy
model, Chương trình ở trạng thái lỗi và trống, hai chủ đề, hai bề rộng.
Kỳ vọng: trang không cuộn ngang (bảng rộng / canvas cuộn trong khung riêng); không chữ bị cắt (D-14); nút DỪNG
không che nội dung (D-13); tương phản AA (axe 0 lỗi); mỗi trạng thái có thiết kế.

**AT-83 (F-68, NFR-11) Bàn phím** · [Vendor]
1. Chỉ dùng bàn phím (`--mock`): Tab qua thanh bước, "Bỏ qua, tới nội dung", tạo hồ sơ, kết nối, hiệu chỉnh,
camera, teleop, Space e-stop, đặt lại, ghi với → / ← / Esc, chạy model, chạy và dừng một chương trình có sẵn.
Kỳ vọng: đi hết luồng chính (NFR-11), focus luôn thấy rõ, mọi điều khiển có nhãn; trình soạn khối không bắt buộc
bàn phím.

## N. Cập nhật và dữ liệu

**AT-84 (F-69) Cập nhật và quay lại trên Windows** · [UAT-KH] (+ [Vendor] VM Windows sạch và Linux)
Tiền điều kiện: bản cũ (0.2.8) đã dùng: có hồ sơ, hiệu chỉnh, dataset, model, quỹ đạo, chương trình.
1. Dán lệnh cập nhật trong ghi chú phát hành (QĐ-3 = A: cùng lệnh cài một dòng). 2. Mở Station, kiểm mọi thứ.
3. Dán lệnh quay lại trong hướng dẫn (cùng lệnh kèm số phiên bản), kiểm lại. 4. [Vendor] So bộ thư viện sau
bước 3 với bộ của bản cũ.
Kỳ vọng: phiên bản mới hiện ở Cài đặt; mọi dữ liệu còn và dùng được (kết nối không cần hiệu chỉnh lại, quỹ đạo
phát được); quay lại bản cũ cũng vậy; (4) trùng 100 %.

**AT-85 (F-70) Docker backup / update / rollback** · [Vendor] (máy Linux x86_64 riêng, image `-cpu`)
1. `hibiscus-station-ctl backup`; `update <tag mới>`; `rollback`. 2. Dựng một tag thử có HEALTHCHECK luôn thất
bại, `update <tag đó>`.
Kỳ vọng: có tệp sao lưu; tag mới healthy; rollback về tag cũ, dữ liệu nguyên; (2) tự quay lại.

**AT-86 (F-71, NFR-15, NFR-16) Dữ liệu bền và ngoại tuyến** · [Vendor]
1. Chạy Station không mạng (`unshare -rn hibiscus-station --mock …` hoặc rút mạng); đi hết Robot → Hiệu chỉnh →
Camera → Teleop → Ghi → Chạy model (zip, model ACT) → Chương trình. 2. Script: lặp 50 lần { lưu hồ sơ qua API, `kill
-9` tiến trình sau 0–50 ms ngẫu nhiên, khởi động lại, đọc `robots.yaml` }. 3. Kiểm quyền tệp `token`,
`robots.yaml` (Linux).
Kỳ vọng: (1) mọi bước chạy không Internet; (2) 50 / 50 lần `robots.yaml` đọc được (bản cũ hoặc mới, không nửa
vời); (3) 0600.

## Các AT cho NFR

**AT-87 (NFR-5) Thời gian khởi động** · [Vendor] + [UAT-KH]
1. Lần chạy **thứ hai** sau cài (không camera): đo từ Enter tới khi trang Chào mừng tải xong. 2. Kết nối hồ sơ
không camera, đo. 3. [UAT-KH] Thêm camera, kết nối lại, ghi thời gian mở camera (không có đích).
Kỳ vọng: Windows của khách ≤ 15 s; Linux vendor ≤ 10 s; kết nối ≤ 5 s; (3) số đo được ghi lại.

**AT-88 (NFR-3a, NFR-3b) Đo thời gian e-stop** · [Vendor]
1. Giả lập pty có thời gian thật: 10 lần e-stop trong teleop nhanh và 10 lần trong phát quỹ đạo; đếm lệnh ghi
vị trí trong log lệnh của `sts_emulator` sau nhịp nhận e-stop. 2. Chạy model với policy giả (suy luận 100 ms), 10
lần e-stop. 3. Playwright: 100 lần phím Space trên trang Teleop (`--mock`), so dấu thời gian trình duyệt với dòng
log máy chủ nhận e-stop.
Kỳ vọng: (1) 20 / 20: 0 lệnh vị trí sau ≤ 1 nhịp; (2) 10 / 10: 0 lệnh mới sau ≤ 1 nhịp + 1 lần suy luận; (3) p99
≤ 50 ms.

**AT-89 (NFR-1b, NFR-2, REG-19) Nhịp vòng 10 phút** · [UAT-KH] (+ [Vendor] Linux giả lập)
1. Teleop 10 phút; ghi 10 tập × 30 s ở 30 fps. 2. Mở Phiên → từng phiên, ghi `loop.fps`, p95 thời gian nhịp, tỉ lệ
nhịp trễ, `telemetry_forced`; ghi số `doctor` "ms mỗi lần đọc".
Kỳ vọng: teleop ≥ 100 Hz khi bus ≤ 3 ms mỗi lần đọc (chậm hơn: theo NFR-2 và đích chốt sau UAT-0); ghi 30 fps:
p95 ≤ 36 ms, nhịp trễ < 1 %, `telemetry_forced` < 1 %.

**AT-90 (NFR-8) Phiên dài** · [Vendor] (job `slow` hằng đêm)
1. Giả lập pty có thời gian thật, tay leader giả chuyển động liên tục: teleop 30 phút rồi ghi 20 tập liên tục;
ghi RSS tiến trình mỗi phút (`ps -o rss`) và `loop.fps` từ tóm tắt phiên. Kỳ vọng: bộ nhớ tăng ≤ 20 %, fps
giảm ≤ 10 %, không treo, không lỗi.

**AT-91 (NFR-10) Không lẫn ngôn ngữ** · [Vendor]
1. Chạy kiểm chuỗi tự động: khoá `vi` = `en`, không khoá trống, không chuỗi chứa "Hiệu chuẩn" / "reset". 2. Ở tiếng
Việt, ma trận ảnh của AT-82 cộng mọi thông báo lỗi gây được (danh sách `errors.*`, `lost.*`, cảnh báo). 3. Chạy
`hibiscus-station` trong PowerShell / terminal tiếng Việt: khởi động, chạy lần hai, cổng bận.
Kỳ vọng: (1) xanh; (2) 0 câu tiếng Anh trên giao diện ngoài thuật ngữ đã thống nhất và mục "Chi tiết kỹ thuật"
thu gọn; một thuật ngữ cho một khái niệm (Q-8); không lỗi chính tả; (3) các dòng đó bằng tiếng Việt hoặc song
ngữ (NFR-10).

**AT-92 (NFR-12, FR-73) Thông tin đúng, không chữ thô** · [Vendor] + [UAT-KH] (quan sát suốt UAT-1)
1. Rà mọi màn hình với tay giả lập (ma trận ảnh AT-82, tìm `undefined`, `NaN`, `internal_error`, `[object`) và
(UAT) tay thật trong 30 phút teleop. 2. Gây từng lỗi: cổng bận, mất USB,
token sai, model không tương thích, dataset chưa hoàn tất. Kỳ vọng: mọi số có đơn vị đúng, trong dải hợp lý; 0
placeholder / debug / stack trace / `internal_error` thô; 0 cảnh báo giả; mỗi lỗi có câu dịch và đường thoát.


## Các AT thêm ở v0.2 (đã duyệt ở v1.0)

**AT-93 (F-33, F-32, NFR-6, QĐ-1, P-3) Chạy khi không đọc được nhiệt độ** · [Vendor] + [UAT-KH] (tay của khách nếu vẫn báo 0 °C)
Theo QĐ-1 = A (đã chốt 2026-11-17).
0. [Vendor] Mở Cài đặt, xem giới hạn thời gian khi không đọc được nhiệt độ.
1. [Vendor] `--mock`: inject `{"port":"mock://follower","temp_c":0}` cho cả 6 động cơ follower; Kết nối.
2. Trong hộp xác nhận, bấm "Ngắt kết nối"; kết nối lại, bấm "Tôi hiểu, tiếp tục". 3. Xem các màn hình Teleop,
Ghi, Chạy model, Chương trình. 4. [Vendor] Đặt giới hạn thời gian trong Cài đặt còn 60 s; chạy model (giả) và
phát một quỹ đạo, mỗi cái liên tục quá 60 s. 5. Đặt lại; teleop 2 phút (quá 60 s). 6. [UAT-KH] Trên tay của
khách: lặp bước 1 – 3 (không cần inject), chạy model 1 tập ngắn.
Kỳ vọng: (0) mặc định 10 phút; (1) hộp xác nhận "Không đọc được nhiệt độ động cơ: bảo vệ nhiệt của Station đang tắt…"; (2) "Ngắt kết
nối" về Chưa kết nối, "Tôi hiểu, tiếp tục" về Sẵn sàng; hộp hiện lại ở **mỗi** lần kết nối; (3) banner cam cố
định trên mọi màn hình chuyển động; (4) sau 60 s phiên dừng an toàn với lý do "chạy quá giới hạn khi không đọc
được nhiệt độ", đặt lại được ngay; (5) teleop không bị dừng; (6) như (1) – (3).

**AT-94 (F-13, F-28, NFR-7, C-4) Mất nguồn follower giữa chuyển động** · [Vendor] + [UAT-KH] (công tắc ngắt nguồn)
1. [Vendor] Giả lập pty: teleop, rồi cho giả lập follower ngừng trả lời mọi servo (dừng luồng trả lời nhưng giữ
pty mở: bộ chuyển USB vẫn cắm, chỉ servo mất nguồn). 2. [UAT-KH] Teleop; tắt công tắc nguồn follower giữa chuyển
động (đỡ tay). 3. Bật lại nguồn; làm theo lối ra trên trang.
Kỳ vọng: trong ≤ 2 s trạng thái lỗi bằng tiếng Việt nói rõ không có phản hồi từ động cơ của Tay follower (kiểm
nguồn), không treo, không vòng thử lại vô hạn, nút điều khiển chuyển động tắt; (3) Kết nối lại (hoặc Ngắt kết nối
→ Kết nối) đưa về Sẵn sàng không khởi động lại Station; hiệu chỉnh không đổi.

**AT-95 (F-4, F-38, FR-75, D-19, P-6) Đóng cửa sổ PowerShell khi tay đang chạy** · [UAT-KH] (+ [Vendor] Ctrl+C / SIGTERM trên Linux)
1. Teleop, đóng cửa sổ PowerShell đang chạy Station (nút X). 2. Mở lại Station (cùng lệnh), kết nối. 3. Ghi
dataset 3 tập; giữa tập 3, đóng cửa sổ. 4. Mở lại, mở Bộ dữ liệu. 5. [Vendor] Lặp 1 – 4 bằng Ctrl+C và `kill
-TERM` trên Linux.
Kỳ vọng: (1) trong ≤ 4 s follower giữ rồi tắt mô-men theo hồ sơ (đỡ tay trước nếu hồ sơ là "thả lỏng"); không
giật; (2) không "cổng bận", kết nối được; (4) dataset mở được, 2 tập đã lưu còn nguyên (tập 3 dở có thể mất, đúng
FR-75); (5) như trên, thêm: về tư thế nghỉ theo hồ sơ, tập dở được `finalize`.

**AT-96 (F-12, D-22, P-7) Cổng bị tiến trình khác giữ trên Linux** · [Vendor]
1. Giả lập pty cho follower; một tiến trình khác mở cổng đó trước (`python -c "import serial,time;
s=serial.Serial('<pty>',1000000); time.sleep(600)"`). 2. Kết nối trong Station. 3. Dừng tiến trình kia; Kết nối.
Kỳ vọng: (2) từ chối `port_busy`, câu tiếng Việt nêu tên tiến trình (ví dụ "python (pid N) đang dùng cổng…"),
Station không gửi gói nào lên cổng (log giả lập trống); (3) kết nối được.

**AT-97 (F-47, F-48, NFR-4, D-20, P-2) Model quá chậm cho dead-man** · [Vendor]
1. `--mock` với một policy giả có suy luận khởi động 800 ms (Tech Lead cung cấp công cụ ở M1). 2. Nạp; xem
Chạy trên robot. 3. Gọi API bắt đầu chạy. 4. Policy giả 200 ms: nạp, chạy, đóng tab giữa chừng.
Kỳ vọng: (2) "Chạy trên robot" tắt với "Model quá chậm trên máy này cho an toàn dead-man. Dùng CUDA hoặc model
nhỏ hơn"; (3) bị từ chối với mã lỗi tương ứng; (4) chạy được; đóng tab → `estopped(ui_lost)` trong ≤ 1,0 s + 1
nhịp + 1 lần suy luận.

**AT-98 (F-6, NFR-14, QĐ-4) Giấy phép và cảnh báo bảo mật** · [Vendor] (QC + Security / Legal)
1. Cài bản ứng viên như AT-1 (VM), xuất danh sách gói và giấy phép từ metadata (`uv pip list --python … --format
json` + trường `License` / classifier của từng gói). 2. So với bảng giấy phép ARCHITECTURE §2. 3. Xem cấu hình
`pnpm audit` / các GHSA bị bỏ qua trong `web/package.json` và kết quả CodeQL, gitleaks, Trivy của commit phát hành.
Kỳ vọng: (1–2) mọi gói có giấy phép tương thích AGPL-3.0, gồm `hibiscus` = Hibiscus CLI **v0.1.2, Apache-2.0** có tệp LICENSE (QĐ-4 = A, EXT-1), khớp bảng; (3) mỗi GHSA bị bỏ
qua có lý do ghi lại (hoặc đã nâng cấp), 0 phát hiện mở; tệp LICENSE / ghi công có trong wheel.

---

## Ký xác nhận

| | Người | Ngày | Phiên bản | Kết quả |
|---|---|---|---|---|
| QC (nội bộ) | | | | |
| Khách hàng (UAT) | | | | |

## Kế hoạch UAT của khách hàng (ba buổi ngắn, SA-Q1, FL-6; đã duyệt ở v1.0)

Vendor chạy mọi phần [Vendor] trước (QC nội bộ, kèm video màn hình để khách xem nếu muốn). Khách chỉ chạy những gì
**chỉ Windows + tay SO-101 thật** chứng minh được. Không cần nhiệt kế, đồng hồ vạn năng hay máy quay tốc độ cao.
Mỗi lỗi khách thấy thành một D-n mới (sửa → QC → UAT lại đúng bước đó, không chạy lại cả buổi trừ khi bản sửa
chạm phần chung). Khách đã duyệt kế hoạch ba buổi (2026-11-17); ngày cụ thể hẹn khi bản M0 sẵn sàng.

**UAT-0 · khoảng 15 phút · ngay sau M0.** Cài bản M0 (AT-1); cắm hai tay; tắt Station và LeLab; chạy
`hibiscus-station doctor --verbose`, gửi tệp zip (AT-77); mở Feetech FD, chụp màn hình nhiệt độ / điện áp / dòng
của một servo follower. Mục đích: đóng REG-13 / SP-1 (servo có báo nhiệt thật không; nếu không thì áp QĐ-1 A, AT-93), lấy số đo bus của PC khách cho D-9 / NFR-2.
Không thử tính năng.

**UAT-1 · khoảng 60 – 90 phút · sau M1 (các tính năng Must).** Mười sáu bước (bước 16: CR-1); trong suốt buổi khách để ý số liệu
và chữ trên màn hình (AT-92).

| # | Khách làm | AT |
|---|---|---|
| 1 | Dán lệnh cài một dòng; `hibiscus-station --version` | AT-1 |
| 2 | Chạy Station, trình duyệt mở tiếng Việt; tắt, chạy lại, đo thời gian | AT-5, AT-87 |
| 3 | Tạo hồ sơ; "Tìm tay follower" / "Tìm tay leader" (cử động, rút cáp); xem gợi ý điện áp, thử Đổi chỗ | AT-11, AT-13 – AT-15 |
| 4 | Mở LeLab giữ follower → Kết nối (cổng bận) → đóng LeLab → Kết nối; xem danh sách cổng; mô-men và tư thế nghỉ | AT-12, AT-16, AT-17, AT-20 |
| 5 | Hiệu chỉnh: dùng tệp LeLab (nếu có) hoặc luồng đầy đủ cả hai tay; Kiểm tra hai tay | AT-22, AT-23, AT-26 |
| 6 | Tắt Station, teleop bằng LeLab với cùng mã tay; hiệu chỉnh một tay bằng LeLab rồi mở trong Station | AT-27 |
| 7 | Camera: Quét lại, Thử; thêm `front`; (nếu có hai webcam) cắm lại và Thử từng camera | AT-28, AT-29 |
| 8 | Teleop 2 phút, rồi cùng động tác bằng LeLab; leader xa → "Đưa tay follower về tư thế tay leader" | AT-31, AT-33 |
| 9 | Space khi teleop (và khi đang ở cửa sổ khác); Space lần hai → đỡ tay; Đặt lại; tắt công tắc nguồn follower giữa chuyển động | AT-36, AT-37, AT-94 |
| 10 | Teleop, rút USB follower, cắm sang ổ USB khác, Kết nối lại | AT-18 |
| 11 | Ghi 3 tập bằng phím → / ← / Esc; rút camera giữa một tập; bóp kẹp vào vật | AT-30, AT-44, AT-48 |
| 12 | Nhập model zip, nạp, chạy 2 tập; Space giữa tập → Đặt lại → "Về tư thế nghỉ"; chạy lại, đóng tab giữa chừng | AT-38, AT-45, AT-59, AT-60 |
| 13 | So nhiệt độ / điện áp / dòng với Feetech FD; nếu không đọc được nhiệt độ: hộp xác nhận, banner, dừng sau 10 phút khi không cầm leader (QĐ-1 A); nếu đọc được: dừng nhiệt với ngưỡng hạ | AT-40, AT-42 hoặc AT-93 |
| 14 | Đóng cửa sổ PowerShell khi đang teleop, rồi khi đang ghi; mở lại | AT-95 |
| 15 | Teleop 10 phút + ghi 10 tập (có thể chạy trong lúc làm bước 11); cập nhật / quay lại bằng lệnh một dòng; xem `station.log` | AT-78, AT-84, AT-89 |
| 16 | (CR-1) Bộ dữ liệu → dataset của bước 11 → bấm một tập: video mọi camera trên **Edge cài sẵn** (không cài AV1 Video Extension), rồi Chrome, Firefox; Phát / Tạm dừng / kéo / bấm biểu đồ | AT-99 |

**UAT-2 · khoảng 45 phút · sau M2 (Should).** Phát lại tập (AT-35); ghép nối máy chủ nếu có tài khoản (AT-52); ghi
và phát quỹ đạo (AT-65, AT-66); nhận diện màu (AT-69); tạo chương trình, chạy thử, chạy trên robot, e-stop, chạy
lại (AT-70, AT-72); Robot 3D và xem trước tay mờ (AT-75, AT-76). Có thể gộp vào cùng buổi với UAT-1 nếu M2 xong kịp.

**AT chỉ khách chứng minh được** (NOT VERIFIED ở QC nội bộ cho tới UAT): AT-1, AT-14, AT-17, AT-18, AT-23, AT-27
(phần LeLab), AT-40, AT-84, AT-93 (phần tay của khách), AT-94 (phần công tắc), AT-95, AT-99 (bước 8: Edge cài sẵn của khách). Các AT còn lại trong bảng trên:
QC chạy phần [Vendor] trước, khách chạy lại trên PC của mình.
