# Hibiscus Station: danh sách nghiệm thu trên phần cứng (UAT)

Hibiscus Station được viết và kiểm thử khi không có robot nào cắm vào: mọi test tự động chạy trên
động cơ giả lập, tay leader giả lập, camera giả lập và một policy ACT rất nhỏ. Các mục dưới đây chỉ
kiểm được trên tay SO-101 (hoặc SO-100) follower và leader thật. Hãy chạy một lần trên bộ robot của
bạn trước khi dùng Station để thu dữ liệu, và chạy lại sau khi cập nhật lerobot hoặc firmware.

Điền cột **Kết quả** (đạt / không đạt / giá trị đo) và lưu file này cùng ghi chép của lab. Khi một
mục không đạt, mở issue kèm thư mục phiên `~/.hibiscus/station/sessions/<id>/` (chứa `session.json`
và `telemetry.jsonl.gz`).

## 0. Chuẩn bị

* [ ] Biết nguồn của follower (bộ 5 V, 7,4 V hay 12 V): ______ V
* [ ] Đã tắt LeLab và mọi lệnh `lerobot-*` (Station từ chối cổng đang bị chương trình khác giữ).
* [ ] Có nhiệt kế (hồng ngoại hoặc que đo) và đồng hồ vạn năng.
* [ ] Có thể ngắt nguồn tay robot bằng tay. E-stop của Station là phần mềm, không thay được việc này.
* [ ] Khởi động Station: `hibiscus-station` (bản cài Python) hoặc `hibiscus-station-ctl up` (Docker). Ghi
      phiên bản và loại image (`hibiscus-station-ctl status`): ______

## 1. Cổng, kết nối, hiệu chỉnh

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 1.1 | Danh sách cổng | Màn hình Robot, chọn cổng | Chỉ có cổng serial USB, kèm VID:PID; có đường dẫn `/dev/serial/by-id/...` | |
| 1.2 | Tìm bằng cách rút cáp | "Tìm bằng cách rút cáp", rút USB follower | Tìm ra cổng follower trong 15 giây | |
| 1.3 | Tìm bằng cách cử động | "Tìm bằng cách cử động", cử động tay leader | Tìm ra cổng leader trong 10 giây | |
| 1.4 | Cổng đang bận | Chạy `lerobot-teleoperate` trên follower, rồi bấm Connect trong Station | Báo lỗi rõ "Chương trình khác (LeLab? lerobot?) đang dùng cổng này" | |
| 1.5 | Kết nối | Connect hồ sơ robot | Trạng thái `idle`, mỗi tay 6 động cơ, có hiện nhiệt độ | |
| 1.6 | Hiệu chỉnh follower | Màn hình Calibrate: home, rồi ranges, rồi Finish | Có file `~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json`; `wrist_roll` ghi là xoay tròn đủ vòng | |
| 1.7 | Hiệu chỉnh leader | Làm tương tự với leader | Có file `.../teleoperators/so_leader/<id>.json` | |
| 1.8 | Dùng chung Station -> lerobot | `lerobot-teleoperate --robot.type=so101_follower --robot.id=<id> ...` với file của Station | Chạy được, không phải hiệu chỉnh lại | |
| 1.9 | Dùng chung lerobot/LeLab -> Station | Dùng file hiệu chỉnh do lerobot hoặc LeLab tạo ("Dùng hiệu chỉnh này") | Vị trí khớp trong Station hợp lý | |

