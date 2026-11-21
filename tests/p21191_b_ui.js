// 2.119.1 UI tests, part B (the contact card), own container (start.sh). jsdom, invented data only:
// - #2086 the card's address is a map link (Google Maps outside Apple devices, URL-encoded, new tab, noopener); the client
//   page's address too
// - #2082 More > "Create as client" makes the client with the contact as its linked contact person, one undo step (the
//   toast's Undo deletes it again); a linked contact offers "Open client"
// - #2083 "Interactions" on the card (#7015: was "Contact history"; German "Vorgänge"): the client's quotation and the event, a tap target each; the phone shows it too
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, undoToast} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21191B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});  // 2.358.0 (#3286): the shared wait of tests/boot.js (default at least 15 s); an explicit n/ms keeps its window
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const items = d => [...d.querySelectorAll('#pop [role="menuitem"]')];
const acme = async () => ((await call('GET', '/api/clients')).clients || []).find(c => c.name === 'Acme GmbH');

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,events,clients,contacts,office'});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  await call('PATCH', '/api/settings', {workspace: `org:${ORG}`});
  const bk = await call('POST', '/api/books', {name: 'Customers', org_id: ORG});
  const ho = await call('POST', `/api/books/${bk.id}/org`, {org_role: 'view'});
  check(bk.http === 201 && ho.org_owned, 'setup: an address book of the organisation');
  const ct = await call('POST', '/api/contacts', {book_id: bk.id, given: 'Petra', family: 'Buyer', org: 'Acme GmbH', title: 'Head of purchasing',
    emails: [{value: 'petra@example.com', type: ['work']}], phones: [{value: '+49 30 1234'}],
    addresses: [{type: ['work'], street: 'Hauptstr. 1', code: '10115', city: 'Berlin', country: 'Germany'}]});
  check(ct.http === 201, 'setup: the contact');

  // ================= #2086 the map link
  let w = await boot({hash: `contacts/${ct.id}`}); let d = w.document;
  const a = await until(() => d.querySelector('#view .ctcard a.ctmap'), 60);
  check(a && a.textContent === 'Hauptstr. 1, 10115 Berlin, Germany', '#2086: the address is a link ' + (a?.textContent || ''));
  check(a && a.getAttribute('href') === 'https://www.google.com/maps/search/?api=1&query=Hauptstr.%201%2C%2010115%20Berlin%2C%20Germany', '#2086: Google Maps, URL-encoded ' + a?.getAttribute('href'));
  check(a && a.target === '_blank' && /noopener/.test(a.rel), '#2086: a new tab, noopener');

  // ================= #2082 Create as client (+ undo)
  click(w, d.querySelector('#view [data-ct="cmenu"]'));
  await until(() => items(d).length, 30);
  let it = items(d).find(b => /Create as client/.test(b.textContent));
  check(!!it && !items(d).some(b => /Open client/.test(b.textContent)), '#2082: the menu offers "Create as client"');
  if (it) click(w, it);
  let cl = await until(acme, 40);
  check(!!cl, '#2082: the client is made');
  const full = cl ? await call('GET', `/api/clients/${cl.id}`) : {};
  check(full.contacts?.[0]?.contact_id === ct.id && full.contacts[0].name === 'Petra Buyer' && full.contacts[0].role === 'Head of purchasing', '#2082: the contact is its linked contact person ' + JSON.stringify(full.contacts || []).slice(0, 160));
  check(full.email === 'petra@example.com' && full.phone === '+49 30 1234' && full.org_id === ORG, '#2082: e-mail, phone, the organisation of the address book');
  check(full.billing?.street === 'Hauptstr. 1' && full.billing?.zip === '10115' && full.billing?.city === 'Berlin' && full.billing?.country === 'DE', '#2082: the address, the country as its code ' + JSON.stringify(full.billing || {}).slice(0, 160));
  await until(() => /Added: Acme GmbH/.test(d.querySelector('#toast')?.textContent || ''), 30);
  check(/Added: Acme GmbH/.test(d.querySelector('#toast')?.textContent || ''), '#2082: a toast with Undo');
  check(await until(() => d.querySelector(`#view .cklsec a[href="#client/${cl?.id}"]`), 40), '#2082: the card lists the client');
  await undoToast(w, /Added: Acme GmbH/);  // 2.312.0 A (#3283)
  check(await until(async () => !(await acme()), 40), '#2082: Undo deletes the client again');
  await until(() => !d.querySelector('#view .cklsec'), 40);
  check(!d.querySelector('#view .cklsec'), '#2082: ... and the card no longer lists it');
  // again, then the menu offers "Open client"
  click(w, d.querySelector('#view [data-ct="cmenu"]'));
  await until(() => items(d).length, 30);
  it = items(d).find(b => /Create as client/.test(b.textContent));
  if (it) click(w, it);
  cl = await until(acme, 40);
  await until(() => d.querySelector('#view .cklsec'), 40);
  click(w, d.querySelector('#view [data-ct="cmenu"]'));
  await until(() => items(d).length, 30);
  it = items(d).find(b => /Open client/.test(b.textContent));
  check(!!it && !items(d).some(b => /Create as client/.test(b.textContent)), '#2082: a linked contact offers "Open client"');
  if (it) { click(w, it); await until(() => w.location.hash === `#client/${cl?.id}`, 30); }
  check(w.location.hash === `#client/${cl?.id}`, '#2082: "Open client" opens the client ' + w.location.hash);
  check(/maps\.apple\.com\/\?q=Berlin/.test(w.eval(`Object.defineProperty(navigator, 'userAgent', {value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)', configurable: true}); ctk_mapLink('Berlin')`)), '#2086: Apple Maps on an iPhone');
  w.close();

  // the client page's address is a map link too
  w = await boot({hash: `client/${cl.id}`}); d = w.document;
  const ca = await until(() => d.querySelector('#view .cldetail a.ctmap'), 60);
  check(ca && /google\.com\/maps\/search\/\?api=1&query=Hauptstr\.%201/.test(ca.getAttribute('href')), '#2086: the client page\'s address is a map link');
  w.close();

  // ================= #2083 the history
  const off = await call('POST', '/api/office/docs', {kind: 'offer', client_id: cl.id, project_title: 'Image film', date: '2026-09-01'});
  check([200, 201].includes(off.http), 'setup: a quotation for the client ' + off.http);
  const ev = await call('POST', '/api/events', {title: 'Kick-off', start: '2026-09-14T10:00', attendees: [{contact_id: ct.id}]});
  check([200, 201].includes(ev.http), 'setup: an event with the contact ' + ev.http);
  w = await boot({hash: `contacts/${ct.id}`}); d = w.document;
  const sec = await until(() => { const x = d.querySelector('#view .ctkhist'); return x && !x.hidden && x.querySelector('li') ? x : null; }, 60);
  check(sec && /Interactions/.test(sec.querySelector('h4')?.textContent || ''), '#2083: the card shows "Interactions" (#7015)');
  const lis = sec ? [...sec.querySelectorAll('li')].map(x => x.textContent) : [];
  // 2.1221.0 (#6241): since #6119 (2.1174.0) the contact's events are no longer in the history - the card shows them in its own block "Events"
  check(lis.length === 1 && /Image film/.test(lis[0]) && /Quotation/.test(lis[0]) && !lis.some(x => /Kick-off/.test(x)), '#2083: the history lists the quotation, the event not twice ' + JSON.stringify(lis));
  check(sec && sec.querySelector(`a[href="#office/offers/${off.id}"]`), '#2083: the history entry opens its quotation');
  const evb = [...d.querySelectorAll('#view .ctsec')].find(x => /^Events$/.test(x.querySelector('h4')?.textContent || ''));
  check(evb && /Kick-off/.test(evb.textContent) && evb.querySelector(`[data-evopen="${ev.id}"]`) && !sec?.querySelector('[data-evopen]'), '#2083: the event sits in the card\'s block "Events" and opens from there');
  check(sec && !sec.querySelector('[data-ctkmore]'), '#2083: no "Show more" on one page');
  w.close();
  w = await boot({hash: `contacts/${ct.id}`, mobile: true}); d = w.document;
  const ms = await until(() => { const x = d.querySelector('#view .ctkhist'); return x && !x.hidden && x.querySelector('li') ? x : null; }, 60);
  check(ms && d.querySelector('#view .ctcard a.ctmap'), '#2083 phone: the history and the map link on the card');
  w.close();

  console.log(`p21191_b_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
