# Hibiscus Station: BRD v0.1 (2026-11-17) · trạng thái: bản nháp (vòng 1)

Tài liệu yêu cầu nghiệp vụ (Business Requirements Document) cho **Hibiscus Station v1.0**.
Người soạn: BA. Người duyệt: khách hàng. Tham khảo: SA, Tech Lead (vòng 1 chưa rà soát).
Tài liệu cùng bộ: [SRS.md](SRS.md) v0.1 · [FEATURES.md](FEATURES.md) v0.1 ·
[ACCEPTANCE.md](ACCEPTANCE.md) v0.1 · [REGRESSION.md](REGRESSION.md) v0.1 ·
ARCHITECTURE.md (SA viết) · [CHANGELOG.md](CHANGELOG.md).

> **Cách đọc.** Đây là **đường cơ sở "như đã xây" (as-built baseline)**: mô tả những gì Station
> 0.2.8 (nhánh `main`, commit `12f36da`) đang làm, để khách hàng duyệt đúng phạm vi v1.0. v1.0
> **không thêm tính năng mới**: v1.0 = các tính năng hiện có, đưa lên chuẩn chất lượng
> (không còn lỗi nào mở). Mọi tính năng ở đây đều có trạng thái "hiện có" (existing).
> Mã định danh (BR-, FR-, NFR-, F-, AT-, REG-, Q-) và thuật ngữ kỹ thuật giữ nguyên tiếng Anh.

## 1. Bối cảnh và vấn đề

Hibiscus Station là ứng dụng chạy trên máy tính cắm tay robot SO-100 / SO-101 (một tay
**follower** làm việc, một tay **leader** để người điều khiển bằng tay). Nó thay cho quy trình
LeLab: kết nối tay robot, hiệu chỉnh, thêm camera, điều khiển bằng tay leader (teleop), ghi dữ liệu
LeRobot, tải lên máy chủ Hibiscus để huấn luyện, kéo model về và chạy trên robot; ngoài ra lập
trình tay robot không cần huấn luyện (quỹ đạo, nhận diện camera, chương trình khối).

Vấn đề khách hàng gặp (theo các báo cáo hiện trường từ bản 0.2.1 đến 0.2.8, người dùng Windows với
tay SO-101 thật):

* Station không khởi động được trên Windows (0.2.1).
* Station điều khiển tay **giả lập** thay vì tay thật (0.2.2).
* Robot dừng vì "quá nhiệt" giả khi servo báo 0 °C (0.2.3).
* Hiệu chỉnh khác chuẩn LeLab (`wrist_roll` "xoay tròn, không cần ghi"), quá phức tạp, và teleop
  không chạy sau khi hiệu chỉnh (0.2.4, 0.2.5, 0.2.7).
* Teleop bị trễ so với LeLab (0.2.6); leader và follower bị gán nhầm (0.2.6).
* Lỗi "Access is denied" trên COM8 rồi mất bus (0.2.7).
* Không tạo được chương trình mới (0.2.7, 0.2.8).
* Sau e-stop khi "Chạy trên robot" thì không có đường phục hồi, lần chạy sau lại chạy tiếp giữa
  chừng (0.2.8).
* Số liệu tay leader vô lý (6,5 A, 0 °C) và báo động giả (0.2.8).
* Bước đang bị khoá trong thanh bước vẫn bấm dùng được (0.2.8).
* **Chưa giải quyết:** vì sao servo của khách đọc 0 °C và dòng khoảng 1000 (đơn vị thô).

Khách hàng không có tài liệu yêu cầu cho Station. Mỗi bản sửa lại làm lộ thêm lỗi. Khách hàng cần
một bộ yêu cầu được duyệt để biết chính xác v1.0 phải làm gì và để nghiệm thu được.

## 2. Mục tiêu nghiệp vụ và thước đo thành công

