// 2.1269.0 (#6450) UI test (Firefox, a phone 390 px, touch, light), fresh DB, a person WITHOUT an organisation (P4,
// freelancer-matrix: agents): an approval card with a harmless title of the agent shows OPEN, above its buttons, what the bound
// step really does in the server's words -- the agent's title stands below as a quote "The agent writes:".
// - sharing a project with a person: "Gives Scout access to Project Home as Member" + the warning line share
// - moving a task: "Moves task Buy paint from Project Home to Project Studio" + the warning move; Yes is usable, a press answers
//   the card and the agent's run of the card moves the task
// - many at once: "Complete 4 tasks at once" + the first titles
// - the pinned bar on top of the chat: "Approval needed" + "The agent writes: <title>" + the server's words
// - Yes stays locked while no description is there (a card the browser cannot load)
// - screenshot P21269_SHOTS/p21269-apvdesc-share.png (light, phone width)
// kalmido-suite: fresh
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21269_d_apvdesc_ui', check, shots: 'P21269_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('PATCH', '/api/settings', {tour: 'done', lang: 'en', theme: 'light', features: 'collab,comments,agents'});
  const me = (await call('GET', '/api/state')).me;
  check(!(me.workspaces || []).length, 'alice has no organisation (P4)');
  await call('PUT', '/api/admin/agent-policy', {user_agents: true});
  const ag = await call('POST', '/api/my/agents', {username: 'helper', display_name: 'Helper', scopes: ['read', 'tasks:write', 'comments']});
  const sc = await call('POST', '/api/my/agents', {username: 'scout', display_name: 'Scout', scopes: ['read']});
  check(ag.token && sc.id, 'setup: two personal agents ' + ag.status + ' ' + sc.status);
  const HOME = (await call('POST', '/api/lists', {name: 'Home'})).id, STUDIO = (await call('POST', '/api/lists', {name: 'Studio'})).id;
  for (const l of [HOME, STUDIO]) check((await call('PUT', `/api/lists/${l}/members`, {user_id: ag.id, role: 'edit'})).status < 300, 'setup: shared with the agent');
  const T = (await call('POST', '/api/tasks', {title: 'Buy paint', list_id: HOME})).id;
  const TS = []; for (const t of ['Sweep', 'Dust', 'Water plants', 'Air out']) TS.push((await call('POST', '/api/tasks', {title: t, list_id: HOME})).id);
  const v1 = async (method, url, body) => { const x = await fetch(B + 'api/v1' + url, {method, headers: {Authorization: 'Bearer ' + ag.token, 'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined}); return {...(await x.json().catch(() => ({}))), status: x.status}; };
  const card = async (title, step) => { const r = await v1('POST', `/agent/chats/${me.id}`, {approval: {title, step}}); check(r.status === 201, 'card ' + title + ' ' + r.status + ' ' + JSON.stringify(r).slice(0, 200)); return r.id; };
  const C1 = await card('May I sort the task?', {method: 'PUT', path: `/lists/${HOME}/members/${sc.id}`, body: {role: 'edit'}});
  const C2 = await card('Tidy up', {method: 'POST', path: `/tasks/${T}/move`, body: {list_id: STUDIO}});
  const C3 = await card('Quick cleanup', {method: 'POST', path: '/tasks/batch', body: {ids: TS, action: 'complete'}});

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const CARD = id => `document.querySelector('#chat-msgs .cmsg[data-mid="a:${id}"]')`;
  const info = id => `(() => { const c = ${CARD(id)}; if (!c) return 'null'; const x = c.querySelector('.apvx'), q = c.querySelector('.apvq'), y = c.querySelector('.apvbtns .cchb');
    return JSON.stringify({x: x?.textContent.trim() || '', warn: [...c.querySelectorAll('[data-apvx-warn]')].map(n => n.dataset.apvxWarn), q: q?.textContent.trim() || '',
      order: !!(x && q && (x.compareDocumentPosition(q) & Node.DOCUMENT_POSITION_FOLLOWING)), folded: !!x?.closest('details'), yes: y ? !y.disabled : null,
      chip: [...(x?.querySelectorAll('.apvxv') || [])].map(n => n.textContent)}); })()`;

  await firefox(async o => {
    const {ev, cmd, ctx, nav, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + 'static/icon.svg');
    await ev(`(async () => { localStorage.clear(); sessionStorage.clear(); return (await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})})).status; })()`);
    await sleep(400);
    await nav(B + '#today');
    check(await ready(ev, `typeof loadModule === 'function' && !!S.me`), 'the app is up');
    await ev(`loadModule('agentchat').then(() => { chatOpen(${ag.id}); return 1; })`);
    check(await ready(ev, `!!${CARD(C1)}`), 'the chat shows the share card');
    check(await ready(ev, `!!${CARD(C1)}?.querySelector('.apvx .apvxv')`), 'the share card gets the server\'s words');
    if (!await ev(`!!${CARD(C1)}`)) { await shot('p21269-debug.png'); return; }

    // ======== sharing behind a harmless title
    const s1 = JSON.parse(await ev(info(C1)));
    check(/^Gives Scout access to Project Home as Member/.test(s1.x) && s1.chip.includes('Scout') && s1.chip.includes('Home'), 'the share in the server\'s words ' + JSON.stringify(s1));
    check(s1.warn.includes('share') && /Other people get access/.test(s1.x), 'the warning line share ' + JSON.stringify(s1));
    check(/^The agent writes:\s*May I sort the task\?/.test(s1.q) && s1.order && !s1.folded, 'open, above: the server; below: "The agent writes:" + the title ' + JSON.stringify(s1));
    check(s1.yes === true, 'Yes is usable once the description is there');
    await ev(`(() => { ${CARD(C1)}.scrollIntoView({block: 'start'}); return 1; })()`);
    await sleep(300);
    await shot('p21269-apvdesc-share.png');

    // ======== the pinned bar on top of the chat (review of #6450): the agent's title set apart like on the card
    const pin = JSON.parse(await ev(`(() => { APV_VIS.clear(); const p = document.querySelector('#chat-apv'); p._h = null; apvPinSync();
      const r = [...p.querySelectorAll('.apvpin')].find(n => /May I sort/.test(n.textContent)); const g = r?.querySelector('.apvgo');
      return JSON.stringify({shown: !p.hidden && !!r, agent: r?.querySelector('[data-apv-agent]')?.textContent.trim() || '', go: g?.textContent.trim() || '',
        x: r?.querySelector('.apvx')?.textContent.trim() || ''}); })()`));
    check(pin.shown && /^The agent writes:\s*May I sort the task\?/.test(pin.agent) && /^Approval needed\s*The agent writes:/.test(pin.go),
      'the pinned bar marks the agent\'s title as its words ' + JSON.stringify(pin));
    check(/^Gives Scout access to Project Home as Member/.test(pin.x), 'the pinned bar names the step in the server\'s words ' + JSON.stringify(pin));
    await ev(`(() => { const p = document.querySelector('#chat-apv'); p._h = null; ${CARD(C1)}.scrollIntoView({block: 'start'}); return 1; })()`);

    // ======== Yes locked without a description
    check(await ev(`/disabled/.test(ccApvBtns({approval: {title: 'x', step: {method: 'PUT', path: '/api/v1/lists/1/members/2'}}, choices: []}, () => '', '', 'chat:987654321'))`), 'a card whose description is missing: Yes locked');
    check(await ev(`!/disabled/.test(ccApvBtns({approval: {title: 'x'}, choices: []}, () => '', '', 'chat:987654322'))`), 'a card without a step: Yes as before');
    // 2.1384.0 (#6991): a card without a step: the agent's text as the title, no quote frame, no server line, Yes usable
    check(await ev(`(() => { const h = ccApvHead({title: 'Shall I go on?', what: 'I write the plan'}, true, 'chat:987654323'); const d = document.createElement('div'); d.innerHTML = h;
      return !d.querySelector('.apvq') && !d.querySelector('.apvx') && !/The agent writes|No step|Kein Schritt/.test(h) && d.querySelector('.apvt')?.textContent === 'Shall I go on?' && /I write the plan/.test(d.querySelector('.apvw')?.textContent || ''); })()`), 'a card without a step: title only, no quote, no server line');
    check(await ev(`(() => { const d = document.createElement('div'); d.innerHTML = ccApvHead({title: 'T', step: {method: 'PUT', path: '/api/v1/lists/1/members/2'}}, true, 'chat:987654324'); return !!d.querySelector('.apvq') && !!d.querySelector('.apvx'); })()`), 'a card with a step: unchanged (quote and server line)');

    // ======== moving: the words, the warning, Yes answers, the run moves the task
    check(await ready(ev, `!!${CARD(C2)}?.querySelector('.apvx .apvxv')`), 'the move card gets its words');
    const s2 = JSON.parse(await ev(info(C2)));
    check(/^Moves task Buy paint from Project Home to Project Studio/.test(s2.x) && s2.warn.includes('move') && /The agent writes:\s*Tidy up/.test(s2.q), 'the move in words + warning ' + JSON.stringify(s2));
    check(await ev(`(() => { const b = ${CARD(C2)}.querySelector('.apvbtns .cchb'); if (!b || b.disabled) return false; b.click(); return true; })()`), 'Yes pressed on the move card');
    check(await ready(ev, `!${CARD(C2)}?.classList.contains('apvopen')`), 'the card is answered');
    const run = await v1('POST', `/agent/approvals/${C2}/run`);
    const t = await call('GET', `/api/tasks/${T}`);
    check(run.status < 300 && (t.list_id ?? t.task?.list_id) === STUDIO, 'the approved step ran: the task is in Studio ' + run.status + ' ' + JSON.stringify(run).slice(0, 200) + ' ' + JSON.stringify(t).slice(0, 120));
    check(await ready(ev, `/Moves task/.test(${CARD(C2)}?.querySelector('.apvx')?.textContent || '')`), 'the answered card keeps the server\'s words');

    // ======== many at once
    check(await ready(ev, `!!${CARD(C3)}?.querySelector('.apvx .apvxv')`), 'the batch card gets its words');
    const s3 = JSON.parse(await ev(info(C3)));
    check(/Complete 4 tasks at once/.test(s3.x) && /Among them: Sweep, Dust, Water plants/.test(s3.x) && /The agent writes:\s*Quick cleanup/.test(s3.q), 'the batch in words ' + JSON.stringify(s3));
    check(await ev(`(() => { const b = ${CARD(C3)}.querySelectorAll('.apvbtns .cchb')[1]; if (!b || b.disabled) return false; b.click(); return true; })()`), 'No is usable');
    check(await ready(ev, `!${CARD(C3)}?.classList.contains('apvopen')`), 'No answers the card');
  }, true);
  console.log(`p21269_d_apvdesc_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('CRASH', e); process.exit(1); });
