// kalmido-suite: fresh
// Package 2.1453.0 (#7390) UI test (regression): a tab switch in the office's Invoices (Invoices -> Credit notes) keeps the page.
// Before: the tap emptied the list, the big loading block stood in its place, the page shrank and the scroll position fell to
// the top, then the list was drawn a second time. Now (render.js tabh_keep / tabh_arm / tabh_held): while the new tab's list
// loads, the head and the tab row stay the same nodes, the scroll position stays, the last tab's rows wait dimmed (.tabheld) and
// no loading block is in the page; when the list is there it stands alone. Firefox at a tablet's (820 px, the tab button) and a
// phone's width (390 px, the kind's address as its link in the menu row sets it, and Back). The list's request is held back
// 1.5 s in the page, so the in-between state can be seen. Own container (start.sh), invented data only.
// freelancer-matrix: n/a - nur Oberfläche, keine neue Route (die Person hier hat keine Organisation)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21453_7390_officetabs_ui', check, shots: 'P21453_7390_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), http: r.status};
  }
};
const FEAT = 'cal,comments,collab,office,clients,files,docs';

// in the page: hold the list request of one kind back (the in-between state of a slow line), count the big loading blocks
const SLOW = kind => `(() => { const f0 = window.fetch; window.__seenBig = 0;
  window.fetch = function (u, o) { const s = String(u && u.url || u); if (/\\/api\\/office\\/docs\\?kind=${kind}\\b/.test(s)) return new Promise(r => setTimeout(r, 1500)).then(() => f0.call(this, u, o)); return f0.apply(this, arguments); };
  new MutationObserver(() => { if (document.querySelector('.office .ofcbody .eload.es-big')) window.__seenBig++; }).observe(document.body, {childList: true, subtree: true});
  return 1; })()`;
// the scrolling box of the office's body, the marks on the nodes that must stay
const MARK = `(() => { const b = document.querySelector('.office .ofcbody'), sc = kr_scroller(b), kinds = document.querySelector('.ofdkinds'), q = document.querySelector('#ofd-q');
  sc.scrollTop = 600; window.__sc = sc; for (const [n, k] of [[document.querySelector('.ofchead'), 'h'], [kinds, 'k'], [q, 'q']]) if (n) n.__keep = k;
  return {top: sc.scrollTop, kinds: !!kinds, q: !!q}; })()`;
const MID = `(() => { const sc = window.__sc; return {top: sc.scrollTop, big: !!document.querySelector('.office .ofcbody .eload.es-big'), seenBig: window.__seenBig,
  held: document.querySelectorAll('.office .tabheld .ofdrow').length, head: document.querySelector('.ofchead')?.__keep === 'h',
  kinds: document.querySelector('.ofdkinds')?.__keep === 'k', q: document.querySelector('#ofd-q')?.__keep === 'q', kind: OFD.kind}; })()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ids = [];
  for (let i = 0; i < 40; i++) ids.push((await call('POST', '/api/office/docs', {kind: 'invoice', items: [{title: `Shooting day ${i}`, qty: 1, rate: 100 + i}]})).id);
  check(ids.every(Boolean), 'setup: 40 invoice drafts');

  for (const [w, h, touch, how] of [[820, 1000, true, 'tab'], [390, 760, true, 'link']]) {
    await firefox(async ({cmd, ev, ctx, nav, until: fu, shot}) => {
      const tag = `${w}px`;
      await nav(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.tour', '"done"'); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, `${tag}: login`);
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
      await nav(B + '#office/invoices/invoice');
      check(await fu(`document.querySelectorAll('.office .ofdrow').length >= 40`, {timeout: 20000}), `${tag}: the invoices are listed`);
      await ev(SLOW('credit'));
      const m = await ev(MARK);
      check(m && m.top > 100, `${tag}: scrolled down the list ${JSON.stringify(m)}`);
      if (how === 'tab') await ev(`document.querySelector('[data-ofd="kind"][data-kind="credit"]').click(), 1`);
      else await ev(`(location.hash = '#office/invoices/credit', 1)`);  // the phone: the kind's link in the menu row
      check(await fu(`OFD.kind === 'credit' && !!document.querySelector('.office .tabheld')`, {timeout: 5000}), `${tag}: the switch shows the last tab's rows dimmed`);
      const a = await ev(MID);
      check(a && a.top === m.top, `#7390 ${tag}: the scroll position stays while the new list loads ${JSON.stringify(a)}`);
      check(a && !a.big && a.seenBig === 0, `#7390 ${tag}: no big loading block in the page`);
      check(a && a.held >= 40, `#7390 ${tag}: the rows wait in place (dimmed)`);
      check(a && a.head && (!m.kinds || a.kinds) && (!m.q || a.q), `#7390 ${tag}: head, tab row and search line are the same nodes`);
      check(await fu(`!document.querySelector('.office .tabheld') && !document.querySelector('.office .ofdrow') && /credit/i.test(document.querySelector('.office .ofcbody').textContent)`, {timeout: 8000}),
        `#7390 ${tag}: the credit notes' list (empty) stands alone when it is there`);
      const b = await ev(`({seenBig: window.__seenBig, sel: document.querySelector('[data-ofd="kind"][aria-selected="true"]')?.dataset.kind || OFD.kind, hash: location.hash})`);
      check(b && b.seenBig === 0 && b.sel === 'credit' && /\/credit$/.test(b.hash), `#7390 ${tag}: never a loading block, the tab and the address say Credit notes ${JSON.stringify(b)}`);
      await shot(`p21453-7390-${w}.png`);
      // Back: a history step per tab (#3004) - back to the invoices, used as before
      await ev(`(history.back(), 1)`);
      check(await fu(`OFD.kind === 'invoice' && document.querySelectorAll('.office .ofdrow').length >= 40 && !document.querySelector('.office .tabheld')`, {timeout: 8000}), `${tag}: Back returns to the invoices`);
      await ev(`document.querySelector('.office .ofdrow[data-ofd="open"]').click(), 1`);
      check(await fu(`!!S.route.id`, {timeout: 8000}), `${tag}: a row of the list opens its invoice`);
    }, touch);
  }

  console.log(`p21453_7390_officetabs_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
