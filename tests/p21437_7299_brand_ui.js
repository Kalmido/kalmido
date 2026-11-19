// 2.1437.0 (#7299, variant 1 of 19.11.2026): a click on the logo always leads to Start; the workspace is chosen only with
// kalmido-suite: fresh
// the chip in the header, which is always there ("All workspaces" too). Own container (start.sh), Firefox, invented names only.
// - computer (1440, mouse): the head bar holds the brand (a link to Start) and beside it the chip (#kbar .kbsw.kbfirm); the
//   brand leads to Start and opens no menu; the chip opens the menu, a pick switches to the organisation, back to "All" the
//   same way
// - phone (390 and 320, touch): the chip in the header under "All" too (its grid symbol, inside the screen); the drawer's brand
//   has no workspace line and no arrow and leads to Start (the drawer closes); the chip: menu -> the organisation -> "All"
// - freelancer-matrix: navigation (a person without an organisation: the brand leads to Start; on the phone the chip shows
//   Private and opens the menu with "Add an organisation" - the drawer's brand used to be her way there)
const {execFileSync} = require('child_process');
const path = require('path');
const {B, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
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
      return {tag: b?.tagName, href: b?.getAttribute('href'), logo: !!b?.querySelector('svg.logo'), word: !!b?.querySelector('svg.kword'), inChip: !!c?.querySelector('svg.logo'),
        chip: c?.dataset.act, name: c?.querySelector('.wsn')?.textContent, before: !!b && !!c && !!(b.compareDocumentPosition(c) & 4), top: !!document.querySelector('#top .wschip')}; })()`);
    check(hb.tag === 'A' && hb.href === '#home' && hb.logo && hb.word && !hb.inChip, `${tag}: the brand is a link to Start (logo + word mark), not in the chip ` + JSON.stringify(hb));
    check(hb.chip === 'sbb-ws' && hb.name === 'All workspaces' && hb.before && !hb.top, `${tag}: beside it the chip names "All workspaces" (the head bar's, none in #top) ` + JSON.stringify(hb));
    await shot('p21437-7299-1440-all.png');
    await ev(`(() => { document.querySelector('#kbar .kbbrand').click(); return 1; })()`);
    check(await until(`location.hash === '#home'`) && !await ev(popOpen), `${tag}: a click on the brand leads to Start, no menu ` + await ev('location.hash'));
    await o.nav(B + '#today'); await ready(o);
    await ev(`(() => { document.querySelector('#kbar .kbsw.kbfirm').click(); return 1; })()`);
    check(await until(popOpen), `${tag}: a click on the chip opens the workspace menu`);
    await shot('p21437-7299-1440-menu.png');
    await pick(o, ORGN);
    check(await until(`wsCur() === 'org:${ORG}' && document.querySelector('#kbar .kbfirm .wsn')?.textContent === ${JSON.stringify(ORGN)}`), `${tag}: the pick switches to the organisation, the chip names it`);
    check(await ev(`location.hash`) === '#today', `${tag}: the page stays`);
    await ev(`(() => { document.querySelector('#kbar .kbsw.kbfirm').click(); return 1; })()`);
    await pick(o, 'All workspaces');
    check(await until(`wsCur() === 'all' && document.querySelector('#kbar .kbfirm .wsn')?.textContent === 'All workspaces'`), `${tag}: back to "All" over the chip`);
    // with an organisation shown the brand still leads to Start (no menu), the workspace stays
    await ev(`(() => { wsSet('org:${ORG}'); return 1; })()`); await until(`wsCur() === 'org:${ORG}'`);
    await ev(`(() => { document.querySelector('#kbar .kbbrand').click(); return 1; })()`);
    check(await until(`location.hash === '#home'`) && !await ev(popOpen) && await ev(`wsCur()`) === `org:${ORG}`, `${tag}: in the organisation the brand leads to Start too, the workspace stays`);
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
    const br = await ev(`(() => { const b = document.querySelector('#side .sbbrand'); return {tag: b?.tagName, href: b?.getAttribute('href'), sub: !!b?.querySelector('.sbbsub, .wsn'), chev: b ? b.querySelectorAll(':scope > svg.i').length : -1, logo: !!b?.querySelector('svg.logo')}; })()`);
    check(br.tag === 'A' && br.href === '#home' && !br.sub && br.chev === 0 && br.logo, `${tag}: the drawer's brand: logo + word mark, no workspace line, no arrow ` + JSON.stringify(br));
    await shot(`p21437-7299-${vw}-drawer.png`);
    await ev(`(() => { document.querySelector('#side .sbbrand').click(); return 1; })()`);
    check(await until(`location.hash === '#home' && !document.querySelector('#side.open')`) && !await ev(popOpen), `${tag}: the drawer's brand leads to Start and the drawer closes ` + await ev('location.hash'));
    await o.nav(B + '#today'); await ready(o);
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
    check(await until(`location.hash === '#home'`), `${tag}: the brand leads to Start`);
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
