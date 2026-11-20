// kalmido-suite: fresh
// UI test (#7386): the phone's drawer, the icon Projects (Firefox, 412 x 915 like the report's Android Chrome).
// freelancer-matrix: n/a (no new route; alice runs it in "All workspaces" and in one organisation, the drawer is the same without one)
// The bug: a task opened over another page (#t/<id> from Agents) keeps that page's key under it ({mod: tasks, key: agents}); the
// router kept 'agents' as the last Projects view (LS lastKey) and the icon Projects in the drawer led to the Agents page.
// - a task opened from Agents, then another area: the icon Projects opens a Projects view (not Agents)
// - a device that already kept the wrong key (lastKey = agents, sbbLast.tasks = agents): the icon Projects still opens Projects
// - from every other area shown in the drawer the icon Projects lands in Projects; tapped in Projects it opens the start page
// - both workspace states: All workspaces and one organisation. Invented names only.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7386_drawer_projects_ui', check, shots: 'P7386_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const MODS = 'cal,comments,office,contacts,wiki,sheets,habits,time,review,agents,reading,collab';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'de'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'de', collab_all: true, time_all: true, modules: MODS.split(',')});
  await call(CA, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: MODS, workspace: 'all'});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Beispiel Werkstatt', admin_id: me.id});
  check(org.http < 300, 'organisation ' + org.http);
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Gartenplan'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Beete umgraben', list_id: L})).id;
  const ag = await call(CA, 'POST', '/api/admin/agents', {scopes: ['read'], username: 'wolke', display_name: 'Wolke'});
  check(ag.id && T, 'an agent and a task ' + ag.http);

  await firefox(async ({cmd, ev, nav, ctx, shot, until}) => {
    const wait = s => until(() => ev(s));
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 915}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'login');
    await nav(B + '#inbox'); await wait(`!!S.booted`);
    const goTo = async h => { await ev(`(() => { go(${JSON.stringify(h)}); return 1; })()`); return wait(`location.hash === ${JSON.stringify('#' + h)} && !!S.route`); };
    const open = async () => { await ev(`(() => { if (!document.querySelector('#side.open')) document.querySelector('#top .menu')?.click(); return 1; })()`); return wait(`!!document.querySelector('#side.open .sbmr .srb[data-sbb="tasks"]')`); };
    // a tap on the icon Projects as a finger does it (the drawer's own click handler, sbm_go); the result: where the page is now
    const tapProjects = async () => {
      check(await open(), 'the drawer opens');
      const before = await ev(`location.hash`);
      await ev(`(() => { document.querySelector('#side .sbmr .srb[data-sbb="tasks"]').click(); return 1; })()`);
      await wait(`location.hash !== ${JSON.stringify(before)} || !document.querySelector('#side.open')`);
      await wait(`S.route.mod === 'tasks' || S.route.mod !== ${JSON.stringify((await ev('S.route.mod')))}`);
      return ev(`({hash: location.hash, mod: S.route.mod, key: S.route.key, area: sbb_area()})`);
    };
    const inProjects = r => r.mod === 'tasks' && r.area === 'tasks' && !/^#(agents|job)\b/.test(r.hash);

    for (const ws of ['all', 'org:' + org.id]) {
      await ev(`(() => { wsSet(${JSON.stringify(ws)}); return 1; })()`);
      check(await wait(`wsCur() === ${JSON.stringify(ws)}`), `${ws}: the workspace is set`);
      // 1) the report's way: a task opened over the Agents page, then another area, then the icon Projects
      if (await ev(`agentsTab()`)) {
        await goTo('agents');
        await ev(`(() => { location.hash = 't/${T}'; return 1; })()`);
        await wait(`S.sel === ${T} || !!document.querySelector('#detail')`);
        await goTo('cal');
        const r = await tapProjects();
        check(inProjects(r), `#7386 ${ws}: a task opened over Agents, then the icon Projects opens Projects, not Agents ` + JSON.stringify(r));
        check(await ev(`LS.get('lastKey', START_KEY) !== 'agents'`), `#7386 ${ws}: Agents is not kept as the last Projects view`);
      }
      // 2) a device that kept the wrong key before the fix
      await goTo('cal');
      await ev(`(() => { LS.set('lastKey', 'agents'); const o = LS.get('sbbLast', {}) || {}; o.tasks = 'agents'; LS.set('sbbLast', o); render(); return 1; })()`);
      const r2 = await tapProjects();
      check(inProjects(r2), `#7386 ${ws}: a kept key of Agents still leads Projects into Projects ` + JSON.stringify(r2));
      // 3) from every other area shown in the drawer
      check(await open(), `${ws}: the drawer opens`);
      const ids = await ev(`[...document.querySelectorAll('#side .sbmr .srb[data-sbb]')].map(b => b.dataset.sbb).filter(x => x !== 'tasks')`);
      check(ids.length >= 4, `${ws}: the drawer shows several areas ` + JSON.stringify(ids));
      for (const id of ids) {
        check(await open(), `${ws}: the drawer opens for ${id}`);
        await ev(`(() => { document.querySelector('#side .sbmr .srb[data-sbb="${id}"]').click(); return 1; })()`);
        await wait(`sbb_area() === ${JSON.stringify(id)}`);
        const r = await tapProjects();
        check(inProjects(r), `#7386 ${ws}: from ${id} the icon Projects opens Projects ` + JSON.stringify(r));
      }
      // 4) in Projects itself: the start page of Projects
      const r4 = await tapProjects();
      check(r4.hash === '#projects' && inProjects(r4), `#7386 ${ws}: the icon Projects in Projects opens its start page ` + JSON.stringify(r4));
      await shot(`p7386-${ws.replace(':', '-')}.png`);
    }
  }, true);
  console.log(F.length ? `p7386_drawer_projects_ui: ${F.length} FAILED, ${ok} passed` : `p7386_drawer_projects_ui: all ${ok} passed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
