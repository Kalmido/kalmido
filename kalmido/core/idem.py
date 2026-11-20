"""2.270.0 C (#3022): idempotency keys of write requests (header Idempotency-Key).

The offline queue (static/js/core.js) and the service worker (static/sw.js) send the queue entry's key `k` with every
replay, agents may send their own key per call (API v1). The first request with a key claims it: a row in idem_keys in
the SAME transaction as the request's effect (effect and key are committed together; a request that fails and does not
commit leaves no row). A 2xx answer is stored with the row. A repeat of the key (same person, method and path) gets the
stored answer back (header Idempotent-Replayed: true) and changes nothing -- the service worker that was stopped before it
could drop the entry, the tab that sends it again, an agent's retry after a lost answer.

Never swallows an effect: only a stored 2xx answer is replayed. A row without an answer (the first request still running:
waited for a moment; or it committed and then failed) lets the repeat run as before and the new 2xx answer is stored.
2.533.0 A2 (#4318 A14): not on the app's own routes (the offline queue, the service worker): there a committed claim is the
committed effect, so a request that committed and then failed (5xx, e.g. a push after the commit) keeps its key as done,
and a repeat that finds a committed claim without an answer gets {"ok": true} instead of applying the change a second time
(a log entry, a new row). API v1 (agents, who may retry a call whose later steps failed) stays as before.
(#6558): the answer's text is kept only for the routes of IDEM_FULL (tasks, habits, time, notes and chat: what the
app's offline queue sends again and reads back); any other route, and a kept answer over IDEM_MAX_BODY, keeps only its short
answer (idem_short: the original's shape with ok, the id fields and updated_at, nothing else) -- an agent's office draft, a
contact, a document no longer lie readable in idem_keys and every backup. A route that hands out a secret sets
g.idem_no_body and keeps no text at all (a repeat gets {"ok": true}); an answer with a token / secret / code / password field
(idem_secretish) keeps only its short answer, also on IDEM_FULL (tests/p21437_c_idem_secret_test.py guards both).
Without the header nothing changes. Keys older than IDEM_DAYS (14, 2.380 H #3387) go with the watchdog's hourly idem_prune
(2.1315.0 #6409, was: when the same person claimed a new key); until then an expired key counts as gone (never replayed).
"""
import json
import re
import time
from datetime import timedelta

from flask import Response, g, request

from .config import app
from .db import connect, db, iso, now_utc

IDEM_HEADER = "Idempotency-Key"
IDEM_DAYS = 14  # 2.380 H (#3387): as long as the offline queue lives (a change sent after days is no false conflict)
IDEM_MAX_KEYS = 5000  # 2.380 (#3387 review): kept keys per person; the oldest beyond go (14 days must not mean unbounded)
IDEM_MAX_BODY = 256 * 1024  # bytes of a stored answer; a larger one keeps its short answer (2.1437.0 #6558, was {"ok": true})
# (#6558): the routes whose whole answer is kept (app and API v1): what the offline queue / service worker send again
# and read back (the new task's fields, a note's text and updated_at, a chat message). Everything else: idem_short.
# #7494 review F1: of the times only what the queue / an agent sends again (start, stop, entries, timer) - a timesheet decision's answer holds its
# sealed note (time_sheets.note) in plain text and never lies in idem_keys
IDEM_FULL = re.compile(r"^/api/(?:v1/)?(?:tasks|habits|time/(?:start|stop|entries|timer)|notes|notepads|lists/\d+/notes|team/messages|agent/chats|agents/\d+/chat)(?:/|$)")
_IDEM_ID = re.compile(r"^(?:id|ids|.+_id|.+_ids)$")
_IDEM_KEEP = ("ok", "updated_at")
# (#6558): field names of a secret shown once; such a field with a text value: only the short answer is kept
_IDEM_SECRET = re.compile(r"(?:^|_)(?:token|tokens|secret|secrets|code|codes|password|passphrase|key|keys|otpauth)$")
IDEM_WAIT = 10.0  # 2.575.0 (#3948): was 3 s; a 503 retry of the MCP client during a long write must not write twice; s: a repeat that arrives while the first request is still running waits this long for its answer
IDEM_PRUNE = {"at": 0.0}  # 2.1315.0 (#6409): the last run of idem_prune (time.time())
IDEM_PRUNE_S = 3600
_IDEM_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
# (#7494): the key the app's rawFetch puts on every write of its own (no outbox entry, no dialog) starts with IDEM_NET: it only
# guards "Try again" after a write without an answer (minutes). Such a key keeps only the short answer, also on IDEM_FULL (a
# sealed text such as a timesheet's decision note never lies in idem_keys as plain text), and idem_prune drops it after
# IDEM_NET_S, so the many ordinary writes do not push the offline queue's keys out of IDEM_MAX_KEYS.
IDEM_NET = "n."
IDEM_NET_S = 3600
_IDEM_METHODS = ("POST", "PATCH", "PUT", "DELETE")


