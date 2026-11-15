// @ts-check
/* Kalmido web client: the ONE Share dialog of folders and files (2.199.0 A, #2742), taken out of the file store (ablage.js
   ab_share) so that the office, the tables and later areas use the same: people, groups and agents of the node's workspace,
   view or edit each with an optional end date, the shares of the folders above (read only), the whole organisation (people
   only). fs_shareDialog(nodeId, {office, onChange}): office = the node lies in the office (a hint: folders rule documents,
   the office groups rule its actions), onChange = after a change (default: the file store reloads). Loaded on first use
   (lazyload.js, module fsshare). Classic script sharing the global scope with the others.
   2.200.0 B (#2747): opts.hint = an area's own hint, opts.org === false = no "Whole organisation" (the knowledge area: every
   member reads anyway), opts.extra(box, node) = fills an area's own section below the shares (the knowledge pages: links and
   older shares).
   2.352.0 E (#2748): opts.listRole = a projects folder: each share gets a list role (admin, member, participant, viewer;
   never admin for an agent), sent as list_role next to the role the file store knows. */
'use strict';

async function fs_shareDialog(id, opts = {}) {
  const changed = () => (typeof opts.onChange === 'function' ? opts.onChange : ab_reload)();
  let n, t; try { [n, t] = await Promise.all([api('GET', `/api/files/nodes/${id}`), api('GET', `/api/files/nodes/${id}/share-targets`)]); } catch { return; }
  if (typeof fsl_prep1 === 'function') await fsl_prep1(n);  // 2.353.0 A (#2758): the plain name of a node in a locked folder
  $('.abshdlg')?.remove();
  const roleSel = (attr, cur, agent) => opts.listRole ? `<select ${attr} aria-label="${esc(tr('Role'))}">${FP_ROLES.filter(([v]) => !agent || v !== 'admin').map(([v, nm]) => `<option value="${v}" ${cur === v ? 'selected' : ''}>${tr(nm)}</option>`).join('')}</select>`
    : `<select ${attr} aria-label="${esc(tr('Role'))}"><option value="view" ${cur === 'view' ? 'selected' : ''}>${tr('Can view')}</option><option value="edit" ${cur === 'edit' ? 'selected' : ''}>${tr('Can edit')}</option></select>`;
  // 2.352.0 E (#2748): a list role -> the body of a share (role of the file store + list_role)
  const roleBody = r => opts.listRole ? {role: r === 'admin' || r === 'edit' ? 'edit' : 'view', list_role: r} : {role: r};
  // the targets; 2.352.0 E (#2748): a projects folder does not offer who has a share already (as its former dialog, #1044)
  const tgtOpts = sh => {
    // 2.1224.0 (#6113, review): everywhere now - choosing adds at once, so choosing someone shared already would set them back
    // to "Can view" without an end date (the server treats the same target as an update); their row beside holds role + date
    const has = (k, id) => sh.some(x => x[k] === id);
    const grp = (lab, k, xs) => (xs = xs.filter(p => !has(k, p.id))).length ? `<optgroup label="${esc(lab)}">${xs.map(p => `<option value="${k}:${p.id}">${esc(p.name)}</option>`).join('')}</optgroup>` : '';
    return `<option value="">${tr('Share with …')}</option>${grp(tr('People'), 'user_id', t.people)}${grp(tr('Groups'), 'group_id', t.groups)}${grp(tr('Agents'), 'agent_id', t.agents)}`;
  };
  /** @type {any} */
  const md = modal(`<div class="lhdr"><h3>${esc(tr('Share “{0}”', n.name))}</h3><span class="spacer"></span><button class="iconbtn" data-m="close" aria-label="${tr('Close')}" title="${tr('Close')}">${ic('x')}</button></div>
    <div class="shint lhint keep">${n.kind === 'folder' ? tr('The share applies to everything in this folder, also what is added later.') : n.kind === 'ref' ? tr('The share applies to this document.') : tr('The share applies to this file and all its versions.')}</div>${''/* 2.1224.0 (#6113): one sentence under the title (the agents' second sentence is gone) */}
    ${opts.hint ? `<div class="shint lhint keep fshint">${ic('info', 's')} ${esc(opts.hint)}</div>` : ''}
    ${n.locked ? `<div class="shint lhint keep fslhint">${ic('lock', 's')} ${esc(tr('Locked folder: only people can get access, and they open it once an owner handed them the key. Agents and API tokens are always excluded.'))}</div>` : ''}
    ${opts.office ? `<div class="shint lhint keep fsoffice">${ic('info', 's')} ${esc(tr('Folders give access to documents, not to office actions (releasing and sending, payments, locking, export): those stay with the office groups.'))}</div>` : ''}
    <div class="shws">${ab_spaceIcon(n.org_id ? 'org:' + n.org_id : 'private')} ${esc(n.org_id ? wsName('org:' + n.org_id) : tr('Private|workspace'))} <small class="muted">${esc(tr('Only people, groups and agents of this workspace'))}</small></div>
    <div id="ab-shl" class="members"></div>
    <div class="abshadd">
      <select id="ab-sht" aria-label="${esc(tr('Share with …'))}">${tgtOpts(n.shares || [])}</select></div>${''/* 2.1224.0 (#6113): choosing adds at once with "Can view"; role and end date beside each person (draw) */}
    ${n.org_id && opts.org !== false ? `<h4>${tr('Whole organisation')}</h4><div class="row"><select id="ab-sho" aria-label="${esc(tr('Whole organisation'))}"><option value="">${tr('Only the people it is shared with')}</option><option value="view" ${n.org_access === 'view' ? 'selected' : ''}>${tr('Every member can view')}</option><option value="edit" ${n.org_access === 'edit' ? 'selected' : ''}>${tr('Every member can edit')}</option></select></div>${n.org_access_from ? `<div class="muted">${esc(tr('Already open through the folder “{0}”', n.org_access_from.name))}</div>` : ''}<div class="muted abhint">${tr('Never for agents. The organisation’s admins always see everything.')}</div>` : ''}
    ${typeof opts.extra === 'function' ? '<div class="fsextra"></div>' : ''}
    <div class="foot"><span class="spacer"></span><button class="btn pri" data-m="close">${tr('Done')}</button></div>`);
  md.classList.add('shmodal', 'abshdlg', ...(opts.listRole ? ['lfshdlg'] : []));
  if (typeof opts.extra === 'function') opts.extra($('.fsextra', md), n);
  let shares = n.shares || [];
  const inh = n.inherited || [];
  const draw = () => {
    const box = $('#ab-shl', md); if (!box) return;
    box.innerHTML = shares.map(s => `<div class="mrow" data-sid="${s.id}">${s.agent_id ? av(s.agent_id, s.name) : s.group_id ? ic('users') : av(s.user_id, s.name)}<span class="n">${esc(s.name)}${s.agent_id ? agentBadge(s.agent_id) : ''}</span><span class="abshctl">${roleSel(`data-absr="${s.id}"`, opts.listRole ? s.list_role || s.role : s.role, !!s.agent_id)}<span class="abexp">${/*html-ok*/ dateIn('ab-she' + s.id, s.expires_at ? ds(new Date(s.expires_at)) : '', {label: tr('Valid until (optional)'), min: today(), empty: tr('No end date'), attrs: `data-abse="${esc(s.id)}"`})}</span></span><button class="iconbtn" data-absx="${s.id}" title="${esc(tr('Stop sharing'))}" aria-label="${esc(tr('Stop sharing with {0}', s.name))}">${ic('x', 's')}</button></div>`).join('')
      + inh.map(s => `<div class="mrow abinh"><span class="n">${esc(s.name)} <small class="muted">${esc(s.area ? tr('shared via: whole knowledge area') : tr('from the folder “{0}”', s.from))}${s.excluded ? ' · ' + esc(tr('excluded here')) : ''}</small></span><span class="muted">${esc(s.excluded ? '–' : ab_role(s.role))}</span></div>`).join('')  // 2.1045.0 (#5823): s.area, s.excluded
      || `<div class="muted mhint">${tr('Not shared yet')}</div>`;
    { const sel = $('#ab-sht', md); if (sel) sel.innerHTML = tgtOpts(shares); }  // 2.1224.0 (#6113): who has a share is not offered
  };
  draw();
  const add = async (target, role, exp) => {
    const [k, v] = target.split(':');
    const r = await api('POST', `/api/files/nodes/${id}/shares`, {[k]: +v, ...roleBody(k === 'agent_id' && role === 'admin' ? 'edit' : role), expires_at: exp || null, tz: evTz()});
    shares = r.shares; draw(); changed(); return r.id;
  };
  md.addEventListener('click', async (/** @type {any} */ e) => {
    if (e.target.closest('[data-m="close"]')) { modalClose(md); return; }
    const x = e.target.closest('[data-absx]');
    if (x) {
      const s = shares.find(q => q.id === +x.dataset.absx); if (!s) return;
      let r; try { r = await api('DELETE', `/api/files/shares/${s.id}`); } catch { return; }
      shares = r.shares; draw(); changed();
      const tg = s.user_id ? 'user_id:' + s.user_id : s.group_id ? 'group_id:' + s.group_id : 'agent_id:' + s.agent_id;
      offerUndo(tr('No longer shared with {0}', s.name), histAdd({label: tr('Stop sharing “{0}”', n.name), undo: async () => { try { await add(tg, opts.listRole ? s.list_role || s.role : s.role, s.expires_at || ''); } catch { /* shown */ } return {}; }, redo: () => ab_req('DELETE', `/api/files/shares/${(shares.find(q => (q.user_id || q.group_id || q.agent_id) === (s.user_id || s.group_id || s.agent_id)) || s).id}`)}));
    }
  });
  // 2.1224.0 (#6113): which way the choice came - a pointer adds at once, the keyboard only with Enter (arrows / letters on the
  // closed field fire change in Chrome and Firefox: a walk through the names must not share with each one)
  let kbPick = false;
  md.addEventListener('pointerdown', (/** @type {any} */ e) => { if (e.target.closest?.('#ab-sht')) kbPick = false; });
  md.addEventListener('keydown', (/** @type {any} */ e) => {
    if (e.target.id !== 'ab-sht') return;
    if (e.key === 'Enter' && e.target.value) { e.preventDefault(); const ev = /** @type {any} */ (new Event('change', {bubbles: true})); ev.kbEnter = true; e.target.dispatchEvent(ev); }
    else if (e.key !== 'Tab' && e.key !== 'Escape') kbPick = true;
  });
  md.addEventListener('change', async (/** @type {any} */ e) => {
    if (e.target.id === 'ab-sht') {  // 2.1224.0 (#6113): a choice adds at once with "Can view" (a projects folder too: a slip gives no write access)
      const sel = e.target, tg = sel.value; if (!tg) return;
      if (kbPick && !e.kbEnter) return;
      const role = 'view';
      const nm = $(`#ab-sht option[value="${tg}"]`, md)?.textContent || '';  // before the add (a projects folder's list drops it)
      sel.value = '';
      if (typeof opts.confirm === 'function' && !(await opts.confirm(tg, role))) return;  // 2.1045.0 (#5823): an area's own question first
      // an agent reads at once (it gets the event file_shared): one question before, an undo comes too late
      else if (typeof opts.confirm !== 'function' && tg.startsWith('agent_id:') && !(await askConfirm(tr('Share with {0}?', nm), tr('The agent can read everything shared here right away.'), {ok: tr('Share')}))) return;
      let sid; try { sid = await add(tg, role, ''); } catch { return; }
      offerUndo(tr('Shared with {0}', nm), histAdd({label: tr('Share “{0}”', n.name), undo: () => ab_req('DELETE', `/api/files/shares/${sid}`), redo: async () => { try { sid = await add(tg, role, ''); } catch { /* shown */ } return {}; }}));
      return;
    }
    const ex = e.target.closest('[data-abse]');  // 2.1224.0 (#6113): the end date beside the person
    if (ex) {
      const s = shares.find(q => q.id === +ex.dataset.abse); if (!s) return;
      const was = s.expires_at || null, v = ex.value || null, put = async x => { try { shares = (await api('PATCH', `/api/files/shares/${s.id}`, {expires_at: x, tz: evTz()})).shares; draw(); changed(); } catch { /* shown */ } return {}; };  // 2.1224.0 (#6113, review): the open dialog shows the date undone
      try { shares = (await api('PATCH', `/api/files/shares/${s.id}`, {expires_at: v, tz: evTz()})).shares; } catch { draw(); return; }
      draw(); changed();
      offerUndo(v ? tr('Valid until {0}', fmtDateLoc(v)) : tr('No end date'), histAdd({label: tr('Share “{0}”', n.name), undo: () => put(was), redo: () => put(v)}));
      return;
    }
    const r = e.target.closest('[data-absr]');
    if (r) { const s = shares.find(q => q.id === +r.dataset.absr), was = opts.listRole ? s?.list_role || s?.role : s?.role;
      // 2.1224.0 (#6113): added with "Can view", so raising the role asks an area's own question now (was: before the add)
      if (s && typeof opts.confirm === 'function' && (r.value === 'edit' || r.value === 'admin') && !(await opts.confirm(s.user_id ? 'user_id:' + s.user_id : s.group_id ? 'group_id:' + s.group_id : 'agent_id:' + s.agent_id, r.value))) { r.value = was; return; }
      try { shares = (await api('PATCH', `/api/files/shares/${r.dataset.absr}`, roleBody(r.value))).shares; } catch { return; } draw(); if (opts.listRole) changed(); offerUndo(tr('Role changed'), histAdd({label: tr('Role in “{0}”', n.name), undo: () => ab_req('PATCH', `/api/files/shares/${r.dataset.absr}`, roleBody(was)), redo: () => ab_req('PATCH', `/api/files/shares/${r.dataset.absr}`, roleBody(r.value))})); return; }
    if (e.target.id === 'ab-sho') {
      const was = n.org_access || '', v = e.target.value;
      try { await api('PATCH', `/api/files/nodes/${id}`, {org_access: v}); } catch { return; }
      n.org_access = v; changed();
      offerUndo(v ? tr('Open to the whole organisation') : tr('Only the people it is shared with'), histAdd({label: tr('Whole organisation: “{0}”', n.name), undo: () => ab_req('PATCH', `/api/files/nodes/${id}`, {org_access: was}), redo: () => ab_req('PATCH', `/api/files/nodes/${id}`, {org_access: v})}));
    }
  });
}
