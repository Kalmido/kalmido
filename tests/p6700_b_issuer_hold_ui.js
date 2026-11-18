// kalmido-suite: fresh
// 2.1384.0 (#6700) UI test: the hold mark of a client an invoice issuer's key set up, own container (start.sh with
// KALMIDO_ISSUER_KEYS=1; KMT_NOSTART=1: a running server), jsdom. Invented companies and figures only.
// - the client card shows "Managed by an invoice issuer", the fields the key set and the button "Client data from the invoice
//   issuer checked"; the button takes the mark away (the box goes, the server has no mark any more, the external id stays)
// - "Finalise" on a draft of a client with a mark: the dialog lists the issuer's data with the tick "I checked these client
//   data"; without the tick nothing is finalised (the hint says so), with it the invoice is finalised
// freelancer-matrix: office (frida has no organisation: her personal office, her own issuer)
// usage: node p6700_b_issuer_hold_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: ((process.env.EXTRA || '') + ' -e KALMIDO_ISSUER_KEYS=1').trim()}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const key = async (k, method, ref, body) => { const r = await fetch(B + 'api/v1/issuer/clients/by-ref/' + ref, {method, headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + k}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients';
const TODAY = new Date().toISOString().slice(0, 10);
const COMPANY = {name: 'Studio Beispiel', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', email: 'hallo@beispiel.example',
  phone: '+49 40 1234567', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const ADDR = {street: 'Marktweg 5', zip: '50667', city: 'Köln', country: 'DE'};
const dlg = d => d.querySelector('.modal .cdlg-f')?.closest('.modal');

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call(ACK, 'POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  // freelancer-matrix: office (a person without an organisation, her own admin and her own issuer)
  await call(ACK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CK = await login('frida');
  await call(CK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  await call(CK, 'GET', '/api/office/settings');
  check((await call(CK, 'PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY})).http === 200, 'company data');
  const RG = (await call(CK, 'POST', '/api/office/num-ranges', {code: 'WEB', scheme: 'WEB-{yyyy}-{seq:03}'})).id;
  const iss = await call(CK, 'POST', '/api/office/issuers', {name: 'Shop', range_id: RG, password: 'password123'});
  check(iss.http === 201 && /^kis_test_/.test(iss.key || ''), 'an issuer with its key ' + iss.http);
  const c1 = await key(iss.key, 'PUT', 'shop:1', {name: 'Musterkunde GmbH', ...ADDR, email_invoice: 'rechnung@muster.example'});
  const c2 = await key(iss.key, 'PUT', 'shop:2', {name: 'Zweitkunde GmbH', ...ADDR, email_invoice: 'rechnung@zweit.example'});
  check(c1.http === 201 && c2.http === 201 && c1.checked === false, 'two clients by the key, not checked');
  const list = (await call(CK, 'GET', '/api/clients')).clients || [];
  const id1 = list.find(x => x.name === 'Musterkunde GmbH')?.id, id2 = list.find(x => x.name === 'Zweitkunde GmbH')?.id;

  // ---- the client card: the mark, then "checked"
  let w = await boot({user: 'frida', hash: `client/${id1}`}), d = w.document;
  let box = await until(() => d.querySelector('.msclcard .ihdbox'), 60);
  const txt = (box?.textContent || '').replace(/\s+/g, ' ');
  check(box && /Set up by the invoice issuer Shop/.test(txt) && /rechnung@muster\.example/.test(txt) && /E-mail for invoices/.test(txt),
    'the card shows the mark with the issuer and its fields ' + txt.slice(0, 300));
  check(/Managed by an invoice issuer, external ID shop:1/.test(d.querySelector('.msclcard')?.textContent || ''), 'the card names the external id');
  const btn = box?.querySelector('[data-ihd-ok]');
  check(btn && /Client data from the invoice issuer checked/.test(btn.textContent), 'the button to take it away is there');
  click(w, btn);
  const gone = await until(() => !d.querySelector('.msclcard .ihdbox') && d.querySelector('.msclcard'), 60);
  const srv = await call(CK, 'GET', `/api/clients/${id1}`);
  check(gone && srv.issuer && !srv.issuer.client_hold && srv.issuer.external_ref === 'shop:1', 'checked: the box goes, the server has no mark, the external id stays');
  check(/Managed by an invoice issuer/.test(d.querySelector('.msclcard')?.textContent || ''), 'the external id stays on the card');
  check(!errs.length, 'card: no script errors ' + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- the finalise dialog of a draft of the second client: the list and the tick
  const doc = await call(CK, 'POST', '/api/office/docs', {kind: 'invoice', lang: 'en', client_id: id2, service_from: TODAY, service_to: TODAY, items: [{title: 'Schnitt', qty: 1, rate: 400}]});
  check(doc.http === 201, 'a draft for the second client ' + doc.http);
  w = await boot({user: 'frida', hash: `office/invoices/${doc.id}`}); d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  w.__dialogs = 'manual';
  click(w, d.querySelector('[data-ofd="finalize"]'));
  let m = await until(() => dlg(d)?.querySelector('#ofd-ihd-ok') && dlg(d), 40);
  const mt = (m?.textContent || '').replace(/\s+/g, ' ');
  check(m && /Set up by the invoice issuer Shop/.test(mt) && /rechnung@zweit\.example/.test(mt) && /I checked these client data/.test(mt),
    'the finalise dialog lists the issuer\'s data with the tick ' + mt.slice(0, 300));
  const cb = m?.querySelector('#ofd-ihd-ok');
  check(cb && cb.checked === false, 'the tick starts unticked');
  click(w, m?.querySelector('[data-cd="yes"]'));
  await sleep(1500);
  let x = await call(CK, 'GET', `/api/office/docs/${doc.id}`);
  check(!x.locked, 'without the tick nothing is finalised');
  check(!errs.length, 'dialog without the tick: no script errors ' + errs.join(' | ')); errs.splice(0);
  // with the tick: the dialog of an office admin (own number) stays open for it, the plain one is opened again
  if (!dlg(d)?.querySelector('#ofd-ihd-ok')) click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => dlg(d)?.querySelector('#ofd-ihd-ok') && dlg(d), 40);
  const cb2 = m?.querySelector('#ofd-ihd-ok');
  click(w, cb2); cb2 && cb2.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(cb2?.checked === true, 'ticked');
  click(w, m?.querySelector('[data-cd="yes"]'));
  x = await until(async () => { const y = await call(CK, 'GET', `/api/office/docs/${doc.id}`); return y.locked && y; }, 60);
  check(x && x.number, 'with the tick: finalised ' + (x?.number || ''));
  check(!errs.length, 'dialog with the tick: no script errors ' + errs.join(' | '));
  w.close();

  console.log(`p6700_b_issuer_hold_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p6700_b_issuer_hold_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
