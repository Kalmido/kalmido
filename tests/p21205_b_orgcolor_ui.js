// kalmido-suite: fresh
// Package 2.1205.0 (#6179) UI test: the organisation colour as one building block of the core (wscolor.js wso_row, wso_origin,
// wso_open, wso_sync; docs/dev/kern.md "Organisation colour"). Rule (owner decision 14.11.2026): what belongs to an organisation wears its
// colour in every area - its entry (a stripe on the left edge) and the open object (#main.wsc-on, under "All" #view.wac-loc);
// Private stays neutral. The projects use the block (behaviour as before); an area registers its open object with wso_open and
// gets the same marks, also when it draws the object later (renderView). A person without an organisation: nothing coloured.
// freelancer-matrix: n/a - nur Oberfläche (Person ohne Organisation in der Datei geprüft)
// jsdom (classes / variables) + Firefox at 1280 (the stripe as drawn).
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21205_b_orgcolor_ui', check, shots: 'P21205B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio', lang: 'en', collab_all: true, modules: ['comments']});
  check(su.http < 300, 'setup: the organisation Studio ' + JSON.stringify(su));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', ws_colors: '{}', workspace: 'all'});
  const st = await call('GET', '/api/state'), ORG = (st.me.workspaces || [])[0]?.id;
  if (!ORG) { console.log('no organisation', JSON.stringify(st.me)); process.exit(1); }
  check((await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'})).http === 200, 'setup: the admins set the organisation colour');
  const WL = (await call('POST', '/api/lists', {name: 'Website', org_id: ORG})).id;
  const PL = (await call('POST', '/api/lists', {name: 'Garden', org_id: null})).id;
  check(WL && PL, 'setup: a project of the organisation and a private one');

  // ================= jsdom, "All workspaces"
  let w = await boot({hash: 'l/' + WL}), d = w.document;
  const main = () => d.querySelector('#main'), view = () => d.querySelector('#view');
  const want = w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return {d: t[0], l: t[1], wad: wac_fit(t[0], false)}; })()`);
  const marked = () => main().classList.contains('wsc-on') && main().style.getPropertyValue('--wsd') === want.d && main().style.getPropertyValue('--wsl') === want.l;
  const toned = () => view().classList.contains('wac-loc') && view().style.getPropertyValue('--wad') === want.wad;
  // the projects on the block: behaviour as before
  check(await until(() => marked()), '#6179 an open project of the organisation: #main.wsc-on in its colour (as before)');
  check(toned(), '#6179 "All": its view wears the organisation\'s tone (wac-loc, as before)');
  const srow = d.querySelector(`#side .srow[data-list="${WL}"]`);
  check(srow?.dataset.wsc === '1' && srow?.dataset.wso === '1' && srow.style.getPropertyValue('--wsd') === want.d, '#6179 its sidebar row: the shared row mark (data-wso + data-wsc + the tone)');
  check(!d.querySelector(`#side .srow[data-list="${PL}"]`)?.dataset.wsc, '#6179 a private project\'s row stays neutral');
  w.eval(`go('l/${PL}')`);
  check(await until(() => !main().classList.contains('wsc-on')), '#6179 an open private project: no organisation mark');
  // the block's parts
  check(/data-wso="1" data-wsc="1" style="--wsd:/.test(w.eval(`wso_row(${ORG})`)) && w.eval(`wso_row('org:${ORG}')`) === w.eval(`wso_row(${ORG})`) && w.eval(`wso_row({org_id: ${ORG}})`) === w.eval(`wso_row(${ORG})`), '#6179 wso_row: an id, a workspace key and an object give the same mark');
  check(w.eval(`wso_row('private') + wso_row(null) + wso_row(0) + wso_row({org_id: null})`) === '', '#6179 wso_row: Private / nothing stays neutral');
  const og = w.eval(`wso_origin(${ORG}, 'mymeta')`);
  check(/class="wso mymeta"/.test(og) && /Studio/.test(og) && /wsp-dot/.test(og) && /Workspace: Studio/.test(og), '#6179 wso_origin under "All": dot + name + the name for screen readers ' + og);
  check(w.eval(`ws_originHtml(listById(${WL}), 'Website', 'lst')`).includes(w.eval(`wso_head('org:${ORG}')`)), '#6179 the task rows\' origin (ws_originHtml) is built from the same head');
  // an area registers its open object
  w.eval(`window.T6179 = null; wso_open('t6179', () => S.route.mod === 'home' ? window.T6179 : null)`);
  w.eval(`go('home')`);
  await until(() => w.eval(`S.route.mod === 'home'`));
  check(!main().classList.contains('wsc-on'), '#6179 an area without an open object: no mark');
  // the object arrives later (a load): the next redraw of the view marks it (renderView, not only render)
  w.eval(`window.T6179 = {org_id: ${ORG}}; renderView()`);
  check(await until(() => marked()), '#6179 an area\'s object of the organisation, drawn later: #main.wsc-on (renderView)');
  check(toned(), '#6179 "All": the area\'s view wears the organisation\'s tone');
  w.eval(`window.T6179 = 'private'; renderView()`);
  check(await until(() => !main().classList.contains('wsc-on') && !view().classList.contains('wac-loc')), '#6179 the area\'s private object: neutral again');
  w.eval(`window.T6179 = null`);
  w.close();

  // ================= one workspace: no origin mark (it says nothing there)
  await call('PATCH', '/api/settings', {workspace: 'org:' + ORG});
  w = await boot({hash: 'l/' + WL}); d = w.document;
  await until(() => d.querySelector('#side .srow'));
  check(w.eval(`wso_origin(${ORG})`) === '', '#6179 inside one workspace: no origin mark');
  check(await until(() => d.querySelector('#main').classList.contains('wsc-on')), '#6179 inside the organisation: the open project still marked');
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= Firefox: the stripe as drawn
  await firefox(async ({cmd, ev, ctx, nav, shot, until: fu}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'ff: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + '?w=1280#l/' + PL);
    check(await fu(`!!document.querySelector('#side .srow[data-list="${WL}"]')`, {timeout: 20000}), 'ff: the projects');
    const r = await ev(`(() => { const box = document.createElement('div'); box.id = 't6179'; box.innerHTML = '<div class="card" ' + wso_row(${ORG}) + '>Org card</div><div class="card" ' + wso_row('private') + '>Private card</div>'; document.querySelector('#view').prepend(box);
      const [a, b] = box.children, s = document.querySelector('#side .srow[data-list="${WL}"]');
      return {org: getComputedStyle(a).boxShadow, prv: getComputedStyle(b).boxShadow, side: getComputedStyle(s).boxShadow, sideBg: getComputedStyle(s).backgroundImage}; })()`);
    check(r && /inset/.test(r.org) && /133, 96, 15/.test(r.org), `#6179 an entry of the organisation: the 3 px stripe in its tone (light) ${JSON.stringify(r)}`);
    check(r && (r.prv === 'none' || !/inset/.test(r.prv)), '#6179 a private entry: no stripe');
    check(r && !/inset/.test(r.side) && /gradient/.test(r.sideBg), '#6179 the sidebar row keeps its own stripe (no second one)');
    await shot('p21205b-rows.png');
  });

  // ================= a person without an organisation: nothing coloured
  await call('POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, CS);
  const SL = (await call('POST', '/api/lists', {name: 'Own project'}, CS)).id;
  w = await boot({user: 'solo', hash: 'l/' + SL}); d = w.document;
  await until(() => d.querySelector('#side .srow'));
  check(!d.querySelector('#main').classList.contains('wsc-on') && !d.querySelector('#view').classList.contains('wac-loc'), '#6179 without an organisation: the open project neutral');
  check(w.eval(`wso_row(5) + wso_origin(5)`) === '', '#6179 without an organisation: no row mark, no origin');
  w.close();

  console.log(`p21205_b_orgcolor_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
