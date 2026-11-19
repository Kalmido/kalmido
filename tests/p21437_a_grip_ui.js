// #7293 UI test: the one grip to resize (static/js/grip.js + static/css/grip.css, docs/dev/kern.md "Resizing: the one grip").
// kalmido-suite: fresh
// Real Firefox (WebDriver BiDi), real pointer and key input. A test page inside the app (#gfx over the page) hangs one grip of
// each form: a column (rem, max as a function), a row (% of its box), the corner of a floating window (bl, fit to its content,
// stored through load / save hooks) and a centred dialog card (dialog mode, px), plus a column that takes over an old key.
// - loading: nothing of the module before the first call, the stand-in loads it (script + stylesheet) and gives the handle
// - mouse: a drag changes the size live (the variable on the nearest box, not the root; body.pgdrag during it), released it is
//   stored under grip:<key>; the max function counts at each drag; the keyboard (arrows, Shift, Home / End, Enter); a double
//   click = the default (forgotten); a tap = the menu (Wider); aria separator values; out of the way while a dialog is open
//   (a grip inside it stays)
// - the row (%), the corner bl (wider to the left, taller, never taller than its content, saved by the hook, not in LS), the
//   dialog card (both edges move, the grip follows at twice the speed), an old key taken over (LS and a raw kalmido.* key)
// - reload: every size is back; touch: a finger drags the column and the corner, a double tap = the default; phone width: no grip
// freelancer-matrix: n/a (no route; a client building block, the same without an organisation - alice has none)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21437_a_grip_ui', check, shots: 'P21437A_SHOTS', lazy: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (process.env.P21437A_NOSTART !== '1') execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };

