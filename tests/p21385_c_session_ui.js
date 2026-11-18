// kalmido-suite: fresh
// 2.1385.0 UI test (#6503 points 7 and 8), own container (start.sh; KMT_NOSTART=1: a running server), jsdom. Invented names only.
// - point 7: the mail's link "Cancel the deletion" (#delete-cancel=<token>) opened while another account is signed in: the token
//   leaves the address bar at once, the app says to sign out first, the token waits in the tab; a visitor without a session
//   gets the cancel page and the token leaves the address bar too
// - point 8: Settings > Account > Active sessions says that app passwords, API tokens, agents and calendar subscription links
//   are no sessions and keep working; "Sign out everywhere else" says the same before it signs out
// usage: node p21385_c_session_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const wait = fn => until(fn, {timeout: 15000, step: 150});
const TOK = 'dc1234567890abcdef.XYZ_test-token';

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true}, CK);
  await call('PATCH', '/api/settings', {tour: 'done', lang: 'en'}, CK);

  // ================= point 7: the link opened while another account is signed in
  let w = await boot({user: 'alice', hash: 'delete-cancel=' + TOK}), d = w.document;
  check(await wait(() => w.eval('!!(S.me && S.booted)')), '7: the app starts for the signed-in account');
  check(!/delete-cancel/.test(w.location.href), '7: the token left the address bar ' + w.location.href);
  check(w.sessionStorage.getItem('kalmido.delcancel') === TOK, '7: it waits in this tab for the sign-in page');
  check(await wait(() => /This link cancels the deletion of an account\. Sign out here first/.test(d.querySelector('#toast')?.textContent || '')),
    '7: the app says to sign out first ' + (d.querySelector('#toast')?.textContent || ''));
  w.close();

  // ---- a visitor without a session: the cancel page, the token out of the address bar
  w = await boot({user: null, hash: 'delete-cancel=' + TOK}); d = w.document;
  check(await wait(() => d.querySelector('[data-dc="go"]')), '7: a visitor gets the page "Cancel the deletion"');
  check(!/delete-cancel/.test(w.location.href), '7: ... and the token left the address bar there too ' + w.location.href);
  check(!w.sessionStorage.getItem('kalmido.delcancel'), '7: the page took it (nothing waits any more)');
  w.close();

  // ================= point 8: the sessions view says what goes on
  await login('alice');  // a second session of alice: "Sign out everywhere else" appears
  const asked = [];
  w = await boot({user: 'alice', hash: 'today', setup: x => { x.confirm = t => { asked.push(String(t)); return false; }; }}); d = w.document;
  check(await wait(() => w.eval('!!(S.me && S.booted)')), '8: the app starts');
  w.eval("settingsModal('account')");
  const hint = await wait(() => [...d.querySelectorAll('#s-ses ~ .shint, #s-ses .shint')].map(x => x.textContent).join(' ').match(/are no sessions: they keep working/) && d.querySelector('#s-ses'));
  check(hint, '8: the sessions view says that app passwords, API tokens, agents and calendar links keep working ' + (d.querySelector('#s-ses')?.textContent || '').slice(0, 300));
  const btn = await wait(() => d.querySelector('[data-ses="others"]'));
  check(btn, '8: "Sign out everywhere else" is there');
  btn?.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
  check(await wait(() => asked.length), '8: it asks first');
  check(/This device stays signed in\. App passwords, API tokens, agents and calendar subscription links are no sessions: they keep working\. End them under Settings > Account, Access and Integrations\./.test(asked.join(' ')),
    '8: the question says what goes on and where it ends ' + asked.join(' | '));
  w.close();

  console.log(`p21385_c_session_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
