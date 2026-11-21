// @ts-check
/* Kalmido web client: "Report a problem" (#7531): the dialog of the shared intake (server: integrations/meldung.py).
   A bug asks "Problem" and "Expected", a wish "What do you want to do?" and "What is in the way today?" (required) and "How
   should it work?". Below the fields the context block (clienterr.js cer_ctx: page, version, device, the last errors and failed
   requests - no contents) is shown as it will go, with a box to leave it out. Under the form: what was already reported at
   this place, with its state (open ones first, done ones dimmed) - mechanically from the task (meldung.py RPT_STATE).
   Opened by setcore.js rptOpen when the server takes reports (S.about.client_errors). Loaded on demand (lazyload.js LD_MODS.report).
   Classic script sharing the global scope with the others (load order: index.html, docs/ARCHITECTURE.md). */
'use strict';
/** @type {Record<string, string>} */
const RPT_STATES = {open: N_('Open'), working: N_('In progress'), fixed: N_('Fixed'), wont: N_('Will not be done')};
/** The place of a report: the page with its numbers as "n" (a task's page is one place, whatever the task). */
const rpt_place = () => cer_route().replace(/\/\d+(?=\/|$)/g, '/n');
/** The rows of the context block as [label, value] (texts only; rpt_ctxHtml escapes them). @param {any} c the context block */
function rpt_ctxRows(c) {
  const d = c.device || {};
  const dev = [d.platform, d.browser, d.width && d.height ? `${d.width} × ${d.height}` : '', d.dpr && d.dpr !== 1 ? `@${d.dpr}x` : '', d.touch ? tr('touch') : ''].filter(Boolean).join(', ');
  return [[tr('Page'), c.route], [tr('Version'), c.version], [tr('Device'), dev],
    ...(c.errors.length ? c.errors.map((/** @type {any} */ e) => [tr('Error'), e.msg + (e.place ? ' · ' + e.place : '')]) : [[tr('Errors'), tr('none')]]),
    ...(c.requests.length ? c.requests.map((/** @type {any} */ q) => [tr('Failed request'), `${q.method} ${cer_reqPath(q.path) /* only shown masked (F11) */} · ${q.status || tr('no answer')} · ${q.ms} ms`]) : [[tr('Failed requests'), tr('none')]])].filter(r => r[1]);
}
const rpt_ctxHtml = (/** @type {any} */ c) => `<ul class="rptctx">${rpt_ctxRows(c).map(([k, v]) => `<li><b>${esc(k)}</b> <span>${esc(v)}</span></li>`).join('')}</ul>`;
/** @param {any[]} items */
function rpt_listHtml(items) {
  if (!items.length) return '';
  return `<h4 class="rpth">${tr('Already reported')}</h4><ul class="rptlist">${items.map(x => `<li class="rpt-${esc(x.state)}${x.state === 'fixed' || x.state === 'wont' ? ' rptdone' : ''}"><span class="rpts">${esc(tr(RPT_STATES[x.state] || RPT_STATES.open))}</span><span class="rptt">${esc(x.title || tr(x.kind === 'wish' ? 'A wish' : 'Something is wrong'))}</span><span class="muted">${esc([x.mine ? tr('by you') : '', x.here ? '' : x.place, fmtWhen(x.created_at)].filter(Boolean).join(' · '))}</span></li>`).join('')}</ul>`;
}
/** @type {Record<string, [string, string, string, boolean][]>} */
const RPT_F = {bug: [['problem', N_('Problem'), N_('What happened?'), true], ['expected', N_('Expected'), N_('What should have happened?'), true]],
  wish: [['want', N_('What do you want to do?'), '', true], ['blocker', N_('What is in the way today?'), '', true], ['how', N_('How should it work?'), N_('optional'), false]]};
