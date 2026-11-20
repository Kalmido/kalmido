// @ts-check
// 2.138.0 D (#2256): number ranges -- the office admin sets the next running number of every series (quotation, invoice,
// credit note, reminder, delivery note) under the number schemes of the settings, and a draft's number can be changed in the document
// editor (click on the number). Own save via /api/office/number-ranges (not the settings' save, hence the ids
// without "os-" and data-fg-skip); only upwards, a jump in the invoice / credit note series needs a reason (office log).
// 2.855.0 (#5456): one form - every field with its hint right below it, one "Apply" at the end saves all changed rows.
const ONUM = {ranges: null, extra: [], loading: false, err: '', doc: null, busy: false};
const ONUM_NAMES = {offer: N_('Quotation numbers'), invoice: N_('Invoice numbers'), credit: N_('Credit note numbers'), reminder: N_('Payment reminder numbers'), delivery: N_('Delivery note numbers')};
const ONUM_SCHEME_IDS = {offer: 'os-scheme', invoice: 'os-inv-scheme', credit: 'os-cr-scheme', reminder: 'os-rm-scheme', delivery: 'os-ls-scheme'};

// a number of the scheme with example values (the same building blocks the server knows, office/model.py)
function onumFmt(scheme, seq) {
  const d = new Date(), y = String(d.getFullYear()), p2 = n => String(n).padStart(2, '0');
  return String(scheme || '').replace(/\{(yyyy|yy|seq(?::0?(\d+))?|project|client|kuerzel|date|isodate|initials)\}/g, (m, t, w) =>
    t === 'yyyy' ? y : t === 'yy' ? y.slice(2) : t.startsWith('seq') ? String(seq).padStart(+w || 0, '0')
      : t === 'project' ? tr('Project') : t === 'client' ? tr('Client') : t === 'kuerzel' ? 'ABC' : t === 'date' ? y + p2(d.getMonth() + 1) + p2(d.getDate())
      : t === 'isodate' ? y + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()) : 'AB');  // 2.138.2 (#2391)
}

async function onumLoad() {
  if (ONUM.loading) return;
  ONUM.loading = true;
  try {
    const j = await api('GET', '/api/office/number-ranges'); ONUM.ranges = j.ranges || []; ONUM.extra = j.extra || []; ONUM.err = '';
    // 2.1345.0 (#6532): an empty invoice / credit note series while no real invoice is finalised: the reason of a jump (GoBD)
    // is prefilled - the usual case is continuing the previous program; it can be changed before "Apply"
    if (j.first_invoice) for (const r of ONUM.ranges) if (r.reason_needed && !r.shared && !+r.last) ONUM['w' + r.kind] ??= tr('Taken over from the previous program');
    onumInfoRanges();
  }
  catch (x) { ONUM.ranges = []; ONUM.extra = []; ONUM.err = ofcErrHere(x); }
  ONUM.loading = false;
  onumRedraw();
}
function onumRedraw() { const box = $('#onum-box'); if (box) box.outerHTML = onumHtml(); }
// 2.979.0 (#5667): an undo / redo the server did: the shown number ranges come again
// 2.1391.0 (#7111): and the issuer block (its ranges decide whether an issuer can be added)
histReloader('numranges', () => { issFresh(); if (!ONUM.ranges) return; if ($('#onum-box')) return onumLoad(); ONUM.ranges = null; });

