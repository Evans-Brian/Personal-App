const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const plans=require('../static/plans.js');
const source=fs.readFileSync('static/app.js','utf8');
const picker=source.slice(source.indexOf('function caffeinePicker('),source.indexOf('function content()'));
const content=source.slice(source.indexOf('function content()'),source.indexOf('function showEditor('));
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.events={};this.value='';}
  append(...children){this.children.push(...children);}
  setAttribute(name,value){this.attributes[name]=value;}
  addEventListener(name,handler){this.events[name]=handler;}
}
function editor(habits={}){
  const raw='### Reflection\n\nAn answer.\n'+plans.serializeHabits(habits),parent=new Element('section');
  let changes=0;
  const context=vm.createContext({JournalPlans:plans,document:{createElement:tag=>new Element(tag)},changed:()=>changes++});
  vm.runInContext(picker,context);context.caffeinePicker(parent,plans.habits(raw).value);
  const nodes=[];function collect(node){nodes.push(node);node.children.forEach(collect);}collect(parent);
  const input=nodes.find(node=>node.id==='last-caffeine-intake'),status=nodes.find(node=>node.id==='caffeine-intake-status');
  const button=text=>nodes.find(node=>node.tag==='button' && node.textContent===text);
  const controls={entry:{value:raw},'last-caffeine-intake':input,'phone-game-before-morning-work':{checked:true},'phone-game-before-afternoon-work':{checked:false},jo:{checked:false},'jo-worth':{checked:false},'jo-why':{value:''}};
  Object.assign(context,{guided:true,period:'evening',entry:{date:'2026-11-06'},reviewTasks:[],parts:[{title:'Reflection'}],el:id=>controls[id]||{value:id.startsWith('answer-')?'An answer.':''}});
  vm.runInContext(content,context);
  return {input,status,button,save:()=>plans.habits(context.content()).value,changes:()=>changes,nodes};
}
for(const [time,after] of [['00:00',false],['08:45',false],['15:00',false],['16:00',false],['16:01',true],['17:00',true],['19:00',true],['23:59',true],['none',false],[null,null],['25:00',null],['7 p.m.',null],['17:00\n',null],[1700,null]]){
  assert.equal(plans.caffeine({caffeine_last_intake:time}).after4pm,after);
}
for(const flag of [true,false]){
  const old=editor({caffeine_after_4pm:flag,custom_habit:'preserve'});
  assert.equal(old.input.value,'');assert.match(old.status.textContent,/exact time not recorded/);
  assert.equal(old.save().caffeine_after_4pm,flag);assert.equal(old.save().custom_habit,'preserve');
  assert.equal(Object.hasOwn(old.save(),'caffeine_last_intake'),false);
  assert.equal(old.changes(),0,'Opening an entry must not create a draft.');
  old.button('5 p.m.').events.click();
  assert.equal(old.input.value,'17:00');assert.equal(old.button('5 p.m.').attributes['aria-pressed'],'true');
  assert.equal(old.save().caffeine_last_intake,'17:00');assert.equal(Object.hasOwn(old.save(),'caffeine_after_4pm'),false);
  assert.equal(old.save().phone_game_before_morning_work,true);assert.equal(old.save().custom_habit,'preserve');
}
const current=editor();
assert.equal(plans.caffeine(current.save()).after4pm,null);
assert.equal(current.button('Not logged').attributes['aria-pressed'],'true');
for(const hour of [3,4,5,6,7]){
  current.button(`${hour} p.m.`).events.click();assert.equal(current.save().caffeine_last_intake,`${hour+12}:00`);
}
current.input.value='18:35';current.input.events.input();
assert.equal(current.save().caffeine_last_intake,'18:35');assert.match(current.status.textContent,/6:35 p.m./);
current.button('No caffeine').events.click();
assert.equal(current.input.value,'');assert.equal(current.save().caffeine_last_intake,'none');
assert.equal(current.button('No caffeine').attributes['aria-pressed'],'true');
current.button('Not logged').events.click();
assert.equal(current.save().caffeine_last_intake,null);assert.equal(plans.caffeine(current.save()).after4pm,null);
for(const intake of ['none','18:35',null]){
  const reloaded=editor({caffeine_last_intake:intake,caffeine_after_4pm:true});
  assert.equal(reloaded.save().caffeine_last_intake,intake);
  assert.equal(reloaded.input.value,intake && intake!=='none'?intake:'');
  assert.doesNotMatch(reloaded.status.textContent,/Earlier entry/);
}
assert.equal(current.nodes.filter(node=>node.tag==='button').length,7);
assert.ok(current.nodes.filter(node=>node.tag==='button').every(button=>button.type==='button'));
console.log('Caffeine picker, quick choices, custom times, unknown logs and legacy preservation checks passed.');
