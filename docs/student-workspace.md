# Không gian học tập của sinh viên

## Mục tiêu và nguồn đối chiếu

Phần student được xây dựng lại từ trang nộp bài thành không gian học tập. Luồng
tham khảo từ mã nguồn LAN-LMS trong `D:\Projects\LAN-LMS`, đặc biệt:

- `client/src/features/courses/`: Dashboard, Workspace, MaterialsPanel,
  CalendarPanel, AttendancePanel, AssignmentsPanel, ExamsPanel, GradebookPanel.
- `client/src/components/`: AppShell, CourseTreeNav, AttendanceScanner, FilePreview.
- `client/src/lib/decodeQrImage.ts`, các trang `client/src/app/student/` và trang
  đổi mật khẩu.
- Các module server courses, materials, assignments, attendance, gradebook,
  coding_exams; tài liệu `PRACTICAL_WORKFLOWS.md`, `LIFECYCLE_AND_DATA.md`.

Giao diện sử dụng sidebar tối, màu xanh, typography, nút, thẻ và bảng của
Classroom Submission Server. Không chuyển framework Next.js/FastAPI hoặc dữ liệu
tài khoản/khóa học của LAN-LMS vào project hiện tại.

## Các màn sử dụng

| Màn | Đường dẫn | Chức năng |
| --- | --- | --- |
| Tổng quan | `/student/dashboard` hoặc `/` | Lời chào, thống kê thật, việc cần làm, lịch tháng, hoạt động sắp tới, khóa học |
| Khóa học | `/student/courses` | Tìm theo tên/mã/học kỳ, lọc đang học/đã tổng kết, mở từng khóa |
| Chi tiết khóa | `/student/courses?course=ID` | Header khóa và các tab Tài liệu (mặc định), Bài tập, Lịch học, Kỳ thi, Kết quả; không có Tổng quan/Điểm danh trong khóa |
| Lịch | `/student/calendar` | Lịch tháng tương tác, buổi học/thông báo/lịch thi và hạn bài tập |
| Điểm danh | `/student/attendance` | Mở camera/quét ảnh và tự xác nhận đúng buổi từ QR, không chọn phiên/nhập mã; lịch sử dạng hàng lọc theo khóa, kết quả, trạng thái phiên |
| Bài tập | `/student/assignments` | Lọc theo khóa/trạng thái, yêu cầu, hạn nộp, nộp/nộp lại, lịch sử, điểm và phản hồi |
| Kỳ thi | `/student/exams` | Danh sách gọn; chọn kỳ thi mở chi tiết nộp file hoặc lập trình, làm bài và nhận kết quả thật |
| Lịch sử | `/student/history` | Bài tập/bài thi đã nộp, thời gian, tải lại file còn lưu |
| Kết quả | `/student/grades` | Điểm cá nhân từng bài, nhận xét, điểm thành phần và tổng kết có trọng số |
| Thông báo | `/student/notifications` | Thông báo chung, riêng và thông báo của các khóa được tham gia |
| Tài khoản | `/student/profile` | Thông tin sinh viên, đổi mật khẩu, thu hồi phiên đăng nhập sau khi đổi |

Các danh sách chính của sinh viên được phân trang 10 mục. Lịch tháng và bộ chọn
khóa không cắt bớt dữ liệu điều hướng. Dashboard hiển thị một số hoạt động gần
nhất và liên kết đến màn đầy đủ. Dữ liệu được kiểm tra lại mỗi 10 giây; thông báo
cập nhật tự áp dụng cho danh sách khi không nhập/chọn file hoặc đang quét QR;
khi đang thao tác, giữ form và báo có cập nhật để người dùng chủ động tải.

