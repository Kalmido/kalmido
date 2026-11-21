// kalmido-suite: fresh
// #7017 (audit #5248 D12) UI test: Office > Clients with the area's "…" and a full row menu. Own container
// (start.sh), jsdom, invented data. frida has no organisation (freelancer: the same ways).
// - no boxes "Archived" / "Trash" and no "Import…" button under the list any more: the area's "…" has Show archived and Trash
//   (and Import… for office admins); what is on shows as a chip in the bar, a tap on it takes it off again (in / back)
// - the row's menu (right click / long press) is the client's full menu: Select, Open, Edit, Archive, Duplicate, ... Delete;
//   the card's "…" has the same client entries; Archive from the row menu is one Undo step; Delete goes to the clients' trash
// freelancer-matrix: clients - frida has no organisation.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const items = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"] .ml')].map(x => x.textContent.trim());
const pick = (d, label) => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].find(b => b.querySelector('.ml')?.textContent.trim() === label);
const rclick = (w, el) => el.dispatchEvent(new w.MouseEvent('contextmenu', {bubbles: true, cancelable: true, button: 2, clientX: 10, clientY: 10}));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,office,clients'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const A = (await call(CF, 'POST', '/api/clients', {name: 'Alpha Example GmbH'})).id, Bt = (await call(CF, 'POST', '/api/clients', {name: 'Beta Example AG'})).id;
  check(A && Bt, 'setup: two clients');
  const cl = async id => call(CF, 'GET', `/api/clients/${id}`);

  const w = await boot({user: 'frida', hash: 'clients'}), d = w.document;
  const row = id => d.querySelector(`#view .msclients .ctrow[data-clopen="${id}"]`);
  await until(() => row(A) && row(Bt), 30000);
  check(!d.querySelector('#mscl-arch') && !d.querySelector('#mscl-trash'), '#7017 D12: no boxes Archived / Trash in the bar');
  check(!d.querySelector('#view .ctlistw > .oimlink'), '#7017 D12: no "Import…" button under the list');
  const more = d.querySelector('#view .ctbar [data-mscl="more"]');
  check(more && more.getAttribute('aria-haspopup') === 'menu', '#7017 D12: the area\'s "…" in the bar');

  // ---- the row's menu: the full one
  rclick(w, row(A));
  await until(() => items(d).length);
  const m = items(d);
  check(['Select', 'Open', 'Edit', 'Archive', 'Duplicate', 'Add location', 'Delete'].every(x => m.includes(x)), '#7017 D12: the row menu is the full client menu ' + JSON.stringify(m));
  check(m.indexOf('Open') < m.indexOf('Archive') && m[m.length - 1] === 'Delete', '... Open first, Delete last');
  pick(d, 'Archive')?.click();
  check(await until(async () => (await cl(A)).archived === true), '#7017 D12: Archive from the row menu archives it (server)');
  check(await until(() => !row(A)), '... and the list hides it');
  await w.eval('histStep("undo")');
  check(await until(async () => !(await cl(A)).archived) && await until(() => row(A)), 'Undo: back in the list (one step)');

  // ---- the area's "…": Show archived -> chip -> off again
  await call(CF, 'POST', '/api/clients/bulk', {action: 'archive', ids: [Bt]});
  await w.eval('ms_clDirty && ms_clDirty()');
  await w.eval('MSC.items = null; ms_clDraw()');
  check(await until(() => row(A) && !row(Bt)), 'setup: Beta archived, not shown');
  d.querySelector('#view .ctbar [data-mscl="more"]').click();
  await until(() => pick(d, 'Show archived'));
  check(items(d).includes('Trash') && !items(d).includes('Import…') === !w.eval('!!oim_link("master")'), '#7017 D12: the area\'s "…": Show archived, Trash (Import only where the office import is offered) ' + JSON.stringify(items(d)));
  pick(d, 'Show archived').click();
  check(await until(() => row(Bt) && d.querySelector('#view .ctbar [data-mscl="arch"][aria-pressed="true"]')), '#7017 D12: Show archived - the archived one listed, a chip "Archived" in the bar');
  d.querySelector('#view .ctbar [data-mscl="arch"]').click();
  check(await until(() => !row(Bt) && !d.querySelector('#view .ctbar [data-mscl="arch"]')), '... the chip takes it off again');

  // ---- Delete from the row menu: the clients' trash, then the trash through the "…"
  w.confirm = () => true;
  rclick(w, row(A));
  await until(() => pick(d, 'Delete'));
  pick(d, 'Delete').click();  // the question (trashui.js ms_clDel) is answered by the dialog bridge of boot.js (w.confirm)
  check(await until(async () => (await cl(A)).http === 404), '#7017 D12: Delete from the row menu moves it into the clients\' trash');
  d.querySelector('#view .ctbar [data-mscl="more"]').click();
  (await until(() => pick(d, 'Trash')))?.click();
  check(await until(() => /Alpha Example/.test(d.querySelector('#view .mscltrash')?.textContent || '') && d.querySelector('#view .ctbar [data-mscl="trash"]')), '#7017 D12: the trash from the "…" lists it, a chip "Trash" shows');
  d.querySelector('#view .ctbar [data-mscl="trash"]').click();
  check(await until(() => !d.querySelector('#view .mscltrash') && d.querySelector('#view .msclients .ctlist, #view .msclients .empty')), '... the chip leads back to the clients');
  w.close();

  console.log(`p21512_7017_clients_menus_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
