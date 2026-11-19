/* Kalmido web client: "My tasks" in the person's own order (2.40.0, #1344).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md).
   - the view menu switches between "Own order" (default) and "Grouped by list" (setting mine_view: own | lists)
   - dragging a task in "My tasks" changes only the person's own order (PUT /api/tasks/mine-order, queued offline like the other
     task writes; /api/state: mine_order {task id: pos}); tasks.sort of the shared list stays untouched
   - new and newly assigned tasks (no place yet) stand on top, newest first
   - "Own order": a grey subtitle "List › Section" under every task, a tap opens the list
   - "Grouped by list": the groups can be put in an own order (#1221); a task dropped into another group moves to that list */
'use strict';

const moView = () => S.settings?.mine_view === 'lists' ? 'lists' : 'own';
const moActive = () => S.route.mod === 'tasks' && S.route.key === 'assigned';
const moOwn = () => moActive() && moView() === 'own';
// what counts as mine: assigned to me or one of my groups; without collaboration every task of my lists (#1344: always shown)
const moPred = () => collab() ? mineAssigned : mineTask;
// 2.363.3 (#3133): S.mineBase = the order the server confirmed, sent as _prev: an order that waited offline does not overwrite one set elsewhere
const moIds = o => Object.entries(o).sort((a, b) => a[1] - b[1]).map(x => +x[0]);
const moFromState = j => { mtFromState(j); mseFromState(j); if (OUT.q.some(e => e.url === '/api/tasks/mine-order')) return S.mineOrder || {}; S.mineBase = moIds(j.mine_order || {}); return j.mine_order || {}; };
const moPos = t => { const p = S.mineOrder?.[t.id]; return p == null ? null : +p; };
function moCmp(a, b) {
  const x = moPos(a), y = moPos(b);
  if (x == null && y == null) return (b.created_at || '').localeCompare(a.created_at || '') || b.id - a.id;  // not placed yet: newest first
  if (x == null) return -1;
  if (y == null) return 1;
  return x - y || a.id - b.id;
}
const moSort = arr => arr.sort(moCmp);
// every task of "My tasks" in the current own order (unfiltered: a view filtered to favourites keeps the hidden tasks' places)
function moAll() {
  const p = moPred(), m = openTasks(true).filter(t => !t.context && p(t)), ids = new Set(m.map(t => t.id));
  return moSort(m.filter(t => !t.parent_id || !ids.has(t.parent_id)));
}
async function moSave(ids, secs) {  // 2.569.0 (#4395): secs = {task id: own section id} put there by hand
  S.mineOrder = Object.fromEntries(ids.map((id, i) => [id, i]));
  if (secs && S.mineSecs) S.mineSecs.tasks = {...S.mineSecs.tasks, ...secs};
  render();
  const send = ids.filter(id => id > 0), seen = S.mineBase;
  S.mineBase = send;  // the next drag builds on this one
  try {
    const r = await api('PUT', '/api/tasks/mine-order', {ids: send, ...(seen ? {_prev: {ids: seen}} : {}), ...(secs ? {secs} : {})});
    if (r?.order_kept) { toast(tr(MO_KEPT)); await load(); render(); }
  } catch { if (S.mineBase === send) S.mineBase = seen; /* api() showed it; the server never confirmed this order; offline it waits in the outbox */ }
}
// ---- (#7344): the adapter of "My tasks" for the drop core (dragmulti.js DROP_ADAPTERS): one way for a drag of one task
// and of a selection (dnd.js, dragmulti.js), the menu "Move to section…" and "New section" (mseMoveTo, mseMoveToNew).
// A place: {sid} an own section (null = without one), {lid} a project of "Grouped by project", tid / after = before / after that
// task (tid in the selection = the selection at its place), none = on top of the section. Gone: moDrop, moDropMany, mseDrop,
// mseDropMany, mseDropHead (they were three ways, audit #5731).
const MO_NOPLACE = N_('Nothing changes here: drop onto a task of your own order or onto one of your own sections.');
const MO_RECENT = N_('“Recently assigned” takes no tasks: drop them into another section.');
const MO_KEYS_OFF = /^(pinned|kb:|mt:|tm:)/;  // groups of My tasks without an own place: Pinned, Unassigned in your projects, hidden projects
function moWhere(tgt, ids = []) {
  if (moBoard()) return null;  // the board: its own adapter below (#7354)
  if (tgt.kind === 'new') return mseOn() ? {fresh: true} : null;
  const lists = moView() === 'lists';
  if (tgt.kind === 'head') {
    const k = tgt.key || '';
    if (k.startsWith('ms:') && mseOn()) { const s = mseList().find(x => x.id === +k.slice(3)); return !s ? {no: true} : s.kind === 'recent' ? {no: tr(MO_RECENT)} : {sid: s.id}; }
    if (lists && /^l:\d+$/.test(k)) { const r = tgt.el.closest('.group')?.querySelector('.trow'); return {lid: +k.slice(2), tid: r ? +r.dataset.id : null, after: false}; }
    return {no: tr(MO_NOPLACE)};
  }
  const t = S.tasks.get(tgt.tid);
  if (!t) return {no: true};
  if (ids.length === 1 && ids[0] === t.id) return {no: true};  // onto itself
  if (MO_KEYS_OFF.test(tgt.gkey)) return {no: tr(MO_NOPLACE)};
  if (t.parent_id && !moAll().some(x => x.id === t.id)) return {sub: true, row: tgt.row, after: tgt.after};  // a subtask's row: beside it under its parent (the project's way)
  if (lists) return {lid: t.list_id, tid: t.id, after: tgt.after};
  if (!mseOn()) return {tid: t.id, after: tgt.after};
  const sid = tgt.gkey.startsWith('ms:') ? +tgt.gkey.slice(3) : null, s = sid && mseList().find(x => x.id === sid);
  if (s?.kind === 'recent') return {no: tr(MO_RECENT)};
  return {sid: s ? s.id : null, tid: t.id, after: tgt.after};
}
// a task of the view that is not in the own order yet but goes in when it is dropped there: a subtask comes out of its parent
// (#6436: it fills its empty date / priority from the parent), a task nobody has ("Unassigned in your projects", #1219; with
// collaboration only) is assigned to me (decision on #7344) - both in the same step as the new place
const moNeedsMe = t => collab() && !mineAssigned(t);
const moCanTake = t => !!t && !t.context && canEdit(t) && (!!t.parent_id || (moNeedsMe(t) && kbSoloList(listById(t.list_id))));
const moSnap = ids => ({ids: moIds(S.mineOrder || {}), secs: Object.fromEntries(ids.map(id => [id, S.mineSecs?.tasks?.[id] ?? null]))});
async function moBack(s) { await moSave(s.ids, s.secs); return {}; }
// the order with the moved tasks (put, in this order) at the place w
function moFlat(put, w) {
  const mv = new Set(put), keep = w.tid != null && mv.has(w.tid) ? w.tid : null, base = moAll().filter(y => !mv.has(y.id) || y.id === keep);
  let flat = base.map(y => y.id);
  if (mseOn()) {  // own sections: the shown ones in their order ("Recently assigned" keeps no place)
    const x = mseCtx(); flat = [];
    for (const o of x.own) flat.push(...base.filter(y => mseOf(y, x) === o.id).map(y => y.id));
    flat.push(...base.filter(y => mseOf(y, x) === null).map(y => y.id));
  }
  if (keep != null) { flat.splice(flat.indexOf(keep), 1, ...put); return flat; }
  let at = w.tid != null && flat.includes(w.tid) ? flat.indexOf(w.tid) + (w.after ? 1 : 0) : -1;
  if (at < 0 && w.sid != null) { const x = mseCtx(), first = base.find(y => !mv.has(y.id) && mseOf(y, x) === w.sid); at = first ? flat.indexOf(first.id) : flat.length; }
  if (at < 0) at = 0;
  flat.splice(at, 0, ...put);
  return flat;
}
// the whole gesture: out of a parent, assigned to me, into another project ("Grouped by project"), then the own order and
// section - one step of the history (histGroup: the tasks' batch on the server, the own order as this device's own part)
async function moPut(ids, w) {
  if (w.sub) return dgBlock(ids, w.row, w.after, true);
  ids = dgRoots([...new Set(ids)].filter(i => S.tasks.get(i)));
  const lid = w.lid ?? null, l = lid != null ? listById(lid) : null;
  const away = l ? ids.filter(i => S.tasks.get(i).list_id !== lid) : [];
  if (away.length && !canEditList(lid)) { roToast(); return; }
  if (away.length && !await mv_ask(away, l)) return;  // (#3848)
  return histGroup(async () => {
    if (LS.get('sort2.' + S.route.key, null)) LS.del('sort2.' + S.route.key);  // a column's sort hid the own order: a drop shows it again (as a project's manual drop)
    const mine = new Set(moAll().map(x => x.id)), items = {}, put = [], ro = [], out = [];
    let subs = 0, mes = 0;
    for (const id of ids) {
      const t = S.tasks.get(id), it = {};
      if (!mine.has(id)) {
        if (!moCanTake(t)) { (t && !t.context && !canEdit(t) ? ro : out).push(id); continue; }
        if (t.parent_id) { it.parent_id = null; subs++; }
        if (moNeedsMe(t)) { it.assignee_id = S.me.id; mes++; }
      }
      if (away.includes(id)) {
        if (!canEdit(t)) { ro.push(id); continue; }
        Object.assign(it, {list_id: lid, section_id: null}, t.parent_id ? {parent_id: null} : {});
      }
      if (Object.keys(it).length) items[id] = it;
      put.push(id);
    }
    if (!put.length) { toast([ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '', out.length ? tr(MO_NOPLACE) : ''].filter(Boolean).join(' · ') || tr('Nothing to move')); return; }
    const n = put.length, lab = w.sid != null ? trn('{0} task moved to section {1}', '{0} tasks moved to section {1}', n, mseName(mseList().find(x => x.id === w.sid) || {})) : away.length ? trn('Moved {0} task to {1}', 'Moved {0} tasks to {1}', n, lname(l)) : trn('{0} task moved', '{0} tasks moved', n);
    let dt = [], fail = 0;
    if (Object.keys(items).length) {
      const r = await dgApply(items, lab, [], {quiet: true});
      if (!r) return;  // api() said why; nothing moved
      dt = r.dt;
      const kept = new Set([...(r.j?.skipped || []), ...(r.j?.conflicts || []).map(c => c.id)]);
      const ni = Object.keys(items).length;
      fail = Math.max(put.filter(i => kept.has(i)).length, ni - (r.j?.count ?? ni));  // locked, changed elsewhere, refused: named, kept where they were
      for (const i of kept) if (put.includes(i)) put.splice(put.indexOf(i), 1);
    }
    const was = moSnap(put);
    await moSave(moFlat(put, w), w.sid !== undefined && mseOn() ? Object.fromEntries(put.map(id => [id, w.sid])) : null);
    const now = moSnap(put), e = histAdd({label: lab, undo: () => moBack(was), redo: () => moBack(now)});
    const msg = [lab, mes ? tr('Assigned to me') : '', subs ? trn('{0} subtask is now standalone', '{0} subtasks are now standalone', subs) : '',
      fail ? trn('{0} task not changed', '{0} tasks not changed', fail) : '', ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '',
      out.length ? tr(MO_NOPLACE) : ''].filter(Boolean).join(' · ');
    if (!dtToast(msg, dt)) offerUndo(msg, e);  // (#6436): "Don't adopt"; the Undo of the whole step stays in the history
  });
}
if (typeof DROP_ADAPTERS !== 'undefined') DROP_ADAPTERS.push({name: 'mine', on: moActive, where: moWhere, put: (ids, w) => w.fresh ? mseMoveToNew(ids) : moPut(ids, w)});
// (#7354, step 2 of the drop core): the board of My tasks as an adapter - a column, and a card (before / after it; its middle stays
// "make subtasks", before the core) mean what the column means (date / priority / list) for one task and for a selection alike
// (mineboard.js mb_drop / mb_dropMany: one step with Undo). Was: a selection onto a card was put into the project's order
const mbWhere = tgt => { const col = (tgt.kind === 'row' ? tgt.row : tgt.kind === 'col' ? tgt.el : null)?.closest?.('#view .mboard .mbcol'); return col ? {col} : null; };
if (typeof DROP_ADAPTERS !== 'undefined') DROP_ADAPTERS.unshift({name: 'mineboard', on: () => moActive() && moBoard(), where: mbWhere,
  put: async (ids, w) => { await loadModule('mineboard'); const t = ids.length === 1 && S.tasks.get(ids[0]); return t ? canEdit(t) ? mb_drop(t, w.col) : roToast() : mb_dropMany(ids, w.col); }});
