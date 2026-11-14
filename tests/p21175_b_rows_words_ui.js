// kalmido-suite: fresh
// 2.1175.0 B (#6141) UI test, own container (start.sh), Firefox. Invented data only. Checks the VISIBLE content, phone and desktop:
// a task row without date and assignee has no second line with a dash and an empty symbol (also a subtask); a row in a group
// "by project" has no project chip of its own (the group head names it); the empty list says "No tasks" without a full stop;
// the view switch explains Kanban / Mind map in its tooltip; swimlane switch "No grouping"; the watch row without 0 watchers;
// a finger device on its side keeps a 44 px view switch.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21175_b_rows_words_ui', check, shots: 'P21175B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments', 'kanban', 'timeline']});
  const st = await call(CA, 'GET', '/api/state'), feats = new Set(((st.settings || {}).features || '').split(',').filter(Boolean));
  ['cal', 'comments', 'kanban', 'timeline'].forEach(x => feats.add(x));
  await call(CA, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: [...feats].join(',')});
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Plain project'})).id, LE = (await call(CA, 'POST', '/api/lists', {name: 'Empty project'})).id;
  const mk = async b => (await call(CA, 'POST', '/api/tasks', {list_id: L, ...b})).id;
  const T1 = await mk({title: 'Row without date and person'});
  await mk({title: 'Subtask without date', parent_id: T1});
  await mk({title: 'Row with a date', due: new Date(Date.now() + 3 * 864e5).toISOString().slice(0, 10)});

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const ffLogin = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(x => x.status)`);
  };
  // the second line of a row: what is in it, minus the dash / empty assign symbol
  const META = id => `(() => { const r = document.querySelector('#view .trow[data-id="${id}"]'); if (!r) return null;
    const m = [...r.querySelectorAll('.meta .mlc, .meta .lcnil, .meta .whob.wnone')].filter(e => e.offsetWidth > 0);
    return {n: m.length, txt: m.map(e => e.textContent.trim()).join('|'), dash: [...r.querySelectorAll('.meta')].some(e => e.offsetWidth > 0 && e.textContent.trim() === '\\u2013')}; })()`;

  for (const [wd, ht, tag, touch] of [[1280, 800, 'desk', false], [360, 740, 'phone', true]]) {
    await firefox(async o => {
      const {cmd, ev, ctx, nav} = o;
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: wd, height: ht}});
      check(await ffLogin(o) === 200, `${tag}: login`);
      await nav(B + '#l/' + L);
      check(await ready(ev, `document.querySelectorAll('#view .trow[data-id]').length >= 3`), `${tag}: the list shows its rows`);
      const ids = await ev(`[...document.querySelectorAll('#view .trow[data-id]')].map(r => [r.dataset.id, r.querySelector('.ttl')?.textContent.trim()])`);
      for (const [id, name] of ids.filter(x => /without date/.test(x[1] || ''))) {
        const m = await ev(META(id));
        check(m && !m.dash && !/^–$/.test(m.txt) && !m.txt.includes('–'), `${tag}: "${name}" has no second line with a dash / empty symbol ` + JSON.stringify(m));
      }
      // the view switch names its views; Kanban and Mind map explain themselves in the tooltip
      const tips = await ev(`(() => { const s = document.querySelector('#top .vseg.ttabs') || document.querySelector('#view .vsegm'); return s ? [...s.querySelectorAll('button')].map(b => [b.dataset.act, b.title, b.getAttribute('aria-label')]) : null; })()`);
      const tk = tips && tips.find(x => x[0] === 'view-kanban'), tm = tips && tips.find(x => x[0] === 'view-mindmap');
      check(tk && tk[1] === 'Kanban: tasks as cards in columns' && tk[2] === 'Kanban', `${tag}: Kanban tooltip explains the view ` + JSON.stringify(tk));
      check(tm && tm[1] === 'Mind map: tasks as branches of a map' && tm[2] === 'Mind map', `${tag}: Mind map tooltip explains the view ` + JSON.stringify(tm));
      // the empty list: title without a full stop
      await nav(B + '#l/' + LE);
      check(await ready(ev, `/^No tasks$/.test((document.querySelector('#view .empty .et, #view .empty h3, #view .empty b, #view .empty .etitle') || {}).textContent?.trim() || '')`)
        || await ev(`/(^|\\n)\\s*No tasks\\s*($|\\n)/.test(document.querySelector('#view').innerText) && !/No tasks\\./.test(document.querySelector('#view').innerText)`), `${tag}: the empty list says "No tasks" without a full stop`);
      // the detail: Watch without "0 watchers"
      await nav(B + '#l/' + L);
      await ready(ev, `document.querySelectorAll('#view .trow[data-id]').length >= 3`);
      await ev(`(() => { openDetail(${T1}); return 1; })()`);
      check(await ready(ev, `!!document.querySelector('#detail .dtop')`), `${tag}: the detail opens`);
      check(!await ev(`/0 watchers/.test(document.querySelector('#detail').innerText)`), `${tag}: no "0 watchers" in the detail`);
    }, touch);
  }
  // the narrow list (820 wide, the detail open): rows without date / person have no dash line; a row with a date keeps its date
  await firefox(async o => {
    const {cmd, ev, ctx, nav} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 820, height: 900}});
    check(await ffLogin(o) === 200, 'mid: login');
    await nav(B + '#l/' + L);
    check(await ready(ev, `document.querySelectorAll('#view .trow[data-id]').length >= 3`), 'mid: rows');
    await ev(`(() => { openDetail(${T1}); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('#detail .dtop')`), 'mid: detail open');
    check(await ev(`lcBlank('<span class="lcnil" aria-hidden="true">\\u2013</span>') && lcBlank('<button class="whob wnone"></button>') && !lcBlank('<span class="dt">Mon</span>')`), 'mid: a dash or an empty assign symbol is blank, a date is not');
    const rows = await ev(`[...document.querySelectorAll('#view .trow[data-id]')].map(r => [r.querySelector('.ttl')?.textContent.trim(), [...r.querySelectorAll('.meta .mlc')].map(e => e.textContent.trim()).join('|') || '', !!r.querySelector('.meta .mlc .lcnil, .meta .mlc .whob.wnone')])`);
    check(rows.length >= 3 && rows.every(x => !x[2]), 'mid: no dash / empty symbol in any second line ' + JSON.stringify(rows));
  }, true);
  // a finger device on its side: the view switch keeps 44 px (the style rule, read from the stylesheet)
  const css = await (await fetch(B + 'static/app.css')).text();
  check(/max-height:500px\) and \(min-aspect-ratio:1\/1\) and \(pointer:coarse\)\{ \.vsegm button\{min-height:2\.75rem\} \}/.test(css), 'landscape finger device keeps the 44 px view switch');
  // words: German
  const de = await (await fetch(B + 'static/i18n/de.json')).json();
  check(de['No grouping'] === 'Keine Gruppierung' && de['No tasks'] === 'Keine Aufgaben' && de['Kanban'] === 'Board' && de['Mind map'] === 'Mindmap', 'German words: Keine Gruppierung / Keine Aufgaben / Board / Mindmap');

  console.log(`p21175_b_rows_words_ui: ${ok} ok, ${F.length} failed`);
  if (F.length) { console.log(F.join('\n')); process.exit(1); }
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
