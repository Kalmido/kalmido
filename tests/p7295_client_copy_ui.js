// #7295 UI test: "Duplicate" and "Add location" in the menu of the client page. jsdom, fresh container,
// kalmido-suite: fresh
// invented names only:
//  - menu "Duplicate" -> the dialog (the contact persons as a tick, off by default) -> the copy opens in its form, the page
//    shows the copy; the toast's Undo puts the copy into the trash and goes back to the original
//  - menu "Add location" on a location -> a location of the same main client, its form open with that main client chosen
//  - a person without an organisation: the same way
// freelancer-matrix: clients (frida has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, B, login, sleep, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => until0(fn, {timeout: ms || 15000, step: 100});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const FEAT = 'collab,comments,office,clients,time';
const menuItems = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')];
const btnText = (d, txt) => [...d.querySelectorAll('.modal button')].find(b => b.textContent.trim() === txt);
const clients = async ck => (await call(ck, 'GET', '/api/clients?brief=1&archived=1')).clients || [];

async function card(w, d, id) {  // the card of client id with its menu button
  for (let i = 0; i < 4; i++) {
    w.eval(`go('client/${id}')`);
    const b = await until(() => w.eval('CLV.data?.id') === id && w.eval('S.route.client') === id && d.querySelector('#view [data-mscl="cmenu"]'), 5000);
    await sleep(300);
    if (b && w.eval('S.route.client') === id && d.querySelector('#view [data-mscl="cmenu"]')) return d.querySelector('#view [data-mscl="cmenu"]');
  }
  return null;
}
async function pick(w, d, id, label) {  // open the card's menu and choose label
  const mb = await card(w, d, id);
  mb?.click();
  const its = await until(() => { const x = menuItems(d); return x.length && x; }) || [];
  const it = its.find(x => x.textContent.trim() === label);
  check(it, `menu of ${id}: "${label}" in ` + its.map(x => x.textContent.trim()));
  it?.click();
  return !!it;
}

async function flow(ck, user, tag) {
  const P = (await call(ck, 'POST', '/api/clients', {name: 'Nordlicht Studios', city: 'Hamburg', rate: 95, note: 'Mornings',
    contacts: [{name: 'Mara Kühn', role: 'Producer', is_default: true}, {name: 'Jonas Weber'}]})).id;
  const S1 = (await call(ck, 'POST', '/api/clients', {name: 'Nordlicht Studios', name_extra: 'Bonn', city: 'Bonn', parent_id: P})).id;
  check(P && S1, `${tag}: a main client with two contact persons and a location`);
  const w = await boot({user, hash: 'clients'}), d = w.document;
  // ---- Duplicate: the dialog, the tick, the copy opens in its form
  if (await pick(w, d, P, 'Duplicate')) {
    const box = await until(() => d.querySelector('.modal.cdlg #clcp-k'));
    check(box && !box.checked && /Take the contact persons along \(2\)/.test(d.querySelector('.modal.cdlg').textContent), `${tag}: the dialog asks about the 2 contact persons, off by default`);
    if (box) box.checked = true;
    btnText(d, 'Duplicate')?.click();
    const nm = await until(() => d.querySelector('.modal.cldlg #cl-name'));
    check(nm && nm.value === 'Nordlicht Studios (copy)', `${tag}: the copy opens in its form: ${nm && nm.value}`);
    const cp = (await clients(ck)).find(c => c.name === 'Nordlicht Studios (copy)');
    check(cp && await until(() => w.eval('S.route.client') === cp.id), `${tag}: the page shows the copy`);
    const full = cp ? await call(ck, 'GET', `/api/clients/${cp.id}`) : {};
    check((full.contacts || []).length === 2 && full.billing?.city === 'Hamburg' && full.rate === 95 && (full.lists || []).length === 0,
      `${tag}: the copy has the contact persons, the city, the rate and no projects`);
    d.querySelector('.modal.cldlg [data-m="close"]')?.click();
    check(await until(() => !d.querySelector('.modal.cldlg')), `${tag}: the form closes`);
    // ---- back: the toast's Undo
    const undo = await until(() => d.querySelector('#toast button:not(.tx)'));
    check(undo, `${tag}: the message "Client duplicated" with Undo`);
    undo?.click();
    check(cp && await until(async () => !(await clients(ck)).some(c => c.id === cp.id)), `${tag}: Undo puts the copy into the trash`);
    check(await until(() => w.eval('S.route.client') === P), `${tag}: Undo goes back to the original`);
  }
  // ---- Add location on a location: the same main client
  if (await pick(w, d, S1, 'Add location')) {
    const yes = await until(() => btnText(d, 'Add location'));
    check(yes && !d.querySelector('.modal.cdlg #clcp-k'), `${tag}: the dialog (no tick: the location has no contact persons)`);
    yes?.click();
    const nm = await until(() => d.querySelector('.modal.cldlg #cl-parent') && d.querySelector('.modal.cldlg'));
    check(nm && nm.querySelector('#cl-parent').value === String(P) && nm.querySelector('#cl-nx').value === '', `${tag}: the new location's form: main client chosen, name addition empty`);
    if (nm) {
      nm.querySelector('#cl-nx').value = 'Köln';
      nm.querySelector('#cl-nx').dispatchEvent(new w.Event('input', {bubbles: true}));
      nm.querySelector('[data-m="save"]').click();
      check(await until(async () => (await clients(ck)).some(c => c.name_extra === 'Köln' && c.parent_id === P)), `${tag}: saved: a location of the main client`);
    }
  }
  w.close();
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await flow(CA, 'alice', 'alice');
  // ---------------- a person without an organisation
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  await flow(CF, 'frida', 'freelancer');
  console.log(`p7295_client_copy_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
