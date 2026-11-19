// @ts-check
/* Kalmido web client: 2.164.0 (#2625) gestures of the calendar (module "calendar", loaded with calview.js / caldrag.js).
   One finger sideways turns the page in month, week, day and year: the page follows the finger and snaps to the next /
   previous period (or back). Two fingers zoom without steps: in week / day the hour height follows the fingers live (the
   grid's --h, the blocks hang on it during the gesture), is taken over on release (bounds CAL_HMIN..CAL_HMAX, kept on the
   device, calendar.js weekH); pinched on beyond a bound, or pinched in month / year, the view changes (year - month - week -
   day) with a soft transition. The trackpad does the same: pinch / Ctrl + mouse wheel zoom, a two-finger swipe turns the
   page. A double tap on a day of the month opens that day. The long press of caldrag.js (events) and dnd.js (tasks) stays:
   a swipe starts only once the finger clearly moved sideways (after their 8 px tolerance), a second finger cancels a
   pending hold, and nothing starts while one of their drags runs.
   2.290.0 A (#3144): in week / day the fingers' direction counts: their sideways distance sets the number of days (1..14,
   live and without steps, rounded to whole days on release: 1 = the day view, 7 = the week, kept on the device), their
   up / down distance the hour height, diagonal both. The hour bounds no longer change the view there; pinched together
   beyond 14 days = the month. Ctrl + Shift + wheel (or Ctrl + a sideways wheel) = days, Ctrl + wheel = hours; a pinch
   without a direction (the trackpad's Ctrl + wheel, Safari's gesture events) zooms the hours and, beyond the lower bound,
   goes to the month.
   2.1312.0 (#6711): one finger leafs like a page with the core's helper (swipenav.js swn_attach, as the document view and the
   task panel): only the grid moves (the bar, the day list with its input line below the month stay), the neighbour period
   lies beside it as a placeholder (its empty grid with the head: weekdays, the days of the week, the twelve months), let go
   far enough it glides fully into place and only then the new period is drawn (no spring back to 0, no second glide-in);
   on every touch screen the same. The trackpad's sideways swipe and the arrows stay as they were. */
'use strict';

const CGS = {
  /** @type {any} */ sw: null,  // 2.1312.0 (#6711): the handle of the one-finger leafing (swipenav.js swn_attach)
  /** @type {any} */ pz: null,  // zoom session {week|flat, k, src: 'touch'|'wheel'|'gesture', ...}
  /** @type {any} */ wx: null,  // trackpad swipe {acc, els, idle, done}
  /** @type {any} */ tap: null,  // last tap on a month day {day, x, y, at}
  fing: false, redraw: false, attaching: false,  // 2.1312.0 (#6711): a finger leafs / a redraw waits for it / swn_attach runs
  hold: false,  // fingers of an ended pinch still on the screen: no swipe until all are lifted
};
const CGS_AREA = '#view .cal, #view .week, #view #cyear';
const CGS_STEP = 1.2;  // pinched on by this much beyond a bound (week / day) = the next view
const CGS_FLAT = 1.25;  // month / year: pinched by this factor = the next view
const CGS_AX = 48;  // 2.290.0 A (#3144): a finger distance along one axis counts from this many px (no jumps from a tiny span)
const CGS_DEAD = 1.12;  // the days change only beyond this factor (a vertical pinch drifting a little sideways keeps them)
/** @param {EventTarget|null} t */
const cgs_el = t => t instanceof Element ? t : null;
/** @param {EventTarget|null} t */
const cgs_area = t => S.route?.mod === 'cal' ? cgs_el(t)?.closest(CGS_AREA) || null : null;
const cgs_hasYear = () => typeof (/** @type {any} */ (window)).cyr_view === 'function';  // 2.155.0 C (#2078): calyear.js
const cgs_still = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return false; } };
// another drag owns the finger: an event (caldrag.js), a task (dnd.js), the sidebar
const cgs_busy = () => !!CG.st?.active || !!CG.nw || document.body.classList.contains('cgdrag') || document.body.classList.contains('tdrag');
function cgs_dropHolds() {  // a second finger: the pending long presses of caldrag.js / dnd.js are off
  // 2.193.0 (#2219): the holds live in drag.js now - cancel the press there too
  // 2.1286.0 (#5704): through cg_cancel, which also draws the events a fetch brought while the finger held (CG.redraw)
  if (CG.st && !CG.st.active) { if (drg_cur?.d === CG.st) drg_cancel(); if (CG.st) cg_cancel(); }
  if (lp && !lp.active) { if (drg_cur?.d === lp) drg_cancel(); lp = null; }
}

