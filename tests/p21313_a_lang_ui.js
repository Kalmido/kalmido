// 2.1313.0 A UI test (#6134 the sign-in page in the browser's language).
// kalmido-suite: fresh
// Own container (start.sh), Firefox. Invented names only.
// A German browser (intl.accept_languages de-DE,de), nothing remembered on the device:
// - the page before the sign-in speaks German (Benutzername, Passwort, Angemeldet bleiben, Anmelden, lang="de");
//   uiLang() itself falls back to the browser's language (red without the fix: 'en'), a language Kalmido lacks -> English,
//   fr-CA -> fr, a remembered language still wins; signing in works from there
// freelancer-matrix: n/a (the page before the sign-in, no account yet)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const ffDe = require('./ff')({tag: 'p21313_a_lang_ui', check, shots: 'P21313A_SHOTS', prefs: [['intl.accept_languages', 'de-DE,de']]});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(200); } return false; };

  await ffDe(async ({ev, nav, cmd, ctx, shot}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    await nav(B);
    check(await ready(ev, `!!document.querySelector('.authscreen #auth-form')`), 'the sign-in page is up');
    check(await ready(ev, `I18N.code === 'de'`), 'the texts are loaded in German');
    const L = JSON.parse(await ev(`JSON.stringify((() => { const el = document.querySelector('.authscreen'); return {
      nav: navigator.languages.join(','), ui: uiLang(), code: I18N.code, lang: document.documentElement.lang,
      user: document.querySelector('label[for="au-user"]')?.textContent || '', pw: document.querySelector('label[for="au-pw"]')?.textContent || '',
      stay: document.querySelector('#au-rem')?.closest('label')?.textContent.trim() || '', btn: el.querySelector('.btn.pri')?.textContent.trim() || '' }; })())`));
    check(/^de/.test(L.nav), 'the browser asks for German: ' + L.nav);
    check(L.ui === 'de', 'uiLang() without a remembered language = the browser\'s language: ' + L.ui);
    check(L.code === 'de' && L.lang === 'de', `the page speaks German (${L.code}, lang=${L.lang})`);
    check(L.user === 'Benutzername' && L.pw === 'Passwort' && L.stay === 'Angemeldet bleiben' && L.btn === 'Anmelden', `the fields and the button in German: ${L.user} | ${L.pw} | ${L.stay} | ${L.btn}`);
    await shot('p21313a-login-de.png');
    // the rule itself: a language Kalmido lacks -> English, a region drops (fr-CA -> fr), a remembered language wins
    const pick = langs => ev(`(() => { const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'languages'); Object.defineProperty(navigator, 'languages', {configurable: true, get: () => ${JSON.stringify(langs)}}); try { return i18nBrowserLang(); } finally { delete navigator.languages; Object.defineProperty(Navigator.prototype, 'languages', d); } })()`);
    check(await pick(['ja-JP', 'ko']) === 'en', 'a language Kalmido lacks -> English');
    check(await pick(['fr-CA', 'de']) === 'fr', 'fr-CA -> fr (the first one Kalmido has)');
    check(await pick(['pt-BR', 'nl-BE']) === 'nl', 'the first one Kalmido has (nl)');
    check(await ev(`(() => { const k = I18N_LS_KEY, old = localStorage.getItem(k); localStorage.setItem(k, '"it"'); const v = uiLang(); if (old == null) localStorage.removeItem(k); else localStorage.setItem(k, old); return v; })()`) === 'it', 'a remembered language still wins');
    // usable: signing in from the German page leads into the app (the account's own language, English, takes over)
    await ev(`(() => { document.querySelector('#au-user').value = 'alice'; document.querySelector('#au-pw').value = 'password123'; document.querySelector('.authscreen .btn.pri').click(); return 1; })()`);
    check(await ready(ev, `typeof S !== 'undefined' && S.booted && !document.querySelector('.authscreen')`, 100), 'signing in from the German page leads into the app');
  });

  console.log(`p21313_a_lang_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