| # | Mục tiêu | Thước đo (đo được) |
|---|---|---|
| G-1 | Người mới (tiếng Việt) tự cài và dùng được Station trên Windows | Một người chưa dùng Station, chỉ có hướng dẫn tiếng Việt, đi từ cài đặt đến teleop tay thật trong ≤ 30 phút, không gõ lệnh nào ngoài lệnh cài đặt (đo trong UAT) |
| G-2 | Teleop ngang LeLab | Độ trễ leader → follower p50 ≤ 70 ms, không tệ hơn LeLab quá 10 ms trên cùng máy (NFR-1) |
| G-3 | An toàn | 100 % AT an toàn đạt trên tay thật; e-stop đóng băng tay trong < 100 ms (NFR-3) |
| G-4 | Không còn lỗi đã biết | 0 lỗi mở ở mọi mức khi phát hành; 20/20 mục REG đạt (REG-13 có kết luận về nguyên nhân) |
| G-5 | Thông tin đúng | 0 số đo vô lý hiển thị như giá trị thật; 0 cảnh báo giả trong 30 phút teleop trên tay của khách |
| G-6 | Nghiệm thu rõ ràng | Khách hàng ký biên bản nghiệm thu v1.0 sau UAT trên Windows + SO-101 thật |

## 3. Các bên liên quan và người dùng

| Nhóm | Ai | Tần suất | Trình độ | Cần gì |
|---|---|---|---|---|
| U-1 Người mới | Sinh viên, người làm lab, người dùng Việt Nam chưa quen robot / dòng lệnh | Hằng ngày khi thu dữ liệu | Không dùng terminal ngoài lệnh cài đặt | Tiếng Việt, từng bước, nút rõ ràng, thông báo dễ hiểu, không bị kẹt |
| U-2 Kỹ sư | Kỹ sư robot / ML | Hằng ngày | Biết lerobot, dòng lệnh, cấu hình | Tuỳ chọn nâng cao (fps, giới hạn an toàn, file hiệu chỉnh, API, tín hiệu HTTP/MQTT, `doctor`), không bị giao diện người mới cản |
| S-1 Khách hàng (chủ sản phẩm) | Người duyệt yêu cầu, chạy UAT | Mỗi vòng | — | Biết chính xác v1.0 làm gì, nghiệm thu được |
| S-2 Nhóm phát triển (vendor) | BA, SA, Tech Lead, dev, QC | — | — | Yêu cầu không mâu thuẫn, kiểm được |
| S-3 Máy chủ Hibiscus | Dịch vụ huấn luyện (ngoài phạm vi sản phẩm v1.0) | Khi tải lên / kéo model | — | Hợp đồng API v0.1.1 |

Không có phân quyền người dùng trong Station: ai mở được trang (từ chính máy đó, bằng liên kết có
token) thì dùng được mọi chức năng.

## 4. Quy trình hiện tại → quy trình mục tiêu

**Hiện tại (as-is):** khách dùng LeLab hoặc lệnh `lerobot-*`; không thấy nhiệt độ động cơ, không thấy
camera khi chạy model; khi thử Station 0.2.x thì gặp các lỗi hiện trường ở mục 1 và phải gửi log qua
lại.

**Mục tiêu (to-be), một vòng làm việc của người mới:**
1. Cài Station bằng một lệnh (Windows: PowerShell) → Station tự mở trình duyệt bằng tiếng Việt.
2. Trang Robot: tạo hồ sơ, bấm "Tìm tay follower" / "Tìm tay leader" → Kết nối → thấy vị trí khớp và
   nhiệt độ.
3. Trang Hiệu chỉnh: một luồng có hướng dẫn (follower → leader → kiểm tra hai tay) hoặc dùng lại file
   LeLab bằng một cú bấm.
4. Trang Camera: thêm camera.
5. Teleop mượt như LeLab; e-stop bằng Space.
6. Ghi dữ liệu bằng phím → / ← / Esc.
7. (Nếu có máy chủ Hibiscus) tải lên, mở huấn luyện, kéo model về.
8. Chạy model trên robot, thấy mọi camera và sức khoẻ động cơ.
9. (Không cần huấn luyện) ghi quỹ đạo, dựng chương trình khối, chạy thử rồi chạy trên robot.
10. Khi có sự cố: thông báo bằng lời dễ hiểu + đường thoát; nếu vẫn không được thì chạy
    `hibiscus-station doctor` và gửi file zip.

