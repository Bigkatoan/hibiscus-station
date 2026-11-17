# Hibiscus Station: danh sách tính năng v0.1 (2026-11-17) · trạng thái: bản nháp (vòng 1)

Đường cơ sở "như đã xây" của Station **0.2.8** (`main` `12f36da`). Mọi dòng có trạng thái
**hiện có** (existing): tính năng đã có trong sản phẩm, v1.0 phải đưa nó lên chuẩn chất lượng
(mọi AT đạt, không còn lỗi mở). Không có tính năng mới trong v1.0.

* **Ưu tiên** theo đề xuất mặc định của BA (BRD §9: Q-1 nền tảng, Q-2 liên kết Hibiscus, Q-3 Chương
  trình). Khách hàng có thể đổi.
* **Effort / Milestone**: Tech Lead điền ở bước rà soát (vòng 1 để trống: "TL").
* **AT** = mã trong [ACCEPTANCE.md](ACCEPTANCE.md). **FR** = mã trong [SRS.md](SRS.md) (FR-n mô tả F-n
  cùng số). **REG** = mục hồi quy trong [REGRESSION.md](REGRESSION.md).
* **Phụ thuộc**: theo quy tắc zero-defect, một tính năng FAIL kéo theo mọi tính năng phụ thuộc nó.
* Nơi xuất hiện: **UI** = trang / nút trên giao diện; **CLI** = lệnh terminal; **API** = chỉ qua API.

## A. Cài đặt và khởi động

| ID | Tính năng | Giá trị cho người dùng | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-1 | Cài đặt trên Windows 10/11 x64 bằng uv + wheel (một lệnh PowerShell cài uv, một lệnh cài Station; tuỳ chọn `--torch-backend cpu`) | Người mới cài được bằng chép-dán | CLI | BR-1, FR-1, NFR-9 | Must | — | TL | TL | AT-1, AT-2 | REG-1, REG-17, REG-18, REG-19 | hiện có |
| F-2 | Cài đặt trên Linux (x86_64 / arm64) bằng wheel, kèm unit systemd tuỳ chọn | Kỹ sư Linux | CLI | BR-1, FR-2 | Should | — | TL | TL | AT-3 | — | hiện có |
| F-3 | Cài đặt Docker trên Linux PC / Raspberry Pi 5 / Jetson Orin: `install.sh` (dò máy, chọn image cpu / cuda / jetson, luật udev, tự khởi động), `hibiscus-station-ctl` (status, logs, url, ports) | Máy robot không màn hình | CLI | BR-1, FR-3 | Could | — | TL | TL | AT-4 | — | hiện có |
| F-4 | Khởi động `hibiscus-station`: mở trình duyệt bằng liên kết đăng nhập một lần, chỉ một phiên bản chạy (lần chạy thứ hai in liên kết của bản đang chạy), `hibiscus-station url` in lại liên kết, `--port`, `--no-browser`, `--home` | Mở được giao diện ngay | CLI, UI | BR-1, FR-4, NFR-5 | Must | F-1 hoặc F-2 | TL | TL | AT-5, AT-6 | — | hiện có |
| F-5 | Chế độ demo `--mock`: tay, camera, policy giả lập; dữ liệu ở thư mục riêng `~/.hibiscus/station-demo`; chip **TAY GIẢ LẬP** trên thanh trên | Thử khi chưa có robot | CLI, UI | BR-2, FR-5 | Must | F-4 | TL | TL | AT-7 | REG-2 | hiện có |
| F-6 | Truy cập cục bộ an toàn: chỉ `127.0.0.1`, token mỗi lần chạy, cookie, danh sách Host cho phép, chặn CSRF; chế độ LAN chỉ khi bật đủ ba thiết lập (host, token cố định ≥ 32 ký tự, tên máy cho phép) | Không ai khác điều khiển được robot | CLI, UI | BR-16, FR-6, NFR-14 | Must (LAN: Could) | F-4 | TL | TL | AT-8, AT-9 | — | hiện có |
| F-7 | Trang Chào mừng và **thanh bước** (Robot · Hiệu chỉnh · Camera · Điều khiển tay · Ghi dữ liệu · Tải lên · Huấn luyện · Chạy model, cùng Bộ dữ liệu, Model, Phiên, Chương trình, Cài đặt): dấu ✓ khi xong, bước bị khoá mở trang nói lý do, liên kết tới bước cần làm trước, nút trên trang bị tắt | Người mới biết làm gì tiếp theo | UI | BR-1, FR-7 | Must | F-4 | TL | TL | AT-10 | REG-12 | hiện có |

