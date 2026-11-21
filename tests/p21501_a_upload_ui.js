// kalmido-suite:
// 2.1501.0 A UI test (#7689): the two upload buttons "Photograph receipt" + "Upload files" are ONE building block with ONE
// arrangement on a phone. Own container (start.sh), Firefox at phone width. Invented people and figures only.
// freelancer-matrix: office -- alice works in her own office without an organisation.
// - 412 px: in the bookkeeping, in the empty receipts view and in the receipts list with entries both buttons stand in one line
//   (same top edge) and share it half and half (a label longer than half keeps its width, the other takes the rest); a member's "Submit receipt" draws the same
// - 320 px: nothing sticks out to the side, no button label is cut (they may wrap there)
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
  // the two buttons in SCOPE: both shown, one line (same top edge), half the room each (the receipts list's "More" aside); the answer names the measure when it fails
  const pair = (scope, shot, files) => `(() => { const s = document.querySelector('${scope} ${shot}')?.closest('label'), f = document.querySelector('${scope} ${files}')?.closest('label');
    if (!s || !f || !s.getClientRects().length || !f.getClientRects().length) return 'missing';
    const a = s.getBoundingClientRect(), b = f.getBoundingClientRect();
    const W = s.parentElement.getBoundingClientRect().width;  // half each; a label longer than half keeps its whole width, the other takes the rest
    return Math.abs(a.top - b.top) < 2 && Math.min(a.width, b.width) >= W * .4 && (Math.abs(a.width - b.width) < 3 || Math.min(a.width, b.width) + Math.max(a.width, b.width) >= W * .9) ? true : 'top ' + a.top + '/' + b.top + ' width ' + a.width + '/' + b.width + ' room ' + s.parentElement.getBoundingClientRect().width + ' font ' + getComputedStyle(s).fontSize + ' pad ' + getComputedStyle(s).paddingLeft; })()`;
  // 320 px: no sideways scroll, every button keeps its label whole and stays in the window
  const fits = scope => `(() => { const W = document.documentElement.clientWidth; if (document.documentElement.scrollWidth > W + 1) return 'page ' + document.documentElement.scrollWidth + ' > ' + W;
    const bad = [...document.querySelectorAll('${scope} .bk-shot, ${scope} .bk-files')].filter(b => b.getClientRects().length && (b.scrollWidth > b.clientWidth + 1 || b.getBoundingClientRect().right > W + 1 || b.getBoundingClientRect().left < -1));
    return bad.length ? bad.map(b => b.textContent.trim() + ' ' + b.scrollWidth + '/' + b.clientWidth).join(', ') : true; })()`;

  await firefox(async ({cmd, ev, ctx, nav, shot}) => {
    for (const w of [412, 320]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: 860}});
      await fresh(ev, nav, 'alice');
      // the bookkeeping
      await nav(B + '#office/books');
      check(await ready(ev, `!!document.querySelector('.bk-photo #bk-file') && !!document.querySelector('.bk-photo #bk-files')`, 80), `${w}: the bookkeeping with both buttons (a phone)`);
      const books = await ev(w === 412 ? pair('.bk-photo', '#bk-file', '#bk-files') : fits('.bk-photo'));
      check(books === true, `#7689 ${w}: the bookkeeping ${w === 412 ? 'has both buttons in one line, equally wide' : 'fits without sideways scroll or cut labels'}: ${books}`);
      await shot(`p21501a-books-${w}.png`);
      if (w === 412) {
        // the empty receipts view
        await nav(B + '#office/receipts');
        check(await ready(ev, `!!document.querySelector('.rcl-none .bk-photo #bk-file') && !!document.querySelector('.rcl-none .bk-photo #bk-files')`, 80), '412: the empty receipts view with both buttons');
        const empty = await ev(pair('.rcl-none', '#bk-file', '#bk-files'));
        check(empty === true, `#7689 412: the empty receipts view has both buttons in one line, equally wide: ${empty}`);
        await shot('p21501a-empty-412.png');
        // a receipt, then the list with entries
        // the upload's own way (office_books.js bkUpload), the sheet saved as it opens
        await ev(`(() => { bkUpload([new File(['%PDF-1.4\\n%%EOF\\n'], 'beleg-7689.pdf', {type: 'application/pdf'})]); return 1; })()`);
        const up = await ready(ev, `!!document.querySelector('.bk-sheet [data-m="save"]') && !!document.querySelector('.bk-sheet #bk-cat')`, 60);
        await ev(`(() => { const m = document.querySelector('.bk-sheet'); if (!m) return 0; m.querySelector('#bk-amount').value = '11.90'; m.querySelector('#bk-cat').value = 'Software'; m.querySelector('#bk-date').value = new Date().toISOString().slice(0, 10); m.querySelector('[data-m="save"]').click(); return 1; })()`);
        await ready(ev, `!document.querySelector('.bk-sheet')`, 60);
        check(await ready(ev, `fetch('/api/office/books/receipts.csv').then(r => r.text()).then(t => /beleg-7689|Software/.test(t))`, 60), '412: the receipt is booked');
        await nav(B + 'static/icon.svg');
        await nav(B + '#office/receipts');
        check(await ready(ev, `!!document.querySelector('.rcl-tools #bk-file') && !document.querySelector('.rcl-none')`, 80), '412: the receipts list with an entry and both buttons ' + up + ' ' + await ev(`JSON.stringify({n: RCL.data?.total, used: OFC.info?.used, sheet: !!document.querySelector('.bk-sheet'), t: document.querySelector('.ofcbody')?.textContent.slice(0, 200)})`).catch(e => String(e)));
        const list = await ev(pair('.rcl-tools', '#bk-file', '#bk-files'));
        check(list === true, `#7689 412: the receipts list keeps both buttons in one line, equally wide: ${list}`);
        await shot('p21501a-list-412.png');
        // Settings > Company & office: the button and its dialog carry the same name
        await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
        await nav(B + '#office/books');
        await ready(ev, `!!document.querySelector('#bk-files')`, 60);
        await ev(`(() => { const b = document.createElement('button'); b.type = 'button'; b.dataset.setgo = 'biz-docs'; document.querySelector('.office').append(b); b.click(); return 1; })()`);
        const sig = await ev(`(async () => { for (let i = 0; i < 60 && !document.querySelector('[data-ltm="sig"]'); i++) await new Promise(r => setTimeout(r, 250));
          const b = document.querySelector('[data-ltm="sig"]'); if (!b) return 'no button'; const d = b.closest('details'); if (d) d.open = true; b.click();
          for (let i = 0; i < 60 && !document.querySelector('.modal #ofm-text'); i++) await new Promise(r => setTimeout(r, 250));
          const h = document.querySelector('.modal #ofm-text')?.closest('.modal')?.querySelector('h3'); return b.textContent.trim() + ' | ' + (h ? h.textContent.trim() : 'no dialog'); })()`);
        check(sig === 'E-mail signature… | E-mail signature', `#7689: "E-mail signature…" opens the dialog of the same name: ${sig}`);
      }
    }
    // a member hands in a receipt: the same two buttons in the same arrangement
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await fresh(ev, nav, 'bob');
    await nav(B + '#office/receipts');
    check(await ready(ev, `!!document.querySelector('.rsb #rsb-shot') && !!document.querySelector('.rsb #rsb-files')`, 80), '412: a member\'s "Submit receipt" with both buttons');
    const rsb = await ev(pair('.rsb-up', '#rsb-shot', '#rsb-files'));
    check(rsb === true, `#7689 412: a member's "Submit receipt" has both buttons in one line, equally wide: ${rsb}`);
    await shot('p21501a-member-412.png');
  }, false);

  console.log(`p21501_a_upload_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
