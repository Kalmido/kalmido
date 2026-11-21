// @ts-check
// 2.121.0 B (#2095): the cash book in the office (tab "Cash book", menu group Money, admins only). On top the balance of
// the cash box and the quick entry (phone first: in / out, amount, text, today), below the entries of the year with the
// running balance (newest first), the day closings and the cash boxes (settings: name, opening balance, archive; autosave).
// Nothing is deleted: an entry goes back only by a cancellation (a counter entry with a new number). "Close day" is final
// (confirmation, no undo); every other action is one undo step (toast). Server: kalmido/office/cashbook.py.
const CB = {oid: null, base: null, list: null, q: '', loading: false, err: null, bid: null, year: String(new Date().getFullYear()), view: 'entries', dir: 'in', links: null};  // #7500: each entry of the quick entry carries its own client_ref (cb_W)
OFC_TABS.splice(OFC_TABS.findIndex(t => t[0] === 'settings'), 0, /** @type {any} */ (['cashbook', 'wallet', N_('Cash book'), 1, () => cbHtml(), 'money']));  // admins only

/** @param {string} s @param {any} [r] @returns {any} */
const cb$ = (s, r) => (r || document).querySelector(s);  // $ with a dialog as root (typed loosely)
// #7495: a write, an undo or a switch of book / year keeps the entries on screen (dimmed) until the fresh ones are there
const cbReload = (all) => ofcRefetch('cashbook', ofcTab() === 'cashbook' && !!CB.base && !!CB.list && !CB.err, () => cbGet(all), () => { if (all) CB.base = null; CB.list = null; CB.err = null; });  // (#2354, N5): a failed load does not stick
async function cbGet(all) {
  const base = all || !CB.base ? await api('GET', '/api/office/cashbooks') : CB.base, act = base.books.filter(b => !b.archived);
  const bid = base.books.some(b => b.id === CB.bid) ? CB.bid : (act[0] || base.books[0])?.id || null, y = CB.year;
  const list = bid ? await api('GET', `/api/office/cashbooks/${bid}/entries?year=${y}`) : null;
  return () => { CB.base = base; CB.bid = bid; CB.err = null; if (list) { CB.list = list; CB.q = `${bid}:${y}`; cb_keepPend(); } };
}
const cbBook = id => (CB.base?.books || []).find(b => b.id === id);
const cbToday = () => CB.base?.today || today();
const cbVat = v => v ? `${v} %` : '';

async function cbLoad() {
  if (CB.loading) return;
  CB.loading = true;
  try {
    // (#7507): with a cash book chosen already its entries come at the same time as the books (were one after the other)
    const q0 = `${CB.bid}:${CB.year}`, early = CB.bid && !CB.base && (!CB.list || CB.q !== q0) ? api('GET', `/api/office/cashbooks/${CB.bid}/entries?year=${CB.year}`, undefined, {quiet: true}) : null;
    early?.catch(() => {});  // awaited below (its failure: the error block) or dropped (another book): quiet, never an unhandled refusal
    if (!CB.base) CB.base = await api('GET', '/api/office/cashbooks');
    const act = CB.base.books.filter(b => !b.archived);
    if (!cbBook(CB.bid)) CB.bid = (act[0] || CB.base.books[0])?.id || null;
    const q = `${CB.bid}:${CB.year}`;
    if (CB.bid && (!CB.list || CB.q !== q)) { CB.list = await (early && q === q0 ? early : api('GET', `/api/office/cashbooks/${CB.bid}/entries?year=${CB.year}`)); CB.q = q; cb_keepPend(); }
    CB.err = null;
  } catch (x) { CB.err = ofcErrHere(x); }
  CB.loading = false;
  ofcDraw();
}

