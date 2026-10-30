# Kiểm tra mở thi, lịch thi và bản nháp giảng viên

## Mở kỳ thi trên web

1. Lưu đề, cấu hình và danh sách dự thi. Với thi file, chọn cấu hình và phân phối đề trước.
2. Chọn **Lưu và kiểm tra mở thi** (code) hoặc nút mở thi file để xem màn hình kiểm tra.
3. Kiểm tra khóa học, loại kỳ thi, số người/danh sách, thời gian, số bài/tổng điểm, ngôn ngữ, file đề và trạng thái Docker.
4. Với code, nhập một lời giải chuẩn cho mỗi bài bằng một ngôn ngữ được phép rồi chấm thử toàn bộ test. Mỗi bài phải AC toàn bộ test mẫu và test ẩn mới xác nhận mở được.
5. Xác nhận mở. Có lịch tương lai thì phòng thi chờ đến giờ đó; không đặt lịch thì bắt đầu ngay. Nếu lịch đã hết thời gian, cần chỉnh lại trước khi mở.

Chấm thử chạy trong Docker riêng, giới hạn một lượt chuẩn đồng thời, không tạo bài nộp/điểm sinh viên và không giữ khóa metadata trong lúc chạy. Mã lời giải chuẩn không được lưu vào dữ liệu server; chỉ lưu hash, kết quả và thông tin người kiểm tra. Nếu cấu hình/danh sách/image thay đổi, kết quả cũ không đủ để xác nhận mở.

Các endpoint điều khiển cũ vẫn phục vụ CLI/script tương thích; giao diện web dùng endpoint mở sau kiểm tra. Quyền admin và kiểm tra thời gian vẫn áp dụng cho cả hai luồng.

## Sửa thời gian khi chờ hoặc đang thi

- Mở Cấu hình kỳ thi → **Điều chỉnh thời gian thi**.
- Khi đang chờ, đổi giờ bắt đầu và thời lượng hoặc giờ kết thúc cụ thể.
- Khi đang thi, giữ giờ bắt đầu thực tế; sửa thời lượng hoặc giờ kết thúc. Hệ thống cập nhật hạn của các lượt đã vào và sinh viên vào sau dùng cùng hạn mới.
- Thi file giữ phần gia hạn cá nhân. Thay đổi có audit. Không sửa thời gian kỳ thi đã kết thúc; dùng nút kết thúc để đóng ngay.
- Đề/test và roster tiếp tục khóa sau khi mở; chỉ phần thời gian được sửa. Editor/nháp đang viết được giữ khi nhận hạn mới.

Mốc thời gian hiển thị theo Việt Nam (UTC+7); server kiểm tra quyền vào bài/nộp bài, không dựa vào đồng hồ máy sinh viên. Trạng thái chờ được tính từ giờ bắt đầu của cửa sổ đã công bố; dữ liệu điều khiển cũ vẫn giữ trạng thái `started` để tương thích, API sinh viên hiển thị `scheduled` khi chưa tới giờ.

## Bản nháp giảng viên

- Đề/test case, danh sách thi code, cấu hình file, bài tập, học liệu, lịch học và thông báo có trạng thái **Chưa lưu** và bản nháp trên trình duyệt.
- Khóa nháp gồm tài khoản admin và ngữ cảnh nội dung. Khi quay lại có nút khôi phục/bỏ nháp; không tự đè dữ liệu đang lưu trên server. Nếu dữ liệu server khác bản gốc, hiện lưu ý trước khi khôi phục.
- Rời nội dung đang sửa có xác nhận; đóng/tải lại tab dùng cảnh báo trình duyệt. Lưu/gửi thành công xóa nháp tương ứng, lỗi lưu giữ nội dung.
- Mật khẩu và nội dung file nhị phân không được lưu trong nháp. Sau khôi phục phải chọn lại file đính kèm. Nháp nằm trên máy/trình duyệt hiện tại, không đồng bộ sang máy khác. Nếu không lưu được, giao diện báo rõ.

## API và kiểm thử

- `GET /api/admin/exam-preflight?exam=...`: báo cáo kiểm tra và kết quả thử.
- `POST /api/admin/exam-preflight/verify`: chấm thử bất đồng bộ, trả job ID.
- `POST /api/admin/exam-preflight/open`: xác nhận đúng fingerprint/cấu hình/image hiện tại.
- `POST /api/admin/exam-timing`: cập nhật cửa sổ thi được phép, có audit.
- Các endpoint trên chỉ dành cho admin. `exam_preflight.json` là dữ liệu runtime, không đưa lên GitHub.

Browser QA: `--code-roster`, `--code-entry`, `--drafts`, `--timing`, `--enrollment`. Fixture roster/timing giả lập bộ chấm cho kiểm thử UI; kiểm thử `test_preflight_real_docker_reference_passes_sample_and_hidden_tests` dùng Docker thật khi bật `CSS_JUDGE_TESTS=1`.

Kết quả bản cập nhật: bộ thường 136 ca (131 đạt, 5 kiểm thử Docker tùy chọn bỏ qua); 43 nhóm kiểm tra trình duyệt đạt, gồm các kích thước sidebar và giao diện desktop/mobile. Kiểm thử lời giải chuẩn Docker chạy riêng đạt AC 2/2 test (mẫu và ẩn), không tạo bài nộp sinh viên. Các bộ được chạy tuần tự sau khi xử lý sự cố Docker/môi trường Windows.

Đã tạo backup có manifest hợp lệ, đối chiếu 5 bảng điểm trên dữ liệu hiện tại: điểm cũ giữ nguyên. Web được nạp lại và giữ nguyên mốc thời gian của kỳ thi đang mở.
