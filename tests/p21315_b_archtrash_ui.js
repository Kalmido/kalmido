// 2.1315.0 B (#6590 c) UI: one imported old document goes into the office trash and comes back, by clicks
// kalmido-suite: fresh
// (jsdom, invented data only). The way a person goes:
// - Invoices, kind Archive: the old invoice is listed; Correct opens its dialog with Delete
// - Delete: the dialog closes, the toast says "Moved to the trash" with Undo, the row is gone from the list (and the app: 404)
// - the toast's Undo: the row is back with its number
// - a second Delete, then the office trash (Offers, trash button) lists it as "Old document (PDF)" with its number;
//   Restore brings it back into the archive list
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, until, idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const PDF = Buffer.from('%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer << /Root 1 0 R >>\n%%EOF\n');
const NUM = 'ALT-2025-117';
const row = d => [...d.querySelectorAll('.oimarch li')].find(li => li.textContent.includes(NUM));
const toastWith = (d, rx) => { const t = d.querySelector('#toast'); return t && !t.classList.contains('hidden') && rx.test(t.textContent) ? t : null; };

(async () => {
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab,office,clients'});
  { const me = (await call('GET', '/api/state')).me; const org = await call('POST', '/api/admin/orgs', {name: 'Example Studio', admin_id: me.id});
    await call('PATCH', '/api/settings', {workspace: `org:${org.id}`}); }
  const run = await call('POST', '/api/office/legacy/archive/run');
  check(run.http === 201, 'archive run ' + run.http);
  const fd = new FormData();
  fd.append('file', new Blob([PDF], {type: 'application/pdf'}), NUM + '.pdf');
  for (const [k, v] of Object.entries({run_id: run.run_id, kind: 'invoice', number: NUM, client_name: 'Example Client', date: '2025-06-02', amount: '595'})) fd.append(k, String(v));
  const up = await fetch(B + 'api/office/legacy/archive', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd});
  check(up.status === 201, 'an archived invoice ' + up.status);
  const aid = (await up.json()).id;

  const w = await boot({hash: 'office/invoices'}), d = w.document;
  await until(() => d.querySelector('.ofdkinds [data-kind="archive"]'), {timeout: 30000});
  d.querySelector('.ofdkinds [data-kind="archive"]').click();
  check(!!await until(() => row(d), {timeout: 30000}), 'archive: the old invoice is listed');

  // ---- Delete in its dialog
  row(d).querySelector('[data-oim="arch-edit"]').click();
  const del = await until(() => d.querySelector('.r81b-dlg [data-r81b="trash"]'));
  check(!!del && /Delete/.test(del.textContent), 'the dialog has Delete');
  del?.click();
  const t1 = await until(() => toastWith(d, /Moved to the trash/));
  check(!!t1 && t1.textContent.includes(NUM) && !!t1.querySelector('button'), 'toast: moved to the trash, with Undo ' + (t1?.textContent || ''));
  check(!!await until(() => !d.querySelector('.r81b-dlg') && !row(d)), 'the dialog closed, the row is gone');
  check((await call('GET', `/api/office/legacy/archive/${aid}`)).http === 404, 'gone for the app (404)');

  // ---- the toast's Undo
  t1?.querySelector('button')?.click();
  check(!!await until(() => row(d), {timeout: 30000}), "the toast's Undo: the row is back");
  // 2.1329.0 (#6848): a state push after the undo (load() -> onumListFresh -> ofdLoadList) read the list again and showed
  // "Loading" instead of the rows for a moment - in the CI exactly before the next click (row(d) undefined); now the rows
  // stay until the fresh list is there. The push here at once (its 5 s pause reset), as a change made elsewhere
  await idle(w);
  let blink = 0; const iv = setInterval(() => { if (!row(d)) blink++; }, 1);
  let reads = 0; const f0 = w.fetch; w.fetch = (u, o) => { if (/\/api\/office\/legacy\/archive$/.test(String(u)) && !(o && o.method && o.method !== 'GET')) reads++; return f0(u, o); };
  w.eval('onumListFresh.at = 0; onumListFresh()');
  await until(() => reads > 0);
  await idle(w);
  clearInterval(iv); w.fetch = f0;
  check(reads > 0 && blink === 0 && !!row(d), `a change elsewhere reads the list again, its rows stay meanwhile (hidden ${blink} times)`);
  check((await call('GET', `/api/office/legacy/archive/${aid}`)).number === NUM, 'with its number');

  // ---- again, then back through the office trash
  row(d).querySelector('[data-oim="arch-edit"]').click();
  (await until(() => d.querySelector('.r81b-dlg [data-r81b="trash"]')))?.click();
  await until(() => !row(d));
  w.location.hash = 'office/offers';
  check(!!await until(() => d.querySelector('[data-ofd="trash"]'), {timeout: 30000}), 'offers: the trash button');
  d.querySelector('[data-ofd="trash"]').click();
  const li = await until(() => [...d.querySelectorAll('.otblist li')].find(x => x.textContent.includes(NUM)));
  check(li && li.dataset.core === 'oarchive' && /Old document \(PDF\)/.test(li.textContent), 'the office trash lists it ' + (li?.textContent || '').trim().slice(0, 120));
  li?.querySelector('[data-m="restore"]')?.click();
  check(!!await until(() => toastWith(d, /Restored/)), 'toast: Restored');
  check(!!await until(() => !d.querySelector('.otblist')), 'the trash dialog closes');
  w.location.hash = 'office/invoices';
  // the kind buttons of the quotations are still there until the invoices area is drawn: wait for its route first
  await until(() => w.eval('S.route.tab') === 'invoices' && d.querySelector('.ofdkinds [data-kind="archive"]'), {timeout: 30000});
  if (!d.querySelector('.ofdkinds [data-kind="archive"].on')) d.querySelector('.ofdkinds [data-kind="archive"]').click();
  check(!!await until(() => row(d), {timeout: 30000}), 'back in the archive list');
  await idle(w);
  w.close();

  console.log(`p21315_b_archtrash_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
