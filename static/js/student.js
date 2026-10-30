/* Course-first student workspace. Files and scores always come from authenticated APIs. */
(() => {
  'use strict';
  const activityColors=window.classroomActivities;
  const $ = id => document.getElementById(id), esc = window.cssEscape;
  const content = $('workspace-content');
  const titles = {dashboard:['Dashboard','Khóa học, bài tập và lịch học của bạn ở cùng một nơi.'],courses:['Khóa học của tôi','Tài liệu, hoạt động và kết quả trong từng khóa học.'],calendar:['Lịch học','Theo dõi buổi học, thông báo và hạn nộp bài.'],attendance:['Điểm danh','Quét QR để tự ghi nhận có mặt và xem lịch sử các buổi học.'],assignments:['Bài tập','Xem yêu cầu, nộp bài và nhận phản hồi từ giảng viên.'],exams:['Kỳ thi','Theo dõi phân phối đề, thời gian làm bài và nộp bài thi.'],history:['Lịch sử nộp bài','Kiểm tra các lần nộp và tải lại bài đã gửi.'],grades:['Kết quả học tập','Điểm và nhận xét của riêng bạn, cập nhật từ giảng viên.'],notifications:['Thông báo','Thông tin mới từ giảng viên và các khóa học của bạn.'],profile:['Tài khoản của tôi','Thông tin sinh viên và bảo mật tài khoản.']};
  let data, pending, loading=false, page=1, selectedDay=dayKey(new Date()), month=selectedDay.slice(0,7), calendarScope='', filters={q:'',status:'',course:'',session:''};
  let examReceived=performance.now(), examSeconds=0, lastSignature='', pollBusy=false, submitting=false;
  const tabId=Math.random().toString(36).slice(2), tabKey='css-exam-tabs';
  function dayKey(value){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));}
  const date = value => value ? new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(value)) : 'Chưa có';
  const size = bytes => bytes>=1048576 ? `${(bytes/1048576).toFixed(1)} MB` : `${Math.ceil(bytes/1024)} KB`;
  const status = (text,color='') => `<span class="student-status ${color}">${esc(text)}</span>`;
  const empty = (title,message,icon='inbox') => `<div class="student-empty"><i class="fa fa-${icon}" aria-hidden="true"></i><h3>${esc(title)}</h3><p>${esc(message)}</p></div>`;
  const link = (view,label,query='',primary=false) => `<a class="btn ${primary?'btn-primary':'btn-secondary'}" href="/student/${view}${query}">${label}</a>`;
  const courseName = id => data.courses.find(c=>c.id===id)?.name || 'Kỳ thi của lớp';
  const course = () => new URLSearchParams(location.search).get('course') || '';
  const view = () => {const v=location.pathname.split('/')[2]; return titles[v]?v:'dashboard';};
  const inScope = rows => rows.filter(r=>!course()||r.course_id===course());
  const courseDone = id => data.courses.find(c=>c.id===id)?.status==='completed';
  const attempts = id => data.submissions.filter(r=>r.assignment_id===id);
  const assignmentState = a => a.grading_applicable===false?'excluded':attempts(a.id).length?'submitted':Date.parse(a.due_at)<Date.now()?'overdue':'not_submitted';
  const assignmentStatus = a => {const s=assignmentState(a);return status(s==='excluded'?'Không tính điểm':s==='submitted'?'Đã nộp':s==='overdue'?'Quá hạn':'Chưa nộp',s==='submitted'?'green':s==='overdue'?'red':'amber');};
  const download = r => `/api/learning/files/submissions/${encodeURIComponent(r.id)}`;
  function pagination(rows, render){
    const total=Math.max(1,Math.ceil(rows.length/10));page=Math.min(page,total);
    return rows.slice((page-1)*10,page*10).map(render).join('')+(rows.length>10?`<div class="student-pagination"><button class="btn btn-secondary" data-page="${page-1}" ${page===1?'disabled':''}>Trước</button><span>Trang ${page} / ${total}</span><button class="btn btn-secondary" data-page="${page+1}" ${page===total?'disabled':''}>Sau</button></div>`:'');
  }
  function table(headers, rows){return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;}
  function toolbar({search=false,states=false}={}){return window.studentWorkspace.toolbar(data,course(),filters,{search,statuses:states?[['not_submitted','Chưa nộp'],['submitted','Đã nộp'],['overdue','Quá hạn']]:null});}
  function filtered(rows){return inScope(rows).filter(r=>(!filters.course||r.course_id===filters.course)&&(!filters.q||[r.title,r.description,r.original_filename].join(' ').toLocaleLowerCase('vi').includes(filters.q.toLocaleLowerCase('vi'))));}
  function courseCard(c){
    const query=`?course=${encodeURIComponent(c.id)}`;
    const theme=['blue','mint','lilac'][Math.max(0,data.courses.findIndex(row=>row.id===c.id))%3];
    const icon={blue:'sitemap',mint:'clone',lilac:'code'}[theme];
    return `<article class="panel student-course student-course-${theme}"><div class="student-course-cover"><span class="student-course-cover-icon"><i class="fa fa-${icon}" aria-hidden="true"></i></span>${status(c.status==='completed'?'Đã tổng kết':'Đang học',c.status==='completed'?'':'green')}</div><div class="student-course-body"><small class="student-course-code">${esc(c.code)}</small><h3>${esc(c.name)}</h3><p class="muted">${esc(c.semester)}</p><div class="student-course-meta"><a href="/student/courses${query}">Vào khóa học <i class="fa fa-arrow-right" aria-hidden="true"></i></a></div></div></article>`;
  }
  function entries(){return [...filtered(data.events).map(e=>({...e,at:e.starts_at,activity:e.kind,type:e.kind==='announcement'?'Thông báo':e.kind==='exam'?'Lịch thi':'Buổi học',view:'calendar'})),...filtered(data.assignments).map(a=>({...a,at:a.due_at,activity:'assignment',type:'Hạn nộp bài',view:'assignments'}))].sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));}
  function eventRow(e){const type=e.view==='assignments'?'assignment':'event';return `<div class="student-row activity-surface" data-activity="${activityColors.kind(e.activity)}"><div class="student-date-tile"><strong>${new Date(e.at).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit'})}</strong><small>TH ${new Date(e.at).toLocaleDateString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',month:'2-digit'})}</small></div><div class="student-row-body"><div class="student-row-title"><button type="button" class="student-list-title" data-learning-detail="${type}" data-item="${e.id}">${esc(e.title)}</button>${activityColors.badge(e.activity,e.type)}</div><p class="muted">${esc(courseName(e.course_id))} · ${date(e.at)}${e.location?' · '+esc(e.location):''}</p></div></div>`;}
  function calendar(){
    const [year,m]=month.split('-').map(Number), days=new Date(year,m,0).getDate(),offset=(new Date(year,m-1,1).getDay()+6)%7;
    const all=window.listUi.view('student:calendar',entries(),'events');
    return `<section class="panel"><div class="student-calendar-header"><h2>Tháng ${m}, ${year}</h2><div><button class="btn btn-ghost" data-month="-1" aria-label="Tháng trước"><i class="fa fa-angle-left"></i></button><button class="btn btn-ghost" data-month="1" aria-label="Tháng sau"><i class="fa fa-angle-right"></i></button></div></div>${window.listUi.controls("student:calendar","events")}<div class="student-calendar-grid">${['T2','T3','T4','T5','T6','T7','CN'].map(d=>`<span>${d}</span>`).join('')}${'<span></span>'.repeat(offset)}${Array.from({length:days},(_,i)=>{const key=`${month}-${String(i+1).padStart(2,'0')}`;return `<button class="student-calendar-day ${key===dayKey(new Date())?'today':''} ${key===selectedDay?'selected':''} ${all.some(e=>dayKey(e.at)===key)?'has-events':''}" data-day="${key}" aria-label="Ngày ${i+1} tháng ${m}" aria-pressed="${key===selectedDay}">${i+1}${activityColors.dots(all.filter(e=>dayKey(e.at)===key).map(e=>e.activity))}</button>`;}).join('')}</div>${activityColors.legend(all.length?all.map(e=>e.activity):['lesson','assignment','exam','announcement'])}<p class="fine-print">Chọn ngày để xem chi tiết hoạt động.</p><hr class="rule"><h3>Hoạt động ngày ${selectedDay.split('-').reverse().join('/')}</h3>${all.filter(e=>dayKey(e.at)===selectedDay).map(eventRow).join('')||empty('Không có lịch trong ngày','Bạn có thể chọn ngày khác để xem hoạt động.','calendar-check-o')}</section>`;
  }
  function dashboard(){
    const due=data.assignments.filter(a=>assignmentState(a)==='not_submitted'&&!courseDone(a.course_id)).sort((a,b)=>Date.parse(a.due_at)-Date.parse(b.due_at));
    const upcoming=entries().filter(e=>Date.parse(e.at)>Date.now()).slice(0,4);
    return `<div class="student-stack"><section class="student-hero"><div><p class="eyebrow">CHÀO MỪNG TRỞ LẠI</p><h2>Xin chào, ${esc(data.student.full_name)}!</h2><p>Một nơi để theo dõi việc học, hoàn thành bài tập và chuẩn bị cho kỳ thi tiếp theo.</p>${link('courses','Khám phá khóa học <i class="fa fa-arrow-right"></i>')}</div><i class="fa fa-graduation-cap student-hero-symbol" aria-hidden="true"></i></section><div class="student-stats">${[['book','blue',data.courses.length,'Khóa học tham gia'],['pencil-square-o','amber',due.length,'Bài tập cần hoàn thành'],['check-square-o','green',new Set(data.submissions.map(s=>s.assignment_id)).size,'Bài tập đã nộp'],['file-text-o','violet',(data.exam.assigned&&data.exam.state==='started'?1:0)+(data.programming?.exams||[]).filter(e=>e.state==='started').length,'Kỳ thi đang mở']].map(([icon,color,n,label])=>`<article class="stat-card"><span class="stat-icon ${color}"><i class="fa fa-${icon}"></i></span><div><p>${label}</p><strong>${n}</strong></div></article>`).join('')}</div>${data.student.must_change_password?`<div class="alert alert-warning">Bạn đang dùng mật khẩu ban đầu. <a href="/student/profile">Đổi mật khẩu tài khoản</a> để bảo vệ thông tin cá nhân.</div>`:''}${data.exam.can_start||data.exam.can_submit||(data.programming?.exams||[]).some(e=>e.can_start||e.can_submit)?`<div class="alert alert-info">Kỳ thi của lớp đang mở. ${link('exams','Vào khu vực thi')}</div>`:''}<div class="student-grid"><div class="student-stack"><section class="panel"><div class="panel-heading"><h2><i class="fa fa-clock-o"></i> Việc cần hoàn thành</h2>${link('assignments','Xem tất cả')}</div>${due.slice(0,4).map(a=>`<div class="student-row activity-surface" data-activity="assignment"><span class="stat-icon amber"><i class="fa fa-pencil-square-o"></i></span><div class="student-row-body"><h3>${esc(a.title)}</h3><p class="muted">${esc(courseName(a.course_id))} · Hạn ${date(a.due_at)}</p></div>${link('assignments','Làm bài',`?course=${a.course_id}&assignment=${a.id}`)}</div>`).join('')||empty('Bạn đã xem hết việc cần làm','Bài tập mới sẽ xuất hiện khi giảng viên đăng trong khóa học.','check-circle-o')}</section><section class="panel"><div class="panel-heading"><h2>Hoạt động sắp tới</h2>${link('calendar','Xem lịch')}</div>${upcoming.map(eventRow).join('')||empty('Chưa có hoạt động sắp tới','Lịch học và hạn nộp bài sẽ được cập nhật tại đây.','calendar')}</section></div>${calendar()}</div><section><div class="panel-heading"><h2>Khóa học của bạn</h2>${link('courses','Tất cả khóa học')}</div><div class="student-course-grid">${data.courses.slice(0,3).map(courseCard).join('')}</div>${!data.courses.length?`<section class="panel">${empty('Chưa có khóa học','Giảng viên cần tạo khóa học và thêm bạn vào lớp. Bạn vẫn có thể tham gia kỳ thi của lớp trong mục Kỳ thi.','book')}</section>`:''}</section></div>`;
  }
  function courses(){
    const c=data.courses.find(c=>c.id===course());
    if(course()&&!c)return `<section class="panel">${empty('Không tìm thấy khóa học','Khóa học không tồn tại hoặc bạn chưa được cấp quyền.','lock')}</section>`;
    if(c){
      const tab=new URLSearchParams(location.search).get('tab')||'materials';
      const views={materials,calendar:calendarView,assignments:assignmentsView,exams:examsView,grades:gradesView};
      return window.studentWorkspace.course(data,c,tab,(views[tab]||materials)());
    }
    const rows=window.listUi.view('student:courses',data.courses.filter(c=>(`${c.name} ${c.code} ${c.semester}`).toLocaleLowerCase('vi').includes(filters.q.toLocaleLowerCase('vi'))&&(!filters.status||c.status===filters.status)),'courses',{search:false,statusFilter:false});
    return `<form id="filter-form" class="student-toolbar"><label>Tìm khóa học<input name="q" value="${esc(filters.q)}" placeholder="Tên khóa học, mã hoặc học kỳ…"></label><label>Trạng thái<select name="status"><option value="">Tất cả trạng thái</option><option value="active" ${filters.status==='active'?'selected':''}>Đang học</option><option value="completed" ${filters.status==='completed'?'selected':''}>Đã tổng kết</option></select></label></form>${window.listUi.controls("student:courses","courses")}<div class="student-course-grid">${pagination(rows,courseCard)}</div>${!rows.length?`<section class="panel">${empty('Chưa có khóa học phù hợp','Khóa học được hiển thị khi giảng viên tạo lớp và thêm tài khoản của bạn.','book')}</section>`:''}`;
  }
  function materials(){return window.studentWorkspace.materials(data,{scope:course(),filters,page});}
  function calendarView(){return `${toolbar()}<div class="student-grid">${calendar()}<section class="panel"><h2>Lịch học & hạn nộp sắp tới</h2>${entries().filter(e=>Date.parse(e.at)>=Date.now()).slice(0,10).map(eventRow).join('')||empty('Chưa có lịch sắp tới','Bạn sẽ thấy các buổi học và hạn nộp bài được công bố.','calendar')}</section></div>`;}
  function submissionRows(rows){return rows.map(r=>`<tr><td>${esc(r.original_filename)}<small>Lần ${r.attempt||1} · ${size(r.size_bytes)}</small></td><td>${date(r.created_at)}</td><td>${r.score===null||r.score===undefined?status('Chờ chấm','amber'):`<strong>${r.score}/10</strong>`}<small>${esc(r.feedback||'')}</small></td><td><a href="${download(r)}">Tải bài nộp</a></td></tr>`);}
  function assignmentCard(a){const records=attempts(a.id),over=Date.parse(a.due_at)<=Date.now(),closed=courseDone(a.course_id),blocked=over||closed||records.length>=a.max_attempts;return `<section class="panel"><div class="panel-heading"><div><h2>${esc(a.title)}</h2><p class="muted">${esc(courseName(a.course_id))}</p></div>${assignmentStatus(a)}</div>${a.grading_applicable===false?'<p class="alert alert-info">Bài tập đã hết hạn trước lúc bạn tham gia khóa học, không tính vào điểm tự động.</p>':''}${a.original_filename?`<div class="student-actions"><button type="button" class="btn btn-secondary" data-preview-url="/api/learning/preview/assignments/${a.id}">Xem đề bài</button><a class="btn btn-ghost" data-has-preview="true" href="/api/learning/files/assignments/${a.id}">Tải đề: ${esc(a.original_filename)}</a></div>`:''}<p class="student-description">${esc(a.description||'Giảng viên chưa bổ sung yêu cầu.')}</p><div class="student-assignment-meta"><span><i class="fa fa-calendar-o"></i> Hạn ${date(a.due_at)}</span><span><i class="fa fa-repeat"></i> Đã nộp ${records.length}/${a.max_attempts} lần</span></div>${blocked?`<div class="alert alert-info">${closed?'Khóa học đã tổng kết.':over?'Đã hết hạn nộp bài.':'Bạn đã sử dụng hết số lần nộp.'} Lịch sử bài nộp vẫn được lưu bên dưới.</div>`:`<div class="student-upload"><form class="stack-form" data-action="assignment-upload" data-deadline-form data-expires-at="${esc(a.due_at)}"><input type="hidden" name="assignment_id" value="${a.id}"><label for="file-${a.id}">File bài làm</label><input id="file-${a.id}" type="file" name="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.c,.cpp,.java,.py,.png,.jpg,.jpeg" required><p class="muted">Tối đa 20 MiB. Tối đa 6 lần nộp/60 giây mỗi sinh viên, tính chung file và code. Bạn có thể nộp tài liệu, ZIP hoặc mã nguồn theo yêu cầu của giảng viên.</p><div><button class="btn btn-primary"><i class="fa fa-cloud-upload"></i> ${records.length?'Nộp lại bài':'Nộp bài tập'}</button></div></form></div>`}<details ${new URLSearchParams(location.search).get('assignment')===a.id?'open':''}><summary>Lịch sử nộp bài (${records.length})</summary>${window.listUi.controls("student:assignment-attempts:"+a.id,"submissions")}${records.length?table(['Bài nộp','Thời gian','Điểm / Nhận xét','Tải về'],submissionRows(window.listUi.view('student:assignment-attempts:'+a.id,records,'submissions'))):empty('Chưa có lần nộp nào','Chọn file bài làm và nhấn Nộp bài tập.','cloud-upload')}</details></section>`;}
  function assignmentsView(){return window.studentWorkspace.assignments(data,{scope:course(),filters,page});}
  function attendanceView(){return window.studentWorkspace.attendance(data,{scope:course(),filters,page});}
  function examsView(){
    const id=new URLSearchParams(location.search).get('exam');
    if(!id)return window.studentWorkspace.exams(data,{scope:course(),filters,page});
    const back=course()?`/student/courses?course=${course()}&tab=exams`:'/student/exams';
    const heading=`<div><a class="btn btn-ghost" href="${back}"><i class="fa fa-arrow-left"></i> Danh sách kỳ thi</a></div>`;
    if(id==='file'&&data.exam.assigned&&(!course()||data.exam.course_id===course()))return heading+fileExamView();
    const exam=data.programming.exams.find(e=>e.id===id&&(!course()||e.course_id===course()));
    return (exam&&new URLSearchParams(location.search).has('problem')?'':heading)+(exam?window.programmingUi.student({...data,programming:{...data.programming,exams:[exam]}},course()):`<section class="panel">${empty('Không tìm thấy kỳ thi','Bạn chưa được cấp quyền hoặc kỳ thi chưa được mở.','lock')}</section>`);
  }
  function fileExamView(){const e=data.exam;let body;let label=e.forced_submit?'Đã thu bài':e.can_submit?'Đang làm bài':e.status==='submitted'?'Đã nộp bài':e.state==='scheduled'?'Chờ đến giờ bắt đầu':e.state==='started'?'Đang mở':e.state==='distributed'?'Chờ bắt đầu':e.state==='ended'?'Đã kết thúc':'Chưa phát đề';
    if(e.started){body=`<div class="student-exam-info"><div><span>Đề được giao</span><strong>${esc(e.exam_file)}</strong></div><div><span>Thời gian còn lại</span><strong class="student-countdown" id="exam-countdown" data-deadline-countdown data-expires-at="${esc(e.ends_at)}">--:--</strong></div><div><span>Lần nộp</span><strong>${e.submission_count} / ${e.max_submissions}</strong></div></div><p class="muted">Bắt đầu: ${date(e.started_at)} · Hạn nộp: ${date(e.ends_at)}</p>${e.remaining_seconds>0&&e.state==='started'&&!e.forced_submit?`<a class="btn btn-secondary" href="/api/student/exam" target="_blank" rel="noopener"><i class="fa fa-external-link"></i> Mở đề thi</a>`:''}${e.can_submit?`<div class="student-upload"><form class="stack-form" data-action="exam-upload" data-deadline-form data-expires-at="${esc(e.ends_at)}"><label for="exam-file">Bài làm của bạn</label><input id="exam-file" name="file" type="file" accept="${esc(e.extensions.join(','))}" required><p class="muted">Cho phép ${esc(e.extensions.join(', '))} · Tối đa 50 MiB · Còn ${e.max_submissions-e.submission_count} lần nộp. Tối đa 6 lần nộp/60 giây, tính chung file và code.</p><div><button class="btn btn-primary"><i class="fa fa-cloud-upload"></i> Nộp bài thi</button></div></form></div>`:`<div class="alert alert-info">${e.forced_submit?'Giảng viên đã thu bài.':e.remaining_seconds<=0?'Đã hết giờ. Hệ thống đã đóng nhận bài.':e.submission_count>=e.max_submissions?'Đã nhận đủ số lần nộp được phép.':'Hiện không thể nộp bài thi.'} Bạn có thể xem biên nhận trong Lịch sử nộp bài.</div>`}`;
    }else if(e.state==='scheduled'){body=`<div class="alert alert-info" data-exam-opens-at="${esc(e.common_starts_at)}"><strong>Chờ đến giờ bắt đầu: ${date(e.common_starts_at)}</strong><p>Kết thúc lúc ${date(e.common_ends_at)}. Đề được giữ kín trước giờ thi.</p>${window.submissionDeadlines.waiting(e.common_starts_at)}</div>`;}else if(e.can_start){body=`<p class="student-description">Đề đã được phân phối cho bạn. Kỳ thi tính giờ chung từ giờ bắt đầu đã đặt, kết thúc lúc ${date(e.common_ends_at)}. Vào muộn chỉ còn thời gian còn lại của lớp; đề mở sau bước xác nhận này.</p><form class="stack-form" data-action="start-exam" data-deadline-form data-expires-at="${esc(e.common_ends_at||'')}">${e.password_enabled?'<label for="exam-password">Mật khẩu kỳ thi</label><input id="exam-password" type="password" name="exam_password" required autocomplete="off">':''}<div><button class="btn btn-primary"><i class="fa fa-play"></i> Bắt đầu làm bài</button></div></form>`;}else body=empty(e.state==='distributed'?'Đã phân phối, chờ giảng viên bắt đầu':e.state==='ended'?'Kỳ thi đã kết thúc':e.state==='started'?'Bạn chưa được giao đề':'Chưa có kỳ thi đang mở',e.state==='started'?'Liên hệ giảng viên để kiểm tra danh sách dự thi.':'Bạn sẽ thấy kỳ thi tại đây khi giảng viên phát đề.','clock-o');
    return `<div class="student-stack"><section class="panel"><div class="panel-heading"><div><h2>Kỳ thi của lớp</h2><p class="muted">Phát đề, làm bài và nộp file theo cấu hình của giảng viên.</p></div>${status(label,e.can_submit?'blue':'')}</div>${body}</section><section class="panel"><div class="panel-heading"><h2>Bài thi đã nộp</h2>${link('history','Xem lịch sử')}</div>${examHistory(data.exam_submissions)}</section></div>`;
  }
  function examHistory(rows){rows=window.listUi.view("student:file-history",rows,"submissions");return window.listUi.controls("student:file-history","submissions")+(rows.length?table(['Bài nộp','Thời gian','Trạng thái','Tải về'],rows.map(r=>`<tr><td>${esc(r.original_filename)}<small>${size(r.size_bytes)} · ${esc(r.filename)}</small></td><td>${date(r.submitted_at)}</td><td>${status('Đã nhận','green')}</td><td>${r.payload_retained===false?'<span class="muted">File gốc cũ không còn lưu</span>':`<a href="/api/student/submissions/${encodeURIComponent(r.filename)}">Tải bài nộp</a>`}</td></tr>`)):empty('Chưa có bài thi đã nộp','Biên nhận sẽ được lưu khi server nhận bài thành công.','history'));}
  function historyView(){const rows=window.listUi.view('student:assignment-history',filtered(data.submissions),'submissions',{search:false});const total=Math.max(1,Math.ceil(rows.length/10));page=Math.min(page,total);return `${toolbar()}<div class="student-stack">${window.programmingUi.history(data,course()||filters.course)}<section class="panel"><h2>Bài tập đã gửi</h2>${window.listUi.controls("student:assignment-history","submissions")}${rows.length?table(['Bài nộp','Thời gian','Điểm / Nhận xét','Tải về'],submissionRows(rows.slice((page-1)*10,page*10))):empty('Chưa có bài tập đã nộp','Các lần nộp hợp lệ được lưu tại đây.','history')}${rows.length>10?`<div class="student-pagination"><button class="btn btn-secondary" data-page="${page-1}" ${page===1?'disabled':''}>Trước</button>Trang ${page}/${total}<button class="btn btn-secondary" data-page="${page+1}" ${page===total?'disabled':''}>Sau</button></div>`:''}</section><section class="panel"><h2>Lịch sử bài thi của lớp</h2>${examHistory(filtered(data.exam_submissions))}</section></div>`;}
  function gradesView(){const rows=window.listUi.view('student:grades',inScope(data.assignments).map(a=>({...a,score:attempts(a.id).at(-1)?.score})),'grades',{defaultSort:'title'});return `<section class="panel" data-student-assignment-grades><div class="panel-heading"><div><h2>Điểm bài tập & nhận xét</h2><p class="muted">Thang điểm 10 · Hiển thị điểm của lần nộp gần nhất. Ô trống là chưa được chấm.</p></div>${status('Điểm cá nhân','blue')}</div>${window.listUi.controls("student:grades","grades")}${rows.length?table(['Bài tập','Khóa học','Lần nộp','Điểm / 10','Nhận xét'],rows.map(a=>{const r=attempts(a.id).at(-1);return `<tr><td>${esc(a.title)}</td><td>${esc(courseName(a.course_id))}</td><td>${r?date(r.created_at):'Chưa nộp'}</td><td>${a.grading_applicable===false?'Không tính điểm':r?.score??'—'}</td><td>${esc(a.grading_applicable===false?'Đã hết hạn trước khi tham gia khóa học':r?.feedback||'Chưa có nhận xét')}</td></tr>`;})):empty('Chưa có kết quả học tập','Điểm và nhận xét sẽ xuất hiện sau khi giảng viên chấm bài.','bar-chart')}<p class="fine-print">Điểm giữa kỳ lấy trung bình các kỳ thi giữa kỳ; cuối kỳ lấy từ kỳ thi cuối kỳ duy nhất. Test không tính điểm khóa học. Điểm giảng viên chỉnh tay được ưu tiên.</p></section>`;}
  function notificationsView(){return window.studentNotifications.renderPage();}
  function profileView(){return `<div class="student-profile-grid"><section class="panel student-profile-card"><div class="student-profile-icon">${esc(data.student.full_name.slice(0,1).toUpperCase())}</div><h2>${esc(data.student.full_name)}</h2>${status('Sinh viên','blue')}<dl><dt>Mã số sinh viên</dt><dd>${esc(data.student.student_id)}</dd><dt>Khóa học tham gia</dt><dd>${data.courses.length} khóa học</dd></dl><p class="muted">Liên hệ giảng viên nếu thông tin họ tên hoặc mã sinh viên cần chỉnh sửa.</p></section><section class="panel"><h2>Đổi mật khẩu</h2><p class="muted">Sau khi cập nhật, bạn cần đăng nhập lại trên các thiết bị.</p><form class="stack-form" data-action="password"><label for="current-password">Mật khẩu hiện tại</label><input id="current-password" type="password" name="current_password" autocomplete="current-password" required maxlength="200"><label for="new-password">Mật khẩu mới</label><input id="new-password" type="password" name="new_password" autocomplete="new-password" required minlength="6" maxlength="200"><label for="confirm-password">Xác nhận mật khẩu mới</label><input id="confirm-password" type="password" name="confirm_password" autocomplete="new-password" required minlength="6" maxlength="200"><p class="fine-print">Sử dụng mật khẩu từ 6 đến 200 ký tự.</p><div><button class="btn btn-primary"><i class="fa fa-lock"></i> Cập nhật mật khẩu</button></div></form></section></div>`;}
  let activeDetail=null,detailDialog=null,filterTimer;
  function closeDetail(){if(detailDialog){detailDialog.close();detailDialog.remove();}detailDialog=null;activeDetail=null;}
  function detailContent(type,row){
    if(type==='assignment')return assignmentCard(row);
    if(type==='material')return `<h3>${esc(row.title)}</h3><p class="muted">${esc(row.original_filename)} · ${date(row.created_at)}</p><p class="student-description">${esc(row.description||'Giảng viên chưa bổ sung nội dung.')}</p><div class="student-actions"><button type="button" class="btn btn-primary" data-preview-url="/api/learning/preview/materials/${row.id}">Xem trực tiếp</button><a class="btn btn-secondary" data-has-preview="true" href="/api/learning/files/materials/${row.id}">Tải về</a></div>`;
    if(type==='event')return `<h3>${esc(row.title)}</h3><p class="muted">${esc(courseName(row.course_id))} · ${date(row.starts_at)} · ${esc(row.location||'Chưa đặt địa điểm')}</p><p class="student-description">${esc(row.description||'Không có mô tả thêm.')}</p>`;
    return `<h3>${esc(row.title)}</h3><p class="muted">${esc(courseName(row.course_id))} · ${date(row.lesson_at)}</p><p>${row.grading_applicable===false?'Không tính điểm · Buổi học trước khi tham gia khóa học':({present:'Có mặt',late:'Đến muộn',absent:'Vắng'})[row.record?.status]||(row.open?'Chưa điểm danh':'Vắng')} · ${row.session_status==='open'?'Phiên đang mở':row.session_status==='closed'?'Phiên đã đóng':'Phiên hết hạn'}</p>${row.record?`<p class="muted">Ghi nhận: ${date(row.record.checked_in_at)}</p><p class="student-description">${esc(row.record.reason||'')}</p>`:''}`;
  }
  function refreshDetail(){
    const key=activeDetail,deep=new URLSearchParams(location.search).get('assignment');
    if(!key){if(deep&&(view()==='assignments'||view()==='courses'&&new URLSearchParams(location.search).get('tab')==='assignments'))openDetail('assignment',deep);return;}
    if(!detailDialog?.isConnected)return;
    if([...detailDialog.querySelectorAll('input[type=file]')].some(n=>n.files.length))return;
    const rows=({assignment:data.assignments,material:data.materials,event:data.events,attendance:data.attendance})[key.type]||[];
    const row=rows.find(r=>r.id===key.id),body=detailDialog.querySelector('[data-student-detail-body]');
    body.innerHTML=row?detailContent(key.type,row):empty('Không còn nội dung để xem','Dữ liệu đã thay đổi hoặc bạn chưa được cấp quyền.','lock');
  }
  function openDetail(type,id){
    if(!data)return;closeDetail();
    const rows=({assignment:data.assignments,material:data.materials,event:data.events,attendance:data.attendance})[type]||[];
    if(!rows.some(r=>r.id===id))return;
    activeDetail={type,id};const dialog=document.createElement('dialog');detailDialog=dialog;
    dialog.className='student-detail-dialog';dialog.setAttribute('aria-label',({assignment:'Chi tiết bài tập',material:'Chi tiết tài liệu',event:'Chi tiết lịch học',attendance:'Chi tiết điểm danh'})[type]);
    dialog.innerHTML=`<div class="student-detail-head"><h2>${esc(dialog.getAttribute('aria-label'))}</h2><button type="button" class="btn btn-secondary" data-close-student-detail aria-label="Đóng chi tiết">Đóng</button></div><div data-student-detail-body></div>`;
    document.body.append(dialog);refreshDetail();dialog.showModal();
    dialog.addEventListener('close',()=>{
      dialog.remove();if(detailDialog!==dialog)return;detailDialog=null;activeDetail=null;
      const url=new URL(location.href);if(url.searchParams.has('assignment')){url.searchParams.delete('assignment');history.replaceState(null,'',url.pathname+url.search);}
    },{once:true});
  }
  function openExam(id){const url=new URL(location.href);url.searchParams.set('exam',id);history.pushState(null,'',url.pathname+url.search);page=1;render();}
  function applyFilters(form){
    if(!form?.isConnected)return;clearTimeout(filterTimer);
    const focus=document.activeElement,focused=form.contains(focus)?focus.name:null,start=focus.selectionStart,end=focus.selectionEnd;
    const f=new FormData(form);filters={q:String(f.get('q')||''),status:String(f.get('status')||''),course:String(f.get('course')||''),session:String(f.get('session')||'')};
    if(view()==='attendance'){const url=new URL(location.href);if(filters.course)url.searchParams.set('course',filters.course);else url.searchParams.delete('course');history.replaceState(null,'',url.pathname+url.search);}
    page=1;render();
    if(focused){const input=document.getElementById('filter-form')?.elements.namedItem(focused);input?.focus();if(typeof start==='number')try{input.setSelectionRange(start,end);}catch(_){}}
  }
  document.addEventListener('input',event=>{if(event.target.closest('#filter-form')&&event.target.matches('input:not([type=file])')){clearTimeout(filterTimer);const form=event.target.form;filterTimer=setTimeout(()=>applyFilters(form),220);}});
  document.addEventListener('attendance-confirmed',event=>{filters={q:'',status:'',course:event.detail.course_id,session:''};page=1;});
  function normalizeCourseRoute(){
    const url=new URL(location.href);if(url.pathname!=='/student/courses'||!url.searchParams.get('course'))return;
    const tab=url.searchParams.get('tab');
    if(tab==='attendance'){url.pathname='/student/attendance';url.searchParams.delete('tab');}
    else if(!['materials','assignments','calendar','exams','grades'].includes(tab))url.searchParams.set('tab','materials');
    history.replaceState(null,'',url.pathname+url.search);
  }
  window.listUi.on('student',()=>{page=1;render();refreshDetail();});
  document.addEventListener('programming-list-change',()=>render());
  function render(){
    if(!data||window.programmingStudent?.busy())return;
    window.studentAttendance.stop();normalizeCourseRoute();
    if(filters.course&&!data.courses.some(c=>c.id===filters.course)){filters.course='';page=1;}
    if(view()==='attendance'&&course()&&!data.courses.some(c=>c.id===course())){
      const url=new URL(location.href);url.searchParams.delete('course');history.replaceState(null,'',url.pathname+url.search);page=1;
    }
    const v=view(), c=data.courses.find(c=>c.id===course());
    document.querySelector('.page-title').classList.toggle('hidden',v==='courses'&&!!c);
    $('page-heading').textContent=v==='courses'&&c?c.name:titles[v][0];$('page-description').textContent=v==='courses'&&c?`${c.code} · ${c.semester}`:titles[v][1];$('header-location').textContent=titles[v][0];
    document.title=`${titles[v][0]} · LAN-LMS`;
    document.querySelectorAll('[data-view]').forEach(a=>{a.classList.toggle('active',a.dataset.view===v);if(a.dataset.view===v)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    $('assignment-badge').textContent=data.assignments.filter(a=>assignmentState(a)==='not_submitted'&&!courseDone(a.course_id)).length;
    window.studentNotifications.setData(data.notification_feed||[]);
    content.innerHTML=({dashboard,courses,calendar:calendarView,attendance:attendanceView,assignments:assignmentsView,exams:examsView,history:historyView,grades:gradesView,notifications:notificationsView,profile:profileView}[v])();
    window.programmingStudent?.mount(data);
    if(content.querySelector('[data-code-workspace]'))document.querySelector('.page-title').classList.add('hidden');
    const assignmentGrades=content.querySelector('[data-student-assignment-grades]');
    if(assignmentGrades){
      const section=document.createElement('section');section.className='panel student-gradebook-panel';
      const books=window.listUi.view('student:gradebooks',data.gradebooks.filter(b=>!course()||b.course_id===course()).map(b=>({...b,title:courseName(b.course_id),score:b.items[0]?.total})),'grades',{defaultSort:'title',directionLabel:'Thứ tự tên khóa học',placeholder:'Tìm tên khóa học…'});
      section.innerHTML=`<h2>Bảng điểm khóa học</h2><p class="muted">Tổng kết theo trọng số của giảng viên. Điểm trống là chưa đủ dữ liệu.</p>${window.listUi.controls('student:gradebooks','grades')}${books.length?table(['Khóa học','Chuyên cần','Bài tập','Giữa kỳ','Cuối kỳ','Tổng kết'],books.map(b=>{const r=b.items[0];return `<tr><td>${esc(courseName(b.course_id))}</td>${['attendance','homework','midterm','final'].map(k=>`<td>${r?.[k]??'—'}<small>${b.weights[k]}%</small></td>`).join('')}<td><strong>${r?.total??'—'}</strong></td></tr>`;})):empty('Chưa có bảng điểm','Bảng điểm sẽ hiển thị khi bạn tham gia khóa học.','bar-chart')}<p class="fine-print">Chuyên cần: 10 điểm, trừ 1 cho mỗi phiên được tính điểm đã kết thúc mà bạn vắng. Bài tập lấy lần nộp gần nhất; chưa nộp sau hạn tính 0. Nội dung trước khi tham gia được loại theo quy tắc ghi danh của bạn. Điểm điều chỉnh của giảng viên được ưu tiên.</p>`;
      // Insert into the grades content, below the course heading and navigation.
      assignmentGrades.before(section);
    }
    window.classroomPreview.decorate(content);
    window.classroomAdminIcons.decorate(content);
    window.studentAttendance.configure(data,load);window.studentAttendance.consumeLink();
    refreshDetail();tick();
  }
  function signature(d){const {server_time,exam,...rest}=d;const {remaining_seconds,...state}=exam;return JSON.stringify({...rest,exam:state});}
  function accept(d){data=d;window.submissionDeadlines.sync(d.server_time);examSeconds=d.exam.remaining_seconds||0;examReceived=performance.now();lastSignature=signature(d);pending=null;$('workspace-update').classList.add('hidden');}
  function error(e){$('workspace-error').textContent=e.message;$('workspace-error').classList.remove('hidden');if(e.status===401)location.assign('/login');}
  async function load(){if(loading)return;loading=true;$('refresh-workspace').disabled=true;try{const d=await window.cssRequest('/api/student/workspace');accept(d);$('workspace-error').classList.add('hidden');$('connection-label').textContent='Đã kết nối';render();}catch(e){error(e);$('connection-label').textContent='Mất kết nối';}finally{loading=false;$('refresh-workspace').disabled=false;}}
  function confirmAction(title,message){return new Promise(resolve=>{const dialog=$('student-confirm');$('confirm-title').textContent=title;$('confirm-message').textContent=message;dialog.returnValue='cancel';dialog.addEventListener('close',()=>resolve(dialog.returnValue==='confirm'),{once:true});dialog.showModal();});}
  function tick(){window.submissionDeadlines.refresh();const el=$('exam-countdown');if(!el||!data)return;const remaining=Math.max(0,Math.ceil(examSeconds-(performance.now()-examReceived)/1000));el.textContent=remaining?`${String(Math.floor(remaining/60)).padStart(2,'0')}:${String(remaining%60).padStart(2,'0')}`:'Hết giờ';el.classList.toggle('urgent',remaining<=300);if(!remaining)content.querySelectorAll('[data-action="exam-upload"] button').forEach(b=>b.disabled=true);}
  document.addEventListener('click',async event=>{
    if(event.target.closest('[data-close-student-detail]')){detailDialog?.close();return;}
    const item=event.target.closest('[data-learning-detail]')||(!event.target.closest('a,button,input,select,textarea,summary')?event.target.closest('[data-learning-row]'):null);
    if(item){const type=item.dataset.learningDetail||item.dataset.learningRow;if(type==='exam')openExam(item.dataset.item);else openDetail(type,item.dataset.item);return;}
    const exam=event.target.closest('[data-student-exam]');if(exam){openExam(exam.dataset.studentExam);return;}
    const anchor=event.target.closest('a[href]');
    if(anchor&&anchor.origin===location.origin&&anchor.pathname.startsWith('/student/')){
      if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||event.button!==0)return;
      event.preventDefault();
      if(window.programmingStudent?.busy())return;
      if([...document.querySelectorAll('#workspace-content input[type=file]:not(:disabled),.student-detail-dialog input[type=file]:not(:disabled)')].some(el=>el.files.length)&&!await confirmAction('Rời trang hiện tại?','File đang chọn chưa được gửi. Bạn sẽ cần chọn lại file khi quay về.'))return;
      closeDetail();history.pushState(null,'',anchor.href);filters={q:'',status:'',course:'',session:''};page=1;render();$('student-app').classList.remove('menu-open');$('student-menu-toggle').setAttribute('aria-expanded','false');window.scrollTo({top:0});
    }
    const p=event.target.closest('[data-page]');if(p){page=Number(p.dataset.page);render();}
    const d=event.target.closest('[data-day]');if(d){selectedDay=d.dataset.day;render();}
    const m=event.target.closest('[data-month]');if(m){const [y,n]=month.split('-').map(Number),next=new Date(y,n-1+Number(m.dataset.month),1);month=`${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,'0')}`;selectedDay=`${month}-01`;render();}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;
    if(form.id==='filter-form'){event.preventDefault();applyFilters(form);return;}
    if(!form.dataset.action)return;
    event.preventDefault();if(submitting)return;
    const action=form.dataset.action,f=new FormData(form),file=f.get('file');
    if(file instanceof File&&file.size>(action==='exam-upload'?50:20)*1048576){window.cssToast('File vượt giới hạn dung lượng.','error');return;}
    if(action==='start-exam'&&!await confirmAction('Bắt đầu kỳ thi?','Thời gian làm bài sẽ được tính ngay trên máy chủ sau khi xác nhận.'))return;
    if(action==='exam-upload'&&!await confirmAction('Xác nhận nộp bài thi',`Gửi file ${file?.name||''}? Lần nộp này sẽ được ghi nhận trong giới hạn của kỳ thi.`))return;
    if(action==='password'&&f.get('new_password')!==f.get('confirm_password')){window.cssToast('Mật khẩu xác nhận không khớp.','error');return;}
    const button=form.querySelector('button[type=submit],button:not([type])');submitting=true;if(button)button.disabled=true;
    try{
      const urls={'start-exam':'/api/student/start','exam-upload':'/api/student/submit','assignment-upload':'/api/learning/submit','check-in':'/api/learning/check-in',password:'/api/student/change-password'};
      if(action==='assignment-upload'||action==='exam-upload'){if(!form.dataset.requestId)form.dataset.requestId=crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`;f.set('request_id',form.dataset.requestId);}
      await window.cssRequest(urls[action],{method:'POST',body:f});
      window.cssToast(action==='password'?'Đã đổi mật khẩu. Vui lòng đăng nhập lại.':action==='check-in'?'Đã xác nhận có mặt.':action==='start-exam'?'Đã bắt đầu kỳ thi.':'Server đã nhận bài nộp.','success');
      if(action==='password'){location.assign('/login');return;}
      form.reset();delete form.dataset.requestId;await load();
    }catch(e){error(e);let inline=form.querySelector('[data-student-form-error]');if(!inline){inline=document.createElement('p');inline.dataset.studentFormError='';inline.setAttribute('role','alert');form.append(inline);}inline.textContent=e.message;window.cssToast(e.message,'error');}finally{submitting=false;if(button)button.disabled=false;}
  });
  document.addEventListener('change',async e=>{
    if(e.target.matches('input[type=file]')&&e.target.form)delete e.target.form.dataset.requestId;
    if(e.target.closest('#filter-form')&&e.target.matches('select')){applyFilters(e.target.form);return;}
    if(e.target.matches('[data-student-course-switch]')){const url=new URL(location.href);url.searchParams.set('course',e.target.value);url.searchParams.delete('assignment');url.searchParams.delete('exam');history.pushState(null,'',url.pathname+url.search);filters={q:'',status:'',course:'',session:''};page=1;render();return;}
    if(e.target.type==='file'&&e.target.form)delete e.target.form.dataset.requestId;

  });
  $('student-menu-toggle').addEventListener('click',()=>{const open=$('student-app').classList.toggle('menu-open');$('student-menu-toggle').setAttribute('aria-expanded',String(open));});
  $('refresh-workspace').addEventListener('click',()=>{if(!submitting)load();});
  $('apply-update').addEventListener('click',()=>{if(submitting)return;load();});
  window.addEventListener('popstate',()=>{closeDetail();page=1;filters={q:'',status:'',course:'',session:''};render();});
  window.studentNotifications.onChange(rows=>{if(data){data.notification_feed=rows;lastSignature=signature(data);}});
  window.addEventListener('beforeunload',e=>{if(submitting||window.programmingStudent?.busy()||[...document.querySelectorAll('#workspace-content input[type=file]:not(:disabled),.student-detail-dialog input[type=file]:not(:disabled)')].some(el=>el.files.length)){e.preventDefault();e.returnValue='';}});
  async function telemetry(){if(!data)return;let tabs={};try{tabs=JSON.parse(localStorage.getItem(tabKey)||'{}');}catch(_){}const now=Date.now();tabs[tabId]=now;Object.keys(tabs).forEach(k=>{if(now-tabs[k]>25000)delete tabs[k];});try{localStorage.setItem(tabKey,JSON.stringify(tabs));}catch(_){}const f=new URLSearchParams({visibility:document.visibilityState,focused:String(document.hasFocus()),tab_count:String(Object.keys(tabs).length),browser:navigator.userAgent});try{await window.cssRequest('/api/student/telemetry',{method:'POST',body:f});}catch(_){} }
  async function poll(){if(pollBusy||loading||submitting||document.hidden)return;pollBusy=true;try{const d=await window.cssRequest('/api/student/workspace');window.studentNotifications.setData(d.notification_feed||[]);data.notification_feed=d.notification_feed;lastSignature=signature(data);$('connection-label').textContent='Đã kết nối';examSeconds=d.exam.remaining_seconds||0;examReceived=performance.now();window.submissionDeadlines.sync(d.server_time);const fileForm=document.querySelector('[data-action=exam-upload]');if(fileForm){window.submissionDeadlines.updateForm(fileForm,d.exam.ends_at,d.exam.can_submit);document.querySelectorAll('#exam-countdown').forEach(n=>n.dataset.expiresAt=d.exam.ends_at||'');}if(signature(d)!==lastSignature){pending=d;if(window.programmingStudent?.sync(d)){accept(d);}else if(!window.studentAttendance.active()&&!document.activeElement?.closest('#filter-form input,.course-select[data-open],.student-detail-dialog input,.student-detail-dialog textarea')&&![...document.querySelectorAll('#workspace-content input[type=file]:not(:disabled),.student-detail-dialog input[type=file]:not(:disabled)')].some(el=>el.files.length)){accept(d);render();}else $('workspace-update').classList.remove('hidden');}tick();await telemetry();}catch(e){$('connection-label').textContent='Mất kết nối';if(e.status===401)error(e);}finally{pollBusy=false;}}
  document.addEventListener('visibilitychange',()=>{telemetry();if(!document.hidden)poll();});window.addEventListener('focus',telemetry);window.addEventListener('blur',telemetry);
  document.addEventListener('exam-window-opened',poll);setInterval(tick,1000);setInterval(poll,10000);load().then(telemetry);
})();
