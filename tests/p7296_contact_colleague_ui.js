// #7296 UI test: the contact card's "..." menu "Add a colleague at the same company". jsdom, fresh container, invented names only:
// kalmido-suite: fresh
//  - the menu of a contact with a company offers the entry; a contact without a company does not
//  - the entry opens the normal "New contact" dialog with company, department, business address, website, the company's
//    landline (phone of the kind Work) and the address book filled in; first / last name, e-mail, mobile, birthday, note,
//    photo and tags are empty
//  - closing it untouched asks nothing; opened again, a name typed, Save creates the contact at once (no look-alike note for
//    the shared landline), the toast is the normal "Contact created", the server has the taken fields and not the others
//  - a person without an organisation (private address book, freelancer parity): the same entry and the same prefill
// freelancer-matrix: contacts (frida has no organisation)
// The waits are on states (rows, the server, the dialog), never on a fixed time.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, sleep, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => until0(fn, {timeout: ms || 15000, step: 100});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const FEAT = 'contacts';
const LABEL = 'Add a colleague at the same company';
const toastText = d => { const t = d.querySelector('#toast'); return t && !t.classList.contains('hidden') ? t.textContent : ''; };
const menuItems = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')];
const ada = book => ({book_id: book, given: 'Ada', family: 'Lovelace', org: 'Acme Example Ltd', dept: 'Research', title: 'Head of research',
  phones: [{value: '+49 170 1234567', type: ['cell']}, {value: '+49 30 1234567', type: ['work']}],
  emails: [{value: 'ada@acme.example', type: ['work']}],
  addresses: [{street: 'Main Street 1', code: '10115', city: 'Berlin', country: 'Germany', type: ['work']}, {street: 'Home Road 9', code: '10117', city: 'Berlin', country: 'Germany', type: ['home']}],
  urls: [{value: 'https://acme.example', type: ['work']}], bday: '1990-12-10', note: 'Likes engines', groups: ['VIP']});

async function cardMenu(w, d, id, tag) {
  w.eval(`go('contacts/${id}')`);
  check(await until(() => w.eval('CT.card?.id') === id && d.querySelector('#view [data-ct="cmenu"]')), `${tag}: the card shows`);
  d.querySelector('#view [data-ct="cmenu"]').click();
  return (await until(() => { const x = menuItems(d); return x.length && x; })) || [];
}
const val = (md, sel) => md.querySelector(sel)?.value || '';
const vals = (md, k) => [...md.querySelectorAll(`input[data-ctk="${k}"][data-cf="value"]`)].map(x => x.value).filter(Boolean);

async function openMate(w, d, id, tag) {
  const its = await cardMenu(w, d, id, tag);
  const it = its.find(x => x.textContent.trim() === LABEL);
  check(it, `${tag}: the card's menu offers "${LABEL}": ` + its.map(x => x.textContent.trim()));
  if (!it) return null;
  it.click();
  const md = await until(() => d.querySelector('.modal.ctmodal'));
  check(md, `${tag}: the contact dialog opens`);
  return md;
}

