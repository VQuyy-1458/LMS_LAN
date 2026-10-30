# Đồng hồ chờ và giám sát theo kỳ thi

- Giảng viên thấy đồng hồ giờ : phút : giây trên danh sách kỳ thi, trong khóa học và trang cấu hình khi kỳ thi đã mở nhưng đang chờ lịch. Sinh viên thấy đồng hồ trên danh sách và trang vào thi, cho cả code và file.
- Đồng hồ dùng thời gian máy chủ; đổi lịch sẽ cập nhật theo lần đồng bộ tiếp theo. Đến giờ bắt đầu, trang tự cập nhật trạng thái. Cập nhật đồng hồ không xóa nội dung giảng viên đang sửa.
- Mỗi kỳ thi đang diễn ra có nút **Giám sát** trên danh sách, trong khóa học và trang cấu hình. Liên kết mang mã kỳ thi; trang giám sát có bộ chọn kỳ thi và thông tin lịch để phân biệt nhiều kỳ thi cùng khóa học.
- API `GET /api/admin/monitor?exam=<id>&course=<optional>` chỉ dành cho admin. Danh sách giới hạn theo thí sinh của kỳ thi; lượt làm, thời gian và bài nộp không lẫn kỳ thi khác. Thi file lọc theo mã phát đề (`release_id`).
- Với code, cột **Bài đã AC / Tổng bài** hiển thị ví dụ `2/5 bài`. Mỗi bài chỉ tính một lần nếu có ít nhất một lần chấm AC có hiệu lực. WA/đang chấm không tăng số bài AC. Chấm lại thất bại do hệ thống giữ kết quả có hiệu lực trước đó, cùng quy tắc với điểm hiện tại. Giám sát tự đồng bộ mỗi 5 giây.
- **Xem bài nộp** chuyển đến kho bài nộp đã lọc đúng sinh viên và kỳ thi, gồm tất cả bài toán của kỳ thi code. Bộ lọc kỳ thi được giữ khi đổi các bộ lọc khác.
- Các nút ép nộp/gia hạn cá nhân của bộ thi file không xuất hiện ở giám sát code. Chỉnh lịch code bằng **Cấu hình / Điều chỉnh thời gian thi**. Backend chặn đường dẫn giám sát code hoặc lượt phát đề cũ thao tác nhầm lên bài thi file hiện tại.

Kiểm chứng: hai kiểm thử API trong `tests/test_learning.py` kiểm tra phạm vi kỳ thi/khóa học/quyền, AC không trùng, chấm lại, lịch sử code và các lượt phát đề file. `node tests/browser_student_qa.cjs --timing` kiểm tra đồng hồ hai vai trò, desktop/mobile, thay lịch giữ nháp, tự đến giờ, liên kết giám sát code/file, AC tự cập nhật, kho bài nộp đúng kỳ thi và editor sinh viên được giữ khi gia hạn.
