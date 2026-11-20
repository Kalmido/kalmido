// (#7150) UI tests (jsdom), fresh DB: the client orders its own writes and the states it fetches by the server's version
// kalmido-suite: fresh
// - a write's answer carries X-Kalmido-V = the version it moved the server to (the v of the next GET /api/state); a read and
//   a refused write carry none
// - a finished write stays on top of a state that predates it (v below its version) and goes once a state holds it (no time
//   limit, no client counter)
// - a state applied while a write of mine was on its way is fetched again once that write is answered (the write's change
//   shows without another action)
// - offline: a change waits in the outbox, the state is not applied over it, it goes out when the server is back
const {boot, errs, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const raw = (method, url, body, ck = CK) => fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
const call = async (method, url, body) => { const r = await raw(method, url, body); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'collab'});
  const P = (await call('POST', '/api/lists', {name: 'Garden'})).id;

  // ================= the header
  const r1 = await raw('PATCH', `/api/lists/${P}`, {name: 'Garden 1'});
  const v1 = +(r1.headers.get('X-Kalmido-V') || 0), st = await call('GET', '/api/state');
  check(r1.ok && v1 > 0 && st.v === v1, 'a write carries X-Kalmido-V = the v of the next state ' + v1 + ' / ' + st.v);
  const r2 = await raw('PATCH', `/api/lists/${P}`, {name: 'Garden 2'});
  check(+(r2.headers.get('X-Kalmido-V') || 0) === v1 + 1 || +(r2.headers.get('X-Kalmido-V') || 0) > v1, 'the next write a higher one');
  check(!(await raw('GET', '/api/state')).headers.get('X-Kalmido-V'), 'a read carries none');
  check(!(await raw('PATCH', '/api/notes/999999', {body: 'x'})).headers.get('X-Kalmido-V'), 'a refused write carries none');

  const w = await boot({user: 'alice', hash: 'l/' + P});
  check(await until(() => w.eval('!!S.me && S.lists.length > 0') && w.eval(`listById(${P})?.name`) === 'Garden 2'), 'setup: the app is up');

  // ================= a finished write on top of an older state, gone once a state holds it
  const old = JSON.stringify(await call('GET', '/api/state'));
  await w.eval(`optWrite(optSet(() => listById(${P}), {name: 'Garden opt'}), () => api('PATCH', '/api/lists/${P}', {name: 'Garden opt'}), () => {})`);
  check(w.eval('S.wv') > JSON.parse(old).v, 'the write\'s version is known in the page ' + w.eval('S.wv'));
  check(w.eval('OPT_DONE.size') === 1, 'the finished write is kept (no state holds it yet)');
  w.eval(`applyState(JSON.parse(${JSON.stringify(old)}))`);
  check(w.eval(`listById(${P}).name`) === 'Garden opt', 'an older state does not take the own change back');
  check(w.eval('OPT_DONE.size') === 1, '… the write is still kept');
  await w.eval('load()');
  check(w.eval('OPT_DONE.size') === 0 && w.eval(`listById(${P}).name`) === 'Garden opt', 'a state that holds it: nothing kept, the server\'s name');

  // ================= a state applied while a write of mine is on its way: fetched again when it is answered
  const f1 = w.fetch, held = []; let gets = 0;
  w.fetch = (u, o = {}) => {
    if (/\/api\/state\?/.test(String(u)) && (o.method || 'GET') === 'GET') gets++;
    if (String(u).endsWith(`/api/lists/${P}`) && o.method === 'PATCH') return new Promise((res, rej) => held.push(() => f1(u, o).then(res, rej)));
    return f1(u, o);
  };
  const wr = w.eval(`api('PATCH', '/api/lists/${P}', {name: 'Garden held'})`);
  check(await until(() => held.length === 1 && w.eval('S.wfly') === 1), 'a write on its way');
  await w.eval('load()');
  check(w.eval('S.wvAgain') === true && w.eval(`listById(${P}).name`) !== 'Garden held', 'the state came while it was on its way: marked to be fetched again');
  const g0 = gets;
  held.shift()(); await wr;
  check(await until(() => gets > g0 && w.eval(`listById(${P}).name`) === 'Garden held' && !w.eval('S.wvAgain')), 'answered: the state fetched again on its own, the change shows ' + (gets - g0));
  w.fetch = f1;

  // ================= offline: the outbox waits, the state is not applied over the change, it goes out later
  const T = (await call('POST', '/api/tasks', {title: 'Water the roses', list_id: P})).id;
  await w.eval('load()');
  check(await until(() => !!w.eval(`S.tasks.get(${T})`)), 'a task to change');
  w.fetch = (u, o = {}) => /\/api\//.test(String(u)) ? Promise.reject(new TypeError('offline')) : f1(u, o);
  w.eval(`enqueue('PATCH', '/api/tasks/${T}', {title: 'Water the roses twice'})`);
  check(w.eval(`S.tasks.get(${T}).title`) === 'Water the roses twice' && w.eval('OUT.q.length') === 1, 'offline: drawn at once, waiting in the outbox');
  w.fetch = f1;
  await w.eval('load()');
  check(await until(async () => (await call('GET', `/api/tasks/${T}`)).title === 'Water the roses twice' && w.eval('OUT.q.length') === 0), 'back online: sent, the outbox empty');
  check(w.eval(`S.tasks.get(${T}).title`) === 'Water the roses twice', '… the change stays in the page');

  check(errs.length === 0, 'no script errors: ' + errs.join(' | '));
  w.close();
  console.log(`p21474_a_order_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
