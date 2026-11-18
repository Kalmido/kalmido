// 2.1381.0 (#6946) UI test: typing in a chat box beside a big page lays out nothing but the box.
// kalmido-suite: fresh
// Real Firefox (WebDriver BiDi, mouse), 1600 x 1000 (the chat panel docked), a project with 300 rows in the view:
// - fall-back test: real keys into the agent chat's box (#chat-in): autosize() neither reads its height (a forced layout of the
//   page per key) nor writes its style; the box sizes itself by CSS (field-sizing: content, app.css) - red without the fix
//   (the old autosize wrote "auto" + a height and read scrollHeight on every key)
// - usable: the box grows with more lines, stops at its max height (scrolls inside), shrinks back after sending / clearing;
//   the edit box of a message (.ach-edit) sizes the same way
// - the fallback for boxes outside the chat (and browsers without field-sizing): a growing text that still fits writes no
//   style (no "auto" round per key), a longer one grows the box, a shorter one shrinks it again
// freelancer-matrix: n/a (no route; the chat box is the same without an organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21381_c_chattype_ui', check, shots: 'P21381C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (process.env.P21381C_NOSTART !== '1') execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return Array.isArray(j) ? j : {...j, http: r.status}; };

// in the page: the box's height reads (scrollHeight / offsetHeight / clientHeight on the box itself) and its style changes
const SPY = sel => `(() => { const ta = document.querySelector('${sel}'); if (!ta) return 0;
  const S = window.__spy = {reads: 0, styles: 0};
  for (const k of ['scrollHeight', 'offsetHeight', 'clientHeight']) { const d = Object.getOwnPropertyDescriptor(Element.prototype, k) || Object.getOwnPropertyDescriptor(HTMLElement.prototype, k);
    Object.defineProperty(ta, k, {configurable: true, get() { S.reads++; return d.get.call(this); }}); }
  window.__mo = new MutationObserver(l => { S.styles += l.length; }); window.__mo.observe(ta, {attributes: true, attributeFilter: ['style']});
  return 1; })()`;