// the block of the settings page (office.js ofcSettingsHtml calls it below the number schemes); admins only
function onumHtml() {
  if (typeof ofcAdmin !== 'function' || !ofcAdmin()) return '';
  const s = OFC.info?.settings || {}, sch = k => (k === 'offer' ? s.offer_scheme : s[k + '_scheme'] || s.offer_scheme) || '';
  const sig = [OFC.info?.org_id, s.offer_counter || 'org', s.credit_shared ? 1 : 0, ...Object.keys(ONUM_NAMES).map(sch)].join('|');  // 2.433.0 (#3597): + the shared counter
  if (ONUM.sig !== sig) { ONUM.sig = sig; ONUM.ranges = null; }  // another office area / a saved scheme: read again
  if (!ONUM.ranges) { if (!ONUM.loading) setTimeout(onumLoad, 0); return `<div id="onum-box" class="onum" data-fg-skip></div>`; }
  const rows = onumRows().map(r => {
    // 2.433.0 (#3597): invoice corrections on the invoices' counter - the row greyed, the next number set with the invoices
    if (r.shared) return `<div class="row onumrow onumshared" data-kind="${r.kind}"><label for="onum-${r.kind}">${esc(tr(ONUM_NAMES[r.kind]))}</label>
      <span class="lacts"><input id="onum-${r.kind}" type="text" value="${esc(String(r.next))}" class="numin" disabled aria-describedby="onum-${r.kind}-h"><span class="muted ofcpv">${esc(tr('next: {0}', onumFmt(r.scheme, r.next)))}</span></span>
      <span class="muted ofchint" id="onum-${r.kind}-h">${esc(tr('Counts with the invoice numbers'))}</span></div>`;
    const id = 'onum-' + r.kind, v = ONUM['v' + r.kind] ?? String(r.next), n = parseInt(v, 10), jump = n > r.min_next;
    const pv = n >= 1 ? tr('next: {0}', onumFmt(r.scheme, n)) : '';
    const hint = [tr('at least {0}', r.min_next), r.yearly ? tr('applies to {0}', r.period) : '', ...onumExtraHint(r)].filter(Boolean).join(' · ');
    return `<div class="row onumrow${r.code ? ' onumextra' : ''}" data-kind="${r.kind}"><label for="${id}">${esc(onumName(r))}</label>
      <span class="lacts"><input id="${id}" data-onum-in="${r.kind}" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" value="${esc(v)}" class="numin" aria-describedby="${id}-h">
      <span class="muted ofcpv" id="${id}-pv" aria-live="polite">${esc(pv)}</span>
      <span class="muted ofchint onumh" id="${id}-h">${esc(hint)}</span></span>
      ${/*html-ok*/ onumGapsHtml(r) /* 2.1315.0 (#6472): escaped inside */}
      ${r.reason_needed && jump ? `<span class="lacts onumwhy"><input id="${id}-why" data-onum-why="${r.kind}" value="${esc(ONUM['w' + r.kind] || '')}" maxlength="300" placeholder="${esc(tr('Reason for the jump (kept in the office log)'))}" aria-label="${esc(tr('Reason'))}"></span>` : ''}
      ${ONUM['e' + r.kind] ? `<span class="ofcpv err ofchint" role="alert">${esc(ONUM['e' + r.kind])}</span>` : ''}${/*html-ok*/ onumExtraActs(r) /* 2.1365.0 (#6698): escaped inside */}</div>`;
  }).join('');
  const dirty = onumDirty().length > 0;
  return `<div id="onum-box" class="onum" data-fg-skip><h4>${tr('Next running number')}</h4><div class="shint">${esc(tr('With a year in the scheme it applies to the current year.'))}</div>
    <p class="muted ofchint">${esc(tr('E.g. to continue your previous program. Only upwards.'))}</p>
    ${/*html-ok*/ ONUM.err ? errorState({sub: ONUM.err, size: 'row'}) /* 2.1076.0 (#5450) */ : ''}${rows}
    ${ONUM.ranges.some(r => !r.shared) ? `<div class="row onumfoot"><span class="lacts"><button type="button" class="btn sm" data-onum="nr-add">${ic('plus', 's')}<span>${tr('Add number range')}</span></button><button type="button" class="btn sm pri" data-onum="apply" ${dirty && !ONUM.busy ? '' : 'disabled'}>${tr('Apply')}</button></span></div>` : ''}</div>`;
}
// 2.1315.0 (#6472): the gaps of the series (the same check as the auditor's export, number_ranges.csv) - each range with its reason
function onumGapsHtml(r) {
  const g = r.gaps; if (!g || !g.count) return '';
  const rg = x => (x.from === x.to ? String(x.from) : x.from + '–' + x.to) + ': ' + x.reason;
  const list = g.ranges.map(rg).concat(g.more ? [tr('{0} more', g.more)] : []).join(' · ');
  return `<span class="muted ofchint onumgaps${g.none ? ' warn' : ''}" id="onum-${esc(r.kind)}-gaps">${esc(tr('Missing numbers: {0}', g.count))}${g.none ? ' (' + esc(tr('{0} without a reason', g.none)) + ')' : ''} - ${esc(list)}</span>`;
}
// 2.855.0 (#5456): the rows whose field differs from the stored next number (shared rows have no own counter)
const onumDirty = () => onumRows().filter(r => !r.shared && ONUM['v' + r.kind] != null && ONUM['v' + r.kind].trim() !== String(r.next));

// 2.855.0 (#5456): one "Apply" for all changed rows: one question naming every jump, then each row through its own route
// (POST /api/office/number-ranges/<kind>); a row the server refuses keeps its value and says why at its field (no toast),
// the others are saved; all saved = one "Saved"
async function onumApplyAll() {
  const ch = onumDirty(); if (!ch.length || ONUM.busy) return;
  const val = r => parseInt(ONUM['v' + r.kind] || '', 10);
  const bad = ch.filter(r => !(val(r) > r.next));
  for (const r of bad) ONUM['e' + r.kind] = tr('Only upwards: at least {0}', r.next + 1);
  if (bad.length) { onumRedraw(); $('#onum-' + bad[0].kind)?.focus(); return; }
  const lines = ch.map(r => tr('{0}: continues at {1}, the numbers {2} to {3} are skipped.', onumName(r), onumFmt(r.scheme, val(r)), r.next, val(r) - 1));
  const html = lines.map(l => `<p>${esc(l)}</p>`).join('') + `<p>${esc(tr('Skipped numbers cannot be given later.'))}</p>`;
  if (!await askConfirm(tr('Apply the new running numbers?'), '', {html, ok: tr('Apply')})) return;
  ONUM.busy = true; onumRedraw();
  let fail = '';
  for (const r of ch) {
    const kind = r.kind;
    try {
      const j = await rawFetch('POST', `/api/office/number-ranges/${kind}`, {next: val(r), reason: (ONUM['w' + kind] || '').trim()});
      Object.assign(r, j); delete ONUM['v' + kind]; delete ONUM['w' + kind]; delete ONUM['e' + kind];
      if (typeof OFC === 'object') { OFC.log = null; if (OFC.pv) delete OFC.pv[kind]; if (kind === 'offer' && OFC.info) OFC.info.number_preview = j.preview; }
      const sch = $('#' + ONUM_SCHEME_IDS[kind]); if (sch && typeof ofcSchemePv === 'function') ofcSchemePv(sch, true);  // the scheme's "next: …" again
    } catch (x) { ONUM['e' + kind] = ofcErrHere(x); fail ||= kind; }
  }
  ONUM.busy = false;
  onumRedraw();
  if (!fail) toast(tr('Saved'));
  else $('#onum-' + fail)?.focus();
}

