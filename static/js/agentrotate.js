// @ts-check
/* Kalmido web client: the agent runtime section "Interim summary" (2.233.0 B, #3189): when the agent's host ends a chat
   conversation with a summary and starts a fresh one (session size, runs, minutes of pause, the daily summary time =
   runtime nightly_reset). Kalmido only stores it (GET /api/v1/agent "runtime"); every field saves at once. Shown in the
   admin's agent dialog (agentchat.js, below "Runtime") and in the permissions dialog of a personal agent (settings.js).
   base = /api/admin/agents/<id> or /api/my/agents/<id>.
   2.396.0 A (#3386): below it the block "Git author": name + mail the host sets for the agent's commits (empty = the neutral
   default) and whether it appends a Co-Authored-By line; saved at once like the fields above.
   2.481.0 (#3662): below it "Work the list off": the starter's mechanical dispatcher (mcp/agent_dispatch.py) off, as a dry
   run or on (runtime.dispatch); which lists and how is the project's KALMIDO-DISPATCH.json on the agent's computer.
   2.974.0 (#5668) / 2.992.0 (#5684): the section "Model" (the model per run: decisions, reviews, routine; the usage per kind of
   the last 7 days); the chat header's "runs with …" opens it as a dialog of its own (agm_open).
   2.1394.0 (#7031): "Jobs on its computer": model and effort for build jobs and review jobs (runtime model_job / effort_job /
   model_audit / effort_audit), in the admin's and the owner's dialog, saved at once.
   #7368: every model field is a real choice (agms_html: Agent default, Fable, Opus, Sonnet, Haiku, Other … with a free field),
   ONE list for the section Model, the admin's Runtime (agentchat.js) and "Jobs on its computer"; next to every model field
   of the section Model the effort of that kind of run (runtime effort / effort_decide / effort_review / effort_routine). */
'use strict';

