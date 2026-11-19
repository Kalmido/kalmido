// 2.1437.0 (#7297): the office in a chosen workspace. A person in two organisations (+ Private): the app names the office's
// kalmido-suite: fresh
// area with EVERY office request (core.js ofc_spHdr), so the office never depends on the setting the server got. Jsdom, own
// container, invented data only.
// - the split view's right half (/?split=1, miniwin.js MW_GUARD: no PATCH /api/settings ever leaves it) on "Alpha" while the
//   server keeps "All": the office opens Alpha with its full menu (admin points), the quotations load, no "Select a workspace";
//   a state load does not jump back to "All" (was: OFFICE_NO_ORG, the short menu, the silent jump)
// - the menu's cache is per office area: "All > Alpha" and "Alpha" share it (areas.js ofm_ws)
// - the main window: a state load that ends while the switch is still being saved keeps the new workspace (core.js OPT)
// - PATCH /api/settings fails: the switch is taken back to the workspace before with a note, never a silent half state
// - a workspace really gone (removed from Bravo): switched to "All workspaces" with a note, never silently
// - Settings > Company & office under "All": "Which workspace? ..." (no "at the top") with a button per
//   workspace with an office right under it; a click chooses it and its office settings show
// - freelancer-matrix: office (a person without an organisation: her own office, the request names Private)
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
const toastTxt = d => [...d.querySelectorAll('#toast, .toast')].map(x => x.textContent).join(' ');
const srvWs = async (ck = CK) => (await call('GET', '/api/state', null, ck)).settings?.workspace;
// the window's own fetch wrapped: rule(url, opt) returns a Promise of a Response to answer instead, or null = through
const intercept = (w, rule) => { const f0 = w.fetch; w.fetch = (u, o = {}) => rule(String(u), o, () => f0(u, o)) || f0(u, o); return () => { w.fetch = f0; }; };
const isWsPatch = (u, o) => (o.method || 'GET') === 'PATCH' && /\/api\/settings\b/.test(u) && /"workspace"/.test(String(o.body || ''));

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
  check(A > 0 && Bo > 0, 'organisations Alpha and Bravo');
  const WA = 'org:' + A, WB = 'org:' + Bo;
  for (const [ws, nm] of [[WA, 'Alpha Studio GmbH'], [WB, 'Bravo Werkstatt GmbH']]) {
    const s = await call('PUT', '/api/office/settings', {company_fields: {name: nm, country: 'de'}, lang: 'en', currency: 'EUR'}, CK, {'X-Kalmido-Office-Space': ws});
    check(s.http < 300, 'setup: the office of ' + nm + ' ' + s.http);
  }
  const q = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Alpha Angebot', items: []}, CK, {'X-Kalmido-Office-Space': WA});
  check(q.http < 300, 'setup: a quotation in Alpha ' + q.http);
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= the split view's right half: the switch stays local, the server keeps "All"
  let w = await boot({path: '?split=1', hash: 'tasks', allWs: true}), d = w.document;
  check(w.eval('MW_GUARD') === true, 'the right half of the split view (MW_GUARD)');
  await w.eval(`wsSet('${WA}')`);
  check(w.eval('wsCur()') === WA && await srvWs() === 'all', 'right half on Alpha, the server still "All" (no PATCH leaves the right half) ' + await srvWs());
  w.eval("go('office/offers')");
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A && !w.eval('OFC.infoErr')), 'the office of Alpha opens, no error ' + (w.eval('OFC.infoErr') || ''));
  check(!/Select a workspace|Which workspace\?/i.test(viewTxt(d)), 'no "Which workspace?" with a workspace chosen ' + viewTxt(d).slice(0, 160));
  check(await until(() => /Alpha Angebot/.test(viewTxt(d))), 'the quotations load (Alpha Angebot) ' + viewTxt(d).slice(0, 160));
  check(w.eval('OFC.info.role') === 'admin' && w.eval('ofm_adm()') === true, 'the full menu: admin of Alpha');
  check(w.eval('ofm_ws()') === `${me.id}:${WA}`, 'the menu cache key is the office area ' + w.eval('ofm_ws()'));
  await w.eval('load()');
  check(w.eval('wsCur()') === WA, 'a state load keeps the right half on Alpha (no silent jump to "All") ' + w.eval('wsCur()'));
  // the menu on a page without the office loaded: its role asked with the area named (never the server's "All")
  w.eval("pb_reset(); OFM_ASKED.clear(); LS.set('ofmAdm', {}); go('clients')");
  check(await until(() => w.eval('ofm_adm()') === true), 'clients page in Alpha: the office menu knows the admin role (asked with the area)');
  w.close();

  // ================= "All > Alpha" fills the same menu cache as "Alpha"
  w = await boot({hash: 'office/s/' + WA, allWs: true}); d = w.document;
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A), '"All > Alpha" opens Alpha\'s office');
  check(w.eval('ofm_ws()') === `${me.id}:${WA}`, '"All > Alpha" uses the cache of Alpha ' + w.eval('ofm_ws()'));
  w.close();

  // ================= "Which workspace?" (no "at the top") with a button per workspace with an office
  w = await boot({hash: 'tasks', allWs: true}); d = w.document;
  w.eval("settingsModal('biz')");
  const nb = () => [...d.querySelectorAll('#s-biz [data-ofc="noarea"]')].map(b => b.dataset.ws).sort().join();
  check(await until(() => /Which workspace\?/.test(d.querySelector('#s-biz')?.textContent || '')), 'Settings > Company & office under "All" (two organisations): "Which workspace?" ' + (d.querySelector('#s-biz')?.textContent || '').slice(0, 160));
  check(!/at the top/i.test(d.querySelector('#s-biz')?.textContent || ''), 'the text names no "at the top"');
  check(await until(() => nb() === ['private', WA, WB].sort().join()), 'right under it a button per workspace with an office ' + nb());
  d.querySelector(`#s-biz [data-ofc="noarea"][data-ws="${WA}"]`).click();
  check(await until(() => w.eval('wsCur()') === WA && w.eval('OFC.info && OFC.info.org_id') === A && !!d.querySelector('#s-biz #ofc-set')), 'a click chooses Alpha and shows its office settings');
  check(await until(async () => await srvWs() === WA), 'and saves the workspace');
  check(!/Which workspace\?/.test(d.querySelector('#s-biz')?.textContent || ''), 'with a workspace chosen the question is gone');
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= main window: a state load overtakes the save of the switch
  w = await boot({hash: 'tasks', allWs: true}); d = w.document;
  let rel = null, held = 0;
  const off1 = intercept(w, (u, o, go) => { if (!isWsPatch(u, o)) return null; held++; return new Promise(res => { rel = res; }).then(go); });
  const sw = w.eval(`wsSet('${WA}')`);
  check(await until(() => held === 1), 'the save of the switch is on its way');
  await w.eval('load()');
  check(w.eval('wsCur()') === WA, 'a state load while the switch is being saved: still Alpha ' + w.eval('wsCur()'));
  off1();
  rel();  // the held save goes out now
  await sw;
  await w.eval('load()');
  check(w.eval('wsCur()') === WA && await srvWs() === WA, 'saved: Alpha here and on the server ' + await srvWs());
  w.eval("go('office/offers')");
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A && /Alpha Angebot/.test(viewTxt(d))), 'Alpha\'s office with its quotations');

  // ================= the save fails: taken back with a note
  const off2 = intercept(w, (u, o) => isWsPatch(u, o) ? Promise.resolve(new w.Response(JSON.stringify({error: 'boom'}), {status: 500, headers: {'Content-Type': 'application/json'}})) : null);
  await w.eval(`wsSet('${WB}')`);
  check(await until(() => w.eval('wsCur()') === WA), 'a failed save: back on Alpha ' + w.eval('wsCur()'));
  check(/could not be switched/i.test(toastTxt(d)), 'a failed save says so ' + toastTxt(d).slice(0, 160));
  off2();
  await w.eval('load()');
  check(w.eval('wsCur()') === WA && await srvWs() === WA, 'no half state: Alpha here and on the server');
  check(await until(() => w.eval('OFC.info && OFC.info.org_id') === A && !w.eval('OFC.infoErr')), 'the office stays usable (Alpha) ' + (w.eval('OFC.infoErr') || ''));
  w.close();

  // ================= a workspace really gone: a note, never silently
  const bu = await call('POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com', orgs: [{id: A, role: 'member'}, {id: Bo, role: 'member'}]});
  check(bu.http < 300, 'setup: bob in Alpha and Bravo ' + bu.http);
  const CB = await login('bob');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: WB}, CB);
  w = await boot({user: 'bob', hash: 'tasks', allWs: true}); d = w.document;
  check(w.eval('wsCur()') === WB, 'bob on Bravo');
  const rm = await call('DELETE', `/api/orgs/${Bo}/members/${bu.id}`);
  check(rm.http < 300, 'alice removes bob from Bravo ' + rm.http);
  await w.eval('load()');
  check(await until(() => w.eval('wsCur()') === 'all' && /no longer a member of Bravo/i.test(toastTxt(d))), 'Bravo gone: "All workspaces" with a note ' + toastTxt(d).slice(0, 160));
  check(await until(async () => await srvWs(CB) === 'all'), 'and saved');
  w.close();

  // ================= freelancer-matrix: a person without an organisation
  const fu = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fu.http < 300, 'a person without an organisation ' + fu.http);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, await login('frida'));
  w = await boot({user: 'frida', hash: 'office/offers'}); d = w.document;
  check(await until(() => w.eval('OFC.info && OFC.info.personal') && !w.eval('OFC.infoErr')), 'freelancer: her own office ' + (w.eval('OFC.infoErr') || ''));
  w.close();

  console.log(`p21437_7297_office_ws_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack); process.exit(1); });
