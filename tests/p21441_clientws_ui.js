// kalmido-suite: fresh
// 2.1441.0 UI test (#7298): "New client" under "All workspaces" puts the client where Clients is on for me, so the list keeps
// it (clientdlg.js cl_newWs; the list's rule: clientpage.js ms_inWs / areas.js mod_spaces). jsdom, invented data only.
// freelancer-matrix: clients -- a person without an organisation has no workspace field (one workspace), her client is listed.
// - Private + two organisations (Nord, Süd), the office area off in Private (the reported case), workspace "All":
//   the dialog asks for the workspace (only Nord and Süd offered, not Private); "Add" without a choice says so and keeps the
//   dialog; Nord chosen -> the client is in the clients list under "All" and in Nord
// - #7407: "Belongs to" stays empty and locked until the workspace is chosen, then offers only that workspace's main clients
//   (a chosen one of the other workspace is cleared on a change); the required message goes with the choice
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

  const hN = await call('POST', '/api/clients', {name: 'Haupt Nord', org_id: O1}), hS = await call('POST', '/api/clients', {name: 'Haupt Sued', org_id: O2});
  check(hN.id && hS.id, 'a main client in Nord and one in Süd');
  const pOpts = md => [...(md.querySelector('#cl-parent')?.options || [])].map(o => o.textContent).filter(t => t.startsWith('Haupt'));

  // ---- two workspaces with Clients on: the dialog asks
  let {w, d} = await listed('-');
  check(w.eval('wsCur()') === 'all', 'the page is under All workspaces');
  d.querySelector('#view [data-act="client-new"]').click();
  await until(() => d.querySelector('.modal.cldlg'), 40);
  let md = d.querySelector('.modal.cldlg'), sel = md.querySelector('#cl-ws');
  const opts = sel ? [...sel.options].map(o => o.value) : [];
  check(sel && JSON.stringify(opts) === JSON.stringify(['', 'org:' + O1, 'org:' + O2]), 'the dialog asks for the workspace: Nord and Süd, not Private: ' + opts);
  let par = md.querySelector('#cl-parent');
  check(par && par.disabled && !pOpts(md).length, '#7407: without a workspace "Belongs to" is locked and offers no main client: ' + pOpts(md));
  check(md.querySelector('#cl-parent-ws') && !md.querySelector('#cl-parent-ws').hidden, '#7407: ... with the hint to choose the workspace first');
  typeIn(w, md.querySelector('#cl-name'), 'Kunde Auswahl');
  md.querySelector('[data-m="save"]').click();
  await sleep(300);
  check(d.body.contains(md) && /workspace/i.test(md.querySelector('.aerr')?.textContent || ''), 'Add without a choice: the dialog stays and says what is missing');
  check(!(await call('GET', '/api/clients')).clients?.some(c => c.name === 'Kunde Auswahl'), '... nothing created');
  const pick = v => { sel.value = v; sel.dispatchEvent(new w.Event('change', {bubbles: true})); };
  pick('org:' + O1);
  check(!(md.querySelector('.aerr')?.textContent || '').trim(), '#7407: the workspace chosen -> the required message is gone');
  check(!par.disabled && JSON.stringify(pOpts(md)) === '["Haupt Nord"]', '#7407: "Belongs to" offers only the main clients of Nord: ' + pOpts(md));
  check(md.querySelector('#cl-parent-ws').hidden, '#7407: ... and the hint is gone');
  par.value = String(hN.id);
  pick('org:' + O2);
  check(JSON.stringify(pOpts(md)) === '["Haupt Sued"]' && par.value === '', '#7407: Süd chosen instead -> only Süd\'s main clients, the Nord one cleared: ' + pOpts(md) + ' / ' + par.value);
  pick('org:' + O1);
  md.querySelector('[data-m="save"]').click();
  await until(() => !d.body.contains(md), 60);
  const c1 = (await call('GET', '/api/clients')).clients?.find(c => c.name === 'Kunde Auswahl');
  check(c1 && c1.org_id === O1, 'the client is in Studio Nord: ' + JSON.stringify(c1 && c1.org_id));
  check((await listed('Kunde Auswahl')).hit, 'the clients list under All shows it (#7298: it no longer vanishes)');

  // ---- Clients off in Süd too: no question, Nord
  check((await set({ws_mods_off: {['org:' + O2]: ['clients']}})).http === 200, 'Clients off in Süd');
  ({w, d} = await listed('Kunde Auswahl'));
  d.querySelector('#view [data-act="client-new"]').click();
  await until(() => d.querySelector('.modal.cldlg'), 40);
  md = d.querySelector('.modal.cldlg');
  check(!md.querySelector('#cl-ws'), 'one workspace left: no workspace field');
  check(JSON.stringify(pOpts(md)) === '["Haupt Nord"]', '#7407: "Belongs to" offers only the main clients of Nord: ' + pOpts(md));
  typeIn(w, md.querySelector('#cl-name'), 'Kunde Direkt');
  md.querySelector('[data-m="save"]').click();
  await until(() => !d.body.contains(md), 60);
  const c2 = (await call('GET', '/api/clients')).clients?.find(c => c.name === 'Kunde Direkt');
  check(c2 && c2.org_id === O1, 'it lands in Nord without a question: ' + JSON.stringify(c2 && c2.org_id));
  check((await listed('Kunde Direkt')).hit, 'and the list under All shows it');

  // ---- contacts: no address book of a workspace where Contacts is off
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
