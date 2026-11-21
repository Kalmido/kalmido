// @ts-check
/* Kalmido web client: the offline start state in IndexedDB (2.663.0, #4200), loaded on demand (lazyload.js) by core.js startSave /
   startRead. (#7595): this module is THE owner of the start state in a browser with IndexedDB - its place, its gate, its
   schedule and the take-over of the old copy; core.js startSave only says "the state changed", liveparts.js only folds the
   delta into S.lpCache. The rules:
   - the mode is the browser's, once: globalThis.indexedDB there = the record below is the start state, never anything else;
     without it core.js keeps it in localStorage "tasks.cache" (icons.js DEV_STORES: the fallback of kalmido-start). A refused
     or hung IndexedDB never moves one window over to localStorage.
   - one record in the database "kalmido-start" (store "s", key "state"): {o} a structured clone while no list is locked, else
     {s} the JSON of LS.set with le2eRepl (only ciphers leave the memory, liste2e.js H1; a state the browser cannot clone goes as
     that JSON too); at = when it was written, v / sat = the server version of the state and when the server confirmed it (_at)
   - the newer record wins, in the same transaction: a write reads the record first and leaves it when the record is newer
     (higher v, or the same v confirmed later) - an older window being hidden never writes its state over a newer one
   - the schedule: a change is written when the browser is idle, at most every 30 s; a page being hidden writes at once
     (oc_now: #6340), a state unchanged since the last write at most every 10 minutes
   - the gate: core.js startMay (devCopyOk, not an own window), asked when the write runs, not when it is planned
   - a write that did not land (quota, aborted, a connection the browser closed, an open that hung): logged once (console.warn,
     the client error report), no copy anywhere else (class copy: nothing of the own is lost, the server has it); the
     connection is dropped, so the next change opens a fresh one
   - the old localStorage copy "tasks.cache" (a browser of before 2.663, or of before this mode rule): taken over once - at the
     first read it goes into the record when it is newer than the record (else the record stays), at the first write the
     newer state is written; then it is removed. While IndexedDB does not open, a read gets that copy as it is (read only).
   - (#6340): the state carries _at = when the server last confirmed it (ms, core.js startAt); an offline start shows
     its real age from it, never the time since the page started
   Classic script sharing the global scope with the others. */
'use strict';

