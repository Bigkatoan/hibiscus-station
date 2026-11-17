# Hibiscus Station: rà soát yêu cầu của SA · vòng 1 (2026-11-17)

Người rà soát: SA (độc lập với Tech Lead). Đầu vào: BRD / SRS / FEATURES / ACCEPTANCE / REGRESSION v0.1 của
BA, mã nguồn `main` `12f36da` (0.2.8), `uv.lock`, `web/package.json`, `.github/workflows/`. Kiến trúc và
tình trạng từng NFR: [ARCHITECTURE.md](ARCHITECTURE.md) §6. Tài liệu này **không** sửa tệp của BA; BA đưa
các đề xuất vào bản v0.2 (bước Reconcile) và hỏi khách hàng những mục ghi "Khách quyết định".

**Cách đọc mỗi flag:** mã yêu cầu · loại vấn đề (mâu thuẫn / không đo được / không an toàn / quá tốn kém /
không làm được trên Windows hoặc phần cứng) · vấn đề cụ thể (có bằng chứng trong mã) · đề xuất thay thế vẫn
đạt mục tiêu của khách. **Mức:** Chặn = phải giải quyết trước khi duyệt baseline; Cao / Trung bình / Thấp.
Đề xuất **không thêm tính năng**, trừ khi ghi rõ là sửa lỗi so với chuẩn chất lượng (phạm vi v1.0 cho phép).

## Tóm tắt: 10 flag quan trọng nhất

| # | Flag | Yêu cầu | Một dòng |
|---|---|---|---|
| 1 | SA-S1 | Q-5, NFR-6, NFR-13, G-3, AT-42 | Trên tay của khách bảo vệ nhiệt đang **tắt** (0 °C); "vẫn cho chạy + banner" chưa đủ an toàn và AT-42 không chạy được trên tay đó |
| 2 | SA-P1 | FR-1, FR-69, chuẩn "kiểm đúng tệp người dùng cài" | `uv tool install <wheel>` không dùng `uv.lock` và cần `git`: môi trường trên PC khách không phải môi trường QC đã kiểm |
| 3 | SA-C1 | NFR-18, AT-2, REG-4/5/7/8/14 | CI Windows bỏ qua ≈ 16 test bus (pty): bằng chứng Windows cho các lỗi hiện trường quan trọng nhất chỉ có ở UAT |
| 4 | SA-N3 | NFR-3, NFR-4, FR-28, FR-29, FR-48 | Suy luận chạy trong nhịp: e-stop / dead-man trễ bằng thời gian suy luận; "tay đứng yên < 100 ms" là số vật lý không đo được ở phía vendor |
| 5 | SA-N2 | NFR-2, FR-24 | Đích 250 Hz + "nhịp trễ < 1 %" mâu thuẫn khi bus chậm hơn; "bộ chuyển 1 ms" không áp dụng được cho CH340 / CH343 |
| 6 | SA-N1 | NFR-1, G-2, AT-31 | Định nghĩa độ trễ là vật lý, số trên màn hình là phần mềm; "≤ LeLab + 10 ms" không đo được (LeLab không có số) |
| 7 | SA-W2 | FR-12, FR-13, REG-8 | Trên Windows "Access is denied" có hai nghĩa; hai bộ chuyển CH340 (không serial) luôn mơ hồ khi kết nối lại; số COM đổi theo cổng USB |
| 8 | SA-W3 | FR-75 | Đóng cửa sổ console trên Windows **không** dừng an toàn (Windows giết tiến trình sau ~5 s, không qua `shutdown`) |
| 9 | SA-L1 | C-1, NFR-14 | Gói phụ thuộc `hibiscus` (Hibiscus CLI v0.1.1) khai giấy phép **"Proprietary"** trong khi Station là AGPL công khai |
| 10 | SA-P2 | Q-1, NFR-9 | Giữ macOS / Docker / Pi 5 / Jetson "trong sản phẩm nhưng chưa nghiệm thu" mâu thuẫn với chuẩn "nền tảng không kiểm được = không đạt" |

Ngoài 10 mục trên: SA-Q1 (danh sách UAT của khách quá dài) là mục Cao về chi phí.

---

## A. An toàn

