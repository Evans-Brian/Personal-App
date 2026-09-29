(() => {
  const supported=!!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  const dialog=document.createElement('section');dialog.className='voice-inline';dialog.hidden=true;dialog.setAttribute('aria-label','Voice dictation');
  const info=document.createElement('p');info.setAttribute('role','status');
  const review=document.createElement('textarea');review.setAttribute('aria-label','Transcript to copy');review.rows=3;review.hidden=true;
  const stop=document.createElement('button');stop.type='button';stop.textContent='Stop recording';
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Cancel';
  const privacy=document.createElement('p');privacy.className='small';privacy.textContent='Transcribed on your PC. Audio is not saved. Up to 2 minutes.';
  dialog.append(info,review,stop,cancel,privacy);document.body.append(dialog);
  let active=null,stream=null,recorder=null,timer=null,controller=null,session=0;
  function release(){clearTimeout(timer);stream?.getTracks().forEach(track=>track.stop());stream=null;}
  function close(){session++;if(recorder?.state==='recording')recorder.stop();release();controller?.abort();active?.closest('.voice-field-shell')?.querySelector('.voice-button')?.classList.remove('recording');dialog.hidden=true;document.body.append(dialog);active=null;}
  cancel.onclick=close;dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close();}});
  stop.onclick=()=>{if(recorder?.state==='recording')recorder.stop();};
  function appendTranscript(text){
    if(!active?.isConnected || active.disabled || active.readOnly){review.value=text;review.hidden=false;info.textContent='The field has changed. Copy your transcript before closing.';return;}
    text=text.trim();if(!text)return;
    const addition=(active.value && !/\s$/.test(active.value)?' ':'')+text;
    if(active.maxLength>=0 && active.value.length+addition.length>active.maxLength){review.value=text;review.hidden=false;info.textContent='This transcript exceeds the field limit. Copy it into a longer note.';return;}
    active.value+=addition;active.dispatchEvent(new Event('input',{bubbles:true}));active.dispatchEvent(new Event('change',{bubbles:true}));
    const target=active;close();target.focus();
  };
  async function record(field){
    if(!dialog.hidden){dialog.scrollIntoView({block:'nearest'});return;}
    active=field;const token=++session;review.hidden=true;review.value='';stop.hidden=false;stop.disabled=true;
    info.textContent='Allow microphone access to start recording.';
    const anchor=field.closest('label, .optional-plan-row') || field.nextElementSibling || field;
    anchor.insertAdjacentElement('afterend',dialog);dialog.hidden=false;
    try{
      const acquired=await navigator.mediaDevices.getUserMedia({audio:true});
      if(token!==session){acquired.getTracks().forEach(t=>t.stop());return;}
      stream=acquired;
      const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime)throw Error('This browser cannot record a supported format. Try Safari or Chrome.');
      recorder=new MediaRecorder(stream,{mimeType:mime});const chunks=[];let bytes=0;field.closest('.voice-field-shell')?.querySelector('.voice-button')?.classList.add('recording');
      recorder.ondataavailable=event=>{if(event.data.size){chunks.push(event.data);bytes+=event.data.size;if(bytes>11*1024*1024 && recorder.state==='recording')recorder.stop();}};
      recorder.onerror=()=>{release();info.textContent='Recording stopped unexpectedly. Cancel and try again.';stop.hidden=true;};
      recorder.onstop=async()=>{
        if(token!==session)return;release();stop.hidden=true;info.textContent='Transcribing on your PC…';controller=new AbortController();
        const timeout=setTimeout(()=>controller.abort(),180000);
        try{
          const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':mime},body:new Blob(chunks,{type:mime}),signal:controller.signal});
          const result=await response.json();if(!response.ok)throw Error(result.error || 'Transcription failed.');
          if(token!==session)return;
          if(result.text?.trim())appendTranscript(result.text);
          else info.textContent='No speech detected. Cancel and try again.';
        }catch(error){if(token===session)info.textContent=error.name==='AbortError'?'Transcription timed out. Cancel and try a shorter recording.':error.message;}
        finally{clearTimeout(timeout);}
      };
      recorder.start(1000);stop.disabled=false;info.textContent='Recording… Tap Stop when you’re finished.';timer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop();},120000);
    }catch(error){release();if(token===session){stop.hidden=true;info.textContent=error.name==='NotAllowedError'?'Microphone access was denied. Allow it in browser settings and try again.':error.message;}}
  }
  const enhanced=new WeakSet();
  function enhance(){
    if(active && !active.isConnected)close();
    document.querySelectorAll('#guided textarea, #guided input[type=text], #entry, #plan-review input[type=text], #people-page textarea, #people-page input[type=text], #restaurants-page textarea, #restaurants-page input[type=text], #bjj-page textarea, #bjj-page input:not([type]), #bjj-page input[type=text]').forEach(field=>{
      if(field.closest('.voice-inline') || enhanced.has(field) || field.readOnly || field.type==='password')return;enhanced.add(field);
      const shell=document.createElement('span');shell.className='voice-field-shell';field.insertAdjacentElement('beforebegin',shell);shell.append(field);
      const button=document.createElement('button');button.type='button';button.className='voice-button';button.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"/><path d="M18 11v1a6 6 0 0 1-12 0v-1M12 18v3M9 21h6"/></svg>';button.setAttribute('aria-label','Dictate into '+(field.getAttribute('aria-label') || field.labels?.[0]?.textContent || 'this field'));button.title=supported?'Speak instead of typing':'Microphone recording needs Safari or Chrome over HTTPS';button.disabled=!supported;
      button.onclick=()=>{if(!field.disabled && !field.readOnly)record(field);};shell.append(button);
    });
  }
  new MutationObserver(enhance).observe(document.querySelector('main'),{childList:true,subtree:true});enhance();
  window.addEventListener('pagehide',close);
})();
