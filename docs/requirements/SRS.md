# Hibiscus Station: SRS v0.2 (2026-11-17) · trạng thái: bản nháp (vòng 1, sau rà soát SA + Tech Lead)

Đặc tả yêu cầu phần mềm (Software Requirements Specification). BA soạn; SA và Tech Lead đã rà soát vòng 1
([REVIEW-SA.md](REVIEW-SA.md), [REVIEW-TECHLEAD.md](REVIEW-TECHLEAD.md)); QC kiểm tính kiểm-được. Chỗ v0.2
đổi so với v0.1 ghi **(v0.2: …)** kèm mã flag (SA-…, FL-…) hoặc đề xuất P-n / quyết định QĐ-n của BRD §9;
lỗi đã biết D-n: [FEATURES.md](FEATURES.md#lỗi-đã-biết-d-n).

## 1. Tổng quan

### 1.1 Mục đích
Mô tả chính xác hành vi Station **0.2.8** (`main` `12f36da`) mà v1.0 phải giữ và đưa lên chuẩn chất
lượng. Kiến trúc và lựa chọn công nghệ thuộc ARCHITECTURE.md (SA). Mỗi FR-n mô tả tính năng F-n cùng
số trong [FEATURES.md](FEATURES.md); FR-72 trở đi là yêu cầu chung cho mọi tính năng.

### 1.2 Tham chiếu
* [BRD.md](BRD.md) v0.2 (BR-1 … BR-18, RULE-1 … RULE-16, quyết định QĐ-1 – QĐ-4, Q-2 … Q-8)
* [ARCHITECTURE.md](ARCHITECTURE.md) v0.2 (spike SP-1 … SP-7, ADR-1 … ADR-13)
* Đặc tả kỹ thuật hiện có: `docs/spec/station.md` (contract v0.1), `docs/spec/station-programs.md`
* Hướng dẫn người dùng: `docs/user-guide/{vi,en}/station.md`, danh sách UAT phần cứng
  `docs/user-guide/{vi,en}/station-hardware-uat.md`
* `openapi.json` (hợp đồng REST `/api/v1`), `CHANGELOG.md` của sản phẩm (0.1.0 … 0.2.8)
* Hợp đồng máy chủ Hibiscus `v0.1.1` (`tests/contract/`)

### 1.3 Thuật ngữ

| Thuật ngữ | Nghĩa |
|---|---|
| Follower | Tay robot làm việc, có mô-men, Station điều khiển |
| Leader | Tay người cầm để điều khiển, không mô-men, Station chỉ đọc |
| Hồ sơ robot (profile) | Một cặp follower (+ leader) với cổng, mã hiệu chỉnh, camera, mặc định an toàn |
| Hiệu chỉnh (calibration) | Tệp lerobot ghi home + dải min/max từng khớp; được ghi vào EEPROM động cơ |
| Teleop | Leader điều khiển follower, không ghi dữ liệu |
| Phiên (session) | Một lần teleop / ghi / phát lại / chạy model / quỹ đạo / chương trình / về tư thế nghỉ / căn tay |
| Nhịp (tick) | Một vòng của vòng điều khiển (đọc → lọc an toàn → ghi lệnh) |
| E-stop | Dừng khẩn cấp phần mềm (đóng băng; lần hai: thả lỏng) |
| Dead-man | Giao diện phải gửi tín hiệu sống mỗi 250 ms; mất 1 s → e-stop |
| Telemetry | Nhiệt độ, điện áp, dòng, tải, cờ trạng thái của động cơ |
| "Không rõ" | Giá trị bị loại vì vô lý (RULE-5); hiện "—" |
| Policy / model | Mạng đã huấn luyện (ACT, Diffusion, SmolVLA…) chạy trên robot |
| Quỹ đạo (trajectory) | Chuỗi tư thế follower ghi bằng leader, phát lại được |
| Chạy thử (dry run) | Chạy chương trình trên tay giả lập |
| [UAT-KH] | Chỉ chứng minh được bằng UAT của khách hàng trên Windows + SO-101 thật |

## 2. Người dùng và quyền

| Vai trò | Mô tả | Quyền |
|---|---|---|
| Người vận hành cục bộ | Người mở Station bằng liên kết có token trên chính máy đó (U-1 người mới, U-2 kỹ sư) | Toàn quyền mọi chức năng |
| Script cục bộ | Chương trình trên cùng máy dùng `Authorization: Bearer <token>` | Như trên (API) |
| Người trong LAN | Chỉ khi chế độ LAN bật đủ điều kiện (FR-6) | Như trên |
| Hệ thống ngoài | Gửi tín hiệu `POST /api/v1/signals/<tên>` có token; MQTT | Chỉ đặt giá trị tín hiệu |
| Bất kỳ ai khác | Host / Origin không được phép, không token | Bị từ chối (`403 forbidden_host`, `401`) |

Không có tài khoản hay phân quyền trong Station v1.0. Giao diện người mới và kỹ sư là một; tuỳ chọn
kỹ sư nằm sau "Nâng cao" (Q-7).

## 3. Yêu cầu chức năng

Mỗi FR: **Station phải …** · traces · đầu vào · xử lý · đầu ra · lỗi / trường hợp biên.

### A. Cài đặt và khởi động

**FR-1 (F-1) Cài đặt Windows.** (v0.2: P-1, QĐ-3 phương án A.) Station phải cài được trên Windows 10/11 x64
bằng **một** lệnh PowerShell chép-dán từ hướng dẫn tiếng Việt (`irm <địa chỉ bản phát hành>/install.ps1 |
iex`), không cần quyền admin, không cần git, không cần Python có sẵn: lệnh cài uv nếu thiếu, rồi cài wheel
của đúng phiên bản với **bộ phụ thuộc cố định** xuất từ `uv.lock` (tệp constraints và wheel dựng sẵn của
`lerobot@fe1c545` và `hibiscus` đính kèm bản phát hành), tuỳ chọn torch CPU. Hai lần cài cùng phiên bản ở
hai ngày khác nhau phải cho cùng bộ thư viện (so `uv pip freeze`). Traces BR-1, BR-15. Đầu ra: lệnh
`hibiscus-station` có trên PATH. Lỗi: không có Python 3.12 → uv tự tải; driver CH340 / CH343 thiếu → hướng
dẫn nói cách cài (Station không tự cài). (Phương án B của QĐ-3: giữ hai lệnh `uv` hiện tại.)

**FR-2 (F-2) Cài đặt Linux.** Wheel trên Ubuntu 22.04 / 24.04 x86_64 (lệnh `uv tool install` với cùng tệp
constraints của FR-1); kèm unit systemd người dùng tuỳ chọn. Wheel arm64: bản xem trước (W-9, QĐ-2).
Traces BR-1.

**FR-3 (F-3) Docker.** (v0.2: QĐ-2.) Thuộc nghiệm thu v1.0: Linux x86_64 image `-cpu`. `-cuda`, Pi 5, Jetson:
bản xem trước (W-9), `install.sh` in cảnh báo "bản xem trước" khi chọn chúng. `deploy/install.sh` phải dò máy (PC / GPU NVIDIA / Jetson / Pi 5), hỏi trước khi
cài Docker, chọn image `-cpu` / `-cuda` / `-jetson`, cài luật udev (tên `/dev/hibiscus/arm-*`), tự khởi
động; `hibiscus-station-ctl status | logs | url | ports`. Container không chạy bằng root, có health
check, dừng an toàn khi `docker stop`. Chỉ Linux. Traces BR-1.

**FR-4 (F-4) Khởi động.** `hibiscus-station` phải: (1) khởi động máy chủ ở `127.0.0.1:18210` (đổi bằng
`--port`); (2) tạo token mới mỗi lần chạy; (3) mở trình duyệt ở liên kết đăng nhập (trừ
`--no-browser`), liên kết đặt cookie rồi chuyển về `/` (token không còn trong lịch sử); (4) nếu đã có
một bản đang chạy thì in liên kết của bản đó và thoát mã 0; (5) `hibiscus-station url` in liên kết
đăng nhập mới; (6) ghi dòng khởi động (FR-64). Traces BR-1, NFR-5. Lỗi (v0.2: D-3, D-4): cổng bận bởi chương trình khác → **không** in / mở liên kết
đăng nhập, in một câu rõ ("Cổng 18210 đang được chương trình khác dùng. Chạy lại với --port 18211") và
thoát mã ≠ 0; `hibiscus-station url` khi không có bản nào đang trả lời → "Hibiscus Station is not running"
và mã ≠ 0 (tệp `token` / `station.pid` cũ không được tính); `url` tìm được cả bản demo (`--mock`). Các dòng
người mới chắc chắn thấy trong PowerShell (khởi động, liên kết đăng nhập, cổng bận, đã có bản đang chạy)
theo NFR-10.

**FR-5 (F-5) Chế độ demo.** `--mock` phải dùng tay, camera, policy giả lập; dữ liệu ở
`~/.hibiscus/station-demo` (trừ khi có `--home`); thanh trên hiện chip **TAY GIẢ LẬP** (tooltip "tay
robot thật không chuyển động"); Cài đặt ghi "chế độ demo". (v0.2: P-4, FL-10, D-8) Tay leader giả lập
đứng theo tư thế follower khi bắt đầu teleop / ghi và khi Kiểm tra hai tay (chỉ trong demo), nên mọi bước
chạy được ngay ở lần bấm đầu. Traces BR-2, RULE-11.

**FR-6 (F-6) Truy cập cục bộ an toàn.** Station phải chỉ nhận Host `127.0.0.1:<port>`,
`localhost:<port>`, `[::1]:<port>`; mọi yêu cầu cần cookie phiên hoặc Bearer token; yêu cầu không phải
GET cần header `X-Station: 1`; WebSocket kiểm Origin. LAN chỉ khi có đủ `--host` khác loopback, token
cố định ≥ 32 ký tự `[A-Za-z0-9_-]` và ít nhất một tên máy cho phép (không ký tự đại diện); thiếu một
→ thoát mã 2 với lời giải thích. Token máy chủ Hibiscus không bao giờ gửi tới trình duyệt; log che
token. Traces BR-16.

**FR-7 (F-7) Trang chào mừng và thanh bước.** Lần đầu mở: trang Chào mừng với hai thẻ "Thiết lập
robot" và "Ghép nối với máy chủ Hibiscus" (bỏ qua được). Thanh bước bên trái liệt kê 8 bước và các
trang phụ; một bước có ✓ khi điều kiện xong (hồ sơ đã lưu; hai tay đã hiệu chỉnh; ≥ 1 camera phát; ≥ 1
dataset có ≥ 1 tập; đã tải lên; đã nhập model). Bước bị khoá hiện lý do dưới tên (ví dụ "Hãy hiệu
chỉnh tay follower trước", "Hãy đặt lại sau khi dừng khẩn cấp" (v0.2: D-12, cùng từ với nút "Đã an toàn,
đặt lại")); mở một bước bị khoá (bằng thanh bước
hoặc gõ địa chỉ) phải hiện trang "Bước này đang bị khoá" với lý do bằng lời (câu dịch theo `code`), nút
"Tới <bước cần làm>", và **mọi nút trên trang bị tắt**; (v0.2: P-5, FL-1) lý do thô của Station (tiếng Anh,
có thể có đường dẫn) chỉ nằm trong mục "Chi tiết kỹ thuật" thu gọn, đóng mặc định; trang Huấn luyện vẫn hiện form
ghép nối. Giống nhau ở bề rộng máy tính và điện thoại. Traces BR-1. REG-12.

### B. Robot và cổng

**FR-8 (F-8) Hồ sơ robot.** Tạo / sửa / xoá hồ sơ: tên, loại (SO-101 / SO-100), cổng follower (bắt
buộc), cổng leader (tuỳ chọn; "Không có leader (chỉ chạy model)"), mã hiệu chỉnh mỗi tay (chọn từ mã
có sẵn, ví dụ của LeLab, hoặc mã mới), "Khi kết thúc phiên": giữ nguyên (mô-men bật) / về tư thế
nghỉ rồi thả lỏng; giới hạn bước, tư thế nghỉ, camera. Xoá hồ sơ không xoá tệp hiệu chỉnh. Sửa bị từ
chối khi hồ sơ đó đang chuyển động. Ghi nguyên tử vào `robots.yaml`. Traces BR-2.

**FR-9 (F-9) Danh sách cổng.** Chỉ cổng USB serial, với mô tả, VID:PID, số serial, đường dẫn ổn định
nếu có, (v0.2: SA-W1) "đang dùng bởi Station (<tay>)" cho cổng Station đang giữ; với tiến trình khác: Linux nêu
tên tiến trình (từ `/proc`), Windows chỉ báo "đang bận — có thể LeLab / lerobot đang mở" **khi** Kết nối
hoặc Dò thất bại với `Access is denied` (Windows không có API thường để biết tiến trình nào giữ cổng COM;
Station không mở thử cổng chỉ để liệt kê); Windows: `COM3`, `com3`, `\\.\COM3` là một cổng. Traces BR-2.

**FR-10 (F-10) Tìm cổng theo vai trò.** Dưới ô follower và ô leader có "Tìm <tay> (cử động)" và "Tìm
<tay> (rút cáp)". Cử động: (v0.2: SA-F1) Station mở từng cổng ứng viên ở 1 Mbaud và **chỉ gửi lệnh ping / đọc, không ghi
thanh ghi nào, không bật mô-men** (cổng đang bận bị bỏ qua và ghi "đang bận"), ping id 1–6, trả cổng có
vị trí thay đổi > 50 bước trong ≤ 15 s; **không bao giờ** xét cổng đã gán cho tay kia. Rút cáp: chụp
danh sách cổng, người dùng rút cáp, cổng biến mất trong ≤ 15 s là kết quả. Kết quả chỉ vào ô đã bấm.
Hết giờ → "Không tìm thấy, thử lại" (không treo). Traces BR-2, RULE-13. REG-6.

**FR-11 (F-11) Dò cổng và gợi ý vai trò.** `POST /ports/probe` chỉ gửi lệnh đọc (điện áp, model,
firmware) tới mỗi cổng rảnh; dưới mỗi cổng: "có vẻ là tay leader (≈ 5 V)" / "có vẻ là tay follower (≥ 6,5 V)" / "chưa
rõ"; cảnh báo khi ô follower ≈ 5 V hoặc ô leader ≥ 7 V; nút "Đổi chỗ follower ⇄ leader" đổi cổng, mã
hiệu chỉnh ở lại theo vai trò. Không bao giờ tự đổi. Traces BR-2, RULE-13.

**FR-12 (F-12) Kết nối.** "Kết nối" phải đi qua: mở cổng → bắt tay (6 động cơ, model, firmware) → cấu
hình → camera; hiện tiến trình. Mỗi lệnh bus được thử lại 2 lần khi gói tin lỗi (telemetry không thử
lại). Lỗi phải nói bước và lý do bằng lời, kèm chi tiết: cổng bận (`port_busy`, "Một chương trình khác
(LeLab? lerobot?) đang dùng COMx"), động cơ thiếu / sai model / firmware lẫn (`bus_error`, bước
`handshake`), không ghi được cấu hình (bước `configure`). Mỗi tay báo mã hiệu chỉnh, tệp, vấn đề (không
có tệp / có tệp khác / động cơ không giữ trường nào), số lỗi bus, lỗi bus cuối. "Ngắt kết nối" đóng
cổng (tuỳ chọn thả lỏng). (v0.2: SA-W2) Trên Windows `Access is denied` **lúc mở cổng** là `port_busy`
(không bao giờ `device_lost`); lúc đang chạy là `device_lost` (FR-13). (v0.2: P-7, D-22, SA-F2) Trên Linux,
trước khi mở, Station kiểm tiến trình khác đang giữ tty (`/proc/*/fd`) → `port_busy` nêu tên tiến trình.
Traces BR-2. REG-14.

**FR-13 (F-13) Mất thiết bị USB.** Khi thiết bị serial biến mất (Windows `ERROR_ACCESS_DENIED`,
`ClearCommError`, "device not ready", `PermissionError`; Linux `EIO` / `ENODEV` / `ENXIO`), Station
phải: không thử lại, không gửi tắt mô-men liên tục lên cổng chết, chuyển trạng thái `error` lý do
`device_lost` với tay, cổng, định danh USB, thông báo hệ thống; trang hiện "Mất kết nối USB với
<tay> (<cổng>)" kèm danh sách kiểm tra (cáp, nguồn follower, đóng LeLab, Windows USB selective
suspend, rút ra cắm lại) và gợi ý "cú nhảy lớn" khi lỗi xảy ra ngay sau bật mô-men / bắt đầu teleop.
"Kết nối lại" chờ bộ chuyển trở lại (cùng serial, đường dẫn by-id hoặc VID:PID, có thể số COM mới),
cập nhật cổng trong hồ sơ, kết nối và ghi lại hiệu chỉnh xuống động cơ. Hai bộ chuyển giống hệt không
có serial → không đoán, yêu cầu người dùng chọn (v0.2: SA-W2: bộ chuyển CH340 `1a86:7523` không có
serial, nên hai tay CH340 sau khi cắm lại **luôn** được hỏi tay nào là tay nào; đây là thiết kế, hướng dẫn
nói rõ; Windows gán số COM theo ổ USB nên cắm sang ổ khác = số COM mới; mục USB selective suspend trong
hướng dẫn có ảnh minh hoạ). Gói tin hỏng (không phải mất thiết bị) không phải
`device_lost`. Traces BR-5. REG-8.

**FR-14 (F-14) Mô-men và tư thế nghỉ.** Khi Sẵn sàng / Đã dừng khẩn: "Bật mô-men", "Thả lỏng (tắt
mô-men)" (chưa có tư thế nghỉ → hộp xác nhận "tay robot sẽ rũ xuống tại chỗ. Hãy đỡ tay trước");
"Lấy tư thế hiện tại làm tư thế nghỉ" lưu vào hồ sơ. Sau kết nối hiện bảng khớp và sức khoẻ động cơ
mỗi tay. Traces BR-5.

