// 2.1242.0 UI test part A (#6096 team chat: a calmer message line), own container
// kalmido-suite: fresh
// Firefox as a touch screen in phone width 360 px. A channel of an organisation: Bob wrote two lines, Alice one that she edited
// and Bob read. Checked on the screen:
// - smiley and "..." are not under every message: hidden until the message is tapped (a real tap), shown then, a second tap
//   hides them again; the closed message is lower than the opened one and its time line is one row;
// - "Read by 1" (two ticks) and "edited" sit in the same row as the time, never in an own row; the time has no title of the
//   same text;
// - a reaction shows at once while its request still waits, a refusal of the server puts it back;
// - the same as a person without an organisation (her own agent in her project's channel). Invented data only.
// freelancer-matrix: team - no new route (only the display of the team chat changes)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21242_a_chat_line_ui', check, shots: 'P21242A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21242A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'collab,comments';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob Member', password: 'password123', email: 'bob@example.com'});
  await call(CA, 'PUT', `/api/orgs/${org.id}/members`, {email: 'bob@example.com', role: 'member'});
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${org.id}`});
  const bob = (await call(CB, 'GET', '/api/state')).me;
  const room = await call(CA, 'POST', '/api/team/channels', {name: 'Film crew', org_id: org.id, open: false, members: [bob.id]});
  check(room.id > 0, 'a room ' + JSON.stringify(room).slice(0, 200));
  const b1 = await call(CB, 'POST', `/api/team/rooms/${room.id}/messages`, {body: 'Take one'});
  const b2 = await call(CB, 'POST', `/api/team/rooms/${room.id}/messages`, {body: 'Take two'});
  const a1 = await call(CA, 'POST', `/api/team/rooms/${room.id}/messages`, {body: 'Wrap'});
  check(b1.id > 0 && b2.id > 0 && a1.id > 0, 'three messages');
  check((await call(CA, 'PATCH', `/api/team/messages/${a1.id}`, {body: 'Wrap at six'})).http < 300, 'alice edited hers');
  check((await call(CB, 'POST', `/api/team/rooms/${room.id}/read`, {})).http < 300, 'bob read the conversation');
  const rx = async id => ((await call(CA, 'GET', `/api/team/rooms/${room.id}/messages`)).messages || []).find(m => m.id === id)?.reactions || [];

  // a person without an organisation: Frida, her own agent in her project = the project's channel; her edited message
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida has no organisation');
  const ag = await call(CF, 'POST', '/api/my/agents', {username: 'fridabot', display_name: "Frida's bot", scopes: ['read', 'comments']});
  const lst = await call(CF, 'POST', '/api/lists', {name: 'Short film'});
  check((await call(CF, 'PUT', `/api/lists/${lst.id}/members`, {user_id: ag.id, role: 'edit'})).http < 300, 'frida: the agent in her project');
  const fch = ((await call(CF, 'GET', '/api/team')).rooms || []).find(x => x.kind === 'list' && x.list_id === lst.id) || {};
  check(fch.id > 0, 'frida: the channel of her project');
  const fm = await call(CF, 'POST', `/api/team/rooms/${fch.id}/messages`, {body: 'Cut the second scene'});
  check(fm.id > 0 && (await call(CF, 'PATCH', `/api/team/messages/${fm.id}`, {body: 'Cut the third scene'})).http < 300, 'frida: her edited message');

  await firefox(async ({cmd, ev, nav: go, ctx, shot, until: wait}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 780}});
    const tap = async (x, y) => {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 't1', parameters: {pointerType: 'touch'}, actions: [{type: 'pointerMove', x: Math.round(x), y: Math.round(y)}, {type: 'pointerDown', button: 0}, {type: 'pause', duration: 60}, {type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
    };
    const signIn = async u => {
      await go(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`) === 200, `Firefox: login ${u}`);
    };
    // one message on the screen: its height, the meta line (height, the spread of its visible parts' middles), the smiley and
    // "..." (shown = wider than 4 px), the ticks / "edited" inside the line, the time's title
    const LINE = id => `(() => { const m = document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"]'); if (!m) return null;
      const q = m.querySelector(':scope > .cmeta'), vis = e => { const r = e?.getBoundingClientRect(); return !!r && r.width > 4 && r.height > 4; };
      const mids = q ? [...q.children].filter(vis).map(e => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; }) : [];
      const b = m.querySelector('.cbub')?.getBoundingClientRect();
      return {h: Math.round(m.getBoundingClientRect().height), bub: b ? Math.round(b.height) : 0, qh: q ? Math.round(q.getBoundingClientRect().height) : 0,
        spread: mids.length ? Math.round(Math.max(...mids) - Math.min(...mids)) : 0, parts: q ? [...q.children].filter(vis).map(e => e.className || e.tagName).join(',') : '',
        open: m.classList.contains('rxshow'), smile: vis(m.querySelector('.rxrow .rxtog')), dots: vis(m.querySelector('[data-act="tc-msg-menu"]')),
        quick: [...m.querySelectorAll('.rxrow .rx.rxq')].filter(vis).length, ticks: !!q?.querySelector('.trdline'), ticksOut: !!m.querySelector(':scope > .trdline'),
        edited: !!q?.querySelector('.cedited'), timeTitle: q?.querySelector('time')?.getAttribute('title'), mob: isMobile(), touch: isTouchUi()}; })()`;
    const bubAt = id => ev(`(() => { const b = document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] .cbub'); if (!b) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect(); return {x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2}; })()`);
    const chipAt = (id, e) => ev(`(() => { const c = document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] .rxrow .rx[data-e="${e}"]'); if (!c) return null; const r = c.getBoundingClientRect(); return r.width > 4 ? {x: r.left + r.width / 2, y: r.top + r.height / 2} : null; })()`);
    const pressed = (id, e) => `document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] .rxrow .rx[data-e="${e}"]')?.getAttribute('aria-pressed') === 'true'`;
    // the reaction request, steered by the test: __hold = it waits for __go(); __fail = it is then refused (403)
    const STEER = `(() => { if (window.__rf) return 1; window.__rf = window.fetch; window.__hold = false; window.__fail = false; window.__n = 0;
      window.fetch = async (u, o = {}) => { const s = String(u && u.url || u);
        if ((o.method || 'GET').toUpperCase() === 'POST' && /\\/api\\/team\\/messages\\/\\d+\\/reactions/.test(s)) {
          window.__n++; if (window.__hold) await new Promise(r => { window.__go = r; });
          if (window.__fail) return new Response(JSON.stringify({error: 'Not allowed here'}), {status: 403, headers: {'Content-Type': 'application/json'}});
        }
        return window.__rf(u, o); }; return 1; })()`;

    // ---------------------------------------------------------------- the calm line (360 px, a finger)
    await signIn('alice');
    await go(B + `#team/${room.id}`);
    check(await wait(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${a1.id}"] .trdline')`, {timeout: 20000}), 'alice: the conversation with "Read by"');
    let s = await ev(LINE(b2.id));
    check(s && s.mob && s.touch, 'a touch screen in phone width ' + JSON.stringify(s));
    check(s && !s.open && !s.smile && !s.dots && !s.quick, '#6096: bob\'s message: no smiley, no "..." before a tap ' + JSON.stringify(s));
    const closed = s;
    let a = await ev(LINE(a1.id));
    check(a && !a.dots, '#6096: my message: no "..." before a tap ' + JSON.stringify(a));
    check(a && a.ticks && !a.ticksOut && a.edited && a.spread <= 6, '#6096: "Read by" and "edited" in the time\'s row, not an own row ' + JSON.stringify(a));
    check(a && a.qh <= 30 && a.h <= a.bub + a.qh + 8, '#6096: my message = bubble + one low time line ' + JSON.stringify(a));
    check(a && a.timeTitle == null, '#6096: the time has no title of the same text ' + JSON.stringify(a));
    check(await ev(`/^Edited /.test(document.querySelector('#tc-msgs .cmsg[data-mid="t:${a1.id}"] .cmeta .cedited')?.title || '')`), '#6096: "edited" says when as its title');
    await shot('p21242a-zeile-ruhig.png');
    // "edited" in the time's line opens the earlier versions with a finger too (#6166 dialog), the message does not open
    let p = await ev(`(() => { const b = document.querySelector('#tc-msgs .cmsg[data-mid="t:${a1.id}"] .cmeta .cedited'); if (!b) return null; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    check(!!p, '#6096: "edited" is there to tap');
    if (p) await tap(p.x, p.y);
    check(await wait(`/Earlier versions/.test(document.querySelector('.modal.chedmd h3')?.textContent || '') && /Wrap at six/.test(document.querySelector('.modal.chedmd')?.textContent || '')`, {timeout: 8000}), '#6096: a tap on "edited" opens the earlier versions');
    await ev(`(document.querySelector('.modal.chedmd [data-m="close"]')?.click(), 1)`);
    check(await wait(`!document.querySelector('.modal.chedmd')`, {timeout: 5000}), 'the versions dialog closes again (Close)');
    check(await ev(`!document.querySelector('#tc-msgs .cmsg[data-mid="t:${a1.id}"].rxshow')`), '#6096: the tap on "edited" did not open the message line');

    // a tap on the message shows smiley and "...", the next tap hides them
    p = await bubAt(b2.id); await tap(p.x, p.y);
    check(await wait(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${b2.id}"].rxshow')`, {timeout: 5000}), '#6096: a tap on bob\'s message opens its line');
    s = await ev(LINE(b2.id));
    check(s && s.open && s.smile && s.dots && s.quick >= 1, '#6096: then smiley, quick reactions and "..." are there ' + JSON.stringify(s));
    check(s && closed.h < s.h, '#6096: the closed message is lower than with smiley and "..." (before) ' + JSON.stringify({closed: closed.h, open: s.h}));
    await shot('p21242a-zeile-angetippt.png');
    p = await bubAt(b2.id); await tap(p.x, p.y);
    check(await wait(`!document.querySelector('#tc-msgs .cmsg[data-mid="t:${b2.id}"].rxshow')`, {timeout: 5000}), '#6096: a second tap closes it');
    s = await ev(LINE(b2.id));
    check(s && !s.smile && !s.dots, '#6096: smiley and "..." gone again ' + JSON.stringify(s));
    // my own message: a tap shows its "..." (no reactions of mine on it)
    p = await bubAt(a1.id); await tap(p.x, p.y);
    check(await wait(`(() => { const d = document.querySelector('#tc-msgs .cmsg[data-mid="t:${a1.id}"].rxshow [data-act="tc-msg-menu"]'); return !!d && d.getBoundingClientRect().width > 4; })()`, {timeout: 5000}), '#6096: a tap on my message shows its "..."');

    // ---------------------------------------------------------------- a reaction shows at once, a refusal takes it back
    await ev(STEER);
    p = await bubAt(b1.id); await tap(p.x, p.y);
    check(await wait(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${b1.id}"].rxshow')`, {timeout: 5000}), 'bob\'s first message open');
    await ev(`(window.__hold = true, window.__fail = false, window.__n = 0, 1)`);
    let c = await chipAt(b1.id, 'up');
    check(!!c, '#6096: the thumbs up is there to tap');
    if (c) await tap(c.x, c.y);
    check(await wait(`window.__n === 1 && !!window.__go`, {timeout: 5000}), 'the reaction request is on its way');
    check(await ev(pressed(b1.id, 'up')), '#6096: the reaction shows at once, before the server answered');
    await ev(`(window.__hold = false, window.__go(), 1)`);
    check(await wait(async () => (await rx(b1.id)).some(x => x.emoji === 'up' && x.count === 1)), '#6096: and is saved');
    check(await ev(pressed(b1.id, 'up')), '#6096: still shown after the answer');
    // refused: shown at once, then back
    await ev(`(window.__hold = true, window.__fail = true, window.__n = 0, 1)`);
    if (!await ev(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${b1.id}"].rxshow')`)) { p = await bubAt(b1.id); await tap(p.x, p.y); }
    c = await chipAt(b1.id, 'heart');
    check(!!c, '#6096: the heart is there to tap');
    if (c) await tap(c.x, c.y);
    check(await wait(`window.__n === 1 && !!window.__go`, {timeout: 5000}), 'the second request is on its way');
    check(await ev(pressed(b1.id, 'heart')), '#6096: the heart shows at once');
    await ev(`(window.__go(), 1)`);
    check(await wait(`!(${pressed(b1.id, 'heart')})`, {timeout: 5000}), '#6096: refused: the heart goes back');
    check(await wait(`/Not allowed here/.test(document.querySelector('#toast:not(.hidden)')?.textContent || '')`, {timeout: 5000}), '#6096: and the reason is shown');
    check(!(await rx(b1.id)).some(x => x.emoji === 'heart'), '#6096: nothing saved for the heart');
    await ev(`(window.__hold = false, window.__fail = false, 1)`);

    // ---------------------------------------------------------------- a person without an organisation
    await signIn('frida');
    await go(B + `#team/${fch.id}`);
    check(await wait(`S.tc.rid === ${fch.id} && !!document.querySelector('#tc-msgs [data-mid="t:${fm.id}"] .cbub')`, {timeout: 20000}), 'freelancer: her project\'s channel');
    a = await ev(LINE(fm.id));
    check(a && !a.dots && a.edited && a.spread <= 6 && a.timeTitle == null, 'freelancer: "edited" in the time\'s row, no "..." before a tap ' + JSON.stringify(a));
    p = await bubAt(fm.id); await tap(p.x, p.y);
    check(await wait(`(() => { const d = document.querySelector('#tc-msgs .cmsg[data-mid="t:${fm.id}"].rxshow [data-act="tc-msg-menu"]'); return !!d && d.getBoundingClientRect().width > 4; })()`, {timeout: 5000}), 'freelancer: a tap shows "..."');
  }, true);

  console.log(`p21242_a_chat_line_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
