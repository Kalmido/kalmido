// 2.1353.0 UI test, part A (#6827): every section of a settings tab is a folded head row (details.sfold, settings.js sf_*),
// also the eight groups of Company & office; the one fold "Weitere Optionen" of #4833 is gone (this replaces p2583_c).
// kalmido-suite: fresh
// freelancer-matrix: settings
// Own container (start.sh), Firefox, German, invented data only. Alice is the admin of the organisation "Alpha Studio" and has
// her private workspace; Frida has no organisation (tests/freelancer_fixture.py idea: a person without an organisation).
// - every heading of the folded tabs sits in a head row (none left loose); a head row = icon, heading, state, chevron
// - at the start a head row is open unless settings.js SF_SHUT lists it (#7555; was #6827: all closed but one); the rule
//   itself (heights, reasons, icons) is tests/p7555_settings_open_ui.js
// - open / closed by hand is the person's setting settings_more (all devices: after a reload as set); set_delta refuses a wrong entry
// - the search finds a setting in a closed row, opens the row and lights it up, nothing saved by that
// - a change in a row: the row says "1 geändert"
// - a jump (settingsModal('sidebar'), settingsModal('caldav')) opens the row of its place and lights it up
// - the keyboard: the head row is in the tab order and takes the focus; activated it opens and closes (#6377)
// - Company & office: the groups are head rows (the first open, #7555), "Firma" names the company, "Dokumente & Nummern" says
//   "Kleinunternehmer · RE-<year>-###"; settingsModal('biz-tax') and ost_show('docs') open their group; organisation and Private
//   (Frida) look the same, a phone (412 px) too
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21353_a_settings_fold', check, shots: 'P21353A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (process.env.P21353A_NOSTART !== '1') execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,files,docs,office,clients';
const YEAR = new Date().getFullYear();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments']});
  const me = (await call(CA, 'GET', '/api/state')).me.id;
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha Studio', admin_id: me})).id;
  check(!!ORG, 'setup: an organisation');
  await call(CA, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT, workspace: 'private'});
  const fr = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.http < 300, 'setup: a person without an organisation');
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT, workspace: 'private'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'setup: frida is in no organisation');

  // the server side: the new entries, a wrong one refused
  for (const bad of ['../x', 'o:Look/x', 'x:look/side', 'o:look/' + 'a'.repeat(41)]) check((await call(CA, 'PATCH', '/api/settings', {set_delta: {settings_more: {add: [bad]}}})).http === 400, 'settings_more: a wrong entry is 400: ' + bad);
  check((await call(CA, 'PATCH', '/api/settings', {set_delta: {settings_more: {add: ['o:look/side']}}})).http === 200, 'settings_more: o:look/side is taken');
  check((await call(CA, 'PATCH', '/api/settings', {set_delta: {settings_more: {remove: ['o:look/side']}}})).http === 200, 'settings_more: and removed');
  check(((await call(CA, 'GET', '/api/state')).settings?.settings_more || '[]') === '[]', 'settings_more: empty again');

  const stored = `fetch('/api/state', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.settings.settings_more || '[]')`;
  const seen = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); return !!e && e.getClientRects().length > 0 && e.getBoundingClientRect().height > 0 && (!e.checkVisibility || e.checkVisibility()); })()`;
  const ROW = k => `document.querySelector('.smodal details[data-sf="${k}"]')`;
  const signIn = async ({ev, nav, until}, who) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`);
    await nav(B + '#home');
    return until(`typeof settingsModal === 'function' && !!document.querySelector('#view') && document.documentElement.lang === 'de'`);
  };
  const open = async ({ev, until}, sec, sel = '.smodal .spane:not(.hidden) details.sfold') => {
    const e = await ev(`(() => { document.querySelectorAll('.smodal').forEach(m => m.remove()); try { settingsModal('${sec}'); } catch (x) { return String(x && x.stack || x); } return ''; })()`);
    check(!e, `settingsModal('${sec}') runs without an error ` + e);
    return until(`!!document.querySelector(${JSON.stringify(sel)})`);
  };
  const tap = (ev, k) => ev(`(() => { ${ROW(k)}.querySelector(':scope > summary').click(); return 1; })()`);

  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot, until} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 1000}});
    check(await signIn(o, 'alice'), 'alice: the app runs in German');

    // every heading of the folded tabs in a head row; the start state
    for (const tab of ['general', 'look', 'notify', 'data', 'account', 'help', 'docs', 'nav', 'modules']) {
      check(await open(o, tab, `.smodal [data-pane="${tab}"]:not(.hidden)`), `${tab}: the tab opens`);
      await o.idle({quiet: 400});  // what the tab draws after loading (forwardings, sessions ...) is folded too
      const r = JSON.parse(await ev(`(() => { const p = document.querySelector('.smodal [data-pane="${tab}"]');
        const loose = [...p.querySelectorAll('h4')].filter(h => !h.closest('details.sfold, details.introw, details.modgrp, details.mopt, .lookpv')).map(h => h.id || h.textContent.trim().slice(0, 30));
        const rows = [...p.querySelectorAll('details.sfold')];
        return JSON.stringify({loose, n: rows.length, open: rows.filter(d => d.open).map(d => d.dataset.sf), bad: rows.filter(d => { const s = d.querySelector(':scope > summary'); return !s.querySelector(':scope > svg:first-child')?.innerHTML.trim() || !s.querySelector(':scope > h4, :scope > h3') || !s.querySelector(':scope > .fcar'); }).map(d => d.dataset.sf)}); })()`));
      check(!r.loose.length, `${tab}: no heading outside a head row ` + JSON.stringify(r.loose));
      check(r.n >= 1 && !r.bad.length, `${tab}: head rows with icon, heading and chevron ` + JSON.stringify(r));
      const want = JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('.smodal [data-pane="${tab}"] details.sfold')].filter(d => d.dataset.sfd === '1').map(d => d.dataset.sf))`));
      check(JSON.stringify(r.open) === JSON.stringify(want) && r.open.length >= 1, `${tab}: open at the start = its default (#7555) ${JSON.stringify(want)}: ` + JSON.stringify(r.open));
      check(!await ev(`!!document.querySelector('.smodal details.setmore')`), `${tab}: no "Weitere Optionen" any more`);
    }
    check(await open(o, 'look'), 'look opens');
    check(await ev(`${ROW('look/lookin')}.querySelector('summary h4').textContent.trim() === 'Farben und Schrift'`), 'look: the first row is "Farben und Schrift"');
    check(!await ev(seen('#s-sideprog')) && await ev(seen('#s-side-h')), 'look: a closed row (Seitenleiste, long) shows its heading, not its switch');
    await shot('p21353-a-look-1440.png');

    // the search finds the switch in the closed row, opens it and lights it up; nothing saved
    const lab = await ev(`document.querySelector('#s-sideprog').closest('label').textContent.trim()`);
    await ev(`(() => { window.__e = []; window.addEventListener('error', x => window.__e.push(x.message + ' ' + x.filename + ':' + x.lineno + ':' + x.colno)); return 1; })()`);
    await ev(`(() => { const q = document.querySelector('#s-search'); q.focus(); q.removeAttribute('readonly'); q.value = ${JSON.stringify(lab.slice(0, 18))}; q._typed = true; q.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    check(await until(`[...document.querySelectorAll('#s-sres [data-hit]')].some(b => b.textContent.includes(${JSON.stringify(lab.slice(0, 18))}))`), 'search: the switch in the closed row is a hit ' + lab + ' ' + await ev(`(document.querySelector('#s-sres')?.className || '-') + ' ' + (document.querySelector('#s-sres')?.textContent || '').slice(0, 300) + ' tab=' + document.querySelector('.smodal .spane:not(.hidden)')?.dataset.pane + ' errors=' + JSON.stringify(window.__e)`));
    await ev(`(() => { [...document.querySelectorAll('#s-sres [data-hit]')].find(b => b.textContent.includes(${JSON.stringify(lab.slice(0, 18))})).click(); return 1; })()`);
    check(await until(`${ROW('look/side')}.open && !!document.querySelector('#s-sideprog').closest('.sflash')`, {timeout: 5000}), 'search: the hit opens the row and lights the switch up');
    check(await ev(seen('#s-sideprog')), 'search: the switch is shown now');
    check(await ev(stored) === '[]', 'search: nothing saved');

    // a change in the row: "1 geändert"
    const CNT = `${ROW('look/side')}.querySelector('summary .sfc').textContent.trim()`;
    await ev(`(() => { document.querySelector('#s-sideprog').click(); return 1; })()`);
    check(await until(`${CNT} === '1 geändert'`), 'the row says "1 geändert" ' + await ev(CNT));
    check(await until(`fetch('/api/state', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.settings.side_progress === '0')`), 'the change is saved');

    // by hand: open a closed row, close the open one; after a reload as set (the person's setting)
    check(await open(o, 'look') && await ev(`!${ROW('look/side')}.open`), 'reopened: the row the search opened is closed again');
    check(await until(`${CNT} === '1 geändert'`), 'reopened: the count is there');
    await tap(ev, 'look/side'); await tap(ev, 'look/lookin');
    check(await until(`${stored}.then(v => { const a = JSON.parse(v); return a.includes('o:look/side') && a.includes('c:look/lookin'); })`), 'by hand: settings_more holds o:look/side and c:look/lookin ' + await ev(stored));
    await nav(B + 'static/icon.svg'); await nav(B + '#home');
    await until(`typeof settingsModal === 'function' && !!document.querySelector('#view')`);
    check(await open(o, 'look') && await ev(`${ROW('look/side')}.open && !${ROW('look/lookin')}.open`), 'after the reload: Sidebar open, "Farben und Schrift" closed');
    await tap(ev, 'look/lookin');  // back to the start: no entry left
    check(await until(`${stored}.then(v => !JSON.parse(v).some(x => x.endsWith('look/lookin')))`), 'opened again = the start: no entry for it');

    // the keyboard (#6377): the head row is a native summary: in the tab order, takes the focus; Enter / Space activate it
    // (headless Firefox does not activate a native control by Enter, see p2132_ui: the activation = its click)
    const kb = JSON.parse(await ev(`(() => { const s = ${ROW('look/tips')}.querySelector('summary'); s.focus(); return JSON.stringify({ti: s.tabIndex, on: document.activeElement === s}); })()`));
    check(kb.ti === 0 && kb.on, 'keyboard: the head row is in the tab order and takes the focus ' + JSON.stringify(kb));
    const tips0 = await ev(`${ROW('look/tips')}.open`);  // (#7555): open at the start (short)
    await ev(`(() => { document.activeElement.click(); return 1; })()`);
    check(await until(`${ROW('look/tips')}.open === ${!tips0}`, {timeout: 3000}), 'keyboard: activated, the head row toggles');
    await ev(`(() => { document.activeElement.click(); return 1; })()`);
    check(await until(`${ROW('look/tips')}.open === ${tips0}`, {timeout: 3000}), 'keyboard: activated again, it toggles back');

    // jumps open the row of their place
    check(await open(o, 'sidebar', '.smodal #s-side-h'), 'settingsModal(sidebar) opens');
    check(await until(`${ROW('look/side')}.open`), 'settingsModal(sidebar): the Sidebar row is open');
    await tap(ev, 'look/side');  // closed by hand again
    check(await until(`${stored}.then(v => !JSON.parse(v).includes('o:look/side'))`), 'Sidebar closed by hand: no entry left');
    check(await open(o, 'sidebar', '.smodal #s-side-h') && await until(`${ROW('look/side')}.open && !!document.querySelector('#s-side-h').closest('.sflash')`, {timeout: 5000}), 'settingsModal(sidebar): the closed row opens, the place lights up');
    check(await open(o, 'caldav', '.smodal #s-dav-h') && await until(`document.querySelector('.smodal #s-dav-h').closest('details.introw')?.open === true`), 'settingsModal(caldav): its integration row opens');
    check(await open(o, 'templates', '.smodal #s-tpl-h') && await until(`${ROW('data/tpl')}?.open`), 'settingsModal(templates): the Templates row opens');

    // Company & office: the groups are head rows, closed, with their state; the organisation and Private the same
    const biz = async (ws) => {
      await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({workspace: '${ws}'})}).then(r => r.status)`);
      await nav(B + 'static/icon.svg'); await nav(B + '#home');
      await until(`typeof settingsModal === 'function' && !!document.querySelector('#view')`);
      await open(o, 'biz', '.smodal #s-biz #ofc-set #s-biz-company');
      return JSON.parse(await ev(`(() => { const f = document.querySelector('.smodal #ofc-set');
        const rows = [...f.querySelectorAll(':scope > details.sfold')];
        return JSON.stringify({ids: rows.map(d => d.dataset.sf), open: rows.filter(d => d.open).length, first: !!rows[0]?.open, noic: rows.filter(d => !d.querySelector(':scope > summary > svg:first-child')?.innerHTML.trim()).map(d => d.dataset.sf), loose: [...f.querySelectorAll(':scope > h3, :scope > fieldset.ostp')].length,
          co: rows.find(d => d.dataset.sf === 'biz/company')?.querySelector('summary').textContent.trim() || ''}); })()`));
    };
    const bo = await biz(`org:${ORG}`);
    check(bo.ids[0] === 'biz/company' && bo.ids.includes('biz/docs') && bo.ids.includes('biz/tax') && bo.open === 1 && bo.first && !bo.loose && !bo.noic.length, 'office of the organisation: the groups are head rows, the first open (#7555), each with its icon ' + JSON.stringify(bo));
    check(/Alpha Studio/.test(bo.co), 'office of the organisation: "Firma" names the company ' + bo.co);
    await shot('p21353-a-biz-org-1440.png');
    // small business + invoice numbers in the head row of Documents & numbers
    await ev(`(() => { ${ROW('biz/docs')}.querySelector('summary').click(); return 1; })()`);
    check(await until(`${ROW('biz/docs')}.open && !!document.querySelector('#os-small')`), 'Dokumente & Nummern opens by a tap');
    await ev(`(() => { const x = document.querySelector('#os-small'); if (!x.checked) x.click(); const s = document.querySelector('#os-inv-scheme'); s.value = 'RE-{yyyy}-{seq:03}'; s.dispatchEvent(new Event('input', {bubbles: true})); s.dispatchEvent(new Event('change', {bubbles: true})); s.blur(); return 1; })()`);
    check(await until(`api('GET', '/api/office/settings').then(j => !!j.settings && +j.settings.small_business === 1 && j.settings.invoice_scheme === 'RE-{yyyy}-{seq:03}')`), 'the office saved small business and the scheme (each field itself)');
    check(await open(o, 'biz', '.smodal #s-biz #ofc-set #s-biz-docs') && await until(`${ROW('biz/docs')}.querySelector('.sfst').textContent.trim() === 'Kleinunternehmer · RE-${YEAR}-###'`), 'Dokumente & Nummern says "Kleinunternehmer · RE-<year>-###" ' + await ev(`${ROW('biz/docs')}?.querySelector('.sfst')?.textContent`));
    check(await ev(`${ROW('biz/docs')}.open`), 'the group opened by a tap stays open (the person\'s setting)');
    // jumps into Company & office: settingsModal('biz-tax') (ofcSetLink) and ost_show
    check(await open(o, 'biz-tax', '.smodal #s-biz #ofc-set #s-biz-tax') && await until(`${ROW('biz/tax')}.open && !!document.querySelector('#s-biz-tax').closest('.sflash')`, {timeout: 6000}), 'settingsModal(biz-tax): Bank & Steuern opens and lights up');
    check(await ev(`(() => { ost_show('packs'); return ${ROW('biz/packs')}.open; })()`), 'ost_show(packs): its group opens');
    check(await ev(stored).then(v => !JSON.parse(v).includes('o:biz/tax') && !JSON.parse(v).includes('o:biz/packs')), 'jumps save nothing');
    const bp = await biz('private');
    check(JSON.stringify(bp.ids.filter(x => bo.ids.includes(x))) === JSON.stringify(bp.ids) && bp.ids.length >= 5 && !bp.loose, 'office of Private: the same head rows ' + JSON.stringify(bp));

    // a phone: the same head rows
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 900}});
    await nav(B + 'static/icon.svg'); await nav(B + '#home');
    await until(`typeof settingsModal === 'function' && !!document.querySelector('#view')`);
    check(await open(o, 'general', '.smodal [data-pane="general"] details.sfold'), 'phone: General opens');
    check(await ev(`[...document.querySelectorAll('.smodal [data-pane="general"] details.sfold')].every(d => d.open === (d.dataset.sfd === '1')) && ${seen('.smodal #s-lang-h')}`), 'phone: General head rows as at the start (#7555), headings shown');
    const ph = await ev(`(() => { const s = document.querySelector('.smodal #s-lang-h').closest('summary').getBoundingClientRect(); return Math.round(s.height) >= 44 && s.right <= innerWidth + 1; })()`);
    check(ph, 'phone: a head row is at least 44 px high and fits the width');
    await shot('p21353-a-general-412.png');
  }, false);

  // a person without an organisation: Settings and Company & office the same
  await firefox(async o => {
    const {cmd, ev, ctx, until, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 1000}});
    check(await signIn(o, 'frida'), 'frida: the app runs in German');
    check(await open(o, 'general'), 'frida: General opens');
    check(await ev(`[...document.querySelectorAll('.smodal [data-pane="general"] details.sfold')].length >= 4 && [...document.querySelectorAll('.smodal [data-pane="general"] details.sfold')].every(d => d.open === (d.dataset.sfd === '1'))`), 'frida: General as head rows, as at the start (#7555)');
    check(await open(o, 'biz', '.smodal #s-biz #ofc-set #s-biz-company'), 'frida: Company & office opens');
    const r = JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('.smodal #ofc-set > details.sfold')].map(d => [d.dataset.sf, d.open]))`));
    check(r.length >= 5 && r.every(([, x], i) => x === (i === 0)) && r[0][0] === 'biz/company', 'frida: her office\'s groups as head rows, only the first open (#7555) ' + JSON.stringify(r));
    await shot('p21353-a-biz-frida-1440.png');
  }, false);

  console.log(`p21353_a_settings_fold: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
