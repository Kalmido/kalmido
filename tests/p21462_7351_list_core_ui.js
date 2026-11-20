// kalmido-suite: fresh
// Package 2.1462.0 (#7351) UI test: the drop core, step 3 - the project list's single drag runs through the same core as a
// selection (dragmulti.js plWhere / plPut: dgBlock, dgToSection, dgToNewSection). jsdom, own container, invented data. frida has
// no organisation (freelancer: the same ways).
// - plain reordering by dragging one task is one step with Undo (before: no Undo at all, dnd.js "plain reordering not") and goes
//   as the core's one batch (patch_each with _prev), not the old reorder request
// - one task dropped on a section's head: "Moved to section …" with Undo, Undo puts it back on the server
// - the board: one task and a selection dropped on a column take the same way (one batch each, one step each)
// - a locked task dropped onto a task of another project keeps its project and says so ("Unlock")
// - a task shown in a further project of its own (#1459): dragged there onto a section's head, only its link moves
// freelancer-matrix: tasks - frida has no organisation.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, undoToast, idle, histAdded} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
// every request that leaves the window: [method, path, body]
const stub = w => { const calls = [], of = w.fetch; w.fetch = (u, o = {}) => { calls.push([(o.method || 'GET').toUpperCase(), new URL(String(u), B).pathname, o.body ? (() => { try { return JSON.parse(o.body); } catch { return null; } })() : null]); return of(u, o); }; return calls; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments', 'kanban']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Home'})).id;
  const L2 = (await call(CF, 'POST', '/api/lists', {name: 'Garden'})).id;
  const mk = async (title, o = {}) => (await call(CF, 'POST', '/api/tasks', {title, list_id: L, ...o})).id;
  const TA = await mk('Water the plants'), TB = await mk('Book a trip'), TC = await mk('Call the bank');
  const SEC = (await call(CF, 'POST', '/api/sections', {list_id: L, name: 'Later'})).id;
  const task = id => call(CF, 'GET', '/api/tasks/' + id);

  // ================= plain reordering: one step with Undo (regression: before #7351 the single drag had none)
  let w = await boot({user: 'frida', hash: 'l/' + L}); let d = w.document;
  check(await until(() => d.querySelector(`#view .trow[data-id="${TC}"]`) && d.querySelector(`#view .trow[data-id="${TA}"]`)), 'the list shows the tasks');
  const calls = stub(w);
  const s0 = (await task(TC)).sort, sa = (await task(TA)).sort;
  let n0 = w.eval('HIST.undo.length');
  await w.eval(`dropTask(${TC}, document.querySelector('#view .trow[data-id="${TA}"]'), 0)`);  // a row without a size: before it
  check(await until(async () => (await task(TC)).sort < sa), 'reorder: the task stands before the other one on the server');
  check(calls.some(c => c[1] === '/api/tasks/batch' && c[2]?.action === 'patch_each' && c[2]?.data?.items?.[TC]) && !calls.some(c => c[1] === '/api/tasks/reorder'),
    'reorder: the core\'s batch, not the old reorder request ' + JSON.stringify(calls.filter(c => c[0] === 'POST').map(c => c[1])));
  check(await histAdded(w, n0), 'reorder: one step in the history');
  check(await undoToast(w, /1 task moved/), 'reorder: the drop offers Undo');
  check(await until(async () => (await task(TC)).sort === s0), 'reorder: Undo puts the place back on the server ' + s0);
  await idle(w);

  // ================= one task onto a section's head
  const head = await until(() => d.querySelector(`#view .ghead[data-section="${SEC}"]`));
  check(head, 'the section\'s head is shown');
  await w.eval(`dropTask(${TB}, document.querySelector('#view .ghead[data-section="${SEC}"]'), 0)`);
  check(await until(async () => (await task(TB)).section_id === SEC), 'section head: the task is in the section on the server');
  check(await undoToast(w, /Moved to section Later/), 'section head: "Moved to section Later" with Undo');
  check(await until(async () => (await task(TB)).section_id == null), 'section head: Undo takes it out again');
  await idle(w);

  // ================= a task shown in a further project of its own: only its link moves there
  const S2 = (await call(CF, 'POST', '/api/sections', {list_id: L2, name: 'Beds'})).id;
  const lk = await call(CF, 'POST', `/api/tasks/${TA}/links`, {list_id: L2});
  w.close();
  w = await boot({user: 'frida', hash: 'l/' + L2}); d = w.document;
  const lcalls = stub(w);
  if (lk.http < 300 && await until(() => d.querySelector(`#view .trow[data-id="${TA}"]`) && d.querySelector(`#view .ghead[data-section="${S2}"]`))) {
    await w.eval(`dropTask(${TA}, document.querySelector('#view .ghead[data-section="${S2}"]'), 0)`);
    check(await until(() => lcalls.some(c => c[0] === 'PATCH' && c[1] === `/api/tasks/${TA}/links/${L2}`)), 'link: the link\'s place is written ' + JSON.stringify(lcalls.map(c => c[0] + ' ' + c[1])));
    const ta = await task(TA);
    check(ta.list_id === L && !ta.section_id, 'link: the task itself stays in its project, without a section ' + JSON.stringify([ta.list_id, ta.section_id]));
    check(!lcalls.some(c => c[1] === '/api/tasks/batch'), 'link: the task itself is not moved');
  } else check(false, 'link: the further project shows the task ' + JSON.stringify(lk));
  await idle(w);
  w.close();

  // ================= a locked task keeps its project (#1118)
  const TL = await mk('Sign the lease');
  const TX = (await call(CF, 'POST', '/api/tasks', {title: 'Mow the lawn', list_id: L2})).id;
  await call(CF, 'PATCH', '/api/tasks/' + TL, {locked: 1});
  w = await boot({user: 'frida', hash: 'all'}); d = w.document;
  check(await until(() => d.querySelector(`#view .trow[data-id="${TL}"]`) && d.querySelector(`#view .trow[data-id="${TX}"]`)), 'All shows both tasks');
  await w.eval(`dropTask(${TL}, document.querySelector('#view .trow[data-id="${TX}"]'), 0)`);
  check(await until(() => /locked/i.test(d.querySelector('#toast:not(.hidden)')?.textContent || '')), 'locked: it says so ' + (d.querySelector('#toast')?.textContent || ''));
  await idle(w);
  check((await task(TL)).list_id === L, 'locked: the task stays in its project');
  w.close();

  // ================= the board: one task and a selection onto a column, the same way
  const K = (await call(CF, 'POST', '/api/lists', {name: 'Board', view: 'kanban'})).id;
  await call(CF, 'PATCH', '/api/lists/' + K, {view: 'kanban'});
  const KD = (await call(CF, 'POST', '/api/sections', {list_id: K, name: 'Doing'})).id;
  const mkK = async t => (await call(CF, 'POST', '/api/tasks', {title: t, list_id: K})).id;
  const K1 = await mkK('Paint the door'), K2 = await mkK('Oil the hinges'), K3 = await mkK('Sand the frame');
  w = await boot({user: 'frida', hash: 'l/' + K}); d = w.document;
  const kcalls = stub(w);
  const col = () => d.querySelector(`#view .kcol[data-kcol="${KD}"]`);
  check(await until(() => col() && d.querySelector(`#view .kcol .trow[data-id="${K1}"]`)), 'the board shows its column and cards');
  n0 = w.eval('HIST.undo.length');
  await w.eval(`dropTask(${K1}, document.querySelector('#view .kcol[data-kcol="${KD}"]'), 0)`);
  check(await until(async () => (await task(K1)).section_id === KD), 'board: one card into the column on the server');
  check(await histAdded(w, n0), 'board: one step for the card');
  await idle(w);
  n0 = w.eval('HIST.undo.length');
  await w.eval(`dropRun([${K2}, ${K3}], document.querySelector('#view .kcol[data-kcol="${KD}"]'), 0)`);
  check(await until(async () => (await task(K2)).section_id === KD && (await task(K3)).section_id === KD), 'board: the selection into the column on the server');
  check(await histAdded(w, n0), 'board: one step for the selection');
  const kb = kcalls.filter(c => c[1] === '/api/tasks/batch' && c[2]?.action === 'patch_each');
  check(kb.length === 2 && kb[0][2].data.items[K1]?.section_id === KD && kb[1][2].data.items[K2]?.section_id === KD && kb[1][2].data.items[K3], 'board: one batch per gesture, the same shape for one and for two ' + JSON.stringify(kb.map(c => Object.keys(c[2].data.items))));
  check(!kcalls.some(c => c[1] === '/api/tasks/reorder'), 'board: no reorder request');
  await idle(w);
  w.close();

  check(!errs.length, 'no script errors ' + errs.slice(0, 2));
  console.log(`p21462_7351_list_core_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack); process.exit(1); });
