// @ts-check
// 2.778.0 (#5383): the candidate card -- one receipt / invoice that can be a booking's match, with its preview (the picture that
// exists already: the document's stored preview or the small one of a picture file, kalmido/office/candthumb.py; an invoice or
// a card statement shows its icon), amount, date and why it fits. One component for the credit card positions and the bank
// bookings, in their lists (office_cards.js, office_bank.js) and in the walk-through (office_walk.js). The preview area has a
// fixed size, so nothing moves while the picture loads; a picture that fails turns into the icon.
const OCD_ICON = {invoice: 'file', card: 'card', payout: 'bank'};
// c = {id, kind?, label, title?, amount, date?, reason?, thumb?}; o = {btn: the attributes of its take button (data-…), take: its
// text, key: the number key shown (walk-through, mouse / keyboard only), on: the chosen one, sub: a line instead of the reason}
function ocd_card(c, o) {
  const icon = OCD_ICON[c.kind] || 'receipt', name = c.label || c.title || (c.kind === 'invoice' ? tr('Invoice') : tr('Receipt'));
  const sub = [c.date && fmtDateLoc(String(c.date).slice(0, 10)), o.sub ?? c.reason].filter(Boolean).join(' · ');
  // 2.1180.0 (#6147): without a picture (an invoice, a receipt without a preview) a compact card: its icon beside the name
  // instead of an empty preview area of 9rem
  const pv = c.thumb ? `<div class="ocd-pv" aria-hidden="true"><img class="ocd-img" src="${esc(c.thumb)}" alt="" loading="lazy" decoding="async"><span class="ocd-ic">${ic(icon)}</span></div>` : '';
  return `<div class="ocd${o.on ? ' on' : ''}${c.thumb ? '' : ' ocd-flat'}" data-ocd="${esc(String(c.kind || 'receipt'))}:${esc(String(+c.id))}">
    ${/*html-ok*/ pv}<div class="ocd-b"><span class="ocd-n">${c.thumb ? '' : `<span class="ocd-ic" aria-hidden="true">${ic(icon, 's')}</span>`}<b>${esc(name)}</b>${c.amount != null && c.amount !== '' ? `<span class="ocd-amt">${esc(ofcMoney(c.amount))}</span>` : ''}</span>
    ${sub ? `<small class="muted ocd-why">${esc(sub)}</small>` : ''}
    <button type="button" class="btn sm pri ocd-take" ${/*html-ok*/ o.btn}>${o.key ? `<kbd class="ocd-key">${esc(String(o.key))}</kbd>` : ''}${ic('check', 's')}<span>${esc(o.take || tr('Take over'))}</span></button></div></div>`;
}
// several cards side by side (a phone: one per screen width, swiped sideways)
const ocd_row = (html, cls = '') => `<div class="ocdrow ${esc(cls)}">${/*html-ok*/ html}</div>`;
// a preview that cannot be shown (deleted meanwhile, 404 / 429): the icon instead, the card keeps its size
document.addEventListener('error', e => {
  const t = /** @type {any} */ (e.target);
  if (t?.classList?.contains('ocd-img')) { t.closest('.ocd-pv')?.classList.add('none'); t.remove(); }
}, true);
