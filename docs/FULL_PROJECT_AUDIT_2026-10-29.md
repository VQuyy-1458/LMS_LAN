# Rà soát toàn dự án LAN-LMS — 29/10/2026

## Kết luận

Ứng dụng đã có các luồng LMS và thi lập trình khá đầy đủ, và các kiểm thử luồng chính đang chạy đạt. Tuy nhiên, cần xử lý các lỗi về xử lý request, cập nhật tài khoản đồng thời, bảo toàn lịch sử thi và lưu bài trước khi dùng cho kỳ thi lấy điểm chính thức. Thêm tính năng giao diện lúc này không giải quyết được những lỗi này.

Đợt này chỉ rà soát và tạo bằng chứng kiểm tra, **không sửa mã ứng dụng, không đặt lại mật khẩu, không thay đổi dữ liệu kỳ thi đang dùng và không khởi động lại server**. Các tình huống gây lỗi chạy trên dữ liệu tạm. Việc kiểm tra mật khẩu demo trên dữ liệu hiện có chỉ đọc và xuất số lượng tổng hợp; không ghi tên, mật khẩu hay hash tài khoản vào báo cáo.

“Đã tái hiện” bên dưới nghĩa là có kết quả chạy thực tế. “Rủi ro từ mã nguồn” nghĩa là đã thấy cơ chế có vấn đề nhưng chưa đo tải hoặc thử mọi tình huống triển khai. Các đề xuất mở rộng nghiệp vụ được tách riêng.

## Phạm vi và kết quả kiểm tra

Đã xem các nhóm chức năng: đăng nhập và quản lý tài khoản; khóa học và thành viên; học liệu; bài tập và chấm điểm; điểm danh QR; thông báo; kỳ thi nộp file; kỳ thi lập trình; bảng điểm; kho bài nộp và xuất dữ liệu; giao diện sinh viên/giảng viên; lưu trữ, bảo mật, Docker và khởi động; kiểm thử và tài liệu. Phạm vi mã ứng dụng gồm 25 module Python, 24 file JavaScript ứng dụng và 5 template, cùng script và tài liệu liên quan.

| Kiểm tra | Kết quả và giới hạn |
|---|---|
| Bộ unittest Python | 74 test: lượt thường đạt 71, bỏ qua 3 test Docker theo cờ cấu hình. Sau đó chạy riêng toàn bộ 7 test của bộ chấm với Docker: đều đạt, gồm cả 3 test vừa bị bỏ qua. Như vậy cả 74 test đã được chạy đạt qua hai lượt. |
| Trình duyệt với Docker thật | 25 nhóm kiểm tra đạt; có thi lập trình, kết quả chấm, lịch sử/rejudge, thông báo, QR, bài tập, bảng điểm, bố cục mobile và không có lỗi JavaScript/CSP trong các luồng được chạy. |
| JavaScript riêng | Bộ lọc/sắp xếp, CSV đề thi và URL QR đều đạt; 24 file JavaScript ứng dụng qua kiểm tra cú pháp. Các file `._*.js` là metadata AppleDouble, không phải source JavaScript. |
| Tình huống biên bổ sung | Tái hiện các lỗi request, race tài khoản, sửa kỳ thi cũ, lưu bài dở dang, nộp trùng request, phân loại TLE và điều hướng bàn phím. Chi tiết phía dưới. |
| Tải và vận hành dài ngày | Chưa có benchmark theo sĩ số lớp, kiểm thử soak nhiều giờ, mô phỏng mất điện hoặc khôi phục toàn bộ từ backup. Không suy ra sức chứa từ kết quả test chức năng. |

Bằng chứng nằm tại:

- [Kết quả unittest](../logs/full-audit-python-tests.log), [test bộ chấm Docker](../logs/full-audit-judge-tests.log), [test trình duyệt](../logs/full-audit-browser-tests.log).
- [Kết quả tái hiện lỗi](../logs/full-audit-probes.json), [script tái hiện trên fixture tạm](../logs/full_audit_probes.py), [kết quả bàn phím](../logs/full-audit-keyboard.json).

Các probe đang là công cụ rà soát trong `logs/`, chưa phải test hồi quy được tích hợp vào bộ test chính.

## Những lỗi cần sửa trước

