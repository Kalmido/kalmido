// kalmido-suite: fresh
// #7499 UI: credit card positions on the core's "write shows at once" (core.js rwRows, W.act) on a slow line. Own container
// (start.sh), jsdom. Invented statement, merchants and receipts only. Every write of a position is held by the test (boot.js hold)
// and let through, refused or dropped one at a time.
// freelancer-matrix: office (the person without an organisation uses the same card sheet in her own office)
// A. three positions answered quickly ("No receipt needed", "Private", the suggested receipt): each stands at once in its new
//    state and says "Saving…", no loading block, no reload of the cards or the statement; on the server all three
// B. a refused write (500): the position is back as it was, says "Not saved" with "Try again"; Try again saves it
// C. no connection: the same; Try again saves it
// D. the walk-through: a step shows the next position at once while its write is held, the next step works at once (no
//    swallowed tap); a refused step = the position open again with "Not saved"
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
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
const MER = ['Cafe Beispiel', 'Buchladen Muster', 'Bahn Beispiel', 'Kopierladen Muster', 'Blumen Beispiel'];

async function run(user, ws) {
  const tag = ` (${user})`;
  const me = (await call('GET', '/api/state')).me;
  const card = await call('POST', '/api/office/cards', {holder_id: me.id, last4: '4711'});
  check(card.id > 0, 'a card ' + card.status + tag);
  const st = await upload(`/api/office/cards/${card.id}/statements`, 'file', 'abrechnung.pdf', pdf(['Abrechnung vom 15.01.2025', 'Karte 5232 12XX XXXX 4711',
    '03.01. 04.01. Cafe Beispiel Berlin 12,50-', '05.01. 05.01. Buchladen Muster 20,00-', '06.01. 06.01. Bahn Beispiel 30,00-', '07.01. 07.01. Kopierladen Muster 7,50-',
    '08.01. 08.01. Blumen Beispiel 9,00-', 'Neuer Saldo 79,00-']), 'application/pdf');
  check(st.status === 201 && st.read, 'the statement read ' + st.status + tag);
  const sid = st.statement?.id;
  const cf = await call('POST', `/api/office/cards/statements/${sid}/confirm`, {accept_diff: true});
  check(cf.status === 200, 'the positions confirmed ' + cf.status + tag);
  const rc = await upload('/api/docs', 'files', 'cafe-beispiel.pdf', pdf(['Rechnung Cafe']), 'application/pdf', {ws});
  const rid = (rc.ids || [])[0];
  check(!!rid, 'a receipt uploaded' + tag);
  await sleep(1200);
  await call('PATCH', `/api/docs/${rid}`, {amount: '12.50', date: '2025-01-03'});
  const lines = async () => (await call('GET', `/api/office/cards/statements/${sid}`)).lines || [];
  const L0 = await lines(), lid = n => L0.find(x => x.merchant.startsWith(n))?.id;
  check(L0.length === 5 && L0.every(x => x.state === 'open'), 'five open positions ' + L0.map(x => x.merchant + ':' + x.state).join() + tag);

  const w = await boot({user, hash: 'office/cards'}), d = w.document;
  check(await until(() => d.querySelector('[data-cc="card"]')), 'the cards' + tag);
  click(w, d.querySelector(`[data-cc="card"][data-id="${card.id}"]`));
  check(await until(() => d.querySelector(`[data-cc="stmt"][data-id="${sid}"]`)), 'the card\'s statements' + tag);
  click(w, d.querySelector(`[data-cc="stmt"][data-id="${sid}"]`));
  const row = n => d.querySelector(`.ccl [data-rwk="i${lid(n)}"]`);
  check(await until(() => row(MER[0])?.querySelector('.ccsug [data-cc="match"]')), 'the sheet with the suggested receipt' + tag);
  // every GET of the cards / statements from here on (a reload after a click is what #7499 takes away)
  const gets = []; { const f1 = w.fetch; w.fetch = (u, o = {}) => { if ((o.method || 'GET') === 'GET' && /\/api\/office\/cards(\?|$|\/\d+\/statements|\/statements\/\d+(\?|$))/.test(String(u))) gets.push(String(u)); return f1(u, o); }; }
  hold(w, /\/api\/office\/cards\/lines\/\d+(\/(match|unmatch|upload))?$/);
  const busy = () => w.eval("typeof CC_W === 'object' && !!CC_W && CC_W.pend > 0");
  const idle = () => until(() => !busy());
  const tagOf = n => row(n)?.querySelector('.rotag')?.textContent.trim() || '';
  const noBlock = () => !d.querySelector('.dash.office .ofcbody > .loading, .dash.office .loading.big');

  // ================= A. three answers at once, no reload
  click(w, row(MER[1])?.querySelector('[data-cc="mark"][data-v="noreceipt"]'));
  check(/No receipt needed/.test(tagOf(MER[1])) && row(MER[1])?.classList.contains('rw-saving'), 'A: "No receipt needed" stands at once and says "Saving…": ' + tagOf(MER[1]) + tag);
  click(w, row(MER[2])?.querySelector('[data-cc="mark"][data-v="private"]'));
  check(/Private/.test(tagOf(MER[2])) && row(MER[2])?.classList.contains('rw-saving'), 'A: "Private" stands at once: ' + tagOf(MER[2]) + tag);
  click(w, row(MER[0])?.querySelector('.ccsug [data-cc="match"]'));
  check(/cafe-beispiel/.test(tagOf(MER[0])) && !!row(MER[0])?.querySelector('[data-cc="unmatch"]') && row(MER[0])?.classList.contains('rw-saving'), 'A: the receipt is matched at once: ' + tagOf(MER[0]) + tag);
  check(noBlock(), 'A: no loading block' + tag);
  check(await until(() => w.__q.length === 1) && w.__n === 1, `A: one write on its way, the others wait behind it (${w.__n})` + tag);
  for (let t = 0; t < 200 && (busy() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(30); }
  check(await idle(), 'A: all three saved' + tag);
  check(w.__n === 3, `A: three writes (${w.__n})` + tag);
  check(await until(() => !d.querySelector('.ccl .rwmark')), 'A: no mark after the answers' + tag);
  check(gets.length === 0, 'A: no reload of the cards or the statement: ' + gets.join(' ') + tag);
  check(noBlock() && !!row(MER[3])?.querySelector('[data-cc="mark"]'), 'A: the sheet stays usable' + tag);
  let L = await lines();
  const by = n => L.find(x => x.merchant.startsWith(n));
  check(by(MER[0])?.state === 'matched' && by(MER[0])?.node_id === rid && by(MER[1])?.state === 'noreceipt' && by(MER[2])?.state === 'private', 'A: on the server ' + L.map(x => x.state).join() + tag);
  check(+w.eval('CC.sheet.statement.private') === 30, 'A: the statement\'s figures from the answer (holder pays back 30): ' + w.eval('CC.sheet.statement.private') + tag);

  // ================= B. a refused write: the position comes back with "Not saved"
  click(w, row(MER[2])?.querySelector('[data-cc="mark"][data-v="open"]'));
  check(!!row(MER[2])?.querySelector('[data-cc="mark"][data-v="private"]'), 'B: "Needs a receipt" stands at once (the open position)' + tag);
  check(await until(() => w.__q.length === 1), 'B: its write is on its way' + tag);
  w.__fail(500);
  check(await until(() => row(MER[2])?.classList.contains('rw-failed')), 'B: refused: the position says "Not saved"' + tag);
  check(/Private/.test(tagOf(MER[2])) && /Not saved/.test(row(MER[2])?.querySelector('.rwfail')?.textContent || ''), 'B: the position is back as it was, with the reason: ' + row(MER[2])?.textContent.replace(/\s+/g, ' ').slice(0, 160) + tag);
  click(w, row(MER[2])?.querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1) && row(MER[2])?.classList.contains('rw-saving'), 'B: Try again sends it, the position open at once' + tag);
  w.__go(); check(await idle(), 'B: saved' + tag);
  check(await until(() => !row(MER[2])?.querySelector('.rwmark') && !!row(MER[2])?.querySelector('[data-cc="mark"][data-v="private"]')), 'B: open, no mark' + tag);
  L = await lines(); check(by(MER[2])?.state === 'open', 'B: open on the server: ' + by(MER[2])?.state + tag);

  // ================= C. no connection
  click(w, row(MER[0])?.querySelector('[data-cc="unmatch"]'));
  check(await until(() => w.__q.length === 1), 'C: the undo of the match is on its way' + tag);
  w.__drop();
  check(await until(() => row(MER[0])?.classList.contains('rw-failed')), 'C: no connection: the position says "Not saved"' + tag);
  check(/cafe-beispiel/.test(tagOf(MER[0])), 'C: still matched as on the server' + tag);
  click(w, row(MER[0])?.querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'C: Try again sends it' + tag);
  w.__go(); check(await idle(), 'C: saved' + tag);
  L = await lines(); check(by(MER[0])?.state === 'open', 'C: open on the server: ' + by(MER[0])?.state + tag);
  check(await until(() => !row(MER[0])?.querySelector('.rwmark')), 'C: no mark' + tag);
  check(gets.length === 0, 'C: still no reload: ' + gets.join(' ') + tag);

  // ================= D. the walk-through: the next one at once, nothing swallowed
  click(w, d.querySelector('[data-cc="walk"]'));
  check(await until(() => w.eval("typeof WLK === 'object' && !!WLK.md && WLK.items.length === 4")), 'D: the walk-through with the four open positions' + tag);
  const wn = () => d.querySelector('.wlkdlg [data-wlk-n]')?.textContent.trim() || '';
  check(await until(() => wn() === '1 of 4'), 'D: 1 of 4: ' + wn() + tag);
  w.eval("wlk_mark('noreceipt')");
  check(wn() === '2 of 4', 'D: the next position at once, its write held: ' + wn() + tag);
  check(await until(() => w.__q.length === 1), 'D: the first step\'s write is on its way' + tag);
  w.eval("wlk_mark('private')");
  check(wn() === '3 of 4', 'D: the next step works at once, nothing swallowed: ' + wn() + tag);
  w.__go();
  check(await until(() => w.__q.length === 1), 'D: the second step\'s write' + tag);
  w.__fail(500);
  check(await until(() => !busy()), 'D: nothing waits' + tag);
  w.eval('wlk_go(-1)');
  check(await until(() => wn() === '2 of 4' && !!d.querySelector('.wlkdlg .wlk-fail')), 'D: the refused step is open again and says "Not saved"' + tag);
  w.eval("wlk_mark('private')");
  check(await until(() => w.__q.length === 1), 'D: taken again' + tag);
  w.__go(); check(await idle(), 'D: saved' + tag);
  L = await lines();
  check(L.filter(x => x.state === 'open').length === 2 && by(MER[0])?.state === 'noreceipt' && by(MER[2])?.state === 'private', 'D: on the server ' + L.map(x => x.merchant.split(' ')[0] + ':' + x.state).join() + tag);
  check(gets.length === 0, 'D: no reload behind the walk-through: ' + gets.join(' ') + tag);
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
  await run('alice', `org:${org.id}`);

  // ================= freelancer-matrix: office - the same card sheet as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida', (await call('GET', '/api/office/books')).upload_ws || 'private');

  console.log(`p7499_karten_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