### SA-S1 · Q-5, RULE-5, FR-33, NFR-6, NFR-13, G-3, AT-42, REG-13 · không an toàn + không làm được trên phần cứng của khách · **Chặn**
**Vấn đề.** Cả hai tay của khách đọc 0 °C ở mọi servo (CHANGELOG 0.2.7 "Known"). Theo RULE-5 / FR-33 các số
này là "không rõ", nên `ThermalGuard` không bao giờ có mẫu thật: **bảo vệ nhiệt của Station không hoạt
động** trên đúng phần cứng nghiệm thu. Chỉ còn lớp firmware (servo tự ngắt mô-men ở `Max_Temperature_Limit`
→ tay rơi). Hệ quả: (a) G-3 "100 % AT an toàn đạt trên tay thật" và AT-42 (dừng nhiệt với ngưỡng hạ) **không
thể thực hiện** trên tay của khách; (b) đề xuất mặc định của Q-5 (cho chạy + banner cam cố định) dựa vào việc
người dùng mới đọc và hiểu banner, trong khi policy / chương trình có thể chạy lâu không người canh.
Nguyên nhân 0 °C / dòng ~1000 chưa được thu thập đúng cách: `doctor` không đọc `Present_Current` /
`Present_Load` và chỉ dùng `sync_read` (cùng đường với Station, nên không phân biệt được lỗi giải mã với
servo thật sự không có cảm biến).
**Đề xuất.**
1. **Trước** khi khách quyết định Q-5: chạy SP-1 (ARCHITECTURE §7.2). Sửa `doctor` (sửa lỗi K-11, trong phạm
   vi v1.0) để dump thô từng servo bằng `read` riêng lẻ khối thanh ghi 56–70 và 0–3 (firmware, model); đồng
   thời nhờ khách mở **công cụ Feetech FD chính hãng** trên cùng PC và chụp màn hình nhiệt độ / dòng của một
   servo. Hai nguồn độc lập → biết lỗi ở Station / rustypot hay ở servo.
2. Nếu servo thật sự không báo nhiệt: Q-5 đổi thành "chạy được khi **không giám sát nhiệt**", với: xác nhận
   rõ ràng **mỗi lần kết nối** (không chỉ banner); phiên policy / phát quỹ đạo / chương trình (không có người
   cầm leader) có giới hạn thời gian liên tục mặc định (ví dụ 10 phút rồi nghỉ, kỹ sư đổi được); teleop / ghi
   không bị giới hạn (người cầm leader thấy tay). Đây là thay đổi hành vi → BA đưa vào như sửa lỗi an toàn
   hoặc CR, khách quyết định.
3. AT-42 trên tay của khách: ghi **"không áp dụng — servo không báo nhiệt"** có chữ ký khách (miễn trừ theo
   mã), và chứng minh AT-42 trên giả lập + (nếu có) một tay SO-101 khác báo nhiệt đúng.
**Khách quyết định:** Q-5 sau khi có kết quả SP-1 (đề xuất: phương án 2).

### SA-S2 · C-4, FR-28, NFR-3, BR-5 · không an toàn (phụ thuộc vào focus trình duyệt) · Cao
**Vấn đề.** E-stop là phần mềm. Phím Space chỉ có tác dụng khi **tab Station đang được chọn**; khi người dùng
đang ở cửa sổ khác (xem hướng dẫn, LeLab, PowerShell) thì Space không dừng gì. Nút DỪNG cần chuột. Kit
SO-101 không có công tắc dừng khẩn cứng; C-4 "luôn phải có cách ngắt nguồn" chưa nói cách nào.
**Đề xuất.** Không đổi mã. (1) Hướng dẫn và UAT ghi rõ: "Space chỉ dừng khi cửa sổ Station đang được chọn".
(2) Khuyến nghị (điều kiện tiên quyết của UAT chuyển động) một **công tắc ngắt nguồn trên dây nguồn
follower** (công tắc DC rẻ hoặc nút nấm) và AT kiểm "ngắt nguồn giữa chuyển động → Station báo
`device_lost` / mất bus rõ ràng, không treo". (3) Sau v1.0 (CR): phím tắt toàn cục hoặc nút dừng USB.

### SA-N3 · NFR-3, NFR-4, FR-28, FR-29, FR-48, ADR-5 · không đo được + không đạt với model chậm · **Chặn** (định nghĩa)
**Vấn đề.** (1) Suy luận policy chạy **đồng bộ trong luồng owner** (`sessions/run.py`). E-stop được kiểm đầu
nhịp và giữa suy luận và gửi lệnh: không lệnh mới nào bị gửi (đúng), nhưng lệnh "giữ" (`Goal := Present`) và
kiểm dead-man chỉ chạy **sau khi suy luận xong**. Với ACT trên CPU yếu (Pi 5) hoặc SmolVLA trên CPU (hàng
trăm ms tới vài giây), NFR-4 "1,0 s (+ ≤ 1 nhịp)" và NFR-3 "< 100 ms" không giữ được. Chuyển động vẫn bị chặn
ở ≤ 5° từ lệnh cuối (giới hạn bước), nên rủi ro thực tế thấp, nhưng yêu cầu đang viết là sai. (2) "Tay đứng
yên < 100 ms" là số **vật lý** (phụ thuộc giảm tốc servo, tải), chỉ đo được bằng video 240 fps ở phía khách.
**Đề xuất.** Viết lại thành ba số đo được:
* NFR-3a (vendor, test tự động): từ lúc nhận e-stop tới khi không còn lệnh vị trí mới: **≤ 1 nhịp** cho
  teleop / ghi / phát lại / quỹ đạo / chương trình; **≤ 1 nhịp + 1 lần suy luận** cho chạy model.