Các bộ lọc sinh viên áp dụng ngay khi chọn; tìm kiếm cập nhật sau khoảng
220 ms nhập chữ. Không có nút Áp dụng. Tài liệu chỉ có tên, nội dung tóm tắt,
ngày đăng, xem trực tiếp/tải về. Bài tập hiển thị tên, khóa, hạn nộp và trạng
thái; nhấn vào để mở hộp chi tiết với yêu cầu, nộp bài và lịch sử. Lịch học và
lịch sử điểm danh cũng mở hộp chi tiết khi nhấn tên. Màu, sidebar và header/tab
khóa học dùng cùng cấu trúc với phía giảng viên, chỉ giữ chức năng của sinh viên.

Điểm danh nằm riêng ở sidebar. Camera trực tiếp dùng getUserMedia + ZXing;
Permissions-Policy cho camera cùng origin. HTTPS/localhost cho phép quét video,
HTTP LAN trên điện thoại chuyển nút mở camera sang camera chụp QR, ảnh được
giải mã và gửi check-in tự động. Có chọn ảnh để dùng khi không có camera.
QR chỉ cung cấp ID phiên và mã; không điều hướng/gửi yêu cầu tới host trong QR,
nên cùng server qua localhost, IP LAN và HTTPS vẫn nhận được phiên. Backend
kiểm tra quyền khóa, mã, thời hạn/đóng phiên. Quét lại không tạo bản ghi trùng;
không tự thay quyết định Vắng của giảng viên. Link QR qua đăng nhập giữ phiên
để đăng nhập xong tự điểm danh, đồng thời chặn next URL bên ngoài.

HTTP LAN dùng Referrer-Policy strict-origin-when-cross-origin để trình duyệt
giữ đúng Origin khi gửi form đăng nhập. Không dùng no-referrer tại trang login:
chính sách đó có thể biến Origin thành null trên IP LAN và bị CSRF từ chối.
Kiểm tra bằng `node tests/browser_login_qa.cjs`: Chrome giả lập điện thoại với
HTTP hostname không phải localhost, đăng nhập sinh viên/admin và tiếp tục QR.

Sau khi quét, lịch sử tự chọn khóa của phiên vừa điểm danh, bỏ bộ lọc trạng
thái để hiện kết quả. Bảng gồm ngày/buổi/khóa/kết quả/trạng thái phiên, một hàng
mỗi buổi. Admin đang mở chi tiết điểm danh nhận thay đổi trong khoảng 2,5 giây,
không làm mất dữ liệu ở form điều chỉnh. Không thay bố cục giảng viên.

File học liệu và bài tập hỗ trợ xem văn bản/mã nguồn, nội dung chữ DOCX/PPTX,
danh sách ZIP và mở PDF trong tab riêng. Chức năng xem trước không thực thi
code/HTML; nội dung giới hạn 2 MiB và luôn kiểm tra quyền khóa/chủ bài nộp.

Nút chuông mở danh sách thông báo gần nhất có cuộn, tải thêm, làm mới và đánh dấu
tất cả đã đọc. Trang Thông báo dùng bảng TT/Người gửi/Tiêu đề/Mô tả/Thời gian gửi,
tìm kiếm, lọc loại và trạng thái đọc, sắp xếp thời gian và chọn số dòng mỗi trang.
Nhấn tiêu đề mở nội dung chi tiết và ghi nhận đã đọc. Trạng thái lưu theo sinh
viên ở `data/notification_reads.json`, dùng chung cho chuông và sidebar; không
ảnh hưởng trạng thái của tài khoản khác.

## Tạo dữ liệu từ phía giảng viên

Đăng nhập admin, chọn **Khóa học** hoặc mở `/admin/courses`:

Mục Khóa học nằm trong sidebar quản trị gốc, cùng Dashboard, Giám sát, Thông báo,
Cấu hình kỳ thi, Tài khoản sinh viên, Bài nộp, Địa chỉ LAN và Tài khoản Admin.
Không có menu quản lý học tập riêng. Trang danh sách tìm theo tên/mã, lọc học kỳ
và trạng thái; mở một khóa hiển thị ngữ cảnh lớp và các tab Tổng quan, Sinh viên,
Tài liệu, Lịch & Thông báo, Bài tập & Chấm điểm, Điểm danh, Bảng điểm. Chuyển tab
giữ khóa đang chọn, đường dẫn lưu khóa/tab để tải lại và dùng nút Back/Forward.
Đường dẫn `/admin/learning` cũ chuyển tiếp sang Khóa học và giữ khóa/tab.

