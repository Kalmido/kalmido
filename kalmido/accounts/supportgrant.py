"""2.485.0 (#3939): support access only with the client's consent (hosted instances).

On a hosted instance (KALMIDO_HOSTED=1) the operator stays out of its clients' organisations and accounts (2.399.0, #2687:
accounts/orgs.py op_foreign_org / op_foreign_account answer "foreign" and every instance-admin way in answers 403). When a
client needs help, the client opens the door for a limited time -- never the operator:

  - a person grants support access to the own account (Settings > Account > Support access): the operator's admin ways into
    that account work again as on a self-hosted server (sign-in link, password link, its private projects, its agents) -- and
    into the person's own office (the organisation personal_of the person: P4, a freelancer's office follows the account);
  - an organisation admin grants it for the organisation: its name, members, roles, projects and agents.

A grant runs 1 hour, 1 day, 3 days or 7 days (SGA_HOURS), ends by itself and can be ended at any time by the person / by any
admin of the organisation. A new grant of the same scope replaces the open one. Every request in which the operator (an
instance admin) passed the guard only thanks to a grant is logged on the grant: time, who, method, route pattern and status
(never values or contents); reading the same route again, or the same refusal, within SGA_GET_GAP_S is one entry. 2.503.0 (#4307): so is every request
of a support session (a sign-in link the operator made through the grant, the session runs as the client: via 'support'), the
sign-in itself included; such an entry is marked as done by support and goes on the newest grant of the account. At most SGA_USES_MAX readings
per grant; a write goes only beyond SGA_CHANGES_MAX, counted (2.1350.0, #6502: changes were pushed out at 300 entries, and an entry
that hit a lock was dropped silently -- it goes to the background queue now). The client sees the grant and its log; the operator sees nothing of it except that the doors are open. An organisation grant holds only while the admin who
granted it is still an admin of the organisation (and it is not retired). Agents and API tokens cannot grant (a session or the
proxy sign-in only). A self-hosted server has no use for it: the routes answer hosted=false and refuse a grant (409).

2.1350.0 (#6502, decision of 16.11.2026): a support session reads only the person's private space, own office and the
organisations whose admins opened support access themselves (core/access.py _ctx_support, per request, never cached for the
account); its changes stand in the history marked as support (obj_history.via, a task's activity data.via); the person / the
organisation's admins hear in the bell (News "support") of an organisation's grant, the first use and an early stop, the person
who grants gets a security mail; a support sign-in is no known device of the client.

  GET    /api/support-access          {hosted, hours, account: grant|null, orgs: [{org_id, name, grant|null}], past: [grant]}
  POST   /api/support-access          {hours, org_id?} -> {grant}
  DELETE /api/support-access/<id>     ends a grant early -> {ok}
"""
import json
import re
from datetime import timedelta

from flask import g, has_request_context, jsonify, request

from ..core.config import app, COOKIE
from ..core.access import ACX_SUP_FOREIGN, ACX_SUPPORT_ORGS  # 2.1350.0 (#6502); 2.1397.0 (#6320): ACX_SUP_FOREIGN
from ..core.db import body, connect, db, err, iso, now_utc, parse_iso, usettings
from ..core.errors import Denied
from ..core.i18n import N_, lang, short_day, tr
from ..core.usertz import tz_of_s  # 2.1350.0 (#6502): the end of a grant in the security mail
from ..core.pg import insert_id, system_ctx
from ..core.env import env_bool
from .session import _token_hash, me
from .sessions import ses_end
from .bgjobs import bgj_add, bgj_fn  # 2.1350.0 (#6502): the log entries that could not be written at once
from .secmail import sec_mail  # 2.1350.0 (#6502)

SGA_HOURS = (1, 24, 72, 168)
SGA_USES_MAX = 300  # readings per grant (2.1350.0, #6502: only readings; was every entry)
SGA_CHANGES_MAX = 3000  # 2.1350.0 (#6502): writes per grant, refused ones too; beyond them the oldest go, counted (uses_dropped)
SGA_GET_GAP_S = 600
SGA_PAST = 10


def sga_hosted():
    return env_bool("KALMIDO_HOSTED", False)  # admin.hosting.hosted() / orgs._operator_apart (the same switch)


def sga_open(c, uid=None, oid=None, note=True):
    """The id of the open grant that lets the operator into account uid (org_id NULL) or organisation oid, else None. note: the
    current request of an instance admin is logged on the grant (sga_flush)."""
    now = iso(now_utc())
    with system_ctx(c):  # grants of other people's accounts and organisations: structure only, no content
        if oid:
            r = c.execute("SELECT s.id FROM support_grants s JOIN orgs o ON o.id=s.org_id JOIN org_members m ON m.org_id=s.org_id "
                          "AND m.user_id=s.user_id AND m.role='admin' JOIN users u ON u.id=s.user_id AND NOT u.disabled "
                          "WHERE s.org_id=? AND s.ended_at IS NULL AND s.ends_at>? "
                          "AND o.retired_at IS NULL ORDER BY s.id DESC LIMIT 1", (oid, now)).fetchone()
            if not r:  # a person's own office follows the person's account grant (P4)
                r = c.execute("SELECT s.id FROM support_grants s JOIN orgs o ON o.personal_of=s.user_id WHERE o.id=? AND s.org_id IS NULL "
                              "AND s.ended_at IS NULL AND s.ends_at>? ORDER BY s.id DESC LIMIT 1", (oid, now)).fetchone()
        elif uid:
            r = c.execute("SELECT id FROM support_grants WHERE user_id=? AND org_id IS NULL AND ended_at IS NULL AND ends_at>? "
                          "ORDER BY id DESC LIMIT 1", (uid, now)).fetchone()
        else:
            r = None
    if r and note:
        sga_note(r[0])
    return r[0] if r else None


