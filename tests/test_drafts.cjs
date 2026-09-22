const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8').split('const prompts =')[0];
function recover({revision='new',baseContent,content='my draft',saved='saved',draftRevision='old'}){
 const data=new Map([['journal-draft:v:2026-09-21:evening:old',JSON.stringify({content,revision:draftRevision,baseContent,updated:1})]]);
 const storage=new Proxy({getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}, {ownKeys:()=>[...data.keys()],getOwnPropertyDescriptor:()=>({enumerable:true,configurable:true})});
 const context=vm.createContext({crypto:{randomUUID:()=> 'test'},localStorage:storage,document:{getElementById:()=>({})},Date});
 vm.runInContext(source+`;period='evening';vaultId='v';entry=${JSON.stringify({date:'2026-09-21',revision,sections:{evening:saved}})};let shown,conflict=false;showEditor=t=>shown=t;status=()=>{};showConflict=()=>conflict=true;recoverDraft();result={shown,conflict,revision:entry.revision};`,context);
 return context.result;
}
assert.equal(recover({baseContent:'saved'}).conflict,false,'Unchanged section rebases across another period edit');
assert.equal(recover({baseContent:'saved'}).revision,'new');
assert.equal(recover({baseContent:'older'}).conflict,true,'Same-section conflict needs review');
assert.equal(recover({}).conflict,true,'Legacy drafts cannot silently overwrite');
assert.equal(recover({content:'saved'}).shown,undefined,'Already saved draft not restored');
console.log('Draft recovery regression checks passed');
