// kalmido-suite: fresh
// 2.1501.0 C UI test (#7533): a task from a comment of a sign-off, own container (start.sh), jsdom. Invented names and links only.
// - the sign-off of a project opens; its comment has "Task from it"; a click makes the task: the comment shows "Task: <text>"
//   with its state, the button is gone; Undo of the step moves the task into the trash (the comment says "Task deleted"),
//   Redo brings it back
// - "Task: …" opens the task's panel, which names the sign-off it came from ("From the sign-off …"); that line opens the sign-off
// - a reader of the project sees the task at the comment but no "Task from it"
// freelancer-matrix: videos (alice works in her private space without an organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21501C_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,clients,videos';

(async () => {
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const bob = await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com', orgs: []});
  const CB = await login('bob');
  for (const ck of [CA, CB]) await call(ck, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Spring film'})).id;
  await call(CA, 'PUT', `/api/lists/${L}/members`, {user_id: bob.id, role: 'view'});
  const R = await call(CA, 'POST', '/api/videos', {list_id: L, title: 'Spot 30s', url: 'https://vimeo.com/123456789'});
  check(R.http === 201 || R.http === 200, 'a sign-off at the project ' + R.http);
  const C1 = (await call(CA, 'POST', `/api/videos/${R.id}/comments`, {version_id: R.versions[0].id, at_sec: 42, body: 'Logo two frames later'})).comment_id;

  let w = await boot({user: 'alice', hash: 'l/' + L}), d = w.document;
  const open = async () => { await w.eval(`loadModule('videos').then(() => vdr_open(${R.id}))`); return until(() => d.querySelector(`.vdrc[data-cid="${C1}"]`)); };
  check(await open(), 'the sign-off opens with its comment');
  const cm = () => d.querySelector(`.vdrc[data-cid="${C1}"]`);
  const mk = () => cm()?.querySelector('[data-vdr="mktask"]');
  check(mk() && /Task from it/.test(mk().textContent), '"Task from it" at the comment');
  click(w, mk());
  check(await until(() => /Task: Logo two frames later/.test(cm()?.querySelector('.vdrtask')?.textContent || '') && !mk()), 'the comment shows its task, the button is gone ' + (cm()?.querySelector('.vdrtask')?.textContent || ''));
  check(/Open/.test(cm().querySelector('.vdrtask .rotag')?.textContent || ''), 'with its state (Open)');
  const tid = await until(async () => (await call(CA, 'GET', `/api/videos/${R.id}`)).comments.find(c => c.id === C1)?.task?.id);
  check(tid > 0, 'the server knows the task ' + tid);
  // undo / redo of the step
  await w.eval("histStep('undo')");
  const undone = await until(async () => (await call(CA, 'GET', `/api/videos/${R.id}`)).comments.find(c => c.id === C1)?.task?.gone);
  check(undone && await until(() => /Task deleted/.test(cm()?.textContent || '')), 'Undo: the task into the trash, the comment says so');
  await w.eval("histStep('redo')");
  check(await until(async () => (await call(CA, 'GET', `/api/videos/${R.id}`)).comments.find(c => c.id === C1)?.task?.id === tid), 'Redo: the task back');
  check(await until(() => cm()?.querySelector('[data-vdr="task"]')), 'the task at the comment again');
  // the task's panel names the sign-off
  click(w, cm().querySelector('[data-vdr="task"]'));
  check(await until(() => w.eval(`S.sel === ${tid}`)), 'a click on the task opens its panel');
  check(await until(() => /From the sign-off “Spot 30s”/.test(d.querySelector('#d-vdr .vdrfrom')?.textContent || ''), 20000), 'the task names the sign-off it came from');
  click(w, d.querySelector('#d-vdr .vdrfrom'));
  check(await until(() => d.querySelector(`.vdrc[data-cid="${C1}"]`)), 'that line opens the sign-off again');
  check(errs.length === 0, 'no script errors: ' + errs.join(' | '));
  w.close();

  // a reader of the project
  w = await boot({user: 'bob', hash: 'l/' + L}); d = w.document;
  check(await open(), 'bob opens the sign-off');
  check(cm().querySelector('[data-vdr="task"]') && !mk(), 'a reader sees the task, no "Task from it"');
  w.close();

  console.log(`p21501_c_review_task_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
