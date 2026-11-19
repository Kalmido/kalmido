#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1284.0 (#6453): an agent writes without a card only towards the same or a smaller circle of people (agents/circle.py).
Invented people only. All of it as people WITHOUT an organisation and their personal agents (freelancer-matrix: agents).
 - one project only: no card from this rule (nothing can flow)
 - private -> shared (a project one more person reads): 409 approval_required with circle "wider", on routine and on free;
   shared -> private: free; two projects with the same people: free in both
 - the approval card of such a step is marked by the server (circle), never by the agent; after the person's Yes it runs
 - public = everyone: a project with a live public link (an expired one: no), a task with a client report of the portal (an
   internal comment there: free), a knowledge page a public link covers (the card's mark) -> circle "public"
 - a card made before the project became public no longer fits (approval_invalid, reason circle); the link gone: it runs
 - the reach counts every kind: a knowledge folder shared with the agent that the other person does not see makes the
   shared project a wider place; the share gone: free again
 - the progress line: in a wider / public project the mark is set, the agent's words are not shown (also a line written
   through the job's log), the answer says so; in its private project the text shows as before
 - a team agent in an organisation: the project open to "everyone in the organisation" is wider than its owner's own one
 - approve_all stays as it was (every write a card, no new field without need)
Fable review of 16.11.2026 (each case red without its fix):
 - G1: a parent's project is a target -- POST /tasks {list_id private, parent_id in the shared one}, PATCH / move {parent_id};
   an agent without a level: the move by parent waits for approval (safety.move_gate)
 - G2: a target without a project is checked against every source: a folder one more person reads + a private project =
   the card says "wider", a folder only the owner reads: no mark; a target the gate cannot name (polls) + more than one
   source = "wider", one source: nothing
 - G3: a batch over ALL the agent's projects is no "one project only"
 - G4: the job list hides title, name and log of a job in a wider place from other viewers
 - G5: an approved bridge is free, but only for the circles of the approval: one more person = a card and the share asks again
 - G6: a participant is no reader of the whole project
 - G9: a page / a task of somebody else gives the same answer as one that does not exist
 - G12: a team agent's message to a person who does not read all it reads = a card; its status text is hidden from them
 - G13: the Yes of a person who does not read the sources does not count (approver_rights)
2.1398.0 (#6863): a team agent's job for a person (POST /agent/jobs user_id, PATCH of its log) = a message to them; a job
without a task hides its words from who does not read everything; rules / playbook / layout proposals are writes into the
project; reader F7: a waiting job with a task but no person sends News / push without its title where job_dict hides it
 - also: a chat room without a project, a new page in a folder of a shared space
usage: p6453_circle_test.py <datadir>"""
import json
import os
import subprocess
import sys
from datetime import timedelta, timezone

import requests

import kt
from freelancer_fixture import freelancer, login
from kt import B, apv_body, check, done, fresh, setup
# 2.1386.0 (#6623): a Yes on an approval card with a bound step carries the proof of the description (kt.apv_body)
from testclock import now

V = B + "/api/v1"
os.environ["KALMIDO_AGENT_CONTROL_NEW"] = "approve_all"  # the real default (tests/start.sh starts other suites with legacy)
fresh(prefix="P6453")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
r = A.put(B + "/api/admin/agent-policy", json={"user_agents": True, "max_per_user": 12})  # 2.1284.0 (#6453): the review cases need more agents
assert r.ok, r.text
FID, F = freelancer(B, A)
OID, OTTO = freelancer(B, A, "otto")
SCOPES = ["read", "tasks:write", "comments", "wiki:read", "wiki:write"]


def ts(hours=0):
    return (now() + timedelta(hours=hours)).astimezone(timezone.utc).isoformat(timespec="seconds")


def err(r):
    try:
        return r.json()["error"]
    except (ValueError, KeyError, TypeError):
        return {}


def agent(name):
    r = F.post(B + "/api/my/agents", json={"username": name, "display_name": name.title(), "scopes": SCOPES})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}


def ctl(aid, patch):
    r = F.patch(B + f"/api/agents/{aid}/control", json=patch)
    assert r.ok, r.text


def project(name, *agents, shared=False):
    lid = F.post(B + "/api/lists", json={"name": name}).json()["id"]
    if shared:  # otto reads it too (as an accepted invitation leaves it)
        kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?) ON CONFLICT DO NOTHING", (lid, OID, ts()))
    for aid in agents:
        join(lid, aid)
    return lid


def join(lid, aid):
    r = F.put(B + f"/api/lists/{lid}/members", json={"user_id": aid, "role": "edit"})
    assert r.ok, r.text


def task(lid, title):
    r = F.post(B + "/api/tasks", json={"title": title, "list_id": lid})
    assert r.ok, r.text
    return r.json()["id"]


def comment(h, tid, text="A note", **kw):
    return requests.post(V + f"/tasks/{tid}/comments", headers=h, json={"body": text, **kw})


def free(r, why):
    check(r.status_code in (200, 201), f"{why} -> free ({r.status_code} {r.text[:200]})")


def card(r, circle, why):
    e = err(r)
    check(r.status_code == 409 and e.get("code") == "approval_required" and e.get("circle") == circle,
          f"{why} -> 409 approval_required, circle {circle} ({r.status_code} {r.text[:260]})")
    return e


def ask(h, e, title="Write there"):
    ap = e.get("approval") or {}
    st = {k: ap[k] for k in ("method", "path", "body", "if_match") if k in ap}
    r = requests.post(V + f"/agent/chats/{FID}", headers=h, json={"approval": {"title": title, "what": title, "step": st}})
    check(r.status_code == 201, f"the approval card {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def mark(mid):
    return (kt.dbx("SELECT choices->'approval'->>'circle' FROM agent_chat WHERE id=?", (mid,)) or [[None]])[0][0]


def yes(aid, mid):
    r = F.post(B + f"/api/agents/{aid}/chat/{mid}/choice", json=apv_body(F, B, f"chat:{mid}", "yes"))
    assert r.ok, r.text


def run(h, mid):
    return requests.post(V + f"/agent/approvals/{mid}/run", headers=h)


# ================================================================== directions: private, shared, the same people
FA, H = agent("fridabot")
ctl(FA, {"level": "routine"})
PRIV = project("Frida private", FA)
T_PRIV = task(PRIV, "Private task")
free(comment(H, T_PRIV), "one project only")
free(requests.post(V + "/tasks", headers=H, json={"title": "By the agent", "list_id": PRIV}), "one project only: a new task")

SHARED = project("With Otto", FA, shared=True)
T_SH = task(SHARED, "Shared task")
e = card(comment(H, T_SH, "from the private project"), "wider", "private -> shared: a comment")
check(e.get("step") == "routine" and e.get("level") == "routine", f"... the step and the level stay what they are {e.get('step')} {e.get('level')}")
check("more people" in (e.get("message") or ""), f"... the answer says why {e.get('message')}")
card(requests.post(V + "/tasks", headers=H, json={"title": "Into the shared one", "list_id": SHARED}), "wider", "private -> shared: a new task")
card(requests.post(V + f"/tasks/{T_SH}/complete", headers=H), "wider", "private -> shared: ticking off")
check(not kt.dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=?", (T_SH,)), "... nothing was written")
free(comment(H, T_PRIV, "from the shared project"), "shared -> private")

# the card: marked by the server, runs after the Yes
MID = ask(H, e)
check(mark(MID) == "wider", f"the card of the step is marked 'wider' by the server ({mark(MID)})")
r = requests.post(V + f"/agent/chats/{FID}", headers=H, json={"approval": {"title": "x", "what": "x", "circle": "public",
                                                                           "step": {"method": "POST", "path": f"/api/v1/tasks/{T_PRIV}/comments", "body": {"body": "y"}}}})
check(r.status_code == 400, f"the agent cannot set the mark itself ({r.status_code})")
M2 = ask(H, {"approval": {"method": "POST", "path": f"/api/v1/tasks/{T_PRIV}/comments", "body": {"body": "y"}}})
check(mark(M2) is None, f"a card for the private project carries no mark ({mark(M2)})")
check(err(run(H, MID)).get("reason") == "unanswered", "before the Yes the card runs nothing")
yes(FA, MID)
r = run(H, MID)
check(r.status_code == 201 and kt.dbx("SELECT 1 FROM obj_comments WHERE kind='task' AND ref_id=?", (T_SH,)),
      f"after the Yes the comment is written ({r.status_code} {r.text[:200]})")

# free with a goal: the same rule
ctl(FA, {"level": "free"})
card(comment(H, T_SH, "free"), "wider", "free, private -> shared")
card(requests.patch(V + f"/tasks/{T_SH}", headers=H, json={"title": "Renamed", "expect_updated_at": requests.get(V + f"/tasks/{T_SH}", headers=H).json()["updated_at"]}),
     "wider", "free, private -> shared: a change")
free(comment(H, T_PRIV, "free"), "free, shared -> private")

# approve_all: as before -- every write a card, the circle adds nothing
ctl(FA, {"level": "approve_all"})
for tid, why in ((T_PRIV, "private"), (T_SH, "shared")):
    r = comment(H, tid, "x")
    e2 = err(r)
    check(r.status_code == 409 and e2.get("code") == "approval_required" and e2.get("level") == "approve_all" and "circle" not in e2,
          f"approve_all, {why}: the card of the level as before ({r.status_code} {sorted(e2)})")

# the same people in two projects: no card
FB, HB = agent("samebot")
ctl(FB, {"level": "routine"})
S1 = project("Shared one", FB, shared=True)
S2 = project("Shared two", FB, shared=True)
free(comment(HB, task(S1, "One")), "the same people: the first project")
free(comment(HB, task(S2, "Two")), "the same people: the second project")

# ================================================================== public = everyone
FC, HC = agent("pubbot")
ctl(FC, {"level": "routine"})
PUB = project("Soon public", FC)
T_PUB = task(PUB, "Public task")
free(comment(HC, T_PUB), "no link yet")
ctl(FC, {"level": "approve_all"})
e = err(comment(HC, T_PUB, "approved before the link"))
M_OLD = ask(HC, e)
check(mark(M_OLD) is None, "a card made before the link: no mark")
yes(FC, M_OLD)
ctl(FC, {"level": "routine"})
kt.dbx("INSERT INTO public_links(list_id,token_hash,token,mode,created_at) VALUES(?,?,?,'view',?)", (PUB, "h" * 64, "sealed", ts()))
e = card(comment(HC, T_PUB, "into the public project"), "public", "a project with a public link")
check("publicly" in (e.get("message") or ""), f"... the answer says publicly visible {e.get('message')}")
card(requests.post(V + "/tasks", headers=HC, json={"title": "Public?", "list_id": PUB}), "public", "a project with a public link: a new task")
r = run(HC, M_OLD)
check(r.status_code == 409 and err(r).get("code") == "approval_invalid" and err(r).get("reason") == "circle",
      f"the card from before the link no longer fits: reason circle ({r.status_code} {r.text[:200]})")
M_NEW = ask(HC, e)
check(mark(M_NEW) == "public", f"the new card is marked 'public' ({mark(M_NEW)})")
yes(FC, M_NEW)
check(run(HC, M_NEW).status_code == 201, "... and runs after the Yes")
kt.dbx("UPDATE public_links SET expires_at=? WHERE list_id=?", (ts(-1), PUB))
free(comment(HC, T_PUB, "expired"), "an expired public link")
check(run(HC, M_OLD).status_code == 201, "the old card runs once the project is not public any more")
kt.dbx("DELETE FROM public_links WHERE list_id=?", (PUB,))

# the portal: a task with a client report
T_TICKET, T_PLAIN = task(PUB, "Client's report"), task(PUB, "Internal")
kt.dbx("INSERT INTO portal_tickets(task_id,list_id,owner_id,name,token,token_hash,created_at) VALUES(?,?,?,?,?,?,?)",
       (T_TICKET, PUB, FID, "A client", "sealed", "p" * 64, ts()))
card(requests.post(V + f"/tasks/{T_TICKET}/complete", headers=HC), "public", "a task with a client report: its state")
free(comment(HC, T_TICKET, "internal note"), "an internal comment on it (never leaves the app)")
free(requests.post(V + f"/tasks/{T_PLAIN}/complete", headers=HC), "another task of the project")

# a knowledge page a public link covers: the card says so (a change of a page is a card for a personal agent anyway)
r = F.post(B + "/api/wiki/pages", json={"space": "private", "path": "Docs/Guide", "body": "text"})
assert r.status_code == 201, r.text
PAGE = r.json()["id"]
j = F.get(B + "/api/wiki", params={"space": "private"}).json()
DOCS = {f["path"]: f["id"] for f in j.get("folders", [])}["Docs"]
r = F.post(B + f"/api/files/nodes/{DOCS}/shares", json={"agent_id": FC, "role": "edit"})
assert r.status_code == 201, r.text
SH_FC = r.json()["id"]
pg = requests.get(V + f"/wiki/pages/{PAGE}", headers=HC)
check(pg.ok, f"setup: the agent reads the page {pg.status_code}")
step = {"approval": {"method": "PATCH", "path": f"/api/v1/wiki/pages/{PAGE}", "body": {"body": "new", "expect_updated_at": pg.json().get("updated_at")}}}
check(mark(ask(HC, step)) is None, "a page nobody else reads: no mark")
r = F.post(B + "/api/wiki/shares", json={"page_id": PAGE, "kind": "link"})
check(r.status_code in (200, 201), f"setup: a public link of the page {r.status_code} {r.text[:200]}")
check(mark(ask(HC, step)) == "public", "a page with a public link: the card is marked 'public'")
assert F.delete(B + f"/api/files/shares/{SH_FC}").ok

# ================================================================== the reach counts every kind
FD, HD = agent("reachbot")
ctl(FD, {"level": "routine"})
ONLY = project("Only shared", FD, shared=True)
T_ONLY = task(ONLY, "Shared")
free(comment(HD, T_ONLY), "one shared project, nothing else")
r = F.post(B + f"/api/files/nodes/{DOCS}/shares", json={"agent_id": FD, "role": "view"})
assert r.status_code == 201, r.text
card(comment(HD, T_ONLY, "from the knowledge folder"), "wider", "a knowledge folder the other person does not see + the shared project")
assert F.delete(B + f"/api/files/shares/{r.json()['id']}").ok
free(comment(HD, T_ONLY, "again"), "the folder's share gone")

# ================================================================== an organisation: a project open to everyone in it
r = A.post(B + "/api/orgs", json={"name": "Beispiel Studio"})
assert r.ok, r.text
ORG = r.json()["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": kt.PASSWORD, "email": "bob@example.com",
                                   "orgs": [{"id": ORG, "role": "member"}]})
assert r.ok, r.text
BOB = r.json()["id"]
r = A.post(B + "/api/admin/agents", json={"username": "teambot", "display_name": "Team", "scopes": SCOPES + ["structure", "layouts"],
                                          "org_id": ORG})  # 2.1398.0 (#6863): structure / layouts for the rules / layout proposals
assert r.status_code in (200, 201), r.text
TA, HT = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
r = A.patch(B + f"/api/agents/{TA}/control", json={"level": "routine"})
assert r.ok, r.text
L_OWN = A.post(B + "/api/lists", json={"name": "Alice only", "kind": "project", "org_id": ORG}).json()["id"]
L_ALL = A.post(B + "/api/lists", json={"name": "For everyone", "kind": "project", "org_id": ORG}).json()["id"]
assert A.patch(B + f"/api/lists/{L_ALL}", json={"org_visibility": "org"}).ok
for x in (L_OWN, L_ALL):
    r = A.put(B + f"/api/lists/{x}/members", json={"user_id": TA, "role": "edit"})
    assert r.ok, r.text
check(kt.dbx("SELECT org_visibility FROM lists WHERE id=?", (L_ALL,))[0][0] == "org" and kt.dbx("SELECT 1 FROM org_members WHERE org_id=? AND user_id=?", (ORG, BOB)),
      "setup: the project is open to the organisation, bob is a member of it")
K_OWN = A.post(B + "/api/tasks", json={"title": "Alice's", "list_id": L_OWN}).json()["id"]
K_ALL = A.post(B + "/api/tasks", json={"title": "Everyone's", "list_id": L_ALL}).json()["id"]
card(comment(HT, K_ALL, "from alice's own project"), "wider", "a team agent: into the project everyone in the organisation reads")
free(comment(HT, K_OWN, "from the open project"), "a team agent: into the project only its owner reads")

# ================================================================== review G1: the parent's project is a target
def upd(h, tid):
    return requests.get(V + f"/tasks/{tid}", headers=h).json()["updated_at"]


ctl(FA, {"level": "routine"})
card(requests.post(V + "/tasks", headers=H, json={"title": "Sub", "list_id": PRIV, "parent_id": T_SH, "notes": "private words"}),
     "wider", "G1 A: a new task with list_id private and a parent in the shared project")
check(not kt.dbx("SELECT 1 FROM tasks WHERE parent_id=?", (T_SH,)), "... no subtask was made in the shared project")
ctl(FA, {"level": "free"})
T_MV = task(PRIV, "Moves?")
card(requests.patch(V + f"/tasks/{T_MV}", headers=H, json={"parent_id": T_SH, "expect_updated_at": upd(H, T_MV)}),
     "wider", "G1 B: PATCH {parent_id: a task of the shared project}")
card(requests.post(V + f"/tasks/{T_MV}/move", headers=H, json={"parent_id": T_SH}), "wider", "G1 B: move {parent_id}")
check(kt.dbx("SELECT list_id, parent_id FROM tasks WHERE id=?", (T_MV,))[0] == (PRIV, None), "... the task stayed where it was")
kt.dbx("UPDATE agents SET control='' WHERE user_id=?", (FA,))  # an agent from before the levels: only safety.move_gate stands
for r, why in ((requests.post(V + f"/tasks/{T_MV}/move", headers=H, json={"parent_id": T_SH}), "move"),
               (requests.patch(V + f"/tasks/{T_MV}", headers=H, json={"parent_id": T_SH, "expect_updated_at": upd(H, T_MV)}), "PATCH")):
    check(r.status_code == 202 and kt.dbx("SELECT list_id FROM tasks WHERE id=?", (T_MV,))[0][0] == PRIV,
          f"G1: no level, {why} by parent into the shared project waits for approval ({r.status_code} {r.text[:160]})")
# 2.1284.0 (#6453, Fable reader #4945 F1): a body naming a parent in the private project AND list_id = the shared one, with a
# _prev that makes apply_update drop the parent as a conflict: the task went to list_id while the gate only looked at the
# parent's project. Every project the body names is a target now (safety.move_dst), with no level and on "free"
T_PP = task(PRIV, "Private parent")
for lvl in ("", "free"):
    if lvl:
        ctl(FA, {"level": lvl})
    else:
        kt.dbx("UPDATE agents SET control='' WHERE user_id=?", (FA,))
    T_PV = task(PRIV, f"Prev trick {lvl or 'no level'}")
    r = requests.patch(V + f"/tasks/{T_PV}", headers=H, json={"parent_id": T_PP, "list_id": SHARED,
                                                               "_prev": {"parent_id": T_SH, "list_id": PRIV}})
    ok = (r.status_code == 202) if not lvl else (r.status_code == 409 and err(r).get("code") == "approval_required")
    check(ok and kt.dbx("SELECT list_id FROM tasks WHERE id=?", (T_PV,))[0][0] == PRIV,
          f"#4945 F1 ({lvl or 'no level'}): parent private + list_id shared + _prev dropping the parent waits, the task stays private ({r.status_code} {r.text[:200]})")
ctl(FA, {"level": "routine"})

# 2.1284.0 (#6453, Fable reader #4926 F1): the gate reads an id exactly as the route does (tasks/validation.py as_int strips
# and allows leading zeros) - ' 7', '7 ', '07' named the shared project for the route but nothing for the gate
SEC_SH = kt.dbx("INSERT INTO sections(list_id,name) VALUES(?,?) RETURNING id", (SHARED, "Shared section"))[0][0]
for form in (" {}", "{} ", "0{}"):
    for key, val in (("list_id", SHARED), ("parent_id", T_SH), ("section_id", SEC_SH)):
        idv = form.format(val)
        body = {"title": f"Spelled {key}", "notes": "private words", key: idv}
        if key != "list_id":
            body["list_id"] = PRIV
        n0 = kt.dbx("SELECT count(*) FROM tasks WHERE list_id=?", (SHARED,))[0][0]
        card(requests.post(V + "/tasks", headers=H, json=body), "wider", f"F1: POST /tasks {key}={idv!r}")
        check(kt.dbx("SELECT count(*) FROM tasks WHERE list_id=?", (SHARED,))[0][0] == n0, f"F1: ... nothing made in the shared project ({key}={idv!r})")
        ctl(FA, {"level": "free"})  # a change passes on "free" only (on "routine" every PATCH waits anyway, like G1 B above)
        T_SP = task(PRIV, f"Spelled move {key}")
        body = {key: idv, "expect_updated_at": upd(H, T_SP)}
        card(requests.patch(V + f"/tasks/{T_SP}", headers=H, json=body), "wider", f"F1: PATCH /tasks {key}={idv!r}")
        check(kt.dbx("SELECT list_id FROM tasks WHERE id=?", (T_SP,))[0][0] == PRIV, f"F1: ... the task stayed private ({key}={idv!r})")
        ctl(FA, {"level": "routine"})

# ================================================================== review G3: a batch over all its projects
FG, HG = agent("batchbot")
ctl(FG, {"level": "free"})
P3, S3 = project("Batch private", FG), project("Batch shared", FG, shared=True)
T_P3, T_S3 = task(P3, "p"), task(S3, "s")
r = requests.post(V + "/tasks", headers=HG, json={"title": "In its basket"})
free(r, "a new task in the agent's own basket (nobody else reads it)")
T_I3 = r.json().get("id")
r = requests.post(V + "/tasks/batch", headers=HG, json={"ids": [T_I3, T_P3, T_S3], "action": "update", "changes": {"notes": "private words"},
                                                        "_prev": {str(t): {"notes": ""} for t in (T_I3, T_P3, T_S3)}})
e = err(r)  # the basket is the agent's own: the owner's rights cap the level there, so the card comes from the level -- its mark from the circle
check(r.status_code == 409 and e.get("code") == "approval_required", f"G3: a batch over everything the agent reaches (basket, private, shared) -> a card ({r.status_code} {r.text[:200]})")
check(mark(ask(HG, e)) == "wider", "G3: ... and the card says 'wider' (reach and targets together are more than one project)")
check(not kt.dbx("SELECT 1 FROM tasks WHERE id=? AND COALESCE(content,'')<>''", (T_S3,)), "... nothing was written into the shared task")

# ================================================================== review G6: a participant does not read the whole project
FP, HP = agent("partbot")
ctl(FP, {"level": "routine"})
PP = project("With a participant", FP)
kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'participant',?) ON CONFLICT DO NOTHING", (PP, OID, ts()))
SP = project("Both read it", FP, shared=True)
card(comment(HP, task(SP, "Shared"), "from the tasks otto does not see"), "wider", "G6: source with a participant -> the project he reads whole")
free(comment(HP, task(PP, "Partly"), "from the shared project"), "... the other way (he reads the whole source)")

# ================================================================== review G2: targets without a project; G9: no oracle
FN, HN = agent("nodebot")
ctl(FN, {"level": "routine"})
PN = project("Node private", FN)


def folder(name, *people):
    r = F.post(B + "/api/files/folders", json={"name": name, "space": "private"})
    assert r.status_code in (200, 201), r.text
    for k, v, role in (("agent_id", FN, "edit"),) + tuple(("user_id", u, "view") for u in people):
        r2 = F.post(B + f"/api/files/nodes/{r.json()['id']}/shares", json={k: v, "role": role})
        assert r2.status_code == 201, r2.text
    return r.json()["id"]


def step(method, path, body):
    return {"approval": {"method": method, "path": "/api/v1" + path, "body": body}}


N_OWN, N_WIDE = folder("Only mine"), folder("With otto", OID)
note = {"name": "note.txt", "content": "private words"}
check(mark(ask(HN, step("POST", "/files", {**note, "parent_id": N_OWN}))) is None, "G2: a folder only the owner reads: no mark")
check(mark(ask(HN, step("POST", "/files", {**note, "parent_id": N_WIDE}))) == "wider",
      "G2: a folder one more person reads, the agent also reads a private project: the card says 'wider'")
check(mark(ask(HN, step("POST", "/polls", {"title": "x"}))) == "wider", "G2: a target the gate cannot name + more than one source: 'wider'")
r = requests.post(V + f"/agent/chats/{FID}", headers=HN, json={"approval": {"title": "x", "what": "x", "step": {"method": "POST", "path": "/api/v1/lists", "body": {"name": "Its own"}}}})
check(r.status_code == 201 and mark(r.json()["id"]) is None, f"a personal agent's new own project: nobody else reads it, no mark ({r.status_code})")
FS, HS = agent("solobot")
ctl(FS, {"level": "routine"})
project("Solo", FS)
r = requests.post(V + f"/agent/chats/{FID}", headers=HS, json={"approval": {"title": "x", "what": "x", "step": step("POST", "/polls", {"title": "x"})["approval"]}})
check(r.status_code == 201 and mark(r.json()["id"]) is None, f"... one source only: no mark ({r.status_code})")

r = OTTO.post(B + "/api/wiki/pages", json={"space": "private", "path": "Otto/Secret", "body": "text"})
assert r.status_code == 201, r.text
O_PAGE = r.json()["id"]
assert OTTO.post(B + "/api/wiki/shares", json={"page_id": O_PAGE, "kind": "link"}).status_code in (200, 201)
m_there = mark(ask(HN, step("PATCH", f"/wiki/pages/{O_PAGE}", {"body": "y"})))
m_none = mark(ask(HN, step("PATCH", "/wiki/pages/99999999", {"body": "y"})))
check(m_there == m_none and m_there != "public", f"G9: somebody else's page with a public link answers like no page ({m_there} / {m_none})")
O_LIST = OTTO.post(B + "/api/lists", json={"name": "Otto alone"}).json()["id"]
O_TASK = OTTO.post(B + "/api/tasks", json={"title": "Otto's client report", "list_id": O_LIST}).json()["id"]
kt.dbx("INSERT INTO portal_tickets(task_id,list_id,owner_id,name,token,token_hash,created_at) VALUES(?,?,?,?,?,?,?)",
       (O_TASK, O_LIST, OID, "A client", "sealed2", "q" * 64, ts()))
r1 = requests.post(V + "/tasks/batch", headers=HN, json={"ids": [O_TASK], "action": "complete"})
r2 = requests.post(V + "/tasks/batch", headers=HN, json={"ids": [99999999], "action": "complete"})
check(r1.status_code == r2.status_code and err(r1).get("circle") == err(r2).get("circle") and err(r1).get("circle") != "public",
      f"G9: a batch with somebody else's client report answers like one with no task ({r1.status_code} {err(r1).get('circle')} / {r2.status_code} {err(r2).get('circle')})")

# a new page in a folder of a space with a live share (the public link of Docs/Guide above)
r = F.post(B + f"/api/files/nodes/{DOCS}/shares", json={"agent_id": FN, "role": "edit"})
assert r.status_code == 201, r.text
check(mark(ask(HN, step("POST", "/wiki/pages", {"folder_id": DOCS, "title": "New page", "body": "x"}))) == "public",
      "a new page in a folder of a space with a public link: the card says 'public'")
assert F.delete(B + f"/api/files/shares/{r.json()['id']}").ok

# a chat room without a project: its members are the readers
r = F.post(B + "/api/team/channels", json={"name": "Side room", "members": [OID, FD]})
check(r.status_code == 201, f"setup: a channel with otto and the agent {r.status_code} {r.text[:200]}")
ROOM = r.json().get("id")
free(requests.post(V + f"/team/rooms/{ROOM}/messages", headers=HD, json={"body": "hello"}), "a room with the people of its one project")
project("Reach private", FD)
card(requests.post(V + f"/team/rooms/{ROOM}/messages", headers=HD, json={"body": "from the private project"}), "wider",
     "a chat room one more person reads than the agent's private project")

# ================================================================== review G5: an approved bridge, for the circles of then
XID, _X = freelancer(B, A, "xaver")
ZID, _Z = freelancer(B, A, "zora")
WID, _W = freelancer(B, A, "wilma")
FBR, HBR = agent("bridgebot")
ctl(FBR, {"level": "routine"})
BA = project("Bridge A", FBR, shared=True)
BB = F.post(B + "/api/lists", json={"name": "Bridge B"}).json()["id"]
kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?)", (BB, XID, ts()))
r = F.put(B + f"/api/lists/{BB}/members", json={"user_id": FBR, "role": "edit"})
check(r.status_code == 409 and r.json().get("code") == "agent_bridge", f"setup: two circles that are not nested ask ({r.status_code})")
r = F.put(B + f"/api/lists/{BB}/members", json={"user_id": FBR, "role": "edit", "bridge_ok": True})
assert r.ok, r.text
row = kt.dbx("SELECT list_a, circle_a, circle_b FROM agent_bridges WHERE agent_id=?", (FBR,))
want = {BA: ",".join(str(x) for x in sorted((FID, OID))), BB: ",".join(str(x) for x in sorted((FID, XID)))}
check(len(row) == 1 and {row[0][1], row[0][2]} == set(want.values()), f"G5: the approval keeps the two circles it was given for {row}")
T_BA, T_BB = task(BA, "A"), task(BB, "B")
free(comment(HBR, T_BB, "from A"), "an approved bridge: A -> B")
free(comment(HBR, T_BA, "from B"), "an approved bridge: B -> A")
kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?)", (BB, ZID, ts()))
card(comment(HBR, T_BB, "zora was never approved"), "wider", "G5: one more person in B since the approval: A -> B")
r = F.put(B + f"/api/lists/{BB}/members", json={"user_id": WID, "role": "edit"})
check(r.status_code == 409 and r.json().get("code") == "agent_bridge", f"G5: adding a person to an approved pair asks again ({r.status_code} {r.text[:160]})")
r = F.put(B + f"/api/lists/{BB}/members", json={"user_id": WID, "role": "edit", "bridge_ok": True})
check(r.ok, f"... with the approval it goes {r.status_code} {r.text[:160]}")
free(comment(HBR, T_BB, "approved again"), "G5: approved for the circle of now: free again")

# ================================================================== review G12 / G13: a team agent's own channel, who says Yes
ALICE = kt.me_id(A)
assert A.put(B + f"/api/lists/{L_ALL}/members", json={"user_id": BOB, "role": "admin"}).ok
BS = login(B, "bob", kt.PASSWORD)
r = requests.post(V + f"/agent/chats/{BOB}", headers=HT, json={"body": "words from alice's own project"})
e = card(r, "wider", "G12: a team agent's message to a person who does not read all it reads")
check(e.get("step") == "meta" and "does not read every place" in (e.get("message") or ""), f"... the answer says why {e.get('step')} {e.get('message')}")
check(not kt.dbx("SELECT 1 FROM agent_chat WHERE agent_id=? AND user_id=?", (TA, BOB)), "... nothing was written")
kt.dbx("DELETE FROM agent_chat WHERE agent_id=? AND user_id=?", (TA, BOB))
r = requests.post(V + f"/agent/chats/{ALICE}", headers=HT, json={"body": "to alice"})
check(r.status_code == 201, f"G12: to a person who reads everything: free ({r.status_code} {r.text[:200]})")
r = requests.post(V + f"/agent/chats/{ALICE}", headers=HT, json={"approval": {"title": "Tell Bob", "what": "x", "step": {
    "method": "POST", "path": f"/api/v1/agent/chats/{BOB}", "body": {"body": "words from alice's own project"}}}})
assert r.status_code == 201, r.text
M_BOB = r.json()["id"]
check(mark(M_BOB) == "wider", f"G12: the card for that message is marked 'wider' ({mark(M_BOB)})")
assert A.post(B + f"/api/agents/{TA}/chat/{M_BOB}/choice", json=apv_body(A, B, f"chat:{M_BOB}", "yes")).ok
r = run(HT, M_BOB)
check(r.status_code == 201 and kt.dbx("SELECT 1 FROM agent_chat WHERE agent_id=? AND user_id=? AND sender='agent'", (TA, BOB)),
      f"G12: after the Yes of a person who reads everything the message goes out ({r.status_code} {r.text[:200]})")
e = card(comment(HT, K_ALL, "again from alice's own project"), "wider", "setup: a write into the open project")
r = requests.post(V + f"/agent/chats/{ALICE}", headers=HT, json={"approval": {"title": "Comment", "what": "x", "step": {
    "method": "POST", "path": f"/api/v1/tasks/{K_ALL}/comments", "body": {"body": "again from alice's own project"}}}})
assert r.status_code == 201, r.text
M_13 = r.json()["id"]
kt.dbx("UPDATE agent_chat SET choice=? WHERE id=?", (json.dumps({"ids": ["yes"], "at": ts(), "user_id": BOB}), M_13))  # as if bob had the card
r = run(HT, M_13)
check(r.status_code == 409 and err(r).get("reason") == "approver_rights",
      f"G13: the Yes of a person who writes in the target but does not read the source does not count ({r.status_code} {r.text[:200]})")
kt.dbx("UPDATE agent_chat SET choice=? WHERE id=?", (json.dumps({"ids": ["yes"], "at": ts(), "user_id": ALICE}), M_13))
check(run(HT, M_13).status_code == 201, "G13: the Yes of a person who reads everything runs it")
r = requests.put(V + "/agent/status", headers=HT, json={"status": "working", "text": "reading alice's private notes"})
assert r.ok, r.text


def status_seen(s):
    return next((x for x in s.get(B + "/api/agents").json().get("agents", []) if x["id"] == TA), {})


check(status_seen(BS).get("status") == "working" and status_seen(BS).get("status_text") == "",
      f"G12: bob sees that the team agent works, not its status text {status_seen(BS).get('status')} {status_seen(BS).get('status_text')!r}")
check(status_seen(A).get("status_text") == "reading alice's private notes", f"... alice reads it {status_seen(A).get('status_text')!r}")

# ================================================================== the progress line
ctl(FA, {"level": "routine"})
r = requests.post(V + f"/tasks/{T_SH}/working", headers=H, json={"text": "copying the private notes", "title": "Private title", "name": "Clara"})
j = r.json() if r.ok else {}
check(r.status_code == 201 and (j.get("working") or {}).get("text") == "" and j.get("text_shown") is False and j.get("note"),
      f"a wider project: the mark is set, the words are not shown, the answer says so ({r.status_code} {r.text[:260]})")
JOB = (j.get("job") or {}).get("id")
r = requests.patch(V + f"/agent/jobs/{JOB}", headers=H, json={"append_log": "a second private line"})
check(r.ok, f"setup: a line through the job's log {r.status_code} {r.text[:160]}")
w = requests.get(V + f"/tasks/{T_SH}/working", headers=H).json().get("working") or {}
check(w.get("text") == "" and w.get("agent_id") == FA, f"... also a line written through the job's log is not shown {w}")
seen = next((t for t in OTTO.get(B + "/api/state").json().get("tasks", []) if t["id"] == T_SH), {})
check((seen.get("working") or {}).get("agent_id") == FA and (seen.get("working") or {}).get("text") == "",
      f"the other person sees that the agent works, not its words {seen.get('working')}")
# review G4: the job list -- title, name and log are the agent's words too
for q in ({"agent_id": FA}, {"id": JOB}):
    jb = next((x for x in OTTO.get(B + "/api/agents/jobs", params=q).json().get("jobs", []) if x["id"] == JOB), None)
    check(jb is not None and jb["title"] == "" and jb["name"] is None and not jb.get("log") and not jb.get("log_last"),
          f"G4: the other person sees the job ({sorted(q)}), not its title, name or log {jb and {k: jb.get(k) for k in ('title', 'name', 'log', 'log_last')}}")
jb = next((x for x in requests.get(V + "/agent/jobs", headers=H).json().get("data", []) if x["id"] == JOB), None)
check(jb is None or jb["title"] == "Private title", f"... the agent itself reads its own job as before {jb and jb.get('title')}")
r = requests.post(V + f"/tasks/{T_PRIV}/working", headers=H, json={"text": "sorting the notes"})
j = r.json() if r.ok else {}
check(r.status_code == 201 and (j.get("working") or {}).get("text") == "sorting the notes" and "text_shown" not in j,
      f"its private project: the progress line as before ({r.status_code} {r.text[:200]})")

# ================================================================== 2.1398.0 (#6863): jobs, proposals, agents without a level
# A team agent's job for a person is a message to that person (title and log reach them: chat start line, progress, News,
# push): a person who does not read every source = a card, nothing stored. A job without a task shows its words only to
# who reads every source. A proposal for the rules / playbook / layout of a project is a write into that project. Each
# red without the fix. (Agents without a level: a task of its own, the decision of #6863.)
n0 = kt.dbx("SELECT count(*) FROM agent_jobs WHERE agent_id=?", (TA,))[0][0]
card(requests.post(V + "/agent/jobs", headers=HT, json={"title": "Alice's private plan", "user_id": BOB, "log": "private words"}),
     "wider", "#6863: a team agent's job for a person who does not read all it reads")
check(kt.dbx("SELECT count(*) FROM agent_jobs WHERE agent_id=?", (TA,))[0][0] == n0, "#6863: ... no job was stored")
r = requests.post(V + "/agent/jobs", headers=HT, json={"title": "For alice", "user_id": ALICE})
check(r.status_code == 201, f"#6863: a job for a person who reads everything: free ({r.status_code} {r.text[:200]})")
JB_BOB = kt.dbx("""INSERT INTO agent_jobs(agent_id,user_id,title,state,log,created_at,updated_at) VALUES(?,?,?,'running','',?,?)
                   RETURNING id""", (TA, BOB, "Bob's job", ts(), ts()))[0][0]
card(requests.patch(V + f"/agent/jobs/{JB_BOB}", headers=HT, json={"append_log": "alice's private line"}), "wider",
     "#6863: a log line of a job for that person")
check(kt.dbx("SELECT log FROM agent_jobs WHERE id=?", (JB_BOB,))[0][0] == "", "#6863: ... the log stayed empty")
check(requests.patch(V + f"/agent/jobs/{JB_BOB}", headers=HT, json={"state": "done"}).ok, "#6863: its state alone is no words: free")
r = requests.post(V + "/agent/jobs", headers=HT, json={"title": "Nobody's secret", "log": "alice's private notes"})
check(r.status_code == 201, f"#6863: a job without a task and a person passes the gate ({r.status_code} {r.text[:200]})")
JB_NONE = r.json().get("id") if r.ok else None
kt.dbx("UPDATE users SET is_admin=TRUE WHERE id=?", (BOB,))  # an admin sees the jobs of agents it reaches (core.job_visible)
try:
    jb = next((x for x in BS.get(B + "/api/agents/jobs", params={"agent_id": TA}).json().get("jobs", []) if x["id"] == JB_NONE), None)
    check(jb is not None and jb["title"] == "" and jb["name"] is None and not jb.get("log") and not jb.get("log_last"),
          f"#6863: bob sees the job without a task, not its title or log {jb and {k: jb.get(k) for k in ('title', 'name', 'log', 'log_last')}}")
    ja = next((x for x in A.get(B + "/api/agents/jobs", params={"agent_id": TA}).json().get("jobs", []) if x["id"] == JB_NONE), None)
    check(ja is not None and ja["title"] == "Nobody's secret", f"#6863: ... alice, who reads everything, reads it {ja and ja.get('title')}")
    # Fable reader job/5498 F4: the same in "Waiting for me" and in the job cards of the chat (jcd_jobs) -- both gave the title
    kt.dbx("UPDATE agent_jobs SET state='waiting' WHERE id=?", (JB_NONE,))
    wi = next((x for x in BS.get(B + "/api/inbox").json().get("items", []) if x["kind"] == "job" and x["id"] == JB_NONE), None)
    check(wi is not None and wi["title"] == "", f"F4: bob's waiting list has the job without its title {wi}")
    wa = next((x for x in A.get(B + "/api/inbox").json().get("items", []) if x["kind"] == "job" and x["id"] == JB_NONE), None)
    check(wa is None or wa["title"] == "Nobody's secret", f"F4: ... alice reads it {wa}")
    out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.agents.jobchat import jcd_jobs
c = connect()
with system_ctx(c):
    print(json.dumps({{k: jcd_jobs(c, {TA}, [{{"job_id": {JB_NONE}}}], u).get(str({JB_NONE})) for k, u in (("bob", {BOB}), ("alice", {ALICE}))}}))
c.close()"""], capture_output=True, text=True)
    try:
        jc = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        jc = {"error": (out.stdout + out.stderr)[-600:]}
    jb_, ja_ = jc.get("bob") or {}, jc.get("alice") or {}
    check(jb_.get("id") == JB_NONE and jb_.get("title") == "" and "secret" not in str(jb_.get("name")),
          f"F4: the chat's job card for bob has no title or name {jc}")
    check(ja_.get("title") == "Nobody's secret", f"F4: ... alice's has them {jc}")
