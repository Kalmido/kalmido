// (#7484) UI tests (jsdom), fresh DB: a new note never conflicts with itself
// kalmido-suite: fresh
// - a new note, the server's answer to "create" already back: typing on (title, then text) saves without a conflict dialog
//   (rollback test: before, the note kept the device's clock as its base and the next change got a 409 "Changed in the
//   meantime by Alice")
// - typed while "create" is still on its way, then typed again while that change is on its way: no dialog, the last text on
//   the server (a change waiting behind one on its way moves on to the new base)
// - a quick note (one text field, made by its first character): typing on after the answer, no dialog
// - this tab's own write the base missed (the stamp not taken over): no dialog, mine saved; a change made elsewhere still asks
const {boot, errs, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const type = (w, sel, v) => { const el = w.document.querySelector(sel); el.focus(); el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); return el; };
// a slow server for one kind of write (re = the address): those wait in w.__held until release (all else goes on)
const hold = (w, re) => {
  w.__held = []; w.__holdRe = re; if (w.__f0) return; const f0 = w.__f0 = w.fetch;
  w.fetch = (u, o = {}) => w.__holdRe && w.__holdRe.test(String(u)) && (o.method || 'GET') !== 'GET'
    ? new Promise((res, rej) => w.__held.push(() => f0(u, o).then(res, rej))) : f0(u, o);
};
const release = w => { w.__holdRe = null; for (const go of w.__held.splice(0)) go(); };
const dlg = w => w.document.querySelector('.modal.cdlg');
const settled = w => until(() => w.eval('OUT.q.length') === 0 && !w.eval('OUT.flushing'));
const note = id => call('GET', `/api/notes/${id}`);
const flush = w => w.eval('noteFlush()');

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'collab'});
  const P = (await call('POST', '/api/lists', {name: 'Garden'})).id;
  const w = await boot({user: 'alice', hash: 'notes/' + P});
  check(await until(() => w.eval('!!S.me && S.lists.length > 0') && !!w.document.querySelector('[data-act="nt-new"]')), 'setup: the notes of the project are up');
  w.__dialogs = 'manual';  // a conflict dialog stays open (and is seen)

  // ================= A: a new note, its "create" answered, then typing on (rollback test of #7484)
  w.document.querySelector('[data-act="nt-new"]').click();
  check(await until(() => w.eval('S.nt.id') > 0 && !!w.document.querySelector('#nt-title')), 'A: the new note has its real id (the answer is back) ' + w.eval('S.nt.id'));
  const NA = w.eval('S.nt.id');
  check(w.eval(`S.nt.notes.find(n => n.id === ${NA}).updated_at`) === (await note(NA)).updated_at, "A: the note's base is the server's stamp, not the device's clock");
  type(w, '#nt-title', 'Shopping');
  await flush(w);
  check(await settled(w), 'A: the title went out');
  check(!dlg(w), 'A: no conflict dialog after the first typing ' + (dlg(w)?.textContent || ''));
  check((await note(NA)).title === 'Shopping', 'A: the title is on the server');
  w.document.querySelector('[data-act="nt-mode"][data-m="edit"]')?.click();
  check(!!await until(() => w.document.querySelector('#nt-body')), 'A: edit mode');
  type(w, '#nt-body', 'Milk');
  await flush(w);
  check(await settled(w), 'A: the text went out');
  check(!dlg(w), 'A: no conflict dialog on the second change');
  check((await note(NA)).body === 'Milk', 'A: the text is on the server');

  // ================= B: typed while "create" is on its way, typed again while that change is on its way
  w.location.hash = '#notes/' + P;
  check(await until(() => !!w.document.querySelector('[data-act="nt-new"]')), 'B: back in the list');
  hold(w, /\/api\/lists\/\d+\/notes$/);
  w.document.querySelector('[data-act="nt-new"]').click();
  check(await until(() => w.eval('S.nt.id') < 0 && !!w.document.querySelector('#nt-title')), 'B: open at once with a temporary id');
  type(w, '#nt-title', 'Trip');
  await flush(w);
  check(w.eval('OUT.q.length') === 2, 'B: the change waits behind the create ' + w.eval('OUT.q.length'));
  release(w); hold(w, /\/api\/notes\/\d+$/);  // the create goes, the change after it is held
  check(await until(() => w.eval('S.nt.id') > 0 && w.__held.length === 1), 'B: the create answered, its change on its way');
  const NB = w.eval('S.nt.id');
  type(w, '#nt-title', 'Trip north');
  await flush(w);
  check(w.eval('OUT.q.length') === 2, 'B: a second change waits behind the one on its way');
  release(w);
  check(await settled(w), 'B: all went out');
  check(!dlg(w), 'B: no conflict dialog ' + (dlg(w)?.textContent || ''));
  check((await note(NB)).title === 'Trip north', 'B: the last title is on the server ' + (await note(NB)).title);
  check(!w.eval("(S.conflicts || []).some(c => c.field === 'rejected')"), 'B: nothing in the conflicts list');

  // ================= C: a quick note: made by its first character, typing on after the answer
  await w.eval('qn_new()');
  check(await until(() => w.eval('S.nt.id') === w.eval('QN_DRAFT') && !!w.document.querySelector('#nt-body')), 'C: the quick note is open');
  type(w, '#nt-body', 'Call the plumber');
  await flush(w);
  check(await until(() => w.eval('S.nt.id') > 0) && await settled(w), 'C: made, its real id ' + w.eval('S.nt.id'));
  const NC = w.eval('S.nt.id');
  type(w, '#nt-body', 'Call the plumber\nabout the boiler');
  await flush(w);
  check(await settled(w), 'C: the change went out');
  check(!dlg(w), 'C: no conflict dialog ' + (dlg(w)?.textContent || ''));
  check((await note(NC)).body === 'Call the plumber\nabout the boiler', 'C: the text is on the server');

  // ================= D: this tab's own write the base missed: no dialog; a change made elsewhere still asks
  const ND = await call('POST', `/api/lists/${P}/notes`, {title: 'Agenda', body: 'Old'});
  w.location.hash = '#notes/' + P;
  check(await until(() => w.eval(`S.nt.lid === ${P}`) && !!w.document.querySelector('[data-act="nt-new"]')), 'D: back in the project');
  await w.eval('load()'); await w.eval(`loadNotes(${P})`);
  w.location.hash = '#note/' + ND.id;
  check(await until(() => w.eval(`S.nt.id === ${ND.id}`) && !!w.document.querySelector('#nt-title')), 'D: open');
  w.document.querySelector('[data-act="nt-mode"][data-m="edit"]')?.click();
  check(!!await until(() => w.document.querySelector('#nt-body')), 'D: edit mode');
  type(w, '#nt-body', 'Mine first');
  await flush(w);
  check(await settled(w), 'D: the first change went out');
  w.eval(`S.nt.notes.find(n => n.id === ${ND.id}).updated_at = ${JSON.stringify(ND.updated_at)}`);  // its stamp not taken over
  type(w, '#nt-body', 'Mine first and second');
  await flush(w);
  check(await settled(w), 'D: the second change went out');
  check(!dlg(w), 'D: own write behind the old base: no dialog ' + (dlg(w)?.textContent || ''));
  check((await note(ND.id)).body === 'Mine first and second', 'D: mine is on the server');
  await call('PATCH', `/api/notes/${ND.id}`, {body: 'Changed on the phone'});
  type(w, '#nt-body', 'Typed on the laptop');
  await flush(w);
  const cd = await until(() => dlg(w));
  check(!!cd && cd.textContent.includes('Changed on the phone') && cd.textContent.includes('Typed on the laptop'), 'D: a change made elsewhere still shows both versions');
  cd?.querySelector('[data-cd="yes"]')?.click();
  check(await until(async () => (await note(ND.id)).body === 'Typed on the laptop') && await settled(w), 'D: "Keep mine" saves mine');

  check(errs.length === 0, 'no script errors: ' + errs.join(' | '));
  w.close();
  console.log(`p21474_a_notenew_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
