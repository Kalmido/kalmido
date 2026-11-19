// #7292 UI test: a client's locations in the client list, the form and the main client's card. jsdom, fresh container,
// kalmido-suite: fresh
// invented names only:
//  - the list shows a location indented right under its main client (its own part of the label), the search finds both
//  - the main client's card: the block "Locations" with all together and one linked row per location; the link opens the
//    location, whose card names its main client with a link back
//  - the form "Belongs to (main client)": only clients that are no location; chosen + Save = the client is a location
//  - the card's menu "Add location" opens "New client" with the main client chosen; Save makes the location
//  - "Archive" on a main client asks about its locations; "Only the main client" archives it alone
//  - a person without an organisation: the same list and card
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
const rows = d => [...d.querySelectorAll('#view .msclients .ctlist .ctrow')].map(r => ({id: +r.dataset.clopen, site: r.classList.contains('clsite'), t: r.querySelector('.ctn b')?.textContent || ''}));
const menuItems = d => [...d.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')];
const typeIn = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
const btnText = (d, txt) => [...d.querySelectorAll('.modal button')].find(b => b.textContent.trim() === txt);

// the card of client id (a save may still jump to the client it saved: the card is opened again until it stays)
async function card(w, d, id) {
  for (let i = 0; i < 4; i++) {
    w.eval(`go('client/${id}')`);
    const b = await until(() => w.eval('CLV.data?.id') === id && w.eval('S.route.client') === id && d.querySelector('#view [data-mscl="cmenu"]'), 5000);
    await sleep(300);
    if (b && w.eval('S.route.client') === id && d.querySelector('#view [data-mscl="cmenu"]')) return d.querySelector('#view [data-mscl="cmenu"]');
  }
  return null;
}
async function listAndCard(ck, user, tag) {
  const P = (await call(ck, 'POST', '/api/clients', {name: 'Acme Group'})).id;
  const S1 = (await call(ck, 'POST', '/api/clients', {name: 'Acme Group', city: 'Zurich', parent_id: P})).id;
  const X = (await call(ck, 'POST', '/api/clients', {name: 'Beta Works'})).id;
  check(P && S1 && X, `${tag}: a main client, a location, another client`);
  const w = await boot({user, hash: 'clients'}), d = w.document;
  check(await until(() => rows(d).length === 3), `${tag}: three rows ` + JSON.stringify(rows(d)));
  const r = rows(d), iP = r.findIndex(x => x.id === P), iS = r.findIndex(x => x.id === S1);
  check(iS === iP + 1 && r[iS].site && !r[iP].site && !r.find(x => x.id === X).site, `${tag}: the location indented right under its main client ` + JSON.stringify(r));
  check(/Zurich/.test(r[iS].t) && !/Acme Group · /.test(r[iS].t.replace(/^Location of [^:]*: /, '')), `${tag}: the row shows the location's own part: ${r[iS].t}`);
  // ---- the search finds the location (on its own when the main client does not match)
  typeIn(w, d.querySelector('#mscl-q'), 'Zurich');
  check(await until(() => { const x = rows(d); return x.length >= 1 && x.some(y => y.id === S1) && !x.some(y => y.id === X); }), `${tag}: the search finds the location ` + JSON.stringify(rows(d)));
  typeIn(w, d.querySelector('#mscl-q'), '');
  await until(() => rows(d).length === 3);
  return {w, d, P, S1, X};
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  {
    const {w, d, P, S1, X} = await listAndCard(CA, 'alice', 'alice');
    // ---- the main client's card: the block Locations, the link to the location and back
    w.eval(`go('client/${P}')`);
    const sec = await until(() => d.querySelector('#view .clsites'));
    check(sec && /All locations together/.test(sec.textContent), 'card: the block "Locations" with all together');
    const a = sec && sec.querySelector(`a[href="#client/${S1}"]`);
    check(a && /Zurich/.test(a.textContent), 'card: a linked row for the location ' + (a && a.textContent));
    if (a) {
      w.eval(`go('client/${S1}')`);
      const back = await until(() => d.querySelector(`#view .clparent a[href="#client/${P}"]`));
      check(back && /Acme Group/.test(back.textContent), "card of the location: 'Location of Acme Group' with a link back");
    }
    // ---- the form: "Belongs to (main client)"
    w.eval(`go('client/${X}')`);
    const eb = await until(() => w.eval('CLV.data?.id') === X && d.querySelector('#view [data-act="client-edit"]'));
    eb.click();
    const md = await until(() => d.querySelector('.modal.cldlg #cl-parent') && d.querySelector('.modal.cldlg'));
    const opts = md ? [...md.querySelectorAll('#cl-parent option')].map(o => +o.value) : [];
    check(opts.includes(P) && !opts.includes(S1) && !opts.includes(X), 'form: the main clients to choose (no location, not itself) ' + opts);
    if (md) {
      md.querySelector('#cl-parent').value = String(P);
      md.querySelector('#cl-parent').dispatchEvent(new w.Event('change', {bubbles: true}));
      md.querySelector('[data-m="save"]').click();
      check(await until(async () => (await call(CA, 'GET', `/api/clients/${X}`)).parent_id === P), 'form: Save makes Beta Works a location of Acme Group');
      check(await until(() => !d.querySelector('.modal.cldlg')), 'form: the dialog closes');
    }
    // ---- the card's menu: "Add location"
    const mb = await card(w, d, P);
    check(mb, 'menu: the card of the main client');
    mb?.click();
    let its = await until(() => { const x = menuItems(d); return x.length && x; }) || [];
    const add = its.find(x => x.textContent.trim() === 'Add location');
    check(add, 'menu: "Add location" ' + its.map(x => x.textContent.trim()));
    if (add) {
      add.click();
      const nm = await until(() => d.querySelector('.modal.cldlg #cl-parent') && d.querySelector('.modal.cldlg'));
      check(nm && nm.querySelector('#cl-parent').value === String(P) && nm.querySelector('#cl-more')?.open, 'menu: "New client" with the main client chosen, the details open');
      if (nm) {
        typeIn(w, nm.querySelector('#cl-name'), 'Acme Bonn');
        nm.querySelector('[data-m="save"]').click();
        check(await until(async () => ((await call(CA, 'GET', '/api/clients')).clients || []).some(c => c.name === 'Acme Bonn' && c.parent_id === P)), 'menu: Save makes the location');
      }
    }
    // ---- Archive asks about the locations; "Only the main client"
    await until(() => w.eval(`(S.clients || []).filter(c => c.parent_id === ${P}).length`) >= 2);
    const mb2 = await card(w, d, P);
    check(mb2, 'archive: the card of the main client');
    mb2?.click();
    its = await until(() => { const x = menuItems(d); return x.length && x; }) || [];
    its.find(x => x.textContent.trim() === 'Archive')?.click();
    const only = await until(() => btnText(d, 'Only the main client'));
    check(only && /Archive its \d locations too\?/.test(d.querySelector('.modal')?.textContent || ''), 'archive: asks about the locations');
    only?.click();
    check(await until(async () => (await call(CA, 'GET', `/api/clients/${P}`)).archived === true), 'archive: the main client archived');
    check(!(await call(CA, 'GET', `/api/clients/${S1}`)).archived, 'archive: the location stays');
    w.close();
  }

  // ---------------- a person without an organisation
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(((await call(CF, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida has no organisation');
  const f = await listAndCard(CF, 'frida', 'freelancer');
  f.w.eval(`go('client/${f.P}')`);
  check(await until(() => f.d.querySelector(`#view .clsites a[href="#client/${f.S1}"]`)), 'freelancer: the block "Locations" links the location');
  f.w.close();

  console.log(`p7292_client_sites_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
