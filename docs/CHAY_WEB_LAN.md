# Chạy LMS_LAN bằng một lần nhấp

Nhấp đúp **`CHAY_WEB_LAN.bat`** trong thư mục `D:\Projects\LMS_LAN`. File `start_windows.bat` cũng gọi cùng trình khởi động này.

- Tự chọn môi trường Python đã có, chạy web trên tất cả giao diện mạng và mở trang đăng nhập.
- Cửa sổ hiển thị **Máy khác LAN** với IP hiện tại. Copy địa chỉ này cho các máy cùng mạng Wi-Fi/LAN.
- Giữ cửa sổ chạy web mở trong lúc sử dụng. Nhấn **Ctrl+C** để dừng. Nếu còn bài đang chấm, server chờ các lượt đang chạy và giữ các bài chờ cho lần khởi động sau.
- Nhấp file thêm lần nữa sẽ mở lại web đang chạy. Khi cổng 8080 bị ứng dụng khác dùng, tự chọn cổng trống tiếp theo và hiển thị đúng địa chỉ.

Lần đầu Windows có thể hỏi quyền quản trị: chọn **Yes** để tạo quy tắc Firewall cho đúng Python/cổng web, chỉ nhận kết nối từ mạng con LAN. Không tắt Windows Firewall. Nếu từ chối, web vẫn dùng trên máy chủ; mở lại file và cấp quyền để các máy khác truy cập.

Docker Desktop được kiểm tra và khởi động nếu đã cài. Nếu thiếu image chấm mặc định, trình khởi động tự build lần đầu, tiến độ ở `logs/lan-docker-build.log`; lần đầu này cần mạng để tải thành phần của image. Web mở ngay trong lúc bộ chấm chuẩn bị. Không có Docker thì các chức năng web vẫn chạy, chấm code chưa sẵn sàng.

Trình khởi động dùng tài khoản, đề và dữ liệu sẵn có. Nó không chạy script reset demo, tạo thi thử hay cấu hình lại mật khẩu admin.

Nếu chưa có môi trường Python, chạy `setup_windows.bat` một lần trước. Các tùy chọn dành cho kiểm tra kỹ thuật:

```powershell
.\CHAY_WEB_LAN.bat --check
.\.venv-windows\Scripts\python.exe -m app.lan_launcher --no-browser --skip-docker --skip-firewall --port 8081
```

`--check` chỉ in chẩn đoán, không bật web, Docker hoặc thay đổi Firewall. Các lỗi Firewall nằm ở `logs/lan-firewall.log`.
