// 2.1208.0 part A UI test (#6173): uploading into the file store / the documents - Undo of a new version with expect_version,
// kalmido-suite: fresh
// no second message beside the list of what stayed out, each upload its own list.
// Own container (start.sh; P21208A_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom only. Invented names and files only.
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
if (!process.env.P21208A_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
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
  check(await upElsewhere('skript.txt', 'Skript Fassung 3 von woanders') === 200, 'meanwhile a newer version from elsewhere');
  d.querySelector('#toast button').click();
  check(await until(() => /Meanwhile someone else uploaded a newer version, it stays as it is: skript\.txt/.test(txt(d.querySelector('#toast')))), 'Undo says that someone else uploaded a newer version: ' + txt(d.querySelector('#toast')));
  check(await content(FK, SK) === 'Skript Fassung 3 von woanders', 'Undo left the newer version on top (nothing put back over it)');
  const vers = (await call(FK, 'GET', `/api/files/nodes/${SK}`)).versions || [];
  check(vers.length === 3, 'no restore was stored (still 3 versions): ' + vers.length);

  // Undo -> Redo -> Undo of an own new version: each step sends the version the step before made
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
  check(!w.__toasts.some(t => /Offline: only works again with a connection/.test(t)), 'documents offline: no second message as a toast: ' + JSON.stringify(w.__toasts));
  w.close();

  console.log(`p21208_a_upload_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
