"""2.1381.0 (#6699): invoice issuer keys -- an outside system (a shop, a booking system, a freelancer's own script) prepares
invoices in one office area with a key of its own, and a person in the office checks, finalises and sends them (review mode,
the only mode: there is no "automatic").

An issuer is NO account and NO agent: a row of office_issuers for one office area and one additional number range (#6698,
office/numranges.py), owned by the area. Its keys ("kis_test_" / "kis_live_" + 43 characters; only the SHA-256 is stored,
shown once) live in office_issuer_keys: at most 365 days, at most two valid at once (the change of a key overlaps by the days
the admin chose, default 7, at most 14), each can be revoked at once. A key is a kind of its own of the API (api/common.py
V1_KEY_KINDS "kis_"): it is never looked up in api_tokens and reaches only the routes of ISS_ROUTES under /api/v1/issuer;
g.user stays None (never the admin who set it up), the request reads as "anon" bound to exactly the issuer's area
(core/access.py acx_anon_bind) and every issuer query filters on issuer_id itself (row-level security lets rows with
org_id NULL through, core/rls.py: the private clients of every person). /api/office/* stays sessions only
(accounts/session.py: a bearer key there is 403).

The sign-in of a key, in this order: hash (as "system") -> key revoked / expired -> issuer revoked -> the key's environment
is the server's (KALMIDO_ISSUER_ENV: a test server never takes a live key and the other way round) -> the server allows
issuers (KALMIDO_ISSUER_KEYS; on a hosted server the operator unlocked the area, orgs.issuer_keys) -> office still on and
the area open (404 otherwise) -> address rule -> route in ISS_ROUTES -> pause -> rate (ISS_RATE a minute, counted in the
database for every process; a failed count refuses, 503) -> the context. An invalid key counts against the address like an
invalid API token (apibad); a key of the other environment is invalid too.

Who manages (Settings of the office > Invoice issuers, sessions only): an admin of the organisation -- in a personal office
its owner -- and only while the server / the operator allows it. Setting up an issuer, a new key, raising a limit,
loosening or removing the address rule, a new bank account and resuming after any pause but the admin's own need the
sign-in confirmation (password, or a fresh sign-in for an account without one: accounts/oidc.py oidc_reauth). Every change
goes into the office log (office_doc_log with issuer_id) and to the other admins of the area (collab/integfail.py
integ_tell); the security alarms (new key, first call from a new address, self-pause) go to every admin by e-mail as well,
whatever the notification settings say. Admins of the area = the personal office's owner or the organisation's admins.

Pause: every call of a paused issuer is refused (403 issuer_paused). It pauses itself on ISS_SELF_PAUSE calls within an hour
that look like probing: refused routes and ids counted per distinct target, or calls from an address outside its rule;
400, 409, 410 and 429 never count. An area without an admin pauses its issuers (daily check), so does a restore of a backup
(an older backup would bring revoked keys back), and the operator taking the unlock back. The office log keeps a line per
writing call, one per hour and target for reads and one per ISS_REFUSED_EVERY minutes and target for refusals (issuer_read /
issuer_write / issuer_refused): the office log is never pruned, so a stolen key cannot fill it.

Moving a personal office into an organisation (office/pbtransfer.py) revokes its issuers first (the rows stay with the
personal office, PBT_KEEP): a key never lands with the target's admins unnoticed.

    GET    /api/office/issuers                       the area's issuers (admins)
    POST   /api/office/issuers                       {name, range_id, allowed_ips?, any_address?, limits?, valid_days?} -> {issuer, key}
    PATCH  /api/office/issuers/<id>                  {name?, limits?, allowed_ips?, any_address?}
    DELETE /api/office/issuers/<id>                  revoke (for good; its keys end at once)
    POST   /api/office/issuers/<id>/keys             {valid_days?, overlap_days?} -> {key} (the older valid key ends after the overlap)
    DELETE /api/office/issuers/<id>/keys/<kid>       ends a key at once
    POST   /api/office/issuers/<id>/pause | /resume
    GET    /api/office/issuers/<id>/log              the issuer's lines of the office log
    GET    /api/office/issuers/<id>/payees           the bank accounts allowed for it (applied on documents from #6819 on)
    POST   /api/office/issuers/<id>/payees           {label, holder, iban, bic?, ref_only?}
    DELETE /api/office/issuers/<id>/payees/<pid>
    GET    /api/v1/issuer                            the key's own view (name, environment, range, limits, tax profile)"""
import os
import re
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import g, jsonify, request

from ..core.config import APP_NAME, PUBLIC_URL, app
from ..core.db import body, bump, db, err, iso, now_utc, parse_iso, usettings
from ..core.env import env_bool
from ..core.errors import BadInput, Denied, UnknownFields
from ..core.i18n import LANGS, N_, tr
from ..core.ipallow import ips_clean, token_ip_ok
from ..core.mailframe import mail_html
from ..core.orgcrypt import oc_dec_fields, oc_enc, oc_enc_fields, oc_log_detail
from ..core.pg import qi, system_ctx, write_lock
from ..core.ratedb import rate_counts, rate_hit
from ..core.access import acx_anon_bind
from ..accounts.bgjobs import BGJ_FNS, bgj_add
from ..accounts.oidc import oidc_reauth
from ..accounts.session import _rate_blocked, _rate_fail, _token_hash, client_ip, FAIL_WINDOW
from ..api.common import v1_err, v1_view, V1_KEY_KINDS
from ..collab.integfail import INTEG_TEXT, integ_tell
from ..notify.alerts import aa_now, fx2_mask_ip
from .ledger import _cap, _iban_ok, _log_public, ofx_company, ofx_log_name
from .model import office_gate, office_on, office_org, office_settings, office_where, pb_owner

ISS_ON = env_bool("KALMIDO_ISSUER_KEYS", False)  # opt-in while the kind of key is new (Kalmido-Dev after review #5304)
ISS_HOSTED = env_bool("KALMIDO_HOSTED", False)  # admin.hosting.hosted() (a higher layer), the same switch
ISS_ENV = "live" if (os.environ.get("KALMIDO_ISSUER_ENV", "") or "").strip().lower() == "live" else "test"
ISS_PREFIX = "kis_"
ISS_KEY_RE = re.compile(r"kis_(test|live)_[A-Za-z0-9_-]{43}")
ISS_DAYS, ISS_OVERLAP, ISS_OVERLAP_MAX = 365, 7, 14
ISS_KEYS_MAX = 2          # valid keys of one issuer at once (the old one runs out after the overlap)
ISS_MAX = 20              # issuers of one area that are not revoked
ISS_RATE = 60             # calls of one issuer per minute (database count)
ISS_SELF_PAUSE = 20       # probing calls within an hour -> the issuer pauses itself
ISS_REFUSED_EVERY = 10    # minutes: the same refusal is logged once in this time (the office log is never pruned)
ISS_USED_EVERY = 60       # s between two last_used_at updates of a key
ISS_IPS_MAX = 50          # addresses kept per issuer (the oldest go)
ISS_NEW_IPS_DAY = 5       # new addresses a day that are each an alarm; one more pauses the issuer ("address")
ISS_NAME_MAX, ISS_LABEL_MAX, ISS_HOLDER_MAX = 80, 80, 70
ISS_PAYEES_MAX = 10
ISS_WARN_DAYS = (30, 7, 0)  # the admins hear of a key running out this many days before
# the limits an admin sets: column -> (kind, default, highest value); 0 = nothing allowed, never "unlimited". day_credits
# (stage 3) is not offered: no switch without an effect. Counted against the documents once the drafts exist (#6701).
ISS_LIMITS = {"max_gross": ("money", Decimal("2000"), Decimal("1000000")), "day_docs": ("int", 50, 10000),
              "day_gross": ("money", Decimal("20000"), Decimal("10000000")), "day_clients": ("int", 50, 10000),
              "open_drafts": ("int", 200, 10000), "day_mails": ("int", 100, 10000), "day_withdraw": ("int", 10, 1000),
              "review_wait_h": ("int", 24, 720)}
