# Hibiscus Station: ứng dụng chạy cạnh robot

Hibiscus Station chạy trên máy tính cắm robot. Nó thay cho quy trình LeLab: kết nối tay robot,
hiệu chỉnh (calibrate), thêm camera, điều khiển bằng tay leader (teleop), ghi dataset LeRobot, tải
lên workspace Hibiscus, train trên server, kéo model đã train về và chạy trên robot.

Hai điểm Station làm thêm so với LeLab:

* **Sức khỏe động cơ.** Nhiệt độ, điện áp, dòng, tải và cờ báo lỗi của từng động cơ được hiện trên
  mọi màn hình làm robot chuyển động. Động cơ ấm hiện màu vàng (50 °C), nóng màu cam (60 °C: không
  cho bắt đầu phiên mới), nguy hiểm màu đỏ (65 °C hai lần liên tiếp, hoặc cờ quá nhiệt / quá tải).
  Khi nguy hiểm, Station giữ tay robot, đưa về tư thế nghỉ nếu bạn đã lưu, rồi tắt torque, trước khi
  bảo vệ 70 °C của chính servo làm tay robot rơi.
* **Camera khi chạy model.** Màn hình Run model hiện tất cả camera trực tiếp, đúng những khung hình
  model nhận được, bên cạnh vị trí khớp, lệnh điều khiển, nhiệt độ động cơ, tốc độ (FPS) và thời gian
  suy luận. Camera cũng được hiện khi teleop, khi ghi và khi phát lại.

## Cài đặt

Có hai cách, chi tiết trong [hướng dẫn triển khai](../../deploy.md):

* **Docker (khuyên dùng)** trên PC hoặc mini PC (x86_64, có thể có GPU NVIDIA), NVIDIA Jetson Orin
  (JetPack 6) hoặc Raspberry Pi 5:

  ```bash
  curl -fsSLO https://raw.githubusercontent.com/Bigkatoan/hibiscus-station/main/deploy/install.sh
  bash install.sh
  ```

