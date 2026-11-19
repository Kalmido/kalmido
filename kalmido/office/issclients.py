"""2.1384.0 (#6700): the clients of an invoice issuer (office/issuers.py) -- set up and changed by its key through the outside
system's own id of the client (external_ref), never anybody else's.

    PUT /api/v1/issuer/clients/by-ref/<external_ref>   {name, name_extra?, street?, address_extra?, zip?, city?, country?, vat_id?,
                                                        email_invoice?, buyer_reference?, doc_lang?, expect_updated_at?}
                                                        -> 201 set up / 200 changed or unchanged: the client (ISC_PUBLIC) + flags
    GET /api/v1/issuer/clients/by-ref/<external_ref>   -> the client (ISC_PUBLIC)

Rules (the design's section 2.4 "Clients", decided 16.11.2026 and 17.11.2026):
  - external_ref: [A-Za-z0-9._:-]{1,64} (a slash or anything else 400 invalid_field); a platform keeps a fixed prefix of its
    environment in it ("prod:account:12"), for good. Unique per issuer (clients.issuer_id, UNIQUE (issuer_id, external_ref)).
  - The fields are a fixed list (ISC_FIELDS, each with its length); an unknown one 400 unknown_field. name = the name of the
    invoice's recipient, also the name of a person: there is no check for names of persons. customer_no stays empty (a person
    sets it in the office). No address as free text, no note, no rate, no Peppol id.
  - Texts with an IBAN form, a web address or an e-mail address are refused (400 invalid_field) in every text field; in name /
    name_extra a web or e-mail pattern only flags text_suspicious (companies are called "Booking.com B.V."), an IBAN stays 400.
    #7113 (review F9): checked after NFKC and without control / format characters (isc_norm, also what is stored); an IBAN with
    any separator or letters before it (check digits), a web address with any ending (isc_has_web); a VAT ID only of letters,
    digits and + * . -.
  - The country of a VAT ID must fit the client's country (Greece = EL, Monaco = FR; Northern Ireland XI for GB), else 400
    invalid_field vat_id. A VAT ID is optional (also for German buyers; never the buyer's tax number).
  - A change needs expect_updated_at (this route insists itself, ow_write asks it of agents only): 400 version_required
    without (a repeated PUT that changes nothing answers 200 without it: a queue's retry of the set-up), 409 conflict with the
    current client when a person changed it meanwhile.
  - Only the issuer's own clients (issuer_id filter in every query, row-level security lets private clients of every person
    through): another client with the same external_ref, the same name or VAT ID is never taken over or merged (404 / a new
    client); a client in the office's trash 409 client_trashed; anonymised, deleted for good or merged away 410 client_gone
    (the external_ref stays a tombstone in office_issuer_refs, route "clients": a PUT never fills in deleted personal data).
  - The write: the office's write layer ow_write (lock, version, only the fields sent, history) with the actor
    "issuer:<id>" (obj_history.via): its entries never merge, a change and its change back are two entries. A set-up: the
    history's "create" entry. Every set-up and every change of a held field (office/isshold.py IHD_FIELDS) sets the hold
    mark; the flags client_new (set up now), client_lookalike (name or VAT ID of another client of the area), text_suspicious.
    The key's answer names client_new and text_suspicious only (its own input); client_lookalike is for the persons in the
    mark (review F2: else a key could ask whether the office knows a name or VAT ID).
  - day_clients new clients within 24 hours (rolling, counted by the tombstones), else 429 limit_reached (an alarm, no pause);
    likewise ISC_DAY_CHANGES changes of its clients within 24 hours (review F6: the office log is never pruned).
  - A personal office: the client is the owner's private client (org_id NULL, created_by = the owner, else it would not show
    in the own office); an organisation: org_id = the area, created_by empty.
  - Log: every writing PUT one line issuer_write (the fields old -> new); reads and unchanged PUTs one line issuer_read per issuer
    and hour, target "clients" (#7113, review F12: per client it grew with the number of clients, the office log is never pruned).
    Alarm "client data changed" to the admins of the area, by e-mail as well, once a day."""
import json
import re
import unicodedata
from datetime import timedelta

from flask import g, jsonify, request

