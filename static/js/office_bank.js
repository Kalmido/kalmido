// 2.90.0 B (#1921): bank reconciliation in the office (tab "Bank", admins of the office area only): import a statement
// (CSV export of the bank with a column mapping like the household budget, CAMT.052 / .053 XML or MT940), then match every booking
// with one tap: money in -> an open invoice (a payment is recorded; less than open = partly paid), money out -> a receipt
// (its payment day), or private / ignore. Every step has its undo; an import can be taken back while none of it is matched.
// Server: kalmido/office/bank.py. No bank access.
const BNK = {oid: null, fints: null, state: 'open', data: null, q: '', err: null, imports: null, showImp: false, other: null, cand: null, candQ: '', busy: false, split: false};
// 2.616.0 (#2473): the direct bank fetch over FinTS (office_fints.js, loaded on its first use): BNK.fints = GET /api/office/bank/fints
// ({on, message}); off (no product registration on the server) no button (2.1324.0 #6147), the foot line says it
const bnkFntHtml = () => {
  const f = BNK.fints;
  if (!f) { if (f === null) { BNK.fints = false; api('GET', '/api/office/bank/fints').then(j => { BNK.fints = j; }, () => { BNK.fints = {on: false, message: ''}; }).then(() => ofcDraw()); } return ''; }
  // 2.1324.0 (#6147): only when it is set up (was: switched off with a sentence, it looked active); the line at the foot says
  // "No bank access: only the file you download yourself"; on a phone it sits in the bar's "More" (bnkBarMenu)
  return f.on ? `<button class="btn bnk-wide" data-bnk="fints">${ic('download', 's')}<span>${tr('Fetch from bank')}</span></button>` : '';
};
// 2.1324.0 (#6147): the bank bar on a phone: "Import bank statement" + "More" in one row (the filters below); "More" holds
// "Go through", "Fetch from bank" (set up only), "Imports" and the bank accounts -- on a computer these stay in the bar
function bnkBarMenu(anchor) {
  const n = BNK.data?.counts || {}, tax = tr('Settings › Company & office › {0}', tr(OST_SUBS.find(x => x[0] === 'tax')?.[2] || 'Company & office'));
  menu(anchor, [
    n.open ? {label: tr('Go through'), icon: 'right', act: 'bnk-walk', fn: () => wlk_open('bnk')} : null,
    BNK.fints?.on ? {label: tr('Fetch from bank'), icon: 'download', act: 'bnk-fints', fn: () => fnt_open()} : null,
    {label: tr('Imports'), icon: 'list', act: 'bnk-imps', on: BNK.showImp, fn: () => { BNK.showImp = !BNK.showImp; ofcDraw(); }},
    {label: tr('Bank accounts'), sub: tax, icon: 'gear', act: 'bnk-accts', fn: () => settingsModal('biz-tax')}].filter(Boolean), null, null, tr('Bank'));
}
OFC_TABS.splice(OFC_TABS.findIndex(t => t[0] === 'settings'), 0, ['bank', 'bank', N_('Bank'), 1, () => bnkHtml(), 'money']);  // admins only; 2.92.1 (#1917): in the menu group Money
const BNK_KIND = {invoice: N_('Invoice'), receipt: N_('Receipt'), private: N_('Private'), ignored: N_('Ignored'), noreceipt: N_('No receipt needed'), card: N_('Credit card statement'), payout: N_('Collective payout'), cash: N_('Cash box transfer')};  // 2.299.0 C (#3192): noreceipt; 2.444.0 (#3447): card; 2.603.0 (#4927): cash

async function bnkLoad() {
  const q = 'state=' + BNK.state; BNK.q = q;
  try { const j = await api('GET', '/api/office/bank/tx?' + q); if (BNK.q === q) { BNK.data = j; BNK.err = null; } }
  catch (x) { BNK.err = ofcErrHere(x); }
  if (BNK.showImp) await bnkImpLoad(false);
  ofcDraw();
}
async function bnkImpLoad(draw = true) {
  try { BNK.imports = (await api('GET', '/api/office/bank/imports')).items || []; BNK.impErr = null; } catch (x) { BNK.imports = []; BNK.impErr = ofcErrHere(x); }  // 2.1076.0 (#5450): a failure is no "No imports yet"
  if (draw) ofcDraw();
}
// 2.114.1 B (#2016): every bank write (match, unmatch, their undo/redo, an import taken back / restored) changes the books, the cash
// flow, the key figures and the paid state of invoices: their loaded data goes, each tab loads again when it is opened
const bfbBooksStale = () => {
  if (typeof BK === 'object') { BK.info = null; BK.euer = null; BK.ustva = null; }
  if (typeof RKF === 'object') RKF.data = null;
  if (typeof KPS === 'object') KPS.data = null;
  if (typeof OFD === 'object') OFD.list = null;
};
// #7495: a write, an undo or the switch Open / Matched keeps the bookings on screen (dimmed) until the fresh ones are there
// (the imports with them when they are open)
async function bnkGet() {
  const q = 'state=' + BNK.state, imp = !!BNK.showImp; BNK.q = q;
  const [j, im] = await Promise.all([api('GET', '/api/office/bank/tx?' + q), imp ? api('GET', '/api/office/bank/imports').catch(x => ({err: ofcErrHere(x)})) : null]);
  return () => { if (BNK.q !== q) return; BNK.data = j; BNK.err = null; if (im) { BNK.imports = im.items || []; BNK.impErr = im.err || null; } };  // (#5450): a failure is no "No imports yet"
}
const bnk_norc = () => typeof BNR === 'object' && BNK.state === 'norc';
const bnk_refetch = () => ofcRefetch('bank', ofcTab() === 'bank' && !!BNK.data && !bnk_norc(), bnkGet, () => { BNK.data = null; });
const bnkReload = () => { BNK.imports = BNK.showImp ? BNK.imports : null; BNK.other = null; BNK.cand = null; bfbBooksStale(); bnk_refetch(); };
// 2.979.0 (#5667): an undo / redo the server did: the bank bookings and imports come again (with the books, cash flow and key figures)
histReloader('bank', () => { if (!BNK.data && !BNK.imports) return; BNK.imports = null; bnkReload(); });
const bnkAmt = v => `${+v > 0 ? '+' : '−'}${ofcMoney(Math.abs(+v))}`;

