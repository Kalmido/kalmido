// #7308 UI test: the name column of the list timeline and of the roadmap gets wider by the one grip (grip.js, docs/dev/kern.md
// "Resizing: the one grip"; keys tl-name / rm-name, --tl-name follows).
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1280 x 860 (mouse, real pointer input), a person WITHOUT an organisation (freelancer-matrix:
// tasks), invented names only. Usability:
// - list timeline: a focusable separator (data-grip tl-name) on the right edge of the names, default 10.625rem; dragged to the
//   right the names get wider live and the days move along (today line), released it is kept (grip:tl-name); a redraw keeps it
// - dragged far: no fixed cap, the days keep 8rem; a double click: the default again, nothing stored
// - the roadmap has its own width (rm-name, default 13rem), the keyboard (arrow right) makes it wider
// - phone width: the narrow column, no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7308_tl_name_grip_ui', check, shots: 'P7308_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const ds = n => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

const M = k => `JSON.stringify((() => {
  const box = document.querySelector('#view .tl'), g = box && box.querySelector(':scope > .tlngrip'), r = g?.getBoundingClientRect(), n = box?.querySelector('.tl-headrow > .tl-name');
  const now = box?.querySelector('.tl-now');
  return {grip: !!g && g.classList.contains('grip'), role: g?.getAttribute('role'), key: g?.dataset.grip, ti: g ? g.tabIndex : null,
    gx: r ? r.left + r.width / 2 : 0, gy: r ? r.top + Math.min(r.height / 2, 60) : 0, gh: r ? Math.round(r.height) : 0,
    name: Math.round(n?.getBoundingClientRect().width || 0), box: box ? box.clientWidth : 0, now: now ? Math.round(now.getBoundingClientRect().left) : null,
    v: box?.style.getPropertyValue('--g-${k}') || '', root: document.documentElement.style.getPropertyValue('--g-${k}'),
    ls: localStorage.getItem('tasks.grip:${k}'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'timeline']});
  await call(CA, 'POST', '/api/users', {orgs: [], username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,timeline', workspace: 'private', roadmap: JSON.stringify({v: 'timeline', z: 'week'})});
  const P = (await call(CF, 'POST', '/api/lists', {name: 'Kurzfilm Herbst', kind: 'project', view: 'timeline'})).id;
  for (const [t, s, e] of [['Drehbuch zweite Fassung mit langem Namen', 0, 3], ['Location-Besichtigung', 2, 5], ['Schnitt', 4, 9]]) await call(CF, 'POST', '/api/tasks', {title: t, list_id: P, start: ds(s), due: ds(e)});
  check(!!P, 'setup: a project with three dated tasks');
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, nav, ctx, shot, until, idle}) => {
    const get = async k => JSON.parse(await ev(M(k)));
    const open = async (W, hash, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 860}});
      await nav(B + 'static/icon.svg');
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + hash); await idle();
      check(await until(`!!document.querySelector('#view .tl #tlscroll')`, {timeout: 20000}), `${W} ${hash}: the timeline is there`);
    };
    const drag = async (x0, y0, dx, look) => {
      const vw = +(await ev('innerWidth')); dx = Math.max(1, Math.min(vw - 2, x0 + dx)) - x0;  // a far drag ends at the window's edge
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

    // ---- the list timeline
    await open(1280, '#l/' + P, true);
    check(await until(`!!document.querySelector('#view .tl > .tlngrip.grip')`, {timeout: 8000}), 'list timeline: the grip is there');
    const a0 = await get('tl-name');
    check(a0.role === 'separator' && a0.key === 'tl-name' && a0.ti === 0 && a0.gh > 60, 'list timeline: a focusable separator named tl-name, as tall as the rows ' + JSON.stringify(a0));
    check(Math.abs(a0.name - 10.625 * a0.rem) <= 2 && a0.ls == null, 'list timeline: nothing stored, the names 10.625rem ' + JSON.stringify(a0));
    check(await ev(`(() => { const e = document.elementFromPoint(${a0.gx}, ${a0.gy}); return !!e && e.classList.contains('tlngrip'); })()`), 'list timeline: the pointer reaches the grip');
    const mid = JSON.parse(await drag(a0.gx, a0.gy, 96, `JSON.stringify({n: Math.round(document.querySelector('#view .tl-headrow > .tl-name').getBoundingClientRect().width), ls: localStorage.getItem('tasks.grip:tl-name')})`) || '{}');
    check(Math.abs(mid.n - (a0.name + 96)) <= 3 && mid.ls == null, 'list timeline: during the drag the names follow live, nothing stored yet ' + JSON.stringify(mid));
    const a1 = await get('tl-name');
    check(Math.abs(a1.name - (a0.name + 96)) <= 3 && a1.ls != null && /rem$/.test(a1.v) && !a1.root, 'list timeline: released it is kept under grip:tl-name on the .tl, not the root ' + JSON.stringify(a1));
    check(a0.now == null || Math.abs(a1.now - a0.now - 96) <= 4, 'list timeline: the today line moves with the names ' + JSON.stringify([a0.now, a1.now]));
    await shot('p7308-tl-wide.png');
    await ev(`(render(), 1)`); await idle();
    const a2 = await get('tl-name');
    check(a2.grip && Math.abs(a2.name - a1.name) <= 1, 'list timeline: a redraw keeps width and grip ' + JSON.stringify(a2));
    await drag(a2.gx, a2.gy, 1200);
    const a3 = await get('tl-name');
    check(a3.name > a3.box / 2 && a3.box - a3.name >= 8 * a3.rem - 12, 'list timeline: dragged far it goes past half, the days keep 8rem (no fixed cap) ' + JSON.stringify(a3));
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
      {type: 'pointerMove', x: Math.round(a3.gx), y: Math.round(a3.gy)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}, {type: 'pause', duration: 80}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    check(await until(`localStorage.getItem('tasks.grip:tl-name') === null && Math.abs(document.querySelector('#view .tl-headrow > .tl-name').getBoundingClientRect().width - 10.625 * ${a3.rem}) <= 2`, {timeout: 3000}),
      'list timeline: a double click = the default, nothing stored ' + JSON.stringify(await get('tl-name')));

    // ---- the roadmap: its own width, the keyboard
    await open(1280, '#all', false);
    check(await until(`!!document.querySelector('#view .tl.rm > .tlngrip.grip')`, {timeout: 8000}), 'roadmap: the grip is there');
    const r0 = await get('rm-name');
    check(r0.key === 'rm-name' && Math.abs(r0.name - 13 * r0.rem) <= 2, 'roadmap: its own key, default 13rem ' + JSON.stringify(r0));
    await ev(`(() => { const g = document.querySelector('#view .tl.rm > .tlngrip'); g.focus(); for (const s of [1, 1]) g.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', shiftKey: true, bubbles: true, cancelable: true})); return 1; })()`);
    const r1 = await get('rm-name');
    check(Math.abs(r1.name - 21 * r1.rem) <= 2 && r1.ls === '21', 'roadmap: Shift + arrow right twice = 8rem wider, kept ' + JSON.stringify(r1));
    await shot('p7308-rm-wide.png');
    await open(1280, '#all', false);
    check(await until(`!!document.querySelector('#view .tl.rm > .tlngrip.grip')`, {timeout: 8000}) && Math.abs((await get('rm-name')).name - 21 * r1.rem) <= 2, 'roadmap: a reload keeps the width');

    // ---- phone: no grip, the narrow column
    await open(390, '#l/' + P, false);
    const p0 = await get('tl-name');
    check(!p0.gx && Math.abs(p0.name - 6.75 * p0.rem) <= 2, 'phone: no grip, the narrow 6.75rem column ' + JSON.stringify(p0));
  });

  console.log(`p7308_tl_name_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
