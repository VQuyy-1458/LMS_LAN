# Kiểm tra mở thi, lịch thi và bản nháp giảng viên

## Mở kỳ thi trên web

1. Lưu đề, cấu hình và danh sách dự thi. Với thi file, chọn cấu hình và phân phối đề trước.
2. Đặt giờ bắt đầu, lưu đủ bài toán/test/ngôn ngữ và danh sách dự thi. Với thi file, phân phối đề xong là đủ điều kiện lên lịch.
3. Trang cấu hình hiển thị **Tự mở theo lịch** và đồng hồ chờ, hoặc chỉ rõ những mục còn thiếu. Không cần bấm mở thủ công; giảng viên có thể sửa cấu hình trước giờ thi.
4. Đến giờ, tiến trình nền mở kỳ thi trên máy chủ, không cần ai đang mở trình duyệt. Sinh viên chỉ được vào từ giờ đã đặt; vào muộn dùng thời gian còn lại của cả phòng.
5. Không đặt lịch thì dùng nút mở ngay. Màn hình kiểm tra tổng hợp vẫn giúp xem lại khóa học, danh sách, thời gian, đề và Docker; **không bắt buộc chấm thử lời giải chuẩn**, kể cả khi kết quả thử WA hoặc đổi image.

Chấm thử là công cụ tùy chọn, nằm trong mục thu gọn. Công cụ chạy trong Docker riêng, giới hạn một lượt chuẩn đồng thời, không tạo bài nộp/điểm sinh viên và không giữ khóa metadata trong lúc chạy. Mã lời giải chuẩn không được lưu vào dữ liệu server; chỉ lưu hash, kết quả và thông tin người kiểm tra. Thay đổi cấu hình/image làm kết quả thử cũ hết hiệu lực, không chặn việc mở thi.

Web/server phải đang chạy để tự mở. Sau khi server khởi động lại trong khoảng giờ thi, hệ thống mở theo mốc giờ gốc, không cấp thêm thời gian. Lịch đã hết toàn bộ thời gian hoặc còn thiếu cấu hình sẽ không tự mở. Lịch mở độc lập với Docker; Docker cần chạy để nhận và chấm bài code theo kiểm tra hiện có. Hủy giờ bắt đầu trước khi mở sẽ hủy tự mở theo lịch. Các kỳ thi đã mở/kết thúc được giữ nguyên.

Các endpoint điều khiển cũ vẫn phục vụ CLI/script tương thích; giao diện web dùng endpoint mở sau kiểm tra. Quyền admin và kiểm tra thời gian vẫn áp dụng cho cả hai luồng.

## Sửa thời gian khi chờ hoặc đang thi

- Khi code còn chờ tự mở, sửa trực tiếp cấu hình đã lưu. Với file đã phân phối hoặc kỳ thi đã mở, dùng **Điều chỉnh thời gian thi**.
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

Browser QA: `--auto-exams`, `--code-roster`, `--code-entry`, `--drafts`, `--timing`, `--enrollment`. Fixture roster/timing/auto-exams giả lập bộ chấm cho kiểm thử UI; kiểm thử `test_preflight_real_docker_reference_passes_sample_and_hidden_tests` dùng Docker thật khi bật `CSS_JUDGE_TESTS=1`.

Kết quả cập nhật tự mở: bộ thường 143 ca (138 đạt, 5 kiểm thử Docker tùy chọn bỏ qua). Ba luồng trình duyệt `--auto-exams`, `--timing`, `--code-roster` đạt, gồm desktop/mobile, không chấm thử vẫn mở, tự mở không có trình duyệt, đổi/hủy lịch, giữ nháp khi đến giờ, đồng hồ/giám sát và danh sách dự thi. Bảy kiểm thử tập trung được chạy lại sau kiểm tra danh sách đã phát đề. Kiểm thử Docker thật của bộ chấm vẫn là tùy chọn riêng, không chạy lại trong thay đổi lịch thi này.

Đã tạo backup có manifest hợp lệ, đối chiếu 5 bảng điểm trên dữ liệu hiện tại: điểm cũ giữ nguyên. Web được nạp lại và giữ nguyên mốc thời gian của kỳ thi đang mở.
