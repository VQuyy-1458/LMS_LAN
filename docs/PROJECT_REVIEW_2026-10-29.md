# Rà soát project ngày 29/10/2026

## Các lỗi đã sửa

- Gửi thông báo: không dùng `event.currentTarget` sau `await`, tránh báo lỗi dù server đã gửi thành công.
- Giữ danh sách người nhận khi tìm kiếm; gửi tất cả không còn bị giới hạn bởi lựa chọn riêng trước đó.
- Sau khi gửi, xóa nội dung và lựa chọn, đóng bộ chọn người nhận, báo số người nhận; chặn gửi lặp khi yêu cầu đang xử lý.
- Loại trùng MSSV và khóa thao tác đọc/sửa/ghi thông báo để không mất thông báo khi có yêu cầu đồng thời.
- Nhập tài khoản và tạo admin: sửa lỗi xóa form sau `await` tương tự.
- Phiên đăng nhập: đồng bộ tạo, đọc/cập nhật, đăng xuất, thu hồi và telemetry để các request không ghi đè phiên của nhau. Thao tác đăng nhập thay phiên cũ của sinh viên được thực hiện nguyên tử.
- Chấm bài: timeout khi dọn container không còn ghi đè kết quả hoặc che lỗi gốc. Ghi log lỗi chấm với ID bài nộp.
- Trang vận hành thi lập trình có kiểm tra trạng thái bộ chấm và nút kiểm tra lại.

## Đã kiểm tra

- Bộ Python: 70 kiểm thử, 67 đạt; 3 kiểm thử Docker chạy riêng.
- 22 file JavaScript nguồn qua kiểm tra cú pháp; không tính metadata AppleDouble `._*`.
- CSV test case, QR, đăng nhập HTTP LAN, reset mật khẩu và gửi/nhận thông báo đúng người nhận.
- Kiểm thử trình duyệt admin/sinh viên: khóa học, thành viên, tài liệu và xem trước, bài tập/nộp bài, điểm danh/QR/camera, kỳ thi, kho bài nộp/xuất file/lịch sử điểm, thông báo/đã đọc, bảng điểm, hồ sơ, đổi mật khẩu, giao diện di động. Không phát hiện lỗi JavaScript/CSP trong lượt hoàn tất.
- Kiểm thử 12 phiên đăng nhập được tạo đồng thời; các phiên đều được giữ và đăng xuất riêng đúng.
- Dữ liệu thực: không phát hiện liên kết khóa học/sinh viên bị thiếu hoặc file bài nộp bị mất trong phạm vi kiểm tra.
- Docker thật: bốn ngôn ngữ C/C++/Java/Python; AC, WA và điểm từng phần, CE, RE, TLE, MLE, OLE; chặn mạng và không đưa test ẩn vào container.

Các kiểm thử không bảo đảm mọi tình huống đều không còn lỗi. Những lỗi phát sinh theo dữ liệu/thao tác cụ thể cần được tái hiện tiếp.

## Cập nhật trang làm bài lập trình

- Sau khi bắt đầu thi, sinh viên thấy danh sách bài; URL `?exam=...&problem=0` mở trang làm bài riêng, không dùng hộp thoại.
- Trang bài có đề, ví dụ, thời gian còn lại, ngôn ngữ được phép, editor có số dòng và khung mẫu C/C++/Java/Python, nút tải file vào editor và Submit.
- Nháp lưu riêng theo sinh viên, kỳ thi, bài và ngôn ngữ trên trình duyệt. Đổi bài, tải lại trang và cập nhật kết quả không xóa nội dung đã viết.
- Lịch sử chỉ lấy bài đang mở; hiển thị trạng thái chờ, biên dịch, tiến trình chấm và AC/WA/CE/RE/TLE/MLE/OLE. Cập nhật từ máy chấm, không tải lại trang; test ẩn vẫn được giữ kín.
- Kiểm thử sau thay đổi: 71 kiểm thử Python (68 đạt, 3 Docker chạy riêng); kiểm thử trình duyệt có Docker hoàn tất không có lỗi JavaScript/CSP. Đã thử trực tiếp cả bốn toolchain và kiểm tra ảnh giao diện desktop/mobile.

## Quy tắc danh sách sau điều chỉnh

