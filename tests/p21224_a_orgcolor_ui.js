// kalmido-suite: fresh
// Package 2.1224.0 (#6186, #6187, #6188) UI test: the organisation colour (core block wscolor.js wso_row / wso_origin / wso_open,
// docs/dev/kern.md "Organisation colour") in tables, time tracking, the command palette and search hits, the trash, news, the
// project group heads and the favourite agents. Rule (owner decision 14.11.2026): what belongs to an organisation wears its
// colour in every area, the entry and the open object; Private stays neutral. Used as a person sees it: the card / row / hit
// with the organisation's name next to it, the open table marks the page, a private one stays neutral.
// freelancer-matrix: n/a - nur Oberfläche (Person ohne Organisation in der Datei geprüft)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return c; };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, o) => require('./boot').until(fn, {timeout: 15000, step: 150, ...(o || {})});
const FEAT = 'comments,collab,sheets,time';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio', lang: 'en', collab_all: true, modules: ['comments']});
  check(su.http < 300, 'setup: the organisation Studio ' + JSON.stringify(su));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', ws_colors: '{}', workspace: 'all', features: FEAT});
  const st = await call('GET', '/api/state'), ORG = (st.me.workspaces || [])[0]?.id;
  if (!ORG) { console.log('no organisation', JSON.stringify(st.me)); process.exit(1); }
  check((await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'})).http === 200, 'setup: the admins set the organisation colour');
  const WL = (await call('POST', '/api/lists', {name: 'Website', org_id: ORG})).id;
  const PL = (await call('POST', '/api/lists', {name: 'Garden', org_id: null})).id;
  const GL = (await call('POST', '/api/lists', {name: 'Old campaign', org_id: ORG})).id;
  check(WL && PL && GL, 'setup: two projects of the organisation and a private one');
  const WT = (await call('POST', '/api/tasks', {list_id: WL, title: 'Homepage copy'})).id;
  const PT = (await call('POST', '/api/tasks', {list_id: PL, title: 'Water plants'})).id;
  await call('PATCH', `/api/tasks/${WT}`, {pinned: 1}); await call('PATCH', `/api/tasks/${PT}`, {pinned: 1});
  const SO = (await call('POST', '/api/sheets', {title: 'Studio budget', space: 'org:' + ORG})).id;
  const SP = (await call('POST', '/api/sheets', {title: 'Household', space: 'private'})).id;
  check(SO && SP, 'setup: a table of the organisation and a private one');
  const t0 = new Date(Date.now() - 3 * 36e5).toISOString();
  const E1 = await call('POST', '/api/time/entries', {task_id: WT, start: t0, minutes: 45, note: 'studio work'});
  const E2 = await call('POST', '/api/time/entries', {task_id: PT, start: t0, minutes: 20, note: 'garden work'});
  check(E1.http < 300 && E2.http < 300, 'setup: a time entry in each project ' + E1.http + ' ' + E2.http);
  await call('PATCH', `/api/lists/${GL}`, {archived: 1});
  check((await call('DELETE', '/api/lists/' + GL)).trash === true, 'setup: a project of the organisation goes to the trash');

  const want = w => w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return {d: t[0], l: t[1]}; })()`);
  const striped = (el, t) => !!el && el.dataset.wso === '1' && el.style.getPropertyValue('--wsd') === t.d;

  // ================= #6186 tables, "All workspaces"
  let w = await boot({hash: 'sheets'}), d = w.document;
  const T = want(w);
  const co = await until(() => d.querySelector(`.shvcard[data-id="${SO}"]`), {timeout: 20000});
  check(co && /Studio budget/.test(co.textContent), '#6186 the overview shows the organisation\'s table');
  check(striped(co, T), '#6186 the organisation\'s table card wears its stripe in its colour');
  const cp = d.querySelector(`.shvcard[data-id="${SP}"]`);
  check(cp && /Household/.test(cp.textContent) && !cp.dataset.wso, '#6186 the private table card stays neutral');
  const hs = [...d.querySelectorAll('.shvgrp h3')];
  check(hs.some(h => /Studio/.test(h.textContent) && h.querySelector('.wsp-dot[data-wsc]')), '#6186 the organisation\'s group heading carries its dot');
  check(hs.some(h => /Private/.test(h.textContent) && !h.querySelector('.wsp-dot')), '#6186 the private group heading has no dot');
  // open the table: the page is marked (the frames, "All": its tone); back and into the private one: neutral
  w.eval(`go('sheets/${SO}')`);
  check(await until(() => d.querySelector('.shvsheet') && d.querySelector('#main').classList.contains('wsc-on') && d.querySelector('#main').style.getPropertyValue('--wsd') === T.d, {timeout: 20000}), '#6186 the open table of the organisation: #main.wsc-on in its colour');
  check(/Studio budget/.test(d.querySelector('.shvtitle')?.textContent || ''), '#6186 the open table shows its title');
  check(d.querySelector('#view').classList.contains('wac-loc'), '#6186 "All": the open table wears the organisation\'s tone');
  w.eval(`go('sheets/${SP}')`);
  check(await until(() => /Household/.test(d.querySelector('.shvtitle')?.textContent || '') && !d.querySelector('#main').classList.contains('wsc-on'), {timeout: 20000}), '#6186 the open private table: no organisation mark');
  w.eval(`go('sheets')`);
  check(await until(() => d.querySelector('.shvov') && !d.querySelector('#main').classList.contains('wsc-on')), '#6186 back in the overview: no open object, no mark');
  check(w.eval(`shf_panelTree(SHV.idx.all.items, shvSpaces(), null).find(n => n.id === 'r:org:${ORG}').battrs`).includes('data-wso="1"') && !w.eval(`shf_panelTree(SHV.idx.all.items, shvSpaces(), null).find(n => n.id === 'r:private').battrs`).includes('data-wso'), '#6186 the panel: the organisation\'s workspace entry wears its stripe, Private not');

  // ================= #6187 time tracking (the page is always mixed); the list of entries opened as a person does
  const openEntries = async () => { const t = await until(() => d.querySelector('[data-act="tv-entries"]'), {timeout: 20000}); if (t && t.querySelector('.closedc')) t.click(); };
  w.eval(`go('time')`);
  await openEntries();
  const r1 = await until(() => [...d.querySelectorAll('.terow')].find(r => /studio work/.test(r.textContent)), {timeout: 20000});
  check(r1 && r1.querySelector('.teorg .wsp-dot[data-wsc]') && /Studio/.test(r1.querySelector('.teorg').textContent), '#6187 the organisation\'s time entry shows its dot + name');
  const r2 = [...d.querySelectorAll('.terow')].find(r => /garden work/.test(r.textContent));
  check(r2 && !r2.querySelector('.teorg'), '#6187 the private entry stays neutral');
  const rl = [...d.querySelectorAll('tr.tvl')].find(r => /Website/.test(r.textContent));
  check(rl && rl.querySelector('.teorg') && /Studio/.test(rl.querySelector('.teorg').textContent), '#6187 the report line of the organisation\'s project shows its organisation');
  check(![...d.querySelectorAll('tr.tvl')].find(r => /Garden/.test(r.textContent))?.querySelector('.teorg'), '#6187 the private report line stays neutral');

  // ================= #6188 palette / search, news, group heads
  w.eval(`openPalette()`);
  const inp = await until(() => d.querySelector('.palette input'));
  inp.value = 'Website'; inp.dispatchEvent(new w.Event('input', {bubbles: true}));
  const pi = await until(() => [...d.querySelectorAll('.pitem')].find(x => /Website/.test(x.querySelector('.plt')?.textContent || '') && x.querySelector('.porg')));
  check(pi && /Studio/.test(pi.querySelector('.porg').textContent), '#6188 the palette: the organisation\'s project hit shows its dot + name');
  inp.value = 'Garden'; inp.dispatchEvent(new w.Event('input', {bubbles: true}));
  const pg = await until(() => [...d.querySelectorAll('.pitem')].find(x => /Garden/.test(x.querySelector('.plt')?.textContent || '')));
  check(pg && !pg.querySelector('.porg'), '#6188 the palette: a private hit stays neutral');
  check(/Studio/.test(w.eval(`pal_org({id: 'fts:1', kind: 'tasks', lid: ${WL}})`)) && /Studio/.test(w.eval(`pal_org({kind: 'view', ws: 'org:${ORG}'})`)) && w.eval(`pal_org({kind: 'view', ws: 'private'})`) === '', '#6188 search hits (tasks, wiki pages) carry their organisation, private ones not');
  w.eval(`closePalette(true)`);
  check(/Studio/.test(w.eval(`newsWsLabel({list_id: ${WL}})`)) && w.eval(`newsWsLabel({list_id: ${PL}})`) === '', '#6188 news / bell under "All": the organisation\'s item names its organisation, a private one not');
  w.eval(`go('all')`);  // "All tasks": grouped by project (Pinned is one group now)
  const gh = await until(() => [...d.querySelectorAll('.ghead')].find(g => /Website/.test(g.textContent)), {timeout: 20000});
  if (!check(gh && gh.querySelector('.gorg .wsp-dot[data-wsc]') && /Studio/.test(gh.querySelector('.gorg').textContent), '#6188 a group head by project shows its organisation')) console.log('heads:', [...d.querySelectorAll('#view .ghead')].map(g => g.outerHTML.slice(0, 400)).join('\n'), w.eval('S.route.key'));
  check(![...d.querySelectorAll('.ghead')].find(g => /Garden/.test(g.textContent))?.querySelector('.gorg'), '#6188 a private project\'s group head stays neutral');
  check(/gorg/.test(w.eval(`mtListHead(${WL})`)) && !/gorg/.test(w.eval(`mtListHead(${PL})`)), '#6188 "Hidden" in My tasks: the project head carries its organisation');
  // the trash: the organisation's project row wears its stripe
  w.eval(`go('trash')`);
  const tr = await until(() => d.querySelector(`.otrrow[data-otr="${GL}"]`), {timeout: 20000});
  check(tr && /Old campaign/.test(tr.textContent) && striped(tr, T), '#6188 the trash: the organisation\'s deleted project wears its stripe');
  w.close();

  // ================= inside the organisation's workspace: no repeated origin; another workspace's item keeps it
  await call('PATCH', '/api/settings', {workspace: 'org:' + ORG});
  w = await boot({hash: 'time'}); d = w.document;
  await openEntries();
  const r3 = await until(() => [...d.querySelectorAll('.terow')].find(r => /studio work/.test(r.textContent)), {timeout: 20000});
  check(r3 && !r3.querySelector('.teorg'), '#6187 inside the organisation\'s workspace its own entries need no mark');
  check(w.eval(`newsWsLabel({list_id: ${PL}})`).includes('nws') && !w.eval(`newsWsLabel({list_id: ${PL}})`).includes('wsp-dot'), '#6188 inside the organisation: a private news item keeps its plain label (Private stays neutral)');
  w.eval(`go('sheets/${SO}')`);
  check(await until(() => d.querySelector('.shvsheet') && d.querySelector('#main').classList.contains('wsc-on'), {timeout: 20000}), '#6186 inside the organisation: the open table still marked');
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all'});

  // ================= a person without an organisation: nothing coloured
  await call('POST', '/api/users', {username: 'solo', display_name: 'Solo', password: 'password123', email: 'solo@example.com', orgs: []});
  const CS = await login('solo');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, CS);
  const SL = (await call('POST', '/api/lists', {name: 'Own project'}, CS)).id;
  const ST = (await call('POST', '/api/tasks', {list_id: SL, title: 'Own task'}, CS)).id;
  await call('POST', '/api/time/entries', {task_id: ST, start: t0, minutes: 15, note: 'own work'}, CS);
  const SS = (await call('POST', '/api/sheets', {title: 'Own table', space: 'private'}, CS)).id;
  w = await boot({user: 'solo', hash: 'sheets'}); d = w.document;
  const sc = await until(() => d.querySelector(`.shvcard[data-id="${SS}"]`), {timeout: 20000});
  check(sc && /Own table/.test(sc.textContent) && !sc.dataset.wso, '#6186 without an organisation: the table card is shown, neutral');
  w.eval(`go('time')`);
  await openEntries();
  const sr = await until(() => [...d.querySelectorAll('.terow')].find(r => /own work/.test(r.textContent)), {timeout: 20000});
  check(sr && !sr.querySelector('.teorg'), '#6187 without an organisation: the time entry is shown, neutral');
  check(w.eval(`pal_org({kind: 'list', lic: listById(${SL})}) + newsWsLabel({list_id: ${SL}})`) === '', '#6188 without an organisation: no marks in palette and news');
  w.close();

  console.log(`p21224_a_orgcolor_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
