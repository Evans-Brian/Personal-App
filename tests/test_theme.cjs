const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/theme.js','utf8');
let now=new Date(2026,10,3,20,59,59),timer,delay;
const events={},root={dataset:{}},meta={content:'#829B87',setAttribute(key,value){this[key]=value;},getAttribute(key){return this[key];}};
class Clock extends Date {constructor(...args){super(...(args.length?args:[now.getTime()]));}static now(){return now.getTime();}}
const document={documentElement:root,hidden:false,querySelector:()=>meta,addEventListener:(name,fn)=>events[name]=fn};
const window={setTimeout:(fn,ms)=>{timer=fn;delay=ms;return 1;},clearTimeout(){},addEventListener:(name,fn)=>events[name]=fn};
vm.runInNewContext(source,{document,window,Date:Clock});
assert.equal(root.dataset.theme,'day');assert.equal(delay,1000);
now=new Date(2026,10,3,21);timer();
assert.equal(root.dataset.theme,'night');assert.equal(meta.content,'#171e1d');assert.equal(delay,10*60*60*1000);
now=new Date(2026,10,4,0,15);events.visibilitychange();assert.equal(root.dataset.theme,'night');
now=new Date(2026,10,4,6,59,59);events.focus();assert.equal(root.dataset.theme,'night');assert.equal(delay,1000);
now=new Date(2026,10,4,7);timer();assert.equal(root.dataset.theme,'day');assert.equal(meta.content,'#829B87');
now=new Date(2026,10,4,22);events.pageshow();assert.equal(root.dataset.theme,'night');
console.log('Automatic night theme boundaries, overnight behavior, wake/focus refresh, and browser bar color checks passed.');
