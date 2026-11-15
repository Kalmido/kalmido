// kalmido-suite: fresh
// Package 2.1223.0 (#6181-#6185) UI test: the organisation colour in the areas Calendar, Wiki, Team chat, Files / Documents and
// Contacts, on the core's block (wscolor.js wso_row / wso_origin / wso_open / wso_sync, docs/dev/kern.md "Organisation colour").
// Rule (owner decision 14.11.2026): what belongs to an organisation wears its colour - its entry (a stripe) and the open object
// (#main.wsc-on, under "All workspaces" #view.wac-loc); Private stays neutral. Each area is used as a person does: the entry is
// seen with its name, opened, and the open object is marked; a private one next to it stays neutral.
// freelancer-matrix: n/a - nur Oberfläche (Person ohne Organisation in der Datei geprüft)
// jsdom only (the stripe as drawn is checked in Firefox by p21205_b_orgcolor_ui).
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
const pad = n => String(n).padStart(2, '0');
const now = new Date(), T0 = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments', 'collab', 'team']});
  check(su.http < 300, 'setup: the organisation Studio ' + JSON.stringify(su));
  const st0 = await call('GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(',').filter(Boolean), 'cal', 'events', 'contacts', 'wiki', 'team', 'collab', 'files'])].join(',');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', ws_colors: '{}', workspace: 'all', features: feats});
  const ORG = ((await call('GET', '/api/state')).me.workspaces || [])[0]?.id;
  if (!ORG) { console.log('no organisation'); process.exit(1); }
  check((await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'})).http === 200, 'setup: the admins set the organisation colour');
  // the objects: one of the organisation, one private, per area
  const CO = await call('POST', '/api/evcals', {name: 'Studio calendar', org_id: ORG}), CP = await call('POST', '/api/evcals', {name: 'Home calendar', org_id: null});
  check(CO.id && CP.id, 'setup: a calendar of the organisation and a private one');
  check((await call('POST', '/api/events', {title: 'Studio meeting', cal_id: CO.id, start: `${T0}T10:00`, end: `${T0}T11:00`, reminders: []})).id, 'setup: an event of the organisation');
  check((await call('POST', '/api/events', {title: 'Dentist', cal_id: CP.id, start: `${T0}T15:00`, end: `${T0}T16:00`, reminders: []})).id, 'setup: a private event');
  const WP = (await call('POST', '/api/wiki/pages', {space: 'org:' + ORG, path: 'Team handbook', body: 'Read me first.'})).id;
  const PP = (await call('POST', '/api/wiki/pages', {space: 'private', path: 'Own notes', body: 'Mine.'})).id;
  check(WP && PP, 'setup: a wiki page of the organisation and a private one');
  const RID = (await call('POST', '/api/team/channels', {name: 'Crew', org_id: ORG, open: true})).id;
  check(RID, 'setup: a channel of the organisation');
  const BO = (await call('POST', '/api/books', {name: 'Studio clients', org_id: ORG})).id, BP = (await call('POST', '/api/books', {name: 'Friends', org_id: null})).id;
  const KO = (await call('POST', '/api/contacts', {book_id: BO, given: 'Olga', family: 'Org'})).id, KP = (await call('POST', '/api/contacts', {book_id: BP, given: 'Paul', family: 'Private'})).id;
  check(BO && BP && KO && KP, 'setup: a contact in an address book of the organisation and one in a private book');

  // ================= jsdom, "All workspaces"
  let w = await boot({hash: 'cal'}), d = w.document;
  const main = () => d.querySelector('#main'), view = () => d.querySelector('#view');
  const want = w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return {d: t[0], l: t[1], wad: wac_fit(t[0], false)}; })()`);
  const marked = () => main().classList.contains('wsc-on') && main().style.getPropertyValue('--wsd') === want.d;
  const toned = () => view().classList.contains('wac-loc') && view().style.getPropertyValue('--wad') === want.wad;
  const striped = el => !!el && el.dataset.wso === '1' && el.dataset.wsc === '1' && el.style.getPropertyValue('--wsd') === want.d;
  const neutral = el => !!el && !el.dataset.wso && !el.style.getPropertyValue('--wsd');

  // ---- #6181 Calendar
  const evEl = t => [...d.querySelectorAll('#view [data-cev]')].find(e => e.textContent.includes(t));
  check(await until(() => evEl('Studio meeting') && evEl('Dentist')), '#6181 the calendar shows both events by name');
  const eo = evEl('Studio meeting'), ep = evEl('Dentist');
  check(striped(eo), '#6181 the event of the organisation\'s calendar: its stripe');
  check(eo.style.getPropertyValue('--cc') !== '', '#6181 ... and its calendar colour stays (--cc kept in the one style attribute)');
  check(neutral(ep) && ep.style.getPropertyValue('--cc') !== '', '#6181 the private event: no stripe, its calendar colour');
  const row = w.eval(`(() => { const e = S.cal.items.find(x => x.title === 'Studio meeting'); return cevRow(e, e.d0); })()`);
  check(/data-wso="1"/.test(row) && /class="wso cevo"/.test(row) && /Studio/.test(row) && /--cc:/.test(row), '#6181 an event row (Today, day list) under "All": stripe + where it comes from ' + row.slice(0, 200));
  const rowP = w.eval(`(() => { const e = S.cal.items.find(x => x.title === 'Dentist'); return cevRow(e, e.d0); })()`);
  check(!/data-wso/.test(rowP) && /Private/.test(rowP), '#6181 a private event row: no stripe; under "All" its origin says Private (as the task rows)');
  eo.click();
  check(await until(() => d.querySelector('#pop .cevpop b')?.textContent.includes('Studio meeting') && d.querySelector('#pop .cevpop .cevact')), '#6181 a click opens the event\'s popover with its title and actions');
  const pop = d.querySelector('#pop .cevpop');
  check(striped(pop) && /Studio/.test(pop.querySelector('.cevo')?.textContent || ''), '#6181 the popover: the organisation\'s stripe and its name');
  w.eval(`closePop()`);
  // the calendar list (view options): an organisation's calendar with its dot + name for every member
  const lst = w.eval(`(() => { const c = S.evcals.find(x => x.name === 'Studio calendar'); return {own: wso_row(c, '--cc:red'), dot: wso_head(wso_ws(c))}; })()`);
  check(/data-wso="1"/.test(lst.own) && /--cc:red;--wsd:/.test(lst.own) && /wsp-dot/.test(lst.dot), '#6181 the calendar list row: stripe next to the calendar colour, the dot with the name');
  // the event dialog: stripe + origin, a change of calendar redraws it
  const dlg = w.eval(`(() => { const md = document.createElement('div'); md.innerHTML = '<div class="card"><span class="evwso"></span></div>'; evDlgWs(md, ${CO.id}); const a = {wso: md.firstChild.dataset.wso, o: md.querySelector('.evwso').textContent}; evDlgWs(md, ${CP.id}); return {...a, wso2: md.firstChild.dataset.wso || '', o2: md.querySelector('.evwso').textContent}; })()`);
  check(dlg.wso === '1' && /Studio/.test(dlg.o) && dlg.wso2 === '' && !/Studio/.test(dlg.o2), '#6181 the event dialog: stripe + origin for the organisation\'s calendar, gone after switching to the private one ' + JSON.stringify(dlg));
  w.close();

  // ---- #6182 Wiki
  w = await boot({hash: 'wiki/' + WP}); d = w.document;
  check(await until(() => d.querySelector('article.wkpage')?.textContent.includes('Read me first.')), '#6182 the wiki page of the organisation opens with its text');
  check(striped(d.querySelector('article.wkpage')), '#6182 the open page wears the organisation\'s stripe');
  check(await until(() => marked()), '#6182 the open page of the organisation: #main.wsc-on in its colour');
  check(toned(), '#6182 "All": the page\'s view wears the organisation\'s tone');
  w.eval(`go('wiki/${PP}')`);
  check(await until(() => d.querySelector('article.wkpage')?.textContent.includes('Mine.')), '#6182 the private page opens');
  check(await until(() => !main().classList.contains('wsc-on') && !view().classList.contains('wac-loc')), '#6182 the private page: neutral');
  check(neutral(d.querySelector('article.wkpage')), '#6182 the private page: no stripe');
  const sp = w.eval(`wk_spacesHtml()`);
  check(new RegExp(`data-wksp="org:${ORG}" data-wso="1"`).test(sp) && !/data-wksp="private" data-wso/.test(sp), '#6182 the list of spaces: the organisation\'s with its stripe, Private without');
  const tree = w.eval(`sbb_treeHtml([{k: 't', name: 'Studio', go: 'wiki', wso: 'org:${ORG}'}, {k: 'u', name: 'Private', go: 'wiki', wso: 'private'}])`);
  check(/data-wso="1" data-wsc="1" style="--sbbl:0;--wsd:/.test(tree) && (tree.match(/data-wso/g) || []).length === 1, '#6182 the panel\'s root node of the organisation\'s space: its stripe (the private one none)');
  w.close();

  // ---- #6183 Team chat
  w = await boot({hash: 'team/' + RID}); d = w.document;
  check(await until(() => d.querySelector('.tcrhead .tcrt b')?.textContent.includes('Crew')), '#6183 the channel of the organisation opens with its name');
  check(striped(d.querySelector('.tcrhead')), '#6183 the open conversation\'s head: the organisation\'s stripe');
  check(/Studio/.test(d.querySelector('.tcrhead .tco')?.textContent || ''), '#6183 "All": the head says where it belongs');
  check(await until(() => marked()), '#6183 the open conversation of the organisation: #main.wsc-on (the input\'s frame)');
  check(!!d.querySelector('#tc-in'), '#6183 ... and its input is there');
  check(w.eval(`wso_row(tc_org({kind: 'dm', user_id: 2, name: 'Bob'}))`) === '', '#6183 a direct message stays neutral');
  check(/data-wso/.test(w.eval(`wso_row(tc_org({kind: 'channel', org_id: ${ORG}}))`)) && w.eval(`wso_row(tc_org({kind: 'group', org_id: null}))`) === '', '#6183 a group of the organisation: stripe; without an organisation: none');
  w.close();

  // ---- #6184 Files and documents
  w = await boot({hash: `ablage/s/org:${ORG}`}); d = w.document;
  check(await until(() => marked()), '#6184 the open space of the organisation in Files: #main.wsc-on');
  check(toned(), '#6184 "All": its view wears the organisation\'s tone');
  w.eval(`go('ablage/s/private')`);
  check(await until(() => !main().classList.contains('wsc-on')), '#6184 the private space: neutral');
  const card = w.eval(`dc_card({id: 7, name: 'Invoice.pdf', org_id: ${ORG}, tags: [], state: 'done'})`), cardP = w.eval(`dc_card({id: 8, name: 'Own.pdf', org_id: null, tags: [], state: 'done'})`);
  check(/data-wso="1"/.test(card) && /class="wso dco"/.test(card) && /Invoice\.pdf/.test(card), '#6184 a document card of the organisation: stripe + where it comes from');
  check(!/data-wso/.test(cardP) && /Own\.pdf/.test(cardP), '#6184 a private document card: no stripe');
  w.eval(`window.__dv = document.createElement('div'); wso_mark(__dv, {org_id: ${ORG}})`);
  check(w.eval(`__dv.dataset.wso === '1' && __dv.style.getPropertyValue('--wsd') === ${JSON.stringify(want.d)}`), '#6184 an open document\'s view gets the mark (wso_mark)');
  w.eval(`wso_mark(__dv, 'private')`);
  check(w.eval(`!__dv.dataset.wso && !__dv.style.getPropertyValue('--wsd')`), '#6184 ... and loses it for a private one');
  w.close();

  // ---- #6185 Contacts
  w = await boot({hash: 'contacts'}); d = w.document;
  const ctRow = n => [...d.querySelectorAll('.ctrow')].find(r => r.textContent.includes(n));
  check(await until(() => ctRow('Olga') && ctRow('Paul')), '#6185 the contacts show both people by name');
  check(striped(ctRow('Olga')) && /Studio/.test(ctRow('Olga').querySelector('.cto')?.textContent || ''), '#6185 the contact of the organisation\'s book: stripe + where it comes from');
  check(neutral(ctRow('Paul')) && !/Studio/.test(ctRow('Paul').textContent), '#6185 the private contact: no stripe, no organisation');
  ctRow('Olga').click();
  check(await until(() => d.querySelector('.ctcard #ct-h')?.textContent.includes('Olga')), '#6185 a click opens the card with the name');
  check(striped(d.querySelector('article.ctcard')), '#6185 the open card wears the organisation\'s stripe');
  check(await until(() => marked()), '#6185 the open card of the organisation: #main.wsc-on');
  ctRow('Paul').click();
  check(await until(() => d.querySelector('.ctcard #ct-h')?.textContent.includes('Paul')), '#6185 the private card opens');
  check(await until(() => !main().classList.contains('wsc-on')) && neutral(d.querySelector('article.ctcard')), '#6185 the private card: neutral');
  w.close();

  // ================= one workspace: no origin marks, the open object still marked
  await call('PATCH', '/api/settings', {workspace: 'org:' + ORG});
  w = await boot({hash: 'wiki/' + WP}); d = w.document;
  check(await until(() => d.querySelector('article.wkpage')?.textContent.includes('Read me first.')), 'one workspace: the page opens');
  check(await until(() => marked()), 'one workspace: the open page still marked');
  check(w.eval(`wso_origin(${ORG}, 'cevo')`) === '', 'one workspace: no origin mark');
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= a person without an organisation: nothing coloured
  await call('POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats}, CS);
  const SB = (await call('POST', '/api/books', {name: 'Mine'}, CS)).id;
  check((await call('POST', '/api/contacts', {book_id: SB, given: 'Sam', family: 'Solo'}, CS)).id, 'solo: a contact');
  w = await boot({user: 'solo', hash: 'contacts'}); d = w.document;
  check(await until(() => [...d.querySelectorAll('.ctrow')].some(r => r.textContent.includes('Sam'))), 'solo: the contact is listed');
  const sr = [...d.querySelectorAll('.ctrow')].find(r => r.textContent.includes('Sam'));
  check(neutral(sr), 'solo: no stripe');
  sr.click();
  check(await until(() => d.querySelector('.ctcard #ct-h')?.textContent.includes('Sam')), 'solo: the card opens');
  check(!main().classList.contains('wsc-on') && neutral(d.querySelector('article.ctcard')), 'solo: the open card neutral');
  w.close();

  console.log(`p21223_orgcolor_areas_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
