// 2.1208.0 (#6138) UI (jsdom): the date dialog puts "Repeat" right under the quick picks, the reminders sit in their own block
// kalmido-suite: fresh
// (shut by default, open once one is set), "Repeat reminder" has the bell, not the repeat icon.
const {boot, errs, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 80});  // 2.358.0 (#3286): the shared wait of tests/boot.js (default at least 15 s); an explicit n/ms keeps its window
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const L = (await call('POST', '/api/lists', {name: 'Plants'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Water', list_id: L, due: today()})).id;
  const w = await boot({user: 'alice', hash: 'l/' + L}), d = w.document;
  await sleep(600);
  w.__dialogs = 'manual';
  w.eval(`datePop(document.querySelector('#top h1'), ${T})`); await sleep(400);
  const pos = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & w.Node.DOCUMENT_POSITION_FOLLOWING));
  const quick = d.querySelector('#pop .quick'), rep = d.querySelector('#pop #p-rep'), cal = d.querySelector('#pop .cal, #pop [data-day]');
  check(rep && pos(quick, rep) && (!cal || pos(rep, cal)), 'Repeat sits under the quick picks, above the calendar');
  const blk = () => d.querySelector('#pop details.remblk');
  check(blk() && !blk().open, 'the reminders block is shut by default');
  check(pos(rep, blk()), 'the reminders block comes after Repeat');
  const nag = d.querySelector('#pop #p-nag');
  check(nag && blk().contains(nag), 'Repeat reminder lives in the reminders block');
  const icon = el => el.closest('.prow')?.querySelector('svg use, svg')?.outerHTML || '';
  check(nag && icon(nag) !== icon(rep), 'Repeat reminder has another icon than Repeat');
  blk().querySelector('summary').click(); await sleep(200);
  check(blk().open, 'the block opens by click');
  click(w, d.querySelector('#pop .remchips [data-rem]')); await sleep(300);
  check(blk() && blk().open && d.querySelector('#pop .remchips button.on'), 'a reminder can be set; the block stays open');
  click(w, d.querySelector('#pop [data-q="done"]')); await sleep(1200);
  const t = (await call('GET', '/api/state')).tasks.find(x => x.id === T);
  check(t.reminders, 'reminder saved: ' + t.reminders);
  w.eval(`datePop(document.querySelector('#top h1'), ${T})`); await sleep(400);
  check(blk() && blk().open, 'opened again with a reminder: the block is open');
  d.querySelector('#pop #p-rep').value = 'FREQ=DAILY'; d.querySelector('#pop #p-rep').dispatchEvent(new w.Event('change', {bubbles: true})); await sleep(300);
  click(w, d.querySelector('#pop [data-q="done"]')); await sleep(1200);
  check((await call('GET', '/api/state')).tasks.find(x => x.id === T).repeat === 'FREQ=DAILY', 'Repeat can be set at the top');
  w.close();
  check(!errs.length, 'jsdom: no JS errors ' + errs.join(' | '));
  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
