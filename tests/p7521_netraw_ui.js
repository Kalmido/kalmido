// kalmido-suite: fresh
// #7521 UI: the remaining plain fetch() calls of the client go through the shared time limit (core.js netRaw, #7494).
// Own container (start.sh), jsdom, invented data only.
// 1. the client code: every fetch( in static/js is netRaw / rawFetch / api() - a plain one stays only with a "#7521: stays"
//    line right above it that says why (a download with its own abort, keepalive, a presence ping, a page without core.js);
//    a new plain fetch without that line makes this red
// 2. call sites in the app with an answer that never comes (the window's fetch waits for ever): they end after the limit -
//    the quips (palette.js quipsLoad: no line), the probe of other servers (render.js msvv_probe: nothing drawn), the code
//    check (codecheck.js ckvRun: NoAnswer, status 408) - before, each waited for ever
// 3. the same calls with the server answering: they work as before
const fs = require('fs');
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');

// ================= 1. the client code (no server needed)
const JS = path.join(__dirname, '..', 'static', 'js');
const loose = [];
for (const f of fs.readdirSync(JS).filter(x => x.endsWith('.js'))) {
  const L = fs.readFileSync(path.join(JS, f), 'utf8').split('\n');
  L.forEach((l, i) => {
    if (!/(^|[^\w.$])fetch\(/.test(l) || /^\s*(\/\/|\*)/.test(l)) return;  // a comment that names fetch( is no call
    if (/^\s*(async\s+)?function\s|=>\s*\{?\s*$/.test(l) && !/fetch\(\s*[^)]/.test(l)) return;
    const pre = l.slice(0, l.search(/(^|[^\w.$])fetch\(/) + 1);
    if (/\/\/.*$/.test(pre) && !/['"`]/.test(pre.slice(pre.indexOf('//')))) return;  // after a // comment on that line
    if ((L[i - 1] || '').includes('#7521: stays') || (L[i - 2] || '').includes('#7521: stays')) return;
    loose.push(`${f}:${i + 1}`);
  });
}
check(!loose.length, '1: every fetch( of the client goes through netRaw / rawFetch / api() or says why it stays ("#7521: stays"): ' + loose.join(', '));

if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
// requests to URLs matching re never get an answer while w.__hang is set
function hang(w, re) {
  const f0 = w.fetch; w.__hang = true; w.__hung = 0;
  w.fetch = (u, o = {}) => { if (w.__hang && re.test(String(u && u.url || u))) { w.__hung++; return new Promise(() => {}); } return f0(u, o); };
}

async function run(user) {
  const tag = ` (${user})`;
  const w = await boot({user});
  check(await until(() => w.eval('typeof S !== "undefined" && S.booted')), '2: the app runs' + tag);
  w.eval('NET_T.r = 300; NET_T.w = 400');
  hang(w, /\/static\/quips\.json|\/api\/servers|\/api\/code-manifest/);
  // ---- 2. no answer: each ends after the limit
  w.eval(`QUIPS.data = null; window.__q = quipsLoad().then(x => ({x}), e => ({e: String(e)}))`);
  const t0 = Date.now();
  const q = await Promise.race([w.eval('window.__q'), sleep(5000).then(() => 'hangs')]);
  check(q !== 'hangs' && q.x == null && !q.e && Date.now() - t0 < 4000, '2: quipsLoad ends after the limit without a line ' + JSON.stringify(q) + tag);
  w.eval(`window.__p = msvv_probe().then(() => 'done', e => 'err ' + e)`);
  const p = await Promise.race([w.eval('window.__p'), sleep(5000).then(() => 'hangs')]);
  check(p === 'done', '2: the probe of other servers ends after the limit, nothing drawn ' + p + tag);
  w.eval(`window.__c = loadModule('codecheck').then(() => ckvRun()).then(() => ({ok: 1}), e => ({st: e.status, na: e instanceof NoAnswer, code: e.data?.code}))`);
  const c = await Promise.race([w.eval('window.__c'), sleep(6000).then(() => 'hangs')]);
  check(c !== 'hangs' && c.st === 408 && c.na && c.code === 'no_answer', '2: the code check hears NoAnswer (408) ' + JSON.stringify(c) + tag);
  check(w.__hung >= 3, '2: the requests were sent (and held back) ' + w.__hung + tag);
  // ---- 3. the server answers: as before
  w.__hang = false; w.eval('NET_T.r = 15000; NET_T.w = 20000');
  w.eval(`QUIPS.data = null; window.__q2 = quipsLoad().then(x => !!x, () => false)`);
  check(await w.eval('window.__q2'), '3: with an answer the quips load' + tag);
  w.close();
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en'});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  await run('alice');
  // a person without an organisation: the same core
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  await run('frida');
  console.log(`p7521_netraw_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
