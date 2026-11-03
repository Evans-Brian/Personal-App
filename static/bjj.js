(() => {
  const $=id=>document.getElementById(id), node=(tag,text,className)=>{const item=document.createElement(tag);if(text!=null)item.textContent=text;if(className)item.className=className;return item;};
  let library=null,current=null,segments=[],openToken=0;
  const time=value=>`${Math.floor(Number(value||0)/60)}:${String(Math.floor(Number(value||0)%60)).padStart(2,'0')}`;
  const video=$('bjj-video'),holdRegion=$('bjj-speed-hold'),holdSpeed=$('bjj-hold-speed'),holdIndicator=$('bjj-speed-indicator');
  const player=BJJPlayer.create(video,{status:text=>{$('bjj-video-status').textContent=text;}});
  const fullscreen=$('bjj-fullscreen'),videoWrap=video.closest('.bjj-video-wrap'),exitFullscreen=$('bjj-exit-fullscreen');
  let expanded=false;
  function closeExpanded(restoreFocus=true){
    if(!expanded)return;
    expanded=false;videoWrap.classList.remove('expanded');document.body.classList.remove('bjj-video-expanded');
    videoWrap.removeAttribute('role');videoWrap.removeAttribute('aria-modal');videoWrap.removeAttribute('aria-label');
    exitFullscreen.hidden=true;finishSpeedHold();updateFullscreen();
    if(restoreFocus)fullscreen.focus({preventScroll:true});
  }
  function openExpanded(){
    expanded=true;videoWrap.classList.add('expanded');document.body.classList.add('bjj-video-expanded');
    videoWrap.setAttribute('role','dialog');videoWrap.setAttribute('aria-modal','true');videoWrap.setAttribute('aria-label','Video player');
    exitFullscreen.hidden=false;exitFullscreen.focus({preventScroll:true});updateFullscreen();
    $('bjj-video-status').textContent='';
  }
  function updateFullscreen(){
    const active=Boolean(expanded || document.fullscreenElement || video.webkitDisplayingFullscreen);
    fullscreen.textContent=active?'Exit full screen':'Full screen';
    fullscreen.setAttribute('aria-pressed',String(active));
    fullscreen.disabled=video.readyState<1;
  }
  fullscreen.addEventListener('click',()=>{
    finishSpeedHold();
    if(expanded){closeExpanded();return;}
    try{Promise.resolve(BJJPlayer.fullscreen(video)).catch(openExpanded);}
    catch{openExpanded();}
  });
  exitFullscreen.addEventListener('click',()=>closeExpanded());
  document.addEventListener('keydown',event=>{if(expanded && event.key==='Escape'){event.preventDefault();closeExpanded();}});
  document.addEventListener('focusin',event=>{if(expanded && !videoWrap.contains(event.target))exitFullscreen.focus({preventScroll:true});});
  window.addEventListener('hashchange',()=>closeExpanded(false));
  document.addEventListener('fullscreenchange',updateFullscreen);
  for(const name of ['loadedmetadata','loadstart','webkitbeginfullscreen','webkitendfullscreen'])video.addEventListener(name,updateFullscreen);
  const mobileHoldQuery=matchMedia('(max-width: 750px) and (pointer: coarse)');
  let holdTimer=null,holdSource='',previousRate=1;
  function updateHoldTarget(){holdRegion.style.pointerEvents=mobileHoldQuery.matches?'auto':'none';}
  mobileHoldQuery.addEventListener?.('change',updateHoldTarget);updateHoldTarget();
  try{const saved=localStorage.getItem('bjj:hold-speed');if([...holdSpeed.options].some(option=>option.value===saved))holdSpeed.value=saved;}catch{}
  function updateHoldLabel(){holdIndicator.textContent=`${holdSpeed.value}×`;}
  function beginSpeedHold(source){if(holdSource)return;previousRate=video.playbackRate;video.playbackRate=Number(holdSpeed.value);holdSource=source;holdRegion.classList.add('active');}
  function finishSpeedHold(source=''){clearTimeout(holdTimer);holdTimer=null;if(holdSource&&(!source||holdSource===source)){video.playbackRate=previousRate;holdSource='';holdRegion.classList.remove('active');}}
  function armSpeedHold(event){
    if(event.pointerType!=='touch'||!matchMedia('(max-width: 750px)').matches)return;
    event.preventDefault();finishSpeedHold('pointer');holdRegion.setPointerCapture?.(event.pointerId);
    holdTimer=setTimeout(()=>beginSpeedHold('pointer'),180);
  }
  holdRegion.addEventListener('pointerdown',armSpeedHold);
  for(const name of ['pointerup','pointercancel','lostpointercapture'])holdRegion.addEventListener(name,()=>finishSpeedHold('pointer'));
  holdRegion.addEventListener('contextmenu',event=>event.preventDefault());
  holdSpeed.addEventListener('change',()=>{updateHoldLabel();try{localStorage.setItem('bjj:hold-speed',holdSpeed.value);}catch{}});updateHoldLabel();
  function editableTarget(target){return target instanceof Element&&!!target.closest('input,textarea,select,[contenteditable=true]');}
  document.addEventListener('keydown',event=>{if(event.key.toLowerCase()!=='f'||event.repeat||location.hash!=='#bjj'||editableTarget(event.target)||video.paused||video.ended)return;event.preventDefault();beginSpeedHold('keyboard');});
  document.addEventListener('keyup',event=>{if(event.key.toLowerCase()==='f'&&holdSource==='keyboard'){event.preventDefault();finishSpeedHold('keyboard');}});
  window.addEventListener('blur',()=>finishSpeedHold());
  async function request(url,options){const response=await fetch(url,options);let data;try{data=await response.json();}catch{data={error:'The BJJ service returned an invalid response.'};}if(!response.ok)throw Error(data.error||`Request failed (${response.status}).`);return data;}
  function message(text,error=false){$('bjj-status').textContent=text;$('bjj-status').className=error?'error':'';}
  function seek(seconds){player.seek(seconds);$('bjj-player-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
  async function openVolume(course,item,seconds=null){
    if(!item.present){message('This volume has not been downloaded and validated yet.',true);return;}
    let saved=0;try{saved=Number(localStorage.getItem(`bjj:position:${item.id}`)||0);localStorage.setItem('bjj:last-media',item.id);}catch{}
    const target=seconds==null?saved:Number(seconds)||0,same=current?.item.id===item.id;
    $('bjj-player-panel').hidden=false;$('bjj-note-time').textContent=time(target);
    player.open(`/api/bjj/media/${encodeURIComponent(item.id)}`,target);
    $('bjj-player-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
    if(same)return;
    const token=++openToken;current={course,item};segments=[];
    $('bjj-player-course').textContent=`${course.title} · ${course.instructor}`;$('bjj-player-title').textContent=`Volume ${item.volume}`;$('bjj-note-excerpt').textContent='';
    const chapters=$('bjj-chapters');chapters.replaceChildren(new Option('Start','0'));
    try{
      const transcript=await request(`/api/bjj/transcript?media_id=${encodeURIComponent(item.id)}`);if(token!==openToken)return;
      segments=transcript.segments||[];
      for(const chapter of transcript.chapters||[])chapters.append(new Option(chapter.title||chapter.id,String(chapter.start_seconds||0)));
    }catch{if(token===openToken)$('bjj-note-excerpt').textContent='The transcript could not load. Video playback is still available.';}
  }
  function renderLibrary(){
    const panel=$('bjj-library');panel.replaceChildren();
    for(const course of library.courses){
      const card=node('details',null,'card bjj-course'),heading=node('summary',null,'bjj-course-heading');
      const copy=node('span',null,'bjj-course-copy');
      copy.append(node('strong',course.title,'bjj-course-title'),node('span',`${course.instructor} · ${time(course.duration)} total`,'small'));
      const state=node('span',course.complete?'4 / 4 ready':`${course.volumes.filter(v=>v.present).length} / 4 ready`,'bjj-badge');
      heading.append(copy,state);card.append(heading);
      for(let volume=1;volume<=4;volume++){
        const item=course.volumes.find(value=>value.volume===volume)||{volume,present:false,transcribed:false};
        const row=node('div',null,'bjj-volume'),label=node('div');
        label.append(node('strong',`Volume ${volume}`),node('small',item.present?`${time(item.duration)} · ${item.transcribed?'Transcript ready':'Transcript pending'}`:'Not downloaded'));
        const button=node('button',item.present?(Number(localStorage.getItem(`bjj:position:${item.id}`)||0)>5?'Resume':'Play'):'Unavailable');
        button.disabled=!item.present;button.addEventListener('click',()=>openVolume(course,item));
        row.append(label,button);card.append(row);
      }
      panel.append(card);
    }
  }
  async function load(){try{library=await request('/api/bjj/library');renderLibrary();const select=$('bjj-filter-course');for(const course of library.courses)select.append(new Option(`${course.title} — ${course.instructor}`,course.id));loadNotes();message(library.courses.some(course=>course.complete)?'Your private library is ready.':'Library setup is in progress. Available volumes can be played now.');}catch(error){message(error.message,true);}}
  async function loadAIStatus(){
    const panel=$('bjj-ai-setup'),status=$('bjj-ai-status');
    if(!['127.0.0.1','localhost'].includes(location.hostname)){panel.hidden=true;return;}
    try{const data=await request('/api/bjj/ai-credentials');status.textContent=`TypeSafe: ${data.typesafe_configured?'configured':'not configured'}`;}catch(error){status.textContent=error.message;}
  }
  $('bjj-ai-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,status=$('bjj-ai-status');status.textContent='Saving securely…';
    try{const data=await request('/api/bjj/ai-credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(form)))});form.reset();status.textContent=`Saved. TypeSafe: ${data.typesafe_configured?'configured':'not configured'}`;}catch(error){status.textContent=error.message;}
  });
  async function loadNotes(){const list=$('bjj-notes-list');try{const data=await request('/api/bjj/notes');list.replaceChildren();if(!data.notes.length){list.append(node('p','No notes saved yet.','small'));return;}for(const note of data.notes){const button=node('button',null,'bjj-result');button.type='button';button.append(node('strong',`${note.title} · ${time(note.timestamp)}`),node('span',note.path));button.addEventListener('click',()=>{const course=library.courses.find(c=>c.volumes.some(v=>v.id===note.media_id)),item=course?.volumes.find(v=>v.id===note.media_id);if(course&&item)openVolume(course,item,note.timestamp);});list.append(button);}}catch(error){list.textContent=error.message;}}
  video.addEventListener('timeupdate',()=>{if(!current)return;localStorage.setItem(`bjj:position:${current.item.id}`,String(video.currentTime));$('bjj-note-time').textContent=time(video.currentTime);const segment=segments.find(part=>video.currentTime>=part.start_seconds&&video.currentTime<part.end_seconds);$('bjj-note-excerpt').textContent=segment?.corrected_text||segment?.raw_text||'';});
  for(const name of ['pause','ended','emptied'])video.addEventListener(name,()=>finishSpeedHold());
  $('bjj-chapters').addEventListener('change',event=>seek(event.target.value));
  function searchResultButton(result){
    const button=node('button',null,'bjj-result');button.type='button';
    const label=result.source_type==='bjj_transcript'?`${result.instructor} · Volume ${result.volume} · ${result.section||result.chapter} · ${time(result.start_seconds)}–${time(result.end_seconds)}`:`${result.title} · ${result.source_type==='bjj_training'?'Training journal':'Study note'}`;
    const excerpt=result.excerpt.length>420?`${result.excerpt.slice(0,417).trim()}…`:result.excerpt;
    button.append(node('strong',label),node('span',excerpt));
    button.addEventListener('click',()=>{
      if(result.source_type==='bjj_transcript'||result.source_type==='bjj_note'){const course=library.courses.find(c=>c.id===result.course_id),item=course?.volumes.find(v=>v.id===result.media_id);if(course&&item)openVolume(course,item,result.start_seconds);return;}
      if(result.source_type==='bjj_training'&&result.journal_date)openTrainingForEdit(result.journal_date);
    });
    return button;
  }
  $('bjj-search-form').addEventListener('submit',async event=>{
    event.preventDefault();const results=$('bjj-search-results');results.textContent='Searching…';
    try{
      const params=new URLSearchParams({q:$('bjj-query').value,source:$('bjj-search-source').value,limit:'15'});
      if($('bjj-search-mode').value==='semantic')params.set('semantic','1');
      for(const [field,id] of [['course','bjj-filter-course'],['volume','bjj-filter-volume']])if($(id).value)params.set(field,$(id).value);
      const data=await request(`/api/bjj/search?${params}`);results.replaceChildren();
      if(!data.results.length){results.append(node('p','No matching passages.','small'));return;}
      for(const result of data.results.slice(0,5))results.append(searchResultButton(result));
      const remaining=data.results.slice(5);
      if(remaining.length){
        const more=node('details',null,'bjj-more-results'),summary=node('summary',`Show ${remaining.length} more ranked results`),list=node('div');
        for(const result of remaining)list.append(searchResultButton(result));
        more.append(summary,list);results.append(more);
      }
    }catch(error){results.textContent=error.message;}
  });
  $('bjj-note-form').addEventListener('submit',async event=>{event.preventDefault();if(!current)return;const video=$('bjj-video'),status=$('bjj-note-status');status.textContent='Saving…';try{const data=await request('/api/bjj/note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media_id:current.item.id,timestamp:video.currentTime,excerpt:$('bjj-note-excerpt').textContent,text:$('bjj-note-text').value,tags:$('bjj-note-tags').value.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean)})});$('bjj-note-text').value='';status.textContent=`Saved to ${data.path}.`;loadNotes();}catch(error){status.textContent=error.message;}});
  const trainingForm=$('bjj-training-form'),trainingDate=$('bjj-training-date');
  const trainingTextareas=[...trainingForm.querySelectorAll('textarea')];
  function resizeTrainingTextareas(){
    for(const field of trainingTextareas){
      field.style.overflowY='hidden';
      field.style.resize='none';
      field.style.height='auto';
      field.style.height=`${field.scrollHeight}px`;
    }
  }
  trainingForm.addEventListener('input',event=>{
    if(event.target.matches('textarea'))resizeTrainingTextareas();
  });
  const trainingValues=()=>JSON.stringify(Object.fromEntries(new FormData(trainingForm)));
  const trainingDirty=()=>trainingForm.dataset.loadedValues!==undefined&&trainingValues()!==trainingForm.dataset.loadedValues;
  let loadedTrainingDate='',trainingLoadToken=0;
  async function loadTraining(){
    const day=trainingDate.value,token=++trainingLoadToken,status=$('bjj-training-status');
    try{
      const data=await request(`/api/bjj/training?date=${encodeURIComponent(day)}`);
      if(token!==trainingLoadToken)return;
      for(const input of trainingForm.querySelectorAll('[name]'))input.value=data[input.name]||'';
      resizeTrainingTextareas();
      trainingForm.dataset.revision=data.revision||'';
      trainingForm.dataset.loadedValues=trainingValues();
      loadedTrainingDate=day;
      status.textContent=data.path?`Loaded ${data.path}.`:'';
    }catch(error){if(token===trainingLoadToken){if(loadedTrainingDate)trainingDate.value=loadedTrainingDate;status.textContent=error.message;}}
  }
  async function openTrainingForEdit(day){
    if(trainingDirty()&&!window.confirm('You have unsaved training notes. Leave this draft and open another session?'))return;
    trainingDate.value=day;
    await loadTraining();
    trainingForm.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    trainingDate.focus({preventScroll:true});
  }
  const today=new Date();trainingDate.value=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  trainingDate.addEventListener('change',()=>{
    if(trainingDirty()&&!window.confirm('You have unsaved training notes. Leave this draft and open another date?')){trainingDate.value=loadedTrainingDate;return;}
    loadTraining();
  });
  loadTraining();

  const historyList=$('bjj-history-list'),historyDetail=$('bjj-history-detail');
  let historyEntries=[],historyTotal=0,historySelected='',historyRequestToken=0,historyDetailToken=0;
  const historyMonthOpen=new Map();
  const now=new Date(),currentMonthKey=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const displayDate=day=>new Intl.DateTimeFormat('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'}).format(new Date(`${day}T12:00:00`));
  const detailDate=day=>new Intl.DateTimeFormat('en-US',{month:'long',day:'numeric',year:'numeric'}).format(new Date(`${day}T12:00:00`));
  const monthLabel=day=>new Intl.DateTimeFormat('en-US',{month:'long',year:'numeric'}).format(new Date(`${day}T12:00:00`));
  function renderHistoryList(){
    historyList.replaceChildren();
    if(!historyEntries.length){historyList.append(node('p','No training sessions saved yet.','small'));return;}
    const months=new Map();
    for(const entry of historyEntries){
      const key=entry.date.slice(0,7);
      if(!months.has(key))months.set(key,[]);
      months.get(key).push(entry);
    }
    for(const [key,entries] of months){
      const group=node('details',null,'bjj-history-month-group');
      group.open=historyMonthOpen.get(key)??key===currentMonthKey;
      group.addEventListener('toggle',()=>historyMonthOpen.set(key,group.open));
      group.append(node('summary',monthLabel(entries[0].date),'bjj-history-month'));
      for(const entry of entries){
        const button=node('button',null,'bjj-history-row');button.type='button';button.dataset.date=entry.date;button.setAttribute('aria-pressed',String(entry.date===historySelected));
        const date=node('span',null,'bjj-history-date');date.append(node('strong',String(Number(entry.date.slice(-2)))),node('small',new Intl.DateTimeFormat('en-US',{weekday:'short'}).format(new Date(`${entry.date}T12:00:00`))));
        const copy=node('span',null,'bjj-history-row-copy');copy.append(node('strong',displayDate(entry.date)),node('span',entry.preview));
        if(entry.rating)copy.append(node('small',`Session rating ${entry.rating}/5`,'bjj-history-rating'));
        button.append(date,copy);
        button.addEventListener('click',()=>showHistoryDetail(entry.date,true));group.append(button);
      }
      historyList.append(group);
    }
  }
  async function showHistoryDetail(day,scroll=false){
    const token=++historyDetailToken;historySelected=day;
    for(const row of historyList.querySelectorAll('.bjj-history-row'))row.setAttribute('aria-pressed',String(row.dataset.date===day));
    historyDetail.replaceChildren(node('p','Loading session…','small'));
    try{
      const entry=await request(`/api/bjj/training?date=${encodeURIComponent(day)}`);
      if(token!==historyDetailToken)return;
      historyDetail.replaceChildren();
      const heading=node('div',null,'bjj-history-detail-heading');
      const title=node('h3',detailDate(day));heading.append(title);
      if(entry.rating)heading.append(node('span',`${entry.rating} / 5`,'bjj-history-score'));
      historyDetail.append(heading);
      const sections=[['general_notes','General notes'],['session_goals','Session goals'],['problems','Problems encountered'],['worked','What worked']];
      let filled=0;
      for(const [key,label] of sections){
        if(!entry[key])continue;
        const section=node('section',null,'bjj-history-section');section.append(node('h4',label),node('p',entry[key]));historyDetail.append(section);filled++;
      }
      if(!filled)historyDetail.append(node('p','This session has no written notes.','small'));
      const edit=node('button','Edit this session','bjj-history-edit');edit.type='button';edit.addEventListener('click',()=>openTrainingForEdit(day));historyDetail.append(edit);
      if(scroll&&matchMedia('(max-width: 750px)').matches)historyDetail.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
    }catch(error){if(token===historyDetailToken)historyDetail.replaceChildren(node('p',error.message,'error'));}
  }
  async function loadTrainingHistory(reset=true){
    const token=++historyRequestToken,status=$('bjj-history-status');
    if(reset)historyDetailToken++;
    const params=new URLSearchParams({limit:'20',offset:String(reset?0:historyEntries.length)});
    status.textContent='Loading sessions…';
    try{
      const data=await request(`/api/bjj/training-history?${params}`);
      if(token!==historyRequestToken)return;
      historyEntries=reset?data.entries:historyEntries.concat(data.entries);
      historyTotal=data.total;
      $('bjj-history-count').textContent=`${historyTotal} ${historyTotal===1?'session':'sessions'}`;
      $('bjj-history-more').hidden=historyEntries.length>=historyTotal;
      status.textContent='';
      if(reset&&!historyEntries.some(entry=>entry.date===historySelected))historySelected=historyEntries.find(entry=>entry.date.startsWith(currentMonthKey))?.date||'';
      renderHistoryList();
      if(historySelected&&reset)showHistoryDetail(historySelected);
      if(!historySelected)historyDetail.replaceChildren(node('p',historyTotal?'Open a month and select a session to read it here.':'Saved training sessions will appear here.','small'));
    }catch(error){if(token===historyRequestToken)status.textContent=error.message;}
  }
  $('bjj-history-jump').addEventListener('click',()=>$('bjj-past-sessions').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}));
  $('bjj-history-more').addEventListener('click',()=>loadTrainingHistory(false));
  trainingForm.addEventListener('submit',async event=>{
    event.preventDefault();const status=$('bjj-training-status'),data=Object.fromEntries(new FormData(trainingForm));
    data.date=trainingDate.value;data.revision=trainingForm.dataset.revision||'';status.textContent='Saving…';
    try{
      const result=await request('/api/bjj/training',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
      trainingForm.dataset.revision=result.revision||'';trainingForm.dataset.loadedValues=trainingValues();loadedTrainingDate=data.date;
      status.textContent=`Saved to ${result.path}.`;
      await loadTrainingHistory();
      if(historyEntries.some(entry=>entry.date===data.date))showHistoryDetail(data.date);
    }catch(error){status.textContent=error.message;}
  });
  window.addEventListener('hashchange',()=>{if(location.hash==='#bjj'&&!library){load();loadAIStatus();loadTrainingHistory();}});
  if(location.hash==='#bjj'){load();loadAIStatus();loadTrainingHistory();}
})();
