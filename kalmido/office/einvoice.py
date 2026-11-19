"""2.38.0 (#1021 P5): the e-invoice XML of a finalised invoice / credit note -- UN/CEFACT Cross Industry Invoice (CII D16B)
in the EN 16931 profile (ZUGFeRD 2.x / Factur-X "EN 16931") or the XRechnung 3.0 customisation (CIUS of the German public
sector), built from the print model of office.docs (odoc_render), which for a finalised document is its snapshot only.

ein_values(model)          -> dict: the EN 16931 values of a print model, once for CII and UBL (2.1407 #7155)
ein_build(model, fmt)      -> bytes: the XML from a print model (pure, no database; tests use it with a fixture)
ein_xml(c, oid, did, fmt)  -> bytes: the XML of document did of organisation oid (locked invoice / credit note)
ein_check(xml_bytes)       -> [findings]: the module's own plausibility check without a validator (mandatory BTs, sums)
ein_check_block(xml_bytes) -> [[key, *args]]: the findings that stop finalising (2.1308.0 #6476, pdfweb.epdf_store)

Amounts are Decimal strings all the way (never float): the totals of the print model carry two-place strings, the line
totals are read as text. Tax categories: S (standard / reduced rate; a line at 0 % of a taxed document Z or E, _line_cat), and
by the vat_note of a document without VAT AE (reverse charge), O (not taxable domestically; G without a register or tax number),
K (intra-Community goods), G (export of goods), E (small business, unknown note), see VAT_CATEGORY and _doc_cat. A foreign currency (USD) gets BT-5 USD, BT-6 EUR and BT-111 (the
tax in EUR) from totals.tax_eur. 2.189.0 (#2475): "EUR" is the office's home currency (totals.home, missing = EUR). A credit note is type 381 with positive amounts and the invoice it cancels in BT-25.
The KoSIT validator (Schematron EN 16931 + XRechnung) and veraPDF run in CI on the files tests/office_einvoice_test.py
writes (tools/einvoice_validate.sh)."""
# Adding a format (#1961): see CONTRIBUTING.md, "Contributing national e-invoice formats".
# A new format is an entry in EIN_FORMATS and EIN_PROFILE, its own writer of ein_values (2.1407 #7155: no rule of its own), the key in pdfweb.epdf_format,
# example invoices in tests/office_einvoice_test.py and an official validator run in CI (tools/einvoice_validate.sh).
# It needs a source of the specification (link + version) and a maintainer; formats that submit invoices to an authority
# are agreed in an issue first. No plugins or scripts run on the server: formats ship with Kalmido.
import json
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree as ET

try:
    from ..core.i18n import LANGS, N_, tr
    from ..core.errors import BadInput
except ImportError:  # loaded as a single file (tests/office_einvoice_test.py, no package)
    def _ein_langs():  # 2.185.0 C (#2520): the same translation files (the document's words in its language)
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static", "i18n")
        out = {"en": {}}
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    out[fn[:-5]] = json.load(fh) if fn.endswith(".json") else {}
            except (OSError, ValueError):
                pass
        try:  # 2.1188.0 (#6194): + the new texts of the packages (static/i18n/neu/<KID>.json, core/i18nfrag.py by its path)
            import importlib.util
            spec = importlib.util.spec_from_file_location("i18nfrag", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "i18nfrag.py"))
            frag = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(frag)
            frags = frag.read_fragments(d)
            out = {code: frag.merge_lang(v, code, frags) for code, v in out.items()}
        except (OSError, ImportError, AttributeError):
            pass
        return out
    LANGS = _ein_langs()

    def N_(s):
        return s

    def tr(key, *a, lg=None):
        v = LANGS.get(lg or "en", {}).get(key)
        s = v if isinstance(v, str) else key[:key.find("|")] if key.find("|") > 0 else key
        return s.format(*a) if a else s

    class BadInput(Exception):
        pass

EIN_FORMATS = ("zugferd", "xrechnung")
EIN_PROFILE = {"zugferd": "urn:cen.eu:en16931:2017",
               "xrechnung": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"}
EIN_PROCESS = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"  # BT-23
NS = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
      "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
      "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
      "qdt": "urn:un:unece:uncefact:data:standard:QualifiedDataType:100"}
Q2 = Decimal("0.01")
UNIT_CODES = {"day": "DAY", "hour": "HUR", "minute": "MIN", "piece": "C62", "flat": "C62", "": "C62"}
COUNTRY_WORDS = {"deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT", "schweiz": "CH", "switzerland": "CH",
                 "frankreich": "FR", "france": "FR", "niederlande": "NL", "netherlands": "NL", "italien": "IT", "italy": "IT",
                 "spanien": "ES", "spain": "ES", "belgien": "BE", "belgium": "BE", "luxemburg": "LU", "luxembourg": "LU",
                 "polen": "PL", "poland": "PL", "dänemark": "DK", "denmark": "DK", "vereinigtes königreich": "GB", "united kingdom": "GB"}
# tax category by the document's VAT note (vat_mode novat); S for taxed documents
# 2.296.0 B (#3173): "abroad" (service not taxable domestically) = O, not G (export of goods); see _doc_cat for the fallback
# 2.355.0 C (#2844): + "eu_goods" (intra-Community supply of goods) = K, "export" (export of goods to a third country) = G
VAT_CATEGORY = {"reverse": ("AE", "VATEX-EU-AE"), "abroad": ("O", "VATEX-EU-O"), "small": ("E", ""),
                "eu_goods": ("K", "VATEX-EU-IC"), "export": ("G", "VATEX-EU-G")}
# 2.185.0 C (#2520): English keys through tr() in the document's language (was a de / en table; the words stay the same)
EXEMPT_TEXT = {"reverse": N_("Reverse charge: VAT liability of the recipient.|einvoice"),
               "abroad": N_("Not taxable domestically (export / service outside the EU).|einvoice"),
               "small": N_("No VAT charged under section 19 of the German VAT Act (small business).|einvoice"),
               "eu_goods": N_("Tax-exempt intra-Community supply of goods.|einvoice"),  # 2.355.0 C (#2844)
               "export": N_("Tax-exempt export of goods.|einvoice"),
               "exempt": N_("Tax exempt.|einvoice")}  # 2.296.0 B (#3169): a 0 % line of a taxed invoice without its own reason
EIN_WORDS = {"project": N_("Project: {0}|einvoice"), "transfer": N_("Credit transfer|einvoice"),
             "refund": N_("The amount will be refunded or offset.|einvoice"), "now": N_("Payable on receipt.|einvoice"),
             "rights": N_("Transfer of rights|pdf")}  # 2.1359.0 (#6482): the rights block as a note (BT-22), the word of the PDF
EIN_NOTE_MAX = 4000  # 2.1359.0 (#6482): characters of one note (BT-22 / BT-127); the PDF limits its texts to the same order


def _text_notes(m, lang):
    """2.1359.0 (#6482 P5-5): the texts of the print model that only stood in the PDF, for the XML (the XML is the invoice).
    Returns ({id(line): BT-127 text}, [BT-22 texts]): heading and text lines between positions go with the NEXT position as
    its line note (BT-127, joined); those after the last position, the intro, the rights block and the closing are
    document notes (BT-22), in the order of the PDF (intro, trailing lines, rights, closing)."""
    by_line, pending = {}, []
    for ln in m.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        k = ln.get("kind") or "item"
        if k in ("heading", "text"):
            t = " ".join(str(ln.get("title") or "").split()) if k == "heading" else str(ln.get("text") or "").strip()
            if t:
                pending.append(t)
        elif k in ("item", "discount", "producing", "surcharge", "raw") and not (k == "raw" and ln.get("optional")):  # as _ein_lines
            if pending:
                by_line[id(ln)] = "\n".join(pending)[:EIN_NOTE_MAX]
                pending = []
    doc = [str(m.get("intro") or "").strip()] + pending
    rg = m.get("rights") if isinstance(m.get("rights"), dict) else {}
    rows = [f"{str(r[0]).strip()}: {str(r[1]).strip()}" if str(r[0]).strip() else str(r[1]).strip()
            for r in (rg.get("rows") or []) if isinstance(r, (list, tuple)) and len(r) >= 2 and str(r[1]).strip()]
    if rows or str(rg.get("note") or "").strip():
        doc.append("\n".join([str(rg.get("title") or "").strip() or tr(EIN_WORDS["rights"], lg=lang)] + rows
                             + ([str(rg["note"]).strip()] if str(rg.get("note") or "").strip() else [])))
    doc.append(str(m.get("closing") or "").strip())
    return by_line, [t[:EIN_NOTE_MAX] for t in doc if t]


def ein_lang(v):
    """2.185.0 C (#2520): the language of the texts in the XML (notes, payment terms; codes stay as they are): en / de as
    before, any other app language, else German."""
    s = str(v or "de").strip().lower()
    return "en" if s.startswith("en") else s if s in LANGS else "de"


def _exempt(m, lang):
    return tr(EXEMPT_TEXT.get(m.get("vat_note_key") or "small", EXEMPT_TEXT["small"]), lg=lang)