from ..api.common import v1_err, v1_view
from ..collab.integfail import INTEG_TEXT
from ..core.access import live_sql
from ..core.config import app
from ..core.conflict import Conflict
from ..core.db import bump, iso, iso_ms, now_utc
from ..core.errors import BadInput, Denied, UnknownFields
from ..core.i18n import N_, tr
from ..core.pg import insert_id, system_ctx, write_lock
from ..notify.alerts import fx2_mask_ip
from ..accounts.session import client_ip
from .countries import fk_vat_prefix
from .isshold import IHD_FIELDS, ihd_load
from .ledger import _iban_ok  # #7113 (review F9): the office's IBAN check (mod 97)
from .issuers import _iss_me, _iss_once, _iss_read_logged, iss_log, iss_tell, ISS_ROUTES
from .model import pb_cl_sql, pb_owner
from ..team.clients import clean_client
from .owrite import ow_created, ow_write

ISC_RULE = "/api/v1/issuer/clients/by-ref/<path:ref>"
ISS_ROUTES.update({("PUT", ISC_RULE), ("GET", ISC_RULE)})
ISC_REF_RE = re.compile(r"[A-Za-z0-9._:-]{1,64}")
# the fields a key sets: column -> highest length (the client's own limits, team/clients.py CLIENT_TEXT_MAX / CLIENT_BILLING_MAX)
ISC_FIELDS = {"name": 80, "name_extra": 120, "street": 200, "address_extra": 200, "zip": 20, "city": 120, "country": 2, "vat_id": 20,
              "email_invoice": 200, "buyer_reference": 60, "doc_lang": 5}
ISC_FLAG_ONLY = ("name", "name_extra")  # a web / mail pattern here flags text_suspicious (an IBAN form stays 400)
ISC_NO_TEXT_CHECK = ("country", "vat_id", "email_invoice", "doc_lang")  # own formats, checked by the client's cleaner
ISC_BODY_MAX = 64 * 1024
ISC_REF_ROUTE = "clients"  # office_issuer_refs.route of a client's tombstone
ISC_PUBLIC = ("external_ref", *ISC_FIELDS)
ISC_KEY_FLAGS = ("client_new", "text_suspicious")  # review F2: what the key hears of the mark - only its own input
# an IBAN form: two letters, two check digits, 11 to 30 letters / digits (spaces allowed between), at least 8 digits in it
ISC_IBAN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}[0-9]{2}(?:[ ]?[A-Za-z0-9]){11,30}(?![A-Za-z0-9])")
# #7113 (review F9): and an IBAN anywhere in the letters and digits of a text, whatever stands between or before them
# ("DE89-3704-...", "DE89.3704...", "IBANDE89...", "DE 89 3704..."): the country's IBAN length and the check digits
# (office/ledger.py _iban_ok, mod 97) keep a street with house numbers out of it
ISC_IBAN_LEN = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22, "BI": 27, "BR": 29, "BY": 28, "CH": 21,
    "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DJ": 27, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24, "FI": 18, "FK": 18, "FO": 18,
    "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IQ": 23, "IS": 26,
    "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LC": 32, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "LY": 25, "MC": 27, "MD": 24,
    "ME": 22, "MK": 19, "MN": 20, "MR": 27, "MT": 31, "MU": 30, "NI": 28, "NL": 18, "NO": 15, "OM": 23, "PK": 24, "PL": 28, "PS": 29,
    "PT": 25, "QA": 29, "RO": 24, "RS": 22, "RU": 33, "SA": 24, "SC": 31, "SD": 18, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "SO": 23,
    "ST": 25, "SV": 28, "TL": 23, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20, "YE": 30}
# characters that print as nothing (fillers) besides the formats (Cf) and enclosing marks (Me)
ISC_INVISIBLE = frozenset("\u034f\u115f\u1160\u17b4\u17b5\u180e\u2800\u3164\uffa0")
ISC_MAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}")
# #7113 (review F9): a web address with any ending (evil.finance, pay.evil.sh, evil.example; letters of every script, punycode):
# a scheme, www., or labels joined by dots without a space. The common endings below only decide the abbreviations: a name with
# one of them is a web address whatever stands before the dot (x.com); with another ending, an abbreviation or a single
# letter before it is none ("St.Gallen", "Co.KG", "z.Hd.").
ISC_TLDS = ("com|net|org|info|biz|io|de|at|ch|eu|co|uk|fr|it|es|nl|be|pl|ru|cn|us|me|ly|app|xyz|top|link|shop|online|site|"
            "store|click|live|page|dev|ai|tv|cc|ws|to|gg|li|lu")
