// 2.380.0 UI tests, leader part (#3420), own container (start.sh), Firefox. freelancer-matrix: office
// 2.1353.0 (#6839): rewritten - the decision of 19.10. (#2251/#2252) holds again: "share by amount" (Producing) is a
// private pack's (from the data folder), the public film pack has only handling costs and markup:
// - the film pack offers no share by amount; a new quotation with the film pack computes by quantities
// - a quotation made before the pack keeps its calculation by quantities when producing is switched on (2.380.0 switched it
//   to the pack's share like a new one - taken back); with only the film pack its editor shows no producing switch
// - a saved quotation with share by amount (made while a pack offered it: here an own pack of the data folder, then
//   switched off for the film pack) keeps computing and showing it: the line in the sums, the switch on, the factor
// - a quotation of an organisation the same as one of a person without an organisation (this test: the person without an
//   organisation, the API part also the organisation)
const fs = require('fs');
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p2380_l_ui', check, shots: 'P2380L_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P2380L_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,office,clients';
const line = (d, k) => (d.totals?.lines || []).find(x => x.kind === k);
// a private pack in the data folder: the film pack with another code and "share by amount" (Producing)
const FILM = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'kalmido', 'office', 'packs', 'industry', 'film.json'), 'utf8'));
const own = {...FILM, code: 'example_share', name: {de: 'Beispiel Privat', en: 'Example private'}, version: 1,
  calc: {share: {label: {de: 'Producing', en: 'Producing'}, rate: 600, factor: 0.25}}};
