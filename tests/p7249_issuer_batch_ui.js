// kalmido-suite: fresh
// (#7249) UI test: "Finalise and send all checked" for the drafts of invoice issuers without a mark (follow-up of #6703). Own
// container (start.sh with KALMIDO_ISSUER_KEYS=1 and SMTP to the stub of tests/stub_mail.py, which refuses refuse@...), jsdom.
// Invented companies, addresses and figures only.
// - the invoice list filtered "From invoice issuers" shows the button; a person's own list ("All ranges") does not
// - the dialog ticks only the drafts without a mark: a confirmed client (sent), a confirmed client whose address the mail server
//   refuses (finalised, not sent); it names why the others stay: a new client (client_new), the issuer's payment statement,
//   no sending wished, no e-mail address; those cannot be ticked
// - going: each ticked draft is finalised and sent through the office's own routes (a number of the issuer's range, the mail
//   in the stub, mail state sent / failed); the result names each; the others stay drafts, untouched
// - no automation: nothing happens before the person's click; the server's checks stay the gate (the hold mark of a new client)
// freelancer-matrix: office (frida has no organisation: her personal office, her own issuer)
// usage: node p7249_issuer_batch_ui.js <datadir>
const {execFileSync} = require('child_process');
const fs = require('fs');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const CT = process.env.KALMIDO_TEST_CONTAINER || 'kalmido-test';
const ENV = '-e KALMIDO_ISSUER_KEYS=1 -e KALMIDO_SMTP_HOST=127.0.0.1 -e KALMIDO_SMTP_PORT=1025 -e KALMIDO_SMTP_TLS=none -e KALMIDO_MAIL_FROM=kalmido@example.test';
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: ((process.env.EXTRA || '') + ' ' + ENV).trim()}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const key = async (k, method, url, body) => { const r = await fetch(B + 'api/v1/issuer/' + url, {method, headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + k}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const mails = to => { try { return fs.readFileSync(path.join(DATA, 'mail', 'out.jsonl'), 'utf8').split('\n').filter(l => l.trim() && l.includes(to)).length; } catch { return 0; } };
const FEAT = 'cal,comments,collab,office,clients';
const TODAY = new Date().toISOString().slice(0, 10);
const COMPANY = {name: 'Studio Beispiel', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', email: 'hallo@beispiel.example',
  phone: '+49 40 1234567', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const ADDR = {street: 'Marktweg 5', zip: '50667', city: 'Köln', country: 'DE'};
const ITEMS = {items: [{text: 'Tarif Studio', qty: 1, unit: 'flat', rate: '150.00'}], expect: {net: '150.00', tax: '28.50', gross: '178.50'}, service_from: TODAY, service_to: TODAY};

(async () => {
  fs.mkdirSync(path.join(DATA, 'mail', 'in'), {recursive: true});
  fs.copyFileSync(path.join(__dirname, 'stub_mail.py'), path.join(DATA, 'stub_mail.py'));
  execFileSync('docker', ['exec', '-d', CT, 'python', '/data/stub_mail.py']);
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call(ACK, 'POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(ACK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CK = await login('frida');
  await call(CK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  await call(CK, 'GET', '/api/office/settings');
  check((await call(CK, 'PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY})).http === 200, 'company data');
  const RG = (await call(CK, 'POST', '/api/office/num-ranges', {code: 'WEB', scheme: 'WEB-{yyyy}-{seq:03}'})).id;
  const iss = await call(CK, 'POST', '/api/office/issuers', {name: 'Shop', range_id: RG, password: 'password123'});
  check(iss.http === 201 && iss.key, 'an issuer with its key ' + iss.http);
  // clients by the key: three the person confirms, one new (its hold mark stays)
  const CL = {ok: ['shop:1', 'Musterkunde GmbH', 'rechnung@muster.example'], bad: ['shop:2', 'Abweis AG', 'refuse@abweis.example'], none: ['shop:3', 'Ohnepost KG', ''], fresh: ['shop:4', 'Neukunde OHG', 'buch@neu.example']};
  for (const [ref, name, mail] of Object.values(CL)) check((await key(iss.key, 'PUT', 'clients/by-ref/' + ref, {name, ...ADDR, ...(mail ? {email_invoice: mail} : {})})).http === 201, 'a client by the key ' + name);
  const draft = async (ref, cref, wish) => { const j = await key(iss.key, 'POST', 'invoices', {client_ref: ref, client: {external_ref: cref}, ...ITEMS, ...(wish ? {wish} : {})}); check(j.http === 201 && j.doc_id, 'a draft by the key ' + ref + ' ' + j.http + ' ' + JSON.stringify(j).slice(0, 160)); return j.doc_id; };
  const D = {ok: await draft('kauf:1', 'shop:1', {send: true, due_days: 14}), bad: await draft('kauf:2', 'shop:2', {send: true, due_days: 14}),
    none: await draft('kauf:3', 'shop:3', {send: true}), paid: await draft('kauf:4', 'shop:1', {send: true, paid: {amount: '178.50', date: TODAY, method: 'card', online_ref: 'tr_4'}}),
    nosend: await draft('kauf:5', 'shop:1', {send: false}), fresh: await draft('kauf:6', 'shop:4', {send: true})};
  // the person checks the client data of the first three (the hold mark goes, the drafts lose client_new)
  for (const k of ['ok', 'bad', 'none']) {
    const doc = await call(CK, 'GET', `/api/office/docs/${D[k]}`), rc = await call(CK, 'GET', `/api/office/docs/${D[k]}/recipients`);
    const at = rc.client_hold?.at;
    check(doc.client_id && at && (await call(CK, 'POST', `/api/clients/${doc.client_id}/issuer-hold`, {at})).http === 200, 'the person confirms the client data ' + k);
  }
  const own = await call(CK, 'POST', '/api/office/docs', {kind: 'invoice', lang: 'en', service_from: TODAY, service_to: TODAY, items: [{title: 'Schnitt', qty: 1, rate: 400}]});

  // ---- the list without the issuer filter: no button
  let w = await boot({user: 'frida', hash: 'office/invoices'}), d = w.document;
  check(await until(() => d.querySelector(`.ofdrow[data-id="${own.id}"]`), 60), 'the list');
  check(!d.querySelector('[data-ofd="iss-batch"]'), 'all ranges: no batch button');
  const sel = await until(() => d.querySelector('#ofd-src'), 40);
  if (sel) { sel.value = 'issuer:any'; sel.dispatchEvent(new w.Event('change', {bubbles: true})); }
  const btn = await until(() => !d.querySelector(`.ofdrow[data-id="${own.id}"]`) && d.querySelector('[data-ofd="iss-batch"]'), 60);
  check(!!btn && /Finalise and send all checked/.test(btn.textContent), 'from invoice issuers: the button "Finalise and send all checked"');
  check(mails('@') === 0 && (await call(CK, 'GET', `/api/office/docs/${D.ok}`)).status === 'draft', 'nothing happens before the person\'s click');
  click(w, btn);
  const md = await until(() => d.querySelector('.modal .ofdissb'), 80);
  check(!!md, 'the dialog lists the drafts');
  const rows = md ? [...md.querySelectorAll('li')].map(li => ({t: li.textContent.replace(/\s+/g, ' '), on: li.querySelector('input').checked, dis: li.querySelector('input').disabled})) : [];
  const row = re => rows.filter(x => re.test(x.t));
  check(rows.length === 6, 'six drafts of the issuer ' + rows.length);
  check(row(/Musterkunde/).filter(x => x.on && !x.dis).length === 1 && row(/Abweis/).every(x => x.on && !x.dis), 'ticked: the confirmed client with an address (once: its other drafts have a reason) and the one the server will refuse ' + JSON.stringify(rows));
  check(row(/Neukunde/).every(x => x.dis && !x.on && /New client/.test(x.t)), 'a new client: cannot be ticked, the reason named');
  check(row(/Ohnepost/).every(x => x.dis && /No e-mail address/.test(x.t)), 'no address: the reason named');
  check(rows.some(x => x.dis && /Payment statement/.test(x.t)) && rows.some(x => x.dis && /wished no sending/.test(x.t)), 'the issuer\'s payment statement and "no sending" stay for the person');
  check(/2 of 6 drafts can go/.test(d.querySelector('.modal')?.textContent || ''), 'the count: 2 of 6');
  click(w, d.querySelector('.modal [data-m="ok"]'));
  const res = await until(() => d.querySelector('.modal .ofdissr'), 200);
  const rt = res ? [...res.querySelectorAll('li')].map(li => li.dataset.st + ':' + li.textContent.replace(/\s+/g, ' ')) : [];
  check(rt.length === 2 && rt.some(x => /^sent:.*Musterkunde.*Sent as WEB-\d{4}-\d{3}/.test(x)) && rt.some(x => /^fin:.*Abweis.*Finalised, not sent/.test(x)), 'the result: sent with its number, the refused one finalised but not sent ' + JSON.stringify(rt));
  const g = async k => call(CK, 'GET', `/api/office/docs/${D[k]}`);
  const ok1 = await g('ok'), bad1 = await g('bad');
  check(ok1.status === 'sent' && /^WEB-/.test(ok1.number || '') && ok1.mail?.state === 'sent' && await until(() => mails('rechnung@muster.example') > 0, 60), 'the sent one: number of the issuer\'s range, sent, the mail in the stub ' + JSON.stringify({s: ok1.status, n: ok1.number, m: ok1.mail}));
  check(bad1.locked_at || bad1.number, 'the refused one: finalised (a number) ' + JSON.stringify({s: bad1.status, n: bad1.number}));
  check(bad1.status !== 'sent' && bad1.mail?.state === 'failed', 'the refused one: not sent, its mail state failed ' + JSON.stringify(bad1.mail));
  for (const k of ['none', 'paid', 'nosend', 'fresh']) { const x = await g(k); check(x.status === 'draft' && !x.number, 'stays a draft: ' + k); }
  check(!errs.length, 'no script errors ' + errs.join(' | '));
  w.close();

  console.log(`p7249_issuer_batch_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p7249_issuer_batch_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
