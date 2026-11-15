// 2.1184.0 (#6137) Polish lists 2: "Recent steps" after a project's settings. Own container (start.sh), Firefox. Invented data only.
// kalmido-suite: fresh
// freelancer-matrix: undo (frida has no organisation: her project's steps on the page #steps)
// - a project's colour change and its sorting are listed with what changed ("“Imagefilm Sommerkampagne”: Colour"), not as
//   "Settings of …"; switching the project's view (list / kanban / list) three times leaves no row
// - a phone (360 x 740): the row's label stands whole above its button "Back up to here" (no cut text beside it), nothing is
//   wider than the screen; the button takes the colour back
// - a computer: the button stays beside the label in one line
// Screenshots into $P21184A_SHOTS.
// usage: node p21184_a_steps_phone_ui.js <datadir>
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21184_a_steps', check, shots: 'P21184A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const NAME = 'Imagefilm Sommerkampagne';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Beispiel Studio', lang: 'en', collab_all: true, modules: ['comments']});
  check((await call('POST', '/api/users', {username: 'frida', display_name: 'frida', password: 'password123', email: 'frida@example.com', orgs: []})).http < 300, 'user frida');
  const FK = await login('frida');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, FK);
  const L = (await call('POST', '/api/lists', {name: NAME, color: '#3366cc'}, FK)).id;
  check(!!L, 'frida\'s project');
  const c1 = await call('PATCH', `/api/lists/${L}`, {color: '#cc3333'}, FK);
  for (const v of ['kanban', 'list', 'kanban']) {
    const x = await call('PATCH', `/api/lists/${L}`, {view: v}, FK);
    check(x.http === 200 && !x.undo_group, `the view ${v}: no step (${x.http} ${x.undo_group})`);
  }
  const c2 = await call('PATCH', `/api/lists/${L}`, {sort_mode: 'date'}, FK);
  const items = (await call('GET', '/api/undo', null, FK)).items || [];
  const mine = items.filter(g => g.kind === 'listset');
  check(c1.undo_group && c2.undo_group && mine.length === 2, `two steps of the project, none of the view switches ${JSON.stringify(items.map(g => [g.kind, g.label]))}`);
  check(mine.some(g => g.label === `“${NAME}”: Colour`) && mine.some(g => g.label === `“${NAME}”: Sorting`), `the steps say what changed ${JSON.stringify(mine.map(g => g.label))}`);

  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);
  // the row of the colour step: its label whole (not cut), its place against the button
  const rowOf = gid => `(() => {
    const li = document.querySelector('#view .ulbody .ulrow[data-ul="s:${gid}"]'); if (!li) return null;
    const lab = li.querySelector('.ullab'), btn = li.querySelector('[data-ul-go], [data-ul-redo]'); if (!lab || !btn) return null;
    const a = lab.getBoundingClientRect(), b = btn.getBoundingClientRect();
    return {text: lab.textContent, whole: lab.scrollWidth <= lab.clientWidth + 1, above: a.bottom <= b.top + 1, beside: b.left >= a.right - 1 && b.top < a.bottom,
      btn: btn.textContent.trim(), seen: b.bottom <= innerHeight && b.right <= innerWidth, wide: document.documentElement.scrollWidth <= innerWidth};
  })()`;
  const G1 = mine.find(g => /Colour$/.test(g.label)) || {};

  // ================= a phone, 360 x 740
  await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await signIn(ev) === 200, 'phone: frida signed in');
    await nav(B + '#steps');
    const row = await until(`(() => { const x = ${rowOf(G1.id)}; return x && /Colour/.test(x.text) ? x : null; })()`, {timeout: 20000});
    check(row && row.text === `“${NAME}”: Colour`, 'phone: the row names the colour: ' + JSON.stringify(row));
    check(row && row.whole && row.above, 'phone: the label stands whole above its button ' + JSON.stringify(row));
    check(row && row.wide && row.seen && /Back up to here/.test(row.btn), 'phone: nothing wider than the screen, the button is there ' + JSON.stringify(row));
    check(await ev(`![...document.querySelectorAll('#view .ulbody .ulrow')].some(li => /Settings of|View/.test(li.textContent))`), 'phone: no row "Settings of …" and none for the view');
    await shot('p21184a-handy-letzte-schritte.png');
    check(await ev(`(() => { const b = document.querySelector('#view .ulbody .ulrow[data-ul="s:${G1.id}"] [data-ul-go]'); b.scrollIntoView({block: 'center'}); b.click(); return 1; })()`) === 1, 'phone: Back up to here');
    check(await until(async () => (await call('GET', '/api/state', null, FK)).lists?.find(l => l.id === L)?.color === '#3366cc', {timeout: 20000}), 'phone: the colour is back');
  }, true);

  // ================= a computer: the button beside the label
  await firefox(async ({cmd, ev, ctx, nav, shot, until}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await signIn(ev) === 200, 'desktop: frida signed in');
    await nav(B + '#steps');
    const G2 = mine.find(g => /Sorting$/.test(g.label)) || {};  // undone on the phone: its row offers Redo
    const row = await until(`${rowOf(G2.id)}`, {timeout: 20000});
    check(row && row.beside && row.whole, 'desktop: the button beside the label ' + JSON.stringify(row));
    await shot('p21184a-desktop-letzte-schritte.png');
  });

  console.log(`p21184_a_steps_phone_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
