"""2.140.0 B (#2134): the one reader of bank statements -- the household budget (life/budget.py) and the office's bank
reconciliation (office/bank.py) both read their files here; nothing is stored here and nothing goes from one to the other.

  CSV    csv_table (encoding left to the client: UTF-8, windows-1252 fallback; the delimiter and the header row found here:
         bank exports start with a few lines about the account), csv_guess (which column holds what, the decimal separator,
         the date format; a known bank layout of CSV_PRESETS first), csv_mapping (a client's mapping checked against the
         columns), csv_row (one row with a mapping -> day, amount, kind, text, counterpart or a readable error)
  CAMT   camt_is / camt_rows: CAMT.052 / .053 XML (no DOCTYPE / ENTITY, so no entity expansion and no external references);
         2.146.0 C (#2469): camt_rows marks pending entries (Sts not BOOK, e.g. PDNG of a CAMT.052 day report) and keeps both
         references (svc_ref = AcctSvcrRef, e2e = EndToEndId; NOTPROVIDED dropped), camt_version tells 052 from 053
  refs   2.146.0 C (#2469): csv_ref_keys -- the reference keys of a booking (AcctSvcrRef / EndToEndId with the amount), the
         duplicate check across files and imports that also finds a pending booking booked later with another day or text
  dups   csv_dup_take: "two equal rows of one file need two existing ones" -- each caller keeps its own keyed fingerprint
         (budget: per list with the space key, office: per office area), so equal bookings never meet across areas
Limits: CSV_MAX bytes, CSV_ROWS rows; texts are cut and stripped of control characters. A CSV export of what came in goes
through csv_cell (no formulas in spreadsheet programs)."""
import csv
import hashlib
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import safexml  # 2.1272.0 (#6422): the one reader for foreign XML
from .i18n import N_, tr
from ..core.errors import BadInput, BadKey  # 2.369.5 (#2517): pulled up from functions
from .serializers import csv_cell as _cell  # 2.369.5 (#2517): pulled up from functions

CSV_MAX, CSV_ROWS = 2 * 1024 * 1024, 3000
CSV_AMOUNT_MAX = Decimal("10000000")
CSV_TEXT_MAX = 200
CAMT_AMOUNT_MAX = Decimal("100000000")
DATE_FORMATS = {"DD.MM.YYYY": r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "YYYY-MM-DD": r"(\d{4})-(\d{1,2})-(\d{1,2})",
                "DD.MM.YY": r"(\d{1,2})\.(\d{1,2})\.(\d{2})", "MM/DD/YYYY": r"(\d{1,2})/(\d{1,2})/(\d{4})",
                # 2.146.0 C (#2455): two more layouts of bank exports
                "DD-MM-YYYY": r"(\d{1,2})-(\d{1,2})-(\d{4})", "YYYYMMDD": r"(\d{4})(\d{2})(\d{2})",
                "DD/MM/YYYY": r"(\d{1,2})/(\d{1,2})/(\d{4})"}  # 2.355.0 B (#2843): British exports (was read as MM/DD)
