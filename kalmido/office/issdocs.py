"""(#6701): the invoice drafts of an invoice issuer (office/issuers.py) -- the outside system sends what was bought, Kalmido
computes, a person in the office checks, finalises and sends (review mode, the only one).

    POST /api/v1/issuer/invoices                       {client_ref, client: {external_ref}, items, expect, service_from?, service_to?,
                                                        order_ref?, vat_note?, vat_check?, business_check?, wish?}
                                                        -> 201 a draft / 200 the same request again (ISD_PUBLIC)
    GET  /api/v1/issuer/docs?changed_since=&cursor=&limit=   the issuer's documents changed since then (the reconciliation)
    GET  /api/v1/issuer/docs/<id> | /docs/by-ref/<client_ref>   one of them (ISD_PUBLIC)
    GET  /api/v1/issuer/docs/<id>/pdf                  the preview of a draft (watermark), only as the key delivered it
    GET  /api/v1/issuer/docs/<id>/file?kind=pdf|xml    (#6818) the archived file of a finalised document, byte for byte
    POST /api/v1/issuer/docs/<id>/withdraw             a draft into the office's trash (a person can restore it)

Rules (the design's section 2.4 "invoice draft", "idempotency", "what the read routes show"; decided 16.11.2026 17:32 and
17.11.2026 09:15):
  - A fixed list of fields (ISD_KEYS, ISD_ITEM_KEYS, ISD_WISH_KEYS ...); an unknown one 400 unknown_field: there is no field for
    the date (Kalmido dates the document when a person finalises it, office/ledger.py ofx_range_date), the number, the range (the
    issuer's own), finalising, sending, the currency (the office's), a free IBAN / BIC or a link.
  - Positions: at most ISD_ITEMS_MAX; title (ISD_TITLE_MAX), detail, quantity > 0, unit (Kalmido's units but percent), net unit
    price >= 0 with at most 4 places, tax standard / reduced / exempt; no discounts, services or texts of the office. Texts with an
    IBAN form, a web or an e-mail address are refused (office/issclients.py isc_text_check, 400 invalid_field + field).
  - Kalmido computes through the person's own functions (docs.doc_create / _put_items / recalc, invoices.inv_missing): each line
    quantity x unit price rounded half up to the cent, summed, the tax per rate on that sum. expect {net, tax, gross} is required:
    a sum that differs makes nothing (409 totals_mismatch with Kalmido's sums). The gross must be above 0.
  - vat_note is a proposal: Kalmido's checks of finalising stay the gate (missing). vat_check and business_check are stored as the
    caller's statements, never printed and never proof of anything (reverse charge waits for a person in every stage).
  - wish: the unconfirmed statements a person sees in the office: send (bool), paid {amount, date, method, provider?, online_ref?},
    payee (the id of an account the admin allowed) with payee_check (its IBAN's last four characters: another = 409
    payee_mismatch, nothing made, an alarm), reference (A-Z 0-9 -, up to 35), due_days or due_date (both = 400; a due date less
    than 7 days after the document's date stops finalising: invoices.inv_missing). Applied when a person finalises: #6819.
  - Idempotency: client_ref is required, unique per issuer (office_issuer_refs, route "invoices"; never office_docs.client_ref).
    The SHA-256 of the checked, normalised request (sorted keys, amounts as normalised decimals, texts NFC; without vat_check and
    business_check) is kept: the same ref with the same content = 200 with the document as it is now (a person's correction
    meanwhile changes nothing), with another content = 409 ref_conflict, a ref whose draft was withdrawn, deleted or purged
    from the trash = 410 withdrawn, for good. Order in one transaction: the issuer's lock -> the ref -> the limits -> the ref row
    and the document; 400 / 409 / 410 / 429 store no ref.
  - Limits (office_issuers, rolling 24 hours): day_docs drafts, open_drafts waiting drafts: 429 limit_reached (an alarm, no
    pause); over max_gross or day_gross the draft is made anyway with the flag over_limit and an alarm. day_withdraw drafts
    withdrawn. A key's PDF preview ISD_PDF_RATE a minute.
  - Flags: over_limit, client_new (the first draft of a client the key set up), client_changed (the client has a hold mark from
    the key's changes), vat_territory (the client's postcode lies in a territory outside the EU's VAT area that has no country
    code of its own, office/countries.py fk_vat_territory). client_lookalike stays in the client's mark (the key never hears it).
  - What the key reads: its own documents only (issuer_id), through a fixed list of fields (isd_public): never the introduction,
    the project, the person who made it or a payment's note. A correction a person makes of its invoice inherits issuer_id
    (origin "manual", no client_ref); a document a person numbered in the issuer's range shows in changed_since with the same
    list (origin "manual"), but GET by id stays 404 for it.
  - The preview: only of a draft whose document, positions and client still match what the key delivered (issuer_rev: the
    fingerprints of the document and of the client; the key's own change of the client renews the client's one), else 409
    edited_by_human; watermark DRAFT like every draft (pdfweb.epdf_mark).
  - A personal office: the draft is the owner's (created_by), like the issuer's clients.
  - An issuer's draft never becomes a series template (office/recurring.py), a copy never keeps issuer_id (docs.DUP_SKIP), its
    client can only be changed to another client of the same issuer (docs.clean_doc).
  - Log: every draft and every withdrawal one line issuer_write, reads once an hour and target; a 404 on an id counts towards the
    self-pause (issuers._iss_refuse), a 404 by ref does not.
  - (#6818) The finished file: GET /docs/<id>/file?kind=pdf|xml of the key's own documents (issuer_id, also a person's correction
    that inherited it), from finalising on (a draft 409 not_final). The archived file (pdfweb.epdf_stored: sealed, its SHA-256
    checked) byte for byte with X-Content-SHA256; kind=xml is the e-invoice XML that was stored (ZUGFeRD: the XML embedded in
    the PDF, XRechnung: the invoice itself). Never rendered anew: no archived file = 409 not_final. ISD_FILE_RATE a minute,
    every delivery one log line (issuer_read, target file:<kind>:<id>, never merged). Reads only: no writing, finalising or
    sending."""
import hashlib
import json
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import g, jsonify, request

from ..accounts.session import client_ip
from ..api.common import v1_err, v1_view
from ..collab.integfail import INTEG_TEXT
from ..core.access import Denied, live_sql
from ..core.config import app
from ..core.db import bump, iso, iso_ms, local_now, now_utc, parse_iso
from ..core.errors import BadInput, UnknownFields
from ..core.i18n import N_, tr
from ..core.orgcrypt import oc_dec_fields, oc_enc
from ..core.pg import system_ctx, write_lock
from ..core.ratedb import rate_hit
from ..notify.alerts import fx2_mask_ip
from .calc import TAX_KEYS, INV_VAT_NOTES, calc_tax_day, dec, money
from .countries import fk_vat_territory
from .docs import _j, _put_items, doc_create, doc_items, doc_row, odoc_trash, recalc
from .invoices import inv_missing, inv_paid_map, inv_state
from .packs import office_pack_for
from .ledger import ofx_locked
from .pdfweb import _file_response, _render, epdf_name, epdf_out, epdf_stored
from .isshold import ihd_load
from .issclients import ISC_REF_RE, isc_body, isc_gone, isc_limit_tell, isc_notice, isc_row, isc_text_check
from .issuers import ISS_ROUTES, _iss_me, _iss_once, _iss_read_logged, _iss_refuse, iss_log, iss_tell
from .model import UNITS, office_settings, pb_owner

