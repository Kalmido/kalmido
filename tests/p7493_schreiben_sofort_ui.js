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
// J-L (F16, F17, F19 of the readers of job/5996): the writer hangs on the document's id, not on an object held over a wait
// M, N (#7496): the positions of an open part and a shoot part's calculation sheet through the same writer: three quick
// changes while the answers are held all reach the server, typing during an answer stays, an error says "Not saved - Try again"
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
  const busy = () => w.eval('[...OFD_WS.values()].some(W => W.pend)');
  const idle = () => until(() => w.eval('OFD.saving') === 0 && !busy());

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
  for (let t = 0; t < 200 && busy(); t++) { if (w.__q.length) w.__go(); await sleep(50); }  // each held save through, none let through ahead
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
  check(titles(d)[6] === 'Licht' && !!rows(d)[6].querySelector('[data-rwagain]'), 'D: the line stays, with "Try again"' + tag);
  check(!d.querySelector('#ofd-pos.rwcalc'), 'D: no "Calculating…" while nothing waits' + tag);
  w.eval("ofdPatch({project_title: 'Spot 2'})");  // a save of the head: its answer brings the stored positions
  check(await until(() => w.__q.length === 1), 'D: the head\'s save is on its way' + tag);
  w.__go();
  check(await until(() => w.eval('OFD.saving') === 0), 'D: the head is saved' + tag);
  await w.eval(`ofdLoadDoc(${doc.id}, true)`);  // "Check again" / a reload of the document
  check(titles(d)[6] === 'Licht' && rows(d)[6]?.classList.contains('rw-failed'), 'D: the unsaved line stays through another answer and a reload: ' + titles(d).join() + tag);
  click(w, rows(d)[6].querySelector('[data-rwagain]'));
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
  click(w, rows(d)[7].querySelector('[data-rwagain]'));
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

  // ================= G. a line removed without a connection: back, said once with "Try again" (no silent return)
  click(w, rows(d)[2].querySelector('[data-ofd="it-del"]'));
  check(await until(() => w.__q.length === 1), 'G: the removal\'s save is on its way' + tag);
  w.__drop();
  check(await until(() => titles(d).length === 8 && titles(d)[2] === 'Licht'), 'G: no connection: the line is back' + tag);
  const tb = await until(() => { const t = d.querySelector('#toast:not(.hidden)'); return t && /not saved|online/i.test(t.textContent) && t.querySelector('button:not(.tx)'); });
  check(!!tb, 'G: a message says it, with "Try again": ' + d.querySelector('#toast')?.textContent + tag);
  click(w, tb);
  check(await until(() => titles(d).length === 7 && w.__q.length === 1), 'G: Try again removes it again and sends it' + tag);
  w.__go(); check(await idle(), 'G: saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.length === 7 && s.items[2].title !== 'Licht', 'G: removed on the server: ' + s.items?.map(x => x.title).join() + tag);

  // ================= H. the editor left while a save waits: the change goes to its own document
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '6');
  check(await until(() => w.__q.length === 1), 'H: the quantity\'s save is on its way' + tag);
  w.location.hash = '#office/offers';
  check(await until(() => !d.querySelector('#ofd-pos')), 'H: the list is open' + tag);
  w.__go(); check(await idle(), 'H: saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 6, `H: the change is on the server (${s.items?.[0]?.qty})` + tag);

  // ================= I. a second document changed while the first one's save waits: each change in its own document
  const doc2 = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Spot B', items: [svc('Other', 1, 100)]});
  w.location.hash = `#office/offers/${doc.id}`;
  check(await until(() => rows(d).length === 7 && w.eval('OFD.doc?.id') === doc.id), 'I: the first document is open again' + tag);
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '7');
  check(await until(() => w.__q.length === 1), 'I: its save is on its way' + tag);
  change(w, rows(d)[1].querySelector('[data-k="qty"]'), '8');  // waits behind it
  w.location.hash = `#office/offers/${doc2.id}`;
  check(await until(() => rows(d).length === 1 && w.eval('OFD.doc?.id') === doc2.id), 'I: the second document is open' + tag);
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '9');  // the second document's save is not held: it goes at once
  check(await until(async () => +(await call('GET', `/api/office/docs/${doc2.id}`)).items?.[0]?.qty === 9), 'I: the second document saved its own change at once' + tag);
  for (let t = 0; t < 200 && (busy() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await idle(), 'I: all saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 7 && +s.items?.[1]?.qty === 8 && s.items?.length === 7, `I: the first document got both its changes (${s.items?.map(x => x.qty).join()})` + tag);
  const s2 = await call('GET', `/api/office/docs/${doc2.id}`);
  check(s2.items?.length === 1 && +s2.items[0].qty === 9 && s2.items[0].title === 'Other', `I: the second document only its own (${s2.items?.map(x => x.title + ':' + x.qty).join()})` + tag);
  // ================= J (F16). a refused line, the document reloaded, then a save of its head: "Try again" sends from the
  // document's current object (its version), no false conflict bar
  w.location.hash = `#office/offers/${doc.id}`;
  check(await until(() => rows(d).length === 7 && w.eval('OFD.doc?.id') === doc.id), 'J: the first document is open again' + tag);
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '3');
  check(await until(() => w.__q.length === 1), 'J: the quantity\'s save is on its way' + tag);
  w.__fail(500);
  check(await until(() => rows(d)[0]?.classList.contains('rw-failed')), 'J: the line says "Not saved"' + tag);
  await w.eval(`ofdLoadDoc(${doc.id}, true)`);
  w.eval("ofdPatch({project_title: 'Spot J'})");
  check(await until(() => w.__q.length === 1), 'J: the head\'s save after the reload is on its way' + tag);
  w.__go(); check(await until(() => w.eval('OFD.saving') === 0), 'J: the head is saved' + tag);
  click(w, rows(d)[0].querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'J: Try again sends it' + tag);
  w.__go(); check(await idle(), 'J: saved' + tag);
  check(!d.querySelector('.ofdcf'), 'J: no conflict bar (the writer sent the version of the head\'s answer)' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 3 && s.project_title === 'Spot J', `J: both on the server (${s.items?.[0]?.qty}, ${s.project_title})` + tag);

  // ================= K (F17). no answer only after the editor was left: back in it, "Try again" at the line sends it
  w.eval('NET_T.w = 400');
  change(w, rows(d)[0].querySelector('[data-k="qty"]'), '4');
  check(await until(() => w.__q.length === 1), 'K: the quantity\'s save is on its way' + tag);
  w.location.hash = '#office/offers';
  check(await until(() => !d.querySelector('#ofd-pos')), 'K: the list is open' + tag);
  check(await until(() => w.eval(`OFD_WS.get(${doc.id}).failed()`)), 'K: no answer: the line is unsaved' + tag);
  w.__q.splice(0); w.eval('NET_T.w = 20000');  // the lost request never comes back
  w.location.hash = `#office/offers/${doc.id}`;
  check(await until(() => rows(d)[0]?.classList.contains('rw-failed') && w.eval('OFD.doc?.id') === doc.id), 'K: back in the document, the line says "Not saved"' + tag);
  const n1 = w.__n;
  click(w, rows(d)[0].querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1 && w.__n === n1 + 1), 'K: Try again sends it' + tag);
  w.__go(); check(await idle(), 'K: saved' + tag);
  check(await until(() => !d.querySelector('#ofd-pos .rwmark')), 'K: no mark after Try again' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(+s.items?.[0]?.qty === 4 && !d.querySelector('.ofdcf'), `K: on the server (${s.items?.[0]?.qty}), no conflict bar` + tag);

  // ================= L (F19). the picker waits for the catalogue, an answer replaces the document meanwhile, the catalogue
  // is empty: the free line goes into the document as it is now (it used to go into the object seen at opening, lost)
  const nL = rows(d).length;
  w.eval('OFC.data.services = null; OFC.loading.services = true');
  click(w, d.querySelector('.ofdeditor [data-ofd="it-svc"]'));
  check(await until(() => d.querySelector('.ofdpick #ofd-slist')), 'L: the picker waits for the catalogue' + tag);
  await w.eval(`ofdLoadDoc(${doc.id}, true)`);  // a new object for the open document
  w.eval('OFC.data.services = []; OFC.loading.services = false');
  check(await until(() => rows(d).length === nL + 1 && w.eval('OFD.doc.items.length') === nL + 1), `L: the free line stands in the open document (${rows(d).length})` + tag);
  check(await until(() => w.__q.length === 1), 'L: its save is on its way' + tag);
  w.__go(); check(await idle(), 'L: saved' + tag);
  s = await call('GET', `/api/office/docs/${doc.id}`);
  check(s.items?.length === nL + 1, `L: on the server (${s.items?.length})` + tag);
  // ================= M (#7496). the positions of an open part: three quick changes, typing during an answer, an error
  const partOf = j => j?.part || j;
  const doc3 = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Spot M', items: [svc('Intro', 1, 100)]});
  const PM = partOf(await call('POST', `/api/office/docs/${doc3.id}/parts`, {kind: 'items', title: 'Modul'}))?.id;
  check(PM > 0, 'M: a part' + tag);
  const pi = await call('PUT', `/api/office/docs/${doc3.id}/parts/${PM}/items`, {items: [svc('Eins', 1, 100), svc('Zwei', 1, 200), svc('Drei', 1, 300)]});
  check(pi.status === 200, 'M: three positions in the part ' + pi.status + tag);
  w.location.hash = `#office/offers/${doc3.id}`;
  check(await until(() => w.eval('OFD.doc?.id') === doc3.id && d.querySelector(`.tplist [data-tog][data-pid="${PM}"]`)), 'M: the quotation with its part' + tag);
  click(w, d.querySelector(`.tplist [data-tog][data-pid="${PM}"]`));
  const BM = `.tpfbox[data-pid="${PM}"]`, prow = () => [...d.querySelectorAll(`${BM} .ofdits [data-rwk]`)];
  check(await until(() => prow().length === 3), 'M: the part is open with its three rows' + tag);
  hold(w, new RegExp(`/api/office/docs/${doc3.id}(/items|/parts/\\d+(/items)?)?$`));
  const busy3 = () => w.eval('[...OFD_WS.values()].some(W => W.pend)');
  const idle3 = () => until(() => w.eval('OFD.saving') === 0 && !busy3());
  const partNow = async () => ((await call('GET', `/api/office/docs/${doc3.id}`)).parts || []).find(p => p.id === PM);
  const n3 = w.__n;
  change(w, prow()[0].querySelector('[data-k="qty"]'), '2');
  change(w, prow()[1].querySelector('[data-k="qty"]'), '3');
  change(w, prow()[2].querySelector('[data-k="qty"]'), '4');
  check(prow().map(r => r.querySelector('[data-k="qty"]').value).join() === '2,3,4', 'M: the three values stand at once' + tag);
  check(prow().every(r => r.classList.contains('rw-saving')), 'M: all three rows say "Saving…"' + tag);
  check(!!d.querySelector(`${BM} .tptotals.rwcalc .rwcalcl`), 'M: the part\'s sums say "Calculating…"' + tag);
  check(await until(() => w.__q.length === 1), 'M: the first save is on its way' + tag);
  const tm = prow()[1].querySelector('[data-k="title"]');
  tm.focus(); tm.value = 'Zwei lang'; tm.dispatchEvent(new w.Event('input', {bubbles: true}));
  for (let t = 0; t < 200 && (busy3() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await idle3(), 'M: saved' + tag);
  check(w.__n - n3 >= 1 && w.__n - n3 <= 2, `M: the changes that waited joined one save (${w.__n - n3} saves for three changes)` + tag);
  let pm = await partNow();
  check((pm?.items || []).map(x => +x.qty).join() === '2,3,4', 'M: all three on the server: ' + (pm?.items || []).map(x => x.qty).join() + tag);
  const tm2 = prow()[1].querySelector('[data-k="title"]');
  check(d.activeElement === tm2 && tm2.value === 'Zwei lang', `M: the typed text and the focus stay through the answers (${tm2?.value})` + tag);
  check(!d.querySelector(`${BM} .rwmark`) && !d.querySelector(`${BM} .tptotals.rwcalc`), 'M: no mark, the sums are back' + tag);
  change(w, tm2, 'Zwei lang');
  check(await until(() => w.__q.length === 1), 'M: the title\'s save' + tag);
  w.__go(); check(await idle3(), 'M: the title saved' + tag);
  change(w, prow()[2].querySelector('[data-k="qty"]'), '9');
  check(await until(() => w.__q.length === 1), 'M: a save that will fail' + tag);
  w.__fail(500);
  check(await until(() => prow()[2]?.classList.contains('rw-failed') && !!prow()[2].querySelector('[data-rwagain]')), 'M: the row says "Not saved" with "Try again"' + tag);
  check(prow()[2].querySelector('[data-k="qty"]').value === '9', 'M: the value stays' + tag);
  click(w, prow()[2].querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'M: Try again sends it' + tag);
  w.__go(); check(await idle3(), 'M: saved' + tag);
  pm = await partNow();
  check(+(pm?.items || [])[2]?.qty === 9 && (pm?.items || [])[1]?.title === 'Zwei lang' && !d.querySelector(`${BM} .rwmark`), `M: on the server (${(pm?.items || []).map(x => x.title + ':' + x.qty).join()}), no mark` + tag);
  check(!d.querySelector('.ofdcf'), 'M: no conflict bar' + tag);

  // ================= N (#7496). the calculation sheet of a shoot part: three quick changes, typing, an error
  check((await call('PUT', '/api/office/settings', {industry_packs: ['film']})).status === 200, 'N: the film pack on' + tag);
  const role = await call('POST', '/api/office/crew', {name_de: 'Kamera', name_en: 'Camera', rate_day: 650, intext: 'intern'});
  const PN = partOf(await call('POST', `/api/office/docs/${doc3.id}/parts`, {kind: 'shoot', title: 'Dreh'}))?.id;
  check(PN > 0, 'N: a shoot part' + tag);
  check((await call('PATCH', `/api/office/docs/${doc3.id}/parts/${PN}`, {sheet: {head: {shoot_days: 1}, staff: [{role_id: role.id, qty: 1, prep: 0}], discount_pct: 0}})).status === 200, 'N: its sheet' + tag);
  w.__off(); await w.eval(`ofdLoadDoc(${doc3.id}, true)`); w.eval('ofdDraw()');
  check(await until(() => d.querySelector(`.tplist [data-tog][data-pid="${PN}"]`)), 'N: the part is listed' + tag);
  click(w, d.querySelector(`.tplist [data-tog][data-pid="${PN}"]`));
  const SN = () => d.querySelector(`.dksheet[data-pid="${PN}"]`), dk = k => SN()?.querySelector(`[data-dk="${k}"]`);
  check(await until(() => dk('head.shoot_days') && dk('staff.0.qty')), 'N: the sheet is open' + tag);
  await sleep(100);  // the editor wires the sheet right after drawing it (office_parts.js: setTimeout 0)
  hold(w, new RegExp(`/api/office/docs/${doc3.id}(/items|/parts/\\d+(/items)?)?$`));
  const sheetNow = async () => ((await call('GET', `/api/office/docs/${doc3.id}`)).parts || []).find(p => p.id === PN)?.sheet || {};
  const n4 = w.__n;
  change(w, dk('head.shoot_days'), '2');
  change(w, dk('staff.0.qty'), '3');
  change(w, dk('discount_pct'), '5');
  check(dk('head.shoot_days').value === '2' && dk('staff.0.qty').value === '3' && dk('discount_pct').value === '5', 'N: the three values stand at once (no jump back)' + tag);
  check(SN().classList.contains('rw-saving') && !!SN().querySelector('.dktotals.rwcalc .rwcalcl'), 'N: the sheet says "Saving…", its sums "Calculating…"' + tag);
  check(await until(() => w.__q.length === 1), 'N: the first save is on its way' + tag);
  const nt = dk('head.nights');
  nt.focus(); nt.value = '4'; nt.dispatchEvent(new w.Event('input', {bubbles: true}));
  for (let t = 0; t < 200 && (busy3() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await idle3(), 'N: saved' + tag);
  check(w.__n - n4 >= 1 && w.__n - n4 <= 2, `N: the changes that waited joined one save (${w.__n - n4} saves for three changes)` + tag);
  let sn = await sheetNow();
  check(+sn.head?.shoot_days === 2 && +sn.staff?.[0]?.qty === 3 && +sn.discount_pct === 5, `N: all three on the server (${sn.head?.shoot_days}, ${sn.staff?.[0]?.qty}, ${sn.discount_pct})` + tag);
  check(d.activeElement === dk('head.nights') && dk('head.nights').value === '4', `N: the typed value and the focus stay through the answers (${dk('head.nights')?.value})` + tag);
  check(!SN().classList.contains('rw-saving') && !SN().querySelector('.rwmark') && !SN().querySelector('.dktotals.rwcalc'), 'N: no mark, the sums are back' + tag);
  check(+w.eval(`tpPart(OFD.doc, ${PN}).calc?.net || 0`) > 0, 'N: the figures from the answer' + tag);
  change(w, dk('head.nights'), '4');
  check(await until(() => w.__q.length === 1), 'N: a save that will fail' + tag);
  w.__fail(500);
  check(await until(() => SN()?.classList.contains('rw-failed') && !!SN().querySelector('[data-rwagain]')), 'N: the sheet says "Not saved" with "Try again"' + tag);
  check(dk('head.nights').value === '4', 'N: the value stays' + tag);
  click(w, SN().querySelector('[data-rwagain]'));
  check(await until(() => w.__q.length === 1), 'N: Try again sends it' + tag);
  w.__go(); check(await idle3(), 'N: saved' + tag);
  sn = await sheetNow();
  check(+sn.head?.nights === 4 && !SN().querySelector('.rwmark'), `N: on the server (${sn.head?.nights}), no mark` + tag);
  check(!d.querySelector('.ofdcf'), 'N: no conflict bar' + tag);
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
