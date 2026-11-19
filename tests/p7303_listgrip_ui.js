// #7303 #7304 UI test: the width of a list beside its content in the page, by the one grip (grip.js grip_col with place,
// render.js gcol_html / gcol_sync). Where sidebar B is missing (an own window /?mini=1): the team chat's conversations
// (tc-list), the file store's areas (ab-list), notes beside an open note (nt-list), knowledge beside an open page (wk-list).
// kalmido-suite: fresh
// Firefox 1280 x 800 (mouse), a person without an organisation (freelancer parity). Per place:
// - the grip is shown on the list's right edge (the middle of the gap), a focusable separator with a name
// - dragging it to the right makes the list wider, the content keeps the rest, the grip stays on the list's edge
//   (the size is the handle's; an own window stores no UI state, miniwin.js #5358 - the storage itself is p21437's); End = as
//   wide as it goes, the content beside it keeps 20 rem (no fixed cap, produkt-regeln "Handles"); a double-click = the standard width
// Notes at 1700 px (the sheet layout of #4808): the block counts with the dragged width (it grows by the same amount).
// Firefox 390 x 844 touch: an open note, the team chat - no grip to see.
// Invented names only.
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7303_listgrip_ui', check, shots: 'P7303_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const login = async user => { const r = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: user, password: 'password123'})}); return (r.headers.get('set-cookie') || '').split(';')[0]; };
const FEATS = 'cal,collab,comments,team,files,docs,wiki,contacts';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call(ACK, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments', 'collab', 'team']});
  await call(ACK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEATS});
  const st = await call(ACK, 'GET', '/api/state');
  check(!(st.me?.workspaces || []).length, 'alice has no organisation (freelancer parity) ' + JSON.stringify(st.me?.workspaces));
  const L = (await call(ACK, 'POST', '/api/lists', {name: 'Example project'})).id;
  const NOTE = (await call(ACK, 'POST', `/api/lists/${L}/notes`, {title: 'A note with a rather long title that gets cut in a narrow list', body: 'Text.'})).id;
  const WP = (await call(ACK, 'POST', '/api/wiki/pages', {space: 'private', path: 'A knowledge page with a rather long title that gets cut', body: 'Read me.'})).id;
  check(L && NOTE && WP, `setup: a list with a note, a knowledge page ${L} ${NOTE} ${WP}`);

  const signIn = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  };
  // the grip of KEY, its list (the element before it) and its box
  const box = key => `(() => { const g = document.querySelector('#view [data-gcol="${key}"]'); if (!g || g.hidden || !g.getClientRects().length || !g._grip) return null;
    const p = g.parentElement, l = g.previousElementSibling, a = g.getBoundingClientRect(), lr = l.getBoundingClientRect(), pr = p.getBoundingClientRect(), gap = parseFloat(getComputedStyle(p).columnGap) || 0;
    return {x: a.left + a.width / 2, y: a.top + Math.min(120, a.height / 2), mid: Math.round(lr.right + gap / 2), lw: Math.round(lr.width), pw: p.clientWidth, bw: Math.round(pr.width),
      tab: g.tabIndex, role: g.getAttribute('role'), lbl: g.getAttribute('aria-label') || '', ls: localStorage.getItem('tasks.grip:${key}'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)}; })()`;
  const PLACES = [
    {key: 'tc-list', hash: '#team', open: null},
    {key: 'ab-list', hash: '#ablage', open: null},
    {key: 'nt-list', hash: `#notes/${L}`, open: `go('note/${NOTE}')`},
    {key: 'wk-list', hash: `#wiki/${WP}`, open: null}];

  await firefox(async o => {
    const {cmd, ev, ctx, nav, until, drag, shot} = o;
    check(await signIn(o) === 200, 'login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 800}});
    for (const P of PLACES) {
      const tag = P.key, url = B + '?mini=1' + P.hash;
      await nav(url);
      if (P.open) { await until(`typeof go === 'function' && !!document.querySelector('#view .ntlist')`, {timeout: 20000}); await ev(`(${P.open}, 1)`); }
      const b0 = await until(box(P.key), {timeout: 20000});
      check(b0 && b0.tab === 0 && b0.role === 'separator' && b0.lbl && Math.abs(b0.x - b0.mid) <= 6 && !b0.ls,
        `${tag}: the grip sits on the list's edge, focusable with a name ${JSON.stringify(b0)}`);
      await shot(`p7303-${tag}-before.png`);
      if (!b0) continue;
      const hit = await ev(`(() => { const e = document.elementFromPoint(${b0.x}, ${b0.y}); return e === document.querySelector('#view [data-gcol="${P.key}"]') ? 'grip' : e ? e.tagName + '.' + e.className : 'none'; })()`);
      check(hit === 'grip', `${tag}: the grip is the element under the pointer (${hit})`);
      await drag(b0.x, b0.y, 120, 0);
      const b1 = await until(`(() => { const b = ${box(P.key)}; return b && b.lw > ${b0.lw} + 80 ? b : null; })()`, {timeout: 5000});
      check(b1 && Math.abs(b1.lw - b0.lw - 120) <= 10 && Math.abs(b1.x - b1.mid) <= 6 && await ev(`document.querySelector('#view [data-gcol="${P.key}"]')._grip.get()`) > 0,
        `${tag}: dragged 120 px to the right: the list wider, the grip on its edge ${JSON.stringify([b0, b1])}`);
      // an own window keeps its UI state to itself (miniwin.js MW_GUARD, #5358): nothing stored for the main window
      check(b1 && !b1.ls, `${tag}: the own window stores nothing ${JSON.stringify(b1)}`);
      await shot(`p7303-${tag}-wider.png`);
      await ev(`(() => { const g = document.querySelector('#view [data-gcol="${P.key}"]'); g.focus(); g.dispatchEvent(new KeyboardEvent('keydown', {key: 'End', bubbles: true})); return 1; })()`);
      const b3 = await until(box(P.key), {timeout: 3000});
      const rest = await ev(`(() => { const t = getComputedStyle(document.querySelector('#view [data-gcol="${P.key}"]').parentElement).gridTemplateColumns.split(/\\s+/).map(parseFloat); return Math.round(t[1]); })()`);
      check(b3 && b3.lw > b0.lw + 100 && rest >= 20 * b3.rem - 1 && rest <= 20 * b3.rem + 6,
        `${tag}: End: as wide as it goes, the content keeps 20 rem (no fixed cap) ${JSON.stringify([b3, rest])}`);
      await ev(`(() => { document.querySelector('#view [data-gcol="${P.key}"]').dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); return 1; })()`);
      const b4 = await until(`(() => { const b = ${box(P.key)}; return b && Math.abs(b.lw - ${b0.lw}) <= 1 ? b : null; })()`, {timeout: 5000});
      check(!!b4 && await ev(`document.querySelector('#view [data-gcol="${P.key}"]')._grip.get() === null`), `${tag}: double-click: the standard width again ${JSON.stringify([b0, b4])}`);
    }
    // notes at 1700 px: the block (list + sheet) grows with the dragged list (#4808 counted a fixed 23rem)
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1800, height: 900}});
    await nav(B + `?mini=1#notes/${L}`);
    await until(`typeof go === 'function' && !!document.querySelector('#view .ntlist')`, {timeout: 20000});
    await ev(`(go('note/${NOTE}'), 1)`);
    const w0 = await until(box('nt-list'), {timeout: 20000});
    check(!!w0, `1800: the notes grip ${JSON.stringify(w0)}`);
    if (w0) {
      await drag(w0.x, w0.y, 100, 0);
      const w1 = await until(`(() => { const b = ${box('nt-list')}; return b && b.lw > ${w0.lw} + 60 ? b : null; })()`, {timeout: 5000});
      check(w1 && Math.abs((w1.bw - w0.bw) - (w1.lw - w0.lw)) <= 4, `1800: the notes block grows by the list's extra width ${JSON.stringify([w0, w1])}`);
      await shot('p7303-notes-1800.png');
    }
  });
  await firefox(async o => {
    const {cmd, ev, ctx, nav, until} = o, tag = '390 touch';
    check(await signIn(o) === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    const none = `(() => [...document.querySelectorAll('#view [data-gcol]')].every(g => g.hidden || !g.getClientRects().length || getComputedStyle(g).display === 'none'))()`;
    await nav(B + `#notes/${L}`);
    await until(`typeof go === 'function' && !!document.querySelector('#view .ntlist')`, {timeout: 20000});
    await ev(`(go('note/${NOTE}'), 1)`);
    check(await until(`!!document.querySelector('#view .ntedit')`, {timeout: 20000}), `${tag}: the note opens`);
    check(await ev(none), `${tag}: an open note, no grip`);
    await nav(B + '#team');
    check(await until(`!!document.querySelector('#view .tcview')`, {timeout: 20000}), `${tag}: the team chat`);
    check(await ev(none), `${tag}: the team chat, no grip`);
  }, true);
  console.log(`p7303_listgrip_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
