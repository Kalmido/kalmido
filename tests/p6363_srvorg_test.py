#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1409.0 (#6363, decision 16.11.2026 variant B): the Kalmido AI (server agent) works in an organisation only after its admin
switched it on (orgs.srv_agents, PATCH /api/orgs/<id> {server_agents}, default off), against tests/fake_anthropic.py.
freelancer-matrix: agents (a person without an organisation sets up her server agent and it runs, no switch involved)
tenant-matrix: agent (a member of the organisation cannot switch it; while it is off nothing of the organisation reaches the provider)
 - a new organisation has it off: GET /api/orgs says server_agents false, a team server agent cannot be created (403
   org_server_agents_off); a member cannot switch it, a bad value 400; the admin switches it on (a security alert)
 - on: the team agent is created, gets its key and a mention runs (the provider gets the task)
 - off again: server settings, the model list and the starter pack answer 403 (deleting the key still works), GET says
   enabled_org false; a mention and a chat end the run before any provider call ("switched off" for the person who asked,
   nothing of the task at the provider)
 - on again: the next mention runs
 - a member's personal server agent placed by itself ("auto") lands in the private area while the organisation has it off
 - the defaults of the dialog name the organisations with it off (orgs_off)
 - a person without an organisation: her server agent runs as before
usage: p6363_srvorg_test.py <datadir>      (KMT_NOSTART=1 / P6363_NOSTART=1: a running server)"""
import json
import os
import shutil
import subprocess

from kt import B, CT, DATA, check, dbx, done, docker_logs_on_first_fail, fresh, sess, until
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
SKEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (the provider key is sealed with it)
KEY_ORG = "sk-test-orgkey-0123456789-oooo"
KEY_FR = "sk-test-frida-0123456789-ffff"
KEY_CA = "sk-test-carl-0123456789-cccc"
OFF_TEXT = "The Kalmido AI is switched off in this organisation"
fresh(env={"KALMIDO_SECRET_KEY": SKEY, "KALMIDO_SRVAGENT_ANTHROPIC_URL": "http://127.0.0.1:8091", "KALMIDO_SRVAGENT_RUN_S": "60",
           "KALMIDO_SRVAGENT_STEPS": "6", "KALMIDO_ADMIN_ALERTS": "1"}, prefix="P6363")  # alerts on: the switch is one
docker_logs_on_first_fail()
shutil.copy(os.path.join(N, "fake_anthropic.py"), DATA)
try:
    os.remove(os.path.join(DATA, "anthropic.log"))
except OSError:
    pass
subprocess.run(["docker", "exec", "-d", CT, "python", "/data/fake_anthropic.py"], check=True)
until(lambda: subprocess.run(["docker", "exec", CT, "python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8091), 1)"],
                             capture_output=True).returncode == 0, 20)


def plog():
    try:
        with open(os.path.join(DATA, "anthropic.log"), encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except OSError:
        return []


assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["comments", "collab"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en"})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "personal agents allowed")
uid = {}
for u, rk in (("bob", "admin"), ("carl", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": rk}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    check(r.ok, f"setup: {u} as {rk} " + r.text[:200])
    uid[u] = r.json().get("id")
Bo, Ca = sess("bob"), sess("carl")
for s in (Bo, Ca):
    s.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": "comments,collab"})
FID, Fr = freelancer(B, A)


def org_of(s):
    return next((o for o in s.get(B + "/api/orgs").json()["orgs"] if o["id"] == ORG), {})


def runs(aid):
    return dbx("SELECT id, state, error FROM agent_runs WHERE agent_id=? ORDER BY id", (aid,))


def settled(aid, n):
    def f():
        rr = runs(aid)
        return rr if len(rr) >= n and all(x[1] != "run" for x in rr) else None
    return until(f, 40)


def comments_by(tid, aid):
    return dbx("SELECT id FROM obj_comments WHERE kind='task' AND ref_id=? AND user_id=? AND body LIKE 'FAKE comment%'", (tid, aid))


# ---------------------------------------------------------------- a new organisation has it off
check(org_of(Bo).get("server_agents") is False, f"a new organisation: the Kalmido AI is off ({org_of(Bo).get('server_agents')})")
r = Bo.post(B + f"/api/orgs/{ORG}/server-agents", json={"username": "teamki", "display_name": "Team KI"})
check(r.status_code == 403 and r.json().get("error") == "org_server_agents_off" and OFF_TEXT in r.json().get("message", ""),
      f"off: its admin cannot create a team server agent ({r.status_code} {r.text[:160]})")
check(dbx("SELECT COUNT(*) FROM agents WHERE org_id=? AND provider='kalmido-server'", (ORG,))[0][0] == 0, "no agent was made")
d = Ca.get(B + "/api/agents/server/defaults").json()
check(ORG in (d.get("orgs_off") or []), f"the dialog's defaults name the organisation as off ({d.get('orgs_off')})")
r = Ca.patch(B + f"/api/orgs/{ORG}", json={"server_agents": True})
check(r.status_code in (403, 404) and org_of(Bo).get("server_agents") is False, f"a member cannot switch it on ({r.status_code})")
r = Bo.patch(B + f"/api/orgs/{ORG}", json={"server_agents": "yes"})
check(r.status_code == 400 and org_of(Bo).get("server_agents") is False, f"a bad value 400 ({r.status_code})")

# a member's personal server agent placed by itself lands in the private area while the organisation has it off
check(Bo.patch(B + f"/api/orgs/{ORG}", json={"member_agents": True}).ok, "setup: members may keep their own agents")
r = Ca.post(B + "/api/my/agents", json={"username": "carl-kki", "display_name": "Carl KI", "provider": "kalmido-server"})
check(r.status_code == 201, f"carl creates a personal agent {r.status_code} {r.text[:160]}")
CK = r.json().get("id")
check(dbx("SELECT org_id FROM agents WHERE user_id=?", (CK,)) == [(None,)], "off: it was placed in carl's private area, not in the organisation")
r = Ca.put(B + f"/api/agents/{CK}/server", json={"api_key": KEY_CA})
check(r.ok and r.json().get("enabled_org") is True, f"a private server agent of an organisation member: its key is stored ({r.status_code} {r.text[:160]})")
r = Ca.post(B + "/api/my/agents", json={"username": "carl-kki2", "display_name": "Carl KI 2", "provider": "kalmido-server", "org_id": ORG})
check(r.status_code == 201, f"carl places a second one in the organisation on purpose {r.status_code} {r.text[:160]}")
CK2 = r.json().get("id")
r = Ca.put(B + f"/api/agents/{CK2}/server", json={"api_key": KEY_CA})
check(r.status_code == 403 and r.json().get("error") == "org_server_agents_off", f"off: no key for an agent of the organisation ({r.status_code})")
check(Ca.get(B + f"/api/agents/{CK2}/server").json().get("enabled_org") is False, "its settings say enabled_org false")

# ---------------------------------------------------------------- the admin switches it on
r = Bo.patch(B + f"/api/orgs/{ORG}", json={"server_agents": True})
check(r.ok and r.json().get("server_agents") is True, f"bob (its admin) switches the Kalmido AI on ({r.status_code} {r.text[:160]})")
check(until(lambda: dbx("SELECT message FROM admin_alerts WHERE key LIKE 'orgswitch:org_server_agents:1:%'"), 20),
      "switching it is a security alert to the server's admins")
m = dbx("SELECT message FROM admin_alerts WHERE key LIKE 'orgswitch:org_server_agents:1:%'")
check(m and "Example Studio" in m[0][0] and "bob" in m[0][0], f"the alert names who and the organisation ({m})")
r = Bo.post(B + f"/api/orgs/{ORG}/server-agents", json={"username": "teamki", "display_name": "Team KI"})
check(r.status_code == 201, f"on: bob creates the team agent {r.status_code} {r.text[:160]}")
TK = r.json().get("id")
r = Bo.put(B + f"/api/agents/{TK}/server", json={"api_key": KEY_ORG})
check(r.ok and r.json().get("has_key") is True and r.json().get("enabled_org") is True, f"on: the key is stored ({r.status_code} {r.text[:160]})")
P = Bo.post(B + "/api/lists", json={"name": "Team project", "org_id": ORG}).json()["id"]
check(Bo.put(B + f"/api/lists/{P}/members", json={"user_id": TK, "role": "edit"}).ok, "setup: the team agent joins the project")
T1 = Bo.post(B + "/api/tasks", json={"title": "Team pelican task", "list_id": P}).json()["id"]
T2 = Bo.post(B + "/api/tasks", json={"title": "Secret osprey task", "list_id": P}).json()["id"]
check(Bo.post(B + f"/api/tasks/{T1}/comments", json={"body": f"<@{TK}> FAKE_COMMENT {T1}"}).ok, "bob mentions it")
check(until(lambda: comments_by(T1, TK), 40), "on: the run commented")
rr = settled(TK, 1)
check(rr and rr[-1][1] == "done", f"on: the run is done {rr}")
check(any("Team pelican task" in json.dumps(x) for x in plog()), "on: the task reached the provider")

# ---------------------------------------------------------------- off again
check(Bo.patch(B + f"/api/orgs/{ORG}", json={"server_agents": False}).ok, "bob switches it off again")
check(until(lambda: dbx("SELECT 1 FROM admin_alerts WHERE key LIKE 'orgswitch:org_server_agents:0:%'"), 20), "switching it off is an alert too")
r = Bo.put(B + f"/api/agents/{TK}/server", json={"instructions": "Be brief."})
check(r.status_code == 403 and r.json().get("error") == "org_server_agents_off", f"off: no change of its settings ({r.status_code})")
r = Bo.get(B + f"/api/agents/{TK}/server/models")
check(r.status_code == 403 and r.json().get("error") == "org_server_agents_off", f"off: no model list from the provider ({r.status_code})")
r = Bo.post(B + f"/api/agents/{TK}/server/starter", json={"items": ["briefing"]})
check(r.status_code == 403, f"off: no starter pack ({r.status_code})")
check(Bo.get(B + f"/api/agents/{TK}/server").json().get("enabled_org") is False, "off: its settings say enabled_org false")
n_calls = len(plog())
check(Bo.post(B + f"/api/tasks/{T2}/comments", json={"body": f"<@{TK}> FAKE_COMMENT {T2}"}).ok, "bob mentions it while off")
rr = settled(TK, 2)
check(rr and rr[-1][1] == "failed" and OFF_TEXT in (rr[-1][2] or ""), f"off: the run ends with the reason {rr}")
check(len(plog()) == n_calls and not any("Secret osprey task" in json.dumps(x) for x in plog()),
      "off: no call to the provider, nothing of the task reached it")
check(not comments_by(T2, TK), "off: no comment of the agent")
r = Bo.post(B + f"/api/agents/{TK}/chat", json={"body": "Hello OSPREY-CHAT"})
check(r.status_code == 201, f"bob writes to it in the chat ({r.status_code})")
rr = settled(TK, 3)
check(rr and rr[-1][1] == "failed" and OFF_TEXT in (rr[-1][2] or ""), f"off: the chat's run ends with the reason {rr}")
check(len(plog()) == n_calls and not any("OSPREY-CHAT" in json.dumps(x) for x in plog()), "off: the chat never reached the provider")
msgs = Bo.get(B + f"/api/agents/{TK}/chat").json()
check(OFF_TEXT in json.dumps(msgs), "off: bob reads in the chat why nothing happened")

# ---------------------------------------------------------------- on again: it works
check(Bo.patch(B + f"/api/orgs/{ORG}", json={"server_agents": True}).ok, "bob switches it on again")
T3 = Bo.post(B + "/api/tasks", json={"title": "Team heron task", "list_id": P}).json()["id"]
check(Bo.post(B + f"/api/tasks/{T3}/comments", json={"body": f"<@{TK}> FAKE_COMMENT {T3}"}).ok, "bob mentions it")
check(until(lambda: comments_by(T3, TK), 40), "on again: the run commented")
rr = settled(TK, 4)
check(rr and rr[-1][1] == "done", f"on again: the run is done {rr}")
# deleting the key works while it is off
check(Bo.patch(B + f"/api/orgs/{ORG}", json={"server_agents": False}).ok, "off once more")
r = Bo.put(B + f"/api/agents/{TK}/server", json={"delete_key": True})
check(r.ok and r.json().get("has_key") is False, f"off: deleting the key still works ({r.status_code} {r.text[:160]})")

# ---------------------------------------------------------------- a person without an organisation (P4)
ag = Fr.post(B + "/api/my/agents", json={"username": "frida-kki", "display_name": "Kalmido-KI", "provider": "kalmido-server"})
check(ag.status_code == 201, f"frida's agent {ag.status_code} {ag.text[:160]}")
FK = ag.json()["id"]
r = Fr.put(B + f"/api/agents/{FK}/server", json={"api_key": KEY_FR})
check(r.ok and r.json().get("enabled_org") is True, f"without an organisation: the key is stored ({r.status_code} {r.text[:160]})")
L1 = Fr.post(B + "/api/lists", json={"name": "Shared with the KI"}).json()["id"]
check(Fr.put(B + f"/api/lists/{L1}/members", json={"user_id": FK, "role": "edit"}).ok, "setup: her list shared with her agent")
FT = Fr.post(B + "/api/tasks", json={"title": "Freelance kestrel task", "list_id": L1}).json()["id"]
check(Fr.post(B + f"/api/tasks/{FT}/comments", json={"body": f"<@{FK}> FAKE_COMMENT {FT}"}).ok, "frida mentions it")
check(until(lambda: comments_by(FT, FK), 40), "without an organisation: the run commented")
rr = settled(FK, 1)
check(rr and rr[-1][1] == "done", f"without an organisation: the run is done {rr}")

raise SystemExit(done("p6363_srvorg"))