## B. Robot và cổng

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-8 | Hồ sơ robot: tạo / sửa / xoá; loại SO-101 / SO-100; cổng follower (bắt buộc), cổng leader (không bắt buộc: chỉ chạy model); mã hiệu chỉnh mỗi tay (chọn được mã có sẵn, ví dụ của LeLab); khi kết thúc phiên: giữ nguyên hoặc về tư thế nghỉ rồi thả lỏng | Cấu hình ở một chỗ | UI | BR-2, FR-8 | Must | F-4 | TL | TL | AT-11 | — | hiện có |
| F-9 | Danh sách cổng USB serial: chỉ cổng USB, mô tả, VID:PID, đường dẫn ổn định (Linux `by-id`), cổng đang bị ai giữ; nút Làm mới | Chọn đúng cổng | UI | BR-2, FR-9 | Must | F-8 | TL | TL | AT-12 | — | hiện có |
| F-10 | Tìm cổng **theo vai trò**: "Tìm tay follower" / "Tìm tay leader", mỗi nút có hai cách (cử động trong ≤ 15 s, hoặc rút cáp trong ≤ 15 s); cổng tìm được vào đúng ô; không bao giờ đề xuất cổng đã gán cho tay kia | Không nhầm leader / follower | UI | BR-2, FR-10 | Must | F-9 | TL | TL | AT-13, AT-14 | REG-6 | hiện có |
| F-11 | Dò cổng chỉ-đọc (điện áp, model, firmware) và gợi ý vai trò (~5 V: thường là leader; ≥ 6,5 V: thường là follower); cảnh báo khi có vẻ nhầm; nút "Đổi chỗ follower ⇄ leader" (mã hiệu chỉnh đi theo vai trò); không bao giờ tự đổi | Phát hiện nhầm trước khi chạy | UI | BR-2, FR-11 | Must | F-9 | TL | TL | AT-15 | REG-6 | hiện có |
| F-12 | Kết nối / ngắt kết nối hồ sơ: tiến trình (mở cổng, bắt tay, cấu hình); lỗi nói rõ bước và lý do (cổng bận do LeLab / lerobot, động cơ thiếu / sai model / firmware lẫn, không ghi được cấu hình), thử lại 2 lần cho mỗi gói tin lỗi | Biết vì sao không kết nối được | UI | BR-2, FR-12 | Must | F-8 | TL | TL | AT-16, AT-17 | REG-14 | hiện có |
| F-13 | **Mất thiết bị USB** (Windows "Access is denied", thiết bị không sẵn sàng; Linux EIO / ENODEV): không thử lại vô ích, trạng thái lỗi `device_lost` với tay, cổng, thông báo hệ thống; trang giải thích bằng lời dễ hiểu kèm danh sách kiểm tra; nút "Kết nối lại" chờ cổng trở lại (kể cả số COM mới), cập nhật hồ sơ, ghi lại hiệu chỉnh | Phục hồi không cần khởi động lại | UI | BR-5, FR-13 | Must | F-12 | TL | TL | AT-18, AT-19 | REG-8 | hiện có |
| F-14 | Mô-men follower: bật / thả lỏng (cần xác nhận khi chưa có tư thế nghỉ); "Lấy tư thế hiện tại làm tư thế nghỉ"; bảng khớp và sức khoẻ động cơ ngay sau khi kết nối | Đỡ tay an toàn, có tư thế đỗ | UI | BR-5, FR-14 | Must | F-12 | TL | TL | AT-20 | — | hiện có |
| F-15 | Bảo vệ khỏi hồ sơ demo: khi chạy với tay thật, hồ sơ demo còn sót bị đánh dấu **DEMO**, không kích hoạt, không kết nối được (`demo_profile`); khi có cổng thật đang cắm, banner "Tạo hồ sơ cho tay thật" điền sẵn cổng | Không bao giờ điều khiển tay giả lập do nhầm | UI | BR-2, FR-15 | Must | F-8 | TL | TL | AT-21 | REG-2 | hiện có |