// 2.855.0 (#5456): the page links the bank accounts (IBAN, default account: Settings › Company & office › Bank & taxes)
function bnkHtml() {
  if (BNK.oid !== OFC.info?.org_id) { Object.assign(BNK, {oid: OFC.info?.org_id, data: null, imports: null, err: null, other: null, cand: null, fints: null}); BNK_W?.reset(); }  // #7497: + the rows' marks  // (#2473): + fints  // another office area
  if (!ofcAdmin()) return ofcLockedHtml();  // 2.356.0 D (#3006): why, and the way to hand in receipts
  if (BNK.err) return ofcFail(BNK.err, () => { BNK.err = null; BNK.data = null; });  // 2.1076.0 (#5450): the reason + "Try again"
  const norc = typeof BNR === 'object' && bnr_route() && BNK.state === 'norc';  // 2.299.0 C (#3192): #office/bank/norc (the reminder task's link)
  if (!norc && !BNK.data) { setTimeout(() => { if (!BNK.data) bnkLoad(); }, 0); return loadingHtml('big'); }
  if (!norc && BNK.q !== 'state=' + BNK.state) setTimeout(() => { if (BNK.q !== 'state=' + BNK.state) bnk_refetch(); }, 0);  // #7495: Open / Matched: the old rows dimmed until the new ones are there
  const d = BNK.data || {}, n = d.counts || {};
  const segs = [['open', tr('Open|payment state'), n.open], ['matched', tr('Matched'), n.matched], ['all', tr('All'), null]];
  if (typeof BNR === 'object') segs.splice(1, 0, ['norc', tr('Without receipt'), BNR.data?.counts?.out]);  // 2.299.0 C (#3192)
  const bar = `<div class="ofcbar bnkbar"><button class="btn pri" data-bnk="imp">${ic('upload', 's')}<span>${tr('Import bank statement')}</span></button>${bnkFntHtml()}<span class="spacer"></span>
    <div class="seg" role="group" aria-label="${esc(tr('Show'))}">${segs.map(([k, t, c]) => `<button type="button" data-bnk="state" data-v="${k}" class="${BNK.state === k ? 'on' : ''}" aria-pressed="${BNK.state === k}">${esc(t)}${c ? ` <small>${c}</small>` : ''}</button>`).join('')}</div>
    ${n.open ? `<button class="btn bnk-wide" data-bnk="walk">${ic('right', 's')}<span>${tr('Go through')}</span></button>` : ''}<button class="btn ghost bnk-wide" data-bnk="imps" aria-expanded="${BNK.showImp}">${ic('list', 's')}<span>${tr('Imports')}</span></button>
    <button type="button" class="btn ghost bnk-mbtn" data-bnk="menu" aria-haspopup="menu">${ic('dots', 's')}<span>${tr('More')}</span></button></div>`;  // 2.1324.0 (#6147): phone only
  if (norc) return bar + (BNK.showImp ? bnkImpHtml() : '') + bnr_html();
  const items = d.items || [];
  const list = items.length ? `<ul class="bnklist" role="list">${items.map(bnkRow).join('')}</ul>`
    : BNK.state === 'open' && (n.open || 0) + (n.matched || 0) ? emptyState({icon: 'check', title: tr('Every booking is matched.')})  // 2.1076.0 (#5450)
      : emptyState({icon: 'bank', title: tr('No bookings yet. Import the statement you download from your bank (CSV, CAMT or MT940).'), action: `<div class="eacts"><button type="button" class="btn pri" data-bnk="imp">${ic('upload', 's')}<span>${tr('Import bank statement')}</span></button></div>`});
  // 2.809.0 (#5452): the hint for a missing receipt once above the list (was in every row without a suggestion)
  // 2.1324.0 (#6147): folds to its question with one tap, and stays folded (LS bnkMissShut, the toggle listener below)
  const miss = items.some(t => !t.match && +t.amount < 0 && !(t.suggestions || []).length) ? `<details class="muted bnkmiss bnkmiss1" data-bnk-miss ${LS.get('bnkMissShut', false) ? '' : 'open'}><summary>${tr('Receipt missing?')}</summary> <span>${tr('Upload it in the documents of the office, then match it here.')}</span></details>` : '';
  return bar + ofcSetLink('tax', tr('Bank accounts')) + (BNK.showImp ? bnkImpHtml() : '') + (typeof brl_sugHtml === 'function' ? brl_sugHtml() : '') + miss + list + `<div class="muted ofchint bnkfoot">${BNK.fints?.on ? tr('Bank access only when you fetch, with your PIN every time.') : tr('No bank access: only the file you download yourself.')/* 2.616.0 (#2473) */}<div class="shint">${tr('A match with an invoice records a payment; with a receipt it sets its payment day.')}</div></div>`;  // 2.298.0 A2 (#3186): the matching rule behind (i)
}
function bnkRow(t) {
  const inn = +t.amount > 0;
  const head = `<div class="bnkhead"><span class="bnkn"><b>${esc(t.counterpart || t.purpose || tr('Booking'))}</b><small class="muted">${esc([fmtDateLoc(t.day), t.counterpart ? t.purpose : ''].filter(Boolean).join(' · '))}</small></span>
    <span class="bnkamt ${inn ? 'in' : 'out'}">${esc(bnkAmt(t.amount))}</span></div>`;
  let act;
  if (t.match) {
    // 2.355.0 B (#2843): a split names its invoices and the rest of the booking (an overpayment)
    const rest = t.match.rest && +t.match.rest > 0 ? ` · ${tr('overpaid {0}', ofcMoney(t.match.rest))}` : '';
    act = `<div class="bnkacts"><span class="rotag bnkm">${ic('check', 's')} ${esc(tr(BNK_KIND[t.match.kind] || t.match.kind))}${t.match.label ? ` · ${esc(t.match.label)}` : ''}${esc(rest)}</span>${typeof brl_byRule === 'function' ? brl_byRule(t.match) : ''}<span class="spacer"></span>
      ${t.match.kind === 'invoice' ? `<a class="btn sm ghost" href="#office/invoices/${t.match.id}">${tr('Open')}</a>` : ''}<button class="btn sm ghost" data-bnk="unmatch" data-id="${t.id}">${ic('undo', 's')}<span>${tr('Undo match')}</span></button></div>`;
  } else {
    // 2.778.0 (#5383): the suggestions as candidate cards (office_cand.js), the best first, instead of the first one as text
    const sg = t.suggestions || [];
    const sug = sg.length ? `<div class="bnksug"><small class="muted">${tr('Suggestion')}</small>${/*html-ok*/ ocd_row(sg.map(s => ocd_card({...s, label: s.label || tr(BNK_KIND[s.kind] || 'Receipt')}, {btn: `data-bnk="match" data-id="${t.id}" data-kind="${esc(s.kind)}" data-mid="${s.id}"`})).join(''))}</div>` : '';
    // 2.809.0 (#5452): one row of buttons -- another receipt / invoice and "More" (private, ignore, no receipt needed, cash box
    // transfer with one line of explanation each, bnkMoreMenu); before five equal buttons in two rows on a phone
    act = `${typeof brl_rowHint === 'function' ? brl_rowHint(t) : ''}${sug}<div class="bnkacts"><button class="btn sm" data-bnk="other" data-id="${t.id}" aria-expanded="${BNK.other === t.id}">${ic('search', 's')}<span>${inn ? tr('Other invoice…') : tr('Other receipt…')}</span></button>
      <button data-rowmenu="bnkrow" type="button" class="btn sm ghost bnkmore" data-bnk="more" data-id="${t.id}" aria-haspopup="menu">${ic('dots', 's')}<span>${tr('More')}</span></button></div>
      ${BNK.other === t.id ? bnkOtherHtml(t) : ''}`;
  }
  const W = bnkW();  // #7497: the row's state ("Saving…" / "Not saved - Try again", the core's mark, escaped there)
  return `<li class="bnkrow ${t.match ? 'done' : ''}${esc(rwCls(W, t))}" data-tx="${t.id}" data-rwk="${esc(rwKey(t))}">${head}${act}${/*html-ok*/ rwMarkHtml(W, t)}</li>`;
}
// 2.809.0 (#5452): the marks of a booking without a receipt / invoice behind "More" (phone: a sheet), each with what it does
function bnkMoreMenu(anchor, tid) {
  const it = (kind, sub) => ({label: tr(BNK_KIND[kind]), sub, act: `bnk-${kind}`, fn: () => bnkMatch(tid, kind)});
  menu(anchor, [
    {...it('private', tr('Private withdrawal or deposit: neither expense nor income of the business')), label: tr('Private')},
    {...it('noreceipt', tr('A business payment without a receipt, e.g. bank fees or tax: it counts in the books')), label: tr('No receipt needed')},
    {...it('ignored', tr('Left out of the books entirely, e.g. a transfer between your own accounts')), label: tr('Ignore')},
    it('cash', tr('Cash withdrawal or cash paid in: a transfer between the bank and the cash book, no expense'))], null, null, tr('Mark booking'));
}
function bnkOtherHtml(t) {
  const c = BNK.cand;
  if (+t.amount > 0 && BNK.split) return bnkSplitHtml(t, c);
  const rows = BNK.candErr ? ofcFail(BNK.candErr, () => { BNK.candErr = null; bnkCand(t.id); }, 'row') : !c ? loadingHtml('row') : !c.length ? ofcNoHit('', 'row')  // 2.1076.0 (#5450)
    : ocd_row(c.map(x => ocd_card({...x, label: x.label || tr(BNK_KIND[x.kind])}, {btn: `data-bnk="match" data-id="${t.id}" data-kind="${esc(x.kind)}" data-mid="${x.id}"`, sub: x.kind === 'invoice' ? (x.refund ? tr('refund open') : tr('open')) : ''})).join(''), 'ocdgrid');  // 2.778.0 (#5383): cards, not a text list
  const sp = +t.amount > 0 ? `<button type="button" class="btn sm ghost" data-bnk="split" data-id="${t.id}">${tr('Split across invoices…')}</button>` : '';
  return `<div class="bnkother"><input type="search" class="bnkq" data-bnk-q="${t.id}" value="${esc(BNK.candQ)}" placeholder="${esc(+t.amount > 0 ? tr('Number or client') : tr('Name of the receipt'))}" aria-label="${esc(tr('Search'))}">${rows}${sp}</div>`;
}
// 2.355.0 B (#2843): one booking on several invoices (a collective transfer) or more than the open amount: an amount per
// invoice, the rest of the booking stays visible as overpaid (server: bank.py bnk_parts)
function bnkSplitHtml(t, c) {
  const rows = BNK.candErr ? ofcFail(BNK.candErr, () => { BNK.candErr = null; bnkCand(t.id); }, 'row') : !c ? loadingHtml('row') : !c.length ? ofcNoHit('', 'row')  // 2.1076.0 (#5450)
    : `<ul class="ofclist" role="list">${c.map(x => `<li class="ofcrow"><span class="ofcn"><b>${esc(x.label)}</b><small class="muted">${esc(fmtDateLoc(x.date))} · ${tr('open')} ${ofcMoney(x.amount)}</small></span><input class="numin" inputmode="decimal" maxlength="16" data-bnk-part="${x.id}" data-open="${esc(x.amount)}" value="${esc(BNK.parts?.[x.id] ?? '')}" aria-label="${esc(tr('Amount for {0}', x.label))}" placeholder="${esc(ofcMoney(x.amount))}"></li>`).join('')}</ul>`;
  return `<div class="bnkother"><input type="search" class="bnkq" data-bnk-q="${t.id}" value="${esc(BNK.candQ)}" placeholder="${esc(tr('Number or client'))}" aria-label="${esc(tr('Search'))}">${rows}
    <div class="bnkacts"><span class="muted" data-bnk-rest="${t.id}" data-amount="${esc(t.amount)}">${esc(bnkSplitRest(t.amount))}</span><span class="spacer"></span><button type="button" class="btn sm ghost" data-bnk="split" data-id="${t.id}">${tr('Cancel')}</button><button type="button" class="btn sm pri" data-bnk="splitgo" data-id="${t.id}">${tr('Assign match')}</button></div></div>`;
}
function bnkSplitRest(amount) {
  const sum = Object.values(BNK.parts || {}).reduce((a, v) => a + (ofcNum(v) || 0), 0);
  return tr('Assigned {0} · rest {1}', ofcMoney(Math.round(sum * 100) / 100), ofcMoney(Math.round((+amount - sum) * 100) / 100));
}
function bnkImpHtml() {
  if (!BNK.imports) { setTimeout(() => bnkImpLoad(), 0); return loadingHtml('sec'); }
  if (BNK.impErr) return ofcFail(BNK.impErr, () => { BNK.impErr = null; BNK.imports = null; }, 'sec');  // 2.1076.0 (#5450)
  if (!BNK.imports.length) return emptyState({title: tr('No imports yet.'), size: 'sec', cls: 'bnkimps'});
  return `<ul class="ofclist bnkimps" role="list">${BNK.imports.map(i => `<li class="ofcrow ${i.undone_at ? 'arch' : ''}"><span class="ofcn"><b>${esc(i.filename || i.fmt.toUpperCase())}</b><small class="muted">${esc([fmtDateLoc(i.created_at.slice(0, 10)), trn('{0} booking', '{0} bookings', i.count), i.dup_count ? trn('{0} already there', '{0} already there', i.dup_count) : '', i.undone_at ? tr('undone') : ''].filter(Boolean).join(' · '))}</small></span>
    ${i.undone_at ? '' : `<button class="btn sm ghost" data-bnk="impundo" data-id="${i.id}">${tr('Undo|import')}</button>`}</li>`).join('')}</ul>`;
}

