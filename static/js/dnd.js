/* Kalmido web client: Drag & drop (desktop) and swipe (touch).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';

// ------------------------------------------------------------------ drag & drop (desktop)
let dragId = null;
document.addEventListener('dragstart', e => {
  const r = e.target.closest('.trow[draggable="true"], .cal .ev[draggable="true"], .week .ev[draggable="true"], .wev[draggable="true"]'); if (!r) return;
  dragId = +r.dataset.id; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(dragId));
  // 2.19.0 (#667): the drop zones appear right after the drag began; a layout change inside dragstart can end the drag
  setTimeout(() => { if (dragId) document.body.classList.add('tdrag'); }, 0);
  requestAnimationFrame(() => r.classList.add('dragging'));
});
document.addEventListener('dragend', () => { dragId = null; DSE.v = 0; kph_clear(); document.body.classList.remove('tdrag'); $$('.dragging,.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dragging', 'dropbefore', 'dropafter', 'drop')); });
const DROP_SEL = '.trow, .kcol, .quad, .cal .cell, .srow[data-drop], .wcol, .wad, .wh, #view .ghead[data-section], #view .sdrop, #view .sprh[data-sprdrop], #view .ghead[data-key^="ms:"], #view [data-dropnew]';  // (#343): + the sprint header; (#4395): + the own sections of My tasks; (#7344): + "New section" of My tasks
// lower half of a row = drop after it (so the end of a block / list is reachable)
const dropAfter = (row, y) => { const r = row.getBoundingClientRect(); return y != null && r.height > 0 && y > r.top + r.height / 2; };
// 2.87.9 (#1965): the highlight changes only when the target or its half changes (dragover fires on every mouse move; the
// search for the old highlights and the restyle ran each time). A highlight someone else took away is set again.
let mdLast = null;
function markDrop(el, id, y) {
  const tgt = el && el.closest(DROP_SEL), row = tgt && tgt.classList.contains('trow');
  const ok = !!tgt && !tgt.closest('#detail') && !(row && +tgt.dataset.id === id);
  if (ok && mdLast?.no === tgt) return true;
  if (ok && dropNo(tgt, y, [id])) { mdLast = {no: tgt}; $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop')); return true; }  // (#7344): the core takes nothing there (the drop says why)
  const cls = !ok ? null : row ? (dropAfter(tgt, y) ? 'dropafter' : 'dropbefore') : 'drop', col = row ? tgt.closest('.kcol,.quad') : null;
  if (cls && mdLast && mdLast.tgt === tgt && mdLast.cls === cls && tgt.classList.contains(cls) && (!col || col.classList.contains('drop'))) return true;
  mdLast = null;
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  if (!cls) return false;
  tgt.classList.add(cls); if (col) col.classList.add('drop');
  mdLast = {tgt, cls};
  return true;
}
document.addEventListener('dragover', e => {
  if (!dragId) return;
  if (ml_altOver(e, dragId)) { mdLast = null; kph_off(); dsEdge(e.clientY); return; }  // 2.320.0 (#3289): Alt onto a project in the sidebar = show also there
  if (dgOver(e, dragId)) { mdLast = null; kph_off(); e.preventDefault(); dsEdge(e.clientY); return; }  // 2.43.0 (#1330, #1003): Alt = dependency, a selection, the panel's drop fields
  if (kph_over(e, dragId)) { e.preventDefault(); dsEdge(e.clientY); return; }  // 2.634.0 (#4797): the board's placeholder
  if (markDrop(e.target, dragId, e.clientY)) e.preventDefault();
  dsEdge(e.clientY);
});
// 2.13.4: mouse drags scroll the list too, held near its top or bottom edge (the browser only scrolls the page)
const DSE = {v: 0, raf: 0};
function dsEdge(y) {
  const v = $('#view'); if (!v) return;
  const r = v.getBoundingClientRect(), E = 64, M = 14;
  DSE.v = y < r.top + E ? -M * Math.min(1, (r.top + E - y) / E) : y > r.bottom - E ? M * Math.min(1, (y - (r.bottom - E)) / E) : 0;
  if (DSE.v && !DSE.raf) {
    const step = () => { if (!dragId || !DSE.v) { DSE.raf = 0; return; } v.scrollTop += DSE.v; DSE.raf = requestAnimationFrame(step); };
    DSE.raf = requestAnimationFrame(step);
  }
}
document.addEventListener('drop', async e => {
  if (!dragId) return;
  e.preventDefault();
  const id = dragId; dragId = null;
  if (ml_altDrop(e, id)) return;  // 2.320.0 (#3289): multilist.js
  if (dgDrop(e, id)) { kph_clear(); return; }  // 2.43.0 (#1330, #1003): dragmulti.js
  const kp = kph_drop();  // 2.634.0 (#4797): on the board the placeholder is the spot (before the card after it, else after the one before)
  if (kp) { const r = kp.el.getBoundingClientRect(); dropTask(id, kp.el, kp.row ? (kp.after ? r.bottom - 1 : r.top + 1) : e.clientY); return; }
  dropTask(id, e.target, e.clientY);
});
// 2.634.0 (#4797) computer / tablet (mouse): on the board the other cards make room for the dragged one. A placeholder (.kph,
// the dragged card's height) stands where it will land. The spot is measured against the cards' resting places (taken once
// per column before anything in it moved, in the column's own coordinates), never against the cards moving right now - else
// the spot flickered between before / after; a few px around a boundary keep the spot (KPH_HY). A move of the placeholder
// slides the neighbours with FLIP (transform only, app.css block "2.634.0 (#4797)", only while an_desk()); reduced motion =
// the placeholder alone. The spots right before / after the dragged card itself change nothing: no placeholder there. The
// drop reads its target from the placeholder. My tasks' board (.mbcol, its own columns) and touch (long press) unchanged.
const KPH = {el: null, kc: null, i: -1, h: 0, rest: new WeakMap()};
const KPH_HY = 6;
const kph_cards = kc => [...kc.children].filter(c => c.classList.contains('trow'));
const kph_top = kc => kc.getBoundingClientRect().top - kc.scrollTop;
function kph_rest(kc) {
  let r = KPH.rest.get(kc);
  if (!r) { const top = kph_top(kc); r = kph_cards(kc).map(c => { const b = c.getBoundingClientRect(); return {c, mid: b.top - top + b.height / 2}; }); KPH.rest.set(kc, r); }
  return r;
}
// the cards of these columns slide from where they were drawn to where mutate() put them
function kph_flip(kcs, mutate) {
  kcs = [...new Set(kcs.filter(k => k && k.isConnected))];
  if (!an_desk()) { mutate(); return; }
  const cards = kcs.flatMap(kph_cards), old = cards.map(c => c.getBoundingClientRect().top);
  mutate();
  cards.forEach(c => { c.classList.remove('kflip'); c.style.transform = ''; });
  const moved = cards.filter((c, j) => { const d = old[j] - c.getBoundingClientRect().top; if (Math.abs(d) < .5) return false; c.style.transform = `translateY(${d}px)`; return true; });
  if (!moved.length) return;
  void document.body.offsetWidth;
  for (const c of moved) { c.classList.add('kflip'); c.style.transform = ''; clearTimeout(c._kphT); c._kphT = setTimeout(() => c.classList.remove('kflip'), 260); }
}
function kph_place(kc, i, id) {
  const rest = kph_rest(kc), s = rest.findIndex(r => +r.c.dataset.id === id), noop = s >= 0 && (i === s || i === s + 1);
  const was = KPH.el?.isConnected ? KPH.el.parentElement : null;
  KPH.kc = kc; KPH.i = i;
  if (noop && !was) return;
  kph_flip([was, kc], () => {
    if (noop) { KPH.el.remove(); return; }
    if (!KPH.el) { KPH.el = document.createElement('div'); KPH.el.className = 'kph'; KPH.el.setAttribute('aria-hidden', 'true'); }
    if (!KPH.h) { const d = document.querySelector(`#view .trow.dragging[data-id="${id}"], #view .trow[data-id="${id}"]`); KPH.h = d ? d.getBoundingClientRect().height : 40; }
    KPH.el.style.height = KPH.h + 'px';
    const ref = rest[i]?.c;
    if (ref && ref.parentElement === kc) kc.insertBefore(KPH.el, ref); else kc.appendChild(KPH.el);
  });
}
// dragover: true = the board's column under the mouse took it (placeholder placed, the column marked)
function kph_over(e, id) {
  const t = e.target, col = t && t.closest && !t.closest('#detail') ? t.closest('#view .kanban .kcol[data-kcol]:not(.mbcol)') : null;
  const kc = col && col.querySelector(':scope > .kcards');
  if (!kc || !S.tasks.has(id)) { kph_off(); return false; }
  const rest = kph_rest(kc), rel = e.clientY - kph_top(kc);
  let i = rest.filter(r => r.mid < rel).length;
  if (KPH.kc === kc && Math.abs(i - KPH.i) === 1 && Math.abs(rel - rest[Math.min(i, KPH.i)].mid) < KPH_HY) i = KPH.i;
  if (KPH.kc !== kc || KPH.i !== i) kph_place(kc, i, id);
  if (!col.classList.contains('drop') || $('.dropbefore,.dropafter')) { $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop')); col.classList.add('drop'); }
  mdLast = null;
  return true;
}
// the mouse left the board's columns: the cards slide back
function kph_off() {
  if (KPH.el?.isConnected) { const kc = KPH.el.parentElement; kph_flip([kc], () => KPH.el.remove()); }
  KPH.kc = null; KPH.i = -1;
}
// the drag ended (drop, Esc, elsewhere): all gone at once
function kph_clear() {
  if (KPH.el) KPH.el.remove();
  KPH.el = null; KPH.kc = null; KPH.i = -1; KPH.h = 0; KPH.rest = new WeakMap();
  $$('#view .kcards > .trow.kflip, #view .kcards > .trow[style*="transform"]').forEach(c => { clearTimeout(c._kphT); c.classList.remove('kflip'); c.style.transform = ''; });
}
// the drop: the spot the placeholder stands on -> {el, row, after}, or null without one
function kph_drop() {
  const ph = KPH.el?.isConnected ? KPH.el : null;
  if (!ph) { kph_clear(); return null; }
  let n = ph.nextElementSibling, p = ph.previousElementSibling;
  while (n && !n.classList.contains('trow')) n = n.nextElementSibling;
  while (p && !p.classList.contains('trow')) p = p.previousElementSibling;
  const col = ph.closest('.kcol');
  kph_clear();
  return n ? {el: n, row: true, after: false} : p ? {el: p, row: true, after: true} : col ? {el: col, row: false, after: false} : null;
}
// one drop = one history step (a subtask made standalone and moved counts once)
function dropTask(id, el, clientY) { return histGroup(async () => { if (await swlDrop(id, el)) return dropTask0(id, el, clientY); }); }  // 2.138.0 D (#2060): a swimlane's value first (same step)
// (#7351): a row, a section's head, a column of a board and "New section" belong to the drop core (dragmulti.js: My tasks'
// adapters, the project list's plWhere / plPut - one task = a selection of one); here only the places with a meaning of their
// own: a project / Today / Tomorrow / Trash / Done in the sidebar, a calendar's day or time, a quadrant, the sprint's head
async function dropTask0(id, el, clientY) {
  const t = S.tasks.get(id); if (!t || !el) return;
  // 2.579.0 (#4798): as this device saw it before the drop - a patchTask below changes t at once (outbox, #4568): undo, _prev, lock move
  const before = snapTask(t);
  const side = el.closest('.srow[data-drop]');
  const quad = el.closest('.quad');
  const cell = el.closest('.cal .cell');
  const wcol = el.closest('.wcol'), wad = el.closest('.wad, .wh');
  $$('.dragging,.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dragging', 'dropbefore', 'dropafter', 'drop'));
  document.body.classList.remove('tdrag');
  if (el.closest('#detail')) return;
  // (#7344, #7351): the drop core (dragmulti.js dropRun). Awaited: the same step.
  const core = dropRun([id], el, clientY);
  if (core) { await core; return; }
  const sprh = el.closest('#view .sprh[data-sprdrop]');  // 2.60.0 (#343): dropped on the sprint header
  if (sprh) { spr_dropTask(id, +sprh.dataset.sprdrop); return; }
  if (!(side || cell || wcol || wad || quad)) return;
  if (!canEdit(t)) { roToast(); return; }
  const item = {id};
  if (side) {
    const k = side.dataset.drop;
    if (k.startsWith('l:')) item.list_id = +k.slice(2);
    else if (k === 'inbox') item.list_id = inbox().id;
    else if (k === 'today') item.due = today();
    else if (k === 'tomorrow') item.due = addDays(today(), 1);
    else if (k === 'trash') { deleteTask(id); return; }
    else if (k === 'done') { toggleTask(id); return; }
    else return;
    if (item.list_id && !await mv_ask([id], listById(item.list_id))) return;  // 2.455.0 (#3848): under All the sidebar has other workspaces' projects
    if (item.list_id && t.parent_id) {
      const ad = detachPatch(t);  // 2.1271.0 (#6436)
      try { await patchUndoable(id, {parent_id: null, list_id: item.list_id, section_id: null, ...ad}, tr('Standalone in {0}', lname(listById(item.list_id))), ad); } catch { return; }
      return;
    }
    if (item.list_id && item.list_id !== t.list_id) item.section_id = null;
  } else if (cell) {
    item.due = cell.dataset.day;
  } else if (wcol) {
    const y = clientY - wcol.getBoundingClientRect().top, m = Math.max(0, Math.min(23 * 60 + 45, Math.round(y / weekH() * 4) * 15));
    item.due = wcol.dataset.day; item.due_time = `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  } else if (wad) {
    item.due = wad.dataset.day; item.due_time = null;
  } else if (quad) {
    if (mxQuad(t) === +quad.dataset.quad) return;
    item.priority = +quad.dataset.quad;  // (#3376): Urgent stays Urgent in its quadrant
  }
  if (item.list_id && !canEditList(item.list_id)) { roToast(); return; }
  if (tlkHits(t, item)) { tlkToast(t); render(); return; }  // 2.36.0 (#1118): a locked task keeps its list / day / priority
  // 2.64.1 (#1817): into / out of a list with the lock: a PATCH, so the browser re-encrypts the texts on the way (reorder cannot)
  const xe2e = item.list_id && item.list_id !== before.list_id && typeof le2eOn === 'function' && (le2eOn(item.list_id) || le2eOn(before.list_id));
  if (!xe2e) { Object.assign(t, item); render(); }
  let res;
  try { res = xe2e ? await api('PATCH', `/api/tasks/${id}`, Object.fromEntries(Object.entries(item).filter(([k]) => k !== 'id'))) : await api('POST', '/api/tasks/reorder', {items: [{...item, _prev: dndPrev(before, item)}]}); } catch { /* api() showed it */ return; }
  if (!xe2e && res?.conflicts?.length) addConflicts(id, res.conflicts, t.title);  // 2.270.0 D (#3028): changed elsewhere meanwhile: kept; 2.528.0 B (#4305): the PATCH one api() adds itself
  await load(); render();
  if (sk_moved(res, id)) return;  // 2.577.0 (#3354)
  // a move to another list or day can be undone
  const after = snapTask(S.tasks.get(id)), rev = after && (before.list_id !== after.list_id || before.due !== after.due || (before.due_time || null) !== (after.due_time || null) || before.priority !== after.priority) && reverseOf(before, after);
  if (res?.shifted?.length) { shiftUndo(before, {...after, shifted: res.shifted}, after?.due ? tr('Date: {0}', dayLabel(after.due)) : ''); return; }
  { const wn = rev && before.list_id !== after.list_id && wsc_moveMsg(before.list_id, after.list_id, ''); if (wn) { offerUndo(wn, histFields(histLabel(before, after), [[before, after, UNDO_FIELDS]], {res})); return; } }  // 2.53.0 (#1474): Private -> organisation
  if (rev) offerUndo(before.list_id !== after.list_id ? tr('Moved to {0}', lname(listById(after.list_id))) : before.priority !== after.priority && before.due === after.due ? tr('Priority: {0}', tr([N_('None'), N_('Low'), '', N_('Medium'), '', N_('High'), '', N_('Urgent')][after.priority] || N_('None'))) : after.due ? tr('Date: {0}', dayLabel(after.due)) : tr('Date removed'),
    histFields(histLabel(before, after), [[before, after, UNDO_FIELDS]], {res}));
}

