(() => {
  const supported=!!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const dialog=document.createElement('dialog');dialog.className='voice-dialog';
  const title=document.createElement('h2');title.textContent='Speak your note';
  const info=document.createElement('p');info.setAttribute('role','status');
  const review=document.createElement('textarea');review.setAttribute('aria-label','Review transcription');review.rows=6;review.hidden=true;
  const stop=document.createElement('button');stop.type='button';stop.textContent='Stop recording';
  const insert=document.createElement('button');insert.type='button';insert.textContent='Add to text';insert.hidden=true;
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Cancel';
  const privacy=document.createElement('p');privacy.className='small';privacy.textContent='Transcribed on your PC. Audio is not saved. Up to 2 minutes.';
  dialog.append(title,info,review,stop,insert,cancel,privacy);document.body.append(dialog);
  let active=null,stream=null,recorder=null,timer=null,controller=null,session=0;
  function release(){clearTimeout(timer);stream?.getTracks().forEach(track=>track.stop());stream=null;}
  function close(){session++;if(recorder?.state==='recording')recorder.stop();release();controller?.abort();dialog.close();active=null;}
  cancel.onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  stop.onclick=()=>{if(recorder?.state==='recording')recorder.stop();};
  insert.onclick=()=>{
    if(!active?.isConnected || active.disabled || active.readOnly){info.textContent='The field has changed. Copy your transcript before closing.';return;}
    const text=review.value.trim();if(!text)return;
    const addition=(active.value && !/\s$/.test(active.value)?' ':'')+text;
    if(active.maxLength>=0 && active.value.length+addition.length>active.maxLength){info.textContent='This text exceeds the field limit. Shorten it or copy it to a longer note.';return;}
    active.value+=addition;active.dispatchEvent(new Event('input',{bubbles:true}));active.dispatchEvent(new Event('change',{bubbles:true}));
    const target=active;close();target.focus();
  };
  async function record(field){
    if(dialog.open)return;
    active=field;const token=++session;review.hidden=true;review.value='';insert.hidden=true;stop.hidden=false;stop.disabled=true;
    info.textContent='Allow microphone access to start recording.';dialog.showModal();
    try{
      const acquired=await navigator.mediaDevices.getUserMedia({audio:true});
      if(token!==session){acquired.getTracks().forEach(t=>t.stop());return;}
      stream=acquired;
      const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime)throw Error('This browser cannot record a supported format. Try Safari or Chrome.');
      recorder=new MediaRecorder(stream,{mimeType:mime});const chunks=[];let bytes=0;
      recorder.ondataavailable=event=>{if(event.data.size){chunks.push(event.data);bytes+=event.data.size;if(bytes>11*1024*1024 && recorder.state==='recording')recorder.stop();}};
      recorder.onerror=()=>{release();info.textContent='Recording stopped unexpectedly. Cancel and try again.';stop.hidden=true;};
      recorder.onstop=async()=>{
        if(token!==session)return;release();stop.hidden=true;info.textContent='Transcribing on your PC…';controller=new AbortController();
        const timeout=setTimeout(()=>controller.abort(),180000);
        try{
          const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':mime},body:new Blob(chunks,{type:mime}),signal:controller.signal});
          const result=await response.json();if(!response.ok)throw Error(result.error || 'Transcription failed.');
          if(token!==session)return;
          review.value=result.text;review.hidden=false;insert.hidden=!result.text;info.textContent=result.text?'Review the text, then add it to your note.':'No speech detected. Cancel and try again.';
        }catch(error){if(token===session)info.textContent=error.name==='AbortError'?'Transcription timed out. Cancel and try a shorter recording.':error.message;}
        finally{clearTimeout(timeout);}
      };
      recorder.start(1000);stop.disabled=false;info.textContent='Recording… Tap Stop when you’re finished.';timer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},120000);
    }catch(error){release();if(token===session){stop.hidden=true;info.textContent=error.name==='NotAllowedError'?'Microphone access was denied. Allow it in browser settings and try again.':error.message;}}
  }
  const enhanced=new WeakSet();
  function enhance(){
    document.querySelectorAll('#guided textarea, #guided input[type=text], #entry, #plan-review input[type=text], #people-page textarea, #people-page input[type=text], #restaurants-page textarea, #restaurants-page input[type=text]').forEach(field=>{
      if(enhanced.has(field) || field.readOnly || field.type==='password')return;enhanced.add(field);
      const button=document.createElement('button');button.type='button';button.className='voice-button';button.textContent='🎙';button.setAttribute('aria-label','Dictate into '+(field.getAttribute('aria-label') || field.labels?.[0]?.textContent || 'this field'));button.title=supported?'Speak instead of typing':'Microphone recording needs Safari or Chrome over HTTPS';button.disabled=!supported;
      button.onclick=()=>{if(!field.disabled && !field.readOnly)record(field);};field.insertAdjacentElement('afterend',button);
    });
  }
  new MutationObserver(enhance).observe(document.querySelector('main'),{childList:true,subtree:true});enhance();
  window.addEventListener('pagehide',close);
})();
