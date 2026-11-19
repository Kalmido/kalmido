"""2.147.1 B (#2054): the GiroCode (EPC QR code, EPC069-12 version 002) on invoices and reminders.

gcq_payload builds the code's text: BCD / 002 / 1 (UTF-8) / SCT / BIC (optional) / name of the payee (max 70) / IBAN /
EUR amount / no purpose / no structured reference / the document number as the unstructured remittance (max 140). Only
for EUR, a valid IBAN of the sender (the office's bank details) and an open amount above 0 -- else None and no code.
gcq_model is called by invoices.inv_render: the setting "girocode" (office settings, default on) decides for drafts; a
finalised document keeps the decision frozen in its sender snapshot (ledger.ofx_finalize notes "girocode"), so a
document finalised before 2.147.1 never gets one when rendered again (GoBD: the archived PDF stays as it was).
gcq_matrix turns the text into the module matrix (segno, error correction M, UTF-8); pdf.py draws it as filled
rectangles (vectors only, no image, no transparency: PDF/A-3 of ZUGFeRD stays valid). The e-invoice XML is unchanged."""
import re
from decimal import Decimal, InvalidOperation

from ..core.i18n import N_, tr
from .ledger import _iban_ok, ofx_locked  # 2.369.5 (#2517): pulled up from functions

GCQ_NAME_MAX = 70
GCQ_REF_MAX = 140
GCQ_AMOUNT_MAX = Decimal("999999999.99")
GCQ_BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")
GCQ_RF_RE = re.compile(r"RF\d{2}[A-Z0-9-]{1,32}")


