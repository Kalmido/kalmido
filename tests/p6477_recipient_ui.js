// kalmido-suite: fresh
// 2.1308.0 (#6477) UI test, own container (start.sh): an invoice without a client (the clients module off) has the fixed
// address fields Recipient, Street, Address extra, Postcode, City, Country instead of the free "Address lines"; they are
// filled and saved; Finalise without the postcode is refused with "postcode of the recipient" and the invoice stays a
// draft; with it, Finalise goes through. A quotation keeps the free lines. The same as a person without an organisation.
// P6477_NOSTART=1 = the server already runs.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6477_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };  // http: the document has a status of its own
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,office';  // the clients module off: the document head has the recipient's own fields
const setVal = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const COMPANY = {name: 'Studio Nordlicht GmbH', street: 'Hafenstraße 12', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890',
  iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};

async function run(user, ck, who) {
  check((await call(ck, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT})).http === 200, who + ': settings');
  await require('./boot').officeWs({Cookie: ck});  // the organisation's office (one workspace), the personal one without
  const st = await call(ck, 'PUT', '/api/office/settings', {lang: 'de', company_fields: COMPANY});
  check(st.http === 200, who + ': office settings ' + JSON.stringify(st).slice(0, 160));
  const inv = await call(ck, 'POST', '/api/office/docs', {kind: 'invoice', project_title: 'Imagefilm', service_from: '2026-05-01', service_to: '2026-05-31', date: '2026-05-08', payment_days: 14});
  check(inv.http === 201, who + ': an invoice draft ' + JSON.stringify(inv).slice(0, 160));
  await call(ck, 'PUT', `/api/office/docs/${inv.id}/items`, {items: [{title: 'Filmherstellung', qty: 2, unit: 'day', rate: 1000}]});

  let w = await boot({user, hash: 'office/invoices/' + inv.id}), d = w.document;
  w.confirm = () => true;
  const street = await until(() => d.querySelector('.ofdeditor #ofd-recipient_street'), 60);
  check(street && d.querySelector('#ofd-recipient_name') && d.querySelector('#ofd-recipient_extra') && d.querySelector('#ofd-recipient_zip')
    && d.querySelector('#ofd-recipient_city') && d.querySelector('#ofd-recipient_country-q'), who + ': the fixed fields are there');
  check(!d.querySelector('#ofd-recipient_lines'), who + ': no free "Address lines" on an invoice');
  if (street) {
    setVal(w, d.querySelector('#ofd-recipient_name'), 'Musterfirma GmbH');
    await until(async () => (await call(ck, 'GET', `/api/office/docs/${inv.id}`)).recipient?.name === 'Musterfirma GmbH', 60);
    setVal(w, d.querySelector('#ofd-recipient_street'), 'Weg 2');
    await until(async () => (await call(ck, 'GET', `/api/office/docs/${inv.id}`)).recipient?.street === 'Weg 2', 60);
    setVal(w, d.querySelector('#ofd-recipient_city'), 'Berlin');
    await until(async () => (await call(ck, 'GET', `/api/office/docs/${inv.id}`)).recipient?.city === 'Berlin', 60);
  }
  let got = await call(ck, 'GET', `/api/office/docs/${inv.id}`);
  check(got.recipient?.name === 'Musterfirma GmbH' && got.recipient?.street === 'Weg 2' && got.recipient?.city === 'Berlin' && !got.recipient?.zip,
    who + ': name, street and city saved ' + JSON.stringify(got.recipient || {}).slice(0, 200));
  // Finalise without the postcode: refused with the word, still a draft
  (await until(() => d.querySelector('.ofdeditor [data-ofd="finalize"], [data-ofd="finalize"]'), 60))?.click();
  const said = await until(() => /postcode of the recipient/.test(d.body.textContent), 60);
  check(said, who + ': the refusal names "postcode of the recipient"');
  got = await call(ck, 'GET', `/api/office/docs/${inv.id}`);
  check(!got.locked && !got.number && got.status === 'draft', who + ': still a draft without a number');
  // with the postcode it goes through
  const zip = await until(() => d.querySelector('#ofd-recipient_zip'), 60);
  if (zip) {
    setVal(w, zip, '10115');
    await until(async () => (await call(ck, 'GET', `/api/office/docs/${inv.id}`)).recipient?.zip === '10115', 60);
  }
  (await until(() => d.querySelector('[data-ofd="finalize"]'), 60))?.click();
  got = await until(async () => { const x = await call(ck, 'GET', `/api/office/docs/${inv.id}`); return x.locked && x; }, 80);
  check(got && got.number && got.recipient?.zip === '10115', who + ': with the postcode Finalise goes through ' + JSON.stringify(got || {}).slice(0, 120));
  w.close();

  // a quotation keeps the free lines
  const off = await call(ck, 'POST', '/api/office/docs', {kind: 'offer', project_title: 'Angebot'});
  w = await boot({user, hash: 'office/offers/' + off.id}); d = w.document;
  check(await until(() => d.querySelector('.ofdeditor #ofd-recipient_lines'), 60) && !d.querySelector('#ofd-recipient_street'), who + ': a quotation keeps "Address lines"');
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call(CK, 'POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']});
  await run('alice', CK, 'org');
  // a person without an organisation (tests/freelancer_fixture.py for the API suites)
  const u = await call(CK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http === 201 || u.http === 200, 'freelancer account ' + JSON.stringify(u).slice(0, 120));
  const FK = await login('frida');
  const ws = (await call(FK, 'GET', '/api/state')).me?.workspaces || [];
  check(ws.length === 0, 'frida is in no organisation');
  await run('frida', FK, 'freelancer');
  console.log(`p6477_recipient_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
