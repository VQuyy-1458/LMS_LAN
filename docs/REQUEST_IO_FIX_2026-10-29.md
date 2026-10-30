# Sửa F01: request gửi dở làm nghẽn hệ thống

Phạm vi được duyệt: ngăn quá trình nhận/gửi dữ liệu mạng giữ khóa học tập dùng chung; kiểm tra quyền quản trị sớm; giới hạn thời gian nhận dữ liệu.

## Thay đổi

- Kiểm tra Origin và quyền admin trước khi đọc body của `/api/admin/`.
- Nhận và phân tích body ngoài `learning.LOCK`. Các cập nhật admin vẫn được tuần tự hóa trong khóa; quyền được kiểm tra lại khi xử lý để chặn phiên bị thu hồi trong lúc upload.
- Hoãn gửi phản hồi admin đến sau khi nhả khóa, để client nhận chậm không giữ khóa dữ liệu.
- Timeout mặc định: tối đa 30 giây không nhận được dữ liệu; tối đa 300 giây cho việc đọc một body, kể cả client gửi nhỏ giọt liên tục. Có thể cấu hình bằng `CSS_REQUEST_IDLE_TIMEOUT` và `CSS_REQUEST_BODY_TIMEOUT`, đơn vị giây, giá trị hữu hạn lớn hơn 0.
- Body bị bỏ dở trả 400; quá hạn trả 408. Các lỗi trước khi nhận đủ body đóng kết nối để phần còn lại không bị hiểu là request keep-alive kế tiếp.

Giới hạn 50 MiB hiện có được giữ. Kiểm tra tính hợp lệ của Content-Length là mục F02, cần phê duyệt riêng; bản sửa F01 không được coi là đã xử lý F02. Giới hạn tổng số kết nối/thread và kiểm thử tải cả lớp cũng chưa thuộc bản sửa này.

## Kiểm tra

`tests/test_http_requests.py` bổ sung 11 test hồi quy với dữ liệu tạm:

1. Chưa đăng nhập bị từ chối trước body.
2. Sinh viên không được gọi API admin trước body.
3. Origin sai bị từ chối trước body.
4. Upload admin dang dở không chặn đăng nhập, workspace và nộp bài tập.
5. Upload bị treo hết hạn và không gửi thông báo.
6. Vẫn tải đề/nộp bài thi file được khi upload admin chưa xong.
7. Gửi nhỏ giọt không kéo dài quá hạn tổng.
8. Body thiếu bị từ chối và không cập nhật dữ liệu.
9. Session bị thu hồi trong lúc upload không được thực hiện thao tác.
10. Gửi phản hồi chậm không giữ khóa học tập.
11. Multipart lớn hơn một chunk giữ đúng nội dung file.

Toàn bộ **85 test Python đạt**, có bật `CSS_JUDGE_TESTS=1` để chạy Docker thật. Bộ trình duyệt cũng đạt **25 nhóm**, bao gồm thi lập trình, thông báo, điểm danh, bài tập và bảng điểm; không có lỗi JavaScript/CSP trong các luồng được chạy.

Bằng chứng: [unittest](../logs/request-isolation-full-tests.log), [trình duyệt](../logs/request-isolation-browser-tests.log). Kết quả chỉ chứng minh các tình huống đã chạy, không phải benchmark sức chịu tải của lớp.

Đã nạp bản sửa bằng cách khởi động lại web sau khi xác nhận không có bài đang chấm. Kiểm tra server đang chạy: `/health` trả 200; POST admin chưa đăng nhập, khai báo body nhưng không gửi body, được trả 401 và đóng kết nối sau khoảng 0,015 giây. Các request workspace/monitor từ trình duyệt thực tế tiếp tục trả 200 sau khởi động.