finally:
    kt.dbx("UPDATE users SET is_admin=FALSE WHERE id=?", (BOB,))
for path, body in ((f"/lists/{L_ALL}/rules/proposals", {"name": "From alice's project", "trigger": {}, "action": {}}),
                   (f"/lists/{L_ALL}/playbook/proposals", {"text": "alice's private notes"}),
                   ("/layouts/proposals", {"view": f"list:{L_ALL}", "name": "x", "layout": {}, "user_id": ALICE})):
    card(requests.post(V + path, headers=HT, json=body), "wider", f"#6863: a proposal into the project everyone reads ({path})")
# Fable reader job/5498 F1: gate and route read the person of a layout proposal alike (as_int) -- 7.0, true, "+7" were no
# person for the gate (free) and person 7 / 1 for the route (int()): the proposal reached bob without a card
LY_OK = {"order": ["today", "news"]}
card(requests.post(V + "/layouts/proposals", headers=HT, json={"view": "dashboard", "name": "x", "layout": LY_OK, "user_id": BOB}),
     "wider", "F1 setup: a layout proposal to bob")
nl0 = kt.dbx("SELECT count(*) FROM agent_jobs WHERE agent_id=? AND user_id=?", (TA, BOB))[0][0]
for bad in (float(BOB), f"+{BOB}", True):
    r = requests.post(V + "/layouts/proposals", headers=HT, json={"view": "dashboard", "name": "x", "layout": LY_OK, "user_id": bad})
    check(r.status_code in (400, 409), f"F1: user_id {bad!r} is no way around the circle ({r.status_code} {r.text[:160]})")
