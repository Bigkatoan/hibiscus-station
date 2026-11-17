# Hibiscus Station v1.0: tóm tắt vòng 1 gửi khách hàng (2026-11-17)

Vòng 1 · bộ tài liệu **v0.2**: [BRD](BRD.md) · [SRS](SRS.md) · [Kiến trúc](ARCHITECTURE.md) ·
[Danh sách tính năng](FEATURES.md) · [Nghiệm thu](ACCEPTANCE.md) · [Hồi quy](REGRESSION.md) ·
[Nhật ký](CHANGELOG.md)

## Thay đổi so với v0.1

* Kiến trúc sư giải pháp (SA) và Tech Lead đã rà soát độc lập. Tech Lead cũng đã chạy thử đúng bản cài 0.2.8.
* Mỗi tính năng giờ có công sức ước lượng, mốc làm, danh sách lỗi đã biết và bảng truy vết đầy đủ.
* Các yêu cầu không đo được hoặc không làm được trên phần cứng của bạn đã được viết lại (xem bảng bên dưới).
* 98 bài thử nghiệm thu được viết lại để làm đúng được như chữ. Phần bạn phải tự thử rút xuống còn 3 buổi.

## v1.0 là gì

Hibiscus Station v1.0 = **71 tính năng đang có** của bản 0.2.8, sửa cho tới khi không còn lỗi nào, không thêm
tính năng mới. Automation để bản sau.

Cài đặt và khởi động 7 · Robot và cổng 8 · Hiệu chỉnh 5 · Camera 3 · Điều khiển tay 4 · An toàn và nhiệt độ 10 ·
Ghi dữ liệu 3 · Máy chủ Hibiscus 4 · Chạy model 7 · Chương trình 9 · Robot 3D 2 · Chẩn đoán 3 · Cài đặt và giao
diện 3 · Cập nhật và dữ liệu 3.
Theo mức ưu tiên: **44 bắt buộc** (Must), 22 nên có (Should), 5 có thể bỏ (Could).

## Hiện trạng (nhóm kiểm thử sơ bộ bản 0.2.8 trên Linux)

* **33** tính năng chưa thấy lỗi.
* **22** tính năng có lỗi. Tổng cộng 23 lỗi: 3 lỗi nặng, 9 lỗi trung bình, 11 lỗi nhẹ. Ba lỗi nặng là: test
  tự động của luồng chính đang hỏng; tay follower bị trễ khi bộ chuyển USB chậm; đóng cửa sổ PowerShell thì
  robot không dừng an toàn.
* **16** tính năng nhóm chưa tự chứng minh được. 11 trong số đó chỉ chứng minh được trên **PC Windows của bạn
  với hai tay thật**: cài đặt, tìm cổng, mất USB rồi kết nối lại, dùng chung tệp hiệu chỉnh với LeLab, camera
  thật, nhiệt độ động cơ, cập nhật. 5 tính năng còn lại cần máy chủ Hibiscus thử hoặc Docker, nhóm sẽ tự dựng.
* Vẫn chưa biết vì sao servo của bạn báo 0 °C. Trong lúc đó **bảo vệ nhiệt của Station không hoạt động trên
  tay của bạn**.
* Ước lượng: khoảng **82 ngày công**, tức 6 – 7 tuần nếu 3 người làm song song (chưa tính kiểm thử và thời gian
  chờ bạn thử). Các đề xuất mới bên dưới sẽ được ước thêm ở vòng 2.
  Lộ trình: M0 (tuần 1) dựng nền kiểm thử → M1 sửa các tính năng bắt buộc → M2 các tính năng nên có → M3 các
  tính năng có thể bỏ.

## Nhóm đề xuất thay đổi, và lý do

