(() => {
  const $=id=>document.getElementById(id), node=(tag,text,className)=>{const item=document.createElement(tag);if(text!=null)item.textContent=text;if(className)item.className=className;return item;};
  let library=null,current=null,segments=[],active=-1,openToken=0;
  const time=value=>`${Math.floor(Number(value||0)/60)}:${String(Math.floor(Number(value||0)%60)).padStart(2,'0')}`;
  const video=$('bjj-video'),holdRegion=$('bjj-speed-hold'),holdSpeed=$('bjj-hold-speed'),holdIndicator=$('bjj-speed-indicator');
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
  function seek(seconds){const video=$('bjj-video');video.currentTime=Number(seconds)||0;video.play().catch(()=>{});$('bjj-player-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
  function renderTranscript(){const panel=$('bjj-transcript');panel.replaceChildren();if(!segments.length){panel.append(node('p','Transcript is still being prepared.','small'));return;}for(const [index,segment] of segments.entries()){const row=node('button',null,'bjj-segment');row.type='button';row.dataset.index=index;row.dataset.start=segment.start_seconds;const stamp=node('time',time(segment.start_seconds));const text=node('span',segment.corrected_text||segment.raw_text||segment.text||'');row.append(stamp,text);row.addEventListener('click',()=>seek(segment.start_seconds));panel.append(row);}}
  async function openVolume(course,item,seconds=0){if(!item.present){message('This volume has not been downloaded and validated yet.',true);return;}const token=++openToken;current={course,item};segments=[];active=-1;localStorage.setItem('bjj:last-media',item.id);$('bjj-player-panel').hidden=false;$('bjj-player-course').textContent=`${course.title} · ${course.instructor}`;$('bjj-player-title').textContent=`Volume ${item.volume}`;$('bjj-note-excerpt').textContent='';$('bjj-note-time').textContent=time(seconds);renderTranscript();const video=$('bjj-video'),saved=Number(localStorage.getItem(`bjj:position:${item.id}`)||0),target=Number(seconds)||saved||0;let applied=false;const applyStart=()=>{if(applied||token!==openToken)return;applied=true;video.removeEventListener('loadedmetadata',applyStart);video.currentTime=Math.min(target,Math.max(0,video.duration-1));};video.addEventListener('loadedmetadata',applyStart,{once:true});video.src=`/api/bjj/media/${encodeURIComponent(item.id)}`;if(video.readyState>=1)applyStart();
    const transcript=await request(`/api/bjj/transcript?media_id=${encodeURIComponent(item.id)}`);if(token!==openToken)return;segments=transcript.segments||[];active=-1;renderTranscript();const chapters=$('bjj-chapters');chapters.replaceChildren(new Option('Start','0'));for(const chapter of transcript.chapters||[])chapters.append(new Option(chapter.title||chapter.id,String(chapter.start_seconds||0)));
  }
  function renderLibrary(){const panel=$('bjj-library');panel.replaceChildren();for(const course of library.courses){const card=node('section',null,'card bjj-course');const heading=node('div',null,'bjj-course-heading');const copy=node('div');copy.append(node('h2',course.title),node('p',`${course.instructor} · ${time(course.duration)} total`,'small'));const state=node('span',course.complete?'4 / 4 ready':`${course.volumes.filter(v=>v.present).length} / 4 ready`,'bjj-badge');heading.append(copy,state);card.append(heading);for(let volume=1;volume<=4;volume++){const item=course.volumes.find(value=>value.volume===volume)||{volume,present:false,transcribed:false};const row=node('div',null,'bjj-volume');const text=node('div');text.append(node('strong',`Volume ${volume}`),node('small',item.present?`${time(item.duration)} · ${item.transcribed?'Transcript ready':'Transcript pending'}`:'Not downloaded'));const button=node('button',item.present?(Number(localStorage.getItem(`bjj:position:${item.id}`)||0)>5?'Resume':'Play'):'Unavailable');button.disabled=!item.present;button.addEventListener('click',()=>openVolume(course,item));row.append(text,button);card.append(row);}panel.append(card);}}
  async function load(){try{library=await request('/api/bjj/library');renderLibrary();const select=$('bjj-filter-course');for(const course of library.courses)select.append(new Option(`${course.title} — ${course.instructor}`,course.id));loadNotes();message(library.courses.some(course=>course.complete)?'Your private library is ready.':'Library setup is in progress. Available volumes can be played now.');}catch(error){message(error.message,true);}}
  async function loadNotes(){const list=$('bjj-notes-list');try{const data=await request('/api/bjj/notes');list.replaceChildren();if(!data.notes.length){list.append(node('p','No notes saved yet.','small'));return;}for(const note of data.notes){const button=node('button',null,'bjj-result');button.type='button';button.append(node('strong',`${note.title} · ${time(note.timestamp)}`),node('span',note.path));button.addEventListener('click',()=>{const course=library.courses.find(c=>c.volumes.some(v=>v.id===note.media_id)),item=course?.volumes.find(v=>v.id===note.media_id);if(course&&item)openVolume(course,item,note.timestamp);});list.append(button);}}catch(error){list.textContent=error.message;}}
  video.addEventListener('timeupdate',()=>{if(!current)return;localStorage.setItem(`bjj:position:${current.item.id}`,String(video.currentTime));$('bjj-note-time').textContent=time(video.currentTime);let index=segments.findIndex(segment=>video.currentTime>=segment.start_seconds&&video.currentTime<segment.end_seconds);if(index!==active){document.querySelector(`.bjj-segment[data-index="${active}"]`)?.classList.remove('active');active=index;const row=document.querySelector(`.bjj-segment[data-index="${active}"]`);row?.classList.add('active');if(row && !row.matches(':hover,:focus'))row.scrollIntoView({block:'nearest'});$('bjj-note-excerpt').textContent=index>=0?(segments[index].corrected_text||segments[index].raw_text||''):'';}});
  for(const name of ['pause','ended','emptied'])video.addEventListener(name,()=>finishSpeedHold());
  $('bjj-chapters').addEventListener('change',event=>seek(event.target.value));
  $('bjj-search-form').addEventListener('submit',async event=>{
    event.preventDefault();const results=$('bjj-search-results');results.textContent='Searching…';
    try{
      const params=new URLSearchParams({q:$('bjj-query').value,source:$('bjj-search-source').value,limit:'12'});
      if($('bjj-search-mode').value==='semantic')params.set('semantic','1');
      for(const [field,id] of [['course','bjj-filter-course'],['volume','bjj-filter-volume'],['chapter','bjj-filter-chapter']])if($(id).value)params.set(field,$(id).value);
      const data=await request(`/api/bjj/search?${params}`);results.replaceChildren();
      if(!data.results.length){results.append(node('p','No matching passages.','small'));return;}
      for(const result of data.results){
        const button=node('button',null,'bjj-result');button.type='button';
        const label=result.source_type==='bjj_transcript'?`${result.instructor} · Volume ${result.volume} · ${result.section||result.chapter} · ${time(result.start_seconds)}–${time(result.end_seconds)}`:`${result.title} · ${result.source_type==='bjj_training'?'Training journal':'Study note'}`;
        const excerpt=result.excerpt.length>420?`${result.excerpt.slice(0,417).trim()}…`:result.excerpt;
        button.append(node('strong',label),node('span',excerpt));
        button.addEventListener('click',()=>{
          if(result.source_type==='bjj_transcript'||result.source_type==='bjj_note'){const course=library.courses.find(c=>c.id===result.course_id),item=course?.volumes.find(v=>v.id===result.media_id);if(course&&item)openVolume(course,item,result.start_seconds);return;}
          if(result.source_type==='bjj_training'&&result.journal_date){$('bjj-training-date').value=result.journal_date;$('bjj-training-date').dispatchEvent(new Event('change'));$('bjj-training-form').scrollIntoView({behavior:'smooth'});}
        });
        results.append(button);
      }
    }catch(error){results.textContent=error.message;}
  });
  $('bjj-note-form').addEventListener('submit',async event=>{event.preventDefault();if(!current)return;const video=$('bjj-video'),status=$('bjj-note-status');status.textContent='Saving…';try{const data=await request('/api/bjj/note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media_id:current.item.id,timestamp:video.currentTime,excerpt:$('bjj-note-excerpt').textContent,text:$('bjj-note-text').value,tags:$('bjj-note-tags').value.split(',').map(x=>x.trim().toLowerCase()).filter(Boolean)})});$('bjj-note-text').value='';status.textContent=`Saved to ${data.path}.`;loadNotes();}catch(error){status.textContent=error.message;}});
  async function loadTraining(){const form=$('bjj-training-form'),status=$('bjj-training-status');try{const data=await request(`/api/bjj/training?date=${encodeURIComponent($('bjj-training-date').value)}`);for(const input of form.querySelectorAll('[name]'))input.value=data[input.name]||'';status.textContent=data.path?`Loaded ${data.path}.`:'';}catch(error){status.textContent=error.message;}}
  const today=new Date();$('bjj-training-date').value=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;$('bjj-training-date').addEventListener('change',loadTraining);loadTraining();$('bjj-training-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,status=$('bjj-training-status'),data=Object.fromEntries(new FormData(form));data.date=$('bjj-training-date').value;status.textContent='Saving…';try{const result=await request('/api/bjj/training',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});status.textContent=`Saved to ${result.path}.`;}catch(error){status.textContent=error.message;}});
  window.addEventListener('hashchange',()=>{if(location.hash==='#bjj'&&!library)load();});if(location.hash==='#bjj')load();
})();
