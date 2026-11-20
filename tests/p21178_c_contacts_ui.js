// 2.1178.0 UI test, part C (#6121): contacts - loading, failed and empty states from the shared blocks (render.js), jsdom
// kalmido-suite: fresh
// against the own test container, invented data only:
// #6121 - the list: "Loading" from the shared block, a failed load = "Could not be loaded" + "Try again" (not "No contact
//         matches"), Try again brings the rows; the right column says nothing while the list is empty / loading / failed;
//         a quiet refresh (ct_live) that fails keeps the rows shown
//       - a card being opened shows "Loading" in its place, not the contact before
//       - the trash and the groups dialog: a failed load is said with "Try again" (no "trash is empty", the dialog stays)
//       - the "Link a contact" box of the task panel: a failed search = error + Try again (no endless "Loading")
//       - no contacts at all: ONE hint with "New contact" and "Import…" (both work), as a person without an organisation
// freelancer-matrix: the empty contacts of a person without an organisation (frida)
// The held answers wait in the page (window.fetch wrapped) until the test lets them go: every wait is on a real state.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const until = fn => until0(fn, {timeout: 15000, step: 100});
// requests matching re ("METHOD /url") wait in w.__held until go() (the real request) or fail() (a 500 with the text)
const hold = (w, re) => {
  w.__held = []; const f1 = w.__f1 || (w.__f1 = w.fetch);
  w.fetch = (u, o = {}) => {
    const k = `${(o.method || 'GET').toUpperCase()} ${u}`;
    return re.test(k) ? new Promise(res => w.__held.push({u: String(u), go: () => res(f1(u, o)), fail: msg => res(new Response(JSON.stringify({error: msg}), {status: 500, headers: {'content-type': 'application/json'}}))})) : f1(u, o);
  };
};
const unhold = w => { if (w.__f1) w.fetch = w.__f1; };
const holdPoll = w => until(() => w.eval('td_polling ? false : (td_polling = true)'));
const freePoll = w => w.eval('td_polling = false');
const txt = (d, sel) => d.querySelector(sel)?.textContent || '';
const lastModal = d => [...d.querySelectorAll('.modal')].pop();
const rowNames = d => [...d.querySelectorAll('#view .ctlist .ctrow .ctn b')].map(b => b.textContent);

