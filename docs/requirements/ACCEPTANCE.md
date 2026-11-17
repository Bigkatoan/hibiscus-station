# Hibiscus Station: tài liệu nghiệm thu v0.1 (2026-11-17) · trạng thái: bản nháp (vòng 1)

BA viết; QC rà soát trước khi duyệt ("kiểm được như đã viết không?"); QC chạy sau khi xây. Mỗi AT kiểm
một tính năng F-n trong [FEATURES.md](FEATURES.md) hoặc một NFR trong [SRS.md](SRS.md). Danh sách hồi quy
[REGRESSION.md](REGRESSION.md) chạy cùng.

## Môi trường

* **Bản kiểm:** đúng tệp người dùng cài: wheel `hibiscus_station-<v>-py3-none-any.whl` của bản ứng viên
  (cài bằng lệnh trong README của chính bản đó); Docker image cùng phiên bản cho AT Docker.
* **Nền tảng:**
  * **[Vendor]**: Linux x86_64 (Ubuntu 24.04) với `--mock`, giả lập STS3215 (`tests/sts_emulator.py`,
    pty, thời gian thật), camera giả lập / webcam; CI `windows-latest` và macOS (không có tay).
  * **[UAT-KH]**: chỉ UAT của khách hàng chứng minh được: PC Windows 10/11 x64 của khách + SO-101
    leader + follower thật + camera USB thật. Nhà cung cấp không có Windows và tay thật, nên các AT này là
    **NOT VERIFIED** ở QC nội bộ và chỉ đạt khi khách hàng chạy (hoặc xem video) và ghi kết quả.
  * Một AT có cả hai nhãn: QC chạy phần [Vendor] trước; khách hàng chạy lại trên nền tảng của mình.
* **Dữ liệu thử:** hồ sơ `desk_so101`; tệp hiệu chỉnh LeLab mẫu (`so_101_follower.json` /
  `so_101_leader.json`); model ACT nhỏ (gói zip) và một thư mục `pretrained_model`; máy chủ Hibiscus thử
  v0.1.1 với token có `datasets:write`, `models:read`, `runs:read` (cho F-41 – F-44).
* **Bằng chứng giữ lại:** ảnh chụp (đánh số theo AT), video khi ghi chú "video", `station.log`, thư mục
  phiên, zip `doctor` khi AT yêu cầu.
* **Kết quả:** PASS / FAIL / NOT VERIFIED (lý do) · người kiểm · ngày · phiên bản. Một AT FAIL = tính
  năng FAIL (quy tắc zero-defect).

Viết tắt: "Space" = phím cách; "≤ N s" đo bằng đồng hồ hoặc dấu thời gian log.

---

## A. Cài đặt và khởi động

**AT-1 (F-1, REG-1) Cài đặt sạch trên Windows** · [UAT-KH]
Tiền điều kiện: Windows 10/11 x64 chưa từng cài Station, chưa có uv; tay chưa cắm.
1. Mở PowerShell (không cần admin), dán lệnh cài uv trong README tiếng Việt.
2. Dán lệnh cài Station (có `--torch-backend cpu` nếu máy không có GPU NVIDIA).
3. Gõ `hibiscus-station --version`.
Kỳ vọng: cả hai lệnh xong không lỗi; in đúng phiên bản bản ứng viên; không cần gõ thêm lệnh nào khác;
hướng dẫn tiếng Việt đủ để làm mà không cần hỏi. Bằng chứng: ảnh PowerShell.

**AT-2 (F-1, NFR-18, REG-17) CI trên Windows / macOS** · [Vendor]
1. Xem lần chạy CI của commit phát hành.
Kỳ vọng: job `windows-latest` (pytest, build wheel, `uv tool install` + `--mock` smoke, kiểm MIME `.js`)
và macOS install smoke xanh; không test bị bỏ qua để che lỗi. Bằng chứng: liên kết CI.

**AT-3 (F-2) Cài đặt Linux** · [Vendor]
1. Ubuntu 24.04 sạch: cài uv, cài wheel theo README. 2. `hibiscus-station --mock`.
3. (Tuỳ chọn) cài unit systemd trong `deploy/systemd/`, khởi động lại máy.
Kỳ vọng: giao diện mở; với systemd, Station tự chạy và `hibiscus-station health` thoát 0.

**AT-4 (F-3) Docker** · [Vendor] (Linux x86_64; Pi 5 / Jetson: NOT VERIFIED nếu không có máy)
1. `bash install.sh` trên máy sạch, đồng ý cài Docker. 2. `hibiscus-station-ctl status`, `url`, `ports`.
3. Khởi động lại máy chưa cắm tay, cắm tay sau.
Kỳ vọng: image đúng biến thể; `healthy` trong ≤ 3 phút sau khởi động lại; cắm tay sau vẫn kết nối được;
`ports` hiện `/dev/serial/by-id/…` và `/dev/hibiscus/arm-*`.

**AT-5 (F-4, REG-1, REG-17) Khởi động và đăng nhập** · [Vendor] + [UAT-KH]
1. Chạy `hibiscus-station`. 2. Quan sát trình duyệt. 3. Xem thanh địa chỉ và lịch sử.
Kỳ vọng: trình duyệt tự mở trang Chào mừng bằng tiếng Việt (trình duyệt tiếng Việt); không lỗi
`fcntl`; không trang trắng; địa chỉ không còn chứa token; log có dòng khởi động "real hardware".

**AT-6 (F-4) Một phiên bản và liên kết lại** · [Vendor]
1. Khi Station đang chạy, chạy `hibiscus-station` lần hai. 2. Chạy `hibiscus-station url`.
3. Mở liên kết trong cửa sổ ẩn danh.
Kỳ vọng: lần hai in liên kết của bản đang chạy và thoát 0, không mở bản thứ hai; liên kết mới đăng nhập
được; cổng 18210 đã bị chương trình khác giữ → thông báo rõ với gợi ý `--port`.

