// kalmido-suite: fresh
// #7399 UI test: on a computer a click on a client in the clients list swaps only the card. The list column, its search field
// and the bar stay the same nodes and keep their scroll position; the next client's card comes in one draw once its data is
// there (the card on screen stays dimmed meanwhile, never "Loading…"); at most two draws of the page per click (before: the
// path line above the page shifted the morph and replaced the whole page, then every loaded part drew it again: 8-10 draws).
// Coming back to a client seen before does not move the list to the place it had then (viewmem.js: one view).
// Firefox with a mouse at 1280 and 820 px, own container, invented names only.
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7399_client_open_ui', check, shots: 'P7399_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

// in the page: mark the nodes, count the draws of #view and watch for a "Loading…" card
const ARM = `(() => {
  const v = document.querySelector('#view'), lw = v.querySelector('.ctlistw');
  const R = window.__p7399 = {lw, q: v.querySelector('#mscl-q'), bar: v.querySelector('.ctbar'), st: lw.scrollTop, draws: 0, loading: false, ld0: [...LD_DONE]};
  if (!window.__p7399set) { window.__p7399set = true; const s0 = window.setHtml; window.setHtml = function (el, html) { if (el && el.id === 'view' && window.__p7399) window.__p7399.draws++, (window.__p7399.st8 = window.__p7399.st8 || []).push((new Error().stack || '').split(String.fromCharCode(10)).slice(4, 14).map(x => x.split('@')[0]).join('<')); return s0.apply(this, arguments); }; }
  R.obs = new MutationObserver(() => { const c = v.querySelector('.ctcard.ctnone'); if (c && /Loading/.test(c.textContent || '')) R.loading = true; });
  R.obs.observe(v, {childList: true, subtree: true, characterData: true});
  return 1;
})()`;
const RESULT = `(() => { const R = window.__p7399, v = document.querySelector('#view'); R.obs.disconnect();
  return {lw: v.querySelector('.ctlistw') === R.lw, q: v.querySelector('#mscl-q') === R.q, bar: v.querySelector('.ctbar') === R.bar,
    st0: Math.round(R.st), st8: R.st8, st: Math.round(v.querySelector('.ctlistw').scrollTop), draws: R.draws, loading: R.loading, ld: [...LD_DONE].filter(x => !R.ld0.includes(x))}; })()`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  await firefox(async ({cmd, ev, nav, ctx, until}) => {
    const wait = s => until(() => ev(s));
    await nav(B + 'static/icon.svg');
    const post = (u, b) => ev(`fetch(${JSON.stringify(u)}, {method: 'POST', headers: ${JSON.stringify(H)}, body: ${JSON.stringify(JSON.stringify(b))}}).then(r => r.status)`);
    check(await post('/api/auth/login', {username: 'alice', password: 'password123'}) === 200, 'login');
    await post('/api/admin/setup', {lang: 'en', collab_all: true, time_all: true, modules: ['office', 'comments']});
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: ${JSON.stringify(H)}, body: JSON.stringify({lang: 'en', tour: 'done', features: 'comments,collab,contacts,office,clients,time'})}).then(() => 1)`);
    const ids = [];
    for (let i = 1; i <= 60; i++) ids.push(await ev(`fetch('/api/clients', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({name: 'Kunde ${String(i).padStart(2, '0')} Werkstatt', email: 'k${i}@example.com'})}).then(r => r.json()).then(j => j.id)`));
    check(ids.every(x => x > 0), '60 clients: ' + JSON.stringify(ids.slice(0, 3)));
    if (!ids.every(x => x > 0)) console.log(await ev(`fetch('/api/clients', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({name: 'Probe'})}).then(r => r.text())`));
    for (const width of [1280, 1024]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width, height: 800}});
      await nav(B + '#clients'); await wait(`!!S.booted && document.querySelectorAll('#view .ctrow[data-clopen]').length === 60`);
      check(await ev(`!lsd_one()`), `${width}: list and card side by side`);
      // once per session the view builder's standard arrives (wgStdLoad: an admin's "Make it the default" button) and draws
      // the view once: not part of opening a client, so one card is opened before the counting starts
      await ev(`(() => { location.hash = 'client/${ids[59]}'; return 1; })()`);
      await wait(`(document.querySelector('#view #mscl-h')?.textContent || '').startsWith('Kunde 60') && !MSC.opening`); await sleep(800);
      await ev(`(() => { location.hash = 'clients'; return 1; })()`); await wait(`!!document.querySelector('#view .ctcard.ctpick')`);
      const open = async (n, scroll) => {
        if (scroll != null) { await ev(`(() => { const l = document.querySelector('#view .ctlistw'); l.scrollTop = ${scroll}; return 1; })()`); await sleep(400); }
        await ev(ARM);
        await ev(`(() => { const b = document.querySelector('#view .ctrow[data-clopen="${ids[n]}"]'); b.click(); return 1; })()`);
        await wait(`(document.querySelector('#view #mscl-h')?.textContent || '').startsWith('Kunde ${String(n + 1).padStart(2, '0')}') && !document.querySelector('#view .ctwait') && !CLV.loading && !MSC.opening`);
        await sleep(500);  // a late draw would count too
        return ev(RESULT);
      };
      let r = await open(39, 900);
      check(r.st0 > 0, `${width}: the list is scrolled before the click (${r.st0})`);
      check(r.lw && r.q && r.bar, `${width}: list -> client: list, search and bar stay the same nodes ${JSON.stringify(r)}`);
      check(Math.abs(r.st - r.st0) <= 1, `${width}: list -> client: the list keeps its scroll position ${r.st0} -> ${r.st}`);
      check(r.draws <= 2, `${width}: list -> client: at most two draws, were ${r.draws} ${JSON.stringify(r.st8)}`);
      check(!r.loading, `${width}: list -> client: the card never shows "Loading…"`);
      r = await open(44, null);
      check(r.lw && r.q && r.bar, `${width}: client -> client: list, search and bar stay the same nodes ${JSON.stringify(r)}`);
      check(Math.abs(r.st - r.st0) <= 1, `${width}: client -> client: the list keeps its scroll position ${r.st0} -> ${r.st}`);
      check(r.draws <= 2, `${width}: client -> client: at most two draws, were ${r.draws} ${JSON.stringify(r.st8)}`);
      check(!r.loading, `${width}: client -> client: the card stays (dimmed) instead of "Loading…"`);
      check(await ev(`document.querySelector('#view .ctrow[data-clopen="${ids[44]}"]').classList.contains('on')`), `${width}: the clicked row is marked`);
      // back to the client seen before, the list scrolled elsewhere meanwhile: it stays where the person put it
      r = await open(39, 300);
      check(Math.abs(r.st - r.st0) <= 1, `${width}: a client seen before: the list stays where it is ${r.st0} -> ${r.st}`);
      check(r.lw && r.draws <= 2, `${width}: a client seen before: same list node, at most two draws ${JSON.stringify(r)}`);
    }
  });
  console.log(`p7399_client_open_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
