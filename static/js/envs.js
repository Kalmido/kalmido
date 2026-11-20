/* Kalmido web client: Environments of a project (Staging, Live, ...).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';

// ------------------------------------------------------------------ 2.60.0 D (#1514)
// Which milestone / version runs in which environment since when. Shown at the milestone (task panel), in the "Milestones"
// block of the project page (where environments are created, renamed, deleted and the deploy webhook is switched on),
// in the roadmap (a small text at the milestone) and at the milestone's tasks ("Live since 15.10."). The milestones in
// /api/state carry `envs` [{name, since, version}] (where they run NOW), the environment list comes from
// GET /api/lists/<id>/envs. Set by hand (milestone panel), by API (set_deployment) or by the deploy webhook.
const ENV = {d: {}};
async function env_load(lid, force) {
  const d = ENV.d[lid] || (ENV.d[lid] = {});
  if (d.busy || (!force && d.j && d.v === S.v)) return;
  d.busy = true;
  try { d.j = await rawFetch('GET', `/api/lists/${lid}/envs`); d.err = ''; }
  catch (e) { if (e.message === 'auth') return; d.err = e instanceof Offline ? 'offline' : e.message; }
  finally { d.busy = false; d.v = S.v; }
  if (routeList()?.id === lid && typeof isOverview === 'function' && isOverview()) viewSafeRender();
  else if (S.sel && S.tasks.get(S.sel)?.list_id === lid) renderDetail();
}
function env_row(e, can) {
  const c = e.current;
  const now = c ? `${esc(c.milestone || c.version)}${c.milestone && c.version && c.version !== c.milestone ? ' (' + esc(c.version) + ')' : ''} <span class="muted">· ${esc(tr('since {0}', env_day(c.at)))}</span>` : `<span class="muted">${esc(tr('Nothing put here yet'))}</span>`;
  return `<div class="envrow"><b class="envn">${esc(e.name)}</b><span class="envnow">${now}</span>${can ? `<button type="button" class="btn sm" data-env="set" data-id="${e.id}">${esc(tr('Put here…'))}</button><button type="button" class="iconbtn" data-env="edit" data-id="${e.id}" title="${esc(tr('Edit'))}" aria-label="${esc(tr('Edit'))}">${ic('edit', 's')}</button>` : ''}</div>`;
}
function env_ovHtml(l, can, hasMs = true) {  // inside the "Milestones" block of the project page
  const d = ENV.d[l.id];
  if (!d || (!d.busy && d.v !== S.v)) setTimeout(() => env_load(l.id), 0);
  const j = d?.j;
  if (!hasMs && !j?.envs?.length) return '';  // 2.60.0 (#1514, #1061): an empty Milestones block stays one line
  if (!j) return d?.err ? '' : `<div class="muted envbox">${esc(tr('Loading…'))}</div>`;
  const rows = j.envs.map(e => env_row(e, can)).join('');
  const sug = can && l.ptype === 'software' ? j.suggest.filter(n => !j.envs.some(e => e.name.toLowerCase() === n.toLowerCase())) : [];
  const add = can && j.envs.length < j.max ? `<div class="envadd">${sug.map(n => `<button type="button" class="btn sm" data-env="add" data-name="${esc(n)}">${ic('plus', 's')}<span>${esc(n)}</span></button>`).join('')}<button type="button" class="btn sm" data-env="add">${ic('plus', 's')}<span>${esc(tr('Add environment'))}</span></button></div>` : '';
  if (!rows && !add) return '';
  return `<div class="envbox" id="pov-envs"><h4>${esc(tr('Environments'))}</h4>${rows || `<div class="muted">${esc(tr('Where does a version run? Add Staging, Live and put milestones there.'))}</div>`}${add}</div>`;
}
// the milestone's own panel: where it runs and, for editors, the buttons to put it on an environment
function env_msHtml(t, rep) {
  const d = ENV.d[t.list_id];
  if (!d || (!d.busy && d.v !== S.v)) setTimeout(() => env_load(t.list_id), 0);
  const envs = d?.j?.envs || [], can = canEditList(t.list_id);
  const on = rep?.envs || [];
  if (!on.length && !envs.length) return '';
  const rows = envs.map(e => {
    const here = on.find(x => x.name === e.name);
    return `<div class="envrow"><b class="envn">${esc(e.name)}</b><span class="envnow">${here ? esc(tr('since {0}', env_day(here.since))) : `<span class="muted">${esc(tr('not here'))}</span>`}</span>${can && !here ? `<button type="button" class="btn sm" data-env="deploy" data-id="${e.id}" data-ms="${t.id}">${esc(tr('Put on {0}', e.name))}</button>` : ''}</div>`;
  }).join('');
  return `<h6>${esc(tr('Environments'))}</h6><div class="envbox">${rows}</div>`;
}
async function env_deploy(eid, body, name) {
  let r;
  try { r = await api('POST', `/api/envs/${eid}/deploy`, body); } catch { return; }
  histAdd({label: tr('Put on {0}', name),
    undo: async () => { await api('DELETE', `/api/envs/${eid}/deploys/${r.id}`); env_refresh(); },
    redo: async () => { r = await api('POST', `/api/envs/${eid}/deploy`, body); env_refresh(); }});
  toast(r.closed?.length ? tr('Put on {0}; {1} tasks completed', name, r.closed.length) : tr('Put on {0}', name));
  env_refresh();
}
async function env_refresh() {
  S.msr = null;
  for (const k of Object.keys(ENV.d)) ENV.d[k].v = -1;
  try { await load(); } catch { /* offline */ }
  render();
}
function env_setModal(l, e) {
  const ms = msOfList(l.id);
  const md = modal(`<h3>${esc(tr('Put on {0}', e.name))}</h3>
    <div class="row"><label for="env-ms">${tr('Milestone')}</label><select id="env-ms"><option value="">${esc(tr('None (version only)'))}</option>${ms.map(m => `<option value="${m.id}">${esc(m.title)}</option>`).join('')}</select></div>
    <div class="row"><label for="env-ver">${tr('Version')}</label><input id="env-ver" maxlength="100" placeholder="${esc(tr('e.g. 2.60.0'))}" autocomplete="off"></div>
    <p class="muted">${esc(tr('The time is now. Without a milestone the version is found by the milestone titles.'))}</p>
    <div class="foot"><span class="spacer"></span><button class="btn" data-m="close">${tr('Cancel')}</button><button class="btn pri" data-m="save">${tr('Save')}</button></div>`);
  md.addEventListener('click', async ev => {
    const b = ev.target.closest('[data-m]'); if (!b) return;
    if (b.dataset.m === 'close') { md.remove(); return; }
    const mid = +$('#env-ms', md).value || null, ver = $('#env-ver', md).value.trim();
    if (!mid && !ver) { toast(tr('Select a milestone or enter a version')); return; }
    md.remove();
    await env_deploy(e.id, {...(mid ? {milestone_id: mid} : {}), ...(ver ? {version: ver} : {})}, e.name);
  });
}
function env_editModal(l, e, j) {
  const md = modal(`<h3>${esc(tr('Environment'))}</h3>
    <div class="row"><label for="env-name">${tr('Name')}</label><input id="env-name" maxlength="40" value="${esc(e?.name || '')}" placeholder="${esc(tr('e.g. Staging'))}" autocomplete="off"></div>
    <div class="row"><label class="chkl"><input type="checkbox" id="env-close" ${e?.auto_close ? 'checked' : ''}> <span>${esc(tr('Complete the open tasks of a milestone when it arrives here'))}</span></label></div>
    <div class="row"><label class="chkl"><input type="checkbox" id="env-acc" ${e?.acceptance_task ? 'checked' : ''}> <span>${esc(tr('Create a task to accept each new version'))}</span></label></div>
    ${e && j.manage ? `<div class="row envhook"><label>${esc(tr('Deploy webhook'))}</label><div><span class="muted">${esc(e.hook ? tr('On: your deploy script posts the version to a secret address.') : tr('Off'))}</span>
      <div class="envhb"><button type="button" class="btn sm" data-m="hook" data-how="${e.hook ? 'rotate' : 'on'}">${esc(e.hook ? tr('New address') : tr('Switch on'))}</button>${e.hook ? `<button type="button" class="btn sm" data-m="hook" data-how="off">${esc(tr('Switch off'))}</button>` : ''}</div>
      <div id="env-url"></div></div></div>` : ''}
    <div class="foot">${e ? `<button class="btn danger" data-m="del">${tr('Remove')}</button>` : ''}<span class="spacer"></span><button class="btn" data-m="close">${tr('Cancel')}</button><button class="btn pri" data-m="save">${tr('Save')}</button></div>`);
  md.addEventListener('click', async ev => {
    const b = ev.target.closest('[data-m]'); if (!b) return;
    const m = b.dataset.m;
    if (m === 'close') { md.remove(); return; }
    try {
      if (m === 'hook') {
        const r = await api('PATCH', `/api/envs/${e.id}`, {hook: b.dataset.how});
        $('#env-url', md).innerHTML = r.url ? `<p class="muted">${esc(tr('Shown only once. POST {"version": "2.60.0"} to it.'))}</p><input readonly id="env-urlin" value="${esc(r.url)}" aria-label="${esc(tr('Deploy webhook'))}"><button type="button" class="btn sm" data-m="copy">${ic('copy', 's')}<span>${tr('Copy')}</span></button>` : '';
        env_load(l.id, true); return;
      }
      if (m === 'copy') { try { await navigator.clipboard.writeText($('#env-urlin', md).value); toast(tr('Copied')); } catch { toast(tr('Copy failed')); } return; }
      if (m === 'del') {
        await api('DELETE', `/api/envs/${e.id}`); md.remove();
        histAdd({label: tr('Environment removed'), srv: true, undo: async () => { await api('POST', `/api/envs/${e.id}/restore`); env_load(l.id, true); },
          redo: async () => { await api('DELETE', `/api/envs/${e.id}`); env_load(l.id, true); }});
        env_load(l.id, true); toast(tr('Environment removed')); return;
      }
      const name = $('#env-name', md).value.trim(), ac = $('#env-close', md).checked, at = $('#env-acc', md).checked;
      if (!name) { toast(tr('Enter a name')); return; }
      if (e) {
        const before = {name: e.name, auto_close: e.auto_close, acceptance_task: e.acceptance_task};
        await api('PATCH', `/api/envs/${e.id}`, {name, auto_close: ac, acceptance_task: at});
        const put = x => async () => { await api('PATCH', `/api/envs/${e.id}`, x); env_load(l.id, true); };
        histAdd({label: tr('Environment changed'), srv: true, undo: put(before), redo: put({name, auto_close: ac, acceptance_task: at})});
      } else {
        let r = await api('POST', `/api/lists/${l.id}/envs`, {name, auto_close: ac, acceptance_task: at});
        histAdd({label: tr('Environment added'), undo: async () => { await api('DELETE', `/api/envs/${r.id}`); env_load(l.id, true); },
          redo: async () => { await api('POST', `/api/envs/${r.id}/restore`); env_load(l.id, true); }});
      }
      md.remove(); env_load(l.id, true);
    } catch { /* api() said it */ }
  });
  setTimeout(() => focusIfKeyboard($('#env-name', md)), 30);  // 2.655.0 (#5081): was !isMobile()
}
document.addEventListener('click', async ev => {
  const b = ev.target.closest('[data-env]'); if (!b) return;
  const id = +b.dataset.id, l = routeList(), tl = S.sel ? listById(S.tasks.get(S.sel)?.list_id) : null;
  const lst = b.dataset.env === 'deploy' ? tl : (l || tl);
  const j = ENV.d[lst?.id]?.j, e = j?.envs.find(x => x.id === id);
  switch (b.dataset.env) {
    case 'add': if (lst && j) { env_editModal(lst, null, j); if (b.dataset.name) $('#env-name').value = b.dataset.name; } break;
    case 'edit': if (e) env_editModal(lst, e, j); break;
    case 'set': if (e) env_setModal(lst, e); break;
    case 'deploy': if (e) env_deploy(e.id, {milestone_id: +b.dataset.ms}, e.name); break;
  }
});

