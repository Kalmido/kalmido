// 2.306.0 B (#2889, #2887) UI test (jsdom), fresh DB:
// - a session that ended on the server (the next request gets 401): this browser's stored state of the account goes (the
//   cached state, the open chat windows, the session keys step-up / tour), the device's own preferences and the reload guard stay
// - with a change still waiting to be sent, the 401 keeps that change (it goes out after the next login)
// - (#6500): ... and only the own data: the rest of the account's state goes too, the remembered keys are forgotten
//   (e2eForget) and the push subscription of this browser ends
// - (#6500) the matrix event x class of icons.js devEnd against the decision: logout / another account / restore = own,
//   view, copy and secret go; the session ended = all but own; another sign-in mark / 14 days / no "Stay signed in" = the
//   copies; the device's own keys stay always. Every store of the register has one of the classes.
// - (#6500): a sign-in without "Stay signed in" keeps no offline start state (me.remember false); an offline start shows
//   no state whose last online sync is older than 14 days
// - (#7595): the register names the two second places (tasks.outbox feed of kalmido-outbox, tasks.cache fallback of
//   kalmido-start) with the class of their store; without IndexedDB both live in localStorage
// - the login page shows the operator's privacy / imprint links from the server configuration
// freelancer-matrix: browser storage (the account here has no organisation)
const {boot, errs, until, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, j: await r.json().catch(() => ({}))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, CK);
  check((await call('PATCH', '/api/admin/settings', {privacy_url: 'https://example.com/privacy', imprint_url: 'https://example.com/imprint'}, CK)).status === 200, 'admin sets the two links');

  // ================= the session ends: the stored state goes, the device preferences stay
  let w = await boot({ls: {'tasks.theme': '"light"', 'tasks.cwins': JSON.stringify({open: true, wins: [{k: 'a:1', h: 1, c: false}]})}});
  check(await until(() => 'tasks.cache' in w.__store), 'the app keeps its state in the browser while signed in');
  w.sessionStorage.setItem('rck-stepup', '0:new'); w.sessionStorage.setItem('kalmido-tour-1', '1'); w.sessionStorage.setItem('kalmido-rl-n', '1');
  await call('POST', '/api/auth/logout', null, w.__cookie);
  w.eval(`api('GET', '/api/state').catch(() => {})`);
  const scr = await until(() => w.document.querySelector('.authscreen'));
  check(scr, 'the login page comes up');
  check(await until(() => !('tasks.cache' in w.__store)), 'session ended: the cached state is gone');
  check(!('tasks.cwins' in w.__store), 'session ended: the open chat windows are gone');
  check(w.__store['tasks.theme'] === '"light"', 'the device preference (theme) stays');
  check(w.sessionStorage.getItem('rck-stepup') === null && w.sessionStorage.getItem('kalmido-tour-1') === null, 'session keys (step-up, tour) are gone');
  check(w.sessionStorage.getItem('kalmido-rl-n') === '1', 'the reload guard stays');
  // #2887: the links on the login page
  const pl = await until(() => w.document.querySelector('.authscreen .aulegal a[data-legal="privacy_url"]'));
  check(pl && pl.getAttribute('href') === 'https://example.com/privacy' && pl.getAttribute('rel').includes('noopener'), 'login page: privacy link');
  check(w.document.querySelector('.authscreen .aulegal a[data-legal="imprint_url"]')?.getAttribute('href') === 'https://example.com/imprint', 'login page: imprint link');
  w.close();

  // ================= a change waits to be sent: the 401 keeps it (2.360.2, #3226: the offline start state goes, by decision)
  w = await boot({ls: {'tasks.cwins': JSON.stringify({open: true, wins: [{k: 'a:1', h: 1, c: false}]})}});
  check(await until(() => 'tasks.cache' in w.__store), 'second start: state stored');
  w.eval(`window.__ef = 0; window.__pu = 0; devDrop('kalmido-e2e', () => { window.__ef++; return e2eForget(); }); devDrop('subscription', async () => { window.__pu++; })`);
  const lid = w.eval('S.lists[0].id');
  w.__offline = true;
  await w.eval(`api('POST', '/api/tasks', {title: 'Written offline', list_id: ${lid}}).catch(() => {})`);
  check(await until(() => w.eval('OUT.q.length') > 0), 'offline: the new task waits in the queue');
  await call('POST', '/api/auth/logout', null, w.__cookie);
  w.__offline = false;
  w.eval(`api('GET', '/api/state').catch(() => {})`);
  check(await until(() => w.document.querySelector('.authscreen')), 'the login page comes up again');
  check(!('tasks.cache' in w.__store), 'a change still waiting: the cached state goes with the session (2.360.2, #3226)');
  check(w.eval('OUT.q.length') > 0 && w.eval(`OUT.q.some(x => x.body?.title === 'Written offline')`), 'a change still waiting: it is kept');
  check('tasks.outbox' in w.__store && 'tasks.uid' in w.__store, '#6500: the waiting change and the account mark stay in the browser');
  check(!('tasks.cwins' in w.__store), '#6500: a change still waiting keeps only itself: the rest of the account (open chat windows) goes');
  check(await until(() => w.eval('window.__ef') >= 1 && w.eval('window.__pu') >= 1), '#6500: the ended session forgets the remembered keys and ends the push subscription');
  w.close();

  // ================= (#6500) the matrix event x class (icons.js DEV_STORES / DEV_END) against the decision of #6500
  w = await boot({});
  await until(() => w.eval('!!S.me && S.booted'));
  const WANT = {logout: ['own', 'view', 'copy', 'secret'], switch: ['own', 'view', 'copy', 'secret'], restore: ['own', 'view', 'copy', 'secret'],
    gone: ['view', 'copy', 'secret'], mark: ['copy']};
  const CLS = ['own', 'view', 'copy', 'secret', 'device'];
  check(w.eval(`DEV_STORES.every(([kind, name, c]) => ['ls', 'ss', 'idb', 'cache', 'push'].includes(kind) && name && ${JSON.stringify(CLS)}.includes(c))`), '#6500: every store of the register has a kind and one of the classes');
  check(JSON.stringify(Object.keys(WANT).sort()) === w.eval('JSON.stringify(Object.keys(DEV_END).sort())'), '#6500: the events of the table ' + w.eval('JSON.stringify(Object.keys(DEV_END))'));
  // (#7595): the second places of one store carry their role - the feed of the queue and the fallback of the start state, of the
  // same class as their store; no other key has one. jsdom has no IndexedDB: the mode of this browser is localStorage for both
  const roles = w.eval(`JSON.stringify(DEV_STORES.filter(e => e[3]).map(([kind, name, c, r]) => {
    const m = /^(feed|fallback) of (.+)$/.exec(r), of = m && DEV_STORES.find(([k2, n2]) => k2 === 'idb' && n2 === m[2]);
    return [kind, name, r, !!of && of[2] === c];
  }))`);
  check(roles === JSON.stringify([['ls', 'tasks.outbox', 'feed of kalmido-outbox', true], ['ls', 'tasks.cache', 'fallback of kalmido-start', true]]), '#7595: the register names the two second places with their role and store ' + roles);
  check(w.eval(`!globalThis.indexedDB && OBX.on === false`) && await until(() => 'tasks.cache' in w.__store), '#7595: a browser without IndexedDB keeps the start state in its fallback tasks.cache, the queue in tasks.outbox');
  // one key per class in both storages, every store that is no key with a drop that only counts
  const SEED = {ls: {own: ['tasks.outbox', 'tasks.conflicts', 'tasks.uid', 'tasks.idmap', 'tasks.fdf.1.x', 'tasks.fdx.1.2', 'tasks.ltpend.1.3'],
    view: ['tasks.cwins', 'tasks.lastKey', 'kalmido.xd', 'kalmido.dlgsize.a', 'vdr-name'], copy: ['tasks.cache', 'tasks.wko'],
    device: ['tasks.theme', 'tasks.vmode', 'kalmido.logoutPending']},
  ss: {view: ['rck-stepup', 'kalmido-tour-1', 'kalmido.rcl.0'], device: ['kalmido-reloaded', 'kalmido.booted']}};
  const stores = w.eval(`JSON.stringify(DEV_STORES.filter(([k]) => k !== 'ls' && k !== 'ss'))`);
  for (const why of Object.keys(WANT)) {
    w.eval(`window.__dropped = []; for (const [, name] of ${stores}) devDrop(name, () => { window.__dropped.push(name); })`);
    for (const [kind, st] of [['ls', w.localStorage], ['ss', w.sessionStorage]]) for (const ks of Object.values(SEED[kind])) for (const k of ks) st.setItem(k, '"x"');
    await w.eval(`devEnd('${why}')`);
    for (const [kind, st] of [['ls', w.localStorage], ['ss', w.sessionStorage]]) for (const [c, ks] of Object.entries(SEED[kind])) for (const k of ks)
      check((st.getItem(k) === null) === WANT[why].includes(c), `#6500 ${why}: ${kind} ${k} (${c}) ${WANT[why].includes(c) ? 'goes' : 'stays'}`);
    const dropped = w.eval('JSON.stringify(window.__dropped.sort())');
    const want = JSON.stringify(JSON.parse(stores).filter(([, , c]) => WANT[why].includes(c)).map(([, n]) => n).sort());
    check(dropped === want, `#6500 ${why}: the stores dropped ${dropped} = ${want}`);
  }
  w.close();

  // ================= (#6500): without "Stay signed in" no offline start state
  const st6500 = await call('GET', '/api/state', null, CK);
  w = await boot({remember: false, ls: {'tasks.cache': JSON.stringify({...st6500.j, _at: Date.now()}), 'tasks.uid': String(st6500.j.me.id)}});
  check(await until(() => w.eval('S.booted && S.me?.remember === false')), '#6500: the state says the sign-in did not ask to stay signed in');
  await w.eval('load().then(() => 1, () => 0)');
  await until(() => !('tasks.cache' in w.__store));
  check(!('tasks.cache' in w.__store) && w.eval('S.lists.length') > 0 && w.eval('devCopyOk()') === false, '#6500: without "Stay signed in" no offline start state is written, the one of before goes');
  w.close();
  w = await boot({});
  check(await until(() => 'tasks.cache' in w.__store) && w.eval('S.me.remember') === true, '#6500: with "Stay signed in" (the default) the state is kept as before');
  // audit #6007 a: a delta carries no sign-in mark, so it never moves the copies' stamp on (an account removed from an
  // organisation with the tab open keeps its 14 days from the last full state); a full state does, with the fresh mark
  const at13 = new Date(Date.now() - 13 * 864e5).toISOString();
  w.eval(`LS.set('wko', {...LS.get('wko', {}), at: '${at13}'}); lpCacheFold({}); 1`);
  check(JSON.parse(w.__store['tasks.wko']).at === at13, '#6500 (audit #6007 a): a delta leaves the stamp as it was ' + w.__store['tasks.wko']);
  await w.eval('load().then(() => 1, () => 0)');
  check(Date.now() - Date.parse(JSON.parse(w.__store['tasks.wko']).at) < 60e3, '#6500: a full state moves the stamp to now ' + w.__store['tasks.wko']);
  w.close();

  // ================= (#6500): an offline start shows no state whose last online sync is older than 14 days
  const down = win => { const f = win.fetch; win.fetch = (u, o) => String(u).includes('/api/') ? Promise.resolve(new Response('bad gateway', {status: 502, headers: {'content-type': 'text/html'}})) : f(u, o); };
  const off = async age => {
    const stamp = JSON.stringify({g: st6500.j.me.sgen || '', at: new Date(Date.now() - age).toISOString()});
    const ww = await boot({ls: {'tasks.cache': JSON.stringify({...st6500.j, _at: Date.now() - age}), 'tasks.uid': String(st6500.j.me.id), 'tasks.wko': stamp}, setup: down});
    await until(() => ww.eval('S.lists.length') > 0 || !('tasks.cache' in ww.__store));
    const r = {lists: ww.eval('S.lists.length'), kept: 'tasks.cache' in ww.__store};
    ww.close(); return r;
  };
  const fresh = await off(864e5), old = await off(15 * 864e5);
  check(fresh.lists > 0 && fresh.kept, '#6500: offline start with a sync of yesterday: shown ' + JSON.stringify(fresh));
  check(old.lists === 0 && !old.kept, '#6500: offline start with a sync 15 days ago: not shown, it goes ' + JSON.stringify(old));

  check(!errs.length, 'no script errors ' + errs.slice(0, 3).join(' | '));
  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