// ---- the view
function cbHtml() {
  if (CB.oid !== OFC.info?.org_id) Object.assign(CB, {oid: OFC.info?.org_id, base: null, list: null, err: null, bid: null, links: null});  // another office area
  if (!ofcAdmin()) return ofcLockedHtml();  // 2.356.0 D (#3006): why, and the way to hand in receipts
  if (CB.err) return ofcFail(CB.err, () => cbReload(true));  // 2.144.11 (#2354, N5); 2.1076.0 (#5450): the shared block
  if (!CB.base || !CB.list) { if (!CB.loading) setTimeout(cbLoad, 0); return loadingHtml('big'); }
  if (CB.q !== `${CB.bid}:${CB.year}` && !ofcHeldBusy('cashbook')) setTimeout(() => { if (!ofcHeldBusy('cashbook') && CB.q !== `${CB.bid}:${CB.year}`) cbReload(); }, 0);  // #7495: another book / year: the old one dimmed
  const bs = CB.base.books, act = bs.filter(b => !b.archived || b.id === CB.bid), b = cbBook(CB.bid);
  const years = ofcYearOpts(CB.list.years, CB.year);  // 2.593.0 (#4891): the years of the box's entries (was this year .. -4)
  const q = `book_id=${CB.bid}&year=${CB.year}`;
  const bar = `<div class="ofcbar cb-bar">${act.length > 1 ? `<select id="cb-book" aria-label="${esc(tr('Cash box'))}">${act.map(x => `<option value="${x.id}" ${x.id === CB.bid ? 'selected' : ''}>${esc(x.name + (x.archived ? ` · ${tr('archived')}` : ''))}</option>`).join('')}</select>` : ''}
    <select id="cb-year" aria-label="${esc(tr('Year'))}">${years.map(y => `<option ${y === CB.year ? 'selected' : ''}>${y}</option>`).join('')}</select>
    <div class="seg" role="group" aria-label="${esc(tr('Show'))}">${[['entries', tr('Entries')], ['closings', tr('Day closings')]].map(([k, n]) => `<button type="button" data-cb="view" data-v="${k}" class="${CB.view === k ? 'on' : ''}" aria-pressed="${CB.view === k}">${n}</button>`).join('')}</div>
    <span class="spacer"></span><a class="btn sm ghost" href="/api/office/cashbook.csv?${q}" download>${ic('download', 's')}<span>CSV</span></a><a class="btn sm ghost" href="/api/office/cashbook.pdf?${q}" download>${ic('download', 's')}<span>PDF</span></a>
    <button type="button" class="btn sm ghost" data-setgo="biz-tax">${ic('gear', 's')}<span>${tr('Cash boxes')}</span></button></div>`;  // 2.365.2 D (#2789): set in Settings > Company & office > Bank & taxes
  const note = `<details class="lgb-note cb-note"><summary>${ic('alert', 's')}<span>${tr('Note on the cash book')}</span></summary><p class="muted">${esc(CB.base.note)}</p></details>`;
  const body = CB.view === 'closings' ? cbClosingsHtml() : cbHeadHtml(b) + cbQuickHtml(b) + cbListHtml();
  return bar + body + note;
}
function cbHeadHtml(b) {
  const l = CB.list;
  const calc = !!cb_W(CB.bid).calc;  // #7500: an entry on its way: the server computes the new balance
  return `<div class="cb-head${calc ? ' rwcalc' : ''}"${calc ? ' aria-busy="true"' : ''}><div><span class="muted">${tr('Cash balance')}</span><b class="cb-bal">${ofcMoney(l.balance)}</b>${calc ? `<small class="rwcalcl muted" role="status">${esc(tr('Calculating…'))}</small>` : ''}
    <small class="muted">${esc(l.last_closed ? tr('Closed up to {0}', fmtDateLoc(l.last_closed)) : tr('No day closed yet'))}</small></div>
    <button class="btn" data-cb="close">${ic('check', 's')}<span>${tr('Close day')}</span></button></div>`
    + `<p class="muted ofchint cb-euer">${esc(typeof ebBasisOf === 'function' && ebBasisOf(OFC.info?.settings, new Date().getFullYear()) === 'bank'  /* 2.603.0 (#4927): the strict basis counts the cash book */
      ? tr('Basis bank and cash: money paid out of the cash book counts in the income/expense statement, with its receipt; a cash withdrawal from the bank is a transfer.')
      : tr('The cash book does not count in the income/expense statement: book the receipts and invoice payments there as usual.'))}</p>`;
}
function cbQuickHtml(b) {
  if (!b || b.archived) return '';
  return `<form class="cb-quick" id="cb-quick" autocomplete="off" aria-label="${esc(tr('New cash entry'))}">
    <div class="seg cb-dir" role="group" aria-label="${esc(tr('Kind'))}">${[['in', tr('Income')], ['out', tr('Expense')]].map(([k, n]) => `<button type="button" data-cb="dir" data-v="${k}" class="${CB.dir === k ? 'on' : ''}" aria-pressed="${CB.dir === k}">${n}</button>`).join('')}</div>
    <input id="cb-amount" inputmode="decimal" class="numin cb-amount" placeholder="${esc(tr('Amount'))}" aria-label="${esc(tr('Amount'))}" required>
    <input id="cb-text" maxlength="300" placeholder="${esc(tr('Text, e.g. sale at the counter'))}" aria-label="${esc(tr('Text'))}" required>
    <div class="cb-qrow">${dateIn('cb-day', cbToday(), {label: tr('Date'), clear: false})}
    <select id="cb-vat" aria-label="${esc(tr('VAT rate'))}">${['19', '7', '0'].map(v => `<option value="${v}">${v} %</option>`).join('')}</select>
    <input id="cb-cat" maxlength="60" list="cb-cats" placeholder="${esc(tr('Category'))}" aria-label="${esc(tr('Category'))}"><datalist id="cb-cats">${CB.base.categories.map(c => `<option value="${esc(c)}">`).join('')}</datalist></div>
    <div class="aerr" role="alert" id="cb-qerr"></div>
    <button class="btn pri cb-go" type="submit">${ic('plus', 's')}<span>${tr('Book')}</span></button></form>`;
}
function cbRef(e) {
  if (e.storno_of_no) return tr('Cancels no. {0}', e.storno_of_no);
  if (e.cancelled_by_no) return tr('Cancelled by no. {0}', e.cancelled_by_no);
  return '';
}
function cbListHtml() {
  const es = CB.list.entries, W = cb_W(CB.bid);
  // #7500: one wrapper whether there are entries or not (the light draw morphs it, the quick entry above stays as typed)
  if (!es.length) return `<div id="cb-entries">${/*html-ok*/ emptyState({icon: 'wallet', title: tr('No entries in this year.'), size: 'sec'}) /* the shared empty block escapes its texts */}</div>`;  // (#5450)
  return `<div id="cb-entries"><ul class="ofclist cb-list" role="list">${es.map(e => `<li data-rwk="${esc(rwKey(e))}" class="${esc(rwCls(W, e).trim())}"><button type="button" class="ofcrow cb-row${e.cancelled_by || e.storno_of ? ' cb-x' : ''}" data-cb="open" data-id="${esc(e.id || '')}">
    <span class="cb-no">${esc(e.no || '…')}</span><span class="ofcn"><b>${esc(e.text)}</b>
    <small class="muted">${esc([fmtDateLoc(e.day), e.category, cbVat(e.vat_pct), e.node ? tr('Receipt') + ': ' + e.node.name : '', e.invoice ? tr('Invoice') + ' ' + e.invoice.number : ''].filter(Boolean).join(' · '))}</small>
    ${cbRef(e) ? `<small class="cb-ref">${esc(cbRef(e))}</small>` : ''}</span>
    ${e.locked ? `<span class="cb-lock" title="${esc(tr('Day closed'))}" aria-label="${esc(tr('Day closed'))}">${ic('lock', 's')}</span>` : ''}
    <span class="cb-amt"><b class="${e.dir === 'in' ? 'cb-in' : 'cb-out'}">${e.dir === 'in' ? '+' : '−'} ${ofcMoney(e.amount)}</b>${e.balance == null ? '' : `<small class="muted">${ofcMoney(e.balance)}</small>`}</span></button>${/*html-ok*/ rwMarkHtml(W, e) /* the core's mark, its texts escaped */}</li>`).join('')}</ul></div>`;
}
function cbClosingsHtml() {
  const cs = (CB.list?.closings || []).slice().reverse();
  if (!cs.length) return emptyState({icon: 'check', title: tr('No day closed in this year.'), size: 'sec'});
  return `<div class="lgb-cards cb-cards">${cs.map(x => `<div class="lgb-card"><h4>${esc(fmtDateLoc(x.day))}</h4><p class="muted">${esc([trn('{0} entry', '{0} entries', x.count), x.by].filter(Boolean).join(' · '))}</p>
    <dl class="lgb-dl"><dt>${tr('Opening balance')}</dt><dd>${ofcMoney(x.opening)}</dd><dt>${tr('Income')}</dt><dd>${ofcMoney(x.sum_in)}</dd>
    <dt>${tr('Expense')}</dt><dd>${ofcMoney(x.sum_out)}</dd><dt>${tr('Closing balance')}</dt><dd><b>${ofcMoney(x.closing)}</b></dd></dl></div>`).join('')}</div>`;
}
// 2.365.2 D (#2789): the cash boxes are set in Settings > Company & office > Bank & taxes (decision 23.10.: cash boxes and their
// opening balance with the bank and taxes); the cash book tab links there
function cb_setHtml() {
  if (CB.oid !== OFC.info?.org_id) Object.assign(CB, {oid: OFC.info?.org_id, base: null, list: null, err: null, bid: null, links: null});  // another office area
  const head = `<h3 id="cbset-h">${tr('Cash boxes')}</h3><p class="muted ofchint">${tr('Name, opening balance and opening day of each cash box; the entries are in Office > Cash book.')}</p>`;
  if (!CB.base) { if (!CB.loading && !CB.err) setTimeout(cbLoad, 0); return `<section class="cbset">${head}${/*html-ok*/ CB.err ? errorState({sub: CB.err, size: 'sec'}) : loadingHtml('sec')}</section>`; }  // 2.1076.0 (#5450): (the settings window draws this part once; the cash book page has "Try again")
  return `<section class="cbset" aria-labelledby="cbset-h">${head}${cbBooksHtml()}</section>`;
}
function cbBooksHtml() {  // the settings of the cash boxes: sections like the general settings, saved on change
  const bs = CB.base.books;
  return `<div class="cb-books">${bs.map(b => `<section class="cb-bk${b.archived ? ' cb-arch' : ''}" data-bid="${b.id}" aria-labelledby="cb-bk${b.id}"><h4 id="cb-bk${b.id}">${esc(b.name)}${b.is_default ? ` <span class="rotag">${tr('Default')}</span>` : ''}${b.archived ? ` <span class="rotag">${tr('archived')}</span>` : ''}</h4>
    ${ofcRowF(`cb-n${b.id}`, tr('Name'), `<input id="cb-n${b.id}" data-cbf="name" value="${esc(b.name)}" maxlength="80">`)}
    ${ofcRowF(`cb-o${b.id}`, tr('Opening balance'), `<input id="cb-o${b.id}" data-cbf="opening" inputmode="decimal" class="numin" value="${esc(fmtNum(+b.opening, 2))}" ${b.last_closed || b.entries ? 'disabled' : ''}>`, b.last_closed ? tr('Fixed after the first day closing.') : b.entries ? tr('Fixed after the first entry.') : '')}
    <div class="row"><label>${tr('Opening day')}</label>${dateIn(`cb-od${b.id}`, b.opening_day, {label: tr('Opening day'), clear: false})}</div>
    <p class="muted">${esc([tr('Balance {0}', ofcMoney(b.balance)), trn('{0} entry', '{0} entries', b.entries), b.last_closed ? tr('Closed up to {0}', fmtDateLoc(b.last_closed)) : ''].filter(Boolean).join(' · '))}</p>
    ${b.is_default ? '' : `<button class="btn sm" data-cb="arch" data-id="${b.id}">${b.archived ? tr('Restore') : tr('Archive')}</button>`}</section>`).join('')}
    <button class="btn" data-cb="bnew">${ic('plus', 's')}<span>${tr('Add cash box')}</span></button></div>`;
}

