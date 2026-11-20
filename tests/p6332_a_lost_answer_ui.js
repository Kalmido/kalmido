// (#6332) UI tests (jsdom), fresh DB: a write whose answer gets lost after the server did the work is not done twice
// - duplicate a task online, the answer is lost (proxy 502 after the server made the copy): the write goes into the queue under
//   the key it was first sent with, the repeat gets the first answer - one copy, not two
// - the chat keeps a message's client_id over a failed try (same text and files = same id; another text or other files = new)
// - an upload sent again after a lost answer carries the same key: the files are attached once
// kalmido-suite: fresh
const {boot, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const lost = () => new Response('<html><body>Bad gateway</body></html>', {status: 502, headers: {'content-type': 'text/html'}});

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const P = (await call('POST', '/api/lists', {name: 'Garden'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Plant tulips', list_id: P})).id;
  const w = await boot({user: 'alice', hash: 'l/' + P});
  // every write that leaves the window {m, p, key}; loseOnce(m, p): the server does the work, the answer is replaced by a 502
  const calls = [], of = w.fetch; let lose = null;
  w.fetch = async (u, o = {}) => {
    const m = (o.method || 'GET').toUpperCase(), p = new URL(String(u), B).pathname;
    if (m !== 'GET') calls.push({m, p, key: (o.headers || {})['Idempotency-Key'] || ''});
    const r = await of(u, o);
    if (lose && lose(m, p)) { lose = null; return lost(); }
    return r;
  };
  check(await until(() => w.eval('OUT.me === S.me.id')), 'setup: the server said who is logged in');
  const copies = async () => ((await call('GET', '/api/state')).tasks || []).filter(t => t.list_id === P && t.title === 'Plant tulips').length;

  // ================= duplicate: the answer is lost after the copy was made
  calls.length = 0;
  lose = (m, p) => m === 'POST' && p === `/api/tasks/${T}/duplicate`;
  await w.eval(`api('POST', '/api/tasks/${T}/duplicate', {}).catch(e => e.message)`);
  const first = calls.find(c => c.m === 'POST' && c.p === `/api/tasks/${T}/duplicate`);
  check(!!first && !!first.key, 'the online try already carries an idempotency key ' + JSON.stringify(first));
  const q = w.eval('outSync()').filter(x => x.url === `/api/tasks/${T}/duplicate`);
  check(q.length === 1 && q[0].k === first?.key, 'the lost write waits in the queue under the SAME key ' + JSON.stringify(q.map(x => x.k)));
  check(await until(() => { w.eval('OUT.down = false; setOnline(true); flush()'); return w.eval('OUT.q.length') === 0 && !w.eval('OUT.flushing'); }, 20),
        'the queue sent it again');
  const again = calls.filter(c => c.m === 'POST' && c.p === `/api/tasks/${T}/duplicate`);
  check(again.length === 2 && again[1].key === first?.key, 'the repeat went with the first key ' + JSON.stringify(again));
  const n = await copies();
  check(n === 2, `one copy, not two (tasks named "Plant tulips": ${n})`);

  // ================= the chat: the id belongs to the message, not to the try
  const r = w.eval(`(() => { const f = [{name: 'a.png', size: 3, lastModified: 1}], a = csdAdd('t:1', 'Hello', [], f); csdDone('t:1', a); csdKeep('t:1', a);
    const b = csdId('t:1', 'Hello', f); csdKeep('t:1', b); const c = csdId('t:1', 'Hello', [{name: 'b.png', size: 4, lastModified: 1}]);
    csdKeep('t:1', b); const d = csdId('t:1', 'Hello again', f); const e = csdId('t:1', 'Hello', f);
    return [a.cid === b.cid, c.cid !== b.cid, d.cid !== b.cid, e.cid !== b.cid]; })()`);
  check(r[0], 'sent again after a failed try: the same client_id');
  check(r[1], 'other files: a new client_id');
  check(r[2], 'another text: a new client_id');
  check(r[3], 'a try that went through (nothing kept): the next message gets a new client_id');
  const r2 = w.eval(`(() => { const a = csdId('t:2', 'ok', []); csdKeep('t:2', a); CSD.again['t:2'].at -= CSD_AGAIN_MS + 1000; return csdId('t:2', 'ok', []).cid !== a.cid; })()`);
  check(r2, 'the kept id expires: the same text much later is a new message');

  // ================= an upload sent again after a lost answer: attached once
  calls.length = 0;
  const file = 'new File(["hello"], "note.txt", {type: "text/plain", lastModified: 5})';
  lose = (m, p) => m === 'POST' && p === `/api/tasks/${T}/attachments`;
  await w.eval(`uploadFiles(${T}, [${file}])`);
  await w.eval(`uploadFiles(${T}, [${file}])`);
  const ups = calls.filter(c => c.m === 'POST' && c.p === `/api/tasks/${T}/attachments`);
  check(ups.length === 2 && ups[0].key && ups[0].key === ups[1].key, 'the same files again: the same key ' + JSON.stringify(ups));
  const t = await call('GET', `/api/tasks/${T}`);
  check((t.attachments || []).length === 1, 'attached once ' + JSON.stringify((t.attachments || []).map(a => a.name)));
  await w.eval(`uploadFiles(${T}, [new File(["other"], "other.txt", {type: "text/plain", lastModified: 6})])`);
  const ups2 = calls.filter(c => c.m === 'POST' && c.p === `/api/tasks/${T}/attachments`);
  check(ups2.length === 3 && ups2[2].key !== ups2[1].key, 'other files: a new key');

  console.log(F.length ? `FAILED ${F.length} of ${ok + F.length}` : `OK ${ok}`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
