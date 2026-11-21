// 2.743.0 D (#4284) the user boundary of the service worker's Background Sync (static/sw.js swOutboxSend) in a vm sandbox
// kalmido-suite: after=p2743_d_logout_ui
// sw.js is read from the working copy (no server needed). The sandbox stands in for IndexedDB, fetch and the window list.
// - another account's entry (uid) is never sent and stays for the app; the signed-in account's entries go around it
// - /api/me names someone else, or no one (signed out, a sign-in page): nothing is sent, everything stays
// - no account remembered on this device (meta uid): not even /api/me is asked
// - the entries go in their order (n), not in the order the store hands them out
// - a temporary id: the create's real id replaces it in the next URL and in parent_id, and is kept for the app (meta swmap)
// - every write carries the app's request header and the Idempotency-Key (the entry's own key, ik before k), same origin
// - an entry without an owner (made before the sign-in was known) stops the queue (kept, noted for the app)
// - (#6334): a note's / knowledge page's change stops the queue (for the app: A9/D7); a create answered without its id
//   stops it too (the mapping is kept for the app); a milestone / a parent in data.items / a _prev are mapped too (A6); what
//   was sent is in the offline start state (D2a: a new or changed task put in, a deleted one out); (#7595) the record keeps its age
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const jres = (st, j) => new Response(JSON.stringify(j), {status: st, headers: {'content-type': 'application/json'}});

const SW = fs.readFileSync(path.join(__dirname, '..', 'static', 'sw.js'), 'utf8');
const ME = 7, OTHER = 8;

function sandbox({meUid = ME, uidMeta = ME, answer = () => jres(200, {ok: true})} = {}) {
  const idb = {ops: new Map(), meta: new Map(uidMeta ? [['uid', {k: 'uid', v: uidMeta}]] : []), s: new Map()}, sent = [];  // s: the offline start state (kalmido-start)
  const req = fn => { const r = {}; setTimeout(() => { try { r.result = fn(); if (r.onsuccess) r.onsuccess(); } catch (e) { r.error = e; if (r.onerror) r.onerror(); } }, 0); return r; };
  const fakeDb = {objectStoreNames: {contains: () => true}, close() {}, transaction: () => { const t = {objectStore: n => ({
    get: k => req(() => idb[n].get(k)), getAll: () => req(() => [...idb[n].values()]), delete: k => req(() => idb[n].delete(k)),
    put: (v, key) => { const r = req(() => idb[n].set(key ?? v.k, v)); setTimeout(() => t.oncomplete && t.oncomplete(), 5); return r; }})}; return t; }};
  let meAsked = 0;
  const ctx = vm.createContext({
    self: {addEventListener() {}, location: {origin: 'https://kalmido.example'}, clients: {matchAll: async () => []}, navigator: {}},
    caches: {open: async () => ({keys: async () => [], delete: async () => true, put: async () => {}}), match: async () => undefined},
    indexedDB: {open: () => req(() => fakeDb)},
    fetch: async (u, o = {}) => {
      if (u === '/api/me') { meAsked++; return typeof meUid === 'function' ? meUid() : jres(200, {id: meUid}); }
      const body = o.body ? JSON.parse(o.body) : undefined;
      sent.push({method: o.method || 'GET', url: u, body, headers: {...(o.headers || {})}, credentials: o.credentials});
      return answer(u, o, body);
    },
    Response, URL, setTimeout, console, atob, Uint8Array, JSON,
  });
  vm.runInContext(SW, ctx);
  const add = (...es) => { for (const e of es) idb.ops.set(e.k, e); };
  return {idb, sent, add, run: () => vm.runInContext('swOutboxSend()', ctx), meAsked: () => meAsked};
}

