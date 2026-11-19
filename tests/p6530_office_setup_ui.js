// kalmido-suite: fresh
// 2.1416.0 UI test (#6530): the card "Set up your office" on top of the office, own container (start.sh), jsdom. Invented
// companies and people only. freelancer-matrix: office (the person without an organisation sees the same card)
// - an office without company data: the card stands above Quotations & invoices, five rows (company, tax and small
//   business, bank, numbers, logo / letterhead), none ticked
// - each row leads into Settings > Company & office at its place (company name, tax number, number scheme)
// - name and address filled in: the company row is ticked, the card stays (tax number and IBAN still missing)
// - "Hide": the card goes and stays away after a reload (the setting of dismissed office hints, per office)
// - a second office with everything filled in: no card at all
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6530_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FULL = {name: 'Studio Voll', street: 'Hafenstraße 12', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};

async function flow(user) {
  const tag = ` (${user})`;
  await call('PUT', '/api/office/settings', {company_fields: {name: '', street: '', zip: '', city: '', tax_number: '', vat_id: '', iban: ''}});
  let w = await boot({user, hash: 'office/offers'}), d = w.document;
  const card = () => d.querySelector('#view .ofsu');
  check(await until(() => card()), 'the card "Set up your office" above the quotations' + tag);
  const rows = [...(card()?.querySelectorAll('[data-ofsu-row]') || [])].map(x => x.dataset.ofsuRow);
  check(rows.join(',') === 'co-name,co-tax,co-iban,numbers,logo', 'five rows ' + rows + tag);
  check(!card()?.querySelector('.ofsuok'), 'none ticked' + tag);
  check(/Coming from another program/.test(card()?.textContent || ''), 'the numbers row asks for the next number' + tag);
  // ---- each row leads into Settings > Company & office at its place
  for (const [k, sel] of [['co-name', '#os-name'], ['co-tax', '#osc-tax_number'], ['numbers', '#os-inv-scheme']]) {
    click(w, card().querySelector(`[data-ofsu-row="${k}"] [data-setgo]`));
    check(await until(() => d.querySelector('.smodal #s-biz ' + sel) && !w.eval('S.bizJump')), `${k} opens Settings > Company & office at ${sel}` + tag);
    click(w, d.querySelector('.smodal [data-m="close"]'));
    await until(() => !d.querySelector('.smodal'));
    w.eval(`location.hash = '#office/offers'; 1`);
    await until(() => card());
  }
  w.close();
  // ---- name and address: the company row ticked, the card stays
  check((await call('PUT', '/api/office/settings', {company_fields: {name: 'Studio ' + user, street: 'Hafenstraße 12', zip: '20457', city: 'Hamburg', country: 'DE'}})).status === 200, 'name and address saved' + tag);
  w = await boot({user, hash: 'office/offers'}); d = w.document;
  check(await until(() => card()?.querySelector('[data-ofsu-row="co-name"].ofsuok')), 'the company row is ticked' + tag);
  check(!card()?.querySelector('[data-ofsu-row="co-iban"].ofsuok'), 'the bank row still open' + tag);
  // ---- Hide: away, also after a reload
  click(w, card().querySelector('[data-ofc="setup-hide"]'));
  check(await until(() => !card()), 'Hide removes the card' + tag);
  await sleep(500);
  w.close();
  w = await boot({user, hash: 'office/offers'}); d = w.document;
  await until(() => d.querySelector('#view .office'));
  await sleep(800);
  check(!card(), 'the card stays away after a reload' + tag);
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients'});
  const me = (await call('GET', '/api/state')).me;
  const org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call('PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await flow('alice');
  // ---- a second office with everything filled in: no card
  const org2 = await call('POST', '/api/admin/orgs', {name: 'Beta', admin_id: me.id});
  await call('PATCH', '/api/settings', {workspace: `org:${org2.id}`});
  await call('PUT', '/api/office/settings', {company_fields: FULL});
  const w = await boot({user: 'alice', hash: 'office/offers'}), d = w.document;
  await until(() => d.querySelector('#view .office .ofcbody'));
  await sleep(800);
  check(!d.querySelector('#view .ofsu'), 'an office with name, address, tax number and IBAN shows no card');
  w.close();

  // ================= freelancer-matrix: office - the same card for a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await flow('frida');

  console.log(`p6530_office_setup_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
