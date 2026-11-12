'use strict';
(() => {
  let snapshot = null, receivedAt = 0, running = false, stopped = false, timer;
  const byId = id => document.getElementById(id);
  const setText = (id, text) => {
    const node = byId(id);
    if (node.textContent !== text) node.textContent = text;
  };
  const words = value => String(value || 'unavailable').replaceAll('_', ' ');
  const title = value => { const text = words(value); return text.charAt(0).toUpperCase() + text.slice(1); };
  const labels = {live: 'Current', no_fix: 'No fix', disconnected: 'Disconnected', stale: 'Stale',
    paused: 'Paused', uncalibrated: 'Setup required', unavailable: 'Unavailable', invalid: 'Invalid data',
    mock: 'Simulated', starting: 'Starting', ready: 'Ready', not_integrated: 'Not integrated'};
  function tone(status) {
    if (['live', 'ready', 'available'].includes(status)) return 'status-current';
    if (['stale', 'no_fix', 'uncalibrated', 'paused', 'starting'].includes(status)) return 'status-warning';
    if (['disconnected', 'invalid', 'error', 'failed'].includes(status)) return 'status-error';
    return status === 'mock' ? 'status-simulated' : 'status-neutral';
  }
  function pill(id, status) {
    setText(id, labels[status] || title(status));
    byId(id).className = 'status-pill ' + tone(status);
  }
  function sourceLabel(source) {
    return source === 'mock' ? 'Demo source' : source === 'live' ? 'Device observation' : 'No current data';
  }
  function ageText(age) {
    if (age < 1) return 'just now';
    if (age < 60) return Math.floor(age) + 's ago';
    if (age < 3600) return Math.floor(age / 60) + 'm ago';
    return Math.floor(age / 3600) + 'h ago';
  }
  function clearSensitive(message) {
    snapshot = null;
    byId('demo').hidden = true;
    byId('people').replaceChildren();
    byId('health').replaceChildren();
    setText('coordinates', 'No current usable GPS fix.');
    setText('last-known', '');
    setText('recognition-age', '');
    setText('outdoor-age', '');
    pill('recognition-status', 'unavailable');
    pill('outdoor-status', 'unavailable');
    setText('recognition-source', 'No current data');
    setText('outdoor-source', 'No current data');
    setText('recognition-empty', 'No current recognition observation.');
    byId('recognition-empty').hidden = false;
    setText('connection', message);
  }
  function render() {
    if (!snapshot) return;
    const elapsed = (performance.now() - receivedAt) / 1000;
    byId('demo').hidden = !snapshot.has_mock_data;
    for (const key of ['recognition', 'outdoor']) {
      const section = snapshot[key];
      const age = section.age_seconds === null ? null : section.age_seconds + elapsed;
      let status = section.status;
      if (status === 'live' && (age === null || age >= section.max_age_seconds)) status = 'stale';
      pill(key + '-status', status);
      setText(key + '-source', sourceLabel(section.data_source));
      let time = age === null ? 'Observation time unavailable' : 'Observed ' + ageText(age);
      if (section.observed_at !== null) {
        const utc = new Date(section.observed_at * 1000).toISOString().replace('T', ' ').replace('.000Z', ' UTC');
        time += ' · ' + utc;
      }
      setText(key + '-age', time);
      if (key === 'recognition') {
        byId('people').replaceChildren();
        const eligible = status === 'live' || status === 'mock';
        if (eligible) for (const person of section.people) {
          const card = document.createElement('div');
          card.className = 'person';
          for (const value of [person.name, person.relationship, person.note]) {
            if (!value) continue;
            const p = document.createElement('p');
            p.textContent = value;
            card.appendChild(p);
          }
          byId('people').appendChild(card);
        }
        byId('recognition-empty').hidden = eligible && section.people.length > 0;
        setText('recognition-empty', eligible ? 'No confirmed person in view.' :
          status === 'paused' ? 'Recognition is paused.' :
          status === 'uncalibrated' ? 'Recognition needs to be calibrated on the Pi.' :
          status === 'stale' ? 'The last recognition observation has expired.' : 'Recognition is not available.');
      } else {
        setText('coordinates', (status === 'live' || status === 'mock') && section.latitude !== null ?
          'Latitude ' + section.latitude.toFixed(6) + ', longitude ' + section.longitude.toFixed(6) :
          'No current usable GPS fix.');
        const last = section.last_known;
        setText('last-known', last ? 'Last known location · ' + last.latitude.toFixed(6) + ', ' + last.longitude.toFixed(6) +
          (last.age_seconds === null ? ' · Time unavailable' : ' · ' + ageText(last.age_seconds + elapsed)) + ' (historical)' : '');
      }
    }
    pill('indoor-status', 'not_integrated');
  }
  async function poll() {
    if (running || stopped || document.hidden) return;
    running = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch('/dashboard/state', {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if (response.status === 401 || response.status === 403 || response.redirected) {
        stopped = true;
        clearSensitive('Session ended. Sign in again to view observations.');
        return;
      }
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('unavailable');
      const data = await response.json();
      if (data.schema_version !== 1 || !data.recognition || !data.outdoor || !data.indoor || !data.health) throw new Error('invalid');
      snapshot = data;
      receivedAt = performance.now();
      setText('connection', 'Connected to dashboard. Observation status is shown below.');
      byId('health').replaceChildren();
      for (const [key, value] of Object.entries(data.health)) {
        const dt = document.createElement('dt'), dd = document.createElement('dd'), badge = document.createElement('span');
        dt.textContent = title(key);
        badge.textContent = labels[value] || title(value);
        badge.className = 'status-pill ' + tone(value);
        dd.appendChild(badge);
        byId('health').append(dt, dd);
      }
      render();
    } catch (_) {
      clearSensitive('Disconnected — current observations unavailable. Reconnecting…');
    } finally {
      clearTimeout(timeout);
      running = false;
      if (!stopped) timer = setTimeout(poll, snapshot ? 500 : 5000);
    }
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (!document.hidden) poll(); else render();
  });
  setInterval(render, 1000);
  poll();
})();
