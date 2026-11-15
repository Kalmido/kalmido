// Package 2.1198.0 A (#6090) UI tests: what Kalmido writes itself on a knowledge page reads like text, not like Markdown.
// kalmido-suite: fresh
// Own container (start.sh), Firefox with a mouse; invented pages only. Screenshots: P21198A_SHOTS.
// - the front matter as fields: keys as words (Tags, As of), a date as the app writes dates; in the editor one folded line of
//   these fields, the cursor in it shows the lines to edit; the event of minutes (termin) as a link "Open event"
// - a link [[Folder/Page]] shows the page's name (the path as its tooltip), in the read view and in the editor; a task link in
//   the editor shows its title after the number
// - "Linked from", search hits and a tag's pages: the page's name, its folders quietly beside it
// - a daily note is titled with its date, its folder "journal" reads "Daily notes", "Templates" stays "Templates" (paths stay)
// - a page from a template drops its empty points and its own front matter (its tags stay); a snippet does not repeat the title
// - the editor's hint has no [[…]] syntax
// freelancer-matrix: Wissen (alice has no organisation, all of it runs as a person on her own)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return !!c; };
const firefox = require('./ff')({tag: 'p21198_a_wiki_text_ui', check, shots: 'P21198A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21198A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call('GET', '/api/state');
  const feats = [...new Set([...(st0.settings.features || '').split(',').filter(Boolean), 'wiki'])].join(',');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats, workspace: 'private'});
  check(!(st0.me.workspaces || []).length, 'setup: alice has no organisation (a person on her own)');
  const T = (await call('POST', '/api/tasks', {title: 'Book the hall'})).id;
  check(T, 'setup: a task');
  const CHECK = `---\ntags: [shoot]\nas_of: 2026-11-10\n---\n# Checklist\n\nPlan B: [[Processes/Shoot day/Weather plan B]]. Hall: [[#${T}]].\n\nThis list holds every shoot day.\n`;
  const P = {};
  for (const [k, p, b] of [['check', 'Processes/Shoot day/Checklist', CHECK], ['plan', 'Processes/Shoot day/Weather plan B', 'Rain: the hall. #shoot'],
    ['day', 'journal/2026-11-14', 'Shot the first scene.'], ['min', 'Minutes/Review', '---\ntermin: 4711\n---\nWho came.'],
    ['tpl', 'Templates/Minutes', '---\ntype: minutes\ntags: [minutes]\n---\n# {{title}}\n\n- \n- [ ] \n* [ ]\n1. \n\n- kept point\nNotes here']]) P[k] = (await call('POST', '/api/wiki/pages', {space: 'private', path: p, body: b})).id;
  check(Object.values(P).every(Boolean), 'setup: the pages ' + JSON.stringify(P));
  const login2 = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await login2(ev) === 200, 'ff: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    const want = `fmtDay('year', new Date('2026-11-10T00:00:00'))`;

    // ================= the editor (a computer opens a page ready to type)
    await nav(B + '?w=1280#wiki/' + P.check);
    const fm = await until(`(() => { const w = document.querySelector('#wk-cm .cm-wkfmw .wkattrs'); if (!w) return null; return {dt: [...w.querySelectorAll('dt')].map(x => x.textContent), dd: [...w.querySelectorAll('dd')].map(x => x.textContent),
      raw: [...document.querySelectorAll('#wk-cm .cm-line')].some(l => /^---$|^as_of:/.test(l.textContent)), want: ${want}}; })()`, {timeout: 20000});
    check(fm && fm.dt.join('|') === 'Tags|As of' && fm.dd[1] === fm.want && /2026/.test(fm.want) && !fm.raw, `the editor: the front matter is one line of fields, the date written out (was "as_of: 2026-11-10") ${JSON.stringify(fm)}`);
    const ln = await until(`(() => { const a = document.querySelector('#wk-cm .cm-wkwl'); return a ? {t: a.textContent, ti: a.getAttribute('title')} : null; })()`);
    check(ln && ln.t === 'Weather plan B' && ln.ti === 'Processes/Shoot day/Weather plan B', `the editor: a link shows the page's name, the path as its tooltip ${JSON.stringify(ln)}`);
    const tk = await until(`(() => { const a = document.querySelector('#wk-cm .cm-wkref'), t = document.querySelector('#wk-cm .cm-wkreft'); return a && t ? a.textContent + t.textContent : null; })()`);
    check(tk === `#${T} Book the hall`, `the editor: a task link shows its title after the number (was only "#${T}") ${tk}`);
    const ph = await ev(`tr('Write … (/ for commands)')`);
    check(ph === 'Write … (/ for commands)' && !/\[\[/.test(ph), 'the editor\'s hint has no link syntax ' + ph);
    await shot('p21198a-editor-1280.png');
    // a click on the fields (wkcm_wDown) puts the cursor there; headless Firefox gives the page no real focus, so the editor's
    // focus mark (WKCM_FOC, set by its focus event) is set by hand after the click
    await ev(`(() => { const dt = document.querySelector('#wk-cm .cm-wkfmw dt'); dt.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, button: 0})); WKCM.view.dispatch({effects: WKCM_FOC.of(true)}); return WKCM.view.state.selection.main.head; })()`);
    check(await until(`!document.querySelector('#wk-cm .cm-wkfmw') && [...document.querySelectorAll('#wk-cm .cm-line')].some(l => /^as_of: 2026-11-10/.test(l.textContent))`),
      'the editor: a click on the fields shows the front matter to edit') || console.log('fm lines:', await ev(`JSON.stringify({lines: [...document.querySelectorAll('#wk-cm .cm-line')].slice(0, 6).map(l => l.textContent), doc: WKCM.view.state.doc.sliceString(0, 60), sel: WKCM.view.state.selection.main.head,
        focus: WKCM.view.hasFocus, fld: WKCM_FIELD && WKCM.view.state.field(WKCM_FIELD, false)?.foc, same: document.querySelector('#wk-cm .cm-editor') === WKCM.view.dom, html: document.querySelector('#wk-cm .cm-content')?.innerHTML.slice(0, 500)})`));
    await ev(`(() => { const v = WKCM.view; v.dispatch({selection: {anchor: v.state.doc.length}}); return 1; })()`);
    check(await until(`!!document.querySelector('#wk-cm .cm-wkfmw .wkattrs')`), 'the editor: the cursor out of it folds the fields again');

    // ================= the read view (the lock "Read-only")
    await ev(`(() => { LS.set('wkRo', '1'); WK.edit = false; renderView(); return 1; })()`);
    const rd = await until(`(() => { const a = document.querySelector('#wk-md a.wklink'), dl = document.querySelector('#view .wkpage .wkattrs'); if (!a || !dl) return null;
      const as = [...dl.querySelectorAll('div')].find(x => x.querySelector('dt')?.textContent === 'As of');
      return {t: a.textContent, ti: a.getAttribute('title'), dt: [...dl.querySelectorAll('dt')].map(x => x.textContent).sort().join('|'), dd: as?.querySelector('dd')?.textContent, want: ${want}}; })()`, {timeout: 20000});
    check(rd && rd.t === 'Weather plan B' && rd.ti === 'Processes/Shoot day/Weather plan B', `read: the link shows the page's name, the path as its tooltip ${JSON.stringify(rd)}`);
    check(rd && rd.dt === 'As of|Tags' && rd.dd === rd.want, `read: the front matter's keys as words, the date written out (was "as_of 2026-11-10") ${JSON.stringify(rd)}`);
    await shot('p21198a-read-1280.png');
    await nav(B + '?w=1280#wiki/' + P.min);
    const ev1 = await until(`(() => { const a = document.querySelector('#view .wkpage .wkattrs dd a'); return a ? {t: a.textContent, h: a.getAttribute('href'), dt: document.querySelector('#view .wkpage .wkattrs dt')?.textContent} : null; })()`, {timeout: 20000});
    check(ev1 && ev1.t === 'Open event' && ev1.h === '#ev/4711' && ev1.dt === 'Event', `read: the minutes' event as a link (was "termin 4711") ${JSON.stringify(ev1)}`);
    await nav(B + '?w=1280#wiki/' + P.plan);
    const bl = await until(`(() => { const a = document.querySelector('#view .wkback a'); return a ? {name: a.querySelector('span')?.firstChild?.textContent.trim(), dir: a.querySelector('.wkpdir')?.textContent, h: a.getAttribute('href')} : null; })()`, {timeout: 20000});
    check(bl && bl.name === 'Checklist' && bl.dir === 'Processes / Shoot day' && bl.h === '#wiki/' + P.check, `"Linked from": the name, its folders quietly beside it (was the full path) ${JSON.stringify(bl)}`);

    // ================= the daily note and the folders the app names itself
    await nav(B + '?w=1280#wiki/' + P.day);
    const dn = await until(`(() => { const h = document.querySelector('#view .wkpage h2'); return h && h.textContent.trim() ? {h: h.textContent.trim(), want: fmtDay('year', new Date('2026-11-14T00:00:00')), crumbs: document.querySelector('#view .wkpage .wkcrumbs')?.textContent} : null; })()`, {timeout: 20000});
    check(dn && dn.h === dn.want && /2026/.test(dn.h) && /Daily notes/.test(dn.crumbs || '') && !/journal/.test(dn.crumbs || ''), `the daily note: titled with its date, its folder "Daily notes" (was 2026-11-14 in "journal") ${JSON.stringify(dn)}`);
    await shot('p21198a-daynote-1280.png');
    const lbl = await ev(`JSON.stringify([wk_label('journal'), wk_label('Templates'), wk_label('Vorlagen'), wk_label('journal/2026-11-14') === fmtDay('year', new Date('2026-11-14T00:00:00')), wk_label('journal/x'), wk_label('A/journal'), wk_dirLabel('journal/2026-11-14')])`);
    check(lbl === JSON.stringify(['Daily notes', 'Templates', 'Templates', true, 'x', 'journal', 'Daily notes']), 'the labels: only the top folders and a dated note are named in words, other names stay ' + lbl);
    await nav(B + '?w=1280#wiki');
    const tree = await until(`(() => { const t = [...document.querySelectorAll('#view .wkitem, #side .sbbtn .n')].map(x => x.textContent.trim()); return t.some(x => x === 'Daily notes') ? t : null; })()`, {timeout: 20000});
    check(tree && !tree.includes('journal') && tree.includes('Templates'), `the lists name the folder "Daily notes", not "journal" ${JSON.stringify(tree)}`);

    // ================= a page from a template
    const mk = await ev(`wk_mk('private', 'Minutes/Monday', ${P.tpl}).then(r => r.id)`);
    const mb = mk && (await call('GET', '/api/wiki/pages/' + mk)).body;
    check(typeof mb === 'string' && !/^\s*(?:[-*]|\d+\.)\s*(\[ \])?\s*$/m.test(mb) && !/type: minutes/.test(mb) && /tags: \[minutes\]/.test(mb) && /# Monday/.test(mb) && /- kept point/.test(mb) && /Notes here/.test(mb),
      `a page from a template: no empty points, the template's own front matter left out, its tags and filled points kept ${JSON.stringify(mb)}`);
    const own = await ev(`wk_meetText(null, {eid: 7, day: '2026-11-14', title: 'T'}, 'Minutes/T').text`);
    check(/- \[ \] *\n/.test(own + '\n'), 'the built-in minutes keep their empty points to fill (#1958) ' + JSON.stringify(own));

    // ================= search: the name with its folders, the snippet without the title
    const sn = await ev(`wks_snipHtml({path: 'Processes/Shoot day/Checklist', snippet: 'Checklist This list holds every shoot day', marks: [[20, 25]]}, 'holds')`);
    check(/^<small class="wksnip">This list <b>holds<\/b> every shoot day<\/small>$/.test(sn || ''), `a snippet does not repeat the page's title ${sn}`);
    const sn2 = await ev(`wks_snipHtml({path: 'A/Other', snippet: '…see [[Proc and **bold** text', marks: []}, 'x')`);
    check(sn2 === '<small class="wksnip">…see Proc and bold text</small>', 'a cut snippet shows no [[ or ** ' + sn2);
    await ev(`(() => { const q = document.querySelector('#wk-q'); q.value = 'Weather'; q.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    const hit = await until(`(() => { const a = [...document.querySelectorAll('#wk-res a.wkitem')].find(x => x.getAttribute('href') === '#wiki/${P.plan}'); const s = a && a.querySelector(':scope > span'); return s ? {name: s.firstChild?.textContent.trim(), dir: s.querySelector('.wkpdir')?.textContent} : null; })()`, {timeout: 20000});
    check(hit && hit.name === 'Weather plan B' && hit.dir === 'Processes / Shoot day', `a search hit: the name, its folders quietly beside it ${JSON.stringify(hit)}`);
    await shot('p21198a-search-1280.png');
    await ev(`(() => { LS.set('wkRo', ''); return 1; })()`);
  });

  console.log(`p21198_a_wiki_text_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
