// kalmido-suite: fresh
// #7563 UI test (decision of 20.11.2026): Home is off in every organisation as long as nobody switches it on there (the default
// of ws_areas_off, accounts/wsareas.py wsa_own). Own container (start.sh), jsdom at a computer's width, invented names only.
// - Alice (Private + the organisation Alpha without Home data), "All workspaces": Home opens Private directly - no overview of
//   the workspaces in between; the page shows Private's Home
// - Settings > Modules > Areas per workspace: Home in Alpha is shown switched off, with the normal switch (not locked);
//   switched on there, Home under "All" shows the overview with Private and Alpha (a tap on Alpha opens it, back to the
//   overview); switched off again, Home opens Private directly again
// - freelancer-matrix: navigation (Solo without an organisation: Home opens directly, no workspace switch in Settings)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,contracts,home,care,travel,family,files,wiki';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'all'});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const A = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  check(A > 0, 'setup: the organisation Alpha (no Home data)');
  const WA = 'org:' + A;

  let w = await boot({hash: 'tasks', allWs: true}), d = w.document;
  check(await until(() => w.eval(`wsOn() && wsCur() === 'all'`)), 'Alice: "All workspaces" with an organisation');
  check(w.eval(`JSON.parse(S.settings.ws_areas_off)[${JSON.stringify(WA)}]?.join()`) === 'life', '#7563 the setting as it applies: Home off in Alpha (the server\'s default)');
  check(w.eval(`mod_spaces('life', null).join()`) === 'private', '#7563 Home is on in Private only ' + w.eval(`mod_spaces('life', null).join()`));
  // the menu entry: Home opens Private directly
  w.location.hash = '#life';
  check(await until(() => w.eval(`S.route?.mod === 'life'`) && d.querySelector('#view .life')), '#7563 Home opens');
  check(!d.querySelector('#view .spov, #view [data-spov]') && w.eval(`rd_space()`) === 'private', '#7563 ... directly in Private, no overview of the workspaces ' + w.eval(`rd_space()`));
  // Settings > Modules: Home in Alpha switched off, with the normal switch
  w.eval(`settingsModal('modules')`);
  const sw = () => d.querySelector(`.smodal input[data-wsa="life"][data-wsaws="${WA}"]`);
  check(await until(() => sw()), '#7563 Settings > Modules shows Home per workspace');
  check(sw() && !sw().checked && !sw().disabled, '#7563 Home in Alpha: switched off, the switch can be used');
  check(d.querySelector('.smodal input[data-wsa="life"][data-wsaws="private"]')?.checked, '#7563 Home in Private: on as before');
  // switch it on (as a person: a click on the switch)
  sw().click();
  check(await until(() => w.eval(`mod_spaces('life', null).join()`) === `private,${WA}`), '#7563 switched on: Home is on in Alpha too ' + w.eval(`mod_spaces('life', null).join()`));
  check(await until(() => w.eval(`(JSON.parse(S.settings.ws_areas_off)[${JSON.stringify(WA)}] || ['x']).length === 0`)), '#7563 the choice is kept as an empty list for Alpha');
  const st = await call(CA, 'GET', '/api/state');
  check(JSON.parse(st.settings.ws_areas_off)[WA]?.length === 0 && st.wsp.travel.includes(WA), '#7563 the server keeps it (a new load: Home on in Alpha)');
  w.eval(`typeof closeModal === 'function' && closeModal(); 1`);
  for (const m of [...d.querySelectorAll('.smodal')]) m.remove();
  w.location.hash = '#tasks';
  await until(() => w.eval(`S.route?.mod === 'tasks'`));
  w.location.hash = '#life';
  check(await until(() => d.querySelector(`#view [data-spov="private"]`) && d.querySelector(`#view [data-spov="${WA}"]`)), '#7563 Home under "All" now shows the overview with Private and Alpha');
  w.location.hash = d.querySelector(`#view [data-spov="${WA}"]`).getAttribute('href');
  check(await until(() => w.eval(`rd_space()`) === WA && !d.querySelector('#view [data-spov]')), '#7563 a tap on Alpha opens Alpha\'s Home');
  w.location.hash = '#life';
  check(await until(() => d.querySelector(`#view [data-spov="${WA}"]`)), '#7563 back to the overview');
  // and off again: directly Private
  const o = JSON.parse(w.eval(`S.settings.ws_areas_off`)); o[WA] = ['life'];
  await w.eval(`setApply({ws_areas_off: ${JSON.stringify(JSON.stringify(o))}}, 'off')`);
  check(await until(() => w.eval(`mod_spaces('life', null).join()`) === 'private'), '#7563 switched off again: Private only');
  w.location.hash = '#tasks'; await until(() => w.eval(`S.route?.mod === 'tasks'`));
  w.location.hash = '#life';
  check(await until(() => d.querySelector('#view .life') && !d.querySelector('#view [data-spov]')), '#7563 Home opens Private directly again');
  w.close();

  // ================= Solo without an organisation
  await call(CA, 'POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call(CS, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  w = await boot({user: 'solo', hash: 'life'}); d = w.document;
  check(await until(() => w.eval(`S.route?.mod === 'life'`) && d.querySelector('#view .life')), 'solo: Home opens');
  check(!d.querySelector('#view [data-spov]') && w.eval(`S.settings.ws_areas_off`) === '{}', 'solo: directly, no default key (P4)');
  w.close();

  console.log(`p7563_home_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
