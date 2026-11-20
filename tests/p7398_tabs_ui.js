// kalmido-suite: fresh
// #7398 UI test (regression): a tab switch outside the office keeps the page, as in the office (#7390, render.js tabh_*).
// Before: the tap threw the tab's data away, a "Loading…" block stood in its place, the page shrank, the scroll position fell
// to the top and the view was drawn a second time. Now, for each tab row - time tracking's period (week -> month), the team's
// tabs (workload -> absences), the review's period (day -> week), a table's sheets (sheet 1 -> sheet 2) and the client card's
// month (back one month): while the new data loads, the tab row stays the same node and shows the new tab at once, the last
// content waits dimmed (.tabheld / .ctwait), no loading placeholder enters the page and the scroll position stays; when the
// answer is there the new content is drawn once (MutationObserver: one batch of changes in the view after the answer).
// Firefox at a tablet's (820 px) and a phone's width (390 px), touch. The request of the new tab is held back 1.5 s in the page,
// so the in-between state can be seen. Own container (start.sh), invented data only.
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7398_tabs_ui', check, shots: 'P7398_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), http: r.status};
  }
};
const FEAT = 'time,collab,comments,clients,workload,review,sheets';
const D = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

// in the page: hold the requests matching RE back 1.5 s; count loading placeholders added to the view and the batches of
// changes in the view after the held answer came
const ARM = re => `(() => { const f0 = window.__f0 || (window.__f0 = window.fetch); window.__resp = 0; window.__load = []; window.__after = 0; window.__what = [];
  window.fetch = function (u, o) { const s = String(u && u.url || u); if (${re}.test(s)) return new Promise(r => setTimeout(r, 1500)).then(() => f0.call(this, u, o)).then(x => { window.__resp = performance.now(); return x; }); return f0.apply(this, arguments); };
  const isLoad = n => n.nodeType === 1 && [n, ...n.querySelectorAll('*')].some(e => e.childElementCount === 0 && /^Loading…$/.test(e.textContent.trim()));
  window.__mo?.disconnect();
  window.__mo = new MutationObserver(ms => { const v = document.querySelector('#view'); let hit = false;
    let what = '';
    // a grip a page hangs in again after its draw (lsdgrip, the one grip) is no drawing of the content
    const deco = n => n.nodeType === 1 && n.matches('.lsdgrip, .grip');
    for (const m of ms) { if (m.type !== 'childList' || !v.contains(m.target) || [...m.addedNodes, ...m.removedNodes].every(deco)) continue; hit = true; what = what || (m.target.className || m.target.nodeName).toString().slice(0, 30) + '+' + m.addedNodes.length + '-' + m.removedNodes.length; m.addedNodes.forEach(n => { if (isLoad(n)) window.__load.push((n.className || n.nodeName).toString().slice(0, 40)); }); }
    if (hit && window.__resp) { window.__after++; window.__what.push(what); } });
  window.__mo.observe(document.body, {childList: true, subtree: true});
  return 1; })()`;
// marks the tab row (and what else must stay) and scrolls the view's scrolling box down
const MARK = (row, rowsSel) => `(() => { const r = document.querySelector(${JSON.stringify(row)}); if (!r) return null; r.__keep = 1;
  const n = [...document.querySelectorAll(${JSON.stringify(rowsSel)})].pop() || r, sc = kr_scroller(n) || document.scrollingElement;
  sc.scrollTop = Math.round((sc.scrollHeight - sc.clientHeight) * 0.6); window.__sc = sc;
  return {top: Math.round(sc.scrollTop), max: sc.scrollHeight - sc.clientHeight}; })()`;
