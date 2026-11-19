// 2.1401.0 A (#6127) UI test, Firefox like a person: ONE menu "Switch to" on the head bar (computer), the drawer's brand
// kalmido-suite: fresh
// and the workspace button of a phone - the same entries in the same order (organisations, Private, All workspaces, then
// "Add an organisation", the organisation's settings; my own Settings only in the account menu, decision 17.11.), the pick switches; the words are "organisation", never
// "company" (the dialog of a new one too). The phone's "More" holds only what the tab bar does not show: none of the drawer's
// areas and no News next to the bell. Favourites show their names (a phone's row, a computer's head bar with room), two
// projects with the same symbol are told apart by the name. Own container (workspaces mode), invented data only.
// freelancer-matrix: n/a (navigation, no route; frida without an organisation is checked: Private + "Add an organisation")
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21401_a_nav_ui', check, shots: 'P21401A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

// what a person reads in the open menu: the heading(s) and the entries, top to bottom
const MENU = `(() => ({head: [...document.querySelectorAll('#pop .mgh')].map(x => x.textContent.trim()),
  items: [...document.querySelectorAll('#pop [role="menuitem"]')].filter(x => x.getClientRects().length).map(x => (x.querySelector('.ml') || x).textContent.trim()),
  text: (document.querySelector('#pop') || {}).innerText || ''}))()`;
// a finger swipe up on the tab bar (opens the phone's favourites row, favtiles.js fvd_*)
const SWIPE_UP = `(() => {
  const el = document.querySelector('#tabs button'), r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const fire = (type, Y) => { const t = new Touch({identifier: 7, target: el, clientX: x, clientY: Y}); el.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], targetTouches: type === 'touchend' ? [] : [t], changedTouches: [t]})); };
  fire('touchstart', y); for (let i = 1; i <= 4; i++) fire('touchmove', y - 70 * i / 4); fire('touchend', y - 70); return 1; })()`;