**AT-7 (F-5, REG-2) Chế độ demo** · [Vendor]
1. `hibiscus-station --mock`. 2. Đi hết Robot → Kết nối → Teleop → Ghi 1 tập. 3. Thoát.
4. Kiểm thư mục `~/.hibiscus/station-demo` và `~/.hibiscus/station`.
Kỳ vọng: chip **TAY GIẢ LẬP** luôn hiện; mọi bước chạy; dữ liệu chỉ nằm trong `station-demo`, thư mục
thật không đổi.

**AT-8 (F-6, NFR-14) Chỉ cục bộ** · [Vendor]
1. Từ máy khác trong LAN mở `http://<ip>:18210`. 2. Trên cùng máy gọi `curl -H 'Host: evil.com'
http://127.0.0.1:18210/api/v1/status`. 3. Gọi `POST /api/v1/estop` không có `X-Station`. 4. Xem log sau khi
ghép nối máy chủ.
Kỳ vọng: (1) không kết nối được; (2) `403 forbidden_host`; (3) bị từ chối (`csrf`); (4) token máy chủ bị
che (`hbp_xxxx…`); `GET /server` không trả token.

**AT-9 (F-6) Chế độ LAN** · [Vendor]
1. `hibiscus-station --host 0.0.0.0` (thiếu token) → quan sát. 2. Đặt `HIBISCUS_STATION_TOKEN` ≥ 32 ký tự và
`--allow-host robot.local`, chạy lại. 3. Mở `http://robot.local:18210` từ laptop; mở bằng IP.
Kỳ vọng: (1) thoát mã 2 với lời giải thích; (3) tên đã khai báo mở được, IP bị `403 forbidden_host`.

**AT-10 (F-7, REG-12) Thanh bước và bước bị khoá** · [Vendor]
1. Chưa có hồ sơ: lần lượt bấm 8 bước trên thanh bước. 2. Gõ thẳng `/run`. 3. Thu hẹp còn 390 px, lặp lại.
4. Kết nối robot, e-stop, bấm Ghi dữ liệu.
Kỳ vọng: bước bị khoá hiện lý do dưới tên; trang "Bước này đang bị khoá" với lý do bằng lời + lý do của
Station + nút "Tới <bước>", mọi nút trên trang tắt; Huấn luyện vẫn có form ghép nối; (4) lý do "Hãy reset
nút dừng khẩn cấp trước"; ✓ xuất hiện đúng khi điều kiện xong.

## B. Robot và cổng

**AT-11 (F-8) Hồ sơ robot** · [Vendor]
1. Robot → Robot mới; điền tên, SO-101, cổng follower, "Không có leader", lưu. 2. Sửa: thêm leader, chọn mã
hiệu chỉnh có sẵn của LeLab, "Về tư thế nghỉ rồi thả lỏng"; lưu. 3. Khi đang teleop thử sửa. 4. Xoá hồ sơ.
Kỳ vọng: lưu / sửa đúng; (3) bị từ chối với lý do; (4) hồ sơ mất, tệp hiệu chỉnh vẫn còn.

**AT-12 (F-9) Danh sách cổng** · [Vendor] + [UAT-KH]
1. Cắm hai bộ chuyển; mở chọn cổng; bấm Làm mới. 2. Mở LeLab giữ một cổng, Làm mới.
Kỳ vọng: chỉ cổng USB serial với mô tả và VID:PID (Windows `COMx`); cổng LeLab giữ hiện "đang dùng bởi …".

**AT-13 (F-10, REG-6) Tìm theo vai trò bằng cử động** · [Vendor] + [UAT-KH]
1. Bấm "Tìm tay follower (cử động)" → Bắt đầu; cử động **leader** trước rồi follower.
2. Bấm "Tìm tay leader (cử động)" → cử động leader. 3. Lặp lại khi không cử động gì 15 s.
Kỳ vọng: (1) ô follower nhận đúng cổng follower trong ≤ 15 s (không lấy cổng leader); (2) không bao giờ đề
xuất cổng đã gán cho follower; (3) "Không tìm thấy", không treo, thử lại được.

**AT-14 (F-10) Tìm bằng rút cáp** · [UAT-KH]
1. "Tìm tay leader (rút cáp)" → Bắt đầu → rút USB leader. 2. Cắm lại.
Kỳ vọng: cổng leader được gán vào ô leader trong ≤ 15 s.

**AT-15 (F-11, REG-6) Gợi ý vai trò và đổi chỗ** · [Vendor] + [UAT-KH]
1. Gán cố ý cổng leader (5 V) vào ô follower và ngược lại. 2. Xem gợi ý dưới cổng. 3. Bấm "Đổi chỗ
follower ⇄ leader".
Kỳ vọng: cảnh báo "Cổng follower đọc 5,0 V: có vẻ đây là tay leader…"; Station không tự đổi; sau Đổi chỗ
hai cổng đổi nhau, mã hiệu chỉnh vẫn theo vai trò; cổng không đọc được → "Không đọc được điện áp…".

**AT-16 (F-12, REG-14) Kết nối và lỗi theo bước** · [Vendor] + [UAT-KH]
1. Kết nối hồ sơ đúng. 2. [Vendor] giả lập 2 % gói hỏng, kết nối 10 lần. 3. [Vendor] giả lập thiếu động cơ
id 4; kết nối. 4. Ngắt kết nối.
Kỳ vọng: (1) tiến trình mở cổng → bắt tay → cấu hình; `Sẵn sàng`, mỗi tay 6 động cơ, có nhiệt độ; ≤ 5 s
(không camera); (2) 10/10 thành công; (3) lỗi nói bước "handshake", động cơ thiếu, bằng tiếng Việt, không
`internal_error`; (4) về Chưa kết nối.

