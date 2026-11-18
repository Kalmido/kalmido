// 2.1384.0 (#6339 D10): a module on demand that failed during the worker's install is not left out of the cache until the next
// worker version: its next fetch through the worker (swShell) takes it from the network and keeps it, so it is there offline after.
// kalmido-suite: nodata
// No browser, no server: static/sw.js runs in a vm with a fake network and fake caches (like p21313_b_sw_lazy_test.js).
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const SRC = process.env.KALMIDO_SRC || path.join(__dirname, '..');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const HASH = 'abcdef012345';

class Response {
  constructor(body, init = {}) { this.body = body; this.ok = true; this.status = 200; this.redirected = false; this.type = 'basic'; this.headers = new Map(Object.entries(init.headers || {})); this.headers.get = k => Map.prototype.get.call(this.headers, k.toLowerCase()) || null; }
  clone() { return new Response(this.body, {headers: Object.fromEntries(this.headers)}); }
  async json() { return JSON.parse(this.body); }
}

(async () => {
  const SW = fs.readFileSync(path.join(SRC, 'static', 'sw.js'), 'utf8');
  const kept = new Map();  // url with query -> body, one cache (this worker's)
  let fail = '', offline = false;
  const fetchUrl = async u => {
    const url = String(u.url || u).replace(/^https:\/\/kalmido\.example/, '');
    if (url.startsWith('/sw-manifest.json')) {
      const files = {}; for (const f of ctx.ALL) files[f] = HASH;
      return new Response(JSON.stringify({v: 1, version: '9.9.9', files, i18n: []}), {headers: {'content-type': 'application/json'}});
    }
    if (offline || (fail && url.split('?')[0] === fail)) throw new TypeError('network error');
    return new Response('x', {headers: {'cache-control': 'public, max-age=31536000, immutable'}});
  };
  const key = k => String(k.url || k).replace(/^https:\/\/kalmido\.example/, '');
  const cache = {put: async (k, r) => { kept.set(key(k), r); }, add: async u => { kept.set(key(u), await fetchUrl(u)); },
    addAll: async us => { for (const u of us) await cache.add(u); }, keys: async () => [], match: async k => kept.get(key(k)), delete: async () => true};
  var ctx = vm.createContext({
    self: {addEventListener() {}, location: {origin: 'https://kalmido.example'}, navigator: {}},
    caches: {open: async () => cache, keys: async () => [], match: async k => kept.get(key(k))},
    fetch: fetchUrl, Response, URL, Headers: Map, setTimeout, clearTimeout, console, JSON, Date, Set, Map, Promise, Array, Object,
  });
  vm.runInContext(SW, ctx);
  ctx.ALL = vm.runInContext('SHELL.concat(LAZY, LAZY_CSS)', ctx);
  const bad = vm.runInContext('LAZY', ctx)[5];
  fail = bad;
  await vm.runInContext('swInstall()', ctx);
  const u = `${bad}?v=${HASH}`;
  check(!kept.has(u), 'setup: the module failed during the install, it is not in the cache');
  fail = '';
  ctx.__u = new URL('https://kalmido.example' + u);
  const r = await vm.runInContext('swShell(__u.href, __u)', ctx);
  check(r && r.ok, 'its next fetch through the worker answers');
  for (let i = 0; i < 50 && !kept.has(u); i++) await new Promise(ok => setTimeout(ok, 10));
  check(kept.has(u), 'and keeps it in the cache (no wait for the next worker version)');
  offline = true;
  const r2 = await vm.runInContext('swShell(__u.href, __u)', ctx).catch(() => null);
  check(r2 && r2.ok, 'offline afterwards: it comes from the cache');

  console.log(`p21384_b_sw_lazy_test: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