* NFR-3b (vendor, e2e): phím Space trên trình duyệt → máy chủ nhận e-stop: p99 ≤ 50 ms (đo trong Playwright).
* NFR-3c (UAT, quan sát): tay dừng "ngay" khi bấm Space; video điện thoại chế độ quay chậm là tuỳ chọn.
* NFR-4: "1,0 s + ≤ 1 nhịp + ≤ 1 lần suy luận". Và (sửa lỗi an toàn, nhỏ): **từ chối chạy model** khi suy
  luận khởi động (warm-up) trên máy đó > 500 ms (½ dead-man), với lời giải thích "Model quá chậm trên máy
  này cho an toàn dead-man. Dùng CUDA hoặc model nhỏ hơn". BA / khách quyết định có nhận sửa này vào v1.0.

## B. Windows, cổng COM, phần cứng

### SA-W1 · FR-9 · không làm được trên Windows · Trung bình
**Vấn đề.** FR-9 yêu cầu hiện "đang dùng bởi <ai> (Station hoặc tiến trình khác)". Station chỉ biết các cổng
**chính nó** giữ (`list_ports(in_use)`); tên tiến trình khác chỉ có ở `doctor` và chỉ trên Linux (`/proc`).
Trên Windows không có API thường (không admin) để biết tiến trình nào giữ một cổng COM.
**Đề xuất.** FR-9: "đang dùng bởi Station (<tay>)" cho cổng của Station; với tiến trình khác: Linux nêu tên
tiến trình (từ `/proc`), Windows chỉ báo "đang bận — có thể LeLab / lerobot đang mở" **khi** Kết nối / Dò
thất bại với `Access is denied`. Không mở thử cổng chỉ để liệt kê.

### SA-W2 · FR-12, FR-13, REG-8 · mơ hồ trên Windows + phần cứng · Cao
**Vấn đề.** (1) Trên Windows cổng COM là **độc quyền**: mở cổng LeLab đang giữ trả `ERROR_ACCESS_DENIED` —
cùng mã với "thiết bị đã mất" khi đang chạy. Mã hiện phân biệt theo **thời điểm** (lúc mở → `port_busy`,
`owner._open_device`; lúc chạy → `device_lost`, `bus.py`), nhưng SRS / AT chưa có ca "LeLab đang mở cổng,
bấm Kết nối" trên Windows. (2) Bộ chuyển CH340 (`1a86:7523`) **không có số serial**: nếu cả leader và
follower đều là CH340, FR-13 "Kết nối lại theo serial / VID:PID" luôn rơi vào ca "hai bộ chuyển giống hệt → hỏi
người dùng". Windows cũng gán số COM theo **ổ USB** cho CH340: cắm sang ổ khác = số COM mới. (3) Windows USB
selective suspend có thể làm cổng "mất" khi rảnh.
**Đề xuất.** Thêm vào SRS / ACCEPTANCE: AT "LeLab đang chạy giữ COMx → Kết nối → `port_busy` với lời nhắc
đóng LeLab, **không** phải `device_lost`" (Windows, UAT); AT "rút cáp, cắm sang ổ USB khác" cho cả CH340 và
CH343; ghi rõ trong hướng dẫn: hai tay CH340 thì sau khi cắm lại Station sẽ hỏi tay nào là tay nào (đúng
thiết kế, không phải lỗi). UAT ghi lại loại bộ chuyển của khách (VID:PID từ `doctor`). Hướng dẫn tiếng Việt
thêm cách tắt USB selective suspend (đã có trong danh sách kiểm tra FR-13 — cần ảnh minh hoạ).

### SA-W3 · FR-75 · không đạt trên Windows · Cao
**Vấn đề.** FR-75 yêu cầu dừng an toàn khi "đóng cửa sổ". Mã chỉ dừng qua `lifespan` của FastAPI (Ctrl+C,
SIGTERM). Đóng cửa sổ console trên Windows gửi `CTRL_CLOSE_EVENT`, Python / uvicorn không xử lý; Windows kết
thúc tiến trình sau ~5 s **không** chạy `shutdown()`: tay giữ mô-men ở mục tiêu cuối, tập đang ghi có thể
không được `finalize`. Đăng xuất / tắt máy Windows cũng vậy. Người mới rất hay đóng cửa sổ.
**Đề xuất.** Sửa lỗi (phạm vi v1.0): bắt `CTRL_CLOSE_EVENT` / `CTRL_LOGOFF_EVENT` / `CTRL_SHUTDOWN_EVENT`
(`SetConsoleCtrlHandler`, SP-7) và chạy đường dừng **rút gọn** trong ≤ 4 s: e-stop giữ → tắt mô-men theo hồ sơ
(bỏ bước về tư thế nghỉ) → `finalize` dataset nếu kịp. FR-75 phải ghi rõ ngoại lệ: "đóng cửa sổ khi đang ghi:
tập đang ghi dở có thể bị bỏ; các tập đã lưu còn nguyên". Thêm AT Windows (UAT) cho ca này.

