// 2.1213.0 Part C (#6126): the start page on computer and tablet (own container, start.sh).
// kalmido-suite: fresh
// jsdom (computer, Alice with the organisation "Acme", the workspace Private shown): the page is titled "Start" beside the sidebar,
// the phone keeps the active tab's name; the deadline lines of the box "Waiting for you" are split per workspace - the line of the
// shown one says what the Today card and the sentence on top count, the line of Acme carries Acme's dot + name; a news item and a
// team chat room of Acme carry the mark, the shown workspace's do not; projects without a status: the editor says why the
// Projects card stays away. Firefox (mouse): 1280 x 900 "Start", no tab bar; 820 x 1000 no narrow block alone in its row (no hole
// in the right column). Screenshots into $P21213C_SHOTS.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21213_c_start_ui', check, shots: 'P21213C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const TC = require('./testclock');
const T0 = TC.today();
const txt = (e) => (e?.textContent || '').replace(/\s+/g, ' ').trim();
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'collab']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab', workspace: 'private'});
  const ORG = (await call('POST', '/api/orgs', {name: 'Acme'})).id;
  const PL = (await call('POST', '/api/lists', {name: 'Garden', org_id: null})).id;
  const OL = (await call('POST', '/api/lists', {name: 'Requests', org_id: ORG})).id;
  const PT = (await call('POST', '/api/tasks', {title: 'Water the hedge', list_id: PL, due: T0})).id;
  const OT = (await call('POST', '/api/tasks', {title: 'Answer the client', list_id: OL, due: T0})).id;
  check(ORG && PL && OL && PT && OT, 'setup: an organisation, a private and an organisation list, one task due today in each ' + JSON.stringify([ORG, PL, OL, PT, OT]));

  // ================= jsdom, computer: title, the box's lines per workspace, the Today card and the sentence count alike
  let w = await boot({user: 'alice', hash: 'home'}), d = w.document;
  check(await until(() => d.querySelector('#view .hpsum') && d.querySelector('.dc-today .dtl li') && d.querySelector('.dtome .dwl li')), 'the start page with the sentence, the Today card and the box');
  check(w.eval('wsOn() && wsCur()') === 'private', 'Private is the shown workspace: ' + w.eval('wsCur()'));
  check(txt(d.querySelector('#top h1 .ht')) === 'Start', '#6126: a computer (sidebar, no tab bar): the page is "Start": ' + txt(d.querySelector('#top h1 .ht')));
  const today = [...d.querySelectorAll('.dc-today .dtl li')].map(txt), sum = txt(d.querySelector('.hpsum'));
  check(today.length === 1 && /Water the hedge/.test(today[0]), '#6126: the Today card shows the shown workspace only: ' + today.join(' | '));
  check(/^1 task for today/.test(sum), '#6126: the sentence counts the same: ' + sum);
  const box = [...d.querySelectorAll('.dtome .dwl li')], due = box.filter(li => /due today/.test(li.textContent));
  const own = due.filter(li => !li.querySelector('.hpws')), other = due.filter(li => li.querySelector('.hpws'));
  check(own.length === 1 && /^1 task due today/.test(txt(own[0])), '#6126: the box\'s line of the shown workspace says 1 like the Today card: ' + due.map(txt).join(' | '));
  check(other.length === 1 && /1 task due today/.test(txt(other[0].querySelector('.dwt'))) && other[0].querySelector('.hpws .wsp-dot') && /Acme/.test(other[0].querySelector('.hpws').textContent),
    '#6126: Acme\'s line carries its dot + name: ' + other.map(li => li.innerHTML).join(' | '));
  check(/Requests/.test(other[0]?.querySelector('.hpws')?.getAttribute('title') || ''), '#6126: the mark names the list in its title: ' + other[0]?.querySelector('.hpws')?.getAttribute('title'));
  check(!/nothing left for today/i.test(txt(d.querySelector('.dc-today'))), '#6126: the Today card does not say "nothing left" beside a line due today');
  // a news item and a team chat room of Acme: its mark; of the shown workspace: none (the data of the bell / the team chat, put in)
  w.eval(`S.nf.items = [{kind: 'assign', to_me: true, read: false, list_id: ${OL}, task_id: ${OT}, task_title: 'Answer the client', actor_id: S.me.id, data: {}, created_at: new Date().toISOString()},
    {kind: 'assign', to_me: true, read: false, list_id: ${PL}, task_id: ${PT}, task_title: 'Water the hedge', actor_id: S.me.id, data: {}, created_at: new Date().toISOString()}]; S.nf.sig = S.news?.sig ?? ''; renderView();`);
  await until(() => [...d.querySelectorAll('.dtome .dwl li')].some(li => /Answer the client/.test(li.textContent)));
  const nAcme = [...d.querySelectorAll('.dtome .dwl li')].find(li => /Answer the client/.test(li.textContent)), nOwn = [...d.querySelectorAll('.dtome .dwl li')].find(li => /Water the hedge/.test(li.textContent));
  check(nAcme && /Acme/.test(txt(nAcme.querySelector('.hpws'))) && nAcme.querySelector('.hpws .wsp-dot'), '#6126: an item of Acme in the box: dot + "Acme" ' + (nAcme?.innerHTML || 'missing'));
  check(nOwn && !nOwn.querySelector('.hpws'), '#6126: an item of the shown workspace: no mark');
  const chat = w.eval(`(() => { S.team = {...(S.team || {}), enabled: true}; S.tc.rooms = [{id: 990001, kind: 'list', list_id: ${OL}, name: 'Requests', last: {text: 'Hello'}, unread: 0},
    {id: 990002, kind: 'list', list_id: ${PL}, name: 'Garden', last: {text: 'Hi'}, unread: 0}]; return dashCard('chat'); })()`);
  const cd = d.createElement('div'); cd.innerHTML = chat;
  const rows = [...cd.querySelectorAll('.dwl li')];
  check(rows.length === 2 && /Acme/.test(txt(rows[0].querySelector('.hpws.hpwsn'))) && !rows[1].querySelector('.hpws'), '#6126: Team chat: the room of Acme carries Acme, the private one nothing ' + rows.map(li => li.innerHTML).join(' | '));
  // "All workspaces" shown: nothing is "another" workspace - no mark on the start page's lines
  w.eval(`S.settings.workspace = 'all'; renderView();`);
  await until(() => !d.querySelector('.dtome .hpws'));
  check(!d.querySelector('.dtome .hpws'), '#6126: under "All workspaces" no line carries a workspace mark');
  w.eval(`S.settings.workspace = 'private'; renderView();`);
  // the Projects card: projects without a status - away on the page, the editor says why
  await until(() => d.querySelector('.dash .dashhead .lycust'));
  check(!/projects without a status/.test(d.querySelector('#view').textContent), 'the page itself: no sentence about the Projects card');
  click(w, d.querySelector('.dash .dashhead .lycust'));
  check(await until(() => /The card does not show projects without a status/.test(d.querySelector('#view').textContent)), '#6126: in the editor: "The card does not show projects without a status"');
  await call('POST', `/api/lists/${PL}/status`, {status: 'on_track', note: ''});
  w.close();

  // ================= jsdom, phone: the tab bar shows - the title is the active tab's name (#5963 stays)
  w = await boot({user: 'alice', hash: 'home', mobile: true}); d = w.document;
  check(await until(() => d.querySelector('#tabs button.on') && d.querySelector('#top h1 .ht')), 'phone: tab bar and title');
  check(txt(d.querySelector('#tabs button.on')) === txt(d.querySelector('#top h1 .ht')), `#5963: phone: active tab and title have one name: "${txt(d.querySelector('#tabs button.on'))}" / "${txt(d.querySelector('#top h1 .ht'))}"`);
  w.close();

  // ================= Firefox, mouse: 1280 the title, 820 the grid without holes
  if (process.env.NOFF) { console.log(`${ok} ok, ${F.length} failed`); process.exit(F.length ? 1 : 0); }
  await firefox(async o => {
    const {cmd, ev, ctx, shot, nav} = o;
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'login');
    const ready = async () => { for (let i = 0; i < 40 && !(await ev(`!!document.querySelector('.dc-today .dtl li') && !!document.querySelector('.lysix .lyb')`).catch(() => false)); i++) await sleep(300); };
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + '#home'); await ready();
    const t = await ev(`(() => { const tb = document.querySelector('#tabs'); return {title: (document.querySelector('#top h1 .ht') || {}).textContent, tabs: !!tb && getComputedStyle(tb).display !== 'none' && tb.getBoundingClientRect().height > 0}; })()`);
    check(t.title === 'Start' && !t.tabs, '#6126: 1280: title Start, no tab bar ' + JSON.stringify(t));
    await shot('p21213c-1280.png');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 820, height: 1000}});
    await nav(B + '#home'); await ready();
    for (let i = 0; i < 20 && !(await ev(`!!document.querySelector('.dtome .dwl li')`).catch(() => false)); i++) await sleep(300);
    await sleep(600);
    // every block narrower than the grid has a neighbour in its row: no empty right column beside a lone tile
    const g = await ev(`(() => { const gr = document.querySelector('.lysix'); if (!gr) return null; const gw = gr.getBoundingClientRect().width;
      const bs = [...gr.querySelectorAll('.lyb')].map(b => { const x = b.getBoundingClientRect(); return {k: b.dataset.lyk, top: Math.round(x.top), w: Math.round(x.width)}; }).filter(b => b.w > 0);
      return {gw: Math.round(gw), bs, title: (document.querySelector('#top h1 .ht') || {}).textContent, sw: document.documentElement.scrollWidth}; })()`);
    check(g && g.bs.length >= 2, '820: the start page has blocks ' + JSON.stringify(g));
    const lone = (g?.bs || []).filter(b => b.w < g.gw * 0.75 && !g.bs.some(x => x !== b && Math.abs(x.top - b.top) <= 2));
    check(g && !lone.length, '#6126: 820: no narrow block alone in its row (no hole beside it): ' + JSON.stringify(lone) + ' of ' + JSON.stringify(g?.bs));
    check(g && g.title === 'Start' && g.sw <= 820, '#6126: 820 (sidebar): title Start, nothing sideways ' + JSON.stringify({title: g?.title, sw: g?.sw}));
    await shot('p21213c-820.png');
  });

  console.log(`${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
