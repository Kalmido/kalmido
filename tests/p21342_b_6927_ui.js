// kalmido-suite: fresh
// 2.1342.0 B (#6927) UI test, own container (start.sh), Firefox with motion on. Invented data only. Ticking a task off with
// "Hide completed" on (#1766): the row folds away to nothing - once its fold has really ended (transitionend of the height) the
// next row sits where the ticked row began (no gap left), and the redraw that follows does not move it (no jump). Phone and
// desktop, a plain list and a list with its own columns (rows .haslc keep their padding with a more specific rule).
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
// the animations run only without "reduce motion" (ff.js sets it on for every suite)
const firefox = require('./ff')({tag: 'p21342_b_6927_ui', check, shots: 'P21342B_SHOTS', prefs: [['ui.prefersReducedMotion', 0]]});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

// in the page: tick the row off, wait for the real end of its fold (transitionend of the height; the redraw first = measured then),
// then for the redraw (toggleTask's promise) and two frames; the next row's top at each step
// n: the n-th row of the list (in screen order, it has a next row)
const MEASURE = n => `(async () => {
  const q = s => document.querySelector(s), row = document.querySelectorAll('#view .trow[data-id]')[${n}];
  if (!row) return {err: 'no row'};
  const id = +row.dataset.id;
  let nx = row.nextElementSibling; while (nx && !(nx.classList.contains('trow') && nx.dataset.id)) nx = nx.nextElementSibling;
  if (!nx) return {err: 'no next row'};
  const nid = nx.dataset.id, top = () => { const n = q('#view .trow[data-id="' + nid + '"]'); return n ? Math.round(n.getBoundingClientRect().top * 10) / 10 : null; };
  const rowTop = Math.round(row.getBoundingClientRect().top * 10) / 10, next0 = top();
  const folded = new Promise(res => { const f = e => { if (e.target === row && e.propertyName === 'height') { row.removeEventListener('transitionend', f); res('folded'); } }; row.addEventListener('transitionend', f); });
  const p = toggleTask(id);
  const first = await Promise.race([folded, p.then(() => 'redrawn')]);
  const atFold = top(), cs = getComputedStyle(row), h = Math.round(row.getBoundingClientRect().height * 10) / 10;
  const box = {pt: cs.paddingTop, pb: cs.paddingBottom, mt: cs.marginTop, mb: cs.marginBottom, bt: cs.borderTopWidth, bb: cs.borderBottomWidth, mh: cs.minHeight};
  await p;
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return {first, rowTop, next0, atFold, h, box, after: top(), gone: !q('#view .trow[data-id="' + id + '"]'), cls: row.className};
})()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en'});
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Plain list'})).id;  // a new list hides completed (#1535)
  const LC = (await call(CA, 'POST', '/api/lists', {name: 'List with columns'})).id;
  await call(CA, 'PATCH', `/api/lists/${LC}`, {columns: ['due', 'who']});
  const mk = async (list, title) => (await call(CA, 'POST', '/api/tasks', {list_id: list, title})).id;
  for (const t of ['Water the plants', 'Buy stamps', 'Call the bakery', 'Fix the shelf', 'Sort the receipts', 'Plan the trip']) { await mk(L, t); await mk(LC, t); }

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const ffLogin = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(x => x.status)`);
  };
  const tick = async (ev, tag, n) => {
    const m = await ev(MEASURE(n));
    const s = `${tag} ` + JSON.stringify(m);
    check(m && !m.err && m.first === 'folded', `#6927 ${tag}: the fold ends before the list redraws ` + s);
    check(m && m.atFold !== null && Math.abs(m.atFold - m.rowTop) <= 1, `#6927 ${tag}: folded, no gap is left (the next row sits where the ticked row began) ` + s);
    check(m && m.after !== null && Math.abs(m.after - m.atFold) <= 1, `#6927 ${tag}: the redraw does not move the next row (no jump) ` + s);
    check(m && m.gone, `#6927 ${tag}: the ticked row is gone after the redraw ` + s);
  };

  for (const [wd, ht, tag, touch] of [[1345, 800, 'desk', false], [390, 800, 'phone', true]]) {
    await firefox(async o => {
      const {cmd, ev, ctx, nav, shot} = o;
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: wd, height: ht}});
      check(await ffLogin(o) === 200, `${tag}: login`);
      check(await ev(`matchMedia('(prefers-reduced-motion: reduce)').matches`) === false, `${tag}: motion is on`);
      await nav(B + '#l/' + L);
      check(await ready(ev, `document.querySelectorAll('#view .trow[data-id]').length >= 3`), `${tag}: the plain list shows its rows`);
      check(await ev(`showDone('l:${L}') === false`), `${tag}: the list hides completed`);
      await tick(ev, `${tag} plain list, first row`, 0);
      await tick(ev, `${tag} plain list, a middle row`, 1);
      await shot(`p21342b-${tag}-plain.png`);
      await nav(B + '#l/' + LC);
      check(await ready(ev, `document.querySelectorAll('#view .trow[data-id]').length >= 3`), `${tag}: the list with columns shows its rows`);
      check(await ev(`!!document.querySelector('#view .trow.haslc[data-id]')`), `${tag}: the rows have the list's columns`);
      await tick(ev, `${tag} list with columns`, 1);
      await shot(`p21342b-${tag}-columns.png`);
    }, touch);
  }

  console.log(`p21342_b_6927_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e.stack); process.exit(1); });