// ---- actions (one undo step each)
// #7497 (decision): matching a booking (a suggestion, another receipt / invoice, a split, a mark, "Without receipt", the
// walk-through) and taking a match back go through the core's "write shows at once" (core.js rwRows, W.act): the row shows its
// new state at once (in "Open" a match takes it out, in "Matched" an undo; in "All" it stays with its new state; in "Without
// receipt" a match takes it out - an error puts it back where it was), the request runs
// behind it (one after the other), the answer (the one booking + the counts, bank.py) takes only this row and the counts -
// no reload of the list (bnkReload) after a click. The books, the cash flow, the key figures and the start page's counter are
// only marked as old. An error puts the row back with "Not saved", the reason and "Try again".
let BNK_W = /** @type {any} */ (null);
const bnkW = () => BNK_W || (BNK_W = rwRows({name: 'bnk', draw: () => ofcDraw()}));
const bnkTx = tid => (BNK.data?.items || []).find(x => x.id === tid) || null;
// the local change of booking tid: match = its new match (null = open again); a row that no longer fits the list's filter
// leaves it ("Open" / "Matched"; in "Without receipt" a match, its number with it), the way back puts it where it was
const bnkFits = t => BNK.state === 'all' || (BNK.state === 'open') === !t.match;
function bnkPut(tid, match) {
  return () => {
    const backs = [], t = bnkTx(tid), bd = BNK.data;
    if (t && bd) {
      const was = t.match; t.match = match;
      const i = bnkFits(t) ? -1 : bd.items.indexOf(t); if (i >= 0) bd.items.splice(i, 1);
      backs.push(() => { t.match = was; const l2 = BNK.data === bd ? bd.items : null; if (i >= 0 && l2 && !l2.some(x => x.id === tid)) l2.splice(Math.min(i, l2.length), 0, t); });
    }
    const nd = typeof BNR === 'object' ? BNR.data : null, ls = nd?.items, i = match && ls ? ls.findIndex(x => x.id === tid) : -1;
    if (i >= 0) {
      const [r] = ls.splice(i, 1), k = +r.amount < 0 ? 'out' : 'in', n = nd.counts || {};
      if (n[k] > 0) n[k]--;
      backs.push(() => { const l2 = BNR.data?.items; if (BNR.data === nd && l2 && !l2.some(x => x.id === tid)) { l2.splice(Math.min(i, l2.length), 0, r); if (nd.counts) nd.counts[k] = (nd.counts[k] || 0) + 1; } });
    }
    return backs.length ? () => backs.forEach(f => f()) : null;
  };
}
// the answer of one booking (match: the booking itself, unmatch: {item}; both + counts): its row (unless a later action of it
// waits: that one's answer stands) and the counts; what the row's change touches elsewhere is only marked as old
function bnkTake(j) {
  bfbBooksStale(); if (typeof BNR === 'object') BNR.cnt = undefined;  // the start page's counter
  const t = j?.item || j;
  if (!t?.id || !t.day) { bnkReload(); return; }  // a short answer (the same request sent again): the list comes again
  if (BNK.data) {
    if (j.counts) BNK.data.counts = j.counts;
    const ls = BNK.data.items || [], i = ls.findIndex(x => x.id === t.id);
    if (i >= 0) { if (!bnkW().busy(rwKey(ls[i]))) ls[i] = {...t, suggestions: ls[i].suggestions, rule_hint: ls[i].rule_hint}; }
    else if (bnkFits(t)) BNK.q = '';  // belongs to the list on screen but is not in it (a step of the walk-through in "Matched"): the list comes again when it is drawn (dimmed)
    // a receipt taken here is no suggestion of another booking any more
    if (t.match?.kind === 'receipt') for (const x of ls) if (x.id !== t.id && x.suggestions) x.suggestions = x.suggestions.filter(g => !(g.kind === 'receipt' && g.id === t.match.id));
  }
  if (!t.match && typeof BNR === 'object' && BNR.data) BNR.q = '';  // open again: "Without receipt" comes again when it is drawn
}
// one action on booking tid: match = its state at once, req = the request (no message of its own: the row says it), undo /
// redo = the history's way back (their answers taken as one), said(j) = the message. -> the history entry, false after an error
async function bnkAct(tid, match, req, label, undo, redo, said) {
  let j; try { j = await bnkW().act('i' + tid, bnkPut(tid, match), req, bnkTake); } catch (x) { return false; }
  const e = histAdd({label, res: j, undo: async () => { bnkTake(await undo()); ofcDraw(); }, redo: async () => { bnkTake(await redo()); ofcDraw(); }});
  const sug = BNK.ruleSug;
  offerUndo(said ? said(j) : label, e);
  if (BNK.ruleSug !== sug) ofcDraw();  // "Always like this?" (brl_learned in said) above the list
  return e;
}
// the match / unmatch request of a booking: the bank's routes are long tasks for rawFetch (NET_LONG: a bank fetch); one booking's
// write is not: the usual limit, so a request without an answer says so at the row
const bnkPost = (tid, what, req) => rawFetch('POST', `/api/office/bank/tx/${tid}/${what}`, req, undefined, undefined, undefined, NET_T.w);
// label: how the row names its match until the answer is there (the suggestion's / candidate's label)
function bnkMatch(tid, kind, mid, parts, label) {
  const req = {kind, ...(mid ? {id: +mid} : {}), ...(parts ? {parts} : {})};  // 2.355.0 B (#2843): parts of a split
  return bnkAct(tid, {kind, id: mid ? +mid : parts?.[0]?.id ?? null, label: label || ''}, () => bnkPost(tid, 'match', req), tr('Bank booking matched'),
    () => api('POST', `/api/office/bank/tx/${tid}/unmatch`), () => api('POST', `/api/office/bank/tx/${tid}/match`, req), j => {
      if (typeof brl_learned === 'function') brl_learned(j);  // (#3191): "Always like this?" after the second time
      // (#2843): a receipt with another amount than the booking is matched, but said (undo right in the toast)
      return j?.amount_differs ? tr('Matched, but the receipt says {0} and the booking {1}', ofcMoney(j.amount_differs.receipt), ofcMoney(j.amount_differs.booking))
        : j?.rule_category ? tr('Matched · category {0} by rule', j.rule_category.category || '') : tr('Matched');
    });
}
function bnkUnmatch(tid) {
  let was = null;
  return bnkAct(tid, null, () => bnkPost(tid, 'unmatch').then(j => { if (j?.was) was = {kind: j.was.kind, ...(j.was.id ? {id: j.was.id} : {}), ...(j.was.parts ? {parts: j.was.parts} : {})}; return j; }), tr('Bank match undone'),
    () => api('POST', `/api/office/bank/tx/${tid}/match`, was), () => api('POST', `/api/office/bank/tx/${tid}/unmatch`), () => tr('Match undone'));
}
async function bnkImpUndo(iid) {
  try { await api('POST', `/api/office/bank/imports/${iid}/undo`); } catch (x) { ofcErr(x); return; }
  BNK.imports = null; bnkReload();
  offerUndo(tr('Import undone'), histAdd({label: tr('Import undone'),
    undo: async () => { await api('POST', `/api/office/bank/imports/${iid}/restore`); BNK.imports = null; bnkReload(); },
    redo: async () => { await api('POST', `/api/office/bank/imports/${iid}/undo`); BNK.imports = null; bnkReload(); }}));
}
async function bnkCand(tid) {
  const q = BNK.candQ;
  try { const j = await api('GET', `/api/office/bank/tx/${tid}/candidates?q=${encodeURIComponent(q)}`); if (BNK.other === tid && BNK.candQ === q) { BNK.cand = j.items || []; BNK.candErr = null; } }
  catch (x) { BNK.cand = []; BNK.candErr = ofcErrHere(x); }
  if (BNK.other === tid) { ofcDraw(); const i = $(`[data-bnk-q="${tid}"]`); if (i && q) { i.focus(); i.setSelectionRange(q.length, q.length); } }
}

