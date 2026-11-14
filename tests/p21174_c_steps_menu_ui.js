// 2.1174.0 UI test, part C (#6164): a phone's "…" menu of the header always has its own entry "Recent steps"
// kalmido-suite: fresh
// freelancer-matrix: undo (alice works without an organisation: the entry is for people, her steps are listed)
// Own container (start.sh; P21174C_NOSTART=1: it runs already), Firefox as a touch screen. Invented names only.
//  - 360 px: "…" opens the menu; "Recent steps" is there with nothing to undo in this browser, and no "Undo: …" above it
//  - after a change (a task renamed in the browser, a step of this browser): "Undo: …" is above "Recent steps", the entry stays
//  - a tap opens the page #steps with the step in the list (content visible); Back returns to the view before
//  - 1280 px (a mouse): the menu has no "Recent steps" entry (← and the account menu stay as they were)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21174_c_steps_menu_ui', check, shots: 'P21174C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21174C_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {tour: 'done', lang: 'en'});
  const lst = await call('POST', '/api/lists', {name: 'Garden plans'});
  const tsk = await call('POST', '/api/tasks', {list_id: lst.id, title: 'Water the tomatoes'});
  check(lst.id > 0 && tsk.id > 0, 'a list with a task');

  await firefox(async ({cmd, ev, nav: go, ctx, shot, until: wait}) => {
    await go(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');
    const labels = `JSON.stringify([...document.querySelectorAll('#pop .menu-list button')].map(b => b.textContent.trim().replace(/\\s+/g, ' ')))`;
    const openMenu = async () => {
      await ev(`(document.querySelector('#top [data-act="top-more"]').click(), 1)`);
      check(await wait(`!!document.querySelector('#pop .menu-list button')`, {timeout: 8000}), 'the "…" menu opens');
      return JSON.parse(await ev(labels));
    };
    const closeMenu = async () => { await ev(`(document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})), 1)`); await wait(`!document.querySelector('#pop .menu-list button')`, {timeout: 5000}); };
    const start = async W => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 760}});
      await go(B + '#l/' + lst.id);
      check(await wait(`!!document.querySelector('#view') && typeof topMoreItems === 'function' && S.route?.key === 'l:${lst.id}' && !!document.querySelector('#top [data-act="top-more"]')`, {timeout: 20000}), `${W}: the app is there`);
    };

    await start(360);
    check(await ev(`isMobile()`), '360: phone width');
    let L = await openMenu();
    check(L.some(x => /^Recent steps/.test(x)), '360: "Recent steps" is in the menu with nothing to undo ' + JSON.stringify(L));
    check(!L.some(x => /^Undo: /.test(x)), '360: no "Undo: …" yet ' + JSON.stringify(L));
    await closeMenu();

    // a step of this browser: rename the task through the app (the undo history of this browser gets an entry)
    check(await ev(`(async () => { const t = S.tasks.get(${tsk.id}); if (!t) return false; await patchUndoable(t.id, {title: 'Water the roses'}, 'Task renamed'); return true; })()`), '360: the task is renamed in the browser');
    await wait(`HIST.undo.length > 0`, {timeout: 8000});
    L = await openMenu();
    const iu = L.findIndex(x => /^Undo: /.test(x)), is = L.findIndex(x => /^Recent steps/.test(x));
    check(iu >= 0 && is > iu, '360: "Undo: …" above "Recent steps" ' + JSON.stringify(L));
    check(L.filter(x => /^Recent steps/.test(x)).length === 1, '360: the entry is there once ' + JSON.stringify(L));
    await shot('p21174c-menu-360.png');
    await ev(`(([...document.querySelectorAll('#pop .menu-list button')].find(b => /^Recent steps/.test(b.textContent.trim())).click()), 1)`);
    check(await wait(`location.hash === '#steps' && !!document.querySelector('#view .ulpage .ulrow')`, {timeout: 15000}), '360: the page #steps shows the steps (rows) ' + await ev(`location.hash`));
    check(/Recent steps/.test(await ev(`document.querySelector('#view .ulhead')?.textContent || ''`)), '360: the page has its title');
    check(/rename|Water|Title|Change|Task/i.test(await ev(`document.querySelector('#view .ulpage')?.textContent || ''`)), '360: the list names a step');
    await shot('p21174c-steps-360.png');
    await ev(`(history.back(), 1)`);
    check(await wait(`location.hash !== '#steps' && !document.querySelector('#view .ulpage')`, {timeout: 8000}), '360: Back returns to the view before ' + await ev(`location.hash`));

    await start(1280);
    check(!(await ev(`isMobile()`)), '1280: not a phone');
    L = await openMenu();
    check(!L.some(x => /^Recent steps/.test(x)), '1280: the menu has no "Recent steps" entry ' + JSON.stringify(L));
    await closeMenu();
  }, true);

  console.log(`p21174_c_steps_menu_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
