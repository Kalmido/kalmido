// kalmido-suite: fresh
// 2.1368.0 B (#5525) UI test, Firefox, own container (start.sh), invented data only. A knowledge page as a presentation: "Present"
// is the first entry of the page's "…" and opens it over the whole window (wkpresent.js, loaded on the click); every "#" / "##"
// heading starts a slide (a "###" stays on its slide), text before the first heading is a title slide with the page's name. A
// person sees the slide's text in large type and "n / m"; arrow keys, End / Home and the ‹ › buttons leaf, Esc ends it and the
// page is there as before. A checkbox on a slide ticks nothing (the page's text stays). A read-only member presents the page too.
// On a phone a swipe leafs and the phone's Back ends the presentation (the page stays open). P21368B_SHOTS=dir: pictures.
// freelancer-matrix: n/a - nur Oberfläche (no route changed; the page lies in the organisation's space, rita may only read it)
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21368_b_wiki_present_ui', check, shots: 'P21368B_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (process.env.P21368B_NOSTART !== '1') execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const MODS = 'wiki,comments';
const BODY = 'Intro before any heading.\n\n# Opening\n\nWelcome **everyone**.\n\n## Story\n\n- one\n- [ ] two\n\n### Detail\n\nStays on the story slide.\n\n## End\n\nThanks for watching.\n';
// WebDriver key codes
const RIGHT = '', LEFT = '', HOME = '', END = '', ESC = '';

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const r = await fetch(B + 'api/auth/login', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', password: 'password123'})});
  const CA = (r.headers.get('set-cookie') || '').split(';')[0];
  const call = (method, url, body) => fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: CA}, body: body ? JSON.stringify(body) : undefined}).then(x => x.json());
  await call('POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: MODS.split(',')});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: MODS + ',collab'});
  const ORG = (await call('GET', '/api/state')).me.workspaces[0].id;
  await call('POST', '/api/users', {username: 'rita', display_name: 'Rita', password: 'password123', email: 'rita@example.com', orgs: [{id: ORG, role: 'readonly'}]});
  const PG = (await call('POST', '/api/wiki/pages', {space: 'org:' + ORG, path: 'Talks/Pitch', body: BODY})).id;
  check(PG > 0, 'a page of the organisation ' + PG);

  const ready = async (ev, expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
  const login = async (ev, nav, who) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); sessionStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: ${JSON.stringify(H)}, body: JSON.stringify({username: '${who}', password: 'password123'})}).then(r => r.status)`) === 200, who + ' logs in');
    await ev(`fetch('/api/settings', {method: 'PATCH', headers: ${JSON.stringify(H)}, body: JSON.stringify({lang: 'en', tour: 'done', features: '${MODS},collab'})}).then(r => r.status)`);
  };
  // what a person sees of the presentation
  const SEEN = `(() => { const m = document.querySelector('#wkp'); if (!m) return null; const R = e => e.getBoundingClientRect(), vis = e => !!e && R(e).width > 0 && R(e).height > 0;
    const s = m.querySelector('.wkpslide'), h = s && s.querySelector('h4, h5, h6'), mr = R(m);
    return {no: m.querySelector('.wkpno').textContent, head: h ? h.textContent : null, hpx: h ? parseFloat(getComputedStyle(h).fontSize) : 0, text: s ? s.textContent.replace(/\\s+/g, ' ').trim() : '',
      shown: vis(s) && R(s).top >= mr.top && R(s).bottom <= mr.bottom + 1, full: Math.abs(mr.width - document.documentElement.clientWidth) <= 2 && Math.abs(mr.height - document.documentElement.clientHeight) <= 2 && mr.top <= 1 && mr.left <= 1,
      prev: m.querySelector('[data-wkp="-1"]').disabled, next: m.querySelector('[data-wkp="1"]').disabled, focus: m.contains(document.activeElement),
      cb: [...m.querySelectorAll('.wkpslide input[type="checkbox"]')].map(x => x.disabled)}; })()`;
  const present = async (ev, who) => {
    await ev(`(() => { document.querySelector('#view [data-wk="pmenu"]').click(); return 1; })()`);
    if (!await ready(ev, `!!document.querySelector('#pop:not(.hidden) [role="menuitem"]')`, 20)) return false;
    const items = await ev(`[...document.querySelectorAll('#pop [role="menuitem"]')].map(x => x.textContent.trim())`);
    check(items[0] === 'Present', who + ': "Present" is the first entry of the page\'s "…" ' + JSON.stringify(items));
    await ev(`(() => { [...document.querySelectorAll('#pop [role="menuitem"]')].find(x => x.textContent.trim() === 'Present').click(); return 1; })()`);
    return ready(ev, `!!document.querySelector('#wkp .wkpslide')`, 40);
  };

  // ---- a computer: keys and buttons; then a read-only member
  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    const act = actions => cmd('input.performActions', {context: ctx, actions}).then(() => cmd('input.releaseActions', {context: ctx}));
    const key = c => act([{type: 'key', id: 'k', actions: [{type: 'keyDown', value: c}, {type: 'keyUp', value: c}]}]);
    const at = n => ready(ev, `(document.querySelector('#wkp .wkpno') || {}).textContent === '${n} / 4'`, 20);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 860}});
    await login(ev, nav, 'alice');
    await nav(B + `#wiki/${PG}`);
    check(await ready(ev, `!!S.booted && !!document.querySelector('#view [data-wk="pmenu"]') && !!document.querySelector('#view .wkpage')`, 80), 'computer: the page is open');
    check(await ev(`JSON.stringify(LD_MODS.wkpresent) === '["wkpresent"]' && !document.querySelector('script[src*="wkpresent"]:not([data-ld])')`), 'computer: the presentation is a module loaded on demand (no script tag of the start)');
    check(await present(ev, 'computer'), 'computer: "Present" opens the presentation');
    const a = await ev(SEEN);
    await shot('p21368_b-desktop-title.png');
    check(a && a.no === '1 / 4' && a.head === 'Pitch' && a.text.includes('Intro before any heading.') && !a.text.includes('Opening'), 'computer: slide 1 is the title slide with the page\'s name and the text before the first heading ' + JSON.stringify(a));
    check(a && a.shown && a.full && a.focus && a.prev && !a.next, 'computer: the slide fills the window, is seen whole, has the keys, ‹ off on the first ' + JSON.stringify(a));
    await key(RIGHT);
    check(await at(2), 'computer: → leafs to slide 2');
    const b = await ev(SEEN);
    check(b.head === 'Opening' && b.text.includes('Welcome everyone.') && !b.text.includes('Story') && b.hpx >= 28, 'computer: slide 2 shows "# Opening" with its text in large type ' + JSON.stringify(b));
    await key(RIGHT);
    check(await at(3), 'computer: → again leafs to slide 3');
    const c = await ev(SEEN);
    await shot('p21368_b-desktop-story.png');
    check(c.head === 'Story' && c.text.includes('Detail') && c.text.includes('Stays on the story slide.') && !c.text.includes('Thanks'), 'computer: "## Story" is a slide, its "### Detail" stays on it ' + JSON.stringify(c));
    check(c.cb.length === 1 && c.cb[0] === true, 'computer: the checkbox on the slide is only shown ' + JSON.stringify(c.cb));
    await ev(`(() => { document.querySelector('#wkp .wkpslide input[type="checkbox"]').click(); return 1; })()`);
    await key(END);
    check(await at(4), 'computer: End goes to the last slide');
    const d = await ev(SEEN);
    check(d.head === 'End' && d.text.includes('Thanks for watching.') && d.next && !d.prev, 'computer: the last slide, › off ' + JSON.stringify(d));
    await key(LEFT);
    check(await at(3), 'computer: ← goes back');
    check((await ev(SEEN)).head === 'Story', 'computer: ← shows "Story" again');
    await key(HOME);
    check(await at(1), 'computer: Home goes to the first slide');
    await ev(`(() => { document.querySelector('#wkp [data-wkp="1"]').click(); return 1; })()`);
    check(await at(2), 'computer: the › button leafs');
    await key(ESC);
    check(await ready(ev, `!document.querySelector('#wkp') && !!document.querySelector('#view .wkpage') && location.hash === '#wiki/${PG}'`, 20), 'computer: Esc ends the presentation, the page is there as before');
    check(await ready(ev, `(e => !!e && e.textContent.includes('Thanks for watching.'))(document.querySelector('#wk-md') || document.querySelector('#wk-cm'))`, 20), 'computer: the page is readable again (the writer sees it in the editor)');
    check(await ready(ev, `!document.fullscreenElement`, 20), 'computer: full screen is left');
    check((await call('GET', `/api/wiki/pages/${PG}`)).body === BODY, 'computer: the page\'s text is unchanged (the checkbox ticked nothing)');
    // the menu of an empty page has no "Present"
    const EMPTY = (await call('POST', '/api/wiki/pages', {space: 'org:' + ORG, path: 'Talks/Empty', body: ''})).id;
    await nav(B + `#wiki/${EMPTY}`);
    check(await ready(ev, `!!document.querySelector('#view [data-wk="pmenu"]') && WK.pg?.id === ${EMPTY}`, 60), 'computer: the empty page is open');
    check(await ev(`!wk_pmenuItems(WK.pg).some(x => x && x.label === 'Present')`), 'computer: an empty page offers no presentation');

    // ---- a read-only member presents the page too
    await ev(`fetch('/api/auth/logout', {method: 'POST', headers: ${JSON.stringify(H)}}).then(r => r.status)`);
    await login(ev, nav, 'rita');
    await nav(B + `#wiki/${PG}`);
    check(await ready(ev, `!!S.booted && !!document.querySelector('#view [data-wk="pmenu"]') && !!document.querySelector('#wk-md') && !document.querySelector('[data-wk="pen"]')`, 80), 'read-only: the page is read, without a pen');
    check(await present(ev, 'read-only'), 'read-only: "Present" opens the presentation');
    const ra = await ev(SEEN);
    check(ra && ra.no === '1 / 4' && ra.head === 'Pitch' && ra.shown, 'read-only: the title slide ' + JSON.stringify(ra));
    await key(RIGHT);
    check(await at(2) && (await ev(SEEN)).head === 'Opening', 'read-only: → shows "Opening"');
    await key(LEFT);
    check(await at(1), 'read-only: ← goes back');
    await shot('p21368_b-readonly.png');
    await key(ESC);
    check(await ready(ev, `!document.querySelector('#wkp') && !!document.querySelector('#wk-md') && location.hash === '#wiki/${PG}'`, 20), 'read-only: Esc ends it, the page is readable');
  }, false);

  // ---- a phone: a swipe leafs, Back ends it
  await firefox(async o => {
    const {cmd, ev, ctx, nav, shot} = o;
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 412, height: 860}});
    await login(ev, nav, 'alice');
    await nav(B + `#wiki/${PG}`);
    check(await ready(ev, `!!S.booted && !!document.querySelector('#view [data-wk="pmenu"]') && !!document.querySelector('#wk-md')`, 80), 'phone: the page is open');
    check(await present(ev, 'phone'), 'phone: "Present" opens the presentation');
    check(await ready(ev, `typeof swn_attach === 'function' && !!WKP.sw`, 40), 'phone: the swipe is ready');
    const a = await ev(SEEN);
    await shot('p21368_b-phone-title.png');
    check(a && a.no === '1 / 4' && a.head === 'Pitch' && a.shown && a.full, 'phone: the title slide fills the screen ' + JSON.stringify(a));
    const sw = await ev(`(async () => {
      const st = document.querySelector('#wkp .wkpstage'), r = st.getBoundingClientRect(), y = Math.round(r.top + r.height / 2), x0 = Math.round(r.left + r.width * 0.75);
      const hit = document.elementFromPoint(x0, y); if (!hit || !st.contains(hit)) return {hit: false};
      const fire = (type, x) => { const t = new Touch({identifier: 7, target: hit, clientX: x, clientY: y}); hit.dispatchEvent(new TouchEvent(type, {bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], targetTouches: type === 'touchend' ? [] : [t], changedTouches: [t]})); };
      fire('touchstart', x0);
      for (let i = 1; i <= 12; i++) { fire('touchmove', x0 - i * 14); await new Promise(z => setTimeout(z, 16)); }
      fire('touchend', x0 - 168);
      return {hit: true}; })()`);
    check(sw && sw.hit, 'phone: the finger lies on the slide ' + JSON.stringify(sw));
    check(await ready(ev, `(document.querySelector('#wkp .wkpno') || {}).textContent === '2 / 4'`, 20), 'phone: a swipe to the left leafs to slide 2');
    const b = await ev(SEEN);
    await shot('p21368_b-phone-swiped.png');
    check(b.head === 'Opening' && b.text.includes('Welcome everyone.') && b.shown, 'phone: slide 2 is seen whole ' + JSON.stringify(b));
    await ev(`(() => { history.back(); return 1; })()`);
    check(await ready(ev, `!document.querySelector('#wkp') && !!document.querySelector('#wk-md') && location.hash === '#wiki/${PG}'`, 20), 'phone: Back ends the presentation, the page stays open');
  }, true);

  console.log(`p21368_b_wiki_present_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
