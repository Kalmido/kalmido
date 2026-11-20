// @ts-check
/* 2.392.0 D (#3369): the view "Waiting for me" (#mine_wait): everything that waits for me over every workspace, from GET
   /api/inbox (agents/waiting.py). The sidebar row counts all of it, the card in Today (agents.js, waitCard) links here
   instead of repeating it.
   (#7538) A way to work through it: a row opens its entry in the view itself (the jump to the target stays as a link in the
   entry); the entry shows what the decision needs and the buttons the target has (a job's Approve / Reject, an approval card
   without a step, a review, the yes to a one-way step, Confirm as an order / Reject of #7528). After a decision - here, on
   the target or on another device - the next entry of the same group opens by itself (mwLoad: the open entry left the list),
   at the end "Nothing waits for you any more". Phone first: the entry fills the screen, Back / Next as buttons, skipping
   without a decision. A computer: the list on the left, the entry on the right. Keys over the one key registry (keys.js):
   j / k next and back, y / n only where the entry has exactly these two answers (never the yes to a one-way step, never
   anything that needs a text). No new kind of decision and no new access: only the existing calls. */
const MW_GROUPS = [['job', N_('Jobs')], ['approval', N_('Approvals')], ['question', N_('Questions')] /* (#7530): agents' questions with a bound step */, ['confirm', N_('Orders to confirm')], ['gate', N_('Merge and deploy requests')], ['review', N_('Reviews')],
  ['blocked', N_('Blocked')], ['irreversible', N_('One-way steps without a yes')], ['parked', N_('Parked')],
  ['watch', N_('Stalled jobs and stranded branches')]];  // (#3365): parked; (#3366): the watchdog's findings; (#7538): confirm (#7528)
S.mw = {items: null, counts: {}, total: 0, at: 0, sel: null, done: false, /** @type {Record<string, any>} */ tk: {}, /** @type {Record<string, any>} */ ch: {},
  busy: false, mine: 0, /** @type {any} */ gone: null};  // reader F1 (job/6017): a decision running, my own decision's time, an entry decided elsewhere