**AT-17 (F-12) Cổng bận** · [UAT-KH]
1. Mở LeLab (hoặc `lerobot-teleoperate`) trên follower. 2. Kết nối trong Station.
Kỳ vọng: "Một chương trình khác (LeLab? lerobot?) đang dùng COMx."; đóng LeLab → Kết nối được ngay.

**AT-18 (F-13, REG-8) Rút USB khi teleop trên Windows** · [UAT-KH] (video)
1. Teleop. 2. Rút USB follower. 3. Đọc trang. 4. Cắm vào cổng USB khác. 5. "Kết nối lại". 6. Teleop.
Kỳ vọng: ≤ 1 s trạng thái lỗi "Mất kết nối USB với Tay follower (COMx)" + danh sách kiểm tra, không có
"Access is denied" thô làm thông báo chính, không 6 lần thử lại; Kết nối lại chờ cổng, nhận số COM mới
("Tay follower giờ ở cổng COMy"), kết nối; teleop chạy lại không khởi động lại Station.

**AT-19 (F-13, NFR-7, REG-8) Mất thiết bị trên giả lập** · [Vendor]
1. Teleop trên giả lập pty. 2. Đóng pty; mở lại dưới tên mới. 3. Kết nối lại.
Kỳ vọng: `error(device_lost)` có tay, cổng, thông báo hệ thống; không torque-off lặp; kết nối lại vào tên
mới; gói tin hỏng đơn lẻ không bị coi là mất thiết bị; hai bộ chuyển giống hệt không serial → yêu cầu chọn.

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

**AT-23 (F-17, REG-4, REG-7) Luồng hiệu chỉnh đầy đủ** · [UAT-KH] (video)
1. Hiệu chỉnh lại follower: Đặt home (tay ở giữa như hình). 2. Bước Biên độ: quay từng khớp, **kể cả
wrist_roll**, hết hành trình. 3. Lưu. 4. Làm tương tự leader. 5. Kiểm tra hai tay → Thử teleop.
Kỳ vọng: mọi khớp hiện `min | vị trí | max`, không có chữ "xoay tròn"; tick khi đủ 100 bước; "Đã xong 6 / 6";
Lưu chỉ mở khi đủ; tệp nằm ở `…\lerobot\calibration\robots\so_follower\<id>.json` có dải wrist_roll đã
ghi; toàn bộ ≤ 3 phút; teleop chạy ngay sau đó.

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
1. Đặt leader giống follower, Kiểm tra. 2. Lệch cố ý một khớp 40°, Kiểm tra. 3. [Vendor] dùng tệp sai cho
leader. 4. [Vendor] đổi cổng hai tay.
Kỳ vọng: (1) "Hai tay khớp nhau (lệch lớn nhất X)" + Thử teleop; (2) khớp đó "lệch hơn 20°" + "Đặt lại tay
leader…"; (3) "có thể đang dùng nhầm tệp hiệu chỉnh" + Hiệu chỉnh lại; (4) "Mọi khớp đều lệch: có thể đã
nhầm cổng…"; luôn có "Vẫn thử teleop".

**AT-27 (F-20) Dùng chung với lerobot** · [UAT-KH]
1. Sau AT-23, chạy `lerobot-teleoperate --robot.type=so101_follower --robot.id=<id> --teleop.id=<id> …`
(Station đã tắt). 2. Dùng tệp do LeLab tạo trong Station.
Kỳ vọng: lerobot chạy không đòi hiệu chỉnh lại; Station hiện vị trí khớp hợp lý (Robot 3D cùng tư thế).

## D. Camera

**AT-28 (F-21, REG-20) Tìm và thử camera** · [Vendor] + [UAT-KH]
1. Camera → Quét lại. 2. Thử từng camera. 3. Thử 1920×1080@30 trên camera USB 2.0.
4. Khi một camera đang được dùng, Quét lại.
Kỳ vọng: mỗi camera một lần (Windows: 0, 1…), có ảnh chụp và fps đo; (3) cảnh báo "Camera chậm hơn yêu cầu…";
(4) camera đó hiện "đang dùng bởi <tên>", không bị mở lại; không có lỗi OpenCV in ra console.

**AT-29 (F-22) Cấu hình và xem camera** · [Vendor] + [UAT-KH]
1. Thêm camera tên `front` 640×480@30 MJPG; thêm `Front!` (tên sai), thêm trùng `front`. 2. Xoay 180°.
3. Mở Teleop, Ghi, Chạy model.
Kỳ vọng: tên sai / trùng bị từ chối với lời giải thích; trang nói "Tên camera là khoá mà policy cần…"; hình
trực tiếp ở mọi màn hình chuyển động, xoay đúng.

**AT-30 (F-23, REG-15) Camera mất khi ghi** · [UAT-KH] (+ [Vendor] với camera giả lập)
1. Ghi một tập; giữa tập rút một camera. 2. Mở dataset sau đó.
Kỳ vọng: ≤ 0,5 s cảnh báo "Camera … không gửi hình. Đồng hồ tập đang tạm dừng", lớp sọc; sau 3 s phiên dừng
(`mất camera`), tay được giữ; dataset mở được bằng lerobot, đúng số tập đã lưu.

## E. Teleop và phát lại

