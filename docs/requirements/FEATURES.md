# Hibiscus Station: danh sách tính năng v1.1 (2026-11-19) · trạng thái: **đã duyệt** (khách hàng duyệt ngày 2026-11-17, đường cơ sở; CR-1 duyệt ngày 2026-11-19)

**v1.1 (2026-11-19, CR-1):** khách hàng thêm một tính năng mới vào M1: **F-72** xem video từng tập trong Bộ dữ liệu
("Có, thêm vào M1"). Nhật ký: [CHANGELOG.md](CHANGELOG.md#cr-1-xem-video-từng-tập-trong-bộ-dữ-liệu--v11--2026-11-19).

Đường cơ sở "như đã xây" của Station **0.2.8** (`main` `12f36da`). Mọi dòng có trạng thái
**hiện có** (existing): tính năng đã có trong sản phẩm, v1.0 phải đưa nó lên chuẩn chất lượng
(mọi AT đạt, không còn lỗi mở). Không có tính năng mới trong v1.0; các **đề xuất thay đổi P-n** dưới
đây là sửa lỗi hoặc đóng gói để đạt chuẩn, không phải tính năng mới.

Bản v0.2 áp dụng rà soát vòng 1 của SA ([REVIEW-SA.md](REVIEW-SA.md)) và Tech Lead
([REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md)). Thay đổi so với v0.1: [CHANGELOG.md](CHANGELOG.md).

**v1.0 (2026-11-17):** khách hàng chọn QĐ-1 – QĐ-4 = A ("1. A, 2. A, 3. A, 4. A") và duyệt toàn bộ bộ tài liệu
("Duyệt, bắt đầu làm"). Danh sách này cùng với P-1 – P-8 được đóng băng trong
[FEATURES-APPROVED.md](FEATURES-APPROVED.md) v1.0; theo dõi trạng thái dev / QC ở đó. Cột "Trạng thái" dưới đây
là kết quả kiểm sơ bộ vòng 1, giữ để tham khảo.

* **Ưu tiên**: đã duyệt. Q-2 (máy chủ Hibiscus = Should) và Q-3 (Chương trình = Should, tín hiệu
  ngoài và model trong chương trình = Could) duyệt cùng bộ tài liệu; nền tảng theo **QĐ-2 = A** (BRD §9).
* **Effort** (Tech Lead, công dev để đạt zero-defect gồm sửa lỗi + tự động hoá AT + tài liệu):
  **S** ≈ 0,5 ngày, **M** ≈ 2 ngày, **L** ≈ 5 ngày. **Milestone** M0 – M3: xem [§ Mốc](#mốc-tech-lead).
* **Trạng thái** (kiểm sơ bộ vòng 1 trên Linux, đúng wheel 0.2.8; *chưa phải kết quả QC*):
  **ĐẠT\*** = không thấy lỗi; **LỖI** = có lỗi / khoảng trống mở (cột "Lỗi / khoảng trống đã biết",
  chi tiết ở [§ Lỗi đã biết](#lỗi-đã-biết-d-n)); **KHÔNG KIỂM ĐƯỢC** = phần quyết định chỉ chứng minh
  được trên Windows + tay thật (UAT của khách) hoặc trên máy chủ Hibiscus thử / Docker (vendor dựng).
* **AT** = mã trong [ACCEPTANCE.md](ACCEPTANCE.md). **FR / NFR** = mã trong [SRS.md](SRS.md) (FR-n mô tả
  F-n cùng số). **REG** = mục hồi quy trong [REGRESSION.md](REGRESSION.md). Truy vết đầy đủ BR → FR / NFR
  → F → AT: [§ Ma trận truy vết](#ma-trận-truy-vết).
* **Phụ thuộc**: theo quy tắc zero-defect, một tính năng FAIL kéo theo mọi tính năng phụ thuộc nó.
* Nơi xuất hiện: **UI** = trang / nút trên giao diện; **CLI** = lệnh terminal; **API** = chỉ qua API.

## A. Cài đặt và khởi động

| ID | Tính năng | Giá trị cho người dùng | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-1 | Cài đặt trên Windows 10/11 x64 bằng uv + wheel. **P-1, QĐ-3 = A:** **một** lệnh PowerShell chép-dán cài uv nếu thiếu và cài Station với bộ phụ thuộc cố định đã kiểm, không cần git / admin / Python có sẵn; tuỳ chọn torch CPU | Người mới cài được bằng chép-dán | CLI | BR-1, BR-15, FR-1, NFR-9, NFR-18 | Must | — | M (+ M cho P-1, SA ước; Tech Lead xác nhận, OI-1) | M0 (P-1) / M1 | AT-1, AT-2 | REG-1, REG-17, REG-18, REG-19 | K-8, P-1 (môi trường cài không cố định, SA-P1), K-10 | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-2 | Cài đặt trên Ubuntu 22.04 / 24.04 x86_64 bằng wheel, kèm unit systemd tuỳ chọn (wheel arm64: bản xem trước, W-9) | Kỹ sư Linux | CLI | BR-1, FR-2, NFR-9 | Should | — | S | M1 | AT-3 | — | — | hiện có · ĐẠT\* |
| F-3 | Cài đặt Docker trên **Linux x86_64, image `-cpu`** (v0.2, QĐ-2; `-cuda`, Raspberry Pi 5, Jetson Orin: bản xem trước, W-9): `install.sh` (dò máy, chọn image cpu / cuda / jetson, luật udev, tự khởi động), `hibiscus-station-ctl` (status, logs, url, ports) | Máy robot không màn hình | CLI | BR-1, FR-3, NFR-9 | Could | — | M | M3 | AT-4 | — | D-18 (= K-1) | hiện có · LỖI |
| F-4 | Khởi động `hibiscus-station`: mở trình duyệt bằng liên kết đăng nhập một lần, chỉ một phiên bản chạy (lần chạy thứ hai in liên kết của bản đang chạy), `hibiscus-station url` in lại liên kết, `--port`, `--no-browser`, `--home` | Mở được giao diện ngay | CLI, UI | BR-1, BR-5, FR-4, FR-75, NFR-5, NFR-10 | Must | F-1 hoặc F-2 | S | M1 | AT-5, AT-6, AT-87, AT-95 | — | D-3, D-4, D-19 | hiện có · LỖI |
| F-5 | Chế độ demo `--mock`: tay, camera, policy giả lập; dữ liệu ở thư mục riêng `~/.hibiscus/station-demo`; chip **TAY GIẢ LẬP** trên thanh trên | Thử khi chưa có robot | CLI, UI | BR-2, FR-5 (v0.2: FL-10) | Must | F-4 | M | M1 | AT-7 | REG-2 | D-8 | hiện có · LỖI |
| F-6 | Truy cập cục bộ an toàn: chỉ `127.0.0.1`, token mỗi lần chạy, cookie, danh sách Host cho phép, chặn CSRF; chế độ LAN chỉ khi bật đủ ba thiết lập (host, token cố định ≥ 32 ký tự, tên máy cho phép) | Không ai khác điều khiển được robot | CLI, UI | BR-16, FR-6, NFR-14 | Must (LAN: Could) | F-4 | S | M1 (LAN: M3) | AT-8, AT-9 (LAN: mạng cô lập, FL-8), AT-98 | — | — | hiện có · ĐẠT\* |
| F-7 | Trang Chào mừng và **thanh bước** (Robot · Hiệu chỉnh · Camera · Điều khiển tay · Ghi dữ liệu · Tải lên · Huấn luyện · Chạy model, cùng Bộ dữ liệu, Model, Phiên, Chương trình, Cài đặt): dấu ✓ khi xong, bước bị khoá mở trang nói lý do, liên kết tới bước cần làm trước, nút trên trang bị tắt | Người mới biết làm gì tiếp theo | UI | BR-1, FR-7, FR-73 | Must | F-4 | S | M1 | AT-10 | REG-12, REG-22 | D-5, D-25 | hiện có · LỖI |

## B. Robot và cổng

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-8 | Hồ sơ robot: tạo / sửa / xoá; loại SO-101 / SO-100; cổng follower (bắt buộc), cổng leader (không bắt buộc: chỉ chạy model); mã hiệu chỉnh mỗi tay (chọn được mã có sẵn, ví dụ của LeLab); khi kết thúc phiên: giữ nguyên hoặc về tư thế nghỉ rồi thả lỏng | Cấu hình ở một chỗ | UI | BR-2, FR-8 | Must | F-4 | S | M1 | AT-11 | — | — | hiện có · ĐẠT\* |
| F-9 | Danh sách cổng USB serial: chỉ cổng USB, mô tả, VID:PID, đường dẫn ổn định (Linux `by-id`), cổng đang bị ai giữ; nút Làm mới | Chọn đúng cổng | UI | BR-2, FR-9 | Must | F-8 | S | M1 | AT-12 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-10 | Tìm cổng **theo vai trò**: "Tìm tay follower" / "Tìm tay leader", mỗi nút có hai cách (cử động trong ≤ 15 s, hoặc rút cáp trong ≤ 15 s); cổng tìm được vào đúng ô; không bao giờ đề xuất cổng đã gán cho tay kia | Không nhầm leader / follower | UI | BR-2, FR-10 | Must | F-9 | S | M1 | AT-13, AT-14 | REG-6 | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-11 | Dò cổng chỉ-đọc (điện áp, model, firmware) và gợi ý vai trò (~5 V: thường là leader; ≥ 6,5 V: thường là follower); cảnh báo khi có vẻ nhầm; nút "Đổi chỗ follower ⇄ leader" (mã hiệu chỉnh đi theo vai trò); không bao giờ tự đổi | Phát hiện nhầm trước khi chạy | UI | BR-2, FR-11 | Must | F-9 | S | M1 | AT-15 | REG-6 | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-12 | Kết nối / ngắt kết nối hồ sơ: tiến trình (mở cổng, bắt tay, cấu hình); lỗi nói rõ bước và lý do (cổng bận do LeLab / lerobot, động cơ thiếu / sai model / firmware lẫn, không ghi được cấu hình), thử lại 2 lần cho mỗi gói tin lỗi | Biết vì sao không kết nối được | UI | BR-2, FR-12 | Must | F-8 | S | M1 | AT-16, AT-17, AT-96 | REG-14 | D-22 | hiện có · LỖI |
| F-13 | **Mất thiết bị USB** (Windows "Access is denied", thiết bị không sẵn sàng; Linux EIO / ENODEV): không thử lại vô ích, trạng thái lỗi `device_lost` với tay, cổng, thông báo hệ thống; trang giải thích bằng lời dễ hiểu kèm danh sách kiểm tra; nút "Kết nối lại" chờ cổng trở lại (kể cả số COM mới), cập nhật hồ sơ, ghi lại hiệu chỉnh | Phục hồi không cần khởi động lại | UI | BR-5, FR-13, NFR-7 | Must | F-12 | M | M1 | AT-18, AT-19, AT-94 | REG-8 | K-2 (tài liệu UAT ghi `bus_lost`) | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-14 | Mô-men follower: bật / thả lỏng (cần xác nhận khi chưa có tư thế nghỉ); "Lấy tư thế hiện tại làm tư thế nghỉ"; bảng khớp và sức khoẻ động cơ ngay sau khi kết nối | Đỡ tay an toàn, có tư thế đỗ | UI | BR-5, FR-14 | Must | F-12 | S | M1 | AT-20 | — | — | hiện có · ĐẠT\* |
| F-15 | Bảo vệ khỏi hồ sơ demo: khi chạy với tay thật, hồ sơ demo còn sót bị đánh dấu **DEMO**, không kích hoạt, không kết nối được (`demo_profile`); khi có cổng thật đang cắm, banner "Tạo hồ sơ cho tay thật" điền sẵn cổng | Không bao giờ điều khiển tay giả lập do nhầm | UI | BR-2, FR-15 | Must | F-8 | S | M1 | AT-21 | REG-2 | — | hiện có · ĐẠT\* |

## C. Hiệu chỉnh

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-16 | Kiểm tra hiệu chỉnh khi vào trang: đọc EEPROM từng tay và so với mọi tệp trên máy; báo "đã hiệu chỉnh — dùng luôn"; nếu động cơ đang mang tệp khác (ví dụ của LeLab) thì đề xuất đúng tệp đó, một cú bấm "Dùng"; nếu động cơ không giữ được tệp thì "Ghi lại tệp" / "Hiệu chỉnh lại" | Không phải hiệu chỉnh lại khi đã có | UI | BR-3, FR-16 | Must | F-12 | S | M1 | AT-22 | REG-7 | — | hiện có · ĐẠT\* |
| F-17 | Luồng hiệu chỉnh có hướng dẫn (follower → leader → kiểm tra): bước **Đặt home** (hình minh hoạ, tay thả lỏng), bước **Biên độ**: dấu tick cho **mọi** khớp kể cả `wrist_roll` khi đã quay đủ 100 bước (quy tắc LeLab), hiện min / vị trí / max trực tiếp, nút **Lưu** chỉ mở khi đủ mọi khớp; tệp lưu ở chỗ lerobot dùng | Hiệu chỉnh chuẩn LeLab, khoảng 1 phút mỗi tay | UI | BR-3, FR-17 | Must | F-12 | M | M0 (D-1) / M1 | AT-23, AT-24 | REG-4, REG-7 | D-1, D-17, K-2 | hiện có · LỖI |
| F-18 | "Nâng cao: các tệp hiệu chỉnh": danh sách mọi tệp của tay đó (kể cả thư mục cũ của lerobot < 0.4 / LeLab), nhãn "của robot này" / "động cơ đang dùng" / "thuộc tay kia" / "không phải tệp hiệu chỉnh"; "Dùng tệp này" sao chép sang mã của tay (tệp cũ giữ lại `.bak-<thời gian>`); không đề xuất tệp khớp với tay kia | Kỹ sư chọn tệp cụ thể | UI | BR-3, BR-11, FR-18 | Should | F-16 | S | M1 | AT-25 | — | — | hiện có · ĐẠT\* |
| F-19 | Kiểm tra hai tay: follower đứng yên, người dùng đặt leader giống follower, bấm Kiểm tra → độ lệch từng khớp; > 20° (kẹp: 20 %) bị đánh dấu với lý do (sai tư thế / sai tệp / nhầm cổng); "Thử teleop" hoặc "Vẫn thử teleop" | Bắt lỗi trước teleop | UI | BR-3, FR-19 | Must | F-17 | M | M1 | AT-26 | REG-7 | D-7 | hiện có · LỖI |
| F-20 | Tệp hiệu chỉnh dùng chung hai chiều với lerobot và LeLab (cùng thư mục, cùng định dạng) | Không bị khoá vào Station | UI, CLI | BR-3, FR-20, NFR-15 | Must | F-17 | S | M1 | AT-27 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |

## D. Camera

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-21 | Tìm camera (Windows / macOS: số 0, 1, 2…; Linux: `/dev/video*`, RealSense nếu có), không mở camera Station đang dùng; "Thử": ảnh chụp, fps đo được; cảnh báo khi fps đo < 90 % yêu cầu | Biết camera nào dùng được | UI | BR-7, FR-21 | Must | F-12 | S | M1 | AT-28 | REG-20 | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-22 | Camera đã cấu hình: tên (khoá `observation.images.<tên>`), độ phân giải, fps, định dạng (MJPG…), xoay; xem trực tiếp trên mọi màn hình chuyển động; mỗi camera chỉ một chủ sở hữu | Thấy camera khi ghi và chạy model | UI | BR-7, BR-9, FR-22 | Must | F-21 | S | M1 | AT-29 | — | D-10 | hiện có · LỖI |
| F-23 | Camera đứng hình / mất trong phiên: sau 0,5 s cảnh báo và dừng đồng hồ tập (ghi, chạy model); sau 3 s phiên dừng với lý do `camera_lost`, tay vẫn được giữ, dataset vẫn hợp lệ; teleop không bắt buộc camera | Không ghi dữ liệu hỏng | UI | BR-7, FR-23 | Must | F-22 | S | M1 | AT-30 | REG-15 | — | hiện có · KHÔNG KIỂM ĐƯỢC |

## E. Điều khiển tay (teleop) và phát lại

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-24 | Teleop leader → follower: vòng nhanh (mặc định 250 Hz, tối đa 300; chậm hơn nếu bus chậm), giới hạn bước 30°/nhịp cho phiên do leader điều khiển, kẹp vào dải hiệu chỉnh; hiện "độ trễ ~X ms, Y Hz", bảng khớp leader / follower / bị cắt, camera (nếu có), sức khoẻ động cơ, đồng hồ phiên | Điều khiển mượt như LeLab | UI | BR-4, FR-24, NFR-1, NFR-2 | Must | F-17 (v0.2: bỏ F-19, FL-9) | L | M1 | AT-31, AT-32, AT-89, AT-90 | REG-5, REG-7 | D-9, D-10, D-11 | hiện có · LỖI |
| F-25 | Leader lệch xa (> 30° một khớp): teleop từ chối, nêu khớp và độ lệch, đề nghị "Đưa tay follower về tư thế tay leader" (chậm, tối đa 30°/s, dead-man, e-stop được) rồi teleop bắt đầu | Không giật tay khi bắt đầu | UI | BR-4, BR-5, FR-25 | Must | F-24 | S | M1 | AT-33 | — | D-5 | hiện có · LỖI |
| F-26 | Cảnh báo "tay follower không theo kịp" khi giới hạn bước cắt > 20 % số nhịp | Biết vì sao follower trễ | UI | BR-4, FR-26 | Should | F-24 | S | M1 | AT-34 | REG-5 | — | hiện có · ĐẠT\* |
| F-27 | Phát lại một tập đã ghi lên follower (từ trang Bộ dữ liệu): dừng được trong một nhịp, có giới hạn an toàn, telemetry, camera, dead-man (bật mặc định) | Kiểm tra dữ liệu trên tay thật | UI | BR-7, FR-27 | Should | F-40 | S | M2 | AT-35 | — | — | hiện có · ĐẠT\* |

## F. An toàn, e-stop, nhiệt, telemetry

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-28 | **E-stop**: nút đỏ lớn (mọi màn hình khi tay chuyển động), phím **Space** từ bất cứ đâu (Esc khi đang gõ chữ), API và WebSocket: lần 1 đóng băng trong nhịp hiện tại (giữ mô-men, tay không rơi), lần 2 trong 2 s hoặc "Thả lỏng" → tắt mô-men; "Đã an toàn, đặt lại" về Sẵn sàng; không bao giờ đổi hiệu chỉnh | Dừng ngay khi nguy hiểm | UI, API | BR-5, FR-28, NFR-3 | Must | F-12 | M | M1 | AT-36, AT-37, AT-88, AT-94 | REG-10 | D-6, D-13 | hiện có · LỖI |
| F-29 | Dead-man: khi chạy model, phát lại, chương trình, về tư thế nghỉ, căn tay: không nhận tín hiệu từ giao diện trong 1 s → e-stop (`ui_lost`) | Đóng tab / sập trình duyệt thì robot dừng | UI | BR-5, FR-29, NFR-4 | Must | F-28 | S | M1 | AT-38 | — | — | hiện có · ĐẠT\* |
| F-30 | Giới hạn an toàn: bước tối đa mỗi nhịp (policy / phát lại 5°, teleop / ghi 30°, sửa được trong hồ sơ; màn hình Chạy model chỉ cho giảm trừ khi mở Nâng cao), kẹp vào dải hiệu chỉnh, giới hạn thời gian tập, điều kiện trước khi bắt đầu (động cơ nóng, camera chưa phát, chưa hiệu chỉnh, model không tương thích) | Tay không làm điều nguy hiểm | UI | BR-5, BR-11, FR-30 | Must | F-12 | S | M1 | AT-39 | — | K-5 | hiện có · LỖI |
| F-31 | Sức khoẻ động cơ: nhiệt độ, điện áp, dòng, tải, cờ trạng thái của từng động cơ follower và leader, đọc trong vòng điều khiển; bảng gọn trên mọi màn hình chuyển động; chip "động cơ nóng nhất" trên thanh trên; ngăn chi tiết với 120 s gần nhất và giới hạn đọc từ động cơ | Thấy động cơ sắp quá nhiệt | UI | BR-6, FR-31, NFR-13 | Must | F-12 | M | M1 | AT-40, AT-41 | REG-11 | REG-13 (K-9) | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-32 | Ngưỡng nhiệt và **dừng an toàn nhiệt**: ấm 50 °C (vàng, Hibi nhắc), nóng 60 °C (cam, chặn phiên mới), nguy hiểm 65 °C hai lần liên tiếp hoặc cờ quá nhiệt / quá tải (đỏ): giữ → về tư thế nghỉ (nếu có) → tắt mô-men trong ≤ 2 s, trạng thái `estopped (thermal)`, banner "Hãy đỡ tay", ước lượng thời gian nguội, không reset được khi còn nóng; trễ 3 °C | Station dừng trước khi servo tự ngắt làm rơi tay | UI | BR-5, BR-6, FR-32, NFR-6 | Must | F-31 | S | M1 | AT-42 | REG-3 | — | hiện có · ĐẠT\* |
| F-33 | **Quy tắc số đo hợp lý**: nhiệt độ ngoài 1–150 °C, giới hạn nhiệt ngoài 40–150 °C, dòng > 3,5 A, tải ngoài ±100 %, điện áp ngoài 3–16 V là "không rõ" (hiện "—" kèm giải thích), không bao giờ là cảnh báo hay lý do dừng; bit hướng của dòng bị bỏ; leader không bao giờ báo động / dừng robot / chặn phiên, nhiệt leader tối đa "nóng"; "không phản hồi" chỉ khi một lần đọc không có trả lời | Không báo động giả | UI | BR-5, BR-6, FR-33, NFR-12 | Must | F-31 | M | M1 | AT-43, AT-93 | REG-3, REG-11, REG-13 | REG-13 (K-9) | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-34 | Dừng vì điện: điện áp dưới tối thiểu hoặc cờ quá dòng trên follower hai lần đọc liên tiếp → dừng an toàn (`electrical`); cờ quá tải của **kẹp** chỉ là cảnh báo (bóp vật là bình thường) | Bảo vệ khi nguồn yếu, không dừng giả khi kẹp vật | UI | BR-5, BR-6, FR-34 | Must | F-31 | S | M1 | AT-44 | REG-16 | — | hiện có · ĐẠT\* |
| F-35 | Sau khi một chuyển động bị dừng giữa chừng và đã reset: banner "Tay robot đã dừng giữa chừng" + "Về tư thế nghỉ" (một chuyển động chậm, ≤ 30°/s, dead-man, Space / Dừng để huỷ); lần chạy chương trình / quỹ đạo tiếp theo luôn bắt đầu lại từ đầu | Luôn có đường phục hồi sau e-stop | UI | BR-5, FR-35 | Must | F-28 | S | M1 | AT-45 | REG-10 | — | hiện có · ĐẠT\* |
| F-36 | Thông báo: banner đỏ (nguy hiểm, không ẩn được tới khi hết), cam (nóng), lỗi, đã dừng (kèm lý do); bong bóng Hibi; mất kết nối với Station → "Đang kết nối lại…", nút điều khiển tạm khoá | Luôn biết trạng thái | UI | BR-5, FR-36, FR-74, NFR-7 | Must | F-4 | S | M1 | AT-46 | — | — | hiện có · ĐẠT\* |
| F-37 | Trang Phiên: lịch sử phiên (loại, bắt đầu, bộ dữ liệu / model, kết quả, nhiệt độ cao nhất), telemetry của phiên; tự dọn phiên cũ hơn 30 ngày hoặc vượt 2 GiB | Xem lại sự cố | UI | BR-6, BR-12, FR-37 | Should | F-31 | S | M2 | AT-47 | — | — | hiện có · ĐẠT\* |

## G. Ghi bộ dữ liệu

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-38 | Ghi dataset LeRobot v3: tên, nhiệm vụ (một câu), số tập, độ dài tập, thời gian đặt lại, fps, mã hoá video, khi hết giờ: lưu / bỏ; ước lượng dung lượng; khởi động → tập → đặt lại → lưu; nút và phím **→** (tiếp, lưu), **←** (ghi lại), **Esc** (dừng); dải các tập đã lưu; kết thúc: "Đã lưu N tập trong …" + Tải lên / Ghi thêm | Thu dữ liệu huấn luyện | UI | BR-7, FR-38, NFR-8, NFR-15 | Must | F-17, F-22, F-24 | M | M1 | AT-48, AT-49 | — | D-2, D-19 (tập đang ghi khi đóng cửa sổ) | hiện có · LỖI |
| F-39 | Ghi thêm vào dataset có sẵn (kiểm tra tương thích động cơ / camera; báo tên trùng) | Thu tiếp nhiều buổi | UI | BR-7, FR-39 | Should | F-38 | S | M2 | AT-50 | — | — | hiện có · ĐẠT\* |
| F-40 | Trang Bộ dữ liệu: danh sách (tập, khung hình, fps, dung lượng, đã hoàn tất, đã tải lên v…); chi tiết: các tập, biểu đồ nhiệt độ follower từng tập (tệp telemetry đi kèm, nằm cạnh, không nằm trong thư mục LeRobot), Phát lại, Xoá (xác nhận, bị từ chối khi đang ghi / tải lên) | Xem lại dữ liệu | UI | BR-7, FR-40 | Must | F-38 | S | M1 | AT-51 | — | D-2 | hiện có · LỖI |
| F-72 | Xem video từng tập (CR-1): trong chi tiết bộ dữ liệu, bấm một tập → video của mọi camera phát cùng lúc, Phát / Tạm dừng, thanh kéo thời gian, con trỏ thời gian chung với biểu đồ nhiệt độ từng khớp (bấm biểu đồ để nhảy tới đó); lỗi riêng từng camera (VI / EN); phát được trên Edge (Windows 11 cài sẵn, không cần AV1 Video Extension), Chrome, Firefox; 1280 / 390 px, sáng / tối | Xem lại tập đã ghi trước khi huấn luyện | UI, API | BR-7, FR-77, NFR-10, NFR-11 | Must | F-38, F-40 | M | M1 | AT-99 | REG-23 | — | mới (CR-1, 2026-11-19) |

## H. Tải lên và liên kết máy chủ Hibiscus

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-41 | Ghép nối máy chủ Hibiscus: địa chỉ + personal access token (`datasets:write`, `models:read`, tuỳ chọn `runs:read`), liên kết "Tạo token với đúng quyền", kiểm tra quyền; token cất trong kho của hệ thống, không bao giờ gửi tới trình duyệt; chip máy chủ; Huỷ ghép nối | Một lần cho mọi lần tải | UI | BR-8, FR-41 | Should | F-4 | M | M2 | AT-52 | REG-22 | D-25 | hiện có · LỖI |
| F-42 | Tải dataset lên (dataset mới / phiên bản mới của dataset có sẵn): kiểm tra đã hoàn tất, tiến độ (băm, tải lên, kiểm tra), tiếp tục được sau mất mạng hoặc khởi động lại; chỉ gửi thư mục LeRobot | Đưa dữ liệu đi huấn luyện | UI | BR-8, FR-42, NFR-7, NFR-17 | Should | F-40, F-41 | M | M2 | AT-53, AT-54 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-43 | Trang Huấn luyện: dataset đã tải lên, "Mở huấn luyện trên Hibiscus" (thẻ mới, chọn sẵn phiên bản), danh sách lượt huấn luyện (trạng thái, tiến độ), "Tải về và chạy" | Không huấn luyện trên máy robot | UI | BR-8, FR-43 | Should | F-42 | S | M2 | AT-55 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-44 | Kéo model từ máy chủ ("Từ máy chủ" → Tải về): tiếp tục được, kiểm tra MANIFEST, đăng ký vào danh sách model | Lấy model đã huấn luyện | UI | BR-8, BR-9, FR-44 | Should | F-41 | S | M2 | AT-56 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |

## I. Chạy model (policy) trên robot

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-45 | Nhập model: tệp zip gói Hibiscus (xác minh MANIFEST → "đã xác minh") hoặc thư mục `pretrained_model` của lerobot ("chưa xác minh"), từ trình duyệt hoặc đường dẫn trên máy (chỉ trong home / ổ khác trên Windows / `/media`, `/mnt`); sao chép vào kho model; từ chối checkpoint pickle, zip độc hại | Dùng model huấn luyện ở đâu cũng được | UI | BR-9, FR-45, NFR-14 | Must | F-4 | S | M1 | AT-57 | — | D-16 | hiện có · LỖI |
| F-46 | Kiểm tra tương thích model ↔ robot (số khớp, kích thước lệnh, camera theo tên, độ phân giải, loại robot, gói bổ sung policy) với sửa một cú bấm ("Đặt camera thành W×H", chọn camera tương ứng) | Không chạy model sai | UI | BR-9, FR-46 | Must | F-45, F-22 | S | M1 | AT-58 | — | — | hiện có · ĐẠT\* |
| F-47 | Nạp model: thiết bị Tự động (CUDA → MPS → CPU) / CPU / CUDA / MPS; hiện thiết bị, thời gian nạp, khởi động; một model tại một thời điểm | Biết model chạy ở đâu | UI | BR-9, FR-47, NFR-4, NFR-16 | Must | F-45 | S | M1 | AT-59, AT-97 | — | D-23 | hiện có · LỖI |
| F-48 | Chạy trên robot: nhiệm vụ, fps, độ dài tập, số tập, đặt lại, bước tối đa; xác nhận một lần "e-stop là phần mềm"; đếm ngược 3 s → tập → đặt lại; Tiếp / Dừng; **mọi camera** với nhãn "đầu vào policy · W×H → w×h" và tick; khớp: đo được / lệnh / đã gửi + biểu đồ 10 s; FPS, độ trễ suy luận p50 / p95, % bị cắt; model quá chậm 5 s → tạm dừng với lời khuyên | Thấy model làm gì, an toàn | UI | BR-9, BR-11, FR-48, NFR-3, NFR-4 | Must | F-46, F-47, F-28, F-29 | M | M1 | AT-60, AT-61, AT-97 | — | D-20 | hiện có · LỖI |
| F-49 | Ghi bộ dữ liệu đánh giá `eval_…` trong lúc chạy model | Đánh giá model | UI | BR-9, FR-49 | Should | F-48, F-38 | S | M2 | AT-62 | — | — | hiện có · ĐẠT\* |
| F-50 | Tóm tắt sau lượt chạy: thời lượng, số tập, nhiệt độ cao nhất từng khớp, cảnh báo, liên kết telemetry phiên và dataset đánh giá | Xem lại lượt chạy | UI | BR-9, FR-50 | Should | F-48 | S | M2 | AT-63 | — | — | hiện có · ĐẠT\* |
| F-51 | Trang Model: các model đã nhập (tên, loại, nguồn, xác minh, đã nạp), Nhập, Chạy, Xoá | Quản lý model | UI | BR-9, FR-51 | Should | F-45 | S | M2 | AT-64 | — | — | hiện có · ĐẠT\* |

## J. Chương trình: quỹ đạo, tư thế, nhận diện, khối (Blockly)

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-52 | Ghi quỹ đạo bằng tay leader (tên, giới hạn thời gian, đếm ngược, số mẫu), xem lại với đồ thị khớp, cắt đầu / cuối (gợi ý tự động đoạn đứng yên), Lưu / Bỏ; danh sách quỹ đạo (Nháp / Sẵn sàng / Cần kiểm tra) | Dạy chuyển động không cần huấn luyện | UI | BR-10, FR-52 | Should | F-24 | S | M2 | AT-65 | — | — | hiện có · ĐẠT\* |
| F-53 | Phát quỹ đạo ở 10–100 % (đến 150 % chỉ khi hồ sơ cho phép): đi chậm về điểm đầu (≤ 30°/s), mọi đường an toàn của phát lại; sau hiệu chỉnh lại → "Cần kiểm tra": "Kiểm tra ở 25 %" rồi "Đã đúng" | Lặp lại chuyển động an toàn | UI | BR-10, FR-53 | Should | F-52 | S | M2 | AT-66, AT-67 | REG-10 | D-12 | hiện có · LỖI |
| F-54 | Tư thế có tên: lưu từ tay hiện tại, từ điểm đầu / cuối quỹ đạo; xoá | Khối "đi tới tư thế" | UI | BR-10, FR-54 | Should | F-12 | S | M2 | AT-68 | — | — | hiện có · ĐẠT\* |
| F-55 | Bộ nhận diện camera: màu trong một vùng (vẽ vùng trên ảnh trực tiếp, quy tắc màu) hoặc bộ phân loại ảnh ONNX (tải model, nhãn); thử trực tiếp với nhãn đổi theo vật | Robot "thấy" để rẽ nhánh | UI | BR-10, FR-55 | Should | F-22 | M | M2 | AT-69 | — | — | hiện có · ĐẠT\* |
| F-56 | Trình soạn chương trình khối (Blockly, giao diện Hibiscus): tạo chương trình mới (nút luôn mở form và đặt con trỏ vào ô tên; tên không có chữ Latin vẫn nhận được mã hợp lệ; nói rõ chương trình lưu cho hồ sơ nào), các nhóm khối Chuyển động / AI / Điều khiển / Điều kiện / Dữ liệu / Đầu ra, lưu, kiểm tra và đánh dấu khối lỗi, danh sách lỗi khi tải thất bại có "Thử lại" | Lập trình bằng kéo thả | UI | BR-10, FR-56 | Should | F-52, F-54 | M | M2 | AT-70 | REG-9, REG-21 | D-24 | hiện có · LỖI |
| F-57 | Chạy thử (dry run) trên tay giả lập, giả lập điều kiện (camera thấy gì, kẹp giữ vật); bắt buộc chạy thử thành công phiên bản đó trước khi "Chạy trên robot" | Thử trước khi tay thật chạy | UI | BR-10, BR-5, FR-57 | Should | F-56 | S | M2 | AT-71 | — | — | hiện có · ĐẠT\* |
| F-58 | Chạy trên robot: xác nhận các khối cần đồng ý, Tạm dừng / Tiếp tục / Dừng, bảng người vận hành (nút, phím, câu hỏi), biến, giá trị điều kiện gần nhất, nhật ký, lịch sử các lần chạy; e-stop / nhiệt dừng trong một nhịp, lần chạy kết thúc `estopped`; danh sách chương trình luôn trả lời kể cả khi robot bận / dừng khẩn | Chạy tác vụ thật | UI | BR-10, BR-5, FR-58 | Should | F-57, F-28 | M | M2 | AT-72 | REG-9, REG-10, REG-21 | D-24 | hiện có · LỖI |
| F-59 | Tín hiệu ngoài: HTTP (`POST /api/v1/signals/<tên>` có token), MQTT (cấu hình URL và topic), khối "thông báo" qua webhook, khối "đặt tín hiệu" | Kỹ sư nối với hệ thống khác | API, UI | BR-10, BR-11, FR-59 | Could | F-58 | M | M3 | AT-73 | — | — | hiện có · ĐẠT\* |
| F-60 | Khối "chạy mô hình … trong … s" / "… đến khi …" trong chương trình | Ghép model với quỹ đạo | UI | BR-10, FR-60 | Could | F-58, F-48 | S | M3 | AT-74 | — | — | hiện có · ĐẠT\* |

## K. Robot 3D

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-61 | Robot 3D (SO-101 follower) vẽ theo vị trí khớp trực tiếp, mỗi động cơ tô màu theo nhiệt độ (màu xám / "chưa có số đo" khi không rõ), nhãn tay thật / tay giả lập, kéo xoay / phóng to, Đặt lại góc nhìn, Ẩn / Hiện; trình duyệt không có WebGL thì ẩn kèm lời giải thích | Nhìn tổng thể nhanh | UI | BR-6, FR-61 | Should | F-31 | S | M2 | AT-75 | — | — | hiện có · ĐẠT\* |
| F-62 | Xem trước quỹ đạo bằng tay mờ (ghost) trước khi phát lên robot: Phát / Tạm dừng / kéo vị trí | Không bất ngờ khi phát | UI | BR-10, FR-62 | Should | F-61, F-52 | S | M2 | AT-76 | — | — | hiện có · ĐẠT\* |

## L. Chẩn đoán

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-63 | `hibiscus-station doctor [--verbose] [--no-ping] [--no-cameras] [--out DIR]`: phiên bản, cổng USB (VID:PID, ai đang giữ), camera, tệp hiệu chỉnh, hồ sơ, trạng thái Station đang chạy, 200 dòng log cuối, kiểm tra chỉ-đọc từng tay (id, model, firmware, điện áp, nhiệt độ, trạng thái, EEPROM so với tệp, tỉ lệ lỗi và độ trễ đọc, ước lượng teleop); mở đầu bằng **LIKELY PROBLEMS** khi có (FL-11); v0.2: thêm `Present_Current` / `Present_Load` và bản dump thô từng servo (K-11, SP-1); là lệnh hỗ trợ chép-dán từ hướng dẫn, cùng loại với lệnh cài (FL-5); tạo zip không chứa token | Khách gửi một tệp, nhà cung cấp tìm ra lỗi | CLI | BR-12, FR-63 | Must | F-1 | M | M0 | AT-77 | REG-2, REG-13 | D-15, D-21, K-11 | hiện có · LỖI |
| F-64 | Nhật ký `station.log` (UTF-8, xoay vòng), dòng khởi động (chế độ giả lập / thật, thư mục dữ liệu, hồ sơ), mọi lỗi bus; `-v` in ra màn hình | Truy vết sự cố | CLI | BR-12, FR-64 | Must | F-4 | S | M1 | AT-78 | REG-18 | — | hiện có · ĐẠT\* |
| F-65 | `hibiscus-station health` (mã thoát 0 khi bản đang chạy trả lời) cho Docker / systemd | Giám sát tự động | CLI | BR-12, FR-65 | Could | F-4 | S | M3 | AT-79 | — | — | hiện có · ĐẠT\* |

## M. Cài đặt, ngôn ngữ, giao diện

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-66 | Trang Cài đặt: ngưỡng nhiệt (kiểm tra quy tắc RULE-4, báo lỗi bằng lời), tần suất đọc telemetry, xem trước camera (rộng, fps), dead-man cho phát lại, thư mục dữ liệu, máy chủ (huỷ ghép nối), phiên bản Station / lerobot / thiết bị, nhãn chế độ demo | Kỹ sư chỉnh, người mới không cần | UI | BR-11, FR-66 | Must | F-4 | S | M1 | AT-80 | — | D-5 | hiện có · LỖI |
| F-67 | Song ngữ Tiếng Việt / English: tự chọn theo trình duyệt (mặc định tiếng Việt), đổi ngay trên thanh trên, mọi chuỗi có ở cả hai ngôn ngữ | Người Việt dùng được | UI | BR-1, BR-14, FR-67, FR-73, NFR-10 | Must | F-4 | M | M1 | AT-81, AT-91 | — | D-5 (= K-4), D-12 (= K-3) | hiện có · LỖI |
| F-68 | Giao diện pixel Hibiscus ngày / đêm (theo hệ thống, đổi được), màn hình máy tính và điện thoại, đi được bằng bàn phím, nhãn cho trình đọc màn hình, linh vật Hibi đổi tâm trạng theo trạng thái | Dễ nhìn, dễ dùng | UI | BR-14, FR-68, NFR-11 | Must | F-4 | L | M1 | AT-82, AT-83 | — | D-13, D-14 | hiện có · LỖI |

## N. Cập nhật và dữ liệu

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Lỗi / khoảng trống đã biết | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-69 | Cập nhật bản wheel (Windows / Linux): chạy lại lệnh cài đặt với phiên bản mới; hồ sơ, hiệu chỉnh, dataset, model, quỹ đạo, chương trình giữ nguyên; quay lại bản cũ bằng cùng cách; P-1, QĐ-3 = A: cùng lệnh một dòng, thêm số phiên bản để quay lại | Lên bản mới không mất gì | CLI | BR-15, FR-69 | Must | F-1 | M | M1 | AT-84 | — | K-8, D-18 (= K-6), P-1 | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-70 | Docker: `hibiscus-station-ctl backup [--full]`, `restore`, `update [TAG]` (sao lưu, kéo image, khởi động lại, kiểm tra sức khoẻ, tự quay lại khi lỗi), `rollback` | Máy robot tự quản | CLI | BR-15, FR-70 | Could | F-3 | M | M3 | AT-85 | — | — | hiện có · KHÔNG KIỂM ĐƯỢC |
| F-71 | Dữ liệu tách bạch và bền: ghi tệp nguyên tử, UTF-8, thư mục dữ liệu riêng cho demo; dataset là LeRobot nguyên bản; telemetry đi kèm nằm cạnh | Không hỏng dữ liệu | — | BR-15, FR-71, NFR-15, NFR-16 | Must | F-4 | S | M1 | AT-86 | REG-2, REG-18 | — | hiện có · ĐẠT\* |


## Lỗi đã biết (D-n)

Lỗi so với chuẩn chất lượng trong bản 0.2.8. Theo quy tắc zero-defect, **mọi** lỗi dưới đây (kể cả
Low) làm tính năng của nó FAIL cho tới khi sửa, có test fail-trước-pass-sau và QC chạy lại AT; chỉ khách
hàng miễn được, bằng văn bản, theo **mã lỗi**. D-1 – D-18: Tech Lead tái hiện bằng chạy thử
([REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md) §4, có bước tái hiện). D-19 – D-23: SA tìm ra khi đọc mã
([REVIEW-SA.md](REVIEW-SA.md)); QC xác nhận bằng chạy thử khi bắt đầu M1 (OI-2; D-19 chỉ xác nhận được trên Windows).
D-24, D-25: khách hàng báo từ hiện trường (bản 0.2.9, check_ver_2.9, 2026-11-18), kèm quyết định của khách.

| D | Mức | Tính năng | Yêu cầu / AT | Lỗi (tóm tắt) | Nguồn | Sửa ở mốc |
|---|---|---|---|---|---|---|
| D-1 | High | F-17 | NFR-18, AT-2 | Test e2e Playwright của repo đỏ (tìm thẻ "Follower" đã bỏ từ 0.2.7): luồng chính không có test trình duyệt chạy được | Tech Lead | M0 |
| D-2 | Medium | F-38, F-40 | FR-38, FR-73, AT-48, AT-51 | Trang Ghi / chi tiết dataset gây `500 internal_error` khi đọc tập đang lưu dở | Tech Lead | M1 |
| D-3 | Medium | F-4 | FR-4, AT-6 | Cổng bị chương trình khác giữ: in / mở liên kết đăng nhập tới chương trình kia, rồi lỗi uvicorn thô, không gợi ý `--port` | Tech Lead | M1 |
| D-4 | Low | F-4 | FR-4, AT-6 | `hibiscus-station url` in liên kết chết (mã 0) khi Station đã tắt; không tìm được bản demo | Tech Lead | M1 |
| D-5 | Medium | F-7, F-25, F-66, F-67 | FR-7, FR-73, NFR-10, AT-10, AT-33, AT-80, AT-91 (= K-4) | Dòng tiếng Anh / chữ máy (có đường dẫn đầy đủ) dưới câu tiếng Việt; thiếu "°" | Tech Lead | M1 |
| D-6 | Medium | F-28 | FR-28, AT-37 | Thả lỏng sau e-stop không hiện "Hãy đỡ tay robot" | Tech Lead | M1 |
| D-7 | Medium | F-19 | FR-19, AT-26 | Kiểm tra hai tay: kẹp đo % nhưng báo "lệch hơn 20°"; luôn liệt kê cả 3 nguyên nhân | Tech Lead | M1 |
| D-8 | Medium | F-5 | FR-5, AT-7 | Demo: teleop bị `leader_far` ngẫu nhiên, Kiểm tra hai tay luôn lệch (tay leader giả quét liên tục) | Tech Lead | M1 |
| D-9 | High | F-24 | NFR-1a, NFR-2, AT-31 (REG-5) | Adapter latency 8 ms, cử động nhanh: 86 Hz, 84,6 % nhịp bị cắt, trễ bám 83 ms so với LeLab 68 ms | Tech Lead | M1 (sau số đo UAT-0) |
| D-10 | Low | F-22, F-24 | FR-24, NFR-12 | "FPS – / 30" khi chọn 250; "Bước 1292" là bộ đếm nhịp; "tick khung hình" lẫn thuật ngữ | Tech Lead | M1 |
| D-11 | Low | F-24 | FR-24, NFR-12 | Bảng Khớp không có đơn vị (bước thô trước hiệu chỉnh, ° / % sau) | Tech Lead | M1 |
| D-12 | Low | F-53, F-67 | NFR-10, AT-91 (= K-3) | 6 chuỗi "Hiệu chuẩn"; "Hãy reset nút dừng khẩn cấp" cạnh "Đã an toàn, đặt lại"; tên menu Windows bằng tiếng Anh | Tech Lead | M1 / M2 |
| D-13 | Low | F-28, F-68 | NFR-11, AT-82 | Nút DỪNG nổi che chú thích Robot 3D ở 1280 px khi đang ghi | Tech Lead | M1 |
| D-14 | Low | F-68 | NFR-11, AT-82 | Chữ bị cắt ở 390 px (chip robot "Chưa kế…") | Tech Lead | M1 |
| D-15 | Low | F-63 | FR-63, AT-77 (+ K-11) | `doctor`: "ConnectError" khi Station đã tắt; cổng bị giữ không vào LIKELY PROBLEMS; chưa đọc dòng / tải | Tech Lead | M0 |
| D-16 | Low | F-45 | FR-73, AT-57 | `POST /models/import` body không phải JSON → 500 (chỉ qua API) | Tech Lead | M1 |
| D-17 | Low | F-17 | FR-17, REG-4 | Mã chết "toàn vòng" của `wrist_roll` (`calibrate.full_turn`) còn trong sản phẩm | Tech Lead | M1 |
| D-18 | Low | F-3, F-69 | FR-76 (= K-1, K-6) | README / README.vi ghi image `0.2.1`; liên kết CHANGELOG dừng ở 0.2.2 | Tech Lead | M1 |
| D-19 | High | F-4, F-38 | FR-75, AT-95 | Windows: **đóng cửa sổ console** không dừng an toàn (Windows giết tiến trình sau ~5 s, `shutdown()` không chạy): tay giữ mô-men ở mục tiêu cuối, tập đang ghi có thể không được `finalize` | SA-W3 | M1 (SP-7, P-6) |
| D-20 | Medium | F-48 | NFR-4, AT-97 | Suy luận chạy trong nhịp: với model chậm (SmolVLA / CPU yếu) lệnh giữ và dead-man chỉ chạy sau khi suy luận xong (chuyển động vẫn ≤ 5°) | SA-N3 | M1 (P-2) |
| D-21 | Low | F-63 | FR-63, AT-77 | `doctor` khuyên "đặt USB latency timer 1 ms": không làm được trên bộ chuyển WCH CH340 / CH343 của SO-101 | SA-N2 | M0 |
| D-22 | Medium | F-12 | FR-12, AT-96 | Linux: Station mở được tty mà LeLab đang giữ (không kiểm độc quyền, spec ghi `TIOCEXCL` nhưng mã không có): hai chương trình cùng lái bus | SA-F2 | M1 (SP-5, P-7) |
| D-23 | Low | F-47 | FR-47, FR-73, NFR-16 | Model cần backbone từ HF Hub (SmolVLA, adapter PEFT) khi không có mạng: lỗi thô thay vì câu dịch | SA-F4 | M1 |
| D-24 | Low | F-56, F-58 | FR-56, FR-58, AT-70, AT-72 (REG-21) | Cảnh báo `first_motion_far` ("Chuyển động đầu tiên bắt đầu xa tư thế hiện tại của tay") tính một lần theo tư thế lúc kiểm, nằm mãi trên khối chuyển động đầu tiên kể cả sau khi chạy xong, dù trình phát luôn đi chậm (minimum-jerk) về điểm đầu. Quyết định của khách: **"Đổi thành thông tin, tự cập nhật"** → mức `info` (không phải cảnh báo, không đếm, không hỏi xác nhận), câu "Tay sẽ đi chậm về điểm bắt đầu của chuyển động này (cách X°)", kiểm lại khi tay di chuyển / khi chạy xong, biến mất khi tay đã ở trong ngưỡng | Khách hàng: báo cáo hiện trường của khách check_ver_2.9 (2026-11-18) | M1 |
| D-25 | Medium | F-7, F-41 | FR-7, FR-41, AT-10, AT-52 (REG-22) | Bước Huấn luyện hiện ổ khoá và "Bước này đang bị khoá — Hãy ghép nối với máy chủ Hibiscus trước" trong khi form ghép nối vẫn dùng được ngay đó; form nhận cả liên kết OneDrive (khách đã dán một liên kết OneDrive dài vào ô địa chỉ máy chủ). Quyết định của khách: **"Không cần robot, nói rõ hơn"** → Huấn luyện chạy trên máy chủ, không khoá: câu trung tính "Kết nối máy chủ Hibiscus để huấn luyện (không cần robot)."; form kiểm địa chỉ trước khi gửi (phải là http(s), không phải liên kết OneDrive / SharePoint / Google Drive / Dropbox), báo lỗi ngay dưới ô, nút Ghép nối tắt tới khi hợp lệ | Khách hàng: báo cáo hiện trường của khách check_ver_2.9 (2026-11-18) | M1 |

Tổng: **25 lỗi**: 3 High (D-1, D-9, D-19) · 10 Medium (D-2, D-3, D-5 – D-8, D-20, D-22, D-25) · 12 Low. Không có
Critical. D-24, D-25 (2026-11-18) từ báo cáo hiện trường của khách trên bản 0.2.9 (check_ver_2.9); sửa ở M1 theo
quyết định của khách dù F-41, F-56, F-58 thuộc M2.

**Còn mở, chưa có mã D** (khoảng trống của BA, SRS §8, Tech Lead chưa kiểm lại): K-2 (tài liệu UAT phần
cứng lỗi thời, F-13 / F-17), K-5 (hướng dẫn ghi 5° cho mọi chuyển động, F-30), K-7 (spec dev lỗi thời), K-8
(cập nhật trên Windows cần gõ lệnh có số phiên bản, F-1 / F-69 → giải quyết bằng P-1), K-10 (hướng dẫn tiếng
Việt phải nói Windows dùng wheel, không Docker), **REG-13** (servo của khách báo 0 °C và dòng ~1000 thô:
F-31, F-33, chờ SP-1).

**Khoảng trống quy trình (không phải lỗi của tính năng, chặn phát hành):** P-1 môi trường cài trên PC khách
khác môi trường đã kiểm (SA-P1); CI Windows bỏ qua ≈ 16 test bus pty (SA-C1, NFR-18); không có e2e trên
Edge / Firefox (SA-C2); gói `hibiscus` khai giấy phép "Proprietary" và 3 cảnh báo GHSA bị bỏ qua chưa có lý
do (SA-L1, NFR-14; QĐ-4 = A: Hibiscus CLI v0.1.2 Apache-2.0, phụ thuộc ngoài **EXT-1**,
BRD §7, chặn AT-98).

## Đề xuất thay đổi (P-n) · đã duyệt cùng bộ tài liệu v1.0 (2026-11-17)

Mỗi mục là sửa lỗi hoặc đóng gói để đạt chuẩn; không thêm màn hình hay chức năng mới. Khách đã duyệt cả tám
mục cùng bộ v1.0.

| P | Thay đổi | Lý do | Tính năng / yêu cầu | Đóng lỗi / flag | Effort |
|---|---|---|---|---|---|
| P-1 | Lệnh cài **một dòng** PowerShell (`install.ps1` đính kèm bản phát hành): cài uv nếu thiếu, cài Station với bộ phụ thuộc cố định từ `uv.lock` và wheel dựng sẵn của lerobot / hibiscus (không cần git); cùng lệnh để **cập nhật**, thêm số phiên bản để **quay lại** | `uv tool install <wheel>` giải lại phụ thuộc theo ngày cài và cần git: PC khách nhận thư viện khác bản QC đã kiểm | F-1, F-69, FR-1, FR-69, AT-1, AT-84 | SA-P1, Q-4, K-8 · **QĐ-3 = A** | M (SA), Tech Lead xác nhận (OI-1) |
| P-2 | Từ chối chạy model khi lần suy luận khởi động trên máy đó > 500 ms (½ dead-man), câu "Model quá chậm trên máy này cho an toàn dead-man. Dùng CUDA hoặc model nhỏ hơn" | Dead-man / lệnh giữ trễ bằng thời gian suy luận | F-47, F-48, NFR-4, AT-97 | D-20, SA-N3 | Tech Lead ước khi bắt đầu M0 (OI-1) |
| P-3 | Khi **không** động cơ follower nào báo nhiệt độ thật: xác nhận rõ ràng mỗi lần kết nối; phiên không có người cầm leader (chạy model, phát lại, quỹ đạo, chương trình) dừng sau 10 phút liên tục (kỹ sư đổi được); teleop / ghi không giới hạn | Bảo vệ nhiệt của Station không hoạt động trên tay của khách (0 °C); chỉ banner là chưa đủ | F-33, FR-33, NFR-6, AT-93 | SA-S1, Q-5 · **QĐ-1 = A** | Tech Lead ước khi bắt đầu M0 (OI-1) |
| P-4 | Chế độ demo: tay leader giả đứng theo follower khi bắt đầu phiên và khi Kiểm tra | Demo phải chạy ổn định cho người mới | F-5, FR-5, AT-7 | D-8, FL-10 | trong F-5 (M) |
| P-5 | Người dùng chỉ thấy câu dịch theo `code`; lý do thô của Station nằm trong mục "Chi tiết kỹ thuật" thu gọn (cho kỹ sư) và trong log / `doctor` | "Lý do chính xác của Station" mâu thuẫn với "không chữ máy / tiếng Anh" | F-7, FR-7, FR-73, AT-10 | D-5, FL-1 | trong F-7 (S) |
| P-6 | Windows: bắt sự kiện đóng cửa sổ / đăng xuất / tắt máy, chạy đường dừng rút gọn ≤ 4 s (e-stop giữ → tắt mô-men theo hồ sơ, bỏ bước về nghỉ → `finalize` dataset nếu kịp) | Người mới hay đóng cửa sổ; hôm nay tay giữ mô-men, tập ghi dở có thể hỏng | F-4, FR-75, AT-95 | D-19, SA-W3 | Tech Lead ước khi bắt đầu M0 (OI-1; SP-7) |
| P-7 | Linux: trước khi mở cổng, kiểm tiến trình khác đang giữ (như `doctor` đã làm) → `port_busy` nêu tên tiến trình | Tránh hai chương trình cùng lái bus | F-12, FR-12, AT-96 | D-22, SA-F2 | Tech Lead ước khi bắt đầu M0 (OI-1; SP-5) |
| P-8 | Nếu SP-1 không xác nhận được đơn vị dòng của STS3215: hiện dòng là "—" ở mọi nơi và bỏ dòng "giới hạn dòng X A" khỏi ngăn chi tiết (ghi trong ghi chú phát hành) | Không hiện số chưa chắc đúng | F-31, FR-31, NFR-13, AT-40 | SA-N4 | S |

## Mốc (Tech Lead)

Theo [REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md) §5, BA bổ sung các mục mới của SA (đánh dấu ✚). Mỗi mốc kết
thúc bằng QC trên đúng bản cài của mốc.

| Mốc | Nội dung | Effort dev (Tech Lead) | Kết thúc khi |
|---|---|---|---|
| **M0 · Nền kiểm** (tuần 1) | D-1 (e2e xanh); CI xanh Linux / Windows / macOS; ma trận ảnh Playwright × sáng / tối × 1280 / 390 + axe tự động (FL-7); `doctor` đọc dòng / tải + dump thô (K-11, D-15, ✚ D-21, ✚ SP-1); chạy thử phát hành nháp (FL-12); ✚ SP-2 (cổng COM ảo trên CI Windows); ✚ SP-3 + P-1 (cài trên Windows sạch không git) | 10 ngày (+ ✚ chưa ước) | Khách nhận bản `doctor` mới → **UAT-0** |
| **M1 · Must** | 44 tính năng Must (F-63 ở M0; F-72 thêm ở v1.1, CR-1, +2 – 3 ngày) cùng 3 Should có mốc M1 (F-2, F-18, F-26): D-2 – D-14, D-16 – D-18, K-2 – K-5, K-8, D-9 (sau số đo UAT-0), REG-13 + QĐ-1; ✚ D-19 / P-6, D-20 / P-2, D-22 / P-7, D-23, P-3, P-8 | 48 ngày (+ ✚ chưa ước) | QC nội bộ PASS mọi phần [Vendor] của Must → **UAT-1** |
| **M2 · Should** | 19 tính năng Should: máy chủ Hibiscus (F-41 – F-44), Chương trình (F-52 – F-58, F-61, F-62), Phiên (F-37), Bộ dữ liệu nâng cao (F-39), phát lại (F-27), model nâng cao (F-49 – F-51) | 17 ngày | QC PASS → **UAT-2** |
| **M3 · Could** | Docker x86_64 `-cpu` (F-3, F-70), LAN (phần LAN của F-6), tín hiệu ngoài (F-59), model trong chương trình (F-60), `health` (F-65) | 7 ngày | Đạt thì vào v1.0; không đạt thì ra khỏi v1.0, không chặn |

**Tổng đã ước: ≈ 82 ngày công dev** (48 S + 21 M + 2 L = 76 theo tính năng, + 6 cho nền kiểm), chưa tính QC
(~30 %) và chờ UAT; với 3 dev song song ≈ 6 – 7 tuần lịch. Các mục ✚ (P-1 – P-3, P-6, P-7, SP-1 – SP-3, SP-7)
Tech Lead ước khi bắt đầu M0 (OI-1). Phát hành v1.0 = M0 + M1 + M2 đạt (M3 nếu đạt). Đường găng: báo cáo `doctor` của
khách ở UAT-0 (REG-13, F-31, F-33, QĐ-1) và số đo adapter (D-9, F-24).

## Ma trận truy vết

Mỗi BR → yêu cầu SRS → tính năng → AT. FR-n mô tả F-n cùng số; FR-72 – FR-76 là yêu cầu chung; FR-77 mô tả F-72 (CR-1, số FR-72 đã dùng). Kết quả
QC điền ở `FEATURES-APPROVED.md` sau khi duyệt.

| BR | FR | NFR | F | AT |
|---|---|---|---|---|
| BR-1 Người mới cài và dùng trên Windows bằng tiếng Việt | FR-1 – FR-4, FR-7, FR-67, FR-73 | NFR-5, NFR-9, NFR-10 | F-1 – F-4, F-7, F-67 | AT-1 – AT-6, AT-10, AT-81, AT-87, AT-91 |
| BR-2 Đúng tay thật, không nhầm leader / follower | FR-5, FR-8 – FR-12, FR-15 | — | F-5, F-8 – F-12, F-15 | AT-7, AT-11 – AT-17, AT-21, AT-96 |
| BR-3 Hiệu chỉnh chuẩn LeLab | FR-16 – FR-20 | NFR-15 | F-16 – F-20 | AT-22 – AT-27 |
| BR-4 Teleop không trễ hơn LeLab | FR-24 – FR-26 | NFR-1a – NFR-1c, NFR-2, NFR-8 | F-24 – F-26 | AT-31 – AT-34, AT-89, AT-90 |
| BR-5 An toàn và phục hồi | FR-13, FR-14, FR-25, FR-28 – FR-30, FR-32 – FR-36, FR-57, FR-58, FR-72, FR-74, FR-75 | NFR-3a – NFR-3c, NFR-4, NFR-6, NFR-7 | F-4, F-13, F-14, F-25, F-28 – F-30, F-32 – F-36, F-57, F-58 | AT-18 – AT-20, AT-33, AT-36 – AT-39, AT-42, AT-44 – AT-46, AT-71, AT-72, AT-88, AT-93 – AT-95, AT-97 |
| BR-6 Số liệu đúng, không báo động giả | FR-31 – FR-34, FR-37, FR-61 | NFR-12, NFR-13 | F-31 – F-34, F-37, F-61 | AT-40 – AT-44, AT-47, AT-75, AT-92 |
| BR-7 Thu dữ liệu LeRobot có camera | FR-21 – FR-23, FR-27, FR-38 – FR-40, FR-77 | NFR-8, NFR-15 | F-21 – F-23, F-27, F-38 – F-40, F-72 | AT-28 – AT-30, AT-35, AT-48 – AT-51, AT-99 |
| BR-8 Máy chủ Hibiscus (Should) | FR-41 – FR-44 | NFR-17 | F-41 – F-44 | AT-52 – AT-56 |
| BR-9 Chạy model, thấy camera và sức khoẻ động cơ | FR-22, FR-45 – FR-51 | NFR-3a, NFR-4, NFR-16 | F-45 – F-51 | AT-57 – AT-64, AT-97 |
| BR-10 Lập trình không cần huấn luyện (Should) | FR-52 – FR-60, FR-62 | — | F-52 – F-60, F-62 | AT-65 – AT-74, AT-76 |
| BR-11 Tuỳ chọn nâng cao cho kỹ sư | FR-18, FR-30, FR-48, FR-59, FR-66 | — | F-18, F-30, F-48, F-59, F-66 | AT-25, AT-39, AT-60, AT-73, AT-80 |
| BR-12 Báo cáo chẩn đoán | FR-63 – FR-65 | — | F-63 – F-65 | AT-77 – AT-79 |
| BR-13 Không lỗi hiện trường tái diễn | FR-76; REG-1 – REG-23 | NFR-18 | mọi F có cột REG | AT-2 + AT ghi ở từng REG ([REGRESSION.md](REGRESSION.md)) |
| BR-14 Song ngữ, sáng / tối, máy tính và điện thoại | FR-67, FR-68 | NFR-10, NFR-11 | F-67, F-68 | AT-81 – AT-83, AT-91 |
| BR-15 Cập nhật không mất dữ liệu | FR-69 – FR-71, FR-75 | NFR-15, NFR-16 | F-69 – F-71 | AT-84 – AT-86, AT-95 |
| BR-16 Chỉ cục bộ, trừ chế độ LAN | FR-6 | NFR-14 | F-6 | AT-8, AT-9, AT-98 |
| BR-17 Automation | — | — | **Won't v1.0** (W-1), dự kiến bản sau | — |
| BR-18 Nền tảng web | — | — | **Won't v1.0** (W-2) | — |

**NFR → AT (mỗi NFR được đo, không giả định):** NFR-1a / 1b / 1c → AT-31 · NFR-2 → AT-31, AT-89 · NFR-3a / 3b /
3c → AT-36, AT-88 · NFR-4 → AT-38, AT-97 · NFR-5 → AT-87 · NFR-6 → AT-42, AT-93 · NFR-7 → AT-19, AT-37, AT-45,
AT-54, AT-72, AT-94, AT-95 · NFR-8 → AT-90 · NFR-9 → AT-1 – AT-4 · NFR-10 → AT-81, AT-91, AT-99 · NFR-11 → AT-82, AT-83, AT-99 ·
NFR-12 → AT-43, AT-92 · NFR-13 → AT-40 · NFR-14 → AT-8, AT-57, AT-98 · NFR-15 → AT-27, AT-47, AT-49, AT-86 ·
NFR-16 → AT-86 · NFR-17 → AT-54 · NFR-18 → AT-2.

Kiểm tra: 72 / 72 tính năng có ≥ 1 AT (F-72 → AT-99, v1.1); 16 / 16 BR trong phạm vi có ≥ 1 F; BR-17, BR-18 là Won't theo quyết
định của khách ngày 2026-11-17.

## Không làm trong v1.0 (Won't)

| ID | Mục | Lý do | Kế hoạch |
|---|---|---|---|
| W-1 | **Automation** (nhánh `feat/automation`, `feat/auto-kin`, `feat/auto-ui`, `feat/auto-vision`, `feat/auto-world`) | Quyết định của khách hàng 2026-11-17 | Bản sau, qua CR |
| W-2 | Nền tảng web Hibiscus | "Sản phẩm = chỉ Hibiscus Station" | Sau |
| W-3 | Huấn luyện trên máy robot | RULE-15 | — |
| W-4 | Robot khác SO-100 / SO-101 | Phạm vi | Sau |
| W-5 | Cài ID / baudrate động cơ | Dùng `lerobot-setup-motors` | — |
| W-6 | Thông báo "có bản mới" / cập nhật trong ứng dụng | Không phải tính năng hiện có; cập nhật bằng lệnh một dòng (P-1) | Đề xuất CR |
| W-7 | Đẩy lên HF Hub, sửa / gộp dataset | Máy chủ đã có | — |
| W-8 | Suy luận ONNX / bất đồng bộ / từ xa | Phạm vi | — |
| W-9 | **Nền tảng bản xem trước** (QĐ-2 = A): macOS, wheel Linux arm64, Docker `-cuda`, Raspberry Pi 5, Jetson Orin | Nhà cung cấp không có máy để kiểm; chuẩn chất lượng không cho nghiệm thu nền tảng chưa kiểm. Vẫn cài được, README / ghi chú phát hành / `install.sh` ghi "bản xem trước, không thuộc nghiệm thu v1.0" kèm lỗi đã biết; lỗi ở đó không tính là lỗi của v1.0 | Nghiệm thu khi có máy (CR) |
| W-10 | Nút "Tạo báo cáo chẩn đoán" trong Cài đặt (thay lệnh `doctor`) | FL-5; v1.0 giữ lệnh chép-dán | Đề xuất CR |
| W-11 | Phím dừng toàn cục / nút dừng USB (khi cửa sổ Station không được chọn) | SA-S2; v1.0: hướng dẫn nói rõ Space chỉ có tác dụng khi cửa sổ Station đang được chọn, khuyến nghị công tắc ngắt nguồn follower | Đề xuất CR |
| W-12 | Nhận diện camera theo đường dẫn thiết bị trên Windows (thay số 0, 1, 2…) | SA-W4; v1.0: hướng dẫn và UAT có bước "Thử từng camera" sau khi cắm lại | Đề xuất CR |

## Chỉ dùng nội bộ (không phải tính năng của người dùng)

`POST /api/v1/mock/inject` (chèn lỗi giả lập, chỉ với `--mock`, cho demo và test e2e),
`hibiscus-station openapi` (xuất hợp đồng API cho nhà phát triển), `tests/sts_emulator.py`,
`tests/teleop_bench.py`. Không có AT người dùng; QC dùng chúng làm công cụ.

## Tổng hợp

| Nhóm | Số F | Must / Should / Could |
|---|---|---|
| A. Cài đặt và khởi động | 7 | 5 / 1 / 1 (F-6 Must, phần LAN Could) |
| B. Robot và cổng | 8 | 8 / 0 / 0 |
| C. Hiệu chỉnh | 5 | 4 / 1 / 0 |
| D. Camera | 3 | 3 / 0 / 0 |
| E. Teleop và phát lại | 4 | 2 / 2 / 0 |
| F. An toàn, nhiệt, telemetry | 10 | 9 / 1 / 0 |
| G. Ghi bộ dữ liệu | 4 | 3 / 1 / 0 (F-72 thêm ở v1.1, CR-1) |
| H. Máy chủ Hibiscus | 4 | 0 / 4 / 0 |
| I. Chạy model | 7 | 4 / 3 / 0 |
| J. Chương trình | 9 | 0 / 7 / 2 |
| K. Robot 3D | 2 | 0 / 2 / 0 |
| L. Chẩn đoán | 3 | 2 / 0 / 1 |
| M. Cài đặt, ngôn ngữ, giao diện | 3 | 3 / 0 / 0 |
| N. Cập nhật và dữ liệu | 3 | 2 / 0 / 1 |
| **Tổng** | **72** | **45 / 22 / 5** |

| Trạng thái vòng 1 | Số F | |
|---|---|---|
| ĐẠT\* (chưa thấy lỗi) | 33 | chưa phải PASS của QC; nhiều tính năng vẫn có bước UAT |
| LỖI | 22 | 23 lỗi D-n + K-n / REG-13 còn mở. So với Tech Lead (18): thêm F-12, F-47, F-48 (lỗi SA tìm ra) và F-66 (D-5 áp dụng cho F-66, Tech Lead ghi ĐẠT\*) |
| KHÔNG KIỂM ĐƯỢC | 16 | 11 chỉ Windows + tay thật / camera thật chứng minh được (F-1, F-9 – F-11, F-13, F-20, F-21, F-23, F-31, F-33, F-69); 5 cần máy chủ Hibiscus thử hoặc Docker do vendor dựng (F-41 – F-44, F-70) |
