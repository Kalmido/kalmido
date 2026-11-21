// kalmido-suite: fresh
// 2.1384.0 UI test (#6339, audit #4764 D1, D8, D9, D10), jsdom, fresh DB. Invented names only. jsdom has no IndexedDB: the outbox
// runs on a stand-in store (window.__obxStore, the five calls of core.js obxIdb) per "browser", one that can refuse its writes,
// and localStorage (boot.js, shared by the windows of a browser) can be made "full" (setItem throws QuotaExceededError).
// - D1: a change whose IndexedDB write failed waits in localStorage; the next change writes it into IndexedDB too and only then
//   does it leave localStorage (red before: the adoption filtered it out as "there already", wrote nothing and deleted the key)
// - D8: IndexedDB AND localStorage refuse: a lasting sign "Not saved - keep this window open" in the top bar, a tap explains it;
//   the next write that lands writes the whole queue and the sign goes. A kept input (fdKeep), the conflicts and outStash
//   (localStorage full: straight into the queue) the same way
// - D9: navigator.storage.persist() is asked for once the first change waits (once per page), not before
// - D10: the queue's IndexedDB would not open: the sign says that earlier waiting changes are not shown here
// - (#7595): with IndexedDB the queue is IndexedDB, localStorage "tasks.outbox" only its feed (one consumer, obxAdopt). A write
//   that failed puts only ITS entries into the feed. The same entry in both places: the newer one wins (its revision r) - the
//   feed's newer one (red before: the queue's older one was sent and the feed's dropped), the queue's newer one over an older
//   feed entry. Zusatz 1: IndexedDB opens in no window - the window sends its feed itself, also after a reload, exactly once;
//   a second window whose IndexedDB opens adopts the entry and sends it, the first one never sends it again
const {boot, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 50});
const clone = v => v === undefined ? v : JSON.parse(JSON.stringify(v));