**AT-31 (F-24, NFR-1, NFR-2, REG-5, REG-7) Độ trễ và nhịp teleop** · [Vendor] (số đo) + [UAT-KH] (video)
1. [Vendor] chạy `tests/teleop_bench.py` trên giả lập (1 Mbaud, latency timer 1 ms và 8 ms).
2. [UAT-KH] Teleop 2 phút, cử động leader nhanh qua lại; đọc "độ trễ ~X ms, Y Hz"; quay video 240 fps cả
hai tay. 3. Cùng PC, cùng động tác với LeLab.
Kỳ vọng: p50 ≤ 70 ms, p95 ≤ 100 ms, ≤ LeLab + 10 ms; ≥ 100 Hz; không cảnh báo "không theo kịp"; người dùng
không thấy follower trễ hơn LeLab.

**AT-32 (F-24, REG-15) Teleop không cần camera** · [Vendor]
1. Hồ sơ có 2 camera, rút cả hai. 2. Bắt đầu teleop. 3. Bắt đầu ghi.
Kỳ vọng: teleop chạy; ghi bị từ chối "Có camera đã cấu hình nhưng không truyền hình."

**AT-33 (F-25) Leader xa và căn tay** · [Vendor] + [UAT-KH]
1. Gập leader, để follower duỗi (lệch > 30°). 2. Bắt đầu điều khiển. 3. "Đưa tay follower về tư thế tay leader".
4. Lặp lại, bấm Space giữa lúc căn.
Kỳ vọng: (2) từ chối, nêu khớp và độ lệch, có nút căn; (3) follower đi chậm (≤ 30°/s), rồi teleop bắt đầu;
(4) dừng ngay, `estopped`; trang Ghi không bao giờ đề nghị căn.

**AT-34 (F-26, REG-5) Cảnh báo không theo kịp** · [Vendor]
1. Giả lập bus chậm / servo chậm; teleop với leader nhanh.
Kỳ vọng: khi > 20 % nhịp bị cắt: cảnh báo "Tay follower chạy sau tay leader quá giới hạn an toàn 30°…".

**AT-35 (F-27) Phát lại tập** · [Vendor] + [UAT-KH]
1. Bộ dữ liệu → một dataset → Phát lại tập 0. 2. Bấm Dừng giữa chừng. 3. Phát lại, đóng tab.
Kỳ vọng: follower lặp lại chuyển động; Dừng trong một nhịp; đóng tab → dừng ≤ 1 s (`ui_lost`).

## F. An toàn

**AT-36 (F-28, NFR-3) E-stop đóng băng** · [Vendor] + [UAT-KH] (video 240 fps)
1. Teleop cử động liên tục; bấm Space. 2. Lặp lại khi đang ghi, chạy model, phát quỹ đạo, chương trình, về
tư thế nghỉ, căn tay, hiệu chỉnh. 3. Lặp lại khi con trỏ đang trong ô chữ (dùng Esc).
Kỳ vọng: không lệnh vị trí nào sau nhịp hiện tại ([Vendor] test); tay đứng yên < 100 ms, vẫn giữ mô-men,
không rơi; trạng thái "Đã dừng khẩn" với lý do; Space không cuộn trang.

**AT-37 (F-28, NFR-7, REG-10) Thả lỏng, đặt lại, hiệu chỉnh không đổi** · [Vendor] + [UAT-KH]
1. Sau AT-36 bấm Space lần hai trong 2 s. 2. Đỡ tay; "Đã an toàn, đặt lại". 3. So tệp hiệu chỉnh (hash) và
EEPROM trước / sau.
Kỳ vọng: (1) mô-men tắt, banner "Hãy đỡ tay robot"; (2) về Sẵn sàng; (3) không thay đổi.

**AT-38 (F-29, NFR-4) Dead-man** · [Vendor] + [UAT-KH]
1. Chạy model; đóng tab. 2. Lặp lại với phát lại, chương trình, về tư thế nghỉ. 3. Mở lại trang.
Kỳ vọng: robot dừng trong 1,0 s (+ ≤ 1 nhịp), lý do "mất kết nối giao diện"; mở lại trang thấy trạng thái
dừng và nút đặt lại.

**AT-39 (F-30) Giới hạn an toàn và điều kiện bắt đầu** · [Vendor]
1. Chạy model với bước tối đa 2.0. 2. Trên Chạy model nhập bước lớn hơn hồ sơ. 3. Bắt đầu phiên khi: động cơ
nóng; tay chưa hiệu chỉnh; đang e-stop; đang teleop. 4. Gửi lệnh vượt dải hiệu chỉnh.
Kỳ vọng: (1) chuyển động chậm, khớp bị cắt đánh dấu; (2) "Vượt mức X của hồ sơ. Mở Nâng cao để tăng"; (3) từ
chối với câu tương ứng (`motor_hot`, `not_calibrated`, `estopped`, `busy`); (4) lệnh bị kẹp trong dải.

**AT-40 (F-31, NFR-13, REG-13) Độ chính xác telemetry** · [UAT-KH]
1. Teleop 10 phút; đo nhiệt vỏ động cơ bằng nhiệt kế; đo điện áp nguồn bằng đồng hồ. 2. Kẹp chặt vật, xem dòng.
3. Đẩy một khớp hai chiều khi có mô-men, xem tải.
Kỳ vọng: nhiệt ±2 °C, điện áp ±0,2 V; dòng cùng bậc độ lớn (ghi tỉ lệ); tải đổi dấu; nếu servo báo 0 °C: ô
hiện "—", không cảnh báo giả (REG-13 ghi kết quả).

**AT-41 (F-31, REG-11) Bảng và ngăn sức khoẻ** · [Vendor]
1. Kết nối; xem bảng gọn trên Robot, Teleop, Ghi, Chạy model, Chương trình. 2. Bấm chip động cơ nóng nhất.
3. Giả lập một lần đọc không trả lời; ba lần liên tiếp.
Kỳ vọng: đủ 5 đại lượng mỗi động cơ, đơn vị đúng; ngăn chi tiết có 120 s, ngưỡng nét đứt, giới hạn từ động
cơ; (3) "không phản hồi" có tooltip; ba lần → cảnh báo "Không đọc được thông số động cơ"; leader có ghi chú
"chỉ để tham khảo".