// ---- changing the view (year < month < week < day); dir > 0 = nearer
function cgs_go(mode, day, dir, x, y) {
  if (day) S.calSel = day;
  S.calMode = mode; LS.set('calMode', mode);
  if (mode === 'month') S.calMonth = S.calSel.slice(0, 7);
  renderView();
  const v = $('#view'), g = $('#view > .calbar ~ *'); if (!v || !g || cgs_still()) return;
  v.classList.remove('cgs-zi', 'cgs-zo');
  const r = g.getBoundingClientRect();  // grows out of the point between the fingers (in the new grid's own box)
  v.style.setProperty('--cgs-o', `${Math.round(x - r.left)}px ${Math.round(Math.max(0, Math.min(r.height, y - r.top)))}px`);
  void v.offsetWidth;  // the animation starts again
  v.classList.add(dir > 0 ? 'cgs-zi' : 'cgs-zo');
  setTimeout(() => v.classList.remove('cgs-zi', 'cgs-zo'), 400);
}
// the next view nearer (dir > 0) / farther from where the fingers are (x, y): null at the end of the row
function cgs_next(dir, x, y) {
  const ms = cgs_modes(), i = ms.indexOf(S.calMode), to = ms[i + dir];
  if (i < 0 || !to) return null;
  const at = cgs_el(document.elementFromPoint?.(x, y) || null);
  let day = null;
  if (S.calMode === 'week' && to === 'day') day = at?.closest('#view .week [data-day]')?.getAttribute('data-day') || cg_colAt(x, null)?.dataset.day || null;
  if (S.calMode === 'month' && to === 'week') day = at?.closest('#view .cal .cell[data-day]')?.getAttribute('data-day') || null;
  if (S.calMode === 'year' && to === 'month') { const m = at?.closest('.cymon')?.querySelector('[data-cym]')?.getAttribute('data-cym'); if (m) day = `${m}-01`; }
  return {mode: to, day};
}
const cgs_modes = () => [...(cgs_hasYear() ? ['year'] : []), 'month', 'week', 'day'];