## C. Hiệu chỉnh

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-16 | Kiểm tra hiệu chỉnh khi vào trang: đọc EEPROM từng tay và so với mọi tệp trên máy; báo "đã hiệu chỉnh — dùng luôn"; nếu động cơ đang mang tệp khác (ví dụ của LeLab) thì đề xuất đúng tệp đó, một cú bấm "Dùng"; nếu động cơ không giữ được tệp thì "Ghi lại tệp" / "Hiệu chỉnh lại" | Không phải hiệu chỉnh lại khi đã có | UI | BR-3, FR-16 | Must | F-12 | TL | TL | AT-22 | REG-7 | hiện có |
| F-17 | Luồng hiệu chỉnh có hướng dẫn (follower → leader → kiểm tra): bước **Đặt home** (hình minh hoạ, tay thả lỏng), bước **Biên độ**: dấu tick cho **mọi** khớp kể cả `wrist_roll` khi đã quay đủ 100 bước (quy tắc LeLab), hiện min / vị trí / max trực tiếp, nút **Lưu** chỉ mở khi đủ mọi khớp; tệp lưu ở chỗ lerobot dùng | Hiệu chỉnh chuẩn LeLab, khoảng 1 phút mỗi tay | UI | BR-3, FR-17 | Must | F-12 | TL | TL | AT-23, AT-24 | REG-4, REG-7 | hiện có |
| F-18 | "Nâng cao: các tệp hiệu chỉnh": danh sách mọi tệp của tay đó (kể cả thư mục cũ của lerobot < 0.4 / LeLab), nhãn "của robot này" / "động cơ đang dùng" / "thuộc tay kia" / "không phải tệp hiệu chỉnh"; "Dùng tệp này" sao chép sang mã của tay (tệp cũ giữ lại `.bak-<thời gian>`); không đề xuất tệp khớp với tay kia | Kỹ sư chọn tệp cụ thể | UI | BR-3, BR-11, FR-18 | Should | F-16 | TL | TL | AT-25 | — | hiện có |
| F-19 | Kiểm tra hai tay: follower đứng yên, người dùng đặt leader giống follower, bấm Kiểm tra → độ lệch từng khớp; > 20° (kẹp: 20 %) bị đánh dấu với lý do (sai tư thế / sai tệp / nhầm cổng); "Thử teleop" hoặc "Vẫn thử teleop" | Bắt lỗi trước teleop | UI | BR-3, FR-19 | Must | F-17 | TL | TL | AT-26 | REG-7 | hiện có |
| F-20 | Tệp hiệu chỉnh dùng chung hai chiều với lerobot và LeLab (cùng thư mục, cùng định dạng) | Không bị khoá vào Station | UI, CLI | BR-3, FR-20 | Must | F-17 | TL | TL | AT-27 | — | hiện có |

## D. Camera

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-21 | Tìm camera (Windows / macOS: số 0, 1, 2…; Linux: `/dev/video*`, RealSense nếu có), không mở camera Station đang dùng; "Thử": ảnh chụp, fps đo được; cảnh báo khi fps đo < 90 % yêu cầu | Biết camera nào dùng được | UI | BR-7, FR-21 | Must | F-12 | TL | TL | AT-28 | REG-20 | hiện có |
| F-22 | Camera đã cấu hình: tên (khoá `observation.images.<tên>`), độ phân giải, fps, định dạng (MJPG…), xoay; xem trực tiếp trên mọi màn hình chuyển động; mỗi camera chỉ một chủ sở hữu | Thấy camera khi ghi và chạy model | UI | BR-7, BR-9, FR-22 | Must | F-21 | TL | TL | AT-29 | — | hiện có |
| F-23 | Camera đứng hình / mất trong phiên: sau 0,5 s cảnh báo và dừng đồng hồ tập (ghi, chạy model); sau 3 s phiên dừng với lý do `camera_lost`, tay vẫn được giữ, dataset vẫn hợp lệ; teleop không bắt buộc camera | Không ghi dữ liệu hỏng | UI | BR-7, FR-23 | Must | F-22 | TL | TL | AT-30 | REG-15 | hiện có |

## E. Điều khiển tay (teleop) và phát lại

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-24 | Teleop leader → follower: vòng nhanh (mặc định 250 Hz, tối đa 300; chậm hơn nếu bus chậm), giới hạn bước 30°/nhịp cho phiên do leader điều khiển, kẹp vào dải hiệu chỉnh; hiện "độ trễ ~X ms, Y Hz", bảng khớp leader / follower / bị cắt, camera (nếu có), sức khoẻ động cơ, đồng hồ phiên | Điều khiển mượt như LeLab | UI | BR-4, FR-24, NFR-1, NFR-2 | Must | F-17, F-19 | TL | TL | AT-31, AT-32 | REG-5, REG-7 | hiện có |
| F-25 | Leader lệch xa (> 30° một khớp): teleop từ chối, nêu khớp và độ lệch, đề nghị "Đưa tay follower về tư thế tay leader" (chậm, tối đa 30°/s, dead-man, e-stop được) rồi teleop bắt đầu | Không giật tay khi bắt đầu | UI | BR-4, BR-5, FR-25 | Must | F-24 | TL | TL | AT-33 | — | hiện có |
| F-26 | Cảnh báo "tay follower không theo kịp" khi giới hạn bước cắt > 20 % số nhịp | Biết vì sao follower trễ | UI | BR-4, FR-26 | Should | F-24 | TL | TL | AT-34 | REG-5 | hiện có |
| F-27 | Phát lại một tập đã ghi lên follower (từ trang Bộ dữ liệu): dừng được trong một nhịp, có giới hạn an toàn, telemetry, camera, dead-man (bật mặc định) | Kiểm tra dữ liệu trên tay thật | UI | BR-7, FR-27 | Should | F-40 | TL | TL | AT-35 | — | hiện có |