### SA-W4 · FR-21, FR-22, FR-46 · rủi ro trên Windows · Trung bình
**Vấn đề.** Trên Windows / macOS Station dò camera theo **số OpenCV** (0, 1, 2…), không có tên thiết bị ổn định.
Hai webcam giống nhau có thể **đổi số** sau khi khởi động lại hoặc cắm lại → camera `front` thành `wrist` mà
không báo: dataset ghi sai khung nhìn, model nhận nhầm camera. Backend MSMF mở camera chậm (vài giây), điều
NFR-5 đã loại trừ nhưng không có đích riêng.
**Đề xuất.** Không thêm tính năng: (1) hướng dẫn và UAT ghi bước "sau khi cắm lại, bấm Thử từng camera và
kiểm hình đúng"; (2) AT cho hai camera cùng loại trên Windows (UAT); (3) NFR-5 thêm "mở mỗi camera ≤ 5 s trên
Windows" hoặc ghi rõ không có đích. Đề xuất CR sau v1.0: nhận diện camera theo đường dẫn thiết bị DirectShow.

### SA-W5 · NFR-5 · đo được nhưng phụ thuộc máy · Thấp
**Vấn đề.** Lần chạy đầu sau cài, Windows Defender quét hàng nghìn tệp của torch → khởi động có thể > 60 s;
NFR-5 đã loại "lần đầu tải torch" nhưng không loại quét của Defender. Import ứng dụng đo được 0,5 s trên Linux
(torch nạp lười), nên lần chạy thứ hai ≤ 15 s là khả thi.
**Đề xuất.** NFR-5 ghi rõ "lần chạy thứ hai trở đi, không camera"; hướng dẫn nói lần đầu có thể chậm 1–2 phút.

### SA-W6 · FR-64 · rủi ro Windows · Thấp
**Vấn đề.** Xoay vòng `station.log` (10 MiB × 5) dùng đổi tên tệp; trên Windows đổi tên thất bại nếu một tiến
trình khác đang mở tệp (antivirus, `doctor` đang nén, trình soạn thảo).
**Đề xuất.** Tech Lead thêm test Windows "xoay vòng khi tệp đang mở" (CI Windows); nếu lỗi, xoay vòng tiếp tục
ghi tệp cũ thay vì mất log. Không đổi yêu cầu.

## C. Cài đặt, cập nhật, nền tảng

### SA-P1 · FR-1, FR-69, Q-4, BR-15, chuẩn "ATs PASS trên đúng tệp người dùng cài" · mâu thuẫn + không làm được cho người mới · **Chặn**
**Vấn đề.** `uv tool install <wheel>` **không dùng `uv.lock`**: nó giải lại phụ thuộc theo khoảng trong
`pyproject.toml` (`fastapi>=0.115,<1`, `uvicorn>=0.30`, `pydantic>=2.9,<3`, torch / datasets / av theo lerobot…)
vào **ngày cài**. Hai cài đặt cùng một wheel ở hai ngày khác nhau có thể khác thư viện; QC không thể kiểm "đúng
tệp người dùng cài" vì môi trường được tạo ra trên PC khách. Quay lại bản cũ (FR-69) cũng không ra đúng môi
trường cũ. Thêm nữa, `lerobot` và `hibiscus` là phụ thuộc **git** → uv cần `git` trên máy; người mới trên
Windows thường không có git. CI Windows không phát hiện vì runner có sẵn git (SP-3).
**Đề xuất (ADR-13).** Bản phát hành v1.0 kèm (a) tệp constraints xuất từ `uv.lock` và (b) wheel dựng sẵn của
`lerobot@fe1c545` và `hibiscus@v0.1.x` (wheelhouse đính kèm release), để cài không cần git và cho ra đúng bộ
thư viện đã kiểm. Gói thành **một lệnh PowerShell** (`irm <release>/install.ps1 | iex`: cài uv nếu thiếu, cài
Station đúng phiên bản có constraints). Cùng lệnh đó dùng để **cập nhật** và **quay lại** (`-Version 1.0.0`) —
đồng thời trả lời Q-4 mà không cần tính năng cập nhật trong ứng dụng. QC kiểm trên VM Windows sạch không có git.
Đây là thay đổi đóng gói, không phải tính năng; Tech Lead ước lượng (đề xuất M).

