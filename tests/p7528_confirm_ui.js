// 2.1494.0 (#7528): "Confirm as an order" / "Reject" in the task panel. Own container (start.sh), Firefox, invented names only.
// kalmido-suite: fresh
// - computer (1440): alice owns the project, bob (a member with edit rights) wrote a task: the panel shows "Not confirmed as
//   an order" and the header's "Confirm…"; its menu -> "Confirm as an order" -> the bar names alice, the button goes;
//   "Withdraw" brings the open state back; the menu's "Reject…" asks for the reason (an empty one closes nothing), with a
//   reason the task is closed as won't do and the history says so; alice's own task shows neither bar nor button
// - phone (390): no header button; the task's menu "…" has "Confirm as an order", which confirms it
// - bob (no decider) sees no button and no entry in the menu
// - freelancer-matrix: tasks (alice is a person without an organisation here)
const {execFileSync} = require('child_process');
const path = require('path');
const {B, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const {realClick} = require('./ff');
const firefox = require('./ff')({tag: 'p7528_confirm_ui', check, shots: 'P7528_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const cookie = async user => { const r = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: user, password: 'password123'})}); return r.headers.get('set-cookie').split(';')[0]; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await cookie('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const bu = await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com', orgs: []});
  check(bu.http < 300, 'setup: bob ' + bu.http);
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Orders', kind: 'project'})).id;
  check((await call(CA, 'PUT', `/api/lists/${L}/members`, {user_id: bu.id, role: 'edit'})).http < 300, 'setup: bob is a member');
  const CB = await cookie('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const T1 = (await call(CB, 'POST', '/api/tasks', {title: 'Bob wants a new export', list_id: L, content: 'CSV and PDF'})).id;
  const T2 = (await call(CB, 'POST', '/api/tasks', {title: 'Bob wants dark mode', list_id: L})).id;
  const T3 = (await call(CA, 'POST', '/api/tasks', {title: 'Alice writes her own', list_id: L})).id;
  check(T1 > 0 && T2 > 0 && T3 > 0, 'setup: the tasks');

  const login = async ({nav, ev}, user) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${user}', password: 'password123'})}).then(r => r.status)`);
  };
  const ready = async o => { await o.until(`typeof S !== 'undefined' && !!S.booted && !!document.querySelector('#top h1')`); await o.idle(); };
  const open = async (o, id) => { await o.ev(`(() => { openDetail(${id}); return 1; })()`); await o.until(`S.sel === ${id} && S.tl.id === ${id} && !!S.tl.activity`); await o.idle(); };
  const bar = `(() => { const b = document.querySelector('#d-cf .ordbar'); return b ? {open: b.classList.contains('ordopen'), text: b.textContent.replace(/\\s+/g, ' ').trim()} : null; })()`;
  const pick = async (o, label) => {
    await o.until(`[...document.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].some(x => (x.querySelector('.ml') || x).textContent.trim() === ${JSON.stringify(label)})`);
    return o.ev(`(() => { const b = [...document.querySelectorAll('#pop [role="menuitem"]')].find(x => (x.querySelector('.ml') || x).textContent.trim() === ${JSON.stringify(label)}); b?.click(); return !!b; })()`);
  };
  const hist = async (o, kind) => (await o.ev(`JSON.stringify((S.tl.activity || []).filter(a => a.kind === '${kind}').map(a => a.data || {}))`));

  // ================= computer
  await firefox(async o => {
    const {cmd, ev, ctx, shot, until} = o, tag = '1440';
    check(await login(o, 'alice') === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 900}});
    await o.nav(B + `#l/${L}`); await ready(o);
    await open(o, T1);
    check(await until(`!!document.querySelector('#d-cfh .dcfb')`), `${tag}: the header shows "Confirm…" on bob's task`);
    const b0 = await ev(bar);
    check(b0 && b0.open && /Not confirmed as an order/.test(b0.text), `${tag}: the bar says it is not confirmed ` + JSON.stringify(b0));
    await shot('p7528-1440-open.png');
    const rc = await realClick(o, '#d-cfh .dcfb');
    check(rc.ok && await pick(o, 'Confirm as an order'), `${tag}: the button's menu offers "Confirm as an order" ` + JSON.stringify(rc));
    check(await until(`(() => { const b = document.querySelector('#d-cf .ordbar'); return !!b && !b.classList.contains('ordopen') && /Confirmed as an order/.test(b.textContent) && /Alice/.test(b.textContent); })()`)
      && !await ev(`!!document.querySelector('#d-cfh .dcfb')`), `${tag}: confirmed: the bar names Alice, the button is gone ` + JSON.stringify(await ev(bar)));
    check(await until(`(S.tl.activity || []).some(a => a.kind === 'confirmed')`) && /confirmed the task as an order/.test(await ev(`document.querySelector('#d-hist-items, #d-tl-items')?.textContent || document.querySelector('#detail')?.textContent || ''`)),
      `${tag}: the history line`);
    await shot('p7528-1440-confirmed.png');
    await ev(`(() => { document.querySelector('#d-cf [data-tcf="off"]').click(); return 1; })()`);
    check(await until(`!!document.querySelector('#d-cf .ordbar.ordopen') && !!document.querySelector('#d-cfh .dcfb')`), `${tag}: "Withdraw": open again, the button is back`);
    // reject: an empty reason closes nothing, a reason closes it as won't do
    await realClick(o, '#d-cfh .dcfb'); await pick(o, 'Reject…');
    check(await until(`!!document.querySelector('.modal #cdlg-in')`), `${tag}: "Reject…" asks for the reason`);
    await ev(`(() => { document.querySelector('.modal [data-cd="yes"]').click(); return 1; })()`);
    await until(`!document.querySelector('.modal #cdlg-in')`); await o.idle();
    check(await ev(`taskById(${T1}).status`) === 0, `${tag}: without a reason nothing closes`);
    await realClick(o, '#d-cfh .dcfb'); await pick(o, 'Reject…');
    await until(`!!document.querySelector('.modal #cdlg-in')`);
    await ev(`(() => { const i = document.querySelector('.modal #cdlg-in'); i.value = 'We keep the old export'; i.dispatchEvent(new Event('input', {bubbles: true})); document.querySelector('.modal [data-cd="yes"]').click(); return 1; })()`);
    check(await until(`taskById(${T1}).status === -1`), `${tag}: with a reason: closed as won't do`);
    check(await until(`(S.tl.activity || []).some(a => a.kind === 'rejected' && a.data && a.data.reason === 'We keep the old export')`), `${tag}: the history keeps the reason ` + await hist(o, 'rejected'));
    check(!await ev(`!!document.querySelector('#d-cfh .dcfb') || !!document.querySelector('#d-cf .ordbar')`), `${tag}: a closed task: no button, no bar`);
    await shot('p7528-1440-rejected.png');
    await open(o, T3);
    check(!await ev(`!!document.querySelector('#d-cfh .dcfb') || !!document.querySelector('#d-cf .ordbar')`), `${tag}: her own task: neither button nor bar`);
  });

  // ================= phone: the task's menu
  await firefox(async o => {
    const {cmd, ev, ctx, shot, until} = o, tag = '390';
    check(await login(o, 'alice') === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 760}});
    await o.nav(B + `#l/${L}`); await ready(o);
    await open(o, T2);
    await until(`!!document.querySelector('#d-cf .ordbar.ordopen')`);
    check(!await ev(`!!document.querySelector('#d-cfh .dcfb')`), `${tag}: no header button on a phone`);
    await ev(`(() => { document.querySelector('#detail [data-act="task-menu"]').click(); return 1; })()`);
    check(await pick(o, 'Confirm as an order'), `${tag}: the task's menu offers "Confirm as an order"`);
    check(await until(`!!taskById(${T2}).confirmed && !!document.querySelector('#d-cf .ordbar:not(.ordopen)')`), `${tag}: confirmed over the menu`);
    await shot('p7528-390-confirmed.png');
  }, true);

  // ================= bob: no decider
  await firefox(async o => {
    const {cmd, ev, ctx, until} = o, tag = 'bob 1440';
    check(await login(o, 'bob') === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1440, height: 900}});
    await o.nav(B + `#l/${L}`); await ready(o);
    const T4 = (await call(CA, 'POST', '/api/tasks', {title: 'Alice asks bob', list_id: L})).id;
    await o.ev(`refreshNow().then(() => 1)`); await until(`!!taskById(${T4})`);
    await open(o, T4);
    check(await ev(`S.tl.may_yes`) === false && !await ev(`!!document.querySelector('#d-cfh .dcfb') || !!document.querySelector('#d-cf .ordbar.ordopen')`), `${tag}: no button, no open bar`);
    await ev(`(() => { document.querySelector('#detail [data-act="task-menu"]').click(); return 1; })()`);
    await until(`!!document.querySelector('#pop:not(.hidden) [role="menuitem"]')`);
    check(!await ev(`!!document.querySelector('#pop .cf-yes, #pop .cf-no')`), `${tag}: no entry in the task's menu`);
  });

  console.log(`p7528_confirm_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack); process.exit(1); });
