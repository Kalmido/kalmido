// kalmido-suite: fresh
// #7503 UI: the receipts of a trip and the drives of the logbook on "write shows at once" (core.js rwOps) on a slow line. Own
// container (start.sh, mode workspaces), jsdom. Invented places and figures only. Every write is held by the test (boot.js hold)
// and let through, refused or failed one at a time. Run for a member of an organisation and for a person without one (P4).
// A. two receipts added one after the other while the first answer is held: both stay in the trip ("Saving…"), the sum says
//    "Calculating…"; the answers bring both, none vanishes; on the server both once
// B. a receipt whose save fails (500): it stays with "Not saved" and "Try again"; Try again saves it
// C. a refused receipt (400): the dialog comes back with what was typed
// D. two drives one after the other while the first answer is held: both stand in the logbook; the second one's dialog starts at
//    the end odometer of the first; on the server both, no overlap warning
// E. a drive whose save fails (500): the row stays with "Try again" (no endless "Still syncing")
// F. "Bill on" clicked twice while the drafts load: one dialog
// freelancer-matrix: office (the own office of a person without an organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
const TC = require('./testclock');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el, n = 1) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true, detail: n}));
const FEAT = 'cal,comments,collab,office,clients';
const DAY = TC.today();

async function round(who, ck) {
  const trip = await call(ck, 'POST', '/api/office/trips', {dest: 'Kiel', date_from: DAY, date_to: DAY, purpose: 'job'});
  check(trip.http === 201, `${who}: a trip ${trip.http}`);
  const veh = await call(ck, 'POST', '/api/office/vehicles', {name: 'Kombi', kind: 'private', odo_start: '1000'});
  check(veh.http === 201, `${who}: a vehicle ${veh.http}`);
  const items = async () => ((await call(ck, 'GET', `/api/office/trips?year=${DAY.slice(0, 4)}`)).trips || []).find(t => t.id === trip.id)?.items || [];
  const drives = async () => (await call(ck, 'GET', `/api/office/drives?year=${DAY.slice(0, 4)}&vehicle_id=${veh.id}`)).drives || [];

  const w = await boot({user: who, hash: 'office/travel'}), d = w.document;
  const dlg = () => [...d.querySelectorAll('.modal.ofcdlg')].filter(m => !m.classList.contains('an-out')).pop() || null;
  const its = () => [...d.querySelectorAll('#rk-its .rkit')];
  const itWith = re => its().find(r => re.test(r.textContent)) || null;
  check(await until(() => [...d.querySelectorAll('.rklist [data-rk="open"]')].some(b => /Kiel/.test(b.textContent))), `${who}: the trip list`);
  click(w, [...d.querySelectorAll('.rklist [data-rk="open"]')].find(b => /Kiel/.test(b.textContent)));
  check(await until(() => d.querySelector('#rk-its [data-rk="add"]')), `${who}: the trip is open`);
  hold(w, /\/api\/office\/(trips|drives)/);
  const tw = () => w.eval(`!!RK_WS.get(${trip.id})?.pend`);
  const addIt = async (amt, text) => {
    click(w, d.querySelector('#rk-its [data-rk="add"]'));
    const m = await until(() => dlg()?.querySelector('#rk-amt') && dlg());
    m.querySelector('#rk-amt').value = amt; m.querySelector('#rk-text').value = text;
    click(w, m.querySelector('[data-m="save"]'));
  };

  // ================= A. two receipts, the first answer held
  await addIt('20', 'Taxi');
  check(await until(() => itWith(/Taxi/)?.classList.contains('rw-saving')), `${who}: A: the first receipt stands at once ("Saving…")`);
  check(await until(() => w.__q.length === 1), `${who}: A: its save is on its way`);
  await addIt('35', 'Train');
  check(await until(() => itWith(/Train/)) && itWith(/Taxi/), `${who}: A: the second one stands next to the first`);
  check(!!d.querySelector('#rk-its.rwcalc .rwcalcl'), `${who}: A: the sum says "Calculating…"`);
  w.__go();
  check(await until(() => w.__q.length === 1), `${who}: A: the first is answered, the second goes after it`);
  check(itWith(/Taxi/) && itWith(/Train/), `${who}: A: after the first answer both are still there: ` + its().map(r => r.textContent.trim().slice(0, 30)).join(' | '));
  w.__go();
  check(await until(() => !tw() && !d.querySelector('#rk-its .rwmark') && !d.querySelector('#rk-its.rwcalc')), `${who}: A: both saved, no mark, the sum is back`);
  check(/55[.,]00/.test(d.querySelector('#rk-its .rksum0')?.textContent || ''), `${who}: A: the sum from the server: ` + d.querySelector('#rk-its .rksum0')?.textContent);
  let s = await items();
  check(s.filter(i => i.text === 'Taxi').length === 1 && s.filter(i => i.text === 'Train').length === 1, `${who}: A: on the server both once: ` + s.map(i => i.text).join());
  check(its().length === 2, `${who}: A: two rows`);

  // ================= B. a failed save: "Not saved", Try again
  await addIt('12', 'Parking');
  check(await until(() => w.__q.length === 1), `${who}: B: its save is on its way`);
  w.__fail(500);
  check(await until(() => itWith(/Parking/)?.classList.contains('rw-failed') && itWith(/Parking/).querySelector('[data-rwagain]')), `${who}: B: "Not saved" with "Try again"`);
  click(w, itWith(/Parking/).querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), `${who}: B: Try again sends it`); w.__go();
  check(await until(() => !tw() && itWith(/Parking/) && !itWith(/Parking/).querySelector('.rwmark')), `${who}: B: saved`);
  check((await items()).filter(i => i.text === 'Parking').length === 1, `${who}: B: on the server once`);

  // ================= C. a refusal: the dialog back with the input
  await addIt('7', 'Coffee');
  check(await until(() => w.__q.length === 1), `${who}: C: its save is on its way`);
  w.__fail(400);
  check(await until(() => dlg()?.querySelector('#rk-text')?.value === 'Coffee' && /7/.test(dlg().querySelector('#rk-amt').value)), `${who}: C: the dialog is back with what was typed`);
  check(!itWith(/Coffee/), `${who}: C: the refused receipt is not in the list`);
  click(w, dlg()?.querySelector('[data-m="close"]'));
  await until(() => !dlg());

  // ================= F. "Bill on" twice: one dialog
  check(await until(() => !tw()), `${who}: F: nothing waits`);
  w.__off();
  for (const b of d.querySelectorAll('#rk-its [data-rk="sel"]:not([disabled])')) { b.checked = true; b.dispatchEvent(new w.Event('change', {bubbles: true})); }
  check(await until(() => d.querySelector('[data-rk="bill"]')), `${who}: F: the bar "Bill on"`);
  w.eval(`rk_billModal(rk_trip(${trip.id})); rk_billModal(rk_trip(${trip.id}))`);
  check(await until(() => [...d.querySelectorAll('.modal')].some(m => /Bill receipts on/.test(m.textContent))), `${who}: F: the dialog opens`);
  await sleep(200);  // wanted: a second dialog would be there by now
  check([...d.querySelectorAll('.modal')].filter(m => /Bill receipts on/.test(m.textContent)).length === 1, `${who}: F: one dialog`);
  for (const m of d.querySelectorAll('.modal')) m.remove();
  w.eval('RK.sel.clear()');

  // ================= D. two drives, the first answer held
  click(w, d.querySelector('[data-rk="back"]'));
  check(await until(() => d.querySelector('[data-rk="view"][data-v="logbook"]')), `${who}: D: the list`);
  click(w, d.querySelector('[data-rk="view"][data-v="logbook"]'));
  check(await until(() => d.querySelector('[data-lgb="new"]')), `${who}: D: the logbook`);
  hold(w, /\/api\/office\/(trips|drives)/);
  const rows = () => [...d.querySelectorAll('#lgb-drives .lgb-list li')];
  const rowWith = re => rows().find(r => re.test(r.textContent)) || null;
  const addDr = async (dest, end, at) => {
    click(w, d.querySelector('[data-lgb="new"]'));
    const m = await until(() => dlg()?.querySelector('#lgb-o1') && dlg());
    const start = m.querySelector('#lgb-o0').value;
    m.querySelector('#lgb-start').value = at; m.querySelector('#lgb-dest').value = dest; m.querySelector('#lgb-o1').value = end;
    m.querySelector('#lgb-o1').dispatchEvent(new w.Event('input', {bubbles: true}));
    click(w, m.querySelector('[data-m="save"]'));
    return start;
  };
  const lw = () => w.eval('LB_W.pend > 0');
  const st1 = await addDr('Kiel', '1100', 'Hamburg');
  check(/^1[.,]?000$/.test(st1), `${who}: D: the first drive starts at the vehicle's odometer (${st1})`);
  check(await until(() => rowWith(/Kiel/)?.classList.contains('rw-saving')), `${who}: D: the first drive stands at once ("Saving…")`);
  check(await until(() => w.__q.length === 1), `${who}: D: its save is on its way`);
  const st2 = await addDr('Lübeck', '1180', 'Kiel');
  check(/^1[.,]?100$/.test(st2), `${who}: D: the second drive starts at the end of the first (${st2})`);
  check(await until(() => rowWith(/Lübeck/)) && rowWith(/Kiel/), `${who}: D: both stand in the logbook`);
  w.__go();
  check(await until(() => w.__q.length === 1), `${who}: D: the first is answered, the second goes after it`);
  check(rowWith(/Lübeck/) && rowWith(/Hamburg/), `${who}: D: after the first answer both are still there`);
  w.__go();
  check(await until(() => !lw() && !d.querySelector('#lgb-drives .rwmark')), `${who}: D: both saved, no mark`);
  const ds = await drives();
  check(ds.length === 2 && ds.some(x => x.dest === 'Lübeck' && +x.odo_start === 1100) && ds.every(x => !x.warn), `${who}: D: on the server both, the second from 1100, no warning: ` + JSON.stringify(ds.map(x => [x.dest, x.odo_start, x.warn])));

  // ================= E. a failed drive: "Try again"
  await addDr('Flensburg', '1260', 'Lübeck');
  check(await until(() => w.__q.length === 1), `${who}: E: its save is on its way`);
  w.__fail(500);
  check(await until(() => rowWith(/Flensburg/)?.classList.contains('rw-failed') && rowWith(/Flensburg/).querySelector('[data-rwagain]')), `${who}: E: the row says "Not saved" with "Try again"`);
  click(w, rowWith(/Flensburg/).querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), `${who}: E: Try again sends it`); w.__go();
  check(await until(() => !lw() && rowWith(/Flensburg/) && !rowWith(/Flensburg/).querySelector('.rwmark')), `${who}: E: saved`);
  check((await drives()).filter(x => x.dest === 'Flensburg').length === 1, `${who}: E: on the server once`);
  w.__off();
  check(!errs.length, `${who}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await round('alice', CA);
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  await round('frida', CF);
  console.log(`p7503_reisen_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