// ---- zoom: one session for fingers, the trackpad's pinch / Ctrl + wheel and Safari's gesture events
// k = the factor since the start; (x, y) = the point between the fingers / under the pointer
function cgs_hang(wb, H0) {  // every block of the hours hangs on --h while the fingers move (no step, no new drawing per frame)
  for (const el of wb.querySelectorAll('[style*="top"]')) {
    const s = /** @type {HTMLElement} */ (el).style, t = parseFloat(s.top), h = parseFloat(s.height);
    if (!s.top.endsWith('px')) continue;
    s.top = `calc(var(--h) * ${t / H0})`;
    if (s.height.endsWith('px') && h > 20.5) s.height = `max(20px, calc(var(--h) * ${h / H0}))`;
  }
}
// 2.290.0 A (#3144): the first day for n days, the day under the fingers staying under them
const cgs_from = (p, n) => addDays(p.anchor, -Math.min(Math.ceil(n - 1e-6) - 1, Math.floor(Math.max(0, Math.min(.999, (p.x - p.cl) / p.cw)) * n)));
function cgs_pzStart(area, x, y, src) {
  const week = area.closest('.week') && $('#view .week'), wb = week && $('#wbody');
  if (week && wb) {
    const H0 = weekH(), r = wb.getBoundingClientRect();
    cgs_hang(wb, H0);
    // 2.290.0 A (#3144): the day columns' box and the day under the fingers (for the number of days)
    const {days, nf} = calGridDays(), cols = $$('#view .week:not(.cgs-nbg) .wcol'), c0 = cols[0]?.getBoundingClientRect(), c1 = cols[cols.length - 1]?.getBoundingClientRect();
    const cl = c0 ? c0.left : r.left, cw = Math.max(1, (c1 ? c1.right : r.right) - cl);
    const anchor = addDays(days[0], Math.min(days.length - 1, Math.floor(Math.max(0, Math.min(.999, (x - cl) / cw)) * nf)));
    const wr = week.getBoundingClientRect();  // #7388: the grid's box once (no layout read per frame after the style writes)
    CGS.pz = {week, wb, src, H0, H: H0, k: 1, kx: 1, ky: 1, x, y, top: r.top, min: (wb.scrollTop + Math.max(0, Math.min(r.height, y - r.top))) / H0 * 60,
      n0: nf, nf, cl, cw, anchor, from: days[0], wl: wr.left, wt: wr.top, ad: /** @type {HTMLElement|null} */ (week.querySelector('.wallday'))?.offsetHeight || 0};
    // #7388: two fingers: the grid of the days they can reach is drawn now, once, before they move (not mid-gesture)
    if (src === 'touch') cgs_prep(CGS.pz, nf, days[0]);
  } else {
    const box = /** @type {HTMLElement} */ (area), r = box.getBoundingClientRect();
    box.style.transformOrigin = `${Math.round(x - r.left)}px ${Math.round(y - r.top)}px`;
    box.style.transition = 'none';
    CGS.pz = {box, src, k: 1, x, y};
  }
}
// #7388: the day of a date string as a number (whole days between two dates)
const cgs_dd = (a, b) => Math.round((pd(b).getTime() - pd(a).getTime()) / 864e5);
// #7388: the grid for a pinch, drawn ONCE: the range of days the fingers can reach from here (up to CAL_DMAX days on the side
// the fingers stand, the shown ones included); the fingers then only move it (--off) and size its columns (--nf). Drawn anew
// only when they reach beyond the range (the fingers wandered far sideways). The all-day row keeps its height (a day of the
// range with more all-day entries would push the hours down)
function cgs_prep(p, nf, from) {
  const fr = Math.max(0, Math.min(.999, (p.x - p.cl) / p.cw)), last = addDays(from, Math.ceil(nf - 1e-6) - 1);
  let r0 = addDays(p.anchor, -Math.min(CAL_DMAX - 1, Math.ceil(fr * CAL_DMAX) + 1));
  if (cgs_dd(r0, from) < 0) r0 = addDays(from, -2);
  let r1 = addDays(r0, CAL_DMAX + 1);
  if (cgs_dd(last, r1) < 0) r1 = addDays(last, 2);
  CAL_LIVE = {nf, from, r0, rn: cgs_dd(r0, r1) + 1, arm: !!p.next};
  p.vis = '';
  renderView();
  if (!cgs_rehook(p)) return false;
  cgs_days(p);
  return true;
}
// #7388: the days seen follow the fingers without drawing: the columns' width (--nf) and the range's shift (--off); the title
// names the days seen
function cgs_days(p) {
  const L = CAL_LIVE; if (!L || !p.week) return;
  p.week.style.setProperty('--nf', String(L.nf)); p.week.style.setProperty('--off', String(calLiveOff()));
  const vis = `${L.from}|${Math.ceil(L.nf - 1e-6)}`;
  if (vis !== p.vis) { p.vis = vis; const h = $('#view > .calbar h2'); if (h) h.textContent = calWeekTitle(calGridDays().vis); }
}
const cgs_pzDraw = rafThrottle(() => {
  const p = CGS.pz; if (!p) return;
  if (p.week) {
    if (!p.week.isConnected && !cgs_rehook(p)) { cgs_pzEnd(); return; }  // drawn anew meanwhile (a live update): the session goes on in the new grid
    const z = uiZ(), want = p.H0 * p.ky, H = Math.max(CAL_HMIN * z, Math.min(CAL_HMAX * z, want)), over = want / H;
    // 2.290.0 A (#3144): the days without steps: the columns are 1/nf wide (calview.js). #7388: on the grid prepared once
    // (cgs_prep), never drawn anew while a day comes or goes
    const wantN = p.n0 / p.kx, nf = Math.max(1, Math.min(CAL_DMAX, wantN)), overD = wantN / nf;
    if (p.dz || Math.abs(nf - p.n0) > .05) {  // the days change only once the fingers left the dead zone (p.dz: since then)
      p.dz = true;
      const from = cgs_from(p, nf), last = addDays(from, Math.ceil(nf - 1e-6) - 1);
      p.nf = nf; p.from = from;
      if (!CAL_LIVE || cgs_dd(CAL_LIVE.r0, from) < 0 || cgs_dd(last, addDays(CAL_LIVE.r0, CAL_LIVE.rn - 1)) < 0) { if (!cgs_prep(p, nf, from)) { cgs_pzEnd(); return; } }
      else { CAL_LIVE.nf = nf; CAL_LIVE.from = from; cgs_days(p); }
    }
    p.H = H;
    p.week.style.setProperty('--h', H + 'px');
    p.wb.scrollTop = p.min / 60 * H - Math.max(0, p.y - p.top);  // the hour between the fingers stays under them
    // beyond a bound: the grid gives a little, and once a release would change the view it says so. 2.290.0 A (#3144):
    // only beyond 14 days (or, without a direction, below the lowest hour height): the month; never the day / week by the hours
    p.next = overD >= CGS_STEP || (p.src !== 'touch' && over <= 1 / CGS_STEP) ? -1 : 0;
    const sc = (1 + (Math.max(.8, Math.min(1.25, over)) - 1) * .25) * (1 - (Math.min(1.25, overD) - 1) * .25);
    p.week.style.transformOrigin = `${Math.round(p.x - p.wl)}px ${Math.round(p.y - p.wt)}px`;
    p.week.style.transform = sc === 1 || cgs_still() ? '' : `scale(${sc})`;
    p.week.classList.toggle('cgs-arm', !!p.next);
    if (CAL_LIVE) CAL_LIVE.arm = !!p.next;  // (a grid drawn anew meanwhile, e.g. by the repeats arriving, keeps saying so)
  } else {
    if (!p.box.isConnected) { CGS.pz = null; return; }
    p.next = p.k >= CGS_FLAT ? 1 : p.k <= 1 / CGS_FLAT ? -1 : 0;
    p.box.style.transform = `scale(${Math.max(.7, Math.min(1.4, p.k))})`;
    p.box.classList.toggle('cgs-arm', !!p.next && !!cgs_next(p.next, p.x, p.y));
  }
});
// 2.290.0 A (#3144): the grid was drawn anew during the gesture: its blocks hang on --h again
function cgs_rehook(p) {
  const week = $('#view .week'), wb = $('#wbody');
  if (!week || !wb) return false;
  p.week = week; p.wb = wb;
  cgs_hang(wb, p.H0);
  week.style.setProperty('--h', p.H + 'px');
  const ad = /** @type {HTMLElement|null} */ (week.querySelector('.wallday'));  // #7388: the hours stay where they were
  if (ad && p.ad && CAL_LIVE) { ad.style.height = p.ad + 'px'; ad.style.overflow = 'hidden'; }
  if (CAL_LIVE) cgs_days(p);
  return true;
}
// 2.290.0 A (#3144): whole days on release: 1 = the day view, 7 = the week of the day under the fingers, else n days from
// the first one shown; kept on the device (like the hour height)
function cgs_setDays(p) {
  const n = Math.max(1, Math.min(CAL_DMAX, Math.round(p.nf)));
  if (n === 1) { S.calMode = 'day'; S.calSel = cgs_from(p, 1); }
  else { S.calMode = 'week'; S.calSel = n === 7 ? p.anchor : cgs_from(p, n); LS.set('calDays', n); }
  LS.set('calMode', S.calMode);
}
function cgs_pzEnd() {
  cgs_pzDraw.flush();
  const p = CGS.pz; if (!p) return;
  CGS.pz = null;
  clearTimeout(p.idle);
  const live = !!CAL_LIVE; CAL_LIVE = null;
  // #7388: what waited for the fingers (the events fetched, a live update: cgs_held / lpHold) is drawn now, once
  const held = CGS.redraw || !!S.viewStale; CGS.redraw = false;
  // 2.290.0 A (#3144): the week grid only goes to the month (with the day under the fingers)
  const to = p.next ? p.week ? {mode: 'month', day: p.anchor} : cgs_next(p.next, p.x, p.y) : null;
  if (to) { cgs_go(to.mode, to.day, p.next, p.x, p.y); return; }
  if (p.week) {
    p.week.style.transform = ''; p.week.classList.remove('cgs-arm');
    const v = Math.round(p.H / uiZ());
    if (v !== calHourH()) LS.set('calHourH', v);
    if (live && p.dz) cgs_setDays(p);  // #7388: only when the days changed (a pinch up / down keeps them)
    if (p.week.isConnected || live) { S.viewStale = false; renderView(); }  // the blocks get their px again (the scroll position is kept)
    return;
  }
  if (held && !cgs_leafing()) { S.viewStale = false; renderView(); return; }
  p.box.classList.remove('cgs-arm');
  p.box.style.transition = 'transform .18s ease-out'; p.box.style.transform = '';
  setTimeout(() => { p.box.style.transition = ''; p.box.style.transformOrigin = ''; }, 200);
}

