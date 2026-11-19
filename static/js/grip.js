// @ts-check
/* Kalmido web client: THE grip to resize (#7293, docs/dev/kern.md "Resizing: the one grip"). Loaded on demand (module grip,
   static/js/lazyload.js): grip_col / grip_row / grip_corner have stand-ins there, so a start file may call them before the
   module is in - the stand-in loads it and resolves to the handle (`const g = await grip_col(el, {...})` works always).
   Three forms, one behaviour:
     grip_col(el, opts)     el = the grip between two columns (axis x); the size is the width of the panel next to it
     grip_row(el, opts)     el = the grip between two rows (axis y, a horizontal divider); the size is the panel's height
     grip_corner(win, opts) win = a floating window; the module puts a corner grip into it (opts.grip: an own element)
                            and sizes width and height; opts.mode 'dialog' = a centred card (both edges move, a drag counts twice)
   The same for all: pointer events (mouse, pen, touch - also a touch tablet), the keyboard (focusable, arrow keys, Shift = 4
   steps, Home / End = smallest / largest, Enter = default), a double click / double tap = the default size, a tap without
   dragging = a small menu (wider / narrower / default; WCAG 2.5.7), role=separator with aria-valuenow/min/max, out of the way
   while a menu, popover or dialog is open (a grip inside it stays), off on the phone layout (< 768 px, isMobile()).
   The size is a CSS variable: --g-<key> (col / row) or --g-<key>-w / --g-<key>-h (corner), set on opts.scope (default: the
   grip's parent, or the window) - the nearest box whose layout reads it, never the root (#4860: ~20 ms per frame at the root,
   ~1 ms at the box). During a drag it is set once per frame (rafThrottle) on opts.dragScope (default scope) and the content
   reflows live (#4860: no preview line). Stored per device in localStorage under grip:<key> (LS: tasks.grip:<key>; signing
   out wipes it like every tasks.* key - a key the device should keep goes into LS_KEEP, icons.js) unless opts.load / opts.save keep it elsewhere (the account, a list of windows). */
'use strict';

const GRIP_KEY_RE = /^[a-z0-9][a-z0-9_-]*$/i;
const GRIP_STEP = {rem: 1, px: 16, '%': 2}, GRIP_ROUND = {rem: 0.25, px: 1, '%': 0.5};
/** @type {Set<any>} */
const GRIP_LIVE = new Set();  // the handles of grips in the page (refreshed on a resize of the window; tests read it)
const grip_rem = () => parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
const grip_fn = (x, ...a) => typeof x === 'function' ? x(...a) : x;
const grip_off = o => (typeof isMobile === 'function' ? isMobile() : innerWidth < 768) || !!grip_fn(o.off);

// ---- storage: the stored value (null = the default), a legacy key taken over once
/** @param {string} k */
function grip_lsRaw(k) { try { const v = localStorage.getItem(k); return v == null ? undefined : JSON.parse(v); } catch { return undefined; } }
// an old key: 'kalmido.*' or {key, raw: true} = the key as it is; else a key of LS (tasks.<key>)
const grip_legSpecs = o => (Array.isArray(o.legacy) ? o.legacy : o.legacy ? [o.legacy] : []).map(s => typeof s === 'string' ? {key: s} : s);
const grip_legRaw = s => s.raw || s.key.startsWith('kalmido.');
/** @param {any} o @param {(v: any) => boolean} ok @returns {any} */
function grip_read(o, ok) {
  let v = o.load ? o.load() : LS.get('grip:' + o.key, undefined);
  if (v !== undefined) return ok(v) ? v : null;
  for (const s of grip_legSpecs(o)) {
    const old = grip_legRaw(s) ? grip_lsRaw(s.key) : LS.get(s.key, undefined);
    if (old == null) continue;
    v = s.map ? s.map(old) : old;
    if (v == null || !ok(v)) continue;
    grip_write(o, v);
    // taken over: the old keys go (a later reset must not bring an old size back)
    for (const t of grip_legSpecs(o)) { if (grip_legRaw(t)) { try { localStorage.removeItem(t.key); } catch { /* private mode */ } } else LS.del(t.key); }
    return v;
  }
  return null;
}
/** @param {any} o @param {any} v */
function grip_write(o, v) {
  if (o.save) { o.save(v); return; }
  if (v == null) LS.del('grip:' + o.key); else LS.set('grip:' + o.key, v);
}

