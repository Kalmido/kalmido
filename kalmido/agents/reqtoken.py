"""2.1325.0 (#6668): a team agent with its own token (an own starter, an own program) works per request for ONE person.

The run of a team agent on the Kalmido server already works with the rights of the person who asked (agents/srvteam.py
srv_run_cut: api_tokens.asked_by / run_lists, core/access.py act_for / token_lists, api/runfor.py run_gate, agents/control.py
ctl_cap). A team agent that runs elsewhere gets the same cut per request:
 - POST /api/v1/agent/request-token {"seqs": [event numbers]} (its own long-lived token only): a short-lived token of the agent
   (REQ_TTL_S) for the person these events come from -- the same cut, the same code (srv_run_cut): only that person's projects,
   outside projects at most their own role, writes capped to their role (a reader's order becomes an approval card).
   Events without a person (the project's own automation): only the events' projects, and every change is a card (req_unasked,
   agents/control.py ctl_gate). Events of two people in one call: 400 (one request = one person).
   {"operator": true}: the token for the person chosen in the agent's settings (perm_user_of: who answers its permission
   questions) -- the starter's own list work (mcp/agent_dispatch.py), which that person configured.
   A personal agent gets {"token": null}: it works for its owner, its own token is already theirs.
 - from the first ask on (agents.per_request, for good) its long-lived token is the agent's channel only (api/runfor.py
   req_main_gate): events, status, chats, jobs, usage, cards, messages; the content of projects, files, contacts, pages ...
   only with a request token. A program that never asks for request tokens keeps working as before -- the
   reference starter (mcp/agent_run.py) asks before every run and hands only the request token to the model.
The hosted MCP access (agents/mcpremote.py) of a team agent is cut to the person who connected it (mcpr_cut)."""
import json
from datetime import timedelta

from flask import g, jsonify

from ..core.config import app
from ..core.db import db, iso, now_utc
from ..core.i18n import tr
from ..core.errors import reject_unknown
from ..core.pg import st_ids, system_ctx
from ..api.common import v1_err, v1_json, v1_view
from ..accounts.session import _token_hash
from .core import agent_row, need_agent, perm_user_of

REQ_TOKEN_NAME = "Agent request"   # api_tokens.name of a request token (never a token a person makes: agents only)
REQ_TTL_S = 8 * 3600               # a request lasts at most this long (a run, the jobs it starts); then a new one
REQ_SEQS_MAX = 100


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def req_issue(c, aid, who, work):
    """A request token of team agent aid for person who (None: the events' own automation) -> (token, expires_at, lids).
    The caller runs it in system_ctx and commits."""
    from .admin import agent_token_new  # a later module (it imports this one)
    from .srvteam import srv_run_cut  # a later module
    now = now_utc()
    c.execute("DELETE FROM api_tokens WHERE user_id=? AND name=? AND expires_at<?", (aid, REQ_TOKEN_NAME, iso(now)))
    tok = agent_token_new(c, aid, name=REQ_TOKEN_NAME)
    exp = iso(now + timedelta(seconds=REQ_TTL_S))
    c.execute("UPDATE api_tokens SET expires_at=? WHERE token_hash=?", (exp, _token_hash(tok)))
    return tok, exp, srv_run_cut(c, aid, _token_hash(tok), who, work)


def req_drop(c, aid):
    """Review F2: a long-lived token of agent aid went (a computer removed, the setup's uninstall, the agent revoking it):
    every request token of aid goes with it -- a request token is never shown in a list nor revoked on its own, so it must
    not outlive the token that may have fetched it (the starters still connected simply ask again). The caller commits."""
    c.execute("DELETE FROM api_tokens WHERE user_id=? AND name=?", (aid, REQ_TOKEN_NAME))


def _main(row):
    """Is token row the agent's own long-lived token (no request, no run of the server, no MCP access of a person)?"""
    return (row is not None and ("asked_by" not in row.keys() or row["asked_by"] is None)
            and str(row["name"] or "") != "Server agent run")  # = agents/srvagent_run.py SRV_TOKEN_NAME (a later module)


@app.post("/api/v1/agent/request-token")
@v1_view
def v1_agent_request_token():
    """2.1325.0 (#6668): the token of one request of a team agent (see the module text)."""
    from .srvteam import srv_may_order, srv_requester  # a later module
    aid = need_agent()
    b = v1_json()
    reject_unknown(b, ("seqs", "operator"))
    if not _main(g.get("token")):
        return v1_err(403, tr("Only the agent's own token can ask for a request token"), name="request_token_main")
    c = db()
    with system_ctx(c):  # the agent's own events and structure; the token it makes reaches only what the person reaches
        a = agent_row(c, aid)
        if a is None:
            return v1_err(404, tr("Not found"))
        if a["owner_id"]:
            return jsonify(token=None, expires_at=None, asked_by=a["owner_id"], list_ids=None)
        if not a["per_request"]:  # from the first ask on (also one refused below): its own token is its channel only
            c.execute("UPDATE agents SET per_request=true WHERE user_id=?", (aid,))
            c.commit()
        if b.get("operator") is True:
            if b.get("seqs"):
                return v1_err(400, tr("Invalid value: {0}", "seqs"))
            who, work = perm_user_of(c, a), []
            if not who:
                return v1_err(409, tr("Invalid value: {0}", "operator"), name="no_operator")
        else:
            seqs = b.get("seqs")
            if not isinstance(seqs, list) or not seqs or len(seqs) > REQ_SEQS_MAX or any(_int(x) is None for x in seqs):
                return v1_err(400, tr("Invalid value: {0}", "seqs"))
            rows = c.execute("SELECT id, payload FROM agent_events WHERE agent_id=? AND id = ANY(CAST(? AS BIGINT[]))",
                             (aid, st_ids(set(seqs)))).fetchall()
            if len(rows) != len(set(seqs)):
                return v1_err(404, tr("Not found"), name="event_gone")
            work = []
            for r in rows:
                try:
                    e = json.loads(r["payload"] or "{}")
                except ValueError:
                    e = {}
                work.append(e if isinstance(e, dict) else {})
            people = {p for p in (srv_requester(e) for e in work) if p}
            if len(people) > 1:
                return v1_err(400, tr("One request works for one person: these events come from several"), name="several_people")
            who = people.pop() if people else None
            if who and not any(srv_may_order(c, a, who, e) for e in work):
                return v1_err(403, tr("This person gives the agent no orders (any more)"), name="no_order")
        tok, exp, lids = req_issue(c, aid, who, work)
    c.commit()
    return jsonify(token=tok, expires_at=exp, asked_by=who, list_ids=sorted(lids or ()))


def req_main_token():
    """Review F3: is the current request one of an agent's own long-lived token (no request token, no run)?"""
    return g.get("auth_via") == "token" and _main(g.get("token"))


def req_unasked():
    """Is the current request one of a request token without a person (the automation of a team agent's projects)? Then every
    change is an approval card (agents/control.py ctl_gate)."""
    t = g.get("token") if g.get("auth_via") == "token" else None
    return bool(t is not None and "asked_by" in t.keys() and t["asked_by"] is not None and not int(t["asked_by"])
                and str(t["name"] or "") == REQ_TOKEN_NAME)


def mcpr_cut(c, aid, token_hash, uid):
    """agents/mcpremote.py _issue: the access token of a TEAM agent works for the person who connected it (uid) -- the same cut
    as a request (srv_run_cut); a personal agent's token stays as it is. The caller runs it in system_ctx."""
    from .srvteam import srv_run_cut  # a later module
    return srv_run_cut(c, aid, token_hash, uid, [])
