// #7305 UI test: the cell details beside a table get wider by the one grip (grip.js, docs/dev/kern.md "Resizing: the one grip";
// key sheets-side, --g-sheets-side on .shvbody).
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1280 x 900 (mouse, real pointer input), a person WITHOUT an organisation (a private table;
// freelancer-matrix: sheets), invented content only. Usability:
// - between the table and the cell details sits a focusable separator (data-grip sheets-side); the details are 17.5rem
// - dragged to the left the details get wider live, released the width is kept (grip:sheets-side) on .shvbody, not the root;
//   typing into a cell (a redraw) keeps width and grip; the table's corner grip is untouched
// - dragged far: no fixed cap, the table keeps 14rem; a reload keeps the width; Enter on the grip: 17.5rem, nothing stored
// - phone width: the details under the table, no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7305_sheet_side_grip_ui', check, shots: 'P7305_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

const M = `JSON.stringify((() => {
  const w = s => Math.round(document.querySelector(s)?.getBoundingClientRect().width || 0);
  const b = document.querySelector('.shvbody'), g = document.querySelector('.shvbody > .shvsgrip'), r = g?.getBoundingClientRect();
  return {side: w('#shv-side'), grid: w('.shvbody > .shvgridw'), body: b ? b.clientWidth : 0, grip: !!g && g.classList.contains('grip'), role: g?.getAttribute('role'), key: g?.dataset.grip,
    ti: g ? g.tabIndex : null, gx: r ? r.left + r.width / 2 : 0, gy: r ? r.top + Math.min(r.height / 2, 80) : 0, gw: r ? Math.round(r.width) : 0,
    v: b?.style.getPropertyValue('--g-sheets-side') || '', root: document.documentElement.style.getPropertyValue('--g-sheets-side'),
    ls: localStorage.getItem('tasks.grip:sheets-side'), shz: !!document.querySelector('.shzgrip'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['sheets']});
  await call(CA, 'POST', '/api/users', {orgs: [], username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'sheets', workspace: 'private'});
  const S1 = await call(CF, 'POST', '/api/sheets', {title: 'Drehtage Budget', space: 'private'});
  check(S1.http < 300 && S1.id, 'setup: a private table ' + S1.http);
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, nav, ctx, shot, until, idle}) => {
    const get = async () => JSON.parse(await ev(M));
    const open = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      await nav(B + 'static/icon.svg');
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#sheets/' + S1.id); await idle();
      check(await until(`!!document.querySelector('#shv-scroll') && !!document.querySelector('#shv-side')`, {timeout: 20000}), `${W}: the table and its details`);
    };
    const drag = async (x0, y0, dx, look) => {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0), duration: 100}]}]});
      await sleep(80);
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await sleep(60);
      return mid;
    };

    await open(1280, true);
    check(await until(`!!document.querySelector('.shvbody > .shvsgrip.grip')`, {timeout: 8000}), 'the grip is there');
    const g0 = await get();
    check(g0.role === 'separator' && g0.key === 'sheets-side' && g0.ti === 0 && g0.gw >= 8, 'a focusable separator named sheets-side ' + JSON.stringify(g0));
    check(Math.abs(g0.side - 17.5 * g0.rem) <= 2 && g0.ls == null, 'nothing stored: the details are 17.5rem ' + JSON.stringify(g0));
    check(await ev(`(() => { const e = document.elementFromPoint(${g0.gx}, ${g0.gy}); return !!e && e.classList.contains('shvsgrip'); })()`), 'the pointer reaches the grip');
    const mid = JSON.parse(await drag(g0.gx, g0.gy, -128, `JSON.stringify({s: Math.round(document.querySelector('#shv-side').getBoundingClientRect().width), ls: localStorage.getItem('tasks.grip:sheets-side')})`) || '{}');
    check(Math.abs(mid.s - (g0.side + 128)) <= 3 && mid.ls == null, 'during the drag the details follow live, nothing stored yet ' + JSON.stringify(mid));
    const g1 = await get();
    check(Math.abs(g1.side - (g0.side + 128)) <= 3 && g1.ls === '25.5' && g1.v === '25.5rem' && !g1.root, 'released: 8rem wider (25.5rem), kept on .shvbody, not the root ' + JSON.stringify(g1));
    await shot('p7305-wide.png');
    // a cell typed into: the sheet redraws, width and grip stay
    await ev(`(() => { const c = document.querySelector('#shv-scroll td[data-c]'); c?.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); c?.dispatchEvent(new MouseEvent('click', {bubbles: true})); return 1; })()`);
    await ev(`(shvRender(), 1)`); await idle();
    const g2 = await get();
    check(g2.grip && Math.abs(g2.side - g1.side) <= 1, 'a redraw keeps the width and the grip ' + JSON.stringify(g2));
    // far: no fixed cap, the table keeps 14rem
    await drag(g2.gx, g2.gy, -(g2.gx - 10));
    const g3 = await get();
    check(g3.side > g3.body / 2 && g3.grid >= 14 * g3.rem - 2, 'dragged far: the details go past half, the table keeps 14rem ' + JSON.stringify(g3));
    await ev(`(localStorage.setItem('tasks.grip:sheets-side', '24'), 1)`);
    await open(1280, false);
    check(await until(`!!document.querySelector('.shvbody > .shvsgrip.grip')`, {timeout: 8000}), 'reload: the grip again');
    const g4 = await get();
    check(Math.abs(g4.side - 24 * g4.rem) <= 2, 'reload: the kept width (24rem) ' + JSON.stringify(g4));
    await ev(`(() => { const g = document.querySelector('.shvbody > .shvsgrip'); g.focus(); g.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})); return 1; })()`);
    const g5 = await get();
    check(g5.ls == null && Math.abs(g5.side - 17.5 * g5.rem) <= 2, 'Enter on the grip: 17.5rem again, nothing stored ' + JSON.stringify(g5));
    // phone: details under the table, no grip
    await open(390, false);
    const g6 = await get();
    check(!g6.gx && g6.side > 300, 'phone: the details under the table, no grip ' + JSON.stringify(g6));
  });

  console.log(`p7305_sheet_side_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
