#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1287.0 (#6454, audit #4790 F4): a team agent answers and writes with the rights of the person who asked, never with its
whole reach (kalmido/agents/srvteam.py srv_run_cut, core/access.py act_for / token_lists, agents/control.py ctl_cap /
ctl_claim, agents/core.py agent_emit / job_may_act), against tests/fake_anthropic.py.
freelancer-matrix: agents (the person without an organisation: her personal agent keeps its whole reach -- her project, a
  folder and an address book shared with it; its token carries no requester; her Yes on a card without a project still counts)
tenant-matrix: agent (the cut is the requester's own rights: a person of another organisation is no requester at all)
 (a) a channel: a member who shares no project with the team agent mentions it -- nothing reaches the agent; a member the
     agent is open to in a project reaches it
 (b) the run for a member of project 1 only: the model's get_task on a task of project 2 is 404; the run for the owner reads it.
     The run token (api_tokens.asked_by / run_lists): tasks of the other project 404; a folder, a knowledge page and an
     address book shared with the agent alone are gone for a requester who does not reach them (one object and the lists),
     there for one who does; a run without a person reaches nothing outside its projects
 (c) a reader of the project asks the agent to comment: no comment (409 approval_required); a writer's order comments
 (d) a card without a project (a contact into an address book): the Yes of a person who shares a project with the agent but
     cannot write into the book does not count (404, the card is free again), the Yes of a person who can does
 review A2 (2.1287.0): the run gate (api/runfor.py) -- another person's chat, job, briefing, office closed in a run;
     a participant's run and a person who left the project mid-run reach no task of it; an admin's run keeps the folders
 audit #4818: a read-only person of the organisation gives the team agent no orders (chat, mention); the owner of an
     approval job who is read-only now approves nothing
usage: p6454_team_agent_asker_test.py <datadir>      (KMT_NOSTART=1 / P6454_NOSTART=1: a running server)"""
import json
import os
import shutil
import subprocess

import requests

from kt import B, CT, DATA, check, dbx, done, docker_logs_on_first_fail, fresh, sess, until
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
V = B + "/api/v1"
HDR = "X-Kalmido-Approval"
SKEY = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA="  # a test server key (the provider key is sealed with it)
KEY_ORG = "sk-test-orgkey-0123456789-oooo"
SCOPES = ["read", "tasks:write", "comments", "wiki:read", "wiki:write", "contacts", "files:read", "files:write", "structure"]
fresh(env={"KALMIDO_SECRET_KEY": SKEY, "KALMIDO_SRVAGENT_ANTHROPIC_URL": "http://127.0.0.1:8091", "KALMIDO_SRVAGENT_RUN_S": "60",
           "KALMIDO_SRVAGENT_STEPS": "6"}, prefix="P6454")
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


def err(r):
    try:
        e = r.json()["error"]
        return e if isinstance(e, dict) else {}
    except (ValueError, KeyError, TypeError):
        return {}


assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True,
                                    "modules": ["comments", "collab", "wiki", "contacts", "files"]})
FEAT = "comments,collab,wiki,contacts,files"
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
check(A.put(B + "/api/admin/agent-policy", json={"user_agents": True}).ok, "personal agents allowed")
uid = {}
for u, rk in (("bob", "admin"), ("carl", "member"), ("rita", "member"), ("eve", "member"), ("ron", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": rk}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    check(r.ok, f"setup: {u} as {rk} " + r.text[:200])
    uid[u] = r.json().get("id")
S = {u: sess(u) for u in uid}
Bo, Ca, Ri, Ev, Ro = (S[u] for u in ("bob", "carl", "rita", "eve", "ron"))
for s in S.values():
    s.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
FID, Fr = freelancer(B, A)

# ---------------------------------------------------------------- the team agents and the two projects
r = Bo.post(B + f"/api/orgs/{ORG}/server-agents", json={"username": "teamki", "display_name": "Team KI"})
check(r.status_code == 201, f"setup: the team agent on the server {r.status_code} {r.text[:200]}")
TK = r.json().get("id")
check(Bo.put(B + f"/api/agents/{TK}/server", json={"api_key": KEY_ORG}).ok, "setup: its key")
r = A.post(B + "/api/admin/agents", json={"scopes": SCOPES, "username": "extbot", "display_name": "Ext Bot", "org_id": ORG})
check(r.status_code == 201, f"setup: a team agent with its own token {r.status_code} {r.text[:200]}")
XT, XTOK = r.json()["id"], r.json()["token"]
XH = {"Authorization": "Bearer " + XTOK}
check(dbx("SELECT owner_id FROM agents WHERE user_id IN (?,?)", (TK, XT)) == [(None,), (None,)], "both are team agents (no owner)")

P1 = Bo.post(B + "/api/lists", json={"name": "Project one", "org_id": ORG}).json()["id"]
P2 = Bo.post(B + "/api/lists", json={"name": "Project two", "org_id": ORG}).json()["id"]
# one agent per project: the same pair of projects once for the server agent (P1, P2) and once for the other one (X1, X2)
X1 = Bo.post(B + "/api/lists", json={"name": "Project one X", "org_id": ORG}).json()["id"]
X2 = Bo.post(B + "/api/lists", json={"name": "Project two X", "org_id": ORG}).json()["id"]
for one in (P1, X1):
    for u, role in (("carl", "edit"), ("rita", "view"), ("ron", "edit")):
        check(Bo.put(B + f"/api/lists/{one}/members", json={"user_id": uid[u], "role": role}).ok, f"setup: {u} in project one ({role})")
for lid, ag in ((P1, TK), (P2, TK), (X1, XT), (X2, XT)):
    r = Bo.put(B + f"/api/lists/{lid}/members", json={"user_id": ag, "role": "edit", "bridge_ok": True})
    check(r.ok, f"setup: agent {ag} in project {lid} {r.status_code} {r.text[:160]}")
    check(Bo.patch(B + f"/api/lists/{lid}", json={"agent_members": True}).ok, "setup: members may use the agent")
T1 = Bo.post(B + "/api/tasks", json={"title": "Open pelican task", "list_id": P1}).json()["id"]
S2 = Bo.post(B + "/api/tasks", json={"title": "Secret heron budget", "list_id": P2}).json()["id"]
TX = Bo.post(B + "/api/tasks", json={"title": "Open stork task", "list_id": X1}).json()["id"]
SX = Bo.post(B + "/api/tasks", json={"title": "Secret crane budget", "list_id": X2}).json()["id"]
check(Ca.get(B + f"/api/tasks/{S2}").status_code == 404 and Ca.get(B + f"/api/tasks/{SX}").status_code == 404, "setup: carl does not see the tasks of the projects two")


def runs(aid=TK):
    return dbx("SELECT id, state, cause, asked_by, error, steps FROM agent_runs WHERE agent_id=? ORDER BY id", (aid,))


def settled(n, aid=TK):
    def f():
        rr = runs(aid)
        return rr if len(rr) >= n and all(x[1] != "run" for x in rr) else None
    return until(f, 40)


def agent_comments(tid, aid=TK):
    return dbx("SELECT id FROM obj_comments WHERE kind='task' AND ref_id=? AND user_id=? AND body LIKE 'FAKE comment%'", (tid, aid))


# ================================================================ (b) the run works with the requester's rights
check(Ca.post(B + f"/api/tasks/{T1}/comments", json={"body": f"<@{TK}> CARL-ASKS FAKE_GET_TASK {S2}"}).ok, "(b) carl (project one only) asks for a task of project two")
rr = settled(1)
check(rr and rr[-1][1] == "done" and rr[-1][3] == uid["carl"], f"(b) the run works for carl {rr}")
mine = [x for x in plog() if "CARL-ASKS" in x.get("first", "")]
check(len(mine) >= 2, f"(b) the model was called with carl's order and the tool result ({len(mine)})")
check(not any("Secret heron" in json.dumps(x) for x in mine), "(b) the task of project two never reached the model in carl's run")
check(any("ERROR" in x.get("last", "") for x in mine), "(b) get_task answered an error (404) " + str([x.get("last", "")[:120] for x in mine]))
check(not dbx("SELECT 1 FROM api_tokens WHERE user_id=? AND name='Server agent run'", (TK,)), "(b) the run's token is gone after the run")
check(Bo.post(B + f"/api/tasks/{T1}/comments", json={"body": f"<@{TK}> BOB-ASKS FAKE_GET_TASK {S2}"}).ok, "(b) bob (both projects) asks the same")
rr = settled(2)
check(rr and rr[-1][1] == "done" and rr[-1][3] == uid["bob"], f"(b) the run works for bob {rr}")
check(any("Secret heron" in x.get("last", "") for x in plog() if "BOB-ASKS" in x.get("first", "")), "(b) bob's run reads the task of project two")

# ---- the run token itself: what srv_run_cut writes, set by hand on the other team agent's token (act_for / token_lists)
TOKID = dbx("SELECT id FROM api_tokens WHERE user_id=? ORDER BY id DESC LIMIT 1", (XT,))[0][0]


def run_for(who, lids):
    """The token of the team agent as the run token of a run for who (None: an ordinary token; 0: a run without a person)."""
    dbx("UPDATE api_tokens SET asked_by=?, run_lists=? WHERE id=?", (who, None if who is None else ",".join(str(x) for x in lids), TOKID))


def xget(path, **kw):
    return requests.get(V + path, headers=XH, timeout=30, **kw)


FD = Bo.post(B + "/api/files/folders", json={"space": f"org:{ORG}", "name": "Board only"}).json().get("id")
check(Bo.post(B + f"/api/files/nodes/{FD}/shares", json={"agent_id": XT, "role": "edit"}).status_code == 201, "setup: a folder shared with the agent alone")
check(Ca.get(B + f"/api/files/nodes/{FD}").status_code == 404, "setup: carl does not reach the folder")
BK = Bo.post(B + "/api/books", json={"name": "Board contacts", "org_id": ORG}).json().get("id")
r = Bo.put(B + f"/api/books/{BK}/members", json={"user_id": XT, "role": "edit"})
check(r.ok, f"setup: an address book shared with the agent alone {r.status_code} {r.text[:160]}")
CT1 = Bo.post(B + "/api/contacts", json={"book_id": BK, "fn": "Zora Quillfeather"}).json().get("id")
check(not any(b["id"] == BK for b in Ca.get(B + "/api/books").json().get("books", [])), "setup: carl does not have the address book")

# a knowledge page of the organisation in a folder shared with the agent: every member reads the organisation's pages, so the
# requester's own role lets it through -- the run's cut names projects, it does not close the pages (wkf_token_listed)
r = Bo.post(B + "/api/wiki/pages", json={"space": f"org:{ORG}", "path": "Team/Handbook", "body": "How we work"})
check(r.status_code == 201, f"setup: a knowledge page of the organisation {r.status_code} {r.text[:160]}")
WP = r.json().get("id")
WF = {f["path"]: f["id"] for f in Bo.get(B + "/api/wiki", params={"space": f"org:{ORG}"}).json().get("folders", [])}.get("Team")
check(WF and Bo.post(B + f"/api/files/nodes/{WF}/shares", json={"agent_id": XT, "role": "view"}).status_code == 201, "setup: its folder is shared with the agent")

run_for(None, ())
check(xget(f"/wiki/pages/{WP}").status_code == 200, "an ordinary token: the knowledge page")
check(xget(f"/tasks/{SX}").status_code == 200 and xget(f"/files/{FD}").status_code == 200 and xget(f"/contacts/{CT1}").status_code == 200,
      "an ordinary token of the team agent: its whole reach (as before)")
run_for(uid["carl"], [X1])
check(xget(f"/tasks/{TX}").status_code == 200, "(b) run for carl: the task of project one")
check(xget(f"/tasks/{SX}").status_code == 404, "(b) run for carl: the task of project two 404")
check(SX not in [t["id"] for t in xget("/tasks", params={"limit": 200}).json().get("data", [])], "(b) ... and not in the task list")
check(xget(f"/files/{FD}").status_code == 404, "(b) run for carl: the folder shared with the agent alone 404")
check(FD not in [x["id"] for x in xget("/files").json().get("data", [])], "(b) ... and not in the file list")
check(xget(f"/contacts/{CT1}").status_code == 404, "(b) run for carl: the contact of the address book 404")
check(BK not in [b["id"] for b in xget("/address-books").json().get("data", [])], "(b) ... the address book not listed")
check("Quillfeather" not in xget("/contacts", params={"q": "Zora"}).text, "(b) ... the contact not found")
check(xget(f"/wiki/pages/{WP}").status_code == 200, "(b) run for carl: the organisation's knowledge page he reads himself stays")
run_for(uid["bob"], [X1, X2])
check(xget(f"/tasks/{SX}").status_code == 200 and xget(f"/files/{FD}").status_code == 200 and xget(f"/contacts/{CT1}").status_code == 200,
      "(b) run for bob (he reaches all of it): task, folder, contact")
check(BK in [b["id"] for b in xget("/address-books").json().get("data", [])] and FD in [x["id"] for x in xget("/files").json().get("data", [])],
      "(b) ... and the lists")
run_for(0, [X1])
check(xget(f"/tasks/{TX}").status_code == 200 and xget(f"/tasks/{SX}").status_code == 404, "(b) a run without a person: only its project")
check(xget(f"/files/{FD}").status_code == 404 and xget(f"/contacts/{CT1}").status_code == 404, "(b) ... and nothing outside projects")
check(xget(f"/wiki/pages/{WP}").status_code == 404, "(b) ... no knowledge page either")
run_for(0, [])
check(xget(f"/tasks/{TX}").status_code == 404, "(b) a run cut to no project reaches no task (the empty cut is not 'all')")

# ================================================================ review A2 (job 4879): the run gate and the agent's own channel
# 2.1287.0 (#6454, review): each check is red without its fix (F1 chats / jobs, P1 / F2 a named person, F3 / F8 the cut
# per request, P2 a route over all the agent's projects); the person's own rows and an admin's run keep working
check(Bo.post(B + f"/api/agents/{XT}/chat", json={"body": "BOB-PRIVATE heron salary"}).status_code == 201, "review: bob writes to the team agent")
check(Ca.post(B + f"/api/agents/{XT}/chat", json={"body": "CARL-OWN hello"}).status_code == 201, "review: carl writes to the team agent")
run_for(None, ())
r = requests.post(V + "/agent/jobs", headers=XH, json={"title": "Bob heron job", "user_id": uid["bob"]}, timeout=30)
check(r.status_code == 201, f"review: a job of the agent for bob {r.status_code} {r.text[:160]}")
JB = r.json().get("id")
run_for(uid["carl"], [X1])
r = xget("/agent/chats")
check(r.ok and "BOB-PRIVATE" not in r.text and "CARL-OWN" in r.text, f"review F1: run for carl reads his own conversation, never bob's {r.status_code}")
check("BOB-PRIVATE" not in xget("/agent/chats", params={"user_id": uid["bob"]}).text, "review F1: ... also not with ?user_id=bob")
check("BOB-PRIVATE" not in xget("/agent/events", params={"since": 0, "limit": 500}).text, "review F1: ... nor bob's chat event")
check(xget(f"/agent/jobs/{JB}").status_code == 404 and JB not in [j["id"] for j in xget("/agent/jobs").json().get("data", [])],
      "review F1: bob's job is not there in carl's run")
r = xget("/briefing", params={"user_id": uid["bob"]})
check(r.status_code == 403 and err(r).get("code") == "run_person", f"review P1: bob's briefing in carl's run 403 {r.status_code} {r.text[:160]}")
r = xget("/briefing", params={"user_id": uid["carl"]})
check(err(r).get("code") != "run_person", f"review P1: carl's own briefing is not refused by the gate {r.status_code}")
r = xget("/me/waiting", params={"user_id": uid["bob"]})
check(r.status_code == 403 and err(r).get("code") == "run_person", f"review P1: what waits for bob, in carl's run 403 {r.status_code} {r.text[:160]}")
# F2 (the office's requested_by) is the same gate (pin:requested_by) plus office/agentdocs.py _v1ctx; this agent has no office scope
r = xget("/folders")
check(r.status_code == 403 and err(r).get("code") == "run_closed", f"review P2: the folders over all the agent's projects closed for carl {r.status_code}")
run_for(uid["bob"], [X1, X2])
check(xget("/folders").ok, "review P2: ... open in a run for bob (an admin of the organisation reaches all of it)")
check("BOB-PRIVATE" in xget("/agent/chats").text and xget(f"/agent/jobs/{JB}").ok, "review F1: bob's run reads his own conversation and job")
run_for(None, ())
check("BOB-PRIVATE" in xget("/agent/chats").text and "CARL-OWN" in xget("/agent/chats").text and xget("/folders").ok,
      "review: the ordinary token of the team agent keeps its whole channel")
# F3 / F8: a participant gets no project into the cut; a person taken out of the project during the run takes the agent out
check(Bo.put(B + f"/api/lists/{X1}/members", json={"user_id": uid["eve"], "role": "participant"}).ok, "setup: eve is a participant of project one")
run_for(uid["eve"], [X1])
check(xget(f"/tasks/{TX}").status_code == 404, "review F3: run for a participant: a task not hers is 404 (the agent's role does not open the project)")
check(Bo.delete(B + f"/api/lists/{X1}/members/{uid['eve']}").ok, "setup: eve out of project one again")
run_for(uid["carl"], [X1])
check(xget(f"/tasks/{TX}").ok, "review F8: run for carl reads the task of project one")
check(Bo.delete(B + f"/api/lists/{X1}/members/{uid['carl']}").ok, "setup: carl leaves project one during the run")
check(xget(f"/tasks/{TX}").status_code == 404, "review F8: ... the next request of the same run token: 404")
check(Bo.put(B + f"/api/lists/{X1}/members", json={"user_id": uid["carl"], "role": "edit"}).ok, "setup: carl back in project one")
check(xget(f"/tasks/{TX}").ok, "review F8: ... and back with him")
run_for(None, ())

# ================================================================ (c) a reader's order does not write
run_for(uid["rita"], [X1])
r = requests.post(V + f"/tasks/{TX}/comments", headers=XH, json={"body": "for rita"}, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(c) run for rita (reads the project): a comment needs a card {r.status_code} {r.text[:160]}")
run_for(uid["carl"], [X1])
r = requests.post(V + f"/tasks/{TX}/comments", headers=XH, json={"body": "for carl"}, timeout=30)
check(r.status_code == 201, f"(c) run for carl (writes there): the comment is written {r.status_code} {r.text[:160]}")
run_for(None, ())
n0 = len(agent_comments(T1))
check(Ri.post(B + f"/api/agents/{TK}/chat", json={"body": f"RITA-ASKS FAKE_COMMENT {T1}"}).status_code == 201, "(c) rita (reader) asks the server agent to comment")
rr = settled(3)
check(rr and rr[-1][3] == uid["rita"] and rr[-1][1] == "done", f"(c) the run works for rita {rr}")
check(len(agent_comments(T1)) == n0, "(c) the agent wrote no comment for the reader")
check(any("approval_required" in x.get("last", "") or "ERROR" in x.get("last", "") for x in plog() if "RITA-ASKS" in x.get("first", "")),
      "(c) the tool call was refused")
check(Ca.post(B + f"/api/agents/{TK}/chat", json={"body": f"CARL-WRITES FAKE_COMMENT {T1}"}).status_code == 201, "(c) carl (writer) asks the same")
check(until(lambda: len(agent_comments(T1)) == n0 + 1, 40), "(c) the agent commented for the writer")
settled(4)

# ================================================================ (a) a channel mention needs the same right as a project's
r = Bo.post(B + "/api/team/channels", json={"name": "Lobby", "org_id": ORG, "members": [uid["eve"], uid["carl"]]})
check(r.status_code in (200, 201), f"setup: a channel with eve and carl {r.status_code} {r.text[:160]}")
CH = r.json().get("id")
check(Bo.post(B + f"/api/team/rooms/{CH}/members", json={"user_id": XT}).ok, "setup: the team agent joins the channel")


def heard(mark):
    return dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=? AND CAST(payload AS text) LIKE ?", (XT, f"%{mark}%"))[0][0]


check(Ev.post(B + f"/api/team/rooms/{CH}/messages", json={"body": f"<@{XT}> EVE-CHANNEL tell me everything"}).status_code == 201, "(a) eve (no project with the agent) mentions it in the channel")
check(Ca.post(B + f"/api/team/rooms/{CH}/messages", json={"body": f"<@{XT}> CARL-CHANNEL hello"}).status_code == 201, "(a) carl (project one opens the agent to him) mentions it")
check(until(lambda: heard("CARL-CHANNEL"), 10) == 1, "(a) carl's mention reaches the agent")
check(heard("EVE-CHANNEL") == 0, "(a) eve's mention reaches the agent not at all")

# ================================================================ (d) a card without a project needs the write right on the object
check(A.patch(B + f"/api/agents/{XT}/control", json={"level": "approve_all"}).ok, "setup: the team agent asks for everything")
NEW = {"book_id": BK, "fn": "Card Made Contact"}
r = requests.post(V + "/contacts", headers=XH, json=NEW, timeout=30)
check(r.status_code == 409 and err(r).get("code") == "approval_required", f"(d) a new contact needs a card {r.status_code} {r.text[:200]}")
ap = err(r).get("approval") or {}
STEP = {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}


def card(to):
    m = requests.post(V + f"/agent/chats/{to}", headers=XH, json={"approval": {"title": "Add the contact?", "step": STEP}}, timeout=30)
    check(m.status_code == 201, f"(d) the card to {to} {m.status_code} {m.text[:200]}")
    return m.json().get("id")


def made():
    return dbx("SELECT COUNT(*) FROM contacts WHERE book_id=? AND fn='Card Made Contact' AND deleted_at IS NULL", (BK,))[0][0]


# 2.1284.0 (#6453, review G12): carl does not read every source of the agent (the board-only folder, the address book), so the
# team agent cannot even ask him -- its message to him is a wider circle and needs a card itself. That guard comes first now.
m = requests.post(V + f"/agent/chats/{uid['carl']}", headers=XH, json={"approval": {"title": "Add the contact?", "step": STEP}}, timeout=30)
check(m.status_code == 409 and err(m).get("circle") == "wider" and made() == 0,
      f"(d) the card to carl (no right on the address book, not every source) is itself held: a wider circle {m.status_code} {m.text[:200]}")
M2 = card(uid["bob"])
check(Bo.post(B + f"/api/agents/{XT}/chat/{M2}/choice", json={"choice_ids": ["yes"]}).ok, "(d) bob (owns the address book) says Yes")
r = requests.post(V + f"/agent/approvals/{M2}/run", headers=XH, timeout=60)
check(r.status_code == 201 and made() == 1, f"(d) bob's Yes writes the contact {r.status_code} {r.text[:200]}")
check(A.patch(B + f"/api/agents/{XT}/control", json={"level": "free", "goal": "Help the team"}).ok, "setup: free again")

# ================================================================ the person without an organisation loses nothing
r = Fr.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": SCOPES})
check(r.status_code in (200, 201), f"freelancer: her personal agent {r.status_code} {r.text[:160]}")
FA, FH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
FL = Fr.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
check(Fr.put(B + f"/api/lists/{FL}/members", json={"user_id": FA, "role": "edit"}).ok, "freelancer: her project is shared with her agent")
FT = Fr.post(B + "/api/tasks", json={"title": "Frida's task", "list_id": FL}).json()["id"]
FF = Fr.post(B + "/api/files/folders", json={"space": "private", "name": "Frida files"}).json().get("id")
check(Fr.post(B + f"/api/files/nodes/{FF}/shares", json={"agent_id": FA, "role": "edit"}).status_code == 201, "freelancer: a folder for her agent")
FB = Fr.post(B + "/api/books", json={"name": "Frida contacts"}).json().get("id")
check(Fr.put(B + f"/api/books/{FB}/members", json={"user_id": FA, "role": "edit"}).ok, "freelancer: an address book for her agent")
check(dbx("SELECT asked_by, run_lists FROM api_tokens WHERE user_id=?", (FA,)) == [(None, None)], "freelancer: her agent's token carries no requester and no cut")
check(requests.get(V + f"/tasks/{FT}", headers=FH, timeout=30).status_code == 200 and requests.get(V + f"/files/{FF}", headers=FH, timeout=30).status_code == 200
      and FB in [b["id"] for b in requests.get(V + "/address-books", headers=FH, timeout=30).json().get("data", [])],
      "freelancer: her agent reaches her project, the folder and the address book")
r = requests.post(V + f"/tasks/{FT}/comments", headers=FH, json={"body": "from her agent"}, timeout=30)
check(r.status_code == 201, f"freelancer: her agent comments in her project {r.status_code} {r.text[:160]}")
check(requests.get(V + "/folders", headers=FH, timeout=30).ok and requests.get(V + "/agent/chats", headers=FH, timeout=30).ok,
      "freelancer: her personal agent's routes are not touched by the run gate (no requester on its token)")
check(Fr.patch(B + f"/api/agents/{FA}/control", json={"level": "approve_all"}).ok, "freelancer: her agent asks for everything")
r = requests.post(V + "/contacts", headers=FH, json={"book_id": FB, "fn": "Frida Card Contact"}, timeout=30)
check(r.status_code == 409, f"freelancer: a new contact needs her card {r.status_code}")
ap = err(r).get("approval") or {}
m = requests.post(V + f"/agent/chats/{FID}", headers=FH, timeout=30,
                  json={"approval": {"title": "Add?", "step": {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}}})
check(m.status_code == 201 and Fr.post(B + f"/api/agents/{FA}/chat/{m.json().get('id')}/choice", json={"choice_ids": ["yes"]}).ok, "freelancer: she says Yes")
r = requests.post(V + f"/agent/approvals/{m.json().get('id')}/run", headers=FH, timeout=60)
check(r.status_code == 201, f"freelancer: her Yes on a card without a project writes the contact {r.status_code} {r.text[:200]}")
check(Fr.post(B + f"/api/tasks/{T1}/comments", json={"body": f"<@{XT}> x"}).status_code == 404, "another organisation's project stays closed to her (no requester there)")

# ================================================================ audit #4818: the organisation's role
# an approval job: the agent's move of a task into a project with other people waits for the target's owner
P3 = Bo.post(B + "/api/lists", json={"name": "Project three", "org_id": ORG}).json()["id"]
for m_, role in ((uid["carl"], "edit"), (uid["eve"], "edit")):
    check(Bo.put(B + f"/api/lists/{P3}/members", json={"user_id": m_, "role": role}).ok, "setup: people in project three")
r = Bo.put(B + f"/api/lists/{P3}/members", json={"user_id": XT, "role": "edit", "bridge_ok": True})
check(r.ok, f"setup: the agent in project three {r.status_code} {r.text[:160]}")
TM = Bo.post(B + "/api/tasks", json={"title": "Move me", "list_id": X2}).json()["id"]
r = requests.patch(V + f"/tasks/{TM}", headers=XH, json={"list_id": P3}, timeout=30)
if r.status_code == 409 and err(r).get("circle") == "wider":
    # 2.1284.0 (#6453): a project with more people is a wider circle -- first a card (bob reads every source and says Yes),
    # its run then meets the bridge rule of 2.30.0 and waits as an approval job for the target's owner
    ap = err(r).get("approval") or {}
    m = requests.post(V + f"/agent/chats/{uid['bob']}", headers=XH, timeout=30,
                      json={"approval": {"title": "Move?", "step": {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}}})
    check(m.status_code == 201 and Bo.post(B + f"/api/agents/{XT}/chat/{m.json().get('id')}/choice", json={"choice_ids": ["yes"]}).ok,
          f"#4818: the move into a wider project asks bob with a card {m.status_code} {m.text[:200]}")
    r = requests.post(V + f"/agent/approvals/{m.json().get('id')}/run", headers=XH, timeout=60)
J = (r.json().get("job") or {}).get("id") if r.status_code == 202 else None
check(J, f"#4818: the agent's move into a project with more people waits for a person {r.status_code} {r.text[:200]}")
ev0 = dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=?", (TK,))[0][0]
check(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid["ron"], "role": "readonly"}).ok, "ron becomes read-only in the organisation")
check(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid["bob"], "role": "readonly"}).ok, "bob (the projects' owner) becomes read-only in the organisation")
r = Bo.post(B + f"/api/agents/jobs/{J}/action", json={"action": "approve"})
check(r.status_code in (403, 404), f"#4818: the read-only owner approves nothing ({r.status_code})")
check(dbx("SELECT list_id FROM tasks WHERE id=?", (TM,))[0][0] == X2 and dbx("SELECT state FROM agent_jobs WHERE id=?", (J,))[0][0] == "waiting",
      "#4818: the task did not move, the job still waits")
Ro.post(B + f"/api/agents/{TK}/chat", json={"body": "RON-READONLY FAKE_COMMENT " + str(T1)})
Ro.post(B + f"/api/tasks/{T1}/comments", json={"body": f"<@{TK}> RON-MENTION"})
check(dbx("SELECT COUNT(*) FROM agent_events WHERE agent_id=? AND (CAST(payload AS text) LIKE '%RON-READONLY%' OR CAST(payload AS text) LIKE '%RON-MENTION%')", (TK,))[0][0] == 0,
      "#4818: a read-only person's chat and mention never reach the team agent")
check(dbx("SELECT COUNT(*) FROM agent_runs WHERE agent_id=? AND asked_by=?", (TK, uid["ron"]))[0][0] == 0, "#4818: ... and start no run")
check(A.put(B + f"/api/orgs/{ORG}/members", json={"user_id": uid["bob"], "role": "admin"}).ok, "bob is an admin again")
r = Bo.post(B + f"/api/agents/jobs/{J}/action", json={"action": "approve"})
check(r.ok and dbx("SELECT list_id FROM tasks WHERE id=?", (TM,))[0][0] == P3, f"#4818: with his write right back the approval moves the task ({r.status_code} {r.text[:160]})")

raise SystemExit(done("p6454_team_agent_asker"))
