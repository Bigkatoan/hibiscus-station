# Hibiscus Station: danh sách tính năng đã duyệt v1.1 · khách hàng duyệt ngày 2026-11-17 (v1.0) và 2026-11-19 (CR-1) · baseline: BRD v1.0, SRS v1.1, Architecture v1.1, Features v1.1, Acceptance v1.1, Regression v1.1

**Lời duyệt của khách hàng (2026-11-17):** quyết định **"1. A, 2. A, 3. A, 4. A"**; khi được hỏi có duyệt toàn bộ
bộ tài liệu v0.2 không: **"Duyệt, bắt đầu làm"**. Nhật ký: [CHANGELOG.md](CHANGELOG.md).

**CR-1 (2026-11-19) → v1.1:** khách hỏi xem được video camera của từng tập đã ghi; BA đề xuất "bấm một tập → video mọi
camera, đồng bộ với biểu đồ theo khớp; phát được trên Edge, Chrome, Firefox trên Windows; khoảng 2 – 3 ngày công, trong
M1". **Lời của khách hàng: "Có, thêm vào M1"** → **F-72** (Must, M1).

Danh sách này **đóng băng** từ ngày duyệt. Nhóm dev chỉ xây những mục ở đây (tính năng F-n, đề xuất thay đổi
P-n, lỗi D-n, khoảng trống K-n). Mọi thêm / đổi / bỏ là **yêu cầu thay đổi (CR)**: BA viết, Tech Lead / SA đánh giá,
khách duyệt, danh sách lên v1.1, v1.2… Ý tưởng của nhóm dev gửi BA dưới dạng đề xuất, không đưa thẳng vào mã.

* **Dev status** (Tech Lead cập nhật): `not started` / `in progress` / `done` (Done = mã + test tự động + chạy
  được trên giao diện thật + tài liệu / chuỗi vi và en + giao QC kèm cách kiểm).
* **QC result** (QC cập nhật trên đúng bản cài của mốc): `PASS` / `FAIL` / `not tested` / `NOT VERIFIED (lý do)`.
  PASS = mọi AT của tính năng đạt, **0 lỗi mở ở mọi mức**, NFR liên quan đã đo và đạt.
* **In release**: `-` (chưa quyết) / `yes` / `no (lý do)`. Một FAIL loại tính năng đó **và mọi tính năng phụ
  thuộc nó** (cột Phụ thuộc trong [FEATURES.md](FEATURES.md)). Một Must FAIL chặn cả bản phát hành. Chỉ khách
  hàng miễn được một lỗi, bằng văn bản, theo mã lỗi.
* Mô tả đầy đủ từng tính năng: [FEATURES.md](FEATURES.md) (F-n) và [SRS.md](SRS.md) (FR-n cùng số); bước kiểm:
  [ACCEPTANCE.md](ACCEPTANCE.md); hồi quy: [REGRESSION.md](REGRESSION.md) (REG-1 – REG-27, chạy trên mọi bản ứng viên).

## Quyết định đã chốt

| QĐ | Phương án | Nội dung | Ảnh hưởng |
|---|---|---|---|
| QĐ-1 | A | Không đọc được nhiệt độ động cơ: robot vẫn chạy; mỗi lần kết nối Station hỏi xác nhận và hiện banner cam; phiên không người cầm leader (chạy model, phát lại, quỹ đạo, chương trình) tự dừng sau 10 phút | P-3, FR-33, F-33, AT-93 |
| QĐ-2 | A | Nghiệm thu: Windows 10/11 x64 Must (UAT của khách), Ubuntu 22.04 / 24.04 x86_64 Should (vendor), Docker trên PC Linux x86_64 `-cpu` Could (vendor); macOS, Pi 5, Jetson, wheel arm64, Docker `-cuda` = bản xem trước, ngoài nghiệm thu | NFR-9, F-1 – F-3, W-9, AT-1 – AT-4 |
| QĐ-3 | A | Windows: một lệnh chép-dán, không cần git, cài đúng bộ thư viện đã kiểm; cùng lệnh để cập nhật hoặc quay lại | P-1, ADR-13, FR-1, FR-69, AT-1, AT-84 |
| QĐ-4 | A | Hibiscus CLI phát hành v0.1.2 với giấy phép Apache-2.0; Station ghim lại v0.1.2 | EXT-1, NFR-14, ADR-12, AT-98 |

## Tính năng đã duyệt (72)

