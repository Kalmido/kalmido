#!/usr/bin/env python3
# kalmido-suite:
"""2.352.0 B (#2752): no difference any more between a list and a project -- invented names only.
 (a) a list of kind "list" is a project: project page (GET / PATCH overview), dependencies to another project, sprints,
     "Move dependent tasks along" on by default, in the roadmap with projects_only
 (b) tracked = has a status: setting one works on kind "list", clearing it ("") = not tracked any more
 (c) the inbox stays outside: no status, no project page, no dependencies (409)
 (d) a list template keeps its dates relative to the project start, also without "relative" (the flag is ignored)
 (e) a person without an organisation: the same in her private workspace
 (f) 2.1380.0 (#6826): gone -- the start step (an old kind=project without a status became "on track" once) is retired
usage: p2352_b_project_unify_test.py <datadir>
freelancer-matrix: lists"""
import os
import sys
from datetime import timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check  # noqa: E402

started = kt.fresh(prefix="P2352B")
A = kt.setup()
FEAT = "cal,timeline,collab,progress,deps,fields,comments"
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
D = lambda n: (kt.today() + timedelta(days=n)).isoformat()  # noqa: E731


def state(s):
    return s.get(B + "/api/state").json()


def lst(s, lid):
    return next((x for x in state(s)["lists"] if x["id"] == lid), None)


def inbox(s):
    return next(x["id"] for x in state(s)["lists"] if x["is_inbox"])


def task(s, lid, title, due=None, start=None):
    r = s.post(B + "/api/tasks", json={"list_id": lid, "title": title, **({"due": due} if due else {}), **({"start": start} if start else {})})
    assert r.ok, r.text
    return r.json()["id"]


def project_checks(s, who):
    """(a)-(c) for the session s; who names the person in the messages."""
    PL = s.post(B + "/api/lists", json={"name": "Groceries " + who}).json()["id"]
    PK = s.post(B + "/api/lists", json={"name": "Launch " + who, "kind": "project"}).json()["id"]
    check(lst(s, PL)["kind"] == "list", f"{who}: kind is still stored and returned (list)")
    check(lst(s, PL)["dep_shift"] == 1, f"{who}: a new kind=list project moves dependent tasks along by default")
    # (a) the project page
    r = s.get(B + f"/api/lists/{PL}/overview")
    check(r.ok, f"{who}: kind list has a project page {r.status_code} {r.text[:120]}")
    r = s.patch(B + f"/api/lists/{PL}/overview", json={"description": "Weekly shop of an invented household"})
    check(r.ok and "invented household" in s.get(B + f"/api/lists/{PL}/overview").text, f"{who}: the project page takes a description {r.status_code}")
    # dependencies between a kind=list and a kind=project project
    t1, t2 = task(s, PL, "Milk", D(2)), task(s, PK, "Plan", D(1))
    r = s.post(B + "/api/deps", json={"task_id": t1, "blocker_id": t2})
    check(r.ok, f"{who}: a dependency from a kind=list project {r.status_code} {r.text[:120]}")
    r = s.put(B + f"/api/lists/{PL}/sprint-settings", json={"on": True})
    check(r.ok, f"{who}: sprints in a kind=list project {r.status_code} {r.text[:120]}")
    j = s.get(B + "/api/roadmap", params={"projects_only": "1"}).json()
    ids = [g["list"]["id"] for g in j.get("groups", [])]
    check(PL in ids and not any(g["list"]["is_inbox"] for g in j.get("groups", [])), f"{who}: projects_only keeps kind list, leaves out the inbox {ids}")
    # (b) tracked = has a status
    check(not lst(s, PL)["status"], f"{who}: a new project is not tracked (no status)")
    r = s.post(B + f"/api/lists/{PL}/status", json={"status": "at_risk", "note": "Shop closed"})
    check(r.ok and lst(s, PL)["status"] == "at_risk", f"{who}: kind list takes a status (tracked) {r.status_code} {r.text[:120]}")
    r = s.post(B + f"/api/lists/{PL}/status", json={"status": ""})
    check(r.ok and not lst(s, PL)["status"], f"{who}: status cleared = not tracked {r.status_code}")
    # (c) the inbox
    INB = inbox(s)
    check(s.post(B + f"/api/lists/{INB}/status", json={"status": "on_track"}).status_code in (400, 409), f"{who}: the inbox has no status")
    check(s.get(B + f"/api/lists/{INB}/overview").status_code == 409, f"{who}: the inbox has no project page")
    ti = task(s, INB, "Loose idea", D(3))
    check(s.post(B + "/api/deps", json={"task_id": ti, "blocker_id": t2}).status_code == 409, f"{who}: no dependency from the inbox")
    return PL, PK


PL, PK = project_checks(A, "alice")

# (d) a list template keeps its dates relative, also when "relative" is not asked for
TL = A.post(B + "/api/lists", json={"name": "Trade fair"}).json()["id"]
task(A, TL, "Book the stand", D(10))
task(A, TL, "Print flyers", D(14), D(12))
for body, what in (({"list_id": TL, "name": "Fair A"}, "without the flag"), ({"list_id": TL, "name": "Fair B", "relative": False}, "relative false")):
    r = A.post(B + "/api/templates", json=body)
    data = (r.json().get("data") or {}) if r.ok else {}
    offs = sorted(t.get("due_offset") for t in data.get("tasks", []))
    check(r.ok and data.get("rel") is True and offs == [0, 4], f"template {what}: relative to the project start (offsets 0 and 4): {r.status_code} {data.get('rel')} {offs}")

# (e) a person without an organisation
FID, Fr = freelancer(B, A)
project_checks(Fr, "frida")

# 2.1380.0 (#6826): (f) the start step stood here (flag migr_kind2352 deleted, restart: an old kind=project without a status
# became "on track" once); that one-shot is retired (core/oncesteps.py RETIRED), the start no longer runs it

sys.exit(kt.done("p2352_b_project_unify"))