const mwKey = x => x.kind + ':' + x.id;
// the entries in the order the view shows them (by group, within a group as the server sends them: confirm by sender)
const mwFlat = (items = S.mw.items) => MW_GROUPS.flatMap(([k]) => (items || []).filter(x => x.kind === k));
const mwSelItem = () => S.mw.sel ? mwFlat().find(x => mwKey(x) === S.mw.sel) || null : null;
// (#7538): the open entry left the list. After my own decision (here or on its target, within the minute): the next one after
// it in the old order, the same group first because the order is by group; none after it: the first one left; none at all:
// done. Decided elsewhere (another device, another decider) - reader F1 (job/6017), "a calm view": the entry stays, marked
// "Already decided elsewhere", without its buttons and keys, until the person goes on with Next
function mwFollow(old, items) {
  if (!S.mw.sel || (S.mw.gone && S.mw.sel === mwKey(S.mw.gone.x))) return;
  const keys = new Set(items.map(mwKey));
  if (keys.has(S.mw.sel)) return;
  const i = old.findIndex(x => mwKey(x) === S.mw.sel), after = old.slice(i + 1).find(x => keys.has(mwKey(x)));
  const nx = after || mwFlat(items)[0];
  if (i >= 0 && !(Date.now() - S.mw.mine < 60000)) { S.mw.gone = {x: old[i], next: nx ? mwKey(nx) : null}; return; }
  S.mw.mine = 0;
  S.mw.sel = nx ? mwKey(nx) : null;
  S.mw.done = !nx;
}
// the open entry: one of the list, or the one decided elsewhere that is still shown
const mwCur = () => mwSelItem() || (S.mw.gone && S.mw.sel === mwKey(S.mw.gone.x) ? S.mw.gone.x : null);
// one decision at a time (a held or doubled key, a second click): the next starts only after the answer
async function mwDecide(/** @type {() => any} */ fn) {
  if (S.mw.busy) return;
  S.mw.busy = true; S.mw.mine = Date.now();
  try { await fn(); } finally { S.mw.busy = false; }
}
async function mwLoad(force = false) {
  if (!force && Date.now() - S.mw.at < 60000) return;
  S.mw.at = Date.now();
  let j; try { j = await api('GET', '/api/inbox'); } catch { return; }  // offline: the last answer stays
  const sig = x => (x || []).map(i => i.kind + i.id).join();
  const same = S.mw.items && sig(S.mw.items) === sig(j.items), old = mwFlat();
  S.mw = {...S.mw, items: j.items || [], counts: j.counts || {}, total: j.total || 0};
  mwFollow(old, S.mw.items);
  if (same || !S.booted) return;
  renderSide();
  if (S.route.mod === 'tasks' && (S.route.key === 'mine_wait' || S.route.key === 'today')) renderView();
}
const mwCount = () => S.mw.total;
const mwToDo = () => S.mw.total - (S.mw.counts.blocked || 0) - (S.mw.counts.parked || 0);  // what only I can settle: my blocked tasks are in the briefing already, parked ones wait on purpose
// a list with the lock: the server holds ciphertexts, the app opens the task's title where it has the key
function mwTitle(x) {
  const t = x.task_id && taskById(x.task_id), own = x.title && !le2eIs(x.title) ? x.title : '';
  if (own) return own;
  if (t?.title && !le2u_locked(t)) return t.title;
  return x.task_title && !le2eIs(x.task_title) ? x.task_title : tr('Encrypted task');
}
const mwHref = x => x.kind === 'watch' && x.job_id ? `#job/${+x.job_id}` : x.kind === 'job' && !x.task_id ? '#agents' : x.task_id ? `#t/${x.task_id}` : '';
function mwSub(x) {
  const tt = x.task_title && !le2eIs(x.task_title) ? x.task_title : '', title = mwTitle(x);
  return [x.agent_name, x.list_name, x.task_id && tt !== title ? `#${x.task_id} ${tt}` : '', x.kind === 'parked' ? x.why : '',
    x.kind === 'watch' ? (x.finding === 'branch_stranded' ? tr('Branch without a merge: {0}', x.branch || '') : tr('No progress')) : ''].filter(Boolean).join(' · ');
}
// (#7538): a row opens its entry here (data-mw="open"); a waiting job keeps its buttons in the row
function mwRow(x) {
  const k = mwKey(x), on = S.mw.sel === k;
  const body = `<span class="wci"><b>${esc(mwTitle(x))}</b><span class="muted">${esc(mwSub(x))}</span></span>`;
  const btn = `<button type="button" class="mwa" data-mw="open" data-k="${esc(k)}"${on ? ' aria-current="true"' : ''}>${body}</button>`;
  if (x.kind === 'job') return `<div class="wcrow${on ? ' on' : ''}">${/*html-ok*/ btn /* built above with esc() */}<div class="wcb">${waitJobBtns({id: x.id, kind: x.proposal})}</div></div>`;
  return `<div class="wcrow${on ? ' on' : ''}">${/*html-ok*/ btn /* built above with esc() */}</div>`;
}
function mwList() {
  return MW_GROUPS.map(([k, name]) => {
    const xs = S.mw.items.filter(x => x.kind === k);
    return xs.length ? `<section class="waitcard mwg" aria-label="${esc(tr(name))}"><h3>${esc(tr(name))} <span class="muted">${xs.length}</span></h3>${xs.map(mwRow).join('')}</section>` : '';
  }).join('');
}
const mwWide = () => !isMobile();
function viewMineWait() {
  if (S.mw.items === null) { mwLoad(true); return `<div class="mwv"><div class="empty">${esc(tr('Loading…'))}</div></div>`; }
  if (!S.mw.items.length && !mwCur()) return `<div class="mwv">${/*html-ok*/ symEmpty('done', S.mw.done ? tr('Nothing waits for you any more') : tr('Nothing waits for you')) /* render.js escapes inside */}</div>`;
  if (mwWide() && !mwCur() && S.mw.items.length) S.mw.sel = mwKey(mwFlat()[0]);  // a computer: the list on the left, the first entry open on the right
  const x = mwCur();
  if (!mwWide()) return x ? `<div class="mwv mwone">${/*html-ok*/ mwPanel(x) /* escaped inside */}</div>` : `<div class="mwv">${/*html-ok*/ mwList() /* escaped inside */}</div>`;
  return `<div class="mwv mwsplit"><div class="mwl">${/*html-ok*/ mwList() /* escaped inside */}</div>${/*html-ok*/ gcol_html('mw-list') /* the grip's fixed markup (render.js) */}<div class="mwr">${/*html-ok*/ x ? mwPanel(x) : '' /* escaped inside */}</div></div>`;
}

