// kalmido-suite: fresh
// 2.1367.0 part B UI test (jsdom), own container (start.sh; KMT_NOSTART=1: a running server), #6748: arranging the bottom
// bar and the sidebar in Settings on a phone (360 / 412 px).
// - the "…" menu of a settings row takes the icons of its hidden buttons with their turn: "move forward" / "move up" point
//   up, "move back" / "move down" down (multisel.js ms_btnItems -> popovers.js menu, icls)
// - every row of the bottom bar (a child's list in settings.js) and of the sidebar's groups has a grip at its left: a finger
//   holds it (the row lifts, a copy follows), drags, lets go -> the new order is saved (still there after a reload), the mark
//   "from here on More" is on the last place of the bar again; a finger moving on the row outside the grip scrolls, no drag
// - the server takes every sidebar group of the app (settings.py SIDE_GROUPS had no "more": every new order was refused)
// - Settings > Navigation (navmenu.js, the bar of everyone else): the same mark, it follows a drag of the grip
// jsdom lays nothing out: the rows get their boxes here (100 px each).
// freelancer-matrix: settings (alice without an organisation arranges her own bar and sidebar)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return !!c; };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const ORDER = ['s:inbox', 's:today', 's:tomorrow', 's:week', 's:doable', 's:pinned', 's:waiting'];
const W390 = '(min-width: 390px)';
const menuOpen = w => { const p = w.document.querySelector('#pop'); return p && !p.classList.contains('hidden') && p.querySelector('[role="menu"]') ? p : null; };
const items = w => [...(menuOpen(w)?.querySelectorAll('[role="menuitem"]') || [])];
// a finger (drag.js follows touches) and a pointer (navmenu.js), both at y
const tc = (w, el, type, y) => { const e = new w.Event(type, {bubbles: true, cancelable: true}); e.touches = type === 'touchend' || type === 'touchcancel' ? [] : [{clientX: 10, clientY: y}]; el.dispatchEvent(e); };
const pe = (w, el, type, y) => { const C = w.PointerEvent || w.MouseEvent, ev = new C(type, {bubbles: true, cancelable: true, clientX: 10, clientY: y, button: 0});
  for (const [k, v] of [['pointerId', 1], ['pointerType', 'touch']]) if (ev[k] !== v) Object.defineProperty(ev, k, {value: v});
  el.dispatchEvent(ev); };