// ---- turning the page with the trackpad: the content below the bar follows, then snaps
const cgs_pages = () => /** @type {HTMLElement[]} */ ($$('#view > .calbar ~ *'));
function cgs_shift(els, dx) { for (const el of els) { el.style.transition = 'none'; el.style.transform = dx ? `translateX(${Math.round(dx)}px)` : ''; } }
function cgs_back(els) {
  for (const el of els) { el.style.transition = 'transform .18s ease-out'; el.style.transform = ''; }
  setTimeout(() => els.forEach(el => { el.style.transition = ''; }), 200);
}
function cgs_turn(els, dir) {  // dir > 0: the next period (finger to the left)
  cgs_shift(els, 0);
  $(`#view [data-act="${dir > 0 ? 'cal-next' : 'cal-prev'}"]`)?.click();  // the bar's arrows (events.js; glides in, an_calSlide)
}

// ---- fingers
document.addEventListener('touchstart', e => {
  if (!e.touches) return;  // a plain Event("touchstart") (tests, synthetic taps) has no touch list
  const n = e.touches.length;
  if (n >= 2) {
    if (CGS.pz || n > 2) { if (n > 2 && CGS.pz) cgs_pzEnd(); return; }
    const a = cgs_area(e.touches[0].target), b = cgs_area(e.touches[1].target);
    if (!a || a !== b || CG.st?.active || lp?.active || document.body.classList.contains('cgdrag') || document.body.classList.contains('tdrag')) return;
    cgs_dropHolds();
    const [p, q] = [e.touches[0], e.touches[1]];
    cgs_follow([p.target, q.target]);
    cgs_pzStart(a, (p.clientX + q.clientX) / 2, (p.clientY + q.clientY) / 2, 'touch');
    CGS.pz.d0 = Math.max(1, Math.hypot(p.clientX - q.clientX, p.clientY - q.clientY));
    CGS.pz.dx0 = Math.max(CGS_AX, Math.abs(p.clientX - q.clientX)); CGS.pz.dy0 = Math.max(CGS_AX, Math.abs(p.clientY - q.clientY));  // 2.290.0 A (#3144)
    return;
  }
  CGS.hold = false;  // one finger: the leafing (swipenav.js, attached below) decides
}, {passive: true});
// #7388 (the cause measured): a touch keeps the element it began on; once the grid is drawn anew (innerHTML) that element is
// out of the page and the browser sends the finger's touchmove / touchend only to it - never to the document. Measured on main
// (tests/p7388_calpinch_ui.js): the pinch froze right after the first day that came or went (7.1 days) and did not end with the
// fingers (each pinch one step). Now nothing is drawn under the fingers (cgs_prep once at the start), and the fingers'
// elements pass their events on while they are out of the page (in the page the document's listeners take them)
let CGS_TGT = /** @type {EventTarget[]} */ ([]);
/** @param {Event} e */
function cgs_fwd(e) {
  if (cgs_el(e.target)?.isConnected) return;
  if (e.type === 'touchmove') cgs_touchMove(/** @type {TouchEvent} */ (e)); else { cgs_touchEnd(e); cgs_lift(); }
}
/** @param {(EventTarget|null)[]} ts */
function cgs_follow(ts) {
  for (const t of CGS_TGT) for (const ev of ['touchmove', 'touchend', 'touchcancel']) t.removeEventListener(ev, cgs_fwd);
  CGS_TGT = [...new Set(ts.filter(t => !!t && typeof t.addEventListener === 'function'))];
  for (const t of CGS_TGT) for (const ev of ['touchmove', 'touchend', 'touchcancel']) t.addEventListener(ev, cgs_fwd, {passive: ev !== 'touchmove'});
}
/** @param {any} e */
function cgs_touchMove(e) {
  const p = CGS.pz;
  if (p?.src === 'touch') {
    if (e.touches.length < 2) return;
    if (e.cancelable) e.preventDefault();  // no page zoom, no scroll: the fingers zoom the calendar
    const [a, b] = [e.touches[0], e.touches[1]];
    p.k = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) / p.d0;
    // 2.290.0 A (#3144): sideways = the days (with a small dead zone: each change draws the grid anew), up / down = the hours
    p.kx = cgs_dead(Math.max(CGS_AX, Math.abs(a.clientX - b.clientX)) / p.dx0); p.ky = Math.max(CGS_AX, Math.abs(a.clientY - b.clientY)) / p.dy0;
    p.x = (a.clientX + b.clientX) / 2; p.y = (a.clientY + b.clientY) / 2;
    cgs_pzDraw();
  }
}
document.addEventListener('touchmove', cgs_touchMove, {passive: false});
const cgs_dead = k => k > CGS_DEAD ? k / CGS_DEAD : k < 1 / CGS_DEAD ? k * CGS_DEAD : 1;
function cgs_touchEnd(e) {
  if (!e.touches?.length && CGS_TGT.length) cgs_follow([]);  // every finger lifted
  if (CGS.pz?.src === 'touch') {
    if (e.touches.length >= 2) return;
    CGS.hold = e.touches.length > 0;
    cgs_pzEnd();
  }
}
document.addEventListener('touchend', cgs_touchEnd, {passive: true});
document.addEventListener('touchcancel', cgs_touchEnd, {passive: true});

