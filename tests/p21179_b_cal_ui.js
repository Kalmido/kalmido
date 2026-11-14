// 2.1179.0 part B (#6155 calendar polish 2: the phone's month, where the hours start, the timeline): Firefox, real layout,
// kalmido-suite: fresh
// freelancer-matrix: n/a (no route changed; the views are drawn in the client only, tested as alice without an organisation)
// German, invented data only. Phone 360 x 780 (touch), desktop 1280 x 800 (mouse).
// - phone month (dots): a day with five entries shows no "N weitere" (nothing of it runs into the next cells), its dots show
// - week and day start at the working hours: 07:00 in view although a subscribed event sits at 01:00 and an own event of the day
//   before runs until 02:00; an own event at 06:00 pulls the start up to it; working hours set to 08:00 = the day starts there
// - desktop week, three events at once: their titles readable over the block's lines (more than "Dreh…")
// - timeline: one-day events in a row are one "+3" (no "T…" stumps), a tap on it opens their week; a bar wide enough keeps its
//   title in full; Enter on a bar opens the event; on a phone the calendar's name "Drehplanung" breaks at no single letter
// With P21179B_SHOTS: pictures of the views.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21179_b_cal_ui', check, shots: 'P21179B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const CT = process.env.KALMIDO_TEST_CONTAINER || 'kalmido-test';
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const pad = n => String(n).padStart(2, '0');
const ds = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const day = i => { const d = new Date(); d.setDate(d.getDate() + i); return ds(d); };
// Wednesday of the week n weeks ahead (German weeks start on Monday): its Tuesday is in the same week
const wed = n => { const d = new Date(); d.setDate(d.getDate() + 7 * n - ((d.getDay() + 6) % 7) + 2); return ds(d); };
const prev = s => { const d = new Date(s + 'T12:00:00'); d.setDate(d.getDate() - 1); return ds(d); };
const utc = (d, h) => new Date(`${d}T${pad(h)}:00:00`).toISOString().replace(/\.\d+Z$/, 'Z');
// a synced subscription with its events, written like the sync does (as p2361_a_ui)
const py = code => execFileSync('docker', ['exec', CT, 'python', '-c', code], {encoding: 'utf8'}).trim();
const addSub = (name, color, events) => +py(`import json
from kalmido.core.db import connect
c = connect()
c.execute("INSERT INTO cal_subs(user_id,kind,name,color,visible,url,status,created_at) VALUES(1,'ics',?,?,TRUE,'x','ok','2026-01-01T00:00:00Z')", (${JSON.stringify(name)}, ${JSON.stringify(color)}))
sid = c.execute('SELECT MAX(id) FROM cal_subs').fetchone()[0]
for t, d0, d1, allday, st, en in json.loads(${JSON.stringify(JSON.stringify(events))}):
    c.execute('INSERT INTO cal_events(sub_id,uid,title,all_day,start,"end",d0,d1) VALUES(?,?,?,?,?,?,?,?)', (sid, t, t, allday, st, en, d0, d1))
c.commit(); c.close(); print(sid)`);

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'de'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal']});
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done', features: 'cal,events,timeline'});
  const W = await call('POST', '/api/evcals', {name: 'Drehplanung', color: '#2dd4bf'});
  const T = await call('POST', '/api/evcals', {name: 'Termine', color: '#f5b041'});
  check(W.id && T.id, 'two calendars');
  const X = wed(1), Y = wed(2);  // X: night and subscription; Y: an own event at 06:00
  const evs = [
    [W, `${prev(X)}T22:00`, `${X}T02:00`, 'Nachtdreh'],
    [W, `${X}T10:00`, `${X}T11:00`, 'Drehbesprechung'], [W, `${X}T10:00`, `${X}T11:00`, 'Telefonat Stadtwerke'], [T, `${X}T10:00`, `${X}T11:00`, 'Imagefilm Schnitt'],
    [W, `${X}T13:00`, `${X}T14:00`, 'Mittag'], [W, `${X}T15:00`, `${X}T16:00`, 'Tonmischung'],
    [W, `${Y}T06:00`, `${Y}T07:00`, 'Frühdreh']];
  for (const [c, a, b, title] of evs) { const r = await call('POST', '/api/events', {title, cal_id: c.id, start: a, end: b}); check(r.http < 300, 'event ' + title + ' ' + r.http); }
  // the timeline: three one-day events in a row and one of four days right after them (the third one has no room either)
  for (const [d0, d1, title] of [[day(1), day(2), 'Tonaufnahme'], [day(2), day(3), 'Sprecher'], [day(3), day(4), 'Dreh im Studio'], [day(4), day(8), 'Messe Berlin']]) {
    const r = await call('POST', '/api/events', {title, cal_id: T.id, all_day: true, start: d0, end: d1}); check(r.http < 300, 'all-day event ' + title + ' ' + r.http + ' ' + JSON.stringify(r).slice(0, 120));
  }
  addSub('Fußball Abo', '#9b59b6', [['Spiel in Übersee', X, X, 0, utc(X, 1), utc(X, 2)]]);

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  const start = async (ev, nav, mode) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.calMode', '"${mode}"'); localStorage.setItem('tasks.calDays', '7'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#cal');
  };
  const show = (ev, mode, sel) => ev(`(() => { S.calSel = '${sel}'; S.calMonth = '${sel.slice(0, 7)}'; S.calMode = '${mode}'; LS.set('calMode', '${mode}'); renderView(); return 1; })()`);
  const has = t => `[...document.querySelectorAll('#view .wcev')].some(x => x.textContent.includes(${JSON.stringify(t)}))`;
  // which hour sits at the top of the hour grid (the grid starts 12 px above it) and whether that hour's label is in view
  const TOP = `JSON.stringify((() => { const wb = document.querySelector('#wbody'), H = weekH(); return {h: (wb.scrollTop + 12) / H, max: wb.scrollHeight - wb.clientHeight}; })())`;
  const vis = t => `(() => { const wb = document.querySelector('#wbody').getBoundingClientRect(), x = [...document.querySelectorAll('#view .wcev')].find(e => e.textContent.includes(${JSON.stringify(t)})); if (!x) return false; const r = x.getBoundingClientRect(); return r.top >= wb.top - 1 && r.bottom <= wb.bottom + 1; })()`;

  // ---- phone 360
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 780}});
    await start(ev, nav, 'month');
    check(await ready(ev, `S.route?.mod === 'cal' && !!document.querySelector('#view .cal')`), 'phone: the calendar loaded');
    await show(ev, 'month', X);
    check(await ready(ev, `document.querySelectorAll('#view .cal .cell[data-day="${X}"] .dots i').length >= 2`), 'phone month: the day shows its dots');
    // five entries on X: no "+N weitere" on a phone, nothing of the cell runs over into the next one
    const m = JSON.parse(await ev(`JSON.stringify((() => {
      const c = document.querySelector('#view .cal .cell[data-day="${X}"]'), cr = c.getBoundingClientRect(), more = c.querySelector('button.more');
      const over = [...c.querySelectorAll('*')].filter(e => e.offsetParent && e.getBoundingClientRect().width > 0).filter(e => { const r = e.getBoundingClientRect(); return r.right > cr.right + 1 || r.left < cr.left - 1; }).map(e => e.className);
      const words = [...document.querySelectorAll('#view .cal *')].filter(e => e.offsetParent && /weitere/.test(e.innerText || '')).length;
      return {more: more ? getComputedStyle(more).display : 'none', over, words};
    })())`));
    check(m.more === 'none' && m.words === 0 && m.over.length === 0, 'phone month: no "N weitere", nothing over the next cell ' + JSON.stringify(m));
    await shot('p21179-b-month-360.png');

    // the week of X starts at 07:00 (the subscription at 01:00 and the night shoot until 02:00 do not pull it up)
    await show(ev, 'week', X);
    check(await ready(ev, `${has('Spiel in Übersee')} && ${has('Nachtdreh')} && ${has('Mittag')}`), 'phone week: the subscription, the night shoot and the day drawn');
    await sleep(300);
    const w1 = JSON.parse(await ev(TOP));
    check(Math.abs(w1.h - 7) < 0.1, 'phone week: starts at 07:00 despite 01:00 / until 02:00 ' + JSON.stringify(w1));
    await shot('p21179-b-week-360.png');

    // timeline on a phone: the name "Drehplanung" breaks at no single letter
    await show(ev, 'timeline', day(0));
    check(await ready(ev, `[...document.querySelectorAll('#view .tl-cal .tln')].some(x => x.textContent === 'Drehplanung')`), 'phone timeline: the calendar rows');
    const lines = JSON.parse(await ev(`JSON.stringify((() => {
      const n = [...document.querySelectorAll('#view .tl-cal .tln')].find(x => x.textContent === 'Drehplanung'), t = n.firstChild, rg = document.createRange(), out = [];
      let top = null, cur = '';
      for (let i = 0; i < t.length; i++) { rg.setStart(t, i); rg.setEnd(t, i + 1); const r = rg.getBoundingClientRect(); if (top !== null && Math.abs(r.top - top) > 2) { out.push(cur); cur = ''; } top = r.top; cur += t.data[i]; }
      out.push(cur); return out;
    })())`));
    check(lines.join('') === 'Drehplanung' && lines.every(l => l.length >= 3), 'phone timeline: "Drehplanung" breaks at no single letter ' + JSON.stringify(lines));
    await shot('p21179-b-timeline-360.png');
  }, true);

  // ---- desktop 1280
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 800}});
    await start(ev, nav, 'week');
    check(await ready(ev, `S.route?.mod === 'cal' && !!document.querySelector('#view #wbody')`), 'desktop: the calendar loaded');
    await show(ev, 'week', X);
    check(await ready(ev, `${has('Spiel in Übersee')} && ${has('Nachtdreh')} && ${has('Drehbesprechung')}`), 'desktop week: the events of X drawn');
    await sleep(300);
    const w1 = JSON.parse(await ev(TOP));
    check(Math.abs(w1.h - 7) < 0.1, 'desktop week: starts at 07:00 despite the subscription at 01:00 and the night shoot until 02:00 ' + JSON.stringify(w1));
    check(await ev(vis('Drehbesprechung')) && !(await ev(vis('Spiel in Übersee'))), 'desktop week: the morning in view, 01:00 above it');
    // three at once: each title readable over the block's lines (letters in view, not "Dreh…")
    const seen = JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('#view .wcol[data-day="${X}"] .wcev.wn3')].map(x => {
      const t = x.querySelector('.wct'), br = x.getBoundingClientRect(), rg = document.createRange(), w = document.createTreeWalker(t, NodeFilter.SHOW_TEXT); let n = 0, all = '';
      for (let tn = w.nextNode(); tn; tn = w.nextNode()) for (let i = 0; i < tn.length; i++) { rg.setStart(tn, i); rg.setEnd(tn, i + 1); const r = rg.getBoundingClientRect(); all += tn.data[i]; if (r.width > 0 && r.bottom <= br.bottom + 1 && r.right <= br.right + 1 && /\\S/.test(tn.data[i])) n++; }
      return {t: all, n};
    }))`));
    check(seen.length === 3 && seen.every(s => s.n >= Math.min(8, s.t.replace(/\s/g, '').length)), 'desktop week: three at once show at least 8 letters of each title ' + JSON.stringify(seen));
    await shot('p21179-b-week-1280.png');

    // an own event at 06:00 pulls the start up
    await show(ev, 'week', Y);
    check(await ready(ev, has('Frühdreh')), 'desktop week of Y drawn');
    await sleep(300);
    const w2 = JSON.parse(await ev(TOP));
    check(Math.abs(w2.h - 6) < 0.1 && await ev(vis('Frühdreh')), 'desktop week: an own event at 06:00 = the hours start at 06:00 ' + JSON.stringify(w2));
    // the day view of X: 07:00 too
    await show(ev, 'day', X);
    check(await ready(ev, `!!document.querySelector('#view .week.oneday') && ${has('Drehbesprechung')}`), 'desktop day of X');
    await sleep(300);
    const d1 = JSON.parse(await ev(TOP));
    check(Math.abs(d1.h - 7) < 0.1, 'desktop day: starts at 07:00 ' + JSON.stringify(d1));
    // working hours from 08:00: the day starts there
    const st = await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({work_start: '08:00'})}).then(r => r.status)`);
    await ev(`(() => { S.settings.work_start = '08:00'; S.calMode = 'week'; renderView(); S.calMode = 'day'; renderView(); return 1; })()`);
    await sleep(300);
    const d2 = JSON.parse(await ev(TOP));
    check(st < 300 && Math.abs(d2.h - 8) < 0.1, 'desktop day: working hours from 08:00 = the day starts at 08:00 ' + st + ' ' + JSON.stringify(d2));

    // the timeline: one-day neighbours are one "+3", a wide bar keeps its title, Enter opens an event
    await ev(`(() => { S.settings.work_start = '09:00'; return 1; })()`);
    await show(ev, 'timeline', day(0));
    // (the events of the timeline's range, not the day's range still loaded before: Tonaufnahme is only in the former)
    check(await ready(ev, `[...document.querySelectorAll('#view .tl-cev span')].some(x => x.textContent === 'Messe Berlin') && [...document.querySelectorAll('#view .tl-cev')].some(x => /Tonaufnahme/.test(x.title))`), 'desktop timeline drawn');
    check(await ev(`tlDW() - 4 < tlMinW()`), 'desktop timeline: a day is too narrow for a title (premise)');
    const tl = JSON.parse(await ev(`JSON.stringify((() => {
      const g = [...document.querySelectorAll('#view .tl-cev.tlmore')].find(b => /Tonaufnahme/.test(b.title));
      const spans = [...document.querySelectorAll('#view .tl-cev span')].filter(s => s.offsetParent).map(s => ({t: s.textContent, w: Math.round(s.getBoundingClientRect().width), cut: s.scrollWidth > s.clientWidth + 1}));
      const messe = spans.find(s => s.t === 'Messe Berlin');
      const rows = [...document.querySelectorAll('#view .tl-cal')].map(r => (r.querySelector('.tln')?.textContent || '-') + ': ' + [...r.querySelectorAll('.tl-cev')].map(x => x.className.replace('tl-cev', '').trim() + '|' + (x.getAttribute('title') || '').slice(0, 24) + '|' + x.style.left + '+' + x.style.width).join(' ; '));
      return {g: g ? {t: g.innerText.trim(), title: g.title, bars: g.querySelectorAll('.cvxbar').length, label: g.getAttribute('aria-label')} : null, stumps: spans.filter(s => s.cut && s.w < 48), messe, rows, dw: tlDW(), min: tlMinW()};
    })())`));
    check(tl.g && tl.g.t === '+3' && tl.g.bars === 3 && /Sprecher/.test(tl.g.title) && /Dreh im Studio/.test(tl.g.title) && /3 Termine/.test(tl.g.label), 'desktop timeline: three one-day events in a row = one "+3" ' + JSON.stringify(tl.g || [tl.dw, tl.min, tl.rows]));
    check(tl.stumps.length === 0, 'desktop timeline: no title cut to a few letters ' + JSON.stringify(tl.stumps));
    check(tl.messe && !tl.messe.cut, 'desktop timeline: a four-day bar shows its title in full ' + JSON.stringify(tl.messe));
    await shot('p21179-b-timeline-1280.png');
    // Enter on a bar opens the event (keyboard)
    await ev(`(() => { const b = [...document.querySelectorAll('#view .tl-cev[data-cev]')].find(x => x.textContent === 'Messe Berlin'); b.focus(); b.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); return 1; })()`);
    check(await ready(ev, `/Messe Berlin/.test(document.querySelector('#pop')?.textContent || '')`, 20), 'desktop timeline: Enter on a bar opens the event');
    await ev(`(() => { closePop(); return 1; })()`);
    // a click on "+3" opens the week of its first day with the three in the all-day row
    await ev(`(() => { [...document.querySelectorAll('#view .tl-cev.tlmore')].find(b => /Tonaufnahme/.test(b.title))?.click(); return 1; })()`);
    check(await ready(ev, `S.calMode === 'week' && S.calSel === '${day(1)}' && [...document.querySelectorAll('#view .wad .cev')].some(x => x.textContent.includes('Tonaufnahme'))`), 'desktop timeline: "+3" opens the week with its events');
  });

  console.log(`p21179_b_cal_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
