/* Apply before the first paint; the schedule follows this device's local clock. */
(() => {
  const root=document.documentElement;
  const bar=document.querySelector('meta[name="theme-color"]');
  const dayColor=bar?.getAttribute('content') || '#829B87';
  let timer;
  function refresh(){
    window.clearTimeout(timer);
    const now=new Date(),hour=now.getHours(),night=hour>=21 || hour<7;
    root.dataset.theme=night?'night':'day';
    bar?.setAttribute('content',night?'#171e1d':dayColor);
    const next=new Date(now);
    if(hour<7)next.setHours(7,0,0,0);
    else if(hour<21)next.setHours(21,0,0,0);
    else {next.setDate(next.getDate()+1);next.setHours(7,0,0,0);}
    timer=window.setTimeout(refresh,Math.max(1000,next-now));
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  window.addEventListener('focus',refresh);
  window.addEventListener('pageshow',refresh);
  refresh();
})();
