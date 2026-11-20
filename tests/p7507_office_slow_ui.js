// kalmido-suite: fresh
// (#7507) UI: the office on a slow connection. Own container (start.sh), jsdom, a computer. Invented names and figures only.
// Fiona has no organisation (her private office): every step runs for a self-employed person.
// freelancer-matrix: office (fiona without an organisation)
// 1. a dialog's Save (New fixed cost): the answer held - the button is disabled and marked busy, a second press sends
//    nothing; released: exactly one fixed cost
// 2. the same dialog when the answer of the create gets lost (the server did it, the page hears nothing): the error shows in
//    the dialog, Save again sends the same Idempotency-Key (the dialog's id) and gets the first answer - still one row
// 3. a letter whose load fails (500): the error block with "Try again", never "does not exist"; Try again opens it;
//    a letter that is not there (404) still says so
// 4. the recipient search failing: "Could not be loaded" with Try again, never "Nothing matches."
// Every wait is on a real state of the page.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, until: until0} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const until = fn => until0(async () => { try { return await fn(); } catch { return false; } }, {timeout: 15000, step: 50});
const FEAT = 'cal,comments,collab,office,clients,docs';
// requests matching re ("METHOD /url") wait in w.__held until the test calls go() (the real request), lose() (the real
// request runs, its answer never reaches the page) or fail(text, status)
const hold = (w, re) => {
  w.__held = []; const f1 = w.__f1 || (w.__f1 = w.fetch);
  w.fetch = (u, o = {}) => re.test(`${o.method || 'GET'} ${u}`)
    ? new Promise((res, rej) => w.__held.push({u: String(u), key: (o.headers || {})['Idempotency-Key'] || '',
      go: () => res(f1(u, o)), lose: () => f1(u, o).then(() => rej(new TypeError('Failed to fetch')), rej),
      fail: (msg, st = 400) => res(new Response(JSON.stringify({error: msg}), {status: st, headers: {'content-type': 'application/json'}}))}))
    : f1(u, o);
};
const unhold = w => { if (w.__f1) w.fetch = w.__f1; };
const txt = (d, sel) => d.querySelector(sel)?.textContent || '';
const fixed = async (ck, label) => ((await call(ck, 'GET', '/api/office/fixed-costs')).items || []).filter(x => x.label === label);

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(CA, 'POST', '/api/users', {username: 'fiona', display_name: 'Fiona Solo', password: 'password123', email: 'fiona@example.com'});
  const CF = await login('fiona');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: 'private'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'setup: fiona has no organisation');
  const lt = await call(CF, 'POST', '/api/office/letters', {subject: 'Anfrage Lichtplan'});
  check(lt.http === 201 && lt.id > 0, 'setup: a letter draft ' + lt.http);

  const w = await boot({user: 'fiona', hash: 'office/start'}), d = w.document;
  check(await until(() => d.querySelector('#view .office')), 'the office start page');
  check(await until(() => w.eval("typeof rk_fixedModal === 'function' && typeof busyRun === 'function'")), 'the office code is there');

  // ================= 1. double press on Save: one request, one row
  hold(w, /^POST \/api\/office\/fixed-costs$/);
  w.eval('rk_fixedModal(null)');
  let md = await until(() => d.querySelector('.modal.ofcdlg'));
  check(!!md, '1: the dialog "New fixed cost" is open');
  md.querySelector('#cf-label').value = 'Studio Miete Nord';
  md.querySelector('#cf-amount').value = '450';
  const save = md.querySelector('[data-m="save"]');
  save.click();
  check(await until(() => w.__held.length === 1), '1: the first press sends the create (held)');
  check(save.disabled && save.getAttribute('aria-busy') === 'true', '1: while it runs Save is disabled and marked busy');
  save.disabled = false; save.click(); save.click();  // even a press that gets through (a fast second tap) sends nothing more
  await sleep(300);
  check(w.__held.length === 1, '1: a second and third press send nothing: ' + w.__held.length);
  check(/^dlg-/.test(w.__held[0].key), '1: the create carries the dialog\'s id as Idempotency-Key: ' + w.__held[0].key);
  w.__held[0].go();
  check(await until(() => !d.querySelector('.modal.ofcdlg')), '1: with the answer the dialog closes');
  check((await fixed(CF, 'Studio Miete Nord')).length === 1, '1: exactly one fixed cost on the server');

  // ================= 2. the answer gets lost: Save again = the same key, still one row
  hold(w, /^POST \/api\/office\/fixed-costs$/);
  w.eval('rk_fixedModal(null)');
  md = await until(() => d.querySelector('.modal.ofcdlg'));
  md.querySelector('#cf-label').value = 'Kamera Versicherung';
  md.querySelector('#cf-amount').value = '38,50';
  md.querySelector('[data-m="save"]').click();
  check(await until(() => w.__held.length === 1), '2: the create is sent (held)');
  const k1 = w.__held[0].key;
  w.__held[0].lose();
  check(await until(async () => (await fixed(CF, 'Kamera Versicherung')).length === 1), '2: the server made it (the page did not hear it)');
  check(await until(() => txt(md, '.aerr').trim().length > 0 && !md.querySelector('[data-m="save"]').disabled), '2: the dialog stays with the error, Save works again');
  w.__held = [];
  md.querySelector('[data-m="save"]').click();
  check(await until(() => w.__held.length === 1), '2: Save again sends the create once more');
  check(w.__held[0].key === k1 && !!k1, `2: with the same key (${k1} / ${w.__held[0].key})`);
  w.__held[0].go();
  check(await until(() => !d.querySelector('.modal.ofcdlg')), '2: the first answer comes back, the dialog closes');
  check((await fixed(CF, 'Kamera Versicherung')).length === 1, '2: still exactly one fixed cost (nothing twice)');
  // 2b (#7494 review F2): the answer gets lost, then a field is changed before Save again: a new key, the new content is saved
  // (the old key would hand back the first answer and the change would be lost while the dialog says it is done)
  w.__held = [];
  w.eval('rk_fixedModal(null)');
  md = await until(() => d.querySelector('.modal.ofcdlg'));
  md.querySelector('#cf-label').value = 'Licht Leasing';
  md.querySelector('#cf-amount').value = '120';
  md.querySelector('[data-m="save"]').click();
  check(await until(() => w.__held.length === 1), '2b: the create is sent (held)');
  const k2 = w.__held[0].key;
  w.__held[0].lose();
  check(await until(() => txt(md, '.aerr').trim().length > 0 && !md.querySelector('[data-m="save"]').disabled), '2b: the dialog stays with the error');
  w.__held = [];
  md.querySelector('#cf-amount').value = '135';
  md.querySelector('[data-m="save"]').click();
  check(await until(() => w.__held.length === 1), '2b: Save after the change sends the create');
  check(w.__held[0].key !== k2 && /^dlg-/.test(w.__held[0].key), `2b: with a new key for the new content (${k2} / ${w.__held[0].key})`);
  w.__held[0].go();
  check(await until(() => !d.querySelector('.modal.ofcdlg')), '2b: the dialog closes');
  check(await until(async () => (await fixed(CF, 'Licht Leasing')).some(x => Math.round(+x.amount) === 135)), '2b: the changed amount is on the server');
  unhold(w);

  // ================= 3. a letter that fails to load: Try again, not "does not exist"
  hold(w, new RegExp(`^GET /api/office/letters/${lt.id}$`));
  w.location.hash = `#office/letters/${lt.id}`;
  check(await until(() => w.__held.length >= 1), '3: the letter is requested (held)');
  w.__held.forEach(h => h.fail('Der Server ruht für den Test', 500));
  check(await until(() => d.querySelector('#view .eerr [data-esretry]')), '3: the failed load shows the error block with "Try again"');
  check(!/does not exist/.test(txt(d, '#view')), '3: it never says the letter does not exist');
  unhold(w);
  d.querySelector('#view .eerr [data-esretry]').click();
  check(await until(() => d.querySelector('#view #lt-rsearch')), '3: "Try again" opens the letter (its editor)');
  check(!d.querySelector('#view .eerr'), '3: the error block is gone');

  // ================= 4. the recipient search fails: no "Nothing matches."
  hold(w, /^GET \/api\/office\/letters\/recipients/);
  const inp = d.querySelector('#lt-rsearch');
  inp.value = 'Lichtwerk'; inp.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(await until(() => w.__held.length >= 1), '4: the search is sent (held)');
  w.__held.forEach(h => h.fail('Suche ruht', 500));
  check(await until(() => d.querySelector('#lt-sug .lt-sugerr [data-lt="rcretry"]')), '4: the failed search says it with "Try again"');
  check(!/Nothing matches/.test(txt(d, '#lt-sug')), '4: never "Nothing matches." for a failure');
  unhold(w);
  d.querySelector('#lt-sug [data-lt="rcretry"]').click();
  check(await until(() => /Nothing matches/.test(txt(d, '#lt-sug')) || d.querySelector('#lt-sug [data-lt="rc"]')), '4: "Try again" searches again (a real answer)');

  // ================= 3b. a letter that is not there still says so
  w.location.hash = '#office/letters/999999';
  check(await until(() => /does not exist/.test(txt(d, '#view .enoacc'))), '3b: a letter that is not there (404): "does not exist"');
  check(!d.querySelector('#view .eerr'), '3b: no error block for it');
  w.close();

  console.log(`p7507_office_slow_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e && e.stack || e); process.exit(1); });
