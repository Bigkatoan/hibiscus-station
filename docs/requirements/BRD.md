# Hibiscus Station: BRD v1.0 (2026-11-17) · trạng thái: **đã duyệt** (khách hàng duyệt ngày 2026-11-17, đường cơ sở)

Tài liệu yêu cầu nghiệp vụ (Business Requirements Document) cho **Hibiscus Station v1.0**.
Người soạn: BA. Người duyệt: khách hàng. Tham khảo: SA ([REVIEW-SA.md](REVIEW-SA.md)), Tech Lead
([REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md)).
Tài liệu cùng bộ: [SRS.md](SRS.md) v1.0 · [FEATURES.md](FEATURES.md) v1.0 ·
[FEATURES-APPROVED.md](FEATURES-APPROVED.md) v1.0 · [ACCEPTANCE.md](ACCEPTANCE.md) v1.0 ·
[REGRESSION.md](REGRESSION.md) v1.0 · [ARCHITECTURE.md](ARCHITECTURE.md) v1.0 · [CHANGELOG.md](CHANGELOG.md).

> **Phê duyệt (2026-11-17).** Khách hàng chọn "1. A, 2. A, 3. A, 4. A" cho QĐ-1 – QĐ-4 và duyệt toàn bộ bộ
> tài liệu: "Duyệt, bắt đầu làm". v1.0 = v0.2 với bốn quyết định đã chốt (§9). Mọi thay đổi sau ngày này là
> yêu cầu thay đổi (CR) và ghi ở [CHANGELOG.md](CHANGELOG.md).

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
| G-1 | Người mới (tiếng Việt) tự cài và dùng được Station trên Windows | Một người chưa dùng Station, chỉ có hướng dẫn tiếng Việt, đi từ cài đặt đến teleop tay thật trong ≤ 30 phút **không tính thời gian tải** (mạng ≥ 20 Mbps, torch CPU), không gõ lệnh nào ngoài lệnh cài đặt (đo trong UAT-1). Lệnh hỗ trợ `hibiscus-station doctor` (chép-dán từ hướng dẫn) được coi cùng loại với lệnh cài (FL-5) |
| G-2 | Teleop ngang LeLab | Trên giả lập có thời gian thật: trễ bám p50 ≤ 70 ms và ≤ vòng tham chiếu kiểu LeLab + 10 ms ở adapter 1 ms và 8 ms (NFR-1a); trên PC của khách: khách teleop lần lượt LeLab và Station cùng tay, đánh giá "không chậm hơn LeLab" (NFR-1c) |
| G-3 | An toàn | 100 % AT an toàn đạt (vendor: test tự động + giả lập; khách: trên tay thật). E-stop: không lệnh vị trí mới sau ≤ 1 nhịp (≤ 1 nhịp + 1 lần suy luận khi chạy model, NFR-3a), Space → máy chủ p99 ≤ 50 ms (NFR-3b), khách thấy tay dừng ngay (NFR-3c). Trên servo không báo nhiệt: AT-42 ghi "không áp dụng" có chữ ký khách, AT-93 phải đạt |
| G-4 | Không còn lỗi đã biết | 0 lỗi mở ở mọi mức khi phát hành; 20/20 mục REG đạt. REG-13 có kết luận: bản `doctor` mới phát hành ở M0 (tuần 1); nếu sau 1 tuần kể từ ngày hẹn UAT-0 vẫn chưa có báo cáo, REG-13 đóng với kết luận "servo không báo nhiệt (chưa rõ vì sao)" và áp hành vi của QĐ-1 (SA-Q3) |
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
| BR-1 | Người mới cài và chạy Station trên Windows 10/11 chỉ bằng lệnh cài đặt (QĐ-3 A: một lệnh, cũng dùng để cập nhật và quay lại bản cũ); mọi việc khác làm trên giao diện, từng bước, bằng tiếng Việt; lệnh hỗ trợ `doctor` chép-dán khi có sự cố | Must | QĐ "người dùng là người mới (tiếng Việt, từng bước, không lệnh nào ngoài cài đặt)"; FR-0.2.1 | F-1, F-4, F-7, F-67 |
| BR-2 | Station luôn điều khiển đúng tay thật; không bao giờ lẫn tay giả lập; không nhầm leader với follower | Must | FR-0.2.2, FR-0.2.6 | F-5, F-8 – F-12, F-15 |
| BR-3 | Hiệu chỉnh theo chuẩn LeLab: ghi biên độ cho **mọi** khớp (kể cả `wrist_roll`); đơn giản; dùng lại được file LeLab; hiệu chỉnh xong thì teleop chạy được | Must | FR-0.2.4/0.2.5 ("khách muốn hiệu chỉnh chuẩn LeLab: ghi biên độ mọi khớp"), FR-0.2.7 | F-16 – F-20 |
| BR-4 | Teleop mượt, không trễ hơn LeLab | Must | FR-0.2.6 | F-24 – F-26 |
| BR-5 | An toàn khi tay chuyển động: e-stop, bảo vệ nhiệt, dead-man, giới hạn bước; tay không rơi ngoài ý muốn; sau mọi lần dừng luôn có đường phục hồi và lần chạy sau bắt đầu lại từ đầu | Must | Spec R1; FR-0.2.8 | F-28 – F-36 |
| BR-6 | Mọi con số, đơn vị, trạng thái hiển thị đều đúng và hợp lý; không báo động giả; số đo vô lý hiện là "không rõ" | Must | FR-0.2.3, FR-0.2.8 | F-31 – F-34 |
| BR-7 | Thu dữ liệu LeRobot với camera, xem lại được (kèm nhiệt độ từng tập) | Must | Spec mục tiêu 2 | F-21 – F-23, F-38 – F-40 |
| BR-8 | Đưa dữ liệu lên máy chủ Hibiscus để huấn luyện và kéo model đã huấn luyện về | Should (Q-2) | Spec mục tiêu 8 | F-41 – F-44 |
| BR-9 | Chạy model trên robot, thấy đúng khung hình camera model nhận và sức khoẻ động cơ | Must | Spec R2 | F-45 – F-51 |
| BR-10 | Lập trình tay robot không cần huấn luyện: quỹ đạo, tư thế, nhận diện camera, chương trình khối, chạy thử trước khi chạy thật | Should (Q-3) | Spec programs v0.1; FR-0.2.7, FR-0.2.8 | F-52 – F-62 |
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
| RULE-5 | Số đo vô lý là "không rõ" (hiện "—"), không bao giờ là cảnh báo, không bao giờ làm dừng robot | Nhiệt độ 0 °C, dòng > 3,5 A, tải ngoài ±100 %, điện áp ngoài 3–16 V | Khi **không** động cơ nào báo nhiệt độ thật: cảnh báo "không đọc được thông số", không phải quá nhiệt (xem QĐ-1, AT-93) |
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
* W-6 Cập nhật tự động trong ứng dụng (đề xuất cho bản sau; cập nhật bằng lệnh một dòng, QĐ-3).
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
  nhận trên phần cứng thật (xem REG-13, SP-1).
