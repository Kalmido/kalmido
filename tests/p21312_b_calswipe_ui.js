// kalmido-suite:
// 2.1312.0 UI test (#6711: the calendar leafs like a page - calgest.js with the core's swipenav.js swn_attach), own container
// (start.sh), Firefox (touch) at the unfolded Fold (884 x 1104) and the phone (412 x 915). Invented data only.
// - half a swipe on the month: only the grid moves (the bar and the day list with its input line below stay, no transform),
//   the next month lies beside it as a placeholder (its empty grid: weekdays and its 30 days, visible on the screen), the page
//   does not scroll sideways
// - let go: the next month, and the grid's transform never went back to 0 before the change (no spring back), no second
//   glide-in (an_calSlide's an-cn* classes stay off #view), the placeholder gone
// - a short swipe springs back (same month, no transform, no placeholder)
// - the week: the next week's head lies beside it (its 7 days), its 12:00 at the height of the shown 12:00 (the hours scrolled);
//   let go = 7 days on; a fetch answered mid-swipe (the week's events) waits for the finger (cgs_held)
// The pinch zoom and the trackpad stay (p21640_ui, p2290_a_calzoom_ui).
// freelancer-matrix: n/a (no route; the gestures run in the client only, tested as alice without an organisation)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21312_b_calswipe_ui', check, shots: 'P21312B_SHOTS', prefs: [['ui.prefersReducedMotion', 0]]});  // the glide as on the phone / Fold (reduced motion snaps without it: swipenav.js)
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21312B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events'});

  await firefox(async ({cmd, ev, nav: go, ctx, shot}) => {
    await go(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(150); } return false; };
    const TOUCH = `const tc = (el, type, pts) => { const e = new Event(type, {bubbles: true, cancelable: true}); Object.defineProperty(e, 'touches', {value: type === 'touchend' ? [] : pts.map(([x, y]) => ({clientX: x, clientY: y, target: el}))}); el.dispatchEvent(e); };
      const at = el => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + Math.min(40, r.height / 2)]; };
      const hold = (el, dx) => { const [x, y] = at(el); window.__at = el; tc(el, 'touchstart', [[x, y]]); for (const f of [.25, .5, .75, 1]) tc(el, 'touchmove', [[x + dx * f, y]]); };
      const lift = () => tc(window.__at, 'touchend', []);`;
    const GRID = `document.querySelector('#view .cal:not(.cgs-nbg)')`;
    // the grid's transforms while the month is still the old one (a spring back to 0 before the change = red)
    const WATCH = `(g => { window.__tf = []; window.__mo?.disconnect(); window.__mo = new MutationObserver(() => __tf.push([g.style.transform, S.calMonth, S.calSel])); window.__mo.observe(g, {attributes: true, attributeFilter: ['style']}); })`;
    for (const [W, Ht] of [[884, 1104], [412, 915]]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Ht}});
      check(await wait(`innerWidth === ${W}`, 40), `Firefox ${W}: the window has its size`);
      await go(B + '#cal');
      check(await wait(`typeof cgs_peek === 'function' && typeof swn_attach === 'function' && isTouch() && !!document.querySelector('#view .calbar')`, 100), `Firefox ${W}: the calendar on a touch screen, leafing with swipenav.js`);
      await ev(`(() => { S.calMode = 'month'; LS.set('calMode', 'month'); S.calMonth = '2026-03'; S.calSel = '2026-03-10'; renderView(); return 1; })()`);
      check(await wait(`!!${GRID}?.querySelector('.cell') && S.calMonth === '2026-03'`), `Firefox ${W}: March 2026`);

      // ---- half a swipe: the placeholder beside the grid, the rest stands
      const mid = await ev(`(() => { ${TOUCH} const g = ${GRID}; ${WATCH}(g); const gl0 = g.getBoundingClientRect().left;
        const v = document.getElementById('view'), ag = v.querySelector('.agenda'), a0 = ag?.getBoundingClientRect().left;
        hold(g.querySelectorAll('.cell:not(.out)')[9], -${Math.round(W * .3)});
        const nb = v.querySelector(':scope > .swn-nb[data-dir="1"] > .cal.cgs-nbg'), r = nb?.getBoundingClientRect();
        return {nb: !!nb, days: nb ? nb.querySelectorAll('.cell:not(.out)').length : 0, wd: nb ? nb.querySelectorAll('.wd').length : 0,
          vis: !!r && r.left < innerWidth - 20 && r.right > 0 && r.height > 100, gtf: g.style.transform, moved: Math.round(g.getBoundingClientRect().left - gl0), gap: r ? Math.round(r.left - g.getBoundingClientRect().right) : null, gcs: getComputedStyle(g).transform, an: getComputedStyle(g).animationName + '|' + document.getElementById('view').className,
          ag: !!ag, agTf: ag ? getComputedStyle(ag).transform : 'none', agMoved: ag ? Math.round(ag.getBoundingClientRect().left - a0) : 0, qin: !!ag?.querySelector('#qinput'),
          bar: getComputedStyle(v.querySelector('.calbar')).transform, side: getComputedStyle(v).overflowX + ':' + v.scrollLeft}; })()`);
      check(mid.nb && mid.days === 30 && mid.wd === 7 && mid.vis, `Firefox ${W}: half a swipe: April lies beside the grid as an empty grid (7 weekdays, 30 days), on the screen ` + JSON.stringify(mid));
      check(/translateX\(-\d+px\)/.test(mid.gtf) && mid.moved === -Math.round(W * .3) && Math.abs(mid.gap - 16) <= 2, `Firefox ${W}: the grid follows the finger (seen on the screen), the next month 16 px beside it ` + JSON.stringify(mid));
      check(mid.ag && mid.qin && mid.agTf === 'none' && mid.agMoved === 0 && mid.bar === 'none', `Firefox ${W}: the day list with its input line and the bar stand still ` + JSON.stringify(mid));
      check(mid.side === 'hidden:0', `Firefox ${W}: the page does not scroll sideways ` + mid.side);
      await shot(`p21312b-month-mid-${W}.png`);

      // ---- let go: April, no spring back, no second glide-in
      await ev(`(() => { ${TOUCH} lift(); return 1; })()`);
      check(await wait(`S.calMonth === '2026-04' && !document.querySelector('#view .swn-nb') && !${GRID}?.style.transform`), `Firefox ${W}: let go = April, the placeholder gone ` + await ev(`S.calMonth`));
      const tf = await ev(`__tf`);
      const back = tf.filter(([t, m]) => m === '2026-03' && !/translateX\(-[1-9]/.test(t));
      check(tf.some(([t, m]) => m === '2026-03' && /translateX\(-[1-9]\d*px\)/.test(t)) && !back.length, `Firefox ${W}: the grid never went back to 0 before the change ` + JSON.stringify(tf));
      check(await ev(`!/\\ban-c[nps][12]\\b/.test(document.getElementById('view').className)`), `Firefox ${W}: no second glide-in (an_calSlide not called)`);
      await shot(`p21312b-month-after-${W}.png`);

      // ---- a short one springs back
      await sleep(800);
      const sh = await ev(`(() => { ${TOUCH} hold(${GRID}.querySelectorAll('.cell:not(.out)')[9], -30); lift(); return 1; })()`);
      check(sh && await wait(`S.calMonth === '2026-04' && !document.querySelector('#view .swn-nb') && !${GRID}.style.transform`), `Firefox ${W}: a short swipe springs back`);

      // ---- the week: the next week's head beside it, the hours at the same place
      await ev(`(() => { S.calMode = 'week'; LS.set('calMode', 'week'); LS.set('calDays', 7); S.calSel = '2026-04-15'; renderView(); return 1; })()`);
      check(await wait(`!!document.querySelector('#view #wbody .wcol')`), `Firefox ${W}: the week`);
      await ev(`(() => { const b = document.getElementById('wbody'); b.scrollTop = 300; return 1; })()`);
      const s0 = await ev(`S.calSel`);
      await ev(`(() => { ${TOUCH} const g = document.querySelector('#view .week:not(.cgs-nbg)'); window.__tf = []; window.__mo?.disconnect(); window.__mo = new MutationObserver(() => __tf.push([g.style.transform, S.calSel])); window.__mo.observe(g, {attributes: true, attributeFilter: ['style']});
        hold(document.querySelectorAll('#view #wbody .wcol')[3], -${Math.round(W * .3)}); return 1; })()`);
      const wk = await ev(`(() => { const nb = document.querySelector('#view > .swn-nb[data-dir="1"] > .week.cgs-nbg'), w0 = weekStartOf(addDays(S.calSel, 7));
        return {nb: !!nb, hd: nb ? [...nb.querySelectorAll('.whead .wh b')].map(b => b.textContent) : [], want: String(pd(w0).getDate()),
          top: nb?.querySelectorAll('.wtime')[12]?.getBoundingClientRect().top, top0: document.querySelectorAll('#wbody .wtime')[12].getBoundingClientRect().top, sc: document.getElementById('wbody').scrollTop, ids: document.querySelectorAll('[id="wbody"]').length}; })()`);
      check(wk.nb && wk.hd.length === 7 && wk.hd[0] === wk.want && wk.ids === 1, `Firefox ${W}: half a swipe in the week: the next week's 7 days beside it (no second #wbody) ` + JSON.stringify(wk));
      check(wk.sc > 0 && Math.abs(wk.top - wk.top0) <= 2, `Firefox ${W}: ... its hours at the same scroll position ` + JSON.stringify(wk));
      await shot(`p21312b-week-mid-${W}.png`);
      await ev(`(() => { ${TOUCH} lift(); return 1; })()`);
      check(await wait(`S.calSel === addDays(${JSON.stringify(s0)}, 7) && !document.querySelector('#view .swn-nb')`), `Firefox ${W}: let go = the next week`);
      const wtf = await ev(`__tf`);
      check(!wtf.filter(([t, s]) => s === s0 && !/translateX\(-[1-9]/.test(t)).length, `Firefox ${W}: the week's grid never went back to 0 before the change ` + JSON.stringify(wtf));
      await sleep(800);
    }
  }, true);

  console.log(`p21312_b_calswipe_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
