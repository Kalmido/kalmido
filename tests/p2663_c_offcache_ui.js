// 2.663.0 UI test, part C (#4200): the offline start state in IndexedDB (static/js/offcache.js) and the open table's poll with
// its etag (static/js/sheets.js shvLoad). Firefox (real IndexedDB), fresh DB, invented names only.
// kalmido-suite: fresh
// alice has no organisation here (her private workspace, her own list and table)
// - online: the state is written to IndexedDB "kalmido-start" when idle (module offcache loaded on demand), as a structured
//   clone ({o}: no locked list), and no copy stays in localStorage
// - the old localStorage copy (a browser of before 2.663) with the network gone: a new start shows it, takes it over into
//   IndexedDB and removes it; a second start without network shows the same state from IndexedDB
// - (#7595): ONE place per browser - with IndexedDB the record, never a localStorage copy after a refused write: the write is
//   said once (console.warn, the client error report), the next change opens a fresh connection and lands (Zusatz 2), and the
//   offline start after it shows that state. The newer record wins: the old copy in both places (older / newer than the
//   record), an older window writing after a newer one. F1 (#6340): another tab signed out - this one writes nothing back,
//   with the gate devCopyOk alone (no own account check any more)
// - (#6340): an offline start names the real age of its state (the header's chip: "State from <day>, <time>"); a page
//   being hidden writes the newest state at once (an own change made just before is in the next offline start)
// - (#7549): an indexedDB.open that never answers (WebKit at a start): the app starts all the same - offline without a copy
//   "Server not reachable" with Try again, offline with the old localStorage copy that copy, online the server's state;
//   the hang is reported once (clienterr), never a blank page; (#7595) the state goes to no localStorage copy meanwhile
// - sign-out (devEnd logout): the record goes
// - an open table polled with nothing changed: {unchanged}, the same sheet object, nothing drawn again; a cell changed on the
//   server: the poll loads it and draws
// The network is cut for the app's requests (/api/) by a preload script (the page and its scripts still load).
const {B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
// (#7549): while localStorage t7549hang = 1 every indexedDB.open returns a request that fires no event (as WebKit at a start)
const HANG = `() => { try { if (localStorage.getItem('t7549hang') !== '1') return; } catch { return; }
  IDBFactory.prototype.open = function () { return {}; }; }`;
const firefox = require('./ff')({tag: 'p2663_c_offcache_ui', check, shots: 'P2663C_SHOTS', lazy: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

// the record in IndexedDB, read with an own open() of the database: 'o' (structured clone), 's' (JSON) or null (undefined
// after ff.js: a null comes back as undefined, hence == null)
const REC = `new Promise(res => { const r = indexedDB.open('kalmido-start'); r.onupgradeneeded = () => r.result.createObjectStore('s');
  r.onsuccess = () => { const d = r.result; const g = d.transaction('s').objectStore('s').get('state'); g.onsuccess = () => { const x = g.result; d.close();
    res(x ? {kind: x.o ? 'o' : 's', tasks: (x.o || JSON.parse(x.s)).tasks.map(t => t.title)} : null); }; g.onerror = () => { d.close(); res('err'); }; };
  r.onerror = () => res('err'); })`;
// (#6340): the age stored with the record's state (_at), and a test setting it
const AT = `new Promise(res => { const r = indexedDB.open('kalmido-start'); r.onsuccess = () => { const d = r.result; const g = d.transaction('s').objectStore('s').get('state');
  g.onsuccess = () => { const x = g.result; d.close(); res(x ? (x.o || JSON.parse(x.s))._at || 0 : 0); }; }; r.onerror = () => res(-1); })`;
const SETAT = ms => `new Promise(res => { const r = indexedDB.open('kalmido-start'); r.onsuccess = () => { const d = r.result, t = d.transaction('s', 'readwrite'), st = t.objectStore('s'), g = st.get('state');
  g.onsuccess = () => { const x = g.result; if (!x) { d.close(); res(0); return; } if (x.o) x.o._at = ${ms}; else { const c = JSON.parse(x.s); c._at = ${ms}; x.s = JSON.stringify(c); } if ('sat' in x) x.sat = ${ms}; st.put(x, 'state'); };
  t.oncomplete = () => { d.close(); res(1); }; t.onerror = () => { d.close(); res(0); }; }; r.onerror = () => res(0); })`;
// in every new document before the app: the app's requests fail like a lost network while localStorage t2663off = 1
const OFF = `() => { try { if (localStorage.getItem('t2663off') !== '1') return; } catch { return; }
  const f0 = window.fetch; window.fetch = function (u, o) { if (/\\/api\\//.test(String(u && u.url || u))) return Promise.reject(new TypeError('NetworkError when attempting to fetch resource.')); return f0.apply(this, arguments); }; }`;

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'sheets,collab,comments'});
  const L = (await call('POST', '/api/lists', {name: 'Greenhouse'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Water the ferns', list_id: L})).id;
  check(L > 0 && T > 0, 'setup: a list with a task');
  const sh = await call('POST', '/api/sheets', {title: 'Plant log', space: 'private'});
  check(sh.status === 201, 'setup: a private table');
  const SID = sh.id;

  await firefox(async ({cmd, ev, nav, ctx, until, shot}) => {
    const pu = (expr, ms = 15000) => until(expr, {timeout: ms, step: 150});
    await cmd('script.addPreloadScript', {functionDeclaration: OFF});
    await cmd('script.addPreloadScript', {functionDeclaration: HANG});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return new Promise(r => { const q = indexedDB.deleteDatabase('kalmido-start'); q.onsuccess = q.onerror = q.onblocked = () => r(1); }); })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: sign-in');

    // ---- online: written to IndexedDB when idle, nothing in localStorage
    await nav(B + `#l/${L}`);
    check(await pu(`typeof S !== 'undefined' && S.booted && !!document.querySelector('#view .trow[data-id="${T}"]')`), 'online: the list shows the task');
    check(await pu(`typeof OC !== 'undefined' && OC.wrote > 0 && !OC.off`), 'online: the state was written to IndexedDB (module offcache loaded on demand, no fallback)');
    const r1 = await ev(REC);
    check(r1 && r1.kind === 'o' && r1.tasks.includes('Water the ferns'), 'online: the record is a structured clone with the task ' + JSON.stringify(r1));
    check(await ev(`localStorage.getItem('tasks.cache') === null`), 'online: no copy of the state in localStorage');

    // ---- a browser of before 2.663: only the old localStorage copy (a title only it has), then a start without network
    await ev(`(async () => { const c = JSON.parse(JSON.stringify(S.lpCache)); S.lpCache = null; await oc_drop(); c.tasks = c.tasks.map(t => t.id === ${T} ? {...t, title: 'From the old copy'} : t);
      localStorage.setItem('tasks.cache', JSON.stringify(c)); localStorage.setItem('t2663off', '1'); return 1; })()`);
    const r0 = await ev(REC);
    check(r0 == null, 'setup: no record in IndexedDB, only the old localStorage copy ' + JSON.stringify(r0) + ' ' + JSON.stringify(await ev(`({gen: OC.gen, t: OC.t, off: OC.off, wrote: OC.wrote})`)));
    await nav(B + `#l/${L}`); await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online === false`), 'offline start: the app started and knows it is offline');
    check(await pu(`document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('From the old copy')`), 'offline start: the old localStorage copy is shown');
    check(await pu(`localStorage.getItem('tasks.cache') === null`), 'offline start: the old copy is removed from localStorage once taken over');
    const r2 = await ev(REC);
    check(r2 && r2.tasks.includes('From the old copy'), 'offline start: the old copy is in IndexedDB now ' + JSON.stringify(r2));
    await shot('p2663c-offline-old.png');
    // a second start without network: from IndexedDB
    // (#6340 D6): the record says its state is three days old - the start shows that age, not "less than a minute"
    const OLD = Date.now() - 3 * 864e5 - 5 * 60000;
    check(await ev(SETAT(OLD)) === 1, 'setup: the record\'s state is three days old');
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online === false && document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('From the old copy')`),
      'second offline start: the state comes from IndexedDB');
    check(await pu(`S.syncOk === ${OLD}`), 'offline start (#6340): the age of the state is the stored one, not the page start ' + await ev(`S.syncOk - ${OLD}`));
    const chip = await ev(`(() => { const b = document.querySelector('#top .offline'); return b ? {t: b.title, w: b.textContent, want: stateFrom(${OLD})} : null; })()`);
    check(chip && /^State from \S/.test(chip.want) && chip.t.includes(chip.want) && chip.w.includes(chip.want), 'offline start (#6340): the header\'s chip names the state\'s day and time ' + JSON.stringify(chip));
    check(await ev(`!document.body.textContent.includes('less than a minute')`), 'offline start (#6340): nothing says the state is fresh');

    // ---- online again: the server's state, written as a structured clone
    await ev(`(localStorage.removeItem('t2663off'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online && document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('Water the ferns')`), 'online again: the server\'s title');
    check(await pu(`typeof OC !== 'undefined' && OC.wrote > 0`), 'online again: written');
    let r3 = null; await until(async () => { r3 = await ev(REC); return r3 && r3.tasks.includes('Water the ferns'); }, {timeout: 15000, step: 200});
    check(r3 && r3.kind === 'o' && !r3.tasks.includes('From the old copy'), 'online again: the record holds the server\'s state ' + JSON.stringify(r3));

    // ---- (#7595): the old copy in both places - older than the record: the record stays, the copy goes; newer: taken over
    const both = await ev(`(async () => {
      await oc_del(); OC.t = 0; await oc_write();
      const c = JSON.parse(JSON.stringify(S.lpCache)), v = +c.v || 0, as = t => ({...c, tasks: c.tasks.map(x => x.id === ${T} ? {...x, title: t} : x)});
      localStorage.setItem('tasks.cache', JSON.stringify({...as('From an older copy'), v: v - 1}));
      const a = await oc_get();
      const older = {title: a?.tasks.find(x => x.id === ${T})?.title, ls: localStorage.getItem('tasks.cache') !== null};
      localStorage.setItem('tasks.cache', JSON.stringify({...as('From a newer copy'), v: v + 1}));
      const b = await oc_get();
      return {v, older, newer: {title: b?.tasks.find(x => x.id === ${T})?.title, ls: localStorage.getItem('tasks.cache') !== null}};
    })()`);
    check(both.older.title === 'Water the ferns' && both.older.ls === false, 'both places, the copy older (#7595): the record wins, the copy goes ' + JSON.stringify(both));
    check(both.newer.title === 'From a newer copy' && both.newer.ls === false, 'both places, the copy newer (#7595): the copy is taken over and goes ' + JSON.stringify(both));
    const rb = await ev(REC);
    check(rb && rb.tasks.includes('From a newer copy'), 'both places, the copy newer (#7595): it is the record now ' + JSON.stringify(rb));
    // ---- (#7595): two windows - another window wrote a newer state (a higher version); this older one writes after it
    const two = await ev(`(async () => {
      await oc_del(); OC.t = 0; await oc_write();
      const v = +S.lpCache.v || 0;
      await new Promise(res => { const r = indexedDB.open('kalmido-start'); r.onsuccess = () => { const d = r.result, t = d.transaction('s', 'readwrite'), st = t.objectStore('s'), g = st.get('state');
        g.onsuccess = () => { const x = g.result, c = x.o || JSON.parse(x.s); c.v = v + 5; c.tasks = c.tasks.map(k => k.id === ${T} ? {...k, title: 'From the newer window'} : k); st.put({o: c, at: Date.now(), v: v + 5, sat: c._at}, 'state'); };
        t.oncomplete = () => { d.close(); res(1); }; t.onerror = () => { d.close(); res(0); }; }; });
      OC.t = 0; await oc_write();
      return {v};
    })()`);
    const rw = await ev(REC);
    check(rw && rw.tasks.includes('From the newer window'), 'an older window writes after a newer one (#7595): the newer record stays ' + JSON.stringify({two, rw}));
    await ev(`(async () => { await oc_del(); OC.t = 0; await oc_write(); return 1; })()`);
    check(!!(await ev(REC))?.tasks.includes('Water the ferns'), 'the record holds this window\'s state again');

    // ---- (#7549): indexedDB.open never answers (WebKit, iOS Safari / PWA at a start). Before: outOpen and the start state's
    // read waited for it forever - a blank page with the Offline chip, also with the server back
    const COPY = await ev(`JSON.stringify({...S.lpCache, tasks: S.lpCache.tasks.map(t => t.id === ${T} ? {...t, title: 'From the hung start'} : t)})`);
    await ev(`(localStorage.removeItem('tasks.cache'), localStorage.setItem('t7549hang', '1'), localStorage.setItem('t2663off', '1'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await ev(`indexedDB.open('kalmido-start').onsuccess === undefined && !('readyState' in indexedDB.open('x'))`), 'setup (#7549): indexedDB.open answers nothing');
    check(await pu(`!!document.querySelector('#boot-retry') && document.querySelector('#view')?.textContent.includes('Server not reachable')`, 20000),
      'hung IndexedDB, offline, no copy (#7549): the start ends with "Server not reachable" and Try again, not a blank page');
    const hr = await ev(`({off: OUT.online, closed: STORE.closed, warned: typeof OC !== 'undefined' && OC.warned})`);
    check(hr.off === false && hr.closed === true && hr.warned === true, 'hung IndexedDB (#7549): the outbox goes without it, the start state\'s read is reported once ' + JSON.stringify(hr));
    await shot('p2663c-hung-offline.png');
    await ev(`(localStorage.setItem('tasks.cache', ${JSON.stringify(COPY)}), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online === false && !!document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('From the hung start')`, 20000),
      'hung IndexedDB, offline, an old localStorage copy (#7549): the app starts with that copy');
    await ev(`(localStorage.removeItem('t2663off'), localStorage.removeItem('tasks.cache'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online && !!document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('Water the ferns')`, 20000),
      'hung IndexedDB, server reachable (#7549): the app starts with the server\'s state');
    // (#7595): the write meanwhile (module loaded after the start, idle) hangs too: said once, no localStorage copy
    check(await pu(`typeof OC !== 'undefined' && OC.warned && OC.wrote === 0`, 25000) && await ev(`localStorage.getItem('tasks.cache') === null`),
      'hung IndexedDB (#7595): the start state goes to no localStorage copy meanwhile, the write is reported');
    // IndexedDB answers again: back to the record
    await ev(`(localStorage.removeItem('t7549hang'), localStorage.removeItem('tasks.cache'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    // #6366: the start draws the kept state first - the server's state is there once the sync behind it is through (!S.devOld)
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online && !S.devOld && !STORE.closed && document.querySelector('#view .trow[data-id="${T}"]')?.textContent.includes('Water the ferns')`), 'IndexedDB answers again: a normal start');

    // ---- (#6340 D2b): an own change online, then the page is hidden: the start state has it at once (was: only after the
    // delta + 30 s + an idle moment - closed before, the next offline start missed it)
    const T2 = await ev(`api('POST', '/api/tasks', {title: 'Mist the orchids', list_id: ${L}}).then(t => t.id)`);
    check(T2 > 0 && await pu(`S.tasks.has(${T2}) && !OUT.q.length`), 'hidden page: the own new task is in the state');
    await ev(`(dispatchEvent(new Event('pagehide')), 1)`);
    let r5 = null; await until(async () => { r5 = await ev(REC); return r5 && r5.tasks.includes('Mist the orchids'); }, {timeout: 6000, step: 150});
    check(r5 && r5.tasks.includes('Mist the orchids'), 'hidden page (#6340): the start state holds the change made just before, at once ' + JSON.stringify(r5));
    const at5 = await ev(AT);
    check(at5 > Date.now() - 120000, 'hidden page (#6340): the record carries the time the server confirmed it ' + at5);
    // ---- (#6340, reader F1): another tab of this browser signed out: a hidden page here writes no start state back - the
    // next person at this browser finds nothing (#2889, #4200). (#7595): without the own account check (startMine), the
    // gate devCopyOk alone: the other tab's devEnd('logout') takes the keys of own / view / copy / secret (tasks.uid, the stamp tasks.wko)
    const T3 = await ev(`api('POST', '/api/tasks', {title: 'Repot the fern', list_id: ${L}}).then(t => t.id)`);
    check(T3 > 0 && await pu(`S.tasks.has(${T3}) && !OUT.q.length`), 'signed out elsewhere: a newer state to write');
    const so = await ev(`(async () => {
      await oc_del();
      const keep = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); keep[k] = localStorage.getItem(k); }
      for (const k of Object.keys(keep)) if (DEV_END.logout.includes(devCls('ls', k))) localStorage.removeItem(k);  // what the other tab's sign-out does to the shared storage
      const gone = !localStorage.getItem('tasks.uid') && !localStorage.getItem('tasks.wko');
      dispatchEvent(new Event('pagehide')); OC.t = 0; await oc_write();
      const off = await ${REC};
      for (const [k, v] of Object.entries(keep)) localStorage.setItem(k, v);
      OC.t = 0; await oc_write();
      return {gone, off, on: await ${REC}};
    })()`);
    check(so.gone && so.off == null, 'signed out in another tab (#6340, #7595): the hidden page writes no start state ' + JSON.stringify({gone: so.gone, off: so.off}));
    check(!!so.on?.tasks.includes('Repot the fern'), 'signed in again: written as before ' + JSON.stringify(so.on));

    // ---- (#7595 Zusatz 2): IndexedDB refuses a write (quota): no copy anywhere else, said once (console.warn); the next change
    // opens the connection anew and lands, the offline start after it shows that state
    const T4 = await ev(`api('POST', '/api/tasks', {title: 'Feed the cacti', list_id: ${L}}).then(t => t.id)`);
    check(T4 > 0 && await pu(`S.tasks.has(${T4}) && !OUT.q.length`), 'refused write: a newer state to write');
    const fb = await ev(`(async () => {
      const put0 = IDBObjectStore.prototype.put, w0 = console.warn, said = [], h0 = OC.h;
      IDBObjectStore.prototype.put = function () { throw new DOMException('quota (test)', 'QuotaExceededError'); };
      console.warn = (...a) => { said.push(a.join(' ')); };
      lpCacheFold(S.lpCache);
      try { OC.t = 0; await oc_write(); } finally { IDBObjectStore.prototype.put = put0; console.warn = w0; }
      return {ls: localStorage.getItem('tasks.cache') !== null, said, dropped: OC.h !== h0, rec: await ${REC}};
    })()`);
    check(!fb.ls && !fb.rec?.tasks.includes('Feed the cacti'), 'refused write (#7595): not written, and no localStorage copy ' + JSON.stringify(fb));
    check(fb.said.some(s => /offline start state/.test(s) && /QuotaExceededError/.test(s)), 'refused write: the reason is logged, not swallowed ' + JSON.stringify(fb.said));
    check(fb.dropped, 'refused write (#7595 Zusatz 2): the connection is dropped, the next change opens a fresh one');
    await ev(`(async () => { OC.t = 0; await oc_write(); return 1; })()`);
    const r6 = await ev(REC);
    check(r6 && r6.tasks.includes('Feed the cacti'), 'the next change (#7595 Zusatz 2): it lands ' + JSON.stringify(r6));
    await ev(`(localStorage.setItem('t2663off', '1'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online === false && !!document.querySelector('#view .trow[data-id="${T4}"]')`),
      'offline start after it (#7595 Zusatz 2): the state of the write that landed is shown');
    await ev(`(localStorage.removeItem('t2663off'), 1)`);
    await cmd('browsingContext.reload', {context: ctx, wait: 'complete'});
    check(await pu(`typeof S !== 'undefined' && S.booted && OUT.online && typeof OC !== 'undefined' && OC.wrote > 0`, 20000), 'online again: written');

    // ---- sign-out: the record goes
    await ev(`(async () => { OC.t = 0; await oc_write(); return 1; })()`);
    // a write planned before the sign-out (idle) must not bring the record back afterwards
    await ev(`(oc_soon(), 1)`);
    check(!!(await ev(REC)), 'setup: a record before the sign-out');
    await ev(`devEnd('logout').then(() => 1)`);
    await ev(`new Promise(r => (globalThis.requestIdleCallback || setTimeout)(() => setTimeout(() => r(1), 50), {timeout: 2000}))`);  // the idle callback planned above has run (a state of the page)
    const r4 = await ev(REC);
    check(r4 == null && (await ev(`S.lpCache === null`)), 'sign-out (devEnd logout): the record is gone and stays gone (a planned write is void) ' + JSON.stringify(r4));

    // ---- the open table: polled unchanged = nothing drawn again; changed = loaded and drawn
    await nav(B + `#sheets/${SID}`);
    check(await pu(`typeof SHV !== 'undefined' && SHV.sh?.id === ${SID} && !!SHV.sh.etag && !!document.querySelector('#shv-scroll')`), 'the table is open with its etag');
    const u = await ev(`(async () => {
      const r0 = shvRender, sh0 = SHV.sh, n0 = SHV.n304 || 0; let drawn = 0;
      shvRender = function () { drawn++; return r0.apply(this, arguments); };
      try { await shvLoad(${SID}, true); await shvLoad(${SID}, true); } finally { shvRender = r0; }
      return {same: SHV.sh === sh0, n: (SHV.n304 || 0) - n0, drawn};
    })()`);
    check(u.same && u.n === 2 && u.drawn === 0, 'polled twice unchanged: {unchanged}, the same sheet, nothing drawn ' + JSON.stringify(u));
    const d = await call('GET', `/api/sheets/${SID}`);
    const row = d.rows.sort((a, b) => a.pos - b.pos)[0].id, col = d.columns.sort((a, b) => a.pos - b.pos)[0].id;
    check((await call('PUT', `/api/sheets/${SID}/cells`, {cells: [{row_id: row, col_id: col, raw: 'Repotted'}]})).status === 200, 'a cell changed on the server (another tab)');
    const c = await ev(`(async () => {
      const r0 = shvRender, sh0 = SHV.sh, n0 = SHV.n304 || 0; let drawn = 0;
      shvRender = function () { drawn++; return r0.apply(this, arguments); };
      try { await shvLoad(${SID}, true); } finally { shvRender = r0; }
      return {other: SHV.sh !== sh0, n: (SHV.n304 || 0) - n0, drawn, raw: SHV.sh.cells.map(x => x.raw)};
    })()`);
    check(c.other && c.n === 0 && c.drawn === 1 && c.raw.includes('Repotted'), 'polled after the change: the whole sheet loaded and drawn ' + JSON.stringify(c));
    check(await pu(`!!document.querySelector('#shv-scroll')?.textContent.includes('Repotted')`), 'the new value shows in the grid');
  });

  console.log(`p2663_c_offcache_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p2663_c_offcache_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