def sga_until(c, uid):
    """The end of the open support access of account uid ('' = none), for the operator's account list."""
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        r = c.execute("SELECT ends_at FROM support_grants WHERE user_id=? AND org_id IS NULL AND ended_at IS NULL AND ends_at>? "
                      "ORDER BY id DESC LIMIT 1", (uid, iso(now_utc()))).fetchone()
    return r[0] if r else ""


def sga_note(gid):
    """Marks grant gid as used by the current request (an instance admin's only: the operator)."""
    if not has_request_context():
        return
    u = g.get("user")
    if u is None or not u["is_admin"]:
        return
    used = g.get("sga_used")
    if used is None:
        used = g.sga_used = set()
    used.add(int(gid))


def sga_link_exp(c, exp):
    """The end of a sign-in / password link made in this request: no later than the grants that let the operator make it
    (invite.invite_new). A link made without a grant keeps exp."""
    used = sorted(g.get("sga_used") or ()) if has_request_context() else []
    if not used:
        return exp
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        r = c.execute(f"SELECT MIN(ends_at) FROM support_grants WHERE id IN ({','.join('?' * len(used))})", used).fetchone()
    return min(exp, r[0]) if r and r[0] else exp


def sga_link_grant(c, uid, by):
    """2.1271.0 (#6497): the open support access of account uid through which instance admin `by` makes a sign-in link for it
    now (its id, stored on the link: user_invites.grant_id), else None (a parent's / an organisation admin's link, a self-hosted
    server). The session started with the link inherits it and holds only while exactly this grant is open."""
    if not sga_hosted() or not by or by == uid:
        return None
    with system_ctx(c):  # the maker's admin right and the account's grants: structure, no content
        if not c.execute("SELECT 1 FROM users WHERE id=? AND is_admin", (by,)).fetchone():
            return None
    return sga_open(c, uid=uid, note=False)


def sga_grant_ends(c, gid):
    """The end of grant gid while it is open (not ended, end ahead), else ''."""
    with system_ctx(c):  # support grants of other accounts (row-level security): structure, no content
        r = c.execute("SELECT ends_at FROM support_grants WHERE id=? AND org_id IS NULL AND ended_at IS NULL AND ends_at>?",
                      (gid, iso(now_utc()))).fetchone()
    return r[0] if r else ""


def sga_link_support(c, uid):
    """The end of the support access through which an instance admin made account uid's current sign-in link, or '' (a link of
    the person's parents / organisation admins, none, or its grant is no longer open). 2.1271.0 (#6497): exactly the link's
    grant (grant_id), not the latest planned end of any grant around the link's time."""
    if not sga_hosted():
        return ""
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        r = c.execute("SELECT grant_id FROM user_invites WHERE user_id=? AND kind='login' AND grant_id IS NOT NULL", (uid,)).fetchone()
    return sga_grant_ends(c, r[0]) if r else ""


def sga_link_refused(c, r):
    """2.1271.0 (#6497): True when sign-in link row r may not sign in: its support access is no longer open (ended early, run
    out), or it is an operator's link from before grant_id (made while a grant of the account was open, no grant_id: it would
    start a session without the support mark). Such a link was capped to its grant's end, at most SGA_HOURS: this check can go
    after 01.12.2026."""
    if r["grant_id"]:
        return not sga_grant_ends(c, r["grant_id"])
    if not sga_hosted() or not r["created_by"] or r["created_by"] == r["user_id"]:
        return False
    with system_ctx(c):  # the maker's admin right and the account's grants: structure, no content
        return bool(c.execute("SELECT 1 FROM users a JOIN support_grants s ON s.user_id=? AND s.org_id IS NULL WHERE a.id=? AND a.is_admin "
                              "AND s.created_at<=? AND s.ends_at>=? AND (s.ended_at IS NULL OR s.ended_at>=?) LIMIT 1",
                              (r["user_id"], r["created_by"], r["created_at"], r["created_at"], r["created_at"])).fetchone())


def sga_session_cap(c, uid, token_hash):
    """2.485.0 (#3939): a session started with a sign-in link the operator made through the account's support access ends with
    that access at the latest and is marked via 'support' (no credentials in it, sga_guard; ended with the access, sga_close).
    2.1271.0 (#6497): it carries the link's grant (sessions.grant_id): authenticate lets it in only while exactly that grant is
    open; the mark follows from the link's grant, whatever the maker's admin right is today."""
    if not sga_hosted():
        return
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        r = c.execute("SELECT i.grant_id, s.ends_at, i.created_by FROM user_invites i JOIN support_grants s ON s.id=i.grant_id "
                      "WHERE i.user_id=? AND i.kind='login'", (uid,)).fetchone()
        if not r:
            return False
        c.execute("UPDATE sessions SET via='support', grant_id=?, expires_at=LEAST(expires_at, ?) WHERE token_hash=?",
                  (r[0], r[1], token_hash))
    if has_request_context():  # 2.503.0 (#4307): the sign-in is the first entry of the log
        g.sga_support = uid
        g.sga_op = r[2]  # 2.1350.0 (#6502): who opened the session (the client's News at the first use names the operator)
        g.acx_sup_uid = int(uid)  # 2.1350.0 (#6502): the sign-in request reads with the narrowed context too (sga_acting)
    return True


