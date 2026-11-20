// 2.1174.0 part B UI tests (#6123 menus, address books and import of the contacts; #6122 the area's rest of the write right),
// kalmido-suite: fresh
// own container (start.sh, mode workspaces), Firefox (the real layout: the menu's place is measured). Invented data only.
// - #6122 Bob may only read the address book Alice shares with him: "New contact" creates NO address book quietly - one
//   sentence with the button "Create your own address book" (Cancel: nothing created; the button: the book, then the editor);
//   the card's menu of a contact he may only read has no "Delete", of one he may change "Delete" as its last entry
// - #6123 Carol (no organisation: freelancer parity) with two address books: the contacts' "..." holds ONE "Import…" and ONE
//   "Export…"; Export asks for the book, then the format, and hands over the file; an import while a search is active ends with
//   "Show imported", which drops the search and shows the new contact; the CSV mapping guesses Work for a work column / a
//   filled company column (not every e-mail / address as Home)
// - #6123 Alice's "Address books" dialog: one sentence on books / folders / groups, the book symbol, "shared with ..." in a
//   second line that is fully visible; the book's "..." menu opens at its button (gap measured), also a menu too tall for
//   either side stays as near its button as the window allows (placePop: it used to jump to the window's top)
// P21174B_NOSTART=1 = the server already runs.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21174_b_contacts_ui', check, shots: 'P21174B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21174B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    const j = await r.json().catch(() => ({})); return {...j, http: r.status};
  }
};
const FEAT = 'comments,collab,contacts';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments', 'contacts']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me.id;
  const bob = await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.org'});
  await call(CA, 'POST', '/api/users', {username: 'carol', display_name: 'Carol Solo', password: 'password123', email: 'carol@example.org'});
  const CB = await login('bob'), CC = await login('carol');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await call(CC, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me})).id;
  check((await call(CA, 'PUT', `/api/orgs/${ORG}/members`, {email: 'bob@example.org'})).http === 200, 'Bob joins the organisation (Alice may share with him)');
  check(!((await call(CC, 'GET', '/api/state')).me.workspaces || []).length, 'P4: Carol has no organisation');
  // Alice: two books, both shared with Bob - "Team view" to read, "Team edit" (shared later) to change
  const BV = (await call(CA, 'POST', '/api/books', {name: 'Team view', org_id: null})).id, BE = (await call(CA, 'POST', '/api/books', {name: 'Team edit', org_id: null})).id;
  const VV = await call(CA, 'POST', '/api/contacts', {book_id: BV, given: 'Vera', family: 'Viewonly'}), EE = await call(CA, 'POST', '/api/contacts', {book_id: BE, given: 'Eddie', family: 'Editable'});
  check(VV.id > 0 && EE.id > 0, 'two contacts of Alice');
  check((await call(CA, 'PUT', `/api/books/${BV}/members`, {user_id: bob.id, role: 'view'})).http === 200, 'Alice shares "Team view" with Bob (view)');
  // Carol: two books of her own, a contact in each
  const BH = (await call(CC, 'POST', '/api/books', {name: 'Home book'})).id, BW = (await call(CC, 'POST', '/api/books', {name: 'Work book'})).id;
  check(BH > 0 && BW > 0, 'Carol: two address books');
  await call(CC, 'POST', '/api/contacts', {book_id: BW, given: 'Walter', family: 'Worker'});

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = async (ev, nav, u) => {
    await nav(B + 'static/icon.svg');
    await ev(`fetch('/api/auth/logout', {method: 'POST', headers: {'X-Requested-With': 'kalmido'}}).then(r => r.status).catch(() => 0)`);
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    const st = await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
    check(st === 200, u + ' signs in');
    await nav(B + '#contacts');
    check(await ready(ev, `typeof CT === 'object' && Array.isArray(CT.items) && CT.items.length > 0 && !!document.querySelector('#view [data-ct="menu"]')`, 80), u + ': the contacts view loads');
  };
  const click = (ev, sel) => ev(`(() => { const b = document.querySelector(${JSON.stringify(sel)}); if (!b) return 0; b.click(); return 1; })()`);
  const MI = `[...document.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')]`;
  const items = ev => ev(`${MI}.map(b => b.textContent.trim())`);
  const pick = (ev, label) => ev(`(() => { const b = ${MI}.find(x => x.textContent.trim() === ${JSON.stringify(label)}); if (!b) return 0; b.click(); return 1; })()`);
  const cardMenu = async (ev, id) => {
    await ev(`(closePop(), document.querySelectorAll('.modal').forEach(m => m.remove()), 1)`);
    await click(ev, `#view [data-ctopen="${id}"]`);
    check(await ready(ev, `CT.card?.id === ${id} && !!document.querySelector('#view [data-ct="cmenu"]')`), `the card of ${id} opens`);
    await click(ev, '#view [data-ct="cmenu"]');
    await ready(ev, `${MI}.length > 0`);
    return items(ev);
  };
  const bobBooks = async () => ((await call(CB, 'GET', '/api/books')).items || []).length;

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 800}});

    // ================= #6122 Bob: no quiet address book, Delete with the right that deletes
    await signIn(ev, nav, 'bob');
    check(await bobBooks() === 1, '#6122: Bob sees one address book (read only) ' + await bobBooks());
    await click(ev, '#view [data-ct="new"]');
    check(await ready(ev, `[...document.querySelectorAll('.modal')].some(m => /You cannot add contacts to any address book here/.test(m.textContent) && /Create your own address book/.test(m.querySelector('[data-cd="yes"]')?.textContent || ''))`),
      '#6122: "New contact" says it in one sentence with the button "Create your own address book"');
    check(await ev(`!document.querySelector('.modal.ctmodal')`), '#6122: ... and opens no editor yet');
    await shot('p21174b-own-book-ask.png');
    await click(ev, '.modal [data-cd="no"]');
    check(await ready(ev, `!document.querySelector('.modal')`), '#6122: Cancel closes it');
    check(await bobBooks() === 1, '#6122: Cancel created no address book');
    let mi = await cardMenu(ev, VV.id);
    check(mi.length > 0 && !mi.includes('Delete') && !mi.includes('Move to the trash'), '#6122: a contact Bob may only read: no "Move to the trash" in its menu ' + mi.join('|'));  // 2.1292.0 (#6124): "Move to the trash" (was Delete)
    await ev(`(closePop(), 1)`);
    await click(ev, '#view [data-ct="new"]');
    await ready(ev, `!!document.querySelector('.modal [data-cd="yes"]')`);
    await click(ev, '.modal [data-cd="yes"]');
    // (#7385): Bob (one organisation, Contacts on in Private and in Alpha) names the workspace in the required choice, as before: Alpha
    const WSQ = `document.querySelector('.cdlg input[name="wsp-ask"][value="org:${ORG}"]')`;
    check(await ready(ev, `!!${WSQ}`) && !await ev(`!!document.querySelector('.modal.ctmodal #ct-given')`),
          '#7385: one organisation under "All": the new address book asks for its workspace first (no editor yet)');
    await ev(`(() => { const q = ${WSQ}; q.checked = true; q.closest('form').querySelector('[data-cd="yes"]').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal.ctmodal #ct-given')`), '#6122: the button creates the book, then the editor opens');
    check(await bobBooks() === 2, '#6122: ... one address book of his own ' + await bobBooks());
    await ev(`(document.querySelectorAll('.modal').forEach(m => m.remove()), 1)`);
    check((await call(CA, 'PUT', `/api/books/${BE}/members`, {user_id: bob.id, role: 'edit'})).http === 200, 'Alice shares "Team edit" with Bob (edit)');
    await signIn(ev, nav, 'bob');
    mi = await cardMenu(ev, EE.id);
    check(mi[mi.length - 1] === 'Move to the trash', '#6122 #6123: a contact Bob may change: "Move to the trash" is the last entry ' + mi.join('|'));  // 2.1292.0 (#6124): was "Delete"
    mi = await cardMenu(ev, VV.id);
    check(!mi.includes('Delete') && !mi.includes('Move to the trash'), '#6122: the read-only one still has none ' + mi.join('|'));  // 2.1292.0 (#6124)
    await ev(`(closePop(), 1)`);

    // ================= #6123 Carol: one Import, one Export; Export asks book + format and hands over the file
    await signIn(ev, nav, 'carol');
    await click(ev, '#view [data-ct="menu"]');
    await ready(ev, `${MI}.length > 0`);
    mi = await items(ev);
    check(mi.filter(x => /^Import/.test(x)).length === 1 && mi.filter(x => /^Export/.test(x)).length === 1 && mi.includes('Import…') && mi.includes('Export…'),
      '#6123: two books, still ONE "Import…" and ONE "Export…" ' + mi.join('|'));
    check(!mi.some(x => /Home book|Work book|\(vCard\)|\(CSV\)/.test(x)), '#6123: no line per address book in the "..." menu');
    await shot('p21174b-head-menu.png');
    await pick(ev, 'Import…');
    await ready(ev, `${MI}.some(b => b.textContent.trim() === 'Home book')`);
    mi = await items(ev);
    check(mi.includes('Home book') && mi.includes('Work book'), '#6123: "Import…" asks into which address book ' + mi.join('|'));
    await ev(`(closePop(), 1)`);
    await ev(`(window.__exp = [], window.ct_expGo = u => window.__exp.push(u), 1)`);
    await click(ev, '#view [data-ct="menu"]');
    await ready(ev, `${MI}.length > 0`);
    await pick(ev, 'Export…');
    check(await ready(ev, `${MI}.some(b => b.textContent.trim() === 'Work book')`), '#6123: "Export…" asks for the address book ' + (await items(ev)).join('|'));
    await pick(ev, 'Work book');
    check(await ready(ev, `${MI}.some(b => b.textContent.trim() === 'vCard (.vcf)') && ${MI}.some(b => b.textContent.trim() === 'CSV (spreadsheet)')`), '#6123: ... then for the format ' + (await items(ev)).join('|'));
    await pick(ev, 'vCard (.vcf)');
    check(await ready(ev, `window.__exp.length === 1`), '#6123: the export starts');
    const exp = await ev(`window.__exp[0] || ''`);
    check(exp === `/api/books/${BW}/export.vcf`, '#6123: the vCard of "Work book" ' + exp);
    const file = await ev(`fetch(${JSON.stringify(exp)}).then(async r => [r.status, r.headers.get('content-disposition') || '', await r.text()].join('\\n'))`);
    check(/^200\n/.test(file) && /attachment/.test(file) && /BEGIN:VCARD/.test(file) && /Walter Worker/.test(file), '#6123: ... a file with the book\'s contact ' + file.slice(0, 120));

    // ================= #6123 an import while a search is active: "Show imported"
    await ev(`(() => { const i = document.querySelector('#ct-q'); i.value = 'zzznomatch'; i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    check(await ready(ev, `CT.q === 'zzznomatch' && !CT.loading && CT.items.length === 0`), '#6123: a search that matches nothing');
    await ev(`(ctImpRun(${BH}, new File(['BEGIN:VCARD\\r\\nVERSION:3.0\\r\\nUID:p21174b-nina\\r\\nFN:Nina Imported\\r\\nN:Imported;Nina;;;\\r\\nEND:VCARD\\r\\n'], 'nina.vcf', {type: 'text/vcard'}), null, true), 1)`);
    check(await ready(ev, `/Imported: 1 new/.test(document.querySelector('#ctimp .ctimp-t')?.textContent || '') && !!document.querySelector('#ctimp [data-ctimp="show"]')`),
      '#6123: the import ends with "Show imported" ' + await ev(`document.querySelector('#ctimp')?.textContent || ''`));
    check(await ev(`!document.querySelector('#view [data-ctopen]')`), '#6123: the new contact is hidden by the search before');
    await shot('p21174b-import-done.png');
    await click(ev, '#ctimp [data-ctimp="show"]');
    check(await ready(ev, `CT.q === '' && document.querySelector('#ct-q')?.value === '' && [...document.querySelectorAll('#view .ctrow')].some(b => /Nina Imported/.test(b.textContent))`),
      '#6123: "Show imported" drops the search and shows the new contact ' + await ev(`CT.q + '|' + [...document.querySelectorAll('#view .ctrow')].map(b => b.textContent.trim()).join(',')`));
    check(await ev(`!document.querySelector('#ctimp')`), '#6123: ... and closes the import message');

    // ================= #6123 the CSV mapping: Work for a work column / a filled company column
    await ev(`(ctx_csvMap(${BH}, new File(['Company;E-mail;Street\\r\\nACME;a@example.com;Way 1\\r\\nBeta;b@example.com;Way 2\\r\\n'], 'firm.csv', {type: 'text/csv'})), 1)`);
    check(await ready(ev, `document.querySelectorAll('.modal .ctxmap select').length === 3`), '#6123: the CSV mapping opens');
    let g = await ev(`[...document.querySelectorAll('.modal .ctxmap select')].map(s => s.value).join(',')`);
    check(g === 'org,email:work,adr:work:street', '#6123: a filled company column: e-mail and address as Work ' + g);
    await ev(`(document.querySelectorAll('.modal').forEach(m => m.remove()), 1)`);
    await ev(`(ctx_csvMap(${BH}, new File(['First name;E-Mail Arbeit;E-Mail privat;E-mail\\r\\nUla;u@example.com;u@example.org;u@example.net\\r\\n'], 'kinds.csv', {type: 'text/csv'})), 1)`);
    check(await ready(ev, `document.querySelectorAll('.modal .ctxmap select').length === 4`), '#6123: the second CSV mapping opens');
    g = await ev(`[...document.querySelectorAll('.modal .ctxmap select')].map(s => s.value).join(',')`);
    check(g === 'given,email:work,email:home,email:home', '#6123: "Arbeit" = Work, "privat" = Home, a plain one without a company stays Home ' + g);
    await ev(`(document.querySelectorAll('.modal').forEach(m => m.remove()), 1)`);

    // ================= #6123 Alice: the "Address books" dialog and its menu at the button
    await signIn(ev, nav, 'alice');
    await click(ev, '#view [data-ct="menu"]');
    await ready(ev, `${MI}.length > 0`);
    await pick(ev, 'Address books…');
    check(await ready(ev, `!!document.querySelector('.modal [data-cbmenu="${BE}"]') && !!document.querySelector('.modal [data-cbmenu="${BV}"]')`), '#6123: the dialog lists both books');
    check(await ev(`(() => { const h = document.querySelector('.modal .ctbhint'); return !!h && h.getBoundingClientRect().height > 0 && /folders/.test(h.textContent) && /groups/.test(h.textContent); })()`), '#6123: one sentence on address books, folders and groups');
    check(await ev(`document.querySelectorAll('.modal .ctbrow .ctbic svg').length === 2 && !document.querySelector('.modal .ctbrow .cevdot')`), '#6123: each book with the book symbol');
    const share = await ev(`(() => { const m = document.querySelector('.modal [data-cbmenu="${BE}"]').closest('li').querySelector('.ctbm'), md = m.closest('.modal .card') || m.closest('.modal'), r = m.getBoundingClientRect(), mr = md.getBoundingClientRect();
      return JSON.stringify({t: m.textContent, full: m.scrollWidth <= m.clientWidth + 1, inside: r.right <= mr.right + 1 && r.left >= mr.left - 1, below: r.top >= m.closest('li').querySelector('.ctbt').getBoundingClientRect().bottom - 1}); })()`);
    const sh = JSON.parse(share);
    check(/shared with (Bob|1 person)/.test(sh.t) && sh.full && sh.inside && sh.below, '#6123: "shared with ..." in a second line, fully visible ' + share);
    await shot('p21174b-books-dialog.png');
    // the book's "..." opens its menu at the button
    await click(ev, `.modal [data-cbmenu="${BE}"]`);
    check(await ready(ev, `${MI}.some(b => b.textContent.trim() === 'Export…')`), '#6123: the book\'s menu opens');
    mi = await items(ev);
    check(mi.filter(x => /^Import/.test(x)).length === 1 && mi.filter(x => /^Export/.test(x)).length === 1, '#6123: the book\'s menu has one Import and one Export ' + mi.join('|'));
    const gap = await ev(`(() => { const b = document.querySelector('.modal [data-cbmenu="${BE}"]').getBoundingClientRect(), p = document.querySelector('#pop').getBoundingClientRect();
      const v = p.top >= b.bottom ? p.top - b.bottom : b.top >= p.bottom ? b.top - p.bottom : 0, h = p.left > b.right ? p.left - b.right : b.left > p.right ? b.left - p.right : 0; return JSON.stringify({v: Math.round(v), h: Math.round(h), top: Math.round(p.top), btn: Math.round(b.top)}); })()`);
    const gp = JSON.parse(gap);
    check(gp.v <= 16 && gp.h <= 16, '#6123: the book\'s menu stands at its "..." (gap in px) ' + gap);
    await shot('p21174b-book-menu.png');
    await ev(`(closePop(), 1)`);
    // a menu too tall for either side of its button: as near as the window allows (it used to go to the window's top)
    const tall = await ev(`(() => { const b = document.createElement('button'); b.textContent = 'x'; b.style.cssText = 'position:fixed;left:600px;top:400px;height:36px;z-index:1'; document.body.appendChild(b);
      const p = menu(b, Array.from({length: 14}, (_, i) => ({label: 'Entry ' + i, fn: () => {}}))), r = b.getBoundingClientRect(), pr = p.getBoundingClientRect(), h = pr.height;
      const fitsNone = h > innerHeight - 12 - r.bottom - 6 && h > r.top - 6 - 12, want = Math.max(12, Math.min(r.bottom + 6, innerHeight - 12 - h));
      const o = JSON.stringify({fitsNone, top: Math.round(pr.top), want: Math.round(want), h: Math.round(h)}); closePop(); b.remove(); return o; })()`);
    const tl = JSON.parse(tall);
    check(tl.fitsNone && Math.abs(tl.top - tl.want) <= 2 && tl.top > 100, '#6123: a menu that fits on neither side stays near its button ' + tall);
  }, false);

  console.log(`p21174_b_contacts_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