ISC_TLD_SET = frozenset(ISC_TLDS.split("|"))
ISC_ABBR = frozenset("st ste sta str dr nr no co fa hd zhd geb bzw ca inh ing dipl prof abt whg og eg ug kg ag gbr mbh".split())
ISC_SCHEME_RE = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]{1,15}://|www\.)")
ISC_HOST_RE = re.compile(r"(?<![\w.-])[^\W_][\w-]{0,62}(?:\.[^\W_][\w-]{0,62})*\.(?:[^\W\d_]{2,24}|xn--[a-z0-9-]{2,59})(?![\w-])", re.I)
ISC_VAT_RE = re.compile(r"[A-Z0-9+*.-]*")  # #7113 (review F9): a VAT ID's letters, digits, + * . (Ireland) and - (Swiss UID)


def isc_norm(v):
    """#7113 (review F9): a text of the key as it is checked and stored: NFKC (full-width letters, ligatures), no control or
    format characters (zero-width, bidi marks, \\u0000: an IBAN split by them passed the check and showed whole; a NUL ended in a
    500), white space as one space."""
    v = unicodedata.normalize("NFKC", v or "")
    v = re.sub(r"\s+", " ", v)
    v = "".join(ch for ch in v if unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co"))
    return re.sub(r" {2,}", " ", v).strip()


# #7144 (Fable reader job/5472 F6): Cyrillic / Greek letters that print like Latin ones (NFKC keeps them) count as those
ISC_LOOKALIKE = str.maketrans(dict(zip(
    "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0425\u0423\u0406\u0408\u0405\u051a\u051c"
    "\u0430\u0435\u043e\u0440\u0441\u0445\u0443\u0456\u0458\u0455\u04bb\u0501\u051b\u051d\u043a"
    "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7"
    "\u03bf\u03bd\u03b9\u03ba\u03b1",
    "ABEKMHOPCTXYIJSQW" "aeopcxyijshdqwk" "ABEZHIKMNOPTYX" "ovika")))
# and in a second look O / I / L for 0 / 1 / 1 -- only in a stretch that has at least ISC_FOLD_DIGITS real digits (an address
# with a few house numbers stays out of it)
ISC_DIGITLIKE = str.maketrans("OIL", "011")
ISC_FOLD_DIGITS = 10


def isc_has_iban(v):
    """An IBAN form (ISC_IBAN_RE) or a valid IBAN in the letters and digits of v (any separator, anything before it; #7144:
    Cyrillic / Greek look-alike letters, O / I / L for digits)."""
    v = v.translate(ISC_LOOKALIKE)
    if any(sum(ch.isdigit() for ch in m.group(0)) >= 8 for m in ISC_IBAN_RE.finditer(v)):
        return True
    s = re.sub(r"[^A-Z0-9]", "", v.upper())
    f = s.translate(ISC_DIGITLIKE)
    for i in range(len(s) - 14):
        n = ISC_IBAN_LEN.get(s[i:i + 2])
        if not n or i + n > len(s):
            continue
        if s[i + 2:i + 4].isdigit() and _iban_ok(s[i:i + n]):
            return True
        w = s[i:i + 2] + f[i + 2:i + n]
        if w != s[i:i + n] and w[2:4].isdigit() and sum(ch.isdigit() for ch in s[i:i + n]) >= ISC_FOLD_DIGITS and _iban_ok(w):
            return True
    return False


def isc_has_web(v):
    """A scheme, www. or a host name with any ending (ISC_HOST_RE; abbreviations of other endings aside, ISC_ABBR)."""
    if ISC_SCHEME_RE.search(v):
        return True
    for m in ISC_HOST_RE.finditer(v):
        labels = m.group(0).lower().split(".")
        tld, sld = labels[-1], labels[-2]
        if tld in ISC_TLD_SET or tld.startswith("xn--") or (len(sld) >= 2 and sld not in ISC_ABBR):
            return True
    return False


INTEG_TEXT.update({
    "issuer_client": N_("Invoice issuer {0} set up or changed the client data of {1}. Check them at the client before you send to it."),
    "issuer_limit": N_("Invoice issuer {0} reached its limit: {1}."),
})
ISC_LIMIT_CLIENTS = N_("new clients within 24 hours")
ISC_LIMIT_CHANGES = N_("changes of clients within 24 hours")
ISC_MAIL_CLIENT = N_("one of its clients")  # #7113 (review F10): the security mail names no client (its name is the key's text)
# review F6: changes of its clients a key makes within 24 hours (rolling). Each is a line of the office log, which is never
# pruned, and a history entry that never merges; 60 calls a minute alone would allow ~86,000 a day. A constant, no limit an
# admin sets (no column): a platform with more changes a day asks for a higher one.
ISC_DAY_CHANGES = 200


def _bad(field, msg=None):
    e = BadInput(msg or tr("Invalid value: {0}", field))
    e.v1 = {"name": "invalid_field", "field": field}
    return e


def _fail(code, msg, name, headers=None, **extra):
    e = Denied(code, msg)
    e.v1_name, e.v1_extra = name, extra
    e.headers = headers or {}
    return e


def _ref(ref):
    if not isinstance(ref, str) or not ISC_REF_RE.fullmatch(ref):
        raise _bad("external_ref", tr("external_ref: 1 to 64 letters, digits or . _ : - (no slash)"))
    return ref


def isc_text_check(field, v):
    """'' / 'suspicious' for value v of field (normalised by isc_norm), or BadInput invalid_field (an IBAN form, a web or an
    e-mail address). A VAT ID: its own characters (ISC_VAT_RE) and no web address."""
    if not v:
        return ""
    if any(unicodedata.category(ch) in ("Cf", "Me") or ch in ISC_INVISIBLE for ch in v):  # (#6701, review F3): invisible / direction marks hide what is printed
        raise _bad(field, tr("{0}: no invisible characters", field))
    w = unicodedata.normalize("NFKC", v)  # (#6701): full-width letters and dots count as the plain ones
    if field == "vat_id":
        if not ISC_VAT_RE.fullmatch(v.replace(" ", "").upper()) or isc_has_web(v):
            raise _bad(field, tr("{0}: letters, digits and + * . - only", field))
        return ""
    if field in ISC_NO_TEXT_CHECK:
        return ""
    if isc_has_iban(w):
        raise _bad(field, tr("{0}: no bank account (IBAN) in the client's data", field))
    if isc_has_web(w) or ISC_MAIL_RE.search(w):
        if field in ISC_FLAG_ONLY:
            return "suspicious"
        raise _bad(field, tr("{0}: no web or e-mail address in the client's data", field))
    return ""


def isc_body():
    """The request's JSON object: at most ISC_BODY_MAX bytes (413), a key twice 400 (the parsers of two systems may read
    another one of them)."""
    if (request.content_length or 0) > ISC_BODY_MAX:
        raise _fail(413, tr("The request is too large"), "too_large")
    raw = request.get_data(cache=True)
    if len(raw) > ISC_BODY_MAX:
        raise _fail(413, tr("The request is too large"), "too_large")

    def pairs(kv):
        d = {}
        for k, v in kv:
            if k in d:
                raise BadInput(tr("The key {0} appears twice", k))
            d[k] = v
        return d
    try:
        b = json.loads(raw.decode("utf-8") or "{}", object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError):
        raise BadInput(tr("The body must be a JSON object")) from None
    if not isinstance(b, dict):
        raise BadInput(tr("The body must be a JSON object"))
    return b


def isc_clean(c, b, cur):
    """{column: clean value} of the fields in body b (cur: the client now or None), and whether name / name_extra look suspicious."""
    unknown = sorted(k for k in b if k not in ISC_FIELDS and k != "expect_updated_at")
    if unknown:
        raise UnknownFields(unknown)
    out, sus = {}, False
    for k in ISC_FIELDS:
        if k not in b:
            continue
        v = b[k]
        if v is not None and not isinstance(v, str):
            raise _bad(k)
        v = isc_norm(v)  # #7113 (review F9): first NFKC and without control / format characters, then the checks
        if len(v) > ISC_FIELDS[k] and k != "vat_id":
            raise _bad(k, tr("{0}: at most {1} characters", k, ISC_FIELDS[k]))
        if isc_text_check(k, v) == "suspicious":
            sus = True
        try:
            got = clean_client(c, None, {k: v})  # ISS_REUSED: the client's own checks (country code, VAT ID form, e-mail, language)
        except BadInput as e:
            raise _bad(k, str(e)) from None
        out[k] = got.get(k, v)
    if cur is None and not out.get("name"):
        raise _bad("name", tr("Name missing"))
    if "name" in out and not out["name"]:
        raise _bad("name", tr("Name missing"))
    if "vat_id" in out or "country" in out:
        vat = out.get("vat_id", (cur or {}).get("vat_id") or "")
        land = out.get("country", (cur or {}).get("country") or "")
        if vat and vat[:2].isalpha():
            want = fk_vat_prefix(land)
            if not land or vat[:2] not in want:
                raise _bad("vat_id", tr("The VAT ID {0} does not fit the country {1} (expected: {2})", vat[:2], land or "-", "/".join(want) or "-"))
    return out, sus


def isc_public(r, flags=None):
    """The client as the key sees it: the fixed list of fields, its version, whether a person still has to check it."""
    d = {k: (r.get(k) if isinstance(r, dict) else r[k]) or "" for k in ISC_PUBLIC}
    d["updated_at"] = r["updated_at"]
    d["checked"] = not (r.get("issuer_hold") if isinstance(r, dict) else r["issuer_hold"])
    if flags is not None:
        d["flags"] = flags
    return d


def _area_sql(c, oid):
    return pb_cl_sql(c, oid)


def isc_row(c, iss, ref, lock=False):
    """The issuer's own client of external_ref ref (None), only in its area."""
    return c.execute(f"SELECT * FROM clients WHERE issuer_id=? AND external_ref=? AND {_area_sql(c, iss['org_id'])}"
                     + (" FOR UPDATE" if lock else ""), (int(iss["id"]), ref)).fetchone()


def isc_gone(c, iss, ref):
    """The tombstone of a client of this issuer that is no more (anonymised, deleted for good, merged away)."""
    with system_ctx(c):  # the issuer's own refs
        return c.execute("SELECT 1 FROM office_issuer_refs WHERE issuer_id=? AND route=? AND client_ref=?",
                         (int(iss["id"]), ISC_REF_ROUTE, ref)).fetchone() is not None


def _need_live(c, iss, ref, r):
    if r is None:
        if isc_gone(c, iss, ref):
            raise _fail(410, tr("This client was deleted or anonymised in the office"), "client_gone")
        raise Denied(404)
    if r["deleted_at"]:
        raise _fail(409, tr("This client is in the trash of the office"), "client_trashed")


def isc_lookalike(c, oid, cid, name, vat):
    """Another client of the area (not in the trash) with the same name (letter case and spaces aside) or VAT ID."""
    n = " ".join((name or "").split()).lower()
    if not n and not vat:
        return False
    q = (f"SELECT 1 FROM clients WHERE {_area_sql(c, oid)} AND {live_sql()} AND id<>? AND "
         "(lower(regexp_replace(btrim(name), '\\s+', ' ', 'g'))=? OR (?<>'' AND vat_id=?)) LIMIT 1")
    with system_ctx(c):  # existence only, across the area (a client the key does not own counts too)
        return c.execute(q, (int(cid or 0), n, vat or "", vat or "")).fetchone() is not None


def isc_hold(old, iss_id, changed, new, flags):
    """The new mark (JSON) after the key set up (new) or changed the fields changed {column: (before, after)}: the old value
    of the first change since a person checked stays, the new one is the last."""
    h = ihd_load(old) or {"fields": {}, "flags": [], "new": False}
    f = h.get("fields") if isinstance(h.get("fields"), dict) else {}
    for k, (a, z) in changed.items():
        if k in IHD_FIELDS:
            f[k] = [(f.get(k) or [a or ""])[0], z or ""]
    h.update(at=iso_ms(now_utc()), issuer=int(iss_id), fields=f, new=bool(h.get("new") or new),
             flags=sorted(set(h.get("flags") or []) | set(flags)))
    return json.dumps(h, ensure_ascii=False)


def isc_notice(c, label, fn):
    """Run fn(c) (a notice / log line of a refusal) and commit; a failure is rolled back and printed, the refusal stands.
    The one place of this catch for the issuer routes (issdocs.py uses it too)."""
    try:
        fn(c)
        c.commit()
    except Exception as e:  # noqa: BLE001 -- the refusal stands without its notice
        c.rollback()
        print(f"issuer {label} notice failed:", type(e).__name__, flush=True)


def isc_limit_tell(c, iss, what, text):
    """The admins hear of a reached limit once a day (no pause: a busy day is no attack)."""
    def tell(c):
        if _iss_once(c, iss, f"limit:{what}"):
            iss_tell(c, iss["org_id"], iss, "issuer_limit", text)
    isc_notice(c, "limit", tell)


def _limit(c, iss, what, retry=3600, text=ISC_LIMIT_CLIENTS):
    """429 limit_reached (isc_limit_tell)."""
    isc_limit_tell(c, iss, what, text)
    return _fail(429, tr("The invoice issuer reached its limit of {0}", tr(text)), "limit_reached", {"Retry-After": str(retry)})


class _OverChanges(Exception):
    """A change over ISC_DAY_CHANGES (raised inside the write, answered after its rollback)."""


def isc_day_changes(c, iss):
    """The changes of its clients the issuer made within 24 hours: its issuer_write lines of clients minus its set-ups (the
    tombstones; a set-up writes a line too and counts against day_clients)."""
    since = iso(now_utc() - timedelta(days=1))
    with system_ctx(c):  # the issuer's own log lines and tombstones
        w = c.execute("SELECT COUNT(*) FROM office_doc_log WHERE issuer_id=? AND action='issuer_write' AND target ILIKE 'client:%' AND at>=?",
                      (int(iss["id"]), since)).fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM office_issuer_refs WHERE issuer_id=? AND route=? AND created_at>=?",
                      (int(iss["id"]), ISC_REF_ROUTE, since)).fetchone()[0]
    return int(w) - int(n)