def sga_sweep(c, uid):
    """2.1271.0 (#6497): account uid's sign-in links and support sessions whose grant is no longer open go (and support sessions
    from before grant_id): authenticate refuses them already, this takes them out of the session list and their push subscriptions."""
    now = iso(now_utc())
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        c.execute("DELETE FROM user_invites i WHERE i.user_id=? AND i.grant_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM support_grants s "
                  "WHERE s.id=i.grant_id AND s.ended_at IS NULL AND s.ends_at>?)", (uid, now))
        gone = [x[0] for x in c.execute("SELECT x.token_hash FROM sessions x WHERE x.user_id=? AND (x.via='support' OR x.grant_id IS NOT NULL) "
                                        "AND NOT EXISTS (SELECT 1 FROM support_grants s WHERE s.id=x.grant_id AND s.ended_at IS NULL AND s.ends_at>?)",
                                        (uid, now)).fetchall()]
    if gone:
        ses_end(c, uid, gone)


def sga_close(c, r, now):
    """Grant row r ends now (early): the links the operator made through the account's support access and the sessions started
    with such links end too. 2.1271.0 (#6497): by the grant they carry (grant_id), whoever made them and whatever their admin
    right is today; links from before grant_id as before (the operator's links since the oldest grant still ahead). An
    organisation's grant opens no account."""
    if r["org_id"]:
        return
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        since = c.execute("SELECT MIN(created_at) FROM support_grants WHERE user_id=? AND org_id IS NULL AND ends_at>?",
                          (r["user_id"], iso(now))).fetchone()[0] or r["created_at"]
        since = min(since, r["created_at"])
        # review F6: only the operator's sign-in links and support sessions (a parent's / an organisation admin's link stays)
        c.execute("DELETE FROM user_invites WHERE user_id=? AND kind='login' AND grant_id IS NULL AND created_at>=? AND created_by<>user_id "
                  "AND created_by IN (SELECT id FROM users WHERE is_admin)", (r["user_id"], since))
    sga_sweep(c, r["user_id"])


# 2.500.0 (#4070, decision of 03.11.2026): a support session (via 'support', sga_session_cap) reads and edits contents, nothing
# else (2.485.0, #3939, review F1, named only credentials; the audit found ways that outlive the consent beside them). A positive list:
# a write goes through only in a contents' area (SGA_CONTENT, the path's second segment) and when no segment of its path hands out
# access, leaves the account or cannot be taken back (SGA_NOT_CONTENT). Everything else, a new area too, is refused; reading stays.
SGA_CONTENT = frozenset((
    "tasks", "comments", "lists", "sections", "section-templates", "list-checks", "list-files", "list-tags", "deps", "tags", "fields",
    "filters", "sprints", "templates", "layouts", "folders", "folder-heads", "docs", "files", "attachments", "receipt-suggestions",
    "wiki", "sheets", "contacts", "events", "evcals", "notes", "notepads", "outline", "bookmarks", "habits", "pomo", "time", "budget",
    "clients", "office", "fsref", "videos", "books", "reading"))
SGA_NOT_CONTENT = frozenset((
    "public-link", "public-links", "regenerate", "members", "people", "groups", "owner", "org", "shares", "ext-links", "portal-link",
    "requests", "signoff", "signoffs", "agent", "agents", "ask-agent", "hooks-in", "error-hook", "repos", "folder-repo", "envs", "rules",
    "forms", "e2e", "keys", "lock", "scan-keys", "feed", "fetchers", "rights", "settings", "payonline", "peppol", "mail", "mail-notice",
    "mail-profile", "receipt-mail", "mail-addresses", "notify-template", "send", "send-mail", "purge", "anonymize", "pay-online", "move-space",
    "request-mail",  # 2.1254.0 (#6294): a project's request address is a mail inbox of the account: it would outlive the grant
    "issuers"))  # 2.1381.0 (#6699): invoice issuers hand out access to the office (keys, limits, pause, bank accounts)
SGA_PLAIN = frozenset(("/api/auth/logout", "/api/client-errors", "/api/settings", "/api/me"))  # /api/me: never SGA_GUARD_ME
SGA_GUARD_ME = {"password", "email", "username", "current_password", "new_password"}
SGA_GUARD_SCOPE = {"org_id", "org_visibility", "org_edit"}  # review F2: a PATCH that carries contents out of the account's scope
SGA_SECRET_READ = frozenset(("public-link", "public-links", "feed", "ext-links",  # review F1: answers with a working link: it would outlive the grant
                             "request-mail", "mail-addresses",  # 2.1254.0 (#6294): the secret inbox addresses (project requests, documents)
                             # review of 2.1254.0 (#6294): the office's receipt address, a letter's reply address (the person's document address)
                             "receipt-mail", "mail-info", "mail-draft"))
