#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6605 (audit #4818 F1, decision 16.11.2026): a personal agent has in an organisation at most the current role of its person,
asked in every request (accounts/orgroles.py org_roles_cap), and a role change to guest / accounting takes the person's agents
out of the organisation as leaving it does (accounts/orgs.py org_agents_out). Invented names only.
freelancer-matrix: agents
 - bob (member) has a personal agent in the organisation with 'edit' in an organisation project and an edit share on his
   knowledge page: its token writes (POST / PATCH /api/v1/tasks, PATCH /api/v1/wiki/pages)
 - alice (admin) makes bob read-only: the agent stays in the organisation, its token reads and writes nothing there (403)
 - bob a member again: the agent writes again in the next request (no stale role)
 - bob a guest: the agent leaves the organisation (org_members, the project, agents.org_id), its token no longer reaches the
   project; alice's own agent and the organisation's other members are untouched
 - a person without an organisation: her own agent still writes in her private project
usage: p6605_agent_role_cap_test.py <datadir>"""
import sys

import requests

from freelancer_fixture import freelancer, login
from kt import B, check, circle_yes, dbx, done, fresh, setup

V = B + "/api/v1"
SCOPES = ["read", "write", "wiki:read", "wiki:write"]
FEAT = "collab,comments,agents,wiki,files"
fresh(prefix="P6605")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Nordwind", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com", "orgs": [ORG]})
assert r.ok, r.text
BOB = r.json()["id"]
Bo = login(B, "bob")
assert Bo.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT}).ok
assert A.patch(B + f"/api/orgs/{ORG}", json={"member_agents": True}).ok


def bearer(tok):
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + tok})
    return s


def role(uid):
    r = dbx("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, uid))
    return r[0][0] if r else None


def set_role(r):
    x = A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": BOB, "role": r})
    assert x.ok, x.text
    assert role(BOB) == r


r = Bo.post(B + "/api/my/agents", json={"username": "bobbot", "org_id": ORG, "scopes": SCOPES})
assert r.status_code == 201 and r.json().get("org_id") == ORG, r.text
BA, T = r.json()["id"], bearer(r.json()["token"])
r = A.post(B + "/api/my/agents", json={"username": "alicebot", "org_id": ORG, "scopes": SCOPES})
assert r.status_code == 201, r.text
AA, TA = r.json()["id"], bearer(r.json()["token"])
OL = Bo.post(B + "/api/lists", json={"name": "Nordwind board", "org_id": ORG}).json()["id"]
assert Bo.put(B + f"/api/lists/{OL}/members", json={"user_id": BA, "role": "edit"}).ok
AL = A.post(B + "/api/lists", json={"name": "Nordwind office", "org_id": ORG}).json()["id"]
r = A.put(B + f"/api/lists/{AL}/members", json={"user_id": AA, "role": "edit"})  # alice's own project and agent
assert r.ok, r.text
OT = Bo.post(B + "/api/tasks", json={"title": "Shoot plan", "list_id": OL}).json()["id"]
r = Bo.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Bob notes", "body": "text"})
assert r.status_code == 201, r.text
PG = r.json()["id"]
NODE = dbx("SELECT id FROM fs_nodes WHERE kind='ref' AND ref_kind='wiki' AND ref_id=?", (PG,))[0][0]
r = Bo.post(B + f"/api/files/nodes/{NODE}/shares", json={"agent_id": BA, "role": "edit"})
assert r.status_code == 201, r.text


def data(r):
    j = r.json()
    return j.get("data", j) if isinstance(j, dict) else j


def task_add(t, title, lid=None):
    return t.post(V + "/tasks", json={"list_id": lid or OL, "title": title}).status_code


def task_patch(t, title):
    g = t.get(V + f"/tasks/{OT}")
    if not g.ok:
        return g.status_code
    return t.patch(V + f"/tasks/{OT}", json={"title": title, "expect_updated_at": data(g)["updated_at"]}).status_code


def page_patch(t, text):
    """#7142: bob's agent has no control level and counts as "free" for the circle rule; it reads the project and the page,
    the organisation's knowledge space is read by more people: the write comes as a card, bob (who reads all its places)
    says Yes, the step runs from the card and answers by the role cap as the direct request did."""
    g = t.get(V + f"/wiki/pages/{PG}")
    if not g.ok:
        return g.status_code
    r = t.patch(V + f"/wiki/pages/{PG}", json={"body": text, "expect_updated_at": data(g)["updated_at"]})
    return circle_yes(r, dict(t.headers), BA, Bo, V, BOB, base=B).status_code


# ================================================================== member: the agent writes
check(task_add(T, "By the agent") in (200, 201), "member: bob's agent adds a task in the organisation project")
check(task_patch(T, "Shoot plan, agent") == 200, "member: ... and changes one")
check(page_patch(T, "agent text") == 200, "member: ... and changes his knowledge page through its edit share")

# ================================================================== read-only: the agent reads only
set_role("readonly")
check(role(BA) is not None, "read-only: the agent stays in the organisation")
check(T.get(V + f"/tasks/{OT}").ok and T.get(V + f"/wiki/pages/{PG}").ok, "read-only: the agent still reads the task and the page")
check(task_add(T, "Not allowed") == 403, f"read-only: POST /api/v1/tasks 403 ({task_add(T, 'Not allowed')})")
check(task_patch(T, "Not allowed") == 403, "read-only: PATCH /api/v1/tasks 403")
check(page_patch(T, "not allowed") == 403, "read-only: PATCH /api/v1/wiki/pages 403")
check(dbx("SELECT COUNT(*) FROM tasks WHERE title='Not allowed'") == [(0,)], "read-only: nothing written")
check(task_add(TA, "Alice agent", AL) in (200, 201), "read-only of bob: alice's agent writes as before")

# ================================================================== a member again: the cap follows in the next request
set_role("member")
check(task_add(T, "Back again") in (200, 201) and page_patch(T, "back again") == 200, "member again: the agent writes again (asked per request)")

# ================================================================== guest: the agents leave the organisation
set_role("guest")
check(role(BA) is None, "guest: bob's agent left the organisation's members")
check(dbx("SELECT COUNT(*) FROM list_members WHERE list_id=? AND user_id=?", (OL, BA)) == [(0,)], "guest: ... and its project")
check(dbx("SELECT org_id FROM agents WHERE user_id=?", (BA,)) == [(None,)], "guest: the agent is private now")
check(task_add(T, "Guest agent") in (403, 404) and T.get(V + f"/tasks/{OT}").status_code in (403, 404),
      "guest: its token no longer reaches the project")
check(role(AA) == "member" and task_add(TA, "Alice agent 2", AL) in (200, 201), "guest of bob: alice's agent stays and writes")
check(role(BOB) == "guest", "bob himself stays, as a guest")

# ================================================================== a person without an organisation
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"features": FEAT})
r = Fr.post(B + "/api/my/agents", json={"username": "fridabot", "scopes": SCOPES})
check(r.status_code == 201, f"freelancer: her own agent {r.status_code} {r.text[:160]}")
FT = bearer(r.json()["token"])
FL = Fr.post(B + "/api/lists", json={"name": "Frida clients"}).json()["id"]
assert Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": r.json()["id"], "role": "edit"}).ok
check(FT.post(V + "/tasks", json={"list_id": FL, "title": "Frida agent"}).status_code in (200, 201), "freelancer: her agent writes in her private project")

sys.exit(done("p6605_agent_role_cap"))
