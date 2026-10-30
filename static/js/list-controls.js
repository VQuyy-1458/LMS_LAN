/* Shared record-list filtering and sorting. Always apply before pagination. */
(() => {
  'use strict';
  const collator=new Intl.Collator('vi',{numeric:true,sensitivity:'base'});
  const states=new Map(),configs=new Map(),listeners=new Map(),callbacks=new Map(),timers=new Map();
  const esc=value=>window.cssEscape(String(value??''));
  const text=value=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLocaleLowerCase('vi');
  const title=r=>r.title||r.name||r.original_filename||r.filename||r.problem_title||'';
  const date=value=>{const n=Date.parse(value);return Number.isFinite(n)?n:null;};
  const time=r=>date(r.submitted_at||r.created_at||r.graded_at||r.starts_at||r.lesson_at||r.due_at);
  const field=(key,label,get)=>({key,label,get});
  const named=field('title','Tên A–Z',title),when=field('time','Thời gian',time);
  const lifecycle=[['open','Đang mở'],['upcoming','Sắp diễn ra'],['closed','Đã đóng']];
  function life(r){
    if(r.waiting)return 'upcoming';
    if(r.state)return ['started','distributed'].includes(r.state)?(r.state==='started'?'open':'upcoming'):['ended','closed','expired','completed'].includes(r.state)?'closed':'upcoming';
    if(r.status==='completed'||r.closed||r.closed_at)return 'closed';
    if(r.open!==undefined)return r.open?'open':'closed';
    if(r.session_status)return r.session_status==='open'?'open':r.session_status==='upcoming'?'upcoming':'closed';
    if(r.due_at||r.expires_at){
      if(Date.parse(r.due_at||r.expires_at)<=Date.now())return 'closed';
      if(date(r.opens_at||r.available_from||r.starts_at)>Date.now())return 'upcoming';
      return 'open';
    }
    if(r.starts_at){const start=Date.parse(r.starts_at),end=date(r.ends_at);return start>Date.now()?'upcoming':end!==null&&end>Date.now()?'open':'closed';}
    return r.status==='active'?'open':'closed';
  }
  const rank=value=>({open:0,upcoming:1,closed:2})[value]??3;
  const lifeField=field('status','Trạng thái: mở → sắp diễn ra → đóng',r=>rank(life(r)));
  const submissionStatus=r=>r.state==='queued'?'queued':r.state==='running'?'running':r.result?.verdict||r.status||r.state||(r.score===null||r.score===undefined?'pending':'graded');
  const schemas={
    people:{fields:[field('id','MSSV / tài khoản',r=>r.student_id||r.username||r.user_id),field('name','Họ tên A–Z',r=>r.full_name||r.username||r.student_id),field('status','Trạng thái',r=>r.active===false?1:0),field('ip','Địa chỉ IP',r=>r.last_ip||r.ip),when],defaultSort:'id',status:r=>r.active===false?'locked':'active',statuses:[['active','Hoạt động'],['locked','Đã khóa']]},
    monitor:{fields:[field('id','MSSV',r=>r.student_id),field('name','Họ tên A–Z',r=>r.full_name),field('count','Số lần nộp',r=>r.submission_count||0),field('remaining','Thời gian còn lại',r=>r.remaining_seconds),field('status','Trạng thái đăng nhập',r=>r.logged_in?0:1)],defaultSort:'id',status:r=>r.logged_in?'online':'offline',statuses:[['online','Đang đăng nhập'],['offline','Ngoại tuyến']]},
    courses:{fields:[lifeField,field('code','Mã khóa học',r=>r.code),named,field('semester','Học kỳ',r=>r.semester),when],defaultSort:'status',status:life,statuses:lifecycle,tie:['title','code']},
    materials:{fields:[named,field('filename','Tên file',r=>r.original_filename||r.filename),when],defaultSort:'title',status:r=>(r.original_filename||r.filename||'').split('.').pop().toLowerCase(),statuses:'auto'},
    assignments:{fields:[lifeField,named,field('time','Hạn nộp',r=>date(r.due_at)),field('attempts','Số lần nộp tối đa',r=>r.max_attempts)],defaultSort:'status',status:life,statuses:lifecycle,tie:['time','title']},
    attendance:{fields:[lifeField,named,field('time','Ngày / giờ học',r=>date(r.lesson_at||r.created_at)),field('deadline','Hạn điểm danh',r=>date(r.expires_at))],defaultSort:'status',status:life,statuses:lifecycle,tie:['time','title']},
    events:{fields:[lifeField,named,field('time','Thời gian diễn ra',r=>date(r.starts_at||r.at)),field('kind','Loại hoạt động',r=>r.kind||r.type)],defaultSort:'status',status:life,statuses:lifecycle,tie:['time','title']},
    exams:{fields:[lifeField,named,field('time','Lịch thi',r=>date(r.scheduled_at||r.started_at)),field('duration','Thời lượng',r=>r.duration_minutes),field('type','Hình thức thi',r=>r.type)],defaultSort:'status',status:life,statuses:lifecycle,tie:['time','title']},
    submissions:{fields:[when,field('attempt','Lần nộp',r=>r.attempt),named,field('student','MSSV',r=>r.student_id),field('score','Điểm',r=>r.effective_score??r.result?.score??r.score),field('status','Trạng thái chấm',r=>({queued:0,running:1,pending:2})[submissionStatus(r)]??3)],defaultSort:'time',status:submissionStatus,statuses:[['queued','Đang chờ chấm'],['running','Đang chấm'],['pending','Chờ chấm điểm'],['graded','Đã chấm điểm'],['done','Đã chấm'],...['AC','WA','CE','RE','TLE','MLE','OLE','SYSTEM_ERROR'].map(v=>[v,v])],tie:['attempt','title']},
    grades:{fields:[field('id','MSSV',r=>r.student_id),field('name','Họ tên A–Z',r=>r.full_name||r.name),named,field('score','Điểm',r=>r.score??r.total),when],defaultSort:'id',statuses:[]},
    notifications:{fields:[when,named,field('sender','Người gửi A–Z',r=>r.sender),field('status','Trạng thái đọc',r=>r.read?1:0)],defaultSort:'time',status:r=>r.read?'read':'unread',statuses:[['unread','Chưa đọc'],['read','Đã đọc']]},
    problems:{fields:[field('index','Thứ tự bài',r=>r.index),named,field('points','Điểm tối đa',r=>r.points),field('score','Điểm tốt nhất',r=>r.best_score)],defaultSort:'index',status:r=>r.verdict||'none',statuses:[['none','Chưa nộp'],['queued','Đang chờ chấm'],['running','Đang chấm'],...['AC','WA','CE','RE','TLE','MLE','OLE','SYSTEM_ERROR'].map(v=>[v,v])]},
    history:{fields:[when,field('attempt','Lần chấm / lần nộp',r=>r.attempt),field('score','Điểm',r=>r.score??r.result?.score),field('by','Người chấm A–Z',r=>r.graded_by||r.requested_by),named],defaultSort:'time',statuses:[]}
  };
  schemas.attendancePeople={...schemas.people,status:r=>r.attendance_status,statuses:[['present','Có mặt'],['late','Đến muộn'],['unrecorded','Chưa điểm danh'],['absent','Vắng'],['excluded','Không tính điểm']],fields:[...schemas.people.fields.filter(f=>!['status','ip','time'].includes(f.key)),field('status','Trạng thái điểm danh',r=>({present:0,late:1,unrecorded:2,absent:3,excluded:4})[r.attendance_status]),field('time','Thời gian điểm danh',r=>date(r.checked_in_at))]};
  const policies={
    people:{filterLabel:'Trạng thái tài khoản',placeholder:'Tìm MSSV hoặc họ tên…',directionLabel:'Thứ tự MSSV / tài khoản'},
    monitor:{filterLabel:'Đăng nhập',placeholder:'Tìm MSSV, họ tên hoặc IP…',directionLabel:'Thứ tự MSSV'},
    courses:{filterLabel:'Trạng thái khóa học',placeholder:'Tìm tên, mã khóa học hoặc học kỳ…',statuses:[['open','Đang hoạt động'],['closed','Đã tổng kết']]},
    materials:{filterLabel:'Loại file',placeholder:'Tìm tên tài liệu hoặc tên file…',directionLabel:'Thứ tự tên tài liệu'},
    assignments:{filterLabel:'Nhận bài',placeholder:'Tìm tên hoặc nội dung bài tập…',statuses:[['open','Đang nhận bài'],['upcoming','Chưa mở'],['closed','Đã đóng']]},
    exams:{filterLabel:'Trạng thái kỳ thi',placeholder:'Tìm tên kỳ thi…'},
    attendance:{filterLabel:'Trạng thái phiên',placeholder:'Tìm buổi học hoặc phiên điểm danh…',statuses:[['open','Đang mở'],['closed','Đã kết thúc']]},
    attendancePeople:{filterLabel:'Điểm danh',placeholder:'Tìm MSSV hoặc họ tên…',directionLabel:'Thứ tự MSSV'},
    events:{filterLabel:'Loại hoạt động',placeholder:'Tìm buổi học hoặc hoạt động…',status:r=>{const value=r.kind||r.activity;return ['test','midterm','final'].includes(value)?'exam':value||(['file','programming'].includes(r.type)?'exam':'');},statuses:[['lesson','Buổi học'],['assignment','Bài tập'],['exam','Kỳ thi'],['announcement','Thông báo']]},
    submissions:{filterLabel:'Chấm điểm',placeholder:'Tìm tên bài, tên file hoặc MSSV…',directionLabel:'Thứ tự thời gian nộp',status:r=>(r.score??r.result?.score)===null||(r.score??r.result?.score)===undefined?'pending':'graded',statuses:[['pending','Chưa chấm'],['graded','Đã chấm']]},
    notifications:{filterLabel:'Trạng thái đọc',placeholder:'Tìm nội dung hoặc người gửi…',directionLabel:'Thứ tự thời gian gửi'},
    problems:{filterLabel:'Kết quả làm bài',placeholder:'Tìm tên bài toán…',directionLabel:'Thứ tự bài'},
    grades:{placeholder:'Tìm MSSV hoặc họ tên…',directionLabel:'Thứ tự MSSV'},
    history:{placeholder:'Tìm người chấm hoặc nội dung…',directionLabel:'Thứ tự thời gian chấm'}
  };
  function config(id,kind,options={}){
    const cfg={...schemas[kind],...policies[kind],...options};
    cfg.fixedOrder=['exams','assignments','courses','attendance','events'].includes(kind);
    if(kind==='submissions'&&(id.startsWith('programming:')||id.includes(':code:'))){
      cfg.status=submissionStatus;cfg.filterLabel='Kết quả chấm';
      cfg.statuses=[['queued','Đang chờ chấm'],['running','Đang biên dịch / chấm'],...['AC','WA','CE','RE','TLE','MLE','OLE','SYSTEM_ERROR'].map(v=>[v,v])];
    }
    if(kind==='submissions'&&cfg.defaultSort==='attempt')cfg.directionLabel='Thứ tự lần nộp';
    if(kind==='grades'&&cfg.defaultSort==='title'){cfg.directionLabel=options.directionLabel||'Thứ tự tên bài';cfg.placeholder=options.placeholder||'Tìm tên bài hoặc khóa học…';}
    if(id==='admin:admins'){cfg.placeholder='Tìm tên tài khoản admin…';cfg.directionLabel='Thứ tự tài khoản';}
    if(id==='admin:accounts'){
      cfg.filterLabel='Tình trạng tài khoản';
      cfg.statuses=[['active','Tài khoản đang mở'],['locked','Tài khoản đã khóa'],['login_locked','Khóa đăng nhập tạm'],['login_ok','Không khóa đăng nhập tạm']];
      cfg.matchesStatus=(r,s)=>s==='active'?r.active!==false:s==='locked'?r.active===false:s==='login_locked'?r.login_locked===true:r.login_locked===false;
    }
    if(!cfg.fields?.length)throw new Error('Unknown list schema: '+kind);
    configs.set(id,cfg);
    if(!states.has(id))states.set(id,{q:'',status:'',sort:cfg.defaultSort||cfg.fields[0].key,dir:'asc'});
    return cfg;
  }
  function compare(a,b){if(a===null||a===undefined||a==='')return b===null||b===undefined||b===''?0:1;if(b===null||b===undefined||b==='')return -1;return typeof a==='number'&&typeof b==='number'?a-b:collator.compare(String(a),String(b));}
  function view(id,rows,kind,options={}){
    const cfg=config(id,kind,options),state=states.get(id),q=text(state.q);
    cfg.values=cfg.statuses==='auto'?[...new Set(rows.map(cfg.status).filter(Boolean))].sort(collator.compare).map(v=>[v,v.toUpperCase()]):cfg.statuses||[];
    let result=rows.filter(r=>(!state.status||(cfg.matchesStatus?cfg.matchesStatus(r,state.status):cfg.status?.(r)===state.status))&&(!q||text(cfg.searchText?cfg.searchText(r):[...cfg.fields.map(f=>f.get(r)),r.description,r.full_name,r.student_id,r.original_filename,r.filename,r.feedback,r.course_name,r.message].join(' ')).includes(q)));
    const selected=cfg.fields.find(f=>f.key===cfg.defaultSort)||cfg.fields[0];
    const tie=(cfg.tie||['title']).map(key=>cfg.fields.find(f=>f.key===key)).filter(Boolean);
    const direction=!cfg.fixedOrder&&state.dir==='desc'?-1:1;
    result=result.map((row,index)=>({row,index})).sort((a,b)=>{
      let value=compare(selected.get(a.row),selected.get(b.row));
      if(value)return value*direction;
      for(const field of tie){value=compare(field.get(a.row),field.get(b.row));if(value)return value*direction;}
      return a.index-b.index;
    }).map(item=>item.row);
    return result;
  }
  function controls(id,kind,options={}){
    const cfg=configs.get(id)||config(id,kind,options),state=states.get(id),values=cfg.values||cfg.statuses||[];
    const choice=(items,value)=>items.map(([v,t])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(t)}</option>`).join('');
    const search=cfg.search===false?'':`<label class="list-query">Tìm kiếm<span class="list-search-field"><i class="fa fa-search" aria-hidden="true"></i><input type="search" ${cfg.searchInputId?`id="${esc(cfg.searchInputId)}"`:''} data-list-query value="${esc(state.q)}" placeholder="${esc(cfg.placeholder||'Tìm kiếm…')}" aria-label="${esc(cfg.placeholder||'Tìm trong danh sách')}"></span></label>`;
    const filter=cfg.statusFilter===false||!Array.isArray(values)||!values.length?'':`<label>${esc(cfg.filterLabel||'Bộ lọc')}<select data-list-status>${choice([['','Tất cả'],...values],state.status)}</select></label>`;
    const direction=cfg.fixedOrder||cfg.directionControl===false?'':orderControl({label:cfg.directionLabel||'Thứ tự',name:'list-direction:'+id,value:state.dir,list:true});
    if(!search&&!filter&&!direction)return '';
    return `<div class="list-controls" data-list-controls="${esc(id)}" role="group" aria-label="Lọc danh sách">${search}${filter}${direction}${search||filter?`<button type="button" class="btn btn-ghost btn-small list-clear" data-list-clear ${state.q||state.status?'':'disabled'}><i class="fa fa-undo" aria-hidden="true"></i><span>Xóa bộ lọc</span></button>`:''}</div>`;
  }
  function orderControl({label='Thứ tự',name,value='asc',list=false}){
    return `<fieldset class="list-order"><legend>${esc(label)}</legend><div class="list-order-options">${[['asc','Tăng dần','sort-amount-asc'],['desc','Giảm dần','sort-amount-desc']].map(([direction,text,icon])=>`<label class="list-order-choice"><input type="radio" name="${esc(name)}" value="${direction}" ${list?'data-list-direction':''} ${value===direction?'checked':''}><i class="fa fa-${icon}" aria-hidden="true"></i><span>${text}</span></label>`).join('')}</div></fieldset>`;
  }
  function enhance(id,target,rows,kind,callback,options={}){
    if(!target)return rows;
    const result=view(id,rows,kind,options);callbacks.set(id,callback);
    let anchor=target.tagName==='TBODY'?target.closest('.table-wrap,.table-scroll')||target.closest('table'):target;
    const existing=[...anchor.parentElement.querySelectorAll(':scope > [data-list-controls]')].find(n=>n.dataset.listControls===id);
    if(!existing)anchor.insertAdjacentHTML('beforebegin',controls(id,kind,options));
    return result;
  }
  function notify(id,focus){
    const callback=callbacks.get(id)||listeners.get(id.split(':')[0]);
    if(!callback)return;
    Promise.resolve(callback(id)).then(()=>{
      if(!focus)return;
      const box=[...document.querySelectorAll('[data-list-controls]')].find(n=>n.dataset.listControls===id);
      const input=focus.direction?box?.querySelector(`[data-list-direction][value="${focus.direction}"]`):focus.status?box?.querySelector('[data-list-status]')?.closest('.course-select')?.querySelector('.course-select-trigger'):box?.querySelector('[data-list-query]');
      input?.focus({preventScroll:true});if(input&&typeof focus.start==='number')try{input.setSelectionRange(focus.start,focus.end);}catch(_){}
    }).catch(error=>window.cssToast?.(error.message,'error'));
  }
  function preserveTable(id,table){
    if(!table?.tBodies[0])return;
    const update=()=>{
      const rows=[...table.tBodies[0].rows].map((node,index)=>{const value=Number(node.querySelector('[data-grade-total]')?.textContent);return {id:String(index),student_id:node.cells[0]?.textContent,full_name:node.cells[1]?.textContent,score:Number.isFinite(value)?value:null,node};});
      const result=enhance(id,table.tBodies[0],rows,'grades',update);
      const visible=new Set(result.map(r=>r.node));rows.forEach(r=>r.node.hidden=!visible.has(r.node));
      result.forEach(r=>table.tBodies[0].append(r.node));
    };
    update();
  }
  document.addEventListener('input',event=>{
    if(!event.target.matches?.('[data-list-query]'))return;
    const input=event.target,id=input.closest('[data-list-controls]').dataset.listControls;
    const clear=input.closest('[data-list-controls]').querySelector('[data-list-clear]');if(clear)clear.disabled=!(input.value||states.get(id).status);
    clearTimeout(timers.get(id));timers.set(id,setTimeout(()=>{states.get(id).q=input.value;notify(id,{start:input.selectionStart,end:input.selectionEnd});},180));
  });
  document.addEventListener('change',event=>{
    const box=event.target.closest?.('[data-list-controls]');if(!box)return;
    const state=states.get(box.dataset.listControls);
    clearTimeout(timers.get(box.dataset.listControls));
    const query=box.querySelector('[data-list-query]');if(query)state.q=query.value;
    if(event.target.matches('[data-list-direction]'))state.dir=event.target.value;
    else if(event.target.matches('[data-list-status]'))state.status=event.target.value;
    else return;
    const clear=box.querySelector('[data-list-clear]');if(clear)clear.disabled=!(state.q||state.status);
    // Some controllers keep the toolbar mounted; others render it with the rows.
    box.querySelectorAll('[data-list-direction]').forEach(input=>input.checked=input.value===state.dir);
    notify(box.dataset.listControls,event.target.matches('[data-list-direction]')?{direction:state.dir}:{status:true});
  });
  document.addEventListener('click',event=>{
    const box=event.target.closest?.('[data-list-controls]');if(!box)return;
    const id=box.dataset.listControls,state=states.get(id);
    if(event.target.closest('[data-list-clear]')){clearTimeout(timers.get(id));states.set(id,{...state,q:'',status:''});}
    else return;
    // enhance() keeps the toolbar mounted while the controller refreshes rows.
    box.outerHTML=controls(id);notify(id);
  });
  document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches?.('[data-list-query]')){event.preventDefault();const id=event.target.closest('[data-list-controls]').dataset.listControls;clearTimeout(timers.get(id));states.get(id).q=event.target.value;notify(id);}});
  window.listUi={view,controls,orderControl,enhance,preserveTable,life,compare,on(owner,callback){listeners.set(owner,callback);},reset(id){states.delete(id);},state(id){return states.get(id);}};
})();
