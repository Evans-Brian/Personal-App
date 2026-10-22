/* Private Oura dashboard. All analysis and rendering run on this computer. */
(() => {
  const $=id=>document.getElementById(id);
  const colors={asleep:'#355977',awake:'#b67c30',onset:'#7e8fbb',wake:'#345b47',hrv:'#7e8fbb',deep:'#355977',light:'#b5cbd2',rem:'#7e8fbb'};
  let data=null, selected=null, visibleNights=60, loading=0, polling=null;
  const node=(tag,text,cls)=>{const item=document.createElement(tag);if(text!=null)item.textContent=text;if(cls)item.className=cls;return item;};
  const valid=value=>typeof value==='number' && Number.isFinite(value);
  const duration=value=>valid(value)?`${Math.floor(Math.round(value)/60)}h ${Math.round(value)%60}m`:'—';
  const mins=value=>valid(value)?`${Math.round(value)}m`:'—';
  const metric=(value,unit='')=>valid(value)?`${Number(value.toFixed(1))}${unit}`:'—';
  const clock=value=>typeof value==='string'?clockNumber(Number(value.slice(11,13))*60+Number(value.slice(14,16))):'—';
  const clockNumber=value=>{if(!valid(value))return '—';const time=((Math.round(value)%1440)+1440)%1440,h=Math.floor(time/60);return `${h%12||12}:${String(time%60).padStart(2,'0')} ${h<12?'a.m.':'p.m.'}`;};
  const dateKey=value=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
  const svgNode=(tag,attrs={},text)=>{const item=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))item.setAttribute(key,String(value));if(text!=null)item.textContent=text;return item;};
  async function api(url,body){const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const value=await response.json();if(!response.ok)throw Error(value.error||'Sleep data could not load.');return value;}
  function legend(parent,series){const box=node('div',null,'sleep-legend');for(const line of series){const label=node('span',line.name);label.style.setProperty('--color',line.color);box.append(label);}parent.append(box);}
  function chart(target,rows,series,{format=String,zero=true,label='Sleep trend',x='day'}={}){
    target.replaceChildren();legend(target,series);
    const values=rows.flatMap(row=>series.map(line=>row[line.key])).filter(valid);
    if(!values.length){target.append(node('p','No measurements for this range.','sleep-empty'));return;}
    const w=620,h=230,l=57,r=12,t=15,b=32,plotW=w-l-r,plotH=h-t-b;
    let min=zero?Math.min(0,...values):Math.floor(Math.min(...values)/30)*30,max=zero?Math.max(...values)*1.08:Math.ceil(Math.max(...values)/30)*30;
    if(max===min)max=min+1;
    const svg=svgNode('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':label,class:'sleep-svg'});
    const dates=rows.map(row=>new Date(row[x]+'T12:00:00Z').getTime());
    const xMin=Math.min(...dates),xMax=Math.max(...dates),px=index=>l+(xMax===xMin?plotW/2:(dates[index]-xMin)/(xMax-xMin)*plotW),py=value=>t+(max-value)/(max-min)*plotH;
    for(let i=0;i<=4;i++){const value=min+(max-min)*i/4,y=py(value);svg.append(svgNode('line',{x1:l,x2:w-r,y1:y,y2:y,class:'grid'}),svgNode('text',{x:l-8,y:y+4,'text-anchor':'end'},format(value)));}
    for(const index of [...new Set([0,Math.floor((rows.length-1)/2),rows.length-1])]){svg.append(svgNode('text',{x:px(index),y:h-6,'text-anchor':index===0?'start':index===rows.length-1?'end':'middle'},rows[index][x].slice(5)));}
    for(const line of series){let path='',previous=-1;
      rows.forEach((row,index)=>{const value=row[line.key];if(!valid(value)){previous=-1;return;}path+=`${previous<0 || dates[index]-dates[previous]>129600000?'M':'L'}${px(index)},${py(value)} `;previous=index;const dot=svgNode('circle',{cx:px(index),cy:py(value),r:2.4,fill:line.color});dot.append(svgNode('title',{},`${row[x]} · ${line.name}: ${format(value)}`));svg.append(dot);});
      svg.append(svgNode('path',{d:path,stroke:line.color}));
    }
    target.append(svg,node('p','Hover over points for values. Gaps indicate missing nights.','sleep-chart-caption'));
  }
  function overview(){const box=$('sleep-overview');box.replaceChildren();const s=data.summary;
    for(const [name,value,detail] of [
      ['Typical bedtime',clockNumber(s.bedtime_clock.median),`Median · ${s.bedtime_clock.n} nights`],
      ['Estimated sleep onset',clockNumber(s.onset_clock.median),`Median · ${s.onset_clock.n} nights`],
      ['Typical final wake',clockNumber(s.wake_clock.median),`Median · ${s.wake_clock.n} nights`],
      ['Time asleep',duration(s.asleep_minutes.median),`Median · ${s.asleep_minutes.n} nights`],
      ['Awake during sleep',mins(s.waso_minutes.median),`Median between first and last sleep · ${s.waso_minutes.n} nights`],
      ['Total awake in bed',mins(s.awake_minutes.median),`Median including night’s edges · ${s.awake_minutes.n} nights`]
    ]){const item=node('div');item.append(node('span',name),node('strong',value),node('small',detail));box.append(item);}
  }
  function timeline(){const container=$('sleep-timeline');container.replaceChildren();const inner=node('div',null,'sleep-timeline-inner');
    // Fit the actual night intervals, anchored to the noon before bedtime.
    const left=960,right=2400;const axis=node('div',null,'sleep-axis');for(let hour=16;hour<=40;hour+=4)axis.append(node('span',clockNumber(hour*60)));inner.append(axis);
    for(const night of [...data.nights].reverse().slice(0,visibleNights)){
      const button=node('button',null,'sleep-night-row');button.type='button';button.setAttribute('aria-pressed',String(night.id===selected));button.setAttribute('aria-label',`Inspect sleep on ${night.day}`);button.append(node('span',night.day.slice(5)));
      const track=node('span',null,'sleep-track'),base=night.bedtime_clock;
      const runs=night.stages.length?night.stages:[{stage:'unknown',start_seconds:0,end_seconds:night.in_bed_minutes*60}];
      for(const run of runs){const start=base+run.start_seconds/60,end=base+run.end_seconds/60,clippedStart=Math.max(left,start),clippedEnd=Math.min(right,end);if(clippedEnd<=clippedStart)continue;
        const stage={'1':'deep','2':'light','3':'rem','4':'awake'}[run.stage];const segment=node('span',null,'sleep-segment'+(stage?' stage-'+stage:''));segment.style.left=`${(clippedStart-left)/(right-left)*100}%`;segment.style.width=`${(clippedEnd-clippedStart)/(right-left)*100}%`;segment.title=`${night.day} · ${stage||'In bed; stages unavailable'} · ${clockNumber(start)}–${clockNumber(end)}`;track.append(segment);
      }
      button.append(track);button.addEventListener('click',()=>selectNight(night.id,true));inner.append(button);
    }
    container.append(inner);$('sleep-timeline-more').hidden=visibleNights>=data.nights.length;
  }
  function selectNight(id,scroll=false){selected=id;$('sleep-night').value=id;renderNight();timeline();if(scroll)$('sleep-night-detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
  function nightMetrics(parent,values){const box=node('div',null,'sleep-night-metrics');for(const [name,value] of values){const item=node('div');item.append(node('span',name),node('strong',value));box.append(item);}parent.append(box);}
  function samples(target,night,key,title,color){const value=night.samples[key];
    if(!value || !Array.isArray(value.items) || !valid(value.interval)){target.append(node('p',`No ${title} samples for this period.`,'small'));return;}
    const w=600,h=180,l=40,t=14,b=28,values=value.items.filter(valid);if(!values.length){target.append(node('p',`No ${title} samples for this period.`,'small'));return;}
    const min=Math.max(0,Math.min(...values)-5),max=Math.max(...values)+5,svg=svgNode('svg',{viewBox:`0 0 ${w} ${h}`,class:'sleep-svg',role:'img','aria-label':`${title} through the night`});let path='',previous=false;
    value.items.forEach((v,index)=>{if(!valid(v)){previous=false;return;}const x=l+index/Math.max(value.items.length-1,1)*(w-l-10),y=t+(max-v)/(max-min)*(h-t-b);path+=`${previous?'L':'M'}${x},${y} `;previous=true;});
    svg.append(svgNode('path',{d:path,stroke:color}),svgNode('text',{x:0,y:t+5},Math.round(max)),svgNode('text',{x:0,y:h-b},Math.round(min)),svgNode('text',{x:l,y:h-5},clock(value.timestamp||night.bedtime)),svgNode('text',{x:w-10,y:h-5,'text-anchor':'end'},clock(new Date(Date.parse(value.timestamp||night.bedtime)+(value.items.length-1)*value.interval*1000).toISOString())));
    // Last axis label uses the recorded offset, not the viewer device's timezone.
    const base=clockNumber(Number((value.timestamp||night.bedtime).slice(11,13))*60+Number((value.timestamp||night.bedtime).slice(14,16))+(value.items.length-1)*value.interval/60);svg.lastChild.textContent=base;
    target.append(node('h3',title),svg);
  }
  function renderNight(){const box=$('sleep-night-detail');box.replaceChildren();const night=data.nights.find(item=>item.id===selected);if(!night){box.append(node('p','Choose a night with a main sleep session.','sleep-empty'));return;}
    box.append(node('p',`${night.day} · ${night.stage_resolution_seconds?night.stage_resolution_seconds+'-second stages':'Stages unavailable'} · ${night.period_count} recorded sleep period${night.period_count===1?'':'s'}`,'small'));
    nightMetrics(box,[['In bed',clock(night.bedtime)],['Estimated sleep onset',clock(night.onset)],['Final wake',clock(night.final_wake)],['Out of bed',clock(night.out_of_bed)],['Time asleep',duration(night.asleep_minutes)],['Time to fall asleep',mins(night.latency_minutes)],['Awake during sleep',mins(night.waso_minutes)],['Longest awakening',mins(night.longest_wake_minutes)],['Awakenings ≥5 min',metric(night.awakenings_5m)],['Total awake in bed',mins(night.awake_minutes)],['Sleep efficiency',metric(night.efficiency,'%')],['Sleep score',metric(night.sleep_score,' / 100')],['Average HRV',metric(night.hrv,' ms')],['Average heart rate',metric(night.heart_rate,' bpm')],['Lowest heart rate',metric(night.lowest_heart_rate,' bpm')],['Breathing rate',metric(night.breathing_rate,' / min')],['SpO₂ average',metric(night.spo2,'%')],['Breathing disturbance index',metric(night.breathing_disturbance_index)],['Temperature deviation',metric(night.temperature_deviation,' °C')],['Restless periods',metric(night.restless_periods)]]);
    const warnings=[];if(night.low_battery)warnings.push('Oura flagged a low battery.');if(night.offset_changed)warnings.push('The UTC offset changed during this session. Stage times retain the starting offset.');if(night.main_period_count>1)warnings.push('Multiple main-sleep sessions: nightly trends use the longest; other sessions are listed below.');if(!night.stages.length)warnings.push('Usable stages are missing. Awakening timings are unknown.');if(warnings.length)box.append(node('p',warnings.join(' '),'small'));
    box.append(node('h3','Overnight awakenings lasting at least five minutes'));
    const events=night.awakenings.filter(item=>item.minutes>=5);
    if(!events.length)box.append(node('p',night.waso_minutes===null?'No usable sleep-stage series.':'No continuous awake interval of five minutes detected between first and last sleep.','small'));
    for(const event of events){const row=node('div',null,'sleep-event');row.append(node('strong',`${clock(event.start)}–${clock(event.end)}`),node('span',duration(event.minutes)));box.append(row);}
    const clusters=night.disrupted_windows.filter(item=>item.span_minutes>item.awake_minutes);
    if(clusters.length){box.append(node('h3','Long disrupted stretches with brief sleep between awakenings'));box.append(node('p','These group awake episodes separated by at most five minutes of detected sleep. The entire stretch is not counted as awake.','small'));for(const item of clusters){const row=node('div',null,'sleep-event');row.append(node('strong',`${clock(item.start)}–${clock(item.end)}`),node('span',`${mins(item.awake_minutes)} awake across ${mins(item.span_minutes)}`));box.append(row);}}
    const reported=night.reported_sleep;box.append(node('p',`Evening caffeine log (${night.caffeine_day}): ${night.caffeine_after_4pm===null?'unknown':night.caffeine_after_4pm?'after 4 p.m.':'none after 4 p.m.'}. Morning self-report: ${Object.keys(reported).length?Object.entries(reported).filter(([,v])=>v===true).map(([key])=>({woke_up:'woke up',awake_20_minutes:'20+ minutes',awake_30_minutes:'30+ minutes (older option)',awake_1_hour:'1+ hour',awake_2_hours:'2+ hours'}[key]||key)).join(', ')||'no interruptions checked':'not logged'}.`,'small'));
    const curves=node('div',null,'sleep-physiology-night');for(const [key,title,color] of [['heart_rate','Heart rate (bpm)',colors.asleep],['hrv','HRV (ms)',colors.hrv]]){const cell=node('div');samples(cell,night,key,title,color);curves.append(cell);}box.append(curves);
    const others=data.sessions.filter(item=>item.day===night.day && item.id!==night.id);if(others.length){box.append(node('h3','Other recorded sleep periods'));for(const item of others)box.append(node('p',`${item.type||'Sleep'}: ${clock(item.bedtime)}–${clock(item.out_of_bed)}, ${duration(item.asleep_minutes)} asleep.`,'small'));}
    const rec=night.bedtime_recommendation;if(rec?.recommendation)box.append(node('p','Oura bedtime recommendation: '+rec.recommendation.replaceAll('_',' ')+'.','small'));
    const stress=night.daytime_stress;if(stress)box.append(node('p',`Daytime stress context on ${stress.day}: ${mins(valid(stress.stress_high)?stress.stress_high/60:null)} high stress; ${mins(valid(stress.recovery_high)?stress.recovery_high/60:null)} recovery.`,'small'));
  }
  function table(){const box=$('sleep-table');box.replaceChildren();const table=node('table',null,'sleep-table'),head=node('tr');for(const title of ['Night','Bedtime','Onset','Final wake','Asleep','Awake in bed','Awake during sleep','Longest wake','Latency','Efficiency'])head.append(node('th',title));table.append(head);
    for(const night of [...data.nights].reverse()){const row=node('tr'),cell=node('td'),button=node('button',night.day);button.addEventListener('click',()=>selectNight(night.id,true));cell.append(button);row.append(cell);for(const value of [clock(night.bedtime),clock(night.onset),clock(night.final_wake),duration(night.asleep_minutes),mins(night.awake_minutes),mins(night.waso_minutes),mins(night.longest_wake_minutes),mins(night.latency_minutes),metric(night.efficiency,'%')])row.append(node('td',value));table.append(row);}box.append(table);
  }
  function render(){overview();const choices=$('sleep-night');choices.replaceChildren();for(const night of [...data.nights].reverse()){const option=node('option',night.day);option.value=night.id;choices.append(option);}if(!data.nights.some(item=>item.id===selected))selected=data.nights.at(-1)?.id;choices.value=selected||'';timeline();renderNight();
    const insights=$('sleep-insights');insights.replaceChildren();for(const text of data.insights)insights.append(node('p',text,'sleep-insight'));
    const monthly=node('table',null,'sleep-table'),heading=node('tr');for(const name of ['Month','Nights','Mean asleep','Mean awake during sleep','Mean latency'])heading.append(node('th',name));monthly.append(heading);for(const month of data.monthly){const row=node('tr');for(const value of [month.month,month.n,duration(month.asleep.mean),mins(month.awake.mean),mins(month.latency.mean)])row.append(node('td',value));monthly.append(row);}const monthlyScroll=node('div',null,'sleep-chart-scroll');monthlyScroll.append(monthly);insights.append(monthlyScroll);
    chart($('sleep-duration-chart'),data.nights,[{key:'asleep_minutes',name:'Asleep',color:colors.asleep},{key:'awake_minutes',name:'All awake in bed',color:colors.awake},{key:'waso_minutes',name:'Awake during sleep',color:colors.onset}],{format:v=>`${Math.round(v)}m`,label:'Minutes asleep and awake by night'});
    const timing=data.nights.map(n=>({...n,wake_unwrapped:valid(n.wake_clock)?n.wake_clock+1440:null}));
    chart($('sleep-timing-chart'),timing,[{key:'bedtime_clock',name:'Bedtime',color:colors.asleep},{key:'onset_clock',name:'Onset',color:colors.onset},{key:'wake_unwrapped',name:'Final wake / end',color:colors.wake}],{format:clockNumber,zero:false,label:'Bedtime, estimated sleep onset and final wake by date'});
    chart($('sleep-wake-chart'),data.nights,[{key:'longest_wake_minutes',name:'Longest awakening',color:colors.awake},{key:'latency_minutes',name:'Latency',color:colors.asleep}],{format:v=>`${Math.round(v)}m`,label:'Longest awakening and time to fall asleep in minutes'});
    chart($('sleep-physiology-chart'),data.nights,[{key:'heart_rate',name:'Heart rate (bpm)',color:colors.asleep},{key:'hrv',name:'HRV (ms)',color:colors.hrv}],{format:v=>String(Math.round(v)),label:'Average sleeping heart rate in bpm and HRV in milliseconds'});
    chart($('sleep-stages-chart'),data.nights,[{key:'deep_minutes',name:'Deep',color:colors.deep},{key:'light_minutes',name:'Light',color:colors.light},{key:'rem_minutes',name:'REM',color:colors.rem}],{format:v=>`${Math.round(v)}m`,label:'Deep, light and REM sleep minutes by night'});
    const hours=$('sleep-hours-chart');hours.replaceChildren();const svg=svgNode('svg',{viewBox:'0 0 620 220',role:'img','aria-label':'Awake minutes by local clock hour from awakenings lasting at least five minutes',class:'sleep-svg'}),max=Math.max(1,...data.wake_hours.map(item=>item.awake_minutes));for(const item of data.wake_hours){const x=36+item.hour*24,height=item.awake_minutes/max*165,bar=svgNode('rect',{x,y:185-height,width:17,height,fill:colors.awake});bar.append(svgNode('title',{},`${clockNumber(item.hour*60)}: ${Math.round(item.awake_minutes)} awake minutes`));svg.append(bar);if(item.hour%4===0)svg.append(svgNode('text',{x,y:207},String(item.hour).padStart(2,'0')));}hours.append(svg);table();$('sleep-method').textContent=data.method;
  }
  function range(){const value=$('sleep-range').value,to=new Date();if(value==='custom')return;const from=new Date(to);if(value==='all')from.setFullYear(2015,0,1);else from.setDate(to.getDate()-Number(value)+1);$('sleep-from').value=dateKey(from);$('sleep-to').value=dateKey(to);}
  async function load(){const id=++loading;$('sleep-status').textContent='Loading sleep history…';try{const result=await api(`/api/oura/sleep-analysis?start=${encodeURIComponent($('sleep-from').value)}&end=${encodeURIComponent($('sleep-to').value)}`);if(id!==loading)return;data=result;render();const inventory=data.inventory.find(item=>item.kind==='sleep');$('sleep-status').textContent=`${data.coverage.nights} recorded main-sleep nights · ${data.coverage.stage_nights} with usable stages · ${data.coverage.missing_days} calendar days without a main-sleep record. ${inventory?`Imported sleep history: ${inventory.start} through ${inventory.end}.`:''}`;}catch(error){if(id===loading)$('sleep-status').textContent=error.message;}}
  async function importStatus(){
    try{
      const state=await api('/api/oura/status');$('sleep-import').disabled=state.history_running||!state.connected;
      const names={daily_sleep:'sleep summaries',daily_readiness:'readiness',daily_activity:'activity',sleep:'sleep stages',daily_spo2:'blood oxygen',sleep_time:'bedtime guidance',daily_stress:'daytime stress'};
      const notes=[];
      if(state.error)notes.push('Import stopped: '+state.error);
      if(state.optional_unavailable.length)notes.push('Unavailable with this connection: '+state.optional_unavailable.map(kind=>names[kind]||kind).join(', ')+'.');
      if(state.optional_unavailable.includes('daily_spo2'))notes.push('Use Reconnect Oura on the Journal tab to grant SpO₂ access.');
      if(!state.connected)notes.push('Connect Oura from the Journal tab to import more data.');
      if(state.history_imported_at)notes.push('Full history last checked '+new Date(state.history_imported_at).toLocaleString()+'.');
      $('sleep-connection-status').textContent=notes.join(' ');
      if(state.history_running){$('sleep-status').textContent=`Importing full history: ${names[state.history_progress?.collection]||'starting'} · ${state.history_progress?.records||0} records.`;if(!polling)polling=setInterval(importStatus,4000);}
      else if(polling){clearInterval(polling);polling=null;await load();}
    }catch(error){$('sleep-connection-status').textContent=error.message;}
  }
  $('sleep-import').addEventListener('click',async()=>{try{$('sleep-import').disabled=true;await api('/api/oura/history',{});await importStatus();}catch(error){$('sleep-import').disabled=false;$('sleep-status').textContent=error.message;}});
  $('sleep-apply').addEventListener('click',()=>{visibleNights=60;load();});$('sleep-range').addEventListener('change',()=>{range();if($('sleep-range').value!=='custom')load();});for(const id of ['sleep-from','sleep-to'])$(id).addEventListener('change',()=>{$('sleep-range').value='custom';});$('sleep-night').addEventListener('change',()=>selectNight($('sleep-night').value));$('sleep-timeline-more').addEventListener('click',()=>{visibleNights+=60;timeline();});
  range();window.addEventListener('hashchange',()=>{if(location.hash==='#sleep'){load();importStatus();}});if(location.hash==='#sleep'){load();importStatus();}
})();
