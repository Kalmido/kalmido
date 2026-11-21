// kalmido-suite:
// UI test (#7525, cause 2): a favourite that is not a project ("My tasks", a view, an area, a tag) stays a favourite even when the
// stored favourites hold a key the server no longer knows. Own container (start.sh), jsdom. Invented data only.
// - before: the client sends the stored keys back with every change, the server refused the WHOLE list for one unknown key,
//   fv2_save loaded the old state again: the star showed and went again (only projects, on their own route, still worked)
// - now: a stored key that is no longer known is dropped, the new favourite is stored; after a reload the tile is there
// - a NEW unknown key is still refused (400) and changes nothing
// P4: frida has no organisation and gets the same (freelancer-matrix: tasks)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7525B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = async (fn, n = 60) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(200); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const items = async ck => JSON.parse((await call(ck, 'GET', '/api/state')).settings.fav_items || '[]');
// a key an older app stored and the server no longer knows (no check would let it in today): written straight into the database
const STALE = ['v:upcoming', 'sv:' + 'x'.repeat(20)];
const stale = uid => execFileSync('python3', ['-c', `import sys, os, json; sys.path.insert(0, ${JSON.stringify(__dirname)}); import dbx; c = dbx.connect(os.path.join(${JSON.stringify(DATA)}, 'tasks.db'), timeout=10); c.execute("INSERT INTO user_settings(user_id,key,value) VALUES(?,'fav_items',?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (${uid}, json.dumps(['v:today'] + ${JSON.stringify(STALE)}))); c.commit()`]);

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: ['cal']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal'});
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida: no organisation');

  for (const [u, ck] of [['alice', CA], ['frida', CF]]) {
    const uid = (await call(ck, 'GET', '/api/state')).me.id;
    const L = (await call(ck, 'POST', '/api/lists', {name: 'Errands'})).id;
    await call(ck, 'POST', '/api/tasks', {list_id: L, title: 'Buy paper', tags: ['office']});
    stale(uid);
    check(JSON.stringify(await items(ck)) === JSON.stringify(['v:today', ...STALE]), `${u}: the stored favourites hold keys the server no longer knows`);
    // the server: a new unknown key is still refused, the stored unknown ones are dropped with the next change
    check((await call(ck, 'PATCH', '/api/settings', {fav_items: ['v:today', ...STALE, 'v:nope']})).http === 400, `${u}: a NEW unknown key = 400`);
    check(JSON.stringify(await items(ck)) === JSON.stringify(['v:today', ...STALE]), `${u}: ... and nothing changed`);

    // the star in the header of My tasks (the reported case)
    let w = await boot({user: u, hash: 'assigned'}), d = w.document;
    const star = await until(() => d.querySelector('[data-fv2-star="v:assigned"]'));
    check(!!star && star.getAttribute('aria-pressed') === 'false', `${u}: My tasks has the star, not set`);
    if (star) click(w, star);
    check(await until(async () => (await items(ck)).includes('v:assigned')), `${u}: My tasks is stored as a favourite ` + JSON.stringify(await items(ck)));
    check(!(await items(ck)).some(k => STALE.includes(k)), `${u}: the keys no longer known are gone ` + JSON.stringify(await items(ck)));
    check(await until(() => w.eval(`!JSON.parse(S.settings.fav_items).some(k => ${JSON.stringify(STALE)}.includes(k))`)), `${u}: the client holds the list as stored`);
    // reader F3: taking the change back with the dropped keys in the value before -- "Recent steps" on the server and the app's undo
    const g = ((await call(ck, 'GET', '/api/undo')).items || [])[0] || {};
    const ru = await call(ck, 'POST', `/api/undo/${g.id}/undo`);
    check(ru.http === 200 && JSON.stringify(await items(ck)) === '["v:today"]', `${u}: Recent steps takes the star back although the value before held unknown keys ${ru.http} ` + JSON.stringify(await items(ck)));
    stale(uid);
    w.close();
    w = await boot({user: u, hash: 'assigned'}); d = w.document;
    const star2 = await until(() => d.querySelector('[data-fv2-star="v:assigned"]'));
    if (star2) click(w, star2);
    check(await until(async () => (await items(ck)).includes('v:assigned')), `${u}: the star set again`);
    await until(() => w.eval(`!JSON.parse(S.settings.fav_items).some(k => ${JSON.stringify(STALE)}.includes(k))`));
    await w.eval(`histStep('undo')`);
    check(await until(async () => JSON.stringify(await items(ck)) === '["v:today"]'), `${u}: the app's undo takes the star back (no 400) ` + JSON.stringify(await items(ck)));
    await w.eval(`histStep('redo')`);
    check(await until(async () => (await items(ck)).includes('v:assigned')), `${u}: redo sets it again ` + JSON.stringify(await items(ck)));
    await sleep(1500);  // a state load after the save must not take it back
    check(w.eval(`fv2_is('v:assigned')`) && d.querySelector('[data-fv2-star="v:assigned"]')?.getAttribute('aria-pressed') === 'true', `${u}: the star stays on`);
    // a view, an area, a tag: the same saving way
    for (const key of ['v:week', 'm:cal', 'tag:office']) {
      w.eval(`fv2_set(${JSON.stringify(key)}, true)`);
      check(await until(async () => (await items(ck)).includes(key)), `${u}: ${key} stored as a favourite`);
    }
    w.close();
    // after a reload: the tiles are there
    w = await boot({user: u, hash: 'today'}); d = w.document;
    for (const key of ['v:assigned', 'v:week', 'm:cal', 'tag:office'])
      check(await until(() => d.querySelector(`[data-fv2="${key}"]`)), `${u}: after a reload the tile ${key} is there`);
    w.close();
  }

  console.log(`p7525_b_fav_stale_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
