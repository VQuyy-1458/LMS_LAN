/* A scan identifies the session and immediately checks in; there is no session picker. */
(() => {
  'use strict';
  const esc=window.cssEscape;
  let refresh=async()=>{},controls=null,generation=0,busy=false,message='',success=false,consumed='';
  function stop(){generation++;controls?.stop();controls=null;const video=document.getElementById('attendance-camera');if(video){for(const track of video.srcObject?.getTracks()||[])track.stop();video.srcObject=null;video.hidden=true;}const button=document.getElementById('attendance-camera-stop');if(button)button.hidden=true;}
  function update(){const node=document.getElementById('qr-read-status');if(node){node.textContent=message;node.className=success?'student-scan-success':'muted';}document.querySelectorAll('[data-scan-start],#attendance-qr-photo,#attendance-qr-gallery').forEach(n=>n.disabled=busy);}
  async function check(text){
    if(busy)return;stop();busy=true;success=false;message='Đang xác nhận điểm danh…';update();
    try{
      const qr=window.classroomQr.parse(text);
      const result=await window.cssRequest('/api/learning/check-in',{method:'POST',body:new URLSearchParams({session_id:qr.session,code:qr.code})});
      success=true;message=`${result.already_checked_in?'Đã có điểm danh':'Điểm danh thành công'} · ${result.course_name} · ${result.title} · ${result.record.status==='late'?'Đến muộn':'Có mặt'}. Giảng viên đã nhận được kết quả.`;
      // Remove the token from the address bar after it has been consumed.
      const url=new URL(location.href);url.searchParams.delete('session');url.searchParams.delete('code');url.searchParams.set('course',result.course_id);history.replaceState(null,'',url.pathname+url.search);
      document.dispatchEvent(new CustomEvent('attendance-confirmed',{detail:{course_id:result.course_id}}));
      await refresh();window.cssToast(message,'success');
    }catch(e){message=e.message;window.cssToast(message,'error');}
    finally{busy=false;update();}
  }
  async function start(){
    if(busy)return;stop();message='';success=false;update();
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){document.getElementById('attendance-qr-photo').click();return;}
    const ticket=generation,video=document.getElementById('attendance-camera');video.hidden=false;
    document.getElementById('attendance-camera-stop').hidden=false;
    try{
      const reader=new ZXingBrowser.BrowserQRCodeReader();
      const handle=await reader.decodeFromConstraints({video:{facingMode:{ideal:'environment'}},audio:false},video,(result,_,scanner)=>{
        if(ticket!==generation){scanner.stop();return;}
        if(result){scanner.stop();void check(result.getText());}
      });
      if(ticket!==generation)handle.stop();else controls=handle;
    }catch(e){if(ticket!==generation)return;stop();message=e.name==='NotAllowedError'?'Chưa được cấp quyền camera. Hãy cho phép camera hoặc dùng nút Chụp QR.':'Không mở được camera. Bạn có thể chụp/chọn ảnh QR để điểm danh.';update();}
  }
  async function photo(file){
    if(!file||busy)return;stop();const ticket=generation;busy=true;success=false;message='Đang đọc ảnh QR…';update();
    try{const text=await window.classroomQr.decode(file);if(ticket!==generation)return;busy=false;await check(text);}
    catch(e){if(ticket===generation){message=e.message;success=false;}}
    finally{busy=false;update();}
  }
  function scanner(){return `<section class="panel student-scan-panel"><div class="student-section-head"><div><h2>Quét QR điểm danh</h2><p class="muted">Hướng máy ảnh vào mã giảng viên đang mở. Hệ thống tự nhận buổi học và ghi nhận có mặt.</p></div><span class="student-status blue"><i class="fa fa-qrcode"></i> Điểm danh nhanh</span></div><video id="attendance-camera" playsinline muted hidden aria-label="Camera quét QR"></video><div class="student-actions"><button type="button" class="btn btn-primary" data-scan-start><i class="fa fa-camera"></i> Mở máy ảnh quét QR</button><label class="btn btn-secondary" for="attendance-qr-photo">Chụp QR</label><label class="btn btn-ghost" for="attendance-qr-gallery">Quét ảnh QR</label><button type="button" class="btn btn-secondary" id="attendance-camera-stop" hidden>Tắt máy ảnh</button></div><input id="attendance-qr-photo" type="file" accept="image/*" capture="environment" hidden><input id="attendance-qr-gallery" type="file" accept="image/*" hidden><p id="qr-read-status" role="status" aria-live="polite" class="${success?'student-scan-success':'muted'}">${esc(message)}</p><p class="fine-print">Camera trực tiếp dùng HTTPS hoặc localhost. Trên điện thoại mở qua HTTP LAN, nút Mở máy ảnh sẽ dùng camera chụp QR và tự xác nhận sau khi chụp.</p></section>`;}
  document.addEventListener('click',e=>{if(e.target.closest('[data-scan-start]'))void start();if(e.target.closest('#attendance-camera-stop'))stop();});
  document.addEventListener('change',e=>{if(['attendance-qr-photo','attendance-qr-gallery'].includes(e.target.id)){const file=e.target.files[0];e.target.value='';void photo(file);}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('pagehide',stop);
  window.studentAttendance={scanner,stop,check,active:()=>busy||!!controls||!!document.getElementById('attendance-camera')?.srcObject,configure(next,onRefresh){refresh=onRefresh;update();},consumeLink(){if(location.pathname==='/student/attendance'&&new URLSearchParams(location.search).has('session')&&!busy&&consumed!==location.href){consumed=location.href;void check(location.href);}}};
})();