// ---- (#7538) the entry
// the task behind an entry as the server has it now (GET /api/tasks/<id>): the text a confirmation goes to (#7528)
async function mwTask(id) {
  if (S.mw.tk[id] !== undefined) return;
  S.mw.tk[id] = null;
  try { S.mw.tk[id] = await rawFetch('GET', `/api/tasks/${id}`); } catch { S.mw.tk[id] = false; }
  mwRedraw();
}
// the buttons of an approval card in a comment (GET /api/comments/<id>/choice); a chat card opens the chat
async function mwChoice(cid) {
  if (S.mw.ch[cid] !== undefined) return;
  S.mw.ch[cid] = null;
  try { S.mw.ch[cid] = await api('GET', `/api/comments/${cid}/choice`); } catch { S.mw.ch[cid] = false; }
  mwRedraw();
}
const mwRedraw = () => { if (S.route.mod === 'tasks' && S.route.key === 'mine_wait') renderView(); };
// an approval card answered right here: no step behind it (a step's yes needs the server's description of it, #6450: that
// stays on the card) and exactly the answers yes / no
const mwYesNo = ch => !!ch && ch.choice_state === 'open' && !!ch.choices?.approval && !ch.choices.approval.step
  && (ch.choices.choices || []).map(c => c.id).sort().join() === 'no,yes';
