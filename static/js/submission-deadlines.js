/* One server-synchronized clock for file, code and assignment submission windows. */
(() => {
  'use strict';
  let serverTime=Date.now(),received=performance.now();
  const now=()=>serverTime+performance.now()-received;
  function sync(value){const parsed=Date.parse(value);if(Number.isFinite(parsed)){serverTime=parsed;received=performance.now();}refresh();}
  function refresh(){
    const current=now();
    document.querySelectorAll('[data-deadline-countdown]').forEach(node=>{
      const end=Date.parse(node.dataset.expiresAt);if(!Number.isFinite(end))return;
      const seconds=Math.max(0,Math.ceil((end-current)/1000));
      const text=seconds?`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`:(node.dataset.zeroLabel||'Hết giờ');
      if(node.textContent!==text)node.textContent=text;
      node.classList.toggle('urgent',seconds<=300);
    });
    document.querySelectorAll('[data-deadline-status]').forEach(node=>{
      const end=Date.parse(node.dataset.expiresAt);if(!Number.isFinite(end))return;
      const closed=end<=current,text=closed?'Đã đóng':(node.dataset.openLabel||'Đang nhận bài');
      if(node.textContent!==text)node.textContent=text;
      node.classList.toggle('green',!closed);node.classList.toggle('deadline-closed',closed);
    });
    document.querySelectorAll('form[data-deadline-form]').forEach(form=>{
      const end=Date.parse(form.dataset.expiresAt);if(!Number.isFinite(end)||end>current||form.dataset.deadlineClosed)return;
      form.dataset.deadlineClosed='true';
      form.querySelectorAll('input,select,textarea,button').forEach(control=>control.disabled=true);
      form.hidden=true;
      const message=document.createElement('p');message.className='alert alert-info';message.setAttribute('role','status');
      message.textContent='Đã hết thời gian. Hệ thống đã đóng nhận bài; các bài đã nộp trước đó vẫn được lưu.';
      message.dataset.deadlineMessage='true';
      form.before(message);
      document.dispatchEvent(new CustomEvent('submission-window-closed'));
    });
    document.querySelectorAll('[data-deadline-start]').forEach(button=>{
      const end=Date.parse(button.dataset.expiresAt);if(Number.isFinite(end)&&end<=current){button.disabled=true;button.textContent='Kỳ thi đã hết giờ';}
    });
    document.querySelectorAll('[data-exam-opens-at]').forEach(node=>{if(!node.dataset.openingHandled&&Date.parse(node.dataset.examOpensAt)<=current){node.dataset.openingHandled='true';document.dispatchEvent(new CustomEvent('exam-window-opened'));}});
  }
  function updateForm(form,end,allowed){
    if(!form||!end)return;form.dataset.expiresAt=end;
    if(allowed&&Date.parse(end)>now()&&form.dataset.deadlineClosed){delete form.dataset.deadlineClosed;form.hidden=false;form.querySelectorAll('input,select,textarea,button').forEach(n=>n.disabled=false);if(form.previousElementSibling?.dataset.deadlineMessage)form.previousElementSibling.remove();}
  }
  window.submissionDeadlines={sync,refresh,now,updateForm};
  setInterval(refresh,250);
})();
