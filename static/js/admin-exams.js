/* Exam catalogue and dedicated setup pages. Course pages reuse read-only cards. */
(() => {
  'use strict';
  const activityColors=window.classroomActivities;
  const esc=window.cssEscape,$=id=>document.getElementById(id);
  const params=new URLSearchParams(location.search);
  let data,filter='all',participantDraft=null;
  const languageNames={c:'C',cpp:'C++',java:'Java',python:'Python'};
  const date=v=>v?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(v)):'Chưa đặt lịch';
  const localDate=v=>v?new Date(Date.parse(v)+7*3600000).toISOString().slice(0,16):'';
  const url=(id='',course='')=>'/admin?section=exam'+(course?'&course='+encodeURIComponent(course):'')+(id?'&exam='+encodeURIComponent(id):'');
  const pill=(text,color='')=>`<span class="bridge-pill ${color}">${esc(text)}</span>`;
  const kind=e=>e.type==='programming'?'Thi lập trình'+(e.programming?.languages?.length?' · '+e.programming.languages.map(x=>languageNames[x]).join(' / '):''):'Thi nộp file';
  function state(e){if(e.waiting)return ['Chờ đến giờ bắt đầu','blue'];return ({started:['Đang diễn ra','green'],distributed:['Chờ bắt đầu','blue'],ended:['Đã kết thúc','']})[e.state]||(e.scheduled_at?['Sắp diễn ra','blue']:['Bản nháp','']);}
  function cards(rows,{readonly=false}={}){
    return `<div class="exam-catalog-list">${rows.map(e=>`<article class="panel bridge-exam-card exam-catalog-card activity-surface" data-activity="${activityColors.exam(e)}" data-exam-card="${e.id}" data-exam-type="${e.type}"><span class="stat-icon blue"><i class="fa fa-${e.type==='programming'?'code':'file-text-o'}"></i></span><div class="bridge-exam-card-body"><div class="bridge-inline">${pill(...state(e))}${activityColors.badge(activityColors.exam(e),e.assessment_type==='test'||!e.assessment_type?'Test · Không tính điểm':undefined)}<span class="muted">${esc(kind(e))}</span></div><h2>${esc(e.title)}</h2><p class="muted">${date(e.started_at||e.scheduled_at)} · ${e.duration_minutes} phút · ${e.participants?.length||0} thí sinh${e.ends_at?' · Đóng '+date(e.ends_at):''}</p></div>${readonly?'':`<div class="bridge-inline"><a class="btn btn-secondary" data-exam-config="${e.id}" href="${url(e.id,e.course_id)}">Cấu hình</a>${e.type==='file'&&e.active?`<a class="btn exam-soft" href="/admin?section=monitor${e.course_id?'&course='+encodeURIComponent(e.course_id):''}">Giám sát <i class="fa fa-arrow-right"></i></a>`:''}</div>`}</article>`).join('')||'<section class="panel"><div class="bridge-empty"><i class="fa fa-calendar-o"></i><h3>Chưa có kỳ thi</h3><p>Chưa có kỳ thi thuộc khóa học hoặc loại đang chọn.</p></div></section>'}</div>`;
  }
  function common(e,create=false){
    return `<input type="hidden" name="id" value="${e.id||''}">${create?`<fieldset class="exam-type-options"><legend>Hình thức thi</legend><label><input type="radio" name="type" value="file" checked><span><i class="fa fa-file-text-o"></i><strong>Thi nộp file</strong><small>Phát đề và nhận bài nộp</small></span></label><label><input type="radio" name="type" value="programming"><span><i class="fa fa-code"></i><strong>Thi lập trình</strong><small>Bài toán, test case và cấu hình chấm</small></span></label></fieldset>`:`<input type="hidden" name="type" value="${e.type}">`}<div class="two-cols"><label>Khóa học<select name="course_id"><option value="">Kỳ thi chung</option>${data.courses.filter(c=>c.status!=='completed'||c.id===e.course_id).map(c=>`<option value="${c.id}" ${e.course_id===c.id?'selected':''}>${esc(c.name)} · ${esc(c.code)}</option>`).join('')}</select></label><label>Loại kỳ thi<select name="assessment_type"><option value="test" ${(e.assessment_type||'test')==='test'?'selected':''}>Test · Không tính điểm</option><option value="midterm" ${e.assessment_type==='midterm'?'selected':''}>Giữa kỳ · Lấy trung bình các bài</option><option value="final" ${e.assessment_type==='final'?'selected':''}>Cuối kỳ · Một kỳ thi mỗi khóa học</option></select></label><label>Tên kỳ thi<input name="title" value="${esc(e.title||'')}" required maxlength="200" placeholder="Ví dụ: Kiểm tra giữa kỳ"></label><label>Giờ bắt đầu dự kiến (giờ Việt Nam)<input type="datetime-local" name="scheduled_at" value="${localDate(e.scheduled_at)}"></label>${e.active&&e.type==='file'?'<input type="hidden" name="metadata_only" value="true">':'<label>Thời lượng (phút)<input name="duration_minutes" type="number" min="1" max="1440" value="'+(e.duration_minutes||90)+'" required></label>'}</div><p class="fine-print">Giờ bắt đầu là mốc cho phép vào làm bài. Mở kỳ thi trước lịch sẽ đưa vào trạng thái chờ; thời lượng tính chung từ giờ bắt đầu đã đặt. Nếu không đặt lịch, kỳ thi bắt đầu ngay khi xác nhận mở.</p><label>Hướng dẫn / Mô tả<textarea name="description" rows="3" maxlength="10000">${esc(e.description||'')}</textarea></label>`;
  }
  function fileFields(e){const f=e.file_settings||{};return `<div class="two-cols"><label>Định dạng bài nộp<input name="accepted_submission_extensions" value="${esc((f.accepted_submission_extensions||['.zip']).join(' '))}" required placeholder=".zip .pdf"></label><label>Chính sách nộp<select name="submission_policy"><option value="once" ${f.submission_policy!=='configurable'?'selected':''}>Một lần duy nhất</option><option value="configurable" ${f.submission_policy==='configurable'?'selected':''}>Theo số lần cấu hình</option></select></label><label>Số lần nộp tối đa<input name="max_submissions" type="number" min="1" max="20" value="${f.max_submissions||1}" required></label><label>Lưu trữ bài nộp<input type="hidden" name="overwrite_previous" value="true"><span>Giữ bản gốc của mọi lần nộp; đánh dấu lần mới nhất.</span></label></div>`;}
  function testView(t={}){return `<div class="exam-test" data-program-test><div class="two-cols"><label>Input<textarea data-test-input rows="3" maxlength="100000">\n${esc(t.input||'')}</textarea></label><label>Output mong đợi<textarea data-test-output rows="3" maxlength="100000">\n${esc(t.output||'')}</textarea></label></div><div class="bridge-inline"><label class="checkbox-row"><input data-test-sample type="checkbox" ${t.sample?'checked':''}> Test mẫu hiển thị cho sinh viên</label><button type="button" class="btn btn-ghost" data-test-remove>Xóa test</button></div></div>`;}
  function problemView(p={}){return `<fieldset class="exam-problem" data-program-problem><legend>Bài toán</legend><label>Tên bài toán<input data-problem-title required maxlength="200" value="${esc(p.title||'')}"></label><label>Đề bài / Input / Output<textarea data-problem-statement rows="5" maxlength="20000">${esc(p.statement||'')}</textarea></label><div class="exam-limits"><label>Điểm tối đa<input data-problem-points type="number" min="1" max="1000" required value="${esc(p.points??100)}"></label><label>Thời gian (ms)<input data-problem-time type="number" min="100" max="30000" required value="${esc(p.time_limit_ms??1000)}"></label><label>Bộ nhớ (MB)<input data-problem-memory type="number" min="16" max="2048" required value="${esc(p.memory_limit_mb??256)}"></label><label>So khớp kết quả<select data-problem-checker><option value="tokens" ${p.checker!=='exact'?'selected':''}>Theo token (bỏ khoảng trắng thừa)</option><option value="exact" ${p.checker==='exact'?'selected':''}>Chính xác</option></select></label></div><div class="bridge-section-toolbar"><h3>Test case</h3><button type="button" class="btn btn-secondary" data-test-import><i class="fa fa-upload"></i> Nhập CSV</button></div><div data-test-list>${(p.tests||[]).map(testView).join('')}</div><div class="bridge-inline"><button type="button" class="btn btn-secondary" data-test-add>+ Thêm test case</button><button type="button" class="btn btn-ghost" data-problem-remove>Xóa bài toán</button></div></fieldset>`;}
  function programmingFields(e){return `<section class="exam-programming"><h3>Ngôn ngữ được phép</h3><div class="bridge-inline">${Object.entries(languageNames).map(([v,n])=>`<label class="checkbox-row"><input type="checkbox" name="language" value="${v}" ${(e.programming?.languages||['c','cpp','java']).includes(v)?'checked':''}> ${n}</label>`).join('')}</div><div class="bridge-section-toolbar"><h3>Đề thi lập trình</h3><button type="button" class="btn btn-secondary" data-problem-add>+ Thêm bài toán</button></div><div data-problem-list>${(e.programming?.problems||[]).map(problemView).join('')}</div><p class="fine-print">Bộ chấm đưa input của từng test vào stdin, so sánh stdout với output mong đợi. Test mẫu và test ẩn đều được tính điểm. Lưu và mở kỳ thi ở phần vận hành bên dưới.</p></section>`;}
  function participantIds(){
    return [...new Set([...participantDraft.selected,...participantDraft.pasted.replace(/,/g,'\n').split(/\r?\n/).map(value=>value.trim()).filter(Boolean)])];
  }
  function participantsChanged(){return participantDraft&&JSON.stringify(participantIds().slice().sort())!==JSON.stringify(participantDraft.saved.slice().sort());}
  function participantSummary(clearFeedback=false){
    const root=document.querySelector('[data-code-participants]');if(!root||!participantDraft)return;
    if(clearFeedback)root.querySelector('[data-code-participant-result]')?.classList.add('hidden');
    root.querySelector('[data-code-participant-count]').textContent=participantIds().length+' sinh viên';
    root.querySelector('[data-code-participant-dirty]').textContent=participantsChanged()?'Có thay đổi chưa lưu.':'';
  }
  function participantRows(){
    const root=document.querySelector('[data-code-participants]');if(!root||!participantDraft)return;
    const course=data.courses.find(c=>c.id===participantDraft.course),members=course?.student_ids==null?null:new Set(course.student_ids);
    const students=(data.students||[]).filter(s=>!members||members.has(s.student_id)||participantDraft.selected.has(s.student_id)).map(s=>({...s,selectable:s.active!==false&&(!members||members.has(s.student_id))}));
    const target=root.querySelector('[data-code-participant-list]');
    const rows=window.listUi.enhance('codeparticipants:'+participantDraft.id,target,students,'people',participantRows,{statusFilter:false});
    target.innerHTML=rows.map(s=>{const checked=participantDraft.selected.has(s.student_id);return `<label class="student-option"><input type="checkbox" data-code-participant value="${esc(s.student_id)}" ${checked?'checked':''} ${participantDraft.locked||(!s.selectable&&!checked)?'disabled':''}><span><strong>${esc(s.student_id)}</strong><small>${esc(s.full_name||'Chưa cập nhật')}${!s.selectable?' · '+(s.active===false?'Tài khoản đã khóa':'Không còn thuộc khóa học'):''}</small></span></label>`;}).join('')||'<p class="muted">Không có sinh viên phù hợp.</p>';
    window.classroomAdminIcons?.decorate(root);participantSummary();
  }
  function participantsView(e){
    const course=data.courses.find(c=>c.id===e.course_id),locked=e.state!=='idle'||course?.status==='completed';
    if(!participantDraft||participantDraft.id!==e.id||participantDraft.course!==(e.course_id||'')||locked){participantDraft={id:e.id,course:e.course_id||'',selected:new Set(e.participants||[]),saved:[...(e.participants||[])],pasted:'',locked,saving:false};}
    const disabled=locked?'disabled':'';
    return `<section class="panel code-exam-participants" data-code-participants="${esc(e.id)}"><div class="panel-heading"><div><h2><i class="fa fa-users" aria-hidden="true"></i> Đối tượng được vào thi</h2><p class="muted">Chỉ sinh viên trong danh sách đã lưu mới được vào làm bài và gửi code cho kỳ thi này.</p></div><span class="section-badge" data-code-participant-count></span></div>${locked?'<p class="alert alert-info">Danh sách dự thi đã khóa vì kỳ thi đã mở, kết thúc hoặc khóa học đã tổng kết.</p>':''}<form id="code-participants-form"><fieldset class="code-participants-fields"><div class="two-cols"><div><p class="code-participant-label">Chọn từ danh sách tài khoản</p><div class="participant-list" data-code-participant-list></div><div class="bridge-inline"><button type="button" class="btn btn-ghost" data-code-participants-all ${disabled}>Chọn tất cả kết quả</button><button type="button" class="btn btn-ghost" data-code-participants-clear ${disabled}>Bỏ chọn</button></div></div><label class="code-participant-label">Hoặc dán danh sách MSSV<textarea name="student_ids" rows="8" maxlength="810000" placeholder="Nhập mỗi dòng một MSSV hoặc phân cách bằng dấu phẩy" ${disabled}>${esc(participantDraft.pasted)}</textarea><span class="fine-print">MSSV chưa có tài khoản được tạo tự động với tên “Chưa cập nhật” và mật khẩu ban đầu là MSSV.${course&&course.student_ids!==null?' Với kỳ thi thuộc khóa học, MSSV phải có trong danh sách thành viên khóa học; hãy thêm sinh viên vào khóa học trước.':''}</span></label></div><div class="bridge-inline"><button class="btn btn-primary" type="submit" ${disabled}><i class="fa fa-save" aria-hidden="true"></i> Lưu danh sách dự thi</button><span class="fine-print" data-code-participant-dirty></span></div></fieldset><p class="notice hidden" data-code-participant-result role="status"></p></form></section>`;
  }
  async function saveParticipants(form){
    if(!participantDraft||participantDraft.saving)return;
    const result=form.querySelector('[data-code-participant-result]'),fields=form.querySelector('fieldset');
    result.classList.add('hidden');
    try{
      participantDraft.saving=true;fields.disabled=true;
      const response=await window.cssRequest('/api/admin/programming/participants',{method:'POST',body:new URLSearchParams({exam_id:participantDraft.id,course_id:participantDraft.course,student_ids:participantIds().join('\n')})});
      participantDraft.selected=new Set(response.student_ids);participantDraft.saved=[...response.student_ids];participantDraft.pasted='';form.elements.student_ids.value='';
      const e=data.exams.find(row=>row.id===participantDraft.id);e.participants=[...response.student_ids];e.participants_configured=true;
      for(const sid of response.created)if(!data.students.some(s=>s.student_id===sid))data.students.push({student_id:sid,full_name:'Chưa cập nhật',active:true});
      participantRows();result.textContent=`Đã lưu ${response.count} sinh viên dự thi. Tạo mới ${response.created.length} tài khoản.`;result.className='notice success';result.setAttribute('role','status');
    }catch(error){result.textContent=error.message;result.className='alert alert-error';result.setAttribute('role','alert');}
    finally{participantDraft.saving=false;fields.disabled=false;}
  }
  window.listUi.on('exams',()=>render(data));
  function render(next){
    data=next;const node=$('admin-exam-overview');if(!node)return;
    const scope=params.get('course')||'',id=params.get('exam');
    if(!id){
      const rows=window.listUi.view('exams:catalog:'+scope,data.exams.filter(e=>(!scope||e.course_id===scope)&&(filter==='all'||e.type===filter)),'exams');
      node.innerHTML=`<div class="bridge-section-toolbar exam-catalog-toolbar"><div class="exam-filter-tabs" role="group" aria-label="Lọc hình thức thi">${[['all','Tất cả'],['file','Thi nộp file'],['programming','Thi lập trình']].map(([v,label])=>`<button type="button" data-exam-filter="${v}" aria-pressed="${filter===v}" class="${filter===v?'active':''}">${label}</button>`).join('')}</div><button type="button" class="btn btn-primary" data-exam-create><i class="fa fa-plus"></i> Tạo kỳ thi</button></div>${window.listUi.controls('exams:catalog:'+scope,'exams')}${cards(rows)}<div class="alert alert-info exam-catalog-note"><i class="fa fa-info-circle"></i> Mỗi kỳ thi thuộc một khóa học. Chọn “Cấu hình” để thiết lập chi tiết cho thi nộp file hoặc thi lập trình.</div>`;
      return;
    }
    const e=data.exams.find(e=>e.id===id);
    const back=`<a class="btn btn-ghost exam-back" href="${url('',scope)}"><i class="fa fa-arrow-left"></i> Danh sách kỳ thi</a>`;
    if(!e){node.innerHTML=back+'<section class="panel">Không tìm thấy kỳ thi.</section>';return;}
    const locked=e.active&&['distributed','started'].includes(e.state)||e.type==='programming'&&['started','ended'].includes(e.state),completed=data.courses.find(c=>c.id===e.course_id)?.status==='completed';
    node.innerHTML=`${back}<section class="panel exam-setup"><div class="panel-heading"><div><p class="eyebrow">${esc(kind(e))}</p><h2>${esc(e.title)}</h2></div>${pill(...state(e))}</div>${locked?'<div class="alert alert-info">Đề và cấu hình chấm được khóa để bảo toàn bài thi. Khi đang chờ hoặc đang thi, dùng phần Điều chỉnh thời gian thi bên dưới.</div>':''}<form class="stack-form" id="exam-config-form"><fieldset class="exam-form-fields" ${locked||completed?'disabled':''}>${common(e)}${e.type==='file'?(e.active?'':fileFields(e)):programmingFields(e)}<div class="bridge-inline"><button class="btn btn-primary">Lưu thiết lập kỳ thi</button>${e.type==='file'&&!e.active?'<button type="button" class="btn btn-secondary" data-exam-activate>Lưu và mở cấu hình phát đề</button>':''}</div></fieldset></form>${e.type==='file'&&e.active?'<p class="fine-print">Kỳ thi đang được chọn để phát đề. Danh sách dự thi, mật khẩu, phân phối đề và điều khiển lượt thi ở bên dưới.</p>':''}${completed?'<p class="muted">Khóa học đã tổng kết. Chỉ xem lại cấu hình kỳ thi.</p>':''}</section>`;
    node.insertAdjacentHTML('beforeend',window.examTiming?.view(e)||'');
    if(e.type==='programming'){node.insertAdjacentHTML('beforeend',participantsView(e)+window.programmingUi.admin(e));participantRows();}
  }
  function importTests(problem){
    const dialog=window.adminDesign.modal('Nhập test case từ CSV',`<form class="stack-form" id="exam-csv-import-form"><p class="muted">CSV UTF-8, tối đa 2 MiB. Cột bắt buộc: <code>input,output</code>; cột tùy chọn: <code>sample</code> (true/false hoặc 1/0, mặc định false).</p><a class="btn btn-secondary" href="/static/samples/test-cases.csv" download="test-cases.csv"><i class="fa fa-download"></i> Tải CSV mẫu</a><p class="fine-print">Ô có dấu phẩy, dấu nháy hoặc nhiều dòng phải đặt trong dấu nháy kép; dấu nháy kép bên trong viết thành hai dấu nháy kép. Hỗ trợ dấu phân cách phẩy hoặc chấm phẩy.</p><label>File test case<input type="file" name="csvFile" accept=".csv,text/csv" required></label><label>Cách nhập<select name="mode"><option value="append">Nối thêm vào test case hiện có</option><option value="replace">Thay thế toàn bộ test case của bài toán này</option></select></label><p data-csv-status role="status" aria-live="polite"></p><p class="ref-form-error" data-csv-error role="alert" hidden></p><div class="exam-csv-preview" data-csv-preview></div><p class="fine-print">Tối đa 100 test case mỗi bài toán. Sau khi nhập, bấm “Lưu thiết lập kỳ thi” để lưu vào hệ thống.</p><div class="bridge-inline"><button type="button" class="btn btn-secondary" data-design-close>Hủy</button><button class="btn btn-primary" data-csv-apply disabled>Nhập test case</button></div></form>`);
    const form=dialog.querySelector('form'),button=form.querySelector('[data-csv-apply]'),status=form.querySelector('[data-csv-status]'),error=form.querySelector('[data-csv-error]'),preview=form.querySelector('[data-csv-preview]');
    let tests=null,fileError='',busy=false,revision=0;
    function refresh(){
      const count=problem.querySelectorAll('[data-program-test]').length,total=(form.elements.mode.value==='append'?count:0)+(tests?.length||0);
      const message=fileError||(tests&&total>100?`Sau khi nhập sẽ có ${total} test case, vượt giới hạn 100. Chọn thay thế hoặc giảm số dòng trong file.`:'');
      error.textContent=message;error.hidden=!message;
      status.textContent=busy?'Đang đọc file CSV…':tests?`Đọc được ${tests.length} test case · Hiện có ${count} · Sau khi nhập: ${total}`:'';
      button.disabled=busy||!tests||!!message;
      button.textContent=tests?`Nhập ${tests.length} test case`:'Nhập test case';
      preview.innerHTML=tests?`<p class="fine-print">Xem trước ${Math.min(tests.length,5)}/${tests.length} test case</p><div class="table-scroll"><table><thead><tr><th>Input</th><th>Output</th><th>Loại</th></tr></thead><tbody>${tests.slice(0,5).map(t=>`<tr><td><pre>\n${esc(t.input)}</pre></td><td><pre>\n${esc(t.output)}</pre></td><td>${t.sample?'Test mẫu':'Test ẩn'}</td></tr>`).join('')}</tbody></table></div>`:'';
    }
    form.elements.mode.addEventListener('change',refresh);
    form.elements.csvFile.addEventListener('change',async()=>{
      const ticket=++revision,file=form.elements.csvFile.files[0];tests=null;fileError='';busy=!!file;refresh();
      if(!file)return;
      try{
        if(!/\.csv$/i.test(file.name))throw new Error('Chỉ chấp nhận file .csv.');
        if(file.size>2*1024*1024)throw new Error('File CSV vượt giới hạn 2 MiB.');
        const bytes=await file.arrayBuffer();
        let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch(_){throw new Error('File cần mã hóa UTF-8. Hãy lưu lại dưới dạng CSV UTF-8.');}
        const parsed=window.classroomTestCsv.parse(text);
        if(ticket!==revision||!dialog.isConnected)return;
        tests=parsed;
      }catch(e){if(ticket!==revision||!dialog.isConnected)return;fileError=e.message;}
      if(ticket===revision){busy=false;refresh();}
    });
    form.addEventListener('submit',event=>{
      event.preventDefault();refresh();if(button.disabled)return;
      if(!problem.isConnected||problem.closest('fieldset:disabled')){fileError='Bài toán không còn cho phép chỉnh sửa.';refresh();return;}
      const list=problem.querySelector('[data-test-list]'),html=tests.map(testView).join('');
      if(form.elements.mode.value==='replace')list.innerHTML=html;else list.insertAdjacentHTML('beforeend',html);
      dialog.close();window.cssToast(`Đã nhập ${tests.length} test case. Bấm Lưu thiết lập kỳ thi để lưu.`,'success');
    });
  }
  function payload(form,{starting=false}={}){
    const body=new FormData(form);
    if(body.get('scheduled_at'))body.set('scheduled_at',new Date(body.get('scheduled_at')+'+07:00').toISOString());
    if(body.get('type')==='programming'){
      if(participantDraft?.id===body.get('id')){
        if(participantDraft.saving)throw new Error('Danh sách dự thi đang được lưu. Vui lòng chờ hoàn tất.');
        const sameCourse=(body.get('course_id')||'')===participantDraft.course;
        if(!sameCourse&&starting)throw new Error('Hãy lưu thiết lập kỳ thi để cập nhật danh sách của khóa học mới trước khi mở thi.');
        if(!sameCourse&&participantsChanged())throw new Error('Hãy lưu danh sách dự thi của khóa hiện tại trước khi đổi khóa học, hoặc tải lại trang để bỏ các thay đổi.');
        if(sameCourse)body.set('participant_ids',participantIds().join('\n'));
      }
      body.set('languages',[...form.querySelectorAll('[name=language]:checked')].map(n=>n.value).join(',')||'');
      body.set('problems',JSON.stringify([...form.querySelectorAll('[data-program-problem]')].map(p=>({title:p.querySelector('[data-problem-title]').value,statement:p.querySelector('[data-problem-statement]').value,points:p.querySelector('[data-problem-points]').value,time_limit_ms:p.querySelector('[data-problem-time]').value,memory_limit_mb:p.querySelector('[data-problem-memory]').value,checker:p.querySelector('[data-problem-checker]').value,tests:[...p.querySelectorAll('[data-program-test]')].map(t=>({input:t.querySelector('[data-test-input]').value,output:t.querySelector('[data-test-output]').value,sample:t.querySelector('[data-test-sample]').checked}))}))));
    }
    return body;
  }
  async function save(form,activate=false){
    if(!form.reportValidity())return;
    const buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    try{const result=await window.cssRequest('/api/admin/exam-configurations/save',{method:'POST',body:payload(form)});window.examConfig.ackSaved(form);if(activate)await window.cssRequest('/api/admin/exam-configurations/activate',{method:'POST',body:new URLSearchParams({id:result.id})});location.assign(url(result.id,form.elements.course_id.value));}
    catch(error){window.adminDesign.formError(form,error.message);buttons.forEach(b=>b.disabled=false);}
  }
  if(document.querySelector('[data-admin-section="exam"]')){
    document.addEventListener('click',event=>{
      const target=event.target;
      if(target.closest('[data-code-participants-all]')){document.querySelectorAll('[data-code-participant-list] input:not(:disabled)').forEach(input=>participantDraft.selected.add(input.value));participantRows();participantSummary(true);return;}
      if(target.closest('[data-code-participants-clear]')){participantDraft.selected.clear();participantRows();participantSummary(true);return;}
      const f=target.closest('[data-exam-filter]');if(f){filter=f.dataset.examFilter;render(data);return;}
      if(target.closest('[data-exam-create]')){
        const dialog=window.adminDesign.modal('Tạo kỳ thi',`<form class="stack-form" id="exam-create-form">${common({course_id:params.get('course')||''},true)}<input type="hidden" name="languages" value="c,cpp,java"><div class="bridge-inline"><button class="btn btn-primary">Tạo và mở thiết lập</button></div></form>`);
        dialog.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const form=e.currentTarget;if(form.elements.type.value==='programming'&&!form.querySelector('[name=language]'))for(const value of ['c','cpp','java']){const input=document.createElement('input');input.type='checkbox';input.name='language';input.value=value;input.checked=true;input.hidden=true;form.append(input);}save(form);});return;
      }
      if(target.closest('[data-exam-activate]')){save($('exam-config-form'),true);return;}
      if(target.closest('[data-problem-add]')){document.querySelector('[data-problem-list]').insertAdjacentHTML('beforeend',problemView());return;}
      const p=target.closest('[data-program-problem]');
      if(p&&target.closest('[data-test-import]')){importTests(p);return;}
      if(p&&target.closest('[data-test-add]'))p.querySelector('[data-test-list]').insertAdjacentHTML('beforeend',testView());
      if(target.closest('[data-test-remove]'))target.closest('[data-program-test]').remove();
      if(p&&target.closest('[data-problem-remove]')&&confirm('Xóa bài toán và các test case khỏi thiết lập này?'))p.remove();
    });
    document.addEventListener('submit',event=>{if(event.target.matches('#exam-config-form')){event.preventDefault();save(event.target);}if(event.target.matches('#code-participants-form')){event.preventDefault();void saveParticipants(event.target);}});
    document.addEventListener('change',event=>{if(event.target.matches('[data-code-participant]')){participantDraft.selected[event.target.checked?'add':'delete'](event.target.value);participantSummary(true);}});
    document.addEventListener('input',event=>{if(event.target.matches('#code-participants-form textarea')){participantDraft.pasted=event.target.value;participantSummary(true);}});
  }
  window.examConfig={render,cards,payload,
    ackSaved(form){window.adminDrafts?.saved(form);if(participantDraft&&form.elements.id?.value===participantDraft.id){participantDraft.saved=participantIds();participantSummary(true);window.adminDrafts?.saved(document.querySelector('#code-participants-form'));}},
    restoreProblems(problems){const list=document.querySelector('[data-problem-list]');if(list&&Array.isArray(problems))list.innerHTML=problems.map(problemView).join('');},
    captureParticipants(){return participantDraft?{selected:[...participantDraft.selected],pasted:participantDraft.pasted}:null;},
    restoreParticipants(value){if(!participantDraft||!value)return;participantDraft.selected=new Set(value.selected||[]);participantDraft.pasted=value.pasted||'';const form=document.querySelector('#code-participants-form');if(form)form.elements.student_ids.value=participantDraft.pasted;participantRows();participantSummary(true);}
  };
})();