**AT-42 (F-32, NFR-6, REG-3) Dừng an toàn nhiệt** · [Vendor] + [UAT-KH] (video)
1. Cài đặt: hạ ngưỡng nguy hiểm xuống nhiệt hiện tại + 1 (giữ RULE-4); lưu tư thế nghỉ. 2. Teleop tới khi
kích hoạt. 3. Bấm đặt lại khi còn nóng. 4. Chờ nguội, đặt lại. 5. [Vendor] giả lập 0 °C và
`Max_Temperature_Limit = 0`.
Kỳ vọng: (2) sau mẫu nguy hiểm thứ hai: giữ → về tư thế nghỉ → tắt mô-men trong ≤ 2 s; banner đỏ đúng chữ;
"Đã dừng vì nhiệt"; ước lượng thời gian nguội; (3) bị từ chối; (4) về Sẵn sàng; (5) không dừng, không cảnh
báo nhiệt, ngưỡng không đổi.

**AT-43 (F-33, NFR-12, REG-3, REG-11, REG-13) Số đo vô lý** · [Vendor]
1. Giả lập trên follower và leader: nhiệt 0 °C và 200 °C; dòng thô 1000 có bit 15; tải 120 %; điện áp 0 và
20 V. 2. Teleop 5 phút. 3. Giả lập leader 62 °C, 70 °C.
Kỳ vọng: mọi giá trị trên hiện "—" với tooltip "Không có giá trị…"; 0 cảnh báo, 0 dừng, lần đọc không bị
coi là lỗi; leader 62 °C → "nóng" không chặn phiên, 70 °C vẫn tối đa "nóng", không dừng; Robot 3D tô "chưa
có số đo" cho giá trị không rõ.

**AT-44 (F-34, REG-16) Dừng vì điện, kẹp quá tải** · [Vendor] + [UAT-KH]
1. [Vendor] giả lập điện áp follower dưới tối thiểu ở 1 lần đọc, rồi 2 lần liên tiếp. 2. Kẹp bóp chặt vật 5 s.
3. Giữ một khớp bị chặn > 2 s.
Kỳ vọng: (1) 1 lần: cảnh báo; 2 lần: dừng an toàn "lỗi điện"; (2) không dừng (chỉ cảnh báo nếu có); (3) cảnh
báo "bị kẹt".

**AT-45 (F-35, NFR-7, REG-10) Về tư thế nghỉ sau khi dừng giữa chừng** · [Vendor] + [UAT-KH]
1. Phát một quỹ đạo; e-stop giữa chừng; đặt lại. 2. Bấm "Về tư thế nghỉ"; bấm Space giữa đường; lặp lại để
đi hết. 3. Hồ sơ chưa có tư thế nghỉ: lặp bước 1.
Kỳ vọng: banner "Tay robot đã dừng giữa chừng…" + "Về tư thế nghỉ"; chuyển động chậm ≤ 30°/s, Space huỷ; (3)
"Hãy lưu tư thế nghỉ ở trang Robot…".

**AT-46 (F-36) Thông báo và kết nối lại giao diện** · [Vendor]
1. Đang teleop, tải lại trang (F5). 2. Tắt Station khi trang đang mở; bật lại. 3. Giả lập nóng, nguy hiểm.
Kỳ vọng: (1) trang khôi phục đúng trạng thái; (2) "Đang kết nối lại… các nút điều khiển tạm khoá…", tự kết nối
lại khi Station chạy; (3) banner cam / đỏ đúng chữ; đỏ không ẩn được khi còn nguy hiểm; Hibi nói tên khớp và
giá trị.

**AT-47 (F-37) Lịch sử phiên** · [Vendor]
1. Chạy teleop, ghi, chạy model. 2. Mở Phiên. 3. Đặt ngày phiên cũ > 30 ngày, khởi động lại.
Kỳ vọng: mỗi phiên một dòng với loại, thời gian, kết quả, nhiệt độ cao nhất; xem telemetry được; (3) phiên cũ bị
xoá.

## G. Ghi dữ liệu

**AT-48 (F-38) Ghi 3 tập với phím** · [Vendor] + [UAT-KH]
1. Ghi: dataset mới `thu_nghiem`, nhiệm vụ tiếng Việt, 3 tập × 10 s, đặt lại 5 s. 2. Tập 1 bấm →; tập 2 bấm ←
rồi ghi lại; tập 3 để hết giờ. 3. Lặp lại một lần ghi, bấm Esc giữa tập; một lần e-stop giữa tập.
Kỳ vọng: tiêu đề pha đúng ("Tập 1 / 3 · đang ghi · …", "Đặt lại cảnh", "Đang lưu tập…"); tập hết giờ được
lưu; kết thúc "Đã lưu 3 tập trong …" + Tải lên / Ghi thêm; (3) dataset vẫn hoàn tất và mở được.

**AT-49 (F-38, NFR-15) Dataset hợp lệ** · [Vendor]
1. Mở dataset của AT-48 bằng lerobot 0.7.1 (`LeRobotDataset('local/thu_nghiem', root=…)`).
2. Liệt kê tệp trong thư mục dataset.
Kỳ vọng: mở được, đúng số tập và camera; không tệp lạ trong thư mục LeRobot; telemetry nằm trong
`thu_nghiem.hibiscus/`.

