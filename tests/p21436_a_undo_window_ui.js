// 2.1436.0 UI test, part A (#6344, decision 16.11.2026: variant A): the arrow / Ctrl+Z take back only this window's steps and
// a step of elsewhere of the last 2 minutes; never a step over an API key; the tooltip names exactly the step of the click.
// kalmido-suite: fresh
// freelancer-matrix: undo (alice works without an organisation: Ctrl+Z, the arrow, the list "Recent steps")
// jsdom, fresh container. Invented names only. alice writes in this window, on "another device" (the app's device header) and
// over her own API key "Script Bot" (Authorization: Bearer, /api/v1). Used like a person does it:
//  (a) a step of the other device older than 2 minutes, nothing done in this window: Ctrl+Z takes nothing back, the list
//      "Recent steps" opens with that step marked and a line saying why; the arrow says "Recent steps" (red without the fix:
//      Ctrl+Z took the old rename back)
//  (b) the arrow's click opens the list the same way (the step marked)
//  (c) a fresh step of the other device, then a newer one over the API key: the arrow names the device's step ("… · from
//      Phone (Test)"); Ctrl+Z takes exactly that one back, the key's change stays, the message names the device
//  (d) a step of this window, then an older-than-2-minutes step of the other device: Ctrl+Z takes this window's step, the
//      other device's change stays
// The 2 minutes are not waited for: the other device's step is dated back in the database (undo_groups.created_at).
// The waits are on states (values on the server, the list, the toast, the tooltip), never on a fixed time.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, errs, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DEV = {'X-Kalmido-Device-Name': 'Phone (Test)'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const sql = (q, a = []) => JSON.parse(execFileSync('python3', [path.join(__dirname, 'dbx.py'), DATA, q, JSON.stringify(a)]).toString() || '[]');
const until = (fn, ms) => until0(fn, {timeout: ms || 20000, step: 100});
const call = async (ck, method, url, body, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const st0 = await call(CA, 'GET', '/api/state');
  check(!(st0.me.workspaces || []).length, `alice works without an organisation (${JSON.stringify(st0.me.workspaces)})`);
  const KEY = (await call(CA, 'POST', '/api/me/tokens', {name: 'Script Bot', scopes: ['read', 'write']})).token;
  check(/^abk_/.test(KEY || ''), 'a personal API key');
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Garden'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {list_id: L, title: 'Plant tulips'}, DEV)).id;
  const U = (await call(CA, 'POST', '/api/tasks', {list_id: L, title: 'Cut the hedge'}, DEV)).id;
  const task = async id => call(CA, 'GET', `/api/tasks/${id}`);
  const newest = async () => ((await call(CA, 'GET', '/api/undo?limit=1')).items || [])[0];
  // the other device's step, dated back by 5 minutes on the server's clock
  const age = async gid => {
    const g = ((await call(CA, 'GET', '/api/undo?limit=50')).items || []).find(x => x.id === gid);
    const back = new Date(Date.parse(g.at) - 5 * 60000).toISOString().replace(/\.\d+Z$/, '+00:00');
    sql('UPDATE undo_groups SET created_at=? WHERE id=?', [back, gid]);
    return ((await call(CA, 'GET', '/api/undo?limit=50')).items || []).find(x => x.id === gid);
  };

  // ---- (a) an old step of the other device, nothing done here: Ctrl+Z opens the list with it marked
  await call(CA, 'PATCH', `/api/tasks/${T}`, {title: 'Plant tulips and roses'}, DEV);
  const G1 = await newest();
  const g1 = await age(G1.id);
  check(g1 && g1.age_s >= 290 && g1.via === '', `the server names the step's age (${JSON.stringify(g1 && [g1.age_s, g1.via])})`);

  const w = await boot({user: 'alice', hash: 'l/' + L}); const d = w.document;
  const btn = () => d.querySelector('#top [data-act="hist-undo"]');
  const key = (k, o = {}) => d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: k, ctrlKey: true, bubbles: true, cancelable: true, ...o}));
  const row = id => d.querySelector(`#pop:not(.hidden) .ulbody .ulrow[data-ul="s:${id}"]`);
  const toastText = () => d.querySelector('#toast:not(.hidden)')?.textContent || '';
  const idle = () => until(() => !w.eval('HIST.busy') && w.eval('OUT.q.length') === 0);
  check(await until(() => btn()), 'the arrow');
  check(await until(() => btn().getAttribute('aria-label') === 'Recent steps' && btn().title === 'Recent steps'), `nothing to undo here: the arrow says "Recent steps" (${btn()?.title})`);

  key('z');
  check(await until(() => row(G1.id)), 'Ctrl+Z: the list "Recent steps" opens');
  check(await until(() => row(G1.id)?.classList.contains('ulmark') && row(G1.id)?.getAttribute('aria-current') === 'true'), 'the other device\'s step is marked');
  check(/only covers the steps of this window and of the last 2 minutes/.test(d.querySelector('#pop .ulnote')?.textContent || ''), `a line says why (${d.querySelector('#pop .ulnote')?.textContent})`);
  check(d.activeElement === row(G1.id)?.querySelector('[data-ul-go]'), 'its "Back up to here" has the focus');
  check(d.querySelectorAll('#pop .ulrow.ulmark').length === 1, 'one row marked');
  await idle();
  check((await task(T)).title === 'Plant tulips and roses', 'the old step of the other device stays (Ctrl+Z took nothing back)');
  check((await newest()).state === 'done', 'its group is still done');
  w.eval('closePop()');

  // ---- (b) the arrow's click: the same list, the step marked
  btn().click();
  check(await until(() => row(G1.id)?.classList.contains('ulmark')), 'the arrow\'s click opens the list with the step marked');
  check((await task(T)).title === 'Plant tulips and roses', '… and takes nothing back');
  // the list keeps working: "Back up to here" on the marked row takes it back
  row(G1.id).querySelector('[data-ul-go]').click();
  check(await until(async () => (await task(T)).title === 'Plant tulips' && !w.eval('UL.busy')), 'Back up to here on the marked row takes it back');
  w.eval('closePop()');
  await idle();

  // ---- (c) a fresh step of the other device, a newer one over the API key: the arrow and Ctrl+Z take the device's step
  await call(CA, 'PATCH', `/api/tasks/${U}`, {title: 'Cut the hedge today'}, DEV);
  const G2 = await newest();
  const kp = await call(null, 'PATCH', `/api/v1/tasks/${T}`, {priority: 3}, {Authorization: 'Bearer ' + KEY});
  check(kp.http === 200, `a change over the key (${kp.http})`);
  const GK = await newest();
  check(GK.via === 'token' && GK.id > G2.id, `the key's step is the newest (${JSON.stringify([GK.id, GK.via, G2.id])})`);
  const sk = (await call(CA, 'GET', '/api/undo?limit=5&skip_api=1')).items || [];
  check(sk[0]?.id === G2.id && !sk.some(x => x.via === 'token'), `GET /api/undo?skip_api=1 leaves the key's step out (${JSON.stringify(sk.map(x => [x.id, x.via]))})`);
  check(await until(() => /^Undo: .*Cut the hedge.* · from Phone \(Test\) \(/.test(btn().title || ''), 30000), `the tooltip names the other device's step, not the key's (${btn().title})`);
  key('z');
  check(await until(async () => (await task(U)).title === 'Cut the hedge'), 'Ctrl+Z takes the other device\'s fresh step back');
  check((await task(T)).priority === 3, 'the key\'s change stays');
  check(((await call(CA, 'GET', '/api/undo?limit=50')).items || []).find(x => x.id === GK.id)?.state === 'done', 'the key\'s step is still done');
  check(await until(() => /Undone: .*Cut the hedge.* · from Phone \(Test\)/.test(toastText())), `the message names the device (${toastText()})`);
  await idle();
  // the tooltip then names the next step the click would take (the newest one not undone and not over the key)
  const nx = ((await call(CA, 'GET', '/api/undo?limit=50')).items || []).find(x => x.state !== 'undone' && x.via !== 'token');
  check(nx && nx.id !== G2.id && await until(() => (btn().title || '').startsWith(`Undo: ${nx.label} · from `)), `the tooltip names the next step (${btn().title} / ${nx?.label})`);

  // ---- (d) a step of this window, then an older step of the other device: Ctrl+Z takes this window's
  await w.eval(`patchUndoable(${U}, {priority: 5}, 'Priority')`);
  check(await until(async () => (await task(U)).priority === 5), 'a step in this window');
  await idle();
  await call(CA, 'PATCH', `/api/tasks/${T}`, {title: 'Plant tulips in autumn'}, DEV);
  const G3 = await newest();
  await age(G3.id);
  await w.eval('histSrvLoad().then(renderHist)');
  check(/^Undo: Priority of .*Cut the hedge/.test(btn().title || ''), `the tooltip names this window's step (${btn().title})`);
  key('z');
  check(await until(async () => (await task(U)).priority === 0), 'Ctrl+Z takes this window\'s step back');
  check((await task(T)).title === 'Plant tulips in autumn', 'the older step of the other device stays');
  await idle();
  check(!d.querySelector('#pop:not(.hidden) .ulbody'), 'no list opened');
  w.close();

  check(!errs.length, 'no script errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21436_a_undo_window_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
