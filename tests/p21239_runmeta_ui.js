// 2.1239.0 (#6261) UI test (Firefox, real layout): the model under an agent's chat answer (agentchat.js chatRunMetaHtml)
// kalmido-suite: fresh
// freelancer-matrix: agents (frida has no organisation and a personal agent; alice an organisation's agent)
// German interface. Computer (1280 x 800) and phone (390 x 844): an answer with run_meta {Fable 5.2, high} shows
// "Fable 5.2 · Effort hoch" in the line under its bubble, next to the time, small (no bigger than the time), in the muted
// colour, on the screen and inside the message; the reason is its tooltip; {Opus 5.5, klasse klein} shows "Opus 5.5 · kurz
// sortiert"; an answer without run_meta and the person's own message show no such text and their line under the bubble is as
// high as before (nothing jumps). The chat can still be scrolled and answered (the box takes text). With P21239_SHOTS: pictures.
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21239_runmeta_ui', check, shots: 'P21239_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.KMT_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

// the line under a message as the person sees it
const ROW = id => `(() => { const m = document.querySelector('#chat-msgs .cmsg[data-mid="a:${id}"]'); if (!m) return null;
  m.scrollIntoView({block: 'nearest'});
  const meta = m.querySelector(':scope > .cmeta'), run = meta?.querySelector('.crun'), t = meta?.querySelector('time');
  const rr = run?.getBoundingClientRect(), mr = m.getBoundingClientRect(), tr0 = t?.getBoundingClientRect(), br = m.querySelector('.cbub')?.getBoundingClientRect();
  const cs = run && getComputedStyle(run), ts = t && getComputedStyle(t);
  return JSON.stringify({run: run ? run.textContent : null, title: run?.title || '', time: !!t,
    on: !!rr && rr.width > 0 && rr.top >= 0 && rr.bottom <= innerHeight && rr.left >= mr.left - 1 && rr.right <= mr.right + 1,
    below: !!rr && !!br && rr.top >= br.bottom - 1, sameLine: !!rr && !!tr0 && Math.abs((rr.top + rr.bottom) / 2 - (tr0.top + tr0.bottom) / 2) < 4,
    small: !!cs && parseFloat(cs.fontSize) <= parseFloat(ts.fontSize) + 0.1, muted: !!cs && cs.color === ts.color,
    metaH: meta ? Math.round(meta.getBoundingClientRect().height) : 0}); })()`;

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'de'})});
  check(r.ok, 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {org_name: 'Example Org', lang: 'de', collab_all: true, modules: ['comments']});
  check((await call('PATCH', '/api/settings', {lang: 'de', tour: 'done', tours_more: '0'})).http < 300, 'alice: German');
  const ME = (await call('GET', '/api/state')).me, ORG = ME.workspaces[0].id;
  const ag = await call('POST', '/api/admin/agents', {scopes: ['read', 'tasks:write', 'comments'], username: 'modelbot', display_name: 'Modelbot', org_id: ORG});
  const L = (await call('POST', '/api/lists', {name: 'Models', org_id: ORG})).id;
  await call('PUT', `/api/lists/${L}/members`, {user_id: ag.id, role: 'edit'});
  const u = await call('POST', '/api/users', {username: 'frida', display_name: 'Frida', password: 'password123', email: 'frida@example.com', orgs: []});
  check(u.http === 200 || u.http === 201, 'the freelancer ' + u.http);
  const fag = await call('POST', '/api/admin/agents', {scopes: ['read', 'tasks:write', 'comments'], username: 'fridabot', display_name: 'Fridabot', owner_id: u.id});
  const ACK = CK, FCK = await login('frida');
  check((await call('PATCH', '/api/settings', {lang: 'de', tour: 'done', tours_more: '0'}, FCK)).http < 300, 'frida: German');
  const FL = (await call('POST', '/api/lists', {name: 'Meins'}, FCK)).id;
  const PEOPLE = [{who: 'frida', uid: u.id, ag: fag, ck: FCK, start: 'l/' + FL}, {who: 'alice', uid: ME.id, ag, ck: ACK, start: 'l/' + L}];
  const say = async (p, body, run_meta) => (await fetch(B + `api/v1/agent/chats/${p.uid}`, {method: 'POST', headers: {Authorization: 'Bearer ' + p.ag.token, 'Content-Type': 'application/json'},
    body: JSON.stringify({body, ...(run_meta ? {run_meta} : {})})})).json();

  for (const p of PEOPLE) {
    const mine = await call('POST', `/api/agents/${p.ag.id}/chat`, {body: 'Wie geht das?'}, p.ck);
    check(mine.id, `${p.who}: my message ` + mine.http);
    const m0 = await say(p, 'An older answer without a model.');
    const m1 = await say(p, 'A careful answer.', {model: 'Fable 5.2', effort: 'high', klasse: 'gross', grund: 'Sicherheitsbereich'});
    const m2 = await say(p, 'A short sorted answer.', {model: 'Opus 5.5', klasse: 'klein'});
    check(m1.run_meta?.model === 'Fable 5.2' && m2.run_meta?.klasse === 'klein' && m0.run_meta === null, `${p.who}: the answers carry run_meta`);
    for (const [view, w, h, mob] of [['desktop', 1280, 800, false], ['phone', 390, 844, true]]) {
      await firefox(async ({cmd, ev, ctx, nav, until, shot}) => {
        await nav(B + 'static/icon.svg');
        check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${p.who}', password: 'password123'})}).then(r => r.status)`) === 200, `${p.who} ${view}: login`);
        await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: w, height: h}});
        await nav(B + (mob ? '#agents/' + p.ag.id : '#' + p.start));
        await until(`!!document.querySelector('#view')?.children.length || !!document.querySelector('#chat-msgs')`);
        await ev(`loadModule('agentchat').then(() => { if (!document.querySelector('#chat-msgs')) chatOpen(${p.ag.id}); return 1; })`);
        const a = JSON.parse(await until(`(() => { const x = ${ROW(m1.id)}; return x && JSON.parse(x).run ? x : null; })()`) || 'null');
        check(a && a.run === 'Fable 5.2 · Effort hoch' && a.title === 'Sicherheitsbereich', `${p.who} ${view}: "Fable 5.2 · Effort hoch" under the answer, the reason as tooltip ` + JSON.stringify(a));
        check(a && a.on && a.below && a.sameLine && a.time, `${p.who} ${view}: on the screen, under the bubble, in the line of the time ` + JSON.stringify(a));
        check(a && a.small && a.muted, `${p.who} ${view}: small and grey like the time ` + JSON.stringify(a));
        const b = JSON.parse(await until(ROW(m2.id)) || 'null');
        check(b && b.run === 'Opus 5.5 · kurz sortiert' && b.on, `${p.who} ${view}: a short sorted run says "Opus 5.5 · kurz sortiert" ` + JSON.stringify(b));
        const c = JSON.parse(await until(ROW(m0.id)) || 'null'), d = JSON.parse(await until(ROW(mine.id)) || 'null');
        check(c && c.run === null && c.time, `${p.who} ${view}: an answer without run_meta shows no model ` + JSON.stringify(c));
        check(d && d.run === null, `${p.who} ${view}: my own message shows no model ` + JSON.stringify(d));
        check(a && c && Math.abs(a.metaH - c.metaH) <= 2, `${p.who} ${view}: the line under the bubble keeps its height (nothing jumps) ${a?.metaH} / ${c?.metaH}`);
        await shot(`p21239-${p.who}-${view}.png`);
        // the chat stays usable: the box takes text
        check(await until(`(() => { const t = document.querySelector('#chat-in'); if (!t) return false; t.focus(); t.value = 'Danke'; t.dispatchEvent(new Event('input', {bubbles: true})); return t.value === 'Danke'; })()`),
          `${p.who} ${view}: the answer box still takes text`);
      }, mob);
    }
  }
  const fails = F.length; console.log(`p21239_runmeta_ui: ${ok} ok, ${fails} failed`); process.exit(fails ? 1 : 0);
})().catch(e => { console.log('FAIL:', e); process.exit(1); });
