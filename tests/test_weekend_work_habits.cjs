const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const plans=require('../static/plans.js');
const keys=['phone_game_before_morning_work','phone_game_before_afternoon_work'];
const value={[keys[0]]:true,[keys[1]]:false,caffeine_last_intake:'17:00',custom:'keep'};
for(const day of ['2026-11-07','2026-11-08']){
  assert.equal(plans.isWeekend(day),true);
  assert.deepEqual(plans.workHabits(value,day),{caffeine_last_intake:'17:00',custom:'keep'});
  const raw='A reflection.\n'+plans.serializeHabits(value);
  const cleaned=plans.cleanWeekendWorkHabits(raw,day);
  assert.equal(decodeURIComponent(cleaned).includes('phone_game_before'),false);
  assert.equal(plans.cleanWeekendWorkHabits(cleaned,day),cleaned);
}
for(const day of ['2026-11-06','2026-11-09','2026-11-11']){
  assert.equal(plans.isWeekend(day),false);assert.deepEqual(plans.workHabits(value,day),value);
  const raw=plans.serializeHabits(value);assert.equal(plans.cleanWeekendWorkHabits(raw,day),raw);
}
assert.equal(value[keys[0]],true,'Filtering must not mutate the original habit object.');
// Execute the actual editor serializer with the weekend-only controls absent.
const source=fs.readFileSync('static/app.js','utf8');
const content=source.slice(source.indexOf('function content()'),source.indexOf('function showEditor('));
for(const day of ['2026-11-07','2026-11-08']){
  const raw=plans.serializeHabits(value);
  const controls={entry:{value:raw},'last-caffeine-intake':{dataset:{edited:'false'}},jo:{checked:false},'jo-worth':{checked:false},'jo-why':{value:''}};
  const context=vm.createContext({JournalPlans:plans,guided:true,period:'evening',entry:{date:day},reviewTasks:[],parts:[{title:'Reflection'}],
    el:id=>id.startsWith('phone-game-')?null:controls[id]||{value:'An answer.'}});
  vm.runInContext(content+'\nresult=content();',context);
  const payload=JSON.parse(decodeURIComponent(context.result.match(/<!-- evening-habits: (.*?) -->/)[1]));
  assert.equal(Object.hasOwn(payload,keys[0]),false);assert.equal(Object.hasOwn(payload,keys[1]),false);
  assert.equal(payload.caffeine_last_intake,'17:00');assert.equal(payload.custom,'keep');
}
console.log('Saturday/Sunday work-habit removal, weekday preservation, legacy drafts and safe weekend saves passed.');
