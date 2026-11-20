// kalmido-suite: fresh
// 2.1474.0 (#6373) UI test: one verb for creating, the close cross of large dialogs. jsdom, invented data only:
// - a dialog that creates says "Create" (German "Anlegen"), editing says "Save": new client, new contact, new event, a
//   household deadline; the German text of "Create" is "Anlegen" (docs/dev/glossar.md)
// - the short new-client sheet: no resize grip for what waits folded under "More details" (dlg_grows)
// - a large dialog (more than half the window high) gets the close cross at the top right (dlgCross), it closes the dialog
//   (asking first with unsaved input, like Esc); a small question dialog (askConfirm) never; a dialog with its own cross keeps
//   its one; a small dialog none. jsdom has no layout: the height is set on the card (getBoundingClientRect), then dlgCross runs
// freelancer-matrix: clients, contacts, events (alice has no organisation: her private workspace)
const fs = require('fs');
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
const until = (fn, ms = 15000) => require('./boot').until(fn, {timeout: ms, step: 100});
const last = d => [...d.querySelectorAll('.modal')].pop();
const text = el => (el?.textContent || '').trim();
// the card of md as high as h (jsdom has no layout), the window 800 high
const tall = (w, md, h) => { const c = md.querySelector(':scope > .card'); c.getBoundingClientRect = () => ({x: 0, y: 0, top: 0, left: 0, width: 500, height: h, right: 500, bottom: h}); };

(async () => {
  await sleep(600);
  const de = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'static', 'i18n', 'de.json'), 'utf8'));
  check(de.Create === 'Anlegen', 'German "Create" is "Anlegen": ' + de.Create);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'contacts']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,contacts,office,clients,time,family'});
  const w = await boot({hash: 'today'}); const d = w.document;
  await until(() => typeof w.modal === 'function' && typeof w.dlgCross === 'function' && w.S?.me);
  await w.eval(`Promise.all(['clientdlg', 'contacts', 'family'].map(m => loadModule(m)))`);

  // ---- create = "Create", edit = "Save"
  w.eval('clientModal(null, {org_id: null})');
  let md = await until(() => d.querySelector('.modal.cldlg'));
  check(text(md?.querySelector('[data-m="save"]')) === 'Create', 'new client: "Create" (was "Add"): ' + text(md?.querySelector('[data-m="save"]')));
  check(w.eval(`dlg_grows(document.querySelector('.modal.cldlg > .card'))`) === false, 'the short new-client sheet: no grip for the folded "More details"');
  md.querySelector('details#cl-more').open = true;
  check(w.eval(`dlg_grows(document.querySelector('.modal.cldlg > .card'))`) === true, 'unfolded, its note can grow: the grip rule as everywhere');
  md.remove();
  w.eval('ctEditor(null)');
  md = await until(() => d.querySelector('.modal [data-ctm2="save"]') && last(d));
  check(text(md?.querySelector('[data-ctm2="save"]')) === 'Create', 'new contact: "Create" (was "Save"): ' + text(md?.querySelector('[data-ctm2="save"]')));
  md?.remove();
  w.eval('evEditor({})');
  md = await until(() => d.querySelector('.modal [data-evm="save"]') && last(d));
  check(text(md?.querySelector('[data-evm="save"]')) === 'Create', 'new event: "Create" (was "Save"): ' + text(md?.querySelector('[data-evm="save"]')));
  // the event editor draws its own cross: a large one keeps exactly one
  tall(w, md, 700); w.eval('dlgCross([...document.querySelectorAll(".modal")].pop(), true)');
  check([...md.querySelectorAll('button')].filter(b => b.getAttribute('aria-label') === 'Close' && !b.closest('.foot')).length === 1 && !md.querySelector('.dlgx'),
    'a dialog with its own cross keeps its one');
  md.remove();
  w.eval('dlModal()');
  md = await until(() => d.querySelector('.modal #dl-err') && last(d));
  check(text(md?.querySelector('[data-m="save"]')) === 'Create', 'household deadline: "Create" (was "Add")');
  md?.remove();

  // ---- the close cross
  w.eval(`window.__big = modal('<h3>Big one</h3><div class="row"><input id="big-in"></div><div class="foot"><span class="spacer"></span><button class="btn pri" data-m="close">Done</button></div>')`);
  md = w.__big; tall(w, md, 700); w.eval('dlgCross(window.__big, true)');
  const x = md.querySelector(':scope > .card > .dlgx');
  check(x && x.getAttribute('aria-label') === 'Close' && md.querySelector('.card').classList.contains('has-dlgx'), 'a large dialog gets the close cross');
  check(x && md.querySelector('.card').lastElementChild === x, 'the cross is last in the Tab order (the fields come first)');
  w.eval('dlgCross(window.__big, true)');
  check(md.querySelectorAll('.dlgx').length === 1, 'looked at again: still one cross');
  x?.click();
  check(await until(() => !md.isConnected), 'the cross closes the dialog');
  // with unsaved input it asks first, like Esc
  w.eval(`window.__g = modal('<h3>Guarded</h3><input id="gd-in"><div class="foot"></div>'); modalGuard(window.__g, () => !!document.querySelector('#gd-in').value)`);
  md = w.__g; md.querySelector('#gd-in').value = 'typed'; tall(w, md, 700); w.eval('dlgCross(window.__g, true)');
  md.querySelector('.dlgx').click();
  const ask = await until(() => d.querySelector('.modal.cdlg'));
  check(ask && /Discard changes/.test(ask.textContent) && md.isConnected, 'unsaved input: the cross asks "Discard changes?" first');
  ask?.querySelector('[data-cd="no"]')?.click();
  await until(() => !d.querySelector('.modal.cdlg'));
  check(md.isConnected, '"Keep editing": the dialog stays');
  md.remove();
  // a small dialog: none; a question dialog: never, also when it is high
  w.eval(`window.__s = modal('<h3>Small</h3><div class="foot"></div>')`);
  md = w.__s; tall(w, md, 120); w.eval('dlgCross(window.__s, true)');
  check(!md.querySelector('.dlgx'), 'a small dialog has no cross');
  md.remove();
  w.eval(`window.__q = askConfirm('Remove it?', 'A question', {ok: 'Remove', danger: true})`);
  md = await until(() => d.querySelector('.modal.cdlg'));
  tall(w, md, 700); w.eval('dlgCross(document.querySelector(".modal.cdlg"), true)');
  check(md && !md.querySelector('.dlgx'), 'a question dialog never has the cross');
  md?.querySelector('[data-cd="no"]')?.click();
  check(await w.__q === false, 'the question still answers (Cancel = no)');
  w.close();
  console.log(`p21474_b_dialogs_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