def _doc_cat(m):
    """(novat, category, VATEX code) of the document by its vat_note; S for taxed documents. 2.296.0 B (#3173): O ("not
    subject to VAT") carries no VAT id of seller or buyer (BR-O-02), so the seller needs its register number (BT-30) for
    BR-CO-26; without one the document stays G as before (BR-G-02 wants the seller's VAT id, which it keeps). 2.357.0 (#3218):
    the seller's tax number as seller identifier (BT-29, see _seller_id) satisfies BR-CO-26 as well, so O without a register."""
    novat = m.get("vat_mode") == "novat"  # 2.354.0 A (#2833): from vat_mode alone (was "or vat_note_key": AE on a taxed invoice, BR-CO-15)
    if not novat:
        return False, "S", ""
    cat, excode = VAT_CATEGORY.get(m.get("vat_note_key") or "", ("E", ""))
    sf = m.get("sender_fields") or {}
    if cat == "O" and not str(sf.get("register_no") or "").strip() and not str(sf.get("tax_number") or "").strip():
        cat, excode = "G", "VATEX-EU-G"
    return True, cat, excode


def _seller_id(m, cat):
    """2.357.0 (#3218): the seller identifier (BT-29) of a document not subject to VAT (O) without a register number: the
    seller's tax number (BR-CO-26 without a VAT id, BR-O-02); empty otherwise (the output stays as before)."""
    sf = m.get("sender_fields") or {}
    if cat != "O" or str(sf.get("register_no") or "").strip():
        return ""
    return str(sf.get("tax_number") or "").strip()


def _line_cat(cat, pct, key=""):
    """2.296.0 B (#3169): the category of one line: a taxed document's line at 0 % is exempt (E; BR-S-05: S needs a rate
    above zero), any other line keeps the document's category. 2.357.0 (#3217): a line of the standard / reduced rate set
    to 0 % by the office (a true zero rate, e.g. UK) is Z (zero rated, no exemption reason); the key exempt stays E."""
    if cat == "S" and pct == 0:
        return "Z" if key in ("standard", "reduced") else "E"
    return cat


def _reason(m, lang, cat, lcat):
    """2.296.0 B (#3169): the exemption reason (BT-120) of a breakdown: the vat_note's text for the document's category,
    the invoice's own reason (exempt_reason, mandatory before finalising) for exempt lines of a taxed invoice."""
    if lcat == cat:
        return _exempt(m, lang)
    return str(m.get("exempt_reason") or "").strip() or tr(EXEMPT_TEXT["exempt"], lg=lang)


def _d(v, default="0"):
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _m(v):
    """Money text with two places (half up)."""
    return format(_d(v).quantize(Q2, rounding=ROUND_HALF_UP), "f")


def _qty(v):
    q = _d(v, "1")
    s = format(q.normalize(), "f")
    return s if "." in s or "E" not in s else format(q, "f")


def _pct(v):
    p = _d(v).normalize()
    return format(p, "f") if p == p.to_integral() else _m(p)


def _date8(s):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(s or "")[:10])
    return "".join(m.groups()) if m else ""