// ---- the draft's number in the document editor (office_docs.js: the head calls onumDocHtml, a click on the number opens it)
const onumDocCan = d => !!d && !d.locked && d.can_edit && d.status === 'draft' && ofcAdmin()  // 2.148.1 (#2496): numbers by office admins only
  && !['invoice', 'credit'].includes(d.kind);  // 2.1289.0 (#6481 N3, S3): an invoice / correction takes its own number in the finalise dialog
function onumDocHtml(d) {
  if (!onumDocCan(d)) return '';
  const e = ONUM.doc && ONUM.doc.id === d.id ? ONUM.doc : null;
  if (!e) return `<button type="button" class="btn sm onumpen" data-onum="doc-open" aria-label="${esc(tr('Change number'))}" title="${esc(tr('Change number'))}">${ic('edit', 's')}</button>`;
  const inv = d.kind !== 'offer';
  return `<span class="onumdoc" role="group" aria-label="${esc(tr('Change number'))}">
    <input id="onum-doc" value="${esc(e.val)}" maxlength="80" autocomplete="off" spellcheck="false" aria-label="${esc(tr('Change number'))}" aria-describedby="onum-doc-h">
    ${inv ? `<input id="onum-doc-why" value="${esc(e.why)}" maxlength="300" placeholder="${esc(tr('Reason (needed when numbers are skipped)'))}" aria-label="${esc(tr('Reason'))}">` : ''}
    <button type="button" class="btn sm" data-onum="doc-x">${tr('Cancel')}</button><button type="button" class="btn sm pri" data-onum="doc-save" ${e.busy ? 'disabled' : ''}>${tr('Save')}</button>
    <span class="muted ofchint" id="onum-doc-h">${esc(inv ? tr('The series continues from this number.') + (d.number_at_finalize && !d.number ? ' ' + tr('A numbered draft can no longer be deleted.') : '') : tr('The counter of the series stays as it is.'))}</span>
    ${e.err ? `<span class="ofcpv err ofchint" role="alert">${esc(e.err)}</span>` : ''}</span>`;
}
function onumDocOpen() {
  const d = typeof OFD === 'object' ? OFD.doc : null; if (!onumDocCan(d)) return;
  ONUM.doc = {id: d.id, val: d.number || '', why: '', err: '', busy: false};
  ofdDraw(); const i = $('#onum-doc'); if (i) { i.focus(); i.select(); }
}
async function onumDocSet(d, num, why) {
  // 2.1317.0 (#6331): after the editor's own saves (ofd_inChain), with the version of the draft shown (ofd_ver); 409 {doc} = the conflict bar
  const j = await ofd_inChain(() => rawFetch('POST', `/api/office/docs/${d.id}/number`, {number: num, reason: why, ...(OFD.doc && OFD.doc.id === d.id ? ofd_ver() : {})}))
    .catch(x => { if (x.status === 409 && x.data?.doc && OFD.doc && x.data.doc.id === OFD.doc.id) { OFD.conflict = {id: OFD.doc.id, doc: x.data.doc}; ONUM.doc = null; x.conflict = true; } throw x; });
  if (OFD.doc && OFD.doc.id === d.id) { OFD.doc.number = j.number; if (j.updated_at) OFD.doc.updated_at = j.updated_at; }
  if (Array.isArray(OFD.list)) { const r = OFD.list.find(x => x.id === d.id); if (r) r.number = j.number; }  // the list shows it at once
  OFD.list = null; OFD.log = null;  // ... and is read again when it opens
  return j;
}
async function onumDocSave() {
  const d = OFD.doc, e = ONUM.doc; if (!d || !e || e.busy) return;
  e.val = ($('#onum-doc')?.value || '').trim(); e.why = ($('#onum-doc-why')?.value || '').trim();
  if (e.val === (d.number || '')) { ONUM.doc = null; ofdDraw(); return; }
  e.busy = true; e.err = '';
  const old = d.number || '', kind = d.kind, id = d.id;
  try {
    const j = await onumDocSet(d, e.val, e.why);
    ONUM.doc = null;
    // one undo step where the server allows the way back: a quotation's number is free (the series is not touched);
    // invoices / credit notes / reminders never go down in their series, so no undo there
    if (kind === 'offer' && old && typeof histAdd === 'function') {
      const back = async n => { try { await onumDocSet({id}, n, ''); ofdDraw(); } catch (x) { ofcErr(x); } };
      offerUndo(tr('Saved'), histAdd({label: tr('Change number'), undo: () => back(old), redo: () => back(j.number)}));
    } else toast(tr('Saved'));
  } catch (x) { e.busy = false; if (!x.conflict) e.err = ofcErrHere(x); }  // 2.1317.0 (#6331): a conflict says it in the bar
  ofdDraw();
}
// the office list follows a change made elsewhere (another device, the console, an agent): load() of the state calls this
function onumListFresh() {
  if (typeof OFD !== 'object' || typeof ofcTab !== 'function' || S.route?.mod !== 'office' || !ofcDocTab(ofcTab()) || S.route.id || OFD.loading || !OFD.list) return;
  // 2.138.0 D (#2256, review): every state push calls this -> at most one reload per 5 s, a later push within it reloads at its end
  const f = /** @type {any} */ (onumListFresh);
  const wait = 5000 - (Date.now() - (f.at || 0));
  if (wait > 0) { if (!f.timer) f.timer = setTimeout(() => { f.timer = 0; onumListFresh(); }, wait); return; }
  f.at = Date.now();
  ofdLoadList(true);
}

