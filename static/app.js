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
  morning: ['How am I feeling this morning?', 'Priority Tasks', 'Secondary Tasks', 'What might get in the way, and what could help?'],
  evening: ['What made me happy or grateful today?', 'When did I feel most engaged or connected today?', 'What am I proud of today?', 'What would I do differently if I replayed today?', 'What moment would I like to remember?', 'What did I learn today—about myself, someone else, or the world?']
};
const hints = {
  morning: ['Notice your mood, energy, sleep, or whatever is on your mind.', 'The tasks that matter most today. Keep the list focused and realistic.', 'Lower-priority tasks to tackle after your priorities, if time and energy allow.', 'Think about practical obstacles, feelings, distractions, or support you might need.'],
  evening: ['A person, a small pleasure, or something that went well.', 'An activity that held your attention, or a moment of connection with someone.', 'An effort, a choice, or how you handled something. Small things count.', 'One thing you might approach differently, knowing what you know now.', 'Capture a detail, a conversation, or a scene you would like to revisit.', 'A discovery, a new perspective, or something you noticed about yourself.']
};
function parsePrompts(text) {
  if(period==='evening')text=JournalPlans.split(text).body;
  else text=JournalPlans.sleep(JournalPlans.upgrade(text)).body;
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
  const prefix=period==='evening'?JournalPlans.serialize(reviewTasks.map((t,i)=>({...t,done:el(`plan-done-${i}`).checked})))+`### Daily ratings\n\nDay satisfaction: ${el('rating-good').value || 'unrated'}\nDay satisfaction scale: 10\nProductive day: ${el('rating-productive').value || 'unrated'}\nProductivity scale: 10\n\n`:'';
  const metadata=period==='morning'?JournalPlans.serializeSleep({
    woke_up:el('woke-up-last-night').checked,
    awake_20_minutes:el('awake-20-minutes').checked,
    awake_1_hour:el('awake-1-hour').checked,
    awake_2_hours:el('awake-2-hours').checked
  }):JournalPlans.serializeHabits({
    phone_game_before_morning_work:el('phone-game-before-morning-work').checked,
    phone_game_before_afternoon_work:el('phone-game-before-afternoon-work').checked,
    caffeine_after_4pm:el('caffeine-after-4pm').checked
  })+JournalPlans.serializeJO({jo:el('jo').checked,worth_it:el('jo-worth').checked,why:el('jo-why').value});
  return (period==='morning'?'<!-- carry-review: '+encodeURIComponent(JSON.stringify(carryChoices))+' -->\n':'')+prefix+parts.map((p,i)=>{
    const answer=period==='morning' && (i===1 || i===2)?[...document.querySelectorAll(`[id^="${i===2?'optional':'plan'}-"].plan-input`)].map(field=>field.value.trim()).filter(Boolean).map(s=>`- ${s}`).join('\n'):el(`answer-${i}`).value.trim();
    return `### ${p.title}\n\n${answer}\n\n`;
  }).join('')+metadata;
}
function showEditor(text, preferGuided=true) {
  // Refresh only an entirely blank old template; preserve answers when upgrading current headings.
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
    const value=JournalPlans.habits(text).value;
    const box=document.createElement('section');box.className='prompt';
    const title=document.createElement('h3');title.textContent='Evening check-in';box.append(title);
    const label=document.createElement('label');label.className='plan-check';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id='caffeine-after-4pm';checkbox.checked=value.caffeine_after_4pm===true;
    checkbox.addEventListener('change',changed);label.append(checkbox,document.createTextNode('Had caffeine after 4 p.m.'));box.append(label);el('plan-review').append(box);
  }
  if(guided && period==='evening'){
    const deferred=JournalPlans.review(entry.sections.morning).choices;
    reviewTasks=JournalPlans.reconcile(JournalPlans.morning(entry.sections.morning),JournalPlans.split(text).tasks).filter(task=>{
      const decision=deferred[entry.date+':'+(task.original || task.text)];
      return decision!=='Deleted' && (task.done || !(typeof decision==='string' && decision.startsWith('Skipped until ') && decision.slice(14)>entry.date));
    });
    const title=document.createElement('h3');title.textContent='How did your plans go?';el('plan-review').append(title);
    const hint=document.createElement('p');hint.className='small';hint.textContent=reviewTasks.length?'Drag the handles or use the arrows to reorder. Check a task and Submit to clear it and save your evening entry.':'No tasks yet. Add an evening task below.';el('plan-review').append(hint);
    const list=document.createElement('div');el('plan-review').append(list);
    const rows=new Map();let dragged=null;
    const refreshOrder=()=>{
      let previousVisible=null;
      reviewTasks.forEach((task,index)=>{
        const row=rows.get(task);list.append(row);
        row.hidden=Boolean(task.deleted || task.submitted && (row.querySelector('input[type=checkbox]').checked || task.cooldown>entry.date));
        row.querySelector('input[type="checkbox"]').id=`plan-done-${index}`;
        const startsGroup=!previousVisible || task.text.startsWith('[If time] ')!==previousVisible.text.startsWith('[If time] ');
        row.querySelector('.plan-category-title').hidden=!startsGroup;
        row.querySelector('hr').hidden=!previousVisible || !startsGroup;
        if(!row.hidden)previousVisible=task;
      });
    };
    const move=(task,index)=>{
      if(busy || index<0 || index>=reviewTasks.length)return;
      const from=reviewTasks.indexOf(task);if(from<0 || from===index)return;
      reviewTasks.splice(from,1);reviewTasks.splice(index,0,task);
      refreshOrder();changed();status('Task order updated. Save your evening entry to keep it.');
    };
    reviewTasks.forEach((task,i)=>{
      const row=document.createElement('div');row.className='evening-task';rows.set(task,row);list.append(row);
      const divider=document.createElement('hr');divider.className='plan-group-divider';row.append(divider);
      const toolbar=document.createElement('div');toolbar.className='task-order';row.append(toolbar);
      const remove=document.createElement('button');remove.type='button';remove.className='task-delete';remove.textContent='×';remove.setAttribute('aria-label','Delete task');
      remove.addEventListener('click',()=>{if(busy || !confirm('Delete this task? It will no longer carry forward. Save your evening entry to keep this change.'))return;task.deleted=true;refreshOrder();changed();});row.append(remove);
      const groupTitle=document.createElement('h4');groupTitle.className='plan-category-title';groupTitle.textContent=task.text.startsWith('[If time] ')?'Secondary Tasks':'Priority Tasks';row.insertBefore(groupTitle,toolbar);
      const handle=document.createElement('button');handle.type='button';handle.textContent='⠿';handle.draggable=true;handle.className='task-drag';handle.setAttribute('aria-label','Drag to reorder task');toolbar.append(handle);
      for(const [symbol,delta,name] of [['↑',-1,'up'],['↓',1,'down']]){
        const button=document.createElement('button');button.type='button';button.textContent=symbol;button.setAttribute('aria-label','Move task '+name);
        button.addEventListener('click',()=>{let target=reviewTasks.indexOf(task)+delta;while(target>=0 && target<reviewTasks.length && rows.get(reviewTasks[target]).hidden)target+=delta;move(task,target);button.focus();});toolbar.append(button);
      }
      handle.addEventListener('dragstart',event=>{
        if(busy){event.preventDefault();return;}
        dragged=task;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain','journal-task');
      });
      handle.addEventListener('dragend',()=>{dragged=null;list.querySelectorAll('.drop-before,.drop-after').forEach(node=>node.classList.remove('drop-before','drop-after'));});
      row.addEventListener('dragover',event=>{
        if(!dragged || dragged===task || busy)return;
        event.preventDefault();event.dataTransfer.dropEffect='move';
        const after=event.clientY>row.getBoundingClientRect().top+row.offsetHeight/2;
        row.classList.toggle('drop-before',!after);row.classList.toggle('drop-after',after);
      });
      row.addEventListener('dragleave',event=>{if(!row.contains(event.relatedTarget))row.classList.remove('drop-before','drop-after');});
      row.addEventListener('drop',event=>{
        row.classList.remove('drop-before','drop-after');if(!dragged || dragged===task || busy)return;event.preventDefault();
        const from=reviewTasks.indexOf(dragged),to=reviewTasks.indexOf(task);
        const after=event.clientY>row.getBoundingClientRect().top+row.offsetHeight/2;
        move(dragged,to+(after?1:0)-(from<to?1:0));dragged=null;
      });
      const label=document.createElement('label');label.className='plan-check';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id=`plan-done-${i}`;checkbox.checked=task.done;checkbox.addEventListener('change',changed);
      const span=document.createElement('span');span.textContent=(task.followup?'Follow-up: ':'')+task.text.replace(/^\[If time\] /,'')+(task.earlier?' (from an earlier version of your morning plans)':'');label.append(checkbox,span);
      const taskLine=document.createElement('div');taskLine.className='task-submit-line';taskLine.append(label);row.append(taskLine);
      const submit=document.createElement('button');submit.type='button';submit.textContent='Submit';submit.title='Save this evening entry and clear a completed task or a task on cooldown';taskLine.append(submit);
      submit.addEventListener('click',async()=>{
        if(busy)return;
        const deferred=!checkbox.checked && task.cooldown>entry.date;
        if(!checkbox.checked && !deferred){status('Check the task as done or set a cooldown before submitting.',true);return;}
        const previous=task.submitted;task.submitted=true;controls(true);status(deferred?'Saving cooldown…':'Saving completion…');
        try{
          const saved=await request('/api/entry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:entry.date,period,content:content(),revision:entry.revision})});
          try{clearDrafts();}catch{}
          entry=saved;draftBase=saved.sections[period];dirty=false;draftStored=false;el('journal-conflict')?.remove();
          submit.textContent=deferred?'✓ Scheduled':'✓ Done';
          await celebrateTask(row,submit);
          refreshOrder();status(saved.warning || (deferred?'Task put away until '+task.cooldown+'. It is still unfinished.':'Completed! Evening entry saved. Find this task in Completed tasks.'),Boolean(saved.warning));loadHistory();
        }catch(error){
          task.submitted=previous;
          if(error.status===409){try{showConflict(await request(`/api/entry?date=${encodeURIComponent(entry.date)}`));}catch(refreshError){status(refreshError.message,true);}}
          else status(error.message,true);
        }finally{controls(false);}
      });
      const cooldown=document.createElement('details');cooldown.className='task-cooldown';
      const cooldownTitle=document.createElement('summary');cooldownTitle.textContent=task.cooldown?'On cooldown until '+task.cooldown:'Do later';cooldown.append(cooldownTitle);row.append(cooldown);
      const dateInput=document.createElement('input');dateInput.type='date';dateInput.setAttribute('aria-label','Bring task back on');
      const tomorrow=new Date(entry.date+'T12:00:00Z');tomorrow.setUTCDate(tomorrow.getUTCDate()+1);dateInput.min=tomorrow.toISOString().slice(0,10);dateInput.value=task.cooldown || dateInput.min;
      const days=document.createElement('input');days.type='number';days.min='1';days.max='3650';days.value='1';days.setAttribute('aria-label','Days to skip');
      const setDays=count=>{const date=new Date(entry.date+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+count);dateInput.value=date.toISOString().slice(0,10);};
      for(const [label,count] of [['Tomorrow',1],['In a week',7]]){const button=document.createElement('button');button.type='button';button.textContent=label;button.addEventListener('click',()=>setDays(count));cooldown.append(button);}
      days.addEventListener('input',()=>{if(days.validity.valid && days.value)setDays(Number(days.value));});cooldown.append(days,dateInput);
      const apply=document.createElement('button');apply.type='button';apply.textContent='Save cooldown';cooldown.append(apply);
      const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Clear cooldown';cooldown.append(cancel);
      const saveCooldown=async value=>{
        if(busy)return;
        if(value && (!dateInput.validity.valid || value<=entry.date)){status('Choose a date after this journal day.',true);return;}
        if(checkbox.checked && value){status('Uncheck this task before putting it on cooldown.',true);return;}
        const previous=task.cooldown;task.cooldown=value;controls(true);
        try{
          const saved=await request('/api/entry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:entry.date,period,content:content(),revision:entry.revision})});
          try{clearDrafts();}catch{}entry=saved;draftBase=saved.sections[period];dirty=false;draftStored=false;
          cooldownTitle.textContent=value?'On cooldown until '+value:'Do later';cooldown.open=false;
          row.classList.toggle('on-cooldown',Boolean(value));status(saved.warning || (value?'Evening saved. This task will return to morning carry-forward on '+value+'.':'Evening saved. Cooldown cleared.'),Boolean(saved.warning));loadHistory();
        }catch(error){task.cooldown=previous;if(error.status===409){try{showConflict(await request(`/api/entry?date=${encodeURIComponent(entry.date)}`));}catch(refreshError){status(refreshError.message,true);}}else status(error.message,true);}
        finally{controls(false);}
      };
      apply.addEventListener('click',()=>saveCooldown(dateInput.value));cancel.addEventListener('click',()=>saveCooldown(null));row.classList.toggle('on-cooldown',Boolean(task.cooldown));
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
        const ratings=`### Daily ratings\n\nDay satisfaction: ${parsed.ratings.good || 'unrated'}\nDay satisfaction scale: 10\nProductive day: ${parsed.ratings.productive || 'unrated'}\nProductivity scale: 10\n\n`;
        showEditor(JournalPlans.serialize(reviewTasks)+ratings+parsed.body+JournalPlans.serializeHabits(JournalPlans.habits(current).value)+JournalPlans.serializeJO(JournalPlans.jo(current).value));changed();
        status('Follow-up added. Save your evening entry to keep it and include it in the next carry-forward review.');
      });tools.append(add);row.append(tools);

    });
    refreshOrder();
  }
  if(guided && period==='evening'){
    const addSection=document.createElement('div');addSection.className='evening-add';
    const title=document.createElement('h3');title.textContent='Add an evening task';addSection.append(title);
    for(const [category,prefix] of [['Priority Tasks',''],['Secondary Tasks','[If time] ']]){
      const row=document.createElement('div');row.className='optional-plan-row';
      const input=document.createElement('input');input.type='text';input.maxLength=1000;input.className='plan-input';input.placeholder=category;input.setAttribute('aria-label','New evening task: '+category);
      const button=document.createElement('button');button.type='button';button.textContent='+ Add to '+category.toLowerCase();
      const addTask=()=>{
        if(busy || !input.value.trim())return;
        const taskText=prefix+input.value.trim(),current=content(),parsed=JournalPlans.split(current);
        if(parsed.tasks.some(task=>task.text.toLowerCase()===taskText.toLowerCase())){status('That task is already in this checklist.',true);return;}
        parsed.tasks.push({text:taskText,original:taskText,done:false,eveningAdded:true});
        const ratings=`### Daily ratings\n\nDay satisfaction: ${parsed.ratings.good || 'unrated'}\nDay satisfaction scale: 10\nProductive day: ${parsed.ratings.productive || 'unrated'}\nProductivity scale: 10\n\n`;
        showEditor(JournalPlans.serialize(parsed.tasks)+ratings+parsed.body+JournalPlans.serializeHabits(JournalPlans.habits(current).value)+JournalPlans.serializeJO(JournalPlans.jo(current).value));changed();
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
    for(const [key,question] of [['good','How satisfying was today overall?'],['productive','Was this a productive day? Grade on a curve for weekends']]){
      const label=document.createElement('label');label.className='rating-label';label.textContent=question;
      const select=document.createElement('select');select.id=`rating-${key}`;
      const blank=document.createElement('option');blank.value='';blank.textContent='Not rated';select.append(blank);
      const options=key==='good'
        ? [['1','Awful — overwhelmingly negative'],['2','Very difficult — little felt good'],['3','Difficult — more bad than good'],['4','Below average — noticeably unsatisfying'],['5','Mixed — good and bad felt balanced'],['6','Decent — somewhat satisfying'],['7','Good — clearly positive'],['8','Very good — happy and fulfilling'],['9','Excellent — deeply satisfying'],['10','Exceptional — about as good as a day gets']]
        : [['1','No meaningful progress'],['2','Minimal progress'],['3','A little progress'],['4','Some progress'],['5','Moderate progress'],['6','Solid progress'],['7','Productive'],['8','Very productive'],['9','Highly productive'],['10','Exceptional progress']];
      for(const [score,description] of options){const option=document.createElement('option');option.value=score;option.textContent=`${score} — ${description}`;select.append(option);}
      select.value=ratings[key] || '';select.addEventListener('change',changed);label.append(select);el('plan-review').append(label);
    }
  }
  if(period==='morning' && yesterdayReflection){
    const reflection=document.createElement('section');reflection.className='prompt';
    const title=document.createElement('h3');title.textContent='From yesterday: what I would do differently';
    const answer=document.createElement('p');answer.textContent=yesterdayReflection;answer.style.whiteSpace='pre-wrap';reflection.append(title,answer);el('guided').append(reflection);
  }
  if(guided && period==='morning'){
    const value=JournalPlans.sleep(text).value;
    const box=document.createElement('section');box.className='prompt';
    const title=document.createElement('h3');title.textContent='Sleep interruption';box.append(title);
    const hint=document.createElement('p');hint.className='small';hint.textContent='Check what happened last night. Longer durations also count as the shorter thresholds.';box.append(hint);
    const options=[
      ['woke-up-last-night','woke_up','Woke up during the night'],
      ['awake-20-minutes','awake_20_minutes','Awake for 20+ minutes'],
      ['awake-1-hour','awake_1_hour','Awake for 1+ hour'],
      ['awake-2-hours','awake_2_hours','Awake for 2+ hours']
    ];
    const checkboxes=[];
    for(const [id,key,labelText] of options){
      const label=document.createElement('label');label.className='plan-check';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id=id;checkbox.checked=value[key]===true;
      checkbox.addEventListener('change',()=>{
        const index=checkboxes.indexOf(checkbox);
        if(index===0 && !checkbox.checked)checkboxes.slice(1).forEach(item=>item.checked=false);
        else if(index>0){if(checkbox.checked)checkboxes.slice(0,index).forEach(item=>item.checked=true);else checkboxes.slice(index+1).forEach(item=>item.checked=false);}
        changed();
      });
      checkboxes.push(checkbox);label.append(checkbox,document.createTextNode(labelText));box.append(label);
    }
    el('guided').append(box);
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
      if(i===2)hint.textContent='Lower-priority tasks to tackle after your priorities, if time and energy allow. Add as many as you need.';
      group.append(label,hint);const plans=JournalPlans.items(part.answer);
      for(let n=0;n<(i===2?Math.max(1,plans.length):Math.max(4,plans.length));n++){
        const field=document.createElement('input');field.type='text';field.id=`${fieldPrefix}-${n}`;field.value=plans[n] || '';field.placeholder=`Entry ${n+1}`;field.setAttribute('aria-label',`${i===2?'Secondary':'Priority'} task ${n+1}`);field.setAttribute('aria-describedby',hint.id);field.className='plan-input';field.hidden=i===2 && n>=Math.max(1,plans.length);field.addEventListener('input',changed);group.append(i===2?optionalPlanRow(field):morningTaskRow(field));
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
    const value=JournalPlans.habits(text).value;
    const box=document.createElement('section');box.className='prompt';
    const title=document.createElement('h3');title.textContent='Phone and game time';box.append(title);
    for(const [id,key,labelText] of [
      ['phone-game-before-morning-work','phone_game_before_morning_work','Phone/Game Time Before Morning Work'],
      ['phone-game-before-afternoon-work','phone_game_before_afternoon_work','Phone/Game Time Before Afternoon Work']
    ]){
      const label=document.createElement('label');label.className='plan-check';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.id=id;checkbox.checked=value[key]===true;
      checkbox.addEventListener('change',changed);label.append(checkbox,document.createTextNode(labelText));box.append(label);
    }
    el('guided').append(box);
  }
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
function morningTaskRow(field,optional=false){
  const row=document.createElement('div');row.className='morning-task';row.append(field);
  const remove=document.createElement('button');remove.type='button';remove.className='task-delete';remove.textContent='×';remove.setAttribute('aria-label','Delete task');
  remove.addEventListener('click',()=>{
    if(busy || !confirm('Delete this task? It will no longer carry forward. Save your morning entry to keep this change.'))return;
    const text=(optional?'[If time] ':'')+field.value.trim();
    if(field.value.trim())carryChoices[entry.date+':'+text]='Deleted';
    row.remove();changed();
  });row.append(remove);return row;
}
function optionalPlanRow(field){
  const row=morningTaskRow(field,true);row.classList.add('optional-plan-row');
  const label=document.createElement('label');label.className='do-later-label';
  const check=document.createElement('input');check.type='checkbox';check.className='do-later-check';label.append(check,document.createTextNode('Do Later'));
  const calendar=document.createElement('input');calendar.type='date';calendar.className='do-later-date';calendar.setAttribute('aria-label','Return date for '+(field.value || 'secondary task'));
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
  const n=Math.max(-1,...[...document.querySelectorAll(`[id^="${prefix}-"].plan-input`)].map(field=>Number(field.id.split("-").at(-1))))+1;
  const field=document.createElement('input');field.type='text';field.id=`${prefix}-${n}`;
  field.placeholder=`Entry ${n+1}`;field.className='plan-input';
  field.setAttribute('aria-label',`${prefix==='optional'?'Secondary':'Priority'} task ${n+1}`);field.setAttribute('aria-describedby',prefix==='optional'?'answer-hint-2':'answer-hint-1');
  field.addEventListener('input',changed);el('add-'+prefix).before(prefix==='optional'?optionalPlanRow(field):morningTaskRow(field));
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
    if(carryChoices[key]==='Deleted')continue;
    const row=document.createElement('div');row.className='carry-row';
    const label=document.createElement('p');label.textContent=text;row.append(label);
    if(!carryChoices[key]){
      const remove=document.createElement('button');remove.type='button';remove.className='task-delete';remove.textContent='×';remove.setAttribute('aria-label','Dismiss carried-over task without completing it');
      remove.addEventListener('click',()=>{if(busy || !confirm('Dismiss this task without completing it? Save your morning entry to keep this change.'))return;carryChoices[key]='Deleted';changed();renderCarryover();});row.append(remove);
    }
    const doneLabel=document.createElement('label');doneLabel.className='plan-check';
    const done=document.createElement('input');done.type='checkbox';done.checked=carryChoices[key]==='Completed';
    done.disabled=busy || String(carryChoices[key] || '').startsWith('Added');
    const doneText=document.createElement('span');doneText.textContent='Already done';doneLabel.append(done,doneText);row.append(doneLabel);
    done.addEventListener('change',()=>{if(busy)return;if(done.checked)carryChoices[key]='Completed';else delete carryChoices[key];changed();renderCarryover();});
    if(carryChoices[key]){const result=document.createElement('span');result.textContent=String(carryChoices[key]).replace('Added to good-day plans','Added to Priority Tasks').replace('Added to if-time','Added to Secondary Tasks');row.append(result);}
    else for(const [action,prefix] of [['Add to Priority Tasks','plan'],['Add to Secondary Tasks','optional'],['Skip today',null],['Skip for a week','week'],['Skip for n days','custom']]){
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
        carryChoices[key]=prefix?`Added to ${prefix==='plan'?'Priority Tasks':'Secondary Tasks'}`:'Skipped today';
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
    for(const [metric,title] of [['good','Day satisfaction'],['productive','Productive']]){
      const cell=document.createElement('div');cell.className=metric;const value=row?.[metric];
      const text=document.createElement('span');text.textContent=`${title}: ${value ?? '—'}`;cell.append(text);
      if(value!=null){const max=10;const bar=document.createElement('progress');bar.max=max;bar.value=value;bar.setAttribute('aria-label',`${date} ${title}: ${value} out of ${max}`);cell.append(bar);}line.append(cell);
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

async function celebrateTask(row,button){
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const bounds=button.getBoundingClientRect(),burst=document.createElement('div');burst.className='completion-burst';burst.setAttribute('aria-hidden','true');document.body.append(burst);
  const animations=[];
  try{
    for(let i=0;i<18;i++){
      const bit=document.createElement('i');burst.append(bit);const angle=i*Math.PI*2/18,distance=45+Math.random()*55;
      bit.style.cssText=`left:${bounds.left+bounds.width/2}px;top:${bounds.top+bounds.height/2}px;background:${['#55b88a','#e5b95c','#87c9df','#a698d5'][i%4]};border-radius:${i%2?'50%':'2px'}`;
      animations.push(bit.animate([{opacity:0,transform:'scale(0)'},{offset:.15,opacity:1,transform:'scale(1.2)'},{opacity:0,transform:`translate(${Math.cos(angle)*distance}px,${Math.sin(angle)*distance+25}px) rotate(${i*55}deg) scale(.4)`}],{duration:700,easing:'cubic-bezier(.15,.7,.3,1)'}));
    }
    animations.push(button.animate([{transform:'scale(1)'},{transform:'scale(1.22)',offset:.35},{transform:'scale(1)'}],{duration:380,easing:'ease-out'}));
    await row.animate([{transform:'scale(1)',opacity:1},{offset:.28,transform:'scale(1.018)',backgroundColor:'#dcebdd',opacity:1},{offset:.55,transform:'scale(.99)',opacity:1},{transform:'scale(.92) translateY(-8px)',opacity:0}],{duration:650,easing:'ease-in-out'}).finished;
    await row.animate([{height:row.offsetHeight+'px',opacity:0,overflow:'hidden'},{height:'0px',opacity:0,overflow:'hidden'}],{duration:180,easing:'ease-out'}).finished;
  }catch{}finally{animations.forEach(animation=>animation.cancel());burst.remove();}
}
