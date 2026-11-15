// kalmido-suite: fresh
// 2.1211.0 UI test, part A (#6148: office device dialog and units), own container (start.sh, mode workspaces), Firefox
// (desktop + phone width). Invented names and figures only.
// - the sections "Purchase and value" / "Warranty and maintenance" show the details arrow (a list-item summary) and open as soon
//   as a field inside is filled (serial number, vendor, warranty date), not only for price / date
// - a unit (EUR in the device dialog, days / EUR in the office settings) stands on the same line as its field, at every width
// - the empty set list: a symbol and "Import…" shaped like a button
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21211_a_device_ui', check, shots: 'P21211ADEV_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21211ADEV_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,office,clients';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  // a device with ONLY a serial number and a warranty date: the sections must open by themselves
  const dev = await call(CA, 'POST', '/api/office/equipment', {name: 'Kamera Beta', category: 'Kamera', serial_no: 'SN-4711', warranty_until: '2030-01-31'});
  check(dev.http === 201, 'a device ' + dev.http);

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  // the unit element after a field is on the field's line (its centre inside the field's vertical extent)
  const sameLine = (field, unit) => `(() => { const f = document.querySelector('${field}'), u = ${unit}; if (!f || !u) return false; const a = f.getBoundingClientRect(), b = u.getBoundingClientRect(); return b.width > 0 && b.left >= a.right - 1 && b.top + b.height / 2 > a.top && b.top + b.height / 2 < a.bottom; })()`;

  for (const [w, h, tag] of [[1280, 900, 'desktop'], [768, 900, 'tablet'], [390, 844, 'phone']]) await firefox(async ({cmd, ev, ctx, nav}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev, 'alice');
    await nav(B + '#office/equipment');
    check(await ready(ev, `!!document.querySelector('.ofcrow[data-id="${dev.id}"]')`, 80), tag + ': the equipment list');
    // empty sets: symbol + a button "Import…"
    check(await ev(`(() => { const e = [...document.querySelectorAll('.ofcgrp')].find(x => x.textContent === 'Sets')?.nextElementSibling; return !!e && e.classList.contains('empty') && !!e.querySelector('svg') && /No sets yet/.test(e.textContent); })()`), tag + ': empty sets with a symbol');
    check(await ev(`(() => { const a = document.querySelector('.oimlink:not(.e) a'); return !!a && /Import…/.test(a.textContent) && a.classList.contains('btn'); })()`), tag + ': "Import…" is a button');
    await ev(`(() => { document.querySelector('.ofcrow[data-id="${dev.id}"]').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal #of-serial_no')`), tag + ': the device dialog');
    // 6148: both sections are open (serial number / warranty alone) and show a real arrow
    check(await ev(`[...document.querySelectorAll('.modal .ast-sec')].length === 2 && [...document.querySelectorAll('.modal .ast-sec')].every(d => d.open)`), tag + ': sections open when a field is filled');
    check(await ev(`(() => { const v = document.querySelector('.modal #of-serial_no'); const r = v.getBoundingClientRect(); return r.width > 0 && r.height > 0 && v.value === 'SN-4711'; })()`), tag + ': the serial number is visible');
    check(await ev(`[...document.querySelectorAll('.modal .ast-sec>summary')].every(s => getComputedStyle(s).display === 'list-item')`), tag + ': the summary keeps its arrow (list-item)');
    // closed section: only the arrow row, it can be opened by the click
    await ev(`(() => { document.querySelector('.modal .ast-sec').open = false; return 1; })()`);
    check(await ev(`(() => { const s = document.querySelector('.modal .ast-sec>summary'); return getComputedStyle(s).listStyleType !== 'none' && s.getBoundingClientRect().height >= 40; })()`), tag + ': closed section shows its marker');
    await ev(`(() => { document.querySelector('.modal .ast-sec').open = true; return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal #of-purchase_net')`), tag + ': purchase price field');
    check(await ev(sameLine('.modal #of-purchase_net', `document.querySelector('.modal #of-purchase_net').parentElement.querySelector('.ofunit')`)), tag + ': EUR beside the purchase price');
    await ev(`(() => { document.querySelector('.modal [data-m="close"], .modal .iconbtn[aria-label="Close"]')?.click(); return 1; })()`);
    // the office settings: days / EUR beside the field
    await nav(B + '#office/settings');
    check(await ready(ev, `!!document.querySelector('#os-paydays')`, 80), tag + ': the office settings');
    check(await ev(sameLine('#os-paydays', `document.querySelector('#os-paydays').parentElement.querySelector('.muted')`)), tag + ': "days" beside the payment terms');
    check(await ev(sameLine('#os-rmfee', `document.querySelector('#os-rmfee').parentElement.querySelector('.muted')`)), tag + ': the currency beside the reminder fee');
  }, false);

  console.log(`p21211_a_device_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
