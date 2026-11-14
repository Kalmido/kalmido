// kalmido-suite: fresh
// 2.1169.0 (#6095 #6100) UI test (Firefox, 360 px), fresh DB:
// - #6095 the keyboard is open (viewport ~55 % high, body.kb-open): with a pinned message the history still shows clearly more than
//   two messages, the pinned bar is one line without the sender, the message box stays in view; without the keyboard the bar is as before
// - #6100 the bell: an approval entry of an agent is a header line + the question below it in one block (not word columns), more than
//   half the entry wide, no ** in the text; a mention entry is not in word columns either
const {boot, errs, B, login, until, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21169_b_chat_phone_ui', check, shots: 'P21169B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const call = async (method, url, body, ck, hdr = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {}), ...hdr}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']}, CK);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, CK);
  const ME = (await call('GET', '/api/state', null, CK)).me, ORG = ME.workspaces[0].id;
  const BOB = (await call('POST', '/api/users', {orgs: [ORG], username: 'bob', display_name: 'Emil Yildiz', password: 'password123', email: 'bob@example.com'}, CK)).id;
  const BK = await login('bob');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, BK);
  const L = await call('POST', '/api/lists', {name: 'Drehteam', org_id: ORG}, CK);
  await call('PUT', `/api/lists/${L.id}/members`, {user_id: BOB, role: 'edit'}, CK);
  const ROOM = (await call('GET', '/api/team', null, CK)).rooms.find(r => r.list_id === L.id).id;
  await call('GET', '/api/team', null, BK);
  const say = async (ck, body) => call('POST', `/api/team/rooms/${ROOM}/messages`, {body}, ck);
  const ag = await call('POST', '/api/admin/agents', {scopes: ['read', 'comments'], username: 'claude', display_name: 'Claude'}, CK);
  const AH = {Authorization: 'Bearer ' + ag.token};
  await call('PUT', `/api/lists/${L.id}/members`, {user_id: ag.id, role: 'edit'}, CK);
  let first = null;
  for (let i = 1; i <= 8; i++) { const m = await say(i % 2 ? CK : BK, `Message number ${i} of the day with some words`); first = first || m; }
  const pin = await call('POST', `/api/team/messages/${first.id}/pin`, {pinned: true}, CK);
  check(pin.status === 200, 'a message is pinned ' + pin.status);
  await say(BK, `Hello <@${ME.id}> please look at this`);  // a mention for Alice
  const ch = await fetch(B + `api/v1/agent/chats/${ME.id}`, {method: 'POST', headers: {...H, ...AH}, body: JSON.stringify({body: 'Deploy?', approval: {title: 'Shall I **really** deploy the new version to the production server tonight and tell the team about it afterwards?'}})});
  check(ch.status === 201, 'the agent asks for an approval ' + ch.status);

  await firefox(async ({cmd, ev, nav, ctx, shot}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`), 'firefox: logged in');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}}); await sleep(300);
    await nav(B + '#team/' + ROOM);
    for (let i = 0; i < 100 && !(await ev("!!document.querySelector('#tc-msgs .cm, #tc-msgs [data-mid]') && !!document.querySelector('#tc-in')").catch(() => false)); i++) await sleep(100);
    const MEAS = `(() => { const m = document.querySelector('#tc-msgs'), i = document.querySelector('#tc-in'), b = document.querySelector('.cpnbar'), r = i.getBoundingClientRect(), g = b && b.getBoundingClientRect();
      return {msgs: Math.round(m.getBoundingClientRect().height), bar: g ? Math.round(g.height) : 0, who: !!(b && [...b.querySelectorAll('b')].some(x => x.offsetParent)), kb: document.body.classList.contains('kb-open'), rule: getComputedStyle(document.querySelector('.cpnrow') || document.body).minHeight, inTop: Math.round(r.top), inBot: Math.round(r.bottom), ih: innerHeight}; })()`;
    const n0 = await ev(MEAS);
    check(n0.bar > 0, 'without the keyboard the pinned bar shows ' + JSON.stringify(n0));
    await ev("(document.querySelector('#tc-in').focus(), 1)"); await sleep(300);  // focus at full height first: S.vvMax = the height without a keyboard
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 407}}); await sleep(400);
    await ev("(document.querySelector('#tc-in').focus(), 1)"); for (let i = 0; i < 30 && !(await ev("document.body.classList.contains('kb-open')")); i++) await sleep(100);  // the app sets kb-open from the focus + the shrunken viewport
    const k = await ev(MEAS);
    check(k.bar > 0 && k.bar <= 44 && !k.who, '#6095 keyboard: the pinned bar is one line without the sender ' + JSON.stringify(k));
    check(k.msgs >= 160, '#6095 keyboard: the history keeps room for more than two messages ' + JSON.stringify(k));
    check(k.inTop >= 0 && k.inBot <= k.ih, '#6095 keyboard: the message box stays in view ' + JSON.stringify(k));
    await shot('p21169b-keyboard-360.png');
    await ev("(document.activeElement.blur(), 1)");
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}}); await sleep(400);
    const n1 = await ev(MEAS);
    check(n1.bar === n0.bar && n1.who === n0.who, '#6095 keyboard closed: the bar is as before ' + JSON.stringify([n0, n1]));

    // ---- the bell
    await nav(B + '#today');
    for (let i = 0; i < 100 && !(await ev('!!(window.S && S.booted)').catch(() => false)); i++) await sleep(100);
    await ev("(document.querySelector('[data-act=\"bell-pop\"]').click(), 1)");
    for (let i = 0; i < 100 && !(await ev("!!document.querySelector('.bpop .ngroup')")); i++) await sleep(100);
    await sleep(500);
    const G = `(() => [...document.querySelectorAll('.bpop .ngroup')].map(g => { const t = g.querySelector('.ngt'), tt = g.querySelector('.ngtt'), x = g.querySelector('.ngex'), r = g.getBoundingClientRect(), tr = t.getBoundingClientRect();
      return {txt: g.textContent.replace(/\\s+/g, ' ').trim(), w: Math.round(r.width), tw: Math.round(tr.width), ttw: tt ? Math.round(tt.getBoundingClientRect().width) : 0, kids: t.children.length, exw: x ? Math.round(x.getBoundingClientRect().width) : 0, exh: x ? Math.round(x.getBoundingClientRect().height) : 0, bold: x ? getComputedStyle(x).fontWeight : ''}; }))()`;
    const gs = await ev(G);
    const ap = gs.find(g => /waiting for your approval/.test(g.txt)), mn = gs.find(g => /mentioned/.test(g.txt));
    check(!!ap, '#6100 the approval entry is in the bell ' + JSON.stringify(gs));
    if (ap) {
      check(ap.txt.includes('Shall I really deploy') && !ap.txt.includes('**'), '#6100 the question reads in one piece, no ** ' + ap.txt);
      check(ap.exw > ap.w / 2 && ap.ttw > ap.w / 2, '#6100 header and question are more than half the entry wide ' + JSON.stringify(ap));
      check(ap.kids === 1 && +ap.bold <= 500, '#6100 the header is one block, the question in normal type ' + JSON.stringify(ap));
      check(ap.exh > 0 && ap.exh <= 3 * 24, '#6100 the question is at most three lines ' + JSON.stringify(ap));
    }
    if (mn) check(mn.kids === 1 && mn.ttw > mn.w / 2, '#6100 the mention entry is not in word columns ' + JSON.stringify(mn));
    await shot('p21169b-bell-360.png');
  });

  check(!errs.length, 'no script errors: ' + errs.join(' | '));
  console.log(`p21169_b_chat_phone_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21169_b_chat_phone_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