## 5. Yêu cầu nghiệp vụ

Ưu tiên: Must (bắt buộc cho v1.0) · Should (nên có, nằm trong v1.0 nếu đạt QC) · Could (có thể bỏ
khỏi v1.0 nếu không đạt) · Won't (không làm trong v1.0). Nguồn: QĐ = quyết định của khách hàng ngày
2026-11-17; FR-x.y.z = báo cáo hiện trường bản x.y.z (CHANGELOG.md của sản phẩm).

| ID | Nhu cầu | Ưu tiên | Nguồn | Tính năng |
|---|---|---|---|---|
| BR-1 | Người mới cài và chạy Station trên Windows 10/11 chỉ bằng lệnh cài đặt; mọi việc khác làm trên giao diện, từng bước, bằng tiếng Việt | Must | QĐ "người dùng là người mới (tiếng Việt, từng bước, không lệnh nào ngoài cài đặt)"; FR-0.2.1 | F-1, F-4, F-7, F-67 |
| BR-2 | Station luôn điều khiển đúng tay thật; không bao giờ lẫn tay giả lập; không nhầm leader với follower | Must | FR-0.2.2, FR-0.2.6 | F-5, F-8 – F-12, F-15 |
| BR-3 | Hiệu chỉnh theo chuẩn LeLab: ghi biên độ cho **mọi** khớp (kể cả `wrist_roll`); đơn giản; dùng lại được file LeLab; hiệu chỉnh xong thì teleop chạy được | Must | FR-0.2.4/0.2.5 ("khách muốn hiệu chỉnh chuẩn LeLab: ghi biên độ mọi khớp"), FR-0.2.7 | F-16 – F-20 |
| BR-4 | Teleop mượt, không trễ hơn LeLab | Must | FR-0.2.6 | F-24 – F-26 |
| BR-5 | An toàn khi tay chuyển động: e-stop, bảo vệ nhiệt, dead-man, giới hạn bước; tay không rơi ngoài ý muốn; sau mọi lần dừng luôn có đường phục hồi và lần chạy sau bắt đầu lại từ đầu | Must | Spec R1; FR-0.2.8 | F-28 – F-36 |
| BR-6 | Mọi con số, đơn vị, trạng thái hiển thị đều đúng và hợp lý; không báo động giả; số đo vô lý hiện là "không rõ" | Must | FR-0.2.3, FR-0.2.8 | F-31 – F-34 |
| BR-7 | Thu dữ liệu LeRobot với camera, xem lại được (kèm nhiệt độ từng tập) | Must | Spec mục tiêu 2 | F-21 – F-23, F-38 – F-40 |
| BR-8 | Đưa dữ liệu lên máy chủ Hibiscus để huấn luyện và kéo model đã huấn luyện về | Should (xem Q-2) | Spec mục tiêu 8 | F-41 – F-44 |
| BR-9 | Chạy model trên robot, thấy đúng khung hình camera model nhận và sức khoẻ động cơ | Must | Spec R2 | F-45 – F-51 |
| BR-10 | Lập trình tay robot không cần huấn luyện: quỹ đạo, tư thế, nhận diện camera, chương trình khối, chạy thử trước khi chạy thật | Should (xem Q-3) | Spec programs v0.1; FR-0.2.7, FR-0.2.8 | F-52 – F-62 |
| BR-11 | Kỹ sư có tuỳ chọn nâng cao (fps, giới hạn an toàn, file hiệu chỉnh, API, tín hiệu) mà không làm rối người mới | Must | QĐ "và kỹ sư (tuỳ chọn nâng cao)" | F-18, F-30, F-48, F-59, F-66 |
| BR-12 | Khi có sự cố, khách tự tạo được một báo cáo chẩn đoán để gửi cho nhà cung cấp | Must | FR-0.2.2 | F-63, F-64 |
| BR-13 | Không lỗi hiện trường nào từ 0.2.1 đến 0.2.8 tái diễn | Must | QĐ "zero-defect" | REGRESSION.md |
| BR-14 | Giao diện song ngữ, tiếng Việt là mặc định, chọn được tiếng Anh; sáng / tối; dùng được trên màn hình máy tính và điện thoại | Must | QĐ ngôn ngữ; spec §6 | F-67, F-68 |
| BR-15 | Cập nhật lên bản mới không mất hồ sơ, hiệu chỉnh, dữ liệu, quỹ đạo, chương trình | Must | Chuẩn chất lượng "rollback tested" | F-69 – F-71 |
| BR-16 | Dữ liệu ở lại máy; Station chỉ nhận kết nối từ chính máy đó, trừ khi kỹ sư bật chế độ LAN | Must | Spec §8 | F-6 |
| BR-17 | Vùng **Automation** (nhánh `feat/automation`) | **Won't (v1.0)**, dự kiến bản sau | QĐ "Automation OUT of v1.0" | W-1 |
| BR-18 | Nền tảng web (Hibiscus web platform) | **Won't (v1.0)**, dự kiến sau | QĐ "sản phẩm = chỉ Hibiscus Station" | W-2 |