// ---- actions
// #7500 (decision): the quick entry "writes at once" (core.js rwRows, docs/dev/kern.md "Write shows at once"): the new line stands
// under the form at once ("Saving…"), the form stays (amount, text and category emptied, the cursor back in the amount) and
// the next entry can be typed; the answer brings the number, the balance after it and the box's new balance (no reload of
// boxes and entries). Entries go one after the other, each with its own client_ref (sent again = booked once, #3046).
// No answer / no connection: the line stays with "Not saved - Try again". A refusal (a closed day, below zero ...): the
// line goes, its values come back into the form with the reason (when the form is empty; else the reason only).
const CB_WS = new Map(), CB_Q = /** @type {Map<number, any[]>} */ (new Map());  // a box's writer, its entries not saved yet (in the order typed)
const cb_q = bid => { cb_W(bid); return CB_Q.get(bid || 0) || []; };
function cb_W(bid) {
  let W = CB_WS.get(bid || 0);
  if (!W) {
    W = rwRows({name: 'cb' + (bid || 0), whole: true, send: () => cb_send(bid, W), draw: () => cbLite(), fail: x => !!x?.rwShown});
    CB_WS.set(bid || 0, W); CB_Q.set(bid || 0, []);
  }
  return W;
}
// the entries not saved yet stay in the list through a reload of it (another year, an undo, a closing)
function cb_keepPend() {
  const q = CB_Q.get(CB.bid || 0); if (!q?.length || !CB.list) return;
  for (const e of q) if (e.day.slice(0, 4) === CB.year && !CB.list.entries.includes(e)) cb_place(e);
}
// newest first: before the first entry of the same day or an earlier one
function cb_place(e) {
  const es = CB.list.entries, i = es.findIndex(x => x.day <= e.day);
  es.splice(i < 0 ? es.length : i, 0, e);
}
async function cb_send(bid, W) {
  let late = /** @type {boolean | string} */ (false);
  const q = cb_q(bid);
  while (q.length) {
    const e = q[0];
    let j;
    try { j = await rawFetch('POST', `/api/office/cashbooks/${bid}/entries`, {...e._b, client_ref: e._ref}); }
    catch (x) {
      if (x instanceof NoAnswer || x instanceof Offline || !x?.status || x.status >= 500) throw x;  // the lines say "Not saved - Try again"
      q.shift(); cb_unput(e); cb_back(e, x); continue;  // refused: the person changes something, sending it again would not help
    }
    q.shift(); e._b = null;
    Object.assign(e, j);  // its key (_rk) stays: the line is found by it
    if (CB.bid === bid && CB.list) {
      CB.list.balance = j.book_balance;
      const bk = cbBook(bid); if (bk) Object.assign(bk, {balance: j.book_balance, entries: j.book_entries});
      if (j.day.slice(0, 4) !== CB.year) late = j.day.slice(0, 4);  // booked into another year: that year is shown (as before)
      else if (!late && CB.list.entries.some(x => x !== e && x.id && x.day > e.day)) late = true;  // booked before later entries: their balances are the server's anew
    }
    toast(tr('Booked as no. {0}', j.no), async () => { await api('POST', `/api/office/cash-entries/${j.id}/cancel`, {}); cbReload(true); });
  }
  if (late && W.last() && CB.bid === bid) { if (typeof late === 'string') CB.year = late; cbReload(); }
  return true;
}
const cb_unput = e => { const es = CB.list?.entries, i = es ? es.indexOf(e) : -1; if (i >= 0) es.splice(i, 1); };
// a refused entry: its values back into the form (when nothing new is typed there), the reason at the form
function cb_back(e, x) {
  const f = $('#cb-quick'), err = f && cb$('#cb-qerr', f); if (!f) { ofcErr(x); return; }
  const set = (id, v) => { const el = cb$(id, f); if (el) el.value = v ?? ''; };
  if (!cb$('#cb-amount', f).value && !cb$('#cb-text', f).value) {
    CB.dir = e.dir; $$('[data-cb="dir"]').forEach(b => { const on = b.dataset.v === CB.dir; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
    set('#cb-amount', fmtNum(+e.amount, 2)); set('#cb-text', e.text); set('#cb-day', e.day); set('#cb-vat', e.vat_pct); set('#cb-cat', e.category);
    if (err) err.textContent = ofcErrHere(x);
  } else if (err) err.textContent = `${e.text} (${ofcMoney(e.amount)}): ${ofcErrHere(x)}`;
}
// the light draw: only the balance and the entries take the new state (the form keeps focus and what is typed)
function cbLite() {
  if (S.route.mod !== 'office' || ofcTab() !== 'cashbook' || !CB.list || CB.view !== 'entries') return;
  if (!rwPatch($('#view'), cbHtml(), ['.cb-head', '#cb-entries'])) ofcDraw();
}
function cbQuick(f) {
  const val = id => cb$(id, f)?.value ?? '', err = cb$('#cb-qerr', f), bid = CB.bid;
  const amount = ofcNum(val('#cb-amount'));
  if (amount == null || amount <= 0) { err.textContent = tr('Invalid value: {0}', tr('Amount')); cb$('#cb-amount', f)?.focus(); return; }
  if (!bid || !CB.list) return;
  const b = {dir: CB.dir, amount: String(amount), text: val('#cb-text'), day: val('#cb-day') || cbToday(), vat_pct: val('#cb-vat'), category: val('#cb-cat')};
  const W = cb_W(bid), q = cb_q(bid), e = /** @type {any} */ ({...b, vat_pct: b.vat_pct || null, book_id: bid, id: null, no: null, balance: null, _b: b, _ref: outKey()});  // (#3046): its own client_ref
  err.textContent = '';
  for (const id of ['#cb-amount', '#cb-text', '#cb-cat']) { const el = cb$(id, f); if (el) el.value = ''; }
  cb$('#cb-amount', f)?.focus();  // sprung-ok: the person just booked from this form; the next entry starts in its amount
  W.write(() => { q.push(e); if (b.day.slice(0, 4) === CB.year) cb_place(e); return null; }, [rwKey(e)]).catch(() => null);  // the line says it
}
const CB_KEYS = ['day', 'dir', 'amount', 'vat_pct', 'text', 'category', 'node_id', 'invoice_id'];
async function cbLinks() {
  if (!CB.links) { try { CB.links = await api('GET', '/api/office/cashbooks/links'); } catch { CB.links = {receipts: [], invoices: []}; } }
  return CB.links;
}
async function cbEntryModal(e) {
  const ro = e.locked || e.cancelled_by || e.storno_of, links = ro ? {receipts: [], invoices: []} : await openOnce('cb-entry', cbLinks);  // (#7507): loading bar, one open at a time
  if (!links) return;
  const rcs = links.receipts.map(r => [r.node_id, [fmtDateLoc(r.date), r.title, ofcMoney(r.amount)].filter(Boolean).join(' · ')]);
  if (e.node && !rcs.some(r => r[0] === e.node.id)) rcs.unshift([e.node.id, e.node.name]);
  const inv = links.invoices.map(i => [i.id, [i.number, i.client, fmtDateLoc(i.date)].filter(Boolean).join(' · ')]);
  if (e.invoice && !inv.some(i => i[0] === e.invoice.id)) inv.unshift([e.invoice.id, e.invoice.number]);
  const dis = ro ? 'disabled' : '';
  const noInv = !ro && links.invoices_allowed === false;  // 2.538.0 (#4368): no right to book payments on invoices = no choice
  const md = modal(`<h3>${trh('Cash entry no. {0}', e.no)}</h3>
    ${ro ? `<p class="muted">${esc([e.locked ? tr('The day is closed: the entry cannot change any more; cancel it instead.') : '', cbRef(e)].filter(Boolean).join(' · '))}</p>` : ''}
    <fieldset class="cb-fs" ${dis}>
    <div class="row"><label>${tr('Kind')}</label>${ofcSel('cb-edir', e.dir, [['in', tr('Income')], ['out', tr('Expense')]])}</div>
    ${ofcRowF('cb-eamount', tr('Amount'), ofcIn('cb-eamount', fmtNum(+e.amount, 2), {num: true}))}
    ${ofcRowF('cb-etext', tr('Text'), ofcIn('cb-etext', e.text, {max: 300}))}
    <div class="row"><label>${tr('Date')}</label>${dateIn('cb-eday', e.day, {label: tr('Date'), clear: false})}</div>
    ${ofcRowF('cb-evat', tr('VAT rate'), ofcSel('cb-evat', e.vat_pct || '', [['19', '19 %'], ['7', '7 %'], ['0', '0 %']], tr('unknown')))}
    ${ofcRowF('cb-ecat', tr('Category'), ofcIn('cb-ecat', e.category, {max: 60, list: 'cb-cats2'}))}<datalist id="cb-cats2">${CB.base.categories.map(c => `<option value="${esc(c)}">`).join('')}</datalist>
    ${ofcRowF('cb-enode', tr('Receipt'), ofcSel('cb-enode', e.node?.id || '', rcs, tr('none')))}
    ${noInv ? (e.invoice ? `<p class="muted">${esc(tr('Invoice') + ' ' + e.invoice.number)}</p>` : '') : ofcRowF('cb-einv', tr('Invoice paid in cash'), ofcSel('cb-einv', e.invoice?.id || '', inv, tr('none')))}</fieldset>
    <p class="muted">${esc(tr('Balance after this entry: {0}', ofcMoney(e.balance)))} · ${esc(e.by)}</p>
    <div class="aerr" role="alert"></div>
    <div class="foot cb-foot">${!e.cancelled_by && !e.storno_of ? `<button class="btn danger" data-m="cancel">${tr('Cancel entry')}</button>` : ''}<button class="btn" data-m="log">${ic('clock', 's')}<span>${tr('History')}</span></button>
    <span class="spacer"></span><button class="btn" data-m="close">${tr('Close')}</button>${ro ? '' : `<button class="btn pri" data-m="save">${tr('Save')}</button>`}</div>`);
  md.classList.add('ofcdlg');
  const close = fgModal(md);
  const val = id => cb$(id, md)?.value ?? '';
  md.addEventListener('click', async ev => {
    const b = /** @type {any} */ (ev.target).closest('[data-m]'); if (!b) return;
    if (b.dataset.m === 'close') { close(); return; }
    try {
      if (b.dataset.m === 'log') { cbLogModal(e); return; }
      if (b.dataset.m === 'cancel') {
        if (!await askConfirm(tr('Cancel entry no. {0}?', e.no), tr('A counter entry with a new number books the amount back; both stay in the cash book.'), {ok: tr('Cancel entry'), danger: true})) return;
        const j = await api('POST', `/api/office/cash-entries/${e.id}/cancel`, {}); md.remove(); cbReload(true);
        // the undo books the original once more (nothing is deleted)
        toast(tr('Cancelled by no. {0}', j.entry.no), async () => {
          await api('POST', `/api/office/cashbooks/${e.book_id}/entries`, {day: j.entry.day, dir: e.dir, amount: e.amount, vat_pct: e.vat_pct, text: e.text, category: e.category});
          cbReload(true);
        });
        return;
      }
      const amount = ofcNum(val('#cb-eamount'));
      const body = {dir: val('#cb-edir'), amount: amount == null ? '' : String(amount), text: val('#cb-etext'), day: val('#cb-eday'), vat_pct: val('#cb-evat') || null,
        category: val('#cb-ecat'), node_id: +val('#cb-enode') || null, ...(noInv ? {} : {invoice_id: +val('#cb-einv') || null})};
      const old = {dir: e.dir, amount: e.amount, text: e.text, day: e.day, vat_pct: e.vat_pct, category: e.category, node_id: e.node_id, ...(noInv ? {} : {invoice_id: e.invoice_id})};
      const j = await ofcSave(md, `/api/office/cash-entries/${e.id}`, e, body); md.remove(); cbReload(true);  // 2.576.0 (#4794): only the changed fields; saved elsewhere meanwhile -> the merge bar
      if (!j) return;
      // 2.533.0 (#4337): an entry that booked its invoice's payment just now has no undo (its amount / day / invoice are fixed: cancel it)
      if (j?.paid && !e.paid) toast(tr('Saved'));
      else toast(tr('Saved'), async () => { await undoWrite(`/api/office/cash-entries/${e.id}`, old, j?.updated_at, {now: body}).catch(() => null); cbReload(true); });  // 2.566.0 (#4704): core.js undoWrite - only the keys this save changed, against its version; changed since -> said, kept
    } catch (x) { ofcSaveErr(md, x, r => { const m2 = cbEntryModal(r); cbReload(true); return m2; }); }  // 2.576.0 (#4794)
  });
}
const CB_ACT = {create: N_('Created'), change: N_('Changed'), cancel: N_('Cancelled'), close: N_('Day closed'), book_create: N_('Cash box created'), book_change: N_('Cash box changed'), delete: N_('Deleted')};  // 2.162.0 A (#2603): test phase, with a deleted invoice
const CB_FLD = {day: N_('Date'), dir: N_('Kind'), amount: N_('Amount'), vat_pct: N_('VAT rate'), text: N_('Text'), category: N_('Category'), node_id: N_('Receipt'), invoice_id: N_('Invoice')};
function cbPrev(p) {
  return Object.entries(p || {}).filter(([k]) => CB_FLD[k]).map(([k, v]) => {
    const s = k === 'dir' ? (v === 'in' ? tr('Income') : tr('Expense')) : k === 'day' ? (v ? fmtDateLoc(v) : '') : k === 'amount' ? ofcMoney(v) : k === 'vat_pct' ? cbVat(v) : v;
    return `${tr(CB_FLD[k])}: ${s ?? ''}`;
  }).join(' · ');
}
async function cbLogModal(e) {
  let rows;
  try { rows = (await api('GET', `/api/office/cash-entries/${e.id}/log`)).log; } catch (x) { ofcErr(x); return; }
  const md = modal(`<h3>${tr('History')}</h3><p class="muted">${esc(tr('Cash entry no. {0}', e.no))} · ${esc(e.text)}</p>
    <ol class="lgb-log">${rows.slice().reverse().map(r => `<li><b>${esc(tr(CB_ACT[r.action] || r.action))}</b> <span class="muted">${esc(fmtMoment(new Date(r.at)))} · ${esc(r.by)}</span>
      ${r.action === 'cancel' && r.prev.by_no ? `<small>${esc(tr('Cancelled by no. {0}', r.prev.by_no))}</small>` : cbPrev(r.prev) ? `<small>${esc((r.action === 'create' ? '' : tr('Before') + ': ') + cbPrev(r.prev))}</small>` : ''}</li>`).join('')}</ol>
    <div class="foot"><span class="spacer"></span><button class="btn" data-m="close">${tr('Close')}</button></div>`);
  md.classList.add('ofcdlg');
  const close = fgModal(md);
  md.addEventListener('click', ev => { if (/** @type {any} */ (ev.target).closest('[data-m="close"]')) close(); });
}
async function cbCloseModal() {
  const b = cbBook(CB.bid); if (!b) return;
  const md = modal(`<h3>${tr('Close day')}</h3><p class="muted">${esc(b.name)}</p>
    <div class="row"><label>${tr('Day')}</label>${dateIn('cb-cday', cbToday(), {label: tr('Day'), clear: false})}</div>
    <div class="cb-plan" aria-live="polite"></div>
    <p class="muted">${esc(tr('Closing is final and cannot be undone: afterwards no entry up to this day can change, corrections only by cancellation.'))}</p>
    <div class="aerr" role="alert"></div>
    <div class="foot"><span class="spacer"></span><button class="btn" data-m="close">${tr('Cancel')}</button><button class="btn pri" data-m="save" disabled>${tr('Close permanently')}</button></div>`);
  md.classList.add('ofcdlg');
  const close = fgModal(md), err = cb$('.aerr', md), go = cb$('[data-m="save"]', md);
  const preview = async () => {
    err.textContent = ''; go.disabled = true;
    try {
      const p = await api('GET', `/api/office/cashbooks/${b.id}/closing?day=${encodeURIComponent(cb$('#cb-cday', md).value)}`);
      cb$('.cb-plan', md).innerHTML = `<dl class="lgb-dl"><dt>${tr('Opening balance')}</dt><dd>${ofcMoney(p.opening)}</dd><dt>${tr('Income')}</dt><dd>${ofcMoney(p.sum_in)}</dd>
        <dt>${tr('Expense')}</dt><dd>${ofcMoney(p.sum_out)}</dd><dt>${tr('Closing balance')}</dt><dd><b>${ofcMoney(p.closing)}</b></dd></dl>
        <p class="muted">${esc([p.from !== p.day ? tr('Closes {0} to {1}', fmtDateLoc(p.from), fmtDateLoc(p.day)) : fmtDateLoc(p.day), trn('{0} entry', '{0} entries', p.count)].join(' · '))}</p>`;
      go.disabled = false;
    } catch (x) { cb$('.cb-plan', md).innerHTML = ''; err.textContent = ofcErrHere(x); }
  };
  md.addEventListener('change', ev => { if (/** @type {any} */ (ev.target).id === 'cb-cday') preview(); });
  md.addEventListener('click', async ev => {
    const x = /** @type {any} */ (ev.target).closest('[data-m]'); if (!x) return;
    if (x.dataset.m === 'close') { close(); return; }
    if (!await askConfirm(tr('Close the day permanently?'), tr('This cannot be undone.'), {ok: tr('Close permanently'), danger: true})) return;
    try { await api('POST', `/api/office/cashbooks/${b.id}/closing`, {day: cb$('#cb-cday', md).value}); md.remove(); cbReload(true); toast(tr('Day closed')); }
    catch (y) { err.textContent = ofcErrHere(y); }
  });
  preview();
}
async function cbBookNew() {
  try {
    const j = await api('POST', '/api/office/cashbooks', {name: tr('Cash box {0}', (CB.base?.books.length || 0) + 1), opening: '0', opening_day: cbToday()});
    CB.bid = j.id; cbReload(true);
    toast(tr('Added'), async () => { await api('PATCH', `/api/office/cashbooks/${j.id}`, {archived: 1}); cbReload(true); });
  } catch (x) { ofcErr(x); }
}
async function cbBookSet(bid, key, v) {  // autosave of one field of a cash box; one undo step
  const b = cbBook(bid); if (!b || String(b[key]) === String(v)) return;
  const old = b[key];
  try {
    await api('PATCH', `/api/office/cashbooks/${bid}`, {[key]: v}); cbReload(true);
    toast(key === 'archived' ? (v ? tr('Archived') : tr('Restored')) : tr('Saved'), async () => { await api('PATCH', `/api/office/cashbooks/${bid}`, {[key]: old}); cbReload(true); });
  } catch (x) { ofcErr(x); cbReload(true); }
}

// ---- events
document.addEventListener('click', e => {
  // 2.525.0 (#4281): the address books dialog (contacts.js, #cb-body) has data-cb="close" too: its X opened the cash book's
  // "Close day" - clicks inside that dialog are not the cash book's (one-meaning guard: data-cb)
  const b = /** @type {any} */ (e.target).closest?.('[data-cb]'); if (!b || b.tagName === 'INPUT' || b.closest('.modal')?.querySelector('#cb-body')) return;
  const a = b.dataset.cb;
  if (a === 'open') { const x = (CB.list?.entries || []).find(y => y.id === +b.dataset.id); if (x) cbEntryModal(x); }
  else if (a === 'view') { CB.view = b.dataset.v; ofcDraw(); }
  else if (a === 'retry') cbReload(true);  // 2.144.11 (#2354, N5)
  else if (a === 'dir') { CB.dir = b.dataset.v; $$('[data-cb="dir"]').forEach(x => { const on = x.dataset.v === CB.dir; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on); }); }
  else if (a === 'close') cbCloseModal();
  else if (a === 'bnew') cbBookNew();
  else if (a === 'arch') { const x = cbBook(+b.dataset.id); if (x) cbBookSet(x.id, 'archived', x.archived ? 0 : 1); }
  else return;
  e.preventDefault();
});
document.addEventListener('submit', e => { const f = /** @type {any} */ (e.target); if (f.id === 'cb-quick') { e.preventDefault(); cbQuick(f); } });
document.addEventListener('change', e => {
  const x = /** @type {any} */ (e.target);
  if (x.id === 'cb-year') { CB.year = x.value; cbReload(); }
  else if (x.id === 'cb-book') { CB.bid = +x.value; cbReload(); }
  else if (x.closest?.('.cb-bk')) {
    const bid = +x.closest('.cb-bk').dataset.bid, f = x.dataset.cbf || (x.id === `cb-od${bid}` ? 'opening_day' : '');
    if (f === 'opening') { const n = ofcNum(x.value); if (n == null || n < 0) { toast(tr('Invalid value: {0}', tr('Opening balance'))); return; } cbBookSet(bid, f, n.toFixed(2)); }
    else if (f) cbBookSet(bid, f, x.value);
  }
});
