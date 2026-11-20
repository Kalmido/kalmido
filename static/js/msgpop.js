// @ts-check
/* Kalmido web client: 2.1130.0 (#6057) the pop-up for new chat messages. Loaded on demand (lazyload.js LD_MODS msgpop) by
   mp_check (liveparts.js) when GET /api/msgpop (agents/msgpop.py) names new messages of other people (team chat: a
   project's conversation, a channel, a group, a direct message, a thread I take part in) or a finished answer / question of
   an agent. No bell entry: the bell stays "waiting for you" (12.11.2026).
   ONE small card at the top edge (picture, sender, first line). It lies over the page and moves nothing (calm view): no
   layout, only position:fixed. A tap opens the chat; it goes by itself after MP_MS, the x / Esc / a swipe sideways or up close it
   earlier; a pointer, a finger or the keyboard focus on it keep it (WCAG 2.2.1, like the toast). Several messages in quick
   succession = one bundled card ("3 new messages from Anna"). Never for the chat that is open right now, never for one's
   own messages. A screen reader hears it (announce). Switch: Settings > Notifications > "Pop-up for new messages" (per
   device, LS msgPop, on by default).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';

const MP_MS = 6000;  // how long the card stays
const MP_SWIPE = 60;  // px sideways / up that close it
const MP_FLING = 0.5;  // px per ms: a flick shorter than MP_SWIPE closes it too
let mp_items = [];  // the messages the card shows now (newest first)

// the chat of a message is open right now (the team view / its window in the side panel / the agent's chat)
function mp_isOpen(m) {
  if (m.src === 'team') {
    if (S.route?.mod === 'team' && S.tc?.rid === m.room_id) return true;
    return typeof cw_has === 'function' && typeof cw_docked === 'function' && cw_docked() && cw_has('t:' + m.room_id);
  }
  const p = $('#achat');
  return S.chat?.aid === m.agent_id && ((!!p && !p.classList.contains('hidden')) || (S.route?.mod === 'agents' && S.route.agent === m.agent_id));
}
const mp_key = m => m.src === 'team' ? 't' + m.room_id + (m.thread ? '.' + m.thread : '') : 'a' + m.agent_id;
const mp_href = m => m.src === 'team' ? (m.thread ? `#msg/t/${m.room_id}/${m.id}` : `#team/${m.room_id}`) : `#agents/${m.agent_id}`;
function mp_text(m) {
  if (m.enc) return tr('Encrypted message');
  return m.text || '';
}
function mp_pic(m) {
  if (avUrl(m.from) || !m.avatar) return av(m.from, m.name, 'avatar');
  return `<span class="avatar pic"><img src="${esc(m.avatar)}" alt="" loading="lazy" decoding="async" draggable="false"></span>`;  // sprung-ok: the .avatar box has its fixed size (app.css), the card is fixed over the page
}
// the card's title: one sender or several, one message or several
function mp_title(items) {
  const names = [...new Set(items.map(m => m.name))], n = items.length, top = items[0];
  const where = top.src === 'team' && top.room && new Set(items.map(mp_key)).size === 1 ? top.room : '';
  if (n === 1) return {who: top.name, where};
  if (names.length === 1) return {who: trn('{0} new message from {1}', '{0} new messages from {1}', n, names[0]), where};
  return {who: trn('{0} new message', '{0} new messages', n), where: names.slice(0, 3).join(', ') + (names.length > 3 ? ' …' : '')};
}

// new messages from mp_check: those of an open chat drop out; the rest joins what the card shows now
function mp_show(items) {
  const fresh = (items || []).filter(m => m && !(S.me && m.from === S.me.id) && !mp_isOpen(m));
  if (!fresh.length) return;
  const el = $('#msgpop'), seen = new Set(mp_items.map(m => m.src + m.id));
  mp_items = [...fresh.filter(m => !seen.has(m.src + m.id)), ...(el ? mp_items : [])].sort((x, y) => (Date.parse(y.at) || 0) - (Date.parse(x.at) || 0) || y.id - x.id);
  if (!mp_items.length) return;
  mp_draw();
}
function mp_draw() {
  let el = /** @type {HTMLElement} */ ($('#msgpop'));
  if (!el) {
    el = document.createElement('div'); el.id = 'msgpop'; el.className = 'msgpop';
    document.body.appendChild(el); mp_wire(el);
  }
  const top = mp_items[0], t = mp_title(mp_items), txt = mp_text(top);
  el.dataset.href = mp_href(top);
  el.innerHTML = `<button type="button" class="mpopen" data-mp="open">${/*html-ok*/ mp_pic(top)}<span class="mptxt"><b class="mpwho">${esc(t.who)}</b>${t.where ? `<small class="mpwhere">${esc(t.where)}</small>` : ''}<span class="mpline">${esc(txt)}</span></span></button>`
    + `<button type="button" class="mpx" data-mp="close" aria-label="${esc(tr('Close'))}" title="${esc(tr('Close'))}">${ic('x', 's')}</button>`;
  el.classList.remove('mpgone'); el.style.transform = '';
  announce(mp_items.length > 1 ? `${t.who}${t.where ? ' · ' + t.where : ''}: ${txt}` : `${tr('New message from {0}', t.who)}: ${txt}`);
  mp_run(MP_MS);
}
// its time: the full one after drawing, half of it after a pointer / the focus left it (core.js debounce, no timer pair of its own)
const mp_hideFull = debounce(() => mp_hide(), MP_MS), mp_hideHalf = debounce(() => mp_hide(), MP_MS / 2);
const mp_keep = () => { mp_hideFull.cancel(); mp_hideHalf.cancel(); };
function mp_run(ms) { mp_keep(); (ms < MP_MS ? mp_hideHalf : mp_hideFull)(); }
function mp_hide() {
  mp_keep(); mp_items = [];
  const el = $('#msgpop'); if (!el) return;
  el.classList.add('mpgone');
  setTimeout(() => { if (el.classList.contains('mpgone')) el.remove(); }, 200);
}
/** @param {HTMLElement} el */
function mp_wire(el) {
  el.addEventListener('click', e => {
    const b = /** @type {HTMLElement} */ (e.target).closest?.('[data-mp]'); if (!b) return;
    if (el.dataset.swiped) { delete el.dataset.swiped; return; }  // the end of a swipe is no tap
    const href = el.dataset.href; mp_hide();
    if (b.dataset.mp === 'open' && href) { if (location.hash !== href) location.hash = href; else route(); }
  });
  el.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); mp_hide(); } });
  // kept while a pointer / the focus is on it, its time runs again after
  const keep = mp_keep, go = () => mp_run(MP_MS / 2);
  el.addEventListener('mouseenter', keep); el.addEventListener('focusin', keep);
  el.addEventListener('mouseleave', go); el.addEventListener('focusout', e => { if (!el.contains(/** @type {Node} */ (e.relatedTarget))) go(); });
  // a swipe sideways or up closes it (#7615): the card sits on the finger (no transition while dragging, the
  // pointer captured so the edge does not lose it), the axis is fixed after the first pixels (sideways or up; down moves
  // nothing), past MP_SWIPE or with a flick it flies out that way, short of it it springs back
  let g = null;
  el.addEventListener('pointerdown', e => { keep(); g = {x0: e.clientX, y0: e.clientY, ax: '', d: 0, p: 0, t: e.timeStamp, v: 0}; });
  el.addEventListener('pointermove', e => {
    if (!g) return;
    const dx = e.clientX - g.x0, dy = e.clientY - g.y0;
    if (!g.ax) {
      if (Math.hypot(dx, dy) <= 6) return;
      g.ax = Math.abs(dx) >= Math.abs(dy) ? 'x' : dy < 0 ? 'y' : '-';
      if (g.ax === '-') return;
      el.classList.add('mpdrag');
      try { el.setPointerCapture(e.pointerId); } catch { /* a synthetic pointer has nothing to capture */ }
    }
    if (g.ax === '-') return;
    const d = g.ax === 'x' ? dx : Math.min(0, dy), dt = e.timeStamp - g.t;
    if (dt > 0) g.v = (d - g.p) / dt;
    g.d = d; g.p = d; g.t = e.timeStamp;
    el.style.transform = g.ax === 'x' ? `translateX(${d}px)` : `translateY(${d}px)`;
  });
  const up = e => {
    if (!g) return;
    const {ax, d, v} = g; g = null;
    el.classList.remove('mpdrag');
    if (ax) { el.dataset.swiped = '1'; setTimeout(() => delete el.dataset.swiped, 400); }  // the end of a swipe is no tap
    if ((ax === 'x' || ax === 'y') && (Math.abs(d) >= MP_SWIPE || (Math.abs(d) > 12 && Math.abs(v) >= MP_FLING && Math.sign(v) === Math.sign(d)))) { mp_fly(el, ax, Math.sign(d)); return; }
    el.style.transform = '';
    if (!(e.pointerType === 'mouse' && el.matches(':hover'))) go();
  };
  el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
}
// out of the screen in the swipe's direction, then gone (with reduced motion at once, no flight)
function mp_fly(el, ax, s) {
  const r = el.getBoundingClientRect();
  el.style.transform = ax === 'x' ? `translateX(${s > 0 ? innerWidth - r.left : -r.right}px)` : `translateY(${-r.bottom - 8}px)`;
  mp_hide();
  if (window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches) el.remove();
}