### SA-P2 · Q-1, NFR-9, AT-4 · mâu thuẫn với chuẩn chất lượng · **Chặn** (khách quyết định)
**Vấn đề.** Đề xuất mặc định của Q-1 giữ macOS, Docker (Linux PC, Pi 5, Jetson) "trong sản phẩm nhưng chưa
nghiệm thu, không chặn phát hành". Chuẩn chất lượng nói nền tảng QC không tới được là NOT VERIFIED = không đạt,
và README hiện quảng cáo các nền tảng này là hỗ trợ. Thực tế hôm nay: image `-cuda`, `-jetson`, arm64 **chưa
từng chạy** (chỉ build khi có tag); base `nvcr.io/nvidia/pytorch:26.02-py3-igpu` chưa được chứng minh trên
JetPack 6 / L4T R36 (SP-6); macOS chỉ có smoke cài đặt, không pytest.
**Đề xuất.** v1.0 **hỗ trợ chính thức**: Windows 10/11 x64 wheel (Must, UAT khách) + Ubuntu 22.04/24.04 x86_64
wheel (Should, vendor) + Docker Linux x86_64 `-cpu` (Should, đã có smoke CI). Các nền tảng còn lại ghi **"bản
xem trước (preview) — không thuộc nghiệm thu v1.0"** trong README, ghi chú phát hành và `install.sh` (in cảnh
báo), với danh sách lỗi đã biết; không chặn phát hành, không bị tính là defect của v1.0. Khách chọn phương án
này hoặc cấp máy để kiểm.

### SA-Q2 · G-1, AT-1 · đo được nhưng phụ thuộc mạng · Thấp
**Vấn đề.** "Từ cài đặt tới teleop ≤ 30 phút" gồm tải torch và lerobot (vài trăm MB với `--torch-backend cpu`,
nhiều GB với CUDA trên Linux) — phụ thuộc đường mạng của khách, không phải sản phẩm.
**Đề xuất.** G-1 đo **không tính thời gian tải** (hoặc ghi điều kiện: mạng ≥ 20 Mbps, `--torch-backend cpu`).

## D. CI và bằng chứng kiểm thử

### SA-C1 · NFR-18, AT-2, REG-4, REG-5, REG-7, REG-8, REG-14 · không đạt hôm nay · **Chặn**
**Vấn đề.** Bộ giả lập STS3215 (`tests/sts_emulator.py`) dùng **pty**, chỉ có trên POSIX. Trên CI Windows bị bỏ
qua: `test_calib_simple.py` (5 test, REG-4 / REG-7), `test_real_stack.py` (8 test, REG-14), `test_teleop_latency.py`
(REG-5), phần `posix` của `test_device_lost.py` (REG-8). Tức là **đường bus thật qua rustypot / serialport-rs
trên Windows chưa từng chạy trong CI**; mọi lỗi hiện trường 0.2.x đều xảy ra trên Windows. NFR-18 / AT-2 "không
test bị bỏ qua để che lỗi" không đạt như đang viết.
**Đề xuất.** (1) SP-2: cặp cổng COM ảo trên `windows-latest` (driver null-modem) để `sts_emulator` nói ở một đầu
và Station mở `COMx` ở đầu kia; nếu runner không cài được driver: một runner Windows tự host với bộ chuyển
CH343 thật nối vào vi điều khiển giả lập servo (chi phí phần cứng nhỏ, đồng thời là HIL rẻ cho R-3). (2) Cho tới
khi xong: NFR-18 liệt kê **từng** test được phép bỏ qua theo nền tảng, lý do, và AT UAT phủ thay; AT-2 kiểm danh
sách đó (không bỏ qua nào ngoài danh sách).

### SA-C2 · NFR-9, NFR-18 · thiếu độ phủ · Trung bình
**Vấn đề.** Không có vitest / e2e trên Windows; e2e chỉ Chromium trên Linux, trong khi NFR-9 hứa Edge và Firefox
120+ (Edge là trình duyệt mặc định của người mới trên Windows). macOS không chạy pytest.
**Đề xuất.** Thêm job e2e Playwright kênh `msedge` trên `windows-latest` (chạy `--mock`, cùng bộ test) và Firefox
trên Linux; thêm pytest trên macOS (pty có trên macOS) hoặc giữ macOS ở "preview" (SA-P2). Chi phí S.

## E. NFR không đo được / mâu thuẫn

