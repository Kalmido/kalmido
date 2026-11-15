// 2.1230.0 A UI test (#4742, start care): the rules of a list (rules.js) and the export of an organisation / the own office
// kalmido-suite: fresh
// (orgexport.js) left the start and load when they are needed. Own container (start.sh), jsdom, invented data only; no
// server route changed.
// - a cold start runs neither rules.js nor orgexport.js; the stand-in rul_mount is there, what the start asks stays (the
//   mark of a comment written by a rule, the kind of a proposal)
// - a person without an organisation opens the settings of a project: the section "Rules" shows the saved rule as a sentence
//   and "Add rule"; the click opens the dialog of a new rule (rules.js came through the stand-in)
// - an organisation admin opens Settings > Organisation > Data: the export of the organisation is drawn with "Create export"
//   (the settings module loaded orgexport.js first, LD_NEED)
const fs = require('fs');
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return r.ok ? r.json() : {status: r.status}; };
const until = fn => require('./boot').until(fn, {timeout: 15000, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const ran = (w, f) => !!w.document.querySelector(`script[data-ld="${f}"]`);
const close = async w => { await until(() => w.eval('ld_n') === 0); w.close(); };

(async () => {
  if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});

  // ---- the files: no script tag, each in its module
  const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');
  check(!/\/static\/js\/rules\.js/.test(html) && !/\/static\/js\/orgexport\.js/.test(html), 'index.html has no tag for rules.js / orgexport.js');

  // ---- a person without an organisation: a project with one rule
  const L = await call('POST', '/api/lists', {name: 'Garden 4742'});
  const R = await call('POST', `/api/lists/${L.id}/rules`, {name: 'Kranich', trigger: {kind: 'created'}, action: {kind: 'comment', text: 'Checked by the rule'}});
  check(L.id > 0 && R.id > 0, 'setup: a project of a person without an organisation with one rule ' + JSON.stringify(R));

  let w = await boot({user: 'alice', lazy: true});
  const d = w.document;
  const tags = w.eval(`[...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src'))`);
  check(!tags.some(s => /\/(rules|orgexport)\.js/.test(s)), 'a cold start runs neither rules.js nor orgexport.js');
  check(w.eval(`LD_MODS.rules.join()`) === 'rules' && w.eval(`LD_MODS.orgexport.join()`) === 'orgexport', 'rules and orgexport are modules');
  check(w.eval(`LD_NEED.settings.includes('orgexport') && LD_NEED.office.includes('orgexport')`), 'the settings and the office load orgexport first');
  check(w.eval(`typeof rul_draw`) === 'undefined' && w.eval(`typeof oxBoxHtml`) === 'undefined', 'their globals are not there yet');
  check(w.eval(`typeof rul_mount`) === 'function', 'the stand-in rul_mount is there');
  check(/Rule Kranich/.test(w.eval(`rul_cmtTag({rule_name: 'Kranich'})`)) && w.eval(`rul_is({kind: 'rule'})`) === true, 'the start keeps the mark of a rule comment and the kind of a proposal');

  // the settings of the project, used like a person
  w.eval(`listModal(${L.id})`);
  const row = await until(() => d.querySelector('#l-rules .rul-row'));
  check(row && /Kranich/.test(row.textContent), 'the project settings show the saved rule: ' + (row?.textContent || '').trim().slice(0, 120));
  check(ran(w, 'rules'), 'the stand-in loaded rules.js');
  const add = d.querySelector('#l-rules [data-rul-add]');
  check(add && /Add rule/.test(add.textContent), '"Add rule" is there');
  click(w, add);
  const nm = await until(() => d.querySelector('#rul-name'));
  check(nm && nm.closest('.modal'), 'the click opens the dialog of a new rule');
  await close(w);

  // ---- an organisation admin: Settings > Organisation > Data
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  w = await boot({user: 'alice', lazy: true});
  check(!ran(w, 'orgexport') && w.eval(`typeof oxDraw`) === 'undefined', 'cold start: orgexport.js not loaded');
  w.eval(`settingsModal('org')`);
  const md = await until(() => w.document.querySelector('.smodal'));
  click(w, await until(() => md?.querySelector('[data-admsub="odata"]')));
  const box = await until(() => md?.querySelector(`#s-wsdata .oxbox[data-oxorg="${ORG}"] [data-ox="start"]`)?.closest('.oxbox'));
  check(box && /Export the organisation/.test(box.textContent) && /Create export/.test(box.textContent), 'Data shows the export of the organisation with "Create export"');
  check(ran(w, 'orgexport'), 'the settings module brought orgexport.js');
  await close(w);

  check(errs.length === 0, 'no JS errors: ' + errs.slice(0, 3).join(' | '));
  console.log(`p21230_a_lazyrules_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
