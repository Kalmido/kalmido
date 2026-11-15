// 2.1211.0 UI test part B (#6098 chat loading / failed states and older pages, #6099 delete and undo), own container
// kalmido-suite: fresh
// Firefox as a touch screen in phone width 390 px. A channel of an organisation with 55 messages (one older page):
// - #6098: the conversation's load fails (the server answers 500 "Testfehler"): the shared block says "The messages could not be
//   loaded" with "Try again", never the server's text; the message box and Send are shut. "Try again" loads it: the messages
//   are there, the box opens. The older page fails: the hint stands at the button, the button works again. Tapped twice while
//   the older page loads: one request, every message once.
// - #6099: deleting my own message asks nothing, the message says so with Undo; Undo brings it back (server and view). A second
//   delete stands under "Recent steps" (#steps) and "Back up to here" brings it back. The same as a person without an
//   organisation (her own agent writes in her project's channel). Invented data only.
// freelancer-matrix: team - no new route for the client parts (the group's archive for Undo: p2113b_b_api_test)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21211_b_chat_states_ui', check, shots: 'P21211B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21211B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
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
  // Carol: a third person of the organisation, so Alice can make a group (two others at least)
  await call(CA, 'POST', '/api/users', {username: 'carol', display_name: 'Carol Member', password: 'password123', email: 'carol@example.com'});
  await call(CA, 'PUT', `/api/orgs/${org.id}/members`, {email: 'carol@example.com', role: 'member'});
  const CC = await login('carol');
  await call(CC, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${org.id}`});
  const carol = (await call(CC, 'GET', '/api/state')).me;
  const room = await call(CA, 'POST', '/api/team/channels', {name: 'Film crew', org_id: org.id, open: false, members: [bob.id]});
  check(room.id > 0, 'a room ' + JSON.stringify(room).slice(0, 200));
  // 55 messages (the first page holds 50): 28 of Bob, then 27 of mine (under the 60 per minute of each)
  const all = [];
  for (let i = 1; i <= 28; i++) all.push(await call(CB, 'POST', `/api/team/rooms/${room.id}/messages`, {body: `Take ${i} from Bob`}));
  for (let i = 1; i <= 27; i++) all.push(await call(CA, 'POST', `/api/team/rooms/${room.id}/messages`, {body: `Note ${i} from Alice`}));
  check(all.length === 55 && all.every(m => m.id > 0), '55 messages ' + JSON.stringify(all.find(m => !(m.id > 0)) || {}).slice(0, 200));
  const first = all[0], last = all[54], mine1 = all[54], mine2 = all[53];

  // a person without an organisation: Frida, her own agent in her project = the project's channel; she wrote two messages
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
  check(fm.id > 0, 'frida: her message');

  const msgOf = async (ck, rid, id) => ((await call(ck, 'GET', `/api/team/rooms/${rid}/messages`)).messages || []).find(m => m.id === id);

  await firefox(async ({cmd, ev, nav: go, ctx, shot, until: wait}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 780}});
    const signIn = async u => {
      await go(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`) === 200, `Firefox: login ${u}`);
    };
    // the server's answers of the conversation, steered by the test: __mode 'fail' = the newest page answers 500, 'oldfail' =
    // the older page answers 500, 'hold' = the older page waits for __go(); __n counts the older page's requests
    const STEER = `(() => { if (window.__rf) return 1; window.__rf = window.fetch; window.__n = 0; window.__mode = '';
      window.fetch = async (u, o = {}) => { const s = String(u), m = (o.method || 'GET').toUpperCase(), old = /before=/.test(s);
        if (m === 'GET' && /\\/api\\/team\\/rooms\\/\\d+\\/messages/.test(s) && !/thread=/.test(s)) {
          if (old) window.__n++;
          if ((window.__mode === 'fail' && !old) || (window.__mode === 'oldfail' && old)) return new Response(JSON.stringify({error: 'Testfehler'}), {status: 500, headers: {'Content-Type': 'application/json'}});
          if (window.__mode === 'hold' && old) await new Promise(r => { window.__go = r; });
        }
        if (m === 'GET' && /\\/api\\/agents\\/\\d+\\/chat(\\?|$)/.test(s) && window.__amode === 'fail') return new Response(JSON.stringify({error: 'Testfehler'}), {status: 500, headers: {'Content-Type': 'application/json'}});
        return window.__rf(u, o); }; return 1; })()`;
    const LOG = `(() => { const box = document.querySelector('#tc-msgs'); if (!box) return {none: 1};
      const ta = document.querySelector('#tc-in'), sb = document.querySelector('[data-act="tc-send"]'), e = box.querySelector('.eerr'), ob = box.querySelector('[data-act="tc-older"]');
      const ids = [...box.querySelectorAll('.cmsg[data-mid]')].map(x => x.dataset.mid);
      return {err: e ? e.textContent.trim() : '', retry: !!e?.querySelector('[data-esretry]'), raw: /Testfehler/.test(box.textContent), ld: !!box.querySelector('.eload'),
        taOff: !!ta?.disabled, sendOff: !!sb?.disabled, n: ids.length, uniq: new Set(ids).size, older: !!ob, olderOff: !!ob?.disabled,
        oerr: box.querySelector('.cholderr')?.textContent.trim() || '', mob: isMobile(), touch: isTouch()}; })()`;
    const log = () => ev(LOG);

    // ---------------------------------------------------------------- #6098 the conversation's load fails, "Try again"
    await signIn('alice');
    await go(B + '#today');
    check(await wait(`!!S.booted && S.route?.key === 'today'`, {timeout: 20000}), 'alice: the app started');
    await ev(STEER);
    await ev(`(window.__mode = 'fail', location.hash = '#team/${room.id}', 1)`);
    check(await wait(`!!document.querySelector('#tc-msgs .eerr')`, {timeout: 20000}), '#6098: the failed load shows the block ' + JSON.stringify(await log()));
    let s = await log();
    check(s.mob && s.touch, 'a touch screen in phone width ' + JSON.stringify(s));
    check(/The messages could not be loaded/.test(s.err) && /Try again/.test(s.err) && s.retry, '#6098: says what failed, with "Try again" ' + JSON.stringify(s));
    check(!s.raw, '#6098: never the server\'s text ' + JSON.stringify(s));
    check(s.taOff && s.sendOff, '#6098: the message box and Send are shut ' + JSON.stringify(s));
    check(await ev(`+getComputedStyle(document.querySelector('[data-act="tc-send"]')).opacity < 0.8 && +getComputedStyle(document.querySelector('#tc-in')).opacity < 0.8`), '#6098: and look shut');
    await shot('p21211b-ladefehler.png');
    await ev(`(window.__mode = '', document.querySelector('#tc-msgs .eerr [data-esretry]').click(), 1)`);
    check(await wait(`!!document.querySelector('#tc-msgs [data-mid="t:${last.id}"]') && !document.querySelector('#tc-msgs .eerr')`, {timeout: 20000}), '#6098: Try again loads the conversation ' + JSON.stringify(await log()));
    check(await wait(`!document.querySelector('#tc-in')?.disabled && !document.querySelector('[data-act="tc-send"]')?.disabled`, {timeout: 10000}), '#6098: the box opens once it loaded ' + JSON.stringify(await log()));
    s = await log();
    check(s.n === 50 && s.uniq === 50 && s.older, '#6098: the newest 50 with "Load older messages" ' + JSON.stringify(s));
    check(await ev(`[...document.querySelectorAll('#tc-msgs .cbub')].some(b => b.textContent.includes('Note 27 from Alice'))`), '#6098: the newest message reads in the log');

    // ---------------------------------------------------------------- #6098 older page: fails at the button, then once only
    await ev(`(window.__mode = 'oldfail', document.querySelector('#tc-msgs [data-act="tc-older"]').click(), 1)`);
    check(await wait(`!!document.querySelector('#tc-msgs .cholderr')`, {timeout: 15000}), '#6098: a failed older page says so ' + JSON.stringify(await log()));
    s = await log();
    check(/Older messages could not be loaded/.test(s.oerr) && !s.raw && s.older && !s.olderOff && s.n === 50, '#6098: the hint at the button, the button works again ' + JSON.stringify(s));
    await ev(`(window.__mode = 'hold', window.__n = 0, 1)`);
    // a double tap: the second tap meets the button of the first one's redraw
    await ev(`(() => { document.querySelector('#tc-msgs [data-act="tc-older"]').click(); document.querySelector('#tc-msgs [data-act="tc-older"]').click(); return 1; })()`);
    check(await wait(`window.__n === 1 && !!window.__go`, {timeout: 10000}), '#6098: the older page is asked for');
    s = await log();
    check(s.olderOff && !s.oerr, '#6098: while it loads the button is shut and the old hint gone ' + JSON.stringify(s));
    await ev(`(() => { document.querySelector('#tc-msgs [data-act="tc-older"]')?.click(); return 1; })()`);
    await ev(`(window.__go(), window.__mode = '', 1)`);
    check(await wait(`!!document.querySelector('#tc-msgs [data-mid="t:${first.id}"]')`, {timeout: 15000}), '#6098: the older page arrived ' + JSON.stringify(await log()));
    s = await log();
    check(await ev(`window.__n`) === 1, '#6098: tapped three times = one request: ' + await ev(`window.__n`));
    check(s.n === 55 && s.uniq === 55 && !s.older, '#6098: every message once, nothing older left ' + JSON.stringify(s));
    // two older loads at once (no guard in between): the second answer brings nothing twice
    await ev(`(location.hash = '#today', 1)`);
    check(await wait(`S.route?.key === 'today' && S.tc.rid === null`, {timeout: 15000}), 'left the conversation');
    await ev(`(location.hash = '#team/${room.id}', 1)`);
    check(await wait(`S.tc.rid === ${room.id} && S.tc.msgs.length === 50 && S.tc.more`, {timeout: 20000}), 'opened again with 50');
    await ev(`Promise.all([loadRoom(${room.id}, true), loadRoom(${room.id}, true)]).then(() => (tcPatch(), 1))`);
    check(await ev(`S.tc.msgs.length === 55 && new Set(S.tc.msgs.map(m => m.id)).size === 55`), '#6098: two older loads at once = every message once ' + await ev(`S.tc.msgs.length`));

    // ---------------------------------------------------------------- #6099 delete my own message: no question, Undo
    const del = async (tag, rid, id) => {
      check(await wait(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] [data-act="tc-msg-menu"]')`, {timeout: 15000}), `${tag}: the message with its menu`);
      await ev(`(document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] [data-act="tc-msg-menu"]').click(), 1)`);
      check(await wait(`[...document.querySelectorAll('#pop [role="menuitem"]')].some(b => /Delete/.test(b.textContent))`, {timeout: 8000}), `${tag}: the menu has Delete`);
      await ev(`([...document.querySelectorAll('#pop [role="menuitem"]')].find(b => /Delete/.test(b.textContent)).click(), 1)`);
      check(await wait(`!!document.querySelector('#tc-msgs .cmsg[data-mid="t:${id}"] .cbub.del')`, {timeout: 10000}), `${tag}: shows as deleted at once`);
      check(!(await ev(`!!document.querySelector('.modal.cdlg')`)), `${tag}: no question asked`);
      check(await wait(`/Message deleted/.test(document.querySelector('#toast:not(.hidden)')?.textContent || '') && !!document.querySelector('#toast:not(.hidden) button')`, {timeout: 8000}), `${tag}: the message "Message deleted" with Undo`);
    };
    await del('#6099 channel', room.id, mine1.id);
    check((await msgOf(CA, room.id, mine1.id))?.deleted === true, '#6099: deleted on the server');
    await shot('p21211b-geloescht-rueckgaengig.png');
    await ev(`(document.querySelector('#toast:not(.hidden) button').click(), 1)`);
    check(await wait(`[...document.querySelectorAll('#tc-msgs .cmsg[data-mid="t:${mine1.id}"] .cbub')].some(b => b.textContent.includes('Note 27 from Alice'))`, {timeout: 10000}), '#6099: Undo brings it back in the log');
    const back1 = await msgOf(CA, room.id, mine1.id);
    check(back1 && !back1.deleted && back1.body === 'Note 27 from Alice', '#6099: and on the server ' + JSON.stringify(back1));
    // a second delete stands under "Recent steps"; "Back up to here" brings it back
    await del('#6099 second', room.id, mine2.id);
    await ev(`(location.hash = '#steps', 1)`);
    check(await wait(`[...document.querySelectorAll('.ulrow .ullab')].some(x => x.textContent.trim() === 'Message deleted')`, {timeout: 15000}), '#6099: "Message deleted" under Recent steps ' + await ev(`[...document.querySelectorAll('.ulrow .ullab')].map(x => x.textContent).join(' | ')`));
    await shot('p21211b-letzte-schritte.png');
    await ev(`(() => { const r = [...document.querySelectorAll('.ulrow')].find(x => x.querySelector('.ullab')?.textContent.trim() === 'Message deleted'); r.querySelector('[data-ul-go]').click(); return 1; })()`);
    check(await wait(async () => { const m = await msgOf(CA, room.id, mine2.id); return m && !m.deleted; }, {timeout: 15000}), '#6099: Recent steps: Back up to here restores it');
    await ev(`(location.hash = '#team/${room.id}', 1)`);
    check(await wait(`[...document.querySelectorAll('#tc-msgs .cmsg[data-mid="t:${mine2.id}"] .cbub')].some(b => b.textContent.includes('Note 26 from Alice'))`, {timeout: 15000}), '#6099: the restored message reads in the log');

    // ---------------------------------------------------------------- #6099 a new group has Undo like a new channel
    const groupsOf = async ck => ((await call(ck, 'GET', '/api/team')).rooms || []).filter(x => x.kind === 'group');
    await ev(`(location.hash = '#team', 1)`);
    check(await wait(`S.route?.mod === 'team' && (S.tc.people || []).length >= 2`, {timeout: 20000}), '#6099: the team chat with two people to pick');
    await ev(`(tcx_groupNew(), 1)`);
    check(await wait(`!!document.querySelector('.tcxdlg .tcxpick')`, {timeout: 10000}), '#6099: the dialog "New group"');
    await ev(`(() => { const md = document.querySelector('.tcxdlg'); for (const id of [${bob.id}, ${carol.id}]) { const c = md.querySelector('.tcxpick input[value="' + id + '"]'); c.checked = true; }
      md.querySelector('#tcx-name').value = 'Crew B'; md.querySelector('button[type="submit"]').click(); return 1; })()`);
    check(await wait(`/Group “Crew B” created/.test(document.querySelector('#toast:not(.hidden)')?.textContent || '') && !!document.querySelector('#toast:not(.hidden) button')`, {timeout: 10000}), '#6099: "Group “Crew B” created" with Undo ' + await ev(`document.querySelector('#toast')?.textContent || ''`));
    const gB = (await groupsOf(CC)).find(x => x.name === 'Crew B') || {};
    check(gB.id > 0, '#6099: carol has the new group');
    await ev(`(document.querySelector('#toast:not(.hidden) button').click(), 1)`);
    check(await wait(async () => !(await groupsOf(CC)).some(x => x.id === gB.id), {timeout: 15000}), '#6099: Undo takes the group away for carol too');
    check(await wait(`!(S.tc.rooms || []).some(r => r.id === ${gB.id}) && S.route?.mod === 'team' && S.tc.rid !== ${gB.id}`, {timeout: 15000}), '#6099: and from my list, the open group closed');
    check((await call(CB, 'POST', `/api/team/rooms/${gB.id}/messages`, {body: 'late'})).http === 409, '#6099: an undone group takes no message');
    // Leave asks only where I cannot come back by myself, and the dialog says that it is a group
    const gL = await call(CA, 'POST', '/api/team/groups', {members: [bob.id, carol.id], name: 'Crew L'});
    check(gL.id > 0, 'a second group');
    await ev(`(location.hash = '#team/${gL.id}', 1)`);
    check(await wait(`S.tc.rid === ${gL.id} && !!S.tc.room`, {timeout: 15000}), 'the second group open');
    await ev(`(tcx_settings(), 1)`);
    check(await wait(`!!document.querySelector('[data-xs="leave"]')`, {timeout: 10000}), '#6099: the group settings with Leave');
    await ev(`(document.querySelector('[data-xs="leave"]').click(), 1)`);
    check(await wait(`/Leave this group\\?/.test([...document.querySelectorAll('.modal.cdlg')].pop()?.textContent || '') && /only come back when someone adds you again/.test([...document.querySelectorAll('.modal.cdlg')].pop()?.textContent || '')`, {timeout: 10000}), '#6099: Leave asks "Leave this group?" and says why');
    await shot('p21211b-gruppe-verlassen.png');
    await ev(`([...document.querySelectorAll('.modal.cdlg')].pop().querySelector('[data-cd="no"]').click(), 1)`);
    check(await wait(async () => ((await call(CA, 'GET', `/api/team/rooms/${gL.id}/messages`)).room?.members || []).some(m => m.id === me.id), {timeout: 8000}), '#6099: Cancel = still a member');

    // ---------------------------------------------------------------- a person without an organisation
    await signIn('frida');
    await go(B + `#team/${fch.id}`);
    check(await wait(`S.tc.rid === ${fch.id} && !!document.querySelector('#tc-msgs [data-mid="t:${fm.id}"]')`, {timeout: 20000}), 'freelancer: her project\'s channel');
    check(await wait(`!document.querySelector('#tc-in')?.disabled`, {timeout: 10000}), 'freelancer: the box is open once it loaded');
    await del('#6099 freelancer', fch.id, fm.id);
    check((await msgOf(CF, fch.id, fm.id))?.deleted === true, 'freelancer: deleted on the server');
    await ev(`(document.querySelector('#toast:not(.hidden) button').click(), 1)`);
    check(await wait(async () => { const m = await msgOf(CF, fch.id, fm.id); return m && !m.deleted; }, {timeout: 15000}), 'freelancer: Undo brings it back');
    // #6098 the agent chat: a failed load is the shared block (it said "Only available online." for every error), the box shut
    await ev(STEER);
    await ev(`(window.__amode = 'fail', location.hash = '#agents/${ag.id}', 1)`);
    check(await wait(`!!document.querySelector('#chat-msgs .eerr')`, {timeout: 20000}), '#6098 agent chat: the failed load shows the block ' + await ev(`document.querySelector('#chat-msgs')?.textContent.slice(0, 200) || 'no #chat-msgs'`));
    const ac = await ev(`(() => { const box = document.querySelector('#chat-msgs'); return {t: box.textContent, retry: !!box.querySelector('.eerr [data-esretry]'), off: !!document.querySelector('#chat-in')?.disabled}; })()`);
    check(/The messages could not be loaded/.test(ac.t) && ac.retry && !/Testfehler|Only available online/.test(ac.t), '#6098 agent chat: says what failed, with Try again, no server text ' + JSON.stringify(ac));
    check(ac.off, '#6098 agent chat: the box is shut while it failed');
    await shot('p21211b-agent-ladefehler.png');
    await ev(`(window.__amode = '', document.querySelector('#chat-msgs .eerr [data-esretry]').click(), 1)`);
    check(await wait(`!document.querySelector('#chat-msgs .eerr') && !document.querySelector('#chat-msgs .eload') && !!document.querySelector('#chat-msgs .cmempty')`, {timeout: 20000}), '#6098 agent chat: Try again loads it (the empty conversation reads) ' + await ev(`document.querySelector('#chat-msgs')?.textContent.slice(0, 200) || ''`));
    if (await ev(`!!agentById(${ag.id})?.enabled`)) check(await wait(`!document.querySelector('#chat-in')?.disabled`, {timeout: 10000}), '#6098 agent chat: the box opens once it loaded');
  }, true);

  console.log(`p21211_b_chat_states_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
