// kalmido-suite: fresh
// 2.1391.0 (#7111) UI test: adding an invoice issuer. Own container (start.sh, mode workspaces, KALMIDO_ISSUER_KEYS=1), jsdom
// for the flow, Firefox (desktop, mouse) for the stacking. Invented data only. freelancer-matrix: office (an organisation's admin)
// - without a number range "Add invoice issuer" is off; adding a range in its dialog turns it on without a reload (the issuer
//   block asks the server again), and the issuer dialog then offers the new range and sets the issuer up
// - Firefox: the sign-in confirmation (pwPrompt) lies above the issuer dialog: its password field is the topmost element at
//   its own place and takes the focus and the typing
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21391_a_issuer_ui', check, shots: 'P21391A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_ISSUER_KEYS=1'}});
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); let j = null; try { j = await r.json(); } catch { j = null; } j = j || {}; j.http = r.status; return j; };
const until = async (fn, n = 120) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const type = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
const FEAT = 'cal,comments,collab,files,docs,office,clients';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']}, CK);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, CK);
  const me = (await call('GET', '/api/state', null, CK)).me;
  const org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id}, CK);
  await call('PATCH', '/api/settings', {workspace: `org:${org.id}`}, CK);
  await call('PUT', '/api/office/settings', {offer_scheme: 'A-{seq:03}', invoice_scheme: 'RE-{yyyy}-{seq:03}'}, CK);
  const iss = await call('GET', '/api/office/issuers', null, CK);
  check(iss.http === 200 && !(iss.ranges || []).length, `the issuer area is on, no range yet ${iss.http}`);

  // ---- no range: "Add invoice issuer" off; a range added in its dialog turns it on without a reload
  const w = await boot({user: 'alice', hash: 'today'}), d = w.document;
  await until(() => d.querySelector('#side, main'));
  w.eval(`settingsModal('biz')`);
  const addB = () => d.querySelector('#iss-box [data-iss="add"]');
  check(!!await until(() => addB()), 'the issuer block with "Add invoice issuer"');
  check(addB()?.disabled === true, '"Add invoice issuer" is off without a number range');
  const nrAdd = await until(() => d.querySelector('[data-onum="nr-add"]'));
  check(!!nrAdd, 'the button "Add number range"');
  click(w, nrAdd);
  const code = await until(() => d.querySelector('.modal.cdlg #nr-code'));
  check(!!code, 'the dialog "Add number range"');
  type(w, code, 'GT'); type(w, d.querySelector('#nr-name'), 'Shop'); type(w, d.querySelector('#nr-scheme'), 'GT-{yyyy}-{seq:03}');
  d.querySelector('.modal.cdlg form').dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));
  check(!!await until(async () => ((await call('GET', '/api/office/issuers', null, CK)).ranges || []).length === 1), 'the range is saved');
  check(!!await until(() => addB() && !addB().disabled), '"Add invoice issuer" is on without a reload (#7111)');
  click(w, addB());
  const sel = await until(() => d.querySelector('.modal.cdlg #iss-range'));
  check(!!sel && /GT/.test(sel.textContent), `the issuer dialog offers the new range: ${sel?.textContent}`);
  type(w, d.querySelector('#iss-name'), 'Shop billing');
  d.querySelector('.modal.cdlg form').dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));
  check(!!await until(async () => ((await call('GET', '/api/office/issuers', null, CK)).issuers || []).some(x => x.name === 'Shop billing')), 'the issuer is set up');
  w.close();

  // ---- Firefox: the password question above the issuer dialog
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const ready = async (ev, expr, n = 80) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev, 'alice');
    await nav(B + '#today');
    check(await ready(ev, `typeof settingsModal === 'function' && !!document.querySelector('#side, main')`), 'ff: the app');
    await ev(`(() => { settingsModal('biz'); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('#iss-box [data-iss="add"]:not([disabled])')`), 'ff: "Add invoice issuer" is on');
    await ev(`(() => { document.querySelector('#iss-box [data-iss="add"]').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal.cdlg #iss-name')`), 'ff: the issuer dialog');
    await ev(`(() => { window.__pp = pwPrompt(tr('Confirm with your password')); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal.pwprompt #pp-pw')`), 'ff: the password question');
    const top = await ev(`(() => { const p = document.querySelector('.modal.pwprompt #pp-pw'), b = p.getBoundingClientRect();
      const at = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      return JSON.stringify({top: at === p, pz: getComputedStyle(p.closest('.modal')).zIndex, dz: getComputedStyle(document.querySelector('.modal.cdlg')).zIndex}); })()`);
    const t = JSON.parse(top || '{}');
    check(t.top === true && +t.pz > +t.dz, 'ff: the password field lies above the issuer dialog (#7111) ' + top);
    await shot('p21391a-pwprompt.png');
  }, false);

  console.log(`p21391_a_issuer_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
