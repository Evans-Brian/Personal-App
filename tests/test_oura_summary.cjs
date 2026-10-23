const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const html=fs.readFileSync('static/index.html','utf8');
const summary=html.split('<section class="card oura-panel"')[1].split('</section>')[0];
assert.doesNotMatch(summary,/Explore sleep patterns|Main sleep|oura-sleep-details|Sleep details/);
for(const id of ['oura-stats','oura-day','oura-status','oura-sync','oura-tools','oura-connect','oura-disconnect','oura-setup','oura-form','oura-client-id','oura-client-secret','oura-redirect','oura-connection-status']){
  assert.equal(html.split(`id="${id}"`).length-1,1,`${id} must remain available exactly once`);
}
assert.doesNotMatch(source,/oura-sleep-details/);
assert.match(html,/<section id="sleep-page"/,'The dedicated sleep dashboard must remain.');
class Element {
  constructor(){this.children=[];this.attributes={};this.value='';this.textContent='';}
  replaceChildren(...children){this.children=children;this.textContent='';}
  append(...children){this.children.push(...children);}
  setAttribute(name,value){this.attributes[name]=value;}
  getAttribute(name){return this.attributes[name];}
}
const elements=Object.fromEntries(['date','oura-stats','oura-day','oura-status','oura-connect','oura-disconnect','oura-sync','oura-redirect','oura-connection-status'].map(id=>[id,new Element()]));
elements.date.value='2026-10-23';
let response;
const context=vm.createContext({el:id=>elements[id],document:{createElement:()=>new Element()},request:async()=>response});
vm.runInContext(source.slice(source.indexOf('function renderOuraScores('),source.indexOf('const post=')),context);
const records=[{kind:'daily_sleep',data:{score:87}},{kind:'daily_readiness',data:{score:75}},{kind:'daily_activity',data:{score:100,steps:1234}},{kind:'sleep',data:{type:'long_sleep'}}];
context.renderOuraScores(records,'2026-10-23');
assert.deepEqual(elements['oura-stats'].children.map(card=>card.children.map(child=>child.textContent)),[['Sleep','87'],['Readiness','75'],['Activity','100']]);
assert.equal(elements['oura-day'].title,'2026-10-23');
assert.equal(elements['oura-stats'].children[0].attributes['aria-label'],'Sleep: 87 out of 100 for 2026-10-23');
for(const score of [0,null,undefined,NaN,Infinity,-1,101,'85']){
  context.renderOuraScores([{kind:'daily_sleep',data:{score}}],'2026-10-23');
  assert.equal(elements['oura-stats'].children[0].children[1].textContent,score===0?'0':'—');
  assert.equal(elements['oura-stats'].children[1].children[1].textContent,'—');
}
(async()=>{
  const connected={connected:true,configured:true,redirect_uri:'http://localhost:8765/api/oura/callback',last_sync:'2026-10-23T12:00:00-04:00',syncing:false,history_running:false,error:null};
  response=connected;await context.ouraStatus();
  assert.equal(elements['oura-status'].hidden,true,'Normal connected status stays out of the compact row.');
  assert.equal(elements['oura-sync'].disabled,false);assert.equal(elements['oura-sync'].textContent,'Sync');
  assert.match(elements['oura-sync'].title,/Last synced/);assert.match(elements['oura-connection-status'].textContent,/Checks hourly/);
  assert.equal(elements['oura-disconnect'].hidden,false);assert.equal(elements['oura-connect'].textContent,'Reconnect Oura');
  response={...connected,connected:false,last_sync:null};await context.ouraStatus();
  assert.equal(elements['oura-sync'].disabled,true);assert.equal(elements['oura-disconnect'].hidden,true);
  assert.equal(elements['oura-status'].hidden,false);assert.match(elements['oura-status'].textContent,/Open Settings/);
  response={...connected,error:'Connection expired'};await context.ouraStatus();
  assert.equal(elements['oura-status'].textContent,'Connection expired');assert.equal(elements['oura-status'].className,'error');
  response={...connected,syncing:true};await context.ouraStatus();
  assert.equal(elements['oura-sync'].disabled,true);assert.equal(elements['oura-status'].textContent,'Syncing…');
  response={...connected,history_running:true};await context.ouraStatus();
  assert.equal(elements['oura-sync'].disabled,true);assert.equal(elements['oura-status'].textContent,'Importing history…');
  response={records};await context.loadOuraDay();
  assert.equal(elements['oura-stats'].children[0].children[1].textContent,'87');
  let finish;
  context.request=()=>new Promise(resolve=>finish=resolve);
  const pending=context.loadOuraDay();elements.date.value='2026-10-24';finish({records:[]});await pending;
  assert.equal(elements['oura-stats'].children[0].children[1].textContent,'87','A stale request must not overwrite the newly selected day.');
  console.log('Compact Oura scores, missing values, connection states and date-race checks passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