## 2. Số liệu sức khỏe động cơ (R1)

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 2.1 | Đơn vị nhiệt độ | So giá trị Station với nhiệt kế đặt trên vỏ động cơ sau 10 phút teleop | Lệch trong ±2 °C (servo đo bên trong, có thể nóng hơn) | |
| 2.2 | Đơn vị điện áp | Đo nguồn bus bằng đồng hồ, so với `V` trong Station | Lệch trong ±0,2 V | |
| 2.3 | Đơn vị dòng (6,5 mA/bước, **chưa xác nhận**) | Kẹp chặt gripper vào vật; so với ampe kìm hoặc số trên nguồn | Cùng bậc độ lớn; ghi tỉ lệ: ______ | |
| 2.4 | Dấu của tải | Khi đang có torque, đẩy một khớp bằng tay theo hai chiều | Tải đổi dấu theo chiều đẩy | |
| 2.5 | Bit trạng thái (**bố cục chưa xác nhận**) | Kẹp chặt gripper vài giây | Hiện chip `overload`; Station dừng robot (mức nguy hiểm) | |
| 2.6 | Điện áp leader | Xem điện áp của leader chạy nguồn 5 V | Không có cảnh báo điện áp thường trực; nếu có, ghi `Min_Voltage_Limit`: ______ | |
| 2.7 | Đọc giới hạn khi kết nối | Tooltip trong ngăn sức khỏe động cơ | Hiện `Max_Temperature_Limit` (mặc định nhà máy 70 °C) | |
| 2.8 | Nhịp vòng điều khiển khi có telemetry | Teleop 10 phút ở 30 Hz, mở tóm tắt phiên | Số tick trễ dưới 1 %, `telemetry_forced` nhỏ | |
| 2.9 | Độ trễ đọc | `station.log` / thống kê phiên | p95 thời gian tick dưới 36 ms ở 30 Hz | |

## 3. An toàn

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 3.1 | E-stop đóng băng | Đang teleop thì bấm Space (hoặc nút đỏ); quay bằng điện thoại ở tốc độ khung hình cao | Tay robot đứng yên trong dưới 100 ms, vẫn giữ torque, không rơi | |
| 3.2 | E-stop thả lỏng | Bấm Space lần nữa trong vòng 2 giây | Tắt torque; màn hình nhắc "Hãy đỡ tay robot" | |
| 3.2a | Dừng là giữ (CR-1) | Teleop, ghi, một chương trình và một quỹ đạo: bấm Dừng của màn hình (Esc khi đang ghi) | Tay đứng yên đúng chỗ (không rơi, không đi); băng rôn mời Về Home và Thả lỏng; Thả lỏng hỏi đã đỡ tay chưa | |
| 3.2b | Dừng khi ghi (báo lỗi 0.2.8) | Ghi episode 30 giây với hai camera, bấm Dừng ở khoảng giây 10 | Ngay lập tức: "Đang lưu tập 1…", đồng hồ dừng, camera vẫn chạy; rồi thẻ kết thúc; dataset dài ~10 giây | |
| 3.3 | Reset | "Đã an toàn, reset" | Về trạng thái chờ | |
| 3.4 | Dừng vì nhiệt | Cài đặt: hạ `temp_critical_c` xuống (nhiệt độ hiện tại + 1), giữ đúng quy tắc (hot ≤ critical − 3, warn ≤ hot − 5); teleop đến khi kích hoạt | Băng rôn đỏ, giữ tay, về Home (nếu đã đặt), tắt torque, trạng thái `estopped (thermal)`; không cho reset khi còn động cơ nóng | |
| 3.5 | Home | Thanh trên cùng: "Đặt Home tại vị trí hiện tại", rồi làm lại 3.4 | Tay robot về Home trước khi tắt torque | |
| 3.6 | Dead-man | Đang chạy model thì đóng tab trình duyệt | Robot dừng trong khoảng 1 giây (`ui_lost`) | |
| 3.7 | Giới hạn bước | Chạy model hoặc phát lại với max relative target 2.0 | Chuyển động chậm lại; khớp bị cắt được đánh dấu trong bảng khớp | |
| 3.8 | Rút USB | Rút USB follower khi đang teleop | Trạng thái `error (bus_lost)`, không treo; kết nối lại được | |

## 4. Camera (R2)

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 4.1 | Tìm và thử camera | Màn hình Camera | Mỗi camera hiện một lần kèm ảnh chụp; có fps đo được | |
| 4.2 | Hai camera chung một hub | Thêm hai camera 640×480@30 MJPG | Cả hai đều phát hình; cảnh báo nếu fps đo < 90 % | |
| 4.3 | Xem camera khi ghi | Ghi một episode | Thấy tất cả camera suốt quá trình ghi | |
| 4.4 | Xem camera khi chạy model | Run model | Thấy tất cả camera, có nhãn "policy input", số tick tăng dần | |
| 4.5 | Rút camera khi đang ghi | Rút một camera giữa episode | Có cảnh báo; đồng hồ episode dừng; sau 3 giây phiên dừng (`camera_lost`); dataset vẫn hợp lệ | |