check(kt.dbx("SELECT count(*) FROM agent_jobs WHERE agent_id=? AND user_id=?", (TA, BOB))[0][0] == nl0, "F1: ... no proposal for bob was stored")
for bad in (float(BOB), f"+{BOB}", True, f"{BOB}_0"):
    card(requests.post(V + "/agent/jobs", headers=HT, json={"title": "x", "user_id": bad}), "wider",
         f"F1 (decision 18.11.2026): a user_id that is there but no id fails closed ({bad!r})")
check(kt.dbx("SELECT count(*) FROM agent_jobs WHERE agent_id=? AND user_id=?", (TA, BOB))[0][0] == nl0, "F1: ... no job for bob was stored")
r = requests.post(V + "/layouts/proposals", headers=HT, json={"view": "list:\u00b2", "name": "x", "layout": {}, "user_id": ALICE})
check(r.status_code < 500, f"F1: a view key 'list:\u00b2' is a 4xx, not a 500 ({r.status_code} {r.text[:160]})")
# Fable reader job/5498 F2: a progress step (chat or a job for bob) and a /working line into a job for bob are words to bob too
ns0 = kt.dbx("SELECT count(*) FROM agent_steps WHERE agent_id=? AND user_id=?", (TA, BOB))[0][0]
card(requests.post(V + "/agent/progress", headers=HT, json={"text": "alice's private notes", "job_id": JB_BOB}), "wider",
     "F2: a progress step of a job for bob")
