/* Keep a loaded media resource when jumping between passages in the same volume. */
(function(root){
  function create(video,{status=()=>{}}={}){
    let source='',pending=null,metadataReady=false,generation=0;
    const seconds=value=>Number.isFinite(Number(value))?Math.max(0,Number(value)):0;
    const label=value=>`${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}`;
    function applyTarget(){
      if(pending===null || !metadataReady)return;
      const target=Number.isFinite(video.duration)?Math.min(pending,Math.max(0,video.duration-.05)):pending;
      try{video.currentTime=target;pending=null;}catch{/* Retry when the media becomes seekable. */}
    }
    function play(){
      const token=++generation;
      try{Promise.resolve(video.play()).catch(error=>{
        if(token===generation && error.name!=='AbortError')status('Tap the video’s play control to start playback.');
      });}catch{status('Tap the video’s play control to start playback.');}
    }
    video.addEventListener('loadedmetadata',()=>{
      // A late event from the outgoing resource must not apply a new timestamp.
      if(video.currentSrc && video.currentSrc.split('#')[0]!==video.src.split('#')[0])return;
      metadataReady=true;applyTarget();
    });
    video.addEventListener('canplay',applyTarget);
    video.addEventListener('playing',()=>status(''));
    video.addEventListener('waiting',()=>status('Buffering video…'));
    video.addEventListener('stalled',()=>status('Waiting for the video connection…'));
    video.addEventListener('error',()=>status('This video could not load. Check your connection and reopen the volume.'));
    return {
      open(url,target=0){
        pending=seconds(target);
        status(pending?`Jumping to ${label(pending)}…`:'Loading video…');
        if(source!==url || video.error){
          source=url;metadataReady=false;
          video.src=url+(pending?`#t=${pending}`:'');
        }else applyTarget();
        // Start within the tap gesture; transcript loading must never gate playback.
        play();
      },
      seek(target){pending=seconds(target);status(`Jumping to ${label(pending)}…`);applyTarget();play();}
    };
  }
  function fullscreen(video){
    const doc=video.ownerDocument;
    if(doc.fullscreenElement)return doc.exitFullscreen();
    if(video.webkitDisplayingFullscreen)return video.webkitExitFullscreen();
    if(typeof video.requestFullscreen==='function')return video.requestFullscreen();
    if(typeof video.webkitEnterFullscreen==='function')return video.webkitEnterFullscreen();
    if(typeof video.webkitRequestFullscreen==='function')return video.webkitRequestFullscreen();
    throw Error('Full screen is not supported in this browser. Use the video’s native controls.');
  }
  const api={create,fullscreen};
  if(typeof module!=='undefined')module.exports=api;else root.BJJPlayer=api;
})(typeof globalThis!=='undefined'?globalThis:this);
