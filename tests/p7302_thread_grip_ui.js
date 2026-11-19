// #7302 UI test: the team chat's thread pane gets wider by the one grip (grip.js, docs/dev/kern.md "Resizing: the one grip").
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1440 x 900 (mouse, real pointer input), invented people and texts only. Usability:
// - an open thread beside the conversation: a grip on the pane's left edge (separator, focusable, data-grip tc-thread); with
//   nothing stored the pane has today's width (24rem)
// - dragging it to the left makes the pane wider live (the conversation keeps the rest), released it is kept on the device
//   (grip:tc-thread); dragged far, it stops at half of the area; a redraw of the view (a live update) keeps width and grip
// - a reload (the thread opened again): the same width; a double click: today's width again, nothing stored
// - 820 px: the thread full size, no grip
// freelancer-matrix: n/a (no route; the team chat's layout - the grip is a client building block, the same in every workspace)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7302_thread_grip_ui', check, shots: 'P7302_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

// the pane, the conversation, the area, the grip and what is stored
const M = `JSON.stringify((() => {
  const w = s => Math.round(document.querySelector(s)?.getBoundingClientRect().width || 0);
  const g = document.querySelector('.tthpane > .tthgrip'), r = g?.getBoundingClientRect();
  return {pane: w('.tthpane'), room: w('.tcview > .tcroom'), view: w('.tcview'), grip: !!g && g.classList.contains('grip'), role: g?.getAttribute('role'), key: g?.dataset.grip,
    ti: g ? g.tabIndex : null, gx: r ? r.left + r.width / 2 : 0, gy: r ? r.top + r.height / 2 : 0, gw: r ? Math.round(r.width) : 0,
    v: getComputedStyle(document.querySelector('.tcview') || document.body).getPropertyValue('--g-tc-thread').trim(), root: document.documentElement.style.getPropertyValue('--g-tc-thread'),
    ls: localStorage.getItem('tasks.grip:tc-thread'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'anna', display_name: 'Anna Berger', password: 'password123'})});
  check(r.ok, 'setup');
  const CA = await login('anna');
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Gegenlicht Film', lang: 'en', collab_all: true, modules: ['comments', 'collab', 'team']});
  const st0 = await call(CA, 'GET', '/api/state'); const ORG = (st0.me?.workspaces || [])[0]?.id;
  check(ORG, 'the organisation');
  const feats = new Set(((st0.settings || {}).features || '').split(',').filter(Boolean)); for (const m of ['comments', 'collab', 'team']) feats.add(m);
  const FEAT = [...feats].join(','), WS = `org:${ORG}`;
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: WS});
  const U = {}, CK = {anna: CA};
  for (const [u, n] of [['bert', 'Bert Kaminski'], ['carla', 'Carla Hohenstein']]) {
    U[u] = (await call(CA, 'POST', '/api/users', {username: u, password: 'password123', display_name: n, email: `${u}@example.com`, orgs: [{id: ORG, role: 'member'}]})).id;
    CK[u] = await login(u); await call(CK[u], 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: WS});
  }
  const CH = (await call(CA, 'POST', '/api/team/channels', {name: 'Shooting crew', org_id: ORG, open: false, members: [U.bert, U.carla]})).id;
  check(CH, 'the channel');
  const post = (u, body, extra = {}) => call(CK[u], 'POST', `/api/team/rooms/${CH}/messages`, {body, ...extra});
  for (const t of ['Tomorrow at 7 at the harbour?', 'I bring the batteries.', 'Hall 3 is booked.']) await post('bert', t);
  const ROOT = (await post('bert', 'Thread about the music - suggestions here please.')).id;
  check(ROOT, 'the thread\'s first message');
  for (const [u, t] of [['carla', 'Something calm, piano.'], ['anna', 'Piano sounds good to me.']]) await post(u, t, {thread_of: ROOT});
  await post('carla', 'The permit is here.');
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'anna', password: 'password123'})}).then(r => r.status)`);

  await firefox(async o => {
    const {cmd, ev, nav, ctx, shot, until, idle} = o;
    const get = async () => JSON.parse(await ev(M));
    const openThread = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      await nav(B + 'static/icon.svg');  // a real new load of the app
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#team/' + CH); await idle();
      check(await until(`!!document.querySelector('#tc-in') && !!document.querySelector('.tthline[data-root="${ROOT}"]')`, {timeout: 20000}), `${W}: the conversation opens`);
      await ev(`(() => { const b = document.querySelector('.tthline[data-root="${ROOT}"]'); b.scrollIntoView({block: 'center'}); b.click(); return 1; })()`);
      check(await until(`[...document.querySelectorAll('#tth-msgs .cbub')].some(b => b.textContent.includes('Something calm'))`), `${W}: the thread opens with its answers`);
    };
    const drag = async (x0, y0, dx, look) => {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0), duration: 100}]}]});
      await sleep(80);  // the last move lands in the next frame (rafThrottle)
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await sleep(60);
      return mid;
    };

    await openThread(1440, true);
    check(await until(`!!document.querySelector('.tthpane > .tthgrip.grip')`, {timeout: 8000}), '1440: the grip is on the thread pane');
    const g0 = await get();
    check(g0.role === 'separator' && g0.key === 'tc-thread' && g0.ti === 0 && g0.gw >= 8, 'the grip: a focusable separator named tc-thread ' + JSON.stringify(g0));
    check(Math.abs(g0.pane - 24 * g0.rem) <= 2 && !g0.v && g0.ls == null, 'nothing stored: the pane has today\'s width (24rem) ' + JSON.stringify(g0));
    const hit = await ev(`(() => { const e = document.elementFromPoint(${g0.gx}, ${g0.gy}); return !!e && e.classList.contains('tthgrip'); })()`);
    check(hit, 'the pointer reaches the grip (nothing lies over it)');
    // a drag to the left: wider live, stored on release
    const mid = await drag(g0.gx, g0.gy, -160, `JSON.stringify({pane: Math.round(document.querySelector('.tthpane').getBoundingClientRect().width), ls: localStorage.getItem('tasks.grip:tc-thread'), drag: document.body.classList.contains('pgdrag')})`);
    const m = JSON.parse(mid || '{}'), want = Math.min(g0.pane + 160, Math.floor(g0.view / g0.rem / 2) * g0.rem);
    check(Math.abs(m.pane - want) <= 3 && m.ls == null && m.drag, 'during the drag the pane follows live, nothing stored yet ' + mid);
    const g1 = await get();
    check(Math.abs(g1.pane - want) <= 3 && g1.ls === String(want / g1.rem) && g1.v === g1.ls + 'rem' && !g1.root && g1.room > 200,
      'released: the pane is 160 px wider (at most half), kept under grip:tc-thread on the area (not the root), the conversation keeps the rest ' + JSON.stringify(g1));
    await shot('p7302-wide.png');
    // a redraw of the view (a live update morphs it): width and grip stay
    await ev(`(renderView(), 1)`); await idle();
    const g2 = await get();
    check(g2.grip && g2.role === 'separator' && Math.abs(g2.pane - g1.pane) <= 1, 'a redraw keeps the width and the grip ' + JSON.stringify(g2));
    // dragged far: at most half of the area
    await drag(g2.gx, g2.gy, -(g2.gx - 20));
    const g3 = await get();
    check(g3.pane <= g3.view / 2 + 2 && g3.pane >= g3.view / 2 - g3.rem - 2 && g3.room > 100, 'dragged far: the pane stops at half of the area ' + JSON.stringify(g3));
    // the keyboard: arrow right = 1rem narrower (the pane lies after the grip)
    await ev(`(document.querySelector('.tthpane > .tthgrip').focus(), 1)`);
    await cmd('input.performActions', {context: ctx, actions: [{type: 'key', id: 'kb', actions: [{type: 'keyDown', value: ''}, {type: 'keyUp', value: ''}]}]});
    await cmd('input.releaseActions', {context: ctx});
    const g4 = await get();
    check(Math.abs(g4.pane - (g3.pane - g4.rem)) <= 2, 'arrow right: 1rem narrower ' + JSON.stringify([g3.pane, g4.pane]));
    await ev(`(document.activeElement && document.activeElement.blur(), 1)`);
    await ev(`(localStorage.setItem('tasks.grip:tc-thread', '30'), 1)`);

    // a reload: the same width
    await openThread(1440, false);
    check(await until(`!!document.querySelector('.tthpane > .tthgrip.grip')`, {timeout: 8000}), 'reload: the grip again');
    const g5 = await get();
    check(Math.abs(g5.pane - 30 * g5.rem) <= 2 && g5.v === '30rem', 'reload: the pane has the kept width (30rem) ' + JSON.stringify(g5));
    // a double click: today's width, nothing stored
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
      {type: 'pointerMove', x: Math.round(g5.gx), y: Math.round(g5.gy)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}, {type: 'pause', duration: 80}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    check(await until(`localStorage.getItem('tasks.grip:tc-thread') === null && Math.abs(document.querySelector('.tthpane').getBoundingClientRect().width - 24 * ${g5.rem}) <= 2`, {timeout: 3000}),
      'a double click: today\'s width again, nothing stored ' + JSON.stringify(await get()));

    // 820 px: the thread full size, no grip
    await ev(`(localStorage.setItem('tasks.grip:tc-thread', '30'), 1)`);
    await openThread(820, false);
    const g6 = await get();
    check(!g6.grip && !g6.pane, '820: the thread full size, no pane and no grip ' + JSON.stringify(g6));
    await shot('p7302-820.png');
  });

  console.log(`p7302_thread_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