| ID | Tính năng | Ưu tiên | Milestone | Acceptance tests | Lỗi / khoảng trống phải đóng | Dev status | QC result | In release |
|---|---|---|---|---|---|---|---|---|
| F-1 | Cài đặt trên Windows 10/11 x64 bằng một lệnh PowerShell (P-1, QĐ-3 = A) | Must | M0 (P-1) / M1 | AT-1, AT-2 | K-8, P-1 (môi trường cài không cố định, SA-P1), K-10 | in progress (phần M0 P-1: mã + test xong, chưa chạy trên Windows thật / CI) | PASS (M0 P-1: QD-1, QD-2, QD-17, QD-18, QD-20 đã đóng; AT-2 PASS; CI Windows PowerShell 5.1 không git PASS; VM Windows 11 sạch NOT VERIFIED (UAT-0); phần M1 not tested; [QC-M0-r10](qc/QC-M0-r10.md)) | - |
| F-2 | Cài đặt trên Ubuntu 22.04 / 24.04 x86_64 (wheel, systemd tuỳ chọn) | Should | M1 | AT-3 | — | not started | not tested | - |
| F-3 | Cài đặt Docker trên PC Linux x86_64, image `-cpu` | Could | M3 | AT-4 | D-18 (= K-1) | not started | not tested | - |
| F-4 | Khởi động `hibiscus-station` | Must | M1 | AT-5, AT-6, AT-87, AT-95 | D-3, D-4, D-19 | not started | not tested | - |
| F-5 | Chế độ demo `--mock` | Must | M1 | AT-7 | D-8 | not started | not tested | - |
| F-6 | Truy cập cục bộ an toàn (chế độ LAN: Could) | Must (LAN: Could) | M1 (LAN: M3) | AT-8, AT-9 (LAN: mạng cô lập, FL-8), AT-98 | — | not started | not tested | - |
| F-7 | Trang Chào mừng và thanh bước | Must | M1 | AT-10 | D-5, D-25 | in progress (D-25: mã + test xong trên `m1/field-029`, chờ QC) | not tested | - |
| F-8 | Hồ sơ robot | Must | M1 | AT-11 | D-26 | in progress (D-26 xoá hồ sơ: done, hotfix 0.2.10; phần còn lại của F-8 not started) | not tested (D-26: PASS trên 0.2.10, [QC-0210-r4](qc/QC-0210-r4.md)) | - |
| F-9 | Danh sách cổng USB serial | Must | M1 | AT-12 | — | not started | not tested | - |
| F-10 | Tìm cổng theo vai trò | Must | M1 | AT-13, AT-14 | — | not started | not tested | - |
| F-11 | Dò cổng chỉ-đọc | Must | M1 | AT-15 | — | not started | not tested | - |
| F-12 | Kết nối / ngắt kết nối hồ sơ | Must | M1 | AT-16, AT-17, AT-96 | D-22 | not started | not tested | - |
| F-13 | Mất thiết bị USB | Must | M1 | AT-18, AT-19, AT-94 | K-2 (tài liệu UAT ghi `bus_lost`) | not started | not tested | - |
| F-14 | Mô-men follower | Must | M1 | AT-20 | — | not started | not tested | - |
| F-15 | Bảo vệ khỏi hồ sơ demo | Must | M1 | AT-21 | — | not started | not tested | - |
| F-16 | Kiểm tra hiệu chỉnh khi vào trang | Must | M1 | AT-22 | — | not started | not tested | - |
| F-17 | Luồng hiệu chỉnh có hướng dẫn | Must | M0 (D-1) / M1 | AT-23, AT-24 | D-1, D-17, K-2 | in progress (phần M0 D-1 done; phần M1 chưa làm) | PASS (M0 D-1, QD-3 đã đóng; phần M1 not tested; [QC-M0-r10](qc/QC-M0-r10.md)) | - |
| F-18 | Nâng cao: các tệp hiệu chỉnh | Should | M1 | AT-25 | — | not started | not tested | - |
| F-19 | Kiểm tra hai tay | Must | M1 | AT-26 | D-7 | not started | not tested | - |
| F-20 | Tệp hiệu chỉnh dùng chung hai chiều với lerobot và LeLab | Must | M1 | AT-27 | — | not started | not tested | - |
| F-21 | Tìm camera | Must | M1 | AT-28 | — | not started | not tested | - |
| F-22 | Camera đã cấu hình | Must | M1 | AT-29 | D-10 | not started | not tested | - |
| F-23 | Camera đứng hình / mất trong phiên | Must | M1 | AT-30 | — | not started | not tested | - |
| F-24 | Teleop leader → follower | Must | M1 | AT-31, AT-32, AT-89, AT-90 | D-9, D-10, D-11 | not started | not tested | - |
| F-25 | Leader lệch xa | Must | M1 | AT-33 | D-5 | not started | not tested | - |
| F-26 | Cảnh báo "tay follower không theo kịp" | Should | M1 | AT-34 | — | not started | not tested | - |
| F-27 | Phát lại một tập đã ghi lên follower | Should | M2 | AT-35 | — | not started | not tested | - |
| F-28 | E-stop | Must | M1 | AT-36, AT-37, AT-88, AT-94 | D-6, D-13 | not started | not tested | - |
| F-29 | Dead-man | Must | M1 | AT-38 | — | not started | not tested | - |
| F-30 | Giới hạn an toàn | Must | M1 | AT-39 | K-5 | not started | not tested | - |
| F-31 | Sức khoẻ động cơ | Must | M1 | AT-40, AT-41 | REG-13 (K-9) | not started | not tested | - |
| F-32 | Ngưỡng nhiệt và dừng an toàn nhiệt | Must | M1 | AT-42 | — | not started | not tested | - |
| F-33 | Quy tắc số đo hợp lý | Must | M1 | AT-43, AT-93 | REG-13 (K-9) | not started | not tested | - |
| F-34 | Dừng vì điện | Must | M1 | AT-44 | — | not started | not tested | - |
| F-35 | Phục hồi sau khi dừng giữa chừng ("Về tư thế nghỉ", chạy lại từ đầu) | Must | M1 | AT-45 | — | not started | not tested | - |
| F-36 | Thông báo | Must | M1 | AT-46 | — | not started | not tested | - |
| F-37 | Trang Phiên | Should | M2 | AT-47 | — | not started | not tested | - |
| F-38 | Ghi dataset LeRobot v3 | Must | M1 | AT-48, AT-49 | D-2, D-19 (tập đang ghi khi đóng cửa sổ) | in progress (D-2: done, hotfix 0.2.10; D-19 not started) | not tested (D-2: PASS trên 0.2.10, [QC-0210-r1](qc/QC-0210-r1.md) – [r4](qc/QC-0210-r4.md)) | - |
| F-39 | Ghi thêm vào dataset có sẵn | Should | M2 | AT-50 | — | not started | not tested | - |
| F-40 | Trang Bộ dữ liệu | Must | M1 | AT-51 | D-2 | in progress (D-2: done, hotfix 0.2.10) | not tested (D-2: PASS trên 0.2.10, [QC-0210-r1](qc/QC-0210-r1.md) – [r4](qc/QC-0210-r4.md); AT-51 đầy đủ chạy lại ở M1) | - |
| F-41 | Ghép nối máy chủ Hibiscus | Should | M2 | AT-52 | D-25 (sửa ở M1) | in progress (D-25: mã + test xong trên `m1/field-029`, chờ QC) | not tested | - |
| F-42 | Tải dataset lên | Should | M2 | AT-53, AT-54 | — | not started | not tested | - |
| F-43 | Trang Huấn luyện | Should | M2 | AT-55 | — | not started | not tested | - |
| F-44 | Kéo model từ máy chủ | Should | M2 | AT-56 | — | not started | not tested | - |
| F-45 | Nhập model | Must | M1 | AT-57 | D-16 | not started | not tested | - |
| F-46 | Kiểm tra tương thích model ↔ robot | Must | M1 | AT-58 | — | not started | not tested | - |
| F-47 | Nạp model | Must | M1 | AT-59, AT-97 | D-23 | not started | not tested | - |
| F-48 | Chạy model trên robot | Must | M1 | AT-60, AT-61, AT-97 | D-20 | not started | not tested | - |
| F-49 | Ghi dataset đánh giá `eval_…` khi chạy model | Should | M2 | AT-62 | — | not started | not tested | - |
| F-50 | Tóm tắt sau lượt chạy | Should | M2 | AT-63 | — | not started | not tested | - |
| F-51 | Trang Model | Should | M2 | AT-64 | — | not started | not tested | - |
| F-52 | Ghi quỹ đạo bằng tay leader | Should | M2 | AT-65 | — | not started | not tested | - |
| F-53 | Phát quỹ đạo (10–100 %, "Cần kiểm tra" sau hiệu chỉnh lại) | Should | M2 | AT-66, AT-67 | D-12 | not started | not tested | - |
| F-54 | Tư thế có tên | Should | M2 | AT-68 | — | not started | not tested | - |
| F-55 | Bộ nhận diện camera | Should | M2 | AT-69 | — | not started | not tested | - |
| F-56 | Trình soạn chương trình khối | Should | M2 | AT-70 | D-24 (sửa ở M1) | in progress (D-24: mã + test xong trên `m1/field-029`, chờ QC) | not tested | - |
| F-57 | Chạy thử chương trình (dry run) trên tay giả lập | Should | M2 | AT-71 | — | not started | not tested | - |
| F-58 | Chạy chương trình trên robot | Should | M2 | AT-72 | D-24 (sửa ở M1) | in progress (D-24: mã + test xong trên `m1/field-029`, chờ QC) | not tested | - |
| F-59 | Tín hiệu ngoài | Could | M3 | AT-73 | — | not started | not tested | - |
| F-60 | Khối "chạy mô hình" trong chương trình | Could | M3 | AT-74 | — | not started | not tested | - |
| F-61 | Robot 3D | Should | M2 | AT-75 | — | not started | not tested | - |
| F-62 | Xem trước quỹ đạo bằng tay mờ | Should | M2 | AT-76 | — | not started | not tested | - |
| F-63 | `hibiscus-station doctor` (báo cáo chẩn đoán) | Must | M0 | AT-77 | D-15, D-21, K-11 | done (M0; chờ QC) | FAIL (QD-32: một gói hỏng lạc (nhiễu) trong lúc hỏi servo mất điện làm nó thành "answers only with corrupted packets", mất "do not answer (power? cable?)", dù dump thô cùng báo cáo ghi "no answer"; QD-33: một lần khựng USB từ 350 ms lúc ping (700 ms lúc quét) làm servo trả lời mọi lệnh bị gọi "answer only now and then" + lời khuyên kiểm cáp / nguồn; QD-34: bộ chuyển chậm đều 49 ms bị kết luận "unreliable bus … check the 3-pin cables" cạnh "slow bus"; mọi bước AT-77 [Vendor] đạt trên bản cài; 0 giá trị thanh ghi sai, 0 lệnh ghi ở 1 609 lượt lưới lỗi; QD-4, QD-7, QD-10 – QD-14, QD-16, QD-18, QD-19, QD-21 – QD-31 đã đóng; VID:PID / WCH thật NOT VERIFIED (UAT-0); [QC-M0-r10](qc/QC-M0-r10.md)) | - |
| F-64 | Nhật ký `station.log` | Must | M1 | AT-78 | — | not started | not tested | - |
| F-65 | `hibiscus-station health` | Could | M3 | AT-79 | — | not started | not tested | - |
| F-66 | Trang Cài đặt | Must | M1 | AT-80 | D-5 | not started | not tested | - |
| F-67 | Song ngữ Tiếng Việt / English | Must | M1 | AT-81, AT-91 | D-5 (= K-4), D-12 (= K-3) | not started | not tested | - |
| F-68 | Giao diện pixel Hibiscus ngày / đêm | Must | M1 | AT-82, AT-83 | D-13, D-14 | not started | not tested | - |
| F-69 | Cập nhật bản wheel | Must | M1 | AT-84 | K-8, D-18 (= K-6), P-1 | not started | not tested | - |
| F-70 | Docker: backup / restore / update / rollback | Could | M3 | AT-85 | — | not started | not tested | - |
| F-71 | Dữ liệu tách bạch và bền | Must | M1 | AT-86 | — | not started | not tested | - |
| F-72 | Xem video từng tập trong Bộ dữ liệu (CR-1, v1.1) | Must | M1 | AT-99 | REG-27 (AV1 không phát trên Edge Windows cài sẵn); QC F072 r1: QV-1 (chặn), QV-2, QV-5, QV-6, QV-9 (Lead nâng lên, sửa cùng vòng); **backlog M1:** QV-3 (`video_path` sai mẫu → 500), QV-4 (mp4 gốc cụt: `source` thiếu khung vẫn 200), QV-7 (Range sai cú pháp → 400), QV-8 (chuyển đổi lỗi không được ghi nhớ) | in progress (bản sửa QC r1: QV-1, QV-2, QV-5, QV-6, QV-9 trên `m1/episode-video`, chờ QC r2; Edge thật trên Windows 11 cài sẵn: NOT VERIFIED tới UAT-1) | FAIL r1 ([QC-F072-r1](qc/QC-F072-r1.md): QV-1) | - |

