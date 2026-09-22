(() => {
  const $=id=>document.getElementById(id);
  let rows=[], revision='', ready=false, saving=false, dirty=false, draftPrefix='', recoveredKey=null;
  const session=crypto.randomUUID();
  const today=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
  const emptyReview=()=>({score:null,review:'',thoughts:''});
  function message(text,error=false){$('restaurants-status').textContent=text;$('restaurants-status').className=error?'error':'';}
  function persist(){
    if(!ready || !dirty)return true;
    try{localStorage.setItem(draftPrefix+session,JSON.stringify({restaurants:rows,revision,updated:Date.now()}));return true;}
    catch{message('Draft recovery is unavailable. Save restaurants before closing this tab.',true);return false;}
  }
  function changed(){dirty=true;if(persist())message('Draft saved in this browser · save restaurants to keep it in your vault.');}
  function node(tag,text,className){const item=document.createElement(tag);if(text)item.textContent=text;if(className)item.className=className;return item;}
  function field(parent,title,value,onInput,multiline=false){
    const label=node('label',title), input=document.createElement(multiline?'textarea':'input');
    if(!multiline){input.type='text';input.maxLength=200;}else{input.rows=3;input.maxLength=40000;}
    input.value=value;input.addEventListener('input',()=>{onInput(input.value);changed();});label.append(input);parent.append(label);return input;
  }
  function reviewEditor(parent,item,person,onScore){
    const review=item[person], panel=node('section',null,'person-review');
    panel.append(node('h4',person==='you'?'You':'Ashley'));
    // Merge legacy review text without discarding either field.
    if(review.review){review.thoughts=review.review===review.thoughts?review.thoughts:[review.review,review.thoughts].filter(Boolean).join('\n\n');review.review='';}
    const label=node('label','Score'),select=document.createElement('select');
    for(const [value,text] of [['','Not rated'],['1','1 — Poor'],['2','2 — Fair'],['3','3 — Good'],['4','4 — Great'],['5','5 — Loved it']]){
      const option=node('option',text);option.value=value;select.append(option);
    }
    select.value=review.score===null?'':String(review.score);
    select.setAttribute('aria-label',`${item.name} — ${person==='you'?'your':'Ashley’s'} score`);
    select.addEventListener('change',()=>{review.score=select.value?Number(select.value):null;changed();onScore();});
    label.append(select);panel.append(label);
    field(panel,'Thoughts',review.thoughts,value=>review.thoughts=value,true);
    parent.append(panel);
  }
  function editors(parent,item,onScore){
    const grid=node('div',null,'review-grid');reviewEditor(grid,item,'you',onScore);parent.append(grid);
    if(item.ashley)reviewEditor(grid,item,'ashley',onScore);
    else{
      const add=node('button','+ Add Ashley','add-ashley');add.type='button';
      add.addEventListener('click',()=>{item.ashley=emptyReview();reviewEditor(grid,item,'ashley',onScore);add.remove();changed();onScore();});parent.append(add);
    }
  }
  function card(item,isRestaurant=false){
    const details=node('details',null,isRestaurant?'card restaurant-card':'dish-card');
    const summary=document.createElement('summary');const name=node('span'),scores=node('small');summary.append(name,scores);details.append(summary);
    const update=()=>{name.textContent=item.name;scores.textContent=`You: ${item.you.score ?? '—'}/5`+(item.ashley?` · Ashley: ${item.ashley.score ?? '—'}/5`:'')+(isRestaurant?` · ${item.date} · ${item.dishes.length} dish${item.dishes.length===1?'':'es'}`:'');};update();
    const body=node('div',null,'restaurant-body');details.append(body);
    field(body,isRestaurant?'Restaurant name':'Dish name',item.name,value=>{item.name=value;update();});
    if(isRestaurant){const label=node('label','Visit date'),input=document.createElement('input');input.type='date';input.required=true;input.value=item.date;input.addEventListener('change',()=>{item.date=input.value;update();changed();});label.append(input);body.append(label);}
    editors(body,item,update);
    if(isRestaurant){
      body.append(node('h3','Dishes you’ve tried'));
      const dishes=node('div'),empty=node('p','No dishes yet. Add your first one below.','small');
      if(!item.dishes.length)dishes.append(empty);
      for(const dish of item.dishes)dishes.append(card(dish));body.append(dishes);
      const form=node('form',null,'restaurant-add'),label=node('label','Dish name'),input=document.createElement('input');
      input.required=true;input.maxLength=200;input.placeholder='What did you try?';label.append(input);
      const add=node('button','+ Add dish');add.type='submit';form.append(label,add);
      form.addEventListener('submit',event=>{event.preventDefault();if(!input.value.trim())return;
        const dish={id:crypto.randomUUID(),name:input.value.trim(),you:emptyReview(),ashley:null};item.dishes.push(dish);
        empty.remove();const element=card(dish);element.open=true;dishes.append(element);input.value='';update();changed();
      });body.append(form);
    }
    return details;
  }
  function render(){const list=$('restaurant-list');list.replaceChildren();if(!rows.length)list.append(node('p','No restaurants yet. Add one to start your list.','small'));for(const item of rows)list.append(card(item,true));}
  function navigate(){
    const page=['restaurants','people'].includes(location.hash.slice(1))?location.hash.slice(1):'journal';
    for(const name of ['journal','restaurants','people']){
      $(name+'-page').hidden=name!==page;const link=$('nav-'+name);
      if(name===page)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    }
    document.title=page==='journal'?'A little room — Journal':page[0].toUpperCase()+page.slice(1)+' — A little room';
  }
  window.addEventListener('hashchange',navigate);navigate();
  $('add-restaurant-form').addEventListener('submit',event=>{event.preventDefault();if(!ready || saving)return;
    const input=$('restaurant-name');if(!input.value.trim())return;
    const item={id:crypto.randomUUID(),name:input.value.trim(),you:emptyReview(),ashley:null,date:today(),dishes:[]};rows.push(item);
    if(rows.length===1)$('restaurant-list').replaceChildren();const element=card(item,true);element.open=true;$('restaurant-list').append(element);input.value='';changed();
  });
  $('save-restaurants').addEventListener('click',async()=>{
    if(!ready || saving)return;saving=true;
    const disabled=[...$('restaurants-page').querySelectorAll('input,textarea,select,button')];disabled.forEach(input=>input.disabled=true);
    message('Saving restaurants…');
    try{
      const response=await fetch('/api/restaurants',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({restaurants:rows,revision})});const data=await response.json();if(!response.ok)throw Error(data.error);
      revision=data.revision;dirty=false;
      try{localStorage.removeItem(draftPrefix+session);if(recoveredKey)localStorage.removeItem(recoveredKey);recoveredKey=null;}catch{}
      message('Restaurants saved to your vault.');
    }catch(error){message(error.message,true);}
    finally{saving=false;disabled.forEach(input=>input.disabled=false);}
  });
  $('reload-restaurants').addEventListener('click',async()=>{
    if(!ready || saving)return;
    saving=true;$('reload-restaurants').disabled=true;$('save-restaurants').disabled=true;
    try{
      const response=await fetch('/api/restaurants');const saved=await response.json();if(!response.ok)throw Error(saved.error);
      // Preserve all recovered versions before retiring stale recovery keys.
      const drafts=Object.keys(localStorage).filter(key=>key.startsWith(draftPrefix)).map(key=>({key,value:localStorage.getItem(key)}));
      localStorage.setItem('restaurants-archive:'+draftPrefix+Date.now(),JSON.stringify({current:{restaurants:rows,revision},drafts}));
      for(const draft of drafts){if(localStorage.getItem(draft.key)===draft.value)localStorage.removeItem(draft.key);}
      rows=saved.restaurants;revision=saved.revision;dirty=false;recoveredKey=null;render();
      message('Saved restaurants loaded. Previous drafts are backed up in this browser.');
    }catch(error){message('Could not reload safely: '+error.message,true);}
    finally{saving=false;$('reload-restaurants').disabled=false;$('save-restaurants').disabled=false;}
  });
  window.addEventListener('beforeunload',event=>{if(dirty&&!persist()){event.preventDefault();event.returnValue='';}});
  Promise.all([fetch('/api/config').then(r=>r.json()),fetch('/api/restaurants').then(async r=>{const data=await r.json();if(!r.ok)throw Error(data.error);return data;})]).then(([config,data])=>{
    draftPrefix='restaurants-draft:'+config.vault+':';rows=data.restaurants;revision=data.revision;ready=true;
    message('Restaurants loaded.');
    try{
      const drafts=Object.keys(localStorage).filter(key=>key.startsWith(draftPrefix)).map(key=>{try{return {key,...JSON.parse(localStorage.getItem(key))};}catch{return null;}}).filter(d=>d&&Array.isArray(d.restaurants)&&typeof d.revision==='string').sort((a,b)=>b.updated-a.updated);
      if(drafts.length){const draft=drafts[0];rows=draft.restaurants;dirty=true;recoveredKey=draft.key;
        const conflict=revision!==draft.revision;revision=draft.revision;message(conflict?'Draft recovered, but saved restaurants changed. Your edits are preserved. Once reconciled, use Back up draft & load saved.':'Restaurant draft recovered. Save when ready.',conflict);}
    }catch{message('Could not recover drafts. Saved restaurants loaded.',true);}
    render();$('save-restaurants').disabled=false;$('reload-restaurants').disabled=false;
  }).catch(error=>message('Could not load restaurants: '+error.message,true));
})();
