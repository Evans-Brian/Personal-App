/* Private Oura dashboard. All analysis and rendering run on this computer. */
(() => {
  const $=id=>document.getElementById(id);
  const colors={asleep:'#355977',awake:'#b67c30',onset:'#7e8fbb',wake:'#345b47',hrv:'#7e8fbb',deep:'#355977',light:'#b5cbd2',rem:'#7e8fbb'};
  let data=null, selected=null, visibleNights=60, loading=0, polling=null, analysisStart=null;
  const node=(tag,text,cls)=>{const item=document.createElement(tag);if(text!=null)item.textContent=text;if(cls)item.className=cls;return item;};
  const valid=value=>typeof value==='number' && Number.isFinite(value);
  const duration=value=>valid(value)?`${Math.floor(Math.round(value)/60)}h ${Math.round(value)%60}m`:'—';
  const mins=value=>valid(value)?`${Math.round(value)}m`:'—';
  const awakeningNote=night=>night.awakening_timing_unknown?`${valid(night.waso_minutes)?'Self-reported awake time: '+mins(night.waso_minutes)+'. ':''}Exact time of the overnight awakening is unknown; this does not refer to your final wake-up. The awake position shown on the timeline is a guess and is excluded from hourly waking analysis.`:null;
  const metric=(value,unit='')=>valid(value)?`${Number(value.toFixed(1))}${unit}`:'—';
  const clock=value=>typeof value==='string'?clockNumber(Number(value.slice(11,13))*60+Number(value.slice(14,16))):'—';
  const clockNumber=value=>{if(!valid(value))return '—';const time=((Math.round(value)%1440)+1440)%1440,h=Math.floor(time/60);return `${h%12||12}:${String(time%60).padStart(2,'0')} ${h<12?'a.m.':'p.m.'}`;};
  const dateKey=value=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
  const svgNode=(tag,attrs={},text)=>{const item=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))item.setAttribute(key,String(value));if(text!=null)item.textContent=text;return item;};
  async function api(url,body){const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const value=await response.json();if(!response.ok)throw Error(value.error||'Sleep data could not load.');return value;}
  function legend(parent,series){const box=node('div',null,'sleep-legend');for(const line of series){const label=node('span',line.name);label.style.setProperty('--color',line.color);box.append(label);}parent.append(box);}
  function enlargePlot(label,draw,index){
    let dialog=$('sleep-chart-dialog');
    if(!dialog){
      dialog=node('dialog',null,'sleep-chart-dialog');dialog.id='sleep-chart-dialog';dialog.setAttribute('aria-labelledby','sleep-chart-dialog-title');
      const heading=node('div',null,'sleep-dialog-heading'),title=node('h2');title.id='sleep-chart-dialog-title';
      const close=node('button','Close');close.type='button';close.setAttribute('aria-label','Close enlarged chart');close.addEventListener('click',()=>dialog.close());heading.append(title,close);
      const content=node('div');content.id='sleep-chart-dialog-content';dialog.append(heading,content);document.body.append(dialog);
      dialog.addEventListener('click',event=>{if(event.target===dialog){const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();}});
    }
    $('sleep-chart-dialog-title').textContent=label;
    draw($('sleep-chart-dialog-content'),index);
    dialog.showModal();
    dialog.querySelector('svg[tabindex]')?.focus();
  }
  function plotTools(target,label,open,expanded){
    if(expanded)return;
    const tools=node('div',null,'sleep-chart-tools'),button=node('button','Enlarge');button.type='button';button.setAttribute('aria-label','Enlarge '+label);button.addEventListener('click',()=>open());tools.append(button);target.append(tools);
  }
  function interactivePlot(target,svg,rows,series,{px,py,width,top,bottom,format=String,label,expanded=false,initialIndex,open}){
    let active=-1;
    const selection=svgNode('g',{'pointer-events':'none'}),guide=svgNode('line',{y1:top,y2:bottom,class:'sleep-chart-guide'});selection.append(guide);
    const dots=series.map(line=>{const dot=svgNode('circle',{r:4,fill:line.color,stroke:'#fffefb','stroke-width':2});selection.append(dot);return dot;});
    const hit=svgNode('rect',{x:0,y:top,width,height:bottom-top,fill:'transparent','pointer-events':'all'});svg.append(hit,selection);
    svg.classList.add('sleep-interactive-plot');svg.setAttribute('tabindex','0');svg.setAttribute('aria-label',label+'. Use left and right arrow keys to inspect values.'+(expanded?'':' Press Enter to enlarge.'));
    const readout=node('div',null,'sleep-chart-readout');readout.setAttribute('role','status');readout.setAttribute('aria-live','polite');readout.setAttribute('aria-atomic','true');
    const show=index=>{
      index=Math.max(0,Math.min(rows.length-1,index));if(index===active)return;active=index;
      const row=rows[index];guide.setAttribute('x1',px(index));guide.setAttribute('x2',px(index));readout.replaceChildren(node('strong',row.label||row.day));
      series.forEach((line,i)=>{const value=row[line.key];dots[i].setAttribute('cx',px(index));dots[i].setAttribute('cy',valid(value)?py(value):top);dots[i].style.display=valid(value)?'':'none';const item=node('span',`${line.name}: ${valid(value)?(line.format||format)(value):'—'}`);item.style.setProperty('--color',line.color);readout.append(item);});
    };
    const point=event=>{
      const box=svg.getBoundingClientRect(),x=(event.clientX-box.left)/box.width*width;
      let nearest=0;for(let i=1;i<rows.length;i++)if(Math.abs(px(i)-x)<Math.abs(px(nearest)-x))nearest=i;
      show(nearest);
    };
    svg.addEventListener('pointermove',point);svg.addEventListener('pointerdown',point);
    svg.addEventListener('click',event=>{point(event);if(!expanded)open(active);});
    svg.addEventListener('keydown',event=>{
      if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();show(event.key==='Home'?0:event.key==='End'?rows.length-1:active+(event.key==='ArrowLeft'?-1:1));}
      else if(!expanded && ['Enter',' '].includes(event.key)){event.preventDefault();open(active);}
    });
    const scroll=node('div',null,'sleep-plot-scroll'),frame=node('div',null,'sleep-plot-frame');frame.append(svg);scroll.append(frame);target.append(scroll,readout);
    target.append(node('p',expanded?'Hover or tap anywhere on the plot for values. Use ← / → to move between points; press Escape to close.':'Hover over the plot for values. Click the graph or Enlarge for a larger view. Arrow keys move between points.','sleep-chart-caption'));
    const lastKnown=rows.findLastIndex(row=>series.some(line=>valid(row[line.key])));
    show(initialIndex??(lastKnown>=0?lastKnown:rows.length-1));
  }
  function chart(target,rows,series,{format=String,zero=true,label='Sleep trend',x='day',expanded=false,initialIndex}={}){
    target.replaceChildren();legend(target,series);
    const values=rows.flatMap(row=>series.map(line=>row[line.key])).filter(valid);
    if(!values.length){target.append(node('p','No measurements for this range.','sleep-empty'));return;}
    const open=index=>enlargePlot(label,(box,selectedIndex)=>chart(box,rows,series,{format,zero,label,x,expanded:true,initialIndex:selectedIndex}),index);
    plotTools(target,label,open,expanded);
    const w=expanded?920:620,h=expanded?370:230,l=expanded?75:57,r=12,t=15,b=32,plotW=w-l-r,plotH=h-t-b;
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
    interactivePlot(target,svg,rows,series,{px,py,width:w,top:t,bottom:h-b,format,label,expanded,initialIndex,open});
    target.append(node('p','Gaps indicate missing nights. Values are shown for the nearest recorded night.','sleep-chart-caption'));
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
    // Show 10 p.m. through 2 p.m. the following day; clip only the display.
    const left=22*60,right=38*60;const axis=node('div',null,'sleep-axis');for(let hour=22;hour<=38;hour+=4)axis.append(node('span',clockNumber(hour*60)));inner.append(axis);
    for(const night of [...data.nights].reverse().slice(0,visibleNights)){
      const button=node('button',null,'sleep-night-row'),label=node('span',null,'sleep-night-label');
      const manual=night.data_source==='manual',total=duration(night.asleep_minutes);
      button.type='button';button.setAttribute('aria-pressed',String(night.id===selected));
      button.setAttribute('aria-label',`Inspect sleep on ${night.day}; ${valid(night.asleep_minutes)?total+' asleep':'total sleep unknown'}${manual?'; manual entry':''}${night.stages_estimated?'; light, deep and REM stages are guesses':''}${night.awakening_timing_unknown?'; overnight awakening clock time unknown':''}`);
      label.append(node('span',night.day.slice(5)),node('strong',total,'sleep-night-total'));
      if(manual||night.stages_estimated)label.append(node('small',manual?(night.stages_estimated?'Manual · guessed stages':'Manual entry'):'Guessed stages'));
      if(night.awakening_timing_unknown)label.append(node('small','Night waking time unknown'));
      button.append(label);
      const track=node('span',null,'sleep-track'),base=night.bedtime_clock;
      const runs=night.stages.length?night.stages:[{stage:'unknown',start_seconds:0,end_seconds:night.in_bed_minutes*60}];
      for(const run of runs){const start=base+run.start_seconds/60,end=base+run.end_seconds/60,clippedStart=Math.max(left,start),clippedEnd=Math.min(right,end);if(clippedEnd<=clippedStart)continue;
        const stage={'1':'deep','2':'light','3':'rem','4':'awake'}[run.stage];
        const provenance=stage==='awake'&&night.awakening_timing_unknown?' (illustrative placement; actual awakening time unknown)':night.stages_estimated&&stage&&stage!=='awake'?' (illustrative guess)':manual?' (self-reported)':'';
        const segment=node('span',null,'sleep-segment'+(stage?' stage-'+stage:''));segment.style.left=`${(clippedStart-left)/(right-left)*100}%`;segment.style.width=`${(clippedEnd-clippedStart)/(right-left)*100}%`;segment.title=`${night.day} · ${stage||'In bed; stages unavailable'}${provenance} · ${clockNumber(start)}–${clockNumber(end)}`;track.append(segment);
      }
      button.append(track);button.addEventListener('click',()=>selectNight(night.id,true));inner.append(button);
    }
    container.append(inner);$('sleep-timeline-more').hidden=visibleNights>=data.nights.length;
  }
  function selectNight(id,scroll=false){selected=id;$('sleep-night').value=id;renderNight();timeline();if(scroll)$('sleep-night-detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
  function nightMetrics(parent,values){const box=node('div',null,'sleep-night-metrics');for(const [name,value] of values){const item=node('div');item.append(node('span',name),node('strong',value));box.append(item);}parent.append(box);}
  function samples(target,night,key,title,color,{expanded=false,initialIndex}={}){const value=night.samples[key];
    target.replaceChildren();if(!expanded)target.append(node('h3',title));
    if(!value || !Array.isArray(value.items) || !valid(value.interval)){target.append(node('p',`No ${title} samples for this period.`,'small'));return;}
    const w=expanded?920:600,h=expanded?370:180,l=40,t=14,b=28,values=value.items.filter(valid);if(!values.length){target.append(node('p',`No ${title} samples for this period.`,'small'));return;}
    const label=`${title} through the night (${night.day})`,open=index=>enlargePlot(label,(box,selectedIndex)=>samples(box,night,key,title,color,{expanded:true,initialIndex:selectedIndex}),index);
    plotTools(target,label,open,expanded);
    const min=Math.max(0,Math.min(...values)-5),max=Math.max(...values)+5,svg=svgNode('svg',{viewBox:`0 0 ${w} ${h}`,class:'sleep-svg',role:'img','aria-label':`${title} through the night`});let path='',previous=false;
    const px=index=>l+index/Math.max(value.items.length-1,1)*(w-l-10),py=v=>t+(max-v)/(max-min)*(h-t-b);
    value.items.forEach((v,index)=>{if(!valid(v)){previous=false;return;}path+=`${previous?'L':'M'}${px(index)},${py(v)} `;previous=true;});
    svg.append(svgNode('path',{d:path,stroke:color}),svgNode('text',{x:0,y:t+5},Math.round(max)),svgNode('text',{x:0,y:h-b},Math.round(min)),svgNode('text',{x:l,y:h-5},clock(value.timestamp||night.bedtime)),svgNode('text',{x:w-10,y:h-5,'text-anchor':'end'},clock(new Date(Date.parse(value.timestamp||night.bedtime)+(value.items.length-1)*value.interval*1000).toISOString())));
    // Last axis label uses the recorded offset, not the viewer device's timezone.
    const base=clockNumber(Number((value.timestamp||night.bedtime).slice(11,13))*60+Number((value.timestamp||night.bedtime).slice(14,16))+(value.items.length-1)*value.interval/60);svg.lastChild.textContent=base;
    const start=value.timestamp||night.bedtime,startMinutes=Number(start.slice(11,13))*60+Number(start.slice(14,16));
    const rows=value.items.map((item,index)=>({label:`${night.day} · ${clockNumber(startMinutes+index*value.interval/60)}`,value:item}));
    interactivePlot(target,svg,rows,[{key:'value',name:title,color}],{px,py,width:w,top:t,bottom:h-b,format:v=>metric(v),label,expanded,initialIndex,open});
  }
  function wakeHours(target,rows,{expanded=false,initialIndex}={}){
    target.replaceChildren();const label='Awake minutes by local clock hour',open=index=>enlargePlot(label,(box,selectedIndex)=>wakeHours(box,rows,{expanded:true,initialIndex:selectedIndex}),index);
    plotTools(target,label,open,expanded);
    const w=expanded?920:620,h=expanded?370:220,left=36,base=h-35,step=(w-left-8)/24,max=Math.max(1,...rows.map(item=>item.awake_minutes));
    const px=index=>left+(index+.5)*step,py=value=>base-value/max*(base-20),svg=svgNode('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':label,class:'sleep-svg'});
    rows.forEach((item,index)=>{const height=base-py(item.awake_minutes);svg.append(svgNode('rect',{x:left+index*step+2,y:base-height,width:step-6,height,fill:colors.awake}));if(index%4===0)svg.append(svgNode('text',{x:left+index*step,y:h-13},String(item.hour).padStart(2,'0')));});
    const labeled=rows.map(item=>({...item,label:clockNumber(item.hour*60)}));
    interactivePlot(target,svg,labeled,[{key:'awake_minutes',name:'Total awake minutes',color:colors.awake}],{px,py,width:w,top:15,bottom:base,format:mins,label,expanded,initialIndex,open});
  }
  function renderNight(){const box=$('sleep-night-detail');box.replaceChildren();const night=data.nights.find(item=>item.id===selected);if(!night){box.append(node('p','Choose a night with a main sleep session.','sleep-empty'));return;}
    if(night.data_source==='manual')box.append(node('p',night.stages_estimated?'Manual entry: sleep and wake times are self-reported and may be approximate. Light, deep and REM intervals are illustrative guesses, not Oura measurements, and are excluded from stage-duration trends. The reported sleep window is used for time in bed; actual bedtime and sleep latency are unknown.':'Manual entry: self-reported sleep times.','small'));
    box.append(node('p',`${night.day} · ${night.stages_estimated?'Illustrative guessed stages':night.stage_resolution_seconds?night.stage_resolution_seconds+'-second stages':'Stages unavailable'} · ${night.period_count} recorded sleep period${night.period_count===1?'':'s'}`,'small'));
    nightMetrics(box,[['In bed',clock(night.bedtime)],['Estimated sleep onset',clock(night.onset)],['Final wake',clock(night.final_wake)],['Out of bed',clock(night.out_of_bed)],['Time asleep',duration(night.asleep_minutes)],['Time to fall asleep',mins(night.latency_minutes)],['Awake during sleep',mins(night.waso_minutes)],['Longest awakening',mins(night.longest_wake_minutes)],['Awakenings ≥5 min',metric(night.awakenings_5m)],['Total awake in bed',mins(night.awake_minutes)],['Sleep efficiency',metric(night.efficiency,'%')],['Sleep score',metric(night.sleep_score,' / 100')],['Average HRV',metric(night.hrv,' ms')],['Average heart rate',metric(night.heart_rate,' bpm')],['Lowest heart rate',metric(night.lowest_heart_rate,' bpm')],['Breathing rate',metric(night.breathing_rate,' / min')],['SpO₂ average',metric(night.spo2,'%')],['Breathing disturbance index',metric(night.breathing_disturbance_index)],['Temperature deviation',metric(night.temperature_deviation,' °C')],['Restless periods',metric(night.restless_periods)]]);
    const warnings=[];if(night.low_battery)warnings.push('Oura flagged a low battery.');if(night.offset_changed)warnings.push('The UTC offset changed during this session. Stage times retain the starting offset.');if(night.main_period_count>1)warnings.push('Multiple main-sleep sessions: nightly trends use the longest; other sessions are listed below.');if(!night.stages.length)warnings.push('Usable stages are missing. Awakening timings are unknown.');if(warnings.length)box.append(node('p',warnings.join(' '),'small'));
    box.append(node('h3','Overnight awakenings lasting at least five minutes'));
    const events=night.awakenings.filter(item=>item.minutes>=5);
    const timingNote=awakeningNote(night);
    if(timingNote)box.append(node('p',timingNote,'small'));
    else if(!events.length)box.append(node('p',night.waso_minutes===null?'No usable sleep-stage series.':'No continuous awake interval of five minutes detected between first and last sleep.','small'));
    for(const event of events){const row=node('div',null,'sleep-event');row.append(node('strong',`${clock(event.start)}–${clock(event.end)}`),node('span',duration(event.minutes)));box.append(row);}
    const clusters=night.disrupted_windows.filter(item=>item.span_minutes>item.awake_minutes);
    if(clusters.length){box.append(node('h3','Long disrupted stretches with brief sleep between awakenings'));box.append(node('p','These group awake episodes separated by at most five minutes of detected sleep. The entire stretch is not counted as awake.','small'));for(const item of clusters){const row=node('div',null,'sleep-event');row.append(node('strong',`${clock(item.start)}–${clock(item.end)}`),node('span',`${mins(item.awake_minutes)} awake across ${mins(item.span_minutes)}`));box.append(row);}}
    const reported=night.reported_sleep;
    const reportText=Object.keys(reported).length?' Historical morning report: '+(Object.entries(reported).filter(([,v])=>v===true).map(([key])=>({woke_up:'woke up',awake_20_minutes:'20+ minutes',awake_30_minutes:'30+ minutes (older option)',awake_1_hour:'1+ hour',awake_2_hours:'2+ hours'}[key]||key)).join(', ')||'no interruptions checked')+'.':'';
    const intake=night.caffeine_last_intake,caffeineText=intake==='none'?'no caffeine':intake?`last intake at ${clockNumber(Number(intake.slice(0,2))*60+Number(intake.slice(3)))}`:night.caffeine_after_4pm===null?'not logged':`${night.caffeine_after_4pm?'after 4 p.m.':'none after 4 p.m.'} (exact time not recorded)`;
    box.append(node('p',`Evening caffeine log (${night.caffeine_day}): ${caffeineText}${caffeineText.endsWith('.')?'':'.'}${reportText}`,'small'));
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
    wakeHours($('sleep-hours-chart'),data.wake_hours);table();$('sleep-method').textContent=data.method;
  }
  function range(){const value=$('sleep-range').value,to=new Date();if(value==='custom')return;const from=new Date(to);if(value==='all')from.setFullYear(2015,0,1);else from.setDate(to.getDate()-Number(value)+1);$('sleep-from').value=analysisStart && dateKey(from)<analysisStart?analysisStart:dateKey(from);$('sleep-to').value=dateKey(to);}
  async function load(){
    const id=++loading;$('sleep-status').textContent='Loading sleep history…';
    try{
      const result=await api(`/api/oura/sleep-analysis?start=${encodeURIComponent($('sleep-from').value)}&end=${encodeURIComponent($('sleep-to').value)}`);
      if(id!==loading)return;
      data=result;analysisStart=data.analysis_start||null;
      $('sleep-from').value=data.start;
      for(const field of ['sleep-from','sleep-to']){if(analysisStart)$(field).min=analysisStart;else $(field).removeAttribute('min');}
      render();const inventory=data.inventory.find(item=>item.kind==='sleep');
      $('sleep-status').textContent=`${data.coverage.nights} recorded main-sleep nights · ${data.coverage.stage_nights} with usable stages · ${data.coverage.missing_days} calendar days without a main-sleep record. ${inventory?`Included sleep history: ${inventory.start} through ${inventory.end}.`:''}`;
    }catch(error){if(id===loading)$('sleep-status').textContent=error.message;}
  }
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