**AT-50 (F-39) Ghi thêm** · [Vendor]
1. Ghi thêm 2 tập vào `thu_nghiem`. 2. Thêm một camera, ghi thêm lần nữa. 3. Dataset mới trùng tên.
Kỳ vọng: (1) 5 tập; (2) từ chối "Dataset này không khớp với robot…"; (3) "Đã có bộ dữ liệu tên này. Hãy chọn ghi
thêm".

**AT-51 (F-40) Bộ dữ liệu** · [Vendor]
1. Mở Bộ dữ liệu, chi tiết `thu_nghiem`, chọn từng tập. 2. Xoá (Huỷ, rồi Xoá vĩnh viễn). 3. Xoá khi đang ghi.
Kỳ vọng: số tập, khung hình, fps, dung lượng đúng; biểu đồ nhiệt mỗi tập; "Tập này không có telemetry" khi
thiếu; xoá cần xác nhận; (3) bị từ chối.

## H. Liên kết máy chủ Hibiscus

**AT-52 (F-41) Ghép nối** · [Vendor] (máy chủ thử) + [UAT-KH] nếu khách có tài khoản
1. Chào mừng → Ghép nối: địa chỉ + token đúng. 2. Token thiếu `models:read`. 3. Token sai. 4. Huỷ ghép nối.
Kỳ vọng: (1) "Đã ghép nối với … (workspace …)", chip máy chủ; (2) nêu quyền thiếu; (3) "Máy chủ từ chối token
này."; (4) chip "Ngoại tuyến", token bị xoá khỏi kho.

**AT-53 (F-42) Tải lên** · [Vendor]
1. Tải `thu_nghiem` thành dataset mới. 2. Tải lại thành phiên bản mới. 3. Tải dataset chưa hoàn tất.
Kỳ vọng: tiến độ băm → tải lên → kiểm tra → "Đã tải lên thành phiên bản N" + "Mở trên máy chủ"; danh sách hiện
"đã tải lên vN"; (3) "Bộ dữ liệu chưa hoàn tất."; telemetry không được gửi.

**AT-54 (F-42, NFR-7, NFR-17) Tải tiếp sau mất mạng** · [Vendor]
1. Tải một dataset lớn; ngắt mạng giữa chừng. 2. Nối lại, bấm Tải lên. 3. Lặp lại, khởi động lại Station giữa
chừng.
Kỳ vọng: công việc báo lỗi bằng lời + "Bấm tải lên lần nữa để tiếp tục…"; tải tiếp không gửi lại phần đã xác
nhận (log / số phần).

**AT-55 (F-43) Huấn luyện** · [Vendor]
1. Huấn luyện → "Mở huấn luyện trên Hibiscus". 2. Xem danh sách lượt. 3. "Tải về và chạy" ở lượt đã xong.
Kỳ vọng: thẻ mới mở trình tạo lượt với phiên bản đã chọn; lượt có trạng thái, tiến độ; (3) model được kéo về và
Chạy model mở với model đó.

**AT-56 (F-44) Kéo model từ máy chủ** · [Vendor]
1. Chạy model → Từ máy chủ → Tải về. 2. Ngắt mạng giữa chừng, tải lại.
Kỳ vọng: tiến độ, model xuất hiện với nguồn "máy chủ", "đã xác minh"; tải tiếp được; sha256 sai → từ chối.

## I. Chạy model

**AT-57 (F-45, NFR-14) Nhập model** · [Vendor]
1. Nhập gói zip. 2. Nhập thư mục `pretrained_model` bằng đường dẫn trong home; đường dẫn `C:\Windows` /
`/etc`. 3. Nhập zip có `../` và zip chứa `*.pt`.
Kỳ vọng: (1) "đã xác minh"; (2) "chưa xác minh"; ngoài thư mục cho phép → "Đường dẫn này không được phép…";
(3) từ chối với lý do; không tệp nào ghi ra ngoài kho model.

**AT-58 (F-46) Tương thích và sửa một cú bấm** · [Vendor]
1. Chọn model cần camera `front` 640×480 khi camera là 320×240. 2. Bấm "Đặt front thành 640×480".
3. Model cần `wrist` mà hồ sơ có `cam1`: chọn tương ứng.
Kỳ vọng: danh sách kiểm có mục "có vấn đề" với lý do; sau sửa → "ổn"; không bao giờ tự resize; bắt đầu chạy kiểm
lại.

**AT-59 (F-47) Nạp model** · [Vendor] + [UAT-KH]
1. Nạp với Tự động. 2. Nạp với CPU.
Kỳ vọng: "Đã nạp trên <thiết bị> trong X giây · khởi động Y ms"; một model tại một lúc; "Chạy trên robot" bị
tắt khi chưa nạp ("Hãy nạp model trước.").

**AT-60 (F-48) Chạy model trên robot** · [UAT-KH] (video) + [Vendor] (mock)
1. Chạy 2 tập × 20 s; lần đầu đánh dấu xác nhận e-stop phần mềm. 2. Quan sát màn hình. 3. Bấm Tiếp ở tập 1;
Dừng ở tập 2.
Kỳ vọng: đếm ngược 3 s; mọi camera với nhãn "đầu vào policy · W×H → w×h" và tick tăng; khớp đo được / lệnh /
đã gửi + biểu đồ 10 s; FPS, suy luận p50 / p95, % cắt; nút DỪNG 128 px; Tiếp / Dừng đúng; robot chuyển động
theo model.

**AT-61 (F-48) Model quá chậm** · [Vendor]
1. Giả lập policy suy luận 200 ms ở 30 fps.
Kỳ vọng: sau 5 s phiên tạm dừng với "Model quá chậm cho fps này trên máy này. Hãy giảm fps hoặc dùng CUDA.";
không lệnh cũ nào được gửi dồn.

