// 2.161.0 UI test, part A, own container (start.sh). Invented data only.
// jsdom:
// - #2594: "Edit organisation" (Admin > Organisation) has the own picture of Settings > Workspaces (icon buttons in the
//   symbol row, so the narrow dialog keeps its height - layout in p21382_b_ui): an admin of the
//   organisation uploads a picture (file -> crop -> POST /api/orgs/{id}/icon) and removes it again; the preview shows the
//   picture, the symbol field is emptied so Save keeps the picture, the emoji stays the fallback without a picture;
//   a server admin who is not an admin of the organisation sees a hint under the dialog instead (same routes, no new rights)
// 2.1381.0 (#6886): the symbol as tiles (first letter automatic, picture, remove), kept until Save; New organisation with a
//   picture uploads it right after creating
// P4: an organisation is managed by the server admin; a person without an organisation has no such dialog (no new route)
const {execFileSync} = require('child_process');
const path = require('path');
const zlib = require('zlib');
const {boot, sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P2161A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); j.http = r.status; return j; };
const until = (fn, n) => require('./boot').until(fn, {timeout: n ? n * 150 : 15000, step: 150});  // 2.358.0 (#3286): the shared wait of tests/boot.js (default at least 15 s); an explicit n/ms keeps its window
const typeIn = (w, el, v) => { if (!el) return; el.value = v; el.dispatchEvent(new w.Event('input', {bubbles: true})); };
// a real 16x16 PNG (one colour), invented
const png = (() => {
  const crcT = Array.from({length: 256}, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = b => { let c = 0xffffffff; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const ih = Buffer.alloc(13); ih.writeUInt32BE(16, 0); ih.writeUInt32BE(16, 4); ih[8] = 8; ih[9] = 2;
  const raw = Buffer.concat(Array.from({length: 16}, () => Buffer.concat([Buffer.from([0]), Buffer.from(Array(16).fill([120, 80, 200]).flat())])));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
})();

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal', 'comments']});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,comments,collab'});
  const me = (await call('GET', '/api/state')).me.id;
  const BOB = await call('POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com'}).then(j => j.id);
  const ORG = (await call('POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me})).id;
  const p0 = await call('PATCH', `/api/admin/orgs/${ORG}`, {members: [me, BOB], admins: [me], icon: '⭐'});
  check(p0.http === 200, 'org prepared ' + p0.http);
  const OTHER = (await call('POST', '/api/admin/orgs', {name: 'Beta', admin_id: BOB})).id;
  await call('PATCH', `/api/admin/orgs/${OTHER}`, {members: [BOB], admins: [BOB]});
  const orgOf = async (id = ORG) => ((await call('GET', '/api/admin/orgs')).orgs || []).find(o => o.id === id);

  const w = await boot({user: 'alice', hash: 'inbox'}), d = w.document;
  await until(() => w.eval(`typeof orgModal === 'function'`), 40);
  // the file picker and the crop dialog are the browser's / tested in #1913: a chosen file comes back as a cropped PNG;
  // jsdom's FormData does not reach the server through the test bridge, so the upload is sent from Node with the same body
  let posted = 0;
  w.eval(`avCropModal = async () => new Blob([new Uint8Array(4)], {type: 'image/png'})`);
  // 2.1381.0 (#6886): the dialog previews the cropped picture through an object URL (jsdom has none)
  let objN = 0; w.URL.createObjectURL = () => `blob:${B}p2161/${++objN}`; w.URL.revokeObjectURL = () => {};
  w.HTMLInputElement.prototype.click = function () { if (this.type === 'file') { Object.defineProperty(this, 'files', {configurable: true, value: [{size: 4, name: 'x.png'}]}); this.dispatchEvent(new w.Event('change')); } };
  const f0 = w.fetch;
  w.fetch = (u, o = {}) => {
    if (o.method === 'POST' && /\/api\/orgs\/\d+\/icon$/.test(String(u))) {
      posted++;
      const fd = new FormData(); fd.append('file', new Blob([png], {type: 'image/png'}), 'icon.png');
      return fetch(new URL(String(u), B), {method: 'POST', headers: {'X-Requested-With': 'kalmido', Cookie: CK}, body: fd});
    }
    return f0(u, o);
  };
  const open = async id => { d.querySelectorAll('.modal.ogmodal').forEach(x => x.remove()); await w.eval(`S.orgs = []; orgModal({id: ${id}}, () => {})`); return until(() => d.querySelector('.modal.ogmodal'), 40); };

  // 2.1381.0 (#6886): the symbol is a tile picker (picTilesHtml, as the project icon) instead of a text field and the icon
  // buttons: first letter (automatic), a symbol typed before as a tile, upload, remove - all kept until Save
  const sav = async () => { md.querySelector('[data-m="save"]').click(); await until(() => !d.querySelector('.modal.ogmodal'), 40); };
  const T = k => md.querySelector(`#og-pic [data-ogsym="${k}"]`);
  // ================= an admin of the organisation: upload, preview, Save keeps it, remove, letter fallback
  let md = await open(ORG);
  check(!!md, '#2594: the dialog opens');
  check(!md.querySelector('#og-icon'), '#6886: no symbol text field any more');
  check(T('upload') && T('auto') && T('text')?.getAttribute('aria-pressed') === 'true' && T('none'), '#6886: tiles: letter, the old emoji (chosen), upload, remove');
  check(/Upload a picture/.test(T('upload')?.title || '') && T('upload')?.previousElementSibling?.matches('input[type="file"][data-fpass]'), '#6886: upload tile with its fixed file input (title = text)');
  check(/⭐/.test(md.querySelector('#og-icprev')?.textContent || ''), '#6886: the preview shows the emoji');
  T('upload').click();
  check(await until(() => md.querySelector('#og-icprev img[src^="blob:"]'), 40), '#6886: the preview shows the chosen picture at once');
  check(T('upload')?.getAttribute('aria-pressed') === 'true' && T('upload')?.querySelector('img'), '#6886: the upload tile is chosen and shows the picture');
  check(posted === 0, '#6886: nothing uploaded before Save ' + posted);
  await sav();
  check(await until(async () => (await orgOf())?.icon_url, 40), '#2594: Save uploads the picture');
  check(posted === 1, '#2594: one upload to /api/orgs/{id}/icon ' + posted);
  let o = await orgOf();
  check(o?.icon_url && !o.icon, '#2594: the organisation has the picture, no emoji ' + JSON.stringify(o && {icon: o.icon, u: !!o.icon_url}));
  // reopened: the picture is chosen; Cancel after Remove keeps it; Remove + Save = the letter
  md = await open(ORG);
  check(md.querySelector('#og-icprev img[src*="/api/org-icon/"]') && T('none') && !T('text'), '#2594: reopened with the picture and the remove tile');
  T('none').click();
  check(md.querySelector('#og-icprev')?.textContent === 'A' && T('auto')?.getAttribute('aria-pressed') === 'true' && !T('none'), '#6886: remove -> the preview is the first letter at once');
  md.querySelector('[data-m="close"]').click(); await sleep(300);
  check((await orgOf())?.icon_url, '#6886: Cancel keeps the picture');
  md = await open(ORG);
  T('none').click();
  await sav();
  o = await until(async () => { const x = await orgOf(); return x && !x.icon_url ? x : null; }, 40);
  check(o && !o.icon_url && !o.icon, '#2594: the picture is removed ' + JSON.stringify(o && {icon: o.icon, u: !!o.icon_url}));
  md = await open(ORG);
  check(md.querySelector('#og-icprev')?.textContent === 'A' && !md.querySelector('#og-icprev img') && !T('text'), '#6886: reopened: the letter (automatic), no emoji tile');
  md.querySelector('[data-m="close"]').click(); await sleep(300);

  // ================= a server admin who does not administer the organisation: no upload tile, a hint (the routes stay as they are)
  md = await open(OTHER);
  check(md && !T('upload') && T('auto') && /Only an admin of the organisation can upload a picture/.test(md.querySelector('#og-pich')?.textContent || ''), '#2594: not an admin of the organisation: hint instead of the upload');
  const deny = await fetch(B + `api/orgs/${OTHER}/icon`, {method: 'DELETE', headers: {...H, Cookie: CK}});
  check(deny.status === 404 || deny.status === 403, '#2594: the route still refuses a non-member ' + deny.status);

  // ================= #6886: "New organisation" with a picture: uploaded right after creating, visible in the list
  d.querySelectorAll('.modal.ogmodal').forEach(x => x.remove());
  await w.eval(`orgModal(null, () => {})`);
  md = await until(() => d.querySelector('.modal.ogmodal'), 40);
  check(md && T('auto') && T('upload') && !md.querySelector('#og-pich'), '#6886: "New organisation" has the tiles with upload');
  typeIn(w, md.querySelector('#og-name'), 'Gamma');
  check(md.querySelector('#og-icprev')?.textContent === 'G' && T('auto')?.textContent === 'G', '#6886: the letter follows the typed name');
  T('upload').click();
  check(await until(() => md.querySelector('#og-icprev img[src^="blob:"]'), 40), '#6886: the preview shows the picture before creating');
  await sav();
  const g = await until(async () => { const x = ((await call('GET', '/api/admin/orgs')).orgs || []).find(y => y.name === 'Gamma'); return x?.icon_url ? x : null; }, 40);
  check(g?.icon_url && posted === 2, '#6886: the new organisation has its picture right after creating ' + JSON.stringify(g && {u: g.icon_url, posted}));
  check(g && (g.admins || []).includes(me), '#6886: the creator is its admin (who may upload)');
  const pic = g && await fetch(new URL(g.icon_url, B), {headers: {Cookie: CK}});
  check(pic?.ok && /image\/png/.test(pic.headers.get('content-type') || ''), '#6886: the picture can be loaded ' + pic?.status);
  // visible in the app: the workspace symbol of the new organisation is the picture (the creator is a member)
  check(g && await until(() => w.eval(`/<img class="orgic"/.test(wsIcon('org:${g.id}'))`), 40), '#6886: the workspace symbol shows the picture after creating');

  console.log(`p2161_a_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