// the names of the favourites as a person sees them: shown, not empty, cut with an ellipsis instead of running out
const NAMES = sel => `(() => [...document.querySelectorAll('${sel} .fv2-tile')].filter(t => !t.hidden).map(t => { const n = t.querySelector('.fv2-nm'), r = n && n.getBoundingClientRect(), cs = n && getComputedStyle(n);
  return {key: t.dataset.fv2, name: n && cs.display !== 'none' && r.width > 4 ? n.textContent : '', ell: !!cs && cs.textOverflow === 'ellipsis', inside: !!n && n.scrollWidth >= n.clientWidth && r.right <= t.getBoundingClientRect().right + 1, w: Math.round(t.getBoundingClientRect().width)}; }))()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  const fr = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  check(fr.http < 300, 'frida (no organisation) ' + fr.http);
  const CF = await login('frida');
  for (const ck of [CA, CF]) await call(ck, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const me = (await call(CA, 'GET', '/api/state')).me;
  await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha Studio', admin_id: me.id});
  // two projects with the same symbol as favourites (the photo of #6127: only the colour of a 16 px symbol told them apart)
  const L1 = (await call(CA, 'POST', '/api/lists', {name: 'Imagefilm Stadtwerke Musterstadt'})).id;
  const L2 = (await call(CA, 'POST', '/api/lists', {name: 'Website Relaunch'})).id;
  for (const L of [L1, L2]) await call(CA, 'PUT', `/api/lists/${L}/favorite`, {on: true});
  await call(CA, 'PATCH', '/api/settings', {fav_items: ['v:today', `l:${L1}`, `l:${L2}`]});
  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(150); } return false; };
  const signIn = async (o, u) => {
    await o.nav(B + 'static/icon.svg');
    await o.ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    return o.ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  };
  const EXPECT = ['Alpha Studio', 'Private', 'All workspaces'];  // 2.1397.0 (#6885): Add an organisation only without an organisation (frida below)
  let desk = null, deskOrg = null;

  // ===== computer, 1280: the head bar's menu, the favourites with names
  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    check(await signIn(o, 'alice') === 200, 'alice: login');
    await nav(B + '#today');
    check(await ready(ev, `!!document.querySelector('#kbar .kbsw') && document.querySelectorAll('#kbar .fv2-tile').length === 3`, 80), 'the head bar with three favourites');
    await ev(`(() => { document.querySelector('#kbar .kbsw').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`), 'the head bar opens its menu');
    desk = await ev(MENU);
    check(desk.head.includes('Switch to') && desk.items.join('|') === EXPECT.join('|'), '#6127 computer: organisations, Private, All (no Add inside an organisation, #6885; no personal Settings) ' + JSON.stringify(desk.items));
    check(!/compan|panel/i.test(desk.text), '#6127 computer: no "company" / "panel" in the menu ' + desk.text);
    await shot('p21401a-menu-1280.png');
    // the pick switches: Alpha Studio, the head bar says so, the menu now offers its settings
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml') || b).textContent.trim() === 'Alpha Studio').click(); return 1; })()`);
    check(await ready(ev, `wsCur().startsWith('org:') && (document.querySelector('#kbar .kbsw .wsn') || {}).textContent === 'Alpha Studio'`), '#6127 computer: the pick switches to the organisation');
    await ev(`(() => { closePop(); document.querySelector('#kbar .kbsw').click(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`);
    deskOrg = await ev(MENU);
    check(deskOrg.items.join('|') === ['Alpha Studio', 'Private', 'All workspaces', 'Organisation settings'].join('|'), '#6127 computer: in the organisation its settings ' + JSON.stringify(deskOrg.items));
    // my own Settings live in the account menu (decision 17.11.: the workspace menu holds only the organisation's)
    await ev(`(() => { closePop(); document.querySelector('#kbar .kbacct').click(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`);
    const acct = await ev(MENU);
    check(acct.items.includes('Settings') && acct.items.includes('Start'), '#6127 computer: the account menu has Start and Settings ' + JSON.stringify(acct.items));
    await ev(`(() => { closePop(); wsSet('private'); return 1; })()`);
    // favourites with their names; the two projects read differently
    await ready(ev, `!document.querySelector('#kbar .fv2bar').classList.contains('fv2-icons')`, 20);
    const N = await ev(NAMES('#kbar .fv2bar'));
    const p1 = N.find(x => x.key === `l:${L1}`), p2 = N.find(x => x.key === `l:${L2}`);
    check(p1 && p2 && p1.name && p2.name && p1.name !== p2.name && p2.name === 'Website Relaunch', '#6127 computer: the head bar shows the favourites\' names ' + JSON.stringify(N));
    check(N.every(x => x.ell && x.w <= 9 * 16 + 1), '#6127 computer: a long name is cut with an ellipsis, a tile stays short ' + JSON.stringify(N));
    check(await ev(`document.querySelector('#kbar .kbsrch').offsetWidth >= 12 * 16 - 1`), '#6127 computer: the names take no room from the search');
    await shot('p21401a-favs-1280.png');
    // tight: the names go first (symbols only), the search keeps its width
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 860, height: 860}});
    check(await ready(ev, `document.querySelector('#kbar .fv2bar').classList.contains('fv2-icons')`, 30), '#6127 860: tight head bar: the names give way first');
    check(await ev(`[...document.querySelectorAll('#kbar .fv2-nm')].every(n => getComputedStyle(n).display === 'none')`), '#6127 860: symbols only');
  }, false);

  // ===== phone, 390: the drawer's brand + the workspace button, "More", the favourites' row
  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    check(await signIn(o, 'alice') === 200, 'alice: login (phone)');
    await nav(B + '#today');
    check(await ready(ev, `S.booted && document.querySelectorAll('#tabs button').length > 0 && !!document.querySelector('#top .menu')`, 80), 'phone: the tab bar is up');
    // 2.1437.0 (#7299): the workspace menu opens from the chip in the header (the drawer's brand leads to Start)
    check(await ready(ev, `!!document.querySelector('#top .wschip')`), 'phone: the chip in the header');
    await ev(`(() => { document.querySelector('#top .wschip').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`), 'phone: the chip opens its menu'); 
    const ph = await ev(MENU);
    check(desk && ph.items.join('|') === desk.items.join('|') && ph.head.join('|') === desk.head.join('|'), '#6127: phone and computer show the same menu, same order ' + JSON.stringify({phone: ph.items, computer: desk && desk.items}));
    check(!/compan|panel|Start|Hide the sidebar/i.test(ph.text), '#6127 phone: no Start / Hide the sidebar / company in the menu ' + ph.text);
    await shot('p21401a-menu-390.png');
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml') || b).textContent.trim() === 'Alpha Studio').click(); return 1; })()`);
    // 2.1437.0 (#7299): the chip sits in the header (the drawer is closed): the pick switches, no drawer opens
    check(await ready(ev, `wsCur().startsWith('org:') && !document.querySelector('#side.open')`), '#6127 / #7299 phone: the pick switches, no drawer');
    await ev(`(() => { closeSide(); return 1; })()`);
    check(await ready(ev, `!document.querySelector('#side.open')`), 'phone: the drawer closes afterwards');
    // the workspace button in the phone's header (shown while one workspace is): the same menu as the computer's in the organisation
    check(await ready(ev, `!!document.querySelector('#top [data-act="ws-menu"]')`), 'phone: the header has the workspace button');
    await ev(`(() => { document.querySelector('#top [data-act="ws-menu"]').click(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`);
    const pb = await ev(MENU);
    check(deskOrg && pb.items.join('|') === deskOrg.items.join('|'), '#6127 phone: the header button has the same menu ' + JSON.stringify({phone: pb.items, computer: deskOrg && deskOrg.items}));
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml') || b).textContent.trim() === 'Private').click(); return 1; })()`);
    check(await ready(ev, `wsCur() === 'private'`), '#6127 phone: back to Private from the header button');

    // "More": only what the tab bar does not show - none of the drawer's areas, no News next to the bell
    check(await ready(ev, `!!document.querySelector('#tabs [data-act="tabs-more"]')`), 'phone: More is in the tab bar');
    const areas = await ev(`tabAreaItems().map(t => t.label)`);
    await ev(`(() => { document.querySelector('#tabs [data-act="tabs-more"]').click(); return 1; })()`);
    check(await ready(ev, `!document.querySelector('#pop').classList.contains('hidden')`), 'phone: More opens');
    const mo = await ev(MENU);
    check(areas.length >= 6 && !mo.items.some(x => areas.includes(x)), '#6127 phone: More repeats none of the drawer\'s areas ' + JSON.stringify({more: mo.items, areas}));
    check(!mo.items.some(x => /^News/.test(x)) && mo.items.includes('Settings') && mo.items.includes('Customise tab bar'), '#6127 phone: no News next to the bell, Settings and the tab bar stay ' + JSON.stringify(mo.items));
    await shot('p21401a-more-390.png');
    // a pinned tab that does not fit still is in More (the tab bar does not show it)
    await ev(`(() => { closePop(); LS.set('tabbar', ['s:inbox', 's:today', 'search', 'lists', 's:week', 's:doable', 'm:cal']); S.settings.nav_menus = '{}'; render(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#tabs [data-act="tabs-more"]')`);
    await ev(`(() => { document.querySelector('#tabs [data-act="tabs-more"]').click(); return 1; })()`);
    await ready(ev, `!document.querySelector('#pop').classList.contains('hidden')`);
    const mo2 = await ev(MENU);
    check(mo2.items.includes('Calendar') && mo2.items.filter(x => x === 'Calendar').length === 1, '#6127 phone: an overflowing pinned tab is in More, once ' + JSON.stringify(mo2.items));
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml') || b).textContent.trim() === 'Calendar').click(); return 1; })()`);
    check(await ready(ev, `S.route.mod === 'cal'`), '#6127 phone: the pick from More opens the calendar');

    // the favourites' row over the tab bar: each tile with its name
    await nav(B + '#today');
    await ready(ev, `S.booted && document.querySelectorAll('#favup .fv2-tile').length === 3`, 80);
    await ev(SWIPE_UP);
    check(await ready(ev, `!document.querySelector('#favup').classList.contains('hidden')`), 'phone: a swipe up opens the favourites');
    await ready(ev, `!document.querySelector('#favup').getAnimations().some(a => a.playState === 'running')`, 20);
    const N = await ev(NAMES('#favup'));
    const p1 = N.find(x => x.key === `l:${L1}`), p2 = N.find(x => x.key === `l:${L2}`), td = N.find(x => x.key === 'v:today');
    check(p1 && p2 && td && p2.name === 'Website Relaunch' && td.name === 'Today' && p1.name && p1.name !== p2.name, '#6127 phone: every favourite shows its name ' + JSON.stringify(N));
    check(N.every(x => x.ell && x.w <= 8.5 * 16 + 1 && x.w >= 44), '#6127 phone: short tiles (long names cut), still big targets ' + JSON.stringify(N));
    await shot('p21401a-favs-390.png');
    // a tap goes there
    await ev(`(() => { document.querySelector('#favup [data-fv2="l:${L2}"]').click(); return 1; })()`);
    check(await ready(ev, `S.route.key === 'l:${L2}'`), '#6127 phone: the named favourite opens its project');
  }, true);

  // ===== frida without an organisation: Private + "Add an organisation" on both devices; the dialog says organisation
  await firefox(async o => {
    const {cmd, ev, ctx, nav} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    check(await signIn(o, 'frida') === 200, 'frida: login');
    await nav(B + '#inbox');
    check(await ready(ev, `!!document.querySelector('#kbar .kbsw')`, 80), 'frida: the head bar');
    await ev(`(() => { document.querySelector('#kbar .kbsw').click(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`);
    const fd = await ev(MENU);
    check(fd.items.join('|') === 'Private|Add an organisation', '#6127 frida computer: Private, Add an organisation ' + JSON.stringify(fd.items));
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => (b.querySelector('.ml') || b).textContent.trim() === 'Add an organisation').click(); return 1; })()`);
    check(await ready(ev, `/Name of the new organisation/.test((document.querySelector('.modal, [role="dialog"]') || {}).innerText || '')`), '#6127: the dialog asks for the name of the new organisation');
    check(await ev(`!/compan/i.test((document.querySelector('.modal, [role="dialog"]') || {}).innerText || '')`), '#6127: the dialog does not say company');
    await ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1; })()`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + '#inbox');
    await ready(ev, `!!document.querySelector('#top .menu')`, 60);
    // 2.1437.0 (#7299): without an organisation the chip shows Private and opens the same menu (the drawer's brand leads to Start)
    check(await ready(ev, `!!document.querySelector('#top .wschip')`), 'frida phone: the chip (Private) in the header');
    await ev(`(() => { document.querySelector('#top .wschip').click(); return 1; })()`);
    await ready(ev, `!!document.querySelector('#pop [role="menuitem"]')`);
    const fp = await ev(MENU);
    check(fp.items.join('|') === fd.items.join('|'), '#6127 frida phone: the same menu as on the computer ' + JSON.stringify({phone: fp.items, computer: fd.items}));
  }, false);

  console.log(`p21401_a_nav_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