## F. An toàn, e-stop, nhiệt, telemetry

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-28 | **E-stop**: nút đỏ lớn (mọi màn hình khi tay chuyển động), phím **Space** từ bất cứ đâu (Esc khi đang gõ chữ), API và WebSocket: lần 1 đóng băng trong nhịp hiện tại (giữ mô-men, tay không rơi), lần 2 trong 2 s hoặc "Thả lỏng" → tắt mô-men; "Đã an toàn, đặt lại" về Sẵn sàng; không bao giờ đổi hiệu chỉnh | Dừng ngay khi nguy hiểm | UI, API | BR-5, FR-28, NFR-3 | Must | F-12 | TL | TL | AT-36, AT-37 | REG-10 | hiện có |
| F-29 | Dead-man: khi chạy model, phát lại, chương trình, về tư thế nghỉ, căn tay: không nhận tín hiệu từ giao diện trong 1 s → e-stop (`ui_lost`) | Đóng tab / sập trình duyệt thì robot dừng | UI | BR-5, FR-29, NFR-4 | Must | F-28 | TL | TL | AT-38 | — | hiện có |
| F-30 | Giới hạn an toàn: bước tối đa mỗi nhịp (policy / phát lại 5°, teleop / ghi 30°, sửa được trong hồ sơ; màn hình Chạy model chỉ cho giảm trừ khi mở Nâng cao), kẹp vào dải hiệu chỉnh, giới hạn thời gian tập, điều kiện trước khi bắt đầu (động cơ nóng, camera chưa phát, chưa hiệu chỉnh, model không tương thích) | Tay không làm điều nguy hiểm | UI | BR-5, BR-11, FR-30 | Must | F-12 | TL | TL | AT-39 | — | hiện có |
| F-31 | Sức khoẻ động cơ: nhiệt độ, điện áp, dòng, tải, cờ trạng thái của từng động cơ follower và leader, đọc trong vòng điều khiển; bảng gọn trên mọi màn hình chuyển động; chip "động cơ nóng nhất" trên thanh trên; ngăn chi tiết với 120 s gần nhất và giới hạn đọc từ động cơ | Thấy động cơ sắp quá nhiệt | UI | BR-6, FR-31 | Must | F-12 | TL | TL | AT-40, AT-41 | REG-11 | hiện có |
| F-32 | Ngưỡng nhiệt và **dừng an toàn nhiệt**: ấm 50 °C (vàng, Hibi nhắc), nóng 60 °C (cam, chặn phiên mới), nguy hiểm 65 °C hai lần liên tiếp hoặc cờ quá nhiệt / quá tải (đỏ): giữ → về tư thế nghỉ (nếu có) → tắt mô-men trong ≤ 2 s, trạng thái `estopped (thermal)`, banner "Hãy đỡ tay", ước lượng thời gian nguội, không reset được khi còn nóng; trễ 3 °C | Station dừng trước khi servo tự ngắt làm rơi tay | UI | BR-5, BR-6, FR-32 | Must | F-31 | TL | TL | AT-42 | REG-3 | hiện có |
| F-33 | **Quy tắc số đo hợp lý**: nhiệt độ ngoài 1–150 °C, giới hạn nhiệt ngoài 40–150 °C, dòng > 3,5 A, tải ngoài ±100 %, điện áp ngoài 3–16 V là "không rõ" (hiện "—" kèm giải thích), không bao giờ là cảnh báo hay lý do dừng; bit hướng của dòng bị bỏ; leader không bao giờ báo động / dừng robot / chặn phiên, nhiệt leader tối đa "nóng"; "không phản hồi" chỉ khi một lần đọc không có trả lời | Không báo động giả | UI | BR-6, FR-33, NFR-12 | Must | F-31 | TL | TL | AT-43 | REG-3, REG-11, REG-13 | hiện có |
| F-34 | Dừng vì điện: điện áp dưới tối thiểu hoặc cờ quá dòng trên follower hai lần đọc liên tiếp → dừng an toàn (`electrical`); cờ quá tải của **kẹp** chỉ là cảnh báo (bóp vật là bình thường) | Bảo vệ khi nguồn yếu, không dừng giả khi kẹp vật | UI | BR-5, BR-6, FR-34 | Must | F-31 | TL | TL | AT-44 | REG-16 | hiện có |
| F-35 | Sau khi một chuyển động bị dừng giữa chừng và đã reset: banner "Tay robot đã dừng giữa chừng" + "Về tư thế nghỉ" (một chuyển động chậm, ≤ 30°/s, dead-man, Space / Dừng để huỷ); lần chạy chương trình / quỹ đạo tiếp theo luôn bắt đầu lại từ đầu | Luôn có đường phục hồi sau e-stop | UI | BR-5, FR-35 | Must | F-28 | TL | TL | AT-45 | REG-10 | hiện có |
| F-36 | Thông báo: banner đỏ (nguy hiểm, không ẩn được tới khi hết), cam (nóng), lỗi, đã dừng (kèm lý do); bong bóng Hibi; mất kết nối với Station → "Đang kết nối lại…", nút điều khiển tạm khoá | Luôn biết trạng thái | UI | BR-5, FR-36 | Must | F-4 | TL | TL | AT-46 | — | hiện có |
| F-37 | Trang Phiên: lịch sử phiên (loại, bắt đầu, bộ dữ liệu / model, kết quả, nhiệt độ cao nhất), telemetry của phiên; tự dọn phiên cũ hơn 30 ngày hoặc vượt 2 GiB | Xem lại sự cố | UI | BR-6, BR-12, FR-37 | Should | F-31 | TL | TL | AT-47 | — | hiện có |

