// #7313 (package 2.1465 part C): every office request of the app names the office it shows; the server never guesses.
// kalmido-suite: fresh
// Jsdom, own container, invented data only. A person in two organisations (Alpha, Beta) and Private, workspace "All":
// - (d) F12 a client card of Beta under "All": its office calls name Beta (core.js ofc_spCur from the open object), the
//   open invoices load; back to the clients list, the client is there
// - F13 a link without an area (#office/offers/<id> of a Beta quotation, as a chat / mail sends it): opens in Beta's office,
//   the address gets the area (#office/s/org:<Beta>/offers/<id>); back leads to Beta's quotations
// - (b) a second tab chooses Alpha (saved on the server); the first tab still shows "All > Beta" and makes a quotation:
//   it lands in Beta's office and is in Beta's list it comes back to
// - route.wsp: #office/s/private with the own office off = a note with the offices that are on, never an empty page
// - the two ways of #7297: under "All" with only Alpha's office on, #office opens Alpha directly; the workspace Alpha chosen
//   at the top opens Alpha's office
// - freelancer-matrix: office (a person without an organisation: their own office under "All")
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
const viewTxt = d => (d.querySelector('#view')?.textContent || '').replace(/\s+/g, ' ');

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call('GET', '/api/state')).me;
  const A = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  const Be = (await call('POST', '/api/admin/orgs', {name: 'Beta', admin_id: me.id})).id;
  const WA = 'org:' + A, WB = 'org:' + Be;
  for (const [ws, nm] of [[WA, 'Alpha Studio GmbH'], [WB, 'Beta Werkstatt GmbH']]) {
    const s = await call('PUT', '/api/office/settings', {company_fields: {name: nm, country: 'de'}, lang: 'en', currency: 'EUR'}, CK, {'X-Kalmido-Office-Space': ws});
    check(s.http < 300, 'setup: the office of ' + nm + ' ' + s.http);
  }
  const cl = await call('POST', '/api/clients', {name: 'Example Kunde Beta', org_id: Be});
  check(cl.http === 201, 'setup: a client of Beta ' + cl.http);
  const q = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Beta Angebot', client_id: cl.id, items: []}, CK, {'X-Kalmido-Office-Space': WB});
  check(q.http < 300, 'setup: a quotation of Beta ' + q.http);
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= (d) F12: the client card of Beta under "All"
  let w = await boot({hash: 'client/' + cl.id, allWs: true}), d = w.document;
  check(w.eval('wsCur()') === 'all', 'the app under "All workspaces"');
  check(await until(() => w.eval('ofc_spCur()') === WB), 'F12: the open client card names Beta for its office calls ' + w.eval('JSON.stringify([ofc_spCur(), wso_cur(), ofc_spaces(), S.route, (MSC.items || []).length, CLV.id])'));
  const st = await w.eval(`api('GET', '/api/office/docs?kind=invoice&status=open&client_id=${cl.id}').then(() => 200, e => String(e && (e.status || e.message)))`);
  check(st === 200, 'F12: the card\'s office call (open invoices) answers 200 for Beta, no 400 ' + st);
  w.eval("go('clients')");
  check(await until(() => /Example Kunde Beta/.test(viewTxt(d))), 'back on the clients list, the client is there');

  // ================= F13: a link without an area opens in the object's office
  w.eval(`location.hash = '#office/offers/${q.id}'`);
  check(await until(() => w.location.hash === `#office/s/${WB}/offers/${q.id}`), 'F13: the address gets the area of the quotation ' + w.location.hash);
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === Be && w.eval('OFD.doc && OFD.doc.id') === q.id), 'F13: Beta\'s office opens the quotation');
  w.eval(`go('office/s/${WB}/offers')`);
  check(await until(() => /Beta Angebot/.test(viewTxt(d))), 'back to Beta\'s quotations, it is listed');

  // ================= (b) a second tab chooses Alpha; the first (All > Beta) makes a quotation
  const w2 = await boot({hash: 'tasks', allWs: true});
  await w2.eval(`wsSet('${WA}')`);
  check(await until(async () => (await call('GET', '/api/state')).settings?.workspace === WA), 'the second tab saved Alpha on the server');
  w2.close();
  const made = await w.eval("api('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Aus dem ersten Tab', items: []})");
  check(made && made.id, 'the first tab (All > Beta) makes a quotation');
  const inB = await call('GET', '/api/office/docs?kind=offer', null, CK, {'X-Kalmido-Office-Space': WB});
  const inA = await call('GET', '/api/office/docs?kind=offer', null, CK, {'X-Kalmido-Office-Space': WA});
  check((inB.docs || []).some(x => x.id === made?.id) && !(inA.docs || []).some(x => x.id === made?.id), '(b) it landed in Beta\'s office (shown), not in Alpha (saved by the other tab)');
  w.eval(`OFD.list = null; go('office/s/${WB}/offers')`);
  check(await until(() => /Aus dem ersten Tab/.test(viewTxt(d))), '(b) Beta\'s list shows it');
  // #7574 (the race behind the flaky step above, made certain): a list load still running when the list is discarded never
  // puts its older answer over it - the held answer comes back after a new quotation and the discard, the list loads again
  await w.eval(`window.__api0 = api; window.__held = null; api = (m, u, ...a) => { const p = __api0(m, u, ...a); if (m !== 'GET' || !/^\\/api\\/office\\/docs\\?kind=offer/.test(u) || window.__held) return p; window.__held = 1; return new Promise(r => { window.__open = () => r(p); }); }; ofdLoadList(true); 0`);
  check(await until(() => w.eval('OFD.loading && typeof __open === "function"')), '#7574: a list load is held open');
  await w.eval("__api0('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Neu waehrend der Ladung', items: []})");
  w.eval(`OFD.list = null; ofdDraw(); __open()`);
  check(await until(() => /Neu waehrend der Ladung/.test(viewTxt(d)) && !w.eval('OFD.loading')), '#7574: the list discarded during the load shows the new quotation, not the older answer');
  await sleep(400);
  check(/Neu waehrend der Ladung/.test(viewTxt(d)), '#7574: and it stays');
  w.eval('api = __api0');
  w.close();

  // ================= route.wsp: an area whose office is off
  await call('PATCH', '/api/settings', {workspace: 'all', ws_mods_off: JSON.stringify({private: ['office']})});
  w = await boot({hash: 'office/s/private/offers', allWs: true}); d = w.document;
  check(await until(() => /The office is off for you in this workspace/.test(viewTxt(d)) && d.querySelector(`.ofcnoarea a[href="#office/s/${WB}"]`)), 'route.wsp: #office/s/private with the own office off = a note with the offices on ' + viewTxt(d).slice(0, 120));
  d.querySelector(`.ofcnoarea a[href="#office/s/${WB}"]`)?.click();
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === Be), 'a tap on Beta opens Beta\'s office');
  w.close();

  // ================= the two ways of #7297
  await call('PATCH', '/api/settings', {workspace: 'all', ws_mods_off: JSON.stringify({private: ['office'], [WB]: ['office']})});
  w = await boot({hash: 'office', allWs: true}); d = w.document;
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A && !w.eval('OFC.infoErr')), 'under "All" with only Alpha\'s office on: it opens directly ' + (w.eval('OFC.infoErr') || ''));
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all', ws_mods_off: '{}'});
  w = await boot({hash: 'tasks', allWs: true}); d = w.document;
  await w.eval(`wsSet('${WA}')`);
  w.eval("go('office/offers')");
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A && !w.eval('OFC.infoErr') && !/Which workspace/.test(viewTxt(d))), 'the workspace Alpha chosen at the top: Alpha\'s office, no question');
  w.close();

  // ================= freelancer-matrix: office
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  check(fr.http < 300, 'setup: frida without an organisation ' + fr.http);
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'all'}, CF);
  w = await boot({user: 'frida', hash: 'office/offers', allWs: true}); d = w.document;
  check(await until(() => w.eval('OFC.info && OFC.info.personal') && !w.eval('OFC.infoErr')), 'freelancer: their own office under "All"');
  w.close();

  console.log(`p21465_c_office_area_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
