// kalmido-suite: fresh
// (#6534) UI test, own container (hosted with a support address), Firefox. Invented accounts only (example.com).
// freelancer-matrix: own
// - /api/about tells every signed-in person (not only the admin) that the server is hosted and names its support address;
//   the answer of "Forgot password" names it too (the same for every request)
// - a sentence that sent people to "the admin of this server" names the support (the e-mail domains of an own company)
// - Settings > Help opens on "Help from a person": a mail to the support, "Allow support access" leads to the section
//   Support access (which now names the support as well); About: "Report a problem" writes to the support, the GitHub
//   links and the device line sit folded under "Technical details"
// - the command palette offers "Contact support"; "Report a problem" goes to the support, not to GitHub
// - the page Help shows the block above the topics; the phone's "More" menu has "Contact support"
// A self-hosted server keeps the old behaviour: settings_ui.js / p21211_a_palette_ui.js (no block, GitHub links) and
// p2485_a_support_test.py (about: hosted false).
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p6534_support_ui', check, shots: 'P6534_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const SUP = 'help@example.com';
if (!process.env.P6534_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ` -e KALMIDO_HOSTED=1 -e KALMIDO_SUPPORT_EMAIL=${SUP}`}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', org_name: 'Alpha', modules: ['comments']});
  const u = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http < 300, 'a person without organisation ' + u.http);
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});

  // ---- the server
  const ab = await call(CF, 'GET', '/api/about');
  check(ab.hosted === true && ab.support === SUP, 'about: a person (no admin) learns hosted + the support address ' + JSON.stringify({h: ab.hosted, s: ab.support}));
  check(ab.update_check === undefined && ab.support_email === undefined, 'about: the admin fields stay the admin\'s');
  const fg = await call(null, 'POST', '/api/auth/forgot', {login: 'nobody'});
  check(fg.http === 200 && fg.support === SUP, 'forgot password: the answer names the support ' + fg.http);
  const og = await call(CF, 'POST', '/api/orgs', {name: 'Studio Frida'});
  check(og.http === 201 && og.id, 'frida creates her company ' + og.http);
  const dm = await call(CF, 'PATCH', `/api/orgs/${og.id}`, {domains: 'example.org'});
  check(dm.http === 403 && (dm.error || '').includes(SUP) && !/admin of this server/.test(dm.error || ''), 'its e-mail domains: the refusal names the support ' + dm.http + ' ' + dm.error);

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, who) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`);
  const vis = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })()`;
  const closeAll = `(() => { for (const m of [...document.querySelectorAll('.modal')]) m.querySelector('[data-m="close"], .iconbtn[aria-label="Close"]')?.click(); return 1; })()`;

  await firefox(async ({cmd, ev, ctx, nav}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev, 'frida');
    await nav(B + '#inbox');
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && !!S.about && S.about.hosted === true`, 80), 'booted, the client knows it is hosted');

    // ---- Settings > Help: the block on top, open
    await ev(`settingsModal('help')`);
    check(await ready(ev, vis('.modal #sp-help:not(.hidden) [data-supmail]')), 'Settings > Help: "Write to support" is visible at once (its section is open)');
    check(await ev(`(() => { const p = document.querySelector('.modal #sp-help'); const h = p.querySelector('#s-suphelp-h'); const all = [...p.querySelectorAll('h4, summary')]; return !!h && all.indexOf(h.closest('summary') || h) === 0; })()`), 'the block "Help from a person" is the first section');
    check(await ev(`document.querySelector('.modal [data-supmail]').getAttribute('href').startsWith('mailto:help%40example.com?subject=')`), 'the button is a mail to the support address');
    check(await ev(`/help@example\\.com/.test(document.querySelector('.modal .supaddr')?.textContent || '')`), 'the address is shown next to it');
    // About: Report a problem = support; GitHub folded
    check(await ev(`!!document.querySelector('.modal #sp-help [data-supreport]')`), 'About: "Report a problem" is a button to the support');
    check(await ev(`[...document.querySelectorAll('.modal #sp-help a[href*="github.com"]')].every(a => a.closest('details.abouttech'))`), 'About: every GitHub link sits under "Technical details"');
    check(await ev(`!!document.querySelector('.modal details.abouttech #s-aboutdev') && !document.querySelector('.modal details.abouttech').open`), 'About: the device line is folded under "Technical details"');
    await ev(`(() => { window.__sc = null; window.supContact = p => { window.__sc = p; }; document.querySelector('.modal [data-supreport]').click(); return 1; })()`);
    check(await ev(`window.__sc === true`), 'About: "Report a problem" writes to the support (a problem)');
    // Allow support access -> Settings > Account > Support access, shown
    await ev(`document.querySelector('.modal [data-supgrant]').click()`);
    check(await ready(ev, vis('.modal #sp-account:not(.hidden) #s-sgv-h'), 60), '"Allow support access" opens Settings > Account at Support access');
    check(await ready(ev, `(() => { const h = document.querySelector('.modal #s-sgv-h'); if (!h) return false; const r = h.getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; })()`), 'the section Support access is on the screen');
    check(await ev(`!!document.querySelector('.modal #s-sgv .sgvmail a[href^="mailto:help%40example.com"]') && !!document.querySelector('.modal #s-sgv [data-sgv="grant"]')`), 'Support access names the support and still offers "Grant"');
    await ev(closeAll);
    check(await ready(ev, `!document.querySelector('.modal')`), 'back out of the settings');

    // ---- command palette
    await ev(`openPalette()`);
    await ev(`(() => { const i = document.querySelector('.palette .pqin'); i.value = 'support'; i.dispatchEvent(new Event('input', {bubbles: true})); palFlush(); return 1; })()`);
    check(await ready(ev, `[...document.querySelectorAll('.palette .pitem .plt')].some(x => x.textContent === 'Contact support')`), 'palette: "Contact support"');
    await ev(`(() => { const i = document.querySelector('.palette .pqin'); i.value = 'report a problem'; i.dispatchEvent(new Event('input', {bubbles: true})); palFlush(); return 1; })()`);
    check(await ready(ev, `[...document.querySelectorAll('.palette .pitem .plt')].some(x => x.textContent === 'Report a problem')`), 'palette: "Report a problem"');
    await ev(`(() => { window.__sc = null; window.__ext = null; window.openExt = u => { window.__ext = u; }; [...document.querySelectorAll('.palette .pitem')].find(x => x.querySelector('.plt')?.textContent === 'Report a problem').click(); return 1; })()`);
    check(await ready(ev, `window.__sc === true && window.__ext === null`), 'palette: "Report a problem" writes to the support, no GitHub');
    await ev(`typeof closePalette === 'function' && closePalette(), 1`);

    // ---- the page Help
    await ev(`go('help')`);
    check(await ready(ev, vis('#view .hvhuman [data-supmail]'), 60), 'page Help: the block "Help from a person" above the topics');
    check(await ev(`(() => { const h = document.querySelector('#view .hvhuman'), s = document.querySelector('#view .hvsearch'); return !!h && !!s && h.getBoundingClientRect().top < s.getBoundingClientRect().top; })()`), 'page Help: the block stands above the search');
    await ev(`document.querySelector('#view .hvhuman [data-supgrant]').click()`);
    check(await ready(ev, vis('.modal #sp-account:not(.hidden) #s-sgv-h'), 60), 'page Help: "Allow support access" opens Support access');
    await ev(closeAll);
    await ready(ev, `!document.querySelector('.modal')`);

    // ---- phone: More
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + '#inbox');
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && isMobile() && !!document.querySelector('#tabs [data-act="tabs-more"]')`, 80), 'phone: the tab "More"');
    await ev(`document.querySelector('#tabs [data-act="tabs-more"]').click()`);
    // the menu (a sheet on the phone) is #pop
    check(await ready(ev, `[...(document.getElementById('pop')?.querySelectorAll('button, [role="menuitem"]') || [])].some(b => /Contact support/.test(b.textContent))`), 'phone: "More" has "Contact support"');
    await ev(`(() => { window.__sc = null; [...document.getElementById('pop').querySelectorAll('button, [role="menuitem"]')].find(b => /Contact support/.test(b.textContent))?.click(); return 1; })()`);
    check(await ready(ev, `window.__sc === false`), 'phone: "Contact support" writes to the support (a question)');
  }, false);

  console.log(`p6534_support_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
