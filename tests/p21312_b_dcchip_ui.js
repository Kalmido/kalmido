// kalmido-suite:
// 2.1312.0 UI test (#6493: the area on a document card stands whole), own container (start.sh), Firefox (touch) at the phone
// (412 x 915) and the unfolded Fold (884 x 1104). Invented data only.
// Rule (owner decision 16.11.2026): on the document cards the area (dot + name, e.g. "Private") always stands in full; short
// names are never cut; a long organisation name is cut only when the card really is too narrow, and then names itself in full
// as the title.
// - "All workspaces", a private document and one of an organisation with a long name: the private card shows the dot and the
//   whole name (not the phone's short letters, no "Pri…": scrollWidth <= clientWidth), inside its card
// - the organisation's card: its mark stays inside the card; cut only when it does not fit, with the full name as title
// freelancer-matrix: n/a - nur Oberfläche (eine Person mit privater Ablage und einer Organisation)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21312_b_dcchip_ui', check, shots: 'P21312B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21312B_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n = 60) => require('./boot').until(fn, {timeout: Math.max(15000, n * 200), step: 100});
const LONG = 'Kulturverein Beispielstadt Musterhausen und Umgebung';

function textPdf(lines) {  // a one-page PDF with a text layer, written by hand
  const esc = s => s.replace(/[\\()]/g, c => '\\' + c);
  const stream = 'BT /F1 12 Tf 60 740 Td 16 TL ' + lines.map(l => `(${esc(l)}) '`).join(' ') + ' ET';
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let out = '%PDF-1.4\n'; const offs = [];
  objs.forEach((o, i) => { offs.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const x = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offs.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${x}\n%%EOF\n`;
  return Buffer.from(out, 'latin1');
}
async function upload(name, ws) {
  const fd = new FormData();
  fd.append('files', new Blob([textPdf(['Bescheinigung', 'Beispiel'])], {type: 'application/pdf'}), name);
  fd.append('ws', ws);
  const r = await fetch(B + 'api/docs', {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd});
  const id = ((await r.json().catch(() => ({}))).ids || [])[0];
  if (id) await until(async () => ['done', 'failed'].includes((await call('GET', `/api/docs/${id}`)).state), 150);
  return id;
}

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  const su = await call('POST', '/api/admin/setup', {org_name: LONG, lang: 'en', collab_all: true, modules: ['docs']});
  check(su.http < 300, 'setup: the organisation ' + JSON.stringify(su));
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', workspace: 'all', features: 'files,docs'});
  const ORG = ((await call('GET', '/api/state')).me?.workspaces || [])[0]?.id;
  check(!!ORG, 'setup: the organisation\'s id');
  const PID = await upload('own.pdf', 'private'), OID = await upload('club.pdf', 'org:' + ORG);
  check(PID && OID, 'setup: a private document and one of the organisation');

  await firefox(async ({cmd, ev, nav: go, ctx, shot}) => {
    await go(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'Firefox: login');
    const wait = async (js, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(js).catch(() => false)) return true; await sleep(150); } return false; };
    // the mark of one card: its name's box, the short letters, where it stands in its card
    const MARK = id => `(() => { const c = document.querySelector('#view .dc-card [data-dco="${id}"]')?.closest('.dc-card'), m = c?.querySelector('.dco'); if (!m) return null;
      const n = m.querySelector('.wsows'), ab = m.querySelector('.wsoab'), dot = m.querySelector('.wsp-dot'), cr = c.getBoundingClientRect(), mr = m.getBoundingClientRect();
      return {name: n?.textContent, seen: !!n && n.getBoundingClientRect().width > 0 && getComputedStyle(n).display !== 'none', sw: n?.scrollWidth, cw: n?.clientWidth,
        ab: !!ab && getComputedStyle(ab).display !== 'none', dot: !!dot && dot.getBoundingClientRect().width > 0, inside: mr.right <= cr.right + 1 && mr.left >= cr.left - 1,
        room: (ct => Math.round(ct.clientWidth - parseFloat(getComputedStyle(ct).paddingLeft) - parseFloat(getComputedStyle(ct).paddingRight) - mr.width))(c.querySelector('.dc-ct')), title: m.title, full: wsName('${id === PID ? 'private' : 'org:' + ORG}'), cardW: Math.round(cr.width)}; })()`;
    for (const [W, Ht] of [[412, 915], [884, 1104]]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: W, height: Ht}});
      check(await wait(`innerWidth === ${W}`, 40), `Firefox ${W}: the window has its size`);
      await go(B + '#docs');
      check(await wait(`document.querySelectorAll('#view .dc-card .dco').length === 2 && wsCur() === 'all'`, 120), `Firefox ${W}: "All workspaces", two cards with their area ` + await ev(`JSON.stringify({ws: typeof wsCur === 'function' && wsCur(), n: document.querySelectorAll('#view .dc-card').length, m: document.querySelectorAll('#view .dc-card .dco').length})`));
      const p = await ev(MARK(PID));
      check(p && p.seen && !p.ab && p.dot && p.name === p.full, `Firefox ${W}: the private card shows the dot and the whole name "${p?.full}", not the short letters ` + JSON.stringify(p));
      check(p && p.sw <= p.cw && p.inside, `Firefox ${W}: ... not cut (scrollWidth <= clientWidth), inside its card ` + JSON.stringify(p));
      const o = await ev(MARK(OID));
      check(o && o.seen && !o.ab && o.inside && o.name === o.full, `Firefox ${W}: the organisation's card: its whole name in the mark, inside the card ` + JSON.stringify(o));
      check(o && (o.sw <= o.cw || o.room <= 1) && o.title === o.full, `Firefox ${W}: ... cut only when the card is too narrow (it then fills the card), the full name as title ` + JSON.stringify(o));
      await shot(`p21312b-dcchip-${W}.png`);
    }
  }, true);

  console.log(`p21312_b_dcchip_ui: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