// ---- 2.1312.0 (#6711): one finger leafs like a page (swipenav.js swn_attach): the grid only, the neighbour as a placeholder
const CGS_LEAF = ['month', 'week', 'day', 'year'];
// 2.1380.0 (#7002): the pinch owns two fingers wholly. A swipe begins only after this much one-finger way (a second finger
// landing a moment late finds none begun), and a second finger ends a begun one at once (o.cut: no glide back, no transform
// left on the grid that the zoom scales - the .2s glide back stayed on it for the whole pinch and eased every step)
const CGS_LOCK = 24;
// the state of the neighbour period (calendar.js calStep, the arrows' step) while fn runs; the shown period stays
function cgs_with(dir, fn) {
  const was = {sel: S.calSel, mon: S.calMonth, tl: S.tlStart};
  try { calStep(dir); return fn(); } finally { S.calSel = was.sel; S.calMonth = was.mon; S.tlStart = was.tl; }
}
function cgs_nbMonth() {  // the month's grid: weekdays and day numbers, no entries
  const [y, m] = S.calMonth.split('-').map(Number), start = weekStartOf(ds(new Date(y, m - 1, 1))), t0 = today();
  let cells = '';
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i), out = pd(d).getMonth() !== m - 1;
    if (i === 35 && out) break;
    cells += `<div class="cell${out ? ' out' : ''}${d === t0 ? ' today' : ''}"><span class="dn">${/*html-ok*/ pd(d).getDate() /* a number */}</span></div>`;
  }
  return `<div class="cal calv">${wdOrder().map(i => `<div class="wd">${esc(WD[i])}</div>`).join('')}${/*html-ok*/ cells /* built above */}</div>`;
}
function cgs_nbWeek() {  // the days' head, an empty all-day row as high as the one shown, the hours (scrolled like the shown ones)
  const {days} = calGridDays(), t0 = today(), H = weekH(), ad = /** @type {HTMLElement|null} */ ($('#view .week:not(.cgs-nbg) .wallday'))?.offsetHeight || 0;
  const up = `transform:translateY(-${/*html-ok*/ $('#wbody')?.scrollTop || 0 /* a number */}px)`;  // the hours where the shown ones are scrolled to
  return `<div class="week calv${S.calMode === 'day' ? ' oneday' : ''}" style="--cols:${days.length};--h:${/*html-ok*/ H /* a number */}px">
    <div class="whead"><div></div>${days.map(d => `<div class="wh${d === t0 ? ' today' : ''}"><span>${esc(WD[pd(d).getDay()])}</span><b>${/*html-ok*/ pd(d).getDate() /* a number */}</b></div>`).join('')}</div>
    <div class="wallday"${ad ? ` style="height:${/*html-ok*/ ad /* a number */}px"` : ''}><div class="wlbl">${esc(tr('all day|short'))}</div>${/*html-ok*/ days.map(() => '<div class="wad"></div>').join('') /* constant */}</div>
    <div class="wbody"><div class="wgutter" style="${/*html-ok*/ up /* numbers */}">${[...Array(24)].map((_, h) => `<div class="wtime" style="top:${/*html-ok*/ h * H /* a number */}px">${esc(fmtTimeLoc(pad(h) + ':00'))}</div>`).join('')}</div>${days.map(d => `<div class="wcol${d === t0 ? ' today' : ''}" style="${/*html-ok*/ up /* numbers */}"></div>`).join('')}</div></div>`;
}
function cgs_nbYear() {  // the twelve months without the tint of the entries
  const y = +S.calSel.slice(0, 4), t0 = today(), none = new Map();
  return `<div class="cyear calv">${/*html-ok*/ [...Array(12).keys()].map(m => cyr_month(y, m, none, t0)).join('') /* calyear.js, escaped there */}</div>`;
}
/** @param {number} dir -> {el}: the neighbour period's empty grid, laid beside the shown one (no ids, never focused) */
function cgs_peek(dir) {
  if (CGS.attaching || !$('#view > .calbar.cbm')) return null;  // swn_attach's prime (no pictures to fetch ahead here)
  CGS.fing = true;  // laid in at the swipe's lock: from now on the redraws wait (cgs_held)
  const box = document.createElement('div');
  box.innerHTML = cgs_with(dir, () => S.calMode === 'year' ? cgs_nbYear() : S.calMode === 'month' ? cgs_nbMonth() : cgs_nbWeek());
  const el = /** @type {HTMLElement} */ (box.firstElementChild);
  el.classList.add('cgs-nbg'); el.inert = true;
  return {el};
}
// the area under the finger: the grid; not in a field / the open "New event" block, not while a drag or a pinch owns the fingers
/** @param {EventTarget|null} t */
const cgs_leafArea = t => CGS.pz || CGS.hold || cgs_busy() || !CGS_LEAF.includes(S.calMode) || cgs_el(t)?.closest('input, textarea, select, .cgnew, .swn-nb') ? null : /** @type {HTMLElement|null} */ (cgs_area(t));
if (typeof swn_attach === 'function') {
  CGS.attaching = true;
  try {
    CGS.sw = swn_attach(document, {area: cgs_leafArea, can: () => CGS_LEAF.includes(S.calMode), peek: cgs_peek,
      go: dir => { CGS.redraw = false; calStep(dir); renderView(); },  // drawn in place: no an_calSlide (the neighbour already stands there)
      busy: () => cgs_busy() || !!CGS.pz || CGS.hold, cut: true, lock: CGS_LOCK});
  } finally { CGS.attaching = false; }
}
// a finger that leafs (from the swipe's lock to the end of its snap): the calendar's own redraws (calendar.js: the events, the
// repeating tasks fetched) and the live ones (liveparts.js lpHold) wait - a grid drawn anew took the moving grid and its
// placeholder away mid-swipe - and are drawn once the snap / the spring back is over
const cgs_leafing = () => !!CGS.fing || !!CGS.sw?.snapping() || !!CGS.pz;  // #7388: + two fingers pinching (no grid drawn under them)
function cgs_held() { if (!cgs_leafing()) return false; CGS.redraw = true; return true; }
function cgs_after() {
  setTimeout(() => {
    if (cgs_leafing()) { cgs_after(); return; }
    const r = CGS.redraw; CGS.redraw = false;
    if (S.viewStale && typeof viewSafeRender === 'function') viewSafeRender();
    else if (r && S.route?.mod === 'cal') renderView();
  }, 260);
}
const cgs_lift = () => { if (!CGS.fing) return; CGS.fing = false; cgs_after(); };  // after swipenav's own end (attached before)
document.addEventListener('touchend', cgs_lift, {passive: true});
document.addEventListener('touchcancel', cgs_lift, {passive: true});