| Chỗ | Yêu cầu cũ | Vấn đề | Đề xuất |
|---|---|---|---|
| Đo độ trễ teleop (G-2, F-24) | Đo bằng video 240 fps, không chậm hơn LeLab quá 10 ms | Bạn không có máy quay như vậy. LeLab cũng không hiện số độ trễ để so | Nhóm đo trên giả lập. Ở phía bạn: chạy LeLab và Station lần lượt, rồi bạn đánh giá "không chậm hơn" |
| E-stop (G-3, F-28) | Tay đứng yên dưới 100 ms | Đây là số vật lý, bạn không đo được | Nhóm đo bằng test tự động: không lệnh mới sau tối đa 1 nhịp. Bạn chỉ cần thấy tay dừng ngay |
| Đo nhiệt độ, điện áp (F-31) | So với nhiệt kế và đồng hồ vạn năng | Cần dụng cụ đo; vỏ servo cũng nguội hơn cảm biến bên trong | So với phần mềm Feetech FD trên cùng servo (bạn đã có) |
| Phím Space (F-28) | Dừng "từ bất cứ đâu" | Space chỉ có tác dụng khi cửa sổ Station đang được chọn | Hướng dẫn ghi rõ điều này. Khuyến nghị lắp công tắc ngắt nguồn trên dây nguồn follower |
| Đóng cửa sổ (F-4) | Robot dừng an toàn | Trên Windows hiện chưa làm được | Sửa: khi đóng cửa sổ, Station tắt mô-men trong 4 giây. Tập đang ghi dở có thể mất, các tập đã lưu vẫn giữ |
| Model chậm (F-48) | Mất giao diện thì robot dừng sau 1 giây | Với model chạy chậm, robot chỉ dừng khi model chạy xong một lượt | Sửa: không cho chạy model nếu máy quá chậm, kèm lời khuyên |
| Lỗi hiện tiếng Anh (F-7) | Hiện "lý do chính xác" của Station | Câu đó là tiếng Anh và chứa đường dẫn | Chỉ hiện câu tiếng Việt. Chi tiết kỹ thuật thu gọn lại, dành cho kỹ sư |
| Lịch thử của bạn | Khoảng 45 bài thử | Mất nhiều giờ, mỗi lỗi lại phải thử lại | Chia 3 buổi: UAT-0 khoảng 15 phút (gửi báo cáo chẩn đoán), UAT-1 có 15 bước trong 60 – 90 phút, UAT-2 khoảng 45 phút |

## Bạn cần quyết định (4 câu, phương án đầu là đề xuất của nhóm)

1. **Khi Station không đọc được nhiệt độ động cơ, robot có được chạy không?**
   **A (đề xuất):** vẫn cho chạy. Mỗi lần kết nối, Station hỏi bạn xác nhận và hiện banner cam. Khi không có
   người cầm tay leader (chạy model, chương trình), robot tự dừng sau 10 phút. ·
   B: chỉ hiện banner, như hiện nay. · C: không cho robot chuyển động.
2. **Những nền tảng nào thuộc nghiệm thu v1.0?**
   **A (đề xuất):** Windows bắt buộc (bạn thử), Ubuntu nên có (nhóm thử), Docker trên PC Linux có thể bỏ (nhóm
   thử). macOS, Raspberry Pi 5, Jetson ghi là "bản xem trước", không thuộc nghiệm thu. ·
   B: nghiệm thu mọi nền tảng (bạn cho mượn máy, thêm thời gian). · C: chỉ Windows.
3. **Cài đặt và cập nhật trên Windows.**
   **A (đề xuất):** chỉ dán **một lệnh**. Lệnh này không cần git, và cài đúng bộ thư viện nhóm đã kiểm. Dán lại
   cùng lệnh đó để cập nhật hoặc quay về bản cũ. ·
   B: giữ cách hiện nay (hai lệnh, máy cần git).
4. **Giấy phép của gói Hibiscus CLI** (đang ghi "Proprietary", trong khi Station là mã nguồn mở AGPL).
   **A (đề xuất):** phát hành bản v0.1.2 với giấy phép Apache-2.0 (hoặc MIT). ·
   B: đổi sang AGPL-3.0. · C: bỏ gói này, nhóm tự viết lại phần kết nối máy chủ (thêm khoảng 1 tuần).

Ngoài 4 câu trên, nhóm giữ các đề xuất mặc định như vòng trước: máy chủ Hibiscus và Chương trình là "nên có",
dùng từ "Hiệu chỉnh" ở mọi nơi. Nhóm cũng cần bạn làm một việc: **sau mốc M0, chạy lệnh chẩn đoán một lần và
chụp màn hình Feetech FD** (khoảng 15 phút).

## Cách duyệt

Trả lời **"duyệt"** để đồng ý toàn bộ bộ tài liệu v0.2, gồm cả 4 phương án đề xuất. Nếu muốn đổi, ghi số câu
và phương án bạn chọn (ví dụ "2B, còn lại duyệt"), hoặc góp ý theo mã (F-…, AT-…). Nhóm chưa sửa mã cho tới
khi bạn duyệt.