document.addEventListener('click', e => {
  const tg = /** @type {any} */ (e.target);
  const b = tg.closest?.('[data-onum]');
  if (!b) { if (tg.closest?.('.ofdhead .ofdnum b') && typeof OFD === 'object' && onumDocCan(OFD.doc) && !ONUM.doc) onumDocOpen(); return; }
  const a = b.dataset.onum;
  if (a === 'apply') { e.preventDefault(); onumApplyAll(); }  // 2.855.0 (#5456): one Apply for the form
  else if (a === 'doc-open') onumDocOpen();
  else if (a === 'doc-save') onumDocSave();
  else if (a === 'doc-x') { ONUM.doc = null; ofdDraw(); }
  else if (a === 'nr-add') nrDialog(null);  // 2.1365.0 (#6698)
  else if (a === 'nr-edit') nrDialog(ONUM.extra.find(x => String(x.id) === b.dataset.id) || null);
  else if (a === 'nr-del') nrDelete(ONUM.extra.find(x => String(x.id) === b.dataset.id));
});
document.addEventListener('input', e => {
  const t = /** @type {any} */ (e.target);
  if (t.dataset?.onumIn) {
    const k = t.dataset.onumIn, r = onumRows().find(x => x.kind === k); if (!r) return;
    ONUM['v' + k] = t.value; delete ONUM['e' + k];
    const n = parseInt(t.value, 10), row = t.closest('.onumrow');
    const pv = $('#onum-' + k + '-pv'); if (pv) pv.textContent = n >= 1 ? tr('next: {0}', onumFmt(r.scheme, n)) : '';
    const btn = $('#onum-box [data-onum="apply"]'); if (btn) btn.disabled = !onumDirty().length || !!ONUM.busy; row?.querySelector('[role="alert"]')?.remove();  // 2.855.0 (#5456)
    if (r.reason_needed && (n > r.min_next) !== !!$('#onum-' + k + '-why')) { onumRedraw(); const i = /** @type {HTMLInputElement|null} */ ($('#onum-' + k)); if (i) { i.focus(); const e = i.value.length; i.setSelectionRange(e, e); } }  // 2.138.0 (#2256): the caret stays at the end after the redraw (device test: 1001 became 0110; a text field, number fields have no caret API)
  } else if (t.dataset?.onumWhy) ONUM['w' + t.dataset.onumWhy] = t.value;
  else if (t.id === 'onum-doc' && ONUM.doc) ONUM.doc.val = t.value;
  else if (t.id === 'onum-doc-why' && ONUM.doc) ONUM.doc.why = t.value;
});
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const t = /** @type {any} */ (e.target);
  if (t.dataset?.onumIn || t.dataset?.onumWhy) { e.preventDefault(); onumApplyAll(); }  // never the settings' submit; 2.855.0 (#5456): Enter = the form's Apply
  else if (t.id === 'onum-doc' || t.id === 'onum-doc-why') { e.preventDefault(); e.stopPropagation(); onumDocSave(); }
}, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && ONUM.doc && (/** @type {any} */ (e.target).id === 'onum-doc' || /** @type {any} */ (e.target).id === 'onum-doc-why')) { ONUM.doc = null; ofdDraw(); } });
if (typeof OA_LOG_TG === 'object') OA_LOG_TG.number_range = N_('Number ranges');  // the office log names the target

