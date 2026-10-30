# Ổn định backend và làm rõ trạng thái tài khoản

Người dùng đã duyệt toàn bộ sửa kỹ thuật backend, và duyệt riêng phần giao diện quản lý hai loại khóa tài khoản. Các kiểm tra lỗi sử dụng dữ liệu tạm. Không tự đặt lại mật khẩu demo, sửa điểm cũ hoặc thay đổi danh sách thí sinh đã lưu trên dữ liệu thật.

## Backend đã sửa

| Nhóm | Thay đổi |
|---|---|
| HTTP/request | Từ chối Content-Length âm, sai định dạng, bị lặp hoặc quá lớn; từ chối Transfer-Encoding chưa hỗ trợ; giới hạn byte đọc thực tế. Giữ timeout và khóa I/O đã sửa ở F01. |
| Kết nối Windows | Gửi lỗi trước rồi đóng nửa kết nối và thu phần dữ liệu còn lại trong thời hạn ngắn. Tránh reset TCP làm client mất thông báo lỗi khi body vẫn đang đến. |
| Tài khoản | Đăng nhập kiểm tra lại trạng thái/hash hiện hành trong giao dịch trước khi tạo phiên. Tự đổi mật khẩu, reset và khóa tài khoản được đồng bộ để tránh ghi đè thay đổi mới. |
| Lưu dữ liệu | Thêm `atomic_transaction`: gom cập nhật JSON và audit, journal trước khi commit, rollback và phục hồi giao dịch dở dang trước khi đọc dữ liệu. Các thao tác học tập, thi, nhận bài, chấm lại và cập nhật hạn thi dùng giao dịch. |
| Payload | File mới được flush trước metadata, có dọn file khi giao dịch thất bại. Chỉ đưa bài vào hàng đợi sau khi lưu thành công; công việc đã lưu nhưng chưa xếp lịch được quét lại định kỳ. |
| Retry nộp bài | File và code có request ID. Gửi lại cùng nội dung trả biên nhận cũ; cùng ID nhưng nội dung khác trả 409. Không tính thêm lượt hoặc quota khi retry. Frontend giữ ID khi cần gửi lại và tạo ID mới cho nội dung/lần nộp mới. |
| Lịch sử thi | Chặn sửa cấu hình kỳ thi file đã phát/kết thúc. Kết thúc thi thủ công giữ mã lượt và liên kết bài nộp/bảng điểm. Khi timestamp cũ trùng giây, bài được thêm sau được chọn là bài mới nhất. Timestamp mới có độ chính xác mili giây. |
| Bộ chấm | Tách lỗi chương trình khỏi mã timeout bằng wrapper chuẩn hóa mã thoát con, dùng cờ `timed_out`. Lưu image digest cùng bài để chấm lại dùng đúng image. Kiểm tra ngân sách test khi lưu cấu hình; hạn tổng một công việc 300 giây. |
| Hàng đợi | Hạn số bài chờ/mỗi sinh viên vẫn được kiểm tra. Lỗi xếp lịch không để ID mắc kẹt trong bộ nhớ; worker định kỳ khôi phục bài queued/running chưa được xếp lịch. Bài lỗi hạ tầng vẫn giữ nguồn và lịch sử. |
| Xác thực | Giới hạn độ dài tên/mật khẩu đăng nhập; quota nguồn 120 lượt/phút; giới hạn 4 phép scrypt đồng thời; dọn và chặn tăng vô hạn dữ liệu khóa đăng nhập. Không thay đổi quy tắc khóa tạm 3 lần sai/15 phút trong đợt này. |
| Hiệu năng | Session chỉ cập nhật hiện diện khi cần, tối đa khoảng mỗi 10 giây khi không đổi IP; preflight không ghi session. Cache JSON có kiểm tra phiên bản file và trả bản sao. Gom refresh hạn thi, lập chỉ mục bài nộp/điểm để tránh quét lặp theo từng sinh viên/bài. |
| Tiến trình | Giới hạn 128 HTTP worker, backlog 128 và trả 503 khi quá tải. OS lease ngăn hai server hoặc các CLI bảo trì đã tích hợp cùng sửa một bộ dữ liệu. Khởi tạo/phục hồi metadata diễn ra sau khi lấy lease. |
| Vận hành | Backup có manifest/hash và kiểm tra file tham chiếu. Tự backup sau khởi động khoảng 30 giây rồi mỗi 6 giờ, giữ 7 backup tự động mới nhất. Có kiểm tra môi trường và chấm mẫu, endpoint readiness dành cho admin. |
| Đóng gói/test | Ignore dữ liệu runtime, backup, log và metadata AppleDouble. Có lệnh kiểm tra tổng hợp, cấu hình đường dẫn Python/Chrome cho test, kiểm thử lỗi ghi/khởi động lại/race/retry và benchmark tạm. |

Giao dịch này giữ định dạng JSON hiện có; chưa chuyển dữ liệu sang SQLite. Nó sử dụng khóa trong tiến trình, journal phục hồi và lease của server/CLI. Không hỗ trợ việc một chương trình bên ngoài bỏ qua lease rồi tự chỉnh JSON trong lúc server chạy. File payload được lưu trước và không bị thay thế giữa các lần nộp. Kiểm thử phục hồi đã chạy; chưa mô phỏng mất điện thật hoặc chứng nhận độ bền của mọi filesystem.

