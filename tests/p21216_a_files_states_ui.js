// Package 2.1216.0 (#6109) UI tests: files and documents say loading, failing and nothing-here with the shared blocks
// kalmido-suite: fresh
// (render.js loadingHtml / errorState / noAccessState, core.js errText) like the knowledge pages (#6088).
// Own container (start.sh), Firefox, invented folders / documents only. Screenshots: P21216A_SHOTS.
// - a folder that fails to load: "The folder could not be loaded" + "Try again", the title is the folder's name or "Files"
//   (never "Organisation"), no button "Private" at the sentence, no toast beside it; "Try again" shows the folder's content
// - a folder that is not there: the no-access block with a way back
// - the file search that fails says so (never "No results."), "Try again" finds it
// - the documents' list that fails: the error block (never "No documents found"), "Try again" shows the list
// - the document's tab History that fails: the error block in the tab, not an empty tab
// - an upload the server refuses: its reasons once, in the list of what stayed out (never "Error 400", no toast beside it)
// freelancer-matrix: files (alice has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21216_a_files_states_ui', check, shots: 'P21216A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21216_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

function tinyPdf(text) {  // a one-page PDF with a text layer (as tests/p21148_receipts_test.py)
  const stream = `BT /F1 12 Tf 40 700 Td (${text}) Tj ET`;
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const x = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  return out + `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${x}\n%%EOF\n`;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const st0 = await call('GET', '/api/state');
  const feats = [...new Set([...(st0.settings.features || '').split(',').filter(Boolean), 'files', 'docs'])].join(',');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: feats, workspace: 'private'});
  check(!(st0.me.workspaces || []).length, 'setup: alice has no organisation (a person on her own)');
  const BOX = (await call('POST', '/api/files/folders', {name: 'Projektakten', space: 'private'})).id;
  const SUB = (await call('POST', '/api/files/folders', {name: 'Angebote Sommer', parent_id: BOX})).id;
  check(BOX && SUB, `setup: the folder Projektakten with a subfolder ${BOX} ${SUB}`);
  const fd = new FormData(); fd.append('files', new Blob([tinyPdf('Rechnung Juni')], {type: 'application/pdf'}), 'rechnung-juni.pdf'); fd.append('ws', 'private');
  const DOC = (await (await fetch(B + 'api/docs', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CA}, body: fd})).json()).ids?.[0];
  check(DOC, 'setup: a document ' + DOC);

  const login2 = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  // one fetch answer replaced in the page (a failing server for one URL, body = its JSON), FAILX() takes it back
  const FAIL = (rx, status = 500, method = '', body = {error: 'Test failure'}) => `(() => { window.__f0 = window.__f0 || window.fetch; const f0 = window.__f0, rx = new RegExp(${JSON.stringify(rx)});
    window.fetch = (u, o) => rx.test(String(u && u.url || u)) && (!${JSON.stringify(method)} || (o && o.method || 'GET') === ${JSON.stringify(method)}) ? Promise.resolve(new Response(${JSON.stringify(JSON.stringify(body))}, {status: ${status}, headers: {'Content-Type': 'application/json'}})) : f0(u, o); return 1; })()`;
  const FAILX = `(() => { if (window.__f0) window.fetch = window.__f0; return 1; })()`;
  const TOASTOFF = `(() => { const t = document.querySelector('#toast'); if (t) { t.classList.add('hidden'); t.textContent = ''; } return 1; })()`;
  const TOAST = `(() => { const t = document.querySelector('#toast'); return t && !t.classList.contains('hidden') ? t.textContent : ''; })()`;

  await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await login2(ev) === 200, 'ff: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await nav(B + '#ablage');
    check(await until(`!!document.querySelector('#view .abview') && /Projektakten/.test(document.querySelector('#view .abmain')?.textContent || '')`, {timeout: 20000}), 'the file store with Projektakten');

    // ================= a folder that fails to load
    await ev(TOASTOFF);
    await ev(FAIL(`/api/files\\?parent=${BOX}(&|$)`));
    await ev(`(() => { location.hash = '#ablage/${BOX}'; return 1; })()`);
    const er = await until(`(() => { const e = document.querySelector('#view .abmain .eerr'); return e ? {t: e.textContent, retry: !!e.querySelector('[data-esretry]'), priv: !!e.querySelector('[data-sp="private"]'), title: document.querySelector('#view .abmain .abtitle, #view .abmain .spovc')?.textContent || ''} : null; })()`, {timeout: 20000});
    check(er && /The folder could not be loaded/.test(er.t) && er.retry, `folder error: the sentence + Try again ${JSON.stringify(er)}`);
    check(er && !er.priv && !/Organisation/.test(er.title) && /Projektakten|Files/.test(er.title), `folder error: the title is the folder / Files, no "Private" button at the sentence ${JSON.stringify(er)}`);
    check(!/Test failure|could not be loaded/.test(await ev(TOAST)), 'folder error: no toast beside it');
    await shot('p21216a-folder-error.png');
    await ev(FAILX);
    await ev(`(() => { document.querySelector('#view .abmain [data-esretry]').click(); return 1; })()`);
    check(await until(`/Angebote Sommer/.test(document.querySelector('#view .abmain')?.textContent || '') && !document.querySelector('#view .abmain .eerr')`, {timeout: 20000}), 'folder error: Try again shows the folder with its subfolder');

    // ================= a folder that is not there (404): the lock block with a way back
    await ev(TOASTOFF);
    await ev(`(() => { location.hash = '#ablage/987654'; return 1; })()`);
    const na = await until(`(() => { const e = document.querySelector('#view .abmain .enoacc'); return e ? {t: e.textContent, back: !!e.querySelector('[data-ab="space"]')} : null; })()`, {timeout: 20000});
    check(na && /does not exist or you cannot see it/.test(na.t) && na.back, `a missing folder: the no-access block with a way back ${JSON.stringify(na)}`);
    check(!(await ev(TOAST)), 'a missing folder: no toast beside it');

    // ================= the file search fails
    await nav(B + '#ablage');
    await until(`!!document.querySelector('#view #ftxt-q') && typeof ftxtSet === 'function'`, {timeout: 20000});
    await ev(TOASTOFF);
    await ev(FAIL('/api/search'));
    await ev(`(() => { ftxtSet('Angebote'); return 1; })()`);
    const se = await until(`(() => { const e = document.querySelector('#view .abmain .eerr'); return e ? {t: document.querySelector('#view .abmain').textContent, retry: !!e.querySelector('[data-esretry]')} : null; })()`, {timeout: 20000});
    check(se && /The search failed/.test(se.t) && !/No results/.test(se.t) && se.retry, `search error: says so, never "No results." ${JSON.stringify(se)}`);
    check(!(await ev(TOAST)), 'search error: no toast');
    await ev(FAILX);
    await ev(`(() => { document.querySelector('#view .abmain [data-esretry]').click(); return 1; })()`);
    check(await until(`/Angebote Sommer/.test(document.querySelector('#view .abmain')?.textContent || '') && !document.querySelector('#view .abmain .eerr')`, {timeout: 20000}), 'search error: Try again finds the folder');
    await ev(`(() => { ftxtSet(''); return 1; })()`);

    // ================= the documents' list fails
    await ev(TOASTOFF);
    await ev(FAIL('/api/docs\\?'));
    await ev(`(() => { location.hash = '#ablage/docs'; return 1; })()`);
    const de = await until(`(() => { const e = document.querySelector('#view .eerr'); return e ? {t: document.querySelector('#view').textContent, retry: !!e.querySelector('[data-esretry]')} : null; })()`, {timeout: 20000});
    check(de && /The documents could not be loaded/.test(de.t) && !/No documents found/.test(de.t) && de.retry, `documents error: the block, never "No documents found" ${JSON.stringify(de)}`);
    check(!(await ev(TOAST)), 'documents error: no toast');
    await shot('p21216a-docs-error.png');
    await ev(FAILX);
    await ev(`(() => { document.querySelector('#view [data-esretry]').click(); return 1; })()`);
    check(await until(`!!document.querySelector('#view [data-dco="${DOC}"]') && !document.querySelector('#view .eerr')`, {timeout: 20000}), 'documents error: Try again shows the document');

    // ================= the document's tab History fails
    await ev(FAIL(`/api/files/nodes/${DOC}$`));
    await ev(`(() => { dc_open(${DOC}, {tab: 'hist'}); return 1; })()`);
    const he = await until(`(() => { const e = document.querySelector('.dv-view #dv-p-hist .eerr'); return e ? {t: e.textContent, retry: !!e.querySelector('[data-esretry]')} : null; })()`, {timeout: 20000});
    check(he && /The history could not be loaded/.test(he.t) && he.retry, `History tab error: the block in the tab, not empty ${JSON.stringify(he)}`);
    const sh = await ev(`document.querySelector('.dv-view #dv-p-share .eerr')?.textContent || ''`);
    check(!sh || (/The shares could not be loaded/.test(sh) && !/history/.test(sh)), `review: the Sharing tab says its own sentence ${JSON.stringify(sh)}`);
    await ev(FAILX);
    await ev(`(() => { document.querySelector('.dv-view #dv-p-hist [data-esretry]').click(); return 1; })()`);
    check(await until(`!!document.querySelector('.dv-view #dv-p-hist .dv-hist') && !document.querySelector('.dv-view #dv-p-hist .eerr')`, {timeout: 20000}), 'History tab error: Try again shows the history');

    // ================= an upload the server refuses (2.1177.0 #6114 lists the refused files; #6109: said once, no toast beside it)
    await nav(B + '#ablage/docs');
    await until(`typeof dc_upload === 'function'`, {timeout: 20000});
    // 2.1208.0 (#6173): each upload has its own list of refused files - the newest list is the one of the upload just made
    const OUTL = `(() => { const e = [...document.querySelectorAll('#upbars .upout')].pop(); return e ? e.textContent : ''; })()`;
    const one = 'scan.pdf: larger than 50 MB';
    await ev(TOASTOFF);
    await ev(FAIL('/api/docs$', 400, 'POST', {ids: [], errors: [one], dups: [], error: one}));
    await ev(`(() => { window.__up1 = 0; dc_upload([new File(['x'], 'scan.pdf', {type: 'application/pdf'})], 'private').then(() => { window.__up1 = 1; }); return 1; })()`);
    const u1 = await until(`window.__up1 && (${OUTL}) || null`, {timeout: 20000});
    check(u1 && /1 file was not uploaded/.test(u1) && u1.includes(one) && !/Error 400/.test(u1), `upload refused: the reason in the list, never "Error 400" ${JSON.stringify(u1)}`);
    const t1 = await ev(TOAST);
    check(!t1 || !/Error 400|larger than/.test(t1), `upload refused: no toast with the same reason beside the list ${JSON.stringify(t1)}`);
    await ev(FAILX); await ev(TOASTOFF);
    const two = ['a.pdf: the file is empty and was not uploaded', 'b.pdf: larger than 50 MB'];
    await ev(FAIL('/api/docs$', 400, 'POST', {ids: [], errors: two, dups: [], error: two.join('; ')}));
    await ev(`(() => { window.__up2 = 0; dc_upload([new File(['x'], 'a.pdf', {type: 'application/pdf'}), new File(['y'], 'b.pdf', {type: 'application/pdf'})], 'private').then(() => { window.__up2 = 1; }); return 1; })()`);
    const u2 = await until(`window.__up2 && (${OUTL}) || null`, {timeout: 20000});
    check(u2 && /2 files were not uploaded/.test(u2) && u2.includes(two[0]) && u2.includes(two[1]), `upload: two reasons in ONE list ${JSON.stringify(u2)}`);
    const t2 = await ev(TOAST);
    check(!t2 || !/Error 400|larger than|empty/.test(t2), `upload: no toast beside the list ${JSON.stringify(t2)}`);
    await shot('p21216a-upload-errors.png');
    await ev(FAILX);
  }, true);

  console.log(`p21216_a_files_states_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