ISC_READ_TARGET = "clients"  # #7113 (review F12): one read line per issuer and hour for all its clients


def _log_read(c, iss):
    """One line issuer_read per issuer and hour for the reads of all its clients (not per client: the log is never pruned)."""
    target = ISC_READ_TARGET
    if not _iss_read_logged(c, iss, target):
        iss_log(c, iss["org_id"], iss["id"], "issuer_read", target, {"key": g.issuer_key["prefix"], "ip": fx2_mask_ip(client_ip())}, name=iss["name"])
        c.commit()


def _answer(fn):
    """v1_view and the BadInput / Denied extras of this module (invalid_field + field, headers of a refusal)."""
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except UnknownFields:
            raise
        except BadInput as e:
            v1 = getattr(e, "v1", None)
            if v1:
                return v1_err(400, str(e), name=v1["name"], field=v1["field"])
            raise
        except Conflict:
            raise
        except Denied as e:
            if getattr(e, "headers", None):
                return v1_err(e.code, e.text(), e.headers, name=getattr(e, "v1_name", None), **getattr(e, "v1_extra", {}))
            raise
    run.__name__ = fn.__name__
    run.__doc__ = fn.__doc__
    return run


@app.get("/api/v1/issuer/clients/by-ref/<path:ref>")  # = ISC_RULE (a literal: tests/routes_ast.py)
@v1_view
@_answer
def isc_get(ref):
    """The issuer's own client by its external_ref (ISC_PUBLIC); 404 unknown, 409 client_trashed, 410 client_gone."""
    extra = sorted(request.args)
    if extra:
        raise UnknownFields(extra)
    c, iss = _iss_me()
    ref = _ref(ref)
    r = isc_row(c, iss, ref)
    _need_live(c, iss, ref, r)
    _log_read(c, iss)
    return jsonify(isc_public(r))


