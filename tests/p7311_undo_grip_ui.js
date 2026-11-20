// #7311 UI test: the window "Recent steps" (the ← button) gets bigger by the one grip in its corner, like the bell (grip.js,
// docs/dev/kern.md "Resizing: the one grip").
// kalmido-suite: fresh
// freelancer-matrix: undo (alice works without an organisation; the grip is a client building block, the same in every workspace)
// Own container (start.sh), Firefox 1280 x 900 (mouse, real pointer input), invented names only. Usability:
// - nothing to undo here: the arrow's click opens "Recent steps"; it hangs under the arrow at the top right, in its lower left
//   corner sits a grip (separator, focusable, data-grip undo-win); the window is 30rem wide
// - dragging the corner to the left and down makes the window wider and taller live, its right edge stays under the arrow;
//   released it is kept on the device (grip:undo-win), set on the
//   window (not the root); the list fills the dragged height (no 34rem cap) and still scrolls; its rows still work
// - closed and opened again: the same size; a double click on the grip: the default again, nothing stored
// - dragged far: it stops inside the browser window (left and bottom edge)
// - phone width: the sheet, no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7311_undo_grip_ui', check, shots: 'P7311_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

const M = `JSON.stringify((() => {
  const p = document.querySelector('#pop:not(.hidden).ulwin'), win = p?.querySelector('.ulpop'), body = p?.querySelector('.ulbody');
  const g = win?.querySelector(':scope > .grip'), r = g?.getBoundingClientRect(), pr = p?.getBoundingClientRect();
  return {open: !!p, sheet: !!p && p.classList.contains('sheet'), w: Math.round(pr?.width || 0), h: Math.round(pr?.height || 0), right: Math.round(pr?.right || 0), left: Math.round(pr?.left || 0), bottom: Math.round(pr?.bottom || 0),
    bh: Math.round(body?.getBoundingClientRect().height || 0), rows: p ? p.querySelectorAll('.ulrow').length : 0,
    grip: !!g, role: g?.getAttribute('role'), key: g?.dataset.grip, ti: g ? g.tabIndex : null, gx: r ? r.left + r.width / 2 : 0, gy: r ? r.top + r.height / 2 : 0,
    v: win?.style.getPropertyValue('--g-undo-win-w') || '', root: document.documentElement.style.getPropertyValue('--g-undo-win-w'),
    ls: localStorage.getItem('tasks.grip:undo-win'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize), iw: innerWidth, ih: innerHeight};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const st = await call(CA, 'GET', '/api/state');
  check(!(st.me.workspaces || []).length, 'alice works without an organisation');
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Garden'})).id;
  for (let i = 0; i < 12; i++) await call(CA, 'POST', '/api/tasks', {list_id: L, title: `Plant row ${i + 1}`});  // steps for the list
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);

  await firefox(async o => {
    const {cmd, ev, nav, ctx, shot, until, idle} = o;
    const get = async () => JSON.parse(await ev(M));
    const load = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      await nav(B + 'static/icon.svg');  // a real new load of the app
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#l/' + L); await idle();
      check(await until(`!!document.querySelector('#top [data-act="hist-undo"]')`, {timeout: 20000}), `${W}: the arrow`);
    };
    const open = async () => {
      await ev(`(document.querySelector('#top [data-act="hist-undo"]').click(), 1)`);
      return until(`document.querySelectorAll('#pop:not(.hidden).ulwin .ulrow').length >= 10`, {timeout: 10000});
    };
    const drag = async (x0, y0, dx, dy, look) => {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0 + dy / 2), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0 + dy), duration: 100}]}]});
      await sleep(80);  // the last move lands in the next frame (rafThrottle)
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await sleep(60);
      return mid;
    };

    await load(1280, true);
    check(await open(), 'the arrow\'s click opens "Recent steps" with the steps');
    check(await until(`!!document.querySelector('#pop:not(.hidden).ulwin .ulpop > .grip')`, {timeout: 8000}), 'the grip is in the window');
    const g0 = await get();
    check(g0.role === 'separator' && g0.key === 'undo-win' && g0.ti === 0, 'the grip: a focusable separator named undo-win ' + JSON.stringify(g0));
    check(Math.abs(g0.w - 30 * g0.rem) <= 2 && g0.ls == null, 'nothing stored: the window is 30rem wide ' + JSON.stringify(g0));
    check(await ev(`(() => { const e = document.elementFromPoint(${g0.gx}, ${g0.gy}); return !!e && e.classList.contains('grip'); })()`), 'the pointer reaches the grip (nothing lies over it)');
    check(g0.gx < g0.left + 30, 'the grip sits in the lower left corner ' + JSON.stringify(g0));
    const mid = await drag(g0.gx, g0.gy, -160, 120, `JSON.stringify({w: Math.round(document.querySelector('#pop').getBoundingClientRect().width), ls: localStorage.getItem('tasks.grip:undo-win')})`);
    const m = JSON.parse(mid || '{}');
    check(Math.abs(m.w - (g0.w + 160)) <= 4 && m.ls == null, 'during the drag the window follows live, nothing stored yet ' + mid);
    const g1 = await get();
    check(Math.abs(g1.right - g0.right) <= 2, 'the right edge stays under the arrow ' + JSON.stringify([g0.right, g1.right]));
    check(Math.abs(g1.w - (g0.w + 160)) <= 4 && Math.abs(g1.h - (g0.h + 120)) <= 4 && /^\d+(\.\d+)?rem$/.test(g1.v) && !g1.root && /"w":\d/.test(g1.ls || ''),
      'released: 10rem wider and 7.5rem taller, kept under grip:undo-win on the window, not the root ' + JSON.stringify(g1));
    check(g1.bh > g0.bh + 100, 'the list fills the dragged height ' + JSON.stringify([g0.bh, g1.bh]));
    await shot('p7311-wide.png');
    // the rows still work: "Back up to here" is a button in the list
    check(await ev(`!!document.querySelector('#pop .ulrow [data-ul-go]')`), 'the rows keep their buttons');
    // closed and opened again: the same size
    await ev(`(closePop(), 1)`);
    check(await open(), 'opened again');
    await until(`!!document.querySelector('#pop:not(.hidden).ulwin .ulpop > .grip')`, {timeout: 8000});
    const g2 = await get();
    check(Math.abs(g2.w - g1.w) <= 2 && Math.abs(g2.h - g1.h) <= 2, 'opened again: the kept size ' + JSON.stringify([g1.w, g1.h, g2.w, g2.h]));
    // dragged far: it stops inside the browser window
    await drag(g2.gx, g2.gy, -(g2.gx - 2), g2.ih - g2.gy - 2);
    const g3 = await get();
    check(g3.left >= 8 && g3.bottom <= g3.ih - 8 && Math.abs(g3.right - g2.right) <= 2 && g3.w > g2.w, 'dragged far: the window stays inside the browser window ' + JSON.stringify(g3));
    // a double click on the grip: the default again, nothing stored
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
      {type: 'pointerMove', x: Math.round(g3.gx), y: Math.round(g3.gy)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}, {type: 'pause', duration: 80}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    check(await until(`localStorage.getItem('tasks.grip:undo-win') === null && Math.abs(document.querySelector('#pop').getBoundingClientRect().width - 30 * ${g3.rem}) <= 2`, {timeout: 3000}),
      'a double click: 30rem again, nothing stored ' + JSON.stringify(await get()));
    await ev(`(closePop(), 1)`);
    // phone width: the sheet, no grip
    await load(390, false);
    await ev(`(ul_open(document.querySelector('#top [data-act="hist-undo"]') || document.body), 1)`);  // the long press on the arrow
    check(await until(`document.querySelectorAll('#pop:not(.hidden).ulwin .ulrow').length >= 10`, {timeout: 10000}), 'phone: the list opens');
    const g4 = await get();
    check(g4.sheet && !g4.grip, 'phone: the sheet, no grip ' + JSON.stringify(g4));
  });

  console.log(`p7311_undo_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
