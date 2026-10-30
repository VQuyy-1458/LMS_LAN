/* Time changes are separate from the frozen questions and participant roster. */
(() => {
  'use strict';
  const esc=window.cssEscape,local=value=>value?new Date(Date.parse(value)+7*3600000).toISOString().slice(0,19):'';
  function view(e){
    if(!['distributed','started'].includes(e.state)||e.type==='file'&&!e.active)return '';
    const running=e.state==='started'&&!e.waiting;
    return `<section class="panel" data-exam-clock="${esc(e.id)}"><h2>Điều chỉnh thời gian thi</h2>${e.waiting?window.submissionDeadlines.waiting(e.started_at):''}<p class="muted">${running?'Kỳ thi đang diễn ra. Giữ giờ bắt đầu thực tế; thay đổi thời lượng hoặc giờ kết thúc sẽ cập nhật hạn của sinh viên.':'Kỳ thi đang chờ. Có thể đổi giờ bắt đầu và thời lượng; sinh viên chỉ vào được khi tới giờ.'} Giờ Việt Nam (UTC+7).</p><form class="stack-form" data-exam-timing-form><input type="hidden" name="exam_id" value="${esc(e.id)}"><div class="two-cols"><label>Giờ bắt đầu<input type="datetime-local" name="scheduled_at" step="1" value="${local(e.started_at||e.scheduled_at)}" ${running?'disabled':''}></label><label>Cách điều chỉnh<select name="mode"><option value="duration">Theo thời lượng</option><option value="end">Theo giờ kết thúc cụ thể</option></select></label><label>Thời lượng (phút)<input type="number" name="duration_minutes" min="1" max="1440" required value="${e.duration_minutes}"></label><label>Giờ kết thúc (dùng khi chọn theo giờ kết thúc)<input type="datetime-local" name="ends_at" step="1" value="${local(e.ends_at)}"></label></div><button type="submit" class="btn btn-primary">Lưu thời gian thi</button><p data-exam-timing-result role="status"></p></form></section>`;
  }
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('[data-exam-timing-form]'))return;event.preventDefault();
    const body=new FormData(form),button=form.querySelector('[type=submit]'),result=form.querySelector('[data-exam-timing-result]');if(button.disabled)return;
    for(const key of ['scheduled_at','ends_at'])if(body.get(key))body.set(key,new Date(body.get(key)+'+07:00').toISOString());
    button.disabled=true;result.textContent='Đang cập nhật thời gian…';
    try{await window.cssRequest('/api/admin/exam-timing',{method:'POST',body});window.adminDrafts?.saved(form);location.reload();}
    catch(error){result.textContent=error.message;button.disabled=false;}
  });
  window.examTiming={view};
})();