const mwLocked = t => !t || le2eIs(t.title) || le2eIs(t.content);
// the two answers a key may give: {yes, no} or null (never a one-way yes, never one that needs a text)
function mwKeys(x) {
  if (!mwSelItem() || mwKey(x) !== S.mw.sel) return null;  // decided elsewhere: no answer any more
  if (x.kind === 'job' && !x.proposal) return {yes: () => jobDo(x.id, 'approve'), no: () => jobDo(x.id, 'reject')};
  if (x.kind === 'approval' && x.source === 'comment' && mwYesNo(S.mw.ch[x.id])) return {yes: () => mwAnswer(x.id, 'yes'), no: () => mwAnswer(x.id, 'no')};
  if (x.kind === 'review' && taskById(x.task_id)) return {yes: () => mwReview(x.task_id, 'approve'), no: () => mwReview(x.task_id, 'changes')};
  return null;
}
function mwActs(x) {
  const b = (a, h, pri = false) => `<button type="button" class="btn${pri ? ' pri' : ''}" data-mw="${/*html-ok*/ a /* a fixed action name of this file */}" data-k="${esc(mwKey(x))}">${/*html-ok*/ h /* the callers pass esc() / icons */}</button>`;
  if (x.kind === 'job') return waitJobBtns({id: x.id, kind: x.proposal});
  if (x.kind === 'approval' && x.source === 'comment') {
    const ch = S.mw.ch[x.id];
    if (ch === undefined) mwChoice(x.id);
    if (mwYesNo(ch)) return b('ap-yes', `${thumbIc(true)} ${esc(tr('Yes, go ahead'))}`, true) + b('ap-no', `${thumbIc(false)} ${esc(tr('No'))}`);
    return ch ? `<span class="muted">${esc(tr('Answer it on its card: it shows what Yes does'))}</span>` : '';
  }
  if (x.kind === 'review' && taskById(x.task_id)) return b('rv-yes', `${thumbIc(true)} ${esc(tr('Approve'))}`, true) + b('rv-no', `${thumbIc(false)} ${esc(tr('Back|review'))}`);
  if (x.kind === 'irreversible') return b('ow-yes', esc(tr('Yes to the one-way step')));
  if (x.kind === 'confirm') {
    const t = S.mw.tk[x.task_id];
    if (!t || mwLocked(t)) return t === false || (t && mwLocked(t)) ? `<span class="muted">${esc(tr('Open the task to confirm it'))}</span>` : '';
    if (navigator.onLine === false) return `<span class="muted">${esc(tr('Only online'))}</span>`;
    return b('cf-yes', `${ic('check', 's')} ${esc(tr('Confirm as an order'))}`, true) + b('cf-no', esc(tr('Reject…|order')));
  }
  return '';
}
function mwPanel(x) {
  const gone = !mwSelItem(), nxk = gone ? S.mw.gone?.next : null;
  const all = mwFlat(), i = all.findIndex(y => mwKey(y) === mwKey(x)), grp = MW_GROUPS.find(([k]) => k === x.kind);
  const href = mwHref(x), keys = mwKeys(x);
  if (x.task_id && (x.kind === 'confirm' || x.kind === 'irreversible')) mwTask(x.task_id);
  const t = x.task_id ? S.mw.tk[x.task_id] : null;
  // the text the decision is about: a confirmation goes to exactly this title and description (#7528)
  const text = x.kind === 'confirm' && t ? (mwLocked(t) ? `<p class="muted">${esc(tr('Encrypted task'))}</p>` : `<div class="mwtx"><b>${esc(t.title || '')}</b>${t.content ? `<div class="mwtxc">${esc(t.content)}</div>` : ''}</div>`)
    : x.kind === 'confirm' && t === null ? `<div class="empty">${esc(tr('Loading…'))}</div>` : '';
  const why = (x.kind === 'irreversible' || x.kind === 'parked') && x.why ? `<p class="mwwhy">${esc(x.why)}</p>` : '';
  const go = x.source === 'chat' ? `<button type="button" class="linkbtn" data-act="chat-open" data-aid="${x.agent_id}">${esc(tr('Open the chat'))}</button>`
    : href ? `<a class="linkbtn mwgo" href="${esc(href)}">${esc(tr('Open the target'))}</a>` : '';
  const nav = `<div class="mwpn">${mwWide() ? '' : `<button type="button" class="btn" data-mw="list">${ic('list', 's')} ${esc(tr('List'))}</button>`}
    <span class="spacer"></span><button type="button" class="btn" data-mw="prev" ${i <= 0 ? 'disabled' : ''} title="k">${esc(tr('Back'))}</button>
    <button type="button" class="btn${gone ? ' pri' : ''}" data-mw="next" ${(gone ? !nxk : i >= all.length - 1) ? 'disabled' : ''} title="j">${esc(gone ? tr('Next') : tr('Skip'))}</button></div>`;
  return `<section class="mwp" aria-label="${esc(mwTitle(x))}" data-k="${esc(mwKey(x))}">
    <div class="mwph muted">${esc(tr(grp ? grp[1] : ''))}${gone ? '' : ` · ${esc(tr('{0} of {1}', i + 1, all.length))}`}</div>
    <h2 class="mwpt">${esc(mwTitle(x))}</h2><div class="muted mwps">${esc(mwSub(x))}</div>${/*html-ok*/ why /* esc() above */}${/*html-ok*/ text /* esc() above */}
    <div class="mwpb">${/*html-ok*/ gone ? `<p class="muted mwdone" role="status">${esc(tr('Already decided elsewhere'))}</p>` : mwActs(x) /* escaped inside */}</div>${keys ? `<div class="mwpk muted">${esc(tr('Keys: y yes, n no, j next, k back'))}</div>` : ''}
    <div class="mwpg">${/*html-ok*/ go /* esc() above */}</div>${/*html-ok*/ nav /* esc() above */}</section>`;
}
function mwGo(d) {
  if (S.mw.gone && S.mw.sel === mwKey(S.mw.gone.x)) {  // decided elsewhere: Next goes on to the entry that followed it
    if (d < 0) return false;
    const nk = S.mw.gone.next; S.mw.gone = null; S.mw.sel = nk; S.mw.done = !nk; mwRedraw(); return true;
  }
  const all = mwFlat(), i = all.findIndex(y => mwKey(y) === S.mw.sel), nx = all[i + d];
  if (!nx) return false;
  S.mw.sel = mwKey(nx); S.mw.done = false; mwRedraw();
  $('#view .mwp')?.focus?.({preventScroll: true});
  return true;
}
// after a decision: the list again from the server; the entry left it, so mwFollow opens the next one
async function mwSettled() { S.mw.at = 0; await mwLoad(true); mwRedraw(); }
async function mwAnswer(cid, id) {
  try { await api('POST', `/api/comments/${cid}/choice`, {choice_ids: [id]}); } catch { delete S.mw.ch[cid]; mwRedraw(); return; }
  delete S.mw.ch[cid]; await mwSettled();
}
async function mwReview(tid, act) { await rvw_do(tid, act); await mwSettled(); }
async function mwOneway(tid) {
  try { await api('POST', `/api/tasks/${tid}/irreversible-yes`); } catch { return; }
  await mwSettled();
}
// (#7528): the yes goes to the title and description shown in the entry (in the server's form); changed since: 409, the
// entry fetches the task again and shows the new text
async function mwConfirm(tid) {
  const t = S.mw.tk[tid]; if (!t || mwLocked(t)) return;
  try { await api('POST', `/api/tasks/${tid}/confirm`, {title: t.title ?? '', content: t.content ?? null}); }
  catch { delete S.mw.tk[tid]; mwRedraw(); return; }
  delete S.mw.tk[tid]; toast(tr('Confirmed as an order')); await mwSettled();
}
async function mwReject(tid) {
  const v = await cf_reason(S.mw.tk[tid] || taskById(tid)); if (v === null) return;  // oneway.js: a reason, none in a list with the lock
  try { await api('POST', `/api/tasks/${tid}/reject`, v ? {reason: v} : {}); } catch { return; }
  delete S.mw.tk[tid]; toast(tr('Rejected: closed as won’t do')); await mwSettled();
}
document.addEventListener('click', e => {
  if (/** @type {any} */ (e.target).closest?.('.mwp [data-act="job-do"], .mwp [data-act="prop-open"]')) S.mw.mine = Date.now();  // my decision on a job: the next entry follows
  const b = /** @type {any} */ (e.target).closest?.('[data-mw]'); if (!b || !b.closest('.mwv')) return;
  const a = b.dataset.mw, x = b.dataset.k ? mwFlat().find(y => mwKey(y) === b.dataset.k) : mwSelItem();
  if (a === 'open') { S.mw.sel = b.dataset.k; S.mw.done = false; S.mw.gone = null; mwRedraw(); return; }
  if (a === 'list') { S.mw.sel = null; S.mw.gone = null; mwRedraw(); return; }
  if (a === 'next' || a === 'prev') { mwGo(a === 'next' ? 1 : -1); return; }
  if (!x || b.disabled || S.mw.busy) return;
  b.disabled = true;
  mwDecide({'ap-yes': () => mwAnswer(x.id, 'yes'), 'ap-no': () => mwAnswer(x.id, 'no'), 'rv-yes': () => mwReview(x.task_id, 'approve'),
    'rv-no': () => mwReview(x.task_id, 'changes'), 'ow-yes': () => mwOneway(x.task_id), 'cf-yes': () => mwConfirm(x.task_id),
    'cf-no': () => mwReject(x.task_id)}[a] || (() => {}));
});
// (#7538): the keys of the view (keys.js; not while typing, an open dialog keeps them): only on "Waiting for me" with an entry open
domReady(() => {
  const here = () => S.route?.mod === 'tasks' && S.route.key === 'mine_wait' && !!mwCur();
  kb_on('view:tasks', 'j', e => here() ? (e.repeat || mwGo(1), true) : false, {help: N_('Waiting for me: next entry'), group: 'Waiting for me'});
  kb_on('view:tasks', 'k', e => here() ? (e.repeat || mwGo(-1), true) : false, {help: N_('Waiting for me: entry before'), group: 'Waiting for me'});
  // reader F1 (job/6017): a held key (repeat) and a key while a decision runs do nothing; an entry decided elsewhere has no answer
  const ans = (/** @type {'yes'|'no'} */ w) => (/** @type {KeyboardEvent} */ e) => {
    if (!here()) return false;
    if (e.repeat || S.mw.busy) return true;
    const k = mwKeys(/** @type {any} */ (mwCur())); if (!k) return !mwSelItem();  // decided elsewhere: the key is taken, nothing happens
    mwDecide(k[w]); return true;
  };
  kb_on('view:tasks', 'y', ans('yes'), {help: N_('Waiting for me: yes (only where an entry has exactly yes and no)'), group: 'Waiting for me'});
  kb_on('view:tasks', 'n', ans('no'), {help: N_('Waiting for me: no (only where an entry has exactly yes and no)'), group: 'Waiting for me'});
});
