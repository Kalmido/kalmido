// 2.1175.0 part C UI test (#6146): a quotation position shows text, quantity, unit, price, VAT and sum; the calculation waits
// kalmido-suite: fresh
// behind a "Kalkulation" button per row. Own container (start.sh; KMT_NOSTART=1: a running server), jsdom for the editor,
// Firefox for the layout (phone 390 px touch, computer 1280 px mouse). German UI, invented services and amounts only.
// freelancer-matrix: office of a person without an organisation (frida) and of an organisation (alice in Alpha)
// - closed: discount %, the ticks (raw data, producing, handling costs, markup, discountable), purchase and the kind of the
//   position are in no visible place; the button says "Kalkulation" and shows a number only where a value differs (purchase)
// - opened: the words "Aufschlag" and "rabattfähig" (no "Markup", no second "Rabatt"); a discount of 10 % on "Regie" saves,
//   the row keeps the calculation open after the redraw and shows 1.800,00; opening / closing changes no amount
// - phone: the closed position is short, the button and the discount button are 44 px high; computer: an optional
//   position's title starts where a normal one's does
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21175_c_angebot_ui', check, shots: 'P21175C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {...(await r.json().catch(() => ({}))), http: r.status}; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const change = (w, el, v) => { if (!el) return; if (v !== undefined) el.value = v; el.dispatchEvent(new w.Event('change', {bubbles: true})); };
const FEATURES = 'cal,collab,comments,contacts,files,clients,office';
const svc = (title, qty, rate, cost = 0, opt = '') => ({kind: 'service', title, qty, unit: 'day', rate, tax: 'standard', raw_fee: 0, producing: 0, in_handling: 1, in_markup: 1, intext: 'intern', cost, discountable: 1, ...(opt ? {opt} : {})});
const CALC_KEYS = ['discount_pct', 'raw_fee', 'producing', 'in_handling', 'in_markup', 'discountable', 'cost', 'opt'];

async function quotation(ck) {
  await call(ck, 'PUT', '/api/office/settings', {lang: 'de', currency: 'EUR', industry_packs: ['film']});
  const doc = await call(ck, 'POST', '/api/office/docs', {kind: 'offer', lang: 'de', project_title: 'Kampagne', raw_mode: 'none', producing_on: 0});
  const j = await call(ck, 'PUT', `/api/office/docs/${doc.id}/items`, {items: [svc('Regie', 2, 1000), svc('Schnitt', 3, 650, 300), svc('Drohne', 1, 400, 0, 'optional')]});
  return {id: doc.id, http: doc.http, items: j.http, totals: j.totals};
}

