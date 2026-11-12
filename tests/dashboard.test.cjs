/* Execute the shipped polling script against a minimal DOM boundary, without
 * claiming this replaces phone/browser accessibility or TLS acceptance tests. */
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../src/cognisight/caregiver/static/dashboard.js'),'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));

class Element {
  constructor() { this.textContent=''; this.children=[]; this.hidden=true; }
  replaceChildren(...children) { this.children=children; }
  appendChild(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
}
function sample() {
  return {schema_version:1,has_mock_data:false,health:{camera:'ready'},indoor:{status:'unavailable'},
    recognition:{status:'live',data_source:'live',age_seconds:0,max_age_seconds:1,observed_at:null,
      people:[{name:'Synthetic profile',relationship:'test fixture',note:'<script>untrusted text</script>'}]},
    outdoor:{status:'live',data_source:'live',age_seconds:0,max_age_seconds:10,observed_at:null,
      latitude:0,longitude:0,last_known:null}};
}
async function boot(replies) {
  const elements=new Map(), timers=new Map(), intervals=[], listeners={};
  let now=0, nextId=0;
  const document={hidden:false,
    getElementById(id) { if(!elements.has(id)) elements.set(id,new Element()); return elements.get(id); },
    createElement() { return new Element(); },
    addEventListener(name,callback) { listeners[name]=callback; }};
  vm.runInNewContext(source,{document,performance:{now:()=>now},AbortController,Date,
    setTimeout(callback,delay) { const id=++nextId; timers.set(id,{callback,delay}); return id; },
    clearTimeout(id) { timers.delete(id); },setInterval(callback) { intervals.push(callback); },
    fetch: async () => {
      const reply=replies.shift();
      if(reply instanceof Error) throw reply;
      return {status:reply.status??200,ok:!reply.status || reply.status===200,redirected:false,
        headers:{get:()=> 'application/json'},json:async()=>reply.data};
    }});
  await flush();
  return {elements,document,listeners,
    tick(seconds) { now+=seconds*1000; intervals.forEach(fn=>fn()); },
    async poll() { const item=[...timers].find(([,v])=>[500,5000].includes(v.delay)); assert.ok(item); timers.delete(item[0]); await item[1].callback(); await flush(); },
    nextPollDelay:()=>[...timers.values()].find(v=>[500,5000].includes(v.delay))?.delay,
    pendingPolls:()=>[...timers.values()].filter(v=>[500,5000].includes(v.delay)).length};
}

test('source freshness expires independently of successful browser polling',async()=>{
  const app=await boot([{data:sample()}]);
  assert.equal(app.elements.get('people').children.length,1);
  assert.match(app.elements.get('coordinates').textContent,/Latitude 0.000000/);
  const note=app.elements.get('people').children[0].children[2];
  assert.equal(note.textContent,'<script>untrusted text</script>');
  app.tick(2);
  assert.equal(app.elements.get('people').children.length,0);
  assert.match(app.elements.get('recognition-status').textContent,/stale/i);
  app.tick(9);
  assert.match(app.elements.get('outdoor-status').textContent,/stale/i);
  assert.doesNotMatch(app.elements.get('coordinates').textContent,/Latitude/);
});

test('expired authentication clears sensitive data and stops polling',async()=>{
  const app=await boot([{data:sample()},{status:401}]);
  await app.poll();
  assert.equal(app.elements.get('people').children.length,0);
  assert.equal(app.elements.get('health').children.length,0);
  assert.match(app.elements.get('connection').textContent,/Session ended/);
  assert.equal(app.pendingPolls(),0);
});

test('network failure clears location and visible mock labels, then retries',async()=>{
  const data=sample(); data.has_mock_data=true; data.recognition.status='mock';
  const app=await boot([{data},new Error('network unavailable')]);
  assert.equal(app.elements.get('demo').hidden,false);
  await app.poll();
  assert.equal(app.elements.get('demo').hidden,true);
  assert.equal(app.elements.get('people').children.length,0);
  assert.match(app.elements.get('connection').textContent,/Disconnected/);
  assert.equal(app.pendingPolls(),1);
});


test('healthy refreshes are faster than recognition expiry',async()=>{
  const app=await boot([{data:sample()},{data:sample()}]);
  assert.ok(app.nextPollDelay()<1000, 'Next refresh must occur before the one-second observation expiry');
  app.tick(.6);
  await app.poll();
  app.tick(.6);
  assert.equal(app.elements.get('people').children.length,1);
  assert.doesNotMatch(app.elements.get('recognition-status').textContent,/stale/i);
});
