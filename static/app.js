const el = id => document.getElementById(id);
let period = new Date().getHours() < 15 ? 'morning' : 'evening';
let entry = null, dirty = false, busy = false;
let guided = false, parts = [];
let yesterdayReflection="";
let reviewTasks=[];
let carryChoices={}, carryData={items:[]};
let vaultId='', draftStored=false, activeDraftKey=null, recoveredDraftKey=null;
let draftBase=null;
const draftSession=crypto.randomUUID();
function draftPrefix(){return `journal-draft:${vaultId}:${entry.date}:${period}:`;}
function storeDraft(){
  if(!entry || !dirty) return true;
  try {
    // Each tab owns its own draft; another tab cannot silently replace it.
    activeDraftKey=activeDraftKey || draftPrefix()+draftSession;
    localStorage.setItem(activeDraftKey,JSON.stringify({content:content(),revision:entry.revision,baseContent:draftBase,updated:Date.now()}));
    draftStored=true; return true;
  } catch {draftStored=false;status('Draft recovery is unavailable. Save to your vault before closing this tab.',true);return false;}
}
function recoverDraft(){
  try {
    const drafts=Object.keys(localStorage).filter(key=>key.startsWith(draftPrefix())).map(key=>{
      try{return {key,...JSON.parse(localStorage.getItem(key))};}catch{return null;}
    }).filter(d=>d && typeof d.content==='string' && typeof d.revision==='string').sort((a,b)=>b.updated-a.updated);
    const draft=drafts[0];
    if(!draft) return;
    if(draft.content.trim()===entry.sections[period].trim()) {localStorage.removeItem(draft.key);return;}
    const changedOnDisk=entry.revision!==draft.revision && draft.baseContent!==entry.sections[period];
    draftBase=draft.baseContent ?? null;
    const latest=entry;
    entry={...entry,revision:changedOnDisk?draft.revision:entry.revision}; showEditor(draft.content); dirty=true;draftStored=true;
    // Keep the source draft until this tab successfully saves; new edits get a new key.
    activeDraftKey=null;
    recoveredDraftKey=draft.key;
    if(changedOnDisk)showConflict(latest);
    else status('Unsaved draft recovered. Save when ready.');
  } catch {status('Could not recover browser drafts. Your saved vault note is loaded.',true);}
}
function clearDrafts(){
  // Clear this editor's drafts only; other tabs retain their own copies.
  const matching=Object.keys(localStorage).filter(key=>key.startsWith(draftPrefix())).filter(key=>{
    try{const draft=JSON.parse(localStorage.getItem(key));return draft.revision===entry.revision && draft.content.trim()===content().trim();}catch{return false;}
  });
  for(const key of new Set([activeDraftKey,recoveredDraftKey,...matching].filter(Boolean))){
    localStorage.removeItem(key);
  }
  activeDraftKey=null; recoveredDraftKey=null;
}
// Keep a downloadable copy of both versions before retiring recovery keys.
function showConflict(latest){
  el('journal-conflict')?.remove();
  const panel=document.createElement('section');panel.id='journal-conflict';panel.className='card';
  const title=document.createElement('h3');title.textContent='Review your recovered draft';panel.append(title);
  const help=document.createElement('p');help.textContent='Your draft is still in the editor. Compare it with the saved version below. Both versions will be backed up before you choose.';panel.append(help);
  const label=document.createElement('label');label.textContent='Currently saved note';
  const saved=document.createElement('textarea');saved.readOnly=true;saved.value=latest.sections[period];saved.rows=10;label.append(saved);panel.append(label);
  const download=document.createElement('a');download.textContent='Download both versions';download.download=`journal-recovery-${entry.date}-${period}.json`;
  const snapshot=()=>({date:entry.date,period,draft:content(),saved:latest.sections[period],revision:latest.revision,updated:Date.now()});
  let url=null;
  download.addEventListener('click',()=>{if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(new Blob([JSON.stringify(snapshot(),null,2)],{type:'application/json'}));download.href=url;});panel.append(download);
  const choose=useDraft=>{
    if(busy)return;
    try{
      const backup=snapshot();
      const keys=Object.keys(localStorage).filter(key=>key.startsWith(draftPrefix()));
      backup.browserDrafts=keys.map(key=>({key,value:localStorage.getItem(key)}));
      localStorage.setItem(`journal-archive:${vaultId}:${entry.date}:${period}:${crypto.randomUUID()}`,JSON.stringify(backup));
      for(const item of backup.browserDrafts)if(localStorage.getItem(item.key)===item.value)localStorage.removeItem(item.key);
      entry=latest;draftBase=latest.sections[period];activeDraftKey=null;recoveredDraftKey=null;
      dirty=useDraft;draftStored=false;showEditor(useDraft?backup.draft:latest.sections[period]);
      if(useDraft)storeDraft();panel.remove();
      status(useDraft?'Draft kept. Review your edits, then save. Both versions are backed up in this browser.':'Saved note loaded. Your previous draft is backed up in this browser.');
    }catch{status('Could not back up both versions. Download them before continuing; your draft has been kept.',true);}
  };
  for(const [text,keep] of [['Keep my edited draft',true],['Use saved note',false]]){
    const button=document.createElement('button');button.type='button';button.textContent=text;button.addEventListener('click',()=>choose(keep));panel.append(button);
  }
  el('status').closest('.actions').after(panel);
  status('Your draft and saved note differ. Review the versions below to continue.',true);
}
const prompts = {
  morning: ['How am I feeling this morning?', 'What would make today feel like a good day?', 'What would be great to do today, if I have time?', 'What might get in the way, and what could help?'],
  evening: ['What made me happy or grateful today?', 'When did I feel most engaged or connected today?', 'What am I proud of today?', 'What would I do differently if I replayed today?', 'What moment would I like to remember?', 'What did I learn today—about myself, someone else, or the world?']
};
const hints = {
  morning: ['Notice your mood, energy, sleep, or whatever is on your mind.', 'List a few things you would like to move forward, experience, or follow up on. They do not all have to be accomplishments.', 'Optional extras, if there is room in your day.', 'Think about practical obstacles, feelings, distractions, or support you might need.'],
  evening: ['A person, a small pleasure, or something that went well.', 'An activity that held your attention, or a moment of connection with someone.', 'An effort, a choice, or how you handled something. Small things count.', 'One thing you might approach differently, knowing what you know now.', 'Capture a detail, a conversation, or a scene you would like to revisit.', 'A discovery, a new perspective, or something you noticed about yourself.']
};
function parsePrompts(text) {
  if(period==='evening')text=JournalPlans.split(text).body;
  else text=JournalPlans.upgrade(text);
  const matches = [...text.matchAll(/^### (.+)\r?\n/gm)];
  if (matches.length !== prompts[period].length || text.slice(0,matches[0].index).trim() || matches.some((m,i)=>m[1].trim()!==prompts[period][i])) return null;
  const parsed=matches.map((m,i)=>({title:prompts[period][i], answer:text.slice(m.index+m[0].length, matches[i+1]?.index ?? text.length).trim()}));
  if(period==='morning' && (JournalPlans.items(parsed[1].answer)===null || JournalPlans.items(parsed[2].answer,Infinity)===null))return null;
  return parsed;
}
function content() {
  if (!guided) return el('entry').value;
  if(period==='morning'){
    const ownPrefix=entry.date+':[If time] ';
    for(const key of Object.keys(carryChoices))if(key.startsWith(ownPrefix) && String(carryChoices[key]).startsWith('Skipped until '))delete carryChoices[key];
    for(const row of document.querySelectorAll('.optional-plan-row')){
      const text=row.querySelector('.plan-input').value.trim();
      if(text && row.querySelector('.do-later-check').checked)carryChoices[ownPrefix+text]='Skipped until '+row.querySelector('.do-later-date').value;
    }
  }
  const prefix=period==='evening'?JournalPlans.serialize(reviewTasks.map((t,i)=>({...t,done:el(`plan-done-${i}`).checked})))+`### Daily ratings\n\nGood day: ${el('rating-good').value || 'unrated'}\nProductive day: ${el('rating-productive').value || 'unrated'}\n\n`:'';
  return (period==='morning'?'<!-- carry-review: '+encodeURIComponent(JSON.stringify(carryChoices))+' -->\n':'')+prefix+parts.map((p,i)=>{
    const answer=period==='morning' && (i===1 || i===2)?[...document.querySelectorAll(`[id^="${i===2?'optional':'plan'}-"].plan-input`)].map(field=>field.value.trim()).filter(Boolean).map(s=>`- ${s}`).join('\n'):el(`answer-${i}`).value.trim();
    return `### ${p.title}\n\n${answer}\n\n`;
  }).join('')+(period==='evening'?JournalPlans.serializeJO({jo:el('jo').checked,worth_it:el('jo-worth').checked,why:el('jo-why').value}):'');
}
function showEditor(text, preferGuided=true) {
  // Refresh only an entirely blank old template; never relabel existing answers.
  const oldMorning = ['How am I feeling this morning?', 'What matters most today?', 'What is one small thing I can do for myself?'];
  const oldEvening = ['What stood out today?', 'What felt difficult, and what helped?', 'What do I want to carry into tomorrow?'];
  const oldPrompts = period==='morning' ? oldMorning : oldEvening;
  if (text.replace(/\s/g,'')===oldPrompts.map(title=>`### ${title}`).join('').replace(/\s/g,'')) {
    text=prompts[period].map(title=>`### ${title}\n\n`).join('');
  }
  if(period==='morning')carryChoices=JournalPlans.review(text).choices;
  parts=parsePrompts(text) || []; guided=preferGuided && parts.length===prompts[period].length;
  el('guided').replaceChildren();
  el('plan-review').replaceChildren();
  if(guided && period==='evening'){
    const deferred=JournalPlans.review(entry.sections.morning).choices;
    reviewTasks=JournalPlans.reconcile(JournalPlans.morning(entry.sections.morning),JournalPlans.split(text).tasks).filter(task=>{
      const decision=deferred[entry.date+':'+(task.original || task.text)];
      return task.done || !(typeof decision==='string' && decision.startsWith('Skipped until ') && decision.slice(14)>entry.date);
    });
    reviewTasks.sort((a,b)=>Number(a.text.startsWith('[If time] '))-Number(b.text.startsWith('[If time] ')));
    const title=document.createElement('h3');title.textContent='How did your plans go?';el('plan-review').append(title);
    const hint=document.createElement('p');hint.className='small';hint.textContent=reviewTasks.length?'Check what you got done, then save your evening entry.':'No tasks yet. Add an evening task below.';el('plan-review').append(hint);
    reviewTasks.forEach((task,i)=>{
      if(i>0 && task.text.startsWith('[If time] ')!==reviewTasks[i-1].text.startsWith('[If time] ')){
        const divider=document.createElement('hr');divider.className='plan-group-divider';el('plan-review').append(divider);
      }
      const groupTitle=document.createElement('small');groupTitle.textContent=task.text.startsWith('[If time] ')?'If I have time':'Good-day plans';el('plan-review').append(groupTitle);
      const label=document.createElement('label');label.className='plan-check';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id=`plan-done-${i}`;checkbox.checked=task.done;checkbox.addEventListener('change',changed);
      const span=document.createElement('span');span.textContent=(task.followup?'Follow-up: ':'')+task.text.replace(/^\[If time\] /,'')+(task.earlier?' (from an earlier version of your morning plans)':'');label.append(checkbox,span);el('plan-review').append(label);
      const tools=document.createElement('details');tools.className='task-edit';
      const summary=document.createElement('summary');summary.textContent=task.followup?'Edit follow-up':'Edit task / add follow-up';tools.append(summary);
      const editLabel=document.createElement('label');editLabel.textContent='Evening description';
      const edit=document.createElement('input');edit.type='text';edit.value=task.text.replace(/^\[If time\] /,'');edit.maxLength=1000;editLabel.append(edit);tools.append(editLabel);
      const original=task.original || task.text;
      const context=document.createElement('p');context.className='small';context.textContent=task.followup?'Follow-up to: '+(task.parent || '').replace(/^\[If time\] /,''):(task.eveningAdded?'Added this evening: ':'Morning plan: ')+original.replace(/^\[If time\] /,'');tools.append(context);
      edit.addEventListener('input',()=>{
        task.original=original;const prefix=original.startsWith('[If time] ')?'[If time] ':'';
        task.text=edit.value.trim()?prefix+edit.value.trim():original;span.textContent=task.text.replace(/^\[If time\] /,'');changed();
      });
      const nextLabel=document.createElement('label');nextLabel.textContent='What still needs doing?';
      const next=document.createElement('input');next.type='text';next.maxLength=1000;next.placeholder='Describe the remaining work';nextLabel.append(next);tools.append(nextLabel);
      const add=document.createElement('button');add.type='button';add.textContent='+ Add follow-up';
      add.addEventListener('click',()=>{
        if(busy || !next.value.trim())return;
        const prefix=task.text.startsWith('[If time] ')?'[If time] ':'';
        const text=prefix+next.value.trim();
        const current=content();reviewTasks=JournalPlans.split(current).tasks;
        reviewTasks.push({text,original:text,done:false,followup:crypto.randomUUID(),parent:original});
        const parsed=JournalPlans.split(current);
        const ratings=`### Daily ratings\n\nGood day: ${parsed.ratings.good || 'unrated'}\nProductive day: ${parsed.ratings.productive || 'unrated'}\n\n`;
        showEditor(JournalPlans.serialize(reviewTasks)+ratings+parsed.body+JournalPlans.serializeJO(JournalPlans.jo(current).value));changed();
        status('Follow-up added. Save your evening entry to keep it and include it in the next carry-forward review.');
      });tools.append(add);el('plan-review').append(tools);

    });
  }
  if(guided && period==='evening'){
    const addSection=document.createElement('div');addSection.className='evening-add';
    const title=document.createElement('h3');title.textContent='Add an evening task';addSection.append(title);
    for(const [category,prefix] of [['Good-day plans',''],['If I have time','[If time] ']]){
      const row=document.createElement('div');row.className='optional-plan-row';
      const input=document.createElement('input');input.type='text';input.maxLength=1000;input.className='plan-input';input.placeholder=category;input.setAttribute('aria-label','New evening task: '+category);
      const button=document.createElement('button');button.type='button';button.textContent='+ Add to '+category.toLowerCase();
      const addTask=()=>{
        if(busy || !input.value.trim())return;
        const taskText=prefix+input.value.trim(),current=content(),parsed=JournalPlans.split(current);
        if(parsed.tasks.some(task=>task.text.toLowerCase()===taskText.toLowerCase())){status('That task is already in this checklist.',true);return;}
        parsed.tasks.push({text:taskText,original:taskText,done:false,eveningAdded:true});
        const ratings=`### Daily ratings\n\nGood day: ${parsed.ratings.good || 'unrated'}\nProductive day: ${parsed.ratings.productive || 'unrated'}\n\n`;
        showEditor(JournalPlans.serialize(parsed.tasks)+ratings+parsed.body+JournalPlans.serializeJO(JournalPlans.jo(current).value));changed();
        status('Task added. Check it off if done, then save your evening entry. Unfinished tasks will be offered in carry-forward.');
      };
      button.addEventListener('click',addTask);input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addTask();}});
      row.append(input,button);addSection.append(row);
    }
    el('plan-review').append(addSection);
  }
  if(guided && period==='evening'){
    const ratings=JournalPlans.split(text).ratings;
    const title=document.createElement('h3');title.textContent='Rate your day';el('plan-review').append(title);
    for(const [key,question] of [['good','Was this a good day? (happy / fulfilling)'],['productive','Was this a productive day? Grade on a curve for weekends']]){
      const label=document.createElement('label');label.className='rating-label';label.textContent=question;
      const select=document.createElement('select');select.id=`rating-${key}`;
      const blank=document.createElement('option');blank.value='';blank.textContent='Not rated';select.append(blank);
      ['Not at all','A little','Somewhat','Quite','Very'].forEach((anchor,i)=>{const option=document.createElement('option');option.value=String(i+1);option.textContent=`${i+1} — ${anchor}`;select.append(option);});
      select.value=ratings[key] || '';select.addEventListener('change',changed);label.append(select);el('plan-review').append(label);
    }
  }
  if(period==='morning' && yesterdayReflection){
    const reflection=document.createElement('section');reflection.className='prompt';
    const title=document.createElement('h3');title.textContent='From yesterday: what I would do differently';
    const answer=document.createElement('p');answer.textContent=yesterdayReflection;answer.style.whiteSpace='pre-wrap';reflection.append(title,answer);el('guided').append(reflection);
  }
  let extras=null;
  if(guided) parts.forEach((part,i)=>{
    if(period==='evening' && i===4){
      extras=document.createElement('details'); extras.className='optional-prompts';
      extras.open=parts.slice(4).some(p=>p.answer.trim());
      const summary=document.createElement('summary'); summary.textContent='Optional add-ons · A memory and something learned';
      extras.append(summary); el('guided').append(extras);
    }
    const group=document.createElement('div'); group.className='prompt';
    const label=document.createElement('label'); label.htmlFor=`answer-${i}`; label.textContent=part.title;
    const hint=document.createElement('p'); hint.id=`answer-hint-${i}`; hint.textContent=hints[period][i];
    if(period==='morning' && (i===1 || i===2)){
      const fieldPrefix=i===2?'optional':'plan';
      label.htmlFor=fieldPrefix+'-0';hint.textContent='Things you would like to move forward, experience, or follow up on. Add more items as needed.';
      if(i===2)hint.textContent='Optional extras, if there is room in your day. Add as many as you need.';
      group.append(label,hint);const plans=JournalPlans.items(part.answer);
      for(let n=0;n<(i===2?Math.max(1,plans.length):Math.max(4,plans.length));n++){
        const field=document.createElement('input');field.type='text';field.id=`${fieldPrefix}-${n}`;field.value=plans[n] || '';field.placeholder=`Entry ${n+1}`;field.setAttribute('aria-label',`${i===2?'If time':'Good day'} entry ${n+1}`);field.setAttribute('aria-describedby',hint.id);field.className='plan-input';field.hidden=i===2 && n>=Math.max(1,plans.length);field.addEventListener('input',changed);group.append(i===2?optionalPlanRow(field):field);
      }
      {
        const add=document.createElement('button');add.id='add-'+fieldPrefix;add.type='button';add.textContent='+ Add item';

        add.addEventListener('click',()=>{if(!busy)revealPlan(fieldPrefix,true);});group.append(add);
      }
      el('guided').append(group);return;
    }
    const answer=document.createElement('textarea'); answer.id=`answer-${i}`; answer.value=part.answer; answer.rows=3;
    answer.setAttribute('aria-describedby',hint.id); answer.addEventListener('input',changed);
    group.append(label,hint,answer); (extras || el('guided')).append(group);
  });
  if(guided && period==='evening'){
    const value=JournalPlans.jo(text).value;
    const box=document.createElement('section');box.className='prompt';
    const label=document.createElement('label');label.className='plan-check';
    const jo=document.createElement('input');jo.type='checkbox';jo.id='jo';jo.checked=value.jo===true;label.append(jo,document.createTextNode('JO'));
    const extra=document.createElement('div');extra.hidden=!jo.checked;
    const worthLabel=document.createElement('label');worthLabel.className='plan-check';
    const worth=document.createElement('input');worth.type='checkbox';worth.id='jo-worth';worth.checked=value.worth_it===true;worthLabel.append(worth,document.createTextNode('Regret?'));
    const whyLabel=document.createElement('label');whyLabel.textContent='Why?';
    const why=document.createElement('textarea');why.id='jo-why';why.rows=3;why.value=value.why || '';whyLabel.append(why);
    jo.addEventListener('change',()=>{extra.hidden=!jo.checked;changed();});worth.addEventListener('change',changed);why.addEventListener('input',changed);
    extra.append(worthLabel,whyLabel);box.append(label,extra);el('guided').append(box);
  }
  renderCarryover();
  el('guided').hidden=!guided; el('freeform').hidden=guided; el('entry').value=text;
  el('mode').textContent=guided?'Write freely in Markdown':'Use guided prompts';
  el('mode').disabled=busy || !entry || (!guided && !parts.length);
  el('mode-hint').textContent=guided?'All prompts are optional.':parts.length?'Your headings and answers stay in the same note.':'This custom note stays in the Markdown editor to preserve its structure.';
}
function optionalPlanRow(field){
  const row=document.createElement('div');row.className='optional-plan-row';row.append(field);
  const label=document.createElement('label');label.className='do-later-label';
  const check=document.createElement('input');check.type='checkbox';check.className='do-later-check';label.append(check,document.createTextNode('Do Later'));
  const calendar=document.createElement('input');calendar.type='date';calendar.className='do-later-date';calendar.setAttribute('aria-label','Return date for '+(field.value || 'optional item'));
  const tomorrow=new Date(entry.date+'T12:00:00Z');tomorrow.setUTCDate(tomorrow.getUTCDate()+1);calendar.min=tomorrow.toISOString().slice(0,10);
  const decision=carryChoices[entry.date+':[If time] '+field.value.trim()];
  check.checked=typeof decision==='string' && decision.startsWith('Skipped until ');
  calendar.value=check.checked?decision.slice(14):calendar.min;calendar.hidden=!check.checked;
  check.addEventListener('change',()=>{calendar.hidden=!check.checked;changed();});
  calendar.addEventListener('change',()=>{
    if(!calendar.value || calendar.value<calendar.min){calendar.value=calendar.min;status('Choose a date after this journal day.',true);}
    changed();
  });
  row.append(label,calendar);return row;
}
function revealPlan(prefix,focus=false){
  const n=document.querySelectorAll(`[id^="${prefix}-"].plan-input`).length;
  const field=document.createElement('input');field.type='text';field.id=`${prefix}-${n}`;
  field.placeholder=`Entry ${n+1}`;field.className='plan-input';
  field.setAttribute('aria-label',`${prefix==='optional'?'If time':'Good day'} entry ${n+1}`);field.setAttribute('aria-describedby',prefix==='optional'?'answer-hint-2':'answer-hint-1');
  field.addEventListener('input',changed);el('add-'+prefix).before(prefix==='optional'?optionalPlanRow(field):field);
  if(focus)field.focus();
  return field;
}
function renderCarryover(){
  const panel=el('carryover');panel.replaceChildren();
  if(!guided || period!=='morning' || !carryData.items.length)return;
  const title=document.createElement('h3');title.textContent='Carry forward?';panel.append(title);
  const hint=document.createElement('p');hint.className='small';hint.textContent=`From ${carryData.source}${carryData.reviewed?' · not checked off':' · no saved evening checklist, so completion is unknown'}. Choose what belongs today. Nothing is added automatically.`;panel.append(hint);
  for(const item of (carryData.entries || carryData.items.map(text=>({text,key:carryData.source+':'+text})))){
    const task=item.text, key=item.key, text=task.replace(/^\[If time\] /,'');
    const row=document.createElement('div');row.className='carry-row';
    const label=document.createElement('p');label.textContent=text;row.append(label);
    const doneLabel=document.createElement('label');doneLabel.className='plan-check';
    const done=document.createElement('input');done.type='checkbox';done.checked=carryChoices[key]==='Completed';
    done.disabled=busy || String(carryChoices[key] || '').startsWith('Added');
    const doneText=document.createElement('span');doneText.textContent='Already done';doneLabel.append(done,doneText);row.append(doneLabel);
    done.addEventListener('change',()=>{if(busy)return;if(done.checked)carryChoices[key]='Completed';else delete carryChoices[key];changed();renderCarryover();});
    if(carryChoices[key]){const result=document.createElement('span');result.textContent=carryChoices[key];row.append(result);}
    else for(const [action,prefix] of [['Add to good-day plans','plan'],['Add to if-time','optional'],['Skip today',null],['Skip for a week','week'],['Skip for n days','custom']]){
      let daysInput;
      if(prefix==='custom'){
        const label=document.createElement('label');label.textContent='Days to skip';
        daysInput=document.createElement('input');daysInput.type='number';daysInput.min='1';daysInput.max='3650';daysInput.step='1';daysInput.value='2';daysInput.disabled=busy;label.append(daysInput);row.append(label);
      }
      const button=document.createElement('button');button.textContent=action;button.disabled=busy;
      button.addEventListener('click',()=>{
        if(busy)return;
        if(prefix===null || prefix==='week' || prefix==='custom'){
          const days=prefix==='week'?7:prefix==='custom'?Number(daysInput.value):1;
          if(!Number.isInteger(days) || days<1 || days>3650){status('Enter a whole number of days from 1 to 3650.',true);return;}
          const due=new Date(entry.date+'T12:00:00Z');due.setUTCDate(due.getUTCDate()+days);
          carryChoices[key]='Skipped until '+due.toISOString().slice(0,10);changed();renderCarryover();return;
        }
        if(prefix){
          const all=[...document.querySelectorAll('.plan-input')];
          if(all.some(field=>field.value.trim().toLowerCase()===text.toLowerCase())){status('That item is already in today’s plans.');return;}
          const slot=[...document.querySelectorAll(`[id^="${prefix}-"].plan-input`)].find(field=>!field.value.trim()) || revealPlan(prefix);
          slot.value=text;slot.hidden=false;
        }
        carryChoices[key]=prefix?`Added to ${prefix==='plan'?'good-day plans':'if-time'}`:'Skipped today';
        changed();renderCarryover();
      });row.append(button);
    }
    panel.append(row);
  }
}
function changed(){dirty=true;if(storeDraft())status('Draft saved in this browser · not yet saved to your vault');}
const now = new Date();
el('date').value = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
function status(message, error=false) { el('status').textContent=message; el('status').className=error?'error':''; }
function controls(value) { busy=value; for(const id of ['date','previous-day','next-day','morning','evening','save','reload','entry']) el(id).disabled=value || (!entry && ['save','entry'].includes(id)); for(const area of document.querySelectorAll('#guided textarea, #guided input, #guided button, #plan-review input, #plan-review select, #plan-review button, #carryover button')) area.disabled=value || !entry; el('mode').disabled=value || !entry || (!guided && !parsePrompts(el('entry').value)); renderCarryover(); }
function render() {
  for(const name of ['morning','evening']) el(name).setAttribute('aria-pressed', String(period===name));
  el('heading').textContent=period==='morning'?'Start where you are.':'Let the day settle.';
  el('save').textContent=`Save ${period} entry`;
  showEditor(entry.sections[period]); el('file').textContent=entry.path;
}
async function request(url, options) { const response=await fetch(url,options); const data=await response.json(); if(!response.ok) {const error=new Error(data.error || 'Could not complete the request.');error.status=response.status;throw error;} return data; }
async function load() {
  controls(true);
  try { entry=await request(`/api/entry?date=${encodeURIComponent(el('date').value)}`); carryData=await request(`/api/carryover?date=${encodeURIComponent(entry.date)}`); yesterdayReflection='';
    if(period==='morning'){
      const previous=new Date(entry.date+'T12:00:00Z');previous.setUTCDate(previous.getUTCDate()-1);
      const prior=await request('/api/entry?date='+previous.toISOString().slice(0,10));
      const match=JournalPlans.jo(prior.sections.evening).body.match(/^### What would I do differently if I replayed today\?[^\S\r\n]*\r?\n([\s\S]*?)(?=^### |$(?![\s\S]))/m);
      yesterdayReflection=match?match[1].trim():'';
    }
    dirty=false; draftBase=entry.sections[period]; el('journal-conflict')?.remove(); activeDraftKey=null; recoveredDraftKey=null; draftStored=false; render(); status(entry.exists?'Note loaded.':'A fresh page. Your file will be created when you save.');recoverDraft();loadOuraDay(); }
  catch(error) { entry=null; status(error.message,true); }
  finally { controls(false); }
}
function mayLeave() { return !dirty || storeDraft() || confirm('Draft recovery failed. Leave without saving your changes?'); }
el('date').addEventListener('change',()=>{if(mayLeave()) load(); else if(entry) el('date').value=entry.date;});
for(const [id,offset] of [['previous-day',-1],['next-day',1]]){
  el(id).addEventListener('click',()=>{
    if(busy || !el('date').value || !mayLeave())return;
    // UTC calendar arithmetic avoids daylight-saving shifts between dates.
    const date=new Date(el('date').value+'T12:00:00Z');
    date.setUTCDate(date.getUTCDate()+offset);
    const next=date.toISOString().slice(0,10);
    if(!/^\d{4}-\d{2}-\d{2}$/.test(next) || next<'0001-01-01')return;
    el('date').value=next;load();
  });
}

for(const name of ['morning','evening']) el(name).addEventListener('click',()=>{if(name===period || !mayLeave()) return; period=name; load();});
el('entry').addEventListener('input',()=>{changed(); el('mode').disabled=!parsePrompts(el('entry').value);});
el('mode').addEventListener('click',()=>showEditor(content(), !guided));
el('reload').addEventListener('click',async()=>{
  if(busy || !entry)return;
  if(dirty){try{showConflict(await request(`/api/entry?date=${encodeURIComponent(entry.date)}`));}catch(error){status(error.message,true);}return;}
  load();
});
el('save').addEventListener('click',async()=>{
  if(busy || !entry) return; controls(true); status('Saving…');
  try { const saved=await request('/api/entry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:entry.date,period,content:content(),revision:entry.revision})}); try{clearDrafts();}catch{} entry=saved; draftBase=saved.sections[period];el('journal-conflict')?.remove(); dirty=false;draftStored=false;render();status(saved.warning || 'Saved to your vault.',Boolean(saved.warning));loadHistory(); }
  catch(error) {
    if(error.status===409){try{showConflict(await request(`/api/entry?date=${encodeURIComponent(entry.date)}`));}catch(refreshError){status(refreshError.message,true);}}
    else status(error.message,true);
  }
  finally { controls(false); }
});
window.addEventListener('beforeunload',event=>{if(dirty && !storeDraft()){event.preventDefault();event.returnValue='';}});
document.addEventListener('visibilitychange',()=>{if(document.hidden && dirty)storeDraft();});

async function loadHistory(){
  try{
    const data=await request('/api/entries'); el('history').replaceChildren();
    renderTrends(data.entries);loadTaskHistory();
    const dates=new Map(data.entries.map(item=>[item.date,{...item}]));
    try{
      const prefix=`journal-draft:${vaultId}:`;
      for(const key of Object.keys(localStorage).filter(key=>key.startsWith(prefix))){
        const match=key.slice(prefix.length).match(/^(\d{4}-\d{2}-\d{2}):(morning|evening):/);
        if(!match)continue;
        const draft=JSON.parse(localStorage.getItem(key));if(typeof draft.content!=='string')continue;
        const item=dates.get(match[1]) || {date:match[1],morning:'missing',evening:'missing'};
        item[match[2]]='draft';dates.set(item.date,item);
      }
    }catch{}
    if(!dates.size){el('history').textContent='Your saved entries and browser drafts will appear here.';return;}
    for(const item of [...dates.values()].sort((a,b)=>b.date.localeCompare(a.date))){
      const row=document.createElement('button');row.className='history-row';
      row.textContent=`${item.date} · Morning: ${item.morning} · Evening: ${item.evening}`;
      row.addEventListener('click',()=>{if(busy || !mayLeave())return;el('date').value=item.date;load();});el('history').append(row);
    }
  }catch(error){el('history').textContent=error.message;}
}
function renderTrends(entries){
  const key=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const days=new Map(entries.map(row=>[row.date,row]));
  const written=day=>{const row=days.get(key(day));return row && (row.morning==='written' || row.evening==='written');};
  let cursor=new Date(),streak=0;if(!written(cursor))cursor.setDate(cursor.getDate()-1);
  while(written(cursor)){streak++;cursor.setDate(cursor.getDate()-1);}
  el('streak').textContent=`${streak} day${streak===1?'':'s'} journaling streak`;
  el('trends').replaceChildren();
  for(let offset=29;offset>=0;offset--){
    const day=new Date();day.setDate(day.getDate()-offset);const date=key(day),row=days.get(date);
    const line=document.createElement('div');line.className='trend-row';const label=document.createElement('span');label.textContent=date;line.append(label);
    for(const [metric,title] of [['good','Good day'],['productive','Productive']]){
      const cell=document.createElement('div');cell.className=metric;const value=row?.[metric];
      const text=document.createElement('span');text.textContent=`${title}: ${value ?? '—'}`;cell.append(text);
      if(value!=null){const bar=document.createElement('progress');bar.max=5;bar.value=value;bar.setAttribute('aria-label',`${date} ${title}: ${value} out of 5`);cell.append(bar);}line.append(cell);
    }
    el('trends').append(line);
  }
}
el('history').parentElement.addEventListener('toggle',()=>{if(el('history').parentElement.open)loadHistory();});
async function loadOuraDay(){
  const day=el('date').value;
  try{
    const data=await request(`/api/oura/day?date=${encodeURIComponent(day)}`);
    if(day!==el('date').value)return;
    el('oura-stats').replaceChildren();
    for(const [kind,label] of [['daily_sleep','Sleep'],['daily_readiness','Readiness'],['daily_activity','Activity']]){
      const record=data.records.find(r=>r.kind===kind)?.data;
      const card=document.createElement('div');card.className='stat';
      const title=document.createElement('span');title.textContent=label;
      const value=document.createElement('strong');value.textContent=record?.score!=null?`${record.score} / 100`:'—';
      const detail=document.createElement('small');detail.textContent=record?(kind==='daily_activity' && record.steps!=null?`${record.steps.toLocaleString()} steps`:`${day}`):`No summary for ${day}`;
      card.append(title,value,detail);el('oura-stats').append(card);
    }
    const sleeps=data.records.filter(r=>r.kind==='sleep').map(r=>r.data).sort((a,b)=>(a.bedtime_start || '').localeCompare(b.bedtime_start || ''));
    const detailPanel=el('oura-sleep-details');detailPanel.replaceChildren();
    if(!sleeps.length){detailPanel.textContent='No detailed sleep records for this date.';return;}
    const duration=seconds=>typeof seconds==='number' && Number.isFinite(seconds) && seconds>=0?`${Math.floor(Math.round(seconds/60)/60)}h ${Math.round(seconds/60)%60}m`:'—';
    const metric=(value,unit)=>typeof value==='number' && Number.isFinite(value)?`${value.toLocaleString(undefined,{maximumFractionDigits:1})} ${unit}`:'—';
    const clock=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)?`${value.slice(0,10)} ${value.slice(11,16)}`:'—';
    for(const sleep of sleeps){
      const section=document.createElement('section');section.className='sleep-record';
      const title=document.createElement('h3');title.textContent=sleep.type==='long_sleep'?'Main sleep':sleep.type==='late_nap'?'Nap':sleep.type==='rest'?'Rest':'Sleep period';
      const timing=document.createElement('p');timing.className='small';timing.textContent=`${clock(sleep.bedtime_start)} → ${clock(sleep.bedtime_end)} · Recorded local times`;
      const grid=document.createElement('div');grid.className='sleep-metrics';
      for(const [label,value] of [
        ['Time asleep',duration(sleep.total_sleep_duration)],['Time in bed',duration(sleep.time_in_bed)],
        ['Average HRV',metric(sleep.average_hrv,'ms')],['Lowest sleeping heart rate',metric(sleep.lowest_heart_rate,'bpm')],
        ['Average sleeping heart rate',metric(sleep.average_heart_rate,'bpm')],['Sleep efficiency',metric(sleep.efficiency,'%')],
        ['Deep sleep',duration(sleep.deep_sleep_duration)],['REM sleep',duration(sleep.rem_sleep_duration)],
        ['Light sleep',duration(sleep.light_sleep_duration)],['Awake',duration(sleep.awake_time)],
        ['Time to fall asleep',duration(sleep.latency)],['Breathing rate',metric(sleep.average_breath,'/ min')]
      ]){const box=document.createElement('div');const name=document.createElement('span');name.textContent=label;const val=document.createElement('strong');val.textContent=value;box.append(name,val);grid.append(box);}
      section.append(title,timing,grid);detailPanel.append(section);
    }
  }catch(error){el('oura-stats').textContent=error.message;}
}
async function ouraStatus(){
  const state=await request('/api/oura/status');
  el('oura-redirect').textContent=state.redirect_uri;
  el('oura-connect').textContent=state.connected?'Reconnect Oura':'Connect Oura';
  el('oura-sync').disabled=!state.connected || state.syncing;
  el('oura-disconnect').hidden=!state.connected;
  el('oura-status').textContent=state.error || (state.connected?(state.last_sync?`Last synced ${new Date(state.last_sync).toLocaleString()}. Checks hourly while the app is running.`:'Connected. The first sync will import the past 90 days.'):'Connect your Oura account to import sleep, readiness, and activity.');
  return state;
}
const post=(url,data={})=>request(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
el('oura-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try{await post('/api/oura/setup',{client_id:el('oura-client-id').value,client_secret:el('oura-client-secret').value});el('oura-client-secret').value='';await ouraStatus();el('oura-status').textContent='Settings saved. Click Connect Oura to authorize your account.';}
  catch(error){el('oura-status').textContent=error.message;}
});
el('oura-connect').addEventListener('click',async()=>{
  if(!mayLeave())return;
  try{const state=await ouraStatus();if(!state.configured){el('oura-setup').open=true;el('oura-client-id').focus();return;}const result=await post('/api/oura/connect');window.location.assign(result.url);}
  catch(error){el('oura-status').textContent=error.message;}
});
el('oura-sync').addEventListener('click',async()=>{
  el('oura-sync').disabled=true;el('oura-status').textContent='Fetching Oura summaries…';
  try{const result=await post('/api/oura/sync');await ouraStatus();await loadOuraDay();el('oura-status').textContent+=` Imported or refreshed ${result.imported} summaries.`;}
  catch(error){el('oura-status').textContent=error.message;}
  finally{el('oura-sync').disabled=false;}
});
el('oura-disconnect').addEventListener('click',async()=>{
  try{await post('/api/oura/disconnect');await ouraStatus();}catch(error){el('oura-status').textContent=error.message;}
});
setInterval(()=>{if(!document.hidden && vaultId){ouraStatus().then(state=>{if(state.connected)loadOuraDay();}).catch(()=>{});}},60000);
window.addEventListener('focus',()=>{if(vaultId){loadHistory();ouraStatus().then(()=>loadOuraDay()).catch(()=>{});}});
request('/api/config').then(async config=>{vaultId=config.vault;el('vault').textContent=`Vault: ${config.vault}`;await load();loadHistory();ouraStatus().catch(error=>el('oura-status').textContent=error.message);}).catch(error=>status(error.message,true));



async function loadTaskHistory(){
  try{
    const data=await request('/api/tasks');const panel=el('task-history');panel.replaceChildren();
    if(!data.tasks.length){panel.textContent='Completed tasks will appear here after you save a check-in.';return;}
    for(const task of data.tasks){
      const row=document.createElement('p');const name=document.createElement('strong');name.textContent='✓ '+task.text;
      const dates=document.createElement('small');dates.textContent=`Created ${task.created} · Completed ${task.completed}`;
      row.append(name,document.createElement('br'),dates);panel.append(row);
    }
  }catch(error){el('task-history').textContent=error.message;}
}