// ---- the import: file -> (CSV: columns) -> preview -> take over
// 2.144.1 B (#2446, #2450): the button opens the dialog first: which file to take from the online banking + "Select files"
// (several files or one ZIP, also dropped onto the dialog). The files go as they are (multipart, field files); the server reads
// UTF-8, else windows-1252, opens a ZIP in memory and merges everything into one preview. after = called once imported (the
// cash flow loads again).
// 2.146.0 C (#2455): the date formats of core/csvimport.DATE_FORMATS (the household import offers the same)
const BNK_DATE_FORMATS = ['DD.MM.YYYY', 'DD.MM.YY', 'YYYY-MM-DD', 'MM/DD/YYYY', 'DD-MM-YYYY', 'YYYYMMDD', 'DD/MM/YYYY'];
const BNK_ACCEPT = '.xml,.csv,.txt,.sta,.mt940,.mt942,.zip,text/csv,text/plain,application/xml,text/xml,application/zip,application/x-zip-compressed';
function bnkPick(after) { return bnkImpModal(null, null, after); }
function bnkHintHtml() {
  return `<ul class="bnk-hint" role="list">
    <li class="ok">${ic('check', 's')}<span>${tr('Recommended: account statement as XML (CAMT.053), booked transactions. Only this brings the account balance along. Several files or one ZIP work too.')}</span></li>
    <li>${ic('info', 's')}<span>${tr('Also works: CSV export (you select the columns) – the account balance only when the CSV has a balance column.')}</span></li>
    <li>${ic('info', 's')}<span>${tr('Also works: MT940 / MT942 (.sta, .mt940) – with the account balance.')}</span></li>
    <li class="no">${ic('ban', 's')}<span>${tr('Better not: CAMT.052 (day reports – pending transactions are only shown, never imported).')}</span></li></ul>`;
}
// 2.146.0 C (#2469): CAMT.052 read -- pending entries stay out, the booked version comes with a later report
function bnk052Html() {
  return `<p class="shint lhint keep bnk052">${ic('info', 's')} ${tr('These are day reports (CAMT.052). Pending transactions are shown but not imported; a booking that appears in several reports counts once. For the bookkeeping, better export the account statement (CAMT.053).')}</p>`;
}
// 2.533.0 (#4318) F14: the rows that are skipped, by number and reason (above the list, not only greyed further down)
function dvaBnkSkipText(rs, many, max = 10) {
  return (rs || []).slice(0, max).map(r => tr('Row {0}', r.n) + (many && r.file ? ` (${r.file})` : '') + ': ' + r.error).join(' · ') + ((rs || []).length > max ? ' · …' : '');
}
function dvaBnkSkipHtml(p, many) {
  const rs = p.skipped_rows || [];
  return rs.length ? `<p class="shint lhint keep dvabnkskip" role="status">${ic('alert', 's')} ${esc(trn('{0} row will be skipped', '{0} rows will be skipped', p.skipped || rs.length))}: ${esc(dvaBnkSkipText(rs, many, 20))}</p>` : '';
}
// 2.702.0 (#5183): a CSV statement names no account: with two or more bank accounts the dialog asks which one (required)
const bnkAccName = a => [a.label, a.iban_end ? `… ${a.iban_end}` : ''].filter(Boolean).join(' ') || tr('Bank account');
function bnkAccPickHtml(st) {
  if (!st.banks.length) return '';
  return `<div class="row"><label for="bi-bank">${tr('Bank account')}</label><select id="bi-bank" required aria-required="true"><option value="">${tr('Select the bank account this statement belongs to')}</option>${st.banks.map(a => `<option value="${a.id}" ${st.bank === a.id ? 'selected' : ''}>${esc(bnkAccName(a))}</option>`).join('')}</select></div>`;
}
function bnkImpModal(text, name, after) {  // text + name: one statement read already (as before); without them the start step
  const md = modal(''), card = $('.card', md), st = {p: null, mapping: null, rows: null, account: null, bank: null, banks: []};  // 2.124.0 D (#2342): account = the name for a CSV balance; 2.702.0 (#5183): bank = the chosen bank account
  md.classList.add('ofcdlg', 'bnkdlg');
  let files = typeof text === 'string' ? [new File([text], name || 'statement.txt', {type: 'text/plain'})] : [];
  const label = () => files.length === 1 ? files[0].name : trn('{0} file', '{0} files', files.length);
  const form = mapping => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    if (mapping) fd.append('mapping', JSON.stringify(mapping));
    if (st.account) fd.append('account', st.account);
    if (st.bank) fd.append('bank_account', st.bank);
    return fd;
  };
  const errEl = () => $('.aerr', md), err = m => { const e = errEl(); if (e) e.textContent = m || ''; };
  const hasStart = typeof text !== 'string';  // 2.962.0 (#5232): opened without a statement = there is a start step to go back to
  // foot(): built from tr() / esc() only (html-ok where its arguments changed in 2.962.0)
  const foot = (ok, back) => `<div class="aerr" role="alert"></div><div class="foot">${back ? `<button class="btn" data-bi="back">${tr('Back')}</button>` : ''}<span class="spacer"></span><button class="btn" data-bi="close">${tr('Cancel')}</button>${ok ? `<button class="btn pri" data-bi="next">${esc(ok)}</button>` : ''}</div>`;
  const sel = (id, label, val, opt) => `<div class="row"><label for="${id}">${esc(label)}</label><select id="${id}">${opt ? `<option value="">${tr('none')}</option>` : ''}${st.p.columns.map((c, i) => `<option value="${i}" ${val === i ? 'selected' : ''}>${esc(c || tr('Column {0}', i + 1))}</option>`).join('')}</select></div>`;
  const cols = () => {
    const g = st.mapping || st.p.guess || {}, two = g.amount == null && (g.amount_in != null || g.amount_out != null);  // 2.140.0 B (#2134): + the recognised bank layout
    card.innerHTML = `<h3>${tr('Import bank statement')}</h3><p class="muted">${esc(label())} · ${tr('Which column holds what? Kalmido has guessed; please check.')}</p>${st.p.files > 1 ? `<p class="muted">${tr('The columns apply to every CSV file.')}</p>` : ''}${filesInfo(st.p)}
      ${st.p.guess?.preset_name ? `<p class="shint lhint keep bgpreset">${ic('check', 's')} ${esc(tr('Recognised layout: {0}', st.p.guess.preset_name))}</p>` : ''}
      ${sel('bi-date', tr('Date'), g.date)}
      <div class="row"><label>${tr('Amount')}</label><div class="seg" role="radiogroup" id="bi-am" aria-label="${esc(tr('Amount'))}"><button type="button" role="radio" data-am="one" aria-checked="${!two}" class="${two ? '' : 'on'}">${tr('One column (minus = expense)')}</button><button type="button" role="radio" data-am="two" aria-checked="${two}" class="${two ? 'on' : ''}">${tr('Income and expense apart')}</button></div></div>
      <div class="bi-one" ${two ? 'hidden' : ''}>${sel('bi-amt', tr('Amount'), g.amount)}${sel('bi-sign', tr('Column with S/H (debit/credit), if the bank gives amounts without a minus'), g.sign, true)}</div>
      <div class="bi-two" ${two ? '' : 'hidden'}>${sel('bi-in', tr('Income'), g.amount_in, true)}${sel('bi-out', tr('Expense'), g.amount_out, true)}</div>
      ${bnkAccPickHtml(st)}${sel('bi-title', tr('Purpose'), g.title, true)}${sel('bi-cp', tr('Paid to / from'), g.counterpart, true)}${cfb_mapHtml(st, sel, g)}
      <div class="row"><label for="bi-dec">${tr('Decimal separator')}</label><select id="bi-dec"><option value="," ${g.decimal !== '.' ? 'selected' : ''}>${tr('comma (1.234,56)')}</option><option value="." ${g.decimal === '.' ? 'selected' : ''}>${tr('point (1,234.56)')}</option></select></div>
      <div class="row"><label for="bi-df">${tr('Date format')}</label><select id="bi-df">${BNK_DATE_FORMATS.map(f => `<option ${g.date_format === f ? 'selected' : ''}>${f}</option>`).join('')}</select></div>
      <div class="bgtblw"><table class="bgtbl"><thead><tr>${st.p.columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${st.p.sample.map(r => `<tr>${r.map(x => `<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      ${/*html-ok*/ foot(tr('Preview'), hasStart)}`;  // 2.962.0 (#5232): Back to the start (there was no way back from the columns)
  };
  const mapOf = () => {
    const n = id => { const v = $(id, md)?.value; return v === '' || v == null ? null : +v; }, two = $('#bi-am [aria-checked="true"]', md)?.dataset.am === 'two';
    st.account = $('#bi-accname', md)?.value.trim() || null;  // 2.124.0 D (#2342): balance + own account column (optional)
    if ($('#bi-bank', md)) st.bank = +$('#bi-bank', md).value || null;  // 2.702.0 (#5183)
    return {date: n('#bi-date'), amount: two ? null : n('#bi-amt'), amount_in: two ? n('#bi-in') : null, amount_out: two ? n('#bi-out') : null, sign: two ? null : n('#bi-sign'), title: n('#bi-title'), counterpart: n('#bi-cp'), decimal: $('#bi-dec', md).value, date_format: $('#bi-df', md).value, balance: n('#bi-bal'), account: n('#bi-acc')};
  };
  const start = () => {
    card.innerHTML = `<h3>${tr('Import bank statement')}</h3><p class="muted">${tr('Which file from your online banking?')}</p>${bnkHintHtml()}
      <div class="bnk-drop" data-bi-drop><input type="file" id="bi-file" class="bnk-file" accept="${esc(BNK_ACCEPT)}" multiple hidden><button type="button" class="btn pri" data-bi="pick">${ic('upload', 's')}<span>${tr('Select files')}</span></button><small class="muted">${tr('or drop them here')}</small></div>
      ${foot('')}`;
  };
  const filesInfo = p => {
    const errs = p.file_errors || [], skip = p.skipped_files || [];
    if (!errs.length && !skip.length) return '';
    return `<ul class="bnk-files" role="list">${errs.map(e => `<li class="no">${ic('alert', 's')}<span><b>${esc(e.file)}</b> ${esc(e.error)}</span></li>`).join('')}${skip.length ? `<li>${ic('info', 's')}<span>${esc(tr('Skipped: {0}', skip.join(', ')))}</span></li>` : ''}</ul>`;
  };
  const rowsView = () => {
    const p = st.p, many = (p.files || 1) > 1;
    card.innerHTML = `<h3>${tr('Import bank statement')}</h3><p class="muted">${esc(label())} · ${esc(tr('Import into: {0}', wsName(ofcWs())))/* 2.356.0 B (#2934) */} · ${esc([many && files.length === 1 ? trn('{0} file', '{0} files', p.files) : '', trn('{0} new', '{0} new', p.count), p.dup_count ? trn('{0} already there', '{0} already there', p.dup_count) : '', p.pending_count ? trn('{0} pending', '{0} pending', p.pending_count) : '', p.skipped ? trn('{0} with an error', '{0} with an error', p.skipped) : ''].filter(Boolean).join(' · '))}</p>
      ${p.camt052 ? bnk052Html() : ''}${cfb_prevHtml(p.balances)}${filesInfo(p)}${dvaBnkSkipHtml(p, many)}<ul class="ofclist bnkprev" role="list">${p.rows.slice(0, 200).map(r => `<li class="ofcrow ${r.error || r.dup || r.pending ? 'arch' : ''} ${r.pending ? 'pend' : ''}"><span class="ofcn"><b>${esc(r.counterpart || r.purpose || tr('Row {0}', r.n))}</b><small class="muted">${esc([r.day ? fmtDateLoc(r.day) : '', r.error || (r.pending ? tr('pending – not imported') : r.dup ? (r.dup_other ? tr('already there (imported from a statement in another format)') : tr('already there')) : r.purpose), many ? r.file : ''].filter(Boolean).join(' · '))}</small></span>${r.amount != null ? `<span class="bnkamt ${+r.amount > 0 ? 'in' : 'out'}">${esc(bnkAmt(r.amount))}</span>` : ''}</li>`).join('')}</ul>
      ${p.rows.length > 200 ? `<p class="muted">${tr('Showing the first 200 rows')}</p>` : ''}${/*html-ok*/ foot(p.count ? trn('Import {0} booking', 'Import {0} bookings', p.count) : '', p.fmt === 'csv' || hasStart)}`;
  };
  // 2.962.0 (#5232): the views are steps of Back: start -> columns -> rows (CSV), start -> rows (CAMT / MT940)
  const toStart = () => { files = []; Object.assign(st, {p: null, mapping: null}); start(); };
  const backOne = () => st.p?.columns || st.p?.fmt !== 'csv' ? toStart() : preview(null);
  const preview = async (mapping, fwd) => {
    try { st.p = await api('POST', '/api/office/bank/import/preview', form(mapping)); }
    catch (x) {
      if (st.p) err(x.message); else if (typeof text === 'string') { md.remove(); ofcErr(x); }
      else { start(); err(ofcErrHere(x)); }  // 2.144.1 B (#2446): e.g. MT940 -> the message in the start step
      $$('button[data-bi]', md).forEach(b => { b.disabled = false; }); return;
    }
    if (st.p.columns) { st.banks = st.p.bank_accounts || []; cols(); } else rowsView();
    if (fwd) f8d_step(md, backOne);
  };
  const take = fl => {
    files = [...(fl || [])]; if (!files.length) return;
    const fwd = hasStart && !st.p;  // from the start step (files dropped onto the columns replace them: no new step)
    Object.assign(st, {p: null, mapping: null}); card.innerHTML = botBusy(`<p class="muted">${tr('Loading…')}</p>`); preview(null, fwd);  // 2.161.2 (#2611): + the bot at work
  };
  md.addEventListener('click', async e => {
    const am = e.target.closest('#bi-am [data-am]');
    if (am) { for (const x of $$('#bi-am [data-am]', md)) { x.classList.toggle('on', x === am); x.setAttribute('aria-checked', x === am); } $('.bi-one', md).hidden = am.dataset.am === 'two'; $('.bi-two', md).hidden = am.dataset.am !== 'two'; return; }
    const b = e.target.closest('button[data-bi]'); if (!b) return;
    if (b.dataset.bi === 'close') { md.remove(); return; }
    if (b.dataset.bi === 'pick') { $('#bi-file', md)?.click(); return; }  // 2.633.0 (#4920): fixed hidden file input, its change uploads (a drop onto the window too, dropany.js)
    if (b.dataset.bi === 'back') { f8d_backBtn(md, backOne); return; }  // 2.962.0 (#5232): = Android Back
    if (st.p?.columns) {
      st.mapping = mapOf();
      if (st.banks.length && !st.bank) { err(tr('Select the bank account this statement belongs to')); $('#bi-bank', md)?.focus(); return; }  // 2.702.0 (#5183): never silently the default
      b.disabled = true; await preview(st.mapping, true); return;
    }
    // 2.356.0 B (#2934): the target before the start, in words: the office area of the account(s) + the account (#1940)
    const accts = [...new Set((st.p?.balances || []).map(x => x.account).filter(Boolean))].map(cfb_acct);
    const bk = st.banks.find(x => x.id === st.bank);  // 2.702.0 (#5183): the chosen bank account names the place
    if (!await importTargetConfirm({what: trn('{0} booking', '{0} bookings', st.p?.count || 0), ws: ofcWs(), place: (bk && bnkAccName(bk)) || st.account || accts.join(', ') || tr('Bank account')})) return;
    b.disabled = true;
    try {
      const j = await api('POST', '/api/office/bank/import', form(st.mapping)), iid = j.import.id;
      md.remove(); BNK.state = 'open'; BNK.imports = null; bnkReload(); if (after) after();
      // 2.533.0 (#4318) F14: the skipped rows by number in the message (the preview names them above the list too)
      const skip = j.skipped_rows?.length ? ` · ${trn('{0} row skipped', '{0} rows skipped', j.skipped)}: ${dvaBnkSkipText(j.skipped_rows, (st.p?.files || 1) > 1, 5)}` : '';
      offerUndo(trn('{0} booking imported', '{0} bookings imported', j.count) + (j.ruled ? ` · ${trn('{0} marked by rule', '{0} marked by rule', j.ruled)}` : '') + skip, histAdd({label: tr('Bank statement imported'),
        undo: async () => { await api('POST', `/api/office/bank/imports/${iid}/undo`); BNK.imports = null; bnkReload(); },
        redo: async () => { await api('POST', `/api/office/bank/imports/${iid}/restore`); BNK.imports = null; bnkReload(); }}));
    } catch (x) { b.disabled = false; err(x.message); }
  });
  md.addEventListener('change', e => { const t = e.target; if (t.id === 'bi-file' && t.files?.length) { take(t.files); t.value = ''; } });  // 2.633.0 (#4920)
  // 2.144.1 B (#2446): files dropped onto the dialog
  md.addEventListener('dragover', e => { if ([...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); $('[data-bi-drop]', md)?.classList.add('on'); } });
  md.addEventListener('dragleave', e => { if (!md.contains(e.relatedTarget)) $('[data-bi-drop]', md)?.classList.remove('on'); });
  md.addEventListener('drop', e => { if (!e.dataTransfer?.files?.length) return; e.preventDefault(); if (!st.p || !st.p.rows) take(e.dataTransfer.files); });
  if (files.length) { card.innerHTML = botBusy(`<p class="muted">${tr('Loading…')}</p>`); preview(null); } else start();
  md.bnkTake = take;  // the UI tests hand files over here
  return md;
}

document.addEventListener('toggle', e => { const d = /** @type {any} */ (e.target); if (d?.matches?.('[data-bnk-miss]')) LS.set('bnkMissShut', !d.open); }, true);  // 2.1324.0 (#6147)
let bnkQT = null;
document.addEventListener('input', e => {
  const pi = e.target.closest?.('[data-bnk-part]');
  if (pi) {  // 2.355.0 B (#2843): the rest of a split, live
    (BNK.parts ||= {})[pi.dataset.bnkPart] = pi.value;
    const r = $('[data-bnk-rest]', pi.closest('.bnkother')); if (r) r.textContent = bnkSplitRest(r.dataset.amount);
    return;
  }
  const i = e.target.closest?.('[data-bnk-q]'); if (!i) return;
  BNK.candQ = i.value; clearTimeout(bnkQT); bnkQT = setTimeout(() => bnkCand(+i.dataset.bnkQ), 250);
});
document.addEventListener('click', e => {
  const b = e.target.closest?.('[data-bnk]'); if (!b) return;
  const a = b.dataset.bnk, id = +b.dataset.id;
  if (a === 'imp') bnkPick();
  else if (a === 'fints') fnt_open();  // 2.616.0 (#2473): office_fints.js (lazyload.js LD_CALL)
  else if (a === 'state') { BNK.state = b.dataset.v; BNK.other = null; ofcDraw(); }
  else if (a === 'imps') { BNK.showImp = !BNK.showImp; ofcDraw(); }
  else if (a === 'impundo') bnkImpUndo(id);
  else if (a === 'match') { const t = bnkTx(id), mid = +b.dataset.mid, c = [...(t?.suggestions || []), ...(BNK.other === id ? BNK.cand || [] : [])].find(x => x.id === mid && x.kind === b.dataset.kind); if (BNK.other === id) BNK.other = null; bnkMatch(id, b.dataset.kind, b.dataset.mid, null, c?.label || ''); }
  else if (a === 'unmatch') bnkUnmatch(id);
  else if (a === 'more') bnkMoreMenu(b, id);  // 2.809.0 (#5452)
  else if (a === 'walk') wlk_open('bnk');  // 2.778.0 (#5383): office_walk.js (lazyload.js LD_CALL)
  else if (a === 'menu') bnkBarMenu(b);  // 2.1324.0 (#6147): the bar's "More" on a phone
  else if (a === 'other') { BNK.other = BNK.other === id ? null : id; BNK.cand = null; BNK.candQ = ''; BNK.split = false; BNK.parts = {}; ofcDraw(); if (BNK.other) bnkCand(id); }
  else if (a === 'split') { BNK.split = !BNK.split; BNK.parts = {}; ofcDraw(); }  // 2.355.0 B (#2843)
  else if (a === 'splitgo') {
    const parts = Object.entries(BNK.parts || {}).filter(([, v]) => String(v).trim()).map(([k, v]) => ({id: +k, amount: ofcNum(v)}));
    if (!parts.length || parts.some(p => !(p.amount > 0))) { toast(tr('Invalid value: {0}', tr('Amount'))); return; }
    // #7497: the typed amounts stay until the answer: an error opens the split again with them
    const typed = {...BNK.parts}, names = parts.map(p => (BNK.cand || []).find(x => x.id === p.id)?.label).filter(Boolean).join(', ');
    BNK.split = false; BNK.parts = {}; BNK.other = null;
    bnkMatch(id, 'invoice', null, parts, names).then(ok => { if (!ok && BNK.other === null) { Object.assign(BNK, {other: id, split: true, parts: typed}); ofcDraw(); if (!BNK.cand) bnkCand(id); } });
  }
  else return;
  e.preventDefault();
});

// ---- 2.124.0 D (#2342): the balance of the statement. CSV: an optional balance column, an optional column with the own IBAN,
// else the account's name (default "Main account"; known names offered). The preview names the closing balance per account.
// Server: kalmido/office/cfbank.py.
const cfb_day = d => fmtDay('year', pd(d));  // always with the year (TT.MM.JJJJ)
const cfb_acct = a => /^[A-Z]{2}\d{2}[A-Z0-9]{8,}$/.test(a || '') ? `${a.slice(0, 4)} … ${a.slice(-4)}` : (a || '');
function cfb_mapHtml(st, sel, g) {
  const known = st.p.accounts || [], v = st.account ?? (known.find(a => !/^[A-Z]{2}\d{2}/.test(a)) || tr('Main account'));
  return `${sel('bi-bal', tr('Balance (optional)'), g.balance, true)}${sel('bi-acc', tr('Own account (IBAN, optional)'), g.account, true)}
      <div class="row"><label for="bi-accname">${tr('Account name for the balance')}</label><input id="bi-accname" maxlength="60" list="bi-accl" autocomplete="off" value="${esc(v)}"><datalist id="bi-accl">${known.map(a => `<option value="${esc(a)}">`).join('')}</datalist></div>`;
}
function cfb_prevHtml(bals) {
  const last = {};
  for (const b of (bals || []).filter(x => x.kind === 'close')) if (!last[b.account] || b.day >= last[b.account].day) last[b.account] = b;
  const ls = Object.values(last);
  if (!ls.length) return '';
  return `<ul class="cfb-prev" role="list">${ls.map(b => `<li>${esc(tr('Account balance according to the bank on {0}: {1}', cfb_day(b.day), ofcMoney(b.amount)))}${ls.length > 1 || /^[A-Z]{2}\d{2}/.test(b.account) ? ` <small class="muted">${esc(cfb_acct(b.account))}</small>` : ''}</li>`).join('')}</ul>`;
}
// 2.854.0 (#5354): a long press (phone) / right click (computer) on an open booking opens its More menu, as a tap on "More"
if (typeof lm_btnMenu === 'function') lm_btnMenu('#view .bnkrow', '[data-bnk="more"]');
