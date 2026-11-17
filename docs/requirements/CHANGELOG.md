# Nhật ký yêu cầu: Hibiscus Station

Ghi mọi vòng làm rõ yêu cầu, quyết định, phê duyệt và yêu cầu thay đổi (CR), kèm ngày và lời của khách
hàng. Phiên bản tài liệu: bản nháp v0.1, v0.2… (mỗi vòng một bản); phê duyệt = v1.0; mỗi CR được duyệt =
v1.1, v1.2…

## Vòng 1 · v0.1 · 2026-11-17

**Trạng thái:** bản nháp, chờ rà soát của SA và Tech Lead, sau đó gửi khách hàng. Chưa được phê duyệt.

**Đầu vào từ khách hàng (2026-11-17):**
* "ok, hoàn thiện lại Hibiscus cho tôi"
* Quyết định: sản phẩm = chỉ Hibiscus Station (nền tảng web để sau). v1.0 = các tính năng **hiện có**,
  đưa lên chuẩn chất lượng (zero-defect). Vùng Automation (nhánh `feat/automation`) **không** thuộc v1.0
  (Won't cho v1.0, làm sau). UAT của khách hàng = PC Windows + SO-101 leader + follower thật (nhà cung cấp
  không có Windows / tay thật: các AT đó là UAT của khách hàng). Người dùng = cả người mới (tiếng Việt,
  từng bước, không lệnh nào ngoài cài đặt) và kỹ sư (tuỳ chọn nâng cao). Tài liệu bằng tiếng Việt; mã và
  thuật ngữ kỹ thuật có thể giữ tiếng Anh.

**BA đã làm:**
* Viết đường cơ sở "như đã xây" từ Station 0.2.8 (`main` `12f36da`): README, `docs/spec/station.md`,
  `docs/spec/station-programs.md`, hướng dẫn người dùng vi / en, danh sách UAT phần cứng, `CHANGELOG.md`
  sản phẩm 0.1.0 – 0.2.8, chuỗi giao diện (`web/src/station/i18n`), các trang và địa chỉ (`StationApp.tsx`),
  API (`openapi.json`), CLI, cài đặt mặc định, test.
* Tạo: [BRD.md](BRD.md) (18 BR, 16 quy tắc nghiệp vụ, 8 câu hỏi mở), [SRS.md](SRS.md) (76 FR, 18 NFR, 11
  khoảng trống K-n), [FEATURES.md](FEATURES.md) (71 tính năng hiện có: 44 Must, 22 Should, 5 Could; 8
  Won't), [ACCEPTANCE.md](ACCEPTANCE.md) (92 AT), [REGRESSION.md](REGRESSION.md) (20 mục REG, REG-13 còn
  mở). ARCHITECTURE.md để SA viết.
* Mỗi lỗi hiện trường 0.2.1 – 0.2.8 thành một mục REG có cách tái hiện và kỳ vọng.

**Phát hiện cần sửa trước v1.0** (SRS §8): K-1 phiên bản 0.2.1 còn trong README / deploy; K-2 danh sách UAT
phần cứng còn ghi `wrist_roll` toàn vòng và `bus_lost`; K-3 lẫn "Hiệu chỉnh" / "Hiệu chuẩn"; K-4 chi tiết lỗi
tiếng Anh dưới câu tiếng Việt; K-5 hướng dẫn ghi giới hạn bước 5° cho mọi chuyển động; K-6 liên kết CHANGELOG
dừng ở 0.2.2; K-7 spec dev lỗi thời; K-8 cập nhật trên Windows cần gõ lệnh; K-9 / REG-13 servo của khách báo 0 °C
và dòng ~1000; K-10 Docker không cho Windows; K-11 `doctor` chưa đọc dòng và tải.

**Quyết định khách hàng cần đưa ra ở vòng này:** Q-1 nền tảng v1.0, Q-2 liên kết máy chủ Hibiscus, Q-3 mức
của vùng Chương trình, Q-4 cập nhật trên Windows (mỗi câu có đề xuất trong BRD §9). Q-5 – Q-8 có thể để vòng
2. Cần khách hàng gửi báo cáo `hibiscus-station doctor --verbose` (REG-13).

**Bước tiếp theo:** SA (ARCHITECTURE.md + rà soát) ‖ Tech Lead (khả thi, effort, mốc, mục "oái oăm") → BA
điều chỉnh (v0.2) → tóm tắt vòng gửi khách hàng.