ISS_COLS = ("name", "allowed_ips", "updated_at", *ISS_LIMITS)  # what PATCH writes (qi)
ISS_PAUSE_WHY = {"admin": N_("paused by an admin"), "refused": N_("it paused itself after many refused calls"),
                 "address": N_("it paused itself after calls from addresses outside its rule"),
                 "noadmin": N_("the office has no admin any more"), "restore": N_("a backup was restored"),
                 "operator": N_("the server operator switched the invoice issuers of this office off")}
# the only routes a key reaches (method, rule); stage 1b: its own view. 2.1384.0 (#6700): its clients (office/issclients.py
# adds them); 2.1396.0 (#6701): its drafts and documents (office/issdocs.py adds them)
ISS_ROUTES = {("GET", "/api/v1/issuer")}
# 2.1381.0 (#6699): every office function an issuer route calls with the issuer's context (no person): each has a test in
# tests/p21381_office_issuer_key_test.py (the suite holds this list against its own); 2.1384.0 (#6700): the clients' ones in
# tests/p6700_office_issuer_clients_test.py
ISS_REUSED = ("office.ledger.ofx_company", "office.model.office_settings", "team.clients.clean_client", "office.owrite.ow_write",
              "office.owrite.ow_created",
              # 2.1396.0 #6701: the drafts of office/issdocs.py, tested in tests/p6701_office_issuer_invoices_test.py
              "office.docs.doc_create", "office.docs._put_items", "office.docs.recalc", "office.invoices.inv_missing",
              "office.docs.odoc_trash", "office.pdfweb._render")
ISS_OFF = N_("Invoice issuers are not available for this office")
ISS_ADMIN_ONLY = N_("Only an admin of the organisation can manage invoice issuers")
ISS_SEC_FOOT = N_("Security notices of invoice issuers always come by e-mail as well.")

INTEG_TEXT.update({
    "issuer_created": N_("Invoice issuer {0} was set up by {2}."),
    "issuer_key": N_("Invoice issuer {0}: {2} created a new key (valid until {1})."),
    "issuer_key_ended": N_("Invoice issuer {0}: {2} ended a key at once."),
    "issuer_changed": N_("Invoice issuer {0}: {2} changed its settings ({1})."),
    "issuer_payee": N_("Invoice issuer {0}: {2} added the bank account {1}."),
    "issuer_payee_gone": N_("Invoice issuer {0}: {2} removed the bank account {1}."),
    "issuer_revoked": N_("Invoice issuer {0} was revoked by {2}."),
    "issuer_paused": N_("Invoice issuer {0} is paused: {1}"),
    "issuer_resumed": N_("Invoice issuer {0} runs again (resumed by {2})."),
    "issuer_ip": N_("Invoice issuer {0}: first call from a new address ({1})."),
    "issuer_expiry": N_("Invoice issuer {0}: its key runs out on {1}. Create a new key in the office settings."),
    "issuer_expired": N_("Invoice issuer {0}: its key ran out today."),
    "issuer_left": N_("Invoice issuer {0} keeps running: {2}, who set it up, is no admin of the office any more."),
    "issuer_moved": N_("Invoice issuer {0} keeps running: the private office became the organisation {1}."),
})
ISS_SECURITY = ("issuer_key", "issuer_ip", "issuer_paused")  # always by e-mail too (not for an admin's own pause)


# ---------------------------------------------------------------- the area: may it have issuers, who are its admins
def iss_allowed(c, oid):
    """True when office area oid may have invoice issuers: the server allows them (KALMIDO_ISSUER_KEYS) and -- on a hosted
    server (admin/hosting.py hosted) -- the operator unlocked the area (orgs.issuer_keys, default off)."""
    if not ISS_ON:
        return False
    if not ISS_HOSTED:
        return True
    with system_ctx(c):  # the operator's switch on the area's own row
        r = c.execute("SELECT issuer_keys FROM orgs WHERE id=?", (oid,)).fetchone()
    return bool(r and r[0])


def iss_admins(c, oid):
    """The admins of office area oid: the personal office's owner, else the organisation's admins (people, not locked)."""
    owner = pb_owner(c, oid)
    with system_ctx(c):  # who gets an issuer's alarms (also from the key's own request, which has no person)
        if owner is not None:
            u = c.execute("SELECT disabled FROM users WHERE id=?", (owner,)).fetchone()
            return [owner] if u and not u[0] else []
        return [r[0] for r in c.execute(
            "SELECT m.user_id FROM org_members m JOIN users u ON u.id=m.user_id WHERE m.org_id=? AND m.role='admin' "
            "AND NOT u.disabled AND COALESCE(u.kind, 'user')<>'agent' ORDER BY m.user_id", (oid,)).fetchall()]


def _who(c, uid):
    u = c.execute("SELECT display_name, username FROM users WHERE id=?", (uid,)).fetchone() if uid else None
    return ((u["display_name"] or u["username"]) or "") if u else ""


def iss_tell(c, oid, iss, what, detail="", who="", besides=None, security=None, mail_detail=None):
    """An issuer's notice to the admins of its area (News + push by their settings), besides = not to this person (the one who
    acted). A security notice (ISS_SECURITY, or security=True) goes to every admin by e-mail as well, whatever their settings
    say (a hijacked session must not stay unnoticed; in a personal office there is nobody else). mail_detail: the mail's
    detail when it must not carry the News' one (#7113: no text a key wrote goes into a mail from Kalmido). The caller commits."""
    admins = iss_admins(c, oid)
    name = iss["name"] or f"#{int(iss['id'])}"
    integ_tell(c, [u for u in admins if u != besides], what, name, detail, click="office/settings", more=(who,), issuer_id=int(iss["id"]))
    if security if security is not None else what in ISS_SECURITY:
        iss_mail(c, admins, what, name, detail if mail_detail is None else mail_detail, who)


def iss_mail(c, uids, what, name, detail="", who=""):
    """The e-mail of a security notice to uids (only a proved address, like collab/integfail.py integ_mail)."""
    if "mail:security" not in BGJ_FNS:  # registered only with outgoing mail
        return
    try:
        with system_ctx(c):  # the recipients' language and proved address
            for uid in uids:
                u = c.execute("SELECT email, email_proved FROM users WHERE id=?", (uid,)).fetchone()
                to = ((u["email"] if u else "") or "").strip()
                if not to or ((u["email_proved"] or "") != to.lower()):
                    continue
                s = usettings(c, uid)
                lg = s.get("lang") if s.get("lang") in LANGS else "en"
                text = tr(INTEG_TEXT[what], name, tr(detail, lg=lg) if detail else "", who, lg=lg)
                link = f"{PUBLIC_URL}/#office/settings"
                subject = f"{APP_NAME}: {tr('Invoice issuer', lg=lg)}"
                foot = tr(ISS_SEC_FOOT, lg=lg)
                bgj_add("mail:security", to, subject, f"{text}\n\n{link}\n\n-- \n{foot}\n",
                        mail_html(subject, [text], tr("Open settings", lg=lg), link, lang=lg, note=foot), user_id=uid)
    except Exception as e:  # noqa: BLE001 -- the News item went out; the mail is a second way
        print("issuer mail failed:", type(e).__name__, flush=True)


def _iss_once(c, iss, key, day=None):
    """True the first time today (or on day) for occasion key of the issuer (office_issuers.told), then False: one notice per
    occasion and day."""
    day = day or now_utc().date().isoformat()
    with system_ctx(c):  # the issuer's own row
        r = c.execute("UPDATE office_issuers SET told = jsonb_set(told, ARRAY[?], to_jsonb(?::text)) WHERE id=? "
                      "AND COALESCE(told->>?, '')<>? RETURNING id", (key, day, iss["id"], key, day)).fetchone()
    return r is not None


