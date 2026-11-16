// kalmido-suite: fresh
// 2.1302.0 (#6532) UI test: the first real invoice of an office, own container (start.sh; KMT_NOSTART=1: a running server),
// jsdom. Invented companies and figures only.
// - the server: GET /api/office/docs/<id>/number-preview says first while the office has finalised no real invoice (a finalised
//   trial invoice, #3445, does not count; a quotation never is first); GET /api/office/number-ranges says first_invoice
// - "Finalise" on the first invoice: the dialog adds "Your first invoice. It can no longer be deleted afterwards, only
//   corrected." with the ways Test mode and Numbers; each closes the question (nothing finalised) and opens the office settings
//   at its section (#tri-h / #onum-box); there an empty invoice series prefills the reason of a jump
// - "Download" on the draft: the main button (focus, the form's only submit button = Enter) is "Show as draft"; Enter
//   downloads the draft and finalises nothing; "Finalise now" is the plain middle button; the first line shows there too
// - the second invoice: no extra line (finalise and download dialog), the preview says first false
// freelancer-matrix: office (frida has no organisation: her personal office)
// usage: node p21302_b_first_invoice_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients';
const COMPANY = {name: 'Studio Beispiel GmbH', street: 'Hafenweg 1', zip: '20457', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', vat_id: 'DE999999999', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'};
const FIRST = 'Your first invoice. It can no longer be deleted afterwards, only corrected.';

async function editor(user, id) {
  const w = await boot({user, hash: `office/invoices/${id}`}), d = w.document;
  await until(() => d.querySelector('[data-ofd="finalize"]'), 60);
  w.__dialogs = 'manual';  // the dialogs are driven here (the bridge of boot.js would answer them)
  w.__dl = []; w.ofdPdfOpen = (doc, dl) => { w.__dl.push({id: doc.id, dl: !!dl, locked: !!doc.locked}); };  // jsdom opens no PDF
  return [w, d];
}
const cdlg = d => d.querySelector('.modal.cdlg');

