// Package 2.1205.0 (#6133) UI test: an address into nothing.
// kalmido-suite: fresh
// A project address without a project (deleted, no access, a typo) showed the title "Project", "No tasks.", "+ Section" and the
// field "Add task…" (adding led nowhere); it shows the shared no-access block now with "To the projects", no add field, no
// section, no +, and it is no next start. An unknown address still lands in the Basket, with the hint "This page does not exist".
// Own container (start.sh), Firefox (a computer, then a phone); invented projects only.
// freelancer-matrix: lists (alice has no organisation)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21205_a_route_gone_ui', check, shots: 'P21205_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21205_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const st0 = await call('GET', '/api/state');
  check(!(st0.me.workspaces || []).length, 'setup: alice has no organisation (a person on her own)');
  const SHOOT = (await call('POST', '/api/lists', {name: 'Shoot day', kind: 'project'})).id;
  const GONE = (await call('POST', '/api/lists', {name: 'Old campaign', kind: 'project'})).id;
  check(SHOOT && GONE, 'setup: two projects');
  await call('PATCH', `/api/lists/${GONE}`, {archived: 1});  // a project is archived before it can be deleted
  check((await call('DELETE', `/api/lists/${GONE}`)).trash === true, 'setup: one project deleted (into the trash)');
  const login2 = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  // what the view shows: the block, its button, the add field, a section, the +
  const SEEN = `(() => { const v = document.querySelector('#view'), b = v.querySelector('.enoacc'), vis = e => !!e && !!(e.offsetWidth || e.offsetHeight);
    return {block: b ? b.textContent.trim() : null, btn: vis(v.querySelector('.enoacc [data-go="projects"]')), add: vis(document.querySelector('#qinput')),
      section: /Section/.test(v.textContent), noTasks: /No tasks/.test(v.textContent), tnew: vis(document.querySelector('#top .tnew')), fab: vis(document.querySelector('#fab')) && !document.querySelector('#fab').classList.contains('gone')}; })()`;

  for (const [w, h, tag] of [[1280, 900, 'desktop'], [390, 800, 'phone']]) {
    await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
      await nav(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
      check(await login2(ev) === 200, `${tag}: login`);
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
      // a project that never was (a typo) and one that was deleted: the same block
      for (const [id, what] of [[987654, 'a typo'], [GONE, 'deleted']]) {
        await nav(B + `?w=${w}&r=${id}#l/${id}`);
        const s = await until(`(() => { const s = ${SEEN}; return s.block ? s : null; })()`, {timeout: 20000});
        check(s && /This project does not exist \(any more\) or you have no access/.test(s.block), `#6133 ${tag} ${what}: the no-access block ${JSON.stringify(s)}`);
        check(s && s.btn, `#6133 ${tag} ${what}: the button "To the projects" is there`);
        check(s && !s.add && !s.section && !s.noTasks, `#6133 ${tag} ${what}: no "Add task…", no section, no "No tasks." (was an empty project) ${JSON.stringify(s)}`);
        check(s && !s.tnew && !s.fab, `#6133 ${tag} ${what}: no "New task" / + (nothing could be added there) ${JSON.stringify(s)}`);
        const lk = await ev(`localStorage.getItem('tasks.lastKey') || ''`);
        check(!new RegExp(`l:${id}`).test(lk), `#6133 ${tag} ${what}: the address is no next start (${lk})`);
      }
      await shot(`p21205a-gone-${tag}.png`);
      // the way out: the projects
      await ev(`(() => { document.querySelector('#view .enoacc [data-go="projects"]').click(); return 1; })()`);
      check(await until(`location.hash === '#projects' && /Shoot day/.test(document.querySelector('#view').textContent)`, {timeout: 20000}), `#6133 ${tag}: "To the projects" leads to the projects (Shoot day listed)`);
      // a project that is there keeps its add field (no block)
      await ev(`(() => { location.hash = 'l/${SHOOT}'; return 1; })()`);
      const live = await until(`(() => { const s = ${SEEN}; return /Shoot day/.test(document.querySelector('#top h1')?.textContent || '') ? s : null; })()`, {timeout: 20000});
      check(live && !live.block && (live.add || live.fab || live.tnew), `#6133 ${tag}: a project that is there: no block, a way to add ${JSON.stringify(live)}`);
      // an unknown address: the Basket with a hint
      await ev(`(() => { location.hash = 'gibtesnicht/42'; return 1; })()`);
      const un = await until(`(() => { const t = document.querySelector('#toast'); return S.route.key === 'inbox' && t && !t.classList.contains('hidden') && /This page does not exist/.test(t.textContent) ? {key: S.route.key, toast: t.textContent} : null; })()`, {timeout: 20000});
      check(!!un, `#6133 ${tag}: an unknown address lands in the Basket with "This page does not exist" ${JSON.stringify(un)}`);
      await shot(`p21205a-unknown-${tag}.png`);
    });
  }

  console.log(`p21205_a_route_gone_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
