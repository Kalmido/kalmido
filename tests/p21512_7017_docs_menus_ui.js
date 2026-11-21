// kalmido-suite: fresh
// #7017 (audit #5248 D9 / D10) UI test: the documents' settings in one place and the file menu in groups.
// Own container (start.sh), jsdom. Invented names only.
// - D9: the documents' head has one text button "Settings" (no symbols for the lists and the gear); it opens Settings >
//   Documents with the inboxes themselves (folder watcher, scan inboxes, e-mail); Connections only points there and its
//   pointer opens the same place; Back returns
// - D10: the "…" of a folder of the documents is grouped Open / Share / Edit / Folder settings ("Recognition…" and "Scan inbox
//   for this folder…" under Folder settings), the trash apart as the last entry; "Recognition…" leads on (its own menu) and
//   Escape closes it
// freelancer-matrix: files (alice has no organisation: her private workspace)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); let j = {}; try { j = await r.json(); } catch { /* no body */ } return {...j, http: r.status}; };
const until = async (fn, n = 60) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const up = async (url, field, name, text, extra = {}) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(extra)) fd.append(k, v);
  fd.append(field, new Blob([text], {type: 'text/plain'}), name);
  return (await fetch(B + url, {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd})).json().catch(() => ({}));
};
// the open menu as groups: [[heading, [entries]], ...] and the entries after the last group
const groups = d => [...d.querySelectorAll('#pop:not(.hidden) .mgrp')].map(g => [g.getAttribute('aria-label'), [...g.querySelectorAll('[role="menuitem"] .ml')].map(x => x.textContent.trim())]);
const items = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"] .ml')].map(x => x.textContent.trim());
const closeMenu = d => d.dispatchEvent(new d.defaultView.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call('GET', '/api/state');
  check(!(st0.me?.workspaces || []).length, 'alice has no organisation');
  const feats = [...new Set([...(st0.settings.features || '').split(',').filter(Boolean), 'files', 'docs'])].join(',');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats, workspace: 'private'});
  const DOC = ((await up('api/docs', 'files', 'statement-alpha.txt', 'An invented bank statement', {ws: 'private'})).ids || [])[0];
  check(DOC, 'setup: a document (makes the documents folder)');
  const ROOT = (await call('GET', `/api/files/nodes/${DOC}`)).parent_id;
  const BANK = (await call('POST', '/api/files/folders', {parent_id: ROOT, name: 'Bank Alpha'})).id;
  check(ROOT && BANK, 'setup: a folder in the documents');

  // ================= D9: one text button, the inboxes in Settings > Documents
  let w = await boot({user: 'alice', hash: 'docs'}), d = w.document;
  const sb = await until(() => d.querySelector('#view .dc-bar [data-dc="settings"]'));
  check(sb && sb.textContent.trim() === 'Settings' && !sb.querySelector('svg'), '#7017 D9: the documents\' head has the text button "Settings"');
  check(!d.querySelector('#view .dc-bar [data-dc="lists"]'), '#7017 D9: no second symbol for the lists');
  click(w, sb);
  const shown = k => !d.querySelector(`.smodal [data-pane="${k}"]`)?.classList.contains('hidden');
  check(await until(() => shown('docs') && d.querySelector('.smodal [data-pane="docs"] #s-dcs #s-scan .dsc-way')), '#7017 D9: it opens Settings > Documents with the inboxes themselves');
  check(/Folder watcher/.test(d.querySelector('#s-scan')?.textContent || '') && d.querySelector('#s-scan [data-dsc="inbox"]'), '... folder of the file store and folder watcher there');
  check(!!d.querySelector('#s-dcs [data-dcs="lists"]'), '... and the way to senders, types and fields');
  // Connections: only the pointer, which leads back to the same place
  click(w, d.querySelector('.smodal .snav [data-sec="integr"]'));
  check(await until(() => shown('integr')), 'Connections opens');
  const ptr = d.querySelector('.smodal [data-pane="integr"] [data-intr="scan"] [data-jump="#s-scan-h"]');
  check(ptr && !d.querySelector('.smodal [data-pane="integr"] #s-scan'), '#7017 D9: Connections keeps only a pointer to the inboxes');
  click(w, ptr);
  check(await until(() => shown('docs')), '#7017 D9: the pointer opens Settings > Documents');
  w.eval(`(() => { let e = document.querySelector('.smodal [data-pane="docs"]'); while (e && !e._back) e = e.parentElement; return e ? e._back() : false; })()`);
  check(await until(() => shown('integr')), 'Back: Connections again');
  w.close();

  // ================= D10: the folder's "…" in groups
  w = await boot({user: 'alice', hash: 'ablage/' + ROOT}); d = w.document;
  check(await until(() => w.eval('typeof dsc_folderItems === "function" && typeof abd_menuItems === "function"')), 'the documents\' scripts are loaded');
  const b = await until(() => d.querySelector(`[data-ab="menu"][data-id="${BANK}"]`));
  b?.click();
  await until(() => items(d).length);
  // what the workspace offers for scan inboxes is loaded with the first opening: open the menu again
  await until(() => w.eval('!!(typeof DSCF !== "undefined" && DSCF.private && DSCF.private.s)'));
  closeMenu(d);
  b?.click();
  await until(() => items(d).includes('Scan inbox for this folder…'));
  const g = groups(d), heads = g.map(x => x[0]), of = name => (g.find(x => x[1].includes(name)) || [])[0];
  check(heads.join('|') === 'Open|Share|Edit|Folder settings', '#7017 D10: the groups Open / Share / Edit / Folder settings ' + JSON.stringify(g));
  check(of('Download') === 'Open' && of('History') === 'Open', '... Download and History under Open');
  check(of('Share…') === 'Share', '... Share… under Share');
  check(of('Rename…') === 'Edit' && of('Move to…') === 'Edit', '... Rename and Move under Edit');
  check(of('Recognition…') === 'Folder settings' && of('Scan inbox for this folder…') === 'Folder settings', '#7017 D10: Recognition… and Scan inbox under Folder settings');
  const all = items(d);
  check(all[all.length - 1] === 'Move to the trash' && !of('Move to the trash'), '... the trash apart as the last entry ' + JSON.stringify(all));
  // on: Recognition… opens its own menu; back: Escape
  click(w, [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].find(x => x.querySelector('.ml')?.textContent.trim() === 'Recognition…'));
  check(await until(() => d.querySelector('#pop:not(.hidden) .mgrp[aria-label="Recognition"]')), '#7017 D10: Recognition… leads to its own menu');
  closeMenu(d);
  check(await until(() => !d.querySelector('#pop:not(.hidden) [role="menuitem"]')), 'Escape closes it');
  w.close();

  console.log(`p21512_7017_docs_menus_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
