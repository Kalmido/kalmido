// 2.1178.0 part B UI test (#6115): the trash of the file store - the message of Delete in the file view, a deleted file by its
// kalmido-suite: fresh
// address, the trash's rows read only, the way back to the workspace, "Empty trash" and the note in plain words.
// Own container (start.sh; P21178B_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom for the flows, Firefox for the delete in
// the file view (its way back is a real history step). Invented names and files only.
// freelancer-matrix: frida has no organisation (her private space); rita edits a folder of alice's, vera only reads it
// (1) Firefox: Delete in the file view goes back to the list WITH "… moved to the trash · Undo", still there after 1,5 s; Undo
//     brings the file back.
// (2) #ablage/<deleted file>: "In the trash" + Restore on top, no Upload a new version / Share / Open; Preview shows the text.
// (3) a row of the trash opens the same details; a picture right there (content?trash=1).
// (4) the trash is never remembered: "Files" after another area (and Documents, #ablage/docs) opens the workspace.
// (5) "Empty trash" only for whom something in it may be deleted for good; the note in plain words.
// Server: GET /api/files/nodes/<id>/content?trash=1 only for a person who may restore it (owner / the editor who deleted it):
//     404 without trash=1, for a stranger, a reader, an editor who did not delete it, a folder.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21178_b_files_ui', check, shots: 'P21178B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21178B_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const upload = async (ck, name, data, form) => {
  const fd = new FormData(); fd.append('file', new Blob([data]), name);
  for (const [k, v] of Object.entries(form || {space: 'private'})) fd.append(k, v);
  const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: ck}, body: fd});
  return ((await r.json()).items || [])[0]?.id;
};
const raw = async (ck, url) => (await fetch(B + url.replace(/^\//, ''), {headers: {'X-Requested-With': 'kalmido', Cookie: ck}})).status;
const rawText = async (ck, url) => (await fetch(B + url.replace(/^\//, ''), {headers: {'X-Requested-With': 'kalmido', Cookie: ck}})).text();
const FEATS = 'files,docs';
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(','), ...FEATS.split(',')])].filter(Boolean).join(',');
  const ID = {};
  for (const name of ['frida', 'rita', 'vera']) {
    const u = await call(CA, 'POST', '/api/users', {username: name, display_name: name[0].toUpperCase() + name.slice(1), password: 'password123', email: `${name}@example.com`, orgs: []});
    check(u.http < 300, `setup: ${name} ${u.http}`); ID[name] = u.id;
  }
  const FK = await login('frida'), RK = await login('rita'), VK = await login('vera');
  for (const ck of [CA, FK, RK, VK]) await call(ck, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  check(((await call(FK, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida has no organisation');
  const items = async (ck, q) => (await call(ck, 'GET', '/api/files?' + q)).items || [];
  let w, d;

  const BOX = (await call(FK, 'POST', '/api/files/folders', {name: 'Drehorte', space: 'private'})).id;
  const BRIEF = await upload(FK, 'brief.txt', 'Lieber Max, bis morgen am Set.');
  const BILD = await upload(FK, 'standbild.png', PNG);
  check(BOX && BRIEF && BILD, 'setup: a folder, a text and a picture');
  for (const id of [BRIEF, BILD]) await call(FK, 'DELETE', `/api/files/nodes/${id}`);
  check((await items(FK, 'space=trash')).filter(x => [BRIEF, BILD].includes(x.id)).length === 2, 'setup: both in the trash');

  // ================= server: content?trash=1
  check(await raw(FK, `/api/files/nodes/${BRIEF}/content`) === 404, 'server: a file in the trash stays 404 without trash=1');
  check(await raw(FK, `/api/files/nodes/${BRIEF}/content?trash=1`) === 200, 'server: trash=1 reads it for its owner (frida, no organisation)');
  check(await rawText(FK, `/api/files/nodes/${BRIEF}/content?trash=1`) === 'Lieber Max, bis morgen am Set.', 'server: the content is the file');
  check(await raw(RK, `/api/files/nodes/${BRIEF}/content?trash=1`) === 404, 'server: trash=1 gives nothing to a stranger');
  check(await raw(FK, `/api/files/nodes/${BOX}/content?trash=1`) === 404, 'server: a living folder with trash=1: 404');
  const BIN = (await call(FK, 'POST', '/api/files/folders', {name: 'Alt', space: 'private'})).id;
  await call(FK, 'DELETE', `/api/files/nodes/${BIN}`);
  check(await raw(FK, `/api/files/nodes/${BIN}/content?trash=1`) === 404, 'server: a folder in the trash with trash=1: 404 (only plain files)');
  // alice's folder: rita edits, vera reads
  const SH = (await call(CA, 'POST', '/api/files/folders', {name: 'Gemeinsam', space: 'private'})).id;
  const SF = await upload(CA, 'drehplan.txt', 'Drehplan', {parent_id: String(SH)});
  const SF2 = await upload(CA, 'gage.txt', 'Gage nur fuer alice', {parent_id: String(SH)});
  check((await call(CA, 'POST', `/api/files/nodes/${SH}/shares`, {user_id: ID.rita, role: 'edit'})).http < 300, 'setup: Gemeinsam shared with rita to edit');
  check((await call(CA, 'POST', `/api/files/nodes/${SH}/shares`, {user_id: ID.vera, role: 'view'})).http < 300, 'setup: Gemeinsam shared with vera to read');
  check(await raw(VK, `/api/files/nodes/${SF2}/content`) === 200, 'setup: vera reads the living gage.txt');
  check((await call(RK, 'DELETE', `/api/files/nodes/${SF}`)).http < 300, 'setup: rita puts drehplan.txt into the trash');
  check((await call(CA, 'DELETE', `/api/files/nodes/${SF2}`)).http < 300, 'setup: alice puts gage.txt into the trash');
  check(await raw(RK, `/api/files/nodes/${SF}/content?trash=1`) === 200, 'server: rita reads the file she put into the trash');
  check(await raw(CA, `/api/files/nodes/${SF}/content?trash=1`) === 200, 'server: alice (owner) reads it too');
  check(await raw(RK, `/api/files/nodes/${SF2}/content?trash=1`) === 404, 'server: rita (edit share) reads nothing of a file alice deleted');
  check(await raw(RK, `/api/files/nodes/${SF2}/content?trash=1&v=1`) === 404, 'server: nor an old version of it');
  check(await raw(VK, `/api/files/nodes/${SF2}/content?trash=1`) === 404, 'server: vera (reader) reads nothing of a deleted file');
  check(await raw(VK, `/api/files/nodes/${SF}/content?trash=1`) === 404, 'server: nor of the one rita deleted');
  check(await raw(VK, `/api/files/nodes/${SF2}/content`) === 404, 'server: without trash=1 a reader gets 404 as before');

  // ================= (2) a deleted file by its address: "In the trash" + Restore, no new version, no Share
  w = await boot({user: 'frida', hash: 'ablage/' + BRIEF, ls: {'tasks.abSpace': '"private"'}}); d = w.document;
  let dlg = await until(() => d.querySelector('.abtrdlg'));
  check(dlg && /In the trash/.test(txt(dlg.querySelector('.abtrashed'))) && dlg.querySelector('.abtrashed [data-abd="restore"]'), 'its address: "In the trash" with Restore on top ' + txt(dlg));
  check(dlg && /brief\.txt/.test(txt(dlg.querySelector('h3'))) && /Deleted on /.test(txt(dlg)), 'the dialog names the file and when it was deleted ' + txt(dlg));
  check(dlg && !dlg.querySelector('[data-abd="ver"], [data-abd="share"], [data-abd="open"]') && !/Upload a new version|Share…/.test(txt(dlg)), 'no Upload a new version / Share / Open of a living file');
  dlg.querySelector('[data-abd="see"]').click();
  check(await until(() => /Lieber Max, bis morgen am Set\./.test(txt(d.querySelector('.tview')))), 'Preview shows the text (read only) ' + txt(d.querySelector('.tview')).slice(0, 80));
  d.querySelector('.tview')?.remove();
  dlg.querySelector('[data-abd="restore"]').click();
  check(await until(async () => !(await items(FK, 'space=trash')).some(x => x.id === BRIEF)), 'Restore brings it back');
  check(await until(() => !d.querySelector('.abtrdlg')), 'the dialog closes');
  check(await until(() => /“brief\.txt” restored/.test(txt(d.querySelector('#toast')))), 'the message "… restored" ' + txt(d.querySelector('#toast')));
  w.close();

  // ================= (3) (4) (5) the trash itself
  w = await boot({user: 'frida', hash: 'ablage', ls: {'tasks.abSpace': '"private"'}}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${BOX}"]`)), 'frida: the private space');
  w.eval(`(() => { ab_pick('trash'); AB.key = ''; ab_load(); return 1; })()`);  // what the space button / the panel's Trash do
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${BILD}"] [data-ab="tropen"]`)), 'the trash: its row can be opened');
  check(w.localStorage.getItem('tasks.abSpace') === '"private"', 'the trash is not remembered (abSpace stays private) ' + w.localStorage.getItem('tasks.abSpace'));
  check(d.querySelector('#view [data-ab="trash-empty"]'), 'frida (owner): "Empty trash"');
  const note = txt(d.querySelector('#view .abtrashdays'));
  check(/^Deleted items stay here (for \d+ days?, then they are deleted permanently|until you delete them permanently)\.$/.test(note), 'the note in plain words: ' + note);
  check(!/deletion runs|server/i.test(note), 'no server words in the note');
  d.querySelector(`#view .abrow[data-abid="${BILD}"] [data-ab="tropen"]`).click();
  dlg = await until(() => d.querySelector('.abtrdlg'));
  check(dlg && /standbild\.png/.test(txt(dlg)) && /In the trash/.test(txt(dlg)), 'a tap on the row: its details ' + txt(dlg));
  const img = dlg?.querySelector('.abtrimg img');
  check(img && /\/content\?trash=1$/.test(img.getAttribute('src')), 'the picture right there (content?trash=1)');
  check(dlg && !dlg.querySelector('[data-abd="ver"], [data-abd="share"]'), 'read only: no new version, no Share');
  dlg.querySelector('[data-m="close"]').click();
  check(await until(() => !d.querySelector('.abtrdlg')), 'Close closes it, the trash stays');
  w.location.hash = '#docs';
  check(await until(() => w.eval('S.route.mod') !== 'ablage'), 'another area');
  w.location.hash = '#ablage';
  check(await until(() => w.eval('S.route.mod') === 'ablage' && w.eval('ab_curSpace()') === 'private' && d.querySelector(`#view .abrow[data-abid="${BOX}"]`)), '"Files" again: the workspace, not the trash ' + w.eval('ab_curSpace()'));
  // the documents of Files (#ablage/docs) leave the trash as well
  w.eval(`(() => { ab_pick('trash'); AB.key = ''; ab_load(); return 1; })()`);
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${BILD}"]`)), 'the trash once more');
  w.location.hash = '#ablage/docs';
  check(await until(() => w.eval('ab_curSpace()') === 'private'), 'Documents: the trash is left ' + w.eval('ab_curSpace()'));
  w.close();
  // rita: may restore what she deleted, delete nothing for good; an old abSpace "trash" opens the workspace
  w = await boot({user: 'rita', hash: 'ablage', ls: {'tasks.abSpace': '"trash"'}}); d = w.document;
  check(await until(() => w.eval('ab_curSpace()') === 'private'), 'an old abSpace "trash" opens the workspace');
  w.eval(`(() => { ab_pick('trash'); AB.key = ''; ab_load(); return 1; })()`);
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${SF}"]`)), 'rita: her trash shows drehplan.txt');
  check(d.querySelector(`#view .abrow[data-abid="${SF}"] [data-ab="restore"]`) && !d.querySelector('#view [data-ab="trash-empty"]'), 'rita: Restore, but no "Empty trash" (nothing she may delete for good)');
  d.querySelector(`#view .abrow[data-abid="${SF}"] [data-ab="tropen"]`).click();
  dlg = await until(() => d.querySelector('.abtrdlg'));
  check(dlg && /drehplan\.txt/.test(txt(dlg)) && dlg.querySelector('[data-abd="restore"]') && /Owner: Alice/.test(txt(dlg)), 'rita: the details with Restore and whose it is ' + txt(dlg));
  w.close();

  // ================= (1) Firefox: Delete in the file view keeps its message with Undo
  const DEL = await upload(FK, 'notiz-set.txt', 'Notiz vom Set');
  await firefox(async o => {
    const {cmd, ev, ctx, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await o.nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.abSpace', '"private"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`) === 200, 'ff: login');
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(250); } return false; };
    await o.nav(B + '#ablage');
    check(await wait(`!!document.querySelector('#view .abrow[data-abid="${DEL}"] [data-ab="open"]')`), 'ff: the list shows notiz-set.txt');
    await ev(`(() => { document.querySelector('#view .abrow[data-abid="${DEL}"] [data-ab="open"]').click(); return 1; })()`);
    check(await wait(`location.hash === '#ablage/${DEL}' && !!document.querySelector('.dv-view [data-dc="del"]')`), 'ff: the file view with Delete');
    await ev(`(() => { document.querySelector('.dv-view [data-dc="del"]').click(); return 1; })()`);
    check(await wait(`location.hash !== '#ablage/${DEL}' && !document.querySelector('.dv-view') && /notiz-set\\.txt” moved to the trash/.test(document.querySelector('#toast:not(.hidden)')?.textContent || '')`), 'ff: back at the list with "… moved to the trash"');
    check(await wait(`!document.querySelector('#view .abrow[data-abid="${DEL}"]') && !!document.querySelector('#view .abrow')`), 'ff: the list without the file');
    await sleep(1500);  // the walk-through's probe: still there after 1,5 s (the message's own time is 6 s)
    check(await ev(`/moved to the trash/.test(document.querySelector('#toast:not(.hidden)')?.textContent || '') && /Undo/.test(document.querySelector('#toast:not(.hidden) button')?.textContent || '')`), 'ff: after 1,5 s the message with Undo is still there');
    await shot('p21178b-view-delete-toast.png');
    await ev(`(() => { document.querySelector('#toast button').click(); return 1; })()`);
    check(await until(async () => !(await items(FK, 'space=trash')).some(x => x.id === DEL)), 'ff: Undo brings the file back');
    check(await wait(`!!document.querySelector('#view .abrow[data-abid="${DEL}"]')`), 'ff: its row is back in the list');
  });

  console.log(`p21178_b_files_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
