// kalmido-suite: fresh
// 2.1494.0 (#7556) Settings > Company & office: its own office tabs (Private | each organisation) instead of switching the
// whole app's workspace. Jsdom, own container, invented data only.
// - alice in Alpha and Bravo (+ Private), the app on Alpha: the tabs, Alpha preselected; the tab Bravo shows Bravo's settings,
//   a field saved there lands in Bravo's office (Alpha's keeps its value), the app's workspace stays Alpha (here and on the
//   server); closing the settings gives the office pages Alpha back
// - under "All": the office used last here is preselected; opened from an office page, the office of that page
// - freelancer-matrix: office (frida without an organisation: one office, no tabs, the line with its name)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,office,clients';
const srvWs = async (ck = CK) => (await call('GET', '/api/state', null, ck)).settings?.workspace;
const days = async ws => (await call('GET', '/api/office/settings', null, CK, {'X-Kalmido-Office-Space': ws})).settings?.payment_days;
const tabOn = d => d.querySelector('#s-biz .bizsp .bizspt.on')?.dataset.ws || '';
const closeSettings = async w => { w.eval(`$$('.modal').forEach(m => m.remove())`); await until(() => !w.document.querySelector('#s-biz')); };

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
  const WA = 'org:' + A, WB = 'org:' + Bo;
  for (const [ws, nm] of [[WA, 'Alpha Studio GmbH'], [WB, 'Bravo Werkstatt GmbH']]) {
    const s = await call('PUT', '/api/office/settings', {company_fields: {name: nm, country: 'de'}, lang: 'en', currency: 'EUR', payment_days: 14}, CK, {'X-Kalmido-Office-Space': ws});
    check(s.http < 300, 'setup: the office of ' + nm + ' ' + s.http);
  }
  await call('PATCH', '/api/settings', {workspace: WA});

  // ================= the app on Alpha: the tab Bravo shows and saves Bravo, the app stays on Alpha
  let w = await boot({hash: 'office/offers'}), d = w.document;
  check(await until(() => w.eval('wsCur()') === WA && w.eval('OFC.info && OFC.info.org_id') === A), 'the app on Alpha, its office');
  w.eval("settingsModal('biz')");
  check(await until(() => d.querySelectorAll('#s-biz .bizsp [data-ofc="bizsp"]').length === 3), 'a tab per office: Private, Alpha, Bravo');
  check(await until(() => tabOn(d) === WA && w.eval('OFC.info && OFC.info.org_id') === A), 'Alpha preselected (the office the page came from) ' + tabOn(d));
  d.querySelector(`#s-biz [data-ofc="bizsp"][data-ws="${WB}"]`).click();
  check(await until(() => tabOn(d) === WB && w.eval('OFC.info && OFC.info.org_id') === Bo && !!d.querySelector('#s-biz #os-paydays')), 'the tab Bravo shows Bravo\'s settings');
  check(/Bravo Werkstatt/.test(d.querySelector('#s-biz')?.textContent || '') || d.querySelector('#s-biz [value="Bravo Werkstatt GmbH"]') || [...d.querySelectorAll('#s-biz input, #s-biz textarea')].some(i => /Bravo Werkstatt/.test(i.value)), 'Bravo\'s company');
  check(w.eval('wsCur()') === WA && await srvWs() === WA, 'the app\'s workspace stays Alpha (here and on the server)');
  const f = d.querySelector('#s-biz #os-paydays');
  f.value = '21'; f.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(await until(async () => await days(WB) === 21), 'a field saved under the tab Bravo lands in Bravo\'s office');
  check(await days(WA) === 14, 'Alpha\'s office keeps its value (no field writes into the wrong office)');
  await closeSettings(w);
  w.eval("go('office/offers')");
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A), 'settings closed: the office pages show Alpha again');
  w.close();

  // ================= under "All": the office used last here; from an office page that page's office
  await call('PATCH', '/api/settings', {workspace: 'all'});
  w = await boot({hash: 'tasks', allWs: true, ls: {'tasks.bizsp': JSON.stringify(WB)}}); d = w.document;
  w.eval("settingsModal('biz')");
  check(await until(() => tabOn(d) === WB && w.eval('OFC.info && OFC.info.org_id') === Bo), '"All": the office used last here is preselected ' + tabOn(d));
  check(!/Which workspace\?/.test(d.querySelector('#s-biz')?.textContent || ''), '"All": never "Which workspace?"');
  await closeSettings(w);
  w.eval(`go('office/s/${WA}/offers')`);
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A), 'the office page of Alpha under "All"');
  w.eval("settingsModal('biz')");
  check(await until(() => tabOn(d) === WA), 'opened from Alpha\'s office page: the tab Alpha ' + tabOn(d));
  check(w.eval('wsCur()') === 'all', 'the app stays on "All"');
  w.close();

  // ================= a person without an organisation: one office, no tabs
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, CF);
  w = await boot({user: 'frida', hash: 'tasks'}); d = w.document;
  w.eval("settingsModal('biz')");
  check(await until(() => !!d.querySelector('#s-biz #ofc-set')), 'frida: her office settings');
  check(!d.querySelector('#s-biz .bizsp') && /Private/.test(d.querySelector('#s-biz .sbizws')?.textContent || ''), 'frida: no tabs, the line with her office ' + (d.querySelector('#s-biz .sbizws')?.textContent || ''));
  w.close();

  console.log(`p7556_bizsp_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