ISD_POST = "/api/v1/issuer/invoices"
ISD_LIST = "/api/v1/issuer/docs"
ISD_ONE = "/api/v1/issuer/docs/<int:did>"
ISD_REF = "/api/v1/issuer/docs/by-ref/<path:ref>"
ISD_PDF = "/api/v1/issuer/docs/<int:did>/pdf"
ISD_WITHDRAW = "/api/v1/issuer/docs/<int:did>/withdraw"
ISD_FILE = "/api/v1/issuer/docs/<int:did>/file"  # (#6818)
ISS_ROUTES.update({("POST", ISD_POST), ("GET", ISD_LIST), ("GET", ISD_ONE), ("GET", ISD_REF), ("GET", ISD_PDF), ("POST", ISD_WITHDRAW),
                   ("GET", ISD_FILE)})
ISD_REF_ROUTE = "invoices"  # office_issuer_refs.route of a draft
ISD_KEYS = ("client_ref", "client", "items", "expect", "service_from", "service_to", "order_ref", "vat_note", "vat_check", "business_check", "wish")
ISD_ITEM_KEYS = ("text", "detail", "qty", "unit", "rate", "tax")
ISD_WISH_KEYS = ("send", "paid", "payee", "payee_check", "reference", "due_days", "due_date")
ISD_PAID_KEYS = ("amount", "date", "method", "provider", "online_ref")
ISD_VAT_CHECK_KEYS = ("source", "checked_at", "valid", "request_id", "vat_id")
ISD_BUSINESS_KEYS = ("checked_at", "kind", "source", "ref")
ISD_METHODS = ("transfer", "card", "direct_debit", "paypal", "online", "cash", "other")
ISD_UNITS = tuple(u for u in UNITS if u != "percent")
ISD_ITEMS_MAX = 50
ISD_TITLE_MAX, ISD_DETAIL_MAX, ISD_ORDER_REF_MAX, ISD_INFO_MAX = 200, 1000, 80, 120
ISD_PDF_RATE = 10        # previews of one issuer a minute
ISD_FILE_RATE = 10       # (#6818) archived files of one issuer a minute (a clock of its own, as low as the preview's)
ISD_FILE_MIME = {"pdf": "application/pdf", "xml": "application/xml"}
ISD_DUE_MIN_DAYS = 7     # a due date asked for less than this many days after the document's date stops finalising
ISD_PAGE = 100           # documents of one page of changed_since (limit up to ISD_PAGE_MAX)
ISD_PAGE_MAX = 500
ISD_REF_RE = re.compile(r"[A-Z0-9-]{1,35}")
# the client's columns its fingerprint holds (what the preview prints of it): a person's change of one = edited_by_human
ISD_CLIENT_COLS = ("name", "name_extra", "contact", "address", "street", "address_extra", "zip", "city", "country", "vat_id",
                   "email_invoice", "buyer_reference", "doc_lang", "customer_no")
# the fingerprint of a draft (the preview only as delivered): every column of the document and of its positions but these (identity,
# state, versions, sums Kalmido derives, the issuer's own columns). Review F2 of #6701: an exclusion list, so a person's change
# of any printed field (free fields, rights, date, discounts, a position's switches) ends the preview
ISD_DOC_SKIP = frozenset(("id", "org_id", "number", "status", "totals", "created_at", "created_by", "updated_at", "updated_by", "rev",
                          "issuer_id", "issuer_wish", "issuer_rev", "ref_sha256", "client_ref", "sent_at", "deleted_at", "deleted_by",
                          "trash_refs", "locked_at", "locked_by", "agent_id", "cashflow"))
ISD_ITEM_SKIP = frozenset(("id", "doc_id", "org_id", "sort", "agent_flag", "created_at", "updated_at", "updated_by", "rev", "net",
                           "tax_pct", "tax_amount", "cost_enc", "deleted_at", "deleted_by"))

INTEG_TEXT.update({
    "issuer_over_limit": N_("Invoice issuer {0} sent a draft over its limit ({1}). Check it before you finalise it."),
    "issuer_payee_mismatch": N_("Invoice issuer {0} named a bank account whose IBAN does not end as it said. Nothing was made."),
    "issuer_waiting": N_("Invoice issuer {0}: {1} drafts wait for a person for longer than its limit."),
})
ISD_LIMIT_DOCS = N_("drafts within 24 hours")
ISD_LIMIT_OPEN = N_("waiting drafts")
ISD_LIMIT_WITHDRAW = N_("withdrawn drafts within 24 hours")
ISD_OVER_GROSS = N_("the gross of one draft")
ISD_OVER_DAY = N_("the gross of the drafts within 24 hours")
ISD_DUE_SHORT = N_("a due date at least {0} days after the date (asked for by the invoice issuer: {1})")


class IsdErr(Exception):
    """An answer of the key's routes with its error name (and headers, extras)."""

    def __init__(self, code, msg, name, headers=None, **extra):
        super().__init__(msg)
        self.code, self.msg, self.name, self.headers, self.extra = code, msg, name, headers or {}, extra


def _bad(field, msg=None):
    return IsdErr(400, msg or tr("Invalid value: {0}", field), "invalid_field", field=field)


def _answer(fn):
    """v1_view's errors, plus IsdErr and the invalid_field of the client checks (issclients.isc_text_check)."""
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except IsdErr as e:
            return v1_err(e.code, e.msg, e.headers, name=e.name, **e.extra)
        except UnknownFields:
            raise
        except BadInput as e:
            v1 = getattr(e, "v1", None)
            if v1:
                return v1_err(400, str(e), name=v1["name"], field=v1["field"])
            raise
    run.__name__ = fn.__name__
    run.__doc__ = fn.__doc__
    return run


# ---------------------------------------------------------------- checking the request
def _only(d, keys, where):
    if not isinstance(d, dict):
        raise _bad(where)
    extra = sorted(k for k in d if k not in keys)
    if extra:
        raise UnknownFields([f"{where}.{k}" if where else k for k in extra])


def _text(v, field, mx, need=False):
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise _bad(field)
    v = unicodedata.normalize("NFC", re.sub(r"[ \t]+", " ", v.replace("\r\n", "\n")).strip())
    if need and not v:
        raise _bad(field, tr("{0} is needed", field))
    if len(v) > mx:
        raise _bad(field, tr("{0}: at most {1} characters", field, mx))
    if any(ord(ch) < 32 and ch != "\n" for ch in v):
        raise _bad(field)
    isc_text_check(field, v)  # an IBAN form, a web or an e-mail address: 400 (never only a flag on a document)
    return v


def _amount(v, field, places=2, lo=Decimal(0), hi=Decimal("100000000"), strict_lo=False):
    """A decimal from a JSON number or a text with a point ("150.00"); at most places places; lo <= v <= hi (strict_lo: v > lo)."""
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise _bad(field)
    try:
        d = Decimal(str(v).strip())
    except InvalidOperation:
        raise _bad(field) from None
    if not d.is_finite() or (d <= lo if strict_lo else d < lo) or d > hi:
        raise _bad(field)
    if -d.as_tuple().exponent > places and d != d.quantize(Decimal(1).scaleb(-places)):
        raise _bad(field, tr("{0}: at most {1} decimal places", field, places))
    return d


def _canon(d):
    """A decimal as its normalised text (150.00 -> "150", 1.50 -> "1.5")."""
    t = format(d.normalize(), "f")
    return "0" if t in ("-0", "") else t