# review of 2.1254.0 (#6294): a GET that answers with an inbox address and is no content to read (the address is left out of
# the answers that are: docs settings, hub mails / inbox); tests/p21254_a_support_purge_test.py finds them in the source
SGA_GET_REFUSED_RX = re.compile(r"/api/office/privacy-sheets/\d+/mail")  # the subject's reply code of a sheet (made on the GET)
# 2.536.0 (#4363): the OIDC start would link a provider identity to the client's account and swap the support session for one
# without the mark (sga_close would not end it) -- refused like a write; the callback refuses a support session itself (oidc.py)
# review of 2.536.0: the HTTP Shortcuts ZIP makes a new drop token of the client on GET (users.py) -- it would outlive the grant
# 2.1254.0 (#6294): /api/me/mail answers with the secret addresses for new tasks by mail (personal, per project)
SGA_GET_REFUSED = frozenset(("/api/auth/oidc/start", "/api/me/share/httpshortcuts.zip", "/api/me/mail"))
SGA_REFUSED = N_("Support access does not hand out sign-in data or add people: the client does that")
# 2.538.0 (#4365, decision of 04.11.2026): a support session books nothing in the office; editing contents is neither
# booking nor changing the account's structure. Refused besides SGA_NOT_CONTENT, whatever the area: finalising, cancelling,
# unlocking, payments, the cash book, the bank, DATEV, period / logbook closing, bookkeeping imports, the move of the personal
# office, deleting for good (trash, purge, delete-all) and deleting a project. (methods or None = every write, the whole path)
SGA_NO_WRITE = tuple((m, re.compile(p)) for m, p in (
    (None, r"/api/office/docs/\d+/(finalize|unlock|credit|datev|fee|payments(/\d+)?)"),  # fee: changes a finalised reminder
    (None, r"/api/office/(cashbooks|cash-entries|bank|datev|books|legacy|periods|move)(/.*)?"),
    (None, r"/api/office/(logbook/close|trial/delete-all|series/\d+/run|gen-docs/\d+/final)"),
    (None, r"/api/office/(meals/\d+/(approve|unlock)|cards/statements/\d+/(confirm|reopen)|cards/lines/\d+/(match|unmatch))"),
    # 2.1254.0 (#6294): the office trash's delete for good is /api/office/trash/core/<kind>/<id> since 2.1067 (the old form stays)
    (("DELETE",), r"/api/office/trash/(\d+|core/[^/]+/\d+)"),
    (None, r"/api/tasks/purge-done|/api/lists/\d+/time/delete-all"),
    # 2.538.0 (#4365): the master data import changes the office's structure; the import undos delete for good
    (None, r"/api/office/(import|fixed-costs/delete|trips/delete)"),
    (("DELETE",), r"/api/lists/\d+"),
    # 2.538.0 (#4365, review F4): deleting one trip / fixed cost has the client's undo only, like the bulk delete above
    (("DELETE",), r"/api/office/(trips|fixed-costs)/\d+"),
    # 2.538.0 (#4365, review F6): the next running number (a gap in the invoice series) is the bookkeeping's structure
    (None, r"/api/office/number-ranges/[^/]+"),
    # 2.1397.0 (#6320, review #4788 (2)): a budget receipt and a project's notepad have no trash: their DELETE is for good
    (("DELETE",), r"/api/(budget/files|notepads)/\d+"),
))
# 2.1254.0 (#6294): routes that delete for good only with a query parameter (the guard never saw the query before): refused
# whenever the parameter is there at all, whatever its value. tests/p21254_a_support_purge_test.py checks every DELETE route that
# deletes for good against SGA_NO_WRITE / SGA_PURGE_ARGS.
SGA_PURGE_ARGS = tuple((m, re.compile(p), a) for m, p, a in (
    (("DELETE",), r"/api/tasks/\d+", "hard"),  # tasks/lifecycle.py task_delete
    (("DELETE",), r"/api/files/nodes/\d+", "purge"),  # files/web.py files_node_delete
    (("DELETE",), r"/api/notes/\d+", "empty"),  # collab/notes.py note_delete: an empty quick note, never into the trash
))
SGA_BOOKING = N_("A support session books nothing in the office and deletes nothing permanently: the client does that")
SGA_FOREIGN = ACX_SUP_FOREIGN  # 2.1397.0 (#6320): one text with the core's check


def sga_may_write(path):
    """True when a support session may write to path."""
    if path in SGA_PLAIN:
        return True
    seg = path.split("/")
    return len(seg) > 2 and seg[1] == "api" and seg[2] in SGA_CONTENT and not SGA_NOT_CONTENT.intersection(seg)


def sga_no_write(method, path, b, args=None):
    """2.538.0 (#4365): True when a support session may not make this write (SGA_NO_WRITE; a status change to / from paid is
    a payment). 2.1254.0 (#6294): args = the query parameters (SGA_PURGE_ARGS: a delete for good by parameter)."""
    if any((m is None or method in m) and rx.fullmatch(path) for m, rx in SGA_NO_WRITE):
        return True
    if args and any(method in m and a in args and rx.fullmatch(path) for m, rx, a in SGA_PURGE_ARGS):
        return True
    return bool(re.fullmatch(r"/api/office/docs/\d+/status", path)) and isinstance(b, dict) and b.get("status") == "paid"


def sga_is_support(c):
    """True when this request runs in a support session (the session cookie's row, via 'support'). Asked once per request."""
    if not has_request_context() or g.get("user") is None:
        return False
    if "sga_is_sup" not in g:
        tok = request.cookies.get(COOKIE) if g.get("auth_via") == "session" else None
        r = c.execute("SELECT via FROM sessions WHERE token_hash=?", (_token_hash(tok),)).fetchone() if tok else None
        g.sga_is_sup = bool(r) and r[0] == "support"
    return g.sga_is_sup


def sga_org_foreign(c, oid):
    """2.538.0 (#4365): True when this request is one of a support session and organisation oid is neither the person's own
    office nor under an open support access of its own (sga_open): a support session puts no contents there."""
    if not oid or not sga_is_support(c):
        return False
    try:
        oid = int(oid)
    except (TypeError, ValueError):
        return False  # not an organisation's id: the route answers it
    with system_ctx(c):  # the organisation's kind and grants: structure, no content
        r = c.execute("SELECT personal_of FROM orgs WHERE id=?", (oid,)).fetchone()
    if r is None:
        return False  # no such organisation: the route answers it (no hint for the support session)
    return r[0] != g.user["id"] and not sga_open(c, oid=oid, note=False)


