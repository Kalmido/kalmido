// @ts-check
/* Kalmido web client: the browser's own errors to the server (2.102.0, #1999). Loaded right after reloadguard.js, so an
   error while the other modules start is caught too. An unhandled error (window "error") or a rejected promise nobody
   handled ("unhandledrejection") is sent to POST /api/client-errors -- only when the server operator chose a list for it
   (S.about.client_errors) -- and becomes a bug ticket there. Sent: the message, the place below /static/ (file:line:col),
   a short stack of such places, the client's version and the name of the open area; never texts of tasks, form values or
   addresses with ids (the server cuts the message once more). At most CER_MAX reports per page load, the same one once.
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';
const CER_MAX = 20, CER_WAIT = [];
let cer_sent = 0;
const cer_seen = new Set();

/** The name of the open area ("tasks", "office", "today"), never an id. */
function cer_view() {
  const r = typeof S !== 'undefined' && S.route ? S.route : null;
  if (!r) return '';
  const k = typeof r.key === 'string' && /^[a-z][\w-]{0,30}$/.test(r.key) ? '-' + r.key : '';
  return String(r.mod || '').replace(/[^\w-]/g, '').slice(0, 20) + k;
}

/** A script address as /static/...: origin, query and hash dropped ("" outside /static/). @param {string} u */
function cer_path(u) {
  const m = /\/static\/[\w./-]+?\.m?js/.exec(String(u || ''));
  return m ? m[0] : '';
}

