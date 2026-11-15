// kalmido-suite: fresh
// 2.1185.0 UI test (#6151): the rest of the office polish round 1, own container (start.sh; P6151_NOSTART=1 / KMT_NOSTART=1: a
// running server), jsdom. Invented companies and figures only.
// - the send dialog without mail sending: ONE sentence ("not set up" once), the mail form out of sight, the button "Download PDF"
// - an empty office log uses the shared empty block
// - a refused pack step (office_packs.js pkc_req) says its error once, not a second toast after api()'s
// - the office start page (phone): the figures card has the row "Overdue" while loading AND with the figures (no growth by a
//   row), the menu pen is a labelled button below the menu, not an empty line above the card
// - a computer: an open quotation has one way back ("< Quotations"), no path line
// - receipts: the upload button says "Upload receipt" on a computer too; an office without receipts shows ONE upload button,
//   which opens the file choice
// - "Times to bill": the page's heading is not repeated inside the page
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6151_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const shown = el => !!el && !el.closest('[hidden]');

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients,time'});
  const me = (await call('GET', '/api/state')).me.id;
  const ORG = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me})).id;
  await call('PATCH', '/api/settings', {workspace: `org:${ORG}`});
  const cl = await call('POST', '/api/clients', {name: 'Nordlicht Studio GmbH', street: 'Hafenweg 2', zip: '20457', city: 'Hamburg', country: 'DE'});
  const q = await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', client_id: cl.id, project_title: 'Imagefilm Hafen',
    items: [{kind: 'service', title: 'Shooting', qty: 1, unit: 'day', rate: 900, tax: 'standard'}]});
  let w, d;

  // ================= a computer: the quotation, the send dialog without mail, the pack error, the empty log
  w = await boot({user: 'alice', hash: `office/offers/${q.id}`}); d = w.document;
  await until(() => w.eval(`!!(OFD.doc && OFD.doc.id === ${q.id})`) && d.querySelector('.ofdhead .ofdback'), 80);
  check(/Quotations/.test(d.querySelector('.ofdhead .ofdback')?.getAttribute('aria-label') || '') && !d.querySelector('#view .ofmcrumb'),
    'computer: the open quotation has one way back ("< Quotations") and no path line');
  w.eval(`window.__api = api; api = (m, u, b) => u === '/api/office/mail-status' ? Promise.resolve({smtp: false, datev_email: ''}) : window.__api(m, u, b); ofdSendDialog(OFD.doc); 1`);
  const md = await until(() => d.querySelector('.modal .ofd-mailf')?.closest('.modal'), 60);
  const warn = [...(md?.querySelectorAll('.ofdwarn:not(.ofdmiss)') || [])];
  check(warn.length === 1 && /not set up: download the PDF/.test(txt(warn[0])), 'without mail: one sentence: ' + warn.map(txt).join(' | '));
  check((txt(md).match(/not set up/g) || []).length === 1, '"not set up" is said once: ' + txt(md).slice(0, 200));
  check(md?.querySelector('.ofd-mailf')?.hidden === true && !shown(md?.querySelector('#ofd-s-to')) && !shown(md?.querySelector('#ofd-s-text')), 'without mail no empty mail form is shown');
  check(txt(md?.querySelector('[data-m="ok"]')) === 'Download PDF', 'without mail the button downloads the PDF');
  md?.querySelector('[data-m="close"]')?.click();
  w.eval(`api = window.__api; 1`);

  check(/nempty/.test(w.eval(`OFC.log = []; ofcLogHtml()`)), 'an empty office log uses the shared empty block');
  w.eval(`OFC.log = null; 1`);

  check(await until(() => w.eval(`typeof pkc_req === 'function'`), 40), 'the packs module is there');
  await w.eval(`window.__toasts = []; window.__toast = toast; toast = (...a) => { window.__toasts.push(a[0]); return window.__toast(...a); }; pkc_after = async () => {}; pkc_req('DELETE', '/api/office/packs/installed/country/zz')`);
  const ts = w.eval(`window.__toasts.slice()`);
  check(ts.length === 1, 'a refused pack step says its error once: ' + JSON.stringify(ts));
  w.eval(`toast = window.__toast; 1`);
  w.close();

  // ================= receipts on a computer: one upload, one word
  w = await boot({user: 'alice', hash: 'office/receipts'}); d = w.document;
  const none = await until(() => d.querySelector('#view .rcl-none'), 80);
  const ups = [...d.querySelectorAll('#view button, #view label')].filter(e => /Upload (receipt|files)/.test(txt(e)) && shown(e));
  check(!!none && ups.length === 1 && txt(ups[0]) === 'Upload receipt', 'an office without receipts shows ONE upload button: ' + ups.map(txt).join(' | '));
  w.eval(`window.__picked = 0; document.querySelector('#bk-files').click = () => { window.__picked++; }; 1`);
  d.querySelector('#view .rcl-none [data-rcl="upfirst"]').click();
  check(w.eval(`window.__picked`) === 1, '"Upload receipt" opens the file choice');
  check(/Upload receipt/.test(w.eval(`bkPhotoHtml(false)`)) && !/Upload files</.test(w.eval(`bkPhotoHtml(false)`)), 'the computer\'s upload button says "Upload receipt"');
  w.close();

  // ================= "Times to bill": the heading once
  w = await boot({user: 'alice', hash: 'office/time'}); d = w.document;
  await until(() => d.querySelector('#view #tbl-from') || d.querySelector('#view [id="tbl-from"]'), 80);
  check(!!d.querySelector('#view .tbl-bar') && ![...d.querySelectorAll('#view h2, #view h3')].some(h => /Times to bill/.test(txt(h))), 'the page does not repeat its heading "Times to bill"');
  w.close();

  // ================= a phone: the office start page
  w = await boot({user: 'alice', mobile: true, hash: 'office/start'}); d = w.document;
  const st = await until(() => d.querySelector('#view .ofmstart'), 80);
  check(!!st && !st.firstElementChild?.classList.contains('navpen'), 'phone: no line with only the pen above the figures');
  const pen = d.querySelector('#view .ofmstart .ofmpen [data-act="nav-edit"]');
  check(!!pen && /Edit menu/.test(txt(pen)) && st.lastElementChild?.classList.contains('ofmpen'), 'phone: "Edit menu" is a labelled button below the menu');
  const rows = () => [...d.querySelectorAll('#view .ofmfig .kptl li')].map(txt);
  const loading = w.eval(`(() => { const o = KPT.data; KPT.data = undefined; KPT.loading = true; const h = kp_tile(c => c); KPT.data = o; KPT.loading = false; return h; })()`);
  check(/Overdue/.test(loading), 'phone: the card keeps the row "Overdue" while it loads');
  check(await until(() => rows().some(x => /Overdue/.test(x)) && !rows().some(x => /…/.test(x)), 80), 'phone: with the figures (nothing overdue) the row "Overdue" stays: ' + rows().join(' | '));
  check(rows().length === (loading.match(/<li/g) || []).length, `phone: the card has as many rows loaded as while loading (${rows().length})`);
  check(!errs.length, 'no script errors: ' + errs.join(' | '));
  w.close();

  console.log(`p6151_buero_rest_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
