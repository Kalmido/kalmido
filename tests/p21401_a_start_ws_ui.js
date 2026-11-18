// 2.1401.0 UI test part A (#6234; rebuilt on main after 2.1242.0 job/4721 and 2.1383.0 job/5370): the start page's Projects and Notes cards under "All workspaces" name each row's workspace with
// the org colour's building block (wscolor.js wso_origin): its dot + name. One workspace shown: no mark on these cards. The box
// "Waiting for you" (hpWsMark, now on the same building block) still marks another workspace's line and none under "All".
// kalmido-suite: fresh
// Own container (start.sh), jsdom, invented data only. Alice: the organisation "Acme" with the project "Requests", the private
// project "Garden", a note in each; both projects have a status (the Projects card shows only those).
// freelancer-matrix: lists - no new route (only the start page's display); Frida without an organisation: no mark, the cards work
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, t = 15000) => require('./boot').until(fn, {timeout: t, step: 150});
const txt = e => (e?.textContent || '').replace(/\s+/g, ' ').trim();
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments', 'collab']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab', workspace: 'all'});
  const ORG = (await call(CA, 'POST', '/api/orgs', {name: 'Acme'})).id;
  const PL = (await call(CA, 'POST', '/api/lists', {name: 'Garden', org_id: null})).id;
  const OL = (await call(CA, 'POST', '/api/lists', {name: 'Requests', org_id: ORG})).id;
  for (const l of [PL, OL]) await call(CA, 'POST', `/api/lists/${l}/status`, {status: 'on_track', note: ''});
  const PN = (await call(CA, 'POST', `/api/lists/${PL}/notes`, {title: 'Seeds to buy', body: 'Beans'})).id;
  const ON = (await call(CA, 'POST', `/api/lists/${OL}/notes`, {title: 'Client call', body: 'Monday'})).id;
  check(ORG && PL && OL && PN && ON, 'setup: an organisation, two projects with a status, a note in each ' + JSON.stringify([ORG, PL, OL, PN, ON]));

  // ================= "All workspaces": every row of the two cards names its workspace
  let w = await boot({user: 'alice', hash: 'home'}), d = w.document;
  check(await until(() => w.eval(`typeof wsCur === 'function' && wsCur()`) === 'all'), 'All workspaces shown: ' + w.eval('wsCur()'));
  const proj = () => [...d.querySelectorAll('.dpl li')], notes = () => [...d.querySelectorAll('.dwl li')].filter(li => li.querySelector('a[href^="#note/"]'));
  check(await until(() => proj().length === 2 && notes().length === 2), 'the Projects card and the Notes card with two rows each: ' + proj().length + ' / ' + notes().length);
  const pRow = n => proj().find(li => li.querySelector('.dpn')?.textContent === n), nRow = n => notes().find(li => new RegExp(n).test(li.textContent));
  const mark = li => li?.querySelector('.hpws.wso');
  check(/Acme/.test(txt(mark(pRow('Requests')))) && !!mark(pRow('Requests'))?.querySelector('.wsp-dot'), '#6234: Projects: "Requests" carries Acme\'s dot + name ' + (pRow('Requests')?.innerHTML || 'missing'));
  check(/Private/.test(txt(mark(pRow('Garden')))) && !/Acme/.test(txt(mark(pRow('Garden')))), '#6234: Projects: "Garden" carries Private ' + (pRow('Garden')?.innerHTML || 'missing'));
  check(/Acme/.test(txt(mark(nRow('Client call')))) && !!mark(nRow('Client call'))?.querySelector('.wsp-dot'), '#6234: Notes: "Client call" carries Acme\'s dot + name ' + (nRow('Client call')?.innerHTML || 'missing'));
  check(/Private/.test(txt(mark(nRow('Seeds to buy')))), '#6234: Notes: "Seeds to buy" carries Private');
  check(/Workspace: Acme/.test(txt(mark(pRow('Requests'))?.querySelector('.sr'))), '#6234: the mark names the workspace for screen readers');
  check(!d.querySelector('.dtome .hpws'), 'the box "Waiting for you" under "All": no mark (hpWsMark on the building block)');
  // the row still leads into the project and the note
  click(w, pRow('Requests').querySelector('a'));
  check(await until(() => w.location.hash === `#l/${OL}`), '#6234: a tap on the marked project row opens the project: ' + w.location.hash);
  w.location.hash = '#home';
  check(await until(() => !!nRow('Client call')), 'back on the start page');
  click(w, nRow('Client call').querySelector('a'));
  check(await until(() => w.location.hash === `#note/${ON}`), '#6234: a tap on the marked note row opens the note: ' + w.location.hash);
  // ================= one workspace shown (Acme): its own rows carry no mark; the box marks another workspace's line (hpWsMark)
  w.eval(`S.settings.workspace = 'org:${ORG}'; location.hash = '#home';`);
  check(await until(() => proj().length === 1 && notes().length === 1), 'Acme shown: one project, one note');
  check(!mark(proj()[0]) && !mark(notes()[0]), '#6234: one workspace shown: no mark on the Projects and Notes rows ' + proj()[0]?.innerHTML);
  const box = w.eval(`(() => { const h = hpWsMark('private', 'Garden'); const x = document.createElement('div'); x.innerHTML = h; const m = x.querySelector('.hpws.wso'); return m ? {t: m.textContent, title: m.title, dot: !!m.querySelector('.wsp-dot')} : null; })()`);
  check(box && /Private/.test(box.t) && /Garden/.test(box.title) && box.dot, 'hpWsMark (building block): another workspace\'s line: dot + name, the list in the title ' + JSON.stringify(box));
  check(w.eval(`hpWsMark('org:${ORG}', 'Requests')`) === '', 'hpWsMark: the shown workspace: no mark');
  // the short form true (= {mixed: true}, #6187) keeps its meaning: inside one workspace Private and the shown one stay unmarked
  check(w.eval(`wso_origin('private', 'x', true)`) === '' && w.eval(`wso_origin('org:${ORG}', 'x', true)`) === '', 'wso_origin(.., true): Private and the shown workspace unmarked inside one workspace');
  w.eval(`S.settings.workspace = 'all';`);
  check(w.eval(`hpWsMark('private', 'Garden')`) === '', 'hpWsMark: under "All": no mark');
  check(/Acme/.test(w.eval(`wso_origin('org:${ORG}', 'x', true)`)), 'wso_origin(.., true): under "All" the organisation is marked');
  w.close();

  // ================= a person without an organisation: the cards as before, no mark
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab'});
  const FL = (await call(CF, 'POST', '/api/lists', {name: 'Short film'})).id;
  await call(CF, 'POST', `/api/lists/${FL}/status`, {status: 'on_track', note: ''});
  const FN = (await call(CF, 'POST', `/api/lists/${FL}/notes`, {title: 'Shot list', body: 'Wide'})).id;
  check(FL && FN, 'frida: a project with a status and a note');
  w = await boot({user: 'frida', hash: 'home'}); d = w.document;
  check(await until(() => proj().length === 1 && notes().length === 1), 'freelancer: the Projects and Notes cards show her project and note');
  check(!w.eval('wsOn()') && !d.querySelector('.dpl .hpws, .dwl .hpws'), 'freelancer: no workspaces, no mark');
  click(w, proj()[0].querySelector('a'));
  check(await until(() => w.location.hash === `#l/${FL}`), 'freelancer: the project row opens her project');
  w.close();

  console.log(`p21401_a_start_ws_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
