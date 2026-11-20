// 2.504.0 (#4084), jsdom, invented data only: the test window of tests/boot.js has CSS.escape and CSS.supports
// - escape follows the CSSOM rules and the app's selectors built with it find their element in jsdom
// - supports leaves the vendored libraries on the path they took without a CSS object
// - #6365: boottheme.js is the first script, blocking in <head>, and alone sets theme, accent, pack, font size and
//   html.rebooting from the device settings (before the loading screen is drawn); the app window keeps them
// kalmido-suite: fresh
const {boot, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const fs = require('fs'), path = require('path'), {JSDOM} = require('jsdom');
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};

(async () => {
  // ================= #6365 the look before the first picture
  const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');
  const head = html.slice(0, html.indexOf('</head>')), firstScript = (html.match(/<script\b[^>]*>/) || [''])[0];
  check(firstScript === '<script src="/static/js/boottheme.js">', '#6365: boottheme.js is the first script of the page, without defer: ' + firstScript);
  check(head.includes(firstScript) && head.indexOf(firstScript) > head.indexOf('name="theme-color"'), '#6365: it stands in <head>, after the theme-color meta it sets');
  const btSrc = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'boottheme.js'), 'utf8');
  const look = (ls, booted, light) => {
    const dom = new JSDOM(head + '</head><body><div id="boot"></div></body>', {url: B, runScripts: 'outside-only'});
    const w = dom.window;
    w.matchMedia = q => ({matches: !!light && /light/.test(q), addEventListener() {}});
    for (const [k, v] of Object.entries(ls)) w.localStorage.setItem('tasks.' + k, JSON.stringify(v));
    if (booted) w.sessionStorage.setItem('kalmido.booted', '1');
    w.eval(btSrc);
    const h = w.document.documentElement;
    const r = {theme: h.dataset.theme, accent: h.dataset.accent, pack: h.dataset.pack, fsize: h.dataset.fsize, ui: h.style.getPropertyValue('--ui'),
      small: h.classList.contains('ui-small'), reboot: h.classList.contains('rebooting'), meta: w.document.querySelector('meta[name="theme-color"]').getAttribute('content')};
    w.close(); return r;
  };
  let lk = look({theme: 'light', accent: 'violet', pack: 'paper', fsize: 120}, true, false);
  check(lk.theme === 'light' && lk.meta === '#f8f8f9', '#6365: a light choice on a dark system is light at once ' + JSON.stringify(lk));
  check(lk.accent === 'violet' && lk.pack === 'paper', '#6365: accent and theme pack before the first picture ' + JSON.stringify(lk));
  check(lk.fsize === 'custom' && lk.ui === '1.2' && !lk.small, '#6365: the font size (120 %) before the first picture ' + JSON.stringify(lk));
  check(lk.reboot, '#6365 / #1213: a reload in the session gets html.rebooting from the first script (no logo flash)');
  lk = look({theme: 'dark', fsize: 's'}, false, true);
  check(lk.theme === 'dark' && lk.meta === '#16171a' && lk.fsize === 's' && lk.small && !lk.reboot && lk.accent === undefined, '#6365: dark on a light system, an old named size, no accent stored, cold start shows the loading screen ' + JSON.stringify(lk));
  lk = look({accent: 'x" onload="', pack: 1}, false, true);
  check(lk.theme === 'auto' && lk.meta === '#f8f8f9' && lk.accent === undefined && lk.pack === undefined && lk.fsize === 'm', '#6365: nothing stored = auto (follows the system), a broken accent / pack is left to icons.js ' + JSON.stringify(lk));

  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const w = await boot({user: 'alice'}), d = w.document;
  check(w.eval(`typeof CSS`) === 'object', 'the app sees a CSS object');
  check(d.documentElement.dataset.theme && d.documentElement.dataset.fsize && w.eval(`typeof applyTheme === 'function' && typeof fsPct === 'function'`), '#6365: the started app keeps theme and font size, icons.js applyTheme / fsPct still there');
  const esc = v => w.eval(`CSS.escape(${JSON.stringify(v)})`);
  for (const [v, want] of [['abc-_9', 'abc-_9'], ['1a', '\\31 a'], ['-1a', '-\\31 a'], ['-', '\\-'], ['--x', '--x'], ['a b', 'a\\ b'], ['a"b', 'a\\"b'], ['a:b.c#d', 'a\\:b\\.c\\#d'],
    ['a\\b', 'a\\\\b'], ['a\nb', 'a\\a b'], ['a\x7fb', 'a\\7f b'], ['a\0b', 'a�b'], ['äß€', 'äß€'], ['', '']]) check(esc(v) === want, `CSS.escape(${JSON.stringify(v)}) = ${JSON.stringify(esc(v))}`);
  check(w.eval(`CSS.escape(12)`) === '\\31 2', 'CSS.escape takes a number as text');

  // the way the app uses it: inside an attribute selector and after a #
  const el = d.createElement('i'); d.body.append(el);
  for (const v of ['private', 'org:1', 'a b', 'a"b', 'x.y', 'ä']) {
    el.dataset.cssProbe = v;
    check(d.querySelector(`[data-css-probe="${esc(v)}"]`) === el, `attribute selector finds ${v}`);
  }
  el.id = 'os-name:1';
  check(d.querySelector('#' + esc(el.id)) === el, 'id selector finds an id with a colon');
  el.remove();

  const sup = (...a) => w.eval(`CSS.supports(${a.map(x => JSON.stringify(x)).join(', ')})`);
  check(sup('backdrop-filter', 'blur(1px)') === false, 'pdf.js: no backdrop filter, as without a CSS object');
  check(sup('color', 'red') === true, 'mermaid: a colour jsdom knows counts');
  check(sup('color', 'not-a-colour') === false, 'mermaid: a text that is no colour does not');
  check(sup('(display: grid)') === false, 'the one-argument form answers false');
  w.close();
  console.log(`p2504_a_css_boot_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