card(requests.post(V + "/agent/progress", headers=HT, json={"text": "alice's private notes", "chat_user_id": BOB}), "wider",
     "F2: a progress step of a chat with bob")
JB_BOBT = kt.dbx("""INSERT INTO agent_jobs(agent_id,task_id,user_id,title,state,log,created_at,updated_at) VALUES(?,?,?,?,'running','',?,?)
                    RETURNING id""", (TA, K_ALL, BOB, "Bob's task job", ts(), ts()))[0][0]
for meth in ("POST", "PATCH"):
    card(requests.request(meth, V + f"/tasks/{K_ALL}/working", headers=HT, json={"text": "alice's private notes", "job_id": JB_BOBT}),
         "wider", f"F2: {meth} /tasks/{{id}}/working into a job for bob")
card(requests.patch(V + f"/tasks/{K_ALL}/working", headers=HT, json={"text": "alice's private notes"}), "wider",
     "F2: PATCH /tasks/{id}/working without job_id picks the newest job -- the one for bob")
check(kt.dbx("SELECT count(*) FROM agent_steps WHERE agent_id=? AND user_id=?", (TA, BOB))[0][0] == ns0
      and kt.dbx("SELECT log FROM agent_jobs WHERE id=?", (JB_BOBT,))[0][0] == "", "F2: ... no step and no log line reached bob")
