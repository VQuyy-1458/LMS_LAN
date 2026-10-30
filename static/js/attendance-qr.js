/* Offline QR creation and photograph decoding using the reference project's ZXing. */
(() => {
  'use strict';
  window.classroomQr={
    draw(container,text){container.replaceChildren(new ZXingBrowser.BrowserQRCodeSvgWriter().write(text,280,280));},
    async decode(file){
      if(!file||!file.type.startsWith('image/'))throw new Error('Hãy chọn ảnh chứa mã QR.');
      if(file.size>20*1048576)throw new Error('Ảnh vượt giới hạn 20 MiB.');
      const src=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Không đọc được ảnh.'));reader.readAsDataURL(file);});
      const image=new Image();image.src=src;await image.decode();
      const reader=new ZXingBrowser.BrowserQRCodeReader();
      for(const max of [1200,800,1800]){
        const ratio=Math.min(1,max/Math.max(image.naturalWidth,image.naturalHeight)),w=Math.max(1,Math.round(image.naturalWidth*ratio)),h=Math.max(1,Math.round(image.naturalHeight*ratio));
        for(const angle of [0,90,180,270]){
          const canvas=document.createElement('canvas');canvas.width=angle%180?h:w;canvas.height=angle%180?w:h;
          const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.translate(canvas.width/2,canvas.height/2);ctx.rotate(angle*Math.PI/180);ctx.drawImage(image,-w/2,-h/2,w,h);
          try{return reader.decodeFromCanvas(canvas).getText();}catch(_){}
          await new Promise(resolve=>setTimeout(resolve,0));
        }
      }
      throw new Error('Không đọc được mã QR. Hãy chụp rõ, đủ bốn góc và tránh phản sáng.');
    },
    parse(value){
      const url=new URL(value,location.origin);
      const session=url.searchParams.get('session'),code=url.searchParams.get('code');
      // Extract locally. The same server may be opened by localhost, LAN IP or HTTPS.
      if(!['http:','https:'].includes(url.protocol)||url.pathname!=='/student/attendance'||url.searchParams.getAll('session').length!==1||url.searchParams.getAll('code').length!==1||!/^[a-z0-9_-]{8,80}$/i.test(session||'')||!/^[a-f0-9]{8}$/i.test(code||''))throw new Error('QR không phải mã điểm danh hợp lệ.');
      return {session:/^[a-f0-9]{20}$/i.test(session)?session.toLowerCase():session,code:code.toUpperCase()};
    }
  };
})();
