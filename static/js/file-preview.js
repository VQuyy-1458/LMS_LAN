/* Preview text as textContent; uploaded source and markup are never executed. */
(() => {
  'use strict';
  const esc=window.cssEscape;
  window.classroomPreview={decorate(root){root.querySelectorAll('a[href^="/api/learning/files/"]').forEach(link=>{if(link.dataset.hasPreview)return;link.dataset.hasPreview='true';const button=document.createElement('button');button.type='button';button.className='btn btn-ghost';button.textContent='Xem trực tiếp';button.dataset.previewUrl=link.getAttribute('href').replace('/files/','/preview/');link.before(button);});}};
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-preview-url]');if(!button)return;
    button.disabled=true;
    try{
      const data=await window.cssRequest(button.dataset.previewUrl),dialog=document.createElement('dialog');dialog.className='student-dialog student-preview-dialog';
      dialog.innerHTML=`<form method="dialog"><div class="panel-heading"><h2>${esc(data.name)}</h2><button class="btn btn-secondary" value="close">Đóng</button></div></form>`;
      if(data.kind==='pdf'){const a=document.createElement('a');a.className='btn btn-primary';a.href=data.url;a.target='_blank';a.rel='noopener';a.textContent='Mở PDF trong tab mới';dialog.append(a);}
      else {const pre=document.createElement('pre');pre.textContent=data.text;pre.tabIndex=0;dialog.append(pre);if(data.truncated){const p=document.createElement('p');p.className='muted';p.textContent='Nội dung xem trước đã được rút gọn. Tải file để xem toàn bộ.';dialog.append(p);}}
      dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
    }catch(error){window.cssToast(error.message,'error');}finally{button.disabled=false;}
  });
})();