// (#7531): what "Report a problem" (report.js) may send as its context block: the last errors of this page load and the
// last failed requests, kept here whether or not the server takes error reports; never texts (cer_clean), never a query part
/** @type {{msg: string, place: string}[]} */
const CER_LAST = [];
/** @type {{method: string, path: string, status: number, ms: number}[]} */
const CER_REQ = [];
/** A message without data of a person (as the server's cer_text): addresses, quoted texts, long numbers cut. @param {string} s */
function cer_clean(s) {
  return String(s || '').replace(/[\x00-\x1f\x7f]+/g, ' ').replace(/\S+@\S+/g, '<mail>').replace(/\b(?:https?|blob|data|file):\S*/gi, u => cer_path(u) || '<url>')
    .replace(/(['"`])(.*?)\1/g, (m, q, x) => /^[\w$.#-]{1,40}$/.test(x) ? m : q + '…' + q).replace(/\b[0-9a-fA-F-]{16,}\b|\d{4,}/g, '<n>').trim().slice(0, 300);
}
/** A request's path as the dialog "What goes along" SHOWS it (#7531 F8): /api/<area> and numbers only, every other part "_".
 *  Only for the eye, never for sending (F11): CER_REQ keeps the real path, the server keeps only the pattern of its route
 *  (meldung.py rpt_req_route, e.g. /api/account/export); a masked path would find no route there and fall away.
 *  @param {string} p */
const cer_reqPath = p => p.split('/').map((x, i) => i < 3 || /^\d{1,12}$/.test(x) ? x : '_').join('/').slice(0, 160);
/** A failed request (core.js rawFetch0): method, path without origin and query (the real one: the server cuts it to its
 *  route's pattern, #7531 F11), status (0 = no answer), duration. */
function cer_req(/** @type {string} */ method, /** @type {string} */ url, /** @type {number} */ status, /** @type {number} */ t0) {
  const p = String(url || '').replace(/^[a-z][\w+.-]*:\/\/[^/]+/i, '').split(/[?#]/)[0];
  if (!p.startsWith('/api/')) return;
  CER_REQ.push({method: String(method || 'GET').toUpperCase(), path: p.slice(0, 160), status: status || 0, ms: Math.max(0, Math.round(performance.now() - t0))});
  if (CER_REQ.length > 8) CER_REQ.shift();
}
/** The page as a path: the address part after # without its query - its first part (the view) and numbers only, every other
 *  part "_" (a tag, a search or a name in the address never goes along, #7531; the server's rpt_route does the same). */
function cer_route() {
  const h = String(location.hash || '').split('?')[0].replace(/^#/, '');
  return '#' + h.split('/').map((x, i) => (i === 0 ? /^[a-z][\w-]{0,30}$/ : /^\d{1,12}$/).test(x) ? x : '_').join('/').slice(0, 150);
}
/** The context block of a report (#7531): page, version, device, the last errors and failed requests - no contents. */
function cer_ctx() {
  const ua = navigator.userAgent || '', br = /(Firefox|Edg|OPR|SamsungBrowser|Chrome|Version)\/(\d+)/.exec(ua);
  const plat = /** @type {any} */ (navigator).userAgentData?.platform || (/(Android|iPhone|iPad|Macintosh|Windows|Linux)/.exec(ua) || [])[1] || '';
  return {route: cer_route(), version: typeof APP_VER === 'string' ? APP_VER : '',
    device: {platform: String(plat).slice(0, 40), browser: br ? (br[1] === 'Version' ? 'Safari' : br[1] === 'Edg' ? 'Edge' : br[1]) + ' ' + br[2] : '',
      touch: matchMedia('(pointer: coarse)').matches, width: innerWidth, height: innerHeight, dpr: Math.round((window.devicePixelRatio || 1) * 100) / 100},
    errors: CER_LAST.slice(), requests: CER_REQ.slice()};
}

/** @param {{msg: string, src?: string, line?: number, col?: number, stack?: string, kind: string}} e */
function cer_send(e) {
  CER_LAST.push({msg: cer_clean(e.msg), place: cer_path(e.src || '') + (e.line ? ':' + e.line : '')}); if (CER_LAST.length > 5) CER_LAST.shift();  // (#7531)
  const on = typeof S !== 'undefined' && S.about ? !!S.about.client_errors : null;
  if (on === null) { if (CER_WAIT.length < 5) CER_WAIT.push(e); return; }  // before the first state: kept for cer_flush
  if (!on || cer_sent >= CER_MAX) return;
  const key = e.msg + '|' + cer_path(e.src || '') + ':' + (e.line || 0);
  if (cer_seen.has(key)) return;
  cer_seen.add(key); cer_sent++;
  const ver = typeof APP_VER === 'string' ? APP_VER : '';
  const body = {msg: e.msg.slice(0, 500), src: cer_path(e.src || ''), line: e.line || 0, col: e.col || 0,
    stack: String(e.stack || '').split('\n').map(cer_line).filter(Boolean).join('\n').slice(0, 2048), ver, view: cer_view(), kind: e.kind};
  try {
    // #7521: stays a plain fetch - keepalive, runs before core.js; an error report never waits for an answer
    fetch('/api/client-errors', {method: 'POST', keepalive: true, credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify(body)}).catch(() => {});
  } catch { /* never an error about an error */ }
}

/** One stack line as "name /static/js/x.js:1:2" (lines outside /static/ dropped). @param {string} l */
function cer_line(l) {
  const m = /(\/static\/[\w./-]+?\.m?js)(?:\?[^:\s)]*)?(:\d+(?::\d+)?)?/.exec(l);
  if (!m) return '';
  const fn = /^\s*(?:at\s+)?([\w$.<>]{1,60})(?:\s*\(|@)/.exec(l);
  return (fn ? fn[1] + ' ' : '') + m[1] + (m[2] || '');
}

/** Sends what came before the first state (nothing happens when reports are off); tries again while it has not come. */
function cer_flush(n = 0) {
  if (typeof S === 'undefined' || !S.about) { if (n < 8) setTimeout(() => cer_flush(n + 1), 15000); return; }
  CER_WAIT.splice(0).forEach(cer_send);
}

window.addEventListener('error', ev => {
  // a resource that failed to load (img, script) has no message: not a script error
  if (!(ev instanceof ErrorEvent) || !ev.message || ev.message === 'Script error.') return;
  // a browser extension's script (chrome-extension://, moz-extension://) is not ours
  if (ev.filename && !cer_path(ev.filename) && !ev.filename.startsWith(location.origin)) return;
  cer_send({msg: String(ev.message), src: ev.filename, line: ev.lineno, col: ev.colno, stack: ev.error && ev.error.stack, kind: 'error'});
});
window.addEventListener('unhandledrejection', ev => {
  const r = ev.reason;
  // offline, a refused write (already shown as a toast) and the session's end are expected, not errors of the client
  if (!r || r.name === 'Offline' || r.shown || r.message === 'auth' || r.message === 'offline' || r.message === 'down') return;
  if (typeof Offline === 'function' && r instanceof Offline) return;
  if (r.status && r.data) return;  // an answer of the server with an error (api() threw it)
  cer_send({msg: String(r && r.message || r).slice(0, 500), stack: r && r.stack, kind: 'rejection'});
});
setTimeout(cer_flush, 15000);