def _date_of(v, field):
    if not isinstance(v, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        raise _bad(field, tr("{0}: a date as YYYY-MM-DD", field))
    try:
        return date.fromisoformat(v.strip()).isoformat()
    except ValueError:
        raise _bad(field, tr("{0}: a date as YYYY-MM-DD", field)) from None


def _ts(v):
    """A time of the database as its full ISO text (microseconds kept: the cursor of changed_since)."""
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _info(d, keys, where):
    """vat_check / business_check: the caller's statement, a flat object of its keys (texts, true / false); stored, never printed."""
    if d is None:
        return None
    _only(d, keys, where)
    out = {}
    for k, v in d.items():
        if isinstance(v, bool) or v is None:
            out[k] = v
        elif isinstance(v, (str, int, float)):
            out[k] = _text(str(v), f"{where}.{k}", ISD_INFO_MAX)
        else:
            raise _bad(f"{where}.{k}")
    return out


def isd_clean(b):
    """(normalised request for the hash, the stored statements) of body b, or 400 (unknown_field / invalid_field)."""
    _only(b, ISD_KEYS, "")
    ref = b.get("client_ref")
    if not isinstance(ref, str) or not ISC_REF_RE.fullmatch(ref):
        raise _bad("client_ref", tr("client_ref: 1 to 64 letters, digits or . _ : - (no slash)"))
    cl = b.get("client")
    _only(cl, ("external_ref",), "client")
    ext = cl.get("external_ref")
    if not isinstance(ext, str) or not ISC_REF_RE.fullmatch(ext):
        raise _bad("client.external_ref", tr("external_ref: 1 to 64 letters, digits or . _ : - (no slash)"))
    items = b.get("items")
    if not isinstance(items, list) or not items:
        raise _bad("items", tr("items: at least one position"))
    if len(items) > ISD_ITEMS_MAX:
        raise _bad("items", tr("items: at most {0} positions", ISD_ITEMS_MAX))
    rows = []
    for i, it in enumerate(items):
        _only(it, ISD_ITEM_KEYS, f"items[{i}]")
        unit = it.get("unit") or "piece"
        if unit not in ISD_UNITS:
            raise _bad(f"items[{i}].unit", tr("unit: one of {0}", ", ".join(ISD_UNITS)))
        tax = it.get("tax") or "standard"
        if tax not in TAX_KEYS:
            raise _bad(f"items[{i}].tax", tr("tax: one of {0}", ", ".join(TAX_KEYS)))
        rows.append({"text": _text(it.get("text"), f"items[{i}].text", ISD_TITLE_MAX, need=True),
                     "detail": _text(it.get("detail"), f"items[{i}].detail", ISD_DETAIL_MAX),
                     "qty": _amount(it.get("qty", 1), f"items[{i}].qty", 4, hi=Decimal(1000000), strict_lo=True),
                     "unit": unit, "rate": _amount(it.get("rate"), f"items[{i}].rate", 4), "tax": tax})
    ex = b.get("expect")
    _only(ex, ("net", "tax", "gross"), "expect")
    if set(ex) != {"net", "tax", "gross"}:
        raise _bad("expect", tr("expect: net, tax and gross are needed"))
    expect = {k: _amount(ex[k], f"expect.{k}", 2, hi=Decimal("1000000000")) for k in ("net", "tax", "gross")}
    sf = _date_of(b["service_from"], "service_from") if b.get("service_from") is not None else ""
    st = _date_of(b["service_to"], "service_to") if b.get("service_to") is not None else ""
    if bool(sf) != bool(st) or (sf and st < sf):
        raise _bad("service_to", tr("The period of service ends before it starts") if sf and st else tr("service_from and service_to go together"))
    vn = b.get("vat_note")
    if vn not in (None, "") and vn not in INV_VAT_NOTES:
        raise _bad("vat_note", tr("vat_note: one of {0}", ", ".join(INV_VAT_NOTES)))
    wish = _wish(b.get("wish"))
    norm = {"client_ref": ref, "client": {"external_ref": ext}, "service_from": sf, "service_to": st,
            "order_ref": _text(b.get("order_ref"), "order_ref", ISD_ORDER_REF_MAX), "vat_note": vn or "",
            "items": [{**r, "qty": _canon(r["qty"]), "rate": _canon(r["rate"])} for r in rows],
            "expect": {k: _canon(v) for k, v in expect.items()}, "wish": wish}
    told = {"vat_check": _info(b.get("vat_check"), ISD_VAT_CHECK_KEYS, "vat_check"),
            "business_check": _info(b.get("business_check"), ISD_BUSINESS_KEYS, "business_check")}
    return norm, told, rows, expect


def _wish(w):
    if w is None:
        return {}
    _only(w, ISD_WISH_KEYS, "wish")
    out = {}
    if "send" in w:
        if not isinstance(w["send"], bool):
            raise _bad("wish.send")
        out["send"] = w["send"]
    if w.get("paid") is not None:
        p = w["paid"]
        _only(p, ISD_PAID_KEYS, "wish.paid")
        if p.get("method") not in ISD_METHODS:
            raise _bad("wish.paid.method", tr("method: one of {0}", ", ".join(ISD_METHODS)))
        out["paid"] = {"amount": _canon(_amount(p.get("amount"), "wish.paid.amount", 2, strict_lo=True)),
                       "date": _date_of(p.get("date"), "wish.paid.date"), "method": p["method"],
                       "provider": _text(p.get("provider"), "wish.paid.provider", 40),
                       "online_ref": _text(p.get("online_ref"), "wish.paid.online_ref", ISD_INFO_MAX)}
    if w.get("payee") is not None:
        if isinstance(w["payee"], bool) or not isinstance(w["payee"], int) or w["payee"] <= 0:
            raise _bad("wish.payee")
        chk = w.get("payee_check")
        if not isinstance(chk, str) or not re.fullmatch(r"[A-Za-z0-9]{4}", chk):
            raise _bad("wish.payee_check", tr("payee_check: the last four characters of the account's IBAN"))
        out["payee"], out["payee_check"] = int(w["payee"]), chk.upper()
    elif w.get("payee_check") is not None:
        raise _bad("wish.payee_check", tr("payee_check goes with payee"))
    if w.get("reference") is not None:
        if not isinstance(w["reference"], str) or not ISD_REF_RE.fullmatch(w["reference"]):
            raise _bad("wish.reference", tr("reference: up to 35 of A-Z, 0-9 and -"))
        out["reference"] = w["reference"]
    if w.get("due_days") is not None and w.get("due_date") is not None:
        raise _bad("wish.due_date", tr("due_days or due_date, not both"))
    if w.get("due_days") is not None:
        v = w["due_days"]
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 365:
            raise _bad("wish.due_days")
        out["due_days"] = v
    if w.get("due_date") is not None:
        out["due_date"] = _date_of(w["due_date"], "wish.due_date")
    return out


def isd_sha(norm):
    """The SHA-256 of the normalised request (+ the route): sorted keys, no spaces, UTF-8."""
    raw = json.dumps({"route": ISD_REF_ROUTE, **norm}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- fingerprints (the preview only as delivered)
def _fp(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _val(v):
    if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
        return _canon(dec(v))
    return "" if v is None else str(v)


def isd_doc_fp(c, oid, r):
    """The fingerprint of document r with its positions (all columns but ISD_DOC_SKIP / ISD_ITEM_SKIP)."""
    head = {k: _val(r[k]) for k in r.keys() if k not in ISD_DOC_SKIP}
    items = [{k: _val(v) for k, v in dict(it).items() if k not in ISD_ITEM_SKIP} for it in doc_items(c, r["id"], oid)]
    return _fp({"doc": head, "items": items})


def isd_client_fp(c, cid):
    with system_ctx(c):  # the issuer's client (the caller checked it is the issuer's own)
        cl = c.execute("SELECT * FROM clients WHERE id=?", (int(cid),)).fetchone() if cid else None
    return _fp({k: _val(cl[k]) for k in ISD_CLIENT_COLS if k in cl.keys()}) if cl else ""


def isd_client_changed(c, iss_id, cid, before):
    """The key changed its client cid (office/issclients.py isc_put): the client's fingerprint of its drafts of that client is
    renewed where it was the client's before the change (before) -- review F4: a draft whose client a person had changed
    meanwhile stays at 409 edited_by_human, the key's own change never clears it; the document's fingerprint stays."""
    fp = isd_client_fp(c, cid)
    with system_ctx(c):  # the issuer's own drafts
        rows = c.execute("SELECT id, issuer_rev FROM office_docs WHERE issuer_id=? AND client_id=? AND status='draft'", (int(iss_id), int(cid))).fetchall()
        for r in rows:
            rev = _rev(r["issuer_rev"])
            if rev.get("client") != before:
                continue
            c.execute("UPDATE office_docs SET issuer_rev=? WHERE id=?", (json.dumps({**rev, "client": fp}), r["id"]))


def _rev(v):
    try:
        d = json.loads(v or "{}")
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def isd_wish_of(c, oid, r):
    """The stored statements of document r (issuer_wish, opened): {} without."""
    v = r["issuer_wish"] if "issuer_wish" in r.keys() else None
    if not v:
        return {}
    if isinstance(v, str) and v.startswith("kenc1:"):
        v = (oc_dec_fields(c, oid, "office_docs", {"issuer_wish": v}) or {}).get("issuer_wish")
    try:
        d = json.loads(v or "{}")
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def isd_due_missing(r, wish):
    """invoices.inv_missing: a due date the issuer asked for that lies less than ISD_DUE_MIN_DAYS days after the document's
    date (the day of finalising for a document of a range) -> the missing entry, else None."""
    due = ((wish or {}).get("wish") or {}).get("due_date")
    if not due or r["kind"] != "invoice":
        return None
    try:
        day = date.fromisoformat(str(r["date"] or "")[:10])
    except ValueError:
        day = local_now().date()
    if date.fromisoformat(due) < day + timedelta(days=ISD_DUE_MIN_DAYS):
        return [ISD_DUE_SHORT, ISD_DUE_MIN_DAYS, due]
    return None


def isd_office_view(c, oid, r):
    """What a person sees of an issuer's document in the office (docs.doc_public): issuer {id, name} ("made by invoice issuer
    ...") and issuer_wish = the outside system's unconfirmed statements (wish, vat_check, business_check, flags, client_ref);
    no booking, no sending from them in stage 1."""
    with system_ctx(c):  # the issuer's name (its row belongs to the area)
        i = c.execute("SELECT id, name, revoked_at FROM office_issuers WHERE id=? AND org_id=?", (int(r["issuer_id"]), int(oid))).fetchone()
    w = isd_wish_of(c, oid, r)
    out = {"issuer": {"id": int(r["issuer_id"]), "name": (i["name"] if i else "") or f"#{int(r['issuer_id'])}", "revoked": bool(i and i["revoked_at"])}}
    out["issuer_wish"] = {k: w.get(k) for k in ("wish", "vat_check", "business_check", "flags", "client_ref", "vat_note") if w.get(k) not in (None, "", [], {})} or None
    if out["issuer_wish"] and r["status"] == "draft" and r["client_id"]:
        out["issuer_wish"]["flags"] = isd_flags(c, oid, r, w)
    return out


# ---------------------------------------------------------------- what the key reads
def _range_code(c, iss):
    with system_ctx(c):  # the issuer's own range
        rg = c.execute("SELECT code FROM office_num_ranges WHERE id=? AND org_id=?", (iss["range_id"], iss["org_id"])).fetchone()
    return rg["code"] if rg else ""


def _refs_of(c, iss, ids):
    if not ids:
        return {}
    with system_ctx(c):  # the issuer's own refs
        return {r["doc_id"]: r["client_ref"] for r in c.execute(
            "SELECT doc_id, client_ref FROM office_issuer_refs WHERE issuer_id=? AND route=? AND doc_id = ANY(CAST(? AS BIGINT[]))",
            (int(iss["id"]), ISD_REF_ROUTE, [int(x) for x in ids])).fetchall()}


def isd_flags(c, oid, r, wish):
    """The flags of draft r for the key: the stored ones (over_limit) and the client's now (client_new, client_changed,
    vat_territory)."""
    fl = set(wish.get("flags") or [])
    if r["client_id"]:
        with system_ctx(c):  # the issuer's client
            cl = c.execute("SELECT issuer_hold, country, zip FROM clients WHERE id=?", (r["client_id"],)).fetchone()
        if cl is not None:
            h = ihd_load(cl["issuer_hold"])
            if h and h.get("new"):
                fl.add("client_new")
            elif h and h.get("fields"):
                fl.add("client_changed")
            if fk_vat_territory(cl["country"], cl["zip"]):
                fl.add("vat_territory")
    return sorted(fl)


def isd_public(c, iss, r, ref=None, origin=None, pm=None):
    """The document as the key sees it -- a fixed list of fields, nothing else of the row (the design's 'what the read routes
    show'): doc_id, client_ref, origin, kind, status, range, number, date, service period, due date, totals, corrects_doc_id,
    payments {date, amount, method}, and for a draft missing + flags."""
    oid = int(r["org_id"])
    trashed = bool(r["deleted_at"]) if "deleted_at" in r.keys() else False
    pm = pm if pm is not None else inv_paid_map(c, oid, [r["id"]])
    t = _j(r["totals"], {})
    st = "withdrawn" if trashed else inv_state(r, pm)
    with system_ctx(c):  # the payments of the issuer's document (date, amount, method; never the note)
        pays = [{"date": p["date"], "amount": str(money(dec(p["amount"]))), "method": p["method"]} for p in c.execute(
            "SELECT date, amount, method FROM office_payments WHERE doc_id=? AND org_id=? ORDER BY date, id", (r["id"], oid)).fetchall()]
    out = {"doc_id": int(r["id"]), "client_ref": ref, "origin": origin or ("issuer" if ref else "manual"), "kind": r["kind"],
           "status": st, "range": _range_code(c, iss) if r["range_id"] == iss["range_id"] else "", "number": r["number"] or None,
           "date": (r["date"] or None) if r["number"] else None, "service_from": r["service_from"] or None,
           "service_to": r["service_to"] or None, "due_date": r["due_date"] or None,
           "totals": {"net": str(money(dec(t.get("net") or 0))), "tax": str(money(dec(t.get("tax") or t.get("tax_total") or 0))),
                      "gross": str(money(dec(t.get("gross") or 0))), "currency": r["currency"]},
           "corrects_doc_id": r["cancels_id"] if r["kind"] == "credit" else None, "payments": pays,
           "updated_at": _ts(r["updated_at"])}
    if r["status"] == "draft" and not trashed and r["issuer_id"] == iss["id"]:
        r = oc_dec_fields(c, oid, "office_docs", r)
        s = office_settings(c, oid)
        pack = office_pack_for(s, calc_tax_day(dict(r))) or {}
        out["missing"] = [tr(*m) for m in inv_missing(c, oid, r, s, pack, doc_items(c, r["id"], oid))]  # ISS_REUSED
        out["flags"] = isd_flags(c, oid, r, isd_wish_of(c, oid, r))
    return out


def _doc(c, iss, did, live=False):
    """The issuer's own document did (issuer_id, its area; also a corrected one a person made), None otherwise."""
    with system_ctx(c):  # the row by its id, filtered to the issuer below (row-level security is no limit for the key)
        r = c.execute("SELECT * FROM office_docs WHERE id=? AND org_id=? AND issuer_id=?" + (f" AND {live_sql()}" if live else ""),
                      (int(did), int(iss["org_id"]), int(iss["id"]))).fetchone()
    return r


def _ref_row(c, iss, ref):
    with system_ctx(c):  # the issuer's own ref
        return c.execute("SELECT * FROM office_issuer_refs WHERE issuer_id=? AND route=? AND client_ref=?",
                         (int(iss["id"]), ISD_REF_ROUTE, ref)).fetchone()


def _log_read(c, iss, target):
    if not _iss_read_logged(c, iss, target):
        iss_log(c, iss["org_id"], iss["id"], "issuer_read", target, {"key": g.issuer_key["prefix"], "ip": fx2_mask_ip(client_ip())}, name=iss["name"])
        c.commit()


def _no_doc(c, iss):
    """A 404 on an id: it counts towards the self-pause (issuers._iss_refuse, kind "id")."""
    return _iss_refuse(c, iss, g.issuer_key, 404, tr("Not found"), "not_found", "id")


def _limit(c, iss, what, text, retry=3600):
    isc_limit_tell(c, iss, what, text)
    return IsdErr(429, tr("The invoice issuer reached its limit of {0}", tr(text)), "limit_reached", {"Retry-After": str(retry)})


# ---------------------------------------------------------------- the routes
@app.post("/api/v1/issuer/invoices")  # = ISD_POST (a literal: tests/routes_ast.py)
@v1_view
@_answer
def isd_post():
    """An invoice draft of the issuer (module text): 201 made, 200 the same request again."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    b = isc_body()
    norm, told, rows, expect = isd_clean(b)
    sha = isd_sha(norm)
    oid, iid = int(iss["org_id"]), int(iss["id"])
    ref = norm["client_ref"]
    write_lock(c, f"issuer-{iid}")  # one write of this issuer at a time: two equal requests at once = one draft
    hit = _ref_row(c, iss, ref)
    if hit is not None:  # the ref first: a retry counts against no limit
        if hit["body_sha256"] != sha:
            raise IsdErr(409, tr("This client_ref was sent before with another content"), "ref_conflict")
        r = _doc(c, iss, hit["doc_id"]) if hit["doc_id"] else None
        if r is None or r["deleted_at"]:
            raise IsdErr(410, tr("The draft of this client_ref was withdrawn or deleted in the office"), "withdrawn")
        out = isd_public(c, iss, r, ref)
        c.commit()
        return jsonify(out), 200
    since = iso(now_utc() - timedelta(days=1))
    with system_ctx(c):  # the issuer's own refs and drafts
        n_day = c.execute("SELECT COUNT(*) FROM office_issuer_refs WHERE issuer_id=? AND route=? AND created_at>=?", (iid, ISD_REF_ROUTE, since)).fetchone()[0]
        n_open = c.execute(f"SELECT COUNT(*) FROM office_docs WHERE issuer_id=? AND org_id=? AND status='draft' AND {live_sql()}", (iid, oid)).fetchone()[0]
    if n_day >= int(iss["day_docs"]):
        raise _limit(c, iss, "day_docs", ISD_LIMIT_DOCS)
    if n_open >= int(iss["open_drafts"]):
        raise _limit(c, iss, "open_drafts", ISD_LIMIT_OPEN)
    ext = norm["client"]["external_ref"]
    cl = isc_row(c, iss, ext, lock=True)
    if cl is None:
        if isc_gone(c, iss, ext):
            raise IsdErr(410, tr("This client was deleted or anonymised in the office"), "client_gone")
        raise IsdErr(404, tr("Unknown client: set it up first (PUT /issuer/clients/by-ref/{external_ref})"), "client_unknown")
    if cl["deleted_at"]:
        raise IsdErr(409, tr("This client is in the trash of the office"), "client_trashed")
    w = norm["wish"]
    if "payee" in w:
        _payee_ok(c, iss, w["payee"], w["payee_check"])
    did = _make(c, iss, oid, cl, norm, rows)
    r = doc_row(c, oid, did)
    t = _j(r["totals"], {})
    got = {"net": money(dec(t.get("net") or 0)), "tax": money(dec(t.get("tax") or 0)), "gross": money(dec(t.get("gross") or 0))}
    if got["gross"] <= 0:
        c.rollback()
        raise _bad("items", tr("The gross total must be above 0"))
    if any(got[k] != money(expect[k]) for k in got):
        c.rollback()
        raise IsdErr(409, tr("The sums differ from Kalmido's: nothing was made"), "totals_mismatch",
                     totals={k: str(v) for k, v in got.items()}, expected={k: str(money(v)) for k, v in expect.items()})
    flags = []
    over = []
    if got["gross"] > dec(iss["max_gross"]):
        over.append(ISD_OVER_GROSS)
    with system_ctx(c):  # the gross of the issuer's drafts of the last 24 hours (this one included)
        day = [money(dec(_j(x[0], {}).get("gross") or 0)) for x in c.execute(
            "SELECT d.totals FROM office_issuer_refs f JOIN office_docs d ON d.id=f.doc_id WHERE f.issuer_id=? AND f.route=? AND f.created_at>=?",
            (iid, ISD_REF_ROUTE, since)).fetchall()]
    if sum(day, Decimal(0)) + got["gross"] > dec(iss["day_gross"]):
        over.append(ISD_OVER_DAY)
    if over:
        flags.append("over_limit")
    stored = {"wish": w, **{k: v for k, v in told.items() if v is not None}, "expect": norm["expect"], "flags": flags,
              "client_ref": ref, "vat_note": norm["vat_note"]}
    rev = {"doc": isd_doc_fp(c, oid, r), "client": isd_client_fp(c, cl["id"])}
    owner = pb_owner(c, oid)
    with system_ctx(c):  # the issuer's new draft and its ref (the tombstone that outlives it)
        c.execute("UPDATE office_docs SET issuer_id=?, issuer_wish=?, issuer_rev=?, created_by=? WHERE id=? AND org_id=?",
                  (iid, oc_enc(c, oid, "office_docs.issuer_wish", json.dumps(stored, ensure_ascii=False)), json.dumps(rev), owner, did, oid))
        c.execute("INSERT INTO office_issuer_refs(issuer_id, org_id, route, client_ref, body_sha256, created_at, doc_id) VALUES(?,?,?,?,?,?,?)",
                  (iid, oid, ISD_REF_ROUTE, ref, sha, iso(now_utc()), did))
    iss_log(c, oid, iid, "issuer_write", f"doc:{ref}", {"doc": did, "new": True, "key": g.issuer_key["prefix"], "positions": len(rows),
                                                         "gross": str(got["gross"]), **({"flags": flags} if flags else {})}, name=iss["name"], doc_id=did)
    if over and _iss_once(c, iss, "over_limit"):
        iss_tell(c, oid, iss, "issuer_over_limit", " / ".join(tr(x) for x in over))
    bump(c)
    c.commit()
    out = isd_public(c, iss, doc_row(c, oid, did), ref)
    c.commit()
    return jsonify(out), 201


def _payee_ok(c, iss, pid, check):
    """The account pid the admin allowed this issuer, whose IBAN ends with check: 404 payee_unknown, 409 payee_mismatch (an alarm)."""
    with system_ctx(c):  # the issuer's own accounts
        p = c.execute("SELECT * FROM office_issuer_payees WHERE id=? AND issuer_id=? AND org_id=? AND removed_at IS NULL",
                      (int(pid), int(iss["id"]), int(iss["org_id"]))).fetchone()
    if p is None:
        raise IsdErr(404, tr("Unknown bank account: only the accounts an admin allowed this issuer"), "payee_unknown")
    iban = re.sub(r"\s+", "", str((oc_dec_fields(c, iss["org_id"], "office_issuer_payees", p) or {}).get("iban") or "")).upper()
    if iban[-4:] != check:
        def tell(c):
            if _iss_once(c, iss, "payee_mismatch"):
                iss_tell(c, iss["org_id"], iss, "issuer_payee_mismatch", security=True)
            iss_log(c, iss["org_id"], iss["id"], "issuer_refused", f"payee:{int(pid)}", {"status": 409, "code": "payee_mismatch",
                                                                                         "key": g.issuer_key["prefix"]}, name=iss["name"])
        isc_notice(c, "payee", tell)
        raise IsdErr(409, tr("The bank account does not match payee_check: nothing was made"), "payee_mismatch")


def _make(c, iss, oid, cl, norm, rows):
    """The draft through the person's own functions (docs.doc_create, _put_items, recalc): ISS_REUSED. -> its id."""
    s = office_settings(c, oid)
    h = {"kind": "invoice", "client_id": cl["id"], "range_id": iss["range_id"]}
    if norm["service_from"]:
        h.update(service_from=norm["service_from"], service_to=norm["service_to"])
    if norm["order_ref"]:
        h["order_ref"] = norm["order_ref"]
    if norm["vat_note"]:
        h.update(vat_mode="novat", vat_note=norm["vat_note"])
    elif not s.get("small_business"):
        h["vat_mode"] = "vat"
    did = doc_create(c, oid, None, h, False, number=False)
    r = doc_row(c, oid, did)
    items = [{"kind": "service", "title": x["text"], "detail": x["detail"], "qty": str(x["qty"]), "unit": x["unit"], "rate": str(x["rate"]),
              "tax": x["tax"], "discountable": 0, "in_handling": 0, "in_markup": 0} for x in rows]
    _put_items(c, oid, r, items, False, [""] * len(items))
    recalc(c, oid, did)
    return did


@app.get("/api/v1/issuer/docs")  # = ISD_LIST
@v1_view
@_answer
def isd_list():
    """?changed_since=<ISO time>&cursor=<next_cursor>&limit= -> {docs: [...ISD_PUBLIC], next_cursor}: the issuer's documents (its
    drafts, their corrections, a person's numbered documents of its range) changed since then, oldest change first."""
    extra = sorted(k for k in request.args if k not in ("changed_since", "cursor", "limit"))
    if extra:
        raise UnknownFields(extra)
    c, iss = _iss_me()
    oid, iid = int(iss["org_id"]), int(iss["id"])
    since = request.args.get("changed_since") or "1970-01-01T00:00:00+00:00"
    try:
        since = iso_ms(parse_iso(since))
    except (ValueError, TypeError):
        raise _bad("changed_since", tr("changed_since: an ISO time")) from None
    lim = request.args.get("limit") or ""
    lim = max(1, min(int(lim), ISD_PAGE_MAX)) if re.fullmatch(r"\d{1,4}", lim) else ISD_PAGE
    after = None
    if request.args.get("cursor"):
        m = re.fullmatch(r"([0-9T:. +\-Z]{10,40})~(\d{1,18})", request.args["cursor"])
        if not m:
            raise _bad("cursor")
        try:
            parse_iso(m[1])
        except (ValueError, TypeError):
            raise _bad("cursor") from None
        after = (m[1], int(m[2]))
    chg = ("GREATEST(d.updated_at, COALESCE(d.deleted_at, d.updated_at), COALESCE((SELECT MAX(p.created_at) FROM office_payments p "
           "WHERE p.doc_id=d.id), d.updated_at))")
    q = (f"SELECT d.*, {chg} AS changed_at FROM office_docs d WHERE d.org_id=? AND d.kind IN ('invoice', 'credit') AND "
         "(d.issuer_id=? OR (d.issuer_id IS NULL AND d.range_id=? AND d.number<>'' AND d.trial=0)) AND " + chg + " >= ?")
    args = [oid, iid, int(iss["range_id"]), since]
    if after:
        q += f" AND ({chg}, d.id) > (CAST(? AS TIMESTAMPTZ), ?)"
        args += [after[0], after[1]]
    q += " ORDER BY changed_at, d.id LIMIT ?"
    args.append(lim + 1)
    with system_ctx(c):  # the issuer's documents and its range's numbered ones (filtered here, not by row-level security)
        rows = c.execute(q, args).fetchall()
    more = len(rows) > lim
    rows = rows[:lim]
    refs = _refs_of(c, iss, [r["id"] for r in rows if r["issuer_id"] == iid])
    pm = inv_paid_map(c, oid, [r["id"] for r in rows])
    docs = []
    for r in rows:
        d = isd_public(c, iss, r, refs.get(r["id"]), pm=pm)
        d["changed_at"] = _ts(r["changed_at"])
        docs.append(d)
    nxt = f"{docs[-1]['changed_at']}~{docs[-1]['doc_id']}" if more and docs else None
    _log_read(c, iss, "docs")
    c.commit()
    return jsonify(docs=docs, next_cursor=nxt)


@app.get("/api/v1/issuer/docs/<int:did>")  # = ISD_ONE
@v1_view
@_answer
def isd_get(did):
    """One of the issuer's documents (ISD_PUBLIC); another's, a person's or an unknown id 404 (counts towards the self-pause)."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    r = _doc(c, iss, did)
    if r is None:
        return _no_doc(c, iss)
    ref = _refs_of(c, iss, [r["id"]]).get(r["id"])
    out = isd_public(c, iss, r, ref)
    _log_read(c, iss, f"doc:{int(did)}")
    c.commit()
    return jsonify(out)


@app.get("/api/v1/issuer/docs/by-ref/<path:ref>")  # = ISD_REF
@v1_view
@_answer
def isd_get_ref(ref):
    """The issuer's draft of client_ref ref: 404 unknown (no count towards a pause: "was it made?" is ordinary), 410 withdrawn."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    if not isinstance(ref, str) or not ISC_REF_RE.fullmatch(ref):
        raise _bad("client_ref", tr("client_ref: 1 to 64 letters, digits or . _ : - (no slash)"))
    hit = _ref_row(c, iss, ref)
    if hit is None:
        raise IsdErr(404, tr("Not found"), "not_found")
    r = _doc(c, iss, hit["doc_id"]) if hit["doc_id"] else None
    if r is None:
        raise IsdErr(410, tr("The draft of this client_ref was withdrawn or deleted in the office"), "withdrawn")
    out = isd_public(c, iss, r, ref)
    _log_read(c, iss, f"doc:{ref}")
    c.commit()
    return jsonify(out)


@app.get("/api/v1/issuer/docs/<int:did>/pdf")  # = ISD_PDF
@v1_view
@_answer
def isd_pdf(did):
    """The PDF preview of the issuer's draft (watermark DRAFT), only while document, positions and client are as the key
    delivered them (409 edited_by_human), ISD_PDF_RATE a minute."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    r = _doc(c, iss, did, live=True)
    if r is None:
        return _no_doc(c, iss)
    if r["status"] != "draft":
        raise IsdErr(409, tr("Only the preview of a draft"), "not_draft")
    hit = rate_hit(f"isspdf:{int(iss['id'])}", ISD_PDF_RATE, 60)
    if hit is None:
        raise IsdErr(503, tr("Please try again in a moment"), "unavailable", {"Retry-After": "10"})
    if hit:
        raise IsdErr(429, tr("Too many requests, please slow down"), "rate_limited", {"Retry-After": "60"})
    oid = int(iss["org_id"])
    r = doc_row(c, oid, did)
    rev = _rev(r["issuer_rev"])
    if not rev or rev.get("doc") != isd_doc_fp(c, oid, r) or rev.get("client") != isd_client_fp(c, r["client_id"]):
        raise IsdErr(409, tr("A person changed this draft or its client in the office: no preview"), "edited_by_human")
    pdf = epdf_out(c, oid, r, _render(c, oid, r)[0])  # ISS_REUSED: the person's preview of a draft (watermark: pdfweb.epdf_mark)
    _log_read(c, iss, f"pdf:{int(did)}")
    c.commit()
    return _file_response(pdf, epdf_name(r) + ".pdf", "application/pdf")


@app.get("/api/v1/issuer/docs/<int:did>/file")  # = ISD_FILE
@v1_view
@_answer
def isd_file(did):
    """(#6818) ?kind=pdf|xml -> the archived file of the issuer's finalised document, byte for byte, its SHA-256 in
    X-Content-SHA256. A draft or no archived file of that kind: 409 not_final (never rendered anew); ISD_FILE_RATE a minute;
    every delivery one line of the office log."""
    c, iss = _iss_me()  # first: a key of another kind hears 403, never what the route asks for
    extra = sorted(k for k in request.args if k != "kind")
    if extra:
        raise UnknownFields(extra)
    kind = request.args.get("kind") or ""
    if kind not in ISD_FILE_MIME:
        raise _bad("kind", tr("kind: pdf or xml"))
    oid, iid = int(iss["org_id"]), int(iss["id"])
    r = _doc(c, iss, did, live=True)
    if r is None:
        return _no_doc(c, iss)
    if not ofx_locked(r):
        raise IsdErr(409, tr("The document is not finalised yet: its file exists from finalising on"), "not_final")
    hit = rate_hit(f"issfile:{iid}", ISD_FILE_RATE, 60)
    if hit is None:
        raise IsdErr(503, tr("Please try again in a moment"), "unavailable", {"Retry-After": "10"})
    if hit:
        raise IsdErr(429, tr("Too many requests, please slow down"), "rate_limited", {"Retry-After": "60"})
    try:
        data = epdf_stored(c, oid, r, kind)  # ISS_REUSED: the archive (sealed, its SHA-256 checked), never rendered here
    except Denied as e:  # the stored file has gone or does not match its checksum (logged by epdf_stored)
        raise IsdErr(409, str(e) or tr("There is no archived file of this kind for this document"), "not_final") from None
    if data is None:
        raise IsdErr(409, tr("There is no archived file of this kind for this document"), "not_final")
    sha = hashlib.sha256(data).hexdigest()
    iss_log(c, oid, iid, "issuer_read", f"file:{kind}:{int(did)}", {"key": g.issuer_key["prefix"], "ip": fx2_mask_ip(client_ip()),
                                                                      "sha256": sha, "bytes": len(data)}, name=iss["name"], doc_id=int(did))
    c.commit()
    resp = _file_response(data, epdf_name(r) + "." + kind, ISD_FILE_MIME[kind])
    resp.headers["X-Content-SHA256"] = sha
    return resp


@app.post("/api/v1/issuer/docs/<int:did>/withdraw")  # = ISD_WITHDRAW
@v1_view
@_answer
def isd_withdraw(did):
    """The issuer's draft into the office's trash (docs.odoc_trash, a person restores it); day_withdraw within 24 hours, else
    429. Withdrawn already: 200 as it is. A finalised document 409 not_draft."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    oid, iid = int(iss["org_id"]), int(iss["id"])
    write_lock(c, f"issuer-{iid}")
    r = _doc(c, iss, did)
    if r is None:
        return _no_doc(c, iss)
    ref = _refs_of(c, iss, [r["id"]]).get(r["id"])
    if r["deleted_at"]:
        out = isd_public(c, iss, r, ref)
        c.commit()
        return jsonify(out)
    if r["status"] != "draft" or r["number"]:
        raise IsdErr(409, tr("Only a draft can be withdrawn; a person corrects a finalised invoice"), "not_draft")
    if not ref:  # review F1: a correction a person made of its invoice carries issuer_id too, but is the person's
        raise IsdErr(409, tr("Only a draft this key made can be withdrawn"), "not_own_draft")
    with system_ctx(c):  # the issuer's own withdrawals of the last 24 hours
        n = c.execute("SELECT COUNT(*) FROM office_doc_log WHERE issuer_id=? AND action='issuer_write' AND target ILIKE 'withdraw:%' AND at>=?",
                      (iid, iso(now_utc() - timedelta(days=1)))).fetchone()[0]
    if n >= int(iss["day_withdraw"]):
        raise _limit(c, iss, "day_withdraw", ISD_LIMIT_WITHDRAW)
    write_lock(c, f"office_doc_{int(did)}")
    odoc_trash(c, oid, None, doc_row(c, oid, did), checked=True)  # ISS_REUSED: the office's trash, restorable by a person
    iss_log(c, oid, iid, "issuer_write", f"withdraw:{int(did)}", {"doc": int(did), "key": g.issuer_key["prefix"], "client_ref": ref},
            name=iss["name"], doc_id=int(did))
    bump(c)
    c.commit()
    out = isd_public(c, iss, _doc(c, iss, did), ref)
    c.commit()
    return jsonify(out)


# ---------------------------------------------------------------- the daily check (issuers.iss_tick)
def isd_wait_check(c, iss):
    """Drafts of issuer iss that wait for a person longer than review_wait_h: one notice a day. -> 1 when told."""
    hours = int(iss["review_wait_h"] or 0)
    if hours <= 0:
        return 0
    with system_ctx(c):  # the issuer's own drafts
        n = c.execute(f"SELECT COUNT(*) FROM office_docs WHERE issuer_id=? AND org_id=? AND status='draft' AND {live_sql()} AND created_at<?",
                      (int(iss["id"]), int(iss["org_id"]), iso(now_utc() - timedelta(hours=hours)))).fetchone()[0]
    if n and _iss_once(c, iss, "waiting"):
        iss_tell(c, iss["org_id"], iss, "issuer_waiting", str(n))
        return 1
    return 0


# ---------------------------------------------------------------- OpenAPI (api/openapi.py)
def isd_spec(paths, op, ok, errs):
    money_ = {"type": "string", "pattern": r"^\d+(\.\d{1,2})?$"}
    totals = {"type": "object", "properties": {"net": money_, "tax": money_, "gross": money_, "currency": {"type": "string"}}}
    doc = {"type": "object", "properties": {
        "doc_id": {"type": "integer"}, "client_ref": {"type": "string", "nullable": True},
        "origin": {"type": "string", "enum": ["issuer", "manual"], "description": "manual: a correction or a document a person made in the issuer's range"},
        "kind": {"type": "string", "enum": ["invoice", "credit"]},
        "status": {"type": "string", "enum": ["draft", "issued", "sent", "partial", "overdue", "paid", "cancelled", "withdrawn"]},
        "range": {"type": "string"}, "number": {"type": "string", "nullable": True},
        "date": {"type": "string", "format": "date", "nullable": True, "description": "Set by Kalmido when a person finalises"},
        "service_from": {"type": "string", "format": "date", "nullable": True}, "service_to": {"type": "string", "format": "date", "nullable": True},
        "due_date": {"type": "string", "format": "date", "nullable": True}, "totals": totals,
        "corrects_doc_id": {"type": "integer", "nullable": True},
        "payments": {"type": "array", "items": {"type": "object", "properties": {"date": {"type": "string"}, "amount": money_, "method": {"type": "string"}}}},
        "missing": {"type": "array", "items": {"type": "string"}, "description": "Drafts: what finalising still needs"},
        "flags": {"type": "array", "items": {"type": "string", "enum": ["over_limit", "client_new", "client_changed", "vat_territory"]}},
        "updated_at": {"type": "string", "format": "date-time"}}}
    item = {"type": "object", "additionalProperties": False, "required": ["text", "rate"], "properties": {
        "text": {"type": "string", "maxLength": ISD_TITLE_MAX}, "detail": {"type": "string", "maxLength": ISD_DETAIL_MAX},
        "qty": {"type": "string", "description": "> 0, up to 4 places (default 1)"}, "unit": {"type": "string", "enum": list(ISD_UNITS)},
        "rate": {"type": "string", "description": "The net unit price, >= 0, up to 4 places"}, "tax": {"type": "string", "enum": list(TAX_KEYS)}}}
    wish = {"type": "object", "additionalProperties": False, "properties": {
        "send": {"type": "boolean"},
        "paid": {"type": "object", "properties": {"amount": money_, "date": {"type": "string", "format": "date"},
                                                  "method": {"type": "string", "enum": list(ISD_METHODS)}, "provider": {"type": "string"},
                                                  "online_ref": {"type": "string"}}},
        "payee": {"type": "integer", "description": "The id of a bank account an admin allowed this issuer"},
        "payee_check": {"type": "string", "description": "The last four characters of that account's IBAN (else 409 payee_mismatch)"},
        "reference": {"type": "string", "pattern": "^[A-Z0-9-]{1,35}$"},
        "due_days": {"type": "integer", "minimum": 0, "maximum": 365}, "due_date": {"type": "string", "format": "date"}}}
    body = {"type": "object", "additionalProperties": False, "required": ["client_ref", "client", "items", "expect"], "properties": {
        "client_ref": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,64}$", "description": "Your id of this purchase, for good"},
        "client": {"type": "object", "properties": {"external_ref": {"type": "string"}}},
        "items": {"type": "array", "maxItems": ISD_ITEMS_MAX, "items": item},
        "expect": totals, "service_from": {"type": "string", "format": "date"}, "service_to": {"type": "string", "format": "date"},
        "order_ref": {"type": "string", "maxLength": ISD_ORDER_REF_MAX},
        "vat_note": {"type": "string", "enum": list(INV_VAT_NOTES), "nullable": True, "description": "A proposal; Kalmido's checks decide"},
        "vat_check": {"type": "object", "description": "Your VAT ID check (stored, never printed, no proof)"},
        "business_check": {"type": "object", "description": "Your check that the buyer is a business (stored, never printed, no proof)"},
        "wish": wish}}
    did = {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
    ref = {"name": "ref", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,64}$"}}
    only = "Only with an invoice issuer key. "
    paths["/issuer/invoices"] = {"post": op(
        "An invoice draft of an invoice issuer (2.1427.0)", "Office", ok(doc) | ok(doc, "Created", "201") | errs("400", "403", "404", "409", "410", "413", "429"),
        [], body=body, scope="office",
        desc=only + "Kalmido computes (each line quantity x unit price rounded to the cent, the tax per rate on the sum); expect must match "
             "(409 totals_mismatch with Kalmido's totals, nothing made). The same client_ref with the same content = 200, with another "
             "= 409 ref_conflict, withdrawn = 410 withdrawn. 404 client_unknown / payee_unknown, 409 client_trashed / payee_mismatch, "
             "410 client_gone, 429 limit_reached (Retry-After). No date, number, range, currency, IBAN or link: a person checks, "
             "finalises and sends every draft. Texts with an IBAN, a web or an e-mail address: 400 invalid_field.")}
    paths["/issuer/docs"] = {"get": op(
        "The invoice issuer's documents changed since a time (2.1427.0)", "Office",
        ok({"type": "object", "properties": {"docs": {"type": "array", "items": doc}, "next_cursor": {"type": "string", "nullable": True}}}) | errs("400", "403"),
        [{"name": "changed_since", "in": "query", "schema": {"type": "string", "format": "date-time"}},
         {"name": "cursor", "in": "query", "schema": {"type": "string"}}, {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": ISD_PAGE_MAX}}],
        scope="office", desc=only + "The source of truth of the reconciliation: its drafts, their corrections and the documents a person "
                                    "numbered in its range (origin manual), oldest change first; next_cursor = the next page.")}
    paths["/issuer/docs/{id}"] = {"get": op("One document of the invoice issuer (2.1427.0)", "Office", ok(doc) | errs("403", "404"), [did],
                                             scope="office", desc=only + "404 for every id that is not its own (counts towards a pause).")}
    paths["/issuer/docs/by-ref/{ref}"] = {"get": op("The invoice issuer's draft of a client_ref (2.1427.0)", "Office", ok(doc) | errs("400", "403", "404", "410"),
                                                    [ref], scope="office", desc=only + "410 withdrawn: withdrawn or deleted in the office.")}
    paths["/issuer/docs/{id}/pdf"] = {"get": op(
        "The PDF preview of an invoice issuer's draft (2.1427.0)", "Office", {"200": {"description": "PDF", "content": {"application/pdf": {}}}} | errs("403", "404", "409", "429"),
        [did], scope="office", desc=only + "Watermark DRAFT; 409 edited_by_human when a person changed the draft or its client; 10 a minute.")}
    paths["/issuer/docs/{id}/file"] = {"get": op(
        "The archived file of an invoice issuer's finalised document (2.1436.0)", "Office",
        {"200": {"description": "The archived file, byte for byte; header X-Content-SHA256 = its SHA-256 (hex)",
                 "content": {"application/pdf": {}, "application/xml": {}}}} | errs("400", "403", "404", "409", "429"),
        [did, {"name": "kind", "in": "query", "required": True, "schema": {"type": "string", "enum": list(ISD_FILE_MIME)}}], scope="office",
        desc=only + "Its own documents only (also a person's correction of its invoice). kind=pdf the PDF, kind=xml the e-invoice XML "
                    "(ZUGFeRD: the XML inside the PDF, XRechnung: the invoice itself). 409 not_final: a draft, or no archived file of "
                    "that kind (never rendered anew). 10 a minute (429 rate_limited); every download is in the office log.")}
    paths["/issuer/docs/{id}/withdraw"] = {"post": op(
        "Withdraw an invoice issuer's draft (2.1427.0)", "Office", ok(doc) | errs("403", "404", "409", "429"), [did], scope="office",
        desc=only + "Into the office's trash (a person can restore it); its client_ref answers 410 withdrawn from then on. 409 not_draft, "
                    "429 limit_reached (day_withdraw).")}
