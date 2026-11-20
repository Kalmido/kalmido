// kalmido-suite: fresh
// #7509 UI: quick changes in the quotation editor are never lost on a slow line. Own container (start.sh), jsdom. Invented
// services and amounts only. Each answer of the editor's saves is held back by the test and let through one at a time.
// freelancer-matrix: office (the person without an organisation uses the same editor code)
// A. three changes A, B, C right after each other (quantities of three lines): A's answer comes while B waits in the row ->
//    B stays in the view (does not jump back); C is typed after it -> all three values are on the server and in the view
// B. a quantity typed and left (its save is on its way), "Add service" open, the answer comes, then a service is chosen ->
//    the new line is there (view and server)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const change = (w, el, v) => { if (!el) return; el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const svc = (title, qty, rate) => ({kind: 'service', title, qty, unit: 'day', rate, tax: 'standard', raw_fee: 0, producing: 0, intext: 'intern', cost: 0, discountable: 1});
// the answers of requests matching re are held one by one: w.__n = how many were asked, w.__go() lets the oldest held one through
function hold(w, re) {
  const f0 = w.fetch, q = []; let free = 0;  // free = answers let through before they arrived from the server
  w.__n = 0; w.__go = () => { const r = q.shift(); if (r) r(); else free++; };
  w.fetch = (u, o = {}) => {
    if (!re.test(String(u)) || (o.method || 'GET') === 'GET') return f0(u, o);
    w.__n++;
    return f0(u, o).then(r => new Promise(res => { if (free > 0) { free--; res(r); } else q.push(() => res(r)); }));  // the server has it; only the answer waits
  };
}
const qtyIn = (d, i) => d.querySelector(`.ofdeditor .ofdits [data-i="${i}"][data-k="qty"]`);
const num = v => +String(v).replace(',', '.');

async function run(user) {
  const tag = ` (${user})`;
  const sv = await call('POST', '/api/office/services', {name_de: 'Farbkorrektur', name_en: 'Grading', category: 'Post', unit: 'day', daily_rate: 700});
  check(sv.id > 0, 'a service ' + sv.status + tag);
  const doc = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Spot', items: [svc('Concept', 1, 800), svc('Shoot', 1, 1200), svc('Edit', 1, 600)]});
  check(doc.status === 201, 'a quotation ' + doc.status + tag);
  const w = await boot({user, hash: `office/offers/${doc.id}`}), d = w.document;
  check(await until(() => d.querySelectorAll('.ofdeditor .ofdits .ofdit').length >= 3), 'the editor shows three lines' + tag);
  hold(w, new RegExp(`/api/office/docs/${doc.id}(/items)?$`));

  // ================= A. A, B, C right after each other
  change(w, qtyIn(d, 0), '2');                       // A goes out
  check(await until(() => w.__n === 1), 'A: its save is on its way' + tag);
  change(w, qtyIn(d, 1), '3');                       // B waits in the row
  w.__go();                                          // A's answer
  check(await until(() => w.__n === 2), 'A: after A\'s answer B goes out' + tag);
  check(num(qtyIn(d, 1)?.value) === 3, `A: B stays in the view after A's answer (${qtyIn(d, 1)?.value})` + tag);
  change(w, qtyIn(d, 2), '5');                       // C, typed after A's answer, while B is on its way
  w.__go();                                          // B's answer
  check(await until(() => w.__n === 3), 'A: C goes out' + tag);
  check(num(qtyIn(d, 1)?.value) === 3 && num(qtyIn(d, 2)?.value) === 5, `A: B and C in the view while C is on its way (${qtyIn(d, 1)?.value}, ${qtyIn(d, 2)?.value})` + tag);
  w.__go();                                          // C's answer
  check(await until(() => w.eval('OFD.saving') === 0), 'A: the row is empty' + tag);
  let s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.map(x => num(x.qty)).join() === '2,3,5', 'A: all three values on the server: ' + s.items?.map(x => x.qty).join() + tag);
  check([0, 1, 2].map(i => num(qtyIn(d, i)?.value)).join() === '2,3,5', 'A: all three values in the view' + tag);
  check(!d.querySelector('.ofdcf') && w.eval('OFD.doc.updated_at') === s.updated_at, 'A: no conflict, the editor holds the current version' + tag);

  // ================= B. a service chosen while an answer comes
  change(w, qtyIn(d, 0), '4');                       // left the field: its save is on its way
  check(await until(() => w.__n === 4), 'B: the quantity\'s save is on its way' + tag);
  click(w, d.querySelector('.ofdeditor [data-ofd="it-svc"]'));
  const row = await until(() => d.querySelector(`.ofdpick [data-sid="${sv.id}"]`));
  check(!!row, 'B: the service picker shows the service' + tag);
  w.__go();                                          // the answer comes while the picker is open
  check(await until(() => w.eval('OFD.saving') === 0), 'B: the quantity is saved' + tag);
  click(w, d.querySelector(`.ofdpick [data-sid="${sv.id}"]`));
  check(await until(() => w.__n === 5), 'B: the new line is sent' + tag);
  w.__go();
  check(await until(() => w.eval('OFD.saving') === 0), 'B: saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.length === 4 && s.items[3].title === 'Grading' && num(s.items[0].qty) === 4, `B: the chosen service is on the server, the quantity too (${s.items?.map(x => x.title + ':' + x.qty).join()})` + tag);
  check(await until(() => d.querySelectorAll('.ofdeditor .ofdits .ofdit').length === 4 && d.querySelector('.ofdeditor .ofdits [data-i="3"][data-k="title"]')?.value === 'Grading'), 'B: the new line in the view' + tag);
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en'});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients'});
  { const me = (await call('GET', '/api/state')).me; const org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
    await call('PATCH', '/api/settings', {workspace: `org:${org.id}`}); }
  await run('alice');

  // ================= freelancer-matrix: office - the same editor as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida');

  console.log(`p7509_editor_kette_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