# ---------------------------------------------------------------- the office log of an issuer
def iss_log(c, oid, iss_id, action, target="issuer", detail=None, uid=None, name=None, doc_id=None):
    """One line of the office log for issuer iss_id: by a person uid (an admin's change), or by the issuer itself (uid None:
    the name kept is the issuer's). 2.1396.0 (#6701): doc_id = the document it concerns (its draft, a withdrawal)."""
    who = ofx_log_name(c, oid, uid) if uid else (oc_enc(c, oid, "office_doc_log.user_name", name or "") or "")
    with system_ctx(c):  # the area's log (the key's own request has no person)
        c.execute("INSERT INTO office_doc_log(org_id, doc_id, user_id, at, action, target, detail, user_name, issuer_id) VALUES(?,?,?,?,?,?,?,?,?)",
                  (oid, doc_id, uid, iso(now_utc()), action, str(target)[:200], oc_log_detail(c, oid, _cap(detail)), who, iss_id))


def _iss_read_logged(c, iss, target):
    """A read is logged once per issuer, target and hour."""
    with system_ctx(c):  # the issuer's own lines
        return c.execute("SELECT 1 FROM office_doc_log WHERE issuer_id=? AND action='issuer_read' AND target=? AND at>=? LIMIT 1",
                         (iss["id"], target, iso(now_utc() - timedelta(hours=1)))).fetchone() is not None


# ---------------------------------------------------------------- the key's sign-in (api/v1.py api_authenticate)
def _iss_refuse(c, iss, key, code, msg, name, kind, headers=None):
    """A refused call of a known issuer: its log line, the self-pause, the API error. The office log cannot be pruned
    (core/migrations.d/6467.py), so a stolen key must not fill it: the same refusal (target) is written once per
    ISS_REFUSED_EVERY minutes; a paused issuer's and a rate refusal carry no path; probing a route ends in the self-pause after
    ISS_SELF_PAUSE distinct targets. Calls from outside the address rule are counted in the database (core/ratedb.py), not by
    their log lines. Both counts start again when a person resumes the issuer."""
    ip = fx2_mask_ip(client_ip())
    if iss["paused"]:  # review F1: every refusal of a paused issuer is one target (a new path each time would be a new line)
        kind = "paused"
    target = {"address": f"address:{ip}", "paused": "paused", "rate": "rate"}.get(kind) or f"{kind}:{request.method} {request.path}"
    try:
        n = 0
        if kind in ("route", "id"):
            hour = iso(now_utc() - timedelta(hours=1))
            with system_ctx(c):  # the distinct targets probed in the last hour, since a person last resumed the issuer
                n = c.execute("SELECT COUNT(DISTINCT target) FROM office_doc_log WHERE issuer_id=? AND action='issuer_refused' AND at>=? "
                              "AND (target LIKE 'route:%' OR target LIKE 'id:%') AND id > COALESCE((SELECT MAX(id) FROM office_doc_log "  # pg-ok: own lower-case prefixes, exact case
                              "WHERE issuer_id=? AND action='issuer_resume'), 0)", (iss["id"], hour, iss["id"])).fetchone()[0]
        since = iso(now_utc() - timedelta(minutes=ISS_REFUSED_EVERY))
        with system_ctx(c):  # the issuer's own refused calls
            seen = n >= ISS_SELF_PAUSE or c.execute(  # review F1: never more than ISS_SELF_PAUSE probed targets an hour
                "SELECT 1 FROM office_doc_log WHERE issuer_id=? AND action='issuer_refused' AND target=? AND at>=? LIMIT 1",
                (iss["id"], target[:200], since)).fetchone() is not None
        if not seen:
            iss_log(c, iss["org_id"], iss["id"], "issuer_refused", target, {"status": code, "code": name, "key": key["prefix"], "ip": ip}, name=iss["name"])
        if kind in ("route", "id") and n + (0 if seen else 1) >= ISS_SELF_PAUSE:
            iss_pause(c, iss, "refused")
        elif kind == "address" and not iss["paused"]:
            cnt = rate_counts([f"issaddr:{int(iss['id'])}:{iss['updated_at']}"], 3600, add=True, cap={f"issaddr:{int(iss['id'])}:{iss['updated_at']}": 2 * ISS_SELF_PAUSE})
            if cnt is not None and max(cnt.values()) >= ISS_SELF_PAUSE:
                iss_pause(c, iss, "address")
        c.commit()
    except Exception as e:  # noqa: BLE001 -- the refusal stands without its log line
        c.rollback()
        print("issuer refusal log failed:", type(e).__name__, flush=True)
    return v1_err(code, msg, headers, name=name)


def iss_authenticate(c, tok, bad):
    """The sign-in of an issuer key (V1_KEY_KINDS "kis_"): an error response, or None with g.issuer / g.issuer_key set and
    g.user None (see the module text for the order of the checks)."""
    key = iss = None
    if ISS_KEY_RE.fullmatch(tok) and tok.startswith(f"kis_{ISS_ENV}_"):
        with system_ctx(c):  # the key's row by its hash across organisations (its area is bound below)
            key = c.execute("SELECT * FROM office_issuer_keys WHERE token_hash=?", (_token_hash(tok),)).fetchone()
            iss = c.execute("SELECT * FROM office_issuers WHERE id=?", (key["issuer_id"],)).fetchone() if key else None
    if key and iss and not key["revoked_at"] and not iss["revoked_at"] and parse_iso(key["expires_at"]) <= now_utc():
        return v1_err(401, tr("The API token has expired"), {"WWW-Authenticate": 'Bearer realm="kalmido", error="invalid_token"'})
    if not key or not iss or key["revoked_at"] or iss["revoked_at"]:
        if _rate_blocked(bad):
            return v1_err(429, tr("Too many invalid tokens, please wait a few minutes"), {"Retry-After": str(FAIL_WINDOW)})
        _rate_fail(bad)
        return v1_err(401, tr("Missing or invalid API token"), {"WWW-Authenticate": 'Bearer realm="kalmido"'})
    oid = iss["org_id"]
    if not iss_allowed(c, oid):
        return v1_err(403, tr(ISS_OFF), name="issuer_keys_off")
    if not _iss_area_live(c, oid):
        return v1_err(404, tr("Not found"))
    try:
        acx_anon_bind(c, oid)  # nobody, inside exactly the issuer's area (a retired organisation: 404)
    except Denied:
        return v1_err(404, tr("Not found"))
    if not token_ip_ok(iss, client_ip()):
        return _iss_refuse(c, iss, key, 403, tr("This token may not be used from this address"), "address_refused", "address")
    rule = request.url_rule.rule if request.url_rule else ""
    if (request.method, rule) not in ISS_ROUTES:
        return _iss_refuse(c, iss, key, 403, tr("This key may only prepare invoices of its office"), "forbidden", "route")
    if iss["paused"]:
        return _iss_refuse(c, iss, key, 403, tr("This invoice issuer is paused"), "issuer_paused", "paused", {"Retry-After": "3600"})
    hit = rate_hit(f"iss:{int(iss['id'])}", ISS_RATE, 60)
    if hit is None:  # the count failed: refused (a limit that is not counted limits nothing)
        return v1_err(503, tr("Please try again in a moment"), {"Retry-After": "10"}, name="unavailable")
    if hit:
        return _iss_refuse(c, iss, key, 429, tr("Too many requests, please slow down"), "rate_limited", "rate", {"Retry-After": "60"})
    g.issuer, g.issuer_key, g.auth_via, g.token, g.scopes = iss, key, "issuer", None, frozenset()
    _iss_seen(c, iss, key)
    return None