### Kết hợp LMS với hệ thống submission

- Dashboard hiển thị số khóa học, sinh viên, bài tập chờ chấm và lượt thi đang
  mở; thẻ khóa có sĩ số, lịch học sắp tới và số bài chờ chấm. Số liệu lấy từ dữ
  liệu thật. Tiến độ lịch là số buổi đã đến lịch, không giả định tuần học.
- Giám sát có bộ chọn khóa, liên kết mở khóa và bốn chỉ số ở trên. Bảng cũ bên
  dưới giữ đủ MSSV/họ tên, IP, trạng thái, đề, thời gian, số lần nộp, trình duyệt,
  cảnh báo và điều khiển. Vẫn đồng bộ mỗi 5 giây; đổi khóa lọc đúng thành viên.
- Cấu hình kỳ thi có ngữ cảnh khóa học/tên kỳ thi. Khi lưu, danh sách dự thi lấy
  từ sinh viên hoạt động trong khóa. Sau khi phân phối đề không được đổi ngữ
  cảnh. Khối cấu hình/phát đề/điều khiển chi tiết cũ tiếp tục hoạt động.
- Lượt phân phối và bài thi mới lưu `course_id` và `exam_title`. Bài thi cũ chưa
  có khóa vẫn xem được ở phạm vi Tất cả khóa học; không đoán khóa từ MSSV vì
  một sinh viên có thể thuộc nhiều khóa.
- Bộ lọc khóa áp dụng cả API giám sát, API bài thi nộp file và thao tác ép
  nộp/điều chỉnh giờ. Không điều khiển bài thi của khóa khác từ phạm vi đang chọn.
- Trang Bài nộp có danh sách bài tập theo khóa, số đã nộp/chưa nộp/chờ chấm/đã
  chấm. Chi tiết lấy lần nộp mới nhất cho mỗi sinh viên, giữ toàn bộ lịch sử và
  cho chấm điểm trong hộp thoại. Bảng bài thi nộp file cũ vẫn có ở trang tổng.
- Chưa thay cơ chế một lượt thi nộp file hoạt động tại một thời điểm và chưa
  tích hợp judge cho thi lập trình. Không tạo danh sách đề/code hoặc số liệu giả
  để khớp ảnh giao diện.

1. Tạo khóa học với tên, mã, học kỳ và danh sách MSSV đã có. Để trống danh sách
   trong giao diện mới nghĩa là chưa ghi danh sinh viên; thêm sau ở tab Sinh viên.
2. Chọn khóa rồi đăng tài liệu, buổi học/thông báo, bài tập có hạn nộp/số lần nộp,
   hoặc mở điểm danh có thời hạn. Thời gian trên form là giờ Việt Nam.
3. Cung cấp mã/QR điểm danh. QR được tạo và đọc bằng thư viện ZXing đặt sẵn ở
   `static/vendor/zxing`, không gọi CDN hoặc dịch vụ bên ngoài. Khi dùng điện
   thoại, đăng nhập sinh viên ở địa chỉ LAN của server rồi mở Điểm danh để quét;
   hệ thống tự nhận buổi học và ghi có mặt ngay sau khi đọc mã.
4. Xem bài nộp và lưu điểm/nhận xét. Có thể điều chỉnh điểm danh có lý do trong
   phiên đang mở. Phiên đã đóng/hết hạn không sửa được.
5. Chọn Bảng điểm để đặt trọng số (tổng 100%) và nhập điểm giữa kỳ/cuối kỳ hoặc
   điều chỉnh điểm thành phần. Để trống điểm điều chỉnh để lấy lại kết quả tự tính.
