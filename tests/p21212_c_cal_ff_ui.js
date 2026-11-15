// 2.1212.0 part C (#6158 the Calendars window on a computer, #6156 the calendar's Share dialog): Firefox, real layout,
// kalmido-suite: fresh
// freelancer-matrix: n/a (no route of its own; the window is drawn in the client, tested as alice without an organisation)
// German, invented data only. Computer 820 x 900 and 1280 x 800 (mouse), phone 390 x 844.
// - "Kalender" window: a shared calendar's row shows its name in full (not "Drehplanung · Gege…") and below it the line
//   "geteilt mit 2 Personen" in view (it was cut away from 600 px on); on a phone the same
// - its Share dialog: the shared frame of projects / folders (head with the cross, "Fertig"), the people with the role words
//   "Nur ansehen" / "Mitglied", the role choice not cut
// With P21212C_SHOTS: pictures of the window and the dialog.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21212_c_cal_ff_ui', check, shots: 'P21212C_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CK}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', lang: 'de'})});
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'de', collab_all: true, modules: ['cal']});
  await call('PATCH', '/api/settings', {lang: 'de', tour: 'done', features: 'cal,events,collab'});
  const W = await call('POST', '/api/evcals', {name: 'Drehplanung', color: '#2dd4bf'});
  const P = await call('POST', '/api/evcals', {name: 'Büro', color: '#f5b041'});
  const bob = await call('POST', '/api/users', {username: 'bob', display_name: 'Bob Berger', password: 'password123'});
  const carol = await call('POST', '/api/users', {username: 'carol', display_name: 'Carola Kramer-Schulte', password: 'password123'});
  check(W.id && P.id && bob.id && carol.id, 'two calendars, two more people');
  check((await call('PUT', `/api/evcals/${W.id}/members`, {user_id: bob.id, role: 'view'})).http < 300 && (await call('PUT', `/api/evcals/${W.id}/members`, {user_id: carol.id, role: 'edit'})).http < 300, 'Drehplanung shared with both');
  const me = (await call('GET', '/api/state')).me;
  check(!(me?.workspaces || []).length, 'alice: no organisation (freelancer)');
  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
  const start = async (ev, nav) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); localStorage.setItem('tasks.calMode', '"month"'); return 1; })()`);
    await signIn(ev);
    await nav(B + '#cal');
  };
  const winOpen = async ev => { await ev(`(() => { document.querySelector('#view [data-act="ev-cals"]').click(); return 1; })()`); return ready(ev, `!!document.querySelector('.modal.evcmodal .evcrow [data-evcshow]')`); };
  // the row of Drehplanung: its name and its second line, each with whether it is cut and whether it is in view
  const ROW = `JSON.stringify((() => { const r = document.querySelector('.evcmodal [data-evcmenu="${W.id}"]').closest('.evcrow'), n = r.querySelector('.evcnm'), s = r.querySelector('.evcsub'), m = r.closest('.modal').getBoundingClientRect();
    const cut = e => !e || e.scrollWidth > e.clientWidth + 1 || e.getBoundingClientRect().right > m.right + 1, vis = e => !!e && e.offsetParent !== null && e.getBoundingClientRect().height > 0;
    return {name: n?.innerText, nameCut: cut(n), sub: s?.innerText, subCut: cut(s), subVis: vis(s), lines: Math.round(r.querySelector('.evcn').getBoundingClientRect().height)}; })())`;

  for (const [wd, ht, phone] of [[820, 900, false], [1280, 800, false], [390, 844, true]]) {
    await firefox(async ({cmd, ev, ctx, nav, shot}) => {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: wd, height: ht}});
      await start(ev, nav);
      check(await ready(ev, `S.route?.mod === 'cal' && !!document.querySelector('#view [data-act="ev-cals"]')`), `${wd}: the calendar loaded`);
      check(await winOpen(ev), `${wd}: the Calendars window opens`);
      const row = JSON.parse(await ev(ROW));
      check(row.name === 'Drehplanung' && !row.nameCut, `#6158 ${wd}: the name in full ` + JSON.stringify(row));
      check(row.subVis && /geteilt mit 2 Personen/.test(row.sub || '') && !row.subCut, `#6158 ${wd}: "geteilt mit 2 Personen" in view below it ` + JSON.stringify(row));
      await shot(`p21212-c-window-${wd}.png`);
      if (phone) return;
      // the Share dialog of the calendar (from its row menu)
      await ev(`(() => { document.querySelector('.evcmodal [data-evcmenu="${W.id}"]').click(); return 1; })()`);
      check(await ready(ev, `[...document.querySelectorAll('#pop [role="menuitem"]')].some(b => /Teilen/.test(b.innerText))`), `${wd}: the row menu has "Teilen…"`);
      await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(b => /Teilen/.test(b.innerText)).click(); return 1; })()`);
      check(await ready(ev, `!!document.querySelector('.modal.evsmodal #evs-members .mrow[data-uid="${carol.id}"]')`), `#6156 ${wd}: the Share dialog shows the people`);
      const dlg = JSON.parse(await ev(`JSON.stringify((() => { const md = document.querySelector('.modal.evsmodal'), r = md.querySelector('.mrow[data-uid="${carol.id}"]'), sel = r.querySelector('select'), b = md.querySelector('.mrow[data-uid="${bob.id}"] select');
        return {x: !!md.querySelector('.lhdr [data-m="close"]'), done: md.querySelector('.foot .btn.pri')?.innerText.trim(), name: r.querySelector('.n')?.innerText.trim(),
          role: sel?.selectedOptions[0]?.text, roleB: b?.selectedOptions[0]?.text, opts: [...(sel?.options || [])].map(o => o.text), selCut: !sel || sel.scrollWidth > sel.clientWidth + 2 || sel.getBoundingClientRect().right > md.getBoundingClientRect().right}; })())`));
      check(dlg.x && dlg.done === 'Fertig', `#6156 ${wd}: the shared frame (cross on top, "Fertig") ` + JSON.stringify(dlg));
      check(/Carola Kramer-Schulte/.test(dlg.name || '') && dlg.role === 'Mitglied' && dlg.roleB === 'Nur ansehen' && dlg.opts.join('|') === 'Mitglied|Nur ansehen', `#6156 ${wd}: the role words of projects and folders ` + JSON.stringify(dlg));
      check(!dlg.selCut, `#6156 ${wd}: the role choice is not cut ` + JSON.stringify(dlg));
      await shot(`p21212-c-share-${wd}.png`);
    }, phone);
  }

  console.log(`p21212_c_cal_ff_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
