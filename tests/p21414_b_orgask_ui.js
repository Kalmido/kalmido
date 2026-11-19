// 2.1414.0 (#6519) UI test, Firefox like a person: the first start of a self-registered account asks "Private or with an
// kalmido-suite: fresh
// organisation?" before the tour (skippable); "For my organisation" with a name creates it and ends in the closing step with
// "Enter the organisation's details" and "Invite people" (the invite dialog opens, one gets back out); the question never
// comes again. "Skip" leaves the account private and is not asked again either. "Add an organisation" in Settings ends in the
// same closing step instead of only a message; without an organisation the button is in Settings > Account. Own container (workspaces mode), invented data only.
// freelancer-matrix: own (frida and gina have no organisation; POST /api/orgs as a person without one: p2422_orgself_test.py)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21414_b_orgask_ui', check, shots: 'P21414B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const sql = q => String(execFileSync('python3', [path.join(__dirname, 'dbx.py'), DATA, q]));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  const ids = {};
  for (const u of ['frida', 'gina']) {
    const x = await call(CA, 'POST', '/api/users', {username: u, display_name: u[0].toUpperCase() + u.slice(1), password: 'password123', email: `${u}@example.com`});
    check(x.http < 300, `${u} (no organisation) ${x.http}`);
    ids[u] = x.id;
    await call(await login(u), 'PATCH', '/api/settings', {lang: 'en', workspace: 'private'});
  }
  // as accounts/signup.py leaves a self-registered account (the registration itself: p2422_orgself_test.py)
  sql(`INSERT INTO user_settings(user_id,key,value) VALUES(${ids.frida},'org_ask','pending'),(${ids.gina},'org_ask','pending') ON CONFLICT (user_id,key) DO UPDATE SET value='pending'`);
  sql(`UPDATE user_settings SET value='pending' WHERE key='tour' AND user_id IN (${ids.frida},${ids.gina})`);
  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(150); } return false; };
  const signIn = async (o, u) => {
    await o.nav(B + 'static/icon.svg');
    await o.ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    return o.ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  };
  const click = (ev, sel) => ev(`(() => { const b = document.querySelector(${JSON.stringify(sel)}); if (!b) return 0; b.click(); return 1; })()`);
  const shown = sel => `!!document.querySelector(${JSON.stringify(sel)})?.getClientRects().length`;

  // ===== frida on a phone: the question, "For my organisation", the closing step, Invite people
  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    check(await signIn(o, 'frida') === 200, 'frida: login');
    await nav(B + '#inbox');
    check(await ready(ev, shown('.modal.oaskdlg'), 80), '#6519: the first start asks "Private or with an organisation?"');
    check(await ev(`!document.querySelector('.tour')?.getClientRects().length`), '#6519: the tour waits for the answer');
    check(await ev(`document.querySelector('.oaskdlg .oaskname').hidden`), '#6519: no name field while Private is chosen');
    await click(ev, '.oaskdlg [data-oask="org"]');
    check(await ready(ev, `!document.querySelector('.oaskdlg .oaskname').hidden && document.activeElement?.id === 'oask-n'`, 20), '#6519: "For my organisation" asks for its name');
    await click(ev, '.oaskdlg [data-oask-go]');
    check(await ready(ev, `/Name of the new organisation/.test(document.querySelector('#oask-err')?.textContent || '')`, 20), '#6519: without a name it says what is missing');
    await ev(`(() => { const i = document.querySelector('#oask-n'); i.value = 'Frida Studio'; i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    if (shot) await shot('orgask-phone');
    await click(ev, '.oaskdlg [data-oask-go]');
    check(await ready(ev, shown('.modal.oadonedlg'), 60), '#6519: the closing step follows');
    check(await ev(`/Frida Studio/.test(document.querySelector('.oadonedlg h3').textContent) && !!document.querySelector('.oadonedlg [data-oadone="data"]') && !!document.querySelector('.oadonedlg [data-oadone="invite"]')`),
      '#6519: it names the organisation and offers "Enter the details" and "Invite people"');
    check(await ev(`(S.me.workspaces || []).some(w => w.name === 'Frida Studio' && w.role === 'admin') && wsCur().startsWith('org:')`), '#6519: the organisation exists, frida is its admin, it is the workspace now');
    if (shot) await shot('orgdone-phone');
    await click(ev, '.oadonedlg [data-oadone="invite"]');
    check(await ready(ev, `!!document.querySelector('.modal .oinvform')?.getClientRects().length`, 60), '#6519: "Invite people" opens the invitation dialog');
    await ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1; })()`);
    check(await ready(ev, `!document.querySelector('.modal')`, 30), '#6519: and one gets back out');
    check(String(sql(`SELECT value FROM user_settings WHERE user_id=${ids.frida} AND key='org_ask'`)).includes('done'), '#6519: the question is answered for good');
    await nav(B + 'static/icon.svg'); await nav(B + '#inbox');
    await sleep(1500);
    check(await ev(`!document.querySelector('.oaskdlg')`), '#6519: the next start does not ask again');
  }, false);

  // ===== gina on a computer: Skip; then Settings > Organisation > Add an organisation ends in the closing step too
  await firefox(async o => {
    const {cmd, ev, ctx, nav} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    check(await signIn(o, 'gina') === 200, 'gina: login');
    await nav(B + '#inbox');
    check(await ready(ev, shown('.modal.oaskdlg'), 80), '#6519 computer: the question');
    await click(ev, '.oaskdlg [data-oask-skip]');
    check(await ready(ev, `!document.querySelector('.oaskdlg')`, 30), '#6519: Skip closes it');
    check(await ready(ev, shown('.tour'), 60), '#6519: then the welcome tour starts');
    check(await ev(`!(S.me.workspaces || []).length`), '#6519: Skip leaves the account private');
    check(String(sql(`SELECT value FROM user_settings WHERE user_id=${ids.gina} AND key='org_ask'`)).includes('done'), '#6519: Skip answers the question for good');
    await ev(`(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); return 1; })()`);
    await ready(ev, `!document.querySelector('.tour')?.getClientRects().length`, 30);
    await ev(`(() => { settingsModal('account'); return 1; })()`);
    check(await ready(ev, shown('.modal [data-wsorgadd]'), 80), '#6519: without an organisation Settings > Account shows "Add an organisation" (rollback test: no button without the fix)');
    await click(ev, '.modal [data-wsorgadd]');
    check(await ready(ev, `!!document.querySelector('.modal.cdlg input')`, 40), 'the name dialog');
    await ev(`(() => { const i = document.querySelector('.modal.cdlg input'); i.value = 'Gina Works'; i.dispatchEvent(new Event('input', {bubbles: true})); document.querySelector('.modal.cdlg [data-cd="yes"]').click(); return 1; })()`);
    check(await ready(ev, shown('.modal.oadonedlg'), 60), '#6519: after "Add an organisation" the closing step instead of only a message (rollback test: a toast without the fix)');
    await click(ev, '.oadonedlg [data-oadone="data"]');
    check(await ready(ev, `!document.querySelector('.oadonedlg') && !!document.querySelector('.modal.smodal')?.getClientRects().length`, 60), '#6519: "Enter the details" opens the settings');
  }, false);

  console.log(`p21414_b_orgask_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
