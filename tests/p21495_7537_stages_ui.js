// kalmido-suite: fresh
// 2.1495.0 (#7537) the stage line on top of a task's panel (envs.js stl_html). jsdom, own container (start.sh).
// - a project without repository and environments: no line, the panel as before
// - a project with a repository and the environments Staging / Live: created › in progress › built › version › Staging › Live ›
//   done; on a branch = in progress current, in main = built, released 1.2 with 1.2 on Staging = Staging current (by version,
//   with its date in the opened list), done = done current
// - parked with a reason: the reason at the current stage; rejected: "Rejected" current; reopened twice: "2× back"; with whom
// - phone width: the same line and stages (only the current one written out is CSS: device test); the opened list with dates
// The repository's build state comes from the git poll (tested in p2151_a_ui): here set in the page as the poll leaves it.
// freelancer-matrix: lists - alice has no organisation.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});  // the history of a task (its reopen lines)
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'kanban,collab,comments,fields'});
  const P = (await call('POST', '/api/lists', {name: 'App', kind: 'project'})).id;
  const Q = (await call('POST', '/api/lists', {name: 'Plain', kind: 'project'})).id;
  const ST = (await call('POST', `/api/lists/${P}/envs`, {name: 'Staging'})).id;
  const LV = (await call('POST', `/api/lists/${P}/envs`, {name: 'Live'})).id;
  check(ST && LV, 'two environments');
  check((await call('POST', `/api/envs/${ST}/deploy`, {version: '1.2'})).http < 300, 'version 1.2 on Staging');
  const mk = async (title, lid = P) => (await call('POST', '/api/tasks', {title, list_id: lid})).id;
  const T0 = await mk('Plain task', Q), TB = await mk('On a branch'), TM = await mk('In main'), TR = await mk('Released'), TD = await mk('Done one');
  const TP = await mk('Parked one'), TX = await mk('Rejected one'), TO = await mk('Reopened twice');
  await call('POST', `/api/tasks/${TD}/complete`, {});
  check((await call('PUT', `/api/tasks/${TP}/delivery`, {state: 'parked', note: 'waits for the bank'})).http < 300, 'parked with a reason');
  await call('POST', `/api/tasks/${TX}/complete`, {status: -1});
  for (let i = 0; i < 2; i++) { await call('POST', `/api/tasks/${TO}/complete`, {}); await call('POST', `/api/tasks/${TO}/reopen`, {}); }

  for (const mobile of [false, true]) {
    const w = await boot({user: 'alice', hash: `l/${P}`, mobile}), d = w.document;
    await until(() => w.eval(`!!taskById(${TB})`));
    // the repository as the git poll leaves it (list.repos, task.code.build)
    const build = {[TB]: {state: 'branch'}, [TM]: {state: 'main'}, [TR]: {state: 'released', version: '1.2'}, [TD]: {state: 'released', version: '1.0'},
      [TP]: {state: 'main'}, [TX]: {state: 'none'}, [TO]: {state: 'branch'}};
    const fake = () => w.eval(`(() => { const l = listById(${P}); l.repos = [{id: 1, full_name: 'acme/app', default_branch: 'main'}];
      for (const [id, b] of Object.entries(${JSON.stringify(build)})) { const t = taskById(+id); if (t) t.code = {prs: [], commits: [], build: b}; } })()`);
    const open = async id => {
      fake(); w.eval(`openDetail(${id})`);
      return until(() => { fake(); const s = d.querySelector('#detail #d-stages'); return s && w.eval(`S.sel === ${id}`) && s; });
    };
    const cur = () => d.querySelector('#detail #d-stages .stl-s.c');
    const tag = mobile ? 'phone' : 'desktop';

    w.eval(`openDetail(${T0})`);
    await until(() => d.querySelector('#detail #d-title'));
    await sleep(800);
    check(!d.querySelector('#detail #d-stages'), `${tag}: no repository, no environment: no stage line`);

    await open(TB);
    await until(() => d.querySelectorAll('#detail #d-stages .stl-s').length === 7);
    const names = [...d.querySelectorAll('#detail #d-stages .stl-s')].map(x => x.dataset.stage);
    check(JSON.stringify(names) === JSON.stringify(['created', 'progress', 'built', 'released', 'env', 'env', 'done']), `${tag}: the stages in order ${names}`);
    check(await until(() => cur()?.dataset.stage === 'progress'), `${tag}: on a branch = in progress ${txt(cur())}`);
    check(/With Alice|With nobody/.test(txt(cur())), `${tag}: with whom it lies ${txt(cur())}`);
    await open(TM);
    check(await until(() => cur()?.dataset.stage === 'built'), `${tag}: in main = built ${txt(cur())}`);
    await open(TR);
    check(await until(() => /Staging/.test(txt(cur()))), `${tag}: released 1.2 and 1.2 on Staging = Staging ${txt(cur())}`);
    check(d.querySelector('#detail #d-stages [data-stage="released"]')?.classList.contains('d') && /Version 1\.2/.test(txt(d.querySelector('#detail #d-stages'))),
      `${tag}: the version stage ticked with its number`);
    const sum = d.querySelector('#detail #d-stages > summary');
    sum.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
    const det = d.querySelector('#detail #d-stages');
    if (!det.open) det.open = true;  // jsdom: the summary toggles in a browser
    const lis = [...det.querySelectorAll('li')];
    check(lis.length === 7 && /Staging · .*now/.test(txt(lis[4])) && lis[6].classList.contains('o'), `${tag}: the opened line: every stage, the date, the current one ${lis.map(txt).join(' | ')}`);
    await open(TD);
    check(await until(() => cur()?.dataset.stage === 'done'), `${tag}: done = done current ${txt(cur())}`);
    await open(TP);
    check(await until(() => /Parked: waits for the bank/.test(txt(cur()))), `${tag}: parked with its reason at the current stage ${txt(cur())}`);
    await open(TX);
    check(await until(() => cur()?.dataset.stage === 'rejected' && cur().classList.contains('bad')), `${tag}: rejected ${txt(cur())}`);
    await open(TO);
    check(await until(() => /2× back/.test(txt(cur())), 20000), `${tag}: reopened twice = 2× back ${txt(cur())}`);
    w.close();
  }
  console.log(`p21495_7537_stages_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack); process.exit(1); });