// 2.380 F (#3436): shared by the list and the task view's subtasks. The neighbours of target in the rendered order: its
// siblings (same parent) without the dragged task; 2.36.2 (#1136): completed ones do not count (only the target itself)
const dndNeighbours = (order, target, id) => order.filter(x => x && x.parent_id === target.parent_id && x.id !== id && (x.status === 0 || x.id === target.id));
// the sort of a task put before / after target: between it and its neighbour (same list), else one step beyond
function dndSortAt(rows, target, after) {
  const i = rows.findIndex(x => x.id === target.id);
  if (after) { const next = rows[i + 1]; return next && next.list_id === target.list_id ? (target.sort + next.sort) / 2 : target.sort + 1; }
  const prev = rows[i - 1]; return prev && prev.list_id === target.list_id ? (prev.sort + target.sort) / 2 : target.sort - 1;
}
// 2.270.0 D (#3028): the values the drop changes as this device saw them (server: reorder _prev; the position is never one)
const dndPrev = (before, item) => Object.fromEntries(Object.keys(item).filter(k => k !== 'id' && k !== 'sort').map(k => [k, before?.[k] ?? null]));

// ---- 2.1271.0 (#6436): a subtask made standalone (any way: dragged out, a kanban column, a section, a list of the sidebar, the
// board of My tasks, the selection's "Out of the parent task", outdent / "Make it a main task", the mind map) takes the date
// (with its time) and the priority of its former parent - only into its own EMPTY fields, never over a value of its own;
// assignee and tags stay. The fields join the write that drops parent_id (one request, one history step, the outbox when
// offline). dtToast says so with "Don't adopt", which sets back only those fields (the task stays standalone) through the
// usual batch write (dgApply: history, outbox, every device). A read-only or locked task, or a parent this person does not see
// (not in S.tasks), adopts nothing.
function detachPatch(t) {
  const p = t?.parent_id && S.tasks.get(t.parent_id), o = {};
  if (!p || !canEdit(t) || tlkIs(t)) return o;
  if (!t.due && p.due && !(t.start && t.start > p.due)) { o.due = p.due; if (p.due_time) o.due_time = p.due_time; }  // a time only with its date; a start after it keeps the task without
  if (!(+t.priority) && +p.priority) o.priority = +p.priority;  // 0 = no priority
  return o;
}
const dtHas = ad => !!ad && Object.keys(ad).length > 0;
// several tasks in one write (items = {id: fields}, patch_each): every item that makes a subtask standalone gets what it adopts
// (only fields the item does not set itself); answers [[id, adopted, parent id]] for dtToast
function dtMerge(items) {
  const dt = [];
  for (const [id, it] of Object.entries(items)) {
    const t = S.tasks.get(+id);
    if (!t?.parent_id || !it || !('parent_id' in it) || it.parent_id) continue;
    const ad = Object.fromEntries(Object.entries(detachPatch(t)).filter(([k]) => !(k in it)));
    if (dtHas(ad)) { Object.assign(it, ad); dt.push([+id, ad, t.parent_id]); }
  }
  return dt;
}
// the ones a batch's answer did not change (skipped, conflicts, or still under a parent) drop out of the toast
const dtDone = (dt, j) => { const kept = new Set([...(j?.skipped || []), ...(j?.conflicts || []).map(c => c.id)]); return dt.filter(([id]) => !kept.has(id) && S.tasks.get(id) && !S.tasks.get(id).parent_id); };
// one task out of its parent through a plain PATCH (outdent, "Make it a main task", the mind map): body plus parent_id null and
// what it adopts; the step in the history as patchTask records it, the toast with "Don't adopt" when something was adopted
async function dtPatch(id, body) {
  const t = S.tasks.get(id), pid = t?.parent_id, ad = detachPatch(t);
  const r = await patchTask(id, {...body, parent_id: null, ...ad});
  dtToast(tr('Subtask is now standalone'), [[id, ad, pid]]);
  return r;
}
// the toast after a detach: got = [[task id, adopted fields, former parent id], ...] (the ones without adopted fields drop out).
// Something adopted: msg plus what was adopted, button "Don't adopt" (the Undo of the step stays in the history: ← / Recent
// steps); nothing adopted: msg as before (shown = false, the caller keeps its own toast)
function dtToast(msg, got) {
  got = (got || []).filter(([, ad]) => dtHas(ad));
  if (!got.length) return false;
  const [, ad, pid] = got[0], pt = qn(toastClip(S.tasks.get(pid)?.title || ''));
  const what = got.length > 1 ? trn('Date / priority of the parent task adopted for {0} task', 'Date / priority of the parent task adopted for {0} tasks', got.length)
    : 'due' in ad && 'priority' in ad ? tr('Date and priority of {0} adopted', pt) : 'due' in ad ? tr('Date of {0} adopted', pt) : tr('Priority of {0} adopted', pt);
  toast([msg, what].filter(Boolean).join(' · '), () => dtUndo(got), 8000, tr('Don’t adopt'));
  return true;
}
// "Don't adopt": only fields that still hold the adopted value go back (empty); one batch step (_prev: changed elsewhere meanwhile = kept)
function dtUndo(got) {
  const items = {};
  for (const [id, ad] of got) {
    const t = S.tasks.get(rid(id)); if (!t) continue;
    const b = {}, prev = {};
    for (const [k, v] of Object.entries(ad)) if (k === 'priority' ? +t.priority === +v : nv(t[k]) === nv(v)) { b[k] = k === 'priority' ? 0 : null; prev[k] = v; }
    if ('due' in b && t.due_time && !('due_time' in b)) { b.due_time = null; prev.due_time = t.due_time; }  // no time without its date
    if (dtHas(b)) items[t.id] = {...b, _prev: prev};
  }
  if (!dtHas(items)) return null;
  return dgApply(items, trn('Not adopted for {0} task', 'Not adopted for {0} tasks', Object.keys(items).length));
}

