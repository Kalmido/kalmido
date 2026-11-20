// #7328 UI test, own container (start.sh, mode workspaces). jsdom, invented data only.
// kalmido-suite: fresh
// The workspace on top changes only by the person's tap on the switch, or with a visible note with "Back":
// - a favourite of the office under "All workspaces" opens its office at its address (#office/s/<area>/...): "All" stays,
//   here and on the server (was: wsSet to the organisation); the browser's Back leads back
// - the same link under a chosen workspace (Private) opens the other workspace's office at its address, the switch stays
//   Private; a link inside it keeps the area (forward), Back returns (usability: in, on, back); the chip still says Private
// - core.js ofc_link: an area other than the one on top = its address, the one on top = the plain address (devlink.js, life.js)
// - the workspace switched from outside (another device): this device says it once ("Switched to ...") with "Back", and
//   Back brings the one before (saved)
// - Settings > Reset (the sidebar included) leaves the workspace alone
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, undoToast} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
let CK;
const call = async (method, url, body, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const srvWs = async () => (await call('GET', '/api/state')).settings?.workspace || 'all';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients'});
  const me = (await call('GET', '/api/state')).me.id;
  const A = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me})).id, WA = 'org:' + A;
  check(A > 0, 'setup: the organisation Alpha');
  await call('POST', '/api/office/services', {name_de: 'Eigene Leistung'}, {'X-Kalmido-Office-Space': 'private'});  // the own office holds data
  const q = await call('POST', '/api/office/docs', {kind: 'offer', project_title: 'Alpha Film'}, {'X-Kalmido-Office-Space': WA});
  check(q.id > 0, 'setup: a quotation in Alpha ' + q.http);
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ---- 1. under "All": a favourite of Alpha's office opens it at its address, "All" stays
  let w = await boot({user: 'alice', hash: 'cal', allWs: true});
  await until(() => w.eval('S.booted') && w.eval('S.route.mod') === 'cal');
  await w.eval(`fv2_goWs('${WA}', 'office/offers/${q.id}', true)`);
  check(await until(() => w.location.hash === `#office/s/${WA}/offers/${q.id}` && w.eval('OFC.info && OFC.info.org_id') === A),
    '#7328: the office favourite opens Alpha at its address ' + w.location.hash);
  check(w.eval('wsCur()') === 'all' && await srvWs() === 'all', '#7328: "All workspaces" stays (here and on the server) ' + w.eval('wsCur()'));
  w.history.back();
  check(await until(() => w.location.hash === '#cal'), "the browser's Back leads back " + w.location.hash);
  check(w.eval('wsCur()') === 'all', 'still "All" after Back');

  // ---- 2. under Private: the other workspace's office by its address, the switch stays; in, on, back
  await w.eval("wsSet('private')");
  check(await until(async () => await srvWs() === 'private'), 'a tap on the switch: Private (saved)');
  check(w.eval(`ofc_link('equipment', '${WA}')`) === `office/s/${WA}/equipment` && w.eval("ofc_link('equipment', 'private')") === 'office/equipment',
    '#7328: ofc_link under a chosen workspace: another area = its address, the own one = the plain address');
  await w.eval(`fv2_goWs('${WA}', 'office/offers/${q.id}', true)`);
  check(await until(() => w.location.hash === `#office/s/${WA}/offers/${q.id}` && w.eval('OFC.info && OFC.info.org_id') === A),
    '#7328: under Private the link opens Alpha\'s office (in) ' + w.location.hash + ' ' + w.eval('OFC.info && OFC.info.org_id'));
  check(w.eval('wsCur()') === 'private' && await srvWs() === 'private', '#7328: the switch stays Private');
  w.eval("go('office/invoices')");
  check(await until(() => w.location.hash === `#office/s/${WA}/invoices` && w.eval('S.route.wsp') === WA), '#7328: a link inside keeps the area (on) ' + w.location.hash);
  w.history.back();
  check(await until(() => w.location.hash === `#office/s/${WA}/offers/${q.id}`), '#7328: Back returns to the quotation (back) ' + w.location.hash);
  check(!w.document.querySelector('#view [data-ofcall="up"]'), 'no "All workspaces /" under a chosen workspace');
  w.eval("go('office')");
  check(await until(() => w.location.hash === `#office/s/${WA}` || w.location.hash === '#office'), 'the office root ' + w.location.hash);

  // ---- 3. switched from outside (another device): one note with Back
  w.eval("go('cal')");
  await until(() => w.eval('S.route.mod') === 'cal');
  await call('PATCH', '/api/settings', {workspace: WA});
  await w.eval('load()');
  check(await until(() => w.eval('wsCur()') === WA), 'the state brings Alpha');
  check(await undoToast(w, /Switched to Alpha/), '#7328: the device says it once, with Back');
  check(await until(() => w.eval('wsCur()') === 'private') && await until(async () => await srvWs() === 'private'), '#7328: Back brings Private (saved)');
  await w.eval('load()');
  await sleep(400);
  const t = w.document.querySelector('#toast');
  check(!t || t.classList.contains('hidden') || !/Switched to/.test(t.textContent), '#7328: no second note for the own Back');
  w.close();

  // ---- 4. a reset of the sidebar keeps the workspace
  const rs = await call('POST', '/api/settings/reset', {});  // every look and comfort setting, the sidebar's too
  check(rs.http < 300, 'reset of the settings ' + rs.http);
  check(await srvWs() === 'private', '#7328: the reset (sidebar included) leaves the workspace ' + await srvWs());

  console.log(`p7328_ws_stays_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
