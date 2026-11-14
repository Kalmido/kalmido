// 2.1172.0 UI test part B (#6102 team composer calmer, #6103 agent chat on the phone), own container
// kalmido-suite: fresh
// Firefox as a touch screen at 360 px. Team chat: after the first character the microphone is still there and the box does not move;
// two image files are ONE row of small tiles with an <img> preview; a tap (pointerdown) on Send does not take the focus from the
// box and after sending the box still has it; muting leaves the draft (the same box node). Agent chat: an open approval whose card
// is in view has no pinned bar, scrolled away the bar shows; "Allow" in the bar and in the card have the same computed colour (the
// agent's colour); the tabs of the chat switcher lie inside the screen. A person without an organisation (this instance has none).
// freelancer-matrix: team - no new route (view of /api/team and the agent chat)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21172_b_chat_input', check, shots: 'P21172B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21172B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const FEAT = 'collab,comments,agents';
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const BOB = (await call('POST', '/api/users', {username: 'bob', display_name: 'Bob Baker', password: 'password123'})).id;
  const mk = async (u, n) => { const a = await call('POST', '/api/admin/agents', {scopes: ['read', 'tasks:write', 'comments'], username: u, display_name: n}); return {id: a.id, h: {Authorization: 'Bearer ' + a.token, 'Content-Type': 'application/json'}}; };
  const A1 = await mk('claude', 'Claude'), A2 = await mk('kalmido-assistant', 'Kalmido Assistant With A Very Long Name Indeed');
  const ME = (await call('GET', '/api/state')).me;
  const L = (await call('POST', '/api/lists', {name: 'Team list'})).id;
  for (const a of [A1, A2]) await call('PUT', `/api/lists/${L}/members`, {user_id: a.id, role: 'edit'});
  await call('PUT', `/api/lists/${L}/members`, {user_id: BOB, role: 'edit'});  // they share a project: a channel is possible
  const room = await call('POST', '/api/team/channels', {name: 'Film crew', open: false, members: [BOB]});
  check(room.id > 0, 'a channel ' + JSON.stringify(room).slice(0, 160));
  const v1 = async (a, body) => { const x = await fetch(B + `api/v1/agent/chats/${ME.id}`, {method: 'POST', headers: a.h, body: JSON.stringify(body)}); return {...(await x.json().catch(() => ({}))), status: x.status}; };
  const pq = await v1(A1, {body: 'May I run this?\n```\n./deploy.sh staging\n```', permission: true});
  check(pq.status === 201, 'a permission question ' + JSON.stringify(pq).slice(0, 160));
  for (let i = 1; i <= 25; i++) await v1(A1, {body: `Progress note ${i}\nsecond line of note ${i}\nthird line`});
  await v1(A2, {body: 'Hello from the second agent'});

  await firefox(async ({cmd, ev, nav: go, ctx, shot, until: wait}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 760}});
    await go(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');

    // ---- team chat
    await go(B + `#team/${room.id}`);
    check(await wait(`S.tc.rid === ${room.id} && !!document.querySelector('#tc-in') && !!S.tc.room`, {timeout: 20000}), 'team: the room is open');
    const BOX = `(() => { const t = document.querySelector('#tc-in'), m = document.querySelector('.tccomp .tvcmic'), r = t.getBoundingClientRect();
      return {l: Math.round(r.left), w: Math.round(r.width), mic: !!m, micHidden: !!m?.classList.contains('hidden'), focus: document.activeElement === t}; })()`;
    await ev(`(() => { const t = document.querySelector('#tc-in'); t.focus(); return 1; })()`);
    const b0 = await ev(BOX);
    await ev(`(() => { const t = document.querySelector('#tc-in'); t.value = 'H'; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    const b1 = await ev(BOX);
    check(b0.mic && b1.mic && !b1.micHidden, '#6102: the microphone stays after the first character ' + JSON.stringify([b0, b1]));
    check(b0.l === b1.l && b0.w === b1.w, '#6102: the box does not move while typing ' + JSON.stringify([b0, b1]));
    // placeholder: whole text, cut by the CSS (no character count)
    check(await ev(`document.querySelector('#tc-in').placeholder.endsWith('Film crew…')`), '#6102: the placeholder is the whole text');
    await ev(`(() => { const t = document.querySelector('#tc-in'); t.value = ''; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);

    // two images: ONE row of tiles with a preview
    await ev(`(async () => { const bin = atob('${PNG}'), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      tcx_addFiles([new File([u], 'a.png', {type: 'image/png'}), new File([u], 'b.png', {type: 'image/png'})]); return 1; })()`);
    const CH = await ev(`(() => { const c = [...document.querySelectorAll('#tc-files .cfile')].map(x => { const r = x.getBoundingClientRect(), i = x.querySelector('img'); return {top: Math.round(r.top), h: Math.round(r.height), right: Math.round(r.right), img: !!i && /^blob:/.test(i.src) && getComputedStyle(i).display !== 'none'}; });
      return {n: c.length, c, vw: innerWidth}; })()`);
    check(CH.n === 2 && CH.c[0].top === CH.c[1].top, '#6102: two attachments stand in ONE row ' + JSON.stringify(CH));
    check(CH.c.every(x => x.img && x.h <= 72 && x.right <= CH.vw), '#6102: small tiles with an image preview ' + JSON.stringify(CH));
    await shot('p21172b-tiles.png');
    await ev(`(() => { document.querySelector('[data-act="tc-file-rm"][data-i="1"]').click(); return 1; })()`);
    check(await ev(`document.querySelectorAll('#tc-files .cfile').length`) === 1, '#6102: removing a tile');

    // Send: the tap does not take the focus; after sending the box keeps it
    await ev(`(() => { const t = document.querySelector('#tc-in'); t.focus(); t.value = 'First line from the phone'; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    const pd = await ev(`(() => { const e = new PointerEvent('pointerdown', {bubbles: true, cancelable: true}); document.querySelector('[data-act="tc-send"]').dispatchEvent(e); return e.defaultPrevented; })()`);
    check(pd === true, '#6102: pointerdown on Send is prevented (the keyboard stays)');
    await ev(`(() => { document.querySelector('[data-act="tc-send"]').click(); return 1; })()`);
    check(await wait(`[...document.querySelectorAll('#tc-msgs .cmsg.me .cbub')].some(e => e.textContent.includes('First line from the phone'))`, {timeout: 15000}), 'team: the message is there');
    check(await wait(`document.activeElement?.id === 'tc-in'`, {timeout: 5000}), '#6102: the focus stays in the box after sending');
    check(await wait(`!document.querySelector('#tc-files .cfile')`, {timeout: 10000}), '#6102: the sent attachment is gone from the row');

    // muting: the draft and the very same box stay
    await ev(`(() => { const t = document.querySelector('#tc-in'); t.value = 'A draft'; t.dispatchEvent(new Event('input', {bubbles: true})); window.__box = t; return tcMute().then(() => 1); })()`);
    check(await wait(`S.tc.room.muted === true`, {timeout: 8000}), 'team: muted');
    check(await ev(`document.querySelector('#tc-in') === window.__box && window.__box.value === 'A draft'`), '#6102: muting keeps the draft in the same box');

    // ---- agent chat
    await ev(`(() => { S.colors = {...(S.colors || {}), [${A1.id}]: '#d9731a'}; return 1; })()`);
    await go(B + `#agents/${A1.id}`);
    check(await wait(`!!document.querySelector('.cmsg.apv .cperm') && !!document.querySelector('#chat-msgs')`, {timeout: 20000}), 'agent: chat with the permission card');
    await ev(`(() => { S.colors = {...(S.colors || {}), [${A1.id}]: '#d9731a'}; chatOpen(${A1.id}); return 1; })()`);
    check(await wait(`!!document.querySelector('.cmsg.apv .cperm')`, {timeout: 15000}), 'agent: card drawn');
    // at the end of the log: the card is far above = the bar shows
    const PIN = `(() => { const p = document.querySelector('#chat-apv'); return !!p && !p.hidden && !!p.querySelector('.apvpin'); })()`;
    await ev(`(() => { const b = document.querySelector('#chat-msgs'); b.scrollTop = b.scrollHeight; return 1; })()`);
    check(await wait(PIN, {timeout: 10000}), '#6103: the card is out of view = the pinned bar shows');
    const colr = sel => `getComputedStyle(document.querySelector('${sel} [data-cid="allow"]')).backgroundColor`;
    await shot('p21172b-pin.png');
    // jump to the card: it is in view, the bar goes
    await ev(`(() => { const n = document.querySelector('.cmsg.apv'); n.scrollIntoView({block: 'center'}); return 1; })()`);
    check(await wait(`(() => { const p = document.querySelector('#chat-apv'); return !p || p.hidden || !p.querySelector('.apvpin'); })()`, {timeout: 10000}), '#6103: the card in view = no pinned bar (no double question)');
    // the colour of Allow: bar and card the same
    await ev(`(() => { const b = document.querySelector('#chat-msgs'); b.scrollTop = b.scrollHeight; return 1; })()`);
    check(await wait(PIN, {timeout: 10000}), '#6103: scrolled away: the bar is back');
    const cp = await ev(colr('#chat-apv .apvpin')), cc = await ev(colr('.cmsg.apv'));
    check(cp && cp === cc && cp !== 'rgba(0, 0, 0, 0)', '#6103: Allow has the same colour in the bar and the card ' + cp + ' / ' + cc);

    // the switcher: two open chats, every tab inside the screen
    await ev(`(() => { S.cw.wins = [{k: 'a:${A1.id}', h: 1, c: false}, {k: 'a:${A2.id}', h: 1, c: false}]; chatOpen(${A1.id}); return 1; })()`);
    await ev(`(() => { location.hash = 'agents/${A2.id}'; return 1; })()`);
    check(await wait(`document.querySelectorAll('.cwsw .cwswb').length >= 2`, {timeout: 15000}), '#6103: the switcher with two tabs');
    const SW = await ev(`(() => ({vw: innerWidth, bs: [...document.querySelectorAll('.cwsw .cwswb')].map(b => Math.round(b.getBoundingClientRect().right))}))()`);
    check(SW.bs.every(x => x <= SW.vw), '#6103: every tab lies inside the screen ' + JSON.stringify(SW));
    await shot('p21172b-switcher.png');
  }, true);

  console.log(`p21172_b_chat_input: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