**FR-15 (F-15) Bảo vệ khỏi hồ sơ demo.** Khi chạy không có `--mock`: hồ sơ demo còn trong thư mục dữ
liệu thật không được kích hoạt, mang nhãn **DEMO**, nút Kết nối bị tắt ("Hồ sơ demo: tay giả lập.
Chạy Station với --mock để dùng"), API trả `409 demo_profile`. Khi có cổng serial thật đang cắm và hồ
sơ hiện tại là demo: banner "Đang dùng tay giả lập — tay thật (COMx) không chuyển động" với nút "Tạo
hồ sơ cho tay thật" điền sẵn cổng. Traces BR-2, RULE-11. REG-2.

### C. Hiệu chỉnh

**FR-16 (F-16) Kiểm tra hiệu chỉnh.** Vào trang Hiệu chỉnh khi đã kết nối, Station phải đọc EEPROM
mỗi tay và so với mọi tệp hiệu chỉnh trên máy (`GET /calibration/check`), rồi hiện một trong: "đã
hiệu chỉnh — dùng luôn"; "Tay này đang dùng hiệu chỉnh từ LeLab: <tệp>" + "Dùng" (lưu một bản thành
mã của robot này); "động cơ không giữ được tệp hiệu chỉnh" + "Ghi lại tệp" / "Hiệu chỉnh lại"; "chưa
được hiệu chỉnh" + "Bắt đầu hiệu chỉnh". Không bao giờ đề xuất tệp khớp với động cơ của tay kia.
Traces BR-3. REG-7.

**FR-17 (F-17) Luồng hiệu chỉnh.** Ba bước: follower → leader → kiểm tra. Mỗi tay: **Đặt home** (hình
SO-101 ở giữa biên độ, tay thả lỏng, banner "hãy giữ lấy nó") → **Biên độ**: mỗi khớp (shoulder_pan,
shoulder_lift, elbow_flex, wrist_flex, **wrist_roll**, gripper) hiện `min | vị trí | max` trực tiếp và
được tick khi đã quay ≥ 100 bước; số đọc ngoài dải encoder bị bỏ qua; "Đã xong N / 6 khớp"; **Lưu** tắt
(và API từ chối `finish_ranges`) cho tới khi đủ 6 tick; min = max là lỗi. Lưu ghi tệp ở
`<HF_LEROBOT_CALIBRATION>/robots/so_follower/<id>.json` hoặc `.../teleoperators/so_leader/<id>.json`
(tôn trọng `HF_LEROBOT_CALIBRATION`, `HF_LEROBOT_HOME`, `XDG_CACHE_HOME`) và ghi vào động cơ. Khi
follower đang hiệu chỉnh, leader đi theo tự động. Huỷ được ở mọi bước; e-stop được. Không có chữ
"xoay tròn, không cần ghi" cho bất kỳ khớp nào trên SO-100 / SO-101. Traces BR-3. REG-4, REG-7.

**FR-18 (F-18) Tệp hiệu chỉnh nâng cao.** Mục "Nâng cao: các tệp hiệu chỉnh" (đóng mặc định) liệt kê
mọi tệp của tay đó (cả thư mục cũ `so101_follower`, `so100_follower`, `so101_leader`, `so100_leader`)
với nhãn và nút "Dùng tệp này" (sao chép sang mã của tay, tệp cũ thành `.bak-<thời gian>`, ghi xuống
động cơ). Traces BR-3, BR-11.

