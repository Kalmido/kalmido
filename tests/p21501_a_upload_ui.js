// kalmido-suite:
// 2.1501.0 A UI test (#7689): the two upload buttons "Photograph receipt" + "Upload files" are ONE building block with ONE
// arrangement on a phone. Own container (start.sh), Firefox at phone width. Invented people and figures only.
// freelancer-matrix: office -- alice works in her own office without an organisation.
// - decided 21.11.2026: from 340 px both buttons stand in one line, half the room each (equal width and height), a long label
//   breaks inside its button, nothing cut - checked in German and French at 390 and 412 px in the bookkeeping, the empty
//   receipts view, the receipts list with entries and a member's "Submit receipt"; at 320 px one under the other, nothing cut;
//   the empty view's button symbol in normal size
// - Settings > Company & office: the button "E-mail signature…" opens the dialog "E-mail signature" (the same name)
// P21501A_NOSTART=1 = the server already runs. Screenshots: P21501A_SHOTS.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21501_a_upload_ui', check, shots: 'P21501A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21501A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    const j = await r.json().catch(() => ({})); return {...j, http: r.status};
  }
};
const FEAT = 'cal,comments,collab,contacts,office,clients,docs,files';

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  const me = await call(CA, 'GET', '/api/state');
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha Studio', admin_id: me.me.id});
  await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob Member', password: 'password123', email: 'bob@example.com'});
  check((await call(CA, 'PUT', `/api/orgs/${org.id}/members`, {email: 'bob@example.com', role: 'member'})).http < 300, 'bob joins Alpha Studio as member');
  const CB = await login('bob');
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});  // alice: her own office, no organisation
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${org.id}`});

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const signIn = (ev, u) => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`);
  const fresh = async (ev, nav, u) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.ofmAll', 'true'); return 1; })()`);
    await ev(`fetch('/api/auth/logout', {method: 'POST', headers: {'X-Requested-With': 'kalmido'}}).then(r => r.status)`).catch(() => 0);
    check(await signIn(ev, u) === 200, `${u} signs in`);
  };
  // (#7689, decided 21.11.2026): from 340 px the two buttons in SCOPE stand in one line, half the room each (equal width and
  // height), a long label breaks INSIDE its button (nothing cut, nothing sticks out); below 340 px one under the other
  const geo = (scope, shot, files) => `(() => { const s = document.querySelector('${scope} ${shot}')?.closest('label'), f = document.querySelector('${scope} ${files}')?.closest('label');
    if (!s || !f || !s.getClientRects().length || !f.getClientRects().length) return null;
    const a = s.getBoundingClientRect(), b = f.getBoundingClientRect(), W = document.documentElement.clientWidth;
    const cut = [s, f].filter(x => x.scrollWidth > x.clientWidth + 1 || [...x.querySelectorAll('span')].some(y => y.scrollWidth > y.clientWidth + 1));
    return {at: [a.top, b.top], w: [a.width, b.width], h: [a.height, b.height], bottom: a.bottom, cut: cut.length, out: a.left < -1 || b.right > W + 1 || document.documentElement.scrollWidth > W + 1,
      room: s.parentElement.getBoundingClientRect().width, svg: s.querySelector('svg')?.getBoundingClientRect().width, text: [s.textContent.trim(), f.textContent.trim()]}; })()`;
  const sideBySide = g => !!g && Math.abs(g.at[0] - g.at[1]) < 2 && Math.abs(g.w[0] - g.w[1]) < 3 && Math.abs(g.h[0] - g.h[1]) < 2 && !g.cut && !g.out;
  const stacked = g => !!g && g.at[1] >= g.bottom - 1 && !g.cut && !g.out;
  const setLang = async (ck, lg) => call(ck, 'PATCH', '/api/settings', {lang: lg});
  const place = async (ev, nav, hash, scope, shotSel, filesSel) => {
    await nav(B + 'static/icon.svg');
    await nav(B + hash);
    await ready(ev, `!!document.querySelector('${scope} ${shotSel}') && !!document.querySelector('${scope} ${filesSel}')`, 80);
    return ev(geo(scope, shotSel, filesSel));
  };
  const PLACES = {books: ['#office/books', '.bk-photo', '#bk-file', '#bk-files'], empty: ['#office/receipts', '.rcl-none', '#bk-file', '#bk-files'],
    list: ['#office/receipts', '.rcl-tools', '#bk-file', '#bk-files']};
  const round = async (ev, nav, cmd, ctx, ck, names, langs) => {
    for (const lg of langs) {
      await setLang(ck, lg);
      for (const w of [390, 412, 320]) {
        await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: 860}});
        for (const n of names) {
          const g = await place(ev, nav, ...PLACES[n]);
          const okay = w >= 340 ? sideBySide(g) : stacked(g);
          check(okay, `#7689 ${n} ${lg} ${w}: ${w >= 340 ? 'side by side, equal width and height, nothing cut' : 'one under the other, nothing cut'} ${JSON.stringify(g)}`);
          if (n === 'empty' && w === 412) check(g && g.svg > 0 && g.svg <= 24, `#7689 empty ${lg}: the button's symbol in normal size (${g?.svg})`);
        }
      }
    }
  };

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await fresh(ev, nav, 'alice');
    // no receipt yet: the bookkeeping and the empty receipts view
    await round(ev, nav, cmd, ctx, CA, ['books', 'empty'], ['de', 'fr']);
    await shot('p21501a-empty-fr-320.png');
    // a receipt (the upload's own way, office_books.js bkUpload; the sheet saved as it opens), then the list with entries
    await setLang(CA, 'en');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await nav(B + 'static/icon.svg');
    await nav(B + '#office/books');
    await ready(ev, `typeof bkUpload === 'function' && !!document.querySelector('#bk-files')`, 80);
    await ev(`(() => { bkUpload([new File(['%PDF-1.4\\n%%EOF\\n'], 'beleg-7689.pdf', {type: 'application/pdf'})]); return 1; })()`);
    await ready(ev, `!!document.querySelector('.bk-sheet [data-m="save"]') && !!document.querySelector('.bk-sheet #bk-cat')`, 60);
    await ev(`(() => { const m = document.querySelector('.bk-sheet'); if (!m) return 0; m.querySelector('#bk-amount').value = '11.90'; m.querySelector('#bk-cat').value = 'Software'; m.querySelector('#bk-date').value = new Date().toISOString().slice(0, 10); m.querySelector('[data-m="save"]').click(); return 1; })()`);
    await ready(ev, `!document.querySelector('.bk-sheet')`, 60);
    check(await ready(ev, `fetch('/api/office/books/receipts.csv').then(r => r.text()).then(t => /beleg-7689|Software/.test(t))`, 60), 'the receipt is booked');
    await round(ev, nav, cmd, ctx, CA, ['list'], ['de', 'fr']);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await nav(B + 'static/icon.svg'); await nav(B + '#office/receipts');
    await shot('p21501a-list-fr-412.png');
    // Settings > Company & office: the button and its dialog carry the same name
    await setLang(CA, 'en');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await nav(B + '#office/books');
    await ready(ev, `!!document.querySelector('#bk-files')`, 60);
    await ev(`(() => { const b = document.createElement('button'); b.type = 'button'; b.dataset.setgo = 'biz-docs'; document.querySelector('.office').append(b); b.click(); return 1; })()`);
    const sig = await ev(`(async () => { for (let i = 0; i < 60 && !document.querySelector('[data-ltm="sig"]'); i++) await new Promise(r => setTimeout(r, 250));
      const b = document.querySelector('[data-ltm="sig"]'); if (!b) return 'no button'; const d = b.closest('details'); if (d) d.open = true; b.click();
      for (let i = 0; i < 60 && !document.querySelector('.modal #ofm-text'); i++) await new Promise(r => setTimeout(r, 250));
      const h = document.querySelector('.modal #ofm-text')?.closest('.modal')?.querySelector('h3'); return b.textContent.trim() + ' | ' + (h ? h.textContent.trim() : 'no dialog'); })()`);
    check(sig === 'E-mail signature… | E-mail signature', `#7689: "E-mail signature…" opens the dialog of the same name: ${sig}`);
    // a member hands in a receipt: the same two buttons in the same arrangement
    await fresh(ev, nav, 'bob');
    for (const lg of ['de', 'fr']) {
      await setLang(CB, lg);
      for (const w of [390, 412, 320]) {
        await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: 860}});
        const g = await place(ev, nav, '#office/receipts', '.rsb-up', '#rsb-shot', '#rsb-files');
        check(w >= 340 ? sideBySide(g) : stacked(g), `#7689 member ${lg} ${w}: ${JSON.stringify(g)}`);
      }
    }
    await shot('p21501a-member-fr-320.png');
  }, false);

  console.log(`p21501_a_upload_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
