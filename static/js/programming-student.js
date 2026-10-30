/* Full-page programming problems, local drafts and live submission results. */
(() => {
  'use strict';
  const esc=window.cssEscape;
  const languages={c:'C',cpp:'C++',java:'Java',python:'Python'};
  const filenames={c:'main.c',cpp:'main.cpp',java:'Main.java',python:'main.py'};
  const templates={
    c:'#include <stdio.h>\n\nint main(void) {\n    // Đọc dữ liệu từ stdin, in kết quả ra stdout.\n    \n    return 0;\n}\n',
    cpp:'#include <iostream>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    // Viết lời giải của bạn tại đây.\n    \n    return 0;\n}\n',
    java:'import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        Scanner scanner = new Scanner(System.in);\n        // Đọc dữ liệu và viết lời giải tại đây.\n        \n    }\n}\n',
    python:'import sys\n\n\ndef main():\n    # Đọc dữ liệu từ stdin, in kết quả ra stdout.\n    pass\n\n\nif __name__ == "__main__":\n    main()\n'
  };
  const memory=new Map();
  let renderResult=()=>'', context=null, polling=false, lastPoll=0;
  const key=(e,index,language)=>`lan-lms:code:${encodeURIComponent(context.student.student_id)}:${e.id}:${index}:${language}`;
  function read(key){try{return JSON.parse(localStorage.getItem(key))||memory.get(key);}catch(_){return memory.get(key);}}
  function write(key,value){memory.set(key,value);try{localStorage.setItem(key,JSON.stringify(value));return true;}catch(_){return false;}}
  function draft(e,index,language){return read(key(e,index,language))||{source:templates[language],filename:filenames[language]};}
  function problemUrl(e,index){const url=new URL(location.href);url.searchParams.set('exam',e.id);url.searchParams.delete('problem');if(index!==undefined)url.searchParams.set('problem',String(index));return url.pathname+url.search;}
  const codeLabel=index=>index<26?String.fromCharCode(65+index):String(index+1);
  function best(rows,index){return Math.max(0,...rows.filter(r=>r.problem_index===index&&Number.isFinite(r.effective_score)).map(r=>r.effective_score));}
  function deadline(e){return `<span class="code-deadline">Còn lại <strong data-deadline-countdown data-expires-at="${esc(e.attempt?.ends_at||e.ends_at||'')}">--:--</strong></span>`;}
  function render(data,course=''){
    context=data;
    return (data.programming?.exams||[]).filter(e=>!course||e.course_id===course).map(e=>{
      const rows=(data.programming.submissions||[]).filter(r=>r.exam_id===e.id);
      const requested=new URLSearchParams(location.search).get('problem');
      if(requested!==null&&e.attempt){
        const problem=e.problems.find(p=>String(p.index)===requested);
        return problem?workspace(e,problem,rows):`<section class="panel"><h2>Không tìm thấy bài toán</h2><a class="btn btn-secondary" href="${esc(problemUrl(e))}">Quay lại danh sách bài</a></section>`;
      }
      const problemRows=window.listUi.view('programming:problems:'+e.id,e.problems.map(p=>({...p,best_score:best(rows,p.index),verdict:(()=>{const last=rows.filter(r=>r.problem_index===p.index).at(-1);return last?(last.state==='queued'||last.state==='running'?last.state:last.result?.verdict):'none';})()})),'problems');
      const max=e.problems.reduce((n,p)=>n+p.points,0),score=e.problems.reduce((n,p)=>n+best(rows,p.index),0);
      return `<section class="panel code-exam" data-code-problem-list="${esc(e.id)}"><div class="panel-heading"><div><p class="eyebrow">THI LẬP TRÌNH</p><h2>${esc(e.title)}</h2><p class="muted">${e.duration_minutes} phút · ${e.languages.map(l=>languages[l]).join(' / ')}</p></div>${e.attempt?deadline(e):''}</div><p class="student-description">${esc(e.description||'Chọn một bài toán để đọc đề và viết lời giải.')}</p>${e.can_start?`<p class="muted">Kỳ thi tính giờ chung từ lúc giảng viên mở. Sau khi bắt đầu, bạn sẽ thấy danh sách các bài toán.</p><button type="button" class="btn btn-primary" data-code-start="${esc(e.id)}" data-deadline-start data-expires-at="${esc(e.ends_at||'')}">Bắt đầu thi lập trình</button>`:''}${e.attempt?`<div class="code-list-heading"><h3>Danh sách bài toán</h3><span><strong>${score}/${max}</strong> điểm tốt nhất</span></div>${window.listUi.controls('programming:problems:'+e.id,'problems')}<div class="table-wrap"><table class="code-problem-table"><thead><tr><th>Bài</th><th>Tên bài toán</th><th>Điểm tốt nhất</th><th>Lần nộp</th><th>Kết quả gần nhất</th><th></th></tr></thead><tbody>${problemRows.map(p=>{
        const attempts=rows.filter(r=>r.problem_index===p.index),last=attempts[attempts.length-1];
        return `<tr><td><span class="code-letter">${codeLabel(p.index)}</span></td><td><a class="student-list-title" data-code-problem="${p.index}" href="${esc(problemUrl(e,p.index))}">${esc(p.title)}</a><small>${p.time_limit_ms} ms · ${p.memory_limit_mb} MB</small></td><td><strong>${best(rows,p.index)}/${p.points}</strong></td><td>${attempts.length}</td><td>${last?window.programmingUi.status(last):'<span class="muted">Chưa nộp</span>'}</td><td><a class="btn btn-secondary btn-small" href="${esc(problemUrl(e,p.index))}">${e.can_submit?'Làm bài':'Xem bài'}</a></td></tr>`;
      }).join('')}</tbody></table></div><p class="muted">Chọn tên bài để mở trang làm bài. Mỗi bài có lịch sử nộp và kết quả riêng.</p>`:!e.can_start?'<p class="alert alert-info">Kỳ thi hiện chưa nhận lượt làm bài mới.</p>':''}</section>`;
    }).join('');
  }
  function workspace(e,p,rows){
    const selected=read(key(e,p.index,'selected'));
    const language=e.languages.includes(selected)?selected:e.languages[0];
    const saved=draft(e,p.index,language);
    return `<div class="code-workspace" data-code-workspace data-exam-id="${esc(e.id)}" data-problem-index="${p.index}"><nav class="code-breadcrumb" aria-label="Điều hướng bài thi"><a href="${esc(problemUrl(e))}"><i class="fa fa-arrow-left"></i> Danh sách bài</a><span>/</span><span>Bài ${codeLabel(p.index)}</span></nav><header class="code-workspace-header"><div><p class="eyebrow">${esc(e.title)}</p><h1>${codeLabel(p.index)}. ${esc(p.title)}</h1></div>${deadline(e)}</header><div class="code-workspace-grid"><section class="panel code-statement"><h2>Đề bài</h2><div class="code-limits"><span>${p.points} điểm</span><span>${p.time_limit_ms} ms / test</span><span>${p.memory_limit_mb} MB</span></div><p class="student-description">${esc(p.statement||'Giảng viên chưa bổ sung đề bài.')}</p><h3>Ví dụ</h3>${p.samples.map((t,i)=>`<div class="code-sample"><h4>Ví dụ ${i+1}</h4><strong>Input</strong><pre class="code-output">\n${esc(t.input)}</pre><strong>Output</strong><pre class="code-output">\n${esc(t.output)}</pre></div>`).join('')||'<p class="muted">Bài này không có test mẫu công khai.</p>'}</section><section class="panel code-solution"><form data-code-submit data-allowed="${e.can_submit}" data-expires-at="${esc(e.attempt.ends_at)}"><input type="hidden" name="exam_id" value="${esc(e.id)}"><input type="hidden" name="problem_index" value="${p.index}"><div class="code-solution-toolbar"><label for="code-language">Ngôn ngữ biên dịch<select id="code-language" name="language">${e.languages.map(l=>`<option value="${l}" ${l===language?'selected':''}>${languages[l]}</option>`).join('')}</select></label><button class="btn btn-secondary btn-small" type="button" data-code-upload><i class="fa fa-upload"></i> Tải file lên</button><input class="code-file-input" type="file" name="file" aria-label="Tải file mã nguồn" accept="${e.languages.map(l=>'.'+filenames[l].split('.').pop()).join(',')}"></div><div class="code-editor-caption"><strong data-code-filename>${esc(saved.filename)}</strong><span data-code-draft-status>Nháp riêng cho bài và ngôn ngữ này</span></div><label class="sr-only" for="code-source">Mã nguồn lời giải</label><div class="code-editor-shell"><pre class="code-line-numbers" aria-hidden="true">1</pre><textarea id="code-source" class="code-editor" name="source" data-code-editor spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off" aria-describedby="code-editor-help">${esc(saved.source)}</textarea></div><p class="muted" id="code-editor-help">Đọc stdin, ghi stdout. Tab: thụt dòng · Ctrl+Enter: submit · Tối đa 100 KB. Java dùng public class Main.</p><div class="code-submit-bar"><p data-code-submit-message role="status"></p><button type="submit" class="btn btn-primary" ${e.can_submit?'':'disabled'}><i class="fa fa-paper-plane"></i> Submit bài</button></div><p class="ref-form-error" data-code-error role="alert"></p><p class="alert alert-info" data-code-closed ${e.can_submit?'hidden':''}>Đã đóng nhận bài. Bạn vẫn có thể xem đề, bản nháp và lịch sử.</p></form></section></div><section class="panel code-problem-history"><div class="panel-heading"><div><h2>Lịch sử submit · Bài ${codeLabel(p.index)}</h2><p class="muted">Tự cập nhật trạng thái biên dịch, chấm test và kết quả.</p></div><span data-code-history-connection role="status"></span></div><div data-code-problem-history>${history(rows.filter(r=>r.problem_index===p.index),'programming:history:'+e.id+':'+p.index)}</div></section></div>`;
  }
  function history(rows,id){const visible=window.listUi.view(id,rows,'submissions');return window.listUi.controls(id,'submissions')+(visible.map(r=>renderResult(r)).join('')||'<p class="muted">Chưa có lần submit nào cho bài này.</p>');}
  function current(){return document.querySelector('[data-code-workspace]');}
  function save(form){
    if(!context)return;
    const e={id:form.elements.exam_id.value},index=Number(form.elements.problem_index.value),language=form.elements.language.value;
    const source=form.elements.source.value;
    const filename=form.querySelector('[data-code-filename]').textContent;
    const persisted=write(key(e,index,language),{source,filename});
    write(key(e,index,'selected'),language);
    form.querySelector('[data-code-draft-status]').textContent=persisted?'Đã lưu nháp trên máy này':'Nháp được giữ trong phiên này';
    updateLines(form);
  }
  function updateLines(form){const editor=form.elements.source,gutter=form.querySelector('.code-line-numbers');gutter.textContent=Array.from({length:editor.value.split('\n').length},(_,i)=>i+1).join('\n');gutter.scrollTop=editor.scrollTop;}
  function mount(data){context=data;const form=current()?.querySelector('form');if(!form)return;form.dataset.language=form.elements.language.value;updateLines(form);lastPoll=0;sync(data);}
  function updateDeadline(form,allowed){
    if(allowed!==undefined)form.dataset.allowed=String(allowed);
    const closed=form.dataset.allowed!=='true'||Date.parse(form.dataset.expiresAt)<=window.submissionDeadlines.now();
    form.querySelector('[type=submit]').disabled=closed||!!form.dataset.sending;
    form.querySelector('[data-code-closed]').hidden=!closed;
  }
  function sync(data){
    const node=current();if(!node)return false;
    context=data;
    const exam=data.programming?.exams.find(e=>e.id===node.dataset.examId);
    if(!exam)return false;
    updateHistory(node,(data.programming.submissions||[]).filter(r=>r.exam_id===exam.id&&r.problem_index===Number(node.dataset.problemIndex)));
    updateDeadline(node.querySelector('form'),exam.can_submit);
    return true;
  }
  window.listUi.on('programming',id=>{const node=current();if(node&&id.startsWith('programming:history:')){const box=node.querySelector('[data-code-problem-history]'),rows=JSON.parse(box.dataset.signature||'[]');delete box.dataset.signature;updateHistory(node,rows);}else document.dispatchEvent(new CustomEvent('programming-list-change'));});
  function updateHistory(node,rows){
    const box=node.querySelector('[data-code-problem-history]');
    const signature=JSON.stringify(rows);if(box.dataset.signature===signature)return;
    const opened=new Set([...box.querySelectorAll('[data-code-result][open]')].map(n=>n.dataset.codeResult));
    box.innerHTML=history(rows,'programming:history:'+node.dataset.examId+':'+node.dataset.problemIndex);box.dataset.signature=signature;
    box.querySelectorAll('[data-code-result]').forEach(n=>{if(opened.has(n.dataset.codeResult))n.open=true;});
    node.dataset.pending=String(rows.some(r=>['queued','running'].includes(r.state)));
  }
  async function refresh(force=false){
    const node=current();if(!node||polling||document.hidden)return;
    if(!force&&Date.now()-lastPoll<(node.dataset.pending==='true'?1200:5000))return;
    polling=true;lastPoll=Date.now();
    const indicator=node.querySelector('[data-code-history-connection]');
    try{
      const data=await window.cssRequest(`/api/student/programming/submissions?exam=${encodeURIComponent(node.dataset.examId)}&problem=${node.dataset.problemIndex}`,{cache:'no-store'});
      if(!node.isConnected)return;
      window.submissionDeadlines.sync(data.server_time);updateHistory(node,data.submissions);updateDeadline(node.querySelector('form'),data.can_submit);indicator.textContent='';
    }catch(error){if(node.isConnected)indicator.textContent='Chưa cập nhật được kết quả. Đang thử lại…';}
    finally{polling=false;}
  }
  function changeLanguage(form,language){
    const prior=form.dataset.language;
    // The select already contains the new value; persist the previous buffer.
    form.elements.language.value=prior;save(form);form.elements.language.value=language;
    form.dataset.language=language;
    const saved=draft({id:form.elements.exam_id.value},Number(form.elements.problem_index.value),language);
    form.elements.source.value=saved.source;form.querySelector('[data-code-filename]').textContent=saved.filename;save(form);
  }
  async function upload(form,file){
    if(!file)return;
    if(!file.size||file.size>100000)throw new Error('File mã nguồn phải từ 1 đến 100.000 byte.');
    const extension=file.name.split('.').pop().toLowerCase();
    const language=[...form.elements.language.options].map(o=>o.value).find(l=>filenames[l].split('.').pop()===extension);
    if(!language)throw new Error('Định dạng file không thuộc ngôn ngữ được phép của kỳ thi.');
    let source;try{source=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());}catch(_){throw new Error('File mã nguồn phải dùng UTF-8.');}
    if(!form.isConnected)return;
    if(form.elements.language.value!==language)changeLanguage(form,language);
    form.elements.source.value=source;form.querySelector('[data-code-filename]').textContent=file.name;form.elements.file.value='';save(form);
    form.querySelector('[data-code-submit-message]').textContent='Đã đưa file vào trình soạn thảo. Bấm Submit bài để nộp.';
  }
  document.addEventListener('click',event=>{const button=event.target.closest('[data-code-upload]');if(button)button.form.elements.file.click();});
  document.addEventListener('input',event=>{if(event.target.matches('[data-code-editor]'))save(event.target.form);});
  document.addEventListener('scroll',event=>{if(event.target.matches?.('[data-code-editor]'))updateLines(event.target.form);},true);
  document.addEventListener('change',async event=>{
    const form=event.target.closest('[data-code-submit]');if(!form)return;
    if(event.target.name==='language')changeLanguage(form,event.target.value);
    if(event.target.name==='file'){
      const error=form.querySelector('[data-code-error]');error.textContent='';
      form.dataset.uploading='true';
      try{await upload(form,event.target.files[0]);}catch(e){error.textContent=e.message;form.elements.file.value='';}
      finally{delete form.dataset.uploading;}
    }
  });
  document.addEventListener('keydown',event=>{
    if(!event.target.matches?.('[data-code-editor]'))return;
    const editor=event.target;
    if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();editor.form.requestSubmit();return;}
    if(event.key==='Tab'){event.preventDefault();editor.setRangeText('    ',editor.selectionStart,editor.selectionEnd,'end');save(editor.form);}
    if(event.key==='Enter'&&!event.ctrlKey&&!event.metaKey){
      event.preventDefault();const before=editor.value.slice(0,editor.selectionStart).split('\n').pop();
      const indent=before.match(/^\s*/)[0]+(/[{:][ \t]*$/.test(before)?'    ':'');
      editor.setRangeText('\n'+indent,editor.selectionStart,editor.selectionEnd,'end');save(editor.form);
    }
  });
  document.addEventListener('submit',async event=>{
    const form=event.target;if(!form.matches('[data-code-submit]'))return;event.preventDefault();
    if(form.dataset.sending||form.dataset.uploading)return;
    const error=form.querySelector('[data-code-error]');error.textContent='';
    if(form.dataset.allowed!=='true'||Date.parse(form.dataset.expiresAt)<=window.submissionDeadlines.now()){updateDeadline(form);return;}
    form.dataset.sending='true';updateDeadline(form);
    try{
      if(form.elements.file.files.length)await upload(form,form.elements.file.files[0]);
      const source=form.elements.source.value;if(!source.trim())throw new Error('Hãy nhập mã nguồn trước khi submit.');
      if(new TextEncoder().encode(source).length>100000)throw new Error('Mã nguồn tối đa 100.000 byte.');
      save(form);
      const body=new FormData();body.set('exam_id',form.elements.exam_id.value);body.set('problem_index',form.elements.problem_index.value);body.set('language',form.elements.language.value);
      const signature=JSON.stringify([form.elements.exam_id.value,form.elements.problem_index.value,form.elements.language.value,source]);
      if(form.dataset.requestSignature!==signature){form.dataset.requestSignature=signature;form.dataset.requestId=crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random()}`;}
      body.set('request_id',form.dataset.requestId);
      body.set('file',new File([source],form.querySelector('[data-code-filename]').textContent,{type:'text/plain'}));
      const data=await window.cssRequest('/api/student/programming/submit',{method:'POST',body});
      delete form.dataset.requestId;delete form.dataset.requestSignature;
      const node=form.closest('[data-code-workspace]');
      if(node?.isConnected){const box=node.querySelector('[data-code-problem-history]');const rows=JSON.parse(box.dataset.signature||'[]');rows.push(data.submission);updateHistory(node,rows);form.querySelector('[data-code-submit-message]').textContent='Đã nhận bài. Đang chờ biên dịch và chấm…';await refresh(true);}
    }catch(e){if(form.isConnected)error.textContent=e.message;}
    finally{delete form.dataset.sending;if(form.isConnected)updateDeadline(form);}
  });
  setInterval(()=>{const form=current()?.querySelector('form');if(form)updateDeadline(form);refresh();},1500);
  window.programmingStudent={render,mount,sync,busy:()=>!!current()?.querySelector('form[data-sending],form[data-uploading]'),configure(options){renderResult=options.result;}};
})();
