// kalmido-suite: fresh
// #6588 UI test (jsdom, own container; invented events only): a calendar import that did not take everything as it is in the
// file says so in a report dialog (static/js/calevents.js evImpReport), never only in a toast or a number:
//  - a series Kalmido cannot keep (FREQ=HOURLY) and an unreadable event: the report names both titles with their reasons; OK
//    closes it and the app is usable again (the calendar view still there)
//  - the server's cap ("limit" in the answer): "5000 of 7312 events imported" stands in the report (the answer is given by a
//    fetch stand-in: a real file of 7312 events would only make the suite slow, p21445_c_ics_report_test.py checks the server)
//  - a plain file: no dialog, the toast as before
// freelancer-matrix: pim
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, idle, until, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21445CIUI_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const ev = (uid, title, extra = '', start = 'DTSTART:20261201T090000Z\r\n') => `BEGIN:VEVENT\r\nUID:${uid}@example.com\r\nDTSTAMP:20261101T080000Z\r\nSUMMARY:${title}\r\n${start}DURATION:PT1H\r\n${extra}END:VEVENT\r\n`;
const cal = (...e) => `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Example//Guard//EN\r\n${e.join('')}END:VCALENDAR\r\n`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'frida', display_name: 'Frida', password: 'password123'})});
  check(r.ok, 'setup');
  const CF = await login('frida');
  await call(CF, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events,contacts'});
  const C = (await call(CF, 'POST', '/api/evcals', {name: 'Own'})).id;
  check(C, 'setup: an own calendar');

  const w = await boot({user: 'frida', hash: 'calendar'}), d = w.document;
  check(await until(() => w.eval('Array.isArray(S.evcals) && S.evcals.length > 0')), 'the calendars are loaded');
  w.eval(`importTargetConfirm = async () => 'here'; window.__toasts = []; const t0 = toast; toast = (m, ...a) => { __toasts.push(String(m)); return t0(m, ...a); };`);
  const run = async (text) => {
    w.__file = new w.File([text], 'termine.ics', {type: 'text/calendar'});
    await w.eval(`evImport(S.evcals.find(c => c.id === ${C}), () => {}, __file)`);
    await idle(w);
  };

  // 1 a series Kalmido cannot keep + an unreadable event: the report names them
  await run(cal(ev('hourly', 'Hourly standup', 'RRULE:FREQ=HOURLY;COUNT=3\r\n'), ev('broken', 'Broken thing', '', ''), ev('plain', 'Plain event')));
  const md = await until(() => [...d.querySelectorAll('.modal')].find(m => /Import finished/.test(m.textContent)));
  check(md, 'the report dialog opens after the import');
  const txt = md ? md.textContent : '';
  check(/Hourly standup/.test(txt) && /repeat rule is not supported/.test(txt), `the hourly series stands with its title and reason: ${txt.slice(0, 300)}`);
  check(/Broken thing/.test(txt) && /could not be read/.test(txt), 'the unreadable event stands with its title');
  check(/Imported: 2 new/.test(txt) && /1 not readable/.test(txt), `the counts are in it: ${txt.slice(0, 160)}`);
  check(md && !md.querySelector('[role="alert"]'), 'no cap note when nothing was cut off');
  const okb = md && [...md.querySelectorAll('button')].find(b => b.textContent.trim() === 'OK');
  check(okb, 'the report has an OK button');
  if (okb) okb.click();
  check(await until(() => !d.querySelector('.modal')), 'OK closes the report');
  check(d.querySelector('#main, main, .cal, #cal') !== null, 'the calendar view is still there');

  // 2 the cap: the answer of the server (stand-in) -> "5000 of 7312 events imported"
  w.eval(`window.__f0 = fetch; fetch = (u, o) => /\\/import/.test(String(u)) ? Promise.resolve({ok: true, status: 200, json: async () => ({created: 4990, updated: 10, skipped: 2312, errors: 0, total: 7312, limit: 5000, warnings: []})}) : __f0(u, o);`);
  await run(cal(ev('x', 'Anything')));
  const md2 = await until(() => [...d.querySelectorAll('.modal')].find(m => /Import finished/.test(m.textContent)));
  check(md2 && /5000 of 7312 events imported/.test(md2.textContent) && md2.querySelector('[role="alert"]'), `the cap is said: ${md2 ? md2.textContent.slice(0, 300) : '-'}`);
  if (md2) md2.querySelector('[data-eir="close"]').click();
  check(await until(() => !d.querySelector('.modal')), 'the close button closes it');
  w.eval(`fetch = __f0`);

  // 3 a plain file: the toast, no dialog
  w.__toasts.length = 0;
  await run(cal(ev('plain2', 'Another plain event')));
  check(await until(() => w.__toasts.some(t => /Imported: 1 new/.test(t))), `a plain file: the toast as before ${w.__toasts.join(' | ')}`);
  check(!d.querySelector('.modal'), 'a plain file: no report dialog');

  console.log(`p21445_c_ics_report_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
