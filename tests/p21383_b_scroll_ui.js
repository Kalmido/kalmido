// kalmido-suite:
// 2.1383.0 B UI test (#6935: scrolling long lists like "Built" is sluggish), own container (start.sh), Firefox 1440 (mouse)
// and 390 (touch). A list like the dev list "Built": 300 sections (one per version) with 4 tasks each (1,200 rows, windowed by
// vlist.js), invented data written straight into the test database (like p2411_done_perf_ui.js).
// The measured cause (throwaway suite on the Mac): vl_sync looked up both spacers of EVERY section in the whole view on every
// frame and measured sections without a drawn row - 42 ms per frame with 300 sections. The checks count work, not time
// (no time limits that wobble in the CI):
// - one vl_sync after a scroll step does a handful of view-wide lookups (querySelector), not some per section
// - usable: real wheel input scrolls the list, scrolling down reaches the last task of the last section, back up shows the first
//   one again, the drawn rows stay few; a click on a row deep in the list opens it
// PERF lines name the lookups and the frame times of a scroll down (information only)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21383_b_scroll_ui', check, shots: 'P21383B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const SECS = 300, PER = 4;
const perf = (k, v) => console.log(`PERF p21383_b ${k} = ${typeof v === 'number' ? Math.round(v * 10) / 10 : JSON.stringify(v)}`);

