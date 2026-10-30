# Danh sách dự thi riêng cho thi lập trình

Trong Cấu hình kỳ thi → chọn kỳ thi lập trình, có phần **Đối tượng được vào thi** với tìm MSSV/họ tên, tăng/giảm theo MSSV, checkbox, chọn tất cả kết quả đang lọc, bỏ chọn và dán MSSV theo dòng/dấu phẩy. Lựa chọn không bị mất khi tìm kiếm hoặc sắp xếp.

- Nút **Lưu danh sách dự thi** lưu riêng danh sách, bảo toàn các ô đề bài/test case đang sửa. **Lưu thiết lập kỳ thi** và **Lưu và mở kỳ thi** cũng lưu lựa chọn đang hiển thị.
- MSSV chưa có tài khoản được tạo với tên “Chưa cập nhật”, mật khẩu ban đầu là MSSV và cờ yêu cầu đổi mật khẩu. Tài khoản đã có giữ nguyên mật khẩu.
- Kỳ thi chung cho phép tạo MSSV mới. Kỳ thi thuộc khóa học chỉ nhận thành viên khóa học; cần thêm sinh viên vào khóa học trước. Tài khoản bị khóa không được thêm vào danh sách.
- Danh sách gắn với từng kỳ thi code, độc lập với các kỳ thi code khác và kỳ thi file. `participants_configured` đánh dấu danh sách đã chọn để việc lưu cấu hình/mở thi không lấy lại toàn bộ thành viên.
- Đổi khóa học đặt lại danh sách theo khóa mới. Giao diện yêu cầu lưu cấu hình và xem danh sách mới trước khi mở thi.
- Kỳ thi đã mở/kết thúc hoặc khóa học đã tổng kết khóa chỉnh sửa danh sách. Backend kiểm tra lại thành viên và trạng thái tài khoản ngay lúc mở thi.
- Sinh viên ngoài danh sách bị chặn ở workspace, bắt đầu thi và gửi code. Tạo tài khoản cùng lưu danh sách nằm trong một transaction; lỗi ghi dữ liệu không để lại tài khoản dở dang.

API: `POST /api/admin/programming/participants` với `exam_id`, `course_id`, `student_ids`. Cấu hình code nhận thêm `participant_ids` trong API lưu cấu hình. API chỉ dành cho admin.

## Kiểm tra

- `node tests/run_checks.cjs`: 125 kiểm tra Python, 121 đạt và 4 kiểm tra Docker tùy chọn bỏ qua; các kiểm tra cú pháp JS/helper đạt.
- `node tests/run_checks.cjs --browser`: 39 nhóm kiểm tra đạt, bao gồm sidebar và luồng danh sách dự thi mới.
- `node tests/browser_student_qa.cjs --code-roster`: kiểm tra riêng tìm/chọn/dán/trùng MSSV, đăng nhập bằng tài khoản mới, lưu độc lập, lưu cùng đề, đổi khóa học đang chỉnh, giao diện desktop/mobile, mở thi với danh sách đã chọn và từ chối sinh viên ngoài danh sách. Riêng fixture này giả lập Docker sẵn sàng để kiểm tra vận hành/danh sách; không dùng nó để xác nhận kết quả chấm Docker.

Log: `logs/code-roster-all-backend.log`, `logs/code-roster-all-browser.log`, `logs/code-roster-browser.log`.

Ảnh phần giao diện: `previews/student-qa/code-exam-participants-desktop.png`, `previews/student-qa/code-exam-participants-mobile.png`.

## Kiểm tra khi khởi động thực tế

Web chạy lại tại cổng 8080, giữ dữ liệu trong LMS_LAN. Docker Desktop đã khởi động lại thành công; image `classroom-judge:1` sẵn sàng và chương trình Python `print(3)` được chấm AC (1/1 test).

Khi chạy server phát hiện lỗi sao lưu tự động: biến tên thư mục snapshot bị vòng lặp metadata ghi đè bằng tên file JSON. Đã dùng `snapshot_name` riêng và bổ sung hồi quy tạo hai snapshot liên tiếp. Hai kiểm tra backup/restore đạt; bản backup tự động thực tế sau khi nạp sửa đã xác minh thành công 183 file.
