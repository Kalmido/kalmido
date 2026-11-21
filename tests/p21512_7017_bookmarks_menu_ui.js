// kalmido-suite: fresh
// #7017 (audit #5248 D13) UI test: the "…" of a bookmark is a real menu (was the dialog "Details"). Own
// container (start.sh), jsdom, invented data. frida has no organisation (freelancer: the same ways).
// - the "…" of a card opens a menu: Edit, Mark read, Archive, Reload preview, Delete (apart, the last)
// - Edit opens the dialog (in), Escape / its X closes it (back); Archive from the menu archives it (one Undo step)
// - Delete from the menu takes it out, Undo brings it back; a right click on the card opens the same menu
// freelancer-matrix: reading - frida has no organisation.
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
const items = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"] .ml')].map(x => x.textContent.trim());
const pick = (d, label) => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].find(b => b.querySelector('.ml')?.textContent.trim() === label);
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,reading', workspace: 'private'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const BM = (await call(CF, 'POST', '/api/bookmarks', {url: 'https://example.com/lens', title: 'Lens guide'})).bookmark?.id;
  check(BM, 'setup: a bookmark');
  const bm = async () => call(CF, 'GET', `/api/bookmarks/${BM}`);
  await call(CF, 'PATCH', `/api/bookmarks/${BM}`, {state: 'unread'});

  const w = await boot({user: 'frida', hash: 'bookmarks'}), d = w.document;
  const card = () => d.querySelector(`#view [data-id="${BM}"].bmcard, #view [data-id="${BM}"].bmrow`);
  check(await until(() => card()), 'the bookmark is shown');
  const dots = () => card()?.querySelector('[data-rowmenu]');
  check(dots() && dots().getAttribute('aria-haspopup') === 'menu' && /^More: Lens guide$/.test(dots().getAttribute('aria-label') || ''), '#7017 D13: the "…" says More and opens a menu (was "Details")');
  click(w, dots());
  await until(() => items(d).length);
  const m = items(d);
  check(['Edit', 'Mark read', 'Archive', 'Reload preview', 'Delete'].every(x => m.includes(x)) && m[m.length - 1] === 'Delete', '#7017 D13: the menu of the bookmark ' + JSON.stringify(m));
  check(!d.querySelector('.bmdlg'), '... and no dialog');
  // in / back: Edit opens the dialog, its X closes it
  pick(d, 'Edit').click();
  const dlg = await until(() => d.querySelector('.modal.bmdlg #bmd-title') && d.querySelector('.modal.bmdlg'));
  check(dlg && d.querySelector('#bmd-title').value === 'Lens guide', '#7017 D13: Edit opens the dialog with the bookmark');
  click(w, dlg.querySelector('[data-m="close"]'));
  check(await until(() => !d.querySelector('.modal.bmdlg')), '... its X closes it');
  // on: Archive from the menu, one Undo step
  click(w, dots());
  await until(() => pick(d, 'Archive'));
  pick(d, 'Archive').click();
  check(await until(async () => (await bm()).state === 'archived'), '#7017 D13: Archive from the menu archives it (server)');
  await w.eval('histStep("undo")');
  check(await until(async () => (await bm()).state !== 'archived'), 'Undo: no longer archived');
  // a right click on the card opens the same menu; Delete, then Undo
  await until(() => card());
  card().dispatchEvent(new w.MouseEvent('contextmenu', {bubbles: true, cancelable: true, button: 2, clientX: 10, clientY: 10}));
  check(await until(() => pick(d, 'Delete')), '#7017 D13: a right click opens the same menu');
  pick(d, 'Delete').click();
  check(await until(async () => (await bm()).http === 404) && await until(() => !card()), '#7017 D13: Delete from the menu takes it out');
  await w.eval('histStep("undo")');
  check(await until(async () => (await bm()).http === 200), 'Undo: it is back');
  w.close();

  console.log(`p21512_7017_bookmarks_menu_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
