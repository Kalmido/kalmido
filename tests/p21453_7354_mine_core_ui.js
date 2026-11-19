// kalmido-suite: fresh
// Package 2.1453.0 (#7354) UI test: the drop core, step 2 - the other ways of "My tasks" go through its adapters. jsdom, own
// container, invented data. frida has no organisation (freelancer: the same ways).
// - the board (columns by priority) is an adapter: a selection dropped onto a CARD (its lower part) of the column High takes
//   High for all of them (before: it went into the project's order and kept the priority); one task dropped onto a card takes
//   the column too; a drop onto the column's free space as before
// - Alt+↑ / Alt+↓ in the list of My tasks moves the task in the OWN order (the person's) - the project's order for everybody
//   stays, the view's sort is not switched to Priority (before: both); at the top it says so; Undo takes the step back
// - "Move to section…" (menu and multi panel) went through the core already with #7344 (mseMoveTo -> moPut, one Undo step)
// freelancer-matrix: tasks - frida has no organisation.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const dnd = (w, el, type, o = {}) => { const e = new w.Event(type, {bubbles: true, cancelable: true}); e.dataTransfer = {setData() {}, getData: () => '', effectAllowed: '', dropEffect: '', setDragImage() {}}; e.clientY = o.clientY ?? 10; el.dispatchEvent(e); return e; };
const rowBox = el => { el.getBoundingClientRect = () => ({top: 100, bottom: 140, height: 40, left: 0, right: 600, width: 600}); return el; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Home'})).id;
  const mk = async (title, o = {}) => (await call(CF, 'POST', '/api/tasks', {title, list_id: L, ...o})).id;
  const TA = await mk('Water the plants'), TB = await mk('Book a trip'), TC = await mk('Call the bank', {priority: 5}), TD = await mk('Pay the rent'), TE = await mk('Fix the bike');
  const st = () => call(CF, 'GET', '/api/state');
  const prio = async id => +(await st()).tasks.find(t => t.id === id).priority;

  // ================= the board by priority
  await call(CF, 'PATCH', '/api/settings', {mine_board: '1', mine_board_by: 'prio'});
  let w = await boot({user: 'frida', hash: 'assigned'}), d = w.document;
  const card = id => d.querySelector(`#view .mboard .trow[data-id="${id}"]`);
  const colOf = id => card(id)?.closest('.mbcol')?.dataset.mbcol;
  check(await until(() => card(TC) && colOf(TC) === 'p5' && card(TA)), 'the board: Call the bank in High, the others elsewhere');
  // a selection onto the lower part of the card "Call the bank" (column High)
  w.eval(`S.multiMode = true; S.multi.clear(); S.multi.add(${TA}); S.multi.add(${TB}); render();`);
  const src = await until(() => card(TA));
  dnd(w, src, 'dragstart');
  check(w.eval('DG.ids ? DG.ids.length : 0') === 2, 'the ghost names 2 tasks');
  const tgt = rowBox(card(TC));
  dnd(w, tgt, 'dragover', {clientY: 136}); dnd(w, tgt, 'drop', {clientY: 136}); dnd(w, src, 'dragend');
  check(await until(async () => await prio(TA) === 5 && await prio(TB) === 5), '#7354 a selection onto a card of High: both take High');
  check(await until(() => colOf(TA) === 'p5' && colOf(TB) === 'p5'), '#7354 ... and stand in the column High');
  check(await prio(TD) !== 5, 'a task not selected keeps its priority');
  // one task onto a card (the drag of one task, dnd.js): it takes the column too
  w.eval(`S.multiMode = false; S.multi.clear(); render();`);
  await until(() => card(TD) && card(TC));
  await w.eval(`dropTask(${TD}, document.querySelector('#view .mboard .trow[data-id="${TC}"]'), 0)`);
  check(await until(async () => await prio(TD) === 5), '#7354 one task onto a card of High: it takes High');
  // the column's free space as before (Low)
  const low = await until(() => d.querySelector('#view .mboard .mbcol[data-mbcol="p1"]'));
  await w.eval(`dropTask(${TE}, document.querySelector('#view .mboard .mbcol[data-mbcol="p1"]'), 0)`);
  check(low && await until(async () => await prio(TE) === 1), 'one task onto the free space of the column Low: Low');
  w.close();

  // ================= Alt+arrow in the list: the own order
  await call(CF, 'PATCH', '/api/settings', {mine_board: '0'});
  const sortsBefore = Object.fromEntries((await st()).tasks.filter(t => t.list_id === L).map(t => [t.id, t.sort]));
  w = await boot({user: 'frida', hash: 'assigned'}); d = w.document;
  const rows = () => [...d.querySelectorAll('#view .trow[data-id]')].map(x => +x.dataset.id);
  await until(() => rows().length >= 5);
  // into an own section first ("Recently assigned" keeps no order: the core says so)
  const own = await w.eval(`(async () => { const s = mseList().find(x => x.kind !== 'recent'); await mseMoveTo([${[TA, TB, TC, TD, TE].join(',')}], s.id); return s.id; })()`);
  check(own && await until(() => [TA, TB, TC, TD, TE].every(t => d.querySelector(`#view .trow[data-id="${t}"]`)?.closest('.group')?.querySelector(':scope > .ghead')?.dataset.key === 'ms:' + own)), 'setup: the five tasks in an own section');
  const order0 = rows(), i = order0.length - 1, id = order0[i], up = order0[i - 1];
  const sameGroup = d.querySelector(`#view .trow[data-id="${id}"]`).closest('.group') === d.querySelector(`#view .trow[data-id="${up}"]`).closest('.group');
  check(sameGroup, 'the last two rows stand in one group');
  const key = (k, o = {}) => w.dispatchEvent(new w.KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true, ...o}));
  w.eval(`kfocus(${id})`);
  key('ArrowUp', {altKey: true});
  check(await until(() => rows().indexOf(id) === i - 1 && rows().indexOf(up) === i), '#7354 Alt+↑: the task stands one row higher ' + rows());
  check(await until(async () => { const o = (await st()).mine_order || {}; return o[id] != null && o[up] != null && o[id] < o[up]; }), '#7354 ... in the own order (the server keeps it)');
  const sortsAfter = Object.fromEntries((await st()).tasks.filter(t => t.list_id === L).map(t => [t.id, t.sort]));
  check(JSON.stringify(sortsAfter) === JSON.stringify(sortsBefore), '#7354 the project\'s order for everybody stays as it was');
  check(!w.eval(`LS.get('sort2.assigned', null)`), '#7354 the view\'s sort is not switched to Priority');
  await w.eval('histStep("undo")');
  check(await until(() => rows().indexOf(id) === i), '#7354 Undo: the task stands where it was');
  // at the top of its group: it says so, nothing moves
  const first = d.querySelector(`#view .trow[data-id="${id}"]`).closest('.group')?.querySelector('.trow[data-id]');
  const fid = +first.dataset.id, before = rows().join();
  w.eval(`kfocus(${fid})`);
  key('ArrowUp', {altKey: true});
  check(await until(() => /Already at the top/.test(d.querySelector('#toast')?.textContent || '')), '#7354 the first row: "Already at the top"');
  check(rows().join() === before, 'nothing moved');
  w.close();

  console.log(`p21453_7354_mine_core_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
