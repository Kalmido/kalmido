// @ts-check
/* Kalmido web client: 2.1368.0 (#5525) a knowledge page as a presentation -- "Present" in the page's "…" menu (wiki.js
   wk_pmenuItems, also for who may only read). Loaded on demand (lazyload.js module 'wkpresent'), so the start does not grow.
   Only a view: the page is drawn as when reading (wk_render; a page of an encrypted space is decrypted already) and cut into
   slides, nothing is stored. A slide starts at every heading of the top two levels ("#" and "##"; a page whose top heading is
   "###" cuts at those); text before the first heading becomes a title slide with the page's name. Full screen where the
   browser allows it (the overlay fills the window anyway, e.g. on an iPhone); arrow keys, Page keys, Space, Enter, Home / End,
   a swipe sideways (swipenav.js) and ‹ › in the bar leaf; Esc, ×, the phone's Back (backclose.js), leaving full screen or
   another address end it. A link on a slide ends it and opens. Checkboxes on a slide are only shown (they never tick the page).
   Classic script sharing the global scope with the others. */
'use strict';

const WKP = {/** @type {any} */ el: null, i: 0, /** @type {string[]} */ sl: [], sp: '', full: false, /** @type {any} */ sw: null};
/** @type {Record<string, number>} */
const WKP_LV = {H4: 4, H5: 5, H6: 6};  // renderMd draws "#" as <h4>, "##" as <h5>, "###" and deeper as <h6>
// the page's drawing cut into slides (the HTML of each)
function wkp_slides(/** @type {any} */ p) {
  const box = document.createElement('div');
  box.innerHTML = wk_render(p);  // the page's own drawing (renderMd escapes), as #wk-md shows it
  const nodes = [...box.childNodes], lv = nodes.map(n => WKP_LV[/** @type {any} */ (n).tagName] || 0);
  const cut = Math.max(5, Math.min(7, ...lv.filter(Boolean)));
  /** @type {string[][]} */
  const out = [];
  nodes.forEach((n, k) => {
    if (!out.length || (lv[k] && lv[k] <= cut)) out.push([]);
    out[out.length - 1].push(n.nodeType === 1 ? /** @type {any} */ (n).outerHTML : esc(n.textContent || ''));
  });
  const first = nodes.findIndex(n => n.nodeType === 1 || (n.textContent || '').trim());
  if (out.length && !(lv[first] && lv[first] <= cut)) out[0].unshift(`<h4>${esc(wk_base(p.path))}</h4>`);  // the title slide
  return out.map(x => x.join('')).filter(x => x.replace(/<[^>]*>/g, '').trim() || /<(img|svg|table|pre|iframe|figure|video)\b/i.test(x));
}
const wkp_slideHtml = (/** @type {number} */ i) => `<section class="wkpslide md ntmd wkmd${esc(typeof wkst_cls === 'function' ? wkst_cls(WKP.sp) : '')}" aria-roledescription="${esc(tr('Slide'))}" aria-label="${esc(tr('Slide {0} of {1}', i + 1, WKP.sl.length))}">${/*html-ok*/ WKP.sl[i] || '' /* the page's drawing (wk_render) */}</section>`;
function wkp_cbOff(/** @type {any} */ el) { for (const x of $$('input', el)) x.disabled = true; return el; }
async function wkp_open(/** @type {any} */ p) {
  if (WK.dirty) await wk_flush();
  const pg = WK.pg?.id === p.id ? WK.pg : p;
  wkp_close();
  WKP.sl = wkp_slides(pg); WKP.sp = pg.space; WKP.i = 0;
  if (!WKP.sl.length) { toast(tr('Empty page.')); return; }
  const m = /** @type {any} */ (document.createElement('div'));
  m.id = 'wkp'; m.className = 'wkp'; m.tabIndex = -1;
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true'); m.setAttribute('aria-label', tr('Presentation: {0}', wk_base(pg.path)));
  m.innerHTML = `<div class="wkpstage"></div><div class="wkpbar"><button type="button" class="iconbtn" data-wkp="-1" title="${esc(tr('Previous slide'))}" aria-label="${esc(tr('Previous slide'))}">${ic('left')}</button><span class="wkpno" role="status" aria-live="polite"></span><button type="button" class="iconbtn" data-wkp="1" title="${esc(tr('Next slide'))}" aria-label="${esc(tr('Next slide'))}">${ic('right')}</button><span class="wkpttl">${esc(wk_base(pg.path))}</span><button type="button" class="iconbtn" data-wkp="x" title="${esc(tr('End presentation'))}" aria-label="${esc(tr('End presentation'))}">${ic('x')}</button></div>`;
  document.body.appendChild(m);
  WKP.el = m;
  kb_push('dialog', m, {close: () => wkp_close()});
  m.addEventListener('click', wkp_click);
  m.addEventListener('keydown', wkp_key);
  // lazy-ok-begin: swOn runs only once swipenav.js is in (the typeof / loadModule below)
  const swOn = () => { if (WKP.el === m && !WKP.sw) WKP.sw = swn_attach(m, {area: t => t && !t.closest?.('.wkpbar') ? $('.wkpslide', m) : null, can: d => !!WKP.sl[WKP.i + d],
    go: d => wkp_go(WKP.i + d, true), peek: d => { const x = document.createElement('div'); x.innerHTML = wkp_slideHtml(WKP.i + d); return {el: wkp_cbOff(x.firstElementChild)}; }}); };
  // lazy-ok-end
  if (typeof swn_attach === 'function') swOn();
  else if (navigator.maxTouchPoints > 0 || isTouch()) loadModule('swipenav').then(swOn).catch(() => {});
  wkp_go(0);
  m.focus({preventScroll: true});
  try { if (!document.fullscreenElement && m.requestFullscreen) m.requestFullscreen().then(() => { WKP.full = WKP.el === m; }, () => {}); } catch { /* not allowed here */ }
}
function wkp_go(/** @type {number} */ i, swiped = false) {
  const m = WKP.el; if (!m) return;
  const was = WKP.i;
  WKP.i = Math.max(0, Math.min(WKP.sl.length - 1, i));
  const st = $('.wkpstage', m);
  st.innerHTML = wkp_slideHtml(WKP.i);
  wkp_cbOff(st); st.scrollTop = 0;  // sprung-ok: a new slide starts at its top (the person leafed)
  if (!swiped && was !== WKP.i && typeof swn_slideIn === 'function') swn_slideIn($('.wkpslide', st), WKP.i > was ? 1 : -1);
  $('.wkpno', m).textContent = `${WKP.i + 1} / ${WKP.sl.length}`;
  $('[data-wkp="-1"]', m).disabled = WKP.i === 0;
  $('[data-wkp="1"]', m).disabled = WKP.i >= WKP.sl.length - 1;
  if (typeof dg_draw === 'function') dg_draw(/** @type {any} */ (st));  // formulas / diagrams of the slide (diagram.js, loaded by wk_render when the page has any)
}
function wkp_close() {
  const m = WKP.el; if (!m) return;
  WKP.el = null; WKP.sw = null; kb_pop(m); m.remove();
  if (WKP.full && document.fullscreenElement) document.exitFullscreen?.()?.catch?.(() => {});
  WKP.full = false;
  $('#view [data-wk="pmenu"]')?.focus({preventScroll: true});
}
function wkp_click(/** @type {any} */ e) {
  const t = e.target, b = t.closest?.('[data-wkp]');
  if (b) { e.preventDefault(); if (b.dataset.wkp === 'x') wkp_close(); else wkp_go(WKP.i + +b.dataset.wkp); return; }
  if (WKP.sw?.recent?.()) { e.preventDefault(); return; }  // the end of a swipe opens nothing
  if (t.closest?.('a[href]')) setTimeout(wkp_close, 0);  // a link leaves the presentation (it opens after this click)
}
/** @type {Record<string, number>} */
const WKP_KEYS = {ArrowRight: 1, ArrowDown: 1, PageDown: 1, ' ': 1, Enter: 1, ArrowLeft: -1, ArrowUp: -1, PageUp: -1, Backspace: -1};
function wkp_key(/** @type {any} */ e) {
  if (e.altKey || e.ctrlKey || e.metaKey || e.isComposing) return;
  const k = e.key, onBtn = !!e.target.closest?.('button,a');
  let to = WKP_KEYS[k] || 0;
  if (k === ' ' && e.shiftKey) to = -1;
  if (to && !((k === 'Enter' || k === ' ') && onBtn)) wkp_go(WKP.i + to);
  else if (k === 'Home' || k === 'End') wkp_go(k === 'Home' ? 0 : WKP.sl.length - 1);
  else if (k === 'Escape') wkp_close();
  else return;
  e.preventDefault(); e.stopPropagation();
}
document.addEventListener('fullscreenchange', () => { if (WKP.el && WKP.full && !document.fullscreenElement) { WKP.full = false; wkp_close(); } });  // the browser's own Esc of full screen ends it too
window.addEventListener('hashchange', () => { if (WKP.el) wkp_close(); });
