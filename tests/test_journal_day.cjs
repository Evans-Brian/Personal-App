const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {spawnSync}=require('node:child_process');
if(!process.argv.includes('--one-zone')){
  for(const zone of ['America/New_York','Pacific/Honolulu','Asia/Tokyo','UTC']){
    const result=spawnSync(process.execPath,[__filename,'--one-zone'],{env:{...process.env,TZ:zone},encoding:'utf8'});
    process.stdout.write(result.stdout);process.stderr.write(result.stderr);
    assert.equal(result.status,0,zone);
  }
  process.exit(0);
}
const plansSource=fs.readFileSync('static/plans.js','utf8');
const app=fs.readFileSync('static/app.js','utf8');
const bjj=fs.readFileSync('static/bjj.js','utf8');
const sleep=fs.readFileSync('static/sleep.js','utf8');
const dateLine=app.match(/^el\('date'\)\.value = .*;$/m)[0];
const trainingLine=bjj.match(/^  (?:const today=.*)?trainingDate\.value=.*;$/m)[0];
const monthLine=bjj.split('\n').find(line=>line.includes('currentMonthKey='));
const rangeLine=sleep.match(/^  function range\(\).*$/m)[0];
const keyLine=sleep.match(/^  const dateKey=.*$/m)[0];
const cases=[
  [new Date(2026,10,5,0,0),'2026-11-04','evening'],
  [new Date(2026,10,5,1,59,59,999),'2026-11-04','evening'],
  [new Date(2026,10,5,2,0),'2026-11-05','morning'],
  [new Date(2026,10,5,14,59),'2026-11-05','morning'],
  [new Date(2026,10,5,15,0),'2026-11-05','evening'],
  [new Date(2027,0,1,0,30),'2026-12-31','evening'],
  [new Date(2028,2,1,1,0),'2028-02-29','evening'],
  [new Date(2026,2,8,1,30),'2026-03-07','evening'],
  [new Date(2026,2,8,3,0),'2026-03-08','morning']
];
if(process.env.TZ==='America/New_York')for(const offset of ['-04:00','-05:00'])cases.push([new Date('2026-11-01T01:30:00'+offset),'2026-10-31','evening']);
for(const [now,day,period] of cases){
  class Clock extends Date {constructor(...args){super(...(args.length?args:[now.getTime()]));}static now(){return now.getTime();}}
  const fields={date:{value:''},'sleep-range':{value:'90'},'sleep-from':{value:''},'sleep-to':{value:''}};
  const context=vm.createContext({Date:Clock,document:{getElementById:id=>fields[id]},trainingDate:{value:''},analysisStart:null,$:id=>fields[id]});
  vm.runInContext(plansSource,context);
  vm.runInContext(app.slice(0,app.indexOf('let entry ='))+'\nconst now = new Date();\n'+dateLine+'\nselectedPeriod=period;',context);
  assert.equal(fields.date.value,day,'Journal default at '+now.toString());
  assert.equal(context.selectedPeriod,period,'Early hours should open the previous evening.');
  vm.runInContext(trainingLine+'\n'+monthLine+'\nselectedMonth=currentMonthKey;',context);
  assert.equal(context.trainingDate.value,day,'BJJ should use the same default day.');
  assert.equal(context.selectedMonth,day.slice(0,7));
  vm.runInContext(keyLine+'\n'+rangeLine+'\nrange();',context);
  assert.equal(fields['sleep-to'].value,day,'The default sleep range should use the same day cutoff.');
  const span=(Date.parse(day+'T12:00:00Z')-Date.parse(fields['sleep-from'].value+'T12:00:00Z'))/86400000;
  assert.equal(span,89,'Retain a 90-calendar-day inclusive range across clock changes.');
  fields['sleep-range'].value='custom';fields['sleep-from'].value='manual start';fields['sleep-to'].value='manual end';
  context.range();assert.equal(fields['sleep-from'].value,'manual start');assert.equal(fields['sleep-to'].value,'manual end');
  const before=now.getTime();assert.equal(context.JournalPlans.journalDay(now),day);assert.equal(now.getTime(),before);
}
console.log('2 a.m. day cutoff, evening default, BJJ, sleep range, month/year/leap/DST checks passed: '+process.env.TZ);
