/* Review the saved configuration; reference runs never create student submissions. */
(() => {
  'use strict';
  const esc=window.cssEscape,names={c:'C',cpp:'C++',java:'Java',python:'Python'};
  async function open(examId){
    if(window.adminDrafts?.dirty())throw new Error('Hãy lưu các thay đổi cấu hình trước khi kiểm tra mở thi.');
    const report=await window.cssRequest('/api/admin/exam-preflight?exam='+encodeURIComponent(examId));
    const dialog=document.createElement('dialog');dialog.className='exam-preflight-dialog';dialog.setAttribute('aria-labelledby','preflight-title');
    const metric=(label,value)=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`;
    dialog.innerHTML=`<header class="preflight-heading"><div><p class="eyebrow">KIỂM TRA TRƯỚC KHI MỞ THI</p><h2 id="preflight-title">${esc(report.title)}</h2></div><button type="button" class="btn btn-ghost" data-preflight-close aria-label="Đóng kiểm tra">×</button></header><dl class="preflight-summary">${metric('Khóa học',report.course_name)}${metric('Hình thức',report.type==='programming'?'Thi lập trình':'Thi nộp file')}${metric('Loại kỳ thi',({test:'Test · Không tính điểm',midterm:'Giữa kỳ',final:'Cuối kỳ'})[report.assessment_type])}${metric('Thời lượng',report.duration_minutes+' phút')+metric('Giờ bắt đầu',report.scheduled_at?new Date(report.scheduled_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Ngay khi xác nhận mở')+metric('Kết thúc',report.planned_end?new Date(report.planned_end).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):report.duration_minutes+' phút sau khi mở')}${metric('Thí sinh',report.participants.length)}${report.type==='programming'?metric('Bài toán / Tổng điểm',report.problems.length+' bài / '+report.total_points+' điểm')+metric('Ngôn ngữ',report.languages.map(l=>names[l]).join(', ')):metric('Số file đề',report.files.length)}</dl><p class="preflight-rule">Kỳ thi tính giờ chung theo giờ bắt đầu đã đặt. Mở trước lịch sẽ đưa phòng thi vào trạng thái chờ, sinh viên chưa vào được. Vào muộn chỉ còn thời gian của phòng thi.</p><ul class="preflight-checks">${report.checks.map(c=>`<li class="${c.ok?'passed':'failed'}"><i class="fa fa-${c.ok?'check-circle':'exclamation-circle'}" aria-hidden="true"></i><div><strong>${esc(c.label)}</strong><small>${esc(c.detail)}</small></div></li>`).join('')}</ul><p class="preflight-runner" data-preflight-runner></p><details class="preflight-roster"><summary>Danh sách dự thi (${report.participants.length})</summary><label>Tìm MSSV hoặc họ tên<input type="search" data-preflight-search placeholder="Tìm trong danh sách đã lưu…"></label><div class="preflight-people">${report.participants.map(s=>`<p data-preflight-person><strong>${esc(s.student_id)}</strong> · ${esc(s.full_name)}</p>`).join('')}</div></details>${report.files.length?`<details><summary>File đề đã phân phối</summary><ul>${report.files.map(f=>`<li>${esc(f.name)} · ${f.exists?'Có file':'Thiếu file'}</li>`).join('')}</ul></details>`:''}${report.problems.length?'<section class="preflight-reference"><h3>Chấm thử lời giải chuẩn</h3><p>Mỗi bài cần một lời giải chuẩn đạt toàn bộ test, gồm test mẫu và test ẩn. Kết quả thử không tính vào bài nộp hay điểm sinh viên. Mỗi lần chấm một bài; sửa cấu hình hoặc đổi image sẽ yêu cầu kiểm tra lại.</p>'+report.problems.map(p=>`<article class="preflight-problem" data-preflight-problem="${p.index}"><h4>${p.index+1}. ${esc(p.title)} · ${p.points} điểm · ${p.tests} test</h4><form data-preflight-reference="${p.index}" class="stack-form"><label>Ngôn ngữ lời giải<select name="language">${report.languages.map(l=>`<option value="${l}">${names[l]}</option>`).join('')}</select></label><label>Lời giải chuẩn<textarea name="source" rows="7" maxlength="100000" spellcheck="false" placeholder="Đọc stdin, ghi stdout; Java dùng public class Main."></textarea></label><button type="submit" class="btn btn-secondary" ${report.checks.every(c=>c.ok)&&report.runner.ready?'':'disabled'}>Chấm thử toàn bộ test</button><p data-preflight-result role="status"></p><pre class="code-output" data-preflight-output hidden></pre></form></article>`).join('')+'</section>':''}<p class="alert alert-error" data-preflight-error role="alert" hidden></p><footer class="preflight-actions"><button type="button" class="btn btn-secondary" data-preflight-close>Quay lại chỉnh sửa</button><button type="button" class="btn btn-primary" data-preflight-confirm disabled>Xác nhận mở kỳ thi</button></footer>`;
    document.body.append(dialog);dialog.showModal();
    let latest=report,timer=null,busy=false,closed=false;
    const error=message=>{const node=dialog.querySelector('[data-preflight-error]');node.textContent=message;node.hidden=!message;};
    function paint(data){
      if(closed)return;
      if(data.fingerprint!==report.fingerprint){error('Cấu hình hoặc danh sách đã thay đổi. Đóng màn hình này và kiểm tra lại.');dialog.querySelector('[data-preflight-confirm]').disabled=true;return;}
      latest=data;
      const running=data.jobs.some(j=>j.state==='running');
      dialog.querySelector('[data-preflight-runner]').textContent='Bộ chấm: '+data.runner.detail;
      dialog.querySelector('[data-preflight-confirm]').disabled=!data.can_open||running||busy;
      for(const p of data.problems){
        const form=dialog.querySelector(`[data-preflight-reference="${p.index}"]`),node=form.querySelector('[data-preflight-result]'),output=form.querySelector('[data-preflight-output]');
        const job=data.jobs.find(j=>j.problem_index===p.index),result=p.verification?.result;
        node.textContent=job?.state==='running'?`Đang ${job.stage==='compiling'?'biên dịch':'chấm'} · ${job.completed_tests}/${job.total_tests} test`:job?.state==='error'?job.error:result?`${result.verdict} · ${result.passed}/${result.total} test${p.verified?' · Đã kiểm tra cấu hình hiện tại':''}`:'Chưa có kết quả chấm thử đạt toàn bộ test.';
        node.className=p.verified?'preflight-pass':'preflight-pending';
        output.textContent=result?.compile_log||result?.tests?.filter(t=>t.verdict!=='AC').map(t=>`Test #${t.index} · ${t.verdict}\nInput: ${t.input}\nMong đợi: ${t.expected}\nThực tế: ${t.actual}\n${t.stderr||''}`).join('\n\n')||'';output.hidden=!output.textContent;
        form.querySelector('button').disabled=running||!data.runner.ready||!data.checks.every(c=>c.ok)||busy;
      }
      clearTimeout(timer);if(running)timer=setTimeout(refresh,1200);
    }
    async function refresh(){try{paint(await window.cssRequest('/api/admin/exam-preflight?exam='+encodeURIComponent(examId)));}catch(e){if(!closed){error(e.message);timer=setTimeout(refresh,2500);}}}
    dialog.addEventListener('input',event=>{if(event.target.matches('[data-preflight-search]')){const q=event.target.value.toLocaleLowerCase('vi');dialog.querySelectorAll('[data-preflight-person]').forEach(n=>n.hidden=!n.textContent.toLocaleLowerCase('vi').includes(q));}});
    dialog.addEventListener('submit',async event=>{
      const form=event.target;if(!form.matches('[data-preflight-reference]'))return;event.preventDefault();if(busy)return;
      busy=true;error('');paint(latest);
      try{await window.cssRequest('/api/admin/exam-preflight/verify',{method:'POST',body:new URLSearchParams({exam_id:examId,fingerprint:report.fingerprint,problem_index:form.dataset.preflightReference,language:form.elements.language.value,source:form.elements.source.value})});await refresh();}
      catch(e){error(e.message);}finally{busy=false;paint(latest);}
    });
    dialog.addEventListener('click',async event=>{
      if(event.target.closest('[data-preflight-close]')){dialog.close();return;}
      if(!event.target.closest('[data-preflight-confirm]')||busy||!latest.can_open)return;
      busy=true;error('');paint(latest);
      try{await window.cssRequest('/api/admin/exam-preflight/open',{method:'POST',body:new URLSearchParams({exam_id:examId,type:report.type,fingerprint:report.fingerprint})});window.adminDrafts?.allowNavigation();location.reload();}
      catch(e){error(e.message);busy=false;paint(latest);}
    });
    paint(report);
    return new Promise(resolve=>dialog.addEventListener('close',()=>{closed=true;clearTimeout(timer);dialog.remove();resolve();},{once:true}));
  }
  window.examPreflight={open};
})();
