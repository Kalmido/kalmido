"""2.1026.0 (#5280, stage Q6c of the cross-cutting core, analysis #3563, decided 08.11.2026 / 09.11.2026): the ONE registry of
the searches and the one route of each side -- GET /api/search (the web) and GET /api/v1/search (tokens, agents).

Every area search registers its kind here (srch_register, at import of the area's module): what one search finds in the
area's own search field, the command palette's "Everywhere" finds too (decision of 09.11.2026), because both run the same
function. The routes /api/search/messages, /api/files/search, /api/wiki/search and /api/v1/files/search went with the stage
(no second way): ?kind= picks the area, its answer is the answer of the old route.

- web(): the answer of ?kind=<kind> (the area's own shape, from request.args).
- group(c, uid, q, n): at most n hits of the kind for the palette (`groups` of the first page of GET /api/search); the same
  entries the kind's own answer lists.
- v1(): the answer of GET /api/v1/search?kind=<kind>; v1group(c, uid, q, n): the kind's part of ?kind=all.
- scope: the token scope a kind needs on /api/v1/search (contacts, files:read, wiki:read, calendar); a token without it gets
  403 for the kind and no part of ?kind=all.
- gate: the path whose module / workspace switches cover the kind (accounts/modcards.py mc_gate, accounts/wsareas.py
  wsa_gate) -- the old route's path, so a switched-off area answers 403 as before (and is left out of the groups).
- office: never for agents or the API (question 16): it registers no v1.

Where the texts are: open texts -> obj_search (core/objsearch.py), sealed texts -> obj_search_words (core/objwords.py),
end-to-end -> the browser (static/js/ftsearch.js SEARCH_SOURCES: the server's answer plus the sources of the locked areas).
The rights stay each area's own (the registered functions check them per hit); this module only routes.
"""
import time

from flask import g, jsonify, request

from .config import app
from .ctx import me
from .db import db
from .env import env_int
from .errors import BadInput, Denied
from .i18n import tr
from ..api.common import v1_view

SEARCH_KINDS = {}
# filled by the higher layers when they load (the pattern of core/objhooks.py, no upward import):
#   gates        accounts/modcards.py mc_gate, accounts/wsareas.py wsa_gate -- f(path) raises Denied for a switched-off area
#   scope_label  api/scopes.py -- f(scope) -> the scope's readable name
#   task_ids     core/objsearch.py osr_ids_sql -- for a reader below the domain layer (accounts/orgtasks.py)
SRCH_HOOKS = {"gates": [], "scope_label": lambda s: s, "task_ids": None}
SRCH_GROUP = 5          # hits per kind in the palette's groups (?glimit=, 1..20)
SRCH_GROUP_MAX = 20
# 2.1343.0 (#6406, audit #4765): the palette's groups run on a time budget per request. The kinds run in their fixed order
# (`order`); once SRCH_BUDGET_S has passed since the request began, the rest is not searched but named in `pending`, and the
# palette asks for them in a second request (?kind=groups&groups=<kinds>) -- at least one kind runs in every request, so the
# palette always gets further. Each kind's statements run under SRCH_STMT_MS (not the session's 30 s) inside a savepoint: a
# kind that runs over it is left out like a kind without hits (the request goes on). A browser that dropped the request
# (a newer query, the palette closed) stops the work before the next kind (waitress: channel_request_lookahead in app.py).
# KALMIDO_SEARCH_BUDGET_MS overrides the 400 ms (0 = one kind per request: the tests walk the pending chain with it).
SRCH_BUDGET_S = env_int("KALMIDO_SEARCH_BUDGET_MS", 400, 0, 10000) / 1000
SRCH_STMT_MS = 2500