// the test page: builds the boxes, hangs the grips (through the stand-ins of lazyload.js), returns what was there before
const FIX = `(async () => {
  const before = {ran: typeof LD_RAN !== 'undefined' && LD_RAN.has('grip'), live: typeof GRIP_LIVE !== 'undefined', stub: typeof grip_col === 'function'};
  document.getElementById('gfx')?.remove();
  const d = document.createElement('div'); d.id = 'gfx';
  d.style.cssText = 'position:fixed;inset:0;z-index:45;background:var(--bg)';
  const rows = Array.from({length: 10}, (_, i) => '<div style="height:2rem">row ' + (i + 1) + '</div>').join('');
  d.innerHTML = '<div id="gx-box" style="position:absolute;left:20px;top:20px;width:700px;height:120px;display:flex;border:1px solid #888">'
    + '<div id="gx-panel" style="width:var(--g-t-col, 15rem);flex:none;overflow:hidden">left</div><div id="gx-grip"></div><div style="flex:1;min-width:0">rest</div></div>'
    + '<div id="gl-box" style="position:absolute;left:20px;top:160px;width:700px;height:60px;display:flex;border:1px solid #888">'
    + '<div id="gl-panel" style="width:var(--g-t-leg, 12rem);flex:none">old key</div><div id="gl-grip"></div><div style="flex:1">rest</div></div>'
    + '<div id="gy-box" style="position:absolute;left:20px;top:240px;width:400px;height:402px;display:flex;flex-direction:column;border:1px solid #888">'
    + '<div id="gy-panel" style="height:var(--g-t-row, 30%);flex:none;overflow:hidden">top</div><div id="gy-grip"></div><div style="flex:1;min-height:0">bottom</div></div>'
    + '<div id="gc-win" style="position:absolute;right:20px;top:20px;width:var(--g-t-win-w, 16rem);height:var(--g-t-win-h, 10rem);border:1px solid #888;overflow:auto;box-sizing:border-box">'
    + '<div id="gc-in" style="height:20rem">' + rows + '</div></div>'
    + '<div id="gd-wrap"><div id="gd-card" style="position:absolute;left:50%;top:680px;transform:translateX(-50%);width:var(--g-t-dlg-w, 300px);height:var(--g-t-dlg-h, 150px);border:1px solid #888;box-sizing:border-box">card</div></div>';
  document.body.appendChild(d);
  const $i = id => document.getElementById(id);
  const gx = await grip_col($i('gx-grip'), {key: 't-col', min: 10, max: () => window.__gmax || 30, def: 15, label: 'Width of the test panel'});
  const gl = await grip_col($i('gl-grip'), {key: 't-leg', min: 8, max: 40, legacy: [{key: 'tleg.none'}, {key: 'tleg.side'}]});
  const gy = await grip_row($i('gy-grip'), {key: 't-row', unit: '%', min: 20, max: 80, def: 30});
  const gc = await grip_corner($i('gc-win'), {key: 't-win', at: 'bl', minW: 12, minH: 6, fit: true,
    load: () => { const v = sessionStorage.getItem('acct.t-win'); return v == null ? undefined : JSON.parse(v); },
    save: v => { window.__saves = (window.__saves || 0) + 1; sessionStorage.setItem('acct.t-win', JSON.stringify(v)); }});
  const gd = await grip_corner($i('gd-card'), {key: 't-dlg', mode: 'dialog', unit: 'px', minW: 300, minH: 150,
    legacy: {key: 'kalmido.dlgsize.tgrip', map: v => ({w: v.w, h: v.h})}});
  window.__g = {gx, gl, gy, gc, gd};
  return {before, ok: [gx, gl, gy, gc, gd].every(h => h && typeof h.set === 'function'), css: !!document.querySelector('link[data-ldcss="grip"]'),
    cur: getComputedStyle($i('gx-grip')).cursor, ran: LD_RAN.has('grip')};
})()`;
const BOX = id => `(() => { const r = document.getElementById('${id}').getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height, r: r.right, b: r.bottom, cx: r.left + r.width / 2, cy: r.top + r.height / 2}; })()`;
const VAR = (id, v) => `getComputedStyle(document.getElementById('${id}')).getPropertyValue('${v}').trim()`;
const LSV = k => `localStorage.getItem('${k}')`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en'});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});

  const open = async ({cmd, ev, nav, ctx, until}, W, Hh, clear) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Hh}});
    await nav(B + 'static/icon.svg');  // a real new load of the app each time (the same address with a hash would not reload)
    if (clear) {
      await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, `${W}: login`);
    }
    await nav(B + '#today');
    check(await until(`!!document.querySelector('#view') && typeof grip_col === 'function' && typeof menu === 'function'`, {timeout: 20000}), `${W}: the app is there`);
  };
  // a pointer pressed, moved (two steps), looked at while still pressed, then released
  const dragLook = async ({cmd, ev, ctx}, x0, y0, dx, dy, look, kind = 'mouse') => {
    const id = 'g' + kind;
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id, parameters: {pointerType: kind}, actions: [
      {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
      {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0 + dy / 2), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0 + dy), duration: 100}]}]});
    await sleep(80);  // the last move lands in the next frame (rafThrottle)
    const mid = look ? await ev(look) : null;
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id, parameters: {pointerType: kind}, actions: [{type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    await sleep(60);
    return mid;
  };
  const taps = async ({cmd, ctx}, x, y, n, kind = 'mouse') => {
    const one = [{type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}];
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 't' + kind, parameters: {pointerType: kind}, actions: [
      {type: 'pointerMove', x: Math.round(x), y: Math.round(y)}, ...one, ...(n > 1 ? [{type: 'pause', duration: 80}, ...one] : [])]}]});
    await cmd('input.releaseActions', {context: ctx});
  };
  const KEY = {ArrowRight: '', ArrowLeft: '', ArrowUp: '', ArrowDown: '', Home: '', End: '', Enter: '', Shift: '', Escape: ''};
  const press = async ({cmd, ev, ctx}, sel, k, shift) => {
    await ev(`(document.querySelector('${sel}').focus(), 1)`);
    const a = shift ? [{type: 'keyDown', value: KEY.Shift}, {type: 'keyDown', value: KEY[k]}, {type: 'keyUp', value: KEY[k]}, {type: 'keyUp', value: KEY.Shift}]
      : [{type: 'keyDown', value: KEY[k]}, {type: 'keyUp', value: KEY[k]}];
    await cmd('input.performActions', {context: ctx, actions: [{type: 'key', id: 'kb', actions: a}]});
    await cmd('input.releaseActions', {context: ctx});
  };
  const remOf = s => parseFloat(s) || 0;

  // ================================================================= mouse, 1280 px
  await firefox(async o => {
    const {ev, until, shot} = o;
    await open(o, 1280, 900, true);
    // an old size under two old keys of the column "t-leg" (the first one empty) and a raw kalmido.* key of the dialog card
    await ev(`(localStorage.setItem('tasks.tleg.side', '22'), localStorage.setItem('kalmido.dlgsize.tgrip', JSON.stringify({w: 420, h: 200})), 1)`);
    const f = await ev(FIX);
    check(!f.before.ran && !f.before.live && f.before.stub, 'loading: nothing of the module before the first call, only the stand-in ' + JSON.stringify(f));
    check(f.ok && f.ran && f.css && f.cur === 'col-resize', 'loading: the stand-in loads script + stylesheet and gives the handles ' + JSON.stringify(f));

    // ---- the old keys are taken over and go
    const lg = await ev(`({v: ${VAR('gl-box', '--g-t-leg')}, w: document.getElementById('gl-panel').getBoundingClientRect().width, nw: ${LSV('tasks.grip:t-leg')}, old: ${LSV('tasks.tleg.side')},
      d: __g.gd.get(), dn: ${LSV('tasks.grip:t-dlg')}, dold: ${LSV('kalmido.dlgsize.tgrip')}, dw: document.getElementById('gd-card').getBoundingClientRect().width})`);
    check(lg.v === '22rem' && Math.abs(lg.w - 352) <= 1 && lg.nw === '22' && lg.old === null, 'legacy: the old LS key is taken over (22rem) and removed ' + JSON.stringify(lg));
    check(lg.d && lg.d.w === 420 && lg.d.h === 200 && lg.dn && lg.dold === null && Math.abs(lg.dw - 420) <= 1, 'legacy: a raw kalmido.dlgsize key is taken over through map and removed ' + JSON.stringify(lg));
    await ev(`(__g.gd.reset(), 1)`);
    check(await ev(`__g.gd.get() === null && ${LSV('tasks.grip:t-dlg')} === null && ${LSV('kalmido.dlgsize.tgrip')} === null && Math.abs(document.getElementById('gd-card').getBoundingClientRect().width - 300) <= 1`), 'legacy: after a reset the old size does not come back');

    // ---- aria
    const ar = await ev(`(() => { const g = document.getElementById('gx-grip'); return {role: g.getAttribute('role'), or: g.getAttribute('aria-orientation'), now: g.getAttribute('aria-valuenow'), min: g.getAttribute('aria-valuemin'), max: g.getAttribute('aria-valuemax'), lbl: g.getAttribute('aria-label'), ti: g.tabIndex, key: g.dataset.grip}; })()`);
    check(ar.role === 'separator' && ar.or === 'vertical' && ar.now === '15' && ar.min === '10' && ar.max === '30' && ar.lbl === 'Width of the test panel' && ar.ti === 0 && ar.key === 't-col', 'aria: separator with value, min, max, label, focusable ' + JSON.stringify(ar));
    const ac = await ev(`(() => { const g = document.querySelector('#gc-win > .grip'); return {role: g?.getAttribute('role'), now: g?.getAttribute('aria-valuenow'), max: g?.getAttribute('aria-valuemax'), txt: g?.getAttribute('aria-valuetext')}; })()`);
    check(ac.role === 'separator' && ac.now === '16' && +ac.max > 16 && /16 rem × 10 rem/.test(ac.txt || ''), 'aria: the corner grip has its values too ' + JSON.stringify(ac));

    // ---- the column: a mouse drag, live on the nearest box
    let b = await ev(BOX('gx-grip'));
    check(Math.abs(b.x - 21 - 240) <= 1, 'column: the grip sits after the 15rem panel ' + JSON.stringify(b));
    const mid = await dragLook(o, b.cx, b.cy, 80, 0, `({box: document.getElementById('gx-box').style.getPropertyValue('--g-t-col'), root: document.documentElement.style.getPropertyValue('--g-t-col'),
      w: document.getElementById('gx-panel').getBoundingClientRect().width, cls: document.body.classList.contains('pgdrag'), cover: !!document.querySelector('.gcover.x'), ls: ${LSV('tasks.grip:t-col')}})`);
    check(mid && mid.box === '20rem' && !mid.root && Math.abs(mid.w - 320) <= 1 && mid.cls && mid.cover && mid.ls === null, 'column: during the drag the width follows live on the box, not the root, stored only on release ' + JSON.stringify(mid));
    const af = await ev(`({v: ${VAR('gx-box', '--g-t-col')}, ls: ${LSV('tasks.grip:t-col')}, cls: document.body.classList.contains('pgdrag'), cover: !!document.querySelector('.gcover'), now: document.getElementById('gx-grip').getAttribute('aria-valuenow')})`);
    check(af.v === '20rem' && af.ls === '20' && !af.cls && !af.cover && af.now === '20', 'column: released it is stored under grip:t-col, the drag marks are gone ' + JSON.stringify(af));
    // max as a function: 30 now, 24 on the next drag
    b = await ev(BOX('gx-grip'));
    await dragLook(o, b.cx, b.cy, 400, 0);
    check(await ev(VAR('gx-box', '--g-t-col')) === '30rem', 'column: the max function holds it at 30rem');
    await ev(`(window.__gmax = 24, 1)`);
    b = await ev(BOX('gx-grip'));
    await dragLook(o, b.cx, b.cy, 60, 0);
    check(await ev(VAR('gx-box', '--g-t-col')) === '24rem', 'column: the max function is asked again at the next drag (24rem)');
    await ev(`(window.__gmax = 30, 1)`);
    // the keyboard
    await o.ev(`(__g.gx.set(20), 1)`);
    await press(o, '#gx-grip', 'ArrowRight');
    check(await ev(VAR('gx-box', '--g-t-col')) === '21rem', 'keyboard: arrow right = 1rem wider');
    await press(o, '#gx-grip', 'ArrowLeft', true);
    check(await ev(VAR('gx-box', '--g-t-col')) === '17rem', 'keyboard: Shift + arrow left = 4rem narrower');
    await press(o, '#gx-grip', 'Home');
    check(await ev(VAR('gx-box', '--g-t-col')) === '10rem', 'keyboard: Home = the minimum');
    await press(o, '#gx-grip', 'End');
    check(await ev(`${VAR('gx-box', '--g-t-col')} === '30rem' && ${LSV('tasks.grip:t-col')} === '30'`), 'keyboard: End = the maximum, stored');
    await press(o, '#gx-grip', 'Enter');
    check(await ev(`${VAR('gx-box', '--g-t-col')} === '15rem' && ${LSV('tasks.grip:t-col')} === null`), 'keyboard: Enter = the default, nothing stored');
    // a double click = the default
    await ev(`(__g.gx.set(25), 1)`);
    b = await ev(BOX('gx-grip'));
    await taps(o, b.cx, b.cy, 2);
    check(await until(`${VAR('gx-box', '--g-t-col')} === '15rem' && ${LSV('tasks.grip:t-col')} === null`, {timeout: 3000}), 'mouse: a double click = the default width, forgotten');
    check(!await until(`!!document.querySelector('#pop:not(.hidden) .menu-list')`, {timeout: 700}), 'mouse: a double click opens no menu');
    // a tap = the menu, "Wider" = 4rem wider
    await taps(o, b.cx, b.cy, 1);
    const mi = await until(`[...document.querySelectorAll('#pop:not(.hidden) button, #pop:not(.hidden) [role="menuitem"]')].find(x => /Wider/.test(x.textContent))?.textContent.trim()`, {timeout: 3000});
    check(mi, 'mouse: a tap without dragging opens the menu with Wider / Narrower / Default width');
    await shot('p21437a-menu.png');
    if (mi) {
      await ev(`([...document.querySelectorAll('#pop:not(.hidden) button, #pop:not(.hidden) [role="menuitem"]')].find(x => /Wider/.test(x.textContent)).click(), 1)`);
      check(await until(`${VAR('gx-box', '--g-t-col')} === '19rem'`, {timeout: 3000}), 'mouse: Wider in the menu = 4rem wider');
    }
    await ev(`(typeof closePop === 'function' && closePop(), 1)`);

    // ---- out of the way while a dialog is open; a grip inside the dialog stays
    await ev(`(() => { const m = document.createElement('div'); m.className = 'modal'; m.id = 'gfx-modal'; m.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px'; document.body.appendChild(m); m.appendChild(document.getElementById('gd-wrap')); return 1; })()`);
    const vis = await ev(`({col: getComputedStyle(document.getElementById('gx-grip')).visibility, pe: getComputedStyle(document.getElementById('gx-grip')).pointerEvents, inside: getComputedStyle(document.querySelector('#gd-card > .grip')).visibility})`);
    check(vis.col === 'hidden' && vis.pe === 'none' && vis.inside === 'visible', 'a dialog is open: the grips step aside, the one inside the dialog stays ' + JSON.stringify(vis));
    await ev(`(() => { document.getElementById('gfx').appendChild(document.getElementById('gd-wrap')); document.getElementById('gfx-modal').remove(); return 1; })()`);
    check(await until(`getComputedStyle(document.getElementById('gx-grip')).visibility === 'visible'`, {timeout: 3000}), 'the dialog is closed: the grip is back');

    // ---- the row, in % of its box
    b = await ev(BOX('gy-grip'));
    check(Math.abs(b.y - 241 - 120) <= 1.5, 'row: the grip sits under the 30% panel ' + JSON.stringify(b));
    await dragLook(o, b.cx, b.cy, 0, 80);
    const ry = await ev(`({v: ${VAR('gy-box', '--g-t-row')}, h: document.getElementById('gy-panel').getBoundingClientRect().height, ls: ${LSV('tasks.grip:t-row')}, or: document.getElementById('gy-grip').getAttribute('aria-orientation')})`);
    check(ry.v === '50%' && Math.abs(ry.h - 200) <= 1 && ry.ls === '50' && ry.or === 'horizontal', 'row: dragged 80px down = 50% of the box, stored ' + JSON.stringify(ry));
    await press(o, '#gy-grip', 'ArrowUp');
    check(await ev(VAR('gy-box', '--g-t-row')) === '48%', 'row: arrow up = 2% shorter');

    // ---- the corner of a window hanging at the right (bl): wider to the left, taller; never taller than its content; the hook
    b = await ev(BOX('gc-win'));
    const cg = b;
    const gp = await ev(`(() => { const r = document.querySelector('#gc-win > .grip').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    check(Math.abs(cg.w - 256) <= 1 && Math.abs(cg.h - 160) <= 1 && gp.x < b.x + 24 && gp.y > b.b - 24, 'corner: the grip sits in the bottom left corner of the 16 x 10rem window ' + JSON.stringify([cg, gp]));
    const cm = await dragLook(o, gp.x, gp.y, -64, 48, `({w: document.getElementById('gc-win').getBoundingClientRect().width, cover: !!document.querySelector('.gcover.cbl')})`);
    const c1 = await ev(`({b: ${BOX('gc-win')}, v: __g.gc.get(), acct: sessionStorage.getItem('acct.t-win'), ls: ${LSV('tasks.grip:t-win')}, saves: window.__saves})`);
    check(cm && Math.abs(cm.w - 320) <= 1 && cm.cover, 'corner: the width follows live during the drag ' + JSON.stringify(cm));
    check(c1.v && c1.v.w === 20 && c1.v.h === 13 && Math.abs(c1.b.r - b.r) <= 1 && Math.abs(c1.b.w - 320) <= 1 && Math.abs(c1.b.h - 208) <= 1, 'corner: 4rem wider to the left, 3rem taller, the right edge stays ' + JSON.stringify(c1));
    check(c1.acct === JSON.stringify({w: 20, h: 13}) && c1.ls === null && c1.saves >= 1, 'corner: the save hook keeps it (not localStorage) ' + JSON.stringify(c1));
    const gp2 = await ev(`(() => { const r = document.querySelector('#gc-win > .grip').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    await dragLook(o, gp2.x, gp2.y, 0, 400);
    const c2 = await ev(`({v: __g.gc.get(), h: document.getElementById('gc-win').getBoundingClientRect().height, sh: document.getElementById('gc-in').getBoundingClientRect().height})`);
    check(c2.v && c2.v.h <= 20.25 && c2.v.h >= 19.75 && c2.h <= c2.sh + 4, 'corner (fit): never taller than its content (#4993) ' + JSON.stringify(c2));
    await press(o, '#gc-win > .grip', 'ArrowLeft');
    check(await ev(`__g.gc.get().w === 21`), 'corner bl: arrow left = 1rem wider');
    await shot('p21437a-mouse.png');

    // ---- the dialog card: both edges move, the grip follows at twice the speed
    b = await ev(BOX('gd-card'));
    const dp = await ev(`(() => { const r = document.querySelector('#gd-card > .grip').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    await dragLook(o, dp.x, dp.y, 40, 20);
    const d1 = await ev(BOX('gd-card'));
    check(Math.abs(d1.w - 380) <= 1 && Math.abs(d1.h - 190) <= 1 && Math.abs(d1.x - (b.x - 40)) <= 1 && Math.abs(d1.r - (b.r + 40)) <= 1, 'dialog: +40px = 80px wider, both edges move ' + JSON.stringify([b, d1]));
    check(await ev(`${LSV('tasks.grip:t-dlg')} === JSON.stringify({w: 380, h: 190})`), 'dialog: stored in px under grip:t-dlg');
    await press(o, '#gd-card > .grip', 'ArrowLeft');
    check(await ev(`__g.gd.get().w === 364`), 'dialog: arrow left = 16px narrower');

    // ---- reload: every size is back
    const want = await ev(`({col: ${VAR('gx-box', '--g-t-col')}, row: ${VAR('gy-box', '--g-t-row')}, win: JSON.stringify(__g.gc.get()), dlg: JSON.stringify(__g.gd.get()), leg: ${VAR('gl-box', '--g-t-leg')}})`);
    await open(o, 1280, 900, false);
    await ev(FIX);
    const got = await ev(`({col: ${VAR('gx-box', '--g-t-col')}, row: ${VAR('gy-box', '--g-t-row')}, win: JSON.stringify(__g.gc.get()), dlg: JSON.stringify(__g.gd.get()), leg: ${VAR('gl-box', '--g-t-leg')},
      ww: document.getElementById('gc-win').getBoundingClientRect().width, pw: document.getElementById('gx-panel').getBoundingClientRect().width})`);
    check(got.col === want.col && got.row === want.row && got.win === want.win && got.dlg === want.dlg && got.leg === '22rem' && Math.abs(got.ww - 336) <= 1 && Math.abs(got.pw - remOf(want.col) * 16) <= 1,
      'reload: every size is back (localStorage and the hook) ' + JSON.stringify([want, got]));

    // ---- phone width: no grip
    await o.cmd('browsingContext.setViewport', {context: o.ctx, viewport: {width: 460, height: 800}});
    check(await until(`['gx-grip', 'gy-grip'].every(id => getComputedStyle(document.getElementById(id)).display === 'none') && getComputedStyle(document.querySelector('#gc-win > .grip')).display === 'none'`, {timeout: 5000}),
      'phone width: the grips are gone');
    await ev(`(() => { const g = document.getElementById('gx-grip'); g.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true})); return 1; })()`);
    check(await ev(`${VAR('gx-box', '--g-t-col')} === ${JSON.stringify(want.col)}`), 'phone width: a key on the grip changes nothing');
    await shot('p21437a-phone.png');
  });

  // ================================================================= a finger (touch tablet), 1280 px
  await firefox(async o => {
    const {ev, until, shot} = o;
    await open(o, 1280, 900, true);
    await ev(FIX);
    let b = await ev(BOX('gx-grip'));
    const tw = await ev(`({w: getComputedStyle(document.getElementById('gx-grip')).width, coarse: matchMedia('(pointer:coarse)').matches})`);
    check(tw.coarse && tw.w === '16px', 'touch: a wider grip for the finger ' + JSON.stringify(tw));
    const mid = await dragLook(o, b.cx, b.cy, 80, 0, `document.getElementById('gx-panel').getBoundingClientRect().width`, 'touch');
    check(Math.abs(mid - 320) <= 1, 'touch: the column follows the finger live ' + mid);
    check(await ev(`${VAR('gx-box', '--g-t-col')} === '20rem' && ${LSV('tasks.grip:t-col')} === '20'`), 'touch: dragged with a finger, stored');
    b = await ev(BOX('gx-grip'));
    await taps(o, b.cx, b.cy, 2, 'touch');
    check(await until(`${VAR('gx-box', '--g-t-col')} === '15rem' && ${LSV('tasks.grip:t-col')} === null`, {timeout: 3000}), 'touch: a double tap = the default width');
    const gp = await ev(`(() => { const r = document.querySelector('#gc-win > .grip').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width}; })()`);
    check(gp.w === 28, 'touch: the corner grip is bigger for the finger ' + gp.w);
    await dragLook(o, gp.x, gp.y, -64, 32, null, 'touch');
    check(await ev(`JSON.stringify(__g.gc.get()) === JSON.stringify({w: 20, h: 12})`), 'touch: the corner of the window follows the finger ' + await ev(`JSON.stringify(__g.gc.get())`));
    await shot('p21437a-touch.png');
  }, true);

  console.log(`p21437_a_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