// ---- 2.1365.0 (#6698): additional number ranges (invoices and their corrections on a counter of their own, e.g. GT-{yyyy}-{seq:03}
// with the corrections' ending -K). Admins add, change, close or remove them here (the settings page is theirs, ofcAdmin); the
// next number of a range is set in the same form (POST /api/office/number-ranges/r<id>). The draft editor offers the open ranges
// (office_docs.js ofd_rangeHtml, from OFC.info.num_ranges).
const onumRows = () => [...(ONUM.ranges || []), ...(ONUM.extra || []).map(x => ({...x, kind: x.key}))];
const onumName = r => r.code ? r.code + (r.name ? ' · ' + r.name : '') : tr(ONUM_NAMES[r.kind]);
const onumExtraHint = r => !r.code ? [] : [tr('corrections: {0}', onumFmt(r.credit_scheme, r.next)), r.dunning ? tr('payment reminders on') : tr('no payment reminders'), r.closed ? tr('closed') : ''];
function onumExtraActs(r) {
  if (!r.code) return '';
  return `<span class="lacts onumacts"><button type="button" class="btn sm" data-onum="nr-edit" data-id="${esc(String(r.id))}">${ic('edit', 's')}<span>${tr('Edit')}</span></button>`
    + (r.used ? '' : `<button type="button" class="btn sm" data-onum="nr-del" data-id="${esc(String(r.id))}">${ic('trash', 's')}<span>${tr('Remove')}</span></button>`) + '</span>';
}
function onumInfoRanges() {  // the draft editor's choice follows a change here
  if (typeof OFC === 'object' && OFC.info) OFC.info.num_ranges = (ONUM.extra || []).map(x => ({id: x.id, code: x.code, name: x.name, closed: x.closed}));
}
function nrDialog(r) {
  let md0 = null;
  const f = (id, label, html, hint) => `<div class="row"><label for="${esc(id)}">${esc(label)}</label>${/*html-ok*/ html}${hint ? `<span class="muted ofchint">${esc(hint)}</span>` : ''}</div>`;
  const used = !!r?.used;
  const html = (r ? '' : f('nr-code', tr('Short code'), `<input id="nr-code" maxlength="8" autocomplete="off" spellcheck="false" placeholder="GT">`, tr('1 to 8 letters A-Z or digits, cannot be changed later')))
    + f('nr-name', tr('Name'), `<input id="nr-name" maxlength="80" value="${esc(r?.name || '')}">`)
    + f('nr-scheme', tr('Scheme'), `<input id="nr-scheme" maxlength="80" autocomplete="off" spellcheck="false" value="${esc(r?.scheme || '')}" placeholder="GT-{yyyy}-{seq:03}">`,
      tr('starts with a fixed text; building blocks {0}', '{yyyy} {yy} {seq} {seq:03}') + (used ? ' · ' + tr('a change applies from the next number on') : ''))
    + f('nr-suffix', tr('Ending of corrections'), `<input id="nr-suffix" maxlength="8" value="${esc(r ? r.credit_suffix : '-K')}">`, tr('corrections count on the same counter'))
    + `<label class="chk"><input type="checkbox" id="nr-dunning" ${r?.dunning ? 'checked' : ''}> ${esc(tr('Payment reminders and overdue notices for this range'))}</label>`
    + (r ? `<label class="chk"><input type="checkbox" id="nr-closed" ${r.closed ? 'checked' : ''}> ${esc(tr('Closed: no new invoices in this range'))}</label>` : '')
    + `<p class="muted ofchint">${esc(tr('Kalmido sets the date of a document of this range when it is finalised; numbers by hand are not possible there.'))}</p>`;
  askDialog({title: r ? tr('Edit number range {0}', r.code) : tr('Add number range'), html, ok: r ? tr('Save') : tr('Create'), cancel: tr('Cancel'), after: md => { md0 = md; },
    submit: async () => {
      const v = id => (/** @type {HTMLInputElement|null} */ ($('#' + id, md0))?.value || '').trim(), on = id => !!(/** @type {HTMLInputElement|null} */ ($('#' + id, md0))?.checked);
      const b = {name: v('nr-name'), scheme: v('nr-scheme'), credit_suffix: v('nr-suffix'), dunning: on('nr-dunning')};
      try {
        if (r) await rawFetch('PATCH', `/api/office/num-ranges/${r.id}`, {...b, closed: on('nr-closed')});
        else await rawFetch('POST', '/api/office/num-ranges', {...b, code: v('nr-code').toUpperCase()});
      } catch (x) { ofcErr(x); return false; }
      toast(tr('Saved')); if (typeof OFC === 'object') OFC.log = null; onumLoad(); issFresh(); return true;
    }});
}
async function nrDelete(r) {
  if (!r || !await askConfirm(tr('Remove number range {0}?', r.code), tr('Its drafts go back to the main range.'), {ok: tr('Remove')})) return;
  try { await rawFetch('DELETE', `/api/office/num-ranges/${r.id}`); toast(tr('Removed')); onumLoad(); issFresh(); } catch (x) { ofcErr(x); }
}

// ---- 2.1381.0 (#6699): invoice issuers -- an outside system (a shop, a booking system, an own script) prepares invoice drafts in
// one additional range with a key of its own (office/issuers.py); a person checks, finalises and sends them. The block sits below
// the number ranges on the settings page (office.js calls issHtml); hidden while the server / the operator does not allow issuers
// here (404). Admins of the organisation change, office admins read. Setting up, a new key, raising a limit, loosening the
// address rule, a new bank account and resuming after a pause the admin did not make ask for the sign-in confirmation (issSend).
const ISS = {data: null, loading: false, off: false, sig: '', err: ''};
const ISS_LIM = [['max_gross', N_('Gross per invoice at most'), 'money'], ['day_docs', N_('Invoices per 24 hours'), 'int'],
  ['day_gross', N_('Gross per 24 hours'), 'money'], ['day_clients', N_('New clients per 24 hours'), 'int'], ['open_drafts', N_('Drafts waiting at most'), 'int'],
  ['day_mails', N_('E-mails per 24 hours'), 'int'], ['day_withdraw', N_('Withdrawn drafts per 24 hours'), 'int'], ['review_wait_h', N_('Alarm when a draft waits longer than (hours)'), 'int']];
const ISS_ACT = {issuer_created: N_('set up'), issuer_changed: N_('settings changed'), issuer_key: N_('new key'), issuer_key_ended: N_('key ended'),
  issuer_pause: N_('paused'), issuer_resume: N_('resumed'), issuer_revoked: N_('revoked'), issuer_payee: N_('bank account added'),
  issuer_payee_gone: N_('bank account removed'), issuer_read: N_('read'), issuer_write: N_('wrote'), issuer_refused: N_('refused')};

async function issLoad() {
  if (ISS.loading) return;
  ISS.loading = true;
  try { ISS.data = await rawFetch('GET', '/api/office/issuers'); ISS.err = ''; ISS.off = false; }
  catch (x) { if (x.status === 404) ISS.off = true; else { ISS.data = {issuers: [], ranges: [], admin: false}; ISS.err = ofcErrHere(x); } }
  ISS.loading = false;
  issRedraw();
}
function issRedraw() { const b = $('#iss-box'); if (b) b.outerHTML = issHtml(); }
// 2.1391.0 (#7111): a number range added, changed or removed: the issuer block asks the server again (its ranges decide whether
// "Add invoice issuer" is possible) instead of keeping the old answer until a reload
function issFresh() { if (ISS.off) return; ISS.data = null; issRedraw(); }
const issDay = v => v ? fmtDate(String(v).slice(0, 10)) : '';

