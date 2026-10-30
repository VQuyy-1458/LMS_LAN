# Thông tin thời gian trước khi vào thi lập trình

- Trước khi vào làm bài, sinh viên thấy giờ bắt đầu đã đặt, hạn kết thúc chung và đồng hồ đếm ngược theo giờ máy chủ. Mốc giờ hiển thị theo Việt Nam (UTC+7).
- Nút đổi thành **Vào làm bài**. Nếu có lịch bắt đầu, mở kỳ thi sớm sẽ đưa vào trạng thái chờ; sinh viên chưa được vào bài. Nội dung giải thích rằng vào muộn chỉ còn thời gian của phòng thi; thao tác vào bài không bắt đầu lại thời lượng.
- Sau khi vào vẫn mở danh sách bài toán trước, rồi mới vào trang làm từng bài. Đề và test ẩn giữ nguyên quy tắc truy cập hiện có.
- Hết giờ khóa nút vào bài. Phòng thi bị kết thúc sớm hiển thị **Đã kết thúc**, không tiếp tục đếm ngược.
- API workspace bổ sung `started_at` cho kỳ thi code. Nếu có lịch, hạn chung tính từ giờ bắt đầu đó; các kỳ thi đã mở trước bản cập nhật giữ mốc đang lưu.

Luồng lịch thi và thay đổi thời gian tiếp theo được mô tả tại [hướng dẫn cập nhật](EXAM_WORKFLOWS_2026-10-30.md).

## Kiểm chứng

- Hai kiểm thử backend: đồng hồ chung/vào muộn/hết giờ và vòng đời thi/quyền xem đề/chấm lại đều đạt trên dữ liệu tạm.
- `node tests/browser_student_qa.cjs --code-entry`: kiểm tra giờ mở/kết thúc, đếm ngược trực tiếp, desktop/mobile, khóa nút khi hết giờ, hạn giữ nguyên sau khi vào, đề/test ẩn và kết thúc sớm.
- Fixture `--code-entry` chỉ giả lập Docker sẵn sàng để kiểm tra luồng vào phòng; không sử dụng dữ liệu thật và không chạy chấm Docker trong kiểm thử này.
- Kiểm tra cú pháp JavaScript và `git diff --check` đạt. Web đã khởi động lại và xác nhận phục vụ script cập nhật.
