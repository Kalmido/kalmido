// kalmido-suite: fresh
// (#7531) UI test (Firefox, 390 px phone), fresh DB: "Report a problem" through the shared intake
// - "Report a problem" (rptOpen, the palette's and the About page's entry) opens the dialog, not GitHub, once the admin chose a project
// - the context block shows page, version, the last browser error and the failed request before sending; a text typed into a
//   form of the page is nowhere in it (neither shown nor sent)
// - Send with an empty required field asks for it; switching to "A wish" and back keeps the typed text
// - sent: the dialog closes; opened again it lists the report under "Already reported" with the state "Open"; Cancel closes
// - the task in the project carries the block as its own attachment without the typed text
const {errs, B, login, sleep} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21514_c_meldung_ui', check, shots: 'P21514C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const call = async (method, url, body, ck) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const SECRET = 'Vertraulicher Entwurf Zebra';

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']}, CK);
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'}, CK);
  const P = (await call('POST', '/api/lists', {name: 'Support'}, CK)).id;
  check((await call('PATCH', `/api/lists/${P}/error-hook`, {state: 'on'}, CK)).status === 200, 'setup: error reports on');
  check((await call('PATCH', '/api/admin/settings', {client_errors_list: P}, CK)).status === 200, 'setup: the project takes reports');
  const T0 = await call('POST', '/api/tasks', {title: 'Draft letter', list_id: P}, CK);  // its panel is the filled form

  await firefox(async ({cmd, ev, nav, ctx, shot}) => {
    const waitEv = async (js, n = 100) => { for (let i = 0; i < n && !(await ev(js).catch(() => false)); i++) await sleep(100); return ev(js).catch(() => false); };
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.ok)`), 'firefox: logged in');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 800}});
    await nav(B + '#l/' + P);
    check(await waitEv(`typeof S !== 'undefined' && !!S.booted && !!S.about?.client_errors`), 'the app is up and knows reports are taken');
    // a filled form on the page, a failed request and an uncaught error
    await ev(`(openDetail(${T0.id}), 1)`);
    await waitEv(`[...document.querySelectorAll('#detail input[type="text"], #detail input:not([type]), #detail textarea')].some(x => x.offsetParent)`);
    const typed = await ev(`(() => { const i = [...document.querySelectorAll('#detail input[type="text"], #detail input:not([type]), #detail textarea')].find(x => x.offsetParent); if (!i) return false; i.value = ${JSON.stringify(SECRET)}; i.dispatchEvent(new Event('input', {bubbles: true})); return true; })()`);
    check(typed, 'a field of the task panel is filled');
    await ev(`api('GET', '/api/tasks/987654').catch(() => 1).then(() => 1)`);
    // (#7531 F11): a nested route with a word in its path: the browser sends the real path, the server keeps its route's pattern
    await ev(`api('PUT', '/api/lists/987655/members', {user_id: 987656, role: 'edit'}).catch(() => 1).then(() => 1)`);
    await ev(`(setTimeout(() => { throw new Error('Boom in step ' + ${JSON.stringify(JSON.stringify(SECRET))}); }, 0), 1)`);
    await waitEv(`CER_LAST.length > 0 && CER_REQ.length > 1`);
    check(await ev(`CER_REQ.some(q => q.path === '/api/lists/987655/members')`), 'F11: the browser keeps the real path to send ' + await ev('JSON.stringify(CER_REQ)'));
    // ---- in: "Report a problem" (the palette's and the About page's entry call rptOpen)
    await ev(`(rptOpen(), 1)`);
    check(await waitEv(`!!document.querySelector('.modal.rptdlg [data-rptf="problem"]')`), 'Report a problem opens the dialog');
    const D = `(() => { const m = document.querySelector('.modal.rptdlg'); if (!m) return null; const d = m.querySelector('.rptctxd'); if (d) d.open = true;
      return {txt: m.textContent, ctx: (m.querySelector('.rptctx') || {}).textContent || '', fields: [...m.querySelectorAll('[data-rptf]')].map(t => t.dataset.rptf), box: !!m.querySelector('#rpt-ctx:checked'), w: m.querySelector('.card').getBoundingClientRect().width, iw: innerWidth}; })()`;
    const d0 = await ev(D);
    check(d0 && d0.fields.join() === 'problem,expected' && d0.box, 'bug fields and the box "send these details along" ' + JSON.stringify(d0 && d0.fields));
    check(d0 && d0.ctx.includes('#l/' + P) && /Version/.test(d0.ctx) && /\/api\/tasks\/987654 · 404/.test(d0.ctx) && /PUT \/api\/lists\/987655\/_ · /.test(d0.ctx) && /Boom in step/.test(d0.ctx), 'the block shows page, version, the failed requests (a word of the path masked for the eye, F11) and the error ' + (d0 && d0.ctx));
    check(d0 && !d0.txt.includes(SECRET) && !d0.ctx.includes('Zebra'), 'the typed text is nowhere in the dialog');
    check(d0 && d0.w <= d0.iw, 'the dialog fits the phone');
    await shot('p21514c-dialog-390.png');
    // ---- on: a required field empty
    await ev(`(() => { document.querySelector('[data-rptf="problem"]').value = 'Totals jump after saving'; document.querySelector('[data-rptm="send"]').click(); return 1; })()`);
    check(await waitEv(`document.activeElement?.dataset?.rptf === 'expected' && document.querySelector('[data-rptf="expected"]').getAttribute('aria-invalid') === 'true'`), 'Send without "Expected": the field asks for it');
    check(await ev(`!!document.querySelector('.modal.rptdlg')`), '... the dialog stays open');
    // switch to a wish and back: the typed text stays
    await ev(`(document.querySelector('[data-rptk="wish"]').click(), 1)`);
    check(await waitEv(`[...document.querySelectorAll('[data-rptf]')].map(t => t.dataset.rptf).join() === 'want,blocker,how'`), 'A wish: its three fields');
    await ev(`(document.querySelector('[data-rptk="bug"]').click(), 1)`);
    check(await waitEv(`document.querySelector('[data-rptf="problem"]')?.value === 'Totals jump after saving'`), 'back to the bug: the typed problem is still there');
    await ev(`(() => { document.querySelector('[data-rptf="expected"]').value = 'Totals stay'; document.querySelector('[data-rptm="send"]').click(); return 1; })()`);
    check(await waitEv(`!document.querySelector('.modal.rptdlg')`), 'sent: the dialog closes');
    // ---- again: the report with its state; back out with Cancel
    await ev(`(rptOpen(), 1)`);
    check(await waitEv(`/Totals jump after saving/.test(document.querySelector('.modal.rptdlg .rptlist')?.textContent || '')`), 'opened again: "Already reported" lists it');
    check(await ev(`/Open/.test(document.querySelector('.modal.rptdlg .rptlist .rpts')?.textContent || '')`), '... with the state Open');
    await shot('p21514c-reported-390.png');
    await ev(`(document.querySelector('[data-rptm="close"]').click(), 1)`);
    check(await waitEv(`!document.querySelector('.modal.rptdlg')`), 'Cancel closes the dialog');
  });

  // the task in the project: the block as its own attachment, without the typed text
  const st = await call('GET', '/api/state', null, CK);
  const t = (st.tasks || []).find(x => x.list_id === P && /Totals jump/.test(x.title));
  check(!!t, 'the task is in the support project');
  const T = t ? await call('GET', `/api/tasks/${t.id}`, null, CK) : {};
  const a = (T.attachments || []).find(x => x.name === 'kalmido-context.json');
  check(!!a, 'the block is its own attachment');
  const raw = a ? await (await fetch(B + `api/attachments/${a.id}`, {headers: {...H, Cookie: CK}})).text() : '';
  check(raw.includes(`"route": "#l/${P}"`) && raw.includes('/api/tasks/<int:tid>') && raw.includes('/api/lists/<int:lid>/members') && !raw.includes('/_') && !raw.includes('987654') && !raw.includes('987655') && !raw.includes('Zebra') && !raw.includes('Vertraulich'), 'the sent block: page and request, not the typed text ' + raw.slice(0, 300));
  check(/Totals stay/.test(T.content || '') && !/987654/.test(T.content || ''), 'the notes: the fields, nothing of the block');

  check(!errs.filter(e => !/Boom in step/.test(e)).length, 'no script errors: ' + errs.join(' | '));
  console.log(`p21514_c_meldung_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p21514_c_meldung_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
