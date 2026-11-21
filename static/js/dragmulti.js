/* Kalmido web client: Dependencies by dragging (#1330) and several selected tasks moved at once (#1003).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md).
   Loaded after dnd.js: its drag handlers ask dgOver / dgDrop first. */
'use strict';

// ------------------------------------------------------------------ 2.43.0 (#1330): dependencies by dragging
// Desktop: a task dragged with Alt (Option) held onto another task waits on it; the target row shows "Waits on this task"
// instead of the insert line (pressing / releasing the key during the drag switches). With a selection every selected
// task waits on it. While a task is dragged, the dependencies of the open task panel show two drop fields: "Waiting on"
// (the open task waits on the dragged one) and "Blocking" (the dragged one waits on the open task). One drop = one history
// step with Undo; the server refuses loops and names both tasks. Phone: no dragging, "Waiting on a task…" in the
// long-press menu picks the task with the task search.
// ------------------------------------------------------------------ 2.43.0 (#1003): several tasks at once
// A drag that starts on a selected row takes the whole selection (badge "3 tasks" on the drag image). Upper / lower part of
// a row = the block goes before / after it (order kept), the middle = they become its subtasks (at most maxDepth() levels: a
// task whose own subtasks would go deeper stays, the message counts it). A section header, a kanban column or a list in
// the sidebar takes them as standalone tasks. One batch request = one Undo. Without dragging: the multi panel and the
// phone's selection menu have "Subtasks of…" and "Out of the parent task".
const DG = {ids: null, zones: false};
const dgShort = s => { s = String(s || ''); return s.length > 40 ? s.slice(0, 39) + '…' : s; };
const dgRowsOrder = () => new Map(vl_ids().map((id, i) => [id, i]));  // 2.65.0 (#1825): also the rows a long list does not draw
// the ids in the order the user sees them (rows on screen first, then by sort)
function dgOrder(ids) {
  const pos = dgRowsOrder(), big = 1e9;
  return [...ids].filter(i => S.tasks.get(i)).sort((a, b) => (pos.get(a) ?? big) - (pos.get(b) ?? big) || (S.tasks.get(a).sort || 0) - (S.tasks.get(b).sort || 0));
}
function dgAncestors(id) { const out = []; let p = S.tasks.get(id)?.parent_id; for (let n = 0; p && n < 10; n++) { out.push(p); p = S.tasks.get(p)?.parent_id; } return out; }
// a selected task whose parent (any level) is selected too moves with that parent
const dgRoots = ids => { const set = new Set(ids); return ids.filter(i => !dgAncestors(i).some(a => set.has(a))); };
function dgHeight(id, n = 0) { const k = children(id); return !k.length || n > 6 ? 0 : 1 + Math.max(...k.map(x => dgHeight(x.id, n + 1))); }
const dgFits = (pid, id) => depthOf(S.tasks.get(pid)) + 1 + dgHeight(id) < maxDepth();

// ---- dependencies
function dgDepOk(w, b) {
  const wt = S.tasks.get(w), bt = S.tasks.get(b);
  return !!wt && !!bt && w !== b && w > 0 && b > 0 && canEdit(wt) && dFor(wt) && dFor(bt);
}
// pairs [[waiting, blocker], ...]: added one by one (the server checks rights and loops), one history step for all
// 2.559.0 (#4660): shown at once (the waiting task's blockers, the counts of both), the requests behind it; all refused = all
// back, some refused (a loop, no right) = the state again in the background (no GET before the screen shows it)
async function dgDepAdd(pairs) {
  const ok = [], errs = [], todo = [], seen = new Set();
  for (const [w, b] of pairs) { const k = w + ':' + b; if (!seen.has(k) && !(S.tasks.get(w)?.blockers || []).includes(b)) { seen.add(k); todo.push([w, b]); } }
  if (!todo.length) { toast(tr('Already waiting on it')); return; }
  const fns = new Map(), on = (id, f) => { if (!fns.has(id)) fns.set(id, []); fns.get(id).push(f); };
  for (const [w, b] of todo) {
    const bo = S.tasks.get(b)?.status === 0, wo = S.tasks.get(w)?.status === 0;
    on(w, t => { if ((t.blockers || []).includes(b)) return; t.blockers = [...(t.blockers || []), b]; if (bo) t.blocked = (t.blocked || 0) + 1; });
    on(b, t => { if (wo) t.blocking = (t.blocking || 0) + 1; });
  }
  const put = dgLocal(new Map([...fns].map(([id, fs]) => [id, t => fs.forEach(f => f(t))])));
  try {
    await optWrite(put, async () => {
      for (const [w, b] of todo) {
        try { await api('POST', '/api/deps', {task_id: w, blocker_id: b}); ok.push([w, b]); } catch (e) { errs.push(e?.message || ''); }
      }
      if (!ok.length) throw new Error(errs[0] || '');
    });
  } catch { return; }
  if (errs.length) load().then(render, () => {});
  if (S.sel && todo.some(p => p.includes(S.sel))) loadDeps(S.sel);
  const [w0, b0] = ok[0], tw = S.tasks.get(w0), tb = S.tasks.get(b0);
  const lab = ok.length === 1 ? tr('“{0}” waits on “{1}”', dgShort(tw?.title), dgShort(tb?.title)) : trn('{0} task waits on “{1}”', '{0} tasks wait on “{1}”', ok.length, dgShort(tb?.title));
  const go = add => async () => {
    const skipped = [];
    for (const [w, b] of ok) {
      try { await api(add ? 'POST' : 'DELETE', add ? '/api/deps' : `/api/deps/${rid(w)}/${rid(b)}`, add ? {task_id: rid(w), blocker_id: rid(b)} : undefined); } catch { skipped.push(histTitle(w)); }
    }
    return {skipped, none: skipped.length === ok.length};
  };
  const ids = [...new Set(ok.flat())];
  const e = histAdd({label: lab, snaps: ids.map(i => snapTask(S.tasks.get(i))).filter(Boolean), ids, undo: go(false), redo: go(true),
    post: () => { if (S.sel && ids.includes(S.sel)) loadDeps(S.sel); }});
  offerUndo(errs.length ? lab + ' · ' + trn('{0} not possible', '{0} not possible', errs.length) + (errs[0] ? ': ' + errs[0] : '') : lab, e);
}
// the phone's way (and the menu's): "Waiting on a task…" with the task search
function dgDepPick(id) {
  const t = S.tasks.get(id); if (!t) return;
  dgPick({title: tr('Waiting on a task…'), hint: tr('“{0}” can only really start once the selected task is done.', t.title),
    filter: x => x.id !== id && dFor(x) && !(t.blockers || []).includes(x.id) && !tlReaches(x.id, id), near: t,
    pick: x => dgDepAdd([[id, x.id]])});
}
// a task search in a dialog (the look of every task picker, .tpk): this list first, then the others under their name
function dgPick(o) {
  const md = modal(`<h3>${esc(o.title)}</h3>${o.hint ? `<div class="shint keep">${esc(o.hint)}</div>` : ''}
    <input id="dg-q" placeholder="${esc(tr('Search open tasks'))}" aria-label="${esc(tr('Search open tasks'))}" autocomplete="off" style="width:100%;margin-top:.5rem">
    <div class="dplist tpk" id="dg-list" role="listbox" aria-label="${esc(tr('Open tasks'))}"></div>
    <div class="foot"><span class="spacer"></span><button class="btn" data-m="close">${tr('Close')}</button></div>`);  // 2.913.0 (#5587): a pure choice closes, nothing to cancel
  md.classList.add('dpmodal', 'dgpick');
  const self = o.near;
  const draw = () => {
    const q = norm($('#dg-q', md).value || '');
    const arr = openTasks().filter(x => x.id > 0 && o.filter(x) && (!q || norm(x.title).includes(q)))
      .sort((a, b) => (b.list_id === self?.list_id) - (a.list_id === self?.list_id) || (a.due || '9999').localeCompare(b.due || '9999') || bySort(a, b)).slice(0, 60);
    const row = x => `<button type="button" class="tpkrow" role="option" data-pick="${x.id}"><span class="tpkt">${esc(x.title)}</span><span class="tpkm">${esc(lname(listById(x.list_id)))}${x.due ? ' · ' + esc(dayLabel(x.due)) : ''}</span></button>`;
    const same = arr.filter(x => x.list_id === self?.list_id), others = arr.filter(x => x.list_id !== self?.list_id);
    $('#dg-list', md).innerHTML = !arr.length ? `<div class="muted mhint">${tr('No matching open task.')}</div>`
      : (same.length ? `<div class="tpkg" role="group" aria-label="${esc(tr('This project'))}"><div class="tpkh">${esc(tr('This project'))}</div>${same.map(row).join('')}</div>` : '')
        + [...new Set(others.map(x => x.list_id))].map(lid => `<div class="tpkg" role="group" aria-label="${esc(lname(listById(lid)))}"><div class="tpkh">${esc(lname(listById(lid)))}</div>${others.filter(x => x.list_id === lid).map(row).join('')}</div>`).join('');
  };
  draw();
  md.addEventListener('input', e => { if (e.target.id === 'dg-q') draw(); });
  md.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.m === 'close') { md.remove(); return; }
    if (b.dataset.pick) { const x = S.tasks.get(+b.dataset.pick); md.remove(); if (x) o.pick(x); }
  });
  setTimeout(() => focusIfKeyboard($('#dg-q', md)), 50);  // 2.655.0 (#5081): was !isMobile()
}

