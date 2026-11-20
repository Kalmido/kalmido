// 2.619.0 UI test, part D (#3890): reload waves. jsdom, own container (start.sh):
// kalmido-suite: fresh
// - a window that just started takes the areas of its state (lva) as those of its first poll: a change right after the start
//   comes as a delta, not as a second whole state (was: every window loaded its whole state once, all at the same time
//   during writes elsewhere)
// - an update of the server: the reload by itself waits a random part of VER_SPREAD_MS (the windows do not all reload in the
//   same poll); the bar shows meanwhile; once the wait is over it reloads
// - (#6338): a running upload holds the reload by itself back and closing the tab asks; an outdated window loads no
//   module of the new version (a click reloads first, a background load does nothing)
// Every wait is on a real state (the app's own change poll, held where a step needs it).
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const until = fn => until0(fn, {timeout: 20000, step: 100});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Garden plan'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Order the seeds', list_id: L})).id;
  check(L && T, 'a list with a task');
  const w = await boot({user: 'alice', hash: 'l/' + L}), d = w.document;
  check(await until(() => d.querySelector(`#view .trow[data-id="${T}"]`)), 'the list shows');
  const caught = () => until(async () => !!w.eval('!!S.lpA && !td_polling') && (await call(CA, 'GET', '/api/version')).v === w.eval('S.v'));
  check(await caught(), 'the page is settled');

  // ================= the first poll after a start
  // held poll; the window as right after its start: no poll areas yet, then its start load
  check(await until(() => w.eval('td_polling ? false : (td_polling = true)')), 'the poll held');
  w.eval('S.lpA = null; S.lpUnk = false; S.lpPend.clear(); window.__ld = 0; load().then(() => { window.__ld = 1; })');
  check(await until(() => w.__ld === 1), 'the start load is done');
  const sv = await call(CA, 'GET', '/api/version');
  check(w.eval('!!S.lpA') && JSON.stringify(w.eval('S.lpA')) === JSON.stringify(sv.a), `#3890: the state brought the areas (lva) ${JSON.stringify(w.eval('S.lpA'))} vs ${JSON.stringify(sv.a)}`);
  const st0 = w.eval('S.lpN.state'), dl0 = w.eval('S.lpN.delta');
  // a write elsewhere before the first poll (another device of alice)
  const T2 = (await call(CA, 'POST', '/api/tasks', {title: 'Build the raised bed', list_id: L})).id;
  check(T2, 'a task from another device');
  w.eval('td_polling = false');
  check(await until(() => d.querySelector(`#view .trow[data-id="${T2}"]`)), '#3890: the new task shows');
  check(w.eval('S.lpN.state') === st0 && w.eval('S.lpN.delta') > dl0,
    `#3890: the first poll took a delta, not the whole state again ${JSON.stringify(w.eval('S.lpN'))} (state was ${st0}, delta ${dl0})`);

  // ================= an update of the server: the reload by itself spread (#6364: by itself only in a window not seen - verAway)
  check(await until(() => w.eval('td_polling ? false : (td_polling = true)')), 'the poll held again');
  const appVer = d.querySelector('meta[name="kalmido-version"]')?.content;
  w.eval(`window.__realVR = verReload; verReload = () => { window.__rl = (window.__rl || 0) + 1; }; VER_SPREAD_MS = 600000; document.activeElement?.blur?.(); verIdle = Date.now() - 60000; window.__realAway = verAway; verAway = () => true; sessionStorage.removeItem('kalmido-reloaded'); window.__rl = 0`);
  // quiet: no field, dialog, popover, draft or waiting change (verQuiet holds the reload back otherwise)
  w.eval(`[...document.querySelectorAll('.modal')].forEach(m => m.remove()); const q = document.querySelector('#qinput'); if (q) q.value = ''`);
  const why = () => JSON.stringify(w.eval(`({quiet: verQuiet(), editing: editing(), focused: editFocused(), modal: !!$('.modal'), pop: !!$('#pop:not(.hidden)'), sheet: !!$('.qadd.sheet'), q: OUT.q.length, multi: !!S.multiMode, draft: verDraft(), seen: S.verSeen})`));
  check(await until(() => w.eval('verQuiet()')), `the window is quiet ${why()}`);
  w.eval(`verCheck('99.1.0'); verCheck('99.1.0'); verCheck('99.1.0')`);
  check(!w.__rl && d.querySelector('#newver'), `#3890: quiet, the new version reported three times: no reload yet, the bar shows (reloads ${w.__rl})`);
  check(w.eval('S.verSpread?.v === "99.1.0" && S.verSpread.at > Date.now()'), `#3890: the window waits its own random time ${why()}`);
  w.eval('if (S.verSpread) S.verSpread.at = Date.now() - 1; verCheck("99.1.0")');
  check(w.__rl === 1, `#3890: once its time has come it reloads by itself (${w.__rl})`);
  w.eval(`S.serverVer = '${appVer}'; verCheck('${appVer}')`);

  // ================= 2.1337.0 (#6892): a click on "Reload" while the reload by itself waits for the server
  // the real verReload runs; the wait for the server is held (rl_waitServer), the window is NOT calm (a draft) - the click must
  // still reload (the mark kalmido-reloaded is set right before location.reload()), and the button is never left disabled
  w.eval(`verReload = window.__realVR; window.__realWait = rl_waitServer; window.__gate = null; rl_waitServer = () => new Promise(r => { window.__gate = r; });
    S.serverVer = '99.2.0'; sessionStorage.removeItem('kalmido-reloaded'); verBusy = false; verWant = false; verCheck('99.2.0'); verReload(true)`);
  check(await until(() => w.eval('verBusy && !!window.__gate')), '#6892: the automatic run waits for the server');
  const nv = () => d.querySelector('#newver [data-nv="go"]');
  check(!!nv() && !nv().disabled, '#6892: the button is usable while it waits');
  const word = nv().textContent;
  nv().click();
  check(nv().disabled && nv().textContent !== word, `#6892: the click shows the wait ("${nv().textContent}") instead of just greying out`);
  w.eval(`const i = document.createElement('input'); i.type = 'text'; i.id = 'nv-draft'; document.body.appendChild(i); i.value = 'typed'`);
  check(w.eval('!verCalm()'), '#6892: the window is not calm (a draft stands)');
  w.eval('window.__gate(true)');
  check(await until(() => !w.eval('verBusy')), '#6892: the run is over');
  check(w.eval(`sessionStorage.getItem('kalmido-reloaded')`) === '99.2.0', '#6892: the click reloaded although the window was not calm');
  // an automatic run that gives up (not calm, no click) frees nothing wrongly and a click after a failed wait frees the button
  w.eval(`sessionStorage.removeItem('kalmido-reloaded'); window.__gate = null; verCheck('99.2.0'); verReload(true)`);
  check(await until(() => w.eval('verBusy && !!window.__gate')), '#6892: second automatic run waits');
  w.eval('window.__gate(true)');
  check(await until(() => !w.eval('verBusy')), '#6892: second run over');
  check(!w.eval(`sessionStorage.getItem('kalmido-reloaded')`), '#6892: without a click the automatic run still gives up when not calm');
  check(!nv()?.disabled, '#6892: the button is free again after the automatic run gave up');
  w.eval(`window.__gate = null; verReload(true)`);
  check(await until(() => w.eval('verBusy && !!window.__gate')), '#6892: third run waits');
  nv().click();
  w.eval('window.__gate(false)');
  check(await until(() => !w.eval('verBusy')), '#6892: third run over (server not reachable)');
  check(!nv().disabled && nv().textContent === word, '#6892: the button is free again after a failed wait');
  w.eval(`document.querySelector('#nv-draft')?.remove(); rl_waitServer = window.__realWait; S.serverVer = '${appVer}'; verCheck('${appVer}'); td_polling = false`);

  // ================= (#6338): a running upload holds the reload by itself back and closing the tab asks; once it is done
  // the reload comes. An outdated window loads no module of the new version: a click reloads first, the background nothing
  check(await until(() => w.eval('td_polling ? false : (td_polling = true)')), '#6338: the poll held');
  w.eval(`window.__rl = 0; window.__rla = []; window.__realVR2 = verReload; verReload = a => { window.__rl++; window.__rla.push(a); }; VER_SPREAD_MS = 0;
    verIdle = Date.now() - 60000; sessionStorage.removeItem('kalmido-reloaded'); document.activeElement?.blur?.(); 1`);
  check(await until(() => w.eval('verQuiet()')), '#6338 setup: the window is quiet');
  // an upload whose answer is held (a form with a file through rawFetch, as every upload of the app)
  w.eval(`window.__f0 = window.fetch; window.__upGate = null;
    window.fetch = (u, o) => o && o.body instanceof FormData ? new Promise(r => { window.__upGate = () => r(window.__f0('/api/version', {headers: {'X-Requested-With': 'kalmido'}})); }) : window.__f0(u, o);
    const fd = new FormData(); fd.append('file', new Blob(['sunflower, marigold']), 'seed list.txt'); window.__up = rawFetch('POST', '/api/files/upload', fd).catch(() => 0); 1`);
  check(await until(() => w.eval('!!window.__upGate')), '#6338: the upload is on its way');
  check(w.eval('upAny()') === true && w.eval('verQuiet()') === false, '#6338: a running upload makes the window not quiet (verQuiet)');
  const bu = () => w.eval(`(() => { const e = new Event('beforeunload', {cancelable: true}); window.dispatchEvent(e); return e.defaultPrevented; })()`);
  check(bu() === true, '#6338: closing / reloading the tab asks while the upload runs');
  w.eval(`S.serverVer = '99.3.0'; S.verSeen = {v: '', n: 0}; verCheck('99.3.0'); verCheck('99.3.0'); 1`);
  check(w.eval('window.__rl') === 0 && !!d.querySelector('#newver'), '#6338: a new version does not reload by itself during the upload, the bar shows');
  w.eval('window.__upGate()');
  check(await until(() => !w.eval('upAny()')), '#6338: the upload is done');
  check(bu() === false, '#6338: closing asks no more');
  w.eval(`verIdle = Date.now() - 60000; verCheck('99.3.0'); 1`);
  check(await until(() => w.eval('window.__rl') === 1), '#6338: after the upload the reload by itself comes');
  // D3: the window is outdated (S.serverVer 99.3.0); a module that has not run here
  w.eval(`LD_MODS.t6338 = ['t6338none']; window.__rl = 0; window.__rla = []; 1`);
  const bg = await w.eval(`(verIdle = Date.now() - 60000, loadModule('t6338').then(() => 'loaded', e => e.stale ? 'stale' : 'err:' + e.message))`);
  check(bg === 'stale' && w.eval('window.__rl') === 0 && !d.querySelector('script[data-ld="t6338none"]'), `#6338 D3: asked in the background, nothing is loaded and nothing reloads (${bg})`);
  const fg = await w.eval(`(verIdle = Date.now(), loadModule('t6338').then(() => 'loaded', e => e.stale ? 'stale' : 'err:' + e.message))`);
  check(fg === 'stale' && w.eval('window.__rl') === 1 && w.eval('window.__rla[0]') === undefined && !d.querySelector('script[data-ld="t6338none"]'),
    `#6338 D3: after a click the window reloads first (with the checks of the reload: quiet), the module of the new version is not loaded (${fg}, ${w.eval('window.__rl')})`);
  w.eval(`window.fetch = window.__f0; verReload = window.__realVR2; verAway = window.__realAway; delete LD_MODS.t6338; S.serverVer = '${appVer}'; verCheck('${appVer}'); td_polling = false`);
  w.close();

  console.log(`p2619_d_reload_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
