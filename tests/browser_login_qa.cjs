/* Exercise real browser login on an untrusted HTTP origin, as on a LAN phone. */
const {spawn}=require('node:child_process'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),profile=fs.mkdtempSync(path.join(os.tmpdir(),'classroom-login-'));
let app,browser,socket,id=1;const callbacks=new Map(),requests=[],responses=[];
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function waitFor(fn,ms=15000){const end=Date.now()+ms;while(Date.now()<end){try{if(await fn())return;}catch(_){}await delay(100);}throw new Error('Timed out');}
function ready(proc,stream,pattern){return new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(new Error('Readiness timeout')),20000);proc[stream].on('data',chunk=>{out+=chunk;const match=out.match(pattern);if(match){clearTimeout(timer);resolve(match[1]);}});proc.once('exit',code=>reject(new Error(`Process exited ${code}: ${out.slice(-1000)}`)));});}
function send(method,params={}){return new Promise((resolve,reject)=>{const key=id++;callbacks.set(key,{resolve,reject});socket.send(JSON.stringify({id:key,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value;}
async function navigate(url){await send('Page.navigate',{url});await waitFor(()=>evaluate("document.readyState==='complete'"));}
async function login(username='QA001'){await waitFor(()=>evaluate("!!document.querySelector('#username')"));await evaluate(`document.querySelector('#username').value=${JSON.stringify(username)};document.querySelector('#password').value='qa-password';document.querySelector('form[action="/login"]').requestSubmit();`);}
(async()=>{
  const {python,chrome}=require('./test_environment.cjs');
  app=spawn(python,['-u',path.join(__dirname,'serve_student_qa.py')],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  const fixture=JSON.parse(await ready(app,'stdout',/QA_READY ([^\r\n]+)/));
  browser=spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-proxy-server','--host-resolver-rules=MAP classroom.test 127.0.0.1','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:['ignore','ignore','pipe']});
  const ws=await ready(browser,'stderr',/DevTools listening on (ws:\/\/[^\r\n]+)/),port=new URL(ws).port;
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r,{once:true}));
  socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const c=callbacks.get(m.id);if(c){callbacks.delete(m.id);m.error?c.reject(new Error(JSON.stringify(m.error))):c.resolve(m.result);}}if(m.method==='Network.requestWillBeSent'&&m.params.request.method==='POST')requests.push({url:m.params.request.url,headers:m.params.request.headers});if(m.method==='Network.responseReceived')responses.push({url:m.params.response.url,status:m.params.response.status});});
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Emulation.setUserAgentOverride',{userAgent:'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36'});
  const base=`http://classroom.test:${fixture.port}`;
  await navigate(base+'/login');assert.equal(await evaluate('window.isSecureContext'),false);
  await login();
  if(process.argv.includes('--expect-blocked')){
    await waitFor(()=>evaluate("document.body.textContent.includes('Origin không hợp lệ')"));
    const post=requests.find(r=>r.url===base+'/login');
    console.log('REPRODUCED: HTTP LAN-style login blocked; Origin='+post?.headers.Origin+'; response='+responses.filter(r=>r.url===base+'/login').at(-1)?.status);
    return;
  }
  await waitFor(()=>evaluate("!!document.querySelector('.student-hero')"));
  const cookie=await evaluate("fetch('/api/student/workspace').then(r=>r.status)");assert.equal(cookie,200);
  console.log('PASS: mobile HTTP non-localhost form login, redirect and authenticated workspace cookie');
  await send('Network.clearBrowserCookies');
  await navigate(base+'/login');await login('qa-admin');
  await waitFor(()=>evaluate("!!document.querySelector('.bridge-teaching')"));
  console.log('PASS: lecturer/admin login and workspace on the same mobile HTTP origin');
  await navigate(base+'/admin?section=accounts');
  await waitFor(()=>evaluate("!!document.querySelector('[data-reset-account=\"QAEMPTY\"]') && !!window.adminDesign"));
  await evaluate("document.querySelector('[data-reset-account=\"QAEMPTY\"]').click()");
  await waitFor(()=>evaluate("!!document.querySelector('#reset-student-password-form')"));
  await evaluate("{const f=document.querySelector('#reset-student-password-form');f.elements.new_password.value='qa-reset-password';f.elements.confirm_password.value='does-not-match';f.requestSubmit()}");
  await waitFor(()=>evaluate("document.querySelector('#reset-student-password-form .ref-form-error')?.textContent.includes('khớp')"));
  await evaluate("{const f=document.querySelector('#reset-student-password-form');f.elements.confirm_password.value='qa-reset-password';f.requestSubmit()}");
  await waitFor(()=>evaluate("!document.querySelector('#reset-student-password-form')"));
  assert.equal(await evaluate("document.querySelector('#toast').textContent.includes('Đã đặt lại mật khẩu')"),true);
  console.log('PASS: password reset dialog, confirmation validation and successful save');
  await navigate(base+'/admin?section=notifications');
  await waitFor(()=>evaluate("document.querySelectorAll('#notification-students input').length===2"));
  await evaluate(`(()=>{document.querySelector('[name=notification_scope][value=selected]').click();document.querySelector('#notification-students input[value=QAEMPTY]').click();const search=document.querySelector('#notification-search');search.value='QA001';search.dispatchEvent(new Event('input'));})()`);
  assert.equal(await evaluate("document.querySelector('#selected-students-count').textContent.startsWith('1 ')"),true);
  await evaluate("document.querySelector('[name=notification_scope][value=all]').click();document.querySelector('#notification-message').value='QA broadcast after selected';document.querySelector('#notification-form').requestSubmit()");
  await waitFor(()=>evaluate("document.querySelector('#notification-result').textContent.includes('thành công')"));
  assert.equal(await evaluate("document.querySelector('#notification-message').value"),'');
  assert.equal(await evaluate("document.querySelector('#notification-picker').classList.contains('hidden')"),true);
  await evaluate(`(()=>{document.querySelector('[name=notification_scope][value=selected]').click();document.querySelector('#notification-search').value='';document.querySelector('#notification-search').dispatchEvent(new Event('input'));document.querySelector('#notification-students input[value=QAEMPTY]').click();document.querySelector('#notification-search').value='QA001';document.querySelector('#notification-search').dispatchEvent(new Event('input'));document.querySelector('#notification-message').value='QA targeted after search';document.querySelector('#notification-form').requestSubmit();})()`);
  await waitFor(()=>evaluate("document.querySelector('#notification-result').textContent.includes('tới 1 sinh viên') && !document.querySelector('#notification-form').dataset.sending"));
  for(const [username,password,receivesTarget] of [['QA001','qa-password',false],['QAEMPTY','qa-reset-password',true]]){
    await evaluate(`fetch('/login',{method:'POST',body:new URLSearchParams({username:${JSON.stringify(username)},password:${JSON.stringify(password)}})}).then(r=>r.status)`);
    const messages=await evaluate("fetch('/api/student/notifications').then(r=>r.json()).then(d=>d.notifications.map(n=>n.description))");
    assert.equal(messages.filter(m=>m==='QA broadcast after selected').length,1);
    assert.equal(messages.includes('QA targeted after search'),receivesTarget);
  }
  console.log('PASS: notification success feedback, reset, recipient search persistence, broadcast switch and actual delivery/privacy');
  await send('Network.clearBrowserCookies');
  await navigate(base+`/student/attendance?session=${fixture.attendance}&code=${fixture.code}`);
  await waitFor(()=>evaluate("!!document.querySelector('#username')"));
  assert.equal(await evaluate("document.querySelector('[name=next]').value.includes('/student/attendance?session=')"),true);
  await login();
  await waitFor(()=>evaluate("document.querySelector('#qr-read-status')?.textContent.includes('Điểm danh thành công')"));
  assert.equal(await evaluate("new URLSearchParams(location.search).has('code')"),false);
  console.log('PASS: mobile LAN-style QR link survives login and automatically checks in');
})().catch(async e=>{console.error(e);try{console.error(await evaluate("JSON.stringify({url:location.href,text:document.body.innerText.slice(0,800)})"));}catch(_){}process.exitCode=1;}).finally(async()=>{socket?.close();browser?.kill();app?.kill();await delay(400);if(path.dirname(path.resolve(profile))===path.resolve(os.tmpdir())&&path.basename(profile).startsWith('classroom-login-'))fs.rmSync(profile,{recursive:true,force:true});});