// ---- the drag: a cover over the page carries the cursor (no ::after on body, #3304), body.pgdrag rests the watchers that fit
// bars to a width (core.js dragRest) and runs them once on release
/** @param {HTMLElement} g @param {string} cls */
function grip_dragOn(g, cls) {
  const c = document.createElement('div'); c.className = 'gcover ' + cls; document.body.appendChild(c);
  g.classList.add('drag'); document.body.classList.add('pgdrag', 'gdrag');
  return () => {
    c.remove(); g.classList.remove('drag');
    if (!document.querySelector('.pgrip.drag, .grip.drag')) { document.body.classList.remove('pgdrag', 'gdrag'); if (typeof dragRestFlush === 'function') dragRestFlush(); }
  };
}
// press, drag, release on a grip; a press without moving is a tap: two within 400 ms = the default, one alone = the menu
/** @param {HTMLElement} g @param {any} h @param {(e: PointerEvent) => any} start */
function grip_wire(g, h, start) {
  let last = 0;
  const later = debounce(() => { if (last && g.isConnected && typeof menu === 'function') menu(g, h.menu()); }, 400);  // core.js, the one delay helper
  const onDown = e => {
    if ((e.pointerType === 'mouse' && e.button !== 0) || grip_off(h.o)) return;
    e.preventDefault(); e.stopPropagation();
    try { g.setPointerCapture(e.pointerId); } catch { /* old engine */ }
    const pid = e.pointerId, x0 = e.clientX, y0 = e.clientY, mv = start(e);
    let moved = false;
    const off = grip_dragOn(g, h.cls);
    const move = ev => { if (ev.pointerId !== pid) return; if (!moved && Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) > 3) moved = true; if (moved) mv(ev.clientX - x0, ev.clientY - y0); };
    const up = ev => {
      if (ev.pointerId !== pid) return;
      g.removeEventListener('pointermove', move); g.removeEventListener('pointerup', up); g.removeEventListener('pointercancel', up);
      mv.end(moved && ev.type === 'pointerup'); off();
      if (moved) return;
      later.cancel();
      if (Date.now() - last < 400) { last = 0; h.reset(); return; }
      last = Date.now();
      if (h.o.menu !== false) later();
    };
    g.addEventListener('pointermove', move); g.addEventListener('pointerup', up); g.addEventListener('pointercancel', up);
  };
  const onDbl = e => { e.preventDefault(); later.cancel(); last = 0; h.reset(); };
  g.addEventListener('pointerdown', onDown); g.addEventListener('dblclick', onDbl);
  return () => { later.cancel(); g.removeEventListener('pointerdown', onDown); g.removeEventListener('dblclick', onDbl); };
}
const grip_say = t => { if (typeof announce === 'function') announce(t); };
/** @param {HTMLElement} g @param {any} o @param {string} label @param {number} now @param {number} min @param {number} max @param {string} text */
function grip_aria(g, o, label, now, min, max, text) {
  g.setAttribute('role', 'separator'); if (g.tabIndex < 0) g.tabIndex = 0;
  g.setAttribute('aria-label', label); if (o.tip !== false) g.title = label;
  g.setAttribute('aria-valuenow', String(Math.round(now * 100) / 100));
  g.setAttribute('aria-valuemin', String(Math.round(min * 100) / 100)); g.setAttribute('aria-valuemax', String(Math.round(max * 100) / 100));
  g.setAttribute('aria-valuetext', text);
}
const grip_unitText = (v, u) => u === 'rem' ? tr('{0} rem', String(v)) : v + ' ' + u;
/** @param {any} o @param {string} what @returns {any} */
function grip_key(o, what) {
  if (!o || !GRIP_KEY_RE.test(String(o.key || ''))) throw new Error(what + ': opts.key must be letters, digits, - or _ (it names --g-<key> and grip:<key>)');
  return {unit: 'rem', ...o};
}

