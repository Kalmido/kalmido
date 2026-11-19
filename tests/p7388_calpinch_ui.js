// kalmido-suite: fresh
// #7388 UI test (regression + measurement): two fingers zoom the calendar's week smoothly with a full calendar. Own container
// (start.sh), Firefox (touch) at a phone's size (412 x 915). Invented data only: three calendars (one of an organisation) with
// about 200 events around this week and 12 daily repeats.
// The fingers are sent the way a browser sends them: every touchmove / touchend goes to the element the finger landed on (a
// browser keeps that target for the whole touch, also when the element has left the page - then the document never hears it).
// Measured cause (before #7388, main of 19.11.2026): each day that came or went drew the grid anew (renderView mid-pinch), the
// fingers' elements left the page, their moves no longer reached calgest.js: the pinch froze after its first day and stayed
// "on" until the next touch (each pinch = one step); and each such drawing of a full grid cost a long frame.
// - pinched together sideways (more days), spread sideways (fewer), up / down (the hours), diagonal (both), a second finger a
//   moment late: the zoom follows to the end (the count of days / the hour height of the last move), no renderView between
//   the first and the last move, no frame over the limit (32 ms, at least 2 x the idle frame), the pinch ends with the fingers
// - released: whole days, the hour height kept, the grid drawn once (no cgs-dz left)
// The trace is printed (PERF #7388: run_all.sh shows PERF lines of a passed suite too).
// freelancer-matrix: n/a (no route; the gestures run in the client only)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7388_calpinch_ui', check, shots: 'P7388_SHOTS', prefs: [['ui.prefersReducedMotion', 0]]});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(400 * (i + 1)); continue; }
    return {status: r.status, ...(await r.json().catch(() => ({})))};
  }
};
const pad = n => String(n).padStart(2, '0');
const dstr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, org_name: 'Studio', modules: ['cal']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events', workspace: 'all'});
  const ORG = ((await call('GET', '/api/state')).me?.workspaces || [])[0]?.id || null;
  const cals = [];
  for (const [name, org] of [['Work', null], ['Home', null], ['Studio', ORG]]) cals.push((await call('POST', '/api/evcals', {name, org_id: org})).id);
  check(cals.every(Boolean), 'setup: three calendars ' + JSON.stringify(cals));
  // a full calendar: ~200 events over five weeks around today (several per day, overlapping), 12 daily repeats
  const t0 = new Date(); let n = 0;
  for (let dd = -17; dd <= 17; dd++) {
    const day = new Date(t0.getFullYear(), t0.getMonth(), t0.getDate() + dd), ds = dstr(day);
    for (let i = 0; i < 6; i++) {
      const h = 7 + ((i * 3 + dd + 40) % 12), m = (i * 15) % 60, len = 30 + (i % 4) * 30;
      const end = new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, m + len);
      const r = await call('POST', '/api/events', {title: `Meeting ${dd}/${i}`, cal_id: cals[(i + dd + 30) % 3], start: `${ds}T${pad(h)}:${pad(m)}`, end: `${dstr(end)}T${pad(end.getHours())}:${pad(end.getMinutes())}`, reminders: []});
      if (r.id) n++;
    }
  }
  for (let i = 0; i < 12; i++) if ((await call('POST', '/api/events', {title: `Daily ${i}`, cal_id: cals[i % 3], start: `${dstr(t0)}T${pad(8 + i)}:00`, end: `${dstr(t0)}T${pad(8 + i)}:45`, rrule: 'FREQ=DAILY', reminders: []})).id) n++;
  check(n >= 200, 'setup: a full calendar (' + n + ' events)');

  await firefox(async ({cmd, ev, nav: go, ctx, shot}) => {
    await go(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');
    const wait = async (js, k = 80) => { for (let i = 0; i < k; i++) { if (await ev(js).catch(() => false)) return true; await sleep(150); } return false; };
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 915}});
    check(await wait(`innerWidth === 412`, 40), 'Firefox: a phone');
    await go(B + '#cal');
    check(await wait(`typeof cgs_pzStart === 'function' && isTouch() && !!document.querySelector('#view .calbar')`, 100), 'Firefox: the calendar on a touch screen');
    // the page's own probe: the renderView calls and the frames of a pinch sent as a browser sends it
    await ev(`(() => {
      if (!window.__rvWrap) { const rv = window.renderView; window.__rv = 0; window.renderView = function () { window.__rv++; return rv.apply(this, arguments); }; window.__rvWrap = 1; }
      window.__pinch = async ({ax, from, to, steps = 36, late = 0}) => {
        const wb = document.getElementById('wbody'), r = wb.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + Math.min(260, r.height / 2);
        const el = document.elementFromPoint(cx, cy) || wb;  // the element under the fingers (a column, an event)
        const at = f => { const hx = ax.includes('x') ? 60 * f : 0, hy = ax.includes('y') ? 60 * f : 0; return [[cx - hx, cy - hy], [cx + hx, cy + hy]]; };
        const tc = (type, pts) => { const e = new Event(type, {bubbles: true, cancelable: true}); const ts = pts.map(([x, y], i) => ({identifier: i, clientX: x, clientY: y, target: el}));
          Object.defineProperty(e, 'touches', {value: type === 'touchend' ? ts.slice(0, pts.length - 1) : ts}); Object.defineProperty(e, 'changedTouches', {value: ts}); el.dispatchEvent(e); };
        const raf = () => new Promise(res => requestAnimationFrame(res));
        const idle = []; let t = await raf();
        for (let i = 0; i < 30; i++) { const u = await raf(); idle.push(u - t); t = u; }
        const h0 = weekH(), n0 = calGridDays().nf;
        const p0 = at(from);
        tc('touchstart', [p0[0]]);
        if (late) for (let i = 1; i <= 3; i++) tc('touchmove', [[p0[0][0] - late * i / 3, p0[0][1]]]);
        const t1 = performance.now(); tc('touchstart', p0); const startMs = performance.now() - t1;
        await raf(); t = await raf();
        const rv0 = window.__rv, fr = [];
        for (let i = 1; i <= steps; i++) { tc('touchmove', at(from + (to - from) * i / steps)); const u = await raf(); fr.push(u - t); t = u; }
        const u = await raf(); fr.push(u - t);
        const live = {pz: !!CGS.pz, kx: CGS.pz ? Math.round(CGS.pz.kx * 100) / 100 : null, ky: CGS.pz ? Math.round(CGS.pz.ky * 100) / 100 : null, nf: CAL_LIVE ? Math.round(CAL_LIVE.nf * 100) / 100 : null, h: CGS.pz ? Math.round(CGS.pz.H) : null};
        const rv = window.__rv - rv0;
        tc('touchend', at(to)); tc('touchend', [at(to)[0]]);
        await raf(); await raf();
        const s = a => [...a].sort((x, y) => x - y), q = (a, k) => s(a)[Math.min(a.length - 1, Math.floor(a.length * k))];
        return {ax, from, to, late, startMs: Math.round(startMs), rv, idleMed: Math.round(q(idle, .5) * 10) / 10, idleMax: Math.round(Math.max(...idle) * 10) / 10,
          frMed: Math.round(q(fr, .5) * 10) / 10, frP95: Math.round(q(fr, .95) * 10) / 10, frMax: Math.round(Math.max(...fr) * 10) / 10, over32: fr.filter(x => x > 32).length,
          live, after: {pz: !!CGS.pz, live: !!CAL_LIVE, dz: !!document.querySelector('#view .week.cgs-dz'), mode: S.calMode, days: calGridDays().nf, h: weekH()}, h0, n0};
      };
      return 1; })()`);
    const week = async () => {
      await ev(`(() => { CAL_LIVE = null; CGS.pz = null; S.calMode = 'week'; LS.set('calMode', 'week'); LS.set('calDays', 7); LS.set('calHourH', 44); S.calSel = today(); renderView(); return 1; })()`);
      return wait(`!!document.querySelector('#view #wbody .wcol') && document.querySelectorAll('#view #wbody .wcev').length > 20 && !CGS.pz`);
    };
    const runs = [
      ['together sideways: more days', {ax: 'x', from: 1, to: .45}, m => m.live.nf >= 13 && m.after.days >= 13],
      ['spread sideways: fewer days', {ax: 'x', from: 1, to: 2.6}, m => m.live.nf <= 3.2 && m.after.days <= 3],
      ['up / down: the hours', {ax: 'y', from: 1, to: 1.8}, m => m.live.ky >= 1.75 && m.after.days === 7 && m.after.h > m.h0 * 1.6],
      ['diagonal: both', {ax: 'xy', from: 1, to: 1.8}, m => m.live.ky >= 1.75 && m.live.nf <= 4.5 && m.after.h > m.h0 * 1.5 && m.after.days <= 5],
      ['a second finger 16 px late, together sideways', {ax: 'x', from: 1, to: .5, late: 16}, m => m.live.nf >= 12],
    ];
    for (const [what, o, follows] of runs) {
      check(await week(), `${what}: the week with its events`);
      await sleep(400);
      const m = await ev(`__pinch(${JSON.stringify(o)})`);
      console.log(`PERF #7388 ${what}:`, JSON.stringify(m));
      check(m.live.pz && follows(m), `${what}: the zoom follows the fingers to their last move ` + JSON.stringify(m.live) + ' ' + JSON.stringify(m.after));
      check(m.rv === 0, `${what}: no renderView while the fingers move (${m.rv})`);
      const lim = Math.max(32, 2 * m.idleMax);
      check(m.frMax <= lim, `${what}: no frame over ${lim} ms (max ${m.frMax}, p95 ${m.frP95}, idle ${m.idleMed} / ${m.idleMax})`);
      check(!m.after.pz && !m.after.live && !m.after.dz, `${what}: the pinch ends with the fingers, the grid drawn once ` + JSON.stringify(m.after));
    }
    await shot('p7388-after.png');
  }, true);

  console.log(`p7388_calpinch_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