def sga_list_foreign(c, lid):
    """2.538.0 (#4365): sga_org_foreign for the organisation of list lid (a task / document put into it)."""
    if isinstance(lid, bool) or not isinstance(lid, (int, str)) or not str(lid).isdigit() or not sga_is_support(c):
        return False
    with system_ctx(c):  # only the list's organisation id: structure, no content
        r = c.execute("SELECT org_id FROM lists WHERE id=?", (int(lid),)).fetchone()
    return bool(r) and sga_org_foreign(c, r[0])


# 2.538.0 (#4365, review F5): a new event / contact / note goes into the organisation of its container: the calendar (cal_id),
# the address book (book_id, an organisation's own book first) or the project in the path
SGA_BOX_ORG = {"cal_id": "SELECT org_id FROM ev_cals WHERE id=?", "book_id": "SELECT COALESCE(owner_org_id, org_id) FROM books WHERE id=?"}
# 2.1397.0 (#6320): the table of paths (SGA_PATH_ORG, 2.1254.0 #6294: tasks, attachments, lists and their child paths) went:
# the core's need_* functions refuse a support session's write into such an organisation themselves (core/access.py acx_sup_write)


def sga_box_foreign(c, method, path, b):
    """2.538.0 (#4365, review F5): True when a support session's write puts contents into an organisation without its own
    support access through a container: cal_id / book_id in the body (an object in the path: the core, #6320)."""
    if not sga_is_support(c):
        return False
    for k, q in SGA_BOX_ORG.items():
        v = b.get(k) if isinstance(b, dict) else None
        if isinstance(v, bool) or not isinstance(v, (int, str)) or not str(v).isdigit():
            continue  # none / not an id: the route answers it (an empty one picks the person's default)
        with system_ctx(c):  # only the container's organisation id: structure, no content
            r = c.execute(q, (int(v),)).fetchone()
        if r and sga_org_foreign(c, r[0]):
            return True
    return False


def sga_scope_check(c, oid):
    """2.538.0 (#4365): for the routes that work out an organisation themselves (a default workspace): Denied 403 code
    support_session when a support session would put contents into an organisation without support access."""
    if sga_org_foreign(c, oid):
        raise Denied(403, tr(SGA_FOREIGN), data={"code": "support_session"})


def sga_session_mark(c, token_hash, uid):
    """2.503.0 (#4307): the current request is one of a support session: it goes into the client's log (sga_flush). Called by
    authenticate, so a request an early gate refuses is listed too, a reading as well as a write. Only a hosted server makes such sessions.
    2.1350.0 (#6502): called before g.user is set; marks the request for the narrowed reading context (g.acx_sup_uid,
    core/access.py acx_of) and answers sga_is_support without a second query."""
    if not sga_hosted():
        return
    r = c.execute("SELECT via FROM sessions WHERE token_hash=?", (token_hash,)).fetchone()
    g.sga_is_sup = bool(r) and r[0] == "support"
    if g.sga_is_sup:
        g.acx_sup_uid = int(uid)
        if request.method != "OPTIONS":
            g.sga_support = int(uid)


def sga_acting(uid=None):
    """2.1350.0 (#6502): True when the current request runs in a support session (of account uid, when given). No query: the
    mark authenticate set (sga_session_mark) or a sign-in through a support link in this request (sga_session_cap)."""
    if not has_request_context():
        return False
    s = g.get("acx_sup_uid")
    return bool(s) and (uid is None or int(uid) == s)


def sga_orgs_readable(c, uid, oids):
    """2.1350.0 (#6502, decision of 16.11.2026): of organisations oids (the memberships of account uid), those a support session
    of uid reads: uid's own office and organisations with an open support access of their own (the conditions of sga_open).
    Never cached beyond the request (core/access.py: the narrowed context is not the account's). The organisations' grants
    this request reads through are used by it: the request goes on their logs too (the organisation's admins see it, sga_flush)."""
    oids = [int(o) for o in oids or ()]
    if not oids:
        return ()
    with system_ctx(c):  # the organisations' kind and grants: structure, no content
        rows = c.execute(
            f"SELECT o.id, o.personal_of, (SELECT s.id FROM support_grants s JOIN org_members m ON m.org_id=s.org_id AND m.user_id=s.user_id "
            "AND m.role='admin' JOIN users u ON u.id=s.user_id AND NOT u.disabled WHERE s.org_id=o.id AND s.ended_at IS NULL AND s.ends_at>? "
            f"ORDER BY s.id DESC LIMIT 1) AS gid FROM orgs o WHERE o.id IN ({','.join('?' * len(oids))}) AND o.retired_at IS NULL",
            (iso(now_utc()), *oids)).fetchall()
    ok = {r[0] for r in rows if r[1] == int(uid) or r[2]}
    gids = {int(r[2]) for r in rows if r[2] and r[1] != int(uid)}
    if gids and has_request_context():
        g.sga_used = {*(g.get("sga_used") or ()), *gids}
    return tuple(o for o in oids if o in ok)


ACX_SUPPORT_ORGS[0] = sga_orgs_readable  # core/access.py _ctx_support (accounts sits above core)