// the grey subtitle "List › Section" (render.js taskRow, own order only)
function moSubHtml(t) {
  const l = listById(t.list_id); if (!l) return '';
  const sec = t.section_id ? S.sections.find(s => s.id === t.section_id)?.name : '';
  const txt = lname(l) + (sec ? ' › ' + sec : '');
  return `<button type="button" class="mosub" data-go="${esc(keyToHash(l.is_inbox ? 'inbox' : 'l:' + l.id))}" title="${esc(tr('Open {0}', lname(l)))}">${licMark(l, 'lsm')}<span>${esc(txt)}</span></button>`;
}
// the view menu (render.js topMoreItems)
function moViewItems() {
  if (!moActive() || moBoard()) return [];  // 2.156.0 C (#2072): the board has its own columns
  const set = v => () => { if (moView() === v) return; S.settings.mine_view = v; render(); api('PATCH', '/api/settings', {mine_view: v}).catch(() => {}); };
  return [{label: tr('Own order'), icon: 'sort', on: moView() === 'own', fn: set('own')}, {label: tr('Grouped by project'), icon: 'list', on: moView() === 'lists', fn: set('lists')},
    ...(mseOn() ? [{label: tr('Rules…'), icon: 'zap', fn: () => mr_open()}] : []),  // 2.823.0 (#4773): the own rules (minerules.js, loaded on demand)
    ...(moView() === 'own' && !isMobile() ? [{label: tr('Project as a column'), icon: 'columns', on: moListCol(), fn: () => { LS.set('moListCol', !moListCol()); render(); }}] : [])];  // 2.569.0 (#4395)
}

