/* Filters and course pickers share an accessible popup and native form values. */
(() => {
  'use strict';
  const selector='select[name="course"],select[name="course_id"],select[data-student-course-switch],select#admin-course-picker,select#design-switch-course,.list-controls select,#filter-form select,#archive-filter select,.notifications-toolbar select,#notification-page-size,.ref-toolbar select';
  const states=new Set(),bySelect=new WeakMap();
  let serial=0,active=null,scheduled=false,typed='',typedAt=0;

  function close(focus=false){
    if(!active)return;
    const state=active;active=null;
    if(state.menu.hasAttribute('popover'))try{state.menu.hidePopover();}catch(_){}
    state.menu.hidden=true;state.wrapper.removeAttribute('data-open');
    state.trigger.setAttribute('aria-expanded','false');state.trigger.removeAttribute('aria-activedescendant');
    if(focus&&state.trigger.isConnected)state.trigger.focus();
  }

  function position(state){
    if(!state.select.isConnected){close();return;}
    const box=state.trigger.getBoundingClientRect(),width=document.documentElement.clientWidth,height=innerHeight;
    const dialog=state.select.closest('dialog');
    const bounds=!state.menu.hasAttribute('popover')&&dialog?dialog.getBoundingClientRect():{left:0,right:width,top:0,bottom:height};
    const popupWidth=Math.min(box.width,Math.max(0,bounds.right-bounds.left-16));
    state.menu.style.width=popupWidth+'px';
    const below=bounds.bottom-box.bottom-8,above=box.top-bounds.top-8;
    const upwards=below<Math.min(state.menu.scrollHeight,180)&&above>below;
    const limit=Math.max(40,Math.min(320,upwards?above:below));
    state.menu.style.maxHeight=limit+'px';
    const popupHeight=Math.min(state.menu.scrollHeight,limit);
    state.menu.style.left=Math.max(bounds.left+8,Math.min(box.left,bounds.right-popupWidth-8))+'px';
    state.menu.style.top=Math.max(bounds.top+8,upwards?box.top-popupHeight-4:box.bottom+4)+'px';
  }

  function highlight(state,index){
    state.index=index;
    for(const option of state.menu.querySelectorAll('[data-course-option]'))option.classList.toggle('is-active',Number(option.dataset.courseOption)===index);
    const option=state.menu.querySelector(`[data-course-option="${index}"]`);
    if(option){
      state.trigger.setAttribute('aria-activedescendant',option.id);
      const top=option.offsetTop,bottom=top+option.offsetHeight;
      if(top<state.menu.scrollTop)state.menu.scrollTop=top;
      else if(bottom>state.menu.scrollTop+state.menu.clientHeight)state.menu.scrollTop=bottom-state.menu.clientHeight;
    }
  }

  function renderOptions(state){
    state.optionSignature=JSON.stringify([...state.select.options].map(o=>[o.value,o.label,o.disabled,o.hidden,o.selected,o.parentElement?.disabled]));
    const fragment=document.createDocumentFragment();
    state.available=[];
    for(const option of state.select.options){
      if(option.hidden)continue;
      const item=document.createElement('button');item.type='button';item.tabIndex=-1;
      item.id=state.menu.id+'-option-'+option.index;
      item.className='course-select-option';item.dataset.courseOption=String(option.index);
      item.setAttribute('role','option');item.setAttribute('aria-selected',String(option.selected));
      item.textContent=option.label;
      item.disabled=option.disabled||option.parentElement?.disabled===true;
      if(!item.disabled)state.available.push(option.index);
      fragment.append(item);
    }
    if(!fragment.childNodes.length){const empty=document.createElement('p');empty.className='course-select-empty';empty.textContent='Chưa có lựa chọn';fragment.append(empty);}
    state.menu.replaceChildren(fragment);
  }

  function open(state){
    if(state.trigger.disabled)return;
    close();renderOptions(state);active=state;
    state.trigger.focus({preventScroll:true});
    state.wrapper.dataset.open='true';state.trigger.setAttribute('aria-expanded','true');state.menu.hidden=false;
    // A popover is placed in the top layer, including when used inside a dialog.
    // https://developer.mozilla.org/en-US/docs/Web/API/HTMLElement/showPopover
    if(typeof state.menu.showPopover==='function'){
      state.menu.setAttribute('popover','manual');
      try{state.menu.showPopover();}catch(_){state.menu.removeAttribute('popover');}
    }
    position(state);highlight(state,state.available.includes(state.select.selectedIndex)?state.select.selectedIndex:state.available[0]);
  }

  function sync(state){
    const selected=state.select.selectedOptions[0]?.label||'Chọn tùy chọn';
    if(state.text.textContent!==selected)state.text.textContent=selected;
    const disabled=state.select.matches(':disabled')||!state.select.options.length;
    if(state.trigger.disabled!==disabled)state.trigger.disabled=disabled;
    const label=state.label+': '+selected;
    if(state.trigger.getAttribute('aria-label')!==label)state.trigger.setAttribute('aria-label',label);
    state.trigger.title=selected;
    const hidden=state.select.hidden||state.select.style.display==='none'||state.select.classList.contains('hidden');
    if(state.wrapper.hidden!==hidden)state.wrapper.hidden=hidden;
    state.wrapper.toggleAttribute('data-filter-active',!!state.select.value&&state.select.value!==state.select.options[0]?.value);
    if(state.select.validity.valid){state.trigger.removeAttribute('aria-invalid');state.error.hidden=true;}
    if((disabled||hidden)&&active===state)close();
    if(active===state){
      const signature=JSON.stringify([...state.select.options].map(o=>[o.value,o.label,o.disabled,o.hidden,o.selected,o.parentElement?.disabled]));
      if(signature!==state.optionSignature){renderOptions(state);position(state);highlight(state,state.select.selectedIndex);}
    }
  }

  function choose(state,index){
    if(!state.available.includes(index))return;
    const source=state.select,formId=source.form?.id,name=source.name,id=source.id,switcher=source.hasAttribute('data-student-course-switch');
    source.selectedIndex=index;sync(state);close();
    source.dispatchEvent(new Event('input',{bubbles:true}));source.dispatchEvent(new Event('change',{bubbles:true}));
    requestAnimationFrame(()=>{
      const current=source.isConnected?source:(id&&document.getElementById(id))||(formId&&document.getElementById(formId)?.elements.namedItem(name))||(switcher&&document.querySelector('[data-student-course-switch]'));
      bySelect.get(current)?.trigger.focus();
    });
  }

  function enhance(select){
    if(bySelect.has(select)||select.multiple||select.size>1||select.closest('template'))return;
    const id='course-select-'+(++serial),wrapper=document.createElement('span'),trigger=document.createElement('button'),text=document.createElement('span'),arrow=document.createElement('span'),menu=document.createElement('div'),error=document.createElement('span');
    const labelNode=select.labels?.[0]?.cloneNode(true);
    labelNode?.querySelectorAll('select,input,button,textarea').forEach(node=>node.remove());
    const label=select.getAttribute('aria-label')||labelNode?.textContent.trim()||'Bộ lọc';
    wrapper.className='course-select';trigger.type='button';trigger.className='course-select-trigger';trigger.id=id+'-trigger';
    trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-controls',id+'-menu');
    text.className='course-select-value';arrow.className='course-select-arrow fa fa-angle-down';arrow.setAttribute('aria-hidden','true');trigger.append(text,arrow);
    menu.id=id+'-menu';menu.className='course-select-menu';menu.setAttribute('role','listbox');menu.setAttribute('aria-label',label);menu.hidden=true;
    error.className='course-select-error';error.setAttribute('role','alert');error.hidden=true;
    select.before(wrapper);wrapper.append(select,trigger,error);select.classList.add('course-select-source');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    (select.closest('dialog')||document.body).append(menu);
    const state={select,wrapper,trigger,text,menu,error,label,available:[],index:-1};states.add(state);bySelect.set(select,state);
    select.addEventListener('invalid',event=>{event.preventDefault();trigger.setAttribute('aria-invalid','true');error.textContent=select.validationMessage;error.hidden=false;trigger.focus();});
    sync(state);
  }

  function refresh(){
    scheduled=false;
    for(const state of states){
      if(!state.select.isConnected){if(active===state)close();state.menu.remove();states.delete(state);}
      else sync(state);
    }
    document.querySelectorAll(selector).forEach(enhance);
  }
  function schedule(){if(!scheduled){scheduled=true;queueMicrotask(refresh);}}
  document.addEventListener('click',event=>{
    const trigger=event.target.closest?.('.course-select-trigger');
    if(trigger){const state=bySelect.get(trigger.parentElement.querySelector('select'));if(state){if(active===state)close();else open(state);}return;}
    const option=event.target.closest?.('[data-course-option]');
    if(option&&active?.menu.contains(option)){choose(active,Number(option.dataset.courseOption));return;}
    if(active&&!active.wrapper.contains(event.target)&&!active.menu.contains(event.target))close();
  });
  document.addEventListener('change',event=>{const state=bySelect.get(event.target);if(state)sync(state);});
  document.addEventListener('reset',event=>queueMicrotask(()=>{
    if(active?.select.form===event.target)close();
    for(const state of states)if(state.select.form===event.target)sync(state);
  }));
  document.addEventListener('keydown',event=>{
    const trigger=event.target.closest?.('.course-select-trigger'),state=trigger&&bySelect.get(trigger.parentElement.querySelector('select'));
    if(event.key==='Escape'&&active){event.preventDefault();close(true);return;}
    if(event.key==='Tab'&&active){close();return;}
    if(!state||event.ctrlKey||event.metaKey)return;
    if(['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(event.key)){
      event.preventDefault();const wasOpen=active===state;
      if(!wasOpen){open(state);return;}
      if(event.key==='Enter'||event.key===' '){choose(state,state.index);return;}
      const index=state.available.indexOf(state.index),last=state.available.length-1;
      highlight(state,state.available[event.key==='Home'?0:event.key==='End'?last:Math.max(0,Math.min(last,index+(event.key==='ArrowDown'?1:-1)))]);return;
    }
    if(event.key.length===1&&!event.altKey){
      event.preventDefault();if(active!==state)open(state);
      if(Date.now()-typedAt>800)typed='';typed+=event.key.toLocaleLowerCase('vi');typedAt=Date.now();
      const found=state.available.find(index=>state.select.options[index].label.toLocaleLowerCase('vi').startsWith(typed));
      if(found!==undefined)highlight(state,found);
    }
  });
  addEventListener('resize',()=>{if(active)position(active);});
  document.addEventListener('scroll',event=>{if(active&&!active.menu.contains(event.target))position(active);},true);
  // Ignore mutations of the generated controls to avoid observing our own UI updates.
  const observer=new MutationObserver(records=>{if(records.some(r=>(r.type==='childList'&&!r.target.closest?.('.course-select-trigger,.course-select-menu,.course-select-error'))||r.target.matches?.(selector)))schedule();});
  observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','value','aria-label','hidden','style','class']});
  refresh();
})();
