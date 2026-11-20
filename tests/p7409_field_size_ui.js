// kalmido-suite: fresh
// #7409 UI test: on a phone (finger, Android-like browser) the text in fields and dropdowns is as large as the label
// (--fs-b), not 16 px; 16 px only with html.vpios (iPhone / iPad, icons.js VP_IOS, against Safari's zoom). In a dialog on a
// phone a dropdown and a number field are as wide as their content (never wider than the row), a text field keeps the
// row's width; the 44 px field height stays. One shared rule (app.css), checked on a dialog built with modal() and on the
// real "New client" dialog. Firefox with a finger at 412 and 320 px, own container, invented names only.
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7409_field_size_ui', check, shots: 'P7409_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

const MEASURE = `(() => {
  const md = document.querySelector('.modal.p7409');
  const px = e => e ? Math.round(parseFloat(getComputedStyle(e).fontSize) * 10) / 10 : null;
  const pr = document.createElement('span'); pr.style.fontSize = 'var(--fs-b)'; md.appendChild(pr); const lab = px(pr); pr.remove();
  const w = s => { const e = md.querySelector(s); return e ? Math.round(e.getBoundingClientRect().width) : null; };
  const h = s => { const e = md.querySelector(s); return e ? Math.round(e.getBoundingClientRect().height) : null; };
  const row = s => { const e = md.querySelector(s)?.closest('.row'); if (!e) return null; const cs = getComputedStyle(e); return Math.round(e.getBoundingClientRect().width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)); };
  return {lab, sel: px(md.querySelector('#p7409-s')), num: px(md.querySelector('#p7409-n')), txt: px(md.querySelector('#p7409-t')),
    selW: w('#p7409-s'), numW: w('#p7409-n'), txtW: w('#p7409-t'), longW: w('#p7409-l'), rowW: row('#p7409-s'), selH: h('#p7409-s'), txtH: h('#p7409-t')};
})()`;
const OPEN = `(() => { document.querySelectorAll('.modal.p7409').forEach(m => m.remove());
  const md = modal('<h3>Probe</h3><div class="row"><label for="p7409-s">Aktiv</label><select id="p7409-s"><option>Ja</option><option>Nein</option></select></div>'
    + '<div class="row"><label for="p7409-n">Anzahl</label><input id="p7409-n" type="number" value="3"></div>'
    + '<div class="row"><label for="p7409-t">Name</label><input id="p7409-t" value="Werkstatt"></div>'
    + '<div class="row"><label for="p7409-l">Lang</label><select id="p7409-l"><option>' + 'Eine sehr lange Auswahl, die breiter ist als jede Zeile eines Telefons '.repeat(2) + '</option></select></div>'
    + '<div class="foot"><button class="btn" data-m="close">Close</button></div>');
  md.classList.add('p7409'); md.querySelector('[data-m="close"]').addEventListener('click', () => md.remove()); return 1; })()`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  await firefox(async ({cmd, ev, nav, ctx, until}) => {
    const wait = s => until(() => ev(s));
    await nav(B + 'static/icon.svg');
    const st = await ev(`fetch('/api/auth/login', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    check(st === 200, 'login ' + st);
    await ev(`fetch('/api/admin/setup', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({lang: 'en', collab_all: true, time_all: true, modules: ['office', 'comments']})}).then(() => 1)`);
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: ${JSON.stringify(H)}, body: JSON.stringify({lang: 'en', tour: 'done', features: 'comments,collab,contacts,office,clients,time'})}).then(() => 1)`);
    for (const width of [412, 320]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width, height: 800}});
      await nav(B + '#clients'); await wait(`!!S.booted && !!document.querySelector('#view [data-act="client-new"]')`);
      check(await ev(`matchMedia('(pointer:coarse)').matches && !document.documentElement.classList.contains('vpios')`), `${width}: a finger, not an iPhone`);
      await ev(OPEN); await wait(`!!document.querySelector('.modal.p7409 #p7409-s')`);
      let m = await ev(MEASURE);
      check(m.lab > 0 && m.lab < 16, `${width}: the label size is below 16 px ${JSON.stringify(m)}`);
      check(m.sel === m.lab && m.num === m.lab && m.txt === m.lab, `${width}: dropdown, number and text field write as large as the label ${JSON.stringify(m)}`);
      check(m.selH >= 43 && m.txtH >= 43, `${width}: the fields keep their 44 px height ${JSON.stringify(m)}`);
      check(m.selW < m.rowW * 0.6 && m.selW >= 60, `${width}: the dropdown "Ja / Nein" is as wide as its content ${JSON.stringify(m)}`);
      check(m.numW < m.rowW * 0.6, `${width}: the number field is not as wide as the row ${JSON.stringify(m)}`);
      check(m.txtW >= m.rowW - 2, `${width}: the text field keeps the row's width ${JSON.stringify(m)}`);
      check(m.longW <= m.rowW + 1, `${width}: a long dropdown never gets wider than the row ${JSON.stringify(m)}`);
      check(await ev(`document.documentElement.scrollWidth <= innerWidth && (() => { const md = document.querySelector('.modal.p7409'); return md.scrollWidth <= md.clientWidth + 1; })()`), `${width}: the dialog does not scroll sideways`);
      // usable: choose in the dropdown, type into the number field, close
      check(await ev(`(() => { const s = document.querySelector('#p7409-s'); s.value = 'Nein'; s.dispatchEvent(new Event('change', {bubbles: true})); const n = document.querySelector('#p7409-n'); n.focus(); n.value = '12'; n.dispatchEvent(new Event('input', {bubbles: true})); return s.value === 'Nein' && n.value === '12'; })()`), `${width}: the dropdown and the number field take a value`);
      await ev(`document.querySelector('.modal.p7409 [data-m="close"]').click(); 1`);
      check(await ev(`!document.querySelector('.modal.p7409')`), `${width}: the dialog closes`);
      // iPhone / iPad: the one detection gives 16 px
      await ev(`document.documentElement.classList.add('vpios'); 1`); await ev(OPEN);
      m = await ev(MEASURE);
      check(m.sel === 16 && m.num === 16 && m.txt === 16, `${width}: with html.vpios (iPhone / iPad) the fields keep 16 px ${JSON.stringify(m)}`);
      await ev(`document.querySelector('.modal.p7409')?.remove(); document.documentElement.classList.remove('vpios'); 1`);
      // the real "New client" dialog: its fields too
      await ev(`document.querySelector('#view [data-act="client-new"]').click(); 1`); await wait(`!!document.querySelector('.modal.cldlg #cl-name')`);
      const c = await ev(`(() => { const pr = document.createElement('span'); pr.style.fontSize = 'var(--fs-b)'; document.body.appendChild(pr); const lab = parseFloat(getComputedStyle(pr).fontSize); pr.remove(); return {lab, name: parseFloat(getComputedStyle(document.querySelector('#cl-name')).fontSize)}; })()`);
      check(c.name === c.lab && c.name < 16, `${width}: "New client": the name field writes as large as the label ${JSON.stringify(c)}`);
      await ev(`document.querySelector('.modal.cldlg [data-m="close"]').click(); 1`);
    }
  }, true);
  console.log(`p7409_field_size_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