### F01 — P0: Request chưa đăng nhập có thể giữ khóa dùng chung và làm nghẽn hệ thống

**Cập nhật sau phê duyệt: đã sửa F01.** Xem [phạm vi và kiểm chứng bản sửa](REQUEST_IO_FIX_2026-10-29.md). Nội dung dưới đây giữ lại bằng chứng của thời điểm rà soát trước sửa; F02 và các mục tiếp theo vẫn chờ phê duyệt riêng.

**Đã tái hiện.** `do_POST()` lấy `learning.LOCK` cho đường dẫn `/api/admin/` trước khi `_do_POST()` đọc xong body và kiểm tra quyền. Đọc body chưa có deadline. Một request gửi body dang dở đã giữ được khóa này dù không có thông tin đăng nhập. Nhiều hoạt động học tập và cập nhật hạn thi cùng cần khóa đó; API GET cũng gọi cập nhật hạn thi trước khi xử lý nội dung.

- Vị trí: `app/main.py:171`, `app/main.py:206`, `app/main.py:383`.
- Bằng chứng: `slow_body.authentication_sent=false`, `global_learning_lock_blocked=true`.
- Nên sửa: giới hạn thời gian đọc và kích thước body; kiểm tra quyền sớm ở các route bảo vệ; chỉ giữ khóa trong đoạn đọc–sửa–ghi dữ liệu thực sự cần thiết. Bổ sung giới hạn kết nối/request đồng thời.
- Tiêu chí đạt: một client tải lên chậm hoặc bỏ dở không ngăn người khác xem bài, nộp bài, đăng nhập hay cập nhật thời gian thi.

### F02 — P1: Content-Length âm vượt qua kiểm tra giới hạn đọc body

**Đã tái hiện.** Parser chỉ kiểm tra `length > MAX_REQUEST_SIZE`, sau đó gọi `read(length)`. Giá trị âm không bị từ chối và dẫn tới đọc đến EOF. Trên fixture có giới hạn 8 byte, parser vẫn đọc 24 byte. Đây là kiểm tra thu nhỏ, không phải thử tải body lớn trên server đang dùng.

- Vị trí: `app/main.py:171`.
- Nên sửa: từ chối độ dài âm, không hợp lệ hoặc header mâu thuẫn; đọc có giới hạn cứng và deadline; xử lý rõ các kiểu truyền body được hỗ trợ. Không để việc giải mã multipart tiếp tục dùng dữ liệu vượt hạn mức.
- Tiêu chí đạt: body không hợp lệ bị trả lỗi thích hợp và đóng kết nối; không thể vượt giới hạn cấu hình bằng header bất thường.

### F03 — P1: Đăng nhập đồng thời có thể khôi phục mật khẩu cũ sau khi admin reset

**Đã tái hiện.** Luồng đăng nhập đọc toàn bộ `students.json`, kiểm tra mật khẩu rồi ghi lại bản đã đọc để cập nhật IP/last_seen. Nếu admin reset mật khẩu giữa hai bước này, bản ghi cũ của luồng đăng nhập có thể ghi đè mật khẩu mới. Luồng tự đổi mật khẩu cũng cần được rà lại theo cùng nguyên tắc cập nhật đồng thời.

- Vị trí: `app/main.py:399–414`, `app/main.py:426–432`, `app/main.py:509`.
- Bằng chứng: reset trả 200; mật khẩu mới hợp lệ ngay sau reset; sau khi cho đăng nhập tiếp tục, mật khẩu mới không còn hợp lệ và mật khẩu cũ được khôi phục.
- Nên sửa: giao dịch thống nhất cho thao tác tài khoản, đọc lại trạng thái hiện hành và chỉ cập nhật các trường cần thiết; dùng phiên bản bản ghi/auth_version khi cần. Reset mật khẩu, khóa tài khoản và thu hồi session phải tuân cùng quy tắc.
- Tiêu chí đạt: chạy đăng nhập/reset/đổi mật khẩu/khóa tài khoản đồng thời không thể làm mất thay đổi mới hơn hoặc phục hồi quyền đã thu hồi.

### F04 — P1: Sửa kỳ thi nộp file đã kết thúc có thể thay đổi điểm lịch sử