# 2.146.0 C (#2455): sign = the column of a debit / credit mark (S/H, Soll/Haben, D/C, -/+) next to an amount without a sign
MAP_KEYS = ("date", "amount", "amount_in", "amount_out", "title", "counterpart", "sign")
SIGN_OUT = frozenset(("s", "soll", "d", "db", "dbit", "debit", "-", "lastschrift", "belastung"))
REF_NONE = frozenset(("NOTPROVIDED", "NONREF", "NOTAVAILABLE", "NONE"))  # 2.146.0 C (#2469): placeholders, no reference
SIGN_IN = frozenset(("h", "haben", "c", "cr", "crdt", "credit", "+", "gutschrift"))
IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{8,30}$")
GUESS = {
    "date": ("buchungstag", "buchungsdatum", "datum", "date", "booking date", "transaction date", "valuta", "wertstellung", "value date"),
    "amount": ("betrag", "amount", "umsatz", "betrag (eur)", "betrag in eur", "value"),
    # 2.146.0 C (#2455): before amount_in / amount_out, so "Soll/Haben" is never taken for one of them
    "sign": ("soll/haben", "s/h", "soll-haben-kennzeichen", "soll/haben-kennzeichen", "soll / haben", "debit/credit", "d/c", "cdtdbtind",
             "sh-kennzeichen", "kennzeichen"),
    "amount_in": ("haben", "gutschrift", "credit", "eingang", "einnahme"),
    "amount_out": ("soll", "lastschrift", "debit", "ausgang", "ausgabe"),
    "title": ("verwendungszweck", "buchungstext", "beschreibung", "description", "purpose", "memo", "reference", "text", "details"),
    "counterpart": ("beguenstigter/zahlungspflichtiger", "begünstigter/zahlungspflichtiger", "zahlungsempfänger", "zahlungsempfaenger",
                    "empfänger", "empfaenger", "auftraggeber", "name", "payee", "counterparty", "gegenseite", "partner"),
}
# Known export layouts (header names as the banks write them, compared like csv_norm). A preset is taken only when EVERY
# column it names is in the header, so another file never matches by accident; it only pre-fills the choice (the person
# checks it like the guess). Without a match the plain guess above decides as before.
CSV_PRESETS = (
    {"id": "sparkasse", "name": "Sparkasse (CSV-CAMT)", "decimal": ",", "date_format": "DD.MM.YY",
     "cols": {"date": "buchungstag", "amount": "betrag", "title": "verwendungszweck", "counterpart": "beguenstigter/zahlungspflichtiger"},
     "also": ("auftragskonto", "valutadatum", "glaeubiger id")},
    {"id": "ing", "name": "ING", "decimal": ",", "date_format": "DD.MM.YYYY",
     "cols": {"date": "buchung", "amount": "betrag", "title": "verwendungszweck", "counterpart": "auftraggeber/empfänger"},
     "also": ("buchungstext", "saldo")},
    {"id": "dkb", "name": "DKB", "decimal": ",", "date_format": "DD.MM.YY",
     "cols": {"date": "buchungsdatum", "amount": "betrag (€)", "title": "verwendungszweck", "counterpart": "zahlungsempfänger*in"},
     "also": ("wertstellung", "zahlungspflichtige*r", "umsatztyp")},
    {"id": "comdirect", "name": "comdirect", "decimal": ",", "date_format": "DD.MM.YYYY",
     "cols": {"date": "buchungstag", "amount": "umsatz in eur", "title": "buchungstext"},
     "also": ("wertstellung (valuta)", "vorgang")},
    # 2.146.0 C (#2455): Volksbank / Raiffeisenbank -- the current export (a signed amount) and the older one: the amount
    # without a sign and the mark S / H in the column right after it (sign_after; its header is often empty)
    {"id": "volksbank", "name": "Volksbank / Raiffeisenbank", "decimal": ",", "date_format": "DD.MM.YYYY",
     "cols": {"date": "buchungstag", "amount": "betrag", "title": "verwendungszweck", "counterpart": "name zahlungsbeteiligter"},
     "also": ("iban zahlungsbeteiligter", "valutadatum")},
    {"id": "volksbank_sh", "name": "Volksbank / Raiffeisenbank (S/H)", "decimal": ",", "date_format": "DD.MM.YYYY", "sign_after": "amount",
     "cols": {"date": "buchungstag", "amount": "umsatz", "title": "vorgang/verwendungszweck", "counterpart": "empfänger/zahlungspflichtiger"},
     "also": ("valuta",)},
)


def _bad(msg):
    return BadInput(msg)


class RowsOver(BadInput):
    """2.1385.0 (#6435): a statement has more rows than its reader may build (max_rows of camt_rows / mt_parse): raised at
    the first row over it, while reading. An import of several files stops at it (not just this file skipped)."""


def rows_over(n):
    return RowsOver(tr("At most {0} rows per import", n))


def csv_norm(s):
    s = unicodedata.normalize("NFKC", s or "").casefold()
    return re.sub(r"\s+", " ", s).strip()


def csv_clean(v, n=CSV_TEXT_MAX):
    """A text of a statement: no control characters, one space between words, at most n characters."""
    v = re.sub(r"[\x00-\x1f\x7f]", " ", v if isinstance(v, str) else "")
    return re.sub(r"\s+", " ", v).strip()[:n]


def csv_cell(s):
    """Free text for a CSV cell of an export (no formulas, core/serializers.csv_cell)."""
    return _cell(s)


def csv_dup_take(counts, key):
    """True (and one existing match used up) when counts still holds key: two equal rows of one file need two existing
    bookings to count as duplicates."""
    if counts.get(key):
        counts[key] -= 1
        return True
    return False


# ---------------------------------------------------------------- the text encoding of an imported file
TXT_NOT_TEXT = N_("This is not a text file")
TXT_CP1252 = N_("The file is not UTF-8 and was read as Windows-1252: please check umlauts and the euro sign")
TXT_UNREADABLE = N_("The text encoding of the file could not be read (UTF-8, UTF-16 or Windows-1252 expected)")


