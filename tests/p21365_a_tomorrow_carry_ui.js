// kalmido-suite: fresh
// 2.1365.0 A (#6960) "Tomorrow" shows on top what "Today" still has open. jsdom, own container (start.sh):
// - an own group "Still open from today" with its count on top: due today and overdue (the rule of Today); below under
//   "Tomorrow" the tasks due tomorrow, never mixed; a task due later is in neither
// - the group folds; the folding stays on this device after a reload (open by default)
// - dragged from the group onto a task of tomorrow = due tomorrow
// - Today and the sidebar's count of Tomorrow (= only tomorrow) stay as they were
// freelancer-matrix: tasks - frida has no organisation.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 150});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const day = n => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Home'})).id;
  const mk = async (title, due) => (await call(CF, 'POST', '/api/tasks', {title, list_id: L, due})).id;
  const TOD = await mk('Pay the rent', day(0)), OVR = await mk('Old invoice', day(-3)), TMR = await mk('Dentist', day(1)), TM2 = await mk('Call the bank', day(1)), LAT = await mk('Trip', day(5));

  let w = await boot({user: 'frida', hash: 'tomorrow'}), d = w.document;
  const head = k => d.querySelector(`#view .ghead[data-key="${k}"]`);
  const inG = (k, id) => !!head(k)?.closest('.group')?.querySelector(`.trow[data-id="${id}"]`);
  check(await until(() => head('tm:carry') && head('tm:tomorrow')), 'Tomorrow: the group "Still open from today" and the head "Tomorrow" ' + [...d.querySelectorAll('#view .ghead')].map(x => x.dataset.key).join(' | '));
  check(/Still open from today/.test(head('tm:carry').textContent) && head('tm:carry').querySelector('.c')?.textContent === '2', 'its name and count 2 in the head: ' + head('tm:carry').textContent.trim());
  check(inG('tm:carry', TOD) && inG('tm:carry', OVR), 'due today and overdue stand in the group');
  check(inG('tm:tomorrow', TMR) && inG('tm:tomorrow', TM2) && !inG('tm:carry', TMR), 'the tasks of tomorrow below, not mixed');
  check(head('tm:carry').compareDocumentPosition(head('tm:tomorrow')) & 4, 'the group on top');
  check(!d.querySelector(`#view .trow[data-id="${LAT}"]`), 'a task due later in neither');
  check(w.eval('counts().tomorrow') === 2 && d.querySelector('#side [data-go="tomorrow"] .c')?.textContent.trim() === '2', 'the sidebar\'s count of Tomorrow: only tomorrow (2) ' + (d.querySelector('#side [data-go="tomorrow"]')?.textContent || '').trim());

  // fold: closed, kept on this device after a reload
  click(w, head('tm:carry'));
  check(await until(() => head('tm:carry').classList.contains('closed') && !inG('tm:carry', TOD)), 'folded: no rows');
  check(inG('tm:tomorrow', TMR), 'folded: tomorrow stays open');
  const coll = w.localStorage.getItem('tasks.collapsed');
  check(/tm:carry/.test(coll || ''), 'the folding kept on this device ' + coll);
  w.close();
  w = await boot({user: 'frida', hash: 'tomorrow', ls: {'tasks.collapsed': coll}}); d = w.document;
  check(await until(() => head('tm:carry')?.classList.contains('closed') && inG('tm:tomorrow', TMR)), 'after a reload: still folded');
  click(w, head('tm:carry'));
  check(await until(() => !head('tm:carry').classList.contains('closed') && inG('tm:carry', OVR)), 'opened again');

  // dragged from the group onto a task of tomorrow: due tomorrow
  await w.eval(`dropTask(${OVR}, document.querySelector('#view .trow[data-id="${TMR}"]'), 0)`);
  check(await until(async () => (await call(CF, 'GET', '/api/state')).tasks.find(t => t.id === OVR).due === day(1)), 'dragged onto a task of tomorrow: due tomorrow');
  check(await until(() => inG('tm:tomorrow', OVR) && !inG('tm:carry', OVR) && head('tm:carry').querySelector('.c')?.textContent === '1'), 'it stands under Tomorrow, the group counts 1');

  // Today as before: no such group
  w.eval(`go('today')`);
  check(await until(() => d.querySelector(`#view .trow[data-id="${TOD}"]`) && !head('tm:carry') && !head('tm:tomorrow')), 'Today: as before, without the group');
  w.close();
  // the merge queue moves a package's new texts into static/i18n/neu/<KID>.json (tools/i18n_neu.py): read both
  const fs = require('fs'), NEU = path.join(__dirname, '../static/i18n/neu');
  const DE = Object.assign({}, require('../static/i18n/de.json'), ...(fs.existsSync(NEU) ? fs.readdirSync(NEU).filter(f => f.endsWith('.json')).map(f => JSON.parse(fs.readFileSync(path.join(NEU, f), 'utf8')).de || {}) : []));
  check(DE['Still open from today'] === 'Noch offen von heute', 'German: "Noch offen von heute"');

  console.log(`p21365_a_tomorrow_carry_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
