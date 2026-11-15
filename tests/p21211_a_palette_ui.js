// kalmido-suite: fresh
// 2.1211.0 UI test, part A (#6128: the command search), own container (start.sh), Firefox. Invented names only.
// - the extra line and the kind of a hit are in the normal font (not the code font); an open task has a neutral task symbol
//   (a ring), never the tick of a finished one
// - commands match only a coherent word: scattered letters find nothing ("clnr" must not find "Calendar"); the word does
// - without a hit: "Nothing found" stands above "Create as task"; in the move mode an own sentence without a promise of Enter
// - the keys: one source (Settings > Help opens the overview, no second list); the doubled key m names its context
// - the dashboard's search tile has the same placeholder as the search
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21211_a_palette_ui', check, shots: 'P21211APAL_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21211APAL_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments'});
  const st = await call(CA, 'GET', '/api/state');
  const inbox = (st.lists || []).find(l => l.is_inbox);
  const t = await call(CA, 'POST', '/api/tasks', {title: 'Imagefilm Stadtwerke', list_id: inbox?.id});
  check(t.http === 201 || t.http === 200, 'a task ' + t.http);

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const type = q => `(() => { const i = document.querySelector('.palette .pqin'); i.value = ${JSON.stringify(q)}; i.dispatchEvent(new Event('input', {bubbles: true})); palFlush(); return 1; })()`;

  await firefox(async ({cmd, ev, ctx, nav}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev, 'alice');
    await nav(B + '#inbox');
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && typeof palAll === 'function' && [...S.tasks.values()].some(x => x.title === 'Imagefilm Stadtwerke')`, 80), 'booted with the task');
    await ev(`openPalette()`);
    await ev(type('Imagefilm'));
    check(await ready(ev, `[...document.querySelectorAll('.palette .pitem .plt')].some(x => x.textContent === 'Imagefilm Stadtwerke')`), 'the task is found');
    // normal font, neutral symbol
    check(await ev(`(() => { const s = document.querySelector('.palette .pitem .pls'); const k = document.querySelector('.palette .pitem .pk'); return !!s && !/mono/i.test(getComputedStyle(s).fontFamily) && !!k && !/mono/i.test(getComputedStyle(k).fontFamily) && getComputedStyle(s).fontFamily === getComputedStyle(document.querySelector('.palette .plt')).fontFamily; })()`), 'extra line and kind are in the normal font');
    check(await ev(`(() => { const b = [...document.querySelectorAll('.palette .pitem')].find(x => x.querySelector('.plt')?.textContent === 'Imagefilm Stadtwerke'); const i = b?.querySelector('.psw'); if (!i) return false; const r = i.getBoundingClientRect(); return r.width > 4 && r.height > 4 && !b.querySelector('.pic svg') && getComputedStyle(i).borderRadius !== '0px'; })()`), 'an open task: a ring, no tick');
    // scattered letters
    await ev(type('clnr'));
    check(await ev(`![...document.querySelectorAll('.palette .pitem .plt')].some(x => /Calendar/.test(x.textContent))`), 'scattered letters do not find a command');
    await ev(type('calen'));
    check(await ev(`[...document.querySelectorAll('.palette .pitem .plt')].some(x => /Calendar/.test(x.textContent))`), 'a coherent word still finds');
    // no hit: Nothing found above Create as task
    await ev(type('qzxwv'));
    check(await ev(`(() => { const n = document.querySelector('.palette .pnone'), c = document.querySelector('.palette .pitem.pdo'); return !!n && /^Nothing found$/.test(n.textContent) && !!c && n.getBoundingClientRect().top < c.getBoundingClientRect().top; })()`), '"Nothing found" above "Create as task"');
    // move mode: an own sentence
    await ev(`closePalette(); openDetail(${t.id})`);
    await ready(ev, `!!curTask()`);
    await ev(`openPalette('move')`);
    await ready(ev, `!!document.querySelector('.palette .pqin')`);
    await ev(type('qzxwv'));
    check(await ev(`(() => { const e = document.querySelector('.palette .pempty'); return !!e && /No project matches/.test(e.textContent) && !/Enter/.test(e.textContent); })()`), 'move mode: no Enter promise');
    await ev(`closePalette()`);
    // the keys
    check(await ev(`(() => { const rows = SHORTCUTS().flatMap(([g, r]) => r.map(x => [g, ...x])); const m = rows.filter(x => x[1] === 'm' && ['General', 'Tasks'].includes(x[0])).map(x => x[2]); return m.length === 2 && new Set(m).size === m.length && m.every(n => /\\(.+\\)/.test(n)); })()`), 'the doubled key m names its context');
    await nav(B + '#inbox');
    await ev(`settingsModal('help')`);
    check(await ready(ev, `!!document.querySelector('.modal [data-m="keys"]')`), 'settings help links the overview');
    check(await ev(`!/j \\/ k move through/.test(document.querySelector('.modal').textContent)`), 'no second hand list of keys');
    await ev(`(() => { document.querySelector('.modal [data-m="close"], .modal .iconbtn[aria-label="Close"]')?.click(); return 1; })()`);
    // the dashboard's search tile has the palette's placeholder (one source: the same text)
    const src = require('fs').readFileSync(path.join(__dirname, '..', 'static/js/dashboard.js'), 'utf8');
    check(src.includes(`placeholder="\${esc(tr('Search tasks, projects, views and actions…'))}"`), 'the dashboard tile has the palette placeholder');
  }, false);

  console.log(`p21211_a_palette_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
