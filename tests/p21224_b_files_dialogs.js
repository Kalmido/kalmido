// 2.1224.0 part B UI test (#6113): Files - Move to a folder, the Share dialog, public links in the file view, the lock dialog
// kalmido-suite: fresh
// Own container (start.sh; P21224B_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom for the ways, Firefox for the phone
// (360 px) and the lock dialog (real WebCrypto). Invented names and files only.
// freelancer-matrix: files of a person without an organisation (frida: Move and the public link in her private space)
// - Move to…: with more than 60 folders the picker shows them all as a tree, its title once; the search finds a folder four
//   levels deep and a click moves the file there (its row in that folder); the bar's Move (two chosen) opens the same picker
//   and moves both
// - Share: choosing a person adds them at once with "Can view" (no second step "Add"), one sentence under the title; at
//   360 px (German) "Darf bearbeiten" is whole and the row stays inside the screen
// - the file view's tab Shares: an existing public link with Copy / New link / Switch off; Copy copies its address, Switch
//   off ends it (the server lists none)
// - the lock dialog: three short sentences (what happens, what no longer works, who is missing) and the missing name
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21224_b_files_dialogs', check, shots: 'P21224B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21224B_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const upload = async (ck, name, text, form) => {
  const fd = new FormData(); fd.append('file', new Blob([text]), name);
  for (const [k, v] of Object.entries(form || {space: 'private'})) fd.append(k, v);
  const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: ck}, body: fd});
  return ((await r.json()).items || [])[0]?.id;
};
const FEATS = 'files,docs,collab';
const parentOf = async (ck, id) => (await call(ck, 'GET', `/api/files/nodes/${id}`)).parent_id ?? null;
// the visible entries of the open menu (a search hides the others)
const items = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].filter(b => !b.hidden && !b.closest('[hidden]'));

