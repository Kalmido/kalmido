// 2.1180.0 A UI test (#6130 the Account tab in groups, everyday words in Notifications; #6134 the sign-in page in the browser's language).
// kalmido-suite: fresh
// Own container (start.sh), Firefox. Invented names only.
// #6134 - a German browser (intl.accept_languages de-DE,de), nothing remembered on the device:
// - the page before the sign-in speaks German (Benutzername, Angemeldet bleiben, Anmelden, the line under the card, lang="de");
//   uiLang() itself falls back to the browser's language (red without the fix: 'en'), a language Kalmido lacks -> English,
//   fr-CA -> fr, a remembered language still wins
// #6130 - Settings > Account at 1280 and 360 px:
// - a jump bar with three groups (Profile · Security and sign-in · Devices and data); a tap brings that group's heading to the top
//   and gives it the focus; Storage sits in "Devices and data"; Sign out next to the name and still at the very end
// - a session of a script (this test's node fetch) is "Program / script", never "node"
// - "No files stored yet, no storage limit" instead of "0 B used · no limit"
// - phone: the two password fields one under the other, each showing its whole placeholder
// - "For advanced users" instead of "Advanced · for developers"; the passkey hint in everyday words, the HTTPS / IP details
//   folded under "For advanced users" (server admin)
// - Notifications: Browser notification / Notification app / Both, the heading "Notification app", "Channel name", no "Topic" or
//   "Web Push" outside "For advanced users"; Tasks by e-mail: KALMIDO_* only folded
// - Organisation > My colour: a long workspace name is not cut, the swatches wrap inside the pane at 820 and 360 px
// P21180A_NOSTART=1 = the server already runs.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const ffDe = require('./ff')({tag: 'p21180_a_konto_ui', check, shots: 'P21180A_SHOTS', prefs: [['intl.accept_languages', 'de-DE,de']]});
const ffEn = require('./ff')({tag: 'p21180_a_konto_ui', check, shots: 'P21180A_SHOTS', allWs: true});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21180A_NOSTART && !process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const LONG = 'Kurzfilmfestival Musterstadt e. V. – Programmkommission';

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

  // ================= #6134: a German browser, nothing remembered
  await ffDe(async ({ev, nav, cmd, ctx, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    await nav(B);
    check(await ready(ev, `!!document.querySelector('.authscreen #auth-form')`), '#6134: the sign-in page is up');
    check(await ready(ev, `!!document.querySelector('.authscreen figure.qd .qdo')`), '#6134: the quote of the day is in');
    const L = JSON.parse(await ev(`JSON.stringify((() => { const el = document.querySelector('.authscreen'); return {
      nav: navigator.languages.join(','), ui: uiLang(), code: I18N.code, lang: document.documentElement.lang,
      user: document.querySelector('label[for="au-user"]')?.textContent || '', pw: document.querySelector('label[for="au-pw"]')?.textContent || '',
      stay: document.querySelector('#au-rem')?.closest('label')?.textContent.trim() || '', btn: el.querySelector('.btn.pri')?.textContent.trim() || '',
      foot: getComputedStyle(el, '::after').content || '', qlang: el.querySelector('figure.qd .qdo')?.lang || '' }; })())`));
    check(/^de/.test(L.nav), '#6134: the browser asks for German: ' + L.nav);
    check(L.ui === 'de', '#6134: uiLang() without a remembered language = the browser\'s language: ' + L.ui);
    check(L.code === 'de' && L.lang === 'de', `#6134: the page speaks German (${L.code}, lang=${L.lang})`);
    check(L.user === 'Benutzername' && L.pw === 'Passwort' && L.stay === 'Angemeldet bleiben' && L.btn === 'Anmelden', `#6134: the fields and the button in German: ${L.user} | ${L.pw} | ${L.stay} | ${L.btn}`);
    check(/Aufgaben, Team und Büro an einem Ort\./.test(L.foot), '#6134: the line under the card in German: ' + L.foot);
    check(L.qlang !== 'en' || /[äöüß]/.test(await ev(`document.querySelector('.authscreen figure.qd .qdo').textContent`)), '#6134: the quote is not the English one: ' + L.qlang);
    await shot('p21180a-login-de.png');
    // the rule itself: a language Kalmido lacks -> English, a region drops (fr-CA -> fr), a remembered language wins
    const pick = langs => ev(`(() => { const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'languages'); Object.defineProperty(navigator, 'languages', {configurable: true, get: () => ${JSON.stringify(langs)}}); try { return i18nBrowserLang(); } finally { delete navigator.languages; Object.defineProperty(Navigator.prototype, 'languages', d); } })()`);
    check(await pick(['ja-JP', 'ko']) === 'en', '#6134: a language Kalmido lacks -> English');
    check(await pick(['fr-CA', 'de']) === 'fr', '#6134: fr-CA -> fr (the first one Kalmido has)');
    check(await pick(['pt-BR', 'nl-BE']) === 'nl', '#6134: the first one Kalmido has (nl)');
    check(await ev(`(() => { localStorage.setItem('tasks.lang', '"it"'); const v = uiLang(); localStorage.removeItem('tasks.lang'); return v; })()`) === 'it', '#6134: a remembered language still wins');
  });

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
        if (await ready(ev, `!!document.querySelector('.smodal [data-pane="account"] .acjump')`, 100)) return true;
      }
      return false;
    };
    check(await openAcc(), '#6130: Settings > Account opens with the jump bar');
    const A = JSON.parse(await ev(`JSON.stringify((() => { const p = document.querySelector('.smodal [data-pane="account"]');
      const hs = [...p.querySelectorAll('h3.acgh')], pos = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & 4));
      const who = p.querySelector('.acwho'), out = who?.querySelector('[data-acc="logout"]'), name = who?.querySelector('.acct b');
      const r1 = out?.getBoundingClientRect(), r2 = name?.getBoundingClientRect();
      return { jump: [...p.querySelectorAll('.acjump [data-acj]')].map(b => b.textContent.trim()), heads: hs.map(h => h.textContent.trim()),
        stoInData: pos(p.querySelector('#a-g-data'), p.querySelector('#s-storage-h, #s-sync-h')) && pos(p.querySelector('#a-g-sec'), p.querySelector('#a-g-data')),
        pwInSec: !p.querySelector('#a-cur') || (pos(p.querySelector('#a-g-sec'), p.querySelector('#a-cur')) && pos(p.querySelector('#a-cur'), p.querySelector('#a-g-data'))),
        topOut: !!out, sameRow: r1 && r2 ? Math.abs((r1.top + r1.height / 2) - (r2.top + r2.height / 2)) : 99,
        lastOut: !!p.lastElementChild?.querySelector?.('[data-acc="logout"]') || p.lastElementChild?.classList.contains('alogout'),
        adv: p.querySelector('details.sdev > summary')?.textContent.trim() || '', sto: p.querySelector('#s-storage-h + .row')?.textContent || '', q: S.storage || null }; })())`));
    check(A.jump.join('|') === 'Profile|Security and sign-in|Devices and data', '#6130: the jump bar has the three groups: ' + A.jump.join('|'));
    check(A.heads.join('|') === 'Profile|Security and sign-in|Devices and data', '#6130: three group headings in that order: ' + A.heads.join('|'));
    check(A.stoInData && A.pwInSec, '#6130: password in "Security and sign-in", storage in "Devices and data"');
    check(A.topOut && A.sameRow < 24 && A.lastOut, `#6130: Sign out next to the name (${A.sameRow}) and still at the very end`);
    check(A.adv === 'For advanced users', '#6130: "For advanced users" instead of "Advanced · for developers": ' + A.adv);
    if (A.q && !A.q.limit) check(/No files stored yet, no storage limit|in use, no storage limit/.test(A.sto) && !/0 B/.test(A.sto), '#6130: storage in plain words: ' + A.sto);
    else check(!/no limit/.test(A.sto), '#6130: storage with a limit: ' + A.sto);
    // the jump: "Devices and data" comes to the top of the pane and gets the focus
    await ev(`(() => { document.querySelector('.smodal .acjump [data-acj="data"]').click(); return 1; })()`);
    // the last group is short: the heading comes to the top, or the pane is scrolled as far as it goes (the heading then in view)
    const JUMP = `(() => { const h = document.querySelector('.smodal #a-g-data'); let sc = h.parentElement; while (sc && !(sc.scrollHeight > sc.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
      const r = sc?.getBoundingClientRect(), t = r ? h.getBoundingClientRect().top - r.top : -999, end = sc ? sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2 : false;
      return {focus: document.activeElement === h, t: Math.round(t), end, top: sc ? Math.round(sc.scrollTop) : -1, sc: sc ? sc.className : ''}; })()`;
    const J0 = await ev(`JSON.stringify(${JUMP})`);
    await ready(ev, `(() => { const j = ${JUMP}; return j.focus && j.t >= -2 && (j.t < 80 || j.end); })()`, 25);
    const J = JSON.parse(await ev(`JSON.stringify(${JUMP})`));
    check(J.focus && J.t >= -2 && (J.t < 80 || (J.end && J.top > 0)), '#6130: the jump brings "Devices and data" to the top (or scrolls to the end) and focuses it ' + JSON.stringify(J) + ' before the wait: ' + J0);
    // the sessions: this script's one is "Program / script"
    check(await ready(ev, `document.querySelectorAll('.smodal #s-ses .sesrow').length >= 2`), '#6130: the sessions are listed');
    const ses = JSON.parse(await ev(`JSON.stringify([...document.querySelectorAll('.smodal #s-ses .sesrow b')].map(b => b.textContent))`));
    check(ses.includes('Program / script') && !ses.some(t => /^node\b/i.test(t)), '#6130: the script\'s session is "Program / script", no raw "node": ' + ses.join(' | '));
    // passkeys over http on an IP: the everyday sentence visible, the technical one only folded
    check(await ready(ev, `!!document.querySelector('.smodal #s-2fa [data-tfa="pk-add"]')`), '#6130: the two-factor part is drawn');
    const pk = JSON.parse(await ev(`JSON.stringify((() => { const b = document.querySelector('.smodal #s-2fa'); const vis = [...b.querySelectorAll('.shint')].filter(x => !x.closest('details')).map(x => x.textContent).join(' ');
      return {vis, fold: b.querySelector('details.acadv')?.textContent || '', sum: b.querySelector('details.acadv > summary')?.textContent || ''}; })())`));
    check(/Passkeys cannot be used on this address or in this browser\./.test(pk.vis) && !/HTTPS|IP address/.test(pk.vis), '#6130: the passkey hint in everyday words: ' + pk.vis.slice(0, 160));
    check(pk.sum === 'For advanced users' && /HTTPS/.test(pk.fold), '#6130: the HTTPS / IP details folded for the server admin');
    await shot('p21180a-account-desktop.png');

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
    await shot('p21180a-account-phone-password.png');

    // ---- Notifications: everyday words
    await size(1280, 900);
    await ev(`(() => { document.querySelectorAll('.modal').forEach(m => m.remove()); settingsModal('notify'); return 1; })()`);
    check(await ready(ev, `!!document.querySelector('.smodal [data-pane="notify"] #s-ntfy')`), '#6130: Notifications open');
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
      const C = JSON.parse(await ev(`JSON.stringify((() => { const pane = document.querySelector('.smodal .wsp-pane'), pr = pane.closest('.spane').getBoundingClientRect();
        const rows = [...pane.querySelectorAll('.wsp-row')]; const long = rows.find(r => r.textContent.includes(${JSON.stringify(LONG)}));
        const nm = long?.querySelector('.wsp-nm > span:last-child') || long?.querySelector('.wsp-nm');
        const outs = rows.flatMap(r => [...r.querySelectorAll('.colors button')]).filter(b => b.getBoundingClientRect().right > pr.right + 1).length;
        return {found: !!long, cut: nm ? nm.scrollWidth > nm.clientWidth + 1 : true, outs, n: rows.length}; })())`));
      check(C.found && !C.cut, `#6130: ${w}px: the long workspace name is shown whole ` + JSON.stringify(C));
      check(C.outs === 0, `#6130: ${w}px: no colour swatch runs out of the pane ` + JSON.stringify(C));
      await ev(`(() => { document.querySelector('.smodal .wsp-pane').scrollIntoView({block: 'start'}); return 1; })()`);
      await shot(`p21180a-mycolour-${w}.png`);
    }
  });

  console.log(`p21180_a_konto_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
