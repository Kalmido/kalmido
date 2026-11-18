// kalmido-suite: fresh
// 2.1389.0 (#6959) "My tasks": a dragged selection arrives whole. jsdom, own container. Before, the ghost said "3 tasks" but the
// own section's head, a row of the own order and a column of the board took the dragged task alone.
// - several selected, dragged onto the head of an own section: all of them stand there, in the selection's order, one moSave
// - dragged onto a row (lower part = after it): all of them after that row, order kept
// - "Recently assigned" takes nothing (unchanged)
// - the board (columns by priority): one drop sets the priority of every selected task
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
  const mk = async title => (await call(CF, 'POST', '/api/tasks', {title, list_id: L})).id;
  const TA = await mk('Water the plants'), TB = await mk('Book a trip'), TC = await mk('Call the bank'), TD = await mk('Pay the rent'), TE = await mk('Fix the bike');

  const w = await boot({user: 'frida', hash: 'assigned'}), d = w.document;
  const heads = () => [...d.querySelectorAll('#view .ghead[data-key^="ms:"]')];
  const head = re => heads().find(x => re.test(x.textContent));
  check(await until(() => head(/\bNow\b/) && head(/Soon/) && head(/Someday/)), 'own sections Now, Soon, Someday');
  const sid = re => +head(re).dataset.key.slice(3);
  const row = id => d.querySelector(`#view .trow[data-id="${id}"]`);
  const inSec = (re, id) => !!head(re)?.closest('.group')?.querySelector(`.trow[data-id="${id}"]`);
  const st = () => call(CF, 'GET', '/api/state');
  const order = async ids => { const o = (await st()).mine_order || {}; return ids.every(i => o[i] != null) && ids.every((i, k) => k === 0 || o[ids[k - 1]] < o[i]); };
  const select = ids => w.eval(`S.multiMode = true; S.multi.clear(); ${ids.map(i => `S.multi.add(${i});`).join(' ')} render();`);
  const dragTo = async (ids, target, o = {}) => {
    select(ids);
    const src = await until(() => row(ids[0]));
    dnd(w, src, 'dragstart');
    const got = w.eval('DG.ids ? [...DG.ids] : []');  // the selection in the order the view shows it (dgOrder)
    check(got.length === ids.length, `the ghost names ${ids.length} tasks`);
    dnd(w, target, 'dragover', o); dnd(w, target, 'drop', o); dnd(w, src, 'dragend');
    return got;
  };

  // three selected onto the head of Soon: all three there, in their order
  await until(() => row(TA) && row(TE));
  const o1 = await dragTo([TA, TC, TE], head(/Soon/));
  check(await until(() => inSec(/Soon/, TA) && inSec(/Soon/, TC) && inSec(/Soon/, TE)), 'onto the head of Soon: all three stand under it');
  check(await until(async () => { const s = (await st()).mine_sections.tasks; return [TA, TC, TE].every(i => s[i] === sid(/Soon/)); }), 'the server keeps all three in Soon');
  check(await until(() => order(o1)), 'their order is the selection\'s ' + o1);
  check(!inSec(/Soon/, TB) && !inSec(/Soon/, TD), 'the others stay where they were');

  // two selected onto the lower part of the first row of Soon: both right after it, in their order
  const o2 = await dragTo([TB, TD], rowBox(row(o1[0])), {clientY: 135});
  check(await until(() => inSec(/Soon/, TB) && inSec(/Soon/, TD)), 'onto a row of Soon: both stand in Soon');
  check(await until(() => order([o1[0], ...o2, ...o1.slice(1)])), 'after the row, in the selection\'s order ' + o2);

  // the board by priority: one drop on "High" sets both
  w.eval(`S.multiMode = false; S.multi.clear(); S.settings.mine_board = '1'; S.settings.mine_board_by = 'prio'; render();`);
  const col = await until(() => d.querySelector('#view .mboard .mbcol[data-mbcol="p5"]'));
  check(!!col, 'the board by priority with a column High');
  if (col) {
    await until(() => row(TB) && row(TD));
    await dragTo([TB, TD], col);
    check(await until(async () => { const ts = (await st()).tasks; return [TB, TD].every(i => +ts.find(t => t.id === i).priority === 5); }), 'onto the column High: both tasks get priority High');
    check(+(await st()).tasks.find(t => t.id === TA).priority !== 5, 'a task not selected keeps its priority');
  }
  w.close();

  console.log(`p21389_a_mine_multidrag_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
