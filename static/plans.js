/* Pure Markdown helpers shared by the editor and regression checks. */
(function(root){
  const heading='### Morning plans — evening check-in';
  function items(answer, limit=Infinity){
    const lines=answer.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
    if(lines.length>limit)return null;
    return lines.map(s=>s.replace(/^(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)/,''));
  }
  const optionalTitle='What would be great to do today, if I have time?';
  function optional(text){
    const match=text.match(/^### What would be great to do today, if I have time\?\s*\r?\n([\s\S]*?)(?=^### |$(?![\s\S]))/m);
    return match?items(match[1],Infinity):[];
  }
  function morning(text){
    const match=text.match(/^### What would make today feel like a good day\?\s*\r?\n([\s\S]*?)(?=^### |$(?![\s\S]))/m);
    return [...(match?items(match[1]) || []:[]),...(optional(text) || []).map(s=>'[If time] '+s)];
  }
  function review(text){
    const match=text.match(/^<!-- carry-review: (.*?) -->\r?\n/);
    if(!match)return {body:text,choices:{}};
    try{return {body:text.slice(match[0].length),choices:JSON.parse(decodeURIComponent(match[1]))};}catch{return {body:text,choices:{}};}
  }
  function upgrade(text){
    const value=review(text).body;
    if(!value.includes('### '+optionalTitle) && value.includes('### What would make today feel like a good day?') && value.includes('### What might get in the way, and what could help?'))
      return value.replace('### What might get in the way, and what could help?', '### '+optionalTitle+'\n\n\n### What might get in the way, and what could help?');
    return value;
  }
  function jo(text){
    const match=text.match(/<!-- evening-jo: (.*?) -->/);
    let value={jo:false,worth_it:false,why:''};
    if(match){try{value={...value,...JSON.parse(decodeURIComponent(match[1]))};}catch{}}
    return {body:text.replace(/\n?<!-- evening-jo: .*? -->\s*$/,''),value};
  }
  function serializeJO(value){return '\n<!-- evening-jo: '+encodeURIComponent(JSON.stringify(value))+' -->\n';}
  function split(text){
    text=jo(text).body;
    const ratings={};
    text=text.replace(/^### Daily ratings\r?\n\s*Good day: ([1-5]|unrated)\r?\nProductive day: ([1-5]|unrated)\s*(?=^### |$(?![\s\S]))/m,(_,good,productive)=>{ratings.good=good==='unrated'?'':good;ratings.productive=productive==='unrated'?'':productive;return '';});
    const marker=heading+'\n';const normalized=text.replace(/\r\n/g,'\n');
    if(!normalized.startsWith(marker))return {body:text,tasks:[],ratings};
    const end=normalized.indexOf('\n### ',marker.length);
    const block=normalized.slice(marker.length,end<0?undefined:end);
    const lines=block.split('\n').filter(s=>s.trim());
    if(lines.some(s=>!/^[-] \[[ xX]\] .+$/.test(s)))return {body:text,tasks:[],ratings};
    return {body:end<0?'':normalized.slice(end+1),tasks:lines.map(s=>{let text=s.slice(6),meta={};const match=text.match(/ <!-- task-meta: (.*?) -->$/);if(match){try{meta=JSON.parse(decodeURIComponent(match[1]));text=text.slice(0,match.index);}catch{}}return {...meta,text,done:s[3].toLowerCase()==='x'};}),ratings};
  }
  function reconcile(plans,previous){
    const remaining=previous.map(t=>({...t}));
    const tasks=(plans || []).map(text=>{
      const index=remaining.findIndex(t=>!t.followup && (t.original || t.text)===text);
      return index<0?{text,done:false}:remaining.splice(index,1)[0];
    });
    // Keep old check-in items if morning text later changes, rather than lose history.
    return tasks.concat(remaining.map(t=>({...t,earlier:!t.followup})));
  }
  function serialize(tasks){return tasks.length?heading+'\n\n'+tasks.map(t=>`- [${t.done?'x':' '}] ${t.text}`+((t.original || t.followup)?' <!-- task-meta: '+encodeURIComponent(JSON.stringify({original:t.original || t.text,...(t.followup?{followup:t.followup,parent:t.parent}: {})}))+' -->':'')).join('\n')+'\n\n':'';}
  const api={jo,serializeJO,items,morning,split,reconcile,serialize,optional,optionalTitle,review,upgrade};
  if(typeof module!=='undefined')module.exports=api;else root.JournalPlans=api;
})(typeof globalThis!=='undefined'?globalThis:this);