const lay = rows => rows.forEach((r, i) => { r.getBoundingClientRect = () => ({top: 100 * i, bottom: 100 * i + 100, left: 0, right: 300, width: 300, height: 100}); });
// a browser's click after a drag (swallowed by drag.js)
const after = w => w.document.body.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
// hold the grip until the row is lifted (a real state), drag it to y, let go
async function held(w, row, y) {
  const g = row.querySelector('.rowgrip[data-rowd]'), y0 = [...row.parentElement.children].filter(x => x.matches(row.matches('[data-tab]') ? '[data-tab]' : '.sidegrp')).indexOf(row) * 100 + 50;
  tc(w, g, 'touchstart', y0);
  const lifted = await until(() => row.classList.contains('rowd-on') && w.document.querySelector('.rowd-ghost'), {timeout: 5000});
  tc(w, g, 'touchmove', y); await until(() => w.document.querySelector('.rowd-before, .rowd-after'), {timeout: 3000});
  tc(w, g, 'touchend', y); after(w);
  return !!lifted;
}
const tabRows = d => [...d.querySelectorAll('.smodal #s-tabbar [data-tab]')];
const tabOrder = d => tabRows(d).map(r => r.dataset.tab).join();
const more = d => tabRows(d).findIndex(r => /from here on/.test(r.textContent));
const serverTabs = async () => { const s = (await call('GET', '/api/state')).settings || {}; return (JSON.parse(s.nav_menus || '{}').tabbar?.order || []).join(); };
const serverSide = async () => { const s = (await call('GET', '/api/state')).settings || {}; return (JSON.parse(s.sidebar || '{}').order || []).join(); };
const turned = b => !!b?.querySelector('svg.i')?.classList.contains('up');
// the menu of a row's "…": its entries by name -> does the icon point up
async function dotsMenu(w, row) {
  row.querySelector('.ms-phdots').click();
  const its = await until(() => items(w).length ? items(w) : null, {timeout: 5000}) || [];
  const o = Object.fromEntries(its.map(b => [b.textContent.trim(), turned(b)]));
  w.eval('closePop()');
  return o;
}
// Settings > Appearance on the phone (a child keeps the bottom bar there: S.me.kid; the others edit it under Navigation)
async function look(w, kid) {
  if (kid) w.eval('S.me.kid = 1');
  w.eval(`settingsModal('look')`);
  return until(() => w.document.querySelector('.smodal #s-sidebar .sidegrp') && (!kid || w.document.querySelector('.smodal #s-tabbar [data-tab]')) && w.document.querySelector('.smodal'), {timeout: 10000});
}

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en'});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', nav_menus: JSON.stringify({tabbar: {order: ORDER}})});
  check(!((await call('GET', '/api/state')).orgs || []).length, 'a person without an organisation');

  // ================= the arrows of the "…" menu (360 px)
  let w = await boot({user: 'alice', mobile: true, hash: 'today'}), d = w.document;
  const md = await look(w, true);
  if (check(md, 'phone: Settings with the bottom bar and the sidebar')) {
    const tab = d.querySelectorAll('#s-tabbar [data-tab]')[1];
    const m = await dotsMenu(w, tab);
    check(m['move forward'] === true, '"move forward" points up in the menu: ' + JSON.stringify(m));
    check(m['move back'] === false && m['remove'] === false, '"move back" and "remove" keep their icon unturned: ' + JSON.stringify(m));
    const grp = d.querySelectorAll('#s-sidebar .sidegrp')[1];
    const s = await dotsMenu(w, grp);
    check(s['move up'] === true && s['move down'] === false, 'sidebar: "move up" points up, "move down" down: ' + JSON.stringify(s));
  }

  // ================= dragging the bottom bar by the grip (360 px: 5 places, the mark on the 5th)
  if (md) {
    check(tabRows(d).every(r => r.firstElementChild?.matches('.rowgrip[data-rowd="tabb"]')), 'every row of the bottom bar has the grip at its left');
    check(tabOrder(d) === ORDER.join() && more(d) === 4, 'the own order, the mark on the 5th row: ' + tabOrder(d) + ' / ' + more(d));
    // a finger on the row outside the grip moves (the list scrolls): no drag
    lay(tabRows(d));
    { const lab = tabRows(d)[5].querySelector('span:not(.rowgrip)'); tc(w, lab, 'touchstart', 550); tc(w, lab, 'touchmove', 150); tc(w, lab, 'touchmove', 20); tc(w, lab, 'touchend', 20); }
    check(!d.querySelector('.rowd-on, .rowd-ghost'), 'a finger outside the grip lifts nothing');
    // the 6th row (s:pinned) held at the grip and dragged before the 2nd
    lay(tabRows(d));
    check(await held(w, tabRows(d)[5], 120), 'holding the grip lifts the row, a copy follows the finger');
    const want = ['s:inbox', 's:pinned', 's:today', 's:tomorrow', 's:week', 's:doable', 's:waiting'].join();
    check(await until(async () => await serverTabs() === want, {timeout: 8000}), 'letting go saves the new order (only the drag, not the scroll): ' + await serverTabs());
    check(await until(() => tabOrder(d) === want, {timeout: 5000}), 'the list shows it: ' + tabOrder(d));
    check(more(d) === 4 && tabRows(d)[4].dataset.tab === 's:week', 'the mark "from here on More" follows: on the 5th row again (' + tabRows(d)[more(d)]?.dataset.tab + ')');
    check(!d.querySelector('.rowd-ghost, .rowd-on, .rowd-before, .rowd-after'), 'nothing of the drag stays behind');
    check(w.eval(`tabOverflow().shown.map(t => t.id).join()`) === want.split(',').slice(0, 4).join(), 'the bar itself follows');
  }
  w.close();

  // ================= after a reload: the order stays (412 px: 6 places, the mark on the 6th)
  w = await boot({user: 'alice', mobile: true, hash: 'today', media: {[W390]: true}}); d = w.document;
  if (check(await look(w, true), 'folded phone 412 px: Settings again')) {
    const want = ['s:inbox', 's:pinned', 's:today', 's:tomorrow', 's:week', 's:doable', 's:waiting'].join();
    check(tabOrder(d) === want, 'after the reload the dragged order is there: ' + tabOrder(d));
    check(more(d) === 5, 'the mark on the 6th row at 412 px: ' + more(d));
  }
  w.close();

  // ================= the sidebar's groups (412 px; a person, not a child: the sidebar is everyone's)
  w = await boot({user: 'alice', mobile: true, hash: 'today', media: {[W390]: true}}); d = w.document;
  if (check(await look(w, false), 'sidebar: Settings > Appearance')) {
    const grps = () => [...d.querySelectorAll('.smodal #s-sidebar .sidegrp')];
    check(grps().every(r => r.firstElementChild?.matches('.rowgrip[data-rowd="sideg"]')), 'every group of the sidebar has the grip at its left');
    const g0 = grps().map(r => r.dataset.sideg);
    lay(grps());
    check(await held(w, grps()[2], 20), 'sidebar: holding the grip lifts the group');
    const gw = [g0[2], g0[0], g0[1], ...g0.slice(3)].join();
    check(await until(async () => (await serverSide()).startsWith(gw.split(',').slice(0, 3).join()), {timeout: 8000}), 'sidebar: letting go saves the order of the groups: ' + await serverSide() + ' / ' + gw);
    check(await until(() => grps().map(r => r.dataset.sideg).join() === gw, {timeout: 5000}), 'sidebar: the settings show it');
    // the server knows every group of the app ("More" was refused since 2.45.0: no new order saved, by arrow or drag)
    grps()[0].querySelector('[data-smove="1"]').click();
    const ga = [g0[0], g0[2], g0[1], ...g0.slice(3)].join();
    check(await until(async () => await serverSide() === ga, {timeout: 8000}), 'sidebar: "move down" saves too, with "More" in the order: ' + await serverSide());
  }
  w.close();

  // ================= Settings > Navigation (everyone but a child): the mark in the editor of the bar follows a drag
  w = await boot({user: 'alice', mobile: true, hash: 'today'}); d = w.document;
  w.eval(`settingsModal('nav')`);
  const ed = await until(() => d.querySelector('.smodal .naved[data-naved="tabbar"]'), {timeout: 10000});
  if (check(ed, 'Navigation: the editor of the bottom bar')) {
    const navRows = () => [...d.querySelectorAll('.smodal .naved[data-naved="tabbar"] .navl:not(.navoffl) .navr')];
    const nmore = () => navRows().findIndex(r => r.previousElementSibling?.matches('.navmore'));  // the line above the first point under More
    check(nmore() === 4 && navRows()[4].dataset.k === 's:week', 'Navigation: the line "from here on More" above the 5th point: ' + nmore());
    lay(navRows());
    const g = navRows()[5].querySelector('.navgrip');
    pe(w, g, 'pointerdown', 550); pe(w, d, 'pointermove', 20); pe(w, d, 'pointerup', 20);
    check(await until(async () => (await serverTabs()).startsWith('s:doable,s:inbox'), {timeout: 8000}), 'Navigation: a drag of the grip saves: ' + await serverTabs());
    check(await until(() => nmore() === 4 && navRows()[4].dataset.k === 's:tomorrow', {timeout: 5000}), 'Navigation: the mark follows to the new 5th point: ' + navRows()[nmore()]?.dataset.k);
  }
  w.close();

  console.log(`p21367_b_tabdrag_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
