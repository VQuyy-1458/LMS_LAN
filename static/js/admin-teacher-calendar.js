/* A monthly teaching calendar backed by the same course events as student schedules. */
(() => {
  'use strict';
  const activityColors=window.classroomActivities;
  const esc=window.cssEscape;
  const key=v=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(v));
  const stamp=v=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(v));
  function mount(node,data){
    const today=key(new Date());let selected=today,month=today.slice(0,7);
    const courseName=id=>data.courses.find(c=>c.id===id)?.name||'Kỳ thi chung';
    const entries=[...data.events.filter(e=>['lesson','exam'].includes(e.kind)).map(e=>({...e,at:e.starts_at,activity:e.kind,label:e.kind==='lesson'?'Buổi học':'Lịch thi',href:`/admin/courses?course=${e.course_id}&tab=calendar${e.kind==='lesson'?'&lesson='+e.id:''}`})),...data.assignments.map(a=>({...a,at:a.due_at,activity:'assignment',label:'Hạn nộp bài',href:`/admin?section=submissions&course=${a.course_id}&assignment=${a.id}`})),...data.exams.filter(e=>e.scheduled_at).map(e=>({...e,at:e.scheduled_at,activity:activityColors.exam(e),label:'Kỳ thi',href:`/admin?section=exam&course=${e.course_id||''}&exam=${e.id}`}))].sort((a,b)=>Date.parse(a.at)-Date.parse(b.at));
    const row=e=>`<a class="teacher-calendar-event activity-surface" data-activity="${activityColors.kind(e.activity)}" href="${e.href}">${activityColors.badge(e.activity,e.label)}<strong>${esc(e.title)}</strong><small>${esc(courseName(e.course_id))} · ${stamp(e.at)}${e.location?' · '+esc(e.location):''}</small></a>`;
    window.listUi.on("teacher",()=>render());
    function render(){
      const visible=window.listUi.view("teacher:calendar",entries,"events");
      const [year,m]=month.split('-').map(Number),days=new Date(Date.UTC(year,m,0)).getUTCDate(),offset=(new Date(`${month}-01T12:00:00Z`).getUTCDay()+6)%7,chosen=visible.filter(e=>key(e.at)===selected),upcoming=visible.filter(e=>Date.parse(e.at)>=Date.now()).slice(0,4);
      node.innerHTML=`<section class="panel teacher-month"><div class="panel-heading"><h2>Lịch giảng dạy · ${m}/${year}</h2><div class="ref-actions"><button type="button" class="btn btn-ghost" data-teacher-month="-1" aria-label="Tháng trước">‹</button><button type="button" class="btn btn-secondary" data-teacher-today>Hôm nay</button><button type="button" class="btn btn-ghost" data-teacher-month="1" aria-label="Tháng sau">›</button></div></div>${window.listUi.controls("teacher:calendar","events")}<div class="teacher-calendar-grid">${['T2','T3','T4','T5','T6','T7','CN'].map(d=>`<span>${d}</span>`).join('')}${'<span></span>'.repeat(offset)}${Array.from({length:days},(_,i)=>{const day=`${month}-${String(i+1).padStart(2,'0')}`;return `<button type="button" data-teacher-day="${day}" class="${day===selected?'selected':''} ${day===today?'today':''} ${visible.some(e=>key(e.at)===day)?'has-events':''}" aria-label="Ngày ${i+1} tháng ${m}" aria-pressed="${day===selected}">${i+1}${activityColors.dots(visible.filter(e=>key(e.at)===day).map(e=>e.activity))}</button>`;}).join('')}</div>${activityColors.legend(visible.length?visible.map(e=>e.activity):['lesson','assignment','test','midterm','final'])}<div class="teacher-calendar-agenda"><h3>Ngày ${selected.split('-').reverse().join('/')}</h3>${chosen.map(row).join('')||'<p class="muted">Chưa có hoạt động trong ngày này.</p>'}</div></section><section class="panel teacher-upcoming"><div class="panel-heading"><h2>Hoạt động sắp tới</h2><a class="bridge-text-link" href="/admin/courses">Quản lý lịch học →</a></div>${upcoming.map(row).join('')||'<p class="muted">Chưa có hoạt động sắp tới.</p>'}<p class="muted teacher-calendar-help">Bấm buổi học để mở hoặc xem điểm danh của buổi đó.</p></section>`;
      window.classroomAdminIcons.decorate(node);
    }
    node.addEventListener('click',event=>{
      const day=event.target.closest('[data-teacher-day]'),shift=event.target.closest('[data-teacher-month]');
      if(day){selected=day.dataset.teacherDay;render();}
      else if(shift){const [y,m]=month.split('-').map(Number),date=new Date(Date.UTC(y,m-1+Number(shift.dataset.teacherMonth),1,12));month=date.toISOString().slice(0,7);selected=month===today.slice(0,7)?today:month+'-01';render();}
      else if(event.target.closest('[data-teacher-today]')){selected=today;month=today.slice(0,7);render();}
    });
    render();
  }
  window.teacherCalendar={mount};
})();