@app.put("/api/v1/issuer/clients/by-ref/<path:ref>")  # = ISC_RULE
@v1_view
@_answer
def isc_put(ref):
    """Sets up (201) or changes (200) the issuer's own client of external_ref (module text)."""
    if request.args:
        raise UnknownFields(sorted(request.args))
    c, iss = _iss_me()
    ref = _ref(ref)
    b = isc_body()
    oid = int(iss["org_id"])
    actor = f"issuer:{int(iss['id'])}"
    write_lock(c, f"issuer-{int(iss['id'])}")  # one write of this issuer at a time: two parallel set-ups = one client
    # review F14 (#7113): no row lock here - ow_write takes clients-<id>, then the row (FOR UPDATE), as a person's change
    # (team/clients.py) and taking the mark away do; a row lock first was the reverse order (a deadlock, one of them aborted).
    # The issuer's lock above queues the key's writes, ow_write reads the row anew under clients-<id>.
    r = isc_row(c, iss, ref, lock=False)
    if r is None and not isc_gone(c, iss, ref):
        return _create(c, iss, oid, ref, b, actor)
    _need_live(c, iss, ref, r)
    seen = {}

    def clean(c, b, cur):
        vals, sus = isc_clean(c, b, cur)
        seen["sus"] = sus
        if any((cur.get(k) or "") != (v or "") for k, v in vals.items()) and isc_day_changes(c, iss) >= ISC_DAY_CHANGES:
            raise _OverChanges()  # review F6: an unchanged PUT writes nothing and still answers
        return vals

    if not b.get("expect_updated_at"):  # a change needs the version (ow_write asks agents only); an unchanged retry does not
        vals, _sus = isc_clean(c, b, dict(r))
        if any((r[k] or "") != (v or "") for k, v in vals.items()):
            e = Denied(400, tr("expect_updated_at is missing: send the client's updated_at with every change"))
            e.v1_name, e.v1_extra = "version_required", {"fields": ["expect_updated_at"]}
            raise e
        _log_read(c, iss)
        return jsonify(isc_public(r, flags=_flags_of(r)))

    def extra(c, cur, changed):
        held = {k: v for k, v in changed.items() if k in IHD_FIELDS}
        if not held:
            return
        nm, vat = (changed.get("name") or (None, cur.get("name")))[1], (changed.get("vat_id") or (None, cur.get("vat_id")))[1]
        flags = (["client_lookalike"] if isc_lookalike(c, oid, cur["id"], nm, vat) else []) + (["text_suspicious"] if seen.get("sus") else [])
        c.execute("UPDATE clients SET issuer_hold=? WHERE id=?", (isc_hold(cur.get("issuer_hold"), iss["id"], held, False, flags), cur["id"]))
        seen["held"] = held

    from .issdocs import isd_client_fp
    fp_before = isd_client_fp(c, r["id"])  # review F4 (#6701): only drafts still as the key delivered them follow its change
    try:
        new, changed = ow_write(c, None, "client", r["id"], b, clean, where=f"id=? AND issuer_id=? AND {_area_sql(c, oid)}",
                                args=(r["id"], int(iss["id"])), lock=f"clients-{int(r['id'])}", public=lambda c, cur: isc_public(cur),
                                extra=extra, via=actor)
    except _OverChanges:
        c.rollback()
        raise _limit(c, iss, "day_changes", text=ISC_LIMIT_CHANGES) from None
    if not changed:
        _log_read(c, iss)
        return jsonify(isc_public(new, flags=_flags_of(new)))
    iss_log(c, oid, iss["id"], "issuer_write", f"client:{ref}", {"client": int(r["id"]), "key": g.issuer_key["prefix"],
                                                                  "fields": {k: [a, z] for k, (a, z) in changed.items()}}, name=iss["name"])
    if seen.get("held"):
        _tell(c, iss, new)
    from .issdocs import isd_client_changed
    isd_client_changed(c, iss["id"], r["id"], fp_before)  # (#6701): its drafts' preview follows the key's own change of the client
    c.commit()
    new = isc_row(c, iss, ref)
    return jsonify(isc_public(new, flags=_flags_of(new)))