// ---- sections (D3): drop a task onto a section header or into an empty section, reorder sections by their handle
// (list view + kanban columns, mouse), long-press on a task = "Move to section…", on a section header = move up / down
// (#7518): sk = the adapter of the section (DROP_ADAPTERS sec, dragmulti.js): 'list' a project's, 'mine' an own section of My tasks
const secHandle = (sid, sk = 'list') => `<span class="shandle" draggable="true" data-sdrag="${sid}"${sk === 'list' ? '' : ` data-sk="${esc(sk)}"`} title="${esc(tr('Drag to reorder sections'))}" aria-hidden="true">${ic('grip', 's')}</span>`;
const secName = sid => sid ? (S.sections.find(x => x.id === sid)?.name || '') : tr('Unassigned');
// 2.958.0 (#3911): a completed / rejected task moved into a column of that meaning: the move changed no status (a drag out by hand still undoes)
function dnd_kindStayed(before, after) {
  if (!before || !after || !before.status || before.status !== after.status || before.list_id !== after.list_id) return false;
  if ((before.section_id || null) === (after.section_id || null) || before.due !== after.due || (before.due_time || null) !== (after.due_time || null) || before.priority !== after.priority || (before.parent_id || null) !== (after.parent_id || null)) return false;  // 2.958.0 (#3911, review F2): only the section changed; any other change keeps its Undo
  const k = S.sections.find(x => x.id === after.section_id)?.kind;
  return before.status === 2 ? k === 'done' : before.status === -1 && k === 'rejected';
}
// a task into a section, at its top; a subtask becomes a standalone task there (as in kanban); one undo. (#7351): the menu's
// "Move to section…" - the same way as a drop on the section (dragmulti.js dgToSection; taskToSection0 went)
function taskToSection(id, sid) { const t = S.tasks.get(id); return t ? dgToSection([id], t.list_id, sid) : null; }
// 2.41.2 (#1501): the sections of list lid in the order ids, locally (S.sections keeps its slots; the server's sort follows)
const secPut = (lid, ids) => () => {
  const mine = S.sections.filter(s => s.list_id === lid), at = [], old = mine.map(s => s.id);
  S.sections.forEach((s, i) => { if (s.list_id === lid) at.push(i); });
  const ord = [...ids.map(i => mine.find(s => s.id === i)).filter(Boolean), ...mine.filter(s => !ids.includes(s.id))];
  ord.forEach((s, k) => { s.sort = k; S.sections[at[k]] = s; });
  return () => secPut(lid, old)();
};
// the sections of a list in a new order: one request (one transaction), undo sends the old order back
async function saveSectionOrder(lid, ids, msg) {
  if (!canEditList(lid)) { roToast(); return; }
  if (ids.some(i => i < 0)) { ids = await Promise.all(ids.map(secReal)); if (ids.some(i => !i)) return; }  // 2.559.0 (#4659): a section still on its way
  let j;
  const was = S.sections.filter(s => s.list_id === lid).map(s => secId(s.id));  // 2.273.0 B (#3051): the order the drag started from
  try { j = await optWrite(secPut(lid, ids), () => api('POST', `/api/lists/${lid}/sections/order`, {ids, _prev: was})); } catch { return; }  // 2.41.2 (#1501): at once
  if (!j.ok) { toast(tr('Changed in the meantime')); await load(); render(); return; }  // someone else reordered meanwhile: their order stays
  const ord = (ids2, prev) => async () => {
    const r = await api('POST', `/api/lists/${lid}/sections/order`, {ids: ids2.map(secId), _prev: prev.map(secId)});
    return {skipped: r.ok ? [] : [tr('Section order')], none: !r.ok};
  };
  offerUndo(msg || tr('Sections reordered'), histAdd({label: tr('Sections of {0} reordered', lname(listById(lid)) || ''), lids: [lid], undo: ord(j.prev, j.ids), redo: ord(j.ids, j.prev)}));
}
// sections with history steps: added, renamed, deleted (the undo brings it back with its tasks, at its old place)
// 2.559.0 (#4659): a new section shows at once with a stand-in id below 0 (no wait for the answer); what is done with it
// before the answer (a task dropped on it, rename, delete, a new order) waits for its real id (secReal, as fdReal of the
// fields); a refusal takes the row back. The answer swaps the stand-in for the real row (HIST.secmap knows the way)
const SEC_TMP = new Map();
let secSeq = 0;
async function secReal(sid) {
  if (!(sid < 0)) return sid;
  if (HIST.secmap.has(sid)) return HIST.secmap.get(sid);
  return SEC_TMP.has(sid) ? await SEC_TMP.get(sid) : null;
}
async function sectionCreate(lid, name) {
  const tmp = -1e9 - (++secSeq), mine = S.sections.filter(x => x.list_id === lid);
  const row = {id: tmp, list_id: lid, name, sort: mine.length ? Math.max(...mine.map(x => +x.sort || 0)) + 1 : 0};
  let real = null;
  const drop = () => { S.sections = S.sections.filter(x => x.id !== tmp); };
  const put = () => { if (!real && !S.sections.some(x => x.id === tmp)) S.sections.push({...row}); return drop; };  // again on top of a state fetched meanwhile
  const pr = optWrite(put, async () => {
    const r = await api('POST', '/api/sections', {list_id: lid, name});
    const {moved, skipped, ...nr} = r;
    real = nr.id; HIST.secmap.set(tmp, nr.id);
    const i = S.sections.findIndex(x => x.id === tmp);
    if (S.sections.some(x => x.id === nr.id)) drop(); else if (i >= 0) S.sections[i] = nr; else S.sections.push(nr);
    for (const t of S.tasks.values()) if (t.section_id === tmp) t.section_id = nr.id;
    return r;
  });
  SEC_TMP.set(tmp, pr.then(r => r.id, () => null));
  let s;
  try { s = await pr; } catch { return; } finally { SEC_TMP.delete(tmp); }
  render();
  const nm = qn(name.slice(0, 40));
  histAdd({label: tr('Section {0} added', nm), lids: [lid], sid: s.id, ...(s.undo_group ? {srv: true} : {}),  // 2.809.0 (#5476): the server lists the step
    undo: async e => { const r = await api('DELETE', '/api/sections/' + secId(e.sid), {_prev: {name, tasks: []}}); return r.ok ? {} : {skipped: [tr('Section {0}', nm)], none: true}; },
    redo: async e => { const r = await api('POST', '/api/sections', {list_id: lid, name, sort: s.sort}); HIST.secmap.set(secId(e.sid), r.id); return {}; }});
  return s;
}
async function sectionRename(sid, name) {
  if (sid < 0) { sid = await secReal(sid); if (!sid) return; }  // 2.559.0 (#4659): a section still on its way
  const s0 = S.sections.find(x => x.id === sid); if (!s0) return;
  const old = s0.name, lid = s0.list_id;
  try { await optWrite(optSet(() => S.sections.find(x => x.id === sid), {name}), () => api('PATCH', '/api/sections/' + sid, {name})); } catch { return; }  // 2.41.2 (#1501): at once
  if (old === name) return;
  const go = (to, from) => async e => { const r = await api('PATCH', '/api/sections/' + secId(e.sid), {name: to, _prev: {name: from}}); return r.conflicts?.length ? {skipped: [tr('Section {0}', qn(from.slice(0, 40)))], none: true} : {}; };
  histAdd({label: tr('Section renamed to {0}', qn(name.slice(0, 40))), lids: [lid], sid, undo: go(old, name), redo: go(name, old)});
}
// 2.559.0 (#4659): gone at once (its tasks stay without a section), the request behind it; a refusal brings it back
async function sectionDelete(sid) {
  if (sid < 0) { sid = await secReal(sid); if (!sid) return; }
  const s0 = S.sections.find(x => x.id === sid); if (!s0) return;
  const put = () => {
    const at = S.sections.findIndex(x => x.id === sid), was = S.sections[at] || s0, had = [];
    S.sections = S.sections.filter(x => x.id !== sid);
    for (const t of S.tasks.values()) if (t.section_id === sid) { t.section_id = null; had.push(t.id); }
    return () => {
      if (!S.sections.some(x => x.id === sid)) S.sections.splice(at < 0 ? S.sections.length : Math.min(at, S.sections.length), 0, was);
      for (const i of had) { const t = S.tasks.get(i); if (t && t.section_id == null) t.section_id = sid; }
    };
  };
  let r;
  try { r = await optWrite(put, () => api('DELETE', '/api/sections/' + sid)); } catch { return; }
  const sec = r.section || {name: s0.name, sort: s0.sort, list_id: s0.list_id}, nm = qn(sec.name.slice(0, 40));
  const e = histAdd({label: tr('Section {0} deleted', nm), lids: [sec.list_id], sid, tasks: r.tasks || [], ...(r.undo_group ? {srv: true} : {}),  // 2.809.0 (#5476)
    undo: async x => {
      // 2.567.0 A (#4707): the section waits in the trash: back with the same id, its limits and the tasks still free
      const j = r.trash ? await api('POST', `/api/sections/${secId(x.sid)}/restore`) : await api('POST', '/api/sections', {list_id: sec.list_id, name: sec.name, sort: sec.sort, wip_limit: sec.wip_limit ?? null, kind: sec.kind || '', tasks: x.tasks.map(rid)});
      if (j.id !== secId(x.sid)) HIST.secmap.set(secId(x.sid), j.id); x.tasks = j.moved || [];
      return {skipped: (j.skipped || []).map(t => `${histTitle(t)}: ${tr('Section')}`)};
    },
    redo: async x => {
      const j = await api('DELETE', '/api/sections/' + secId(x.sid), {_prev: {name: sec.name, tasks: x.tasks}});
      if (!j.ok) return {skipped: [tr('Section {0}', nm)], none: true};
      x.tasks = j.tasks || []; return {};
    }});
  offerUndo(tr('Section {0} deleted', nm), e);
}
const secIds = lid => S.sections.filter(x => x.list_id === lid).map(x => x.id);
async function moveSection(sid, dir) {
  const s = S.sections.find(x => x.id === sid); if (!s) return;
  const ids = secIds(s.list_id), i = ids.indexOf(sid), j = i + dir;
  if (j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  await saveSectionOrder(s.list_id, ids, dir < 0 ? tr('Section moved up') : tr('Section moved down'));
}
function sectionPicker(anchor, id) {
  const t = S.tasks.get(id); if (!t) return;
  if (!canEdit(t)) { roToast(); return; }
  const secs = S.sections.filter(x => x.list_id === t.list_id), add = canEditList(t.list_id);
  if (!secs.length && !add) return;
  const cur = secs.some(x => x.id === t.section_id) ? t.section_id : null;
  menu(anchor, [...(secs.length ? [{label: tr('Unassigned'), icon: 'list', on: !cur && !t.parent_id, fn: () => taskToSection(id, null)},
    ...secs.map(x => ({label: x.name, icon: 'folder', on: cur === x.id && !t.parent_id, fn: () => taskToSection(id, x.id)}))] : []),
    ...(add ? [...(secs.length ? ['-'] : []), {label: tr('New section…'), icon: 'plus', fn: () => dgToNewSection([id], t.list_id)}  /* (#667), (#7351): name it, the task lands in it; one step */] : [])]);
}
function secHeadMenu(anchor, sid, sk = 'list') {  // (#7518): sk = the section's adapter (an own section of My tasks: 'mine')
  if (sk === 'list') { const s = S.sections.find(x => x.id === sid); if (!s) return; if (!canEditList(s.list_id)) { roToast(); return; } }
  // 2.1151.0 B (#3835): the head's whole menu at once, its "+" (hidden on the phone) on top; up / down went (the head drags).
  // Was 2.46.1 (#1635): Move section up / down and "Section menu…"
  // the add button's own text; the call itself, not a click on it (the hold redraws the list, the button may be a new one by then)
  const ab = anchor.querySelector('.gadd');
  sh_menu(anchor, sk, sid, ab ? [{label: ab.getAttribute('aria-label') || '', icon: 'plus', fn: () => secAddOpen(+ab.dataset.sec || 0, ab.dataset.sk)}, '-'] : []);
}
// (#7518): one drag for every section with a grip - a project's (sk 'list') and an own section of My tasks ('mine'); where it may go
// and the saving come from its adapter (sec.ids / sec.order, dragmulti.js), secdrag.js measures the spot
let secDrag = null, secSk = 'list';
const secOf = el => el.classList.contains('kcol') ? el.dataset.kcol : el.dataset.section ?? el.dataset.sid;
document.addEventListener('dragstart', e => {
  const h = e.target.closest?.('[data-sdrag]'); if (!h) return;
  e.stopPropagation();
  secDrag = +h.dataset.sdrag; secSk = h.dataset.sk || 'list'; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', 'section:' + secDrag);
  requestAnimationFrame(() => sb_secFold(h, true));  // 2.46.1 (#1635): the section folds while it is dragged
}, true);
document.addEventListener('dragover', e => {
  if (secDrag === null) return;
  // 2.46.1 (#1635): anywhere on the sections; past the middle of the last one = the end
  const sp = sb_secSpot(e.clientX, e.clientY, e.target, secSk), ok = !!sb_secOrder(secDrag, sp, secSk);
  sb_secMark(ok ? sp : null);
  if (ok) e.preventDefault();
});
document.addEventListener('drop', e => {
  if (secDrag === null) return;
  e.preventDefault(); e.stopImmediatePropagation();
  const sid = secDrag; secDrag = null;
  const o = sb_secOrder(sid, sb_secSpot(e.clientX, e.clientY, e.target, secSk), secSk);  // (#1635): before the target ("Unassigned" = first) or at the end (measured while folded)
  $$('#view .dropbefore, #view .dropafter, #view .dragging').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'dragging', 'sb-secfold'));
  if (o) o.save();
}, true);
document.addEventListener('dragend', () => { if (secDrag !== null) { secDrag = null; $$('#view .dropbefore, #view .dropafter, #view .dragging').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'dragging', 'sb-secfold')); } });
// touch: long-press a section header (list view, kanban) = drag it (2.46.1 #1635, secdrag.js); held without moving = move up / down
// 2.725.0 (#5177): one mechanism on the head: the hold (450 ms) takes the press from the row menu's long press (multisel.js
// LM_SECHEAD, 500 ms), as the rows of the file store do - let go unmoved = the menu (once), moved past the threshold = the drag
let secHold = null, secHeld = false;
const secLpTake = () => { if (typeof LM_SECHEAD !== 'undefined') ms_lpTake(LM_SECHEAD); };
// a move past the threshold before the hold ends the row menu's long press by itself (multisel.js pointermove, 10 px)
document.addEventListener('touchstart', e => {
  const h = e.target.closest?.('#view .ghead[data-section], #view .khead[data-ksec], #view .ghead[data-sk][data-sid]');
  const sid = h && +(h.dataset.section || h.dataset.ksec || h.dataset.sid), sk = h?.dataset.ksec ? 'list' : h?.dataset.sk || 'list';
  if (!sid || e.target.closest('.iconbtn, .gact')) { secHold = null; return; }
  const p = e.touches[0];
  // (#7518): may it drag? a project's section: the list may be changed; another adapter's: its sec.drag
  const may = () => { const a = sh_ad(sk), s = a?.sec.byId(sid); return !!s && (sk === 'list' ? canEditList(s.list_id) : a.sec.drag(s)); };
  secHold = {h, sid, x: p.clientX, y: p.clientY, timer: setTimeout(() => { if (!secHold) return; secHold.fired = true; secLpTake(); if (!may()) { secHeadMenu(secHold.h, secHold.sid, sk); return; } sb_secHoldStart(secHold.h, secHold.sid, secHold.x, secHold.y, sk); }, 450)};
}, {passive: true});
document.addEventListener('touchmove', e => { if (secHold && !secHold.fired && Math.hypot(e.touches[0].clientX - secHold.x, e.touches[0].clientY - secHold.y) > 8) { clearTimeout(secHold.timer); secHold = null; } }, {passive: true});
function secHoldEnd(e) {
  if (!secHold) return;
  clearTimeout(secHold.timer);
  const f = secHold.fired; secHold = null;
  if (f) { secHeld = true; setTimeout(() => { secHeld = false; }, 400); if (e.cancelable) e.preventDefault(); }
}
document.addEventListener('touchend', secHoldEnd);
document.addEventListener('touchcancel', secHoldEnd);