// ---- 2.41.0 (#1365): "Show in My tasks" per list, only for me (PUT /api/lists/<id>/in-mine; /api/state mine_hidden = ids of
// the lists switched off). Their tasks leave "My tasks" for the group "Hidden (N)" at the end (folded until opened, every list
// with "Show the list again"); my assigned tasks of such a list due today or overdue stay visible in the small group "From
// hidden lists" above it. The sidebar counts what "My tasks" shows openly (hidden ones only when due today or overdue).
// The own order (#1344) keeps the hidden tasks' places; the other views do not look at it.
function mtFromState(j) { if (!OUT.q.some(e => /^\/api\/lists\/\d+\/in-mine$/.test(e.url))) S.mineHidden = new Set(j.mine_hidden || []); }
const mtHid = t => !!S.mineHidden?.has(t.list_id);
const mtUrgent = (t, t0 = today()) => !!t.due && t.due <= t0;
const mtCounts = (t, t0) => !mtHid(t) || mtUrgent(t, t0);
const mtShown = id => !S.mineHidden?.has(id);
// views.js groupTasks: the two groups at the end of "My tasks" (hid: hidden roots of my tasks, kb: hidden undated tasks of
// "From your lists, without a date")
function mtGroups(hid, kb) {
  const t0 = today(), urg = hid.filter(t => mtUrgent(t, t0)).sort((a, b) => dueKey(a).localeCompare(dueKey(b)) || a.id - b.id);
  const ord = kbListOrder().map(l => l.id), rest = [...hid.filter(t => !mtUrgent(t, t0)), ...kb]
    .sort((a, b) => ord.indexOf(a.list_id) - ord.indexOf(b.list_id) || moCmp(a, b));
  const out = [];
  if (urg.length) out.push({id: 'mt:urgent', name: tr('From hidden projects'), tasks: urg, cls: 'mturg'});
  if (rest.length) out.push({id: 'mt:hidden', name: tr('Hidden'), tasks: rest, cls: 'mthid', folded: true, byList: true});
  return out;
}
// the head of one list inside "Hidden" (render.js viewListBody, before its first task)
function mtListHead(lid) {
  const l = listById(lid); if (!l) return '';
  return `<div class="mthl">${licMark(l, 'lsm')}<span class="mthn">${esc(lname(l))}</span>${/*html-ok*/ wso_origin(l, 'gorg', true) /* 2.1224.0 (#6188) */}<button type="button" class="linkbtn" data-mt="show" data-id="${l.id}">${esc(tr('Show the project again'))}</button></div>`;
}
async function mtSet(id, on, o = {}) {
  const was = mtShown(id);
  if (was === on) return;
  if (!S.mineHidden) S.mineHidden = new Set();
  if (on) S.mineHidden.delete(id); else S.mineHidden.add(id);
  render();
  try {
    const j = await api('PUT', `/api/lists/${id}/in-mine`, {on});
    if (Array.isArray(j?.mine_hidden)) S.mineHidden = new Set(j.mine_hidden);
  } catch { if (was) S.mineHidden.delete(id); else S.mineHidden.add(id); render(); return; }
  render();
  o.post?.();
  if (!o.quiet) toast(on ? tr('{0} shows in My tasks again', lname(listById(id))) : tr('{0} is hidden in My tasks', lname(listById(id))), () => mtSet(id, was, {...o, quiet: true}));
}
document.addEventListener('click', e => {
  const b = e.target.closest?.('[data-mt="show"]'); if (!b) return;
  e.preventDefault(); e.stopPropagation(); mtSet(+b.dataset.id, true);
}, true);

