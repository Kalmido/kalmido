// kalmido-suite: fresh
// #7502 UI: saving a receipt of the bookkeeping "writes at once" (core.js rwRows, one writer per receipt) on a slow line. Own
// container (start.sh), jsdom. Invented file names, categories and amounts only. The saves are held by the test (boot.js hold).
// freelancer-matrix: office (the person without an organisation has the same receipts; the long list only for alice)
// A. Save: the sheet closes, the row shows the new category with "Saving…" before the answer; after it no mark
// B. after the save the list keeps every row loaded with "Load more" (over 200) and only the list comes again (no income
//    statement, no VAT figures, no books of the year while their page is not open)
// C. a refused save (500): the row keeps the typed category with "Not saved" and "Try again", the sheet comes back with it
//    and the reason; saving from there stores it
// D. no answer: the row says "Not saved"; "Try again" at the row saves it
// E. a value taken over while the sheet is open (bkRxAfter): the same sheet shows it in its field, what was typed in another
//    field stays
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
const TC = require('./testclock');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const today = TC.today();

function tinyPdf(text) {  // a one-page PDF with a text layer
  const s = `BT /F1 12 Tf 40 700 Td (${text}) Tj ET`;
  const o = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${s.length} >>\nstream\n${s}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  o.forEach((x, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${x}\nendobj\n`; });
  const xr = out.length; out += `xref\n0 ${o.length + 1}\n0000000000 65535 f \n` + offs.map(n => String(n).padStart(10, '0') + ' 00000 n \n').join('');
  return out + `trailer\n<< /Size ${o.length + 1} /Root 1 0 R >>\nstartxref\n${xr}\n%%EOF\n`;
}
// n receipts of today (uploaded in batches, then amount, date and category in parallel batches)
async function receipts(ws, n, tag) {
  const ids = [];
  for (let i = 0; i < n; i += 50) {
    const fd = new FormData(); fd.append('ws', ws);
    for (let k = i; k < Math.min(n, i + 50); k++) fd.append('files', new Blob([tinyPdf(`Beleg ${tag} ${k}`)], {type: 'application/pdf'}), `beleg-${tag}-${k}.pdf`);
    const r = await fetch(B + 'api/docs', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd});
    const j = await r.json().catch(() => ({}));
    ids.push(...(j.ids || []));
  }
  check(ids.length === n, `${n} receipts uploaded (${ids.length})`);
  for (let i = 0; i < ids.length; i += 20) {
    await Promise.all(ids.slice(i, i + 20).map(async (id, k) => {
      await call('PATCH', `/api/docs/${id}`, {amount: String(10 + i + k) + '.00', date: today});
      await call('PUT', `/api/docs/${id}/receipt`, {category: 'Material', vat_pct: '19', keep: true});
    }));
  }
  return ids;
}

async function run(user, many, ws) {
  const tag = ` (${user})`;
  const ids = await receipts(ws, many ? 205 : 4, user);
  const rcOf = async id => (await call('GET', `/api/docs/${id}/receipt`)).receipt || {};
  const w = await boot({user, hash: 'office/books/receipts'}), d = w.document;
  const rowOf = id => d.querySelector(`.rcl-list [data-rcl="rc"][data-id="${id}"]`)?.closest('li');
  const nRows = () => d.querySelectorAll('.rcl-list > li').length;
  check(await until(() => nRows() === Math.min(200, ids.length), 30000), `the list shows ${Math.min(200, ids.length)} rows (${nRows()})` + tag);
  if (many) {
    click(w, d.querySelector('[data-rcl="more"]'));
    check(await until(() => nRows() === 205, 30000), `"Load more": 205 rows (${nRows()})` + tag);
  }
  const R = [...d.querySelectorAll('.rcl-list [data-rcl="rc"]')].map(b => +b.dataset.id);
  const last = R[R.length - 1], R2 = R[R.length - 2], R3 = R[R.length - 3], R4 = R[0];
  const sent = []; { const f0 = w.fetch; w.fetch = (u, o = {}) => { sent.push(`${o.method || 'GET'} ${u}`); return f0(u, o); }; }
  hold(w, /\/api\/docs\/\d+(\/receipt)?$/);
  const open = async id => { click(w, rowOf(id)?.querySelector('[data-rcl="rc"]')); return until(() => d.querySelector(`.bk-sheet[data-rxid="${id}"] #bk-cat`)); };
  const busy = () => w.eval('[...BK_WS.values()].some(W => W.pend)');
  const idle = () => until(() => !busy());

  // ================= A. Save: the row shows its state
  check(!!await open(last), 'A: the sheet of the last loaded row opens' + tag);
  d.querySelector('.bk-sheet #bk-cat').value = 'Software';
  sent.length = 0;
  click(w, d.querySelector('.bk-sheet [data-m="save"]'));
  check(await until(() => w.__q.length === 1), 'A: its save is on its way and held' + tag);
  check(!d.querySelector('.bk-sheet'), 'A: the sheet closed' + tag);
  check(/Software/.test(rowOf(last)?.textContent || '') && rowOf(last).classList.contains('rw-saving') && !!rowOf(last).querySelector('.rwsaving'), 'A: the row shows Software with "Saving…"' + tag);
  w.__go();
  check(await idle(), 'A: saved' + tag);
  check(await until(async () => (await rcOf(last)).category === 'Software'), 'A: on the server' + tag);
  check(await until(() => rowOf(last) && !rowOf(last).querySelector('.rwmark') && !rowOf(last).classList.contains('rw-saving')), 'A: no mark after the answer' + tag);

  // ================= B. the list keeps its rows, only the list comes again
  check(await until(() => !w.eval('RCL.loading') && sent.some(s => /^GET \/api\/office\/books\/receipts\?/.test(s))), 'B: the list came again' + tag);
  check(nRows() === ids.length && /Software/.test(rowOf(last)?.textContent || ''), `B: it keeps every loaded row (${nRows()} of ${ids.length})` + tag);
  const extra = sent.filter(s => /^GET \/api\/office\/books(\/euer|\/ustva)?\?year=/.test(s));
  check(!extra.length, 'B: no income statement, VAT figures or books of the year fetched: ' + extra.join(' | ') + tag);
  check(sent.filter(s => /^GET \/api\/office\/books\/receipts\?/.test(s)).length === 1, 'B: the list once, all its rows in one request: ' + sent.filter(s => /receipts\?/.test(s)).length + tag);

  // ================= C. refused: the row keeps the value with "Try again", the sheet comes back with it
  check(!!await open(R2), 'C: the sheet opens' + tag);
  d.querySelector('.bk-sheet #bk-cat').value = 'Hardware';
  click(w, d.querySelector('.bk-sheet [data-m="save"]'));
  check(await until(() => w.__q.length === 1), 'C: its save is on its way' + tag);
  w.__fail(500);
  check(await until(() => rowOf(R2)?.classList.contains('rw-failed') && /Hardware/.test(rowOf(R2).textContent) && !!rowOf(R2).querySelector('[data-rwagain]')), 'C: the row keeps Hardware with "Not saved" and "Try again"' + tag);
  check(await until(() => d.querySelector(`.bk-sheet[data-rxid="${R2}"] #bk-cat`)?.value === 'Hardware' && (d.querySelector('.bk-sheet .aerr')?.textContent || '').trim()), 'C: the sheet comes back with the typed value and the reason' + tag);
  check((await rcOf(R2)).category === 'Material', 'C: nothing written' + tag);
  click(w, d.querySelector('.bk-sheet [data-m="save"]'));
  check(await until(() => w.__q.length === 1), 'C: saved from the sheet: on its way' + tag);
  w.__go(); check(await idle(), 'C: saved' + tag);
  check(await until(async () => (await rcOf(R2)).category === 'Hardware'), 'C: on the server' + tag);
  check(await until(() => rowOf(R2) && !rowOf(R2).querySelector('.rwmark')), 'C: no mark' + tag);

  // ================= D. no answer: "Try again" at the row
  w.eval('NET_T.w = 400');
  check(!!await open(R3), 'D: the sheet opens' + tag);
  d.querySelector('.bk-sheet #bk-cat').value = 'Travel';
  click(w, d.querySelector('.bk-sheet [data-m="save"]'));
  check(await until(() => w.__q.length === 1), 'D: its save is on its way' + tag);
  check(await until(() => rowOf(R3)?.classList.contains('rw-failed')), 'D: no answer: the row says "Not saved"' + tag);
  w.__q.splice(0); w.eval('NET_T.w = 20000');  // the lost request never comes back
  check(await until(() => d.querySelector('.bk-sheet [data-m="close"]')), 'D: the sheet came back' + tag);
  click(w, d.querySelector('.bk-sheet [data-m="close"]'));
  check(await until(() => !d.querySelector('.bk-sheet')), 'D: closed without saving' + tag);
  click(w, rowOf(R3).querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'D: Try again sends it' + tag);
  w.__go(); check(await idle(), 'D: saved' + tag);
  check(await until(async () => (await rcOf(R3)).category === 'Travel'), 'D: on the server' + tag);
  check(await until(() => rowOf(R3) && !rowOf(R3).querySelector('.rwmark')), 'D: no mark' + tag);

  // ================= E. a value taken over while the sheet is open: the same sheet, the typed field stays
  check(!!await open(R4), 'E: the sheet opens' + tag);
  const sh = d.querySelector('.bk-sheet'), am = sh.querySelector('#bk-amount');
  am.value = '77,00'; am.dispatchEvent(new w.Event('input', {bubbles: true}));
  w.__off();
  check((await call('PUT', `/api/docs/${R4}/receipt`, {category: 'Taken over', vat_pct: '7', keep: true})).status === 200, 'E: the receipt changed by a take-over' + tag);
  await w.eval(`bkRxAfter(${R4})`);
  check(d.querySelector('.bk-sheet') === sh && sh.isConnected, 'E: the sheet stays (not built anew)' + tag);
  check(sh.querySelector('#bk-cat').value === 'Taken over' && sh.querySelector('#bk-vat').value === '7', 'E: the new values in its fields' + tag);
  check(sh.querySelector('#bk-amount').value === '77,00' || sh.querySelector('#bk-amount').value === '77.00', 'E: the typed amount stays: ' + sh.querySelector('#bk-amount').value + tag);
  click(w, sh.querySelector('[data-m="save"]'));
  check(await until(async () => +(await call('GET', `/api/docs/${R4}`)).amount === 77 && (await rcOf(R4)).category === 'Taken over'), 'E: saved without a conflict: the amount and the taken over category' + tag);
  check(!d.querySelector('.obj-merge'), 'E: no merge bar' + tag);
  check(await idle(), 'E: nothing waits' + tag);
  check(!errs.length, 'no script errors ' + errs.join(' | ') + tag); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients,docs'});
  { const me = (await call('GET', '/api/state')).me; const org = await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
    await call('PATCH', '/api/settings', {workspace: `org:${org.id}`});
    await run('alice', true, `org:${org.id}`); }

  // ================= freelancer-matrix: office - the same receipts as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients,docs'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida', false, 'private');

  console.log(`p7502_belege_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
