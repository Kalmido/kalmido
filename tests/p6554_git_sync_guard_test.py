#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1306.0 (#6554, audit #4804 D2 / D5 / D9): the guards of the issue sync's way out (integrations/git_sync.py, git.py,
git_issues.py), against the fake GitHub of tests/fake_git.py (:8090), never a real provider. Invented names only.
 - only what a signed-in person creates in the app becomes an issue: a task an agent creates through the API does not
 - @names in what goes out (title, text, comment) notify nobody on the provider (a zero-width space after the @), an e-mail
   address stays as it is; when the text comes back the sync sees no change (no echo, no conflict)
 - per connection and day at most 60 new issues and 300 comments: past it nothing goes out, the link waits for the next day,
   the connecting person is told once (News "integfail" gitcap); the next day it goes out
 - an issue address that is no http(s) is not taken over as the task's link (javascript:)
 - the person whose token a connection uses: may remove it without being a project admin (another member may not); after
   leaving the project the connection pauses (error "owner", the project owner is told) and that person can still remove it
 - a person without an organisation (freelancer-matrix: tasks): bob and carol have none
usage: p6554_git_sync_guard_test.py <datadir>"""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, DATA, check, done, until  # noqa: E402

GH = "http://127.0.0.1:8090"
GHTOK, FTOK = "ghp_guardSyncWrite0042", "ghp_guardCarolWrite0099"
KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
ZW = "@​"


def gh_issue(n, title, body="", url=None, repo="acme/app"):
    return {"number": n, "title": title, "body": body, "state": "open", "labels": [], "assignees": [],
            "user": {"login": "reporter"}, "html_url": url if url is not None else f"{GH}/{repo}/issues/{n}",
            "created_at": "2026-09-01T10:00:00Z", "updated_at": "2026-09-05T10:00:00Z", "closed_at": None, "comments": 0}


STATE = {"8090": {"acme/app": {"token": GHTOK, "default_branch": "main", "issues": []},
                  "carol/site": {"token": FTOK, "default_branch": "main", "issues": []}}}
GJ = os.path.join(DATA, "git.json")


def put_state():
    tmp = GJ + ".tmp"
    with open(tmp, "w") as f:
        json.dump(STATE, f)
    os.replace(tmp, GJ)


def edit(repo, fn):
    st = json.load(open(GJ))
    fn(st["8090"][repo])
    tmp = GJ + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.replace(tmp, GJ)


if kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_CALENDAR_ALLOW_HOSTS": "127.0.0.1", "KALMIDO_GIT_POLL": "3600",
                 "KALMIDO_GIT_TICK": "1"}, prefix="P6554"):
    shutil.copy(os.path.join(N, "fake_git.py"), DATA)
    put_state()
    subprocess.run(["docker", "exec", "-d", CT, "python", "/data/fake_git.py"])
kt.docker_logs_on_first_fail()
until(lambda: os.path.exists(os.path.join(DATA, "git.log")), 20)
LOGF = os.path.join(DATA, "git.log")


def loglen():
    return len(open(LOGF).readlines())


def posts(n0, what="issues"):
    rows = [json.loads(x) for x in open(LOGF).readlines()[n0:]]
    return [x for x in rows if x.get("method") == "POST" and x["path"].endswith("/comments" if what == "comments" else "/issues")]


A = kt.setup(lang="en")
ids = {}
for u, dn in (("bob", "Bob"), ("carol", "Carol")):
    r = A.post(B + "/api/users", json={"username": u, "display_name": dn, "password": "password123"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
Bo, Ca = kt.sess("bob"), kt.sess("carol")
for x in (Bo, Ca):
    x.patch(B + "/api/settings", json={"lang": "en"})
r = A.post(B + "/api/admin/agents", json={"scopes": ["write"], "username": "claude", "display_name": "Claude"})
assert r.status_code == 201, r.text
AG, AGTOK = r.json()["id"], r.json()["token"]
AGH = {"Authorization": "Bearer " + AGTOK, "X-Requested-With": "kalmido"}
ALICE = kt.dbx("SELECT id FROM users WHERE username='alice'")[0][0]
P = A.post(B + "/api/lists", json={"name": "App", "kind": "project"}).json()["id"]
assert A.put(B + f"/api/lists/{P}/members", json={"user_id": ids["bob"], "role": "edit"}).ok
assert A.put(B + f"/api/lists/{P}/members", json={"user_id": AG, "role": "edit"}).ok


def poll(cid):
    kt.dbx("UPDATE git_conns SET next_at=0 WHERE id=?", (cid,))
    return until(lambda: kt.dbx("SELECT next_at FROM git_conns WHERE id=?", (cid,))[0][0] > 1000, 30)


def push(tid):
    """The collected changes of task tid go out now (push_due 1 -> the loop sends them and sets 0)."""
    kt.dbx("UPDATE git_issue_links SET push_due=1 WHERE task_id=? AND push_due>0", (tid,))
    return until(lambda: (lambda r: r and r[0][0] == 0)(kt.dbx("SELECT push_due FROM git_issue_links WHERE task_id=?", (tid,))), 30)


def push_waits(tid):
    """push_due 1 -> the loop takes it and the link waits for the next day (push_due hours ahead)."""
    kt.dbx("UPDATE git_issue_links SET push_due=1 WHERE task_id=? AND push_due>0", (tid,))
    return until(lambda: (lambda r: r and r[0][0] > time.time() + 60)(kt.dbx("SELECT push_due FROM git_issue_links WHERE task_id=?", (tid,))), 30)


def link(tid):
    r = kt.dbx("SELECT conn_id, issue_no, push_due FROM git_issue_links WHERE task_id=?", (tid,))
    return r[0] if r else None


def told(s, what):
    return [x for x in s.get(B + "/api/news").json()["items"] if x["kind"] == "integfail" and x["data"].get("what") == what]


r = A.post(B + f"/api/lists/{P}/repos", json={"provider": "github", "base_url": GH, "repo": "acme/app", "token": GHTOK})
check(r.status_code == 201, f"connected: {r.status_code} {r.text[:200]}")
GID = r.json()["id"]
check(kt.dbx("SELECT token_by FROM git_conns WHERE id=?", (GID,))[0][0] == ALICE, "token_by = the person who stored the token")
poll(GID)
r = A.patch(B + f"/api/repos/{GID}", json={"issue_sync": True, "issue_create": True})
check(r.ok and r.json().get("issue_create") is True, f"sync + create on: {r.status_code} {r.text[:200]}")
poll(GID)

# ---- D9: an issue address that is no http(s) is not taken over as the link
edit("acme/app", lambda x: x["issues"].extend([gh_issue(1, "Evil link", url="javascript:alert(1)"), gh_issue(2, "Good link")]))
edit("acme/app", lambda x: [i.update(created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")) for i in x["issues"]])
poll(GID)
got = {t: u for t, u in kt.dbx("SELECT title, url FROM tasks WHERE list_id=? AND title IN ('Evil link', 'Good link')", (P,))}
check(set(got) == {"Evil link", "Good link"}, f"both issues became tasks: {got}")
check(not got.get("Evil link") and (got.get("Good link") or "").startswith("http://127.0.0.1:8090/"),
      f"a javascript: address is no link, an http one is: {got}")

# ---- D2: only what a person creates in the app becomes an issue
r = requests.post(B + "/api/v1/tasks", json={"list_id": P, "title": "Made by the agent"}, headers=AGH)
check(r.status_code in (200, 201), f"the agent creates a task: {r.status_code} {r.text[:200]}")
TA = r.json().get("id")
check(TA and not link(TA), "a task an agent created never becomes an issue")
T1 = Bo.post(B + "/api/tasks", json={"list_id": P, "title": "Ping @octocat", "content": "Hi @someone, mail me at a@b.example"}).json()["id"]
check(link(T1) and link(T1)[1] == -T1, "a task a person created in the app is queued")

# ---- D2: @names are taken out of what goes out, no echo when it comes back
n0 = loglen()
push(T1)
p = posts(n0)
check(p and p[0]["body"]["title"] == f"Ping {ZW}octocat" and p[0]["body"]["body"] == f"Hi {ZW}someone, mail me at a@b.example",
      f"title and text go out without working @mentions, the address stays: {p}")
NO = link(T1)[1]
r = Bo.post(B + f"/api/tasks/{T1}/comments", json={"body": "Thanks @octocat"})
check(r.ok, f"comment: {r.status_code}")
n1 = loglen()
push(T1)
pc = posts(n1, "comments")
check(pc and f"{ZW}octocat" in pc[0]["body"]["body"] and "@octocat" not in pc[0]["body"]["body"], f"the comment too: {pc}")
poll(GID)
t = A.get(B + f"/api/tasks/{T1}").json()
lost = kt.dbx("SELECT 1 FROM activity WHERE task_id=? AND kind='git_sync_lost'", (T1,))
check(t["title"] == "Ping @octocat" and "​" not in (t.get("content") or "") and not lost,
      f"back from the repository the task is unchanged (no echo, no conflict): {t['title']!r} {t.get('content')!r}")
check(not (link(T1) or (0, 0, 1))[2], "nothing due after the round")

# ---- D2: the daily limit of new issues
day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
kt.dbx("UPDATE git_conns SET out_day=?, out_issues=60, out_comments=0, out_told='' WHERE id=?", (day, GID))
T2 = Bo.post(B + "/api/tasks", json={"list_id": P, "title": "Over the limit"}).json()["id"]
n2 = loglen()
check(push_waits(T2), "past 60 issues today the new issue waits for the next day")
check(not posts(n2) and link(T2)[1] == -T2, "nothing went out, the link is still pending")
check(until(lambda: len(told(A, "gitcap")) == 1, 10), "the connecting person is told")
T3 = Bo.post(B + "/api/tasks", json={"list_id": P, "title": "Also over"}).json()["id"]
check(push_waits(T3) and len(told(A, "gitcap")) == 1, "told once a day, not per task")
kt.dbx("UPDATE git_conns SET out_day='2000-01-01' WHERE id=?", (GID,))  # the next day
n3 = loglen()
push(T2)
check(len(posts(n3)) == 1 and link(T2)[1] > 0, "the next day it goes out")
check(kt.dbx("SELECT out_day, out_issues FROM git_conns WHERE id=?", (GID,))[0] == (day, 1), "the day's count starts anew")

# ---- D2: the daily limit of comments
kt.dbx("UPDATE git_conns SET out_comments=300 WHERE id=?", (GID,))
assert Bo.post(B + f"/api/tasks/{T1}/comments", json={"body": "One too many"}).ok
n4 = loglen()
check(push_waits(T1) and not posts(n4, "comments"), "past 300 comments today the comment waits")
kt.dbx("UPDATE git_conns SET out_day='2000-01-01' WHERE id=?", (GID,))
n5 = loglen()
push(T1)
check(len(posts(n5, "comments")) == 1, "the next day the comment goes out")

# ---- D5: the person whose token a connection uses
P2 = A.post(B + "/api/lists", json={"name": "Site", "kind": "project"}).json()["id"]
assert A.put(B + f"/api/lists/{P2}/members", json={"user_id": ids["carol"], "role": "admin"}).ok
assert A.put(B + f"/api/lists/{P2}/members", json={"user_id": ids["bob"], "role": "edit"}).ok
r = Ca.post(B + f"/api/lists/{P2}/repos", json={"provider": "github", "base_url": GH, "repo": "carol/site", "token": FTOK})
check(r.status_code == 201, f"carol connects with her token: {r.status_code} {r.text[:200]}")
CID = r.json()["id"]
poll(CID)
assert A.put(B + f"/api/lists/{P2}/members", json={"user_id": ids["carol"], "role": "edit"}).ok
rs = Ca.get(B + f"/api/lists/{P2}/repos").json()["repos"]
check(rs and rs[0].get("mine") is True, f"carol sees it as hers: {rs}")
rb = Bo.get(B + f"/api/lists/{P2}/repos").json()["repos"]
check(rb and rb[0].get("mine") is False, "bob does not")
check(Bo.delete(B + f"/api/repos/{CID}").status_code in (403, 404), "another member without the admin role may not remove it")
r = requests.delete(B + f"/api/repos/{CID}", headers=AGH)
check(r.status_code in (401, 403, 404) and kt.dbx("SELECT 1 FROM git_conns WHERE id=?", (CID,)), f"an agent may not: {r.status_code}")
assert A.delete(B + f"/api/lists/{P2}/members/{ids['carol']}").ok
poll(CID)
check(kt.dbx("SELECT last_error FROM git_conns WHERE id=?", (CID,))[0][0] == "owner", "carol left: the connection pauses")
rs = A.get(B + f"/api/lists/{P2}/repos").json()["repos"]
check(rs and rs[0]["status"] == "error" and "no access to the project" in rs[0]["error"], f"shown to the project: {rs}")
check(until(lambda: len(told(A, "gitowner")) == 1, 10), "the project owner is told")
poll(CID)
check(len(told(A, "gitowner")) == 1, "told once, not every round")
r = Ca.delete(B + f"/api/repos/{CID}")
check(r.ok and not kt.dbx("SELECT 1 FROM git_conns WHERE id=?", (CID,)), f"carol removes her connection without access: {r.status_code} {r.text[:200]}")

log = subprocess.run(["docker", "logs", CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
check("git loop error" not in log and "Traceback" not in log, "no error in the git loop")
check(all(t not in log for t in (GHTOK, FTOK)), "no access token in the server's log")

sys.exit(done("p6554_git_sync_guard"))
