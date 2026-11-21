"""2.115.0 B (#2062): active sessions -- Settings > Account > Active sessions.

A person sees their own browser sessions (device and browser read from the User-Agent, how they signed in, since when,
last activity, until when) and ends one of them or all others. Nothing new about the client is stored beyond a shortened
User-Agent: no address, no location. Outwards a session is named by a short public id (sid, derived from the token hash
with another hash), never by the token hash itself. last_seen_at is written at most every SES_TOUCH seconds per session
(an in-process throttle plus a condition in the UPDATE), not on every request. Ending a session also removes the push
subscriptions made in it (push_subs.session_hash); older subscriptions ('' = unknown session) stay. Agent tokens are no
sessions (agents never get a cookie session, see authenticate) and are not touched here.
A child account reads the list like its other account settings and ends sessions only after the parents' PIN
(family/pin.py PIN_GUARD)."""
import hashlib
import importlib
import re
import threading
import time
from datetime import timedelta

from flask import g, jsonify, request

from ..core.config import app, COOKIE
from ..core.i18n import tr
from ..core.db import db, err, iso, now_utc
from ..accounts.session import _token_hash, me
from ..core.ephem import eph_drop_uid  # #6498
from .accessways import ACCESS_WAYS  # #7633

SES_TOUCH = 300  # s: last activity is written at most this often per session
SES_UA_MAX = 200
_seen, _seen_lock = {}, threading.Lock()


def ses_sid(token_hash):
    """The public id of a session (16 hex characters; the token hash never leaves the server)."""
    return hashlib.sha256(("sid:" + token_hash).encode()).hexdigest()[:16]


def ses_ua():
    """The request's User-Agent, control characters removed, shortened."""
    return re.sub(r"[\x00-\x1f<>]", "", request.headers.get("User-Agent") or "")[:SES_UA_MAX]


def ses_current_hash():
    """The token hash of this request's cookie session, or None (proxy login, no cookie)."""
    tok = request.cookies.get(COOKIE) if g.get("auth_via") == "session" else None
    return _token_hash(tok) if tok else None


def ses_touch(c, token_hash):
    """Records the activity of a session: at most every SES_TOUCH seconds (no UPDATE per request)."""
    now = time.monotonic()
    with _seen_lock:
        if now - _seen.get(token_hash, -SES_TOUCH) < SES_TOUCH:
            return
        _seen[token_hash] = now
        if len(_seen) > 5000:  # forget idle sessions
            for k in [k for k, v in _seen.items() if now - v >= SES_TOUCH]:
                _seen.pop(k, None)
    t = now_utc()
    # 2.1115.0 (#5951): last_seen_at is TIMESTAMPTZ, NULL = never seen (was ''; NULL < x is no row)
    n = c.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=? AND (last_seen_at IS NULL OR last_seen_at<?)",
                  (iso(t), token_hash, iso(t - timedelta(seconds=SES_TOUCH)))).rowcount
    if n:
        c.commit()  # only the session row is written so far in this request


def ses_end(c, uid, hashes=None, keep=None, expired=None):
    """THE way a session ends on the server (#6500): the sessions and the push subscriptions made in them, in one place for
    every caller (a logout, "end the others", a new password, a disabled account, start_session, the clean-up of
    admin/dataretention.py, a backup restore). uid: the account (None = by the hashes alone, or every account); hashes: the
    token hashes to end (None = every session of uid); keep: a token hash that stays; expired: a time - only the sessions
    that ran out before it, and the subscriptions whose session is gone already (a sign-in of before #6500 left them).
    '' = a subscription bound to no session (a proxy login, from before 2.115): stays. The send asks the same
    (notify/push.py webpush_user: only subscriptions of a living session). The caller commits. Returns the sessions ended."""
    w, a = "TRUE", []
    if uid is not None:
        w, a = w + " AND user_id=?", a + [uid]
    if hashes is not None:
        hashes = [h for h in hashes if h]
        if not hashes:
            return 0
        w, a = w + " AND token_hash IN (" + ",".join("?" * len(hashes)) + ")", a + hashes
    if keep:
        w, a = w + " AND token_hash<>?", a + [keep]
    if expired is not None:
        w, a = w + " AND expires_at<?", a + [iso(expired)]
    c.execute(f"DELETE FROM push_subs WHERE session_hash<>'' AND session_hash IN (SELECT token_hash FROM sessions WHERE {w})", a)
    n = c.execute(f"DELETE FROM sessions WHERE {w}", a).rowcount or 0
    if expired is not None:
        c.execute("DELETE FROM push_subs WHERE session_hash<>'' AND NOT EXISTS (SELECT 1 FROM sessions s WHERE s.token_hash=push_subs.session_hash)")
    return n


