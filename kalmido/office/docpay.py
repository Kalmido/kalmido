"""(#6819): the payment block of an invoice, chosen when a person finalises it and frozen with the sender snapshot
(ledger.ofx_finalize, sender["pay"]); the print model (invoices.inv_render), the GiroCode (girocode.gcq_model) and the e-invoice
(einvoice.ein_values) read it from there. Three kinds, nothing else is computed, booked or numbered here:

- none (no "pay" in the snapshot): the office's own bank account, as before.
- "paid": the finalise dialog's "Issue as paid" (body as_paid {date, method}): the person confirms each document on its own
  (an invoice issuer's wish.paid stands beside it unconfirmed, never applied by itself: #1146). The document says "Paid on <date>
  by <method>", amount outstanding 0, no bank account, no GiroCode, no due date; the e-invoice the payment means of the method
  (einvoice.ein_values: card 48 -- XRechnung: a text, BR-DE-24 wants card details; cash 10; else ZZZ with the text: never 30/58 without
  an IBAN, BR-61) and the gross as prepaid (BT-113). The payment is booked through invoices.inv_pay_add in the same transaction
  as the finalising (dpy_book): only who may book payments may choose it (403).
- "payee": an invoice issuer's draft named a bank account its admin allowed (office_issuer_payees, wish.payee, checked by the
  draft route #6701): its holder, IBAN and BIC stand on the PDF, in the GiroCode (holder as the payee's name) and in the
  e-invoice (BT-84 IBAN, BT-85 holder, BT-83 the remittance). An account with the mark ref_only ("a payment can be matched
  only by its reference") prints a fixed sentence with the reference (document language) and puts the reference instead of
  the document number into the GiroCode and BT-83; an ISO 11649 reference (RF...) without its hyphens, as the EPC structured
  reference. Without the mark the remittance stays the document number. A third-party account stands only on invoices paid by
  transfer: "Issue as paid" prints none.
Either way the footer leaves out the office's own bank lines (sender.company.bank_lines). An issuer's due_days become the
draft's payment days when it is made (issdocs._make); its due_date is applied when finalising while the draft has none of its
own (dpy_due_apply); a date too close stops finalising (issdocs.isd_due_missing)."""
import re

from ..core.access import Denied
from ..core.errors import BadInput
from ..core.i18n import N_, tr
from ..core.orgcrypt import oc_dec_fields
from ..core.pg import system_ctx
from .calc import dec, money
from .girocode import gcq_rf
from .invoices import _ofr_pay, inv_pay_add
from .issdocs import isd_wish_of

DPY_METHODS = ("transfer", "card", "direct_debit", "paypal", "online", "cash", "other")  # = issdocs.ISD_METHODS
DPY_BOOK = {"transfer": "transfer", "card": "card", "cash": "cash"}  # invoices.PAY_METHODS; the rest is booked as "other" with its name
DPY_WORDS = {"transfer": N_("bank transfer|paid by"), "card": N_("card|paid by"), "direct_debit": N_("direct debit|paid by"),
             "paypal": N_("PayPal|paid by"), "online": N_("online payment|paid by"), "cash": N_("cash|paid by"),
             "other": N_("another payment method|paid by")}
DPY_PAID = N_("Paid on {0} by {1}.|document")
DPY_REF_SENTENCE = N_("Please state the reference {0} with your transfer: only with it can your payment be matched. After the due date, new payment details are in your account with the platform you bought from.|document")  # one line for the text extractor
DPY_HOLDER = N_("Account holder|document")
DPY_MISS_PAYEE = N_("the bank account the invoice issuer named (it was removed: ask the admin)")
DPY_MISS_REF = N_("the payment reference the bank account of the invoice issuer requires")


def _wish(c, oid, r):
    if r["kind"] != "invoice" or not ("issuer_wish" in r.keys() and r["issuer_wish"]):
        return {}
    return (isd_wish_of(c, oid, r) or {}).get("wish") or {}


def dpy_payee(c, oid, r):
    """The bank account an invoice issuer's draft r named (wish.payee): {id, label, holder, iban, bic, ref_only, removed,
    reference} opened, or None (no issuer document, no account named)."""
    w = _wish(c, oid, r)
    if not w.get("payee") or not r["issuer_id"]:
        return None
    with system_ctx(c):  # the account the area's admin allowed this document's issuer (removed ones too: the draft names it)
        p = c.execute("SELECT * FROM office_issuer_payees WHERE id=? AND issuer_id=? AND org_id=?",
                      (int(w["payee"]), int(r["issuer_id"]), int(oid))).fetchone()
    if p is None:
        return {"id": int(w["payee"]), "removed": True}
    f = oc_dec_fields(c, oid, "office_issuer_payees", p) or {}
    return {"id": int(p["id"]), "label": str(f.get("label") or ""), "holder": " ".join(str(f.get("holder") or "").split()),
            "iban": re.sub(r"\s+", "", str(f.get("iban") or "")).upper(), "bic": re.sub(r"\s+", "", str(f.get("bic") or "")).upper(),
            "ref_only": bool(p["ref_only"]), "removed": bool(p["removed_at"]), "reference": str(w.get("reference") or "")}


