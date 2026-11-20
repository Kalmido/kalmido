// #7307 UI test: the sidebar folded into the drawer (side-rail) takes the remembered sidebar width and has the same grip as the
// fixed sidebar (one key pw.side, one width for both states, at most 80 % of the window).
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1280 x 860 (mouse, real pointer input), a person WITHOUT an organisation (freelancer-matrix:
// tasks), invented names only. Usability:
// - the fixed sidebar dragged to 20rem; folded by hand (sideFold): the drawer opened by the menu button is 20rem wide too
// - the open drawer has its grip on the right edge (#pgrip-side, a separator); dragged right the drawer gets wider live, released
//   the width is kept (pw.side); the drawer stays open; dragged far it stops at 80 % of the window
// - closed: no grip; unfolded: the fixed sidebar has the drawer's width
// - phone width: the drawer keeps its own width (not pw.side), no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7307_drawer_grip_ui', check, shots: 'P7307_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

const M = `JSON.stringify((() => {
  const s = document.querySelector('#side'), r = s.getBoundingClientRect(), g = document.querySelector('#pgrip-side'), gr = g && !g.hidden ? g.getBoundingClientRect() : null;
  return {rail: document.querySelector('#app').classList.contains('side-rail'), open: s.classList.contains('open'), w: Math.round(r.width), right: Math.round(r.right),
    grip: !!gr && getComputedStyle(g).visibility === 'visible', gx: gr ? gr.left + gr.width / 2 : 0, gy: gr ? gr.top + Math.min(gr.height / 2, 200) : 0, role: g?.getAttribute('role'),
    ls: localStorage.getItem('tasks.pw.side'), W: innerWidth, rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: []});
  await call(CA, 'POST', '/api/users', {orgs: [], username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Requisiten mit einem recht langen Listennamen', kind: 'list'})).id;
  await call(CF, 'POST', '/api/tasks', {title: 'Stativ abholen', list_id: L});
  check(!!L, 'setup: a list with a task');
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, nav, ctx, shot, until, idle}) => {
    const get = async () => JSON.parse(await ev(M));
    const open = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 860}});
      await nav(B + 'static/icon.svg');
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#l/' + L); await idle();
      check(await until(`!!document.querySelector('#side') && !!document.querySelector('#view')`, {timeout: 20000}), `${W}: the app is there`);
    };
    const drag = async (x0, y0, dx, look) => {
      const vw = +(await ev('innerWidth')); dx = Math.max(1, Math.min(vw - 2, x0 + dx)) - x0;  // a far drag ends at the window's edge
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0), duration: 100}]}]});
      await ev('new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(1))))');  // two frames: the drag's width is drawn
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await until(`!document.querySelector('.pgrip.drag')`, {timeout: 3000});  // released: the grip's drag is over
      return mid;
    };
    const openDrawer = async () => {
      await ev(`(document.querySelector('#top [data-act="side"]')?.click(), 1)`);
      return until(`document.querySelector('#side').classList.contains('open') && !document.querySelector('#side').getAnimations().length && (() => { const g = document.querySelector('#pgrip-side'); return !!g && !g.hidden && Math.abs(g.getBoundingClientRect().left + 5 - document.querySelector('#side').getBoundingClientRect().right) <= 2; })()`, {timeout: 5000});
    };

    await open(1280, true);
    await ev(`(panelSet('side', 20), 1)`);
    const f0 = await get();
    check(!f0.rail && Math.abs(f0.w - 20 * f0.rem) <= 2 && f0.ls === '20', 'the fixed sidebar at 20rem ' + JSON.stringify(f0));
    // folded by hand: the drawer
    await ev(`(sideFold(true), 1)`);
    check(await until(`document.querySelector('#app').classList.contains('side-rail') && !document.querySelector('#side').getAnimations().length && document.querySelector('#pgrip-side').hidden`, {timeout: 5000}), 'folded: the drawer layout, the closed drawer hides the grip');
    const c0 = await get();
    check(!c0.open && !c0.grip, 'the closed drawer has no grip ' + JSON.stringify(c0));
    check(await openDrawer(), 'the menu button opens the drawer, its grip sits on the right edge');
    const d0 = await get();
    check(d0.open && d0.grip && d0.role === 'separator' && Math.abs(d0.w - 20 * d0.rem) <= 2, 'the open drawer: the remembered 20rem and the grip ' + JSON.stringify(d0));
    await shot('p7307-drawer.png');
    const mid = JSON.parse(await drag(d0.gx, d0.gy, 96, `JSON.stringify({w: Math.round(document.querySelector('#side').getBoundingClientRect().width)})`) || '{}');
    check(Math.abs(mid.w - (d0.w + 96)) <= 3, 'during the drag the drawer follows live ' + JSON.stringify(mid));
    const d1 = await get();
    check(d1.open && d1.rail && Math.abs(d1.w - (d0.w + 96)) <= 3 && d1.ls === '26' && d1.grip, 'released: 26rem kept under pw.side, the drawer stays open with its grip ' + JSON.stringify(d1));
    await drag(d1.gx, d1.gy, 2000);
    const d2 = await get();
    check(d2.open && d2.right <= Math.round(d2.W * .8) + 2 && d2.w > 30 * d2.rem, 'dragged far: it stops at 80 % of the window ' + JSON.stringify(d2));
    await ev(`(panelSet('side', 26), 1)`);
    // closed: no grip; unfolded: the same width fixed
    await ev(`(closeSide(), 1)`);
    check(await until(`!document.querySelector('#side').classList.contains('open') && document.querySelector('#pgrip-side').hidden`, {timeout: 3000}), 'closed: the grip goes');
    await ev(`(sideFold(false), 1)`);
    check(await until(`!document.querySelector('#app').classList.contains('side-rail')`, {timeout: 5000}), 'unfolded: the fixed sidebar');
    const u0 = await get();
    check(Math.abs(u0.w - 26 * u0.rem) <= 2 && u0.grip, 'unfolded: the fixed sidebar has the drawer\'s width and its grip ' + JSON.stringify(u0));
    // phone: the fixed drawer width, no grip
    await open(390, false);
    await ev(`(document.querySelector('#top [data-act="side"]')?.click(), 1)`);
    await until(`document.querySelector('#side').classList.contains('open')`, {timeout: 5000});
    await until(`!document.querySelector('#side').getAnimations().length`, {timeout: 3000});
    const p0 = await get();
    check(p0.open && p0.w < 26 * p0.rem && p0.w <= p0.W * .8 + 1 && !p0.grip, 'phone: the drawer keeps its own width (not the 26rem of pw.side), no grip ' + JSON.stringify(p0));
  });

  console.log(`p7307_drawer_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
