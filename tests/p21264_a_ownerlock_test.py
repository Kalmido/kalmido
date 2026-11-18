#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1264.0 (#6351) API tests, own container: a locked account locks its personal agents too -- the one check of the owner in
agents/core.py (AGENT_ROW_SQL owner_locked, agent_active), which the API token (api/v1.py api_authenticate), the hosted MCP
server (/mcp and its tools) and the agent's events / webhook (agent_emit) all inherit. Invented people only (example.com).
 - a person WITHOUT an organisation, locked by the hosting operator (PUT /api/operator/accounts/{id} {disabled}): her
   agent's token answers 403 code owner_locked (the message names the reason, no person), /mcp answers 403 (no 401: the
   client must not refresh), a tool call of a still open access is refused, no new event is recorded, what waited for the
   agent's webhook is dropped; nothing is written to the agent (agents.enabled stays) -> unlocked: the SAME token and the
   SAME MCP access work again without any further step
 - a person locked by the instance admin (PATCH /api/users/{id} {disabled}): the same for their agent's token
 - agents without an owner (team agents) and other people's agents are never touched by a lock
 - the access an instance admin gave to a team agent stops on /mcp while that admin is locked; the team agent's own token
   keeps working (it has no owner). 2.1380.0 (#6485): its access token answers 403 owner_locked on /api/v1 at once, a refresh
   while locked answers 403 and keeps the access; unlocked, the same refresh token goes on
usage: p21264_a_ownerlock_test.py <datadir>"""
import base64
import hashlib
import html
import os
import re
import secrets
import shutil
import sys
import urllib.parse

import requests

import kt
from kt import B, PASSWORD, check, dbx, done, fresh, sess, setup, until

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freelancer_fixture import freelancer  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OPDIR = os.path.abspath(DATA.rstrip("/")) + "-op"
OPTOKEN = secrets.token_urlsafe(40)
KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64), as p2488_mcp_oauth_test.py
HOOK = "http://127.0.0.1:8097/agent"  # nobody listens there: a delivery fails and waits in the queue for its next try
CB = "http://127.0.0.1:9/cb"

if not kt.nostart("P21264A"):
    shutil.rmtree(OPDIR, ignore_errors=True)
    os.makedirs(OPDIR)
    with open(os.path.join(OPDIR, "token"), "w") as f:
        f.write(OPTOKEN + "\n")
    os.chmod(OPDIR, 0o755)
    os.chmod(os.path.join(OPDIR, "token"), 0o644)
    os.environ["EXTRA"] = (os.environ.get("EXTRA", "") + f" -v {OPDIR}:/run/kop:ro -e KALMIDO_OPERATOR_TOKEN_FILE=/run/kop/token").strip()
fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_WEBHOOK_ALLOW_HOSTS": "127.0.0.1:8097", "KALMIDO_WEBHOOK_TICK": "1"}, prefix="P21264A")
A = setup()


def op(method, path, **kw):
    return requests.request(method, B + "/api/operator/" + path, headers={"Authorization": "Bearer " + OPTOKEN}, timeout=60, **kw)


def api(tok, path="/api/v1/me"):
    return requests.get(B + path, headers={"Authorization": "Bearer " + tok}, timeout=60)


def j(r):
    try:
        return r.json()
    except ValueError:
        return {}


def locked_answer(r):
    e = j(r).get("error") or {}
    return r.status_code == 403 and e.get("code") == "owner_locked" and e.get("message") == "The account this agent belongs to is locked"


def mcp(tok, msg):
    return requests.post(B + "/mcp", json=msg, headers={"Authorization": "Bearer " + tok}, timeout=120)


def mcp_lists(tok, i):
    """-> (HTTP status, isError, text) of the tool list_lists."""
    r = mcp(tok, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "list_lists", "arguments": {}}})
    return r.status_code, (j(r).get("result") or {}).get("isError"), r.text


def grant(s, agent, full=False):
    """The whole OAuth way (consent page, code, token) of person s for agent -> the access token."""
    v = secrets.token_urlsafe(48)
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    q = {"response_type": "code", "client_id": CID, "redirect_uri": CB, "code_challenge": ch, "code_challenge_method": "S256", "state": "s1"}
    r = s.get(B + "/oauth/authorize?" + urllib.parse.urlencode(q), allow_redirects=False)
    m = re.search(r'name="t" value="([^"]+)"', r.text)
    r = s.post(B + "/oauth/authorize", data={"t": html.unescape(m.group(1)) if m else "", "decision": "allow", "agent": str(agent)},
               allow_redirects=False)
    code = (urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers.get("Location", "")).query).get("code") or [""])[0]
    r = requests.post(B + "/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CB, "client_id": CID,
                                                "code_verifier": v})
    return j(r) if full else j(r).get("access_token", "")  # 2.1380.0 (#6485): full = the whole answer (refresh token)


# ---------------------------------------------------------------- the people and their agents
r = A.patch(B + "/api/admin/settings", json={"mcp_remote": True, "password": PASSWORD})
check(r.ok and r.json().get("mcp_remote") is True, f"the hosted MCP server is on ({r.status_code} {r.text[:120]})")
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "personal agents allowed")
CID = requests.post(B + "/oauth/register", json={"redirect_uris": [CB], "client_name": "Lock Test"}).json()["client_id"]

FID, Fr = freelancer(B, A)  # a person without an organisation
# her personal agent with a webhook: an admin creates it for her (owner_id; only that route takes a webhook address)
ag = A.post(B + "/api/admin/agents", json={"username": "frida-bot", "display_name": "Frida Bot", "owner_id": FID, "webhook_url": HOOK})
check(ag.status_code == 201 and ag.json().get("token"), f"the freelancer's personal agent with a webhook {ag.status_code} {ag.text[:160]}")
FA, FTOK = ag.json()["id"], ag.json()["token"]
check(dbx("SELECT owner_id FROM agents WHERE user_id=?", (FA,))[0][0] == FID, "it is her personal agent")
L1 = Fr.post(B + "/api/lists", json={"name": "Shared with the bot"}).json()["id"]
check(Fr.put(B + f"/api/lists/{L1}/members", json={"user_id": FA, "role": "edit"}).ok, "her project shared with her agent")
WID = dbx("SELECT webhook_id FROM agents WHERE user_id=?", (FA,))[0][0]

r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": PASSWORD, "email": "bob@example.com"})
assert r.ok, r.text
BID = r.json()["id"]
Bo = sess("bob")
ag = Bo.post(B + "/api/my/agents", json={"username": "bob-bot", "display_name": "Bob Bot"})
check(ag.status_code == 201, f"bob's personal agent {ag.status_code} {ag.text[:120]}")
BA, BTOK = ag.json()["id"], ag.json()["token"]

team = A.post(B + "/api/admin/agents", json={"username": "teambot", "display_name": "Team Bot"})
check(team.status_code == 201, f"a team agent {team.status_code} {team.text[:120]}")
TEAM, TTOK = team.json()["id"], team.json()["token"]
check(dbx("SELECT owner_id FROM agents WHERE user_id=?", (TEAM,))[0][0] is None, "the team agent has no owner")

r = A.post(B + "/api/users", json={"username": "carol", "display_name": "Carol", "password": PASSWORD, "email": "carol@example.com"})
assert r.ok, r.text
CAID = r.json()["id"]
check(A.patch(B + f"/api/users/{CAID}", json={"is_admin": True}).ok, "carol is a second instance admin")
Ca = sess("carol")

for name, tok in (("the freelancer's agent", FTOK), ("bob's agent", BTOK), ("the team agent", TTOK)):
    check(api(tok).status_code == 200, f"before: {name} works")
AT = grant(Fr, FA)
check(AT and mcp(AT, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200, "before: her MCP access answers")
st, bad, txt = mcp_lists(AT, 2)
check(st == 200 and not bad and "Shared with the bot" in txt, f"before: the MCP tool reads her project ({st} {txt[:160]})")
TFULL = grant(Ca, TEAM, full=True)  # 2.1380.0 (#6485): the refresh token too
TAT, TRT = TFULL.get("access_token", ""), TFULL.get("refresh_token", "")
check(TAT and mcp(TAT, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200, "before: the access carol gave to the team agent answers")

# something waits for the agent's webhook (the delivery fails: nobody listens)
check(Fr.post(B + f"/api/agents/{FA}/chat", json={"body": "hello bot"}).ok, "a chat message to her agent")
check(until(lambda: dbx("SELECT COUNT(*) FROM webhook_queue WHERE webhook_id=?", (WID,))[0][0] >= 1, 20), "before: its event waits for the webhook")
EV0 = dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=?", (FA,))[0][0]
check(EV0 >= 1, "before: the event is recorded")

# ---------------------------------------------------------------- the operator locks the person without an organisation
r = op("PUT", f"accounts/{FID}", json={"disabled": True})
check(r.ok and Fr.get(B + "/api/state").status_code == 401, f"the operator locked the freelancer ({r.status_code} {r.text[:120]})")
r = api(FTOK)
check(locked_answer(r), f"locked: her agent's token 403 owner_locked ({r.status_code} {r.text[:200]})")
check("frida" not in r.text.lower(), "locked: the answer names no person")
check(locked_answer(api(FTOK, "/api/v1/agent/events")), "locked: no events for her agent")
check(locked_answer(api(FTOK, f"/api/v1/tasks?list_id={L1}")), "locked: no tasks for her agent")
r = requests.post(B + "/api/v1/tasks", json={"title": "Written while locked", "list_id": L1}, headers={"Authorization": "Bearer " + FTOK})
check(locked_answer(r) and not dbx("SELECT 1 FROM tasks WHERE title='Written while locked'"), "locked: her agent writes nothing")
r = mcp(AT, {"jsonrpc": "2.0", "id": 3, "method": "ping"})
check(r.status_code == 403 and "WWW-Authenticate" not in r.headers, f"locked: /mcp 403, no call for a refresh ({r.status_code} {r.text[:120]})")
r = mcp(AT, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
check(r.status_code == 403, f"locked: /mcp tools/list 403 ({r.status_code})")
st, bad, txt = mcp_lists(AT, 5)
check(st == 403 and "Shared with the bot" not in txt, f"locked: the MCP tool reads nothing ({st} {txt[:160]})")
check(until(lambda: dbx("SELECT COUNT(*) FROM webhook_queue WHERE webhook_id=?", (WID,))[0][0] == 0, 30),
      "locked: what waited for the agent's webhook is dropped")
r = A.post(B + f"/api/admin/agents/{FA}/test")
check(r.status_code == 409, f"locked: no test event for her agent ({r.status_code})")
check(dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=?", (FA,))[0][0] == EV0, "locked: no new event is recorded")
check(dbx("SELECT COUNT(*) FROM webhook_queue WHERE webhook_id=?", (WID,))[0][0] == 0, "locked: nothing new for its webhook")
row = dbx("SELECT a.enabled, u.disabled FROM agents a JOIN users u ON u.id=a.user_id WHERE a.user_id=?", (FA,))[0]
check(row[0] in (1, True) and row[1] in (0, False), f"locked: nothing is written to the agent itself ({list(row)})")
check(dbx("SELECT enabled FROM webhooks WHERE id=?", (WID,))[0][0] in (1, True), "locked: its webhook stays switched on")
for name, tok in (("bob's agent", BTOK), ("the team agent", TTOK)):
    check(api(tok).status_code == 200, f"the freelancer locked: {name} keeps working")

# ---------------------------------------------------------------- unlocked: everything works again, no further step
r = op("PUT", f"accounts/{FID}", json={"disabled": False})
check(r.ok, f"the operator unlocked the freelancer ({r.status_code})")
r = api(FTOK)
check(r.status_code == 200, f"unlocked: the same token works again ({r.status_code} {r.text[:160]})")
r = requests.post(B + "/api/v1/tasks", json={"title": "Written after the lock", "list_id": L1}, headers={"Authorization": "Bearer " + FTOK})
check(r.status_code in (200, 201) and dbx("SELECT 1 FROM tasks WHERE title='Written after the lock' AND created_by=?", (FA,)),
      f"unlocked: her agent writes again ({r.status_code} {r.text[:160]})")
check(mcp(AT, {"jsonrpc": "2.0", "id": 6, "method": "ping"}).status_code == 200, "unlocked: the same MCP access answers again")
st, bad, txt = mcp_lists(AT, 7)
check(st == 200 and not bad and "Shared with the bot" in txt, f"unlocked: the MCP tool reads her project again ({st} {txt[:160]})")
Fr = sess("frida")
check(Fr.post(B + f"/api/agents/{FA}/chat", json={"body": "back again"}).ok, "unlocked: she writes to her agent")
check(dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=?", (FA,))[0][0] > EV0, "unlocked: events are recorded again")
check(until(lambda: dbx("SELECT COUNT(*) FROM webhook_queue WHERE webhook_id=?", (WID,))[0][0] >= 1, 20), "unlocked: its webhook gets events again")

# ---------------------------------------------------------------- the instance admin locks a person
check(A.patch(B + f"/api/users/{BID}", json={"disabled": True}).ok, "the admin locked bob")
r = api(BTOK)
check(locked_answer(r), f"bob locked: his agent's token 403 owner_locked ({r.status_code} {r.text[:200]})")
check(api(FTOK).status_code == 200 and api(TTOK).status_code == 200, "bob locked: the other agents keep working")
check(A.patch(B + f"/api/users/{BID}", json={"disabled": False}).ok, "the admin unlocked bob")
check(api(BTOK).status_code == 200, "bob unlocked: his agent's token works again")
# the kill switch stays what it was: paused by its owner, not "locked"
check(sess("bob").patch(B + f"/api/my/agents/{BA}", json={"enabled": False}).ok, "bob pauses his agent")
r = api(BTOK)
check(r.status_code == 403 and (j(r).get("error") or {}).get("code") == "forbidden", f"a paused agent: the old answer ({r.status_code} {r.text[:160]})")

# ---------------------------------------------------------------- a team agent: no owner, never locked along
check(A.patch(B + f"/api/users/{CAID}", json={"disabled": True}).ok, "the admin locked carol (who gave an access to the team agent)")
check(api(TTOK).status_code == 200, "carol locked: the team agent's own token keeps working")
r = mcp(TAT, {"jsonrpc": "2.0", "id": 8, "method": "ping"})
check(r.status_code == 403, f"carol locked: the access she gave stops on /mcp ({r.status_code})")
# 2.1380.0 (#6485): the access token of that access stops on /api/v1 too (not only after its hour), and a refresh while she is
# locked answers 403 without ending the access
r = api(TAT)
check(r.status_code == 403 and (j(r).get("error") or {}).get("code") == "owner_locked" and "carol" not in r.text.lower(), f"carol locked: the access token 403 owner_locked on /api/v1 at once ({r.status_code} {r.text[:200]})")
r = requests.post(B + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": TRT, "client_id": CID})
check(r.status_code == 403 and "access_token" not in r.text, f"carol locked: the refresh answers 403, no new token ({r.status_code} {r.text[:160]})")
check(dbx("SELECT COUNT(*) FROM oauth_grants WHERE agent_id=? AND user_id=? AND revoked_at IS NULL", (TEAM, CAID))[0][0] == 1,
      "carol locked: the refresh did not end the access")
check(A.patch(B + f"/api/users/{CAID}", json={"disabled": False}).ok, "the admin unlocked carol")
check(mcp(TAT, {"jsonrpc": "2.0", "id": 9, "method": "ping"}).status_code == 200, "carol unlocked: her access answers again")
check(api(TAT).status_code == 200, "carol unlocked: the access token works on /api/v1 again")
r = requests.post(B + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": TRT, "client_id": CID})
check(r.status_code == 200 and j(r).get("access_token"), f"carol unlocked: the same refresh token works, no new connecting ({r.status_code} {r.text[:160]})")
check(mcp(j(r).get("access_token", ""), {"jsonrpc": "2.0", "id": 10, "method": "ping"}).status_code == 200, "carol unlocked: the new access token answers")

sys.exit(done("p21264_a_ownerlock"))
