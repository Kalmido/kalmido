// kalmido-suite: fresh
// (#6819) UI test: "Issue as paid" in the finalise dialog, own container (start.sh with KALMIDO_ISSUER_KEYS=1;
// KMT_NOSTART=1: a running server), jsdom. Invented companies and figures only.
// - an invoice issuer's draft with wish.paid (card): the finalise dialog shows "Issue as paid" unticked, the issuer's statement
//   as unconfirmed; ticked: date and method appear, filled from the statement (card); with the client tick it is finalised as
//   paid (status paid, one payment), the editor shows the payment; back in the list
// - a person's own invoice: the option is there too; unticked = finalised as before (issued, no payment)
// freelancer-matrix: office (frida has no organisation: her personal office, her own issuer)
// usage: node p6819_b_issue_paid_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: ((process.env.EXTRA || '') + ' -e KALMIDO_ISSUER_KEYS=1').trim()}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const key = async (k, method, url, body) => { const r = await fetch(B + 'api/v1/issuer/' + url, {method, headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + k}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const dlg = d => d.querySelector('.modal .cdlg-f')?.closest('.modal') || d.querySelector('.modal');
const FEAT = 'cal,comments,collab,office,clients';
const TODAY = new Date().toISOString().slice(0, 10);
const COMPANY = {name: 'Studio Beispiel', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', email: 'hallo@beispiel.example',
  phone: '+49 40 1234567', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const ADDR = {street: 'Marktweg 5', zip: '50667', city: 'Köln', country: 'DE'};

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call(ACK, 'POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(ACK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CK = await login('frida');
  await call(CK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  await call(CK, 'GET', '/api/office/settings');
  check((await call(CK, 'PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY})).http === 200, 'company data');
  const RG = (await call(CK, 'POST', '/api/office/num-ranges', {code: 'WEB', scheme: 'WEB-{yyyy}-{seq:03}'})).id;
  const iss = await call(CK, 'POST', '/api/office/issuers', {name: 'Shop', range_id: RG, password: 'password123'});
  check(iss.http === 201, 'an issuer with its key ' + iss.http);
  check((await key(iss.key, 'PUT', 'clients/by-ref/shop:1', {name: 'Musterkunde GmbH', ...ADDR, email_invoice: 'rechnung@muster.example'})).http === 201, 'a client by the key');
  const dr = await key(iss.key, 'POST', 'invoices', {client_ref: 'kauf:88', client: {external_ref: 'shop:1'}, service_from: TODAY, service_to: TODAY,
    items: [{text: 'Tarif Studio', qty: 1, unit: 'flat', rate: '150.00'}], expect: {net: '150.00', tax: '28.50', gross: '178.50'},
    wish: {paid: {amount: '178.50', date: TODAY, method: 'card', online_ref: 'tr_88'}}});
  check(dr.http === 201 && dr.doc_id, 'a draft by the key ' + dr.http);

  // ---- the issuer's draft: the dialog, the tick, finalised as paid
  let w = await boot({user: 'frida', hash: `office/invoices/${dr.doc_id}`}), d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  w.__dialogs = 'manual';
  click(w, d.querySelector('[data-ofd="finalize"]'));
  let m = await until(() => dlg(d)?.querySelector('#ofd-fin-paid') && dlg(d), 40);
  const mt = (m?.textContent || '').replace(/\s+/g, ' ');
  const cb = m?.querySelector('#ofd-fin-paid');
  check(cb && cb.checked === false && /Issue as paid/.test(mt), 'the dialog offers "Issue as paid", unticked ' + mt.slice(0, 200));
  check(/Statement of the invoice issuer \(unconfirmed\)/.test(mt) && /Card/.test(mt), 'the issuer\'s statement stands beside it as unconfirmed ' + mt.slice(0, 300));
  check(m?.querySelector('.ofdfinpaidf')?.hidden === true, 'date and method hidden while unticked');
  click(w, cb);
  check(cb?.checked === true && m?.querySelector('.ofdfinpaidf')?.hidden === false, 'ticked: date and method appear');
  check(m?.querySelector('#ofd-fin-pmeth')?.value === 'card' && (m?.querySelector('#ofd-fin-pdate')?.value || '') === TODAY, 'filled from the statement: card, its date');
  const hold = m?.querySelector('#ofd-ihd-ok');
  if (hold) { click(w, hold); }
  click(w, m?.querySelector('[data-cd="yes"]') || m?.querySelector('.btn.primary'));
  const x = await until(async () => { const y = await call(CK, 'GET', `/api/office/docs/${dr.doc_id}`); return y.locked && y; }, 80);
  check(x && x.status === 'paid' && (x.payments || []).length === 1, 'finalised as paid: status paid, one payment ' + (x ? `${x.status} ${(x.payments || []).length}` : 'not finalised'));
  const pay = await until(() => /Payments/.test(d.querySelector('.ofdeditor')?.textContent || '') && d.querySelector('[data-ofd="pay-del"]'), 60);
  check(!!pay, 'the editor shows the booked payment');
  check(!errs.length, 'issuer draft: no script errors ' + errs.join(' | ')); errs.splice(0);
  click(w, d.querySelector('[data-ofd="back"]'));
  check(await until(() => d.querySelector(`.ofdrow[data-id="${dr.doc_id}"]`), 60), 'back in the list: the invoice is there');
  w.close();

  // ---- a person's own invoice: the option is there; unticked = as before
  const own = await call(CK, 'POST', '/api/office/docs', {kind: 'invoice', lang: 'en', service_from: TODAY, service_to: TODAY, items: [{title: 'Schnitt', qty: 1, rate: 400}]});
  const cl = await call(CK, 'POST', '/api/clients', {name: 'Eigene Kundin', ...ADDR, email_invoice: 'k@muster.example'});
  await call(CK, 'PATCH', `/api/office/docs/${own.id}`, {client_id: cl.id});
  w = await boot({user: 'frida', hash: `office/invoices/${own.id}`}); d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  w.__dialogs = 'manual';
  click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => dlg(d)?.querySelector('#ofd-fin-paid') && dlg(d), 40);
  check(!!m && !/Statement of the invoice issuer/.test(m.textContent || ''), 'an own invoice: the option without an issuer statement');
  click(w, m?.querySelector('[data-cd="yes"]') || m?.querySelector('.btn.primary'));
  const y = await until(async () => { const z = await call(CK, 'GET', `/api/office/docs/${own.id}`); return z.locked && z; }, 80);
  check(y && y.status !== 'paid' && !(y.payments || []).length, 'unticked: finalised as before, no payment ' + (y ? y.status : 'not finalised'));
  check(!errs.length, 'own invoice: no script errors ' + errs.join(' | '));
  w.close();

  console.log(`p6819_b_issue_paid_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p6819_b_issue_paid_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
