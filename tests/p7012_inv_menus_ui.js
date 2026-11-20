// kalmido-suite:
// UI test (#7012, audit #5248 B1 B2 B9): the ways of the invoices. Own container (start.sh), jsdom. Invented data only.
// - an open finalised invoice: its row menu has "Record payment…" (the dialog of the open document); booked, the list shows it
//   paid; a draft and a paid invoice have no such entry
// - "New invoice" has "Recurring invoice (series)…": a new invoice draft opens with the series sheet over it
// - the section "Invoice series" shows without a series too, with its empty line and the same button
// - the "…" of a quotation and of an invoice: "Layout & numbers…" opens Settings > Company & office
// - Settings > Company & office: "Signature…" next to the signature switch opens the signature dialog
// P4: frida has no organisation, her own office gets the same (freelancer-matrix: office)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7012_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = async (fn, n = 75) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(200); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const COMPANY = {name: 'Beispiel Film GmbH', street: 'Musterweg 1', zip: '12345', city: 'Musterstadt', country: 'DE', email: 'hallo@beispiel.example', vat_id: 'DE123456789',
  iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank', tax_number: '12/345/67890'};
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const FEAT = 'office,clients';
const items = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')];
const item = (d, re) => items(d).find(b => re.test(b.textContent));

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', modules: ['office']});
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  for (const ck of [CA, CF]) await call(ck, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida: no organisation');

  for (const [u, ck] of [['alice', CA], ['frida', CF]]) {
    check((await call(ck, 'PUT', '/api/office/settings', {company_fields: COMPANY})).http === 200, `${u}: the company`);
    const cl = await call(ck, 'POST', '/api/clients', {name: 'Kunde Beta GmbH', street: 'Weg 2', zip: '10115', city: 'Berlin', country: 'DE', email: 'kunde-beta@example.com'});
    const inv = await call(ck, 'POST', '/api/office/docs', {kind: 'invoice', client_id: cl.id, service_from: today(), items: [{title: 'Schnitt', qty: 1, rate: 100}]});
    const fin = await call(ck, 'POST', `/api/office/docs/${inv.id}/finalize`, {});
    const draft = await call(ck, 'POST', '/api/office/docs', {kind: 'invoice', client_id: cl.id, items: [{title: 'Entwurf', qty: 1, rate: 50}]});
    check(inv.http === 201 && fin.http === 200 && draft.http === 201, `${u}: a finalised invoice and a draft (${inv.http} ${fin.http} ${fin.error || ''})`);

    let w = await boot({user: u, hash: 'office/invoices'}), d = w.document;
    const row = id => d.querySelector(`#view .ofdrow[data-id="${id}"]`);
    check(await until(() => row(inv.id) && row(draft.id)), `${u}: the invoice list with both rows`);
    // B2: the section of the series without a series, with its empty line and the button
    check(await until(() => d.querySelector('#view .rin-sec .rin-none')), `${u}: "Invoice series" shows without a series, with its empty line`);
    check(/Recurring invoice \(series\)/.test(d.querySelector('#view .rin-sec [data-rin="new0"]')?.textContent || ''), `${u}: ... and the button to start one`);
    // B1: the row menu of the open invoice
    w.eval(`ofdRowMenu(${inv.id}, document.querySelector('#view .ofdrow[data-id="${inv.id}"]'))`);
    const pay = await until(() => item(d, /^Record payment/));
    check(!!pay, `${u}: the row menu of an open invoice has "Record payment…" ` + items(d).map(b => b.textContent.trim()).join(' | '));
    if (pay) click(w, pay);
    const md = await until(() => d.querySelector('.modal #ofd-p-amount'));
    check(md && /100/.test(md.value), `${u}: the payment dialog opens with the open amount ` + (md && md.value));
    const rec = md && [...d.querySelectorAll('.modal .foot button, .modal button')].find(b => /^Record$/.test(b.textContent.trim()));
    if (rec) click(w, rec);
    check(await until(async () => (await call(ck, 'GET', `/api/office/docs/${inv.id}`)).status === 'paid'), `${u}: the payment is booked: paid`);
    check(await until(() => (w.eval(`(OFD.list || []).find(r => r.id === ${inv.id})?.status`) === 'paid')), `${u}: the list shows it paid without leaving it`);
    w.eval(`closePop && closePop(); 1`);
    w.eval(`ofdRowMenu(${inv.id}, document.querySelector('#view .ofdrow[data-id="${inv.id}"]'))`);
    await until(() => items(d).length);
    check(!item(d, /^Record payment/), `${u}: a paid invoice has no "Record payment…"`);
    w.eval(`closePop && closePop(); 1`);
    w.eval(`ofdRowMenu(${draft.id}, document.querySelector('#view .ofdrow[data-id="${draft.id}"]'))`);
    await until(() => items(d).length);
    check(!item(d, /^Record payment/), `${u}: a draft has no "Record payment…"`);
    // B9: Layout & numbers from the row's menu
    const lay = item(d, /^Layout & numbers/);
    check(!!lay, `${u}: the "…" of an invoice has "Layout & numbers…"`);
    if (lay) click(w, lay);
    check(await until(() => d.querySelector('.smodal #s-biz-company, .smodal [data-ostp="company"]')), `${u}: it opens Settings > Company & office`);
    // B9: the signature button in the same settings
    const sig = await until(() => d.querySelector('.smodal [data-ost-sig]'));
    check(!!sig && /Signature/.test(sig.textContent), `${u}: Documents & numbers has "Signature…"`);
    if (sig) click(w, sig);
    check(await until(() => [...d.querySelectorAll('.modal h3')].some(h => h.textContent.trim() === 'Signature') && d.querySelector('.modal .lt-sigbox')), `${u}: "Signature…" opens the signature dialog`);
    w.eval(`document.querySelectorAll('.modal').forEach(m => m.remove()); 1`);
    w.close();

    // B2: "New invoice" > "Recurring invoice (series)…": a new draft with the series sheet over it
    w = await boot({user: u, hash: 'office/invoices'}); d = w.document;
    const nb = await until(() => d.querySelector('#view [data-ofd="new-inv"]'));
    if (nb) click(w, nb);
    const ser = await until(() => item(d, /^Recurring invoice \(series\)/));
    check(!!ser, `${u}: "New invoice" has "Recurring invoice (series)…" ` + items(d).map(b => b.textContent.trim()).join(' | '));
    const n0 = (await call(ck, 'GET', '/api/office/docs?kind=invoice')).docs?.length;
    if (ser) click(w, ser);
    check(await until(() => d.querySelector('.modal #ofd-rin-title')), `${u}: the series sheet opens`);
    check(await until(() => /^#office\/(s\/[^/]+\/)?invoices\/\d+$/.test(w.location.hash)), `${u}: over the editor of the new invoice draft ` + w.location.hash);
    const n1 = (await call(ck, 'GET', '/api/office/docs?kind=invoice')).docs?.length;
    check(n0 != null && n1 === n0 + 1, `${u}: one new invoice draft (${n0} -> ${n1})`);
    w.eval(`document.querySelectorAll('.modal').forEach(m => m.remove()); 1`);
    // B9 in the editor: the "…" of an open invoice
    w.eval(`menu(document.body, ofdMoreItems(OFD.doc, false))`);
    check(await until(() => item(d, /^Layout & numbers/)), `${u}: the editor's "…" has "Layout & numbers…"`);
    w.close();
  }

  console.log(`p7012_inv_menus_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
