// 2.1469 B (#6370, decision A, step 1) UI tests (jsdom), fresh DB: the "New" of an area sits in one place per layout
// - a computer: ONE blue button in the head bar next to the title (core.js headNew, btn pri, one size) for Notes, Tables,
//   Knowledge, Calendar and Files; their old buttons inside the view are gone; the round + stays hidden
// - the button creates the area's main object (a note, a table, a page, an event; Files: the file field) and Back leads out again
// - a phone: no head button, the round + carries the area's main object (its label says which), a tap creates it; holding it
//   opens the small menu with the further kinds where an area has some (Knowledge: Today, New folder)
// kalmido-suite: fresh
const {boot, errs, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const pe = (w, el, type) => {  // a touch pointer (jsdom: a MouseEvent with pointerType)
  const C = w.PointerEvent || w.MouseEvent, ev = new C(type, {bubbles: true, cancelable: true, clientX: 30, clientY: 30, button: 0});
  for (const [k, v] of [['pointerId', 1], ['pointerType', 'touch']]) if (ev[k] !== v) Object.defineProperty(ev, k, {value: v});
  el.dispatchEvent(ev); return ev;
};
const heads = d => [...d.querySelectorAll('#top .hnew')];
const label = d => heads(d)[0]?.getAttribute('aria-label') || '';

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call('GET', '/api/state');
  const feats = new Set((st0.settings?.features || '').split(',').filter(Boolean));
  for (const f of ['collab', 'cal', 'events', 'wiki', 'sheets', 'files', 'docs']) feats.add(f);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: [...feats].join(','), workspace: 'private'});

  // ================= a computer: the head bar's New
  let w = await boot({user: 'alice', hash: 'notes'}), d = w.document;
  const area = async (hash, want) => {
    w.eval(`go(${JSON.stringify(hash)})`);
    const okh = await until(() => w.eval('S.route.mod') === hash && heads(d).length === 1 && label(d) === want);
    const b = heads(d)[0];
    check(okh && b.classList.contains('btn') && b.classList.contains('pri') && !b.classList.contains('sm'), `${hash}: one blue "${want}" in the head bar, one size (${label(d)} / ${b?.className})`);
    check(d.querySelector('#fab').classList.contains('gone'), `${hash}: no round + on a computer`);
    return b;
  };
  // Notes: a new quick note, Back leads to the notes again
  let b = await area('notes', 'New note');
  check(!d.querySelector('#view [data-sb="note-new"], #side .sbnbar [data-sb="note-new"]'), 'notes: no second "New note" in the list');
  b.click();
  check(await until(() => w.eval('S.nt.id === QN_DRAFT') && !!d.querySelector('#nt-body')), 'notes: the head button opens a new note');
  w.eval("go('notes')");
  check(await until(() => w.eval("S.route.mod === 'notes' && !S.nt.draft") && heads(d).length === 1), 'notes: back in the overview, the button again');
  // Tables
  b = await area('sheets', 'New table');
  check(!d.querySelector('#view [data-shv="new"]'), 'tables: no second "New table" in the overview');
  w.prompt = () => 'Kit list';
  b.click();
  check(await until(() => /^#sheets\/\d+$/.test(w.location.hash) && w.eval('!!SHV.sh')), 'tables: the head button makes a table and opens it ' + w.location.hash);
  check(await until(() => !heads(d).length), 'tables: no "New table" inside an open table');
  w.history.back();
  check(await until(() => w.location.hash === '#sheets' && heads(d).length === 1), 'tables: Back leads to the overview with its button');
  // Knowledge: a page; the arrow beside it has Today and New folder
  b = await area('wiki', 'New page');
  check(![...d.querySelectorAll('#view [data-wk="new"]')].some(x => !x.closest('.zleempty')), 'knowledge: no second "New page" in the view (the empty state keeps its own, #6371)');
  const more = d.querySelector('#top .hnewm');
  if (more) {
    more.click();
    const it = [...d.querySelectorAll('#pop button')].map(x => x.textContent.trim());
    check(await until(() => !d.querySelector('#pop').classList.contains('hidden')) && it.some(t => /New page/.test(t)) && it.some(t => /Today/.test(t)), 'knowledge: the arrow opens the small menu (New page first, Today) ' + it.join(' | '));
    w.eval('closePop()');
  } else check(w.eval("wk_all() && !wk_open()"), 'knowledge: "All" shows no further kinds (the arrow only in one space)');
  w.prompt = () => 'Start';
  b.click();
  check(await until(() => !!d.querySelector('#wk-body') || /^#wiki\//.test(w.location.hash) && !!w.eval('WK.pg')), 'knowledge: the head button makes a page and opens it ' + w.location.hash);
  // Calendar: "New event" (no longer in the middle of the calendar's bar)
  b = await area('cal', 'New event');
  check(!d.querySelector('#view .calbar [data-act="ev-new"]'), 'calendar: "+ Event" left the calendar\'s bar');
  b.click();
  check(await until(() => !!d.querySelector('.modal.evmodal')), 'calendar: the head button opens a new event');
  d.querySelector('.modal.evmodal [data-evm="close"]')?.click();
  check(await until(() => !d.querySelector('.modal.evmodal')), 'calendar: closed again');
  // Files: Upload (the file field of the shown place)
  b = await area('ablage', 'Upload');
  check(!d.querySelector('#view .abtools [data-ab="upload"]'), 'files: no second Upload in the tools');
  const fi = await until(() => d.querySelector('#ab-file')); let picked = 0;
  if (fi) fi.addEventListener('click', () => picked++);
  heads(d)[0].click();
  check(picked === 1, 'files: the head button opens the file picker of the shown place');
  check(errs.length === 0, 'computer: no script errors: ' + errs.join(' | '));
  w.close();

  // ================= a phone: the round + carries the area's New
  w = await boot({user: 'alice', hash: 'wiki', mobile: true}); d = w.document;
  const fab = d.querySelector('#fab');
  const onFab = async (hash, want) => {
    w.eval(`go(${JSON.stringify(hash)})`);
    const okf = await until(() => w.eval('S.route.mod') === hash && !fab.classList.contains('gone') && fab.getAttribute('aria-label') === want);
    check(okf && !heads(d).length, `phone ${hash}: the round + says "${want}", no head button (${fab.getAttribute('aria-label')})`);
  };
  await onFab('wiki', 'New page');
  pe(w, fab, 'pointerdown');
  check(await until(() => !d.querySelector('#pop').classList.contains('hidden') && [...d.querySelectorAll('#pop button')].some(x => /New page/.test(x.textContent))), 'phone wiki: holding the + opens the small menu');
  pe(w, fab, 'pointerup'); fab.click(); w.eval('closePop()');
  check(!d.querySelector('#wk-body'), 'phone wiki: the end of the hold creates nothing');
  await onFab('notes', 'New note');
  await until(() => !w.eval('ms_lpRecent(QN_FAB)'));  // the hold above is over (its click is swallowed for a moment)
  fab.click();
  check(await until(() => w.eval('S.nt.id === QN_DRAFT') && !!d.querySelector('#nt-body')), 'phone notes: a tap on the + opens a new note');
  w.eval("go('notes')");
  await onFab('cal', 'New event');
  fab.click();
  check(await until(() => !!d.querySelector('.modal.evmodal')), 'phone calendar: a tap on the + opens a new event');
  d.querySelector('.modal.evmodal [data-evm="close"]')?.click();
  check(await until(() => !d.querySelector('.modal.evmodal')), 'phone calendar: closed again');
  w.eval("go('today')");
  check(await until(() => !fab.classList.contains('gone') && fab.getAttribute('aria-label') === 'New task'), 'phone Today: the + is "New task" again');
  check(errs.length === 0, 'phone: no script errors: ' + errs.join(' | '));
  w.close();
  console.log(`p21469_b_newbtn_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
