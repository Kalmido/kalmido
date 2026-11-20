#!/usr/bin/env python3
# kalmido-suite: fresh
"""#7218 (reader F1 of job/5616): a PRIVATE server agent with a left-over membership in a project of an organisation reads
nothing of that project while the organisation has the Kalmido AI off (orgs.srv_agents 0, #6363). Invented names only.
freelancer-matrix: agents (a person without an organisation: her own private server agent keeps reading her own project)
tenant-matrix: agent (the organisation's project stays closed to a private server agent of a member while the switch is off)
 - setup: alice's organisation (switch off by default), its project with a task; carl (member) has a private server agent;
   a left-over list_members row puts the agent into the organisation's project (new joins are refused, accounts/orgs.py)
 - the agent's token: the task by id (404/403), the task list of the project and the list overview leave it out
 - frida (no organisation): her private server agent reads her own project and its task as before
usage: p7218_srvorg_legacy_test.py <datadir>      (KMT_NOSTART=1 / P7218_NOSTART=1: a running server)"""
import sys

from kt import B, H, check, dbx, done, fresh, sess
from freelancer_fixture import freelancer

SKEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="
fresh(env={"KALMIDO_SECRET_KEY": SKEY}, prefix="P7218")
V = B + "/api/v1"

assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["comments", "collab"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "setup: personal agents allowed")
check(A.patch(B + f"/api/orgs/{ORG}", json={"member_agents": True}).ok, "setup: members may keep their own agents")
r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": "member"}], "username": "carl", "display_name": "Carl",
                                   "password": "password123", "email": "carl@example.com"})
check(r.ok, "setup: carl as member " + r.text[:200])
Ca = sess("carl")
Ca.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": "comments,collab"})
FID, Fr = freelancer(B, A)
check(dbx("SELECT srv_agents FROM orgs WHERE id=?", (ORG,)) == [(0,)], "setup: the organisation has the Kalmido AI off")


def server_agent(S, name):
    r = S.post(B + "/api/my/agents", json={"username": name, "display_name": name.title(), "provider": "kalmido-server",
                                           "scopes": ["read"]})
    check(r.status_code == 201, f"{name}: a private server agent {r.status_code} {r.text[:160]}")
    j = r.json()
    return j.get("id"), {"Authorization": "Bearer " + (j.get("token") or ""), **H}


# ---------------------------------------------------------------- the organisation's project, carl's private server agent in it
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
P = A.post(B + "/api/lists", json={"name": "Werbefilm Sommer", "kind": "project"}).json().get("id")
check(dbx("SELECT org_id FROM lists WHERE id=?", (P,)) == [(ORG,)], "setup: the project belongs to the organisation")
T = A.post(B + "/api/tasks", json={"title": "Drehorte anfragen", "list_id": P}).json().get("id")
CK, CH = server_agent(Ca, "carl-kki")
check(dbx("SELECT org_id FROM agents WHERE user_id=?", (CK,)) == [(None,)], "setup: carl's server agent is private")
dbx("INSERT INTO list_members(list_id, user_id, role, added_at) VALUES(?, ?, 'edit', now())", (P, CK))  # the left-over membership

r = sess().get(V + f"/tasks/{T}", headers=CH)
check(r.status_code in (403, 404), f"off: the agent does not get the organisation's task by id ({r.status_code} {r.text[:120]})")
r = sess().get(V + "/tasks", params={"list_id": P}, headers=CH)
ids = [x.get("id") for x in (r.json().get("tasks") or r.json().get("items") or [])] if r.ok else []
check(T not in ids, f"off: the project's tasks are not listed for the agent ({r.status_code} {ids})")
r = sess().get(V + "/lists", headers=CH)
lids = [x.get("id") for x in (r.json().get("lists") or r.json().get("items") or [])] if r.ok else []
check(P not in lids, f"off: the project is not among the agent's lists ({r.status_code} {lids})")

# ---------------------------------------------------------------- a person without an organisation: as before
Fr.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": "comments,collab"})
FP = Fr.post(B + "/api/lists", json={"name": "Kurzfilm Herbst", "kind": "project"}).json().get("id")
FT = Fr.post(B + "/api/tasks", json={"title": "Schnitt planen", "list_id": FP}).json().get("id")
FK, FH = server_agent(Fr, "frida-kki")
dbx("INSERT INTO list_members(list_id, user_id, role, added_at) VALUES(?, ?, 'edit', now()) ON CONFLICT DO NOTHING", (FP, FK))
r = sess().get(V + f"/tasks/{FT}", headers=FH)
check(r.status_code == 200, f"freelancer: her private server agent reads her own project's task ({r.status_code} {r.text[:120]})")
sys.exit(done("p7218_srvorg_legacy"))
