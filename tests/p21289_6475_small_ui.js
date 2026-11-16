// kalmido-suite: fresh
// 2.1289.0 UI test (#6475): the VAT choice of the office editor under the switch "Small business", own container (start.sh).
// jsdom; invented data only. Played by a person WITHOUT an organisation (the personal office; freelancer-matrix: office).
// - switch on + a draft without VAT: no VAT choice in the editor (the section 19 note shown)
// - switch on + a draft with VAT from before the switch: the VAT choice stays, with the hint "As a small business without
//   VAT"; set to "without VAT" and the section 19 note in the editor, the draft finalises (usable, not stuck)
// - switch off: the VAT choice as before, the note "Small business" is not offered
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21289S_UI_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const until = async (fn, n = 60) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const FEAT = 'cal,comments,collab,office,clients';
const COMPANY = {name: 'Studio Beispiel', street: 'Hafenstraße 12', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890',
  iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const HINT = 'As a small business without VAT';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  // freelancer-matrix: office -- a person without an organisation
  const u = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http === 200 || u.http === 201, 'the freelancer ' + u.http);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await call('GET', '/api/office/settings');
  check((await call('PUT', '/api/office/settings', {small_business: 0, lang: 'de', payment_days: 14, company_fields: COMPANY})).http === 200, 'office settings');
  const CL = (await call('POST', '/api/clients', {name: 'Beispielkunde AG', street: 'Marktstraße 5', zip: '50667', city: 'Köln', country: 'DE'})).id;
  const inv = async () => (await call('POST', '/api/office/docs', {kind: 'invoice', client_id: CL, service_from: '2026-10-01', service_to: '2026-10-20',
    items: [{title: 'Schnitt', qty: 1, rate: 1000}]})).id;
  const OLD = await inv();  // with VAT, made before the switch
  check((await call('GET', `/api/office/docs/${OLD}`)).vat_mode === 'vat', 'setup: a draft with VAT');

  // ================= switch off: as before
  let w = await boot({user: 'frida', hash: 'office/offers/' + OLD}); let d = w.document;
  check(await until(() => d.querySelector('#ofd-vat_mode')), 'switch off: the VAT choice is there');
  check(!(d.querySelector('#ofd-vat_mode').closest('.row')?.textContent || '').includes(HINT), 'switch off: no small business hint');
  w.close();

  // ================= switch on
  check((await call('PUT', '/api/office/settings', {small_business: 1})).http === 200, 'small business on');
  const NEW = await inv();
  check((await call('GET', `/api/office/docs/${NEW}`)).vat_mode === 'novat', 'setup: a new draft without VAT');
  w = await boot({user: 'frida', hash: 'office/offers/' + NEW}); d = w.document;
  check(await until(() => d.querySelector('#ofd-client_id')), 'the new draft opens');
  await sleep(300);
  check(!d.querySelector('#ofd-vat_mode'), 'switch on, draft without VAT: no VAT choice');
  check(await until(() => d.querySelector('#ofd-vat_note')) && [...d.querySelector('#ofd-vat_note').options].some(o => o.value === 'small'), 'switch on: the section 19 note offered');
  w.close();

  w = await boot({user: 'frida', hash: 'office/offers/' + OLD}); d = w.document;
  const sel = await until(() => d.querySelector('#ofd-vat_mode'));
  check(sel && (sel.closest('.row')?.textContent || '').includes(HINT), 'switch on, draft with VAT: the choice stays with the hint');
  check(!sel?.disabled, 'the choice can be changed');
  if (sel) { sel.value = 'novat'; sel.dispatchEvent(new w.Event('change', {bubbles: true})); }
  check(await until(async () => (await call('GET', `/api/office/docs/${OLD}`)).vat_mode === 'novat'), 'set to without VAT in the editor');
  check(await until(() => !d.querySelector('#ofd-vat_mode')), 'now matching the switch: the choice is hidden');
  const note = await until(() => d.querySelector('#ofd-vat_note'));
  if (note) { note.value = 'small'; note.dispatchEvent(new w.Event('change', {bubbles: true})); }
  check(await until(async () => (await call('GET', `/api/office/docs/${OLD}`)).vat_note === 'small'), 'the section 19 note chosen in the editor');
  w.close();
  const fin = await call('POST', `/api/office/docs/${OLD}/finalize`);
  check(fin.http === 200 && fin.locked, 'set right in the editor, the draft finalises ' + fin.http + ' ' + (fin.error || ''));

  // ================= switch off again: the note "Small business" is not offered on a draft without it
  check((await call('PUT', '/api/office/settings', {small_business: 0})).http === 200, 'small business off');
  const OFF = await inv();
  check((await call('PATCH', `/api/office/docs/${OFF}`, {vat_mode: 'novat'})).http === 200, 'setup: a draft without VAT, switch off');
  w = await boot({user: 'frida', hash: 'office/offers/' + OFF}); d = w.document;
  const n2 = await until(() => d.querySelector('#ofd-vat_note'));
  check(n2 && ![...n2.options].some(o => o.value === 'small') && [...n2.options].some(o => o.value === 'reverse'), 'switch off: no section 19 note offered');
  check(d.querySelector('#ofd-vat_mode'), 'switch off: the VAT choice as before');
  w.close();

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