**FR-19 (F-19) Kiểm tra hai tay.** Cần cả hai tay đã hiệu chỉnh. Follower đứng yên; người dùng đặt
leader giống follower, bấm "Kiểm tra" (`GET /calibration/compare`) → bảng độ lệch từng khớp; mọi khớp
≤ 20° (kẹp ≤ 20 %) → "Hai tay khớp nhau (lệch lớn nhất X). Sẵn sàng teleop" + "Thử teleop"; ngược lại
nêu khớp lệch, mỗi khớp với đơn vị đúng (° cho khớp, % cho kẹp), và **một** lý do khả dĩ theo trường hợp
(v0.2: D-7): một vài khớp → đặt lại tư thế / sai tệp ("Hiệu chỉnh lại <tay>"); mọi khớp → có thể nhầm
cổng leader với follower; không liệt kê lý do không khớp với trường hợp. Luôn có "Vẫn thử teleop" (teleop vẫn áp RULE-12).
Traces BR-3. REG-7. Q-6.

**FR-20 (F-20) Dùng chung với lerobot / LeLab.** (v0.2: SA-F3, ma trận phiên bản.) (a) lerobot 0.7.1
(`fe1c545`): tệp do Station ghi dùng được với `lerobot-teleoperate` không cần hiệu chỉnh lại và ngược lại
(AT vendor); (b) LeLab **đang cài trên PC của khách** (phiên bản lerobot ghi lại từ `doctor`): hai chiều,
UAT. Nếu LeLab của khách dùng thư mục cũ (`so101_follower` …): chiều LeLab → Station qua "Dùng tệp này"
(FR-18); chiều Station → LeLab cũ là CR (ghi thêm bản sao vào thư mục cũ). Traces BR-3, C-2.

### D. Camera

**FR-21 (F-21) Tìm và thử camera.** "Thiết bị tìm thấy": Windows / macOS dò số OpenCV 0, 1, 2… dừng sau
3 số trống liên tiếp; Linux dò `/dev/video*` (đường dẫn `by-id`), RealSense nếu đã cài; camera Station
đang dùng hiện "đang dùng bởi <tên>" và không bị mở lại. "Thử" mở camera 2 s → ảnh chụp, fps và độ
phân giải đo được; fps đo < 90 % yêu cầu → "Camera chậm hơn yêu cầu (băng thông USB). Hãy thử MJPG
hoặc độ phân giải thấp hơn". Số "0" chọn trên giao diện mở như số camera, không như tên tệp. Không in
lỗi dò backend của OpenCV ra màn hình. (v0.2: SA-W4) Trên Windows / macOS camera được nhận theo số, hai
webcam giống nhau có thể đổi số sau khi khởi động lại / cắm lại: hướng dẫn và UAT có bước "sau khi cắm lại,
bấm Thử từng camera và kiểm hình đúng"; nhận diện theo đường dẫn thiết bị là CR (W-12). Traces BR-7. REG-20.

**FR-22 (F-22) Camera đã cấu hình.** Thêm từ thiết bị tìm thấy (mặc định 640×480 @ 30 MJPG); tên chữ
thường `[a-z0-9_]` không trùng (là khoá `observation.images.<tên>`, trang nói rõ); độ phân giải, fps,
định dạng, xoay; xem trực tiếp; sửa / xoá. Mỗi camera chỉ một chủ sở hữu trong Station; vòng điều khiển
và giao diện thấy cùng khung hình. Camera mở khi kết nối hồ sơ và giữ mở giữa các phiên. Traces BR-7,
BR-9.

**FR-23 (F-23) Camera mất trong phiên.** Khi ghi hoặc chạy model, camera không có khung hình mới quá
0,5 s → cảnh báo "Camera <tên> không gửi hình. Đồng hồ tập đang tạm dừng", lớp sọc trên ô camera, đồng
hồ tập dừng; quá 3 s → phiên dừng với lý do `camera_lost`, follower được giữ, dataset vẫn mở được.
Teleop không cần camera nào đang phát; ghi, chạy model, chương trình thì cần. Traces BR-7. REG-15.

### E. Teleop và phát lại

**FR-24 (F-24) Teleop.** Bắt đầu cần: kết nối, Sẵn sàng, hai tay đã hiệu chỉnh, không động cơ follower
nóng, leader trong 30° (RULE-12); không cần bước Kiểm tra hai tay (v0.2: FL-9). Vòng nhanh: mỗi nhịp kiểm e-stop → đọc leader → lọc an toàn → ghi
lệnh follower; quan sát follower và camera ở ≤ 30 Hz, telemetry ở các nhịp khác. fps mặc định 250 (≤
300; ô chọn fps hiện ngay trên trang, mặc định "250 (nhanh nhất)"); bus chậm thì chạy chậm hơn, không lỗi. Giới hạn bước teleop
`safety.teleop_max_relative_target` 30°; kẹp dải hiệu chỉnh. Màn hình: camera (nếu có), bảng khớp
(leader, follower, bị cắt), sức khoẻ động cơ hai tay, Robot 3D, đồng hồ, "độ trễ ~X ms, Y Hz" đo trực
tiếp (p50; đây là độ trễ **phần mềm** đọc leader → gửi lệnh, NFR-1b), Dừng. (v0.2: D-10, D-11) Mọi số có
nhãn và đơn vị đúng: bảng khớp ghi đơn vị (bước encoder trước hiệu chỉnh, ° / % sau); FPS hiện số thật
đạt được / mục tiêu ("nhanh nhất" khi chọn 250); bộ đếm nhịp không dùng chữ "Bước". Tóm tắt phiên lưu
`loop.fps`, `latency_ms_p50/p95`. Traces BR-4, NFR-1, NFR-2.
REG-5, REG-7.

