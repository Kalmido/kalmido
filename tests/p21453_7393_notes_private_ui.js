// kalmido-suite: fresh
// Package 2.1453.0 (#7393) UI test: Notes under "All workspaces" - a private note wears my own Private colour
// (ws_colors.private) as the stripe of its card and as the tone of the open note, a project's note keeps its organisation's
// colour; without a chosen Private colour Private stays neutral; inside one workspace nothing changes (nothing is mixed there).
// The colour comes from the core (wscolor.js wso_row with priv, wso_open / wso_sync, docs/dev/kern.md "Organisation colour").
// freelancer-matrix: n/a - nur Oberfläche (ohne Organisation ist wsOn() false: wso_row und wso_locVars geben nichts, wie vorher)
// jsdom only.
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
const until = fn => require('./boot').until(fn, {timeout: 15000, step: 150});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio', lang: 'en', collab_all: true, modules: ['cal', 'comments', 'collab']});
  check(su.http < 300, 'setup: the organisation Studio ' + JSON.stringify(su));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', ws_colors: JSON.stringify({private: 'red'}), workspace: 'all'});
  const ORG = ((await call('GET', '/api/state')).me.workspaces || [])[0]?.id;
  if (!ORG) { console.log('no organisation'); process.exit(1); }
  check((await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'})).http === 200, 'setup: the organisation colour');
  const QL = (await call('POST', '/api/notes/quick-list')).list_id;
  const LO = (await call('POST', '/api/lists', {name: 'Studio film', org_id: ORG})).id;
  const NP = (await call('POST', `/api/lists/${QL}/notes`, {title: 'Grocery idea', body: 'Mine alone'})).id;
  const NO = (await call('POST', `/api/lists/${LO}/notes`, {title: 'Shot list', body: 'For the crew'})).id;
  check(QL && LO && NP && NO, 'setup: a private note and a note of an organisation\'s project');

  // ================= "All workspaces", Private colour chosen (red)
  let w = await boot({hash: 'notes'}), d = w.document;
  const red = w.eval(`(() => { const t = LP_TONES.find(x => x[0] === 'red'); return {d: t[2], wad: wac_fit(t[2], false)}; })()`);
  const org = w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return {d: t[0], wad: wac_fit(t[0], false)}; })()`);
  const card = t => [...d.querySelectorAll('a.sbncard')].find(a => a.textContent.includes(t));
  const stripe = el => el && el.dataset.wso === '1' ? el.style.getPropertyValue('--wsd') : '';
  const view = () => d.querySelector('#view');
  const tone = () => view()?.classList.contains('wac-loc') ? view().style.getPropertyValue('--wad') : '';
  check(await until(() => card('Grocery idea') && card('Shot list')), 'All: both notes are listed by title');
  check(stripe(card('Grocery idea')) === red.d, '#7393 All: the private note\'s card wears my Private colour ' + stripe(card('Grocery idea')));
  check(stripe(card('Shot list')) === org.d, '#7393 All: the project note\'s card keeps the organisation\'s colour');
  // open the private note as a person does: a tap on its card
  card('Grocery idea').click();
  check(await until(() => w.eval('S.nt.id') === NP), 'All: a tap opens the private note');
  check(await until(() => tone() === red.wad), '#7393 All: the open private note wears the Private tone ' + tone());
  check(!d.querySelector('#main').classList.contains('wsc-on'), 'All: the open private note has no organisation frame');
  w.eval(`go('note/${NO}')`);
  check(await until(() => w.eval('S.nt.id') === NO && tone() === org.wad), '#7393 All: the open project note wears the organisation\'s tone');
  w.eval(`history.back()`);
  check(await until(() => w.eval('S.nt.id') === NP), 'All: back returns to the private note');
  w.close();

  // ================= "All", no Private colour: Private stays neutral
  await call('PATCH', '/api/settings', {ws_colors: '{}'});
  w = await boot({hash: 'notes'}); d = w.document;
  check(await until(() => card('Grocery idea')), 'All, no colour: the private note is listed');
  check(stripe(card('Grocery idea')) === '' && !card('Grocery idea').style.getPropertyValue('--wsd'), '#7393 All, no colour: the private card stays neutral');
  check(stripe(card('Shot list')) === org.d, '#7393 All, no colour: the project note keeps its organisation\'s colour');
  card('Grocery idea').click();
  check(await until(() => w.eval('S.nt.id') === NP), 'All, no colour: the private note opens');
  await sleep(300);
  check(tone() === '', '#7393 All, no colour: the open private note stays neutral');
  w.close();

  // ================= inside the workspace Private (colour chosen): nothing mixed, no stripe on the cards
  await call('PATCH', '/api/settings', {ws_colors: JSON.stringify({private: 'red'}), workspace: 'private'});
  w = await boot({hash: 'notes'}); d = w.document;
  check(await until(() => card('Grocery idea')), 'Private: the private note is listed');
  check(stripe(card('Grocery idea')) === '', '#7393 Private: the card has no stripe (as before)');
  check(!card('Shot list'), 'Private: the organisation\'s note is not shown');
  w.close();
  await call('PATCH', '/api/settings', {workspace: 'all'});

  console.log(`p21453_7393_notes_private_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