## G. Ghi bộ dữ liệu

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-38 | Ghi dataset LeRobot v3: tên, nhiệm vụ (một câu), số tập, độ dài tập, thời gian đặt lại, fps, mã hoá video, khi hết giờ: lưu / bỏ; ước lượng dung lượng; khởi động → tập → đặt lại → lưu; nút và phím **→** (tiếp, lưu), **←** (ghi lại), **Esc** (dừng); dải các tập đã lưu; kết thúc: "Đã lưu N tập trong …" + Tải lên / Ghi thêm | Thu dữ liệu huấn luyện | UI | BR-7, FR-38 | Must | F-17, F-22, F-24 | TL | TL | AT-48, AT-49 | — | hiện có |
| F-39 | Ghi thêm vào dataset có sẵn (kiểm tra tương thích động cơ / camera; báo tên trùng) | Thu tiếp nhiều buổi | UI | BR-7, FR-39 | Should | F-38 | TL | TL | AT-50 | — | hiện có |
| F-40 | Trang Bộ dữ liệu: danh sách (tập, khung hình, fps, dung lượng, đã hoàn tất, đã tải lên v…); chi tiết: các tập, biểu đồ nhiệt độ follower từng tập (tệp telemetry đi kèm, nằm cạnh, không nằm trong thư mục LeRobot), Phát lại, Xoá (xác nhận, bị từ chối khi đang ghi / tải lên) | Xem lại dữ liệu | UI | BR-7, FR-40 | Must | F-38 | TL | TL | AT-51 | — | hiện có |

## H. Tải lên và liên kết máy chủ Hibiscus

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-41 | Ghép nối máy chủ Hibiscus: địa chỉ + personal access token (`datasets:write`, `models:read`, tuỳ chọn `runs:read`), liên kết "Tạo token với đúng quyền", kiểm tra quyền; token cất trong kho của hệ thống, không bao giờ gửi tới trình duyệt; chip máy chủ; Huỷ ghép nối | Một lần cho mọi lần tải | UI | BR-8, FR-41 | Should | F-4 | TL | TL | AT-52 | — | hiện có |
| F-42 | Tải dataset lên (dataset mới / phiên bản mới của dataset có sẵn): kiểm tra đã hoàn tất, tiến độ (băm, tải lên, kiểm tra), tiếp tục được sau mất mạng hoặc khởi động lại; chỉ gửi thư mục LeRobot | Đưa dữ liệu đi huấn luyện | UI | BR-8, FR-42 | Should | F-40, F-41 | TL | TL | AT-53, AT-54 | — | hiện có |
| F-43 | Trang Huấn luyện: dataset đã tải lên, "Mở huấn luyện trên Hibiscus" (thẻ mới, chọn sẵn phiên bản), danh sách lượt huấn luyện (trạng thái, tiến độ), "Tải về và chạy" | Không huấn luyện trên máy robot | UI | BR-8, FR-43 | Should | F-42 | TL | TL | AT-55 | — | hiện có |
| F-44 | Kéo model từ máy chủ ("Từ máy chủ" → Tải về): tiếp tục được, kiểm tra MANIFEST, đăng ký vào danh sách model | Lấy model đã huấn luyện | UI | BR-8, BR-9, FR-44 | Should | F-41 | TL | TL | AT-56 | — | hiện có |