**Đã tái hiện.** Guard sửa cấu hình khóa kỳ thi lập trình đã kết thúc, nhưng một kỳ thi file đã kết thúc và không còn active vẫn sửa được. Khi lưu, danh sách thí sinh có thể được tính lại theo thành viên hiện tại. Bảng điểm dùng danh sách này để xác định ai không nộp bài sẽ nhận 0.

- Vị trí: `app/exam_catalog.py:54–84`, `app/course_grades.py:11–28`.
- Bằng chứng: sinh viên không thuộc danh sách thí sinh gốc ban đầu không có điểm kỳ thi; sau khi sửa kỳ thi cũ, sinh viên đó xuất hiện với điểm 0.
- Nên sửa: đóng băng roster, đề, cách tính điểm và mốc thời gian sau khi phát đề/kết thúc cho cả hai loại thi. Thay đổi cần thiết phải có phiên bản hoặc lượt thi mới; chỉnh điểm thủ công cần lịch sử riêng.
- Tiêu chí đạt: thay đổi thành viên lớp hoặc sửa thông tin kỳ thi cũ không làm đổi người được tính điểm và kết quả lịch sử ngoài một thao tác chỉnh điểm được ghi nhận rõ.

### F05 — P1: Báo nộp thất bại dù dữ liệu bài nộp đã được ghi một phần

**Đã tái hiện bằng giả lập lỗi ghi.** Nộp file ghi nội dung, danh sách bài nộp, trạng thái phân công và audit ở các bước riêng. Khi bước ghi trạng thái phân công lỗi, thao tác ném lỗi nhưng danh sách đã chứa bài nộp, còn trạng thái vẫn `in_progress`.

