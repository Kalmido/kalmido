#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1385.0 (#6503) API tests, own container: ways in that outlive what they were made for. Invented people only (example.com).
 - point 1: a change of an agent's owner (a team agent becomes Bob's, Bob's agent becomes a team agent again) ends its API
   tokens (the old token answers 401), its setup codes and its hosted MCP accesses (the access token answers 401, the refresh
   token no longer works); the new owner (or the admin) makes a new token that works; the same owner again changes nothing
 - point 2: an owner made a kid account pauses its personal agents (403 owner_locked, no write to the agent: enabled stays)
   and nobody can hand a kid an agent (400); an ordinary account again lets the same token work at once
 - point 3: /drop counts wrong upload tokens per address: after DROP_FAIL_LIMIT the address gets 429 (also with the right
   token, like the calendar feed), another address is untouched; a request without a token is not counted
usage: p21385_c_access_test.py <datadir>"""
import base64
import hashlib
import html
import os
import re
import secrets
import sys
import urllib.parse

import requests

from kt import B, PASSWORD, check, dbx, done, fresh, sess, setup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (32 bytes, base64), as p2488_mcp_oauth_test.py
CB = "http://127.0.0.1:9/cb"
DROP_FAIL_LIMIT = 30  # kalmido/core/pages.py

fresh(env={"KALMIDO_SECRET_KEY": KEY}, prefix="P21385C")
A = setup()


def j(r):
    try:
        return r.json()
    except ValueError:
        return {}


def api(tok, path="/api/v1/me"):
    return requests.get(B + path, headers={"Authorization": "Bearer " + tok}, timeout=60)


def grant(s, agent):
    """The whole OAuth way (consent page, code, token) of person s for agent -> the token answer (access + refresh)."""
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
    return j(r)


def setup_code(aid):
    """A setup code row of agent aid (its value does not matter here: only that it is gone after a change of owner)."""
    dbx("INSERT INTO agent_setup_codes(agent_id,code_hash,os,folder,created_by,created_at,expires_at) "
        "VALUES(?,?,'linux','',1,now(),now() + interval '1 hour')", (aid, secrets.token_hex(32)))


def codes(aid):
    return dbx("SELECT COUNT(*) FROM agent_setup_codes WHERE agent_id=?", (aid,))[0][0]


r = A.patch(B + "/api/admin/settings", json={"mcp_remote": True, "password": PASSWORD})
check(r.ok and r.json().get("mcp_remote") is True, f"the hosted MCP server is on ({r.status_code} {r.text[:120]})")
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "personal agents allowed")
CID = requests.post(B + "/oauth/register", json={"redirect_uris": [CB], "client_name": "Owner Test"}).json()["client_id"]

r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": PASSWORD, "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
Bo = sess("bob")

# ================================================================== point 1: a team agent becomes Bob's
team = A.post(B + "/api/admin/agents", json={"username": "teambot", "display_name": "Team Bot"})
check(team.status_code == 201, f"a team agent {team.status_code} {team.text[:120]}")
TEAM, TTOK = team.json()["id"], team.json()["token"]
G = grant(A, TEAM)
check(G.get("access_token") and api(G["access_token"]).status_code == 200, f"the admin's MCP access of the team agent works {str(G)[:120]}")
setup_code(TEAM)
check(api(TTOK).status_code == 200 and codes(TEAM) == 1, "before: the team agent's token works, a setup code waits")

check(A.patch(B + f"/api/admin/agents/{TEAM}", json={"display_name": "Team Bot 2"}).ok, "another change (name) ...")
check(api(TTOK).status_code == 200 and codes(TEAM) == 1, "... ends nothing")
check(A.patch(B + f"/api/admin/agents/{TEAM}", json={"owner_id": None}).ok and api(TTOK).status_code == 200,
      "'Belongs to: team' again for a team agent changes nothing")

r = A.patch(B + f"/api/admin/agents/{TEAM}", json={"owner_id": BOB})
check(r.ok and (j(r).get("owner") or {}).get("id") == BOB, f"the team agent becomes Bob's {r.status_code} {r.text[:160]}")
check(api(TTOK).status_code == 401, f"#6503 1: the old token on the former side's computer stops ({api(TTOK).status_code})")
check(codes(TEAM) == 0, "#6503 1: the setup codes are gone")
check(api(G["access_token"]).status_code == 401, "#6503 1: the MCP access token stops")
r = requests.post(B + "/oauth/token", data={"grant_type": "refresh_token", "refresh_token": G.get("refresh_token", ""), "client_id": CID})
check(r.status_code >= 400 and not j(r).get("access_token"), f"#6503 1: the MCP refresh token no longer works ({r.status_code})")
check(dbx("SELECT COUNT(*) FROM oauth_grants WHERE agent_id=? AND revoked_at IS NULL", (TEAM,))[0][0] == 0, "#6503 1: the access is revoked")
check(not dbx("SELECT 1 FROM api_tokens WHERE user_id=?", (TEAM,)), "#6503 1: no token of the agent is left")
r = Bo.post(B + f"/api/my/agents/{TEAM}/token", json={})
NT = j(r).get("token", "")
check(r.ok and NT and api(NT).status_code == 200, f"the new owner makes a new token that works {r.status_code}")

# ---- Bob's agent becomes a team agent again
setup_code(TEAM)
G2 = grant(Bo, TEAM)
check(G2.get("access_token") and api(G2["access_token"]).status_code == 200, "Bob's own MCP access of his agent works")
r = A.patch(B + f"/api/admin/agents/{TEAM}", json={"owner_id": None})
check(r.ok and j(r).get("owner") is None, f"Bob's agent becomes a team agent {r.status_code} {r.text[:160]}")
check(api(NT).status_code == 401 and api(G2["access_token"]).status_code == 401 and codes(TEAM) == 0,
      "#6503 1: 'becomes a team agent' ends Bob's token, his MCP access and the setup code too")

# ================================================================== point 2: Bob becomes a kid account
ag = Bo.post(B + "/api/my/agents", json={"username": "bob-bot", "display_name": "Bob Bot"})
check(ag.status_code == 201, f"Bob's personal agent {ag.status_code} {ag.text[:120]}")
BA, BTOK = ag.json()["id"], ag.json()["token"]
check(api(BTOK).status_code == 200, "before: Bob's agent works")
r = A.patch(B + f"/api/users/{BOB}", json={"kid": True})
check(r.ok, f"the admin makes Bob a kid account {r.status_code} {r.text[:160]}")
r = api(BTOK)
check(r.status_code == 403 and (j(r).get("error") or {}).get("code") == "owner_locked",
      f"#6503 2: Bob's agent pauses with him ({r.status_code} {r.text[:160]})")
check(dbx("SELECT enabled FROM agents WHERE user_id=?", (BA,))[0][0] in (True, 1), "#6503 2: nothing is written to the agent")
check(A.patch(B + f"/api/admin/agents/{TEAM}", json={"owner_id": BOB}).status_code == 400, "#6503 2: nobody hands a kid an agent")
check(A.patch(B + f"/api/users/{BOB}", json={"kid": False}).ok, "Bob is an ordinary account again")
check(api(BTOK).status_code == 200, "#6503 2: the same token works again at once")

# ================================================================== point 3: /drop counts wrong tokens per address
DT = A.post(B + "/api/me/drop-token").json()["drop_token"]


def drop(tok, ip, text="x"):
    h = {"X-Forwarded-For": ip}
    if tok is not None:
        h["Authorization"] = "Bearer " + tok
    return requests.post(B + "/drop", headers=h, data={"text": text}, timeout=60).status_code


check(drop(DT, "198.51.100.77", "first upload") == 200, "the right token uploads")
check(all(drop(None, "198.51.100.77") == 403 for _ in range(DROP_FAIL_LIMIT + 2)), "no token: 403, not counted")
check(drop(DT, "198.51.100.77") == 200, "#6503 3: ... the address still works")
codes_ = [drop("wrong-" + secrets.token_hex(8), "198.51.100.77") for _ in range(DROP_FAIL_LIMIT)]
check(codes_ == [403] * DROP_FAIL_LIMIT, f"#6503 3: {DROP_FAIL_LIMIT} wrong tokens: 403 {sorted(set(codes_))}")
check(drop("wrong-again", "198.51.100.77") == 429, "#6503 3: then the address gets 429")
check(drop(DT, "198.51.100.77") == 429, "#6503 3: ... also with the right token (like the calendar feed)")
check(drop(DT, "198.51.100.78") == 200, "#6503 3: another address is untouched")

sys.exit(done("p21385_c_access"))