def _idem_key():
    if request.method not in _IDEM_METHODS or not request.path.startswith("/api/"):
        return None
    k = (request.headers.get(IDEM_HEADER) or "").strip()
    u = getattr(g, "user", None)
    return k if k and _IDEM_KEY.match(k) and u is not None else None


def dvb_idem_app():
    """2.533.0 A2 (#4318 A14): an app route (not API v1): a committed claim counts as the effect done (see the module text)."""
    if request.path.startswith("/api/v1/"):
        return False
    # review 2.533.0 (#4318 A14): a create with client_ref runs again instead -- its duplicate check hands back the existing
    # row with its id (an answer without id would lose the offline queue's mapping of the temporary id)
    if request.method == "POST" and isinstance(b := request.get_json(silent=True), dict) and b.get("client_ref"):
        return False
    return True


def _idem_replay(r):
    body = r["body"]
    resp = Response(body if body is not None else json.dumps({"ok": True}), int(r["status"]), mimetype="application/json")
    if int(r["status"]) == 204:
        resp = Response(status=204)
    resp.headers["Idempotent-Replayed"] = "true"
    return resp


def idem_secretish(v):
    """(#6558): True when the answer holds, at any depth, a field named like a secret (token, secret, code, key, password
    ...) with a text value (or a list of texts): such an answer keeps only its short answer, whatever the route."""
    if isinstance(v, dict):
        return any((_IDEM_SECRET.search(str(k).lower()) and (isinstance(x, str) and x or isinstance(x, list) and any(isinstance(y, str) for y in x)))
                   or idem_secretish(x) for k, x in v.items())
    if isinstance(v, list):
        return any(idem_secretish(x) for x in v)
    return False


