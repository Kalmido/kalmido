// kalmido-suite: fresh
// #7493 UI: "write shows at once" (core.js rwRows) in the quotation editor on a slow line. Own container (start.sh), jsdom.
// Invented services and amounts only. Every save of the positions is held by the test (boot.js hold) and let through,
// refused or dropped one at a time.
// freelancer-matrix: office (the person without an organisation uses the same editor code)
// A. a service added: the line stands at once ("Saving…", the sums "Calculating…"), before any answer; after it the mark goes
// B. typing in a line while the answer of an earlier save comes: the field keeps the focus and the typed text
// C. three services added quickly: three lines at once, in that order; on the server the same three, no double line
// D. a refused save (500): the line stays with "Not saved" and "Try again"; Try again saves it
// E. no connection (the line drops the request): the same, "Try again" saves it
// F. a line removed: gone at once; the save refused -> the line is back where it was
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
const change = (w, el, v) => { if (!el) return; el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const svc = (title, qty, rate) => ({kind: 'service', title, qty, unit: 'day', rate, tax: 'standard', raw_fee: 0, producing: 0, intext: 'intern', cost: 0, discountable: 1});
const rows = d => [...d.querySelectorAll('#ofd-pos .ofdits [data-rwk]')];
const titles = d => rows(d).map(r => r.querySelector('[data-k="title"]')?.value ?? '');
const svName = (d, id) => d.querySelector(`.ofdpick [data-sid="${id}"]`);

async function run(user) {
  const tag = ` (${user})`;
  const sv = {};
  for (const [n, r] of [['Licht', 500], ['Ton', 400], ['Maske', 300], ['Grading', 700]]) {
    const j = await call('POST', '/api/office/services', {name_de: n, name_en: n, category: 'Crew', unit: 'day', daily_rate: r});
    check(j.id > 0, `service ${n} ${j.status}` + tag); sv[n] = j.id;
  }
  const doc = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Spot', items: [svc('Concept', 1, 800), svc('Shoot', 1, 1200)]});
  check(doc.status === 201, 'a quotation ' + doc.status + tag);
  const w = await boot({user, hash: `office/offers/${doc.id}`}), d = w.document;
  check(await until(() => rows(d).length === 2), 'the editor shows two lines' + tag);
  hold(w, new RegExp(`/api/office/docs/${doc.id}(/items)?$`));
  const pick = async name => {
    click(w, d.querySelector('.ofdeditor [data-ofd="it-svc"]'));
    const b = await until(() => svName(d, sv[name]));
    click(w, b);
    return !!b;
  };
  const idle = () => until(() => w.eval('OFD.saving') === 0 && !w.eval('OFD_W.pend'));

  // ================= A. a line stands at once
  check(await pick('Licht'), 'A: the picker shows the service' + tag);
  check(titles(d).join() === 'Concept,Shoot,Licht', 'A: the new line is there before any answer: ' + titles(d).join() + tag);
  check(await until(() => w.__q.length === 1) && w.__n === 1, 'A: its save is on its way and held' + tag);
  check(!!rows(d)[2]?.querySelector('.rwsaving') && rows(d)[2].classList.contains('rw-saving'), 'A: the new line says "Saving…"' + tag);
  check(!!d.querySelector('#ofd-pos.rwcalc .rwcalcl') && d.querySelector('#ofd-pos').getAttribute('aria-busy') === 'true', 'A: the sums say "Calculating…"' + tag);
  check(d.activeElement === rows(d)[2]?.querySelector('[data-k="qty"]'), 'A: the new line\'s quantity has the focus at once' + tag);
  w.__go();
  check(await idle(), 'A: saved' + tag);
  check(await until(() => !d.querySelector('#ofd-pos .rwmark') && !d.querySelector('#ofd-pos.rwcalc')), 'A: after the answer no mark, the sums are back' + tag);
  let s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.map(x => x.title).join() === 'Concept,Shoot,Licht', 'A: on the server: ' + s.items?.map(x => x.title).join() + tag);
  check(w.eval('OFD.doc.items[2].id') === s.items?.[2]?.id, 'A: the new line has its id from the answer' + tag);

  // ================= B. typing while the answer of an earlier save comes
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '2');
  check(await until(() => w.__q.length === 1), 'B: the quantity\'s save is on its way' + tag);
  const tt = rows(d)[1].querySelector('[data-k="title"]');
  tt.focus(); tt.value = 'Shoot extended'; tt.dispatchEvent(new w.Event('input', {bubbles: true}));
  w.__go();
  check(await idle(), 'B: the quantity is saved' + tag);
  await sleep(100);
  const tt2 = rows(d)[1].querySelector('[data-k="title"]');
  check(d.activeElement === tt2, 'B: the field keeps the focus after the answer' + tag);
  check(tt2?.value === 'Shoot extended', `B: the typed text stays after the answer (${tt2?.value})` + tag);
  change(w, tt2, 'Shoot extended');
  check(await until(() => w.__q.length === 1), 'B: the title\'s save goes when the field is left' + tag);
  w.__go(); check(await idle(), 'B: the title is saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 2 && s.items?.[1]?.title === 'Shoot extended', `B: both on the server (${s.items?.[0]?.qty}, ${s.items?.[1]?.title})` + tag);

  // ================= C. three services added quickly
  const n0 = w.__n;
  for (const n of ['Ton', 'Maske', 'Grading']) await pick(n);
  check(titles(d).slice(3).join() === 'Ton,Maske,Grading', 'C: three lines at once, in order: ' + titles(d).join() + tag);
  check(rows(d).slice(3).every(r => r.classList.contains('rw-saving')), 'C: all three say "Saving…"' + tag);
  for (let t = 0; t < 200 && w.eval('OFD_W.pend'); t++) { if (w.__q.length) w.__go(); await sleep(50); }  // each held save through, none let through ahead
  check(await idle(), 'C: saved' + tag);
  check(w.__n - n0 === 2, `C: the first add went at once, the two that waited joined one save (${w.__n - n0} saves)` + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.map(x => x.title).join() === 'Concept,Shoot extended,Licht,Ton,Maske,Grading', 'C: on the server the same lines, none twice: ' + s.items?.map(x => x.title).join() + tag);
  check(titles(d).join() === s.items?.map(x => x.title).join() && !d.querySelector('#ofd-pos .rwmark'), 'C: the view the same, no mark' + tag);

  // ================= D. a refused save: the line stays with "Try again"
  await pick('Licht');
  check(titles(d).length === 7, 'D: the line is there' + tag);
  check(await until(() => w.__q.length === 1), 'D: its save is on its way' + tag);
  w.__fail(500);
  check(await until(() => rows(d)[6]?.classList.contains('rw-failed')), 'D: the line says "Not saved"' + tag);
  check(titles(d)[6] === 'Licht' && !!rows(d)[6].querySelector('[data-rwagain="ofd"]'), 'D: the line stays, with "Try again"' + tag);
  check(!d.querySelector('#ofd-pos.rwcalc'), 'D: no "Calculating…" while nothing waits' + tag);
  w.eval("ofdPatch({project_title: 'Spot 2'})");  // a save of the head: its answer brings the stored positions
  check(await until(() => w.__q.length === 1), 'D: the head\'s save is on its way' + tag);
  w.__go();
  check(await until(() => w.eval('OFD.saving') === 0), 'D: the head is saved' + tag);
  await w.eval(`ofdLoadDoc(${doc.id}, true)`);  // "Check again" / a reload of the document
  check(titles(d)[6] === 'Licht' && rows(d)[6]?.classList.contains('rw-failed'), 'D: the unsaved line stays through another answer and a reload: ' + titles(d).join() + tag);
  click(w, rows(d)[6].querySelector('[data-rwagain="ofd"]'));
  check(await until(() => w.__q.length === 1), 'D: Try again sends it' + tag);
  check(rows(d)[6]?.classList.contains('rw-saving'), 'D: the line says "Saving…" again' + tag);
  w.__go(); check(await idle(), 'D: saved' + tag);
  check(await until(() => !d.querySelector('#ofd-pos .rwmark')), 'D: no mark after Try again' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.length === 7 && s.items[6].title === 'Licht', 'D: on the server once: ' + s.items?.map(x => x.title).join() + tag);

  // ================= E. no connection
  await pick('Ton');
  check(await until(() => w.__q.length === 1), 'E: its save is on its way' + tag);
  w.__drop();
  check(await until(() => rows(d)[7]?.classList.contains('rw-failed')), 'E: no connection: the line says "Not saved"' + tag);
  check(titles(d)[7] === 'Ton', 'E: the line stays' + tag);
  click(w, rows(d)[7].querySelector('[data-rwagain="ofd"]'));
  check(await until(() => w.__q.length === 1), 'E: Try again sends it' + tag);
  w.__go(); check(await idle(), 'E: saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.length === 8 && s.items[7].title === 'Ton' && !d.querySelector('#ofd-pos .rwmark'), 'E: on the server, no mark: ' + s.items?.map(x => x.title).join() + tag);

  // ================= F. a line removed, the save refused: it comes back
  click(w, rows(d)[2].querySelector('[data-ofd="it-del"]'));
  check(titles(d).length === 7 && !titles(d).slice(0, 3).includes('Licht'), 'F: the line is gone at once: ' + titles(d).join() + tag);
  check(await until(() => w.__q.length === 1), 'F: its save is on its way' + tag);
  w.__fail(500);
  check(await until(() => titles(d).length === 8 && titles(d)[2] === 'Licht'), 'F: refused: the line is back in its place: ' + titles(d).join() + tag);
  check(await idle(), 'F: nothing waits' + tag);
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

  // ================= freelancer-matrix: office - the same editor as a person without an organisation
  const fr = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.status === 200 || fr.status === 201, 'freelancer created ' + fr.status);
  CK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'office,clients'});
  check(!((await call('GET', '/api/state')).me?.workspaces || []).length, 'the freelancer is in no organisation');
  await run('frida');

  console.log(`p7493_schreiben_sofort_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
