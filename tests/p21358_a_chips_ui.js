// kalmido-suite: fresh
// 2.1358.0 A (#6964) UI test, own container (start.sh), jsdom, invented data only. The kind chips of Quotations / Invoices
// (Archive, Reminders, Corrections ...) change the list also under an area address of "All workspaces" (#office/s/org:<id>/...):
// ofd_kindHash skipped no prefix, so only the address changed and the list stayed (device test Android 2.1344.0).
// - a phone (390 px): a tap on the chip Corrections shows the (empty) corrections list, the chip is the current one, the address names it
// - a tap on Invoices (the point itself) leads back to the invoice list with its draft
// - an address with the kind (a link, Back) chooses the kind under the prefix as well; the archive too
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,office,clients';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call('GET', '/api/state')).me;
  const A = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  const Bo = (await call('POST', '/api/admin/orgs', {name: 'Bravo', admin_id: me.id})).id;
  check(A > 0 && Bo > 0, 'organisations');
  const WA = 'org:' + A;
  await call('PATCH', '/api/settings', {workspace: 'all'});
  const inv = await call('POST', '/api/office/docs', {kind: 'invoice', lang: 'en', project_title: 'Alpha Rechnung', items: [{kind: 'service', title: 'Kamera', qty: 1, unit: 'day', rate: 500, tax: 'standard', raw_fee: 0, producing: 0, intext: 'intern', cost: 0, discountable: 1}]}, {'X-Kalmido-Office-Space': WA});
  check(inv.http === 201, 'an invoice draft in Alpha ' + inv.http);

  const w = await boot({hash: `office/s/${WA}/invoices`, allWs: true, mobile: true}), d = w.document;
  const rowsOf = () => d.querySelectorAll('#view .ofdlist .ofdrow').length;
  const chip = k => d.querySelector(`#view .ofpb .ofpk[data-ofk="${k}"]`);
  check(await until(() => w.eval('OFD.kind') === 'invoice' && rowsOf() === 1 && chip('credit')), 'the invoice list of Alpha with its chips ' + rowsOf());
  chip('credit').click();
  check(await until(() => w.eval('OFD.kind') === 'credit' && rowsOf() === 0), 'tap Corrections: the list changes (no invoice any more) ' + w.eval('OFD.kind') + ' ' + rowsOf());
  check(w.location.hash === `#office/s/${WA}/invoices/credit`, 'the address names the kind ' + w.location.hash);
  check(await until(() => chip('credit')?.getAttribute('aria-current') === 'true'), 'the chip Corrections is the current one');
  d.querySelector('#view .ofpb .ofpt2[data-ofm="invoices"]').click();
  check(await until(() => w.eval('OFD.kind') === 'invoice' && rowsOf() === 1), 'tap Invoices: back to the invoice list ' + w.eval('OFD.kind') + ' ' + rowsOf());
  w.eval("go('office/invoices/archive')");
  check(await until(() => w.eval('OFD.kind') === 'archive'), 'a link to the archive chooses it ' + w.eval('OFD.kind') + ' ' + w.location.hash);
  w.history.back();
  check(await until(() => w.eval('OFD.kind') === 'invoice' && rowsOf() === 1), 'Back: the invoice list again ' + w.eval('OFD.kind') + ' ' + w.location.hash);
  w.close();
  console.log(`p21358_a_chips_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack); process.exit(1); });
