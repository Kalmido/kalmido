// 2.1297.0 (#6129) UI test, own container (start.sh), jsdom, invented data only: every setting has one clear name in one place
// kalmido-suite: fresh
// - Notifications: "Daily digest at" and "Morning briefing at" are two different names; under "Zustellung" the field is "Kanal" (de)
// - the bottom bar is edited under Navigation only (heading "Menüs und Leiste unten"); Appearance keeps the heading and a link
//   that lands on the opened bottom bar section; settingsModal('tabbar') lands there too
// - "Completed tasks": both switches (s-sdd, s-sdn) in one section
// - "For advanced users" at most once in Integrations; the Account tab has no row called just "Server"
// - a person without an organisation: the same link
// freelancer-matrix: settings
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs, until: untilT} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21297A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = fn => untilT(fn, {timeout: 15000, step: 100}).catch(() => null);
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const labelOf = (root, id) => txt(root.querySelector(`label[for="${id}"]`));
const shown = el => !!el && !el.closest('.hidden, [hidden]');

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  const call = async (method, url, body, ck = CK) => (await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined})).status;
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done'});

  let w = await boot({user: 'alice'}), d = w.document;
  w.eval(`settingsModal('look')`);
  let md = await until(() => d.querySelector('.smodal [data-pane="look"] #s-sdd') && d.querySelector('.smodal'));
  check(!!md, 'Appearance opens');
  const look = md.querySelector('[data-pane="look"]');
  // Completed tasks: one section with both switches
  const hd = look.querySelector('#s-sdd-h');
  // 2.1353.0 (#6827): every section is a fold (details.sfold) with its heading in the head row: both switches in the heading's fold
  const fold = hd?.closest('details.sfold');
  check(!!fold && fold.contains(look.querySelector('#s-sdd')) && fold.contains(look.querySelector('#s-sdn')), 'Completed tasks: s-sdd and s-sdn in the same section');
  check(/rledigte/.test(txt(hd)), 'Completed tasks heading: ' + txt(hd));
  // the bottom bar: heading + link only
  check(!md.querySelector('#s-tabbar') && !look.querySelector('[data-m="tab-add"]'), 'Appearance: no bottom bar editor');
  const lk = look.querySelector('[data-m="go-nav"]');
  check(shown(lk) && /Navigation/.test(txt(lk)), 'Appearance: a visible link to Navigation: ' + txt(lk));
  click(w, lk);
  const nav = md.querySelector('[data-pane="nav"]');
  check(md.querySelector('.snav .on')?.dataset.sec === 'nav' && shown(nav) && !shown(look), 'the link lands on Navigation');
  check(txt(nav.querySelector('#s-nav-h')) === 'Menüs und Leiste unten', 'Navigation heading: ' + txt(nav.querySelector('#s-nav-h')));
  const tb = await until(() => nav.querySelector('[data-navsec="tabbar"]'));
  check(!!tb && !!(await until(() => tb.open)), 'Navigation: the bottom bar section is there and opened by the link');
  check(shown(nav.querySelector('[data-m="tab-add"]')) && shown(nav.querySelector('[data-m="tab-reset"]')), 'Navigation: + Add tab and Default');
  check(md.querySelectorAll('[data-navsec="tabbar"]').length === 1 && md.querySelectorAll('[data-m="tab-add"]').length === 1, 'the bottom bar editor appears once in the whole dialog');
  // and back: the Appearance tab is still reachable and keeps its link
  click(w, md.querySelector('.snav [data-sec="look"]'));
  check(shown(look) && shown(look.querySelector('[data-m="go-nav"]')), 'back to Appearance: the link is there again');

  // Notifications: two different names, "Zustellung" > "Kanal"
  click(w, md.querySelector('.snav [data-sec="notify"]'));
  const np = md.querySelector('[data-pane="notify"]');
  const dg = labelOf(np, 's-digest'), br = labelOf(np, 's-brief');
  check(dg === 'Tagesüberblick um' && br === 'Morgen-Briefing um', 'digest / briefing labels differ: ' + dg + ' | ' + br);
  check([...np.querySelectorAll('label')].map(txt).filter(x => x === 'Tagesüberblick um').length === 1, 'Tagesüberblick um appears once');
  if (w.eval('!!S.webpush?.enabled')) {
    check([...np.querySelectorAll('h4')].map(txt).includes('Zustellung') && labelOf(np, 's-pushch') === 'Kanal', 'Delivery: heading Zustellung, field Kanal');
    check(![...np.querySelectorAll('label')].some(l => txt(l) === 'Zustellung'), 'no field called Zustellung');
  }
  // Integrations: "For advanced users" (the link to Access) at most once
  click(w, md.querySelector('.snav [data-sec="integr"]'));
  const ip = md.querySelector('[data-pane="integr"]');
  // (#7230): the server admin's details (e-mail not set up) fold under "Für Server-Admins", not a second "Für Fortgeschrittene"
  const adv = p => [...p.querySelectorAll('summary')].filter(s => txt(s) === 'Für Fortgeschrittene');
  const where = l => l.map(s => s.parentElement.className + '@' + (s.closest('[data-intr], [data-sf]')?.dataset.sf || s.closest('[data-intr]')?.dataset.intr || '-')).join(', ');
  check(adv(ip).length <= 1 && ip.querySelectorAll('[data-m="go-access"]').length <= 1, 'Integrations: "Für Fortgeschrittene" and the link to Access at most once: ' + where(adv(ip)) + ' / go-access ' + ip.querySelectorAll('[data-m="go-access"]').length);
  // Account: no row labelled just "Server" (that name is the tab Server)
  const ap = md.querySelector('[data-pane="account"]');
  check(![...ap.querySelectorAll('label')].some(l => txt(l) === 'Server'), 'Account: no row called Server');
  check(adv(ap).length <= 1, 'Account: "Für Fortgeschrittene" at most once (#6129): ' + where(adv(ap)));
  md.remove();
  // the jump settingsModal('tabbar') (search, palette) lands on the bottom bar under Navigation
  w.eval(`settingsModal('tabbar')`);
  md = await until(() => d.querySelector('.smodal .snav .on') && d.querySelector('.smodal'));
  check(md?.querySelector('.snav .on')?.dataset.sec === 'nav' && !!(await until(() => md.querySelector('[data-navsec="tabbar"]')?.open)), 'settingsModal(tabbar) -> Navigation, bottom bar open');
  md?.remove();
  w.close();

  // a person without an organisation: the same link
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const FK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done'}, FK);
  w = await boot({user: 'frida'}); d = w.document;
  w.eval(`settingsModal('look')`);
  md = await until(() => d.querySelector('.smodal [data-pane="look"] [data-m="go-nav"]') && d.querySelector('.smodal'));
  check(!!md && !md.querySelector('#s-tabbar'), 'frida: Appearance links to Navigation, no second editor');
  w.close();

  check(!errs.length, 'no script errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21297_a_settings_labels_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
