// #7310 UI test: the preview windows (text file, PDF, Word / Excel) get wider by the corner of the one grip (grip.js,
// docs/dev/kern.md "Resizing: the one grip"; mode dialog, keys pv-text / pv-pdf / pv-doc).
// kalmido-suite: fresh
// Own container (start.sh), Firefox 1600 x 900 (mouse, real pointer input), a person WITHOUT an organisation (freelancer-matrix:
// files), nothing uploaded (the text file is a static file of the app, PDF / Word are blobs that fail to load: the window stays). Usability:
// - the text viewer: a corner grip (separator, data-grip pv-text); the window is 56rem; dragged out it grows on both sides
//   (centred) live, released it is kept (grip:pv-text) and the next text file opens as wide; it never gets narrower than
//   56rem nor wider than the window; switching Formatted / Source keeps the width and the grip; a double click = 56rem
// - the PDF window (64rem, pv-pdf) and the Word / Excel window (60rem, pv-doc) have their own width and grip
// - phone width: the full-screen window, no grip
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7310_preview_grip_ui', check, shots: 'P7310_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

const M = (box, k) => `JSON.stringify((() => {
  const b = document.querySelector('.lightbox ${box}'), r = b?.getBoundingClientRect(), g = b?.querySelector(':scope > .grip-c'), gr = g?.getBoundingClientRect();
  return {w: r ? Math.round(r.width) : 0, cx: r ? Math.round(r.left + r.width / 2) : 0, grip: !!gr && gr.width > 0 && getComputedStyle(g).display !== 'none', role: g?.getAttribute('role'), key: g?.dataset.grip,
    gx: gr ? gr.left + gr.width / 2 : 0, gy: gr ? gr.top + gr.height / 2 : 0, ls: localStorage.getItem('tasks.grip:${k}'), W: innerWidth,
    rem: parseFloat(getComputedStyle(document.documentElement).fontSize)};
})())`;
// a text file the server has anyway (a blob: URL is not allowed by the page's connect-src)
const TEXT = `(() => { textView({name: 'lizenz.md', size: 4400, url: '/static/fonts/OFL.txt', ext: 'md', md: true}); return 1; })()`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: []});
  await call(CA, 'POST', '/api/users', {orgs: [], username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com'});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'private'});
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'frida', password: 'password123'})}).then(r => r.status)`);

  await firefox(async ({cmd, ev, nav, ctx, shot, until, idle}) => {
    const open = async (W, clear) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: 900}});
      await nav(B + 'static/icon.svg');
      if (clear) { await ev(`(localStorage.clear(), sessionStorage.clear(), 1)`); check(await signIn(ev) === 200, `${W}: login`); }
      await nav(B + '#inbox'); await idle();
    };
    const drag = async (x0, y0, dx, dy, look) => {
      const vw = +(await ev('innerWidth')); dx = Math.max(1, Math.min(vw - 2, x0 + dx)) - x0;  // a far drag ends at the window's edge
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
        {type: 'pointerMove', x: Math.round(x0), y: Math.round(y0)}, {type: 'pointerDown', button: 0},
        {type: 'pointerMove', x: Math.round(x0 + dx / 2), y: Math.round(y0 + dy / 2), duration: 100}, {type: 'pointerMove', x: Math.round(x0 + dx), y: Math.round(y0 + dy), duration: 100}]}]});
      await sleep(80);
      const mid = look ? await ev(look) : null;
      await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerUp', button: 0}]}]});
      await cmd('input.releaseActions', {context: ctx});
      await sleep(80);
      return mid;
    };
    const get = async (box, k) => JSON.parse(await ev(M(box, k)));
    const ready = (box, extra = '') => until(`!!document.querySelector('.lightbox ${box} > .grip-c.grip')${extra}`, {timeout: 15000});

    await open(1600, true);
    // ---- the text viewer
    await ev(TEXT);
    check(await ready('.tvbox', ` && !!document.querySelector('.lightbox .tvmd')`), 'text: the viewer with its corner grip and the content');
    const t0 = await get('.tvbox', 'pv-text');
    check(t0.role === 'separator' && t0.key === 'pv-text' && Math.abs(t0.w - 56 * t0.rem) <= 2 && t0.ls == null, 'text: a separator named pv-text, the window 56rem, nothing stored ' + JSON.stringify(t0));
    const mid = JSON.parse(await drag(t0.gx - 4, t0.gy - 4, 80, 0, `JSON.stringify({w: Math.round(document.querySelector('.lightbox .tvbox').getBoundingClientRect().width)})`) || '{}');
    check(Math.abs(mid.w - (t0.w + 160)) <= 4, 'text: during the drag the window grows on both sides (centred) live ' + JSON.stringify(mid));
    const t1 = await get('.tvbox', 'pv-text');
    check(Math.abs(t1.w - (t0.w + 160)) <= 4 && Math.abs(t1.cx - t0.cx) <= 2 && /"w":66/.test(t1.ls || ''), 'text: released 66rem, still centred, kept under grip:pv-text ' + JSON.stringify(t1));
    await shot('p7310-text-wide.png');
    await ev(`(document.querySelector('.lightbox [data-tv="src"]')?.click(), 1)`);
    check(await ready('.tvbox', ` && !!document.querySelector('.lightbox .tvsrc')`), 'text: Source shown, the grip again');
    check(Math.abs((await get('.tvbox', 'pv-text')).w - t1.w) <= 2, 'text: switching to Source keeps the width');
    const t2 = await get('.tvbox', 'pv-text');
    await drag(t2.gx - 4, t2.gy - 4, -900, 0);
    const t3 = await get('.tvbox', 'pv-text');
    check(Math.abs(t3.w - 56 * t3.rem) <= 2, 'text: never narrower than 56rem ' + JSON.stringify(t3));
    await drag(t3.gx - 4, t3.gy - 4, 900, 0);
    const t4 = await get('.tvbox', 'pv-text');
    check(t4.w <= t4.W && t4.w > 66 * t4.rem, 'text: dragged to the window\'s edge it grows, at most the window ' + JSON.stringify(t4));
    await ev(`(document.querySelector('.lightbox [data-tv="x"]')?.click(), 1)`);
    await ev(`(localStorage.setItem('tasks.grip:pv-text', JSON.stringify({w: 70, h: 10})), 1)`);
    await ev(TEXT);
    check(await ready('.tvbox', ` && !!document.querySelector('.lightbox .tvbody :is(.tvmd, .tvsrc)')`), 'text: opened again (the content is in: the corner stays where it is)');
    const t5 = await get('.tvbox', 'pv-text');
    check(Math.abs(t5.w - 70 * t5.rem) <= 2, 'text: the next file opens with the kept width (70rem) ' + JSON.stringify(t5));
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm', parameters: {pointerType: 'mouse'}, actions: [
      {type: 'pointerMove', x: Math.round(t5.gx), y: Math.round(t5.gy)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}, {type: 'pause', duration: 80}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    check(await until(`localStorage.getItem('tasks.grip:pv-text') === null && Math.abs(document.querySelector('.lightbox .tvbox').getBoundingClientRect().width - 56 * ${t5.rem}) <= 2`, {timeout: 3000}), 'text: a double click = 56rem, nothing stored');
    await ev(`(document.querySelector('.lightbox')?.remove(), 1)`);

    // ---- the PDF window and the Word / Excel window: their own width and grip
    await ev(`(() => { pdfView({url: URL.createObjectURL(new Blob(['no pdf'], {type: 'application/pdf'})), name: 'vertrag.pdf', size: 6}); return 1; })()`);
    check(await ready('.pvbox'), 'PDF: the window with its corner grip');
    const p0 = await get('.pvbox', 'pv-pdf');
    check(p0.key === 'pv-pdf' && Math.abs(p0.w - 64 * p0.rem) <= 2, 'PDF: pv-pdf, 64rem ' + JSON.stringify(p0));
    await drag(p0.gx - 4, p0.gy - 4, 64, 0);
    const p1 = await get('.pvbox', 'pv-pdf');
    check(Math.abs(p1.w - (p0.w + 128)) <= 4 && /"w":72/.test(p1.ls || ''), 'PDF: dragged 8rem wider, kept under grip:pv-pdf ' + JSON.stringify(p1));
    await ev(`(document.querySelector('.lightbox')?.remove(), 1)`);
    await ev(`(() => { dpvOpen({url: URL.createObjectURL(new Blob(['{}'], {type: 'application/json'})), name: 'kalkulation.xlsx', size: 2}); return 1; })()`);
    check(await ready('.dpvbox'), 'Word / Excel: the window with its corner grip');
    const d0 = await get('.dpvbox', 'pv-doc');
    check(d0.key === 'pv-doc' && Math.abs(d0.w - 60 * d0.rem) <= 2 && d0.ls == null, 'Word / Excel: pv-doc, 60rem, its own width ' + JSON.stringify(d0));
    await ev(`(document.querySelector('.lightbox')?.remove(), 1)`);

    // ---- phone: full screen, no grip
    await open(390, false);
    await ev(TEXT);
    check(await until(`!!document.querySelector('.lightbox .tvbox .tvbody :is(.tvmd, .tvsrc)')`, {timeout: 15000}), 'phone: the viewer (Source is kept from above)');
    await sleep(300);
    const m0 = await get('.tvbox', 'pv-text');
    check(!m0.grip && m0.w >= 388, 'phone: the full-screen window, no grip ' + JSON.stringify(m0));
  });

  console.log(`p7310_preview_grip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