def text_decode(data):
    """Bytes of a text file -> (str, encoding): UTF-8 (with / without BOM), UTF-16 (BOM or detected), else Windows-1252
    (encoding "windows-1252": the caller warns with TXT_CP1252 -- an ISO-8859-15 file shows a wrong euro sign). BadKey
    TXT_NOT_TEXT / TXT_UNREADABLE when it is no text. 2.1324.0 (#6589): moved here from the task import
    (integrations/importers.imp_decode, 2.533.0 #4318 F8), the knowledge import reads its pages with it too."""
    enc = "utf-8"
    try:
        if data.startswith(b"\xef\xbb\xbf"):
            s = data[3:].decode("utf-8")
        elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
            s, enc = data.decode("utf-16"), "utf-16"
        else:
            head = data[:4000]
            if len(head) >= 4 and head.count(b"\x00") > len(head) // 4:
                enc = "utf-16-le" if head[1::2].count(0) > head[0::2].count(0) else "utf-16-be"
                s = data.decode(enc)
            else:
                if b"\x00" in data:
                    raise BadKey(TXT_NOT_TEXT)
                try:
                    s = data.decode("utf-8")
                except UnicodeDecodeError:
                    s, enc = data.decode("cp1252"), "windows-1252"
    except UnicodeDecodeError:
        raise BadKey(TXT_UNREADABLE) from None
    if "\x00" in s:
        raise BadKey(TXT_NOT_TEXT)
    return s.lstrip("\ufeff"), enc


