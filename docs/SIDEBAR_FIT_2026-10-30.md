# Menu chức năng nằm trọn trong khung

Ngày 30/10/2026, áp dụng tại LMS_LAN.

- Menu admin dùng khoảng cách và chiều cao hàng thích ứng theo chiều cao viewport. Thu gọn phần thương hiệu, tài khoản và ghi chú trên màn hình thấp để mọi nút điều hướng đều hiện đủ.
- Giữ chiều cao huy hiệu độc lập với line-height của hàng, tránh huy hiệu làm menu phát sinh cuộn.
- Trên điện thoại xoay ngang, menu admin chuyển thành hai cột. Menu sinh viên cũng hiển thị đủ các mục cuối ở viewport cao 320px; phần trạng thái kết nối không tương tác được ẩn tại chiều cao rất thấp để dành chỗ cho các nút.
- Thêm phiên bản cho CSS menu ở template sinh viên và admin. Tab đang mở cần tải lại để nhận stylesheet mới.

Xác minh bằng `node tests/browser_student_qa.cjs --sidebar`: exit code 0. Có 32 trường hợp gồm trang sinh viên và ba biến thể trang admin (tài khoản, giám sát, khóa học), tại các viewport 1536×738, 1366×768, 1280×650, 1024×576, 1280×480, 390×664, 844×390 và 568×320.

Kiểm tra số lượng nút, vị trí trong viewport, không tràn/cuộn menu và hit-test tại tâm từng nút để phát hiện nút bị che. Kiểm tra này cũng được tích hợp trong bộ browser QA đầy đủ.

Log: `logs/sidebar-fit-browser.log`. Ảnh: `previews/student-qa/sidebar-admin-1536x738.png`, `sidebar-admin-568x320.png`, `sidebar-student-landscape.png`.
