// kalmido-suite:
// UI test (#7525, cause 3): favourite saves and a state load on their way at the same time. Own container (start.sh), jsdom.
// Invented data only.
// - two quick changes (two stars one after the other, a slow line under the first): each save sends the WHOLE list, so the
//   older one arriving last took the newer favourite away again (the star showed and went). Now every favourite write goes
//   one way, one after the other (favorites.js favWrite / FAV_Q, as the project star since #5013): both stay
// - a state load begun before the save and answered after it does not take the star back (guard of #7150 S.wfly / S.wv)
// - a refused save says the server's reason in the message (not a silent reload) and the shown list is the stored one again
// P4: frida has no organisation and gets the same (freelancer-matrix: tasks)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, until, slow} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7525C_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const items = async ck => JSON.parse((await call(ck, 'GET', '/api/state')).settings.fav_items || '[]');
const u2 = (fn, timeout = 8000) => until(fn, {timeout}).catch(() => null);
// the favourite saves only (PATCH /api/settings with fav_items): the first one waits on the line until w.__go(), later ones pass;
// w.__n = how many were asked
const holdFav = w => {
  const f0 = w.fetch; let rel = null; const first = new Promise(r => { rel = r; });
  w.__n = 0; w.__go = () => rel();
  w.fetch = (u, o = {}) => {
    if (!/api\/settings/.test(String(u)) || o.method !== 'PATCH' || !String(o.body || '').includes('fav_items')) return f0(u, o);
    return ++w.__n === 1 ? first.then(() => f0(u, o)) : f0(u, o);
  };
};

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: ['cal']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida: no organisation');

  for (const [u, ck] of [['alice', CA], ['frida', CF]]) {
    const L = (await call(ck, 'POST', '/api/lists', {name: 'Errands'})).id;
    await call(ck, 'POST', '/api/tasks', {list_id: L, title: 'Buy paper'});
    await call(ck, 'PATCH', '/api/settings', {fav_items: []});

    // (1) two quick stars, the first save slow on the line
    let w = await boot({user: u, hash: 'today'});
    holdFav(w);
    w.eval(`fv2_set('v:week', true)`);
    check(await u2(() => w.__n === 1), `${u}: the first save is on its way (held)`);
    w.eval(`fv2_set('v:today', true)`);
    await sleep(400);  // the second star's save: only after the first one is answered (none may pass it)
    check(w.__n === 1, `${u}: the second save waits behind the first one (asked ${w.__n})`);
    w.__go();
    check(await u2(async () => { const x = await items(ck); return x.includes('v:week') && x.includes('v:today'); }), `${u}: both favourites are stored ` + JSON.stringify(await items(ck)));
    check(await u2(() => w.eval(`fv2_is('v:week') && fv2_is('v:today')`)), `${u}: both stars stay on`);
    w.close();

    // (2) a state load begun before the save, answered after it: the star stays
    w = await boot({user: u, hash: 'assigned'});
    slow(w, /api\/state/);
    const ld = w.eval(`(window.__ld = load().then(() => 'done', e => 'err ' + e.message), 1)`);
    check(ld === 1 && await u2(() => w.__held >= 1), `${u}: a state load is on its way`);
    w.eval(`fv2_set('v:assigned', true)`);
    check(await u2(async () => (await items(ck)).includes('v:assigned')), `${u}: My tasks stored while the state load waits`);
    await u2(() => w.eval('!S.wfly'));
    w.__go();
    check(await u2(async () => (await w.eval('window.__ld')) === 'done'), `${u}: the held state load is through`);
    await sleep(300);
    check(w.eval(`fv2_is('v:assigned')`), `${u}: the star stays after the older state came in ` + w.eval('S.settings.fav_items'));
    check(await u2(() => w.document.querySelector('[data-fv2-star="v:assigned"]')?.getAttribute('aria-pressed') === 'true'), `${u}: the star in the header is pressed`);
    w.close();

    // (3) a refused save: the server's reason is said, the shown list is the stored one again
    w = await boot({user: u, hash: 'today'});
    const before = await items(ck);
    w.eval(`fv2_set('v:nope', true)`);
    const msg = await u2(() => { const t = w.document.querySelector('#toast:not(.hidden)')?.textContent || ''; return /Invalid value/.test(t) ? t : null; });
    check(!!msg, `${u}: the message says the server's reason ` + (w.document.querySelector('#toast')?.textContent || '(none)'));
    check(await u2(() => !w.eval(`fv2_is('v:nope')`)), `${u}: the refused key is not shown as a favourite`);
    check(JSON.stringify(await items(ck)) === JSON.stringify(before), `${u}: nothing stored`);
    w.close();
  }

  console.log(`p7525_c_fav_order_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