6. Tổng kết khóa học sau khi đủ điểm của các thành phần có trọng số dương. Sau
   khi chốt, server từ chối thay đổi nội dung, điểm hoặc nhận bài trong khóa.

Kỳ thi của lớp vẫn dùng **Cấu hình kỳ thi** hiện có. Không có dữ liệu học tập giả
được ghi vào lớp thật; khi chưa tạo khóa học, các màn hiển thị trạng thái trống.

## Quy tắc điểm

- Chuyên cần: `max(0, 10 - số phiên đã kết thúc mà sinh viên vắng)`. Có mặt và
  đến muộn đều tính tham gia; phiên còn mở chưa trừ điểm.
- Bài tập: trung bình điểm lần nộp gần nhất của các bài đã chấm/đã hết hạn;
  chưa nộp sau hạn tính 0, bài chờ chấm khiến điểm trung bình chưa đủ dữ liệu.
- Giữa kỳ/cuối kỳ: giảng viên nhập điểm thang 10.
- Điểm nhập thủ công thành phần được ưu tiên hơn điểm suy ra từ hoạt động.
- Tổng kết chỉ hiển thị khi các thành phần có trọng số dương đủ điểm.

## Lưu trữ và kiểm soát truy cập

- Dữ liệu mới: `data/learning.json`; file riêng: `learning-files/`.
- JSON ghi thay thế nguyên tử, khóa ghi trong tiến trình cho các thao tác học tập.
  Tiếp tục chạy một tiến trình server như kiến trúc gốc.
- Tài khoản và kỳ thi cũ giữ ở các file hiện có. Mật khẩu vẫn băm scrypt.
- Server kiểm tra quyền thành viên khóa, chủ bài nộp, trạng thái khóa, hạn nộp,
  số lần nộp, loại file và dung lượng (bài tập/học liệu 20 MiB).
- Bài tập có khóa yêu cầu để gửi lại request lỗi mạng không tăng số lần nộp.
- Điểm/bài nộp sinh viên khác, mã điểm danh và vị trí file thật không xuất hiện
  trong snapshot của sinh viên. Request ghi kiểm tra Origin.
- Sửa lỗi telemetry dùng sai khóa phiên: lưu theo SHA-256 token phiên như cơ chế
  đăng nhập. Bài thi bị giảng viên thu cưỡng bức không được nộp tiếp.

## Khác biệt với LAN-LMS

Thi nộp file giữ quy trình Classroom; thi lập trình có Docker judge cho
C/C++/Java/Python, bộ test và lịch sử chấm. Video camera/ảnh QR đều gửi check-in
tự động. Đồng bộ dùng polling thay vì WebSocket. Điểm chấm code hiển thị trong
kỳ thi/lịch sử, chưa tự ghi đè điểm thành phần mà giảng viên đã nhập. Chưa
chuyển nhập CSV điểm, xóa mềm hoặc nhiều file đính kèm đề bài.

## Giao diện admin theo mẫu `aaa`

Thiết kế đối chiếu từ `index.html`, `preview.css`, `preview.js` tại
`D:\HK1_Năm_4\Lập trình mạng\BTL\aaa`. Chỉ dùng bố cục, màu sắc, kích thước và
đường nét biểu tượng của mẫu; không dùng bản ghi giả, hash router hoặc các
callback chỉ hiển thị thông báo thành công của bản xem trước.

- Dashboard, Khóa học, Cấu hình kỳ thi, Tài khoản sinh viên, Bài nộp, Địa chỉ LAN
  và Tài khoản Admin dùng shell/sidebar 244 px, header 73 px và kiểu thẻ/bảng
  theo mẫu. Giám sát và Thông báo giữ nguyên nội dung/header, đồng bộ riêng
  sidebar qua `admin-sidebar.css` và bộ icon dùng chung. Tất cả sidebar có cùng
  chiều rộng, logo, avatar, khoảng cách menu, trạng thái chọn và ghi chú cuối.