check(requests.patch(V + f"/tasks/{K_ALL}/working", headers=HT, json={"job_id": JB_BOBT}).ok, "F2: 'still working' without words: free")
kt.dbx("UPDATE agent_jobs SET state='done' WHERE id=?", (JB_BOBT,))
# Fable reader job/5481 F7: a job with a task but no person, state waiting -- job_notify derives the recipient from the task
# (assignee) and sent the title as News "approval" and push without the gate (no person): the words reach bob, who does not
# read all the team agent reads. Now News and push carry no title where job_dict hides it (job_words_muted).
K_BOB = A.post(B + "/api/tasks", json={"title": "Bob's in the open project", "list_id": L_ALL}).json()["id"]
K_ALI = A.post(B + "/api/tasks", json={"title": "Alice's own", "list_id": L_OWN}).json()["id"]
kt.dbx("UPDATE tasks SET assignee_id=? WHERE id=?", (BOB, K_BOB))
kt.dbx("UPDATE tasks SET assignee_id=? WHERE id=?", (ALICE, K_ALI))


def appr_title(uid, jid):
    r = kt.dbx("SELECT data->>'title' FROM notifications WHERE user_id=? AND kind='approval' AND data->>'job' = ?", (uid, str(jid)))
    return r[0][0] if r else None


