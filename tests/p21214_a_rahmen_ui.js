// 2.1214.0 (#6132, was 2.1170.0 Part C; the #6126 start-page checks stay with #6126): the app's bars, own container (start.sh,
// kalmido-suite: fresh
// mode workspaces). Firefox 1280 x 900 with a mouse, 360 x 740 with a finger:
// #6132 offline is ONE sign (the header chip with its word in the normal font, no bar, no grey dot); new version + waiting change
// + upload + code hint stack without overlapping, under the header (computer) / above the tab bar and the "+" (phone); Close
// takes the new-version bar away; the code hint only for server admins. Screenshots into $P21214A_SHOTS.
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21214_a_rahmen_ui', check, shots: 'P21214A_SHOTS', allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const TC = require('./testclock');
const FEAT = 'cal,comments,collab,events';

// in the page: the rectangles of the bars and what they must not cover
const RECTS = `(() => { const r = s => { const e = document.querySelector(s); if (!e || !e.getClientRects().length) return null; const b = e.getBoundingClientRect(); return b.width && b.height ? {l: b.left, t: b.top, r: b.right, b: b.bottom} : null; };
  return {newver: r('#newver'), stale: r('#stale'), up: r('#upbars .upbar'), code: r('#codechg'), kbar: r('#kbar'), top: r('#top'), tabs: r('#tabs'), fab: r('#fab:not(.gone)'), vw: innerWidth, vh: innerHeight}; })()`;
const over = (a, b) => !!a && !!b && a.l < b.r - 1 && b.l < a.r - 1 && a.t < b.b - 1 && b.t < a.b - 1;
const inView = (a, m) => !!a && a.l >= -1 && a.t >= -1 && a.r <= m.vw + 1 && a.b <= m.vh + 1;
// in the page: offline for the app (the 4 s check must not switch it back) with one change waiting (a title saved while the
// requests fail), then the connection back
const GO_OFF = (tid) => `(async () => { window.__f0 = window.__f0 || window.fetch; window.fetch = (u, o) => String(u && u.url || u).includes('/api/') ? Promise.reject(new TypeError('offline')) : window.__f0(u, o);
  await patchTask(${tid}, {title: 'Offline title ' + Date.now()}).catch(() => 0); setOnline(false); return OUT.q.length; })()`;
