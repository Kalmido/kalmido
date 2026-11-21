// kalmido-suite: fresh
// #7504 UI: the autosave of a letter and of a document of "Writing & contracts" on the order of "write shows at once" (core.js
// rwRows, a text editor without rows). Own container (start.sh), jsdom, invented texts only. The saves are held by the test
// (boot.js hold) and let through or refused one at a time.
// A. two bursts of typing while the first save is held: the second save waits for the first answer and goes after it with
//    its version - two saves one after the other, no conflict bar, on the server the second text
// B. the editor says "Saving…" while a save is on its way and "Saved" after it
// C. a refused save (500): "Not saved" with "Try again", the text stays in the field and in this browser; Try again saves it
// D. "Back" waits visibly for the save (busy) and goes once it is through
// E. the document: the same order; its input is kept in this browser (fdKeep) until the server has it; the preview follows the
//    save (no preview request with the whole text beside it)
// freelancer-matrix: office (the person without an organisation uses the same editors)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, errs, hold} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, ms = 15000) => require('./boot').until(async () => { try { return await fn(); } catch { return false; } }, {timeout: ms, step: 50});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const type = (w, el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
const FEAT = 'office,clients';

async function round(who, ck, orgId) {
  // ================= the letter
  const L = await call(ck, 'POST', '/api/office/letters', {rcpt_name: 'Amt', subject: 'Antrag'});
  check(L.http === 201 || L.http === 200, `${who}: a letter ${L.http}`);
  let w = await boot({user: who, hash: `office/letters/${L.id}`}), d = w.document;
  check(await until(() => d.querySelector('#lt-body')), `${who}: the letter editor is open`);
  hold(w, new RegExp(`/api/office/letters/${L.id}$`));
  const st = () => d.querySelector('#lt-st')?.textContent || '';
  const lw = () => w.eval(`!!LT_WS.get(${L.id})?.pend`);
  type(w, d.querySelector('#lt-body'), 'First burst');
  check(await until(() => w.__q.length === 1), `${who}: A: the first save goes after the pause`);
  check(/Saving/.test(st()), `${who}: B: the editor says "Saving…": ` + st());
  type(w, d.querySelector('#lt-body'), 'First burst and the second one');
  check(await until(() => w.eval('LT_WS.get(' + L.id + ')?.wait') && true), `${who}: A: the second save waits behind the first`);
  check(w.__n === 1, `${who}: A: still one request on the line (${w.__n})`);
  w.__go();
  check(await until(() => w.__q.length === 1 && w.__n === 2), `${who}: A: after the first answer the second save goes (${w.__n})`);
  w.__go();
  check(await until(() => !lw()), `${who}: A: both saved`);
  check(!d.querySelector('.obj-merge') && !(d.querySelector('#lt-err')?.textContent || '').trim(), `${who}: A: no conflict bar, no error: ` + (d.querySelector('#lt-err')?.textContent || ''));
  check((await call(ck, 'GET', `/api/office/letters/${L.id}`)).body === 'First burst and the second one', `${who}: A: the second text on the server`);
  check(await until(() => /Saved/.test(st())), `${who}: B: the editor says "Saved": ` + st());

  // C. a refused save
  type(w, d.querySelector('#lt-body'), 'Third text');
  check(await until(() => w.__q.length === 1), `${who}: C: the save is on its way`);
  w.__fail(500);
  check(await until(() => /Not saved/.test(st()) && d.querySelector('#lt-st [data-rwagain]')), `${who}: C: "Not saved" with "Try again": ` + st());
  check(d.querySelector('#lt-body').value === 'Third text', `${who}: C: the text stays in the field`);
  check(/Third text/.test(w.eval(`JSON.stringify(fdGet('ltpend', ${L.id}))`) || ''), `${who}: C: the text stays in this browser`);
  click(w, d.querySelector('#lt-st [data-rwagain]'));
  check(await until(() => w.__q.length === 1), `${who}: C: Try again sends it`); w.__go();
  check(await until(async () => (await call(ck, 'GET', `/api/office/letters/${L.id}`)).body === 'Third text'), `${who}: C: saved`);
  check(await until(() => /Saved/.test(st()) && !w.eval(`fdGet('ltpend', ${L.id})`)), `${who}: C: "Saved", nothing kept any more`);

  // D. Back waits visibly
  type(w, d.querySelector('#lt-body'), 'Fourth text');
  const back = d.querySelector('[data-lt="back"]');
  click(w, back);
  check(await until(() => w.__q.length === 1), `${who}: D: Back saves first`);
  check(back.getAttribute('aria-busy') === 'true' && back.classList.contains('rwwait'), `${who}: D: the button shows that it waits`);
  w.__go();
  check(await until(() => !d.querySelector('#lt-body')), `${who}: D: then back in the list`);
  check((await call(ck, 'GET', `/api/office/letters/${L.id}`)).body === 'Fourth text', `${who}: D: saved`);
  w.__off(); w.close();

  // ================= the document of "Writing & contracts"
  const CL = (await call(ck, 'POST', '/api/clients', {name: 'Example Media GmbH', ...(orgId ? {org_id: orgId} : {})})).id;
  const G = await call(ck, 'POST', '/api/office/gen-docs', {title: 'Note', body: 'First text', client_id: CL});
  check(G.http === 201, `${who}: a document ${G.http}`);
  w = await boot({user: who, hash: `office/gendocs/${G.id}`}); d = w.document;
  check(await until(() => d.querySelector('#dt-body') && d.querySelector('.dtp-pv .dtp-doc')), `${who}: E: the document editor with its preview`);
  hold(w, /\/api\/office\/gen-docs(\/\d+|\/preview)$/);
  const log = []; { const f1 = w.fetch; w.fetch = (u, o) => { log.push(`${(o && o.method) || 'GET'} ${String(u)} ${o && typeof o.body === 'string' ? o.body.slice(0, 80) : ''}`); return f1(u, o); }; }
  const dst = () => d.querySelector('#dt-st')?.textContent || '';
  const dw = () => w.eval(`!!DT_WS.get(${G.id})?.pend`);
  type(w, d.querySelector('#dt-body'), 'Doc burst one');
  check(await until(() => w.__q.length === 1), `${who}: E: the first save goes`);
  check(/Doc burst one/.test(w.eval(`JSON.stringify(fdGet('dtpend', ${G.id}))`) || ''), `${who}: E: the input is kept in this browser`);
  check(!log.some(x => /\/preview /.test(x) && /Doc burst/.test(x)), `${who}: E: no preview request with the text beside the save`);
  type(w, d.querySelector('#dt-body'), 'Doc burst one and two');
  check(await until(() => w.eval(`!!DT_WS.get(${G.id})?.wait`)), `${who}: E: the second save waits behind the first`);
  w.__go();
  check(await until(() => w.__q.some(() => true) && w.__n >= 2), `${who}: E: then the second goes (${w.__n})`);
  for (let t = 0; t < 100 && (dw() || w.__q.length); t++) { if (w.__q.length) w.__go(); await sleep(50); }
  check(await until(() => !dw()), `${who}: E: saved`);
  check(!d.querySelector('.obj-merge'), `${who}: E: no conflict bar`);
  check((await call(ck, 'GET', `/api/office/gen-docs/${G.id}`)).body === 'Doc burst one and two', `${who}: E: the second text on the server`);
  check(await until(() => /Saved/.test(dst()) && !w.eval(`fdGet('dtpend', ${G.id})`)), `${who}: E: "Saved", nothing kept any more: ` + dst());
  check(log.some(x => /^POST .*\/gen-docs\/preview/.test(x) && !/"body"/.test(x)), `${who}: E: the preview of the saved draft followed the save`);
  for (let t = 0; t < 40 && w.__q.length; t++) { w.__go(); await sleep(50); }
  w.__off();
  check(!errs.length, `${who}: no script errors ` + errs.join(' | ')); errs.splice(0);
  w.close();
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en'});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await round('alice', CA, org.id);
  const fr = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.http === 200 || fr.http === 201, 'freelancer created ' + fr.http);
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  check(!((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length, 'frida has no organisation');
  await round('frida', CF);
  console.log(`p7504_schreiben_kette_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