@app.before_request
def sga_guard():
    if g.get("auth_via") != "session" or g.get("user") is None or request.method == "OPTIONS":
        return None
    if request.method in ("GET", "HEAD"):
        p = request.path
        if ((p in SGA_GET_REFUSED or (p.startswith("/api/") and p.rsplit("/", 1)[-1] in SGA_SECRET_READ) or SGA_GET_REFUSED_RX.fullmatch(p))
                and sga_is_support(db())):
            return jsonify(error=tr(SGA_REFUSED), code="support_session"), 403
        return None
    c = db()
    if not sga_is_support(c):
        return None
    # 2.500.0 (#4070): every write of a support session stands on the grant's log, a refused one too (sga_flush): the client sees it
    gid = sga_open(c, uid=g.user["id"], note=False)
    if gid:
        g.sga_used = {*(g.get("sga_used") or ()), int(gid)}
        g.sga_support = g.user["id"]
    p = request.path
    hit = not sga_may_write(p)
    b = request.get_json(silent=True) if request.is_json else None
    if not hit and request.method == "PATCH":
        hit = isinstance(b, dict) and bool(set(b) & (SGA_GUARD_ME if p == "/api/me" else SGA_GUARD_SCOPE))
    if hit:
        return jsonify(error=tr(SGA_REFUSED), code="support_session"), 403
    if sga_no_write(request.method, p, b, request.args):  # 2.538.0 (#4365): no booking, nothing deleted for good
        return jsonify(error=tr(SGA_BOOKING), code="support_session"), 403
    # 2.538.0 (#4365): contents go into no organisation without its own support access (a new object's org_id, a list_id)
    if (isinstance(b, dict) and (sga_org_foreign(c, b.get("org_id")) or sga_list_foreign(c, b.get("list_id")))) \
            or sga_box_foreign(c, request.method, p, b):  # review F5: through a calendar, an address book (a path: the core, #6320)
        return jsonify(error=tr(SGA_FOREIGN), code="support_session"), 403
    return None


def _route():
    """The route pattern, never the address: a path without a route could carry a value (2.503.0, #4307)."""
    r = request.url_rule
    return r.rule[:120] if r is not None else "(unknown)"


def sga_read_again(uses, e, now):
    """Entry e is a reading or a refused request the log of a grant already has within SGA_GET_GAP_S (2.503.0, #4307: anywhere in
    that time, not only as the last entry: the app reads a few routes in turn, and that alone filled the log; review: refused
    requests in a row must not push the readings out of the log, a request that went through always counts)."""
    if e["m"] not in ("GET", "HEAD") and e["s"] < 400:
        return False
    since = now - timedelta(seconds=SGA_GET_GAP_S)
    for u in reversed(uses):
        if not isinstance(u, dict):
            continue
        at = parse_iso(u.get("at") or "")
        if at is None or at <= since:
            return False
        if (u.get("m"), u.get("r"), u.get("by"), u.get("s"), u.get("sup")) == (e["m"], e["r"], e["by"], e["s"], e.get("sup")):
            return True
    return False


def sga_is_reading(u):
    """2.1350.0 (#6502): log entry u is a reading (GET / HEAD); every other entry is a write, refused or not, and is kept."""
    return not isinstance(u, dict) or u.get("m") in ("GET", "HEAD")


def sga_trim(uses):
    """2.1350.0 (#6502): uses within the log's limits -> the number of entries dropped (the oldest first). Readings above
    SGA_USES_MAX go; a write only above SGA_CHANGES_MAX (was: at 300 entries the oldest change went once no reading was left)."""
    n = 0
    reads = [i for i, u in enumerate(uses) if sga_is_reading(u)]
    over = set(reads[:max(0, len(reads) - SGA_USES_MAX)])
    writes = [i for i, u in enumerate(uses) if not sga_is_reading(u)]
    over |= set(writes[:max(0, len(writes) - SGA_CHANGES_MAX)])
    if over:
        uses[:] = [u for i, u in enumerate(uses) if i not in over]
        n = len(over)
    return n


def sga_log_write(c, gids, sup, e, now, op=None, wait="2s"):
    """2.1350.0 (#6502): entry e on the grants gids (and, for a support session of account sup, on its newest grant) in the
    caller's transaction (system context, the caller commits). A grant whose log was empty is used for the first time: the
    client / the organisation's admins hear of it (sga_tell, actor op = the operator). Raises on a database error (the
    caller decides: sga_flush hands the entry to the background, the background's run fails visibly)."""
    gids = {int(x) for x in gids or ()}
    pushes = []
    with system_ctx(c):  # an organisation's grant is behind row-level security
        c.execute(f"SET LOCAL lock_timeout = '{wait}'")  # review F7: never stall a response behind the request's own locks
        if sup:  # 2.503.0 (#4307): a reading or the sign-in of a support session goes on the account's newest grant
            row = c.execute("SELECT id FROM support_grants WHERE user_id=? AND org_id IS NULL ORDER BY id DESC LIMIT 1", (int(sup),)).fetchone()
            if row:
                gids.add(int(row[0]))
        for gid in sorted(gids):
            row = c.execute("SELECT * FROM support_grants WHERE id=? FOR UPDATE", (gid,)).fetchone()
            if not row:
                continue
            try:
                uses = json.loads(row["uses"] or "[]")
            except ValueError:
                uses = []
            if not isinstance(uses, list):
                uses = []
            if sga_read_again(uses, e, now):
                continue  # the same reading / refusal again: one entry
            first = not uses
            uses.append(e)
            n = sga_trim(uses)
            c.execute("UPDATE support_grants SET uses=?, uses_dropped=uses_dropped+? WHERE id=?",
                      (json.dumps(uses, separators=(",", ":")), n, gid))
            if first and not op and sup:  # a later request of a support session: the operator who made its sign-in link
                x = c.execute("SELECT created_by FROM user_invites WHERE user_id=? AND kind='login' AND grant_id IS NOT NULL "
                              "ORDER BY created_at DESC LIMIT 1", (int(sup),)).fetchone()
                op = x[0] if x else None
            if first and op:  # #6977 F3: the entry has priority -- a failing bell (News, push) never takes it along
                try:
                    with c.savepoint():
                        pushes += sga_tell(c, row, "start", op)
                except Exception as x:  # noqa: BLE001 - a failing bell (any error of a push channel) never drops the log entry (#6977 F3)
                    print("support access log: bell of the first use failed:", type(x).__name__, flush=True)
    return pushes