## 6. Quy tắc nghiệp vụ

| ID | Quy tắc | Ví dụ | Trường hợp biên |
|---|---|---|---|
| RULE-1 | Chỉ một phiên chuyển động tại một thời điểm | Đang teleop thì không bắt đầu ghi được | Bấm "Bắt đầu" khi đang bận → thông báo "Station đang bận (trạng thái)" |
| RULE-2 | Không bắt đầu phiên mới khi có động cơ follower **nóng** (≥ 60 °C mặc định) | Khuỷu 61 °C → nút Bắt đầu bị chặn kèm lý do | Leader nóng không bao giờ chặn (leader được cử động bằng tay) |
| RULE-3 | Nguy hiểm nhiệt (≥ 65 °C hai lần liên tiếp, hoặc cờ quá nhiệt) trên follower → dừng an toàn: giữ, về tư thế nghỉ (nếu có), tắt mô-men; chỉ reset khi mọi động cơ dưới ngưỡng nóng | | ≥ 70 °C hoặc cờ quá nhiệt: tắt mô-men ngay, bỏ bước về tư thế nghỉ |
| RULE-4 | Ngưỡng hợp lệ: nguy hiểm ≤ giới hạn tự ngắt của servo − 3; nóng ≤ nguy hiểm − 3; ấm ≤ nóng − 5 | Servo tự ngắt 70 °C → nguy hiểm tối đa 67 °C | Servo báo giới hạn vô lý (ngoài 40–150 °C) → bỏ qua giới hạn đó, dùng mặc định |
| RULE-5 | Số đo vô lý là "không rõ" (hiện "—"), không bao giờ là cảnh báo, không bao giờ làm dừng robot | Nhiệt độ 0 °C, dòng > 3,5 A, tải ngoài ±100 %, điện áp ngoài 3–16 V | Khi **không** động cơ nào báo nhiệt độ thật: cảnh báo "không đọc được thông số", không phải quá nhiệt (xem Q-5) |
| RULE-6 | Tay leader (cử động bằng tay, không mô-men) không bao giờ gây cảnh báo dòng / tải / trạng thái / điện áp, không bao giờ làm dừng robot hay chặn phiên | | Nhiệt độ leader hiện tối đa mức "nóng" |
| RULE-7 | Mỗi lần chạy chương trình / quỹ đạo / model luôn bắt đầu lại từ đầu, không bao giờ "đi tiếp" mục tiêu của lần chạy bị dừng | E-stop giữa chương trình → lần chạy sau đi về điểm đầu rồi chạy từ t = 0 | |
| RULE-8 | E-stop và reset không bao giờ thay đổi hiệu chỉnh (không ghi EEPROM, không đổi file) | | |
| RULE-9 | Chương trình mới hoặc vừa sửa phải chạy thử (dry run) thành công trên tay giả lập trước khi được chạy trên robot | | Kỹ sư có thể tắt trong cài đặt (`programs.require_dry_run`) |
| RULE-10 | Sau khi hiệu chỉnh lại follower, quỹ đạo và tư thế cũ bị đánh dấu "Cần kiểm tra" và không chạy được trên robot cho tới khi phát lại ở 25 % và xác nhận | | |
| RULE-11 | Hồ sơ demo (tay giả lập) không bao giờ được kết nối khi Station chạy với tay thật | | Chế độ `--mock` dùng thư mục dữ liệu riêng |
| RULE-12 | Teleop chỉ bắt đầu khi tay leader cách follower ≤ 30° mỗi khớp; nếu xa hơn, Station đề nghị đưa follower chậm về tư thế leader | | Ghi dữ liệu không bao giờ tự căn |
| RULE-13 | Station không bao giờ tự đổi vai trò leader / follower; chỉ gợi ý (theo điện áp) và để người dùng bấm "Đổi chỗ" | Cổng ~5 V thường là leader; ≥ 6,5 V thường là follower | |
| RULE-14 | Một tập ghi chạm giới hạn thời gian thì được **lưu** (như lerobot), trừ khi người dùng chọn "Bỏ và ghi lại" | | |
| RULE-15 | Station không bao giờ huấn luyện trên máy robot; huấn luyện ở máy chủ Hibiscus | | |
| RULE-16 | Model chỉ được nhập từ định dạng an toàn (safetensors); checkpoint pickle (`*.bin`, `*.pt`) bị từ chối | | |