// ---- the line grips: grip_col (axis x) and grip_row (axis y)
/** @param {any} el @param {any} opts */
function grip_col(el, opts) { return grip_line(el, 'x', grip_key(opts, 'grip_col')); }
/** @param {any} el @param {any} opts */
function grip_row(el, opts) { return grip_line(el, 'y', grip_key(opts, 'grip_row')); }
/** opts: key (required), min / max / def (a number or a function, in unit), unit 'rem' (default) | 'px' | '%' (of the scope's
 *  size), edge 'end' (default: the panel lies before the grip, left / above it; dragging right / down makes it bigger) or
 *  'start' (the panel lies after the grip), panel (element or function; default the grip's neighbour on that side), scope /
 *  dragScope (where the variable lives / lives during a drag), step, round, label, legacy, load / save, onChange(v), off(),
 *  menu: false (no menu on a tap), tip: false (no title), place: true (#7303 #7304: the grip is no item of the layout - it
 *  stands absolutely in the scope (a positioned box) on the panel's edge, the middle of the gap; kept there while the panel
 *  or the scope changes size; hidden while the panel is not drawn or fills the scope alone - one column).
 * @param {any} el @param {string} axis @param {any} o */
function grip_line(el, axis, o) {
  if (el._grip) el._grip.destroy();
  const X = axis === 'x', vn = '--g-' + o.key, sgn = o.edge === 'start' ? -1 : 1;
  const scope = o.scope || el.parentElement, dscope = o.dragScope || scope, u = o.unit;
  const panel = () => grip_fn(o.panel) || (o.edge === 'start' ? el.nextElementSibling : el.previousElementSibling);
  const upx = () => u === 'rem' ? grip_rem() : u === 'px' ? 1 : ((X ? scope.clientWidth : scope.clientHeight) || 100) / 100;
  const q = o.round || GRIP_ROUND[u] || 1;
  const lim = () => {
    const mn = Number(grip_fn(o.min, h)) || 0, mx = Number(grip_fn(o.max, h));
    return [mn, mx >= mn ? mx : Infinity];
  };
  const clamp = (v, L = lim()) => Math.min(L[1], Math.max(L[0], Math.round(v / q) * q));
  const measured = () => { const p = panel(); if (!p) return 0; const r = p.getBoundingClientRect(); return Math.round((X ? r.width : r.height) / upx() / q) * q; };
  const def = () => { const d = grip_fn(o.def, h); return d == null || !isFinite(d) ? null : clamp(+d); };
  const ok = v => typeof v === 'number' && isFinite(v);
  let cur = null;
  const now = () => cur != null ? clamp(cur) : def() ?? measured();
  const put = (v, at) => { if (v == null) at.style.removeProperty(vn); else at.style.setProperty(vn, v + u); };
  const label = o.label || tr('Drag to resize · double-click: default size');
  const aria = () => { const L = lim(), v = now(); grip_aria(el, o, label, v, L[0], isFinite(L[1]) ? L[1] : Math.max(v, Math.round(((X ? scope.clientWidth : scope.clientHeight) || 0) / upx())), grip_unitText(v, u)); };
  // #7303 #7304: opts.place - the grip on the panel's far edge, in the scope's coordinates
  const place = () => {
    if (!o.place) return;
    const p = panel(), pr = p && p.getClientRects().length ? p.getBoundingClientRect() : null, sr = scope.getBoundingClientRect();
    if (ro && p && p !== seen) { if (seen) ro.unobserve(seen); ro.observe(p); seen = p; }  // a redraw may bring a new panel
    const on = !!pr && !grip_off(o) && (X ? pr.width < sr.width - 2 : pr.height < sr.height - 2);
    if (el.hidden !== !on) el.hidden = !on;
    if (!on) return;
    const cs = getComputedStyle(scope), gap = parseFloat(X ? cs.columnGap : cs.rowGap) || 0, half = (X ? el.offsetWidth : el.offsetHeight) / 2;
    const at = X ? (sgn > 0 ? pr.right : pr.left) - sr.left - scope.clientLeft + scope.scrollLeft : (sgn > 0 ? pr.bottom : pr.top) - sr.top - scope.clientTop + scope.scrollTop;
    const v = Math.round(at + sgn * gap / 2 - half) + 'px';
    if (el.style[X ? 'left' : 'top'] !== v) el.style[X ? 'left' : 'top'] = v;
  };
  const ro = o.place && typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => { if (el.isConnected) place(); }) : null;
  let seen = null;
  const show = () => { put(cur != null ? clamp(cur) : def(), scope); aria(); place(); };
  const h = {
    el, o, key: o.key, axis, cls: X ? 'x' : 'y',
    get: () => cur, now,
    set(v, quiet) {
      cur = v == null || !ok(+v) ? null : clamp(+v);
      if (cur != null && cur === def()) cur = null;  // the default itself is no stored size
      show(); grip_write(o, cur); if (!quiet && o.onChange) o.onChange(cur, h);
      return cur;
    },
    reset() { h.set(null); grip_say((X ? tr('Default width') : tr('Default height'))); },
    refresh: show,
    destroy() { unwire(); ro?.disconnect(); el.removeEventListener('keydown', key); GRIP_LIVE.delete(h); delete el._grip; },
    menu: () => {
      const st = (o.step || GRIP_STEP[u] || 1) * 4;
      return [{label: (X ? tr('Wider') : tr('Taller')), icon: X ? (sgn > 0 ? 'right' : 'left') : (sgn > 0 ? 'down' : 'up'), fn: () => h.set(now() + st)},
        {label: (X ? tr('Narrower') : tr('Shorter')), icon: X ? (sgn > 0 ? 'left' : 'right') : (sgn > 0 ? 'up' : 'down'), fn: () => h.set(now() - st)},
        {label: (X ? tr('Default width') : tr('Default height')), icon: 'undo', fn: () => h.reset()}];
    },
  };
  const unwire = grip_wire(el, h, () => {
    const L = lim(), w = upx(), v0 = now();
    let v = v0;
    const f = rafThrottle((dx, dy) => { v = clamp(v0 + sgn * (X ? dx : dy) / w, L); put(v, dscope); place(); });
    const mv = (dx, dy) => f(dx, dy);
    mv.end = keep => {
      f.flush();
      if (dscope !== scope) dscope.style.removeProperty(vn);
      if (keep) h.set(v); else show();
      if (keep && o.onEnd) o.onEnd(cur, h);
    };
    return mv;
  });
  const grow = X ? (sgn > 0 ? 'ArrowRight' : 'ArrowLeft') : (sgn > 0 ? 'ArrowDown' : 'ArrowUp');
  const shrink = X ? (sgn > 0 ? 'ArrowLeft' : 'ArrowRight') : (sgn > 0 ? 'ArrowUp' : 'ArrowDown');
  const key = e => {
    if (grip_off(o)) return;
    const st = (o.step || GRIP_STEP[u] || 1) * (e.shiftKey ? 4 : 1), L = lim();
    const to = e.key === grow ? now() + st : e.key === shrink ? now() - st : e.key === 'Home' ? L[0] : e.key === 'End' && isFinite(L[1]) ? L[1] : undefined;
    if (to !== undefined) { e.preventDefault(); e.stopPropagation(); h.set(to); grip_say(grip_unitText(now(), u)); }
    else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); h.reset(); }
  };
  el.addEventListener('keydown', key);
  el.classList.add('grip', 'grip-' + h.cls);
  if (o.place) { el.classList.add('grip-place'); ro?.observe(scope); }
  el.setAttribute('aria-orientation', X ? 'vertical' : 'horizontal');  // the separator line between columns stands upright
  if (!el.dataset.grip) el.dataset.grip = o.key;
  el._grip = h; GRIP_LIVE.add(h);
  cur = grip_read(o, ok); if (cur != null) cur = clamp(cur);
  show();
  return h;
}

