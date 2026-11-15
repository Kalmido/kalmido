// 2.1213.0 (#6140) UI test, part A, own container (start.sh), Firefox. Invented data only.
// kalmido-suite:
// Polish lists, round 2 - the content area gets narrow (820 px, or a computer with a task open): cards and bars stack instead of
// being squeezed. Per width (360 / 820 with a finger, 1280 with a mouse and a task open):
// - the archive card: the whole name readable, the buttons UNDER the name (820, 1280 with a task open)
// - a list's calendar with a task open: the month name AND the view switch (Month / Week / Day / Agenda) stay visible, also after a
//   reload with the task panel open (the state of the finding: only "< Today >" was left)
// - the selection bar ("3 selected"): at the bottom in the width of the list area, type >= 13 px, no code font, the last row is not covered
// - the task panel's breadcrumb (folder > project > section sign): the section sign stands in the breadcrumb's row, not alone below it
// - the cause of the calendar finding: a list scrolled down and then shown as a calendar (switched, or after a reload) drew the
//   calendar at the list's place (viewmem.js kept one place per list, not per view): month and views were out of sight
// freelancer-matrix: Listen bei mittlerer Breite (alice has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21213_a_listen_breite_ui', check, shots: 'P21213A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const pad = n => String(n).padStart(2, '0');

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'de'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
  await call('POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done', features: 'cal,kanban,timeline,collab,comments,events'});
  const me = (await call('GET', '/api/state')).me;
  const now = new Date(), MID = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-15`;
  const LONG = 'Dokumentarfilm über den alten Hafen und seine Menschen - zweite Staffel';
  const A = await call('POST', '/api/lists', {name: LONG, kind: 'project', folder: 'Kunden'});
  await call('POST', '/api/tasks', {title: 'Archivierte Aufgabe', list_id: A.id});
  await call('PATCH', `/api/lists/${A.id}`, {archived: true});
  const L = await call('POST', '/api/lists', {name: 'Imagefilm Stadtwerke Musterstadt', kind: 'project', folder: 'Kunden'});
  await call('PATCH', `/api/lists/${L.id}`, {view: 'calendar'});
  const T = [];
  for (const n of ['Drehgenehmigung', 'Callsheet', 'Kamera-Miete', 'Storyboard', 'Catering', 'Musiklizenz klären', 'Farbkorrektur', 'Rohschnitt'])
    T.push((await call('POST', '/api/tasks', {title: n, list_id: L.id, due: MID, assignee_id: me.id})).id);
  const P = await call('POST', '/api/lists', {name: 'Website-Relaunch Bäckerei Krüger', kind: 'project', folder: 'Kunden'});
  const PT = [];
  for (let i = 1; i <= 40; i++) PT.push((await call('POST', '/api/tasks', {title: 'Zeile ' + i, list_id: P.id, assignee_id: me.id})).id);
  check(A.id && L.id && P.id && T.every(Boolean) && PT.every(Boolean), 'setup: lists and tasks');

  const RECT = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length) return null; const b = e.getBoundingClientRect(); return {l: Math.round(b.left), r: Math.round(b.right), t: Math.round(b.top), b: Math.round(b.bottom), w: Math.round(b.width), h: Math.round(b.height)}; })()`;
  // what of an element is really in sight: inside #view's box and the window, the topmost element at its middle is it or inside it
  const SEEN = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e || !e.getClientRects().length) return false; const b = e.getBoundingClientRect(), v = document.querySelector('#view').getBoundingClientRect();
    if (b.width < 8 || b.height < 8 || b.top < Math.max(0, v.top) - 1 || b.bottom > Math.min(innerHeight, v.bottom) + 1 || b.left < v.left - 1 || b.right > v.right + 1) return false;
    const h = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!h && (h === e || e.contains(h)); })()`;
  const BAR = `(() => { const v = document.querySelector('#view'), bar = document.querySelector('#view .lcal .calbar'); if (!bar) return null;
    return {vst: Math.round(v.scrollTop), vw: Math.round(v.clientWidth), parts: [...bar.children].map(c => { const b = c.getBoundingClientRect(); const s = getComputedStyle(c); return (c.tagName.toLowerCase() + '.' + (c.className || '').toString().split(' ')[0]) + ' ' + Math.round(b.left) + ',' + Math.round(b.top) + ' ' + Math.round(b.width) + 'x' + Math.round(b.height) + ' ' + s.display + (s.visibility !== 'visible' ? ' ' + s.visibility : ''); })}; })()`;

  const WIDTHS = [[360, 740, true], [820, 1100, true], [1280, 800, false]];
  for (const [wi, [W, Hh, touch]] of WIDTHS.entries()) {  // wi: each width its own tasks (Complete in the bar test changes them)
    await firefox(async ({cmd, ev, ctx, nav, shot, until, idle}) => {
      const tag = `${W}: `;
      await nav(B + 'static/icon.svg');
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Hh}});
      await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
      await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`);
      const go = async hash => { await nav(B + 'static/icon.svg'); await nav(B + hash); await until(`!!window.S && !!S.booted && !!document.querySelector('#view')`); await idle({quiet: 300, timeout: 8000}); };
      const open = async id => { await ev(`(() => { openDetail(${id}); return 1; })()`); return until(`!!document.querySelector('#detail .dcrumbs')`); };
      const closeDetail = () => ev(`(() => { document.querySelector('[data-act="close-detail"]')?.click(); return 1; })()`);
      const wide = W > 767;

      // ---- breadcrumb with the section sign (task panel): 360 and 820 are where the sign stood alone below the breadcrumb
      await go(`#l/${P.id}`);
      check(await open(PT[30 + wi]), tag + 'the task panel has its breadcrumb');
      await idle({quiet: 300, timeout: 5000});
      { const cr = await ev(RECT('#detail .dcrumbs .dcb:not(.dcadd)')), sp = await ev(RECT('#detail .dcrumbs .dcadd')), nv = await ev(RECT('#detail .dcrumbs'));
        check(!!sp, tag + 'the section sign is there ' + JSON.stringify(sp));
        check(sp && cr && Math.abs((sp.t + sp.b) / 2 - (cr.t + cr.b) / 2) < 4, tag + 'the section sign is in the breadcrumb\'s row ' + JSON.stringify({cr, sp}));
        check(sp && nv && sp.r <= nv.r + 1, tag + 'the section sign is inside the panel ' + JSON.stringify({sp, nv}));
        const names = await ev(`[...document.querySelectorAll('#detail .dcrumbs .dcb:not(.dcadd)')].map(e => e.textContent.trim())`);
        check(Array.isArray(names) && names.some(n => /Kunden/.test(n)) && names.some(n => /Website/.test(n)), tag + 'folder and project are named in the breadcrumb ' + JSON.stringify(names)); }
      await shot(`p21213a-brotkrume-${W}.png`);
      await closeDetail();
      if (!wide) return;  // the phone: archive, calendar and bar have their own phone layout (stacked already, #5462 / app.css)

      // ---- archive card, with a task open (the content area narrower still)
      await go('#archived');
      check(await until(`!!document.querySelector('#view .archv .arow')`), tag + 'the archive shows its card');
      await open(T[0]); await idle({quiet: 300, timeout: 5000});
      { const n = await ev(`(() => { const e = document.querySelector('#view .arow .aname .n'); return e ? {sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight, txt: e.textContent} : null; })()`);
        check(n && n.sw <= n.cw + 1 && n.sh <= n.ch + 1 && /Hafen/.test(n.txt), tag + 'the archive name is readable, not cut ' + JSON.stringify(n));
        const nm = await ev(RECT('#view .arow .aname')), op = await ev(RECT('#view .arow .aacts .btn')), bt = await ev(`[...document.querySelectorAll('#view .arow .aacts .btn')].map(b => { const r = b.getBoundingClientRect(); return Math.round(r.height); })`);
        check(nm && op && op.t >= nm.b - 1, tag + 'the buttons stand under the name ' + JSON.stringify({nm, op}));
        check(Array.isArray(bt) && bt.length >= 2 && bt.every(h => h < 60), tag + 'the buttons are not squeezed into one word per line ' + JSON.stringify(bt)); }
      await shot(`p21213a-archiv-${W}.png`);
      await closeDetail();

      // ---- the list's calendar with a task open, (1) opened in place, (2) after a reload with the panel open (the finding)
      for (const how of ['open', 'reload']) {
        if (how === 'open') { await go(`#l/${L.id}`); await open(T[5]); }
        else { await nav(B + `#l/${L.id}`); await until(`!!window.S && !!S.booted && !!document.querySelector('#view .lcal .calbar')`); await idle({quiet: 300, timeout: 8000}); if (!await ev(`!!document.querySelector('#detail .dcrumbs')`)) await open(T[5]); }
        await until(`!!document.querySelector('#view .lcal .calbar')`); await idle({quiet: 300, timeout: 5000});
        const t2 = `${tag}${how}: `;
        console.log(t2 + 'calbar', JSON.stringify(await ev(BAR)));
        const txt = await ev(`document.querySelector('#view .lcal .calbar h2')?.textContent || ''`);
        check(/\d{4}/.test(txt) && await ev(SEEN('#view .lcal .calbar h2')), t2 + 'the calendar shows the month name ' + txt + ' ' + JSON.stringify(await ev(RECT('#view .lcal .calbar h2'))));
        check(await ev(SEEN('#view .lcal .calbar .seg')), t2 + 'the view switch is in sight ' + JSON.stringify(await ev(RECT('#view .lcal .calbar .seg'))));
        const modes = await ev(`[...document.querySelectorAll('#view .lcal .calbar [data-act="cal-mode"]')].map(b => { const r = b.getBoundingClientRect(); return r.width > 20 ? b.textContent.trim() : ''; }).filter(Boolean)`);
        check(Array.isArray(modes) && modes.length === 4, t2 + 'all four views readable ' + JSON.stringify(modes));
        check(await ev(SEEN('#view .lcal .calbar [data-act="cal-today"]')), t2 + 'Today is in sight');
        await shot(`p21213a-kalender-${W}-${how}.png`);
      }
      // a click on "Week" in the narrow bar works and the bar stays whole
      await ev(`(() => { document.querySelector('#view .lcal .calbar [data-act="cal-mode"][data-k="week"]').click(); return 1; })()`);
      check(await until(`document.querySelector('#view .lcal .calbar [data-k="week"]')?.getAttribute('aria-pressed') === 'true'`), tag + 'Week can be chosen in the narrow bar');
      check(await ev(SEEN('#view .lcal .calbar h2')), tag + 'the week keeps its title in sight');
      await ev(`(() => { document.querySelector('#view .lcal .calbar [data-act="cal-mode"][data-k="month"]')?.click(); return 1; })()`);
      await closeDetail();

      // ---- the selection bar over a plain list, with a task open on a computer
      await go(`#l/${P.id}`);
      check(await until(`document.querySelectorAll('#view .trow[data-id]').length >= 10`), tag + 'the plain list shows');
      if (!touch) await open(PT[0]);
      await ev(`(() => { S.multiMode = true; S.multi.clear(); [${PT[3 * wi + 1]}, ${PT[3 * wi + 2]}, ${PT[3 * wi + 3]}].forEach(i => S.multi.add(i)); render(); return 1; })()`);
      await until(`!!document.querySelector('#mbar:not(.hidden) .mcount')`); await idle({quiet: 300, timeout: 5000});
      { const bar = await ev(RECT('#mbar')), v = await ev(RECT('#view')), c = await ev(`(() => { const e = document.querySelector('#mbar .mcount'); return e ? {fs: parseFloat(getComputedStyle(e).fontSize), ff: getComputedStyle(e).fontFamily, txt: e.textContent.trim()} : null; })()`);
        check(c && /3/.test(c.txt) && c.fs >= 13 && !/mono/i.test(c.ff), tag + 'the count is readable (>= 13 px, no code font) ' + JSON.stringify(c));
        check(bar && v && Math.abs(bar.l - v.l) <= 2 && Math.abs(bar.r - v.r) <= 2, tag + 'the bar has the width of the list area ' + JSON.stringify({bar, v}));
        check(bar && bar.b <= Hh && bar.b >= Hh - 120, tag + 'the bar sits at the bottom ' + JSON.stringify(bar));
        await ev(`(() => { const v = document.querySelector('#view'); v.scrollTop = v.scrollHeight; return 1; })()`);
        await until(`(() => { const v = document.querySelector('#view'); return v.scrollTop + v.clientHeight >= v.scrollHeight - 2; })()`);
        const last = await ev(`(() => { const rows = [...document.querySelectorAll('#view .trow[data-id]')].filter(e => e.getClientRects().length); const e = rows[rows.length - 1]; return e ? Math.round(e.getBoundingClientRect().bottom) : null; })()`);
        const bt = await ev(`Math.round(document.querySelector('#mbar').getBoundingClientRect().top)`);
        check(last != null && last <= bt + 1, tag + 'the last row can be scrolled clear of the bar ' + last + ' vs ' + bt); }
      await shot(`p21213a-leiste-${W}.png`);
      // the bar's "Complete" still works where it sits now (hinein / weiter)
      await ev(`(() => { document.querySelector('#mbar [data-act="mb-done"]').click(); return 1; })()`);
      check(await until(`[${PT[3 * wi + 1]}, ${PT[3 * wi + 2]}, ${PT[3 * wi + 3]}].every(i => S.tasks.get(i) && S.tasks.get(i).status !== 0)`), tag + 'Complete from the bar completes the three tasks');
      await ev(`(() => { S.multi.clear(); S.multiMode = false; render(); return 1; })()`);
      check(await until(`!!document.querySelector('#mbar.hidden') || !document.querySelector('#mbar')`), tag + 'the bar goes again');
      await closeDetail();

      // ---- a list scrolled down, then its calendar: (1) switched in place, (2) switched elsewhere and reloaded (the finding's path)
      const lst = async () => { await call('PATCH', `/api/lists/${P.id}`, {view: 'list'}); await go(`#l/${P.id}`); await until(`document.querySelectorAll('#view .trow[data-id]').length >= 10`);
        await ev(`(() => { const v = document.querySelector('#view'); v.scrollTop = v.scrollHeight; v.dispatchEvent(new Event('scroll')); return 1; })()`);
        return until(`Object.entries(LS.get('viewMem', {})).some(([k, m]) => k.endsWith('t:l:${P.id}') && m.y > 100)`); };
      const calSeen = async t2 => { await until(`!!document.querySelector('#view .lcal .calbar h2')`); await idle({quiet: 300, timeout: 5000});
        console.log(t2 + 'calbar', JSON.stringify(await ev(BAR)));
        check(await ev(SEEN('#view .lcal .calbar h2')) && await ev(SEEN('#view .lcal .calbar .seg')), t2 + 'month name and views in sight ' + JSON.stringify(await ev(BAR))); };
      check(await lst(), tag + 'the scrolled list keeps its place');
      await ev(`(() => { setListView(listById(${P.id}), 'calendar'); return 1; })()`);
      await calSeen(tag + 'switched: ');
      await shot(`p21213a-kalender-${W}-umgeschaltet.png`);
      check(await lst(), tag + 'the scrolled list keeps its place again');
      await call('PATCH', `/api/lists/${P.id}`, {view: 'calendar'});
      await nav(B + 'static/icon.svg'); await nav(B + `#l/${P.id}`); await until(`!!window.S && !!S.booted`);
      await calSeen(tag + 'reloaded: ');
      await shot(`p21213a-kalender-${W}-neu-geladen.png`);
      // back in the list view it is at its place again (the list's place is still kept)
      await call('PATCH', `/api/lists/${P.id}`, {view: 'list'});
      await go(`#l/${P.id}`); await until(`document.querySelectorAll('#view .trow[data-id]').length >= 10`);
      check(await until(`document.querySelector('#view').scrollTop > 100`), tag + 'the list view comes back at its own place');
    }, touch);
  }

  console.log(`p21213_a_listen_breite_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
