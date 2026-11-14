// 2.1170.0 UI test, part B (#6110 the file view: a preview for every kind of file, a calm head on a phone): own container
// kalmido-suite: fresh
// (start.sh), jsdom + Firefox (phone 360 px). Invented data only. P21170B_NOSTART=1 = the container runs.
// - a Word file of a folder opens the file view with the office preview IN the preview column (its text readable: heading and
//   bold word), no page count / zoom there, Full screen stays
// - a ZIP: the archive icon, "No preview for this kind of file" and Download; no bar at all (nothing to zoom)
// - a text file: its text in the preview column
// - Back names the folder it came from and leads there (the folder's files again)
// - Firefox 360 px: the long title of the Word file in a row of its own, whole (not cut), Back with the folder's name and
//   Download / Actions / Delete in the row below it, nothing sideways; the ZIP's sentence and Download in sight; a one-page
//   PDF's bar in ONE row with the short page count "1 / 1" (the long one was cut to "Se")
// P4: alice works without an organisation (private files): the person without an organisation (freelancer-matrix: files)
const {execFileSync} = require('child_process');
const path = require('path');
const fs = require('fs');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21170_b_fileview_ui', check, shots: 'P21170B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21170B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const FEAT = 'cal,collab,comments,contacts,files,docs,wiki';
const DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = async (fn, n = 75) => { for (let i = 0; i < n; i++) { const x = await fn(); if (x) return x; await sleep(200); } return fn(); };
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));

// the test files: written with Python's zipfile (no zip library in node, nothing checked in)
const MAKE = String.raw`
import io, sys, zipfile
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
def z(parts):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as f:
        for k, v in parts.items():
            f.writestr(k, v)
    return b.getvalue()
p = lambda x, st="": '<w:p>' + ('<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % st if st else '') + x + '</w:p>'
r = lambda t, b=False: '<w:r>' + ('<w:rPr><w:b/></w:rPr>' if b else '') + '<w:t xml:space="preserve">%s</w:t></w:r>' % t
body = p(r("Projektplan Seestern"), "Heading1") + p(r("Wir liefern ") + r("Treibholz", True) + r(" am Montag."))
docx = z({"word/document.xml": '<w:document %s><w:body>%s</w:body></w:document>' % (W, body),
          "word/styles.xml": '<w:styles %s><w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style></w:styles>' % W})
out = sys.argv[1]
open(out + "/plan.docx", "wb").write(docx)
open(out + "/paket.zip", "wb").write(z({"liesmich.txt": "Inhalt der Kiste", "bild/leer.txt": ""}))
`;
const TMP = path.join(DATA, 'p21170b-files');
fs.mkdirSync(TMP, {recursive: true});
execFileSync('python3', ['-c', MAKE, TMP]);
const DOCX = fs.readFileSync(path.join(TMP, 'plan.docx')), ZIP = fs.readFileSync(path.join(TMP, 'paket.zip'));

