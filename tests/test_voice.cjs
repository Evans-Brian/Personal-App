const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/voice.js','utf8');
const append=source.slice(source.indexOf('  function appendTranscript('),source.indexOf('  async function record('));
assert.ok(append.includes('function appendTranscript('));

function dictate(value,text,options={}){
  const events=[];
  const field={value,tagName:options.tagName||'TEXTAREA',isConnected:true,disabled:false,readOnly:false,maxLength:-1,
    closest:()=>options.bjj===false?null:{},
    dispatchEvent:event=>events.push(event.type),focus(){this.focused=true;},...options};
  const context={active:field,review:{hidden:true},info:{},text,closed:false,
    Event:class{constructor(type){this.type=type;}},
    close(){context.closed=true;context.active=null;}};
  vm.createContext(context);vm.runInContext(append+'\nappendTranscript(text);',context);
  return {field,events,...context};
}

const first=dictate('','First practice note.').field.value;
const second=dictate(first,'Second practice note.');
assert.equal(second.field.value,'First practice note.\nSecond practice note.','Separate BJJ recordings must not run together.');
assert.deepEqual(second.events,['input','change']);
assert.ok(second.closed&&second.field.focused);
assert.equal(dictate('- First note.\n','- Second note.').field.value,'- First note.\n- Second note.');
assert.equal(dictate('- First note.\n  ','Second note.').field.value,'- First note.\n  Second note.');
assert.equal(dictate('- First note.\n- ','Second note.').field.value,'- First note.\n- Second note.','Dictating into an unfinished bullet should fill that bullet.');
assert.equal(dictate('1. ','First note.').field.value,'1. First note.');
assert.equal(dictate('First note.\r\n','Second note.').field.value,'First note.\r\nSecond note.');
assert.equal(dictate('','  First line.\n\nSecond paragraph.  ').field.value,'First line.\n\nSecond paragraph.');
assert.equal(dictate('Search','guard',{tagName:'INPUT'}).field.value,'Search guard','Single-line fields must stay on one line.');
assert.equal(dictate('Reflection','Another sentence.',{bjj:false}).field.value,'Reflection Another sentence.','Other journal dictation behavior is unchanged.');
const limited=dictate('First','Second',{maxLength:10});
assert.equal(limited.field.value,'First');assert.equal(limited.review.value,'Second');assert.equal(limited.review.hidden,false);assert.equal(limited.closed,false);
const changed=dictate('First','Second',{readOnly:true});
assert.equal(changed.field.value,'First');assert.equal(changed.review.value,'Second');assert.equal(changed.closed,false);
console.log('BJJ dictation line breaks, unfinished bullets, original paragraphs, field limits and single-line input checks passed.');
