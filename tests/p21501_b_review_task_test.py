#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1501.0 B (#7533): a task from a comment of a sign-off (review) with one click. Invented names and links only.
tenant-matrix: video (another organisation: 404 on the route)
freelancer-matrix: videos (a person without an organisation: a task from a comment of a review at her private project)
 - a review at a project (list) and one at a task: "can_task" for who may change it and write in the project; the route makes a
   task in the project (title = the comment, description = text + "From the sign-off ...: Version 1 · 00:42"), once per comment
 - the link of the core (obj_links video_review -> task, rel review_task, extra comment_id / version / at) in both directions:
   the review's comment carries {task: id, title, done}, GET /api/videos?task_id= of the new task names the review as `from`,
   the task's links (GET /api/obj/task/<id>/links) show the review; done on the task -> done at the comment
 - an answer (not a top-level comment) 400; a review only at a client (no project): can_task false, the route 403
 - a member who may only read the project: can_task false, 403; another organisation 404; an agent 404 (people only)
 - the task in the trash: the comment says "gone"
usage: p21501_b_review_task_test.py <datadir>"""
import json
import os
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, sess  # noqa: E402

fresh(prefix="P21501B")
V = B + "/api/videos"
FEAT = "cal,comments,collab,office,clients,videos"

assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True, "modules": ["comments", "office", "clients"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT})
ME = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Example Studio", "admin_id": ME}).json()["id"]
for u in ("bob", "carol"):
    A.post(B + "/api/users", json={"username": u, "display_name": u.title(), "password": "password123", "email": f"{u}@example.com", "orgs": []})
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
Bo, Ca = sess("bob"), sess("carol")
CAROL = Ca.get(B + "/api/state").json()["me"]["id"]
ORG2 = A.post(B + "/api/admin/orgs", json={"name": "Other Example", "admin_id": CAROL}).json()["id"]
for s, o in ((A, ORG), (Bo, ORG), (Ca, ORG2)):
    s.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEAT, "workspace": f"org:{o}"})
ag = A.post(B + "/api/admin/agents", json={"scopes": ["read", "tasks:write", "comments"], "username": "claude", "display_name": "Claude"}).json()
AGH = {"Authorization": "Bearer " + ag["token"], "X-Requested-With": "kalmido"}
FID, Fr = freelancer(B, A, features=FEAT)

L = A.post(B + "/api/lists", json={"name": "Imagefilm Spring", "org_id": ORG}).json()["id"]
BOB = Bo.get(B + "/api/state").json()["me"]["id"]
A.put(B + f"/api/lists/{L}/members", json={"user_id": BOB, "role": "view"})
T = A.post(B + "/api/tasks", json={"title": "Rough cut", "list_id": L}).json()["id"]
CL = A.post(B + "/api/clients", json={"name": "Client One Ltd"}).json()["id"]

r = A.post(V, json={"list_id": L, "title": "Spot 30s", "url": "https://vimeo.com/123456789"})
check(r.ok, f"a review at the project {r.status_code} {r.text[:200]}")
R = r.json()
VID, VER = R["id"], R["versions"][0]["id"]
r = A.post(f"{V}/{VID}/comments", json={"version_id": VER, "at_sec": 42, "body": "Logo two frames later\nand a bit smaller"})
CID = r.json()["comment_id"]
ANS = A.post(f"{V}/{VID}/comments", json={"parent_id": CID, "body": "Agreed"}).json()["comment_id"]
R = A.get(f"{V}/{VID}").json()
check(R.get("can_task") is True and all(c.get("task") is None for c in R["comments"]), f"alice may make tasks, none made yet {R.get('can_task')}")

# ---------------------------------------------------------------- the task
r = A.post(f"{V}/{VID}/comments/{CID}/task", json={})
check(r.status_code == 201, f"a task from the comment {r.status_code} {r.text[:200]}")
J = r.json()
TID = J.get("task_id")
t = A.get(B + f"/api/tasks/{TID}").json() if TID else {}
t = t.get("task", t)
check(t.get("list_id") == L and t.get("title") == "Logo two frames later and a bit smaller", f"the task in the review's project, titled by the comment {t.get('list_id')} {t.get('title')}")
check("From the sign-off “Spot 30s”: Version 1 · 00:42" in (t.get("content") or ""), f"its description names review, version and place {t.get('content')!r}")
cm = {c["id"]: c for c in J["comments"]}
check(cm[CID].get("task") == {"id": TID, "title": t.get("title"), "done": False} and cm[ANS].get("task") is None, f"the comment carries its task {cm[CID].get('task')}")
lk = [(*x[:5], x[5] if isinstance(x[5], dict) else json.loads(x[5] or "{}")) for x in dbx("SELECT src_kind, src_id, dst_kind, dst_id, rel, extra FROM obj_links WHERE rel='review_task'")]
check(len(lk) == 1 and tuple(lk[0][:5]) == ("video_review", VID, "task", TID, "review_task") and lk[0][5].get("comment_id") == CID
      and lk[0][5].get("version") == 1 and lk[0][5].get("at") == 42, f"one link of the core with comment, version and time {lk}")
r = A.post(f"{V}/{VID}/comments/{CID}/task", json={})
check(r.ok and len(dbx("SELECT 1 FROM obj_links WHERE rel='review_task'")) == 1
      and dbx("SELECT COUNT(*) FROM tasks WHERE list_id=? AND deleted_at IS NULL", (L,))[0][0] == 2, "a second click makes no second task")
fr = A.get(V, params={"task_id": TID}).json()
check(fr.get("from") == [{"id": VID, "title": "Spot 30s", "comment_id": CID}], f"the task's panel names the review it came from {fr.get('from')}")
ol = A.get(B + f"/api/obj/task/{TID}/links").json()
ol = ol.get("links", ol) if isinstance(ol, dict) else ol
check(any(x.get("rel") == "review_task" and x.get("dir") == "in" and (x.get("other") or {}).get("kind") == "video_review" for x in ol or []),
      f"the task's links show the review (the core's list) {ol}")
check(A.post(B + f"/api/tasks/{TID}/complete").ok, "the task done")
R = A.get(f"{V}/{VID}").json()
check(next(c for c in R["comments"] if c["id"] == CID)["task"].get("done") is True, f"done shows at the comment {next(c for c in R['comments'] if c['id'] == CID)['task']} {dbx('SELECT status, completed_at FROM tasks WHERE id=?', (TID,))}")

# ---------------------------------------------------------------- refusals
check(A.post(f"{V}/{VID}/comments/{ANS}/task", json={}).status_code == 400, "an answer makes no task")
RC = A.post(V, json={"client_id": CL, "title": "Client only", "url": "https://vimeo.com/22222222"}).json()
c2 = A.post(f"{V}/{RC['id']}/comments", json={"version_id": RC["versions"][0]["id"], "at_sec": 1, "body": "Colour"}).json()["comment_id"]
check(A.get(f"{V}/{RC['id']}").json().get("can_task") is False and A.post(f"{V}/{RC['id']}/comments/{c2}/task", json={}).status_code == 403,
      "a review only at a client offers no task (403)")
CID2 = A.post(f"{V}/{VID}/comments", json={"version_id": VER, "at_sec": 7, "body": "Music softer"}).json()["comment_id"]
rb = Bo.get(f"{V}/{VID}")
check(rb.ok and rb.json().get("can_task") is False and Bo.post(f"{V}/{VID}/comments/{CID2}/task", json={}).status_code == 403,
      f"a member who only reads the project: no task {rb.status_code}")
check(Ca.post(f"{V}/{VID}/comments/{CID2}/task", json={}).status_code == 404, "another organisation: 404")  # tenant: POST /api/videos/{}/comments/{}/task
check(requests.post(f"{V}/{VID}/comments/{CID2}/task", json={}, headers=AGH).status_code in (401, 403, 404), "an agent: not through the app (people only)")
check(not dbx("SELECT 1 FROM obj_links WHERE rel='review_task' AND extra->>'comment_id'=?", (str(CID2),)), "none of them made a task")

# ---------------------------------------------------------------- a review at a task; the task in the trash
RT = A.post(V, json={"task_id": T, "title": "Still", "url": "https://vimeo.com/33333333"}).json()
c3 = A.post(f"{V}/{RT['id']}/comments", json={"version_id": RT["versions"][0]["id"], "at_sec": 3, "body": "Crop the left edge"}).json()["comment_id"]
r = A.post(f"{V}/{RT['id']}/comments/{c3}/task", json={})
T3 = r.json().get("task_id")
check(r.status_code == 201 and dbx("SELECT list_id FROM tasks WHERE id=?", (T3,))[0][0] == L, "a review at a task: the task goes into that task's project")
A.delete(B + f"/api/tasks/{T3}")
R = A.get(f"{V}/{RT['id']}").json()
check(next(c for c in R["comments"] if c["id"] == c3).get("task") == {"id": None, "gone": True}, "the task in the trash: the comment says gone")

# ---------------------------------------------------------------- a person without an organisation
LF = Fr.post(B + "/api/lists", json={"name": "My film"}).json()["id"]
RF = Fr.post(V, json={"list_id": LF, "title": "Cut", "url": "https://vimeo.com/44444444"}).json()
cf = Fr.post(f"{V}/{RF['id']}/comments", json={"version_id": RF["versions"][0]["id"], "at_sec": 5, "body": "Shorter"}).json()["comment_id"]
r = Fr.post(f"{V}/{RF['id']}/comments/{cf}/task", json={})
check(r.status_code == 201 and dbx("SELECT list_id FROM tasks WHERE id=?", (r.json().get("task_id"),))[0][0] == LF, "P4: a freelancer makes a task from a comment of her review")
check(A.post(f"{V}/{RF['id']}/comments/{cf}/task", json={}).status_code == 404, "P4: someone else does not reach her review")

sys.exit(done("p21501_b_review_task_test"))