def isc_spec(paths, op, ok, errs):
    """OpenAPI of an invoice issuer's client routes (called from api/openapi.py), like office/issuers.py iss_spec."""
    txt = {"type": "string"}
    fields = {k: {"type": "string", "maxLength": n} for k, n in ISC_FIELDS.items()}
    fields["name"]["description"] = "The name of the invoice's recipient, also the name of a person"
    fields["country"]["description"] = "ISO 3166-1 alpha-2 (Greece GR; its VAT IDs start with EL)"
    fields["vat_id"]["description"] = "Optional, also for German buyers (never the buyer's tax number); its two letters fit the country"
    client = {"type": "object", "properties": {"external_ref": txt, **fields, "updated_at": {"type": "string", "format": "date-time"},
                                               "checked": {"type": "boolean", "description": "false while a person has not checked the data the key set"},
                                               "flags": {"type": "array", "items": {"type": "string", "enum": list(ISC_KEY_FLAGS)}}}}
    ref = {"name": "ref", "in": "path", "required": True, "description": "external_ref: [A-Za-z0-9._:-]{1,64}, the outside system's own id of "
           "the client with a fixed prefix of its environment (prod:account:12), kept for good", "schema": {"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,64}$"}}
    paths["/issuer/clients/by-ref/{ref}"] = {
        "get": op("An invoice issuer's own client by its external_ref (2.1384.0)", "Office", ok(client) | errs("400", "403", "404", "409", "410"), [ref],
                  scope="office", desc="Only with an invoice issuer key. 404 unknown (or another's), 409 client_trashed (in the office's trash), "
                                       "410 client_gone (anonymised, deleted or merged away in the office; for good)."),
        "put": op("Set up (201) or change (200) an invoice issuer's own client (2.1384.0)", "Office",
                  ok(client) | ok(client, "set up", "201") | errs("400", "403", "404", "409", "410", "413"), [ref],
                  body={"type": "object", "additionalProperties": False, "properties": {**fields, "expect_updated_at": {"type": "string"}}},
                  scope="office", desc="Only with an invoice issuer key; a fixed list of fields (an unknown one 400 unknown_field). A change "
                       "needs expect_updated_at (400 version_required; 409 conflict with the current client when a person changed it). Texts "
                       "with an IBAN, a web or an e-mail address are refused (400 invalid_field + field); in name / name_extra a web or e-mail "
                       "pattern only flags text_suspicious. A VAT ID must fit the country (400 invalid_field vat_id). Every set-up and every "
                       "change of the address, the name, the VAT ID, the buyer reference or the e-mail for invoices puts a hold mark on the "
                       "client until a person checks it (checked false): nothing is sent to it without the person's confirmation. "
                       "429 limit_reached (day_clients new clients or 200 changes of clients within 24 hours, Retry-After).")}


