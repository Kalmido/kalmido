// kalmido-suite: fresh
// 2.1345.0 (#6943) UI test: the surcharge ("Zuschlag") of a quotation as percent or fixed amount. Own container (start.sh),
// jsdom, invented services and amounts. As a person WITHOUT an organisation (her personal office; freelancer-matrix: office).
// - the surcharge field has a switch % / EUR like the discount; switched to EUR the percent becomes 0 (the surcharge stays
//   on); 300 typed: the line "Surcharge" 300.00 without a percent, net 3,300.00, gross 3,795.00 on screen; the switch
//   stays on the amount after the save; back to %, the amount is gone and the percent field is there again
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const change = (w, el, v) => { if (!el) return; if (v !== undefined) el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const FEATURES = 'cal,collab,comments,contacts,files,clients,office';
const svc = (title, qty, rate, tax = 'standard', unit = 'day') => ({kind: 'service', title, qty, unit, rate, tax, raw_fee: 0, producing: 0, in_handling: 0, in_markup: 1, intext: 'intern', cost: 0, discountable: 1});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const AK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']}, AK);
  await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: (await call('GET', '/api/state', null, AK)).me.id}, AK);
  const fu = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []}, AK);
  check(fu.http < 300, 'a person without an organisation ' + fu.http);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATURES});
  check(((await call('GET', '/api/state')).me.workspaces || []).length === 0, 'frida is in no organisation');
  await call('PUT', '/api/office/settings', {lang: 'en', currency: 'EUR'});
  const doc = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Campaign', raw_mode: 'none', producing_on: 0,
    items: [svc('Direction', 2, 1000), svc('Book licence', 1, 1000, 'reduced', 'flat')]});
  check(doc.http === 201, 'a quotation with 19 % and 7 % ' + doc.http);
  const D = doc.id, get = () => call('GET', `/api/office/docs/${D}`);
  check((await call('PATCH', `/api/office/docs/${D}`, {markup_pct: 15})).http === 200, 'the surcharge on, 15 %');

  const w = await boot({user: 'frida', hash: `office/offers/${D}`}), d = w.document;
  const mode = await until(() => d.querySelector('#ofd-markup_mode'));
  check(mode && mode.value === 'pct' && d.querySelector('#ofd-markup_pct'), 'the surcharge field: percent, with the switch % / EUR');
  await until(() => /15 %/.test(d.querySelector('.ofdautos')?.textContent || ''));
  change(w, mode, 'amount');
  let x = await until(async () => { const j = await get(); return j.markup_amount == null && +j.markup_pct === 0 ? j : null; });
  check(x, 'switched to the amount: the percent is 0, the surcharge stays on');
  const amt = await until(() => d.querySelector('#ofd-markup_amount'));
  check(amt && !d.querySelector('#ofd-markup_pct'), 'the amount field instead of the percent');
  change(w, amt, '300');
  x = await until(async () => { const j = await get(); return +j.markup_amount === 300 ? j : null; });
  const sl = x?.totals?.lines?.find(l => l.kind === 'surcharge');
  check(x && sl?.total === 300 && sl?.pct == null && x.totals?.net === 3300 && x.totals?.gross === 3795,
    'saved: 300.00 as its own line, net 3300.00, gross 3795.00 (200.00 at 19 %, 100.00 at 7 %) ' + JSON.stringify(sl || {}) + ' ' + (x && x.totals?.gross));
  await until(() => /300\.00/.test(d.querySelector('.ofdautos')?.textContent || ''));
  const at = (d.querySelector('.ofdautos')?.textContent || '').replace(/\s+/g, ' ');
  check(/Surcharge/.test(at) && /300\.00/.test(at) && !/%/.test(at), 'on screen: the line "Surcharge" with 300.00 and no percent: ' + at.slice(0, 200));
  await until(() => /3,795\.00/.test(d.querySelector('#ofd-totals')?.textContent || ''));
  check(/3,795\.00/.test(d.querySelector('#ofd-totals')?.textContent || ''), 'on screen: the total 3,795.00');
  check(d.querySelector('#ofd-markup_mode')?.value === 'amount' && d.querySelector('#ofd-markup_amount')?.value.replace(/[^0-9]/g, '') === '300', 'after the save the switch stays on the amount, 300 in the field');

  // ---- back to percent
  change(w, d.querySelector('#ofd-markup_mode'), 'pct');
  x = await until(async () => { const j = await get(); return j.markup_amount == null ? j : null; });
  check(x && !x.totals?.lines?.some(l => l.kind === 'surcharge'), 'back to percent: the amount is cleared, 0 % = no line');
  await until(() => d.querySelector('#ofd-markup_pct'));
  check(d.querySelector('#ofd-markup_pct') && !/300\.00/.test(d.querySelector('.ofdautos')?.textContent || ''), 'on screen: the percent field again, no amount line');

  console.log(`p6943_zuschlag_betrag_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