**AT-62 (F-49) Dataset đánh giá** · [Vendor]
1. Chạy model với "Ghi bộ dữ liệu đánh giá". Kỳ vọng: dataset `eval_…` mở được bằng lerobot, có telemetry.

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

**AT-73 (F-59) Tín hiệu ngoài** · [Vendor]
1. Chương trình chờ "tín hiệu door = open". 2. `curl -X POST -H 'Authorization: Bearer <token>'
…/api/v1/signals/door -d '{"value":"open"}'`; không token. 3. MQTT: cấu hình broker, publish topic. 4. Khối
thông báo với webhook.
Kỳ vọng: chương trình tiếp tục khi nhận tín hiệu; không token bị từ chối; MQTT cũng vậy; webhook nhận POST.

**AT-74 (F-60) Chạy model trong chương trình** · [Vendor]
1. Khối "chạy mô hình M nhiệm vụ T trong 10 s", rồi "… đến khi kẹp đang giữ vật (hết giờ 20 s)"; chạy thử, chạy
trên tay giả lập. Kỳ vọng: model chạy đúng thời gian / tới khi điều kiện; hết giờ thì sang khối sau; an toàn của
F-48 áp dụng (e-stop, dead-man).

## K. Robot 3D

**AT-75 (F-61) Robot 3D** · [Vendor] + [UAT-KH]
1. Robot → Robot 3D; thả lỏng, xoay `wrist_roll` một phần tư vòng; đặt tay ở tư thế giữa. 2. Kéo xoay, phóng to,
Đặt lại góc nhìn, Ẩn / Hiện. 3. Giả lập khuỷu 61 °C. 4. Tắt WebGL.
Kỳ vọng: tay 3D cùng chiều, lệch < 5° mỗi khớp; điều khiển góc nhìn chạy; khuỷu màu cam, tooltip "<động cơ>:
61 °C, Nóng"; (4) ẩn với "Trình duyệt này không vẽ được 3D…".

**AT-76 (F-62) Xem trước bằng tay mờ** · [Vendor] + [UAT-KH]
1. Quỹ đạo A → Xem 3D → Phát xem trước; kéo vị trí. 2. Phát A thật.
Kỳ vọng: tay mờ chạy cạnh tay đặc, "t / tổng giây"; chuyển động cùng chiều và thứ tự khớp như lúc phát thật.

## L. Chẩn đoán

**AT-77 (F-63, REG-2, REG-13) Doctor** · [Vendor] + [UAT-KH]
1. Station tắt, hai tay cắm: `hibiscus-station doctor --verbose`. 2. Mở zip. 3. Có hồ sơ demo hoạt động và cổng
thật: chạy lại. 4. `--no-ping --no-cameras`.
Kỳ vọng: bắt đầu bằng LIKELY PROBLEMS; có phiên bản, cổng (VID:PID, ai giữ), camera, tệp hiệu chỉnh, hồ sơ, 200
dòng log, kiểm tra từng tay (id, firmware, điện áp, nhiệt, trạng thái, EEPROM vs tệp, độ trễ đọc, ước lượng
teleop); zip không chứa token (tìm `hbp_`, token cục bộ); không gì ghi xuống động cơ; (3) `MOCK PROFILE ACTIVE …`;
(4) không mở cổng / camera.

**AT-78 (F-64, REG-18) Nhật ký** · [Vendor] + [UAT-KH]
1. Chạy `hibiscus-station -v`; tạo dataset tên có dấu; rút USB một lần. 2. Mở `station.log`.
Kỳ vọng: dòng khởi động (chế độ, thư mục, hồ sơ); lỗi bus có thao tác, thanh ghi, id; UTF-8, tiếng Việt đúng;
không dòng thời gian mỗi nhịp; không lỗi mã hoá trên console Windows.

**AT-79 (F-65) Health** · [Vendor]
1. Station đang chạy: `hibiscus-station health; echo $?`. 2. Station tắt. Kỳ vọng: 0; khác 0 trong ≤ 5 s.

## M. Cài đặt, ngôn ngữ, giao diện

**AT-80 (F-66) Cài đặt** · [Vendor]
1. Đặt ngưỡng nguy hiểm 69 khi động cơ tự ngắt 70; nóng 64 khi nguy hiểm 65; ấm 58 khi nóng 60. 2. Đặt hợp lệ, lưu.
3. Đổi rộng xem trước 640, fps 30. 4. Xem dòng phiên bản.
Kỳ vọng: (1) mỗi lỗi có câu tiếng Việt tương ứng, không lưu; (2) "Đã lưu."; (3) xem trước đổi; (4) phiên bản
Station đúng, lerobot là phiên bản thực đã cài.

**AT-81 (F-67, NFR-10) Song ngữ** · [Vendor]
1. Trình duyệt tiếng Việt: mở Station. 2. Trình duyệt `en-US`. 3. Đổi ngôn ngữ trên thanh trên ở giữa phiên
teleop. 4. Kiểm bộ khoá `vi` và `en`.
Kỳ vọng: (1) tiếng Việt; (2) English; (3) đổi ngay không tải lại, phiên không bị ảnh hưởng; (4) cùng bộ khoá,
không khoá trống.

**AT-82 (F-68, NFR-11) Chủ đề và bề rộng** · [Vendor]
1. Chụp mọi trang ở 1280 px và 390 px, sáng và tối, ở các trạng thái trống / đang tải / lỗi / thành công / bị tắt
có lý do. Kỳ vọng: không cuộn ngang, không chữ bị cắt, tương phản AA (axe 0 lỗi), mỗi trạng thái có thiết kế.

