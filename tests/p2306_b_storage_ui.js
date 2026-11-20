// 2.306.0 B (#2889, #2887) UI test (jsdom), fresh DB:
// - a session that ended on the server (the next request gets 401): this browser's stored state of the account goes (the
//   cached state, the open chat windows, the session keys step-up / tour), the device's own preferences and the reload guard stay
// - with a change still waiting to be sent, the 401 keeps that change (the change goes out after the next login)
// - (#6500): ... and only that: the rest of the account's state goes too, the remembered keys are forgotten (e2eForget)
// - (#6500): a sign-in without "Stay signed in" keeps no offline start state (me.remember false); an offline start does
//   not show a state older than 14 days
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
  w.eval(`window.__ef = 0; const ef0 = e2eForget; e2eForget = async () => { window.__ef++; return ef0(); }`);
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
  check(await until(() => w.eval('window.__ef') >= 1), '#6500: the ended session forgets the remembered keys (e2eForget)');
  w.close();

  // ================= (#6500): without "Stay signed in" no offline start state
  const st6500 = await call('GET', '/api/state', null, CK);
  w = await boot({remember: false, ls: {'tasks.cache': JSON.stringify({...st6500.j, _at: Date.now()}), 'tasks.uid': String(st6500.j.me.id)}});
  check(await until(() => w.eval('S.booted && S.me?.remember === false')), '#6500: the state says the sign-in did not ask to stay signed in');
  await w.eval('load().then(() => 1, () => 0)');
  await new Promise(r => setTimeout(r, 300));
  check(!('tasks.cache' in w.__store) && w.eval('S.lists.length') > 0, '#6500: without "Stay signed in" no offline start state is written, the one of before goes');
  w.close();
  w = await boot({});
  check(await until(() => 'tasks.cache' in w.__store) && w.eval('S.me.remember') === true, '#6500: with "Stay signed in" (the default) the state is kept as before');
  w.close();

  // ================= (#6500): an offline start shows no state older than 14 days (like the knowledge pages' copy)
  const down = win => { const f = win.fetch; win.fetch = (u, o) => String(u).includes('/api/') ? Promise.resolve(new Response('bad gateway', {status: 502, headers: {'content-type': 'text/html'}})) : f(u, o); };
  const off = async age => {
    const ww = await boot({ls: {'tasks.cache': JSON.stringify({...st6500.j, _at: Date.now() - age}), 'tasks.uid': String(st6500.j.me.id)}, setup: down});
    await new Promise(r => setTimeout(r, 500));
    const r = {lists: ww.eval('S.lists.length'), kept: 'tasks.cache' in ww.__store};
    ww.close(); return r;
  };
  const fresh = await off(864e5), old = await off(15 * 864e5);
  check(fresh.lists > 0 && fresh.kept, '#6500: offline start with a state of yesterday: shown ' + JSON.stringify(fresh));
  check(old.lists === 0 && !old.kept, '#6500: offline start with a state 15 days old: not shown, it goes ' + JSON.stringify(old));

  check(!errs.length, 'no script errors ' + errs.slice(0, 3).join(' | '));
  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