## 5. Ghi dữ liệu và tải lên

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 5.1 | Ghi 3 episode | Ghi, dùng →, ←, Esc và để một episode hết giờ | Dataset ở `~/.hibiscus/station/datasets/<tên>`; episode hết giờ được lưu | |
| 5.2 | Dataset hợp lệ | `python -c "from pathlib import Path; from lerobot.datasets import LeRobotDataset as D; print(D('local/<tên>', root=Path.home()/'.hibiscus/station/datasets/<tên>'))"` | Mở được; đúng số episode | |
| 5.3 | File telemetry đi kèm | Màn hình Datasets, biểu đồ nhiệt độ từng episode | Mỗi episode một biểu đồ; không có file lạ trong thư mục LeRobot | |
| 5.4 | Tải lên | Ghép với server Hibiscus, bấm Upload | Server tạo phiên bản dataset; kiểm tra hợp lệ đạt | |
| 5.5 | Tải tiếp sau khi mất mạng | Rút cáp mạng giữa lúc tải, cắm lại, tải lại | Tải tiếp từ các phần đã gửi | |

## 6. Model trên robot

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 6.1 | Nhập bundle | Run model: Import file `.zip` từ Hibiscus | Có nhãn "verified"; danh sách kiểm tra tương thích toàn xanh | |
| 6.2 | Kéo từ server | "Từ server", rồi Pull | Model xuất hiện và load được; hiện thiết bị và độ trễ khởi động | |
| 6.3 | Chạy một episode | Chạy 1 episode 20 giây | Robot chuyển động; hiện độ trễ suy luận p50/p95; tóm tắt có nhiệt độ cao nhất từng khớp | |
| 6.4 | CPU quá chậm | Chạy policy nặng trên CPU ở 30 fps | Phiên tạm dừng với "model quá chậm" thay vì dồn lệnh cũ | |
| 6.5 | Ghi dataset đánh giá | Chạy với "ghi dataset đánh giá" | Có dataset `eval_...` mở được | |

## 7. Quỹ đạo, chương trình và Robot 3D

