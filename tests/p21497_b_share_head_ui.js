// 2.1497.0 UI test (#7015: the document areas alike), own container (start.sh), jsdom. Invented names only.
// kalmido-suite: fresh
// - every opened object has the TEXT button "Share" in its head, also before its first share: a knowledge page, a table, a
//   folder of the file store, a file (the document view), an address book; it opens the area's own share dialog, the dialog
//   closes again and the object stays open (in, on, back)
// - a reader of a shared table / a receiver of a folder gets no such button
// - the words: the file view's tab "Teilen" (not "Zugriff"), a folder's "Download" (a ZIP) and "History", "Encrypt folder…"
//   instead of "Lock folder…", the table's "History", the contact card's "Vorgänge", the page's "Download" + "Export as Word"
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
// every module on (the fixture of the freelancer suites): Knowledge, Tables, contacts, files
const FEAT = 'cal,collab,comments,contacts,files,docs,wiki,sheets,office,clients';
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21497B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const upload = async (name, parent) => { const fd = new FormData(); fd.append('parent_id', String(parent)); fd.append('file', new Blob(['hello']), name); const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd}); return (await r.json()).items[0].id; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const txt = e => (e?.textContent || '').replace(/\s+/g, ' ').trim();
// the button is a text button (not a bare symbol) and says "Share"
const isText = b => !!b && b.classList.contains('btn') && txt(b) === 'Share';
// close the open dialog by its own close / done button (or Escape) and wait until it is gone
async function closeDlg(w, sel) {
  const d = w.document, md = d.querySelector(sel); if (!md) return false;
  const x = md.querySelector('[data-m="close"], [data-cbs="close"], .foot .btn.pri, .foot .btn');
  if (x) x.click(); else w.eval('modalClose && modalClose(document.querySelector(' + JSON.stringify(sel) + '))');
  return !!(await until(() => !d.querySelector(sel)));
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice Admin', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {tour: 'done', lang: 'en', features: FEAT});
  const BOB = (await call('POST', '/api/users', {username: 'bob', display_name: 'Bob Example', password: 'password123'})).id;
  const BK = await login('bob'); await call('PATCH', '/api/settings', {tour: 'done', lang: 'en', features: FEAT}, BK);
  const QUIET = (await call('POST', '/api/files/folders', {space: 'private', name: 'Quiet'})).id;
  const SHARED = (await call('POST', '/api/files/folders', {space: 'private', name: 'For Bob'})).id;
  await call('POST', `/api/files/nodes/${SHARED}/shares`, {user_id: BOB, role: 'view'});
  const FILE = await upload('plan.txt', QUIET);
  const PG = (await call('POST', '/api/wiki/pages', {space: 'private', path: 'Notes/Plan', body: 'Read this.'})).id;
  await call('GET', '/api/wiki?space=private');
  const SH = (await call('POST', '/api/sheets', {title: 'Budget sheet', space: 'private'})).id;
  const BOOK = (await call('POST', '/api/books', {name: 'Customers'})).id;
  check(QUIET > 0 && FILE > 0 && PG > 0 && SH > 0 && BOOK > 0, 'setup: folder, file, page, table, address book ' + JSON.stringify([QUIET, FILE, PG, SH, BOOK]));

  // ================= a folder without shares: "Share" in its head, the dialog, back
  let w = await boot({user: 'alice', hash: 'ablage/' + QUIET}), d = w.document;
  let b = await until(() => d.querySelector('#view .abtools [data-ab="share"]'));
  check(isText(b), '#7015 files: the unshared folder has the text button "Share" in its head ' + txt(b));
  b?.click();
  check(await until(() => /Quiet/.test(txt(d.querySelector('.abshdlg h3')))), 'files: it opens the share dialog of the folder');
  check(await closeDlg(w, '.abshdlg') && d.querySelector('#view .abtools [data-ab="share"]'), 'files: the dialog closes, the folder stays open');
  const items = w.eval(`JSON.stringify((ab_menuItems(AB.data.node) || []).filter(Boolean).map(x => x.label))`);
  check(/"Download"/.test(items) && /"History"/.test(items) && !/Download as ZIP|Details and history/.test(items), '#7015 files: the folder menu says "Download" and "History" ' + items);
  check(await until(() => w.eval(`typeof fsl_menuItem !== 'function' || (fsl_menuItem(AB.data.node) || {label: 'Encrypt folder…'}).label === 'Encrypt folder…'`)), '#7015: "Encrypt folder…" instead of "Lock folder…"');

  // ================= the file: the document view's head has "Share", its tab is "Teilen" in German
  w = await boot({user: 'alice', hash: 'ablage/' + FILE}); d = w.document;
  b = await until(() => d.querySelector('.dv-view .dv-hacts [data-dc="share"]'));
  check(isText(b), '#7015 document: the head has the text button "Share" ' + txt(b));
  b?.click();
  check(await until(() => d.querySelector('.abshdlg')), 'document: "Share" opens the file store\'s share dialog');
  check(await closeDlg(w, '.abshdlg') && d.querySelector('.dv-view'), 'document: the dialog closes, the file stays open');
  check(w.eval(`tr('Sharing')`) === 'Sharing' && txt(d.querySelector('.dv-view #dv-t-share')) === 'Sharing', '#7015 document: the tab is "Sharing" ' + txt(d.querySelector('.dv-view #dv-t-share')));

  // ================= the knowledge page: the text button next to the title
  w = await boot({user: 'alice', hash: 'wiki/' + PG}); d = w.document;
  b = await until(() => d.querySelector(`[data-wsh-share="${PG}"]`));
  check(isText(b), '#7015 knowledge: the page has the text button "Share" (was a symbol) ' + txt(b));
  b?.click();
  check(await until(() => d.querySelector('.wshmodal, .abshdlg')), 'knowledge: it opens the page\'s share dialog');
  check(await closeDlg(w, '.wshmodal, .abshdlg') && d.querySelector(`[data-wsh-share="${PG}"]`), 'knowledge: the dialog closes, the page stays open');
  const wi = w.eval(`JSON.stringify(wk_docItems(WK.pg).map(x => x.label))`);
  check(wi === JSON.stringify(['Download', 'Export as Word (.docx)']), '#7015 knowledge: "Download" (the page as PDF) and "Export as Word (.docx)" ' + wi);

  // ================= the table: "Share" in the head, not only deep in the "…"
  w = await boot({user: 'alice', hash: 'sheets/' + SH}); d = w.document;
  b = await until(() => d.querySelector('#view .shvtop [data-shv="share"]'));
  check(isText(b), '#7015 tables: the head has the text button "Share" ' + txt(b));
  b?.click();
  check(await until(() => /Budget sheet/.test(txt(d.querySelector('.modal h3')))), 'tables: it opens the table\'s share dialog');
  check(await closeDlg(w, '.modal') && d.querySelector('#view .shvtop'), 'tables: the dialog closes, the table stays open');
  check(w.eval(`SHV_HOOKS.menu.flatMap(f => f(SHV.sh) || []).some(x => x && x.label === 'History')`), '#7015 tables: the "…" says "History" (was "Recent changes")');

  // ================= the address book (the only one shown = the opened one): "Share" in the bar
  w = await boot({user: 'alice', hash: 'contacts'}); d = w.document;
  b = await until(() => d.querySelector('#view .ctbar [data-ct="bshare"]'));
  check(isText(b), '#7015 contacts: the opened address book has the text button "Share" ' + txt(b));
  b?.click();
  check(await until(() => /Customers/.test(txt(d.querySelector('.modal h3')))), 'contacts: it opens the address book\'s share dialog');
  check(await closeDlg(w, '.modal') && d.querySelector('#view .ctbar'), 'contacts: the dialog closes, the contacts stay');
  check(w.eval(`tr('Activities|contact')`) === 'Activities', '#7015 contacts: the card\'s block is "Activities"');

  // ================= German words
  const DE = await (await fetch(B + 'static/i18n/de.json')).json();
  check(DE['Sharing'] === 'Teilen' && DE['Activities|contact'] === 'Vorgänge' && DE['Encrypt folder…'] === 'Ordner verschlüsseln…' && DE['Export as CSV'] === 'Exportieren als CSV' && DE['History'] === 'Verlauf',
    '#7015 German: Teilen, Vorgänge, Ordner verschlüsseln…, Exportieren als CSV, Verlauf');
  check(!('Shares' in DE) && !('Lock folder…' in DE) && !('Recent changes' in DE), '#7015 German: the old words are gone');

  // ================= a receiver: no "Share" in the head of a folder shared with him
  w = await boot({user: 'bob', hash: 'ablage/' + SHARED}); d = w.document;
  check(await until(() => d.querySelector('#view .abtools')), 'bob: the shared folder opens');
  check(!d.querySelector('#view .abtools [data-ab="share"]'), 'bob (a reader): no "Share" in the head');

  console.log(`p21497_b_share_head_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
