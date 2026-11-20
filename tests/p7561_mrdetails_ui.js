// kalmido-suite: fresh
// #7561 UI test (Firefox, real layout): the card "Ready to merge" with details (200 lines of SQL) at 412 px (a phone, touch)
// and 1280 px (a computer). The card is drawn by the app's own mrHtml (static/js/git.js) into the view; the server side of the
// field (summary over 2000 = 400, unknown field, details kept) is tests/p220_api_test.py, the timeline card tests/p220_ui.js.
// - folded at first, its summary names the line count; open: a fixed-width font, every line and its indent kept (white-space
//   pre, 200 lines), the block scrolls inside itself (max height), a long line scrolls sideways inside the block and the page
//   itself never gets wider than the window
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7561_mrdetails_ui', check, shots: 'P7561_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7561_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
// 200 lines under the 10000 characters of a comment; the first one is long (a phone scrolls it sideways)
const SQL = ['ALTER TABLE office_documents_archive ADD COLUMN IF NOT EXISTS reviewed_by_person BIGINT REFERENCES users(id) ON DELETE SET NULL;',
  ...Array.from({length: 199}, (_, i) => `    UPDATE t${i} SET c = ${i} WHERE id > 0;`)].join('\n');

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']}, ACK);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, ACK);

  const run = (width, touch) => firefox(async o => {
    const {cmd, ev, ctx, nav} = o, tag = `${width}: `;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width, height: 860}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, tag + 'login');
    await nav(B + '#today');
    for (let i = 0; i < 60 && !(await ev(`typeof mrHtml === 'function' && !!document.querySelector('#view')`).catch(() => false)); i++) await sleep(250);
    // the app's own drawing of the card in a layer of its own over the page (a redraw of the view does not take it away): the full
    // width on a phone, about the task panel's on a computer
    const put = await ev(`(() => { const lay = document.createElement('div'); lay.id = 'mrl'; lay.style.cssText = 'position:fixed;inset:0;overflow:auto;z-index:10000;background:var(--bg);padding:.5rem;box-sizing:border-box';
      const box = document.createElement('div'); box.id = 'mrt'; box.style.maxWidth = '${width < 600 ? '100%' : '42rem'}'; lay.append(box); document.body.append(lay);
      box.innerHTML = mrHtml({id: 1, may_decide: false}, {kind: 'merge_request', pr_url: 'https://git.example.com/o/r/pull/7', repo: 'o/r', number: 7, state: 'open',
        summary: 'Adds the review column to the archive tables', details: ${JSON.stringify(SQL)}}, true);
      return !!box.querySelector('.sug.mr'); })()`);
    check(put, tag + 'the card is drawn');
    const geo = () => ev(`(() => { const d = document.querySelector('#mrt details.mrdet'), p = d && d.querySelector('pre'); if (!p) return null; const cs = getComputedStyle(p), r = p.getBoundingClientRect();
      return {open: d.open, sum: d.querySelector('summary').textContent.trim(), ws: cs.whiteSpace, mono: /mono|courier|menlo|consol/i.test(cs.fontFamily), ox: cs.overflowX,
        lines: p.textContent.split('\\n').length, sw: p.scrollWidth, cw: p.clientWidth, sh: p.scrollHeight, ch: p.clientHeight, w: Math.round(r.width), right: Math.round(r.right),
        sumH: Math.round(d.querySelector('summary').getBoundingClientRect().height), doc: document.querySelector('#mrl').scrollWidth, win: document.querySelector('#mrl').clientWidth}; })()`);
    const innerW = await ev('innerWidth');
    let g = await geo();
    check(g && !g.open && /^Details/.test(g.sum) && /200 lines/.test(g.sum), tag + 'folded at first, its summary names 200 lines ' + JSON.stringify(g && {open: g.open, sum: g.sum}));
    check(g && g.sumH >= (touch ? 44 : 27), tag + 'the summary is a touch target of its size ' + (g && g.sumH));
    await ev(`(() => { document.querySelector('#mrt details.mrdet summary').click(); return 1; })()`);
    for (let i = 0; i < 20 && !(g = await geo())?.open; i++) await sleep(100);
    check(g && g.open, tag + 'a click opens it');
    check(g && g.ws === 'pre' && g.mono && g.lines === 200, tag + 'fixed-width font, every line kept ' + JSON.stringify(g && {ws: g.ws, mono: g.mono, lines: g.lines}));
    check(g && g.sh > g.ch && g.ch > 100, tag + 'the 200 lines scroll inside the block ' + JSON.stringify(g && {sh: g.sh, ch: g.ch}));
    check(g && g.sw > g.cw && /auto|scroll/.test(g.ox), tag + 'a long line scrolls sideways inside the block ' + JSON.stringify(g && {sw: g.sw, cw: g.cw, ox: g.ox}));
    check(g && g.right <= innerW && g.doc <= g.win + 1, tag + 'the card itself stays inside the window, only the block scrolls sideways ' + JSON.stringify(g && {right: g.right, doc: g.doc, win: g.win}));
    const sx = await ev(`(() => { const p = document.querySelector('#mrt pre'); p.scrollLeft = 200; p.scrollTop = 400; return [p.scrollLeft, p.scrollTop]; })()`);
    check(sx[0] > 0 && sx[1] > 0, tag + 'the block scrolls both ways ' + JSON.stringify(sx));
    if (o.shot) { await ev(`document.querySelector('#mrt').scrollIntoView({block: 'start'})`); await sleep(200); await o.shot(`7561-mrdetails-${width}.png`); }
  }, touch);

  if (await run(412, true) === true) { console.log('p7561_mrdetails_ui: firefox part skipped'); }
  else await run(1280, false);

  console.log(`p7561_mrdetails_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
