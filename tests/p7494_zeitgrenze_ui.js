// kalmido-suite: fresh
// #7494 UI: no request hangs without a word (the shared time limit of rawFetch). Own container (start.sh), jsdom. Invented
// services and amounts only. The test shortens the limits (NET_T) and holds answers back on purpose (the window's fetch waits).
// freelancer-matrix: office (the person without an organisation uses the same core)
// 1. a write through api() without an answer: after the limit "Not saved: no answer" with "Try again" (said once, the caller
//    hears an error with status 408); the request carried an idempotency key; Try again sends the same key -> "Saved", the
//    service exists exactly once on the server
// 2. the quotation editor: a position saved without an answer -> the same hint; Try again goes through the editor's row ->
//    the value on the server, and the next change saves without a false conflict
// 3. a read without an answer: tried a second time without a word, then the error block with "Try again"; that loads it
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
// requests of method m to URLs matching re: the first n answers never come (the server gets the request, the answer is lost on
// the line); w.__seen = [{key}] of every matching request
function lose(w, m, re, n = 1) {
  const f0 = w.fetch; let left = n;
  w.__seen = [];
  w.fetch = (u, o = {}) => {
    if (!re.test(String(u)) || (o.method || 'GET') !== m) return f0(u, o);
    w.__seen.push({key: (o.headers || {})['Idempotency-Key'] || ''});
    const p = f0(u, o);
    if (left > 0) { left--; p.catch(() => {}); return new Promise(() => {}); }
    return p;
  };
}
const toastTxt = d => { const t = d.querySelector('#toast'); return t && !t.classList.contains('hidden') ? t.textContent : ''; };
const toastBtn = d => d.querySelector('#toast:not(.hidden) button:not(.tx)');

async function run(user) {
  const tag = ` (${user})`;
  // ================= 1. a write through api() without an answer
  let w = await boot({user, hash: 'office/offers'}), d = w.document;
  check(await until(() => d.querySelector('.office .ofcbody')), '1: the office is drawn' + tag);
  w.eval('NET_T.w = 400; NET_T.r = 300');
  lose(w, 'POST', /\/api\/office\/services$/);
  w.eval(`window.__r = api('POST', '/api/office/services', {name_de: 'Schnittplatz', name_en: 'Edit suite', daily_rate: 300}).then(() => 'ok', e => e)`);
  check(await until(() => /no answer/i.test(toastTxt(d)) && toastBtn(d)), '1: after the limit the hint with "Try again": ' + toastTxt(d) + tag);
  check(/not saved/i.test(toastTxt(d)), '1: it says not saved' + tag);
  const e1 = await w.eval('window.__r');
  check(e1 && e1.status === 408 && w.eval('window.__r.then(e => e instanceof NoAnswer && !(e instanceof Offline))'), '1: the caller hears NoAnswer (408), not Offline' + tag);
  check(w.__seen.length === 1 && /^[A-Za-z0-9_.:-]{6,}$/.test(w.__seen[0].key), '1: the write carried an idempotency key: ' + JSON.stringify(w.__seen) + tag);
  check(await until(async () => ((await call('GET', '/api/office/services')).items || []).some(s => s.name_en === 'Edit suite')), '1: the server got the first try' + tag);
  click(w, toastBtn(d));
  check(await until(() => /Saved/.test(toastTxt(d))), '1: Try again -> Saved: ' + toastTxt(d) + tag);
  check(w.__seen.length === 2 && w.__seen[1].key === w.__seen[0].key, '1: Try again sent the same key' + tag);
  const n1 = ((await call('GET', '/api/office/services')).items || []).filter(s => s.name_en === 'Edit suite').length;
  check(n1 === 1, '1: the service exists exactly once: ' + n1 + tag);
  w.close();

  // ================= 2. the quotation editor
  const doc = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Spot', items: [svc('Concept', 1, 800), svc('Shoot', 1, 1200)]});
  check(doc.status === 201, '2: a quotation ' + doc.status + tag);
  w = await boot({user, hash: `office/offers/${doc.id}`}); d = w.document;
  const qty = i => d.querySelector(`.ofdeditor .ofdits [data-i="${i}"][data-k="qty"]`);
  check(await until(() => qty(1)), '2: the editor shows the lines' + tag);
  w.eval('NET_T.w = 400');
  lose(w, 'PUT', new RegExp(`/api/office/docs/${doc.id}/items$`));
  change(w, qty(0), '3');
  check(await until(() => /no answer/i.test(toastTxt(d)) && toastBtn(d)), '2: the hint with "Try again": ' + toastTxt(d) + tag);
  check(await until(() => w.eval('OFD.saving') === 0), '2: the editor does not hang ("Saving…" ends)' + tag);
  click(w, toastBtn(d));
  check(await until(() => /Saved/.test(toastTxt(d))), '2: Try again -> Saved' + tag);
  check(w.__seen.length === 2 && w.__seen[1].key && w.__seen[1].key === w.__seen[0].key, '2: the same key' + tag);
  let s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 3 && s.items.length === 2, '2: the quantity on the server, no line twice' + tag);
  check(await until(() => w.eval('OFD.saving') === 0 && w.eval('OFD.doc.updated_at') === s.updated_at), '2: the editor holds the current version' + tag);
  change(w, qty(1), '2');
  s = await until(async () => { const x = await call('GET', `/api/office/docs/${doc.id}`); return +x.items?.[1]?.qty === 2 ? x : null; });
  check(s && +s.items[0].qty === 3 && !d.querySelector('.ofdcf'), '2: the next change saves, no false conflict' + tag);
  w.close();

  // ================= 3. a read without an answer
  w = await boot({user, hash: 'office/offers'}); d = w.document;
  check(await until(() => d.querySelector('.office .ofcbody')), '3: the office is drawn' + tag);
  w.eval('NET_T.r = 300');
  lose(w, 'GET', new RegExp(`/api/(office/docs|fsref/office_doc)/${doc.id}$`), 2);
  w.location.hash = `#office/offers/${doc.id}`;
  check(await until(() => d.querySelector('#view .eerr [data-esretry]')), '3: the error block with "Try again"' + tag);
  check(w.__seen.length === 2, '3: tried twice (one silent second try), no way round through a folder: ' + w.__seen.length + tag);
  check(!d.querySelector('#view .ofdeditor'), '3: no editor without the document' + tag);
  click(w, d.querySelector('#view .eerr [data-esretry]'));
  check(await until(() => qty(1)), '3: Try again loads the document' + tag);
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

  // ================= freelancer-matrix: office - the same core as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida');

  console.log(`p7494_zeitgrenze_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
