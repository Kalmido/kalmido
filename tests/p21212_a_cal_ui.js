// 2.1212.0 UI test, part A (#6159 calendar polish round 2, the rest of round 1), jsdom,
// kalmido-suite: fresh
// own container (start.sh), invented names only. P21212A_NOSTART=1 = the container runs.
// freelancer-matrix: n/a (no new route; alice has no organisation, every check runs without one)
// - the event popover: "Loading…" is the shared block while the event loads; a failed load says so with "Try again" (it closed
//   without a word) and "Try again" opens the event
// - deleting an event, a date of a series and a calendar: the step is in the history (Ctrl+Z takes it back, not only the toast)
// - the subscription link window: the shared "Loading…"; a failed load says what failed with "Try again" (was "Only available
//   online." for every error)
// - the people of the event editor: a failed load is not kept as "nobody", the field says it could not load them
// - the later dates of repeating tasks that could not be loaded: the calendar says so with "Try again", no loop of fetches
// - a subscription's sync error and a refused save: what failed first, the calendar server's text in brackets
// - the view choice is a group with a name; the Calendars window: the trash is the last row, the "Per project" rows have no
//   inline styles
// - #6158: an event in another time zone names the zone at its times (popover "10:00–11:00 New York · … your time", the editor
//   next to Starts / Ends; the device's zone: no hint); the task an event prepares stands in the editor outside "More options"
//   and is fetched when it is not in memory (popover too, it opens); an own series carries the repeat mark; an existing event
//   without guests has no availability bar; the Calendars window: a shared calendar's row has its own line "shared with 2 people"
// - #6156: the calendar's Share dialog is the shared frame (X on top, "Done"), the owner first, the people with the role words
//   of projects (Member / Read-only, only these two), "Add" says "Shared"; taking a person out goes without a question, the
//   toast's Undo and Ctrl+Z put the share back with its role (the core's restore); people that could not be loaded say so
//   with "Try again" (no names "?"); the window's row of a calendar shared with me uses the same role word
const {execFileSync} = require('child_process');
const path = require('path');
const {boot, sleep, B, login, until: until0, histAdded, idle, undoToast} = require('./boot');
const F = []; let ok = 0;
const check = (c, what) => { if (c) ok++; else { F.push(what); console.log('FAIL:', what); } };
const H = {'Content-Type': 'application/json', 'X-Requested-With': 'kalmido'};
const DATA = process.argv[2] || path.join(__dirname, '.data');
if (!process.env.P21212A_NOSTART) execFileSync('bash', [path.join(__dirname, 'start.sh'), DATA], {stdio: 'ignore'});
let CK;
const call = async (method, url, body, ck = CK) => { const r = await fetch(B + url.replace(/^\//, ''), {method, headers: {...H, Cookie: ck}, body: body ? JSON.stringify(body) : undefined}); return {http: r.status, ...(await r.json().catch(() => ({})))}; };
const until = fn => until0(fn, {timeout: 15000, step: 100});
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', {bubbles: true, cancelable: true}));
const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
const pad = n => String(n).padStart(2, '0');
const dstr = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const D0 = dstr(new Date());
// the page's requests: one matching w.__fail fails with 500 (a server text), one matching w.__hold waits in w.__held until the
// test lets it go (go) - every wait below is on a real state
const wrap = w => {
  const f1 = w.fetch;
  w.__log = []; w.__held = []; w.__fail = null; w.__hold = null;
  w.fetch = (u, o = {}) => {
    const k = `${o.method || 'GET'} ${u}`; w.__log.push(k);
    if (w.__fail && w.__fail.test(k)) return Promise.resolve(new Response(JSON.stringify({error: 'Refused for the test'}), {status: 500, headers: {'content-type': 'application/json'}}));
    if (w.__hold && w.__hold.test(k)) return new Promise(res => w.__held.push({k, go: () => res(f1(u, o))}));
    return f1(u, o);
  };
};
const ctrlZ = w => w.document.body.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'z', ctrlKey: true, bubbles: true, cancelable: true}));
const closeAll = d => { d.querySelectorAll('.modal').forEach(m => m.remove()); };