// ---- 2.156.0 C (#2072): "My tasks" as a board (mineboard.js, module mineboard, loaded on demand): the switch List / Board
// and the board's columns (by due date, priority or list) at the top of the view; settings mine_board (0 | 1) and
// mine_board_by (due | prio | list), per person on every device
const moBoard = () => S.settings?.mine_board === '1';
const moBoardBy = () => ['prio', 'list'].includes(S.settings?.mine_board_by) ? S.settings.mine_board_by : 'due';
function moSetPref(k, v) {
  if (!S.settings || S.settings[k] === v) return;
  S.settings[k] = v; render();
  api('PATCH', '/api/settings', {[k]: v}).catch(() => {});
}
function moSegHtml() {
  if (!moActive()) return '';
  const b = moBoard(), btn = (act, k, on, ico, label) => `<button type="button" class="${on ? 'on' : ''}" data-act="${act}"${k ? ` data-k="${k}"` : ''} aria-pressed="${on}" title="${esc(label)}">${ico ? ic(ico, 's') : ''}<span>${esc(label)}</span></button>`;
  let h = `<div class="mobar"><div class="seg mbseg" role="group" aria-label="${esc(tr('View'))}">${btn('mo-view', 'list', !b, 'list', tr('List'))}${btn('mo-view', 'board', b, 'kanban', tr('Kanban'))}</div>`;  // 2.365.0 (#3010): "Kanban" as in a project
  if (b) h += `<div class="seg mbby" role="group" aria-label="${esc(tr('Columns by'))}">${[['due', N_('Due')], ['prio', N_('Priority')], ['list', N_('Project')]].map(([k, n]) => btn('mo-by', k, moBoardBy() === k, '', tr(n))).join('')}</div>`;
  return h + '</div>';
}
// dnd.js dropTask0: a drop inside the board -> true when handled there (mineboard.js mb_drop)
// (#7354): gone - the board is an adapter of the drop core (dnd.js reaches it through dropRun)
document.addEventListener('click', e => {
  const b = e.target.closest?.('#view .mobar [data-act="mo-view"], #view .mobar [data-act="mo-by"]'); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  if (b.dataset.act === 'mo-view') moSetPref('mine_board', b.dataset.k === 'board' ? '1' : '0');
  else moSetPref('mine_board_by', b.dataset.k);
}, true);