## I. Chạy model (policy) trên robot

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-45 | Nhập model: tệp zip gói Hibiscus (xác minh MANIFEST → "đã xác minh") hoặc thư mục `pretrained_model` của lerobot ("chưa xác minh"), từ trình duyệt hoặc đường dẫn trên máy (chỉ trong home / ổ khác trên Windows / `/media`, `/mnt`); sao chép vào kho model; từ chối checkpoint pickle, zip độc hại | Dùng model huấn luyện ở đâu cũng được | UI | BR-9, FR-45 | Must | F-4 | TL | TL | AT-57 | — | hiện có |
| F-46 | Kiểm tra tương thích model ↔ robot (số khớp, kích thước lệnh, camera theo tên, độ phân giải, loại robot, gói bổ sung policy) với sửa một cú bấm ("Đặt camera thành W×H", chọn camera tương ứng) | Không chạy model sai | UI | BR-9, FR-46 | Must | F-45, F-22 | TL | TL | AT-58 | — | hiện có |
| F-47 | Nạp model: thiết bị Tự động (CUDA → MPS → CPU) / CPU / CUDA / MPS; hiện thiết bị, thời gian nạp, khởi động; một model tại một thời điểm | Biết model chạy ở đâu | UI | BR-9, FR-47 | Must | F-45 | TL | TL | AT-59 | — | hiện có |
| F-48 | Chạy trên robot: nhiệm vụ, fps, độ dài tập, số tập, đặt lại, bước tối đa; xác nhận một lần "e-stop là phần mềm"; đếm ngược 3 s → tập → đặt lại; Tiếp / Dừng; **mọi camera** với nhãn "đầu vào policy · W×H → w×h" và tick; khớp: đo được / lệnh / đã gửi + biểu đồ 10 s; FPS, độ trễ suy luận p50 / p95, % bị cắt; model quá chậm 5 s → tạm dừng với lời khuyên | Thấy model làm gì, an toàn | UI | BR-9, FR-48 | Must | F-46, F-47, F-28, F-29 | TL | TL | AT-60, AT-61 | — | hiện có |
| F-49 | Ghi bộ dữ liệu đánh giá `eval_…` trong lúc chạy model | Đánh giá model | UI | BR-9, FR-49 | Should | F-48, F-38 | TL | TL | AT-62 | — | hiện có |
| F-50 | Tóm tắt sau lượt chạy: thời lượng, số tập, nhiệt độ cao nhất từng khớp, cảnh báo, liên kết telemetry phiên và dataset đánh giá | Xem lại lượt chạy | UI | BR-9, FR-50 | Should | F-48 | TL | TL | AT-63 | — | hiện có |
| F-51 | Trang Model: các model đã nhập (tên, loại, nguồn, xác minh, đã nạp), Nhập, Chạy, Xoá | Quản lý model | UI | BR-9, FR-51 | Should | F-45 | TL | TL | AT-64 | — | hiện có |

