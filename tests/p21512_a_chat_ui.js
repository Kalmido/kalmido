// kalmido-suite: fresh
// (#7669) UI test (Firefox, 360 px phone), fresh DB: a chat at its end and a new message of someone else that is taller than the
// visible part shows its BEGINNING (the box stops at the message's top and is no longer pinned to the end); a short one goes to
// the end as before; scrolled up the place stays and "New message ↓" shows (#1660, #4393); my own message goes to the end.
// The team chat follows the same rule (a long message of Bob from its top, a short one to the end). Invented names only.
const {errs, B, login, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21512_a_chat_ui', check, shots: 'P21512A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const LONG = Array.from({length: 40}, (_, i) => `Line ${i + 1} of a long answer with enough words to fill the phone`).join('\n\n');

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
  const ROOM = (await call('GET', '/api/team', null, CK)).rooms.find(r => r.list_id === L.id).id;
  await call('GET', '/api/team', null, BK);
  const tsay = (ck, body) => call('POST', `/api/team/rooms/${ROOM}/messages`, {body}, ck);
  for (let i = 1; i <= 12; i++) await tsay(i % 2 ? CK : BK, `Team message ${i}`);
  const ag = await call('POST', '/api/admin/agents', {scopes: ['read', 'comments'], username: 'claude', display_name: 'Claude'}, CK);
  const AG = ag.id, AH = {...H, Authorization: 'Bearer ' + ag.token};
  await call('PUT', `/api/lists/${L.id}/members`, {user_id: AG, role: 'edit'}, CK);  // the agent shares a list with Alice: it may chat with her
  const say = async body => { const r = await fetch(B + `api/v1/agent/chats/${ME.id}`, {method: 'POST', headers: AH, body: JSON.stringify({body})}); check(r.status === 201, 'the agent says something ' + r.status); return r.json(); };
  for (let i = 1; i <= 12; i++) await say(`Short status ${i}`);

  await firefox(async ({cmd, ev, nav, ctx, shot}) => {
    const waitEv = async (js, n = 100) => { for (let i = 0; i < n && !(await ev(js).catch(() => false)); i++) await sleep(100); return ev(js).catch(() => false); };
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`), 'firefox: logged in');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await waitEv('innerHeight === 740');
    await nav(B + '#agents/' + AG);
    check(await waitEv(`document.querySelectorAll('#chat-msgs .cmsg').length >= 12`), 'the agent chat is up');

    // ================= agent chat
    const POS = id => `(() => { const box = document.querySelector('#chat-msgs'), m = document.querySelector('#chat-msgs .cmsg[data-mid="a:${id}"]'); if (!box || !m) return null;
      const bt = box.getBoundingClientRect().top; return {top: Math.round(m.getBoundingClientRect().top - bt), mh: Math.round(m.offsetHeight), ch: box.clientHeight, gap: Math.round(box.scrollHeight - box.scrollTop - box.clientHeight), st: Math.round(box.scrollTop), pin: S.chat.pin, pill: !document.querySelector('#chat-new').classList.contains('hidden')}; })()`;
    await ev(`(chatBottom(), 1)`); await waitEv(`S.chat.pin === true`);
    const long = await say(LONG);
    await ev(`chatLoad().then(() => 1)`);
    check(await waitEv(`!!document.querySelector('#chat-msgs .cmsg[data-mid="a:${long.id}"]')`), 'the long answer arrives');
    await waitEv(`(() => { const p = ${POS(long.id)}; return p && p.top >= -2 && p.top <= 24; })()`, 30);
    const p1 = await ev(POS(long.id));
    check(p1 && p1.mh > p1.ch && p1.top >= -2 && p1.top <= 24, 'a long answer: its beginning is in view ' + JSON.stringify(p1));
    check(p1 && p1.gap > 100 && p1.pin === false && !p1.pill, '... the box stopped there (not at the end, unpinned, no pill) ' + JSON.stringify(p1));
    await shot('p21512a-long-answer-360.png');
    // reading on: the box scrolls on by hand down to the end, nothing pulls it back up
    await ev(`(chatBottom(), 1)`); await waitEv(`S.chat.pin === true`);
    const short = await say('Done, the cut is rendered.');
    await ev(`chatLoad().then(() => 1)`);
    check(await waitEv(`!!document.querySelector('#chat-msgs .cmsg[data-mid="a:${short.id}"]') && ${POS(short.id)}?.gap <= 4`), 'a short answer: to the end as before ' + JSON.stringify(await ev(POS(short.id))));
    check(await ev(`S.chat.pin === true`), '... and the box stays pinned to the end');
    // scrolled up: the place stays, the pill shows (#1660, #4393)
    await ev(`(() => { const b = document.querySelector('#chat-msgs'); b.scrollTop = 0; b.dispatchEvent(new Event('scroll')); return 1; })()`);
    await waitEv(`S.chat.pin === false`);
    const up = await say(LONG.replace(/Line/g, 'Row'));
    await ev(`chatLoad().then(() => 1)`);
    await waitEv(`!!document.querySelector('#chat-msgs .cmsg[data-mid="a:${up.id}"]') && !document.querySelector('#chat-new').classList.contains('hidden')`);
    const p3 = await ev(POS(up.id));
    check(p3 && p3.st === 0 && p3.pill, 'scrolled up: the place stays, "New message" shows ' + JSON.stringify(p3));
    await ev(`(document.querySelector('#chat-new').click(), 1)`); await waitEv(`S.chat.pin === true`);
    // my own message: to the end
    await ev(`(() => { const t = document.querySelector('#chat-in'); t.value = 'Thanks, looks good'; t.dispatchEvent(new Event('input', {bubbles: true})); document.querySelector('[data-act="chat-send"]').click(); return 1; })()`);
    check(await waitEv(`[...document.querySelectorAll('#chat-msgs .cmsg.me')].some(m => /looks good/.test(m.textContent))`), 'my own message is sent');
    const GAP = `(() => { const b = document.querySelector('#chat-msgs'); return Math.round(b.scrollHeight - b.scrollTop - b.clientHeight); })()`;
    check(await waitEv(`${GAP} <= 4 && !document.querySelector('#chat-msgs .csending')`, 50), 'my own message: to the end ' + await ev(GAP));

    // ================= team chat
    await nav(B + '#team/' + ROOM);
    check(await waitEv(`!!document.querySelector('#tc-msgs [data-mid]') && !!document.querySelector('#tc-in')`), 'the team room is up');
    await waitEv(`!(S.tc.fitUntil > Date.now())`);  // the first load keeps the room at the end for a moment (teamFit)
    await ev(`(() => { const b = document.querySelector('#tc-msgs'); b.scrollTop = b.scrollHeight; return 1; })()`);
    const TPOS = id => `(() => { const box = document.querySelector('#tc-msgs'), m = document.querySelector('#tc-msgs [data-mid="t:${id}"]'); if (!box || !m) return null; return {top: Math.round(m.getBoundingClientRect().top - box.getBoundingClientRect().top), mh: m.offsetHeight, ch: box.clientHeight, gap: Math.round(box.scrollHeight - box.scrollTop - box.clientHeight)}; })()`;
    const tl = await tsay(BK, LONG);
    await ev(`loadRoom(${ROOM}).then(() => (tcPatch(), 1))`);
    check(await waitEv(`!!document.querySelector('#tc-msgs [data-mid="t:${tl.id}"]')`), 'team: the long message arrives');
    await waitEv(`(() => { const p = ${TPOS(tl.id)}; return p && p.top >= -2 && p.top <= 24; })()`, 30);
    const t1 = await ev(TPOS(tl.id));
    check(t1 && t1.mh > t1.ch && t1.top >= -2 && t1.top <= 24 && t1.gap > 100, 'team: a long message from its beginning ' + JSON.stringify(t1));
    await shot('p21512a-team-long-360.png');
    await ev(`(() => { const b = document.querySelector('#tc-msgs'); b.scrollTop = b.scrollHeight; return 1; })()`);
    const ts = await tsay(BK, 'Short one');
    await ev(`loadRoom(${ROOM}).then(() => (tcPatch(), 1))`);
    check(await waitEv(`!!document.querySelector('#tc-msgs [data-mid="t:${ts.id}"]') && ${TPOS(ts.id)}?.gap <= 4`), 'team: a short message to the end ' + JSON.stringify(await ev(TPOS(ts.id))));
  });

  check(!errs.length, 'no script errors: ' + errs.join(' | '));
  console.log(`p21512_a_chat_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21512_a_chat_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