const UNSPY = sel => `(() => { const ta = document.querySelector('${sel}'); window.__mo?.disconnect(); for (const k of ['scrollHeight', 'offsetHeight', 'clientHeight']) delete ta[k]; return window.__spy; })()`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Example', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,agents'});
  const AG = (await call(CA, 'POST', '/api/admin/agents', {scopes: ['write'], username: 'claude', display_name: 'Claude'})).id;
  check(AG, 'setup: an agent');
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Many rows'})).id;
  let n = 0;
  for (let i = 0; i < 300; i += 25) n += (await Promise.all(Array.from({length: 25}, (_, j) => call(CA, 'POST', '/api/tasks', {title: `Row ${i + j + 1} follow up with the client about the draft`, list_id: L})))).filter(t => t.id).length;
  check(n === 300, 'setup: 300 tasks ' + n);

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1600, height: 1000}});
    await nav(B + 'static/icon.svg');
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(() => 1)`);
    const ready = async (expr, k = 80) => { for (let i = 0; i < k; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
    await nav(B + '#l/' + L);
    check(await ready(`document.querySelectorAll('#view .trow[data-id]').length >= 300`), 'the project shows its 300 rows');
    // the agent list comes with the app's start: opened again until the box is there
    check(await ready(`(() => { if (document.querySelector('#achat #chat-in')) return true; if (typeof chatOpen === 'function' && (S.agents || []).some(a => a.id === ${AG})) chatOpen(${AG}); return false; })()`), 'the chat panel is open beside the page');
    check(await ev(`document.body.classList.contains('chat-open')`), 'the chat panel is docked (wide window)');
    const fs = await ev(`CSS.supports('field-sizing', 'content')`);
    check(fs, 'this Firefox sizes boxes by CSS (field-sizing: content) - the fall-back test needs it');
    check(await ev(`getComputedStyle(document.querySelector('#chat-in')).fieldSizing === 'content'`), 'the chat box is sized by CSS');
    const H0 = await ev(`document.querySelector('#chat-in').getBoundingClientRect().height`);

    // ---- fall-back test: real keys, no height read / style write of the box by the script
    await ev(`(() => { const t = document.querySelector('#chat-in'); t.focus(); t.value = ''; return 1; })()`);
    await ev(SPY('#chat-in'));
    const txt = 'the quick brown fox jumps over the lazy dog';
    await cmd('input.performActions', {context: ctx, actions: [{type: 'key', id: 'k', actions: [...txt].flatMap(c => [{type: 'keyDown', value: c}, {type: 'keyUp', value: c}])}]});
    await cmd('input.releaseActions', {context: ctx});
    await sleep(300);
    const sp = await ev(UNSPY('#chat-in'));
    check(await ev(`document.querySelector('#chat-in').value`) === txt, 'the typed text is in the box');
    check(sp && sp.reads === 0 && sp.styles === 0, `typing reads no height of the box and writes no style (no forced layout per key) ${JSON.stringify(sp)}`);

    // ---- usable: grows with lines, stops at the max height and scrolls, shrinks back when cleared
    const lines = k => `(() => { const t = document.querySelector('#chat-in'); t.value = Array.from({length: ${k}}, (_, i) => 'line ' + (i + 1)).join('\\n'); t.dispatchEvent(new InputEvent('input', {bubbles: true})); return new Promise(r => requestAnimationFrame(() => r(1))); })()`;
    const box = `(() => { const t = document.querySelector('#chat-in'); return {h: t.getBoundingClientRect().height, sh: t.scrollHeight, ch: t.clientHeight, max: parseFloat(getComputedStyle(t).maxHeight)}; })()`;
    await ev(lines(4));
    const b4 = await ev(box);
    check(b4.h > H0 + 20 && b4.sh <= b4.ch + 1, `four lines: the box grows and shows them all (${H0} -> ${JSON.stringify(b4)})`);
    await ev(lines(30));
    const b30 = await ev(box);
    check(Math.abs(b30.h - b30.max) <= 1 && b30.sh > b30.ch, `30 lines: the box stops at its max height and scrolls inside ${JSON.stringify(b30)}`);
    await ev(`(() => { const t = document.querySelector('#chat-in'); t.value = ''; t.dispatchEvent(new InputEvent('input', {bubbles: true})); return new Promise(r => requestAnimationFrame(() => r(1))); })()`);
    const b0 = await ev(box);
    check(Math.abs(b0.h - H0) <= 1, `cleared: the box is one line again (${H0} / ${b0.h})`);
    await shot('p21381c-chat.png');

    // ---- the edit box of a message (.cbub.tcedit textarea) is sized by CSS too
    check(await ev(`(() => { const d = document.createElement('div'); d.className = 'cbub tcedit'; d.innerHTML = '<textarea class="ach-edit" rows="2"></textarea>'; document.querySelector('#chat-msgs').appendChild(d); const t = d.firstChild; t.style.height = '200px'; autosize(t); const r = getComputedStyle(t).fieldSizing === 'content' && t.style.height === '200px'; d.remove(); return r; })()`),
      'the edit box of a message is sized by CSS; a height dragged by hand stays');

    // ---- the fallback (boxes outside the chat, browsers without field-sizing): no "auto" round while the text grows and fits
    const fb = await ev(`(() => { const t = document.createElement('textarea'); t.style.cssText = 'width:20rem;font:16px/1.5 sans-serif;padding:4px;border:1px solid;box-sizing:border-box;overflow:hidden'; t.rows = 1; document.body.appendChild(t);
      autosize(t); const h0 = t.getBoundingClientRect().height; let st = 0; const mo = new MutationObserver(l => { st += l.length; }); mo.observe(t, {attributes: true, attributeFilter: ['style']});
      for (const c of 'abcdef') { t.value += c; autosize(t); }
      const grewFits = st + mo.takeRecords().length;  // the records are delivered later: taken here
      t.value += '\\nsecond line\\nthird line'; autosize(t); const h3 = t.getBoundingClientRect().height, fit3 = t.scrollHeight <= t.clientHeight + 1;
      t.value = 'x'; autosize(t); const h1 = t.getBoundingClientRect().height; mo.disconnect(); t.remove();
      return {grewFits, h0, h3, fit3, h1}; })()`);
    check(fb.grewFits === 0, 'fallback: a growing text that still fits writes no style ' + JSON.stringify(fb));
    check(fb.h3 > fb.h0 + 20 && fb.fit3, 'fallback: more lines grow the box ' + JSON.stringify(fb));
    check(Math.abs(fb.h1 - fb.h0) <= 1, 'fallback: a shorter text shrinks it again ' + JSON.stringify(fb));
  });

  console.log(`p21381_c_chattype_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack); process.exit(1); });
