// 2.1383.0 A (#7060) UI test, own container (start.sh), Firefox. Invented data only.
// kalmido-suite:
// "My tasks" with own sections: the floating "+" button (#fab) never covers a control at the end of the list ("New section",
// the last row) - the list ends with room of the button's height + its bottom offset. Short and long list, 320 / 460 (phone,
// tab bar) and 840 (touch tablet, no tab bar), each scrolled to the end: no control under the button, "New section" can be
// clicked where it stands and opens its dialog.
// freelancer-matrix: Meine Aufgaben (frida has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21383_a_fab_room_ui', check, shots: 'P21383A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'setup: frida is in no organisation');
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Home'})).id;
  const T = [];
  for (const n of ['Water the plants', 'Book a trip', 'Call the bank']) T.push((await call(CF, 'POST', '/api/tasks', {title: n, list_id: L})).id);
  check(T.every(Boolean), 'setup: three tasks');

  // every control in #view that the button's box overlaps (a 1 px touch counts), the view scrolled to its end
  const COVER = `(() => { const f = document.querySelector('#fab'); if (!f || !f.getClientRects().length || getComputedStyle(f).display === 'none') return {fab: null};
    const a = f.getBoundingClientRect(), hit = []; let low = -1e9;
    for (const e of document.querySelectorAll('#view button, #view a[href], #view input, #view [data-act], #view [data-mse-add], #view .trow[data-id]')) {
      if (!e.getClientRects().length) continue; const b = e.getBoundingClientRect(); if (b.width < 2 || b.height < 2) continue;
      const x = Math.min(a.right, b.right) - Math.max(a.left, b.left), y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      low = Math.max(low, b.bottom);
      if (x > 0 && y > 0) hit.push((e.className || e.tagName).toString().split(' ')[0] + ' ' + Math.round(y) + 'px'); }
    const v = document.querySelector('#view'); return {fab: {t: Math.round(a.top), b: Math.round(a.bottom), h: Math.round(a.height)}, gap: Math.round(a.top - low), st: Math.round(v.scrollTop), sh: v.scrollHeight, ch: v.clientHeight, hit}; })()`;
  for (const [W, Hh] of [[320, 568], [460, 800], [840, 1100]]) {
    await firefox(async ({cmd, ev, ctx, nav, shot, until, idle}) => {
      const tag = `${W}: `;
      await nav(B + 'static/icon.svg');
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Hh}});
      await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`) === 200, tag + 'login');
      const go = async () => { await nav(B + 'static/icon.svg'); await nav(B + '#assigned'); await until(`!!window.S && !!S.booted && !!document.querySelector('#view [data-mse-add]')`); await idle({quiet: 300, timeout: 8000}); };
      const toEnd = async () => { await ev(`(() => { const v = document.querySelector('#view'); v.scrollTop = v.scrollHeight; v.dispatchEvent(new Event('scroll')); return 1; })()`); await sleep(250); return ev(COVER); };
      const extra = [];
      for (const [k, n] of [['short', 0], ['long', 22]]) {
        for (let i = 1; i <= n; i++) extra.push((await call(CF, 'POST', '/api/tasks', {title: `Errand ${W} ${i}`, list_id: L})).id);
        await go();
        const c = await toEnd();
        console.log(tag + k + ' ' + JSON.stringify(c));
        if (W < 768) {  // the phone: the + button above the tab bar; a touch tablet (840) has no + button (fabOff: its own field)
          check(c.fab, `${tag}${k}: the + button is there ` + JSON.stringify(c));
          check(c.fab && c.hit.length === 0, `${tag}${k}: the + button covers no control at the end of the list ` + JSON.stringify(c));
          // the list ends with the button's height + its bottom offset + a clear gap of 1rem: the last control 16 px above it
          check(c.fab && c.gap >= 16, `${tag}${k}: a clear gap of 1rem between the last control and the + button ` + JSON.stringify(c));
        } else check(!c.fab || c.hit.length === 0, `${tag}${k}: nothing covered at the end of the list ` + JSON.stringify(c));
        await shot(`p21383a-fab-${W}-${k}.png`);
        // "New section" works where it stands: its middle is itself (not the button) and a click opens the dialog
        const mid = await ev(`(() => { const e = document.querySelector('#view [data-mse-add]'), b = e.getBoundingClientRect(); const h = document.elementFromPoint(b.left + b.width - 4, b.top + b.height / 2); return !!h && (h === e || e.contains(h)); })()`);
        check(mid, `${tag}${k}: "New section" is reachable at its right end`);
        await ev(`(() => { document.querySelector('#view [data-mse-add]').click(); return 1; })()`);
        check(await until(`!!document.querySelector('#cdlg-in')`), `${tag}${k}: "New section" opens its dialog`);
        await ev(`(() => { document.querySelector('[data-cd="no"]')?.click(); return 1; })()`);
        await until(`!document.querySelector('#cdlg-in')`);
        for (const id of extra.splice(0)) await call(CF, 'DELETE', `/api/tasks/${id}`);
      }
    }, true);
  }

  console.log(`p21383_a_fab_room_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
