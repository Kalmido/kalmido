// 2.1493.0 (#7616) the head of the phone's drawer (Firefox, touch, 412 px, invented names only)
// kalmido-suite: fresh
// - the word mark sits on the middle of the bot sign (at most 1 px off), its capital height is about 45 % of the sign's
//   height (40-50 %), the head stays without a new part (no workspace line, no arrow; #7299)
// - less air from the head to the search: 2-5 px (was 8 px, the sticky search's own padding)
// - the words of neighbouring area tiles keep at least 4 px apart ("Habits" / its long German word "Gewohnheiten" too)
const {execFileSync} = require('child_process');
const path = require('path');
const {B, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21493_a_drawer_head_ui', check, shots: 'P21493A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'de'})});
  check(r.ok, 'setup');
  const lr = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', password: 'password123'})});
  const CK = lr.headers.get('set-cookie').split(';')[0];
  const call = (method, url, body) => fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined});
  await call('POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments', 'habits', 'timeline', 'kanban', 'stats', 'pomo', 'contacts', 'time', 'notes']});
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done'});

  for (const [theme, vw] of [['dark', 412], ['light', 412], ['dark', 360]]) await firefox(async o => {
    const {cmd, ev, ctx, shot, until, nav, idle} = o;
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"${theme}"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: vw, height: 860}});
    await nav(B + '#today');
    await until(`typeof S !== 'undefined' && !!S.booted && !!document.querySelector('#top h1')`); await idle();
    await ev(`(() => { document.querySelector('#top [data-act="side"]').click(); return 1; })()`);
    await until(`(() => { const b = document.querySelector('#side.open .sbbrand'); return !!b && b.getBoundingClientRect().width > 30; })()`);
    await sleep(500);
    const m = await ev(`(() => {
      const R = e => { const r = e.getBoundingClientRect(); return {t: r.top, b: r.bottom, l: r.left, r: r.right, h: r.height, w: r.width}; };
      const lg = document.querySelector('#side .sbbrand svg.logo'), kw = document.querySelector('#side .sbbrand svg.kword');
      const hd = document.querySelector('#side .sbhead'), sr = document.querySelector('#side .sbmsrch .scmd, #side .sbmsrch input, #side .sbmsrch > *');
      const L = R(lg), K = R(kw), Hd = R(hd), Sr = sr ? R(sr) : null;
      // the capital K of the mark: viewBox -78..3, K from -70 to 0 (icons.js wordSvg)
      const cap = K.h * 70 / 81, capMid = K.t + K.h * (78 - 35) / 81;
      const tiles = [...document.querySelectorAll('#side .sbmr .srb')].filter(t => t.offsetParent);
      let minGap = 999, pair = '';
      const wordBox = n => { const rg = document.createRange(); rg.selectNodeContents(n); return rg.getBoundingClientRect(); };
      for (let i = 0; i + 1 < tiles.length; i++) {
        const a = tiles[i].querySelector('.srbn'), b = tiles[i + 1].querySelector('.srbn');
        if (!a || !b) continue;
        const ra = wordBox(a), rb = wordBox(b);
        if (Math.abs(ra.top - rb.top) > 20) continue;  // the next row
        const g = rb.left - ra.right;
        if (g < minGap) { minGap = g; pair = a.textContent + ' | ' + b.textContent; }
      }
      return {logoMid: L.t + L.h / 2, kwMid: K.t + K.h / 2, capMid, logoH: L.h, kwH: K.h, cap, capPct: Math.round(cap / L.h * 100),
        headBottom: Hd.b, searchTop: Sr && Sr.t, gap: Sr ? Math.round(Sr.t - Hd.b) : null, minGap: Math.round(minGap * 10) / 10, pair, tiles: tiles.length,
        names: tiles.map(t => t.querySelector('.srbn')?.textContent).join(','), sub: !!document.querySelector('#side .sbbrand .sbbsub, #side .sbbrand .wsn')};
    })()`);
    console.log('MEASURE ' + theme + ' ' + vw + ' ' + JSON.stringify(m));
    check(Math.abs(m.capMid - m.logoMid) <= 1, `${theme}: the word mark's capitals sit on the middle of the sign (${m.capMid.toFixed(1)} vs ${m.logoMid.toFixed(1)})`);
    check(m.capPct >= 40 && m.capPct <= 50, `${theme}: capital height about 45 % of the sign: ${m.capPct} %`);
    check(m.gap !== null && m.gap >= 2 && m.gap <= 5, `${theme}: less air from the head to the search (was 8 px): ${m.gap} px`);
    check(m.minGap >= 4, `${theme}: the words of neighbouring tiles keep 4 px apart: ${m.minGap} px (${m.pair})`);
    check(m.names.includes('Gewohnheiten'), `${theme}: the tile Gewohnheiten is there: ${m.names}`);
    check(!m.sub, `${theme}: no new part in the head`);
    await shot(`p21493a-drawer-${vw}-${theme}.png`);
  }, true);

  console.log(`p21493_a_drawer_head_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21493_a_drawer_head_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