// ------------------------------------------------------------------ swipe (touch)
// 2.876.0 (#5559): the gesture is the shared row swipe (rowswipe.js); here what a task row does with it. `swiped` stays the
// mark of a drag that just ended (tdDrop / tdHeld): its click opens nothing
let swiped = false;
const SWIPE_BG = dx => dx > 60 ? 'color-mix(in srgb,var(--ok) 25%,var(--bg))' : dx < -60 ? 'color-mix(in srgb,var(--danger) 25%,var(--bg))' : 'var(--bg2)';
rsw_attach({
  at: e => (e.target.closest('.chk') ? null : e.target.closest('#view .trow')),
  can: () => true,
  min: () => 90,
  busy: () => !!(lp && lp.active),  // the long press lifted the row: the finger drags it
  look: (r, dx) => { r.style.background = dx ? SWIPE_BG(dx) : ''; },
  // 2.46.1 (#1559): a swipe that completes the task carries the row on out to the right (like a dismissed news item) instead
  // of snapping back; 2.655.0 (#5085): every touch screen (an_on = phones only)
  out: (r, dir) => dir > 0 && isTouch() && ui_motion(),
  done: r => { if (!r.style.transform) r.style.background = ''; },
  go: (r, dir) => {
    const id = +r.dataset.id;
    if (dir > 0) { const back = () => { rsw_back(r); if (r.isConnected) r.style.background = ''; }; Promise.resolve(toggleTask(id)).then(back, back); return; }  // the list redraws without the row; if it stayed (cancelled, error) it slides back
    // 2.24.0 (UX-09 / UX-14 / UX-37): the short menu names its task, keeps the order of the task menu (date, list, …) and ends
    // with "All…"; "Move to list…" sorts the inbox. 2.25.0 (UX-37): emptying the inbox = putting tasks into lists: there "Move to list…" leads the menu
    const inb = S.tasks.get(id)?.list_id === inbox()?.id;
    // 2.31.0 (#1056): the same entries, in two groups with a small heading (Snooze / Task), delete last and set apart
    snoozeSheet(id, r, [{head: tr('Task')}, ...(inb ? [] : [moveListItem(r, id), moveWsItem(r, id)]), {label: tr('Completed'), icon: 'done', fn: () => toggleTask(id)}, {label: tr('All…'), icon: 'dots', next: 1, fn: () => taskMenu(r, id)}, '-', {label: tr('Delete'), icon: 'trash', cls: 'flag-5', fn: () => deleteTask(id)}], true, [...(inb ? [moveListItem(r, id), moveWsItem(r, id)] : []), {head: tr('Snooze')}]);
  },
});

