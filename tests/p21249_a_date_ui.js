// 2.1249.0 (#6138) UI (jsdom): the date dialog puts "Repeat" right under the quick picks, the reminders sit in their own block
// kalmido-suite: fresh
// (shut by default, open once one is set, kept open over redraws), "Repeat reminder" has the bell, not the repeat icon.
const {boot, errs, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const task = async T => (await call('GET', '/api/state')).tasks.find(x => x.id === T);

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const L = (await call('POST', '/api/lists', {name: 'Plants'})).id;
  const T = (await call('POST', '/api/tasks', {title: 'Water', list_id: L, due: today()})).id;
  const w = await boot({user: 'alice', hash: 'l/' + L}), d = w.document;
  await until(() => w.eval(`typeof datePop === 'function' && !!taskById(${T})`));
  w.__dialogs = 'manual';
  const openDp = async () => { w.eval(`datePop(document.querySelector('#top h1'), ${T})`); return until(() => d.querySelector('#pop #p-rep')); };
  await openDp();
  const pos = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & w.Node.DOCUMENT_POSITION_FOLLOWING));
  const quick = d.querySelector('#pop .quick'), rep = d.querySelector('#pop #p-rep'), cal = d.querySelector('#pop .mcal');
  check(rep && cal && pos(quick, rep) && pos(rep, cal), 'Repeat sits under the quick picks, above the calendar');
  const blk = () => d.querySelector('#pop details.remblk');
  check(blk() && !blk().open, 'the reminders block is shut by default');
  check(pos(cal, blk()), 'the reminders block comes after the calendar');
  const nag = d.querySelector('#pop #p-nag');
  check(nag && blk().contains(nag) && blk().contains(d.querySelector('#pop .remchips')), 'reminder chips and Repeat reminder live in the reminders block');
  check(!blk().contains(d.querySelector('#pop #p-dl')), 'Deadline stays outside the reminders block');
  const icon = el => el.closest('.prow')?.querySelector('svg')?.outerHTML || '';
  check(nag && icon(nag) && icon(nag) !== icon(rep), 'Repeat reminder has another icon than Repeat');
  // usable: open the block, set a reminder (a redraw), the block stays open, saved
  click(w, blk().querySelector('summary'));
  check(await until(() => blk()?.open, {timeout: 3000}), 'the block opens by click on its title');
  click(w, d.querySelector('#pop .remchips [data-rem]'));
  check(await until(() => d.querySelector('#pop .remchips button.on'), {timeout: 3000}) && blk()?.open, 'a reminder can be set; the block stays open after the redraw');
  click(w, d.querySelector('#pop [data-q="done"]'));
  check(await until(async () => (await task(T))?.reminders), 'the reminder is saved');
  await until(() => !d.querySelector('#pop #p-rep'), {timeout: 5000});
  await openDp();
  check(blk() && blk().open, 'opened again with a reminder: the block is open');
  const r = d.querySelector('#pop #p-rep'); r.value = 'FREQ=DAILY'; r.dispatchEvent(new w.Event('change', {bubbles: true}));
  await until(() => d.querySelector('#pop #p-end'), {timeout: 3000});
  click(w, d.querySelector('#pop [data-q="done"]'));
  check(await until(async () => (await task(T))?.repeat === 'FREQ=DAILY'), 'Repeat can be set at the top');
  w.close();
  check(!errs.length, 'jsdom: no JS errors ' + errs.join(' | '));
  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