const GO_ON = `(() => { window.fetch = window.__f0; setOnline(true); return 1; })()`;
// until the waiting change went out (the outbox sends it once online), then the header and the bar are drawn again
const SENT = `(() => { if (OUT.q.length) { if (!OUT.flushing) flush().catch(() => 0); return false; } S.syncOk = Date.now(); staleDraw(); renderTop(); return true; })()`;
const SIGNS = `(() => { const vis = e => !!e && e.getClientRects().length > 0 && e.getBoundingClientRect().width > 0;
  const chip = document.querySelector('#top .offline');
  return {chip: vis(chip), word: chip ? (chip.querySelector('.ofl')?.textContent || '').trim() : '', wordVis: vis(chip?.querySelector('.ofl')),
    mono: chip ? /mono/i.test(getComputedStyle(chip).fontFamily) : null, stale: vis(document.querySelector('#stale')),
    dots: [...document.querySelectorAll('.netdot.n-off')].filter(vis).length}; })()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha Film', admin_id: me.id});
  check(org.id > 0, 'the organisation Alpha Film ' + org.http);
  const ol = await call(CA, 'POST', '/api/lists', {name: 'Alpha shoot', org_id: org.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: 'private'});  // a new list goes into the shown workspace
  const pl = await call(CA, 'POST', '/api/lists', {name: 'Home things', org_id: null});
  const ls = (await call(CA, 'GET', '/api/state')).lists || [];
  check(ls.find(l => l.id === ol.id)?.org_id === org.id && !ls.find(l => l.id === pl.id)?.org_id, 'a list in Alpha Film and a private one');
  const T0 = TC.today();
  const ta = await call(CA, 'POST', '/api/tasks', {title: 'Alpha call', list_id: ol.id, due: T0});
  await call(CA, 'POST', '/api/tasks', {title: 'Alpha cut', list_id: ol.id, due: T0});
  const tp = await call(CA, 'POST', '/api/tasks', {title: 'Water the plants', list_id: pl.id});
  check(ta.id > 0 && tp.id > 0, 'two tasks due today in Alpha Film, one undated private task');
  await call(CA, 'PATCH', '/api/settings', {workspace: 'private'});
  // bob: no server admin (the code hint is not his)
  const bob = await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com', orgs: []});
  check(bob.http === 200, 'bob ' + bob.http);
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});

  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const home = async (o) => { await o.nav(B + '#home'); await o.until(`!!document.querySelector('.dash .dashhead')`); await o.idle({quiet: 300}); };

  // ================= computer, mouse: 1280 and 820
  await firefox(async o => {
    const {cmd, ev, ctx, shot, nav, until} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    check(await signIn(ev, 'alice') === 200, 'alice signs in');
    await home(o);
    // #6132: offline = one sign
    const n = await ev(GO_OFF(ta.id));
    check(n >= 1, '#6132: a change waits while the requests fail ' + n);
    await ev(`(() => { renderTop(); staleDraw(); return 1; })()`);
    // the bar for the waiting change (offline + 1 waiting), then nothing waiting: the chip alone
    const s1 = await ev(SIGNS);
    check(s1.chip && s1.word === 'Offline' && s1.wordVis && s1.mono === false && s1.dots === 0, '#6132 1280: the chip with the word "Offline" in the normal font, no grey dot ' + JSON.stringify(s1));
    check(s1.stale, '#6132 1280: while a change waits the bar shows it ' + JSON.stringify(s1));
    check(/Click to try again/.test(await ev(`document.querySelector('#top .offline')?.title || ''`)), '#6132: with a mouse "Click to try again"');
    // + a new version, an upload and the code hint at the same time: one stack under the header, nothing on top of each other
    await ev(`(() => { verIdle = Date.now(); verCheck('99.9.9'); window.__up = upRow('Big file.pdf', () => {}); upCodeBar({version: '1'}); return 1; })()`);
    await until(`!!document.querySelector('#bars #newver') && !!document.querySelector('#bars #upbars .upbar') && !!document.querySelector('#bars #codechg') && !!document.querySelector('#bars #stale')`);
    let m = await ev(RECTS);
    const four = [m.newver, m.stale, m.up, m.code];
    check(four.every(x => inView(x, m)) && !four.some((a, i) => four.some((b, j) => j > i && over(a, b))), '#6132 1280: new version, waiting change, upload and code hint do not overlap ' + JSON.stringify(m));
    check(four.every(x => !over(x, m.kbar) && !over(x, m.top)) && m.newver.t >= m.top.b - 1, '#6132 1280: the stack sits under the header, not on it ' + JSON.stringify(m));
    await shot('p21214a-1280-bars.png');
    // Close takes the new-version bar away (for this version)
    await ev(`(() => { document.querySelector('#newver [data-nv="x"]').click(); verCheck('99.9.9'); return 1; })()`);
    check(await until(`!document.querySelector('#newver') && !!document.querySelector('#stale')`), '#6132: Close takes the new-version bar away, the others stay');
    // back online: the waiting change goes out, no chip, no bar
    await ev(GO_ON);
    const sent = await until(SENT);
    await ev(`(() => { window.__up.done(); document.querySelector('#codechg [data-ccx]')?.click(); return 1; })()`);
    const s2 = await ev(SIGNS);
    check(sent && !s2.chip && !s2.stale, '#6132: back online: the change goes out, chip and bar go ' + JSON.stringify({sent, s2}));
    // offline without a waiting change: the chip alone (no bar)
    await ev(`(() => { Object.defineProperty(OUT, 'online', {configurable: true, get: () => false, set() {}}); renderTop(); staleDraw(); return 1; })()`);
    const s3 = await ev(SIGNS);
    check(s3.chip && !s3.stale && s3.dots === 0, '#6132: offline, nothing waiting: exactly one sign (the chip) ' + JSON.stringify(s3));
    await ev(`(() => { delete OUT.online; OUT.online = true; renderTop(); staleDraw(); return 1; })()`);

    // ---- bob (no server admin): no code hint
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    check(await signIn(ev, 'bob') === 200, 'bob signs in');
    await nav(B + 'static/icon.svg');
    await home(o);
    await ev(`(() => { upCodeBar({version: '1'}); return 1; })()`);
    check(await ev(`!!S.me && !S.me.is_admin && !document.querySelector('#codechg')`), '#6132: no server admin: no code hint');
  }, false);

  // ================= phone and tablet, a finger: 360 and 820
  await firefox(async o => {
    const {cmd, ev, ctx, shot, nav, until} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    check(await signIn(ev, 'alice') === 200, 'alice signs in (phone)');
    await home(o);
    // #6132 on the phone: the chip with symbol + word; new version + waiting change + upload above the tab bar and the "+"
    await ev(GO_OFF(ta.id));
    await ev(`(() => { renderTop(); staleDraw(); return 1; })()`);
    const s = await ev(SIGNS);
    check(s.chip && s.word === 'Offline' && s.wordVis && s.dots === 0, '#6132 360: the chip shows symbol + "Offline" ' + JSON.stringify(s));
    check(/Tap to try again/.test(await ev(`document.querySelector('#top .offline')?.title || ''`)), '#6132: with a finger "Tap to try again"');
    await ev(`(() => { verIdle = Date.now(); verCheck('99.9.9'); window.__up = upRow('Big file.pdf', () => {}); return 1; })()`);
    await until(`!!document.querySelector('#bars #newver') && !!document.querySelector('#bars #upbars .upbar') && !!document.querySelector('#bars #stale')`);
    const m = await ev(RECTS);
    const three = [m.newver, m.stale, m.up];
    check(three.every(x => inView(x, m)) && !three.some((a, i) => three.some((b, j) => j > i && over(a, b))), '#6132 360: new version, waiting change and upload do not overlap ' + JSON.stringify(m));
    check(three.every(x => !over(x, m.tabs) && !over(x, m.fab)), '#6132 360: above the tab bar and the "+" button ' + JSON.stringify(m));
    check(await ev(`(() => { const s = document.querySelector('#stale span'); return !!s && s.scrollWidth <= s.clientWidth + 1; })()`), '#6132 360: the bar\'s words are not cut');
    await shot('p21214a-360-bars.png');
    await ev(`(() => { document.querySelector('#newver [data-nv="x"]').click(); window.__up.done(); return 1; })()`);
    check(await until(`!document.querySelector('#newver')`), '#6132 360: Close takes the new-version bar away');
    await ev(GO_ON); await until(SENT);
  }, true);

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
