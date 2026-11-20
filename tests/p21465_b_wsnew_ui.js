// kalmido-suite: fresh
// Package 2.1465 part B UI test (#7309): every "new" dialog names its workspace from the shared place (accounts/wsplace.py,
// areas.js wsp_list / wsp_ask / wsp_post, workspace.js wsNewSpace / wsAskNew) - never the first organisation, never quietly
// Private, never where the module is off. jsdom, invented data only.
// The matrix (thinned out pairwise): situation on top (All / All with the module on in one workspace only = it opens that one /
// an organisation chosen / Private chosen) x office + clients, calendar, contacts, documents on / off in Private and per
// organisation x organisations (0 / 1 / 1 read-only / 2) x the way (clients page, palette "Add client", New calendar, New address
// book, New contact, upload, Move to another workspace). Each row checks: where did it land AND does the list one comes back to
// show it (a fresh page in the same situation).
// freelancer-matrix: clients / events / contacts / docs -- frida has no organisation: nothing asks, everything is private and listed.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const CK = {};
const call = async (u, method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK[u]}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...await r.json().catch(() => ({})), http: r.status};
  }
};
const until = (fn, n = 100) => require('./boot').until(fn, {timeout: n * 150, step: 150});
const typeIn = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
const pickSel = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const WANT = ['cal', 'events', 'contacts', 'office', 'clients', 'docs', 'files', 'comments', 'collab'];
const J = o => JSON.stringify(o);

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: J({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK.alice = await login('alice');
  await call('alice', 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'contacts', 'office', 'clients']});
  const feats = async u => {
    await call(u, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
    const have = ((await call(u, 'GET', '/api/state')).settings?.features || '').split(',').filter(Boolean);
    for (const f of WANT) if (!have.includes(f) && (await call(u, 'PATCH', '/api/settings', {features: [...have, f].join(',')})).http < 300) have.push(f);
    return have;
  };
  const fa = await feats('alice');
  check(['events', 'contacts', 'clients', 'docs'].every(f => fa.includes(f)), 'the modules are on: ' + fa);
  const me = (await call('alice', 'GET', '/api/state')).me;
  const O1 = (await call('alice', 'POST', '/api/admin/orgs', {name: 'Studio Nord', admin_id: me.id})).id;
  const O2 = (await call('alice', 'POST', '/api/admin/orgs', {name: 'Atelier Süd', admin_id: me.id})).id;
  check(O1 > 0 && O2 > 0, 'two organisations');
  const N = 'org:' + O1, S = 'org:' + O2, P = 'private';
  const mkUser = async (u, nm, orgs) => {
    const x = await call('alice', 'POST', '/api/users', {username: u, display_name: nm, password: 'password123', email: u + '@example.com', ...(orgs ? {orgs} : {})});
    check(x.http < 300, 'user ' + u + ' ' + x.http + ' ' + (x.error || ''));
    CK[u] = await login(u); await feats(u);
  };
  await mkUser('bert', 'Bert Eins', [{id: O1, role: 'member'}]);
  await mkUser('rita', 'Rita Rot', [{id: O1, role: 'readonly'}]);
  await mkUser('frida', 'Frida Frei', null);
  const set = (u, b) => call(u, 'PATCH', '/api/settings', Object.fromEntries(Object.entries({ws_areas_off: {}, ws_mods_off: {}, ...b}).map(([k, v]) => [k, typeof v === 'object' ? J(v) : v])));
  const nm = ws => ws === P ? 'Private' : ws === N ? 'Nord' : ws === S ? 'Süd' : ws;
  const wsOf = o => o && o.org_id ? 'org:' + o.org_id : P;

  // the choice a dialog offers, answered: the select of the dialog (#cl-ws, #ws-new) or the server's question (wsp_ask radios)
  const offered = d => {
    const sel = d.querySelector('.modal.cldlg #cl-ws, .cdlg #ws-new');
    if (sel) return [...sel.options].map(o => o.value).filter(Boolean);
    const rs = [...d.querySelectorAll('.cdlg input[name="wsp-ask"]')].map(x => x.value);
    return rs.length ? rs : null;
  };
  const answerAsk = async (w, d, pick) => {  // the server's question after sending (wsp_post / dc_upload)
    const q = await until(() => d.querySelector('.cdlg input[name="wsp-ask"]'), 12);
    if (!q) return null;
    const rs = [...d.querySelectorAll('.cdlg input[name="wsp-ask"]')].map(x => x.value);
    const t = d.querySelector(`.cdlg input[name="wsp-ask"][value="${pick}"]`); if (t) t.checked = true;
    d.querySelector('.cdlg [data-cd="yes"]').click();
    return rs;
  };

  // ---- the ways: each creates `name`, answers a choice with `pick`, returns the choice it saw (null = no question)
  const WAYS = {
    async client(w, d, name, pick, palette = false) {
      if (palette) { await until(() => w.eval('typeof palAll === "function"'), 60); w.eval(`palAll().find(x => x.id === 'a:cl-new').fn()`); }
      else { await until(() => d.querySelector('#view [data-act="client-new"]'), 80); d.querySelector('#view [data-act="client-new"]').click(); }
      const md = await until(() => d.querySelector('.modal.cldlg'), 60);
      let seen = offered(d);
      const sel = md.querySelector('#cl-ws'); if (sel && pick) pickSel(w, sel, pick);
      typeIn(w, md.querySelector('#cl-name'), name);
      md.querySelector('[data-m="save"]').click();
      const late = await answerAsk(w, d, pick); if (late) seen = late;
      await until(() => !d.body.contains(md), 60);
      return seen;
    },
    async calendar(w, d, name, pick) {
      await until(() => typeof w.evCalsModal === 'function' || w.eval('typeof loadModule') === 'function', 60);
      if (typeof w.evCalsModal !== 'function') await w.eval(`loadModule('calendar')`).catch(() => {});
      w.evCalsModal();
      const b = await until(() => d.querySelector('[data-evc="new"]'), 60); b.click();
      return WAYS._named(w, d, name, pick);
    },
    async book(w, d, name, pick) {
      await until(() => typeof w.ctBooksModal === 'function', 60);
      w.ctBooksModal();
      const b = await until(() => d.querySelector('[data-cb="new"]'), 60); b.click();
      return WAYS._named(w, d, name, pick);
    },
    async _named(w, d, name, pick) {  // workspace.js wsAskNew: the name and (several workspaces) the required choice
      const inp = await until(() => d.querySelector('.cdlg #cdlg-in'), 40);
      let seen = offered(d);
      WAYS.hint = d.querySelector('.cdlg .wsnew')?.textContent || '';
      typeIn(w, inp, name);
      const sel = d.querySelector('.cdlg #ws-new');
      if (sel) {  // first without a choice when nothing is preselected: the dialog stays
        // nothing preselected: Create waits for the choice (disabled; jsdom's click on a disabled button is not the browser's,
        // so the state is read, not clicked - p21398_a_modspaces_ui walks the dialog in Firefox)
        if (!sel.value) WAYS.stayed = !!d.querySelector('.cdlg [data-cd="yes"]')?.disabled;
        if (pick) pickSel(w, sel, pick);
      }
      const yes = d.querySelector('.cdlg [data-cd="yes"]');
      if (!yes) { console.log('DIAG _named: the dialog is gone', J({seen, stayed: WAYS.stayed, toasts: [...d.querySelectorAll('.toast, #toast')].map(x => x.textContent)})); return seen; }
      yes.click();
      const late = await answerAsk(w, d, pick); if (late) seen = late;
      await sleep(400);
      return seen;
    },
    async contact(w, d, name, pick) {  // New contact: without a book one may add to here, "Create your own address book" first
      await until(() => typeof w.ctEditor === 'function' && w.S?.books, 60);
      w.ctEditor(null);
      let seen = null;
      const first = await until(() => d.querySelector('#ct-given') || d.querySelector('.cdlg [data-cd="yes"]'), 60);
      if (first && !first.matches('#ct-given')) { first.click(); seen = await answerAsk(w, d, pick); }
      const g = await until(() => d.querySelector('#ct-given'), 60);
      WAYS.books = [...d.querySelectorAll('#ct-bk option')].map(o => w.eval(`JSON.stringify(ctBook(${+o.value}) || null)`)).map(x => JSON.parse(x)).filter(Boolean);
      typeIn(w, g, name);
      d.querySelector('[data-ctm2="save"]').click();
      await until(() => !d.querySelector('#ct-given'), 60);
      return seen;
    },
    async upload(w, d, name, pick) {
      await until(() => typeof w.dc_upload === 'function', 80);
      const p = w.eval(`dc_upload([new File(['%PDF-1.4 ${name}'], '${name}.pdf', {type: 'application/pdf'})])`);
      const seen = await answerAsk(w, d, pick);
      await p;
      return seen;
    },
  };
  // the list one comes back to: a fresh page in the same situation shows the new entry
  const LISTS = {
    client: {hash: 'clients', shown: (w, d, name) => (d.querySelector('#view')?.textContent || '').includes(name)},
    calendar: {hash: 'cal', shown: async (w, d, name) => { w.evCalsModal(); return !!await until(() => [...d.querySelectorAll('.evcnm')].some(x => x.textContent === name), 40); }},
    book: {hash: 'contacts', shown: async (w, d, name) => { w.ctBooksModal(); return !!await until(() => (d.querySelector('#cb-body')?.textContent || '').includes(name), 40); }},
    contact: {hash: 'contacts', shown: (w, d, name) => (d.querySelector('#view')?.textContent || '').includes(name)},
    upload: {hash: 'ablage/docs', shown: (w, d, name) => w.eval(`(typeof DC === 'object' && DC.docs || []).some(x => (x.name || '').startsWith(${J(name)}))`)},
  };
  const WHERE = {
    client: async (u, name) => wsOf((await call(u, 'GET', '/api/clients')).clients?.find(c => c.name === name)),
    calendar: async (u, name) => wsOf((await call(u, 'GET', '/api/state')).evcals?.find(c => c.name === name)),
    book: async (u, name) => wsOf((await call(u, 'GET', '/api/state')).books?.find(c => c.name === name)),
    contact: async (u, name) => { const st = await call(u, 'GET', '/api/state'), it = (await call(u, 'GET', '/api/contacts?q=' + encodeURIComponent(name))).items?.[0]; return it ? wsOf(st.books?.find(b => b.id === it.book_id)) : null; },
    upload: async (u, name) => wsOf((await call(u, 'GET', '/api/docs?ws=all&limit=200')).docs?.find(x => (x.name || '').startsWith(name))),
  };

  let n = 0;
  const row = async ({u = 'alice', top, off = {}, aoff = {}, way, palette = false, ask, pick = null, land, hint = null}) => {
    const tag = `[${u} ${top} ${way}${palette ? ' (palette)' : ''} ${J({off, aoff})}] `, name = `W${++n} ${way}`;
    check((await set(u, {workspace: top, ws_mods_off: off, ws_areas_off: aoff})).http === 200, tag + 'switches');
    const kind = way === 'client' ? 'client' : way;
    let w = await boot({user: u, hash: palette ? 'inbox' : LISTS[kind].hash, allWs: true}), d = w.document;
    await until(() => w.S?.me && w.S.booted !== false && d.querySelector('#view')?.children.length, 80);
    await sleep(1500);  // the page settles first (a view drawn late closes the dialogs opened before it)
    WAYS.hint = ''; WAYS.stayed = null;
    const seen = await WAYS[way](w, d, name, pick, palette);
    check(J(seen) === J(ask), tag + 'the choice offered: ' + J(seen) + ' wanted ' + J(ask));
    if (ask && ask.length > 1 && WAYS.stayed !== null) check(WAYS.stayed, tag + 'without a choice the dialog stays');
    if (hint) check(WAYS.hint.includes(hint), tag + 'the dialog names where it goes: ' + J(WAYS.hint));
    const at = await WHERE[kind](u, name);
    check(at === land, tag + 'landed in ' + nm(at) + ', wanted ' + nm(land));
    // back to the list (another page, then the list again - the same window, as a person goes back)
    d.querySelectorAll('.modal').forEach(m => m.remove());
    w.location.hash = '#inbox'; await sleep(300); w.location.hash = '#' + LISTS[kind].hash;
    await until(() => d.querySelector('#view'), 80);
    if (kind === 'upload') await until(() => w.eval(`typeof DC === 'object' && !!DC.docs`), 80);
    check(!!await until(async () => await LISTS[kind].shown(w, d, name), 60), tag + 'the list one comes back to shows it');
    w.close();
    return name;
  };
  const OFF = mods => ({...mods});

  // ================= alice: two organisations (admin of both)
  // clients page / palette
  await row({top: 'all', way: 'client', ask: [P, N, S], pick: S, land: S});
  await row({top: 'all', aoff: {[P]: ['office']}, way: 'client', palette: true, ask: [N, S], pick: N, land: N});  // office + clients off in Private
  await row({top: 'all', off: OFF({[P]: ['clients'], [N]: ['clients']}), way: 'client', ask: null, land: S});  // All > Süd: the only one, no question
  await row({top: P, off: OFF({[N]: ['clients']}), way: 'client', palette: true, ask: null, land: P});  // Private chosen
  // calendar
  await row({top: 'all', way: 'calendar', ask: [P, N, S], pick: N, land: N});  // several: required, nothing preselected
  await row({top: 'all', off: OFF({[P]: ['events'], [S]: ['events']}), way: 'calendar', ask: null, land: N, hint: 'Studio Nord'});  // All > Nord
  await row({top: P, way: 'calendar', ask: [P, N, S], land: P});  // Private chosen: preselected, kept
  // address book
  await row({top: N, way: 'book', ask: [P, N, S], land: N});  // an organisation chosen: preselected
  await row({top: 'all', aoff: {[P]: ['office']}, way: 'book', ask: [N, S], pick: S, land: S});  // Contacts off in Private: not offered
  // documents
  await row({top: 'all', way: 'upload', ask: [P, N, S], pick: S, land: S});  // under All: asks (was: always Private)
  await row({top: 'all', off: OFF({[P]: ['docs'], [N]: ['docs']}), way: 'upload', ask: null, land: S});  // All > Süd
  const upN = await row({top: N, way: 'upload', ask: null, land: N});

  // ================= bert: one organisation, member
  await row({u: 'bert', top: 'all', way: 'client', ask: [P, N], pick: N, land: N});
  await row({u: 'bert', top: 'all', aoff: {[N]: ['office']}, way: 'client', ask: null, land: P});  // office + clients off in Nord
  await row({u: 'bert', top: 'all', off: OFF({[P]: ['contacts']}), way: 'book', ask: null, land: N, hint: 'Studio Nord'});
  // New contact without a book of his own: "Create your own address book" goes where Contacts is on (here Nord), the contact too
  const bertBooks = (await call('bert', 'GET', '/api/state')).books || [];
  for (const b of bertBooks) await call('bert', 'DELETE', '/api/books/' + b.id);
  await row({u: 'bert', top: 'all', off: OFF({[P]: ['contacts']}), way: 'contact', ask: null, land: N});
  check(WAYS.books.length > 0 && WAYS.books.every(b => b.org_id === O1), '[bert contact] the editor offers only books where Contacts is on: ' + J(WAYS.books.map(b => b.org_id)));

  // ================= rita: one organisation, read-only
  await row({u: 'rita', top: 'all', way: 'client', ask: null, land: P});  // the only workspace she may add to
  await row({u: 'rita', top: 'all', way: 'calendar', ask: null, land: P, hint: 'Private'});

  // ================= frida: no organisation (P4): nothing asks
  await row({u: 'frida', top: 'all', way: 'client', ask: null, land: P});
  await row({u: 'frida', top: 'all', way: 'calendar', ask: null, land: P});
  await row({u: 'frida', top: 'all', way: 'upload', ask: null, land: P});

  // ================= Move to another workspace (F6): only targets where the module is on and writable for me
  await set('alice', {workspace: 'all', ws_mods_off: {[S]: ['files']}});
  let w = await boot({user: 'alice', hash: 'ablage/docs', allWs: true}), d = w.document;
  await until(() => typeof w.smv_open === 'function' && w.S?.me, 80);
  const doc = (await call('alice', 'GET', '/api/docs?ws=all&limit=200')).docs?.find(x => (x.name || '').startsWith(upN + '.'));
  check(doc && doc.org_id === O1, 'the document of Nord to move');
  const mp = w.dc_smvMove(new Map([[doc.id, doc.org_id || null]]), 'x');
  await until(() => d.querySelector('#smv-to'), 40);
  const tos = [...d.querySelectorAll('#smv-to option')].map(o => o.value);
  check(J(tos) === J([P]), 'F6: the target is only Private (Files off in Süd, Nord is the source): ' + J(tos));
  await until(() => !d.querySelector('[data-smv="yes"]')?.disabled, 60);
  d.querySelector('[data-smv="yes"]').click();
  await mp.catch(() => null);
  const moved = (await call('alice', 'GET', '/api/docs?ws=all&limit=200')).docs?.find(x => x.id === doc.id);
  check(moved && !moved.org_id, 'F6: moved to Private: ' + J(moved && moved.org_id));
  w.location.hash = '#inbox'; await sleep(300); w.location.hash = '#ablage/docs';
  check(!!await until(() => w.eval(`typeof DC === 'object' && (DC.docs || []).some(x => x.id === ${doc.id})`), 80), 'F6: the documents list under All still shows it');
  w.close();

  // ================= #7611: Files under "All workspaces": the overview has no Upload of its own (no place to put it), the +
  // never stays from the space shown before (it clicked a file field the overview does not have); a space has it again
  await set('alice', {workspace: 'all', ws_mods_off: {}});
  w = await boot({user: 'alice', hash: 'ablage', allWs: true}); d = w.document;
  check(await until(() => d.querySelector('#view .abovr'), 80), '#7611: Files under All shows the overview of the spaces');
  w.eval("go(ab_home('private'))");
  check(await until(() => d.querySelector('#ab-file') && w.eval('!!newCur()'), 80), '#7611: in Private the area\'s Upload is there with its file field');
  w.eval("go('ablage')");
  check(await until(() => d.querySelector('#view .abovr') && !d.querySelector('#ab-file'), 80), '#7611: back on the overview of All');
  check(await until(() => w.eval('!newCur()'), 40), '#7611: the overview offers no Upload that does nothing (the + / the head\'s New are gone)');
  check(w.eval('newRun()') === false, '#7611: a tap on the + there runs nothing silently');
  w.eval("go(ab_home('private'))");
  check(await until(() => d.querySelector('#ab-file') && w.eval('!!newCur()'), 80), '#7611: Private again: Upload with its file field');
  w.close();

  console.log(`p21465_b_wsnew_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
