// 2.1271.0 C UI test (jsdom), fresh DB, invented data only:
// kalmido-suite: fresh
// - #6436 a subtask made standalone takes the date (with its time) and the priority of its former parent, only into its own
//   EMPTY fields (a value of its own stays); assignee and tags never come along. One toast says what was adopted with the
//   button "Don't adopt", which sets back only those fields - the task stays standalone - and the server keeps that (reload).
//   A parent without date / priority, or a subtask with all of it filled: no adoption, no "Don't adopt".
//   Ways: dragged out of the parent onto a standalone row, onto a project of the sidebar, onto a column of the board (kanban),
//   the selection's "Out of the parent task" (one task, and several at once: ONE collective toast, ONE "Don't adopt" for all,
//   counting only the tasks that adopted something), "Outdent" in the task menu. Once more as a person without an organisation.
const {boot, errs, sleep, B, login, undoToast} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 100});
const st = async (ck = CK) => call('GET', '/api/state', null, ck);
const taskOf = async (id, ck = CK) => (await st(ck)).tasks.find(t => t.id === id);
const toastText = d => d.querySelector('#toast:not(.hidden)')?.textContent || '';
const toastBtn = d => d.querySelector('#toast:not(.hidden) button:not(.tx)')?.textContent.trim() || '';
// every text #toast showed since the call (a toast can be gone again before a slow check looks)
const toastSeen = w => { const el = w.document.querySelector('#toast'), seen = []; new w.MutationObserver(() => { if (!el.classList.contains('hidden')) seen.push(el.textContent); }).observe(el, {childList: true, subtree: true, characterData: true, attributes: true}); return seen; };
const dnd = (w, el, type, o = {}) => { const e = new w.Event(type, {bubbles: true, cancelable: true}); e.dataTransfer = {setData() {}, getData: () => '', effectAllowed: '', dropEffect: '', setDragImage() {}}; e.clientY = o.clientY ?? 10; el.dispatchEvent(e); return e; };
const rowBox = el => { el.getBoundingClientRect = () => ({top: 100, bottom: 140, height: 40, left: 0, right: 600, width: 600}); return el; };
const click = (w, el, o = {}) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true, ...o}));
const DUE = '2026-12-01', TIME = '09:30', OWN = '2026-12-07';
// the fields this test looks at, as the server keeps them
const pick = t => t && {parent_id: t.parent_id || null, due: t.due || null, due_time: t.due_time || null, priority: +t.priority || 0, tags: [...(t.tags || [])].sort().join(','), assignee_id: t.assignee_id || null};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// one task selected, the selection's menu (the phone bar's "More"): "Out of the parent task"
const outMenu = async (w, id) => {
  w.eval(`(() => { S.multi.clear(); S.multi.add(${id}); renderMultiBar(); render(); multiMoreMenu(document.querySelector('#top h1') || document.body); })()`);
  const b = await until(() => [...w.document.querySelectorAll('#pop button')].find(x => x.textContent.trim() === 'Out of the parent task'));
  if (b) click(w, b);
  return !!b;
};

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'kanban,collab'});
  const ME = (await st()).me.id;
  const P = (await call('POST', '/api/lists', {name: 'Launch', kind: 'project'})).id;
  const P2 = (await call('POST', '/api/lists', {name: 'Backlog', kind: 'project'})).id;
  const mk = async (title, extra = {}) => (await call('POST', '/api/tasks', {title, list_id: P, ...extra})).id;
  // the parent: date, time, priority High, a tag and an assignee (those two never come along)
  const PAR = await mk('Trade fair', {due: DUE, due_time: TIME, priority: 5, tags: ['fair'], assignee_id: ME});
  const BARE = await mk('Loose ideas');  // a parent without date and priority
  const TOP = await mk('Standalone anchor'), TOP1 = await mk('Low anchor', {priority: 1});  // a drop between rows of another priority takes that one (sort "prio")
  const S1 = await mk('Book the booth', {parent_id: PAR});                                   // empty: takes everything
  const S2 = await mk('Print flyers', {parent_id: PAR, due: OWN, priority: 1});               // full: takes nothing
  const S3 = await mk('Order badges', {parent_id: PAR, priority: 3});                         // own priority: takes the date only
  const S4 = await mk('Plan travel', {parent_id: PAR});                                       // sidebar project
  const S5 = await mk('Brief the team', {parent_id: PAR, tags: ['team']});                    // several at once (adopts)
  const S6 = await mk('Ship the posters', {parent_id: PAR});                                  // several at once (adopts)
  const S7 = await mk('Rent the van', {parent_id: PAR, due: OWN, priority: 7});               // several at once (full: not counted)
  const S8 = await mk('Write the speech', {parent_id: PAR});                                  // task menu: Outdent
  const B1 = await mk('Sketch something', {parent_id: BARE});                                 // parent without anything
  const before = {};
  for (const id of [S1, S2, S3, S4, S5, S6, S7, S8, B1]) before[id] = pick(await taskOf(id));

  let w = await boot({user: 'alice', hash: 'l/' + P, ls: {hintsSeen: ['dgalt', 'dgmulti'], ['tasks.sort2.l:' + P]: '"prio"'}}); let d = w.document;
  const row = id => d.querySelector(`#view .trow[data-id="${id}"]`);
  const reload = async () => { await w.eval('load().then(render)'); await sleep(300); };
  check(await until(() => row(TOP) && row(PAR)), 'the project list renders');
  // the subtasks are shown under their parent (unfolded, should the list keep them folded)
  const unfold = (ww, id) => ww.eval(`(() => { S.collapsed.delete('t${id}'); render(); })()`);
  const showKids = async () => { unfold(w, PAR); unfold(w, BARE); await sleep(100); };
  await showKids();

  // ---- 1. dragged out of the parent onto a standalone row: everything empty is filled
  let seen = toastSeen(w);
  check(await until(() => row(S1)), 'the subtask "Book the booth" is shown');
  dnd(w, row(S1), 'dragstart');
  dnd(w, rowBox(row(TOP)), 'dragover', {clientY: 102}); dnd(w, row(TOP), 'drop', {clientY: 102}); dnd(w, row(S1), 'dragend');
  check(await until(async () => !(await taskOf(S1)).parent_id), 'drag out: "Book the booth" is standalone');
  let s1 = pick(await taskOf(S1));
  check(s1.due === DUE && s1.due_time === TIME && s1.priority === 5, 'drag out: date, time and priority of the parent adopted ' + JSON.stringify(s1));
  check(s1.tags === '' && s1.assignee_id === null, 'drag out: no tags, no assignee came along ' + JSON.stringify(s1));
  check(await until(() => /Date and priority of “Trade fair” adopted/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'drag out: the toast names it, button "Don’t adopt": ' + toastText(d) + ' / ' + seen.join(' | '));
  check(await undoToast(w, /adopted/), 'drag out: "Don’t adopt" tapped');
  check(await until(async () => { const x = pick(await taskOf(S1)); return !x.due && !x.due_time && !x.priority && !x.parent_id; }), 'Don’t adopt: date, time and priority empty again, the task stays standalone ' + JSON.stringify(pick(await taskOf(S1))));
  await reload();
  check(same(pick(w.eval(`S.tasks.get(${S1})`)), pick(await taskOf(S1))) && !w.eval(`S.tasks.get(${S1}).due`), 'after a reload the page shows the server\'s state (no date, standalone)');

  // ---- 2. a subtask with its own date and priority: nothing adopted, no "Don't adopt"
  await showKids();
  seen = toastSeen(w);
  check(await until(() => row(S2)), 'the subtask "Print flyers" is shown');
  dnd(w, row(S2), 'dragstart');
  dnd(w, rowBox(row(TOP1)), 'dragover', {clientY: 102}); dnd(w, row(TOP1), 'drop', {clientY: 102}); dnd(w, row(S2), 'dragend');
  check(await until(async () => !(await taskOf(S2)).parent_id), 'filled: "Print flyers" is standalone');
  check(same(pick(await taskOf(S2)), {...before[S2], parent_id: null}), 'filled: its own date and priority stay ' + JSON.stringify(pick(await taskOf(S2))));
  await sleep(600);
  check(!seen.some(x => /adopted|Don’t adopt/.test(x)), 'filled: no adoption toast: ' + seen.join(' | '));

  // ---- 3. the selection's menu "Out of the parent task" with one task: its own priority stays, the date comes
  await reload(); await showKids();
  check(await until(() => row(S3)), 'the subtask "Order badges" is shown');
  check(await outMenu(w, S3), 'the selection\'s menu offers "Out of the parent task"');
  check(await until(async () => !(await taskOf(S3)).parent_id), 'Out of the parent task: "Order badges" is standalone');
  let s3 = pick(await taskOf(S3));
  check(s3.due === DUE && s3.due_time === TIME && s3.priority === 3, 'Out of the parent task: date adopted, its own priority (Medium) stays ' + JSON.stringify(s3));
  check(await until(() => /Date of “Trade fair” adopted/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'Out of the parent task: the toast says "Date of … adopted": ' + toastText(d));
  check(await undoToast(w, /adopted/), 'Out of the parent task: "Don’t adopt" tapped');
  check(await until(async () => { const x = pick(await taskOf(S3)); return !x.due && !x.due_time && x.priority === 3 && !x.parent_id; }), 'Don’t adopt: only the date went, the priority of its own stays ' + JSON.stringify(pick(await taskOf(S3))));

  // ---- 4. several at once: one collective toast, counting only the tasks that adopted something; one "Don't adopt" for all
  await reload(); await showKids();
  check(await until(() => row(S5) && row(S6) && row(S7)), 'the three subtasks are shown');
  w.eval(`(() => { S.multi.clear(); [${S5}, ${S6}, ${S7}].forEach(i => S.multi.add(i)); renderMultiBar(); render(); })()`);
  check(await until(() => d.querySelector('#detail.multi [data-act="dg-out"]')), 'several: "Out of the parent task" is offered');
  let calls = []; { const of = w.fetch; w.fetch = (u, o = {}) => { calls.push([(o.method || 'GET').toUpperCase(), String(u)]); return of(u, o); }; }
  click(w, d.querySelector('#detail.multi [data-act="dg-out"]'));
  check(await until(async () => { const s = (await st()).tasks; return [S5, S6, S7].every(i => !s.find(t => t.id === i).parent_id); }), 'several: all three are standalone');
  check(calls.filter(c => c[0] === 'POST' && /\/api\/tasks\/batch/.test(c[1])).length === 1 && !calls.some(c => c[0] === 'PATCH'), 'several: ONE batch request (detach and adoption together)');
  const s5 = pick(await taskOf(S5)), s6 = pick(await taskOf(S6)), s7 = pick(await taskOf(S7));
  check(s5.due === DUE && s5.priority === 5 && s5.tags === 'team' && s6.due === DUE && s6.priority === 5, 'several: the empty ones adopted, tags kept ' + JSON.stringify([s5, s6]));
  check(same(s7, {...before[S7], parent_id: null}), 'several: the full one kept its own ' + JSON.stringify(s7));
  check(await until(() => /adopted for 2 tasks/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'several: ONE collective toast counting 2 tasks: ' + toastText(d));
  check(await undoToast(w, /adopted for 2 tasks/), 'several: "Don’t adopt" tapped');
  check(await until(async () => { const s = (await st()).tasks, g = i => pick(s.find(t => t.id === i)); return !g(S5).due && !g(S5).priority && !g(S6).due && !g(S6).priority && g(S5).tags === 'team' && same(g(S7), {...before[S7], parent_id: null}) && !g(S5).parent_id && !g(S6).parent_id; }),
    'several: Don’t adopt empties only the adopted fields, the full one and the tags stay, all stay standalone');

  // ---- 5. a parent without date and priority: nothing to adopt, no adoption toast
  await reload();
  await showKids();
  check(await until(() => row(B1)), 'the subtask "Sketch something" is shown');
  seen = toastSeen(w);
  check(await outMenu(w, B1), 'bare parent: "Out of the parent task" is offered');
  check(await until(async () => !(await taskOf(B1)).parent_id), 'bare parent: "Sketch something" is standalone');
  check(same(pick(await taskOf(B1)), {...before[B1], parent_id: null}), 'bare parent: nothing changed besides');
  check(await until(() => seen.some(x => /1 subtask is now standalone/.test(x))) && !seen.some(x => /adopted|Don’t adopt/.test(x)), 'bare parent: the usual toast, no adoption: ' + seen.join(' | '));
  w.eval('(() => { S.multi.clear(); renderMultiBar(); render(); })()');

  // ---- 6. the task menu "Outdent" (a subtask of the top level becomes standalone)
  await reload(); await showKids();
  check(await until(() => row(S8)), 'the subtask "Write the speech" is shown');
  w.eval(`taskMenu(document.querySelector('#view .trow[data-id="${S8}"]'), ${S8})`);
  const more = await until(() => [...d.querySelectorAll('#pop button')].find(b => b.textContent.trim() === 'More…'));  // the rarer entries sit one level down
  if (more) click(w, more);
  const outd = await until(() => [...d.querySelectorAll('#pop button')].find(b => b.textContent.trim() === 'Outdent'));
  check(outd, 'the task menu offers "Outdent"');
  if (outd) click(w, outd);
  check(await until(async () => !(await taskOf(S8)).parent_id), 'Outdent: "Write the speech" is standalone');
  const s8 = pick(await taskOf(S8));
  check(s8.due === DUE && s8.due_time === TIME && s8.priority === 5 && s8.tags === '' && s8.assignee_id === null, 'Outdent: date, time and priority adopted, no tags / assignee ' + JSON.stringify(s8));
  check(await until(() => /Date and priority of “Trade fair” adopted/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'Outdent: the toast with "Don’t adopt": ' + toastText(d));
  check(await undoToast(w, /adopted/), 'Outdent: "Don’t adopt" tapped');
  check(await until(async () => { const x = pick(await taskOf(S8)); return !x.due && !x.priority && !x.parent_id; }), 'Outdent: Don’t adopt empties them again, standalone');

  // ---- 7. onto a project of the sidebar (one write with the move)
  await reload(); await showKids();
  check(await until(() => row(S4)), 'the subtask "Plan travel" is shown');
  const side = d.querySelector(`#side .srow[data-drop="l:${P2}"]`);
  check(side, 'the sidebar shows the project "Backlog"');
  if (side) {
    dnd(w, row(S4), 'dragstart'); dnd(w, side, 'dragover'); dnd(w, side, 'drop'); dnd(w, row(S4), 'dragend');
    check(await until(async () => { const x = await taskOf(S4); return !x.parent_id && x.list_id === P2; }), 'sidebar: "Plan travel" is standalone in "Backlog"');
    const s4 = pick(await taskOf(S4));
    check(s4.due === DUE && s4.priority === 5, 'sidebar: date and priority adopted ' + JSON.stringify(s4));
    check(await until(() => /Standalone in Backlog/.test(toastText(d)) && /adopted/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'sidebar: one toast names the move and the adoption: ' + toastText(d));
    check(await undoToast(w, /adopted/), 'sidebar: "Don’t adopt" tapped');
    check(await until(async () => { const x = await taskOf(S4); return !x.due && !x.priority && !x.parent_id && x.list_id === P2; }), 'sidebar: Don’t adopt keeps the move, empties the fields');
  }
  check(errs.length === 0, 'no script errors (list): ' + errs.join(' | '));
  w.close();

  // ---- 8. the board (kanban): a subtask dropped onto a column
  const K = (await call('POST', '/api/lists', {name: 'Booth board', kind: 'project'})).id;
  await call('PATCH', `/api/lists/${K}`, {view: 'kanban'});
  const KD = (await call('POST', '/api/sections', {name: 'Doing', list_id: K})).id;
  const KP = (await call('POST', '/api/tasks', {title: 'Booth build', list_id: K, section_id: KD, due: DUE, priority: 3})).id;
  const KS = (await call('POST', '/api/tasks', {title: 'Carry the panels', list_id: K, section_id: KD, parent_id: KP})).id;
  w = await boot({user: 'alice', hash: 'l/' + K}); d = w.document;
  const col = sid => d.querySelector(`#view .kcol[data-kcol="${sid}"]`);
  check(await until(() => col(KD)), 'the board renders');
  w.eval(`dropTask(${KS}, document.querySelector('#view .kcol[data-kcol="${KD}"]'), 10)`);
  check(await until(async () => !(await taskOf(KS)).parent_id), 'board: "Carry the panels" is standalone');
  const ks = pick(await taskOf(KS));
  check(ks.due === DUE && !ks.due_time && ks.priority === 3, 'board: date (no time: the parent has none) and priority adopted ' + JSON.stringify(ks));
  check(await until(() => /Subtask is now standalone/.test(toastText(d)) && /adopted/.test(toastText(d)) && toastBtn(d) === 'Don’t adopt'), 'board: the toast with "Don’t adopt": ' + toastText(d));
  check(await undoToast(w, /adopted/), 'board: "Don’t adopt" tapped');
  check(await until(async () => { const x = await taskOf(KS); return !x.due && !x.priority && !x.parent_id; }), 'board: Don’t adopt empties them, standalone');
  check(errs.length === 0, 'no script errors (board): ' + errs.join(' | '));
  w.close();

  // ---- 9. a person without an organisation: the same in the own private project
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.id, 'the person without an organisation is created');
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, CF);
  check(!((await st(CF)).me.workspaces || []).length, 'frida is in no organisation');
  const FL = (await call('POST', '/api/lists', {name: 'Studio', kind: 'project'}, CF)).id;
  const FP = (await call('POST', '/api/tasks', {title: 'Portfolio', list_id: FL, due: DUE, priority: 1}, CF)).id;
  const FS = (await call('POST', '/api/tasks', {title: 'Pick the photos', list_id: FL, parent_id: FP}, CF)).id;
  w = await boot({user: 'frida', hash: 'l/' + FL}); d = w.document;
  await until(() => d.querySelector(`#view .trow[data-id="${FP}"]`));
  unfold(w, FP);
  check(await until(() => d.querySelector(`#view .trow[data-id="${FS}"]`)), 'frida: the subtask is shown');
  check(await outMenu(w, FS), 'frida: "Out of the parent task" is offered');
  check(await until(async () => { const x = await taskOf(FS, CF); return !x.parent_id && x.due === DUE && x.priority === 1; }), 'frida: standalone, date and priority adopted');
  check(await undoToast(w, /adopted/), 'frida: "Don’t adopt" tapped');
  check(await until(async () => { const x = await taskOf(FS, CF); return !x.parent_id && !x.due && !x.priority; }), 'frida: Don’t adopt empties them');
  check(errs.length === 0, 'no script errors (frida): ' + errs.join(' | '));
  w.close();

  console.log(`p21271_c_detach_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21271_c_detach_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
