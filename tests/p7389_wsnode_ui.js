// kalmido-suite: fresh
// #7389 UI test: a workspace's row in the panel under "All workspaces" is drawn by ONE place of the core (areas.js
// sbb_treeHtml, a node with wso) and looks the same in every area that has such rows - Knowledge, Files, Contacts, Tables and
// the office's overview. One test over all areas (not one per area):
// - the symbol: Private = the house, the organisation = its own symbol (wsIcon), the same markup in every area (before:
//   Knowledge the organisation's letter, Files a folder, Contacts and Tables a building)
// - the stripe: on the workspace's row (.sbbt), never on its button nor on the rows below it (before: Tables put it on the
//   button and on every table and folder); Private wears the colour the person chose for it (before: none in the panel)
// - the arrow: a workspace known to be empty has none (before: Tables and the office always had one)
// - the start: nothing open under "All" while no object of a workspace is open - the same in every area (before: Contacts and
//   Tables always open, Knowledge / Files only with the open object)
// - the guard: an area that gives a workspace node its own icon / ichtml / kids / open is refused (console.error + sbb_wsoBad)
//   and the core draws its symbol anyway
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route (ohne Organisation zeigt die Leiste keine Arbeitsbereichs-Zeilen: p2198_a_wiki_spaces_ui)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, sp) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK, ...(sp ? {'X-Kalmido-Office-Space': sp} : {})}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), http: r.status};
  }
};
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  const st0 = await call('GET', '/api/state');
  const feats = [...new Set([...(st0.settings?.features || '').split(',').filter(Boolean), 'wiki', 'files', 'docs', 'contacts', 'sheets', 'office', 'clients'])].join(',');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats, workspace: 'all'});
  const me = (await call('GET', '/api/state')).me;
  const ORG = (await call('POST', '/api/admin/orgs', {name: 'Studio', admin_id: me.id})).id;
  check(ORG > 0, 'setup: the organisation Studio');
  check((await call('PATCH', '/api/orgs/' + ORG, {color: '#e0b05c'})).http === 200, 'setup: the admins set the organisation colour');
  const WO = 'org:' + ORG;
  check((await call('POST', '/api/wiki/pages', {space: WO, path: 'Team handbook', body: 'Read me first.'})).id, 'setup: a page in Studio\'s knowledge');

  let w = await boot({hash: 'wiki', allWs: true}), d = w.document;
  // Private's own colour (a tone of the switch), so the panel's Private row has a stripe to show
  const tone = w.eval('LP_TONES[2][0]');
  await call('PATCH', '/api/settings', {ws_colors: JSON.stringify({private: tone})});
  w.close();

  const rows = () => [...d.querySelectorAll('#side .sbbt.sbbws')];
  const rowOf = name => rows().find(x => x.querySelector('.sbbtn .n')?.textContent === name);
  const icons = {};
  // [area, hash, LS, what has to be there before the rows are complete]
  const AREAS = [
    ['Knowledge', 'wiki', {}],
    ['Files', 'ablage', {}],
    ['Contacts', 'contacts', {}],
    ['Tables', 'sheets', {}],
    ['Office', 'office/offers', {'tasks.sbbOpen': '["of:a:offers"]', 'tasks.ofmAll': 'true'}],
  ];
  for (const [area, hash, ls] of AREAS) {
    w = await boot({hash, allWs: true, ls}); d = w.document;
    const ok1 = await until(() => rowOf('Studio') && rowOf('Private'));
    check(ok1, `${area}: the panel has a row for Private and for Studio under "All" (` + rows().map(x => x.textContent).join('|') + ')');
    if (!ok1) { w.close(); continue; }
    const st = rowOf('Studio'), pr = rowOf('Private');
    const norm = x => { const t = d.createElement('div'); t.innerHTML = x; return t.innerHTML; };  // as the browser serialises it (svg paths)
    const iO = norm(w.eval(`wsIcon('${WO}')`)), iP = norm(w.eval(`wsIcon('private')`));
    const first = x => x.querySelector('.sbbtn').innerHTML.split('<span class="n">')[0];
    check(first(st) === iO, `${area}: Studio's row has the organisation's symbol ` + first(st));
    check(first(pr) === iP, `${area}: Private's row has the house ` + first(pr));
    icons[area] = first(st);
    // the stripe: on the row, the organisation's colour; Private its chosen colour; never a button, never a row below
    const wsd = w.eval(`(() => { const t = WSC_TONES[wsc_ix(wsOrg(${ORG}).color, ${ORG})]; return t[0]; })()`);
    check(st.dataset.wso === '1' && st.style.getPropertyValue('--wsd') === wsd, `${area}: Studio's row wears its stripe`);
    check(pr.dataset.wso === '1' && !!pr.style.getPropertyValue('--wsd'), `${area}: Private's row wears the colour I chose`);
    check(!d.querySelector('#side .sbbtn[data-wso]'), `${area}: no button wears a stripe`);
    check(![...d.querySelectorAll('#side .sbbt[data-wso]')].some(x => !x.classList.contains('sbbws')), `${area}: no row below a workspace wears a stripe`);
    // the start: no workspace open under "All" while nothing of it is open
    check(rows().every(x => !x.querySelector('[data-act="sbb-tree"][data-open="1"]')), `${area}: under "All" no workspace starts open`);
    // known empty = no arrow (Tables / Contacts know their content at once; Studio has neither tables nor contact folders)
    if (area === 'Tables' || area === 'Contacts') check(!st.querySelector('.sbbtar'), `${area}: the empty Studio has no arrow`);
    // Knowledge: Studio has a page -> its arrow opens it, the person's choice is kept (LS sbbOpen)
    if (area === 'Knowledge') {
      check(await until(() => rowOf('Studio')?.querySelector('[data-act="sbb-tree"]')), 'Knowledge: Studio with a page has its arrow');
      rowOf('Studio').querySelector('[data-act="sbb-tree"]').click();
      check(await until(() => rowOf('Studio')?.querySelector('[data-act="sbb-tree"][data-open="1"]') && [...d.querySelectorAll('#side .sbbt')].some(x => /Team handbook/.test(x.textContent))), 'Knowledge: the arrow opens Studio to its page');
      check(JSON.parse(w.localStorage.getItem('tasks.sbbOpen') || '[]').includes(`wk:${WO}:`), 'Knowledge: opened by hand is kept (sbbOpen)');
    }
    check(w.eval('sbb_wsoBad.length') === 0, `${area}: the area gives its workspace nodes nothing of their own (guard) ` + w.eval('sbb_wsoBad.join()'));
    w.close();
  }
  const seen = Object.values(icons);
  check(seen.length === AREAS.length && new Set(seen).size === 1, 'every area: the same symbol for Studio ' + JSON.stringify(icons));

  // the guard: a workspace node with its own icon is refused, the core's symbol wins
  w = await boot({hash: 'wiki', allWs: true}); d = w.document;
  await until(() => w.eval('typeof sbb_treeHtml === "function"'));
  const err0 = w.console.error; w.console.error = () => {};
  const h = w.eval(`sbb_treeHtml([{k: 'x:1', name: 'X', go: 'wiki', wso: 'private', icon: 'folder', kids: true, open: true, sub: () => []}])`);
  w.console.error = err0;
  check(w.eval('sbb_wsoBad.some(x => /^x:1: icon,kids,open$/.test(x))'), 'the guard: icon / kids / open on a workspace node are refused ' + w.eval('sbb_wsoBad.join()'));
  check(h.includes(w.eval(`wsIcon('private')`)) && !h.includes(w.eval(`ic('folder')`)), 'the guard: the core draws the house anyway');
  w.close();

  console.log(`p7389_wsnode_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log("FAIL: crashed", e); process.exit(1); });
