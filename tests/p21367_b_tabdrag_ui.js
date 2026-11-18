// kalmido-suite: fresh
// 2.1367.0 part B UI test (jsdom), own container (start.sh; KMT_NOSTART=1: a running server), #6748: arranging the bottom
// bar and the sidebar in Settings on a phone (360 / 412 px).
// - the "…" menu of a settings row takes the icons of its hidden buttons with their turn: "move forward" / "move up" point
//   up, "move back" / "move down" down (multisel.js ms_btnItems -> popovers.js menu, icls)
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
  w.close();

  console.log(`p21367_b_tabdrag_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
