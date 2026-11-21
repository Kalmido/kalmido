// kalmido-suite: fresh
// #7661 UI test (decision of 20.11.2026, replaces "Private stays neutral" of #6179): as soon as the person has an organisation,
// Private wears its colour at the same places as an organisation - one rule in the core (static/js/wscolor.js wso_vars), no
// caller decides. Own container (start.sh), jsdom at a computer's width, invented names only.
// - Alice (Private + the organisation Alpha), "All workspaces": the overview of the workspaces in Office, Files, Knowledge and
//   Reading (and the Workload's, the same spo_html): the Private row carries data-wso in Private's default colour (Kalmido's
//   accent, var(--acc-d)), Alpha's row its own; "Recently edited", "Shared with me" and the trash stay neutral. A tap on the
//   Private row opens the private space, back leads to the overview again
// - my own colour for Private (Settings > Workspaces) wins over the default in the same rows
// - freelancer-matrix: navigation (Solo without an organisation: no workspace row is marked, nothing coloured)
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
const FEAT = 'cal,comments,collab,office,clients,files,docs,wiki,reading,feeds';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, ws_colors: '{}', workspace: 'all'});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const A = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  check(A > 0, 'setup: the organisation Alpha');
  check((await call(CA, 'PATCH', '/api/orgs/' + A, {color: '#e0b05c'})).http === 200, 'setup: Alpha\'s colour');
  const WA = 'org:' + A;

  const row = (d, sp) => d.querySelector(`#view [data-spov="${sp}"]`) || d.querySelector(`#view [data-wksp="${sp}"]`);
  const privd = (el, wsd = 'var(--acc-d)') => !!el && el.dataset.wso === '1' && el.dataset.wsc === '1' && el.style.getPropertyValue('--wsd') === wsd;
  const neutral = el => !el || (!el.dataset.wso && !el.style.getPropertyValue('--wsd'));

  // ================= Alice, a computer, "All workspaces"
  let w = await boot({hash: 'tasks', allWs: true}), d = w.document;
  check(await until(() => w.eval(`wsOn() && wsCur() === 'all'`)), 'Alice: "All workspaces" with an organisation');
  const tone = w.eval(`WSC_TONES[wsc_ix(wsOrg(${A}).color, ${A})][0]`);
  const AREAS = [['Office', 'office', 'office/s/private'], ['Files', 'ablage', 'ablage/s/private'], ['Knowledge', 'wiki', 'wiki/s/private'], ['Reading', 'bookmarks', 'bookmarks/s/private']];
  for (const [name, hash, open] of AREAS) {
    w.location.hash = '#' + hash;
    const fresh = () => row(d, 'private')?.getAttribute('href') === '#' + open && row(d, WA);  // the overview of THIS area
    const seen = await until(fresh);
    check(seen, `${name}: the overview shows Private and Alpha ` + (seen ? '' : (d.querySelector('#view')?.textContent || '').slice(0, 160)));
    if (!seen) continue;
    check(privd(row(d, 'private')), `${name}: the Private row wears Private's colour (data-wso) ` + row(d, 'private').outerHTML.slice(0, 200));
    check(privd(row(d, WA), tone), `${name}: Alpha's row wears Alpha's colour`);
    for (const sp of ['shared', 'trash']) check(neutral(row(d, sp)), `${name}: "${sp}" is no workspace and stays neutral`);
    check(neutral(d.querySelector('#view [data-zlego]')), `${name}: "Recently edited" stays neutral`);
    // as a person: into the private space and back
    const a = row(d, 'private');
    w.location.hash = a.getAttribute('href') || '#' + open;
    check(await until(() => w.eval(`location.hash`) === '#' + open && !row(d, WA)), `${name}: a tap on Private opens the private space ` + w.eval('location.hash'));
    check(await until(() => d.querySelector('#main')?.classList.contains('wsc-on') && d.querySelector('#main').style.getPropertyValue('--wsd') === 'var(--acc-d)')
      || name === 'Reading', `${name}: the open private space wears Private's colour (#main.wsc-on)`);
    w.location.hash = '#' + hash;
    check(await until(fresh), `${name}: back to the overview`);
  }
  // the Workload's overview is spo_html too (its private row: the absences)
  const wl = w.eval(`(() => { const x = document.createElement('div'); x.innerHTML = spo_html('workload', tm_rows({personal: 1, orgs: [{id: ${A}, name: 'Alpha'}]}, true)); return x; })()`);
  check(privd(wl.querySelector('[data-spov="private"]')) && privd(wl.querySelector(`[data-spov="${WA}"]`), tone), 'Workload: the overview\'s Private row and Alpha\'s row are marked the same way');
  // my own colour for Private wins
  await call(CA, 'PATCH', '/api/settings', {ws_colors: JSON.stringify({private: 'orange'})});
  w.close();
  w = await boot({hash: 'ablage', allWs: true}); d = w.document;
  const orange = w.eval(`LP_TONES.find(x => x[0] === 'orange')[2]`);
  check(await until(() => privd(row(d, 'private'), orange)), 'my own Private colour (orange) on the Private row of Files');
  check(w.eval(`wso_row('private')`).includes('--wsd:' + orange), 'wso_row: my own Private colour');
  w.close();
  await call(CA, 'PATCH', '/api/settings', {ws_colors: '{}'});

  // ================= Solo without an organisation: nothing coloured
  await call(CA, 'POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call(CS, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check((await call(CS, 'POST', '/api/wiki/pages', {space: 'private', path: 'Own notes', body: 'Mine.'})).id, 'solo: a private wiki page');
  w = await boot({user: 'solo', hash: 'ablage'}); d = w.document;
  check(await until(() => w.eval(`typeof S !== 'undefined' && !!S.booted`)), 'solo: the app is up');
  check(w.eval(`!wsOn() && wso_row('private') === '' && wso_origin('private', '', true) === ''`), 'solo: Private stays neutral without an organisation');
  for (const hash of ['ablage', 'wiki', 'office']) {
    w.location.hash = '#' + hash;
    await until(() => w.eval(`S.route?.mod`) === (hash === 'ablage' ? 'ablage' : hash));
    await sleep(300);
    check(!d.querySelector('#view [data-wso], #side [data-wso]') && !d.querySelector('#main.wsc-on'), `solo: ${hash}: no workspace row marked, no frame colour`);
  }
  w.close();

  console.log(`p7661_privcolor_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