## J. Chương trình: quỹ đạo, tư thế, nhận diện, khối (Blockly)

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-52 | Ghi quỹ đạo bằng tay leader (tên, giới hạn thời gian, đếm ngược, số mẫu), xem lại với đồ thị khớp, cắt đầu / cuối (gợi ý tự động đoạn đứng yên), Lưu / Bỏ; danh sách quỹ đạo (Nháp / Sẵn sàng / Cần kiểm tra) | Dạy chuyển động không cần huấn luyện | UI | BR-10, FR-52 | Should | F-24 | TL | TL | AT-65 | — | hiện có |
| F-53 | Phát quỹ đạo ở 10–100 % (đến 150 % chỉ khi hồ sơ cho phép): đi chậm về điểm đầu (≤ 30°/s), mọi đường an toàn của phát lại; sau hiệu chỉnh lại → "Cần kiểm tra": "Kiểm tra ở 25 %" rồi "Đã đúng" | Lặp lại chuyển động an toàn | UI | BR-10, FR-53 | Should | F-52 | TL | TL | AT-66, AT-67 | REG-10 | hiện có |
| F-54 | Tư thế có tên: lưu từ tay hiện tại, từ điểm đầu / cuối quỹ đạo; xoá | Khối "đi tới tư thế" | UI | BR-10, FR-54 | Should | F-12 | TL | TL | AT-68 | — | hiện có |
| F-55 | Bộ nhận diện camera: màu trong một vùng (vẽ vùng trên ảnh trực tiếp, quy tắc màu) hoặc bộ phân loại ảnh ONNX (tải model, nhãn); thử trực tiếp với nhãn đổi theo vật | Robot "thấy" để rẽ nhánh | UI | BR-10, FR-55 | Should | F-22 | TL | TL | AT-69 | — | hiện có |
| F-56 | Trình soạn chương trình khối (Blockly, giao diện Hibiscus): tạo chương trình mới (nút luôn mở form và đặt con trỏ vào ô tên; tên không có chữ Latin vẫn nhận được mã hợp lệ; nói rõ chương trình lưu cho hồ sơ nào), các nhóm khối Chuyển động / AI / Điều khiển / Điều kiện / Dữ liệu / Đầu ra, lưu, kiểm tra và đánh dấu khối lỗi, danh sách lỗi khi tải thất bại có "Thử lại" | Lập trình bằng kéo thả | UI | BR-10, FR-56 | Should | F-52, F-54 | TL | TL | AT-70 | REG-9 | hiện có |
| F-57 | Chạy thử (dry run) trên tay giả lập, giả lập điều kiện (camera thấy gì, kẹp giữ vật); bắt buộc chạy thử thành công phiên bản đó trước khi "Chạy trên robot" | Thử trước khi tay thật chạy | UI | BR-10, BR-5, FR-57 | Should | F-56 | TL | TL | AT-71 | — | hiện có |
| F-58 | Chạy trên robot: xác nhận các khối cần đồng ý, Tạm dừng / Tiếp tục / Dừng, bảng người vận hành (nút, phím, câu hỏi), biến, giá trị điều kiện gần nhất, nhật ký, lịch sử các lần chạy; e-stop / nhiệt dừng trong một nhịp, lần chạy kết thúc `estopped`; danh sách chương trình luôn trả lời kể cả khi robot bận / dừng khẩn | Chạy tác vụ thật | UI | BR-10, BR-5, FR-58 | Should | F-57, F-28 | TL | TL | AT-72 | REG-9, REG-10 | hiện có |
| F-59 | Tín hiệu ngoài: HTTP (`POST /api/v1/signals/<tên>` có token), MQTT (cấu hình URL và topic), khối "thông báo" qua webhook, khối "đặt tín hiệu" | Kỹ sư nối với hệ thống khác | API, UI | BR-10, BR-11, FR-59 | Could | F-58 | TL | TL | AT-73 | — | hiện có |
| F-60 | Khối "chạy mô hình … trong … s" / "… đến khi …" trong chương trình | Ghép model với quỹ đạo | UI | BR-10, FR-60 | Could | F-58, F-48 | TL | TL | AT-74 | — | hiện có |

## K. Robot 3D

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-61 | Robot 3D (SO-101 follower) vẽ theo vị trí khớp trực tiếp, mỗi động cơ tô màu theo nhiệt độ (màu xám / "chưa có số đo" khi không rõ), nhãn tay thật / tay giả lập, kéo xoay / phóng to, Đặt lại góc nhìn, Ẩn / Hiện; trình duyệt không có WebGL thì ẩn kèm lời giải thích | Nhìn tổng thể nhanh | UI | BR-6, FR-61 | Should | F-31 | TL | TL | AT-75 | — | hiện có |
| F-62 | Xem trước quỹ đạo bằng tay mờ (ghost) trước khi phát lên robot: Phát / Tạm dừng / kéo vị trí | Không bất ngờ khi phát | UI | BR-10, FR-62 | Should | F-61, F-52 | TL | TL | AT-76 | — | hiện có |

## L. Chẩn đoán

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-63 | `hibiscus-station doctor [--verbose] [--no-ping] [--no-cameras] [--out DIR]`: phiên bản, cổng USB (VID:PID, ai đang giữ), camera, tệp hiệu chỉnh, hồ sơ, trạng thái Station đang chạy, 200 dòng log cuối, kiểm tra chỉ-đọc từng tay (id, model, firmware, điện áp, nhiệt độ, trạng thái, EEPROM so với tệp, tỉ lệ lỗi và độ trễ đọc, ước lượng teleop); mở đầu bằng **LIKELY PROBLEMS**; tạo zip không chứa token | Khách gửi một tệp, nhà cung cấp tìm ra lỗi | CLI | BR-12, FR-63 | Must | F-1 | TL | TL | AT-77 | REG-2, REG-13 | hiện có |
| F-64 | Nhật ký `station.log` (UTF-8, xoay vòng), dòng khởi động (chế độ giả lập / thật, thư mục dữ liệu, hồ sơ), mọi lỗi bus; `-v` in ra màn hình | Truy vết sự cố | CLI | BR-12, FR-64 | Must | F-4 | TL | TL | AT-78 | REG-18 | hiện có |
| F-65 | `hibiscus-station health` (mã thoát 0 khi bản đang chạy trả lời) cho Docker / systemd | Giám sát tự động | CLI | BR-12, FR-65 | Could | F-4 | TL | TL | AT-79 | — | hiện có |

