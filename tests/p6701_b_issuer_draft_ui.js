// kalmido-suite: fresh
// 2.1417.0 (#6701) UI test: an invoice issuer's draft in the office, own container (start.sh with KALMIDO_ISSUER_KEYS=1;
// KMT_NOSTART=1: a running server), jsdom. Invented companies and figures only.
// - the invoice editor of a draft the key made shows "Made by the invoice issuer Shop" with its client_ref and the outside
//   system's unconfirmed statements (paid by card, sending wished, payment terms, the VAT ID check: no proof)
// - the person works on as with any draft: a field saved in the editor, "Finalise" opens its dialog, back in the list
// - the invoice list's filter "number range / invoice issuer": only the issuer's draft, then all again
// - a draft a person made shows no such note
// freelancer-matrix: office (frida has no organisation: her personal office, her own issuer)
// usage: node p6701_b_issuer_draft_ui.js <datadir>
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
  const dr = await key(iss.key, 'POST', 'invoices', {client_ref: 'kauf:77', client: {external_ref: 'shop:1'}, service_from: TODAY, service_to: TODAY,
    items: [{text: 'Tarif Studio', qty: 1, unit: 'flat', rate: '150.00'}], expect: {net: '150.00', tax: '28.50', gross: '178.50'},
    vat_check: {source: 'VIES', valid: true}, wish: {send: true, due_days: 14, paid: {amount: '178.50', date: TODAY, method: 'card', online_ref: 'tr_77'}}});
  check(dr.http === 201 && dr.doc_id, 'a draft by the key ' + dr.http + ' ' + JSON.stringify(dr).slice(0, 200));

  // ---- into the editor: the note, then the usual work
  let w = await boot({user: 'frida', hash: `office/invoices/${dr.doc_id}`}), d = w.document;
  const box = await until(() => d.querySelector('.ofdiss'), 60);
  const txt = (box?.textContent || '').replace(/\s+/g, ' ');
  check(box && /Made by the invoice issuer Shop/.test(txt) && /kauf:77/.test(txt), 'the editor names the issuer and the client_ref ' + txt.slice(0, 200));
  check(/Unconfirmed statements/.test(txt) && /Paid/.test(txt) && /Card/.test(txt) && /tr_77/.test(txt) && /Sending wished/.test(txt)
    && /14 days/.test(txt) && /no proof/.test(txt), 'the unconfirmed statements: paid by card, sending wished, terms, the VAT ID check (no proof) ' + txt.slice(0, 400));
  const inp = d.querySelector('[data-f="order_ref"]');
  check(!!inp, 'the editor\'s fields are there');
  if (inp) { inp.value = 'Bestellung 77'; inp.dispatchEvent(new w.Event('input', {bubbles: true})); inp.dispatchEvent(new w.Event('change', {bubbles: true})); }
  const saved = await until(async () => (await call(CK, 'GET', `/api/office/docs/${dr.doc_id}`)).order_ref === 'Bestellung 77', 60);
  check(saved, 'a field saved in the editor of the issuer\'s draft');
  w.__dialogs = 'manual';
  click(w, d.querySelector('[data-ofd="finalize"]'));
  const m = await until(() => d.querySelector('.modal'), 40);
  check(!!m, 'Finalise opens its dialog');
  check(!errs.length, 'editor: no script errors ' + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- the list: the draft is there; a person's own draft has no note
  const own = await call(CK, 'POST', '/api/office/docs', {kind: 'invoice', lang: 'en', service_from: TODAY, service_to: TODAY, items: [{title: 'Schnitt', qty: 1, rate: 400}]});
  w = await boot({user: 'frida', hash: 'office/invoices'}); d = w.document;
  const row = await until(() => d.querySelector(`.ofdrow[data-id="${dr.doc_id}"]`), 60);
  check(!!row && !!d.querySelector(`.ofdrow[data-id="${own.id}"]`), 'back in the list: the issuer\'s draft and the own one are there');
  const sel = await until(() => d.querySelector('#ofd-src'), 40);
  const opts = [...(sel?.options || [])].map(o => o.value);
  check(sel && opts.includes('issuer:any') && opts.includes(`range:${RG}`) && opts.includes('range:main'), 'the filter offers the main range, the range and the issuers ' + opts.join(','));
  if (sel) { sel.value = 'issuer:any'; sel.dispatchEvent(new w.Event('change', {bubbles: true})); }
  const only = await until(() => d.querySelector(`.ofdrow[data-id="${dr.doc_id}"]`) && !d.querySelector(`.ofdrow[data-id="${own.id}"]`), 60);
  check(only, 'filter "From invoice issuers": only the issuer\'s draft');
  if (sel) { const s2 = d.querySelector('#ofd-src'); s2.value = ''; s2.dispatchEvent(new w.Event('change', {bubbles: true})); }
  check(await until(() => d.querySelector(`.ofdrow[data-id="${own.id}"]`), 60), 'filter back to all: the own draft again');
  w.close();
  w = await boot({user: 'frida', hash: `office/invoices/${own.id}`}); d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  check(!d.querySelector('.ofdiss'), 'a person\'s own draft shows no issuer note');
  check(!errs.length, 'list and own draft: no script errors ' + errs.join(' | '));
  w.close();

  console.log(`p6701_b_issuer_draft_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p6701_b_issuer_draft_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