// long press (380 ms) on a row / chip, then drag: reorder, other kanban column, quadrant, calendar day
let lp = null;
// 2.13.4: a drag that never got its touchend (a second finger, the system taking the gesture, the app going to the
// background) left its ghost on top of the list for good. Every way out of a drag ends here; a new touch first clears
// whatever is left of an old one.
function tdKill() {
  $$('.ghost-drag:not(.side-ghost)').forEach(g => g.remove());
  $('#tdmove')?.remove();
  $$('#view .trow.dragging, #view .ev.dragging, #view .wev.dragging').forEach(x => x.classList.remove('dragging'));
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  dgs_touchMark(null);  // 2.122.3 B (#2334): the middle mark goes too
  document.body.classList.remove('tdrag');
}
function tdCancel() {
  const d = lp; lp = null;
  if (d) { tdOff(d, true); if (drg_cur && drg_cur.d === d) drg_cancel(); }  // 2.193.0 C (#2219): the drag.js side ends too
  tdKill();
}
document.addEventListener('visibilitychange', () => { if (document.hidden && (lp?.active || $('.ghost-drag:not(.side-ghost)'))) tdCancel(); });
window.addEventListener('blur', () => { if (lp?.active) tdCancel(); });
domReady(() => kb_on('first', 'Escape', e => { if (lp?.active) { e.preventDefault(); tdCancel(); } return false; }));  // 2.655.0 (#4998): key registry (keys.js); the key goes on (as before: only its default is taken)
// 2.13.4: held near the top or bottom edge of the list, it scrolls on its own (the deeper in the edge zone, the faster),
// also while the finger stays still
const TD_EDGE = 72, TD_MAX = 16;
function tdScroller(el) {
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    const cs = getComputedStyle(n);
    if (/(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 1) return n;
  }
  return document.scrollingElement || document.documentElement;
}
// 2.13.0 (#453 A4): Kanban by touch: near the left / right edge the board scrolls smoothly, the deeper in the edge zone the
// faster (at most ~1 column per second), with snapping off while dragging; it used to jump a column per touchmove (the
// mandatory snap turned every 16 px into a whole column: 3 columns in 300 ms)
const KB_EDGE = 56, KB_MAX = 5;
function kbEdge(x, y) {
  const k = $('#view .kanban'); if (!k || !lp) return;
  const r = k.getBoundingClientRect(), a = Math.max(0, r.left), b = Math.min(innerWidth, r.right);
  const v = x < a + KB_EDGE ? -KB_MAX * Math.min(1, (a + KB_EDGE - x) / KB_EDGE) : x > b - KB_EDGE ? KB_MAX * Math.min(1, (x - (b - KB_EDGE)) / KB_EDGE) : 0;
  lp.kv = v; lp.kx = x; lp.ky = y;
  if (v && !lp.kraf) {
    k.classList.add('kbscroll');
    const step = () => {
      if (!lp || !lp.active || !lp.kv || !k.isConnected) { if (lp) lp.kraf = 0; return; }
      const before = k.scrollLeft; k.scrollLeft = before + lp.kv;
      if (k.scrollLeft !== before) { const at = document.elementFromPoint(lp.kx, lp.ky); if (!dgs_touchMark(at, lp.id, lp.ky)) markDrop(at, lp.id, lp.ky); }  // 2.122.3 B (#2334)
      lp.kraf = requestAnimationFrame(step);
    };
    lp.kraf = requestAnimationFrame(step);
  }
}
function kbEdgeEnd(st) { if (st.kraf) cancelAnimationFrame(st.kraf); $('#view .kanban.kbscroll')?.classList.remove('kbscroll'); }
// a drop beside the cards of a Kanban column (the gap, the board's padding, the edge) lands in the column under the finger
function kbColAt(x, y) {
  const cols = swlColsAt(y) || $$('#view .kanban .kcol'); if (!cols.length) return null;  // 2.138.0 D (#2060): with swimlanes the lane under the finger
  let best = null, bd = Infinity;
  for (const c of cols) { const r = c.getBoundingClientRect(); if (r.right < 0 || r.left > innerWidth) continue; const d = x < r.left ? r.left - x : x > r.right ? x - r.right : 0; if (d < bd) { bd = d; best = c; } }
  return best;
}
// 2.193.0 C (#2219): the long press on a row / chip and the drag after it run on drag.js (hold = the long press, the ghost,
// auto-scroll at the list's top / bottom, Esc, a second finger cancels, no click after it); here only what is the list's:
// where a task may go and what a drop does. The swipe above stays its own: a move during the hold ends the press (a swipe
// or a scroll, never a drag), after the hold the swipe is off (lp.active).
function tdBox(sc, d = lp) {  // d: the drag (its cache: lp or a section's, secdrag.js)
  const side = !!d?.at?.closest?.('#side');
  // 2.87.9 (#1965): the view's box and the fixed bars are measured once per drag (the drawer's box each frame: it slides in)
  const page = sc === document.scrollingElement || sc === document.documentElement;
  const r = page ? {top: 0, bottom: innerHeight} : side || !d ? sc.getBoundingClientRect() : (d.scR?.sc === sc ? d.scR.r : (d.scR = {sc, r: sc.getBoundingClientRect()}).r);
  if (side || !d) return {top: r.top, bottom: Math.min(r.bottom, innerHeight)};
  // the tab bar / docked add box cover the list's bottom (fixed: no offsetParent, so measured)
  if (d.tb == null) {
    d.tb = Math.min(innerHeight, ...['#tabs', '#view .qdock', '#fab'].map(q => $(q)).filter(e => e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0 && e.getBoundingClientRect().top > innerHeight / 2).map(e => e.getBoundingClientRect().top));
    d.topB = $('#top')?.getBoundingClientRect().bottom || 0;
  }
  return {top: Math.max(r.top, d.topB), bottom: Math.min(r.bottom, d.tb, (visualViewport?.height || innerHeight))};
}
// over the drawer / sidebar its list scrolls (lists further down are reachable), elsewhere the view; not over "Move to project"
function tdScrollEl() {
  const d = lp; if (!d || !d.active || d.onMv) return null;
  const side = d.at?.closest?.('#side');
  return side ? (d.ssc || (d.ssc = tdScroller(d.at))) : (d.sc || (d.sc = tdScroller(d.r.isConnected ? d.r : $('#view'))));
}
// the finger over "Move to project" (measured once per drag)
function tdOnMove(d, x, y) {
  const mv = $('#tdmove'), b = mv && (d.mvR || (d.mvR = mv.getBoundingClientRect()));
  return !!b && x >= b.left - 8 && x <= b.right + 8 && y >= b.top - 8 && y <= b.bottom + 8;
}
// what the finger is over; below the last open row of a list (its bottom padding, the bottom auto-scroll strip with the
// list scrolled to its end) = after that row
function tdAt(x, y) {
  const at = document.elementFromPoint(x, y);
  if (!at || at.closest(DROP_SEL) || !at.closest('#view') || isKanban() || $('#view .cal, #view .week, #wbody')) return {at, y};
  const rows = $$('#view .trow[data-id]:not(.done):not(.ghost)'), last = rows[rows.length - 1], r = last?.getBoundingClientRect();
  return r && r.height > 0 && y > r.bottom && x >= r.left && x <= r.right ? {at: last, y: r.bottom - 1, end: true} : {at, y};
}
function tdStart(t) {
  const r = t.closest?.('#view .trow, #view .ev, #view .wev, #detail .subs .trow');
  // 2.32.0 (#1055): while selecting, a row is dragged by its grip (at once, no long press); elsewhere a tap selects
  const grip = !!t.closest?.('.tgrip');
  if (!r || !r.dataset.id || r.classList.contains('trtrash') || t.closest('.chk, input, .caret') || (S.multiMode && !grip) || r.classList.contains('ghost')) { lp = null; return null; }
  return (lp = {r, id: +r.dataset.id, active: false, grip});
}
// the hold ended: the row lifts
function tdLift(d) {
  if (lp !== d || !S.tasks.has(d.id)) { drg_cancel(); return; }
  d.active = true;  // 2.876.0 (#5559): the row swipe ends itself on the next move (rowswipe.js asks busy())
  d.r.classList.add('dragging');
  document.body.classList.add('tdrag');
  // 2.13.4: "Move to list…" at the top while dragging a task row: drop it there and pick the list (the drawer at the
  // left edge collides with the system's back gesture on Android)
  const t = S.tasks.get(d.id);
  if (d.r.matches('#view .trow') && t && canEdit(t) && S.lists.filter(l => !l.archived && canEditList(l.id)).length > 1) {
    const m = document.createElement('div'); m.id = 'tdmove'; m.className = 'tdmove'; m.innerHTML = `${ic('folder', 's')}<span>${esc(tr('Move to project'))}</span>`;
    document.body.appendChild(m);
  }
  if (navigator.vibrate) navigator.vibrate(12);
}
// once per frame (drag.js raf), also after an auto-scroll step: the mark under the finger, the drawer, the board's edges
function tdOver(d, x, y) {
  if (lp !== d || !d.active) return;
  d.lx = x; d.ly = y;
  const onMv = d.onMv = tdOnMove(d, x, y), mv = $('#tdmove');
  if (mv) mv.classList.toggle('on', onMv);
  const p = tdAt(x, y); d.at = p.at;
  if (onMv) { mdLast = null; $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop')); }
  else if (dsb_mark(dsb_spot(d.id, document.elementFromPoint(x, y), y))) mdLast = null;  // 2.380 F (#3436): among the task view's subtasks
  else if (!dgs_touchMark(p.at, d.id, p.y)) markDrop(p.at, d.id, p.y);  // 2.122.3 B (#2334): the middle of a row = its subtask (dragmulti.js)
  // hold at the left edge: open the list drawer so the task can be dropped on another list
  if (isTouch() && x < 26 && !$('#side').classList.contains('open')) {  // 2.655.0 (#5085): was isMobile(), the tablet too
    if (!d.edge) d.edge = setTimeout(() => { $('#side').classList.add('open'); if (S.sel) $('#detail').style.visibility = 'hidden'; d.opened = true; }, 450);
  } else if (d.edge && x >= 26) { clearTimeout(d.edge); d.edge = null; }
  kbEdge(x, y);
  const wb = $('#wbody'); if (wb && wb !== d.sc) { const r = d.wbR || (d.wbR = wb.getBoundingClientRect()); if (y < r.top + 40) wb.scrollBy(0, -12); else if (y > r.bottom - 40) wb.scrollBy(0, 12); }
}
// every way out of a lifted drag: the row, the drawer, the board's scrolling
function tdOff(d, now) {
  if (lp === d) lp = null;
  clearTimeout(d.edge); kbEdgeEnd(d);
  d.r.classList.remove('dragging');
  if (d.opened) { d.opened = false; const c = () => { closeSide(); $('#detail').style.visibility = ''; }; if (now) c(); else setTimeout(c, 150); }
}
function tdDrop(d, x, y) {
  if (!d.active) { if (lp === d) lp = null; return; }
  const toMove = tdOnMove(d, x, y);  // measured here: the last move may not have had its frame
  tdOff(d);
  // 2.19.0 (#667): a drop zone under the finger is read while the zones still show (tdKill hides them)
  const zone = document.elementFromPoint(x, y)?.closest?.('#view .sdrop'), p = tdAt(x, y);
  tdKill();
  let el = zone || p.at;
  if (toMove) { S.kf = d.id; setTimeout(() => openPalette('move'), 0); return; }
  swiped = true; setTimeout(() => { swiped = false; }, 400);
  if (el && isKanban() && !el.closest(DROP_SEL) && el.closest('#view')) el = kbColAt(x, y) || el;  // #453 A4
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  const sb = dsb_spot(d.id, document.elementFromPoint(x, y), y); if (sb) { dsb_drop(d.id, sb); return; }  // 2.380 F (#3436)
  if (el && dgs_touchDrop(el, d.id, p.y)) return;  // 2.122.3 B (#2334): onto the middle of a row = its subtask
  // after the last row also when the list moves once the drop zones go (it was scrolled into their room)
  if (el) dropTask(d.id, el, zone ? y : p.end ? 1e9 : p.y);
}
// held without moving
function tdHeld(d) {
  if (!d.active) { if (lp === d) lp = null; return; }
  tdOff(d); tdKill();
  swiped = true; setTimeout(() => { swiped = false; }, 400);
  if (d.r.closest('#view') && isKanban() && S.sections.some(x => x.list_id === S.tasks.get(d.id)?.list_id)) sectionPicker(d.r, d.id);  // "Move to column…"
  // 2.1151.0 B (#3835): held and let go unmoved = the task's menu with "Select" on top (the row has no symbols on the phone,
  // the menu has them all); was 2.32.0 (#1055): the hold selected the task at once. A subtask of the task view: its menu
  else if (d.r.matches('#view .trow, #detail .subs .trow') && !isKanban() && !d.grip) tdRowMenu(d.r, d.id);
}
// 2.1151.0 B (#3835): the menu of a held task row; read-only = the title, "Select" and "Open details" (taskMenu shows only a hint there)
function tdRowMenu(r, id) {
  const t = S.tasks.get(id); if (!t || !r.isConnected) return;
  const sel = !!r.closest('#view');
  if (canEdit(t)) { taskMenu(r, id, {select: sel}); return; }
  menu(r, [...cm_selHead(t.title, sel ? () => { S.multiMode = true; S.multi.add(id); S.multiLast = id; render(); } : null), {label: tr('Open details'), icon: 'edit', fn: () => openDetail(id)}]);
}
// 2.1151.0 B (#3835): a row of the trash (no drag, not in S.tasks): the long press opens what its two buttons do (hidden on the phone)
domReady(() => ms_rowMenu('#view .trow.trtrash', r => ms_btnMenu(r, '[data-act="restore"], [data-act="purge"]', r.querySelector('.ttl')?.textContent.trim() || '')));  // multisel.js loads later
document.addEventListener('touchstart', e => {
  if ((e.touches?.length || 0) > 1) return;  // a second finger: drag.js cancels the drag
  if (lp?.active || $('.ghost-drag:not(.side-ghost)')) tdCancel();  // 2.13.4: a drag whose end got lost: its ghost goes
}, {passive: true});
drg_attach(document, {
  mouse: false, onTarget: true,  // 2.13.4: a live update that redraws the list mid-drag must not cut the touch off
  hold: d => d.grip ? 0 : 380, holdMove: 8, raf: true,
  ghost: {el: d => d.r, cls: 'ghost-drag'},
  scroll: tdScrollEl, scrollBox: tdBox, edge: TD_EDGE, step: TD_MAX,
  start: tdStart, onHold: tdLift, onMove: tdOver, onDrop: tdDrop, onTap: tdHeld,
  onCancel: d => { if (!d.active) { if (lp === d) lp = null; return; } tdOff(d); tdKill(); },
});
// 2.38.0 (#1178): on a touch screen the long press on a task row (its title too) is the app's: the browser's own menu (Copy,
// Select all, Search) never opens over it. When the browser took the press away from the app (touchcancel, so no selection
// above), its menu event opens the row's menu instead (2.1151.0 B #3835; was: the selection). A mouse (also in a narrow window) keeps the browser's menu.
document.addEventListener('contextmenu', e => {
  const r = e.target.closest?.('#view .trow[data-id]');
  if (!r || !(e.pointerType ? e.pointerType === 'touch' : isTouch()) || e.target.closest('input,textarea,.ttlin')) return;
  e.preventDefault();
  const id = +r.dataset.id;
  if (lp || S.multiMode || isKanban() || !S.tasks.has(id) || r.classList.contains('ghost')) return;
  tdRowMenu(r, id);  // 2.1151.0 B (#3835): the row's menu, as the hold
});

// ---- 2.380 F (#3436): the subtasks of the task view sorted by dragging, only among themselves (not out of the task, not into
// another one): the mouse drags the row itself (its own drag, caught here before the list's handlers), touch the long press of
// tdStart. The same sort field as in the list (dndSortAt), completed ones are no neighbours, only with the right to edit.
// dragmulti.js keeps leaving #detail alone.
// -> {target, after, row} for the dragged task id over el, or null (not a sibling here, read-only, itself)
function dsb_spot(id, el, y) {
  const box = $('#detail .subs'), t = S.tasks.get(id);
  if (!box || !t || !el?.closest || !box.contains(el) || !box.querySelector(`.trow[data-id="${id}"]`) || !canEdit(t)) return null;
  let row = el.closest('.trow[data-id]');
  if (!row || !box.contains(row)) {  // the box's free room below the rows = after the last one
    const rs = [...box.querySelectorAll(':scope > .trow[data-id]')], last = rs[rs.length - 1];
    if (!last || y <= last.getBoundingClientRect().bottom) return null;
    row = last; y = 1e9;
  }
  const target = S.tasks.get(+row.dataset.id);
  if (!target || target.id === id || target.parent_id !== t.parent_id) return null;
  return {target, after: dropAfter(row, y), row};
}
function dsb_mark(sp) {
  if (!sp) return false;
  const cls = sp.after ? 'dropafter' : 'dropbefore';
  if (!sp.row.classList.contains(cls)) { $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop')); sp.row.classList.add(cls); }
  return true;
}
async function dsb_drop(id, sp) {
  $$('.dropbefore,.dropafter,.drop,.dragging').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop', 'dragging'));
  const t = S.tasks.get(id), box = $('#detail .subs'); if (!t || !box) return;
  const order = [...box.querySelectorAll('.trow[data-id]')].map(r => S.tasks.get(+r.dataset.id));
  const item = {id, sort: dndSortAt(dndNeighbours(order, sp.target, id), sp.target, sp.after)};
  if (item.sort === t.sort) return;
  const before = snapTask(t);
  Object.assign(t, item); render();
  let res;
  try { res = await api('POST', '/api/tasks/reorder', {items: [{...item, _prev: dndPrev(before, item)}]}); } catch { await load().catch(() => {}); render(); return; }
  if (res?.conflicts?.length) addConflicts(id, res.conflicts, t.title);  // 2.270.0 D (#3028)
  await load().catch(() => {}); render();
}
document.addEventListener('dragover', e => {
  if (!dragId) return;
  const sp = dsb_spot(dragId, e.target, e.clientY); if (!sp) return;
  e.preventDefault(); e.stopPropagation(); mdLast = null; dsb_mark(sp);
}, true);
document.addEventListener('drop', e => {
  if (!dragId) return;
  const sp = dsb_spot(dragId, e.target, e.clientY); if (!sp) return;
  e.preventDefault(); e.stopPropagation();
  const id = dragId; dragId = null; document.body.classList.remove('tdrag');
  dsb_drop(id, sp);
}, true);
