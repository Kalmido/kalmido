// kalmido-suite: fresh
// 2.1289.0 UI tests (#6481 N3, S3, U4): the office editor and list, own container (start.sh). jsdom; invented data only.
// Played by a person WITHOUT an organisation (the personal office; freelancer-matrix: office).
// - N3: an invoice draft has no number pen any more; the finalise dialog offers "Number of your own (optional)" with a
//   reason; a refused number (gap without a reason) keeps the dialog open and finalises nothing, with the reason it is
//   finalised with exactly that number
// - N3: a numbered invoice draft from before 2.1289 carries the tag "Draft with number - please finalise" in the list
// - U4: a finalised invoice the import took from a file carries "imported on ..." in the list and "Imported on ... by ..."
//   in its view
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6481_UI_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const sql = q => execFileSync('python3', [path.join(__dirname, 'dbx.py'), DATA, q]);
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const until = async (fn, n = 60) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return fn(); };
const FEAT = 'cal,comments,collab,office,clients';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  // freelancer-matrix: office -- a person without an organisation
  const u = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http === 200 || u.http === 201, 'the freelancer ' + u.http);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const st = await call('PUT', '/api/office/settings', {lang: 'de', currency: 'EUR', invoice_scheme: 'RE-{yyyy}-{seq:03}', company_fields: {name: 'Beispiel Studio', street: 'Musterweg 1', zip: '12345', city: 'Musterstadt',
    country: 'DE', email: 'kontakt@example.com', tax_number: '12/345/67890', vat_id: 'DE999999999', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'}});
  check(st.http === 200, 'office settings ' + st.http);
  const draft = async () => { const x = await call('POST', '/api/office/docs', {kind: 'invoice', project_title: 'Imagefilm', recipient: {name: 'Beispielkunde AG', lines: ['Marktplatz 2', '54321 Beispielort']},
    service_from: '2026-05-01', items: [{title: 'Kamera', qty: 1, rate: 500}]}); check(x.http === 201, 'invoice draft ' + x.http); return x.id; };
  const I = await draft();
  const pv = await call('GET', `/api/office/docs/${I}/number-preview`);
  const m = /^RE-(\d{4})-(\d{3})$/.exec(pv.number || '');
  check(!!m, 'the preview ' + JSON.stringify(pv));
  const own = `RE-${m[1]}-${String(+m[2] + 2).padStart(3, '0')}`;  // one above the next: a gap of one number, a reason needed

  const w = await boot({user: 'frida', hash: 'office/invoices/' + I}); const d = w.document;
  check(!!await until(() => d.querySelector('[data-ofd="finalize"]')), 'the invoice draft opens');
  check(!d.querySelector('.ofdhead .onumpen'), 'N3: an invoice draft has no number pen (its own number comes with the finalising)');
  w.__dialogs = 'manual';
  d.querySelector('[data-ofd="finalize"]').click();
  const md = await until(() => d.querySelector('.modal.cdlg'));
  check(md && /Will be finalised as/.test(md.textContent) && md.textContent.includes(pv.number), 'N3: the dialog names the next number ' + (md && md.textContent.slice(0, 160)));
  const sum = md && md.querySelector('.ofdfinhand summary');
  check(sum && /Number of your own/.test(sum.textContent), 'N3: the dialog offers a number of your own');
  sum.click();
  const no = md.querySelector('#ofd-fin-no'), why = md.querySelector('#ofd-fin-why');
  check(no && why && md.querySelector(`label[for="ofd-fin-no"]`) && md.querySelector(`label[for="ofd-fin-why"]`), 'N3: number and reason fields with their labels');
  no.value = own;
  md.querySelector('[data-cd="yes"]').click();
  await sleep(1200);
  const st1 = await call('GET', `/api/office/docs/${I}`);
  check(md.isConnected && !st1.locked && !st1.number, 'N3: a gap without a reason is refused, the dialog stays open, nothing finalised ' + JSON.stringify({open: md.isConnected, locked: st1.locked, number: st1.number}));
  why.value = 'Eine Nummer im Altprogramm vergeben';
  md.querySelector('[data-cd="yes"]').click();
  const fin = await until(async () => { const x = await call('GET', `/api/office/docs/${I}`); return x.locked && x; });
  check(fin && fin.number === own, 'N3: finalised with the own number ' + (fin && fin.number));
  check(await until(() => !md.isConnected), 'N3: the dialog closes');
  w.close();

  // a numbered draft from before 2.1289 and an imported finalised invoice in the list
  const J = await draft();
  const old = `RE-${m[1]}-${String(+m[2] + 10).padStart(3, '0')}`;
  sql(`UPDATE office_docs SET number='${old}' WHERE id=${+J}`);
  sql(`INSERT INTO office_doc_log(org_id, doc_id, user_id, at, action, target, detail) SELECT org_id, id, created_by, '2026-11-01T10:00:00Z', 'import', 'doc', '{}' FROM office_docs WHERE id=${+I}`);
  const w2 = await boot({user: 'frida', hash: 'office/invoices'}); const d2 = w2.document;
  const rowJ = await until(() => d2.querySelector(`#view .ofdrow[data-id="${J}"]`));
  check(rowJ && /Draft with number - please finalise/.test(rowJ.querySelector('.ofd-numdraft')?.textContent || ''), 'N3: the list marks the numbered draft ' + (rowJ && rowJ.textContent.slice(0, 160)));
  const rowI = d2.querySelector(`#view .ofdrow[data-id="${I}"]`);
  check(rowI && /imported on/.test(rowI.querySelector('.ofd-imp')?.textContent || '') && !rowI.querySelector('.ofd-numdraft'), 'U4: the list marks the imported invoice ' + (rowI && rowI.textContent.slice(0, 160)));
  check(!rowJ.querySelector('.ofd-imp'), 'U4: the draft is not marked imported');
  w2.close();
  const w3 = await boot({user: 'frida', hash: 'office/invoices/' + I}); const d3 = w3.document;
  const tag = await until(() => d3.querySelector('.ofdhead .ofd-imp'));
  check(tag && /Imported on .+ by Frida/.test(tag.textContent), 'U4: the view says imported on ... by ... ' + (tag && tag.textContent));
  w3.close();
  console.log(`p6481_office_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p6481_office_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
