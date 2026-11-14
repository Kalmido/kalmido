// 2.1180.0 D UI test (#6149): call sheets in the shared blocks. Own container (start.sh). Invented names only.
// kalmido-suite: fresh
// - the empty tab is the shared empty block with its own button "New call sheet" (no grey sentence)
// - "New call sheet" is a dialog form (askDialog): the confirm button has the focus (Enter creates), an empty day is an error
//   INSIDE the dialog (it stays open), a day -> the call sheet opens
// - the logo choice is a dialog form too; the logo button's accessible name starts with its visible text "Add logo"
// - mail without a mail setup: a dialog with "Download PDF" (not only a toast)
// - mail send fails: the "Send" button keeps its symbol (and the error is in the dialog); the focus is on the heading after
//   each step
// P21180DUI_NOSTART=1 = the server already runs.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21180DUI_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = fn => require('./boot').until(fn, {timeout: 15000, step: 150});
const FEAT = 'collab,comments,contacts,office,clients,workload,dispo,kanban';
const dstr = x => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const A = await login('alice');
  await call(A, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  const me = (await call(A, 'GET', '/api/state')).me;
  const org = await call(A, 'POST', '/api/admin/orgs', {name: 'Beispiel Studio', admin_id: me.id});
  await call(A, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${org.id}`});
  await call(A, 'PUT', '/api/industry', {industries: ['film']});
  const L = await call(A, 'POST', '/api/lists', {name: 'Kinospot Sommer', kind: 'project', org_id: org.id});
  const t = new Date(), D = dstr(new Date(t.getFullYear(), t.getMonth(), t.getDate() + 5));
  check(org.id && L.id, 'setup: organisation, Film & Video, a project');

  const w = await boot({user: 'alice', hash: `l/${L.id}`}), d = w.document;
  w.__dialogs = 'manual';  // the dialogs are driven here (boot.js would answer them with w.confirm)
  (await until(() => d.querySelector('#top [data-act="view-callsheets"]')))?.click();
  await until(() => d.querySelector('#view .pcs .pcsbar') && !/Loading/.test(txt(d.querySelector('#view .pcs'))));

  // ================= empty block with the button
  const em = d.querySelector('#view .pcs .eact');
  check(em && /No call sheets yet/.test(txt(em)) && !d.querySelector('#view .pcsempty'), 'the empty tab is the shared empty block ' + txt(d.querySelector('#view .pcs')).slice(0, 120));
  const eb = em?.querySelector('[data-pcs="new"]');
  check(eb && /New call sheet/.test(txt(eb)), 'the empty block has the button "New call sheet"');

  // ================= the dialog: a form, focus on confirm, an error stays inside
  eb?.click();
  const nm = await until(() => d.querySelector('.modal.cdlg form.cdlg-f #pcs-day') && d.querySelector('.modal.cdlg'));
  check(!!nm, 'New call sheet is a dialog form (askDialog)');
  await until(() => d.activeElement?.dataset?.cd === 'yes');
  check(d.activeElement?.dataset?.cd === 'yes' && d.activeElement.type === 'submit', 'the confirm button has the focus: Enter creates');
  nm.querySelector('#pcs-day').value = '';
  nm.querySelector('form').requestSubmit();
  const er = await until(() => { const e = nm.querySelector('.cserr'); return e && !e.hidden && e; });
  check(er && /select a date/i.test(txt(er)) && d.querySelector('.modal.cdlg'), 'an empty day: the error is in the dialog, the dialog stays open');
  nm.querySelector('#pcs-day').value = D;
  nm.querySelector('form').requestSubmit();
  const md = await until(() => d.querySelector('.modal.csmd #cs-loc_name') && d.querySelector('.modal.csmd'));
  check(md && !d.querySelector('.modal.cdlg'), 'a day: the dialog closes, the call sheet opens');

  // ================= logo: the button name starts with its text; the choice is a dialog form
  const bk = await call(A, 'POST', '/api/books', {name: 'Kontakte', org_id: org.id});
  await call(A, 'POST', '/api/contacts', {book_id: bk.id, kind: 'org', fn: 'Werbe Beispiel GmbH'});
  md.querySelector('[data-cs="close"]')?.click();
  await until(() => !d.querySelector('.modal.csmd'));
  d.querySelector('#view .pcsrow [data-pcs="open"]')?.click();
  const md2 = await until(() => d.querySelector('.modal.csmd #cs-loc_name') && d.querySelector('.modal.csmd'));
  const lb = md2?.querySelector('.cslogo[data-logo="agency"] [data-cs="logo"]');
  if (lb) {
    const an = lb.getAttribute('aria-label') || '';
    check(/^Add logo/.test(an) && an.startsWith(txt(lb)), 'the logo button\'s accessible name starts with its visible text: ' + an);
    lb.click();
    const lq = await until(() => d.querySelector('.modal.cdlg form.cdlg-f #cs-logoct') && d.querySelector('.modal.cdlg'));
    check(!!lq, 'the logo choice is a dialog form');
    lq?.querySelector('[data-cd="no"]')?.click();
    await until(() => !d.querySelector('.modal.cdlg'));
  } else check(false, 'the call sheet shows "Add logo" for the agency');

  // ================= mail: no mail setup -> a dialog with "Download PDF"
  md2?.querySelector('[data-cs="mail"]')?.click();
  const nd = await until(() => d.querySelector('.modal.cdlg') && /Download PDF/.test(txt(d.querySelector('.modal.cdlg'))) && d.querySelector('.modal.cdlg'));
  check(!!nd, 'no mail setup: a dialog with "Download PDF" ' + txt(d.querySelector('.modal.cdlg')).slice(0, 100));
  nd?.querySelector('[data-cd="no"]')?.click();
  await until(() => !d.querySelector('.modal.cdlg'));

  // ================= mail: a failed send keeps the symbol; the focus is on the heading after each step
  // the mail routes are answered here (a configured mail setup, one recipient; the send itself fails)
  const f0 = w.fetch;
  const J = (st, o) => new Response(JSON.stringify(o), {status: st, headers: {'content-type': 'application/json'}});
  w.fetch = (u, o = {}) => {
    if (!/\/callsheet\/[0-9a-f]+\/mail\?/.test(String(u))) return f0(u, o);
    if ((o.method || 'GET') === 'GET') return Promise.resolve(J(200, {sender: {way: 'smtp'}, recipients: [{name: 'Kim Kamera', email: 'kim@example.com', group: 'crew'}], without: [], max: 20, subject: 'S', text: 'T', filename: 'callsheet.pdf'}));
    if (JSON.parse(o.body).preview) return Promise.resolve(J(200, {recipients: [{name: 'Kim Kamera', email: 'kim@example.com'}], subject: 'S', text: 'T', file: {name: 'callsheet.pdf', size: 1000}, sender: {}}));
    return Promise.resolve(J(502, {error: 'Mail server not reachable'}));
  };
  md2?.querySelector('[data-cs="mail"]')?.click();
  const mm = await until(() => d.querySelector('.modal.csmail [data-csm="preview"]') && d.querySelector('.modal.csmail'));
  await until(() => d.activeElement?.tagName === 'H3');
  check(d.activeElement?.tagName === 'H3' && mm.contains(d.activeElement), 'mail form: the focus is on the heading');
  mm.querySelector('[data-csm="preview"]').click();
  await until(() => mm.querySelector('[data-csm="send"]'));
  await until(() => d.activeElement?.tagName === 'H3' && /Preview/.test(txt(d.activeElement)));
  check(/Preview/.test(txt(d.activeElement)), 'mail preview: the focus is on the heading');
  const sb = mm.querySelector('[data-csm="send"]');
  sb.click();
  const er2 = await until(() => { const e = mm.querySelector('.cserr'); return e && !e.hidden && e; });
  check(er2 && /not reachable/.test(txt(er2)), 'a failed send: the reason is in the dialog');
  const sb2 = mm.querySelector('[data-csm="send"]');
  check(sb2 && !sb2.disabled && sb2.querySelector('svg') && /Send/.test(txt(sb2)) && !/Sending/.test(txt(sb2)), 'a failed send: "Send" is back with its symbol ' + sb2?.innerHTML.slice(0, 80));
  w.close();

  console.log(`p21180_d_callsheet_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