(async () => {
  await new Promise(r => setTimeout(r, 600));
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(','), ...FEATS.split(',')])].filter(Boolean).join(',');
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: st0.me.id})).id;
  check(ORG, 'setup: the organisation Alpha');
  const mona = await call(CA, 'POST', '/api/users', {username: 'mona', display_name: 'Mona Beispiel', password: 'password123', email: 'mona@example.com'});
  const fr = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(mona.http < 300 && fr.http < 300, 'setup: mona and frida');
  check((await call(CA, 'PUT', `/api/orgs/${ORG}/members`, {email: 'mona@example.com', role: 'member'})).http < 300, 'setup: mona member of Alpha');
  const MK = await login('mona'), FK = await login('frida');
  await call(MK, 'POST', `/api/orgs/${ORG}/join`, {});
  await call(FK, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats, workspace: 'private'});
  check(((await call(FK, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida has no organisation');

  // frida: 65 folders at the top, one chain four levels deep, three files
  const mk = async (name, parent) => (await call(FK, 'POST', '/api/files/folders', parent ? {name, parent_id: parent} : {name, space: 'private'})).id;
  for (let i = 1; i <= 65; i++) await mk('Ordner ' + String(i).padStart(2, '0'));
  const P1 = await mk('Projekte'), P2 = await mk('Stadtwerke Musterstadt', P1), P3 = await mk('Rohmaterial', P2), DEEP = await mk('Drehtag 1', P3);
  const O65 = ((await call(FK, 'GET', '/api/files/folders?ablage=1')).folders || []).find(f => f.name === 'Ordner 65')?.id;
  check(DEEP && O65, 'setup: 69 folders, one four levels deep');
  const FA = await upload(FK, 'drehplan.txt', 'Plan'), FB = await upload(FK, 'lageplan.txt', 'Lage'), FC = await upload(FK, 'zufahrt.txt', 'Weg');
  check(FA && FB && FC, 'setup: three files at the top');
  let w, d;

  // ================= Move to…: the tree with its search (one file)
  w = await boot({user: 'frida', hash: 'ablage'}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FA}"]`)), 'frida: the file store shows her files');
  w.eval(`ab_moveDlg(ab_item(${FA}))`);
  check(await until(() => d.querySelector('#pop:not(.hidden) #mq-q')), 'Move to…: the picker opens with a search field');
  const all = items(d).map(b => b.textContent.trim());
  check(all.length >= 70, `Move to…: every folder, no cut after 60 (${all.length} entries)`);
  check((d.querySelector('#pop').textContent.match(/Move to/g) || []).length === 1, 'Move to…: the title once ' + d.querySelector('#pop').textContent.slice(0, 80));
  check(all.includes('Drehtag 1') && !all.some(t => t.includes(' / ')), 'Move to…: the folders by their names (a tree), not as whole paths');
  const deepBtn = items(d).find(b => b.textContent.trim() === 'Drehtag 1');
  check(deepBtn?.classList.contains('abmt4') && /Projekte \/ Stadtwerke Musterstadt \/ Rohmaterial \/ Drehtag 1/.test(deepBtn?.title || ''), 'Move to…: the deep folder indented four levels, its path as the tooltip');
  const top = items(d).find(b => b.textContent.trim() === 'Top level');
  check(top?.disabled && top.classList.contains('on'), 'Move to…: the current place (Top level) is marked and not choosable');
  const q = d.querySelector('#mq-q'); q.value = 'drehtag'; q.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(await until(() => items(d).length === 1 && items(d)[0].textContent.trim() === 'Drehtag 1'), 'Move to…: the search finds the folder four levels deep ' + items(d).map(b => b.textContent.trim()).join('|'));
  items(d)[0].click();
  check(await until(async () => (await parentOf(FK, FA)) === DEEP), 'Move to…: the file lies in "Drehtag 1" on the server');
  w.close();
  w = await boot({user: 'frida', hash: 'ablage/' + DEEP}); d = w.document;
  check(await until(() => /drehplan\.txt/.test(d.querySelector(`#view .abrow[data-abid="${FA}"]`)?.textContent || '')), 'Move to…: the file shows in "Drehtag 1"');
  w.close();

  // ================= the bar's Move: the same picker, both chosen ones
  w = await boot({user: 'frida', hash: 'ablage'}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FB}"]`) && d.querySelector(`#view .abrow[data-abid="${FC}"]`)), 'frida: two files at the top');
  w.eval(`ab_selPick(${FB}); ab_selPick(${FC})`);
  const mv = await until(() => d.querySelector('#ab-sbar [data-absel="move"]'));
  check(mv && /2 selected/.test(d.querySelector('#ab-sbar').textContent), 'the bar: two chosen, Move');
  mv?.click();
  check(await until(() => d.querySelector('#pop:not(.hidden) #mq-q') && d.querySelector('#pop .abmt')), 'the bar\'s Move opens the same picker (tree + search)');
  const q2 = d.querySelector('#mq-q'); q2.value = 'Ordner 65'; q2.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(await until(() => items(d).length === 1), 'the bar\'s Move: the search finds "Ordner 65"');
  items(d)[0]?.click();
  check(await until(async () => (await parentOf(FK, FB)) === O65 && (await parentOf(FK, FC)) === O65), 'the bar\'s Move: both files lie in "Ordner 65"');
  w.close();
  w = await boot({user: 'frida', hash: 'ablage/' + O65}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FB}"]`) && d.querySelector(`#view .abrow[data-abid="${FC}"]`)), 'the bar\'s Move: both rows show in "Ordner 65"');
  w.close();

  // ================= the file view's tab Shares: an existing public link (frida, no organisation)
  const XL = await call(FK, 'POST', `/api/files/nodes/${FA}/ext-links`, {expires: 'none', label: 'Kunde Nord'});
  const link = (XL.links || []).find(l => l.id === XL.id);
  check(XL.http < 300 && link?.url, 'setup: a public link of drehplan.txt ' + XL.http);
  w = await boot({user: 'frida', hash: 'ablage/' + DEEP}); d = w.document;
  Object.defineProperty(w.navigator, 'clipboard', {configurable: true, value: {writeText: async t => { w.__cp = t; }}});
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FA}"]`)), 'file view: the folder shows the file');
  w.eval(`dc_open(${FA}, {tab: 'share'})`);
  const row = await until(() => d.querySelector('.dv-view #dv-p-share .xl-sec .xl-row'), 100);
  check(row && /Kunde Nord/.test(row.textContent), 'file view, tab Shares: the existing link with its label ' + (d.querySelector('.dv-view #dv-p-share')?.textContent || '').replace(/\s+/g, ' ').slice(0, 200));
  check(row?.querySelector('[data-xl="copy"]') && row?.querySelector('[data-xl="regen"]') && row?.querySelector('[data-xl="revoke"]'), 'file view: Copy, New link and Switch off');
  // 2.1352.0 (#6172): the button "Link for external people…" is there but hidden while the section stands
  check(d.querySelector('.dv-view #dv-p-share [data-xl="new"]') && !d.querySelector('.dv-view #dv-p-share [data-dc="xlink"]:not([hidden])'), 'file view: "Create link" in the section (no second button)');
  row?.querySelector('[data-xl="copy"]').click();
  check(await until(() => w.__cp === link?.url), 'file view: Copy copies the link\'s address');
  row?.querySelector('[data-xl="revoke"]').click();
  check(await until(async () => ((await call(FK, 'GET', `/api/files/nodes/${FA}/ext-links`)).links || []).length === 0), 'file view: Switch off ends the link on the server');
  check(await until(() => !d.querySelector('.dv-view #dv-p-share .xl-row')), 'file view: the row is gone');
  w.close();

  // ================= 2.1352.0 (#6172): undo of a new link redraws only its own file's section; the button comes back
  // when the section cannot stand (the links may not be seen)
  const XB = await call(FK, 'POST', `/api/files/nodes/${FB}/ext-links`, {expires: 'none', label: 'Andere'});
  check(XB.http < 300, 'setup: a public link of lageplan.txt ' + XB.http);
  w = await boot({user: 'frida', hash: 'ablage/' + DEEP}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FA}"]`)), '#6172: the folder shows the file');
  w.eval(`xl_newDlg(${FA}, null, 'none')`);
  const mk6172 = await until(() => d.querySelector('.xldlg [data-xn="make"]'));
  mk6172?.click();
  check(await until(() => d.querySelector('.xldlg .xl-out:not([hidden])')), '#6172: a new link of drehplan.txt');
  d.querySelector('.xldlg [data-m="close"]')?.click();
  check(await until(async () => ((await call(FK, 'GET', `/api/files/nodes/${FA}/ext-links`)).links || []).length === 1), '#6172: the link is on the server');
  w.eval(`dc_open(${FB}, {tab: 'share'})`);
  const sb = await until(() => d.querySelector(`.dv-view #dv-p-share .xl-sec[data-nid="${FB}"] .xl-row`), 100);
  check(sb && /Andere/.test(sb.textContent), '#6172: lageplan.txt, tab Shares: its own link "Andere"');
  await w.eval('HIST.undo.at(-1).undo()');  // resolves once its answer was drawn (xl_req)
  check(((await call(FK, 'GET', `/api/files/nodes/${FA}/ext-links`)).links || []).length === 0, '#6172: undo switched the new link of drehplan.txt off');
  check(/Andere/.test(d.querySelector(`.dv-view #dv-p-share .xl-sec[data-nid="${FB}"]`)?.textContent || ''),
    '#6172: the section of lageplan.txt still shows its own link (was redrawn with the links of drehplan.txt)');
  w.close();
  w = await boot({user: 'frida', hash: 'ablage/' + DEEP}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FA}"]`)), '#6172: the folder again');
  w.eval(`{ const rf0 = rawFetch; rawFetch = (m, u, ...a) => m === 'GET' && /ext-links$/.test(u) ? Promise.reject(Object.assign(new Error('no'), {status: 403})) : rf0(m, u, ...a); }`);
  w.eval(`dc_open(${FA}, {tab: 'share'})`);
  const xb = await until(() => d.querySelector('.dv-view #dv-p-share [data-dc="xlink"]:not([hidden])'));
  check(xb && !d.querySelector('.dv-view #dv-p-share .xl-sec'), '#6172: links not to be seen: no section, the button "Link for external people…" shows');
  w.close();

  // ================= #7590: the view of a plain file, Actions > "Link for external people…" > Create link: the view reads the
  // file again over its node - no request for a document (404) and no "Not found" over the new link
  w = await boot({user: 'frida', hash: 'ablage/' + O65}); d = w.document;
  check(await until(() => d.querySelector(`#view .abrow[data-abid="${FB}"]`)), '#7590: the folder shows lageplan.txt');
  w.eval(`dc_open(${FB})`);
  check(await until(() => w.eval('DC.doc && DC.doc.id') === FB && w.eval('!!DC.doc.file') && d.querySelector('.dv-view')), '#7590: the view of the plain file');
  w.eval(`window.__t = []; { const t0 = toast; toast = (m, ...a) => { __t.push(String(m)); return t0(m, ...a); }; }
    window.__dq = []; { const r0 = rawFetch; rawFetch = (m, u, ...a) => { if (/^\\/api\\/docs\\/\\d+$/.test(u)) __dq.push(u); return r0(m, u, ...a); }; }
    dcv_actItems(DC.doc, true, document.querySelector('.dv-view [data-dc="actsmore"]') || document.querySelector('.dv-view')).find(x => x && x.label === tr('Link for external people…')).fn()`);
  const mk7590 = await until(() => d.querySelector('.xldlg [data-xn="make"]'));
  mk7590?.click();
  check(await until(() => d.querySelector('.xldlg .xl-out:not([hidden])')), '#7590: the new link shows');
  check(await until(async () => ((await call(FK, 'GET', `/api/files/nodes/${FB}/ext-links`)).links || []).length === 2), '#7590: the link is on the server');
  await new Promise(r => setTimeout(r, 600));
  check(w.eval('__dq.length') === 0, '#7590: no request for a document of the plain file ' + w.eval('JSON.stringify(__dq)'));
  check(!w.eval('__t.some(m => /Not found/.test(m))') && !/Not found/.test(d.querySelector('#toast, .toast')?.textContent || ''), '#7590: no "Not found" ' + w.eval('JSON.stringify(__t)'));
  check(w.eval('DC.doc && DC.doc.id') === FB && w.eval('!!DC.doc.file') && d.querySelector('.dv-view'), '#7590: the view still shows the file');
  w.close();

  // ================= Share: choosing adds at once with "Can view" (alice, Alpha)
  const BOX = (await call(CA, 'POST', '/api/files/folders', {name: 'Drehorte', space: 'org:' + ORG})).id;
  check(BOX, 'setup: alice\'s folder in Alpha');
  w = await boot({user: 'alice', hash: 'ablage'}); d = w.document;
  check(await until(() => typeof w.fs_shareDialog === 'function' || w.eval('typeof ab_share') === 'function'), 'alice: the file store');
  w.eval(`ab_share(${BOX})`);
  const md = await until(() => d.querySelector('.abshdlg #ab-sht') && d.querySelector('.abshdlg'));
  check(md && !md.querySelector('[data-abs="add"]') && !md.querySelector('#ab-shr'), 'Share: no second step (no Add button, no role before the choice)');
  const hint = md?.querySelector('.shint.lhint')?.textContent.trim() || '';
  check(hint && (hint.match(/\.\s|\.$/g) || []).length === 1, 'Share: one sentence under the title: ' + hint);
  // arrows on the closed field fire change - that must not share yet; Enter adds
  const sht = md.querySelector('#ab-sht');
  sht.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'ArrowDown', bubbles: true}));
  sht.value = 'user_id:' + mona.id;
  sht.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(sht.value === 'user_id:' + mona.id && !md.querySelector('#ab-shl .mrow[data-sid]'), 'Share: walking the names with the arrow keys shares with nobody');
  sht.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
  check(await until(() => /Mona Beispiel/.test(md.querySelector('#ab-shl .mrow[data-sid]')?.textContent || '')), 'Share: Mona is in the list at once');
  check(md.querySelector('#ab-shl [data-absr]')?.value === 'view', 'Share: with "Can view" beside her');
  check(await until(async () => ((await call(CA, 'GET', `/api/files/nodes/${BOX}`)).shares || []).some(s => s.user_id === mona.id && s.role === 'view')), 'Share: the share is on the server (view)');
  check(md.querySelector('#ab-sht').value === '', 'Share: the choice is free again for the next person');
  const rs = md.querySelector('#ab-shl [data-absr]'); rs.value = 'edit'; rs.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(await until(async () => ((await call(CA, 'GET', `/api/files/nodes/${BOX}`)).shares || []).some(s => s.user_id === mona.id && s.role === 'edit')), 'Share: the role beside her changes it (edit)');
  // review (#6113): someone shared already is not offered again - choosing her would set her back to "Can view" without an end date
  check(await until(() => !md.querySelector(`#ab-sht option[value="user_id:${mona.id}"]`)), 'Share: Mona, shared already, is no longer offered in the choice');
  check(((await call(CA, 'GET', `/api/files/nodes/${BOX}`)).shares || []).some(s => s.user_id === mona.id && s.role === 'edit'), 'Share: her role stays "Can edit"');
  w.close();

  // ================= Firefox: the Share dialog at 360 px in German, the lock dialog
  await call(CA, 'PATCH', '/api/settings', {lang: 'de'});
  await firefox(async o => {
    const {cmd, ev, ctx, shot} = o;
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await new Promise(r => setTimeout(r, 250)); } return false; };
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await o.nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'p360: login');
    await o.nav(B + '#ablage');
    check(await wait(`!!document.querySelector('#view .abview') && typeof ab_share === 'function'`), 'p360: the file store is drawn');
    await ev(`(ab_share(${BOX}), 1)`);
    check(await wait(`!!document.querySelector('.abshdlg #ab-shl [data-absr]')`), 'p360: the Share dialog with Mona');
    const m = JSON.parse(await ev(`(() => { const s = document.querySelector('.abshdlg #ab-shl [data-absr]'), r = s.getBoundingClientRect(), cs = getComputedStyle(s);
      const sp = document.createElement('span'); sp.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + cs.font; sp.textContent = s.options[s.selectedIndex].text; document.body.append(sp);
      const need = sp.getBoundingClientRect().width; sp.remove();
      const row = s.closest('.mrow').getBoundingClientRect();
      return JSON.stringify({txt: s.options[s.selectedIndex].text, need, w: s.clientWidth, sw: s.scrollWidth, l: r.left, r: r.right, rowR: row.right, vw: innerWidth}); })()`));
    check(m.txt === 'Darf bearbeiten', 'p360: the role in German ' + m.txt);
    check(m.sw <= m.w + 1 && m.w >= m.need + 8, `p360: "Darf bearbeiten" is not cut (${Math.round(m.need)} px text in ${m.w} px)`);
    check(m.l >= 0 && m.r <= m.vw + .5 && m.rowR <= m.vw + .5, 'p360: the role and the row inside the screen ' + JSON.stringify(m));
    // the person and "x" in one line, role and end date in the next (no "x" alone in a line of its own)
    const lay = JSON.parse(await ev(`(() => { const r = document.querySelector('.abshdlg #ab-shl .mrow[data-sid]'), T = e => Math.round(e.getBoundingClientRect().top);
      return JSON.stringify({n: T(r.querySelector('.n')), x: T(r.querySelector('[data-absx]')), role: T(r.querySelector('[data-absr]')), date: T(r.querySelector('.dpbtn'))}); })()`));
    check(Math.abs(lay.n - lay.x) < 12 && Math.abs(lay.role - lay.date) < 12 && lay.role > lay.n, 'p360: name and x in one line, role and end date below ' + JSON.stringify(lay));
    await shot('p21224b-p360-share.png');
    await ev(`(() => { document.querySelector('.abshdlg [data-m="close"]').click(); return 1; })()`);
    check(await wait(`!document.querySelector('.abshdlg')`), 'p360: the Share dialog closes');

    // the lock dialog: who has no encryption yet is named (fslInfo stubbed: alice's folder, Mona with keys, Bert without)
    check(await wait(`(async () => { if (typeof fsl_lockDlg !== 'function') await loadModule('fslock'); return typeof fsl_lockDlg === 'function' && fslOk(); })()`), 'lock: fslock.js loaded, the browser can encrypt');
    await ev(`(() => { window.__fi = fslInfo; fslInfo = async () => ({mode: null, members: [{user_id: ${mona.id}, name: 'Mona Beispiel', has_keys: true}, {user_id: 999, name: 'Bert Kaminski', has_keys: false}], tagged: 0}); fsl_lockDlg({id: ${BOX}, name: 'Drehorte'}); return 1; })()`);
    check(await wait(`!!document.querySelector('#cdlg-b .fsl-who') && !document.getAnimations().some(x => x.playState === 'running')`), 'lock: the dialog opens');
    const L = JSON.parse(await ev(`JSON.stringify({what: document.querySelector('#cdlg-b .fsl-what')?.textContent || '', after: document.querySelector('#cdlg-b .fsl-after')?.textContent || '', who: document.querySelector('#cdlg-b .fsl-who')?.textContent || '', all: document.querySelector('#cdlg-b')?.textContent || ''})`));
    const one = t => t && (t.match(/[.!?](\s|$)/g) || []).length <= 2;
    check(L.what && L.after && L.who, 'lock: what happens, what no longer works, who: three parts ' + JSON.stringify(L));
    check(one(L.what) && one(L.after), 'lock: each a short sentence');
    check(/verschlüsselt/.test(L.what) && /Vorschau/.test(L.after), 'lock: what happens (encrypted) and what no longer works (preview)');
    check(/Frühere Versionen/.test(L.after) && /Betreiber/.test(L.after) && /auch der Betreiber nicht/.test(L.all), 'lock: the removed versions and "not even the operator" are named');
    check(/Bert Kaminski/.test(L.who) && /Mona Beispiel/.test(L.who), 'lock: who gets the key and who is missing are named: ' + L.who);
    check(!/API-Token/.test(L.all) && !/Passphrase und Wiederherstellungscode/.test(L.all), 'lock: no technical words without explanation');
    await shot('p21224b-p360-lock.png');
    await ev(`(() => { [...document.querySelectorAll('.cdlg button')].find(b => b.dataset.cd !== 'yes')?.click(); fslInfo = window.__fi; return 1; })()`);
    check(await wait(`!document.querySelector('#cdlg-b')`), 'lock: Cancel closes it, nothing locked');
  }, true);
  check(!((await call(CA, 'GET', `/api/files/nodes/${BOX}`)).locked), 'lock: the folder stays open');

  console.log(`p21224_b_files_dialogs: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
