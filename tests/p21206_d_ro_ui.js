// kalmido-suite: fresh
// 2.1206.0 (#6161, Stufe 3): the office's quotations and invoices follow the core's write rule (canWrite + the server's
// can_edit with the role). jsdom, invented data only. Used like a person:
// - the reader (organisation role read-only) opens a quotation from the list: its number and positions are there, the fields
//   read, ONE read hint; no Finalise, no Add service / Heading / Text block, no move / remove of a position, no next step
//   (Create invoice), no Adjust prices / Duplicate / Delete in "More", no New in the list; back to the list works
// - an invoice draft: the reader sees its position, no Discount, no Finalise
// - the member opens the same quotation: Finalise, Add service, Create invoice, New in the list, no read hint
const {boot, B, login, idle, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 100});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const FEAT = 'cal,comments,collab,office,clients';

(async () => {
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: 'Studio Example', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  check(su.http < 300, 'admin setup ' + su.http + ' ' + JSON.stringify(su).slice(0, 200));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  for (const [u, role] of [['rita', 'readonly'], ['bob', 'member']]) {
    const x = await call('POST', '/api/users', {orgs: [{id: ORG, role}], username: u, display_name: u[0].toUpperCase() + u.slice(1), password: 'password123', email: `${u}@example.com`});
    check(x.http < 300, `create ${u} as ${role} ${x.http}`);
    await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${ORG}`}, await login(u));
  }
  const q = await call('POST', '/api/office/docs', {project_title: 'Spring campaign'});
  check(q.http === 201, 'a quotation ' + q.http + ' ' + JSON.stringify(q).slice(0, 300));
  await call('PUT', `/api/office/docs/${q.id}/items`, {items: [{title: 'Concept workshop', qty: 2, rate: 800}]});
  const inv = await call('POST', '/api/office/docs', {kind: 'invoice', project_title: 'Spring invoice'});
  check(inv.http === 201 && inv.kind === 'invoice', 'an invoice draft ' + inv.http + ' ' + inv.kind);
  await call('PUT', `/api/office/docs/${inv.id}/items`, {items: [{title: 'Editing day', qty: 1, rate: 900}]});
  const rq = await call('GET', `/api/office/docs/${q.id}`, null, await login('rita'));
  check(rq.can_edit === false && rq.locked === false, 'the server: the reader gets can_edit false on an open draft');

  // ================= the reader
  let w = await boot({user: 'rita', hash: 'office/offers'}), d = w.document;
  const row = await until(() => d.querySelector(`.ofdlist [data-ofd="open"][data-id="${q.id}"]`));
  check(!!row && /Spring campaign/.test(row.textContent), 'reader: the list shows the quotation');
  check(!d.querySelector('[data-ofd="new"]') && !d.querySelector('[data-ofd="trash"]'), 'reader: no New quotation, no trash in the list');
  click(w, row);
  const it = await until(() => d.querySelector('.ofdeditor .ofdits .ofdit input[data-k="title"]'));
  check(it && it.value === 'Concept workshop', 'reader: the position is there ' + (it && it.value));
  check(/Spring campaign/.test(d.querySelector('#ofd-project_title')?.value || ''), 'reader: the project title is there');
  check([...d.querySelectorAll('fieldset.ofdfs')].every(f => f.disabled), 'reader: the fields read');
  check(d.querySelectorAll('.cwro').length === 1 && /only read this document/.test(d.querySelector('.cwro')?.textContent || ''), 'reader: one read hint ' + d.querySelectorAll('.cwro').length);
  check(!d.querySelector('[data-ofd="finalize"]') && !d.querySelector('[data-ofd="it-svc"]') && !d.querySelector('[data-ofd="it-head"]') && !d.querySelector('[data-ofd="it-text"]'), 'reader: no Finalise, no Add service / Heading / Text block');
  check(!d.querySelector('.ofdmv') && !d.querySelector('[data-ofd="it-del"]') && !d.querySelector('[data-ofd="fld-add"]'), 'reader: no move / remove of a position, no Add field');
  check(!d.querySelector('[data-ofd="to-invoice"]') && !d.querySelector('[data-ofd="kva-st"]') && !d.querySelector('[data-ofd="number"]'), 'reader: no next step, no Assign number');
  check(!d.querySelector('[data-dpj="sel"]') && !d.querySelector('#dpj-new'), 'reader: no project picker');
  const more = w.eval('ofdMoreItems(OFD.doc, false).filter(x => x && x.label).map(x => x.label)');
  check(!more.some(l => /Duplicate|Adjust prices|Delete|Move to another/.test(l)), 'reader: "More" has no write step: ' + more.join(', '));
  check(w.eval('ofe_can(OFD.doc)') === false, 'reader: no follow-up answers (Nachfassen)');
  click(w, d.querySelector('[data-ofd="back"]'));
  check(await until(() => d.querySelector(`.ofdlist [data-ofd="open"][data-id="${q.id}"]`)), 'reader: back to the list');
  await idle(w); w.close();

  w = await boot({user: 'rita', hash: 'office/invoices/' + inv.id}); d = w.document;
  const ii = await until(() => d.querySelector('.ofdeditor .ofdits .ofdit input[data-k="title"]'));
  check(ii && ii.value === 'Editing day', 'reader: the invoice position is there');
  check(!d.querySelector('[data-ofd="it-disc"]') && !d.querySelector('[data-ofd="finalize"]') && d.querySelectorAll('.cwro').length === 1, 'reader: invoice without Discount / Finalise, one read hint');
  await idle(w); w.close();

  // ================= the member: everything as before
  w = await boot({user: 'bob', hash: 'office/offers/' + q.id}); d = w.document;
  const bi = await until(() => d.querySelector('.ofdeditor .ofdits .ofdit input[data-k="title"]'));
  check(bi && bi.value === 'Concept workshop', 'member: the position');
  check(!!d.querySelector('[data-ofd="finalize"]') && !!d.querySelector('[data-ofd="it-svc"]') && !!d.querySelector('[data-ofd="to-invoice"]') && !!d.querySelector('.ofdmv'), 'member: Finalise, Add service, Create invoice, move');
  check(!d.querySelector('.cwro') && ![...d.querySelectorAll('fieldset.ofdfs')].some(f => f.disabled), 'member: no read hint, the fields write');
  check(w.eval('ofdMoreItems(OFD.doc, false).filter(x => x && x.label).map(x => x.label)').includes('Duplicate'), 'member: Duplicate in "More"');
  click(w, d.querySelector('[data-ofd="back"]'));
  check(await until(() => d.querySelector('.ofdbar [data-ofd="new"]')), 'member: New quotation in the list');
  await idle(w); w.close();

  check(errs.length === 0, 'no script errors: ' + errs.join(' | '));
  console.log(`p21206_d_ro_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