def _iss_area_live(c, oid):
    """The office of the area is still on: a personal office's owner exists, is not locked and has the office (an
    organisation that is retired answers 404 at acx_anon_bind)."""
    owner = pb_owner(c, oid)
    if owner is None:
        return True
    with system_ctx(c):  # the owner of a personal office (the key's request has no person)
        u = c.execute("SELECT disabled FROM users WHERE id=?", (owner,)).fetchone()
        return bool(u and not u[0] and office_on(c, owner))


def _iss_seen(c, iss, key):
    """The key's last use (at most every ISS_USED_EVERY s) and the address it came from: a new address is a security alarm."""
    ip = client_ip()
    now = now_utc()
    try:
        with system_ctx(c):  # the issuer's own rows
            last = key["last_used_at"]
            if not last or (now - parse_iso(last)).total_seconds() >= ISS_USED_EVERY:
                c.execute("UPDATE office_issuer_keys SET last_used_at=? WHERE id=?", (iso(now), key["id"]))
            new = c.execute("INSERT INTO office_issuer_ips(issuer_id, org_id, ip, first_at, last_at, calls) VALUES(?,?,?,?,?,1) "
                            "ON CONFLICT(issuer_id, ip) DO UPDATE SET last_at=excluded.last_at, calls=office_issuer_ips.calls+1 "
                            "RETURNING (xmax = 0) AS fresh", (iss["id"], iss["org_id"], ip, iso(now), iso(now))).fetchone()[0]
            if new:
                c.execute("DELETE FROM office_issuer_ips WHERE issuer_id=? AND ip IN (SELECT ip FROM office_issuer_ips WHERE issuer_id=? "
                          "ORDER BY last_at DESC OFFSET ?)", (iss["id"], iss["id"], ISS_IPS_MAX))
        if new:  # review F4: at most ISS_NEW_IPS_DAY alarms a day; one more new address pauses it (one alarm instead of many)
            with system_ctx(c):  # the issuer's addresses first seen in the last 24 hours
                fresh = c.execute("SELECT COUNT(*) FROM office_issuer_ips WHERE issuer_id=? AND first_at>=?",
                                  (iss["id"], iso(now - timedelta(days=1)))).fetchone()[0]
            if fresh > ISS_NEW_IPS_DAY:
                iss_pause(c, iss, "address")
            else:
                iss_tell(c, iss["org_id"], iss, "issuer_ip", fx2_mask_ip(ip))
        c.commit()
    except Exception as e:  # noqa: BLE001 -- the call goes on without its bookkeeping
        c.rollback()
        print("issuer use not recorded:", type(e).__name__, flush=True)


V1_KEY_KINDS[ISS_PREFIX] = iss_authenticate


def iss_pause(c, iss, why, uid=None):
    """Pauses issuer iss (why: a key of ISS_PAUSE_WHY), its log line and the alarm (an admin's own pause: the other admins
    only, no e-mail). Nothing when it is paused already. The caller commits."""
    with system_ctx(c):  # the issuer's row (also from the key's own request or a background check)
        r = c.execute("UPDATE office_issuers SET paused=true, paused_reason=?, paused_at=?, paused_by=? WHERE id=? AND NOT paused "
                      "AND revoked_at IS NULL RETURNING id", (why, iso(now_utc()), uid, iss["id"])).fetchone()
    if r is None:
        return False
    iss_log(c, iss["org_id"], iss["id"], "issuer_pause", detail={"reason": why}, uid=uid, name=None if uid else iss["name"])
    iss_tell(c, iss["org_id"], iss, "issuer_paused", ISS_PAUSE_WHY.get(why, why), besides=uid, security=why != "admin")
    return True


# ---------------------------------------------------------------- the key's routes
def _iss_me():
    """The issuer of this request (403 for anything else: a session, an API token never reaches here with one)."""
    iss = g.get("issuer")
    if iss is None:
        raise Denied(403, tr("This key may only prepare invoices of its office"))
    return db(), iss


@app.get("/api/v1/issuer")
@v1_view
def v1_issuer_get():
    """The key's own view: {name, environment, mode, range: {code}, key: {prefix, expires_at}, limits, tax_profile: {country,
    small_business}}. Never the admins, the bank accounts, the address rule or the other key."""
    extra = sorted(request.args)
    if extra:
        raise UnknownFields(extra)
    c, iss = _iss_me()
    oid = iss["org_id"]
    with system_ctx(c):  # the issuer's own range (its row was chosen by its admin)
        rg = c.execute("SELECT code FROM office_num_ranges WHERE id=? AND org_id=?", (iss["range_id"], oid)).fetchone()
    s = office_settings(c, oid)  # ISS_REUSED: read with the area bound, no person
    comp = ofx_company(c, oid)  # ISS_REUSED
    key = g.issuer_key
    if not _iss_read_logged(c, iss, "issuer"):
        iss_log(c, oid, iss["id"], "issuer_read", "issuer", {"key": key["prefix"], "ip": fx2_mask_ip(client_ip())}, name=iss["name"])
        c.commit()
    return jsonify(name=iss["name"], environment=ISS_ENV, mode=iss["mode"], range={"code": rg["code"] if rg else ""},
                   key={"prefix": key["prefix"], "expires_at": iso(parse_iso(key["expires_at"]))},
                   limits=_iss_limits(iss), tax_profile={"country": (comp.get("country") or "DE").upper(),
                                                         "small_business": bool(s.get("small_business"))})


# ---------------------------------------------------------------- the admins' management (sessions only)
def _iss_ctx(write=True):
    """(c, uid, oid) of a management route: a person (office_gate: no agent, no token), an office admin; a change needs the
    organisation's admin (in a personal office its owner) and the server / operator allowing issuers (404 otherwise)."""
    c = db()
    uid = office_gate(c)
    oid = office_org(c, uid, admin=True)
    if not iss_allowed(c, oid):
        raise Denied(404, tr(ISS_OFF))
    if write:
        _oid, role = office_where(c, uid)
        if role != "admin" or _oid != oid:
            raise Denied(403, tr(ISS_ADMIN_ONLY))
    return c, uid, oid


def _iss_row(c, oid, iid, live=True):
    r = c.execute("SELECT * FROM office_issuers WHERE id=? AND org_id=?", (iid, oid)).fetchone()
    if r is None or (live and r["revoked_at"]):
        raise Denied(404)
    return r


def _iss_confirm(c, b):
    """The sign-in confirmation of a sensitive step (accounts/oidc.py oidc_reauth): None = confirmed, else the response
    (403 password_needed / reauth_needed, or a wrong password)."""
    return oidc_reauth(c, b)


def _iss_limits(r):
    return {k: (str(Decimal(str(r[k])).quantize(Decimal("0.01"))) if kind == "money" else int(r[k])) for k, (kind, _d, _m) in ISS_LIMITS.items()}


def _iss_limits_clean(v, cur=None):
    """{column: value} of a body's limits (only ISS_LIMITS, each 0..its highest value); BadInput otherwise."""
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise BadInput(tr("Invalid value: {0}", "limits"))
    unknown = sorted(set(v) - set(ISS_LIMITS))
    if unknown:
        raise UnknownFields(unknown)
    out = {}
    for k, x in v.items():
        kind, _d, hi = ISS_LIMITS[k]
        if isinstance(x, bool) or x is None:
            raise BadInput(tr("Invalid value: {0}", k))
        try:
            n = Decimal(str(x).strip()) if kind == "money" else int(str(x).strip())
        except (InvalidOperation, ValueError):
            raise BadInput(tr("Invalid value: {0}", k)) from None
        if kind == "money":
            if not n.is_finite() or n != n.quantize(Decimal("0.01")):
                raise BadInput(tr("Invalid value: {0}", k))
        if n < 0 or n > hi:
            raise BadInput(tr("{0} must be between {1} and {2}", k, 0, hi))
        out[k] = n
    return out


