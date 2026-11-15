// kalmido-suite: fresh
// 2.1185.0 UI test (#6150): the steps of a quotation without an answer and "Adjust prices" follow the editor's rules, own
// container (start.sh; P6150_NOSTART=1 / KMT_NOSTART=1: a running server), jsdom. Invented companies and figures only.
// - "Mark as rejected" says so in a toast with Undo; Undo -> the quotation is "sent" again and the note is back
// - "Extend validity": a refused date is said IN the open dialog (not in a toast behind it); OK -> a toast with Undo; Undo ->
//   the old date (in the past) is back on the server
// - the note offers no answers through a folder (via_folder) or without the right to edit quotations
// - "Follow up" fills the text in the quotation's language and says "was valid until" once the date is gone
// - "Adjust prices" opened straight on a quotation: title without "…", the mode "Surplus" for the admin, "Apply" off until
//   the preview arrived (empty field: off), Apply -> a toast with Undo; Undo -> the old unit prices
// - the approval box of a sent quotation calls its date "Link valid until"
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6150_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const ds = d => d.toISOString().slice(0, 10);
const day = n => { const d = new Date(); d.setHours(12, 0, 0, 0); d.setDate(d.getDate() + n); return ds(d); };
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const toastUndo = d => { const t = d.querySelector('#toast:not(.hidden)'); return t && [...t.querySelectorAll('button')].find(b => /Undo/.test(b.textContent)); };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,office,clients'});
  const me = (await call('GET', '/api/state')).me.id;
  const ORG = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me})).id;
  await call('PATCH', '/api/settings', {workspace: `org:${ORG}`});
  const cl = await call('POST', '/api/clients', {name: 'Nordlicht Studio GmbH', street: 'Hafenweg 2', zip: '20457', city: 'Hamburg', country: 'DE'});
  const sent = async (title, lang = 'en') => {
    const d = await call('POST', '/api/office/docs', {kind: 'offer', lang, client_id: cl.id, project_title: title,
      items: [{kind: 'service', title: 'Shooting', qty: 1, unit: 'day', rate: 900, tax: 'standard'}]});
    const p = await call('PATCH', `/api/office/docs/${d.id}`, {valid_until: day(-1), expect_updated_at: d.updated_at});
    check(p.http === 200, `setup: "valid until" yesterday on ${title} ${p.http}`);
    const s = await call('POST', `/api/office/docs/${d.id}/status`, {status: 'sent'});
    check(s.status === 'sent', `setup: ${title} marked sent`);
    return d.id;
  };
  const A1 = await sent('Imagefilm Hafen'), A2 = await sent('Werbespot Kai'), A3 = await sent('Doku Elbe', 'de');
  let w, d;

  // ================= "Mark as rejected": toast with Undo
  w = await boot({user: 'alice', hash: `office/offers/${A2}`}); d = w.document;
  click(w, await until(() => d.querySelector('.ofe-note [data-ofd="kva-st"][data-st="declined"]'), 80));
  check(await until(async () => (await call('GET', `/api/office/docs/${A2}`)).status === 'declined', 60), '"Mark as rejected" -> rejected on the server');
  const u1 = await until(() => toastUndo(d), 40);
  check(!!u1 && /rejected/i.test(txt(d.querySelector('#toast'))), '"Mark as rejected" says so with Undo: ' + txt(d.querySelector('#toast')));
  click(w, u1);
  check(await until(async () => (await call('GET', `/api/office/docs/${A2}`)).status === 'sent', 60), 'Undo -> the quotation is "sent" again');
  check(await until(() => d.querySelector('.ofe-note'), 60), 'Undo -> the note is back in the editor');

  // ================= the note's answers only with the right to edit, never through a folder
  const n0 = w.eval(`ofe_note({...OFD.doc, via_folder: true})`);
  check(/expired/.test(n0) && !/data-ofd=/.test(n0), 'through a folder the note informs but offers no answers');
  w.eval(`window.__r = OFC.info.rights; OFC.info.rights = {levels: {offers: 'view'}, specials: [], adm: [], manager: 'group'}`);
  check(!/data-ofd="ofe-ext"/.test(w.eval(`ofe_note(OFD.doc)`)), 'a person who may only view quotations gets no answers in the note');
  w.eval(`OFC.info.rights = {levels: {offers: 'edit'}, specials: ['release'], adm: [], manager: 'group'}`);
  check(/data-ofd="ofe-ext"/.test(w.eval(`ofe_note(OFD.doc)`)), 'with the right to edit quotations the answers are there');
  w.eval(`OFC.info.rights = window.__r`);
  w.close();

  // ================= "Extend validity": the error in the dialog, then Undo
  w = await boot({user: 'alice', hash: `office/offers/${A1}`}); d = w.document;
  click(w, await until(() => d.querySelector('.ofe-note [data-ofd="ofe-ext"]'), 80));
  const inp = await until(() => d.querySelector('.modal #ofd-ofe-date'), 40);
  inp.value = day(-5);
  click(w, d.querySelector('.modal .foot [data-m="ok"]'));
  const aerr = await until(() => txt(d.querySelector('.modal .aerr')), 60);
  check(/today or later/.test(aerr || ''), 'a refused date is said inside the open dialog: ' + aerr);
  check(!!d.querySelector('.modal #ofd-ofe-date'), 'the dialog stays open after the refusal');
  check(!/today or later/.test(txt(d.querySelector('#toast:not(.hidden)'))), 'no toast with the same error behind the dialog');
  d.querySelector('.modal #ofd-ofe-date').value = day(14);
  click(w, d.querySelector('.modal .foot [data-m="ok"]'));
  check(await until(async () => (await call('GET', `/api/office/docs/${A1}`)).valid_until === day(14), 60), 'OK -> the server has the new date');
  const u2 = await until(() => toastUndo(d), 40);
  check(!!u2 && /Validity extended/.test(txt(d.querySelector('#toast'))), '"Extend validity" says so with Undo: ' + txt(d.querySelector('#toast')));
  click(w, u2);
  check(await until(async () => (await call('GET', `/api/office/docs/${A1}`)).valid_until === day(-1), 60), 'Undo -> the old date (yesterday) is back');
  check(await until(() => /expired/.test(txt(d.querySelector('.ofe-note'))), 60), 'Undo -> the note "expired" is back');
  w.close();

  // ================= "Follow up" in the quotation's language
  w = await boot({user: 'alice', hash: `office/offers/${A3}`}); d = w.document;
  await until(() => w.eval(`!!(OFD.doc && OFD.doc.id === ${A3})`), 80);
  w.eval(`ofdSendDialog(OFD.doc, {follow: true})`);
  const ta = await until(() => d.querySelector('.modal #ofd-s-text'), 60);
  check(/Guten Tag/.test(ta?.value || '') && /gültig war/.test(ta?.value || ''), 'the follow-up text of a German quotation is German and says "was valid": ' + (ta?.value || '').slice(0, 160));
  check(/Angebot/.test(d.querySelector('.modal #ofd-s-subject')?.value || ''), 'the subject is German too');
  w.close();

  // ================= "Adjust prices" opened straight on a draft
  const q = (await call('POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Herbstfilm', items: [{title: 'Edit', qty: 2, rate: 1000, ek: 300}, {title: 'Sound', qty: 1, rate: 500}]})).id;
  w = await boot({user: 'alice', hash: `office/offers/${q}`}); d = w.document;
  await until(() => w.eval(`!!(OFD.doc && OFD.doc.id === ${q})`) && d.querySelector('[data-ofd="more"]'), 80);
  await w.eval(`loadModule('reprice').then(() => { orp_open(OFD.doc); })`);
  const v = await until(() => d.querySelector('.orp-dlg #orp-v'), 40);
  const okb = () => d.querySelector('.orp-dlg [data-m="ok"]');
  check(txt(d.querySelector('.orp-dlg h3')) === 'Adjust prices', 'the dialog title has no dots: ' + txt(d.querySelector('.orp-dlg h3')));
  check(!!d.querySelector('.orp-dlg [data-orp-seg="mode"] [data-v="margin"]'), 'the mode "Surplus" is there for the admin when opened straight on the quotation');
  check(okb()?.disabled === true, '"Apply" is off while the field is empty');
  v.value = '10'; v.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(await until(() => okb() && !okb().disabled && /2[.,]750/.test(txt(d.querySelector('.orp-prev'))), 60), '"Apply" is on once the preview arrived: ' + txt(d.querySelector('.orp-prev')));
  v.value = ''; v.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(okb()?.disabled === true, 'emptied again -> "Apply" is off at once');
  v.value = '10'; v.dispatchEvent(new w.Event('input', {bubbles: true}));
  await until(() => okb() && !okb().disabled, 60);
  click(w, okb());
  check(await until(async () => (await call('GET', `/api/office/docs/${q}`)).items.map(x => +x.rate).join() === '1100,550', 60), 'Apply -> stored 1100 and 550');
  const u3 = await until(() => toastUndo(d), 40);
  check(!!u3 && /Prices changed/.test(txt(d.querySelector('#toast'))), '"Prices changed" with Undo: ' + txt(d.querySelector('#toast')));
  click(w, u3);
  check(await until(async () => (await call('GET', `/api/office/docs/${q}`)).items.map(x => +x.rate).join() === '1000,500', 60), 'Undo -> the old unit prices 1000 and 500');
  check(await until(() => { const r = [...d.querySelectorAll('#view input[data-k="rate"]')].map(x => x.value); return r.length === 2 && /1[.,]?000/.test(r[0]) && /500/.test(r[1]); }, 60),
    'Undo -> the editor shows the old prices: ' + [...d.querySelectorAll('#view input[data-k="rate"]')].map(x => x.value).join(' | '));
  w.close();

  // ================= the approval box: "Link valid until"
  w = await boot({user: 'alice', hash: `office/offers/${A2}`}); d = w.document;
  const lab = await until(() => d.querySelector('#sg-box label[for="sg-exp"]'), 80);
  check(txt(lab) === 'Link valid until', 'the approval box names the link\'s date "Link valid until": ' + txt(lab));
  check(!errs.length, 'no script errors: ' + errs.join(' | '));
  w.close();

  console.log(`p6150_offer_steps_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