// ---- trackpad / mouse: Ctrl + wheel (a trackpad pinch arrives so in Chrome, Edge, Firefox) zooms, sideways turns the page
($('#view') || document).addEventListener('wheel', e => {  // on the view only: scrolling elsewhere never waits for it
  const a = cgs_area(e.target); if (!a || cgs_busy()) return;
  const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
  if (e.ctrlKey) {
    e.preventDefault();  // not the browser's page zoom
    if (CGS.pz && CGS.pz.src !== 'wheel') return;
    if (!CGS.pz) cgs_pzStart(a, e.clientX, e.clientY, 'wheel');
    const p = CGS.pz;
    // 2.290.0 A (#3144): Ctrl + Shift + wheel (Shift turns it sideways on a Mac) or a sideways Ctrl + wheel = the days
    const dX = e.deltaX * unit, dY = e.deltaY * unit, side = Math.abs(dX) > Math.abs(dY), days = e.shiftKey || side;
    const f = Math.exp(-Math.max(-25, Math.min(25, days && side ? dX : dY)) * .01);
    p.k *= f;
    if (p.week) { if (days) p.kx *= f; else p.ky *= f; }
    p.x = e.clientX; p.y = e.clientY;
    cgs_pzDraw();
    clearTimeout(p.idle); p.idle = setTimeout(() => { if (CGS.pz === p) cgs_pzEnd(); }, 220);  // the pinch has ended
    return;
  }
  const dx = e.deltaX * unit;
  if (!dx || Math.abs(dx) <= Math.abs(e.deltaY * unit)) return;
  e.preventDefault();  // not the browser's history swipe
  let w = CGS.wx;
  if (w?.done) { clearTimeout(w.idle); w.idle = setTimeout(() => { if (CGS.wx === w) CGS.wx = null; }, 250); return; }  // the swipe's run-out
  if (!w) w = CGS.wx = {acc: 0, els: cgs_pages()};
  w.acc += dx;
  clearTimeout(w.idle);
  if (Math.abs(w.acc) >= 110) {
    w.done = true;
    cgs_turn(w.els, w.acc > 0 ? 1 : -1);
    w.idle = setTimeout(() => { if (CGS.wx === w) CGS.wx = null; }, 250);
    return;
  }
  cgs_shift(w.els, -w.acc * .6);
  w.idle = setTimeout(() => { if (CGS.wx !== w) return; CGS.wx = null; cgs_back(w.els); }, 160);
}, {passive: false});
// Safari (Mac, iPad trackpad): a pinch comes as gesture events; on the phone the touch events started the zoom first (the
// gesture is only stopped then: no page zoom)
for (const [ev, fn] of /** @type {[string, (e: any) => void][]} */ ([
  ['gesturestart', e => { if (!CGS.pz && !cgs_busy()) cgs_pzStart(cgs_area(e.target), e.clientX, e.clientY, 'gesture'); }],
  ['gesturechange', e => { const p = CGS.pz; if (p?.src !== 'gesture') return; p.k = p.ky = e.scale || 1; cgs_pzDraw(); }],  // 2.290.0 A (#3144): no direction = the hours
  ['gestureend', () => { if (CGS.pz?.src === 'gesture') cgs_pzEnd(); }],
])) {
  document.addEventListener(ev, e => {
    if (!cgs_area(e.target) && !(CGS.pz && ev !== 'gesturestart')) return;
    e.preventDefault();
    fn(e);
  });
}

// ---- a double tap (double click) on a day of the month opens that day
document.addEventListener('click', e => {
  const c = cgs_el(e.target)?.closest('#view .cal .cell[data-day]');
  if (!c || cgs_el(e.target)?.closest('.ev, .cev, .more, .cgnew, button, a, input')) { CGS.tap = null; return; }
  const d = c.getAttribute('data-day'), now = Date.now(), t = CGS.tap;
  if (t && t.day === d && now - t.at < 400 && Math.hypot(e.clientX - t.x, e.clientY - t.y) < 30) {
    e.stopImmediatePropagation(); e.preventDefault();
    CGS.tap = null;
    cgs_go('day', d, 1, e.clientX, e.clientY);
    return;
  }
  CGS.tap = {day: d, x: e.clientX, y: e.clientY, at: now};
}, true);