async function editor(user, ck, tag) {
  const q = await quotation(ck);
  check(q.http === 201 && q.items === 200, `${tag}: a quotation with three positions ${q.http}/${q.items}`);
  const get = () => call(ck, 'GET', `/api/office/docs/${q.id}`);
  const w = await boot({user, hash: `office/offers/${q.id}`}), d = w.document;
  const row = t => [...d.querySelectorAll('.ofdeditor .ofdits .ofdit')].find(li => li.querySelector('[data-k="title"]')?.value === t);
  await until(() => row('Regie') && row('Schnitt'));
  const shown = el => !!el && !el.closest('[hidden]');
  for (const t of ['Regie', 'Schnitt']) {
    const r = row(t);
    check(['title', 'detail', 'qty', 'unit', 'rate', 'tax'].every(k => shown(r?.querySelector(`[data-k="${k}"]`))) && shown(r?.querySelector('.ofdlt')),
      `${tag}: ${t}: text, quantity, unit, price, VAT and sum are open`);
    const open = CALC_KEYS.filter(k => shown(r?.querySelector(`[data-k="${k}"]`)));
    check(!open.length && !shown(r?.querySelector('[data-ofd="it-pdisc"]')) && !shown(r?.querySelector('.ofdmargin')), `${tag}: ${t}: the calculation is closed (open: ${open.join(',')})`);
    const b = r?.querySelector('[data-ofd="it-kalk"]');
    check(b && /Kalkulation/.test(b.textContent) && b.getAttribute('aria-expanded') === 'false', `${tag}: ${t}: the button "Kalkulation", closed`);
  }
  check(!row('Regie').querySelector('.ofdkcnt') && row('Schnitt').querySelector('.ofdkcnt')?.textContent === '1' && /1 geändert/.test(row('Schnitt').querySelector('[data-ofd="it-kalk"]').getAttribute('aria-label') || ''),
    `${tag}: only "Schnitt" (purchase 300) shows a number at its button`);
  const tx0 = d.querySelector('#ofd-totals')?.textContent || '';
  // open, close, open: no amount changes, nothing is saved
  const kb = () => row('Regie').querySelector('[data-ofd="it-kalk"]');
  click(w, kb()); click(w, kb()); click(w, kb());
  const fl = row('Regie').querySelector('.ofdflags');
  check(kb().getAttribute('aria-expanded') === 'true' && shown(fl) && shown(row('Regie').querySelector('[data-ofd="it-pdisc"]')) && shown(row('Regie').querySelector('[data-k="opt"]')),
    `${tag}: opened: discount %, ticks and the kind of the position show`);
  const words = fl?.textContent || '';
  check(/Aufschlag/.test(words) && /rabattfähig/.test(words) && /Handlungskosten/.test(words) && !/Markup/.test(words) && !/\bRabatt\b(?! %)/.test(words.replace(/rabattfähig/g, '')),
    `${tag}: the words "Aufschlag" and "rabattfähig", no "Markup", no second "Rabatt": ${words.replace(/\s+/g, ' ').trim()}`);
  check(!shown(row('Schnitt').querySelector('[data-k="cost"]')), `${tag}: the other row stays closed`);
  check((d.querySelector('#ofd-totals')?.textContent || '') === tx0 && JSON.stringify((await get()).totals) === JSON.stringify(q.totals), `${tag}: opening and closing changes no amount`);
  // a discount of 10 % on "Regie"
  click(w, row('Regie').querySelector('[data-ofd="it-pdisc"]'));
  const pin = await until(() => row('Regie')?.querySelector('[data-k="discount_pct"]'));
  change(w, pin, '10');
  const x = await until(async () => { const j = await get(); return +j.items?.[0]?.discount_pct === 10 ? j : null; });
  check(x && x.totals?.lines?.find(l => l.title === 'Regie')?.total === 1800 && x.totals?.lines?.find(l => l.title === 'Schnitt')?.total === 1950, `${tag}: saved: Regie 1800, Schnitt 1950 unchanged`);
  await until(() => /1\.800,00/.test(row('Regie')?.querySelector('.ofdlt')?.textContent || ''));
  check(/1\.800,00/.test(row('Regie').querySelector('.ofdlt').textContent) && /10 %/.test(row('Regie').textContent), `${tag}: on screen: 1.800,00 and the 10 % note in the row`);
  check(row('Regie').querySelector('[data-ofd="it-kalk"]').getAttribute('aria-expanded') === 'true' && shown(row('Regie').querySelector('[data-k="discount_pct"]')) && row('Regie').querySelector('.ofdkcnt')?.textContent === '1',
    `${tag}: after the redraw the calculation stays open and counts the discount`);
  w.close();
  return q.id;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const AK = await login('alice');
  await call(AK, 'POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal', 'comments']});
  await call(AK, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEATURES});
  const me = (await call(AK, 'GET', '/api/state')).me;
  const org = await call(AK, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(AK, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  const fu = await call(AK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fu.http < 300, 'a person without an organisation ' + fu.http);
  const FK = await login('frida');
  await call(FK, 'PATCH', '/api/settings', {lang: 'de', tour: 'done', features: FEATURES});
  check(((await call(FK, 'GET', '/api/state')).me.workspaces || []).length === 0, 'frida is in no organisation');

  await editor('alice', AK, 'org');
  const QF = await editor('frida', FK, 'frida');

  // ---- the layout: phone (finger) and computer (mouse)
  for (const [wd, ht, touch, tag] of [[390, 844, true, 'p390'], [1280, 900, false, 'c1280']]) {
    await firefox(async o => {
      const {cmd, ev, ctx, shot} = o;
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: wd, height: ht}});
      await o.nav(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`) === 200, `${tag}: login`);
      const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(250); } return false; };
      await o.nav(B + `#office/offers/${QF}`);
      const ROW = t => `[...document.querySelectorAll('.ofdeditor .ofdits .ofdit')].find(li => li.querySelector('[data-k="title"]')?.value === '${t}')`;
      check(await wait(`!!${ROW('Schnitt')} && !!${ROW('Drohne')}`), `${tag}: the editor with its positions`);
      await sleep(300);
      const m = JSON.parse(await ev(`(() => { const r = ${ROW('Schnitt')}, b = r.querySelector('[data-ofd="it-kalk"]').getBoundingClientRect(), t = r.querySelector('[data-k="title"]').getBoundingClientRect(),
        o = ${ROW('Drohne')}.querySelector('[data-k="title"]').getBoundingClientRect();
        return JSON.stringify({h: r.getBoundingClientRect().height, bh: b.height, bw: b.width, tl: t.left, ol: o.left, vw: innerWidth, br: b.right}); })()`));
      if (touch) {
        check(m.h < 400, `${tag}: the closed position is short (${Math.round(m.h)} px, was about 600)`);
        check(m.bh >= 43.5 && m.br <= m.vw + .5, `${tag}: the button "Kalkulation" is 44 px high and inside the screen (${Math.round(m.bh)} px)`);
      } else check(Math.abs(m.tl - m.ol) <= 1, `${tag}: the optional position's title starts where a normal one's does (${Math.round(m.tl)} / ${Math.round(m.ol)})`);
      await ev(`(() => { ${ROW('Schnitt')}.querySelector('[data-ofd="it-kalk"]').click(); return 1; })()`);
      check(await wait(`!${ROW('Schnitt')}.querySelector('.ofdflags').hidden`), `${tag}: the button opens the calculation`);
      const p = JSON.parse(await ev(`(() => { const r = ${ROW('Schnitt')}, f = r.querySelector('.ofdflags'), d = r.querySelector('[data-ofd="it-pdisc"]').getBoundingClientRect(),
        lab = [...f.querySelectorAll('label')].filter(l => l.getBoundingClientRect().width > 0).map(l => l.textContent.trim());
        return JSON.stringify({dh: d.height, lab, out: [...f.querySelectorAll('label, button, select')].filter(x => x.getBoundingClientRect().right > innerWidth + .5).length}); })()`));
      check(p.lab.some(l => /Aufschlag/.test(l)) && p.lab.some(l => /rabattfähig/.test(l)), `${tag}: "Aufschlag" and "rabattfähig" are visible: ${p.lab.join(' | ')}`);
      check(!p.out, `${tag}: every field of the calculation inside the screen`);
      if (touch) check(p.dh >= 43.5, `${tag}: the button "Rabatt %" is 44 px high for a finger (${Math.round(p.dh)} px)`);
      await ev(`(() => { ${ROW('Regie')}.scrollIntoView({block: 'start'}); return 1; })()`); await sleep(200);  // the picture shows the positions
      await shot(`p21175c-${tag}.png`);
    }, touch);
  }

  console.log(`p21175_c_angebot_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: exception', e); process.exit(1); });