function issHtml() {
  if (typeof ofcAdmin !== 'function' || !ofcAdmin()) return '';
  const sig = String(OFC.info?.org_id ?? '');
  if (ISS.sig !== sig) { ISS.sig = sig; ISS.data = null; ISS.off = false; }
  if (ISS.off) return '';
  if (!ISS.data) { if (!ISS.loading) setTimeout(issLoad, 0); return `<div id="iss-box" class="onum issbox" data-fg-skip></div>`; }
  const d = ISS.data, adm = !!d.admin;
  const rows = (d.issuers || []).map(i => {
    const k = (i.keys || []).filter(x => x.valid).sort((a, b) => String(b.expires_at).localeCompare(String(a.expires_at)))[0];
    const used = (i.keys || []).map(x => x.last_used_at).filter(Boolean).sort().pop();
    const state = i.paused ? tr('Paused: {0}', i.paused_why || i.paused_reason) : k ? tr('Active') : tr('No valid key');
    const info = [i.range?.code ? tr('Range {0}', i.range.code) : '', k ? tr('key {0}… valid until {1}', k.prefix, issDay(k.expires_at)) : '',
      used ? tr('last used {0}', issDay(used)) : tr('not used yet'), i.allowed_ips?.length ? tr('{0} allowed addresses', i.allowed_ips.length) : tr('any address')].filter(Boolean).join(' · ');
    const id = String(i.id), btn = (a, icon, label) => `<button type="button" class="btn sm" data-iss="${esc(a)}" data-id="${esc(id)}">${ic(icon, 's')}<span>${esc(label)}</span></button>`;
    return `<div class="row issrow${i.paused ? ' isspaused' : ''}" data-iss-row="${esc(id)}"><label>${esc(i.name)}</label>
      <span class="lacts"><span class="${i.paused ? 'err' : 'muted'} ofcpv">${esc(state)}</span></span>
      <span class="muted ofchint">${esc(info)}</span>
      <span class="lacts onumacts">${/*html-ok*/ adm ? btn('key', 'plus', tr('New key')) + (i.paused ? btn('resume', 'play', tr('Resume')) : btn('pause', 'pause', tr('Pause')))
        + btn('edit', 'edit', tr('Edit')) + btn('payees', 'card', tr('Bank accounts')) : ''}${/*html-ok*/ btn('log', 'list', tr('Log'))}${/*html-ok*/ adm ? btn('revoke', 'trash', tr('Revoke')) : ''}</span></div>`;
  }).join('');
  const noRange = adm && !(d.ranges || []).length;
  return `<div id="iss-box" class="onum issbox" data-fg-skip><h4>${tr('Invoice issuers')}</h4>
    <p class="muted ofchint">${esc(tr('An outside system (a shop, a booking system) prepares invoice drafts in a number range with its own key; you check, finalise and send them here.'))}${d.environment === 'test' ? ' ' + esc(tr('This server gives out test keys.')) : ''}</p>
    ${/*html-ok*/ ISS.err ? errorState({sub: ISS.err, size: 'row'}) : ''}${/*html-ok*/ rows || `<p class="muted">${esc(tr('No invoice issuer yet.'))}</p>`}
    ${adm ? `<div class="row onumfoot"><span class="lacts"><button type="button" class="btn sm" data-iss="add" ${noRange ? 'disabled' : ''}>${ic('plus', 's')}<span>${tr('Add invoice issuer')}</span></button></span>
      ${noRange ? `<span class="muted ofchint">${esc(tr('Add a number range first: an issuer writes into its own range.'))}</span>` : ''}</div>` : ''}</div>`;
}

// a change that may ask for the sign-in confirmation: the password (pwPrompt) or a fresh sign-in (reauthFresh), then once more
async function issSend(method, url, b = {}) {
  try { return await rawFetch(method, url, b); } catch (x) {
    if (x.data?.reauth_needed) { if (!await reauthFresh(x.data)) { x.cancel = true; throw x; } return await rawFetch(method, url, b); }
    if (!x.data?.password_needed) throw x;
    const p = await pwPrompt(tr('Confirm with your password')); if (!p) { x.cancel = true; throw x; }
    return await rawFetch(method, url, {...b, password: p.password});
  }
}
const issFail = x => { if (!x.cancel) ofcErr(x); };
const issRow = id => (ISS.data?.issuers || []).find(x => String(x.id) === String(id));
const issVal = (md, id) => (/** @type {HTMLInputElement|null} */ ($('#' + id, md))?.value || '').trim();
const issOn = (md, id) => !!(/** @type {HTMLInputElement|null} */ ($('#' + id, md))?.checked);
const issIps = s => s.split(/[\s,]+/).map(x => x.trim()).filter(Boolean);

// the key is shown this once: a dialog with the key and a copy button
function issKeyShow(key) {
  askDialog({title: tr('The new key'), ok: tr('Done'), cancel: tr('Close'), html: `<p>${esc(tr('Copy the key now and store it in the outside system: Kalmido shows it only this once.'))}</p>
    <p><code class="topic isskey" id="iss-key">${esc(key)}</code></p><button type="button" class="btn sm" data-iss="copy">${ic('copy', 's')}<span>${tr('Copy')}</span></button>`,
  after: md => { $('[data-iss="copy"]', md)?.addEventListener('click', async () => { try { await navigator.clipboard.writeText(key); toast(tr('Copied')); } catch { toast(tr('Please copy the key by hand')); } }); }});
}

