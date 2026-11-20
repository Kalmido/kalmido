// kalmido-suite: fresh
// #6381 UI: no wrong state before the content comes. Own container (start.sh with KALMIDO_STATE_LAZY_MIN=20, so a few tasks
// make the account "big"). jsdom. Invented texts only. Each slow answer is held back on purpose (the window's fetch waits).
// freelancer-matrix: tasks, agents (alice without an organisation)
// 1. a view whose module loads on demand (contacts, a fresh device): the old view stays until the module draws, "Loading…"
//    (.ldwait) never shows in the first 300 ms; ld_hold holds the stand-in for 300 ms, then lets it through
// 2. the agents page: before the jobs answer it never says "No running or waiting jobs" (the loading block instead); after
//    the answer it does
// 3. a project of a big account not loaded yet: the loading block, never "No tasks"; then its rows
// 4. Completed: the click shows the page at once (its loading block, not "Nothing completed yet"); the rows with the answer
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, B, login, sleep, until: until0, slow} = require('./boot');  // slow: answers held until w.__go() (#7493: shared)
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) {
  execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: `${process.env.EXTRA || ''} -e KALMIDO_STATE_LAZY_MIN=20`.trim()}});
}
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 20000) => until0(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
// every text the view showed (sampled on each change), from now on
function watchView(w) {
  const seen = []; const v = w.document.querySelector('#view');
  const mo = new w.MutationObserver(() => seen.push({t: Date.now(), txt: v.textContent || '', ldwait: [...v.querySelectorAll('.ldwait, .lempty')].some(e => /Loading…/.test(e.textContent)), eload: !!v.querySelector('.eload')}));
  mo.observe(v, {childList: true, subtree: true, characterData: true});
  return {seen, stop: () => mo.disconnect()};
}

(async () => {
  await until(async () => (await fetch(B + 'sw.js').catch(() => null))?.ok, 60000);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'contacts,agents'});
  const L = {};
  for (const n of ['Garten', 'Keller']) L[n] = (await call('POST', '/api/lists', {name: n})).id;
  for (const n of Object.keys(L)) for (let i = 1; i <= 12; i++) await call('POST', '/api/tasks', {title: `${n} Schritt ${i}`, list_id: L[n]});
  const today = new Date().toLocaleDateString('sv-SE', {timeZone: 'Europe/Berlin'});
  await call('POST', '/api/tasks', {title: 'Keller heute fegen', list_id: L.Keller, due: today});
  const done = (await call('POST', '/api/tasks', {title: 'Kiste erledigt', list_id: L.Keller, due: today})).id;
  await call('POST', `/api/tasks/${done}/complete`, {});
  check(L.Garten > 0 && done > 0 && (await call('GET', '/api/tasks?scope=done')).tasks?.some(t => t.id === done), 'setup: two projects, one completed task');

  // ================= 1. a lazy view keeps the old one, no early "Loading…"
  let w = await boot({user: 'alice', hash: 'today', lazy: true, ls: {'tasks.lzOpen': null}});
  check(await until(() => w.document.querySelector('#view .trow[data-id]')), '1: Today drawn');
  check(!w.eval("LD_RAN.has('contacts')"), '1: contacts not loaded on a fresh device');
  let vw = watchView(w); const t0 = Date.now();
  w.location.hash = '#contacts';
  check(await until(() => w.eval("LD_RAN.has('contacts')") && w.document.querySelector('#view .ctview')), '1: the contacts page comes');
  vw.stop();
  const early = vw.seen.filter(s => s.t - t0 < 300 && s.ldwait);
  check(!early.length, '1: no "Loading…" stand-in in the first 300 ms: ' + early.length);
  check(!vw.seen.some(s => s.ldwait) || vw.seen.find(s => s.ldwait).t - t0 >= 300, '1: a stand-in shows only after 300 ms');
  // the mechanism itself: the stand-in is held for 300 ms, then let through
  const hold = w.eval(`(() => { const el = document.createElement('div'); el.id = 'view'; el.innerHTML = '<p>alt</p>'; LDH.at = 0; const a = ld_hold(el, '<p class="ldwait">x</p>'); LDH.at = Date.now() - 400; const b = ld_hold(el, '<p class="ldwait">x</p>'); const c = ld_hold(el, '<p>neu</p>'); return [a, b, c, LDH.at]; })()`);
  check(hold[0] === true && hold[1] === false && hold[2] === false && hold[3] === 0, '1: ld_hold holds 300 ms, then lets the stand-in through, a real view ends it: ' + JSON.stringify(hold));
  w.close();

  // ================= 2. the agents page: no "No jobs" before the answer
  w = await boot({user: 'alice', hash: 'today'});
  check(await until(() => w.document.querySelector('#view .trow[data-id]')), '2: Today drawn');
  slow(w, /\/api\/agents\/jobs/);
  vw = watchView(w);
  w.location.hash = '#agents';
  check(await until(() => w.__held > 0 && w.document.querySelector('#view .agview')), '2: the agents page is drawn, the jobs are asked');
  await sleep(400);
  const noJobs = /No running or waiting jobs/;
  check(!noJobs.test(w.document.querySelector('#view').textContent), '2: before the answer no "No running or waiting jobs"');
  check(!!w.document.querySelector('#view .jobs .eload'), '2: the jobs box shows the loading block meanwhile');
  w.__go();
  check(await until(() => noJobs.test(w.document.querySelector('#view').textContent)), '2: after the answer the empty text');
  vw.stop();
  check(!vw.seen.some(s => noJobs.test(s.txt) && w.__held && s.eload), '2: empty text and loading block never together');
  w.close();

  // ================= 3. a project of a big account not loaded yet: loading, never "No tasks"
  w = await boot({user: 'alice', hash: 'today', ls: {'tasks.lzOpen': null}});
  check(await until(() => w.eval(`!!S.lz && S.lz.pending.has(${L.Garten})`)), '3: Garten is not loaded (start set)');
  slow(w, /\/api\/state\/lists\?/);
  vw = watchView(w);
  w.location.hash = '#l/' + L.Garten;
  check(await until(() => w.__held > 0 && w.eval("S.route.key") === 'l:' + L.Garten), '3: the project is opened, its tasks asked');
  await sleep(300);
  check(!/No tasks/.test(w.document.querySelector('#view').textContent), '3: before the answer no "No tasks"');
  check(!!w.document.querySelector('#view .eload'), '3: the loading block meanwhile');
  w.__go();
  check(await until(() => w.document.querySelectorAll('#view .trow[data-id]').length >= 12), '3: then its 12 tasks');
  vw.stop();
  check(!vw.seen.some(s => /No tasks/.test(s.txt)), '3: "No tasks" never showed on the way');
  w.close();

  // ================= 4. Completed: the click shows at once
  w = await boot({user: 'alice', hash: 'today'});
  check(await until(() => w.document.querySelector('#view .trow[data-id]')), '4: Today drawn');
  slow(w, /\/api\/tasks\?scope=done/);
  vw = watchView(w);
  w.location.hash = '#done';
  check(await until(() => w.__held > 0 && w.document.querySelector('#view .hview'), 3000), '4: the Completed page is drawn before the answer');
  check(!!w.document.querySelector('#view .hview .eload'), '4: with its loading block');
  check(!/Nothing completed yet/.test(w.document.querySelector('#view').textContent), '4: not "Nothing completed yet" before the answer');
  w.__go();
  check(await until(() => w.document.querySelector(`#view .trow[data-id="${done}"]`)), '4: then the completed task');
  vw.stop();
  check(!vw.seen.some(s => /Nothing completed yet/.test(s.txt)), '4: "Nothing completed yet" never showed on the way');
  w.close();

  console.log(`\n${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
