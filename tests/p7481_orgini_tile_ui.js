// #7481 UI test: under "All workspaces" in Files and Knowledge the organisation's letter tile (span.orgini of orgIniHtml) keeps
// its small square size; the row's name (span.spovn) takes the remaining width. Before, the name rule of the overview with
// "Recently edited" (.zlerows .spovr>span) hit the tile too and pulled it wide.
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1280 / 390 (real layout), invented names only. The tile in Files and Knowledge is as wide as
// in the overview of the office and the others (areas.js spo_html, no .zlerows) and as high as wide; in and out: open the
// organisation, back to the overview, the tile is still small.
// freelancer-matrix: Person ohne Organisation in der Datei geprüft (solo)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7481_orgini_tile_ui', check, shots: 'P7481_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,files,docs,reading,wiki';

// the tiles of the overview, the width of its name, and the tile of the office's overview (spo_html) put next to it
const M = `JSON.stringify((() => {
  const ts = [...document.querySelectorAll('#view .zleov .spovr .orgini')].map(t => { const r = t.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; });
  const nm = [...document.querySelectorAll('#view .zleov .spovr[data-spov^="org:"] .spovn')].map(n => Math.round(n.getBoundingClientRect().width));
  const x = document.createElement('div'); x.innerHTML = spo_html(sp => 'office/s/' + sp, [['org:1', 'Gegenfilm', orgIniHtml({name: 'Gegenfilm'})]]);
  document.querySelector('#view').appendChild(x); const r = x.querySelector('.orgini').getBoundingClientRect(); const ref = [Math.round(r.width), Math.round(r.height)]; x.remove();
  return {ts, nm, ref};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const g = await call(CA, 'POST', '/api/admin/orgs', {name: 'Gegenfilm', admin_id: me.id});
  const t = await call(CA, 'POST', '/api/admin/orgs', {name: 'Tonstudio', admin_id: me.id});
  check(g.id && t.id, 'setup: two organisations G and T ' + JSON.stringify([g.http, t.http]));
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'all'});
  await call(CA, 'POST', '/api/wiki/pages', {space: 'org:' + g.id, path: 'Team/Ablauf', body: 'x'});
  // a person without an organisation: her overview has no organisation row and no tile (P4)
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, ctx, nav, shot, until, idle}) => {
    const fresh = async u => { await nav(B + 'static/icon.svg'); await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev, u) === 200, `${u}: login`); };
    await fresh('alice');
    for (const W of [1280, 390]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 860}});
      for (const [mod, label] of [['wiki', 'Knowledge'], ['ablage', 'Files']]) {
        await nav(B + '#' + mod); await idle();
        check(await until(`document.querySelectorAll('#view .zleov .spovr .orgini').length === 2`, {timeout: 20000}), `${W} ${label}: the overview shows the tiles of G and T`);
        const a = JSON.parse(await ev(M));
        const tileOk = a.ts.every(([w, h]) => Math.abs(w - a.ref[0]) <= 1 && Math.abs(w - h) <= 1);
        check(a.ref[0] > 0 && a.ref[0] < 40 && tileOk, `#7481 ${W} ${label}: each tile is as small as in the office's overview and square ${JSON.stringify(a)}`);
        check(a.nm.length === 2 && a.nm.every(n => n > a.ref[0]), `#7481 ${W} ${label}: the name takes the row, not the tile ${JSON.stringify(a.nm)}`);
        if (W === 1280) await shot(`p7481-${mod}-ov.png`);
        // in and out: into the organisation, back to the overview, the tile still small
        await ev(`(document.querySelector('#view .zleov .spovr[data-spov="org:${g.id}"]').click(), 1)`);
        check(await until(`location.hash.includes('/s/org:${g.id}') || location.hash.includes('/s/org%3A${g.id}')`, {timeout: 8000}), `${W} ${label}: a tap opens the organisation`);
        await nav(B + '#' + mod); await idle();
        check(await until(`document.querySelectorAll('#view .zleov .spovr .orgini').length === 2`, {timeout: 15000}), `${W} ${label}: back on the overview`);
        const b = JSON.parse(await ev(M));
        check(b.ts.every(([w]) => Math.abs(w - b.ref[0]) <= 1), `#7481 ${W} ${label}: back again, the tile still small ${JSON.stringify(b)}`);
      }
    }
    // without an organisation: the overview works, no tile
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await fresh('frida');
    await nav(B + '#wiki'); await idle();
    check(await until(`!!document.querySelector('#view .zleov, #view .wkw, #view [data-wk]')`, {timeout: 15000}) && await ev(`!document.querySelector('#view .orgini')`), 'P4: frida: Knowledge opens, no organisation tile');
  });

  console.log(`p7481_orgini_tile_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
