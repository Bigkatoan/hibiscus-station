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

## Vòng 1 · Reconcile · v0.2 · 2026-11-17

**Trạng thái:** bản nháp v0.2, gửi khách hàng cùng [ROUND-1-SUMMARY.md](ROUND-1-SUMMARY.md). Chưa được phê
duyệt.

**Đầu vào:** rà soát độc lập của SA ([ARCHITECTURE.md](ARCHITECTURE.md) v0.1, [REVIEW-SA.md](REVIEW-SA.md): 28
flag, 7 mục chặn) và Tech Lead ([REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md): kiểm sơ bộ trên Linux với đúng wheel
0.2.8, 18 lỗi D-1 – D-18, 12 flag FL-1 – FL-12, effort và mốc M0 – M3).

**BA đã làm (mọi tài liệu lên v0.2):**
* [FEATURES.md](FEATURES.md): điền effort và mốc của Tech Lead cho 71 / 71 tính năng; thêm cột "Lỗi / khoảng
  trống đã biết" và trạng thái vòng 1 (ĐẠT\* 33 · LỖI 22 · KHÔNG KIỂM ĐƯỢC 16; F-66 tính là LỖI vì D-5); bảng
  23 lỗi D-n (D-19 – D-23 từ SA, chờ QC xác nhận); 8 đề xuất thay đổi P-1 – P-8; bảng mốc; ma trận truy vết
  BR → FR / NFR → F → AT và NFR → AT; Won't thêm W-9 – W-12; F-24 không còn phụ thuộc F-19 (FL-9).
* [BRD.md](BRD.md): G-1 – G-4 viết lại cho đo được (SA-Q2, SA-N1, SA-N3, SA-Q3); C-1 (giấy phép gói phụ thuộc),
  C-4 (Space chỉ khi cửa sổ được chọn, công tắc ngắt nguồn); A-5 (Feetech FD); rủi ro RK-6 – RK-8; §9: bốn quyết
  định **QĐ-1** (thay Q-5), **QĐ-2** (thay Q-1), **QĐ-3** (thay Q-4), **QĐ-4** (mới, giấy phép Hibiscus CLI); Q-2,
  Q-3, Q-6 – Q-8 giữ đề xuất, duyệt cùng bộ tài liệu; UAT-0 là việc khách cung cấp.
* [SRS.md](SRS.md): NFR-1 tách 1a / 1b / 1c, NFR-3 tách 3a / 3b / 3c; NFR-2, NFR-4, NFR-5, NFR-6, NFR-7, NFR-9 –
  NFR-11, NFR-13 – NFR-18 viết lại theo SA và Tech Lead; FR-1 – FR-5, FR-7, FR-9 – FR-13, FR-19 – FR-21, FR-24,
  FR-28, FR-31, FR-33, FR-37, FR-38, FR-47, FR-48, FR-63, FR-64, FR-69, FR-73, FR-75 cập nhật (mỗi chỗ ghi
  "(v0.2: …)" kèm mã flag); §7 thêm 3 luồng phục hồi; §8 nối K-n với D-n.
* [ACCEPTANCE.md](ACCEPTANCE.md): 49 AT viết lại để chạy được đúng như viết (lệnh, test tự động có tên, lệnh
  chèn lỗi, máy chủ thử, mạng cô lập); bỏ nhiệt kế / đồng hồ vạn năng / video 240 fps; thêm AT-93 – AT-98 (tổng 98);
  UAT của khách thành ba buổi: UAT-0 (~15 phút), UAT-1 (15 bước, ~60 – 90 phút), UAT-2 (~45 phút).
* [REGRESSION.md](REGRESSION.md): REG-3, REG-5, REG-8, REG-13 cập nhật (QĐ-1, NFR mới, port_busy, UAT-0 và hạn).
* [ARCHITECTURE.md](ARCHITECTURE.md): chỉ đổi phiên bản và ghi chú v0.2 (SA cập nhật §6 ở vòng 2).