**FR-25 (F-25) Leader xa và căn tay.** Leader lệch > `safety.max_approach_deg` (30°) ở bất kỳ khớp nào
→ từ chối `leader_far` nêu khớp và độ lệch, kèm "Đưa tay follower về tư thế tay leader": follower đi
chậm (minimum-jerk, ≤ 30°/s) tới tư thế leader với dead-man và e-stop ("giữ yên tay leader. Space để
dừng"), rồi teleop bắt đầu. Ghi dữ liệu không đề nghị căn. Traces BR-4, BR-5.

**FR-26 (F-26) Cảnh báo không theo kịp.** Khi giới hạn bước cắt > 20 % số nhịp trong teleop / ghi:
cảnh báo "Tay follower chạy sau tay leader quá giới hạn an toàn 30°: nó không theo kịp tốc độ này…".
Traces BR-4.

**FR-27 (F-27) Phát lại tập.** Từ chi tiết dataset, "Phát lại" một tập: lệnh của tập ở fps của dataset
lên follower, giới hạn bước 5°, dead-man (bật mặc định, tắt được ở Cài đặt), dừng được trong một nhịp,
camera và telemetry hiển thị. Traces BR-7.

### F. An toàn, e-stop, nhiệt, telemetry

**FR-28 (F-28) E-stop.** Nút DỪNG (≥ 96 px, 128 px trên Chạy model) cố định góc phải dưới khi trạng
thái là hiệu chỉnh / teleop / ghi / phát lại / chạy model / quỹ đạo / chương trình / về nghỉ / căn tay.
Phím Space từ mọi nơi **trong cửa sổ Station đang được chọn** (không cuộn trang; khi đang gõ chữ thì Esc;
v0.2: SA-S2, hướng dẫn nói rõ Space không có tác dụng khi người dùng đang ở cửa sổ khác; phím dừng toàn
cục là CR W-11). Cũng qua `POST /estop` và WebSocket.
Lần 1: trong nhịp hiện tại không gửi lệnh mới, `Goal := Present`, mô-men giữ, trạng thái `estopped`
(lý do `user`). Lần 2 trong 2 s hoặc "Thả lỏng (tắt mô-men)": tắt mô-men và hiện banner "Hãy đỡ tay robot" (v0.2: D-6). Khi `estopped` nút thành
"Đã an toàn, đặt lại" (xanh) kèm lý do; reset về Sẵn sàng (bị từ chối khi còn điều kiện nhiệt, xem
FR-32). E-stop và reset không ghi EEPROM, không đổi tệp hiệu chỉnh. Traces BR-5, NFR-3, RULE-8. REG-10.

**FR-29 (F-29) Dead-man.** Trong chạy model, phát lại (mặc định), quỹ đạo, chương trình trên robot, về
tư thế nghỉ, căn tay: giao diện gửi tín hiệu mỗi 250 ms; không nhận từ giao diện nào trong
`safety.deadman_timeout_s` (1,0 s) → e-stop lý do `ui_lost`. Không áp cho teleop / ghi (người cầm
leader). Traces BR-5, NFR-4.

**FR-30 (F-30) Giới hạn an toàn và điều kiện bắt đầu.** Mỗi nhịp, mỗi khớp: `|lệnh − quan sát|` ≤ giới
hạn bước (policy / phát lại / chương trình `max_relative_target` 5°; teleop / ghi 30°; theo hồ sơ);
lệnh kẹp trong `[min, max]` hiệu chỉnh; giới hạn thời gian tập (ghi, chạy 30 s mặc định, ≤ 600 s) do
Station áp, không phải giao diện. Màn hình Chạy model chỉ cho giảm bước tối đa so với hồ sơ, trừ khi
mở "Nâng cao" ("Vượt mức X của hồ sơ. Mở Nâng cao để tăng"). Không phiên nào bắt đầu khi: động cơ
follower nóng (`motor_hot`), camera cấu hình không phát (trừ teleop), tay dùng chưa hiệu chỉnh
(`not_calibrated`), model không tương thích, robot đang e-stop (`estopped`), robot bận (`busy`). Cắt
> 30 % nhịp trong 2 s khi chạy model → "Policy đang bị bộ giới hạn an toàn chặn liên tục". Traces BR-5,
BR-11, RULE-1, RULE-2.

**FR-31 (F-31) Sức khoẻ động cơ.** Với mỗi động cơ follower và leader: nhiệt độ (°C), điện áp (V),
dòng (A), tải (%), cờ trạng thái (điện áp, cảm biến góc, quá nhiệt, quá dòng, quá tải); nhiệt độ và
trạng thái 2 Hz, điện áp / dòng / tải 1 Hz, đọc khi vòng điều khiển có thời gian trống, bắt buộc đọc
nhiệt khi mẫu cũ hơn 2 s. Bảng gọn trên Robot, Teleop, Ghi, Chạy model, Chương trình; chip "Động cơ
nóng nhất <động cơ> <nhiệt> (<mức>)" trên thanh trên mở ngăn chi tiết: bảng động cơ × đại lượng, đường
120 s, ngưỡng nét đứt, giới hạn đọc từ động cơ ("động cơ tự ngắt ở 70 °C", "tối thiểu X V", "giới hạn
dòng X A" chỉ khi đơn vị dòng đã được SP-1 xác nhận; nếu không, dòng hiện "—" ở mọi nơi, P-8). Lần đọc không có trả lời → "không phản hồi" (giá trị cũ, có tooltip); ba lần liên tiếp →
cảnh báo "Không đọc được thông số động cơ". Leader có ghi chú "Di chuyển bằng tay: chỉ để tham khảo,
không bao giờ báo động". Telemetry lưu theo phiên và theo tập (FR-37, FR-40). Traces BR-6. REG-11.

**FR-32 (F-32) Ngưỡng nhiệt và dừng an toàn.** Mặc định: ấm ≥ 50 °C (vàng, chip vàng, Hibi "<động cơ>
đang ấm lên (52 °C)"); nóng ≥ 60 °C (cam, banner, chặn phiên mới); nguy hiểm ≥ 65 °C ở 2 mẫu liên tiếp
hoặc cờ quá nhiệt / quá tải (trừ quá tải kẹp, FR-34) trên follower → dừng an toàn ≤ 2 s: (1) e-stop, (2)
giữ, (3) nếu có tư thế nghỉ và động cơ < nguy hiểm + 5 °C: về tư thế nghỉ trong 1,5 s (vẫn qua lọc an
toàn), (4) tắt mô-men follower, (5) banner đỏ "Động cơ nguy hiểm: <động cơ> <nhiệt> °C. Robot đã dừng,
đã tắt mô-men. Hãy để động cơ nguội." + "Hãy đỡ tay robot". Cờ quá nhiệt hoặc ≥ nguy hiểm + 5 °C: bỏ
bước 2–3, tắt mô-men ngay. Trạng thái `estopped` lý do `thermal`; reset chỉ khi mọi động cơ dưới
"nóng"; hiện "Khoảng N giây nữa đủ nguội để đặt lại" (ước lượng tuyến tính 60 s). Một mức chỉ hết khi
thấp hơn ngưỡng 3 °C. Ngưỡng dùng giới hạn nhiệt thật của từng servo đọc khi kết nối (RULE-4). Traces
BR-5, BR-6. REG-3.

**FR-33 (F-33) Số đo hợp lý.** Station phải coi là "không rõ" (hiện "—", tooltip "Không có giá trị:
servo này không báo đại lượng này (số đọc vô lý nên bị bỏ qua)") mọi giá trị: nhiệt độ ngoài 1–150 °C;
giới hạn nhiệt ngoài 40–150 °C (dùng mặc định); dòng > 3,5 A; tải ngoài ±100 %; điện áp ngoài 3–16 V;
bit 15 (hướng) của dòng bị bỏ trước khi đổi đơn vị. Giá trị "không rõ" không bao giờ tạo cảnh báo,
không làm lần đọc bị coi là lỗi, không làm dừng robot. Khi không động cơ nào báo nhiệt độ thật: lần
đọc tính là lỗi (cảnh báo telemetry), không phải quá nhiệt. (v0.2: P-3, QĐ-1 phương án A) Hành vi khi chạy
lúc đó: (1) mỗi lần kết nối, hộp xác nhận "Không đọc được nhiệt độ động cơ: bảo vệ nhiệt của Station đang
tắt. Chỉ còn bảo vệ của chính servo (tay có thể rơi). Theo dõi tay robot." với nút "Tôi hiểu, tiếp tục" /
"Ngắt kết nối"; (2) banner cam cố định trên mọi màn hình chuyển động; (3) chạy model, phát lại, phát quỹ
đạo, chương trình dừng an toàn sau một giới hạn thời gian (600 s mặc định, kỹ sư đổi được trong Cài đặt; tên cài đặt do SA chốt) chạy
liên tục, lý do mới (tên đề xuất `thermal_blind`), đặt lại được ngay; teleop / ghi không giới hạn. Tay leader: không
bao giờ cảnh báo dòng / tải / trạng thái / điện áp, nhiệt tối đa mức "nóng", không bao giờ dừng robot
hay chặn phiên. Bảo vệ follower giữ nguyên. Traces BR-6, NFR-12, RULE-5, RULE-6. REG-3, REG-11, REG-13.

**FR-34 (F-34) Dừng vì điện.** Follower: điện áp dưới `Min_Voltage_Limit` + 0,5 V hoặc dưới 85 % điện
áp đo khi kết nối → cảnh báo; dưới tối thiểu hoặc cờ quá dòng ở **2 lần đọc liên tiếp** → dừng an toàn
như FR-32 với lý do `electrical`. Cờ quá tải của kẹp SO-101 chỉ là cảnh báo. Tải ≥ 90 % trong > 2 s →
cảnh báo "bị kẹt". Traces BR-5, BR-6. REG-16.

**FR-35 (F-35) Phục hồi sau dừng giữa chừng.** Station phải quên mọi mục tiêu của phiên trước ở mỗi
lần kết thúc và bắt đầu phiên. Sau khi một chuyển động bị e-stop và đã reset (`status.interrupted`):
banner "Tay robot đã dừng giữa chừng một chuyển động… Lần chạy chương trình hoặc quỹ đạo tiếp theo
sẽ bắt đầu lại từ đầu" + "Về tư thế nghỉ": một chuyển động minimum-jerk ≤ 30°/s, dead-man bật,
Space / "Dừng" huỷ. Chưa có tư thế nghỉ → "Hãy lưu tư thế nghỉ ở trang Robot…" (API từ chối). Lần chạy
sau luôn: về điểm đầu → chạy từ t = 0. Traces BR-5, RULE-7. REG-10.

**FR-36 (F-36) Thông báo và kết nối giao diện.** Banner nguy hiểm (đỏ, toàn chiều rộng, không ẩn
được tới khi hết), nóng (cam), ấm, lỗi kết nối ("Robot đã ngắt kết nối: <lý do>…"), đã dừng (lý do);
bong bóng Hibi cho cảnh báo kèm tên khớp và giá trị. Mất WebSocket với Station → "Đang kết nối lại…
các nút điều khiển tạm khoá. Model đang chạy sẽ tự dừng"; kết nối lại tự động, tải lại trạng thái.
Traces BR-5.

**FR-37 (F-37) Lịch sử phiên.** Trang Phiên liệt kê phiên (bắt đầu, loại, dataset / model, kết quả,
nhiệt độ cao nhất) và telemetry của mỗi phiên. Mỗi phiên lưu `session.json` + `telemetry.jsonl.gz`.
Lúc khởi động xoá phiên cũ hơn 30 ngày hoặc khi tổng vượt 2 GiB (cũ trước); chỉ kiểm lúc khởi động
(v0.2: SA-F5, chấp nhận như đã xây: Station chạy liên tục nhiều tuần có thể vượt 2 GiB tới lần khởi động
sau). Traces BR-6, BR-12.

### G. Ghi bộ dữ liệu

**FR-38 (F-38) Ghi dataset.** Form: dataset mới (tên chỉ gồm chữ, số, `_ . -`, sai → "Chỉ dùng chữ, số, _ . -"; trùng → "Đã có bộ dữ liệu
tên này. Hãy chọn ghi thêm") hoặc ghi thêm; nhiệm vụ; số tập; độ dài tập (30 s mặc định); đặt lại;
fps; mã hoá video; khi hết giờ: Lưu lại (mặc định) / Bỏ và ghi lại; ước lượng "Khoảng X MB mỗi tập với
N camera, tổng Y GiB". Chạy: tiêu đề pha ("Tập 4 / 20 · đang ghi · 12,4 / 30 giây", "Đặt lại cảnh",
"Đang lưu tập 4…"); Tiếp → / Ghi lại ← / Dừng Esc (nút và phím); khi lưu, vòng điều khiển vẫn giữ tay;
dải tập đã lưu với nhiệt độ cao nhất. Kết thúc: "Đã lưu N tập trong <đường dẫn>" + Tải lên / Ghi thêm.
Dataset là LeRobot v3 đúng như lerobot ghi (`finalize` luôn được gọi, kể cả khi dừng sớm hoặc e-stop).
Trong lúc ghi và lưu tập, trang Ghi và trang chi tiết dataset không bao giờ gây lỗi 5xx (v0.2: D-2): tập
đang lưu dở hiện "Đang lưu…".
Traces BR-7, RULE-14.

**FR-39 (F-39) Ghi thêm.** Ghi thêm vào dataset cục bộ có sẵn; kiểm tra tương thích (động cơ, camera,
fps) → `dataset_incompatible` nếu khác. Traces BR-7.

**FR-40 (F-40) Bộ dữ liệu.** Danh sách: tên, số tập, khung hình, fps, dung lượng, đã / chưa hoàn tất,
đã tải lên vX. Chi tiết: các tập, biểu đồ "Tập N: nhiệt độ tay follower (°C)" từ telemetry đi kèm
(`<tên>.hibiscus/telemetry/`, nằm cạnh thư mục LeRobot), "Tập này không có telemetry" khi thiếu, Phát
lại, Xoá (hộp "Xoá vĩnh viễn"; từ chối khi đang ghi / tải lên). Traces BR-7.

### H. Liên kết máy chủ Hibiscus

**FR-41 (F-41) Ghép nối.** Địa chỉ + token; "Tạo token với đúng quyền" mở trang token của máy chủ
với các quyền cần; Station kiểm tra token (`/auth/me`, danh sách workspace, quyền) và cất vào keyring
(hoặc tệp quyền 0600 với Docker); `GET /server` chỉ trả địa chỉ, workspace, tiền tố token, quyền. Lỗi:
máy chủ từ chối token, thiếu quyền (nêu quyền thiếu), không kết nối được. Huỷ ghép nối xoá token.
Traces BR-8.

**FR-42 (F-42) Tải lên.** Đích: dataset mới (tên điền sẵn) hoặc phiên bản mới của dataset trên máy chủ
(chọn từ danh sách). Dataset chưa hoàn tất → từ chối. Tiến độ: đang băm / đang tải lên (phần đã gửi,
MB/s) / đang kiểm tra / xong + "Mở trên máy chủ". Mất mạng hoặc khởi động lại Station → bấm Tải lên
lần nữa tiếp tục từ phần đã gửi. Chỉ gửi thư mục LeRobot (không gửi telemetry đi kèm). Huỷ được.
Traces BR-8.

**FR-43 (F-43) Huấn luyện.** Dataset đã tải lên; "Mở huấn luyện trên Hibiscus" mở thẻ mới ở trình tạo
lượt huấn luyện với phiên bản đã chọn; danh sách lượt (trạng thái, tiến độ) khi token có `runs:read`;
"Tải về và chạy" khi lượt đã xuất model. Traces BR-8, RULE-15.

**FR-44 (F-44) Kéo model.** "Từ máy chủ": danh sách model sẵn sàng; Tải về (tiếp tục được, kiểm tra
sha256 MANIFEST) → đăng ký model. Traces BR-8, BR-9.

### I. Chạy model

**FR-45 (F-45) Nhập model.** Zip gói Hibiscus (≤ 4 GiB, giải nén an toàn: không đường dẫn tuyệt đối,
`..`, symlink; tổng ≤ 20 GiB, tỉ lệ nén ≤ 200; kiểm MANIFEST → "đã xác minh") hoặc thư mục
`pretrained_model` ("chưa xác minh") từ đường dẫn trên máy (chỉ trong home, ổ khác trên Windows,
`/media`, `/mnt`; ngoài → `forbidden`). Sao chép vào kho model. Từ chối `*.bin` / `*.pt` pickle
(`unsafe_weights`). Tiến độ: giải nén / kiểm tra. Traces BR-9, RULE-16.

**FR-46 (F-46) Tương thích.** Khi chọn model: danh sách kiểm (số khớp = 6, kích thước lệnh = 6, mỗi
camera của policy có camera cấu hình tương ứng, độ phân giải khớp — không tự resize, loại robot (chỉ
cảnh báo), gói policy đã cài) với "ổn / có vấn đề"; sửa: "Đặt <camera> thành W×H" (sửa hồ sơ, mở lại
camera), chọn camera tương ứng khi tên khác. Kiểm lại khi bắt đầu chạy. Traces BR-9.

**FR-47 (F-47) Nạp model.** Thiết bị Tự động (CUDA → MPS → CPU) / CPU / CUDA / MPS; nạp + khởi động
(một lần suy luận trên quan sát 0) trong nền; "Đã nạp trên <thiết bị> trong X giây · khởi động Y ms";
một model tại một thời điểm; tự gỡ sau 10 phút không dùng. Không phiên nào chạy với model chưa nạp.
(v0.2: P-2, D-20, SA-N3) Lần suy luận khởi động > 500 ms (½ dead-man) trên máy đó → "Chạy trên robot" bị
tắt với "Model quá chậm trên máy này cho an toàn dead-man. Dùng CUDA hoặc model nhỏ hơn" (mã lỗi đề xuất `model_too_slow`).
(v0.2: D-23, SA-F4) Model cần tải thành phần từ HF Hub (SmolVLA, adapter PEFT) khi không có mạng → câu dịch
"Model này cần tải thành phần từ Internet ở lần nạp đầu", không lỗi thô.
Traces BR-9.

**FR-48 (F-48) Chạy model trên robot.** Thiết lập: nhiệm vụ (điền từ model), fps (từ huấn luyện), độ dài
tập, số tập, đặt lại, bước tối đa (FR-30), ghi dataset đánh giá. Lần đầu mỗi hồ sơ: xác nhận "e-stop
là phần mềm, không thay việc ngắt nguồn". Chạy: đếm ngược 3 s ("Space = dừng") → tập (≤ độ dài) → đặt
lại → tập tiếp; Tiếp / Dừng; mọi camera "đầu vào policy · 640×480 → 320×240" kèm tick khung hình và
tick trạng thái; mỗi khớp: đo được / lệnh / đã gửi + biểu đồ 10 s, nhịp bị cắt được đánh dấu; Bước,
FPS thật / mục tiêu, Suy luận p50 / p95, Vòng lặp p95, % bị cắt; sức khoẻ động cơ; Robot 3D. Suy luận
> 2 nhịp trong 5 s → tạm dừng "Model quá chậm cho fps này trên máy này. Hãy giảm fps hoặc dùng CUDA"
(không dồn lệnh cũ). Mỗi tập reset trạng thái policy. E-stop trong lúc suy luận: không lệnh mới nào được gửi; lệnh giữ được ghi
ngay khi lần suy luận đang chạy kết thúc (NFR-3a). Traces BR-9.

**FR-49 (F-49) Dataset đánh giá.** Bật "Ghi bộ dữ liệu đánh giá": cùng vòng ghi dataset `eval_<model>_<ngày>`
(sửa được tên) kèm telemetry. Traces BR-9.

**FR-50 (F-50) Tóm tắt.** Sau lượt chạy: thời lượng, số tập, số cảnh báo, nhiệt độ cao nhất từng khớp,
liên kết telemetry phiên và dataset đánh giá. Traces BR-9.

**FR-51 (F-51) Trang Model.** Danh sách model (tên, loại policy, nguồn gói / thư mục / máy chủ, xác
minh, đã nạp), Nhập, Chạy (mở Chạy model với model đã chọn), Xoá. Traces BR-9.

### J. Chương trình

**FR-52 (F-52) Ghi quỹ đạo.** Cần leader. Tên (gợi ý "Lượt 10:15"), giới hạn thời gian (60 s mặc định,
≤ 600 s); đếm ngược; "Đang ghi · X / Y s · N mẫu"; Dừng ghi; ghi lệnh follower sau lọc an toàn. Xem lại:
đồ thị khớp, vùng xám sẽ bị cắt, gợi ý tự động đoạn đứng yên đầu / cuối (mọi khớp đổi < 0,5° trong >
0,5 s), "Giữ X s trên Y s", Lưu / Bỏ. Danh sách: Nháp / Sẵn sàng / Cần kiểm tra, thời lượng, fps, tốc độ
đỉnh. Traces BR-10.

**FR-53 (F-53) Phát quỹ đạo.** Tốc độ 10–100 % (đến 150 % chỉ khi hồ sơ bật `allow_fast_replay`, ngược
lại `fast_replay_not_allowed`); xa điểm đầu > 3° → đi về điểm đầu trước (≤ 30°/s); mọi đường an toàn
của phát lại (bước tối đa, dải, dead-man, e-stop trong một nhịp, nhiệt). Sau hiệu chỉnh lại follower:
quỹ đạo và tư thế "Cần kiểm tra", không chạy được trên robot (`needs_check`) cho tới khi "Kiểm tra ở
25 %" rồi "Đã đúng". Traces BR-10, RULE-10.

**FR-54 (F-54) Tư thế.** Tên `a-z 0-9 _ -`; "Lưu tư thế hiện tại", "Lưu điểm đầu / cuối làm tư thế";
nguồn hiển thị; xoá. Theo từng hồ sơ robot. Traces BR-10.

**FR-55 (F-55) Nhận diện.** Màu trong vùng: vẽ vùng trên ảnh trực tiếp, quy tắc màu (HSV) theo nhãn;
ONNX: tải model, nhãn; thử trực tiếp (`/detectors/{id}/test`) hiện nhãn và độ tin cậy; bộ nhận diện
không dùng được → `detector_invalid` với lý do. Traces BR-10.

**FR-56 (F-56) Trình soạn khối.** "Chương trình mới" luôn mở form và đặt con trỏ vào ô tên (kể cả khi
form đã mở, danh sách trống, đang tải hay lỗi); tên không có chữ Latin / số vẫn nhận mã ổn định
`program_<hash>`; form nói chương trình lưu cho hồ sơ nào, và báo khi chưa có hồ sơ hoạt động; danh
sách lỗi → lỗi + "Thử lại"; lỗi không phải của Station vẫn hiện mã HTTP. Khối: khi bắt đầu, phát quỹ
đạo ở %, đi tới tư thế ở °/s, kẹp, về vị trí nghỉ, thả lỏng tay, chạy mô hình (FR-60), lặp mãi, chờ,
chờ đến khi, dừng chương trình, camera thấy, độ tin cậy, nút được bấm, phím được bấm, hỏi người vận
hành, kẹp đang giữ vật, so sánh khớp, vị trí khớp, gần tư thế, nhiệt độ động cơ, tín hiệu, nhận tin,
ghi nhật ký, thông báo (FR-59), đặt tín hiệu (FR-59). Lưu tạo phiên bản mới; "Kiểm tra" đánh dấu khối
lỗi (`program_invalid`) với lý do. Tối đa 2000 khối. Traces BR-10. REG-9.

**FR-57 (F-57) Chạy thử.** "Chạy thử" chạy trên tay giả lập (không đụng tay thật, chạy được cả khi
robot bận); bảng "giả lập điều kiện" (camera thấy gì, kẹp giữ vật); kết quả lưu theo phiên bản. "Chạy
trên robot" bị chặn ("Chạy trên robot cần phiên bản này đã chạy thử thành công", `dry_run_required`)
cho tới khi phiên bản đó chạy thử thành công (RULE-9). Traces BR-10, BR-5.

**FR-58 (F-58) Chạy trên robot.** Cần Sẵn sàng, không e-stop ("Robot đang dừng khẩn cấp: cần đặt lại
trước"), không chương trình khác đang chạy. Hộp "Xác nhận trước khi chạy" cho các khối cần đồng ý.
Tạm dừng / Tiếp tục / Dừng chương trình; trạng thái "t s · N bước · <khối>", đang chờ (chờ / điều kiện /
người vận hành / di chuyển / mô hình) với "hết giờ sau X s"; bảng người vận hành (nút, phím, câu hỏi);
biến; giá trị điều kiện gần nhất; nhật ký; các lần chạy gần đây. E-stop / nhiệt / dead-man dừng trong
một nhịp, lần chạy kết thúc `estopped`; lần sau bắt đầu lại từ đầu (FR-35). Danh sách / đọc chương trình
không phụ thuộc trạng thái phần cứng (trả lời khi robot bận / e-stop / lỗi). Traces BR-10, BR-5. REG-9,
REG-10.

**FR-59 (F-59) Tín hiệu ngoài.** `POST /api/v1/signals/<tên>` (cần token) đặt giá trị; `GET /signals`;
MQTT khi cấu hình `programs.mqtt_url` và topic; khối "thông báo" POST tới webhook đã cấu hình; khối
"đặt tín hiệu". Traces BR-10, BR-11.

**FR-60 (F-60) Chạy model trong chương trình.** Khối chạy model đã nạp với nhiệm vụ trong X s, hoặc tới
khi điều kiện đúng (có hết giờ), với mọi an toàn của FR-48. Traces BR-10.

### K. Robot 3D

**FR-61 (F-61) Robot 3D.** Vẽ SO-101 follower theo vị trí khớp trực tiếp (≥ 10 Hz cập nhật), động cơ tô
màu theo mức nhiệt (xanh / vàng / cam / đỏ; "chưa có số đo" khi không rõ); chú thích "Màu động cơ cho
biết nhiệt độ"; nhãn "Tay thật" / "Tay giả lập"; kéo xoay, cuộn / chụm phóng to, "Đặt lại góc nhìn",
"Ẩn / Hiện Robot 3D"; chưa có dữ liệu khớp → tư thế nghỉ với ghi chú; không WebGL → ẩn với lời giải
thích; ghi công mô hình TheRobotStudio (Apache-2.0). Chỉ hiển thị, không điều khiển. Traces BR-6.

**FR-62 (F-62) Xem trước bằng tay mờ.** "Xem 3D" ở một quỹ đạo: tay mờ chạy quỹ đạo (Phát / Tạm dừng /
kéo vị trí, "t / tổng giây") cạnh tay đặc (robot lúc này); cùng chiều và thứ tự khớp như khi phát thật.
Traces BR-10.

### L. Chẩn đoán

**FR-63 (F-63) Doctor.** `hibiscus-station doctor` phải chạy được khi Station đang tắt hoặc đang chạy,
không bao giờ ghi gì xuống động cơ; thu thập như F-63; mở đầu bằng "LIKELY PROBLEMS" khi có vấn đề, khi không có thì dòng "No likely problems found" (v0.2:
FL-11); ví dụ "MOCK PROFILE ACTIVE … real serial ports present: COM3"; bộ chuyển USB chậm: với bộ chuyển
WCH CH340 / CH343 nói "slow USB adapter / hub: plug the arm straight into the PC", chỉ nói "latency timer
1 ms" với chip FTDI (v0.2: D-21); cổng bị chương trình khác giữ vào LIKELY PROBLEMS; `station.pid` còn mà
Station không trả lời → "Station is not running" (v0.2: D-15); tạo
`hibiscus-station-doctor-<thời gian>.zip` trong `--out` (mặc định thư mục hiện tại) không chứa token;
phần kiểm tra từng tay ghi **giá trị thô** của các thanh ghi đọc được (vị trí, homing, giới hạn vị trí, điện áp và giới hạn điện áp, nhiệt độ, `Max_Temperature_Limit`, `Status`, mô-men, khoá, return delay, chế độ) — (v0.2: K-11, SP-1) thêm `Present_Current`, `Present_Load`, và bản dump thô từng servo bằng lệnh `read`
**riêng lẻ** (không `sync_read`) của khối thanh ghi 56–70 và 0–3 (firmware, model); `--verbose` in mọi lỗi bus (id động cơ, thanh ghi);
`--no-ping` không mở cổng; `--no-cameras` không dò camera. Lệnh này là **lệnh hỗ trợ** chép-dán từ hướng
dẫn tiếng Việt (cùng loại với lệnh cài, FL-5); đầu ra tiếng Anh (cho vendor, NFR-10). Traces BR-12. REG-2,
REG-13.

**FR-64 (F-64) Nhật ký.** `station.log` UTF-8, xoay vòng 10 MiB × 5; dòng khởi động: chế độ (giả lập /
phần cứng thật), thư mục dữ liệu, hồ sơ hoạt động và loại thiết bị; mọi lệnh bus lỗi (thao tác, thanh
ghi, id, lỗi); `-v` in ra màn hình; không in dòng thời gian mỗi nhịp của lerobot. Console Windows không
lỗi với tiếng Việt (UTF-8 khi chuyển hướng). Xoay vòng thất bại trên Windows (tệp đang bị chương trình
khác mở) → tiếp tục ghi tệp cũ, không mất log (v0.2: SA-W6). Traces BR-12. REG-18.

**FR-65 (F-65) Health.** `hibiscus-station health` thoát 0 khi bản đang chạy trả lời `GET /status` bằng
token của chính nó trong `--timeout` (5 s), khác 0 nếu không. Traces BR-12.

### M. Cài đặt, ngôn ngữ, giao diện

**FR-66 (F-66) Cài đặt.** Ngưỡng nhiệt ấm / nóng / nguy hiểm với RULE-4, lỗi bằng lời ("Ngưỡng nguy hiểm
phải thấp hơn ngưỡng tự ngắt của động cơ (70 °C) ít nhất 3 °C"…), API trả 422 cho cấu hình sai; tần suất
đọc (nhiệt / trạng thái, điện áp / dòng / tải); xem trước camera (rộng 160–640 px, fps ≤ 30); dead-man
cho phát lại; thư mục dữ liệu; máy chủ (huỷ ghép nối); "Station X · lerobot Y · thiết bị Z" (lerobot là
phiên bản thực đã cài). Lưu → "Đã lưu." Traces BR-11.

**FR-67 (F-67) Song ngữ.** Mọi chuỗi giao diện có ở `vi` và `en` (cùng bộ khoá); ngôn ngữ mặc định theo
trình duyệt: `en*` → English, còn lại → Tiếng Việt; nút đổi ngôn ngữ trên thanh trên đổi ngay không tải
lại; `lang` của trang theo ngôn ngữ. Mã lỗi của Station hiện bằng ngôn ngữ đã chọn. Traces BR-14,
NFR-10.

**FR-68 (F-68) Giao diện.** Hệ thiết kế pixel Hibiscus; chủ đề ngày / đêm theo hệ thống, đổi được;
bố cục ≥ 1280 px và ~390 px (điện thoại: xếp dọc camera → sức khoẻ → khớp); "Bỏ qua, tới nội dung"; mọi
điều khiển có nhãn; Hibi đổi tâm trạng (sẵn sàng / làm việc / buồn khi dừng / lỗi / nóng / ngủ khi chưa
kết nối). Traces BR-14, NFR-11.

### N. Cập nhật và dữ liệu

**FR-69 (F-69) Cập nhật wheel.** (v0.2: P-1, QĐ-3) Chạy lại **đúng lệnh cài một dòng** của FR-1 (bản mới
nhất), hoặc cùng lệnh kèm số phiên bản để quay lại (ví dụ `-Version 1.0.0`), phải thay Station mà giữ nguyên `~/.hibiscus/station` (hồ sơ, cài đặt,
dataset, model, phiên, quỹ đạo, tư thế, bộ nhận diện, chương trình) và thư mục hiệu chỉnh lerobot; cài
lại bản cũ cũng vậy (quay lại, ra **đúng** bộ thư viện của bản cũ). Bản mới đọc được dữ liệu của bản cũ
(0.2.x). Traces BR-15. QĐ-3.

**FR-70 (F-70) Docker backup / update / rollback.** `backup [--full]` (mặc định không gồm dataset và
model) → tarball; `restore FILE`; `update [TAG]`: sao lưu, kéo, khởi động lại, kiểm sức khoẻ, tự quay lại
khi không khoẻ; `rollback` về tag trước. Traces BR-15.

**FR-71 (F-71) Dữ liệu bền.** Ghi tệp cấu hình nguyên tử (tệp tạm + thay thế, thử lại khi Windows khoá
tệp), UTF-8, quyền 0600 cho tệp nhạy cảm; dataset đúng như lerobot ghi, telemetry đi kèm nằm cạnh;
`--mock` không ghi vào thư mục dữ liệu thật. Traces BR-15.

### Yêu cầu chung

**FR-72 Một phiên chuyển động.** Station phải chỉ chạy một phiên chuyển động tại một lúc; bắt đầu khi
không Sẵn sàng → `409 busy` với trạng thái hiện tại, giao diện "Station đang bận (<trạng thái>)".
Rời mọi phiên đi qua "Đang dừng" (≤ 10 s), sau đó follower được giữ hoặc về nghỉ rồi thả lỏng theo hồ sơ.
Traces RULE-1.

**FR-73 Lỗi có nghĩa.** Mọi lỗi API là Problem (RFC 9457) có `code` ổn định; giao diện hiện câu dịch theo
`code` (danh sách `errors.*`) và có đường thoát (thử lại, tới bước cần làm, kết nối lại, đặt lại). Không
hiện stack trace, `internal_error` thô hay chuỗi debug. (v0.2: P-5, FL-1, D-5) Chi tiết kỹ thuật
(lý do thô, tiếng Anh, đường dẫn) chỉ nằm trong mục "Chi tiết kỹ thuật" thu gọn, đóng mặc định, không bao
giờ là một dòng hiện sẵn dưới câu dịch; câu dịch có đủ đơn vị (°, %, V). Yêu cầu sai định dạng (ví dụ body
không phải JSON) → 4xx có `code`, không bao giờ 500 (D-16). Traces BR-1, BR-6.

**FR-74 Không ngõ cụt.** Ở mọi trạng thái (`disconnected`, `connecting`, `idle`, `calibrating`,
`teleop`, `recording`, `replaying`, `inferring`, `recording_traj`, `playing`, `programming`, `rest`,
`stopping`, `estopped`, `error`) giao diện phải chỉ ra ít nhất một hành động đưa người dùng về
`idle` hoặc `disconnected` (xem §7). Tải lại trang giữa chừng phải khôi phục đúng trạng thái từ Station.
Traces BR-5.

**FR-75 Hành vi khi tắt.** Dừng Station (Ctrl+C, `docker stop`, tắt dịch vụ) khi tay đang chuyển động
phải: dừng phiên, giữ / về nghỉ, tắt mô-men theo hồ sơ, đóng dataset (finalize), giải phóng cổng và camera.
(v0.2: P-6, D-19, SA-W3) **Đóng cửa sổ console, đăng xuất, tắt máy trên Windows**: Station bắt sự kiện của
Windows và chạy đường dừng **rút gọn** trong ≤ 4 s: e-stop giữ → tắt mô-men theo hồ sơ (bỏ bước về tư thế
nghỉ) → `finalize` dataset nếu kịp. Ngoại lệ đã biết: đóng cửa sổ khi đang ghi thì tập **đang ghi dở** có
thể bị bỏ; các tập đã lưu còn nguyên và dataset mở được. Lần khởi động sau không bị "cổng bận" do khoá cũ.
Traces BR-5, BR-15.

**FR-76 Phiên bản thống nhất.** Phiên bản Station hiện giống nhau ở `--version`, Cài đặt, `doctor`,
README, hướng dẫn, ghi chú phát hành, tên wheel và tag image. Traces BR-13.

## 4. Yêu cầu phi chức năng (đo được)

v0.2: NFR-1, NFR-3 tách thành phần **vendor đo** (giả lập / test tự động) và phần **UAT** (khách quan sát,
không cần dụng cụ đo); video quay chậm bằng điện thoại là tuỳ chọn, không bắt buộc (SA-N1, SA-N3, FL-2,
FL-3). "≤ 3 ms mỗi lần đọc bus" = số `doctor` đo trên PC đó.

| ID | Loại | Yêu cầu | Cách đo | Đích | AT |
|---|---|---|---|---|---|
| NFR-1a | Hiệu năng teleop (vendor) | Trễ bám: từ khi leader tới một vị trí tới khi follower tới vị trí đó, trên giả lập STS3215 có thời gian thật (1 Mbaud, servo ~300°/s) | `tests/teleop_bench.py`, adapter 1 ms và 8 ms, cử động chậm và nhanh; so với vòng tham chiếu kiểu LeLab chạy trong cùng bench | p50 ≤ 70 ms, p95 ≤ 100 ms, và ≤ tham chiếu LeLab + 10 ms ở **cả** 1 ms và 8 ms (hôm nay 8 ms không đạt: D-9) | AT-31 |
| NFR-1b | Hiệu năng teleop (mọi máy) | Độ trễ **phần mềm** Station hiển thị ("độ trễ ~X ms": đọc leader → gửi lệnh follower) | Tóm tắt phiên `latency_ms_p50` / `_p95`, teleop 2 phút | p50 ≤ 15 ms, p95 ≤ 30 ms khi bus ≤ 3 ms mỗi lần đọc | AT-31, AT-89 |
| NFR-1c | Hiệu năng teleop (UAT) | Cảm nhận so với LeLab | Khách teleop lần lượt LeLab và Station trên cùng PC, cùng tay, cùng động tác, 2 phút mỗi bên | Khách đánh giá "không chậm hơn LeLab" | AT-31 |
| NFR-2 | Hiệu năng (nhịp) | (a) Teleop: báo Hz đạt được (vòng teleop chạy nhanh nhất bus cho phép nên không tính "nhịp trễ"); (b) vòng cố định 30 Hz (ghi, chạy model) | Tóm tắt phiên `loop.fps`, p95 thời gian nhịp, tỉ lệ nhịp trễ, `telemetry_forced` | (a) ≥ 100 Hz khi bus ≤ 3 ms mỗi lần đọc; bus chậm hơn: ≥ vòng tham chiếu LeLab trên cùng bench và không cảnh báo "không theo kịp" khi cử động bình thường; đích cuối cho Windows + CH34x chốt sau số đo UAT-0 (SP-4); (b) p95 ≤ 36 ms, nhịp trễ < 1 %, `telemetry_forced` < 1 % | AT-31, AT-89 |
| NFR-3a | An toàn e-stop (vendor) | Từ lúc Station nhận e-stop tới khi không còn lệnh vị trí mới | Test tự động đếm lệnh ghi bus (giả lập pty, log lệnh của `sts_emulator`) | ≤ 1 nhịp cho teleop / ghi / phát lại / quỹ đạo / chương trình / về nghỉ / căn tay; ≤ 1 nhịp + 1 lần suy luận khi chạy model | AT-36, AT-88 |
| NFR-3b | An toàn e-stop (vendor, e2e) | Từ phím Space trong trình duyệt tới khi máy chủ nhận e-stop | Playwright, 100 lần bấm, dấu thời gian trình duyệt và log máy chủ | p99 ≤ 50 ms | AT-88 |
| NFR-3c | An toàn e-stop (UAT) | Tay dừng khi bấm Space / nút DỪNG | Khách quan sát (video quay chậm điện thoại tuỳ chọn) | Tay dừng "ngay", giữ mô-men, không rơi, 10 / 10 lần | AT-36 |
| NFR-4 | An toàn (dead-man) | Từ khi giao diện mất tới e-stop | Đóng tab khi chạy model / phát lại / chương trình / về nghỉ | ≤ 1,0 s + 1 nhịp (+ 1 lần suy luận khi chạy model); model có suy luận khởi động > 500 ms bị từ chối chạy (P-2) | AT-38, AT-97 |
| NFR-5 | Khởi động | Từ lệnh `hibiscus-station` tới khi trang tải xong, **từ lần chạy thứ hai**, không camera (lần đầu sau cài có thể chậm 1–2 phút vì tải torch và Windows Defender quét tệp; hướng dẫn nói rõ, SA-W5) | Đồng hồ / dấu thời gian log | ≤ 15 s trên PC Windows của khách; ≤ 10 s trên Linux x86_64 của vendor; kết nối hồ sơ ≤ 5 s (không camera). Mở camera trên Windows (MSMF): không có đích ở v1.0, ghi số đo trong UAT (SA-W4) | AT-87 |
| NFR-6 | An toàn nhiệt | Thời gian dừng an toàn nhiệt (từ mẫu nguy hiểm thứ hai tới tắt mô-men), **trên servo báo nhiệt thật** | Giả lập (vendor); tay của khách với ngưỡng hạ nếu servo báo nhiệt | ≤ 2 s. Servo không báo nhiệt: AT-42 "không áp dụng" có chữ ký khách, hành vi theo QĐ-1 (AT-93) | AT-42, AT-93 |
| NFR-7 | Phục hồi | Sau mọi lần dừng (e-stop, nhiệt, dead-man, mất camera, mất USB, mất nguồn follower, đóng cửa sổ, mất mạng khi tải lên, tải lại trang) có đường về Sẵn sàng hoặc Chưa kết nối không cần khởi động lại Station (đóng cửa sổ: mở lại Station); lần chạy sau bắt đầu từ đầu | ATs phục hồi | 100 % | AT-19, AT-37, AT-45, AT-54, AT-72, AT-94, AT-95 |
| NFR-8 | Bền | Phiên dài không suy giảm | Teleop 30 phút + ghi 20 tập liên tục (job `slow` hằng đêm) | Bộ nhớ tăng ≤ 20 %, không treo, fps giảm ≤ 10 % | AT-90 |
| NFR-9 | Nền tảng | (v0.2: QĐ-2 phương án A) Nền tảng thuộc nghiệm thu v1.0 | — | **Windows 10 22H2 / 11 x64** (wheel, Python 3.12) — Must, UAT của khách; **Ubuntu 22.04 / 24.04 x86_64** (wheel) — Should, vendor; **Docker Linux x86_64 `-cpu`** — Could, vendor. Bản xem trước, ngoài nghiệm thu (W-9): macOS, wheel Linux arm64, Docker `-cuda`, Raspberry Pi 5, Jetson Orin. Trình duyệt: Edge 120+ (e2e trên CI Windows), Chrome 120+, Firefox 120+ (e2e trên Linux) (SA-C2) | AT-1 – AT-4 |
| NFR-10 | Ngôn ngữ | (v0.2: SA-U1) Phạm vi: **giao diện web và hướng dẫn tiếng Việt**, cùng các dòng CLI người mới chắc chắn thấy (khởi động, liên kết đăng nhập, cổng bận, đã có bản đang chạy) bằng tiếng Việt hoặc song ngữ. Ngoài phạm vi (tiếng Anh, cho kỹ sư / vendor): `doctor`, log, đầu ra của uv, mục "Chi tiết kỹ thuật" thu gọn. Tiếng Việt (mặc định) và English đầy đủ, không lẫn ngôn ngữ, không lỗi chính tả, một thuật ngữ cho một khái niệm | Kiểm chuỗi tự động (khoá `vi` = `en`, cấm "Hiệu chuẩn", không chuỗi `detail` tiếng Anh hiện sẵn ở chế độ `vi`) + ma trận ảnh | 0 chuỗi thiếu; 0 câu tiếng Anh trong phạm vi ngoài thuật ngữ đã thống nhất (teleop, follower, leader, e-stop, fps, policy, tên khớp, mã lỗi) | AT-81, AT-91 |
| NFR-11 | Khả dụng / a11y | (v0.2: SA-U2, FL-7) Bàn phím đi hết **luồng chính** (robot → hiệu chỉnh → camera → teleop → ghi → chạy model → e-stop → đặt lại); trình soạn khối Blockly được miễn yêu cầu bàn phím (chạy / dừng chương trình vẫn dùng được bằng bàn phím); focus thấy rõ; điều khiển có nhãn; tương phản WCAG AA ở hai chủ đề; ở 390 px **trang** không cuộn ngang (bảng rộng và canvas cuộn ngang trong khung riêng); trình soạn khối trên điện thoại: xem và chạy | Ma trận ảnh Playwright tự động (mọi trang × trạng thái × sáng / tối × 1280 / 390) + axe trong CI; QC xem tay mẫu cố định; đi bằng bàn phím | 0 lỗi | AT-82, AT-83 |
| NFR-12 | Thông tin đúng | Mọi số hiển thị có đơn vị đúng và nằm trong dải hợp lý (RULE-5); không placeholder, không debug | Rà màn hình với tay giả lập + tay thật | 0 vi phạm; 0 cảnh báo giả trong 30 phút teleop trên tay khách | AT-43, AT-92 |
| NFR-13 | Độ chính xác telemetry | (v0.2: SA-N4, FL-4) So với **công cụ Feetech FD** chính hãng trên cùng servo, cùng lúc (không cần nhiệt kế / đồng hồ vạn năng) | Ảnh chụp FD và Station cạnh nhau: nguội (để yên 30 phút) và sau 10 phút teleop | Nhiệt ±3 °C, điện áp ±0,2 V; khi có tải nhiệt tăng đều, không nhảy; dòng: ±20 % nếu SP-1 xác nhận đơn vị, nếu không: "—" ở mọi nơi (P-8). Servo không báo nhiệt: ô hiện "—" (RULE-5) | AT-40 |
| NFR-14 | Bảo mật / pháp lý | Chỉ cục bộ, token mỗi lần chạy, không lộ token máy chủ, che token trong log, zip an toàn, không pickle; (v0.2: SA-L1) mọi gói phân phối cùng Station có giấy phép tương thích AGPL (QĐ-4); mỗi cảnh báo bảo mật bị bỏ qua có lý do ghi lại | Test + rà soát bảo mật + bảng giấy phép từ metadata gói đã cài | 0 phát hiện mở; 0 gói không tương thích; 0 GHSA bỏ qua không lý do | AT-8, AT-57, AT-98 |
| NFR-15 | Dữ liệu | Dataset mở được bằng lerobot 0.7.1 (`fe1c545`); không tệp lạ trong thư mục LeRobot; phiên lưu 30 ngày / 2 GiB (kiểm lúc khởi động); (v0.2: SA-F3) tệp hiệu chỉnh và dataset dùng được với LeLab đang cài trên PC của khách (phiên bản lerobot ghi lại) | Script kiểm (vendor); UAT với LeLab của khách | 100 % | AT-27, AT-47, AT-49, AT-86 |
| NFR-16 | Ngoại tuyến | Mọi chức năng trừ ghép nối / tải lên / huấn luyện / kéo model chạy không cần Internet; (v0.2: SA-F4) ngoại lệ: model cần backbone từ HF Hub (SmolVLA, adapter PEFT) cần Internet ở lần nạp đầu và báo bằng câu dịch | Chạy không mạng | 100 % | AT-86 |
| NFR-17 | Tải lên | Tiếp tục sau mất mạng không gửi lại phần đã gửi | Dừng máy chủ thử giữa chừng | Phần đã xác nhận không gửi lại | AT-54 |
| NFR-18 | Chất lượng mã / CI | (v0.2: SA-C1, SA-C2, D-1) Lint, kiểu, toàn bộ test xanh trên CI Linux / Windows / macOS cho đúng commit phát hành, gồm e2e (Chromium Linux, Firefox Linux, Edge Windows); test bỏ qua theo nền tảng **chỉ** những test trong danh sách công bố (tên test, nền tảng, lý do, AT / UAT phủ thay), hôm nay: test giả lập pty trên Windows (`test_calib_simple.py`, `test_real_stack.py`, `test_teleop_latency.py`, phần POSIX của `test_device_lost.py`) phủ thay bởi UAT-1 cho tới khi SP-2 chạy được chúng trên cổng COM ảo | CI + danh sách bỏ qua trong repo | Xanh; 0 test bỏ qua ngoài danh sách | AT-2 |

## 5. Giao diện

### 5.1 Màn hình (địa chỉ)
`/` Chào mừng · `/robot` Robot · `/calibrate` Hiệu chỉnh · `/cameras` Camera · `/teleop` Điều khiển tay ·
`/record` Ghi dữ liệu · `/replay` Phát lại · `/upload` Tải lên · `/datasets`, `/datasets/:name` Bộ dữ
liệu · `/train` Huấn luyện · `/run` Chạy model · `/programs` Chương trình (thẻ Quỹ đạo, Nhận diện,
Chương trình) · `/models` Model · `/sessions` Phiên · `/settings` Cài đặt · địa chỉ khác → Chào mừng.
Thành phần chung: thanh trên (logo, chip robot, chip sức khoẻ, chip máy chủ / ngoại tuyến, chip TAY GIẢ
LẬP, ngôn ngữ, chủ đề), thanh bước, nút e-stop, banner, Hibi, ngăn sức khoẻ, Robot 3D.

### 5.2 API
REST `/api/v1` (86 thao tác trong `openapi.json`, cộng `POST /mock/inject` chỉ với `--mock`), WebSocket điều khiển `/api/v1/ws`, video `/api/v1/ws/video`.
Chi tiết hợp đồng thuộc ARCHITECTURE.md / `docs/spec/station.md` §5.

### 5.3 Phần cứng
SO-100 / SO-101 follower + leader, servo Feetech STS3215 (6 mỗi tay, id 1–6, 1 Mbaud), bộ chuyển USB
serial WCH CH340 / CH343; camera UVC (OpenCV), Intel RealSense (tuỳ chọn); GPU NVIDIA / Apple MPS tuỳ
chọn.

### 5.4 Hệ thống ngoài
Máy chủ Hibiscus API v0.1.1 (`/api/v1`: auth/me, workspace, dataset upload theo phần, model pull, runs);
MQTT broker (tuỳ chọn); webhook (tuỳ chọn); lerobot / LeLab qua tệp hiệu chỉnh dùng chung.

## 6. Dữ liệu

| Thực thể | Nơi lưu (nguồn sự thật) | Ghi chú |
|---|---|---|
| Cài đặt | `~/.hibiscus/station/settings.yaml` | Windows: `%USERPROFILE%\.hibiscus\station` |
| Hồ sơ robot | `robots.yaml` (+ hồ sơ hoạt động) | demo: `~/.hibiscus/station-demo` |
| Hiệu chỉnh | `<HF_LEROBOT_CALIBRATION>/robots/so_follower/<id>.json`, `.../teleoperators/so_leader/<id>.json` | Dùng chung với lerobot / LeLab; cũng đọc thư mục cũ |
| Dataset | `datasets/<tên>/` (LeRobot v3) + `datasets/<tên>.hibiscus/` (dataset.json, telemetry/episode_*.jsonl.gz) | Telemetry không tải lên |
| Model | `models/index.json` + `models/<key>/` | |
| Phiên | `sessions/<id>/{session.json, telemetry.jsonl.gz}` | 30 ngày / 2 GiB |
| Quỹ đạo, tư thế, bộ nhận diện, chương trình, lần chạy | `robots/<id>/…` | Theo hồ sơ |
| Token cục bộ | `token` (0600, mới mỗi lần chạy) | |
| Token máy chủ | keyring hệ thống (Docker: `hibiscus-cli/credentials.json` 0600) | Không bao giờ tới trình duyệt |
| Nhật ký | `logs/station.log` | 10 MiB × 5 |

Di chuyển dữ liệu: v1.0 phải đọc được mọi dữ liệu của 0.2.x (FR-69); không có định dạng mới trong v1.0.

## 7. Trạng thái và luồng (gồm dừng / lỗi / phục hồi)

| Trạng thái | Nghĩa | Lối ra người dùng thấy |
|---|---|---|
| `disconnected` | Chưa kết nối | Kết nối |
| `connecting` | Đang mở cổng / bắt tay / cấu hình | Tự sang `idle` hoặc `error` |
| `idle` | Sẵn sàng | Bắt đầu phiên, hiệu chỉnh, mô-men, ngắt kết nối |
| `calibrating` | Hiệu chỉnh một tay | Lưu, Huỷ, e-stop |
| `teleop` / `recording` / `replaying` / `inferring` | Phiên chuyển động | Dừng, Tiếp / Ghi lại (ghi, model), e-stop |
| `recording_traj` / `playing` / `programming` | Quỹ đạo / chương trình | Dừng, Tạm dừng / Tiếp tục (chương trình), e-stop |
| `rest` (`playing`) / căn tay (`teleop.align`) | Về nghỉ / căn tay | Dừng, e-stop |
| `stopping` | Kết thúc phiên (≤ 10 s) | Tự sang `idle` |
| `estopped` | Đã dừng (lý do: user, thermal, electrical, ui_lost, camera_lost; v0.2 đề xuất thêm thermal_blind, P-3) | Đặt lại (khi đủ nguội), Thả lỏng, ngắt kết nối; sau đặt lại: "Về tư thế nghỉ" nếu bị dừng giữa chừng |
| `error` | Mất bus / thiết bị (`bus_lost`, `device_lost`) | Kết nối lại (chờ cổng), ngắt kết nối |

Luồng phục hồi bắt buộc (mỗi luồng có AT):
1. E-stop giữa bất kỳ chuyển động → `estopped` → Đặt lại → (Về tư thế nghỉ) → `idle` → chạy lại từ đầu
   (AT-37, AT-45, AT-72).
2. Nhiệt nguy hiểm → dừng an toàn → `estopped(thermal)` → nguội dưới "nóng" → Đặt lại (AT-42).
3. Mất giao diện → `estopped(ui_lost)` → mở lại trang → Đặt lại (AT-38).
4. Mất camera → phiên dừng `camera_lost`, dataset hợp lệ → `idle` (AT-30).
5. Rút USB → `error(device_lost)` → cắm lại → Kết nối lại (AT-18, AT-19).
6. Mất mạng khi tải lên → lỗi công việc → Tải lên lại tiếp tục (AT-54).
7. Tải lại trang / mất WebSocket → "Đang kết nối lại…" → trạng thái khôi phục (AT-46).
8. Leader xa → từ chối → Căn tay → teleop (AT-33).
9. Sai thứ tự bước (mở bước bị khoá) → trang khoá với lý do và liên kết (AT-10).
10. Mất nguồn follower giữa chuyển động → lỗi bus rõ ràng, không treo → bật nguồn → Kết nối lại (AT-94).
11. Đóng cửa sổ console trên Windows → dừng rút gọn ≤ 4 s → mở lại Station, không "cổng bận" (AT-95).
12. Không đọc được nhiệt độ → xác nhận khi kết nối → phiên không người cầm leader dừng sau 10 phút → đặt lại (AT-93).

## 8. Khoảng trống phát hiện ở vòng 1 (so với chuẩn chất lượng)

Các điểm dưới đây là **lỗi so với chuẩn chất lượng** trong bản 0.2.8 (không phải yêu cầu mới); chúng
phải được sửa (hoặc khách hàng miễn bằng văn bản theo mã) trước khi phát hành v1.0. v0.2: K-n đã được Tech
Lead xác nhận bằng chạy thử mang mã lỗi D-n; danh sách lỗi đầy đủ (D-1 – D-23) ở
[FEATURES.md](FEATURES.md#lỗi-đã-biết-d-n).

| ID | Chỗ | Vấn đề | Yêu cầu liên quan | v0.2 |
|---|---|---|---|---|
| K-1 | README / README.vi (bảng Docker), `docs/deploy.md` | Tag image và wheel ghi `0.2.1` trong khi sản phẩm là `0.2.8` | FR-76 | = **D-18** (xác nhận) |
| K-2 | `docs/user-guide/{vi,en}/station-hardware-uat.md` mục 1.6, 3.8 | Còn ghi `wrist_roll` "xoay tròn đủ vòng" (trái với 0.2.4+) và `error (bus_lost)` (nay là `device_lost`) | FR-17, FR-13 | mở, M1 (tài liệu UAT được thay bằng "Kế hoạch UAT" của ACCEPTANCE) |
| K-3 | Chuỗi giao diện tiếng Việt | Lẫn "Hiệu chỉnh" và "Hiệu chuẩn" cho cùng khái niệm | NFR-10, Q-8 | = **D-12** (6 chuỗi) |
| K-4 | Thông báo lỗi | Chi tiết lỗi của máy chủ (tiếng Anh, chữ máy) hiện dưới câu tiếng Việt cho mọi lỗi | FR-73, NFR-10 | = **D-5**; sửa theo P-5 |
| K-5 | `docs/user-guide/vi/station.md` §An toàn | "Mỗi bước chuyển động bị giới hạn … mặc định 5 độ" (teleop nay 30°) | FR-30 | mở, M1 |
| K-6 | `CHANGELOG.md` sản phẩm | Liên kết so sánh dừng ở 0.2.2 | FR-76 | = **D-18** |
| K-7 | `docs/spec/station.md` §6.3, §4.7 | Còn mô tả `wrist_roll` full-turn và teleop 30 Hz (tài liệu dev, lỗi thời) | — | mở (SA cập nhật) |
| K-8 | Cập nhật trên Windows | Người mới phải gõ lệnh có số phiên bản (trái BR-1) | FR-69 | giải quyết bằng P-1 nếu QĐ-3 = A |
| K-9 | Telemetry trên tay của khách | Servo báo 0 °C và dòng ~1000 thô: chưa rõ nguyên nhân | REG-13, QĐ-1 | mở, SP-1 / UAT-0 |
| K-10 | Docker trên Windows | Không hỗ trợ (đã ghi trong README); hướng dẫn tiếng Việt phải nói rõ người dùng Windows dùng wheel | NFR-9 | mở, M1 |
| K-11 | `hibiscus-station doctor` | Không đọc `Present_Current`, `Present_Load`, không dump thô, chỉ `sync_read` | FR-63, REG-13 | xác nhận (trong D-15), M0 |