def srch_register(kind, *, web=None, group=None, v1=None, v1group=None, scope=None, gate=None, order=None):
    """Register the search of kind (see the module's text); a second call of the same kind adds the parts it names (the web
    and the API side of an area may stand in two modules)."""
    s = SEARCH_KINDS.setdefault(kind, {"web": None, "group": None, "v1": None, "v1group": None, "scope": "read", "gate": None, "order": 50})
    for k, v in (("web", web), ("group", group), ("v1", v1), ("v1group", v1group), ("scope", scope), ("gate", gate), ("order", order)):
        if v is not None:
            s[k] = v


def _ordered(field):
    return [k for k, s in sorted(SEARCH_KINDS.items(), key=lambda x: (x[1]["order"], x[0])) if s.get(field)]


def srch_gate(kind):
    """Denied when the module / workspace switches of the kind's area refuse the person (the old route's before_request)."""
    p = SEARCH_KINDS[kind].get("gate")
    if not p:
        return
    for gate in SRCH_HOOKS["gates"]:
        r = gate(p)
        if r is not None:  # a gate that answers instead of raising
            raise Denied(403)


def srch_q(a, key="q"):
    q = (a.get(key) or "").strip()
    if not q or len(q) > 200:
        raise BadInput(tr("Invalid value: {0}", "q"))
    return q


def _glimit(a):
    try:
        n = int(a.get("glimit") or SRCH_GROUP)
    except ValueError:
        raise BadInput(tr("Invalid value: {0}", "glimit")) from None
    return max(1, min(SRCH_GROUP_MAX, n))


def _gone():
    """2.1343.0 (#6406): True when the browser closed the connection of this request (waitress sees it with
    channel_request_lookahead; without it -- tests, another server -- never)."""
    try:
        f = request.environ.get("waitress.client_disconnected")  # a callable of the server, not a value of the request
        return callable(f) and f() is True
    except RuntimeError:  # outside a request (a direct call)
        return False


def _stmt_ms(c):
    return c.execute("SELECT current_setting('statement_timeout')").fetchone()[0]


def srch_groups(c, uid, q, n, field="group", skip=("tasks",), scopes=None, kinds=None, t0=None, pending=None):
    """{kind: [hits]} of every registered kind with hits (not those in skip; kinds = only these); a kind the person may not
    reach (switched off, no right, a token without the scope) is left out quietly. t0 (time.monotonic() of the request's
    start) turns the budget on: the kinds not searched within SRCH_BUDGET_S are appended to pending (a list); see above."""
    out = {}
    todo = [k for k in _ordered(field) if k not in skip and (kinds is None or k in kinds)]
    timed = t0 is not None
    prev = _stmt_ms(c) if timed else None
    try:
        for i, kind in enumerate(todo):
            if timed and i and (time.monotonic() - t0 > SRCH_BUDGET_S or _gone()):
                if pending is not None:
                    pending.extend(todo[i:])
                break
            s = SEARCH_KINDS[kind]
            if scopes is not None and s["scope"] not in scopes:
                continue
            try:
                if field == "group":
                    srch_gate(kind)
                if timed:
                    with c.savepoint():
                        c.execute(f"SET LOCAL statement_timeout = {int(SRCH_STMT_MS)}")
                        hits = s[field](c, uid, q, n)
                else:
                    hits = s[field](c, uid, q, n)
            except (Denied, BadInput):
                continue
            except Exception as e:  # noqa: BLE001 - only a kind over its time (query_canceled) is left out; the rest is an error
                if not timed or getattr(e, "sqlstate", None) != "57014":
                    raise
                print(f"search: kind {kind} ran over {SRCH_STMT_MS} ms, left out of the groups", flush=True)
                continue
            if hits:
                out[kind] = list(hits)[:n]
    finally:
        if timed:
            c.execute("SELECT set_config('statement_timeout', ?, true)", (prev,))  # SET LOCAL outlives RELEASE SAVEPOINT
    return out


def _err(e):
    if isinstance(e, Denied):
        return jsonify(error=e.text()), e.code
    return jsonify(error=str(e)), 400


