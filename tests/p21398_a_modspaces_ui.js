// Package 2.1398.0 part A UI test (#6722): one switch, one meaning - under "All workspaces" every module shows only the
// workspaces it is on in for me (areas.js mod_spaces / mod_entryOn, docs/dev/kern.md). Firefox, 1280 px, invented data only.
// kalmido-suite: fresh
// freelancer-matrix: wiki / clients -- carol has no organisation (P4): her wiki opens directly, her client is listed.
// - an account with Private + two organisations (Nord, Süd), a knowledge page, a table, a contact and a client in each
// - case B: every module off in Private and Süd -> under "All" Knowledge opens Nord directly (no overview) and wears its colour,
//   Files / the office / Tables offer only Nord, clients / contacts list only Nord's entries
// - case C: off in Süd only -> the overview of Knowledge lists Private + Nord, not Süd
// - a page of a switched-off workspace still opens by its address (search / trash find everything)
// - everything on again -> the three spaces and all entries are back
// P21398A_NOSTART=1 = the server already runs. Screenshots: P21398A_SHOTS.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21398_a_modspaces_ui', check, shots: 'P21398A_SHOTS', allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21398A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    const j = await r.json().catch(() => ({})); return {...j, http: r.status};
  }
};
const AREAS = ['office', 'time', 'review', 'life', 'reading', 'ablage', 'wiki', 'sheets'];
const MODS = ['office', 'clients', 'contacts', 'time', 'workload', 'dispo', 'wiki', 'sheets', 'files', 'docs', 'cal', 'events'];
const off = wss => ({ws_areas_off: JSON.stringify(Object.fromEntries(wss.map(w => [w, AREAS]))), ws_mods_off: JSON.stringify(Object.fromEntries(wss.map(w => [w, MODS])))});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'anna', display_name: 'Anna Berger', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('anna');
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Studio Nord', lang: 'en', collab_all: true, modules: ['cal', 'comments', 'collab', 'office', 'clients']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'all'});
  const st0 = await call(CA, 'GET', '/api/state');
  const feats = (st0.settings?.features || '').split(',').filter(Boolean);
  for (const f of ['cal', 'events', 'contacts', 'office', 'clients', 'files', 'wiki', 'sheets', 'time']) {
    if (feats.includes(f)) continue;
    const x = await call(CA, 'PATCH', '/api/settings', {features: [...feats, f].join(',')}); if (x.http < 300) feats.push(f);
  }
  const O1 = (st0.me?.workspaces || [])[0]?.id, me = st0.me;
  check(O1 > 0, 'the first organisation (Nord)');
  const O2 = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Atelier Süd', admin_id: me.id})).id;
  check(O2 > 0, 'the second organisation (Süd)');
  await call(CA, 'PATCH', '/api/orgs/' + O1, {color: '#e0b05c'});
  await call(CA, 'PATCH', '/api/orgs/' + O2, {color: '#4cc3d9'});
  const SP = {P: ['private', null, 'Privat'], A: ['org:' + O1, O1, 'Nord'], B: ['org:' + O2, O2, 'Süd']}, ID = {};
  for (const [k, [ws, org, nm]] of Object.entries(SP)) {
    const x = ID[k] = {};
    await call(CA, 'PATCH', '/api/settings', {workspace: ws});
    x.wiki = (await call(CA, 'POST', '/api/wiki/pages', {space: ws, path: 'Handbuch ' + nm, body: 'Text ' + nm})).id;
    x.sheet = (await call(CA, 'POST', '/api/sheets', {title: 'Tabelle ' + nm, space: ws})).id;
    x.book = (await call(CA, 'POST', '/api/books', {name: 'Adressen ' + nm, org_id: org})).id;
    x.contact = (await call(CA, 'POST', '/api/contacts', {book_id: x.book, given: 'Kontakt', family: nm})).id;
    x.client = (await call(CA, 'POST', '/api/clients', {name: 'Kunde ' + nm + ' GmbH', org_id: org})).id;
  }
  await call(CA, 'PATCH', '/api/settings', {workspace: 'all'});
  check(ID.P.wiki && ID.A.wiki && ID.B.wiki && ID.A.client && ID.B.contact && ID.A.sheet, 'the data of the three workspaces ' + JSON.stringify(ID));
  // carol without an organisation (P4)
  await call(CA, 'POST', '/api/users', {username: 'carol', display_name: 'Carol Solo', password: 'password123', email: 'carol@example.com'});
  const CC = await login('carol');
  await call(CC, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,contacts,office,clients,wiki'});
  await call(CC, 'POST', '/api/wiki/pages', {space: 'private', path: 'Notizbuch Carol', body: 'x'});
  await call(CC, 'POST', '/api/clients', {name: 'Kunde Carol', org_id: null});

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const patch = (ev, body) => ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: ${JSON.stringify(JSON.stringify(body))}}).then(r => r.status)`);
  const txt = `(document.querySelector('#view')?.textContent || '')`;
  const N = 'org:' + O1;

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await signIn(ev, 'anna') === 200, 'anna signs in');
    const go = async hash => { await nav(B + 'static/icon.svg'); await nav(B + '#' + hash); await ready(ev, `!!window.S && !!S.me && !!document.querySelector('#view')`, 80); };

    // ================= case B: only Studio Nord has the modules
    check(await patch(ev, {workspace: 'all', ...off(['private', 'org:' + O2])}) === 200, 'B: modules off in Private and Süd');
    await go('wiki');
    check(await ready(ev, `typeof wk_shown === 'function' && wk_shown().join('|') === ${JSON.stringify(N)}`, 60), 'B: Knowledge shows only Nord');
    check(await ready(ev, `!wk_all() && wk_open() === ${JSON.stringify(N)} && !document.querySelector('#view .spovl, #view .zleov') && /Handbuch Nord/.test(${txt})`, 60), 'B: Knowledge opens Nord directly (no overview, its page listed)');
    check(await ready(ev, `wso_cur() === ${JSON.stringify(N)} && document.querySelector('#view').classList.contains('wac-loc')`, 40), 'B: Knowledge wears the colour of Nord');
    check(!await ev(`/Handbuch Süd|Handbuch Privat/.test(${txt})`), 'B: no page of Private / Süd in the list');
    check(await ev(`wso_scope() === ${JSON.stringify(N)}`), 'B: the frame of Knowledge wears Nord too (#6697 wso_scope on the same core)');
    check(await ev(`mod_spaces('time').join('|') === ${JSON.stringify(N)} && (typeof tv_wsLists !== 'function' || Array.isArray(tv_wsLists()))`), 'B: time tracking on in Nord only');
    await shot('p21398a-B-wiki.png');
    // a page of a switched-off workspace still opens by its address (the search and the trash find everything)
    await go('wiki/' + ID.B.wiki);
    check(await ready(ev, `WK.pg?.id === ${ID.B.wiki} && /Text Süd|Handbuch Süd/.test(${txt})`, 60), 'B: a page of Süd still opens by its address');
    await go('ablage');
    check(await ready(ev, `typeof ab_spaces === 'function' && ab_spaces().filter(s => s === 'private' || s.startsWith('org:')).join('|') === ${JSON.stringify(N)} && !ab_all()`, 60), 'B: Files offers only Nord, no overview');
    check(await ev(`ab_spaces().includes('trash') && ab_spaces().includes('shared')`), 'B: Files keeps Shared with me and the trash');
    check(await ev(`ofc_spaces().join('|') === ${JSON.stringify(N)}`), 'B: the office is Nord only (shared core)');
    await go('sheets');
    check(await ready(ev, `/Tabelle Nord/.test(${txt})`, 60), 'B: Tables lists Nord');
    check(!await ev(`/Tabelle Süd|Tabelle Privat/.test(${txt})`), 'B: Tables leaves out Private and Süd');
    check(await ev(`wso_cur() === ${JSON.stringify(N)}`), 'B: the overview of Tables wears the colour of Nord');
    await go('clients');
    check(await ready(ev, `/Kunde Nord/.test(${txt})`, 60), 'B: clients lists Nord');
    check(!await ev(`/Kunde Süd|Kunde Privat/.test(${txt})`), 'B: clients leaves out Private and Süd');
    await shot('p21398a-B-clients.png');
    // (#7309): New client under "All" through the dialog (the API calls above name org_id and would never have caught it):
    // one workspace with Clients (Nord) = no question, it lands there and the list one comes back to shows it
    const newClient = async (name, ws) => {
      await ev(`(document.querySelector('#view [data-act="client-new"]').click(), 1)`);
      check(await ready(ev, `!!document.querySelector('.modal.cldlg #cl-name')`, 40), name + ': the New client dialog opens');
      const opts = await ev(`JSON.stringify([...document.querySelectorAll('.modal.cldlg #cl-ws option')].map(o => o.value).filter(Boolean))`);
      await ev(`(m => { const e = m.querySelector('#cl-name'); e.value = ${JSON.stringify(name)}; e.dispatchEvent(new Event('input', {bubbles: true}));
        const s = m.querySelector('#cl-ws'); if (s && ${JSON.stringify(ws)}) { s.value = ${JSON.stringify(ws)}; s.dispatchEvent(new Event('change', {bubbles: true})); }
        m.querySelector('[data-m="save"]').click(); return 1; })(document.querySelector('.modal.cldlg'))`);
      check(await ready(ev, `!document.querySelector('.modal.cldlg')`, 60), name + ': saved, the dialog closes');
      await go('clients');
      check(await ready(ev, `${txt}.includes(${JSON.stringify(name)})`, 60), name + ': the clients list under All shows it');
      const x = (await call(CA, 'GET', '/api/clients')).clients?.find(c => c.name === name);
      return {opts: JSON.parse(opts), org: x ? x.org_id || null : 'missing'};
    };
    let nc = await newClient('Neukunde B', '');
    check(nc.opts.length === 0 && nc.org === O1, 'B #7309: one workspace with Clients: no question, it lands in Nord: ' + JSON.stringify(nc));
    await go('contacts');
    check(await ready(ev, `/Kontakt Nord|Nord, Kontakt/.test(${txt})`, 60), 'B: contacts lists Nord');
    check(!await ev(`/Süd|Privat/.test([...document.querySelectorAll('#view .ctrow, #view [data-cid]')].map(e => e.textContent).join(' '))`), 'B: contacts leaves out Private and Süd');

    // ================= case C: off in Süd only -> overview Private + Nord
    check(await patch(ev, {workspace: 'all', ...off(['org:' + O2])}) === 200, 'C: modules off in Süd');
    await go('wiki');
    check(await ready(ev, `wk_shown().join('|') === ${JSON.stringify('private|' + N)} && wk_all() && !wk_open()`, 60), 'C: Knowledge under All: overview of Private + Nord');
    check(await ready(ev, `(a => a.includes('private') && a.includes(${JSON.stringify(N)}) && !a.includes('org:${O2}'))([...document.querySelectorAll('#view [data-spov], #view a[href^="#wiki/s/"]')].map(e => e.dataset.spov || e.getAttribute('href').replace('#wiki/s/', '')))`, 60), 'C: the overview shows Private and Nord, not Süd');
    // usable: a tap on Nord opens it, the path above it leads back to the overview
    await ev(`document.querySelector('#view [data-spov="${N}"], #view a[href="#wiki/s/${N}"]')?.click()`);
    check(await ready(ev, `wk_open() === ${JSON.stringify(N)} && /Handbuch Nord/.test(${txt})`, 60), 'C: a tap on Nord opens it');
    await ev(`(history.back(), 1)`);  // the browser's Back (the computer has no path above an open space of Knowledge)
    check(await ready(ev, `!wk_open() && wk_all() && !!document.querySelector('#view [data-spov="${N}"], #view a[href="#wiki/s/${N}"]')`, 60), 'C: Back leads to the overview again');
    await go('wiki/s/org:' + O2);
    check(await ready(ev, `!wk_open()`, 20), 'C: the address of Süd leads to the overview (Knowledge off there)');
    // (#7309): under "All" the dialogs offer only the workspaces where the module is on (Private + Nord, not Süd), required
    await go('clients');
    nc = await newClient('Neukunde C', 'private');
    check(JSON.stringify(nc.opts) === JSON.stringify(['private', N]) && nc.org === null, 'C #7309: New client offers Private + Nord, not Süd; Private chosen lands there: ' + JSON.stringify(nc));
    await ev(`(evCalsModal(), 1)`);
    check(await ready(ev, `!!document.querySelector('[data-evc="new"]')`, 40), 'C #7309: the Calendars window opens');
    await ev(`(document.querySelector('[data-evc="new"]').click(), 1)`);
    check(await ready(ev, `!!document.querySelector('.cdlg #cdlg-in')`, 40), 'C #7309: New calendar asks for the name');
    const copts = await ev(`JSON.stringify([...document.querySelectorAll('.cdlg #ws-new option')].map(o => o.value).filter(Boolean))`);
    check(copts === JSON.stringify(['private', N]), 'C #7309: New calendar offers Private + Nord, not Süd: ' + copts);
    await ev(`(m => { const e = m.querySelector('#cdlg-in'); e.value = 'Kalender C'; e.dispatchEvent(new Event('input', {bubbles: true}));
      const s = m.querySelector('#ws-new'); s.value = ${JSON.stringify(N)}; s.dispatchEvent(new Event('change', {bubbles: true})); m.querySelector('[data-cd="yes"]').click(); return 1; })(document.querySelector('.cdlg'))`);
    check(await ready(ev, `(S.evcals || []).some(c => c.name === 'Kalender C' && c.org_id === ${O1})`, 60), 'C #7309: the calendar lands in Nord');
    check(await ready(ev, `[...document.querySelectorAll('.evcnm')].some(x => x.textContent === 'Kalender C')`, 40), 'C #7309: the Calendars window lists it');
    await ev(`(document.querySelector('[data-evc="done"]')?.click(), 1)`);

    // ================= everything on again: the spaces and entries come back
    check(await patch(ev, {workspace: 'all', ws_areas_off: '{}', ws_mods_off: '{}'}) === 200, 'on again');
    await go('wiki');
    check(await ready(ev, `wk_shown().length === 3 && wk_all()`, 60), 'on again: Knowledge offers all three spaces');
    check(await ev(`(typeof tv_wsLists !== 'function' || tv_wsLists() === null) && wso_scope() === ''`), 'on again: no time filter, the page wears no single colour');
    await go('clients');
    check(await ready(ev, `/Kunde Nord/.test(${txt}) && /Kunde Süd/.test(${txt}) && /Kunde Privat/.test(${txt})`, 60), 'on again: clients lists all three');
    await go('sheets');
    check(await ready(ev, `/Tabelle Nord/.test(${txt}) && /Tabelle Süd/.test(${txt}) && /Tabelle Privat/.test(${txt})`, 60), 'on again: Tables lists all three');

    // ================= P4: carol without an organisation
    await ev(`fetch('/api/auth/logout', {method: 'POST', headers: {'X-Requested-With': 'kalmido'}}).then(r => r.status)`).catch(() => 0);
    check(await signIn(ev, 'carol') === 200, 'carol signs in');
    await go('wiki');
    check(await ready(ev, `typeof wk_shown === 'function' && wk_shown().join('|') === 'private' && !wk_all() && /Notizbuch Carol/.test(${txt})`, 60), 'P4: Knowledge opens Private directly');
    await go('clients');
    check(await ready(ev, `/Kunde Carol/.test(${txt})`, 60), 'P4: her client is listed');
  }, false);

  console.log(`p21398_a_modspaces_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
