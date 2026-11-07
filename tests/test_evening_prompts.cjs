const assert=require('node:assert/strict'),fs=require('node:fs');
const plans=require('../static/plans.js');
const cases=JSON.parse(fs.readFileSync('tests/fixtures/evening_prompt_merge.json','utf8'));
for(const test of cases){
  const merged=plans.combineEvening(test.before);
  assert.equal(merged,test.after,test.name);
  assert.equal(plans.combineEvening(merged),merged,'Already combined answers must not gain duplicate labels.');
}
const first=plans.split(plans.combineEvening(cases[0].before));
assert.equal(first.ratings.good,'7');assert.equal(first.ratings.productive,'6');
assert.equal(plans.habits(plans.combineEvening(cases[0].before)).value.caffeine_last_intake,'16:00');
assert.equal(plans.jo(plans.combineEvening(cases[0].before)).value.jo,false);
console.log('Combined evening answers, labels, multiline text, metadata, legacy drafts and idempotence checks passed.');