### SA-N1 · NFR-1, G-2, AT-31, REG-5 · không đo được như đang viết · **Chặn** (định nghĩa)
**Vấn đề.** NFR-1 định nghĩa độ trễ **vật lý** (leader tới vị trí → follower tới vị trí). Con số "độ trễ ~X
ms" Station hiển thị là **phần mềm** (`loop.latency_ms`: từ lúc đọc leader tới lúc gửi Goal, cộng ½ nhịp),
thường vài ms; phần lớn độ trễ vật lý là đáp ứng của chính servo (giả lập: 54 ms), giống nhau giữa Station và
LeLab vì cả hai dùng cấu hình servo của lerobot. "≤ LeLab + 10 ms trên cùng máy" không đo được: LeLab không
hiển thị độ trễ, và video 240 fps đòi thiết bị và thao tác phân tích khung hình mà khách không có.
**Đề xuất.** Tách:
* NFR-1a (vendor, giả lập có thời gian thật `teleop_bench.py`): độ trễ vật lý mô phỏng p50 ≤ 70 ms và ≤ vòng
  tham chiếu kiểu LeLab + 10 ms (đã đo 0.2.6: 55 ms vs 54 ms).
* NFR-1b (sản phẩm, mọi máy): độ trễ phần mềm Station hiển thị p50 ≤ 15 ms, p95 ≤ 30 ms khi `doctor` báo ≤ 3 ms
  mỗi lần đọc bus.
* NFR-1c (UAT): khách teleop lần lượt bằng LeLab và Station trên cùng PC, cùng tay; kết quả "không chậm hơn
  LeLab" theo đánh giá của khách. Video quay chậm là tuỳ chọn, không bắt buộc.

### SA-N2 · NFR-2, FR-24, FR-63 · mâu thuẫn + không áp dụng cho phần cứng · Cao
**Vấn đề.** (1) Teleop mặc định 250 Hz, "bus chậm thì chạy chậm hơn" (FR-24), nhưng NFR-2 đòi "tỉ lệ nhịp trễ <
1 %". `Deadline` tính mỗi nhịp vượt chu kỳ 4 ms là trễ: trên bus chỉ chạy được 150 Hz thì **gần 100 % nhịp là
"trễ"** dù teleop hoàn toàn bình thường. (2) "Bộ chuyển 1 ms" / "đặt latency timer 1 ms" là khái niệm của chip
**FTDI**; bo SO-101 dùng **WCH CH340 / CH343** (`cdc_acm` trên Linux, driver WCH hoặc `usbser` trên Windows),
không có thiết lập latency timer. Lời khuyên của `doctor` ("set the USB latency timer to 1 ms") không làm được
trên phần cứng của khách. (3) ≥ 100 Hz trên Windows + CH34x chưa ai đo (SP-4).
**Đề xuất.** NFR-2: teleop báo **Hz đạt được** (không tính "nhịp trễ"), đích ≥ 100 Hz khi `doctor` báo ≤ 3 ms mỗi
lần đọc; chỉ số "nhịp trễ < 1 %" và "p95 thời gian nhịp ≤ 36 ms" áp cho vòng **cố định** 30 Hz (ghi, chạy model).
`doctor` (sửa lỗi chuỗi): với bộ chuyển WCH nói "bộ chuyển USB chậm / hub USB: cắm thẳng vào máy" thay vì latency
timer. Đích cuối cho Windows chốt sau SP-4 (số đo trên PC của khách).

### SA-N4 · NFR-13, FR-31, AT-40 · không đo được · Cao
**Vấn đề.** "Dòng: cùng bậc độ lớn" không phải tiêu chí đạt / không đạt; đơn vị 6,5 mA/bước chưa xác nhận
(`feetech.py`). AT-40 cần nhiệt kế và đồng hồ vạn năng ở phía khách. Trên tay của khách nhiệt độ đang 0 °C
(SA-S1).
**Đề xuất.** Sau SP-1: nhiệt ±3 °C và điện áp ±0,2 V **so với công cụ Feetech FD** trên cùng servo (khách có sẵn,
không cần dụng cụ đo). Dòng: nếu SP-1 xác nhận đơn vị → ±20 % so với FD; nếu không → v1.0 hiện dòng là "—"
(không rõ) ở mọi nơi và bỏ "giới hạn dòng X A" khỏi ngăn chi tiết, ghi vào ghi chú phát hành.

### SA-U1 · NFR-10, AT-91 · phạm vi không rõ · Trung bình
**Vấn đề.** "0 câu tiếng Anh" nhưng người mới vẫn thấy tiếng Anh ở: thông báo của uv khi cài, dòng khởi động của
`hibiscus-station` trong PowerShell (liên kết, "port in use…"), `doctor`, log; và chi tiết lỗi máy chủ (K-4).
**Đề xuất.** NFR-10 áp cho **giao diện web và hướng dẫn**; các dòng CLI người mới **chắc chắn thấy** (khởi động,
liên kết đăng nhập, cổng bận, đã có bản đang chạy) song ngữ hoặc theo ngôn ngữ hệ thống; `doctor`, log, đầu ra
của uv: tiếng Anh, ngoài phạm vi (dành cho kỹ sư / nhà cung cấp). Hướng dẫn tiếng Việt có ảnh chụp các dòng đó.