def ses_pend_end(c, uid):
    """#6498: the account's open sign-in tickets (the second step or the enrolment begun with the old password, ns pend of
    core/ephem.py) - the row "pending" of ACCESS_WAYS."""
    eph_drop_uid("pend", uid)


def ses_access_end(c, uid, tokens=True):
    """#7633: what a new password and the first second factor end besides the sessions - ONE place, read from the one list of
    every way into and out of an account (accounts/accessways.py ACCESS_WAYS; tests/access_ways_test.py holds every table with a
    key against it). Callers: the own change (PATCH /api/me, after ses_end), the admin's reset (PATCH /api/users/<id>), the reset
    link (invite.py) and the first second factor (login.py _end_other_sessions). end "always" runs every time (the sign-in
    tickets, the scan inbox keys and receipt fetchers); with tokens (the dialog's tick, 2.539.0 B #4375; a reset and the first
    second factor always) the rows "tick" end (app passwords, own API tokens - an agent's stay -, feed links, the upload token)
    and the rows "off" are switched off with the reason 'password' and their queue emptied (the person's own webhooks and
    forwardings, #7633: they are switched on again in the settings). The caller commits."""
    for w in ACCESS_WAYS:
        if w["end"] not in ("always", "tick", "off") or (w["end"] != "always" and not tokens):
            continue
        for q in w.get("sql", ()):
            c.execute(q, (uid,))
        if w.get("fn"):
            mod, fn = w["fn"].split(":")
            getattr(importlib.import_module(mod, __package__), fn)(c, uid)


def ses_device(ua):
    """(device, browser, system) read from a User-Agent, '' when unknown (a small table, no library)."""
    ua = ua or ""
    browser = next((n for p, n in (("Edg/", "Edge"), ("EdgA/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser/", "Samsung Internet"),
                                   ("Firefox/", "Firefox"), ("FxiOS/", "Firefox"), ("CriOS/", "Chrome"), ("Chrome/", "Chrome"),
                                   ("Safari/", "Safari")) if p in ua), "")
    system = next((n for p, n in (("iPhone", "iOS"), ("iPad", "iPadOS"), ("Android", "Android"), ("CrOS", "ChromeOS"),
                                  ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Macintosh", "macOS"), ("Linux", "Linux")) if p in ua), "")
    device = "phone" if ("Mobile" in ua or "iPhone" in ua) and "iPad" not in ua else "tablet" if ("iPad" in ua or system == "Android") else \
        "computer" if system else ""
    if not browser and ua and not system:
        browser = re.split(r"[/ ]", ua, 1)[0][:40]  # an app or tool (curl, a native client)
    return device, browser, system


def ses_public(r, cur):
    device, browser, system = ses_device(r["user_agent"])
    return {"sid": ses_sid(r["token_hash"]), "device": device, "browser": browser, "system": system, "via": r["via"] or "password",
            "created_at": r["created_at"], "last_seen_at": r["last_seen_at"] or r["created_at"], "expires_at": r["expires_at"],
            "current": r["token_hash"] == cur}


def _mine(c):
    return c.execute("SELECT * FROM sessions WHERE user_id=? AND expires_at>? ORDER BY created_at DESC", (me(), iso(now_utc()))).fetchall()


@app.get("/api/me/sessions")
def me_sessions():
    """The own sessions: [{sid, device, browser, system, via, created_at, last_seen_at, expires_at, current}], newest first,
    the current one first."""
    c, cur = db(), ses_current_hash()
    out = [ses_public(r, cur) for r in _mine(c)]
    out.sort(key=lambda s: not s["current"])
    return jsonify(sessions=out, current=bool(cur))


@app.delete("/api/me/sessions/<sid>")
def me_session_end(sid):
    """Ends one own session; the current one is the ordinary logout (the cookie goes too)."""
    c, cur = db(), ses_current_hash()
    hit = next((r["token_hash"] for r in _mine(c) if ses_sid(r["token_hash"]) == sid), None)
    if not hit:
        return err(tr("Not found"), 404)
    ses_end(c, me(), [hit])
    c.commit()
    resp = jsonify(ok=True, current=hit == cur)
    if hit == cur:
        resp.delete_cookie(COOKIE, path="/")
        resp.headers["Clear-Site-Data"] = '"cache"'  # 2.666.0 (#4074 7): the own session ended here = a logout (login.py auth_logout)
    return resp


@app.post("/api/me/sessions/others")
def me_sessions_others():
    """Ends every own session except this one -> {ended: n}."""
    c = db()
    n = ses_end(c, me(), None, keep=ses_current_hash())
    c.commit()
    return jsonify(ok=True, ended=n)