// ---- the corner of a floating window
/** opts: key (required), minW / minH / maxW / maxH / def ({w, h}; numbers or functions, in unit; the max defaults to the window
 *  minus 1.5rem), unit 'rem' (default) | 'px', at 'br' (default) | 'bl' | 'tr' | 'tl' (the corner the grip sits in; a window
 *  hanging right-aligned under a button grows to the left: 'bl'), mode 'dialog' (a centred card: both edges move, the grip
 *  follows the pointer at twice the speed), fit: true (never taller than its content, #4993: needs `height:
 *  var(--g-<key>-h, …)` in the window's CSS), grip (an own grip element instead of the module's), scope / dragScope, step,
 *  label, legacy, load / save, onChange(v), off(), menu: false, tip: false. The value: {w, h} in unit, null = the default.
 * @param {any} win @param {any} opts */
function grip_corner(win, opts) {
  const o = {at: 'br', ...grip_key(opts, 'grip_corner')};
  if (win._grip) win._grip.destroy();
  const u = o.unit, vw = '--g-' + o.key + '-w', vh = '--g-' + o.key + '-h', scope = o.scope || win, dscope = o.dragScope || scope;
  const sx = o.at.includes('l') ? -1 : 1, sy = o.at.includes('t') ? -1 : 1, k = o.mode === 'dialog' ? 2 : 1;
  const upx = () => u === 'px' ? 1 : grip_rem(), q = o.round || GRIP_ROUND[u] || 1;
  const own = !o.grip, g = o.grip || document.createElement('div');
  if (own) { g.className = 'grip grip-c grip-' + o.at; win.appendChild(g); } else g.classList.add('grip', 'grip-c');
  const vv = () => window.visualViewport || {width: innerWidth, height: innerHeight};
  const natH = () => {  // the height of the content (fit): the variable at auto for one measurement
    const was = scope.style.getPropertyValue(vh), mh = win.style.maxHeight;
    scope.style.setProperty(vh, 'auto'); win.style.maxHeight = 'none';
    const n = Math.max(win.getBoundingClientRect().height, win.scrollHeight);
    if (was) scope.style.setProperty(vh, was); else scope.style.removeProperty(vh);
    win.style.maxHeight = mh;
    return n / upx();
  };
  const lim = () => {
    const m = 24 / upx();
    let mxH = Number(grip_fn(o.maxH, h)) || vv().height / upx() - m;
    if (o.fit) mxH = Math.min(mxH, natH());
    const mnW = Number(grip_fn(o.minW, h)) || 0, mnH = Math.min(Number(grip_fn(o.minH, h)) || 0, mxH);
    return {mnW, mnH, mxW: Math.max(mnW, Number(grip_fn(o.maxW, h)) || vv().width / upx() - m), mxH: Math.max(mnH, mxH)};
  };
  const cl = (v, a, b) => Math.min(b, Math.max(a, Math.round(v / q) * q));
  const clamp = (v, L = lim()) => v == null ? null : {w: v.w > 0 ? cl(v.w, L.mnW, L.mxW) : 0, h: v.h > 0 ? cl(v.h, L.mnH, L.mxH) : 0};
  const measured = () => { const r = win.getBoundingClientRect(); return {w: Math.round(r.width / upx() / q) * q, h: Math.round(r.height / upx() / q) * q}; };
  const def = () => { const d = grip_fn(o.def, h); return d && (d.w > 0 || d.h > 0) ? clamp(d) : null; };
  const ok = v => !!v && typeof v === 'object' && (v.w > 0 || v.h > 0);
  let cur = null;
  const now = () => { const m = measured(), v = cur ? clamp(cur) : def(); return {w: v?.w || m.w, h: v?.h || m.h}; };
  const put = (v, at) => {
    if (v?.w) at.style.setProperty(vw, v.w + u); else at.style.removeProperty(vw);
    if (v?.h) at.style.setProperty(vh, v.h + u); else at.style.removeProperty(vh);
  };
  const label = o.label || tr('Drag to resize · double-click: default size');
  const aria = () => { const L = lim(), v = now(); grip_aria(g, o, label, v.w, L.mnW, L.mxW, `${grip_unitText(v.w, u)} × ${grip_unitText(v.h, u)}`); };
  const show = () => { put(cur ? clamp(cur) : def(), scope); aria(); };
  const h = {
    el: g, win, o, key: o.key, axis: 'xy', cls: 'c' + o.at,
    get: () => cur, now,
    set(v, quiet) {
      cur = ok(v) ? clamp({w: +v.w || 0, h: +v.h || 0}) : null;
      const d = def(); if (cur && d && cur.w === d.w && cur.h === d.h) cur = null;
      show(); grip_write(o, cur); if (!quiet && o.onChange) o.onChange(cur, h);
      return cur;
    },
    reset() { h.set(null); grip_say(tr('Default size')); },
    refresh: show,
    destroy() { unwire(); g.removeEventListener('keydown', key); if (own) g.remove(); GRIP_LIVE.delete(h); delete win._grip; },
    menu: () => {
      const st = (o.step || GRIP_STEP[u] || 1) * 4, by = d => { const v = now(); h.set({w: v.w + d, h: v.h + d}); };
      return [{label: tr('Larger'), icon: 'plus', fn: () => by(st)}, {label: tr('Smaller'), icon: 'minus', fn: () => by(-st)}, {label: tr('Default size'), icon: 'undo', fn: () => h.reset()}];
    },
  };
  const unwire = grip_wire(g, h, () => {
    const L = lim(), w = upx(), v0 = now();
    let v = v0;
    const f = rafThrottle((dx, dy) => { v = clamp({w: v0.w + sx * k * dx / w, h: v0.h + sy * k * dy / w}, L); put(v, dscope); });
    const mv = (dx, dy) => f(dx, dy);
    mv.end = keep => {
      f.flush();
      if (dscope !== scope) put(null, dscope);
      if (keep) h.set(v); else show();
      if (keep && o.onEnd) o.onEnd(cur, h);
    };
    return mv;
  });
  const key = e => {
    if (grip_off(o)) return;
    const st = (o.step || GRIP_STEP[u] || 1) * (e.shiftKey ? 4 : 1), v = now(), L = lim();
    const to = {ArrowRight: {w: v.w + sx * st, h: v.h}, ArrowLeft: {w: v.w - sx * st, h: v.h}, ArrowDown: {w: v.w, h: v.h + sy * st}, ArrowUp: {w: v.w, h: v.h - sy * st},
      Home: {w: L.mnW, h: L.mnH}, End: {w: L.mxW, h: L.mxH}}[e.key];
    if (to) { e.preventDefault(); e.stopPropagation(); h.set(to); const n = now(); grip_say(`${grip_unitText(n.w, u)} × ${grip_unitText(n.h, u)}`); }
    else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); h.reset(); }
  };
  g.addEventListener('keydown', key);
  g.setAttribute('aria-orientation', 'horizontal');
  if (!g.dataset.grip) g.dataset.grip = o.key;
  win._grip = h; GRIP_LIVE.add(h);
  cur = grip_read(o, ok); if (cur) cur = clamp(cur);
  show();
  return h;
}

// a resize of the window: the limits may have moved (a max of the window's width); grips no longer in the page go
const grip_onResize = rafThrottle(() => { for (const h of [...GRIP_LIVE]) { if (!h.el.isConnected) h.destroy(); else h.refresh(); } });
window.addEventListener('resize', () => grip_onResize());
