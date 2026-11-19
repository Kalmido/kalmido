// (#7342) UI test (Firefox), fresh DB:
// kalmido-suite: fresh
// The floating bars, toasts and hints are centred without transform (start-mitte-7342.css): a box of odd width on a half
// pixel made Chrome / Safari on the Mac raster the text soft. For each one: no transform left, the box sits in the middle
// of the window (left gap = right gap within a pixel) at phone and desktop width, odd text widths included; the undo
// toast is still usable (its Undo button takes the click and closes it).
const {B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p7342_mitte_ui', check, shots: 'P7342_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const SEL = ['#toast', '#newver', '#stale', '#savedok', '#upbars', '#mbar', '.mselbar', '.tdmove', '#codechg', '#dahint', '.cele-quip.on', '.dswpos.on'];

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const CK = await login('alice');
  await fetch(B + 'api/settings', {method: 'PATCH', headers: {...H, Cookie: CK}, body: JSON.stringify({lang: 'en', tour: 'done', whatsnew_on: '0'})});

  await firefox(async ({cmd, ev, nav, ctx, until}) => {
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); return 1; })()`);
    check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`) === 200, 'login');
    await nav(B + '#today');
    check(await until(`typeof toast === 'function' && !!document.querySelector('#view')`), 'the app is up');

    for (const w of [390, 1280]) {
      await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: 844}});
      for (const txt of ['Moved', 'Moved 3 tasks to Done']) {
        const m = await ev(`(() => { const out = [];
          for (const sel of ${JSON.stringify(SEL)}) {
            const m = sel.match(/^([#.])([\\w-]+)((?:\\.[\\w-]+)*)$/), el = document.createElement('div');
            if (m[1] === '#') el.id = m[2]; else el.className = m[2];
            if (m[3]) el.classList.add(...m[3].split('.').filter(Boolean));
            el.dataset.p7342 = '1'; el.innerHTML = '<span>${txt}</span>'; document.body.appendChild(el);
            el.getAnimations().forEach(a => a.finish());  // the entry slide (an_up / an_tin) moves vertically and ends at 0
            const r = el.getBoundingClientRect(), cs = getComputedStyle(el), W = document.documentElement.clientWidth;
            out.push({sel, tf: cs.transform, tx: cs.translate, l: Math.round(r.left * 100) / 100, gap: Math.round((r.left - (W - r.right)) * 100) / 100, w: Math.round(r.width)});
            el.remove();
          }
          return out; })()`);
        for (const x of m) {
          check(x.tf === 'none' && (x.tx === 'none' || /^0px( 0px)?$/.test(x.tx)), `#7342 ${x.sel} at ${w}px ("${txt}"): no transform (${x.tf} / ${x.tx})`);
          check(Math.abs(x.gap) <= 1 && x.w > 0, `#7342 ${x.sel} at ${w}px ("${txt}"): centred, left gap = right gap (${JSON.stringify(x)})`);
        }
      }
    }

    // the real undo toast: centred, no transform once its entry animation ended, and its button still works
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 1280, height: 844}});
    await ev(`(() => { window.__undo = 0; toast('Task deleted', () => { window.__undo++; }, 8000); })()`);
    check(await until(`!!document.querySelector('#toast:not(.hidden)') && document.querySelector('#toast').getAnimations().length === 0`), 'the undo toast is shown');
    const t = await ev(`(() => { const e = document.querySelector('#toast'), r = e.getBoundingClientRect(), W = document.documentElement.clientWidth;
      return {tf: getComputedStyle(e).transform, gap: Math.abs(r.left - (W - r.right))}; })()`);
    check(t.tf === 'none' && t.gap <= 1, `#7342 the undo toast is centred without transform ${JSON.stringify(t)}`);
    await ev(`document.querySelector('#toast button:not(.tx)')?.click()`);
    check(await until(`window.__undo === 1 && document.querySelector('#toast').classList.contains('hidden')`), '#7342 the undo button still takes the click and closes the toast');
  }, true);

  console.log(`p7342_mitte_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e.stack || e); console.log(`p7342_mitte_ui: ${ok} ok, ${F.length + 1} failed`); process.exit(1); });
