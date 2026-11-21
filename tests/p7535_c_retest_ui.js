// kalmido-suite: fresh
// UI test (#7535): the retest after the build in the web app. Own container (start.sh), jsdom. Invented data only.
// - project settings > Review step: the pick "Retest after the build" (Off / By a person / By a review job) saves the switch
//   and Undo takes it back
// - the task panel with the review job: "Retest by a person" hands this task to a person (the bar says so), the entry turns
//   into "Retest by the review job", Undo takes it back; with the switch on "person" or off the entry is not there
// - "Back" in a project with the retest on asks what does not work (required) and sends the task back with the reason
//   (without one the server refuses it: p7535_a_retest_api_test; the dialog keeps itself open by askDialog's submit check)
// P4: frida has no organisation and gets the same (freelancer-matrix: tasks)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, until, undoToast, idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7535C_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const change = (w, el, v) => { if (!el) return; el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const u2 = (fn, timeout = 10000) => until(fn, {timeout}).catch(() => null);
const cfgOf = async (ck, lid) => { const l = (await call(ck, 'GET', '/api/state')).lists.find(x => x.id === lid); try { return JSON.parse(l.review_cfg || '{}'); } catch { return {}; } };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida: no organisation');

  for (const [u, ck] of [['alice', CA], ['frida', CF]]) {
    const me = (await call(ck, 'GET', '/api/state')).me.id;
    const L = (await call(ck, 'POST', '/api/lists', {name: 'Release', kind: 'project'})).id;
    const T = (await call(ck, 'POST', '/api/tasks', {title: 'The login button', list_id: L})).id;
    check((await call(ck, 'PUT', `/api/lists/${L}/review`, {on: true, reviewer: me})).http === 200, `${u}: setup: review step on`);

    // ---- the project setting
    let w = await boot({user: u, hash: 'today'}), d = w.document;
    w.eval(`listModal(${L})`);
    const sel = await u2(() => d.querySelector('#l-rvw-ret'));
    check(!!sel && [...sel.options].map(o => o.textContent).join('|') === 'Off|By a person|By a review job', `${u}: the pick in the review step ` + (sel ? [...sel.options].map(o => o.textContent).join('|') : '-'));
    change(w, sel, 'job');
    check(await u2(async () => (await cfgOf(ck, L)).retest === 'job'), `${u}: "By a review job" saved`);
    check(await undoToast(w, 'Review step saved'), `${u}: Undo offered`);
    check(await u2(async () => !(await cfgOf(ck, L)).retest), `${u}: Undo takes the switch back`);
    w.close();
    await call(ck, 'PUT', `/api/lists/${L}/review`, {on: true, reviewer: me, retest: 'job'});

    // ---- the task panel: retest by a person
    w = await boot({user: u, hash: `t/${T}`}); d = w.document;
    const btn = await u2(() => d.querySelector('.rvwbar [data-rvw="retest"]'));
    check(!!btn && btn.textContent.trim() === 'Retest by a person' && btn.getAttribute('aria-pressed') === 'false', `${u}: the task panel offers "Retest by a person"`);
    click(w, btn);
    check(await u2(async () => (await call(ck, 'GET', `/api/tasks/${T}`)).retest_person === true), `${u}: stored on the task`);
    check(await u2(() => /Retested by a person/.test(d.querySelector('.rvwbar')?.textContent || '')), `${u}: the bar says it`);
    check(await u2(() => d.querySelector('.rvwbar [data-rvw="retest"]')?.textContent.trim() === 'Retest by the review job'), `${u}: the way back is offered`);
    check(await undoToast(w, 'Retest by a person'), `${u}: Undo offered`);
    check(await u2(async () => !(await call(ck, 'GET', `/api/tasks/${T}`)).retest_person), `${u}: Undo takes it back`);
    w.close();

    // ---- switch on "person" / off: the entry is not there
    for (const rt of ['person', '']) {
      await call(ck, 'PUT', `/api/lists/${L}/review`, {on: true, reviewer: me, retest: rt});
      w = await boot({user: u, hash: `t/${T}`}); d = w.document;
      check(await u2(() => d.querySelector('.rvwbar')), `${u} ${rt || 'off'}: the review bar is there`);
      check(!d.querySelector('[data-rvw="retest"]'), `${u} ${rt || 'off'}: no "Retest by a person"`);
      w.close();
    }

    // ---- "Back" with the retest on: a reason is required
    await call(ck, 'PUT', `/api/lists/${L}/review`, {on: true, reviewer: me, retest: 'person'});
    await call(ck, 'POST', `/api/tasks/${T}/review`, {action: 'request', reviewer_id: me});
    // the panel's Back button runs rvw_do(id, 'changes'); called here from the page Today
    w = await boot({user: u, hash: 'today'}); d = w.document;
    await idle(w, {quiet: 400});
    w.eval(`rvw_do(${T}, 'changes')`);
    const dlg = await u2(() => [...d.querySelectorAll('.modal')].find(m => /What does not work\?/.test(m.textContent)));
    check(!!dlg && /required/.test(dlg.textContent), `${u}: Back asks what does not work (required)`);
    const inp = dlg?.querySelector('#cdlg-in');
    if (inp) { inp.value = 'The button does nothing'; inp.dispatchEvent(new w.Event('input', {bubbles: true})); }
    dlg?.querySelector('form')?.dispatchEvent(new w.Event('submit', {bubbles: true, cancelable: true}));
    check(await u2(async () => (await call(ck, 'GET', `/api/tasks/${T}`)).review === 'changes'), `${u}: with a reason it goes back`);
    w.close();
  }

  console.log(`p7535_c_retest_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
