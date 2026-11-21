// kalmido-suite: fresh
// #7501 UI: time entries and the timer on "write shows at once" (core.js rwRows, time.js TE_W) on a slow line. Own container
// (start.sh), jsdom. Invented tasks and notes only. Every write of time is held by the test (boot.js hold) and let through,
// refused or left without an answer one at a time.
// A. a new entry: the dialog closes at once, the entry stands in the task's list ("Saving…", the sums "Calculating…") before any
//    answer; Save clicked twice = one request, one entry; no GET /api/state after the save
// B. the timer: a double click on "Start timer" = one start, one timer (the second click does not stop it); Stop = gone at once
// C. a refusal (400): the dialog comes back with what was typed, the entry is not in the list
// D. no answer: the entry stays with "Not saved" and "Try again"; Try again saves it once
// E. the time page: an entry added there stands in the entries at once, the tiles say "Calculating…"; after the answer the
//    report reads its sums again (GET /api/time/report), never the whole state
// F. an entry removed: gone at once; refused (409) -> back in the list
// freelancer-matrix: time (a person without an organisation tracks time with the same code; the account here has none)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold, idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el, n = 1) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true, detail: n}));
const dlg = d => [...d.querySelectorAll('.modal')].pop() || null;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the account is in no organisation (freelancer case)');
  const WORK = (await call('POST', '/api/lists', {name: 'Work', kind: 'project', time_tracking: true})).id;
  const t1 = (await call('POST', '/api/tasks', {title: 'Write report', list_id: WORK})).id;
  const entries = async () => (await call('GET', `/api/time/entries?task_id=${t1}`)).entries || [];

  const w = await boot({user: 'alice', hash: 'l/' + WORK}), d = w.document;
  w.eval(`openDetail(${t1})`); await idle(w);
  check(await until(() => d.querySelector('#d-time [data-act="te-add"]')), 'the task\'s time section is there');
  hold(w, /\/api\/time\/(start|stop|entries)/);
  const f1 = w.fetch, log = []; w.fetch = (u, o) => { log.push(`${(o && o.method) || 'GET'} ${String(u)}`); return f1(u, o); };
  const stateReads = () => log.filter(x => /^GET .*\/api\/state(\?|$)/.test(x)).length;
  const rowsOf = () => [...d.querySelectorAll('#d-time .terow')];
  const rowWith = txt => rowsOf().find(r => r.textContent.includes(txt)) || null;
  const busy = () => w.eval('TE_W.pend > 0');
  const add = async (dur, note) => {
    click(w, d.querySelector('#d-time [data-act="te-add"]'));
    const md = await until(() => { const m = dlg(d); return m?.querySelector('#te-dur') && m; });
    md.querySelector('#te-dur').value = dur; md.querySelector('#te-note').value = note;
    return md;
  };

  // ================= A. a new entry stands at once, one request for two clicks, no state load
  let md = await add('1:30', 'held one');
  const st0 = stateReads();
  click(w, md.querySelector('[data-m="save"]')); click(w, md.querySelector('[data-m="save"]'), 2);
  check(await until(() => !md.isConnected || md.classList.contains('an-out') || !d.querySelector('.modal #te-dur')), 'A: the dialog closes at once');
  check(await until(() => rowWith('held one')), 'A: the entry is in the list before any answer');
  check(rowWith('held one')?.classList.contains('rw-saving') && !!rowWith('held one')?.querySelector('.rwsaving'), 'A: the entry says "Saving…"');
  check(!!d.querySelector('#d-time h5.rwcalc .rwcalcl'), 'A: the sums say "Calculating…"');
  check(await until(() => w.__q.length === 1) && w.__n === 1, `A: one request for two clicks (${w.__n})`);
  w.__go();
  check(await until(() => !busy() && !rowWith('held one')?.querySelector('.rwmark')), 'A: saved, no mark');
  check(await until(() => !d.querySelector('#d-time h5.rwcalc')), 'A: the sums are back');
  let es = await entries();
  check(es.filter(e => e.note === 'held one').length === 1 && es[0].seconds === 5400, 'A: one entry of 1:30 on the server: ' + es.map(e => e.note + ':' + e.seconds).join());
  await idle(w);
  check(stateReads() === st0, `A: no GET /api/state after the save (${log.filter(x => /api\/state/.test(x)).join(' | ')})`);
  check(/1:30/.test(d.querySelector('#d-time h5')?.textContent || '') || /1h 30|1 h 30|90/.test(d.querySelector('#d-time h5')?.textContent || ''), 'A: the task\'s total from the answer: ' + d.querySelector('#d-time h5')?.textContent);

  // ================= B. a double click on "Start timer" = one timer
  const n0 = w.__n, st1 = stateReads();
  click(w, d.querySelector('#d-time [data-act="timer-toggle"]'), 1);
  check(!!d.querySelector('#top .tmini'), 'B: the timer runs at once (the pill, before any answer)');
  click(w, d.querySelector('#d-time [data-act="timer-toggle"]'), 2);  // the second click of the double click: the button says Stop by now
  check(!!d.querySelector('#top .tmini') && w.eval('!!S.timer'), 'B: the second click does not stop it');
  check(await until(() => w.__q.length === 1) && w.__n - n0 === 1, `B: one start request (${w.__n - n0})`);
  w.__go(); check(await until(() => !busy()), 'B: started');
  let run = (await call('GET', '/api/state')).timer;
  check(run && run.task_id === t1, 'B: one timer on the server');
  await sleep(1100);  // wanted: the timer runs over a second (a shorter one is dropped as a misclick)
  click(w, d.querySelector('#d-time [data-act="timer-toggle"]'), 1);
  check(!d.querySelector('#top .tmini'), 'B: Stop: the pill is gone at once');
  check(await until(() => w.__q.length === 1), 'B: the stop is on its way'); w.__go();
  check(await until(() => !busy()), 'B: stopped');
  check(!(await call('GET', '/api/state')).timer && (await entries()).filter(e => e.source === 'timer').length === 1, 'B: no timer running, one timer entry');
  await idle(w);
  check(stateReads() === st1, 'B: no GET /api/state for start and stop');

  // ================= C. a refusal: the dialog back with the input
  md = await add('0:45', 'refused one');
  click(w, md.querySelector('[data-m="save"]'));
  check(await until(() => rowWith('refused one')), 'C: the entry stands at once');
  check(await until(() => w.__q.length === 1), 'C: its save is on its way');
  w.__fail(400);
  const md2 = await until(() => { const m = dlg(d); return m?.querySelector('#te-note')?.value === 'refused one' && m; });
  check(!!md2 && md2.querySelector('#te-dur').value === '0:45', 'C: the dialog is back with what was typed');
  check(!rowWith('refused one'), 'C: the refused entry is not in the list');
  click(w, md2?.querySelector('[data-m="close"]'));

  // ================= D. no answer: "Not saved" with "Try again", saved once
  w.eval('NET_T.w = 400');
  md = await add('0:20', 'lost answer');
  click(w, md.querySelector('[data-m="save"]'));
  check(await until(() => rowWith('lost answer')?.classList.contains('rw-failed')), 'D: no answer: the entry says "Not saved"');
  check(!!rowWith('lost answer')?.querySelector('[data-rwagain]'), 'D: with "Try again"');
  w.eval('NET_T.w = 20000');
  click(w, rowWith('lost answer').querySelector('[data-rwagain]'));
  for (let t = 0; t < 100 && (busy() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await until(() => !busy() && rowWith('lost answer') && !rowWith('lost answer').querySelector('.rwmark')), 'D: saved, no mark');
  check((await entries()).filter(e => e.note === 'lost answer').length === 1, 'D: on the server once');

  // ================= F. removed: gone at once; refused -> back
  const del = rowWith('held one')?.querySelector('[data-act="te-del"]');
  click(w, del);
  check(!rowWith('held one'), 'F: the entry is gone at once');
  check(await until(() => w.__q.length === 1), 'F: its removal is on its way');
  w.__fail(409);
  check(await until(() => rowWith('held one')), 'F: refused: the entry is back');
  check(await until(() => !busy()), 'F: nothing waits');

  // ================= E. the time page
  w.eval("LS.set('timeEntries', true); S.tv.entries = true; closeDetail()");
  w.location.hash = 'time';
  check(await until(() => d.querySelector('.timev .sttiles') && d.querySelector('.timev .terow')), 'E: the report with its entries');
  await idle(w);
  log.splice(0);
  click(w, d.querySelector('.timev [data-act="te-add"]'));
  md = await until(() => { const m = dlg(d); return m?.querySelector('#te-dur') && m; });
  md.querySelector('#te-target').value = 't:' + t1; md.querySelector('#te-dur').value = '0:10'; md.querySelector('#te-note').value = 'from the report';
  click(w, md.querySelector('[data-m="save"]'));
  check(await until(() => [...d.querySelectorAll('.timev .terow')].some(r => r.textContent.includes('from the report') && r.classList.contains('rw-saving'))), 'E: the entry stands in the report at once ("Saving…")');
  check(!!d.querySelector('.timev .sttiles.rwcalc') && /Calculating/.test(d.querySelector('.timev').textContent), 'E: the tiles say "Calculating…"');
  check(await until(() => w.__q.length === 1), 'E: its save is on its way'); w.__go();
  check(await until(() => !busy() && !d.querySelector('.timev .sttiles.rwcalc')), 'E: saved, the sums are back');
  await idle(w);
  check(log.some(x => /^GET .*\/api\/time\/report/.test(x)), 'E: the report read its sums again');
  check(!stateReads(), 'E: no GET /api/state: ' + log.filter(x => /api\/state/.test(x)).join(' | '));
  check([...d.querySelectorAll('.timev .terow')].filter(r => r.textContent.includes('from the report')).length === 1, 'E: the entry once in the report');

  w.__off();
  check(!errs.length, 'no script errors ' + errs.join(' | ')); errs.splice(0);
  w.close();
  console.log(`p7501_zeit_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