function issAddDialog() {
  const d = ISS.data || {}; let md0 = null;
  const f = (id, label, html, hint) => `<div class="row"><label for="${esc(id)}">${esc(label)}</label>${/*html-ok*/ html}${hint ? `<span class="muted ofchint">${esc(hint)}</span>` : ''}</div>`;
  const html = f('iss-name', tr('Name'), `<input id="iss-name" maxlength="80" placeholder="${esc(tr('e.g. Shop billing'))}">`)
    + f('iss-range', tr('Number range'), `<select id="iss-range">${(d.ranges || []).map(r => `<option value="${esc(String(r.id))}">${esc(r.code + (r.name ? ' · ' + r.name : ''))}</option>`).join('')}</select>`, tr('cannot be changed later'))
    + f('iss-ips', tr('Allowed addresses'), `<input id="iss-ips" autocomplete="off" spellcheck="false" placeholder="203.0.113.10, 198.51.100.0/24">`,
      d.address_needed ? tr('required for a live key: the addresses of the outside system') : tr('empty = any address; recommended as soon as the outside system has fixed addresses'))
    + (d.address_needed ? `<label class="chk"><input type="checkbox" id="iss-any"> ${esc(tr('Allow any address (not recommended)'))}</label>` : '')
    + f('iss-days', tr('Key valid for (days)'), `<input id="iss-days" class="numin" inputmode="numeric" value="${esc(String(d.days_max || 365))}">`, tr('at most {0} days', d.days_max || 365))
    + `<p class="muted ofchint">${esc(tr('The issuer only prepares drafts; a person finalises and sends them. Limits can be changed after setting it up.'))}</p>`;
  askDialog({title: tr('Add invoice issuer'), html, ok: tr('Add'), cancel: tr('Cancel'), after: md => { md0 = md; }, submit: async () => {
    const b = {name: issVal(md0, 'iss-name'), range_id: +issVal(md0, 'iss-range'), valid_days: +issVal(md0, 'iss-days') || undefined};
    const ips = issVal(md0, 'iss-ips');
    if (issOn(md0, 'iss-any')) b.any_address = true; else if (ips || d.address_needed) b.allowed_ips = issIps(ips);
    try { const j = await issSend('POST', '/api/office/issuers', b); OFC.log = null; issLoad(); setTimeout(() => issKeyShow(j.key), 0); return true; }
    catch (x) { issFail(x); return false; }
  }});
}

function issEditDialog(i) {
  if (!i) return; let md0 = null;
  const d = ISS.data || {};
  const f = (id, label, html, hint) => `<div class="row"><label for="${esc(id)}">${esc(label)}</label>${/*html-ok*/ html}${hint ? `<span class="muted ofchint">${esc(hint)}</span>` : ''}</div>`;
  const lim = ISS_LIM.map(([k, label, kind]) => f('iss-l-' + k, tr(label), `<input id="iss-l-${esc(k)}" class="numin" inputmode="${kind === 'money' ? 'decimal' : 'numeric'}" value="${esc(String(i.limits?.[k] ?? ''))}">`,
    tr('0 = nothing allowed, at most {0}', String(d.limit_max?.[k] ?? '')))).join('');
  const html = f('iss-name', tr('Name'), `<input id="iss-name" maxlength="80" value="${esc(i.name)}">`)
    + f('iss-ips', tr('Allowed addresses'), `<input id="iss-ips" autocomplete="off" spellcheck="false" value="${esc((i.allowed_ips || []).join(', '))}">`, tr('empty = any address'))
    + (d.address_needed ? `<label class="chk"><input type="checkbox" id="iss-any" ${(i.allowed_ips || []).length ? '' : 'checked'}> ${esc(tr('Allow any address (not recommended)'))}</label>` : '')
    + `<h4>${esc(tr('Limits'))}</h4>${/*html-ok*/ lim}<p class="muted ofchint">${esc(tr('Raising a limit or loosening the address rule asks for your password.'))}</p>`
    + ((i.addresses || []).length ? `<h4>${esc(tr('Used from'))}</h4><ul class="issips">${i.addresses.map(a => `<li>${esc(a.ip)} · ${esc(tr('last {0}', issDay(a.last_at)))} · ${esc(tr('{0} calls', a.calls))}</li>`).join('')}</ul>` : '');
  askDialog({title: tr('Invoice issuer {0}', i.name), html, ok: tr('Save'), cancel: tr('Cancel'), after: md => { md0 = md; }, submit: async () => {
    const limits = {}; for (const [k] of ISS_LIM) { const v = issVal(md0, 'iss-l-' + k).replace(',', '.'); if (v !== String(i.limits?.[k] ?? '')) limits[k] = v; }
    const b = {name: issVal(md0, 'iss-name'), limits};
    const ips = issIps(issVal(md0, 'iss-ips'));
    if (issOn(md0, 'iss-any')) b.any_address = true; else if (ips.join(',') !== (i.allowed_ips || []).join(',')) b.allowed_ips = ips;
    try { await issSend('PATCH', `/api/office/issuers/${i.id}`, b); toast(tr('Saved')); OFC.log = null; issLoad(); return true; }
    catch (x) { issFail(x); return false; }
  }});
}

async function issNewKey(i) {
  if (!i) return;
  const d = ISS.data || {}; let md0 = null;
  const html = `<p>${esc(tr('The current key keeps working for the overlap, so the outside system can switch over.'))}</p>
    <div class="row"><label for="iss-ov">${esc(tr('Overlap (days)'))}</label><input id="iss-ov" class="numin" inputmode="numeric" value="${esc(String(d.overlap_default ?? 7))}"><span class="muted ofchint">${esc(tr('0 to {0} days; 0 = the current key ends now', d.overlap_max ?? 14))}</span></div>`;
  askDialog({title: tr('New key for {0}', i.name), html, ok: tr('Create key'), cancel: tr('Cancel'), after: md => { md0 = md; }, submit: async () => {
    try { const j = await issSend('POST', `/api/office/issuers/${i.id}/keys`, {overlap_days: +issVal(md0, 'iss-ov') || 0}); OFC.log = null; issLoad(); setTimeout(() => issKeyShow(j.key), 0); return true; }
    catch (x) { issFail(x); return false; }
  }});
}

