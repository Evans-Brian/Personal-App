const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/sleep.js','utf8');
// Exercise the real timeline renderer without loading unrelated app controls.
const renderer=source.slice(source.indexOf('  function timeline(){'),source.indexOf('  function selectNight('));
const formatter=source.match(/^  const clockNumber=.*$/m)[0];
const duration=source.match(/^  const duration=.*$/m)[0];
class Element {
  constructor(tag,text,cls){this.tag=tag;this.text=text;this.className=cls;this.children=[];this.style={};this.attributes={};this.events={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this.attributes[name]=value;}
  addEventListener(name,handler){this.events[name]=handler;}
}
const node=(...args)=>new Element(...args);
const controls={'sleep-timeline':node('div'),'sleep-timeline-more':node('button')};
const night=(id,base,hours=2,stages=true)=>({id,day:'2026-10-01',bedtime_clock:base,in_bed_minutes:hours*60,stages:stages?[{stage:'1',start_seconds:0,end_seconds:hours*3600}]:[]});
const nights=[night('early',21*60),night('late',37*60),night('spanning',20*60,20),night('before',20*60,1),night('after',39*60,1),night('unstaged',23*60,1,false),night('inside',26*60,1)];
nights[0].asleep_minutes=95;
nights[0].data_source='manual';
nights[0].stages_estimated=true;
nights[1].asleep_minutes=0;
const original=JSON.stringify(nights),clicks=[];
const context=vm.createContext({node,$:id=>controls[id],valid:Number.isFinite,data:{nights},selected:'late',visibleNights:60,selectNight:(...args)=>clicks.push(args)});
vm.runInContext(formatter+'\n'+duration+'\n'+renderer+'\ntimeline();',context);
const [axis,...rows]=controls['sleep-timeline'].children[0].children;
assert.deepEqual(axis.children.map(label=>label.text),['10:00 p.m.','2:00 a.m.','6:00 a.m.','10:00 a.m.','2:00 p.m.']);
const row=id=>rows[nights.length-1-nights.findIndex(n=>n.id===id)];
const segments=id=>row(id).children[1].children;
for(const [id,left,width] of [['early','0%','6.25%'],['late','93.75%','6.25%'],['spanning','0%','100%'],['unstaged','6.25%','6.25%'],['inside','25%','6.25%']]){
  assert.equal(segments(id).length,1);
  assert.equal(segments(id)[0].style.left,left,id);
  assert.equal(segments(id)[0].style.width,width,id);
}
assert.equal(segments('before').length,0);
assert.equal(segments('after').length,0);
assert.equal(row('late').attributes['aria-pressed'],'true');
assert.deepEqual(row('early').children[0].children.map(item=>item.text),['10-01','1h 35m','Manual · guessed stages']);
assert.equal(row('early').attributes['aria-label'],'Inspect sleep on 2026-10-01; 1h 35m asleep; manual entry; light, deep and REM stages are guesses');
assert.match(segments('early')[0].title,/illustrative guess/);
assert.equal(row('late').children[0].children[1].text,'0h 0m');
assert.equal(row('unstaged').children[0].children[1].text,'—');
assert.match(row('unstaged').attributes['aria-label'],/total sleep unknown/);
row('late').events.click();
assert.deepEqual(clicks,[['late',true]]);
assert.equal(controls['sleep-timeline-more'].hidden,true);
assert.equal(JSON.stringify(nights),original,'The display window must not modify source sleep records.');
console.log('Sleep timeline totals, manual labels, clock range, clipping and selection checks passed.');
