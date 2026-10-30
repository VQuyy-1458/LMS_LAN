/* Shared activity names and markup for teacher and student views. */
(() => {
  'use strict';
  const names={lesson:'Buổi học',material:'Tài liệu',assignment:'Bài tập',attendance:'Điểm danh',test:'Test',midterm:'Giữa kỳ',final:'Cuối kỳ',exam:'Kỳ thi',announcement:'Thông báo'};
  const kind=value=>Object.hasOwn(names,value)?value:'exam';
  const esc=value=>window.cssEscape(value);
  const badge=(value,label)=>`<span class="activity-badge" data-activity="${kind(value)}">${esc(label||names[kind(value)])}</span>`;
  const legend=values=>`<div class="activity-legend" aria-label="Chú thích màu hoạt động">${[...new Set(values.map(kind))].map(value=>badge(value)).join('')}</div>`;
  function dots(values){
    const types=[...new Set(values.map(kind))];
    return types.length?`<span class="activity-dots" aria-hidden="true">${types.slice(0,5).map(value=>`<span data-activity="${value}"></span>`).join('')}</span>`:'';
  }
  const exam=e=>kind(e.assessment_type||'test');
  window.classroomActivities={kind,badge,legend,dots,exam};
})();