async function run(user, ck, tag) {
  await call('GET', '/api/office/settings', null, ck);
  await call('PUT', '/api/office/settings', {lang: 'en', company_fields: COMPANY}, ck);
  const CL = (await call('POST', '/api/clients', {name: 'Beispielkunde AG', street: 'Marktstraße 5', zip: '50667', city: 'Köln', country: 'DE'}, ck)).id;
  const mk = (b = {}) => call('POST', '/api/office/docs', {kind: 'invoice', client_id: CL, service_from: '2026-05-01', service_to: '2026-05-31', items: [{title: 'Schnitt', qty: 1, rate: 900}], ...b}, ck);
  // a finalised trial invoice does not count
  const tri = await mk({trial: true});
  const tf = await call('POST', `/api/office/docs/${tri.id}/finalize`, {}, ck);
  check(tri.http === 201 && tf.http === 200, `${tag}: a trial invoice finalised ` + [tri.http, tf.http]);
  const inv = await mk(), inv2 = await mk();
  const q = await call('POST', '/api/office/docs', {client_id: CL, project_title: 'Imagefilm', items: [{title: 'Konzept', qty: 1, rate: 800}]}, ck);
  const pv = await call('GET', `/api/office/docs/${inv.id}/number-preview`, null, ck);
  check(pv.http === 200 && pv.first === true, `${tag}: the preview of the first real invoice says first ` + JSON.stringify(pv));
  check((await call('GET', `/api/office/docs/${q.id}/number-preview`, null, ck)).first === false, `${tag}: a quotation is never first`);
  check((await call('GET', `/api/office/docs/${tri.id}/number-preview`, null, ck)).first === false, `${tag}: a trial invoice is never first`);
  check((await call('GET', '/api/office/number-ranges', null, ck)).first_invoice === true, `${tag}: the number ranges say first_invoice`);

  // ---- Finalise: the extra line, the way to the test mode
  let [w, d] = await editor(user, inv.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  let m = await until(() => cdlg(d)?.querySelector('.ofdfirst') && cdlg(d), 40);
  check(m && m.textContent.includes(FIRST) && /Try it out first\?/.test(m.textContent) && /Will be finalised as/.test(m.textContent),
    `${tag}: the finalise dialog adds the first-invoice line ` + (m?.textContent || '').replace(/\s+/g, ' ').slice(0, 300));
  const trialB = m?.querySelector('[data-first="trial"]'), numB = m?.querySelector('[data-first="numbers"]');
  check(trialB && trialB.tagName === 'BUTTON' && /Test mode/.test(trialB.textContent) && numB && /Numbers/.test(numB.textContent), `${tag}: the ways Test mode and Numbers are buttons`);
  check(m?.querySelector('[data-cd="yes"]')?.textContent.trim() === 'Finalise', `${tag}: the main button keeps its verb`);
  click(w, trialB);
  check(await until(() => !cdlg(d), 30), `${tag}: Test mode closes the question`);
  check(await until(() => d.querySelector('#tri-h'), 60), `${tag}: Test mode opens the office settings at the test mode`);
  check(await until(() => d.querySelector('#tri-mode'), 30), `${tag}: the switch of the test mode is there`);
  check((await call('GET', `/api/office/docs/${inv.id}`, null, ck)).locked === false, `${tag}: Test mode finalised nothing`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- the way to the number ranges: the empty invoice series prefills the reason
  [w, d] = await editor(user, inv.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => cdlg(d)?.querySelector('[data-first="numbers"]') && cdlg(d), 40);
  click(w, m?.querySelector('[data-first="numbers"]'));
  check(await until(() => !cdlg(d), 30), `${tag}: Numbers closes the question`);
  const inp = await until(() => d.querySelector('#onum-box #onum-invoice'), 60);
  check(inp, `${tag}: Numbers opens the office settings at the next running numbers`);
  if (inp) {
    inp.value = '673'; inp.dispatchEvent(new w.Event('input', {bubbles: true}));
    const why = await until(() => d.querySelector('#onum-invoice-why'), 30);
    check(why && why.value === 'Taken over from the previous program', `${tag}: a jump in the empty invoice series prefills the reason: ` + why?.value);
  }
  check((await call('GET', `/api/office/docs/${inv.id}`, null, ck)).locked === false, `${tag}: Numbers finalised nothing`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- Download on the draft: "Show as draft" is the main button, Enter never finalises
  [w, d] = await editor(user, inv.id);
  click(w, d.querySelector('.ofdhead .ofddl'));
  m = await until(() => d.querySelector('.modal.ofdpa'), 40);
  const yes = m?.querySelector('[data-cd="yes"]'), fin = m?.querySelector('[data-pa="final"]');
  check(yes && yes.textContent.trim() === 'Show as draft' && yes.matches('.pri') && yes.type === 'submit', `${tag}: the download's main button is Show as draft ` + yes?.outerHTML);
  check(fin && fin.textContent.trim() === 'Finalise now' && fin.type === 'button' && !fin.matches('.pri') && m.querySelectorAll('button[type="submit"]').length === 1, `${tag}: Finalise now is a plain button, the only submit button is the draft`);
  check(await until(() => d.activeElement === yes, 20), `${tag}: the focus is on Show as draft`);
  check(m?.textContent.includes(FIRST), `${tag}: the download question names the first invoice too`);
  m.querySelector('form').dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));  // Enter = the form's submission
  check(await until(() => w.__dl.length, 30) && w.__dl[0].dl && !w.__dl[0].locked, `${tag}: Enter downloads the draft ` + JSON.stringify(w.__dl));
  await sleep(300);
  check((await call('GET', `/api/office/docs/${inv.id}`, null, ck)).locked === false, `${tag}: Enter finalised nothing`);
  // Finalise now (the deliberate click) finalises, then the PDF
  click(w, d.querySelector('.ofdhead .ofddl'));
  click(w, await until(() => d.querySelector('.modal.ofdpa [data-pa="final"]'), 40));
  const srv = await until(async () => { const j = await call('GET', `/api/office/docs/${inv.id}`, null, ck); return j.locked && j; }, 60);
  check(srv && /\d/.test(srv.number || ''), `${tag}: Finalise now finalises ` + srv?.number);
  check(await until(() => w.__dl.length === 2, 30) && w.__dl[1].locked, `${tag}: then the finalised PDF downloads`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();

  // ---- the second invoice: no extra line
  check((await call('GET', `/api/office/docs/${inv2.id}/number-preview`, null, ck)).first === false, `${tag}: the second invoice is not first`);
  check((await call('GET', '/api/office/number-ranges', null, ck)).first_invoice === false, `${tag}: the number ranges no longer say first_invoice`);
  [w, d] = await editor(user, inv2.id);
  click(w, d.querySelector('[data-ofd="finalize"]'));
  m = await until(() => cdlg(d), 40);
  await sleep(200);
  check(m && /Finalise this document/.test(m.textContent) && !m.querySelector('.ofdfirst') && !m.textContent.includes(FIRST), `${tag}: the second invoice's dialog has no first-invoice line`);
  click(w, m?.querySelector('[data-cd="no"]'));
  await until(() => !cdlg(d), 30);
  click(w, d.querySelector('.ofdhead .ofddl'));
  m = await until(() => d.querySelector('.modal.ofdpa'), 40);
  check(m && !m.querySelector('.ofdfirst'), `${tag}: the second invoice's download question has no first-invoice line`);
  click(w, m?.querySelector('[data-cd="no"]'));
  await until(() => !d.querySelector('.modal.ofdpa'), 30);
  check((await call('GET', `/api/office/docs/${inv2.id}`, null, ck)).locked === false, `${tag}: Cancel finalised nothing`);
  check(!errs.length, `${tag}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await run('alice', CK, 'org');

  // freelancer-matrix: office (a person without an organisation, her own admin)
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const FCK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, FCK);
  await run('frida', FCK, 'freelancer');

  console.log(`p21302_b_first_invoice_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); console.log(`p21302_b_first_invoice_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