## Đề xuất thay đổi đã duyệt (P-1 – P-8)

Sửa lỗi / đóng gói để đạt chuẩn, không phải tính năng mới; mô tả đầy đủ ở [FEATURES.md](FEATURES.md) (mục "Đề xuất thay đổi").

| P | Thay đổi | Tính năng | Milestone | AT | Dev status | QC result |
|---|---|---|---|---|---|---|
| P-1 | Lệnh cài / cập nhật / quay lại một dòng PowerShell, phụ thuộc cố định, không cần git (QĐ-3 = A) | F-1, F-69 | M0 (cài, SP-3) / M1 (cập nhật, quay lại) | AT-1, AT-84 | in progress (cài: mã + test + dry run PowerShell 7 trên Linux; chưa chạy trên Windows PowerShell 5.1 / VM sạch) | PASS (cài, M0: QD-1, QD-2, QD-17, QD-18, QD-20 đã đóng; AT-2 PASS; VM Windows 11 sạch NOT VERIFIED (UAT-0); cập nhật / quay lại (M1) not tested; [QC-M0-r10](qc/QC-M0-r10.md)) |
| P-2 | Từ chối chạy model khi suy luận khởi động > 500 ms | F-47, F-48 | M1 | AT-97 | not started | not tested |
| P-3 | Không đọc được nhiệt độ: xác nhận mỗi lần kết nối, banner cam, dừng sau 10 phút khi không cầm leader (QĐ-1 = A) | F-33 | M1 | AT-93 | not started | not tested |
| P-4 | Demo: tay leader giả đứng theo follower khi bắt đầu phiên và khi Kiểm tra | F-5 | M1 | AT-7 | not started | not tested |
| P-5 | Chỉ hiện câu dịch; lý do thô trong "Chi tiết kỹ thuật" thu gọn | F-7 | M1 | AT-10 | not started | not tested |
| P-6 | Windows: đóng cửa sổ / đăng xuất / tắt máy → dừng rút gọn ≤ 4 s | F-4 | M1 | AT-95 | not started | not tested |
| P-7 | Linux: kiểm tiến trình khác giữ cổng trước khi mở → `port_busy` | F-12 | M1 | AT-96 | not started | not tested |
| P-8 | Nếu SP-1 không xác nhận đơn vị dòng: hiện dòng là "—" | F-31 | M1 | AT-40 | not started | not tested |

## Lỗi và khoảng trống phải đóng