(async () => {
  await sleep(600);
  const r0 = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r0.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,contacts'});
  const BK = (await call(CA, 'POST', '/api/books', {name: 'People', org_id: null})).id;
  const ADA = (await call(CA, 'POST', '/api/contacts', {book_id: BK, given: 'Ada', family: 'Lovelace', groups: ['Customers']})).id;
  const BOB = (await call(CA, 'POST', '/api/contacts', {book_id: BK, given: 'Bob', family: 'Builder'})).id;
  const GONE = (await call(CA, 'POST', '/api/contacts', {book_id: BK, given: 'Gina', family: 'Gone'})).id;
  check((await call(CA, 'DELETE', `/api/contacts/${GONE}`)).http === 200, 'a contact in the trash');
  const L = (await call(CA, 'POST', '/api/lists', {name: 'House'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Roof', list_id: L})).id;

  let w = await boot({user: 'alice', hash: 'contacts'}), d = w.document;
  check(await until(() => rowNames(d).includes('Ada Lovelace')), 'the contacts view shows its rows');
  await holdPoll(w);

  // ================= #6121: the trash's failed load is said with Try again
  hold(w, /^GET \/api\/contacts\?trash=1/);
  w.eval(`CT.trash = {}; ctDraw()`);
  check(await until(() => w.__held.length === 1 && d.querySelector('#view .ctview .eload')), '#6121 trash: "Loading" from the shared block while it loads');
  w.__held[0].fail('Testfehler');
  check(await until(() => d.querySelector('#view .ctview .eerr')), '#6121 trash: a failed load shows the error block');
  check(/The trash could not be loaded/.test(txt(d, '#view .ctview .eerr')) && !/trash is empty/i.test(txt(d, '#view .ctview')), '#6121 trash: it says so, not "The trash is empty": ' + txt(d, '#view .ctview'));
  check(!/Testfehler/.test(txt(d, '#toast:not(.hidden)')), '#6372 trash: no toast with the server text beside the error block: ' + txt(d, '#toast'));
  unhold(w);
  d.querySelector('#view .ctview .eerr [data-esretry]').click();
  check(await until(() => d.querySelector(`#view [data-ctt="crest"][data-id="${GONE}"]`)), '#6121 trash: Try again brings the deleted contact');
  w.eval(`ctt_close()`);
  await until(() => rowNames(d).includes('Ada Lovelace'));

  // ================= #6121: the list's failed load = error + Try again (not "No contact matches")
  hold(w, /^GET \/api\/contacts\?/);
  w.eval(`CT.items = null; CT.loading = false; CT.sel = null; CT.card = null; ctDraw()`);
  check(await until(() => w.__held.length === 1 && d.querySelector('#view .ctlistw .eload')), '#6121 list: "Loading" from the shared block while it loads');
  check(!/Select a contact/.test(txt(d, '#view .ctcols')), '#6121 list: the right column is quiet while it loads');
  w.__held[0].fail('Testfehler');
  check(await until(() => d.querySelector('#view .ctlistw .eerr')), '#6121 list: a failed load shows the error block');
  const le = txt(d, '#view .ctlistw');
  check(/Contacts could not be loaded/.test(le) && /Try again/.test(le) && !/No contact matches/.test(le), '#6121 list: "could not be loaded" + Try again, not "No contact matches": ' + le);
  check(!/Select a contact/.test(txt(d, '#view .ctcols')), '#6121 list: ONE message - the right column says nothing');
  check(!/Testfehler/.test(txt(d, '#toast:not(.hidden)')), '#6372 list: ONE message - no toast with the server text beside the error block: ' + txt(d, '#toast'));
  unhold(w);
  d.querySelector('#view .ctlistw [data-esretry]').click();
  check(await until(() => rowNames(d).includes('Ada Lovelace') && rowNames(d).includes('Bob Builder')), '#6121 list: Try again brings the rows');
  check(await until(() => /Select a contact/.test(txt(d, '#view .ctcols'))), '#6121 list: with rows the right column says "Select a contact" again');
  hold(w, /^GET \/api\/contacts\?/);
  const qr = w.eval(`ctLoad(1)`);
  check(await until(() => w.__held.length === 1), '#6121 quiet: the quiet refresh is on its way (held)');
  w.__held[0].fail('Testfehler'); await qr; unhold(w);
  check(rowNames(d).includes('Ada Lovelace') && !w.eval('CT.err'), '#6121 quiet: a failed quiet refresh keeps the rows (no error block)');

  // ================= #6121: a card being opened shows "Loading", not the one before
  d.querySelector(`#view [data-ctopen="${ADA}"]`).click();
  check(await until(() => txt(d, '#view #ct-h') === 'Ada Lovelace'), '#6121 card: Ada opens');
  hold(w, /^GET \/api\/contacts\/\d+$/);
  d.querySelector(`#view [data-ctopen="${BOB}"]`).click();
  check(await until(() => w.__held.length === 1 && d.querySelector('#view .ctcard.ctld .eload')), '#6121 card: Bob\'s place shows "Loading"');
  check(!/Ada Lovelace/.test(txt(d, '#view .ctcard')), '#6121 card: Ada\'s card is gone meanwhile');
  w.__held[0].go(); unhold(w);
  check(await until(() => txt(d, '#view #ct-h') === 'Bob Builder' && !d.querySelector('#view .ctcard.ctld')), '#6121 card: then Bob\'s card');

  // ================= #6121: the groups dialog stays on a failed load, with Try again
  hold(w, /^GET \/api\/contacts\/groups$/);
  w.eval(`ctx_groupsModal()`);
  check(await until(() => w.__held.length === 1 && d.querySelector('#ctg-body .eload')), '#6121 groups: "Loading" while it loads');
  w.__held[0].fail('Testfehler');
  check(await until(() => d.querySelector('#ctg-body .eerr')), '#6121 groups: a failed load is said in the dialog (it stays open)');
  check(/The groups could not be loaded/.test(txt(d, '#ctg-body')), '#6121 groups: in words: ' + txt(d, '#ctg-body'));
  unhold(w);
  d.querySelector('#ctg-body [data-esretry]').click();
  check(await until(() => /Customers/.test(txt(d, '#ctg-body'))), '#6121 groups: Try again lists the group');
  lastModal(d).querySelector('[data-ctg="close"]').click();

  // ================= #6121: the "Link a contact" box: a failed search = error + Try again
  w.eval(`go('l/${L}')`);
  await until(() => d.querySelector(`#view [data-id="${T}"]`));
  w.eval(`openDetail(${T})`);
  hold(w, /^GET \/api\/contacts\?limit=30/);
  (await until(() => d.querySelector('#detail [data-act="ct-link"]'))).click();
  check(await until(() => w.__held.length === 1 && d.querySelector('#pop #ctp-l .eload')), '#6121 link: "Loading" while it searches');
  w.__held[0].fail('Testfehler');
  check(await until(() => d.querySelector('#pop #ctp-l .eerr')), '#6121 link: a failed search says so (no endless "Loading")');
  check(!/Loading/.test(txt(d, '#pop #ctp-l')), '#6121 link: no "Loading" left');
  unhold(w);
  d.querySelector('#pop #ctp-l [data-esretry]').click();
  const pk = await until(() => d.querySelector(`#pop [data-ctpick="${ADA}"]`));
  check(pk, '#6121 link: Try again lists the contacts');
  pk.click();
  check(await until(() => d.querySelector(`#detail [data-ctunlink="${ADA}"]`)), '#6121 link: the picked contact is linked');
  freePoll(w);
  w.close();

  // ================= a person without an organisation, German: no contacts = ONE hint with New contact + Import
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: 'comments,contacts'});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  await call(CF, 'POST', '/api/books', {name: 'Kunden', org_id: null});
  w = await boot({user: 'frida', hash: 'contacts'}); d = w.document;
  const em = await until(() => d.querySelector('#view .ctlistw .ctnoitems'));
  check(em, 'freelancer empty: the empty block shows');
  check(/Noch keine Kontakte/.test(txt(d, '#view .ctnoitems')), 'freelancer empty: "Noch keine Kontakte": ' + txt(d, '#view .ctnoitems'));
  check(d.querySelector('#view .ctnoitems [data-ct="new"]') && d.querySelector('#view .ctnoitems [data-ct="imp"]'), 'freelancer empty: with the buttons "Neuer Kontakt" and "Importieren…"');
  check(!/Wähle einen Kontakt|Select a contact/.test(txt(d, '#view')) && !txt(d, '#view .ctcard.ctnone').trim(), 'freelancer empty: ONE hint - the right column says nothing');
  w.eval(`(() => { const f = document.querySelector('#ct-impfile'); f.click = () => { window.__imp = 1; }; return 1; })()`);
  d.querySelector('#view .ctnoitems [data-ct="imp"]').click();
  check(w.eval('window.__imp') === 1, 'freelancer empty: "Importieren…" opens the file choice');
  d.querySelector('#view .ctnoitems [data-ct="new"]').click();
  check(await until(() => d.querySelector('#ct-given')), 'freelancer empty: "Neuer Kontakt" opens the editor');
  lastModal(d).querySelector('[data-ctm2="close"]').click();
  w.close();
  console.log(`p21178_c_contacts_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