(async () => {
  // ================= another account's entry
  {
    const s = sandbox();
    s.add({k: 'a1', n: 1, method: 'PATCH', url: '/api/tasks/11', body: {title: 'mine one'}, uid: ME},
      {k: 'b1', n: 2, method: 'PATCH', url: '/api/tasks/12', body: {title: 'not mine'}, uid: OTHER},
      {k: 'a2', n: 3, method: 'PATCH', url: '/api/tasks/13', body: {title: 'mine two'}, uid: ME});
    await s.run();
    check(!s.sent.some(x => x.url === '/api/tasks/12' || x.body?.title === 'not mine'), 'another account\'s entry is never sent ' + JSON.stringify(s.sent.map(x => x.url)));
    check(s.sent.map(x => x.url).join() === '/api/tasks/11,/api/tasks/13', 'the own entries go, around the foreign one ' + JSON.stringify(s.sent.map(x => x.url)));
    check(s.idb.ops.has('b1') && !s.idb.ops.has('a1') && !s.idb.ops.has('a2'), 'the foreign entry stays in the store for the app, the sent ones are gone');
  }
  // ================= /api/me names someone else / no one
  for (const [what, me] of [['someone else signed in', () => jres(200, {id: OTHER})], ['signed out (401)', () => jres(401, {error: 'Not signed in', auth: 'login'})],
    ['a sign-in page (redirect)', () => new Response('', {status: 302, headers: {location: '/login'}})], ['an HTML page', () => new Response('<html></html>', {status: 200, headers: {'content-type': 'text/html'}})]]) {
    const s = sandbox({meUid: me});
    s.add({k: 'a1', n: 1, method: 'PATCH', url: '/api/tasks/11', body: {title: 'mine'}, uid: ME});
    await s.run();
    check(s.meAsked() === 1 && !s.sent.length && s.idb.ops.has('a1'), `${what}: nothing is sent, the entry stays ${JSON.stringify(s.sent)}`);
  }
  // ================= no account remembered on this device
  {
    const s = sandbox({uidMeta: null});
    s.add({k: 'a1', n: 1, method: 'PATCH', url: '/api/tasks/11', body: {title: 'mine'}, uid: ME});
    await s.run();
    check(s.meAsked() === 0 && !s.sent.length && s.idb.ops.has('a1'), 'no account remembered: not even /api/me is asked, nothing sent');
  }
  // ================= order
  {
    const s = sandbox();
    s.add({k: 'z', n: 30, method: 'PATCH', url: '/api/tasks/3', body: {title: 'third'}, uid: ME},
      {k: 'x', n: 10, method: 'PATCH', url: '/api/tasks/1', body: {title: 'first'}, uid: ME},
      {k: 'y', n: 20, method: 'PATCH', url: '/api/tasks/2', body: {title: 'second'}, uid: ME});
    await s.run();
    check(s.sent.map(x => x.body.title).join() === 'first,second,third', 'the entries go in their order ' + JSON.stringify(s.sent.map(x => x.body.title)));
  }
  // ================= temporary id
  {
    const s = sandbox({answer: (u, o) => u === '/api/tasks' && o.method === 'POST' ? jres(200, {id: 42}) : jres(200, {ok: true})});
    s.idb.meta.set('idmap', {k: 'idmap', v: {'-3': 33}});  // a real id the app already knows
    s.add({k: 'c1', n: 1, method: 'POST', url: '/api/tasks', body: {title: 'made offline'}, uid: ME, tmp: -5},
      {k: 'c2', n: 2, method: 'PATCH', url: '/api/tasks/-5', body: {title: 'renamed offline'}, uid: ME},
      {k: 'c3', n: 3, method: 'POST', url: '/api/tasks', body: {title: 'a sub task', parent_id: -5}, uid: ME},
      {k: 'c4', n: 4, method: 'POST', url: '/api/tasks/batch', body: {action: 'complete', ids: [-3, -5]}, uid: ME});
    await s.run();
    const urls = s.sent.map(x => x.method + ' ' + x.url);
    check(urls.join() === 'POST /api/tasks,PATCH /api/tasks/42,POST /api/tasks,POST /api/tasks/batch', 'the temporary id becomes the real one in the URL ' + JSON.stringify(urls));
    check(s.sent[2]?.body.parent_id === 42, 'and in parent_id ' + JSON.stringify(s.sent[2]?.body));
    check(JSON.stringify(s.sent[3]?.body.ids) === '[33,42]', 'and in the ids of a batch (also one the app knew) ' + JSON.stringify(s.sent[3]?.body));
    check(s.idb.meta.get('swmap')?.v?.[-5] === 42, 'the pair is kept for the app (swmap) ' + JSON.stringify(s.idb.meta.get('swmap')));
    check(!s.sent.some(x => /\/-\d+/.test(x.url)), 'a temporary id never goes to the server');
  }
  // ================= request header and Idempotency-Key
  {
    const s = sandbox();
    s.add({k: 'k-own', n: 1, method: 'PATCH', url: '/api/tasks/1', body: {title: 'one'}, uid: ME},
      {k: 'k-base', ik: 'k-rebased', n: 2, method: 'DELETE', url: '/api/tasks/2', uid: ME});
    await s.run();
    check(s.sent[0]?.headers['Idempotency-Key'] === 'k-own' && s.sent[1]?.headers['Idempotency-Key'] === 'k-rebased', 'Idempotency-Key = the entry\'s key, ik before k ' + JSON.stringify(s.sent.map(x => x.headers)));
    check(s.sent.every(x => x.headers['X-Requested-With'] === 'kalmido' && x.credentials === 'same-origin'), 'every write with the app\'s header, same origin');
    check(s.sent[0]?.headers['Content-Type'] === 'application/json' && s.sent[1] && s.sent[1].body === undefined && !s.sent[1].headers['Content-Type'], 'a body is JSON, a DELETE has none');
  }
  // ================= an entry without an owner
  {
    const s = sandbox();
    s.add({k: 'o1', n: 1, method: 'PATCH', url: '/api/tasks/1', body: {title: 'mine'}, uid: ME},
      {k: 'o2', n: 2, method: 'PATCH', url: '/api/tasks/2', body: {title: 'nobody\'s'}},
      {k: 'o3', n: 3, method: 'PATCH', url: '/api/tasks/3', body: {title: 'mine after'}, uid: ME});
    await s.run();
    check(s.sent.map(x => x.url).join() === '/api/tasks/1' && s.idb.ops.has('o2') && s.idb.ops.has('o3'), 'an entry of nobody stops the queue, it and the rest stay ' + JSON.stringify(s.sent.map(x => x.url)));
    check((s.idb.meta.get('swres')?.v || []).some(x => x.nouid), 'the app is told (swres nouid)');
  }

  // ================= (#6334 A9/D7) notes and knowledge pages are left to the app
  for (const u of ['/api/notes/5', '/api/lists/3/notes', '/api/wiki/pages/9']) {
    const s = sandbox();
    s.add({k: 'n0', n: 1, method: 'PATCH', url: '/api/tasks/1', body: {title: 'before'}, uid: ME},
      {k: 'n1', n: 2, method: u.endsWith('notes') ? 'POST' : 'PATCH', url: u, body: {body: 'text'}, uid: ME},
      {k: 'n2', n: 3, method: 'PATCH', url: '/api/tasks/2', body: {title: 'after'}, uid: ME});
    await s.run();
    check(s.sent.map(x => x.url).join() === '/api/tasks/1' && s.idb.ops.has('n1') && s.idb.ops.has('n2'), `A9/D7: ${u} stops the queue, it and the rest wait for the app ` + JSON.stringify(s.sent.map(x => x.url)));
  }
  // ================= (#6334 D7) a create answered without its id
  {
    const s = sandbox({answer: () => jres(200, {ok: true})});
    s.add({k: 'i1', n: 1, method: 'POST', url: '/api/tasks', body: {title: 'made offline'}, uid: ME, tmp: -5},
      {k: 'i2', n: 2, method: 'PATCH', url: '/api/tasks/-5', body: {title: 'renamed'}, uid: ME});
    await s.run();
    check(s.sent.length === 1 && s.idb.ops.has('i1') && s.idb.ops.has('i2') && !s.idb.meta.get('swmap')?.v?.[-5], 'D7: a create without id in its answer stays for the app, nothing behind it goes ' + JSON.stringify(s.sent.map(x => x.url)));
  }
  // ================= (#6334 A6) every temporary id of a body
  {
    const s = sandbox({answer: (u, o) => u === '/api/tasks' && o.method === 'POST' ? jres(200, {id: 42}) : jres(200, {ok: true})});
    s.add({k: 'm1', n: 1, method: 'POST', url: '/api/tasks', body: {title: 'a milestone', ms: 1}, uid: ME, tmp: -5},
      {k: 'm2', n: 2, method: 'PATCH', url: '/api/tasks/7', body: {milestone_id: -5, _prev: {milestone_id: -5}}, uid: ME},
      {k: 'm3', n: 3, method: 'POST', url: '/api/tasks/batch', body: {action: 'patch_each', ids: [7], data: {items: {7: {parent_id: -5, _prev: {parent_id: -5}}}}}, uid: ME});
    await s.run();
    const sent = JSON.stringify(s.sent.slice(1).map(x => x.body));
    check(s.sent.length === 3 && !/-5/.test(sent) && /"milestone_id":42/.test(sent) && /"parent_id":42/.test(sent), 'A6: milestone, a parent in data.items and the base values are mapped ' + sent);
  }
  // ================= (#6334 D2a) the offline start state follows what was sent
  {
    const s = sandbox({answer: (u, o) => u === '/api/tasks' && o.method === 'POST' ? jres(200, {id: 42, list_id: 3, title: 'made offline', status: 0, conflicts: []})
      : u === '/api/tasks/1' ? jres(200, {id: 1, list_id: 3, title: 'renamed offline', status: 0, conflicts: []}) : jres(200, {ok: true})});
    s.idb.s.set('state', {o: {v: 9, _at: 5, tasks: [{id: 1, list_id: 3, title: 'old title', status: 0}, {id: 2, list_id: 3, title: 'deleted offline', status: 0}]}, at: 1, v: 9, sat: 5});
    s.add({k: 'd1', n: 1, method: 'POST', url: '/api/tasks', body: {title: 'made offline'}, uid: ME, tmp: -5},
      {k: 'd2', n: 2, method: 'PATCH', url: '/api/tasks/1', body: {title: 'renamed offline'}, uid: ME},
      {k: 'd3', n: 3, method: 'DELETE', url: '/api/tasks/2', uid: ME});
    await s.run();
    const ts = s.idb.s.get('state')?.o?.tasks || [];
    check(ts.map(t => t.id + ':' + t.title).sort().join() === '1:renamed offline,42:made offline' && !ts.some(t => 'conflicts' in t), 'D2a: the start state holds the new task, the change, not the deleted one ' + JSON.stringify(ts));
    const rec = s.idb.s.get('state') || {};
    check(rec.v === 9 && rec.sat === 5 && rec.at === 1 && rec.o?.v === 9 && rec.o?._at === 5, '(#7595): the fold keeps the record\'s age (v / sat / at, the contract of offcache.js): a window\'s newer state still wins ' + JSON.stringify({v: rec.v, sat: rec.sat, at: rec.at}));
    s.idb.s.set('state', {s: JSON.stringify({tasks: [{id: 1, list_id: 3, title: 'old', status: 0}]}), at: 1});
    s.add({k: 'd4', n: 4, method: 'PATCH', url: '/api/tasks/1', body: {title: 'renamed offline'}, uid: ME});
    await s.run();
    check(JSON.parse(s.idb.s.get('state')?.s || '{}').tasks?.[0]?.title === 'renamed offline', 'D2a: a start state kept as JSON follows too');
  }

  console.log(`p2743_d_sw_outbox: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
