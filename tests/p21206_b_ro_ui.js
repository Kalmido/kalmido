// 2.1206.0 UI test, part B (#6161, Stufe 1): calendar and contacts show their write entries only where canWrite says yes.
// kalmido-suite: fresh
// jsdom, own container (start.sh, mode workspaces), invented data only. Persons:
// - Rita: read-only in the organisation Alpha; Alice shares the organisation's calendar and address book with her as "edit"
//   (the server makes it "view": read-only role). Bob: member of Alpha; Alice shares her private calendar and address book
//   with him as "view". Fred: no organisation (the freelancer fixture's case), his own calendar and address book.
// - a reader (Rita, Bob): no "+ Event", no new event by dragging over a day, an event is not draggable, the popover has no
//   Edit / Delete, the editor opened on the event reads (fields disabled, no Save / Delete); no "New contact", no import
//   (file input, menu), no select button, the card has no Edit and its "..." no Delete; the read hint shows exactly ONCE per
//   view; the CONTENT (event title, contact name) is there
// - a direct API write of the reader stays 403 (event, contact)
// - the same persons with the right (Bob: share "edit", Rita: member) see the entries and no read hint; Fred too
// freelancer-matrix: events contacts (Fred has no organisation: his private workspace, every entry there)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, ms = 15000) => until0(fn, {timeout: ms, step: 100});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const pad = n => String(n).padStart(2, '0');
const dstr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const TODAY = dstr(new Date());
const FEATS = 'cal,events,contacts,collab,comments';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'contacts']}, CA);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATS}, CA);
  const me = (await call('GET', '/api/state', null, CA)).me.id;
  const U = {};
  for (const n of ['rita', 'bob', 'fred']) {
    U[n] = (await call('POST', '/api/users', {username: n, display_name: n[0].toUpperCase() + n.slice(1), password: 'password123', email: `${n}@example.org`}, CA)).id;
    U[n + 'C'] = await login(n);
    await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATS}, U[n + 'C']);
  }
  const ORG = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me}, CA)).id;
  for (const n of ['rita', 'bob']) check((await call('PUT', `/api/orgs/${ORG}/members`, {email: `${n}@example.org`}, CA)).http === 200, `${n} joins Alpha`);
  check((await call('PUT', `/api/orgs/${ORG}/members`, {user_id: U.rita, role: 'readonly'}, CA)).http === 200, 'Rita is read-only in Alpha');
  await call('PATCH', '/api/settings', {workspace: `org:${ORG}`}, U.ritaC);
  await call('PATCH', '/api/settings', {workspace: 'private'}, U.bobC);

  // the organisation's calendar + address book (shared with Rita as "edit"), Alice's private ones (shared with Bob as "view")
  const OC = await call('POST', '/api/evcals', {name: 'Alpha team', org_id: ORG}, CA);
  const PC = await call('POST', '/api/evcals', {name: 'Alice home', org_id: null}, CA);
  const OE = await call('POST', '/api/events', {title: 'Board meeting', cal_id: OC.id, start: `${TODAY}T10:00`, end: `${TODAY}T11:00`, reminders: []}, CA);
  const PE = await call('POST', '/api/events', {title: 'Dentist visit', cal_id: PC.id, start: `${TODAY}T15:00`, end: `${TODAY}T16:00`, reminders: []}, CA);
  const OB = await call('POST', '/api/books', {name: 'Alpha contacts', org_id: ORG}, CA);
  const PB = await call('POST', '/api/books', {name: 'Alice friends', org_id: null}, CA);
  const OK1 = await call('POST', '/api/contacts', {book_id: OB.id, given: 'Petra', family: 'Partner'}, CA);
  const PK1 = await call('POST', '/api/contacts', {book_id: PB.id, given: 'Viktor', family: 'Viewonly'}, CA);
  check(OC.id && PC.id && OE.id && PE.id && OB.id && PB.id && OK1.id && PK1.id, 'calendars, events, address books, contacts set up');
  check((await call('PUT', `/api/evcals/${OC.id}/members`, {user_id: U.rita, role: 'edit'}, CA)).http === 200
    && (await call('PUT', `/api/books/${OB.id}/members`, {user_id: U.rita, role: 'edit'}, CA)).http === 200, 'Alice shares the organisation\'s calendar and book with Rita (edit)');
  check((await call('PUT', `/api/evcals/${PC.id}/members`, {user_id: U.bob, role: 'view'}, CA)).http === 200
    && (await call('PUT', `/api/books/${PB.id}/members`, {user_id: U.bob, role: 'view'}, CA)).http === 200, 'Alice shares her private calendar and book with Bob (view)');
  const roleOf = async (ck, url, id) => ((await call('GET', url, null, ck)).items || []).find(x => x.id === id)?.role;
  check(await roleOf(U.ritaC, '/api/evcals', OC.id) === 'view', 'server: Rita reads the organisation\'s calendar (read-only role)');
  check(await roleOf(U.bobC, '/api/evcals', PC.id) === 'view', 'server: Bob reads Alice\'s calendar');
  check(!((await call('GET', '/api/evcals', null, U.bobC)).items || []).some(c => c.role === 'owner'), 'Bob has no calendar of his own');
  // Fred: no organisation, his own calendar and book
  const FC = await call('POST', '/api/evcals', {name: 'Fred work'}, U.fredC);
  const FE = await call('POST', '/api/events', {title: 'Fred client call', cal_id: FC.id, start: `${TODAY}T09:00`, end: `${TODAY}T09:30`, reminders: []}, U.fredC);
  const FB = await call('POST', '/api/books', {name: 'Fred clients'}, U.fredC);
  const FK = await call('POST', '/api/contacts', {book_id: FB.id, given: 'Clara', family: 'Client'}, U.fredC);
  check(FC.id && FE.id && FB.id && FK.id && !(await call('GET', '/api/state', null, U.fredC)).me.workspaces?.length, 'Fred (no organisation): own calendar, event, book, contact');

  // ================= the server stays the lock: a reader's direct write is 403
  check((await call('POST', '/api/events', {title: 'x', cal_id: OC.id, start: `${TODAY}T12:00`, end: `${TODAY}T13:00`}, U.ritaC)).http === 403, 'API: Rita cannot add an event (403)');
  check((await call('PATCH', `/api/events/${OE.id}`, {title: 'changed'}, U.ritaC)).http === 403, 'API: Rita cannot change the event (403)');
  check((await call('POST', '/api/events', {title: 'x', cal_id: PC.id, start: `${TODAY}T12:00`, end: `${TODAY}T13:00`}, U.bobC)).http === 403, 'API: Bob cannot add an event to Alice\'s calendar (403)');
  check((await call('POST', '/api/contacts', {book_id: OB.id, given: 'x'}, U.ritaC)).http === 403, 'API: Rita cannot add a contact (403)');
  check((await call('POST', '/api/contacts', {book_id: PB.id, given: 'x'}, U.bobC)).http === 403, 'API: Bob cannot add a contact (403)');

  // ================= the calendar
  const calCase = async (user, title, eid, writer) => {
    const who = `${user} (${writer ? 'writes' : 'reads'})`;
    const w = await boot({user, hash: 'cal', ls: {'tasks.calMode': '"month"'}}), d = w.document;
    const chip = () => [...d.querySelectorAll('#view .cal .cev[data-cev]')].find(x => x.textContent.includes(title));
    check(await until(() => d.querySelector('#view .calbar') && chip()), `${who}: the month shows the event "${title}"`);
    check(!!d.querySelector('#view [data-act="ev-new"]') === writer, `${who}: "+ Event" ${writer ? 'there' : 'left out'}`);
    check(w.eval('evCanNew()') === writer, `${who}: evCanNew() = ${writer}`);
    check(d.querySelectorAll('#view .cwro').length === (writer ? 0 : 1), `${who}: read hint ${writer ? 'none' : 'exactly once'}: ${d.querySelectorAll('#view .cwro').length}`);
    if (!writer) check(/You can only read here/.test(d.querySelector('#view .cwro')?.textContent || ''), `${who}: the hint says so`);
    // dragging over a free day (new event) and the event itself
    const cell = d.querySelector('#view .cal .cell[data-day]');
    check(w.eval('(c => { const r = cg_down(c, 5, 5, false); if (r) cg_cancel(); return !!r; })')(cell) === writer, `${who}: dragging over a day ${writer ? 'makes' : 'makes no'} event`);
    check(w.eval(`cg_canDrag(S.cal.items.find(x => x.eid === ${eid}))`) === writer, `${who}: the event ${writer ? 'can' : 'cannot'} be dragged`);
    // the popover
    click(w, chip());
    check(await until(() => d.querySelector('#pop .evpop .cevact')), `${who}: the popover opens`);
    const pop = d.querySelector('#pop .evpop');
    check(pop?.textContent.includes(title), `${who}: the popover shows the title`);
    check(!!pop?.querySelector('[data-evp="edit"]') === writer && !!pop?.querySelector('[data-evp="del"]') === writer, `${who}: Edit / Delete ${writer ? 'there' : 'left out'}`);
    w.eval('closePop()');
    // the editor on the event
    w.eval(`api('GET', '/api/events/${eid}').then(ev => evEditor({ev}))`);
    const md = await until(() => d.querySelector('.modal.evmodal'));
    check(!!md, `${who}: the editor opens`);
    if (md) {
      check(md.querySelector('#ev-title')?.value === title, `${who}: the editor shows the title`);
      check(!!md.querySelector('[data-evm="save"]') === writer && !!md.querySelector('[data-evm="del"]') === writer, `${who}: Save / Delete ${writer ? 'there' : 'left out'}`);
      check(md.querySelector('#ev-title').disabled === !writer && md.querySelector('#ev-desc').disabled === !writer, `${who}: the fields ${writer ? 'edit' : 'read'}`);
      check(md.querySelectorAll('.cwro').length === (writer ? 0 : 1), `${who}: the editor's read hint ${writer ? 'none' : 'once'}`);
      md.remove();
    }
    w.close();
  };
  // ================= the contacts
  const ctCase = async (user, name, cid, writer) => {
    const who = `${user} contacts (${writer ? 'writes' : 'reads'})`;
    let w = await boot({user, hash: 'contacts'}), d = w.document;
    const row = () => [...d.querySelectorAll('#view .ctrow')].find(x => x.textContent.includes(name));
    check(await until(() => row()), `${who}: the list shows "${name}"`);
    check(!!d.querySelector('#view [data-ct="new"]') === writer, `${who}: "New contact" ${writer ? 'there' : 'left out'}`);
    check(!!d.querySelector('#ct-impfile') === writer && !!d.querySelector('#view [data-ct="pick"]') === writer, `${who}: import input / select ${writer ? 'there' : 'left out'}`);
    check(d.querySelectorAll('#view .cwro').length === (writer ? 0 : 1), `${who}: read hint ${writer ? 'none' : 'exactly once'}`);
    click(w, d.querySelector('#view [data-ct="menu"]'));
    await until(() => d.querySelector('#pop [role="menuitem"]'));
    const mi = [...d.querySelectorAll('#pop [role="menuitem"]')].map(x => x.textContent.trim());
    check(mi.some(x => /Address books/.test(x)) && mi.some(x => /Import a vCard/.test(x)) === writer && mi.some(x => /Import a CSV/.test(x)) === writer, `${who}: the menu's import ${writer ? 'there' : 'left out'}: ${mi.join('|')}`);
    w.eval('closePop()'); w.close();
    // the card
    w = await boot({user, hash: `contacts/${cid}`}); d = w.document;
    check(await until(() => d.querySelector('#view .ctcard #ct-h')?.textContent.includes(name)), `${who}: the card shows "${name}"`);
    check(!!d.querySelector('#view .ctcard [data-ct="edit"]') === writer, `${who}: the card's Edit ${writer ? 'there' : 'left out'}`);
    check(d.querySelectorAll('#view .cwro, #view .ctcard .rotag').length === (writer ? 0 : 1), `${who}: one read hint with the card open: ${d.querySelectorAll('#view .cwro, #view .ctcard .rotag').length}`);
    click(w, d.querySelector('#view [data-ct="cmenu"]'));
    await until(() => d.querySelector('#pop [role="menuitem"]'));
    const cm = [...d.querySelectorAll('#pop [role="menuitem"]')].map(x => x.textContent.trim());
    check(cm.some(x => /^Delete/.test(x)) === writer, `${who}: the card's Delete ${writer ? 'there' : 'left out'}: ${cm.join('|')}`);
    w.eval('closePop()'); w.close();
  };

  await calCase('rita', 'Board meeting', OE.id, false);
  await calCase('bob', 'Dentist visit', PE.id, false);
  await ctCase('rita', 'Petra Partner', OK1.id, false);
  await ctCase('bob', 'Viktor Viewonly', PK1.id, false);
  await calCase('fred', 'Fred client call', FE.id, true);
  await ctCase('fred', 'Clara Client', FK.id, true);

  // ================= the same persons with the right: Bob's shares "edit", Rita a member
  check((await call('PUT', `/api/evcals/${PC.id}/members`, {user_id: U.bob, role: 'edit'}, CA)).http === 200
    && (await call('PUT', `/api/books/${PB.id}/members`, {user_id: U.bob, role: 'edit'}, CA)).http === 200, 'Bob\'s shares become "edit"');
  check((await call('PUT', `/api/orgs/${ORG}/members`, {user_id: U.rita, role: 'member'}, CA)).http === 200, 'Rita becomes a member');
  check(await roleOf(U.ritaC, '/api/evcals', OC.id) === 'edit', 'server: Rita may change the organisation\'s calendar now');
  await calCase('bob', 'Dentist visit', PE.id, true);
  await calCase('rita', 'Board meeting', OE.id, true);
  await ctCase('bob', 'Viktor Viewonly', PK1.id, true);
  await ctCase('rita', 'Petra Partner', OK1.id, true);

  console.log(`p21206_b_ro_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
