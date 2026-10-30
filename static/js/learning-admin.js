(() => {
  'use strict';
  const esc=window.cssEscape, $=id=>document.getElementById(id), content=$('learning-content');
  let data,selected=new URLSearchParams(location.search).get('course')||'',tab=new URLSearchParams(location.search).get('tab')||'overview',busy=false;
  let search='',statusFilter='',semesterFilter='';
  let weekOffset=0;
  let attendanceId=new URLSearchParams(location.search).get('session')||'',attendancePage=1,attendanceQuery='';
  const date=v=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(v));
  const empty=message=>`<div class="student-empty"><i class="fa fa-folder-open-o"></i><p>${esc(message)}</p></div>`;
  const titleField='<label>Tiêu đề<input name="title" required maxlength="200"></label>';
  const description='<label>Mô tả / Yêu cầu<textarea name="description" rows="4" maxlength="10000"></textarea></label>';
  const form=(action,title,fields)=>`<section class="panel"><h2>${title}</h2><form class="stack-form" data-action="${action}"><input type="hidden" name="course_id" value="${esc(selected)}">${['material','assignment'].includes(action)?'<label>Chủ đề<input name="topic" maxlength="200" placeholder="Ví dụ: Chủ đề 02 · Thực hành"></label>':''}${fields}<div><button class="btn btn-primary">Lưu ${title.toLowerCase()}</button></div></form></section>`;
  const scoped=key=>data[key].filter(r=>r.course_id===selected);
  const course=()=>data.courses.find(c=>c.id===selected);
  const members=c=>data.students.filter(s=>c.student_ids===null||c.student_ids.includes(s.student_id));
  function syncUrl(replace=false){const query=new URLSearchParams();if(selected)query.set('course',selected);if(selected&&tab!=='overview')query.set('tab',tab);if(selected&&tab==='attendance'&&attendanceId)query.set('session',attendanceId);history[replace?'replaceState':'pushState'](null,'','/admin/courses'+(query.size?'?'+query.toString():''));}
  function choose(id){selected=id;tab='overview';attendanceId='';syncUrl();render();drawAttendanceQr();}
  function openAttendance(id){attendanceId=id;attendancePage=1;attendanceQuery='';tab='attendance';syncUrl();render();drawAttendanceQr();}
  function openLesson(id){
    const lesson=data.events.find(r=>r.id===id&&r.course_id===selected&&r.kind==='lesson');if(!lesson)return;
    const session=data.attendance.find(r=>r.event_id===id),closed=course().status==='completed';
    const dialog=window.adminDesign.modal('Buổi học & điểm danh',`<h3>${esc(lesson.title)}</h3><p class="muted">${date(lesson.starts_at)} · ${esc(lesson.location||'Chưa đặt địa điểm')}</p><p>${esc(lesson.description||'')}</p>${session?`<p>${session.open?'Điểm danh đang mở':'Phiên điểm danh đã kết thúc'}.</p><button type="button" class="btn btn-primary" data-lesson-attendance="${session.id}">Xem chi tiết điểm danh</button>`:closed?'<p class="muted">Khóa học đã tổng kết.</p>':`<form class="stack-form" data-action="attendance"><input type="hidden" name="course_id" value="${selected}"><input type="hidden" name="event_id" value="${id}"><label>Thời gian mở mã QR<select name="duration_minutes"><option value="5">5 phút</option><option value="10">10 phút</option><option value="15" selected>15 phút</option><option value="30">30 phút</option><option value="60">60 phút</option></select></label><p class="muted">Điểm danh gắn với buổi học này. Sinh viên quét QR để ghi nhận có mặt.</p><button class="btn btn-primary">Mở điểm danh buổi học</button></form>`}`);
    dialog.querySelector('[data-lesson-attendance]')?.addEventListener('click',()=>{dialog.close();openAttendance(session.id);});
  }
  function landing(){return window.courseDesign.landing(data,{search,status:statusFilter});}
  function courseHeader(c){return window.courseDesign.header(data,c,tab);}
  function overviewPanel(c,readonly){return window.courseDesign.overview(data,c);}
  function updateGradeTotal(row){
    const book=data.gradebooks.find(b=>b.course_id===selected),output=row?.querySelector('[data-grade-total]');
    if(!book||!output)return;
    let total=0,complete=true;
    for(const [component,weight] of Object.entries(book.weights)){
      if(weight===0)continue;
      const input=[...row.querySelectorAll('[data-grade-component]')].find(el=>el.dataset.gradeComponent===component);
      const raw=input?.value||input?.dataset.gradeAutomatic||'';
      const score=Number(raw);
      if(!input||input.validity.badInput||!input.checkValidity()||raw===''||!Number.isFinite(score)||score<0||score>10){complete=false;break;}
      total+=score*weight/100;
    }
    // Python's round uses ties-to-even. Exact half-cent ties on a 0–10
    // grade are odd multiples of 1/8; toFixed handles the other values.
    const eighths=total*8,cents=Math.floor(total*100);
    const rounded=Number.isInteger(eighths)&&eighths%2===1?(cents+cents%2)/100:Number(total.toFixed(2));
    output.textContent=complete?String(rounded):'—';
    output.title='Tự tính theo trọng số đã lưu. Bấm Lưu điểm để lưu thay đổi.';
  }
  window.listUi.on('course',()=>{attendancePage=1;render();drawAttendanceQr();});
  function render(){
    if($('admin-course-count'))$('admin-course-count').textContent=data.courses.length;
    document.querySelectorAll('.sidebar-nav a').forEach(a=>{const url=new URL(a.href);if(url.pathname==='/admin'&&['monitor','exam','submissions'].includes(url.searchParams.get('section'))){if(selected)url.searchParams.set('course',selected);else url.searchParams.delete('course');a.href=url.pathname+url.search;}});
    const c=course(),readonly=c?.status==='completed';
    const top=c?courseHeader(c):'';
    if(!c){content.innerHTML=landing();return;}
    if(tab==='learning')tab='materials';
    const tabs=[['overview','Tổng quan','th-large'],['students','Sinh viên','users'],['materials','Tài liệu','book'],['assignments','Bài tập','file-text-o'],['calendar','Lịch & điểm danh','calendar'],['exams','Kỳ thi','shield'],['grades','Bảng điểm','bar-chart']];
    const parentTab=({material:'materials',assignment:'assignments',event:'calendar',attendance:'calendar'})[tab]||tab;
    if(!tabs.some(([key])=>key===parentTab))tab='overview';
    let body='';
    if(tab==='materials'||tab==='assignments')body=window.courseDesign.teaching(data,c,tab);
    if(tab==='calendar')body=window.courseDesign.calendar(data,c,weekOffset);
    if(tab==='exams')body=window.courseDesign.examView(data,c);
    if(tab==='students')body=window.courseDesign.students(data,c);
    if(tab==='grades')body=window.courseDesign.grades(data,c);
    if(tab==='overview')body=overviewPanel(c,readonly);
    if(tab==='material')body=`${!readonly?form('material','Tài liệu',titleField+description+'<label>File tài liệu (tối đa 20 MiB)<input name="file" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.c,.cpp,.java,.py,.png,.jpg,.jpeg" required></label>'):''}<section class="panel"><h2>Tài liệu đã đăng</h2>${window.listUi.controls('course:legacy-materials:'+selected,'materials')}${window.listUi.view('course:legacy-materials:'+selected,scoped('materials'),'materials').map(r=>`<div class="student-row"><div class="student-row-body"><h3>${esc(r.title)}</h3><p class="muted">${esc(r.original_filename)} · ${date(r.created_at)}</p></div><a href="/api/learning/files/materials/${r.id}">Tải về</a></div>`).join('')||empty('Chưa có tài liệu.')}</section>`;
    if(tab==='event')body=`${!readonly?form('event','Lịch & thông báo',titleField+description+'<label>Loại hoạt động<select name="kind"><option value="lesson">Buổi học</option><option value="announcement">Thông báo</option><option value="exam">Lịch thi</option></select></label><label>Thời gian (giờ Việt Nam)<input name="starts_at" type="datetime-local" required></label><label>Địa điểm<input name="location" maxlength="200"></label>'):''}<section class="panel"><h2>Hoạt động đã đăng</h2>${window.listUi.controls('course:legacy-events:'+selected,'events')}${window.listUi.view('course:legacy-events:'+selected,scoped('events'),'events').map(r=>`<div class="student-row"><div class="student-row-body"><h3>${esc(r.title)}</h3><p class="muted">${date(r.starts_at)} · ${esc(r.location)}</p><p class="student-description">${esc(r.description)}</p></div></div>`).join('')||empty('Chưa có hoạt động.')}</section>`;
    if(tab==='assignment')body=`${!readonly?form('assignment','Bài tập',titleField+description+'<label>File đề bài (tùy chọn, tối đa 20 MiB)<input name="file" type="file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.zip,.c,.cpp,.java,.py,.png,.jpg,.jpeg"></label><label>Hạn nộp (giờ Việt Nam)<input name="due_at" type="datetime-local" required></label><label>Số lần nộp tối đa<input name="max_attempts" type="number" min="1" max="20" value="3" required></label>'):''}${window.listUi.controls('course:legacy-assignments:'+selected,'assignments')}${window.listUi.view('course:legacy-assignments:'+selected,scoped('assignments'),'assignments').map(a=>`<section class="panel"><div class="panel-heading"><div><h2>${esc(a.title)}</h2><p class="muted">Hạn ${date(a.due_at)} · Tối đa ${a.max_attempts} lần nộp</p></div></div><p class="student-description">${esc(a.description)}</p><div class="student-admin-list">${data.submissions.filter(r=>r.assignment_id===a.id).map(r=>`<details><summary>${esc(r.student_id)} · Lần ${r.attempt} · ${date(r.created_at)} · ${r.score===null?'Chờ chấm':r.score+'/10'}</summary><div class="student-actions"><a class="btn btn-secondary" href="/api/learning/files/submissions/${r.id}">Tải bài: ${esc(r.original_filename)}</a></div>${!readonly?`<form class="stack-form" data-action="grade"><input name="submission_id" type="hidden" value="${r.id}"><label>Điểm (0–10)<input name="score" type="number" min="0" max="10" step="0.01" value="${r.score??''}" required></label><label>Nhận xét<textarea name="feedback" maxlength="4000">${esc(r.feedback)}</textarea></label><div><button class="btn btn-primary">Lưu điểm & nhận xét</button></div></form>`:`<p>Điểm: ${r.score??'Chưa chấm'} · ${esc(r.feedback)}</p>`}</details>`).join('')||empty('Chưa có bài nộp cho bài tập này.')}</div></section>`).join('')}`;
    if(tab==='attendance')body=window.classroomAttendance.view(data,c,attendanceId,attendancePage,attendanceQuery);
    if(['material','assignment','event','attendance'].includes(tab)&&!(tab==='attendance'&&attendanceId))body=`<div class="ref-actions"><button type="button" class="btn btn-ghost" data-tab="${parentTab}"><i class="fa fa-arrow-left"></i> Quay lại ${parentTab==='materials'?'Tài liệu':parentTab==='assignments'?'Bài tập':'Lịch & điểm danh'}</button></div>`+body;
    content.innerHTML=top+`<nav class="ref-tabs" aria-label="Chức năng khóa học">${tabs.map(([v,t,icon])=>`<button type="button" class="ref-tab ${parentTab===v?'active':''}" data-tab="${v}" ${parentTab===v?'aria-current="page"':''}><i class="fa fa-${icon}"></i>${t}</button>`).join('')}</nav>${readonly?'<div class="alert alert-info">Khóa học đã tổng kết. Nội dung chỉ được xem.</div>':''}<div class="student-stack">${body}</div></div>`;
  }
  function drawAttendanceQr(){
    window.listUi.preserveTable('course:gradebook:'+selected,content.querySelector('.editable-gradebook'));
    window.classroomPreview.decorate(content);
    content.querySelectorAll('[data-qr-session]').forEach(el=>{
      const row=data.attendance.find(r=>r.id===el.dataset.qrSession);
      const url=new URL('/student/attendance',location.origin);url.searchParams.set('session',row.id);url.searchParams.set('code',row.code);
      window.classroomQr.draw(el,url.href);
      const note=document.createElement('p');note.className='muted';note.textContent='Sinh viên quét QR bằng điện thoại hoặc chọn ảnh trong trang Điểm danh. Khi dùng điện thoại trong lớp, hãy mở trang quản trị bằng địa chỉ LAN của server.';el.after(note);
    });
  }
  async function load(){try{data=await window.cssRequest('/api/admin/workspace');window.submissionDeadlines.sync(data.server_time);$('learning-error').classList.add('hidden');render();drawAttendanceQr();const url=new URL(location.href),lesson=url.searchParams.get('lesson');if(lesson){url.searchParams.delete('lesson');history.replaceState(null,'',url.pathname+url.search);openLesson(lesson);}}catch(e){$('learning-error').textContent=e.message;$('learning-error').classList.remove('hidden');}}
  content.addEventListener('click',e=>{
    const lesson=e.target.closest('[data-lesson-open]');if(lesson){openLesson(lesson.dataset.lessonOpen);return;}
    const reset=e.target.closest('[data-grade-reset]');if(reset){const input=reset.parentElement.querySelector('[data-grade-component]');input.value='';input.dataset.gradeReset='true';reset.textContent='Sẽ dùng điểm tự động';updateGradeTotal(input.closest('tr'));return;}
    const session=e.target.closest('[data-attendance-open]');if(session){openAttendance(session.dataset.attendanceOpen);return;}
    if(e.target.closest('[data-attendance-back]')){openAttendance('');return;}
    const attendancePager=e.target.closest('[data-attendance-page]');if(attendancePager){attendancePage=Number(attendancePager.dataset.attendancePage);render();drawAttendanceQr();return;}

    if(e.target.closest('[data-member-add]')){const c=course(),allowed=data.students.filter(s=>!members(c).some(m=>m.student_id===s.student_id));window.adminDesign.modal('Thêm sinh viên vào lớp',allowed.length?`<form class="stack-form" data-action="course-members"><input name="course_id" type="hidden" value="${c.id}"><label>Sinh viên<select name="add_student_id">${allowed.map(s=>`<option value="${esc(s.student_id)}">${esc(s.student_id)} · ${esc(s.full_name)}</option>`).join('')}</select></label><div class="ref-actions"><button class="btn btn-primary">Thêm vào lớp</button></div></form>`:'<p class="muted">Toàn bộ tài khoản sinh viên đã thuộc khóa học này.</p>');return;}
    if(e.target.closest('[data-members-import]')){window.adminDesign.modal('Nhập danh sách vào khóa học',`<form class="stack-form" data-action="course-members"><input name="course_id" type="hidden" value="${selected}"><label>Danh sách MSSV<textarea name="append_ids" required rows="6" placeholder="Mỗi dòng một MSSV, hoặc phân cách bằng dấu phẩy"></textarea></label><p class="muted">Bổ sung các tài khoản đã tồn tại vào lớp. Sinh viên đang có trong lớp được giữ lại.</p><div class="ref-actions"><button class="btn btn-primary">Thêm danh sách</button></div></form>`);return;}
    const remove=e.target.closest('[data-member-remove]');if(remove){if(window.confirm('Bỏ '+remove.dataset.memberRemove+' khỏi lớp? Tài khoản và lịch sử đã lưu vẫn được giữ.')){const f=new FormData();f.set('course_id',selected);f.set('student_ids',members(course()).map(s=>s.student_id).filter(id=>id!==remove.dataset.memberRemove).join(','));window.cssRequest('/api/learning/course-members',{method:'POST',body:f}).then(load).catch(error=>window.cssToast(error.message,'error'));}return;}
    if(e.target.closest('[data-grades-edit]')){const details=$('design-grade-edit');details.open=true;details.scrollIntoView({behavior:'smooth',block:'center'});return;}
    if(e.target.closest('[data-grades-export]')){const book=data.gradebooks.find(b=>b.course_id===selected),quote=v=>{let s=String(v??'');if(/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};const csv='\uFEFF'+[['student_id','full_name','attendance','homework','midterm','final','total'],...book.items.map(r=>[r.student_id,r.full_name,r.attendance,r.homework,r.midterm,r.final,r.total])].map(row=>row.map(quote).join(',')).join('\r\n'),a=document.createElement('a'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));a.href=url;a.download=course().code+'-bang-diem.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;}
    if(e.target.closest('[data-course-import]')){window.adminDesign.modal('Nhập khóa học','<form class="stack-form" data-action="import-course"><label>Gói khóa học<input type="file" name="file" accept=".json,application/json" required></label><p class="muted">Nhập gói đã xuất từ hệ thống này. Nội dung gồm thông tin khóa, học liệu, bài tập và lịch; không nhập tài khoản, bài nộp hoặc điểm cá nhân. Khóa mới chưa có sinh viên.</p><div class="ref-actions"><button type="button" class="btn btn-secondary" data-design-close>Hủy</button><button class="btn btn-primary">Nhập khóa học</button></div></form>');return;}
    if(e.target.closest('[data-course-create]')){window.adminDesign.modal('Tạo khóa học',window.courseDesign.courseForm());return;}
    if(e.target.closest('[data-course-options]')){const c=course();window.adminDesign.modal('Tùy chọn khóa học',`<p class="muted">${esc(c.code)} · ${esc(c.name)}</p><div class="ref-actions">${c.status!=='completed'?'<button type="button" class="btn btn-secondary" data-course-edit><i class="fa fa-pencil"></i> Sửa thông tin</button>':''}<a class="btn btn-secondary" href="/api/learning/export-course?course=${c.id}"><i class="fa fa-download"></i> Xuất khóa học</a></div>`);return;}
    if(e.target.closest('[data-course-edit]')){e.target.closest('dialog')?.close();window.adminDesign.modal('Sửa thông tin khóa học',window.courseDesign.courseForm(course()));return;}
    const week=e.target.closest('[data-week]');if(week){weekOffset=week.dataset.week==='0'?0:weekOffset+Number(week.dataset.week);render();return;}
    const chosen=e.target.closest('[data-course]');if(chosen){choose(chosen.dataset.course);return;}
    if(e.target.closest('[data-course-back]')){choose('');return;}
    const button=e.target.closest('[data-tab]');if(button){tab=button.dataset.tab;attendanceId='';attendancePage=1;attendanceQuery='';syncUrl();render();drawAttendanceQr();}
  });
  content.addEventListener('submit',async e=>{
    e.preventDefault();if(busy)return;const form=e.target,f=new FormData(form);
    if(form.id==='attendance-search-form'){attendanceQuery=String(f.get('query')||'').trim();attendancePage=1;render();drawAttendanceQr();return;}
    if(form.id==='course-search'){search=String(f.get('query')||'');statusFilter=String(f.get('status')||'');semesterFilter=String(f.get('semester')||'');render();return;}
    if(form.id==='select-course'){choose(String(f.get('course')||''));return;}
    const action=form.dataset.action;if(!action)return;
    if(action==='gradebook-save'){
      const changes=[...form.querySelectorAll('[data-grade-component]')].filter(input=>input.value!==input.dataset.gradeOriginal||input.dataset.gradeReset==='true').map(input=>({student_id:input.dataset.gradeStudent,component:input.dataset.gradeComponent,score:input.value}));
      if(!changes.length){window.cssToast('Chưa có điểm thay đổi.','info');return;}
      f.set('items',JSON.stringify(changes));
    }
    if(action==='course-members'&&(f.has('add_student_id')||f.has('append_ids'))){const added=String(f.get('add_student_id')||f.get('append_ids')||'').replaceAll(',',' ').split(/\s+/).filter(Boolean);f.set('student_ids',[...new Set([...members(course()).map(s=>s.student_id),...added])].join(','));}
    if(action==='complete-course'&&!window.confirm('Tổng kết khóa học? Sau khi chốt chỉ có thể xem, không thể đăng nội dung hoặc chấm điểm.'))return;
    if(action==='close-attendance'&&!window.confirm('Kết thúc điểm danh? Phiên đã đóng không thể sửa.'))return;
    for(const name of ['starts_at','due_at','expires_at'])if(f.get(name)){f.set(name,new Date(String(f.get(name))+'+07:00').toISOString());}
    const file=f.get('file');if(file instanceof File&&file.size>20*1048576){window.cssToast('File vượt 20 MiB.','error');return;}
    busy=true;const button=form.querySelector('button[type="submit"],button:not([type])');button.disabled=true;
    try{const result=await window.cssRequest(`/api/learning/${action}`,{method:'POST',body:f});if(action==='course'||action==='import-course'){selected=result.id;tab='overview';attendanceId='';syncUrl();}if(action==='attendance'){attendanceId=result.id;tab='attendance';attendancePage=1;attendanceQuery='';syncUrl();}window.cssToast('Đã lưu dữ liệu khóa học.','success');await load();}catch(error){$('learning-error').textContent=error.message;$('learning-error').classList.remove('hidden');window.adminDesign.formError(form,error.message);window.cssToast(error.message,'error');}finally{busy=false;button.disabled=false;}
  });
  content.addEventListener('change',e=>{if(e.target.id==='design-course-status'){statusFilter=e.target.value;render();}if(e.target.id==='design-switch-course'){selected=e.target.value;attendanceId='';syncUrl();render();drawAttendanceQr();}});
  content.addEventListener('input',e=>{if(e.target.matches('[data-grade-component]')){updateGradeTotal(e.target.closest('tr'));return;}if(e.target.id==='design-member-search'){const q=e.target.value.toLocaleLowerCase('vi');content.querySelectorAll('[data-member-search]').forEach(row=>row.hidden=!row.dataset.memberSearch.includes(q));}if(e.target.id==='design-course-search'){const position=e.target.selectionStart;search=e.target.value;render();const input=$('design-course-search');input.focus();input.setSelectionRange(position,position);}});
  window.addEventListener('popstate',()=>{selected=new URLSearchParams(location.search).get('course')||'';tab=new URLSearchParams(location.search).get('tab')||'overview';attendanceId=new URLSearchParams(location.search).get('session')||'';attendancePage=1;attendanceQuery='';if(data){render();drawAttendanceQr();}});
  let attendancePolling=false;
  setInterval(async()=>{
    if(attendancePolling||busy||document.hidden||tab!=='attendance'||!attendanceId||!data)return;
    attendancePolling=true;
    try{
      const next=await window.cssRequest('/api/admin/workspace'),before=data.attendance.find(r=>r.id===attendanceId),after=next.attendance.find(r=>r.id===attendanceId);
      if(JSON.stringify(before)!==JSON.stringify(after)){
        if(before?.open!==after?.open&&content.contains(document.activeElement))return;
        data=next;
        if(before?.open!==after?.open){if(!content.contains(document.activeElement)){render();drawAttendanceQr();}}
        else {
          const scratch=document.createElement('div');scratch.innerHTML=window.classroomAttendance.view(data,course(),attendanceId,attendancePage,attendanceQuery);
          for(const selector of ['.attendance-detail-table','.attendance-session-detail>.ref-stats','.attendance-pagination']){
            const current=content.querySelector(selector),replacement=scratch.querySelector(selector);if(current&&replacement)current.replaceWith(replacement);
          }
        }
      }
    }catch(_){}finally{attendancePolling=false;}
  },2500);
  load();
})();