Chi tiết và bước tái hiện: [FEATURES.md](FEATURES.md#lỗi-đã-biết-d-n), [REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md) §4,
[SRS.md](SRS.md) §8. Một lỗi chỉ đóng khi bản sửa có test fail-trước-pass-sau, QC chạy lại AT của tính năng trên
bản mới và danh sách hồi quy vẫn đạt.

| Mốc | Lỗi D-n | Khoảng trống K-n / REG |
|---|---|---|
| M0 | D-1 (High), D-15, D-21 | K-11 |
| M1 | D-2 – D-11, D-12 (phần M1), D-13, D-14, D-16 – D-20, D-22, D-23 (D-9 sau số đo UAT-0), D-24, D-25 (báo cáo hiện trường của khách check_ver_2.9, 2026-11-18), D-26 (báo cáo của khách 2026-11-20; D-2 và D-26 đã sửa trong hotfix 0.2.10) | K-2, K-3 (= D-12), K-4 (= D-5), K-5, K-8 (P-1), K-10, REG-13 / K-9 (sau UAT-0, QĐ-1 = A) |
| M2 | D-12 (phần F-53) | — |
| M3 | — (D-18 của F-3 là tài liệu, đóng ở M1) | — |

25 lỗi trong baseline: 3 High (D-1, D-9, D-19) · 10 Medium · 12 Low · 0 Critical; thêm D-24, D-25 (hiện trường 0.2.9) và
D-26 (hotfix 0.2.10). K-1, K-6 = D-18; K-7 (spec dev lỗi thời) SA cập nhật cùng
OI-3. Trạng thái mọi lỗi hôm nay: **mở**.

**Dev status M0 (2026-11-17, nhánh `release/v1`):** D-1, D-15, D-21, K-11 có bản sửa kèm test fail-trước-pass-sau
(D-1: e2e Playwright của repo xanh lại; D-15, D-21, K-11: `tests/test_doctor.py`). Lỗi vẫn **mở** đến khi QC chạy lại
AT-77 / AT-2 trên bản pre-release M0. Nền kiểm: NFR-18 (danh sách bỏ qua theo nền tảng), FL-7 (ma trận ảnh + axe,
các phát hiện ghi làm lỗi M1 trong `tests/e2e/screen_matrix_known.json`), FL-12 (dry run cục bộ) xong ở máy dev;
CI Linux / Windows / macOS, e2e `windows-latest`, SP-2, SP-3 **chưa chạy** (nhánh chưa đẩy lên GitHub).

**Lỗi hiện trường 0.2.9 (2026-11-18, nguồn: báo cáo hiện trường của khách check_ver_2.9 (2026-11-18)).** Khách đã quyết định cách sửa; hai lỗi vào M1:

| D | Mức | Tính năng | Lỗi | Quyết định của khách | Hồi quy |
|---|---|---|---|---|---|
| D-24 | Low | F-56, F-58 | Cảnh báo "chuyển động đầu tiên bắt đầu xa tư thế của tay" tính một lần, nằm mãi trên khối sau khi chạy xong | **"Đổi thành thông tin, tự cập nhật"**: mức `info` mới (không phải cảnh báo, không đếm, không hỏi xác nhận), câu "Tay sẽ đi chậm về điểm bắt đầu của chuyển động này (cách X°)", kiểm lại khi tay di chuyển và khi chạy xong, biến mất khi tay trong ngưỡng | REG-21 |
| D-25 | Medium | F-7, F-41 | Bước Huấn luyện hiện "Bước này đang bị khoá" khi chưa ghép nối dù form ghép nối dùng được; form nhận liên kết OneDrive | **"Không cần robot, nói rõ hơn"**: không khoá, câu trung tính "Kết nối máy chủ Hibiscus để huấn luyện (không cần robot)."; form kiểm địa chỉ (http(s), không phải OneDrive / SharePoint / Google Drive / Dropbox), lỗi ngay dưới ô, nút Ghép nối tắt tới khi hợp lệ | REG-22 |

**Dev status D-24, D-25 (2026-11-18, nhánh `m1/field-029` từ `release/v1` `ae7d680`):** bản sửa kèm test
fail-trước-pass-sau (`tests/test_field_029.py`, `web/src/station/field029.screens.test.tsx`, `station.unit.test.ts`).
Bước Tải lên vẫn khoá "Hãy ghi một bộ dữ liệu trước" (cần dataset đã ghi, tức là cần robot); bước Huấn luyện là bước duy
nhất chỉ cần máy chủ. Lỗi vẫn **mở** đến khi QC chạy lại AT-10, AT-52, AT-70, AT-72 và REG-21, REG-22 trên bản cài.

**QC F029 lần 1 ([QC-F029-r1](qc/QC-F029-r1.md), `deea10b`): D-24 FAIL (QD-36 Low), D-25 FAIL (QD-35 Medium).** Bản sửa
lần 2 trên `m1/field-029` (test fail-trước-pass-sau, chờ QC lần 2):
* **QD-35:** kiểm liên kết chia sẻ tệp theo họ tên miền (mọi tên miền con của `cloud.microsoft`, `officeapps.live.com`,
  `office.com`, `office365.com`, `sharepoint.com`, OneDrive / `*.live.com` có onedrive, `1drv.ms`, Google Drive / Docs,
  `googleusercontent.com`, Dropbox, Box, WeTransfer, iCloud…) cộng quy tắc chung (tham số `docId`, `driveId`, `resid`,
  `authkey`…; đường dẫn `/open/onedrive`, `/:w:/`, `/file/d/`…; tên tệp tài liệu). Cùng bộ quy tắc ở giao diện và ở
  Station: `POST /server/pair` từ chối trước khi gửi gì đi, mã `server_url_file_share` / `server_url_invalid` (422, câu
  EN / VI). Bộ ca chung `tests/server_urls.json`, có đúng liên kết kiểu khách `word.cloud.microsoft/open/onedrive/?docId=…&driveId=…`.
* **QD-36:** khi robot ngắt kết nối hoặc luồng khớp cũ quá 2,5 s, dòng thông tin mất ngay và trình soạn kiểm lại; kết nối
  lại thì dòng hiện lại.
* **Ghi nhận của QC (sửa luôn):** Ghi chú nằm trong khung riêng có tiêu đề "Ghi chú" / "Notes", viền và màu info; vấn đề
  dùng biểu tượng riêng theo mức (lỗi: tam giác đỏ, cảnh báo: tam giác cam, cần xác nhận: dấu hỏi), có nhãn đọc màn hình.

**QC F029 lần 2 ([QC-F029-r2](qc/QC-F029-r2.md), `b74a735`): QD-35, QD-36 PASS; D-24 FAIL (QD-37, QD-38 Low), D-25 FAIL
(QD-40 Medium, QD-39, QD-41 Low).** Quyết định của Lead: không chạy theo danh sách chặn (không bao giờ đủ, QD-40, và
đã chặn nhầm, QD-41). Bản sửa lần 3 trên `m1/field-029` (test fail-trước-pass-sau, chờ QC lần 3):
* **QD-40 (thiết kế):** Station không bao giờ gửi token tới một máy chưa chứng minh là máy chủ Hibiscus. Trước token,
  `POST /server/pair` hỏi `GET <địa chỉ>/api/v1/auth/config` (cấu hình đăng nhập công khai của máy chủ đã phát hành,
  không cần đăng nhập): không theo chuyển hướng, chờ tối đa 5 s, phải là `application/json` đúng dạng `AuthConfig`.
  Không đạt → 422 `server_not_hibiscus` ("Địa chỉ này không phản hồi như một máy chủ Hibiscus…"), token chưa gửi đi.
  Test với máy chủ cục bộ thật: trang web thường, JSON khác, sai content-type, 404, chuyển hướng sang máy khác, quá
  giờ, máy giống Hibiscus; và các trang chia sẻ (kiểu `*.usercontent…`, fshare, terabox, sites.google, Box): 0 request
  mang token.
* **QD-41:** danh sách liên kết chia sẻ chỉ còn là gợi ý sớm cho các họ khách đã nêu (OneDrive / SharePoint / Office /
  `cloud.microsoft` / Teams / `d.docs.live.net`, Google Drive / Docs / usercontent, Dropbox), có gỡ Safe Links và
  `google.com/url`. Bỏ quy tắc chung (`cid`, đuôi tệp, tham số / đường dẫn trên tên miền bất kỳ): `?cid=campaign1`,
  `/robots.txt` không còn bị chặn nhầm.
* **QD-37:** mỗi mức có huy hiệu riêng, khác cả hình lẫn màu: lỗi = ô đỏ dấu X, cảnh báo = ô vàng hổ phách hình tam
  giác, cần xác nhận = ô tím dấu hỏi; chữ trên nền ≥ 4,5:1 ở sáng và tối (token `sev-*`, kiểm trong `pixelTheme.test.ts`).
* **QD-38:** tư thế đổi từ "không biết" sang "biết" (kết nối lại, kể cả trong 0,2 s) thì luôn kiểm lại, không cần tay
  di chuyển.
* **QD-39:** lỗi có câu dịch thì chỉ hiện câu dịch; chi tiết tiếng Anh của Station nằm trong "Chi tiết kỹ thuật" thu
  gọn (FR-73, P-5), kể cả lỗi token sai định dạng; lỗi không có câu dịch vẫn hiện chi tiết.

**QC F029 lần 3 ([QC-F029-r3](qc/QC-F029-r3.md), `dc07cdc`): D-24 PASS; QD-37 – QD-41 PASS, không rò token; D-25 FAIL
(QD-44 Medium; QD-42, QD-43, QD-45 Low).** Bản sửa lần 4 trên `m1/field-029` (test fail-trước-pass-sau, chờ QC lần 4):
* **QD-44:** ghép nối trả mã riêng cho từng lý do, có câu EN / VI: `server_unauthorized` (máy chủ trả 401 / 403),
  `token_format_invalid`, `token_missing_scope`, `workspace_required`, `server_url_insecure`. Giao diện chỉ thu gọn chi
  tiết với các mã mà câu dịch đã nói đủ (danh sách `SELF_EXPLAINING`); mọi mã khác, trước hết `validation_failed` chung
  (52 chỗ ở Station, mỗi chỗ một lý do), hiện chi tiết ngay như trước QD-39.
* **QD-42:** bước dò có một hạn chót 5 s cho cả trao đổi (kết nối, tiêu đề, nội dung; `asyncio.wait_for`), test với máy
  chủ nhỏ giọt 1 byte / 3 s ở phần nội dung và ở phần tiêu đề.
* **QD-43:** kiểm danh tính theo sự có mặt và kiểu của các trường chính; `supported_locales` là danh sách có "vi" hoặc
  "en" (cho phép ngôn ngữ khác, ví dụ `["vi","en","ja"]`); không đòi giá trị cố định.
* **QD-45:** `http://` chỉ cho localhost, địa chỉ loopback / mạng riêng (RFC 1918, ULA) / link-local / CGNAT 100.64/10,
  `*.local`, `*.lan` và tên một nhãn; máy chủ công khai qua `http://` → `server_url_insecure` ("Hãy dùng địa chỉ
  https:// …") ở form và ở Station, trước mọi request; cùng bảng ca `tests/server_urls.json`. (Chuyển hướng HTTP → HTTPS
  của máy chủ prod là việc hạ tầng, không thuộc nhánh này.)

**Hotfix 0.2.10 (2026-11-20, `hotfix/0.2.10` → tag `v0.2.10`, main `d8c5356`; gộp vào `release/v1` qua nhánh
`m1/merge-0210`).** Nguồn: báo cáo hiện trường của khách trên 0.2.9 (Windows, SO-101, 2026-11-19: "Tôi không xem được
video và các tập đã ghi") và báo cáo 2026-11-20 (hồ sơ trùng "so-101-1" / "SO_101" trên COM8 / COM7 không xoá được).

| D | Mức | Tính năng | Lỗi | Bản sửa | Dev status | QC | Hồi quy |
|---|---|---|---|---|---|---|---|
| D-2 | Medium | F-38, F-40 | Trang Ghi / chi tiết dataset gây `500 internal_error` khi đọc tập đang lưu dở; trang Bộ dữ liệu không hiện tập nào trong khi ghi; dataset bỏ dở khi Station tắt giữa phiên làm hỏng trang mãi | Mỗi dòng `episode_list[]` có `state` = `saved` / `saving` / `unreadable`; sổ đăng ký tập đang ghi của recorder; `meta/episodes` chỉ đọc khi tệp có footer; trang dataset có error element (không trang trắng); ghi thêm vào dataset bỏ dở hoặc không nhất quán → 409 `dataset_not_finalized` / `dataset_unreadable`, lỗi tệp → 409 `dataset_io_error`, không đổi tệp nào; một bộ kiểm `meta/info.json` chung (`hibiscus_station/data/info.py`: `info_problems`, `consistency_problems`) cho danh sách, chi tiết, ghi thêm, phát lại | **done** (hotfix 0.2.10) | **PASS** ([QC-0210-r1](qc/QC-0210-r1.md) FAIL QH-1, QH-2; [r2](qc/QC-0210-r2.md) FAIL QH-7, QH-8; [r3](qc/QC-0210-r3.md) FAIL QH-9; [r4](qc/QC-0210-r4.md) PASS) | REG-23, REG-24, REG-25 |
| D-26 | Medium | F-8 | Không xoá được hồ sơ robot (F-8 đã duyệt "tạo / sửa / xoá") | Nút Xoá / Delete trên thẻ hồ sơ, hộp xác nhận nêu tên và nói tệp hiệu chỉnh, dataset không bị xoá; 409 `busy` khi robot đó đang kết nối / hiệu chỉnh / trong phiên / chờ USB; xoá hồ sơ đang dùng trên tay thật không làm hồ sơ demo thành active | **done** (hotfix 0.2.10) | **PASS** ([QC-0210-r1](qc/QC-0210-r1.md) – [r4](qc/QC-0210-r4.md)) | REG-26 |

Test tự động: `tests/test_field_0210.py`, `tests/test_info_fuzz.py` (825 biến đổi `meta/info.json`, 0 lỗi 5xx),
`tests/test_robot_delete.py`, `web/src/station/field0210.screens.test.tsx`, `web/src/station/robotdelete.screens.test.tsx`.
Việc còn lại (Low, không chặn, vào M1): ~~QH-6 (test dead-man trên Windows CI đôi khi quá 1,5 s)~~ đã đóng ở `m1/ci-timing` (mục bên dưới), M1-4 (danh sách Bộ
dữ liệu chậm hơn 0.2.9 khoảng 9 lần vì kiểm nhất quán: cache theo mtime hoặc chuyển khỏi danh sách), M1-5 (thẻ ghi thêm
cho dataset không nhất quán dùng câu chung "tệp bị hỏng"; lý do chính xác chỉ có trong `reasons` của API), O-1 (tập của
dataset bỏ dở do sập không xem lại được: 0.2.10 hiện rõ và an toàn nhưng không khôi phục; liên quan D-19).

Khi gộp vào `release/v1`, hai mã mới `dataset_unreadable`, `dataset_io_error` vào danh sách `SELF_EXPLAINING`
(QD-44: câu dịch đã nói đủ, chi tiết tiếng Anh vào "Chi tiết kỹ thuật"); `dataset_not_finalized` giữ chi tiết trong tầm
mắt (câu chung không nói tệp nào còn mở). Gộp kèm cả hotfix 0.2.9 (QD-1 – QD-27 của 0.2.9, CR-1, CR-2), vốn chưa có trên
`release/v1`; test của hotfix 0.2.9 đổi tên thành `tests/test_hotfix_029.py` và `web/src/station/hotfix029.screens.test.tsx`
vì `test_field_029.py` trên `release/v1` là test của D-24, D-25.

**CI timing (M1, nhánh `m1/ci-timing`, 2026-11-20).** CI phải xanh thật: không chạy lại job lỗi. Các test thời gian
hay lỗi trên runner chậm (VM macOS, Windows) được làm cho xác định; yêu cầu sản phẩm giữ nguyên, không nới dung sai,
không skip / xfail, không thêm vào `tools/ci/allowed-skips.toml`.

| Mã | Test | Nguyên nhân | Sửa | Sản phẩm đổi? |
|---|---|---|---|---|
| **QD-34** (đóng, dev; QC kiểm lại) | `test_doctor.py::test_the_bus_speed_is_measured_only_from_answers_to_their_own_request`, `::test_a_steadily_slow_adapter_is_a_slow_bus_not_loose_cables`; test mới `::test_a_steady_adapter_near_the_first_wait_is_a_slow_bus_not_loose_cables` | (1) Lỗi thật: `bus_verdict()` ở nhánh không có servo im tính lần sync read mà mọi câu trả lời chỉ trễ do bộ chuyển chậm đều là "reads failed … check the 3-pin cables" (giả lập có thời gian dây thật: bộ chuyển đường ống 47,5 – 49,5 ms, tái hiện xác định). (2) Test: giả lập loopback và probe dùng đồng hồ thật; VM khựng tiến trình 80 – 600 ms nên câu trả lời của bộ chuyển 50 ms "trễ tới 130 ms" → "unreliable bus" | (1) `doctor.py`: lần đọc chỉ có câu trả lời trễ của bộ chuyển chậm đều (`steady_slow`) không còn là lỗi bus, như nhánh có servo im đã làm. (2) `tests/test_doctor.py`: cổng loopback chạy trên **thời gian giả lập** (`EmulatedClock` thay `time` của `hw/probe.py`; độ trễ bộ chuyển, timeout đọc serial đều theo đồng hồ này): kết luận chỉ phụ thuộc độ trễ test đặt. Test mới quét 44 – 53 ms (bước 0,5 ms) với thời gian dây thật | **Có** (`doctor.py`) |
| NFR-2 (lỗi sản phẩm, không có mã QC) | `test_owner.py::test_teleop_timing_ownership_and_telemetry` | Lỗi thật: nhịp cố định đo hạn chót từ lúc tick *bắt đầu*, nên độ trễ đánh thức của OS cộng dồn mỗi tick: vòng 30 Hz chạy 28,8 Hz khi máy tải nặng (Linux, 0 overrun), ~26 Hz trên VM macOS (79 tick / 3 s). Ảnh hưởng ghi dữ liệu và chạy model ở nhịp cố định | `hw/owner.py` `_tick_deadline()`: tick kết thúc trên lưới `t0 + k·T` của phiên; tick trễ cả một chu kỳ (overrun, máy khựng) bắt đầu lưới mới, không chạy bù. Test đo bằng dấu thời gian tick của chính vòng lặp: chờ 90 tick, p95 thời gian tick ≤ 36 ms (NFR-2b), khoảng cách tick trung bình = 1/30 s ± 2 % (bỏ khoảng > 1,5 chu kỳ = máy khựng), telemetry ≤ 1 lần / tick và theo thời gian của vòng | **Có** (`hw/owner.py`) |
| **QH-6** (đóng) | `test_programs_safety.py::test_deadman_loss_while_the_program_waits` | Test đo bằng đồng hồ của luồng test (1,61 s > 1,5 s trên Windows): luồng test thức muộn, không nói gì về vòng lặp | `Watchdog` có sẵn tham số `clock`: test dùng `ManualClock` và bước đồng hồ: không e-stop ở `timeout − 1 ms` (sau 10 tick), e-stop "ui_lost" ở tick đầu tiên sau `timeout + 1 ms` (≤ 1 tick, đếm bằng số tick do chính luồng owner ghi). Đúng NFR-4 "≤ 1,0 s + 1 nhịp" | Không |
| NFR-3a | `test_programs_safety.py::test_estop_during_run_model` (và cùng mẫu: `test_estop_during_the_approach_aborts_the_program`, `test_owner.py::test_estop_freezes_within_one_tick_then_relaxes`, `test_traj_sessions.py::test_estop_mid_replay_stops_within_one_tick`, `test_program_session.py::test_estop_aborts_the_program_within_one_tick`, `test_teleop_lean.py::test_estop_in_the_lean_loop_freezes_within_one_tick`, `test_programs_api.py::test_red_blue_cube_program_end_to_end`, `test_field_028.py::test_align_honours_the_estop`) | Điều kiện "mọi lệnh ghi trong 1 tick + 50 ms tính từ lúc luồng test bấm" theo đồng hồ tường: máy tải nặng làm hỏng dù vòng dừng đúng | Một hàm chung `conftest.press_estop_frozen_within_one_tick()` đo đúng cách NFR-3a ghi: đếm lệnh ghi vị trí lên bus sau khi bấm (≤ 2: lệnh giữ + tick đang chạy) và số tick tới `estopped` (≤ 1, do luồng owner tự ghi) | Không |
| — | `test_sessions.py::test_record_timeout_discard_and_sidecar_line_count` | Test ngủ 0,3 s rồi bấm "next"; Windows chậm không có lần đọc telemetry nào trong 0,3 s nên sidecar rỗng (đúng); chờ pha `reset` 0,2 s bằng thăm dò cũng có thể lỡ | Chờ trạng thái sản phẩm: bộ đếm `discarded == 1`, rồi bộ đệm telemetry của tập có ≥ 2 dòng; sidecar có ≥ 2 dòng, mỗi lần đọc một dòng | Không |
| — | `test_traj_sessions.py`: `test_trim_rename_delete_through_the_api` (macOS: 0,601 so với 0,657 ± 0,05), `test_record_a_and_b_with_the_leader` (1,5 ± 0,3 s; B 0,8 ± 0,15 s) | Thời lượng so với giây của luồng test; cắt (trim) theo lưới mẫu nên một tick khựng cạnh điểm cắt dịch thời lượng | Thời lượng kiểm bằng thời điểm mẫu của chính take: ghi tới khi đủ 46 mẫu (1,5 s ở 30 fps); `raw_duration_s` = khoảng mẫu, không bao giờ nhanh hơn fps; B dừng ở tick đầu tiên ≥ 0,8 s; trim giữ mẫu từ +0,2 s tới −0,1 s và thời lượng = khoảng của các mẫu đó | Không |
| — | `test_program_session.py::test_run_model_block_uses_the_inferring_path` (1,686 s so với 0,6 ± 0,3 s) | `run model for 0.6 s` là một tập `RunSession`: kết thúc sau `round(0,6 × fps)` tick, như mọi tập (tập ghi là số khung). Máy tải nặng làm suy luận CPU overrun tick nên kéo dài thời gian tường | Kiểm đúng 18 tick của tập và thời lượng không ngắn hơn số tick ở fps của phiên; câu lệnh có `timeout_s` 60 rõ ràng (thời hạn tự động "dự kiến + 5 s" theo giờ tường dành cho chuyển động bị treo; máy chạy thử bị bỏ đói CPU trông giống vậy: 1 / 200 lượt dưới tải) | Không |
| — | `test_field_028.py::test_programs_list_never_waits_for_the_hardware_owner` (macOS: 1,14 s so với 1,0 s) | Bấm giờ yêu cầu bằng đồng hồ của test trong lúc owner bận 3 s cố định | Owner bị giữ bận cho tới khi cả GET và PUT đã trả lời; kiểm hai yêu cầu trả lời 200 **trong khi** owner vẫn bận (yêu cầu nào đi qua owner chỉ trả lời được sau khi owner được thả) | Không |
| — | `test_hotfix_029.py::test_a_camera_slower_than_configured_never_reads_as_stale` (Windows: 1 tick "stale", đo 9,3 fps của 12) | Luồng tạo khung của camera giả lập chạy theo bộ lập lịch của máy: runner Windows bỏ đói nó hơn 250 ms, khung cũ 250 ms thật và sản phẩm báo "stale" là đúng | Camera của test giao đúng 12 khung / giây theo đồng hồ của chính nó (khung mới nhất luôn là khung của bước 1/12 s gần nhất, không bao giờ cũ hơn 83 ms); test vẫn hỏng nếu quy tắc "tươi" quay lại 2 chu kỳ ở 30 fps | Không |

Bằng chứng (chạy 200 lần dưới tải CPU, 3 lượt CI `workflow_dispatch` liên tiếp xanh trên Linux / Windows / macOS,
không chạy lại): xem mô tả commit và báo cáo của nhánh `m1/ci-timing`.

## Số tính năng theo mốc

| Mốc | Số F (mốc chính) | Theo ưu tiên | Phần của tính năng khác làm ở mốc này | Kết thúc khi |
|---|---|---|---|---|
| M0 · Nền kiểm (tuần 1) | 1 (F-63) | 1 Must | F-1 (P-1: lệnh cài một dòng), F-17 (D-1: e2e của repo) | xem mục M0 bên dưới → **UAT-0** |
| M1 · Must | 47 | 44 Must (gồm F-72, CR-1) + 3 Should (F-2, F-18, F-26) | — | QC nội bộ PASS mọi phần [Vendor] của Must → **UAT-1** |
| M2 · Should | 19 | 19 Should | — | QC PASS → **UAT-2** |
| M3 · Could | 5 (F-3, F-59, F-60, F-65, F-70) | 5 Could | F-6 (chế độ LAN) | Đạt thì vào v1.0; không đạt thì ra khỏi v1.0, không chặn |
| **Tổng** | **72** | **45 Must / 22 Should / 5 Could** | | Phát hành v1.0 = M0 + M1 + M2 đạt (M3 nếu đạt) |

## Phạm vi M0 (đã duyệt)

Theo bảng Mốc của [FEATURES.md](FEATURES.md#mốc-tech-lead) và [REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md) §5. Effort: 10
ngày công dev (F-17, F-63 + 6 ngày nền kiểm), cộng các mục ✚ Tech Lead ước khi bắt đầu M0 (OI-1).

* **Tính năng:** F-63 `doctor` (toàn bộ); F-17 chỉ phần D-1; F-1 chỉ phần P-1 (lệnh cài một dòng, để khách cài
  bản M0 ở UAT-0). Phần còn lại của F-1, F-17 làm ở M1.
* **Lỗi:** D-1 (e2e Playwright của repo xanh lại), D-15 (`doctor`: "ConnectError" khi Station tắt, cổng bị giữ vào
  LIKELY PROBLEMS), D-21 (`doctor` không khuyên latency timer 1 ms với CH340 / CH343).
* **Khoảng trống:** K-11 (`doctor` đọc `Present_Current`, `Present_Load`, dump thô từng servo).
* **Nền kiểm:** CI xanh Linux / Windows / macOS cho đúng commit, gồm danh sách test bỏ qua theo nền tảng (NFR-18);
  e2e tiếng Việt đi hết luồng người mới; ma trận ảnh Playwright mọi trang × trạng thái × sáng / tối × 1280 / 390 + kiểm
  cuộn ngang + axe trong CI (FL-7; công cụ cho AT-82, AT-83, các AT này đạt ở M1); e2e trên `windows-latest`
  (`--mock`).
* **Spike / đóng gói:** SP-1 (đọc dòng / tải + dump thô), SP-2 (cổng COM ảo trên CI Windows), SP-3 + P-1 (cài trên
  Windows 11 sạch không git), FL-12 (chạy thử phát hành nháp: wheel + `install.ps1` lên pre-release, không phát hành
  chính thức).
* **AT phải PASS khi kết thúc M0** (QC trên đúng bản pre-release của M0):
  * **AT-77** (F-63) `doctor`, phần [Vendor].
  * **AT-2** (F-1, NFR-18) CI Linux / Windows / macOS xanh, e2e của repo xanh, 0 test bỏ qua ngoài danh sách.
  * **AT-1** phần [Vendor] (VM Windows 11 sạch không git): lệnh một dòng cài được, bộ thư viện trùng 100 % bản QC.
* **Kết thúc M0 khi:** ba AT trên PASS; D-1, D-15, D-21, K-11 đóng (mỗi cái có test fail-trước-pass-sau); 0 lỗi mở
  trong phạm vi M0; bản M0 nằm ở pre-release kèm lệnh cài một dòng; khách nhận lệnh cài và hướng dẫn `doctor` →
  **UAT-0** (khách cài, chạy `hibiscus-station doctor --verbose`, gửi zip, chụp Feetech FD). M1 chạy song song; kết quả
  UAT-0 đóng REG-13 và chốt D-9 / NFR-2 cho Windows.

## Phụ thuộc ngoài và việc còn mở

| ID | Việc | Ai | Chặn |
|---|---|---|---|
| EXT-1 / CR-EXT-1 | Phát hành gói `hibiscus` (Hibiscus CLI) **v0.1.2** với giấy phép **Apache-2.0** + tệp LICENSE, không đổi mã (QĐ-4 = A). Làm trong repo nền tảng Hibiscus, không phải repo Station; sau đó Station ghim lại v0.1.2 | Chủ sở hữu nền tảng Hibiscus | AT-98 (F-6, Must) → phát hành v1.0; cần trước QC bản ứng viên M1 |
| OI-1 | Ước effort các mục ✚ (P-1 – P-3, P-6, P-7, SP-1 – SP-3, SP-7) | Tech Lead | Kế hoạch M0 / M1 (không đổi phạm vi) |
| OI-2 | Xác nhận D-19 – D-23 bằng chạy thử (D-19 chỉ trên Windows, UAT-1 bước 14) | QC | — |
| OI-3 | Cập nhật ARCHITECTURE §6 theo SRS v1.0; chốt tên `thermal_blind` và khoá cài đặt giới hạn 10 phút; K-7 | SA | P-3 ở M1 |
| OI-4 | Hẹn ngày UAT-0 / UAT-1 / UAT-2; cho biết loại bộ chuyển USB của hai tay | Khách hàng | UAT-0 sau M0 |

## Ma trận truy vết

QC kiểm trước khi phát hành. FR-n mô tả F-n cùng số; FR-72 – FR-76 là yêu cầu chung; FR-77 mô tả F-72 (CR-1).

| BR | FR / NFR | F | AT | QC result |
|---|---|---|---|---|
| BR-1 Người mới cài và dùng trên Windows bằng tiếng Việt | FR-1 – FR-4, FR-7, FR-67, FR-73; NFR-5, NFR-9, NFR-10 | F-1 – F-4, F-7, F-67 | AT-1 – AT-6, AT-10, AT-81, AT-87, AT-91 | not tested |
| BR-2 Đúng tay thật, không nhầm leader / follower | FR-5, FR-8 – FR-12, FR-15 | F-5, F-8 – F-12, F-15 | AT-7, AT-11 – AT-17, AT-21, AT-96 | not tested |
| BR-3 Hiệu chỉnh chuẩn LeLab | FR-16 – FR-20; NFR-15 | F-16 – F-20 | AT-22 – AT-27 | not tested |
| BR-4 Teleop không trễ hơn LeLab | FR-24 – FR-26; NFR-1a – NFR-1c, NFR-2, NFR-8 | F-24 – F-26 | AT-31 – AT-34, AT-89, AT-90 | not tested |
| BR-5 An toàn và phục hồi | FR-13, FR-14, FR-25, FR-28 – FR-30, FR-32 – FR-36, FR-57, FR-58, FR-72, FR-74, FR-75; NFR-3a – NFR-3c, NFR-4, NFR-6, NFR-7 | F-4, F-13, F-14, F-25, F-28 – F-30, F-32 – F-36, F-57, F-58 | AT-18 – AT-20, AT-33, AT-36 – AT-39, AT-42, AT-44 – AT-46, AT-71, AT-72, AT-88, AT-93 – AT-95, AT-97 | not tested |
| BR-6 Số liệu đúng, không báo động giả | FR-31 – FR-34, FR-37, FR-61; NFR-12, NFR-13 | F-31 – F-34, F-37, F-61 | AT-40 – AT-44, AT-47, AT-75, AT-92 | not tested |
| BR-7 Thu dữ liệu LeRobot có camera | FR-21 – FR-23, FR-27, FR-38 – FR-40, FR-77; NFR-8, NFR-15 | F-21 – F-23, F-27, F-38 – F-40, F-72 | AT-28 – AT-30, AT-35, AT-48 – AT-51, AT-99 | not tested |
| BR-8 Máy chủ Hibiscus (Should) | FR-41 – FR-44; NFR-17 | F-41 – F-44 | AT-52 – AT-56 | not tested |
| BR-9 Chạy model, thấy camera và sức khoẻ động cơ | FR-22, FR-45 – FR-51; NFR-3a, NFR-4, NFR-16 | F-45 – F-51 | AT-57 – AT-64, AT-97 | not tested |
| BR-10 Lập trình không cần huấn luyện (Should) | FR-52 – FR-60, FR-62 | F-52 – F-60, F-62 | AT-65 – AT-74, AT-76 | not tested |
| BR-11 Tuỳ chọn nâng cao cho kỹ sư | FR-18, FR-30, FR-48, FR-59, FR-66 | F-18, F-30, F-48, F-59, F-66 | AT-25, AT-39, AT-60, AT-73, AT-80 | not tested |
| BR-12 Báo cáo chẩn đoán | FR-63 – FR-65 | F-63 – F-65 | AT-77 – AT-79 | not tested |
| BR-13 Không lỗi hiện trường tái diễn | FR-76; REG-1 – REG-27; NFR-18 | mọi F có cột REG | AT-2 + AT ghi ở từng REG ([REGRESSION.md](REGRESSION.md)) | not tested |
| BR-14 Song ngữ, sáng / tối, máy tính và điện thoại | FR-67, FR-68; NFR-10, NFR-11 | F-67, F-68 | AT-81 – AT-83, AT-91 | not tested |
| BR-15 Cập nhật không mất dữ liệu | FR-69 – FR-71, FR-75; NFR-15, NFR-16 | F-69 – F-71 | AT-84 – AT-86, AT-95 | not tested |
| BR-16 Chỉ cục bộ, trừ chế độ LAN | FR-6; NFR-14 | F-6 | AT-8, AT-9, AT-98 | not tested |
| BR-17 Automation | — | **Won't v1.0** (W-1), dự kiến bản sau | — | — |
| BR-18 Nền tảng web | — | **Won't v1.0** (W-2) | — | — |

**NFR → AT** (mỗi NFR được đo, không giả định):

| NFR | AT | QC result |
|---|---|---|
| NFR-1a / 1b / 1c | AT-31 (NFR-1b cũng AT-89) | not tested |
| NFR-2 | AT-31, AT-89 | not tested |
| NFR-3a / 3b / 3c | AT-36, AT-88 | not tested |
| NFR-4 | AT-38, AT-97 | not tested |
| NFR-5 | AT-87 | not tested |
| NFR-6 | AT-42, AT-93 | not tested |
| NFR-7 | AT-19, AT-37, AT-45, AT-54, AT-72, AT-94, AT-95 | not tested |
| NFR-8 | AT-90 | not tested |
| NFR-9 | AT-1 – AT-4 | not tested |
| NFR-10 | AT-81, AT-91, AT-99 | not tested |
| NFR-11 | AT-82, AT-83, AT-99 | not tested |
| NFR-12 | AT-43, AT-92 | not tested |
| NFR-13 | AT-40 | not tested |
| NFR-14 | AT-8, AT-57, AT-98 | not tested |
| NFR-15 | AT-27, AT-47, AT-49, AT-86 | not tested |
| NFR-16 | AT-86 | not tested |
| NFR-17 | AT-54 | not tested |
| NFR-18 | AT-2 | not tested |

Kiểm: 72 / 72 tính năng có ≥ 1 AT (F-72 → AT-99, CR-1); 16 / 16 BR trong phạm vi có ≥ 1 F; BR-17 (Automation), BR-18 (nền tảng web) là
Won't v1.0 theo quyết định của khách ngày 2026-11-17; 18 / 18 NFR (tính NFR-1, NFR-3 theo phần a / b / c) có AT.
99 AT (AT-1 – AT-99). Danh sách Won't W-1 – W-12: [FEATURES.md](FEATURES.md#không-làm-trong-v10-wont).

## Ký xác nhận

| | Người | Ngày | Ghi chú |
|---|---|---|---|
| Khách hàng duyệt danh sách | Khách hàng | 2026-11-17 | "1. A, 2. A, 3. A, 4. A" · "Duyệt, bắt đầu làm" |
| Khách hàng duyệt CR-1 (F-72 vào M1) | Khách hàng | 2026-11-19 | "Có, thêm vào M1" |
| QC (trước phát hành) | | | |
| Khách hàng nghiệm thu (biên bản) | | | |