**Flag đã áp dụng:** SA-S1 → P-3 / QĐ-1 / AT-93; SA-S2 → C-4, FR-28, W-11, AT-94; SA-N1, FL-2, FL-3 → NFR-1a – 1c,
AT-31; SA-N2 → NFR-2, D-21; SA-N3 → NFR-3a – 3c, NFR-4, P-2, D-20, AT-88, AT-97; SA-N4, FL-4 → NFR-13, P-8, AT-40;
SA-W1 → FR-9, AT-12; SA-W2 → FR-12, FR-13, AT-17, AT-18; SA-W3 → FR-75, D-19, P-6, AT-95; SA-W4 → FR-21, NFR-5,
W-12, AT-28; SA-W5 → NFR-5; SA-W6 → FR-64; SA-P1 → FR-1, FR-69, P-1 / QĐ-3, AT-1, AT-84; SA-P2 → QĐ-2, NFR-9,
W-9; SA-Q2 → G-1; SA-C1, SA-C2 → NFR-18, NFR-9, AT-2; SA-U1 → NFR-10, AT-91; SA-U2 → NFR-11; SA-F1 → FR-10; SA-F2 →
FR-12, D-22, P-7, AT-96; SA-F3 → FR-20, NFR-15, AT-27; SA-F4 → NFR-16, FR-47, D-23; SA-F5 → FR-37 (chấp nhận như
đã xây); SA-F6 → FR-63; SA-L1 → C-1, NFR-14, QĐ-4, AT-98; SA-Q1, FL-6 → Kế hoạch UAT; SA-Q3 → G-4, REG-13; FL-1 →
P-5, FR-7, FR-73, AT-10; FL-5 → BR-1, FR-63, W-10; FL-7 → NFR-11, AT-82; FL-8 → AT-9; FL-9 → F-24; FL-10 → P-4,
FR-5, AT-7; FL-11 → FR-63, AT-77; FL-12 → môi trường ACCEPTANCE, M0.

**Khác với đề xuất của SA (BA giữ, ghi lý do):** Docker Linux x86_64 `-cpu` giữ **Could** (SA đề xuất Should) để
không kéo dài M2 (QC Docker cần máy riêng); SA-F5 chấp nhận "dọn phiên lúc khởi động" thay vì thêm sửa.

**Quyết định khách hàng cần đưa ra ở vòng này:** QĐ-1 – QĐ-4 (BRD §9). **Cần khách cung cấp:** UAT-0 sau M0.

**Bước tiếp theo:** khách đọc tóm tắt vòng 1 và trả lời QĐ-1 – QĐ-4 (hoặc "duyệt" để nhận mọi phương án đề
xuất); vòng 2: Tech Lead ước các mục mới (P-1 – P-3, P-6, P-7, SP), QC xác nhận D-19 – D-23 và rà ACCEPTANCE v0.2,
SA cập nhật ARCHITECTURE §6.

## Phê duyệt · v1.0 (đường cơ sở) · 2026-11-17

**Trạng thái:** **ĐÃ DUYỆT.** Bộ tài liệu v1.0 là đường cơ sở; Build bắt đầu từ đây. Mọi thay đổi sau ngày này là
yêu cầu thay đổi (CR), ghi ở nhật ký này và nâng [FEATURES-APPROVED.md](FEATURES-APPROVED.md) lên v1.1, v1.2…

**Lời của khách hàng (2026-11-17):**
* Trả lời bốn quyết định của [ROUND-1-SUMMARY.md](ROUND-1-SUMMARY.md): **"1. A, 2. A, 3. A, 4. A"**
* Khi được hỏi có duyệt toàn bộ bộ tài liệu v0.2 không: **"Duyệt, bắt đầu làm"**

**Quyết định đã chốt (BRD §9):**
* **QĐ-1 = A:** không đọc được nhiệt độ động cơ → robot vẫn chạy; mỗi lần kết nối Station hỏi xác nhận, hiện banner
  cam; phiên không người cầm leader (chạy model, phát lại, quỹ đạo, chương trình) tự dừng sau 10 phút (P-3, AT-93).
* **QĐ-2 = A:** nghiệm thu Windows 10/11 x64 = Must (UAT của khách), Ubuntu 22.04 / 24.04 x86_64 = Should (vendor),
  Docker trên PC Linux x86_64 `-cpu` = Could (vendor); macOS, Raspberry Pi 5, Jetson Orin, wheel arm64, Docker `-cuda`
  = bản xem trước, ngoài nghiệm thu (W-9).
