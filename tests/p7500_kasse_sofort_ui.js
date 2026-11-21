// kalmido-suite: fresh
// #7500 UI: the cash book's quick entry "writes at once" (core.js rwRows) on a slow line. Own container (start.sh), jsdom.
// Invented texts and amounts only. Every new entry's save is held by the test (boot.js hold) and let through or refused.
// freelancer-matrix: office (the person without an organisation has the same cash book)
// A. an entry booked: its line stands under the form at once ("Saving…", the balance "Calculating…"), the form stays empty
//    with the cursor in the amount, no loading block; the answer brings the number and the new balance
// B. three entries typed one after the other while the answers are held: three lines at once, the form never a loading
//    block, the focus in the form; on the server the three, each once, in that order
// C. typing while an answer comes: the text in the form stays
// D. a refusal (below zero): the line goes, its values come back into the form with the reason
// E. no answer: the line stays with "Not saved" and "Try again"; Try again books it once
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const lines = d => [...d.querySelectorAll('#cb-entries [data-rwk]')];
const texts = d => lines(d).map(l => l.querySelector('.ofcn b')?.textContent || '');
const bal = d => (d.querySelector('.cb-bal')?.textContent || '').replace(/\s/g, ' ');

async function run(user) {
  const tag = ` (${user})`;
  const bk = (await call('GET', '/api/office/cashbooks')).books?.[0];
  check(!!bk, 'the default cash box' + tag);
  const p = await call('PATCH', `/api/office/cashbooks/${bk.id}`, {opening: '100'});
  check(p.status === 200, 'opening balance 100 ' + p.status + tag);
  const w = await boot({user, hash: 'office/cashbook'}), d = w.document;
  check(await until(() => d.querySelector('#cb-quick') && d.querySelector('.cb-bal')), 'the cash book with the quick entry' + tag);
  hold(w, new RegExp(`/api/office/cashbooks/${bk.id}/entries$`));
  const form = () => d.querySelector('#cb-quick');
  const amt = () => d.querySelector('#cb-amount'), txt = () => d.querySelector('#cb-text');
  const book = (dir, a, t) => {
    click(w, d.querySelector(`[data-cb="dir"][data-v="${dir}"]`));
    amt().value = a; txt().value = t;
    click(w, form().querySelector('.cb-go'));
  };
  const busy = () => w.eval('[...CB_WS.values()].some(W => W.pend)');
  const idle = () => until(() => !busy());
  const f0 = form();

  // ================= A. one entry
  book('in', '20', 'Verkauf A');
  check(texts(d).join() === 'Verkauf A', 'A: the line is there before any answer: ' + texts(d).join() + tag);
  check(await until(() => w.__q.length === 1), 'A: its save is on its way and held' + tag);
  check(lines(d)[0]?.classList.contains('rw-saving') && !!lines(d)[0].querySelector('.rwsaving'), 'A: the line says "Saving…"' + tag);
  check(!!d.querySelector('.cb-head.rwcalc .rwcalcl'), 'A: the balance says "Calculating…"' + tag);
  check(form() === f0 && !d.querySelector('.ofcbody .loading, .ofcbody .skel'), 'A: the form stands, no loading block' + tag);
  check(amt().value === '' && txt().value === '' && d.activeElement === amt(), 'A: the form is empty, the cursor in the amount' + tag);
  w.__go();
  check(await idle(), 'A: saved' + tag);
  check(await until(() => /120[.,]00/.test(bal(d)) && !d.querySelector('.cb-head.rwcalc')), 'A: the new balance from the answer: ' + bal(d) + tag);
  check(lines(d)[0]?.querySelector('.cb-no')?.textContent.trim() === '1' && !lines(d)[0].querySelector('.rwmark'), 'A: the number from the answer, no mark' + tag);

  // ================= B. three entries one after the other, the answers held
  const n0 = w.__n;
  book('in', '1', 'Eins'); book('in', '2', 'Zwei'); book('out', '3', 'Drei');
  check(texts(d).slice(0, 3).join() === 'Drei,Zwei,Eins', 'B: three lines at once (newest first): ' + texts(d).join() + tag);
  check(form() === f0 && d.activeElement === amt() && !d.querySelector('.ofcbody .loading, .ofcbody .skel'), 'B: the form stands, the focus in the amount, no loading block' + tag);
  check(lines(d).slice(0, 3).every(l => l.classList.contains('rw-saving')), 'B: all three say "Saving…"' + tag);

  // ================= C. typing while an answer comes
  amt().focus(); amt().value = '7'; txt().value = 'Halb getippt';
  for (let t = 0; t < 200 && (busy() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await idle(), 'B: all saved' + tag);
  check(w.__n - n0 === 3, `B: one request per entry (${w.__n - n0})` + tag);
  const s = await call('GET', `/api/office/cashbooks/${bk.id}/entries`);
  check(s.entries?.map(e => e.text).join() === 'Drei,Zwei,Eins,Verkauf A' && s.balance === '120.00', `B: on the server the four, each once (${s.entries?.map(e => e.no + ':' + e.text).join()}, ${s.balance})` + tag);
  check(await until(() => /120[.,]00/.test(bal(d)) && !d.querySelector('#cb-entries .rwmark')), 'B: the balance from the last answer, no mark: ' + bal(d) + tag);
  check(form() === f0 && amt().value === '7' && txt().value === 'Halb getippt' && d.activeElement === amt(), 'C: the typed values and the focus stay through the answers' + tag);
  amt().value = ''; txt().value = '';

  // ================= D. a refusal: below zero
  book('out', '500', 'Zu viel');
  check(await until(() => w.__q.length === 1), 'D: its save is on its way' + tag);
  w.__go();  // the server refuses it (below zero)
  check(await until(() => /below zero/.test(d.querySelector('#cb-qerr')?.textContent || '')), 'D: the reason at the form: ' + d.querySelector('#cb-qerr')?.textContent + tag);
  check(!texts(d).includes('Zu viel'), 'D: the line is gone' + tag);
  check(/500/.test(amt().value) && txt().value === 'Zu viel', `D: its values are back in the form (${amt().value}, ${txt().value})` + tag);
  check(await idle(), 'D: nothing waits' + tag);
  amt().value = ''; txt().value = '';

  // ================= E. no answer: "Not saved", "Try again" books it once
  w.eval('NET_T.w = 400');
  book('in', '5', 'Ohne Antwort');
  check(await until(() => w.__q.length === 1), 'E: its save is on its way' + tag);
  check(await until(() => lines(d)[0]?.classList.contains('rw-failed')), 'E: no answer: the line says "Not saved"' + tag);
  check(texts(d)[0] === 'Ohne Antwort' && !!lines(d)[0].querySelector('[data-rwagain]'), 'E: the line stays, with "Try again"' + tag);
  w.__go();  // the lost request reaches the server late: booked once
  w.eval('NET_T.w = 20000');
  await sleep(200);
  click(w, lines(d)[0].querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'E: Try again sends it' + tag);
  w.__go(); check(await idle(), 'E: saved' + tag);
  check(await until(() => !d.querySelector('#cb-entries .rwmark') && /125[.,]00/.test(bal(d))), 'E: no mark, the balance 125: ' + bal(d) + tag);
  const s2 = await call('GET', `/api/office/cashbooks/${bk.id}/entries`);
  check(s2.entries?.filter(e => e.text === 'Ohne Antwort').length === 1, `E: booked once on the server (${s2.entries?.map(e => e.text).join()})` + tag);
  w.__off();
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

  // ================= freelancer-matrix: office - the same cash book as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida');

  console.log(`p7500_kasse_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
