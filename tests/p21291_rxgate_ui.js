// kalmido-suite: fresh
// 2.1291.0 (#6474, audit #4791 A6) UI test, own container (hosted, mode workspaces), Firefox. Invented companies, clients
// and figures only. freelancer-matrix: office
// - a person without organisation (a finalised invoice) where Kalmido is hosted: Office > Settings > Data shows, under the
//   retention export, "Do without the export…"; the question names what it means; after "yes" the box says since when it
//   is declared and offers to take it back; taken back, the button is there again
// - the instance admin deletes that account: the retention step offers no waiver of her own, it says who can declare it;
//   after the person's declaration the step offers "Delete without the export (declared on ...)", and with it and the
//   confirmation the account goes
const path = require('path');
const crypto = require('crypto');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21291_rxgate_ui', check, shots: 'P21291RX_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
const KEY = crypto.randomBytes(32).toString('base64');
if (!process.env.P21291RX_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ` -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_HOSTED=1 -e KALMIDO_ORGCRYPT_DELAY=0 -e KALMIDO_SECRET_KEY=${KEY}`}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,office,clients,docs,files';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const u = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http < 300, 'a person without organisation ' + u.http);
  const FID = u.id;
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  await call(CF, 'PUT', '/api/office/settings', {company_fields: {name: 'Studio Frida', street: 'Teststrasse 1', zip: '20000', city: 'Hamburg', country: 'DE', tax_number: '12/345/67890', iban: 'DE02120300000000202051', bic: 'BYLADEM1001'}});
  const cl = await call(CF, 'POST', '/api/clients', {name: 'Client Ltd', street: 'Marktstrasse 5', zip: '50000', city: 'Koeln', country: 'DE'});
  const d = await call(CF, 'POST', '/api/office/docs', {kind: 'invoice', client_id: cl.id, service_from: '2026-03-01', service_to: '2026-03-02', items: [{title: 'Schnitt', qty: 1, rate: 120}]});
  check((await call(CF, 'POST', `/api/office/docs/${d.id}/finalize`)).http < 300, 'setup: a finalised invoice of frida');
  const info = await call(CF, 'GET', '/api/retention/me');
  check(info.hosted === true && info.needed === true && info.may_declare === true && !info.waived_at, 'setup: hosted, records to keep, nothing declared ' + JSON.stringify(info).slice(0, 300));

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, who) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`);
  const SEEN = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); return !!e && e.offsetParent !== null; })()`;
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});  // a phone first
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.ofcSetSub', '"data"'); return 1; })()`);
    await signIn(ev, 'frida');
    await nav(B + '#office/settings');
    check(await ready(ev, SEEN('.rxbox .rxwv [data-rxwvact="on"]'), 80), 'office settings > data: "Do without the export…" under the retention export');
    check(await ev(`/Do without the export/.test(document.querySelector('.rxwv [data-rxwvact="on"]').textContent)`), 'the button says what it does');
    await ev(`(() => { const b = document.querySelector('.rxwv [data-rxwvact="on"]'); b.scrollIntoView({block: 'center'}); b.click(); return 1; })()`);
    check(await ready(ev, SEEN('.modal [data-cd="yes"]'), 40), 'the question comes first');
    check(await ev(`/deleted without the export/.test(document.querySelector('.modal [data-cd="yes"]').closest('.modal').textContent) && /lost/.test(document.querySelector('.modal [data-cd="yes"]').closest('.modal').textContent)`), 'it says the records are lost then');
    await shot('p21291-rx-ask.png');
    await ev(`(() => { document.querySelector('.modal [data-cd="no"]').click(); return 1; })()`);
    check(await ready(ev, `!document.querySelector('.modal [data-cd="yes"]')`, 40) && !(await call(CF, 'GET', '/api/retention/me')).waived_at, 'cancel: nothing declared');
    await ev(`(() => { document.querySelector('.rxwv [data-rxwvact="on"]').click(); return 1; })()`);
    check(await ready(ev, SEEN('.modal [data-cd="yes"]'), 40), 'the question again');
    await ev(`(() => { document.querySelector('.modal [data-cd="yes"]').click(); return 1; })()`);
    check(await ready(ev, SEEN('.rxwv [data-rxwvact="off"]'), 60), 'declared: the box offers to take it back');
    check(await ev(`/Declared on/.test(document.querySelector('.rxwv').textContent) && !document.querySelector('.rxwv [data-rxwvact="on"]')`), 'the box says since when it is declared');
    check(!!(await call(CF, 'GET', '/api/retention/me')).waived_at, 'the server holds the declaration');
    await ev(`document.querySelector('.rxbox').scrollIntoView({block: 'center'})`);
    await shot('p21291-rx-declared.png');
    await ev(`(() => { document.querySelector('.rxwv [data-rxwvact="off"]').click(); return 1; })()`);
    check(await ready(ev, SEEN('.rxwv [data-rxwvact="on"]'), 60) && !(await call(CF, 'GET', '/api/retention/me')).waived_at, 'taken back: the button is there again, the server holds none');

    // the instance admin deletes frida: no waiver of her own
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    await signIn(ev, 'alice');
    await nav(B + '#inbox');
    check(await ready(ev, `typeof ua8_delete === 'function' && typeof rxAsk === 'function'`, 80), 'the app is loaded');
    await ev(`(() => { window.__del = 'pending'; ua8_delete({id: ${FID}, display_name: 'Frida'}).then(v => { window.__del = v; }); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal [name="rxhow"]')`, 60), 'the retention step comes first');
    const RXM = `document.querySelector('[name="rxhow"]').closest('.modal')`;
    check(await ev(`!${RXM}.querySelector('[name="rxhow"][value="waived"]') && !!${RXM}.querySelector('[name="rxhow"][value="exported"]')`), 'the admin is offered the export only, no waiver');
    check(await ev(`(() => { const h = ${RXM}.querySelector('[data-rxnowv]'); return !!h && h.offsetParent !== null && /Only the person themself or an admin of the organisation/.test(h.textContent); })()`), 'the step says who can do without the export');
    await shot('p21291-rx-step-admin.png');
    await ev(`(() => { ${RXM}.querySelector('[data-m="close"]').click(); return 1; })()`);
    check(await ready(ev, `window.__del === false`, 40), 'cancel: nothing deleted');

    // after frida's declaration the step offers it
    check(!!(await call(CF, 'POST', '/api/retention/me/waiver')).waived_at, 'frida declares the waiver');
    await ev(`(() => { window.__del = 'pending'; ua8_delete({id: ${FID}, display_name: 'Frida'}).then(v => { window.__del = v; }); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal [name="rxhow"][value="waived"]')`, 60), 'the step offers the declared waiver');
    check(await ev(`/declared on/.test(${RXM}.querySelector('[name="rxhow"][value="waived"]').closest('label').textContent) && !${RXM}.querySelector('[data-rxnowv]')`), 'it names the declaration');
    await ev(`(() => { const i = document.querySelector('[name="rxhow"][value="waived"]'); i.checked = true; i.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()`);
    check(await ev(`!${RXM}.querySelector('[data-m="go"]').disabled`), 'the choice enables "Continue"');
    await ev(`(() => { ${RXM}.querySelector('[data-m="go"]').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.modal [data-cd="yes"]') && !document.querySelector('.modal [name="rxhow"]')`, 60), 'then the usual question');
    await ev(`(() => { document.querySelector('.modal [data-cd="yes"]').click(); return 1; })()`);
    check(await ready(ev, `window.__del === true`, 60), 'deleted with the declared waiver ' + await ev('String(window.__del)'));
    check((await call(CA, 'GET', `/api/users/${FID}/delete-info`)).http === 404, 'frida is gone');
  }, false);

  console.log(`p21291_rxgate_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
