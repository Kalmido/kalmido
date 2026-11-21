// #7306 UI test: in the bank view "Without receipt" the column of the open receipts gets wider by the one grip (grip.js,
// docs/dev/kern.md "Resizing: the one grip").
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1280 x 900 (mouse, real pointer input), a person WITHOUT an organisation (the own personal
// office; freelancer-matrix: office), invented names and figures only. Usability:
// - a booking and an open receipt: between the bookings and the receipts sits a grip (separator, focusable, data-grip
//   bank-norc); the receipts' column is 18rem
// - dragging it to the left makes the column wider live, released it is kept on the device (grip:bank-norc); dragged far it
//   stops where the bookings keep 18rem (no fixed cap); a redraw of the office keeps width and grip
// - a reload: the same width; a double click: 18rem again, nothing stored
// - the receipt dropped onto the booking (the drag of a receipt) still matches it
// - phone width: no receipts' column, no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const TC = require('./testclock');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7306_bank_grip_ui', check, shots: 'P7306_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const day = n => { const x = new Date(TC.today() + 'T12:00:00'); x.setDate(x.getDate() - n); return x.toISOString().slice(0, 10); };
const ntry = (amt, ref, dd, name) => `<Ntry><Amt Ccy="EUR">${amt}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>${dd}</Dt></BookgDt><AcctSvcrRef>${ref}</AcctSvcrRef><NtryDtls><TxDtls><RltdPties><Cdtr><Pty><Nm>${name}</Nm></Pty></Cdtr></RltdPties><RmtInf><Ustrd>Buchung ${ref}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>`;

const M = `JSON.stringify((() => {
  const w = s => Math.round(document.querySelector(s)?.getBoundingClientRect().width || 0);
  const g = document.querySelector('.bnrcols > .bnrgrip'), r = g?.getBoundingClientRect();
  return {rc: w('.bnrcols > .bnrrc'), list: w('.bnrcols > div:first-child'), cols: w('.bnrcols'), grip: !!g && g.classList.contains('grip'), role: g?.getAttribute('role'), key: g?.dataset.grip,
    ti: g ? g.tabIndex : null, gx: r ? r.left + r.width / 2 : 0, gy: r ? r.top + Math.min(r.height / 2, 40) : 0, gw: r ? Math.round(r.width) : 0,
    v: document.querySelector('.bnrcols')?.style.getPropertyValue('--g-bank-norc') || '', root: document.documentElement.style.getPropertyValue('--g-bank-norc'),
    ls: localStorage.getItem('tasks.grip:bank-norc'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'POST', '/api/users', {orgs: [], username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,office,clients,docs', workspace: 'private'});
  await call(CF, 'PUT', '/api/office/settings', {company_fields: {name: 'Frida Film', street: 'Weg 3', zip: '10115', city: 'Berlin', country: 'DE'}});
  const xml = `<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><Stmt><Acct><Id><IBAN>DE02120300000000202051</IBAN></Id><Ccy>EUR</Ccy></Acct>${ntry('119.00', 'U-1', day(3), 'Software Beispiel GmbH')}${ntry('42.00', 'U-2', day(5), 'Druckerei Muster')}</Stmt></BkToCstmrStmt></Document>`;
  const imp = await call(CF, 'POST', '/api/office/bank/import', {text: xml, filename: 'konto.xml'});
  check(imp.http === 201, 'setup: two bookings imported ' + imp.http);
  const TX = ((await call(CF, 'GET', '/api/office/bank/tx?state=all')).items || []).find(t => t.purpose === 'Buchung U-1')?.id;
  const fd = new FormData(); fd.append('ws', 'private'); fd.append('files', new Blob(['Beleg Software Beispiel 119,00'], {type: 'text/plain'}), 'beleg-software-beispiel-jahreslizenz-langer-name.txt');
  const up = await (await fetch(B + 'api/docs', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CF}, body: fd})).json().catch(() => ({}));
  const RC = (up.ids || [])[0];
  check(TX && RC && (await call(CF, 'PATCH', `/api/docs/${RC}`, {amount: '119.00', date: day(3)})).http === 200 && (await call(CF, 'PUT', `/api/docs/${RC}/receipt`, {keep: true})).http === 200, 'setup: a receipt of 119.00 without a booking');
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);

  await firefox(async o => {
    const {cmd, ev, nav, ctx, shot, until, idle} = o;
    const get = async () => JSON.parse(await ev(M));
    const open = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      await nav(B + 'static/icon.svg');  // a real new load of the app
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#office/bank/norc'); await idle();
      check(await until(`document.querySelectorAll('.bnklist .bnkrow').length >= 1`, {timeout: 20000}), `${W}: the bookings without a receipt`);
    };
    const drag = async (x0, y0, dx, look) => {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0), duration: 100}]}]});
      await sleep(80);  // the last move lands in the next frame (rafThrottle)
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await sleep(60);
      return mid;
    };

    await open(1280, true);
    check(await until(`!!document.querySelector('.bnrcols > .bnrgrip.grip') && !!document.querySelector('.bnrrc [data-bnr-rc]')`, {timeout: 8000}), 'the grip and the open receipt are there');
    const g0 = await get();
    check(g0.role === 'separator' && g0.key === 'bank-norc' && g0.ti === 0 && g0.gw >= 8, 'the grip: a focusable separator named bank-norc ' + JSON.stringify(g0));
    check(Math.abs(g0.rc - 18 * g0.rem) <= 2 && g0.ls == null, 'nothing stored: the receipts\' column is 18rem ' + JSON.stringify(g0));
    check(await ev(`(() => { const e = document.elementFromPoint(${g0.gx}, ${g0.gy}); return !!e && e.classList.contains('bnrgrip'); })()`), 'the pointer reaches the grip');
    const mid = await drag(g0.gx, g0.gy, -128, `JSON.stringify({rc: Math.round(document.querySelector('.bnrrc').getBoundingClientRect().width), ls: localStorage.getItem('tasks.grip:bank-norc')})`);
    const m = JSON.parse(mid || '{}');
    check(Math.abs(m.rc - (g0.rc + 128)) <= 3 && m.ls == null, 'during the drag the column follows live, nothing stored yet ' + mid);
    const g1 = await get();
    check(Math.abs(g1.rc - (g0.rc + 128)) <= 3 && g1.ls === '26' && g1.v === '26rem' && !g1.root && g1.list > 200, 'released: 8rem wider (26rem), kept under grip:bank-norc on the columns, not the root ' + JSON.stringify(g1));
    await shot('p7306-wide.png');
    // a redraw of the office keeps width and grip
    await ev(`(ofcDraw(), 1)`); await idle();
    const g2 = await get();
    check(g2.grip && g2.role === 'separator' && Math.abs(g2.rc - g1.rc) <= 1, 'a redraw keeps the width and the grip ' + JSON.stringify(g2));
    // dragged far: no fixed cap (product rule "Handles", #4829) - it stops where the bookings keep their 18rem
    await drag(g2.gx, g2.gy, -(g2.gx - 20));
    const g3 = await get();
    const far = Math.floor(g3.cols / g3.rem - 1 - 18) * g3.rem;
    check(Math.abs(g3.rc - far) <= g3.rem + 2 && g3.rc > g3.cols / 2 && g3.list >= 18 * g3.rem - 2, 'dragged far: the column goes past half and stops where the bookings keep 18rem ' + JSON.stringify(g3));
    await ev(`(localStorage.setItem('tasks.grip:bank-norc', '24'), 1)`);
    // a reload: the same width
    await open(1280, false);
    check(await until(`!!document.querySelector('.bnrcols > .bnrgrip.grip')`, {timeout: 8000}), 'reload: the grip again');
    const g4 = await get();
    check(Math.abs(g4.rc - 24 * g4.rem) <= 2, 'reload: the kept width (24rem) ' + JSON.stringify(g4));
    // the receipt dropped onto the booking still matches it
    await ev(`(() => { const r = document.querySelector('.bnrrc [data-bnr-rc="${RC}"]'), row = document.querySelector('[data-bnr-drop="${TX}"]'), dt = new DataTransfer();
      r.dispatchEvent(new DragEvent('dragstart', {bubbles: true, cancelable: true, dataTransfer: dt}));
      row.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}));
      row.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); return 1; })()`);
    check(await until(`document.querySelectorAll('.bnklist .bnkrow').length === 1`, {timeout: 8000}), 'the receipt dropped onto the booking matches it (the row goes)');
    let mt = {};  // #7497: the row goes at once, the match is saved behind it
    for (let i = 0; i < 60 && !(mt.items || []).some(t => t.id === TX); i++) { mt = await call(CF, 'GET', '/api/office/bank/tx?state=matched'); if (!(mt.items || []).some(t => t.id === TX)) await new Promise(r => setTimeout(r, 250)); }
    check((mt.items || []).some(t => t.id === TX && t.match?.kind === 'receipt'), 'the booking is matched with the receipt');
    // a double click: 18rem again, nothing stored (the column stays while a booking is open: the receipts are gone, the grip too)
    const g5 = await get();
    if (g5.grip) {
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(g5.gx), y: Math.round(g5.gy)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}, {type: 'pause', duration: 80}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      check(await until(`localStorage.getItem('tasks.grip:bank-norc') === null && Math.abs(document.querySelector('.bnrrc').getBoundingClientRect().width - 18 * ${g5.rem}) <= 2`, {timeout: 3000}),
        'a double click: 18rem again, nothing stored ' + JSON.stringify(await get()));
    } else check(false, 'the grip stays while a booking is left ' + JSON.stringify(g5));
    // phone width: no column, no grip
    await open(390, false);
    const g6 = await get();
    check(!g6.grip && !g6.rc, 'phone: no receipts\' column, no grip ' + JSON.stringify(g6));
  });

  console.log(`p7306_bank_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
