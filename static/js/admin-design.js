/* Presentation adapter for the supplied admin reference; protected pages do not load it. */
(() => {
  'use strict';
  const root=document.querySelector('.admin-redesign');if(!root)return;
  const esc=window.cssEscape,$=id=>document.getElementById(id);
  const icons=window.classroomAdminIcons.decorate;
  icons(root);new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)icons(node);}).observe(root,{childList:true,subtree:true});
  function modal(title,body){
    const node=document.createElement('dialog');node.className='ref-modal';node.setAttribute('aria-label',title);
    node.innerHTML=`<div class="ref-dialog-head"><h2>${esc(title)}</h2><button class="btn btn-ghost" type="button" data-design-close aria-label="Đóng">×</button></div>${body}`;
    (root.querySelector('#learning-content')||root.querySelector('main')).append(node);
    node.addEventListener('close',()=>node.remove(),{once:true});node.showModal();return node;
  }
  function formError(form,message){let p=form.querySelector('.ref-form-error');if(!p){p=document.createElement('p');p.className='ref-form-error';p.setAttribute('role','alert');form.append(p);}p.textContent=message;}
  window.adminDesign={modal,formError};
  document.addEventListener('click',event=>{const close=event.target.closest('[data-design-close]');if(close)close.closest('dialog')?.close();});
  if(root.dataset.adminSection==='courses')root.querySelector('.page-title').classList.add('hidden');
  const accountForm=$('import-form');
  if(accountForm){
    const panel=$('accounts'),heading=panel.querySelector('.panel-heading'),actions=document.createElement('div');actions.className='ref-actions';
    actions.innerHTML='<button type="button" class="btn btn-secondary" id="design-import-students"><i class="fa fa-upload"></i> Nhập danh sách</button><button type="button" class="btn btn-primary" id="design-add-student"><i class="fa fa-plus"></i> Thêm sinh viên</button>';
    const template=heading.querySelector('a');if(template){template.className='btn btn-ghost';actions.prepend(template);}heading.append(actions);
    const details=document.createElement('details');details.className='ref-topic';details.innerHTML='<summary><strong>Nhập tài khoản sinh viên</strong><small>MSSV · Ngày sinh · Họ tên</small></summary><div class="ref-topic-body"></div>';accountForm.before(details);details.lastElementChild.append(accountForm);const result=$('import-result');if(result)details.lastElementChild.append(result);
    $('design-import-students').addEventListener('click',()=>{details.open=true;details.scrollIntoView({behavior:'smooth',block:'center'});$('pasted-text').focus();});
    $('design-add-student').addEventListener('click',()=>{
      const d=modal('Thêm sinh viên','<form class="stack-form" id="design-student-form"><label>Mã sinh viên<input name="student_id" required maxlength="80"></label><label>Họ và tên<input name="full_name" required maxlength="200"></label><label>Ngày sinh<input name="dob" type="date" required></label><p class="muted">Ngày sinh là mật khẩu ban đầu, theo định dạng DD/MM/YYYY.</p><div class="ref-actions"><button class="btn btn-primary">Tạo tài khoản</button></div></form>');
      d.querySelector('form').addEventListener('submit',async e=>{e.preventDefault();const f=new FormData(e.target),parts=String(f.get('dob')).split('-');const body=new URLSearchParams({pasted_text:`${f.get('student_id')}|${parts.reverse().join('/')}|${f.get('full_name')}`});const button=e.target.querySelector('button');button.disabled=true;try{const r=await window.cssRequest('/api/admin/accounts/import',{method:'POST',body});if(!r.created_count)throw new Error(r.duplicates?.length?'MSSV đã tồn tại.':r.errors?.[0]?.message||'Không tạo được tài khoản.');location.reload();}catch(error){formError(e.target,error.message);button.disabled=false;}});
    });
    const decorate=()=>panel.querySelectorAll('#accounts-body tr').forEach(tr=>{const td=tr.cells[0];if(!td||td.querySelector('.ref-person')||td.colSpan>1)return;const label=document.createElement('span');while(td.firstChild)label.append(td.firstChild);const person=document.createElement('div');person.className='ref-person';const avatar=document.createElement('span');avatar.className='ref-person-avatar';avatar.textContent=(tr.cells[1]?.textContent||label.textContent).trim().split(/\s+/).map(p=>p[0]).slice(-2).join('');person.append(avatar,label);td.append(person);});
    new MutationObserver(decorate).observe($('accounts-body'),{childList:true,subtree:false});decorate();
  }
  const adminForm=$('create-admin-form');if(adminForm){const details=document.createElement('details');details.className='ref-topic';details.innerHTML='<summary><strong>Thêm tài khoản Admin</strong><i class="fa fa-plus"></i></summary><div class="ref-topic-body"></div>';adminForm.before(details);details.lastElementChild.append(adminForm);}
})();
