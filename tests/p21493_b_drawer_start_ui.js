// (#7617) the phone's drawer, area Start: under the tiles "Favourites" and "Recently opened" (Firefox, touch, 412 px)
// kalmido-suite: fresh
// - a favourite (Today) and a project opened before: both groups with their rows; a tap on the favourite opens it and
//   closes the drawer, a tap on the recent project opens the project and closes the drawer; a group folds like the others;
//   a row carries the workspace's colour mark like every row
// - no favourites and no history: no empty headings (and no area head over nothing)
// - a computer's sidebar stays as it was (no such groups)
const {execFileSync} = require('child_process');
const path = require('path');
const {B, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21493_b_drawer_start_ui', check, shots: 'P21493B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const lr = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', password: 'password123'})});
  const CK = lr.headers.get('set-cookie').split(';')[0];
  const call = async (method, url, body) => { const x = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {...(await x.json().catch(() => ({}))), http: x.status}; };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const ME = (await call('GET', '/api/state')).me;
  const ORG = ME?.workspaces?.[0]?.id || (await call('POST', '/api/admin/orgs', {name: 'Alpha Studio', admin_id: ME.id})).id;
  check(ORG > 0, 'setup: an organisation');
  const L = await call('POST', '/api/lists', {name: 'Shoot Berlin', org_id: ORG});
  check(L.id > 0, 'setup: a project ' + L.http);

  const G = (g, sel = '') => `#side.open .sgroup[data-sbmh="${g}"]${sel}`;
  await firefox(async o => {
    const {cmd, ev, ctx, shot, until, nav, idle} = o;
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    const open = async hash => {
      await nav(B + '#' + hash);
      await until(`typeof S !== 'undefined' && !!S.booted && !!document.querySelector('#top h1')`); await idle();
      await ev(`(() => { document.querySelector('#top [data-act="side"]').click(); return 1; })()`);
      await until(`!!document.querySelector('#side.open .sbmr')`); await sleep(300);
    };

    // ================= nothing yet: no empty headings
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({fav_items: []})}).then(r => r.status)`);
    await ev(`(localStorage.removeItem('tasks.recentViewed'), localStorage.removeItem('recentViewed'), 1)`);
    await open('home');
    const e0 = await ev(`({favs: !!document.querySelector('${G('home:favs')}'), rec: !!document.querySelector('${G('home:recent')}'), head: !!document.querySelector('#side.open .sbah')})`);
    check(!e0.favs && !e0.rec, 'no favourites, no history: no empty group ' + JSON.stringify(e0));
    check(!e0.head, 'and no area head over nothing ' + JSON.stringify(e0));

    // ================= a favourite and a project opened before
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({fav_items: ['v:today']})}).then(r => r.status)`);
    await nav(B + `#l/${L.id}`);
    await until(`typeof S !== 'undefined' && !!S.booted && S.route.key === 'l:${L.id}'`); await idle();
    await open('home');
    const m = await until(`(() => { const f = document.querySelector('${G('home:favs')}'), r = document.querySelector('${G('home:recent')}'); if (!f || !r) return null;
      const rows = g => [...g.querySelectorAll('.srow')].map(x => x.textContent.trim());
      return {fh: f.querySelector('.sgt')?.textContent.trim(), rh: r.querySelector('.sgt')?.textContent.trim(), favs: rows(f), rec: rows(r), below: f.getBoundingClientRect().top > document.querySelector('#side .sbmr').getBoundingClientRect().bottom - 1}; })()`);
    check(!!m, 'Start open: both groups are there');
    check(m && m.fh === 'Favourites' && m.rh === 'Recently opened', 'their headings ' + JSON.stringify(m));
    check(m && m.favs.includes('Today'), 'the favourite row ' + JSON.stringify(m));
    check(m && m.rec.includes('Shoot Berlin'), 'the recent project row ' + JSON.stringify(m));
    check(m && m.below, 'the groups stand under the tiles');
    // the rows carry the workspace's colour mark like every row (product rule: organisation colour everywhere)
    const mk = await ev(`(() => { const r = [...document.querySelectorAll('${G('home:recent', ' .srow')}')].find(x => x.textContent.includes('Shoot Berlin')); const l = listById(${L.id}); return {want: !!wso_row(wsOf(l)), has: !!r?.hasAttribute('data-wso')}; })()`);
    check(mk.want && mk.has, 'the recent project row (in the organisation) carries the workspace mark ' + JSON.stringify(mk));
    await shot('p21493b-start-412.png');
    // a group folds like the others and opens again
    await ev(`(() => { document.querySelector('${G('home:recent', ' .sgt')}').click(); return 1; })()`);
    check(await until(`!document.querySelector('${G('home:recent', ' .srow')}') && !!document.querySelector('${G('home:recent')}')`), 'a tap on the heading folds the group');
    await ev(`(() => { document.querySelector('${G('home:recent', ' .sgt')}').click(); return 1; })()`);
    check(await until(`!!document.querySelector('${G('home:recent', ' .srow')}')`), 'and unfolds it again');
    // the favourite: opens Today, the drawer closes
    await ev(`(() => { [...document.querySelectorAll('${G('home:favs', ' .srow')}')].find(x => x.textContent.includes('Today')).click(); return 1; })()`);
    check(await until(`location.hash === '#today' && !document.querySelector('#side.open')`), 'the favourite opens Today and the drawer closes: ' + await ev('location.hash'));
    // the recent project: opens it, the drawer closes
    await open('home');
    await until(`!!document.querySelector('${G('home:recent', ' .srow')}')`);
    await ev(`(() => { [...document.querySelectorAll('${G('home:recent', ' .srow')}')].find(x => x.textContent.includes('Shoot Berlin')).click(); return 1; })()`);
    check(await until(`S.route.key === 'l:${L.id}' && !document.querySelector('#side.open')`), 'the recent project opens and the drawer closes: ' + await ev('location.hash'));
  }, true);

  // ================= a computer: the sidebar has no such groups
  await firefox(async o => {
    const {cmd, ev, ctx, until, nav, idle} = o;
    await nav(B + 'static/icon.svg');
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 900}});
    await nav(B + '#home');
    await until(`typeof S !== 'undefined' && !!S.booted && !!document.querySelector('#top h1, #kbar')`); await idle();
    check(!await ev(`!!document.querySelector('[data-sbmh]')`), 'a computer: no drawer groups in the sidebar');
  });

  console.log(`p21493_b_drawer_start_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21493_b_drawer_start_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