- Tài khoản, sinh viên, bảng điểm: chỉ tăng/giảm theo MSSV hoặc mã tài khoản; bộ lọc tài khoản và điểm danh dùng đúng trạng thái tương ứng.
- Tài liệu: tăng/giảm theo tên; lọc loại file, tìm tên tài liệu/file.
- Kỳ thi và bài tập: luôn đang mở → sắp diễn ra/chưa mở → đã đóng; không có điều khiển sắp xếp. Chỉ tìm kiếm và lọc trạng thái phù hợp, kèm các bộ lọc khóa học/hình thức/bài làm sẵn có.
- Khóa học, phiên điểm danh và lịch hoạt động: giữ thứ tự hoạt động phù hợp; lọc theo trạng thái khóa học, phiên hoặc loại hoạt động.
- Bài toán lập trình: tăng/giảm theo thứ tự bài, lọc kết quả làm bài. Lịch sử code lọc trạng thái chấm/AC/WA/CE…; lịch sử file chỉ lọc chưa chấm/đã chấm.
- Lịch sử nộp/chấm: tăng/giảm theo thời gian; các lần nộp của cùng một bài dùng số lần nộp. Kho bài nộp áp dụng thứ tự trước phân trang và khi xuất CSV/ZIP.
- Không có menu chọn tiêu chí sắp xếp chung. Các ô điểm đang sửa và bản nháp code được giữ khi lọc/đổi chiều.

Kiểm chứng: kiểm thử quy tắc danh sách, ba kiểm thử archive mới và lượt trình duyệt có chấm Docker đều đạt; đã thử trực tiếp đổi chiều MSSV, xác nhận kỳ thi/bài tập không có nút sắp xếp, lọc AC giữ editor và đổi chiều bảng điểm giữ ô điểm chưa lưu.

## Các kỳ thi thử

Khóa học: **Phòng thi thử bộ chấm lập trình** (`JUDGE-TRY-2026`).

1. Thi thử 01: Tổng hai số nguyên; Giá trị lớn nhất trong mảng.
2. Thi thử 02: Ước chung lớn nhất; Kiểm tra số nguyên tố.
3. Thi thử 03: Truy vấn tổng đoạn; Dãy ngoặc đúng.

Mỗi kỳ 240 phút, 2 bài × 50 điểm, hỗ trợ C/C++/Java/Python. Mỗi bài có 2 test mẫu + 6 test ẩn, chia đều điểm theo số test đạt. Loại Test không tính vào bảng điểm học phần. Tất cả tài khoản sinh viên đang hoạt động tại lúc tạo được thêm vào khóa thi thử.

Tài khoản thi thử được tạo bằng script mẫu. Thông tin đăng nhập hiện hành được quản lý riêng tại máy triển khai; không công bố trong báo cáo. Không đặt lại mật khẩu trong quá trình khởi động server.

Thông tin ID kỳ thi và thư mục sao lưu trước khi thêm nằm trong `data/programming_trial.json`. Không thay thế các khóa học, kỳ thi hoặc mật khẩu sinh viên cũ.

`python -m app.programming_trial --verify` chấm lời giải tham chiếu bằng Docker và ghi kết quả vào `logs/trial-judge-verification.json`. Dừng server trước khi chạy `--apply`; lệnh này mở các đề thi thử còn ở bản nháp nếu bộ chấm đã sẵn sàng. Chạy lại không tạo trùng kỳ thi, không mở lại kỳ thi đã kết thúc.

## Môi trường chấm

Docker/WSL từng gặp lỗi I/O và kernel soft lockup trong lúc kiểm tra. Đã khởi động lại dịch vụ WSL với quyền quản trị. Kết quả xác nhận sáu bài tham chiếu và lượt kiểm thử trình duyệt có chấm thật được ghi riêng trong `logs/review-trial-tests.log` và `logs/review-browser-judge-tests.log`; cần đọc kết quả cuối, không coi các lượt bị gián đoạn là đạt.

Lượt khởi động tiếp theo sau khi Windows khởi động lại: Docker tiếp tục không phản hồi. Đã tạo `%USERPROFILE%\.wslconfig` với `memory=2GB`, `processors=2` (trước đó không có file cấu hình này), rồi khởi động lại dịch vụ WSL và Docker. Bộ chấm đã sẵn sàng. Đây là cấu hình tài nguyên dùng chung cho WSL 2; tham khảo [tài liệu Microsoft](https://learn.microsoft.com/windows/wsl/wsl-config).

Đã chấm lại cả sáu lời giải tham chiếu: **6/6 bài AC, tổng 48/48 test đạt**. Kết quả đầy đủ nằm trong `logs/trial-judge-verification.json` và `logs/review-trial-tests.log`. Đã mở cả ba kỳ thi thử bằng cấu hình lưu sẵn, mỗi kỳ có thời lượng 240 phút tính từ lúc mở. Server được khởi động lại tại cổng 8080. Kết quả này xác nhận lượt kiểm tra hiện tại, không bảo đảm Docker sẽ không còn lỗi môi trường trong mọi lần chạy.
