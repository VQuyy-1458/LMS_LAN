/* CSV grammar and test-data preservation, without a browser or dependencies. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/exam-test-csv.js'),'utf8'),context);
const parse=text=>JSON.parse(JSON.stringify(context.window.classroomTestCsv.parse(text)));
assert.deepEqual(parse('\uFEFFinput,output,sample\r\n"  a,""b""  ","line 1\r\nline 2",true\r\n,,0\r\n'),[
  {input:'  a,"b"  ',output:'line 1\r\nline 2',sample:true},{input:'',output:'',sample:false}
]);
assert.deepEqual(parse('OUTPUT;Input;Sample\n"a;b";"\nhello";1'),[{input:'\nhello',output:'a;b',sample:true}]);
assert.deepEqual(parse('input,output\n"\\n","\\t"\n\n'),[{input:'\\n',output:'\\t',sample:false}]);
assert.deepEqual(parse('input,output,sample\n1,2,\n3,4,FALSE'),[{input:'1',output:'2',sample:false},{input:'3',output:'4',sample:false}]);
assert.equal(parse('input,output\n'+Array(100).fill('1,2').join('\n')).length,100);
assert.equal(parse(fs.readFileSync(path.join(__dirname,'../static/samples/test-cases.csv'),'utf8')).length,3);
for(const [source,message] of [
  ['',/trống/],['input,output\n',/chưa có/],['input,answer\n1,2',/tiêu đề/],
  ['input,input,output\na,b,c',/trùng/],['input,output,extra\n1,2,3',/tiêu đề/],
  ['input,output\n1,2,3',/dòng 2.*2 cột/],['input,output,sample\n1,2,maybe',/sample/],
  ['input,output\n"abc,2',/chưa đóng/],['input,output\n"abc"x,2',/ký tự thừa/],
  ['input,output\nab"c,2',/bao trọn/],['input,output\n'+Array(101).fill('1,2').join('\n'),/100 test/],
  ['input,output\n"'+('a'.repeat(100001))+'",2',/100.000/]
])assert.throws(()=>parse(source),message);
console.log('PASS: CSV BOM, comma/semicolon, escaped quotes, multiline, whitespace, samples, size/count limits and invalid files');
