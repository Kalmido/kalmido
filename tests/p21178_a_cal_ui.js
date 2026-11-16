// 2.1178.0 UI test, part A (#6153): a date opened from a series changes only that date unless "All dates" is chosen on purpose;
// kalmido-suite: fresh
// saving in the editor offers Undo (the server's step of the write, obj_undo) like dragging and deleting. jsdom, own container
// (start.sh), invented names only. P21178A_NOSTART=1 / KMT_NOSTART=1 = the container runs.
// freelancer-matrix: n/a (no new route; alice has no organisation, every check runs without one)
//  - a daily series, one date opened in the editor: "Only this date" is preset (on, aria-checked), the date's own day shown,
//    no repeat row; title changed + saved -> only this date has the new title, the other dates and the series keep theirs
//    (server and the month view: one chip with the new title, the others with the old one)
//  - the toast "Event saved" offers Undo: the date's own change is gone again, the month view shows the old title only
//  - "All dates" chosen on purpose: the whole series takes the title; Undo brings the old title back
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, B, login, undoToast} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return !!c; };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21178A_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); let j = {}; try { j = await r.json(); } catch { /* no body */ } return {http: r.status, ...j}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const pad = n => String(n).padStart(2, '0');
const dstr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
// the series lies in the current month (the month view opens on it): starts on the 1st .. 10th, five days long
const base = (() => { const d = new Date(); d.setDate(Math.min(d.getDate(), 10)); return d; })();
const day = n => { const d = new Date(base); d.setDate(d.getDate() + n); return dstr(d); };
const D0 = day(0), D2 = day(2);

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events'});
  check(!((await call('GET', '/api/state')).orgs || []).length, 'a person without an organisation');
  const W = await call('POST', '/api/evcals', {name: 'Work', color: '#2dd4bf'});
  const SE = await call('POST', '/api/events', {title: 'Team round', cal_id: W.id, start: `${D0}T09:00`, end: `${D0}T09:30`, tz: TZ, reminders: [], rrule: 'FREQ=DAILY;COUNT=5'});
  check(SE.id, 'a daily series ' + JSON.stringify(SE));
  const occ = `${D2}T09:00`;
  const get = () => call('GET', `/api/events/${SE.id}`);
  const ovOf = x => (x.overrides || []).find(o => o.rid === occ);

  const w = await boot({user: 'alice', hash: 'cal', ls: {'tasks.calMode': '"month"'}}), d = w.document;
  await until(() => w.eval(`typeof evEditor === 'function' && Array.isArray(S.cal?.items)`));
  // what the month view shows: the titles of the series' chips (the month cells' chips, not the day list beside them)
  const shown = () => [...d.querySelectorAll('#view .cev[data-cev]')].map(x => x.textContent + ' ' + (x.title || '')).filter(t => /round/.test(t));
  const count = re => shown().filter(t => re.test(t)).length;
  check(await until(() => count(/Team round/) === 5), 'the month view shows the five dates of the series ' + JSON.stringify(shown()));
  // the editor as the popover's "Edit" opens it (calevents.js: evEditor({ev, occ}))
  const open = async () => {
    const full = await get();
    w.eval(`evEditor({ev: ${JSON.stringify(full)}, occ: ${JSON.stringify(occ)}})`);
    return until(() => d.querySelector('.modal.evmodal [data-evsc]') && d.querySelector('.modal.evmodal'));
  };

  // ---- 1. a date of the series: "Only this date" preset, its own day shown, no repeat row
  let md = await open();
  const one = md && md.querySelector('[data-evsc="one"]'), all = md && md.querySelector('[data-evsc="all"]');
  check(one && one.classList.contains('on') && one.getAttribute('aria-checked') === 'true' && !all.classList.contains('on') && all.getAttribute('aria-checked') === 'false',
    '#6153: "Only this date" is preset, "All dates" not ' + (md && [one?.className, all?.className]));
  check(md && md.querySelector('#ev-sd').value === D2 && md.querySelector('#ev-stm').value === '09:00' && md.querySelector('.evrep').hidden,
    '#6153: the editor shows the opened date (its day, no repeat row) ' + (md && [md.querySelector('#ev-sd').value, md.querySelector('#ev-stm').value]));
  md.querySelector('#ev-title').value = 'Team round (longer today)';
  click(w, md.querySelector('[data-evm="save"]'));
  let x = await until(async () => { const y = await get(); return ovOf(y)?.title === 'Team round (longer today)' ? y : null; });
  check(x && x.title === 'Team round' && x.overrides.length === 1 && ovOf(x).start === occ && x.rrule === 'FREQ=DAILY;COUNT=5',
    '#6153: saving changed only the opened date, the series keeps its title ' + JSON.stringify(x && [x.title, x.rrule, x.overrides]));
  check(await until(() => !d.querySelector('.modal.evmodal')), 'the editor closed');
  check(await until(() => count(/longer today/) === 1 && count(/Team round(?! \()/) === 4),
    '#6153: the month view shows one date with the new title, the other four with the old one ' + JSON.stringify(shown()));

  // ---- 2. Undo of the toast: the date's own change goes again
  check(await undoToast(w, 'Event saved'), '#6153: the toast "Event saved" offers Undo');
  x = await until(async () => { const y = await get(); return !(y.overrides || []).length ? y : null; });
  check(x && x.title === 'Team round' && !(x.exdates || []).length, '#6153: Undo took the date\'s own change back, the series as before ' + JSON.stringify(x && [x.title, x.overrides, x.exdates]));
  check(await until(() => !count(/longer today/) && count(/Team round/) === 5), '#6153: after Undo the month view shows the old title on all five dates ' + JSON.stringify(shown()));

  // ---- 3. "All dates" chosen on purpose: the whole series; Undo brings the old title back
  md = await open();
  click(w, md.querySelector('[data-evsc="all"]'));
  check(md.querySelector('[data-evsc="all"]').classList.contains('on') && !md.querySelector('.evrep').hidden && md.querySelector('#ev-sd').value === D0,
    '"All dates": the series\' first day and the repeat row ' + md.querySelector('#ev-sd').value);
  md.querySelector('#ev-title').value = 'Daily round';
  click(w, md.querySelector('[data-evm="save"]'));
  x = await until(async () => { const y = await get(); return y.title === 'Daily round' ? y : null; });
  check(x && !(x.overrides || []).length && x.start === `${D0}T09:00` && x.end === `${D0}T09:30` && x.rrule === 'FREQ=DAILY;COUNT=5',
    '"All dates": the whole series took the title, its times and rule stay ' + JSON.stringify(x && [x.start, x.end, x.rrule, x.overrides]));
  check(await until(() => count(/Daily round/) === 5), '"All dates": the month view shows the new title on all five dates ' + JSON.stringify(shown()));
  check(await undoToast(w, 'Event saved'), '#6153: the toast offers Undo after "All dates" as well');
  x = await until(async () => { const y = await get(); return y.title === 'Team round' ? y : null; });
  check(x && x.rrule === 'FREQ=DAILY;COUNT=5' && !(x.overrides || []).length, '#6153: Undo brought the series\' old title back ' + JSON.stringify(x && [x.title, x.rrule]));
  check(await until(() => !count(/Daily round/) && count(/Team round/) === 5), '#6153: after Undo the month view shows the old title again ' + JSON.stringify(shown()));

  w.close();
  console.log(`p21178_a_cal_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