// one browser: the queue's store (ops by key; br.fail = writes refused, br.closed = it does not open), localStorage (br.full)
function browser() {
  const ops = new Map(), persist = [];
  const br = {ops, persist, fail: false, closed: false, full: false, shared: {store: {}, wins: []}};
  br.store = {
    all: async () => { if (br.closed) throw new Error('UnknownError: the database connection is lost'); return [...ops.values()].map(clone); },
    write: async (put, del) => { if (br.fail) throw new Error('QuotaExceededError (IndexedDB)'); for (const r of put) ops.set(r.k, clone(r)); for (const k of del) ops.delete(k); },
    meta: async () => undefined, setMeta: async () => {}, clear: async () => { ops.clear(); },
  };
  br.setup = w => {
    w.__obxStore = br.store;
    Object.defineProperty(w.navigator, 'storage', {configurable: true, value: {persisted: async () => false, persist: async () => { persist.push(Date.now()); return true; }}});
  };
  return br;
}
// localStorage of the window "full": setItem throws as a browser does (boot.js gives a plain object, its setItem can be replaced)
function fullable(w, br) {
  const set = w.localStorage.setItem;
  w.localStorage.setItem = (k, v) => { if (br.full) { const e = new Error('The quota has been exceeded.'); e.name = 'QuotaExceededError'; throw e; } set(k, v); };
}
const sign = w => w.document.querySelector('#top .stlost');
const lsq = br => { const v = br.shared.store['tasks.outbox']; return v == null ? null : JSON.parse(v); };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const P = (await call('POST', '/api/lists', {name: 'Garden'})).id;
  const T = [];
  for (const t of ['Sow the beans', 'Water the beds', 'Cut the hedge', 'Fix the fence']) T.push((await call('POST', '/api/tasks', {title: t, list_id: P})).id);
  const ren = (w, i, title) => w.eval(`api('PATCH', '/api/tasks/${T[i]}', {title: ${JSON.stringify(title)}})`);

  // ================= D9 + D1
  const br = browser();
  const w = await boot({user: 'alice', hash: 'l/' + P, shared: br.shared, setup: br.setup});
  fullable(w, br);
  check(w.eval('OBX.on') === true, 'setup: the queue runs on its store');
  check(br.persist.length === 0, 'D9: nothing waits: no persist() yet');
  w.__offline = true;
  br.fail = true;
  // straight through outSave (no send attempt in between touches the entry again)
  const put = (i, title, k) => w.eval(`outSave(() => OUT.q.push({method: 'PATCH', url: '/api/tasks/${T[i]}', body: {title: ${JSON.stringify(title)}}, uid: S.me.id, k: '${k}'})); 1`);
  put(0, 'Sow the beans early', 'k6339a');
  check(w.eval('OUT.q.length') === 1, 'D1: the change waits');
  check(await until(() => (lsq(br) || []).length === 1), 'D1: its IndexedDB write failed: it waits in localStorage');
  check(await until(() => br.persist.length === 1), 'D9: persist() asked for with the first waiting change');
  check(!sign(w), 'D1: localStorage kept it: no sign');
  br.fail = false;
  put(1, 'Water the beds at dusk', 'k6339b');
  check(await until(() => br.ops.has('k6339b')), 'D1: the next change is in the store');
  check(br.ops.has('k6339a'), `D1: the same write took the first one into IndexedDB as well (in the store: ${[...br.ops.keys()]})`);
  check(await until(() => lsq(br) === null), 'D1: only then it leaves localStorage');
  check(br.persist.length === 1, 'D9: asked once per page');

  // ================= D8: IndexedDB and localStorage refuse
  br.fail = true; br.full = true;
  await ren(w, 2, 'Cut the hedge in May');
  check(await until(() => !!sign(w)), 'D8: nothing kept it: the sign in the top bar');
  check(/Not saved/.test(sign(w)?.textContent || '') && /keep it open/.test(sign(w)?.title || ''), 'D8: it says "not saved", its title what to do: ' + sign(w)?.title);
  sign(w).click();
  check(await until(() => /keep it open until they are sent/.test(w.document.querySelector('#toast')?.textContent || '')), 'D8: a tap explains it');
  // outStash (a page going away) with localStorage full: straight into the queue, not lost
  w.eval(`outStash([{method: 'PATCH', url: '/api/tasks/${T[3]}', body: {title: 'Fix the fence today'}, uid: S.me.id, k: 'k6339s'}]); 1`);
  check(w.eval(`OUT.q.some(x => x.k === 'k6339s')`) === true, 'D8: outStash with localStorage full: the entry is in the queue');
  br.fail = false;
  await ren(w, 3, 'Fix the fence now');
  check(await until(() => !sign(w)), 'D8: the next write landed: the sign is gone');
  const ks = w.eval('OUT.q.map(x => x.k)');
  check(ks.length >= 4 && ks.every(k => br.ops.has(k)), `D8: the whole queue is in the store (${ks.length} waiting, ${[...br.ops.keys()].filter(k => ks.includes(k)).length} kept)`);
  // kept input (fdKeep) and the conflicts with localStorage full
  w.eval(`fdKeep('fdc', 6339, {text: 'A comment draft'}); 1`);
  check(await until(() => !!sign(w)), 'D8: a kept input refused: the sign');
  w.eval(`fdDrop('fdc', 6339); 1`);
  check(await until(() => !sign(w)), 'D8: dropped again: the sign goes');
  w.eval(`LS.set('conflicts', [{tid: ${T[0]}, field: 'title', mine: 'x', theirs: 'y'}]); 1`);
  check(await until(() => !!sign(w)), 'D8: the conflicts refused: the sign');
  br.full = false;
  w.eval(`LS.set('conflicts', []); 1`);
  check(await until(() => !sign(w)), 'D8: written later: the sign goes');
  // online again: everything goes out
  w.__offline = false;
  w.dispatchEvent(new w.Event('online'));
  check(await until(() => w.eval('OUT.q.length') === 0 && br.ops.size === 0, 20000), 'sent: the queue and the store are empty');
  check((await call('GET', '/api/tasks/' + T[3])).title === 'Fix the fence now' && (await call('GET', '/api/tasks/' + T[0])).title === 'Sow the beans early', 'the changes arrived');
  w.close();

  // a write that failed put only its own entries into the feed (#7595: never the whole queue)
  {
    const b1 = browser();
    const w1 = await boot({user: 'alice', hash: 'l/' + P, shared: b1.shared, setup: b1.setup});
    w1.__offline = true;
    w1.eval(`outSave(() => OUT.q.push({method: 'PATCH', url: '/api/tasks/${T[0]}', body: {title: 'One'}, uid: S.me.id, k: 'k7595a'})); 1`);
    check(await until(() => b1.ops.has('k7595a')), '#7595 setup: one entry in the store');
    b1.fail = true;
    w1.eval(`outSave(() => OUT.q.push({method: 'PATCH', url: '/api/tasks/${T[1]}', body: {title: 'Two'}, uid: S.me.id, k: 'k7595b'})); 1`);
    check(await until(() => (lsq(b1) || []).length > 0), '#7595: the failed write went to the feed');
    check(JSON.stringify((lsq(b1) || []).map(x => x.k)) === '["k7595b"]', '#7595: only the entry of the failed write is in the feed, not the whole queue ' + JSON.stringify(lsq(b1)));
    b1.fail = false;
    w1.eval(`obxSave(() => { OUT.q = OUT.q.filter(x => !['k7595a', 'k7595b'].includes(x.k)); }); 1`);
    w1.close();
  }

  // ================= (#7595) the same entry in both places: the newer one wins (its revision r)
  {
    const ME = (await call('GET', '/api/me')).id;
    const b5 = browser();
    const e = (k, i, title, r, n) => ({k, n, r, method: 'PATCH', url: `/api/tasks/${T[i]}`, body: {title}, uid: ME});
    b5.ops.set('k7595n', e('k7595n', 0, 'Sow the beans (queue, older)', 1, 1));
    b5.ops.set('k7595o', e('k7595o', 1, 'Water the beds (queue, newer)', 3, 2));
    const feed = [e('k7595n', 0, 'Sow the beans (feed, newer)', 2, 1), e('k7595o', 1, 'Water the beds (feed, older)', 2, 2)];
    const w5 = await boot({user: 'alice', hash: 'l/' + P, shared: b5.shared, setup: b5.setup, ls: {'tasks.outbox': JSON.stringify(feed)}});
    check(await until(async () => w5.eval('OUT.q.length') === 0 && b5.ops.size === 0 && lsq(b5) === null, 20000), '#7595 both places: sent, the store and the feed are empty');
    const t0 = (await call('GET', '/api/tasks/' + T[0])).title, t1 = (await call('GET', '/api/tasks/' + T[1])).title;
    check(t0 === 'Sow the beans (feed, newer)', '#7595 both places, the feed newer: its entry is sent (was: the queue\'s older one) ' + t0);
    check(t1 === 'Water the beds (queue, newer)', '#7595 both places, the feed older: the queue\'s entry is sent ' + t1);
    w5.close();
  }

  // ================= (#7595 Zusatz 1) IndexedDB opens in no window: the window sends its feed itself, also after a reload
  const nTasks = async title => (await call('GET', '/api/state')).tasks.filter(t => t.title === title).length;
  {
    const b3 = browser(); b3.closed = true;
    let w3 = await boot({user: 'alice', hash: 'l/' + P, shared: b3.shared, setup: b3.setup});
    check(w3.eval('OBX.on') === false && w3.eval('STORE.closed') === true, 'Zusatz 1 setup: IndexedDB does not open');
    w3.__offline = true;
    await w3.eval(`createTask({title: 'Plant the tulips', list_id: ${P}}).catch(() => 0)`);
    check(await until(() => w3.eval('OUT.q.length') === 1 && (lsq(b3) || []).length === 1), 'Zusatz 1: made offline, it waits in the feed');
    w3.close();
    w3 = await boot({user: 'alice', hash: 'l/' + P, shared: b3.shared, setup: b3.setup});  // a reload, online, IndexedDB still closed
    check(await until(async () => w3.eval('OUT.q.length') === 0 && !(lsq(b3) || []).length && await nTasks('Plant the tulips') === 1, 20000), 'Zusatz 1: after the reload the window sends it, the feed is empty');
    await w3.eval('flush()');
    check(await nTasks('Plant the tulips') === 1, 'Zusatz 1: it arrived exactly once');
    w3.close();
  }
  // ... and a second window of the browser whose IndexedDB opens: it adopts the entry and sends it, the first never again
  {
    const b4 = browser();
    const shut = x => { b4.setup(x); x.__obxStore = {...b4.store, all: async () => { throw new Error('UnknownError (test): this window\'s IndexedDB does not open'); }}; };
    const w4 = await boot({user: 'alice', hash: 'l/' + P, shared: b4.shared, setup: shut});
    check(w4.eval('OBX.on') === false && w4.eval('STORE.closed') === true, 'Zusatz 1 setup: the first window\'s IndexedDB does not open');
    w4.eval(`(() => { const f = window.fetch; window.__posts = 0; window.fetch = function (u, o) { if (/\\/api\\/tasks$/.test(String(u && u.url || u)) && (o && o.method) === 'POST') window.__posts++; return f.apply(this, arguments); }; })()`);
    w4.__offline = true;
    await w4.eval(`createTask({title: 'Rake the leaves', list_id: ${P}}).catch(() => 0)`);
    check(await until(() => (lsq(b4) || []).length === 1), 'Zusatz 1: made offline in the first window, it waits in the feed');
    const w5 = await boot({user: 'alice', hash: 'l/' + P, shared: b4.shared, setup: b4.setup});
    check(w5.eval('OBX.on') === true, 'Zusatz 1 setup: the second window\'s IndexedDB opens');
    check(await until(async () => w5.eval('OUT.q.length') === 0 && !(lsq(b4) || []).length && await nTasks('Rake the leaves') === 1, 20000), 'Zusatz 1: the second window adopted it and sent it');
    const posts0 = w4.eval('window.__posts');  // its tries while offline
    w4.__offline = false;
    w4.dispatchEvent(new w4.Event('online'));
    check(await until(() => w4.eval('OUT.q.length') === 0), 'Zusatz 1: the first window counts it as sent elsewhere');
    await w4.eval('flush()');
    check(w4.eval('window.__posts') === posts0 && await nTasks('Rake the leaves') === 1, `Zusatz 1: the first window never sends it again (its POSTs online: ${w4.eval('window.__posts') - posts0}), it arrived once`);
    w4.close(); w5.close();
  }

  // ================= D10: the queue's IndexedDB would not open
  const b2 = browser(); b2.closed = true;
  const w2 = await boot({user: 'alice', hash: 'l/' + P, shared: b2.shared, setup: b2.setup});
  check(w2.eval('OBX.on') === false, 'D10 setup: the queue runs on localStorage');
  check(await until(() => !!sign(w2)), 'D10: the sign in the top bar');
  check(/earlier visit are not shown/.test(sign(w2)?.title || ''), 'D10: it says earlier waiting changes are not shown: ' + sign(w2)?.title);
  w2.close();

  console.log(`\n${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crash', e); process.exit(1); });
