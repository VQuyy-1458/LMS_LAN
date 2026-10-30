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
      const text=seconds?`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`:'Hết giờ';
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
      form.before(message);
      document.dispatchEvent(new CustomEvent('submission-window-closed'));
    });
    document.querySelectorAll('[data-deadline-start]').forEach(button=>{
      const end=Date.parse(button.dataset.expiresAt);if(Number.isFinite(end)&&end<=current){button.disabled=true;button.textContent='Kỳ thi đã hết giờ';}
    });
  }
  window.submissionDeadlines={sync,refresh,now};
  setInterval(refresh,250);
})();
