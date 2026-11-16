// 2.1284.0 (#6606) UI test: the installer leaves the virus scanner out under about 3 GB of memory and leaves the trace
// KALMIDO_CLAMAV_OFF=low_memory in .env; Settings > Server > Backup says so (scanner off, the reason) and how to switch it on.
// kalmido-suite:
// own container (start.sh with KALMIDO_CLAMD empty and the trace), jsdom. Invented data only. P6606B_NOSTART=1 = the container runs.
// freelancer-matrix: settings (sam is a server admin without an organisation)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6606B_NOSTART) {
  execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: '-e KALMIDO_CLAMD= -e KALMIDO_CLAMAV_OFF=low_memory'}});
}
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = async (fn, n = 80) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };

async function scannerLine(user) {
  const w = await boot({user}), d = w.document;
  w.eval(`settingsModal('backup')`);
  const md = await until(() => d.querySelector('.smodal'));
  const bp = md && md.querySelector('#admp-backup');
  const box = await until(() => bp && bp.querySelector('#s-scn .shint'));
  const out = {open: !!(bp && !bp.hidden), text: box ? box.textContent : '', note: !!(box && box.classList.contains('cnote'))};
  w.close();
  return out;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments', 'docs']});
  await call('POST', '/api/users', {username: 'sam', display_name: 'Sam', password: 'password123', email: 'sam@example.com', is_admin: true});  // no organisation
  for (const u of ['alice', 'sam']) await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, await login(u));

  const st = await call('GET', '/api/admin/upload-scan');
  check(st.state === 'off' && st.off_why === 'low_memory', '#6606: the server names the installer\'s reason ' + JSON.stringify(st));

  for (const u of ['alice', 'sam']) {
    const s = await scannerLine(u);
    check(s.open, `#6606 ${u}: Settings > Server > Backup opens`);
    check(/Virus scanner: off/.test(s.text) && /less than about 3 GB of memory/.test(s.text) && /not checked for malware/.test(s.text),
      `#6606 ${u}: the line says off, why (little memory) and what it means: ${s.text}`);
    check(/Switch it on: in the installation folder run KALMIDO_CLAMAV=1 \.\/update\.sh/.test(s.text) && /COMPOSE_PROFILES/.test(s.text),
      `#6606 ${u}: ... and how to switch it on (installer and own setup): ${s.text}`);
    check(s.note, `#6606 ${u}: the line stands out (cnote), it is not a routine state`);
  }

  console.log(`p6606_b_scanner_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log("FAIL: crashed", e); process.exit(1); });