r = requests.post(V + "/agent/jobs", headers=HT, json={"title": "Alice's private plan", "task_id": K_BOB, "state": "waiting"})
check(r.status_code == 201, f"F7 setup: a waiting job on bob's task without a person ({r.status_code} {r.text[:200]})")
JW = r.json().get("id") if r.ok else None
check(appr_title(BOB, JW) == "", f"F7: bob's News 'waiting for approval' has no title (POST) {appr_title(BOB, JW)!r}")
r = requests.post(V + "/agent/jobs", headers=HT, json={"title": "Running first", "task_id": K_BOB})
JW2 = r.json().get("id") if r.ok else None
r = requests.patch(V + f"/agent/jobs/{JW2}", headers=HT, json={"state": "waiting", "title": "Alice's second plan"})
check(r.ok and appr_title(BOB, JW2) == "", f"F7: ... nor through PATCH state waiting ({r.status_code} {appr_title(BOB, JW2)!r})")
r = requests.post(V + "/agent/jobs", headers=HT, json={"title": "Alice's own plan", "task_id": K_ALI, "state": "waiting"})
JW3 = r.json().get("id") if r.ok else None
check(appr_title(ALICE, JW3) == "Alice's own plan", f"F7: a task in the project only alice reads: her News keeps the title {appr_title(ALICE, JW3)!r}")
# #7162 (Fable reader job/5481 F14): a job WITH a task in the open project -- job_dict hides its title from bob (WK_MUTE), but
# "Waiting for me", the chat's job cards (jcd_jobs) and the job names (jn9_job_names) asked job_words_hidden (jobs without a
# task only) and gave it; now all three ask job_words_muted like job_dict and job_notify
kt.dbx("UPDATE users SET is_admin=TRUE WHERE id=?", (BOB,))  # bob sees the agent's jobs (core.job_visible), as in F4
try:
    wi = next((x for x in BS.get(B + "/api/inbox").json().get("items", []) if x["kind"] == "job" and x["id"] == JW), None)
    check(wi is None or wi["title"] == "", f"F14: bob's waiting list has the task's job without its title {wi}")
    out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.agents.jobchat import jcd_jobs
