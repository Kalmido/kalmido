// 2.1358.0 UI test, part B (#6328): undo takes back only the own step - a newer step of the same person made elsewhere (another
// device, a second tab, the API) stays.
// kalmido-suite: fresh
// freelancer-matrix: undo (a person without an organisation: the date popover's Undo, Ctrl+Z, the outbox's resend)
// jsdom, fresh container. Invented names only. Used like a person does it:
//  (a) the date popover: "Today", meanwhile another device renames another task, then "Tomorrow"; "Undo" in the popover's
//      foot puts the date back and leaves the other device's rename (was: POST /api/undo/to/<oldest> took it with it)
//  (b) the same visit closed with Esc, then Ctrl+Z on it: the date goes back, the other device's rename stays
//  (c) without the server's list (GET /api/undo fails; a child's account has none either): Ctrl+Z on the own tick takes back only it
//  (d) an own step of this device (no server group) whose way back waits in the outbox offline: sent later it still carries
//      X-Kalmido-Undo-Own and records no new server step (the way forward of the undone server step stays)
// The waits are on states (values on the server, the popover, the outbox), never on a fixed time.
const {boot, errs, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DEV = {'X-Kalmido-Device-Name': 'Phone (Test)'};
const until = (fn, ms) => until0(fn, {timeout: ms || 20000, step: 100});
const call = async (ck, method, url, body, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const day = n => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

async function round(who, ck, tag) {
  const L = (await call(ck, 'POST', '/api/lists', {name: `Work ${tag}`})).id;
  const T = (await call(ck, 'POST', '/api/tasks', {title: `Pay invoice ${tag}`, list_id: L, due: day(5)})).id;
  const U = (await call(ck, 'POST', '/api/tasks', {title: `Call bank ${tag}`, list_id: L})).id;
  const get = id => call(ck, 'GET', `/api/tasks/${id}`);
  const newest = async () => ((await call(ck, 'GET', '/api/undo?limit=1')).items || [])[0];
  const w = await boot({user: who, hash: 'l/' + L}); const d = w.document;
  const idle = () => until(() => !w.eval('HIST.busy') && w.eval('OUT.q.length') === 0);
  const click = el => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
  const key = (k, o = {}) => d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: k, ctrlKey: true, bubbles: true, cancelable: true, ...o}));
  const pop = () => d.querySelector('#pop:not(.hidden)');
  const rename = async n => { const r = await call(ck, 'PATCH', `/api/tasks/${U}`, {title: `Call bank ${tag} ${n}`}, DEV); check(r.http === 200, `${tag}: renamed on the other device (${r.http})`); };
  check(await until(() => d.querySelector(`#view .trow[data-id="${T}"]`)), `${tag}: the task row`);

  // ---- (a) the date popover's "Undo": only the visit's own steps
  w.eval(`datePop(document.querySelector('#top h1'), ${T})`);
  check(await until(() => pop()?.querySelector('[data-q="0"]')), `${tag}: the date popover is open`);
  click(pop().querySelector('[data-q="0"]'));
  check(await until(async () => (await get(T)).due === day(0)), `${tag}: "Today" is saved`);
  await idle();
  await rename('A');
  click(pop().querySelector('[data-q="1"]'));
  check(await until(async () => (await get(T)).due === day(1)), `${tag}: "Tomorrow" is saved too`);
  await idle();
  const rv = pop()?.querySelector('[data-q="revert"]');
  check(rv && !rv.hidden, `${tag}: "Undo" in the popover's foot`);
  click(rv);
  check(await until(async () => (await get(T)).due === day(5)), `${tag}: the popover's Undo puts the date back`);
  await idle();
  check(!pop(), `${tag}: the popover closed`);
  check((await get(U)).title === `Call bank ${tag} A`, `${tag}: the other device's newer rename stays (#6328): ${(await get(U)).title}`);

  // ---- (b) the same visit closed, then Ctrl+Z on it
  w.eval(`datePop(document.querySelector('#top h1'), ${T})`);
  check(await until(() => pop()?.querySelector('[data-q="0"]')), `${tag}: the date popover again`);
  click(pop().querySelector('[data-q="0"]'));
  check(await until(async () => (await get(T)).due === day(0)), `${tag}: "Today" saved again`);
  await idle();
  await rename('B');
  click(pop().querySelector('[data-q="1"]'));
  check(await until(async () => (await get(T)).due === day(1)), `${tag}: "Tomorrow" saved again`);
  await idle();
  const n0 = w.eval('HIST.undo.length');
  d.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  check(await until(() => !pop() && w.eval('HIST.undo.length') === n0 + 1), `${tag}: Esc closes, one step for the visit`);
  check(w.eval('histGids(HIST.undo.at(-1)).length') === 2, `${tag}: the visit's step holds its two server groups`);
  await idle();
  key('z');
  check(await until(async () => (await get(T)).due === day(5)), `${tag}: Ctrl+Z puts the date back`);
  await idle();
  check((await get(U)).title === `Call bank ${tag} B`, `${tag}: Ctrl+Z leaves the other device's rename in between (#6328): ${(await get(U)).title}`);

  // ---- (c) no list from the server (its GET /api/undo fails, as on a shaky network): Ctrl+Z takes back only the own tick
  const chk = () => d.querySelector(`#view .trow[data-id="${T}"] .chk`);
  check(await until(() => chk()), `${tag}: the task's check box`);
  click(chk());
  check(await until(async () => (await get(T)).status === 2), `${tag}: ticked off`);
  check(await until(() => /^Completed/.test(w.eval('HIST.undo.at(-1)?.label || ""'))), `${tag}: the tick is the newest entry here`);
  await idle();
  await rename('C');
  const f0 = w.fetch;  // histNext gets no list and falls back to this window's top entry
  w.fetch = (u, o) => /\/api\/undo\?/.test(String(u)) ? Promise.resolve(new Response(JSON.stringify({error: 'Server error'}), {status: 500, headers: {'Content-Type': 'application/json'}})) : f0(u, o);
  key('z');
  check(await until(async () => (await get(T)).status === 0), `${tag}: Ctrl+Z without the server's list opens it again`);
  await idle();
  w.fetch = f0;
  check((await get(U)).title === `Call bank ${tag} C`, `${tag}: the fallback leaves the newer rename (#6328): ${(await get(U)).title}`);

  // ---- (d) an own step's way back waiting in the outbox keeps X-Kalmido-Undo-Own
  const base = await newest();
  const back = await call(ck, 'POST', `/api/undo/${base.id}/undo`);
  check(back.http === 200, `${tag}: the newest server step undone (${back.http})`);
  w.eval(`HIST.fresh = []; histAdd({label: 'Own step ${tag}', undo: async () => { const r = await api('PATCH', '/api/tasks/${T}', {priority: 3}); return {q: r?._q}; }, redo: async () => ({})})`);
  w.__offline = true; w.eval('setOnline(false)');
  key('z');
  check(await until(() => w.eval('OUT.q.length') === 1 && !w.eval('HIST.busy')), `${tag}: offline the own way back waits in the outbox`);
  check(w.eval('OUT.q[0]?.own') === 1, `${tag}: the outbox entry knows it is an own way back`);
  w.__offline = false; w.eval('setOnline(true)'); await w.eval('flush()').catch(() => {});
  check(await until(async () => (await get(T)).priority === 3), `${tag}: sent once online`);
  await idle();
  const after = await newest();
  check(after && after.id === base.id && after.state === 'undone', `${tag}: the resend is no new server step (#6328 C5): ${JSON.stringify(after)}`);
  const rd = await call(ck, 'POST', `/api/undo/${base.id}/redo`);
  check(rd.http === 200, `${tag}: the undone step keeps its way forward (${rd.http})`);
  w.close();
}

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const ALICE = (await call(CA, 'GET', '/api/state')).me.id;
  const ORG = (await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: ALICE})).id;
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${ORG}`});
  await round('alice', CA, 'Alpha');

  // a person without an organisation (freelancer parity)
  await call(CA, 'POST', '/api/users', {username: 'fiona', display_name: 'Fiona', password: 'password123', email: 'fiona@example.com', orgs: []});
  const CF = await login('fiona');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  await round('fiona', CF, 'Frei');

  check(!errs.length, 'no script errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21358_b_undo_own_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
