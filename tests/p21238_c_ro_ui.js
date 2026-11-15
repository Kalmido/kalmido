// 2.1238.0 part C UI test (#6161, Stufe 2): files + documents and lists / tasks ask the shared core's canWrite
// kalmido-suite: fresh
// Own container (start.sh; P21238C_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom only. Invented names and files only.
// freelancer-matrix: files and lists of a person without an organisation (frida: her private space, all buttons there)
// Files: rita (read-only in the organisation Alpha) and vera (member of Alpha, alice's private folder shared with her for reading) see no
//   New folder / Upload / Scan, no "+" at the head of the tree, no Move / Trash in the selection bar; the read hint exactly
//   once; the file name is shown, a subfolder opens and the path leads back. mona (member) and frida see every button and no
//   hint. The server still refuses rita's / vera's writes (403 / 404 as before).
// Lists: rita (list role edit capped to view by her organisation role) and vera (a share 'view') see in the list no add bar,
//   round boxes without a button, the hint once; the task panel has the title as read text, no Complete / date button, no
//   disabled button in its head, no second hint (beside the list) and the hint once when the list is not beside it; closing
//   the panel leads back to the list. mona and frida get the add bar, the buttons, no hint. The server refuses the writes.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21238C_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const upload = async (ck, name, text, form) => {
  const fd = new FormData(); fd.append('file', new Blob([text]), name);
  for (const [k, v] of Object.entries(form || {space: 'private'})) fd.append(k, v);
  const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: ck}, body: fd});
  return ((await r.json()).items || [])[0]?.id;
};
const FEATS = 'files,docs,collab,comments';
const WRITE = ['[data-ab="new-folder"]', '[data-ab="upload"]', '[data-ab="scan"]'];
const has = (d, sel) => !!d.querySelector('#view ' + sel);
const hints = d => d.querySelectorAll('.cwro').length;
const vtext = d => (d.querySelector('#view')?.textContent || '').replace(/\s+/g, ' ');

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(','), ...FEATS.split(',')])].filter(Boolean).join(',');
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: st0.me.id})).id;
  check(ORG, 'setup: the organisation Alpha');
  const uid = {};
  for (const [u, role] of [['rita', 'readonly'], ['mona', 'member'], ['vera', 'member'], ['frida', null]]) {
    const r = await call(CA, 'POST', '/api/users', {username: u, display_name: u[0].toUpperCase() + u.slice(1), password: 'password123', email: `${u}@example.com`, orgs: role ? [{id: ORG, role}] : []});
    check(r.http < 300 && r.id, `setup: ${u} ${r.http}`);
    uid[u] = r.id;
  }
  const RK = await login('rita'), MK = await login('mona'), VK = await login('vera'), FK = await login('frida');
  for (const ck of [RK, MK]) await call(ck, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'org:' + ORG});
  for (const ck of [VK, FK]) await call(ck, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  check(((await call(RK, 'GET', '/api/state')).me?.workspaces || []).some(o => o.id === ORG && o.role === 'readonly'), 'setup: rita is read-only in Alpha');
  check(((await call(FK, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida has no organisation');

  // a folder of alice with a file and a subfolder, shared for reading with rita and vera
  const BOX = (await call(CA, 'POST', '/api/files/folders', {name: 'Kiste', space: 'private'})).id;
  const BF = await upload(CA, 'drehplan.txt', 'Drehplan', {parent_id: String(BOX)});
  const SUB = (await call(CA, 'POST', '/api/files/folders', {name: 'Unterordner', parent_id: BOX})).id;
  const SF = await upload(CA, 'lageplan.txt', 'Lageplan', {parent_id: String(SUB)});
  check(BOX && BF && SUB && SF, 'setup: folder, file, subfolder, file');
  for (const u of ['rita', 'vera']) check((await call(CA, 'POST', `/api/files/nodes/${BOX}/shares`, {user_id: uid[u], role: 'view'})).http < 300, `setup: Kiste shared with ${u} for reading`);
  // an organisation project (rita edit = capped to view, mona edit) and a private one shared with vera for reading
  const OL = (await call(CA, 'POST', '/api/lists', {name: 'Studio board', org_id: ORG})).id;
  for (const [u, role] of [['rita', 'edit'], ['mona', 'edit']]) await call(CA, 'PUT', `/api/lists/${OL}/members`, {user_id: uid[u], role});
  const OT = (await call(CA, 'POST', '/api/tasks', {list_id: OL, title: 'Plan the shoot', due: '2026-12-01'})).id;
  const PL = (await call(CA, 'POST', '/api/lists', {name: 'Script work'})).id;
  await call(CA, 'PUT', `/api/lists/${PL}/members`, {user_id: uid.vera, role: 'view'});
  const PT = (await call(CA, 'POST', '/api/tasks', {list_id: PL, title: 'Read the script', due: '2026-12-02'})).id;
  const FL = (await call(FK, 'POST', '/api/lists', {name: 'Own work'})).id;
  const FT = (await call(FK, 'POST', '/api/tasks', {list_id: FL, title: 'Own task'})).id;
  check(OL && OT && PL && PT && FL && FT, 'setup: projects and tasks');
  const roleIn = async (ck, lid) => ((await call(ck, 'GET', '/api/state')).lists || []).find(l => l.id === lid)?.role;
  check(await roleIn(RK, OL) === 'view' && await roleIn(VK, PL) === 'view' && await roleIn(MK, OL) === 'edit', 'setup: the server\'s list roles (rita view, vera view, mona edit)');
  let w, d;

  // ================= files: the readers
  for (const [u, ck] of [['rita', RK], ['vera', VK]]) {
    w = await boot({user: u, hash: 'ablage/' + BOX}); d = w.document;
    check(await until(() => d.querySelector(`#view .abrow[data-abid="${BF}"]`)), `${u}: the shared folder shows its file`);
    check(/drehplan\.txt/.test(vtext(d)) && /Unterordner/.test(vtext(d)), `${u}: the file name and the subfolder are shown`);
    check(WRITE.every(s => !has(d, s)), `${u}: no New folder / Upload / Scan in a folder she only reads`);
    check(!d.querySelector('#view .abview').classList.contains('abdropok'), `${u}: no drop frame`);
    check(hints(d) === 1 && d.querySelector('#view .cwro'), `${u}: the read hint exactly once (${hints(d)})`);
    check(![...d.querySelectorAll('#view button')].some(b => b.disabled && /new-folder|upload|scan|move|trash/.test(b.dataset.ab || b.dataset.absel || '')), `${u}: no disabled writing button`);
    w.eval(`ab_selPick(${BF})`);
    const bar = await until(() => d.querySelector('#ab-sbar'));
    check(bar && bar.querySelector('[data-absel="dl"]') && !bar.querySelector('[data-absel="move"]') && !bar.querySelector('[data-absel="trash"]'), `${u}: the selection bar has Download, no Move / Trash`);
    // into the subfolder and back
    w.eval(`go('ablage/${SUB}')`);
    check(await until(() => d.querySelector(`#view .abrow[data-abid="${SF}"]`)), `${u}: the subfolder opens with its file`);
    check(/lageplan\.txt/.test(vtext(d)) && WRITE.every(s => !has(d, s)) && hints(d) === 1, `${u}: in the subfolder the file, no writing buttons, one hint`);
    const up = d.querySelector(`#view .abcrumbs [data-go="ablage/${BOX}"]`);
    check(up, `${u}: the path leads back to Kiste`);
    up?.click();
    check(await until(() => d.querySelector(`#view .abrow[data-abid="${BF}"]`)), `${u}: back in Kiste`);
    w.close();
    // the server refuses as before
    let r = await call(ck, 'POST', '/api/files/folders', {name: 'Sneaky', parent_id: BOX});
    check([403, 404].includes(r.http), `${u}: API new folder in Kiste refused ${r.http}`);
    r = await call(ck, 'DELETE', `/api/files/nodes/${BF}`);
    check([403, 404].includes(r.http), `${u}: API trash of the file refused ${r.http}`);
  }
  // rita at the top of Alpha: no writing, no "+" in the tree, one hint
  w = await boot({user: 'rita', hash: 'ablage'}); d = w.document;
  check(await until(() => d.querySelector('#view .abview') && w.eval('ab_curSpace()') === 'org:' + ORG && !/Loading/.test(vtext(d))), 'rita: the top of Alpha is drawn');
  check(WRITE.every(s => !has(d, s)) && !d.querySelector('#side [data-abtadd]'), 'rita: no writing buttons at the top of Alpha, no "+" in the tree');
  check(await until(() => hints(d) === 1), `rita: the read hint once at the top of Alpha (${hints(d)})`);
  w.close();
  // mona (member) and frida (no organisation): every button, no hint
  for (const [u, sp] of [['mona', 'org:' + ORG], ['frida', 'private']]) {
    w = await boot({user: u, hash: 'ablage'}); d = w.document;
    check(await until(() => d.querySelector('#view .abview') && w.eval('ab_curSpace()') === sp && WRITE.every(s => has(d, s))), `${u}: New folder / Upload / Scan at the top of ${sp}`);
    check(await until(() => d.querySelector('#side [data-abtadd]')), `${u}: "+" at the head of the tree`);
    check(hints(d) === 0, `${u}: no read hint`);
    w.close();
  }

  // ================= documents: "Add documents" follows canWrite of the space (rita read-only: none; mona member: there)
  for (const [u, want] of [['rita', false], ['mona', true]]) {
    w = await boot({user: u, hash: 'ablage/docs'}); d = w.document;
    check(await until(() => d.querySelector('#view .dc-view') && !/Loading/.test(vtext(d))), `${u}: the documents' list is drawn`);
    check(await until(() => !!d.querySelector('#view .dc-up') === want), `${u}: "Add documents" ${want ? 'offered' : 'left out'}`);
    w.close();
  }
  { const fd = new FormData(); fd.append('files', new Blob(['%PDF-1.4 x']), 'brief.pdf'); fd.append('ws', 'org:' + ORG);
    const r = await fetch(B + 'api/docs', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: RK}, body: fd});
    check([403, 404].includes(r.status), `rita: API upload of a document refused ${r.status}`); }

  // ================= lists: the readers
  for (const [u, ck, L, T, title] of [['rita', RK, OL, OT, 'Plan the shoot'], ['vera', VK, PL, PT, 'Read the script']]) {
    w = await boot({user: u, hash: 'l/' + L}); d = w.document;
    const row = await until(() => d.querySelector(`#view .trow[data-id="${T}"]`));
    check(row && new RegExp(title).test(row.textContent), `${u}: the task's title in the list`);
    check(row && !row.querySelector('button.chk') && row.querySelector('span.chk'), `${u}: the round box shows the state, no button`);
    check(!d.querySelector('#view .qdock') && !d.querySelector('#view [data-act="section-new"]'), `${u}: no add bar, no New section`);
    check(hints(d) === 1 && d.querySelector('#view .cwro'), `${u}: the read hint once in the list (${hints(d)})`);
    w.eval(`openDetail(${T})`);
    check(await until(() => d.querySelector('#detail #d-title')?.value === title), `${u}: the task panel opens with its title`);
    const D = d.querySelector('#detail');
    check(D.querySelector('#d-title').readOnly, `${u}: the title reads`);
    check(!D.querySelector('button.chk') && !D.querySelector('[data-act="date"]') && !D.querySelector('.dtdone') && !D.querySelector('[data-act="prio"]'), `${u}: no Complete / date / priority button in the panel`);
    check(D.querySelector('.dtop .chk') && /Dec|12/.test(D.querySelector('.dtop .dchip')?.textContent || ''), `${u}: the state and the date are shown as text`);
    check(![...D.querySelectorAll('.dtop button')].some(b => b.disabled), `${u}: no disabled button in the panel's head`);
    check(hints(d) === 1 && !D.querySelector('.rotag') && !D.querySelector('.sayno'), `${u}: still ONE read hint with the panel beside the list (${hints(d)})`);
    // the panel without its list beside it: the hint once, in the panel
    w.eval(`go('inbox')`); await until(() => w.eval(`S.route.key === 'inbox'`));
    w.eval(`openDetail(${T})`);
    check(await until(() => d.querySelector('#detail #d-title')?.value === title && d.querySelector('#detail .cwro')), `${u}: elsewhere the panel carries the hint`);
    check(hints(d) === 1, `${u}: and only there (${hints(d)})`);
    d.querySelector('#detail [data-act="close-detail"]')?.click();
    check(await until(() => !w.eval('S.sel')), `${u}: the panel closes`);
    w.eval(`go('l/${L}')`);
    check(await until(() => d.querySelector(`#view .trow[data-id="${T}"]`)), `${u}: back in the list`);
    w.close();
    const r = await call(ck, 'PATCH', `/api/tasks/${T}`, {title: 'Sneaky'});
    check([403, 404].includes(r.http), `${u}: API change of the task refused ${r.http}`);
    const n = await call(ck, 'POST', '/api/tasks', {list_id: L, title: 'Sneaky'});
    check([403, 404].includes(n.http), `${u}: API new task refused ${n.http}`);
  }
  // mona (member, edit) and frida (her own list): the add bar, the buttons, no hint
  for (const [u, L, T] of [['mona', OL, OT], ['frida', FL, FT]]) {
    w = await boot({user: u, hash: 'l/' + L}); d = w.document;
    const row = await until(() => d.querySelector(`#view .trow[data-id="${T}"]`));
    check(row && row.querySelector('button.chk'), `${u}: the round box is a button`);
    check(await until(() => d.querySelector('#view .qdock')), `${u}: the add bar`);
    w.eval(`openDetail(${T})`);
    check(await until(() => d.querySelector('#detail button.chk') && d.querySelector('#detail [data-act="date"]')), `${u}: Complete and the date in the panel`);
    check(hints(d) === 0, `${u}: no read hint`);
    w.close();
  }
  // 2.1238.0 (#6161, review fund 1): a participant of an organisation's list writes only where the organisation role lets them
  // (the server's _org_list_writes): rita (read-only) gets no add / edit as participant, mona (member) does, frida's own Private too
  for (const [u, org, exp] of [['rita', ORG, false], ['mona', ORG, true], ['frida', null, true]]) {
    w = await boot({user: u, hash: 'inbox'});
    check(await until(() => w.eval('!!S.lists')), `${u}: the lists are there`);
    w.eval(`S.lists.push({id: -9, name: 'Part', role: 'participant', org_id: ${org === null ? 'null' : org}})`);
    check(w.eval('canAddTo(-9)') === exp && w.eval(`canEdit({id: -1, list_id: -9})`) === exp, `${u}: as participant ${exp ? 'adds and edits' : 'neither adds nor edits'}`);
    w.close();
  }

  console.log(`p21238_c_ro_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