- Vị trí: `app/submissions.py:88–107`; cơ chế lưu ở `app/storage.py:16`, `app/storage.py:77–85`.
- Bằng chứng: `operation_raised_error=true`, `stored_submission_count=1`, `assignment_state=in_progress`.
- `os.replace` bảo vệ một file JSON khỏi ghi dở; `transaction()` hiện là khóa trong tiến trình, không cung cấp rollback nhiều file và không khóa được tiến trình khác. Đây là giới hạn kiến trúc, không chỉ một chỗ thiếu `try/except`.
- Nên sửa: dùng giao dịch cho metadata; lưu file theo bước staging/commit có khả năng đối chiếu và phục hồi. SQLite phù hợp để cân nhắc cho metadata nhờ giao dịch atomic; file bài nộp bên ngoài database vẫn cần cơ chế nhất quán riêng. [Tài liệu SQLite về atomic commit](https://www.sqlite.org/atomiccommit.html).
- Tiêu chí đạt: lỗi đĩa, lỗi ghi hoặc khởi động lại giữa các bước không tạo trạng thái “báo lỗi nhưng đã tính lượt”, không mất file và không tạo bản ghi trỏ tới file không có.

### F06 — P1: Nộp lại cùng request lập trình tạo hai bài nộp

**Đã tái hiện.** Hai lần gọi submit cùng `request_id` đã nhận hai ID khác nhau và lưu hai submission. Chặn nút ở frontend không xử lý được trường hợp mạng mất sau khi server đã nhận bài rồi người dùng thử lại.

- Vị trí: `app/programming.py:129–158`; luồng nộp file cũng cần cùng chính sách. Luồng bài tập đã có cơ chế nhận diện request để tham khảo.
- Bằng chứng: `same_request_id_sent_twice=true`, `different_submission_ids=true`, `stored_submission_count=2`.
- Nên sửa: idempotency key do client giữ cho cùng một lần nộp, ràng buộc theo sinh viên/kỳ thi/bài; retry trả lại kết quả cũ. Hiển thị biên nhận có ID bài nộp và thời điểm server nhận.
- Tiêu chí đạt: double-click, retry sau mất mạng và hai request đồng thời của cùng một lần nộp chỉ tạo một bản ghi, một lượt và một công việc chấm.

### F07 — P1 trước thi thật: Mật khẩu khởi tạo còn dễ dự đoán, đổi mật khẩu chưa được cưỡng chế đầy đủ

**Đã kiểm tra chỉ đọc:** 20/22 tài khoản sinh viên hiện có còn khớp mật khẩu demo đã biết trong mã tạo dữ liệu. Điều này có thể phù hợp cho dữ liệu thi thử hiện tại; không nên mang nguyên sang kỳ thi thật. Báo cáo không công bố mật khẩu hoặc danh tính các tài khoản đó.

- Vị trí: `app/reset_demo.py:81`; import tài khoản ở `app/main.py:451` và tạo tài khoản từ danh sách thi ở `app/main.py:467`.
- Một số nhánh dùng ngày sinh hoặc MSSV làm mật khẩu ban đầu. Cờ `must_change_password` có tồn tại nhưng chưa thành điều kiện bắt buộc chung ở backend trước khi vào thi. Quy định độ dài mật khẩu giữa các thao tác cũng chưa thống nhất.
- Nên sửa: mật khẩu khởi tạo riêng có hạn dùng; cưỡng chế đổi ở backend; thống nhất chính sách và thông báo. Chỉ chuyển các tài khoản demo sang quy trình thật khi có kế hoạch cấp lại thông tin đăng nhập cho sinh viên.

### F08 — P2, ảnh hưởng độ đúng bộ chấm: Chương trình tự thoát mã 124 bị chấm TLE

**Đã tái hiện với Docker thật.** Python `raise SystemExit(124)` chạy khoảng 94 ms với giới hạn 2.000 ms vẫn nhận TLE. Runner đang suy luận timeout từ các mã thoát 124/137/143. Mã thoát của chương trình và nguyên nhân dừng không đủ phân biệt theo cách này.

- Vị trí: `app/code_runner.py:131–136`.
- Nên sửa: runner trả các trường riêng như `exit_code`, `signal`, `timed_out`, `oom_killed`; phân loại từ nguyên nhân thực. GNU `timeout` có thể trả mã của chương trình khi không xảy ra timeout, nên chỉ xét mã số sẽ bị nhập nhằng. [Tài liệu GNU timeout](https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html).
- Tiêu chí đạt: thoát chủ động với các mã đặc biệt là RE thích hợp; chạy quá hạn là TLE; OOM là MLE; kết quả đúng nhất quán giữa bốn ngôn ngữ.

## Rủi ro và cải tiến theo từng phần

### F09 — P1: Cần hoàn thiện chống lạm dụng đăng nhập

**Rủi ro từ mã nguồn.** Hiện có khóa tạm theo tài khoản, nhưng chưa thấy hạn mức kết hợp theo IP/nguồn, giới hạn đủ chặt độ dài tên đăng nhập ở luồng login, hoặc dọn các key tên đăng nhập không tồn tại trong `login_attempts.json`. Ghi toàn bộ map và audit theo từng lần thử khiến tên giả hoặc request dồn dập còn tạo áp lực lưu trữ. Khóa theo tài khoản cũng có thể bị người khác cố ý kích hoạt để cản sinh viên đăng nhập.

- Vị trí: `app/main.py:396–414`, `app/security.py:75–95`.
- Đề xuất: giới hạn input; quota và trì hoãn tăng dần theo cả nguồn lẫn tài khoản; TTL/dọn bản ghi; giới hạn tốc độ và kích thước log. Cân bằng bảo vệ mật khẩu với khả năng sinh viên vào thi. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
- Giao diện nên tách “khóa tài khoản” với “khóa đăng nhập tạm”, hiển thị lý do và thời gian còn lại. Nút gỡ khóa cần giải thích đúng loại khóa; chỉ hiển thị active/inactive hiện chưa diễn tả hết trạng thái đăng nhập.

### F10 — P1: Chưa có bằng chứng hệ thống chịu được tải cả lớp

**Rủi ro từ mã nguồn, chưa phải kết luận benchmark.** `get_session()` ghi lại toàn bộ session khi xác thực; nhiều API gọi refresh deadline; snapshot và gradebook duyệt dữ liệu tổng; frontend có nhiều nhịp polling. Nhiều trang phân trang sau khi đã tải dữ liệu đầy đủ. Càng nhiều lịch sử bài nộp, chi phí mỗi lần refresh càng lớn.

- Vị trí: `app/security.py:46–61`, `app/main.py:206/394`, `app/learning.py:40/128`, `static/js/programming-student.js:159`.
- Đề xuất: giảm tần suất ghi last_seen, gom cập nhật; endpoint trạng thái nhẹ; phân trang và lọc ở server cho lịch sử lớn; tránh tính lại bảng điểm không đổi; index metadata. Static asset có phiên bản nên được cache thay vì áp dụng `no-store` cho mọi phản hồi.
- Kiểm tra cần bổ sung: đồng loạt đăng nhập/mở đề/nộp bài theo sĩ số thực; đo P95, CPU/RAM, hàng đợi, lỗi ghi và thời gian chờ khóa. Thử cả khi Docker đang chấm đầy tải và mạng bị gián đoạn.

### F11 — P1 trước thi thật: Sao lưu và phục hồi cần thành quy trình có kiểm chứng

Đã có các thư mục backup, nhưng chưa có bằng chứng về một lịch sao lưu tự động, bộ dữ liệu backup nhất quán và một lần diễn tập phục hồi toàn bộ. Sao chép từng JSON trong lúc đang ghi có thể lấy các thời điểm khác nhau. Khóa Python hiện tại cũng không bảo vệ dữ liệu khi một script khác cùng chạy.

Đề xuất: manifest gồm schema/version, thời điểm, số bản ghi và hash file; snapshot metadata nhất quán cùng các file được tham chiếu; retention/dung lượng; thử restore sang thư mục khác rồi đối chiếu tài khoản, roster, đề, bài nộp và điểm. Có chặn chạy hai server/script ghi chung một bộ dữ liệu ngoài quy trình cho phép. Nếu chuyển SQLite, cần migration thử, kiểm chứng và đường lui rõ ràng.

### F12 — P1/P2: Khởi động, health check và môi trường Docker cần rõ trạng thái hơn

Docker tại thời điểm kiểm tra đang sẵn sàng và test thực thi đạt. Tuy nhiên `/health` chủ yếu báo tiến trình HTTP còn đáp ứng; `code_runner.status()` kiểm tra daemon/image chưa tương đương một lần biên dịch/chạy thật. Startup, cấu hình Python và Docker còn phụ thuộc thao tác/script môi trường.

- Vị trí: `app/main.py:214`, `app/code_runner.py:28`, các script setup/start.
- Đề xuất một lệnh kiểm tra môi trường: Python/dependencies, static asset, thư mục ghi, dung lượng đĩa, Docker/image và mẫu chấm ngắn. Tách liveness/readiness; hiện worker heartbeat, tuổi job chờ và lỗi gần nhất. Có quản lý tiến trình/restart, log rotation và quy trình dừng an toàn.
- Cấu hình pool 2 worker, queue 50 và hạn mức mỗi sinh viên đã có ích; cần công bố khả năng thực tế sau kiểm thử tải thay vì chỉ tăng số worker.

### F13 — P2: Giới hạn cấu hình đề và ngân sách chấm chưa khớp nhau

Cho phép tới 100 test/bài nhưng worker có ngân sách tổng khoảng 180 giây. Một cấu hình được chấp nhận vẫn có thể vượt ngân sách này; còn có overhead tạo container cho từng test. Đây là rủi ro cấu hình, không phải mọi đề 100 test đều lỗi.

- Vị trí: `app/exam_catalog.py:102–112`, `app/code_runner.py:131–133`, `app/programming.py:17/147`.
- Đề xuất: kiểm tra ngân sách ngay khi tạo đề; có bước chấm thử lời giải chuẩn và các lời giải lỗi; hiển thị cảnh báo cụ thể. Lưu phiên bản/image digest và toolchain cùng lần chấm để rejudge có thể giải thích được. Phân biệt lỗi hạ tầng với bài sai, có retry hữu hạn cho lỗi hạ tầng và giữ kết quả trước khi rejudge như hiện có.
- Cần bộ đề chuẩn kiểm tra AC/WA/CE/RE/TLE/MLE/OLE, EOF, Unicode, số thực nếu có checker phù hợp, test lớn, Java main/class và timeout ở cả bốn ngôn ngữ. Exact/token hiện tại là chính sách chấm được chọn, không tự động là lỗi.

### F14 — P1 khi triển khai rộng: Cần cấu hình phục vụ và bảo mật theo môi trường

Server hiện dựa trên `ThreadingHTTPServer`. Khi dùng chính thức hoặc mở ra ngoài mạng kiểm soát, nên có lớp HTTP phù hợp với timeout, giới hạn kết nối/body, TLS và giám sát; đồng thời hoàn thiện tầng ứng dụng. Tài liệu Python cũng không khuyến nghị `http.server` cho production. [Tài liệu Python](https://docs.python.org/3.14/library/http.server.html).

HTTPS còn giúp bảo vệ thông tin đăng nhập và cho phép camera trực tiếp trên điện thoại. Qua HTTP LAN, ứng dụng đã có fallback chụp/chọn ảnh QR, nên không coi việc camera video bị giới hạn là lỗi riêng của ứng dụng. `getUserMedia()` cần secure context. [Tài liệu MediaDevices](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).

Ứng dụng đã có SameSite cookie và kiểm tra Origin, nên không kết luận “hoàn toàn không có chống CSRF”. Cần kiểm tra cách cấu hình proxy, cookie Secure và nguồn tin cậy trong môi trường thực tế.

### F15 — P1 trước chia sẻ source/backup: Tách dữ liệu vận hành khỏi mã nguồn

`.gitignore` chưa bao phủ nhiều JSON nhạy cảm như tài khoản, session, cấu hình và một số loại backup/log. Tại thời điểm kiểm tra không có thư mục `.git` trong workspace; **không có bằng chứng dữ liệu đã bị push hoặc lộ**. Rủi ro là vô tình đưa chúng vào Git hoặc gói gửi dự án sau này.

Đề xuất ignore mặc định dữ liệu runtime, session, backup, file bài và log; chỉ giữ mẫu không nhạy cảm. Có lệnh đóng gói source với allowlist. Phân quyền thư mục và thời gian lưu cho tài khoản, IP, user-agent, telemetry, bài làm và backup; công bố rõ dữ liệu thu thập cho người sử dụng.

### F16 — P2: Editor đang chặn cả Tab và Shift+Tab

**Đã tái hiện bằng sự kiện bàn phím:** Shift+Tab bị preventDefault và chèn 4 dấu cách. Cả Tab lẫn Shift+Tab hiện đều được dùng để chèn code, làm người dùng bàn phím khó thoát khỏi textarea tới nút nộp hoặc chọn ngôn ngữ.

- Vị trí: `static/js/programming-student.js:129–134`.
- Đề xuất: quy ước thoát editor có thể khám phá được, chẳng hạn Escape rồi Tab; xử lý thụt lề/ngược thụt lề đúng; hướng dẫn phím tắt. Kiểm tra focus khi chuyển trang, mở/đóng modal, cảnh báo lỗi và thông báo kết quả bằng screen reader. [WCAG: No Keyboard Trap](https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html).

### F17 — P2: Hoàn thiện các tình huống làm bài mất mạng và dùng nhiều máy

Hiện đã có draft theo sinh viên/kỳ thi/bài/ngôn ngữ và cơ chế giữ code khi đổi bài. Draft chủ yếu nằm trong localStorage của trình duyệt, chưa đồng bộ sang máy khác; đây là giới hạn cần giải thích cho sinh viên. Cần chính sách hết hạn/xóa draft trên máy dùng chung và thông báo khi không lưu được.

Nên ưu tiên: trạng thái mạng; phân biệt “đã gửi request” với “server đã nhận”; biên nhận nộp; retry an toàn theo F06; khôi phục sau refresh/đăng nhập lại; xử lý hai tab cùng sửa một bài. Có thể thêm đồng bộ draft có version sau khi độ tin cậy nộp bài đã được giải quyết. Thời gian thi và chốt hạn tiếp tục do server quyết định.

### F18 — P2: Chuẩn hóa nghiệp vụ và trạng thái ở từng loại danh sách

Giữ đúng yêu cầu hiện tại của người dùng: **bộ lọc phụ thuộc từng danh sách**, không đưa tất cả loại bộ lọc vào một thanh chung. Với list có số/chữ/thời gian, chỉ cần tăng/giảm theo khóa cố định của list. Kỳ thi và bài tập giữ thứ tự đang mở → sắp diễn ra → đã đóng; không thêm tùy chọn đảo thứ tự vòng đời này.

Nên hoàn thiện theo nghiệp vụ:

- Tài khoản: MSSV/tên/lớp, hoạt động, đăng nhập và khóa tạm; tách các khái niệm này rõ ràng.
- Bài tập/kỳ thi: khóa học, loại đánh giá và trạng thái; hiện mốc mở/đóng rõ ràng và phân biệt ngày dự kiến với đã phát đề.
- Bài nộp: kỳ thi/bài/sinh viên/ngôn ngữ/verdict và khoảng thời gian; có reset bộ lọc, tổng kết quả và trạng thái không có kết quả.
- Thông báo: người nhận thực tế, chưa đọc/đã đọc, thời điểm và nội dung; lưu trạng thái soạn khi mạng lỗi, chống gửi lặp khi retry. Các test gửi/nhận hiện tại đạt; không xác nhận một lỗi gửi thông báo còn tồn tại trong luồng đã chạy.
- Điểm danh: phiên học, khóa, kết quả; hiển thị bằng chứng check-in theo quyền. Focus/tab telemetry chỉ là dấu hiệu cần xem xét, không tự động chứng minh gian lận.

Bài tập hiện có hạn nộp nhưng chưa có quy trình xuất bản theo thời điểm mở đầy đủ như một số trạng thái UI có thể gợi ý. Nếu cần giao bài theo lịch, bổ sung `published/open_at` ở backend và thống nhất với UI. Các thay đổi này là hoàn thiện nghiệp vụ, không phải kết luận mọi danh sách hiện đang sai.

### F19 — P2 nếu có nhiều giảng viên: Bổ sung phạm vi quyền theo khóa học

Quyền admin hiện rộng trên toàn hệ thống, phù hợp mô hình một người quản trị. Nếu nhiều giảng viên cùng dùng, cần vai trò quản trị/giảng viên/sinh viên và quyền sở hữu hoặc phân công theo khóa. API tải bài, bảng điểm, xuất dữ liệu, reset tài khoản và audit đều phải kiểm tra phạm vi; ẩn nút ở frontend là chưa đủ. Chưa cần coi đây là lỗi phân quyền trong mô hình một admin hiện tại.

### F20 — P2: Bổ sung kiểm thử đúng các lỗi biên, chuẩn hóa cách chạy

Các test hiện có bao phủ nhiều luồng chính nhưng vẫn bỏ lọt các lỗi F01–F08. Cần chuyển probe thành regression test sau khi sửa: request chậm/header sai, race tài khoản, sửa kỳ thi lịch sử, lỗi ghi giữa chừng, idempotency và exit code đặc biệt. Bổ sung bài test mất mạng, reboot khi đang chấm và restore backup.

Đề xuất một lệnh test tổng hợp và pipeline riêng cho unit/API, Docker và trình duyệt; công bố rõ test skip. Script browser đang gắn đường dẫn Chrome và `.venv-windows`, nên hỗ trợ biến môi trường/tự phát hiện. Không thấy cấu hình CI trong phạm vi kiểm tra. Khóa phiên bản dependencies/build và lưu phiên bản toolchain để tái lập môi trường; không suy ra có lỗ hổng thư viện chỉ vì chưa có lockfile.

### F21 — P2: Cập nhật tài liệu và kiểm tra gói cài mới

README và một số tài liệu còn mô tả tính năng theo giai đoạn cũ: khóa học, bộ chấm và tích hợp điểm đã đi xa hơn nội dung mô tả. Các đường dẫn môi trường Python và quy trình setup/start cũng cần thống nhất. CSS build đang bị ignore; cần kiểm chứng gói cài mới có asset hoặc có bước build đầy đủ, thay vì chỉ dựa trên workspace hiện tại đã có sẵn file.

Nên có: hướng dẫn cài sạch; khởi động web + Docker; nhập tài khoản; tạo bài tập/thi; thi thử và kiểm tra verdict; cách tính điểm; reset/gỡ khóa; backup/restore; xử lý lỗi thường gặp. Các script xóa/reset demo cần thể hiện rõ phạm vi dữ liệu bị ảnh hưởng và không nằm trong luồng vận hành thường ngày.

### F22 — P3: Giảm độ khó bảo trì và dọn dữ liệu phụ

Nhiều handler và đoạn render JavaScript đang dồn logic/HTML vào dòng dài. Chia theo nghiệp vụ, chuẩn hóa schema request/response và bộ trạng thái sẽ giúp tránh lệch giữa frontend/backend. Dùng các helper bộ lọc dùng chung nhưng giữ cấu hình theo từng loại list, không biến thành một bộ lọc chung cho mọi màn hình.

Có metadata `._*`, tài liệu/reference cũ, preview, log và thư mục công việc chấm tồn dư. Cần quy tắc đóng gói/dọn theo vòng đời và quyền truy cập; không xóa hàng loạt thư mục có thể chứa bài làm. Lệnh kiểm tra source nên loại metadata AppleDouble. Đây là housekeeping; các file `._*.js` không phải lỗi cú pháp của JavaScript đang được ứng dụng tải.

## Những phần nên giữ

- Mật khẩu dùng hash có salt; session lưu token băm, cookie HttpOnly/SameSite; có CSP và kiểm soát đường dẫn/quyền truy cập. Tiếp tục xây trên các cơ chế này.
- Sandbox Docker có user không đặc quyền, hạn chế mạng/tài nguyên, không đưa Docker socket hay toàn bộ bộ test vào chương trình thí sinh. Các test cách ly hiện chạy đạt; kết quả này không thay thế một audit sandbox chuyên biệt.
- Đã có snapshot đề/test/bài, lịch sử chấm lại, trạng thái đang biên dịch/đang chấm và phân biệt lỗi hệ thống. Cần bảo toàn chúng khi cải tổ lưu trữ.
- Luồng sinh viên đã có trang bài riêng, code mẫu theo ngôn ngữ, upload riêng, lịch sử verdict và draft. Ưu tiên độ tin cậy nộp bài trước các tiện ích editor bổ sung.
- Thông báo có phạm vi người nhận; QR có fallback ảnh khi HTTP LAN; bài tập và điểm thi đã tích hợp vào bảng điểm. Những luồng này có kiểm thử thực tế trong đợt rà soát.

## Thứ tự triển khai đề nghị

| Đợt | Nội dung | Điều kiện kết thúc |
|---|---|---|
| 1 — Chặn lỗi ảnh hưởng kỳ thi | F01–F08 và giới hạn login thiết yếu của F09. | Có test hồi quy cho từng lỗi; không đổi mật khẩu/điểm ngoài ý muốn, không nộp trùng và không nghẽn hệ thống vì một request dang dở. |
| 2 — Đảm bảo dữ liệu và vận hành | Giao dịch metadata, staging file, backup/restore, single-instance, health/readiness, khởi động và cấu hình bảo mật đúng môi trường. | Restore đối chiếu đạt; mất tiến trình khi đang nhận/chấm bài có quy trình phục hồi; cài sạch và chấm mẫu được. |
| 3 — Chứng minh sức chịu tải | Tối ưu session/snapshot/polling, phân trang server, kiểm tra ngân sách chấm. | Test theo sĩ số lớp thực; có số liệu độ trễ/hàng đợi; không mất/trùng bài khi nộp đồng loạt hoặc retry. |
| 4 — Hoàn thiện trải nghiệm | Bàn phím editor, thông báo trạng thái, khóa đăng nhập rõ ràng, draft, bộ lọc đúng từng list, nghiệp vụ xuất bản và tài liệu. | Luồng dùng bàn phím, mất mạng, refresh và mobile qua kiểm tra; UI thể hiện đúng trạng thái backend. |
| 5 — Mở rộng có điều kiện | Quyền nhiều giảng viên, ngân hàng đề có phiên bản, checker/điểm theo nhóm test, chạy input tự nhập, đồng bộ draft nhiều máy. | Chọn theo nhu cầu sử dụng sau khi các điều kiện ổn định ở trên đã đạt. |

Đây là rà soát rộng có đọc mã và kiểm tra hành vi, chưa phải chứng nhận an toàn, kiểm thử xâm nhập đầy đủ hay cam kết dung lượng lớp. Các lỗi đã tái hiện đủ cơ sở để ưu tiên sửa ngay; những giới hạn chưa đo được đã ghi rõ để tránh coi giả định là kết quả kiểm chứng.
