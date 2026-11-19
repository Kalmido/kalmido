// 2.1247.0 part A UI test (#6173): uploading into the file store / the documents - Undo of a new version with expect_version,
// kalmido-suite: fresh
// no second message beside the list of what stayed out, each upload its own list.
// Own container (start.sh; P21247A_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom only. Invented names and files only.
// freelancer-matrix: files of a person without an organisation (frida: her private space)
// #6173 1 - an upload that gave a file a new version, then someone else uploads a newer one: Undo leaves the file as it is
//           (expect_version -> 409) and says so; without the check Undo put the version before back over the other's one.
//           Undo -> Redo -> Undo of an own upload still works (each step knows the version it made).
// #6173 2 - a portion the server refuses (400) and an upload of documents while offline: the reason stands in the list only,
//           api()'s toast no longer says it a second time.
// #6173 3 - two uploads one after the other, both with files that stayed out: two lists (the second no longer removes the first).
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21247A_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEATS = 'files,docs';
// every text the toast showed (the check "no second message" needs the ones that were replaced)
const watchToasts = w => w.eval(`(() => { window.__toasts = []; const t = document.querySelector('#toast'); new MutationObserver(() => { if (!t.classList.contains('hidden')) window.__toasts.push(t.textContent); }).observe(t, {childList: true, subtree: true, characterData: true, attributes: true}); return 1; })()`);
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(','), ...FEATS.split(',')])].filter(Boolean).join(',');
  const u = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http < 300, `setup: frida ${u.http}`);
  const FK = await login('frida');
  await call(FK, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  check(((await call(FK, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida has no organisation');
  const items = async (ck, q) => (await call(ck, 'GET', '/api/files?' + q)).items || [];
  const content = async (ck, id) => (await fetch(B + `api/files/nodes/${id}/content`, {headers: {'X-Requested-With': 'kalmido', Cookie: ck}})).text();
  // an upload from "somewhere else" (another device of hers): straight to the server, the window does not know of it
  const upElsewhere = async (name, text) => {
    const fd = new FormData(); fd.append('file', new Blob([text]), name); fd.append('space', 'private');
    return (await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: FK}, body: fd})).status;
  };
  let w = await boot({user: 'frida', hash: 'ablage', ls: {'tasks.abSpace': '"private"'}}), d = w.document;
  check(await until(() => d.querySelector('#view .abview')), 'frida: her private space is drawn');
  watchToasts(w);

  // ================= #6173 1: Undo of a new version only while it is still the newest
  await w.eval(`ab_upload([new File(['Skript Fassung 1'], 'skript.txt', {type: 'text/plain'})], null)`);
  const SK = await until(async () => (await items(FK, 'space=private')).find(x => x.name === 'skript.txt')?.id);
  check(SK, 'skript.txt uploaded');
  await w.eval(`ab_upload([new File(['Skript Fassung 2'], 'skript.txt', {type: 'text/plain'})], null)`);
  check(await until(() => /1 uploaded, 1 as a new version/.test(txt(d.querySelector('#toast'))) && /Undo/.test(d.querySelector('#toast button')?.textContent || '')), 'a new version: its message with Undo ' + txt(d.querySelector('#toast')));
  check(await upElsewhere('skript.txt', 'Skript Fassung 3 von woanders') < 300, 'meanwhile a newer version from elsewhere');
  d.querySelector('#toast button').click();
  check(await until(() => /Meanwhile someone else uploaded a newer version, it stays as it is: skript\.txt/.test(txt(d.querySelector('#toast')))), 'Undo says that someone else uploaded a newer version: ' + txt(d.querySelector('#toast')));
  check(await content(FK, SK) === 'Skript Fassung 3 von woanders', 'Undo left the newer version on top (nothing put back over it)');
  const vers = (await call(FK, 'GET', `/api/files/nodes/${SK}`)).versions || [];
  check(vers.length === 3, 'no restore was stored (still 3 versions): ' + vers.length);

  // Undo -> Redo -> Undo of an own new version: each step sends the version the step before made
  w.__toasts.length = 0;
  await w.eval(`ab_upload([new File(['Plan A'], 'plan.txt', {type: 'text/plain'})], null)`);
  const PL = await until(async () => (await items(FK, 'space=private')).find(x => x.name === 'plan.txt')?.id);
  await w.eval(`ab_upload([new File(['Plan B'], 'plan.txt', {type: 'text/plain'})], null)`);
  check(await until(() => /1 as a new version/.test(txt(d.querySelector('#toast')))), 'plan.txt: a new version');
  await w.eval('histStep("undo")');
  check(await until(async () => await content(FK, PL) === 'Plan A'), 'Undo: Plan A on top again');
  await w.eval('histStep("redo")');
  check(await until(async () => await content(FK, PL) === 'Plan B'), 'Redo: Plan B on top again');
  await w.eval('histStep("undo")');
  check(await until(async () => await content(FK, PL) === 'Plan A'), 'Undo once more: Plan A (the step knew the version Redo made)');
  check(!w.__toasts.some(t => /Meanwhile someone else/.test(t)), 'no "someone else" message for her own steps');

  // Fable review M1: a 409 that is no version conflict (a locked month, a folder that switches; no "current") is said as it is,
  // not as "someone else uploaded"; 2.1412.0 (#6227 N1): the step stays in the history (was: counted as done)
  w.eval(`(() => { const f0 = window.fetch; window.__f1 = f0; window.fetch = (u, o) => /versions\\/\\d+\\/restore/.test(String(u)) ? Promise.resolve(new Response(JSON.stringify({error: 'Folder is switching right now'}), {status: 409, headers: {'Content-Type': 'application/json'}})) : f0(u, o); return 1; })()`);
  w.__toasts.length = 0;
  await w.eval('histStep("redo")');
  check(await until(() => w.__toasts.some(t => /Folder is switching right now/.test(t))), 'M1: another 409 says its own reason: ' + JSON.stringify(w.__toasts));
  check(!w.__toasts.some(t => /Meanwhile someone else/.test(t)), 'M1: no "someone else" message for a 409 without current');
  w.eval('window.fetch = window.__f1');
  check(await content(FK, PL) === 'Plan A', 'M1: nothing changed while refused');
  // 2.1412.0 (#6227 N1): the refused step is still there to redo; once the folder lets it, Redo goes
  check(w.eval(`HIST.redo.some(e => e.label === 'Upload')`), 'N1: the refused Redo stays in the history');
  await w.eval('histStep("redo")');
  check(await until(async () => await content(FK, PL) === 'Plan B'), 'N1: Redo again once the server lets it: Plan B');

  // 2.1412.0 (#6227 N2): two files of the same name in one upload, another version in between (two portions: a tiny size limit
  // makes each file its own request; between them a version from elsewhere) - Undo leaves the file and names it like a conflict
  const mb0 = w.eval('S.maxFileMb');
  w.eval('S.maxFileMb = 0.00002');
  w.eval(`(() => { const r0 = window.rawFetch; window.__r0 = r0; let n = 0; window.rawFetch = async (m, u, b) => { const r = await r0(m, u, b); if (/files\\/upload/.test(String(u)) && ++n === 1) { const fd = new FormData(); fd.append('file', new Blob(['Luecke fremd']), 'luecke.txt'); fd.append('space', 'private'); await r0('POST', '/api/files/upload', fd); } return r; }; return 1; })()`);
  w.__toasts.length = 0;
  await w.eval(`ab_upload([new File(['Luecke 1'], 'luecke.txt', {type: 'text/plain'}), new File(['Luecke 2'], 'luecke.txt', {type: 'text/plain'})], null)`);
  w.eval('window.rawFetch = window.__r0');
  const LU = await until(async () => (await items(FK, 'space=private')).find(x => x.name === 'luecke.txt')?.id);
  check(LU && ((await call(FK, 'GET', `/api/files/nodes/${LU}`)).versions || []).length === 3, 'N2: three versions (own, from elsewhere, own)');
  await w.eval('histStep("undo")');
  check(await until(() => w.__toasts.some(t => /Meanwhile someone else uploaded a newer version, it stays as it is: luecke\.txt/.test(t))), 'N2: Undo names the file like a conflict: ' + JSON.stringify(w.__toasts));
  check(await content(FK, LU) === 'Luecke 2' && (await items(FK, 'space=private')).some(x => x.id === LU), 'N2: the file stays as it is (not back over the other version, not in the trash)');

  // 2.1412.0 (#6227 N3): the session ends in the middle of an upload: the rest "Signed out" in the list, the end as usual
  w.eval(`(() => { const r0 = window.__r0; let n = 0; window.rawFetch = (m, u, b) => /files\\/upload/.test(String(u)) && ++n === 2 ? Promise.reject(new Error('auth')) : r0(m, u, b); return 1; })()`);
  w.eval('S.maxFileMb = 0.00002');  // again: a reload of the state in between brings the server's limit back
  await w.eval(`ab_upload([new File(['Teil 1'], 'abm-1.txt', {type: 'text/plain'}), new File(['Teil 2'], 'abm-2.txt', {type: 'text/plain'})], null)`);
  w.eval('window.rawFetch = window.__r0');
  w.eval(`S.maxFileMb = ${JSON.stringify(mb0)}`);
  const out3 = await until(() => [...d.querySelectorAll('#upbars .upout')].find(x => /abm-2\.txt/.test(txt(x))));
  check(out3 && /Signed out/.test(txt(out3)) && !/abm-1\.txt/.test(txt(out3)), 'N3: the rest in the list with "Signed out": ' + txt(out3));
  check(await until(() => /1 file uploaded · 1 not uploaded/.test(txt(d.querySelector('#toast')))), 'N3: the message with the uploaded file as usual: ' + txt(d.querySelector('#toast')));
  check(w.eval(`HIST.undo.at(-1)?.label === 'Upload'`), 'N3: the upload is a step in the history');
  check((await items(FK, 'space=private')).some(x => x.name === 'abm-1.txt'), 'N3: the first file is on the server');
  out3?.querySelector('.upoutx')?.click();

  // ================= #6173 2: a refused portion stands in the list only, not in a toast as well
  // the server's own 400: the portion's form goes up with an empty file in it (the server refuses the whole form)
  w.eval(`(() => { const f0 = window.fetch; window.__f0 = f0; window.fetch = (u, o) => { if (o?.body instanceof FormData && /files\\/upload/.test(String(u))) { const fd = new FormData(); fd.append('file', new File(['x'], 'a.txt')); fd.append('file', new File([], 'b.mp4')); fd.append('space', 'private'); return f0(u, {...o, body: fd}); } return f0(u, o); }; return 1; })()`);
  w.__toasts.length = 0;
  await w.eval(`ab_upload([new File(['Abgelehnt'], 'abgelehnt.txt', {type: 'text/plain'})], null)`);
  w.eval('window.fetch = window.__f0');
  const out1 = await until(() => [...d.querySelectorAll('#upbars .upout')].find(x => /abgelehnt\.txt/.test(txt(x))));
  const why = txt(out1?.querySelector('li .muted'));
  check(out1 && why, 'the refused file is in the list with the reason: ' + txt(out1));
  await sleep(0);
  check(why && !w.__toasts.some(t => t.includes(why)), 'the reason is said once (no toast of api() beside the list): ' + JSON.stringify(w.__toasts));
  out1?.querySelector('.upoutx')?.click();

  // ================= #6173 3: each upload its own list
  await w.eval(`ab_upload([new File([], 'leer-eins.mp4', {type: 'video/mp4'})], null)`);
  await w.eval(`ab_upload([new File([], 'leer-zwei.wav', {type: 'audio/wav'})], null)`);
  const lists = [...d.querySelectorAll('#upbars .upout')].map(txt);
  check(lists.length === 2 && lists.some(t => /leer-eins\.mp4/.test(t)) && lists.some(t => /leer-zwei\.wav/.test(t)), 'two uploads, two lists (the second keeps the first): ' + JSON.stringify(lists));
  // an upload with a file out before sending and one refused while sending: still ONE list for it (its first one replaced)
  w.eval('window.__offline = true');
  await w.eval(`ab_upload([new File([], 'leer-drei.pdf', {type: 'application/pdf'}), new File(['Offline'], 'offline.txt', {type: 'text/plain'})], null)`);
  w.eval('window.__offline = false');
  const lists2 = [...d.querySelectorAll('#upbars .upout')].map(txt);
  check(lists2.length === 3 && lists2.filter(t => /leer-drei\.pdf/.test(t)).length === 1 && lists2.some(t => /leer-drei\.pdf/.test(t) && /offline\.txt/.test(t)), 'the third upload: one list with both of its files: ' + JSON.stringify(lists2));
  d.querySelectorAll('#upbars .upout .upoutx').forEach(b => b.click());
  w.close();

  // ================= #6173 2: the documents offline - the list says it, no second message
  w = await boot({user: 'frida', hash: 'docs'}); d = w.document;
  check(await until(() => d.querySelector('#dc-file'), 80), 'frida: the documents are drawn');
  watchToasts(w);
  w.eval('window.__offline = true');
  await w.eval(`dc_upload([new File(['Angebot'], 'angebot-offline.txt', {type: 'text/plain'})])`);
  w.eval('window.__offline = false');
  const dout = d.querySelector('#upbars .upout');
  check(dout && /angebot-offline\.txt Only available online\./.test(txt(dout)), 'documents offline: the list names the file and why: ' + txt(dout));
  check(!w.__toasts.some(t => /Only available online/.test(t)), 'documents offline: no second message as a toast: ' + JSON.stringify(w.__toasts));
  w.close();

  console.log(`p21247_a_upload_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
