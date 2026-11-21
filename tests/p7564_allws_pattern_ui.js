// kalmido-suite: fresh
// #7564 UI test (Firefox, real layout at 412 px with touch and 1280 px with a mouse): ONE pattern under "All workspaces" for every
// area whose content is separated per workspace (owner decision 20.11.2026). A person with Private + one organisation (Alpha):
// - Knowledge, Files, Reading, the office and Tables: the same building blocks in the same order - the muted line on top that
//   says what the choice means (areas.js spo_hintHtml), the row "Recently edited" first, then Private, Alpha (+ Shared with me
//   in Files); the row "Recently edited" opens #<area>/recent with the way back
// - the sidebar (the panel on a computer, the drawer on a phone) of Knowledge, Files, the office and Tables shows the two
//   workspaces with the fold arrow
// - as a person: a tap on Alpha's row opens the area in Alpha (the address carries it), Back returns to the overview; in Tables
//   also the path "All workspaces /" above the open space
// - Notes stay one mixed list: every card names its project and where it belongs (the workspace mark under "All")
// - Frida without an organisation: no overview in Tables and the office (one workspace only)
// freelancer-matrix: n/a - nur Oberfläche (Person ohne Organisation in der Datei geprüft)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return c; };
const firefox = require('./ff')({tag: 'p7564_allws_pattern_ui', check, shots: 'P7564_SHOTS', allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7564_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const upload = async (ck, name, space) => {
  const fd = new FormData(); fd.append('file', new Blob(['text of ' + name]), name); fd.append('space', space);
  const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: ck}, body: fd});
  return (await r.json()).items?.[0]?.id;
};
const FEAT = 'cal,comments,collab,files,docs,reading,wiki,sheets,office,clients';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']}, CA);
  const me = (await call('GET', '/api/state', null, CA)).me;
  const A = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id}, CA)).id;
  const WA = 'org:' + A;
  check(A > 0, 'setup: the organisation Alpha');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'all'}, CA);
  // something in every space of every area (the sidebar's arrow shows a workspace with content)
  for (const sp of ['private', WA]) {
    check((await call('POST', '/api/wiki/pages', {space: sp, path: 'Guide ' + sp, body: 'Text'}, CA)).id > 0, 'setup: a page in ' + sp);
    check(await upload(CA, 'file-' + sp.replace(':', '') + '.txt', sp) > 0, 'setup: a file in ' + sp);
    check((await call('POST', '/api/reading', {url: 'https://example.com/' + sp.replace(':', ''), title: 'Article ' + sp, space: sp}, CA)).status < 300, 'setup: read later in ' + sp);
  }
  const SP = (await call('POST', '/api/sheets', {title: 'Household table', space: 'private'}, CA)).id;
  const SO = (await call('POST', '/api/sheets', {title: 'Studio table', space: WA}, CA)).id;
  check(SP > 0 && SO > 0, 'setup: a table in Private and in Alpha');
  check((await call('POST', '/api/clients', {name: 'Studio client', org_id: A}, CA)).id > 0, 'setup: a client in Alpha (an item of the office, #7664)');
  const QL = (await call('POST', '/api/notes/quick-list', null, CA)).list_id;
  const LO = (await call('POST', '/api/lists', {name: 'Alpha film', org_id: A}, CA)).id;
  const NP = (await call('POST', `/api/lists/${QL}/notes`, {title: 'Grocery idea', body: 'Mine alone'}, CA)).id;
  const NO = (await call('POST', `/api/lists/${LO}/notes`, {title: 'Shot list', body: 'For the crew'}, CA)).id;
  check(NP && NO, 'setup: a private note and a note of an Alpha project');
  const fu = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []}, CA);
  check(fu.status < 300, 'setup: Frida without an organisation');
  const CF = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, CF);
  check((await call('POST', '/api/sheets', {title: 'Frida table', space: 'private'}, CF)).id > 0, 'setup: Frida\'s table');

  // [area, address, the hint, where Alpha's row leads, "opened in Alpha" (an expression), sidebar check]
  const AREAS = [
    ['Knowledge', 'wiki', /^Whose pages\?/, `wiki/s/${WA}`, `typeof wk_cur === 'function' && wk_cur() === '${WA}'`, true],
    ['Files', 'ablage', /^Whose files\?/, `ablage/s/${WA}`, `typeof ab_curSpace === 'function' && ab_curSpace() === '${WA}' && !ab_ovr()`, true],
    ['Reading', 'reading', /^Whose list\?/, `reading/s/${WA}`, `typeof rd_open === 'function' && rd_open() === '${WA}'`, false],
    ['Office', 'office', /^Whose office\?/, `office/s/${WA}`, `typeof OFC !== 'undefined' && !!OFC.info && OFC.info.org_id === ${A}`, true],
    ['Tables', 'sheets', /^Whose tables\?/, `sheets/s/${WA}`, `!!document.querySelector('.shvcard[data-id="${SO}"]') && !document.querySelector('.shvcard[data-id="${SP}"]')`, true],
  ];
  const OV = `JSON.stringify([...document.querySelectorAll('#view .zleov .spovl .spovr')].map(a => a.dataset.spov || (a.dataset.zlego ? 'recent' : '?')))`;
  // the workspace nodes of the panel (the core's sbb_treeHtml wso), each name once (an office's menu below may repeat its own)
  const SIDE = `JSON.stringify([...document.querySelectorAll('#side .sbbt.sbbws')].map(r => [(r.querySelector('.sbbtn .n')?.textContent || '').trim(), !!r.querySelector(':scope > .sbbtar')]).filter((x, i, a) => a.findIndex(y => y[0] === x[0]) === i))`;

  const run = (width, touch) => firefox(async o => {
    const {cmd, ev, ctx, nav} = o, tag = `${width}: `;
    const ready = async (expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
    const val = async expr => { try { return JSON.parse(await ev(expr)); } catch { return null; } };
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width, height: 860}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, tag + 'login');
    for (const [name, mod, hint, open, opened, side] of AREAS) {
      const t = tag + name + ': ';
      await nav(B + '#' + mod);
      const want = JSON.stringify(['recent', 'private', WA, ...(mod === 'ablage' ? ['shared'] : [])]);
      check(await ready(`${OV} === ${JSON.stringify(want)}`), t + 'the overview: "Recently edited", Private, Alpha' + (mod === 'ablage' ? ', Shared with me' : '') + ' ' + await ev(OV).catch(() => ''));
      const h = await ev(`(() => { const p = document.querySelector('#view .zleov > .spovh'); return p ? p.textContent.trim() + '|' + (p.nextElementSibling?.classList.contains('spov') ? 'first' : '') : ''; })()`);
      check(hint.test(h) && /\|first$/.test(h), t + 'the line that says what the choice means, right above the rows ' + h);
      check(await ev(`(() => { const a = document.querySelector('#view .zleov [data-zlego]'); return !!a && a.getAttribute('href') === '#${mod}/recent' && /Recently edited/.test(a.textContent); })()`), t + 'the row "Recently edited" leads to its page');
      check(await ev(`document.querySelector('#view .zleov [data-spov="${WA}"]')?.getAttribute('href') === '#${open}'`), t + 'Alpha\'s row leads to #' + open);
      check(await ev(`document.documentElement.scrollWidth <= innerWidth + 1`), t + 'nothing wider than the window');
      if (o.shot) await o.shot(`7564-${mod}-${width}.png`);
      // the sidebar: the two workspaces with the arrow
      if (side) {
        if (width < 600) { await ev(`(document.querySelector('#top [data-act="side"]')?.click(), 1)`); await ready(`!!document.querySelector('#side.open')`, 20); }
        const okSide = await ready(`(x => x.length === 2 && x[0][0] === 'Private' && x[1][0] === 'Alpha' && x.every(r => r[1]))(${SIDE.replace(/^JSON\.stringify\((.*)\)$/s, '$1')})`, 80);
        check(okSide, t + 'the sidebar shows Private and Alpha, each with the arrow ' + await ev(SIDE).catch(() => ''));
        if (width < 600 && o.shot) await o.shot(`7564-${mod}-${width}-drawer.png`);
        if (width < 600) { await nav(B + '#' + mod); await ready(`${OV} === ${JSON.stringify(want)}`); }
      }
      // as a person: Alpha's row opens the area in Alpha, Back returns to the overview
      await ev(`(document.querySelector('#view .zleov [data-spov="${WA}"]').click(), 1)`);
      check(await ready(`location.hash === '#${open}' || location.hash.startsWith('#${open}/')`, 40), t + 'a tap on Alpha opens its address ' + await ev('location.hash'));
      check(await ready(`(${opened}) && !document.querySelector('#view .zleov')`), t + 'the area is open in Alpha, no overview');
      if (mod === 'sheets') {
        check(await ev(`!!document.querySelector('#view .spovc [data-spovup]') && /Alpha/.test(document.querySelector('#view .spovc .abccur')?.textContent || '')`), t + 'the path "All workspaces / Alpha" above the open space');
        check(await ev(`!document.querySelector('#view .shvgrp h3')`), t + 'no group heading (the old "PRIVATE") in the open space');
        await ev(`(document.querySelector('#view [data-spovup]').click(), 1)`);
        check(await ready(`location.hash === '#sheets' && ${OV} === ${JSON.stringify(want)}`), t + '"All workspaces" in the path leads back to the overview');
        await ev(`(document.querySelector('#view .zleov [data-spov="${WA}"]').click(), 1)`);
        await ready(opened);
      }
      await ev(`(history.back(), 1)`);
      check(await ready(`${OV} === ${JSON.stringify(want)}`), t + 'Back returns to the overview ' + await ev('location.hash'));
      // the page "Recently edited" and its way back
      await ev(`(document.querySelector('#view .zleov [data-zlego]').click(), 1)`);
      check(await ready(`location.hash === '#${mod}/recent' && !!document.querySelector('#view .zlepage') && document.querySelector('#view .zlehead [data-navup]')?.getAttribute('href') === '#${mod}'`), t + 'the page "Recently edited" opens with the way back');
      if (mod === 'office' || mod === 'sheets') check(await ready(`document.querySelectorAll('#view .zlepage .zler').length > 0`), t + 'its page lists the recent items');
      // (#7664): the page lists only the area's own kind (no page, file or read-later entry of the others)
      const own = {wiki: '#wiki/', ablage: '#ablage/', reading: '#reading', office: '#(client|office|docs)/', sheets: '#sheets/'}[mod];
      check(await ev(`[...document.querySelectorAll('#view .zlepage .zler')].every(a => new RegExp('^${own}').test(a.getAttribute('href')))`), t + '#7664: only its own kind ' + await ev(`[...document.querySelectorAll('#view .zlepage .zler')].map(a => a.getAttribute('href')).join()`));
    }
    // Notes: one mixed list, every card names its project and where it belongs
    await nav(B + '#notes');
    const NC = `JSON.stringify([...document.querySelectorAll('a.sbncard')].map(a => [(a.querySelector('.ntt')?.textContent || '').trim(), (a.querySelector('.sbnl')?.textContent || '').trim(), a.querySelector('.wso')?.getAttribute('title') || '']))`;
    check(await ready(`(x => x.length >= 2)(${NC.replace(/^JSON\.stringify\((.*)\)$/s, '$1')})`), tag + 'Notes: both notes listed ' + await ev(NC).catch(() => ''));
    const cards = await val(NC) || [];
    const shot = cards.find(c => c[0] === 'Shot list'), groc = cards.find(c => c[0] === 'Grocery idea');
    check(shot && shot[1] === 'Alpha film' && shot[2] === 'Alpha', tag + 'Notes: the card of the Alpha project names the project and Alpha ' + JSON.stringify(shot));
    check(groc && groc[1] && groc[2] === 'Private', tag + 'Notes: the private note names its list and Private ' + JSON.stringify(groc));
    check(!cards.some(c => /always private/i.test(c.join(' '))), tag + 'Notes: no "(always private)" addition');
    check(await ev(`!document.querySelector('#view .zleov, #view .spov')`), tag + 'Notes: no overview of the workspaces (a mixed list)');
    if (o.shot) await o.shot(`7564-notes-${width}.png`);
    // Frida: one workspace, no overview
    await ev(`fetch('/api/auth/logout', {method: 'POST', headers: {'X-Requested-With': 'kalmido'}}).then(r => r.status)`).catch(() => 0);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`) === 200, tag + 'Frida signs in');
    await nav(B + 'static/icon.svg');  // a new page load: the app starts as Frida (a hash change alone keeps Alice's state)
    await nav(B + '#sheets');
    check(await ready(`/Frida table/.test(document.querySelector('#view')?.textContent || '')`), tag + 'Frida: Tables lists her table directly');
    check(await ev(`!document.querySelector('#view .spov, #view .spovh')`), tag + 'Frida: no overview, no line about workspaces in Tables');
    await nav(B + '#office');
    await ready(`typeof OFC !== 'undefined' && (!!OFC.info || !!OFC.infoErr)`);
    check(await ev(`!document.querySelector('#view .spov, #view .spovh')`), tag + 'Frida: no overview in the office');
  }, touch);

  if (await run(412, true) === true) console.log('p7564_allws_pattern_ui: firefox part skipped');
  else await run(1280, false);

  console.log(`p7564_allws_pattern_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
