#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6581: the organisation export in operation. Invented names only (example.com).
 - free disk space: an organisation whose files would not fit on the disk (a file version marked as huge) is refused with
   507 and a plain text before anything is written; the state stays "none"; with the real size it starts again
 - one organisation export at a time on the instance: while another organisation's export waits in the queue, a second
   one answers 409 with a plain text; a person without an organisation exports their own office all the same (the personal
   office is never held up by a company's export)
 - the end of the run: the starter gets one News item (kind oxdone, row "export" of the notification settings) - ready,
   with the organisation's name; for the own office "own"; with the row "export" switched off for the News nothing is written
freelancer-matrix: office
usage: p6581_orgexport_ops_test.py <datadir>      (a fresh container; P6581_NOSTART=1 = the server already runs)"""
# tenant-matrix: own
import json
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, setup, until  # noqa: E402

fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6581")
A = setup("alice", "Alice Admin")
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": "cal,comments,collab,office,clients,docs,files,wiki", "tour": "done"})
X = A.post(B + "/api/admin/orgs", json={"name": "Alpha Export", "admin_id": ALICE}).json()["id"]
Y = A.post(B + "/api/admin/orgs", json={"name": "Beta Export", "admin_id": ALICE}).json()["id"]


def news(uid):
    return [json.loads(r[0]) if isinstance(r[0], str) else r[0]
            for r in dbx("SELECT data FROM notifications WHERE user_id=? AND kind='oxdone' ORDER BY id", (uid,))]


def wait_done(s, oid):
    st = until(lambda: (lambda j: j if j.get("state") != "running" else None)(s.get(B + f"/api/orgs/{oid}/export").json()), timeout=120)
    return st or {}


# ---------------------------------------------------------------- free disk space
r = A.post(B + "/api/files/folders", json={"name": "Ablage", "space": f"org:{X}"})
check(r.status_code == 201, "a folder in the organisation's store " + r.text[:160])
r = A.post(B + "/api/files/upload", data={"parent_id": str(r.json()["id"])}, files={"file": ("notiz.txt", b"Notiz", "text/plain")})
check(r.ok, "a file in the organisation's store " + r.text[:160])
VER = dbx("SELECT v.id, v.size FROM fs_versions v JOIN fs_nodes n ON n.id=v.node_id WHERE n.org_id=? AND n.name='notiz.txt'", (X,))
check(len(VER) == 1, f"the file has its version {VER}")
dbx("UPDATE fs_versions SET size=? WHERE id=?", (10 ** 17, VER[0][0]))  # 100 PB: no disk has that
r = A.post(B + f"/api/orgs/{X}/export")
check(r.status_code == 507 and "not enough space" in r.text, f"refused before it starts when the files would not fit {r.status_code} {r.text[:160]}")
check(A.get(B + f"/api/orgs/{X}/export").json().get("state") == "none", "nothing started, nothing written")
dbx("UPDATE fs_versions SET size=? WHERE id=?", (VER[0][1], VER[0][0]))

# ---------------------------------------------------------------- one organisation export at a time
# another organisation's export waits in the queue (a row the worker does not take yet)
dbx("INSERT INTO bg_jobs(kind, org_id, user_id, payload, state, run_after, created_at) VALUES('ox:export', ?, ?, '[]', 'wait', '9999-12-31T00:00:00', now())",
    (Y, ALICE))
r = A.post(B + f"/api/orgs/{X}/export")
check(r.status_code == 409 and "Another organisation" in r.text, f"a second organisation export waits for the first {r.status_code} {r.text[:160]}")
FID, F = freelancer(B, A, "frida", features="cal,comments,collab,office,clients")
r = F.put(B + "/api/office/settings", json={"lang": "en", "currency": "EUR", "company_fields": {"name": "Frida Film"}})
check(r.ok, "the self-employed sets up the own office " + r.text[:160])  # the personal office is made on its first use
r = F.post(B + "/api/orgs/0/export")
check(r.status_code == 202, f"the self-employed exports the own office while a company's export waits {r.status_code} {r.text[:160]}")
st = wait_done(F, 0)
check(st.get("state") == "done", f"the own office's export is done {st}")
n = until(lambda: news(FID))
check(n and n[-1].get("what") == "done" and n[-1].get("own") is True and n[-1].get("click") == "office/settings",
      f"the self-employed hears the end, pointed at the office's settings {n}")
dbx("DELETE FROM bg_jobs WHERE kind='ox:export' AND org_id=? AND run_after LIKE '9999%'", (Y,))

# ---------------------------------------------------------------- the end of the run: one News item for the starter
r = A.post(B + f"/api/orgs/{X}/export")
check(r.status_code == 202, f"the organisation export starts once the other is gone {r.status_code} {r.text[:160]}")
st = wait_done(A, X)
check(st.get("state") == "done", f"organisation export done {st}")
n = until(lambda: news(ALICE))
check(len(n) == 1 and n[0].get("what") == "done" and "Alpha Export" in n[0].get("text", "") and n[0].get("own") is False,
      f"the starter hears it is ready, with the organisation's name {n}")
lst = A.get(B + "/api/news").json()
items = lst.get("items", lst) if isinstance(lst, dict) else lst
check(any(isinstance(i, dict) and i.get("kind") == "oxdone" for i in items), "the News list shows it")
# switched off: no News item
check(A.patch(B + "/api/settings", json={"notify": {"export": {"news": 0, "push": 0}}}).ok, "the row export switched off")
r = A.post(B + f"/api/orgs/{X}/export")
check(r.status_code == 202, "exported again " + r.text[:120])
st = wait_done(A, X)
check(st.get("state") == "done" and len(news(ALICE)) == 1, f"no second News item with the row switched off {news(ALICE)}")
check(A.get(B + "/api/state").json().get("notify", {}).get("export") is not None, "the row export is in the notification settings")

sys.exit(done("p6581_orgexport_ops"))
