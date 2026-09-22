(() => {
  const $=id=>document.getElementById(id);
  let people=[],selected=null,busy=false,prefix='',ready=false,draftFailed=false;
  const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const node=(tag,text)=>{const e=document.createElement(tag);if(text)e.textContent=text;return e;};
  function status(text,error=false){$('people-status').textContent=text;$('people-status').className=error?'error':'';}
  function readDraft(key){try{return JSON.parse(localStorage.getItem(prefix+key)) || {};}catch{return {};}}
  function draft(key,value){try{localStorage.setItem(prefix+key,JSON.stringify(value));draftFailed=false;}catch{draftFailed=true;status('Browser draft recovery is unavailable. Save your note before leaving.',true);}}
  function clear(key){try{localStorage.removeItem(prefix+key);}catch{}}
  let personDraft={};
  function lock(value){busy=value;document.querySelectorAll('#people-page button, #people-page input, #people-page textarea').forEach(e=>e.disabled=value);}
  async function add(payload){const r=await fetch('/api/people',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await r.json();if(!r.ok)throw Error(data.error || 'Could not save.');people=data.people;}
  function directory(){
    const query=$('people-search').value.trim().toLowerCase(),list=$('people-directory');list.replaceChildren();
    const matches=people.filter(p=>(p.name+' '+p.relation+' '+p.notes.map(n=>n.text).join(' ')).toLowerCase().includes(query)).sort((a,b)=>a.name.localeCompare(b.name));
    if(!matches.length)list.append(node('p',people.length?'No matches.':'Add your first person above.'));
    for(const p of matches){const b=node('button');b.type='button';b.className='people-person';b.setAttribute('aria-pressed',String(p.id===selected));b.append(node('strong',p.name),node('small',p.relation+` Â· ${p.notes.length} note${p.notes.length===1?'':'s'}`));b.onclick=()=>{if(busy)return;selected=p.id;directory();detail();};list.append(b);}
  }
  function detail(){
    const panel=$('people-detail');panel.replaceChildren();const p=people.find(p=>p.id===selected);
    if(!p){panel.append(node('p','Select a person to see their dated notes.'));return;}
    panel.append(node('h2',p.name));
    const relationForm=node('form'),relationLabel=node('label','Relation to me'),relation=node('input');
    relation.type='text';relation.required=true;relation.maxLength=300;relation.value=p.relation;relationLabel.append(relation);
    const saveRelation=node('button','Save relation');saveRelation.type='submit';relationForm.append(relationLabel,saveRelation);panel.append(relationForm);
    relationForm.onsubmit=async event=>{
      event.preventDefault();if(busy || !relation.value.trim())return;
      lock(true);status('Saving relation…');
      try{await add({action:'relation',id:crypto.randomUUID(),person_id:p.id,relation:relation.value,previous_relation:p.relation});p.relation=relation.value.trim();directory();status('Relation saved to your vault.');}
      catch(error){status(error.message,true);}finally{lock(false);}
    };

    const key='note:'+p.id;let savedDraft=readDraft(key);
    const form=node('form'),label=node('label','Note date'),date=node('input');date.type='date';date.required=true;date.value=savedDraft.date||today();label.append(date);
    const textLabel=node('label','Notes'),text=node('textarea');text.required=true;text.maxLength=40000;text.rows=4;text.value=savedDraft.text||'';text.placeholder='A conversation, something they mentioned, or anything you want to rememberâ€¦';textLabel.append(text);
    const save=node('button','Save note');save.type='submit';save.className='primary';form.append(label,textLabel,save);panel.append(form);
    const remember=()=>{savedDraft={id:crypto.randomUUID(),date:date.value,text:text.value};draft(key,savedDraft);};date.oninput=remember;text.oninput=remember;
    form.onsubmit=async event=>{event.preventDefault();if(busy||!text.value.trim())return;
      if(!savedDraft.id){savedDraft={id:crypto.randomUUID(),date:date.value,text:text.value};draft(key,savedDraft);}
      lock(true);status('Saving noteâ€¦');
      try{await add({action:'note',person_id:p.id,...savedDraft});clear(key);directory();detail();status('Note saved to your vault.');}
      catch(error){status(error.message+' Your text is still here.',true);}finally{lock(false);}
    };
    if(savedDraft.text){const hint=node('p','Unfinished note recovered. Save when ready.');hint.className='small';form.append(hint);}
    const timeline=node('div');timeline.className='people-timeline';panel.append(node('h3','Dated notes'),timeline);
    if(!p.notes.length)timeline.append(node('p','No notes yet. Add your first one above.'));
    for(const note of [...p.notes].reverse().sort((a,b)=>b.date.localeCompare(a.date))){const card=node('article');card.className='people-note';const time=node('time',note.date);time.dateTime=note.date;const body=node('p',note.text);card.append(time,body);timeline.append(card);}
  }
  $('people-search').oninput=directory;
  function rememberPerson(){personDraft={id:crypto.randomUUID(),name:$('people-name').value,relation:$('people-relation').value};draft('new-person',personDraft);}
  $('people-name').oninput=rememberPerson;$('people-relation').oninput=rememberPerson;
  $('add-person-form').onsubmit=async event=>{event.preventDefault();if(!ready||busy)return;
    if(!personDraft.id)rememberPerson();lock(true);status('Saving personâ€¦');
    try{await add({action:'person',...personDraft});selected=personDraft.id;clear('new-person');personDraft={};$('people-name').value='';$('people-relation').value='';$('people-search').value='';directory();detail();status('Person saved. You can add dated notes below.');}
    catch(error){status(error.message,true);}finally{lock(false);}
  };
  window.addEventListener('beforeunload',event=>{if(draftFailed){event.preventDefault();event.returnValue='';}});
  Promise.all([fetch('/api/config').then(r=>r.json()),fetch('/api/people').then(async r=>{const data=await r.json();if(!r.ok)throw Error(data.error);return data;})]).then(([config,data])=>{
    prefix='people-draft:'+config.vault+':';people=data.people;ready=true;
    personDraft=readDraft('new-person');$('people-name').value=personDraft.name||'';$('people-relation').value=personDraft.relation||'';
    selected=people[0]?.id||null;directory();detail();lock(false);status('People loaded.');
  }).catch(error=>status('Could not load People: '+error.message,true));
})();