* A-5 Khách có công cụ Feetech FD chính hãng trên PC Windows (dùng để đối chứng nhiệt độ / điện áp / dòng
  ở UAT-0 và AT-40, thay cho nhiệt kế và đồng hồ vạn năng).

**Ràng buộc:**
* C-1 Giấy phép AGPL-3.0, repo công khai: tài liệu không chứa email, đường dẫn máy cá nhân hay dữ liệu
  khách hàng. Mọi gói phân phối cùng Station phải có giấy phép tương thích AGPL; gói `hibiscus` (Hibiscus
  CLI v0.1.1) hôm nay khai "Proprietary" → QĐ-4 A: Station dùng Hibiscus CLI **v0.1.2** phát hành với giấy
  phép **Apache-2.0** (phụ thuộc ngoài EXT-1 bên dưới, SA-L1).
* C-2 lerobot 0.7.1 (commit `fe1c545`) là nền; tệp hiệu chỉnh phải dùng chung được với LeLab / lerobot.
* C-3 Python 3.12. Docker chỉ cho Linux (Docker Desktop trên Windows không chuyển được cổng USB serial).
* C-4 E-stop là phần mềm và phím Space chỉ có tác dụng khi cửa sổ Station đang được chọn; luôn phải có
  cách ngắt nguồn tay robot bằng tay. Khuyến nghị (điều kiện của UAT chuyển động): một **công tắc ngắt
  nguồn** trên dây nguồn follower (công tắc DC hoặc nút nấm, SA-S2); AT-94 kiểm Station xử lý đúng khi mất
  nguồn giữa chuyển động.