function rpt_open() {
  const ctx = cer_ctx(), place = rpt_place();
  let kind = 'bug';
  /** @type {Record<string, string>} */
  const vals = {};
  const fields = () => RPT_F[kind].map(([k, l, ph, need]) => `<div class="row rptf"><label for="rpt-${esc(k)}">${esc(tr(l))}${need ? ' *' : ''}</label><textarea id="rpt-${esc(k)}" data-rptf="${esc(k)}" rows="3" maxlength="4000"${need ? ' required aria-required="true"' : ''} placeholder="${esc(ph ? tr(ph) : '')}">${esc(vals[k] || '')}</textarea></div>`).join('');
  /** @type {any} */
  const md = modal(`<h3>${tr('Report a problem')}</h3>
    <div class="seg rptkind" role="group" aria-label="${esc(tr('Kind'))}"><button type="button" data-rptk="bug" class="on" aria-pressed="true">${tr('Something is wrong')}</button><button type="button" data-rptk="wish" aria-pressed="false">${tr('A wish')}</button></div>
    <div id="rpt-fields">${/*html-ok*/ fields() /* labels and values escaped in fields() */}</div>
    <div class="row rptctxrow"><label></label><div><label class="chk"><input type="checkbox" id="rpt-ctx" checked> ${tr('Send these details along')}</label>
      <details class="rptctxd"><summary class="muted">${tr('What goes along')}</summary>${/*html-ok*/ rpt_ctxHtml(ctx) /* every text escaped in rpt_ctxHtml */}</details>
      <div class="shelp">${esc(tr('No texts of your tasks, documents or inputs. Your name goes along so the team can ask back.'))} ${esc(tr('People of your organisations see only that something was reported here and its state, never your words.'))}</div></div></div>
    <div id="rpt-list" aria-live="polite"></div>
    <div class="foot"><span class="spacer"></span><button type="button" class="btn" data-rptm="close">${tr('Cancel')}</button><button type="button" class="btn pri" data-rptm="send">${ic('send', 's')} ${tr('Send')}</button></div>`);
  md.classList.add('rptdlg');
  const keep = () => { for (const t of $$('[data-rptf]', md)) vals[t.dataset.rptf] = t.value; };
  const load = () => api('GET', '/api/reports?place=' + encodeURIComponent(place)).then((/** @type {any} */ j) => { const l = $('#rpt-list', md); if (l) l.innerHTML = rpt_listHtml(j.items || []); }).catch(() => {});
  load();
  md.addEventListener('click', async (/** @type {any} */ e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.rptk && b.dataset.rptk !== kind) {
      keep(); kind = b.dataset.rptk;
      for (const x of $$('[data-rptk]', md)) { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', String(x === b)); }
      $('#rpt-fields', md).innerHTML = fields(); $('[data-rptf]', md)?.focus(); // sprung-ok: the person switched the kind, the first field of the new kind takes the focus
      return;
    }
    if (b.dataset.rptm === 'close') { md.remove(); return; }
    if (b.dataset.rptm !== 'send' || b.disabled) return;
    keep();
    const miss = RPT_F[kind].find(([k, , , need]) => need && !(vals[k] || '').trim());
    if (miss) { const t = $(`#rpt-${miss[0]}`, md); t?.focus(); t?.setAttribute('aria-invalid', 'true'); toast(tr('Please fill in: {0}', tr(miss[1]))); return; } // sprung-ok: Send with an empty required field: the field asks for it
    /** @type {Record<string, any>} */
    const body = {kind, place, context: $('#rpt-ctx', md)?.checked ? ctx : null};
    for (const [k] of RPT_F[kind]) if ((vals[k] || '').trim()) body[k] = vals[k].trim();
    b.disabled = true;
    try { await api('POST', '/api/reports', body); }
    catch (/** @type {any} */ x) { b.disabled = false; if (x?.status === 409) { md.remove(); if (hostedOn()) supContact(true); else openExt(ABOUT_LINKS[2][0]); } return; }
    md.remove(); toast(tr('Thanks, it is reported. Its state shows here under Report a problem.'));
  });
  if (!isTouch()) setTimeout(() => $('[data-rptf]', md)?.focus(), 50); // sprung-ok: the dialog just opened (desktop): its first field
}
