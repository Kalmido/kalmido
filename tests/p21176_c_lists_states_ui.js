// 2.1176.0 UI test, part C (#6139 lists: loading, error and empty leftovers; #6136 rest: the reader's task menu, the folder's
// kalmido-suite: fresh
// Share dialog for who does not own it, the words of the read hints). jsdom, own container (start.sh). Invented data only.
// P21176C_NOSTART=1 = the container runs.
// freelancer-matrix: n/a (no new route; alice has no organisation, every check of hers runs without one - the invitation of
// her private project included)
// - #6139: a refused write of the lists names what was not saved (a section, a task's move through the outbox), the server's
//   text only in brackets; the open invitations and the folder's people: a failed load shows the error with "Try again"
//   (not an empty list = "not shared"), "Try again" shows them; removing an invitation offers Undo, Undo brings it back
//   (visible and on the server, same role); the board in lanes without tasks says "No tasks"; a sprint filter that hides
//   every task says a filter is active and "Show all" shows them again
// - #6136: a reader (role "view") gets the "…" menu in the task panel with Copy link, Print and History (no writing entries),
//   Print opens the task's printable page, History scrolls to it; in the folder's Share dialog she sees no share by address,
//   no invitations, no role choice and no remove
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21176C_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = async (fn, n = 75) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(200); } return (await fn()) || null; };  // null: a failed wait never crashes x?.click()
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  check(await until(async () => (await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})}).catch(() => null))?.status < 500), 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: 'kanban,collab,comments'});
  await call(CA, 'POST', '/api/users', {username: 'dora', display_name: 'Dora', password: 'password123', email: 'dora@example.com'});
  const CD = await login('dora'); await call(CD, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'kanban,collab,comments'});
  const me = async ck => (await call(ck, 'GET', '/api/state')).me;
  const [UA, UD] = [await me(CA), await me(CD)];
  check(!(UA.workspaces || []).length, 'alice: no organisation (a person without an organisation)');
  const P = (await call(CA, 'POST', '/api/lists', {name: 'Garden', kind: 'project', folder: 'Clients'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Water the roses', list_id: P, content: 'Twice a week'})).id;
  await call(CA, 'POST', '/api/tasks', {title: 'Buy mulch', list_id: P, parent_id: T});
  const SID = (await call(CA, 'POST', '/api/sections', {list_id: P, name: 'Beds'})).id;
  const fs = await call(CA, 'PUT', '/api/folders/people', {folder: 'Clients', user_id: UD.id, role: 'view'});
  const inv = await call(CA, 'PUT', `/api/lists/${P}/members`, {email: 'nobody@example.com', role: 'edit'});
  const openRows = async () => (await call(CA, 'GET', `/api/addr-shares?kind=list&ref=${P}`)).open || [];
  check(P && T && SID && fs.status === 200 && inv.status === 200 && (await openRows()).some(x => x.email === 'nobody@example.com'), 'set-up: a project in a folder shared with dora (view), a task, a section, an open invitation');
  const BOARD = (await call(CA, 'POST', '/api/lists', {name: 'Orchard', kind: 'project'})).id;
  await call(CA, 'PATCH', `/api/lists/${BOARD}`, {view: 'kanban'});
  const SPR = (await call(CA, 'POST', '/api/lists', {name: 'Vineyard', kind: 'project'})).id;
  await call(CA, 'POST', '/api/tasks', {title: 'Prune the vines', list_id: SPR});
  await call(CA, 'PATCH', `/api/lists/${SPR}`, {view: 'kanban'});
  const sp = await call(CA, 'PUT', `/api/lists/${SPR}/sprint-settings`, {on: true});
  check(BOARD && SPR && sp.status === 200, 'set-up: an empty board, a board with sprints on');

  // ================= #6139 what was not saved
  let w = await boot({user: 'alice', hash: `l/${P}`}), d = w.document;
  await until(() => w.eval(`!!listById(${P})`));
  check(w.eval(`apiWhat('PATCH', '/api/tasks/5', {section_id: 2})`) === 'The move was not saved' && w.eval(`apiWhat('PATCH', '/api/tasks/5', {title: 'x'})`) === 'The change to the task was not saved'
    && w.eval(`apiWhat('PATCH', '/api/sections/3', {name: 'x'})`) === 'The section was not saved' && w.eval(`apiWhat('POST', '/api/lists/3/sections/order', {})`) === 'The order of the sections was not saved'
    && w.eval(`apiWhat('DELETE', '/api/addr-shares/4')`) === 'The invitation was not removed' && w.eval(`apiWhat('GET', '/api/lists/3/members')`) === '', '#6139: apiWhat names the list writes (a read names nothing)');
  const toastT = () => txt(d.querySelector('#toast'));
  // a section's rename refused by the server: the sentence first, the server's words in brackets
  w.eval(`window.__rf = rawFetch; rawFetch = (m, u, b, ...r) => m === 'PATCH' && /^\\/api\\/sections\\//.test(u) ? Promise.reject(Object.assign(new Error('boom-sec'), {status: 422})) : window.__rf(m, u, b, ...r)`);
  w.eval(`api('PATCH', '/api/sections/${SID}', {name: 'Hedges'}).catch(() => 0)`);
  check(await until(() => /The section was not saved \(boom-sec\)/.test(toastT())), '#6139: a refused section write says what was not saved: ' + toastT());
  // a task's move sent online through the outbox and refused: the same sentence (was the server's raw text)
  w.eval(`rawFetch = (m, u, b, ...r) => m === 'PATCH' && u === '/api/tasks/${T}' ? Promise.reject(Object.assign(new Error('boom-move'), {status: 422})) : window.__rf(m, u, b, ...r)`);
  w.eval(`patchTask(${T}, {section_id: ${SID}}).catch(() => 0)`);
  check(await until(() => /The move was not saved \(boom-move\)/.test(toastT())), '#6139: a refused move of the outbox says what was not saved: ' + toastT());
  w.eval(`rawFetch = window.__rf`);
  check(await until(async () => !(await call(CA, 'GET', `/api/tasks/${T}`)).section_id), '#6139: ... and the move did not happen on the server');

  // ================= #6139 the open invitations: load error with "Try again", Undo of a removed one (alice, no organisation)
  w.eval(`S.peopleVis = 'contacts'; shareModal(${P})`);
  let row = await until(() => [...d.querySelectorAll('#sh-open .mrow')].find(r => /nobody@example\.com/.test(txt(r))));
  check(row && d.querySelector('#sh-email'), '#6139: the owner sees the invitation and the share by address');
  // the list's load fails: the error and "Try again", not an empty part
  const box = 'document.querySelector("#sh-open")';
  w.eval(`rawFetch = (m, u, ...r) => m === 'GET' && /^\\/api\\/addr-shares/.test(u) ? Promise.reject(new Error('boom-ads')) : window.__rf(m, u, ...r); adsFill(${box}, 'kind=list&ref=${P}')`);
  let er = await until(() => d.querySelector('#sh-open .eerr'));
  check(er && /The invitations could not be loaded/.test(txt(er)) && er.querySelector('[data-esretry]') && !/nobody@example/.test(txt(d.querySelector('#sh-open'))), '#6139: a failed load of the invitations says so with "Try again": ' + txt(er));
  w.eval(`rawFetch = window.__rf`);
  er?.querySelector('[data-esretry]')?.click();
  row = await until(() => [...d.querySelectorAll('#sh-open .mrow')].find(r => /nobody@example\.com/.test(txt(r))));
  check(row && !d.querySelector('#sh-open .eerr'), '#6139: "Try again" shows the invitation');
  // remove it, then Undo through the toast: back in the dialog and on the server with its role
  row?.querySelector('[data-adsrm]')?.click();
  check(await until(async () => !d.querySelector('#sh-open .mrow') && !(await openRows()).length), '#6139: the invitation is removed (dialog and server)');
  const ub = await until(() => /Invitation removed/.test(toastT()) && [...d.querySelectorAll('#toast button')].find(b => /Undo/.test(txt(b))));
  check(ub, '#6139: "Invitation removed" offers Undo: ' + toastT());
  ub?.click();
  row = await until(() => [...d.querySelectorAll('#sh-open .mrow')].find(r => /nobody@example\.com/.test(txt(r))));
  const back = await until(async () => (await openRows()).find(x => x.email === 'nobody@example.com'));
  check(row && back && back.role === 'edit', '#6139: Undo brings the invitation back, visible and on the server with its role: ' + JSON.stringify(back || null));
  d.querySelectorAll('.modal').forEach(m => m.remove());

  // ================= #6139 the folder's people: a failed load is no "not shared"
  // (__usersDone: the accounts of the server (/api/users) have arrived - they draw the part again, the error has to stay)
  w.eval(`window.__api0 = api; window.__usersDone = 0; api = (m, u, b) => m === 'GET' && /^\\/api\\/folders\\/people/.test(u) ? Promise.reject(new Error('boom-fp')) : window.__api0(m, u, b).then(r => { if (/^\\/api\\/users/.test(u)) window.__usersDone = 1; return r; }); S.peopleVis = 'contacts'; folderShareModal('Clients')`);
  await until(() => w.eval('window.__usersDone') && d.querySelector('#fsh-members .eerr'));
  er = await until(() => d.querySelector('#fsh-members .eerr') && !d.querySelector('#fsh-members .eload') && d.querySelector('#fsh-members .eerr'));
  check(er && /The people could not be loaded/.test(txt(er)) && er.querySelector('[data-esretry]') && !d.querySelector('#fsh-members [data-uid]'), '#6139: the folder\'s people failed: the error with "Try again", no empty list: ' + txt(d.querySelector('#fsh-members')));
  w.eval(`api = window.__api0`);
  er?.querySelector('[data-esretry]')?.click();
  const dr = await until(() => d.querySelector(`#fsh-members .mrow[data-uid="${UD.id}"]`));
  check(dr && /Dora/.test(txt(dr)) && !d.querySelector('#fsh-members .eerr'), '#6139: "Try again" shows the people of the folder: ' + txt(dr));
  check(d.querySelector('#fsh-email') && d.querySelector(`#fsh-members [data-fprole="${UD.id}"]`) && d.querySelector(`#fsh-members [data-rm="${UD.id}"]`), '#6136: the owner of the folder\'s projects manages its people (address, role, remove)');
  d.querySelectorAll('.modal').forEach(m => m.remove());

  // ================= #6139 the board in lanes without tasks; a sprint filter that hides every task
  w.eval(`LS.set('swl', {${BOARD}: 'prio'}); go('l/${BOARD}')`);
  let ke = await until(() => d.querySelector('#view .kanban.swl') && d.querySelector('#view .kempty'));
  check(ke && /No tasks/.test(txt(ke)), '#6139: the board in lanes without tasks says so: ' + txt(ke));
  w.eval(`LS.set('swl', {}); LS.set('sprFlt', {${SPR}: 'cur'}); go('l/${SPR}')`);
  ke = await until(() => w.eval(`S.route.key === 'l:${SPR}'`) && d.querySelector('#view .kempty.efilt'));
  check(ke && /No tasks match the filter/.test(txt(ke)) && /A filter is active: Current sprint/.test(txt(ke)) && !/Prune the vines/.test(txt(d.querySelector('#view'))), '#6139: the sprint filter hides every task: says a filter is active: ' + txt(ke));
  ke?.querySelector('[data-spr="flt"]')?.click();
  check(await until(() => /Prune the vines/.test(txt(d.querySelector('#view .kanban'))) && !d.querySelector('#view .kempty')), '#6139: "Show all" shows the tasks again');
  w.close();

  // ================= #6136 the reader: the "…" menu with the read functions, no management in the folder's Share dialog
  w = await boot({user: 'dora', hash: `t/${T}`}); d = w.document;
  const mb = await until(() => d.querySelector('#detail .rotag') && d.querySelector('#detail .dtop [data-act="task-menu"]'));
  check(mb, '#6136: the reader\'s task panel has the "…" menu');
  mb?.click();
  const pop = await until(() => d.querySelector('#pop [data-act="tro-hist"]') && d.querySelector('#pop'));
  const items = [...(pop?.querySelectorAll('[role^="menuitem"]') || [])].map(txt);
  check(pop?.querySelector('[data-act="tro-link"]') && /Copy link/.test(txt(pop.querySelector('[data-act="tro-link"]'))) && /Print/.test(txt(pop.querySelector('[data-act="tro-print"]'))) && /History/.test(txt(pop.querySelector('[data-act="tro-hist"]'))),
    '#6136: the menu offers Copy link, Print and History: ' + items.join(' | '));
  check(!items.some(s => /Delete|Won’t do|Duplicate|Move to|Pin/.test(s)), '#6136: ... and no writing entry: ' + items.join(' | '));
  pop?.querySelector('[data-act="tro-print"]')?.click();
  const sheet = await until(() => d.querySelector('.tsheet .lextask'));
  check(sheet && txt(sheet.querySelector('h1')) === 'Water the roses' && /Twice a week/.test(txt(sheet)) && /Buy mulch/.test(txt(sheet)) && /Garden/.test(txt(sheet.querySelector('.tssub'))), '#6136: Print opens the task\'s page (title, project, description, subtasks): ' + txt(sheet).slice(0, 120));
  d.querySelector('.tsheet [data-ts="close"]')?.click();
  check(await until(() => !d.querySelector('.tsheet')), '#6136: the page closes');
  d.querySelector('#detail .dtop [data-act="task-menu"]')?.click();
  (await until(() => d.querySelector('#pop [data-act="tro-hist"]')))?.click();
  check(await until(() => d.querySelector('#detail #d-tl, #detail #d-hist[open]')), '#6136: History leads to the task\'s history in the panel');
  // the folder's Share dialog: the people only, nothing to manage (the server shares only one's own projects of a folder)
  const fold = w.eval(`listById(${P})?.folder || ''`) || 'Clients';
  w.eval(`S.peopleVis = 'contacts'; { const l = listById(${P}); if (l && !l.folder) l.folder = 'Clients'; } folderShareModal(${JSON.stringify(fold)})`);
  // the part is drawn once the folder's people have arrived (no "Loading…" left)
  const fm = await until(() => d.querySelector('#fsh-members .fshowner') && !d.querySelector('#fsh-members .eload') && d.querySelector('.fshmodal'));
  check(fm && w.eval(`!isOwner(listById(${P}))`), '#6136: the reader opens the folder\'s Share dialog');
  check(fm && !fm.querySelector('#fsh-email') && !fm.querySelector('#fsh-open') && !fm.querySelector('[data-fprole], [data-rm], #fp-user'), '#6136: no share by address, no invitations, no role choice / remove / add for who does not own it');
  d.querySelectorAll('.modal').forEach(m => m.remove());
  // the project's own Share dialog: no share by address for the reader either (dialogs.js canManage)
  w.eval(`S.peopleVis = 'contacts'; shareModal(${P})`);
  await until(() => d.querySelector('.shmodal #l-members .mrow'));
  check(!d.querySelector('#sh-email') && !d.querySelector('#sh-open'), '#6136: the project\'s Share dialog has no share by address for the reader');
  w.close();

  console.log(`p21176_c_lists_states_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