* C-5 (QĐ-2 A) Nền tảng thuộc nghiệm thu v1.0: Windows 10/11 x64 = Must (UAT của khách); Ubuntu 22.04 /
  24.04 x86_64 = Should (vendor kiểm); Docker trên PC Linux x86_64, image `-cpu` = Could (vendor kiểm). macOS,
  wheel Linux arm64, Docker `-cuda`, Raspberry Pi 5, Jetson Orin = **bản xem trước**, ngoài nghiệm thu (W-9).

**Phụ thuộc ngoài (không làm trong repo Station):**
* **EXT-1 (QĐ-4 A)** Chủ sở hữu nền tảng Hibiscus phát hành gói `hibiscus` (Hibiscus CLI) **v0.1.2** với giấy
  phép **Apache-2.0** và tệp LICENSE, không đổi mã so với v0.1.1. Việc này làm trong repo của nền tảng Hibiscus,
  ghi là CR bên ngoài (CR-EXT-1); nhóm Station không sửa repo khác. Sau khi v0.1.2 có, Station ghim lại `hibiscus`
  v0.1.2 (một thay đổi phụ thuộc trong Station, kiểm bằng AT-98). **Chặn phát hành v1.0:** AT-98 (F-6, Must)
  chỉ đạt khi Station ghim v0.1.2; cần có trước khi QC bản ứng viên M1.
## 8. Rủi ro

| ID | Rủi ro | Tác động | Giảm thiểu |
|---|---|---|---|
| RK-1 | Servo của khách đọc 0 °C và dòng ~1000 (thô): bảo vệ nhiệt không hoạt động trên tay của khách | Không phát hiện quá nhiệt thật → servo tự ngắt, tay rơi | REG-13: cần báo cáo `hibiscus-station doctor --verbose` của khách; `doctor` hiện chưa đọc dòng và tải (SRS K-11), nhà cung cấp phải bổ sung trước khi xin báo cáo; QĐ-1 A: cho chạy, xác nhận mỗi lần kết nối, banner cam, phiên không người cầm leader dừng sau 10 phút; `doctor` mới ở M0 và UAT-0 (SP-1) |
| RK-2 | Nhà cung cấp không kiểm được Windows + tay thật | Lỗi chỉ lộ ở UAT | Bộ giả lập STS3215 có thời gian thật, CI Windows, danh sách UAT ngắn, có video |
| RK-3 | Quy tắc zero-defect: một lỗi nhỏ loại cả tính năng và tính năng phụ thuộc | Tính năng Should/Could có thể bị loại khỏi v1.0 | Q-2, Q-3 (đã duyệt): Should / Could không đạt thì ra khỏi v1.0, không chặn |
| RK-4 | Phạm vi rộng (71 tính năng) | Thời gian QC dài | Tech Lead đặt mốc; Could được cắt trước |
| RK-5 | Tài liệu người dùng cũ mâu thuẫn với sản phẩm (xem SRS §8 "Khoảng trống") | Người mới làm sai theo hướng dẫn | Sửa tài liệu là một phần của Done |
| RK-6 | Môi trường cài trên PC khách khác môi trường QC đã kiểm (phụ thuộc trôi theo ngày, cần git) | Lỗi chỉ có trên máy khách, không tái hiện được | P-1 / QĐ-3 A (lệnh một dòng, phụ thuộc cố định) |
| RK-7 | Gói `hibiscus` khai "Proprietary" trong khi Station là AGPL công khai | Rủi ro pháp lý khi phát hành công khai | QĐ-4 A: Hibiscus CLI v0.1.2 Apache-2.0 (EXT-1); chưa có v0.1.2 thì AT-98 FAIL và v1.0 không phát hành |
| RK-8 | Nhiều lượt UAT do quy tắc zero-defect (mỗi lỗi khách thấy = sửa → QC → UAT lại) | Trễ lịch, tốn thời gian của khách | UAT chia 3 buổi ngắn (ACCEPTANCE "Kế hoạch UAT"); vendor chạy phần còn lại và gửi video |

