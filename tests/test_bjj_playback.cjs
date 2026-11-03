const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/bjj.js','utf8');
const playback=fs.existsSync('static/bjj-player.js')?require('../static/bjj-player.js'):null;
class Video {
  constructor(){this.events={};this.srcWrites=[];this.readyState=0;this.duration=600;this.currentTime=0;this.currentSrc='';this.playCalls=0;this.ownerDocument={};}
  set src(value){this._src=value;this.srcWrites.push(value);}
  get src(){return this._src||'';}
  addEventListener(name,fn){(this.events[name]??=[]).push(fn);}
  removeEventListener(name,fn){this.events[name]=(this.events[name]||[]).filter(item=>item!==fn);}
  emit(name){for(const fn of [...this.events[name]||[]])fn();}
  play(){this.playCalls++;return Promise.resolve();}
  metadata(){this.currentSrc=this.src;this.readyState=1;this.emit('loadedmetadata');}
}
function setup(saved=0){
  const video=new Video(),controls={'bjj-video':video};let requests=0;
  const player=playback?.create(video,{status:()=>{}});
  const $=id=>controls[id]??=( {textContent:'',hidden:true,replaceChildren(){},append(){},scrollIntoView(){}} );
  const context=vm.createContext({$,video,player,current:null,segments:[],openToken:0,transcriptReady:false,
    time:value=>String(value),message:()=>{},matchMedia:()=>({matches:true}),Option:class {},
    localStorage:{getItem:()=>String(saved),setItem(){}},
    request:async()=>{requests++;return {segments:[],chapters:[]};}});
  const block=source.slice(source.indexOf('  function seek('),source.indexOf('  function renderLibrary('));
  vm.runInContext(block,context);
  return {video,context,requests:()=>requests};
}
const course={title:'Sample course',instructor:'Sample instructor'},item={id:'sample-v01',volume:1,present:true};
(async()=>{
  const state=setup();
  await state.context.openVolume(course,item,120);state.video.metadata();
  assert.equal(state.video.currentTime,120);
  await state.context.openVolume(course,item,240);
  assert.equal(state.video.srcWrites.length,1,'A second timestamp in the loaded volume must seek without reloading its stream.');
  assert.equal(state.video.currentTime,240);
  assert.equal(state.requests(),1,'Reusing a volume must not download its full transcript again.');
  const zero=setup(150);await zero.context.openVolume(course,item,0);zero.video.metadata();
  assert.equal(zero.video.currentTime,0,'An explicit timestamp of zero must override the saved resume position.');
  const resume=setup(150);await resume.context.openVolume(course,item);resume.video.metadata();
  assert.equal(resume.video.currentTime,150,'Opening from the library still resumes.');
  const changed=setup();await changed.context.openVolume(course,item,400);changed.video.metadata();
  await changed.context.openVolume(course,{...item,id:'sample-v02',volume:2},20);
  assert.equal(changed.video.currentTime,400,'Do not seek using metadata left over from the previous video.');
  changed.video.metadata();assert.equal(changed.video.currentTime,20);
  assert.match(changed.video.src,/#t=20$/,'A new stream should request its starting timestamp immediately.');
  assert.ok(playback,'The playback controller must support both browser and Node tests.');
  const early=new Video(),controller=playback.create(early,{status:()=>{}});
  controller.open('/one.mp4',30);controller.open('/one.mp4',90);early.metadata();
  assert.equal(early.srcWrites.length,1);assert.equal(early.currentTime,90,'Latest selection wins while metadata loads.');
  controller.seek(0);assert.equal(early.currentTime,0);
  controller.seek(999);assert.ok(early.currentTime<600,'Clamp an out-of-range timestamp.');
  let calls=[];const safari={ownerDocument:{},webkitEnterFullscreen(){calls.push('native');}};
  await playback.fullscreen(safari);assert.deepEqual(calls,['native']);
  const standard={ownerDocument:{},requestFullscreen(){calls.push('standard');return Promise.resolve();}};
  await playback.fullscreen(standard);assert.equal(calls.at(-1),'standard');
  standard.ownerDocument={fullscreenElement:standard,exitFullscreen(){calls.push('exit');return Promise.resolve();}};
  await playback.fullscreen(standard);assert.equal(calls.at(-1),'exit');
  safari.webkitDisplayingFullscreen=true;safari.webkitExitFullscreen=()=>calls.push('native exit');
  await playback.fullscreen(safari);assert.equal(calls.at(-1),'native exit');
  await assert.rejects(async()=>playback.fullscreen({ownerDocument:{}}),/not supported/);
  console.log('BJJ timestamp reuse, resume, metadata races, initial seek, and mobile fullscreen checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
