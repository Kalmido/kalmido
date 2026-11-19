// kalmido-suite: fresh
// 2.1435.0 UI tests (#6820): the delivery state of a document's e-mail in the invoice list and at the invoice. Own container
// (start.sh), jsdom, invented data only, as a person without an organisation (her personal office).
// freelancer-matrix: office
// - a mailed invoice: the row menu offers "Delivery failed"; picked: the row shows the tag, the status select's
//   "Delivery failed" lists it (and only it), the invoice shows the note
// - "Delivered after all" in the menu takes it back: no tag, the filter empty again; back to "All" lists every invoice
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const sql = (q, args) => JSON.parse(execFileSync('python3', [path.join(__dirname, 'dbx.py'), DATA, q, JSON.stringify(args || [])]).toString() || '[]');
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const menuItems = d => [...d.querySelectorAll('#pop [role="menuitem"]')].map(b => b.textContent.trim());
const pick = async (d, label) => { const it = await until(() => [...d.querySelectorAll('#pop [role="menuitem"]')].find(b => b.textContent.trim() === label)); it?.click(); return !!it; };
const COMPANY = {name: 'Beispiel Film GmbH', street: 'Musterweg 1', zip: '12345', city: 'Musterstadt', country: 'DE', email: 'hallo@beispiel.example',
  vat_id: 'DE123456789', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,office,clients'});
  const st = await call('GET', '/api/state');
  check(!(st.orgs || []).length, 'a person without an organisation');
  check((await call('PUT', '/api/office/settings', {company_fields: COMPANY})).http === 200, 'company');
  const cl = (await call('POST', '/api/clients', {name: 'Kunde GmbH', street: 'Weg 2', zip: '10115', city: 'Berlin', country: 'DE', email: 'kunde@example.com'})).id;
  const inv = async title => {
    const o = await call('POST', '/api/office/docs', {kind: 'invoice', client_id: cl, project_title: title, service_from: new Date().toISOString().slice(0, 10), items: [{title: 'Schnitt', qty: 1, rate: 100}]});
    check(o.http === 201, 'invoice ' + title + ' ' + o.http);
    const fz = await call('POST', `/api/office/docs/${o.id}/finalize`);
    check(fz.http < 300, 'finalised ' + title + ' ' + fz.http + ' ' + (fz.error || ''));
    return o.id;
  };
  const I1 = await inv('Mailed film'), I2 = await inv('Other film');
  sql("UPDATE office_docs SET status='sent', sent_at=CURRENT_TIMESTAMP, mail_state='sent', mail_at=CURRENT_TIMESTAMP WHERE id=?", [I1]);  // as the mail server took it

  let w = await boot({hash: 'office/invoices'}); let d = w.document;
  const rows = () => [...d.querySelectorAll('.ofdlist .ofdrow')].map(x => +x.dataset.id).sort((a, b) => a - b).join();
  const tagOf = id => d.querySelector(`.ofdlist .ofdrow[data-id="${id}"] .oms-tag`);
  check(await until(() => rows() === [I1, I2].sort((a, b) => a - b).join(), 60), 'the list: both invoices ' + rows());
  check(!tagOf(I1), 'no tag before');
  const sel = d.querySelector('#ofd-status');
  check(sel && [...sel.options].some(o => o.value === 'mail_failed' && o.textContent.trim() === 'Delivery failed'), 'the status select offers "Delivery failed"');
  const rowMenu = id => d.querySelector(`.ofdrmore[data-id="${id}"]`)?.click();
  rowMenu(I2);
  check(!(await until(() => menuItems(d).length && menuItems(d)) || []).includes('Delivery failed'), 'an invoice never mailed: no "Delivery failed" in its menu');
  d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  await sleep(200);
  rowMenu(I1);
  check(await pick(d, 'Delivery failed'), 'the mailed invoice\'s menu: "Delivery failed"');
  check(await until(() => tagOf(I1)), 'the row shows the tag');
  check(sql('SELECT mail_state FROM office_docs WHERE id=?', [I1])[0]?.mail_state === 'bounced', 'stored: bounced');
  const filter = v => { const s = d.querySelector('#ofd-status'); s.value = v; s.dispatchEvent(new w.Event('change', {bubbles: true})); };
  filter('mail_failed');
  check(await until(() => rows() === String(I1)), 'the filter "Delivery failed": only that invoice ' + rows());
  w.close();
  // ================= at the invoice
  w = await boot({hash: 'office/invoices/' + I1}); d = w.document;
  check(await until(() => d.querySelector('.oms-note'), 60), 'the invoice shows the note');
  check(/not delivered/i.test(d.querySelector('.oms-note')?.textContent || ''), 'its text: ' + d.querySelector('.oms-note')?.textContent);
  w.close();
  // ================= back
  w = await boot({hash: 'office/invoices'}); d = w.document;
  check(await until(() => tagOf(I1), 60), 'the list again: the tag');
  rowMenu(I1);
  check(await pick(d, 'Delivered after all'), 'the menu: "Delivered after all"');
  check(await until(() => !tagOf(I1)), 'the tag is gone');
  filter('mail_failed');
  check(await until(() => d.querySelector('.ofdlist') ? rows() === '' : true), 'the filter is empty again');
  filter('');
  check(await until(() => rows() === [I1, I2].sort((a, b) => a - b).join()), '"All" lists both again ' + rows());
  w.close();

  console.log(`p6820_office_mail_state_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