(async () => {
  execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
  await call('POST', '/api/admin/setup', {lang: 'en', modules: ['kanban']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'kanban'});
  const BUILT = (await call('POST', '/api/lists', {name: 'Built'})).id;
  check(BUILT, 'setup: the list');
  execFileSync('docker', ['exec', '-w', '/app', process.env.KALMIDO_TEST_CONTAINER || 'kalmido-test', 'python', '-c', `
import datetime
from kalmido.core.db import connect
from kalmido.core.pg import insert_id
c = connect()
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
for k in range(${SECS}):
    s = insert_id(c, "INSERT INTO sections(list_id, name, sort) VALUES(?,?,?)", (${BUILT}, f"Version 2.{1400 - k}", k))
    for i in range(${PER}):
        n = k * ${PER} + i
        c.execute("INSERT INTO tasks(list_id, section_id, title, priority, sort, created_at, updated_at, created_by) VALUES(?,?,?,0,?,?,?,1)",
                  (${BUILT}, s, f"Task {n:04d} of version 2.{1400 - k}", n, now, now))
c.execute("UPDATE settings SET value=CAST(CAST(value AS BIGINT)+1 AS TEXT) WHERE key='version'")
c.commit()
c.close()
`], {stdio: ['ignore', 'ignore', 'inherit']});
  const LAST = `Task ${String(SECS * PER - 1).padStart(4, '0')} of version 2.${1400 - SECS + 1}`, FIRST = 'Task 0000 of version 2.1400';

  for (const [vw, vh, touch] of [[1440, 900, false], [390, 844, true]]) await firefox(async ({cmd, ev, ctx, nav, until, shot}) => {
    const tag = String(vw), frame = `await new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)))`;
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: vw, height: vh}});
    await nav(B + '#l/' + BUILT);
    await until(`!!document.querySelector('#view .trow')`, {timeout: 20000});
    const st0 = await ev(`({vl: VL.on, segs: VL.segs.length, rows: document.querySelectorAll('#view .trow').length})`);
    check(st0.vl && st0.segs >= SECS && st0.rows < 300, `${tag}: the list is windowed per section ` + JSON.stringify(st0));
    // the lookups of one vl_sync after a scroll step, counted on the view (querySelector / querySelectorAll of any element)
    const look = await ev(`(async () => { const v = document.getElementById('view'), out = [], rc = [];
      const qs = Element.prototype.querySelector, qa = Element.prototype.querySelectorAll, gb = Element.prototype.getBoundingClientRect; let n = 0, m = 0;
      Element.prototype.querySelector = function () { n++; return qs.apply(this, arguments); };
      Element.prototype.querySelectorAll = function () { n++; return qa.apply(this, arguments); };
      Element.prototype.getBoundingClientRect = function () { m++; return gb.apply(this, arguments); };
      try { for (let i = 0; i < 30; i++) { v.scrollTop += v.clientHeight * .4; ${frame}; n = 0; m = 0; vl_sync(); out.push(n); rc.push(m); } }
      finally { Element.prototype.querySelector = qs; Element.prototype.querySelectorAll = qa; Element.prototype.getBoundingClientRect = gb; }
      out.sort((a, b) => a - b); rc.sort((a, b) => a - b); return {p50: out[15], max: out[29], rects50: rc[15], rectsMax: rc[29]}; })()`);
    perf(`${tag} lookups per vl_sync`, look);
    // 2.1383.0 (#6935): before the fix 4 lookups per section and pass (about 1,500 with 300 sections), now a few per pass
    check(look.max < 40, `${tag}: one vl_sync does a handful of view-wide lookups, not some per section ` + JSON.stringify(look));
    // 2.1383.0 (#6935): the scrolling box's place once per pass, the anchor found by halving: about one rectangle per section
    // and pass (before: three per section plus every head above the screen)
    check(look.rectsMax < SECS * 2, `${tag}: one vl_sync reads about one rectangle per section ` + JSON.stringify(look));
    // usable: real wheel input scrolls the list
    await ev(`(async () => { document.getElementById('view').scrollTop = 0; ${frame}; return 1; })()`);
    const c = await ev(`(() => { const b = document.getElementById('view').getBoundingClientRect(); return {x: Math.round(b.left + b.width / 2), y: Math.round(b.top + b.height / 2)}; })()`);
    await cmd('input.performActions', {context: ctx, actions: [{type: 'wheel', id: 'w1', actions: Array.from({length: 20}, () => ({type: 'scroll', x: c.x, y: c.y, deltaX: 0, deltaY: 100, duration: 16}))}]});
    const wst = await until(`document.getElementById('view').scrollTop > 500 && document.getElementById('view').scrollTop`, {timeout: 5000});
    check(wst > 500, `${tag}: the wheel scrolls the list (${wst})`);
    // down to the end and back up
    const down = await ev(`(async () => {
      const v = document.getElementById('view'), fr = []; let maxRows = 0, steps = 0;
      while (v.scrollTop + v.clientHeight < v.scrollHeight - 2 && steps < 600) {
        const t = performance.now(); v.scrollTop += v.clientHeight * .9; vl_sync(); ${frame}; fr.push(performance.now() - t); steps++;
        maxRows = Math.max(maxRows, document.querySelectorAll('#view .trow').length);
      }
      fr.sort((a, b) => a - b);
      const vr = v.getBoundingClientRect(), vis = [...document.querySelectorAll('#view .trow[data-id]')].filter(r => { const b = r.getBoundingClientRect(); return b.bottom > vr.top && b.top < vr.bottom; });
      return {steps, maxRows, p50: fr[Math.floor(fr.length / 2)] || 0, p95: fr[Math.floor(fr.length * .95)] || 0, last: vis.map(r => S.tasks.get(+r.dataset.id)?.title).pop()};
    })()`);
    perf(`${tag} scroll down`, down);
    check(down.last === LAST, `${tag}: scrolling down reaches the last task ` + JSON.stringify(down.last));
    check(down.maxRows < 300, `${tag}: the drawn rows stay few while scrolling (${down.maxRows})`);
    await shot(`p21383b_${tag}_end.png`);
    // a row deep in the list opens
    const tgt = await ev(`(() => { const vr = document.getElementById('view').getBoundingClientRect(); const r = [...document.querySelectorAll('#view .trow[data-id]')].find(x => { const b = x.getBoundingClientRect(); return b.top > vr.top + 40 && b.bottom < vr.bottom - 80; }); if (!r) return null;
      const t = r.querySelector('.ttl') || r, b = t.getBoundingClientRect(); return {id: +r.dataset.id, x: Math.round(b.left + Math.min(40, b.width / 2)), y: Math.round(b.top + b.height / 2)}; })()`);
    if (tgt) {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'c1', parameters: {pointerType: touch ? 'touch' : 'mouse'}, actions: [
        {type: 'pointerMove', x: tgt.x, y: tgt.y}, {type: 'pointerDown', button: 0}, {type: 'pause', duration: 60}, {type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
    }
    const opened = tgt && await until(`S.sel === ${tgt.id} && !document.getElementById('detail').classList.contains('hidden')`, {timeout: 5000});
    check(!!opened, `${tag}: a click on a row deep in the list opens it ` + JSON.stringify(tgt));
    await nav(B + '#l/' + BUILT);
    await until(`!!document.querySelector('#view .trow')`, {timeout: 20000});
    const up = await ev(`(async () => { const v = document.getElementById('view'); v.scrollTop = v.scrollHeight; vl_sync(); ${frame};
      for (let i = 0; i < 600 && v.scrollTop > 0; i++) { v.scrollTop -= v.clientHeight * .9; vl_sync(); ${frame}; }
      const vr = v.getBoundingClientRect(), r = [...document.querySelectorAll('#view .trow[data-id]')].find(x => x.getBoundingClientRect().bottom > vr.top);
      return r && S.tasks.get(+r.dataset.id)?.title; })()`);
    check(up === FIRST, `${tag}: back up shows the first task again ` + JSON.stringify(up));
  }, touch);

  console.log(`p21383_b_scroll_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