// ---- 2.569.0 (#4395): own sections in the own order (/api/mine-sections, kalmido/tasks/mineorder.py; /api/state mine_sections
// {list, tasks}). Personal: they never change a list, its sections or its order. On top the fixed section "Recently assigned"
// (kind recent: tasks without a place; shown while it has tasks, never renamed or deleted); the first opening makes "Now",
// "Soon", "Someday" (kinds now / soon / later, the name '' = the translated default). 2.823.0 (#4773): a task due today or
// overdue goes into Now through the person's first own rule (server, kalmido/tasks/minerules.py: it writes the section like a
// drag, once per due day; switched off or deleted = it stays where it is). A task with a place but no section stands in the
// topmost section. Deleting a section moves its tasks into the
// topmost one left (Undo brings it back); renaming and deleting carry the version (409 = changed on another device).
const MSE_KIND = {recent: N_('Recently assigned'), now: N_('Now'), soon: N_('Soon'), later: N_('Someday')};
const mseList = () => S.mineSecs?.list || [];
const mseName = s => s.name || tr(MSE_KIND[s.kind] || '');
const mseOn = () => moOwn() && !moBoard() && mseList().length > 0;
const moListCol = () => moOwn() && !isMobile() && LS.get('moListCol', false) === true;  // (4): "Project" as a column (this device)
// #3506 (CI red of 2.614.0, p2569_a): a folding whose PATCH has not come back yet - an answer the server gave before it (the
// DELETE of another section, a state load) carried the old value and folded the section again under the hand that opened it
const mseFoldP = new Map();
const mseKeepFold = ms => { for (const s of ms?.list || []) if (mseFoldP.has(s.id)) s.collapsed = mseFoldP.get(s.id); return ms; };
function mseFromState(j) {
  if (!j.mine_sections) return;
  const q = OUT.q.some(e => e.url === '/api/tasks/mine-order');  // a drag waiting offline keeps its sections
  S.mineSecs = {list: mseKeepFold(j.mine_sections).list || [], rules: j.mine_sections.rules || 0, tasks: q && S.mineSecs ? S.mineSecs.tasks : j.mine_sections.tasks || {}};
}
let mseIniting = false;
async function mseInit() {  // the first opening of the own order: the default sections (once; the server does nothing a second time)
  if (mseIniting || !moOwn() || !S.mineSecs || mseList().length) return;
  mseIniting = true;
  try { const j = await api('POST', '/api/mine-sections/init', {}); if (j?.mine_sections) { S.mineSecs = j.mine_sections; render(); } } catch { mseIniting = false; /* offline: next time */ }
}
// the section a task stands in (id; null = no own section left)
function mseOf(t, x) {
  const p = x.map[t.id];
  if (p && x.ids.has(p)) return p;  // put there by hand: wins
  if (moPos(t) == null && x.rec) return x.rec.id;
  return x.top ? x.top.id : null;
}
function mseCtx() {
  const L = mseList(), own = L.filter(s => s.kind !== 'recent');
  return {rec: L.find(s => s.kind === 'recent'), own, top: own[0], ids: new Set(own.map(s => s.id)), map: S.mineSecs?.tasks || {}};
}
// views.js groupTasks: the groups of the own order (arr = the shown tasks in the own order)
function mseGroups(arr) {
  mrApplySoon();  // 2.823.0 (#4773)
  const x = mseCtx(), by = new Map();
  for (const t of arr) { const k = mseOf(t, x); if (!by.has(k)) by.set(k, []); by.get(k).push(t); }
  const mk = s => {
    const id = 'ms:' + s.id;
    if (s.collapsed) S.collapsed.add(id); else S.collapsed.delete(id);  // the folding of every device (the server keeps it)
    return {id, name: mseName(s), tasks: by.get(s.id) || [], cls: 'mosec' + (s.kind === 'recent' ? ' msrec' : ''), mosec: s};
  };
  const out = x.rec && by.get(x.rec.id)?.length ? [mk(x.rec)] : [];
  out.push(...x.own.map(mk));
  if (by.get(null)?.length) out.push({id: 'ms:none', name: '', tasks: by.get(null)});
  return out;
}
// render.js: the "…" of an own section in its head; the button "New section" under the last one
const mseHeadHtml = g => g.mosec && g.mosec.kind !== 'recent' ? `<button data-rowmenu="mosec" type="button" class="iconbtn gact" data-mse-menu="${g.mosec.id}" title="${esc(tr('More') + ': ' + g.name)}" aria-label="${esc(tr('More') + ': ' + g.name)}">${ic('dots', 's')}</button>` : '';
const mseAddHtml = () => mseOn() ? `<button type="button" class="linkbtn msenew" data-mse-add="1" data-dropnew="1">${ic('plus', 's')}<span>${esc(tr('New section'))}</span></button>` : '';
// (#6962): tasks (ids, in this order) into own section sid - before / after targetId, else on top of it (where its first
// task stands; an empty one = at the end). "Move to section…" of the task menu and of the multi panel; (#7344): the
// drop core's way (moPut: a subtask comes out, a task nobody has is assigned to me, one step of the history)
async function mseMoveTo(ids, sid, targetId = null, after = false) {
  const s = mseList().find(x => x.id === sid);
  if (!s || s.kind === 'recent' || !ids.length) return false;
  await moPut(ids, {sid, tid: targetId, after});
  return true;
}
// 2.1365.0 (#6962): in "My tasks" with own sections (a row of the view, not the task panel) "Move to section…" offers the own
// sections (not "Recently assigned"; a check at the one it stands in) and "New section…"; the project's sections stay reachable
// as "Move to section of <project>…". null = not here (the menu stays as it was).
function mseMenuHere(anchor, ts) {
  if (!mseOn() || anchor?.closest?.('#detail') || !ts.length) return false;
  const mine = new Set(moAll().map(y => y.id));
  return ts.every(t => mine.has(t.id) || moCanTake(t));  // (#7344): also subtasks and "Unassigned in your projects" (they come along)
}
function mseSecPicker(anchor, ids, done = () => {}) {  // done: before the move (the multi panel marks its field changed)
  const x = mseCtx(), ts = ids.map(id => S.tasks.get(id)).filter(Boolean), cur = new Set(ts.map(t => mseOf(t, x)));
  menu(anchor, [...x.own.map(s => ({label: mseName(s), icon: 'columns', on: cur.size === 1 && cur.has(s.id), fn: () => { done(); mseMoveTo(ids, s.id); }})),
    '-', {label: tr('New section…'), icon: 'plus', fn: () => { done(); mseMoveToNew(ids); }}]);
}
async function mseMoveToNew(ids) {
  const n = (await askPrompt(tr('New section'), '', {ok: tr('Create'), input: {placeholder: tr('Name'), max: 200}}))?.trim();
  if (!n) return;
  const j = await mseCall('POST', '/api/mine-sections', {name: n});
  if (j?.id) await mseMoveTo(ids, j.id);
}
function mseMenuItems(anchor, ids, proj) {  // proj = the project's own picker (or null)
  const l = proj && listById(S.tasks.get(ids[0])?.list_id);
  return [{label: tr('Move to section…'), icon: 'columns', next: 1, fn: () => mseSecPicker(anchor, ids)},
    ...(proj && l ? [{label: tr('Move to section of {0}…', lname(l)), icon: 'folder', next: 1, fn: proj}] : [])];
}
async function mseCall(method, url, b) {
  try { const j = await api(method, url, b); if (j?.mine_sections) S.mineSecs = {...mseKeepFold(j.mine_sections), ...(OUT.q.some(e => e.url === '/api/tasks/mine-order') ? {tasks: S.mineSecs.tasks} : {})}; if (j?.order_kept) toast(tr('The sections were changed on another device: that order stays.')); render(); return j; }
  catch (e) { if (e?.status === 409 || e?.status === 404) { await load(); render(); } return null; }  // api() showed the reason; the current state instead of an old one
}
async function mseRename(s) {
  const old = mseName(s), n = (await askPrompt(tr('Rename section'), old, {ok: tr('Rename'), input: {max: 200}}))?.trim();
  if (!n || n === old) return;
  const j = await mseCall('PATCH', `/api/mine-sections/${s.id}`, {name: n, expect_updated_at: s.updated_at});
  if (j?.section) toast(tr('Section renamed'), () => mseCall('PATCH', `/api/mine-sections/${s.id}`, {name: old, expect_updated_at: j.section.updated_at}));
}
async function mseMove(s, d) {
  const ids = mseList().filter(x => x.kind !== 'recent').map(x => x.id), i = ids.indexOf(s.id), k = i + d;
  if (i < 0 || k < 0 || k >= ids.length) return;
  const nw = ids.slice(); nw.splice(i, 1); nw.splice(k, 0, s.id);
  await mseCall('PUT', '/api/mine-sections/order', {ids: nw, _prev: {ids}});
}
async function mseDelete(s) {
  const j = await mseCall('DELETE', `/api/mine-sections/${s.id}`, {expect_updated_at: s.updated_at});
  if (j?.restore) toast(tr('Section deleted'), () => mseCall('POST', '/api/mine-sections', {name: j.restore.name, restore: j.restore}));
}
async function mseAdd() {
  const n = (await askPrompt(tr('New section'), '', {ok: tr('Create'), input: {placeholder: tr('Name'), max: 200}}))?.trim();
  if (n) await mseCall('POST', '/api/mine-sections', {name: n});
}
function mseMenu(anchor, sid) {
  const s = mseList().find(x => x.id === sid); if (!s) return;
  const own = mseList().filter(x => x.kind !== 'recent'), i = own.indexOf(s);
  menu(anchor, [
    {label: tr('Rename'), icon: 'edit', fn: () => mseRename(s)},
    ...(i > 0 ? [{label: tr('Move up'), icon: 'up', fn: () => mseMove(s, -1)}] : []),
    ...(i < own.length - 1 ? [{label: tr('Move down'), icon: 'down', fn: () => mseMove(s, 1)}] : []),
    '-',
    {label: tr('Delete section (tasks stay)'), icon: 'trash', cls: 'flag-5', fn: () => mseDelete(s)},
  ]);
}
document.addEventListener('click', e => {
  const m = e.target.closest?.('#view [data-mse-menu]'), a = !m && e.target.closest?.('#view [data-mse-add]');
  if (m || a) { e.preventDefault(); e.stopPropagation(); if (m) mseMenu(m, +m.dataset.mseMenu); else mseAdd(); return; }
  const h = e.target.closest?.('#view .ghead[data-key^="ms:"]');  // folding: the server keeps it for every device (events.js toggles it here)
  if (!h || e.target.closest('.gact, .shandle') || h.dataset.key === 'ms:none') return;
  const s = mseList().find(x => x.id === +h.dataset.key.slice(3)); if (!s) return;
  const v = s.collapsed = !s.collapsed;
  mseFoldP.set(s.id, v);
  api('PATCH', `/api/mine-sections/${s.id}`, {collapsed: v}).catch(() => {}).finally(() => { if (mseFoldP.get(s.id) === v) mseFoldP.delete(s.id); });
}, true);
// 2.695.0 (#4619): a long press (phone) / right click (computer) on a row opens what its "…" opens (multisel.js lm_btnMenu)
if (typeof lm_btnMenu === 'function') lm_btnMenu('#view .ghead.mosec', '[data-mse-menu]');  // the head of an own section of My tasks

