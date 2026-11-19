// kalmido-suite: fresh
// 2.1389.0 (#6959) "My tasks": a dragged selection arrives whole. jsdom, own container. Before, the ghost said "3 tasks" but the
// own section's head, a row of the own order and a column of the board took the dragged task alone.
// - several selected, dragged onto the head of an own section: all of them stand there, in the selection's order, one moSave
// - dragged onto a row (lower part = after it): all of them after that row, order kept
// - "Recently assigned" takes nothing (unchanged)
// - the board (columns by priority): one drop sets the priority of every selected task
// 2.1444 (#7344) the drop core of My tasks (gina: collaboration on, no organisation):
// - a mixed selection (some already in the target section, some not) lands whole: onto a head, onto a row (also onto a row of
//   the selection itself = at its place), through "Move to section…"; three tasks put in another order inside one section
// - a drop shows the own order again when a column's sort hid it; "Recently assigned" says why it takes nothing
// - "New section" is a drop target: it lights up, asks the name, Cancel moves nothing, a name makes it with the whole selection
// - "Unassigned in your projects": dropped into an own section (alone or mixed) = assigned to me, in the same Undo step
// - a subtask dragged out onto a row of the own order: standalone there, with the parent's date / priority in its empty fields
// - Undo takes back the whole gesture (the own order and sections, the assignment)
// freelancer-matrix: tasks - frida and gina have no organisation.
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
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
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

  // ---- 2.1444 (#7344): the drop core
  const gu = await call(CA, 'POST', '/api/users', {username: 'gina', display_name: 'Gina', password: 'password123', email: 'gina@example.com', orgs: []});
  const CG = await login('gina');
  await call(CG, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab'});
  const me = (await call(CG, 'GET', '/api/state')).me?.id;
  check(gu.http < 300 && me > 0 && ((await call(CG, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'gina is in no organisation');
  const LG = (await call(CG, 'POST', '/api/lists', {name: 'Garden'})).id;
  const due = new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10);
  const mkg = async (title, o = {}) => (await call(CG, 'POST', '/api/tasks', {title, list_id: LG, ...o})).id;
  const G = [];
  for (const t of ['Mow the lawn', 'Cut the hedge', 'Plant tulips', 'Rake leaves', 'Clean the pond', 'Fix the fence', 'Paint the shed']) G.push(await mkg(t, {assignee_id: me}));
  const [K1, K2] = [await mkg('Order compost'), await mkg('Sharpen the shears')];  // nobody has them: "Unassigned in your projects"
  const PA = await mkg('Build a greenhouse', {assignee_id: me, due, priority: 5}), S1 = await mkg('Buy glass panes', {parent_id: PA, assignee_id: me});
  check([...G, K1, K2, PA, S1].every(x => x > 0), 'gina\'s tasks');

  const v = await boot({user: 'gina', hash: 'assigned'}), e = v.document;
  const gHeads = () => [...e.querySelectorAll('#view .ghead[data-key^="ms:"]')];
  const gHead = re => gHeads().find(x => re.test(x.textContent));
  const gRow = id => e.querySelector(`#view .trow[data-id="${id}"]`);
  const gIn = (re, id) => !!gHead(re)?.closest('.group')?.querySelector(`.trow[data-id="${id}"]`);
  const gSid = re => +gHead(re).dataset.key.slice(3);
  const gSt = () => call(CG, 'GET', '/api/state');
  const gOrder = async ids => { const o = (await gSt()).mine_order || {}; return ids.every(i => o[i] != null) && ids.every((i, k) => k === 0 || o[ids[k - 1]] < o[i]); };
  const gSecs = async (re, ids) => { const s = (await gSt()).mine_sections.tasks; return ids.every(i => s[i] === gSid(re)); };
  const toastTxt = () => e.querySelector('#toast')?.textContent || '';
  const gSel = ids => v.eval(`S.multiMode = true; S.multi.clear(); ${ids.map(i => `S.multi.add(${i});`).join(' ')} render();`);
  const gDrag = async (ids, target, o = {}) => {
    gSel(ids);
    const src = await until(() => gRow(ids[0]));
    dnd(v, src, 'dragstart');
    const got = v.eval('DG.ids ? [...DG.ids] : []');
    check(got.length === ids.length, `the ghost names ${ids.length} tasks`);
    const ov = dnd(v, target, 'dragover', o);
    if (o.lit) check(ov.defaultPrevented && target.classList.contains(o.lit), `the target lights up while dragged over (${o.lit})`);
    dnd(v, target, 'drop', o); dnd(v, src, 'dragend');
    v.eval('S.multiMode = false; S.multi.clear(); render();');
    return got;
  };
  check(await until(() => gHead(/\bNow\b/) && gHead(/Soon/) && gHead(/Someday/) && gHead(/Recently assigned/)), 'gina: own sections, her tasks in "Recently assigned"');

  // "Recently assigned" says why it takes nothing (was: a silent nothing)
  await v.eval(`dropTask(${G[0]}, document.querySelector('#view .ghead[data-key="${gHead(/Recently assigned/).dataset.key}"]'), 0)`);
  check(/takes no tasks/.test(toastTxt()) && gIn(/Recently assigned/, G[0]), '"Recently assigned": a message, the task stays');

  // all seven onto Soon, then two of them onto Someday
  await until(() => gRow(G[6]));
  await gDrag(G, gHead(/Soon/));
  check(await until(() => G.every(i => gIn(/Soon/, i))) && await until(() => gSecs(/Soon/, G)), 'seven tasks from "Recently assigned" onto Soon');
  await gDrag([G[0], G[1]], gHead(/Someday/));
  check(await until(() => gIn(/Someday/, G[0]) && gIn(/Someday/, G[1])), 'two onto Someday');

  // (1) a mixed selection onto a head: two already in Someday, two from Soon -> all four in Someday, in the selection's order, on top
  const m1 = await gDrag([G[0], G[2], G[1], G[3]], gHead(/Someday/));
  check(await until(() => [G[0], G[1], G[2], G[3]].every(i => gIn(/Someday/, i))), 'mixed selection onto the head of Someday: all four stand there');
  check(await until(() => gSecs(/Someday/, m1)) && await until(() => gOrder(m1)), 'the server keeps all four in Someday, in the selection\'s order ' + m1);

  // (2) a mixed selection onto a row that belongs to the selection itself: at its place (Soon: G4 G5 G6 -> G4 [m2] G6)
  const m2 = await gDrag([G[5], G[0], G[1]], rowBox(gRow(G[5])), {clientY: 105});
  check(await until(() => [G[5], G[0], G[1]].every(i => gIn(/Soon/, i))), 'onto a row of the selection: all three in Soon');
  check(await until(() => gOrder([G[4], ...m2, G[6]])), 'at the place of that row, in the selection\'s order ' + m2);

  // (3) the menu "Move to section…" with a mixed selection: two in Soon, two in Someday -> all in Someday
  v.eval(`closePop(); mseSecPicker(document.querySelector('#top h1'), [${G[4]}, ${G[2]}, ${G[6]}, ${G[3]}])`);
  const gmi = txt => [...e.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml')?.textContent || b.textContent).trim() === txt);
  click(v, await until(() => gmi('Someday')));
  check(await until(() => [G[4], G[2], G[6], G[3]].every(i => gIn(/Someday/, i))) && await until(() => gSecs(/Someday/, [G[4], G[2], G[6], G[3]])), 'menu with a mixed selection: all four in Someday');

  // (4) three put in another order inside one section; a column's sort that hid the own order is reset by the drop
  const sd = async () => { const o = (await gSt()).mine_order, s = (await gSt()).mine_sections.tasks; return G.filter(i => s[i] === gSid(/Someday/)).sort((a, b) => o[a] - o[b]); };
  const z0 = await until(sd);
  check(z0.length >= 4, 'Someday has at least four tasks ' + z0);
  v.eval(`LS.set('sort2.assigned', 'title'); render();`);
  const m4 = await gDrag([z0[1], z0[2], z0[3]], rowBox(gRow(z0[0])), {clientY: 105});
  check(await until(() => gOrder([...m4, z0[0]])), 'three tasks of Someday dropped above its first one: they stand before it ' + m4);
  check(v.eval(`LS.get('sort2.assigned', null)`) === null, 'the drop switched the column\'s sort back to the own order');
  await v.eval(`dropTask(${z0[0]}, document.querySelector('#view .trow[data-id="${m4[0]}"]'), 0)`);
  check(await until(() => gOrder([z0[0], ...m4])), 'one task dragged above them: first again');

  // (5) "New section" is a drop target: Cancel = nothing moved, a name = a section with the whole selection
  const n0 = gHeads().length, before = JSON.stringify((await gSt()).mine_sections.tasks);
  v.prompt = () => null;
  await gDrag([G[0], G[1]], await until(() => e.querySelector('#view [data-dropnew]')), {lit: 'drop'});
  await sleep(400);
  check(gHeads().length === n0 && JSON.stringify((await gSt()).mine_sections.tasks) === before, '"New section" cancelled: no section, nothing moved');
  v.prompt = () => 'Weekend';
  await gDrag([G[0], G[1]], e.querySelector('#view [data-dropnew]'));
  check(await until(() => gHead(/Weekend/) && gIn(/Weekend/, G[0]) && gIn(/Weekend/, G[1])), 'dropped onto "New section": the section Weekend with both tasks');

  // (6) "Unassigned in your projects": mixed with an own task onto a head = assigned to me, in Soon; Undo takes it all back
  const kb = await until(() => e.querySelector('#view .ghead[data-key="kb:mine"]'));
  check(!!kb, 'the group "Unassigned in your projects"');
  if (kb && !gRow(K1)) click(v, kb);
  await until(() => gRow(K1) && gRow(K2));
  const g0sec = (await gSt()).mine_sections.tasks[G[0]];
  await gDrag([K1, G[0]], gHead(/Soon/));
  check(await until(() => gIn(/Soon/, K1) && gIn(/Soon/, G[0])), 'mixed from both groups onto Soon: both stand there');
  check(await until(async () => (await gSt()).tasks.find(t => t.id === K1).assignee_id === me) && await until(() => gSecs(/Soon/, [K1, G[0]])), 'the unassigned task is mine now, the server keeps both in Soon');
  check(/Assigned to me/.test(toastTxt()), 'the message says it was assigned: ' + toastTxt());
  await v.eval('histStep("undo")');
  check(await until(async () => !(await gSt()).tasks.find(t => t.id === K1).assignee_id), 'Undo: the task is unassigned again');
  check(await until(async () => (await gSt()).mine_sections.tasks[G[0]] === g0sec), 'Undo: the own task is back in its section');
  check(await until(() => !gIn(/Soon/, K1)), 'Undo: the unassigned task left Soon');
  // alone onto a row of Someday
  if (!await until(() => gRow(K2), 3000)) click(v, e.querySelector('#view .ghead[data-key="kb:mine"]'));
  check(await until(() => gRow(K2)), 'the second unassigned task is shown');
  const anchor = (await sd())[0];
  await v.eval(`dropTask(${K2}, document.querySelector('#view .trow[data-id="${anchor}"]'), 0)`);
  check(await until(async () => (await gSt()).tasks.find(t => t.id === K2).assignee_id === me) && await until(() => gSecs(/Someday/, [K2])), 'one unassigned task onto a row of Someday: mine, in Someday');
  check(await until(() => gOrder([K2, anchor])), 'before that row');

  // (7) a subtask dragged out onto a row of the own order: standalone there, the parent's date and priority in its empty fields
  await until(() => gRow(S1));
  await v.eval(`dropTask(${S1}, document.querySelector('#view .trow[data-id="${anchor}"]'), 0)`);
  check(await until(async () => { const t = (await gSt()).tasks.find(x => x.id === S1); return !t.parent_id && t.due === due && +t.priority === 5; }), 'the subtask is standalone and took the parent\'s date / priority (#6436)');
  check(await until(() => gSecs(/Someday/, [S1])) && await until(() => gOrder([S1, anchor])), 'it stands in Someday before that row');
  check(/Don’t adopt/.test(toastTxt()), 'the message offers "Don’t adopt": ' + toastTxt());
  v.close();

  console.log(`p21389_a_mine_multidrag_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