from kalmido.agents.core import jn9_job_names
c = connect()
with system_ctx(c):
    print(json.dumps({{"card": {{k: jcd_jobs(c, {TA}, [{{"job_id": {JW}}}], u).get(str({JW})) for k, u in (("bob", {BOB}), ("alice", {ALICE}))}},
                      "name": {{k: jn9_job_names(c, [{JW}], u).get({JW}) for k, u in (("bob", {BOB}), ("alice", {ALICE}))}}}}))
c.close()"""], capture_output=True, text=True)
    try:
        jc = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        jc = {"error": (out.stdout + out.stderr)[-600:]}
    cb, ca = (jc.get("card") or {}).get("bob") or {}, (jc.get("card") or {}).get("alice") or {}
    check(cb.get("id") == JW and cb.get("title") == "" and "plan" not in str(cb.get("name")),
          f"F14: the chat's job card of the task's job has no title or name for bob {jc}")
    check(ca.get("title") == "Alice's private plan", f"F14: ... alice's has them {jc}")
    nb = (jc.get("name") or {}).get("bob")
    check("plan" not in json.dumps(nb), f"F14: the job's name for bob carries no title {jc.get('name')}")
finally:
    kt.dbx("UPDATE users SET is_admin=FALSE WHERE id=?", (BOB,))
for x in (JW, JW2, JW3):
    kt.dbx("UPDATE agent_jobs SET state='done' WHERE id=?", (x,))
for path, body in ((f"/lists/{L_OWN}/rules/proposals", {"name": "x"}), (f"/lists/{L_OWN}/playbook/proposals", {"text": "x"})):
    r = requests.post(V + path, headers=HT, json=body)
    check(not (r.status_code == 409 and err(r).get("code") == "approval_required"),
          f"#6863: a proposal into the project only alice reads: no card from the rule ({path} {r.status_code} {r.text[:160]})")

# ================================================================== 2.1345.0 (#6736, Fable reader #4945 N1): approvals from before 2.1284
# A bridge approved before the circles were kept (circle_a / circle_b NULL) gets at the start the circle of the moment of
# its approval as far as list_members.added_at proves it -- not the one of the start: otto, who came to the project after
# the approval, was never approved, so the bridge no longer holds and asks anew; otto there before: it holds.
LG_A, LG_B = project("Legacy own"), project("Legacy shared")
LG_C = project("Legacy shared early")
LG_D, LG_E = project("Legacy shared moved"), project("Legacy own moved")
# review F1 (decision 17.11.2026): the owner of today counts only without a change of ownership since the approval (list_activity)
kt.dbx("INSERT INTO list_activity(list_id,user_id,kind,data,created_at) VALUES(?,?,'owner','{}',?)", (LG_E, FID, ts(-1)))
for name, la, lb, added in (("legacylate", LG_A, LG_B, ts(-1)), ("legacyearly", LG_A, LG_C, ts(-72)), ("legacymoved", LG_E, LG_D, ts(-72))):
    aid, _ = agent(name)
    kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?)", (lb, OID, added))
    x, y = min(la, lb), max(la, lb)
    kt.dbx("INSERT INTO agent_bridges(agent_id,list_a,list_b,by_id,at) VALUES(?,?,?,?,?)", (aid, x, y, FID, ts(-48)))
    out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.agents.safety import bridge_circles_start
from kalmido.agents.circle import bridge_holds, list_circles
c = connect()
bridge_circles_start(c)
c.commit()
with system_ctx(c):
    r = c.execute("SELECT * FROM agent_bridges WHERE agent_id=?", ({aid},)).fetchone()
    print(json.dumps({{"a": r["circle_a"], "b": r["circle_b"], "holds": bridge_holds(c, r, list_circles(c, [{x}, {y}]))}}))
c.close()"""], capture_output=True, text=True)
    try:
        j = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        j = {"error": (out.stdout + out.stderr)[-600:]}
    want_b = f"{min(FID, OID)},{max(FID, OID)}" if name != "legacylate" else str(FID)
    want_a = "" if name == "legacymoved" else str(FID)
    got_b, got_a = (j.get("b"), j.get("a")) if lb == y else (j.get("a"), j.get("b"))
    check(got_b == want_b and got_a == want_a and j.get("holds") is (name == "legacyearly"),
          f"#6736 a bridge from before 2.1284 ({name}: otto {'added after' if name == 'legacylate' else 'there before'} the approval"
          f"{', the owner of the other project changed since' if name == 'legacymoved' else ''}): circles as proved then "
          f"({want_a} / {want_b}), holds {name == 'legacyearly'} {j}")

