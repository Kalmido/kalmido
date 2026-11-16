// 2.1178.0 (#6129) UI test, own container (start.sh), jsdom, invented data only: the settings labels are unique
// kalmido-suite: fresh
// - Notifications: "Daily digest at" and "Morning briefing at" are two different names, "Delivery" > "Channel" (de)
// - the bottom bar is edited under Navigation only; Appearance has the heading and a link that lands there
// - "Completed tasks": both switches (s-sdn, s-sdd) in one section
// - "For advanced users" once in Integrations; the Account tab has no row called just "Server"
// freelancer-matrix: settings
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs, until: untilT} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21178D_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = fn => untilT(fn, {timeout: 15000, step: 100}).catch(() => null);
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const labelOf = (root, id) => txt(root.querySelector(`label[for="${id}"]`));

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  const call = async (method, url, body) => (await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined})).status;
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done'});

  let w = await boot({user: 'alice'}), d = w.document;
  w.eval(`settingsModal('look')`);
  let md = await until(() => d.querySelector('.smodal [data-pane="look"] #s-sdd') && d.querySelector('.smodal'));
  check(!!md, 'Appearance opens');
  const look = md.querySelector('[data-pane="look"]');
  // Completed tasks: one section, both switches, nothing else between the heading and the next heading
  const hd = look.querySelector('#s-sdd-h');
  let sec = [], n = hd.nextElementSibling; while (n && n.tagName !== 'H4') { sec.push(n); n = n.nextElementSibling; }
  check(sec.some(e => e.querySelector('#s-sdd')) && sec.some(e => e.querySelector('#s-sdn')), 'Completed tasks: s-sdd and s-sdn in the same section');
  check(txt(hd) === 'Erledigte Aufgaben' || /rledigte/.test(txt(hd)), 'Completed tasks heading: ' + txt(hd));
  // the bottom bar: heading + link only
  check(!md.querySelector('#s-tabbar') && !md.querySelector('[data-pane="look"] [data-m="tab-add"]'), 'Appearance: no bottom bar editor');
  const lk = look.querySelector('[data-m="go-nav"]');
  check(!!lk && /Navigation/.test(txt(lk)), 'Appearance: link to Navigation: ' + txt(lk));
  click(w, lk);
  check(md.querySelector('.snav .on')?.dataset.sec === 'nav' && !md.querySelector('[data-pane="nav"]').classList.contains('hidden'), 'the link lands on Navigation');
  const nav = md.querySelector('[data-pane="nav"]');
  check(txt(nav.querySelector('#s-nav-h')) === 'Menüs und Leiste unten', 'Navigation heading: ' + txt(nav.querySelector('#s-nav-h')));
  const tb = await until(() => nav.querySelector('[data-navsec="tabbar"]'));
  check(!!tb && (await until(() => tb.open)), 'Navigation: the bottom bar section is there and opened by the link');
  check(!!nav.querySelector('[data-m="tab-add"]') && !!nav.querySelector('[data-m="tab-reset"]'), 'Navigation: + Add tab and Default');
  check(md.querySelectorAll('[data-navsec="tabbar"]').length === 1, 'the bottom bar appears once in the whole dialog');

  // Notifications: two different names
  click(w, md.querySelector('.snav [data-sec="notify"]'));
  const np = md.querySelector('[data-pane="notify"]');
  const dg = labelOf(np, 's-digest'), br = labelOf(np, 's-brief');
  check(dg === 'Tagesüberblick um' && br === 'Morgen-Briefing um' && dg !== br, 'digest / briefing labels differ: ' + dg + ' | ' + br);
  const names = [...np.querySelectorAll('label[for]')].map(l => txt(l)).filter(Boolean);
  check(names.filter(x => x === 'Tagesüberblick um').length === 1, 'Tagesüberblick um appears once');
  if (w.eval('!!S.webpush?.enabled')) {
    const hs = [...np.querySelectorAll('h4')].map(h => txt(h));
    check(hs.includes('Zustellung') && labelOf(np, 's-pushch') === 'Kanal', 'Delivery: heading Zustellung, field Kanal');
  }
  // Integrations: "For advanced users" at most once
  click(w, md.querySelector('.snav [data-sec="integr"]'));
  const ip = md.querySelector('[data-pane="integr"]');
  check([...ip.querySelectorAll('summary')].filter(s => txt(s) === 'Für Fortgeschrittene').length <= 1 && ip.querySelectorAll('[data-m="go-access"]').length <= 1, 'Integrations: "Für Fortgeschrittene" and the link to Access at most once');
  // Account: no row labelled just "Server" (that name is the tab)
  const ap = md.querySelector('[data-pane="account"]');
  check(![...ap.querySelectorAll('label')].some(l => txt(l) === 'Server') && !ap.querySelector('#s-tabbar'), 'Account: no row called Server');
  check(!!md.querySelector('.snav [data-sec="users"]'), 'the Server tab stays');
  w.close();

  // a person without an organisation: the same
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const FK = await login('frida');
  await fetch(B + 'api/settings', {method: 'PATCH', headers: {...H, Cookie: FK}, body: JSON.stringify({lang: 'de', tour: 'done'})});
  w = await boot({user: 'frida'}); d = w.document;
  w.eval(`settingsModal('look')`);
  md = await until(() => d.querySelector('.smodal [data-pane="look"] [data-m="go-nav"]') && d.querySelector('.smodal'));
  check(!!md, 'frida: Appearance links to Navigation');
  w.close();

  check(!errs.length, 'no script errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21178_d_settings_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