fs.mkdirSync(path.join(DATA, 'packs', 'industry'), {recursive: true});
fs.writeFileSync(path.join(DATA, 'packs', 'industry', 'example_share.json'), JSON.stringify(own));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});

  // ================= API: the organisation
  check(!(FILM.calc || {}).share && !!FILM.calc?.handling && !!FILM.calc?.markup, '#6839: the film pack file has only handling costs and markup ' + Object.keys(FILM.calc || {}));
  check(FILM.labels.de.share === 'Produktionsleitung' && FILM.labels.en.share === 'Production management', '#6839: the film pack\'s share of the crew is "Produktionsleitung" (decision 19.10. 17:05, #2251)');
  await call(CA, 'PUT', '/api/office/settings', {industry_packs: ['film']});
  const film = ((await call(CA, 'GET', '/api/office/settings')).industry || []).find(x => x.code === 'film');
  await call(CA, 'PUT', '/api/office/settings', {industry_packs: []});
  check(film && !film.calc?.share, '#6839: the film pack offers no share by amount ' + JSON.stringify(film?.calc));
  const SV = (await call(CA, 'POST', '/api/office/services', {name_de: 'Dreh', name_en: 'Shoot', daily_rate: 1000, producing: 1})).id;
  const its = [{kind: 'service', service_id: SV, qty: 6}];
  const qa = await call(CA, 'POST', '/api/office/docs', {project_title: 'Vor dem Paket'});
  check(qa.producing_on === 0 && qa.producing_mode == null, 'a quotation without a pack has no producing');
  await call(CA, 'PUT', `/api/office/docs/${qa.id}/items`, {items: its});
  const qb = await call(CA, 'POST', '/api/office/docs', {project_title: 'Vor dem Paket 2'});
  await call(CA, 'PUT', `/api/office/docs/${qb.id}/items`, {items: its});
  const qq = await call(CA, 'POST', '/api/office/docs', {project_title: 'Nach Mengen'});
  await call(CA, 'PATCH', `/api/office/docs/${qq.id}`, {producing_on: 1, prod_quotient: 3, producing_rate: 600});
  await call(CA, 'PUT', `/api/office/docs/${qq.id}/items`, {items: its});
  check((await call(CA, 'PUT', '/api/office/settings', {industry_packs: ['film'], lang: 'de'})).http === 200, 'film on');
  const qn = await call(CA, 'POST', '/api/office/docs', {project_title: 'Mit Paket'});
  check(qn.producing_mode == null, '#6839: a new quotation with the film pack: no share by amount ' + JSON.stringify([qn.producing_mode, qn.producing_on]));
  const ja = await call(CA, 'PATCH', `/api/office/docs/${qa.id}`, {producing_on: 1, prod_quotient: 3, producing_rate: 600});
  check(ja.producing_on === 1 && ja.producing_mode == null && line(ja, 'producing')?.qty === 2,
    '#6839: switched on in the older quotation: it keeps the calculation by quantities (6 / 3 = 2 days) ' + JSON.stringify([ja.producing_mode, line(ja, 'producing')]));
  const jq = await call(CA, 'PUT', `/api/office/docs/${qq.id}/items`, {items: its});
  check(jq.producing_mode == null && line(jq, 'producing')?.qty === 2, 'a quotation computing by quantities keeps its calculation (6 / 3 = 2 days)');
  // a quotation made while a pack offered share by amount (the private pack) keeps it after that pack is off and film on
  check((await call(CA, 'PUT', '/api/office/settings', {industry_packs: ['example_share']})).http === 200, 'the private pack on');
  // the older quotation, switched on while the private pack is on: still by quantities (2.380.0 made it share by amount - taken back)
  const jb = await call(CA, 'PATCH', `/api/office/docs/${qb.id}`, {producing_on: 1, prod_quotient: 3, producing_rate: 600});
  check(jb.producing_on === 1 && jb.producing_mode == null && line(jb, 'producing')?.qty === 2,
    '#6839: an older quotation switched on with the private pack on keeps its calculation by quantities ' + JSON.stringify([jb.producing_mode, line(jb, 'producing')]));
  const qs = await call(CA, 'POST', '/api/office/docs', {project_title: 'Mit Anteil'});
  check(qs.producing_mode === 'amount' && qs.share_label?.de === 'Producing', 'a new quotation with the private pack: share by amount ' + JSON.stringify([qs.producing_mode, qs.share_label]));
  await call(CA, 'PATCH', `/api/office/docs/${qs.id}`, {producing_on: 1});
  const js0 = await call(CA, 'PUT', `/api/office/docs/${qs.id}/items`, {items: its});
  const p0 = line(js0, 'producing');
  check(p0 && p0.total === 1500 && js0.totals.net === 7500, 'share by amount: 6.000 / 600 x 0,25 = 2,5 days = 1.500 ' + JSON.stringify([p0, js0.totals?.net]));
  check((await call(CA, 'PUT', '/api/office/settings', {industry_packs: ['film']})).http === 200, 'the private pack off, film on');
  const js1 = await call(CA, 'GET', `/api/office/docs/${qs.id}`);
  const js2 = await call(CA, 'PUT', `/api/office/docs/${qs.id}/items`, {items: its});
  check([js1, js2].every(j => j.producing_mode === 'amount' && j.producing_on === 1 && line(j, 'producing')?.total === 1500 && j.totals.net === 7500 && j.share_label?.de === 'Producing'),
    '#6839: the saved quotation with share by amount keeps computing it (read and computed again) ' + JSON.stringify([js1.producing_mode, line(js1, 'producing'), js2.totals?.net]));

  // ================= the person without an organisation: API + editor
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fu.http < 300, 'a person without an organisation ' + fu.http);
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT});
  await call(CF, 'PUT', '/api/office/settings', {company: {name: 'Beispiel Film'}, lang: 'de'});
  const SVF = (await call(CF, 'POST', '/api/office/services', {name_de: 'Schnitt', name_en: 'Edit', daily_rate: 800, producing: 1})).id;
  const qf = await call(CF, 'POST', '/api/office/docs', {project_title: 'Alt ohne Paket'});
  await call(CF, 'PUT', `/api/office/docs/${qf.id}/items`, {items: [{kind: 'service', service_id: SVF, qty: 5}]});
  check(qf.producing_on === 0 && qf.producing_mode == null, 'freelancer: the quotation starts without producing');
  check((await call(CF, 'PUT', '/api/office/settings', {industry_packs: ['example_share']})).http === 200, 'freelancer: the private pack on in the own office');
  const qg = await call(CF, 'POST', '/api/office/docs', {project_title: 'Mit Anteil'});
  await call(CF, 'PATCH', `/api/office/docs/${qg.id}`, {producing_on: 1});
  const jg = await call(CF, 'PUT', `/api/office/docs/${qg.id}/items`, {items: [{kind: 'service', service_id: SVF, qty: 5}]});
  check(jg.producing_mode === 'amount' && line(jg, 'producing')?.total > 0, 'freelancer: a quotation with share by amount ' + JSON.stringify([jg.producing_mode, line(jg, 'producing')]));
  check((await call(CF, 'PUT', '/api/office/settings', {industry_packs: ['film']})).http === 200, 'freelancer: the private pack off, film on in the own office');

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const open = async (nav, id) => { await nav(B + 'static/icon.svg'); await nav(B + `#office/offers/${id}`); };
  const ptotal = line(jg, 'producing').total;
  const money = ptotal.toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev, 'frida');
    await open(nav, qf.id);
    check(await ready(ev, `document.querySelectorAll('.ofdeditor .ofdits .ofdit').length >= 1`, 80), 'the quotation editor');
    check(await ev(`!document.querySelector('#ofd-producing_on') && !document.querySelector('.ofdeditor [data-k="producing"]')`),
      '#6839: with only the film pack the older quotation shows no producing switch (no share by amount any more)');
    await open(nav, qg.id);
    const autos = `[...document.querySelectorAll('.ofdautos .ofdauto')].map(x => x.textContent).join(' | ')`;
    check(await ready(ev, `!!document.querySelector('#ofd-producing_on') && document.querySelector('#ofd-producing_on').checked && !!document.querySelector('#ofd-prod_quotient')`, 80),
      '#6839: the saved quotation with share by amount: the switch on and the factor');
    check(await ready(ev, `/Producing/.test(${autos}) && ${autos}.includes(${JSON.stringify(money)})`, 60), '#6839: its Producing line by amount ' + money + ' -- ' + await ev(autos));
    check(await ev(`!!document.querySelector('.ofdeditor [data-k="producing"]')`), '#6839: the position marks stay');
    await shot('p2380-l-producing.png');
  });
  const sf = await call(CF, 'GET', `/api/office/docs/${qg.id}`);
  check(sf.producing_on === 1 && sf.producing_mode === 'amount' && line(sf, 'producing')?.total === ptotal, 'freelancer: unchanged on the server ' + JSON.stringify([sf.producing_on, sf.producing_mode]));
  check((await call(CA, 'GET', `/api/office/docs/${qg.id}`)).http >= 403, 'freelancer: the organisation admin does not see the quotation');
  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
