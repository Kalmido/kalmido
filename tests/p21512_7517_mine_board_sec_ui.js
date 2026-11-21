// kalmido-suite: fresh
// (#7517) UI test: the board of My tasks with columns by own sections. jsdom, own container, invented data.
// frida has no organisation (freelancer: the same ways).
// - "Columns by" offers "Sections" only while the person has own sections; the server takes mine_board_by "sec"
// - a column per own section in its order ("Recently assigned" while it has tasks), each own one with the "…" of the list's
//   head (Rename, Move left / right, Delete)
// - one task dropped onto a column puts it into that own section (the list's adapter moPut, one Undo step); a selection dropped
//   onto a card stands after it in the same section; "Recently assigned" takes nothing and says so
// - back in the list (hinein / weiter / zurück): the task stands in the same own section
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
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
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
  const TA = await mk('Water the plants'), TB = await mk('Book a trip'), TC = await mk('Call the bank');
  const st = () => call(CF, 'GET', '/api/state');
  const secOf = async id => (await st()).mine_sections?.tasks?.[id] ?? null;

  // ================= without own sections: no "Sections" (the setting stays, the board shows Due)
  check((await call(CF, 'PATCH', '/api/settings', {mine_board: '1', mine_board_by: 'sec'})).http < 300, '#7517 the server takes mine_board_by "sec"');
  check((await call(CF, 'PATCH', '/api/settings', {mine_board_by: 'status'})).http === 400, 'an unknown grouping stays 400');
  await call(CF, 'PATCH', '/api/settings', {mine_board_by: 'due'});
  let w = await boot({user: 'frida', hash: 'assigned'}), d = w.document;
  await until(() => d.querySelector('#view .mobar .mbby'));
  w.eval(`S.mineSecs = {list: [], tasks: {}, rules: 0}; S.settings.mine_board_by = 'sec'; render();`);
  check(await until(() => d.querySelector('#view .mobar .mbby')) && !d.querySelector('#view .mobar [data-act="mo-by"][data-k="sec"]'), '#7517 without own sections: no "Sections" under Columns by');
  check(w.eval('moBoardBy()') === 'due' && d.querySelector('#view .mobar [data-act="mo-by"][data-k="due"]')?.classList.contains('on'), '... and the board shows Due');
  w.close();
  await call(CF, 'PATCH', '/api/settings', {mine_board_by: 'due'});

  // ================= own sections: Now, Soon, Someday
  const ms = (await call(CF, 'POST', '/api/mine-sections/init', {})).mine_sections;
  const S_ = k => ms.list.find(x => x.kind === k);
  const NOW = S_('now').id, SOON = S_('soon').id, REC = S_('recent')?.id;
  check(NOW && SOON && REC, 'setup: the default own sections');
  w = await boot({user: 'frida', hash: 'assigned'}); d = w.document;
  const secBtn = await until(() => d.querySelector('#view .mobar [data-act="mo-by"][data-k="sec"]'));
  check(secBtn && secBtn.textContent.trim() === 'Sections', '#7517 with own sections: "Sections" under Columns by');
  click(w, secBtn);
  check(await until(async () => (await st()).settings.mine_board_by === 'sec'), '#7517 the choice is kept on the server (every device)');
  const cols = () => [...d.querySelectorAll('#view .mboard .mbcol')].map(c => c.dataset.mbcol);
  check(await until(() => cols().join() === [REC, NOW, SOON, S_('later').id].map(i => 'ms:' + i).join()), '#7517 a column per own section in its order, Recently assigned first: ' + cols());
  const col = id => d.querySelector(`#view .mboard .mbcol[data-mbcol="ms:${id}"]`);
  const card = id => d.querySelector(`#view .mboard .trow[data-id="${id}"]`);
  const colOf = id => card(id)?.closest('.mbcol')?.dataset.mbcol;
  check(await until(() => colOf(TA) === 'ms:' + REC && colOf(TB) === 'ms:' + REC), 'new tasks stand in Recently assigned');
  check(!col(REC).querySelector('[data-act="section-menu"]') && col(SOON).querySelector('[data-act="section-menu"]'), '#7517 an own section\'s column has the "…", Recently assigned none');
  click(w, col(SOON).querySelector('[data-act="section-menu"]'));
  await until(() => d.querySelector('#pop [role="menuitem"]'));
  const items = [...d.querySelectorAll('#pop [role="menuitem"]')].map(b => b.textContent.trim());
  check(items.includes('Rename') && items.includes('Move left') && items.includes('Move right') && items.includes('Delete section (tasks stay)'), '#7517 the column\'s "…": Rename, Move left / right, Delete ' + items);
  w.eval('closePop()');

  // one task onto the column Soon (its free space)
  await w.eval(`dropTask(${TA}, document.querySelector('#view .mboard .mbcol[data-mbcol="ms:${SOON}"]'), 0)`);
  check(await until(async () => await secOf(TA) === SOON), '#7517 one task onto the column Soon: in the own section Soon (server)');
  check(await until(() => colOf(TA) === 'ms:' + SOON), '... and its card stands in the column Soon');
  check((await st()).tasks.find(t => t.id === TA).section_id == null, 'the project\'s own sections stay untouched');
  // one Undo step takes it back
  await w.eval('histStep("undo")');
  check(await until(() => colOf(TA) === 'ms:' + REC), '#7517 Undo: back in Recently assigned');
  await w.eval('histStep("redo")');
  check(await until(() => colOf(TA) === 'ms:' + SOON), 'Redo: in Soon again');

  // Recently assigned takes nothing and says so
  const nn = await w.eval(`dropFor(document.querySelector('#view .mboard .mbcol[data-mbcol="ms:${REC}"]'), 10, [${TA}])?.w.no`);
  check(/Recently assigned/.test(String(nn || '')), '#7517 the column Recently assigned refuses with a message: ' + nn);
  await w.eval(`dropTask(${TA}, document.querySelector('#view .mboard .mbcol[data-mbcol="ms:${REC}"]'), 0)`);
  check(await until(() => /Recently assigned/.test(d.querySelector('#toast')?.textContent || '')) && await secOf(TA) === SOON, '... a drop there says so, the task stays in Soon');

  // a selection onto the lower part of the card "Water the plants" (column Soon)
  w.eval(`S.multiMode = true; S.multi.clear(); S.multi.add(${TB}); S.multi.add(${TC}); render();`);
  const src = await until(() => card(TB));
  dnd(w, src, 'dragstart');
  check(w.eval('DG.ids ? DG.ids.length : 0') === 2, 'the ghost names 2 tasks');
  const tgt = rowBox(card(TA));
  dnd(w, tgt, 'dragover', {clientY: 136}); dnd(w, tgt, 'drop', {clientY: 136}); dnd(w, src, 'dragend');
  check(await until(async () => await secOf(TB) === SOON && await secOf(TC) === SOON), '#7517 a selection onto a card of Soon: both in Soon');
  const inCol = id => [...col(id).querySelectorAll('.trow[data-id]')].map(x => +x.dataset.id);
  check(await until(() => inCol(SOON)[0] === TA && inCol(SOON).slice(1).sort().join() === [TB, TC].sort().join()), '... after the card: ' + inCol(SOON));
  w.eval(`S.multiMode = false; S.multi.clear(); render();`);

  // ================= back to the list: the same own section
  click(w, d.querySelector('#view .mobar [data-act="mo-view"][data-k="list"]'));
  const gkey = id => d.querySelector(`#view .trow[data-id="${id}"]`)?.closest('.group')?.querySelector(':scope > .ghead')?.dataset.key;
  check(await until(() => gkey(TA) === 'ms:' + SOON && gkey(TB) === 'ms:' + SOON && gkey(TC) === 'ms:' + SOON), '#7517 the list shows the three tasks in the same own section Soon');
  click(w, d.querySelector('#view .mobar [data-act="mo-view"][data-k="board"]'));
  check(await until(() => colOf(TA) === 'ms:' + SOON && d.querySelector('#view .mobar [data-act="mo-by"][data-k="sec"]')?.classList.contains('on')), 'back on the board: still columns by section');
  w.close();

  console.log(`p21512_7517_mine_board_sec_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
