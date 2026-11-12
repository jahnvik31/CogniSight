'use strict';
(() => {
  let snapshot = null, receivedAt = 0, running = false, stopped = false, timer;
  const byId = id => document.getElementById(id);
  const setText = (id,text) => { byId(id).textContent = text; };
  const words = value => String(value || 'unavailable').replaceAll('_',' ');
  function clearSensitive(message) {
    snapshot = null; byId('demo').hidden=true;
    byId('people').replaceChildren(); byId('health').replaceChildren();
    setText('coordinates','No current usable GPS fix.'); setText('last-known','');
    setText('recognition-age',''); setText('outdoor-age','');
    setText('recognition-status','Unavailable'); setText('outdoor-status','Unavailable');
    setText('connection',message);
  }
  function render() {
    if (!snapshot) return;
    const elapsed = (performance.now()-receivedAt)/1000;
    byId('demo').hidden = !snapshot.has_mock_data;
    for (const key of ['recognition','outdoor']) {
      const section = snapshot[key];
      const age = section.age_seconds === null ? null : section.age_seconds+elapsed;
      let status = section.status;
      if (status === 'live' && (age === null || age >= section.max_age_seconds)) status = 'stale';
      setText(key+'-status',words(status)+' — '+words(section.data_source));
      let time = age === null ? 'Observation age unavailable.' : 'Observation age: '+Math.floor(age)+' seconds.';
      if (section.observed_at !== null) time += ' Observed '+new Date(section.observed_at*1000).toISOString()+'.';
      setText(key+'-age',time);
      if (key === 'recognition') {
        byId('people').replaceChildren();
        if (status === 'live' || status === 'mock') for (const person of section.people) {
          const card = document.createElement('div'); card.className='person';
          for (const value of [person.name,person.relationship,person.note]) {
            if (!value) continue; const p=document.createElement('p'); p.textContent=value; card.appendChild(p);
          }
          byId('people').appendChild(card);
        }
      } else {
        setText('coordinates',(status === 'live' || status === 'mock') && section.latitude !== null ?
          'Latitude '+section.latitude.toFixed(6)+', longitude '+section.longitude.toFixed(6) : 'No current usable GPS fix.');
        const last=section.last_known;
        setText('last-known',last ? 'Last known location (historical): '+last.latitude.toFixed(6)+', '+last.longitude.toFixed(6)+
          (last.age_seconds === null ? '. Age unavailable.' : '. Age '+Math.floor(last.age_seconds+elapsed)+' seconds.') : '');
      }
    }
    setText('indoor-status','Unavailable — not integrated.');
  }
  async function poll() {
    if (running || stopped || document.hidden) return;
    running=true;
    const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),4000);
    try {
      const response=await fetch('/dashboard/state',{credentials:'same-origin',cache:'no-store',signal:controller.signal});
      if (response.status===401 || response.status===403 || response.redirected) {
        stopped=true; clearSensitive('Session ended. Sign in again to view data.'); return;
      }
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('unavailable');
      const data=await response.json();
      if (data.schema_version!==1 || !data.recognition || !data.outdoor || !data.indoor || !data.health) throw new Error('invalid');
      snapshot=data; receivedAt=performance.now(); setText('connection','Connected to device. Source status is shown separately.');
      byId('health').replaceChildren();
      for (const [key,value] of Object.entries(data.health)) {
        const dt=document.createElement('dt'),dd=document.createElement('dd'); dt.textContent=words(key); dd.textContent=words(value);
        byId('health').append(dt,dd);
      }
      render();
    } catch (_) { clearSensitive('Disconnected — current data unavailable. Reconnecting…'); }
    finally { clearTimeout(timeout); running=false; if(!stopped) timer=setTimeout(poll,5000); }
  }
  document.addEventListener('visibilitychange',()=>{ clearTimeout(timer); if(!document.hidden) poll(); else render(); });
  setInterval(render,1000); poll();
})();