## 9. Quyết định của khách hàng (đã chốt) và việc còn mở

Khách hàng trả lời ngày 2026-11-17: **"1. A, 2. A, 3. A, 4. A"**, rồi khi được hỏi có duyệt toàn bộ bộ tài liệu
v0.2 không: **"Duyệt, bắt đầu làm"**. Bốn quyết định dưới đây đã chốt; các phương án không chọn ghi lại để truy
vết. Muốn đổi một quyết định = yêu cầu thay đổi (CR).

### Quyết định đã chốt (QĐ-1 – QĐ-4)

**QĐ-1 (thay Q-5) = A. Khi Station không đọc được nhiệt độ thật của bất kỳ động cơ follower nào, robot vẫn được
chạy**, với ba điều kiện:
1. Mỗi lần kết nối, Station hiện hộp xác nhận "Không đọc được nhiệt độ động cơ: bảo vệ nhiệt của Station đang
   tắt" với "Tôi hiểu, tiếp tục" / "Ngắt kết nối"; người dùng phải xác nhận mới dùng được tay.
2. Banner cam cố định trên mọi màn hình chuyển động.
3. Phiên không có người cầm leader (chạy model, phát lại, phát quỹ đạo, chương trình) tự dừng an toàn sau
   **10 phút** chạy liên tục (kỹ sư đổi được trong Cài đặt); teleop và ghi dữ liệu không giới hạn (người cầm
   leader nhìn thấy tay).

Trên tay không báo nhiệt, AT-42 ghi "không áp dụng" có chữ ký khách; AT-93 phải đạt. (P-3, SA-S1, FR-33.)
Không chọn: B (chỉ banner), C (chặn mọi chuyển động).

**QĐ-2 (thay Q-1) = A. Nền tảng thuộc nghiệm thu v1.0:**
* Windows 10/11 x64 (wheel) = **Must**, khách nghiệm thu bằng UAT.
* Ubuntu 22.04 / 24.04 x86_64 (wheel) = **Should**, vendor kiểm.
* Docker trên PC Linux x86_64, image `-cpu` = **Could**, vendor kiểm (vào v1.0 nếu đạt).
* macOS, wheel Linux arm64, Docker `-cuda`, Raspberry Pi 5, Jetson Orin = **bản xem trước** (W-9): vẫn cài được,
  README / ghi chú phát hành / `install.sh` ghi rõ "bản xem trước, không thuộc nghiệm thu v1.0" kèm lỗi đã biết;
  lỗi ở đó không chặn phát hành.

(C-5, NFR-9, SA-P2.) Không chọn: B (nghiệm thu mọi nền tảng), C (chỉ Windows).

**QĐ-3 (thay Q-4) = A. Cài và cập nhật trên Windows bằng một lệnh.** **Một** lệnh PowerShell chép-dán (`irm <địa
chỉ bản phát hành>/install.ps1 | iex`): không cần git, không cần quyền admin, không cần Python có sẵn; cài uv nếu
thiếu; cài Station với **đúng bộ thư viện nhóm đã kiểm** (phụ thuộc cố định theo `uv.lock`). Dán lại **cùng lệnh**
để cập nhật; cùng lệnh kèm số phiên bản để quay lại bản cũ (ra đúng bộ thư viện của bản đó). Không có nút cập nhật
trong ứng dụng (W-6). (P-1, ADR-13, FR-1, FR-69, AT-1, AT-84.) Không chọn: B (hai lệnh, cần git).

