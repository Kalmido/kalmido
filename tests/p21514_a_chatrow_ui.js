// kalmido-suite: fresh
// 2.1514.0 (#7672) UI test (Firefox, 360 px phone), fresh DB:
// - #7672 the typing line and "Earlier suggestions (N)" share one row: same top edge, the button whole and 44 px high, the message
//   list keeps its height with and without the typing signal (#3737); the open list sits under the row across the width, a second tap folds it
const {errs, B, login, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21514_a_chatrow_ui', check, shots: 'P21514A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']}, CK);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab,agents,team'}, CK);
  const ME = (await call('GET', '/api/state', null, CK)).me, ORG = ME.workspaces[0].id;
  const BOB = (await call('POST', '/api/users', {orgs: [ORG], username: 'bob', display_name: 'Bob Brandt', password: 'password123', email: 'bob@example.com'}, CK)).id;
  const BK = await login('bob');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, BK);
  const L = await call('POST', '/api/lists', {name: 'Drehteam', org_id: ORG}, CK);
  await call('PUT', `/api/lists/${L.id}/members`, {user_id: BOB, role: 'edit'}, CK);
  const ag = await call('POST', '/api/admin/agents', {scopes: ['read', 'comments'], username: 'claude', display_name: 'Claude'}, CK);
  const AG = ag.id, AH = {...H, Authorization: 'Bearer ' + ag.token};
  await call('PUT', `/api/lists/${L.id}/members`, {user_id: AG, role: 'edit'}, CK);  // the agent shares a list with Alice: it may chat with her
  await call('PUT', `/api/agents/${AG}/chat-prefs`, {sugg: 'collect'}, CK);  // (#2848): ended suggestions wait in the shelf
  const say = async (body, extra = {}) => { const r = await fetch(B + `api/v1/agent/chats/${ME.id}`, {method: 'POST', headers: AH, body: JSON.stringify({body, ...extra})}); check(r.status === 201, 'the agent says something ' + r.status); return r.json(); };
  await say('Shall I plan the next cut?', {choices: [{id: 'yes', label: 'Plan it', style: 'primary'}, {id: 'no', label: 'Later'}]});
  for (let i = 1; i <= 12; i++) await say(`Short status ${i}`);

  await firefox(async ({cmd, ev, nav, ctx, shot}) => {
    const waitEv = async (js, n = 100) => { for (let i = 0; i < n && !(await ev(js).catch(() => false)); i++) await sleep(100); return ev(js).catch(() => false); };
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`), 'firefox: logged in');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await waitEv('innerHeight === 740');
    await nav(B + '#agents/' + AG);
    check(await waitEv(`!!document.querySelector('#chat-msgs .cmsg') && !!document.querySelector('#chat-typing') && !!document.querySelector('#chat-sug:not([hidden]) .acsug-t')`), 'the agent chat with its shelf is up');
    await sleep(400);

    // ================= #7672 one row
    const ROW = `(() => { const R = e => { const b = e.getBoundingClientRect(); return {t: Math.round(b.top), b: Math.round(b.bottom), l: Math.round(b.left), r: Math.round(b.right), h: Math.round(b.height), w: Math.round(b.width)}; };
      const q = s => document.querySelector(s), t = q('#chat-typing'), b = q('#chat-sug .acsug-t'), s = b && b.querySelector('span'), m = q('#chat-msgs'), l = q('#chat-sug .acsug-l');
      return {ty: R(t), bt: b && R(b), m: R(m), l: l && R(l), cut: !!s && s.scrollWidth > s.clientWidth + 1, iw: innerWidth, bot: !!q('#chat-typing svg.bot'), open: b && b.getAttribute('aria-expanded')}; })()`;
    const r0 = await ev(ROW);
    check(r0.bt && Math.abs(r0.ty.t - r0.bt.t) <= 1, '#7672 typing hint and button share the top edge ' + JSON.stringify(r0));
    check(r0.bt && r0.bt.h >= 44 && r0.bt.r <= r0.iw && !r0.cut, '#7672 the button is whole and 44 px high at 360 px ' + JSON.stringify(r0));
    check(r0.bt && r0.ty.r <= r0.bt.l + 1 && r0.ty.h === r0.bt.h, '#7672 the hint sits left of the button in the same row height ' + JSON.stringify(r0));
    await ev(`(() => { const a = agentById(${AG}); a.enabled = true; a.online = true; a.typing = 600; S.agentsAt = Date.now(); agentLive(); return 1; })()`);
    check(await waitEv(`!!document.querySelector('#chat-typing svg.bot')`), '#7672 the writing signal shows');
    const r1 = await ev(ROW);
    check(r1.m.h === r0.m.h && r1.ty.t === r0.ty.t && Math.abs(r1.ty.t - r1.bt.t) <= 1, '#7672 #3737 the message list keeps its height with the signal, same row ' + JSON.stringify([r0, r1]));
    await shot('p21514a-row-typing-360.png');
    await ev(`(() => { const a = agentById(${AG}); a.typing = 0; agentLive(); return 1; })()`);
    await waitEv(`!document.querySelector('#chat-typing svg.bot')`);
    check((await ev(ROW)).m.h === r0.m.h, '#7672 without the signal the same height again');
    await ev(`(document.querySelector('#chat-sug .acsug-t').click(), 1)`);
    check(await waitEv(`!!document.querySelector('#chat-sug .acsug-l .acsug-i')`), '#7672 a tap opens the earlier suggestions');
    const r2 = await ev(ROW);
    check(r2.l && r2.l.t >= r2.bt.b - 1 && r2.l.w >= 0.9 * r2.iw && r2.open === 'true', '#7672 the open list lies under the row across the width ' + JSON.stringify(r2));
    await shot('p21514a-shelf-open-360.png');
    await ev(`(document.querySelector('#chat-sug .acsug-t').click(), 1)`);
    check(await waitEv(`!document.querySelector('#chat-sug .acsug-l') && document.querySelector('#chat-sug .acsug-t').getAttribute('aria-expanded') === 'false'`), '#7672 a second tap folds it again');
    check((await ev(ROW)).m.h === r0.m.h, '#7672 folded: the message list as before');

  });

  check(!errs.length, 'no script errors: ' + errs.join(' | '));
  console.log(`p21514_a_chatrow_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21514_a_chatrow_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