// 2.559.0 (#4659): a change of tasks shown at once, as optWrite's put (core.js): ch = Map id -> fn(t) that changes the task
// here, or null = it leaves (the trash). Each run (again on top of a state fetched meanwhile) changes the task found then;
// the values from before are kept once. The return of put() puts all of them back (an error), put.back(ids) only some
// (the ones the server kept: skipped, conflicts).
const dgCp = v => v && typeof v === 'object' ? JSON.parse(JSON.stringify(v)) : v;
function dgLocal(ch) {
  let old = null, ext = [];  // ext: the rows of S.extra (completed ones fetched for a view) that left, with their place
  const back = only => {
    for (const [id, o] of old || []) {
      if (only && !only.includes(id)) continue;
      const t = S.tasks.get(id);
      if (!o.keys) { if (!t && o.in) S.tasks.set(id, snapTask(o.t)); continue; }
      if (t) for (const k of o.keys) { if (k in o.t) t[k] = dgCp(o.t[k]); else delete t[k]; }
    }
    for (const [i, x] of ext) if ((!only || only.includes(x.id)) && S.extra && !S.extra.some(y => y.id === x.id)) S.extra.splice(Math.min(i, S.extra.length), 0, x);
    _kidsIx = null;
  };
  const put = () => {
    const first = !old; if (first) old = new Map();
    for (const [id, fn] of ch) {
      const inT = S.tasks.has(id), t = S.tasks.get(id) || (!fn && (S.extra || []).find(x => x.id === id)); if (!t) continue;
      const s = first ? snapTask(t) : null;
      if (fn) fn(t); else S.tasks.delete(id);
      if (first) old.set(id, {t: s, in: inT, keys: fn ? Object.keys({...s, ...t}).filter(k => JSON.stringify(s[k]) !== JSON.stringify(t[k])) : null});
    }
    if (S.extra && [...ch.values()].includes(null)) {
      if (first) S.extra.forEach((x, i) => { if (ch.has(x.id) && ch.get(x.id) === null) ext.push([i, x]); });
      S.extra = S.extra.filter(x => !(ch.has(x.id) && ch.get(x.id) === null));
    }
    _kidsIx = null;
    return () => back();
  };
  put.back = back;
  return put;
}
// one item of a patch_each batch on the local task (as applyLocal does it offline)
function dgItem(t, d) {
  const {_prev, fields, ...b} = d || {}; Object.assign(t, b);
  if (fields) { t.fields = {...(t.fields || {})}; for (const [k, v] of Object.entries(fields)) { if (v == null || v === '') delete t.fields[k]; else t.fields[k] = String(v); } }
}
// patch_each items at once; a task that moves to another list takes its subtasks along (the server does the same)
// #3506 (CI red of 2.560.0 - 2.563.1, p2134_ui): a task made a subtask goes into its parent's list and section, as the server's
// indent (tasks/lifecycle.py) does it; before, it kept its own list here until the next load (the move picker then left out
// the list it had come from)
function dgItemsPut(items) {
  const ch = new Map();
  for (const [id, d0] of Object.entries(items)) {
    const p = d0.parent_id ? S.tasks.get(d0.parent_id) : null, d = p ? {...d0, list_id: p.list_id, section_id: p.section_id ?? null} : d0;
    ch.set(+id, t => dgItem(t, d));
    if (d.list_id != null) for (const k of withKids(+id).slice(1)) if (!(k.id in items)) ch.set(k.id, t => { t.list_id = d.list_id; });
  }
  return dgLocal(ch);
}
// tasks to the trash at once, with their subtasks (any level, as the server's do_delete); back(ids) brings a kept one back
// with its subtasks
function dgGone(ids) {
  const fam = new Map();
  for (const id of ids) for (const k of withKids(id)) if (!fam.has(k.id)) fam.set(k.id, id);
  const put = dgLocal(new Map([...fam.keys()].map(i => [i, null]))), b0 = put.back;
  put.back = only => b0([...fam].filter(([i, r]) => only.includes(r) || only.includes(i)).map(([i]) => i));
  return put;
}
// the server's answer to such a batch: the tasks it kept (locked, changed elsewhere) back here; with errors (which ones is
// not told) the state again in the background, so the screen shows what the server has
function dgAfter(put, j) {
  const kept = [...(j?.skipped || []), ...(j?.conflicts || []).map(c => c.id)];
  if (kept.length) { put.back(kept); render(); }
  if (j?.errors?.length || kept.length) load().then(render, () => {});
}
// ---- several tasks: one patch_each batch = one history step
// 2.559.0 (#4659): shown at once (dgItemsPut), the request behind it; an error puts the tasks back (no reload)
// 2.1271.0 (#6436): a subtask an item makes standalone (parent_id: null) takes its parent's date / priority into its empty fields
// (dnd.js detachPatch), in the same item; one toast for all of them with "Don't adopt"
// (#7344): o.quiet = no toast (the caller's gesture says it once, with what it did besides); -> {j, dt} (dt: dtToast's got)
// (#7351): every item carries what this device saw before (_prev, as the single drag's reorder did, #3028): a field changed
// elsewhere meanwhile stays and is named; a task the server completed as a recurring one in a done column (#3354,
// section_moved) and a done task dropped into a done column (#3911, dnd_kindStayed) get no Undo of the move
async function dgApply(items, lab, notes = [], o = {}) {
  const ids = Object.keys(items).map(Number);
  if (!ids.length) { if (!o.quiet) toast(notes.filter(Boolean).join(' · ') || tr('Nothing to move')); return null; }
  for (const id of ids) { const t = S.tasks.get(id), it = items[id]; if (t && it && !it._prev) { const {fields, ...rest} = it, p = dndPrev(t, rest); if (Object.keys(p).length) it._prev = p; } }
  const dt = dtMerge(items);
  const snaps = ids.flatMap(withKids), put = dgItemsPut(items);
  let j;
  try { j = await optWrite(put, () => api('POST', '/api/tasks/batch', {ids, action: 'patch_each', data: {items}})); } catch { return null; }
  dgAfter(put, j);
  const skm = Object.keys(j?.section_moved || {}).map(Number);
  const pairs = snaps.filter(b => ids.includes(b.id) && !skm.includes(b.id)).map(b => [b, snapTask(S.tasks.get(b.id))]).filter(([b, a]) => !dnd_kindStayed(b, a));
  const skx = sid => ['done', 'rejected'].includes(wip_sec(sid)?.kind);  // into / out of a column with that meaning: the server set the status
  if (skm.length || snaps.some(b => items[b.id] && 'section_id' in items[b.id] && (skx(items[b.id].section_id) || skx(b.section_id)))) load().then(render, () => {});
  for (const id of skm) sk_moved(j, id);
  const e = histFields(lab, pairs, {res: j, fields: [...UNDO_FIELDS, 'sort']});
  if (o.quiet) return {j, dt: dtDone(dt, j)};
  if (skm.length && !e) return j;  // sk_moved said it, with its own Undo
  const fail = ids.length - (j?.count ?? ids.length);
  const msg = [lab, fail ? trn('{0} task not changed', '{0} tasks not changed', fail) + (j?.errors?.[0] ? ': ' + j.errors[0] : '') : '', ...notes].filter(Boolean).join(' · ');
  if (dtToast(msg, dtDone(dt, j))) return j;  // 2.1271.0 (#6436): the Undo of the step stays in the history
  if (e) offerUndo(msg, e); else toast(msg);
  return j;
}
// the selected tasks become subtasks of pid, after its own subtasks, in their order
async function dgMakeSubs(ids, pid) {
  const p = S.tasks.get(pid); if (!p) return;
  if (!canEdit(p)) { roToast(); return; }
  if (isMs(p)) { toast(tr('A milestone cannot have subtasks')); return; }
  const set = new Set(ids);
  if (set.has(pid) || dgAncestors(pid).some(a => set.has(a))) { toast(tr('A task cannot be nested under itself')); return; }
  let list = dgRoots(dgOrder(ids));
  const ro = list.filter(i => !canEdit(S.tasks.get(i))), ms = list.filter(i => isMs(S.tasks.get(i)) && !ro.includes(i));
  list = list.filter(i => !ro.includes(i) && !ms.includes(i));
  const deep = list.filter(i => !dgFits(pid, i));
  list = list.filter(i => !deep.includes(i));
  const kids = children(pid).filter(k => !set.has(k.id));
  const s0 = kids.length ? Math.max(...kids.map(k => k.sort || 0)) + 1 : 0;
  const items = {};
  list.forEach((i, k) => { items[i] = {parent_id: pid, sort: s0 + k}; });
  const notes = [deep.length ? trn('{0} task stays: its own subtasks would go deeper than {1} levels', '{0} tasks stay: their own subtasks would go deeper than {1} levels', deep.length, maxDepth()) : '',
    ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '',
    ms.length ? tr('A milestone cannot be a subtask') : ''];
  return dgApply(items, trn('{0} task is now a subtask of “{1}”', '{0} tasks are now subtasks of “{1}”', list.length, dgShort(p.title)), notes);
}
// out of the parent task: standalone right after the main task they were under (same section), order kept
async function dgDetach(ids) {
  const list = dgOrder(ids).filter(i => S.tasks.get(i)?.parent_id), ro = list.filter(i => !canEdit(S.tasks.get(i)));
  const may = list.filter(i => !ro.includes(i));
  if (!list.length) { toast(tr('None of them is a subtask')); return; }
  const top = i => { const a = dgAncestors(i); return S.tasks.get(a[a.length - 1]); };
  const items = {}, byTop = new Map();
  for (const i of may) { const tp = top(i); if (!tp) continue; if (!byTop.has(tp.id)) byTop.set(tp.id, []); byTop.get(tp.id).push(i); }
  for (const [tid, arr] of byTop) {
    const tp = S.tasks.get(tid);
    const nexts = [...S.tasks.values()].filter(x => x.list_id === tp.list_id && !x.parent_id && x.id !== tid && (x.section_id || null) === (tp.section_id || null) && (x.sort || 0) > (tp.sort || 0) && !may.includes(x.id));
    const hi = nexts.length ? Math.min(...nexts.map(x => x.sort || 0)) : (tp.sort || 0) + arr.length + 1;
    arr.forEach((i, k) => { items[i] = {parent_id: null, section_id: tp.section_id || null, sort: (tp.sort || 0) + (hi - (tp.sort || 0)) * (k + 1) / (arr.length + 1)}; });
  }
  return dgApply(items, trn('{0} subtask is now standalone', '{0} subtasks are now standalone', Object.keys(items).length),
    [ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '']);
}
// "Subtasks of…": the task search, without the selection and what is under it, only where another level fits
function dgSubPick(ids) {
  const set = new Set(ids), roots = dgRoots(ids);
  dgPick({title: tr('Subtasks of…'), hint: trn('The {0} selected task becomes a subtask of the selected task.', 'The {0} selected tasks become subtasks of the selected task.', roots.length),
    near: S.tasks.get(roots[0]),
    filter: x => !set.has(x.id) && !dgAncestors(x.id).some(a => set.has(a)) && canEdit(x) && !isMs(x) && depthOf(x) < maxDepth() - 1,
    pick: x => dgMakeSubs(ids, x.id)});
}
// a block before / after a row: the same parent, list and section as the row, sorted between it and its neighbour
// (#7344): plain = only the place (My tasks: beside a subtask under its parent; no priority block, no sort switch)
// (#7351): one task and a selection alike (the project list's single drag went here): a section still on its way waits for its
// id (#4659), a locked task keeps its project / priority (#1118: named with "Unlock"), a task under a parent of another project
// carries that project (the browser re-encrypts its texts on the way when one of them has the lock, #1817 le2e_move), on
// Tomorrow a task dropped onto one of tomorrow's takes that day (#6960; as its own write, so dependent tasks move along, #1865)
async function dgBlock(ids, row, after, plain = false) {
  const target = S.tasks.get(+row.dataset.id); if (!target) return;
  const set = new Set(ids), kcol = row.closest('.kcol');
  if (set.has(target.id) || dgAncestors(target.id).some(a => set.has(a))) return;
  let list = dgRoots(dgOrder(ids));
  const ro = list.filter(i => !canEdit(S.tasks.get(i)));
  list = list.filter(i => !ro.includes(i));
  if (!list.length && ro.length) { roToast(); return; }
  const deep = target.parent_id ? list.filter(i => !dgFits(target.parent_id, i)) : [];
  list = list.filter(i => !deep.includes(i));
  if (target.list_id && list.some(i => S.tasks.get(i).list_id !== target.list_id) && !canEditList(target.list_id)) { roToast(); return; }
  const mode = plain ? 'custom' : sortMode();
  const g = !kcol && row.closest('.group')?.querySelector('.ghead[data-section]');
  let sec = target.parent_id ? undefined : kcol ? (kcol.dataset.kcol ? +kcol.dataset.kcol : null) : g ? (g.dataset.section ? +g.dataset.section : null) : target.section_id ?? null;
  if (sec < 0) { sec = await secReal(sec); if (!sec) return; }  // (#4659): a section still on its way
  const prio = mode === 'prio' && !kcol;
  const lk = list.filter(i => { const t = S.tasks.get(i); return tlkHits(t, {...(!target.parent_id ? {list_id: target.list_id} : {}), ...(prio ? {priority: target.priority} : {})}); });
  if (lk.length && lk.length === list.length && list.length === 1) { tlkToast(S.tasks.get(lk[0])); render(); return; }
  list = list.filter(i => !lk.includes(i));
  let rows = vl_ids().map(i => S.tasks.get(i)).filter(x => x && x.parent_id === target.parent_id && !set.has(x.id) && (x.status === 0 || x.id === target.id));
  if (prio) rows = rows.filter(x => x.priority === target.priority);
  const i = rows.findIndex(x => x.id === target.id), n = list.length;
  let lo, hi;
  if (after) { const nx = rows[i + 1]; lo = target.sort; hi = nx && nx.list_id === target.list_id ? nx.sort : target.sort + n + 1; }
  else { const pv = rows[i - 1]; hi = target.sort; lo = pv && pv.list_id === target.list_id ? pv.sort : target.sort - n - 1; }
  const tmr = S.route.key === 'tomorrow' && target.due && target.due === addDays(today(), 1) ? target.due : null;  // (#6960)
  const items = {}, days = [];
  list.forEach((id, k) => {
    const t = S.tasks.get(id), it = {sort: lo + (hi - lo) * (k + 1) / (n + 1)};
    if ((t.parent_id || null) !== (target.parent_id || null)) it.parent_id = target.parent_id || null;
    if (t.list_id !== target.list_id) it.list_id = target.list_id;
    if (sec !== undefined && (t.section_id || null) !== sec) it.section_id = sec;
    if (prio && t.priority !== target.priority) it.priority = target.priority;
    if (tmr && t.due !== tmr && !tlkIs(t)) days.push(id);
    items[id] = it;
  });
  if (((mode === 'date' || mode === 'title' || mode === 'creator' || mode.startsWith('created') || sortByCol(mode)) && !kcol) || mode === 'flow') LS.set('sort2.' + S.route.key, 'prio');  // a manual drop: prio + manual (as one task)
  const one = n === 1 && S.tasks.get(list[0]), tl = listById(target.list_id);
  const away = n && list.every(i => items[i].list_id), insec = n && sec !== undefined && list.every(i => 'section_id' in items[i]);
  const under = n && target.parent_id && list.every(i => items[i].parent_id);
  let lab = away ? (one ? tr('Moved to {0}', lname(tl)) : trn('Moved {0} task to {1}', 'Moved {0} tasks to {1}', n, lname(tl)))
    : under ? trn('{0} task is now a subtask of “{1}”', '{0} tasks are now subtasks of “{1}”', n, dgShort(S.tasks.get(target.parent_id)?.title))
    : insec ? wip_msg(one ? tr('Moved to section {0}', secName(sec)) : trn('{0} task moved to section {1}', '{0} tasks moved to section {1}', n, secName(sec)), sec)
    : trn('{0} task moved', '{0} tasks moved', n);
  if (one && away) lab = wsc_moveMsg(one.list_id, target.list_id, lab);  // (#1474): Private -> organisation: who sees it now
  const notes = [list.some(i => 'priority' in items[i]) ? tr('Priority: {0}', tr([N_('None'), N_('Low'), '', N_('Medium'), '', N_('High'), '', N_('Urgent')][target.priority] || N_('None'))) : '',
    deep.length ? trn('{0} task stays: its own subtasks would go deeper than {1} levels', '{0} tasks stay: their own subtasks would go deeper than {1} levels', deep.length, maxDepth()) : '',
    ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '',
    lk.length ? trn('{0} task is locked', '{0} tasks are locked', lk.length) : ''];
  if (!days.length) return dgApply(items, lab, notes);
  return histGroup(async () => {  // the day first, as the task's own write: its dependent tasks move along (#1865) in the same step
    for (const id of days) { try { await patchTask(id, {due: tmr}); } catch { /* api() said why */ } }
    return dgApply(items, lab, notes);
  });
}
// into a section / kanban column of a list as standalone tasks, at its top, order kept
// (#7351): also the single task's way (dropped on a section's head or a column, "Move to section…"): only a move into another
// project needs the right on that project, the section alone the right on the task
async function dgToSection(ids, lid, sid, lab0) {  // lab0: the gesture's own words (New section …)
  if (sid < 0) { sid = await secReal(sid); if (!sid) return; }  // 2.559.0 (#4659): a section still on its way (dnd.js)
  if (sid && !S.sections.some(x => x.id === sid && x.list_id === lid)) return;
  let list = dgRoots(dgOrder(ids));
  const ro = list.filter(i => !canEdit(S.tasks.get(i)));
  list = list.filter(i => !ro.includes(i));
  if (!list.length && ro.length) { roToast(); return; }
  if (list.some(i => S.tasks.get(i).list_id !== lid) && !canEditList(lid)) { roToast(); return; }
  const lk = list.filter(i => S.tasks.get(i).list_id !== lid && tlkIs(S.tasks.get(i)));  // (#1118): a locked task keeps its project
  if (lk.length && list.length === 1) { tlkToast(S.tasks.get(lk[0])); render(); return; }
  list = list.filter(i => !lk.includes(i));
  const inSec = [...S.tasks.values()].filter(x => x.list_id === lid && !x.parent_id && x.status === 0 && !list.includes(x.id) && (sid ? x.section_id === sid : !S.sections.some(z => z.id === x.section_id)));
  const top = inSec.length ? Math.min(...inSec.map(x => x.sort || 0)) : 0;
  const items = {};
  list.forEach((id, k) => { const t = S.tasks.get(id); items[id] = {section_id: sid, sort: top - list.length + k, ...(t.parent_id ? {parent_id: null} : {}), ...(t.list_id !== lid ? {list_id: lid} : {})}; });
  if (['date', 'title', 'creator', 'flow', 'created', 'created_asc'].includes(sortMode()) || sortByCol(sortMode())) LS.set('sort2.' + S.route.key, 'prio');
  const n = list.length, subs = list.filter(i => S.tasks.get(i).parent_id).length, one = n === 1;
  const lab = lab0 || wip_msg(one ? (subs ? tr('Subtask is now standalone') + ' · ' : '') + tr('Moved to section {0}', secName(sid)) : trn('{0} task moved to section {1}', '{0} tasks moved to section {1}', n, secName(sid)), sid);
  return dgApply(items, lab,
    [subs && (!one || lab0) ? trn('{0} subtask is now standalone', '{0} subtasks are now standalone', subs) : '',
      ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '', lk.length ? trn('{0} task is locked', '{0} tasks are locked', lk.length) : '']);
}
async function dgToNewSection(ids, lid) {
  lid = lid ?? S.tasks.get(ids[0])?.list_id; if (!lid) return;
  if (!canEditList(lid)) { roToast(); return; }
  const name = (await askPrompt(tr('New section'), tr('New section'), {ok: tr('Create'), input: {max: 100}}))?.trim();
  if (!name) return;
  return histGroup(async () => {  // one step: Undo puts the tasks back and removes the section
    const had = new Set(S.sections.map(s => s.id));
    await sectionCreate(lid, name);
    const s = S.sections.find(x => x.list_id === lid && !had.has(x.id));
    if (s) await dgToSection(ids, lid, s.id, tr('New section {0}', qn(name)));
  }, tr('New section {0}', qn(name)));
}
// a list in the sidebar: standalone tasks there (subtasks leave their parent)
async function dgToList(ids, lid) {
  if (!canEditList(lid)) { roToast(); return; }
  let list = dgRoots(dgOrder(ids));
  const ro = list.filter(i => !canEdit(S.tasks.get(i)));
  list = list.filter(i => !ro.includes(i));
  const items = {};
  for (const id of list) { const t = S.tasks.get(id); if (t.list_id !== lid || t.parent_id) items[id] = {list_id: lid, ...(t.list_id !== lid ? {section_id: null} : {}), ...(t.parent_id ? {parent_id: null} : {})}; }
  return dgApply(items, trn('Moved {0} task to {1}', 'Moved {0} tasks to {1}', Object.keys(items).length, lname(listById(lid)) || '?'),
    [ro.length ? trn('{0} task skipped (read-only)', '{0} tasks skipped (read-only)', ro.length) : '']);
}

