/* Pure Markdown helpers shared by the editor and regression checks. */
(function(root){
  const heading='### Morning plans — evening check-in';
  function items(answer, limit=Infinity){
    const lines=answer.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    if(lines.length>limit)return null;
    return lines.map(s=>s.replace(/^(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)/,''));
  }
  const priorityTitle='Priority Tasks';
  const secondaryTitle='Secondary Tasks';
  const legacyPriorityTitle='What would make today feel like a good day?';
  const legacySecondaryTitle='What would be great to do today, if I have time?';
  function optional(text){
    const match=text.match(/^### (?:Secondary Tasks|What would be great to do today, if I have time\?)\s*\r?\n([\s\S]*?)(?=^### |$(?![\s\S]))/m);
    return match?items(match[1],Infinity):[];
  }
  function morning(text){
    const match=text.match(/^### (?:Priority Tasks|What would make today feel like a good day\?)\s*\r?\n([\s\S]*?)(?=^### |$(?![\s\S]))/m);
    return [...(match?items(match[1]) || []:[]),...(optional(text) || []).map(s=>'[If time] '+s)];
  }
  function review(text){
    const match=text.match(/^<!-- carry-review: (.*?) -->\r?\n/);
    if(!match)return {body:text,choices:{}};
    try{return {body:text.slice(match[0].length),choices:JSON.parse(decodeURIComponent(match[1]))};}catch{return {body:text,choices:{}};}
  }
  function upgrade(text){
    let value=review(text).body
      .replace('### '+legacyPriorityTitle, '### '+priorityTitle)
      .replace('### '+legacySecondaryTitle, '### '+secondaryTitle);
    if(!value.includes('### '+secondaryTitle) && value.includes('### '+priorityTitle) && value.includes('### What might get in the way, and what could help?'))
      return value.replace('### What might get in the way, and what could help?', '### '+secondaryTitle+'\n\n\n### What might get in the way, and what could help?');
    return value;
  }
  function jo(text){
    const match=text.match(/<!-- evening-jo: (.*?) -->/);
    let value={jo:false,worth_it:false,why:''};
    if(match){try{value={...value,...JSON.parse(decodeURIComponent(match[1]))};}catch{}}
    return {body:text.replace(/\n?<!-- evening-jo: .*? -->\s*$/,''),value};
  }
  function serializeJO(value){return '\n<!-- evening-jo: '+encodeURIComponent(JSON.stringify(value))+' -->\n';}
  function habits(text){
    const match=text.match(/<!-- evening-habits: (.*?) -->/);
    let value={phone_game_before_morning_work:false,phone_game_before_afternoon_work:false,caffeine_after_4pm:false};
    if(match){try{value={...value,...JSON.parse(decodeURIComponent(match[1]))};}catch{}}
    return {body:text.replace(/\n?<!-- evening-habits: .*? -->\s*$/,''),value};
  }
  function serializeHabits(value){return '\n<!-- evening-habits: '+encodeURIComponent(JSON.stringify(value))+' -->\n';}
  function sleep(text){
    const match=text.match(/<!-- morning-sleep: (.*?) -->/);
    let value={woke_up:false,awake_20_minutes:false,awake_30_minutes:false,awake_1_hour:false,awake_2_hours:false};
    if(match){try{value={...value,...JSON.parse(decodeURIComponent(match[1]))};}catch{}}
    return {body:text.replace(/\n?<!-- morning-sleep: .*? -->\s*$/,''),value};
  }
  function serializeSleep(value){return '\n<!-- morning-sleep: '+encodeURIComponent(JSON.stringify(value))+' -->\n';}
  function split(text){
    text=habits(jo(text).body).body;
    const ratings={};
    text=text.replace(/^### Daily ratings\r?\n\s*(?:Good day|Day satisfaction): (10|[1-9]|unrated)(?:\r?\nDay satisfaction scale: (10))?\r?\nProductive day: (10|[1-9]|unrated)(?:\r?\nProductivity scale: (10))?\s*(?=^### |$(?![\s\S]))/m,(_,good,goodScale,productive,productiveScale)=>{
      const legacy={1:'1',2:'3',3:'6',4:'8',5:'10'};
      ratings.good=good==='unrated'?'':(!goodScale && legacy[good] || good);
      ratings.productive=productive==='unrated'?'':(!productiveScale && legacy[productive] || productive);
      return '';
    });
    const marker=heading+'\n';const normalized=text.replace(/\r\n/g,'\n');
    if(!normalized.startsWith(marker))return {body:text,tasks:[],ratings};
    const end=normalized.indexOf('\n### ',marker.length);
    const block=normalized.slice(marker.length,end<0?undefined:end);
    const lines=block.split('\n').filter(s=>s.trim());
    if(lines.some(s=>!/^[-] \[[ xX]\] .+$/.test(s)))return {body:text,tasks:[],ratings};
    return {body:end<0?'':normalized.slice(end+1),tasks:lines.map(s=>{let text=s.slice(6),meta={};const match=text.match(/ <!-- task-meta: (.*?) -->$/);if(match){try{meta=JSON.parse(decodeURIComponent(match[1]));text=text.slice(0,match.index);}catch{}}return {...meta,text,done:s[3].toLowerCase()==='x'};}),ratings};
  }
  function reconcile(plans,previous){
    const remaining=[...(plans || [])];
    // The saved checklist is the user's order; append only new morning items.
    const tasks=previous.map(task=>{
      const index=task.followup?-1:remaining.indexOf(task.original || task.text);
      if(index>=0)remaining.splice(index,1);
      return {...task,earlier:index<0 && !task.followup && !task.eveningAdded};
    });
    return tasks.concat(remaining.map(text=>({text,done:false})));
  }
  function serialize(tasks){return tasks.length?heading+'\n\n'+tasks.map(t=>`- [${t.done?'x':' '}] ${t.text}`+((t.original || t.followup || t.eveningAdded || t.submitted || t.cooldown || t.deleted)?' <!-- task-meta: '+encodeURIComponent(JSON.stringify({original:t.original || t.text,...(t.deleted?{deleted:true}:{}),...(t.cooldown?{cooldown:t.cooldown}:{}),...(t.submitted?{submitted:true}:{}),...(t.eveningAdded?{eveningAdded:true}:{}),...(t.followup?{followup:t.followup,parent:t.parent}: {})}))+' -->':'')).join('\n')+'\n\n':'';}
  const api={jo,serializeJO,habits,serializeHabits,sleep,serializeSleep,items,morning,split,reconcile,serialize,optional,priorityTitle,secondaryTitle,review,upgrade};
  if(typeof module!=='undefined')module.exports=api;else root.JournalPlans=api;
})(typeof globalThis!=='undefined'?globalThis:this);