def dpy_missing(c, oid, r):
    """invoices.inv_missing_keyed: [(key, stored text)] of the issuer's bank account -- removed meanwhile, or its mark ref_only
    without a reference in the draft."""
    p = dpy_payee(c, oid, r)
    if p is None:
        return []
    if p["removed"] or not p.get("iban"):
        return [("payee", [DPY_MISS_PAYEE])]
    if p["ref_only"] and not p["reference"]:
        return [("payee", [DPY_MISS_REF])]
    return []


def dpy_due_apply(c, oid, r):
    """ledger.ofx_finalize, before the required-field check: the due date an invoice issuer asked for, while the draft has
    none of its own (a person's due date wins). The caller reads the row again."""
    w = _wish(c, oid, r)
    if w.get("due_date") and not r["due_date"]:  # due_days were set as the draft's payment days when it was made (issdocs._make)
        c.execute("UPDATE office_docs SET due_date=? WHERE id=? AND org_id=?", (w["due_date"], r["id"], oid))


def dpy_as_paid(b):
    """The finalise body's as_paid {date, method} -> {date, method} checked, or None (absent / false). 400 otherwise."""
    v = b.get("as_paid") if isinstance(b, dict) else None
    if v in (None, False):
        return None
    if not isinstance(v, dict) or set(v) - {"date", "method"}:
        raise BadInput(tr("Invalid value: {0}", "as_paid"))
    d = str(v.get("date") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise BadInput(tr("Invalid value: {0}", "as_paid.date"))
    if v.get("method") not in DPY_METHODS:
        raise BadInput(tr("Invalid value: {0}", "as_paid.method"))
    return {"date": d, "method": v["method"]}


def dpy_freeze(c, oid, uid, r, as_paid, gross):
    """ledger.ofx_finalize: the payment block for sender["pay"] -- {"mode": "paid", date, method, amount} for as_paid (only an
    invoice with a gross above 0, only who may book payments: 403), {"mode": "payee", ...} for an issuer's bank account, else None."""
    if as_paid:
        if r["kind"] != "invoice":
            raise Denied(409, tr("Only an invoice can be issued as paid"))
        if not _ofr_pay(c, uid, oid):
            raise Denied(403, tr("Only who may record payments can issue an invoice as paid"))
        amt = money(dec(gross or 0))
        if amt <= 0:
            raise Denied(409, tr("Only an invoice with an amount can be issued as paid"))
        return {"mode": "paid", "date": as_paid["date"], "method": as_paid["method"], "amount": str(amt)}
    p = dpy_payee(c, oid, r)
    if p is None or p["removed"]:
        return None
    ref = p["reference"] if p["ref_only"] else ""
    return {"mode": "payee", "payee_id": p["id"], "label": p["label"], "holder": p["holder"], "iban": p["iban"], "bic": p["bic"],
            "ref_only": p["ref_only"], "reference": ref}


def dpy_book(c, oid, uid, r, pay):
    """ledger.ofx_finalize, after the finalising (same transaction): the payment of "Issue as paid" through invoices.inv_pay_add
    (its checks: the month open, no date in the future)."""
    m = pay["method"]
    inv_pay_add(c, oid, uid, int(r["id"]), {"date": pay["date"], "amount": pay["amount"], "method": DPY_BOOK.get(m, "other"),
                                            "note": "" if m in DPY_BOOK else tr(DPY_WORDS[m])})


def dpy_of(snd):
    """The frozen payment block of a sender snapshot, or None."""
    p = snd.get("pay") if isinstance(snd, dict) else None
    return p if isinstance(p, dict) and p.get("mode") in ("paid", "payee") else None


def dpy_paid_text(pay, lang, fmt_date, pack):
    return tr(DPY_PAID, fmt_date(pay["date"], pack), tr(DPY_WORDS.get(pay["method"], DPY_WORDS["other"]), lg=lang), lg=lang)


def dpy_render(r, m, pay, lang, fmt_date, pack, number):
    """invoices.inv_render: the payment info of print model m from the frozen block pay (dpy_of). paid: the paid text only,
    prepaid = its amount (einvoice BT-113), the means of its method; payee: holder, IBAN, BIC, the reference sentence and the
    remittance (GiroCode / BT-83)."""
    if pay["mode"] == "paid":
        txt = dpy_paid_text(pay, lang, fmt_date, pack)
        m["payment"] = {"text": txt, "paid": {"method": pay["method"], "amount": pay["amount"], "date": pay["date"], "text": txt}}
        return m
    old = m.get("payment") if isinstance(m.get("payment"), dict) else {}
    text = old.get("text") or ""
    ref = pay.get("reference") or ""
    if ref:
        text = (text + "\n" if text else "") + tr(DPY_REF_SENTENCE, ref, lg=lang)
    rf = gcq_rf(ref) if ref else None
    m["payment"] = {**{k: v for k, v in old.items() if k not in ("iban", "bic", "bank_name", "text", "pay_url")},
                    "iban": pay.get("iban") or "", "bic": pay.get("bic") or "", "bank_name": "", "holder": pay.get("holder") or "",
                    "holder_label": tr(DPY_HOLDER, lg=lang), "text": text, "ref": ref or number,
                    "remit": (rf or ref) if ref else number, "sref": rf or ""}
    return m