Trước tiên ghi hai quỹ đạo ngắn A và B, một tư thế `home` và một bộ nhận diện màu, rồi dựng chương
trình mẫu "đỏ → A, xanh → B" theo hướng dẫn sử dụng.

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 7.1 | Chiều `wrist_roll` trên Robot 3D | Màn hình Robot, Robot 3D: tắt torque, xoay `wrist_roll` của follower một phần tư vòng theo chiều kim đồng hồ (nhìn từ phía kẹp) | Cổ tay 3D xoay cùng chiều, góc gần bằng | |
| 7.2 | Độ lệch điểm 0 trên Robot 3D | Đặt tay ở tư thế giữa lúc hiệu chỉnh (mọi khớp ở giữa hành trình) | Tay 3D cùng tư thế, lệch dưới khoảng 5° mỗi khớp; ghi độ lệch từng khớp: ______ | |
| 7.3 | E-stop khi đang về điểm đầu | Phát lại A khi tay đang cách điểm đầu xa (> 30°); bấm Space khi tay đang di chuyển về điểm đầu | Tay dừng trong một nhịp; không còn lệnh vị trí nào được gửi sau khi bấm (quay video: tay không chuyển động lại cho tới khi Reset); trạng thái `estopped` | |
| 7.4 | E-stop khi đang phát lại | Phát lại A ở 100 %; bấm Space giữa chừng | Như 7.3; lần chạy chương trình kết thúc với kết quả `estopped` | |
| 7.5 | Quá nhiệt giữa chương trình | Hạ `temp_critical_c` như 3.4 rồi chạy chương trình trên robot đến khi kích hoạt | Chương trình dừng trong một nhịp, tay về Home, rồi tắt torque; trạng thái `estopped (thermal)`; lần chạy kết thúc với kết quả `estopped` | |
| 7.6 | Thả lỏng khi có Home | Đã đặt Home; sau một phiên bấm *Thả lỏng* (hoặc hồ sơ đặt `on_session_end: relax`) | Tay về Home trước, rồi mới tắt torque; tay không rơi | |
| 7.7 | Chạy model khi rút camera | Đang chạy model, rút một camera mà policy dùng | Có cảnh báo; tạm dừng; sau `camera_lost_stop_s` (3 giây) phiên dừng (`camera_lost`), tay vẫn được giữ | |
| 7.8 | Ghi lại quỹ đạo sau khi hiệu chỉnh lại | Hiệu chỉnh lại follower | A, B, tư thế và chương trình bị đánh dấu "cần kiểm tra"; không cho chạy trên robot đến khi ghi lại A, B hoặc xác nhận bằng một lần phát lại chậm | |
| 7.9 | Chạy thử lại sau khi cắt quỹ đạo | Cắt bớt đầu hoặc cuối của A rồi lưu | Phiên bản chương trình đổi; "Chạy trên robot" bị từ chối đến khi chạy thử mới thành công | |
| 7.10 | Xem trước bằng tay 3D mờ | Thẻ Quỹ đạo, chọn A, phát xem trước 3D | Tay mờ chuyển động giống lúc phát lại A thật (cùng chiều, cùng thứ tự khớp) | |
| 7.11 | Nhận diện trên camera thật | Thẻ Nhận diện: vẽ vùng, đưa vật đỏ rồi vật xanh vào | Nhãn trực tiếp đổi đỏ → xanh → không có trong khoảng 0,5 giây | |
| 7.12 | Nút vận hành và tín hiệu ngoài | Thêm khối nút bấm và một tín hiệu HTTP (`POST /api/v1/signals/<tên>` kèm token) | Chương trình phản ứng với cả hai | |

## 8. Trên thiết bị (Docker, Raspberry Pi 5, Jetson)

| # | Kiểm tra | Cách làm | Kỳ vọng | Kết quả |
|---|---|---|---|---|
| 8.1 | Tìm cổng bằng cách rút cáp trong Docker | Màn hình Robot, "Tìm bằng cách rút cáp" khi container đang chạy | Cổng biến mất rồi xuất hiện lại; tìm ra trong 15 giây | |
| 8.2 | Tên cổng cố định | `hibiscus-station-ctl ports` | Mỗi bộ chuyển đổi có đường dẫn `/dev/serial/by-id/...`, và `/dev/hibiscus/arm-...` khi đã cài luật udev | |
| 8.3 | Khởi động khi chưa cắm tay robot | Khởi động lại máy khi chưa cắm tay, cắm sau | Container vẫn chạy và healthy; cắm vào thì kết nối được | |
| 8.4 | Tự khởi động | Khởi động lại máy, không đăng nhập | `hibiscus-station-ctl status` báo `healthy` trong 3 phút | |
| 8.5 | Dừng an toàn khi tắt | Đang teleop thì chạy `hibiscus-station-ctl down` | Tay giữ yên, về Home, tắt torque trước khi container dừng | |
| 8.6 | Cập nhật và quay lại | `hibiscus-station-ctl update <tag mới>`, rồi `rollback` | Có file sao lưu; tag mới healthy; quay lại tag cũ mà hiệu chỉnh, quỹ đạo, chương trình còn nguyên | |
| 8.7 | Chế độ LAN | Đặt `STATION_BIND`, token và tên máy cho phép; mở link từ laptop | Mở được bằng tên đã khai báo; tên hoặc IP khác bị `403 forbidden_host` | |
| 8.8 | Tốc độ model trên thiết bị | Chạy model ACT mẫu ở 30 fps | Ghi p50/p95 suy luận: ______ / ______ ms (CPU Pi 5: model lớn hơn ACT sẽ bị trễ nhịp) | |

Ký xác nhận: tên ______  ngày ______  phiên bản Station ______  lerobot 0.7.1 commit `fe1c545`
