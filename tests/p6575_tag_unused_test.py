#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1284.0 (#6575): an agent deletes a project tag nothing carries without a one-way card.
DELETE /api/v1/lists/{id}/tags/{tag_id} is a one-way step for an agent (every DELETE) -- except for a tag of exactly this
project (scope list) that no task carries, open, done or in the trash: nothing is lost, the gate reads it as routine.
 - routine / free: an unused project tag -> 204 without a card, a line in the history (step routine)
 - a tag a task carries (open, done, in the trash, each alone) -> 409 approval_required, step one_way, the tag stays
 - taken off its last task -> 204
 - approve_all: the unused tag still needs a card (step routine, not one_way); after the Yes the card's run deletes it
 - a tag of another project under this project's path -> 409 one_way as before; a project the agent does not see -> 404
 - a label of the organisation -> 409 one_way, used or not
 - a person without an organisation with a personal agent, and a team agent in a project of an organisation
   (freelancer-matrix: agents)
 - review G7: a tag no object carries but a rule (trigger, action, chain, condition) or a client link's filter names -> one-way
 - review G8: the approval card for an unused tag is not marked one-way, the one for a used tag is
usage: p6575_tag_unused_test.py <datadir>"""
import os
import sys

import requests

import kt
from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

V = B + "/api/v1"
os.environ["KALMIDO_AGENT_CONTROL_NEW"] = "approve_all"  # the real default (tests/start.sh starts other suites with legacy)
fresh(prefix="P6575")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FID, F = freelancer(B, A)
SCOPES = ["read", "tasks:write", "comments", "structure", "delete"]


def err(r):
    try:
        return r.json()["error"]
    except (ValueError, KeyError, TypeError):
        return {}


def ctl(s, aid, patch):
    r = s.patch(B + f"/api/agents/{aid}/control", json=patch)
    assert r.ok, r.text


def tag(s, lid, name):
    r = s.post(B + f"/api/lists/{lid}/tags", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def task(s, lid, title, tags):
    r = s.post(B + "/api/tasks", json={"title": title, "list_id": lid})
    assert r.ok, r.text
    assert s.patch(B + f"/api/tasks/{r.json()['id']}", json={"ltags": tags}).ok
    return r.json()["id"]


def tags_of(h, lid):
    r = requests.get(V + f"/lists/{lid}/tags", headers=h)
    assert r.ok, r.text
    return {x["id"]: x for x in r.json()["data"]}


def links(tid):
    return kt.dbx("SELECT COUNT(*) FROM obj_tag_links WHERE tag_id=?", (tid,))[0][0]


def one_way(who, h, lid, tid, why):
    r = requests.delete(V + f"/lists/{lid}/tags/{tid}", headers=h)
    e = err(r)
    check(r.status_code == 409 and e.get("code") == "approval_required" and e.get("step") == "one_way",
          f"{who}: {why} -> 409 approval_required one_way ({r.status_code} {r.text[:160]})")
    check(tid in tags_of(h, lid), f"{who}: {why} -> the tag is still there")


# ================================================================== a person without an organisation, her personal agent
r = F.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": SCOPES})
assert r.status_code in (200, 201), r.text
FA, FH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
FL = F.post(B + "/api/lists", json={"name": "Frida work"}).json()["id"]
FL2 = F.post(B + "/api/lists", json={"name": "Frida second"}).json()["id"]
FX = F.post(B + "/api/lists", json={"name": "Frida alone"}).json()["id"]
for x in (FL, FL2):
    assert F.put(B + f"/api/lists/{x}/members", json={"user_id": FA, "role": "edit"}).ok
ctl(F, FA, {"level": "routine"})
who = "freelancer"

T_FREE = tag(F, FL, "after 4711")
n0 = kt.dbx("SELECT COUNT(*) FROM agent_decisions WHERE agent_id=?", (FA,))[0][0]
r = requests.delete(V + f"/lists/{FL}/tags/{T_FREE}", headers=FH)
check(r.status_code == 204, f"{who}: an unused project tag on routine -> 204 without a card ({r.status_code} {r.text[:160]})")
check(T_FREE not in tags_of(FH, FL) and not kt.dbx("SELECT 1 FROM obj_tags WHERE id=?", (T_FREE,)), f"{who}: the tag is gone")
d = kt.dbx("SELECT step, level, via, method FROM agent_decisions WHERE agent_id=? ORDER BY id DESC LIMIT 1", (FA,))
check(kt.dbx("SELECT COUNT(*) FROM agent_decisions WHERE agent_id=?", (FA,))[0][0] == n0 + 1 and d
      and tuple(d[0]) == ("routine", "routine", "self", "DELETE"), f"{who}: one line in the history, step routine {d and tuple(d[0])}")
check(tag(F, FL, "after 4711") != T_FREE, f"{who}: the tag comes back by its name")

# a tag a task carries: open, done, in the trash -- each alone
T_OPEN, T_DONE, T_TRASH = tag(F, FL, "open one"), tag(F, FL, "done one"), tag(F, FL, "trash one")
K_OPEN = task(F, FL, "Open", ["open one"])
K_DONE = task(F, FL, "Done", ["done one"])
K_TRASH = task(F, FL, "Trashed", ["trash one"])
assert F.post(B + f"/api/tasks/{K_DONE}/complete").ok
assert F.delete(B + f"/api/tasks/{K_TRASH}").ok
check(links(T_OPEN) == 1 and links(T_DONE) == 1 and links(T_TRASH) == 1, "setup: each tag sits on exactly one task")
check(kt.dbx("SELECT 1 FROM tasks WHERE id=?", (K_TRASH,)) and requests.get(V + f"/tasks/{K_TRASH}", headers=FH).status_code == 404,
      "setup: the trashed task is kept and no longer listed")
one_way(who, FH, FL, T_OPEN, "a tag on an open task")
one_way(who, FH, FL, T_DONE, "a tag on a done task")
one_way(who, FH, FL, T_TRASH, "a tag on a task in the trash")
check(links(T_OPEN) == 1 and links(T_DONE) == 1 and links(T_TRASH) == 1, f"{who}: no link was taken along")

# taken off its last task: unused again
assert F.patch(B + f"/api/tasks/{K_OPEN}", json={"ltags": []}).ok
check(requests.delete(V + f"/lists/{FL}/tags/{T_OPEN}", headers=FH).status_code == 204, f"{who}: taken off its last task -> 204")

# free: the same line
ctl(F, FA, {"level": "free"})
T2 = tag(F, FL, "free unused")
check(requests.delete(V + f"/lists/{FL}/tags/{T2}", headers=FH).status_code == 204, f"{who}: free, unused -> 204")
one_way(who, FH, FL, T_DONE, "free, a tag on a done task")

# the tag must belong to the project in the path; a project it does not see answers as before
T_OTHER = tag(F, FL2, "of the second")
r = requests.delete(V + f"/lists/{FL}/tags/{T_OTHER}", headers=FH)
check(r.status_code == 409 and err(r).get("step") == "one_way", f"{who}: a tag of another project under this path -> one_way as before {r.status_code}")
check(T_OTHER in tags_of(FH, FL2), f"{who}: ... and it stays")
T_HID = tag(F, FX, "hidden")
r = requests.delete(V + f"/lists/{FX}/tags/{T_HID}", headers=FH)
check(r.status_code == 404, f"{who}: a project the agent does not see -> 404 as before ({r.status_code})")
r = requests.delete(V + f"/lists/{FL}/tags/{T_HID}", headers=FH)
check(r.status_code == 409 and err(r).get("step") == "one_way" and kt.dbx("SELECT 1 FROM obj_tags WHERE id=?", (T_HID,)),
      f"{who}: a hidden project's tag under its own project's path -> one_way, nothing deleted ({r.status_code})")
check(requests.delete(V + f"/lists/{FL}/tags/0", headers=FH).status_code in (400, 409), f"{who}: no id -> refused")

# 2.1284.0 (#6575, review G7): a tag nothing carries, but a rule or a client link names it by its id -- "used": one-way
T_TRIG, T_ACT, T_CHAIN, T_COND, T_LINK = (tag(F, FL, n) for n in ("rule trigger", "rule action", "rule chain", "rule condition", "client filter"))
for body, why in (({"trigger": {"kind": "ltag", "tag_id": T_TRIG}, "action": {"kind": "priority", "priority": "high"}}, "trigger"),
                  ({"trigger": {"kind": "done"}, "action": {"kind": "tag", "tag_id": T_ACT}}, "action"),
                  ({"trigger": {"kind": "done"}, "actions": [{"kind": "priority", "priority": "high"}, {"kind": "tag", "tag_id": T_CHAIN}]}, "chain"),
                  ({"trigger": {"kind": "done"}, "action": {"kind": "priority", "priority": "low"}, "conditions": {"tag_id": T_COND}}, "condition")):
    r = F.post(B + f"/api/lists/{FL}/rules", json={"name": "Rule " + why, **body})
    assert r.status_code in (200, 201), (why, r.text)
kt.dbx("INSERT INTO public_links(list_id,token_hash,token,mode,created_at,cv_show) VALUES(?,?,?,'view',CURRENT_TIMESTAMP,?)",
       (FL2, "t" * 64, "sealed", '{"tag": %d}' % T_OTHER))
check(all(links(x) == 0 for x in (T_TRIG, T_ACT, T_CHAIN, T_COND, T_OTHER)), "setup: no task carries the tags the rules and the client link name")
one_way(who, FH, FL, T_TRIG, "a tag a rule's trigger names")
one_way(who, FH, FL, T_ACT, "a tag a rule's action sets (the review's case: on done set the tag)")
one_way(who, FH, FL, T_CHAIN, "a tag an action of a rule's chain sets")
one_way(who, FH, FL, T_COND, "a tag a rule's condition names")
one_way(who, FH, FL2, T_OTHER, "a tag a client link filters by")
check(len(F.get(B + f"/api/lists/{FL}/rules").json().get("rules", [])) == 4, f"{who}: the rules stand as they were")
kt.dbx("DELETE FROM public_links WHERE list_id=?", (FL2,))
check(requests.delete(V + f"/lists/{FL2}/tags/{T_OTHER}", headers=FH).status_code == 204, f"{who}: the client link gone -> unused again, 204")

# approve_all: "routine" is not "always free" -- a card, but none marked one-way; after the Yes the card's run deletes the tag
ctl(F, FA, {"level": "approve_all"})
T3 = tag(F, FL, "needs a card")
r = requests.delete(V + f"/lists/{FL}/tags/{T3}", headers=FH)
e = err(r)
check(r.status_code == 409 and e.get("code") == "approval_required" and e.get("step") == "routine" and e.get("level") == "approve_all",
      f"{who}: approve_all, unused -> a card, step routine ({r.status_code} {r.text[:160]})")
ap = e.get("approval") or {}
r = requests.post(V + f"/agent/chats/{FID}", headers=FH, json={"approval": {
    "title": "Delete the tag", "what": "Delete the unused tag", "step": {"method": ap.get("method"), "path": ap.get("path")}}})
check(r.status_code == 201, f"{who}: the approval card {r.status_code} {r.text[:160]}")
MID = r.json()["id"]
# 2.1284.0 (#6575, review G8): the card of an unused tag is an ordinary one (the gate reads the step as routine), a used one's is one-way
ow = lambda mid: (kt.dbx("SELECT choices->'approval'->>'one_way' FROM agent_chat WHERE id=?", (mid,)) or [[None]])[0][0]  # noqa: E731
check(ow(MID) is None, f"{who}: the card for an unused tag is not marked one-way ({ow(MID)})")
r2 = requests.post(V + f"/agent/chats/{FID}", headers=FH, json={"approval": {
    "title": "Delete a used tag", "what": "x", "step": {"method": "DELETE", "path": f"/api/v1/lists/{FL}/tags/{T_TRASH}"}}})
check(r2.status_code == 201 and ow(r2.json()["id"]) == "true", f"{who}: the card for a tag in use stays one-way ({r2.status_code} {ow(r2.json().get('id', 0))})")
assert F.post(B + f"/api/agents/{FA}/chat/{MID}/choice", json={"choice_ids": ["yes"]}).ok
r = requests.post(V + f"/agent/approvals/{MID}/run", headers=FH)
check(r.status_code == 204 and T3 not in tags_of(FH, FL), f"{who}: after the Yes the card runs the delete ({r.status_code} {r.text[:160]})")
one_way(who, FH, FL, T_TRASH, "approve_all, a tag on a task in the trash")

# ================================================================== a team agent in a project of an organisation: labels
r = A.post(B + "/api/orgs", json={"name": "Beispiel Studio"})
assert r.ok, r.text
ORG = r.json()["id"]
r = A.post(B + "/api/admin/agents", json={"username": "teambot", "display_name": "Team", "scopes": SCOPES, "org_id": ORG})
assert r.status_code in (200, 201), r.text
TA, TH = r.json()["id"], {"Authorization": "Bearer " + r.json()["token"]}
r = A.post(B + "/api/lists", json={"name": "Team work", "kind": "project", "org_id": ORG})
assert r.ok, r.text
TL = r.json()["id"]
r = A.put(B + f"/api/lists/{TL}/members", json={"user_id": TA, "role": "edit"})
assert r.ok, r.text
A.patch(B + f"/api/lists/{TL}", json={"agent_members": True})
ctl(A, TA, {"level": "free"})
who = "team"
r = A.post(B + "/api/org-labels", json={"org_id": ORG, "name": "Used label", "color": "#f87171"})
assert r.status_code == 201, r.text
LB_USED = r.json()["id"]
r = A.post(B + "/api/org-labels", json={"org_id": ORG, "name": "Idle label", "color": "#60a5fa"})
assert r.status_code == 201, r.text
LB_IDLE = r.json()["id"]
task(A, TL, "Carries the label", ["Used label"])
check(links(LB_USED) == 1 and links(LB_IDLE) == 0, "setup: one label is used, one is not")
for lb, why in ((LB_USED, "a used label of the organisation"), (LB_IDLE, "an unused label of the organisation")):
    r = requests.delete(V + f"/lists/{TL}/tags/{lb}", headers=TH)
    e = err(r)
    check(r.status_code == 409 and e.get("code") == "approval_required" and e.get("step") == "one_way",
          f"{who}: {why} -> 409 one_way ({r.status_code} {r.text[:160]})")
    check(kt.dbx("SELECT 1 FROM obj_tags WHERE id=?", (lb,)) and links(LB_USED) == 1, f"{who}: {why} -> nothing changed")
T4 = tag(A, TL, "team unused")
check(requests.delete(V + f"/lists/{TL}/tags/{T4}", headers=TH).status_code == 204, f"{who}: an unused project tag -> 204")
T5 = tag(A, TL, "team used")
task(A, TL, "Carries the tag", ["team used"])
one_way(who, TH, TL, T5, "a used project tag")

sys.exit(done("p6575_tag_unused"))
