// kalmido-suite: fresh
// #7336 UI test (regression): the arrow of an office area in the panel opens its tree under "All workspaces" too. Own
// container (start.sh), jsdom at a computer's width, invented data only. Alice: Private + the organisations Alpha and Bravo.
// - "All", the office's overview (no office open): Quotations opens to one node per office (Private, Alpha, Bravo); Alpha's
//   node opens to its folder, its 20 newest quotations and More…, each link keeps the office (#office/s/<space>/...); the
//   arrows close again. Invoices, Documents, Correspondence, Receipts open the same way (their trees load without an error)
//   (before: the tree was loaded without the office, the server answered 400, the node opened to nothing)
// - "All" with an office open (#office/s/org:<Alpha>): the tree of Alpha; then #office/s/private: Private's own tree (before:
//   one cache per workspace, the other office's or the failed tree stayed)
// - one workspace (Alpha chosen on top): the tree as before
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route (Person ohne Organisation: p2351_a_officetree_ui)
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
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,office,clients,files,docs';
const LS = {'tasks.sbbUnfold': '["office:money"]', 'tasks.ofmAll': 'true'};  // every point shown, Money open (Receipts)

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
  check(A > 0 && Bo > 0, 'setup: organisations Alpha and Bravo');
  const WA = 'org:' + A, WB = 'org:' + Bo;
  await call('PATCH', '/api/settings', {workspace: 'all'});
  const QA = [];
  for (let i = 0; i < 22; i++) QA.push((await call('POST', '/api/office/docs', {kind: 'offer', items: [{title: `Alpha day ${i}`, qty: 1, rate: 100 + i}]}, WA)).id);
  check(QA.every(Boolean), 'setup: 22 quotations in Alpha');
  const FA = (await call('POST', '/api/office/docs/tree/folders', {name: 'Alpha folder'}, WA)).folder?.id;
  const QP = (await call('POST', '/api/office/docs', {kind: 'offer', items: [{title: 'Private day', qty: 1, rate: 90}]}, 'private')).id;
  check(FA && QP, 'setup: a folder in Alpha, a quotation in Private');
  check((await call('GET', '/api/office/docs/tree')).http === 400, 'setup: under "All" without the office the tree route answers 400 (the cause of #7336)');

  const arrow = (d, k) => [...d.querySelectorAll('#side [data-act="sbb-tree"]')].find(b => b.dataset.k === k);
  const toggle = (d, k, open) => { const a = arrow(d, k); if (!a) return false; if (!!a.dataset.open !== open) a.click(); return true; };
  const spNodes = d => [...d.querySelectorAll('#side [data-oftsp]')].map(x => x.dataset.oftsp).join();

  // ================= "All", the office's overview
  let w = await boot({hash: 'office/offers', allWs: true, ls: LS}), d = w.document;
  check(await until(() => w.eval('typeof ofc_allOvr === "function" && ofc_allOvr()') && arrow(d, 'of:a:offers')), 'overview: Quotations has its arrow');
  toggle(d, 'of:a:offers', true);
  check(await until(() => spNodes(d) === `private,${WA},${WB}`), 'overview: the arrow opens Quotations to Private, Alpha, Bravo ' + spNodes(d));
  check(arrow(d, 'of:a:offers')?.getAttribute('aria-expanded') === 'true', 'overview: the arrow says open');
  toggle(d, `of:s:${WA}:offers`, true);
  const alphaDocs = () => [...d.querySelectorAll('#side [data-oftspdoc^="offers:"]')];
  check(await until(() => alphaDocs().length === 20 && [...d.querySelectorAll('#side .sbbtn .n')].some(n => n.textContent === 'Alpha folder')),
    'overview: Alpha opens to its folder and its 20 newest quotations ' + alphaDocs().length);
  const more = await until(() => d.querySelector(`#side [data-oftmore="offers"]`));
  check(more && more.dataset.go === `office/s/${WA}/offers`, 'overview: More… opens Alpha\'s list ' + more?.dataset.go);
  const g0 = alphaDocs()[0]?.querySelector('.sbbtn')?.dataset.go || '';
  check(new RegExp(`^office/s/${WA}/offers/\\d+$`).test(g0), 'overview: a quotation\'s link keeps the office ' + g0);
  alphaDocs()[0].querySelector('.sbbtn').click();
  check(await until(() => w.location.hash === '#' + g0 && w.eval('S.route.wsp') === WA), 'overview: the quotation opens in Alpha ' + w.location.hash);
  w.location.hash = '#office';  // the overview again (#office/offers inside an open office keeps that office, core.js)
  check(await until(() => w.eval('ofc_allOvr()') && alphaDocs().length === 20), 'back on the overview: Alpha stays open');
  toggle(d, `of:s:${WA}:offers`, false);
  check(await until(() => !alphaDocs().length && !d.querySelector('#side [data-oftmore]')), 'overview: Alpha closes again');
  toggle(d, 'of:a:offers', false);
  check(await until(() => !spNodes(d)), 'overview: Quotations closes again');
  // the other areas of the office: the same nodes, their trees load without an error
  for (const area of ['invoices', 'gendocs', 'letters', 'receipts']) {
    if (!await until(() => arrow(d, 'of:a:' + area), 20)) { check(area !== 'invoices', `overview: ${area} is not in the panel`); continue; }
    toggle(d, 'of:a:' + area, true);
    check(await until(() => arrow(d, `of:s:${WA}:${area}`)), `overview: ${area} opens to the offices`);
    toggle(d, `of:s:${WA}:${area}`, true);
    check(await until(() => w.eval(`Object.entries(OFT.ov).some(([k, v]) => k.endsWith('${WA}|${area}') && !v.err)`)), `overview: Alpha's tree of ${area} loads without an error`);
    toggle(d, 'of:a:' + area, false);
  }
  w.close();

  // ================= "All" with an office open: its own tree, never the other office's
  w = await boot({hash: `office/s/${WA}/offers`, allWs: true, ls: LS}); d = w.document;
  const node = id => d.querySelector(`#side .sbbt[data-sbbid="${id}"]`);
  check(await until(() => arrow(d, 'of:a:offers')), 'Alpha open: Quotations has its arrow');
  toggle(d, 'of:a:offers', true);
  check(await until(() => node('f:offers:' + FA) && node('d:offers:' + QA[21])), 'Alpha open: its folder and its newest quotation');
  w.location.hash = '#office/s/private/offers';
  check(await until(() => node('d:offers:' + QP) && !node('f:offers:' + FA) && !node('d:offers:' + QA[21])), 'Private open: Private\'s tree, not Alpha\'s');
  w.close();

  // ================= one workspace on top (Alpha)
  await call('PATCH', '/api/settings', {workspace: WA});
  w = await boot({hash: 'office/offers', allWs: true, ls: {...LS, 'tasks.sbbOpen': '["of:a:offers"]'}}); d = w.document;
  check(await until(() => node('f:offers:' + FA) && node('d:offers:' + QA[21]) && !node('d:offers:' + QP)), 'workspace Alpha: the tree opens with Alpha\'s folder and quotations');
  toggle(d, 'of:a:offers', false);
  check(await until(() => !node('f:offers:' + FA)), 'workspace Alpha: closes again');
  w.close();

  console.log(`p7336_officetree_all_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