**QĐ-4 (mới) = A. Giấy phép Hibiscus CLI: Apache-2.0 trong bản v0.1.2.** Chủ sở hữu phát hành gói `hibiscus`
(Hibiscus CLI) **v0.1.2** với giấy phép **Apache-2.0** kèm tệp LICENSE, không đổi mã; Station ghim lại v0.1.2.
Việc phát hành nằm ngoài repo Station: phụ thuộc ngoài **EXT-1** (§7), CR bên ngoài CR-EXT-1. (C-1, NFR-14,
ADR-12, AT-98, SA-L1.) Không chọn: B (AGPL-3.0), C (viết lại phần kết nối máy chủ).

### Câu đã có đề xuất, duyệt cùng bộ tài liệu

* **Q-2.** Liên kết máy chủ Hibiscus (F-41 – F-44) = **Should**: vendor kiểm với máy chủ thử theo hợp đồng
  v0.1.1; khách UAT nếu có tài khoản; không đạt thì ra khỏi v1.0, không chặn (nhập model bằng zip vẫn Must).
* **Q-3.** Chương trình: quỹ đạo, tư thế, Robot 3D, trình soạn khối, chạy thử, chạy trên robot = **Should**;
  tín hiệu ngoài HTTP / MQTT, webhook và khối "chạy model trong chương trình" = **Could**.
* **Q-6.** Kiểm tra hai tay báo lệch: giữ như hiện nay (lý do theo từng trường hợp + "Hiệu chỉnh lại" + nút
  phụ "Vẫn thử teleop"; teleop vẫn từ chối nếu lệch quá 30°). Teleop không còn phụ thuộc bước Kiểm tra
  (FL-9).
* **Q-7.** Tuỳ chọn nâng cao: giữ như hiện nay (Hiệu chỉnh và Chạy model có "Nâng cao" đóng sẵn; ô fps
  Teleop hiện trên trang, mặc định "nhanh nhất"; Cài đặt là trang của kỹ sư).
* **Q-8.** Thuật ngữ: **"Hiệu chỉnh"** ở mọi nơi; giữ "teleop", "follower", "leader", "e-stop" kèm giải thích
  lần đầu; "đặt lại" thay cho "reset" trong câu tiếng Việt (D-12).
* **Q-1, Q-4, Q-5:** thay bằng QĐ-2, QĐ-3, QĐ-1.

Không còn câu hỏi mở cho khách hàng về phạm vi hay hành vi của v1.0.

### Cần khách hàng cung cấp (không phải quyết định)

* **UAT-0 (khoảng 15 phút, ngay sau M0):** cài bản M0 bằng lệnh một dòng, cắm cả hai tay, tắt Station và LeLab,
  chạy `hibiscus-station doctor --verbose` và gửi tệp zip; mở công cụ Feetech FD trên cùng PC, chụp màn hình nhiệt
  độ / điện áp / dòng của một servo follower. Kết quả đóng REG-13 (servo báo nhiệt thật hay không: nếu không thì
  áp hành vi QĐ-1) và chốt đích NFR-1 / NFR-2 cho Windows (D-9).
* Xác nhận lịch ba buổi UAT (ACCEPTANCE "Kế hoạch UAT") và loại bộ chuyển USB của hai tay (VID:PID có trong
  báo cáo `doctor`).

### Việc còn mở của nhà cung cấp (không đổi phạm vi, theo dõi trong [FEATURES-APPROVED.md](FEATURES-APPROVED.md))

* **OI-1** Tech Lead ước effort các mục ✚ (P-1 – P-3, P-6, P-7, SP-1 – SP-3, SP-7) khi bắt đầu M0; tổng 82 ngày
  công chưa gồm các mục này.
* **OI-2** QC xác nhận D-19 – D-23 bằng chạy thử (D-19 chỉ trên Windows: UAT-1 bước 14).
* **OI-3** SA cập nhật ARCHITECTURE §6 theo định nghĩa NFR của SRS v1.0; chốt tên lý do dừng `thermal_blind` và tên
  cài đặt giới hạn 10 phút (QĐ-1).
* **OI-4** EXT-1: chờ chủ sở hữu nền tảng Hibiscus phát hành Hibiscus CLI v0.1.2 (Apache-2.0); sau đó Station ghim
  lại (QĐ-4).
