/* Read CSV without trimming test data or interpreting escape sequences. */
(() => {
  'use strict';
  function parse(source){
    source=source.replace(/^\uFEFF/,'');
    let headerEnd=0,quoted=false,commas=0,semicolons=0;
    for(;headerEnd<source.length;headerEnd++){
      const ch=source[headerEnd];
      if(ch==='"'){if(quoted&&source[headerEnd+1]==='"')headerEnd++;else quoted=!quoted;}
      else if(!quoted){if(ch==='\r'||ch==='\n')break;if(ch===',')commas++;if(ch===';')semicolons++;}
    }
    const delimiter=semicolons>commas?';':',';
    const rows=[];let row=[],cell='',inside=false,closed=false,touched=false,line=1,start=1;
    const fail=message=>{throw new Error(`CSV dòng ${line}: ${message}`);};
    function endRow(){
      if(touched||row.length||cell!=='')rows.push({values:[...row,cell],line:start});
      row=[];cell='';closed=false;touched=false;
    }
    for(let i=0;i<source.length;i++){
      const ch=source[i];
      if(inside){
        if(ch==='"'){if(source[i+1]==='"'){cell+='"';i++;}else{inside=false;closed=true;}}
        else{cell+=ch;if(ch==='\n'||ch==='\r'&&source[i+1]!=='\n')line++;}
        continue;
      }
      if(ch===delimiter){row.push(cell);cell='';closed=false;touched=true;}
      else if(ch==='\r'||ch==='\n'){
        endRow();if(ch==='\r'&&source[i+1]==='\n')i++;
        line++;start=line;
      }
      else if(ch==='"'){
        if(cell!==''||closed)fail('dấu nháy kép phải bao trọn ô dữ liệu.');
        inside=true;touched=true;
      }
      else{
        if(closed)fail('có ký tự thừa sau dấu nháy kép đóng.');
        cell+=ch;touched=true;
      }
    }
    if(inside)fail('ô dữ liệu chưa đóng dấu nháy kép.');
    endRow();
    if(!rows.length)throw new Error('File CSV trống.');
    const headers=rows.shift().values.map(h=>h.trim().toLowerCase());
    if(!headers.includes('input')||!headers.includes('output')||headers.some(h=>!['input','output','sample'].includes(h))||new Set(headers).size!==headers.length)throw new Error('Dòng tiêu đề cần có cột input,output và tùy chọn sample; không được trùng cột.');
    if(!rows.length)throw new Error('File CSV chưa có test case.');
    if(rows.length>100)throw new Error('Mỗi bài toán có tối đa 100 test case.');
    return rows.map(({values,line:rowLine})=>{
      if(values.length!==headers.length)throw new Error(`CSV dòng ${rowLine}: cần ${headers.length} cột, nhận được ${values.length}.`);
      const test=Object.fromEntries(headers.map((h,i)=>[h,values[i]]));
      const sample=(test.sample||'').trim().toLowerCase();
      if(!['','true','false','1','0'].includes(sample))throw new Error(`CSV dòng ${rowLine}: sample phải là true/false hoặc 1/0.`);
      if(test.input.length>100000||test.output.length>100000)throw new Error(`CSV dòng ${rowLine}: input/output vượt 100.000 ký tự.`);
      return {input:test.input,output:test.output,sample:sample==='true'||sample==='1'};
    });
  }
  window.classroomTestCsv={parse};
})();
