// 2.1170.0 (#6140) UI test, part D, own container (start.sh), Firefox with a mouse. Invented data only.
// kalmido-suite:
// - Polish lists, round 2 - the content area gets narrow (820 px, or a computer with a task open): cards and bars stack instead of
// being squeezed. Per width (820 and 1280 with a task open):
// - the archive card: the whole name readable, the buttons UNDER the text (Open starts below the name)
// - a list's calendar: the month name AND the view switch (Month / Week / Day / Agenda) stay visible
// - the selection bar ("3 selected"): at the bottom in the width of the list area, type >= 13 px, the last row is not covered
// - the task panel's breadcrumb: the section sign stands in the same row as the breadcrumb
// freelancer-matrix: Listen bei mittlerer Breite (alice has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21170_d_listen_breite_ui', check, shots: 'P21170D_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const pad = n => String(n).padStart(2, '0');

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,kanban,timeline,collab,comments,events'});
  const me = (await call('GET', '/api/state')).me;
  const now = new Date(), MID = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`;
  const LONG = 'Documentary about the old harbour and its people - season two';
  const A = await call('POST', '/api/lists', {name: LONG, kind: 'project'});
  await call('POST', '/api/tasks', {title: 'Archived one', list_id: A.id});
  await call('PATCH', `/api/lists/${A.id}`, {archived: true});
  const L = await call('POST', '/api/lists', {name: 'Editorial plan'});
  await call('PATCH', `/api/lists/${L.id}`, {view: 'calendar'});
  const T = [];
  for (const n of ['One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight']) T.push((await call('POST', '/api/tasks', {title: 'Task ' + n, list_id: L.id, due: MID, assignee_id: me.id})).id);
  const P = await call('POST', '/api/lists', {name: 'Plain list'});
  const PT = [];
  for (const n of ['One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve']) PT.push((await call('POST', '/api/tasks', {title: 'Row ' + n, list_id: P.id, assignee_id: me.id})).id);
  check(A.id && L.id && P.id && PT.every(Boolean), 'setup: lists and tasks');

  await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`);
    const RECT = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length) return null; const b = e.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom, w: b.width, h: b.height}; })()`;
    const closeDetail = () => ev(`(() => { document.querySelector('[data-act="close-detail"]')?.click(); return 1; })()`);

    for (const W of [820, 1280]) {
      const tag = `${W}: `;
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      // ---- archive card
      await nav(B + `?w=${W}#archived`);
      check(await until(`!!S.booted && !!document.querySelector('#view .archv .arow')`), tag + 'the archive shows its card');
      await ev(`(() => { openDetail(${T[0]}); return 1; })()`);  // a computer with a task open: the content area is narrower still
      await sleep(300);
      { const n = await until(`(() => { const e = document.querySelector('#view .arow .aname .n'); return e ? {sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight} : null; })()`);
        check(n && n.sw <= n.cw + 1 && n.sh <= n.ch + 1, tag + 'the archive name is fully readable ' + JSON.stringify(n));
        const nm = await ev(RECT('#view .arow .aname')), op = await ev(RECT('#view .arow .aacts .btn'));
        check(nm && op && op.t >= nm.b - 1, tag + 'the buttons stand under the name ' + JSON.stringify({nm, op})); }
      await shot(`p21170d-archiv-${W}.png`);
      await closeDetail();

      // ---- the list's calendar with a task open
      await nav(B + `?w=${W}#l/${L.id}`);
      check(await until(`!!S.booted && !!document.querySelector('#view .lcal .calbar')`), tag + 'the list opens in its calendar');
      await ev(`(() => { openDetail(${T[0]}); return 1; })()`);
      await until(`!!document.querySelector('#detail .dtitle, #detail #d-title')`);
      await sleep(300);
      { const h2 = await ev(RECT('#view .lcal .calbar h2')), seg = await ev(RECT('#view .lcal .calbar .seg')), bar = await ev(RECT('#view .lcal .calbar'));
        const txt = await ev(`document.querySelector('#view .lcal .calbar h2')?.textContent || ''`);
        check(h2 && h2.w > 40 && /\d{4}/.test(txt), tag + 'the calendar shows the month name ' + txt + ' ' + JSON.stringify(h2));
        check(seg && seg.w > 100 && bar && seg.r <= bar.r + 1 && seg.l >= bar.l - 1, tag + 'the view switch is visible inside the bar ' + JSON.stringify({seg, bar}));
        check(await ev(`document.querySelectorAll('#view .lcal .calbar [data-act="cal-mode"]').length === 4`), tag + 'four views'); }
      await shot(`p21170d-kalender-${W}.png`);
      await closeDetail();

      // ---- the selection bar over a plain list
      await nav(B + `?w=${W}#l/${P.id}`);
      check(await until(`!!S.booted && document.querySelectorAll('#view .row, #view [data-id]').length >= 12`), tag + 'the plain list shows');
      await ev(`(() => { S.multiMode = true; S.multi.clear(); [${PT[0]}, ${PT[1]}, ${PT[2]}].forEach(i => S.multi.add(i)); render(); return 1; })()`);
      await sleep(400);
      { const bar = await until(RECT('#mbar')), v = await ev(RECT('#view')), c = await ev(`(() => { const e = document.querySelector('#mbar .mcount'); return e ? {fs: parseFloat(getComputedStyle(e).fontSize), ff: getComputedStyle(e).fontFamily, txt: e.textContent.trim()} : null; })()`);
        check(c && /3/.test(c.txt) && c.fs >= 13 && !/mono/i.test(c.ff), tag + 'the count is readable (>= 13 px, no code font) ' + JSON.stringify(c));
        check(bar && v && Math.abs(bar.l - v.l) <= 2 && Math.abs(bar.r - v.r) <= 2, tag + 'the bar has the width of the list area ' + JSON.stringify({bar, v}));
        check(bar && bar.b <= 900 && bar.b >= 700, tag + 'the bar sits at the bottom ' + JSON.stringify(bar));
        // the last row can be scrolled clear of the bar
        await ev(`(() => { const v = document.querySelector('#view'); v.scrollTop = v.scrollHeight; return 1; })()`); await sleep(200);
        const last = await ev(`(() => { const rows = [...document.querySelectorAll('#view .row, #view [data-id]')].filter(e => e.getClientRects().length); const e = rows[rows.length - 1]; return e ? e.getBoundingClientRect().bottom : null; })()`);
        const bt = await ev(`document.querySelector('#mbar').getBoundingClientRect().top`);
        check(last != null && last <= bt + 1, tag + 'the last row is not covered by the bar ' + last + ' vs ' + bt); }
      await shot(`p21170d-leiste-${W}.png`);
      await ev(`(() => { S.multi.clear(); S.multiMode = false; render(); return 1; })()`);

      // ---- breadcrumb with the section sign (task panel)
      await nav(B + `?w=${W}#l/${P.id}`);
      await until(`!!S.booted && !!document.querySelector('#view')`);
      await ev(`(() => { openDetail(${PT[0]}); return 1; })()`);
      check(await until(`!!document.querySelector('#detail .dcrumbs')`), tag + 'the task panel has its breadcrumb');
      { const cr = await ev(RECT('#detail .dcrumbs .dcb')), sp = await ev(RECT('#detail .dcrumbs .dcadd, #detail .dcrumbs [data-act="crumb-menu"]'));
        check(!sp || (cr && Math.abs((sp.t + sp.b) / 2 - (cr.t + cr.b) / 2) < cr.h), tag + 'the section sign is in the breadcrumb\'s row ' + JSON.stringify({cr, sp})); }
      await closeDetail();
    }
  }, false);

  console.log(`p21170_d_listen_breite_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