const OC_DB = 'kalmido-start', OC_KEY = 'state', OC_GAP = 30000, OC_SAME = 600e3;
/** @type {{h: ReturnType<typeof idbHeld> | null, t: any, warned: boolean, wrote: number, gen: number, last: number, wv: any}} */
const OC = {h: null, t: 0, warned: false, wrote: 0, gen: 0, last: 0, wv: undefined};  // gen: counted up by oc_drop, a write planned before it is void; t: the planned write; last / wv: when and which version the last write landed
// 2.1120.0 (#6036): the connection over core.js idbHeld: closed by the browser (a reload on Android) or by another tab's sign-out
// (versionchange) -> opened again at the next access, a "connection is closing" no longer ends up as a warning on window.onerror
function oc_held() {
  if (!globalThis.indexedDB) return null;
  return OC.h ||= idbHeld(() => new Promise((ok, no) => {
    const r = indexedDB.open('kalmido-start', 1);  // = OC_DB; the literal for tools/check_layout.py (sw.js swStartFold opens it too, #6334)
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains('s')) r.result.createObjectStore('s'); };
    r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); r.onblocked = () => no(new Error('blocked'));
  }));
}
// (#7595): a write that did not land: the next access opens the connection anew instead of writing on the dead one
function oc_reopen() { const h = OC.h; OC.h = null; if (h) h.close().catch(() => {}); }
function oc_db() { const h = oc_held(); return h ? h.db() : Promise.reject(new Error('no IndexedDB')); }
async function oc_tx(mode, fn) {
  const h = oc_held(); if (!h) throw new Error('no IndexedDB');
  const t = (await h.tx('s', mode)), out = fn(t.objectStore('s'));
  await new Promise((ok, no) => { t.oncomplete = ok; t.onerror = t.onabort = () => no(t.error || new Error('aborted')); });
  return out instanceof IDBRequest ? out.result : out;
}
function oc_warn(what, e) {
  const m = `Kalmido: offline start state (${what}): ${e?.name || ''} ${e?.message || e}`.trim();
  console.warn(m);
  if (!OC.warned) { OC.warned = true; try { window.dispatchEvent(new ErrorEvent('error', {message: m, error: e instanceof Error ? e : new Error(m)})); } catch { /* old browser */ } }  // clienterr.js reports it once per page
}
// the age of a state [server version, confirmed at]; a record carries it beside the state (v, sat), one of before only inside
const oc_age = c => [+c?.v || 0, +c?._at || 0];
const oc_newer = (a, b) => a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
function oc_state(rec) {
  if (!rec) return null;
  let c = rec.o || null;
  if (!c) { try { c = JSON.parse(rec.s); } catch { return null; } }
  return c && typeof c === 'object' ? c : null;
}
const oc_recAge = rec => rec.v !== undefined ? [+rec.v || 0, +rec.sat || 0] : oc_age(oc_state(rec));
// the record of the state c: a structured clone where it may be (no locked list), else the JSON of LS.set
/** @returns {{s?: string, o?: any, at: number, v: number, sat: number}} */
function oc_rec(c) {
  const repl = typeof le2eRepl === 'function' ? le2eRepl() : undefined, [v, sat] = oc_age(c);
  return repl ? {s: JSON.stringify(c, repl), at: Date.now(), v, sat} : {o: c, at: Date.now(), v, sat};
}
// one transaction: the record is read, rec goes in only when it is at least as new (an equal age = the same state, written
// again with its newest content); true = written. gen: a sign-out meanwhile voids it
function oc_putNewer(rec, gen) {
  let put = false, err = null;
  return oc_tx('readwrite', st => {
    const g = st.get(OC_KEY);
    g.onsuccess = () => {
      if (gen !== OC.gen || (g.result && oc_newer(oc_recAge(g.result), [rec.v, rec.sat]))) return;
      try { st.put(rec, OC_KEY); put = true; } catch (e) { err = e; try { st.transaction.abort(); } catch { /* ended */ } }  // a DataCloneError / quota thrown by put: its own name, not the abort's
    };
  }).then(() => { if (err) throw err; return put; }, e => { throw err || e; });
}
async function oc_put(c, gen) {
  let rec = oc_rec(c);
  try { return await oc_putNewer(rec, gen); }
  catch (e) {
    if (e?.name !== 'DataCloneError' || rec.s !== undefined) throw e;
    rec = {s: JSON.stringify(c), at: rec.at, v: rec.v, sat: rec.sat};  // a value the browser cannot clone (a function, a node): the JSON as before
    return oc_putNewer(rec, gen);
  }
}
function oc_lsOld() { try { return localStorage.getItem('tasks.cache'); } catch { return null; } }  // private mode
function oc_lsDrop(raw) { try { if (raw == null || localStorage.getItem('tasks.cache') === raw) localStorage.removeItem('tasks.cache'); } catch { /* private mode */ } }
// the write itself: the newest S.lpCache, through the gate; not landed = said once, the next change tries on a fresh connection
async function oc_write(gen = OC.gen) {
  OC.t = 0;
  const c = S.lpCache; if (!c || gen !== OC.gen || !startMay()) return;
  try {
    await oc_db();
    if (S.lpCache !== c || gen !== OC.gen || !startMay()) return;  // dropped (sign-out, another sign-in) or replaced meanwhile: that one has its own write
    const v = c.v;
    if (await oc_put(c, gen)) OC.wrote++;
    OC.last = Date.now(); OC.wv = v;
    oc_lsDrop(null);  // the old copy: the record holds this state or a newer one now
  } catch (e) { oc_warn('not written, the next change tries again', e); oc_reopen(); }
}
// core.js startSave: a write when the browser is idle, at most every OC_GAP (one at a time; it takes the newest state when it runs)
function oc_soon() {
  if (OC.t) return;
  const tok = OC.t = {g: OC.gen}, run = () => { if (OC.t === tok) oc_write(tok.g); };
  const idle = () => { if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(run, {timeout: 10000}); else setTimeout(run, 300); };
  const wait = OC.last + OC_GAP - Date.now();
  if (wait > 0) setTimeout(idle, wait); else idle();
}
// (#6340): core.js startSave(true) when the page is hidden: written now, not when idle (a hidden page may never be idle
// again, and the next start would miss the last changes); nothing planned and the same version written within 10 minutes = nothing new
function oc_now() {
  const planned = !!OC.t;
  OC.t = 0;
  if (!planned && OC.last && S.lpCache?.v === OC.wv && Date.now() - OC.last < OC_SAME) return Promise.resolve();
  return oc_write(OC.gen);
}
// core.js startRead: the record; the old localStorage copy is taken over once in the same transaction when it is newer
async function oc_get() {
  const raw = oc_lsOld();
  let old = null; if (raw) { try { old = JSON.parse(raw); } catch { /* broken: the record */ } }
  if (old && typeof old !== 'object') old = null;
  const g = OC.gen;
  let c = null;
  try {
    await oc_tx(old ? 'readwrite' : 'readonly', st => {
      const r = st.get(OC_KEY);
      r.onsuccess = () => {
        const rec = r.result;
        if (old && g === OC.gen && (!rec || oc_newer(oc_age(old), oc_recAge(rec)))) {
          const [v, sat] = oc_age(old);
          st.put({s: raw, at: Date.now(), v, sat}, OC_KEY); c = old;
        } else {
          c = oc_state(rec);
          if (c && !c._at && rec.at) c._at = rec.at;  // (#6340): a record of before carries only its write time
        }
      };
    });
  } catch (e) { oc_warn('reading', e); oc_reopen(); return old; }  // IndexedDB does not open: the old copy as it is, read only
  if (old) oc_lsDrop(raw);  // taken over or older than the record: it goes
  return c;
}
// icons.js devEnd (class copy): the record goes (the connection stays open: a clear, not a deleteDatabase)
function oc_del() { return oc_tx('readwrite', st => st.delete(OC_KEY)); }
function oc_drop() { OC.t = 0; OC.gen++; OC.last = 0; OC.wv = undefined; return oc_del().catch(() => {}); }
devDrop('kalmido-start', () => { startClr(); return oc_drop(); });  // (#6500): the drop of class copy (icons.js DEV_STORES)