## M. Cài đặt, ngôn ngữ, giao diện

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-66 | Trang Cài đặt: ngưỡng nhiệt (kiểm tra quy tắc RULE-4, báo lỗi bằng lời), tần suất đọc telemetry, xem trước camera (rộng, fps), dead-man cho phát lại, thư mục dữ liệu, máy chủ (huỷ ghép nối), phiên bản Station / lerobot / thiết bị, nhãn chế độ demo | Kỹ sư chỉnh, người mới không cần | UI | BR-11, FR-66 | Must | F-4 | TL | TL | AT-80 | — | hiện có |
| F-67 | Song ngữ Tiếng Việt / English: tự chọn theo trình duyệt (mặc định tiếng Việt), đổi ngay trên thanh trên, mọi chuỗi có ở cả hai ngôn ngữ | Người Việt dùng được | UI | BR-14, FR-67, NFR-10 | Must | F-4 | TL | TL | AT-81 | — | hiện có |
| F-68 | Giao diện pixel Hibiscus ngày / đêm (theo hệ thống, đổi được), màn hình máy tính và điện thoại, đi được bằng bàn phím, nhãn cho trình đọc màn hình, linh vật Hibi đổi tâm trạng theo trạng thái | Dễ nhìn, dễ dùng | UI | BR-14, FR-68, NFR-11 | Must | F-4 | TL | TL | AT-82, AT-83 | — | hiện có |

## N. Cập nhật và dữ liệu

| ID | Tính năng | Giá trị | Nơi | Traces | Ưu tiên | Phụ thuộc | Effort | Milestone | AT | REG | Trạng thái |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-69 | Cập nhật bản wheel (Windows / Linux): chạy lại lệnh cài đặt với phiên bản mới; hồ sơ, hiệu chỉnh, dataset, model, quỹ đạo, chương trình giữ nguyên; quay lại bản cũ bằng cùng cách (xem Q-4) | Lên bản mới không mất gì | CLI | BR-15, FR-69 | Must | F-1 | TL | TL | AT-84 | — | hiện có |
| F-70 | Docker: `hibiscus-station-ctl backup [--full]`, `restore`, `update [TAG]` (sao lưu, kéo image, khởi động lại, kiểm tra sức khoẻ, tự quay lại khi lỗi), `rollback` | Máy robot tự quản | CLI | BR-15, FR-70 | Could | F-3 | TL | TL | AT-85 | — | hiện có |
| F-71 | Dữ liệu tách bạch và bền: ghi tệp nguyên tử, UTF-8, thư mục dữ liệu riêng cho demo; dataset là LeRobot nguyên bản; telemetry đi kèm nằm cạnh | Không hỏng dữ liệu | — | BR-15, FR-71 | Must | F-4 | TL | TL | AT-86 | REG-2, REG-18 | hiện có |

## Không làm trong v1.0 (Won't)

| ID | Mục | Lý do | Kế hoạch |
|---|---|---|---|
| W-1 | **Automation** (nhánh `feat/automation`, `feat/auto-kin`, `feat/auto-ui`, `feat/auto-vision`, `feat/auto-world`) | Quyết định của khách hàng 2026-11-17 | Bản sau, qua CR |
| W-2 | Nền tảng web Hibiscus | "Sản phẩm = chỉ Hibiscus Station" | Sau |
| W-3 | Huấn luyện trên máy robot | RULE-15 | — |
| W-4 | Robot khác SO-100 / SO-101 | Phạm vi | Sau |
| W-5 | Cài ID / baudrate động cơ | Dùng `lerobot-setup-motors` | — |
| W-6 | Thông báo / cập nhật tự động trong ứng dụng | Không phải tính năng hiện có (Q-4) | Đề xuất CR |
| W-7 | Đẩy lên HF Hub, sửa / gộp dataset | Máy chủ đã có | — |
| W-8 | Suy luận ONNX / bất đồng bộ / từ xa | Phạm vi | — |

## Chỉ dùng nội bộ (không phải tính năng của người dùng)

`POST /api/v1/mock/inject` (chèn lỗi giả lập, chỉ với `--mock`, cho demo và test e2e),
`hibiscus-station openapi` (xuất hợp đồng API cho nhà phát triển), `tests/sts_emulator.py`. Không có
AT người dùng; QC dùng chúng làm công cụ.

## Tổng hợp

| Ưu tiên | Số F |
|---|---|
| Must | 44 (F-6 tính là Must; phần LAN của nó là Could) |
| Should | 22 |
| Could | 5 (F-3, F-59, F-60, F-65, F-70; LAN trong F-6) |
| Tổng | 71 |
