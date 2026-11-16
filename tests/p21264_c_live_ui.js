// kalmido-suite:
// 2.1264.0 UI test (Teil C: live updates on a second device), own container (start.sh), Firefox, phone width (390 x 844, touch).
// The browser is one device of alice, the suite's own fetches with a second login of alice are her other device. Invented data only.
// - #6326: the open task changed on the other device: the panel (it holds the focus on a phone) shows the new text at once;
//   a focused field keeps what it shows while the change arrives, a save typed on it is a conflict (the other device's text
//   stays on the server), a field left untouched shows the newest text
const path = require('path');
const {execFileSync} = require('child_process');
const {sleep, B, login} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const firefox = require('./ff')({tag: 'p21264_c_live_ui', check, shots: 'P21264C_SHOTS'});
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
  const other = (body, prev) => call(CA, 'PATCH', `/api/tasks/${T}`, {...body, _prev: prev});
  const srv = async () => call(CA, 'GET', `/api/tasks/${T}`);
  // the server's task once fn holds (a save goes out through the outbox: it lands a moment after flushSaves)
  const srvUntil = async (fn, n = 40) => { let x; for (let i = 0; i < n; i++) { x = await srv(); if (fn(x)) return x; await sleep(250); } return x; };

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
    check(await ready(`typeof lpDelta === 'function' && isMobile() && !!document.querySelector('#view [data-id="${T}"]') && !!S.lpA`, 60), 'the list on a phone, the poll runs');

    // ================= #6326 the open task changed on the other device
    S6326: {
      await ev(`(() => { openDetail(${T}); return 1; })()`);
      const open = await ready(`S.sel === ${T} && document.activeElement === document.querySelector('#detail')`, 40);
      check(open, '#6326: the panel is open and holds the focus (phone)'); if (!open) break S6326;
      const shown = `(() => { const ta = document.querySelector('#d-content'), md = document.querySelector('#d-md'); return md && !md.classList.contains('hidden') ? md.textContent : ta?.value; })()`;
      check(/Milk/.test(await ev(shown)), '#6326: the panel shows the note');
      await other({content: 'Milk, eggs, bread'}, {content: 'Milk'});
      check(await ready(`S.tasks.get(${T})?.content === 'Milk, eggs, bread'`, 60), '#6326: the change arrives (delta)');
      check(await ready(`/eggs, bread/.test(${shown})`, 20), '#6326: the panel shows the other device\'s text at once (the focus was in the panel) ' + JSON.stringify(await ev(shown)));
      await shot('p21264c-6326-panel.png');
      // typed on: the text builds on what the panel shows
      await ev(`(() => { editContent(); const ta = document.querySelector('#d-content'); ta.dispatchEvent(new FocusEvent('focusin', {bubbles: true})); ta.value += ', cheese'; ta.dispatchEvent(new Event('input', {bubbles: true})); return flushSaves().then(() => 1); })()`);
      check((await srvUntil(x => /cheese/.test(x.content || ''))).content === 'Milk, eggs, bread, cheese', '#6326: typing on keeps the other device\'s text ' + (await srv()).content);
      await caught();
      await leave('#d-content');
      await caught();

      // the field holds the focus while the change arrives (the delta's answer came after the tap): it keeps what it shows,
      // a save typed on it is a conflict, the other device's text stays
      await ev(`(() => { editContent(); document.querySelector('#d-content').dispatchEvent(new FocusEvent('focusin', {bubbles: true})); return 1; })()`);
      check(await ready(`document.activeElement?.id === 'd-content'`, 20), '#6326: the note field has the focus');
      await other({content: 'Bread only'}, {content: 'Milk, eggs, bread, cheese'});
      await ev(`lpDelta(S.v, ['tasks']).then(() => 1)`);
      check(await ev(`S.tasks.get(${T})?.content === 'Bread only' && document.querySelector('#d-content').value === 'Milk, eggs, bread, cheese'`), '#6326: the focused field keeps what it shows (calm view) ' + JSON.stringify(await ev(`(() => { const x = document.querySelector('#d-content'); return {v: x?.value, dv: x?.defaultValue, hid: x?.classList.contains('hidden'), st: S.tasks.get(${T})?.content, act: document.activeElement?.id, q: OUT.q.length, ed: editing()}; })()`).catch(e => String(e))));
      await ev(`(() => { const ta = document.querySelector('#d-content'); ta.value += ', butter'; ta.dispatchEvent(new Event('input', {bubbles: true})); return flushSaves().then(() => 1); })()`);
      check(await ready(`(S.conflicts || []).some(c => c.field === 'content') || !OUT.q.length`, 40), '#6326: the save is answered');
      check((await srvUntil(x => x.content !== 'Bread only', 8)).content === 'Bread only', '#6326: the save on the old text does not overwrite the other device\'s change silently ' + (await srv()).content);
      check(await ready(`(S.conflicts || []).some(c => c.field === 'content') && document.querySelector('#d-content').value.endsWith(', butter')`, 20), '#6326: a conflict, the typed text stays in the field');
      await shot('p21264c-6326-conflict.png');
      // the bar's "Keep mine" saves the typed text on top of the other one (one goes on from here)
      await ev(`(() => { document.querySelector('#detail .cfbar[data-f="content"] [data-cfi="mine"]')?.click(); return 1; })()`);
      check(await ready(`!document.querySelector('#detail .cfbar')`, 20) && /butter$/.test((await srvUntil(x => /butter$/.test(x.content || ''))).content || ''), '#6326: "Keep mine" saves the typed text ' + (await srv()).content);
      await leave('#d-content');
      await caught();

      // a field left untouched shows the newest text once it is left (and saves nothing over it)
      await ev(`(() => { closeDetail(); openDetail(${T}); return 1; })()`);
      await ready(`S.sel === ${T} && !!document.querySelector('#d-title')`, 20);
      await focus('#d-title');
      const t0 = await ev(`document.querySelector('#d-title').value`);
      await other({title: 'Shopping Saturday'}, {title: t0});
      const dbg = () => ev(`(() => { const x = document.querySelector('#d-title'); return {v: x?.value, dv: x?.defaultValue, kf: x?._kf, st: S.tasks.get(${T})?.title, stale: S.detailStale, q: OUT.q.length, act: document.activeElement?.id}; })()`).catch(e => String(e));
      check(await ready(`document.activeElement?.id === 'd-title' && lpDelta(S.v, ['tasks']).then(() => S.tasks.get(${T})?.title === 'Shopping Saturday')`, 20), '#6326: the title change arrives while the title has the focus ' + JSON.stringify(await dbg()));
      check(await ev(`document.querySelector('#d-title').value === ${JSON.stringify(t0)}`), '#6326: the focused title keeps what it shows');
      await leave('#d-title');
      check(await ready(`document.querySelector('#d-title')?.value === 'Shopping Saturday'`, 20), '#6326: left untouched, the title shows the newest text ' + JSON.stringify(await dbg()));
      check((await srvUntil(x => x.title !== 'Shopping Saturday', 8)).title === 'Shopping Saturday', '#6326: leaving the field saved nothing over it');
    }

    // ================= #6335 B5 a late delta answer does not overwrite a newer one
    S6335B5: {
      await ev(`(() => { closeDetail(); return 1; })()`);
      await caught();
      const T5 = (await call(CA, 'POST', '/api/tasks', {title: 'B5 start', list_id: L})).id;
      check(await ready(`!!document.querySelector('#view .trow[data-id="${T5}"]')`, 60), 'B5: the new row is shown');
      await caught();
      const held = await ready(`(() => { if (td_polling) return false; td_polling = true; return true; })()`, 120);
      check(held, 'B5: the poll held'); if (!held) break S6335B5;
      // the first delta reads the old change, its answer is held back until the second one is through
      await ev(`(() => { const a0 = api; window.__gate = null; window.__api0 = a0; api = function (m, u) { const p = a0.apply(this, arguments); if (!String(u).includes('/api/state/delta')) return p; api = a0; p.then(() => { window.__got = 1; }, () => {}); return new Promise(res => { window.__gate = () => p.then(res, () => res(null)); }); }; return 1; })()`);
      await call(CA, 'PATCH', `/api/tasks/${T5}`, {title: 'B5 old'});
      await ev(`(() => { window.__p1 = lpDelta(S.v, ['tasks']); return 1; })()`);
      check(await ready(`typeof window.__gate === 'function'`, 20), 'B5: the first delta is on its way');
      check(await ready(`window.__got === 1`, 40), 'B5: the server answered the first delta (the answer waits in the page)');
      await call(CA, 'PATCH', `/api/tasks/${T5}`, {title: 'B5 new'});
      check(await ev(`lpDelta(S.v, ['tasks']).then(() => S.tasks.get(${T5})?.title)`) === 'B5 new', 'B5: the second delta brings the newest title');
      await ev(`(() => { window.__gate(); return window.__p1.then(() => 1); })()`);
      check(await ev(`S.tasks.get(${T5})?.title`) === 'B5 new' && /B5 new/.test(await ev(`document.querySelector('#view .trow[data-id="${T5}"]')?.textContent || ''`)), 'B5: the late answer of the first delta does not take the older title back ' + JSON.stringify(await ev(`({t: S.tasks.get(${T5})?.title, row: document.querySelector('#view .trow[data-id="${T5}"]')?.textContent, stale: S.viewStale, busy: lpBusy(), ed: editing(), act: document.activeElement?.id || document.activeElement?.tagName, route: S.route.mod + '/' + S.route.key, late: S.lpN.late})`).catch(e => String(e))));
      await ev(`(() => { api = window.__api0; td_polling = false; return 1; })()`);
    }

    // ================= #6335 B3 notes: a light area of their own; the open notes and the open note follow
    S6335B3: {
      await ev(`(() => { location.hash = '#notes/${L}'; return 1; })()`);
      const nv = await ready(`S.route.mod === 'notes' && S.nt.lid === ${L} && Array.isArray(S.nt.notes)`, 40);
      check(nv, 'B3: the notes of the list are open'); if (!nv) break S6335B3;
      await caught();
      const NID = (await call(CA, 'POST', `/api/lists/${L}/notes`, {title: 'Phone list', body: 'Eggs'})).id;
      check(await ready(`/Phone list/.test(document.querySelector('#view')?.textContent || '')`, 40), 'B3: a note made on the other device shows in the open notes ' + await ev(`S.nt.notes?.length`));
      check(await ready(`(S.notes || []).some(n => n.id === ${NID})`, 80), 'B3: ... and in the notes the app knows (search, overview)');
      await ev(`(() => { location.hash = '#note/${NID}'; return 1; })()`);
      check(await ready(`S.nt.id === ${NID} && /Eggs/.test(document.querySelector('#nt-md')?.textContent || '')`, 40), 'B3: the note is open (read)');
      await caught();
      await call(CA, 'PATCH', `/api/notes/${NID}`, {body: 'Eggs, milk'});
      check(await ready(`/milk/.test(document.querySelector('#nt-md')?.textContent || '')`, 40), 'B3: the open note shows the other device\'s text ' + await ev(`document.querySelector('#nt-md')?.textContent`));
      await shot('p21264c-b3-note.png');
      // writing on builds on the new text: no conflict question
      await ev(`(() => { S.nt.edit = true; renderView(); const b = document.querySelector('#nt-body'); b.value += ', bread'; b.dispatchEvent(new Event('input', {bubbles: true})); return noteFlush().then(() => 1); })()`);
      const nb = async () => (await call(CA, 'GET', `/api/lists/${L}/notes`)).notes?.find(n => n.id === NID)?.body;
      let body = ''; for (let i = 0; i < 40 && body !== 'Eggs, milk, bread'; i++) { body = await nb(); if (body !== 'Eggs, milk, bread') await sleep(250); }
      check(body === 'Eggs, milk, bread' && !(await ev(`!!document.querySelector('.modal')`)), 'B3: writing on saves on top of the other device\'s text, no conflict question ' + body);
      // typed and not saved yet: a change from elsewhere waits, the typed text stays
      await caught();
      await ev(`(() => { const b = document.querySelector('#nt-body'); b.value += ' and tea'; b.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()`);
      await call(CA, 'PATCH', `/api/notes/${NID}`, {body: 'Only coffee'});
      await ev(`(() => { lpNotes(); return 1; })()`);
      check(await ev(`document.querySelector('#nt-body').value.endsWith(' and tea') && S.nt.live === true`), 'B3: unsaved typing stays, the reload waits');
      await ev(`(() => { clearTimeout(S.nt.saveT); S.nt.dirty = false; S.nt.edit = false; location.hash = '#l/${L}'; return 1; })()`);
      await ready(`S.route.mod === 'tasks'`, 20);
    }

    // ================= #6335 B4 the open calendar / Today view draws an event changed on the other device
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
      await shot('p21264c-b4-today.png');
    }

    // ================= #6335 B6 the team chat's signal is taken only once it was handled
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
  }, true);

  console.log(`p21264_c_live_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.log('FAIL:', e.stack || e); process.exit(1); });