### SA-U2 · NFR-11, FR-56, FR-68 · quá tốn kém / không làm được với thành phần bên thứ ba · Trung bình
**Vấn đề.** "Bàn phím đi hết luồng chính" và "390 px không cuộn ngang" đụng **trình soạn Blockly** (kéo thả trên
canvas, không hỗ trợ bàn phím mặc định) và các bảng rộng (động cơ × đại lượng, 12 động cơ).
**Đề xuất.** NFR-11: luồng chính = cài → robot → hiệu chỉnh → camera → teleop → ghi → chạy model → e-stop; trình
soạn khối được miễn yêu cầu bàn phím (chạy / dừng chương trình vẫn phải dùng được bằng bàn phím); ở 390 px **trang**
không cuộn ngang, bảng rộng và canvas được cuộn ngang **trong khung riêng**. Trình soạn khối trên điện thoại: xem
và chạy, không yêu cầu soạn.

## F. Chức năng

### SA-F1 · FR-10 · diễn đạt sai kỹ thuật · Thấp
**Vấn đề.** "Mở từng cổng ứng viên **chỉ-đọc**": cổng serial không mở chỉ-đọc được; ping / đọc vẫn gửi gói lên
bus. Trên Windows, mở cổng còn bị từ chối nếu LeLab giữ.
**Đề xuất.** "Station chỉ gửi lệnh ping / đọc, **không ghi thanh ghi nào, không bật mô-men**; cổng đang bận bị
bỏ qua và ghi 'đang bận'".

### SA-F2 · FR-9, FR-12, RULE-1 (Linux) · không an toàn trên Linux · Trung bình
**Vấn đề.** Trên Linux tty không độc quyền mặc định. Khoá của Station (`flock`, ADR-9) chỉ chặn một Station khác.
Nếu LeLab mở cổng **trước**, Station có thể mở cùng cổng và hai chương trình cùng lái bus (gói lẫn, lệnh của hai
bên). Spec §4.3 ghi Station kiểm `TIOCEXCL`, nhưng mã không có (`grep TIOCEXCL` = 0); việc serialport-rs đặt cờ
này khi mở chưa được test.
**Đề xuất.** SP-5; sửa lỗi nhỏ: trước khi mở, Linux quét `/proc/*/fd` (đã có trong `doctor`) và trả `port_busy`
nêu tên tiến trình. Thêm AT Linux "LeLab đang mở cổng → Kết nối bị từ chối".

### SA-F3 · FR-20, NFR-15, C-2 · không đo được (thiếu phiên bản) · Cao
**Vấn đề.** "Dùng được với `lerobot-teleoperate` / LeLab" không nêu phiên bản. LeLab cài lerobot **không ghim**
(git main tại ngày cài): thư mục hiệu chỉnh đã đổi qua các bản (`so101_follower` → `so_follower`); Station ghi
vào `so_follower/` nên LeLab dùng lerobot cũ sẽ không thấy tệp, và dataset LeRobot v3 không mở được bằng lerobot
quá cũ.
**Đề xuất.** FR-20 / NFR-15 ghi ma trận: (a) lerobot 0.7.1 `fe1c545` hai chiều — AT vendor; (b) LeLab **đang cài
trên PC của khách** (ghi phiên bản lerobot từ `doctor` / `pip show`) — AT UAT. Nếu (b) dùng thư mục cũ: hướng dẫn
"Dùng tệp này" (FR-18) cho chiều LeLab → Station; chiều ngược lại là CR (ghi thêm bản sao vào thư mục cũ).

### SA-F4 · NFR-16 · không đạt cho một số model · Trung bình
**Vấn đề.** `models/loader.py` nạp adapter PEFT qua `base_model_name_or_path` và SmolVLA nạp backbone VLM: cả hai
**tải từ HF Hub** lần đầu nếu chưa có trong cache. Không có mạng → nạp model thất bại.
**Đề xuất.** NFR-16 thêm ngoại lệ: "model cần backbone từ HF Hub (SmolVLA, adapter PEFT) cần Internet ở lần nạp đầu"
và FR-47 hiện lỗi dịch rõ ("Model này cần tải thành phần từ Internet lần đầu") thay vì lỗi thô. Gói Hibiscus đầy
đủ (tự chứa backbone) là CR phía máy chủ.

### SA-F5 · FR-37 · hành vi biên · Thấp
**Vấn đề.** Dọn lịch sử phiên (30 ngày / 2 GiB) chỉ chạy **lúc khởi động**; Station chạy liên tục (systemd /
Docker) nhiều tuần sẽ vượt 2 GiB.
**Đề xuất.** Ghi rõ "kiểm lúc khởi động và sau mỗi phiên" (sửa nhỏ) hoặc chấp nhận "lúc khởi động" trong SRS.