function pdf(lines) {  // a one-page PDF with a text layer, written by hand
  const esc = s => s.replace(/[\\()]/g, c => '\\' + c);
  const st = 'BT /F1 12 Tf 60 740 Td 16 TL ' + lines.map(l => `(${esc(l)}) '`).join(' ') + ' ET';
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${st.length} >>\nstream\n${st}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const x = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${x}\n%%EOF\n`;
  return Buffer.from(out, 'latin1');
}
async function upload(name, data, type, parent) {
  const fd = new FormData();
  fd.append('file', new Blob([data], {type}), name);
  fd.append('parent_id', String(parent));
  const r = await fetch(B + 'api/files/upload', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd});
  return ((await r.json()).items || [])[0]?.id;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {tour: 'done', lang: 'en', features: FEAT});
  const FNAME = 'Hafen Nordkai';
  const FID = (await call('POST', '/api/files/folders', {name: FNAME, space: 'private'})).id;
  const LONG = 'Drehgenehmigung Hafenamt Nordkai Sommer 2026 Fassung drei.docx';
  const DX = await upload(LONG, DOCX, DOCX_MIME, FID);
  const ZP = await upload('paket.zip', ZIP, 'application/zip', FID);
  const TX = await upload('notiz.txt', 'Zeile eins\nLeuchtturm am Kai\n', 'text/plain', FID);
  const PD = await upload('einseiter.pdf', pdf(['Einseiter Beispiel']), 'application/pdf', FID);
  check(FID && DX && ZP && TX && PD, 'setup: a folder with a Word file, a ZIP, a text file and a PDF ' + JSON.stringify([FID, DX, ZP, TX, PD]));

  // ================= jsdom: the preview column of each kind, Back to the folder
  const w = await boot({user: 'alice', hash: `ablage/${FID}`}), d = w.document;
  check(await until(() => w.eval(`(AB.data?.items || []).length === 4`) && w.eval('typeof ab_openFile === "function"')), 'the folder lists its four files');
  const v = () => d.querySelector('.dv-view');
  const openF = async id => { w.eval(`ab_openFile(ab_item(${id}))`); return until(() => w.location.hash === `#ablage/${id}` && v()?.querySelector('.dc-body')?.dataset.id === String(id)); };

  // the Word file: its text in the preview column
  check(await openF(DX), 'the Word file opens in the file view');
  const pvo = () => v()?.querySelector('.dv-pv .dv-pvo');
  check(await until(() => /Projektplan Seestern/.test(pvo()?.querySelector('.dpvdoc')?.textContent || '')), 'the Word file: the office preview in the preview column (its heading) ' + (pvo()?.textContent || '').slice(0, 120));
  check(pvo()?.querySelector('.dpvdoc strong')?.textContent === 'Treibholz', '... with its bold word, built from the model');
  check(!v().querySelector('.dv-pv [data-dc^="dvz:"]') && !v().querySelector('.dv-pv .dv-pgn') && !v().querySelector('.dv-pv .dv-pages'), '... no page count, no zoom, no page box (nothing to page)');
  check(!!v().querySelector('.dv-pv [data-dc="view"]'), '... Full screen stays (the lightbox of the office preview)');
  check(!d.querySelector('.lightbox'), '... and no lightbox opened by itself');
  const back = () => v()?.querySelector('.dv-head .dv-back');
  check(back()?.textContent.trim() === FNAME, `Back names the folder it came from ("${back()?.textContent.trim()}")`);

  // Back leads into that folder
  click(w, back());
  check(await until(() => !v() && w.location.hash === `#ablage/${FID}` && d.querySelector(`.abrow[data-abid="${ZP}"], [data-abid="${ZP}"]`)), 'Back leads into the folder, its files again ' + w.location.hash);

  // the ZIP: icon + sentence + Download, no bar
  check(await openF(ZP), 'the ZIP opens in the file view');
  const msg = () => v()?.querySelector('.dv-pv .dv-pvmsg');
  check(await until(() => /No preview for this kind of file/.test(msg()?.textContent || '')), 'the ZIP: "No preview for this kind of file" ' + (v()?.querySelector('.dv-pv')?.textContent || '').slice(0, 120));
  const dl = msg()?.querySelector('a[download]');
  check(dl && /Download/.test(dl.textContent) && /dl=1|download/.test(dl.getAttribute('href') || ''), '... with Download (the file itself) ' + dl?.getAttribute('href'));
  check(!v().querySelector('.dv-pv .dv-pvbar') && !v().querySelector('.dv-pv [data-dc^="dvz:"]'), '... no zoom bar at all');
  check(!!msg()?.querySelector('svg.i'), '... with an icon of its kind');
  check(back()?.textContent.trim() === FNAME, '... Back names the folder here too');

  // the text file: its text in the column
  click(w, back());
  await until(() => !v() && w.location.hash === `#ablage/${FID}`);
  check(await openF(TX), 'the text file opens in the file view');
  check(await until(() => /Leuchtturm am Kai/.test(pvo()?.querySelector('pre, .tvmd')?.textContent || '')), 'the text file: its text in the preview column ' + (pvo()?.textContent || '').slice(0, 80));
  check(!v().querySelector('.dv-pv [data-dc^="dvz:"]'), '... no zoom there');
  w.close();

  // ================= Firefox, phone 360 px: the head, the ZIP's sentence, the PDF's bar in one row
  await firefox(async ({cmd, ev, nav, ctx, shot}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 740}});
    await nav(B + `#ablage/${FID}`);
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(250); } return false; };
    check(await wait(`typeof ab_openFile === 'function' && (AB.data?.items || []).length === 4`), 'Firefox 360: the folder with its four files');
    const openF = async id => { await ev(`(ab_openFile(ab_item(${id})), 1)`); return wait(`location.hash === '#ablage/${id}' && document.querySelector('.dv-view .dc-body')?.dataset.id === '${id}'`, 80); };

    check(await openF(DX), 'Firefox 360: the Word file opens');
    check(await wait(`/Treibholz/.test(document.querySelector('.dv-view .dv-pvo .dpvdoc')?.textContent || '')`), 'Firefox 360: its text in the preview column');
    const hd = await ev(`(() => { const q = s => document.querySelector('.dv-view ' + s), r = e => e.getBoundingClientRect(), t = q('.dv-title'), bk = q('.dv-back'), bs = bk.querySelector('span'), dl = q('.dv-hacts .dv-dl'), del = q('.dv-hacts [data-dc="del"]'), v = document.querySelector('.dv-view');
      return {title: t.textContent.trim(), cutX: t.scrollWidth > t.clientWidth + 1, tw: Math.round(r(t).width), tb: Math.round(r(t).bottom), bt: Math.round(r(bk).top), dt: Math.round(r(dl).top), delR: Math.round(r(del).right), vw: innerWidth,
        bl: bs.textContent.trim(), blw: Math.round(r(bs).width), sw: v.scrollWidth, cw: v.clientWidth}; })()`);
    check(hd && hd.title === LONG && !hd.cutX && hd.tw >= 300, 'Firefox 360: the title whole, in a row of its own ' + JSON.stringify(hd));
    check(hd && hd.bt >= hd.tb - 1 && hd.dt >= hd.tb - 1 && hd.delR <= hd.vw, 'Firefox 360: Back and Download / Actions / Delete in the row after the title, in sight');
    check(hd && hd.bl === FNAME && hd.blw > 20, 'Firefox 360: Back shows the folder\'s name');
    check(hd && hd.sw <= hd.cw + 1, 'Firefox 360: nothing sideways');
    await shot('p21170b-docx-360.png');

    await ev(`(document.querySelector('.dv-view .dv-back').click(), 1)`);
    check(await wait(`!document.querySelector('.dv-view') && location.hash === '#ablage/${FID}'`), 'Firefox 360: Back leads into the folder');
    check(await openF(ZP), 'Firefox 360: the ZIP opens');
    const zp = await ev(`(() => { const m = document.querySelector('.dv-view .dv-pvmsg'); if (!m) return null; const a = m.querySelector('a[download]').getBoundingClientRect(), p = m.querySelector('p').getBoundingClientRect();
      return {txt: m.textContent.trim(), at: Math.round(a.top), ab: Math.round(a.bottom), pt: Math.round(p.top), vh: innerHeight, bar: !!document.querySelector('.dv-view .dv-pvbar')}; })()`);
    check(zp && /No preview for this kind of file/.test(zp.txt) && zp.ab <= zp.vh && zp.pt >= 0 && !zp.bar, 'Firefox 360: the ZIP\'s sentence and Download in sight, no bar ' + JSON.stringify(zp));
    await shot('p21170b-zip-360.png');

    await ev(`(document.querySelector('.dv-view .dv-back').click(), 1)`);
    await wait(`!document.querySelector('.dv-view') && location.hash === '#ablage/${FID}'`);
    check(await openF(PD), 'Firefox 360: the PDF opens');
    check(await wait(`!!document.querySelector('.dv-view .dv-pages .dv-pg canvas') && /1 \\/ 1/.test(document.querySelector('.dv-view .dv-pgn')?.textContent || '')`, 80), 'Firefox 360: the PDF page drawn, the page count there');
    const bar = await ev(`(() => { const b = document.querySelector('.dv-view .dv-pvbar'), r = b.getBoundingClientRect(), kids = [...b.children].filter(e => e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none'), tops = kids.map(e => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)), s = b.querySelector('.dv-pgs'), l = b.querySelector('.dv-pgl');
      return {h: Math.round(r.height), spread: Math.max(...tops) - Math.min(...tops), short: s && getComputedStyle(s).display !== 'none' ? s.textContent : '', long: l ? getComputedStyle(l).display : ''}; })()`);
    check(bar && bar.spread <= 3 && bar.h <= 64 && bar.short === '1 / 1' && bar.long === 'none', 'Firefox 360: the PDF bar in one row with "1 / 1" (no "Se") ' + JSON.stringify(bar));
    await shot('p21170b-pdf-360.png');
  });

  console.log(`p21170_b_fileview_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