async function issLogDialog(i) {
  if (!i) return;
  let rows = [];
  try { rows = (await rawFetch('GET', `/api/office/issuers/${i.id}/log`)).log || []; } catch (x) { issFail(x); return; }
  const line = r => `<li><span class="muted">${esc(issDay(r.at))} ${esc(String(r.at).slice(11, 16))}</span> · ${esc(r.by === 'issuer' ? tr('Issuer') : r.user_name)} · ${esc(tr(ISS_ACT[r.action] || r.action))}${r.target && r.target !== 'issuer' ? ' · ' + esc(r.target) : ''}</li>`;
  askDialog({title: tr('Log of {0}', i.name), ok: tr('Close'), cancel: tr('Close'), after: () => {}, html: rows.length ? `<ul class="isslog">${/*html-ok*/ rows.map(line).join('')}</ul>` : `<p class="muted">${esc(tr('No entries yet.'))}</p>`});
}

async function issPayeesDialog(i) {
  if (!i) return;
  let rows = [];
  try { rows = (await rawFetch('GET', `/api/office/issuers/${i.id}/payees`)).payees || []; } catch (x) { issFail(x); return; }
  let md0 = null;
  const list = rows.map(p => `<li>${esc(p.label)} · ${esc(p.holder)} · ${esc(p.iban)}${p.bic ? ' · ' + esc(p.bic) : ''}${p.ref_only ? ' · ' + esc(tr('only with reference')) : ''}
    <button type="button" class="btn sm" data-iss-pdel="${esc(String(p.id))}">${ic('trash', 's')}<span>${tr('Remove')}</span></button></li>`).join('');
  const html = `<p class="muted ofchint">${esc(tr('The accounts the issuer may select for a payment notice (by number only; it never reads them).'))}</p>${list ? `<ul class="isspay">${/*html-ok*/ list}</ul>` : ''}
    <h4>${esc(tr('Add bank account'))}</h4>
    <div class="row"><label for="iss-p-label">${esc(tr('Name'))}</label><input id="iss-p-label" maxlength="80"></div>
    <div class="row"><label for="iss-p-holder">${esc(tr('Account holder'))}</label><input id="iss-p-holder" maxlength="70"><span class="muted ofchint">${esc(tr('exactly as the bank has it'))}</span></div>
    <div class="row"><label for="iss-p-iban">IBAN</label><input id="iss-p-iban" autocomplete="off" spellcheck="false"></div>
    <div class="row"><label for="iss-p-bic">BIC</label><input id="iss-p-bic" autocomplete="off" spellcheck="false"></div>
    <label class="chk"><input type="checkbox" id="iss-p-ref"> ${esc(tr('A payment can only be matched by its reference'))}</label>`;
  askDialog({title: tr('Bank accounts of {0}', i.name), html, ok: tr('Add'), cancel: tr('Close'), after: md => {
    md0 = md;
    md.addEventListener('click', async e => {
      const b = /** @type {any} */ (e.target).closest?.('[data-iss-pdel]'); if (!b) return;
      try { await rawFetch('DELETE', `/api/office/issuers/${i.id}/payees/${b.dataset.issPdel}`); toast(tr('Removed')); b.closest('li')?.remove(); } catch (x) { issFail(x); }
    });
  }, submit: async () => {
    const b = {label: issVal(md0, 'iss-p-label'), holder: issVal(md0, 'iss-p-holder'), iban: issVal(md0, 'iss-p-iban'), bic: issVal(md0, 'iss-p-bic'), ref_only: issOn(md0, 'iss-p-ref')};
    try { await issSend('POST', `/api/office/issuers/${i.id}/payees`, b); toast(tr('Saved')); issLoad(); return true; } catch (x) { issFail(x); return false; }
  }});
}

async function issAct(a, i) {
  if (!i) return;
  try {
    if (a === 'pause') {
      if (!await askConfirm(tr('Pause {0}?', i.name), tr('Every call of its keys is refused until you resume it; the outside system can repeat them later.'), {ok: tr('Pause')})) return;
      await rawFetch('POST', `/api/office/issuers/${i.id}/pause`);
    } else if (a === 'resume') await issSend('POST', `/api/office/issuers/${i.id}/resume`);
    else if (a === 'revoke') {
      if (!await askConfirm(tr('Revoke {0}?', i.name), tr('Its keys stop working at once and permanently; its drafts stay in the office.'), {ok: tr('Revoke'), danger: true})) return;
      await rawFetch('DELETE', `/api/office/issuers/${i.id}`);
    }
    OFC.log = null; toast(tr('Saved')); issLoad();
  } catch (x) { issFail(x); }
}

document.addEventListener('click', e => {
  const b = /** @type {any} */ (e.target).closest?.('#iss-box [data-iss]'); if (!b) return;
  const a = b.dataset.iss, i = issRow(b.dataset.id);
  if (a === 'add') issAddDialog();
  else if (a === 'edit') issEditDialog(i);
  else if (a === 'key') issNewKey(i);
  else if (a === 'log') issLogDialog(i);
  else if (a === 'payees') issPayeesDialog(i);
  else issAct(a, i);
});
if (typeof OA_LOG_TG === 'object') OA_LOG_TG.issuer = N_('Invoice issuers');  // the office log names the target