def _iss_ips(b, cur, live_env):
    """The address rule of a body (allowed_ips / any_address) -> (value, loosened). A live key needs a rule unless the admin
    removes it on purpose (any_address: true)."""
    if "allowed_ips" not in b and "any_address" not in b:
        return cur, False
    v = ips_clean(b.get("allowed_ips")) if "allowed_ips" in b else cur
    if b.get("any_address") is True:
        v = ""
    elif not v and live_env and b.get("any_address") is not True:  # review F5: only true removes the rule on purpose
        raise BadInput(tr("A live issuer key needs the addresses of the system that uses it (or allow any address on purpose)"))
    old = [x for x in (cur or "").split(",") if x]
    new = [x for x in v.split(",") if x]
    loosened = bool(old) and (not new or any(x not in old for x in new))
    return v, loosened


def _iss_new_key(c, oid, iss_id, uid, days):
    """A new key of issuer iss_id, valid for days days -> (the key itself, its row). Only its hash is stored."""
    tok = f"kis_{ISS_ENV}_" + secrets.token_urlsafe(32)
    now = now_utc()
    prefix = tok[:len(f"kis_{ISS_ENV}_") + 4]
    c.execute("INSERT INTO office_issuer_keys(issuer_id, org_id, token_hash, prefix, created_by, created_at, expires_at) VALUES(?,?,?,?,?,?,?)",
              (iss_id, oid, _token_hash(tok), prefix, uid, iso(now), iso(now + timedelta(days=days))))
    row = c.execute("SELECT * FROM office_issuer_keys WHERE token_hash=?", (_token_hash(tok),)).fetchone()
    return tok, row


def _iss_days(v, default, lo, hi, name):
    if v is None:
        return default
    if isinstance(v, bool):
        raise BadInput(tr("Invalid value: {0}", name))
    try:
        n = int(str(v).strip())
    except ValueError:
        raise BadInput(tr("Invalid value: {0}", name)) from None
    if not lo <= n <= hi:
        raise BadInput(tr("{0} must be between {1} and {2}", name, lo, hi))
    return n


def _key_public(k):
    now = now_utc()
    exp = parse_iso(k["expires_at"])
    return {"id": k["id"], "prefix": k["prefix"], "created_at": iso(parse_iso(k["created_at"])), "expires_at": iso(exp),
            "last_used_at": iso(parse_iso(k["last_used_at"])) if k["last_used_at"] else None,
            "revoked_at": iso(parse_iso(k["revoked_at"])) if k["revoked_at"] else None,
            "valid": not k["revoked_at"] and exp > now}


def iss_public(c, r):
    """An issuer for its admins: never a key's hash."""
    rg = c.execute("SELECT id, code, name FROM office_num_ranges WHERE id=? AND org_id=?", (r["range_id"], r["org_id"])).fetchone()
    keys = c.execute("SELECT * FROM office_issuer_keys WHERE issuer_id=? ORDER BY id DESC LIMIT 10", (r["id"],)).fetchall()
    ips = c.execute("SELECT ip, first_at, last_at, calls FROM office_issuer_ips WHERE issuer_id=? ORDER BY last_at DESC LIMIT 20", (r["id"],)).fetchall()
    payees = c.execute("SELECT COUNT(*) FROM office_issuer_payees WHERE issuer_id=? AND removed_at IS NULL", (r["id"],)).fetchone()[0]
    ts = lambda v: iso(parse_iso(v)) if v else None  # noqa: E731
    return {"id": r["id"], "name": r["name"], "mode": r["mode"], "environment": ISS_ENV,
            "range": {"id": r["range_id"], "code": rg["code"] if rg else "", "name": (rg["name"] or "") if rg else ""},
            "paused": bool(r["paused"]), "paused_reason": r["paused_reason"] or "", "paused_why": tr(ISS_PAUSE_WHY[r["paused_reason"]]) if r["paused_reason"] in ISS_PAUSE_WHY else "",
            "paused_at": ts(r["paused_at"]), "allowed_ips": [x for x in (r["allowed_ips"] or "").split(",") if x],
            "limits": _iss_limits(r), "keys": [_key_public(k) for k in keys],
            "addresses": [{"ip": x["ip"], "first_at": ts(x["first_at"]), "last_at": ts(x["last_at"]), "calls": int(x["calls"])} for x in ips],
            "payees": int(payees), "created_by": _who(c, r["created_by"]), "created_at": ts(r["created_at"]), "revoked_at": ts(r["revoked_at"])}


@app.get("/api/office/issuers")
def iss_list():
    """The issuers of the office area (admins): {issuers, admin (may change), environment, ranges (the open additional ranges
    an issuer can be set up for)}. 404 while the server / the operator does not allow issuers here."""
    c, uid, oid = _iss_ctx(write=False)
    _oid, role = office_where(c, uid)
    rows = c.execute("SELECT * FROM office_issuers WHERE org_id=? AND revoked_at IS NULL ORDER BY lower(name), id", (oid,)).fetchall()
    ranges = [{"id": r["id"], "code": r["code"], "name": r["name"] or ""} for r in c.execute(
        "SELECT id, code, name FROM office_num_ranges WHERE org_id=? AND closed_at IS NULL ORDER BY code, id", (oid,))]
    return jsonify(issuers=[iss_public(c, r) for r in rows], admin=role == "admin" and _oid == oid, environment=ISS_ENV, ranges=ranges,
                   address_needed=ISS_ENV == "live", days_max=ISS_DAYS, overlap_default=ISS_OVERLAP, overlap_max=ISS_OVERLAP_MAX,
                   limit_max={k: str(m) if kind == "money" else m for k, (kind, _d, m) in ISS_LIMITS.items()})


@app.post("/api/office/issuers")
def iss_create():
    """Org admin + sign-in confirmation. {name, range_id, allowed_ips?, any_address?, limits?, valid_days? (365)} -> 201
    {issuer, key} (the key is shown this once)."""
    c, uid, oid = _iss_ctx()
    b = body()
    b = b if isinstance(b, dict) else {}
    unknown = sorted(set(b) - {"name", "range_id", "allowed_ips", "any_address", "limits", "valid_days", "password"})
    if unknown:
        raise UnknownFields(unknown)
    name = re.sub(r"[\x00-\x1f]+", " ", str(b.get("name") or "")).strip()[:ISS_NAME_MAX]
    if not name:
        return err(tr("Please give the issuer a name"))
    try:
        rid = int(b.get("range_id"))
    except (TypeError, ValueError):
        return err(tr("Please select a number range"))
    write_lock(c, f"office_issuers_{int(oid)}")
    if not c.execute("SELECT 1 FROM office_num_ranges WHERE id=? AND org_id=? AND closed_at IS NULL", (rid, oid)).fetchone():
        return err(tr("Please select a number range"))
    if c.execute("SELECT COUNT(*) FROM office_issuers WHERE org_id=? AND revoked_at IS NULL", (oid,)).fetchone()[0] >= ISS_MAX:
        return err(tr("At most {0} invoice issuers per office", ISS_MAX), 409)
    lim = {k: d for k, (_kind, d, _m) in ISS_LIMITS.items()}
    lim.update(_iss_limits_clean(b.get("limits")))
    ips, _l = _iss_ips(b, "", ISS_ENV == "live")
    if "allowed_ips" not in b and b.get("any_address") is not True and ISS_ENV == "live":  # review F5
        raise BadInput(tr("A live issuer key needs the addresses of the system that uses it (or allow any address on purpose)"))
    days = _iss_days(b.get("valid_days"), ISS_DAYS, 1, ISS_DAYS, "valid_days")
    e = _iss_confirm(c, b)
    if e:
        return e
    ts = iso(now_utc())
    cols = ["org_id", "name", "range_id", "allowed_ips", "created_by", "created_at", "updated_at", *lim]
    r = c.execute(f"INSERT INTO office_issuers({', '.join(cols)}) VALUES({', '.join('?' * len(cols))}) RETURNING *",
                  (oid, name, rid, ips, uid, ts, ts, *lim.values())).fetchone()
    tok, key = _iss_new_key(c, oid, r["id"], uid, days)
    iss_log(c, oid, r["id"], "issuer_created", detail={"name": name, "range_id": rid, "allowed_ips": ips, "key": key["prefix"],
                                                       "expires_at": iso(parse_iso(key["expires_at"])), "limits": {k: str(v) for k, v in lim.items()}}, uid=uid)
    who = _who(c, uid)
    iss_tell(c, oid, r, "issuer_created", who=who, besides=uid)
    iss_tell(c, oid, r, "issuer_key", parse_iso(key["expires_at"]).date().isoformat(), who=who)
    bump(c)
    c.commit()
    return jsonify(issuer=iss_public(c, r), key=tok), 201