const AGZ_SIZES = [['small', N_('Small'), '0.4 MB'], ['medium', N_('Medium'), '0.8 MB'], ['large', N_('Large'), '1.5 MB']];
// the section; own = also its own time field (the admin dialog already has #ag-nr: agz_wire moves it in here)
/** @param {any} a @param {boolean} [own] */
function agz_html(a, own) {
  if (!a) return '';
  const rt = a.runtime || {}, size = rt.rotate_size || 'medium', idle = rt.rotate_idle_min ?? 45;
  return `<div class="agzsec" data-agz="${a.id}"><h4 id="agz-h">${tr('Interim summary')}</h4>
    <div class="shint">${tr('The agent then starts a new conversation with a summary of the previous one: this saves cost, but it can forget details. Its host applies it.')}</div>
    <div class="row"><label for="agz-size">${tr('Session size')}</label><select id="agz-size" data-agzk="rotate_size">${AGZ_SIZES.map(([k, n, mb]) => `<option value="${k}" ${size === k ? 'selected' : ''}>${esc(tr(n))} (${mb})</option>`).join('')}</select></div>
    <div class="row"><label for="agz-runs">${tr('After messages')}</label><input id="agz-runs" class="numin" data-agzk="rotate_runs" type="number" min="10" max="500" step="1" inputmode="numeric" value="${rt.rotate_runs ?? 60}"></div>
    <div class="row"><label for="agz-idle">${tr('After a pause of')}</label><span class="agpct"><input id="agz-idle" class="numin" data-agzk="rotate_idle_min" type="number" min="0" max="1440" step="1" inputmode="numeric" value="${idle}"><span class="muted">${tr('min')}</span></span></div>
    <div class="shint">${tr('Pause: 0 = never; it counts only from the small size on.')}</div>
    ${own ? `<div class="row agznr"><label>${tr('Daily summary')}</label>${timeIn('agz-nr', rt.nightly_reset || '', {label: tr('Daily summary'), empty: tr('Agent default')})}</div>` : '<div class="agznr-slot"></div>'}</div>${agg_html(a)}${agd_html(a)}${/*html-ok*/ agj_html(a)}${/*html-ok*/ own ? agm_html(a) : ''}`;  // 2.974.0 (#5668): agm_html escapes its values
}
// #7368: the one list of models of every model field (short name = the stored value, the server keeps it in lower case;
// the names are product names, not translated); "Other …" opens a free field for any other model id
const AG_MODEL_CHOICES = [['fable', 'Fable'], ['opus', 'Opus'], ['sonnet', 'Sonnet'], ['haiku', 'Haiku']];
const AGMS_OTHER = '__other';
// a model field: the choice (#<id>-sel) and the free field #<id> that holds the value (read by the dialogs and the autosave,
// data-agzk = its runtime key); the free field shows only with "Other …" (also for a stored name not in the list)
/** @param {string} id @param {string} v @param {string} [k] @param {string} [ph] @param {string} [label] */
function agms_html(id, v, k, ph, label) {
  v = String(v || '').trim();
  const lv = v.toLowerCase(), known = !v || AG_MODEL_CHOICES.some(([m]) => m === lv), cur = !v ? '' : known ? lv : AGMS_OTHER;
  const opts = [['', ph || tr('Agent default')], ...AG_MODEL_CHOICES, [AGMS_OTHER, tr('Other …')]]
    .map(([val, txt]) => `<option value="${esc(val)}" ${cur === val ? 'selected' : ''}>${esc(txt)}</option>`).join('');
  return `<span class="agms"><select id="${esc(id)}-sel" class="agms-sel"${label ? ` aria-label="${esc(label)}"` : ''}>${/*html-ok*/ opts}</select>`  // opts: options built with esc() above
    + `<input id="${esc(id)}"${k ? ` data-agzk="${esc(k)}"` : ''} value="${esc(known ? lv : v)}" maxlength="100" placeholder="${esc(tr('Model name'))}" aria-label="${esc(tr('Model name'))}" autocomplete="off" autocapitalize="off" spellcheck="false" ${cur === AGMS_OTHER ? '' : 'hidden'}></span>`;
}
// the choice changes: a listed model (or the default) goes into the free field, which then saves like a typed value
// (its own change event: the sections' autosave and the admin dialog's OK read the free field); "Other …" shows the free
// field with the value so far, to type a new name
/** @param {any} sel */
function agms_pick(sel) {
  const inp = sel.parentElement?.querySelector('input'); if (!inp) return;
  if (sel.value === AGMS_OTHER) { inp.hidden = false; inp.focus(); inp.select?.(); return; }  // the value stays until a new one is typed
  inp.hidden = true;
  if (inp.value === sel.value) return;
  inp.value = sel.value;
  inp.dispatchEvent(new Event('change', {bubbles: true}));
}
// the choice follows the free field (after a save, a refused save, a typed short name)
/** @param {any} inp */
function agms_sync(inp) {
  const sel = inp?.parentElement?.querySelector('select.agms-sel'); if (!sel) return;
  const lv = String(inp.value || '').trim().toLowerCase(), known = !lv || AG_MODEL_CHOICES.some(([m]) => m === lv);
  if (known) inp.value = lv;
  sel.value = known ? lv : AGMS_OTHER;
  inp.hidden = known;
}
document.addEventListener('change', e => { const t = /** @type {any} */ (e.target); if (t?.classList?.contains('agms-sel')) agms_pick(t); });
// #7368: the effort next to a model field (the values of the jobs' effort, AGJ_EFFORTS); ph = the text of "empty"
/** @param {string} id @param {string} k @param {any} rt @param {string} label @param {string} [ph] @param {boolean} [noKey] */
function agme_html(id, k, rt, label, ph, noKey) {
  const v = String((rt || {})[k] || '');
  return `<span class="agme"><span class="muted" aria-hidden="true">${esc(tr('Effort'))}</span><select id="${esc(id)}"${noKey ? '' : ` data-agzk="${esc(k)}"`} aria-label="${esc(label)}">${AGJ_EFFORTS.map(([e, n]) =>
    `<option value="${esc(e)}" ${v === e ? 'selected' : ''}>${esc(e ? tr(n) : ph || tr(n))}</option>`).join('')}</select></span>`;
}
// 2.974.0 (#5668): the model and the model per run in the owner's dialog of a personal agent (the admin dialog has them in
// "Runtime", agentchat.js agSplitFields); saved at once like the fields above. 2.992.0 (#5684): a third model for reviews
// (empty = the first) and the usage per kind of the last 7 days below them (agmu_load); the same section is the dialog the
// chat header opens (agm_open)
/** @param {any} a */
function agm_html(a) {
  const rt = a.runtime || {}, on = !!rt.model_split, like = tr('Like messages and decisions');
  /** #7368: the model choice and its effort in one row @param {string} id @param {string} k @param {string} ek @param {string} lbl @param {string} [ph] */
  const mrow = (id, k, ek, lbl, ph) => `<div class="agmsw">${/*html-ok*/ agms_html(id, rt[k], k, ph, lbl)}${/*html-ok*/ agme_html(id + '-eff', ek, rt, tr('Effort') + ': ' + lbl, ph)}</div>`;
  return `<div class="agzsec agzmod" data-agz="${esc(String(a.id))}"><h4 id="agm-h">${tr('Model')}</h4>
    <div class="row"><label for="agm-model-sel">${tr('Model')}</label>${/*html-ok*/ mrow('agm-model', 'model', 'effort', tr('Model'))}</div>
    <label class="chkl swl"><span class="swc"><input type="checkbox" role="switch" id="agm-split" data-agzk="model_split" ${on ? 'checked' : ''}><span class="swt" aria-hidden="true"></span></span><span>${tr('Select the model per run')}</span></label>
    <div class="row agm-r" ${on ? '' : 'hidden'}><label for="agm-dec-sel">${tr('For your messages and decisions')}</label>${/*html-ok*/ mrow('agm-dec', 'model_decide', 'effort_decide', tr('For your messages and decisions'))}</div>
    <div class="row agm-r" ${on ? '' : 'hidden'}><label for="agm-rev-sel">${tr('For reviews')}</label>${/*html-ok*/ mrow('agm-rev', 'model_review', 'effort_review', tr('For reviews'), like)}</div>
    <div class="row agm-r" ${on ? '' : 'hidden'}><label for="agm-rou-sel">${tr('For routine')}</label>${/*html-ok*/ mrow('agm-rou', 'model_routine', 'effort_routine', tr('For routine'))}</div>
    <div class="shint agm-r" ${on ? '' : 'hidden'}>${tr('Your messages, buttons, reactions and comments and every run that may need a decision use the first model; reviews (a review you ask it for, a planned job of the kind Review, a scheduled check of a project) the second, empty = the first; quiet wake-ups, new tasks, follow-ups and planned jobs without a warning sign the third. When in doubt the first.')}</div>
    <div class="agmu agm-r" aria-live="polite" ${on ? '' : 'hidden'}></div></div>`;
}
// 2.992.0 (#5684): the usage per kind of run of the last 7 days (GET <base>/model-usage): runs, tokens, the costs only when
// its computer reports them (nothing estimated)
const AGM_CLASSES = {decide: N_('Messages and decisions'), review: N_('Reviews'), routine: N_('Routine'), '': N_('Without a kind')};
/** @param {any} box @param {string} base */
async function agmu_load(box, base) {
  if (!box) return;
  /** @type {any} */
  let j; try { j = await api('GET', `${base}/model-usage`); } catch { box.textContent = ''; return; }
  if (!box.isConnected) return;
  const any = (j.classes || []).some((/** @type {any} */ x) => x.calls);
  box.innerHTML = `<div class="lbl">${esc(tr('Last 7 days'))}</div>` + (any ? `<ul class="agmul">${(j.classes || []).map((/** @type {any} */ x) =>
    `<li data-cls="${esc(x.run_class)}"><span class="agmuk">${esc(tr(AGM_CLASSES[x.run_class] || AGM_CLASSES['']))}</span><span class="muted">${esc([
      tr('Runs: {0}', String(x.runs)), tr('{0} tokens', fmtTok(x.tokens)), ...j.cost && x.cost != null ? [fmtUsd(x.cost)] : []].join(' · '))}</span></li>`).join('')}</ul>`
    : `<div class="muted">${esc(tr('No usage reported yet'))}</div>`)
    + (j.cost ? '' : `<div class="shint">${esc(tr('Its computer reports no costs: runs and tokens only.'))}</div>`);
}
// the section's autosave (the owner's permissions dialog and the header's dialog); base = /api/admin/agents/<id> or /api/my/agents/<id>
/** @param {any} mod @param {any} a @param {string} base */
function agm_wire(mod, a, base) {
  if (!mod) return;
  mod.addEventListener('change', async (/** @type {any} */ e) => {
    const el = e.target, k = el.dataset.agzk; if (!k) return;
    const rt = a.runtime || (a.runtime = {}), v = k === 'model_split' ? !!el.checked : String(el.value).trim();
    /** @param {boolean} on */
    const show = on => $$('.agm-r', mod).forEach((/** @type {any} */ x) => { x.hidden = !on; });
    if (k === 'model_split') show(!!v);
    try {
      const r = await api('PATCH', base, {runtime: {[k]: v}});
      if (r?.runtime) a.runtime = r.runtime;
      if (k !== 'model_split') { el.value = (r?.runtime || {})[k] ?? v; agms_sync(el); }  // #7368: "Fable" comes back as "fable"
      else agm_headSync(a.id, !!v);
      savedTick(agms_tickEl(el));
    } catch {
      if (k === 'model_split') { el.checked = !!rt[k]; show(!!rt[k]); } else { el.value = rt[k] || ''; agms_sync(el); }
    }
  });
  agmu_load($('.agmu', mod), base);
}
// #7368: the tick of a saved model shows at its choice while the free field is hidden
/** @param {any} el */
function agms_tickEl(el) { return el?.hidden && el.parentElement?.querySelector('select.agms-sel') || el; }
// the open chat of this agent follows the switch at once (the header's "runs with …")
/** @param {number} id @param {boolean} on */
function agm_headSync(id, on) {
  const ag = typeof agentById === 'function' ? agentById(id) : null;
  if (!ag) return;
  ag.model_split = on;
  if (typeof chatHeadSync === 'function') chatHeadSync(ag, true);
}
// 2.992.0 (#5684): the tap on "runs with …" in the chat header: the section Model of this agent in a dialog of its own (its
// owner: the personal agent; an admin: any agent)
/** @param {any} ag */
async function agm_open(ag) {
  if ((ag?.server || ag?.provider === 'kalmido-server') && typeof srv_modelModal === 'function') { srv_modelModal(ag); return; }  // 2.1044.0 (#5824): its model lives in the server settings
  const own = !!ag.owner_id && ag.owner_id === S.me?.id, base = own ? `/api/my/agents/${ag.id}` : `/api/admin/agents/${ag.id}`;
  /** @type {any} */
  let a; try { a = ((await api('GET', own ? '/api/my/agents' : '/api/admin/agents')).agents || []).find((/** @type {any} */ x) => x.id === ag.id); } catch { return; }
  if (!a) return;
  /** @type {any} */
  const md = modal(`<h3>${esc(tr('Model of {0}', a.name))}</h3>${/*html-ok*/ agm_html(a)}<div class="foot"><span class="spacer"></span><button class="btn" data-m="close">${tr('Close')}</button></div>`);
  agm_wire($('.agzmod', md), a, base);
  $('[data-m="close"]', md)?.addEventListener('click', () => md.remove());
}
// 2.396.0 A (#3386): the git author block (same section style, same autosave in agz_wire)
const AGG_DEFAULT = ['Kalmido', 'noreply@kalmido.com'];
const AGG_MAIL = /^[^@\s<>,]{1,100}@[^@\s<>,]{1,100}\.[^@\s<>,]{1,60}$/;
/** @param {any} a */
function agg_html(a) {
  const rt = a.runtime || {};
  return `<div class="agzsec agzgit" data-agz="${a.id}"><h4 id="agg-h">${tr('Git author')}</h4>
    <div class="shint">${tr('Appears publicly in GitHub with every commit of this agent.')}</div>
    <div class="row"><label for="agg-name">${tr('Name')}</label><input id="agg-name" data-agzk="git_author_name" maxlength="100" autocomplete="off" value="${esc(rt.git_author_name || '')}" placeholder="${AGG_DEFAULT[0]}"></div>
    <div class="row"><label for="agg-mail">${tr('E-mail')}</label><input id="agg-mail" data-agzk="git_author_email" type="email" maxlength="200" autocomplete="off" autocapitalize="off" spellcheck="false" value="${esc(rt.git_author_email || '')}" placeholder="${AGG_DEFAULT[1]}" aria-describedby="agg-err"></div>
    <div class="calerr" role="alert" id="agg-err" hidden></div>
    <label class="chkl swl"><span class="swc"><input type="checkbox" role="switch" id="agg-co" data-agzk="git_coauthor" ${rt.git_coauthor ? 'checked' : ''}><span class="swt" aria-hidden="true"></span></span><span>${tr('Append Co-Authored-By')}</span></label>
    <div class="shint">${tr('Empty = {0}. A project with a repository can set its own author.', esc(AGG_DEFAULT[0] + ' <' + AGG_DEFAULT[1] + '>'))}</div></div>`;
}
// 2.481.0 (#3662): the dispatcher switch (same section style, saved at once)
const AGD_MODES = [['', N_('Off')], ['dry', N_('Dry run')], ['on', N_('Active')]];
/** @param {any} a */
function agd_html(a) {
  const v = (a.runtime || {}).dispatch || '';
  return `<div class="agzsec agzdisp" data-agz="${a.id}"><h4 id="agd-h">${tr('Work the list off')}</h4>
    <div class="shint">${tr('The agent works the lists named on its computer off one after the other: it starts the next job when a place is free and closes tasks once they are built. Dry run = it only reports what it would do.')}</div>
    <div class="shint">${tr('It builds only tasks you wrote yourself in the app or with your own token, never tasks of other members or tasks from a webhook, an e-mail, a form or an import; comments of others reach the job only as information, never as an order.')} ${esc(tr('Once somebody else changes the title or notes of such a task, the agent leaves it until you change them yourself.'))}</div>
    <div class="row"><label for="agd-mode">${tr('Mode')}</label><select id="agd-mode" data-agzk="dispatch">${AGD_MODES.map(([k, n]) => `<option value="${k}" ${v === k ? 'selected' : ''}>${esc(tr(n))}</option>`).join('')}</select></div></div>`;
}
// 2.1394.0 (#7031): model and effort per kind of job (a build job, a read-only review job) its host starts with agent_job.py;
// empty = the agent's default; saved at once like the sections above
const AGJ_EFFORTS = [['', N_('Agent default')], ['low', N_('Low')], ['medium', N_('Medium')], ['high', N_('High')], ['xhigh', N_('Extra high')], ['max', N_('Maximum')]];
/** @param {any} a */
function agj_html(a) {
  const rt = a.runtime || {};
  /** #7368: the shared model choice @param {string} id @param {string} k @param {string} lbl */
  const mi = (id, k, lbl) => agms_html(id, rt[k], k, '', lbl);
  /** @param {string} id @param {string} k */
  const ei = (id, k) => `<select id="${esc(id)}" data-agzk="${esc(k)}">${AGJ_EFFORTS.map(([v, n]) => `<option value="${esc(v)}" ${(rt[k] || '') === v ? 'selected' : ''}>${esc(tr(n))}</option>`).join('')}</select>`;
  return `<div class="agzsec agzjob" data-agz="${esc(String(a.id))}"><h4 id="agj-h">${tr('Jobs on its computer')}</h4>
    <div class="shint">${tr('Long work the agent starts as a job: a build or a read-only review. Empty = the agent’s default; the effort applies to Claude Code only.')}</div>
    <div class="row"><label for="agj-model-sel">${tr('Model for build jobs')}</label>${/*html-ok*/ mi('agj-model', 'model_job', tr('Model for build jobs'))}</div>
    <div class="row"><label for="agj-effort">${tr('Effort for build jobs')}</label>${/*html-ok*/ ei('agj-effort', 'effort_job')}</div>
    <div class="row"><label for="agj-amodel-sel">${tr('Model for review jobs')}</label>${/*html-ok*/ mi('agj-amodel', 'model_audit', tr('Model for review jobs'))}</div>
    <div class="row"><label for="agj-aeffort">${tr('Effort for review jobs')}</label>${/*html-ok*/ ei('agj-aeffort', 'effort_audit')}</div></div>`;
}
/** @type {Record<string, number[]>} */
const AGZ_RANGE = {rotate_runs: [10, 500], rotate_idle_min: [5, 1440]};
// autosave of the section's fields; in the admin dialog the existing "Nightly fresh restart" row moves in as "Daily summary"
/** @param {any} md @param {any} a @param {string} base */
function agz_wire(md, a, base) {
  const sec = a && $(`.agzsec[data-agz="${a.id}"]`, md); if (!sec) return;
  const git = $(`.agzgit[data-agz="${a.id}"]`, md);  // 2.396.0 A (#3386): its own section element, the same autosave
  if (git) git.addEventListener('change', (/** @type {any} */ e) => agg_save(md, a, base, e.target));
  const disp = $(`.agzdisp[data-agz="${a.id}"]`, md);  // 2.481.0 (#3662)
  if (disp) disp.addEventListener('change', async (/** @type {any} */ e) => {
    const el = e.target; if (el.dataset.agzk !== 'dispatch') return;
    try {
      const r = await api('PATCH', base, {runtime: {dispatch: el.value}});
      if (r?.runtime) a.runtime = r.runtime;
      savedTick(el);
    } catch { el.value = (a.runtime || {}).dispatch || ''; /* api() said it */ }
  });
  const job = $(`.agzjob[data-agz="${a.id}"]`, md);  // 2.1394.0 (#7031): model / effort per kind of job
  if (job) job.addEventListener('change', async (/** @type {any} */ e) => {
    const el = e.target, k = el.dataset.agzk; if (!k) return;
    const v = String(el.value).trim();
    try {
      const r = await api('PATCH', base, {runtime: {[k]: v}});
      if (r?.runtime) a.runtime = r.runtime;
      el.value = (r?.runtime || {})[k] ?? v;
      agms_sync(el);  // #7368: the choice follows (a model field; an effort select has none)
      savedTick(agms_tickEl(el));
    } catch { el.value = (a.runtime || {})[k] || ''; agms_sync(el); /* api() said it */ }
  });
  agm_wire($(`.agzmod[data-agz="${a.id}"]`, md), a, base);  // 2.974.0 (#5668), 2.992.0 (#5684): agm_wire
  const slot = $('.agznr-slot', sec), nr = slot && $('#ag-nr', md)?.closest('.row');
  if (nr) { const l = $('label', nr); if (l) l.textContent = tr('Daily summary'); slot.replaceWith(nr); nr.classList.add('agznr'); }
  sec.addEventListener('change', async (/** @type {any} */ e) => {
    const el = e.target, k = el.dataset.agzk || (['ag-nr', 'agz-nr'].includes(el.id) ? 'nightly_reset' : ''); if (!k) return;
    const rt = a.runtime || (a.runtime = {});
    const raw = String(el.value);
    /** @type {string | number} */
    let v = raw;
    if (AGZ_RANGE[k]) {
      const [lo, hi] = AGZ_RANGE[k], n = +raw;
      if (!/^\d+$/.test(raw) || !((n >= lo && n <= hi) || (k === 'rotate_idle_min' && n === 0))) {
        toast(k === 'rotate_runs' ? tr('Messages: a number from {0} to {1}', lo, hi) : tr('Pause: 0 or {0} to {1} minutes', lo, hi));
        el.value = rt[k] ?? ''; return;
      }
      v = n;
    }
    try {
      const r = await api('PATCH', base, {runtime: {[k]: v}});
      if (r?.runtime) a.runtime = r.runtime;
      savedTick(el.type === 'hidden' ? $(`[data-dpfor="${el.id}"]`, md) || el : el);
    } catch { if (el.type !== 'hidden') el.value = rt[k] ?? ''; /* api() said it */ }
  });
}
// 2.396.0 A (#3386): saves one git author field; an invalid mail = the error at the field, nothing saved
/** @param {any} md @param {any} a @param {string} base @param {any} el */
async function agg_save(md, a, base, el) {
  const k = el.dataset.agzk; if (!k) return;
  const rt = a.runtime || (a.runtime = {}), err = $('#agg-err', md);
  const v = k === 'git_coauthor' ? !!el.checked : String(el.value).trim();
  const bad = k === 'git_author_email' && v && !AGG_MAIL.test(String(v)) ? tr('Git author: please enter a valid e-mail address')
    : k === 'git_author_name' && /[<>]/.test(String(v)) ? tr('Invalid value: {0}', tr('Name')) : '';
  if (err) { err.textContent = bad; err.hidden = !bad; }
  el.setAttribute('aria-invalid', bad ? 'true' : 'false');
  if (bad) return;
  try {
    const r = await api('PATCH', base, {runtime: {[k]: v}});
    if (r?.runtime) a.runtime = r.runtime;
    if (k !== 'git_coauthor') el.value = v;
    savedTick(el);
  } catch (e) {
    if (err && e?.status === 400) { err.textContent = e.message; err.hidden = false; }
    if (k === 'git_coauthor') el.checked = !!rt[k]; else el.value = rt[k] ?? '';
  }
}
