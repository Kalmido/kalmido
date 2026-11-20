// kalmido-suite: fresh
// (#7532) UI test, own container (start.sh), Firefox. Invented names and generated pictures only.
// freelancer-matrix: videos
// - a task with several image approvals offers "Overview of the images (n)": tiles with title and the number of open
//   comments; the filter With / Without comments / All narrows them; a tile opens its approval, closing it comes back to
//   the overview
// - computer: dragging with the mouse over the image marks an area ("at area n"), the comment keeps it (pos w / h) and the
//   area is drawn with its number; a plain click still sets a point
// - "Compare versions": two versions side by side on the computer, one above the other on the phone; the other version can
//   be chosen
// - phone: "Area", then a finger drag marks an area (without "Area" the finger scrolls: no area)
// - many files at once: the file picker takes several, each becomes an approval, one undo step, the overview opens
const path = require('path');
const zlib = require('zlib');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7532_b_images_ui', check, shots: 'P7532B_SHOTS'});
const H = {'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7532B_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, 'Content-Type': 'application/json', Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
// a real PNG of w x h in one colour (no library)
const CRC = Array.from({length: 256}, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc = b => { let c = 0xffffffff; for (const x of b) c = CRC[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
const chunk = (t, d) => { const len = Buffer.alloc(4); len.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const cr = Buffer.alloc(4); cr.writeUInt32BE(crc(td)); return Buffer.concat([len, td, cr]); };
function png(w, h, rgb) {
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({length: w}, () => rgb).flat())]);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({length: h}, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}
const up = async (ck, url, fields, name, data) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, String(v));
  fd.append('file', new Blob([data], {type: 'image/png'}), name);
  const r = await fetch(B + url.replace(/^\//, ''), {method: 'POST', headers: {...H, Cookie: ck}, body: fd});
  return {...(await r.json().catch(() => ({}))), http: r.status};
};

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: {...H, 'Content-Type': 'application/json'}, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab,videos,files'});
  const st = await call(CA, 'GET', '/api/state');
  const inbox = (st.lists || []).find(l => l.is_inbox);
  const t = await call(CA, 'POST', '/api/tasks', {title: 'Screens Rundgang', list_id: inbox?.id});
  check(t.http < 300, 'a task ' + t.http);
  const a = await up(CA, '/api/videos', {task_id: t.id, title: 'Startseite'}, 'start.png', png(400, 300, [40, 120, 200]));
  const b = await up(CA, '/api/videos', {task_id: t.id, title: 'Kontakt'}, 'kontakt.png', png(400, 300, [200, 120, 40]));
  const c = await up(CA, '/api/videos', {task_id: t.id, title: 'Impressum'}, 'impressum.png', png(400, 300, [60, 160, 60]));
  check(a.http < 300 && b.http < 300 && c.http < 300, `three image approvals ${a.http} ${b.http} ${c.http}`);
  const v2 = await up(CA, `/api/videos/${a.id}/versions`, {}, 'start-v2.png', png(400, 300, [90, 60, 180]));
  check(v2.http < 300 && v2.versions?.length === 2, 'Startseite has two versions ' + v2.http);
  const cm = await call(CA, 'POST', `/api/videos/${b.id}/comments`, {pos: {x: 0.2, y: 0.2}, body: 'Telefonnummer fehlt'});
  check(cm.http < 300, 'a comment on Kontakt ' + cm.http);

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  const rect = sel => `(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; const r = e.getBoundingClientRect(); return JSON.stringify({x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom, r: r.right}); })()`;
  const box = async (ev, sel) => JSON.parse(await ev(rect(sel)) || 'null');
  const openTask = async ev => {
    await ev(`openDetail(${t.id})`);
    return ready(ev, `!!document.querySelector('#d-vdr [data-vdr="grid"]')`, 80);
  };

  // ---- computer
  await firefox(async ({cmd, ev, ctx, nav, drag}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 900}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#inbox');
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && S.tasks.has(${t.id})`, 80), 'booted');
    check(await openTask(ev), 'the task shows "Overview of the images"');
    check(await ev(`/\\(3\\)/.test(document.querySelector('#d-vdr [data-vdr="grid"]').textContent)`), 'the button counts the 3 images');
    await ev(`document.querySelector('#d-vdr [data-vdr="grid"]').click()`);
    check(await ready(ev, `document.querySelectorAll('.vdrgmd .vdrtile').length === 3`), 'overview: 3 tiles');
    check(await ev(`(() => { const t = [...document.querySelectorAll('.vdrgmd .vdrtile')].find(x => /Kontakt/.test(x.textContent)); return !!t && /1 open comment/.test(t.textContent) && !!t.querySelector('img'); })()`), 'the Kontakt tile: picture, title and "1 open comment"');
    await ev(`document.querySelector('.vdrgmd [data-vdrgf="with"]').click()`);
    check(await ready(ev, `document.querySelectorAll('.vdrgmd .vdrtile').length === 1`), 'filter With comments: 1 tile');
    await ev(`document.querySelector('.vdrgmd [data-vdrgf="without"]').click()`);
    check(await ready(ev, `document.querySelectorAll('.vdrgmd .vdrtile').length === 2 && document.querySelector('.vdrgmd [data-vdrgf="without"]').getAttribute('aria-pressed') === 'true'`), 'filter Without comments: 2 tiles, the chip pressed');
    await ev(`document.querySelector('.vdrgmd [data-vdrgf="all"]').click()`);
    check(await ready(ev, `document.querySelectorAll('.vdrgmd .vdrtile').length === 3`), 'filter All: 3 again');
    // a tile opens its approval; closing comes back to the overview
    await ev(`[...document.querySelectorAll('.vdrgmd .vdrtile')].find(x => /Impressum/.test(x.textContent)).click()`);
    check(await ready(ev, `document.querySelector('.vdrdlg #vdr-h')?.textContent === 'Impressum'`), 'a tile opens its approval');
    await ev(`document.querySelector('.vdrdlg [data-m="close"]').click()`);
    check(await ready(ev, `!document.querySelector('.vdrdlg') && !!document.querySelector('.vdrgmd .vdrtile')`), 'closing it: back at the overview');

    // ---- an area with the mouse (Impressum: one version)
    await ev(`[...document.querySelectorAll('.vdrgmd .vdrtile')].find(x => /Impressum/.test(x.textContent)).click()`);
    check(await ready(ev, `(() => { const i = document.querySelector('.vdrdlg [data-vdr-stage] img'); return !!i && i.complete && i.naturalWidth > 0; })()`), 'the image is shown');
    const sb = await box(ev, '.vdrdlg [data-vdr-stage]');
    await drag(sb.x + sb.w * 0.2, sb.y + sb.h * 0.2, sb.w * 0.4, sb.h * 0.3);
    check(await ready(ev, `/at area 1/.test(document.querySelector('.vdrdlg [data-vdr="pt"]')?.textContent || '') && !!document.querySelector('.vdrdlg .vdrbox.new')`), 'a mouse drag marks an area ("at area 1", drawn)');
    await ev(`(() => { const i = document.querySelector('#vdr-in'); i.value = 'Fusszeile zu eng'; document.querySelector('.vdrdlg [data-vdr="send"]').click(); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.vdrdlg .vdrbox:not(.new)') && !!document.querySelector('.vdrdlg .vdrpin[data-vdr="mk"]')`), 'saved: the area drawn with its number');
    const got = await call(CA, 'GET', `/api/videos/${c.id}`);
    const pos = (got.comments || []).find(x => x.body === 'Fusszeile zu eng')?.pos || {};
    check(Math.abs(pos.x - 0.2) < 0.03 && Math.abs(pos.y - 0.2) < 0.03 && Math.abs(pos.w - 0.4) < 0.03 && Math.abs(pos.h - 0.3) < 0.03, 'the server keeps the area ' + JSON.stringify(pos));
    // a plain click still sets a point
    const sb2 = await box(ev, '.vdrdlg [data-vdr-stage]');
    await cmd('input.performActions', {context: ctx, actions: [{type: 'pointer', id: 'm1', parameters: {pointerType: 'mouse'}, actions: [{type: 'pointerMove', x: Math.round(sb2.x + sb2.w * 0.8), y: Math.round(sb2.y + sb2.h * 0.8)}, {type: 'pointerDown', button: 0}, {type: 'pointerUp', button: 0}]}]});
    await cmd('input.releaseActions', {context: ctx});
    check(await ready(ev, `/at point 2/.test(document.querySelector('.vdrdlg [data-vdr="pt"]')?.textContent || '') && !document.querySelector('.vdrdlg .vdrbox.new')`), 'a click sets a point ("at point 2"), no area');
    await ev(`document.querySelector('.vdrdlg [data-m="close"]').click()`);

    // ---- compare two versions: side by side
    await ev(`[...document.querySelectorAll('.vdrgmd .vdrtile')].find(x => /Startseite/.test(x.textContent)).click()`);
    check(await ready(ev, `!!document.querySelector('.vdrdlg [data-vdr="cmp"]')`), 'Startseite (two versions): "Compare versions"');
    await ev(`document.querySelector('.vdrdlg [data-vdr="cmp"]').click()`);
    check(await ready(ev, `document.querySelectorAll('.vdrdlg .vdrvs figure img').length === 2 && [...document.querySelectorAll('.vdrdlg .vdrvs figure img')].every(i => i.complete && i.naturalWidth > 0)`), 'two versions shown');
    const fa = await box(ev, '.vdrdlg .vdrvsa'), fb = await box(ev, '.vdrdlg .vdrvsb');
    check(fa && fb && fa.r <= fb.x + 1 && Math.abs(fa.y - fb.y) < 4, 'computer: side by side ' + JSON.stringify({fa, fb}));
    check(await ev(`document.querySelector('#vdr-cmpv').value === String(${v2.versions[0].id}) && /v2/.test(document.querySelector('.vdrvsb figcaption').textContent)`), 'left the older v1, right v2');
    await ev(`document.querySelector('.vdrdlg [data-vdr="cmp"]').click()`);
    check(await ready(ev, `!document.querySelector('.vdrdlg .vdrvs') && !!document.querySelector('.vdrdlg [data-vdr-stage] img')`), 'Compare off: one image again');
    await ev(`document.querySelector('.vdrdlg [data-m="close"]').click()`);
    await ev(`document.querySelector('.vdrgmd [data-m="close"]').click()`);

    // ---- many files at once
    await ev(`document.querySelector('#d-vdr [data-vdr="newfile"]').click()`);
    check(await ready(ev, `!!document.querySelector('#vdr-file') && document.querySelector('#vdr-file').multiple`), 'the file picker takes several files');
    const pngB64 = png(40, 30, [10, 10, 10]).toString('base64');
    await ev(`(() => { const b = Uint8Array.from(atob('${pngB64}'), ch => ch.charCodeAt(0)); const fs = ['flur.png', 'bad.png', 'kueche.png'].map(n => new File([b], n, {type: 'image/png'}));
      vdr_upMany('task_id', ${t.id}, fs, document.querySelector('#vdr-file').closest('.modal')); return 1; })()`);
    check(await ready(ev, `document.querySelectorAll('.vdrgmd .vdrtile').length === 6`, 100), 'three uploaded: the overview opens with 6 tiles');
    check(await ready(ev, `/3 approvals created/.test(document.body.textContent)`), 'one toast for all three');
    const list = await call(CA, 'GET', `/api/videos?task_id=${t.id}`);
    check((list.reviews || []).filter(x => ['flur.png', 'bad.png', 'kueche.png'].includes(x.title)).length === 3, 'three approvals named by their files');
  }, false);

  // ---- phone: compare stacked, an area with the finger after "Area"
  await firefox(async ({cmd, ev, ctx, nav, drag}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    await signIn(ev);
    await nav(B + '#inbox');
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && isMobile()`, 80), 'phone: booted');
    await ev(`vdr_open(${a.id})`);
    check(await ready(ev, `!!document.querySelector('.vdrdlg [data-vdr="cmp"]')`), 'phone: Compare versions');
    await ev(`document.querySelector('.vdrdlg [data-vdr="cmp"]').click()`);
    check(await ready(ev, `[...document.querySelectorAll('.vdrdlg .vdrvs figure img')].every(i => i.complete && i.naturalWidth > 0) && document.querySelectorAll('.vdrdlg .vdrvs figure img').length === 2`), 'phone: two versions shown');
    const fa = await box(ev, '.vdrdlg .vdrvsa'), fb = await box(ev, '.vdrdlg .vdrvsb');
    check(fa && fb && fa.b <= fb.y + 1, 'phone: one above the other ' + JSON.stringify({fa, fb}));
    await ev(`document.querySelector('.vdrdlg [data-vdr="cmp"]').click()`);
    check(await ready(ev, `(() => { const i = document.querySelector('.vdrdlg [data-vdr-stage] img'); return !!i && i.complete && i.naturalWidth > 0; })()`), 'phone: one image again');
    await ev(`document.querySelector('.vdrdlg [data-vdr-stage]').scrollIntoView({block: 'center'}), 1`);
    let sb = await box(ev, '.vdrdlg [data-vdr-stage]');
    await drag(sb.x + sb.w * 0.3, sb.y + sb.h * 0.3, sb.w * 0.3, sb.h * 0.3, 'touch');
    check(await ev(`!document.querySelector('.vdrdlg .vdrbox.new')`), 'phone: a finger drag without "Area" marks nothing');
    await ev(`document.querySelector('.vdrdlg [data-vdr="area"]').click()`);
    check(await ready(ev, `document.querySelector('.vdrdlg [data-vdr="area"]').getAttribute('aria-pressed') === 'true' && document.querySelector('.vdrdlg [data-vdr-stage]').classList.contains('vdrareaon')`), 'phone: "Area" on');
    await ev(`document.querySelector('.vdrdlg [data-vdr-stage]').scrollIntoView({block: 'center'}), 1`);
    sb = await box(ev, '.vdrdlg [data-vdr-stage]');
    await drag(sb.x + sb.w * 0.3, sb.y + sb.h * 0.3, sb.w * 0.3, sb.h * 0.3, 'touch');
    check(await ready(ev, `!!document.querySelector('.vdrdlg .vdrbox.new') && /at area/.test(document.querySelector('.vdrdlg [data-vdr="pt"]').textContent)`), 'phone: with "Area" a finger drag marks an area');
  }, true);

  console.log(`p7532_b_images_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
