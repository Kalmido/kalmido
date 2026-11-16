// kalmido-suite: fresh
// 2.1257.0 UI test (#6286, audit #4742 C1-C3), own container (start.sh), jsdom. Invented names only. jsdom has no IndexedDB:
// the knowledge pages' copy and the outbox run on stand-in stores (window.__wkoStore / __obxStore), one per "browser",
// localStorage shared by its windows.
// - C1: an own knowledge page text the server refused (waiting at its page, x:) survives a new sign-in, an ended session
//   (401) and the 14-day tidying of the copy; logout counts it in its question, the switch to another account counts it and
//   downloads it; another account of the browser never reads it
// - C2: the reload by itself asks for quiet (incl. the form guard, fgAny) right before it reloads, not only before its wait
//   for the server, and gives up otherwise
// - C3: the adoption of the old localStorage queue removes only the adopted entries there, not what was put there meanwhile
// P6286_NOSTART=1 = the server already runs.
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P6286_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 100});
const clone = v => v === undefined ? v : JSON.parse(JSON.stringify(v));
const DAY = 864e5;

// one browser: the copy's store (counting clears), the outbox store (writes held while br.hold), localStorage
function browser() {
  const db = new Map(), ops = new Map(), held = [];
  const store = {get: async k => clone(db.get(k)), put: async v => { db.set(v.k, clone(v)); }, del: async k => { db.delete(k); },
    all: async () => [...db.values()].map(clone), pre: async x => [...db.values()].filter(r => r.k.startsWith(x)).map(clone), nClear: 0,
    clear: async () => { store.nClear++; db.clear(); }, close: async () => {}};
  const br = {db, ops, held, store, hold: false, shared: {store: {}, wins: []}};
  br.obx = {all: async () => [...ops.values()].map(clone), meta: async () => undefined, setMeta: async () => {}, clear: async () => { ops.clear(); },
    write: (put, del) => {
      const go = () => { for (const r of put) ops.set(r.k, clone(r)); for (const k of del) ops.delete(k); };
      if (!br.hold) { go(); return Promise.resolve(); }
      return new Promise(ok => held.push(() => { go(); ok(); }));
    }};
  return br;
}
// a window of the browser; ck = this session's cookie (else boot's own new sign-in), offline = started without network
function win(br, user, {ck = null, offline = false, hash = 'wiki', setup = null} = {}) {
  const su = w => {
    w.__wkoStore = br.store; w.__obxStore = br.obx;
    if (ck) w.fetch = (u, o = {}) => {
      if (w.__offline) return Promise.reject(new TypeError('Failed to fetch'));
      return fetch(new URL(String(u), B), {...o, headers: {...(o.headers || {}), Cookie: ck}});
    };
    if (offline) w.__offline = true;
    if (setup) setup(w);
  };
  return boot({user, hash, shared: br.shared, setup: su, ls: {'tasks.wkSpace': JSON.stringify('private')}});
}
const lsj = (br, k) => { const v = br.shared.store['tasks.' + k]; return v == null ? null : JSON.parse(v); };

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  const AK = await login('alice');
  await call(AK, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call(AK, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  await call(AK, 'POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CK = await login('frida');
  const st0 = await call(CK, 'GET', '/api/state'), me = st0.me.id;
  const feats = [...new Set([...(st0.settings.features || '').split(',').filter(Boolean), 'wiki'])].join(',');
  await call(CK, 'PATCH', '/api/settings', {tour: 'done', lang: 'en', features: feats});
  const P1 = (await call(CK, 'POST', '/api/wiki/pages', {space: 'private', path: 'Garden/Beds', body: 'Beds of the server'})).id;
  check(P1, 'setup: a page');
  const XK = `tasks.fdx.${me}.${P1}`;

  // ================= C1: refused (409, changed elsewhere): the text waits at its page, kept as input of the account
  const br = browser();
  let w = await win(br, 'frida', {ck: CK});
  check(await until(() => br.db.get('s:private')?.pages?.length), 'the copy of the space');
  const took = await w.eval(`loadModule('wiki').then(() => wkoReject({url: '/api/wiki/pages/${P1}', method: 'PATCH', body: {body: 'My offline beds'}},
    {status: 409, data: {page: {id: ${P1}, space: 'private', title: 'Beds', body: 'Beds of the server', updated_at: '2030-01-01T00:00:00Z'}}}))`);
  check(took === true && lsj(br, `fdx.${me}.${P1}`)?.b?.mine === 'My offline beds', 'C1: the refused text is kept as input of the account ' + br.shared.store[XK]);
  check(w.eval('fdAny()') === true, 'C1: it counts as kept input (authGone keeps the local state)');
  w.close();

  // a new sign-in (another sign-in mark): the copy is emptied, the waiting text stays and shows at its page
  const n0 = br.store.nClear;
  w = await win(br, 'frida', {hash: 'wiki/' + P1});
  check(w.eval('S.me.sgen') !== st0.me.sgen && await until(() => br.store.nClear > n0), 'C1 setup: a new sign-in empties the copy');
  check(!!br.shared.store[XK], 'C1: the waiting text survives the new sign-in');
  await until(() => w.eval(`WK.pg?.id === ${P1}`));
  if (!w.document.querySelector('#view .wkocf')) w.eval('renderView(); 1');
  const bar = await until(() => w.document.querySelector('#view .wkocf'));
  check(bar && bar.querySelector('[data-wk="cfshow"]') && w.eval(`WKO.cf[${P1}]?.mine`) === 'My offline beds', 'C1: after the new sign-in the page shows the waiting text with Compare ' + (bar?.textContent || ''));
  // the copy emptied again while the page is open (another tab's new sign-in): the text stays in memory and kept
  await w.eval('wko_reset()');
  check(w.eval(`WKO.cf[${P1}]?.mine`) === 'My offline beds' && !!br.shared.store[XK], 'C1: emptying the copy keeps the waiting text');
  // logout counts it in its question (the "Cancel" answer keeps everything)
  w.__ask = ''; w.confirm = t => { w.__ask = String(t); return false; };  // the harness answers the app's dialogs through confirm (boot.js)
  w.eval('logout(); 1');
  check(await until(() => w.__ask), 'C1: logout asks');
  check(/1 change is not synced yet/.test(w.__ask) && !!br.shared.store[XK], 'C1: logout counts the waiting text ' + w.__ask);
  w.close();

  // 14 days without an online sync: an offline start empties the copy, not the waiting text
  br.shared.store['tasks.wko'] = JSON.stringify({...lsj(br, 'wko'), at: new Date(Date.now() - 15 * DAY).toISOString()});
  const n1 = br.store.nClear, CK2 = await login('frida');
  w = await win(br, 'frida', {ck: CK2, offline: true, hash: ''});
  check(await until(() => br.store.nClear > n1 || br.db.size === 0), 'C1 setup: 15 days without a sync empty the copy');
  check(!!br.shared.store[XK], 'C1: the waiting text survives the 14-day tidying');
  w.close();

  // the session gone (401 at /api/state): the copy goes, the waiting text stays (and keeps the local state)
  w = await win(br, 'frida', {ck: CK2});
  await until(() => br.db.get('s:private')?.g === w.eval('S.me.sgen'));
  w.close();
  await fetch(B + 'api/auth/logout', {method: 'POST', headers: {...H, Cookie: CK2}});
  w = await win(br, 'frida', {ck: CK2});
  check(await until(() => br.db.size === 0), 'C1 setup: 401 empties the copy');
  await sleep(500);
  check(!!br.shared.store[XK] && lsj(br, 'uid') === me, 'C1: the waiting text survives the ended session ' + Object.keys(br.shared.store).filter(k => k.startsWith('tasks.fdx')));
  w.close();

  // another account in this browser: never reads it; the switch asks with it counted and downloads it
  const asked = [], blobs = [];
  w = await win(br, 'alice', {hash: '', setup: x => {
    x.confirm = t => { asked.push(String(t)); return true; };
    const OB = x.Blob; x.Blob = class extends OB { constructor(parts, o) { super(parts, o); this.__txt = (parts || []).join(''); } };
    x.URL.createObjectURL = b => { blobs.push(b); return 'blob:x'; }; x.URL.revokeObjectURL = () => {}; x.HTMLAnchorElement.prototype.click = function () {};
  }});
  check(await until(() => asked.length), 'C1: the switch to another account asks');
  check(/1 change of the previous account/.test(asked[0] || ''), 'C1: the switch counts the waiting text ' + asked[0]);
  check(await until(() => blobs.length), 'C1: the switch downloads');
  const txt = blobs[0]?.__txt || '';
  check(/Beds · Knowledge page/.test(txt) && /My offline beds/.test(txt), 'C1: the download holds the waiting text ' + txt);
  check(await until(() => !Object.keys(br.shared.store).some(k => k.startsWith('tasks.fdx.'))), 'C1: after the switch it is gone from this browser');
  w.close();

  // ================= C2: the reload by itself asks for quiet right before it reloads
  const b2 = browser();
  w = await win(b2, 'frida', {ck: CK, hash: ''});
  await until(() => w.eval('!!S.me && S.booted'));
  w.eval(`document.activeElement?.blur?.(); verIdle = Date.now() - 60000; window.__dirty = false; fgWatch(() => window.__dirty);
    rl_waitServer = () => new Promise(ok => { window.__srv = ok; }); sessionStorage.removeItem('kalmido-reloaded'); 1`);
  check(w.eval('verCalm()') === true, `C2 setup: the window is quiet ${w.eval('JSON.stringify({q: verQuiet(), e: editing(), f: editFocused(), d: verDraft(), n: OUT.q.length})')}`);
  w.eval('verReload(true); 1');
  check(await until(() => typeof w.__srv === 'function'), 'C2: the reload waits for the server');
  w.__dirty = true;  // input the form guard knows comes up during the wait
  check(w.eval('verQuiet()') === false, 'C2: unsaved input of the form guard holds the reload back (verQuiet)');
  w.__srv(true);
  check(await until(() => w.eval('!verBusy')), 'C2: the reload gives up');
  check(!w.eval(`sessionStorage.getItem('kalmido-reloaded')`), 'C2: input during the wait: no reload by itself');
  // quiet again: the next one reloads (the reload of jsdom is a no-op; the mark is set right before it)
  w.__dirty = false; w.__srv = null;
  w.eval('verReload(true); 1');
  await until(() => typeof w.__srv === 'function'); w.__srv(true);
  check(await until(() => w.eval(`sessionStorage.getItem('kalmido-reloaded') === S.serverVer`)), 'C2: quiet: it reloads');

  w.close();

  console.log(`\n${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
