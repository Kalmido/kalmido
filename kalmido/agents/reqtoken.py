"""2.1386.0 (#6668): a team agent with its own token (an own starter, an own program) works per request for ONE person.

The run of a team agent on the Kalmido server already works with the rights of the person who asked (agents/srvteam.py
srv_run_cut: api_tokens.asked_by / run_lists, core/access.py act_for / token_lists, api/runfor.py run_gate, agents/control.py
ctl_cap). A team agent that runs elsewhere gets the same cut per request:
 - POST /api/v1/agent/request-token {"seqs": [event numbers]} (its own long-lived token only): a short-lived token of the agent
   (REQ_TTL_S) for the person these events come from (events at most REQ_EVENT_MAX_AGE_S old) -- the same cut, the same code (srv_run_cut): only that person's projects,
   outside projects at most their own role, writes capped to their role (a reader's order becomes an approval card).
   Events without a person (the project's own automation): only the events' projects, and every change is a card (req_unasked,
   agents/control.py ctl_gate). Events of two people in one call: 400 (one request = one person).
   {"operator": true}: the token for the person chosen in the agent's settings (perm_user_of: who answers its permission
   questions) -- the starter's own list work (mcp/agent_dispatch.py), which that person configured.
   A personal agent gets {"token": null}: it works for its owner, its own token is already theirs.
 - from the first request token on (agents.per_request, for good) its long-lived token is the agent's channel only (api/runfor.py
   req_main_gate, review F1: the class own plus REQ_MAIN_CHANNEL by name): events, status, chats, jobs, usage, cards,
   messages; the content of projects, files, contacts, pages, search, news, time, office ...
   only with a request token. 2.1432 (#6808): a program that never asks keeps its whole reach only until
   KALMIDO_REQ_MAIN_FROM (api/runfor.py req_main_on; Settings > Agents names the day), then its token is the channel too;
   GET /agent/chats (what people wrote) needs the request token as well. The reference starter (mcp/agent_run.py) asks
   before every run and hands only the request token to the model.
The hosted MCP access (agents/mcpremote.py) of a team agent is cut to the person who connected it (mcpr_cut)."""
import json
from datetime import timedelta

from flask import g, jsonify

from ..core import objhooks  # #6978 F6: the lock / revoke hooks (accounts calls them without importing the agents)
from ..core.config import app
from ..core.db import db, iso, now_utc
from ..core.i18n import tr
from ..core.errors import reject_unknown
from ..core.pg import st_ids, system_ctx
from ..api.common import v1_err, v1_json, v1_view
from ..api.runfor import REQ_SQL, req_is  # #6978 F7: a request token by its columns (asked_by + req_slot), not its name
from ..accounts.orgroles import SAY_NO  # #6978 F6
from ..accounts.session import _token_hash
from .core import agent_row, need_agent, perm_user_of

REQ_TOKEN_NAME = "Agent request"   # api_tokens.name of a request token -- a label only, never how one is recognised (REQ_SQL)
REQ_TTL_S = 8 * 3600               # a request lasts at most this long (a run, the jobs it starts); then a new one
REQ_SEQS_MAX = 100
REQ_EVENT_MAX_AGE_S = 24 * 3600    # review F4: an event older than this gives no request token any more (404 event_gone)


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def req_slot(operator, main_id):
    """Review F4 (2.1386.0): the place of a request token -- its kind (a run / the starter's list work, {operator: true}) and
    the long-lived token (the computer) that asked. One valid token per agent, person and place: a chat run of the person
    chosen for the list work never ends the dispatcher's token, two computers of one agent never end each other's."""
    return ("op:" if operator else "run:") + str(int(main_id or 0))


def req_issue(c, aid, who, work, slot="", ips=""):
    """A request token of team agent aid for person who (None: the events' own automation) -> (token, expires_at, lids).
    slot: req_slot. ips: the address rule of the asking token (review R3 F2: a computer's own, narrower rule of #6457 holds
    for its request tokens too; empty = the agent's rule, as agent_token_new copies it). The caller runs it in system_ctx
    and commits."""
    from .admin import agent_token_new  # a later module (it imports this one)
    from .srvteam import srv_run_cut  # a later module
    now = now_utc()
    c.execute(f"DELETE FROM api_tokens WHERE user_id=? AND {REQ_SQL} AND expires_at<?", (aid, iso(now)))
    # F2 (2.1386.0): at most ONE valid request token per agent and person (0 = the automation without a person): a new one
    # replaces the older one, so a person's leftover tokens never pile up unlisted for hours; review F4: per place (req_slot)
    c.execute(f"DELETE FROM api_tokens WHERE user_id=? AND {REQ_SQL} AND asked_by=? AND req_slot=?", (aid, who or 0, slot))
    tok = agent_token_new(c, aid, name=REQ_TOKEN_NAME)
    exp = iso(now + timedelta(seconds=REQ_TTL_S))
    c.execute("UPDATE api_tokens SET expires_at=?, req_slot=? WHERE token_hash=?", (exp, slot, _token_hash(tok)))
    if (ips or "").strip():
        c.execute("UPDATE api_tokens SET allowed_ips=? WHERE token_hash=?", (ips.strip(), _token_hash(tok)))
    return tok, exp, srv_run_cut(c, aid, _token_hash(tok), who, work)


