# Bộ dữ liệu để thử hệ thống

Tạo bằng `python -m app.seed_demo --apply`. Bộ mẫu thêm dữ liệu riêng, không đổi
mật khẩu tài khoản cũ và không xóa bài nộp cũ. Ngày giờ được tính theo lúc tạo
dữ liệu, với lịch/hạn nộp hiển thị theo giờ Việt Nam.

## Đăng nhập

- Admin: dùng tài khoản admin hiện tại (`admin`, mật khẩu đã được bạn đặt).
- Sinh viên mẫu: `DEMO001` đến `DEMO020`, mật khẩu ban đầu **111111**.
- `DEMO001`–`DEMO008`: Lập trình mạng và Lập trình căn bản đã tổng kết.
- `DEMO009`–`DEMO016`: Lập trình mạng và Cơ sở dữ liệu.
- `DEMO017`–`DEMO020`: chỉ Cơ sở dữ liệu; dùng để kiểm tra phân quyền khóa.

Các tên và kết quả trong bộ này là dữ liệu giả lập phục vụ kiểm thử.

## Dữ liệu có sẵn

| Khóa | Sĩ số | Trạng thái | Bài tập |
| --- | --- | --- | --- |
| Lập trình mạng · LTM-DEMO-01 | 16 | Đang học | 5 |
| Cơ sở dữ liệu · CSDL-DEMO-02 | 12 | Đang học | 5 |
| Lập trình căn bản · LT-DEMO-03 | 8 | Đã tổng kết, chỉ xem | 3 |

- Mỗi khóa có 3 học liệu thật có thể tải/xem và 3 thông báo.
- Hai khóa đang học có 12 buổi học/khóa, bài quá hạn và bài còn hạn, lịch sử
  nộp lại, các bài đã chấm và chờ chấm, điểm giữa kỳ và lịch sử điểm danh.
- Mỗi khóa đang học có một phiên điểm danh mở trong 24 giờ kể từ lúc tạo mẫu.
- Khóa đã tổng kết có đầy đủ điểm để xem kết quả và kiểm tra việc khóa sửa/nộp.
- Có 14 thông báo chung/riêng để thử chuông, phân trang, lọc và trạng thái đọc.
- Có 2 file đề thi văn bản và một ZIP bài làm tại `demo-inputs/DEMO001_bai_lam.zip`.

## Các bước thử đề xuất

1. Đăng nhập admin, mở Dashboard, Khóa học và chọn Lập trình mạng. Xem tài liệu,
   lịch, danh sách lớp, bài tập, điểm danh và bảng điểm.
2. Mở cửa sổ ẩn danh/trình duyệt khác, đăng nhập `DEMO001 / 111111`. Hai vai trò
   dùng cookie riêng; tránh đăng nhập admin và sinh viên trong các tab chung
   một hồ sơ trình duyệt vì cookie có thể thay thế nhau.
3. Chọn **Bài tập 03 – Truyền file trong mạng LAN**, nộp ZIP tại `demo-inputs/`.
   DEMO001 chưa nộp bài này nên bạn có thể thử nộp lần đầu và nộp lại.
4. Quay lại admin → Bài nộp → Lập trình mạng → Bài tập 03. Mở Chấm bài, lưu điểm
   và nhận xét. Sinh viên tải lại để xem lịch sử và kết quả mới.
5. Admin mở Điểm danh của khóa và mở/tạo phiên còn hiệu lực để hiện QR.
   Sinh viên DEMO001 mở Điểm danh ở sidebar → Mở máy ảnh quét QR. Đọc được QR
   sẽ tự nhận đúng buổi và ghi có mặt, không chọn phiên/nhập mã/xác nhận lần nữa.
   Nếu phiên mẫu 24 giờ đã hết hạn, tạo phiên mới. Trên HTTP LAN, điện thoại
   dùng camera chụp QR rồi hệ thống tự giải mã; HTTPS/localhost quét video trực
   tiếp. Bảng giảng viên tự nhận kết quả. Lọc lịch sử sinh viên theo khóa/trạng
   thái sẽ cập nhật ngay, không cần Áp dụng.
6. Vào Thông báo, thử mở chuông, xem chi tiết, lọc chưa đọc và đánh dấu tất cả.
7. Thử khóa CSDL bằng DEMO017, xác nhận tài khoản này không được truy cập các
   file và dữ liệu của khóa Lập trình mạng.
8. Thử khóa Lập trình căn bản đã tổng kết: vẫn xem tài liệu, lịch sử và điểm,
   nhưng không thể nộp hoặc sửa nội dung.

## Thử kỳ thi nộp file và giám sát

Nếu lúc tạo mẫu không có kỳ thi đang hoạt động, bộ mẫu chuẩn bị sẵn lượt thi
60 phút cho 16 sinh viên Lập trình mạng, phân phối xen kẽ đề A/B, tối đa 3 lần
nộp. Trạng thái ban đầu là **Chờ bắt đầu**, không tự chạy đồng hồ.

1. Admin → Cấu hình kỳ thi → Lập trình mạng → nhấn **Bắt đầu kỳ thi**.
2. Sinh viên DEMO001 → Kỳ thi → chọn kỳ thi trong danh sách → Bắt đầu làm bài
   → mở đề → nộp ZIP mẫu. Trong khóa học cũng có tab Kỳ thi dùng cùng dữ liệu.
3. Admin → Giám sát → Lập trình mạng. Quan sát IP, trình duyệt, thời gian, số
   lần nộp và trạng thái đăng nhập; thử điều chỉnh giờ hoặc ép nộp với tài khoản
   mẫu khác đang thi.
4. Thử chuyển tab/cửa sổ của sinh viên để quan sát cảnh báo sau lần đồng bộ.

Không tạo phiên online, IP hay cảnh báo giả. Chúng chỉ xuất hiện khi có tương tác
thực tế. Bộ dữ liệu này dùng thi nộp file. Để thử chấm mã nguồn tự động,
tạo kỳ thi loại Thi lập trình, thêm test và mở thi theo
[hướng dẫn bộ chấm](programming-judge.md).

Nếu lúc tạo dữ liệu đã có kỳ thi đang phát/đang chạy, lượt thi đó được giữ
nguyên. Sau khi kết thúc, bạn có thể chọn khóa mẫu và các file `DEMO_De_Thi_A.txt`,
`DEMO_De_Thi_B.txt` để thiết lập lượt thi mới.

## Sao lưu và chạy lại

Trước khi thêm mẫu, các file dữ liệu gốc được sao lưu vào
`backups/before-demo-YYYYMMDD-HHMMSS/data/`. Vị trí chính xác được ghi trong
`data/demo_seed.json`. Muốn khôi phục, dừng server trước rồi khôi phục các file
JSON từ bản sao lưu; lưu riêng mọi bài nộp mới cần giữ.

Script chạy lại sẽ báo `already-seeded`, không nhân bản khóa, đổi mật khẩu mẫu
đã sửa hoặc ghi đè bài bạn vừa thử nộp. Hết hạn điểm danh thì admin tạo phiên mới.
