// kalmido-suite: fresh
// 2.1380.0 (#6976) UI test: finalising an invoice draft dated in an earlier year (the turn of the year), own container
// (start.sh; KMT_NOSTART=1: a running server), jsdom. Invented companies and figures only.
// - the server: GET /api/office/docs/<id>/number-preview says past_year (the draft's date) and number_today (the number when
//   dated today) for an invoice draft of the main number range dated in an earlier year; a draft of this year has neither
// - "Finalise" on such a draft: the dialog says "The date … lies in an earlier year." with "Set the date to today" ticked; the
//   number it names follows the tick (today's number ticked, the old year's number unticked)
// - finalised ticked: dated today, the due date keeps its term, today's number; unticked: the date and the old year's number stay
// - a draft of this year: no hint, no tick
// freelancer-matrix: office (frida has no organisation: her personal office)
// usage: node p21380_a_pastyear_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients';
const COMPANY = {name: 'Studio Beispiel GmbH', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', vat_id: 'DE999999999', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const days = (a, b) => Math.round((Date.parse(String(b).slice(0, 10)) - Date.parse(String(a).slice(0, 10))) / 864e5);

async function editor(user, id) {
  const w = await boot({user, hash: `office/invoices/${id}`}), d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  w.__dialogs = 'manual';  // the dialogs are driven here (the bridge of boot.js would answer them)
  return [w, d];
}
const dlg = d => d.querySelector('.modal .cdlg-f')?.closest('.modal');
const shown = m => m?.querySelector('.ofdfinno b')?.textContent || '';

async function run(user, ck, tag) {
  await call('GET', '/api/office/settings', null, ck);
  await call('PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY, payment_days: 14, invoice_scheme: 'RE-{yyyy}-{seq:03}'}, ck);
  const CL = (await call('POST', '/api/clients', {name: 'Beispielkunde AG', street: 'Marktstraße 5', zip: '50667', city: 'Köln', country: 'DE'}, ck)).id;
  const Y = new Date().getFullYear(), OLD = Y - 1;
  const mk = (date, b = {}) => call('POST', '/api/office/docs', {kind: 'invoice', client_id: CL, date, service_from: `${OLD}-12-01`, service_to: `${OLD}-12-31`, items: [{title: 'Schnitt', qty: 1, rate: 900}], ...b}, ck);
  const a = await mk(`${OLD}-12-20`), b = await mk(`${OLD}-12-21`), now = await mk(`${Y}-01-02`);
  check(a.http === 201 && b.http === 201 && now.http === 201, `${tag}: three drafts ` + [a.http, b.http, now.http]);
  check((await call('PATCH', `/api/office/docs/${a.id}`, {due_date: `${Y}-01-03`}, ck)).http === 200, `${tag}: the December draft has a due date`);
  const pa = await call('GET', `/api/office/docs/${a.id}/number-preview`, null, ck);
  check(pa.past_year === `${OLD}-12-20` && pa.number === `RE-${OLD}-001` && pa.number_today === `RE-${Y}-001`,
    `${tag}: the preview knows the old date and both numbers ` + JSON.stringify(pa));
  const pn = await call('GET', `/api/office/docs/${now.id}/number-preview`, null, ck);
  check(pn.http === 200 && !('past_year' in pn) && !('number_today' in pn), `${tag}: a draft of this year has no past_year ` + JSON.stringify(pn));

  // ---- ticked (the default): dated today, today's number
  let [w, d] = await editor(user, a.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  let m = await until(() => dlg(d)?.querySelector('#ofd-fin-today') && dlg(d), 40);
  const cb = m?.querySelector('#ofd-fin-today');
  check(m && /lies in an earlier year/.test(m.textContent) && /Set the date to today/.test(m.textContent) && cb?.checked === true,
    `${tag}: the dialog names the earlier year, "Set the date to today" ticked ` + (m?.textContent || '').replace(/\s+/g, ' ').slice(0, 300));
  check(shown(m) === `RE-${Y}-001`, `${tag}: ticked, the dialog names today's number ${shown(m)}`);
  click(w, cb); cb && cb.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(cb?.checked === false && shown(m) === `RE-${OLD}-001`, `${tag}: unticked, it names the number of the old year ${shown(m)}`);
  click(w, cb); cb && cb.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(cb?.checked === true && shown(m) === `RE-${Y}-001`, `${tag}: ticked again, today's number ${shown(m)}`);
  click(w, m?.querySelector('[data-cd="yes"]'));
  let r = await until(async () => { const x = await call('GET', `/api/office/docs/${a.id}`, null, ck); return x.locked && x; }, 60);
  check(r && r.number === `RE-${Y}-001` && String(r.date).slice(0, 4) === String(Y), `${tag}: finalised ticked: today's date and number ${r?.number} ${r?.date}`);
  check(r && days(r.date, r.due_date) === days(`${OLD}-12-20`, `${Y}-01-03`), `${tag}: the due date keeps its term ${r?.date} ${r?.due_date}`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- unticked: the date and the old year's number stay
  [w, d] = await editor(user, b.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => dlg(d)?.querySelector('#ofd-fin-today') && dlg(d), 40);
  const cb2 = m?.querySelector('#ofd-fin-today');
  click(w, cb2); cb2 && cb2.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(cb2?.checked === false && shown(m) === `RE-${OLD}-001`, `${tag}: the second draft unticked names ${shown(m)}`);
  click(w, m?.querySelector('[data-cd="yes"]'));
  r = await until(async () => { const x = await call('GET', `/api/office/docs/${b.id}`, null, ck); return x.locked && x; }, 60);
  check(r && r.number === `RE-${OLD}-001` && String(r.date).slice(0, 10) === `${OLD}-12-21`, `${tag}: finalised unticked: date and number of the old year ${r?.number} ${r?.date}`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- a draft of this year: no hint
  [w, d] = await editor(user, now.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => dlg(d)?.querySelector('[data-cd="yes"]') && dlg(d), 40);
  check(m && !m.querySelector('#ofd-fin-today') && !/earlier year/.test(m.textContent), `${tag}: a draft of this year: no hint, no tick`);
  click(w, m?.querySelector('[data-cd="no"]'));
  await until(() => !dlg(d), 30);
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

  // freelancer-matrix: office (a person without an organisation, her own admin)
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const FCK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, FCK);
  await run('frida', FCK, 'freelancer');

  console.log(`p21380_a_pastyear_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p21380_a_pastyear_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