# ---------------------------------------------------------------- CSV
def csv_decode(text, max_bytes=CSV_MAX):
    if not isinstance(text, str):
        raise _bad(tr("Invalid value: {0}", "text"))
    if len(text.encode("utf-8", "ignore")) > max_bytes:
        raise _bad(tr("The file is too large (at most {0} MB)", max_bytes // (1024 * 1024)))
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def csv_delim(lines):
    best, n = ";", -1
    for d in (";", ",", "\t", "|"):
        counts = [ln.count(d) for ln in lines[:30] if ln.strip()]
        if not counts:
            continue
        top = max(set(counts), key=counts.count)
        score = top * counts.count(top) if top else 0
        if score > n:
            best, n = d, score
    return best


def csv_table(text, max_rows=CSV_ROWS):
    """CSV text -> (delimiter, header, rows): the header is the first row with the most common column count (bank
    exports start with a few lines about the account)."""
    return csv_table_numbered(text, max_rows)[:3]


def csv_table_numbered(text, max_rows=CSV_ROWS):
    """csv_table + the spreadsheet row of each body row (2.363.2, #3106: blank rows and lines above the header count there)."""
    text = csv_decode(text)
    lines = text.split("\n")
    d = csv_delim(lines)
    numbered = []
    try:
        for n, r in enumerate(csv.reader(io.StringIO(text), delimiter=d), 1):
            if any(x.strip() for x in r):
                if len(numbered) >= max_rows + 50:  # 2.1385.0 (#6435): stopped at the first row too many, not after all of them
                    raise rows_over(max_rows)
                numbered.append((n, r))
    except csv.Error:
        raise _bad(tr("The file cannot be read as CSV")) from None
    if not numbered:
        raise _bad(tr("The file is empty"))
    nums, rows = zip(*numbered)
    lens = [len(r) for r in rows]
    common = max(set(lens), key=lens.count)
    hi = next(i for i, r in enumerate(rows) if len(r) == common)
    header = [x.strip()[:80] for x in rows[hi]]
    body = [[x.strip() for x in r] for r in rows[hi + 1:]]
    return d, header, body, list(nums[hi + 1:])


class XlNum(str):
    """2.1315.0 (#6590 a): the stored text of a real number cell of a spreadsheet (.xlsx "n", .xls number): always a dot as
    decimal mark, never a thousand separator. The cell type decides, amount_text never guesses it by the text rule ("0.125"
    of a number cell was 125). str() and strip() keep the mark, so the readers' str(cell).strip() pass it on."""
    __slots__ = ()

    def __str__(self):
        return self

    def strip(self, chars=None):
        return self if chars is None else str.strip(self, chars)


def xl_num_value(s):
    """Decimal of an XlNum (also "1.5E-7" and formula results with many decimals) or None."""
    try:
        v = Decimal(str.__str__(s))
    except InvalidOperation:
        return None
    return v if v.is_finite() else None


def amount_text(s, dec=None):
    """2.355.0 B (#2843): the one reader of a typed / exported money amount -> unrounded signed Decimal or None (unreadable,
    never a silent other number). Thousand separators only in groups of three ("1.234,56", "1,234.56", "1'234.56"); dec ","
    or "." is the decimal mark of the file, dec None reads both (German first: "1.500" = 1500, "1.234,5" / "1,234.5" by the
    last mark). A single mark before exactly three digits after at most three ("1,500", "1.234" with the decimal point)
    could be a thousand or three decimals and is unreadable."""
    if isinstance(s, XlNum):  # 2.1315.0 (#6590 a): a number cell is read as stored (dot = decimal), never by the text rule
        return xl_num_value(s)
    s = re.sub(r"[\s\u00a0\u202f]", "", str(s or ""))
    s = re.sub(r"(?i)(eur|€|\$|usd|chf|£)", "", s)
    if not s:
        return None
    neg = False
    if s.endswith("-"):
        neg, s = True, s[:-1]
    elif s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if dec is None:
        last = max(s.rfind(","), s.rfind("."))
        if last < 0:
            dec = ","
        elif "," in s and "." in s:
            dec = s[last]
        elif s.count(s[last]) > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):
            dec = "," if s[last] == "." else "."  # repeated = thousands; "1.500" = 1500 (German first)
        else:
            dec = s[last]
    grp = "[.']" if dec == "," else "[,']"
    m = re.fullmatch(rf"(\d{{1,3}}(?:{grp}\d{{3}})+|\d{{1,12}})(?:{re.escape(dec)}(\d{{1,10}}))?", s)
    if not m or (m.group(2) and len(m.group(2)) == 3 and len(m.group(1)) <= 3):
        return None  # "1,500" / "1.234" with that decimal mark: a thousand or three decimals -- never guessed
    v = Decimal(re.sub(r"\D", "", m.group(1)) + ("." + m.group(2) if m.group(2) else ""))
    return -v if neg else v


def csv_amount(s, dec):
    """'1.234,56' / '-12,30' / '12,30-' / '12.30' / '(12.30)' -> signed Decimal or None. 2.355.0 B (#2843): read by
    amount_text (thousand separators only in groups of three, else unreadable -- "1,234.5" with the decimal comma was
    1,23), rounded half up like CAMT."""
    v = amount_text(s, dec)
    if v is None or abs(v) >= 10 ** 9:
        return None
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def csv_day(s, fmt):
    m = re.fullmatch(DATE_FORMATS[fmt], (s or "").strip())
    if not m:
        return None
    a, b_, y = m.groups()
    if fmt in ("YYYY-MM-DD", "YYYYMMDD"):  # 2.146.0 C (#2455): YYYYMMDD
        y, a, b_ = a, b_, y
        dd, mm = int(b_), int(a)
    elif fmt == "MM/DD/YYYY":
        dd, mm = int(b_), int(a)
    else:
        dd, mm = int(a), int(b_)
    yy = int(y) + (2000 if len(y) == 2 else 0)
    try:
        return date(yy, mm, dd).isoformat()
    except ValueError:
        return None


def csv_preset(header):
    """The first preset of CSV_PRESETS whose columns are all in header -> (preset, {field: column}) or (None, None)."""
    low = [csv_norm(h) for h in header]
    for p in CSV_PRESETS:
        names = list(p["cols"].values()) + list(p["also"])
        if all(n in low for n in names):
            cols = {k: low.index(n) for k, n in p["cols"].items()}
            if p.get("sign_after"):  # 2.146.0 C (#2455): the mark column right after the amount
                i = cols[p["sign_after"]] + 1
                if i >= len(header):
                    continue
                cols["sign"] = i
            return p, cols
    return None, None


def _plain_guess(header, body):
    low = [csv_norm(h) for h in header]
    g_ = {}
    for k, names in GUESS.items():
        g_[k] = None
        for n in names:
            hit = next((i for i, h in enumerate(low) if h == n and i not in g_.values()), None)
            if hit is None:
                hit = next((i for i, h in enumerate(low) if n in h and i not in g_.values()), None)
            if hit is not None:
                g_[k] = hit
                break
    if g_["amount"] is not None:
        g_["amount_in"] = g_["amount_out"] = None
    # 2.146.0 C (#2455): a mark column only next to one amount column and when it holds marks; an unnamed column right
    # after the amount holding S / H is one too (older Volksbank / Postbank exports)
    if g_["sign"] is not None and (g_["amount"] is None or not _sign_col(body, g_["sign"])):
        g_["sign"] = None
    if g_["sign"] is None and g_["amount"] is not None and g_["amount"] + 1 < len(header) and g_["amount"] + 1 not in g_.values() \
            and _sign_col(body, g_["amount"] + 1):
        g_["sign"] = g_["amount"] + 1
    sample = [r for r in body[:50]]
    cols = [g_[k] for k in ("amount", "amount_in", "amount_out") if g_[k] is not None]
    vals = [r[i] for r in sample for i in cols if i < len(r) and r[i]]
    commas = sum(1 for v in vals if re.search(r",\d{1,2}-?$", v))
    dots = sum(1 for v in vals if re.search(r"\.\d{1,2}-?$", v))
    g_["decimal"] = "." if dots > commas else ","
    fmt = "DD.MM.YYYY"
    if g_["date"] is not None:
        ds = [r[g_["date"]] for r in sample if g_["date"] < len(r) and r[g_["date"]]]
        fmt = _day_fmt(ds, DATE_FORMATS) or fmt
    g_["date_format"] = fmt
    return g_


def _day_fmt(ds, fmts):
    """2.355.0 B (#2843): the format reading the most of ds (at least 80 %); a tie goes to the day first (DD/MM before
    MM/DD: 03/04/2026 is the 3rd of April unless a day above 12 says otherwise)."""
    hits = {f: sum(1 for x in ds if csv_day(x, f)) for f in fmts}
    best = max(hits.values(), default=0)
    if not ds or best < max(1, len(ds) * 0.8):
        return None
    pick = [f for f in fmts if hits[f] == best]
    return "DD/MM/YYYY" if "DD/MM/YYYY" in pick else pick[0]


def csv_guess(header, body):
    """{date, amount, amount_in, amount_out, title, counterpart, decimal, date_format, preset, preset_name}: a known layout
    (csv_preset; its date format only when the sample reads with it) or the plain guess (preset None)."""
    g_ = _plain_guess(header, body)
    p, cols = csv_preset(header)
    g_["preset"] = g_["preset_name"] = None
    if p:
        for k in MAP_KEYS:
            g_[k] = cols.get(k)
        g_["decimal"] = p["decimal"]
        ds = [r[cols["date"]] for r in body[:50] if cols["date"] < len(r) and r[cols["date"]]]
        if not ds or sum(1 for x in ds if csv_day(x, p["date_format"])) >= max(1, len(ds) * 0.8):
            g_["date_format"] = p["date_format"]
        else:
            g_["date_format"] = _day_fmt(ds, DATE_FORMATS) or g_["date_format"]
        g_["preset"], g_["preset_name"] = p["id"], p["name"]
    return g_


def csv_hkey(header):
    """The fingerprint of a header (a remembered mapping per layout)."""
    return hashlib.sha256("\x1f".join(csv_norm(h) for h in header).encode()).hexdigest()[:24]


def csv_mapping(m, ncols):
    """A client's mapping, checked against the number of columns."""
    if not isinstance(m, dict):
        raise _bad(tr("Invalid value: {0}", "mapping"))
    out = {}
    for k in MAP_KEYS:
        v = m.get(k)
        if v is None:
            out[k] = None
            continue
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < ncols:
            raise _bad(tr("Invalid value: {0}", k))
        out[k] = v
    if out["date"] is None or (out["amount"] is None and out["amount_in"] is None and out["amount_out"] is None):
        raise _bad(tr("Please select the columns for the date and the amount"))
    if out["title"] is None and out["counterpart"] is None:
        raise _bad(tr("Please select the column for the text"))
    out["decimal"] = m.get("decimal") if m.get("decimal") in (",", ".") else ","
    out["date_format"] = m.get("date_format") if m.get("date_format") in DATE_FORMATS else "DD.MM.YYYY"
    return out


def csv_row(r, m, title_max=CSV_TEXT_MAX, cp_max=CSV_TEXT_MAX, amount_max=CSV_AMOUNT_MAX):
    """One CSV row with mapping m -> {day, amount (positive float), kind out | in, title, counterpart, error}."""
    def col(k):
        i = m.get(k)
        return r[i] if i is not None and i < len(r) else ""
    out = {"day": None, "amount": None, "kind": "out", "title": "", "counterpart": col("counterpart")[:cp_max], "error": None}
    out["day"] = csv_day(col("date"), m["date_format"])
    amt = None
    if m.get("amount") is not None:
        amt = csv_amount(col("amount"), m["decimal"])
        if m.get("sign") is not None and amt is not None:  # 2.146.0 C (#2455): the mark decides, the amount's own sign does not
            mark = csv_sign(col("sign"))
            amt = None if mark is None else abs(amt) * mark
    else:
        a_in = csv_amount(col("amount_in"), m["decimal"]) if m.get("amount_in") is not None else None
        a_out = csv_amount(col("amount_out"), m["decimal"]) if m.get("amount_out") is not None else None
        if a_in:
            amt = a_in  # 2.355.0 B (#2843): "-50,00" in the credit column is -50 (a return), never +50
        elif a_out:  # the debit column: written with or without a minus, always out
            amt = -abs(a_out)
    title = (col("title") or col("counterpart")).strip()
    full = re.sub(r"\s+", " ", title)
    out["title"] = full[:title_max]
    if len(full) > title_max:
        out["cut"] = True  # 2.363.3 (#3134): the import dialog says so
    if out["day"] is None:
        out["error"] = tr("The date cannot be read")
    elif m.get("sign") is not None and m.get("amount") is not None and amt is None and csv_sign(col("sign")) is None:
        out["error"] = tr("The debit / credit mark cannot be read")
    elif amt is None or amt == 0 or abs(amt) > amount_max:
        out["error"] = tr("The amount cannot be read")
    elif not out["title"]:
        out["error"] = tr("The row has no text")
    if amt is not None and amt != 0:
        out["amount"], out["kind"] = float(abs(amt).quantize(Decimal("0.01"))), "out" if amt < 0 else "in"
    return out


def csv_sign(v):
    """2.146.0 C (#2455): a debit / credit mark -> -1 (S, Soll, D, Debit, -), 1 (H, Haben, C, Credit, +) or None."""
    v = csv_norm(v).strip(" .")
    return -1 if v in SIGN_OUT else 1 if v in SIGN_IN else None


def _sign_col(body, i):
    """2.146.0 C (#2455): column i holds debit / credit marks (at least 80 % of the filled cells of the sample)."""
    vals = [r[i] for r in body[:50] if i < len(r) and r[i].strip()]
    return bool(vals) and sum(1 for v in vals if csv_sign(v) is not None) >= max(1, len(vals) * 0.8)


def csv_iban_col(header):
    """2.146.0 C (#2455): the column of the counterpart's IBAN -- a column named IBAN; one of the own account (Auftragskonto,
    eigene ...) only when there is no other."""
    cols = [i for i, h in enumerate(header) if "iban" in (h or "").casefold()]
    other = [i for i in cols if not any(w in (header[i] or "").casefold() for w in ("auftragskonto", "eigen", "own account"))]
    return (other or cols or [None])[0]


# 2.1315.0 (#6590 d): the currency of a CSV statement's row -- a column named so (read by its name, no mapping needed) or a
# code / sign in the amount cell ("12,50 USD", "$12.50"). amount_text drops those marks, so a caller that books in one
# currency compares this with its own and refuses another one, never books it silently as its own.
CUR_HEAD = ("währung", "waehrung", "whg", "whg.", "currency", "ccy", "devise", "divisa", "munt")
CUR_SIGN = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY", "₣": "CHF"}


def csv_currency_col(header):
    """The column of the currency (by its name) or None."""
    return next((i for i, h in enumerate(header) if (h or "").strip().casefold() in CUR_HEAD), None)


def csv_currency(text):
    """'EUR' / 'usd' / '€' / '12,50 USD' / '$12.50' -> the ISO code, '' when the text names none."""
    s = str(text or "").strip()
    m = re.search(r"(?<![A-Za-z])([A-Za-z]{3})(?![A-Za-z])", s)
    if m:
        return m.group(1).upper()
    return next((v for k, v in CUR_SIGN.items() if k in s), "")


# ---------------------------------------------------------------- CAMT.052 / .053
# 2.1272.0 (#6422): a statement is read by core/safexml.py (callers cap the file far below CAMT_BYTES_MAX; an entry has
# about 60 elements)
CAMT_BYTES_MAX = 64 * 1024 * 1024
CAMT_ELEMENTS_MAX = 1_000_000
CAMT_DEPTH_MAX = 64


def camt_tree(text):
    """The root element of a CAMT text: XmlRefused (NUL, DOCTYPE / ENTITY, too large) or ET.ParseError. The client sends
    text (UTF-8, cp1252 fallback); the reader drops the XML declaration, whose encoding no longer holds."""
    return safexml.sx_tree(text, max_bytes=CAMT_BYTES_MAX, max_elements=CAMT_ELEMENTS_MAX, max_depth=CAMT_DEPTH_MAX)


def camt_is(text):
    head = (text or "")[:4000]
    return "<Document" in head and "camt.05" in head


def camt_version(text):
    """2.146.0 C (#2469): "052" (account report, intraday: pending entries), "053" (statement), "054" or "" from the namespace."""
    m = re.search(r"camt\.(05[234])\.", (text or "")[:4000])
    return m.group(1) if m else ""


def csv_ref_parts(row):
    """2.146.0 C (#2469): the reference parts of a booking for the duplicate check across files and imports: the bank's
    reference (AcctSvcrRef) and the EndToEndId, each with the signed amount (a reference alone is not always unique: an
    EndToEndId may come back every month). Each caller keys them (HMAC) for its area -- they are never stored plain.
    2.355.0 B (#2843): with a day in row the EndToEndId part carries it too ("e|<id>|<amount>|<day>": a fixed EndToEndId of a
    standing order with the same amount every month is a new booking each month); csv_ref_legacy gives the old form."""
    amt = row.get("amount")
    if amt is None:
        return []
    a = str(_money(Decimal(str(amt))))
    out = []
    for tag, k in (("a", "svc_ref"), ("e", "e2e")):
        v = (row.get(k) or "").strip()
        if v and v.upper() not in REF_NONE:
            out.append(f"{tag}|{v}|{a}|{row['day']}" if tag == "e" and row.get("day") else f"{tag}|{v}|{a}")
    # 2.1315.0 (#6590 d): a position of a batch booking also carries the entry's reference with the entry's total -- the key
    # the whole entry had as one row before (stored that way, it keeps finding the entry: no position comes twice)
    bt = row.get("batch")
    if bt and bt[0] and bt[0].strip().upper() not in REF_NONE:
        out.append(f"a|{bt[0].strip()}|{_money(Decimal(str(bt[1])))}")
    return out


def csv_ref_legacy(row):
    """2.355.0 B (#2843): the EndToEndId part without the day, as stored before 2.355 (matched only with a booking of the
    same day, never rewritten)."""
    return [x.rsplit("|", 1)[0] for x in csv_ref_parts(row) if x.startswith("e|") and row.get("day")]


def camt_local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def camt_kids(el, name):
    return [x for x in el if camt_local(x.tag) == name]


def camt_kid(el, *path):
    for name in path:
        if el is None:
            return None
        el = next((x for x in el if camt_local(x.tag) == name), None)
    return el


def camt_txt(el, *path):
    el = camt_kid(el, *path)
    return (el.text or "").strip() if el is not None and el.text else ""


def _camt_day(el):
    if el is None:
        return None
    v = camt_txt(el, "Dt") or camt_txt(el, "DtTm")[:10]
    try:
        return date.fromisoformat(v[:10]).isoformat() if v else None
    except ValueError:
        return None


def _money(d):
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _camt_tx(row, tx, credit, text_max):
    """The texts, counterpart, IBAN and references of one TxDtls into row."""
    purpose = [(x.text or "").strip() for x in camt_kids(camt_kid(tx, "RmtInf") if camt_kid(tx, "RmtInf") is not None else tx, "Ustrd")]
    row["purpose"] = csv_clean(" ".join(p for p in purpose if p), text_max)
    pts = camt_kid(tx, "RltdPties")
    if pts is not None:
        side, acct = ("Dbtr", "DbtrAcct") if credit else ("Cdtr", "CdtrAcct")
        p = camt_kid(pts, side)
        if p is not None:
            row["counterpart"] = csv_clean(camt_txt(p, "Nm") or camt_txt(p, "Pty", "Nm"), 200)
        iban = camt_txt(pts, acct, "Id", "IBAN").replace(" ", "").upper()
        row["iban"] = iban if IBAN_RE.match(iban) else None
    if not row["ref"]:
        row["ref"] = csv_clean(camt_txt(tx, "Refs", "AcctSvcrRef") or camt_txt(tx, "Refs", "EndToEndId"), 120) or None
    if row["ref"] == "NOTPROVIDED":
        row["ref"] = None
    row["svc_ref"] = row["svc_ref"] or csv_clean(camt_txt(tx, "Refs", "AcctSvcrRef"), 120) or None
    e2e = csv_clean(camt_txt(tx, "Refs", "EndToEndId"), 120)
    row["e2e"] = e2e if e2e and e2e.upper() != "NOTPROVIDED" else None


def _camt_positions(txs, credit, total):
    """2.1315.0 (#6590 d): [(signed amount, credit)] of the positions of a batch booking, or None when one names no readable
    amount or they do not add up to the entry's signed total (then the entry stays one row)."""
    out = []
    for tx in txs:
        el = next((x for x in (camt_kid(tx, "Amt"), camt_kid(tx, "AmtDtls", "TxAmt", "Amt"), camt_kid(tx, "AmtDtls", "InstdAmt", "Amt"))
                   if x is not None), None)  # an Element without children is falsy: no "or" here
        try:
            a = Decimal((el.text or "").strip()) if el is not None else None
        except (ArithmeticError, ValueError):
            a = None
        if a is None or not a.is_finite() or not 0 < a <= CAMT_AMOUNT_MAX or _money(a) == 0:
            return None
        ind = camt_txt(tx, "CdtDbtInd")
        cr = (ind == "CRDT") if ind in ("CRDT", "DBIT") else credit
        out.append((_money(a if cr else -a), cr))
    return out if sum(x for x, _c in out) == total else None


def camt_rows(text, text_max=300, max_rows=None):
    """CAMT.052 / .053 XML -> [{day, amount (signed Decimal), currency, counterpart, purpose, iban, ref, error}]. Documents
    with a DOCTYPE or an ENTITY are refused by the reader (camt_tree: no entity expansion, no external references).
    2.1385.0 (#6435): max_rows: RowsOver at the first row over it, while reading (was: counted after every row was built)."""
    try:
        root = camt_tree(text)
    except safexml.XmlRefused as e:
        if e.reason in ("nul", "dtd"):
            raise _bad(tr("The file contains a DOCTYPE or an ENTITY and is not read")) from None
        raise _bad(tr("The file cannot be read as CAMT")) from None
    except (ET.ParseError, ValueError):
        raise _bad(tr("The file cannot be read as CAMT")) from None
    out = []
    for ntry in root.iter():
        if camt_local(ntry.tag) != "Ntry":
            continue
        if max_rows is not None and len(out) >= max_rows:  # 2.1385.0 (#6435): one more entry = at least one row too many
            raise rows_over(max_rows)
        amt_el = camt_kid(ntry, "Amt")
        row = {"day": _camt_day(camt_kid(ntry, "BookgDt")) or _camt_day(camt_kid(ntry, "ValDt")), "amount": None,
               "currency": ((amt_el.get("Ccy") if amt_el is not None else "") or "").upper()[:3], "counterpart": "", "purpose": "",
               "iban": None, "ref": csv_clean(camt_txt(ntry, "AcctSvcrRef"), 120) or None, "error": None,
               # 2.146.0 C (#2469): Sts (BOOK / PDNG / INFO; camt.052.001.08+: Sts/Cd) -- only booked entries count, an entry
               # without a status (older files) is booked
               "status": (camt_txt(ntry, "Sts", "Cd") or camt_txt(ntry, "Sts")).upper()[:4], "svc_ref": None, "e2e": None}
        row["pending"] = bool(row["status"]) and row["status"] != "BOOK"
        row["svc_ref"] = row["ref"]
        credit = camt_txt(ntry, "CdtDbtInd") == "CRDT"
        try:
            a = Decimal((amt_el.text or "").strip()) if amt_el is not None else None
        except (ArithmeticError, ValueError):
            a = None
        if a is not None and a.is_finite() and 0 < a <= CAMT_AMOUNT_MAX and _money(a) != 0:  # 0.004 -> 0.00 = unreadable
            row["amount"] = _money(a if credit else -a)
        # 2.1315.0 (#6590 d): a batch booking (Sammelbuchung) carries one TxDtls per position: every position is a row of its own
        # when each names its amount and they add up to the entry; else one row with every position's text (was: the first only)
        txs = [t for nd in camt_kids(ntry, "NtryDtls") for t in camt_kids(nd, "TxDtls")]
        parts = _camt_positions(txs, credit, row["amount"]) if len(txs) > 1 and row["amount"] is not None and row["day"] else None
        if parts:
            total, svc = row["amount"], row["svc_ref"]
            for tx, (amt, cr) in zip(txs, parts):
                pos = dict(row, amount=amt, ref=None, svc_ref=None, e2e=None, batch=(svc, total) if svc else None)
                _camt_tx(pos, tx, cr, text_max)
                pos["purpose"] = pos["purpose"] or csv_clean(camt_txt(ntry, "AddtlNtryInf"), text_max)
                out.append(pos)
            continue
        for k, tx in enumerate(txs):
            if k == 0:
                _camt_tx(row, tx, credit, text_max)
                continue
            more = dict(row, purpose="", counterpart="")  # the other positions' texts join the one row
            _camt_tx(more, tx, credit, text_max)
            row["purpose"] = csv_clean(" · ".join(x for x in (row["purpose"], more["counterpart"], more["purpose"]) if x), text_max)
        if not row["purpose"]:
            row["purpose"] = csv_clean(camt_txt(ntry, "AddtlNtryInf"), text_max)
        if row["day"] is None:
            row["error"] = tr("The date cannot be read")
        elif row["amount"] is None:
            row["error"] = tr("The amount cannot be read")
        out.append(row)
    if max_rows is not None and len(out) > max_rows:  # the positions of the last batch booking
        raise rows_over(max_rows)
    if not out:
        raise _bad(tr("The file contains no bookings"))
    return out
