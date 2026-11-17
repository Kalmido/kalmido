// kalmido-suite:
// 2.1357.0 UI test (#6335: live updates on a second device), own container (start.sh), Firefox, phone width (390 x 844).
// The browser is one device of alice, the suite's own fetches with a second login of alice are her other device; bob writes
// in the team chat. Invented data only.
// - B5: a late delta answer (overtaken by a newer one) does not take a task back to an older copy; the bundled follow-up
//   asked from an older version still brings its tasks
// - B3: notes are a light area: a note made / changed on the other device shows in the open notes and the open note;
//   typing not saved yet keeps its text (the reload waits), also when typing begins while the reload is on its way
// - B4: the open calendar / Today view shows an event changed on the other device
// - B6: the team chat's signal is taken only once it was handled (typing elsewhere does not swallow it)
// - B8: the open file store shows a folder made on the other device; the day changing redraws the open Today view
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21357_a_live_ui', check, shots: 'P21357A_SHOTS'});
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
const call = async (ck, method, url, body) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, ...(ck ? {Cookie: ck} : {})}, body: body ? JSON.stringify(body) : undefined}); const j = await r.json().catch(() => ({})); return {...j, http: r.status}; };

(async () => {
  await sleep(600);
  const r = await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123', wizard: true, lang: 'en'})});
  check(r.ok, 'setup');
  const CA = await login('alice');  // the other device
  await call(CA, 'POST', '/api/admin/setup', {org_name: 'Alpha', lang: 'en', collab_all: true, modules: ['comments']});
  await call(CA, 'PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'comments,collab,cal,events,team'});
  const ORG = ((await call(CA, 'GET', '/api/state')).me?.workspaces || [])[0]?.id;
  const BOB = (await call(CA, 'POST', '/api/users', {orgs: ORG ? [ORG] : [], username: 'bob', display_name: 'Bob', password: 'password123', email: 'bob@example.com'})).id;
  const CB = await login('bob');
  await call(CB, 'PATCH', '/api/settings', {lang: 'en', tour: 'done'});
  const LB = (await call(CA, 'POST', '/api/lists', {name: 'With Bob'})).id;
  await call(CA, 'PUT', `/api/lists/${LB}/members`, {user_id: BOB, role: 'edit'});  // people who work together
  const dm = await call(CA, 'POST', '/api/team/dm', {user_id: BOB}), DM = dm.id;
  if (!DM) console.log('team dm:', JSON.stringify(dm), 'org', ORG, 'bob', BOB);
  const day = n => { const d = new Date(); d.setDate(d.getDate() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const W = (await call(CA, 'POST', '/api/evcals', {name: 'Work', color: '#2dd4bf'})).id;
  const EV = (await call(CA, 'POST', '/api/events', {title: 'Standup', cal_id: W, start: `${day(0)}T09:00`, end: `${day(0)}T09:15`})).id;
  const L = (await call(CA, 'POST', '/api/lists', {name: 'Household'})).id;
  const T = (await call(CA, 'POST', '/api/tasks', {title: 'Shopping', content: 'Milk', list_id: L})).id;

  await firefox(async o => {
    const {ev, nav, shot, cmd, ctx} = o;
    const ready = async (expr, n = 40) => { for (let i = 0; i < n; i++) { if (await ev(expr).catch(() => false)) return true; await sleep(250); } return false; };
    // a background window gets no focus events (tests/p2170_ui.js): sent by hand, as a browser in front sends them
    const focus = sel => ev(`(() => { const x = document.querySelector('${sel}'); x.focus(); x.dispatchEvent(new FocusEvent('focusin', {bubbles: true})); return 1; })()`);
    const leave = sel => ev(`(() => { const x = document.querySelector('${sel}'); x.blur(); x.dispatchEvent(new FocusEvent('focusout', {bubbles: true})); return 1; })()`);
    const caught = () => ready(`fetch('/api/version', {headers: {'X-Requested-With': 'kalmido'}}).then(r => r.json()).then(j => j.v === S.v && !td_polling)`, 120);
    await nav(B + 'static/icon.svg');
    await ev(`(() => { localStorage.clear(); localStorage.setItem('tasks.theme', '"light"'); return 1; })()`);
    await ev(`fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'}, body: JSON.stringify({username: 'alice', password: 'password123'})}).then(r => r.status)`);
    await cmd('browsingContext.setViewport', {context: ctx, viewport: {width: 390, height: 844}});
    await nav(B + '#l/' + L);
    check(await ready(`typeof lpDelta === 'function' && !!document.querySelector('#view [data-id="${T}"]') && !!S.lpA`, 60), 'the list on a phone, the poll runs');

    // ================= B5 a late delta answer does not overwrite a newer one
    S6335B5: {
      await caught();
      const T5 = (await call(CA, 'POST', '/api/tasks', {title: 'B5 start', list_id: L})).id;
      check(await ready(`!!document.querySelector('#view .trow[data-id="${T5}"]')`, 60), 'B5: the new row is shown');
      await caught();
      const held = await ready(`(() => { if (td_polling) return false; td_polling = true; return true; })()`, 120);
      check(held, 'B5: the poll held'); if (!held) break S6335B5;
      // the first delta reads the old change, its answer is held back until the second one is through; a write of this
      // window meanwhile (a read mark in the background) would send lpDelta the full way and hide the race: S.wseq is put
      // back to its value at the delta's start before the answer is let through (no write of mine, the case of #6335 B5)
      const gate = `(() => { const a0 = window.__api0 || api; window.__api0 = a0; window.__got = 0; window.__gate = null; api = function (m, u) { const p = a0.apply(this, arguments); if (!String(u).includes('/api/state/delta')) return p; api = a0; window.__w = S.wseq || 0; p.then(() => { window.__got = 1; }, () => {}); return new Promise(res => { window.__gate = () => p.then(res, () => res(null)); }); }; return 1; })()`;
      await ev(gate);
      await call(CA, 'PATCH', `/api/tasks/${T5}`, {title: 'B5 old'});
      await ev(`(() => { window.__p1 = lpDelta(S.v, ['tasks']); return 1; })()`);
      check(await ready(`typeof window.__gate === 'function'`, 20), 'B5: the first delta is on its way');
      check(await ready(`window.__got === 1`, 40), 'B5: the server answered the first delta (the answer waits in the page)');
      await call(CA, 'PATCH', `/api/tasks/${T5}`, {title: 'B5 new'});
      check(await ev(`lpDelta(S.v, ['tasks']).then(() => S.tasks.get(${T5})?.title)`) === 'B5 new', 'B5: the second delta brings the newest title');
      await ev(`(() => { S.wseq = window.__w; window.__gate(); return window.__p1.then(r => { window.__r1 = r; return 1; }); })()`);
      check(await ev(`S.tasks.get(${T5})?.title`) === 'B5 new' && /B5 new/.test(await ev(`document.querySelector('#view .trow[data-id="${T5}"]')?.textContent || ''`)), 'B5: the late answer of the first delta does not take the older title back ' + JSON.stringify(await ev(`({t: S.tasks.get(${T5})?.title, row: document.querySelector('#view .trow[data-id="${T5}"]')?.textContent, late: S.lpN.late, r: window.__r1})`).catch(e => String(e))));
      // the bundled follow-up asks from an older version (S.lpBase) while S.v moved on without a state (a light change,
      // lpLive): its late answer still brings the tasks of that range
      const T6 = (await call(CA, 'POST', '/api/tasks', {title: 'F start', list_id: L})).id;
      await ev(`lpDelta(S.v, ['tasks']).then(() => 1)`);
      const base = await ev(`S.v`);
      await call(CA, 'PATCH', `/api/tasks/${T6}`, {title: 'F changed'});
      const vnow = (await call(CA, 'GET', '/api/version')).v;
      await ev(gate);
      await ev(`(() => { S.v = ${vnow}; window.__pf = lpDelta(S.v, ['tasks'], undefined, ${base}); return 1; })()`);
      check(await ready(`window.__got === 1`, 40), 'B5: the follow-up\'s delta is answered (held in the page)');
      await call(CA, 'PATCH', `/api/tasks/${T5}`, {title: 'B5 newer'});
      await ev(`lpDelta(S.v, ['tasks']).then(() => 1)`);
      await ev(`(() => { S.wseq = window.__w; window.__gate(); return window.__pf.then(r => { window.__r1 = r; return 1; }); })()`);
      check(await ev(`S.tasks.get(${T6})?.title`) === 'F changed', 'B5: the late follow-up (asked from an older version) still brings its tasks ' + await ev(`JSON.stringify({t: S.tasks.get(${T6})?.title, r: window.__r1})`));
      check(await ev(`S.tasks.get(${T5})?.title`) === 'B5 newer', 'B5: ... and keeps the newer copy of a task it read earlier');
      await ev(`(() => { api = window.__api0; td_polling = false; return 1; })()`);
    }

    // ================= B3 notes: a light area of their own; the open notes and the open note follow
    S6335B3: {
      await ev(`(() => { location.hash = '#notes/${L}'; return 1; })()`);
      const nv = await ready(`S.route.mod === 'notes' && S.nt.lid === ${L} && Array.isArray(S.nt.notes)`, 40);
      check(nv, 'B3: the notes of the list are open'); if (!nv) break S6335B3;
      await caught();
      const NID = (await call(CA, 'POST', `/api/lists/${L}/notes`, {title: 'Phone list', body: 'Eggs'})).id;
      check(await ready(`/Phone list/.test(document.querySelector('#view')?.textContent || '')`, 40), 'B3: a note made on the other device shows in the open notes ' + await ev(`S.nt.notes?.length`));
      check(await ready(`(S.notes || []).some(n => n.id === ${NID})`, 80), 'B3: ... and in the notes the app knows (search, overview)');
      await ev(`(() => { location.hash = '#note/${NID}'; return 1; })()`);
      const nopen = await ready(`S.nt.id === ${NID} && /Eggs/.test(document.querySelector('#nt-md')?.textContent || '')`, 40);
      check(nopen, 'B3: the note is open (read)');
      if (!nopen) { await ev(`(() => { location.hash = '#l/${L}'; return 1; })()`); break S6335B3; }
      await caught();
      await call(CA, 'PATCH', `/api/notes/${NID}`, {body: 'Eggs, milk'});
      check(await ready(`/milk/.test(document.querySelector('#nt-md')?.textContent || '')`, 40), 'B3: the open note shows the other device\'s text ' + await ev(`document.querySelector('#nt-md')?.textContent`));
      await shot('p21357a-b3-note.png');
      // writing on builds on the new text: no conflict question
      await ev(`(() => { S.nt.edit = true; renderView(); const b = document.querySelector('#nt-body'); b.value += ', bread'; b.dispatchEvent(new Event('input', {bubbles: true})); return noteFlush().then(() => 1); })()`);
      const nb = async () => (await call(CA, 'GET', `/api/lists/${L}/notes`)).notes?.find(n => n.id === NID)?.body;
      let body = ''; for (let i = 0; i < 40 && body !== 'Eggs, milk, bread'; i++) { body = await nb(); if (body !== 'Eggs, milk, bread') await sleep(250); }
      check(body === 'Eggs, milk, bread' && !(await ev(`!!document.querySelector('.modal')`)), 'B3: writing on saves on top of the other device\'s text, no conflict question ' + body);
      // typing begun while the reload is on its way: the notes are not replaced (the next save keeps its base)
      await caught();
      await call(CA, 'PATCH', `/api/notes/${NID}`, {body: 'Race text'});
      const race = await ev(`(async () => { S.nt.dirty = false; const p = lpNotes(); S.nt.dirty = true; await p; const n = (S.nt.notes || []).find(x => x.id === ${NID}); return {live: S.nt.live, body: n && n.body}; })()`);
      check(race.live === true && race.body !== 'Race text', 'B3: typing begun during the reload keeps the notes as they were ' + JSON.stringify(race));
      await ev(`(() => { S.nt.dirty = false; return 1; })()`);
      // typed and not saved yet: a change from elsewhere waits, the typed text stays
      await ev(`(() => { const b = document.querySelector('#nt-body'); b.value += ' and tea'; b.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
      await call(CA, 'PATCH', `/api/notes/${NID}`, {body: 'Only coffee'});
      await ev(`(() => { lpNotes(); return 1; })()`);
      check(await ev(`document.querySelector('#nt-body').value.endsWith(' and tea') && S.nt.live === true`), 'B3: unsaved typing stays, the reload waits');
      await ev(`(() => { clearTimeout(S.nt.saveT); S.nt.dirty = false; S.nt.edit = false; location.hash = '#l/${L}'; return 1; })()`);
      await ready(`S.route.mod === 'tasks'`, 20);
    }

    // ================= B4 the open calendar / Today view draws an event changed on the other device
    S6335B4: {
      check(!!EV, 'B4: the event exists'); if (!EV) break S6335B4;
      for (const [hash, title] of [['#cal', 'Standup moved'], ['#today', 'Standup again']]) {
        await ev(`(() => { S.collapsed.add('cev-past'); location.hash = '${hash}'; return 1; })()`);  // Today: past events unfolded (the suite may run after 09:15)
        const shown = await ready(`/Standup/.test(document.querySelector('#view')?.textContent || '')`, 60);
        check(shown, `B4 ${hash}: the event is shown`); if (!shown) continue;
        await caught();
        await call(CA, 'PATCH', `/api/events/${EV}`, {title});
        check(await ready(`document.querySelector('#view')?.textContent.includes('${title}')`, 40), `B4 ${hash}: the open view shows the other device's change`);
      }
      await shot('p21357a-b4-today.png');
    }

    // ================= B6 the team chat's signal is taken only once it was handled
    S6335B6: {
      check(!!DM, 'B6: a direct conversation with bob'); if (!DM) break S6335B6;
      await ev(`(() => { location.hash = '#l/${L}'; return 1; })()`);
      await ready(`S.route.mod === 'tasks' && S.teamSig !== undefined`, 40);
      await caught();
      const u0 = await ev(`S.team?.unread || 0`);
      // alice types (the task's title has the focus) while bob writes
      await ev(`(() => { openDetail(${T}); return 1; })()`);
      await ready(`S.sel === ${T} && !!document.querySelector('#d-title')`, 20);
      await focus('#d-title');
      await call(CB, 'POST', `/api/team/rooms/${DM}/messages`, {body: 'Coffee at three?'});
      const t1 = await ev(`Date.now()`);
      check(await ready(`editing() && S.syncOk > ${t1} && !td_polling`, 40), 'B6: a poll ran while alice types ' + await ev(`JSON.stringify({ed: editing(), act: document.activeElement?.id})`));
      await leave('#d-title');
      await ev(`(() => { closeDetail(); return 1; })()`);
      // the next poll takes the waiting signal (not the bundled follow-up 15 s later)
      check(await ready(`(S.team?.unread || 0) > ${u0}`, 28), 'B6: after typing the team chat shows the new message (unread) ' + await ev(`JSON.stringify({u: S.team?.unread, sig: S.teamSig, lpT: !!lpT})`));
    }

    // ================= B8 the open file store folder follows a change elsewhere; the day's change redraws Today
    S6335B8: {
      const st0 = await call(CA, 'GET', '/api/state');
      const feats = [...new Set([...(st0.settings?.features || '').split(',').filter(Boolean), 'files', 'docs'])].join(',');
      await call(CA, 'PATCH', '/api/settings', {features: feats, workspace: 'private'});
      const on = await ready(`typeof feat === 'function' && feat('files') && S.settings.workspace === 'private'`, 80);
      check(on, 'B8: the file store is switched on (taken from the other device)'); if (!on) break S6335B8;
      await ev(`(() => { location.hash = '#ablage'; return 1; })()`);
      const shown = await ready(`S.route.mod === 'ablage' && !AB.loading && !!AB.data`, 60);
      check(shown, 'B8: the file store is open'); if (!shown) break S6335B8;
      await caught();
      const FD = (await call(CA, 'POST', '/api/files/folders', {space: 'private', name: 'Holiday pictures'})).id;
      check(!!FD, 'B8: the other device made a folder');
      // the change is "other" (the whole state): a full load may wait for the server's brake (8 s after the last one, core/state.py)
      check(await ready(`(document.querySelector('#view')?.textContent || '').includes('Holiday pictures')`, 100), 'B8: the open file store shows the folder made on the other device ' + JSON.stringify(await ev(`({items: (AB.data?.items || []).map(n => n.name), key: AB.key, v: S.v, route: location.hash, lp: S.lpN})`).catch(e => String(e))) + ' fd ' + FD);
      await shot('p21357a-b8-ablage.png');
      // the day changes while the app stays open (here: the day it noted is set back): the shown view and the sidebar are drawn
      await ev(`(() => { location.hash = '#today'; return 1; })()`);
      await ready(`S.route.key === 'today'`, 20);
      await ev(`(() => { window.__rv = 0; const R0 = renderView; renderView = function () { window.__rv++; return R0.apply(this, arguments); }; S.dayNow = '2000-01-01'; document.dispatchEvent(new Event('visibilitychange')); return 1; })()`);
      check(await ready(`S.dayNow === today() && window.__rv > 0`, 40), 'B8: the day change redraws the open Today view (back in the app)');
    }
  }, true);

  console.log(`p21357_a_live_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