// ---- (#7344): the drop core, step 1 (audit #5731). One resolver reads where a drop lands - mouse or finger, one task or
// a selection (one task = a selection of one): a row (before / after it), the head of a group, a "New ..." button. What a
// place means belongs to the adapter of the container that is shown (DROP_ADAPTERS; step 1: "My tasks" = own order / own
// sections, mineorder.js). An adapter answers where(tgt) -> null (not mine: the old ways of dnd.js / dgDrop go on), {no: text}
// (it takes nothing there: the text instead of a silent nothing, no highlight) or a place, and put(ids, place) does the whole
// gesture as one step of the history. The middle of a row (= make subtasks, dgMakeSubs) stays the same everywhere and comes
// before the core. Step 3 (#7351): the project list and every other task list (plWhere / plPut below).
const DROP_ADAPTERS = [];
// (#7354): + kind 'col' = a column of a board (data-dropcol; the cards are rows: before / after a card = its column)
const dropRowTgt = (row, after) => ({kind: 'row', row, tid: +row.dataset.id, after, gkey: row.closest('.group')?.querySelector(':scope > .ghead')?.dataset.key || ''});
function dropAt(el, y, after) {
  if (!el?.closest || el.closest('#detail')) return null;
  const row = el.closest('#view .trow');
  if (row) return dropRowTgt(row, after ?? dropAfter(row, y));
  const nw = el.closest('#view [data-dropnew], #view .sdrop[data-newsec]');  // (#7351): + a project's "New section"
  if (nw) return {kind: 'new', el: nw};
  const head = el.closest('#view .ghead[data-key]');
  if (head) return {kind: 'head', el: head, key: head.dataset.key};
  const col = el.closest('#view [data-dropcol], #view .kcol[data-kcol]');  // (#7351): + a column of a project's board
  return col ? {kind: 'col', el: col, key: col.dataset.dropcol ?? 'k:' + col.dataset.kcol} : null;
}
// -> {a: adapter, tgt, w: its place} or null (no adapter takes this target)
function dropForTgt(tgt, ids) {
  if (!tgt) return null;
  for (const a of DROP_ADAPTERS) { if (!a.on()) continue; const w = a.where(tgt, ids); if (w) return {a, tgt, w}; }
  return null;
}
// after = the selection's zone (dgZone)
const dropFor = (el, y, ids, after) => dropForTgt(dropAt(el, y, after), ids);
// the drop itself: false = not the core's; true = it takes nothing there (said); else the promise of the put (a caller inside
// a histGroup awaits it, so the gesture stays one step)
function dropDo(d, ids) {
  if (!d) return false;
  if (d.w.no) { if (d.w.no !== true) toast(d.w.no); return true; }
  return Promise.resolve(d.a.put(ids, d.w)).then(() => true);
}
const dropRun = (ids, el, y, after) => dropDo(dropFor(el, y, ids, after), ids);
// (#7354): a place without a pointer - the keyboard (Alt+arrow) and the menu's Move up / down: the same adapters, the target
// built from a row (before / after it); false = no adapter takes it (the caller's own way)
const dropTo = (ids, tgt) => dropDo(dropForTgt(tgt, ids), ids);
// dragover: a target the core refuses gets no highlight (the drop still comes, to say why)
const dropNo = (el, y, ids) => !!dropFor(el, y, ids)?.w.no;

