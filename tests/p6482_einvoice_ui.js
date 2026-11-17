// kalmido-suite: fresh
// 2.1359.0 UI tests (#6482), own container (start.sh). Invented data only. jsdom:
// - the finalise dialog of an invoice above 250 EUR to a business in Germany with e-invoices switched off shows the warning
//   (2027 / 2028) and still finalises (only a warning); with e-invoices on the dialog has no warning
// - the button "Text block" of a document offers the German pack's "Retention note section 14b UStG"; choosing it adds a text
//   line with the note in the document's language (German: "§ 14b")
// freelancer-matrix: office (a person without an organisation sees the same)
// usage: node p6482_einvoice_ui.js <datadir>      (P6482UI_NOSTART=1: a running server, no start.sh)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6482UI_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients';
const COMPANY = {name: 'Studio Beispiel GmbH', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', email: 'kontakt@example.com', phone: '+49 40 000000',
  tax_number: '12/345/67890', vat_id: 'DE999999999', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};

async function editor(user, id) {
  const w = await boot({user, hash: `office/offers/${id}`}), d = w.document;
  w.__dialogs = 'manual';  // tests/boot.js dialogBridge: the dialogs are driven here (it would answer them at once)
  await until(() => d.querySelector('.ofdhead'), 60);
  return [w, d];
}

async function run(user, ck, tag) {
  await call('GET', '/api/office/settings', null, ck);
  await call('PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY, features_off: ['docs.einvoice']}, ck);
  const CL = (await call('POST', '/api/clients', {name: 'Beispielkunde GmbH', street: 'Marktstraße 5', zip: '50667', city: 'Köln', country: 'DE', vat_id: 'DE123456789'}, ck)).id;
  const mk = async () => call('POST', '/api/office/docs', {kind: 'invoice', lang: 'de', client_id: CL, service_from: '2026-05-01', service_to: '2026-05-31', items: [{title: 'Schnitt', qty: 1, rate: 900}]}, ck);
  const inv = await mk();
  check(inv.http === 201, `${tag}: draft invoice ${inv.http}`);

  // ---- the text block of section 14b UStG
  let [w, d] = await editor(user, inv.id);
  click(w, await until(() => d.querySelector('[data-ofd="it-text"]'), 60));
  const item = await until(() => [...d.querySelectorAll('.menu-list [role="menuitem"]')].find(b => /14b/.test(b.textContent)), 30);
  check(item && /Retention note section 14b UStG/.test(item.textContent), `${tag}: the menu "Text block" offers the retention note section 14b UStG`);
  click(w, item);
  const got = await until(async () => { const j = await call('GET', `/api/office/docs/${inv.id}`, null, ck); return (j.items || []).find(x => x.kind === 'text' && /§ 14b/.test(x.detail || '')) && j; }, 60);
  check(got, `${tag}: choosing it adds a text line with the German note (§ 14b)`);
  await until(() => [...d.querySelectorAll('.ofdits textarea, .ofdits [data-k="detail"]')].some(t => /§ 14b/.test(t.value || t.textContent || '')), 30);
  check([...d.querySelectorAll('.ofdits textarea, .ofdits [data-k="detail"]')].some(t => /§ 14b/.test(t.value || t.textContent || '')), `${tag}: the text line is visible in the editor`);

  // ---- the finalise dialog warns, finalising still works
  click(w, d.querySelector('.ofdhead [data-ofd="finalize"]'));
  const m = await until(() => d.querySelector('.modal .ofdfinwarn'), 60);
  check(m && /2027/.test(m.textContent) && /2028/.test(m.textContent) && /PDF/.test(m.textContent), `${tag}: the finalise dialog warns: no e-invoice ` + (m?.textContent || '').slice(0, 120));
  click(w, d.querySelector('.modal [data-cd="yes"]'));
  const srv = await until(async () => { const j = await call('GET', `/api/office/docs/${inv.id}`, null, ck); return j.locked && j; }, 60);
  check(srv && srv.locked && srv.number, `${tag}: only a warning: the invoice is finalised as ${srv && srv.number}`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- e-invoices on: no warning in the dialog
  await call('PUT', '/api/office/settings', {features_off: []}, ck);
  const inv2 = await mk();
  [w, d] = await editor(user, inv2.id);
  click(w, await until(() => d.querySelector('.ofdhead [data-ofd="finalize"]'), 60));
  const m2 = await until(() => d.querySelector('.modal [data-cd="yes"]'), 60);
  check(m2 && !d.querySelector('.modal .ofdfinwarn'), `${tag}: e-invoices on: the dialog has no warning`);
  click(w, d.querySelector('.modal [data-cd="no"]'));
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await run('alice', CK, 'org');

  // freelancer-matrix: office (a person without an organisation, its own admin)
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const FCK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, FCK);
  await run('frida', FCK, 'freelancer');

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
