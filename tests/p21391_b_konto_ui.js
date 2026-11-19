// kalmido-suite: fresh
// 2.1391.0 B UI test (#6130 Settings > Account and Notifications: order, everyday words, sessions, password fields, My colour).
// Own container (start.sh), Firefox. Invented names only. Since #6827 every section is a folded head row: the test opens them.
// - Account in the order Profile, Security and sign-in (password before the sessions), Devices and data (storage after the
//   app passwords, before "For advanced users"); Sign out next to the name and still at the very end
// - a session of a script (this test's node fetch) is "Program / script", never "node"
// - "No files stored yet, no storage limit" instead of "0 B used · no limit"
// - phone: the two password fields one under the other, each showing its whole placeholder
// - "For advanced users" instead of "Advanced · for developers"; the passkey hint in everyday words, the HTTPS / IP details
//   folded under "For advanced users" (server admin)
// - Notifications: Browser notification / Notification app / Both, the heading "Notification app", "Channel name", no "Topic" or
//   "Web Push" outside "For advanced users"; Tasks by e-mail: KALMIDO_* only folded
// - Organisation > My colour: a long workspace name is not cut, the swatches wrap inside the pane at 820 and 360 px
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const ffEn = require('./ff')({tag: 'p21391_b_konto_ui', check, shots: 'P21391B_SHOTS', allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const LONG = 'Kurzfilmfestival Musterstadt e. V. – Programmkommission';
// every folded section of the open settings pane open (#6827), so that the layout can be measured
const OPEN_ALL = `(() => { document.querySelectorAll('.smodal details.sfold:not([open])').forEach(d => { d.open = true; }); return 1; })()`;

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  CK = await login('alice');  // a session of this script: its User-Agent is "node"
  await call('POST', '/api/admin/setup', {org_name: 'Gegenlicht Beispiel GbR', lang: 'en', collab_all: true, modules: ['comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const o2 = await call('POST', '/api/orgs', {name: LONG});
  check(o2.status === 200 || o2.status === 201, 'setup: a second organisation with a long name ' + o2.status + ' ' + (o2.error || ''));

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };
  const signIn = ev => ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);

  // ================= #6130: Settings > Account, Notifications, My colour (English browser)
  await ffEn(async ({ev, nav, cmd, ctx, shot}) => {
    const size = (w, h) => cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
    await size(1280, 900);
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await signIn(ev);
    await nav(B);
    check(await ready(ev, `typeof settingsModal === 'function' && !!document.querySelector('#view') && !!(S.booted && S.me && S.me.id)`, 150), 'the app is up');
    // a slow Mac under load: the dialog is opened again once if it did not come up (the state is waited for, not a time)
    const openAcc = async () => {
      for (let k = 0; k < 2; k++) {
        await ev(`(() => { document.querySelectorAll('.modal').forEach(m => m.remove()); settingsModal('account'); return 1; })()`);
        if (await ready(ev, `!!document.querySelector('.smodal [data-pane="account"] #a-name')`, 100)) { await ev(OPEN_ALL); return true; }
      }
      return false;
    };
    check(await openAcc(), '#6130: Settings > Account opens');
    const A = JSON.parse(await ev(`JSON.stringify((() => { const p = document.querySelector('.smodal [data-pane="account"]');
      const pos = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & 4));
      const who = p.querySelector('.acwho'), out = who?.querySelector('[data-acc="logout"]'), name = who?.querySelector('.acct b');
      const r1 = out?.getBoundingClientRect(), r2 = name?.getBoundingClientRect(), sto = p.querySelector('#s-storage-h, #s-sync-h');
      return { order: pos(p.querySelector('#s-account-h'), p.querySelector('#a-name')) && (!p.querySelector('#a-cur') || pos(p.querySelector('#a-name'), p.querySelector('#a-cur')))
          && pos(p.querySelector('#s-ses-h'), sto) && pos(sto, p.querySelector('details.sdev')),
        topOut: !!out, sameRow: r1 && r2 ? Math.abs((r1.top + r1.height / 2) - (r2.top + r2.height / 2)) : 99,
        lastOut: !![...p.querySelectorAll('[data-acc="logout"]')].pop()?.closest('.alogout'),
        adv: p.querySelector('details.sdev > summary')?.textContent.trim() || '', sto: p.querySelector('#s-storage-h')?.closest('.sfold, [data-pane]')?.querySelector('.stoq')?.textContent || '', q: S.storage || null }; })())`));
    check(A.order, '#6130: Profile, then the password and the sessions, then storage before "For advanced users"');
    check(A.topOut && A.sameRow < 24 && A.lastOut, `#6130: Sign out next to the name (${A.sameRow}) and still at the very end`);
    check(A.adv === 'For advanced users', '#6130: "For advanced users" instead of "Advanced · for developers": ' + A.adv);
    if (A.q && !A.q.limit) check(/No files stored yet, no storage limit|in use, no storage limit/.test(A.sto) && !/0 B/.test(A.sto), '#6130: storage in plain words: ' + A.sto);
    else check(!/no limit/.test(A.sto), '#6130: storage with a limit: ' + A.sto);
    // the sessions: this script's one is "Program / script"
    check(await ready(ev, `document.querySelectorAll('.smodal #s-ses .sesrow').length >= 2`), '#6130: the sessions are listed');
    const ses = JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('.smodal #s-ses .sesrow b')].map(b => b.textContent))`));
    check(ses.includes('Program / script') && !ses.some(t => /^node\b/i.test(t)), '#6130: the script\'s session is "Program / script", no raw "node": ' + ses.join(' | '));
    // passkeys over http on an IP: the everyday sentence visible, the technical one only folded
    check(await ready(ev, `!!document.querySelector('.smodal #s-2fa [data-tfa="pk-add"]')`), '#6130: the two-factor part is drawn');
    const pk = JSON.parse(await ev(`JSON.stringify((() => { const b = document.querySelector('.smodal #s-2fa'); const vis = [...b.querySelectorAll('.shint')].filter(x => !x.closest('details.acadv')).map(x => x.textContent).join(' ');
      return {vis, fold: b.querySelector('details.acadv')?.textContent || '', sum: b.querySelector('details.acadv > summary')?.textContent || ''}; })())`));
    check(/Passkeys cannot be used on this address or in this browser\./.test(pk.vis) && !/HTTPS|IP address/.test(pk.vis), '#6130: the passkey hint in everyday words: ' + pk.vis.slice(0, 160));
    // (#7230): the server admin's fold is called "For server admins" - "For advanced users" stands once per tab (#6129)
    check(pk.sum === 'For server admins' && /HTTPS/.test(pk.fold), '#6130: the HTTPS / IP details folded for the server admin: ' + pk.sum);
    await shot('p21391b-account-desktop.png');

    // ---- phone: the password fields one under the other, the placeholder whole
    await size(360, 740);
    check(await openAcc(), '#6130: phone: Account opens');
    const P = JSON.parse(await ev(`JSON.stringify((() => { const a = document.querySelector('#a-cur'), b = document.querySelector('#a-new'); if (!a || !b) return null;
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(), cs = getComputedStyle(a), c = document.createElement('canvas').getContext('2d');
      c.font = cs.font || (cs.fontSize + ' ' + cs.fontFamily);
      const room = el => el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft) - parseFloat(getComputedStyle(el).paddingRight);
      return {stacked: rb.top >= ra.bottom - 1, aw: ra.width, ar: ra.right, br: rb.right, vw: innerWidth, fitA: c.measureText(a.placeholder).width <= room(a) + 1, fitB: c.measureText(b.placeholder).width <= room(b) + 1, sw: document.querySelector('.smodal .sbody, .smodal')?.scrollWidth <= innerWidth + 1}; })())`));
    check(P && P.stacked && P.ar <= P.vw && P.br <= P.vw, '#6130: phone: the password fields one under the other, inside the window ' + JSON.stringify(P));
    check(P && P.fitA && P.fitB, '#6130: phone: "current password" / "new password" are not cut ' + JSON.stringify(P));
    await ev(`(() => { document.querySelector('.smodal #a-cur').scrollIntoView({block: 'center'}); return 1; })()`);
    await shot('p21391b-account-phone-password.png');

    // ---- Notifications: everyday words
    await size(1280, 900);
    await ev(`(() => { document.querySelectorAll('.modal').forEach(m => m.remove()); settingsModal('notify'); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.smodal [data-pane="notify"] #s-ntfy')`), '#6130: Notifications open');
    await ev(OPEN_ALL);
    const N = JSON.parse(await ev(`JSON.stringify((() => { const p = document.querySelector('.smodal [data-pane="notify"]'), nt = p.querySelector('#s-ntfy');
      const clone = p.cloneNode(true); clone.querySelectorAll('details.acadv').forEach(d => d.remove());
      return {opts: [...p.querySelectorAll('#s-pushch option')].map(o => o.textContent), h: nt.querySelector('h4')?.textContent || '',
        lab: nt.querySelector('.row > label')?.textContent || '', vis: clone.textContent, fold: nt.querySelector('details.acadv')?.textContent || ''}; })())`));
    if (N.opts.length) check(N.opts.join('|') === 'Browser notification|Notification app|Both', '#6130: the channel choice in everyday words: ' + N.opts.join('|'));
    check(N.h === 'Notification app' && N.lab === 'Channel name', `#6130: "Notification app" and "Channel name": ${N.h} | ${N.lab}`);
    check(!/\bTopic\b|Web Push|ntfy topic/.test(N.vis), '#6130: no "Topic" / "Web Push" outside "For advanced users": ' + ((N.vis.match(/.{0,40}(\bTopic\b|Web Push|ntfy topic).{0,40}/) || [''])[0]));
    check(/server .*topic as above/.test(N.fold), '#6130: the ntfy server and topic folded under "For advanced users"');
    // Tasks by e-mail on a server without mail: the plain sentence, KALMIDO_* only folded (server admin)
    const M = JSON.parse(await ev(`JSON.stringify((() => { const d = document.createElement('div'); d.innerHTML = mailHtml({enabled: false, lists: []}); const f = d.querySelector('details.acadv'); const vis = d.cloneNode(true); vis.querySelectorAll('details').forEach(x => x.remove()); return {vis: vis.textContent, fold: f?.textContent || ''}; })())`));
    check(/Not set up on this server yet/.test(M.vis) && !/KALMIDO_|README/.test(M.vis) && /KALMIDO_MAIL_ADDRESS/.test(M.fold), '#6130: e-mail: server details only folded: ' + M.vis.trim().slice(0, 120));

    // ---- Organisation > My colour: the long name whole, the swatches inside the pane
    for (const [w, h] of [[820, 1000], [360, 740]]) {
      await size(w, h);
      await ev(`(() => { document.querySelectorAll('.modal').forEach(m => m.remove()); settingsModal('org'); return 1; })()`);
      check(await ready(ev, `document.querySelectorAll('.smodal .wsp-pane .wsp-row').length >= 3`), `#6130: ${w}px: My colour with its rows`);
      await ev(OPEN_ALL);
      const C = JSON.parse(await ev(`JSON.stringify((() => { const pane = document.querySelector('.smodal .wsp-pane'), pr = pane.closest('.spane').getBoundingClientRect();
        const rows = [...pane.querySelectorAll('.wsp-row')]; const long = rows.find(r => r.textContent.includes(${JSON.stringify(LONG)}));
        const nm = long?.querySelector('.wsp-nm > span:last-child') || long?.querySelector('.wsp-nm');
        const outs = rows.flatMap(r => [...r.querySelectorAll('.colors button')]).filter(b => b.getBoundingClientRect().right > pr.right + 1).length;
        return {found: !!long, cut: nm ? nm.scrollWidth > nm.clientWidth + 1 : true, outs, n: rows.length}; })())`));
      check(C.found && !C.cut, `#6130: ${w}px: the long workspace name is shown whole ` + JSON.stringify(C));
      check(C.outs === 0, `#6130: ${w}px: no colour swatch runs out of the pane ` + JSON.stringify(C));
      await ev(`(() => { document.querySelector('.smodal .wsp-pane').scrollIntoView({block: 'start'}); return 1; })()`);
      await shot(`p21391b-mycolour-${w}.png`);
    }
  });

  console.log(`p21391_b_konto_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
