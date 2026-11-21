// 2.46.1 (#1635): sections (list view) and board columns: where a dragged section goes -- before the one under the pointer,
// or past the middle of the last one (or below / right of it) = the very end. Shared by the mouse (dnd.js) and the long press
// on a phone (below, like a task: a buzz, the section folds while it is dragged). Held and let go without moving: the menu
// with up / down as before (the way without dragging).
// (#7518): sk = the dragged section's adapter (dnd.js secHandle): 'list' a project's sections (list view, board), another one
// (My tasks: 'mine') its heads marked data-sk (render.js) - the same measuring, its own order and saving (sec.ids / sec.order)
const sb_secKan = (sk = 'list') => sk === 'list' && !!$('#view .kcol[data-kcol]');
// 2.138.0 D (#2060): with swimlanes only the head row's columns (.swlc = a lane's cells)
const sb_secEls = (sk = 'list') => sb_secKan(sk) ? $$('#view .kcol[data-kcol]:not(.swlc)') : $$(sk === 'list' ? '#view .ghead[data-section]' : `#view .ghead[data-sk="${sk}"][data-sid]`).map(h => h.closest('.group') || h);
const sb_secHead = el => el.classList.contains('group') ? el.querySelector('.ghead[data-section], .ghead[data-sid]') || el : el;
// -> {el: the head / column to go before, end: after the last one} or null; el = the element under the pointer, used when
// nothing is laid out (no sizes)
function sb_secSpot(x, y, el, sk = 'list') {
  const kan = sb_secKan(sk), els = sb_secEls(sk), n = sb_dropNear(els, kan ? x : y, kan ? 'x' : 'y', 48);
  if (!n) {
    // 2.193.0 C (#2219): below / right of the last one anywhere in the view = the end (a phone lets go in the bottom
    // auto-scroll strip, under the folded sections and the list's bottom padding, once the list is at its end)
    const vis = els.filter(e => e.getBoundingClientRect().height > 0), last = vis[vis.length - 1], v = $('#view')?.getBoundingClientRect();
    const lr = last?.getBoundingClientRect();
    if (lr && v && v.height > 0 && (kan ? x > lr.right : y > lr.bottom) && x >= v.left && x <= v.right && y >= v.top && y <= innerHeight) return {el: sb_secHead(last), end: true};
    const t = el?.closest?.(sk === 'list' ? '#view .ghead[data-section], #view .kcol[data-kcol]:not(.swlc)' : `#view .ghead[data-sk="${sk}"][data-sid]`); return t ? {el: t, end: false} : null;
  }
  const i = els.indexOf(n.el);
  return n.after && i < els.length - 1 ? {el: sb_secHead(els[i + 1]), end: false} : {el: sb_secHead(n.el), end: n.after};
}
// the new section order with sid moved to spot -> {ids, save()}; null = nothing changes. (#7518): the order and its saving come
// from the section's adapter (a project's: the list's sections, saveSectionOrder; My tasks: the own sections, mseSetOrder)
function sb_secOrder(sid, spot, sk = 'list') {
  const a = sh_ad(sk), s = a?.sec.byId(sid); if (!s || !spot || !a.sec.ids) return null;
  const now = a.sec.ids(s), ids = now.filter(x => x !== sid), tid = secOf(spot.el) ? +secOf(spot.el) : null;
  if (!spot.end && tid === sid) return null;
  const at = spot.end ? ids.length : tid ? ids.indexOf(tid) : 0; if (at < 0) return null;
  ids.splice(at, 0, sid);
  return ids.join() === now.join() ? null : {ids, save: () => a.sec.order(s, ids)};
}
function sb_secMark(spot) {
  $$('#view .dropbefore, #view .dropafter').forEach(x => x.classList.remove('dropbefore', 'dropafter'));
  if (!spot) return;
  if (spot.end) (spot.el.classList.contains('kcol') ? spot.el : spot.el.closest('.group') || spot.el).classList.add('dropafter');
  else spot.el.classList.add('dropbefore');
}
const sb_secFold = (h, on) => { const g = h?.closest('.group, .kcol'); if (!g) return; g.classList.toggle('dragging', on); if (g.classList.contains('group')) g.classList.toggle('sb-secfold', on); };
// touch: dnd.js calls this after the long press on a section header. 2.102.0 (#1998): the drag itself is drag.js (ghost,
// threshold, auto-scroll, Esc); here only where the section goes
let sb_sd = null;
function sb_secHoldStart(h, sid, x, y, sk = 'list') {
  sb_secTouchStop();
  const st = sb_sd = {h, sid, sk, moved: false};
  drg_begin(h, x, y, {
    ghost: {el: h, cls: 'ghost-drag sb-secghost'}, threshold: 6, raf: true, scroll: tdScroller(h),
    scrollBox: sc => tdBox(sc, st), edge: TD_EDGE, step: TD_MAX,  // 2.193.0 C (#2219): the strip above the tab bar, as for a task
    onStart: () => { st.moved = true; },
    onMove: (d, mx, my) => { if (sb_sd !== st) return; const sp = sb_secSpot(mx, my, undefined, st.sk); sb_secMark(sp && sb_secOrder(st.sid, sp, st.sk) ? sp : null); },
    onDrop: (d, mx, my) => {
      const o = sb_secOrder(st.sid, sb_secSpot(mx, my, undefined, st.sk), st.sk);  // measured while the section is still folded
      sb_secTouchStop();
      if (o) o.save();
    },
    // held without moving: the head's menu (2.1151.0 B #3835; was up / down) (on the header now shown: a live update may have drawn it anew)
    onTap: () => {
      sb_secTouchStop();
      const hh = st.h.isConnected ? st.h : $(st.sk === 'list' ? `#view .ghead[data-section="${st.sid}"], #view .khead[data-ksec="${st.sid}"]` : `#view .ghead[data-sk="${st.sk}"][data-sid="${st.sid}"]`); if (hh) secHeadMenu(hh, st.sid, st.sk);
    },
    onCancel: () => sb_secTouchStop(),
  }, st);
  sb_secFold(h, true);
  if (navigator.vibrate) navigator.vibrate(12);
}
function sb_secTouchStop() {
  const st = sb_sd; sb_sd = null;
  if (st && drg_cur && drg_cur.d === st) drg_cancel();
  $$('.sb-secghost').forEach(x => x.remove());
  $$('#view .dropbefore, #view .dropafter').forEach(x => x.classList.remove('dropbefore', 'dropafter'));
  if (st) sb_secFold(st.h, false);
}
