/* Programming exam submission and real per-test grading results. */
(() => {
  'use strict';
  const esc=window.cssEscape,names={c:'C',cpp:'C++',java:'Java',python:'Python'},extensions={c:'.c',cpp:'.cpp',java:'.java',python:'.py'};
  const dates=v=>new Date(v).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'});
  const labels={AC:'Đúng',WA:'Sai kết quả',CE:'Lỗi biên dịch',RE:'Lỗi chạy',TLE:'Quá thời gian',MLE:'Vượt bộ nhớ',OLE:'Output quá lớn',SYSTEM_ERROR:'Lỗi bộ chấm'};
  const badge=v=>`<span class="code-verdict ${v==='AC'?'code-pass':'code-fail'}">${esc(v)} · ${esc(labels[v]||v)}</span>`;
  function status(row){
    if(row.state==='done'||row.state==='error')return badge(row.result?.verdict||'SYSTEM_ERROR');
    const stage=row.state==='queued'?'queued':row.stage||'preparing';
    const label=stage==='queued'?'Đang chờ chấm':stage==='compiling'?'Đang biên dịch':stage==='judging'?`Đang chấm${row.total_tests?` · ${row.completed_tests||0}/${row.total_tests} test`:''}`:'Đang chuẩn bị';
    return `<span class="code-verdict code-pending" data-grading-stage="${esc(stage)}"><i class="fa fa-circle-o-notch fa-spin" aria-hidden="true"></i> ${label}</span>`;
  }
  function result(row,admin=false){
    const r=['done','error'].includes(row.state)?row.result:null;
    return `<details class="code-result" data-code-result="${row.id}"><summary><strong>${esc(row.problem_title)}</strong> · ${esc(admin?row.student_id:row.original_filename)} · ${status(row)} ${r&&row.state==='done'?`${r.score}/${row.max_score} điểm · ${r.passed}/${r.total} test`:''}</summary><p class="muted">${esc(names[row.language])} · ${dates(row.submitted_at)}</p><a class="btn btn-secondary" href="/api/programming/source/${row.id}" download="${esc(row.original_filename)}">Tải mã nguồn</a>${r?`${badge(r.verdict)}${r.compile_log?`<pre class="code-output">\n${esc(r.compile_log)}</pre>`:''}<div class="table-scroll"><table><thead><tr><th>Test</th><th>Kết quả</th><th>Thời gian</th><th>Chi tiết</th></tr></thead><tbody>${r.tests.map(t=>`<tr><td>#${t.index}<small>${t.sample?'Test mẫu':'Test ẩn'}</small></td><td>${badge(t.verdict)}</td><td>${t.time_ms??'—'} ms</td><td>${Object.hasOwn(t,'input')?`<details><summary>Input / Output</summary><strong>Input</strong><pre class="code-output">\n${esc(t.input)}</pre><strong>Output mong đợi</strong><pre class="code-output">\n${esc(t.expected)}</pre><strong>Output thực tế</strong><pre class="code-output">\n${esc(t.actual)}</pre>${t.stderr?`<strong>Thông báo chạy</strong><pre class="code-output">\n${esc(t.stderr)}</pre>`:''}</details>`:'Nội dung test ẩn'}</td></tr>`).join('')}</tbody></table></div>`:''}${admin&&!['queued','running'].includes(row.state)?`<button type="button" class="btn btn-secondary" data-code-rejudge="${row.id}">Chấm lại</button>`:''}</details>`;
  }
  function student(data,course=''){return window.programmingStudent.render(data,course);}
  function admin(e){
    setTimeout(()=>{
      loadAdmin(e.id);
      const results=document.querySelector('[data-code-admin-results]');
      if(!results||results.dataset.codeAdminResults!==e.id)return;
      const status=document.createElement('div');status.className='alert alert-info';status.dataset.judgeStatus='';
      status.innerHTML='<span data-judge-message>Đang kiểm tra bộ chấm…</span> <button type="button" class="btn btn-secondary btn-small" data-judge-refresh>Kiểm tra lại</button>';
      results.before(status);loadJudgeStatus();
    },0);
    return `<section class="panel"><div class="panel-heading"><div><h2>Vận hành & chấm thi lập trình</h2><p class="muted">Chấm toàn bộ test đã nạp. Điểm bài toán = điểm tối đa × số test đạt / tổng số test.</p></div>${e.state==='idle'?`<button type="button" class="btn btn-primary" data-code-control="start" data-code-exam="${e.id}">${e.scheduled_at?'Lưu / Kiểm tra cấu hình':'Lưu và mở ngay'}</button>`:e.state==='started'?`<button type="button" class="btn btn-danger" data-code-control="end" data-code-exam="${e.id}">Kết thúc kỳ thi</button>`:'<span>Đã kết thúc</span>'}</div><p class="fine-print">Bộ chấm sử dụng Docker. Test ẩn chỉ hiển thị kết quả đạt/sai cho sinh viên; giảng viên xem được input và output thực tế.</p><div data-code-admin-results="${e.id}">Đang tải bài nộp…</div></section>`;
  }
  function history(data,course=''){
    const records=window.listUi.view('programming:all-history:'+course,(data.programming?.submissions||[]).filter(r=>!course||r.course_id===course),'submissions');
    return `<section class="panel"><h2>Lịch sử thi lập trình</h2>${window.listUi.controls('programming:all-history:'+course,'submissions')}${records.map(r=>result(r)).join('')||'<p class="muted">Chưa có bài nộp lập trình.</p>'}</section>`;
  }
  let adminBusy=false;
  async function loadJudgeStatus(){
    const box=document.querySelector('[data-judge-status]');if(!box)return;
    const button=box.querySelector('button');if(button.disabled)return;button.disabled=true;
    try{const data=await window.cssRequest('/api/admin/programming/status');box.querySelector('[data-judge-message]').textContent=data.detail;}
    catch(error){box.querySelector('[data-judge-message]').textContent=error.message;}
    finally{button.disabled=false;}
  }
  async function loadAdmin(id){
    const node=document.querySelector('[data-code-admin-results]');if(!node||node.dataset.codeAdminResults!==id||adminBusy)return;
    adminBusy=true;
    try{const data=await window.cssRequest('/api/admin/programming/submissions?exam='+encodeURIComponent(id));if(!node.isConnected)return;
      const opened=new Set([...node.querySelectorAll('details[open][data-code-result]')].map(n=>n.dataset.codeResult));
      node.innerHTML=window.listUi.enhance('programming:admin:'+id,node,data.submissions,'submissions',()=>loadAdmin(id)).map(r=>result(r,true)).join('')||'<p class="muted">Chưa có sinh viên nộp bài.</p>';
      node.querySelectorAll('[data-code-result]').forEach(n=>{if(opened.has(n.dataset.codeResult))n.open=true;});
    }catch(e){node.textContent=e.message;}finally{adminBusy=false;}
  }
  document.addEventListener('click',async event=>{
    if(event.target.closest('[data-judge-refresh]')){await loadJudgeStatus();return;}
    const start=event.target.closest('[data-code-start]'),control=event.target.closest('[data-code-control]'),rejudge=event.target.closest('[data-code-rejudge]'),button=start||control||rejudge;
    if(!button)return;button.disabled=true;
    try{
      if(start){await window.cssRequest('/api/student/programming/start',{method:'POST',body:new URLSearchParams({exam_id:start.dataset.codeStart})});location.reload();}
      if(control){
        if(control.dataset.codeControl==='start'){
          const form=document.querySelector('#exam-config-form');if(!form.reportValidity()){button.disabled=false;return;}
          await window.cssRequest('/api/admin/exam-configurations/save',{method:'POST',body:window.examConfig.payload(form,{starting:true})});
          window.examConfig.ackSaved(form);
          await window.examPreflight.open(control.dataset.codeExam);button.disabled=false;return;
        }
        await window.cssRequest('/api/admin/programming/control',{method:'POST',body:new URLSearchParams({exam_id:control.dataset.codeExam,action:control.dataset.codeControl})});location.reload();
      }
      if(rejudge){await window.cssRequest('/api/admin/programming/rejudge',{method:'POST',body:new URLSearchParams({submission_id:rejudge.dataset.codeRejudge})});const node=document.querySelector('[data-code-admin-results]');if(node)await loadAdmin(node.dataset.codeAdminResults);else document.dispatchEvent(new CustomEvent('archive-refresh'));}
    }catch(e){window.cssToast(e.message,'error');button.disabled=false;}
  });
  setInterval(()=>{const node=document.querySelector('[data-code-admin-results]');if(node)loadAdmin(node.dataset.codeAdminResults);},5000);
  window.programmingUi={student,admin,result,history,status};
  window.programmingStudent?.configure({result});
})();