@app.after_request
def sga_flush(resp):
    """Writes the uses of this request on their grants (own connection: a reading request commits nothing). 2.1350.0 (#6502):
    an entry that cannot be written now (a lock held longer than 2 s, a database error) goes to the background queue
    (bgjobs "sga:log", which waits longer and retries) instead of being dropped."""
    used = g.get("sga_used") if has_request_context() else None
    sup = g.get("sga_support") if has_request_context() else None
    if not used and not sup:
        return resp
    now = now_utc()
    try:  # 2.1350.0 (#6502, review F6): building the entry belongs to the log too - an error here never breaks the answer
        e = {"at": iso(now), "by": int(sup or g.user["id"]), "m": request.method[:8], "r": _route(), "s": int(resp.status_code)}
        if sup:  # 2.500.0 (#4070): done in a support session, not by the person
            e["sup"] = 1
        op = g.get("sga_op") if sup else g.user["id"]  # the operator: the link's maker (a support session) or the admin himself
        gids = sorted({int(gid) for gid in used or ()})
    except Exception as x:  # noqa: BLE001
        print("support access log error:", type(x).__name__, flush=True)
        return resp
    try:
        c = connect()
        try:
            pushes = sga_log_write(c, gids, sup, e, now, op)
            c.commit()
        finally:
            c.close()
        sga_push(pushes)
    except Exception as x:  # noqa: BLE001  the log never breaks a request; the entry goes to the background instead
        print("support access log: deferred:", type(x).__name__, flush=True)
        try:
            bgj_add("sga:log", gids, int(sup or 0), e, int(op or 0))
        except Exception as y:  # noqa: BLE001
            print("support access log error:", type(y).__name__, flush=True)
    return resp


@bgj_fn("sga:log", free=True)  # (#6951, reader F4): the client's record of the operator's access, also while its organisation moves
def _sga_log_bg(gids, sup, e, op):
    """2.1350.0 (#6502): an entry sga_flush could not write right away; a failed run is retried (bgjobs) and stays as a failed row."""
    c = connect()
    try:
        pushes = sga_log_write(c, gids, sup or None, e, parse_iso(e.get("at") or "") or now_utc(), op or None, wait="30s")
        c.commit()
    finally:
        c.close()
    sga_push(pushes)


# 2.1350.0 (#6502): the bell (News "support", row "support" of the notification settings, News and push on by default) lives
# in the domain layer: collab/news.py registers SGA_BELL["tell"] (c, grant row, stage, actor) -> pushes and SGA_BELL["push"]
SGA_BELL = {}


def sga_tell(c, r, stage, actor):
    """2.1350.0 (#6502): News "support" about grant row r -- stage 'grant' (an organisation's grant opened: its other admins),
    'start' (its first use: the person, for an organisation every admin), 'end' (ended early: the same) -- never to actor
    (who did it). Returns the pushes for after the commit (sga_push). The caller commits."""
    fn = SGA_BELL.get("tell")
    return fn(c, r, stage, actor) if fn else []


def sga_push(pushes):
    """2.1350.0 (#6502): the pushes of sga_tell, after the commit, through the push queue."""
    fn = SGA_BELL.get("push")
    if pushes and fn:
        fn(pushes)


def sga_mail(c, r):
    """2.1350.0 (#6502): a security mail to the person who opened grant row r (secmail.py "support" / "support_org": if it
    was not them, they act at once). The time in the person's zone and language. Never raises."""
    try:
        lg = lang(c, r["user_id"])
        at = parse_iso(r["ends_at"]).astimezone(tz_of_s(usettings(c, r["user_id"])))
        until = f"{short_day(at.date(), lg, year=True)} {at:%H:%M}"
        if r["org_id"]:
            with system_ctx(c):  # the organisation's name (the person administers it)
                o = c.execute("SELECT name FROM orgs WHERE id=?", (r["org_id"],)).fetchone()
            sec_mail(c, r["user_id"], "support_org", o["name"] if o else "?", until)
        else:
            sec_mail(c, r["user_id"], "support", until)
    except Exception as x:  # noqa: BLE001 - the grant stands without the mail
        print("support access mail skipped:", type(x).__name__, flush=True)