async function prefilled(md, tag, bookId, w) {
  check(/New contact/.test(md.querySelector('h3')?.textContent || ''), `${tag}: it is the "New contact" dialog`);
  check(val(md, '#ct-org') === 'Acme Example Ltd' && val(md, '#ct-dept') === 'Research', `${tag}: company and department taken: ${val(md, '#ct-org')} / ${val(md, '#ct-dept')}`);
  check(!val(md, '#ct-given') && !val(md, '#ct-family') && !val(md, '#ct-title') && !val(md, '#ct-note') && !val(md, '#ct-groups') && !val(md, '#ct-bday'), `${tag}: name, title, note, tags and birthday are empty`);
  check(JSON.stringify(vals(md, 'phones')) === JSON.stringify(['+49 30 1234567']), `${tag}: only the company's landline taken: ${vals(md, 'phones')}`);
  check(!!md.querySelector('input[data-ctk="phones"][data-cf="value"]:placeholder-shown') || [...md.querySelectorAll('input[data-ctk="phones"][data-cf="value"]')].some(x => !x.value), `${tag}: an empty phone row for the mobile`);
  check(!vals(md, 'emails').length, `${tag}: no e-mail taken`);
  check(JSON.stringify(vals(md, 'urls')) === JSON.stringify(['https://acme.example']), `${tag}: the website taken: ${vals(md, 'urls')}`);
  const streets = [...md.querySelectorAll('input[data-ctk="addresses"][data-cf="street"]')].map(x => x.value);
  check(JSON.stringify(streets) === JSON.stringify(['Main Street 1']), `${tag}: the business address taken, the home address not: ${streets}`);
  check(!/avatar[^"]*img|<img/.test(md.querySelector('#ct-ph')?.innerHTML || '') , `${tag}: no photo`);
  const bk = md.querySelector('#ct-bk');
  check(!bk || +bk.value === bookId, `${tag}: the same address book: ${bk?.value} (${bookId})`);
  void w;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: []});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const B1 = (await call(CA, 'POST', '/api/books', {name: 'People', org_id: null})).id;
  const B2 = (await call(CA, 'POST', '/api/books', {name: 'Work', org_id: null})).id;
  const r = await call(CA, 'POST', '/api/contacts', ada(B2));
  const ADA = r.id;
  const NOORG = (await call(CA, 'POST', '/api/contacts', {book_id: B1, given: 'Linus', family: 'Sample'})).id;
  check(B1 && B2 && ADA && NOORG, 'two address books, Ada at a company, Linus without one ' + JSON.stringify(r).slice(0, 200));

  let w = await boot({user: 'alice', hash: 'contacts'}), d = w.document;
  w.__asked = 0; w.confirm = () => { w.__asked++; return true; };

  // ================= no company: no entry
  const its0 = await cardMenu(w, d, NOORG, 'no company');
  check(its0.length && !its0.some(x => x.textContent.trim() === LABEL), 'no company: the menu has no colleague entry');
  d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  await until(() => !menuItems(d).length);

  // ================= prefill; closing untouched asks nothing
  let md = await openMate(w, d, ADA, 'alice');
  if (md) {
    await prefilled(md, 'alice', B2, w);
    md.querySelector('[data-ctm2="close"]').click();
    check(await until(() => !d.querySelector('.modal.ctmodal')), 'alice: Cancel on the untouched dialog closes it');
    check(w.__asked === 0 && !d.querySelector('.modal'), 'alice: no "Discard changes?" for the untouched prefill');
  }

  // ================= a name, Save: created at once, no look-alike note
  md = await openMate(w, d, ADA, 'save');
  if (md) {
    const g = md.querySelector('#ct-given'); g.value = 'Bob'; g.dispatchEvent(new w.Event('input', {bubbles: true}));
    const f = md.querySelector('#ct-family'); f.value = 'Builder'; f.dispatchEvent(new w.Event('input', {bubbles: true}));
    md.querySelector('[data-ctm2="save"]').click();
    check(await until(() => /Contact created/.test(toastText(d))), 'save: the normal "Contact created": ' + toastText(d));
    check(!d.querySelector('.ctxdup'), 'save: no look-alike note for the shared landline');
    const got = (await call(CA, 'GET', '/api/contacts?q=Builder')).items || [];
    check(got.length === 1, 'save: Bob is on the server once');
    const bob = got[0] ? await call(CA, 'GET', '/api/contacts/' + got[0].id) : {};
    check(bob.org === 'Acme Example Ltd' && bob.dept === 'Research' && bob.book_id === B2, `save: company, department, book: ${bob.org} / ${bob.dept} / ${bob.book_id}`);
    check((bob.phones || []).map(x => x.value).join() === '+49 30 1234567', 'save: only the landline: ' + JSON.stringify(bob.phones));
    check(!(bob.emails || []).length && !bob.bday && !bob.note && !(bob.groups || []).length && !bob.title && !bob.photo, 'save: no e-mail, birthday, note, tags, title, photo');
    check((bob.addresses || []).length === 1 && bob.addresses[0].street === 'Main Street 1' && (bob.urls || [])[0]?.value === 'https://acme.example', 'save: business address and website');
    check(await until(() => w.eval('CT.card?.id') === bob.id || [...d.querySelectorAll('#view .ctrow .ctn b')].some(b => /Bob Builder/.test(b.textContent))), 'save: Bob shows');
  }

  // ================= a person without an organisation (freelancer parity)
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  const FB = (await call(CF, 'POST', '/api/books', {name: 'Mine', org_id: null})).id;
  const FA = (await call(CF, 'POST', '/api/contacts', ada(FB))).id;
  check(FB && FA, 'frida: her book and contact');
  w.close?.();
  w = await boot({user: 'frida', hash: 'contacts'}); d = w.document;
  w.__asked = 0; w.confirm = () => { w.__asked++; return true; };
  md = await openMate(w, d, FA, 'freelancer');
  if (md) {
    await prefilled(md, 'freelancer', FB, w);
    const g = md.querySelector('#ct-given'); g.value = 'Kat'; g.dispatchEvent(new w.Event('input', {bubbles: true}));
    md.querySelector('[data-ctm2="save"]').click();
    check(await until(() => /Contact created/.test(toastText(d))) && !d.querySelector('.ctxdup'), 'freelancer: created, no look-alike note');
    check(((await call(CF, 'GET', '/api/contacts?q=Kat')).items || []).some(x => x.org === 'Acme Example Ltd'), 'freelancer: Kat at Acme on the server');
  }

  console.log(`p7296_contact_colleague_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