def _flags_of(r):
    """The flags of the mark the key sees: client_new and text_suspicious (its own input). client_lookalike stays in the mark
    for the persons (office/isshold.py): told to the key it would answer whether the office knows a name or VAT ID (review F2)."""
    h = ihd_load(r["issuer_hold"] if not isinstance(r, dict) else r.get("issuer_hold"))
    if not h:
        return []
    return sorted(x for x in set(h.get("flags") or []) | ({"client_new"} if h.get("new") else set()) if x in ISC_KEY_FLAGS)


def _tell(c, iss, r):
    if _iss_once(c, iss, "client"):
        # #7113 (review F10): the client's name (free text of the key) only in the app's News, never in the security mail
        iss_tell(c, iss["org_id"], iss, "issuer_client", (r["name"] if not isinstance(r, dict) else r.get("name")) or "", security=True,
                 mail_detail=ISC_MAIL_CLIENT)


def _create(c, iss, oid, ref, b, actor):
    vals, sus = isc_clean(c, b, None)
    since = iso(now_utc() - timedelta(days=1))
    with system_ctx(c):  # the issuer's own tombstones of the last 24 hours (a client deleted since still counts)
        n = c.execute("SELECT COUNT(*) FROM office_issuer_refs WHERE issuer_id=? AND route=? AND created_at>=?",
                      (int(iss["id"]), ISC_REF_ROUTE, since)).fetchone()[0]
    if n >= int(iss["day_clients"]):
        raise _limit(c, iss, "day_clients")
    owner = pb_owner(c, oid)
    flags = (["client_lookalike"] if isc_lookalike(c, oid, 0, vals.get("name"), vals.get("vat_id")) else []) + (["text_suspicious"] if sus else [])
    ts = iso_ms(now_utc())
    row = {**vals, "org_id": None if owner is not None else oid, "created_by": owner, "created_at": iso(now_utc()), "updated_at": ts,
           "issuer_id": int(iss["id"]), "external_ref": ref}
    row["issuer_hold"] = isc_hold(None, iss["id"], {k: ("", v) for k, v in vals.items() if v}, True, flags)
    cid = insert_id(c, f"INSERT INTO clients({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
    with system_ctx(c):  # the tombstone of the ref: it outlives the client (anonymised, deleted, merged away: 410, never anew)
        c.execute("INSERT INTO office_issuer_refs(issuer_id, org_id, route, client_ref, body_sha256, created_at, doc_id) VALUES(?,?,?,?,?,?,NULL)",
                  (int(iss["id"]), oid, ISC_REF_ROUTE, ref, "", iso(now_utc())))
    ow_created(c, None, "client", cid, {k: v for k, v in row.items() if k in ISC_FIELDS or k == "external_ref"}, row["org_id"], via=actor)
    iss_log(c, oid, iss["id"], "issuer_write", f"client:{ref}", {"client": cid, "new": True, "key": g.issuer_key["prefix"],
                                                                  "fields": {k: ["", v] for k, v in vals.items() if v}}, name=iss["name"])
    _tell(c, iss, row)
    bump(c)
    c.commit()
    r = isc_row(c, iss, ref)
    return jsonify(isc_public(r, flags=_flags_of(r))), 201