### SA-F6 · FR-63, K-11, REG-13 · thiếu cho chẩn đoán · Cao (phụ thuộc của SA-S1)
**Vấn đề.** `doctor` không đọc `Present_Current`, `Present_Load`, không dump thô, và chỉ dùng `sync_read`.
**Đề xuất.** Như SA-S1 bước 1: dump thô bằng `read` riêng lẻ, `--verbose` in từng byte; bản này phát hành **trước**
khi nhờ khách chạy (để khách chỉ chạy một lần). Là sửa lỗi theo K-11.

## G. Pháp lý

### SA-L1 · C-1, NFR-14, ADR-12 · rủi ro pháp lý · **Chặn** (trước phát hành công khai)
**Vấn đề.** Gói phụ thuộc `hibiscus` 0.1.1 (Hibiscus CLI, git `v0.1.1`) khai `License: Proprietary` trong metadata.
Station là AGPL-3.0 công khai và wheel kéo gói này về máy người dùng: người nhận không biết được quyền sử dụng
gói đó, và AGPL đòi mã tương ứng của toàn bộ tác phẩm phải phân phối theo điều khoản tương thích. Ngoài ra
`web/package.json` đang bỏ qua 3 cảnh báo bảo mật (`GHSA-5gmw-xhrv-c9v3`, `GHSA-85c8-ppgw-ccpr`,
`GHSA-mrhx-c7xc-m3w5`) chưa có lý do ghi lại.
**Đề xuất.** Chủ sở hữu (cùng tác giả) phát hành Hibiscus CLI **v0.1.2** với giấy phép tương thích (AGPL-3.0, hoặc
MIT / Apache-2.0) và tệp LICENSE, không đổi mã; Station ghim lại. Security ghi lý do (hoặc nâng cấp) cho từng GHSA.
Legal xác nhận bảng giấy phép ở ARCHITECTURE §2 trước phát hành.

## H. Nghiệm thu và quy trình

### SA-Q1 · ACCEPTANCE "Danh sách UAT", AT-31, AT-36, AT-40, AT-88 · quá tốn kém cho khách · Cao
**Vấn đề.** Danh sách UAT hiện có ≈ 45 AT cần khách chạy lại trên Windows + tay thật, nhiều AT cần video 240 fps,
nhiệt kế, đồng hồ vạn năng. Với quy tắc zero-defect, mỗi lỗi tìm thấy ở UAT kéo theo sửa → QC → UAT lại: nhiều
lượt, mỗi lượt vài giờ của khách.
**Đề xuất.** UAT lõi ≤ 15 bước (≈ 60–90 phút) phủ các Must trên Windows + SO-101 thật: cài (một lệnh, SA-P1) →
khởi động → hồ sơ + tìm tay → kết nối → hiệu chỉnh (hoặc dùng tệp LeLab) → kiểm hai tay → teleop + A/B với LeLab
(SA-N1) → e-stop / thả lỏng / đặt lại → rút cáp + cắm lại (SA-W2) → camera + ghi 3 tập → chạy model zip → đóng cửa
sổ khi đang chạy (SA-W3) → `doctor`. Các AT còn lại: vendor chạy trên Linux + giả lập + (SP-2) COM Windows ảo, kèm
video màn hình để khách xem. Không cần dụng cụ đo (SA-N4 dùng Feetech FD).

### SA-Q3 · BRD G-4, REG-13, SA-S1 · phụ thuộc lịch · Trung bình
**Vấn đề.** G-4 "REG-13 có kết luận" phụ thuộc dữ liệu từ PC của khách; nếu khách gửi muộn, cả phát hành bị chặn.
**Đề xuất.** Đặt mốc: bản `doctor` mới (SA-F6) phát hành trong tuần đầu; nếu sau mốc chưa có dữ liệu, REG-13 chuyển
"kết luận: servo không báo nhiệt (chưa rõ vì sao)" và áp SA-S1 phương án 2.

---

## Không flag (đã kiểm, khả thi như viết)

FR-4 / FR-6 (bảo mật cục bộ, LAN), FR-8, FR-11 (dò điện áp), FR-14, FR-16 – FR-19, FR-23, FR-25 – FR-27, FR-30,
FR-32 (thuật toán dừng nhiệt; chỉ vô hiệu do SA-S1), FR-34 – FR-36, FR-38 – FR-45, FR-47 – FR-55, FR-57 – FR-62,
FR-65 – FR-67, FR-70 – FR-74, FR-76; NFR-6 (trên servo báo nhiệt), NFR-7 (trên Linux), NFR-8, NFR-12, NFR-14
(ngoài SA-L1), NFR-17. Các mục này có thiết kế trong ARCHITECTURE §3 – §5; QC vẫn phải chứng minh theo AT.
