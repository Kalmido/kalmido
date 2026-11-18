// 2.1367.0 part B (#6748): Settings on a phone in Firefox (real layout, 360 x 780 touch): the sidebar groups and the bottom
// bar with their grip, the "…" menu with its arrows.
// kalmido-suite: fresh
// freelancer-matrix: settings  (alice without an organisation)
// - Appearance > Sidebar: every group row has its grip at the left, 44 px tall (a finger), the row stays inside the screen
// - the "…" of a group: "move up" is drawn turned (arrow up), "move down" not
// - Navigation > Tab bar: the line "from here on More" right above the 5th point (its name not cut), nothing sideways
// With P21367B_SHOTS: pictures of the three.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21367_b_tabdrag_ff_ui', check, shots: 'P21367B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const ORDER = ['s:inbox', 's:today', 's:tomorrow', 's:week', 's:doable', 's:pinned', 's:waiting'];

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en'});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', nav_menus: JSON.stringify({tabbar: {order: ORDER}})});
  const ready = async (ev, expr, n = 80) => { for (let i = 0; i < n; i++) { const x = await ev(expr).catch(() => null); if (x) return x; await sleep(250); } return null; };

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 780}});
    await nav(B + '#today');
    check(await ready(ev, `typeof settingsModal === 'function' && !!document.querySelector('#tabs button')`), 'the app is up');
    await ev(`settingsModal('look')`);
    const geo = await ready(ev, `(() => { const rs = [...document.querySelectorAll('.smodal #s-sidebar .sidegrp')]; if (!rs.length || document.fonts.status !== 'loaded') return null;
      rs[0].scrollIntoView({block: 'start'});
      return JSON.stringify(rs.map(r => { const g = r.querySelector('.rowgrip').getBoundingClientRect(), b = r.getBoundingClientRect(), e = r.querySelector('.sideye').getBoundingClientRect();
        return {gl: Math.round(g.left - b.left), gw: g.width, gh: g.height, left: g.right <= e.left + 1, inside: b.right <= innerWidth + 1}; })); })()`);
    const G = JSON.parse(geo || '[]');
    check(G.length >= 5 && G.every(x => x.gl <= 8 && x.left), 'sidebar: every group\'s grip at the row\'s left, before the eye: ' + geo);
    check(G.every(x => x.gh >= 43 && x.gw >= 43), 'sidebar: the grip is a finger\'s size (44 px): ' + geo);
    check(G.every(x => x.inside), 'sidebar: the rows stay inside the screen');
    await sleep(300); await shot('p21367b-sidebar-360.png');
    // the "…" of the second group: its menu
    await ev(`document.querySelectorAll('.smodal #s-sidebar .sidegrp')[1].querySelector('.ms-phdots').click()`);
    const m = await ready(ev, `(() => { const its = [...document.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')]; if (!its.length) return null;
      return JSON.stringify(its.map(b => [b.textContent.trim(), getComputedStyle(b.querySelector('svg.i')).transform])); })()`);
    const M = Object.fromEntries(JSON.parse(m || '[]'));
    check(M['move up'] && M['move up'] !== 'none' && (M['move down'] || 'none') === 'none', 'the "…" menu: "move up" drawn turned, "move down" not: ' + m);
    await sleep(300); await shot('p21367b-menu-360.png');
    await ev(`closePop(); document.querySelector('.smodal [data-sec="nav"]')?.click(); 1`);
    const nv = await ready(ev, `(() => { const s = document.querySelector('.smodal details.navsec[data-navsec="tabbar"]'); if (!s) return null; s.open = true; s.scrollIntoView({block: 'start'});
      const rs = [...s.querySelectorAll('.navl:not(.navoffl) .navr')], i = rs.findIndex(r => r.previousElementSibling?.matches('.navmore')); if (i < 0) return JSON.stringify({i});
      const k = rs[i].previousElementSibling.getBoundingClientRect(), b = rs[i].getBoundingClientRect(), n = rs[i].querySelector('.navn');
      return JSON.stringify({i, above: k.bottom <= b.top + 1 && k.height > 0, full: n.scrollWidth <= n.clientWidth, wide: document.querySelector('.smodal .spane:not(.hidden)').scrollWidth > document.querySelector('.smodal .spane:not(.hidden)').clientWidth + 1}); })()`);
    const N = JSON.parse(nv || '{}');
    check(N.i === 4 && N.above && N.full && !N.wide, 'Navigation: the line "from here on More" right above the 5th point, its name not cut, nothing sideways: ' + nv);
    await sleep(300); await shot('p21367b-tabbar-360.png');
  }, true);

  console.log(`p21367_b_tabdrag_ff_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
