const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const python=process.env.CSS_TEST_PYTHON||[
  path.join(root,'.venv-windows','Scripts','python.exe'),path.join(root,'.venv','Scripts','python.exe'),path.join(root,'.venv','bin','python')
].find(file=>fs.existsSync(file))||'python3';
const chrome=process.env.CSS_TEST_CHROME||[
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  '/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
].find(file=>fs.existsSync(file))||'google-chrome';
module.exports={python,chrome,root};
