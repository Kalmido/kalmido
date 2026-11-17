// 2.1313.0 (#6367): the first start no longer fetches every module on demand at once (static/sw.js swInstall, static/js/main.js)
// kalmido-suite: nodata
// No browser, no server: static/sw.js runs in a vm with a fake network and fake caches.
// - the modules on demand (LAZY + LAZY_CSS) come at most 6 at a time (red before: all ~240 in one go), every one of them lands
//   in the cache, with and without the server's manifest; one failing module fails nothing else
// - data saver / 2g: no module on demand from the network (they come on first use), an unchanged copy of an old cache is kept;
//   the shell still comes whole
// - main.js signs the worker up only once the app stands (requestIdleCallback with a 5 s limit, else after 5 s)
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const SRC = process.env.KALMIDO_SRC || path.join(__dirname, '..');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const HASH = 'abcdef012345';

class Response { constructor(body, init = {}) { this.body = body; this.ok = true; this.status = 200; this.redirected = false; this.type = 'basic'; this.headers = new Map(Object.entries(init.headers || {})); this.headers.get = k => Map.prototype.get.call(this.headers, k.toLowerCase()) || null; } async json() { return JSON.parse(this.body); } }

async function install({manifest = true, conn = null, old = [], fail = ''} = {}) {
  const SW = fs.readFileSync(path.join(SRC, 'static', 'sw.js'), 'utf8');
  let now = 0, peak = 0;
  const net = [], kept = new Set(), lazy = new Set();
  const fetchUrl = async u => {
    const url = String(u).replace(/^https:\/\/kalmido\.example/, '');
    if (url.startsWith('/sw-manifest.json')) {
      if (!manifest) return Object.assign(new Response('', {}), {ok: false, status: 404});
      const files = {}; for (const f of ctx.ALL) files[f] = HASH;
      return new Response(JSON.stringify({v: 1, version: '9.9.9', files, i18n: []}), {headers: {'content-type': 'application/json'}});
    }
    const base = url.split('?')[0], isLazy = lazy.has(base);
    net.push(base);
    if (isLazy) { now++; peak = Math.max(peak, now); }
    await new Promise(r => setTimeout(r, 2));
    if (isLazy) now--;
    if (fail && base === fail) throw new TypeError('network error');
    return new Response('x', {headers: {'cache-control': 'public, max-age=31536000, immutable'}});
  };
  const cache = {put: async k => { kept.add(String(k.url || k).split('?')[0]); }, add: async u => { await fetchUrl(u); kept.add(u); },
    addAll: async us => { await Promise.all(us.map(u => cache.add(u))); }, keys: async () => [], match: async () => undefined, delete: async () => true};
  const oldSet = new Set(old);
  var ctx = vm.createContext({
    self: {addEventListener() {}, location: {origin: 'https://kalmido.example'}, navigator: conn ? {connection: conn} : {}},
    caches: {open: async () => cache, keys: async () => [], match: async k => oldSet.has(String(k).split('?')[0]) ? new Response('old') : undefined},
    fetch: fetchUrl, Response, URL, Headers: Map, setTimeout, clearTimeout, console, JSON, Date, Set, Map, Promise, Array, Object,
  });
  vm.runInContext(SW, ctx);
  ctx.ALL = vm.runInContext('SHELL.concat(LAZY, LAZY_CSS)', ctx);
  for (const u of vm.runInContext('LAZY.concat(LAZY_CSS)', ctx)) lazy.add(u);
  await vm.runInContext('swInstall()', ctx);
  const shell = vm.runInContext('SHELL', ctx);
  return {peak, net, kept, lazy: [...lazy], shell};
}

(async () => {
  let r = await install();
  check(r.lazy.length > 100, `the list of modules on demand is there (${r.lazy.length})`);
  check(r.peak > 0 && r.peak <= 6, `with the manifest: at most 6 modules on demand at a time (peak ${r.peak})`);
  check(r.lazy.every(u => r.kept.has(u)), 'with the manifest: every module on demand lands in the cache');
  check(r.shell.every(u => r.kept.has(u)), 'with the manifest: the whole shell lands in the cache');

  r = await install({manifest: false});
  check(r.peak > 0 && r.peak <= 6, `without the manifest: at most 6 at a time (peak ${r.peak})`);
  check(r.lazy.every(u => r.kept.has(u)), 'without the manifest: every module on demand lands in the cache');

  const bad = (await install()).lazy[3];
  r = await install({fail: bad});
  check(!r.kept.has(bad) && r.lazy.filter(u => u !== bad).every(u => r.kept.has(u)), 'one failing module on demand fails nothing else');

  for (const conn of [{saveData: true}, {effectiveType: 'slow-2g'}, {effectiveType: '2g'}]) {
    const keep = (await install()).lazy.slice(0, 2);
    r = await install({conn, old: keep});
    const lz = new Set(r.lazy);
    check(!r.net.some(u => lz.has(u)), `${JSON.stringify(conn)}: no module on demand from the network (${r.net.filter(u => lz.has(u)).length})`);
    check(keep.every(u => r.kept.has(u)), `${JSON.stringify(conn)}: an unchanged copy of an old cache is kept`);
    check(r.shell.every(u => r.kept.has(u)), `${JSON.stringify(conn)}: the shell still comes whole`);
    r = await install({conn, manifest: false});
    check(!r.net.some(u => lz.has(u)), `${JSON.stringify(conn)} without the manifest: no module on demand from the network`);
  }
  r = await install({conn: {effectiveType: '4g', saveData: false}});
  check(r.lazy.every(u => r.kept.has(u)), '4g without the data saver: every module on demand as usual');

  const main = fs.readFileSync(path.join(SRC, 'static', 'js', 'main.js'), 'utf8');
  check(!/navigator\.serviceWorker\.register\('\/sw\.js'\)\.catch\(\(\) => \{\}\);\n\s*navigator\.serviceWorker\.addEventListener/.test(main), 'main.js: the worker no longer signs up right at the start');
  check(/window\.requestIdleCallback\(swReg, \{timeout: 5000\}\); else setTimeout\(swReg, 5000\)/.test(main), 'main.js: the worker signs up when idle, at the latest after 5 s');

  console.log(`p21313_b_sw_lazy_test: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
