// 2.1180.0 UI test, part B (#6131 frame: loading, error and offline texts from the shared blocks), jsdom
// kalmido-suite: fresh
// own container (start.sh), invented names only. P21180B_NOSTART=1 = the container runs.
// freelancer-matrix: n/a (no new route; alice has no organisation, every check runs without one)
// - errText: a browser's refusal (DOMException NotAllowedError / InvalidStateError / NotSupportedError) is a plain sentence, never
//   the browser's English text; offline is the ONE sentence "Only available online."
// - Settings (calendar link, organisations): a failed load says so with "Try again", and that loads it (no raw text, no dead end)
// - the files of the frame no longer carry the other offline sentences
const {execFileSync} = require('child_process');
const fs = require('fs');
const path = require('path');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21180B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const until = fn => until0(fn, {timeout: 15000, step: 100});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const wrap = w => {
  const f1 = w.fetch;
  w.__fail = null;
  w.fetch = (u, o = {}) => {
    const k = `${o.method || 'GET'} ${u}`;
    if (w.__fail && w.__fail.test(k)) return Promise.resolve(new Response(JSON.stringify({error: 'Refused for the test'}), {status: 500, headers: {'content-type': 'application/json'}}));
    return f1(u, o);
  };
};

(async () => {
  await sleep(600);
  check(await until(async () => (await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})}).catch(() => null))?.status < 500), 'setup');
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const w = await boot({user: 'alice', hash: ''}), d = w.document;
  await until(() => w.eval(`typeof errText === 'function' && typeof icalDraw === 'function' && typeof wsPaneDraw === 'function'`));
  wrap(w);

  // ================= errText: the browser's own refusals and offline
  const et = (name, msg) => w.eval(`errText(new DOMException(${JSON.stringify(msg)}, ${JSON.stringify(name)}))`);
  const na = et('NotAllowedError', 'The request is not allowed by the user agent or the platform in the current context.');
  check(/^Your browser or device did not allow this/.test(na) && !/user agent/.test(na), 'NotAllowedError in plain words: ' + na);
  check(et('InvalidStateError', 'The object is in an invalid state.') === 'This is already set up on this device.', 'InvalidStateError');
  check(et('NotSupportedError', 'Push is not supported') === 'Your browser does not support this.', 'NotSupportedError');
  check(et('AbortError', 'The operation was aborted.') === 'Cancelled.', 'AbortError');
  check(w.eval(`errText('offline')`) === 'Only available online.' && w.eval(`errText(new Offline())`) === 'Only available online.', 'offline: the one sentence');
  check(w.eval(`errText(new DOMException('x', 'NotAllowedError'), 'Could not switch on notifications')`).startsWith('Could not switch on notifications ('), 'with a what: sentence first');
  check(w.eval(`errText(Object.assign(new Error('Server says no'), {status: 400}))`) === 'Server says no', 'a server answer keeps its text');

  // ================= Settings: a failed load = "Try again", and that loads
  w.eval(`(() => { const x = document.createElement('div'); x.id = 'p21180-ical'; x.innerHTML = '<div id="s-ical"></div>'; document.body.appendChild(x); window.__ix = x; icalDraw(x); })()`);
  const ib = () => d.querySelector('#p21180-ical #s-ical');
  await until(() => txt(ib()).length > 0);
  w.eval(`(() => { document.querySelector('#s-ical').innerHTML = ''; })()`);
  w.__fail = /^GET \/api\/ical/;
  w.eval(`icalDraw(window.__ix)`);
  const ie = await until(() => ib()?.querySelector('.eerr'));
  check(ie && ie.querySelector('[data-esretry]') && /Could not be loaded/.test(txt(ie)), 'calendar link: failed load with "Try again": ' + txt(ib()));
  check(!/Loading…/.test(txt(ib())) && !/Offline: only works again/.test(txt(ib())), 'no stuck "Loading…" / old offline sentence');
  w.__fail = null;
  click(w, ie.querySelector('[data-esretry]'));
  check(await until(() => !ib().querySelector('.eerr') && txt(ib()).length > 0), 'calendar link: "Try again" loads it: ' + txt(ib()));

  w.eval(`(() => { const x = document.createElement('div'); x.id = 'p21180-ws'; x.innerHTML = '<div id="s-ws"></div>'; document.body.appendChild(x); window.__wx = x; })()`);
  w.__fail = /^GET \/api\/orgs/;
  w.eval(`wsPaneDraw(window.__wx)`);
  const we = await until(() => d.querySelector('#p21180-ws .eerr'));
  check(we && we.querySelector('[data-esretry]'), 'organisations: failed load with "Try again"');
  w.__fail = null;
  click(w, we.querySelector('[data-esretry]'));
  check(await until(() => !d.querySelector('#p21180-ws .eerr')), 'organisations: "Try again" loads');

  // ================= the files of the frame: no second offline sentence any more
  const root = path.join(__dirname, '..', 'static', 'js');
  for (const f of ['settings', 'account', 'acctset', 'setreset', 'areas', 'dashboard', 'taskbell', 'collab', 'core', 'render']) {
    const s = fs.readFileSync(path.join(root, f + '.js'), 'utf8');
    check(!/Offline: only works again with a connection|News are only available online|tr\('You are offline'\)/.test(s), f + '.js: one offline sentence');
  }

  w.close();
  console.log(`p21180_b_errors_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