@app.patch("/api/office/issuers/<int:iid>")
def iss_patch(iid):
    """Org admin. {name?, limits?, allowed_ips?, any_address?}: raising a limit or loosening / removing the address rule needs
    the sign-in confirmation; lowering and tightening do not. The range and the mode never change."""
    c, uid, oid = _iss_ctx()
    b = body()
    b = b if isinstance(b, dict) else {}
    unknown = sorted(set(b) - {"name", "limits", "allowed_ips", "any_address", "password"})
    if unknown:
        raise UnknownFields(unknown)
    write_lock(c, f"office_issuers_{int(oid)}")
    r = _iss_row(c, oid, iid)
    f = {}
    if "name" in b:
        f["name"] = re.sub(r"[\x00-\x1f]+", " ", str(b.get("name") or "")).strip()[:ISS_NAME_MAX]
        if not f["name"]:
            return err(tr("Please give the issuer a name"))
    lim = _iss_limits_clean(b.get("limits"))
    raised = [k for k, v in lim.items() if v > Decimal(str(r[k]))]
    f.update(lim)
    ips, loosened = _iss_ips(b, r["allowed_ips"] or "", ISS_ENV == "live")
    f["allowed_ips"] = ips
    f = {k: v for k, v in f.items() if (Decimal(str(r[k])) != v if k in ISS_LIMITS else r[k] != v)}
    if not f:
        return jsonify(issuer=iss_public(c, r))
    if raised or loosened:
        e = _iss_confirm(c, b)
        if e:
            return e
    f["updated_at"] = iso(now_utc())
    c.execute(f"UPDATE office_issuers SET {', '.join(qi(k, ISS_COLS) + '=?' for k in f)} WHERE id=? AND org_id=?",
              (*[str(v) if isinstance(v, Decimal) else v for v in f.values()], iid, oid))
    keys = [k for k in f if k != "updated_at"]
    iss_log(c, oid, iid, "issuer_changed", detail={"before": {k: str(r[k]) for k in keys}, "after": {k: str(f[k]) for k in keys}}, uid=uid)
    what = N_("address rule") if "allowed_ips" in keys else N_("limits") if any(k in ISS_LIMITS for k in keys) else N_("name")
    iss_tell(c, oid, r, "issuer_changed", what, who=_who(c, uid), besides=uid, security=bool(raised or loosened))
    bump(c)
    c.commit()
    return jsonify(issuer=iss_public(c, _iss_row(c, oid, iid)))


@app.delete("/api/office/issuers/<int:iid>")
def iss_revoke(iid):
    """Org admin. Revokes the issuer for good: every key ends at once (no confirmation: it only takes access away)."""
    c, uid, oid = _iss_ctx()
    write_lock(c, f"office_issuers_{int(oid)}")
    r = _iss_row(c, oid, iid)
    iss_revoke_rows(c, oid, [iid], uid)
    iss_tell(c, oid, r, "issuer_revoked", who=_who(c, uid), besides=uid)
    bump(c)
    c.commit()
    return jsonify(ok=True)


def iss_revoke_rows(c, oid, ids, uid=None, why="admin"):
    """Revokes issuers ids of area oid and ends their keys (office/pbtransfer.py before a move, the route above). The caller
    commits. -> how many were revoked."""
    if not ids:
        return 0
    now = iso(now_utc())
    q = ",".join("?" * len(ids))
    with system_ctx(c):  # the area's own issuer rows (also before a move, which runs as the owner)
        n = c.execute(f"UPDATE office_issuers SET revoked_at=?, revoked_by=? WHERE org_id=? AND id IN ({q}) AND revoked_at IS NULL", (now, uid, oid, *ids)).rowcount
        c.execute(f"UPDATE office_issuer_keys SET revoked_at=?, revoked_by=? WHERE org_id=? AND issuer_id IN ({q}) AND revoked_at IS NULL", (now, uid, oid, *ids))
    for i in ids:
        iss_log(c, oid, i, "issuer_revoked", detail={"reason": why}, uid=uid)
    return n


@app.post("/api/office/issuers/<int:iid>/keys")
def iss_key_new(iid):
    """Org admin + sign-in confirmation. {valid_days? (365), overlap_days? (7, at most 14)} -> 201 {key, issuer}: a new key;
    the valid one before it runs out after overlap_days (0 = at once). At most ISS_KEYS_MAX valid keys: end one first (409)."""
    c, uid, oid = _iss_ctx()
    b = body()
    b = b if isinstance(b, dict) else {}
    unknown = sorted(set(b) - {"valid_days", "overlap_days", "password"})
    if unknown:
        raise UnknownFields(unknown)
    days = _iss_days(b.get("valid_days"), ISS_DAYS, 1, ISS_DAYS, "valid_days")
    overlap = _iss_days(b.get("overlap_days"), ISS_OVERLAP, 0, ISS_OVERLAP_MAX, "overlap_days")
    write_lock(c, f"office_issuers_{int(oid)}")
    r = _iss_row(c, oid, iid)
    now = now_utc()
    valid = [k for k in c.execute("SELECT * FROM office_issuer_keys WHERE issuer_id=? AND revoked_at IS NULL ORDER BY id", (iid,)).fetchall()
             if parse_iso(k["expires_at"]) > now]
    if len(valid) >= ISS_KEYS_MAX:
        return err(tr("This issuer has {0} valid keys already; end one first", ISS_KEYS_MAX), 409)
    e = _iss_confirm(c, b)
    if e:
        return e
    end = now + timedelta(days=overlap)
    for k in valid:  # the key before runs out after the overlap (never later than it would anyway)
        if parse_iso(k["expires_at"]) > end:
            c.execute("UPDATE office_issuer_keys SET expires_at=? WHERE id=?", (iso(end), k["id"]))
    tok, key = _iss_new_key(c, oid, iid, uid, days)
    iss_log(c, oid, iid, "issuer_key", detail={"key": key["prefix"], "expires_at": iso(parse_iso(key["expires_at"])), "overlap_days": overlap,
                                               "ends": [k["prefix"] for k in valid]}, uid=uid)
    iss_tell(c, oid, r, "issuer_key", parse_iso(key["expires_at"]).date().isoformat(), who=_who(c, uid))
    bump(c)
    c.commit()
    return jsonify(key=tok, issuer=iss_public(c, r)), 201


