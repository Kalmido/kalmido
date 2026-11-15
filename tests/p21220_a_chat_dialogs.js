// 2.1220.0 UI test part A (#6101: the channel dialogs on the shared askDialog; #6104: the conversation list in sections), own container
// kalmido-suite: fresh
// Firefox as a touch screen in phone width 360 px. An organisation with a project shared with Bob and a direct message:
// the list shows the sections "Projects" and "Direct messages" with the right rows (no line about Private in the organisation);
// New channel without a name: the error stands at the field, the dialog stays; with a name the channel is created, opens and is
// in the list. Its settings: one primary button "Done" (no Save next to the name, no Cancel), "(you)" at my row, Leave and
// Archive as quiet links apart from Done (Archive in another colour), the remove x at least 44 px; an empty name + Done =
// error at the field; a new name + Done saves and closes. Browse channels: joining a channel archived meanwhile keeps the
// dialog with the reason, joining an open one opens it and closes the dialog. The workspace Private: one line says why groups
// and direct messages stand there. The same list and New channel as a person without an organisation (two freelancers).
// Invented data only.
// freelancer-matrix: team - no new route, the client of /api/team, /api/team/channels and /api/team/rooms (checked for freelancers below)
const {execFileSync} = require('child_process');
const path = require('path');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21220_a_chat_dialogs', check, shots: 'P21220A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21220A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore', env: {...process.env, EXTRA: (process.env.EXTRA || '') + ' -e KALMIDO_INSTANCE_MODE=workspaces'}});
const dbx = (sql, args = []) => JSON.parse(execFileSync('python3', [path.join(__dirname, 'dbx.py'), DATA, sql, JSON.stringify(args)]).toString() || '[]');
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };
const FEAT = 'collab,comments';
const roomOf = async (ck, lid) => ((await call(ck, 'GET', '/api/team')).rooms || []).find(x => x.kind === 'list' && x.list_id === lid) || {};

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const me = (await call(CA, 'GET', '/api/state')).me;
  const org = await call(CA, 'POST', '/api/admin/orgs', {name: 'Alpha', admin_id: me.id});
  await call(CA, 'PATCH', '/api/settings', {workspace: `org:${org.id}`});
  await call(CA, 'POST', '/api/users', {username: 'bob', display_name: 'Bob Member', password: 'password123', email: 'bob@example.com'});
  await call(CA, 'PUT', `/api/orgs/${org.id}/members`, {email: 'bob@example.com', role: 'member'});
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT, workspace: `org:${org.id}`});
  const bob = (await call(CB, 'GET', '/api/state')).me;
  // a project shared with bob (its room with a message) and a direct message
  const lst = await call(CA, 'POST', '/api/lists', {name: 'Shoot plan', org_id: org.id, kind: 'project'});
  check((await call(CA, 'PUT', `/api/lists/${lst.id}/members`, {user_id: bob.id, role: 'edit'})).http < 300, 'setup: the project shared with bob');
  const pr = await roomOf(CA, lst.id);
  check(pr.id > 0 && (await call(CB, 'POST', `/api/team/rooms/${pr.id}/messages`, {body: 'Call sheet is up'})).id > 0, 'setup: a message in the project room');
  const dm = await call(CA, 'POST', '/api/team/dm', {user_id: bob.id});
  check(dm.id > 0 && (await call(CB, 'POST', `/api/team/rooms/${dm.id}/messages`, {body: 'Hi Alice'})).id > 0, 'setup: a direct message ' + JSON.stringify(dm).slice(0, 160));
  // channels of bob for Browse: one stays open, one gets archived while the dialog is open
  const lobby = await call(CB, 'POST', '/api/team/channels', {name: 'Lobby', org_id: org.id, open: true, members: []});
  const gone = await call(CB, 'POST', '/api/team/channels', {name: 'Gone soon', org_id: org.id, open: true, members: []});
  check(lobby.id > 0 && gone.id > 0, 'setup: two open channels of bob');

  // two freelancers who work together (a shared project, a direct message)
  for (const n of ['frida', 'fiona']) { const u = await call(CA, 'POST', '/api/users', {username: n, display_name: n[0].toUpperCase() + n.slice(1), password: 'password123', email: `${n}@example.com`, orgs: []}); check(u.id > 0, `freelancer setup: ${n} created ` + JSON.stringify(u).slice(0, 200)); }
  const CF = await login('frida'), CI = await login('fiona');
  for (const ck of [CF, CI]) await call(ck, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const fr = (await call(CF, 'GET', '/api/state')).me, fi = (await call(CI, 'GET', '/api/state')).me;
  check(fr && fi && fr.id > 0 && fi.id > 0 && !(fr.workspaces || []).length && !(fi.workspaces || []).length, 'frida and fiona have no organisation ' + JSON.stringify([fr && fr.id, fi && fi.id]));
  // they work together through a group of the instance (as tests/p2281_a_teamchat_test.py): then they may share and write
  // (an admin of the mode workspaces does not see people outside its organisations - the row straight into the database)
  dbx('INSERT INTO groups(name,oidc_group,created_at,created_by) VALUES(?,?,?,?)', ['Freelance pool', '', '2026-11-14T08:00:00', me.id]);
  const gid = dbx('SELECT id FROM groups WHERE name=?', ['Freelance pool'])[0]?.id;
  for (const x of [fr.id, fi.id]) dbx('INSERT INTO group_members(group_id,user_id,added_at) VALUES(?,?,?)', [gid, x, '2026-11-14T08:00:00']);
  check(gid > 0, 'freelancer setup: an instance group of the two');
  const fl = await call(CF, 'POST', '/api/lists', {name: 'Short film', kind: 'project'});
  const sh = await call(CF, 'PUT', `/api/lists/${fl.id}/members`, {user_id: fi.id, role: 'edit'});
  check(sh.http < 300, 'freelancer setup: the project shared with fiona ' + JSON.stringify(sh).slice(0, 160));
  const fpr = await roomOf(CF, fl.id);
  check(fpr.id > 0 && (await call(CI, 'POST', `/api/team/rooms/${fpr.id}/messages`, {body: 'Edit is done'})).id > 0, 'freelancer setup: a message in the project room');
  const fdm = await call(CF, 'POST', '/api/team/dm', {user_id: fi.id});
  check(fdm.id > 0 && (await call(CI, 'POST', `/api/team/rooms/${fdm.id}/messages`, {body: 'Coffee?'})).id > 0, 'freelancer setup: a direct message ' + JSON.stringify(fdm).slice(0, 160));

  await firefox(async ({cmd, ev, nav: go, ctx, shot, until: wait}) => {
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 360, height: 760}});
    const signIn = async u => {
      await go(B + 'static/icon.svg');
      await ev(`(() => { localStorage.clear(); return 1; })()`);
      check(await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: '${u}', password: 'password123'})}).then(r => r.status)`) === 200, `Firefox: login ${u}`);
    };
    // the list as it reads: '#Heading' for a section, the room id for a row
    const LIST = `[...document.querySelectorAll('.tclist .tcsec, .tclist .tcrow')].map(e => e.classList.contains('tcsec') ? '#' + e.textContent.trim() : e.dataset.rid)`;
    const listOk = async (tag, proj, dmr) => {
      check(await wait(`!!document.querySelector('.tclist .tcrow[data-rid="${proj}"]') && !!document.querySelector('.tclist .tcrow[data-rid="${dmr}"]')`, {timeout: 20000}), `${tag}: the list with the project and the direct message`);
      const l = await ev(LIST);
      const pi = l.indexOf('#Projects'), di = l.indexOf('#Direct messages');
      check(pi >= 0 && di > pi && l.indexOf(String(proj)) > pi && l.indexOf(String(proj)) < di && l.indexOf(String(dmr)) > di, `${tag}: "Projects" with the project, then "Direct messages" with the person ` + JSON.stringify(l));
      check(!l.includes('#Projects and direct messages'), `${tag}: no mixed section any more ` + JSON.stringify(l));
    };
    const OKB = `document.querySelector('.modal.tcxmd [data-cd="yes"]')`;
    const setVal = (sel, v) => ev(`(() => { const i = document.querySelector('${sel}'); i.value = ${JSON.stringify(v)}; i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
    const newChannel = async (tag, name) => {
      await ev(`(tcx_chanNew(), 1)`);
      check(await wait(`!!document.querySelector('.modal.tcxmd .tcxdlg #tcx-name') && !!document.querySelector('.modal #tcx-mem')`), `${tag}: the dialog New channel`);
      check(await ev(`document.querySelector('.modal.tcxmd #cdlg-t')?.textContent === 'New channel' && ${OKB}?.textContent.trim() === 'Create'`), `${tag}: on the shared dialog (title, Create)`);
      await ev(`(${OKB}.click(), 1)`);
      check(await wait(`document.querySelector('.modal #tcx-name + .ferr')?.textContent === 'Give the channel a name'`), `${tag}: no name = the error at the field ` + await ev(`document.querySelector('.modal .ferr')?.textContent || ''`));
      check(await ev(`!!document.querySelector('.modal.tcxmd') && document.querySelector('#tcx-name').getAttribute('aria-invalid') === 'true' && !document.querySelector('#toast:not(.hidden)')?.textContent.includes('Give the channel a name')`), `${tag}: the dialog stays, the field marked, no toast`);
      await shot(`p21220a-${tag}-noname.png`);
      await setVal('.modal #tcx-name', name);
      check(await ev(`!document.querySelector('.modal .ferr')`), `${tag}: typing clears the error`);
      return name;
    };

    // ===== 1. the organisation: the list
    await signIn('alice');
    await go(B + '#team');
    await listOk('organisation', pr.id, dm.id);
    check(!await ev(`!!document.querySelector('.tcxwhy')`), 'organisation: no line about Private in an organisation');
    await shot('p21220a-list.png');

    // ===== 2. New channel
    await newChannel('channel', 'Crew');
    await ev(`(() => { const b = document.querySelector('.modal #tcx-mem input[value="${bob.id}"]'); if (b) b.checked = true; return 1; })()`);
    await ev(`(${OKB}.click(), 1)`);
    const crew = await (async () => { for (let i = 0; i < 60; i++) { const c = ((await call(CA, 'GET', '/api/team/channels')).channels || []).find(x => x.name === 'Crew'); if (c) return c; await sleep(200); } return null; })();
    check(crew && crew.members === 2, 'channel: created with bob ' + JSON.stringify(crew));
    check(await wait(`location.hash === '#team/${crew?.id}' && !document.querySelector('.modal')`, {timeout: 15000}), 'channel: the new channel opens, the dialog is gone ' + await ev('location.hash'));
    await go(B + '#team');
    check(await wait(`[...document.querySelectorAll('.tclist .tcrow[data-rid="${crew?.id}"]')].some(e => e.textContent.includes('Crew'))`, {timeout: 15000}), 'channel: it stands in the list');
    check(await ev(`(() => { const l = ${LIST}; return l.indexOf('#Channels') >= 0 && l.indexOf('${crew?.id}') > l.indexOf('#Channels'); })()`), 'channel: under "Channels" ' + JSON.stringify(await ev(LIST)));

    // ===== 3. the settings
    await go(B + `#team/${crew?.id}`);
    check(await wait(`S.tc.rid === ${crew?.id} && S.tc.room?.kind === 'channel'`, {timeout: 15000}), 'settings: the channel is open');
    await ev(`(tcx_settings(), 1)`);
    check(await wait(`!!document.querySelector('.modal #tcx-set .tcxmem .tcxrm')`), 'settings: the dialog with the members');
    const S1 = await ev(`(() => { const md = document.querySelector('.modal.tcxmd'), btns = [...md.querySelectorAll('button')];
      const lv = md.querySelector('[data-xs="leave"]'), ar = md.querySelector('[data-xs="archive"]'), x = md.querySelector('.tcxrm').getBoundingClientRect();
      const meRow = [...md.querySelectorAll('.tcxmem .tcxrow')].find(r => r.textContent.includes('Alice'));
      return {title: md.querySelector('#cdlg-t')?.textContent, pri: btns.filter(b => b.classList.contains('pri')).map(b => b.textContent.trim()),
        save: btns.filter(b => /^Save$/.test(b.textContent.trim())).length, cancel: !!md.querySelector('[data-cd="no"]'), nameBtn: !!md.querySelector('.tcxname button'),
        me: meRow?.textContent.replace(/\\s+/g, ' ').trim() || '', lvLink: lv?.classList.contains('linkbtn') && !lv.closest('.foot'), arLink: ar?.classList.contains('linkbtn') && !ar.closest('.foot'),
        lvCol: lv && getComputedStyle(lv).color, arCol: ar && getComputedStyle(ar).color, xw: Math.round(x.width), xh: Math.round(x.height), foot: [...md.querySelectorAll('.foot button')].map(b => b.textContent.trim())}; })()`);
    check(S1.title === 'Channel settings' && S1.pri.join() === 'Done' && S1.foot.join() === 'Done', 'settings: ONE primary button Done, alone in the foot ' + JSON.stringify(S1));
    check(!S1.save && !S1.nameBtn && !S1.cancel, 'settings: no Save next to the name, no Cancel ' + JSON.stringify(S1));
    check(/Alice \(you\)/.test(S1.me), 'settings: "(you)" at my row ' + JSON.stringify(S1.me));
    check(S1.lvLink && S1.arLink, 'settings: Leave and Archive as links apart from Done ' + JSON.stringify(S1));
    check(S1.lvCol && S1.arCol && S1.lvCol !== S1.arCol, 'settings: Archive in its own (warning) colour ' + JSON.stringify([S1.lvCol, S1.arCol]));
    check(S1.xw >= 44 && S1.xh >= 44, 'settings: the remove x at least 44 px on a finger ' + JSON.stringify([S1.xw, S1.xh]));
    await shot('p21220a-settings.png');
    // an empty name + Done: the error at the field, the dialog stays
    await setVal('.modal #tcx-name', '');
    await ev(`(${OKB}.click(), 1)`);
    check(await wait(`document.querySelector('.modal #tcx-name + .ferr')?.textContent === 'Give the channel a name'`), 'settings: an empty name + Done = the error at the field');
    check(await ev(`!!document.querySelector('.modal.tcxmd')`), 'settings: the dialog stays');
    // a new name + Done saves it and closes
    await setVal('.modal #tcx-name', 'Crew room');
    await ev(`(${OKB}.click(), 1)`);
    check(await wait(`!document.querySelector('.modal.tcxmd')`, {timeout: 10000}), 'settings: Done closes');
    const rn = await (async () => { for (let i = 0; i < 50; i++) { const c = ((await call(CA, 'GET', '/api/team/channels')).channels || []).find(x => x.id === crew?.id); if (c?.name === 'Crew room') return c; await sleep(200); } return null; })();
    check(!!rn, 'settings: the name saved with Done');

    // ===== 4. Browse channels
    await ev(`(tcx_browse(), 1)`);
    check(await wait(`[...document.querySelectorAll('.modal.tcxmd .tcxrow')].some(r => r.textContent.includes('Gone soon')) && [...document.querySelectorAll('.modal.tcxmd .tcxrow')].some(r => r.textContent.includes('Lobby'))`), 'browse: both open channels');
    check(await ev(`document.querySelector('.modal.tcxmd #cdlg-t')?.textContent === 'Browse channels' && !document.querySelector('.modal.tcxmd [data-cd="no"]') && ${OKB}?.textContent.trim() === 'Close'`), 'browse: on the shared dialog with Close only');
    check((await call(CB, 'PATCH', `/api/team/rooms/${gone.id}`, {archived: true})).http < 300, 'browse: bob archives "Gone soon" meanwhile');
    await ev(`(document.querySelector('.modal.tcxmd [data-xb="join"][data-rid="${gone.id}"]').click(), 1)`);
    check(await wait(`!!document.querySelector('.modal.tcxmd .tcxerr')?.textContent.trim()`), 'browse: a failed joining says why in the dialog ' + await ev(`document.querySelector('.modal .tcxerr')?.textContent || ''`));
    check(await ev(`!!document.querySelector('.modal.tcxmd') && !location.hash.endsWith('/${gone.id}')`), 'browse: the dialog stays open after the failure');
    await shot('p21220a-browse-error.png');
    await ev(`(document.querySelector('.modal.tcxmd [data-xb="join"][data-rid="${lobby.id}"]').click(), 1)`);
    check(await wait(`location.hash === '#team/${lobby.id}' && !document.querySelector('.modal')`, {timeout: 15000}), 'browse: joining opens the channel and only then closes the dialog ' + await ev('location.hash'));

    // ===== 5. the workspace Private
    check(await ev(`fetch('/api/settings', {method: 'PATCH', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({workspace: 'private'})}).then(r => r.status)`) < 300, 'private: switched to Private');
    await go(B + 'static/icon.svg'); await go(B + '#team');
    check(await wait(`wsCur() === 'private' && !!document.querySelector('.tclist .tcrow[data-rid="${dm.id}"]')`, {timeout: 20000}), 'private: the direct message stands there');
    check(await wait(`/belong to no organisation/.test(document.querySelector('.tclist .tcxwhy')?.textContent || '')`), 'private: one line says why ' + await ev(`document.querySelector('.tcxwhy')?.textContent || ''`));
    check(await ev(`(() => { const w = document.querySelector('.tclist .tcxwhy'), r = document.querySelector('.tclist .tcrow'); return !!w && !!r && !!(w.compareDocumentPosition(r) & Node.DOCUMENT_POSITION_FOLLOWING) && w.getBoundingClientRect().height > 0; })()`), 'private: the line stands above the list and is visible');
    await shot('p21220a-private.png');

    // ===== 6. a person without an organisation
    await signIn('frida');
    await go(B + '#team');
    await listOk('freelancer', fpr.id, fdm.id);
    check(!await ev(`!!document.querySelector('.tcxwhy')`), 'freelancer: no workspaces, no line about Private');
    await newChannel('freelancer channel', 'Studio');
    await ev(`(${OKB}.click(), 1)`);
    check(await wait(`/^#team\\/\\d+$/.test(location.hash) && S.tc.room?.name === 'Studio' && !document.querySelector('.modal')`, {timeout: 15000}), 'freelancer channel: created and open ' + await ev('location.hash'));
  }, true);

  console.log(`p21220_a_chat_dialogs: ${ok} passed, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL: crashed', e); process.exit(1); });
