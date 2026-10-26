const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const plans=require('../static/plans.js');
const source=fs.readFileSync('static/app.js','utf8');
const renderer=source.slice(source.indexOf('function renderCarryover(){'),source.indexOf('function changed(){'));
const serializer=source.slice(source.indexOf('function content()'),source.indexOf('function showEditor('));
const sourceDay='2026-10-30',day='2026-10-31',key=text=>sourceDay+':'+text;
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.events={};this.attributes={};this.value='';this.checked=false;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  setAttribute(name,value){this.attributes[name]=value;}
  addEventListener(name,handler){this.events[name]=handler;}
}
function descendants(element){return [element,...element.children.flatMap(descendants)];}
function editor({tasks=['Review task'],choices={},entries=true,busy=false,fields=[],confirm=true}={}){
  const panel=new Element('section'),controls={carryover:panel,entry:new Element('textarea')};
  const inputs=fields.map(({id,value})=>Object.assign(new Element('input'),{id,value}));
  const carryData={source:sourceDay,reviewed:true,items:[...tasks]};
  if(entries)carryData.entries=tasks.map(text=>({text,key:key(text),source:sourceDay}));
  let changes=0;const messages=[];
  const document={createElement:tag=>new Element(tag),querySelectorAll:selector=>{
    if(selector==='.optional-plan-row')return [];
    if(selector==='.plan-input')return inputs;
    const prefix=selector.match(/^\[id\^="(plan|optional)-"\]\.plan-input$/)?.[1];
    if(prefix)return inputs.filter(input=>input.id.startsWith(prefix+'-'));
    throw Error('Unexpected selector: '+selector);
  }};
  const context=vm.createContext({document,JournalPlans:plans,entry:{date:day},carryData,carryChoices:choices,busy,guided:true,period:'morning',
    parts:[{title:'How am I feeling this morning?'},{title:'Priority Tasks'},{title:'Secondary Tasks'},{title:'What might get in the way, and what could help?'}],
    el:id=>controls[id]||(controls[id]=new Element('input')),changed:()=>changes++,confirm:()=>confirm,status:(...args)=>messages.push(args),
    revealPlan:prefix=>{const input=Object.assign(new Element('input'),{id:prefix+'-'+inputs.length});inputs.push(input);return input;}});
  vm.runInContext(renderer+'\n'+serializer,context);context.renderCarryover();
  const rows=()=>panel.children.filter(node=>node.className==='carry-row');
  const row=text=>rows().find(node=>node.children.find(child=>child.tag==='p')?.textContent===text.replace(/^\[If time\] /,''));
  const button=(text,label)=>descendants(row(text)).find(node=>node.tag==='button'&&node.textContent===label);
  return {context,panel,inputs,carryData,rows,row,button,messages,changes:()=>changes,serialize:()=>context.content()};
}
// Saved/recovered choices clear the review only; the choices themselves remain intact.
for(const action of ['Completed','Deleted','Added to Priority Tasks','Added to Secondary Tasks','Added to good-day plans','Added to if-time','Skipped today','Skipped until 2026-11-07']){
  for(const entries of [true,false]){
    const choices={[key('Handled')]:action},before=JSON.stringify(choices);
    const state=editor({tasks:['Handled','Still pending'],choices,entries});
    assert.deepEqual(state.rows().map(row=>row.children[0].textContent),['Still pending'],action);
    assert.equal(JSON.stringify(choices),before);
    assert.equal(state.changes(),0,'Rendering must not create a draft.');
    assert.equal(plans.review(state.serialize()).choices[key('Handled')],action);
    const recovered=editor({tasks:['Handled','Still pending'],choices:plans.review(state.serialize()).choices,entries});
    assert.equal(recovered.rows().length,1,'Saved and recovered decisions remain cleared.');
  }
}
const empty=editor({choices:{[key('Review task')]:'Completed'}});
assert.equal(empty.panel.children.length,0,'Hide the entire review when no pending items remain.');
const authoritativeEmpty=editor();authoritativeEmpty.context.carryData.entries=[];authoritativeEmpty.context.renderCarryover();
assert.equal(authoritativeEmpty.panel.children.length,0,'An empty server entries list must not fall back to stale items.');

const completed=editor();const done=descendants(completed.row('Review task')).find(node=>node.type==='checkbox');
done.checked=true;done.events.change();
assert.equal(completed.rows().length,0);
assert.equal(completed.context.carryChoices[key('Review task')],'Completed');
assert.equal(completed.changes(),1);

for(const [action,prefix,label] of [['Add to Priority Tasks','plan','Priority Tasks'],['Add to Secondary Tasks','optional','Secondary Tasks']]){
  const text='[If time] Move task',state=editor({tasks:[text]});
  state.button(text,action).events.click();
  assert.equal(state.rows().length,0,action);
  assert.equal(state.context.carryChoices[key(text)],'Added to '+label);
  assert.equal(state.inputs.length,1);
  assert.equal(state.inputs[0].value,'Move task');
  assert.ok(state.inputs[0].id.startsWith(prefix+'-'));
  assert.equal(state.changes(),1);
}
// Already present in today's plans should resolve the old queue card without duplication.
for(const prefix of ['plan','optional']){
  const state=editor({fields:[{id:prefix+'-0',value:'Review task'}]});
  state.button('Review task','Add to Priority Tasks').events.click();
  assert.equal(state.rows().length,0);
  assert.equal(state.inputs.length,1);
  assert.equal(state.context.carryChoices[key('Review task')],'Added to '+(prefix==='plan'?'Priority Tasks':'Secondary Tasks'));
}
for(const [action,days,due] of [['Skip today',null,'2026-11-01'],['Skip for a week',null,'2026-11-07'],['Skip for n days','3','2026-11-03']]){
  const state=editor();
  if(days)descendants(state.row('Review task')).find(node=>node.type==='number').value=days;
  state.button('Review task',action).events.click();
  assert.equal(state.rows().length,0,action);
  assert.equal(state.context.carryChoices[key('Review task')],'Skipped until '+due);
  assert.equal(plans.review(state.serialize()).choices[key('Review task')],'Skipped until '+due);
  assert.equal(state.changes(),1);
}
for(const value of ['0','1.5','3651']){
  const state=editor();descendants(state.row('Review task')).find(node=>node.type==='number').value=value;
  state.button('Review task','Skip for n days').events.click();
  assert.equal(state.rows().length,1);
  assert.equal(state.changes(),0);
  assert.equal(state.messages.at(-1)[1],true);
}
for(const confirm of [true,false]){
  const state=editor({confirm});state.button('Review task','×').events.click();
  assert.equal(state.rows().length,confirm?0:1);
  assert.equal(state.changes(),confirm?1:0);
}
const blocked=editor({busy:true});blocked.button('Review task','Skip today').events.click();
assert.equal(blocked.rows().length,1);assert.equal(blocked.changes(),0);
assert.deepEqual(blocked.carryData.items,['Review task'],'Clearing the review must not mutate source tasks.');
console.log('Carry-over pending-only rendering, actions, draft persistence and empty-queue checks passed.');
