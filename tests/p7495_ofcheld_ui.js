// #7495 UI tests, own container (start.sh), jsdom, invented data only: a reload of an office area keeps what it shows
// kalmido-suite: fresh
// (office.js ofcRefetch) instead of emptying its data and showing the big loading block; each answer is held back on purpose
// (the window's fetch waits, a slow connection), so the order is the same on every machine
// - Subscriptions: a saved change (the dialog) while the list's answer is held: the rows stay on screen (the same nodes, no
//   loading block), dimmed and busy (.ofcbody.ofcheld, aria-busy); the fresh list replaces them once the answer comes
// - the fetch fails: the rows stay, above them the reason with "Try again"; "Try again" fetches again and the line goes
// - Cash flow: another number of months keeps the old plan dimmed instead of the loading block until the new one is there
// - a dialog built from the area's data while the fetch runs (#7064): the subscription opens with its fields
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const until = fn => until0(fn, {timeout: 15000, step: 100});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients,docs';
const YM = new Date().toISOString().slice(0, 7);
// GET answers to URLs matching re wait until the returned function is called (a slow network, held by the test); fail: answer 500
function hold(w, re, fail) {
  const f0 = w.fetch; let rel = null; const held = new Promise(r => { rel = r; }); const st = {n: 0};
  w.fetch = (u, o = {}) => {
    if (!re.test(String(u)) || (o.method && o.method !== 'GET')) return f0(u, o);
    st.n++;
    if (fail) return Promise.resolve(new Response(JSON.stringify({detail: 'Example failure'}), {status: 500, headers: {'Content-Type': 'application/json'}}));
    return held.then(() => f0(u, o));
  };
  st.go = () => { rel(); w.fetch = f0; };
  return st;
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ids = [];
  for (const [label, amount] of [['Example Mail', 12], ['Example Chat', 8], ['Example Cloud', 30]]) {
    const j = await call('POST', '/api/office/fixed-costs', {label, amount, start: YM + '-01', repeat: 'monthly', vat_rate: 19, sub: 1});
    check(j.http === 201 || j.http === 200, `the subscription ${label} ${j.http}`); ids.push(j.id);
  }

  // ================= Subscriptions: a saved change while the list's answer is held
  const w = await boot({hash: 'office/subs'}); const d = w.document;
  const rows = () => [...d.querySelectorAll('.office .abo-row')];
  const body = () => d.querySelector('.office .ofcbody');
  const row = t => rows().find(x => x.textContent.includes(t));
  check(await until(() => rows().length === 3), 'the subscriptions are listed ' + rows().length);
  const chat = row('Example Chat');
  click(w, row('Example Mail')?.querySelector('[data-abo="edit"]'));
  const dlg = await until(() => d.querySelector('.modal #abo-label'));
  check(!!dlg, 'the dialog of a subscription opens');
  const h1 = hold(w, /\/api\/office\/subs(\?|$)/);
  if (dlg) { dlg.value = 'Example Mail Pro'; click(w, d.querySelector('.modal [data-m="save"]')); }
  check(await until(async () => (await call('GET', '/api/office/subs')).items?.some(f => f.label === 'Example Mail Pro')), 'the change is saved');
  check(await until(() => h1.n > 0 && !d.querySelector('.modal #abo-label')), 'the dialog closed and the list is being fetched again');
  check(rows().length === 3 && !d.querySelector('.office .eload.es-big'), 'while it loads: the rows stay, no loading block ' + rows().length);
  check(row('Example Chat') === chat && chat.isConnected, 'while it loads: the same rows (nothing drawn anew, the place stays)');
  check(body()?.classList.contains('ofcheld') && body()?.getAttribute('aria-busy') === 'true', 'while it loads: dimmed and busy');
  // #7064: a dialog built from the data while the fetch runs has them
  click(w, row('Example Cloud')?.querySelector('[data-abo="edit"]'));
  check(await until(() => d.querySelector('.modal #abo-label')?.value === 'Example Cloud'), 'while it loads: a row opens its dialog with its data');
  for (const m of d.querySelectorAll('.modal')) m.remove();
  h1.go();
  check(await until(() => row('Example Mail Pro') && !body()?.classList.contains('ofcheld') && !body()?.hasAttribute('aria-busy')), 'the fresh list replaces the rows, no longer dimmed');

  // ================= the fetch fails: the rows stay, the reason and "Try again" above them
  const h2 = hold(w, /\/api\/office\/subs(\?|$)/, true);
  w.eval('aboReload()');  // what every write of the area ends with
  check(await until(() => d.querySelector('.office .ofcheldErr [data-esretry]')), 'a failed fetch: "Try again" above the rows');
  check(rows().length === 3 && !d.querySelector('.office .eload.es-big') && !body()?.classList.contains('ofcheld'), 'a failed fetch: the rows stay, not dimmed any more');
  h2.go();
  click(w, d.querySelector('.office .ofcheldErr [data-esretry]'));
  check(await until(() => !d.querySelector('.office .ofcheldErr') && rows().length === 3), '"Try again" fetches again and the line goes');

  // ================= Cash flow: another number of months keeps the old plan dimmed
  location: {
    w.location.hash = '#office/cashflow';
    const bar = () => d.querySelector('.office .rkcfbar');
    if (!await until(() => bar() && d.querySelector('.office [data-rkf="months"]:not(.on)'))) { check(false, 'the cash flow plan is shown'); break location; }
    const h3 = hold(w, /\/api\/office\/cashflow\?/);
    const was = bar();
    click(w, d.querySelector('.office [data-rkf="months"]:not(.on)'));
    check(await until(() => h3.n > 0), 'another number of months fetches the plan again');
    check(bar() === was && !d.querySelector('.office .eload.es-big') && body()?.classList.contains('ofcheld'), 'while it loads: the old plan stays, dimmed, no loading block');
    h3.go();
    check(await until(() => !body()?.classList.contains('ofcheld')), 'the new plan is there, no longer dimmed');
  }
  w.close();
  console.log(`p7495_ofcheld_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