## Giao diện tài khoản đã được duyệt

- Hai cột riêng: **Tài khoản** và **Đăng nhập**.
- Hiển thị khóa đăng nhập tạm và thời gian còn lại; tự hết hiển thị khi đến hạn và cập nhật lại trạng thái từ server.
- Bộ lọc chỉ dành cho danh sách tài khoản: tài khoản mở/khóa, đăng nhập bị khóa tạm/không khóa tạm. Một tài khoản có thể đồng thời bị cả hai loại khóa.
- Đổi nhãn nút thành Khóa tài khoản, Mở tài khoản và Gỡ khóa tạm. Nút gỡ khóa tạm chỉ dùng được khi có khóa tạm.
- Có giải thích và xác nhận tác động. Mở/khóa dùng trạng thái đích rõ ràng, nên gửi lại request không đảo trạng thái lần thứ hai.
- Đặt lại mật khẩu cập nhật danh sách ngay; trạng thái active của tài khoản được xử lý riêng với việc gỡ khóa đăng nhập.

## Bằng chứng kiểm tra

- [Toàn bộ kiểm tra Python/JavaScript](../logs/backend-final-checks.log): bật `CSS_JUDGE_TESTS=1` để chạy Docker thật.
- [Kiểm tra trình duyệt và đăng nhập](../logs/backend-final-browser.log): gồm luồng tài khoản mới, luồng thi, thông báo, QR, bài tập và bảng điểm.
- [Kiểm tra môi trường dữ liệu thật](../logs/backend-live-doctor.log): không có lỗi tham chiếu, Docker sẵn sàng, chấm mẫu đạt.
- [Benchmark](../logs/backend-load.json): 30 sinh viên, 900 bài lịch sử, 30 request đồng thời mỗi pha. Workspace P95 243,8 ms; nhận bài tập P95 854,5 ms; 0 request lỗi, đúng 30 biên nhận mới.
- [Ảnh giao diện khóa đăng nhập](../previews/student-qa/admin-account-login-lock.png).

Benchmark chạy loopback, file nhỏ, Docker không bận chấm. Không suy ra sức chứa khi cả lớp upload file lớn hoặc Docker chấm đầy tải. Các test trình duyệt xác nhận luồng đã chạy, không thay thế kiểm tra mọi thiết bị và cấu hình mạng.

## Cách kiểm tra và phục hồi

```powershell
# Kiểm tra cú pháp JS, các helper UI và toàn bộ unittest.
$env:CSS_JUDGE_TESTS='1'
npm test

# Kiểm tra trình duyệt; có thể đặt CSS_TEST_PYTHON/CSS_TEST_CHROME.
npm run test:browser

# Kiểm tra môi trường trước khi chạy web (server đang dùng dữ liệu phải được dừng).
.\.venv-windows\Scripts\python.exe -m app.maintenance check --execute

# Backup thủ công khi web đã dừng; in ra đường dẫn backup mới.
.\.venv-windows\Scripts\python.exe -m app.maintenance backup

# Kiểm tra backup rồi phục hồi thử vào một thư mục mới/rỗng.
.\.venv-windows\Scripts\python.exe -m app.maintenance verify '<backup-path>'
.\.venv-windows\Scripts\python.exe -m app.maintenance restore-copy '<backup-path>' --target '<new-empty-path>'
```

`restore-copy` không ghi đè bộ dữ liệu đang dùng và không phục hồi session cũ. Có thể chạy server từ bộ dữ liệu phục hồi bằng `CSS_DATA_ROOT=<new-empty-path>` và một `CSS_PORT` khác để diễn tập. Khi chạy bình thường không đặt `CSS_DATA_ROOT`, vị trí dữ liệu hiện tại được giữ như trước. Endpoint `/api/admin/readiness` dành cho admin kiểm tra môi trường khi web đang chạy; `/health` là liveness.

Khi cài từ source sạch, cần có dependencies Python và static CSS đã build (`npm install`, `npm run build` nếu chưa có asset). Docker/image bộ chấm cần được chuẩn bị theo tài liệu bộ chấm.

## Các quyết định nghiệp vụ/giao diện vẫn cần duyệt

Các mục này không được âm thầm thay đổi trong đợt sửa kỹ thuật:

- Cấp lại mật khẩu demo, cưỡng chế đổi mật khẩu ban đầu và thống nhất chính sách độ dài mật khẩu.
- Quy tắc xuất bản/mở bài tập theo lịch; quyền của nhiều giảng viên theo khóa.
- Cách thoát editor bằng bàn phím, hiển thị biên nhận chi tiết và đồng bộ draft nhiều máy.
- Đối chiếu hoặc sửa dữ liệu lịch sử đã sai từ trước; bản sửa ngăn tái diễn, không tự suy đoán điểm/roster cũ.

Triển khai public vẫn cần cấu hình TLS/proxy/giám sát theo môi trường thật. Đợt này chưa thực hiện triển khai public hoặc chuyển database.