// ------------------------------------------------------------------ (#7537) the stage line of a task
// On top of a task's panel, in a project with a repository or environments: one line of stages - created, in progress, built
// (in the default branch), released (version), every environment of the project in its order (Staging, Live ...), done or
// rejected - the reached ones ticked, the current (last reached) one stressed. Everything is read from what is there (column
// meaning sk_task, code.build of the repository, a milestone's environments or an environment's current version equal to the
// task's version, the delivery state, the reopen lines of the history); nothing is stored and nobody sets it by hand. At the
// current stage: parked / waiting with its reason, "2× back" (reopened twice) and with whom the task lies now. A phone shows
// the current stage written out and the others as dots; a tap opens every stage with its date.
const STL_CSS = `.stl{margin:.1rem 0 .35rem;font-size:var(--fs-s)}.stl>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:center;gap:.15rem .3rem}
.stl>summary::-webkit-details-marker{display:none}.stl .stl-s{display:inline-flex;align-items:center;gap:.2rem;color:var(--muted)}
.stl .stl-s.d{color:var(--text2)}.stl .stl-s.c{color:var(--accent);font-weight:600}.stl .stl-s.c.bad{color:var(--danger)}
.stl .stl-x{color:var(--muted)}.stl .stl-ex{color:var(--st-wait-t);font-weight:400}.stl .stl-dot{width:.45rem;height:.45rem;border-radius:50%;background:var(--bg4)}
.stl .stl-s.d .stl-dot{background:var(--muted)}.stl .stl-s.c .stl-dot{background:var(--accent)}.stl ol{margin:.3rem 0 0;padding-left:1.2rem}
.stl li.o{color:var(--muted)}@media (max-width:640px){.stl .stl-s:not(.c) .stl-n,.stl .stl-x{display:none}}`;
function stl_css() { if (!document.getElementById('stl-css')) { const s = document.createElement('style'); s.id = 'stl-css'; s.textContent = STL_CSS; document.head.appendChild(s); } }
const stl_ver = v => String(v || '').replace(/^v/i, '').replace(/(\.0)+$/, '');  // 2.151 == 2.151.0 == v2.151.0 (as gitbuild.gb_key)
// the stages of t: [{k, label, on, at, bad}] (on = reached); null = no line here (no repository, no environment)
function stl_model(t) {
  const repo = listRepos(t.list_id).length > 0, d = ENV.d[t.list_id];
  if (!d || (!d.busy && d.v !== S.v)) setTimeout(() => env_load(t.list_id), 0);
  const envs = d?.j?.envs || [];
  if (!repo && !envs.length) return null;
  const b = repo ? t.code?.build || {state: 'none'} : null, sk = sk_task(t);
  const msEnvs = (t.milestone_id && env_ms(t.list_id, t.milestone_id)?.envs) || [];
  const out = [{k: 'created', label: tr('Created'), on: true, at: t.created_at},
    {k: 'progress', label: tr('In progress'), on: ['progress', 'review', 'done'].includes(sk) || ['branch', 'main', 'released'].includes(b?.state)}];
  if (b) out.push({k: 'built', label: tr('Built'), on: ['main', 'released'].includes(b.state)},
    {k: 'released', label: b.version ? tr('Version {0}', b.version) : tr('Released'), on: b.state === 'released'});
  for (const e of envs) {
    const m = msEnvs.find(x => x.name === e.name), c = e.current;
    const byVer = !!(b?.version && c?.version && stl_ver(c.version) === stl_ver(b.version));
    out.push({k: 'env', label: e.name, on: !!m || byVer, at: m ? m.since : byVer ? c.at : null});
  }
  out.push(t.status === -1 ? {k: 'rejected', label: tr('Rejected'), on: true, at: t.completed_at, bad: true} : {k: 'done', label: tr('Done|section'), on: t.status === 2, at: t.completed_at});
  return out;
}
// what stands at the current stage: parked / waiting with the reason, "2× back", with whom
function stl_extra(t) {
  const x = [], ds = typeof dv_state === 'function' ? dv_state(t) : '';
  if (ds === 'parked') x.push(t.delivery_note ? tr('Parked: {0}', t.delivery_note) : tr('Parked'));
  else if (ds === 'waiting') x.push(tr('Waiting for {0}', t.delivery_task_id ? '#' + t.delivery_task_id : t.delivery_note || '…'));
  const back = S.tl.id === t.id ? (S.tl.activity || []).filter(a => a.kind === 'reopen').length : 0;
  if (back) x.push(tr('{0}× back', back));
  const who = t.assignee_id ? personNameAny(t.assignee_id) || '?' : t.assignee_group_id ? grpName(t.assignee_group_id) : tr('nobody');
  x.push(tr('With {0}|lies with', who));
  return x;
}
function stl_html(t) {
  if (!(t?.id > 0) || t.context || isMs(t)) return '';
  const st = stl_model(t); if (!st) return '';
  stl_css();
  let cur = 0; st.forEach((s, i) => { if (s.on) cur = i; });
  const ex = stl_extra(t), day = s => s.at ? env_day(s.at) : '';
  const chain = st.map((s, i) => `${i ? '<span class="stl-x" aria-hidden="true">›</span>' : ''}<span class="stl-s ${i === cur ? 'c' : s.on ? 'd' : 'o'}${s.bad ? ' bad' : ''}" data-stage="${esc(s.k)}">`
    + `<span class="stl-dot" aria-hidden="true"></span><span class="stl-n">${s.on && i !== cur ? '✓ ' : ''}${esc(s.label)}</span>`
    + `${i === cur && ex.length ? ` <span class="stl-ex">· ${esc(ex.join(' · '))}</span>` : ''}</span>`).join('');
  const all = st.map((s, i) => `<li class="${s.on ? 'd' : 'o'}">${esc(s.label)}${day(s) ? ` <span class="muted">· ${esc(day(s))}</span>` : ''}${i === cur ? ` <b>${esc(tr('now'))}</b>` : ''}</li>`).join('');
  return `<details class="stl" id="d-stages"><summary aria-label="${esc(tr('Stage {0} of {1}: {2}', cur + 1, st.length, st[cur].label) + (ex.length ? ' · ' + ex.join(' · ') : ''))}">${/*html-ok*/ chain /* the stages above, built escaped */}</summary><ol>${/*html-ok*/ all /* the rows above, built escaped */}</ol></details>`;
}
