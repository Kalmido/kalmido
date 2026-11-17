// 2.1292.0 UI test, part C (#6124): contacts delete like tasks - no question, Undo in the toast, Ctrl+Z, "Recent steps"; the
// kalmido-suite: fresh
// glossary's words ("Move to the trash" in the card's menu, the selection bar and the address book's menu). jsdom, fresh
// container, invented names only (built anew on job/4600's p21176_b_contacts_undo_ui.js):
//  - the card's "..." menu says "Move to the trash" (no "Delete"); a click asks nothing, the contact leaves the list, the toast
//    names it and offers Undo; Undo brings it back into the list
//  - two ticked contacts: the selection bar's "Move to the trash" asks nothing, the toast names the count, Undo brings both back
//  - Ctrl+Z after a delete brings the contact back; the page "Recent steps" (#steps) lists the delete with its name
//  - an address book "Move to the trash…": still one question (all its contacts go along), then the toast with Undo; Undo
//    brings the book and its contacts back
//  - a person without an organisation (private address book, freelancer parity): delete + Undo the same way
// freelancer-matrix: contacts (frida has no organisation)
// The waits are on states (rows, the server, the toast), never on a fixed time.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, sleep, undoToast, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => until0(fn, {timeout: ms || 15000, step: 100});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const FEAT = 'comments,contacts';
const rowNames = d => [...d.querySelectorAll('#view .ctlist .ctrow .ctn b')].map(b => b.textContent);
const live = async (ck, q) => ((await call(ck, 'GET', '/api/contacts?q=' + encodeURIComponent(q))).items || []).length;
const toastText = d => { const t = d.querySelector('#toast'); return t && !t.classList.contains('hidden') ? t.textContent : ''; };
const menuItems = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')];
const contact = (ck, book, given, family) => call(ck, 'POST', '/api/contacts', {book_id: book, given, family, fn: `${given} ${family}`});
// the card of a contact, its "..." menu, "Move to the trash"; the question would show as window.confirm (counted in w.__asked)
async function trashFromCard(w, d, id, name, tag) {
  w.eval(`go('contacts/${id}')`);
  check(await until(() => w.eval('CT.card?.id') === id && d.querySelector('#view [data-ct="cmenu"]')), `${tag}: the card of ${name} shows`);
  d.querySelector('#view [data-ct="cmenu"]').click();
  const its = await until(() => { const x = menuItems(d); return x.length && x; });
  const lab = (its || []).map(x => x.textContent.trim());
  check(lab.includes('Move to the trash') && !lab.includes('Delete'), `${tag}: the card's menu says "Move to the trash" ${lab}`);
  its.find(x => x.textContent.trim() === 'Move to the trash').click();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const BK = (await call(CA, 'POST', '/api/books', {name: 'People', org_id: null})).id;
  const ADA = (await contact(CA, BK, 'Ada', 'Lovelace')).id, ALAN = (await contact(CA, BK, 'Alan', 'Turing')).id;
  await contact(CA, BK, 'Grace', 'Hopper'); await contact(CA, BK, 'Linus', 'Example');
  check(BK && ADA && ALAN, 'an address book with four contacts');

  let w = await boot({user: 'alice', hash: 'contacts'}), d = w.document;
  w.__asked = 0; w.confirm = () => { w.__asked++; return true; };
  check(await until(() => rowNames(d).length === 4), 'the four contacts show ' + rowNames(d));

  // ================= one contact: no question, the toast with Undo, Undo brings it back
  await trashFromCard(w, d, ADA, 'Ada', 'one');
  check(await until(() => !rowNames(d).includes('Ada Lovelace')), 'one: Ada leaves the list at once');
  check(await until(() => /“Ada Lovelace” moved to the trash/.test(toastText(d)) && d.querySelector('#toast button:not(.tx)')), 'one: the toast names her and offers Undo: ' + toastText(d));
  check(await until(async () => !(await live(CA, 'Lovelace'))), 'one: in the trash on the server');
  check(w.__asked === 0 && !d.querySelector('.modal'), 'one: no question');
  check(await undoToast(w, /Ada Lovelace/), 'one: Undo clicked');
  check(await until(async () => (await live(CA, 'Lovelace')) === 1), 'one: back on the server');
  check(await until(() => rowNames(d).includes('Ada Lovelace')), 'one: Undo shows her in the list again ' + rowNames(d));

  // ================= Ctrl+Z after a delete brings it back; "Recent steps" lists the delete
  await trashFromCard(w, d, ALAN, 'Alan', 'ctrl+z');
  check(await until(() => !rowNames(d).includes('Alan Turing')) && await until(async () => !(await live(CA, 'Turing'))), 'ctrl+z: Alan is in the trash');
  w.eval(`go('steps')`);
  check(await until(() => [...d.querySelectorAll('#view .ulbody .ulrow')].some(r => /Alan Turing/.test(r.textContent))),
    '"Recent steps" lists the delete of Alan: ' + [...d.querySelectorAll('#view .ulbody .ulrow')].slice(0, 3).map(r => r.textContent).join(' | '));
  w.eval(`go('contacts')`);
  await until(() => rowNames(d).length === 3);
  d.activeElement?.blur?.();
  d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true}));
  check(await until(async () => (await live(CA, 'Turing')) === 1), 'ctrl+z: Alan is back on the server');
  check(await until(() => rowNames(d).includes('Alan Turing')), 'ctrl+z: Alan shows in the list again ' + rowNames(d));

  // ================= two ticked: the selection bar's "Move to the trash", no question, Undo brings both back
  await until(() => rowNames(d).length === 4);
  d.querySelector('[data-ct="pick"]').click();
  await until(() => d.querySelector('#ct-sbar'));
  const row = n => [...d.querySelectorAll('#view .ctrow')].find(x => x.textContent.includes(n));
  row('Grace Hopper').click(); row('Linus Example').click();
  check(await until(() => w.eval('CT.pick?.size') === 2), 'many: two ticked');
  const del = d.querySelector('[data-ctb="del"]');
  check(/Move to the trash/.test(del?.textContent || del?.getAttribute('aria-label') || del?.title || ''), 'many: the bar says "Move to the trash"');
  del.click();
  check(await until(() => /2 contacts moved to the trash/.test(toastText(d))), 'many: the toast names the count: ' + toastText(d));
  check(await until(() => !rowNames(d).includes('Grace Hopper') && !rowNames(d).includes('Linus Example')), 'many: both leave the list');
  check(w.__asked === 0, 'many: no question');
  check(await undoToast(w, /2 contacts moved to the trash/), 'many: Undo clicked');
  check(await until(async () => (await live(CA, 'Hopper')) === 1 && (await live(CA, 'Example')) === 1), 'many: both back on the server');
  check(await until(() => rowNames(d).includes('Grace Hopper') && rowNames(d).includes('Linus Example')), 'many: both show again ' + rowNames(d));

  // ================= an address book: "Move to the trash…" asks once, then Undo brings it back with its contacts
  const CLUB = (await call(CA, 'POST', '/api/books', {name: 'Club', org_id: null})).id;
  await contact(CA, CLUB, 'Carl', 'Club');
  await w.eval('load()'); w.eval('ctLoad()');
  check(await until(() => rowNames(d).includes('Carl Club')), 'book: the contact of Club shows ' + rowNames(d));
  w.__asked = 0;
  d.querySelector('#view [data-ct="menu"]').click();
  const ab = await until(() => menuItems(d).find(x => x.textContent.trim() === 'Address books…')); ab.click();
  const bm = await until(() => d.querySelector(`.modal [data-cbmenu="${CLUB}"]`)); bm.click();
  const bl = await until(() => { const x = menuItems(d); return x.length && x; });
  const blab = (bl || []).map(x => x.textContent.trim());
  check(blab.includes('Move to the trash…') && !blab.includes('Delete…'), 'book: its menu says "Move to the trash…" ' + blab);
  bl.find(x => x.textContent.trim() === 'Move to the trash…').click();
  check(await until(async () => !((await call(CA, 'GET', '/api/books')).items || []).some(b => b.id === CLUB)), 'book: in the trash on the server');
  check(w.__asked === 1, 'book: one question (all its contacts go along) ' + w.__asked);
  check(await undoToast(w, /“Club” moved to the trash/), 'book: the toast with Undo');
  check(await until(async () => ((await call(CA, 'GET', '/api/books')).items || []).some(b => b.id === CLUB) && (await live(CA, 'Club')) === 1), 'book: Undo brings it back with its contact');
  d.querySelector('.modal [data-cb="close"]')?.click();
  check(await until(() => rowNames(d).includes('Carl Club')), 'book: its contact shows again ' + rowNames(d));
  w.close();

  // ================= a person without an organisation: her private address book, the same way
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  const FB = (await call(CF, 'POST', '/api/books', {name: 'Clients', org_id: null})).id;
  const KAT = (await contact(CF, FB, 'Kat', 'Sample')).id;
  w = await boot({user: 'frida', hash: 'contacts'}); d = w.document;
  w.__asked = 0; w.confirm = () => { w.__asked++; return true; };
  check(await until(() => rowNames(d).includes('Kat Sample')), 'freelancer: her contact shows');
  await trashFromCard(w, d, KAT, 'Kat', 'freelancer');
  check(await until(() => !rowNames(d).includes('Kat Sample')) && await until(async () => !(await live(CF, 'Sample'))), 'freelancer: Kat is in the trash');
  check(w.__asked === 0, 'freelancer: no question');
  check(await undoToast(w, /“Kat Sample” moved to the trash/), 'freelancer: the toast with Undo');
  check(await until(async () => (await live(CF, 'Sample')) === 1) && await until(() => rowNames(d).includes('Kat Sample')), 'freelancer: Undo brings Kat back into the list');
  w.close();

  console.log(`p21292_c_contacts_undo_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
