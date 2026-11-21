// kalmido-suite: fresh
// Package 2.1453.0 (#7390) UI test (regression): a tab switch in the office's Invoices (Invoices -> Credit notes) keeps the page.
// Before: the tap emptied the list, the big loading block stood in its place, the page shrank and the scroll position fell to
// the top, then the list was drawn a second time. Now (render.js tabh_keep / tabh_arm / tabh_held): while the new tab's list
// loads, the head and the tab row stay the same nodes, the scroll position stays, the last tab's rows wait dimmed (.tabheld) and
// no loading block is in the page; when the list is there it stands alone. Firefox at a tablet's (820 px, the tab button) and a
// phone's width (390 px, the kind's address as its link in the menu row sets it, and Back). The list's request is held back
// 1.5 s in the page, so the in-between state can be seen. #7729: the held rows also keep their place on the page (the search /
// button line above them stays the last tab's until the new list is there). Own container (start.sh), invented data only.
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
// #7729 (diagnosis, stays): what stands above the first row (each box between the scroller and the row: the boxes before it,
// their height) and every change of the scroll position after the mark - who set it (the first frames of the stack) or the
// browser itself (a scroll event without a set: its own anchoring). A FAIL line of the scroll check names both.
const ABOVE = `window.__above = () => { const sc = window.__sc, r0 = sc.querySelector('.ofdrow'); if (!r0) return null; const o = {row: Math.round(r0.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop)};
  for (let n = r0; n && n !== sc; n = n.parentElement) for (let x = n.previousElementSibling; x; x = x.previousElementSibling) { const h = Math.round(x.getBoundingClientRect().height); if (h) o[(x.className || x.nodeName).toString().split(' ').slice(0, 2).join('.')] = h; }
  return o; }`;
const TRACE = `(() => { const sc = window.__sc, d = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop'); window.__st = [];
  const at = () => (new Error().stack || '').split('\\n').slice(2, 5).map(l => (l.match(/^([^@]*)@.*?([\\w.]+\\.js):(\\d+)/) || []).slice(1).join(':')).join('<');
  Object.defineProperty(sc, 'scrollTop', {configurable: true, get() { return d.get.call(this); }, set(v) { window.__st.push('set ' + Math.round(v) + ' ' + at()); d.set.call(this, v); }});
  let last = sc.scrollTop; sc.addEventListener('scroll', () => { const t = Math.round(d.get.call(sc)); if (t !== last) window.__st.push('scroll ' + last + '>' + t); last = t; });
  window.__before = window.__above(); return 1; })()`;
// the scrolling box of the office's body, the marks on the nodes that must stay
const MARK = `(() => { const b = document.querySelector('.office .ofcbody'), sc = kr_scroller(b), kinds = document.querySelector('.ofdkinds'), q = document.querySelector('#ofd-q');
  sc.scrollTop = 600; window.__sc = sc; for (const [n, k] of [[document.querySelector('.ofchead'), 'h'], [kinds, 'k'], [q, 'q']]) if (n) n.__keep = k;
  return {top: sc.scrollTop, kinds: !!kinds, q: !!q}; })()`;
const MID = `(() => { const sc = window.__sc; return {top: sc.scrollTop, big: !!document.querySelector('.office .ofcbody .eload.es-big'), seenBig: window.__seenBig,
  held: document.querySelectorAll('.office .tabheld .ofdrow').length, head: document.querySelector('.ofchead')?.__keep === 'h',
  kinds: document.querySelector('.ofdkinds')?.__keep === 'k', q: document.querySelector('#ofd-q')?.__keep === 'q', kind: OFD.kind, above: window.__above?.(), before: window.__before, trace: window.__st}; })()`;

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
      await ev(ABOVE + ', 1'); await ev(TRACE);
      if (how === 'tab') await ev(`document.querySelector('[data-ofd="kind"][data-kind="credit"]').click(), 1`);
      else await ev(`(location.hash = '#office/invoices/credit', 1)`);  // the phone: the kind's link in the menu row
      check(await fu(`OFD.kind === 'credit' && !!document.querySelector('.office .tabheld')`, {timeout: 5000}), `${tag}: the switch shows the last tab's rows dimmed`);
      const a = await ev(MID);
      check(a && a.top === m.top, `#7390 ${tag}: the scroll position stays while the new list loads ${JSON.stringify(a)}`);
      // #7729: nothing above the held rows changes height at the switch (the new tab's search / button line had other buttons:
      // 820 px 148 -> 96 px, the rows moved 52 px under the finger; CI 390 px: the scroll position went 600 -> 666)
      check(a && a.above && a.before && a.above.row === a.before.row, `#7729 ${tag}: the held rows stay where they were on the page ${JSON.stringify({above: a?.above, before: a?.before, trace: a?.trace})}`);
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
