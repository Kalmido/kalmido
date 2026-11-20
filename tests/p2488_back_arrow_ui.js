// kalmido-suite:
// 2.488.0 A UI test, own container (start.sh), Firefox. Invented data only.
// - #3988: a Back arrow (greyed out at the start, active after a change of view, click = history.back(), greyed out again at
//   the first view); Alt+Left goes back; Alt+Left inside an input does not
// - #7395 (rewritten): Back and Forward are two arrows right before the bell (the head bar #kbar on a computer, #top on a phone),
//   no arrow left of the title any more; Forward greyed out at both ends, active after Back, empty again after Back + a new
//   view; an open overlay is closed first by Back; Alt+Right / the mouse's Forward button go forward; the tooltips name the
//   keys; Settings > Appearance "Back and forward arrows in the header": on by default on a computer, off by default on a
//   phone, switched on there they sit next to the bell and nothing overlaps at 320 px; off = no arrows, the keys still work
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p2488_back_arrow_ui', check, shots: 'P2488A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P2488A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CA = await login('alice');
  const call = async (method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}); return r.json().catch(() => ({})); };
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab'});
  const lid = (await call('POST', '/api/lists', {name: 'Project one'})).id;
  const lid2 = (await call('POST', '/api/lists', {name: 'Project two'})).id;
  const lid3 = (await call('POST', '/api/lists', {name: 'Project three'})).id;

  const ready = async (ev, expr, n = 60) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  await firefox(async o => {
    const {cmd, ev, ctx, nav} = o;
    await nav(B + 'static/icon.svg');
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'ff: login');
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1200, height: 800}});
    await nav(B + '#today');
    const btn = `document.querySelector('[data-act="nav-back"]')`, fwd = `document.querySelector('[data-act="nav-fwd"]')`;
    const route = k => ready(ev, `S.route.key === '${k}' && !!${btn}`);
    const off = () => ev(`${btn}.disabled`);
    const fOff = () => ev(`${fwd}.disabled`);
    const key = (init, k = 'ArrowLeft') => ev(`(() => { const e = new KeyboardEvent('keydown', {key: '${k}', altKey: true, bubbles: true, cancelable: true}); (${init}).dispatchEvent(e); return e.defaultPrevented; })()`);
    check(await route('today'), 'the arrows are in the head bar');
    check(await off() === true && await fOff() === true, 'Back and Forward greyed out at the start');
    // #7395: right before the bell, one place only, none left of the title
    check(await ev(`document.querySelectorAll('[data-act="nav-back"]').length === 1 && document.querySelectorAll('[data-act="nav-fwd"]').length === 1`), '#7395: the arrows exist once');
    check(await ev(`(() => { const g = ${btn}.closest('.bnnav'), b = g?.nextElementSibling; return !!b && b.matches('[data-act="bell-pop"]') && ${fwd}.closest('.bnnav') === g && ${btn}.nextElementSibling === ${fwd}; })()`), '#7395: Back, Forward, then the bell');
    check(await ev(`!document.querySelector('#top > .bnback, #top > [data-act="nav-back"]') && (() => { const h = document.querySelector('#top h1'); return !h || ${btn}.getBoundingClientRect().left > h.getBoundingClientRect().right; })()`), '#7395: no arrow left of the title');
    check(/Back/.test(await ev(`${btn}.title`)) && /Alt|⌘/.test(await ev(`${btn}.title`)), 'tooltip with the shortcut: ' + await ev(`${btn}.title`));
    check(/Forward/.test(await ev(`${fwd}.title`)) && /Alt|⌘/.test(await ev(`${fwd}.title`)) && await ev(`${fwd}.getAttribute('aria-label')`) === await ev(`${fwd}.title`), '#7395: Forward named with its shortcut: ' + await ev(`${fwd}.title`));

    // a change of view
    await ev(`location.hash = '#l/${lid}'`);
    check(await route(`l:${lid}`), 'the project opens');
    check(await ready(ev, `${btn}.disabled === false`, 12) && await fOff() === true, 'Back active after a change of view, Forward still greyed out');
    await ev(`${btn}.click()`);
    check(await route('today'), 'a click goes back');
    check(await ready(ev, `${btn}.disabled === true`, 12), 'greyed out again at the first view');
    check(await ready(ev, `${fwd}.disabled === false`, 12), '#7395: after Back, Forward is active');
    await ev(`${fwd}.click()`);
    check(await route(`l:${lid}`), '#7395: Forward goes to the view again');
    check(await ready(ev, `${fwd}.disabled === true && ${btn}.disabled === false`, 12), '#7395: at the newest view Forward is greyed out again');
    await ev(`${fwd}.click()`);  // disabled: nothing
    await sleep(300);
    check(await ev(`location.hash`) === '#l/' + lid, '#7395: a greyed out Forward does nothing');
    // Back, then a new view: nothing ahead any more
    await ev(`${btn}.click()`); await route('today');
    await ready(ev, `${fwd}.disabled === false`, 12);
    await ev(`location.hash = '#l/${lid2}'`); await route(`l:${lid2}`);
    check(await ready(ev, `${fwd}.disabled === true`, 12), '#7395: after Back and a new view, Forward is empty');
    await ev(`${btn}.click()`);
    check(await route('today'), 'Back from the new view');
    check(await ready(ev, `${btn}.disabled === true`, 12), 'greyed out at the first view');
    await ev(`${btn}.click()`);  // disabled: nothing
    await sleep(300);
    check(await ev(`location.hash`) === '#today', 'greyed out arrow does nothing');

    // Alt+Left / Alt+Right
    await ev(`location.hash = '#l/${lid}'`);
    await route(`l:${lid}`);
    check(await key('document.body') === true, 'Alt+Left is taken over (no second Back from the browser)');
    check(await route('today'), 'Alt+Left goes back');
    check(await ready(ev, `${btn}.disabled === true`, 12), 'greyed out after Alt+Left');
    check(await key('document.body') === true && await ev(`location.hash`) === '#today', 'Alt+Left at the start stays in Kalmido');
    check(await key('document.body', 'ArrowRight') === true, '#7395: Alt+Right is taken over');
    check(await route(`l:${lid}`), '#7395: Alt+Right goes forward');
    check(await key('document.body', 'ArrowRight') === true && await ev(`location.hash`) === '#l/' + lid, '#7395: Alt+Right at the newest view stays');

    // mouse Back / Forward buttons
    await ev(`document.body.dispatchEvent(new MouseEvent('mouseup', {button: 3, bubbles: true, cancelable: true}))`);
    check(await route('today'), 'the mouse Back button goes back');
    await ev(`document.body.dispatchEvent(new MouseEvent('mouseup', {button: 4, bubbles: true, cancelable: true}))`);
    check(await route(`l:${lid}`), '#7395: the mouse Forward button goes forward');

    // inside an input: not taken over
    await ev(`(() => { const i = document.createElement('input'); i.id = 'bn-in'; document.body.appendChild(i); i.focus(); })()`);
    check(await key(`document.getElementById('bn-in')`) === false, 'Alt+Left in an input is left alone');
    await sleep(300);
    check(await ev(`location.hash`) === '#l/' + lid, 'no step back from an input');
    await ev(`document.getElementById('bn-in').remove()`);

    // an overlay (a dialog's own history entry) is closed first by Back, the view stays
    await ev(`location.hash = '#l/${lid3}'`); await route(`l:${lid3}`);
    await ev(`history.pushState({f8d: 1}, '', location.href); bnSync(); 1`);
    check(await ready(ev, `${btn}.disabled === false && ${fwd}.disabled === true`, 12), '#7395: with an overlay open: Back active, Forward greyed out');
    await ev(`${btn}.click()`);
    await sleep(500);
    check(await ev(`location.hash`) === '#l/' + lid3 && await ev(`!(history.state && history.state.f8d)`), '#7395: Back closes the overlay first, the view stays');
    check(await ready(ev, `${fwd}.disabled === true`, 12), '#7395: a closed overlay is nothing to go forward to');

    // 2.488.0 (#3988, self-review): history.length stops at 50 in Firefox / WebKit - a new view must still count as a step
    // (before, every view after the 50th looked like a step back and the arrow greyed out)
    await nav(B + 'static/icon.svg');  // a new page load: the first view is the start again (a hash-only nav would be a step)
    await nav(B + '#today');
    await route('today');
    await ev(`(Object.defineProperty(history, 'length', {configurable: true, get: () => 50}), true)`);
    await ev(`location.hash = '#l/${lid}'`);
    await route(`l:${lid}`);
    await ev(`location.hash = '#l/${lid2}'`);
    check(await route(`l:${lid2}`), 'a third view opens');
    check(await ready(ev, `${btn}.disabled === false`, 12), 'active with a full history (length frozen at 50)');
    await ev(`history.back()`);
    check(await route(`l:${lid}`) && await ready(ev, `${btn}.disabled === false`, 12), 'one step back: still active');
    await ev(`history.back()`);
    check(await route('today') && await ready(ev, `${btn}.disabled === true`, 12), 'two steps back: greyed out at the first view');
    // a pushState to a new hash (the note view does that) is a new view
    await ev(`history.pushState(null, '', '#l/${lid}')`);
    check(await ready(ev, `${btn}.disabled === false`, 12), 'pushState to a new hash makes the arrow active');
    check(await ready(ev, `${fwd}.disabled === true`, 12), '#7395: and cuts what was ahead');
    await ev(`history.back()`);
    check(await ready(ev, `${btn}.disabled === true`, 12), 'and Back from it greys it out again');
    await ev(`delete history.length`);

    // the setting: off = no arrows, the keys still work; the account's appearance
    await ev(`loadModule('settings').then(() => { settingsModal('look'); return 1; })`);
    await ready(ev, `!!document.querySelector('#s-navarrows')`);
    check(await ev(`document.querySelector('#s-navarrows').checked`) === true, '#7395: the switch is on by default on a computer');
    await ev(`(() => { const c = document.querySelector('#s-navarrows'); c.click(); return 1; })()`);
    check(await ready(ev, `LS.get('navArrows', null) === false && !${btn}`, 20), '#7395: switched off: no arrows');
    await ev(`document.querySelectorAll('.smodal').forEach(m => m.remove()); 1`);
    await ev(`location.hash = '#l/${lid3}'`); await ready(ev, `S.route.key === 'l:${lid3}'`);
    await key('document.body');
    check(await ready(ev, `S.route.key !== 'l:${lid3}'`, 20), '#7395: off: Alt+Left still goes back');
    const lk = await (async () => { for (let i = 0; i < 30; i++) { const s = (await call('GET', '/api/state')).settings || {}; if (/"navArrows":false/.test(s.look || '')) return true; await sleep(300); } return false; })();
    check(lk, '#7395: the choice is the account\'s appearance (setting look)');
    await ev(`LS.del('navArrows'); render(); 1`);

    // the phone: off by default, switched on next to the bell, nothing overlaps at 320 px
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + '#today');
    await ready(ev, `!!S.booted && !!document.querySelector('#top .menu')`);
    check(await ev(`!${btn} && !${fwd}`), '#7395: the phone has no arrows by default');
    await ev(`LS.set('navArrows', true); render(); 1`);
    await ev(`location.hash = '#l/${lid}'`);
    check(await ready(ev, `S.route.key === 'l:${lid}' && !!document.querySelector('#top [data-act="nav-back"]')`), '#7395: switched on, the phone shows them in its header');
    check(await ev(`(() => { const b = document.querySelector('#top .bnnav')?.nextElementSibling; return !!b && b.matches('[data-act="bell-pop"]'); })()`), '#7395: on the phone right before the bell too');
    await ev(`document.querySelector('#top [data-act="nav-back"]').click()`);
    check(await ready(ev, `S.route.key === 'today'`, 20), '#7395: the phone\'s Back arrow goes back');
    for (const w of [390, 320]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: 800}});
      await ev(`location.hash = '#l/${lid2}'`); await ready(ev, `S.route.key === 'l:${lid2}'`); await sleep(400);
      const g = await ev(`(() => { const r = e => e && e.getBoundingClientRect(), t = document.querySelector('#top'), h = r(document.querySelector('#top h1')), a = r(document.querySelector('#top .bnnav')), b = r(document.querySelector('#top [data-act="bell-pop"]'));
        const vis = [...t.children].filter(e => e.getClientRects().length && getComputedStyle(e).display !== 'none').map(r);
        const hit = vis.some((x, i) => vis.some((y, j) => j > i && x.right > y.left + 1 && y.right > x.left + 1 && x.bottom > y.top + 1 && y.bottom > x.top + 1));
        return {h: h && Math.round(h.right), a: a && [Math.round(a.left), Math.round(a.right)], b: b && Math.round(b.left), sw: t.scrollWidth, cw: t.clientWidth, win: innerWidth, hit}; })()`);
      check(g.a && g.b != null && g.a[1] <= g.b + 1 && g.h <= g.a[0] + 1 && !g.hit && g.a[1] <= g.win, `#7395: ${w} px: title, arrows and bell side by side, nothing overlaps ${JSON.stringify(g)}`);
    }
  }, false);

  console.log(`p2488_back_arrow_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
