// kalmido-suite: fresh
// 2.1188.0 B UI test (#6152), jsdom, own container (start.sh). freelancer-matrix: files (frida has no organisation, her own office)
// - Settings > Integrations > Receipt fetcher: a section "Download the helper" with a link to the zip for Mac and Windows
//   (its version in the text) and the three steps (unpack, double-click Einrichten.command / .cmd, paste the setup code)
// - the link's file loads (200, a zip); the setup code below still works (the section does not push it away)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21188B_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = async (fn, n = 40) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const DESK = {'(hover:hover) and (pointer:fine)': true};

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'files,docs,comments,collab,office'}, CF);
  check(((await call('GET', '/api/state', null, CF)).me.workspaces || []).length === 0, 'frida has no organisation');

  const w = await boot({user: 'frida', media: DESK}), d = w.document;
  await until(() => w.eval('S.booted && typeof dsc_integrDraw === "function" && typeof fx_draw === "function"'), 60);
  w.eval(`settingsModal('integr')`);
  const box = await until(() => d.querySelector('#s-fetch .fx-dl'));
  check(!!box && /Download the helper/.test(box.textContent), 'Receipt fetcher: the section "Download the helper"');
  const a = /** @type {any} */ (box?.querySelector('a#fx-dl'));
  const href = a?.getAttribute('href') || '';
  check(/^\/static\/downloads\/kalmido-belegabholer-\d+(\.\d+)*\.zip$/.test(href) && a.hasAttribute('download'), 'the link points at the zip and downloads it: ' + href);
  const ver = (href.match(/-(\d+(?:\.\d+)*)\.zip$/) || [])[1] || '?';
  check(a && a.textContent.includes(ver) && /Mac/.test(a.textContent) && /Windows/.test(a.textContent), 'the link names the version, Mac and Windows: ' + (a?.textContent || '').trim());
  const steps = [...(box?.querySelectorAll('ol li') || [])].map(li => li.textContent.trim());
  check(steps.length === 3 && /Unpack/.test(steps[0]) && /Einrichten\.command/.test(steps[1]) && /Einrichten\.cmd/.test(steps[1]) && /setup code/.test(steps[2]),
    'three steps: unpack, double-click, paste the setup code ' + JSON.stringify(steps));
  const r = await fetch(B + href.replace(/^\//, ''));
  const buf = Buffer.from(await r.arrayBuffer());
  check(r.status === 200 && buf.subarray(0, 4).toString('binary') === 'PK\x03\x04', `the file loads as a zip (${r.status}, ${buf.length} bytes)`);
  // the way on: connecting still works below the download
  click(w, d.querySelector('#s-fetch [data-fx="new"]'));
  const codeEl = await until(() => d.querySelector('#fx-code'));
  check(!!codeEl && /** @type {any} */ (codeEl).value.startsWith('kalmido-fetch:1:'), 'below it the setup code is made as before');
  check(!!d.querySelector('#s-fetch .fx-dl a#fx-dl'), 'the download stays after the code is shown');
  w.close();

  console.log(`p21188_b_fetcherdl_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
