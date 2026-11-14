// 2.1180.0 C (#6147) UI test: the bank page on a phone and the walk-through with one main step.
// kalmido-suite: fresh
// freelancer-matrix: office (Frida, a person without an organisation: the whole test runs in her own office)
// Own container (start.sh, mode workspaces), Firefox phone 360x740 + desktop 1280x900. Invented companies, people, figures only.
// - phone: the bar is ONE row (Import + "More"), the filters below, no "Fetch from bank" while it is not set up, the first
//   booking clearly higher (measured); "Receipt missing?" folds with one tap and stays folded after leaving the page;
//   "More" holds Go through / Imports / Bank accounts and they work; an invoice suggestion is a compact card (no empty preview)
// - desktop: Go through / Imports in the bar; the walk-through: a booking without a suggestion has "Search another receipt" as
//   its one main step, "More" with upload + the marks, the key hint names only arrows, the dialog is no two-thirds-empty box;
//   with a suggestion "Take over" is the main step and the hint names Enter (no "1-3" without numbers); the end view is the
//   shared empty state with its icon
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const TC = require('./testclock');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21180_c_bank_ui', check, shots: 'P21180C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,office,clients,docs';
const day = n => { const d = new Date(TC.today() + 'T12:00:00'); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
const de = iso => `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'de'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments']});
  // ---- Frida without an organisation, her own office: one invoice, three bookings (money in for the invoice, two out without receipt)
  const fu = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fu.http < 300, 'a person without organisation ' + fu.http);
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEAT});
  check(((await call(CF, 'GET', '/api/state')).me?.workspaces || []).length === 0, 'frida is in no organisation');
  const co = await call(CF, 'PUT', '/api/office/settings', {company_fields: {name: 'Frida Beispiel', street: 'Musterweg 1', zip: '12345', city: 'Musterstadt', country: 'DE', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'}});
  check(co.http === 200, 'her office has its company data ' + co.http);
  const cl = await call(CF, 'POST', '/api/clients', {name: 'Kunde Eins GmbH', street: 'Weg 2', zip: '10115', city: 'Berlin', country: 'DE'});
  const inv = await call(CF, 'POST', '/api/office/docs', {kind: 'invoice', client_id: cl.id, service_from: day(20), items: [{title: 'Schnitt', qty: 1, rate: 1000}]});
  const fin = await call(CF, 'POST', `/api/office/docs/${inv.id}/finalize`);
  check(fin.http === 200 && fin.number, 'a finalised invoice ' + fin.http);
  const csv = `Buchungstag;Auftraggeber/Empfänger;Verwendungszweck;Betrag\n${de(day(3))};Kunde Eins GmbH;Rechnung ${fin.number};1.190,00\n${de(day(2))};Bäckerei Beispiel;Brötchen;-4,50\n${de(day(1))};Kontoführung Beispiel;Gebühr;-12,90\n`;
  const pv = await call(CF, 'POST', '/api/office/bank/import/preview', {text: csv});
  const mapping = {}; for (const k of ['date', 'amount', 'amount_in', 'amount_out', 'title', 'counterpart', 'decimal', 'date_format']) mapping[k] = pv.guess?.[k] ?? null;
  const imp = await call(CF, 'POST', '/api/office/bank/import', {text: csv, filename: 'konto.csv', mapping});
  check(imp.http === 201 && imp.count === 3, 'three bookings imported ' + imp.http);
  const openTx = async () => ((await call(CF, 'GET', '/api/office/bank/tx?state=open')).items || []).length;

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const click = sel => `(() => { const e = ${sel}; if (!e) return 0; e.click(); return 1; })()`;
  const shown = sel => `(() => { const e = ${sel}; return !!e && e.getClientRects().length > 0; })()`;
  const row = p => `[...document.querySelectorAll('.bnklist .bnkrow')].find(e => /${p}/.test(e.textContent))`;
  const firstTop = `Math.round(document.querySelector('.bnklist .bnkrow')?.getBoundingClientRect().top ?? 9999)`;
  const popActs = `[...document.querySelectorAll('#pop:not(.hidden) [role="menuitem"]')].map(b => b.dataset.act).join(',')`;
  const W = `document.querySelector('.wlkdlg')`;
  const head = `(${W}?.querySelector('.wlk-tx b')?.textContent || '')`;
  const acts = `[...${W}.querySelectorAll('.wlk-acts button')].map(b => b.dataset.wlk).join(',')`;
  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    // ---- phone 360 x 740
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);
    await nav(B + '#office/bank');
    check(await ready(ev, `document.querySelectorAll('.bnklist .bnkrow').length === 3 && /Kein Bankzugriff/.test(document.querySelector('#view')?.textContent || '')`, 100), 'phone: the bank page with three open bookings');
    const bar = await ev(`(() => { const i = document.querySelector('.bnkbar [data-bnk="imp"]').getBoundingClientRect(), m = document.querySelector('.bnkbar [data-bnk="menu"]').getBoundingClientRect(), s = document.querySelector('.bnkbar .seg').getBoundingClientRect();
      return {same: Math.abs(i.top - m.top) < 2, h: Math.round(i.height), inside: m.right <= document.documentElement.clientWidth + 1, segBelow: s.top >= i.bottom - 1}; })()`);
    check(bar.same && bar.inside && bar.segBelow && bar.h >= 40, 'phone: "Kontoauszug importieren" and "Mehr" in ONE row, the filters below ' + JSON.stringify(bar));
    check(await ev(`!${shown(`document.querySelector('.bnkbar [data-bnk="walk"]')`)} && !${shown(`document.querySelector('.bnkbar [data-bnk="imps"]')`)} && !${shown(`document.querySelector('.ofcsetl')`)}`), 'phone: Durchgehen, Importe and the bank accounts line are not in the head');
    check(await ev(`!document.querySelector('[data-bnk="fints"]') && !document.querySelector('#bnk-fnt-off')`), 'phone: no "Von der Bank abrufen" while the fetch is not set up');
    const top1 = await ev(firstTop);
    check(top1 <= 420, `phone: the first booking starts at ${top1} px of 740 (was ~570)`);
    // "Beleg fehlt?" folds and stays folded
    check(await ev(`(() => { const d = document.querySelector('details.bnkmiss1'); return !!d && d.open && /Beleg fehlt\\?/.test(d.querySelector('summary').textContent); })()`), 'phone: the hint "Beleg fehlt?" is open the first time');
    await shot('p21180c-phone-bank.png');
    await ev(click(`document.querySelector('details.bnkmiss1 summary')`));
    check(await ready(ev, `!document.querySelector('details.bnkmiss1').open && localStorage.getItem('tasks.bnkMissShut') === 'true'`), 'phone: one tap folds the hint (remembered)');
    const top2 = await ev(firstTop);
    check(top2 < top1, `phone: folded, the first booking moves up (${top1} -> ${top2})`);
    await nav(B + '#office/receipts');
    await ready(ev, `!document.querySelector('.bnkbar')`, 40);
    await nav(B + '#office/bank');
    check(await ready(ev, `document.querySelectorAll('.bnklist .bnkrow').length === 3 && !!document.querySelector('details.bnkmiss1') && !document.querySelector('details.bnkmiss1').open`, 80), 'phone: back on the page the hint stays folded');
    // the compact card of an invoice suggestion (no picture)
    const cardH = await ev(`(() => { const c = ${row('Kunde Eins')}?.querySelector('.bnksug .ocd'); return c && !c.querySelector('.ocd-pv') && c.classList.contains('ocd-flat') && /Übernehmen/.test(c.textContent) ? Math.round(c.getBoundingClientRect().height) : -1; })()`);
    check(cardH > 0 && cardH < 150, `phone: the invoice suggestion is a compact card without an empty preview (${cardH} px)`);
    // "Mehr": Durchgehen, Importe, Bankkonten
    await ev(click(`document.querySelector('.bnkbar [data-bnk="menu"]')`));
    check(await ready(ev, `${popActs} === 'bnk-walk,bnk-imps,bnk-accts'`), 'phone: "Mehr" holds Durchgehen, Importe, Bankkonten ' + await ev(popActs));
    await shot('p21180c-phone-more.png');
    await ev(click(`document.querySelector('#pop [data-act="bnk-imps"]')`));
    check(await ready(ev, `document.querySelectorAll('.bnkimps .ofcrow').length === 1 && /konto\\.csv/.test(document.querySelector('.bnkimps').textContent)`), 'phone: "Importe" from "Mehr" shows the import');
    await ev(click(`document.querySelector('.bnkbar [data-bnk="menu"]')`));
    check(await ready(ev, `!!document.querySelector('#pop:not(.hidden) [data-act="bnk-walk"]')`), 'phone: "Mehr" again');
    await ev(click(`document.querySelector('#pop [data-act="bnk-walk"]')`));
    check(await ready(ev, `/1 von 3/.test(${W}?.querySelector('[data-wlk-n]')?.textContent || '')`), 'phone: "Durchgehen" from "Mehr" opens the walk-through');
    check(await ev(`document.documentElement.scrollWidth <= innerWidth + 1 && ${W}.querySelector('.card').scrollWidth <= ${W}.querySelector('.card').clientWidth + 1`), 'phone: the walk-through without sideways scroll');
    await ev(click(`${W}.querySelector('[data-wlk="close"]')`));
    await ready(ev, `!${W}`, 20);

    // ---- desktop
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    check(await ready(ev, `${shown(`document.querySelector('.bnkbar [data-bnk="walk"]')`)} && ${shown(`document.querySelector('.bnkbar [data-bnk="imps"]')`)} && !${shown(`document.querySelector('.bnkbar [data-bnk="menu"]')`)} && ${shown(`document.querySelector('.ofcsetl')`)}`),
      'desktop: Durchgehen, Importe and the bank accounts line in the head, no "Mehr"');
    await ev(click(`document.querySelector('.bnkbar [data-bnk="walk"]')`));
    check(await ready(ev, `/1 von 3/.test(${W}?.querySelector('[data-wlk-n]')?.textContent || '')`), 'desktop: the walk-through "1 von 3"');
    // to a booking without a suggestion
    for (let i = 0; i < 3 && !/Bäckerei/.test(await ev(head)); i++) { await ev(click(`${W}.querySelector('[data-wlk="skip"]')`)); await ready(ev, `!!${W}.querySelector('.wlk-acts')`, 20); }
    check(await ready(ev, `/Bäckerei/.test(${head}) && !!${W}.querySelector('.wlk-none')`), 'desktop: the booking without a suggestion');
    check(await ev(`${acts} === 'search,more' && ${W}.querySelector('[data-wlk="search"]').classList.contains('pri') && !${W}.querySelector('.wlk-foot [data-wlk="take"]')`), 'desktop: "Anderen Beleg suchen" is the one main step, the rest under "Mehr" ' + await ev(acts));
    const keys = await ev(`${W}.querySelector('.wlk-keys')?.textContent || ''`);
    check(/Pfeile/.test(keys) && !/\d/.test(keys) && !/Enter/.test(keys), `desktop: the key hint names only what works (${keys})`);
    const dh = await ev(`Math.round(${W}.querySelector('.card').getBoundingClientRect().height)`);
    check(dh < 450, `desktop: the dialog is as tall as its content (${dh} px, was at least 576)`);
    await shot('p21180c-walk-none.png');
    await ev(click(`${W}.querySelector('[data-wlk="more"]')`));
    check(await ready(ev, `${popActs} === 'wlk-up,wlk-private,wlk-noreceipt,wlk-ignored,wlk-cash'`), 'desktop: "Mehr" holds upload and the four marks ' + await ev(popActs));
    check(await ev(`[...document.querySelectorAll('#pop [role="menuitem"] .msub')].length >= 4`), 'desktop: each mark with its line of explanation');
    await shot('p21180c-walk-more.png');
    await ev(click(`document.querySelector('#pop [data-act="wlk-private"]')`));
    check(await ready(ev, `!/Bäckerei/.test(${head})`), 'desktop: "Privat" from "Mehr" goes on to the next booking');
    check(await openTx() === 2, 'the server: one booking marked');
    // the booking with its invoice
    for (let i = 0; i < 3 && !/Kunde Eins/.test(await ev(head)); i++) { await ev(click(`${W}.querySelector('[data-wlk="skip"]')`)); await ready(ev, `!!${W}.querySelector('.wlk-acts')`, 20); }
    check(await ready(ev, `/Kunde Eins/.test(${head}) && !!${W}.querySelector('.wlk-cands .ocd.ocd-flat')`), 'desktop: the booking with its invoice as compact card');
    check(await ev(`!${W}.querySelector('[data-wlk="search"]').classList.contains('pri') && ${W}.querySelector('.wlk-foot [data-wlk="take"]').classList.contains('pri')`), 'desktop: with a suggestion "Übernehmen" is the main step');
    const keys2 = await ev(`${W}.querySelector('.wlk-keys')?.textContent || ''`);
    check(/Enter/.test(keys2) && !/1-3/.test(keys2) && /1/.test(await ev(`${W}.querySelector('.ocd-key')?.textContent || ''`)), `desktop: one card: the hint names Enter, no "1-3" (${keys2})`);
    await ev(click(`${W}.querySelector('[data-wlk="more"]')`));
    check(await ready(ev, `${popActs} === 'wlk-private,wlk-noreceipt,wlk-ignored,wlk-cash,wlk-split'`), 'desktop: money in: no upload, "Auf Rechnungen aufteilen" in "Mehr" ' + await ev(popActs));
    await ev(`(() => { closePop(); return 1; })()`);
    await ev(click(`${W}.querySelector('.wlk-foot [data-wlk="take"]')`));
    check(await ready(ev, `/Kontoführung/.test(${head})`), 'desktop: "Übernehmen" goes on');
    await ev(click(`${W}.querySelector('[data-wlk="more"]')`));
    await ready(ev, `!!document.querySelector('#pop:not(.hidden) [data-act="wlk-noreceipt"]')`);
    await ev(click(`document.querySelector('#pop [data-act="wlk-noreceipt"]')`));
    check(await ready(ev, `(() => { const e = ${W}?.querySelector('.wlk-end'); return !!e && e.classList.contains('empty') && !!e.querySelector('svg') && /Jede Buchung ist erledigt/.test(e.textContent); })()`), 'desktop: the end view is the shared empty state with its icon');
    check(await openTx() === 0, 'the server: no open booking left');
    await shot('p21180c-walk-end.png');
  }, false);

  console.log(`p21180_c_bank_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