@app.get("/api/search")
def srch_web():
    """?q, kind (default tasks) -- the one search route of the web. kind=tasks: {hits, next} and on the first page (no cursor)
    groups: {kind: [hits]} of every other kind with hits (at most ?glimit, default 5). Any other kind: that area's answer.
    2.1343.0 (#6406): the groups run on the time budget (SRCH_BUDGET_S): kinds not searched in time are named in
    pending: [kinds]; kind=groups&groups=<kind,kind> searches only those (the palette's second request, {groups, pending}).
    ?groups= (empty) with kind=tasks: no groups at all (a caller that needs only the tasks)."""
    t0 = time.monotonic()
    a = request.args
    kind = a.get("kind") or "tasks"
    if kind == "groups":
        want = [k.strip() for k in (a.get("groups") or "").split(",") if k.strip()]
        if not want or len(want) > len(SEARCH_KINDS) or any(SEARCH_KINDS.get(k, {}).get("group") is None or k == "tasks" for k in want):
            return jsonify(error=tr("Invalid value: {0}", "groups")), 400
        pend = []
        try:
            groups = srch_groups(db(), me(), srch_q(a), _glimit(a), kinds=set(want), t0=t0, pending=pend)
        except BadInput as e:
            return _err(e)
        return jsonify(groups=groups, **({"pending": pend} if pend else {}))
    s = SEARCH_KINDS.get(kind)
    if s is None or s["web"] is None:
        return jsonify(error=tr("Invalid value: {0}", "kind")), 400
    pend = []
    try:
        srch_gate(kind)
        r = s["web"]()
        if kind != "tasks" or a.get("cursor") or not isinstance(r, dict):
            return r if not isinstance(r, dict) else jsonify(r)
        if "groups" in a and not a.get("groups"):
            return jsonify(r)
        groups = srch_groups(db(), me(), srch_q(a), _glimit(a), t0=t0, pending=pend)
    except (Denied, BadInput) as e:
        return _err(e)
    return jsonify({**r, **({"groups": groups} if groups else {}), **({"pending": pend} if pend else {})})


@app.get("/api/v1/search")
@v1_view
def v1_search():
    """GET /api/v1/search: ?kind = tasks (default) | messages | contacts | notes | files | wiki | events | all (scope=messages
    stays the older name of kind=messages). all: {groups: {kind: [at most ?limit (default 5) entries]}} of the kinds the
    token may read; never the office (question 16)."""
    a = request.args
    if a.get("scope") not in (None, "", "tasks", "messages"):  # review 2.1026 F3: an unknown scope stays a 400
        raise BadInput(tr("Invalid value: {0}", "scope"))
    kind = a.get("kind") or ("messages" if a.get("scope") == "messages" else "tasks")
    tok = g.get("auth_via") == "token"
    scopes = set(g.get("scopes") or ()) if tok else None
    if kind == "all":
        extra = sorted(k for k in a if k not in ("q", "kind", "limit"))
        if extra:
            raise BadInput(tr("Unknown parameter: {0}", ", ".join(extra)[:200]))
        try:
            n = max(1, min(SRCH_GROUP_MAX, int(a.get("limit") or SRCH_GROUP)))
        except ValueError:
            raise BadInput(tr("Invalid value: {0}", "limit")) from None
        return jsonify(groups=srch_groups(db(), me(), srch_q(a), n, field="v1group", skip=(), scopes=scopes))
    s = SEARCH_KINDS.get(kind)
    if s is None or s["v1"] is None:
        raise BadInput(tr("Invalid value: {0}", "kind"))
    if tok and s["scope"] not in scopes:
        e = Denied(403, tr("This token lacks the permission “{0}”", SRCH_HOOKS["scope_label"](s["scope"])))
        e.v1_extra = {"required_scope": s["scope"]}
        raise e
    g.srch_kind = kind  # api/common.py v1_args: the area's own handler accepts kind / scope beside its parameters
    try:
        return s["v1"]()
    finally:
        g.pop("srch_kind", None)  # review 2.1026 F2: never beyond this call (in-process calls may share g)

