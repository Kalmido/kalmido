// #6583 UI test: the upload of an account import (Settings > Data > "Import from a Kalmido export", move.js umzUpload).
// kalmido-suite: fresh
// Own container (start.sh), jsdom, invented data only (the file is zeros: the upload is what counts, the check says invalid).
// - a piece whose request fails (network) is sent again after a pause: two failures, the upload still finishes
// - a connection that stays away: after its tries the upload stops with "Continue the upload"; that goes on at the bytes the
//   server has (no new upload, no piece twice) and finishes
// - the page left during an upload: opened again, the section offers to continue; the same file chosen again goes on where
//   it stopped (only the missing pieces are sent)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 20000) => require('./boot').until(fn, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));

// the pieces go through Node's fetch (boot.js: w.File / w.Blob are Node's, so file.slice() goes as it is); net.fail = how many PUTs fail
// (after net.okFirst good ones), net.puts = the PUTs tried, net.offs = the offsets sent
function wire(w, net) {
  const f0 = w.fetch;
  w.fetch = async (u, o = {}) => {
    if (o.method === 'PUT' && /\/api\/account\/import\//.test(String(u))) {
      net.puts++;
      if (net.okFirst > 0) net.okFirst--;
      else if (net.fail > 0) { net.fail--; throw new w.TypeError('Failed to fetch'); }
      net.offs.push(+new URL(String(u), B).searchParams.get('offset'));
    }
    return f0(u, o);
  };
}
async function dataPane(w) {
  w.eval(`settingsModal('data')`);
  await until(() => w.document.querySelector('.smodal #s-umz-imp'));
  return w.document.querySelector('.smodal');
}
const cur = async () => (await call('GET', '/api/account/import')).current || {};
// the end of the upload: the check after the last piece (the zeros are no export: invalid) is over
const settled = () => until(async () => { const s = (await cur()).state; return s && s !== 'upload' && s !== 'checking'; });

(async () => {
  if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice Umzug', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const CH = (await call('GET', '/api/account/import')).chunk;
  const SIZE = 2 * CH + 1000;  // three pieces

  // ---- two failures of a piece: sent again after a pause, the upload finishes
  let w = await boot({user: 'alice'});
  let md = await dataPane(w);
  const net = {puts: 0, okFirst: 0, fail: 2, offs: []};
  wire(w, net);
  w.eval('UMZ.pause = 5');
  let file = new w.File([new w.Uint8Array(SIZE)], 'probe.kalmido-export');
  await w.eval('umzUpload')(md, file);
  await settled();
  let c = await cur();
  check(net.puts === 5 && net.offs.join() === `0,${CH},${2 * CH}` && c.state !== 'upload' && c.received === SIZE,
    `two failed requests: the piece goes again, the upload finishes ${net.puts} ${net.offs} ${c.state} ${c.received}`);

  // ---- the connection stays away: the upload stops and continues on the button
  Object.assign(net, {puts: 0, okFirst: 1, fail: 99, offs: []});
  file = new w.File([new w.Uint8Array(SIZE)], 'probe.kalmido-export');
  const id0 = (await w.eval('umzUpload')(md, file), (await cur()).id);
  const btn = md.querySelector('#s-umz-imp [data-umz="resume"]');
  check(btn && /The upload stopped at/.test(md.querySelector('#s-umz-imp').textContent) && net.puts === 6,
    `after its tries the upload stops and offers to continue ${net.puts} ${md.querySelector('#s-umz-imp').textContent.slice(0, 160)}`);
  c = await cur();
  check(c.state === 'upload' && c.received === CH && c.id === id0, `the server keeps the first piece ${c.state} ${c.received}`);
  Object.assign(net, {puts: 0, fail: 0, offs: []});
  click(w, btn);
  await settled();
  c = await cur();
  check(c.id === id0 && c.received === SIZE && net.offs.join() === `${CH},${2 * CH}`, `continued at the bytes the server has, no piece twice ${c.id === id0} ${c.received} ${net.offs}`);
  await call('DELETE', `/api/account/import/${id0}`);

  // ---- the page left during the upload: the same file again continues where it stopped
  Object.assign(net, {puts: 0, okFirst: 1, fail: 99, offs: []});
  file = new w.File([new w.Uint8Array(SIZE)], 'probe.kalmido-export');
  await w.eval('umzUpload')(md, file);
  const id1 = (await cur()).id;
  w.close();
  w = await boot({user: 'alice'});
  md = await dataPane(w);
  const box = await until(() => { const b = md.querySelector('#s-umz-imp'); return b && /Select the same file again/.test(b.textContent) ? b : null; });
  check(box && !box.querySelector('[data-umz="resume"]') && box.querySelector('[data-umz="cancel"]'), `opened again: choose the same file to continue ${box && box.textContent.slice(0, 160)}`);
  const net2 = {puts: 0, okFirst: 0, fail: 0, offs: []};
  wire(w, net2);
  const inp = md.querySelector('#s-umz-file');
  file = new w.File([new w.Uint8Array(SIZE)], 'probe.kalmido-export');
  Object.defineProperty(inp, 'files', {value: [file], configurable: true});
  inp.dispatchEvent(new w.Event('change', {bubbles: true}));
  await settled();
  c = await cur();
  check(c.id === id1 && c.received === SIZE && net2.offs.join() === `${CH},${2 * CH}`, `the same file goes on where it stopped ${c.id === id1} ${c.received} ${net2.offs}`);
  w.close();

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
