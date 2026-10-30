const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {python,root}=require('./test_environment.cjs');
function run(command,args){const result=spawnSync(command,args,{cwd:root,stdio:'inherit',windowsHide:true,env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});if(result.error)throw result.error;if(result.status!==0)process.exit(result.status||1);}
for(const file of fs.readdirSync(path.join(root,'static/js')).filter(name=>name.endsWith('.js')&&!name.startsWith('._')))run(process.execPath,['--check',path.join('static/js',file)]);
for(const file of ['test_list_controls.cjs','test_exam_csv.cjs','test_attendance_qr.cjs'])run(process.execPath,[path.join('tests',file)]);
if(process.argv.includes('--browser')){
  run(process.execPath,['tests/browser_student_qa.cjs']);run(process.execPath,['tests/browser_login_qa.cjs']);run(process.execPath,['tests/browser_student_qa.cjs','--code-roster']);run(process.execPath,['tests/browser_student_qa.cjs','--code-entry']);run(process.execPath,['tests/browser_student_qa.cjs','--enrollment']);run(process.execPath,['tests/browser_student_qa.cjs','--drafts']);run(process.execPath,['tests/browser_student_qa.cjs','--timing']);
}else run(python,['-m','unittest','discover','-s','tests','-v']);