// ---- (#7351, step 3 of the drop core): the adapter of a project's list and board - and of every other task list that is not
// My tasks (Today, Tomorrow, All, a filter): before / after a row (dgBlock), a section's head or a column of the board
// (dgToSection), "New section" (dgToNewSection), for one task and a selection alike, one step of the history each. Gone: the
// row / section / column part of dnd.js dropTask0, taskToSection0 and taskToNewSection, and dgDrop's own branches for them.
// A task shown in a further project of its own (#1459, multilist.js): one dragged there moves only its link (ml_drop).
// The middle of a row (subtasks) comes before the core; a swimlane's value (swlDrop) before it in the same step (dnd.js dropTask).
const plLink = (ids, v = ml_viewList()) => { const t = ids.length === 1 && S.tasks.get(ids[0]); return !!t && !!v && t.list_id !== v && ml_in(t, v); };
function plWhere(tgt, ids) {
  const el = tgt.kind === 'row' ? tgt.row : tgt.el;
  if (tgt.kind === 'head' && el.dataset.section === undefined) return null;  // a day's / a priority's head: not a place
  if (tgt.kind === 'new' && !el.matches('[data-newsec]')) return null;
  if (tgt.kind === 'col' && !el.matches('.kcol[data-kcol]')) return null;
  if (tgt.kind === 'row' && ids.includes(tgt.tid)) return {no: true};  // onto itself / its own selection
  if (plLink(ids)) return {link: true, tgt};
  return tgt.kind === 'row' ? {row: tgt.row, after: tgt.after} : tgt.kind === 'new' ? {fresh: true}
    : {sid: (tgt.kind === 'col' ? el.dataset.kcol : el.dataset.section) ? +(tgt.kind === 'col' ? el.dataset.kcol : el.dataset.section) : null};
}
function plPut(ids, w) {
  if (w.link) {
    const t = S.tasks.get(ids[0]), x = w.tgt, row = x.kind === 'row' ? x.row : null;
    return ml_drop(t, {row, after: x.after, kcol: x.kind === 'col' ? x.el : row?.closest('.kcol'), sec: x.kind === 'head' ? x.el : null});
  }
  const lid = routeList()?.id ?? S.tasks.get(ids[0])?.list_id;
  if (w.fresh) return dgToNewSection(ids, lid);
  if (w.row) return dgBlock(ids, w.row, w.after);
  return dgToSection(ids, w.sid ? S.sections.find(s => s.id === w.sid)?.list_id ?? lid : lid, w.sid);
}
// ---- (#7519): the section side of the adapters - one head for every group that is a section (a project's section, an own
// section of My tasks). What a section can comes from its adapter (sec), render.js draws the head from it and sh_menu is its
// one menu (the same order and texts everywhere); renaming, moving and deleting go through the adapter's saving:
//   of(g) -> the section of a group (null = not one of this adapter; a project's group without section = {id: null})
//   byId(id), label(s), drag(s) (the head drags: grip, no Move up / down on a touch screen), add(s, v, ro) (its "+"),
//   newAt(s, r) -> the new task's fields of its "+" (r = parseQuick of the text; default: the project's list + section),
//   placed(s, t) -> what follows the creation in the same step (My tasks: into the own section) (#7512)
//   menu(s, ro) (its "…"), grip(s) / chip(g) (html), pos(s) -> [i, n], rename(s, name), move(s, d), del(s), extra(s, anchor)
//   ids(s) -> the order of the sections s moves among, order(s, ids) saves a new one (#7518: the grip's drag, dnd.js / secdrag.js)
//   head(h) / fold(s): an adapter that keeps the folding itself (My tasks: on the server for every device)
const sh_ad = name => DROP_ADAPTERS.find(a => a.name === (name || 'list') && a.sec);
function sh_of(g) { for (const a of DROP_ADAPTERS) { const s = a.sec?.of(g); if (s) return {a, s}; } return null; }
// the head's parts: {grip, chip, add, menu} (html, add a boolean)
function sh_head(g, v, ro) {
  const x = sh_of(g); if (!x) return {grip: '', chip: '', add: false, ak: '', aid: 0, menu: ''};
  const {a, s} = x, c = a.sec;
  // (#7512): add = the "+" of this head; ak / aid = the adapter and section the new task goes to (secAddOpen, listedit.js)
  return {grip: s.id && !ro && c.drag(s) ? c.grip(s) : '', chip: c.chip ? c.chip(g) : '', add: !!c.add(s, v, ro), ak: a.name, aid: s.id || 0,
    menu: s.id && c.menu(s, ro) ? `<button data-rowmenu="ghead" class="iconbtn gact" data-act="section-menu" data-sk="${esc(a.name)}" data-id="${esc(s.id)}" title="${esc(tr('More') + ': ' + g.name)}" aria-label="${esc(tr('More') + ': ' + g.name)}">${ic('dots', 's')}</button>` : ''};
}
// the one menu of a section's head (the "…", a long press, the hold of a head); head = items on top (the head's "+")
// a board's column (.khead) moves left / right, a list's head up / down
function sh_menu(anchor, name, id, head = []) {
  const a = sh_ad(name), s = a?.sec.byId(id); if (!s) return;
  // (#7518): Move up / down always, also where the head drags (WCAG 2.5.7: the way without dragging; was: hidden on a touch screen)
  const c = a.sec, [i, n] = c.pos(s), x = !!anchor?.closest?.('.khead, .kcol'), mv = true;
  menu(anchor, [...head,
    {label: tr('Rename'), icon: 'edit', fn: () => sh_rename(a, s)},
    ...(mv && i > 0 ? [{label: x ? tr('Move left') : tr('Move up'), icon: x ? 'left' : 'up', fn: () => c.move(s, -1)}] : []),
    ...(mv && i >= 0 && i < n - 1 ? [{label: x ? tr('Move right') : tr('Move down'), icon: x ? 'right' : 'down', fn: () => c.move(s, 1)}] : []),
    ...c.extra(s, anchor),
    '-',
    {label: tr('Delete section (tasks stay)'), icon: 'trash', cls: 'flag-5', fn: () => c.del(s)},
  ]);
}
// folding a section's head: the group folds as every group (events.js collapse); an adapter that keeps it (fold) saves it
document.addEventListener('click', e => {
  const h = e.target.closest?.('#view .ghead[data-key]');
  if (!h || e.target.closest('.gact, .shandle')) return;
  for (const a of DROP_ADAPTERS) { const s = a.sec?.fold && a.sec.head(h); if (s) { a.sec.fold(s); return; } }
}, true);
async function sh_rename(a, s) {
  const old = a.sec.label(s), n = (await askPrompt(tr('Rename section'), old, {ok: tr('Rename'), input: {max: 200}}))?.trim();
  if (n && n !== old) await a.sec.rename(s, n);
}
// a project's sections (S.sections; the sections API, dnd.js sectionRename / moveSection / sectionDelete)
const plSec = {
  of: g => g.section === undefined ? null : g.section ? S.sections.find(x => x.id === g.section) || {id: g.section, name: g.name} : {id: null, name: g.name},
  byId: id => S.sections.find(x => x.id === id), label: s => s.name,
  drag: () => true, add: (s, v, ro) => !ro && !!v?.list && canAddTo(v.list), menu: (s, ro) => !ro,
  grip: s => secHandle(s.id), chip: g => g.section ? wip_ghead(g) : '',
  pos: s => { const ids = secIds(s.list_id); return [ids.indexOf(s.id), ids.length]; },
  ids: s => secIds(s.list_id), order: (s, ids) => saveSectionOrder(s.list_id, ids),
  rename: (s, n) => sectionRename(s.id, n), move: (s, d) => moveSection(s.id, d), del: s => sectionDelete(s.id),
  extra: (s, anchor) => [wip_menuItem(s.id) /* (#1510) */, dw_menuItem(s.id) /* (#3515) */, sk_menuItem(s.id, anchor) /* (#3354) */],
};
DROP_ADAPTERS.push({name: 'list', on: () => !(typeof moActive === 'function' && moActive()), where: plWhere, put: plPut, sec: plSec});

