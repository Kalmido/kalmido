// 2.1208.0 UI test, part B (#6125 the start page is honest: loading instead of empty, nothing twice, one name for "Waiting for you").
// kalmido-suite: fresh
// jsdom, own container (start.sh; P21208B_NOSTART=1: a running server). Invented names only. The way a person sees it:
// - an empty account (no project, no task) sees the card "Getting started" with its steps and no grey "…: nothing" lines;
//   a step leads into an area (Create a project opens the dialog, the first step opens the inbox)
// - an account with a project but nothing to do: every empty sentence once ("Nothing waits for you" once, no "Waiting for
//   you: nothing", no "Nothing due today." above "Nothing left for today.")
// - an account with entries: every entry of the box "Waiting for you" stands exactly once on the page (the card News lists only
//   the others), the number once; "All news" is the link in the card's head
// - the bell's window is called "Waiting for you: N" (N = the bell's number), one way to all ("Show all" below, no second one)
// - loading: the card News and the box show the shared placeholder, not "Nothing waits for you"; failed: errorState with
//   "Try again", which loads and shows the entries; the team chat card the same
// freelancer-matrix: the empty account and alice are persons without an organisation (the start page has no own routes)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21208B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), status: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(fn, {timeout: ms, step: 150});
const ALL = 'cal,collab,stats,agents,comments,team';
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const txt = (d, s) => (d.querySelector(s)?.textContent || '').replace(/\s+/g, ' ').trim();
const count = (hay, needle) => hay.split(needle).length - 1;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ALL.split(',').filter(x => x !== 'collab')});
  await call('PATCH', '/api/settings', {features: ALL, lang: 'en', tour: 'done'});
  const BOB = (await call('POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123'})).id;
  const CB = await login('bob');
  await call('PATCH', '/api/settings', {features: ALL, lang: 'en', tour: 'done'}, CB);
  const DORA = (await call('POST', '/api/users', {username: 'dora', display_name: 'Dora', password: 'password123'})).id;
  const CD = await login('dora');
  await call('PATCH', '/api/settings', {features: ALL, lang: 'en', tour: 'done'}, CD);
  // the first start's "Getting started" list once, then away: dora has no project and no task (as an account that cleared it)
  await call('POST', '/api/onboarding', {}, CD);
  for (const l of (await call('GET', '/api/state', null, CD)).lists.filter(l => !l.is_inbox)) await call('DELETE', `/api/lists/${l.id}`, null, CD);
  const ds = await call('GET', '/api/state', null, CD);
  check(DORA > 0 && BOB > 0 && !ds.tasks.length && !ds.lists.some(l => !l.is_inbox), 'setup: bob and dora, dora without project and task ' + ds.tasks.length);

  // ================= an empty account: "Getting started" instead of grey lines
  let w = await boot({user: 'dora', hash: 'home'}), d = w.document;
  await until(() => d.querySelector('#view .dc-today')); await idle(w);
  const st = [...d.querySelectorAll('#view .dfirst .dfsteps li')].map(li => li.textContent.replace(/\s+/g, ' ').trim());
  check(/Getting started/.test(txt(d, '#view .dfirst h3')) && st.length === 4 && /first task/.test(st[0]) && /project/.test(st[1]), 'empty account: the card "Getting started" with 4 steps ' + JSON.stringify(st));
  check(!d.querySelector('#view .dempty') && !/: nothing/.test(txt(d, '#view')), 'empty account: no grey "…: nothing" lines: ' + txt(d, '#view').slice(0, 300));
  const v0 = txt(d, '#view');
  check(count(v0, 'Nothing waits for you') <= 1 && !(/Nothing due today/.test(v0) && /Nothing left for today/.test(v0)), 'empty account: no sentence twice: ' + v0.slice(0, 300));
  click(w, d.querySelector('#view .dfirst [data-hpfirst="project"]'));
  check(await until(() => d.querySelector('.modal input')), 'Getting started: "Create a project" opens the dialog');
  d.querySelector('.modal')?.remove();
  click(w, d.querySelector('#view .dfirst a[href="#inbox"]')); w.location.hash = '#inbox';
  check(await until(() => w.eval('S.route.key') === 'inbox'), 'Getting started: the first step leads into the inbox');
  w.close();

  // ================= the same account with a project, nothing to do: every empty sentence once
  const P = (await call('POST', '/api/lists', {name: 'Garden plan', kind: 'project'}, CD)).id;
  check(P > 0, 'dora has a project');
  w = await boot({user: 'dora', hash: 'home'}); d = w.document;
  await until(() => d.querySelector('#view .dc-today') && /Nothing waits for you/.test(txt(d, '#view'))); await idle(w);
  const v1 = txt(d, '#view');
  check(!d.querySelector('#view .dfirst'), 'with a project: no "Getting started"');
  check(count(v1, 'Nothing waits for you') === 1 && !/Waiting for you: nothing/.test(v1), '"Nothing waits for you" stands once (no "Waiting for you: nothing"): ' + v1.slice(0, 300));
  check(/Nothing left for today/.test(txt(d, '#view .dc-today')) && !/Nothing due today/.test(v1), 'today: one sentence, in the card Today');
  w.close();

  // ================= alice with six entries for her: each once on the page
  const SH = (await call('POST', '/api/lists', {name: 'Shared work', kind: 'project'})).id;
  await call('PUT', `/api/lists/${SH}/members`, {user_id: BOB, role: 'edit'});
  const NAMES = ['Paint the fence', 'Order the tiles', 'Book the van', 'Call the plumber', 'Measure the hall', 'Sort the cables'];
  for (const n of NAMES) { const t = (await call('POST', '/api/tasks', {title: n, list_id: SH}, CB)).id; await call('POST', `/api/tasks/${t}/comments`, {body: '<@1> please have a look'}, CB); }
  const srv = await call('GET', '/api/news');
  check(srv.unread_me === 6, 'setup: six entries wait for alice: ' + srv.unread_me);
  w = await boot({user: 'alice', hash: 'home'}); d = w.document;
  await until(() => d.querySelectorAll('#view .dtome .dwl li').length >= 4 && d.querySelector('#view .dc-news .hpnl li')); await idle(w);
  const page = txt(d, '#view .dash');
  const twice = NAMES.filter(n => count(page, n) !== 1);
  check(!twice.length, 'every entry stands exactly once (box + card News): ' + twice.map(n => n + '=' + count(page, n)).join(', '));
  const inBox = NAMES.filter(n => txt(d, '#view .dtome').includes(n)), inCard = NAMES.filter(n => txt(d, '#view .dc-news').includes(n));
  check(inBox.length === 4 && inCard.length === 2 && !inCard.some(n => inBox.includes(n)), `box ${inBox.length}, card News the other ${inCard.length}`);
  check(/Waiting for you: 6/.test(txt(d, '#view .dtome h3')) && !d.querySelector('#view .dc-news h3 .dcn') && count(page, 'Waiting for you') === 1, 'the number once, in the box: ' + txt(d, '#view .dtome h3'));
  check(d.querySelector('#view .dc-news h3 a[href="#news"]')?.textContent === 'All news' && !d.querySelector('#view .dc-news > a, #view .dc-news .hpall'), '"All news" is the link in the card\'s head');

  // ================= the bell's window: one name, one number, one way to all
  const bell = d.querySelector('#kbar .bell');
  check(/^Waiting for you: 6$/.test(bell?.getAttribute('aria-label') || ''), 'the bell is called "Waiting for you: 6": ' + bell?.getAttribute('aria-label'));
  click(w, bell); await until(() => d.querySelector('#pop .bpop .ngroup'));
  check(txt(d, '#pop #bp-h') === 'Waiting for you: ' + (bell.querySelector('.nbadge')?.textContent || '?'), 'the window\'s title = the bell\'s number: ' + txt(d, '#pop #bp-h'));
  check(!d.querySelector('#pop .bphl') && !/\d+ for you/.test(txt(d, '#pop .bphead')) && d.querySelectorAll('#pop [data-bp="all"], #pop [data-bp="news"]').length === 1, 'one way to all ("Show all" below), no "N for you"');
  click(w, d.querySelector('#pop [data-bp="all"]'));
  check(await until(() => w.eval('S.route.mod') === 'news'), '"Show all" opens the whole list');
  w.eval(`go('home')`); await until(() => d.querySelector('#view .dc-news .hpnl li'));

  // ================= loading and failed: the shared blocks, never the empty sentence
  w.eval(`S.nf.items = null; S.nf.err = null; S.nf.loading = true; renderView()`);
  check(d.querySelector('#view .dc-news .eload') && d.querySelector('#view .dtome .eload') && !/Nothing waits for you/.test(txt(d, '#view')), 'loading: a placeholder in the card News and in the box, no "Nothing waits for you"');
  w.eval(`S.nf.loading = false; S.nf.err = 'Server error'; renderView()`);
  const retry = d.querySelector('#view .dc-news .eerr [data-esretry]');
  check(retry && /Try again/.test(retry.textContent) && /Could not be loaded/.test(txt(d, '#view .dc-news')) && !/Nothing waits for you/.test(txt(d, '#view')), 'failed: "Could not be loaded" with "Try again": ' + txt(d, '#view .dc-news'));
  await sleep(50);
  check(w.eval('S.nf.items === null && !S.nf.loading'), 'failed: no new request on every draw');
  click(w, retry);
  check(await until(() => d.querySelector('#view .dc-news .hpnl li') && !d.querySelector('#view .eerr')), '"Try again" loads and shows the entries');
  if (w.eval('teamOn()')) {
    w.eval(`S.tc.rooms = null; S.tc.loading = false; S.tc.err = 'Server error'; renderView()`);
    const r2 = d.querySelector('#view .dc-chat .eerr [data-esretry]');
    check(r2 && !/Team chat: nothing/.test(txt(d, '#view')), 'team chat failed: "Try again" instead of "Team chat: nothing"');
    click(w, r2);
    check(await until(() => d.querySelector('#view .dc-chat') && !d.querySelector('#view .dc-chat .eerr, #view .dc-chat .eload')), 'team chat: "Try again" loads it');
  } else check(false, 'setup: the team chat is on');
  w.close();

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
