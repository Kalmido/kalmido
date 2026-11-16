// 2.1292.0 UI test, part D (#6136 the reader of a list: the task menu with the read functions, the folder's Share dialog for
// kalmido-suite: fresh
// who does not own it; #6139 lists: loading, error and empty leftovers). jsdom, own container (start.sh). Invented data only.
// P21292D_NOSTART=1 / KMT_NOSTART=1 = the container runs.
// freelancer-matrix: lists (no new route; alice has no organisation, every check of hers runs without one - the invitation of
// her private project included)
// - #6136: a reader (role "view" through the folder) sees no write button in the panel's head and ONE read hint; the panel's
//   "…" menu offers Copy link, Print and History and no writing entry; Copy link gives the task's link, Print opens the
//   task's printable page (title, project, description, subtasks) that closes again, History leads to the task's history
//   in the panel; the list row's context menu is the same read menu. In the folder's Share dialog she sees the people with
//   their role as text: no share by address, no invitations, no role choice, no remove, no add; the owner keeps all of it.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21292D_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = async (fn, n = 75) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(200); } return (await fn()) || null; };  // null: a failed wait never crashes x?.click()
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const hints = d => d.querySelectorAll('.cwro').length;  // the core's ONE read hint (roHintHtml)

(async () => {
  check(await until(async () => (await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})}).catch(() => null))?.status < 500), 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: 'kanban,collab,comments'});
  await call(CA, 'POST', '/api/users', {username: 'dora', display_name: 'Dora', password: 'password123', email: 'dora@example.com'});
  const CD = await login('dora'); await call(CD, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'kanban,collab,comments'});
  const me = async ck => (await call(ck, 'GET', '/api/state')).me;
  const [UA, UD] = [await me(CA), await me(CD)];
  check(UA?.id && UD?.id && !(UA.workspaces || []).length, 'alice: no organisation (a person without an organisation)');
  const P = (await call(CA, 'POST', '/api/lists', {name: 'Garden', kind: 'project', folder: 'Clients'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Water the roses', list_id: P, content: 'Twice a week', due: '2030-05-04'})).id;
  await call(CA, 'POST', '/api/tasks', {title: 'Buy mulch', list_id: P, parent_id: T});
  const fs = await call(CA, 'PUT', '/api/folders/people', {folder: 'Clients', user_id: UD.id, role: 'view'});
  check(P && T && fs.status === 200, 'set-up: a project in a folder shared with dora (view), a task with a subtask');

  // ================= #6136 the reader: no write entry, one hint, the "…" menu with the read functions
  let w = await boot({user: 'dora', hash: `l/${P}`}), d = w.document;
  const row = await until(() => d.querySelector(`#view .trow[data-id="${T}"]`));
  check(row && w.eval(`!canEdit(taskById(${T}))`), '#6136: dora reads the project (role view)');
  w.eval(`openDetail(${T})`);
  const D = await until(() => d.querySelector('#detail #d-title')?.value === 'Water the roses' && d.querySelector('#detail'));
  const top = D?.querySelector('.dtop');
  check(top && !top.querySelector('button.chk, [data-act="date"], [data-act="due-q"], [data-act="pin"], [data-act="prio"], [data-act="timer-toggle"]') && !D.querySelector('.dtdone'),
    '#6136: no Complete / date / quick dates / pin / priority / timer button in the panel\'s head: ' + [...(top?.querySelectorAll('button') || [])].map(b => b.dataset.act || b.className).join(','));
  check(hints(d) === 1, `#6136: the read hint once with the panel beside the list (${hints(d)})`);
  const mb = top?.querySelector('[data-act="task-menu"]');
  check(mb && !mb.disabled, '#6136: the reader\'s task panel has the "…" menu');
  mb?.click();
  let pop = await until(() => d.querySelector('#pop [data-act="tro-hist"]') && d.querySelector('#pop'));
  const items = [...(pop?.querySelectorAll('[role^="menuitem"]') || [])].map(txt);
  check(pop && /Copy link/.test(txt(pop.querySelector('[data-act="tro-link"]'))) && /Print/.test(txt(pop.querySelector('[data-act="tro-print"]'))) && /History/.test(txt(pop.querySelector('[data-act="tro-hist"]'))),
    '#6136: the menu offers Copy link, Print and History: ' + items.join(' | '));
  check(items.length === 3 && !items.some(s => /Delete|Won’t do|Duplicate|Move|Pin|Lock|Select/.test(s)), '#6136: ... and no writing entry: ' + items.join(' | '));
  // Copy link: the task's link reaches the clipboard (jsdom: a stand-in), the toast says so
  w.eval(`window.__clip = ''; Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: async s => { window.__clip = s; }}})`);
  pop?.querySelector('[data-act="tro-link"]')?.click();
  check(await until(() => w.eval('window.__clip').endsWith(`#t/${T}`) && /copied/i.test(txt(d.querySelector('#toast')))), '#6136: Copy link copies the task\'s link: ' + w.eval('window.__clip'));
  // Print: the task's printable page
  d.querySelector('#detail .dtop [data-act="task-menu"]')?.click();
  (await until(() => d.querySelector('#pop [data-act="tro-print"]')))?.click();
  const sheet = await until(() => d.querySelector('.tsheet .lextask'));
  check(sheet && txt(sheet.querySelector('h1')) === 'Water the roses' && /Twice a week/.test(txt(sheet)) && /Buy mulch/.test(txt(sheet)) && /Garden/.test(txt(sheet.querySelector('.tssub'))),
    '#6136: Print opens the task\'s page (title, project, description, subtasks): ' + txt(sheet).slice(0, 160));
  w.eval(`window.__printed = 0; window.print = () => { window.__printed++; }`);
  d.querySelector('.tsheet [data-ts="print"]')?.click();
  check(w.eval('window.__printed') === 1, '#6136: the page\'s Print button prints');
  d.querySelector('.tsheet [data-ts="close"]')?.click();
  check(await until(() => !d.querySelector('.tsheet') && !d.body.classList.contains('tsprint')), '#6136: the page closes');
  // History: the panel's history (the comments with the changes of a shared list, or the folded History)
  w.eval(`window.__scrolled = ''; Element.prototype.scrollIntoView = function () { window.__scrolled = this.id; }`);
  d.querySelector('#detail .dtop [data-act="task-menu"]')?.click();
  (await until(() => d.querySelector('#pop [data-act="tro-hist"]')))?.click();
  check(await until(() => ['d-tl', 'd-hist'].includes(w.eval('window.__scrolled')) && d.querySelector('#detail #d-tl, #detail #d-hist[open]')), '#6136: History leads to the task\'s history in the panel: ' + w.eval('window.__scrolled'));
  // the list row's context menu: the same read menu, not a "read-only" message
  w.eval(`taskMenu(document.querySelector('#view .trow[data-id="${T}"]'), ${T}, {select: true})`);
  pop = await until(() => d.querySelector('#pop [data-act="tro-print"]') && d.querySelector('#pop'));
  check(pop && pop.querySelector('[data-act="tro-link"]') && !/Select|Delete/.test(txt(pop)), '#6136: the row\'s menu is the read menu too: ' + txt(pop));
  d.body.click();

  // ================= #6136 the folder's Share dialog: the people only for who does not own the folder's projects
  // (the shared project carries the folder of its owner for her, else as if it did: the dialog's rule is the point)
  const fold = w.eval(`listById(${P})?.folder || ''`) || 'Clients';
  w.eval(`S.peopleVis = 'contacts'; { const l = listById(${P}); if (l && !l.folder) l.folder = 'Clients'; } folderShareModal(${JSON.stringify(fold)})`);
  const fm = await until(() => d.querySelector('.fshmodal #fsh-members .fshowner') && !d.querySelector('#fsh-members .eload') && !/Loading/.test(txt(d.querySelector('#fsh-members'))) && d.querySelector('.fshmodal'));
  check(fm && w.eval(`!isOwner(listById(${P}))`), '#6136: the reader opens the folder\'s Share dialog');
  check(fm && !fm.querySelector('#fsh-email') && !fm.querySelector('#fsh-open') && !fm.querySelector('[data-fprole], [data-rm], #fp-user, [data-m="add"]'),
    '#6136: no share by address, no invitations, no role choice / remove / add for who does not own it');
  check(fm && /Only your own projects can be shared/.test(txt(fm)), '#6136: ... and says why');
  d.querySelectorAll('.modal').forEach(m => m.remove());
  w.close();

  // the owner keeps all of it
  w = await boot({user: 'alice', hash: `l/${P}`}); d = w.document;
  await until(() => w.eval(`!!listById(${P})`));
  w.eval(`S.peopleVis = 'contacts'; folderShareModal('Clients')`);
  const om = await until(() => d.querySelector(`.fshmodal #fsh-members [data-fprole="${UD.id}"]`) && d.querySelector('.fshmodal'));
  check(om && om.querySelector('#fsh-email') && om.querySelector('#fsh-open') && om.querySelector(`[data-rm="${UD.id}"]`), '#6136: the owner of the folder\'s projects manages its people (address, role, remove)');
  d.querySelectorAll('.modal').forEach(m => m.remove());
  // the owner's task menu stays the writing one
  w.eval(`openDetail(${T})`);
  (await until(() => d.querySelector('#detail .dtop [data-act="task-menu"]')))?.click();
  pop = await until(() => d.querySelector('#pop [role^="menuitem"]') && d.querySelector('#pop'));
  check(pop && !pop.querySelector('[data-act="tro-print"]') && /Delete|Duplicate/.test(txt(pop)), '#6136: the owner gets the writing task menu: ' + txt(pop).slice(0, 120));
  w.close();

  console.log(`p21292_d_lists_states_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
