// kalmido-suite:
// UI test (#7525, cause 1): the own person page (#who/<me>, titled "My tasks") as a favourite draws its tile.
// Own container (start.sh), jsdom. Invented data only.
// - before: fv2_tile looked persons up in teamPeople() only, which leaves the own account out: the star on #who/<me> stored
//   p:<me> (PATCH 200) but no tile was ever drawn - "Added to favourites" showed and the favourite was gone
// - now: the own account counts; the tile is labelled "My tasks", its avatar carries the own name; a click opens #who/<me>;
//   after a reload the tile and the star are still there; the star takes it out again
// P4: frida has no organisation and gets the same (freelancer-matrix: tasks)
const path = require('path');
const {execFileSync} = require('child_process');
const {boot, sleep, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P7525A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const items = async ck => JSON.parse((await call(ck, 'GET', '/api/state')).settings.fav_items || '[]');
const u2 = (fn, timeout = 8000) => until(fn, {timeout}).catch(() => null);

(async () => {
  await sleep(600);
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice Archer', password: 'password123'})});
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['cal']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const ORG = (await call(CA, 'GET', '/api/state')).me.workspaces?.[0]?.id;
  const BOB = (await call(CA, 'POST', '/api/users', {orgs: ORG ? [ORG] : [], username: 'bob', display_name: 'Bob Builder', password: 'password123', email: 'bob@example.com'})).id;
  await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida Free', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'frida: no organisation');

  for (const [u, ck, name] of [['alice', CA, 'Alice Archer'], ['frida', CF, 'Frida Free']]) {
    const me = (await call(ck, 'GET', '/api/state')).me.id;
    const L = await call(ck, 'POST', '/api/lists', {name: 'Shoot Berlin', ...(u === 'alice' && ORG ? {org_id: ORG} : {})});
    if (u === 'alice') await call(ck, 'PUT', `/api/lists/${L.id}/members`, {user_id: BOB, role: 'edit'});
    await call(ck, 'POST', '/api/tasks', {title: 'Book the van', list_id: L.id, assignee_id: me});
    await call(ck, 'PATCH', '/api/settings', {fav_items: []});
    const key = 'p:' + me;

    let w = await boot({user: u, hash: 'who/' + me}), d = w.document;
    check(await u2(() => w.eval(`fv2_routeKey()`) === key), `${u}: the own person page can be a favourite (${key}) ` + w.eval('fv2_routeKey()'));
    const star = await u2(() => d.querySelector(`[data-fv2-star="${key}"]`));
    check(!!star && star.getAttribute('aria-pressed') === 'false', `${u}: #who/<me> has the star, not set`);
    if (star) click(w, star);
    check(await u2(async () => (await items(ck)).includes(key)), `${u}: p:<me> is stored ` + JSON.stringify(await items(ck)));
    const tile = await u2(() => w.eval(`fv2_tiles().find(t => t.key === ${JSON.stringify(key)})`) || null);
    check(!!tile, `${u}: the tile of the own person page is drawn (the cause: teamPeople() leaves the own account out) ` + JSON.stringify(w.eval('fv2_tiles().map(t => t.key)')));
    check(tile?.name === 'My tasks', `${u}: the tile says "My tasks" ` + tile?.name);
    check(String(tile?.icon || '').includes(name.split(' ')[0][0]), `${u}: the avatar carries the own name's initial ` + tile?.icon);
    check(await u2(() => d.querySelector(`[data-fv2-star="${key}"]`)?.getAttribute('aria-pressed') === 'true'), `${u}: the star stays on`);
    w.close();

    // after a reload on another page: the tile is there and opens the own person page
    w = await boot({user: u, hash: 'today'}); d = w.document;
    const el = await u2(() => d.querySelector(`[data-fv2="${key}"]`));
    check(!!el, `${u}: after a reload the tile ${key} is in the row of favourites`);
    if (el) { click(w, el); check(await u2(() => w.location.hash === '#who/' + me), `${u}: the tile opens #who/<me> ` + w.location.hash); }
    // and back out: the star takes it away
    const off = await u2(() => d.querySelector(`[data-fv2-star="${key}"]`));
    if (off) click(w, off);
    check(await u2(async () => !(await items(ck)).includes(key)), `${u}: the star takes the favourite out again`);
    w.close();
  }

  console.log(`p7525_a_fav_me_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('ERR', e); process.exit(1); });
