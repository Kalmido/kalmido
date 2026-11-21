// kalmido-suite: fresh
// #7497 UI: bank bookings on the core's "write shows at once" (core.js rwRows, W.act) on a slow line. Own container (start.sh),
// jsdom. Invented bookings and receipts only. Every match / unmatch of a booking is held by the test (boot.js hold) and let
// through, refused or dropped one at a time.
// freelancer-matrix: office (the person without an organisation matches her bookings with the same list in her own office)
// A. three matches quickly in "Open" (the suggested receipt, "Private", "No receipt needed"): each row leaves the list at once,
//    the next row stays usable, no reload of the list; the counts come from the answers; on the server all three. A refused
//    match (500): the row is back where it was with "Not saved" and "Try again"; Try again saves it
// B. "All": an undo of a match stands at once with "Saving…"; refused = the row is back with its match and "Not saved";
//    Try again saves it
// C. "Without receipt": "No receipt needed" takes the row out at once (its number with it); refused = the row is back with
//    "Not saved"; Try again saves it
// D. the walk-through: a step shows the next booking at once while its write is held, the next step works at once (no
//    swallowed tap); a lost answer = the booking open again with "Not saved", taken again it saves
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
const TC = require('./testclock');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const FEAT = 'office,clients,docs';
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const upload = async (url, field, name, data, type, extra = {}) => { const fd = new FormData(); fd.append(field, new Blob([data], {type}), name); for (const [k, v] of Object.entries(extra)) fd.append(k, v);
  const r = await fetch(B + url.replace(/^\//, ''), {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const pdf = lines => {  // a PDF with a text layer, hand-written (as p2444_a_cards_ui.js)
  const stream = `BT /F1 10 Tf 12 TL 40 760 Td\n${lines.map(x => `(${x}) Tj T*`).join('\n')}\nET`;
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const x = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('')}trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${x}\n%%EOF\n`;
  return out;
};
const de = iso => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
const CP = ['Software Beispiel', 'Druckerei Muster', 'Bahn Beispiel', 'Kopierladen Muster', 'Blumen Beispiel', 'Kiosk Beispiel'];

async function run(user) {
  const tag = ` (${user})`, today = TC.today();
  const ws = (await call('GET', '/api/office/books')).upload_ws || 'private';
  const csv = `Buchungstag;Auftraggeber/Empfänger;Verwendungszweck;Betrag\n${de(today)};${CP[0]};Abo;-119,00\n${de(today)};${CP[1]};Flyer;-45,00\n${de(today)};${CP[2]};Ticket;-12,00\n${de(today)};${CP[3]};Kopien;-30,00\n${de(today)};${CP[4]};Strauss;-8,00\n${de(today)};${CP[5]};Zeitung;-3,00\n`;
  const pv = await call('POST', '/api/office/bank/import/preview', {text: csv});
  const mapping = {}; for (const k of ['date', 'amount', 'amount_in', 'amount_out', 'title', 'counterpart', 'decimal', 'date_format']) mapping[k] = pv.guess?.[k] ?? null;
  const imp = await call('POST', '/api/office/bank/import', {text: csv, filename: 'konto.csv', mapping});
  check(imp.status === 201 && imp.count === 6, 'six bookings imported ' + imp.status + tag);
  const rc = await upload('/api/docs', 'files', 'software-abo.pdf', pdf(['Rechnung Software']), 'application/pdf', {ws});
  const rid = (rc.ids || [])[0];
  check(!!rid, 'a receipt uploaded' + tag);
  await sleep(1200);
  await call('PATCH', `/api/docs/${rid}`, {amount: '119.00', date: today, name: 'software-abo'});
  await call('PUT', `/api/docs/${rid}/receipt`, {category: 'Software', vat_pct: '19'});
  const all = async () => (await call('GET', '/api/office/bank/tx?state=all')).items || [];
  const T0 = await all(), tid = n => T0.find(x => x.counterpart === n)?.id;
  check(T0.length === 6, 'six bookings' + tag);

  const w = await boot({user, hash: 'office/bank'}), d = w.document;
  const row = n => d.querySelector(`.bnklist [data-rwk="i${tid(n)}"]`);
  check(await until(() => row(CP[0])?.querySelector('.bnksug [data-bnk="match"]')), 'the list with the suggested receipt' + tag);
  const gets = []; { const f1 = w.fetch; w.fetch = (u, o = {}) => { if ((o.method || 'GET') === 'GET' && /\/api\/office\/bank\/(tx|noreceipt)(\?|$)/.test(String(u))) gets.push(String(u)); return f1(u, o); }; }
  hold(w, /\/api\/office\/bank\/tx\/\d+\/(match|unmatch)$/);
  const busy = () => w.eval("typeof BNK_W === 'object' && !!BNK_W && BNK_W.pend > 0");
  const idle = () => until(() => !busy());
  const tagOf = n => row(n)?.querySelector('.rotag')?.textContent.trim() || '';
  const openN = () => d.querySelector('.bnkbar [data-bnk="state"][data-v="open"] small')?.textContent || '';
  const noBlock = () => !d.querySelector('.dash.office .loading.big');
  const by = (L, n) => L.find(x => x.counterpart === n);

  // ================= A. three matches at once in "Open", no reload
  click(w, row(CP[0])?.querySelector('.bnksug [data-bnk="match"]'));
  check(!row(CP[0]), 'A: the receipt\'s booking leaves the open list at once' + tag);
  w.eval(`bnkMatch(${tid(CP[1])}, 'private')`);  // "More" > "Private" (bnkMoreMenu)
  w.eval(`bnkMatch(${tid(CP[2])}, 'noreceipt')`);
  check(!row(CP[1]) && !row(CP[2]), 'A: "Private" and "No receipt needed" at once too' + tag);
  check(noBlock() && !!row(CP[3])?.querySelector('[data-bnk="more"]'), 'A: no loading block, the next row stays usable' + tag);
  check(await until(() => w.__q.length === 1) && w.__n === 1, `A: one write on its way, the others wait behind it (${w.__n})` + tag);
  for (let t = 0; t < 200 && (busy() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(30); }
  check(await idle(), 'A: all three saved' + tag);
  check(w.__n === 3, `A: three writes (${w.__n})` + tag);
  check(gets.length === 0, 'A: no reload of the list: ' + gets.join(' ') + tag);
  check(openN() === '3', 'A: the count of open bookings from the answers: ' + openN() + tag);
  let L = await all();
  check(by(L, CP[0])?.match?.kind === 'receipt' && by(L, CP[0])?.match?.id === rid && by(L, CP[1])?.match?.kind === 'private' && by(L, CP[2])?.match?.kind === 'noreceipt', 'A: on the server ' + L.map(x => x.match?.kind || '-').join() + tag);
  // a refused match: the row is back where it was
  const at = () => [...d.querySelectorAll('.bnklist [data-rwk]')].map(r => r.dataset.rwk).indexOf(`i${tid(CP[3])}`), at0 = at();
  w.eval(`bnkMatch(${tid(CP[3])}, 'private')`);
  check(!row(CP[3]), 'A: the fourth one leaves at once' + tag);
  check(await until(() => w.__q.length === 1), 'A: its write is on its way' + tag);
  w.__fail(500);
  check(await until(() => row(CP[3])?.classList.contains('rw-failed')), 'A: refused: the row is back with "Not saved"' + tag);
  check(at() === at0 && /Not saved/.test(row(CP[3])?.querySelector('.rwfail')?.textContent || '') && !!row(CP[3])?.querySelector('[data-rwagain]') && !!row(CP[3])?.querySelector('[data-bnk="more"]'), `A: where it was (${at0} -> ${at()}), open, with the reason and "Try again"` + tag);
  check(openN() === '3', 'A: the count unchanged: ' + openN() + tag);
  click(w, row(CP[3])?.querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1) && !row(CP[3]), 'A: Try again takes it out again and sends it' + tag);
  w.__go(); check(await idle(), 'A: saved' + tag);
  check(openN() === '2', 'A: the count from the answer: ' + openN() + tag);
  L = await all(); check(by(L, CP[3])?.match?.kind === 'private', 'A: on the server: ' + by(L, CP[3])?.match?.kind + tag);

  // ================= B. "All": a refused undo of a match, the row is back with "Not saved"
  click(w, d.querySelector('.bnkbar [data-bnk="state"][data-v="all"]'));
  check(await until(() => row(CP[1])?.querySelector('[data-bnk="unmatch"]')), 'B: all bookings' + tag);
  await sleep(300); const gb = gets.length;
  click(w, row(CP[1])?.querySelector('[data-bnk="unmatch"]'));
  check(!row(CP[1])?.querySelector('[data-bnk="unmatch"]') && !!row(CP[1])?.querySelector('[data-bnk="more"]') && row(CP[1])?.classList.contains('rw-saving'), 'B: open again at once, "Saving…"' + tag);
  check(await until(() => w.__q.length === 1), 'B: its write is on its way' + tag);
  w.__fail(500);
  check(await until(() => row(CP[1])?.classList.contains('rw-failed')), 'B: refused: the row says "Not saved"' + tag);
  check(/Private/.test(tagOf(CP[1])) && /Not saved/.test(row(CP[1])?.querySelector('.rwfail')?.textContent || '') && !!row(CP[1])?.querySelector('[data-rwagain]'), 'B: back with its match, the reason and "Try again": ' + row(CP[1])?.textContent.replace(/\s+/g, ' ').slice(0, 160) + tag);
  click(w, row(CP[1])?.querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1) && row(CP[1])?.classList.contains('rw-saving'), 'B: Try again sends it' + tag);
  w.__go(); check(await idle(), 'B: saved' + tag);
  check(await until(() => !row(CP[1])?.querySelector('.rwmark') && !!row(CP[1])?.querySelector('[data-bnk="more"]')), 'B: open, no mark' + tag);
  check(openN() === '3', 'B: the count from the answer: ' + openN() + tag);
  L = await all(); check(!by(L, CP[1])?.match, 'B: open on the server' + tag);
  check(gets.length === gb, 'B: no reload: ' + gets.slice(gb).join(' ') + tag);

  // ================= C. "Without receipt": the row leaves at once
  click(w, d.querySelector('.bnkbar [data-bnk="state"][data-v="norc"]'));
  const nrow = n => d.querySelector(`.bnklist [data-tx="${tid(n)}"]`);
  check(await until(() => nrow(CP[4])?.querySelector('[data-bnr="noreceipt"]')), 'C: the bookings without a receipt' + tag);
  const outN = () => d.querySelector('.bnrbar [data-bnr="dir"][data-v="out"] small')?.textContent || '';
  const n0 = +outN(), g0 = gets.length;
  click(w, nrow(CP[4])?.querySelector('[data-bnr="noreceipt"]'));
  check(!nrow(CP[4]) && +outN() === n0 - 1, `C: the row is gone at once, its number with it (${n0} -> ${outN()})` + tag);
  check(await until(() => w.__q.length === 1), 'C: its write is on its way' + tag);
  w.__fail(500);
  check(await until(() => nrow(CP[4])?.classList.contains('rw-failed')), 'C: refused: the row is back with "Not saved"' + tag);
  check(+outN() === n0 && !!nrow(CP[4])?.querySelector('[data-rwagain]'), 'C: its number back, "Try again" at the row' + tag);
  click(w, nrow(CP[4])?.querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1) && !nrow(CP[4]), 'C: Try again takes it out again and sends it' + tag);
  w.__go(); check(await idle(), 'C: saved' + tag);
  L = await all(); check(by(L, CP[4])?.match?.kind === 'noreceipt', 'C: on the server: ' + by(L, CP[4])?.match?.kind + tag);
  check(gets.length === g0, 'C: no reload of the list: ' + gets.slice(g0).join(' ') + tag);

  // ================= D. the walk-through: the next one at once, nothing swallowed, a lost answer said
  click(w, d.querySelector('.bnkbar [data-bnk="state"][data-v="open"]'));
  w.eval("wlk_open('bnk')");
  check(await until(() => w.eval("typeof WLK === 'object' && !!WLK.md && WLK.items.length === 2")), 'D: the walk-through with the two open bookings' + tag);
  const wn = () => d.querySelector('.wlkdlg [data-wlk-n]')?.textContent.trim() || '';
  const g1 = gets.length;
  check(await until(() => wn() === '1 of 2'), 'D: 1 of 2: ' + wn() + tag);
  w.eval("wlk_mark('private')");
  check(wn() === '2 of 2', 'D: the next booking at once, its write held: ' + wn() + tag);
  check(await until(() => w.__q.length === 1), 'D: the first step\'s write is on its way' + tag);
  w.eval("wlk_mark('noreceipt')");
  check(!!d.querySelector('.wlkdlg .wlk-end'), 'D: the next step works at once (the end view), nothing swallowed' + tag);
  w.__go();
  check(await until(() => w.__q.length === 1), 'D: the second step\'s write' + tag);
  w.__drop();
  check(await until(() => !busy()), 'D: nothing waits after the lost answer' + tag);
  w.eval('wlk_go(-1)');
  check(await until(() => wn() === '2 of 2' && !!d.querySelector('.wlkdlg .wlk-fail')), 'D: the booking of the lost answer is open again and says "Not saved"' + tag);
  w.eval("wlk_mark('noreceipt')");
  check(await until(() => w.__q.length === 1), 'D: taken again' + tag);
  w.__go(); check(await idle(), 'D: saved' + tag);
  L = await all();
  check(L.every(x => x.match) && by(L, CP[5])?.match?.kind === 'private' && by(L, CP[1])?.match?.kind === 'noreceipt', 'D: on the server ' + L.map(x => x.counterpart.split(' ')[0] + ':' + (x.match?.kind || '-')).join() + tag);
  check(gets.length === g1, 'D: no reload behind the walk-through: ' + gets.slice(g1).join(' ') + tag);
  w.eval('WLK.md?.remove()');
  w.__off();
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en'});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call('GET', '/api/state')).me, org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call('PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await run('alice');

  // ================= freelancer-matrix: office - the same bank list as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida');

  console.log(`p7497_bank_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