def _clean(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def gcq_rf(ref):
    """(#6819): an ISO 11649 creditor reference (RF + check digits + up to 21 characters; hyphens as sent are only grouping) -> its
    electronic form without hyphens, else None (no RF reference)."""
    s = str(ref or "").upper()
    if not GCQ_RF_RE.fullmatch(s):
        return None
    s = s.replace("-", "")
    return s if 5 <= len(s) <= 25 else None


def gcq_rf_ok(ref):
    """The mod-97 check of an RF reference (ISO 11649: the first four characters moved to the end, letters as 10..35, the
    number mod 97 = 1)."""
    s = gcq_rf(ref)
    if not s:
        return False
    num = "".join(str(int(ch, 36)) for ch in s[4:] + s[:4])
    return int(num) % 97 == 1


def gcq_payload(name, iban, bic, amount, ref, currency="EUR", sref=""):
    """The EPC QR text or None when no code may be printed (not EUR, no valid IBAN, no name, amount not in 0.01 ..
    999999999.99). (#6819): sref = an ISO 11649 creditor reference (RF..., without hyphens) as the structured
    reference (element 9; the unstructured remittance stays empty then, EPC069-12 allows only one of them)."""
    if (currency or "").upper() != "EUR":
        return None
    iban = re.sub(r"\s+", "", str(iban or "")).upper()
    if not iban or not _iban_ok(iban):
        return None
    name = _clean(name, GCQ_NAME_MAX)
    if not name:
        return None
    try:
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if amt <= 0 or amt > GCQ_AMOUNT_MAX:
        return None
    bic = re.sub(r"\s+", "", str(bic or "")).upper()
    if not GCQ_BIC_RE.match(bic):
        bic = ""
    sref = re.sub(r"[^A-Z0-9]", "", str(sref or "").upper())[:25]
    ref = "" if sref else _clean(ref, GCQ_REF_MAX)
    while True:
        els = ["BCD", "002", "1", "SCT", bic, name, iban, f"EUR{amt}", "", sref, ref]
        while els[-1] == "":  # EPC069-12: unused trailing elements are left out (a draft has no number yet)
            els.pop()
        out = "\n".join(els)
        over = len(out.encode("utf-8")) - 331  # EPC069-12: at most 331 bytes
        if over <= 0:
            return out
        # 2.147.1 (#2054, review): a long multi-byte name / reference is shortened instead of dropping the code; the name
        # first (the document number in the reference matches the payment), down to 20 characters, then the reference
        if len(name) > 20:
            name = name[:-1].rstrip()
        elif ref:
            ref = ref[:-1].rstrip()
        elif len(name) > 1:
            name = name[:-1].rstrip()
        else:
            return None


def gcq_matrix(payload):
    """[[bool, ...], ...] the dark modules of the QR code of payload (no quiet zone), error correction M."""
    import segno
    qr = segno.make(payload, error="m", boost_error=False, micro=False, encoding="utf-8")
    return [[bool(v) for v in row] for row in qr.matrix]


def gcq_model(r, m, s, snd=None):
    """Sets m["payment"]["girocode"] (the EPC text) when the document gets one: invoice = its open amount, reminder = the open
    amounts plus the fee (its total); credit notes never. snd = the decrypted sender snapshot of a finalised document."""
    pay = m.get("payment")
    if not isinstance(pay, dict) or r["kind"] not in ("invoice", "reminder"):
        return m
    if ofx_locked(r):
        on = bool(isinstance(snd, dict) and snd.get("girocode"))
    else:
        on = bool(int((s or {}).get("girocode", 1) or 0))
    if not on:
        return m
    tot = m.get("totals") or {}
    # 2.296.0 B (#3173): an invoice asks for what is still open (gross - paid - credit notes; with a cash discount the full
    # open amount, the discount stays a line of the payment text); a reminder for its total
    # open amount; a draft (no payments or credit notes yet) its gross
    amount = tot.get("open") if r["kind"] == "invoice" and ofx_locked(r) and tot.get("open") not in (None, "") else tot.get("gross") or 0
    # (#6819): an invoice issuer's bank account (docpay.dpy_render): its holder is the payee (banks check the name
    # against the IBAN), its remittance the reference (RF: structured, without hyphens) or the document number
    code = gcq_payload(pay.get("holder") or (m.get("sender_fields") or {}).get("name") or "", pay.get("iban"), pay.get("bic"), amount,
                       pay.get("remit") or r["number"] or "", r["currency"], sref=pay.get("sref") or "")
    if code:
        pay["girocode"] = code
    return m


GCQ_SIZE = 57.0  # 2.434.0 A (#3603): 2 x 2 cm (56.7 pt), the EPC minimum that banking apps read well (was 76 pt, about 2.7 cm)
GCQ_LABELS = ("GiroCode", N_("Scan with banking app|girocode"))  # 2.185.0 C (#2520): through tr() in the document's language
POL_LABELS = (N_("Pay online|document"), N_("Scan with your phone|document"))  # 2.469.0 (#3459): the code of the pay link


def gcq_block_h():
    """The height pdf.py reserves next to the payment text: the code plus its two label lines."""
    return GCQ_SIZE + 22


def gcq_draw(p, x, y, payload, lang, color="#000000", color2="#4b515c", labels=None):
    """Draws the code of payload with its top left corner at (x, y) on page p (pdf.py page: y from the top), the label
    below. One filled rectangle per horizontal run of dark modules (vectors only). 2.469.0 (#3459): labels = other words (the pay link's code)."""
    rows = gcq_matrix(payload)
    n = len(rows) or 1
    mod = GCQ_SIZE / n
    for i, row in enumerate(rows):
        j = 0
        while j < n:
            if not row[j]:
                j += 1
                continue
            k = j
            while k < n and row[k]:
                k += 1
            p.rect(x + j * mod, y + i * mod, (k - j) * mod + 0.02, mod + 0.02, color)  # +0.02: no hairline gaps between rows
            j = k
    t1, t2 = labels or (GCQ_LABELS[0], tr(GCQ_LABELS[1], lg=lang))  # lang: pdf.pdf_lang; 2.434.0 A (#3603): "cr" = a label wider than the smaller code ends at its right edge
    p.text(x, y + GCQ_SIZE + 4, t1, 7, True, color2, align="cr", width=GCQ_SIZE)
    p.text(x, y + GCQ_SIZE + 12.5, t2, 6.2, False, color2, align="cr", width=GCQ_SIZE)
