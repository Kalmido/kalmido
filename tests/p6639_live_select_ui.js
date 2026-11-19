// kalmido-suite:
// 2.1432.0 UI test (#6639: a <select> is no typing), own container (start.sh), Firefox, phone width (390 x 844, touch).
// The browser is one device of alice, the suite's own fetches with a second login of alice are her other device. Invented data only.
// - a choice made in a select of the open task's panel leaves the focus there: a change of the other device still arrives
//   and is drawn (before: editing() counted the select as typing, nothing came until the focus moved, also after hours)
// - a text field with the focus: while typed in, the change waits; after EDIT_IDLE_MS without input it is loaded and the
//   panel drawn, the focused field keeps its text, its focus and its caret (the keyboard stays open)
// - the full redraw (render(), a change the delta does not carry) morphs the panel with the focus in it (lpDetail) instead of
//   leaving it untouched; the focused field keeps what it shows
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p6639_live_select_ui', check, shots: 'P6639_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');  // the other device
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab'});
  const L = (await call(CA, 'POST', '/api/lists', {name: 'App', kind: 'project', tickets: 1})).id;
  await call(CA, 'POST', '/api/tasks', {title: 'Release 1.0', list_id: L, ms: 1});
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Sign-in page', content: 'Form', list_id: L})).id;
  const other = (body, prev) => call(CA, 'PATCH', `/api/tasks/${T}`, {...body, _prev: prev});

  await firefox(async o => {
    const {ev, nav, shot, cmd, ctx} = o;
    const ready = async (expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
    // a background window gets no focus events (tests/p2170_ui.js): sent by hand, as a browser in front sends them
    const focus = sel => ev(`(() => { const x = document.querySelector('${sel}'); x.focus(); x.dispatchEvent(new FocusEvent('focusin', {bubbles: true})); return 1; })()`);
    const caught = () => ready(`fetch('/api/version', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.v === S.v && !td_polling)`, 120);
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    // the select part on a computer: on a phone a select opens the app's own sheet (popovers.js selSheet), the focus moves there
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + '#l/' + L);
    check(await ready(`typeof lpDelta === 'function' && typeof EDIT_IDLE_MS === 'number' && !isMobile() && !!document.querySelector('#view [data-id="${T}"]') && !!S.lpA`, 60), 'the project on a computer, the poll runs');
    await ev(`(() => { openDetail(${T}); return 1; })()`);
    const title = `document.querySelector('#d-title')?.value`;

    // ================= a choice made in a select: the focus stays there, live changes still arrive
    SEL: {
      const has = await ready(`S.sel === ${T} && !!document.querySelector('#detail select:not([disabled])')`, 40);
      check(has, 'the panel has a select (type / milestone)'); if (!has) break SEL;
      await ev(`(() => { const s = document.querySelector('#detail select:not([disabled])'); s.id && (window.__sel = '#' + s.id); return 1; })()`);
      const sel = await ev(`window.__sel || ''`);
      check(!!sel, 'the select has an id ' + sel); if (!sel) break SEL;
      await focus(sel);
      await ev(`(() => { const s = document.querySelector('${sel}'); s.value = s.options[s.options.length - 1].value; s.dispatchEvent(new Event('input', {bubbles: true})); s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()`);
      // the change's save draws the panel anew (patchTask -> renderDetail): the focus is put back on the select, as it stays
      // there after a choice in a select that does not redraw (a custom field) or when it is reached with Tab
      await ready(`!OUT.q.length`, 20);
      await focus(sel);
      check(await ev(`document.activeElement === document.querySelector('${sel}') && !editing()`), 'a focused select is no typing ' + JSON.stringify(await ev(`[document.activeElement?.tagName, document.activeElement?.id, document.activeElement?.className, editing()]`)));
      await caught();
      await other({title: 'Sign-in page v2'}, {title: 'Sign-in page'});
      check(await ready(`S.tasks.get(${T})?.title === 'Sign-in page v2'`, 60), 'the change arrives while the select has the focus');
      check(await ready(`${title} === 'Sign-in page v2'`, 20), 'the panel shows it ' + JSON.stringify(await ev(title)));
      check(await ev(`document.activeElement === document.querySelector('${sel}')`), 'the select keeps the focus');
      await shot('p6639-select.png');
    }

    // ================= a text field with the focus (phone): waits while typed in, taken after EDIT_IDLE_MS without input
    await caught();
    await ev(`(() => { closeDetail(); return 1; })()`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    check(await ready(`isMobile()`, 20), 'phone width');
    await ev(`(() => { openDetail(${T}); return 1; })()`);
    check(await ready(`S.sel === ${T} && !!document.querySelector('#d-title')`, 20), 'the panel is open on the phone');
    TXT: {
      const t0 = await ev(title);
      await ev(`(() => { editContent(); return 1; })()`);
      await focus('#d-content');
      const ta = `document.querySelector('#d-content')`;
      check(await ready(`document.activeElement === ${ta}`, 20), 'the note has the focus'); if (!(await ev(`document.activeElement === ${ta}`))) break TXT;
      await ev(`(() => { const t = ${ta}; t.value += ' with password'; t.setSelectionRange(4, 4); t.dispatchEvent(new Event('input', {bubbles: true})); return flushSaves().then(() => 1); })()`);
      check(await ev(`editing()`), 'typed just now: editing');
      // the save has landed (its answer carries the task: a change made before it would come with it, not through the poll)
      check(await ready(`!OUT.q.length && fetch('/api/tasks/${T}', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.content === 'Form with password')`, 40), 'the typed note is saved');
      await ev(`(() => { editAt = Date.now(); return 1; })()`);  // still typing (the test's own waits take no time off the minute)
      await other({title: 'Sign-in page v3'}, {title: t0});
      // a poll saw the change (S.vNow = the server's counter) and left it waiting while typed in
      check(await ready(`fetch('/api/version', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => S.vNow === j.v && !td_polling)`, 60), 'a poll saw the change');
      check(await ev(`${title} !== 'Sign-in page v3'`), 'while typed in the panel waits ' + JSON.stringify(await ev(`[${title}, Date.now() - editAt, document.activeElement?.id]`)));
      // the last input EDIT_IDLE_MS ago (set back by the test instead of waiting a minute)
      await ev(`(() => { editAt = Date.now() - EDIT_IDLE_MS - 1; return 1; })()`);
      check(await ev(`!editing()`), 'after EDIT_IDLE_MS without input: no longer editing');
      check(await ready(`${title} === 'Sign-in page v3'`, 60), 'then the change is loaded and drawn ' + JSON.stringify(await ev(title)));
      check(await ev(`document.activeElement === ${ta} && ${ta}.value === 'Form with password' && ${ta}.selectionStart === 4`), 'the note keeps the focus, its text and its caret ' + JSON.stringify(await ev(`[document.activeElement?.id, ${ta}.value, ${ta}.selectionStart]`)));
      await shot('p6639-idle.png');
    }

    // ================= the full redraw (render) morphs the panel with the focus in it
    RND: {
      await caught();
      const ta = `document.querySelector('#d-content')`;
      if (!(await ev(`document.activeElement === ${ta}`))) await focus('#d-content');
      await ev(`(() => { const t = ${ta}; t.value += '!'; t.dispatchEvent(new Event('input', {bubbles: true})); return flushSaves().then(() => 1); })()`);
      const typed = await ev(`${ta}.value`);
      await other({title: 'Sign-in page v4'}, {title: 'Sign-in page v3'});
      check(await ev(`load(true).then(() => { render(); return 1; })`), 'a full load + render() runs');
      check(await ready(`${title} === 'Sign-in page v4'`, 20), 'render() draws the panel with the focus in it ' + JSON.stringify(await ev(title)));
      check(await ev(`document.activeElement === ${ta} && ${ta}.value === ${JSON.stringify(typed)}`), 'the focused note keeps its typed text');
    }
  }, true);

  console.log(`p6639_live_select_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
