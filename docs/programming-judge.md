# Chấm thi lập trình

## Chuẩn bị

Docker Desktop cần chạy Linux containers. Tạo image từ thư mục project:

```powershell
docker build -t classroom-judge:1 ./judge
```

Máy hiện tại đã tạo image này. Image có C17 (gcc), C++17 (g++), Java 17 và
Python 3. Server không tự kéo image khi chấm. Có thể chọn image tương thích
khác bằng biến `CSS_JUDGE_IMAGE` khi khởi động server.

## Luồng sử dụng

1. Vào Cấu hình kỳ thi trên sidebar, tạo loại Thi lập trình.
2. Thêm bài toán, điểm tối đa, ngôn ngữ, thời gian/bộ nhớ và test (nhập tay/CSV).
3. Bấm Lưu và mở kỳ thi. Mỗi bài phải có ít nhất một test. Cấu hình và bộ test
   được khóa khi mở thi. Danh sách dự thi lấy từ thành viên đang hoạt động.
4. Sinh viên vào Kỳ thi, bấm Bắt đầu thi lập trình để tính thời lượng riêng.
   Chỉ đề và test mẫu được gửi xuống trình duyệt sau khi bắt đầu.
5. Nộp một file mã nguồn UTF-8 cho từng bài: .c, .cpp, .java hoặc .py, tối đa
   100.000 byte. Java dùng lớp public Main, không khai báo package.
6. Server xếp hàng và chấm tự động. Input mỗi test đưa vào stdin; stdout so
   với output mong đợi. Chương trình không nên in lời nhắc nhập dữ liệu.
7. Sinh viên xem trạng thái, điểm, số test đạt. Chi tiết input/output/stderr
   chỉ có ở test mẫu; test ẩn không trả dữ liệu đó cho tài khoản sinh viên.
   Admin xem được toàn bộ và tải mã nguồn/chấm lại ngay trong trang cấu hình.
8. Kết thúc kỳ thi chặn mọi lần nộp mới; bài đã nhận vẫn được chấm. Không thể
   tổng kết khóa học trong lúc kỳ thi lập trình còn mở.

Có thể nộp lại khi còn thời gian. Giao diện hiển thị điểm cao nhất từng bài;
điểm thi chưa tự ghi đè điểm thành phần của bảng điểm khóa học.

File gốc được giữ nguyên byte, kể cả UTF-8 BOM; bộ chấm chỉ bỏ BOM ở bản sao
biên dịch tạm. Mỗi lần chấm có ID, thời điểm, kết quả và người yêu cầu riêng
trong grading_history. Chấm lại không xóa kết quả trước; test ẩn của mọi lần
chấm đều được lọc khỏi API sinh viên. Khi lỗi hạ tầng, điểm hợp lệ trước vẫn
được dùng để hiển thị điểm tốt nhất.

Mục Bài nộp tra cứu chung code/file, xem nội dung từng phiên bản, kết quả,
lịch sử chấm và tải ZIP/CSV. Mỗi tài khoản chỉ nộp tối đa sáu lần thành công
trong 60 giây, cộng chung code và file. Chấm lại của admin không tính là lần
nộp mới của sinh viên.

## So sánh và tính điểm

- Theo token: bỏ khác biệt khoảng trắng và xuống dòng giữa các token.
- Chính xác: giữ khoảng trắng và xuống dòng cuối; chuẩn hóa CRLF thành LF.
- Điểm bài toán = điểm tối đa × số test AC / tổng số test. Mọi test có trọng
  số như nhau, kể cả test mẫu và ẩn. Chưa hỗ trợ checker tùy biến/chấm số thực.
- AC: đúng; WA: sai output; CE: lỗi biên dịch; RE: lỗi chạy; TLE: quá giờ;
  MLE: bị container dừng do bộ nhớ; OLE: vượt giới hạn output.
- Lỗi hạ tầng chấm ghi SYSTEM_ERROR, không gán 0 điểm; giữ bài để chấm lại.

## Môi trường chạy

Biên dịch một lần trong container riêng, sau đó mỗi test chạy container mới.
Các [tùy chọn Docker](https://docs.docker.com/engine/containers/run/) gồm:
network none, user không phải root, drop toàn bộ capabilities, no-new-privileges,
root filesystem chỉ đọc, CPU 1, giới hạn RAM/swap và số tiến trình. Container
chỉ được gắn thư mục tạm của bài đang chấm; khi chạy, thư mục này chỉ đọc.
Không gắn data, tài khoản, bộ test hay Docker socket. Output mong đợi luôn
ở server; mỗi container chỉ nhận input của test hiện tại qua stdin.

Giới hạn: 100 test/bài; stdout tối đa 1 MiB và stderr 64 KiB mỗi test (lưu
tối đa 16.000 ký tự output/4.000 ký tự stderr để xem). Thời gian thi khác giới
hạn chạy từng test. Bộ nhớ tính trên toàn container, bao gồm trình thông dịch
hoặc JVM; Java nên có ít nhất 128–256 MB. Toàn lượt chạy test có ngân sách
180 giây; quá ngân sách được báo lỗi hạ tầng để điều chỉnh cấu hình/chấm lại.

Hai bài được chấm đồng thời. Hàng đợi tối đa 50 bài, mỗi sinh viên tối đa hai
bài đang chờ/chấm. Mã nguồn và bản sao bộ test của từng lần nộp nằm trong
`programming-submissions/`, kết quả/attempt trong `data/programming_*.json`.
Chấm lại dùng đúng bản sao test lúc nộp. Bài đang chờ/chấm khi server bị tắt
được xếp lại khi khởi động bằng `run_server.py`.

## Kiểm tra thật qua Docker

```powershell
$env:CSS_JUDGE_TESTS='1'
.\.venv-windows\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
node tests/browser_student_qa.cjs
```

Các kiểm thử dùng dữ liệu tạm, gồm cả bốn ngôn ngữ, sai output/điểm một phần,
lỗi biên dịch, lỗi chạy, quá giờ, output lớn, khóa mạng, bảo vệ test ẩn,
deadline, lưu kết quả và chấm lại. Khi không đặt CSS_JUDGE_TESTS, các bài kiểm
tra chạy container thực được bỏ qua.
