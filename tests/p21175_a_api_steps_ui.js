// 2.1175.0 UI test, part A (#6165): "Recent steps" hides the steps over a personal API key (static/js/undolist.js).
// kalmido-suite: fresh
// freelancer-matrix: undo (alice works without an organisation: her key step hidden, shown by the switch, skipped by "Back up to here")
// jsdom, fresh container. Invented names only. alice writes in the app (X-Kalmido-Device-Name: Laptop (Test)) and over her own
// API key "Script Bot" (Authorization: Bearer, /api/v1):
//  - the window lists the app's steps; the key's step is not there, a line says "1 step over an API key hidden"
//  - the switch "Show steps over API keys" shows it (device "Script Bot", "Over an API key") and is kept for the account
//    (undo_show_api on the server, a new page has it on); off again hides it
//  - switch off: "Back up to here" on the row below the hidden step takes back only the shown step; the key's change stays
//  - a shown step on the object the hidden step changed: the run stops and the window says so; nothing of it went
// The waits are on states (rows, values on the server), never on a fixed time.
const {boot, errs, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DEV = {'X-Kalmido-Device-Name': 'Laptop (Test)'};
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
  const T1 = (await call(CA, 'POST', '/api/tasks', {list_id: L, title: 'Plant tulips'}, DEV)).id;
  const T2 = (await call(CA, 'POST', '/api/tasks', {list_id: L, title: 'Cut the hedge'}, DEV)).id;
  await call(CA, 'PATCH', `/api/tasks/${T1}`, {title: 'Plant tulips and roses'}, DEV);
  const kp = await call(null, 'PATCH', `/api/v1/tasks/${T2}`, {priority: 3}, {Authorization: 'Bearer ' + KEY});
  check(kp.http === 200, `a change over the key (${kp.http})`);
  const srv = (await call(CA, 'GET', '/api/undo')).items || [];
  const [GH, G3, G2] = srv;
  check(GH?.via === 'token' && GH?.device === 'Script Bot' && G3?.via === '' && /Plant tulips/.test(G3?.label || '') && /Cut the hedge/.test(G2?.label || ''),
    `the server: the key's step on top, then the app's ${JSON.stringify(srv.slice(0, 3).map(g => [g.id, g.via, g.device, g.label]))}`);
  const task = async id => (await call(CA, 'GET', '/api/state')).tasks.find(t => t.id === id);

  let w = await boot({user: 'alice', hash: 'today'}); let d = w.document;
  const btn = () => d.querySelector('#top [data-act="hist-undo"]');
  const row = id => d.querySelector(`#pop:not(.hidden) .ulbody .ulrow[data-ul="s:${id}"]`);
  const chk = () => /** @type {any} */ (d.querySelector('#pop:not(.hidden) .ulhead .ulapi-chk'));
  btn().dispatchEvent(new w.MouseEvent('contextmenu', {bubbles: true, cancelable: true}));
  check(await until(() => row(G3.id)), 'the window shows the app\'s steps');
  check(!row(GH.id), 'the key\'s step is hidden');
  check(/1 step over an API key hidden/.test(d.querySelector('#pop .ulbody .ulhid')?.textContent || ''), `a line says one is hidden (${d.querySelector('#pop .ulbody .ulhid')?.textContent})`);
  check(chk() && !chk().checked && /Show steps over API keys/.test(d.querySelector('#pop .ulhead .ulapi')?.textContent || ''), 'the switch, off');

  // ---- the switch shows it (and is kept for the account)
  chk().click();
  check(await until(() => row(GH.id)), 'switch on: the key\'s step is listed');
  const rh = row(GH.id)?.textContent || '';
  check(/Script Bot/.test(rh) && /Over an API key/.test(rh) && !row(GH.id).querySelector('[data-ul-go]').disabled, `its row: the key's name, marked, can be taken back: ${rh}`);
  check(d.querySelector('#pop .ulbody .ulrow').getAttribute('data-ul') === 's:' + GH.id && !d.querySelector('#pop .ulbody .ulhid'), 'on top, no "hidden" line');
  check(await until(async () => (await call(CA, 'GET', '/api/state')).settings.undo_show_api === '1'), 'kept for the account (server)');
  w.eval('closePop()'); w.close();
  w = await boot({user: 'alice', hash: 'today'}); d = w.document;
  btn().dispatchEvent(new w.MouseEvent('contextmenu', {bubbles: true, cancelable: true}));
  check(await until(() => row(GH.id) && chk()?.checked), 'a new page: the switch on, the step listed');
  chk().click();
  check(await until(() => !row(GH.id) && row(G3.id)), 'switch off: hidden again');
  check(await until(async () => (await call(CA, 'GET', '/api/state')).settings.undo_show_api === '0'), 'off kept for the account');

  // ---- "Back up to here" on the shown row below the hidden step: only that one goes
  row(G3.id).querySelector('[data-ul-go]').click();
  check(await until(async () => (await task(T1))?.title === 'Plant tulips' && !w.eval('UL.busy')), 'Back up to here: the shown step went back');
  check((await task(T2))?.priority === 3, 'the key\'s change stays');
  check(await until(() => row(G3.id)?.classList.contains('ulundone')), 'its row says Undone');
  check(/1 step undone/.test(d.querySelector('#pop .ulnote')?.textContent || ''), `the window: one step (${d.querySelector('#pop .ulnote')?.textContent})`);
  const gh = ((await call(CA, 'GET', '/api/undo')).items || []).find(g => g.id === GH.id);
  check(gh?.state === 'done', `the key's step is still done (${gh?.state})`);

  // ---- the next row created the task the hidden step changed: the run stops there and says so
  await until(() => row(G2.id) && !row(G2.id).querySelector('[data-ul-go]').disabled && !w.eval('UL.busy'));
  row(G2.id).querySelector('[data-ul-go]').click();
  check(await until(() => /Stopped: a later step over an API key changed the same object/.test(d.querySelector('#pop .ulnote')?.textContent || '')), `the window says why it stopped (${d.querySelector('#pop .ulnote')?.textContent})`);
  const t2 = await task(T2);
  check(t2 && !t2.deleted_at && t2.priority === 3, `the task and the key's change stay (${JSON.stringify(t2 && [t2.priority, t2.deleted_at])})`);
  check(!row(G2.id)?.classList.contains('ulundone'), 'the row stays as it was');
  w.eval('closePop()'); w.close();

  check(!errs.length, 'no script errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21175_a_api_steps_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
