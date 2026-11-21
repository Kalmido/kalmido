// #6366 UI test: the start draws the state kept on this device first and syncs behind it (Firefox, the real service worker).
// kalmido-suite: fresh
// freelancer-matrix: tasks (alice has no organisation: her private workspace, her own list)
// Firefox reaches the test server only through a small TCP relay of this file (an own port on 127.0.0.1, as p2579_d_sw_ui).
// The relay can HOLD: every byte the browser sends waits in the relay until release() - the line hangs the way a dead spot of
// the mobile network does (the page, the worker and the API get no answer, nothing is refused).
// - the network hangs: the worker serves the kept app page after its race (sw.js SW_RACE_MS), the app draws the kept state
//   (a title the server has changed since), the header's chip says "Syncing" with the state's age (no "up to date"), a write
//   goes into the queue; released: the server's state replaces the kept one, the chip goes, the write reaches the server once
// - the session ended elsewhere (signed out with a plain request) while the network hangs: the kept state is drawn (the gate
//   devCopyOk is the device's only knowledge); released: the 401 of the sync clears the screen (sign-in, the app hidden) and the
//   start record in IndexedDB is gone (devEnd)
// Without the change of #6366 the held start shows the loading screen until the release (red: nothing of the kept state).
// The waits are on states (the page's state, the relay's held requests, the server's rows), never on a fixed time.
// P6366A_SHOTS=<dir> = screenshots.
const net = require('net');
const {B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p6366_a_devstart_ui', check, shots: 'P6366A_SHOTS', lazy: true, allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = (fn, ms = 15000) => require('./boot').until(fn, {timeout: ms, step: 150});

// the relay: 127.0.0.1:<own port> -> the test server; hold = what the browser sends waits (in order) until release()
function relay(target) {
  const to = new URL(target);
  const R = {hold: false, q: [], held: 0, port: 0, srv: null};
  R.release = () => { R.hold = false; for (const f of R.q.splice(0)) f(); };
  const conn = c => {
    const s = net.connect(+to.port || 80, to.hostname);
    const end = () => { c.destroy(); s.destroy(); };
    c.on('error', end); s.on('error', end); c.on('close', end); s.on('close', end);
    c.on('data', d => { if (R.hold) { R.held++; R.q.push(() => s.write(d)); } else s.write(d); });
    s.pipe(c);
  };
  R.open = () => new Promise((res, no) => { R.srv = net.createServer(conn); R.srv.once('error', no); R.srv.listen(0, '127.0.0.1', () => { R.port = R.srv.address().port; res(R.port); }); });
  R.close = () => new Promise(res => (R.srv ? R.srv.close(() => res()) : res()));
  return R;
}
// the start record in IndexedDB, read with an own open() of the database: its task titles, or null
const REC = `new Promise(res => { const r = indexedDB.open('kalmido-start'); r.onupgradeneeded = () => r.result.createObjectStore('s');
  r.onsuccess = () => { const d = r.result; if (!d.objectStoreNames.contains('s')) { d.close(); return res(null); } const g = d.transaction('s').objectStore('s').get('state');
    g.onsuccess = () => { const x = g.result; d.close(); res(x ? (x.o || JSON.parse(x.s)).tasks.map(t => t.title) : null); }; g.onerror = () => { d.close(); res('err'); }; };
  r.onerror = () => res('err'); })`;

(async () => {
  check((await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})})).ok, 'setup');
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const L = (await call('POST', '/api/lists', {name: 'Shed'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Oil the hinges', list_id: L})).id;
  const T2 = (await call('POST', '/api/tasks', {title: 'Sharpen the saw', list_id: L})).id;
  check(L > 0 && T > 0 && T2 > 0, 'a list with two tasks');
  const SRV = 'Oil the hinges (changed on the server)', MINE = 'Sharpen the saw (changed on the kept state)';
  const title = async id => ((await call('GET', '/api/state')).tasks || []).find(t => t.id === id)?.title;

  const R = relay(B);
  await R.open();
  const O = `http://127.0.0.1:${R.port}/`;

  await firefox(async ({cmd, ctx, ev, nav, until: pageUntil, shot}) => {
    const pu = (expr, ms = 15000) => pageUntil(expr, {timeout: ms, step: 150});
    const go = url => cmd('browsingContext.navigate', {context: ctx, url, wait: 'none'});  // a held line never completes a load
    await nav(O + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: sign-in over the relay');

    // ---- online: the start state kept, the worker holds the page and the module offcache
    await nav(O + `#l/${L}`);
    check(await pu(`typeof S !== 'undefined' && S.booted && !!document.querySelector('#view .trow[data-id="${T}"]')`), 'online: the list opens');
    check(await pu(`typeof OC !== 'undefined' && OC.wrote > 0`), 'online: the start state is kept in IndexedDB');
    check(await pu(`navigator.serviceWorker.ready.then(() => caches.keys()).then(async ks => { ks = ks.filter(k => k.startsWith('tasks-shell')); if (!ks.length || !navigator.serviceWorker.controller) return false;
      const c = await caches.open(ks.pop()); return !!(await c.match('/', {ignoreSearch: true})) && !!(await c.match('/static/js/offcache.js', {ignoreSearch: true})); })`, 60000),
      'online: the worker controls the page and holds the page and offcache.js');
    check(await ev(`!document.querySelector('#top .offline')`), 'online: no sync chip');

    // ---- the server changes meanwhile, then the line hangs
    const ch = await call('PATCH', `/api/tasks/${T}`, {title: SRV});
    check(ch.id === T && ch.title === SRV, 'a change on the server (another device) ' + JSON.stringify({id: ch.id, title: ch.title}));
    await nav(O + 'static/icon.svg');  // a new document below (the same address with its hash would stay in the page)
    R.hold = true; R.held = 0;
    await go(O + `#l/${L}`);
    check(await pu(`typeof S !== 'undefined' && S.booted && !!document.querySelector('#view .trow[data-id="${T}"]')`, 30000),
      'network hangs: the app is drawn (the worker served the kept page after its race, the app the kept state)');
    check(R.hold && R.held > 0, 'network hangs: the relay holds the page\'s requests, nothing was answered ' + R.held);
    check(await ev(`!ld_net && !!S.devOld && document.querySelector('#view .trow[data-id="${T}"]').textContent.includes('Oil the hinges') && !document.querySelector('#view').textContent.includes('changed on the server')`),
      'network hangs: the kept state is shown (the old title), not the server\'s');
    const chip = await ev(`(() => { const b = document.querySelector('#top .offline'); return b ? {cls: b.className, w: b.textContent, t: b.title, want: S.devOld.at ? stateFrom(S.devOld.at) : ''} : null; })()`);
    check(chip && /devold/.test(chip.cls) && chip.w.includes('Syncing') && !!chip.want && chip.t.includes(chip.want), 'network hangs: the header\'s chip says "Syncing" with the state\'s age ' + JSON.stringify(chip));
    check(await ev(`!document.body.textContent.includes('Up to date') && !document.querySelector('#boot:not(.out)')`), 'network hangs: nothing says "up to date", the loading screen is gone');
    await shot('p6366a-held.png');
    const w = await ev(`Promise.resolve(api('PATCH', '/api/tasks/${T2}', {title: ${JSON.stringify(MINE)}})).then(() => OUT.q.length, e => 'failed: ' + e.message)`);
    check(w === 1, 'network hangs: a write on the kept state goes into the queue (as offline) ' + w);

    // ---- released: the server's state replaces the kept one, the write arrives once
    R.release();
    check(await pu(`!S.devOld && ld_net && document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('changed on the server')`, 30000), 'released: the server\'s state is drawn');
    check(await pu(`!document.querySelector('#top .offline') && OUT.q.length === 0`, 30000), 'released: the chip goes, the queue is sent');
    check(await until(async () => (await title(T2)) === MINE, 30000), 'released: the write of the kept state reached the server');
    check(await pu(`document.querySelector('#view .trow[data-id="${T2}"]')?.textContent.includes('changed on the kept state')`), 'released: the page shows the own write');

    // ---- the session ended elsewhere while the network hangs: drawn, then the 401 of the sync clears it
    await nav(O + 'static/icon.svg');
    check(Array.isArray(await ev(REC)), 'session ended: the start record is there before');
    check(await ev(`fetch('/api/auth/logout', {method: 'POST', headers: {'X-Requested-With': 'kalmido'}}).then(r => r.status)`) < 300, 'session ended: signed out with a plain request (the app did not see it)');
    R.hold = true; R.held = 0;
    await go(O + `#l/${L}`);
    check(await pu(`typeof S !== 'undefined' && S.booted && !!S.devOld && !!document.querySelector('#view .trow[data-id="${T}"]')`, 30000), 'session ended, network hangs: the kept state is drawn (the accepted rest of #6500)');
    R.release();
    // the 401 of the sync (built-in login: the sign-in on top, devWipe) or of a request before it (a reload: the sign-in)
    const gone = await pu(`!!document.querySelector('.authscreen') && !document.querySelector('#view .trow') && !S.devOld`, 30000);
    check(gone, 'session ended, released: the 401 clears the screen, the sign-in takes over ' + (gone ? '' : JSON.stringify(await ev(`({auth: !!document.querySelector('.authscreen'), rows: document.querySelectorAll('#view .trow').length, old: typeof S !== 'undefined' && !!S.devOld, hidden: document.getElementById('app')?.hidden, url: location.href})`).catch(e => e.message))));
    check(await pu(`(${REC}).then(r => r == null)`), 'session ended, released: the start record in IndexedDB is gone (devEnd)');
    await shot('p6366a-ended.png');
  }, false);
  R.release(); await R.close();

  console.log(`p6366_a_devstart_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); console.log('p6366_a_devstart_ui: crashed'); process.exit(1); });
