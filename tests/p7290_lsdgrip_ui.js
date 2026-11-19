// #7290 UI test: the grip between list and detail of the building block .lsd2 (clientpage.js lsg_*, start-lsd-4553.css).
// kalmido-suite: fresh
// Firefox 1280 x 800 (mouse), a person without an organisation (freelancer parity), Contacts with a long name:
// - the grip sits between list and card (focusable separator with a name)
// - dragging it to the right makes the list wider (the long name is no longer cut), the card keeps the rest; remembered for
//   the page on this device: a reload brings the same width
// - arrow keys: left 1 rem narrower; Home = the narrowest (--w-leiste-min, 14 rem), End = at most half the pair
// - double-click: the standard width again, nothing stored
// Firefox 390 x 844 touch: one column, no grip to see - the list alone and (#7376) an open contact / client card, where only
// the card is drawn: no grey line at its left edge; open and back still work
// Invented names only.
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7290_lsdgrip_ui', check, shots: 'P7290_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const login = async user => { const r = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: user, password: 'password123'})}); return (r.headers.get('set-cookie') || '').split(';')[0]; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ACK = await login('alice');
  await call(ACK, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  const fr = await call(ACK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(fr.id > 0, 'a person without an organisation ' + JSON.stringify(fr));
  const FCK = await login('frida');
  await call(FCK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'contacts,clients,office'});
  const bk = (await call(FCK, 'POST', '/api/books', {name: 'People'})).id;
  const LONG = 'Maximiliane Konstantinopoulou-Wettersteinhausen';
  const c1 = await call(FCK, 'POST', '/api/contacts', {book_id: bk, fn: LONG, given: 'Maximiliane', family: 'Konstantinopoulou-Wettersteinhausen'});
  for (const n of ['Ann Example', 'Ben Example']) await call(FCK, 'POST', '/api/contacts', {book_id: bk, fn: n});
  check(c1.id > 0, 'setup: contacts');
  const cl1 = await call(FCK, 'POST', '/api/clients', {name: 'Example Studio'});
  check(cl1.id > 0, 'setup: a client ' + JSON.stringify(cl1));

  const signIn = async ({ev, nav}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    return ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);
  };
  const box = `(() => { const p = document.querySelector('#view .lsd2'), g = p && p.querySelector(':scope > .lsdgrip'), l = p && p.querySelector(':scope > .lsdl'), c = p && p.querySelector(':scope > .ctcard');
    if (!g || !l || !c || g.hidden) return null; const a = g.getBoundingClientRect(), lr = l.getBoundingClientRect(), cr = c.getBoundingClientRect(), b = [...l.querySelectorAll('.ctrow b')].find(x => x.textContent.startsWith('Maximiliane'));
    return {x: a.left + a.width / 2, y: a.top + 120, gl: a.left, gr: a.right, lw: Math.round(lr.width), lr: lr.right, cl: cr.left, pw: p.clientWidth, cut: b ? b.scrollWidth > b.clientWidth + 1 : null,
      tab: g.tabIndex, role: g.getAttribute('role'), lbl: g.getAttribute('aria-label') || '', ls: localStorage.getItem('tasks.lsdW.contacts'), rem: parseFloat(getComputedStyle(document.documentElement).fontSize)}; })()`;

  await firefox(async o => {
    const {cmd, ev, ctx, nav, until, drag, shot} = o, tag = '1280';
    check(await signIn(o) === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 800}});
    await nav(B + `#contacts/${c1.id}`);
    const b0 = await until(box, {timeout: 20000});
    check(b0 && b0.tab === 0 && b0.role === 'separator' && b0.lbl && b0.gl >= b0.lr - 8 && b0.gr <= b0.cl + 8 && !b0.ls, `${tag}: the grip sits between list and card, focusable with a name ${JSON.stringify(b0)}`);
    await shot('p7290-1280-before.png');
    if (!b0) return;
    await drag(b0.x, b0.y, 160, 0);
    const b1 = await until(`(() => { const b = ${box}; return b && b.ls && b.lw > ${b0.lw} + 100 ? b : null; })()`, {timeout: 5000});
    check(b1 && b1.cl > b0.cl + 100 && b1.cut === false, `${tag}: dragged to the right: the list wider, the long name whole, the card keeps the rest ${JSON.stringify([b0, b1])}`);
    await shot('p7290-1280-wider.png');
    await nav(B + `#contacts/${c1.id}`);
    const b2 = await until(`(() => { const b = ${box}; return b && b.lw === ${b1 ? b1.lw : -1} ? b : null; })()`, {timeout: 20000});
    check(!!b2, `${tag}: after a reload the same width ${JSON.stringify([b1, b2])}`);
    const key = k => ev(`(() => { const g = document.querySelector('#view .lsd2 > .lsdgrip'); g.focus(); g.dispatchEvent(new KeyboardEvent('keydown', {key: '${k}', bubbles: true})); return 1; })()`);
    await key('ArrowLeft');
    const b3 = await ev(box);
    check(b2 && b3 && Math.abs(b3.lw - (b2.lw - b2.rem)) <= 1, `${tag}: arrow left: 1 rem narrower ${JSON.stringify([b2, b3])}`);
    await key('Home');
    const b4 = await ev(box);
    check(b4 && b4.lw === Math.round(14 * b4.rem) && b4.ls === '14', `${tag}: Home: the narrowest (14 rem) ${JSON.stringify(b4)}`);
    await key('End');
    const b5 = await ev(box);
    check(b5 && b5.lw <= b5.pw / 2 + 1 && b5.lw > b5.pw / 2 - b5.rem, `${tag}: End: at most half the pair ${JSON.stringify(b5)}`);
    await ev(`(() => { document.querySelector('#view .lsd2 > .lsdgrip').dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); return 1; })()`);
    const b6 = await until(`(() => { const b = ${box}; return b && !b.ls ? b : null; })()`, {timeout: 5000});
    check(b6 && b6.lw === b0.lw, `${tag}: double-click: the standard width again, nothing stored ${JSON.stringify([b0, b6])}`);
  });
  await firefox(async o => {
    const {cmd, ev, ctx, nav, until} = o, tag = '390 touch';
    check(await signIn(o) === 200, tag + ': login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + '#contacts');
    await until(`!!document.querySelector('#view .ctrow')`, {timeout: 20000});
    check(await ev(`(() => { const g = document.querySelector('#view .lsd2 > .lsdgrip'); return !g || g.hidden || !g.getClientRects().length; })()`), `${tag}: one column, no grip`);
    // #7376: an open card on the phone (only the card in the pair, no list): the grip stays hidden
    const noGrip = `(() => { const g = document.querySelector('#view .lsd2 > .lsdgrip'); return !g || g.hidden || !g.getClientRects().length || getComputedStyle(g).display === 'none'; })()`;
    for (const [hash, back, name] of [[`#contacts/${c1.id}`, '#contacts', 'contact'], [`#client/${cl1.id}`, '#clients', 'client']]) {
      await nav(B + hash);
      const card = await until(`(() => { const c = document.querySelector('#view .ctcard:not(.ctnone)'); return c && c.getBoundingClientRect().width > 300 ? 1 : 0; })()`, {timeout: 20000});
      check(!!card, `${tag}: the ${name} card opens`);
      await until(`!!document.querySelector('#view .lsd2 > .lsdgrip') || 1`, {timeout: 2000});
      check(await ev(noGrip), `${tag} #7376: the open ${name} card has no grip at its edge`);
      await nav(B + back);
      check(await until(`!!document.querySelector('#view .ctrow') && !document.querySelector('#view .ctcard:not(.ctnone)')`, {timeout: 20000}), `${tag}: back to the ${name} list`);
      check(await ev(noGrip), `${tag} #7376: the ${name} list has no grip`);
    }
  }, true);
  console.log(`p7290_lsdgrip_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