* **Gói Python (wheel)** (Linux, Windows 10/11 hoặc macOS có Python 3.12, qua [uv](https://docs.astral.sh/uv/)):

  ```bash
  uv tool install https://github.com/Bigkatoan/hibiscus-station/releases/download/v1.0.0a1/hibiscus_station-1.0.0a1-py3-none-any.whl
  hibiscus-station                  # mở giao diện
  ```

  Máy không có GPU NVIDIA thì thêm `--torch-backend cpu` để khỏi tải thư viện CUDA.

* **Windows 10/11 và macOS**: dùng cùng wheel đó (Docker chỉ dành cho Linux). Trên Windows cổng của
  tay robot là `COM3`, `COM4`... còn camera là số (`0`, `1`...); bo servo có thể cần driver WCH
  CH340/CH343. Xem [README](../../../README.vi.md#windows-1011).

Station chạy ở `http://127.0.0.1:18210` và tự mở trình duyệt. Nó chỉ nhận kết nối từ chính máy đó.
Nếu trình duyệt không mở, chạy `hibiscus-station url` (Docker: `hibiscus-station-ctl url`) và mở
đường link được in ra. Từ máy khác, dùng SSH tunnel (`ssh -L 18210:127.0.0.1:18210 user@may-robot`)
hoặc bật chế độ LAN như hướng dẫn triển khai. Muốn thử khi chưa có robot: `hibiscus-station --mock` (tay giả lập, có nhãn **TAY GIẢ LẬP**; hồ sơ và
dữ liệu nằm ở `~/.hibiscus/station-demo`). Nếu tay thật không chuyển động, tắt Station rồi chạy
`hibiscus-station doctor` và gửi file zip nó tạo ra.

Hãy tắt LeLab và mọi lệnh `lerobot-*` trước: mỗi cổng serial chỉ một chương trình dùng được.

## Các bước

1. **Robot.** Tạo hồ sơ robot: loại robot, cổng follower, cổng leader (không bắt buộc). Dưới mỗi ô
   có nút "Tìm tay follower" / "Tìm tay leader" (cử động hoặc rút cáp): chỉ cử động (hoặc rút cáp)
   đúng tay đó, cổng tìm được vào đúng ô đó. Station đọc điện áp động cơ của mỗi cổng (chỉ đọc) và
   gợi ý: tay leader thường chạy ~5 V, follower 7,4 V hoặc 12 V. Nếu hai tay có vẻ bị nhầm, bấm
   "Đổi chỗ follower ⇄ leader" (Station không tự đổi). Bấm Connect. Lúc này bạn thấy vị
   trí các khớp và nhiệt độ động cơ. Khi tay robot đang ở tư thế gập an toàn, bấm "Dùng tư thế hiện
   tại làm tư thế nghỉ": Station sẽ đưa tay về đây trước khi tắt torque.
2. **Calibrate.** Với mỗi tay: đưa mọi khớp về giữa hành trình, bấm *Set home*, rồi đưa từng khớp đi
   hết hành trình và bấm *Finish*. File hiệu chỉnh được lưu đúng chỗ lerobot dùng, nên LeLab và các
   lệnh `lerobot-*` dùng lại được. File có sẵn dùng lại được bằng *Dùng hiệu chỉnh này*.
3. **Camera.** Thêm các camera tìm thấy. Tên camera (`wrist`, `front`, ...) là tên model sẽ cần
   (`observation.images.<tên>`).
4. **Teleop.** Cử động tay leader, tay follower làm theo. Nếu leader lệch xa tư thế follower,
   Station yêu cầu bạn đưa leader lại gần trước. Teleop chạy nhanh như LeLab (mặc định 250 Hz, mỗi
   nhịp chỉ đọc tay leader và gửi lệnh cho follower); màn hình hiện "độ trễ ~X ms, Y Hz" đo trực
   tiếp. Nếu số Hz thấp, chạy `hibiscus-station doctor` (xem [Báo cáo chẩn đoán](#báo-cáo-chẩn-đoán-doctor)):
   nó đo tốc độ bus và nói cách sửa theo loại bộ chuyển USB (cắm thẳng vào máy, không qua hub; chỉnh
   latency timer 1 ms chỉ có ở bộ chuyển FTDI).
5. **Ghi dữ liệu.** Chọn tên dataset, câu mô tả nhiệm vụ, số episode và độ dài. Phím: **→** sang
   episode tiếp (lưu), **←** ghi lại, **Esc** dừng. Episode chạm giới hạn thời gian sẽ được **lưu**
   (khác LeLab, vốn lặng lẽ ghi lại); bạn có thể đổi thành *bỏ*.
6. **Tải lên.** Ghép Station với server Hibiscus một lần (URL server và personal access token có
   quyền `datasets:write` và `models:read`; thêm `runs:read` để xem các run). Sau đó tải dataset lên
   thành dataset mới hoặc phiên bản mới. Mất mạng giữa chừng thì lần sau tải tiếp từ chỗ dở.
7. **Train.** "Mở trang train trên Hibiscus" mở trang New Run của server. Việc train chạy trên
   server, không bao giờ chạy trên máy robot.
8. **Chạy model.** Nhập file zip bundle hoặc thư mục `pretrained_model`, hoặc kéo model từ server.
   Station kiểm tra model có khớp robot không (số khớp, tên và độ phân giải camera) và đề xuất cách
   sửa. Load model, đặt nhiệm vụ và độ dài episode, rồi bắt đầu.
9. **Chương trình** (không cần train). *Quỹ đạo*: ghi một chuyển động của tay follower bằng tay
   leader, cắt bớt đầu cuối, xem trước trên tay robot 3D mờ, phát lại ở 10-150 %. *Nhận diện*: dạy
   camera cần tìm gì (một màu trong một vùng, hoặc một bộ phân loại ảnh ONNX). *Chương trình*: ghép
   quỹ đạo, tư thế, chờ và các điều kiện camera / nút bấm / khớp / tín hiệu bằng trình soạn khối.
   Chương trình mới hoặc vừa sửa phải **chạy thử** trên tay giả lập thành công thì mới chạy được
   trên robot. Mọi quy tắc an toàn của phát lại vẫn áp dụng, và phím Space dừng chương trình ngay
   trong một nhịp.

**Robot 3D.** Mọi màn hình làm tay robot chuyển động đều có tay follower dạng 3D, vẽ theo vị trí khớp
trực tiếp, mỗi động cơ tô màu theo nhiệt độ. Nếu tay 3D không khớp tay thật (ví dụ `wrist_roll` xoay
ngược chiều), hãy hiệu chỉnh lại trước khi tin vào phát lại.

## Báo cáo chẩn đoán (doctor)

Khi tay robot không chạy đúng, một báo cáo giúp chúng tôi tìm ra nguyên nhân ngay lần đầu:

1. Tắt Station (Ctrl+C trong cửa sổ đang chạy nó) và tắt LeLab, Feetech FD và mọi lệnh `lerobot-*`.
2. Cắm cả hai tay vào máy và bật nguồn cho chúng.
3. Mở PowerShell (Windows) hoặc Terminal, chép và dán lệnh:

   ```
   hibiscus-station doctor --verbose
   ```

4. Đợi khoảng một phút. Phần cuối báo cáo, mục **WHAT TO SEND / CẦN GỬI GÌ**, ghi đường dẫn đầy đủ
   của tệp `hibiscus-station-doctor-<thời gian>.zip`: bạn chỉ cần gửi tệp đó. Nếu mục này nói phần
   kiểm tra động cơ chưa đủ, làm theo hướng dẫn ở đó rồi chạy lại.

Báo cáo bằng tiếng Anh (dành cho kỹ sư), trừ mục cuối. Dòng đầu là **LIKELY PROBLEMS** (các vấn đề
có thể có, hoặc "No likely problems found"): ví dụ hồ sơ tay giả lập đang hoạt động, thiếu tệp hiệu
chỉnh, cổng đang bị chương trình khác giữ (có tên chương trình), Station đã tắt mà còn sót tệp
`station.pid`, bus chậm, hoặc động cơ báo số đo vô lý (0 °C, dòng 6,5 A).

`doctor` **chỉ đọc**: nó không ghi gì xuống động cơ và không bật mô-men. Với mỗi cổng USB serial (kể
cả cổng chưa có trong hồ sơ robot) nó đọc từng động cơ: model, firmware, vị trí, điện áp, nhiệt độ,
`Max_Temperature_Limit`, dòng (`Present_Current`), tải (`Present_Load`), trạng thái, EEPROM so với tệp
hiệu chỉnh, tốc độ bus; rồi in **bản dump thô** các thanh ghi 0–4, 13–15 và 56–70 của từng động cơ
(byte đúng như động cơ gửi về) kèm giá trị đã giải mã, cùng đơn vị và quy tắc "không rõ" như màn hình
sức khoẻ động cơ. Tệp zip có báo cáo, 200 dòng nhật ký cuối, hồ sơ robot, cài đặt, tệp hiệu chỉnh và 5
phiên gần nhất; không có token đăng nhập hay token truy cập Hibiscus.

Tuỳ chọn: `--no-ping` không mở cổng serial, `--no-cameras` không dò camera, `--out <thư mục>` nơi lưu
tệp zip (mặc định: thư mục hiện tại).

## An toàn

* **E-stop:** nút đỏ lớn hoặc phím **Space**. Lần bấm đầu: tay robot đứng yên và vẫn giữ torque. Bấm
  lần hai trong vòng 2 giây (hoặc *Relax*): tắt torque, hãy đỡ tay robot. *Đã an toàn, reset* để
  quay lại trạng thái chờ.
* Khi model đang chạy, trình duyệt phải luôn mở: nếu Station không nhận tín hiệu từ trình duyệt
  trong 1 giây, robot sẽ dừng.
* Mỗi bước chuyển động bị giới hạn (`max relative target`, mặc định 5 độ).
* E-stop là phần mềm. Luôn có cách ngắt nguồn robot bằng tay.

## Dữ liệu nằm ở đâu

`~/.hibiscus/station/` chứa hồ sơ robot (`robots.yaml`), cài đặt, dataset (`datasets/<tên>/`, là
dataset LeRobot bình thường; số liệu động cơ nằm cạnh trong `datasets/<tên>.hibiscus/`), model
(`models/`), nhật ký phiên (`sessions/`) và, theo từng robot, quỹ đạo, tư thế, bộ nhận diện và
chương trình (`robots/<id>/`). File hiệu chỉnh nằm ở chỗ lerobot dùng
(`~/.cache/huggingface/lerobot/calibration/`). Token server do Hibiscus CLI cất: trong keyring hệ
thống với bản cài Python; với bản Docker (không có keyring) thì ở
`~/.hibiscus/station/hibiscus-cli/credentials.json` (quyền 0600). `hibiscus-station-ctl backup` sao
lưu tất cả những thứ này trừ dataset và model (`--full` thì lấy cả hai).

Trước khi dùng thật, hãy chạy danh sách kiểm tra phần cứng: [station-hardware-uat.md](station-hardware-uat.md).
