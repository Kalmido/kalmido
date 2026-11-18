// 2.1392.0 (#6330) UI test (jsdom), fresh DB: a knowledge page that reloads while one starts typing keeps the base one
// writes on, so the other device's text is never overwritten without the conflict dialog (a person without an organisation)
// freelancer-matrix: wiki
// - the page is open; another device saves it; the reload of the page starts (GET held back), typing begins before its
//   answer: the answer does not replace updated_at / body of the page being written on (WK.pg keeps the old base)
// - the save then gets the server's 409: the dialog "Changed in the meantime" opens, the server still has the other
//   device's text until one decides ("Take theirs": theirs stays, also on the server)
// - without typing, the same reload takes the new base (updated_at and text of the other device)
// kalmido-suite: fresh
const {boot, errs, B, login, until} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {status: r.status, ...(await r.json().catch(() => ({})))}; };

(async () => {
  await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  CK = await login('alice');
  await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  const CF = await login('frida');
  const stf = await call('GET', '/api/state', null, CF);
  check(!(stf.me.workspaces || []).length, 'setup: frida has no organisation');
  const feats = [...new Set([...(stf.settings.features || '').split(',').filter(Boolean), 'wiki'])].join(',');
  await call('PATCH', '/api/settings', {look: '{"wkEd":"text"}', tour: 'done', lang: 'en', features: feats}, CF);
  const W1 = (await call('POST', '/api/wiki/pages', {space: 'private', path: 'Notes/Plan', body: 'Old plan'}, CF)).id;
  check(W1, 'setup: a page');
  const w = await boot({user: 'frida', hash: 'wiki/' + W1, ls: {'tasks.wkSpace': JSON.stringify('private')}});
  check(await until(() => w.eval(`WK.pg?.id === ${W1} && WK.pg.body === 'Old plan'`) && w.document.querySelector('#wk-body'), {timeout: 20000}), 'setup: the page is open for writing');
  const base = w.eval('WK.pg.updated_at');
  w.__dialogs = 'manual';  // the conflict dialog is answered by the test (boot.js would confirm it)

  // the GET of the page waits until the test lets it go (the answer arrives after typing began)
  let hold = null, release = null;
  const of = w.fetch, sent = [];
  w.fetch = (u, o = {}) => {
    const m = (o.method || 'GET').toUpperCase(), p = new URL(String(u), B).pathname;
    if (p.startsWith('/api/wiki/')) sent.push(m + ' ' + p + ' ' + String(o.body || '').slice(0, 120));
    if (hold && m === 'GET' && p === '/api/wiki/pages/' + W1) { const r = of(u, o); return hold.then(() => r); }
    return of(u, o);
  };
  const held = () => { hold = new Promise(r => { release = r; }); };

  // ================= typing begins while the page reloads
  // updated_at counts whole seconds: the other device saves once the clock is past the base's second (a later updated_at)
  const past = t => until(() => Math.floor(Date.now() / 1000) > Math.floor(Date.parse(t) / 1000), {timeout: 5000});
  await past(base);
  const other = await call('PATCH', '/api/wiki/pages/' + W1, {body: 'Plan of the phone'}, CF);
  check(other.status === 200 && other.updated_at && other.updated_at !== base, 'setup: the other device saved ' + JSON.stringify(other).slice(0, 200));
  held();
  const loading = w.eval(`wk_loadPage(${W1}, true)`);
  const ta = w.document.querySelector('#wk-body');
  ta.focus();
  ta.value = 'Plan of the laptop'; ta.dispatchEvent(new w.Event('input', {bubbles: true}));
  check(w.eval('WK.dirty') === true, 'setup: typed (dirty)');
  release(); hold = null;
  await loading;
  check(w.eval('WK.pg.updated_at') === base, `#6330: the reload keeps the base being written on (updated_at ${w.eval('WK.pg.updated_at')} vs ${base})`);
  check(w.eval('WK.pg.body') === 'Old plan', '#6330: ... and its text ' + w.eval('WK.pg.body'));
  check(w.document.querySelector('#wk-body')?.value === 'Plan of the laptop', '#6330: the typed text stays in the editor');

  // ================= the save gets its 409: the dialog, nothing overwritten without it
  const flushing = w.eval('wk_flush()');
  const md = await until(() => [...w.document.querySelectorAll('.modal')].find(x => /Changed in the meantime/.test(x.textContent)), {timeout: 10000});
  const now = await call('GET', '/api/wiki/pages/' + W1, null, CF);
  check(!!md, '#6330: the conflict dialog opens ("Changed in the meantime") ' + JSON.stringify(sent) + ' ' + [...w.document.querySelectorAll('.modal')].map(x => x.textContent.slice(0, 80)).join(' | '));
  check(now.body === 'Plan of the phone', '#6330: the server still has the other device\'s text ' + now.body);
  md?.querySelector('[data-cd="no"]')?.click();  // "Take theirs"
  await flushing;
  check(await until(() => w.eval('WK.pg.body') === 'Plan of the phone'), '#6330: "Take theirs": the page shows the other device\'s text');
  check((await call('GET', '/api/wiki/pages/' + W1, null, CF)).body === 'Plan of the phone', '#6330: ... and the server keeps it');
  // 2.1397.0 (#6329 E6): "Take theirs" after an online 409 does not drop the own text: it waits at the page (kept input 'fdx')
  const XK = `tasks.fdx.${stf.me.id}.${W1}`, xb = () => { try { return JSON.parse(w.__store[XK] || 'null')?.b; } catch { return null; } };
  check(await until(() => xb()?.mine === 'Plan of the laptop'), '#6329 E6: "Take theirs": my text waits at the page as kept input (rollback test) ' + JSON.stringify(xb()));
  if (!w.document.querySelector('#view .wkocf')) w.eval('renderView(); 1');
  const bar = await until(() => w.document.querySelector('#view .wkocf'));
  check(bar && /Changed in the meantime/.test(bar.textContent) && bar.querySelector('[data-wk="cfshow"]'), '#6329 E6: the page shows it with Compare ' + (bar?.textContent || ''));
  // Compare -> "Take theirs" again is the explicit choice: the waiting text goes
  bar?.querySelector('[data-wk="cfshow"]')?.click();
  const md2 = await until(() => [...w.document.querySelectorAll('.modal.cdlg')].find(x => /Changed in the meantime/.test(x.textContent)), {timeout: 10000});
  check(md2 && md2.textContent.includes('Plan of the laptop'), '#6329 E6: Compare shows my waiting text');
  md2?.querySelector('[data-cd="no"]')?.click();
  check(await until(() => !w.__store[XK] && !w.eval(`WKO.cf[${W1}]`)), '#6329 E6: "Take theirs" in Compare drops the waiting text');
  w.eval('WK.dirty = false; 1');

  // ================= without typing the reload takes the new base
  w.document.activeElement?.blur?.();
  w.eval('WK.dirty = false; 1');
  await past(w.eval('WK.pg.updated_at'));
  const third = await call('PATCH', '/api/wiki/pages/' + W1, {body: 'Plan of the tablet'}, CF);
  check(third.status === 200, 'setup: a third save');
  await w.eval(`wk_loadPage(${W1}, true)`);
  check(w.eval('WK.pg.updated_at') === third.updated_at && w.eval('WK.pg.body') === 'Plan of the tablet', '#6330: not typing: the reload takes the new base ' + w.eval('WK.pg.updated_at'));
  w.close();

  check(errs.length === 0, 'no script errors: ' + errs.join(' | '));
  console.log(`p21392_6330_wiki_base_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
