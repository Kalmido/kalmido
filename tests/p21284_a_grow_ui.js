// kalmido-suite: fresh
// 2.1284.0 A (#6597) UI tests, own container (start.sh), Firefox (1280 and 390 px). Invented data only. Played by a person WITHOUT an
// organisation (freelancer-matrix: office). The multi-line fields of the office editor show their whole text without dragging:
// - the subject (project title) of a quotation, invoice and credit note: at least two rows, grows with its text up to ten rows,
//   never higher than its text + one row (a short subject stays two rows, also after typing), as wide as its column, the label
//   "Subject" above it (not centred beside a tall field)
// - the same for the address lines, the rights note, introduction / closing, a text position and the company name of the settings
// - after the first render, after typing (input) and when a closed section opens (the field had no width while hidden)
// 2.1358.0 (#6659): also the address of a client from the directory (shown whole, label above) and the title of a part on the title page
// (a growing field, ofcGrow). Screenshots with P21284A_SHOTS=<dir>.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } return !!c; };
const firefox = require('./ff')({tag: 'p21284_a_grow_ui', check, shots: 'P21284A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'cal,comments,collab,office';
const svc = (title, qty, rate) => ({kind: 'service', title, qty, unit: 'day', rate, tax: 'standard', raw_fee: 0, producing: 0, intext: 'intern', cost: 0, discountable: 1});
const SHORT = 'ARAL CarGeek', LONG60 = 'ARAL CarCash Kampagne 2027 - Imagefilm, Social Cuts und Fotos', THREE = 'Imagefilm\nDreh und Schnitt\nFarbkorrektur',
  MANY = Array.from({length: 14}, (_, i) => 'Zeile ' + (i + 1)).join('\n');

// in the page: the measures of one field (content height in rows, the rows its text needs, visible, width against its row)
const MEASURE = `(sel) => { const t = document.querySelector(sel); if (!t || !t.offsetParent) return null;
  const cs = getComputedStyle(t), pad = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
  const h0 = t.style.height, o0 = t.style.overflow; t.style.height = '1px'; t.style.overflow = 'hidden'; const need = Math.max(1, Math.round((t.scrollHeight - pad) / lh)); t.style.height = h0; t.style.overflow = o0;
  const r = t.getBoundingClientRect(), row = t.closest('.row'), lab = row && row.querySelector('label'), rr = row && row.getBoundingClientRect(), lr = lab && lab.getBoundingClientRect();
  return {rows: (t.clientHeight - pad) / lh, need, fits: t.clientHeight + 1 >= t.scrollHeight, w: r.width, rowW: rr ? rr.width : null, labTop: lr ? lr.top : null, labBottom: lr ? lr.bottom : null, top: r.top,
    lab: lr ? (lr.bottom <= r.top + 1 ? 'above' : Math.abs(lr.top - r.top) <= 6 ? 'top' : 'centred') : null, attr: t.rows, h: t.clientHeight, sh: t.scrollHeight, lh, flex: cs.flex, alignSelf: cs.alignSelf, minH: cs.minHeight, ch: cs.height}; }`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  // freelancer-matrix: office -- a person without an organisation
  const u = await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http === 200 || u.http === 201, 'the freelancer ' + u.http);
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const st = await call(CF, 'PUT', '/api/office/settings', {lang: 'en', currency: 'EUR', company_fields: {name: 'Beispiel Studio', street: 'Musterweg 1', zip: '12345', city: 'Musterstadt',
    country: 'DE', email: 'kontakt@example.com', tax_number: '12/345/67890', vat_id: 'DE999999999', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'}});
  check(st.http === 200, 'office settings ' + st.http);
  const docs = {};
  // a credit note needs a finalised invoice: its draft (POST /credit) gets the subjects by PATCH
  const base = await call(CF, 'POST', '/api/office/docs', {kind: 'invoice', lang: 'en', project_title: 'Basis', recipient: {name: 'Beispielkunde AG', lines: ['Marktplatz 2', '54321 Beispielort']}, service_from: '2026-05-01', items: [svc('Kamera', 1, 500)]});
  const fin = await call(CF, 'POST', `/api/office/docs/${base.id}/finalize`);
  check(fin.http === 200, 'the invoice finalised ' + fin.http + ' ' + (fin.error || ''));
  const credit = async b => { const c = await call(CF, 'POST', `/api/office/docs/${base.id}/credit`, {}); if (c.http !== 201) return c;
    const p = await call(CF, 'PATCH', `/api/office/docs/${c.id}`, b); return {...p, id: c.id, http: p.http === 200 ? 201 : p.http}; };
  for (const kind of ['offer', 'invoice', 'credit']) {
    const post = kind === 'credit' ? credit : b => call(CF, 'POST', '/api/office/docs', {kind, ...b});
    const x = await post({lang: 'en', project_title: SHORT, recipient: {name: 'Beispielkunde AG', lines: ['Marktplatz 2', '54321 Beispielort']},
      intro: 'Hallo,', closing: LONG60, rights: {note: THREE}, service_from: '2026-05-01', items: [svc('Kamera', 1, 500), {kind: 'text', detail: SHORT}]});
    check(x.http === 201, kind + ': a draft ' + x.http + ' ' + (x.error || ''));
    const y = await post({lang: 'en', project_title: LONG60 + '\n' + THREE, recipient: {name: 'Beispielkunde AG', lines: ['Marktplatz 2']}, service_from: '2026-05-01', items: [svc('Kamera', 1, 500)]});
    check(y.http === 201, kind + ': a draft with a long subject ' + y.http);
    docs[kind] = [x.id, y.id];
  }
  // 2.1358.0 (#6659): an offer with a client from the directory (read-only address block) and a part on its title page with a long title
  const PLONG = LONG60 + ' ' + LONG60;
  // a second person (also without an organisation) with the clients module: with it every document shows the directory's address block
  check((await call(CA, 'POST', '/api/users', {username: 'greta', display_name: 'Greta', password: 'password123', email: 'greta@example.com', orgs: []})).http < 300, 'the person with clients');
  const CG = await login('greta');
  await call(CG, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT + ',clients'});
  await call(CG, 'PUT', '/api/office/settings', {lang: 'en', currency: 'EUR', company_fields: {name: 'Beispiel Atelier', street: 'Musterweg 2', zip: '12345', city: 'Musterstadt',
    country: 'DE', email: 'atelier@example.com', tax_number: '12/345/67891', vat_id: 'DE999999998', iban: 'DE02120300000000202051', bic: 'BYLADEM1001', bank_name: 'Beispielbank'}});
  const cl = await call(CG, 'POST', '/api/clients', {name: 'Beispielkunde AG', street: 'Marktplatz 2', zip: '54321', city: 'Beispielort', country: 'DE'});
  check(cl.http === 200 || cl.http === 201, 'a client ' + cl.http);
  const po = await call(CG, 'POST', '/api/office/docs', {kind: 'offer', lang: 'en', project_title: 'Teile', client_id: cl.id, items: [svc('Kamera', 1, 500)]});
  check(po.http === 201, 'an offer with a client ' + po.http);
  const pp = await call(CG, 'POST', `/api/office/docs/${po.id}/parts`, {title: PLONG});
  check(pp.http === 201 || pp.http === 200, 'a part ' + pp.http);
  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const blank = async (nav, ev) => { await nav(B + 'static/icon.svg'); await ready(ev, `location.pathname === '/static/icon.svg' && document.readyState === 'complete'`, 40); };
  const signIn = (ev, who) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    const m = sel => ev(`(${MEASURE})(${JSON.stringify(sel)})`);
    // one field judged: whole text visible up to `max` rows, at least `min` rows, never more than text + 1 row; o.full: the
    // column's width with the label above or top-aligned
    const judge = async (tag, sel, min, max, o = {}) => {
      const x = await m(sel);
      if (process.env.P21284A_SHOTS) require('fs').appendFileSync(path.join(process.env.P21284A_SHOTS, 'p21284-a-measures.txt'), tag + sel + ' ' + JSON.stringify(x) + '\n');
      if (!check(x, tag + sel + ' is shown')) return null;
      const want = Math.min(max, Math.max(min, x.need)), info = ' ' + JSON.stringify(x);
      check(x.need > max || x.fits, tag + sel + ': the whole text is visible (no inner scrolling up to ' + max + ' rows)' + info);
      check(x.rows >= Math.min(want, max) - 0.15, tag + sel + ': at least ' + want + ' rows high' + info);
      check(x.rows <= want + 1.05, tag + sel + ': never higher than its text + one row (' + want + ')' + info);
      if (o.exact) check(Math.abs(x.rows - want) < 0.2, tag + sel + ': exactly ' + want + ' rows' + info);
      if (o.full) {
        check(x.rowW && x.w >= x.rowW - 2, tag + sel + ': the field takes the column width' + info);
        check(x.lab === 'above' || x.lab === 'top', tag + sel + ': the label sits above / at the top, not centred beside it' + info);
      }
      return x;
    };
    const type = (sel, v) => ev(`(() => { const t = document.querySelector(${JSON.stringify(sel)}); t.focus(); t.value = ${JSON.stringify(v)}; t.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    const hash = kind => kind === 'offer' ? 'offers' : 'invoices';
    for (const [w, h] of [[1280, 900], [1920, 1080], [390, 844]]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
      await blank(nav, ev);
      await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
      await signIn(ev, 'frida');
      for (const kind of ['offer', 'invoice', 'credit']) {
        const tag = `${kind} ${w}px: `, S = '#ofd-project_title';
        // ---- the long subject as drawn (60 characters + three lines: wraps, fits without dragging)
        await nav(B + `#office/${hash(kind)}/${docs[kind][1]}`);
        check(await ready(ev, `!!document.querySelector('${S}') && !!document.querySelector('${S}').offsetParent`, 80), tag + 'the editor (long subject)');
        await judge(tag + 'drawn long: ', S, 2, 10, {full: true});
        await shot(`p21284-a-long-${kind}-${w}.png`);
        // ---- the short subject as drawn: two rows, not squeezed
        await nav(B + `#office/${hash(kind)}/${docs[kind][0]}`);
        check(await ready(ev, `!!document.querySelector('${S}') && !!document.querySelector('${S}').offsetParent && document.querySelector('${S}').value === ${JSON.stringify(SHORT)}`, 80), tag + 'the editor (short subject)');
        await judge(tag + 'drawn short: ', S, 2, 10, {full: true, exact: true});
        await shot(`p21284-a-short-${kind}-${w}.png`);
        // ---- typing: empty, short (2 rows, not 10), 60 characters, three lines, more than ten lines (10 rows, the rest scrolls)
        for (const [name, v] of [['empty', ''], ['short', SHORT], ['60 characters', LONG60], ['three lines', THREE], ['14 lines', MANY], ['short again', SHORT]]) {
          await type(S, v);
          await judge(tag + 'typed ' + name + ': ', S, 2, 10, {full: true, exact: true});
        }
        // ---- the other multi-line fields of the document
        if (await ev(`!!document.querySelector('#ofd-recipient_lines')`)) await judge(tag, '#ofd-recipient_lines', 3, 10, {full: true});
        if (kind === 'offer') {
          await judge(tag + 'rights note drawn: ', '#ofd-r-note', 2, 10, {full: true, exact: true});
          await type('#ofd-r-note', SHORT);
          await judge(tag + 'rights note typed short: ', '#ofd-r-note', 2, 10, {full: true, exact: true});
        }
        const tx = '.ofdtx textarea';  // the credit note copies its invoice's positions (no text position there)
        if (kind !== 'credit') { await judge(tag + 'text position drawn: ', tx, 2, 10, {exact: true});
        await type(tx, LONG60 + ' ' + LONG60 + '\n' + THREE);
        await judge(tag + 'text position typed long: ', tx, 2, 10, {exact: true}); }
        // introduction / closing sit in a closed section: measured once it opens (they had no width while hidden)
        await ev(`(() => { const s = document.querySelector('details.ofdsec[data-sec="texts"]'); if (s && !s.open) s.querySelector('summary').click(); return 1; })()`);
        check(await ready(ev, `!!document.querySelector('#ofd-closing') && !!document.querySelector('#ofd-closing').offsetParent`, 40), tag + 'the texts section opens');
        await sleep(0);
        await ready(ev, `(() => { const t = document.querySelector('#ofd-closing'); return t && t.clientHeight + 1 >= t.scrollHeight; })()`, 10);
        await judge(tag + 'intro drawn: ', '#ofd-intro', 3, 10, {exact: true});
        await judge(tag + 'closing drawn: ', '#ofd-closing', 3, 10, {exact: true});
        await type('#ofd-intro', MANY);
        await judge(tag + 'intro typed 14 lines: ', '#ofd-intro', 3, 10, {exact: true});
        await shot(`p21284-a-fields-${kind}-${w}.png`);
      }
      // ---- the company name in the office settings (up to three rows)
      await nav(B + '#office/settings');
      check(await ready(ev, `!!document.getElementById('os-name') && !!document.getElementById('os-name').offsetParent`, 80), `settings ${w}px: the company name`);
      await type('#os-name', 'Beispiel Studio für Film, Foto und Bewegtbild GmbH & Co. KG');
      await judge(`settings ${w}px: company name typed: `, '#os-name', 1, 3, {exact: true});
      await type('#os-name', 'Beispiel');
      await judge(`settings ${w}px: company name short: `, '#os-name', 1, 3, {exact: true});
      // ---- 2.1358.0 (#6659): the address of a client from the directory and the title of a part on the title page
      await blank(nav, ev); await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`); await signIn(ev, 'greta');
      await nav(B + `#office/offers/${po.id}`);
      check(await ready(ev, `!!document.querySelector('.ofdeditor .tppl [data-k="title"]') && !!document.querySelector('.cdnadr')`, 80), `${w}px: the offer with a part and a client`);
      const adr = await ev(`(() => { const a = document.querySelector('.cdnadr'), row = a.closest('.row'), lab = row.querySelector('label'), ar = a.getBoundingClientRect(), lr = lab.getBoundingClientRect();
        return {fits: a.clientHeight + 1 >= a.scrollHeight, text: a.textContent, wide: a.getBoundingClientRect().right <= row.getBoundingClientRect().right + 1, lab: lr.bottom <= ar.top + 1 ? 'above' : Math.abs(lr.top - ar.top) <= 6 ? 'top' : 'centred'}; })()`);
      check(adr && adr.fits && /Marktplatz 2.*54321 Beispielort/.test(adr.text) && adr.wide, `${w}px: the address of the client is shown whole ` + JSON.stringify(adr));
      check(adr && (adr.lab === 'above' || adr.lab === 'top'), `${w}px: its label sits above / at the top ` + JSON.stringify(adr));
      const PT = '.ofdeditor .tppl textarea[data-k="title"]';
      await judge(`part title ${w}px drawn: `, PT, 1, 10);
      await type(PT, PLONG);  // the line's own title (the part's name is only its placeholder)
      await judge(`part title ${w}px typed long: `, PT, 1, 10, {exact: true});
      check(await ev(`document.querySelector(${JSON.stringify(PT)}).value === ${JSON.stringify(PLONG)}`), `${w}px: the part title is whole in the field`);
      await type('.ofdeditor .tppl textarea[data-k="title"]', THREE + '\n' + THREE);
      const pt = await judge(`part title ${w}px typed six lines: `, '.ofdeditor .tppl textarea[data-k="title"]', 1, 10, {exact: true});
      check(pt && pt.rows >= 5.8, `${w}px: the part title grows with its lines ` + JSON.stringify(pt));
      await type('.ofdeditor .tppl textarea[data-k="title"]', 'Teil');
      await judge(`part title ${w}px short: `, '.ofdeditor .tppl textarea[data-k="title"]', 1, 10, {exact: true});
      await shot(`p21284-a-part-${w}.png`);
      await blank(nav, ev); await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`); await signIn(ev, 'frida');
    }
  });
  console.log(F.length ? `FAILED ${F.length}:\n` + F.join('\n') : `p21284_a_grow_ui: ${ok} checks passed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
