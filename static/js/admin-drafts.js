/* Local, account-scoped teacher drafts. Binary files and credentials are excluded. */
(() => {
  'use strict';
  const owner=document.querySelector('[data-draft-owner]')?.dataset.draftOwner;if(!owner)return;
  const selector='#exam-config-form,#settings-form,#code-participants-form,#notification-form,form[data-action="assignment"],form[data-action="material"],form[data-action="event"],form[data-exam-timing-form]';
  const forms=new Map(),prefix='lms:teacher-draft:v1:'+encodeURIComponent(owner)+':';
  let changing=false,leaving=false,timer;
  const fieldAllowed=node=>node.name&&!['password','new_password','current_password','confirm_password','exam_password','notification_student'].includes(node.name)&&node.type!=='password'&&!['submit','button','reset'].includes(node.type)&&!node.matches('[data-list-query],[data-list-status],[data-list-direction]');
  function capture(form){
    const fields=[...form.elements].filter(fieldAllowed).filter(n=>n.type!=='file').map(n=>({name:n.name,type:n.type,value:n.value,checked:['checkbox','radio'].includes(n.type)?n.checked:undefined}));
    const files=[...form.querySelectorAll('input[type=file]')].flatMap(n=>[...n.files].map(f=>f.name));
    const extra=form.getAttribute('id')==='exam-config-form'?{problems:[...form.querySelectorAll('[data-program-problem]')].map(p=>({title:p.querySelector('[data-problem-title]').value,statement:p.querySelector('[data-problem-statement]').value,points:p.querySelector('[data-problem-points]').value,time_limit_ms:p.querySelector('[data-problem-time]').value,memory_limit_mb:p.querySelector('[data-problem-memory]').value,checker:p.querySelector('[data-problem-checker]').value,tests:[...p.querySelectorAll('[data-program-test]')].map(t=>({input:t.querySelector('[data-test-input]').value,output:t.querySelector('[data-test-output]').value,sample:t.querySelector('[data-test-sample]').checked}))}))}:form.getAttribute('id')==='code-participants-form'?window.examConfig?.captureParticipants():form.getAttribute('id')==='notification-form'?{recipients:window.notificationDraft?.capture()||[]}:null;
    return {fields,files,extra};
  }
  function apply(form,value){
    changing=true;
    try{
      if(form.getAttribute('id')==='exam-config-form'&&value.extra?.problems)window.examConfig?.restoreProblems(value.extra.problems);
      const indexes=new Map();
      for(const field of value.fields||[]){
        const index=indexes.get(field.name)||0,nodes=[...form.elements].filter(n=>fieldAllowed(n)&&n.name===field.name&&n.type===field.type),node=nodes[index];indexes.set(field.name,index+1);
        if(!node)continue;
        if(['checkbox','radio'].includes(node.type))node.checked=!!field.checked;else node.value=field.value;
      }
      form.querySelectorAll('input[type=file]').forEach(n=>n.value='');
      if(form.getAttribute('id')==='code-participants-form')window.examConfig?.restoreParticipants(value.extra);
      if(form.getAttribute('id')==='notification-form')window.notificationDraft?.restore(value.extra?.recipients||[]);
      // Repaint custom select labels without firing navigation/form handlers.
      form.querySelectorAll('select').forEach(n=>n.setAttribute('data-draft-restored',String(Date.now())));
      document.dispatchEvent(new Event('admin-draft-restored'));
    }finally{changing=false;}
  }
  function key(form){const q=new URLSearchParams(location.search),kind=form.getAttribute('id')||form.dataset.action;return prefix+encodeURIComponent([kind,form.elements.course_id?.value||q.get('course')||'',form.elements.id?.value||q.get('exam')||''].join('|'));}
  function read(key){try{const value=JSON.parse(localStorage.getItem(key));return value?.version===1&&Date.now()-value.updated<30*86400000?value:null;}catch(_){return null;}}
  function remove(key){try{localStorage.removeItem(key);}catch(_){}}
  function write(state,value){
    try{
      const record=JSON.stringify({version:1,updated:Date.now(),base:state.base,value});
      if(record.length>2000000)throw new Error('Draft too large');
      localStorage.setItem(state.key,record);return true;
    }catch(_){return false;}
  }
  function paint(state){
    if(!state.form.isConnected)return;
    const offer=state.offer,box=state.banner;
    box.hidden=!offer&&!state.dirty;
    const text=offer?'Có bản nháp trên máy này. '+(offer.base!==state.base?'Dữ liệu trên máy chủ đã thay đổi; kiểm tra kỹ trước khi khôi phục.':'Bạn có thể khôi phục nội dung chưa lưu.')+(offer.value.files?.length?' File đính kèm cần được chọn lại.':''):'Chưa lưu · '+(state.persisted?'Đã giữ bản nháp trên máy này.':'Chưa lưu được nháp trên máy này; giữ trang mở để tránh mất nội dung.');
    const label=box.querySelector('[data-draft-message]');if(label.textContent!==text)label.textContent=text;
    box.querySelector('[data-draft-restore]').hidden=!offer;
    box.querySelector('[data-draft-discard]').textContent=offer?'Bỏ nháp':'Bỏ thay đổi';
  }
  function update(state){
    if(changing||leaving||!state.form.isConnected)return;
    const value=capture(state.form),signature=JSON.stringify(value);
    if(signature===state.current)return;
    state.current=signature;state.offer=null;state.dirty=signature!==state.base;
    if(state.dirty)state.persisted=write(state,value);else remove(state.key);
    paint(state);
  }
  function mount(){
    if(changing||leaving)return;
    for(const [form,state] of forms)if(!form.isConnected){state.banner.remove();forms.delete(form);}
    for(const form of document.querySelectorAll(selector)){
      if(forms.has(form)||!form.querySelector('input:not([type=hidden]):not(:disabled),textarea:not(:disabled),select:not(:disabled)'))continue;
      const base=JSON.stringify(capture(form)),draftKey=key(form),offer=read(draftKey),banner=document.createElement('div');
      banner.className='admin-draft-banner';banner.dataset.adminDraftStatus='';banner.setAttribute('role','status');
      banner.innerHTML='<span data-draft-message></span><div><button type="button" class="btn btn-secondary btn-small" data-draft-restore>Khôi phục nháp</button><button type="button" class="btn btn-ghost btn-small" data-draft-discard>Bỏ nháp</button></div>';
      form.prepend(banner);const state={form,key:draftKey,base,current:base,banner,offer:offer&&JSON.stringify(offer.value)!==base?offer:null,dirty:false,persisted:false};forms.set(form,state);paint(state);
      banner.addEventListener('click',event=>{
        if(event.target.closest('[data-draft-restore]')&&state.offer){const draft=state.offer;state.offer=null;apply(form,draft.value);state.current='';update(state);}
        if(event.target.closest('[data-draft-discard]')){if(state.dirty)apply(form,JSON.parse(state.base));remove(state.key);state.offer=null;state.dirty=false;state.current=state.base;paint(state);}
      });
    }
    for(const state of forms.values())update(state);
  }
  function saved(form){const state=forms.get(form);if(!state)return;remove(state.key);state.base=JSON.stringify(capture(form));state.current=state.base;state.offer=null;state.dirty=false;paint(state);}
  function hasDirty(){for(const state of forms.values())update(state);return [...forms.values()].some(s=>s.form.isConnected&&s.dirty);}
  function guard(){return !hasDirty()||window.confirm('Bạn có thay đổi chưa lưu. Bản nháp được giữ trên máy này nếu trình duyệt cho phép. Tiếp tục rời nội dung đang soạn?');}
  document.addEventListener('input',event=>{const state=forms.get(event.target.closest('form'));if(state)update(state);},true);
  document.addEventListener('change',event=>{const state=forms.get(event.target.closest('form'));if(state)update(state);},true);
  document.addEventListener('click',event=>{
    if(leaving||event.defaultPrevented||event.ctrlKey||event.metaKey||event.shiftKey||event.button>0||event.target.closest('[data-admin-draft-status]'))return;
    const target=event.target.closest('a[href],[data-tab],[data-course],[data-course-back],[data-exam-filter],[data-design-close]');if(!target)return;
    if(target.matches('a')&&(target.target==='_blank'||target.hasAttribute('download')||target.getAttribute('href')?.startsWith('#')))return;
    if(target.matches('[data-design-close]')&&![...forms.values()].some(s=>s.dirty&&s.form.closest('dialog')===target.closest('dialog')))return;
    const dirty=hasDirty();
    if(!guard()){event.preventDefault();event.stopImmediatePropagation();}
    else if(dirty&&target.matches('a'))leaving=true;
  },true);
  document.addEventListener('change',event=>{
    if(changing||!event.target.matches('#design-switch-course,[data-admin-course-switch]'))return;
    if(!guard()){event.target.value=new URLSearchParams(location.search).get('course')||'';event.target.dispatchEvent(new Event('admin-draft-select-reset'));event.stopImmediatePropagation();}
  },true);
  document.addEventListener('cancel',event=>{if(event.target.matches('dialog')&&[...forms.values()].some(s=>s.dirty&&s.form.closest('dialog')===event.target)&&!guard())event.preventDefault();},true);
  addEventListener('beforeunload',event=>{if(!leaving&&hasDirty()){event.preventDefault();event.returnValue='';}});
  const observer=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(mount,80);});observer.observe(document.body,{childList:true,subtree:true});
  window.adminDrafts={saved,guard,dirty:hasDirty,allowNavigation(){leaving=true;},check:mount};mount();
})();