// ---- 2.823.0 (#4773): the person's own rules (kalmido/tasks/minerules.py; the dialog: minerules.js, module minerules). The
// server decides and moves; the app only says which tasks "My tasks" shows (no hidden projects) when they change, at most every
// MR_GAP ms, while the own order with sections is open and the person has active rules (mine_sections.rules). A drag waiting
// offline goes first. The answer brings the new own order and sections, like a drag of the person.
const MR_GAP = 700;
let mrSig = '', mrT = 0, mrBusy = false;
function mrApplySoon() {
  if (!mseOn() || !(S.mineSecs?.rules > 0) || mrT || mrBusy) return;
  mrT = setTimeout(mrApply, MR_GAP);
}
async function mrApply() {
  mrT = 0;
  if (!mseOn() || !(S.mineSecs?.rules > 0) || OUT.q.some(e => e.url === '/api/tasks/mine-order') || navigator.onLine === false) return;
  const ts = moAll().filter(t => t.id > 0 && !mtHid(t)), t0 = today();
  const sig = t0 + '|' + (S.mineSecs.rules) + '|' + ts.map(t => [t.id, t.due || '', t.priority || 0, t.list_id, (t.ltags || []).join(','), moPos(t) == null ? 'n' : ''].join(':')).join(';');
  if (sig === mrSig) return;
  mrBusy = true;
  try {
    const j = await rawFetch('POST', '/api/mine-rules/apply', {ids: ts.map(t => t.id), today: t0});  // never queued: offline it runs at the next change
    mrSig = sig;
    if (j?.mine_order && !OUT.q.some(e => e.url === '/api/tasks/mine-order')) {
      S.mineOrder = j.mine_order; S.mineBase = moIds(j.mine_order);
      mseFromState(j);
      if (j.moved) { mrSig = ''; render(); }
    }
  } catch { /* offline / an older server: the next change asks again */ } finally { mrBusy = false; }
}