const MID = (row, on, held) => `(() => { const r = document.querySelector(${JSON.stringify(row)});
  return {top: Math.round(window.__sc.scrollTop), same: !!r && r.__keep === 1, on: !!document.querySelector(${JSON.stringify(on)}), held: !!document.querySelector(${JSON.stringify(held)}),
    load: window.__load.slice(), resp: !!window.__resp}; })()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Beispiel Film', lang: 'en', collab_all: true, modules: ['comments', 'time']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  for (let i = 1; i <= 14; i++) await call('POST', '/api/users', {username: 'crew' + i, display_name: 'Crew ' + i, password: 'password123', email: `crew${i}@example.com`, orgs: [ORG]});
  // time: a tracked project with 30 tasks, an entry each this week (a long report)
  const P = (await call('POST', '/api/lists', {name: 'Dreh Beispiel', kind: 'project', time_tracking: true})).id;
  for (let i = 0; i < 30; i++) {
    const t = (await call('POST', '/api/tasks', {title: `Drehtag ${i + 1}`, list_id: P, due: D(1 + i % 6)})).id;
    await call('POST', '/api/time/entries', {task_id: t, start: new Date(Date.now() - (i % 3 + 1) * 36e5).toISOString(), minutes: 20 + i, note: 'Schnitt ' + i});
  }
  // a table with two sheets, the first one long
  const S1 = (await call('POST', '/api/sheets', {title: 'Drehplan', space: 'private'})).id;
  await call('POST', `/api/sheets/${S1}/rows`, {count: 50});
  const T2 = (await call('POST', `/api/sheets/${S1}/tabs`, {after_id: S1})).tab?.id;
  // a client with this project
  const C = (await call('POST', '/api/clients', {name: 'Beispielkunde GmbH', org_id: ORG})).id;
  check(P && S1 && T2 && C, 'setup: project, table with two sheets, client ' + JSON.stringify({P, S1, T2, C}));

  const CASES = [
    {name: 'time period', hash: '#time', ready: `!!document.querySelector('#view .ttable .tvt')`, pre: `document.querySelector('[data-act="tv-period"][data-k="week"]:not(.on)')?.click(), 1`,
      re: '/\\/api\\/time\\/report\\?/', row: '#view .tvseg', rows: '#view .ttable tr', tap: '#view [data-act="tv-period"][data-k="month"]',
      on: '#view .tvseg [data-k="month"].on', held: '#view .tabheld .ttable', done: `!document.querySelector('#view .tabheld') && !!document.querySelector('#view .ttable .tvt')`},
    {name: 'team tabs', hash: '#workload', ready: `!!document.querySelector('#view .wltable')`, re: '/\\/api\\/team\\/absences\\?/', row: '#view .ab2tabs', rows: '#view .wltable tr',
      tap: '#view [data-act="ab2-tab"][data-v="abs"]', on: '#view .ab2tabs [data-v="abs"].on', held: '#view .tabheld .wltable',
      done: `!document.querySelector('#view .tabheld') && !!document.querySelector('#view .ab2table')`},
    {name: 'review period', hash: '#review', ready: `!!document.querySelector('#view .rv-next')`, pre: `document.querySelector('[data-act="rv-period"][data-p="day"]:not(.on)')?.click(), 1`,
      re: '/\\/api\\/life\\/review\\?/', row: '#view .rvhead .seg', rows: '#view .rv-next li', tap: '#view [data-act="rv-period"][data-p="week"]',
      on: '#view .rvhead [data-p="week"].on', held: '#view .tabheld .rv-next', done: `!document.querySelector('#view .tabheld') && !!document.querySelector('#view .rvjdays')`},
    {name: 'sheet tabs', hash: '#sheets/' + S1, ready: `!!document.querySelector('#view .shvgrid') && !!document.querySelector('#view .shbtabs')`, re: `/\\/api\\/sheets\\/${T2}(\\?|$)/`,
      row: '#view .shbtabs', rows: '#view .shvgrid tr', tap: `#view .shbtab[data-id="${T2}"]`, on: `#view .shbtab.on[data-id="${T2}"]`, held: '#view .shvwrap[aria-busy="true"] .shzbox.tabheld',
      done: `!!document.querySelector('#view .shvwrap[data-k="shv-${T2}"]') && !document.querySelector('#view [aria-busy="true"]')`, sameAfter: false},
    {name: 'client month', hash: '#client/' + C, ready: `!!document.querySelector('#view .msclcard')`, ready2: `!!document.querySelector('#view .msclcard [data-act="client-month"]')`,
      pre: `(lyOptSet('clients', 'month', 'open', true), renderView(), 1)`, re: `/\\/api\\/clients\\/${C}\\?month=/`, row: '#view .msclcard .clmon', rows: '#view .msclcard section, #view .msclcard .clmon',
      tap: '#view [data-act="client-month"][data-d="-1"]', on: '#view .msclcard.ctwait .clmon', held: '#view .ctcard.ctwait', done: `!document.querySelector('#view .ctwait') && !!document.querySelector('#view .msclcard .clmon')`},
  ];

  for (const [w, h, tag] of [[820, 700, 'tablet'], [390, 700, 'phone']]) {
    await firefox(async ({cmd, ev, ctx, nav, until: fu, idle, shot}) => {
      await nav(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.tour', '"done"'); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, `${tag}: login`);
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
      for (const c of CASES) {
        const t = `#7398 ${tag} ${c.name}`;
        await nav(B + 'static/icon.svg'); await nav(B + c.hash);
        if (!await fu(c.ready, {timeout: 20000})) { check(false, `${t}: the page is there`); continue; }
        if (c.pre) { await ev(c.pre); check(await fu(c.ready2 || c.ready, {timeout: 10000}), `${t}: ready to switch`); }
        await idle({quiet: 400});
        await ev(ARM(c.re));
        const m = await ev(MARK(c.row, c.rows));
        check(!!m, `${t}: the tab row is there`);
        if (!m) continue;
        await ev(`document.querySelector(${JSON.stringify(c.tap)}).click(), 1`);
        check(await fu(`!!document.querySelector(${JSON.stringify(c.held)})`, {timeout: 5000}), `${t}: the last content waits dimmed`);
        const a = await ev(MID(c.row, c.on, c.held));
        check(a && !a.resp, `${t}: seen before the answer ${JSON.stringify(a)}`);
        check(a && a.same && a.on, `${t}: the tab row is the same node and shows the new tab at once ${JSON.stringify(a)}`);
        // the place stays: never back to the top (a card above that comes with the new tab moves the rows down, the view keeps the reading place, render.js keepReading)
        check(a && a.top >= m.top - 1, `${t}: the scroll position stays while it loads ${JSON.stringify({m, a})}`);
        check(a && !a.load.length, `${t}: no loading placeholder in the page ${JSON.stringify(a)}`);
        check(await fu(c.done, {timeout: 10000}), `${t}: the new content stands alone when it is there`);
        await idle({quiet: 600});
        const b = await ev(`({load: window.__load.slice(), after: window.__after, what: window.__what, same: document.querySelector(${JSON.stringify(c.row)})?.__keep === 1})`);
        check(b && !b.load.length, `${t}: never a loading placeholder ${JSON.stringify(b)}`);
        check(b && b.after === 1, `${t}: drawn once after the answer ${JSON.stringify(b)}`);
        if (c.sameAfter !== false) check(b && b.same, `${t}: the tab row is still the same node`);
        await shot(`p7398-${tag}-${c.name.replace(/\W+/g, '-')}.png`);
      }
    }, true);
  }

  console.log(`p7398_tabs_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