- Danh sách khóa có thống kê thật, tìm kiếm, lọc trạng thái, thẻ khóa và thao
  tác tạo/nhập. Tiến độ tính theo số buổi đã đến lịch, không giả lập tuần học.
- Trong khóa dùng sáu tab: Tổng quan, Sinh viên, Học tập, Lịch & điểm danh,
  Kỳ thi, Bảng điểm. Các đường dẫn material/assignment/event/attendance cũ vẫn
  mở được và được đánh dấu dưới tab cha tương ứng.
- Điểm danh hiển thị danh sách buổi gọn. Nhấn một buổi trong danh sách hoặc
  Lịch & điểm danh để mở chi tiết duy nhất của buổi đó: thống kê, QR/mã nếu còn
  mở, danh sách sinh viên có tìm kiếm/phân trang, điều chỉnh có lý do và kết
  thúc phiên. URL giữ `session=ID` để tải lại vẫn đúng buổi. Tạo phiên mới mở
  ngay chi tiết của phiên vừa tạo; nút quay lại trả về danh sách.
- Học tập nhóm tài liệu/bài tập theo trường chủ đề. Nội dung cũ chưa có chủ đề
  được nhóm vào Nội dung học tập. Lịch có chuyển tuần và bổ sung cuối tuần khi
  có hoạt động để không bỏ sót hạn nộp.
- Các thao tác tạo/sửa khóa, thêm/nhập thành viên, điều chỉnh điểm và xuất CSV
  dùng dữ liệu thật. Bỏ sinh viên khỏi lớp không xóa tài khoản hoặc bài nộp.
- Xuất khóa tạo gói JSON gồm thông tin, trọng số, học liệu, bài tập và lịch;
  không chứa tài khoản, điểm, bài nộp hoặc mã điểm danh. Nhập gói tạo khóa mới
  với ID mới, trạng thái đang học và danh sách ghi danh rỗng. Giới hạn tổng học
  liệu 15 MiB/gói. Kiểm tra nội dung trước khi lưu, dọn file mới nếu nhập lỗi.
- Tab Kỳ thi trong khóa học chỉ hiển thị danh sách, loại thi, lịch dự kiến,
  thời lượng và trạng thái; không có nút tạo, sửa hay cấu hình trong tab này.
- Mục Cấu hình kỳ thi trên sidebar là nơi duy nhất tạo và thiết lập kỳ thi.
  Trang đầu là danh sách theo khóa học, có bộ lọc Tất cả / Thi nộp file /
  Thi lập trình. Nhấn Cấu hình để mở trang chi tiết `exam=ID`.
- Thi nộp file giữ các chức năng chi tiết cũ: danh sách dự thi, thời gian,
  số lần nộp, định dạng, mật khẩu, quy tắc phát đề và bắt đầu/kết thúc lượt.
  Có thể lưu nhiều bản cấu hình trong `data/exam_catalog.json`; chỉ một kỳ
  thi nộp file được chọn để vận hành trên server. “Lưu và mở cấu hình phát đề”
  chọn bản nháp; thao tác này bị chặn nếu một lượt khác đã phát đề/đang thi.
  Các thiết lập và trạng thái của kỳ thi trước được giữ trong danh sách.
- Thi lập trình hỗ trợ lưu ngôn ngữ C/C++/Java/Python, bài toán, thang điểm,
  giới hạn thời gian/bộ nhớ, cách so khớp và test case mẫu/ẩn. “Lưu và mở kỳ
  thi” đưa đề vào mục Kỳ thi của sinh viên trong danh sách, khóa cấu hình.
  Sinh viên bấm bắt đầu để tính giờ, nộp file nguồn theo bài toán, nhận kết
  quả chấm tự động qua Docker. Cả test mẫu và ẩn đều tính điểm. Admin xem
  input/output mong đợi/output thực tế và có thể chấm lại bài đã lưu.
  Chi tiết vận hành và giới hạn tại [programming-judge.md](programming-judge.md).