def idem_short(v):
    """(#6558): the short answer in the shape of the original: ok, every id field (id, ids, *_id, *_ids) and updated_at,
    at any depth (a dict / list keeps what holds such fields, the rest goes). -> the reduced value (None: nothing to keep)."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in _IDEM_KEEP or _IDEM_ID.match(str(k)):
                if x is None or isinstance(x, (bool, int, float, str)) or (isinstance(x, list) and all(isinstance(y, (int, str)) for y in x)):
                    out[k] = x
                    continue
            if isinstance(x, (dict, list)) and (r := idem_short(x)) not in (None, {}, []):
                out[k] = r
        return out
    if isinstance(v, list):
        r = [idem_short(x) for x in v if isinstance(x, (dict, list))]
        return [x for x in r if x not in (None, {}, [])]
    return None


def idem_body(path, data, no_body=False, key=""):
    """(#6558): the text kept with a key for a 2xx JSON answer (bytes) of `path`: the whole answer on IDEM_FULL up to
    IDEM_MAX_BODY and without a secret-named field, else the short answer; None (a repeat gets {"ok": true}) for a route
    marked idem_no_body (it hands out a secret) or an answer that is no JSON."""
    if no_body:
        return None
    try:
        j = json.loads(data)
    except ValueError:
        return None
    if IDEM_FULL.match(path) and not key.startswith(IDEM_NET) and len(data) <= IDEM_MAX_BODY and not idem_secretish(j):
        return data.decode("utf-8", "replace")
    r = idem_short(j)
    if isinstance(j, dict):
        r = {"ok": True, **(r or {})}
    return json.dumps(r if r is not None else {"ok": True}, separators=(",", ":"))


def _idem_insert(c, uid, k, ts):
    """Claims the key (True) or finds it there (False). A second request with the same key waits here until the first one
    commits or rolls back (the row's lock)."""
    return bool(c.execute("INSERT INTO idem_keys(user_id, k, method, path, created_at) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING k",
                          (uid, k, request.method, request.path, iso(ts))).fetchone())


def idem_prune(c, force=False):
    """2.1315.0 (#6409): the watchdog (notify/push.py, at most hourly): keys older than IDEM_DAYS go in one DELETE (index
    ix6409_idem_keys_created), then the oldest keys of a person over IDEM_MAX_KEYS. Was done by every write request with a
    key. Between two runs a person may hold a few keys more than IDEM_MAX_KEYS; an expired key is never replayed meanwhile
    (idem_claim). -> the number of keys removed."""
    if not force and time.time() - IDEM_PRUNE["at"] < IDEM_PRUNE_S:  # also in the test containers: a suite runs it with force
        return 0
    IDEM_PRUNE["at"] = time.time()
    n = c.execute("DELETE FROM idem_keys WHERE created_at<?", (iso(now_utc() - timedelta(days=IDEM_DAYS)),)).rowcount
    n += c.execute("DELETE FROM idem_keys WHERE created_at<? AND left(k, ?)=?", (iso(now_utc() - timedelta(seconds=IDEM_NET_S)), len(IDEM_NET), IDEM_NET)).rowcount  # (#7494)
    for (uid,) in c.execute("SELECT user_id FROM idem_keys GROUP BY user_id HAVING COUNT(*)>?", (IDEM_MAX_KEYS,)).fetchall():
        n += c.execute("DELETE FROM idem_keys WHERE user_id=? AND k IN (SELECT k FROM idem_keys WHERE user_id=? ORDER BY created_at DESC, k DESC OFFSET ?)",
                       (uid, uid, IDEM_MAX_KEYS)).rowcount
    c.commit()
    return n


@app.before_request
def idem_claim():
    k = _idem_key()
    if not k:
        return None
    c, uid, ts = db(), g.user["id"], now_utc()
    # 2.1315.0 (#6409): no tidying here any more (two DELETE per write, the second sorting up to IDEM_MAX_KEYS keys): the
    # watchdog's idem_prune does it hourly. Only the claim; a key past IDEM_DAYS that is still there is taken over below.
    if _idem_insert(c, uid, k, ts):
        g.idem_k = k
        return None
    lim = iso(ts - timedelta(days=IDEM_DAYS))
    # a key older than IDEM_DAYS counts as gone until the next run (as when it was deleted before the claim): never replayed
    if c.execute("DELETE FROM idem_keys WHERE user_id=? AND k=? AND created_at<?", (uid, k, lim)).rowcount and _idem_insert(c, uid, k, ts):
        g.idem_k = k
        return None
    end = time.monotonic() + IDEM_WAIT
    while True:
        r = c.execute("SELECT method, path, status, body FROM idem_keys WHERE user_id=? AND k=?", (uid, k)).fetchone()
        if r is None or (r["method"], r["path"]) != (request.method, request.path):
            return None  # gone meanwhile / the key of another call: runs as without a key
        if r["status"] is not None:
            return _idem_replay(r)
        if time.monotonic() > end:
            if dvb_idem_app():  # 2.533.0 A2 (#4318 A14): committed = done, never applied twice
                return _idem_replay({"status": 200, "body": None})
            g.idem_k = k  # committed without an answer (failed after its commit): runs again, its answer is stored
            return None
        time.sleep(0.1)


@app.after_request
def idem_store(resp):
    """Stores a 2xx answer with the key -- on a connection of its own, and only when the claim row is committed (the request's
    effect then is too). The request's own transaction is never committed here: a claim it did not commit is locked by it
    (skipped) and goes with its rollback."""
    k = g.pop("idem_k", None)
    if not k or getattr(g, "user", None) is None:
        return resp
    ok, body = 200 <= resp.status_code < 300, None
    # 2.391.0 (#3362 review B1): idem_no_body = an answer with a secret shown once is never stored (a repeat gets {"ok": true}:
    # the effect happened, the secret is not handed out twice); (#6558): the whole text only on IDEM_FULL (idem_body)
    no_body = g.pop("idem_no_body", False)
    if ok and not resp.direct_passthrough and not resp.is_streamed and "json" in (resp.content_type or ""):
        body = idem_body(request.path, resp.get_data(), no_body, k)
    c = None
    try:
        c = connect()
        if c.execute("SELECT 1 FROM idem_keys WHERE user_id=? AND k=? AND status IS NULL FOR UPDATE SKIP LOCKED", (g.user["id"], k)).fetchone():
            if ok:
                c.execute("UPDATE idem_keys SET status=?, body=? WHERE user_id=? AND k=?", (resp.status_code, body, g.user["id"], k))
            elif resp.status_code >= 500 and dvb_idem_app():  # 2.533.0 A2 (#4318 A14): committed, then a server error: done
                c.execute("UPDATE idem_keys SET status=200, body=NULL WHERE user_id=? AND k=?", (g.user["id"], k))
            else:  # committed and then failed: the key is free again
                c.execute("DELETE FROM idem_keys WHERE user_id=? AND k=?", (g.user["id"], k))
        c.commit()
    except Exception as e:  # noqa: BLE001  (the answer goes out anyway; a repeat then runs as without a key)
        print(f"idempotency key not stored: {e!r}", flush=True)
    finally:
        if c is not None:
            c.close()
    return resp