* **QĐ-3 = A:** Windows cài / cập nhật / quay lại bằng một lệnh chép-dán, không cần git, đúng bộ thư viện đã kiểm (P-1,
  ADR-13 chấp nhận).
* **QĐ-4 = A:** Hibiscus CLI phát hành v0.1.2 với giấy phép Apache-2.0; Station ghim lại. Việc phát hành làm trong repo
  nền tảng Hibiscus, ghi là phụ thuộc ngoài **EXT-1 / CR-EXT-1** (BRD §7); nhóm Station không sửa repo khác. Chặn
  AT-98 (F-6, Must) tới khi có v0.1.2.
* Q-2, Q-3, Q-6 – Q-8 và P-1 – P-8 duyệt cùng bộ tài liệu như đề xuất.

**BA đã làm:**
* Mọi tài liệu lên **v1.0, trạng thái đã duyệt**: [BRD.md](BRD.md), [SRS.md](SRS.md), [ARCHITECTURE.md](ARCHITECTURE.md),
  [FEATURES.md](FEATURES.md), [ACCEPTANCE.md](ACCEPTANCE.md), [REGRESSION.md](REGRESSION.md). Bản rà soát (REVIEW-SA,
  REVIEW-TECHLEAD) và ROUND-1-SUMMARY giữ nguyên làm hồ sơ.
* BRD: §9 viết lại thành quyết định đã chốt kèm lời khách; thêm C-5 (nền tảng), EXT-1 (§7), việc còn mở của vendor OI-1 –
  OI-4; RK-1, RK-3, RK-6, RK-7 cập nhật. Không còn câu hỏi mở cho khách về phạm vi / hành vi.
* SRS: FR-1, FR-3, FR-33, FR-69, NFR-6, NFR-9, NFR-14, §5.4, §7, §8 (K-8, K-9) ghi quyết định đã chốt; bỏ "phương án B".
* ACCEPTANCE: AT-1 (bỏ bước phương án B), AT-4 (chỉ PC Linux x86_64 `-cpu`; kiểm nhãn "bản xem trước"), AT-84, AT-93
  (thêm bước 0: mặc định 10 phút), AT-98 (Hibiscus CLI v0.1.2 Apache-2.0), môi trường (nền tảng nghiệm thu), Kế hoạch
  UAT (UAT-0, bước 13).
* FEATURES: F-1 mốc **M0 (P-1) / M1** (khớp bảng Mốc: P-1 / SP-3 ở M0 để khách cài bản M0 ở UAT-0); bảng Mốc: M1 = 43 Must
  + 3 Should (F-2, F-18, F-26), M2 = 19 Should (bỏ F-2 khỏi dòng M2 vì cột mốc của F-2 là M1, theo Tech Lead); "Tech Lead
  vòng 2" → OI-1.
* ARCHITECTURE: ADR-12 (ghim v0.1.2 Apache-2.0), ADR-13 chấp nhận, §3.4 (Pi 5, Jetson, macOS = bản xem trước), bảng
  công nghệ (`hibiscus`).
* Tạo [FEATURES-APPROVED.md](FEATURES-APPROVED.md) v1.0: 71 tính năng (mốc, AT, Dev status = not started, QC result =
  not tested, In release = -), P-1 – P-8, lỗi / khoảng trống theo mốc, số tính năng theo mốc, phạm vi và điều kiện kết
  thúc M0, EXT-1 và OI-1 – OI-4, ma trận truy vết BR → FR / NFR → F → AT → QC result.

**Số tính năng theo mốc (mốc chính):** M0 1 (F-63; thêm phần P-1 của F-1 và D-1 của F-17) · M1 46 · M2 19 · M3 5 (thêm
phần LAN của F-6) · tổng 71 (44 Must / 22 Should / 5 Could).

**Bước tiếp theo:** Tech Lead ước các mục ✚ (OI-1) và bắt đầu M0 trên nhánh tích hợp `release/v1`; khách hẹn UAT-0 khi
có bản M0.
