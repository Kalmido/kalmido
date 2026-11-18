// 2.1383.0 A (#7023) UI test, own container (start.sh), Firefox. Invented data only.
// kalmido-suite:
// The bell's section heads "For you" / "History" stand flush at the top of the list when it scrolls, full width and opaque:
// a point 2 px under the list's top edge and 2 px from its left / right edge hits the head, never a row under it (the finding:
// the list's padding and the head's margin let rows show above and beside it). History reaches the top and pushes For you away.
// Tablet window (884 x 1104, finger) and phone sheet (412 x 915).
// freelancer-matrix: n/a - nur Oberfläche (alice has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21383_a_bell_head_ui', check, shots: 'P21383A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  const call = async (method, url, body, ck = CA) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
  const ALL = 'collab,comments';
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('PATCH', '/api/settings', {features: ALL, lang: 'en', tour: 'done'});
  const ME = (await call('GET', '/api/state')).me.id;
  const BOB = (await call('POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123'})).id;
  const CB = await login('bob');
  await call('PATCH', '/api/settings', {features: ALL, tour: 'done'}, CB);
  const L = (await call('POST', '/api/lists', {name: 'Website', kind: 'project'})).id;
  await call('PUT', `/api/lists/${L}/members`, {user_id: BOB, role: 'edit'});
  // 14 mentions (For you, one bundle per task) + 8 comments on watched tasks (History)
  for (let i = 1; i <= 14; i++) {
    const t = (await call('POST', '/api/tasks', {title: `Shot list part ${i}`, list_id: L})).id;
    await call('POST', `/api/tasks/${t}/comments`, {body: `<@${ME}> please check part ${i}`}, CB);
  }
  for (let i = 1; i <= 8; i++) {
    const t = (await call('POST', '/api/tasks', {title: `Bob's draft ${i}`, list_id: L}, CB)).id;
    await call('POST', `/api/tasks/${t}/watchers`, {});
    await call('POST', `/api/tasks/${t}/comments`, {body: `Draft ${i} is in`}, CB);
  }
  const srv = await call('GET', '/api/news');
  check(srv.unread_me >= 14, 'setup: 14 entries for alice ' + srv.unread_me);

  // the head that stands at the list's top (2 px under it, 2 px from each side): which element is there
  const PROBE = `(() => { const l = document.querySelector('#pop .bplist'); if (!l) return null; const r = l.getBoundingClientRect(), w = l.clientWidth;
    const at = (x, y) => { const e = document.elementFromPoint(x, y); const h = e && e.closest('.nsh'); return h ? (h.closest('.nhist') ? 'hist' : 'me') : (e ? (e.closest('.ngroup') ? 'row' : e.className || e.tagName) : 'none'); };
    return {top: Math.round(r.top), st: Math.round(l.scrollTop), sh: l.scrollHeight, ch: l.clientHeight, left: at(r.left + 2, r.top + 2), mid: at(r.left + w / 2, r.top + 2), right: at(r.left + w - 2, r.top + 2), under: at(r.left + 2, r.top + 4)}; })()`;
  for (const [W, Hh] of [[884, 1104], [412, 915]]) {
    await firefox(async ({cmd, ev, ctx, nav, shot, until, idle}) => {
      const tag = `${W}: `;
      await nav(B + 'static/icon.svg');
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Hh}});
      await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.newsHist', 'true'); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, tag + 'login');
      await nav(B + '#today'); await until(`!!window.S && !!S.booted && !!document.querySelector('[data-act="bell-pop"]')`); await idle({quiet: 300, timeout: 8000});
      await ev(`(() => { document.querySelector('[data-act="bell-pop"]').click(); return 1; })()`);
      check(await until(`document.querySelectorAll('#pop .bpop .ngroup').length >= 20 && !!document.querySelector('#pop .bpop .nhist.open')`), tag + 'the bell shows For you and the open History');
      await idle({quiet: 300, timeout: 5000});
      const p0 = await ev(PROBE);
      check(p0 && p0.sh > p0.ch + 400, tag + 'the list scrolls ' + JSON.stringify(p0));
      // scrolled 200 px: For you's head covers the top edge on the whole width
      await ev(`(() => { const l = document.querySelector('#pop .bplist'); l.scrollTop = 200; l.dispatchEvent(new Event('scroll')); return 1; })()`);
      await sleep(200);
      const p1 = await ev(PROBE);
      check(p1 && p1.left === 'me' && p1.mid === 'me' && p1.right === 'me' && p1.under === 'me', tag + 'scrolled: For you covers the top edge, no row above or beside it ' + JSON.stringify(p1));
      const hr = await ev(`(() => { const h = document.querySelector('#pop .nsect.me .nsh'), l = document.querySelector('#pop .bplist'), a = h.getBoundingClientRect(), b = l.getBoundingClientRect();
        return {ht: Math.round(a.top - b.top), hl: Math.round(a.left - b.left), hr: Math.round(b.left + l.clientWidth - a.right), bg: getComputedStyle(h).backgroundColor}; })()`);
      check(hr.ht === 0 && hr.hl <= 0 && hr.hr <= 0 && !/rgba\(.*, 0\)|transparent/.test(hr.bg), tag + 'For you: flush at the top, full width, opaque ' + JSON.stringify(hr));
      await shot(`p21383a-glocke-fuer-dich-${W}.png`);
      // History reaches the top: it stands there alone, For you is pushed away
      await ev(`(() => { const l = document.querySelector('#pop .bplist'), h = document.querySelector('#pop .nhist .nsh'); l.scrollTop += h.getBoundingClientRect().top - l.getBoundingClientRect().top + 60; l.dispatchEvent(new Event('scroll')); return 1; })()`);
      await sleep(200);
      const p2 = await ev(PROBE);
      check(p2 && p2.left === 'hist' && p2.mid === 'hist' && p2.right === 'hist' && p2.under === 'hist', tag + 'History at the top, flush and full width ' + JSON.stringify(p2));
      const me = await ev(`(() => { const h = document.querySelector('#pop .nsect.me .nsh'), l = document.querySelector('#pop .bplist'); return Math.round(h.getBoundingClientRect().bottom - l.getBoundingClientRect().top); })()`);
      check(me <= 0, tag + 'For you has been pushed away ' + me);
      await shot(`p21383a-glocke-verlauf-${W}.png`);
      // the history head still folds (the button works through the sticky head)
      await ev(`(() => { document.querySelector('#pop .nhisth').click(); return 1; })()`);
      check(await until(`!document.querySelector('#pop .nhist.open')`), tag + 'History folds from its head');
    }, true);
  }

  console.log(`p21383_a_bell_head_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