@app.delete("/api/office/issuers/<int:iid>/keys/<int:kid>")
def iss_key_end(iid, kid):
    """Org admin. Ends a key at once (always possible, no confirmation)."""
    c, uid, oid = _iss_ctx()
    r = _iss_row(c, oid, iid)
    k = c.execute("SELECT * FROM office_issuer_keys WHERE id=? AND issuer_id=? AND org_id=?", (kid, iid, oid)).fetchone()
    if k is None:
        raise Denied(404)
    if not k["revoked_at"]:
        c.execute("UPDATE office_issuer_keys SET revoked_at=?, revoked_by=? WHERE id=?", (iso(now_utc()), uid, kid))
        iss_log(c, oid, iid, "issuer_key_ended", detail={"key": k["prefix"]}, uid=uid)
        iss_tell(c, oid, r, "issuer_key_ended", who=_who(c, uid), besides=uid)
        bump(c)
    c.commit()
    return jsonify(issuer=iss_public(c, r))


@app.post("/api/office/issuers/<int:iid>/pause")
def iss_pause_post(iid):
    """Org admin. Pauses the issuer: every call of its keys is refused until a person resumes it."""
    c, uid, oid = _iss_ctx()
    r = _iss_row(c, oid, iid)
    if iss_pause(c, r, "admin", uid):
        bump(c)
    c.commit()
    return jsonify(issuer=iss_public(c, _iss_row(c, oid, iid)))


@app.post("/api/office/issuers/<int:iid>/resume")
def iss_resume(iid):
    """Org admin. Lets a paused issuer run again: after an admin's own pause at once, after any other pause (self-pause,
    restore, no admin, operator) with the sign-in confirmation. An area the operator has not unlocked stays off (404 above)."""
    c, uid, oid = _iss_ctx()
    b = body()
    b = b if isinstance(b, dict) else {}
    r = _iss_row(c, oid, iid)
    if not r["paused"]:
        return jsonify(issuer=iss_public(c, r))
    if r["paused_reason"] != "admin":
        e = _iss_confirm(c, b)
        if e:
            return e
    c.execute("UPDATE office_issuers SET paused=false, paused_reason='', paused_at=NULL, paused_by=NULL, updated_at=? WHERE id=? AND org_id=?",
              (iso(now_utc()), iid, oid))
    iss_log(c, oid, iid, "issuer_resume", detail={"after": r["paused_reason"]}, uid=uid)
    iss_tell(c, oid, r, "issuer_resumed", who=_who(c, uid), besides=uid)
    bump(c)
    c.commit()
    return jsonify(issuer=iss_public(c, _iss_row(c, oid, iid)))


@app.get("/api/office/issuers/<int:iid>/log")
def iss_log_get(iid):
    """The issuer's lines of the office log, newest first (?limit, at most 500): changes by admins and the issuer's own calls."""
    c, _uid, oid = _iss_ctx(write=False)
    _iss_row(c, oid, iid, live=False)
    try:
        lim = max(1, min(int(request.args.get("limit", 200)), 500))
    except ValueError:
        lim = 200
    rows = c.execute("SELECT * FROM office_doc_log WHERE org_id=? AND issuer_id=? ORDER BY id DESC LIMIT ?", (oid, iid, lim)).fetchall()
    out = []
    for r in rows:
        d = _log_public(c, r)
        out.append({"id": d["id"], "at": iso(parse_iso(d["at"])), "action": d["action"], "target": d["target"], "detail": d["detail"],
                    "by": "person" if d.get("user_id") else "issuer", "user_name": d.get("user_name") or ""})
    return jsonify(log=out)


# ---------------------------------------------------------------- the bank accounts allowed for an issuer (applied from #6819 on)
def _payee_public(c, oid, p):
    d = oc_dec_fields(c, oid, "office_issuer_payees", p)
    return {"id": d["id"], "label": d["label"], "holder": d["holder"], "iban": d["iban"], "bic": d["bic"], "ref_only": bool(d["ref_only"]),
            "created_at": iso(parse_iso(d["created_at"]))}


@app.get("/api/office/issuers/<int:iid>/payees")
def iss_payees(iid):
    """The bank accounts allowed for the issuer (admins). The key never reads them (it may only choose one by its id)."""
    c, _uid, oid = _iss_ctx(write=False)
    _iss_row(c, oid, iid)
    return jsonify(payees=[_payee_public(c, oid, p) for p in c.execute(
        "SELECT * FROM office_issuer_payees WHERE issuer_id=? AND org_id=? AND removed_at IS NULL ORDER BY id", (iid, oid)).fetchall()])


@app.post("/api/office/issuers/<int:iid>/payees")
def iss_payee_add(iid):
    """Org admin + sign-in confirmation. {label, holder (exactly as the bank has it), iban, bic?, ref_only? (a payment can only
    be matched by its reference)} -> 201 {payee}."""
    c, uid, oid = _iss_ctx()
    b = body()
    b = b if isinstance(b, dict) else {}
    unknown = sorted(set(b) - {"label", "holder", "iban", "bic", "ref_only", "password"})
    if unknown:
        raise UnknownFields(unknown)
    r = _iss_row(c, oid, iid)
    clean = lambda v, n: re.sub(r"[\x00-\x1f]+", " ", str(v or "")).strip()[:n]  # noqa: E731
    label, holder = clean(b.get("label"), ISS_LABEL_MAX), clean(b.get("holder"), ISS_HOLDER_MAX)
    iban = re.sub(r"\s+", "", str(b.get("iban") or "")).upper()
    bic = re.sub(r"\s+", "", str(b.get("bic") or "")).upper()
    if not holder:
        return err(tr("Please enter the account holder exactly as the bank has it"))
    if not _iban_ok(iban):
        return err(tr("Invalid value: {0}", "IBAN"))
    if bic and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?", bic):
        return err(tr("Invalid value: {0}", "BIC"))
    if "ref_only" in b and not isinstance(b["ref_only"], bool):
        return err(tr("Invalid value: {0}", "ref_only"))
    if c.execute("SELECT COUNT(*) FROM office_issuer_payees WHERE issuer_id=? AND removed_at IS NULL", (iid,)).fetchone()[0] >= ISS_PAYEES_MAX:
        return err(tr("At most {0} bank accounts per issuer", ISS_PAYEES_MAX), 409)
    e = _iss_confirm(c, b)
    if e:
        return e
    v = oc_enc_fields(c, oid, "office_issuer_payees", {"holder": holder, "iban": iban, "bic": bic})
    p = c.execute("INSERT INTO office_issuer_payees(issuer_id, org_id, label, holder, iban, bic, ref_only, created_by, created_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?) RETURNING *", (iid, oid, label or iban[-4:], v["holder"], v["iban"], v["bic"],
                                                            bool(b.get("ref_only")), uid, iso(now_utc()))).fetchone()
    shown = (label or "") + f" (…{iban[-4:]})"
    iss_log(c, oid, iid, "issuer_payee", detail={"payee": p["id"], "label": label, "iban_end": iban[-4:], "ref_only": bool(b.get("ref_only"))}, uid=uid)
    iss_tell(c, oid, r, "issuer_payee", shown.strip(), who=_who(c, uid), besides=uid, security=True)
    bump(c)
    c.commit()
    return jsonify(payee=_payee_public(c, oid, p)), 201


@app.delete("/api/office/issuers/<int:iid>/payees/<int:pid>")
def iss_payee_remove(iid, pid):
    """Org admin. Removes an allowed bank account (the row stays, marked removed: documents may name it)."""
    c, uid, oid = _iss_ctx()
    r = _iss_row(c, oid, iid)
    p = c.execute("SELECT * FROM office_issuer_payees WHERE id=? AND issuer_id=? AND org_id=? AND removed_at IS NULL", (pid, iid, oid)).fetchone()
    if p is None:
        raise Denied(404)
    c.execute("UPDATE office_issuer_payees SET removed_at=?, removed_by=? WHERE id=?", (iso(now_utc()), uid, pid))
    iban = oc_dec_fields(c, oid, "office_issuer_payees", p)["iban"] or ""
    iss_log(c, oid, iid, "issuer_payee_gone", detail={"payee": pid, "iban_end": iban[-4:]}, uid=uid)
    iss_tell(c, oid, r, "issuer_payee_gone", f"{p['label']} (…{iban[-4:]})", who=_who(c, uid), besides=uid)
    bump(c)
    c.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- daily, restore, operator, moves