// ---- dragging (desktop); dnd.js asks dgOver on every dragover and dgDrop on the drop
const dgZone = (row, y) => { const r = row.getBoundingClientRect(), f = r.height > 0 ? (y - r.top) / r.height : .5; return f < .28 ? 'before' : f > .72 ? 'after' : 'onto'; };
function dgClear() { $$('.dgdep,.dgonto,.dgno').forEach(x => { x.classList.remove('dgdep', 'dgonto', 'dgno'); delete x.dataset.dg; }); $$('.dgzone.drop').forEach(x => x.classList.remove('drop')); }
function dgMark(el, cls, text) { el.classList.add(cls); el.dataset.dg = text; }
// true = handled here (the caller then allows the drop)
// 2.87.9 (#1965): moving a selection over the same third of the same row changes nothing (no search, no restyle)
let dgLast = null;
function dgOver(e, id) {
  const lr = dgLast && !e.altKey && (DG.ids || dgLast.one) && !e.target.closest?.('.dgzone') && e.target.closest?.('#view .trow');
  if (lr && lr === dgLast.row && lr.isConnected && dgZone(lr, e.clientY) === dgLast.zn && lr.classList.contains(dgLast.cls)) return true;
  dgLast = null;
  dgClear();
  const z = e.target.closest?.('.dgzone');
  if (z) { $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop')); if (z.classList.contains('dgoff')) return false; z.classList.add('drop'); e.dataTransfer.dropEffect = 'link'; return true; }
  const row = e.target.closest?.('#view .trow');
  if (!row || row.closest('#detail')) return false;
  const tid = +row.dataset.id, ids = DG.ids || [id];
  const own = ids.includes(tid);  // (#7344): onto a row of the selection = the selection at its place, where the core takes it
  if (own && (!DG.ids || e.altKey || !dropFor(row, e.clientY, ids) || dropNo(row, e.clientY, ids))) return false;
  if (e.altKey) {
    $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
    const bad = ids.find(w => !dgDepOk(w, tid));
    if (bad !== undefined) dgMark(row, 'dgno', !dFor(S.tasks.get(tid)) || !dFor(S.tasks.get(bad)) ? tr('Dependencies only between tasks of projects') : tr('No permission'));
    else if (ids.some(w => tlReaches(tid, w))) dgMark(row, 'dgno', tr('Not possible: that would be a loop'));
    else dgMark(row, 'dgdep', ids.length > 1 ? trn('{0} task waits on this one', '{0} tasks wait on this one', ids.length) : tr('Waits on this task'));
    e.dataTransfer.dropEffect = 'link';
    return true;
  }
  if (!DG.ids) return dgs_over(e, row, id, tid);  // 2.122.3 B (#2334): one task, the middle of a row
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  let zn = dgZone(row, e.clientY);
  if (own && zn === 'onto') zn = dropAfter(row, e.clientY) ? 'after' : 'before';
  if (zn !== 'onto' && dropNo(row, e.clientY, ids)) { dgLast = null; return true; }  // (#7344): no highlight; the drop says why
  if (zn === 'onto') dgMark(row, 'dgonto', trn('{0} task becomes its subtask', '{0} tasks become its subtasks', dgRoots(ids).length));
  else row.classList.add(zn === 'after' ? 'dropafter' : 'dropbefore');
  dgLast = {row, zn, cls: zn === 'onto' ? 'dgonto' : zn === 'after' ? 'dropafter' : 'dropbefore'};
  return true;
}
// true = handled here (dnd.js does nothing more)
function dgDrop(e, id) {
  const el = e.target, ids = DG.ids, y = e.clientY, alt = e.altKey;
  const z = el.closest?.('.dgzone'), row = el.closest?.('#view .trow');
  const end = () => { dgClear(); dgEnd(); $$('.dragging,.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dragging', 'dropbefore', 'dropafter', 'drop')); document.body.classList.remove('tdrag'); };
  if (z) {
    end();
    if (z.classList.contains('dgoff') || !S.sel || S.sel === id) return true;
    const w = z.dataset.dgz === 'by' ? S.sel : id, b = z.dataset.dgz === 'by' ? id : S.sel;
    if (!dgDepOk(w, b)) { roToast(); return true; }
    dgDepAdd([[w, b]]);
    return true;
  }
  if (alt && row && !row.closest('#detail')) {
    const tid = +row.dataset.id, ws = (ids || [id]).filter(w => w !== tid);
    end();
    const ok = ws.filter(w => dgDepOk(w, tid));
    if (!ok.length) { toast(!dFor(S.tasks.get(tid)) ? tr('Dependencies only between tasks of projects') : tr('No permission')); return true; }
    dgDepAdd(ok.map(w => [w, tid]));
    return true;
  }
  if (!ids && row && !row.closest('#detail') && dgs_mid(row, y) && dgs_ok(id, +row.dataset.id)) { end(); dgMakeSubs([id], +row.dataset.id); return true; }  // 2.122.3 B (#2334)
  if (!ids) return false;
  end();
  if (el.closest?.('#detail')) return true;
  const side = el.closest?.('.srow[data-drop]'), quad = el.closest?.('.quad'), cell = el.closest?.('.cal .cell');
  const wcol = el.closest?.('.wcol'), wad = el.closest?.('.wad, .wh');
  // (#7344, #7351): the drop core first (My tasks, a project's list and board: rows, sections, columns, "New section"); the middle
  // of a row stays "subtasks"
  { const zn = row && dgZone(row, y); if (zn !== 'onto' || ids.includes(+row.dataset.id)) { if (dropRun(ids, el, y, row ? (zn === 'onto' ? dropAfter(row, y) : zn === 'after') : undefined)) return true; } }
  if (row) { if (dgZone(row, y) === 'onto' && !ids.includes(+row.dataset.id)) dgMakeSubs(ids, +row.dataset.id); return true; }
  const may = ids.filter(i => canEdit(S.tasks.get(i)));
  if (!may.length) { roToast(); return true; }
  if (side) {
    const k = side.dataset.drop;
    if (k.startsWith('l:')) mv_ask(ids, listById(+k.slice(2))).then(y => y && dgToList(ids, +k.slice(2)));  // 2.455.0 (#3848)
    else if (k === 'inbox') dgToList(ids, inbox().id);
    else if (k === 'today' || k === 'tomorrow') batch('patch', {due: k === 'today' ? today() : addDays(today(), 1)}, false, may);
    else if (k === 'trash') batch('delete', {}, true, may);
    else if (k === 'done') batch('complete', {}, false, may);
    return true;
  }
  if (cell) { batch('patch', {due: cell.dataset.day}, false, may); return true; }
  if (wad) { batch('patch', {due: wad.dataset.day, due_time: null}, false, may); return true; }
  if (wcol) {
    const m = Math.max(0, Math.min(23 * 60 + 45, Math.round((y - wcol.getBoundingClientRect().top) / weekH() * 4) * 15));
    batch('patch', {due: wcol.dataset.day, due_time: `${pad(Math.floor(m / 60))}:${pad(m % 60)}`}, false, may);
    return true;
  }
  if (quad) { const q = +quad.dataset.quad; if (q !== 5 || ids.some(i => (S.tasks.get(i)?.priority || 0) !== 7)) batch('patch', {priority: q}, false, may); return true; }  // 2.574.0 (#3376): Urgent stays in the top quadrant
  return true;
}
// 2.122.3 B (#2334): a single dragged task (mouse or finger) onto the middle of another becomes its subtask, as a
// selection does (dgMakeSubs: one batch, one Undo). Only where it may: both editable, no milestone, not under itself or
// its own subtask, not already there, the depth fits, no move into / out of a list with the lock (that needs a PATCH).
// Elsewhere (and the upper / lower part of a row) dnd.js moves it as before.
function dgs_ok(id, tid) {
  const t = S.tasks.get(id), p = S.tasks.get(tid);
  if (!t || !p || id <= 0 || tid <= 0 || id === tid || t.context || p.context || !canEdit(t) || !canEdit(p) || isMs(t) || isMs(p)) return false;
  if (t.parent_id === tid || dgAncestors(tid).includes(id) || !dgFits(tid, id)) return false;
  return t.list_id === p.list_id || !(typeof le2eOn === 'function' && (le2eOn(t.list_id) || le2eOn(p.list_id)));
}
// the middle of a row that has a size (a row without one keeps the old halves)
const dgs_mid = (row, y) => row.getBoundingClientRect().height > 0 && dgZone(row, y) === 'onto';
function dgs_over(e, row, id, tid) {
  if (!dgs_mid(row, e.clientY) || !dgs_ok(id, tid)) return false;
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  dgMark(row, 'dgonto', tr('As a subtask of this task'));
  dgLast = {row, zn: 'onto', cls: 'dgonto', one: true};
  return true;
}
// the finger's drag (dnd.js, once per frame): true = the middle of a row is marked here, else dnd.js marks before / after
let dgsRow = null;
function dgs_touchMark(at, id, y) {
  const row = at?.closest?.('#view .trow'), on = !!row && !row.closest('#detail') && dgs_mid(row, y) && dgs_ok(id, +row.dataset.id);
  if (on && row === dgsRow && row.classList.contains('dgonto')) return true;
  if (dgsRow) { dgsRow.classList.remove('dgonto'); delete dgsRow.dataset.dg; dgsRow = null; }
  if (!on) return false;
  $$('.dropbefore,.dropafter,.drop').forEach(x => x.classList.remove('dropbefore', 'dropafter', 'drop'));
  dgMark(row, 'dgonto', tr('As a subtask of this task'));
  dgsRow = row;
  return true;
}
function dgs_touchDrop(el, id, y) {
  const row = el?.closest?.('#view .trow');
  if (!row || row.closest('#detail') || y == null || !dgs_mid(row, y) || !dgs_ok(id, +row.dataset.id)) return false;
  dgMakeSubs([id], +row.dataset.id);
  return true;
}
// the two drop fields in the open task's dependencies (only while a task is dragged)
function dgZonesShow(id) {
  const box = $('#detail #d-deps'), t = S.sel && taskById(S.sel), d = S.tasks.get(id);
  if (!box || !t || !d || t.id === id || $('.dgzones', box)) return;
  const by = dgDepOk(t.id, id), bl = dgDepOk(id, t.id);
  const zone = (k, ok, lab, sub) => `<div class="dgzone ${ok ? '' : 'dgoff'}" data-dgz="${k}" ${ok ? '' : `title="${esc(tr('Not possible here'))}"`}><b>${esc(lab)}</b><span>${esc(sub)}</span></div>`;
  const div = document.createElement('div');
  div.className = 'dgzones'; div.setAttribute('aria-hidden', 'true');
  div.innerHTML = zone('by', by, tr('Waiting on'), tr('“{0}” waits on the dragged task', dgShort(t.title))) + zone('blocking', bl, tr('Blocking'), tr('The dragged task waits on “{0}”', dgShort(t.title)));
  box.querySelector('h5')?.after(div);
  DG.zones = true;
}
function dgEnd() { DG.ids = null; if (DG.zones) { $$('.dgzones').forEach(x => x.remove()); DG.zones = false; } }
document.addEventListener('dragstart', e => {
  dgEnd();
  const r = e.target.closest?.('#view .trow[draggable="true"]'); if (!r) return;
  const id = +r.dataset.id, t = S.tasks.get(id); if (!t) return;
  if (S.multi.size >= 2 && S.multi.has(id)) {
    DG.ids = dgOrder([...S.multi]);
    const g = document.createElement('div');
    g.className = 'dgghost'; g.textContent = trn('{0} task', '{0} tasks', DG.ids.length);
    document.body.appendChild(g);
    try { e.dataTransfer.setDragImage(g, 14, 14); } catch { /* old browsers: the row as the image */ }
    setTimeout(() => g.remove(), 0);
    requestAnimationFrame(() => DG.ids?.forEach(i => $(`#view .trow[data-id="${i}"]`)?.classList.add('dragging')));
  }
  e.dataTransfer.effectAllowed = 'all';  // move, and link for Alt (dependencies)
  setTimeout(() => dgZonesShow(id), 0);  // after the drag began (a layout change inside dragstart can end it)
  // the first drag on this device explains the extra ways (as the timeline does); after dragstart (no layout change inside it)
  const tip = DG.ids ? !hintSeen('dgmulti') && 'dgmulti' : dFor(t) && canEdit(t) && !hintSeen('dgalt') && 'dgalt';
  if (tip) setTimeout(() => { hintDone(tip); toast(tip === 'dgmulti' ? tr('Tip: drop onto the middle of a task and the selected tasks become its subtasks; above or below it moves them as a block.') : tr('Tip: hold Alt (Option on a Mac) while you drop onto another task: it then waits on that task.'), null, 9000); }, 0);
});
document.addEventListener('dragend', () => { dgClear(); dgEnd(); });
// the multi panel and the phone's selection menu (multiedit.js, sidebar.js)
function dgMeHtml(ts) {
  if (!ts.length || ts.some(t => t.context)) return '';
  const subs = ts.some(t => t.parent_id), lock = ts.every(t => !canEdit(t));
  return `<div class="dsec dgme"><h5>${ic('indent', 's')}${tr('Structure')}</h5><div class="dgmeb">
    <button type="button" class="btn sm" data-act="dg-sub" ${lock ? 'disabled' : ''}>${ic('indent', 's')} ${esc(tr('Subtasks of…'))}</button>
    ${subs ? `<button type="button" class="btn sm" data-act="dg-out" ${lock ? 'disabled' : ''}>${ic('outdent', 's')} ${esc(tr('Out of the parent task'))}</button>` : ''}</div></div>`;
}
const dgMenuItems = ids => [{label: tr('Subtasks of…'), icon: 'indent', fn: () => dgSubPick(ids)},
  ...(ids.some(i => S.tasks.get(i)?.parent_id) ? [{label: tr('Out of the parent task'), icon: 'outdent', fn: () => dgDetach(ids)}] : [])];
document.addEventListener('click', e => {
  const a = e.target.closest?.('[data-act="dg-sub"], [data-act="dg-out"]'); if (!a || a.disabled) return;
  const ids = [...S.multi].filter(i => S.tasks.get(i));
  if (a.dataset.act === 'dg-sub') dgSubPick(ids); else dgDetach(ids);
});