def _country(v, fallback="DE"):
    """2.40.0 (#1372): a code from the ISO list (UK -> GB, EL -> GR); an unknown code is stopped before finalising
    (invoices.inv_missing), a free word is looked up, empty = the fallback."""
    try:
        from .countries import fk_country_code
    except ImportError:  # loaded on its own (tests/office_einvoice_test.py): only the two corrections
        def fk_country_code(x):
            return {"UK": "GB", "EL": "GR"}.get(x.upper(), x.upper())
    s = str(v or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", s):
        return fk_country_code(s) or fallback  # 2.40.0 (review): an unknown pair of letters is no country
    return COUNTRY_WORDS.get(s.lower(), fallback)


def _e(parent, tag, text=None, **attrs):
    ns, _, name = tag.partition(":")
    el = ET.SubElement(parent, f"{{{NS[ns]}}}{name}", {k: v for k, v in attrs.items() if v not in (None, "")})
    if text is not None:
        el.text = str(text)
    return el


def _date_el(parent, tag, iso, prefix="udt"):
    d8 = _date8(iso)
    if d8:
        _e(_e(parent, tag), f"{prefix}:DateTimeString", d8, format="102")


_ZIP_RE = re.compile(r"^(?:([A-Z]{1,2})\s*-\s*)?(\d{4,5})\s+(\S.*)$")


def fd_split_address(lines):
    """2.40.0 (#1368): free address lines -> street / line2 / line3 / zip / city. The LAST line with a postcode pattern
    ("12345 Town", "1010 Wien", "CH-8000 Zürich") is zip + city, the line before it the street (LineOne), the lines before
    that LineTwo / LineThree. No postcode line found (e.g. UK): the last line is the city, the one before the street."""
    lines = [str(x).strip() for x in (lines or []) if str(x).strip()]
    out = {}
    if not lines:
        return out
    idx = next((i for i in range(len(lines) - 1, -1, -1) if _ZIP_RE.match(lines[i])), None)
    if idx is None:
        idx, zip_, city = len(lines) - 1, "", lines[-1]
    else:
        mm = _ZIP_RE.match(lines[idx])
        zip_, city = mm.group(2), mm.group(3).strip()
        pre = {"D": "DE", "A": "AT", "F": "FR", "B": "BE", "I": "IT", "L": "LU"}.get(mm.group(1) or "", mm.group(1) or "")
        tail = lines[idx + 1:]  # a country line after "zip city" ("Deutschland", "AT")
        cc = _country(tail[-1], "") if tail else ""
        if cc or pre:
            out["country"] = cc or pre
    before = lines[:idx]
    out["zip"], out["city"] = zip_, city
    if before:
        out["street"] = before[-1]
        extra = before[:-1]
        if extra:
            out["line2"] = extra[0]
        if len(extra) > 1:
            out["line3"] = ", ".join(extra[1:])
    return out


def _address(a, f, home):
    """A postal address in the schema order. 2.424.0 C (#3524): empty parts are left out (ZUGFeRD 2.4+ deprecates empty
    elements); the country (BT-40 / BT-55 / BT-80) is always there."""
    for k, tg in (("zip", "ram:PostcodeCode"), ("street", "ram:LineOne"), ("line2", "ram:LineTwo"), ("line3", "ram:LineThree"), ("city", "ram:CityName")):
        v = str(f.get(k) or "").strip()  # 2.40.0 (#1368): + extra free address lines
        if v:
            _e(a, tg, v)
    _e(a, "ram:CountryID", _country(f.get("country"), home))


def _party(parent, tag, name, fields, home, contact=None, email=None, legal_id=None, party_id=""):
    """A trade party (seller / buyer) in the schema order: ID (BT-29, 2.357.0 #3218), Name, legal organisation, contact
    (BG-6 of the seller / 2.40.0 #1380 BG-9 of the buyer: {name, phone, email} from ein_values), address, URI, tax ids."""
    f = fields or {}
    p = _e(parent, tag)
    if party_id:
        _e(p, "ram:ID", party_id)
    _e(p, "ram:Name", name or "")
    if legal_id:
        _e(_e(p, "ram:SpecifiedLegalOrganization"), "ram:ID", legal_id)
    if contact:
        ct = _e(p, "ram:DefinedTradeContact")
        _e(ct, "ram:PersonName", contact.get("name") or "")
        if contact.get("phone"):
            _e(_e(ct, "ram:TelephoneUniversalCommunication"), "ram:CompleteNumber", contact["phone"])
        if contact.get("email"):
            _e(_e(ct, "ram:EmailURIUniversalCommunication"), "ram:URIID", contact["email"])
    _address(_e(p, "ram:PostalTradeAddress"), f, home)
    if email:
        _e(_e(p, "ram:URIUniversalCommunication"), "ram:URIID", email, schemeID="EM")
    if f.get("tax_number") and tag.startswith("ram:Seller"):
        _e(_e(p, "ram:SpecifiedTaxRegistration"), "ram:ID", f["tax_number"], schemeID="FC")
    if f.get("vat_id"):
        _e(_e(p, "ram:SpecifiedTaxRegistration"), "ram:ID", f["vat_id"], schemeID="VA")
    return p


def _abs_full(m):
    """2.408.0 (#3520, BMF letter of 15.10.2026 no. 3): (totals, prepaid, note) of a print model. A final invoice whose
    deduction lines abschlag.abs_prepaid_view took out of the lines: the totals of the whole service (tax per rate, gross,
    tax in the home currency), the progress invoices' gross as prepaid (BT-113; 2.502.0, #4079: no payments of today) and their details as
    one note (BT-22). Else the totals as they are, 0, ''."""
    tot = m.get("totals") or {}
    full = m.get("abs_full")
    if m.get("kind") != "invoice" or not isinstance(full, dict) or not m.get("abs_prepaid"):
        return tot, Decimal("0"), ""
    tot = {**tot, "tax_lines": full.get("tax_lines") or [], "gross": full.get("gross"), **({"tax_eur": full["tax_eur"]} if full.get("tax_eur") else {})}
    return tot, _d(full.get("prepaid")).quantize(Q2, rounding=ROUND_HALF_UP), str(full.get("note") or "")


def _line_allowance(ln):
    """(#5815): (amount, basis, percent) of a position's own discount (calc.inv_calc: allowance = list_net - net), or
    None. Only for a positive line whose price x quantity gives the list amount, so BT-131 = BT-129 x BT-146 - BT-136 holds."""
    try:
        a, b, p = _d(ln.get("allowance")), _d(ln.get("list_net")), _d(ln.get("discount_pct"))
    except (ArithmeticError, ValueError, TypeError):  # an unreadable value: no allowance, the line is fitted as before
        return None
    if a <= 0 or b <= 0 or p <= 0:
        return None
    return a.quantize(Q2, rounding=ROUND_HALF_UP), b.quantize(Q2, rounding=ROUND_HALF_UP), p


def _ein_lines(m, cat):
    """[(line dict, n, net, pct, qty, price, charge)] of the positions; price and quantity agree with the net amount
    (PEPPOL-EN16931-R120: net = quantity x price + line charges - line allowances, rounded to cents).
    (#4082): a price that does not fit with two places gets four, then six places (a foreign currency with
    sub-cent prices: 1,000 minutes x 0.125 EUR x rate 1.085 = 0.135625 USD). When even six places do not fit, the
    quantity stays as on the PDF, the price is net / qty with four places and the rounding gap goes as a line charge
    (charge > 0) or line allowance (charge < 0) -- before 2.523.0 such a line fell back to quantity 1."""
    out = []
    n = 0
    for ln in m.get("lines") or []:
        if not isinstance(ln, dict) or ln.get("kind") not in ("item", "discount", "producing", "surcharge", "raw"):
            continue
        if ln.get("kind") == "raw" and ln.get("optional"):
            continue
        n += 1
        net = _d(ln.get("net") if ln.get("net") not in (None, "") else ln.get("total")).quantize(Q2, rounding=ROUND_HALF_UP)
        pct = _d(ln.get("tax_pct")) if cat == "S" else Decimal("0")
        qty = _d(ln.get("qty"), "1") if ln.get("qty") not in (None, "") else Decimal("1")
        rate = _d(ln.get("rate")) if ln.get("rate") not in (None, "") else net
        if qty == 0:
            qty, rate = Decimal("1"), net
        if rate < 0:
            rate, qty = -rate, -qty
        elif net < 0 and qty > 0:
            qty = -qty
        charge = Decimal("0")
        lac = _line_allowance(ln)
        if (lac and qty > 0 and rate == rate.quantize(Decimal("0.000001")) and (qty * rate).quantize(Q2, rounding=ROUND_HALF_UP) == lac[1]
                and lac[1] - lac[0] == net):  # a price of more than six places would be cut when written (_uprice): fitted below
            out.append((ln, n, net, pct, qty, rate, -lac[0]))  # (#5815): the position's own discount, a line allowance
            continue
        # a given rate with more than six places would be cut when written (_uprice), so it is fitted like an odd one
        if rate != rate.quantize(Decimal("0.000001")) or (qty * rate).quantize(Q2, rounding=ROUND_HALF_UP) != net:
            for places in (Decimal("0.0001"), Decimal("0.000001")):
                p = (net / qty).quantize(places, rounding=ROUND_HALF_UP)
                if p >= 0 and (qty * p).quantize(Q2, rounding=ROUND_HALF_UP) == net:
                    rate = p
                    break
            else:
                rate = (net / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                if rate < 0:  # net and qty of opposite sign cannot come here (flipped above); stay safe: qty 1 as before
                    qty, rate = (Decimal("-1"), -net) if net < 0 else (Decimal("1"), net)
                else:
                    charge = net - (qty * rate).quantize(Q2, rounding=ROUND_HALF_UP)
        out.append((ln, n, net, pct, qty, rate, charge))
    return out


def _uprice(rate):
    """BT-146 as written: two places when it has no more, else up to six (2.523.0 #4082), trailing zeros dropped down to four."""
    if rate == rate.quantize(Q2):
        return _m(rate)
    if rate == rate.quantize(Decimal("0.0001")):
        return format(rate.quantize(Decimal("0.0001")), "f")
    return format(rate.quantize(Decimal("0.000001")), "f")


def ein_values(model):
    """(#7155): the EN 16931 values of a print model, computed once for both syntaxes; ein_build (CII) and
    ein_ubl_build (UBL) only write them. A rule about what the invoice says (tax category, breakdown, payment means,
    terms, notes, parties, line price / quantity / allowance, totals) belongs here, never into one of the writers; the
    writers only decide where and how a value stands in their syntax. Returns a dict:
    m, lang, kind, credit, cur, hcur, home, novat, cat, excode,
    buyer_ref (BT-10 as given), notes (BT-22 head lines: VAT note / exemption, project, progress invoices), text_notes
    (BT-22 texts of the PDF), line_notes ({id(line): BT-127}),
    seller_name, seller (fields: address, tax ids), seller_id (BT-29), seller_contact (BG-6 or None),
    buyer_name, buyer (fields), buyer_contact (BG-9 or None), ship_to (BG-15 for K or None),
    iban, bic (BG-17), means ("58" / "30", BT-81), terms (BT-20 text or ""), terms_default (refund / payable on receipt),
    lines ([{ln, id, n, net, pct, qty, price, charge, allowance, cat, unit, name}]),
    breakdown ([{cat, pct, base, amount, reason, code}], BG-23), line_sum, tax_sum, tax_home (BT-111), gross, paid (BT-113)."""
    m = model or {}
    lang = ein_lang(m.get("lang"))  # 2.185.0 C (#2520)
    kind = m.get("kind") or "invoice"
    sf = m.get("sender_fields") or {}
    rc = m.get("recipient") or {}
    tot, prepaid, abs_note = _abs_full(m)  # 2.408.0 (#3520)
    pay = m.get("payment") or {}
    novat, cat, excode = _doc_cat(m)  # 2.296.0 B (#3173)
    v = {"m": m, "lang": lang, "kind": kind, "credit": kind == "credit", "pay": pay, "novat": novat, "cat": cat, "excode": excode,
         "cur": str(m.get("currency") or "EUR").upper(),
         "hcur": str(tot.get("home") or "EUR").upper(),  # (#2475): the home currency (BT-6)
         "home": _country(sf.get("country"), "DE"),
         "buyer_ref": str(rc.get("buyer_reference") or "").strip()}

    notes = [str(x) for x in (m.get("vat_note_text") or (tot.get("vat_note") if novat else ""), m.get("project_title") and
             tr(EIN_WORDS["project"], " ".join(str(m["project_title"]).split()), lg=lang)) if x and str(x).strip()]  # (#3594): the subject on one line
    if novat and not m.get("vat_note_text"):
        notes.insert(0, _exempt(m, lang))
    v["notes"] = notes[:4] + ([abs_note] if abs_note else [])
    v["line_notes"], v["text_notes"] = _text_notes(m, lang)  # (#6482): intro, rights, closing and trailing text lines (BT-22)

    sname = " ".join(str(sf.get("name") or (m.get("company") or {}).get("name") or "").split())  # (#2188): BT-27 on one line
    novid = {"vat_id": ""} if cat == "O" else {}  # (#3173): BR-O-02 no VAT ids
    v["seller_name"], v["seller"], v["seller_id"] = sname, {**sf, "line2": sf.get("address_extra") or "", **novid}, _seller_id(m, cat)  # BT-36; (#3218): BT-29
    v["seller_contact"] = ({"name": sf.get("managing_directors") or sname, "phone": sf.get("phone"), "email": sf.get("email")}
                           if (sf.get("phone") or sf.get("email")) else None)  # BG-6 (XRechnung BR-DE-2: the seller contact is mandatory)
    rfields = {"street": rc.get("street"), "zip": rc.get("zip"), "city": rc.get("city"), "country": rc.get("country"), "vat_id": rc.get("vat_id"), **novid}
    if rc.get("extra"):  # (#1951): the client's extra address line (BT-51)
        rfields["line2"] = rc["extra"]
    if not rfields["street"] and not rfields["city"]:  # only free address lines (2.40.0 #1368: see fd_split_address)
        lines = [str(x) for x in (rc.get("lines") or []) if str(x).strip() and str(x).strip() not in (str(rc.get("name") or "").strip(), str(rc.get("name_extra") or "").strip())]
        sp = fd_split_address(lines)
        if rfields.get("country"):
            sp.pop("country", None)
        rfields.update(sp)
    v["buyer"] = rfields
    v["buyer_name"] = " - ".join(x for x in (str(rc.get("name") or "").strip(), str(rc.get("name_extra") or "").strip()) if x)  # (#2188): BT-44 + the name addition
    v["buyer_contact"] = rc.get("contact") if isinstance(rc.get("contact"), dict) else None  # (#1380): BG-9
    v["buyer_email"] = rc.get("email_invoice")
    v["customer_no"] = str(rc.get("customer_no") or "").strip()
    # (#2844): BR-IC-12 the deliver-to address (BG-15, BT-80; XRechnung BR-DE-10/11 city + postcode) = the client's
    v["ship_to"] = {k: rfields.get(k) for k in ("zip", "street", "city", "country")} if cat == "K" else None

    v["iban"] = str(pay.get("iban") or sf.get("iban") or "").replace(" ", "")
    v["bic"] = str(pay.get("bic") or sf.get("bic") or "").replace(" ", "")
    v["means"] = "58" if v["iban"] else "30"
    v["bank_name"] = str(sf.get("bank_name") or "")[:70]
    if pay.get("skonto_bt20"):  # (#2087): the XRechnung cash discount line (BT-20), the printed text before it
        first = str(pay.get("text") or "").split("\n")[0][:400]
        v["terms"] = (first + "\n" if first else "") + pay["skonto_bt20"]
    else:
        v["terms"] = str(pay["text"])[:500] if pay.get("text") else ""
    # (#1368): a credit note is not "payable on receipt"; BR-CO-25 still wants terms
    v["terms_default"] = tr(EIN_WORDS["refund"] if kind == "credit" else EIN_WORDS["now"], lg=lang)

    out, by_rate = [], {}
    for ln, n, net, pct, qty, rate, charge in _ein_lines(m, cat):
        lcat = _line_cat(cat, pct, ln.get("tax"))  # (#3169): the category per line (2.357.0 #3217: Z by the tax key)
        lac = _line_allowance(ln) if charge < 0 else None
        allowance = lac if lac and -charge == lac[0] else None  # (#5815): the position's own discount (BG-27 with percent and basis)
        out.append({"ln": ln, "id": str(ln.get("pos") or n), "n": n, "net": net, "pct": pct, "qty": qty, "price": rate,
                    "charge": Decimal("0") if allowance else charge,  # (#4082): else the rounding gap of a sub-cent price
                    "allowance": allowance, "cat": lcat, "unit": UNIT_CODES.get(str(ln.get("unit") or ""), "C62"),
                    "name": str(ln.get("title") or "")[:200] or ("Position " + str(n))})
        by_rate[(lcat, pct)] = by_rate.get((lcat, pct), Decimal("0")) + net
    v["lines"] = out
    v["line_sum"] = sum((x["net"] for x in out), Decimal("0"))

    tax_lines = [tl for tl in (tot.get("tax_lines") or []) if isinstance(tl, dict)]
    bd, tax_sum = [], Decimal("0")
    for lcat, pct in (sorted(by_rate) if by_rate else [(cat, Decimal("0"))]):  # (#3169): one breakdown per category and rate (BR-CO-18)
        base = by_rate.get((lcat, pct), Decimal("0"))
        given = next((tl for tl in tax_lines if _d(tl.get("pct")) == pct), None)
        amount = _d(given.get("amount")).quantize(Q2, rounding=ROUND_HALF_UP) if given else (base * pct / 100).quantize(Q2, rounding=ROUND_HALF_UP)
        if lcat != "S":
            amount = Decimal("0")
        bd.append({"cat": lcat, "pct": pct, "base": base, "amount": amount,
                   "reason": "" if lcat in ("S", "Z") else _reason(m, lang, cat, lcat),  # (#3217): BR-Z-10 no exemption reason for zero rated
                   "code": excode if lcat == cat else ""})
        tax_sum += amount
    v["breakdown"], v["tax_sum"] = bd, tax_sum
    v["tax_home"] = tot.get("tax_eur") if tot.get("tax_eur") not in (None, "") else tax_sum  # BT-111
    gross = tot.get("gross") if tot.get("gross") not in (None, "") else v["line_sum"] + tax_sum
    v["gross"] = _d(gross).quantize(Q2, rounding=ROUND_HALF_UP)
    # (#4079): BT-113 of a finalised document is fixed like its PDF: no payments of today, only the progress invoices
    v["paid"] = prepaid if kind == "invoice" else Decimal("0")
    return v


def ein_build(model, fmt="zugferd"):
    """The CII XML (bytes, UTF-8) from the print model of an invoice / credit note (see the module text for the keys used:
    kind, number, date, lang, currency, order_ref, service_from/to, due_date, sender_fields, recipient, lines, totals,
    cancels, payment, vat_mode, vat_note_key). fmt: zugferd (EN 16931 profile) or xrechnung (BT-10 buyer reference
    mandatory -> BadInput with the reason). (#7155): writes the values of ein_values in the CII order."""
    fmt = fmt if fmt in EIN_FORMATS else "zugferd"
    v = ein_values(model)
    m, cur, hcur, home = v["m"], v["cur"], v["hcur"], v["home"]
    if fmt == "xrechnung" and not v["buyer_ref"]:
        raise BadInput(tr("XRechnung needs a buyer reference (billing details of the client)."))

    for p, u in NS.items():
        ET.register_namespace(p, u)
    root = ET.Element(f"{{{NS['rsm']}}}CrossIndustryInvoice")
    ctx = _e(root, "rsm:ExchangedDocumentContext")
    _e(_e(ctx, "ram:BusinessProcessSpecifiedDocumentContextParameter"), "ram:ID", EIN_PROCESS)
    _e(_e(ctx, "ram:GuidelineSpecifiedDocumentContextParameter"), "ram:ID", EIN_PROFILE[fmt])
    doc = _e(root, "rsm:ExchangedDocument")
    _e(doc, "ram:ID", m.get("number") or "")
    _e(doc, "ram:TypeCode", "381" if v["credit"] else (m.get("type_code") or "380"))  # (#2087): 326 progress invoice
    _date_el(doc, "ram:IssueDateTime", m.get("date"))
    for n in v["notes"] + v["text_notes"]:  # one IncludedNote per text
        _e(_e(doc, "ram:IncludedNote"), "ram:Content", n)

    tx = _e(root, "rsm:SupplyChainTradeTransaction")
    # 2.1259.0 (#6303 e): price and quantity as in the UBL (one rule in ein_values since #7155)
    for x in v["lines"]:
        ln = x["ln"]
        li = _e(tx, "ram:IncludedSupplyChainTradeLineItem")
        ald = _e(li, "ram:AssociatedDocumentLineDocument")
        _e(ald, "ram:LineID", x["id"])
        if id(ln) in v["line_notes"]:  # (#6482): the heading / text lines above this position (BT-127)
            _e(_e(ald, "ram:IncludedNote"), "ram:Content", v["line_notes"][id(ln)])
        pr = _e(li, "ram:SpecifiedTradeProduct")
        _e(pr, "ram:Name", x["name"])
        if ln.get("detail"):
            _e(pr, "ram:Description", str(ln["detail"])[:1000])
        _e(_e(_e(li, "ram:SpecifiedLineTradeAgreement"), "ram:NetPriceProductTradePrice"), "ram:ChargeAmount", _uprice(x["price"]))
        _e(_e(li, "ram:SpecifiedLineTradeDelivery"), "ram:BilledQuantity", _qty(x["qty"]), unitCode=x["unit"])
        st = _e(li, "ram:SpecifiedLineTradeSettlement")
        t = _e(st, "ram:ApplicableTradeTax")
        _e(t, "ram:TypeCode", "VAT")
        _e(t, "ram:CategoryCode", x["cat"])
        if x["cat"] != "O":  # BR-O-05: no rate for "not subject to VAT"
            _e(t, "ram:RateApplicablePercent", _pct(x["pct"]))
        lac, charge = x["allowance"], x["charge"]
        if lac:  # (#5815): the position's own discount as a line allowance (BG-27: BT-136 .. BT-140, schema order before BG-30's sum)
            ac = _e(st, "ram:SpecifiedTradeAllowanceCharge")
            _e(_e(ac, "ram:ChargeIndicator"), "udt:Indicator", "false")
            _e(ac, "ram:CalculationPercent", _pct(lac[2]))
            _e(ac, "ram:BasisAmount", _m(lac[1]))
            _e(ac, "ram:ActualAmount", _m(lac[0]))
            _e(ac, "ram:ReasonCode", "95")  # UNTDID 5189: discount
            _e(ac, "ram:Reason", "Discount")
        elif charge:  # 2.1259.0 (#6303 e): the rounding gap of a sub-cent price (BG-27 / BG-28 like the UBL)
            ac = _e(st, "ram:SpecifiedTradeAllowanceCharge")
            _e(_e(ac, "ram:ChargeIndicator"), "udt:Indicator", "true" if charge > 0 else "false")
            _e(ac, "ram:ActualAmount", _m(abs(charge)))
            _e(ac, "ram:Reason", "Rounding")  # BR-41 / BR-42: a reason or a reason code
        _e(_e(st, "ram:SpecifiedTradeSettlementLineMonetarySummation"), "ram:LineTotalAmount", _m(x["net"]))

    ag = _e(tx, "ram:ApplicableHeaderTradeAgreement")
    if v["buyer_ref"]:
        _e(ag, "ram:BuyerReference", v["buyer_ref"])
    _party(ag, "ram:SellerTradeParty", v["seller_name"], v["seller"], home, contact=v["seller_contact"],
           email=v["seller"].get("email"), legal_id=v["seller"].get("register_no"), party_id=v["seller_id"])
    _party(ag, "ram:BuyerTradeParty", v["buyer_name"], v["buyer"], home, email=v["buyer_email"],
           contact=v["buyer_contact"] if v["buyer_contact"] and v["buyer_contact"].get("name") else None)
    if m.get("order_ref"):
        _e(_e(ag, "ram:BuyerOrderReferencedDocument"), "ram:IssuerAssignedID", m["order_ref"])
    dl = _e(tx, "ram:ApplicableHeaderTradeDelivery")  # BG-13: the period of service stands in BillingSpecifiedPeriod below
    if v["ship_to"]:
        _address(_e(_e(dl, "ram:ShipToTradeParty"), "ram:PostalTradeAddress"), v["ship_to"], home)
    se = _e(tx, "ram:ApplicableHeaderTradeSettlement")
    if cur != hcur:
        _e(se, "ram:TaxCurrencyCode", hcur)
    _e(se, "ram:InvoiceCurrencyCode", cur)
    pm = _e(se, "ram:SpecifiedTradeSettlementPaymentMeans")
    _e(pm, "ram:TypeCode", v["means"])
    _e(pm, "ram:Information", "SEPA" if v["iban"] else tr(EIN_WORDS["transfer"], lg=v["lang"]))
    if v["iban"]:
        acc = _e(pm, "ram:PayeePartyCreditorFinancialAccount")
        _e(acc, "ram:IBANID", v["iban"])
        if v["bank_name"]:
            _e(acc, "ram:AccountName", v["bank_name"])
        if v["bic"]:
            _e(_e(pm, "ram:PayeeSpecifiedCreditorFinancialInstitution"), "ram:BICID", v["bic"])
    for b in v["breakdown"]:
        t = _e(se, "ram:ApplicableTradeTax")
        _e(t, "ram:CalculatedAmount", _m(b["amount"]))
        _e(t, "ram:TypeCode", "VAT")
        if b["cat"] not in ("S", "Z"):  # (#3217): BR-Z-10 no exemption reason for zero rated
            _e(t, "ram:ExemptionReason", b["reason"])
        _e(t, "ram:BasisAmount", _m(b["base"]))
        _e(t, "ram:CategoryCode", b["cat"])
        if b["code"]:
            _e(t, "ram:ExemptionReasonCode", b["code"])
        _e(t, "ram:RateApplicablePercent", _pct(b["pct"]))  # BT-119 0 for O as well (XRechnung BR-DE-14 wants it)
    if m.get("service_from") or m.get("service_to"):
        bp = _e(se, "ram:BillingSpecifiedPeriod")
        _date_el(bp, "ram:StartDateTime", m.get("service_from") or m.get("service_to"))
        _date_el(bp, "ram:EndDateTime", m.get("service_to") or m.get("service_from"))
    pt = _e(se, "ram:SpecifiedTradePaymentTerms")
    if v["terms"]:
        _e(pt, "ram:Description", v["terms"])
    if m.get("due_date"):
        _date_el(pt, "ram:DueDateDateTime", m.get("due_date"))
    elif v["credit"] or not v["pay"].get("text"):
        _e(pt, "ram:Description", v["terms_default"])
    ms = _e(se, "ram:SpecifiedTradeSettlementHeaderMonetarySummation")
    _e(ms, "ram:LineTotalAmount", _m(v["line_sum"]))
    _e(ms, "ram:TaxBasisTotalAmount", _m(v["line_sum"]))
    _e(ms, "ram:TaxTotalAmount", _m(v["tax_sum"]), currencyID=cur)
    if cur != hcur:
        _e(ms, "ram:TaxTotalAmount", _m(v["tax_home"]), currencyID=hcur)
    _e(ms, "ram:GrandTotalAmount", _m(v["gross"]))
    _e(ms, "ram:TotalPrepaidAmount", _m(v["paid"]))
    _e(ms, "ram:DuePayableAmount", _m(v["gross"] - v["paid"]))
    cz = m.get("cancels") or {}
    if v["credit"] and cz.get("number"):
        ir = _e(se, "ram:InvoiceReferencedDocument")
        _e(ir, "ram:IssuerAssignedID", cz["number"])
        if cz.get("date"):
            _date_el(ir, "ram:FormattedIssueDateTime", cz["date"], prefix="qdt")
    ET.indent(root, space=" ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def ein_xml(c, oid, did, fmt=None):
    """The XML of the finalised invoice / credit note did of organisation oid (bytes). fmt: the document's einvoice_format
    when empty. 409 (BadInput) for drafts and other kinds."""
    from .docs import odoc_render
    model = odoc_render(c, did, oid)
    if not model.get("locked") or model.get("kind") not in ("invoice", "credit"):
        raise BadInput(tr("The e-invoice XML exists for finalised invoices and credit notes only."))
    return ein_build(model, fmt or model.get("einvoice_format") or "zugferd")


# ---------------------------------------------------------------- the own check (no validator)
def _find(el, path):
    return el.find(path, NS)


def _text(el, path):
    x = _find(el, path) if el is not None else None
    return (x.text or "").strip() if x is not None else ""


def ein_check(xml_bytes):
    """Plausibility findings of an e-invoice XML (list of strings, empty = fine): mandatory business terms present, the
    sums agree (BR-CO-10/13/15/16, BR-CO-17 tax per rate = base x rate rounded half up), lines present, dates well-formed.
    Not a replacement for the Schematron validator (CI), but enough for tests without Java."""
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return [f"not well-formed: {e}"]
    doc = _find(root, "rsm:ExchangedDocument")
    tx = _find(root, "rsm:SupplyChainTradeTransaction")
    if doc is None or tx is None:
        return ["missing ExchangedDocument / SupplyChainTradeTransaction"]
    req = {"BT-1 number": (doc, "ram:ID"), "BT-3 type": (doc, "ram:TypeCode"), "BT-2 date": (doc, "ram:IssueDateTime/udt:DateTimeString"),
           "BT-24 profile": (root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"),
           "BT-27 seller name": (tx, "ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:Name"),
           "BT-40 seller country": (tx, "ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:PostalTradeAddress/ram:CountryID"),
           "BT-44 buyer name": (tx, "ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty/ram:Name"),
           "BT-55 buyer country": (tx, "ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty/ram:PostalTradeAddress/ram:CountryID"),
           "BT-5 currency": (tx, "ram:ApplicableHeaderTradeSettlement/ram:InvoiceCurrencyCode"),
           "BT-106 line total": (tx, "ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:LineTotalAmount"),
           "BT-109 tax basis": (tx, "ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:TaxBasisTotalAmount"),
           "BT-112 grand total": (tx, "ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:GrandTotalAmount"),
           "BT-115 due": (tx, "ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:DuePayableAmount")}
    for name, (el, path) in req.items():
        if not _text(el, path):
            out.append(f"{name} missing")
    if _text(doc, "ram:TypeCode") not in ("380", "381", "326"):  # 2.120.0 A (#2087): 326 progress invoice
        out.append("BT-3 type must be 380, 381 or 326")
    for d in root.iterfind(".//udt:DateTimeString", NS):
        if not re.fullmatch(r"\d{8}", d.text or "") or d.get("format") != "102":
            out.append(f"date not YYYYMMDD / format 102: {d.text}")
    dlv = f"{{{NS['ram']}}}ApplicableHeaderTradeDelivery"  # BG-13 is a mandatory group, empty without a deliver-to party
    for el in root.iter():  # 2.424.0 C (#3524): ZUGFeRD 2.4+ deprecates empty elements
        if len(el) == 0 and not (el.text or "").strip() and el.tag != dlv:
            out.append(f"empty element {el.tag.rpartition('}')[2]}")
    profile = _text(root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID")
    seller = _find(tx, "ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty")
    if seller is not None and not seller.findall("ram:SpecifiedTaxRegistration/ram:ID", NS) and not _text(seller, "ram:SpecifiedLegalOrganization/ram:ID") \
            and not _text(seller, "ram:ID"):  # 2.357.0 (#3218): + the seller identifier BT-29
        out.append("BT-31/BT-32/BT-30 seller tax or registration id missing")
    if "xrechnung" in profile:
        if not _text(tx, "ram:ApplicableHeaderTradeAgreement/ram:BuyerReference"):
            out.append("BT-10 buyer reference missing (XRechnung)")
        if seller is not None and not (_text(seller, "ram:DefinedTradeContact/ram:PersonName") and
                                       _text(seller, "ram:DefinedTradeContact/ram:TelephoneUniversalCommunication/ram:CompleteNumber") and
                                       _text(seller, "ram:DefinedTradeContact/ram:EmailURIUniversalCommunication/ram:URIID")):
            out.append("BT-41/42/43 seller contact with phone and e-mail missing (XRechnung)")
        if not _text(tx, "ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:URIUniversalCommunication/ram:URIID"):
            out.append("BT-34 seller electronic address missing (XRechnung)")
        if not _text(tx, "ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty/ram:URIUniversalCommunication/ram:URIID"):
            out.append("BT-49 buyer electronic address missing (XRechnung)")
        # 2.1308.0 (#6476): postcode and city of seller and buyer are mandatory in XRechnung (BR-DE-3/4, BR-DE-8/9)
        for who, nos, base in (("seller", ("BR-DE-4", "BR-DE-3"), "SellerTradeParty"), ("buyer", ("BR-DE-9", "BR-DE-8"), "BuyerTradeParty")):
            for no, (tag, what) in zip(nos, (("PostcodeCode", "postcode"), ("CityName", "city"))):
                if not _text(tx, f"ram:ApplicableHeaderTradeAgreement/ram:{base}/ram:PostalTradeAddress/ram:{tag}"):
                    out.append(f"{no} {who} {what} missing (XRechnung)")
    lines = tx.findall("ram:IncludedSupplyChainTradeLineItem", NS)
    if not lines:
        out.append("BG-25 no invoice lines")
    line_sum = Decimal("0")
    by_cat = {}
    for li in lines:
        amt = _text(li, "ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount")
        if not re.fullmatch(r"-?\d+\.\d{2}", amt):
            out.append(f"BT-131 line amount not two places: {amt!r}")
            continue
        if _d(_text(li, "ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount")) < 0:
            out.append("BT-146 net price negative")
        if not _text(li, "ram:SpecifiedTradeProduct/ram:Name"):
            out.append("BT-153 item name missing")
        line_sum += _d(amt)
        key = (_text(li, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:CategoryCode"),
               _d(_text(li, "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent")))
        by_cat[key] = by_cat.get(key, Decimal("0")) + _d(amt)
    se = _find(tx, "ram:ApplicableHeaderTradeSettlement")
    ms = _find(se, "ram:SpecifiedTradeSettlementHeaderMonetarySummation") if se is not None else None
    if ms is None:
        return out + ["BG-22 totals missing"]
    bt106, bt109, bt112, bt113, bt115 = (_d(_text(ms, p)) for p in ("ram:LineTotalAmount", "ram:TaxBasisTotalAmount", "ram:GrandTotalAmount",
                                                                    "ram:TotalPrepaidAmount", "ram:DuePayableAmount"))
    allow = _d(_text(ms, "ram:AllowanceTotalAmount"))
    charge = _d(_text(ms, "ram:ChargeTotalAmount"))
    cur = _text(se, "ram:InvoiceCurrencyCode")
    taxcur = _text(se, "ram:TaxCurrencyCode")
    tts = ms.findall("ram:TaxTotalAmount", NS)
    bt110 = next((_d(t.text) for t in tts if t.get("currencyID") == cur), None)
    if bt110 is None:
        out.append("BT-110 tax total in the invoice currency missing")
        bt110 = Decimal("0")
    if taxcur and not any(t.get("currencyID") == taxcur for t in tts):
        out.append("BT-111 tax total in the tax currency missing")
    if line_sum != bt106:
        out.append(f"BR-CO-10: sum of lines {line_sum} != BT-106 {bt106}")
    if bt106 - allow + charge != bt109:
        out.append(f"BR-CO-13: BT-109 {bt109} != BT-106 - allowances + charges {bt106 - allow + charge}")
    if bt109 + bt110 != bt112:
        out.append(f"BR-CO-15: BT-112 {bt112} != BT-109 + BT-110 {bt109 + bt110}")
    if bt112 - bt113 != bt115:
        out.append(f"BR-CO-16: BT-115 {bt115} != BT-112 - BT-113 {bt112 - bt113}")
    tax_sum = Decimal("0")
    seen = set()
    for t in se.findall("ram:ApplicableTradeTax", NS):
        cat = _text(t, "ram:CategoryCode")
        pct = _d(_text(t, "ram:RateApplicablePercent"))
        base = _d(_text(t, "ram:BasisAmount"))
        amount = _d(_text(t, "ram:CalculatedAmount"))
        seen.add((cat, pct))
        want = (base * pct / 100).quantize(Q2, rounding=ROUND_HALF_UP)
        # 2.408.0 (#3520): with a paid amount (BT-113 > 0, e.g. a final invoice that adds the taxes its progress invoices rounded
        # each) a few cents apart are fine (the EN 16931 rule allows 1.00); without one exact
        if amount != want and not (bt113 > 0 and abs(amount - want) <= Decimal("0.05")):
            out.append(f"BR-CO-17: tax {amount} for {cat} {pct} % != {want}")
        if by_cat.get((cat, pct), Decimal("0")) != base:
            out.append(f"BR-S-08: basis {base} for {cat} {pct} % != sum of its lines {by_cat.get((cat, pct), Decimal('0'))}")
        if cat not in ("S", "Z") and not (_text(t, "ram:ExemptionReason") or _text(t, "ram:ExemptionReasonCode")):
            out.append(f"BR-{cat}-10: exemption reason missing")
        if cat == "Z" and (_text(t, "ram:ExemptionReason") or _text(t, "ram:ExemptionReasonCode")):  # 2.357.0 (#3217)
            out.append("BR-Z-10: zero rated carries no exemption reason")
        tax_sum += amount
    if set(by_cat) - seen:
        out.append(f"tax breakdown lacks {sorted(set(by_cat) - seen)}")
    # 2.296.0 B (#3168, #3169, #3173): the category rules the Schematron rejects (rate, VAT ids of seller and buyer)
    cats = {k[0] for k in by_cat} | {k[0] for k in seen}
    buyer = _find(tx, "ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty")
    s_va = seller is not None and any(i.get("schemeID") == "VA" and (i.text or "").strip() for i in seller.findall("ram:SpecifiedTaxRegistration/ram:ID", NS))
    b_va = buyer is not None and any(i.get("schemeID") == "VA" and (i.text or "").strip() for i in buyer.findall("ram:SpecifiedTaxRegistration/ram:ID", NS))
    b_legal = buyer is not None and bool(_text(buyer, "ram:SpecifiedLegalOrganization/ram:ID"))
    if any(k[0] == "S" and k[1] <= 0 for k in by_cat):
        out.append("BR-S-05: a line of category S needs a rate above zero")
    s_fc = seller is not None and any(i.get("schemeID") == "FC" and (i.text or "").strip() for i in seller.findall("ram:SpecifiedTaxRegistration/ram:ID", NS))
    if "AE" in cats and not (s_va or s_fc):  # 2.296.0 F (#3168): BT-31 or BT-32 (domestic section 13b: tax number)
        out.append("BR-AE-02: reverse charge needs the seller's VAT id (BT-31)")
    if "AE" in cats and not (b_va or b_legal):
        out.append("BR-AE-02: reverse charge needs the buyer's VAT id (BT-48)")
    if "O" in cats and (s_va or b_va):
        out.append("BR-O-02: not subject to VAT carries no VAT id of seller or buyer")
    if "O" in cats and len(cats) > 1:
        out.append("BR-O-11: not subject to VAT allows no other category")
    if tax_sum != bt110:
        out.append(f"BR-CO-14: BT-110 {bt110} != sum of the tax breakdown {tax_sum}")
    if bt115 > 0 and not (_text(se, "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString") or _text(se, "ram:SpecifiedTradePaymentTerms/ram:Description")):
        out.append("BR-CO-25: due date or payment terms missing")
    if not se.findall("ram:SpecifiedTradeSettlementPaymentMeans", NS):
        out.append("BG-16 payment means missing")
    return out


# 2.1308.0 (#6476): the findings of ein_check that finalising refuses, as plain texts for the person (stored: [key, args]).
# Every finding blocks except the empty element (ZUGFeRD 2.4+ only deprecates it, the EN 16931 / XRechnung rules do not
# reject it); a finding without a plain text is named as it is (a sum the module itself got wrong).
EIN_PLAIN = (("BT-10 ", N_("the client's Leitweg ID (buyer reference, XRechnung)")),
             ("BT-41/42/43 ", N_("phone and e-mail of your company (office settings, company; XRechnung)")),
             ("BT-34 ", N_("e-mail of your company (office settings, company; XRechnung)")),
             ("BT-49 ", N_("the client's invoice e-mail (XRechnung)")),
             ("BR-DE-3 ", N_("city of your company")), ("BR-DE-4 ", N_("postcode of your company")),
             ("BR-DE-8 ", N_("city of the recipient")), ("BR-DE-9 ", N_("postcode of the recipient")),
             ("BT-27 ", N_("company name")), ("BT-44 ", N_("recipient name")),
             ("BT-31/BT-32/BT-30 ", N_("tax number or VAT ID")), ("BG-25 ", N_("at least one position")),
             ("BR-CO-25", N_("due date or payment days")))


def ein_check_block(xml_bytes):
    """2.1308.0 (#6476): what stops finalising an e-invoice: [[key, *args], ...] (stored texts, tr(*x)), empty = fine."""
    out = []
    for f in ein_check(xml_bytes):
        if f.startswith("empty element"):
            continue
        # 2.1308.0 (#6476, case F51): a tax per rate a few cents off base x rate (a credit note / final invoice made from the
        # gross amounts, #6445: 178.48 gross -> 28.49 tax on 149.99) is within the EN 16931 / KoSIT tolerance of 1.00 for BR-CO-17;
        # ein_check stays exact (it is the test of the module's own sums), finalising refuses only what a validator rejects
        m = re.match(r"BR-CO-17: tax (\S+) for .* != (\S+)$", f)
        if m and abs(_d(m.group(1)) - _d(m.group(2))) <= Decimal("1.00"):
            continue
        hit = next((k for p, k in EIN_PLAIN if f.startswith(p)), None)
        x = [hit] if hit else [N_("e-invoice check: {0}"), f]
        if x not in out:
            out.append(x)
    return out


# ---------------------------------------------------------------- 2.154.0 B (#1960): UBL 2.1 (Peppol BIS Billing 3.0)
# The same print model as OASIS UBL 2.1 Invoice / CreditNote: Peppol BIS Billing 3.0 (the Peppol network), the XRechnung
# 3.0 UBL syntax (German public buyers, also through Peppol) or plain EN 16931. (#7155): like ein_build only a writer
# of ein_values (tax category by vat_note, discount lines as a negative quantity, BT-111 ...); a rule goes there, not here.
# EndpointID (BT-34 / BT-49): the Peppol ids "<scheme>:<id>" when given, else the e-mail (scheme EM).
UBL_PROFILES = {"peppol": "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0",
                "xrechnung": "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0",
                "en16931": "urn:cen.eu:en16931:2017"}
UBL_NS = {"inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
          "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
          "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
          "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}


def _u(parent, tag, text=None, **attrs):
    """A UBL element (cac:/cbc:); an empty text is not written (PEPPOL-EN16931-R008: no empty elements)."""
    ns, _, name = tag.partition(":")
    el = ET.SubElement(parent, f"{{{UBL_NS[ns]}}}{name}", {k: v for k, v in attrs.items() if v not in (None, "")})
    if text is not None:
        el.text = str(text)
    return el


def _ut(parent, tag, text, **attrs):
    """_u only when text is not empty."""
    if text is None or not str(text).strip():
        return None
    return _u(parent, tag, str(text).strip(), **attrs)


def _udate(iso):
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})", str(iso or "")[:10])
    return m.group(1) if m else ""


def ein_ubl_endpoint(pid):
    """'<scheme>:<id>' -> (scheme, id) or None."""
    m = re.fullmatch(r"\s*(\d{4}|EM):(\S{1,200})\s*", str(pid or ""))
    return (m.group(1), m.group(2)) if m else None


def _ubl_party(parent, tag, name, f, home, endpoint=None, email=None, contact=None, legal_id=None, seller=False, party_id=""):
    """AccountingSupplierParty / AccountingCustomerParty in the UBL order: EndpointID, PartyIdentification (BT-29, 2.357.0
    #3218), PostalAddress, PartyTaxScheme, PartyLegalEntity, Contact."""
    p = _u(_u(parent, tag), "cac:Party")
    ep = ein_ubl_endpoint(endpoint)
    if ep:
        _u(p, "cbc:EndpointID", ep[1], schemeID=ep[0])
    elif email:
        _u(p, "cbc:EndpointID", email, schemeID="EM")
    if party_id:
        _u(_u(p, "cac:PartyIdentification"), "cbc:ID", party_id)
    a = _u(p, "cac:PostalAddress")
    _ut(a, "cbc:StreetName", f.get("street"))
    _ut(a, "cbc:AdditionalStreetName", f.get("line2"))
    _ut(a, "cbc:CityName", f.get("city"))
    _ut(a, "cbc:PostalZone", f.get("zip"))
    if f.get("line3"):
        _ut(_u(a, "cac:AddressLine"), "cbc:Line", f["line3"])
    _u(_u(a, "cac:Country"), "cbc:IdentificationCode", _country(f.get("country"), home))
    if f.get("vat_id"):
        ts = _u(p, "cac:PartyTaxScheme")
        _u(ts, "cbc:CompanyID", f["vat_id"])
        _u(_u(ts, "cac:TaxScheme"), "cbc:ID", "VAT")
    if seller and f.get("tax_number"):  # BT-32: the seller's tax number (scheme FC, not VAT)
        ts = _u(p, "cac:PartyTaxScheme")
        _u(ts, "cbc:CompanyID", f["tax_number"])
        _u(_u(ts, "cac:TaxScheme"), "cbc:ID", "FC")
    le = _u(p, "cac:PartyLegalEntity")
    _u(le, "cbc:RegistrationName", name or "-")
    _ut(le, "cbc:CompanyID", legal_id)
    if contact and (contact.get("name") or contact.get("phone") or contact.get("email")):
        ct = _u(p, "cac:Contact")
        _ut(ct, "cbc:Name", contact.get("name"))
        _ut(ct, "cbc:Telephone", contact.get("phone"))
        _ut(ct, "cbc:ElectronicMail", contact.get("email"))
    return p


def ein_ubl_build(model, profile="peppol", sender_id="", receiver_id=""):
    """The UBL 2.1 XML (bytes, UTF-8) of an invoice / credit note print model. profile: peppol (Peppol BIS Billing 3.0),
    xrechnung (XRechnung 3.0 UBL: BT-10 mandatory -> BadInput) or en16931. sender_id / receiver_id: Peppol ids
    "<scheme>:<id>" (BT-34 / BT-49); empty = the e-mail addresses (scheme EM). (#7155): writes the values of
    ein_values in the UBL order."""
    profile = profile if profile in UBL_PROFILES else "peppol"
    v = ein_values(model)
    m, cur, hcur, home, credit = v["m"], v["cur"], v["hcur"], v["home"], v["credit"]
    buyer_ref = v["buyer_ref"]
    if profile == "xrechnung" and not buyer_ref:
        raise BadInput(tr("XRechnung needs a buyer reference (billing details of the client)."))
    if profile == "peppol" and not buyer_ref and not m.get("order_ref"):
        buyer_ref = v["customer_no"]  # PEPPOL-EN16931-R003: BT-10 or BT-13; the customer number stands in

    for p, u in (("cac", UBL_NS["cac"]), ("cbc", UBL_NS["cbc"])):
        ET.register_namespace(p, u)
    ET.register_namespace("", UBL_NS["cn" if credit else "inv"])
    root = ET.Element(f"{{{UBL_NS['cn' if credit else 'inv']}}}{'CreditNote' if credit else 'Invoice'}")
    _u(root, "cbc:CustomizationID", UBL_PROFILES[profile])
    _u(root, "cbc:ProfileID", EIN_PROCESS)
    _u(root, "cbc:ID", m.get("number") or "")
    _u(root, "cbc:IssueDate", _udate(m.get("date")))
    if not credit and _udate(m.get("due_date")):
        _u(root, "cbc:DueDate", _udate(m.get("due_date")))
    _u(root, "cbc:CreditNoteTypeCode" if credit else "cbc:InvoiceTypeCode", "381" if credit else (m.get("type_code") or "380"))
    if v["notes"] or v["text_notes"]:  # PEPPOL-EN16931-R002: one note on document level (the texts as paragraphs after the old lines)
        _u(root, "cbc:Note", "\n\n".join((["\n".join(v["notes"])] if v["notes"] else []) + v["text_notes"]))
    _u(root, "cbc:DocumentCurrencyCode", cur)
    if cur != hcur:
        _u(root, "cbc:TaxCurrencyCode", hcur)
    if buyer_ref:
        _u(root, "cbc:BuyerReference", buyer_ref)
    if m.get("service_from") or m.get("service_to"):
        ip = _u(root, "cac:InvoicePeriod")
        _u(ip, "cbc:StartDate", _udate(m.get("service_from") or m.get("service_to")))
        _u(ip, "cbc:EndDate", _udate(m.get("service_to") or m.get("service_from")))
    if m.get("order_ref"):
        _u(_u(root, "cac:OrderReference"), "cbc:ID", m["order_ref"])
    cz = m.get("cancels") or {}
    if credit and cz.get("number"):  # BT-25 / BT-26: the invoice this credit note cancels
        dr = _u(_u(root, "cac:BillingReference"), "cac:InvoiceDocumentReference")
        _u(dr, "cbc:ID", cz["number"])
        _ut(dr, "cbc:IssueDate", _udate(cz.get("date")))

    sf = v["seller"]
    _ubl_party(root, "cac:AccountingSupplierParty", v["seller_name"], sf, home, endpoint=sender_id, email=sf.get("email"),
               legal_id=sf.get("register_no"), seller=True, party_id=v["seller_id"], contact=v["seller_contact"])
    _ubl_party(root, "cac:AccountingCustomerParty", v["buyer_name"], v["buyer"], home, endpoint=receiver_id, email=v["buyer_email"],
               contact=v["buyer_contact"])
    if v["ship_to"]:
        sa = _u(_u(_u(root, "cac:Delivery"), "cac:DeliveryLocation"), "cac:Address")
        _ut(sa, "cbc:StreetName", v["ship_to"].get("street"))
        _ut(sa, "cbc:CityName", v["ship_to"].get("city"))
        _ut(sa, "cbc:PostalZone", v["ship_to"].get("zip"))
        _u(_u(sa, "cac:Country"), "cbc:IdentificationCode", _country(v["ship_to"].get("country"), home))

    pm = _u(root, "cac:PaymentMeans")
    _u(pm, "cbc:PaymentMeansCode", v["means"])
    if credit and _udate(m.get("due_date")):
        _u(pm, "cbc:PaymentDueDate", _udate(m.get("due_date")))
    if v["iban"]:
        acc = _u(pm, "cac:PayeeFinancialAccount")
        _u(acc, "cbc:ID", v["iban"])
        _ut(acc, "cbc:Name", v["bank_name"])
        if v["bic"]:
            _u(_u(acc, "cac:FinancialInstitutionBranch"), "cbc:ID", v["bic"])
    terms = v["terms"] or (v["terms_default"] if credit or not m.get("due_date") else "")
    if terms:
        _u(_u(root, "cac:PaymentTerms"), "cbc:Note", terms)

    tt = _u(root, "cac:TaxTotal")
    _u(tt, "cbc:TaxAmount", _m(v["tax_sum"]), currencyID=cur)
    for b in v["breakdown"]:
        st = _u(tt, "cac:TaxSubtotal")
        _u(st, "cbc:TaxableAmount", _m(b["base"]), currencyID=cur)
        _u(st, "cbc:TaxAmount", _m(b["amount"]), currencyID=cur)
        tc = _u(st, "cac:TaxCategory")
        _u(tc, "cbc:ID", b["cat"])
        _u(tc, "cbc:Percent", _pct(b["pct"]))  # BT-119 0 for O as well (XRechnung BR-DE-14 wants it; only the line rate BT-152 goes, BR-O-05)
        if b["cat"] not in ("S", "Z"):  # (#3217): BR-Z-10
            _ut(tc, "cbc:TaxExemptionReasonCode", b["code"])
            _u(tc, "cbc:TaxExemptionReason", b["reason"])
        _u(_u(tc, "cac:TaxScheme"), "cbc:ID", "VAT")
    if cur != hcur:  # BT-111: the tax in the home currency, its own TaxTotal without subtotals
        _u(_u(root, "cac:TaxTotal"), "cbc:TaxAmount", _m(v["tax_home"]), currencyID=hcur)
    mt = _u(root, "cac:LegalMonetaryTotal")
    _u(mt, "cbc:LineExtensionAmount", _m(v["line_sum"]), currencyID=cur)
    _u(mt, "cbc:TaxExclusiveAmount", _m(v["line_sum"]), currencyID=cur)
    _u(mt, "cbc:TaxInclusiveAmount", _m(v["gross"]), currencyID=cur)
    if v["paid"]:
        _u(mt, "cbc:PrepaidAmount", _m(v["paid"]), currencyID=cur)
    _u(mt, "cbc:PayableAmount", _m(v["gross"] - v["paid"]), currencyID=cur)

    for x in v["lines"]:
        ln = x["ln"]
        li = _u(root, "cac:CreditNoteLine" if credit else "cac:InvoiceLine")
        _u(li, "cbc:ID", x["id"])
        if id(ln) in v["line_notes"]:  # (#6482): the heading / text lines above this position (BT-127, one note per line)
            _u(li, "cbc:Note", v["line_notes"][id(ln)])
        _u(li, "cbc:CreditedQuantity" if credit else "cbc:InvoicedQuantity", _qty(x["qty"]), unitCode=x["unit"])
        _u(li, "cbc:LineExtensionAmount", _m(x["net"]), currencyID=cur)
        lac, charge = x["allowance"], x["charge"]
        if lac:  # (#5815): the position's own discount (BG-27 with its percent and basis)
            ac = _u(li, "cac:AllowanceCharge")
            _u(ac, "cbc:ChargeIndicator", "false")
            _u(ac, "cbc:AllowanceChargeReasonCode", "95")
            _u(ac, "cbc:AllowanceChargeReason", "Discount")
            _u(ac, "cbc:MultiplierFactorNumeric", _pct(lac[2]))
            _u(ac, "cbc:Amount", _m(lac[0]), currencyID=cur)
            _u(ac, "cbc:BaseAmount", _m(lac[1]), currencyID=cur)
        elif charge:  # 2.523.0 (#4082): the rounding gap of a sub-cent price (BG-27 / BG-28, schema order before cac:Item)
            ac = _u(li, "cac:AllowanceCharge")
            _u(ac, "cbc:ChargeIndicator", "true" if charge > 0 else "false")
            _u(ac, "cbc:AllowanceChargeReason", "Rounding")  # BR-41 / BR-42: a reason or a reason code
            _u(ac, "cbc:Amount", _m(abs(charge)), currencyID=cur)
        it = _u(li, "cac:Item")
        _ut(it, "cbc:Description", str(ln.get("detail") or "")[:1000])
        _u(it, "cbc:Name", x["name"])
        tc = _u(it, "cac:ClassifiedTaxCategory")
        _u(tc, "cbc:ID", x["cat"])  # (#3169), (#3217)
        if x["cat"] != "O":
            _u(tc, "cbc:Percent", _pct(x["pct"]))
        _u(_u(tc, "cac:TaxScheme"), "cbc:ID", "VAT")
        _u(_u(li, "cac:Price"), "cbc:PriceAmount", _uprice(x["price"]), currencyID=cur)
    ET.indent(root, space=" ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8")


def ein_ubl_check(xml_bytes):
    """The Peppol points the EN 16931 Schematron does not cover (list of strings, empty = fine): CustomizationID /
    ProfileID of Peppol BIS 3.0, both electronic addresses with a scheme (in the Peppol profile not EM), BT-10 or BT-13, one note, one tax total with
    subtotals, every amount with a currency, no empty element."""
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return [f"not well-formed: {e}"]
    q = {"cac": UBL_NS["cac"], "cbc": UBL_NS["cbc"]}

    def tx(path):
        x = root.find(path, q)
        return (x.text or "").strip() if x is not None else ""
    peppol = tx("cbc:CustomizationID") == UBL_PROFILES["peppol"]
    if not tx("cbc:CustomizationID").startswith("urn:cen.eu:en16931:2017"):
        out.append("BT-24 CustomizationID")
    if tx("cbc:ProfileID") != EIN_PROCESS:
        out.append("BT-23 ProfileID (PEPPOL-EN16931-R001)")
    for who, path in (("BT-34 seller", "cac:AccountingSupplierParty/cac:Party/cbc:EndpointID"), ("BT-49 buyer", "cac:AccountingCustomerParty/cac:Party/cbc:EndpointID")):
        el = root.find(path, q)
        if el is None or not (el.text or "").strip() or not el.get("schemeID"):
            out.append(f"{who} electronic address with scheme missing (PEPPOL-EN16931-R020 / R010)")
        elif peppol and el.get("schemeID") == "EM":  # 2.446.0 (#3783): the e-mail fallback is not in the Peppol EAS list (XRechnung allows it)
            out.append(f"{who} electronic address: scheme EM is not in the Peppol list (PEPPOL-EN16931-CL008)")
    if not tx("cbc:BuyerReference") and not tx("cac:OrderReference/cbc:ID"):
        out.append("BT-10 buyer reference or BT-13 order reference missing (PEPPOL-EN16931-R003)")
    if len(root.findall("cbc:Note", q)) > 1:
        out.append("more than one note (PEPPOL-EN16931-R002)")
    if len([t for t in root.findall("cac:TaxTotal", q) if t.find("cac:TaxSubtotal", q) is not None]) != 1:
        out.append("exactly one tax total with subtotals (PEPPOL-EN16931-R053)")
    for tc in root.findall("cac:TaxTotal/cac:TaxSubtotal/cac:TaxCategory", q):  # 2.357.0 (#3217, review N3): BR-Z-10 / BR-E-10
        cat, why = tc.findtext("cbc:ID", "", q), tc.findtext("cbc:TaxExemptionReason", "", q) or tc.findtext("cbc:TaxExemptionReasonCode", "", q)
        if cat == "Z" and why:
            out.append("BR-Z-10: zero rated carries no exemption reason")
        if cat == "E" and not why:
            out.append("BR-E-10: exemption reason missing")
    for el in root.iter():
        if len(el) == 0 and not (el.text or "").strip():
            out.append(f"empty element {el.tag.split('}')[-1]} (PEPPOL-EN16931-R008)")
        if el.tag.endswith("Amount") and el.tag.startswith("{" + UBL_NS["cbc"]) and not el.get("currencyID"):
            out.append(f"amount without currency: {el.tag.split('}')[-1]}")
    for ln in root.findall("cac:InvoiceLine", q) + root.findall("cac:CreditNoteLine", q):
        qe = ln.find("cbc:InvoicedQuantity", q)
        qe = qe if qe is not None else ln.find("cbc:CreditedQuantity", q)
        net, price = _d(ln.findtext("cbc:LineExtensionAmount", "", q)), _d(ln.findtext("cac:Price/cbc:PriceAmount", "", q))
        ac = sum((_d(a.findtext("cbc:Amount", "", q)) * (1 if a.findtext("cbc:ChargeIndicator", "", q) == "true" else -1)
                  for a in ln.findall("cac:AllowanceCharge", q)), Decimal("0"))  # 2.523.0 (#4082): line charges / allowances
        if qe is not None and (_d(qe.text) * price).quantize(Q2, rounding=ROUND_HALF_UP) + ac != net:
            out.append(f"line {ln.findtext('cbc:ID', '', q)}: net != quantity x price (PEPPOL-EN16931-R120)")
    return out
