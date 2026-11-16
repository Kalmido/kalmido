// Package 2.1254.0 C (#6180) UI test: organisation colour in office and clients.
// kalmido-suite: fresh
// Rule (owner decision 14.11.2026): what belongs to an organisation wears its colour - the office badge and the open office page
// (#main.wsc-on), the entries of the area overview (stripe), a client row (stripe) and the open client card; "All" shows the origin of
// a client; Private stays neutral; a person without an organisation sees nothing coloured. jsdom, invented people only.
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
  check(!d.querySelector('.ofcws[data-wsc]') && !d.querySelector('#main').classList.contains('wsc-on'), '#6180 the private office: badge and page neutral');
  w.close();

  // ---- area overview under "All": entries with stripe
  w = await boot({hash: 'office'}); d = w.document;
  await call('PATCH', '/api/settings', {workspace: 'all'});
  const ov = w.eval(`(() => { const o = spo_html(sp => 'office/s/' + sp, [['org:${ORG}', 'Studio', ''], ['private', 'Private', '']]); const x = document.createElement('div'); x.innerHTML = o; return [...x.querySelectorAll('.spovr')].map(a => [a.dataset.spov, a.dataset.wso || '', a.dataset.wsc || '']); })()`);
  check(JSON.stringify(ov) === JSON.stringify([['org:' + ORG, '1', '1'], ['private', '', '']]), '#6180 the overview: the organisation entry has the stripe, Private none ' + JSON.stringify(ov));
  w.close();

  // ---- clients under "All": stripe, origin, open card
  w = await boot({hash: 'clients'}); d = w.document;
  check(await until(() => d.querySelector(`.ctrow[data-clopen="${CO}"]`)), 'clients: the list is there');
  const ro = d.querySelector(`.ctrow[data-clopen="${CO}"]`), rp = d.querySelector(`.ctrow[data-clopen="${CP}"]`);
  check(ro?.dataset.wso === '1' && ro.style.getPropertyValue('--wsd') === want.d, '#6180 the client row of the organisation has the stripe');
  check(rp && !rp.dataset.wsc, '#6180 the private client row is neutral');
  check(!!ro.querySelector('.wso.ctorg') && /Studio/.test(ro.querySelector('.wso').textContent) && /Private/.test(rp.querySelector('.wso')?.textContent || ''), '#6180 "All": each client shows its origin (Studio / Private)');
  w.eval(`go('client/${CO}')`);
  check(await until(() => d.querySelector('.msclcard[data-wsc]') && main().classList.contains('wsc-on')), '#6180 the open client card is marked (card + #main)');
  w.eval(`go('client/${CP}')`);
  check(await until(() => d.querySelector('.msclcard') && !d.querySelector('.msclcard[data-wsc]') && !main().classList.contains('wsc-on')), '#6180 the open private client: neutral');
  w.close();

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