ISS_TICK = {"at": 0.0}


def iss_tick(c, force=False):
    """Daily in the watchdog (notify/push.py): the admins hear of a key running out ISS_WARN_DAYS days before (once each);
    an issuer whose area has no admin any more pauses ("noadmin"); 2.1396.0 (#6701): drafts waiting longer than review_wait_h
    (office/issdocs.py isd_wait_check, once a day). -> notices sent."""
    import time
    if not force and time.time() - ISS_TICK["at"] < 6 * 3600:
        return 0
    ISS_TICK["at"] = time.time()
    n = 0
    now = now_utc()
    with system_ctx(c):  # every area's issuers (a background check without a person)
        rows = c.execute("SELECT k.id AS kid, k.expires_at, k.warned, i.* FROM office_issuer_keys k JOIN office_issuers i ON i.id=k.issuer_id "
                         "WHERE k.revoked_at IS NULL AND i.revoked_at IS NULL AND k.expires_at>? AND k.expires_at<=?",
                         (iso(now - timedelta(days=1)), iso(now + timedelta(days=max(ISS_WARN_DAYS) + 1)))).fetchall()
        issuers = c.execute("SELECT * FROM office_issuers WHERE revoked_at IS NULL AND NOT paused").fetchall()
    for r in rows:
        try:
            with c.savepoint():
                exp = parse_iso(r["expires_at"])
                left = (exp.date() - now.date()).days
                step = next((d for d in sorted(ISS_WARN_DAYS) if left <= d), None)
                done = set((r["warned"] or "").split(","))
                if step is None or str(step) in done:
                    continue
                newer = c.execute("SELECT 1 FROM office_issuer_keys WHERE issuer_id=? AND id<>? AND revoked_at IS NULL AND expires_at>? LIMIT 1",
                                  (r["id"], r["kid"], iso(exp))).fetchone()
                with system_ctx(c):  # the key's own row
                    c.execute("UPDATE office_issuer_keys SET warned=? WHERE id=?", (",".join(sorted(done | {str(step)} - {""})), r["kid"]))
                if newer:  # a newer key takes over: the old one runs out on purpose (the overlap)
                    continue
                if left <= 0 or exp <= now:
                    iss_tell(c, r["org_id"], r, "issuer_expired")
                else:
                    iss_tell(c, r["org_id"], r, "issuer_expiry", exp.date().isoformat())
                n += 1
        except Exception as e:  # noqa: BLE001 -- one key must not stop the others
            print("issuer expiry notice failed:", type(e).__name__, flush=True)
    for r in issuers:
        try:
            with c.savepoint():
                admins = iss_admins(c, r["org_id"])
                if not admins:
                    iss_pause(c, r, "noadmin")
                    n += 1
                elif r["created_by"] and r["created_by"] not in admins and _iss_once(c, r, "left", "once"):
                    # who set it up is no admin of the area any more: it keeps running (it belongs to the area), the admins hear it once
                    iss_tell(c, r["org_id"], r, "issuer_left", who=_who(c, r["created_by"]))
                    n += 1
                if admins:
                    from .issdocs import isd_wait_check
                    n += isd_wait_check(c, r)  # 2.1396.0 (#6701): drafts waiting longer than review_wait_h
        except Exception as e:  # noqa: BLE001
            print("issuer admin check failed:", type(e).__name__, flush=True)
    c.commit()
    return n


def iss_pause_all(c, why, oid=None, commit=True):
    """Pauses every issuer (of area oid) that runs: after a restore ("restore") or when the operator takes the unlock back
    ("operator"). Review F3: the pause itself is one statement for all of them, committed first; the log line and the alarm
    of each follow in a savepoint of its own (one that fails costs only its own notice). -> the paused rows."""
    now = iso(now_utc())
    with system_ctx(c):  # every area's issuers, or the one area
        rows = c.execute("UPDATE office_issuers SET paused=true, paused_reason=?, paused_at=?, paused_by=NULL WHERE revoked_at IS NULL "
                         "AND NOT paused" + (" AND org_id=?" if oid else "") + " RETURNING *", (why, now, *((oid,) if oid else ()))).fetchall()
    if commit:  # commit=False: inside the caller's transaction (the operator's switch commits with it)
        c.commit()
    failed = 0
    for r in rows:
        try:
            with c.savepoint():
                iss_log(c, r["org_id"], r["id"], "issuer_pause", detail={"reason": why}, name=r["name"])
                iss_tell(c, r["org_id"], r, "issuer_paused", ISS_PAUSE_WHY.get(why, why))
        except Exception as e:  # noqa: BLE001 -- paused anyway; its admins miss this one notice
            failed += 1
            print("issuer pause notice failed:", type(e).__name__, flush=True)
    if commit:
        c.commit()
    if failed:
        aa_now("security", f"issuer-pause:{why}:{int(now_utc().timestamp())}",
               N_("Invoice issuers were paused ({0}), but {1} of their notices could not be written; check the server log."), [why, str(failed)])
    return rows


def iss_moved(c, oid, name):
    """A personal office became a new organisation of the same id (office/web.py pb_move_post): its issuers run on; the
    person hears of it."""
    with system_ctx(c):
        rows = c.execute("SELECT * FROM office_issuers WHERE org_id=? AND revoked_at IS NULL", (oid,)).fetchall()
    for r in rows:
        iss_tell(c, oid, r, "issuer_moved", name)
    return len(rows)


def iss_count(c, oid):
    """The issuers of area oid that are not revoked (the preview of a move names them)."""
    with system_ctx(c):
        return c.execute("SELECT COUNT(*) FROM office_issuers WHERE org_id=? AND revoked_at IS NULL", (oid,)).fetchone()[0]


def iss_ids(c, oid):
    with system_ctx(c):
        return [r[0] for r in c.execute("SELECT id FROM office_issuers WHERE org_id=? AND revoked_at IS NULL", (oid,)).fetchall()]


def iss_spec(paths, op, ok, errs):
    """OpenAPI of the invoice issuer key's route (called from api/openapi.py). Documented with the scope office: an ordinary
    token never reaches it (403), an issuer key reaches nothing else."""
    lim = {"type": "object", "properties": {k: {"type": "string" if kind == "money" else "integer"} for k, (kind, _d, _m) in ISS_LIMITS.items()}}
    paths["/issuer"] = {"get": op(
        "The invoice issuer of this key (2.1381.0)", "Office",
        ok({"type": "object", "properties": {
            "name": {"type": "string"}, "environment": {"type": "string", "enum": ["test", "live"]},
            "mode": {"type": "string", "enum": ["review"], "description": "review: a person checks, finalises and sends every draft"},
            "range": {"type": "object", "properties": {"code": {"type": "string"}}},
            "key": {"type": "object", "properties": {"prefix": {"type": "string"}, "expires_at": {"type": "string", "format": "date-time"}}},
            "limits": lim, "tax_profile": {"type": "object", "properties": {"country": {"type": "string"}, "small_business": {"type": "boolean"}}}}})
        | errs("400", "403", "503"), [], scope="office",
        desc="Only for invoice issuer keys (kis_test_... / kis_live_..., set up by an admin in the office settings > Invoice issuers): "
             "such a key reaches only the routes below /issuer; every other route answers 401 / 403. Errors carry a name: "
             "issuer_paused (403, try again later), issuer_keys_off (403), address_refused (403), rate_limited (429, Retry-After), "
             "unavailable (503, Retry-After). Calls of other routes and of unknown ids count towards a pause of the issuer.")}