**AT-83 (F-68, NFR-11) Bàn phím** · [Vendor]
1. Chỉ dùng bàn phím: Tab qua thanh bước, "Bỏ qua, tới nội dung", tạo hồ sơ, kết nối, teleop, Space e-stop, đặt
lại, ghi với → / ← / Esc. Kỳ vọng: đi hết luồng, focus luôn thấy rõ, mọi điều khiển có nhãn.

## N. Cập nhật và dữ liệu

**AT-84 (F-69) Cập nhật và quay lại trên Windows** · [UAT-KH] (+ [Vendor] Linux)
Tiền điều kiện: bản cũ (0.2.8) đã dùng: có hồ sơ, hiệu chỉnh, dataset, model, quỹ đạo, chương trình.
1. Chạy lệnh cập nhật trong ghi chú phát hành. 2. Mở Station, kiểm mọi thứ. 3. Cài lại bản cũ theo hướng dẫn,
kiểm lại.
Kỳ vọng: phiên bản mới hiện ở Cài đặt; mọi dữ liệu còn và dùng được (kết nối không cần hiệu chỉnh lại, quỹ đạo
phát được); quay lại bản cũ cũng vậy.

**AT-85 (F-70) Docker backup / update / rollback** · [Vendor]
1. `hibiscus-station-ctl backup`; `update <tag mới>`; `rollback`. 2. Giả lập image mới không khoẻ, `update`.
Kỳ vọng: có tệp sao lưu; tag mới healthy; rollback về tag cũ, dữ liệu nguyên; (2) tự quay lại.

**AT-86 (F-71, NFR-15, NFR-16) Dữ liệu bền và ngoại tuyến** · [Vendor]
1. Rút mạng; đi hết Robot → Hiệu chỉnh → Camera → Teleop → Ghi → Chạy model (zip) → Chương trình. 2. Tắt nguồn
(kill -9) giữa lúc lưu hồ sơ; khởi động lại. 3. Kiểm quyền tệp `token`, `robots.yaml`.
Kỳ vọng: (1) mọi bước chạy không Internet; (2) `robots.yaml` không hỏng (bản cũ hoặc mới, không nửa vời); (3) 0600.

## Các AT cho NFR

**AT-87 (NFR-5) Thời gian khởi động** · [Vendor] + [UAT-KH]
1. Lần chạy thứ hai: đo từ Enter tới khi trang Chào mừng tải xong. 2. Kết nối hồ sơ không camera, đo.
Kỳ vọng: Windows của khách ≤ 15 s; Linux vendor ≤ 10 s; kết nối ≤ 5 s.

**AT-88 (NFR-3) Đo thời gian e-stop** · [Vendor] (test tự động) + [UAT-KH] (video 240 fps)
1. 10 lần e-stop trong teleop nhanh và trong phát quỹ đạo. Kỳ vọng: 10/10 tay đứng yên < 100 ms; log không có
lệnh ghi vị trí sau nhịp e-stop.

**AT-89 (NFR-2, REG-19) Nhịp vòng 10 phút** · [UAT-KH] (+ [Vendor] Linux)
1. Teleop 10 phút; ghi 10 tập × 30 s ở 30 fps. 2. Xem tóm tắt phiên. Kỳ vọng: teleop ≥ 100 Hz, nhịp trễ < 1 %;
ghi 30 fps: p95 ≤ 36 ms; `telemetry_forced` nhỏ (< 1 %).

**AT-90 (NFR-8) Phiên dài** · [Vendor]
1. Teleop 30 phút rồi ghi 20 tập liên tục, theo dõi bộ nhớ tiến trình và fps. Kỳ vọng: bộ nhớ tăng ≤ 20 %, fps
giảm ≤ 10 %, không treo, không lỗi.

**AT-91 (NFR-10) Không lẫn ngôn ngữ** · [Vendor]
1. Ở tiếng Việt, chụp mọi màn hình và mọi thông báo lỗi có thể gây ra (danh sách `errors.*`, `lost.*`, cảnh
báo). Kỳ vọng: 0 câu tiếng Anh ngoài thuật ngữ đã thống nhất; một thuật ngữ cho một khái niệm (Q-8); không lỗi
chính tả.

**AT-92 (NFR-12, FR-73) Thông tin đúng, không chữ thô** · [Vendor] + [UAT-KH]
1. Rà mọi màn hình với tay giả lập và (UAT) tay thật trong 30 phút teleop. 2. Gây từng lỗi: cổng bận, mất USB,
token sai, model không tương thích, dataset chưa hoàn tất. Kỳ vọng: mọi số có đơn vị đúng, trong dải hợp lý; 0
placeholder / debug / stack trace / `internal_error` thô; 0 cảnh báo giả; mỗi lỗi có câu dịch và đường thoát.

---

## Ký xác nhận

| | Người | Ngày | Phiên bản | Kết quả |
|---|---|---|---|---|
| QC (nội bộ) | | | | |
| Khách hàng (UAT) | | | | |

## Danh sách UAT của khách hàng (tóm tắt)

AT chỉ khách hàng chứng minh được (Windows + SO-101 thật): AT-1, AT-14, AT-17, AT-18, AT-23, AT-27, AT-40,
AT-84. AT cần khách hàng chạy lại trên nền tảng của mình sau QC: AT-5, AT-12, AT-13, AT-15, AT-16, AT-20, AT-21,
AT-22, AT-26, AT-28 – AT-31, AT-33, AT-35 – AT-38, AT-42, AT-44, AT-45, AT-48, AT-52 (nếu có tài khoản), AT-59,
AT-60, AT-65, AT-66, AT-69, AT-70, AT-72, AT-75 – AT-78, AT-87 – AT-89, AT-92. BA sẽ gửi bản rút gọn theo các
tính năng Must, từng bước đánh số, khi tới giai đoạn UAT.
