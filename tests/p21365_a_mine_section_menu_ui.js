// kalmido-suite: fresh
// 2.1365.0 A (#6962) "My tasks" with own sections: the task menu's "Move to section…" (right-click on a row). jsdom, own container:
// - it offers the own sections of the view (not "Recently assigned"), "New section…" and a check at the one the task stands in;
//   not the project's sections (was: always the sections of the task's project)
// - a pick moves the task there the way a drop onto the section's head does (personal: the list's sections stay untouched)
// - the project's sections stay reachable as "Move to section of <project>…"
// - "New section…" makes an own section with the task in it
// - the multi panel (several selected): the field "Section" = the own sections, the project's as "Section of <project>"
// - in the project itself the menu is the one of before
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

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments'});
  check(fu.http < 300 && ((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const L = (await call(CF, 'POST', '/api/lists', {name: 'Home'})).id;
  const SEC = (await call(CF, 'POST', '/api/sections', {list_id: L, name: 'Backlog'})).id;
  const WAIT = (await call(CF, 'POST', '/api/sections', {list_id: L, name: 'Waiting for feedback'})).id;
  const mk = async title => (await call(CF, 'POST', '/api/tasks', {title, list_id: L, section_id: SEC})).id;
  const TA = await mk('Water the plants'), TB = await mk('Book a trip'), TC = await mk('Call the bank');

  const w = await boot({user: 'frida', hash: 'assigned'}), d = w.document;
  const heads = () => [...d.querySelectorAll('#view .ghead[data-key^="ms:"]')];
  const head = re => heads().find(x => re.test(x.textContent));
  const inSec = (re, id) => !!head(re)?.closest('.group')?.querySelector(`.trow[data-id="${id}"]`);
  check(await until(() => head(/\bNow\b/) && head(/Soon/) && head(/Someday/)), 'own sections Now, Soon, Someday');
  const sid = re => +head(re).dataset.key.slice(3);
  const items = () => [...d.querySelectorAll('#pop [role="menuitem"]')];
  const mi = txt => items().find(b => (b.querySelector('.ml')?.textContent || b.textContent).trim() === txt);
  const rclick = async id => {
    w.eval('closePop()');
    const row = await until(() => d.querySelector(`#view .trow[data-id="${id}"]`));
    (row.querySelector('.ttl') || row).dispatchEvent(new w.MouseEvent('contextmenu', {bubbles: true, cancelable: true}));
    return until(() => mi('Move to section…'));
  };
  const open2 = async () => { click(w, mi('Move to section…')); return until(() => mi('Soon') || mi('Backlog')); };

  // the own sections, not the project's
  check(await rclick(TA), 'right-click: "Move to section…"');
  check(mi('Move to section of Home…'), 'the project\'s sections behind "Move to section of Home…" ' + items().map(b => b.textContent.trim()).join(' | '));
  await open2();
  const names = items().map(b => (b.querySelector('.ml')?.textContent || '').trim());
  check(mi('Now') && mi('Soon') && mi('Someday') && mi('New section…'), 'the own sections + "New section…" ' + names.join(' | '));
  check(!mi('Backlog') && !mi('Waiting for feedback') && !mi('Recently assigned'), 'not the project\'s sections, not "Recently assigned" ' + names.join(' | '));
  click(w, mi('Soon'));
  check(await until(() => inSec(/Soon/, TA)), 'picked Soon: the task stands under the head of Soon');
  check(await until(async () => (await call(CF, 'GET', '/api/state')).mine_sections.tasks[TA] === sid(/Soon/)), 'the server keeps it in Soon');
  check((await call(CF, 'GET', '/api/state')).tasks.find(t => t.id === TA).section_id === SEC, 'its project section stays Backlog (personal)');
  // the check at the section it stands in
  await rclick(TA); await open2();
  check(mi('Soon')?.classList.contains('on') && !mi('Now')?.classList.contains('on'), 'a check at Soon');

  // the project's sections through the second entry
  await rclick(TB);
  click(w, mi('Move to section of Home…'));
  check(await until(() => mi('Backlog') && mi('Waiting for feedback')), 'the second entry: the project\'s sections');
  click(w, mi('Waiting for feedback'));
  check(await until(async () => (await call(CF, 'GET', '/api/state')).tasks.find(t => t.id === TB).section_id === WAIT), 'moved into the project\'s section Waiting for feedback');

  // a new own section with the task in it
  w.prompt = () => 'Errands';
  await rclick(TB); await open2();
  click(w, mi('New section…'));
  check(await until(() => head(/Errands/) && inSec(/Errands/, TB)), '"New section…": an own section Errands with the task in it');

  // several selected: the multi panel's field "Section" offers the own sections
  w.eval(`closePop(); S.multiMode = true; S.multi.clear(); S.multi.add(${TB}); S.multi.add(${TC}); render();`);
  const fl = () => w.eval(`meFields(meTasks()).map(f => f.k + '=' + (f.raw ? f.lab : tr(f.lab))).join(',')`);
  check(/msec=Section/.test(fl()) && /(^|,)section=Section of Home/.test(fl()), 'multi: "Section" = own sections, the project\'s as "Section of Home" ' + fl());
  w.eval(`meFields(meTasks()).find(f => f.k === 'msec').open(document.querySelector('#top h1'))`);
  check(await until(() => mi('Someday') && !mi('Backlog')), 'multi: the own sections in its menu');
  click(w, mi('Someday'));
  check(await until(() => inSec(/Someday/, TB) && inSec(/Someday/, TC)), 'multi: both tasks in Someday');
  check(await until(async () => { const s = (await call(CF, 'GET', '/api/state')).mine_sections.tasks; return s[TB] === sid(/Someday/) && s[TC] === sid(/Someday/); }), 'multi: the server keeps both in Someday');
  w.eval(`S.multiMode = false; S.multi.clear(); render();`);

  // in the project itself: the project's sections as before
  w.eval(`closePop(); go('l/${L}')`);
  await until(() => d.querySelector(`#view .trow[data-id="${TC}"]`) && !heads().length);
  await rclick(TC);
  check(!mi('Move to section of Home…'), 'in the project: no second entry');
  await open2();
  check(mi('Backlog') && mi('Waiting for feedback') && !mi('Soon'), 'in the project: its own sections as before');
  w.close();

  console.log(`p21365_a_mine_section_menu_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
