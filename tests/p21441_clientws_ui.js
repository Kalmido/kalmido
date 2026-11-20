// kalmido-suite: fresh
// 2.1441.0 UI test (#7298): "New client" under "All workspaces" puts the client where Clients is on for me, so the list keeps
// it (clientdlg.js cl_newWs; the list's rule: clientpage.js ms_inWs / areas.js mod_spaces). jsdom, invented data only.
// freelancer-matrix: clients -- a person without an organisation has no workspace field (one workspace), her client is listed.
// - Private + two organisations (Nord, Süd), the office area off in Private (the reported case), workspace "All":
//   the dialog asks for the workspace (only Nord and Süd offered, not Private); "Add" without a choice says so and keeps the
//   dialog; Nord chosen -> the client is in the clients list under "All" and in Nord
// - Clients off in Süd too: no field, the client goes into Nord without a question and is listed
// - the contacts editor under "All" offers no address book of a workspace where Contacts is off
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...await r.json().catch(() => ({})), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const typeIn = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
const FEATS = 'cal,comments,collab,contacts,office,clients,time';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'contacts']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATS});
  const me = (await call('GET', '/api/state')).me;
  const O1 = (await call('POST', '/api/admin/orgs', {name: 'Studio Nord', admin_id: me.id})).id;
  const O2 = (await call('POST', '/api/admin/orgs', {name: 'Atelier Süd', admin_id: me.id})).id;
  check(O1 > 0 && O2 > 0, 'two organisations');
  const set = b => call('PATCH', '/api/settings', Object.fromEntries(Object.entries(b).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : v])));
  check((await set({workspace: 'all', ws_areas_off: {private: ['office']}, ws_mods_off: {}})).http === 200, 'the office off in Private, workspace All');
  const txt = d => d.querySelector('#view')?.textContent || '';
  const listed = async (name, n = 80) => {
    const w = await boot({hash: 'clients', allWs: true}); const d = w.document;
    await until(() => w.S?.me && d.querySelector('#view [data-act="client-new"]'), 80);
    const hit = !!await until(() => txt(d).includes(name), n);
    return {w, d, hit};
  };

  // ---- two workspaces with Clients on: the dialog asks
  let {w, d} = await listed('-');
  check(w.eval('wsCur()') === 'all', 'the page is under All workspaces');
  d.querySelector('#view [data-act="client-new"]').click();
  await until(() => d.querySelector('.modal.cldlg'), 40);
  let md = d.querySelector('.modal.cldlg'), sel = md.querySelector('#cl-ws');
  const opts = sel ? [...sel.options].map(o => o.value) : [];
  check(sel && JSON.stringify(opts) === JSON.stringify(['', 'org:' + O1, 'org:' + O2]), 'the dialog asks for the workspace: Nord and Süd, not Private: ' + opts);
  typeIn(w, md.querySelector('#cl-name'), 'Kunde Auswahl');
  md.querySelector('[data-m="save"]').click();
  await sleep(300);
  check(d.body.contains(md) && /workspace/i.test(md.querySelector('.aerr')?.textContent || ''), 'Add without a choice: the dialog stays and says what is missing');
  check(!(await call('GET', '/api/clients')).clients?.some(c => c.name === 'Kunde Auswahl'), '... nothing created');
  sel.value = 'org:' + O1; sel.dispatchEvent(new w.Event('change', {bubbles: true}));
  md.querySelector('[data-m="save"]').click();
  await until(() => !d.body.contains(md), 60);
  const c1 = (await call('GET', '/api/clients')).clients?.find(c => c.name === 'Kunde Auswahl');
  check(c1 && c1.org_id === O1, 'the client is in Studio Nord: ' + JSON.stringify(c1 && c1.org_id));
  check((await listed('Kunde Auswahl')).hit, 'the clients list under All shows it (#7298: it no longer vanishes)');

  // ---- (#7309) wsp_post: the server needs the workspace -> the required choice (wsp_ask), then sent again with space
  ({w, d} = await listed('Kunde Auswahl'));
  check(w.eval("JSON.stringify(wsp_list('clients', true))") === JSON.stringify(['org:' + O1, 'org:' + O2]), '#7309 wsp_list: where I may add a client: ' + w.eval("JSON.stringify(wsp_list('clients', true))"));
  const pr = w.eval("wsp_post('/api/clients', {name: 'Kunde Frage'})");
  await until(() => d.querySelector('.cdlg input[name="wsp-ask"]'), 40);
  const radios = [...d.querySelectorAll('.cdlg input[name="wsp-ask"]')].map(x => x.value);
  check(JSON.stringify(radios) === JSON.stringify(['org:' + O1, 'org:' + O2]), '#7309 wsp_ask: the server\'s choice: ' + radios);
  d.querySelector('.cdlg [data-cd="yes"]').click();
  await sleep(300);
  check(!!d.querySelector('.cdlg input[name="wsp-ask"]'), '#7309 wsp_ask: without a choice the dialog stays');
  d.querySelector(`.cdlg input[value="org:${O2}"]`).checked = true;
  d.querySelector('.cdlg [data-cd="yes"]').click();
  const made = await pr;
  check(made && made.org_id === O2, '#7309 wsp_post: sent again with the chosen workspace -> Süd: ' + JSON.stringify(made && made.org_id));
  check((await listed('Kunde Frage')).hit, '#7309: and the list under All shows it');

  // ---- Clients off in Süd too: no question, Nord
  check((await set({ws_mods_off: {['org:' + O2]: ['clients']}})).http === 200, 'Clients off in Süd');
  ({w, d} = await listed('Kunde Auswahl'));
  d.querySelector('#view [data-act="client-new"]').click();
  await until(() => d.querySelector('.modal.cldlg'), 40);
  md = d.querySelector('.modal.cldlg');
  check(!md.querySelector('#cl-ws'), 'one workspace left: no workspace field');
  typeIn(w, md.querySelector('#cl-name'), 'Kunde Direkt');
  md.querySelector('[data-m="save"]').click();
  await until(() => !d.body.contains(md), 60);
  const c2 = (await call('GET', '/api/clients')).clients?.find(c => c.name === 'Kunde Direkt');
  check(c2 && c2.org_id === O1, 'it lands in Nord without a question: ' + JSON.stringify(c2 && c2.org_id));
  check((await listed('Kunde Direkt')).hit, 'and the list under All shows it');

  // ---- contacts: no address book of a workspace where Contacts is off
  // (#7309): a book goes only where Contacts is on (the office area, Contacts' area, is still off in Private here): on first
  check((await set({ws_areas_off: {}, ws_mods_off: {}})).http === 200, 'the office area on again in Private');
  const bOff = await call('POST', '/api/books', {name: 'Buch Gesperrt', org_id: null});
  await set({ws_areas_off: {private: ['office']}});
  const bOff2 = await call('POST', '/api/books', {name: 'Buch Gesperrt', org_id: null});
  check(bOff.http === 201 && bOff2.http === 400 && bOff2.code === 'space_needed', '#7309: a new book named Private while Contacts is off there -> 400 space_needed: ' + bOff2.http + ' ' + bOff2.code);
  await set({ws_areas_off: {}});
  const bP = await call('POST', '/api/books', {name: 'Buch Privat', org_id: null});
  const bN = await call('POST', '/api/books', {name: 'Buch Nord', org_id: O1});
  check(bP.id && bN.id, 'an address book in Private and in Nord');
  check((await set({ws_mods_off: {private: ['contacts']}, ws_areas_off: {}})).http === 200, 'Contacts off in Private');
  w = await boot({hash: 'contacts', allWs: true}); d = w.document;
  await until(() => w.S?.me && w.S.books?.length && typeof w.ctEditor === 'function', 80);
  w.ctEditor(null);
  await until(() => d.querySelector('#ct-bk'), 60);
  const bopts = [...d.querySelectorAll('#ct-bk option')].map(o => o.textContent);
  check(!bopts.includes('Buch Privat'), 'the contacts editor under All offers no book of Private (Contacts off there): ' + bopts.join('|'));
  check(bopts.includes('Buch Nord'), '... but the book of Nord');

  // ---- P4: a person without an organisation
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida Frei', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATS}, CF);
  w = await boot({user: 'frida', hash: 'clients'}); d = w.document;
  await until(() => w.S?.me && d.querySelector('#view [data-act="client-new"]'), 80);
  d.querySelector('#view [data-act="client-new"]').click();
  await until(() => d.querySelector('.modal.cldlg'), 40);
  md = d.querySelector('.modal.cldlg');
  check(!md.querySelector('#cl-ws'), 'P4: no workspace field without an organisation');
  typeIn(w, md.querySelector('#cl-name'), 'Kunde Frida');
  md.querySelector('[data-m="save"]').click();
  await until(() => !d.body.contains(md), 60);
  const cf = (await call('GET', '/api/clients', null, CF)).clients?.find(c => c.name === 'Kunde Frida');
  check(cf && cf.org_id == null, 'P4: her client is private');

  console.log(`p21441_clientws_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
