// (#7534, #7530) UI tests, own container (start.sh):
// kalmido-suite: fresh
// - #7534: the agent chat has the four kinds above its box (Question, Instruction, Proposal, Note); a pressed one goes with
//   the next message only (then none again); the message shows its kind and "waiting for an answer from <agent>"; the task
//   panel shows the kinds only while an agent hears the task
// - #7530: an agent's buttons with a bound step show the step under their label, an option without one "answer only"; a
//   click runs the step (the task is parked) and the answer line says what ran
// Firefox 390 touch: the kinds stay one line (no wrap, nothing sideways), the step label is visible in the button
// freelancer-matrix: agents (a person without an organisation with a personal agent)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7530_steps_ui', check, shots: 'P7530_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,agents,kanban';
const V = B + 'api/v1';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call('PUT', '/api/admin/agent-policy', {user_agents: true});
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const FK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT}, FK);
  const FU = (await call('GET', '/api/state', null, FK)).me;
  const fa = await call('POST', '/api/my/agents', {username: 'helfer', display_name: 'Helfer', scopes: ['read', 'tasks:write', 'comments']}, FK);
  check(fa.id, 'setup: the personal agent ' + JSON.stringify(fa).slice(0, 200));
  const AGH = {Authorization: 'Bearer ' + fa.token, 'Content-Type': 'application/json'};
  const L = (await call('POST', '/api/lists', {name: 'Umzug'}, FK)).id;
  await call('PUT', `/api/lists/${L}/members`, {user_id: fa.id, role: 'edit'}, FK);
  const T = (await call('POST', '/api/tasks', {title: 'Kisten', list_id: L}, FK)).id;
  const T0 = (await call('POST', '/api/tasks', {title: 'Ohne Agent', list_id: L}, FK)).id;
  await call('PATCH', `/api/tasks/${T}`, {assignee_id: fa.id}, FK);
  const say = async (body, extra = {}) => (await fetch(V + `/agent/chats/${FU.id}`, {method: 'POST', headers: AGH, body: JSON.stringify({body, ...extra})})).json();
  const q = await say('Parken?', {task_id: T, choices: [{id: 'p', label: 'Parken', do: {kind: 'park', reason: 'nach dem Urlaub'}}, {id: 'n', label: 'Reden'}]});
  check(q.id && q.choices?.choices?.[0]?.do?.kind === 'park', 'setup: a chat question with a step ' + JSON.stringify(q).slice(0, 200));
  const cm = (d, id) => d.querySelector(`#chat-msgs .cmsg[data-mid="a:${id}"]`);

  // ================= jsdom: the chat
  let w = await boot({user: 'frida'}), d = w.document;
  w.eval(`chatOpen(${fa.id})`); await until(() => cm(d, q.id)?.querySelector('.cchb[data-cid="p"]'));
  const bp = cm(d, q.id).querySelector('.cchb[data-cid="p"]'), bn = cm(d, q.id).querySelector('.cchb[data-cid="n"]');
  check(/park: nach dem Urlaub/.test(bp?.querySelector('.cstep')?.textContent || ''), '#7530: the step stands at its button ' + (bp?.textContent || ''));
  check(/answer only/.test(bn?.querySelector('.cstep.none')?.textContent || ''), '#7530: an option without a step reads "answer only"');
  const bar = d.querySelector('.intbar[data-intbar="a:' + fa.id + '"]');
  check(bar && bar.querySelectorAll('.intsw').length === 4 && [...bar.querySelectorAll('.intsw')].map(x => x.textContent).join('|') === 'Question|Instruction|Proposal|Note',
    '#7534: the four kinds above the chat box ' + (bar?.textContent || 'none'));
  click(w, bar.querySelector('[data-intent="question"]'));
  check(bar.querySelector('[data-intent="question"]').getAttribute('aria-pressed') === 'true', '#7534: a pressed kind is marked (aria-pressed)');
  click(w, bar.querySelector('[data-intent="question"]'));
  check(!bar.querySelector('.intsw.on'), '#7534: pressed again: none (back out)');
  click(w, bar.querySelector('[data-intent="question"]'));
  d.querySelector('#chat-in').value = 'Wann kommt der Wagen?';
  click(w, d.querySelector('[data-act="chat-send"]'));
  const mine = () => [...d.querySelectorAll('#chat-msgs .cmsg.me')].find(x => /Wann kommt der Wagen/.test(x.textContent) && !/Sending/.test(x.textContent) && x.querySelector('.intmark'));
  await until(() => mine());
  check(/Question/.test(mine()?.querySelector('.inttag')?.textContent || '') && /waiting for an answer from Helfer/.test(mine()?.querySelector('.intwait')?.textContent || ''),
    '#7534: the message shows its kind and whom it waits for ' + (mine()?.querySelector('.intmark')?.textContent || 'none'));
  check(!d.querySelector('.intbar[data-intbar="a:' + fa.id + '"] .intsw.on'), '#7534: after sending no kind is chosen (it holds for one message)');
  // the step: a click parks the task, the answer line says so
  click(w, cm(d, q.id).querySelector('.cchb[data-cid="p"]'));
  await until(() => cm(d, q.id)?.querySelector('.cchoices.done'));
  check(/Done: park: nach dem Urlaub/.test(cm(d, q.id)?.querySelector('.cchans')?.textContent || ''), '#7530: the answer line names the step that ran ' + (cm(d, q.id)?.querySelector('.cchans')?.textContent || ''));
  const tk = await call('GET', `/api/tasks/${T}`, null, FK);
  check(tk.delivery === 'parked', '#7530: the task is parked ' + tk.delivery);
  w.close();

  // ================= jsdom: the task panel shows the kinds only while an agent hears the task
  w = await boot({user: 'frida', hash: 'l/' + L}); d = w.document;
  w.eval(`openDetail(${T})`); await until(() => d.querySelector('#c-int .intbar'));
  check(d.querySelectorAll('#c-int .intsw').length === 4, '#7534: the task the agent hears: the kinds above the comment box');
  w.eval(`openDetail(${T0})`); await until(() => w.eval('S.tl.id') === T0 && w.eval('Array.isArray(S.tl.hears)'));
  await sleep(300);
  check(!d.querySelector('#c-int .intbar'), '#7534: a task no agent hears: no kinds');
  w.close();

  // ================= Firefox 390 touch: one line, nothing sideways
  const ffLogin = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);
  };
  const q2 = await say('Weiter?', {task_id: T0, choices: [{id: 'd', label: 'Erledigt', do: {kind: 'state', state: 'done'}}, {id: 'n', label: 'Nein'}]});
  await firefox(async o => {
    const {cmd, ev, ctx, shot} = o;
    check(await ffLogin(o) === 200, '390: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 800}});
    await o.nav(B + '#agents/' + fa.id);
    for (let i = 0; i < 40 && !(await ev(`!!document.querySelector('.intbar .intsw') && !!document.querySelector('[data-mid="a:${q2.id}"] .cstep')`).catch(() => false)); i++) await sleep(300);
    const g = await ev(`(() => { const b = document.querySelector('.intbar'), s = [...b.querySelectorAll('.intsw')].map(x => x.getBoundingClientRect()), t = document.querySelector('[data-mid="a:${q2.id}"] .cstep');
      return {oneLine: s.every(r => Math.abs(r.top - s[0].top) < 2), h: Math.round(s[0].height), wide: document.documentElement.scrollWidth <= innerWidth,
        step: t ? Math.round(t.getBoundingClientRect().height) : 0, stepText: t ? t.textContent : ''}; })()`);
    check(g && g.oneLine && g.wide, '390: the four kinds stay one line, nothing sticks out sideways ' + JSON.stringify(g));
    check(g && g.h >= 32, '390: the kinds are big enough to tap ' + JSON.stringify(g));
    check(g && g.step > 0 && /mark as done/.test(g.stepText), '390: the step label shows in the button ' + JSON.stringify(g));
    await shot('p7530-390-chat.png');
  }, true);

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
