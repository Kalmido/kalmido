// 2.1437.0 (#7299, variant 1 of 19.11.2026): the workspace is chosen only with the chip in the header, which is always there
// kalmido-suite: fresh
// ("All workspaces" too). (#7526, decision of 20.11.2026, newer than #7299 "the logo leads to Start"): a click (and Enter)
// on the logo opens the settings. Own container (start.sh), Firefox, invented names only.
// - computer (1440, mouse): the head bar holds the brand (a button "Settings") and beside it the chip (#kbar .kbsw.kbfirm); a
//   click on the brand opens the settings (no menu, the page stays), Escape closes them and the focus is back on the brand,
//   Enter opens them again; the chip opens the menu, a pick switches to the organisation, back to "All" the same way
// - phone (390 and 320, touch): the chip in the header under "All" too (its grid symbol, inside the screen); the drawer's brand
//   has no workspace line and no arrow and opens the settings (the drawer closes); the chip: menu -> the organisation -> "All"
// - freelancer-matrix: navigation (a person without an organisation: the brand opens the settings; on the phone the chip shows
//   Private and opens the menu with "Add an organisation")
const {execFileSync} = require('child_process');
const path = require('path');
const {B, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const {realClick} = require('./ff');
const firefox = require('./ff')({tag: 'p21437_7299_brand_ui', check, shots: 'P21437_7299_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const ORGN = 'Alpha Studio';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const lr = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', password: 'password123'})});
  CK = lr.headers.get('set-cookie').split(';')[0];
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'all'});
  const me = (await call('GET', '/api/state')).me;
  const ORG = (await call('POST', '/api/admin/orgs', {name: ORGN, admin_id: me.id})).id;
  check(ORG > 0, 'setup: an organisation');
  const fu = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fu.http < 300, 'setup: a person without an organisation ' + fu.http);

  const login = async ({nav, ev}, user = 'alice') => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    const st = await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${user}', password: 'password123'})}).then(r => r.status)`);
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({tour: 'done', lang: 'en', workspace: 'all'})}).then(r => r.status)`);
    return st;
  };
  const ready = async o => { await o.until(`typeof S !== 'undefined' && !!S.booted && !!document.querySelector('#top h1')`); await o.idle(); };
  const popOpen = `!!document.querySelector('#pop:not(.hidden) [role="menuitem"].kbwsi')`;
  const setOpen = `!!document.querySelector('.smodal') && !document.querySelector('#pop:not(.hidden) [role="menuitem"].kbwsi')`;
  const setClose = async o => { await o.cmd('input.performActions', {context: o.ctx, actions: [{type: 'key', id: 'k', actions: [{type: 'keyDown', value: '\uE00C'}, {type: 'keyUp', value: '\uE00C'}]}]}); await o.cmd('input.releaseActions', {context: o.ctx}); return o.until(`!document.querySelector('.smodal')`); };
  const pick = async (o, name) => {
    await o.until(popOpen);
    await o.ev(`(() => { const b = [...document.querySelectorAll('#pop [role="menuitem"].kbwsi')].find(x => (x.querySelector('.ml') || x).textContent.trim() === ${JSON.stringify(name)}); b?.click(); return !!b; })()`);
  };

  // ================= computer: the head bar
  await firefox(async o => {
    const {cmd, ev, ctx, shot, until} = o, tag = '1440';
    check(await login(o) === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 900}});
    await o.nav(B + '#today'); await ready(o);
    const hb = await ev(`(() => { const b = document.querySelector('#kbar .kbbrand'), c = document.querySelector('#kbar .kbsw.kbfirm');
      return {tag: b?.tagName, act: b?.dataset.act, label: b?.getAttribute('aria-label'), title: b?.title, logo: !!b?.querySelector('svg.logo'), word: !!b?.querySelector('svg.kword'), inChip: !!c?.querySelector('svg.logo'),
        chip: c?.dataset.act, name: c?.querySelector('.wsn')?.textContent, before: !!b && !!c && !!(b.compareDocumentPosition(c) & 4), top: !!document.querySelector('#top .wschip')}; })()`);
    check(hb.tag === 'BUTTON' && hb.act === 'settings' && /Settings/.test(hb.label) && hb.title === 'Settings' && hb.logo && hb.word && !hb.inChip, `${tag}: the brand is a button "Settings" (logo + word mark), not in the chip ` + JSON.stringify(hb));
    check(hb.chip === 'sbb-ws' && hb.name === 'All workspaces' && hb.before && !hb.top, `${tag}: beside it the chip names "All workspaces" (the head bar's, none in #top) ` + JSON.stringify(hb));
    await shot('p21437-7299-1440-all.png');
    const rc = await realClick(o, '#kbar .kbbrand');
    check(rc.ok && await until(setOpen) && await ev(`location.hash`) === '#today', `${tag}: a click on the brand opens the settings, no menu, the page stays ` + JSON.stringify(rc));
    await shot('p7526-1440-settings.png');
    check(await setClose(o), `${tag}: Escape closes the settings`);
    await o.idle();
    const foc = await until(`(() => { const b = document.querySelector('#kbar .kbbrand'); if (document.activeElement !== b) b.focus(); return document.activeElement === b; })()`);
    // Enter: a native button (no tabindex -1) gets its click from the browser; headless Firefox delivers the real key's keydown
    // but never the activation (seen 20.11.2026), so the suite checks the button and presses it the way Enter does (click())
    const kb = await ev(`(() => { const b = document.querySelector('#kbar .kbbrand'); return b.tagName === 'BUTTON' && b.type === 'button' && b.tabIndex === 0 && !b.disabled; })()`);
    await ev(`(() => { document.activeElement.click(); return 1; })()`);
    check(foc && kb && await until(setOpen), `${tag}: the focused brand (a native button, reached by Tab) opens the settings like Enter does`);
    check(await setClose(o) && await until(`document.activeElement === document.querySelector('#kbar .kbbrand')`), `${tag}: Escape closes them, the focus is back on the brand`);
    await ev(`(() => { document.querySelector('#kbar .kbsw.kbfirm').click(); return 1; })()`);
    check(await until(popOpen), `${tag}: a click on the chip opens the workspace menu`);
    await shot('p21437-7299-1440-menu.png');
    await pick(o, ORGN);
    check(await until(`wsCur() === 'org:${ORG}' && document.querySelector('#kbar .kbfirm .wsn')?.textContent === ${JSON.stringify(ORGN)}`), `${tag}: the pick switches to the organisation, the chip names it`);
    check(await ev(`location.hash`) === '#today', `${tag}: the page stays`);
    await ev(`(() => { document.querySelector('#kbar .kbsw.kbfirm').click(); return 1; })()`);
    await pick(o, 'All workspaces');
    check(await until(`wsCur() === 'all' && document.querySelector('#kbar .kbfirm .wsn')?.textContent === 'All workspaces'`), `${tag}: back to "All" over the chip`);
    // with an organisation shown the brand still opens the settings (no menu), the workspace stays
    await ev(`(() => { wsSet('org:${ORG}'); return 1; })()`); await until(`wsCur() === 'org:${ORG}'`);
    await ev(`(() => { document.querySelector('#kbar .kbbrand').click(); return 1; })()`);
    check(await until(setOpen) && await ev(`wsCur()`) === `org:${ORG}`, `${tag}: in the organisation the brand opens the settings too, the workspace stays`);
    await setClose(o);
    // Start stays reachable over the account menu
    await ev(`(() => { document.querySelector('#kbar .kbacct').click(); return 1; })()`);
    await until(`!!document.querySelector('#pop:not(.hidden) [role="menuitem"]')`);
    await ev(`(() => { const b = [...document.querySelectorAll('#pop [role="menuitem"]')].find(x => (x.querySelector('.ml') || x).textContent.trim() === 'Start'); b?.click(); return !!b; })()`);
    check(await until(`location.hash === '#home'`), `${tag}: Start is reached over the account menu ` + await ev('location.hash'));
    await ev(`(() => { wsSet('all'); return 1; })()`); await until(`wsCur() === 'all'`); await o.idle();
  });

  // ================= phone: 390 and 320 (touch)
  for (const vw of [390, 320]) await firefox(async o => {
    const {cmd, ev, ctx, shot, until} = o, tag = String(vw);
    check(await login(o) === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: vw, height: 760}});
    await o.nav(B + '#today'); await ready(o);
    const chip = `(() => { const c = document.querySelector('#top .wschip'); if (!c) return null; const r = c.getBoundingClientRect();
      return {w: Math.round(r.width), right: Math.round(r.right), h: Math.round(r.height), grid: !!c.querySelector('svg.i'), over: document.documentElement.scrollWidth - innerWidth}; })()`;
    const c0 = await until(chip);
    check(!!c0 && c0.w >= 24 && c0.right <= vw && c0.over <= 0 && c0.grid, `${tag}: under "All" the chip is in the header (its symbol, inside the screen) ` + JSON.stringify(c0));
    await shot(`p21437-7299-${vw}-all.png`);
    await ev(`(() => { document.querySelector('#top [data-act="side"]').click(); return 1; })()`);
    await until(`(() => { const b = document.querySelector('#side.open .sbbrand'); return !!b && b.getBoundingClientRect().width > 30; })()`);
    const br = await ev(`(() => { const b = document.querySelector('#side .sbbrand'); return {tag: b?.tagName, act: b?.dataset.act, label: b?.getAttribute('aria-label'), sub: !!b?.querySelector('.sbbsub, .wsn'), chev: b ? b.querySelectorAll(':scope > svg.i').length : -1, logo: !!b?.querySelector('svg.logo')}; })()`);
    check(br.tag === 'BUTTON' && br.act === 'settings' && /Settings/.test(br.label) && !br.sub && br.chev === 0 && br.logo, `${tag}: the drawer's brand: logo + word mark, no workspace line, no arrow ` + JSON.stringify(br));
    await shot(`p21437-7299-${vw}-drawer.png`);
    const rp = await realClick(o, '#side .sbbrand', {kind: 'touch'});
    check(rp.ok && await until(`${setOpen} && !document.querySelector('#side.open')`), `${tag}: the drawer's brand opens the settings and the drawer closes ` + JSON.stringify(rp));
    await shot(`p7526-${vw}-settings.png`);
    check(await setClose(o) && await ev(`location.hash`) === '#today', `${tag}: closing the settings leads back to the page`);
    await ev(`(() => { document.querySelector('#top .wschip').click(); return 1; })()`);
    check(await until(popOpen), `${tag}: the chip opens the workspace menu`);
    await pick(o, ORGN);
    check(await until(`wsCur() === 'org:${ORG}' && !!document.querySelector('#top .wschip .orgini')`), `${tag}: the organisation; the chip shows its letter (#7210)`);
    const c1 = await ev(chip);
    check(!!c1 && c1.right <= vw && c1.over <= 0, `${tag}: the organisation's chip inside the screen ` + JSON.stringify(c1));
    await shot(`p21437-7299-${vw}-org.png`);
    await o.until(`!document.querySelector('#pop:not(.hidden)')`);
    await ev(`(() => { document.querySelector('#top .wschip').click(); return 1; })()`);
    await pick(o, 'All workspaces');
    check(await until(`wsCur() === 'all' && !!document.querySelector('#top .wschip')`), `${tag}: back to "All" over the chip, the chip stays`);
    await o.idle();
  }, true);

  // ================= freelancer-matrix: a person without an organisation
  await firefox(async o => {
    const {cmd, ev, ctx, until} = o, tag = 'frida 1440';
    check(await login(o, 'frida') === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 900}});
    await o.nav(B + '#today'); await ready(o);
    await ev(`(() => { document.querySelector('#kbar .kbbrand').click(); return 1; })()`);
    check(await until(setOpen), `${tag}: the brand opens the settings`);
    await setClose(o);
    check(await ev(`!document.querySelector('#top .wschip') && document.querySelector('#kbar .kbfirm .wsn')?.textContent === 'Private'`), `${tag}: the head bar's chip shows Private (none in #top)`);
  });
  await firefox(async o => {
    const {cmd, ev, ctx, until} = o, tag = 'frida 390';
    check(await login(o, 'frida') === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 760}});
    await o.nav(B + '#today'); await ready(o);
    check(await until(`!!document.querySelector('#top .wschip')`), `${tag}: the chip (Private) in the header`);
    await ev(`(() => { document.querySelector('#top .wschip').click(); return 1; })()`);
    check(await until(`!!document.querySelector('#pop:not(.hidden) .kbws-add')`), `${tag}: its menu offers "Add an organisation"`);
  }, true);

  console.log(`p21437_7299_brand_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack); process.exit(1); });
