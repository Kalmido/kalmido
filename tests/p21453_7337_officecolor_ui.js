// kalmido-suite: fresh
// Package 2.1453.0 (#7337) UI test: quotations and invoices wear the colour of their workspace (the core's wso_row, no colour of
// their own) - the row of the list, the card of the pipeline and the document in the panel's tree. An organisation's office: its
// stripe; Private: its colour (my own, else the default var(--acc-d)), also inside the workspace Private.
// Ersetzt Entscheidung #6957 ("Private only under All"): gedeckt durch #7661 (20.11.2026, Private wears its colour everywhere).
// Own container (start.sh), jsdom at a computer's width, invented data only. Alice: Private + the organisation Alpha (a colour).
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route (Person ohne Organisation: wsOn() false, wso_row gibt nichts; p2351_a_officetree_ui)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, sp) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK, ...(sp ? {'X-Kalmido-Office-Space': sp} : {})}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), http: r.status};
  }
};
const until = fn => require('./boot').until(fn, {timeout: 15000, step: 150});
const FEAT = 'cal,comments,collab,office,clients,files,docs,pipeline';
const LS = {'tasks.ofmAll': 'true', 'tasks.sbbOpen': '["of:a:offers"]'};

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, ws_colors: JSON.stringify({private: 'red'})});
  const me = (await call('GET', '/api/state')).me;
  const A = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  check(A > 0, 'setup: organisation Alpha');
  check((await call('PATCH', '/api/orgs/' + A, {color: '#e0b05c'})).http === 200, 'setup: Alpha\'s colour');
  const WA = 'org:' + A;
  await call('PATCH', '/api/settings', {workspace: 'all'});
  const QA = (await call('POST', '/api/office/docs', {kind: 'offer', items: [{title: 'Alpha day', qty: 1, rate: 100}]}, WA)).id;
  const QP = (await call('POST', '/api/office/docs', {kind: 'offer', items: [{title: 'Private day', qty: 1, rate: 90}]}, 'private')).id;
  const DA = (await call('POST', '/api/office/deals', {title: 'Alpha film', value: 1000, stage: 'inquiry'}, WA)).id;
  check(QA && QP && DA, 'setup: a quotation in Alpha and in Private, a deal in Alpha');

  const stripe = el => el && el.dataset.wso === '1' ? el.style.getPropertyValue('--wsd') : '';
  const rowOf = (d, id) => d.querySelector(`#view .ofdrow[data-id="${id}"]`);
  const treeDoc = (d, id) => d.querySelector(`#side .sbbt[data-sbbid="d:offers:${id}"]`);
  let w, d, alpha, red;
  const tones = () => { alpha = w.eval(`WSC_TONES[wsc_ix(wsOrg(${A}).color, ${A})][0]`); red = w.eval(`LP_TONES.find(x => x[0] === 'red')[2]`); };

  // ================= the workspace Alpha on top: rows, tree and cards in Alpha's colour
  await call('PATCH', '/api/settings', {workspace: WA});
  w = await boot({hash: 'office/offers', allWs: true, ls: LS}); d = w.document; tones();
  check(await until(() => rowOf(d, QA)), 'Alpha: the quotation is listed');
  check(stripe(rowOf(d, QA)) === alpha, '#7337 Alpha: the quotation row wears Alpha\'s stripe ' + stripe(rowOf(d, QA)));
  check(await until(() => treeDoc(d, QA)), 'Alpha: the panel\'s tree shows the quotation');
  check(stripe(treeDoc(d, QA)) === alpha, '#7337 Alpha: the tree\'s quotation wears Alpha\'s stripe');
  rowOf(d, QA).click();
  check(await until(() => w.eval('S.route.id') === QA), 'Alpha: a tap on the row opens the quotation');
  w.eval(`go('office/pipeline')`);
  const card = () => [...d.querySelectorAll('#view .ppcard')].find(c => c.textContent.includes('Alpha film'));
  check(await until(() => card()), 'Alpha: the pipeline shows the deal');
  check(stripe(card()) === alpha, '#7337 Alpha: the pipeline card wears Alpha\'s stripe');
  w.close();

  // ================= the workspace Private on top: Private's colour like an organisation's inside its own workspace (#7661)
  await call('PATCH', '/api/settings', {workspace: 'private'});
  w = await boot({hash: 'office/offers', allWs: true, ls: LS}); d = w.document; tones();
  check(await until(() => rowOf(d, QP)), 'Private: the quotation is listed');
  check(stripe(rowOf(d, QP)) === red, '#7661 (was #7337 neutral): Private: the row wears my Private colour ' + stripe(rowOf(d, QP)));
  check(await until(() => treeDoc(d, QP)) && [red, ''].includes(stripe(treeDoc(d, QP))), '#7337 / #7389 Private: the tree\'s quotation (below the workspace row, which carries the stripe) ' + stripe(treeDoc(d, QP)));
  w.close();

  // ================= "All": the Private office open - Private in my colour; Alpha's office open - Alpha's colour
  await call('PATCH', '/api/settings', {workspace: 'all'});
  w = await boot({hash: 'office/s/private/offers', allWs: true, ls: LS}); d = w.document; tones();
  check(await until(() => rowOf(d, QP)), 'All, Private open: the quotation is listed');
  check(stripe(rowOf(d, QP)) === red, '#7337 All: the private row wears my Private colour ' + stripe(rowOf(d, QP)));
  w.location.hash = `#office/s/${WA}/offers`;
  check(await until(() => rowOf(d, QA) && !rowOf(d, QP)), 'All, Alpha open: Alpha\'s quotation is listed');
  check(stripe(rowOf(d, QA)) === alpha, '#7337 All: Alpha\'s row wears Alpha\'s stripe');
  w.close();

  console.log(`p21453_7337_officecolor_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
