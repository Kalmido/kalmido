// 2.1213.0 UI test, part D (#6166): "edited" under a team chat message opens its earlier versions (as in an agent's chat).
// kalmido-suite: fresh
// Own container (start.sh), jsdom, invented data only. Bob edits his message in the room (the edit box, Save): the line shows
// the button "edited"; a press opens the dialog "Earlier versions" with the current text on top and the earlier one below;
// closing it leaves the room as it was. Alice (another member) sees the same versions. freelancer-matrix: team -- frida has no
// organisation: her own private channel, an edited message, its earlier version. P21213D_NOSTART=1 = the server already runs.
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, errs} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21213D_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => {
  for (let i = 0; ; i++) {
    const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined});
    if (r.status === 429 && i < 8) { await sleep(500 * (i + 1)); continue; }
    return {...(await r.json().catch(() => ({}))), status: r.status};
  }
};
const until = (fn, ms) => require('./boot').until(fn, {timeout: ms || 15000, step: 100});
const click = (w, el) => el && el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const dlg = d => d.querySelector('.modal.chedmd');

// open the versions of message mid in window w (the button "edited" of its line) -> the dialog
async function openVersions(w, mid) {
  const d = w.document, btn = await until(() => d.querySelector(`#tc-msgs .cmsg[data-mid="t:${mid}"] .cmeta .cedited[data-act="tc-ed-hist"]`));
  check(!!btn && /edited/i.test(btn.textContent), `message ${mid}: the line shows the button "edited"`);
  click(w, btn);
  return until(() => dlg(d));
}

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})});
  check(r.ok, 'setup');
  const CA = await login('alice');
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Kalmido', lang: 'en', collab_all: true, modules: ['comments']});
  const st0 = await call(CA, 'GET', '/api/state'), feats = new Set(((st0.settings || {}).features || '').split(',').filter(Boolean)); feats.add('collab');
  const FEAT = [...feats].join(',');
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const ORG = (await call(CA, 'GET', '/api/state')).me.workspaces[0].id;
  const BOB = (await call(CA, 'POST', '/api/users', {orgs: [ORG], username: 'bob', display_name: 'Bob', password: 'password123'})).id;
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
  const RID = (await call(CA, 'POST', '/api/team/channels', {name: 'Shoot', org_id: ORG, open: false, members: [BOB]})).id;
  check(RID > 0, 'a channel of alice and bob');
  const M1 = (await call(CB, 'POST', `/api/team/rooms/${RID}/messages`, {body: 'Call time at seven'})).id;
  const M0 = (await call(CB, 'POST', `/api/team/rooms/${RID}/messages`, {body: 'Bring the long lens'})).id;
  check(M1 && M0, 'two messages of bob');

  // ================= bob edits his message in the app, then opens its earlier versions
  {
    const w = await boot({user: 'bob', hash: 'team/' + RID}), d = w.document;
    const sel = `#tc-msgs .cmsg[data-mid="t:${M1}"]`;
    await until(() => d.querySelector(`${sel} .cbub`));
    check(!d.querySelector(`${sel} .cedited`) && !d.querySelector(`#tc-msgs .cmsg[data-mid="t:${M0}"] .cedited`), 'messages never edited show no "edited"');
    w.eval(`S.tc.edit = ${M1}; S.tc.editTh = false; S.tc.editVer = tth_msg(${M1}).created_at; tcPatch();`);
    const ed = await until(() => d.querySelector(`${sel} .tc-edit`));
    check(!!ed, 'bob: his message in edit mode');
    ed.value = 'Call time at eight'; ed.dispatchEvent(new w.Event('input', {bubbles: true}));
    click(w, d.querySelector(`${sel} [data-act="tc-edit-save"]`));
    await until(() => !d.querySelector(`${sel} .tc-edit`) && /Call time at eight/.test(d.querySelector(`${sel} .cbub`)?.textContent || ''));
    check(/Call time at eight/.test(d.querySelector(`${sel} .cbub`)?.textContent || ''), 'bob: the new text in the conversation');
    const md = await openVersions(w, M1);
    check(!!md, 'bob: the dialog of the earlier versions opens');
    check(/Earlier versions/.test(md?.querySelector('h3')?.textContent || ''), 'the dialog is titled "Earlier versions"');
    check(/Call time at eight/.test(md?.querySelector('.chednow')?.textContent || ''), 'the current text on top');
    const li = md ? [...md.querySelectorAll('.chedits li')] : [];
    check(li.length === 1 && /Call time at seven/.test(li[0].textContent) && li[0].querySelector('time')?.textContent.trim(),
      `the earlier text below, with its time (${li.map(x => x.textContent.trim()).join(' | ')})`);
    click(w, md?.querySelector('[data-m="close"]'));
    await until(() => !dlg(d));
    check(!dlg(d), 'closed: the dialog is gone');
    check(/Call time at eight/.test(d.querySelector(`${sel} .cbub`)?.textContent || '') && !!d.querySelector(`#tc-msgs .cmsg[data-mid="t:${M0}"]`),
      'back in the room: the messages as before');
    check(!errs.length, `bob: no JS errors ${errs.join(' | ')}`);
    await sleep(300); w.close();
  }

  // ================= alice (another member) sees the same versions; Escape closes them
  {
    errs.length = 0;
    const w = await boot({user: 'alice', hash: 'team/' + RID}), d = w.document;
    const md = await openVersions(w, M1);
    const li = md ? [...md.querySelectorAll('.chedits li')] : [];
    check(li.length === 1 && /Call time at seven/.test(li[0].textContent), 'alice: the earlier version of bob\'s message');
    d.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    await until(() => !dlg(d));
    check(!dlg(d) && !!d.querySelector(`#tc-msgs .cmsg[data-mid="t:${M1}"]`), 'alice: Escape closes the dialog, the room stays');
    check(!errs.length, `alice: no JS errors ${errs.join(' | ')}`);
    await sleep(300); w.close();
  }

  // ================= frida (no organisation): her own private channel
  {
    errs.length = 0;
    await call(CA, 'POST', '/api/users', {username: 'frida', display_name: 'Frida Solo', password: 'password123', email: 'frida@example.com', orgs: []});
    const CF = await login('frida');
    await call(CF, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: FEAT});
    check(!((await call(CF, 'GET', '/api/state')).me.workspaces || []).length, 'P4: frida has no organisation');
    const FR = (await call(CF, 'POST', '/api/team/channels', {name: 'Notes to self'})).id;
    const FM = (await call(CF, 'POST', `/api/team/rooms/${FR}/messages`, {body: 'First idea'})).id;
    const e = await call(CF, 'PATCH', `/api/team/messages/${FM}`, {body: 'Better idea'});
    check(e.status === 200, `frida: her message edited (${e.status})`);
    const w = await boot({user: 'frida', hash: 'team/' + FR}), d = w.document;
    const md = await openVersions(w, FM);
    const li = md ? [...md.querySelectorAll('.chedits li')] : [];
    check(li.length === 1 && /First idea/.test(li[0].textContent) && /Better idea/.test(md.querySelector('.chednow')?.textContent || ''),
      'frida: the earlier version of her message, the current one on top');
    click(w, md?.querySelector('[data-m="close"]'));
    await until(() => !dlg(d));
    check(!dlg(d), 'frida: closed');
    check(!errs.length, `frida: no JS errors ${errs.join(' | ')}`);
    await sleep(300); w.close();
  }

  console.log(`p21213_d_tchat_versions_ui: ${ok} ok, ${F.length} failed`);
  execFileSync('docker', ['rm', '-f', process.env.KALMIDO_TEST_CONTAINER || 'kalmido-test'], {stdio: 'ignore'});
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
