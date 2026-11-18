// kalmido-suite: fresh
// 2.1385.0 (#6944) UI tests in Firefox (real layout): the tiles of the project page and the start page are one calm unit, fixed
// at the building blocks (povSec / .povs / .povh, the grid .lysix of dashboard.js lyHtml), not per page. Own container (start.sh).
// Invented project, people and figures only.
// - (1) an empty tile: its title and its short hint stand on one line (same middle), the title has no own margins
// - (2) the half tiles of a run stack in two columns: a short tile ("Key links") is not stretched to its tall neighbour
//   ("Members"), the next tile ("Notes") moves up under it instead of waiting below the tall one
// - (3) no visible resize grip while the pointer is on a tile (only on the grip's own corner)
// - (4) "Tracked time": the hours and "66/103 h" in the text font, not the monospace font
// - (5) "Flow": its sub headings are the tiles' sub heading (h4.povsub), not tiny bold h6
// - (6) the project's quotations and approvals below the arranged tiles look like the tiles above (same box, same gap)
// Pictures (P21385A_SHOTS=dir): project page and start page, computer 1440 px and phone 390 px.
// freelancer-matrix: n/a (no route; the project page and the start page are drawn in the client)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21385_a_tiles_ui', check, shots: 'P21385A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'clients,office,collab,time,fields,comments,videos';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice Example', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Example Studio', lang: 'en', collab_all: true, time_all: true, modules: ['comments', 'collab', 'videos']});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'org:' + ORG});
  const P = (await call('POST', '/api/lists', {name: 'Car spot Example', kind: 'project', time_tracking: true, org_id: ORG})).id;
  check(!!P, 'setup: the project');
  await call('PATCH', `/api/lists/${P}/overview`, {description: 'Goal: a 30 second spot for an invented car dealer.'});
  // many members: a tall tile "Members"
  for (const [u, n] of [['bob', 'Bob Baker'], ['carla', 'Carla Cutter'], ['dana', 'Dana Director'], ['emil', 'Emil Editor'], ['fritz', 'Fritz Focus'], ['greta', 'Greta Grip'], ['hanna', 'Hanna Host']]) {
    const id = (await call('POST', '/api/users', {username: u, display_name: n, password: 'password123', email: u + '@example.com', orgs: [{id: ORG, role: 'member'}]})).id;
    if (id) await call('PUT', `/api/lists/${P}/members`, {user_id: id, role: 'edit'});
  }
  // two key links (a short tile), two notes
  for (const [t, u] of [['Storyboard', 'https://example.com/board'], ['Music', 'https://example.org/music']]) await call('POST', `/api/lists/${P}/links`, {url: u, title: t});
  for (const t of ['Kick-off', 'Shot list']) await call('POST', `/api/lists/${P}/notes`, {title: t, body: 'Invented note.'});
  // tracked time 66 h against a budget of 103 h (a number field "Budget h" like p2555_d)
  await call('POST', `/api/lists/${P}/fields`, {name: 'Budget h', type: 'number'});
  const fb = (await call('GET', '/api/state')).fields.find(f => f.list_id === P && f.name === 'Budget h');
  const S1 = (await call('POST', '/api/sections', {list_id: P, name: 'To do'})).id;
  const S2 = (await call('POST', '/api/sections', {list_id: P, name: 'In progress'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Shoot', list_id: P, section_id: S2, fields: fb ? {[fb.id]: '103'} : {}})).id;
  await call('POST', '/api/tasks', {title: 'Grade', list_id: P, section_id: S1});
  for (let i = 0; i < 6; i++) await call('POST', '/api/time/entries', {task_id: T, start: `2026-10-${String(12 + i).padStart(2, '0')}T08:00`, minutes: 660});
  const D = (await call('POST', '/api/tasks', {title: 'Edit', list_id: P, section_id: S2})).id;
  await call('POST', `/api/tasks/${D}/complete`, {});
  // a quotation of the project (the documents below the arranged tiles)
  try {
    await call('PUT', '/api/office/settings', {company_fields: {name: 'Studio Example GmbH', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'de'}});
    const C = await call('POST', '/api/clients', {name: 'Example Client AG', street: 'Marktstrasse 5', zip: '50667', city: 'Koeln', country: 'DE', org_id: ORG});
    const q = await call('POST', '/api/office/docs', {kind: 'offer', project_title: 'Car spot', client_id: C.id});
    await call('PUT', `/api/office/docs/${q.id}/items`, {items: [{title: 'Shoot', qty: 1, rate: 1200}]});
    await call('POST', `/api/office/docs/${q.id}/project`, {list_id: P});
  } catch (e) { console.log('setup: no quotation', e.message); }

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  // the page's scrolling box, scrolled in steps: one picture per screen (at most 4)
  const shotAll = async (ev, shot, name) => {
    const n = await ev(`(() => { let s = document.querySelector('#view'); while (s && s !== document.body && !(s.scrollHeight > s.clientHeight + 2 && /auto|scroll/.test(getComputedStyle(s).overflowY))) s = s.parentElement;
      window.__sc = s && s !== document.body ? s : document.scrollingElement; window.__sc.scrollTop = 0; return Math.min(4, Math.ceil(window.__sc.scrollHeight / (window.__sc.clientHeight * .9))); })()`);
    for (let i = 0; i < n; i++) {
      await ev(`(() => { window.__sc.scrollTop = ${i} * window.__sc.clientHeight * .9; return 1; })()`); await sleep(150);
      await shot(`${name}-${i + 1}.png`);
    }
    await ev(`(() => { window.__sc.scrollTop = 0; return 1; })()`);
  };
  const openProject = async ev => {
    await ev(`(() => { go('l/${P}'); return 1; })()`);
    await ready(ev, `typeof setListView === 'function' && routeList()?.id === ${P}`, 80);
    await ev(`(() => { setListView(routeList(), 'overview'); return 1; })()`);
    return ready(ev, `!!document.querySelector('#pov-people') && !!document.querySelector('#pov-time .tsum') && !!document.querySelector('#pov-flow .flw')`, 100);
  };
  const box = (ev, sel) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return {t: r.top, b: r.bottom, l: r.left, r: r.right, h: r.height}; })()`);

  // ================= computer
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 1000}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#home');
    check(await ready(ev, `S.booted && !!document.querySelector('#view .lysix')`, 100), 'the start page');
    await sleep(600);
    await shotAll(ev, shot, 'p21385a-start-desktop');
    check(await openProject(ev), 'the project page with members, time and flow');
    await sleep(800);

    // (1) an empty tile: title and hint on one middle line, the title without own margins
    const e1 = await ev(`(() => { const s = document.querySelector('.pov .povs-empty .povemh'); if (!s) return null; const h = s.closest('.povh').querySelector('h3'), a = h.getBoundingClientRect(), b = s.getBoundingClientRect(), c = getComputedStyle(h);
      return {id: s.closest('.povs').id, mid: Math.abs((a.top + a.bottom) / 2 - (b.top + b.bottom) / 2), mt: c.marginTop, mb: c.marginBottom}; })()`);
    check(e1 && e1.mid <= 1.5 && e1.mt === '0px' && e1.mb === '0px', '(1) an empty tile: title and hint on one line ' + JSON.stringify(e1));
    // (2) a short tile next to a tall one: not stretched, the next tile moves up under it
    const lk = await box(ev, '#pov-links'), pp = await box(ev, '#pov-people'), nt = await box(ev, '#pov-notes');
    check(lk && pp && pp.h > lk.h + 40, 'setup: "Members" is taller than "Key links" ' + JSON.stringify({lk, pp}));
    check(lk && pp && Math.abs(lk.t - pp.t) <= 1, '(2) the two tiles start on one line ' + JSON.stringify({lk, pp}));
    check(lk && nt && Math.abs(nt.l - lk.l) <= 1 && nt.t - lk.b >= 0 && nt.t - lk.b <= 20, '(2) "Notes" moves up under "Key links" (gap ' + (nt && lk ? Math.round(nt.t - lk.b) : '?') + ' px)');
    // the arranged order stays from top to bottom: Milestones and Project files come before the run of Key links / Members
    const ms = await box(ev, '.lyb[data-lyk="ms"]'), fs = await box(ev, '.lyb[data-lyk="files"]');
    check(ms && fs && lk && ms.b <= fs.t && fs.b <= lk.t, '(2) the run keeps its place in the arranged order ' + JSON.stringify({ms, fs, lk}));
    // (3) the pointer on a tile: no resize grip to see
    const st = await box(ev, '#pov-status') || await box(ev, '#pov-ms');
    if (st) await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm1', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerMove', x: Math.round(st.l + 40), y: Math.round(st.t + st.h / 2), duration: 0}]}]});
    await sleep(300);
    const gr = await ev(`(() => { const g = document.querySelector('.pov .lyb:hover > .lygrip'); return g ? getComputedStyle(g).opacity : 'no-hover'; })()`);
    check(gr === '0', '(3) the pointer on a tile shows no resize grip: opacity ' + gr);
    // (4) tracked time in the text font
    const tf = await ev(`(() => { const b = document.querySelector('#pov-time .tsum b'), n = document.querySelector('#pov-time .tsum .tbn'), bf = getComputedStyle(document.body).fontFamily;
      return {b: b && getComputedStyle(b).fontFamily === bf, n: !n || getComputedStyle(n).fontFamily === bf, txt: (b?.textContent || '') + ' | ' + (n?.textContent || '')}; })()`);
    check(tf.b && tf.n, '(4) "Tracked time": hours and budget in the text font ' + JSON.stringify(tf));
    // (5) the flow's sub headings
    const fl = await ev(`(() => { const s = [...document.querySelectorAll('#pov-flow .povsub')], note = document.querySelector('#pov-flow .flwnote');
      return {n: s.length, h6: document.querySelectorAll('#pov-flow h6').length, fs: s[0] ? parseFloat(getComputedStyle(s[0]).fontSize) : 0, note: note ? parseFloat(getComputedStyle(note).fontSize) : 0, w: s[0] ? +getComputedStyle(s[0]).fontWeight : 0}; })()`);
    check(fl.n === 2 && !fl.h6 && fl.fs > fl.note && fl.w >= 500, '(5) "Flow": two sub headings in the tiles\' style ' + JSON.stringify(fl));
    // (6) the documents below the arranged tiles: the same box and the same gap as the tiles above
    const d6 = await ev(`(() => { const a = document.querySelector('#pov-people'), o = document.querySelector('#pov-officedocs'); if (!o) return null; const ca = getComputedStyle(a), co = getComputedStyle(o);
      const r = o.querySelector('.dpjdoc'), l = document.querySelector('#pov-links .povl'), cr = r && getComputedStyle(r);
      return {same: ['borderTopWidth', 'borderRadius', 'backgroundColor', 'paddingLeft', 'paddingTop'].every(k => ca[k] === co[k]), row: cr ? [cr.borderTopWidth, cr.borderLeftWidth] : null, w: r ? Math.round(r.getBoundingClientRect().width - (o.clientWidth - 2 * parseFloat(co.paddingLeft))) : null}; })()`);
    check(d6 && d6.same, '(6) the quotations below are a tile like the tiles above ' + JSON.stringify(d6));
    check(d6 && d6.row && d6.row[0] === '0px' && d6.row[1] === '0px' && Math.abs(d6.w) <= 2, '(6) a quotation is a row of the tile (no own box, full width) like a key link ' + JSON.stringify(d6));
    const v6 = await ev(`(() => { const v = document.querySelector('#pov-videos'), a = document.querySelector('#pov-people'); if (!v) return 'none'; const ca = getComputedStyle(a), cv = getComputedStyle(v);
      return ['borderTopWidth', 'borderRadius', 'backgroundColor', 'paddingLeft', 'paddingTop'].every(k => ca[k] === cv[k]); })()`);
    check(v6 === true || v6 === 'none', '(6) the approvals below are a tile like the tiles above ' + v6);
    await shotAll(ev, shot, 'p21385a-project-desktop');
  });

  // ================= phone
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#home');
    check(await ready(ev, `S.booted && !!document.querySelector('#view .lysix')`, 100), 'phone: the start page');
    await sleep(600);
    await shotAll(ev, shot, 'p21385a-start-phone');
    check(await openProject(ev), 'phone: the project page');
    await sleep(800);
    // one column: the tiles keep their arranged order from top to bottom
    const ord = await ev(`[...document.querySelectorAll('.pov .lysix .lyb')].filter(x => x.offsetParent).sort((a, b) => (+a.style.order || 0) - (+b.style.order || 0)).map(x => [x.dataset.lyk, Math.round(x.getBoundingClientRect().top), Math.round(x.getBoundingClientRect().left)])`);
    check(ord.length > 3 && ord.every((x, i) => !i || (x[1] > ord[i - 1][1] && x[2] === ord[0][2])), 'phone: one column, top to bottom in the arranged order ' + JSON.stringify(ord));
    const keys = ord.map(x => x[0]);
    check(keys.indexOf('links') < keys.indexOf('people') && keys.indexOf('people') < keys.indexOf('notes'), 'phone: Key links, Members, Notes in this order ' + keys.join(','));
    await shotAll(ev, shot, 'p21385a-project-phone');
  }, true);

  console.log(`p21385_a_tiles_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
