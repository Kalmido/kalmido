#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1198.0 (#3642): the organisation export takes the old ticket keys of tasks (task_keys) and the people taken off a project
by hand (list_folder_skip) along; the import writes them with the new ids. Invented names only.
 - an organisation's project with the key APP and two tasks (APP-1, APP-2), the key changed to NEW (APP-1 / APP-2 stay as
   old keys), a person taken off by hand (a list_folder_skip row, written like lists/lffolder.py does)
 - exported and imported into another organisation: the old keys point at the NEW tasks and the new project, the numbers
   stay, a new task there gets NEW-3 (the counter starts above the imported numbers, never NEW-1 a second time), the
   person taken off stays off (the row on the new project)
 - a person without an organisation imports the same export privately: the old keys come along, the folder exception not
   (a private project has no folder shares of the organisation)
 - 2.1218.0 (#6202): the target workspace already has a project with the key NEW (an organisation, and a second person without
   an organisation privately): the imported project comes without a key (never two NEW in one workspace), its numbers stay as
   old keys (NEW-1 / NEW-2 and APP-1 / APP-2 find the moved tasks), the target's own project keeps NEW, a new task there gets
   NEW-2 from its own counter, the import report says so
Starts its OWN container (start.sh) with KALMIDO_SECRET_KEY (P21198B_NOSTART=1 = the server already runs like that).
usage: p21198_b_orgx_keys_test.py <datadir>"""
# freelancer-matrix: lists
# tenant-matrix: own
import base64
import os
import subprocess
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess, su_get, until  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}
KEY = base64.b64encode(os.urandom(32)).decode()


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(q, args).fetchall()
    finally:
        c.close()


def upload(s, data, name="alpha.kalmido-export"):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": name})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return iid


def wait(s, iid, secs=240):
    j = {}
    for _ in range(secs * 4):
        j = s.get(B + f"/api/account/import/{iid}").json()
        if j.get("state") not in ("checking", "running", "upload"):
            return j
        time.sleep(0.25)
    return j


def opened(s, data, rk):
    iid = upload(s, data)
    j = wait(s, iid)
    check(j.get("state") == "key", f"asks for the recovery key {j.get('state')} {j.get('error')}")
    check(s.post(B + f"/api/account/import/{iid}/key", json={"recovery_key": rk}).status_code == 202, "the recovery key is taken")
    j = wait(s, iid)
    check(j.get("state") == "preview", f"opened {j.get('state')} {j.get('error')}")
    return iid


def run(s, iid, target):
    r = s.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": target, "people": {}})
    check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
    return wait(s, iid)


def tasks_of(lid):
    return {r[0]: (r[1], r[2]) for r in sql("SELECT id, title, ticket_no FROM tasks WHERE list_id=? AND deleted_at IS NULL", (lid,))}


def keys_of(lid):
    """{(prefix, no): task title} of the old keys of the tasks of list lid."""
    return {(r[0], r[1]): r[2] for r in sql("SELECT k.prefix, k.no, t.title FROM task_keys k JOIN tasks t ON t.id=k.task_id WHERE t.list_id=?", (lid,))}


if os.environ.get("P21198B_NOSTART") != "1":
    env = dict(os.environ, EXTRA=os.environ.get("EXTRA", "") + f" -e KALMIDO_INSTANCE_MODE=workspaces -e KALMIDO_ORGCRYPT_DELAY=0 -e KALMIDO_SECRET_KEY={KEY}")
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    s0 = requests.Session()
    s0.headers.update(H)
    assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Ablage", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + f"/api/users/{ALICE}", json={"email": "alice@example.com"})
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha Projekte", "admin_id": ALICE}).json()["id"]
GAM = A.post(B + "/api/admin/orgs", json={"name": "Gamma Ziel", "admin_id": ALICE}).json()["id"]

# ---------------------------------------------------------------- the source: a project with a key, changed once
P = A.post(B + "/api/lists", json={"name": "Bordbuch", "org_id": ORG, "kind": "project"}).json()["id"]
T1, T2 = (A.post(B + "/api/tasks", json={"title": t, "list_id": P}).json()["id"] for t in ("Erster Eintrag", "Zweiter Eintrag"))
check(A.patch(B + f"/api/lists/{P}", json={"ticket_key": "APP"}).ok, "setup: key APP")
check(A.patch(B + f"/api/lists/{P}", json={"ticket_key": "NEW"}).ok, "setup: key changed to NEW")
check(keys_of(P) == {("APP", 1): "Erster Eintrag", ("APP", 2): "Zweiter Eintrag"}, f"setup: APP-1 / APP-2 stay as old keys {keys_of(P)}")
# a person taken off by hand: the row lists/lffolder.py writes (lf_skip), here for the exporting person herself (she maps to herself)
code = ("from kalmido.core.db import connect, iso, now_utc\nc = connect()\n"
        f"c.execute('INSERT INTO list_folder_skip(list_id, user_id, created_at) VALUES(?,?,?)', ({P}, {ALICE}, iso(now_utc())))\n"
        "c.commit()\nprint('ok')\n")
ct = subprocess.run(["docker", "exec", CT, "python3", "-c", code], capture_output=True, text=True)
check(ct.stdout.split() == ["ok"], f"setup: the folder exception written {ct.stdout} {ct.stderr[-400:]}")

# ---------------------------------------------------------------- export -> import into the other organisation
r = A.post(B + f"/api/orgs/{ORG}/export")
check(r.status_code == 202, "organisation export started " + r.text[:120])
until(lambda: A.get(B + f"/api/orgs/{ORG}/export").json().get("state") != "running", 120)
OX = su_get(A, B + f"/api/orgs/{ORG}/export/file").content
RK = A.post(B + f"/api/orgs/{ORG}/encryption/recovery", json={"password": "password123"}).json().get("recovery_key", "")
check(OX[:13] == b"KALMIDO-ORGX\n" and RK, "organisation export + recovery key")
iid = opened(A, OX, RK)
j = run(A, iid, GAM)
check(j.get("state") == "done", f"import done {j.get('state')} {j.get('error')} {(j.get('result') or {}).get('warnings')}")
gp = sql("SELECT id, ticket_key FROM lists WHERE org_id=? AND name='Bordbuch' AND deleted_at IS NULL", (GAM,))
GP = gp[0][0] if gp else 0
check(GP and GP != P and gp[0][1] == "NEW", f"the project came along with a new id and its key {gp}")
nt = tasks_of(GP)
check(sorted(nt.values()) == [("Erster Eintrag", 1), ("Zweiter Eintrag", 2)] and not set(nt) & {T1, T2},
      f"the tasks came along with new ids and their numbers {nt}")
check(keys_of(GP) == {("APP", 1): "Erster Eintrag", ("APP", 2): "Zweiter Eintrag"}, f"#3642: APP-1 / APP-2 find the new tasks {keys_of(GP)}")
check(not sql("SELECT 1 FROM task_keys WHERE list_id IS NOT NULL AND list_id<>? AND task_id IN (SELECT id FROM tasks WHERE list_id=?)", (GP, GP)),
      "#3642: the old keys name the new project, never the source's id")
T3 = A.post(B + "/api/tasks", json={"title": "Dritter Eintrag", "list_id": GP}).json().get("id")
check(tasks_of(GP).get(T3, (None, None))[1] == 3, f"#3642: a new task in the moved project gets NEW-3, not NEW-1 again {tasks_of(GP)}")
check(sql("SELECT user_id FROM list_folder_skip WHERE list_id=?", (GP,)) == [(ALICE,)], "#3642: the person taken off by hand stays off on the new project")
A.delete(B + f"/api/account/import/{iid}")

# ---------------------------------------------------------------- a person without an organisation imports it privately
FID, Fr = freelancer(B, A)
iid = opened(Fr, OX, RK)
j = run(Fr, iid, "private")
check(j.get("state") == "done", f"freelancer: import done {j.get('error')} {(j.get('result') or {}).get('warnings')}")
fp = sql("SELECT id FROM lists WHERE org_id IS NULL AND owner_id=? AND name='Bordbuch' AND deleted_at IS NULL", (FID,))
FP = fp[0][0] if fp else 0
check(FP and keys_of(FP) == {("APP", 1): "Erster Eintrag", ("APP", 2): "Zweiter Eintrag"}, f"freelancer: the old keys find her private tasks {keys_of(FP) if FP else fp}")
check(FP and not sql("SELECT 1 FROM list_folder_skip WHERE list_id=?", (FP,)), "freelancer: no folder exception on a private project")


# ---------------------------------------------------------------- 2.1218.0 (#6202): the key is taken in the target workspace
def clash(s, target, own_lid, owner_where, who):
    iid = opened(s, OX, RK)
    j = run(s, iid, target)
    w = (j.get("result") or {}).get("warnings") or []
    check(j.get("state") == "done", f"{who}: import done {j.get('state')} {j.get('error')} {w}")
    rows = sql(f"SELECT id, ticket_key FROM lists WHERE {owner_where[0]} AND name='Bordbuch' AND deleted_at IS NULL", owner_where[1])
    lid = rows[0][0] if rows else 0
    check(lid and rows[0][1] is None, f"#6202 {who}: the imported project came without a key {rows}")
    check(sql("SELECT ticket_key FROM lists WHERE id=?", (own_lid,)) == [("NEW",)], f"#6202 {who}: the target's own project keeps NEW")
    check(lid and sorted(tasks_of(lid).values()) == [("Erster Eintrag", 1), ("Zweiter Eintrag", 2)], f"#6202 {who}: the numbers stay {tasks_of(lid) if lid else rows}")
    check(lid and keys_of(lid) == {("APP", 1): "Erster Eintrag", ("APP", 2): "Zweiter Eintrag", ("NEW", 1): "Erster Eintrag", ("NEW", 2): "Zweiter Eintrag"},
          f"#6202 {who}: NEW-1 / NEW-2 and APP-1 / APP-2 stay as old keys of the moved tasks {keys_of(lid) if lid else rows}")
    ws = [x.get("text") if isinstance(x.get("text"), str) else " ".join(map(str, x.get("text") or [])) for x in w]
    check(any("already used in this workspace" in t and "NEW" in t and "Bordbuch" in t for t in ws), f"#6202 {who}: the import report names the key {ws}")
    t = s.post(B + "/api/tasks", json={"title": "Eigener Eintrag", "list_id": own_lid}).json().get("id")
    check(tasks_of(own_lid).get(t, (None, None))[1] == 2, f"#6202 {who}: the target's own project counts on (NEW-2) {tasks_of(own_lid)}")
    s.delete(B + f"/api/account/import/{iid}")


# another person imports (the same person's second import of the same export loses its tasks to tasks_tt_user, an own task)
DID, Do = freelancer(B, A, name="dora")
DEL = A.post(B + "/api/admin/orgs", json={"name": "Delta Ziel", "admin_id": DID}).json()["id"]
DL = Do.post(B + "/api/lists", json={"name": "Logbuch", "org_id": DEL, "kind": "project"}).json()["id"]
Do.post(B + "/api/tasks", json={"title": "Logbuch Eintrag", "list_id": DL})
check(Do.patch(B + f"/api/lists/{DL}", json={"ticket_key": "NEW"}).ok, "#6202 setup: the target organisation's project has NEW")
clash(Do, DEL, DL, ("org_id=?", (DEL,)), "organisation")

GID, Gr = freelancer(B, A, name="greta")
GL = Gr.post(B + "/api/lists", json={"name": "Werkbank", "kind": "project"}).json()["id"]
Gr.post(B + "/api/tasks", json={"title": "Werkbank Eintrag", "list_id": GL})
check(Gr.patch(B + f"/api/lists/{GL}", json={"ticket_key": "NEW"}).ok, "#6202 setup: the freelancer's private project has NEW")
clash(Gr, "private", GL, ("org_id IS NULL AND owner_id=?", (GID,)), "freelancer")

if FAILS:
    print(subprocess.run(["docker", "logs", "--tail", "80", CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True).stdout[-8000:], flush=True)
print(f"p21198_b: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