def req_person_ok(c, who):
    """F4 (2.1386.0): may a request token work for account who? Only an active person's account (no agent, not disabled) --
    an event of an agent, a locked or deleted account gives no token (403 no_order), also on the operator path."""
    r = c.execute("SELECT 1 FROM users WHERE id=? AND kind<>'agent' AND NOT disabled", (_int(who),)).fetchone()
    return r is not None


def req_drop(c, aid):
    """Review F2: a long-lived token of agent aid went (a computer removed, the setup's uninstall, the agent revoking it):
    every request token of aid goes with it -- a request token is never shown in a list nor revoked on its own, so it must
    not outlive the token that may have fetched it (the starters still connected simply ask again). The caller commits."""
    c.execute(f"DELETE FROM api_tokens WHERE user_id=? AND {REQ_SQL}", (aid,))


def req_drop_person(c, uid, org=None):
    """#6978 F6: person uid gives orders no more -- locked (USER_LOCKED), left or removed from an organisation, a guest /
    read-only role there, the account deleted (REVOKE): their request tokens end at once (asked_by = uid), not after up to
    REQ_TTL_S; org: only those of the agents of that organisation. uid None (an organisation retires): every request token of
    its agents. The starter of a person who still may asks anew. The caller commits."""
    with system_ctx(c):  # every agent's tokens of that person (other workspaces too)
        if uid is None:
            if org:
                c.execute(f"DELETE FROM api_tokens WHERE {REQ_SQL} AND user_id IN (SELECT user_id FROM agents WHERE org_id=?)", (org,))
        elif org:
            c.execute(f"DELETE FROM api_tokens WHERE {REQ_SQL} AND asked_by=? AND user_id IN (SELECT user_id FROM agents WHERE org_id=?)",
                      (uid, org))
        else:
            c.execute(f"DELETE FROM api_tokens WHERE {REQ_SQL} AND asked_by=?", (uid,))


def _req_revoked(c, uid, org, reason, heir=None, role=None):
    """core/objhooks.person_revoked (accounts/orgs.py, orginvite.py, users.py, orgretain.py): a role change ends the person's
    request tokens of that organisation's agents only when the new role gives no orders (accounts/orgroles.py SAY_NO, as
    agents/core.py agent_org_say); leaving, a deleted account, a retired organisation always."""
    if reason == "role" and role not in SAY_NO:
        return {}
    req_drop_person(c, uid, org)
    return {}


objhooks.REVOKE.append(_req_revoked)
objhooks.USER_LOCKED.append(req_drop_person)


def req_drop_op(c, aid):
    """2.1386.0 (#6668, review R3 F9): the person chosen for team agent aid's questions changed (agents/admin.py runtime_set):
    the list work's request tokens (place op:, req_slot) of the person chosen before end at once -- the starter's dispatcher
    must not work up to 8 hours on as the old person; the starter asks anew for the new one. The caller commits."""
    with system_ctx(c):
        c.execute(f"DELETE FROM api_tokens WHERE user_id=? AND {REQ_SQL} AND substr(req_slot, 1, 3)='op:'", (aid,))  # a prefix without LIKE (pg_dialect)


def _main(row):
    """Is token row the agent's own long-lived token (no request, no run of the server, no MCP access of a person)?"""
    return (row is not None and ("asked_by" not in row.keys() or row["asked_by"] is None)
            and str(row["name"] or "") != "Server agent run")  # = agents/srvagent_run.py SRV_TOKEN_NAME (a later module)


@app.post("/api/v1/agent/request-token")
@v1_view
def v1_agent_request_token():
    """2.1386.0 (#6668): the token of one request of a team agent (see the module text)."""
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
            rows = c.execute("SELECT id, payload FROM agent_events WHERE agent_id=? AND id = ANY(CAST(? AS BIGINT[])) AND created_at>=?",
                             (aid, st_ids(set(seqs)), iso(now_utc() - timedelta(seconds=REQ_EVENT_MAX_AGE_S)))).fetchall()
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
            # review R3 F3: EVERY order event must be one the person may give (as agents/srvteam.py srv_batch checks each);
            # an event that is no order (srv_may_order is true for it) never carries a refused order along
            if who and not all(srv_may_order(c, a, who, e) for e in work):
                return v1_err(403, tr("This person gives the agent no orders (any more)"), name="no_order")
        if who and not req_person_ok(c, who):  # F4 (2.1386.0): only an active person's account gives orders
            return v1_err(403, tr("This person gives the agent no orders (any more)"), name="no_order")
        mt = g.token
        tok, exp, lids = req_issue(c, aid, who, work, req_slot(b.get("operator") is True, mt["id"]),
                                   ips=(mt["allowed_ips"] if "allowed_ips" in mt.keys() else "") or "")
        if not a["per_request"]:  # from the first request token on: its own token is its channel only (review F5: never
            c.execute("UPDATE agents SET per_request=true WHERE user_id=?", (aid,))  # by a refused or malformed ask)
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
                and req_is(t))



def mcpr_cut(c, aid, token_hash, uid):
    """agents/mcpremote.py _issue: the access token of a TEAM agent works for the person who connected it (uid) -- the same cut
    as a request (srv_run_cut); a personal agent's token stays as it is. The caller runs it in system_ctx."""
    from .srvteam import srv_run_cut  # a later module
    return srv_run_cut(c, aid, token_hash, uid, [])
