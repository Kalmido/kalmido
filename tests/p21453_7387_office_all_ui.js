// kalmido-suite: fresh
// Package 2.1453.0 (#7387) UI test (owner decision 19.11.2026 and its addition): the office under "All workspaces".
// Own container (start.sh), jsdom at a computer's and a phone's width, invented data only. Alice: Private + the organisations
// Alpha (a colour) and Bravo; Bob: member of Alpha (office group "Staff": only his own receipts, travel, entertainment, times)
// and of Bravo (office group without any right).
// - several offices: the panel (and the phone's drawer, the same drawing) shows ONE entry per office with its stripe (Private in
//   my own colour); unfolded it holds that office's menu, every link carries the office (#office/s/<space>/...)
// - the rights of THAT office: Bob sees Alpha with only his points (no Quotations), no entry for Bravo
// - the office used last is unfolded after a new load, the others closed; a tap on "Office" opens it at its point used last;
//   the very first time "Office" leads to the overview of the offices (#office)
// - exactly one office under "All" (Private's and Bravo's office off): no entries, the full menu as with Alpha chosen on top
//   (also on #clients), the frame and :root in Alpha's tone; with a second office again one entry per office and only the
//   open office's page in its tone
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route (Person ohne Organisation unverändert: p2351_a_officetree_ui)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body, sp) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck, ...(sp ? {'X-Kalmido-Office-Space': sp} : {})}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), http: r.status};
  }
};
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const FEAT = 'cal,comments,collab,office,clients,files,docs';
const R = '/api/office/rights';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, ws_colors: JSON.stringify({private: 'red'})});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const A = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id})).id;
  const Bo = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Bravo', admin_id: me.id})).id;
  check(A > 0 && Bo > 0, 'setup: organisations Alpha and Bravo');
  check((await call(CA, 'PATCH', '/api/orgs/' + A, {color: '#e0b05c'})).http === 200, 'setup: Alpha\'s colour');
  const WA = 'org:' + A, WB = 'org:' + Bo;
  await call(CA, 'PATCH', '/api/settings', {workspace: 'all'});
  const bob = await call(CA, 'POST', '/api/users', {orgs: [{id: A, role: 'member'}, {id: Bo, role: 'member'}], username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com'});
  check(bob.id, 'setup: Bob, member of Alpha and Bravo ' + JSON.stringify(bob).slice(0, 200));
  const grp = async (sp, src, name) => { const g = await call(CA, 'POST', R + '/groups', {from: src, name}, sp); return g.id ? `g:${g.id}` : null; };
  const gA = 'tpl:staff', gB = await grp(WB, 'tpl:none', 'Nothing');
  check((await call(CA, 'PUT', `${R}/people/${bob.id}`, {groups: [gA]}, WA)).http === 200, 'setup: Bob in Alpha\'s group Staff');
  check(gB && (await call(CA, 'PUT', `${R}/people/${bob.id}`, {groups: [gB]}, WB)).http === 200, 'setup: Bob in Bravo\'s group without rights');
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'all'});

  const arrow = (d, k) => [...d.querySelectorAll('#side [data-act="sbb-tree"]')].find(b => b.dataset.k === k);
  const entries = d => [...d.querySelectorAll('#side .sbbt[data-ofmsp]')].map(x => x.dataset.ofmsp).join();
  const entry = (d, sp) => d.querySelector(`#side .sbbt[data-ofmsp="${sp}"]`);
  const menuOf = (d, sp) => d.querySelector(`#side [data-ofmsp-menu="${sp}"]`);
  const stripe = el => el && el.dataset.wso === '1' ? el.style.getPropertyValue('--wsd') : '';
  const lsOf = (w, ks) => Object.fromEntries(ks.map(k => [k, w.localStorage.getItem(k)]).filter(([, v]) => v != null));

  // ================= Alice, a computer, "All", the very first time
  let w = await boot({hash: 'tasks', allWs: true}), d = w.document;
  check(await until(() => w.eval('typeof ofm_multi === "function" && ofm_multi()')), 'Alice: several offices under "All"');
  check(w.eval(`mg_target('office')`) === 'office', '#7387 the very first time "Office" leads to the overview of the offices ' + w.eval(`mg_target('office')`));
  w.location.hash = '#office';
  check(await until(() => entries(d) === `private,${WA},${WB}`), '#7387 one entry per office (Private, Alpha, Bravo) ' + entries(d));
  const tone = w.eval(`({a: WSC_TONES[wsc_ix(wsOrg(${A}).color, ${A})][0], red: LP_TONES.find(x => x[0] === 'red')[2]})`);
  check(stripe(entry(d, WA)) === tone.a, '#7387 Alpha\'s entry wears Alpha\'s stripe');
  check(stripe(entry(d, 'private')) === tone.red, '#7387 Private\'s entry wears my own Private colour');
  check(!menuOf(d, WA) && !menuOf(d, WB) && !menuOf(d, 'private'), '#7387 nothing used yet: every entry closed');
  arrow(d, 'of:sp:' + WA).click();
  check(await until(() => menuOf(d, WA)?.querySelector('[data-ofm="invoices"]') && menuOf(d, WA)?.querySelector('[data-ofm="offers"]')), '#7387 Alpha\'s entry unfolds to its menu');
  const gos = [...menuOf(d, WA).querySelectorAll('[data-go]')].map(b => b.dataset.go);
  check(gos.length > 3 && gos.filter(g => g.startsWith('office')).every(g => g.startsWith(`office/s/${WA}/`)), '#7387 every office link of Alpha\'s menu carries Alpha (Clients / Contacts are pages of their own) ' + gos.filter(g => !g.startsWith(`office/s/${WA}/`)).join());
  // as a person: a tap on Invoices of Alpha
  const inv = menuOf(d, WA).querySelector('[data-ofm="invoices"]');
  (inv.matches('[data-go]') ? inv : inv.querySelector('[data-go]') || inv).click();
  check(await until(() => w.eval('S.route.wsp') === WA && w.eval('S.route.tab') === 'invoices'), '#7387 Invoices of Alpha open in Alpha ' + w.location.hash);
  check(await until(() => entry(d, WA)?.classList.contains('on') && arrow(d, 'of:sp:' + WA)?.dataset.open), '#7387 the open office\'s entry is open and marked');
  check(w.eval('wsCur()') === 'all', 'the workspace on top stays "All"');
  const keep = lsOf(w, ['tasks.ofmLastSp', 'tasks.ofmLastBy', 'tasks.ofmLast', 'tasks.sbbLast', 'tasks.mgTab']);
  w.close();

  // a new load: the office used last is unfolded, the others closed; "Office" opens it at its point used last
  w = await boot({hash: 'tasks', allWs: true, ls: keep}); d = w.document;
  check(await until(() => w.eval('typeof ofm_multi === "function" && ofm_multi()')), 'a new load on Tasks');
  check(w.eval(`mg_target('office')`) === `office/s/${WA}/invoices`, '#7387 "Office" opens Alpha at Invoices ' + w.eval(`mg_target('office')`));
  check(w.eval(`sbb_target('office')`) === `office/s/${WA}/invoices`, '#7387 the bar\'s Office (the page kept) opens Alpha at Invoices ' + w.eval(`sbb_target('office')`));
  w.location.hash = '#office';
  check(await until(() => entries(d) === `private,${WA},${WB}` && menuOf(d, WA)), '#7387 after a new load Alpha (used last) is unfolded');
  check(!menuOf(d, WB) && !menuOf(d, 'private'), '#7387 ... the other offices closed');
  // the phone's drawer: the same drawing
  w.close();
  w = await boot({hash: `office/s/${WA}/invoices`, allWs: true, mobile: true}); d = w.document;
  check(await until(() => (w.eval(`sbb_panelHtml('office')`).match(/data-ofmsp="/g) || []).length === 3), '#7387 phone: the drawer holds one entry per office');
  w.close();

  // ================= Bob: the rights of each office
  w = await boot({user: 'bob', hash: 'office', allWs: true}); d = w.document;
  check(await until(() => entry(d, WA)), 'Bob: Alpha\'s entry');
  arrow(d, 'of:sp:' + WA)?.click();
  check(await until(() => menuOf(d, WA)?.querySelector('[data-ofm="travel"]') && !menuOf(d, WA)?.querySelector('[data-ofm="offers"]') && !menuOf(d, WA)?.querySelector('[data-ofm="invoices"]'), 60),
    '#7387 Bob: Alpha\'s menu shows only his points (travel expenses yes, quotations / invoices no) ' + [...(menuOf(d, WA)?.querySelectorAll('[data-ofm]') || [])].map(x => x.dataset.ofm).join());
  check(await until(() => !entry(d, WB), 60), '#7387 Bob: no entry for Bravo (no office right there) ' + entries(d));
  w.close();

  // ================= exactly one office under "All": Alpha only (Private's and Bravo's office off)
  await call(CA, 'PATCH', '/api/settings', {ws_areas_off: JSON.stringify({private: ['office'], [WB]: ['office']})});
  w = await boot({hash: 'office', allWs: true}); d = w.document;
  check(await until(() => w.eval('ofm_one()') === WA && d.querySelector('#side [data-ofm="offers"]')), 'one office: its menu in the panel');
  check(!entries(d), '#7387 one office: no entry to unfold, no overview');
  const ofmKeys = () => [...d.querySelectorAll('#side [data-ofm]')].map(x => x.dataset.ofm).sort().join();
  await until(() => w.eval('!!(typeof OFC === "object" && OFC.info)') && ofmKeys().includes('settings'));
  await sleep(600);
  const keys1 = ofmKeys();
  console.log('one office, keys', keys1);
  const vars = w.eval(`(() => { const t = wsp_barTone('${WA}'); return {wbd: getComputedStyle(document.querySelector('#app')).getPropertyValue('--wbd').trim() || document.querySelector('#app').style.getPropertyValue('--wbd'), want: t && t[0], root: document.documentElement.classList.contains('wac-on')}; })()`);
  check(vars.wbd === vars.want && vars.root, '#7387 one office under "All": the frame and the accent in Alpha\'s tone ' + JSON.stringify(vars));
  w.location.hash = '#clients';
  check(await until(() => w.eval('S.route.mod') === 'clients' && [...d.querySelectorAll('#side [data-ofm]')].map(x => x.dataset.ofm).sort().join() === keys1, 40), '#7387 one office: the same full menu on #clients ' + [...d.querySelectorAll('#side [data-ofm]')].map(x => x.dataset.ofm).sort().join());
  w.close();
  await call(CA, 'PATCH', '/api/settings', {workspace: WA});
  w = await boot({hash: 'office', allWs: true}); d = w.document;
  check(await until(() => [...d.querySelectorAll('#side [data-ofm]')].map(x => x.dataset.ofm).sort().join() === keys1, 40), '#7387 one office under "All" = the menu with Alpha chosen on top ' + keys1 + ' / ' + [...d.querySelectorAll('#side [data-ofm]')].map(x => x.dataset.ofm).sort().join());
  w.close();

  // ================= a second office again: one entry per office, only the open office's page in its tone
  await call(CA, 'PATCH', '/api/settings', {workspace: 'all', ws_areas_off: JSON.stringify({private: ['office']})});
  w = await boot({hash: `office/s/${WA}/offers`, allWs: true}); d = w.document;
  check(await until(() => entries(d) === `${WA},${WB}`), '#7387 two offices: an entry each ' + entries(d));
  await until(() => w.eval(`document.querySelector('#view').classList.contains('wac-loc')`));
  const pg = w.eval(`(() => { const v = document.querySelector('#view'); return {loc: v.classList.contains('wac-loc'), wad: v.style.getPropertyValue('--wad'), want: wac_fit(WSC_TONES[wsc_ix(wsOrg(${A}).color, ${A})][0], false), root: document.documentElement.classList.contains('wac-on')}; })()`);
  check(pg.loc && pg.wad === pg.want, '#7387 two offices: the open office\'s page in Alpha\'s tone ' + JSON.stringify(pg));
  w.close();
  await call(CA, 'PATCH', '/api/settings', {ws_areas_off: '{}'});

  console.log(`p21453_7387_office_all_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
