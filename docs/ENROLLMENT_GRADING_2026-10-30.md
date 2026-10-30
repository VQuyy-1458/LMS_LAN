# Ngày tham gia và phạm vi tính điểm

## Quy tắc

- Khi thêm sinh viên, mặc định tính từ lúc tham gia: bài tập đã hết hạn và buổi học trước mốc đó không tự tính 0/vắng. Bài tập còn hạn vẫn phải làm, kể cả được đăng trước ngày tham gia.
- Trong Thêm sinh viên hoặc Nhập danh sách, giảng viên có thể chọn **Tính cả nội dung trước khi tham gia**. Lựa chọn chỉ áp dụng cho người mới được thêm; thành viên đang có giữ nguyên quy tắc.
- Bỏ rồi thêm lại sinh viên giữ mốc và chính sách trước đó, không xóa nghĩa vụ hoặc kết quả cũ.
- Điểm điều chỉnh thủ công vẫn được ưu tiên. Các bài/phiên được loại khỏi điểm tự động hiện **Không tính điểm** ở giao diện sinh viên và danh sách điểm danh của giảng viên.
- Khóa học tự nhận mọi tài khoản ghi nhận người được tạo sau khi bắt đầu theo dõi bằng thời điểm tạo tài khoản. Chuyển sang danh sách thành viên chọn riêng giữ mốc này.

## Tương thích dữ liệu cũ

Lần khởi động đầu sẽ ghi nhận các thành viên hiện có với `joined_at=null, include_previous=true`, giữ cách tính cũ vì không có ngày tham gia đáng tin cậy. Không suy đoán ngày hoặc tự sửa điểm lịch sử. Khởi tạo này có giao dịch và chạy lại không tạo thay đổi mới.

`enrollments` là metadata riêng của khóa học. API sinh viên chỉ trả chính sách của chính sinh viên đó, không trả bản đồ ghi danh hoặc danh sách MSSV của người khác. Gói xuất/nhập khóa học không mang theo các mốc ghi danh cá nhân.

## Kiểm chứng

Kiểm thử trên dữ liệu tạm gồm: thêm giữa kỳ, bài còn hạn, tính cả phần cũ, thêm lại, tự ghi danh, quyền xem, giữ điểm chỉnh tay và tính lặp an toàn. Luồng trình duyệt: `node tests/browser_student_qa.cjs --enrollment`.