# Fable reader #5194 F1: lists.list_keep (a deleted person's project kept for its custodian) changes the owner and writes the
# history row "owner" -- the custodian of today is then not proved for an approval from before
LG_F = project("Legacy kept")
FX, FY = min(LG_A, LG_F), max(LG_A, LG_F)  # aid: the agent of the last case above (at most 12 personal agents)
kt.dbx("INSERT INTO agent_bridges(agent_id,list_a,list_b,by_id,at) VALUES(?,?,?,?,?)", (aid, FX, FY, FID, ts(-48)))
out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.lists.lists import list_keep
from kalmido.agents.safety import bridge_circles_start
c = connect()
with system_ctx(c):
    c.execute("UPDATE agent_bridges SET circle_a=NULL, circle_b=NULL WHERE agent_id=? AND list_a=? AND list_b=?", ({aid}, {FX}, {FY}))
    list_keep(c, {LG_F}, {FID}, None, owner={OID})
    c.commit()
    bridge_circles_start(c)
    c.commit()
    r = c.execute("SELECT * FROM agent_bridges WHERE agent_id=? AND list_a=? AND list_b=?", ({aid}, {FX}, {FY})).fetchone()
    n = c.execute("SELECT COUNT(*) FROM list_activity WHERE list_id=? AND kind='owner'", ({LG_F},)).fetchone()[0]
    print(json.dumps({{"a": r["circle_a"], "b": r["circle_b"], "rows": n}}))
c.close()"""], capture_output=True, text=True)
try:
    j = json.loads(out.stdout.strip().splitlines()[-1])
except (ValueError, IndexError):
    j = {"error": (out.stdout + out.stderr)[-600:]}
got_f = j.get("b") if LG_F > LG_A else j.get("a")
check(j.get("rows") == 1 and got_f == "", f"#6736 F1: a project kept for its custodian has the history row 'owner', the custodian is not proved: {j}")

# Fable reader #5196 F2 (decision 17.11.2026): an approval older than the log period (ret_days("logs"), list_activity is kept
# that long) proves no owner: empty circle, the bridge asks once anew
LG_G, LG_H = project("Legacy very old own"), project("Legacy very old shared")
kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?)", (LG_H, OID, ts(-24 * 900)))
GX, GY = min(LG_G, LG_H), max(LG_G, LG_H)
kt.dbx("INSERT INTO agent_bridges(agent_id,list_a,list_b,by_id,at) VALUES(?,?,?,?,?)", (aid, GX, GY, FID, ts(-24 * 500)))
out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.agents.safety import bridge_circles_start
c = connect()
with system_ctx(c):
    bridge_circles_start(c)
    c.commit()
    r = c.execute("SELECT * FROM agent_bridges WHERE agent_id=? AND list_a=? AND list_b=?", ({aid}, {GX}, {GY})).fetchone()
    print(json.dumps({{"a": r["circle_a"], "b": r["circle_b"]}}))
c.close()"""], capture_output=True, text=True)
try:
    j = json.loads(out.stdout.strip().splitlines()[-1])
except (ValueError, IndexError):
    j = {"error": (out.stdout + out.stderr)[-600:]}
check(j.get("a") == "" and j.get("b") == "", f"#6736 F2: an approval older than the log period proves nobody (asks anew): {j}")

# 2.1367.0 (#6971, Fable reader #5199 F1): 2.1284 to 2.1344 filled the circles of such approvals with the circle of the day of
# the update (otto came between the approval and that start: wrongly approved). Once, before bridge_circles_start, the rows
# approved before the first start of 2.1284 (the step that added circle_a, kalmido_migrations) go back to NULL and get the circle
# of the moment of the approval; an approval made after that start keeps its circle.
LG_I, LG_J, LG_K = project("Legacy filled own"), project("Legacy filled shared"), project("Fresh approval shared")
# otto came to both after their approval (stored wide here on purpose: the fresh row must stay as stored, not be recalculated)
for lid in (LG_J, LG_K):
    kt.dbx("INSERT INTO list_members(list_id,user_id,role,added_at) VALUES(?,?,'edit',?)", (lid, OID, ts(-1)))
wide = f"{min(FID, OID)},{max(FID, OID)}"
IX, IY, KX, KY = min(LG_I, LG_J), max(LG_I, LG_J), min(LG_I, LG_K), max(LG_I, LG_K)
kt.dbx("INSERT INTO agent_bridges(agent_id,list_a,list_b,by_id,at,circle_a,circle_b) VALUES(?,?,?,?,?,?,?)",
       (aid, IX, IY, FID, ts(-48), wide if IX == LG_J else str(FID), wide if IY == LG_J else str(FID)))
kt.dbx("INSERT INTO agent_bridges(agent_id,list_a,list_b,by_id,at,circle_a,circle_b) VALUES(?,?,?,?,?,?,?)",
       (aid, KX, KY, FID, ts(-2), wide if KX == LG_K else str(FID), wide if KY == LG_K else str(FID)))
mig0 = kt.dbx("SELECT applied_at, note FROM kalmido_migrations WHERE id='agent_bridges.circle_a'")
kt.dbx("UPDATE kalmido_migrations SET applied_at=?, note='applied' WHERE id='agent_bridges.circle_a'", (ts(-24),))
out = subprocess.run(["docker", "exec", kt.CT, "python", "-c", f"""import json, app
from kalmido.core.db import connect
from kalmido.core.pg import system_ctx
from kalmido.agents.safety import bridge_circles_reset, bridge_circles_start
c = connect()
n = bridge_circles_reset(c)
bridge_circles_start(c)
c.commit()
with system_ctx(c):
    out = {{"n": n}}
    for k, (x, y) in (("old", ({IX}, {IY})), ("fresh", ({KX}, {KY}))):
        r = c.execute("SELECT * FROM agent_bridges WHERE agent_id=? AND list_a=? AND list_b=?", ({aid}, x, y)).fetchone()
        out[k] = [r["circle_a"], r["circle_b"]]
    print(json.dumps(out))
c.close()"""], capture_output=True, text=True)
if mig0:
    kt.dbx("UPDATE kalmido_migrations SET applied_at=?, note=? WHERE id='agent_bridges.circle_a'", tuple(mig0[0]))
try:
    j = json.loads(out.stdout.strip().splitlines()[-1])
except (ValueError, IndexError):
    j = {"error": (out.stdout + out.stderr)[-600:]}
check(sorted(j.get("old") or []) == [str(FID), str(FID)] and sorted(j.get("fresh") or []) == sorted([wide, str(FID)]) and j.get("n", 0) >= 1,
      f"#6971 F1: a circle 2.1284 filled with the day of the update is reset and narrowed (otto came after the approval); "
      f"an approval after that start keeps its circle: {j}")

sys.exit(done("p6453_circle"))
