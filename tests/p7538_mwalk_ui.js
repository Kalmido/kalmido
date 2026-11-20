// kalmido-suite: fresh
// 2.1494.0 (#7538) working through "Waiting for me" (#mine_wait), own container (start.sh), jsdom, invented names only.
// - the server: a task another person's agent wrote into frida's project waits for her "Confirm as an order" (#7528, kind
//   confirm), sorted by sender; her own agent's task does not wait; gert (project admin, the agent is his) has no entry for
//   it; an agent's token sees no confirm entry (never a decider's yes)
// - a computer: the list on the left, the first entry open on the right; the entry shows the text the yes goes to; Confirm
//   -> the server has the yes to exactly that text, the next entry of the same group opens by itself
// - j / k next and back; an entry that goes away on another device: the next one opens; y while typing in a field does
//   nothing, y on the page approves the review (exactly two answers); the last one: "Nothing waits for you any more"
// - a phone: the list first, a row opens its entry over the whole view, "List" goes back
// - freelancer-matrix: tasks (frida and gert are people without an organisation)
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, idle} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body, hd = {}) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...hd, ...(ck ? {Cookie: ck} : {})}, body: body === undefined ? undefined : JSON.stringify(body)}); let j = {}; try { j = await r.json(); } catch { /* none */ } return {...j, http: r.status}; };
const until = async (fn, n = 40) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(150); } return null; };
const key = (w, el, k) => el.dispatchEvent(new w.KeyboardEvent('keydown', {key: k, bubbles: true, cancelable: true}));

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', email: 'alice@example.com'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'PUT', '/api/admin/agent-policy', {user_agents: true});
  for (const u of ['frida', 'gert']) await call(CA, 'POST', '/api/users', {username: u, display_name: u[0].toUpperCase() + u.slice(1), password: 'password123', email: `${u}@example.com`, orgs: []});
  const CF = await login('frida'), CG = await login('gert');
  for (const ck of [CF, CG]) await call(ck, 'PATCH', '/api/settings', {features: 'agents,comments,collab', lang: 'en', tour: 'done'});
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Shop', kind: 'project', ptype: 'software'})).id;
  const frida = (await call(CF, 'GET', '/api/state')).me?.id, gert = (await call(CG, 'GET', '/api/state')).me?.id;
  check((await call(CF, 'PUT', `/api/lists/${L}/members`, {user_id: gert, role: 'admin'})).http < 300, 'setup: gert is a project admin');
  const mkAgent = async (ck, name, lid) => {  // one agent per project: the own agent writes into a second project
    const a = await call(ck, 'POST', '/api/my/agents', {username: name, display_name: name, scopes: ['read', 'tasks:write', 'comments']});
    const m = await call(ck, 'PUT', `/api/lists/${lid}/members`, {user_id: a.id, role: 'edit'});
    check(m.http < 300, 'setup: agent ' + name + ' ' + JSON.stringify(a).slice(0, 200) + ' ' + JSON.stringify(m).slice(0, 200));
    return {Authorization: 'Bearer ' + (await call(ck, 'POST', `/api/my/agents/${a.id}/token`)).token};
  };
  const L2 = (await call(CF, 'POST', '/api/lists', {name: 'Notes', kind: 'project'})).id;
  const GH = await mkAgent(CG, 'gertbot', L), FH = await mkAgent(CF, 'fridabot', L2);
  const K1 = (await call(null, 'POST', '/api/v1/tasks', {list_id: L, title: 'Add a gift card', notes: 'Value 10 to 100'}, GH)).id;
  const K2 = (await call(null, 'POST', '/api/v1/tasks', {list_id: L, title: 'Ship to Austria', notes: 'Only parcels'}, GH)).id;
  const OWN = (await call(null, 'POST', '/api/v1/tasks', {list_id: L2, title: 'My bot writes this'}, FH)).id;
  const T = (await call(CF, 'POST', '/api/tasks', {title: 'Check the prices', list_id: L})).id;
  await call(CF, 'POST', `/api/tasks/${T}/review`, {action: 'request', reviewer_id: frida});
  check(K1 > 0 && K2 > 0 && OWN > 0 && T > 0, 'setup: the tasks');

  // the server
  const inb = await call(CF, 'GET', '/api/inbox'), cf = (inb.items || []).filter(x => x.kind === 'confirm');
  check(JSON.stringify(cf.map(x => x.id)) === JSON.stringify([K2, K1]) && inb.counts?.confirm === 2, 'another person\'s agent: its tasks wait for the confirmation, newest first ' + JSON.stringify(cf.map(x => x.id)));
  check(cf[0]?.agent_name === 'gertbot' && cf[0]?.task_id === K2, 'the entry names the sender ' + JSON.stringify(cf[0]));
  check(!cf.some(x => x.id === OWN), 'the own agent\'s task does not wait');
  const ing = await call(CG, 'GET', '/api/inbox');
  check(!(ing.items || []).some(x => x.kind === 'confirm'), 'gert (his agent wrote them) has no confirm entry');
  const ag = await call(null, 'GET', `/api/v1/me/waiting?user_id=${frida}`, undefined, FH);
  check(ag.http === 200 && (ag.counts?.confirm ?? 0) === 0, 'an agent\'s token: no confirm entry ' + ag.http + ' ' + JSON.stringify(ag.counts));

  // a computer: list left, entry right
  const w = await boot({user: 'frida', hash: 'mine_wait'}), d = w.document;
  await until(() => w.eval(`S.mw.items !== null && S.mw.items.length > 0`)); await idle(w);
  await until(() => d.querySelector('.mwsplit .mwr .mwp .mwtx'));
  check(!!d.querySelector('.mwsplit .mwl .mwg') && !!d.querySelector('.mwsplit .mwr .mwp'), 'list and entry side by side');
  check(/Orders to confirm/.test(d.querySelector('.mwl').textContent), 'the group "Orders to confirm"');
  const p1 = d.querySelector('.mwp');
  check(/Ship to Austria/.test(p1?.textContent || '') && /Only parcels/.test(p1?.querySelector('.mwtx')?.textContent || ''), 'the first entry shows the text the yes goes to');
  check(p1?.querySelector(`a.mwgo[href="#t/${K2}"]`), 'the jump to the target stays as a link');
  check(!d.querySelector('.mwp .mwpk'), 'a confirmation has no y / n keys (its no needs a reason)');
  d.querySelector('.mwp [data-mw="cf-yes"]').click();
  const p2 = await until(() => { const p = d.querySelector('.mwp'); return p && /Add a gift card/.test(p.querySelector('.mwpt')?.textContent || '') ? p : null; });
  check(!!p2, 'after the decision the next entry of the same group opens by itself');
  const k2 = await call(CF, 'GET', `/api/tasks/${K2}`);
  check(k2.confirmed?.by === frida, 'the server has the yes ' + JSON.stringify(k2.confirmed));

  // j / k
  key(w, d.body, 'j'); await idle(w);
  check(/Check the prices/.test(d.querySelector('.mwp .mwpt')?.textContent || ''), 'j: the next entry (the review)');
  key(w, d.body, 'k'); await idle(w);
  check(/Add a gift card/.test(d.querySelector('.mwp .mwpt')?.textContent || ''), 'k: back');
  // gone on another device: the next one opens
  check((await call(CF, 'POST', `/api/tasks/${K1}/reject`, {reason: 'Not this year'})).http === 200, 'rejected elsewhere');
  await w.eval(`mwLoad(true)`); await idle(w);
  check(/Check the prices/.test(d.querySelector('.mwp .mwpt')?.textContent || ''), 'the entry went away on another device: the next one opens');
  check(!!d.querySelector('.mwp .mwpk'), 'the review has exactly two answers: the keys are named');
  // y while typing: nothing
  const inp = d.createElement('input'); d.querySelector('.mwp').appendChild(inp); inp.focus();
  key(w, inp, 'y'); await sleep(500); await idle(w);
  check((await call(CF, 'GET', `/api/tasks/${T}`)).review === 'pending', 'y while typing in a field does nothing');
  inp.remove();
  key(w, d.body, 'y');
  check(!!(await until(async () => (await call(CF, 'GET', `/api/tasks/${T}`)).review === 'approved')), 'y on the page approves the review');
  check(!!(await until(() => /Nothing waits for you any more/.test(d.querySelector('#view')?.textContent || ''))), 'the last one: nothing waits any more');

  // a phone: the list, a row opens the entry over the view, "List" goes back
  const K3 = (await call(null, 'POST', '/api/v1/tasks', {list_id: L, title: 'Print the labels'}, GH)).id;
  const m = await boot({user: 'frida', hash: 'mine_wait', mobile: true}), md = m.document;
  await until(() => m.eval(`S.mw.items !== null && S.mw.items.length > 0`)); await idle(m);
  const row = await until(() => md.querySelector(`.mwg [data-mw="open"][data-k="confirm:${K3}"]`));
  check(!!row && !md.querySelector('.mwp'), 'a phone: the list first');
  row?.click(); await idle(m);
  check(!!md.querySelector('.mwone .mwp') && !md.querySelector('.mwg'), 'a phone: the entry fills the view');
  md.querySelector('.mwp [data-mw="list"]')?.click(); await idle(m);
  check(!!md.querySelector('.mwg') && !md.querySelector('.mwp'), 'a phone: "List" goes back');

  console.log(`p7538_mwalk_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
