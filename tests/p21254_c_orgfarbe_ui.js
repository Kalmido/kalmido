// Package 2.1254.0 C (#6180) UI test: organisation colour in office and clients.
// kalmido-suite: fresh
// Rule (owner decision 14.11.2026): what belongs to an organisation wears its colour - the office badge and the open office page
// (#main.wsc-on), the entries of the area overview (stripe), a client row (stripe) and the open client card; "All" shows the origin of
// a client; a person without an organisation sees nothing coloured. jsdom, invented people only.
// Ersetzt Entscheidung #6179 ("Private stays neutral"): gedeckt durch #7661 (20.11.2026) - with an organisation Private wears its
// colour too (the default var(--acc-d) without a choice of my own).
// freelancer-matrix: Person ohne Organisation in der Datei geprüft (solo)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,contacts,office,clients,docs';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio', lang: 'en', collab_all: true, modules: ['comments', 'office', 'clients']});
  check(su.http < 300, 'setup: the organisation Studio ' + JSON.stringify(su));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', ws_colors: '{}', workspace: 'all', features: FEAT});
  const st = await call('GET', '/api/state'), ORG = (st.me.workspaces || [])[0]?.id;
  if (!ORG) { console.log('no organisation', JSON.stringify(st.me)); process.exit(1); }
  await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'});
  const CO = (await call('POST', '/api/clients', {name: 'Orgclient Ltd', org_id: ORG})).id;
  const CP = (await call('POST', '/api/clients', {name: 'Privclient Ltd', org_id: null})).id;
  check(CO && CP, 'setup: a client of the organisation and a private one');

  // ---- the organisation's office: the badge and the page carry the colour
  await call('PATCH', '/api/settings', {workspace: 'org:' + ORG});
  let w = await boot({hash: 'office'}), d = w.document;
  const main = () => d.querySelector('#main');
  const want = w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return {d: t[0], l: t[1]}; })()`);
  check(await until(() => d.querySelector('.ofcws')), 'office of the organisation: the badge is there');
  const bd = d.querySelector('.ofcws');
  check(bd?.dataset.wsc === '1' && bd.style.getPropertyValue('--wsd') === want.d, '#6180 the office badge wears the organisation colour');
  check(await until(() => main().classList.contains('wsc-on') && main().style.getPropertyValue('--wsd') === want.d), '#6180 the open office page reports the organisation (#main.wsc-on)');
  // 2.1254.0 (#6180): an open quotation of the organisation: still marked; back to the list: marked, in and out
  const QD = (await call('POST', '/api/office/docs', {kind: 'offer', client_id: CO, project_title: 'Orgfilm', items: [{title: 'Cut', qty: 1, rate: 100}]})).id;
  check(!!QD, 'setup: a quotation in the organisation office');
  w.eval(`go('office/offers/${QD}')`);
  check(await until(() => d.querySelector('.ofdhead') && main().classList.contains('wsc-on') && main().style.getPropertyValue('--wsd') === want.d), '#6180 the open quotation wears the organisation colour (#main.wsc-on)');
  w.eval(`go('office/offers')`);
  check(await until(() => !d.querySelector('.ofdhead') && main().classList.contains('wsc-on')), '#6180 back from the quotation: the office page stays marked');
  w.eval(`go('office/receipts')`);
  check(await until(() => w.eval(`S.route.tab === 'receipts'`)) && await until(() => main().classList.contains('wsc-on')), '#6180 another office page: still marked');
  w.close();

  // ---- the private office: neutral
  await call('PATCH', '/api/settings', {workspace: 'private'});
  w = await boot({hash: 'office'}); d = w.document;
  await until(() => d.querySelector('#view .office'));
  await sleep(800);
  check(!!d.querySelector('.ofcws[data-wsc]') && await until(() => d.querySelector('#main').classList.contains('wsc-on') && d.querySelector('#main').style.getPropertyValue('--wsd') === 'var(--acc-d)'), '#7661 (was #6180 neutral): the private office: badge and page in Private\'s colour');
  w.close();

  // ---- area overview under "All": entries with stripe
  w = await boot({hash: 'office'}); d = w.document;
  await call('PATCH', '/api/settings', {workspace: 'all'});
  const ov = w.eval(`(() => { const o = spo_html(sp => 'office/s/' + sp, [['org:${ORG}', 'Studio', ''], ['private', 'Private', '']]); const x = document.createElement('div'); x.innerHTML = o; return [...x.querySelectorAll('.spovr')].map(a => [a.dataset.spov, a.dataset.wso || '', a.dataset.wsc || '']); })()`);
  check(JSON.stringify(ov) === JSON.stringify([['org:' + ORG, '1', '1'], ['private', '1', '1']]), '#6180 / #7661 the overview: the organisation entry and Private have their stripe ' + JSON.stringify(ov));
  w.close();

  // ---- clients under "All": stripe, origin, open card
  w = await boot({hash: 'clients'}); d = w.document;
  check(await until(() => d.querySelector(`.ctrow[data-clopen="${CO}"]`)), 'clients: the list is there');
  const ro = d.querySelector(`.ctrow[data-clopen="${CO}"]`), rp = d.querySelector(`.ctrow[data-clopen="${CP}"]`);
  check(ro?.dataset.wso === '1' && ro.style.getPropertyValue('--wsd') === want.d, '#6180 the client row of the organisation has the stripe');
  check(rp && rp.dataset.wsc === '1' && rp.style.getPropertyValue('--wsd') === 'var(--acc-d)', '#7661 (was #6180 neutral): the private client row wears Private\'s colour');
  check(!!ro.querySelector('.wso.ctorg') && /Studio/.test(ro.querySelector('.wso').textContent) && /Private/.test(rp.querySelector('.wso')?.textContent || ''), '#6180 "All": each client shows its origin (Studio / Private)');
  w.eval(`go('client/${CO}')`);
  check(await until(() => d.querySelector('.msclcard[data-wsc]') && main().classList.contains('wsc-on')), '#6180 the open client card is marked (card + #main)');
  w.eval(`go('client/${CP}')`);
  check(await until(() => d.querySelector('.msclcard[data-wsc]') && main().classList.contains('wsc-on') && main().style.getPropertyValue('--wsd') === 'var(--acc-d)'), '#7661 (was #6180 neutral): the open private client in Private\'s colour');
  w.close();

  // ---- 2.1333.0 (#6697): "All" while office, clients and time tracking are switched off in Private -- the modules belong to the
  // organisation alone, so the whole frame wears its colour: :root's accent (rail, panel, header, tab bar), the stripe on top of the
  // sidebar (#app --wbl), the office's header names the organisation. Desktop and phone. Without the fix :root stays Kalmido's accent.
  const S_mod = w2 => w2.eval('S.route.mod');
  await call('PATCH', '/api/settings', {workspace: 'all', features: FEAT + ',time', ws_mods_off: JSON.stringify({private: ['office', 'clients', 'time']})});
  const frame = (w2, wt) => { const de = w2.document.documentElement, app = w2.document.querySelector('#app');
    return {root: de.classList.contains('wac-on') && de.style.getPropertyValue('--wal') === wt[2] && de.style.getPropertyValue('--wad') === wt[0], stripe: app?.style.getPropertyValue('--wbl') === want.l && app?.style.getPropertyValue('--wbd') === want.d,
      scope: w2.eval('wso_scope()'), ws: w2.eval('wsCur()')}; };
  for (const mobile of [false, true]) {
    const tag = mobile ? 'phone' : 'desktop';
    w = await boot({hash: 'office', mobile, allWs: true}); d = w.document;  // allWs: stay on "All" (boot would switch into the office's workspace)
    const wt = w.eval(`wac_tone('org:${ORG}')`);
    check(await until(() => d.querySelector('.ofcws')), `#6697 ${tag}: the office opens under "All" (only the organisation has one)`);
    check(await until(() => frame(w, wt).root && frame(w, wt).stripe), `#6697 ${tag}: office under "All" with one office - accent and stripe in the organisation colour ` + JSON.stringify(frame(w, wt)));
    check(/Studio/.test(d.querySelector('.ofcws')?.textContent || ''), `#6697 ${tag}: the office header names the organisation`);
    check(w.eval('wsCur()') === 'all', `#6697 ${tag}: the switch itself stays on "All"`);
    if (mobile) {  // the drawer and the tab bar: the same :root accent, nothing local overrides it
      w.eval(`document.querySelector('#top [data-act="side"]')?.click()`);
      check(await until(() => d.querySelector('#side.open')) && !d.querySelector('#side .wac-loc') && frame(w, wt).root, '#6697 phone: the drawer follows the organisation accent');
    } else {
      check(!!d.querySelector('#srail .srb.on, #side .srow.on') && !d.querySelector('#srail .wac-loc'), '#6697 desktop: the active office entry takes the accent of :root (no local Kalmido tone)');
    }
    w.eval(`go('clients')`);
    check(await until(() => d.querySelector(`.ctrow[data-clopen="${CO}"]`) && frame(w, wt).root && frame(w, wt).stripe), `#6697 ${tag}: clients under "All", only in the organisation - its colour ` + JSON.stringify(frame(w, wt)));
    w.eval(`go('time')`);
    check(await until(() => S_mod(w) === 'time' && frame(w, wt).root && frame(w, wt).stripe), `#6697 ${tag}: time tracking under "All", only in the organisation - its colour ` + JSON.stringify(frame(w, wt)));
    w.eval(`go('today')`);
    check(await until(() => S_mod(w) === 'tasks' && !d.documentElement.classList.contains('wac-on') && !frame(w, wt).scope), `#6697 ${tag}: back on a page of every workspace - Kalmido's accent again`);
    w.close();
  }
  // the module on in both workspaces again: the office is a page of two workspaces, the frame stays Kalmido's accent (rule #4222)
  await call('PATCH', '/api/settings', {workspace: 'all', ws_mods_off: '{}'});
  w = await boot({hash: 'clients'}); d = w.document;
  check(await until(() => d.querySelector(`.ctrow[data-clopen="${CO}"]`)), 'clients in both workspaces: the list is there');
  check(!d.documentElement.classList.contains('wac-on') && w.eval('wso_scope()') === '', '#6697 clients of two workspaces under "All": the frame stays Kalmido\'s accent');
  // a mixed page with an open object of the organisation: the active sidebar row wears its tone (wac-loc), a private one does not
  const LO = (await call('POST', '/api/lists', {name: 'Orgproject', org_id: ORG})).id, LP = (await call('POST', '/api/lists', {name: 'Ownproject', org_id: null})).id;
  w.close();
  for (const mobile of [false, true]) {
    const tag = mobile ? 'phone' : 'desktop';
    w = await boot({hash: 'l/' + LO, mobile}); d = w.document;
    const wt = w.eval(`wac_tone('org:${ORG}')`);
    if (mobile) w.eval(`document.querySelector('#top [data-act="side"]')?.click()`);
    const row = id => d.querySelector(`#side .srow[data-list="${id}"]`);
    check(await until(() => row(LO)?.classList.contains('on') && row(LO).classList.contains('wac-loc') && row(LO).style.getPropertyValue('--wal') === wt[2]), `#6697 ${tag}: open project of the organisation under "All" - its active sidebar row in the organisation tone ` + (row(LO)?.outerHTML || '').slice(0, 300));
    check(!d.documentElement.classList.contains('wac-on'), `#6697 ${tag}: a mixed page keeps Kalmido's accent on :root`);
    w.eval(`go('l/${LP}')`);
    check(await until(() => row(LP)?.classList.contains('on') && !d.querySelector('#side .wac-loc')), `#6697 ${tag}: the private project - no organisation tone left in the sidebar`);
    w.close();
  }

  // ---- a person without an organisation: nothing coloured, nothing broken
  await call('POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, CS);
  const SC = (await call('POST', '/api/clients', {name: 'Solo client'}, CS)).id;
  w = await boot({user: 'solo', hash: 'clients'}); d = w.document;
  check(await until(() => d.querySelector(`.ctrow[data-clopen="${SC}"]`)), 'solo: the client list is there');
  check(!d.querySelector('.ctrow[data-wsc]') && !d.querySelector('.ctrow .wso'), '#6180 without an organisation: no stripe, no origin');
  w.eval(`go('client/${SC}')`);
  check(await until(() => d.querySelector('.msclcard')) && !d.querySelector('.msclcard[data-wsc]') && !d.querySelector('#main').classList.contains('wsc-on'), '#6180 without an organisation: the card neutral');
  w.eval(`go('office')`);
  await sleep(1000);
  check(!d.querySelector('.ofcws[data-wsc]') && !d.querySelector('#main').classList.contains('wsc-on'), '#6180 without an organisation: the office neutral');
  w.close();

  console.log(`p21254_c_orgfarbe_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
