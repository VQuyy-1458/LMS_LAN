# Bộ lọc và bố cục kết quả học tập — 30/10/2026

Áp dụng trong LMS_LAN cho giao diện sinh viên và giảng viên/admin.

## Thay đổi

- Dùng chung màu xanh, viền, chiều cao, trạng thái chọn/focus và menu cho các bộ lọc. Menu nằm trong top layer khi trình duyệt hỗ trợ, hiển thị đầy đủ lựa chọn dài trong viewport và trong dialog.
- Tăng/giảm dùng hai lựa chọn cạnh nhau bằng radio native, có nhãn và biểu tượng. Áp dụng cả ở kho bài nộp và trang Thông báo; giữ focus khi nội dung được render lại.
- Giữ tiêu chí lọc riêng của từng danh sách và quy tắc số/chữ/thời gian. Kỳ thi, bài tập vẫn theo thứ tự đang mở, sắp diễn ra, đã đóng.
- Gom tìm kiếm, lọc và sắp xếp tài khoản/giám sát vào thanh điều khiển chung. Xóa bộ lọc xử lý cả nội dung tìm kiếm; giữ văn bản vừa nhập khi đổi bộ lọc/thứ tự trong thời gian debounce.
- Bảng điểm sinh viên được chèn trước phần điểm bài tập trong nội dung tab Kết quả. Tiêu đề khóa học, breadcrumb và các tab luôn ở phía trên, kể cả sau khi tìm kiếm hoặc sắp xếp.
- Bảng điểm khóa học có nhãn sắp xếp và gợi ý tìm kiếm theo tên khóa học. Biểu tượng tìm kiếm có khoảng cách riêng với chữ.
- Khóa đã tổng kết vẫn chọn được trong các bộ lọc tra cứu. Bộ lọc khóa học ở lịch sử nộp bài áp dụng cho bài tập, bài thi file và bài thi code.
- Thêm phiên bản vào đường dẫn các tài nguyên bộ lọc trong template chung. Các tab đang mở cần tải lại trang để nhận mã JavaScript mới.

## Xác minh

Chạy `node tests/run_checks.cjs --browser`: exit code 0, 37 nhóm kiểm tra thành công, bao gồm helper và trình duyệt cho cả hai vai trò. Các kiểm tra trình duyệt dùng server và dữ liệu thử tách riêng.

Đã kiểm tra menu chọn bằng chuột/bàn phím, Escape, form required trong dialog, viewport mobile/HiDPI, xóa bộ lọc, thứ tự thông báo, bảo toàn ô điểm đang sửa và thứ tự hình học tiêu đề → tab → bảng điểm trên desktop/mobile. Fixture có thêm khóa đã tổng kết để kiểm tra chọn và tra cứu lịch sử.

Đã đối chiếu nội dung sáu tài nguyên bộ lọc/bảng điểm đang được server LAN trả về với file trong LMS_LAN; HTTP 200 và Cache-Control `no-store`.

Log: `logs/filters-design-browser.log`. Kết quả tiến trình: `logs/filters-design-result.txt`.

Ảnh kiểm tra trong `previews/student-qa/`:

- `student-course-grades-header-desktop.png`, `student-course-grades-header-mobile.png`
- `filters-admin-accounts-desktop.png`, `filters-student-materials-desktop.png`
- `filters-archive.png`, `filters-mobile.png`
- `notifications-desktop.png`, `notifications-mobile.png`