def _names(c, ids):
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    with system_ctx(c):  # the operator's and the granting admin's names, shown to the client
        rows = c.execute(f"SELECT id, display_name, username FROM users WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    return {r["id"]: r["display_name"] or r["username"] for r in rows}


def sga_public(c, r, names=None):
    now = iso(now_utc())
    try:
        uses = json.loads(r["uses"] or "[]")
    except ValueError:
        uses = []
    uses = [u for u in uses if isinstance(u, dict)]
    if names is None:
        names = _names(c, [r["user_id"], r["ended_by"]] + [u.get("by") for u in uses])
    return {"id": r["id"], "org_id": r["org_id"], "created_at": r["created_at"], "ends_at": r["ends_at"], "ended_at": r["ended_at"] or "",
            "dropped": int(r["uses_dropped"] or 0),  # 2.1350.0 (#6502): the oldest entries beyond the log's limits
            "active": not r["ended_at"] and r["ends_at"] > now, "by": names.get(r["user_id"], ""),
            "ended_by": names.get(r["ended_by"], "") if r["ended_by"] else "",
            "uses": [{"at": u.get("at") or "", "by": tr("Support access") if u.get("sup") else names.get(u.get("by"), ""), "method": u.get("m") or "", "route": u.get("r") or "",
                      "status": u.get("s") or 0} for u in reversed(uses)]}


def _need_person():
    """A person in a session (or the proxy sign-in) -- never an agent or an API token: a door into the account."""
    if g.user is None or (g.user["kind"] or "user") == "agent" or g.get("auth_via") not in ("session", "proxy"):
        raise Denied(403, tr("Only you can grant support access, signed in in the app"))


def _my_orgs(c):
    """The organisations the current person administers (not a personal office, not retired): [(id, name)]."""
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        return [(r["id"], r["name"]) for r in c.execute(
            "SELECT o.id, o.name FROM orgs o JOIN org_members m ON m.org_id=o.id WHERE m.user_id=? AND m.role='admin' "
            "AND o.personal_of IS NULL AND o.retired_at IS NULL ORDER BY o.name, o.id", (me(),)).fetchall()]


def _may_end(c, r):
    if r["org_id"]:
        with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
            return bool(c.execute("SELECT 1 FROM org_members WHERE org_id=? AND user_id=? AND role='admin'", (r["org_id"], me())).fetchone())
    return r["user_id"] == me()


@app.get("/api/support-access")
def support_access_get():
    c = db()
    orgs = _my_orgs(c)
    oids = [o for o, _n in orgs]
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        q = "SELECT * FROM support_grants WHERE (user_id=? AND org_id IS NULL)"
        args = [me()]
        if oids:
            q += f" OR org_id IN ({','.join('?' * len(oids))})"
            args += oids
        rows = c.execute(q + " ORDER BY id DESC LIMIT 200", args).fetchall()
    pub = [sga_public(c, r) for r in rows]
    open_ = {}
    for p in pub:
        if p["active"]:
            open_.setdefault(p["org_id"], p)
    return jsonify(hosted=sga_hosted(), hours=list(SGA_HOURS), account=open_.get(None),
                   orgs=[{"org_id": o, "name": n, "grant": open_.get(o)} for o, n in orgs],
                   past=[p for p in pub if not p["active"]][:SGA_PAST])


@app.post("/api/support-access")
def support_access_grant():
    _need_person()
    c = db()
    if not sga_hosted():
        return err(tr("Support access is only needed on a hosted server"), 409)
    b = body()
    if not isinstance(b, dict):
        b = {}
    h = b.get("hours")
    if isinstance(h, bool) or h not in SGA_HOURS:
        return err(tr("Invalid value: {0}", "hours"))
    oid = b.get("org_id")
    if oid is not None:
        if isinstance(oid, bool) or not isinstance(oid, int) or oid not in [o for o, _n in _my_orgs(c)]:
            raise Denied(403, tr("Only an admin of the organisation can grant support access to it"))
    now = now_utc()
    with system_ctx(c):  # the grants of an organisation are its admins' together (row-level security: system)
        if oid is None:
            c.execute("UPDATE support_grants SET ended_at=?, ended_by=? WHERE user_id=? AND org_id IS NULL AND ended_at IS NULL",
                      (iso(now), me(), me()))
        else:
            c.execute("UPDATE support_grants SET ended_at=?, ended_by=? WHERE org_id=? AND ended_at IS NULL", (iso(now), me(), oid))
        gid = insert_id(c, "INSERT INTO support_grants(user_id, org_id, created_at, ends_at) VALUES(?,?,?,?)",
                        (me(), oid, iso(now), iso(now + timedelta(hours=h))))
        r = c.execute("SELECT * FROM support_grants WHERE id=?", (gid,)).fetchone()
    if oid is None:  # 2.1271.0 (#6497): the replaced grant's links and sessions end with it (each holds only its own grant)
        sga_sweep(c, me())
    # 2.1350.0 (#6502): an organisation's other admins hear of it in the bell, the person who granted it gets a security mail
    pushes = sga_tell(c, r, "grant", me()) if oid else []
    sga_mail(c, r)
    c.commit()
    sga_push(pushes)
    print("support access granted:", "org" if oid else "account", f"#{oid or me()}", f"{h} h", flush=True)
    return jsonify(grant=sga_public(c, r))


@app.delete("/api/support-access/<int:gid>")
def support_access_end(gid):
    _need_person()
    c = db()
    with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
        r = c.execute("SELECT * FROM support_grants WHERE id=?", (gid,)).fetchone()
    if not r or not _may_end(c, r):
        return err(tr("Not found"), 404)
    if not r["ended_at"]:
        now = now_utc()
        with system_ctx(c):  # support grants of other accounts / organisations (row-level security): structure, no content
            c.execute("UPDATE support_grants SET ended_at=?, ended_by=? WHERE id=? AND ended_at IS NULL", (iso(now), me(), gid))
        sga_close(c, r, now)
        pushes = sga_tell(c, r, "end", me())  # 2.1350.0 (#6502): an organisation's other admins (the person ended it themselves)
        c.commit()
        sga_push(pushes)
        print("support access ended:", f"grant #{gid}", flush=True)
    return jsonify(ok=True)
