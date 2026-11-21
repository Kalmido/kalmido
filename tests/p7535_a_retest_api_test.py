#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7535) the retest after the build -- the server's part, own container (start.sh). Invented people and texts only.
freelancer-matrix: tasks, lists
 - the project switch sits in the review step (PUT /api/lists/<id>/review {retest: '' | person | job}); a wrong value = 400;
   GET /api/v1/lists names it (retest) for the starter's dispatcher; review step off = ''
 - the task field "retest by a person" (POST .../review {action: retest_person, on}): only a person with write access sets it,
   an agent gets 403 (also through the API v1), a reader 403; only while the project's retest is a review job (else 400);
   shown on the task (app and API v1) only when set; one step in the task's history
 - with the retest on, "does not work" (changes) needs a reason (400 without); with it off a note stays optional
 - everything as frida, a person without an organisation (the main case)
usage: p7535_a_retest_api_test.py <datadir>"""
import os
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
import kt  # noqa: E402
from kt import check, B, H, done  # noqa: E402

V = B + "/api/v1"


def hdr(tok):
    return {"Authorization": "Bearer " + tok, **H}


kt.fresh()
A = kt.setup()
A.put(B + "/api/admin/agent-policy", json={"user_agents": True})
FU, F = freelancer(B, A, "frida")
GU, G = freelancer(B, A, "gert")  # a reader of frida's project
check(not F.get(B + "/api/state").json()["me"].get("workspaces"), "frida: no organisation")
L = F.post(B + "/api/lists", json={"name": "Release", "kind": "project", "ptype": "software"}).json()["id"]
check(F.put(B + f"/api/lists/{L}/members", json={"user_id": GU, "role": "view"}).ok, "setup: a reader")
r = F.post(B + "/api/my/agents", json={"username": "fridabot", "display_name": "Fridabot", "scopes": ["read", "tasks:write", "comments", "structure"]})
AID = r.json()["id"]
check(F.put(B + f"/api/lists/{L}/members", json={"user_id": AID, "role": "edit"}).ok, "setup: the agent in the project")
AH = hdr(F.post(B + f"/api/my/agents/{AID}/token").json()["token"])
T = F.post(B + "/api/tasks", json={"title": "Login button", "list_id": L}).json()["id"]


def v1_list():
    r = requests.get(V + "/lists", headers=AH)
    return next((x for x in r.json()["data"] if x["id"] == L), {}) if r.ok else {"http": r.status_code}


def review(s, b):
    return s.post(B + f"/api/tasks/{T}/review", json=b)


# ---- the switch
check(v1_list().get("retest") == "", "no review step: retest '' " + str(v1_list().get("retest")))
check(F.put(B + f"/api/lists/{L}/review", json={"on": True, "retest": "nope"}).status_code == 400, "a wrong value = 400")
r = F.put(B + f"/api/lists/{L}/review", json={"on": True, "reviewer": FU, "retest": "job"})
check(r.ok and '"retest":"job"' in r.json()["review_cfg"], "the switch on 'review job' " + r.text[:200])
check(v1_list().get("retest") == "job", "the API v1 names it for the dispatcher " + str(v1_list()))
check(requests.put(V + f"/lists/{L}/review", headers=AH, json={"on": True, "retest": "job", "x": 1}).status_code == 400, "v1: unknown keys refused")
check(requests.put(V + f"/lists/{L}/review", headers=AH, json={"on": True, "reviewer": FU, "retest": ""}).status_code == 403, "an agent switches the retest off: 403")
check(requests.put(V + f"/lists/{L}/review", headers=AH, json={"on": False}).status_code == 403, "an agent switches the review step (and so the retest) off: 403")
check(requests.put(V + f"/lists/{L}/review", headers=AH, json={"on": True, "reviewer": FU, "retest": "job", "gate": True}).ok, "the rest of the step stays the agent's (editors)")
check(v1_list().get("retest") == "job", "... the switch unchanged")
check(requests.put(V + f"/lists/{L}/review", headers=AH, json={"on": True, "reviewer": FU}).ok and v1_list().get("retest") == "job",
      "a body without retest (MCP set_list_review, an older app) keeps the switch")

# ---- the task field
r = requests.post(V + f"/tasks/{T}/review", headers=AH, json={"action": "retest_person", "on": True})
check(r.status_code == 403, "an agent sets the field: 403 " + r.text[:200])
check(review(G, {"action": "retest_person", "on": True}).status_code in (403, 404), "a reader cannot set it")
check(review(F, {"action": "retest_person", "on": "yes"}).status_code == 400, "on must be true / false")
check(not F.get(B + f"/api/tasks/{T}").json().get("retest_person"), "not set: not shown on the task")
r = review(F, {"action": "retest_person", "on": True})
check(r.ok and r.json().get("retest_person"), "frida hands the retest of this task to a person " + r.text[:200])
t1 = requests.get(V + f"/tasks/{T}", headers=AH).json()
t1 = t1.get("data", t1)
check(t1.get("retest_person") is True, "the API v1 shows it to the dispatcher " + str(t1.get("retest_person")))
acts = F.get(B + f"/api/tasks/{T}/timeline").json().get("activity") or []
check(any(a.get("kind") == "review" and (a.get("data") or {}).get("state") == "retest_person" for a in acts), "one step in the history")
check(requests.post(V + f"/tasks/{T}/review", headers=AH, json={"action": "retest_person", "on": False}).status_code == 403, "nor take it away: 403")
check(review(F, {"action": "retest_person", "on": False}).ok, "frida takes it back")
check(not F.get(B + f"/api/tasks/{T}").json().get("retest_person"), "... gone")

# field set -> the dispatcher asks the person (as its round does: review requested with the owner) -> "Waiting for me"
check(review(F, {"action": "retest_person", "on": True}).ok, "setup: the field set again")
r = requests.post(V + f"/tasks/{T}/review", headers=AH, json={"action": "request", "reviewer_id": FU, "note": "Built in commit abc1234 (main) - in review for the retest."})
check(r.ok, "the dispatcher's request (agent token) " + r.text[:200])
check(T in [x["id"] for x in F.get(B + "/api/inbox").json()["items"] if x["kind"] == "review"], "the task waits for frida (Waiting for me)")
check(review(F, {"action": "approve"}).ok, "frida: works")
check(review(F, {"action": "retest_person", "on": False}).ok, "setup: the field back")

# only with the review job: person / off = 400 (the field has no effect there)
check(F.put(B + f"/api/lists/{L}/review", json={"on": True, "reviewer": FU, "retest": "person"}).ok, "switch on 'person'")
check(v1_list().get("retest") == "person", "the API v1: person")
check(review(F, {"action": "retest_person", "on": True}).status_code == 400, "project on 'person': the field cannot be set")

# ---- "does not work" needs a reason with the retest on
check(review(F, {"action": "request", "reviewer_id": FU}).ok, "setup: in review, frida reviews")
r = review(F, {"action": "changes"})
check(r.status_code == 400, "retest on: changes without a reason = 400 " + r.text[:200])
r = review(F, {"action": "changes", "note": "The button does nothing on a phone"})
check(r.ok and r.json().get("review") == "changes", "with a reason: sent back " + r.text[:200])
check(F.put(B + f"/api/lists/{L}/review", json={"on": True, "reviewer": FU, "retest": ""}).ok, "switch off (review step stays)")
check(v1_list().get("retest") == "", "the API v1: ''")
check(review(F, {"action": "request", "reviewer_id": FU}).ok and review(F, {"action": "changes"}).ok, "retest off: a note stays optional")
check(F.put(B + f"/api/lists/{L}/review", json={"on": False}).ok and v1_list().get("retest") == "", "review step off: ''")

sys.exit(done("p7535_a_retest_api_test"))