(async () => {
  await sleep(600);
  check(await until(async () => (await fetch(B + 'api/auth/setup', {method: 'POST', headers: H, body: JSON.stringify({username: 'alice', display_name: 'Alice', password: 'password123'})}).catch(() => null))?.status < 500), 'setup');
  CK = await login('alice');
  await call('POST', '/api/admin/setup', {lang: 'en', collab_all: true});
  await call('PATCH', '/api/settings', {lang: 'en', tour: 'done', features: 'cal,events,collab'});
  const W = await call('POST', '/api/evcals', {name: 'Work', color: '#2dd4bf'});
  const SU = await call('POST', '/api/events', {title: 'Standup', cal_id: W.id, start: `${D0}T09:00`, end: `${D0}T09:30`, reminders: []});
  const PI = await call('POST', '/api/events', {title: 'Tuning the piano', cal_id: W.id, start: `${D0}T15:00`, end: `${D0}T16:00`, reminders: []});
  const SE = await call('POST', '/api/events', {title: 'Rehearsal', cal_id: W.id, start: `${D0}T18:00`, end: `${D0}T19:00`, rrule: 'FREQ=DAILY;COUNT=5', reminders: []});
  const CH = await call('POST', '/api/evcals', {name: 'Choir', color: '#a78bfa'});
  check(W.id && SU.id && PI.id && SE.id && CH.id, 'set-up: two calendars, a single event, a series');
  const me = (await call('GET', '/api/state')).me;
  check(!(me?.workspaces || []).length, 'alice: no organisation (freelancer)');

  const w = await boot({user: 'alice', hash: 'cal', ls: {'tasks.calMode': '"month"'}}), d = w.document;
  await until(() => w.eval(`typeof evPop === 'function' && typeof evCalsModal === 'function' && typeof calEvState === 'function'`));
  wrap(w);
  const chip = t => d.querySelector(`#view .cev[title=${JSON.stringify(t)}]`);
  check(await until(() => chip('Standup')), 'the month shows the event');

  // ================= #6159: the popover loads with the shared block; a failed load says so
  w.__hold = new RegExp(`^GET /api/events/${SU.id}$`);
  click(w, chip('Standup'));
  let ld = await until(() => d.querySelector('#pop .evpop .eload'));
  check(ld && ld.getAttribute('role') === 'status' && /Loading…/.test(txt(ld)), '#6159: the popover says "Loading…" with the shared block ' + txt(ld));
  w.__hold = null; w.__held.splice(0).forEach(h => h.go());
  check(await until(() => d.querySelector('#pop [data-evp="edit"]')), 'loaded: the popover has its actions');
  w.eval('closePop()');
  w.__fail = new RegExp(`^GET /api/events/${SU.id}$`);
  click(w, chip('Standup'));
  const pe = await until(() => d.querySelector('#pop .evpop .eerr'));
  check(pe && /The event could not be loaded/.test(txt(pe)) && pe.querySelector('[data-esretry]') && !d.querySelector('#pop').classList.contains('hidden'),
    '#6159: a failed load stays open and says so with "Try again" (it closed without a word) ' + txt(pe));
  w.__fail = null;
  click(w, pe.querySelector('[data-esretry]'));
  check(await until(() => d.querySelector('#pop [data-evp="edit"]') && /Standup/.test(txt(d.querySelector('#pop')))), '#6159: "Try again" opens the event');
  w.eval('closePop()');

  // ================= #6159: deleting goes into the history: Ctrl+Z takes it back
  const items = async () => (await call('GET', `/api/events?from=${D0}&to=${D0}`)).items || [];
  let n0 = w.eval('HIST.undo.length');
  w.eval(`evDelete(${JSON.stringify(await call('GET', `/api/events/${PI.id}`))}, null)`);
  check(await until(async () => !(await items()).some(x => x.title === 'Tuning the piano')), 'a single event is deleted');
  check(await histAdded(w, n0), '#6159: deleting an event is a step of the history');
  check(/Tuning the piano/.test(w.eval('HIST.undo[HIST.undo.length - 1].label')), '#6159: the step names the event ' + w.eval('HIST.undo[HIST.undo.length - 1]?.label'));
  ctrlZ(w);
  check(await until(async () => (await items()).some(x => x.title === 'Tuning the piano')), '#6159: Ctrl+Z brings the event back');
  check(await until(() => chip('Tuning the piano')), '#6159: and into the month');
  // a date of a series ("Only this date")
  n0 = w.eval('HIST.undo.length');
  const occ = `${D0}T18:00`;
  w.eval(`evDelete(${JSON.stringify(await call('GET', `/api/events/${SE.id}`))}, ${JSON.stringify(occ)})`);
  const q = await until(() => d.querySelector('.modal.cdlg.evscope [data-sc="one"]'));
  click(w, q);
  check(await until(async () => (await call('GET', `/api/events/${SE.id}`)).exdates?.includes(occ)), 'only this date is left out');
  check(await histAdded(w, n0), '#6159: removing one date of a series is a step of the history');
  await until(() => !d.querySelector('.modal'));
  ctrlZ(w);
  check(await until(async () => !(await call('GET', `/api/events/${SE.id}`)).exdates?.length), '#6159: Ctrl+Z brings the date back');
  // a calendar (from the Calendars window; Ctrl+Z works once the window is closed)
  w.eval('evCalsModal()');
  let md = await until(() => d.querySelector(`.modal.evcmodal [data-evcmenu="${CH.id}"]`) && d.querySelector('.modal.evcmodal'));
  // the trash row is the last one of the window, after the subscriptions and the holidays
  const body = md.querySelector('#evc-body'), last = body?.lastElementChild;
  check(last && (last.matches('.evctrbtn') || last.closest('.evctrbtn')), '#6159: the trash is the last row of the Calendars window ' + (last?.className || '-'));
  click(w, md.querySelector('[data-evc="lists"]'));
  const cvf = await until(() => md.querySelector('.cvflists'));
  check(cvf && ![...cvf.querySelectorAll('[style]')].some(x => /padding|flex/.test(x.getAttribute('style'))), '#6159: the "Per project" rows have no inline padding / flex');
  n0 = w.eval('HIST.undo.length');
  click(w, md.querySelector(`[data-evcmenu="${CH.id}"]`));
  await until(() => [...d.querySelectorAll('#pop [role="menuitem"]')].some(b => /Delete/.test(b.textContent)));
  click(w, [...d.querySelectorAll('#pop [role="menuitem"]')].find(b => /Delete/.test(b.textContent)));
  click(w, await until(() => d.querySelector('.modal.cdlg [data-cd="yes"]')));
  check(await until(async () => !(await call('GET', '/api/evcals')).items?.some(c => c.id === CH.id)), 'the calendar is deleted');
  check(await histAdded(w, n0), '#6159: deleting a calendar is a step of the history');
  closeAll(d);
  ctrlZ(w);
  check(await until(async () => (await call('GET', '/api/evcals')).items?.some(c => c.id === CH.id)), '#6159: Ctrl+Z brings the calendar back');

  // ================= #6159: the subscription link window
  w.__fail = new RegExp(`^GET /api/evcals/${W.id}/feed$`);
  w.eval(`evf_modal(evCal(${W.id}))`);
  md = await until(() => d.querySelector('.modal.evfmodal'));
  const fe = await until(() => md.querySelector('#evf-body .eerr'));
  check(fe && /The subscription link could not be loaded/.test(txt(fe)) && !/Only available online/.test(txt(md)) && fe.querySelector('[data-esretry]'),
    '#6159: a failed load says what failed with "Try again" ' + txt(fe));
  w.__fail = null;
  click(w, fe.querySelector('[data-esretry]'));
  check(await until(() => md.querySelector('[data-evf="create"]')), '#6159: "Try again" loads it');
  closeAll(d);

  // ================= #6159: the people of the editor
  w.eval('EVU = null');
  w.__fail = /^GET \/api\/users/;
  w.eval(`evEditor({start: '${D0}T13:00', end: '${D0}T14:00'})`);
  md = await until(() => d.querySelector('.modal.evmodal #ev-attin') && d.querySelector('.modal.evmodal'));
  check(/People could not be loaded/.test(md.querySelector('#ev-attin').placeholder), '#6159: the people field says they could not be loaded ' + md.querySelector('#ev-attin').placeholder);
  check(w.eval('EVU') === null, '#6159: the failure is not kept as "nobody" (the next dialog asks again)');
  w.__fail = null;
  closeAll(d);
  check((await w.eval('evPeople()')).length === 0 && w.eval('Array.isArray(EVU)'), 'the next try loads them');

  // ================= #6159: the later dates of repeating tasks
  w.__fail = /^GET \/api\/occurrences/;
  w.eval(`S.occ = {key: '', items: [], want: ''}; renderView()`);
  const oe = await until(() => d.querySelector('#view .calst .eerr'));
  check(oe && /Repeating tasks could not be loaded/.test(txt(oe)), '#6159: the calendar says the repeating tasks could not be loaded ' + txt(oe));
  const nOcc = () => w.__log.filter(k => /^GET \/api\/occurrences/.test(k)).length, o1 = nOcc();
  w.eval('renderView(); renderView(); renderView()'); await sleep(300);
  check(nOcc() === o1, '#6159: drawing again does not fetch again by itself (no loop) ' + (nOcc() - o1));
  w.__fail = null;
  click(w, oe.querySelector('[data-esretry]'));
  check(await until(() => !d.querySelector('#view .calst') && w.eval('!!S.occ.key')), '#6159: "Try again" loads them, the hint goes');

  // ================= #6159: what failed first, the server's text in brackets
  check(/^Could not sync \(HTTP 404\)/.test(txt(new w.DOMParser().parseFromString(w.eval(`calStatus({status: 'error', error_text: 'HTTP 404'})`), 'text/html').body)),
    '#6159: a subscription\'s sync error names what failed first');
  w.__fail = /^POST \/api\/events$/;
  w.eval(`evEditor({start: '${D0}T13:00', end: '${D0}T14:00'})`);
  md = await until(() => d.querySelector('.modal.evmodal #ev-title') && d.querySelector('.modal.evmodal'));
  md.querySelector('#ev-title').value = 'Refused one';
  click(w, md.querySelector('[data-evm="save"]'));
  const se = await until(() => d.querySelector('.modal.evmodal .evsaveerr'));
  check(se && /^The event was not saved \(Refused for the test\)/.test(txt(se)), '#6159: a refused save: what failed first ' + txt(se));
  w.__fail = null;
  closeAll(d);

  // ================= #6158: the time zone at the times
  const NY = await call('POST', '/api/events', {title: 'Call with sales New York', cal_id: W.id, start: `${D0}T10:00`, end: `${D0}T11:00`, tz: 'America/New_York', reminders: []});
  check(NY.id, 'set-up: an event in New York');
  w.eval('calInvalidate(); renderView()');
  check(await until(() => chip('Call with sales New York')), 'the month shows it');
  click(w, chip('Call with sales New York'));
  let when = await until(() => d.querySelector('#pop [data-evp="edit"]') && d.querySelector('#pop .cevm'));
  check(when && /10:00\D.*11:00\D* New York · \S.* your time/.test(txt(when)), '#6158: the popover names the zone at the times and the time for you ' + txt(when));
  w.eval('closePop()');
  click(w, chip('Standup'));
  when = await until(() => d.querySelector('#pop [data-evp="edit"]') && d.querySelector('#pop .cevm'));
  check(when && !/your time/.test(txt(when)), '#6158: an event in the device\'s zone: no zone ' + txt(when));
  w.eval('closePop()');
  w.eval(`evEditor({ev: ${JSON.stringify(await call('GET', `/api/events/${NY.id}`))}})`);
  md = await until(() => d.querySelector('.modal.evmodal #ev-tzh-s:not([hidden])') && d.querySelector('.modal.evmodal'));
  check(md && /^New York · \S.* your time$/.test(txt(md.querySelector('#ev-tzh-s'))) && txt(md.querySelector('#ev-tzh-e')) === 'New York',
    '#6158: the editor names the zone next to Starts / Ends ' + txt(md?.querySelector('#ev-tzh-s')) + ' | ' + txt(md?.querySelector('#ev-tzh-e')));
  check(md && !md.querySelector('details.evmore #ev-tzh-s') && md.querySelector('#ev-tzh-s').closest('.evdt'), '#6158: in the rows of the times, not under "More options"');
  const tzIn = md.querySelector('#ev-tz'); tzIn.value = w.eval('evTz()'); tzIn.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(await until(() => md.querySelector('#ev-tzh-s').hidden && md.querySelector('#ev-tzh-e').hidden), '#6158: the device\'s zone chosen: the hint goes');
  closeAll(d);
  // the task an event prepares, not in memory
  const L = (await call('GET', '/api/state')).lists.find(l => l.is_inbox) || (await call('GET', '/api/state')).lists[0];
  const T = await call('POST', '/api/tasks', {title: 'Equipment list', list_id: L.id});
  const PR = await call('POST', '/api/events', {title: 'Shooting day', cal_id: W.id, start: `${D0}T07:00`, end: `${D0}T08:00`, task_id: T.id, reminders: []});
  check(T.id && PR.id && PR.task_id === T.id, 'set-up: an event that prepares a task');
  w.eval(`S.tasks.delete(${T.id}); calInvalidate(); renderView()`);
  check(await until(() => chip('Shooting day')) && !w.eval(`!!taskById(${T.id})`), 'the task is not in memory');
  w.eval(`evEditor({ev: ${JSON.stringify(await call('GET', `/api/events/${PR.id}`))}})`);
  md = await until(() => d.querySelector('.modal.evmodal .evprep') && d.querySelector('.modal.evmodal'));
  const prep = md?.querySelector('.evprep');
  check(prep && !prep.closest('details') && !md.querySelector('details.evmore').open, '#6158: the task stands in the editor outside "More options" (closed)');
  check(await until(() => /Equipment list/.test(txt(md.querySelector('.evprepn')))), '#6158: its title is fetched ' + txt(md.querySelector('.evprepn')));
  closeAll(d);
  w.eval(`S.tasks.delete(${T.id})`);
  click(w, chip('Shooting day'));
  const pt = await until(() => d.querySelector('#pop [data-evp="task"]'));
  check(pt && /Preparation: Equipment list/.test(txt(pt)), '#6158: the popover names the task also when it was not in memory ' + txt(pt));
  click(w, pt);
  check(await until(() => w.eval(`S.sel === ${T.id}`) && !d.querySelector('#detail').classList.contains('hidden')), '#6158: and opens it');
  w.eval("typeof closeDetail === 'function' && closeDetail()");
  // an own series: the repeat mark (not the subscription's)
  const rc = await until(() => chip('Rehearsal'));
  check(rc && rc.querySelector('.cevrep[aria-label="Repeats"]') && !rc.querySelector('[aria-label="Subscribed calendar"]'), '#6158: an own series carries the repeat mark');
  check(!chip('Standup').querySelector('.cevsub'), 'a single own event: no mark');
  // no availability bar on an existing event without guests
  w.eval(`evEditor({ev: ${JSON.stringify(await call('GET', `/api/events/${SU.id}`))}})`);
  md = await until(() => d.querySelector('.modal.evmodal #ev-atts') && d.querySelector('.modal.evmodal'));
  await until(() => w.eval(`typeof efb_draw === 'function'`)); await idle(w);
  check(!md.querySelector('#ev-fb'), '#6158: an existing event without guests: no availability bar');
  closeAll(d);
  // the Calendars window: the line of a shared calendar
  const bob = await call('POST', '/api/users', {username: 'bob', display_name: 'Bob', password: 'password123'});
  const carol = await call('POST', '/api/users', {username: 'carol', display_name: 'Carol', password: 'password123'});
  check((await call('PUT', `/api/evcals/${W.id}/members`, {user_id: bob.id, role: 'view'})).http < 300 && (await call('PUT', `/api/evcals/${W.id}/members`, {user_id: carol.id, role: 'edit'})).http < 300, 'set-up: Work shared with two people');
  await w.eval('load()');
  w.eval('evCalsModal()');
  md = await until(() => d.querySelector(`.modal.evcmodal [data-evcmenu="${W.id}"]`) && d.querySelector('.modal.evcmodal'));
  const wrow = md.querySelector(`[data-evcmenu="${W.id}"]`).closest('.evcrow');
  check(txt(wrow.querySelector('.evcnm')) === 'Work' && /shared with 2 people/.test(txt(wrow.querySelector('.evcsub'))), '#6158: the name and below it "shared with 2 people" ' + txt(wrow));
  closeAll(d);

  // ================= #6156: the Share dialog on the shared frame
  const mems = async () => Object.fromEntries(((await call('GET', '/api/evcals')).items.find(c => c.id === W.id)?.members || []).map(m => [m.user_id, m.role]));
  check(await call('DELETE', `/api/evcals/${W.id}/members/${carol.id}`).then(r => r.http < 300), 'set-up: Carol out again');
  await w.eval('load()');
  w.eval('evCalsModal()');
  md = await until(() => d.querySelector(`.modal.evcmodal [data-evcmenu="${W.id}"]`) && d.querySelector('.modal.evcmodal'));
  click(w, md.querySelector(`[data-evcmenu="${W.id}"]`));
  await until(() => [...d.querySelectorAll('#pop [role="menuitem"]')].some(b => /Share/.test(b.textContent)));
  click(w, [...d.querySelectorAll('#pop [role="menuitem"]')].find(b => /Share/.test(b.textContent)));
  let sm = await until(() => d.querySelector(`.modal.evsmodal .mrow[data-uid="${bob.id}"]`) && d.querySelector('.modal.evsmodal'));
  check(sm && sm.querySelector('.lhdr [data-m="close"][aria-label="Close"]') && txt(sm.querySelector('.foot .btn.pri')) === 'Done' && /Share Work/.test(txt(sm.querySelector('.lhdr h3'))),
    '#6156: the shared frame: title, X on top, "Done"');
  check(/Alice/.test(txt(sm.querySelector('.mrow.evsowner'))) && /Owner/.test(txt(sm.querySelector('.mrow.evsowner'))), '#6156: the owner first');
  const bsel = sm.querySelector(`.mrow[data-uid="${bob.id}"] select`);
  check(/Bob/.test(txt(sm.querySelector(`.mrow[data-uid="${bob.id}"] .n`))) && bsel.selectedOptions[0].text === 'Read-only' && [...bsel.options].map(o => o.text).join('|') === 'Member|Read-only',
    '#6156: Bob with the role words of projects (only Member / Read-only) ' + [...bsel.options].map(o => o.text).join('|'));
  check(!/can view|can edit/.test(txt(sm)), '#6156: no own role words');
  // add Carol as a member
  const us = sm.querySelector('#evs-user'); us.value = String(carol.id); us.dispatchEvent(new w.Event('change', {bubbles: true}));
  check(sm.querySelector('#evs-role').value === 'edit', 'the role of a new person: Member');
  click(w, sm.querySelector('[data-evs="add"]'));
  check(await until(async () => (await mems())[carol.id] === 'edit'), '#6156: Carol shared as a member');
  check(await until(() => { const t = d.querySelector('#toast'); return t && !t.classList.contains('hidden') && /^Shared/.test(txt(t)); }), '#6156: "Shared" as the feedback');
  check(await until(() => sm.querySelector(`.mrow[data-uid="${carol.id}"] select`)?.value === 'edit'), '#6156: her row with "Member"');
  // take Bob out: no question, Undo puts him back as Read-only
  n0 = w.eval('HIST.undo.length');
  click(w, sm.querySelector(`[data-evsrm="${bob.id}"]`));
  check(await until(async () => !(bob.id in await mems())), '#6156: Bob taken out');
  check(!d.querySelector('.modal.cdlg'), '#6156: without a question');
  check(!sm.querySelector(`.mrow[data-uid="${bob.id}"]`), '#6156: his row left the dialog');
  check(await undoToast(w, 'Stopped sharing with Bob'), '#6156: the toast offers Undo');
  check(await until(async () => (await mems())[bob.id] === 'view'), '#6156: Undo puts the share back with its role (Read-only)');
  check(await until(() => sm.querySelector(`.mrow[data-uid="${bob.id}"] select`)?.value === 'view'), '#6156: and his row into the dialog');
  // again, and Ctrl+Z (the dialog closed)
  n0 = w.eval('HIST.undo.length');
  click(w, sm.querySelector(`[data-evsrm="${bob.id}"]`));
  check(await until(async () => !(bob.id in await mems())), 'Bob taken out again');
  check(await histAdded(w, n0), '#6156: taking a person out is a step of the history');
  closeAll(d);
  ctrlZ(w);
  check(await until(async () => (await mems())[bob.id] === 'view'), '#6156: Ctrl+Z puts the share back');
  // the people could not be loaded: said so, no names "?"
  w.eval('EVU = null');
  w.__fail = /^GET \/api\/users/;
  w.eval(`evPeople().then(u => evShareModal(evCal(${W.id}), u, () => {}))`);
  sm = await until(() => d.querySelector('.modal.evsmodal #evs-members .eerr') && d.querySelector('.modal.evsmodal'));
  check(sm && /The people could not be loaded/.test(txt(sm.querySelector('.eerr'))) && !/\?/.test(txt(sm.querySelector('#evs-members'))), '#6156: the people that could not be loaded say so (no "?") ' + txt(sm?.querySelector('#evs-members')));
  w.__fail = null;
  click(w, sm.querySelector('[data-esretry]'));
  check(await until(() => /Bob/.test(txt(sm.querySelector(`.mrow[data-uid="${bob.id}"]`)))), '#6156: "Try again" loads them, the names show');
  closeAll(d);

  // ================= #6159: the view choice is a named group
  const seg = d.querySelector('#view .calbar .seg');
  check(seg && seg.getAttribute('role') === 'group' && seg.getAttribute('aria-label') === 'View', '#6159: the view choice is a group with a name');

  w.close();
  console.log(`p21212_a_cal_ui: ${ok} ok, ${F.length} failed`);
  process.exit(F.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