- Lịch thi dự kiến hiển thị theo giờ Việt Nam; chưa tự động phát đề/mở thi.
  Cấu hình và test case chỉ được trả về qua API quản trị.
- Mục Bài nộp là kho chung cho bài tập nộp file, kỳ thi nộp file và code.
  Mỗi lần nộp là một bản gốc riêng; có lọc khóa học, sinh viên, hoạt động,
  loại, trạng thái, ngày nhận, tìm tên/file, phân trang và nhóm theo sinh viên.
  Bấm chi tiết để xem nội dung, tải đúng phiên bản, chuyển giữa các lần nộp,
  xem kết quả và lịch sử chấm. Giám sát chỉ có lối tắt đến kho của sinh viên.
- Chấm thủ công hoặc chấm lại code đều thêm một lần chấm, không thay kết quả
  cũ trong lịch sử. Thi nộp file không xóa file trước dù dữ liệu cấu hình cũ
  còn trường overwrite_previous. File cũ đã bị xóa trước thay đổi được đánh dấu
  thiếu, không giả lập nội dung. Kho chọn lần nộp file mới nhất / điểm code
  cao nhất từng bài để hiển thị; không tự thay điểm thành phần của khóa học.
- Có xuất CSV và ZIP theo bộ lọc. ZIP gồm bản gốc và metadata/lịch sử chấm;
  giới hạn 1.000 bản ghi hoặc 100 MiB payload mỗi gói. Nội dung CSV được xử lý
  để tên sinh viên/file bắt đầu bằng ký hiệu công thức không thành công thức.
- Giới hạn 6 lần nộp thành công mỗi sinh viên trong cửa sổ trượt 60 giây, dùng
  chung cho cả ba luồng. Quota lưu tại data/submission_rate.json để tải lại
  trang, nhiều tab hoặc đăng nhập lại không đặt lại giới hạn. Lần vượt trả
  HTTP 429, retry_after và Retry-After theo số giây phải chờ. Yêu cầu lỗi không
  chiếm quota; retry idempotent của cùng lần nộp bài tập không tạo bản/quota mới.
  Kiểm tra/giữ chỗ được khóa để nộp đồng thời không vượt sáu bản.
- Trong chi tiết thi lập trình, mỗi bài toán có nút Nhập CSV và file mẫu tải
  xuống. CSV UTF-8 (có/không BOM), tối đa 2 MiB, hỗ trợ phân cách bằng phẩy
  hoặc chấm phẩy. Tiêu đề bắt buộc `input,output`; cột `sample` tùy chọn nhận
  `true/false`, `1/0` hoặc để trống (test ẩn). Ô có dấu phân cách hoặc xuống
  dòng đặt trong nháy kép; nháy kép bên trong viết `""`. Không chuyển chuỗi
  `\n` thành xuống dòng: dùng xuống dòng thật trong ô được đặt nháy kép.
  Xem trước tối đa 5 test, chọn nối thêm/thay thế trong đúng bài toán, sau đó
  Lưu thiết lập kỳ thi. File sai định dạng không thay đổi test hiện có;
  tổng số test sau nhập không vượt 100. Không cắt khoảng trắng đầu/cuối ô.

## Kiểm chứng

```powershell
.\.venv-windows\Scripts\python.exe -m unittest discover -s tests -v
node tests/browser_student_qa.cjs
node tests/test_exam_csv.cjs
```

Bộ kiểm thử HTTP dùng thư mục tạm. Bộ trình duyệt chạy Chrome headless qua CDP
và một server riêng với dữ liệu tạm; không dùng cookie hoặc dữ liệu của server
lớp thật. Nó kiểm tra các màn, form nộp/chấm bài, QR offline, điểm trọng số, màn
trống, mobile, đổi mật khẩu và lỗi JavaScript/CSP. Ảnh QA nằm ở
`previews/student-qa/`.

Trên máy này, `start_windows.bat` cũng nhận `.venv-windows` khi `.venv` là môi
trường sao chép từ macOS/Linux.