## 7. Phạm vi, giả định, ràng buộc

**Trong phạm vi v1.0:** toàn bộ tính năng hiện có của Station 0.2.8 liệt kê trong
[FEATURES.md](FEATURES.md) (F-1 … F-71), ở mức ưu tiên ghi trong đó, đưa lên chuẩn chất lượng.

**Ngoài phạm vi v1.0 (Won't):**
* W-1 Vùng Automation (nhánh `feat/automation` và các nhánh `feat/auto-*`): dự kiến bản sau, qua
  yêu cầu thay đổi (CR) riêng.
* W-2 Nền tảng web Hibiscus (máy chủ huấn luyện là hệ thống ngoài; v1.0 chỉ dùng hợp đồng API
  v0.1.1 của nó).
* W-3 Huấn luyện trên máy robot.
* W-4 Robot khác SO-100 / SO-101 (bimanual, LeKiwi, Koch, gamepad...).
* W-5 Cài ID / baudrate cho động cơ kit mới (dùng `lerobot-setup-motors`).
* W-6 Cập nhật tự động trong ứng dụng (đề xuất cho bản sau, xem Q-4).
* W-7 Đẩy dataset lên HF Hub; sửa / gộp dataset.
* W-8 Suy luận ONNX / bất đồng bộ / từ xa cho policy.

**Giả định:**
* A-1 Khách hàng có PC Windows 10/11 x64, tay SO-101 leader + follower thật, ít nhất một camera USB.
* A-2 Nhà cung cấp không có Windows và không có tay thật: mọi AT cần Windows + tay thật chỉ được
  chứng minh trong UAT của khách hàng (đánh dấu **[UAT-KH]** trong ACCEPTANCE.md). Nhà cung cấp kiểm
  trên Linux với tay giả lập, bộ giả lập servo STS3215 (`tests/sts_emulator.py`) và CI Windows (không
  có tay).
* A-3 Tính năng liên kết Hibiscus cần một máy chủ Hibiscus v0.1.1 và một personal access token.
* A-4 Bảng thanh ghi Feetech STS3215 (đơn vị dòng 6,5 mA/bước, bố cục bit trạng thái) chưa được xác
  nhận trên phần cứng thật (xem REG-13).

**Ràng buộc:**
* C-1 Giấy phép AGPL-3.0, repo công khai: tài liệu không chứa email, đường dẫn máy cá nhân hay dữ liệu
  khách hàng.
* C-2 lerobot 0.7.1 (commit `fe1c545`) là nền; tệp hiệu chỉnh phải dùng chung được với LeLab / lerobot.
* C-3 Python 3.12. Docker chỉ cho Linux (Docker Desktop trên Windows không chuyển được cổng USB serial).
* C-4 E-stop là phần mềm; luôn phải có cách ngắt nguồn tay robot bằng tay.

## 8. Rủi ro

| ID | Rủi ro | Tác động | Giảm thiểu |
|---|---|---|---|
| RK-1 | Servo của khách đọc 0 °C và dòng ~1000 (thô): bảo vệ nhiệt không hoạt động trên tay của khách | Không phát hiện quá nhiệt thật → servo tự ngắt, tay rơi | REG-13: cần báo cáo `hibiscus-station doctor --verbose` của khách; `doctor` hiện chưa đọc dòng và tải (SRS K-11), nhà cung cấp phải bổ sung trước khi xin báo cáo; Q-5 quyết định hành vi khi không đọc được nhiệt |
| RK-2 | Nhà cung cấp không kiểm được Windows + tay thật | Lỗi chỉ lộ ở UAT | Bộ giả lập STS3215 có thời gian thật, CI Windows, danh sách UAT ngắn, có video |
| RK-3 | Quy tắc zero-defect: một lỗi nhỏ loại cả tính năng và tính năng phụ thuộc | Tính năng Should/Could có thể bị loại khỏi v1.0 | Q-2, Q-3 để khách chọn trước phần nào có thể bỏ |
| RK-4 | Phạm vi rộng (71 tính năng) | Thời gian QC dài | Tech Lead đặt mốc; Could được cắt trước |
| RK-5 | Tài liệu người dùng cũ mâu thuẫn với sản phẩm (xem SRS §8 "Khoảng trống") | Người mới làm sai theo hướng dẫn | Sửa tài liệu là một phần của Done |

## 9. Câu hỏi mở cho khách hàng

Chỉ là quyết định của khách hàng (ưu tiên, bỏ gì, hành vi, từ ngữ). Mỗi câu có **đề xuất mặc định**:
nếu khách hàng không trả lời khác, nhà cung cấp làm theo đề xuất. **Vòng 1 cần quyết định Q-1 đến
Q-4**; Q-5 đến Q-8 có thể để vòng 2.

**Q-1. Nền tảng nào phải đạt trong v1.0?**
Station hiện chạy trên Windows 10/11, Linux (wheel và Docker), macOS, Raspberry Pi 5 và Jetson Orin.
Mỗi nền tảng nằm trong v1.0 đều phải đạt mọi AT (chuẩn zero-defect).
*Đề xuất:* Windows 10/11 x64 (wheel) = **Must**, nghiệm thu bằng UAT của khách hàng;
Ubuntu 22.04/24.04 x86_64 (wheel) = **Should**, nhà cung cấp tự kiểm; macOS, Docker (Linux PC,
Raspberry Pi 5, Jetson Orin) = **Could**: vẫn giữ trong sản phẩm nhưng ghi "chưa nghiệm thu" và không
chặn phát hành v1.0.

**Q-2. Các tính năng liên kết máy chủ Hibiscus (ghép nối, tải lên, trang Huấn luyện, kéo model)
có thuộc v1.0 không?** Chúng cần một máy chủ Hibiscus và token để nghiệm thu.
*Đề xuất:* giữ trong v1.0 ở mức **Should**: nhà cung cấp kiểm với máy chủ thử theo hợp đồng
v0.1.1; khách hàng UAT nếu có tài khoản. Nếu một tính năng này không đạt, nó bị loại khỏi v1.0
nhưng không chặn phát hành (nhập model bằng file zip vẫn là Must).

**Q-3. Vùng Chương trình (quỹ đạo, tư thế, nhận diện, trình soạn khối) ở mức nào trong v1.0?**
Đây là vùng lớn nhất (khoảng 1/3 giao diện) và có hai lỗi hiện trường (REG-9, REG-10).
*Đề xuất:* quỹ đạo, tư thế, Robot 3D, trình soạn khối, chạy thử, chạy trên robot = **Should**;
tín hiệu ngoài HTTP / MQTT, webhook thông báo và khối "chạy model trong chương trình" = **Could**
(dành cho kỹ sư, cắt trước nếu không đạt).

**Q-4. Cập nhật phiên bản trên Windows cho người mới.** Hiện nay muốn lên bản mới, người dùng phải
gõ lại lệnh `uv tool install ...` có số phiên bản mới. Điều này trái với "không lệnh nào ngoài cài
đặt". v1.0 chỉ gồm tính năng hiện có.
*Đề xuất:* v1.0 giữ cách hiện tại, coi lệnh cập nhật là "lệnh cài đặt" (cùng một lệnh, in sẵn trong
hướng dẫn tiếng Việt và trong ghi chú phát hành, chép-dán được); thông báo "có bản mới" ngay trong
ứng dụng ghi vào danh sách đề xuất cho bản sau (CR).

**Q-5. Khi Station không đọc được nhiệt độ thật của bất kỳ động cơ follower nào (như servo của
khách đang báo 0 °C), robot có được chạy không?** Lúc đó bảo vệ nhiệt của Station không hoạt động;
chỉ còn bảo vệ 70 °C của chính servo (tay có thể rơi).
*Đề xuất:* vẫn cho chạy (như hiện nay, để không chặn khách), nhưng hiện cảnh báo cố định màu cam
trên mọi màn hình chuyển động: "Không đọc được nhiệt độ động cơ: bảo vệ nhiệt của Station đang tắt.
Theo dõi tay robot và gửi báo cáo chẩn đoán." Đồng thời khách hàng gửi báo cáo
`hibiscus-station doctor --verbose` để đóng REG-13.

**Q-6. Kiểm tra hai tay sau hiệu chỉnh báo lệch (> 20°): chặn teleop hay vẫn cho thử?**
*Đề xuất:* giữ như hiện nay: hiện lý do (sai tư thế / sai tệp / nhầm cổng) và nút "Hiệu chỉnh lại",
kèm nút phụ "Vẫn thử teleop" (teleop vẫn từ chối nếu hai tay lệch quá 30°).

**Q-7. Tuỳ chọn nâng cao cho kỹ sư nên ẩn hay hiện mặc định?**
Hiện nay: Hiệu chỉnh và Chạy model đã có mục "Nâng cao" đóng sẵn; ô chọn fps của Teleop và trang
Cài đặt hiện thẳng.
*Đề xuất:* giữ như hiện nay cho v1.0 (fps Teleop mặc định "nhanh nhất" nên người mới không cần đổi;
Cài đặt là trang riêng của kỹ sư); không thêm màn hình "chế độ người mới / kỹ sư".

**Q-8. Thuật ngữ tiếng Việt cho "calibrate".** Giao diện đang dùng lẫn "Hiệu chỉnh" và "Hiệu chuẩn".
*Đề xuất:* dùng **"Hiệu chỉnh"** ở mọi nơi (đã dùng trong thanh bước và hướng dẫn). Tương tự giữ các
từ "teleop", "follower", "leader", "e-stop" như hiện nay (người dùng lerobot quen), có giải thích
lần đầu trong hướng dẫn.

**Cần khách hàng cung cấp (không phải quyết định):** báo cáo `hibiscus-station doctor --verbose`
chạy trên PC Windows của khách, khi đã cắm cả hai tay và đã tắt Station / LeLab (để đóng REG-13).
Đề xuất (chờ Tech Lead xác nhận): nhà cung cấp bổ sung cho `doctor` phần đọc dòng và tải (SRS K-11)
trước khi nhờ khách chạy, để khách chỉ phải chạy một lần.
