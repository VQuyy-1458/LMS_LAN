(function () {
  const $ = (id) => document.getElementById(id);
  const courseQuery = () => {const id=new URLSearchParams(location.search).get('course');return id?'?course='+encodeURIComponent(id):'';};
  const monitorQuery = () => {const p=new URLSearchParams(location.search),q=new URLSearchParams();for(const k of ['course','exam'])if(p.get(k))q.set(k,p.get(k));return q.size?'?'+q:'';};
  const shell = document.querySelector(".admin-shell");
  const escape = (value) => window.cssEscape(String(value ?? ""));
  const show = (id, message, error) => {
    const node = $(id);
    if (!node) return;
    node.textContent = message;
    node.classList.remove("hidden");
    node.style.background = error ? "#fff0f0" : "";
  };
  const toastError = (error) => window.cssToast(error.message || "Không thể xử lý yêu cầu.", "error");

  document.querySelector(".sidebar-toggle")?.addEventListener("click", () => shell?.classList.toggle("sidebar-open"));
  document.querySelectorAll(".sidebar-nav a").forEach((link) => link.addEventListener("click", () => shell?.classList.remove("sidebar-open")));

  let monitorRows = [];
  let monitorServerAt = Date.now();
  let monitorExam = null;
  async function loadMonitor() {
    const data = await window.cssRequest("/api/admin/monitor"+monitorQuery());
    monitorExam = data.exam;
    if($('monitor-submission-heading'))$('monitor-submission-heading').textContent=monitorExam?.type==='programming'?'Bài đã AC / Tổng bài':'Nộp bài';
    window.submissionDeadlines.sync(data.occurred_at);
    if($('monitor-exam-context')){
      const e=monitorExam;
      $('monitor-exam-context').innerHTML=e?`<h2>${escape(e.title)}</h2><p class="muted">${e.type==='programming'?'Thi lập trình':'Thi nộp file'} · ${e.waiting?'Chờ đến giờ bắt đầu':e.live?'Đang diễn ra':'Chưa mở hoặc đã kết thúc'}${e.started_at?' · Bắt đầu '+escape(new Date(e.started_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})):''}${e.ends_at?' · Kết thúc '+escape(new Date(e.ends_at).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'})):''}</p>${e.waiting?window.submissionDeadlines.waiting(e.started_at):''}<a class="btn btn-secondary" href="/admin?section=exam&exam=${encodeURIComponent(e.id)}${e.course_id?'&course='+encodeURIComponent(e.course_id):''}">Cấu hình / Điều chỉnh thời gian thi</a>`:'<p class="muted">Tổng quan sinh viên. Chọn kỳ thi phía trên để giám sát riêng danh sách dự thi và bài nộp của kỳ thi đó.</p>';
    }
    monitorRows = data.students || [];
    monitorServerAt = Date.parse(data.occurred_at) || Date.now();
    if ($("stat-total")) $("stat-total").textContent = monitorRows.length;
    if ($("stat-online")) $("stat-online").textContent = data.online_count ?? 0;
    if ($("stat-submitted")) $("stat-submitted").textContent = monitorRows.filter((row) => row.submission_count > 0).length;
    if ($("stat-abnormal")) $("stat-abnormal").textContent = data.abnormal_count ?? 0;
    if ($("monitor-stat-total")) $("monitor-stat-total").textContent=monitorRows.length;
    if ($("monitor-stat-online")) $("monitor-stat-online").textContent=data.online_count??0;
    if ($("monitor-stat-submitted")) $("monitor-stat-submitted").textContent=monitorRows.filter(row=>row.exam_status==='submitted').length;
    if ($("monitor-stat-attention")) $("monitor-stat-attention").textContent=data.abnormal_count??0;
    if ($("monitor-updated")) $("monitor-updated").textContent = "Đồng bộ server " + new Date(monitorServerAt).toLocaleTimeString();
    renderMonitor();
  }
  function monitorActions(row){
    const query=new URLSearchParams({section:'submissions',student:row.student_id}),course=new URLSearchParams(location.search).get('course');
    if(course)query.set('course',course);
    if(monitorExam){if(monitorExam.type==='programming')query.set('exam',monitorExam.id);else query.set('activity',monitorExam.activity_id);}
    return `<a class="btn btn-secondary btn-small" data-monitor-archive href="/admin?${escape(query.toString())}">Xem bài nộp</a> ${!monitorExam||row.can_force?`<button class="btn btn-secondary btn-small" data-force="${escape(row.student_id)}">Ép nộp</button>`:''} ${!monitorExam||row.can_adjust?`<button class="btn btn-secondary btn-small" data-adjust="${escape(row.student_id)}">Điều chỉnh giờ</button>`:''}`;
  }
  function renderParticipants() {
    const box = $("participant-list");
    if (!box) return;
    if(participantSelection===null)participantSelection=new Set(students.filter(r=>r.exam_participant).map(r=>r.student_id));
    box.querySelectorAll("input[name=exam_participant]").forEach(input=>{if(input.checked)participantSelection.add(input.value);else participantSelection.delete(input.value);});
    const query = ($("participant-search")?.value || "").toLowerCase();
    const rows = window.listUi.enhance(box.id==="participant-list"?"admin:participants":"admin:recipients",box,students.filter((row) => [row.student_id, row.full_name].join(" ").toLowerCase().includes(query)),"people",box.id==="participant-list"?renderParticipants:renderNotificationStudents,{search:false,statusFilter:false});
    box.innerHTML = rows.map((row) => `<label class="student-option"><input type="checkbox" name="exam_participant" value="${escape(row.student_id)}" ${participantSelection.has(row.student_id) ? "checked" : ""}><span><strong>${escape(row.student_id)}</strong><small>${escape(row.full_name || "")}</small></span></label>`).join("") || '<span class="muted">Không tìm thấy sinh viên.</span>';
    if ($("participant-count")) $("participant-count").textContent = `${participantSelection?.size||0} sinh viên`;
  }
  function renderMonitor() {
    const body = $("monitor-body");
    if (!body) return;
    const labels = { tab_hidden: "Tab bị ẩn", window_unfocused: "Mất focus", multiple_tabs: "Nhiều tab" };
    const rows = window.listUi.enhance("admin:monitor",body,monitorRows,"monitor",renderMonitor,{searchInputId:'monitor-search',searchText:row=>[row.student_id,row.full_name,row.ip].join(' ')});
    body.innerHTML = rows.map((row) => {
      const alerts = (row.alerts || []).map((alert) => `<span class="status-pill status-red">${labels[alert] || escape(alert)}</span>`).join("");
      const remaining = row.remaining_seconds == null ? "—" : `${Math.floor(row.remaining_seconds / 60)}:${String(row.remaining_seconds % 60).padStart(2, "0")}`;
      return `<tr class="${alerts ? "row-warning" : ""}"><td><div class="cell-main">${escape(row.student_id)}</div><div class="cell-sub">${escape(row.full_name)}</div></td><td class="code-text">${escape(row.ip || "—")}</td><td>${row.logged_in ? '<span class="status-pill status-green">Đang đăng nhập</span>' : '<span class="status-pill status-gray">Ngoại tuyến / chưa đăng nhập</span>'}<div class="cell-sub">${escape(row.last_seen || "")}</div></td><td>${escape(row.exam_file || "—")}</td><td>${remaining}</td><td>${monitorExam?.type==='programming'?`<strong data-monitor-accepted="${escape(row.student_id)}">${row.accepted_problems}/${row.total_problems} bài</strong>`:`${row.submission_count || 0} lần`}${row.latest_verdict?`<div class="cell-sub">${escape(row.latest_verdict)}</div>`:''}</td><td><div class="user-agent">${escape(row.user_agent || "—")}</div></td><td>${alerts || '<span class="muted">Bình thường</span>'}</td><td>${monitorActions(row)}</td></tr>`;
    }).join("") || '<tr><td colspan="9" class="empty-cell">Không có dữ liệu.</td></tr>';
  }

  let students = [];
  let accountClockOffset = 0, accountLoadVersion = 0;
  let participantSelection = null;
  async function loadAccounts() {
    const version=++accountLoadVersion;
    const data = await window.cssRequest("/api/admin/accounts");
    if(version!==accountLoadVersion)return;
    accountClockOffset=data.server_time?Date.parse(data.server_time)-Date.now():0;
    students = data.students || [];
    renderStudents();
    renderNotificationStudents();
    renderParticipants();
  }
  function loginRemaining(row){return Math.max(0,Math.ceil((Number(row.login_locked_until||0)*1000-Date.now()-accountClockOffset)/1000));}
  function loginCountdown(row){const seconds=loginRemaining(row);return `${Math.floor(seconds/60)} phút ${seconds%60} giây`;}
  function loginBadge(row){
    if(typeof row.login_locked!=='boolean')return '<span class="muted">Chưa cập nhật</span>';
    if(row.login_locked&&loginRemaining(row)>0)return `<span class="status-pill status-red">Khóa đăng nhập tạm</span><div class="cell-sub" data-login-countdown="${escape(row.student_id)}">Còn ${loginCountdown(row)}</div>`;
    return `<span class="status-pill status-green">Không khóa tạm</span>${row.active?'':'<div class="cell-sub">Tài khoản đang bị khóa</div>'}`;
  }
  function confirmAccountAction(studentId,unlock){
    const row=students.find(s=>s.student_id===studentId);if(!row)return;
    const title=unlock?'Gỡ khóa đăng nhập tạm':row.active?'Khóa tài khoản sinh viên':'Mở tài khoản sinh viên';
    const description=unlock?'Cho phép sinh viên thử đăng nhập lại ngay. Tài khoản đang bị khóa vẫn cần được mở bằng nút Mở tài khoản.':row.active?'Sinh viên sẽ bị đăng xuất và không thể truy cập cho đến khi tài khoản được mở lại.':'Cho phép tài khoản hoạt động trở lại. Nếu còn khóa đăng nhập tạm, thời gian khóa được hiển thị riêng trong danh sách.';
    const dialog=window.adminDesign.modal(title,`<p>Sinh viên: <strong>${escape(studentId)}</strong> · ${escape(row.full_name||'')}</p><p>${description}</p><form class="stack-form"><div class="ref-actions"><button type="button" class="btn btn-secondary" data-design-close>Hủy</button><button type="submit" class="btn btn-primary">Xác nhận</button></div></form>`);
    dialog.querySelector('form').addEventListener('submit',async event=>{
      event.preventDefault();const form=event.currentTarget;if(form.dataset.sending)return;form.dataset.sending='true';
      const button=form.querySelector('[type=submit]');button.disabled=true;form.querySelector('.ref-form-error')?.remove();
      const fields=new FormData();if(!unlock)fields.set('active',String(!row.active));
      try{
        await window.cssRequest(`/api/admin/accounts/${encodeURIComponent(studentId)}/${unlock?'unlock-login':'toggle'}`,{method:'POST',body:fields});
        dialog.close();window.cssToast(unlock?'Đã gỡ khóa đăng nhập tạm.':'Đã cập nhật trạng thái tài khoản.','success');await loadAccounts();
      }catch(error){window.adminDesign.formError(form,error.message);}finally{delete form.dataset.sending;button.disabled=false;}
    });
  }
  function renderStudents() {
    const body = $("accounts-body");
    if (!body) return;
    const rows = window.listUi.enhance("admin:accounts",body,students,"people",renderStudents,{searchInputId:'account-search'});
    body.innerHTML = rows.map((row) => `<tr><td class="cell-main">${escape(row.student_id)}</td><td>${escape(row.full_name)}</td><td>${row.active ? '<span class="status-pill status-green">Đang mở</span>' : '<span class="status-pill status-red">Đã khóa tài khoản</span>'}</td><td>${loginBadge(row)}</td><td class="code-text">${escape(row.last_ip || "—")}</td><td><div class="actions-inline"><button class="btn btn-secondary btn-small" data-toggle-account="${escape(row.student_id)}">${row.active ? "Khóa tài khoản" : "Mở tài khoản"}</button><button class="btn btn-secondary btn-small" data-reset-account="${escape(row.student_id)}">Đặt lại mật khẩu</button><button class="btn btn-secondary btn-small" data-unlock-account="${escape(row.student_id)}" ${loginRemaining(row)>0?'':'disabled'}>Gỡ khóa tạm</button></div></td></tr>`).join("") || '<tr><td colspan="6" class="empty-cell">Không có tài khoản phù hợp bộ lọc.</td></tr>';
  }
  const notificationRecipients = new Set();
  function renderNotificationStudents() {
    const box = $("notification-students");
    if (!box) return;
    const query = ($("notification-search")?.value || "").toLowerCase();
    const rows = window.listUi.enhance(box.id==="participant-list"?"admin:participants":"admin:recipients",box,students.filter((row) => [row.student_id, row.full_name].join(" ").toLowerCase().includes(query)),"people",box.id==="participant-list"?renderParticipants:renderNotificationStudents,{search:false,statusFilter:false});
    box.innerHTML = rows.map((row) => `<label class="student-option"><input type="checkbox" name="notification_student" value="${escape(row.student_id)}" ${notificationRecipients.has(row.student_id) ? "checked" : ""}><span><strong>${escape(row.student_id)}</strong><small>${escape(row.full_name)}</small></span></label>`).join("") || '<span class="muted">Không tìm thấy sinh viên.</span>';
    updateSelectedCount();
  }
  function updateSelectedCount() {
    if ($("selected-students-count")) $("selected-students-count").textContent = `${notificationRecipients.size} sinh viên được chọn`;
  }

  let submissions = [];
  async function loadSubmissions() {
    const data = await window.cssRequest("/api/admin/submissions"+courseQuery());
    submissions = data.submissions || [];
    const body = $("submissions-body");
    if (!body) return;
    const query = ($("submission-search")?.value || "").toLowerCase();
    const rows = window.listUi.enhance("admin:submissions",body,submissions.filter((row) => [row.student_id, row.full_name, row.filename, row.ip].join(" ").toLowerCase().includes(query)),"submissions",loadSubmissions,{search:false});
    if ($("submission-count")) $("submission-count").textContent = `${rows.length} bản ghi`;
    body.innerHTML = rows.map((row) => `<tr><td><div class="cell-main">${escape(row.student_id)}</div><div class="cell-sub">${escape(row.full_name)}</div></td><td>${row.attempt}</td><td>${row.payload_retained === false ? "Payload đã xóa" : `<a href="/admin/submissions/${encodeURIComponent(row.student_id)}/${encodeURIComponent(row.filename)}">${escape(row.filename)}</a>`}</td><td>${escape(row.submitted_at || "")}</td><td>${row.payload_retained === false ? "Đã xóa payload" : "Đang lưu"}</td></tr>`).join("") || '<tr><td colspan="5" class="empty-cell">Chưa có bài nộp.</td></tr>';
  }

  async function loadAdmins() {
    const data = await window.cssRequest("/api/admin/admins");
    const body = $("admins-body");
    if (!body) return;
    body.innerHTML = window.listUi.enhance("admin:admins",body,data.admins||[],"people",loadAdmins).map((row) => `<tr><td>${escape(row.username)}</td><td>${escape(row.created_at || "")}</td><td>${escape(row.created_by || "—")}</td><td>${row.active ? "Hoạt động" : "Đã khóa"}</td></tr>`).join("") || '<tr><td colspan="4" class="empty-cell">Chưa có Admin.</td></tr>';
  }
  async function loadServerInfo() {
    const box = $("server-addresses");
    if (!box) return;
    let data;
    try { data = await window.cssRequest("/api/admin/server-info", { cache: "no-store" }); }
    catch (error) { box.textContent = "Không cập nhật được địa chỉ LAN. Hãy kiểm tra kết nối mạng."; throw error; }
    const addresses = (data.addresses || []).slice(0, 1).map((ip) => `${data.scheme}://${ip}:${data.port}`);
    box.innerHTML = addresses.map((address) => `<div class="address-item"><strong>${escape(address)}</strong><button class="btn btn-secondary" data-copy="${escape(address)}">Copy</button></div>`).join("") || '<span class="muted">Không xác định được địa chỉ LAN.</span>';
  }

  $("refresh-monitor")?.addEventListener("click", () => loadMonitor().catch(toastError));
  $("participant-search")?.addEventListener("input", renderParticipants);
  $("participant-list")?.addEventListener("change", renderParticipants);
  $("select-all-participants")?.addEventListener("click", () => { document.querySelectorAll("#participant-list .student-option").forEach((row) => { row.querySelector("input").checked = true; }); renderParticipants(); if ($("participant-count")) $("participant-count").textContent = `${participantSelection?.size||0} sinh viên`; });
  $("clear-all-participants")?.addEventListener("click", () => { participantSelection?.clear(); document.querySelectorAll("#participant-list input").forEach((input) => { input.checked = false; }); if ($("participant-count")) $("participant-count").textContent = "0 sinh viên"; });
  $("save-participants")?.addEventListener("click", async () => {
    renderParticipants();
    const selected = [...(participantSelection||[])];
    const pasted = $("participant-paste")?.value.trim() || "";
    const ids = [...new Set([...selected, ...pasted.replace(/,/g, "\n").split(/\r?\n/).map((item) => item.trim()).filter(Boolean)])];
    if (!ids.length) return window.cssToast("Hãy chọn hoặc nhập ít nhất một MSSV.", "error");
    const form = new FormData(); form.set("student_ids", ids.join("\n"));
    try { const data = await window.cssRequest("/api/admin/exam-participants", { method: "POST", body: form }); $("participant-paste").value = ""; show("participant-result", `Đã lưu ${data.count} sinh viên dự thi. Tạo mới ${data.created.length} tài khoản.`); await loadAccounts(); } catch (error) { show("participant-result", error.message, true); toastError(error); }
  });
  $("accounts-body")?.addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-toggle-account]");
    const reset = event.target.closest("[data-reset-account]");
    const unlock = event.target.closest("[data-unlock-account]");
    try {
      if (toggle) {
        confirmAccountAction(toggle.dataset.toggleAccount,false);return;
      } else if (unlock) {
        confirmAccountAction(unlock.dataset.unlockAccount,true);return;
      } else if (reset) {
        const studentId = reset.dataset.resetAccount;
        const dialog = window.adminDesign.modal("Đặt lại mật khẩu sinh viên", `<p>Mã sinh viên: <strong>${escape(studentId)}</strong></p><form class="stack-form" id="reset-student-password-form"><label>Mật khẩu mới<input name="new_password" type="password" autocomplete="new-password" required minlength="8" maxlength="200"></label><label>Xác nhận mật khẩu mới<input name="confirm_password" type="password" autocomplete="new-password" required minlength="8" maxlength="200"></label><p class="muted">Từ 8 đến 200 ký tự. Sau khi lưu, sinh viên có thể đăng nhập lại bằng mật khẩu mới.</p><div class="ref-actions"><button class="btn btn-secondary" type="button" data-design-close>Hủy</button><button class="btn btn-primary" type="submit">Lưu mật khẩu</button></div></form>`);
        dialog.querySelector("form").addEventListener("submit", async (submitEvent) => {
          submitEvent.preventDefault();
          const form = submitEvent.currentTarget;
          const fields = new FormData(form);
          const button = form.querySelector('[type="submit"]');
          form.querySelector(".ref-form-error")?.remove();
          if (fields.get("new_password") !== fields.get("confirm_password")) return window.adminDesign.formError(form, "Mật khẩu xác nhận không khớp.");
          button.disabled = true;
          try {
            await window.cssRequest(`/api/admin/accounts/${encodeURIComponent(studentId)}/reset-password`, { method: "POST", body: fields });
            dialog.close();
            window.cssToast("Đã đặt lại mật khẩu và gỡ giới hạn đăng nhập.", "success");
            await loadAccounts();
          } catch (error) { window.adminDesign.formError(form, error.message); }
          finally { button.disabled = false; }
        });
        return;
      }
      if (toggle || reset || unlock) await loadAccounts();
    } catch (error) { toastError(error); }
  });
  $("submission-search")?.addEventListener("input", () => loadSubmissions().catch(toastError));
  $("refresh-server-info")?.addEventListener("click", () => loadServerInfo().catch(toastError));
  $("distribution-mode")?.addEventListener("change", (event) => {
    $("parity-fields")?.classList.toggle("hidden", event.target.value !== "parity");
    $("custom-fields")?.classList.toggle("hidden", event.target.value !== "custom");
    if (event.target.value === "custom") renderRemainderRules();
  });
  $("select-all-exams")?.addEventListener("click", () => document.querySelectorAll('input[name="exam-choice"]').forEach((input) => { input.checked = true; }));
  $("clear-all-exams")?.addEventListener("click", () => document.querySelectorAll('input[name="exam-choice"]').forEach((input) => { input.checked = false; }));
  function selectedExamNames() {
    return [...document.querySelectorAll('input[name="exam-choice"]:checked')].map((input) => input.value);
  }
  function renderRemainderRules() {
    const box = $("remainder-rules");
    if (!box) return;
    const exams = selectedExamNames();
    const count = exams.length;
    if ($("custom-modulus")) $("custom-modulus").value = String(count);
    if ($("custom-modulus-label")) $("custom-modulus-label").textContent = String(count);
    if (count < 2) {
      box.innerHTML = '<p class="muted">Hãy chọn ít nhất 2 đề ở mục phía trên để tạo quy tắc theo số dư.</p>';
      updateRemainderMap();
      return;
    }
    box.innerHTML = Array.from({ length: count }, (_, remainder) => `<label class="remainder-row"><span>Chữ số cuối chia ${count} dư <strong>${remainder}</strong></span><select class="remainder-exam" data-remainder="${remainder}">${exams.map((exam) => `<option value="${escape(exam)}">${escape(exam)}</option>`).join("") || '<option value="">Chưa chọn đề</option>'}</select></label>`).join("");
    updateRemainderMap();
  }
  function updateRemainderMap() {
    const map = {};
    const modulus = Number($("custom-modulus")?.value || selectedExamNames().length);
    document.querySelectorAll(".remainder-exam").forEach((select) => {
      const exam = select.value;
      if (exam && modulus > 0) for (let digit = Number(select.dataset.remainder); digit < 10; digit += modulus) map[String(digit)] = exam;
    });
    if ($("last-digit-map")) $("last-digit-map").value = JSON.stringify(map);
  }
  $("remainder-rules")?.addEventListener("change", updateRemainderMap);
  document.querySelectorAll('input[name="exam-choice"]').forEach((input) => input.addEventListener("change", () => { if ($("distribution-mode")?.value === "custom") renderRemainderRules(); }));
  document.querySelectorAll('input[name="notification_scope"]').forEach((radio) => radio.addEventListener("change", () => $("notification-picker")?.classList.toggle("hidden", radio.value !== "selected" || !radio.checked)));
  $("notification-search")?.addEventListener("input", renderNotificationStudents);
  $("notification-students")?.addEventListener("change", (event) => { const input=event.target; if(input.name!=="notification_student")return; if(input.checked)notificationRecipients.add(input.value);else notificationRecipients.delete(input.value);updateSelectedCount(); });
  $("select-visible-students")?.addEventListener("click", () => { document.querySelectorAll('#notification-students input[name="notification_student"]').forEach((input) => { input.checked = true; notificationRecipients.add(input.value); }); updateSelectedCount(); });
  $("clear-selected-students")?.addEventListener("click", () => { notificationRecipients.clear(); renderNotificationStudents(); });

  $("import-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = await window.cssRequest("/api/admin/accounts/import", { method: "POST", body: new FormData(form) });
      show("import-result", `Đã tạo ${data.created_count} tài khoản.` + (data.errors?.length ? ` Có ${data.errors.length} dòng lỗi.` : ""));
      if (!data.errors?.length) form.reset();
      await Promise.all([loadAccounts(), loadMonitor()]);
    } catch (error) { show("import-result", error.message, true); toastError(error); }
  });
  $("notification-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const node = event.currentTarget;
    if (node.dataset.sending) return;
    const selected = [...notificationRecipients];
    const scope = node.querySelector('input[name="notification_scope"]:checked')?.value;
    if (scope === "selected" && !selected.length) return window.cssToast("Hãy chọn ít nhất một sinh viên.", "error");
    const form = new FormData(node); form.delete("notification_scope"); form.set("student_ids", scope === "selected" ? selected.join(",") : "");
    const button = node.querySelector('[type="submit"]');
    node.dataset.sending = "true"; button.disabled = true;
    try {
      const result = await window.cssRequest("/api/admin/notifications", { method: "POST", body: form });
      node.reset(); notificationRecipients.clear(); renderNotificationStudents(); $("notification-picker").classList.add("hidden");window.adminDrafts?.saved(node);
      show("notification-result", `Đã gửi thông báo thành công tới ${result.recipient_count} sinh viên.`);
    } catch (error) { show("notification-result", error.message, true); toastError(error); }
    finally { delete node.dataset.sending; button.disabled = false; }
  });
  $("create-admin-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try { const data = await window.cssRequest("/api/admin/admins", { method: "POST", body: new FormData(form) }); form.reset(); show("admin-create-result", `Đã tạo Admin ${data.username}.`); await loadAdmins(); } catch (error) { show("admin-create-result", error.message, true); toastError(error); }
  });
  $("monitor-body")?.addEventListener("click", async (event) => {
    const force = event.target.closest("[data-force]"); const adjust = event.target.closest("[data-adjust]");
    try {
      if (force && window.confirm(`Ép ${force.dataset.force} nộp bài ngay?`)) await window.cssRequest(`/api/admin/students/${encodeURIComponent(force.dataset.force)}/force-submit`+monitorQuery(), { method: "POST" });
      if (adjust) { const minutes = window.prompt("Nhập số phút cộng/trừ:", "-5"); if (minutes !== null) { const form = new FormData(); form.set("minutes", minutes); await window.cssRequest(`/api/admin/students/${encodeURIComponent(adjust.dataset.adjust)}/adjust-time`+monitorQuery(), { method: "POST", body: form }); } }
      if (force || adjust) { await loadMonitor(); window.cssToast("Đã cập nhật.", "success"); }
    } catch (error) { toastError(error); }
  });
  $("distribution-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    form.set("exam_files", [...document.querySelectorAll('input[name="exam-choice"]:checked')].map((input) => input.value).join(","));
    if (!form.get("exam_files")) return window.cssToast("Hãy chọn ít nhất một đề.", "error");
    if (form.get("mode") === "custom") { updateRemainderMap(); form.set("last_digit_map", $("last-digit-map").value); form.set("custom_modulus", $("custom-modulus").value); }
    try { const data = await window.cssRequest("/api/admin/distribute", { method: "POST", body: form }); show("distribution-result", `Đã phát đề cho ${data.assigned_count} tài khoản.`); if ($("start-exam-admin")) $("start-exam-admin").disabled = false; } catch (error) { show("distribution-result", error.message, true); toastError(error); }
  });
  $("settings-form")?.addEventListener("submit", async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); form.set("overwrite_previous", $("overwrite").value); form.set("exam_password_enabled", $("password-enabled").checked ? "true" : "false");
    try { await window.cssRequest("/api/admin/settings", { method: "POST", body: form }); window.adminDrafts?.saved(event.target);show("settings-result", "Đã lưu cấu hình kỳ thi."); } catch (error) { show("settings-result", error.message, true); toastError(error); }
  });
  $("start-exam-admin")?.addEventListener("click", async event => {const button=event.currentTarget;button.disabled=true;try {await window.examPreflight.open(new URLSearchParams(location.search).get('exam')||'current');}catch(error){toastError(error);}finally{button.disabled=false;}});
  $("end-exam")?.addEventListener("click", async () => { try { await window.cssRequest("/api/admin/end-exam", { method: "POST" }); location.reload(); } catch (error) { toastError(error); } });
  document.body.addEventListener("click", (event) => { const button = event.target.closest("[data-copy]"); if (button) navigator.clipboard?.writeText(button.dataset.copy); });

  const pageLoads = [];
  if ($("monitor-body") || $("stat-total")) pageLoads.push(loadMonitor());
  if ($("accounts-body") || $("notification-students") || $("participant-list")) pageLoads.push(loadAccounts());
  if ($("submissions-body")) pageLoads.push(loadSubmissions());
  if ($("admins-body")) pageLoads.push(loadAdmins());
  if ($("server-addresses")) pageLoads.push(loadServerInfo());
  if ($("distribution-mode")?.value === "custom") renderRemainderRules();
  Promise.all(pageLoads).catch(toastError);
  window.setInterval(() => { if ($("monitor-body")) loadMonitor().catch(() => {}); }, 5000);
  window.setInterval(() => { if ($("server-addresses")) loadServerInfo().catch(() => {}); }, 5000);
  window.setInterval(()=>{
    const body=$('accounts-body');if(!body||!body.getClientRects().length||document.hidden)return;
    let expired=false;
    for(const row of students){if(row.login_locked&&loginRemaining(row)===0){row.login_locked=false;row.login_locked_until=null;expired=true;}}
    if(expired)renderStudents();
    else for(const node of body.querySelectorAll('[data-login-countdown]')){const row=students.find(r=>r.student_id===node.dataset.loginCountdown);if(row)node.textContent='Còn '+loginCountdown(row);}
  },1000);
  window.setInterval(()=>{if(!document.hidden&&$('accounts-body')?.getClientRects().length)loadAccounts().catch(()=>{});},10000);
  window.notificationDraft={capture:()=>[...notificationRecipients],restore(ids){notificationRecipients.clear();for(const id of ids)if(typeof id==='string')notificationRecipients.add(id);renderNotificationStudents();$('notification-picker')?.classList.toggle('hidden',document.querySelector('[name="notification_scope"]:checked')?.value!=='selected');}};
})();
