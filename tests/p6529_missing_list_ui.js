// kalmido-suite: fresh
// 2.1416.0 UI test (#6529): the missing details of an invoice as a list that stays above the editor, own container (start.sh),
// jsdom. Invented companies, people and amounts only. freelancer-matrix: office (the person without an organisation, same editor)
// - an invoice draft of an office without company data: the list "Still missing before finalising" shows before any finalising,
//   one line per missing detail (company address, period of service, ...), each with its way
// - Finalise while something blocks: no dialog, the list stays and is lit up; nothing is finalised
// - "To the field" of the period leads to the field "Service from" (focused); "To the settings" of the company address opens
//   Settings > Company & office at the street field
// - the data filled in (company by API, the period in the editor), "Check again": no block left, Finalise opens the dialog
//   and finalises
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6529_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const COMPANY = {street: 'Hafenstraße 12', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};

async function flow(user) {
  const tag = ` (${user})`;
  await call('PUT', '/api/office/settings', {lang: 'en', currency: 'EUR', payment_days: 14});
  const cl = await call('POST', '/api/clients', {name: 'Beispielkunde AG', street: 'Marktstraße 5', zip: '50667', city: 'Köln', country: 'DE'});
  check(cl.status === 201, 'a client ' + cl.status + tag);
  const doc = await call('POST', '/api/office/docs', {kind: 'invoice', client_id: cl.id, items: [{title: 'Schnitt', qty: 1, rate: 1000}]});
  check(doc.status === 201, 'an invoice draft ' + doc.status + tag);
  const w = await boot({user, hash: `office/offers/${doc.id}`}), d = w.document;
  const box = () => d.querySelector('#view .ofdmiss');
  check(await until(() => box()?.querySelector('[data-miss="company_address"]')), 'the list shows before finalising, with the company address' + tag);
  check(!!box()?.querySelector('[data-miss="service_period"] [data-ofd="miss-go"]') && !!box()?.querySelector('[data-miss="company_iban"]'), 'the period and the IBAN with their ways' + tag);
  check(/Still missing before finalising/.test(box()?.textContent || ''), 'the heading of the blocks' + tag);
  // ---- Finalise while something blocks: no dialog, nothing finalised
  click(w, d.querySelector('[data-ofd="finalize"]'));
  check(await until(() => box()?.classList.contains('sflash')), 'Finalise lights the list up' + tag);
  await sleep(400);
  check(!d.querySelector('.modal.cdlg') && !d.querySelector('.modal [data-cd="yes"]'), 'no finalise dialog while something blocks' + tag);
  check(!(await call('GET', `/api/office/docs/${doc.id}`)).locked, 'nothing finalised' + tag);
  // ---- the ways: a field of the document, the settings
  click(w, box().querySelector('[data-miss="service_period"] [data-ofd="miss-go"]'));
  check(await until(() => d.activeElement?.dataset?.dpfor === 'ofd-service_from'), 'the period leads to "Service from" ' + d.activeElement?.outerHTML?.slice(0, 80) + tag);
  click(w, box().querySelector('[data-miss="company_address"] [data-ofd="miss-go"]'));
  check(await until(() => d.querySelector('.smodal #osc-street')), 'the company address opens Settings > Company & office at the street' + tag);
  check(await until(() => d.querySelector('.smodal #osc-street')?.closest('details.sfold')?.open), 'its group is open' + tag);
  click(w, d.querySelector('.smodal [data-m="close"]')); await until(() => !d.querySelector('.smodal'));
  // ---- filled in: no block, Finalise opens the dialog and finalises
  check((await call('PUT', '/api/office/settings', {company_fields: {...COMPANY, name: 'Studio ' + user}})).status === 200, 'company data saved' + tag);
  check((await call('PATCH', `/api/office/docs/${doc.id}`, {service_from: '2026-10-01', service_to: '2026-10-20'})).status === 200, 'the period saved' + tag);
  // back at the document (closing the settings may leave the address on the settings page)
  if (!d.querySelector('#view .ofdeditor [data-ofd="miss-re"], #view [data-ofd="miss-re"]')) w.eval(`location.hash = '#office/offers/${doc.id}'; 1`);
  check(await until(() => d.querySelector('#view [data-ofd="miss-re"]') && w.eval(`!!OFD.doc && OFD.doc.id === ${doc.id}`)), 'back at the document with its list' + tag);
  click(w, d.querySelector('#view [data-ofd="miss-re"]'));
  check(await until(() => d.querySelector('#view .ofdeditor') && !d.querySelector('#view .ofdmiss [data-miss="company_address"]') && !d.querySelector('#view .ofdmiss [data-miss="service_period"]')
    && !w.eval(`(OFD.doc.missing || []).some(m => m.level === 'block')`)), '"Check again": no block left' + tag);
  await until(() => !w.eval('OFD.docLoading'));
  click(w, d.querySelector('#view [data-ofd="finalize"]'));
  // the dialog opens now (askDialog of an admin's invoice, or askConfirm - the harness may answer that one itself)
  const y = await until(async () => d.querySelector('.modal [data-cd="yes"]') || ((await call('GET', `/api/office/docs/${doc.id}`)).locked ? 'done' : null));
  check(!!y, 'the finalise dialog opens ' + JSON.stringify({missing: w.eval('JSON.stringify(OFD.doc && OFD.doc.missing)'), modals: d.querySelectorAll('.modal').length}) + tag);
  if (y && y !== 'done') click(w, y);
  check(await until(async () => (await call('GET', `/api/office/docs/${doc.id}`)).locked), 'finalised' + tag);
  check(await until(() => !d.querySelector('#view .ofdmiss')), 'the finalised invoice shows no list' + tag);
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients'});
  { const me = (await call('GET', '/api/state')).me; const org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
    await call('PATCH', '/api/settings', {workspace: `org:${org.id}`}); }
  await flow('alice');

  // ================= freelancer-matrix: office - the same list for a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await flow('frida');

  console.log(`p6529_missing_list_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
