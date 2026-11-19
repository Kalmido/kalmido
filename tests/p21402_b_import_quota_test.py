#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1402.0 B (#6579): the organisation import counts the storage of the TARGET organisation, all or nothing.
Invented names only (example.com). Hosting with 1 MB per person, pool "org" (members x quota):
 - organisation "Quelle" (alice admin, bob, carol): bob uploads two files of 600 KB to an organisation project; alice exports it
 - alice imports it into the fresh organisation "Ziel" (alice alone: pool 1 MB): the preview names the target as too small
   (need, free, missing); the upload itself was no quota question; the private space (pool of "Quelle", 3 MB) fits
 - the start into "Ziel" without inviting anybody: 409 quota_exceeded with what is missing and the way, nothing created
 - with bob ticked (invited to "Ziel": he joins its pool once he accepts, 2 MB) the run starts; a quota cut while the run
   writes rolls everything back (state failed, no project, no file on disk, no import record, no invitation)
 - with room: every file comes (no file left out, state done, no "stopped")
 - review F1: two keys of the file sent with one account's user name count as ONE invited seat
 - a person without an organisation (P4): her account import against her own storage, before the preview
Starts its OWN container (kt.fresh) with a short wait per imported file (KALMIDO_TEST_UMZ_FILE_DELAY, tests only).
usage: p21402_b_import_quota_test.py <datadir>"""
# freelancer-matrix: own
import base64
import os
import time

import kt
from kt import B, check, sess, su_get
from freelancer_fixture import freelancer

KEY = base64.b64encode(os.urandom(32)).decode()
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_SECRET_KEY": KEY, "KALMIDO_TEST_UMZ_FILE_DELAY": "0.6"})
FILE = 600 << 10  # below the 1 MB per file of the tests; random, so it does not compress


def upload(s, data, name="quelle.kalmido-export"):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": name})
    check(r.ok, f"the upload starts (no quota question) {r.status_code} {r.text[:160]}")
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
    return iid, j.get("preview") or {}


def go(s, iid, target, people=None):
    return s.post(B + f"/api/account/import/{iid}/run", json={"again": True, "target": target, "people": people or {}})


def zlists():
    return kt.dbx("SELECT id FROM lists WHERE org_id=? AND deleted_at IS NULL", (ZIEL,))


def disk_files():
    out = set()
    for root, _d, fs in os.walk(os.path.join(kt.DATA, "attachments")):
        out |= {os.path.join(root, f) for f in fs}
    return out


s0 = sess()
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Umzug", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + f"/api/users/{ALICE}", json={"email": "alice@example.com"})
ids = {}
for u, n in (("bob", "Bob Mitglied"), ("carol", "Carol Mitglied")):
    r = A.post(B + "/api/users", json={"username": u, "display_name": n, "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    ids[u] = r.json()["id"]
Bo = sess("bob")
for s in (A, Bo):
    s.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
QUELLE = A.post(B + "/api/admin/orgs", json={"name": "Quelle", "admin_id": ALICE}).json()["id"]
for u in ("bob", "carol"):
    assert A.put(B + f"/api/orgs/{QUELLE}/members", json={"email": f"{u}@example.com", "role": "member"}).ok
ZIEL = A.post(B + "/api/admin/orgs", json={"name": "Ziel", "admin_id": ALICE}).json()["id"]
check(QUELLE < ZIEL, "setup: Quelle is alice's first organisation")
A.patch(B + "/api/settings", json={"workspace": f"org:{QUELLE}"})
L = A.post(B + "/api/lists", json={"name": "Quelle Projekt", "org_id": QUELLE}).json()["id"]
check(A.put(B + f"/api/lists/{L}/members", json={"user_id": ids["bob"], "role": "edit"}).ok, "setup: bob in the project")
T = A.post(B + "/api/tasks", json={"list_id": L, "title": "Mit Dateien"}).json()["id"]
check(A.patch(B + "/api/admin/settings", json={"storage_quota_mb": 1, "storage_pool": "org"}).ok, "setup: 1 MB per person, pool organisation")
for i in range(2):
    r = Bo.post(B + f"/api/tasks/{T}/attachments", files={"file": (f"gross{i}.bin", os.urandom(FILE), "application/octet-stream")})
    check(r.status_code in (200, 201), f"setup: bob's file {i} in the pool of Quelle (3 MB) {r.status_code} {r.text[:160]}")

r = A.post(B + f"/api/orgs/{QUELLE}/export")
check(r.status_code == 202, f"the export starts {r.text[:120]}")
for _ in range(960):
    if A.get(B + f"/api/orgs/{QUELLE}/export").json().get("state") != "running":
        break
    time.sleep(0.25)
OX = su_get(A, B + f"/api/orgs/{QUELLE}/export/file").content
RK = A.post(B + f"/api/orgs/{QUELLE}/encryption/recovery", json={"password": "password123"}).json().get("recovery_key", "")
check(OX[:13] == b"KALMIDO-ORGX\n" and RK, "the organisation export + its recovery key")

# ------------------------------------------------------------ the preview names the target that is too small
iid, pv = opened(A, OX, RK)
st = pv.get("storage") or {}
zt = (st.get("targets") or {}).get(str(ZIEL)) or {}
check(st.get("need", 0) >= 2 * FILE and zt.get("free") == 1 << 20 and zt.get("missing") == st.get("need", 0) - (1 << 20)
      and "are missing" in (zt.get("text") or "") and "operator" in (zt.get("text") or ""),
      f"#6579 the preview: Ziel (alice alone, 1 MB) is short by the missing amount, with the way {st}")
check("private" not in (st.get("targets") or {}), f"#6579 the private space (pool of Quelle, 3 MB, 1.2 MB used) fits {st}")

# ------------------------------------------------------------ the start without invitations: refused, nothing created
r = go(A, iid, ZIEL)
e = r.json() if r.content else {}
check(r.status_code == 409 and e.get("code") == "quota_exceeded" and e.get("missing") == zt.get("missing") and "operator" in (e.get("error") or ""),
      f"#6579 the start into Ziel without invitations: 409 with what is missing and the way {r.status_code} {e}")
check(not zlists() and A.get(B + f"/api/account/import/{iid}").json().get("state") == "preview", "#6579 nothing created, the preview stays")

# ------------------------------------------------------------ bob invited (joins the pool of Ziel): fits; cut in the run -> rollback
before = disk_files()
bob_key = [x["key"] for x in pv.get("people") or [] if x.get("name") == "Bob Mitglied"]
check(len(bob_key) == 1 and next(x for x in pv["people"] if x["key"] == bob_key[0]).get("found"), f"bob found in the preview {pv.get('people')}")
r = go(A, iid, ZIEL, {k: {"share": True, "role": "member"} for k in bob_key})
check(r.status_code == 202, f"#6579 with bob invited the pool of Ziel is 2 MB: the run starts {r.status_code} {r.text[:200]}")
check(A.patch(B + f"/api/users/{ALICE}", json={"storage_quota_mb": 1}).ok, "the quota cut while the run writes (alice: 1 MB of her own)")
j = wait(A, iid)
err = str(j.get("error") or "")
check(j.get("state") == "failed" and "nothing was imported" in err and "operator" in err, f"#6579 the run over the limit fails as a whole {j.get('state')} {err[:300]}")
check(not zlists(), "#6579 rolled back: no project in Ziel")
check(not kt.dbx("SELECT 1 FROM imports WHERE user_id=?", (ALICE,)) and not kt.dbx("SELECT 1 FROM org_joins WHERE org_id=?", (ZIEL,)),
      "#6579 rolled back: no import record, no invitation")
check(disk_files() == before, f"#6579 no file of the run stays on disk {sorted(disk_files() - before)[:3]}")
check(A.patch(B + f"/api/users/{ALICE}", json={"storage_quota_mb": None}).ok, "alice back on the server default")

# ------------------------------------------------------------ with room: every file comes
iid, pv = opened(A, OX, RK)
bob_key = [x["key"] for x in pv.get("people") or [] if x.get("name") == "Bob Mitglied"]
check(len(bob_key) == 1, f"bob in the preview {[x.get('name') for x in pv.get('people') or []]}")
r = go(A, iid, ZIEL, {bob_key[0]: {"share": True, "role": "member"}})
check(r.status_code == 202, f"#6579 the run starts {r.status_code} {r.text[:200]}")
j = wait(A, iid)
res = j.get("result") or {}
n = kt.dbx("SELECT COUNT(*) FROM attachments a JOIN tasks t ON t.id=a.task_id JOIN lists l ON l.id=t.list_id WHERE l.org_id=? AND a.deleted_at IS NULL", (ZIEL,))[0][0]
check(j.get("state") == "done" and not res.get("stopped") and n == 2, f"#6579 every file came {j.get('state')} {n} {res.get('warnings')}")
check(kt.dbx("SELECT 1 FROM org_joins WHERE org_id=? AND user_id=?", (ZIEL, ids["bob"])), "#6579 bob invited to Ziel (joins its pool on accepting)")

# ------------------------------------------------------------ review F1 (job/5521): invitations counted per account, not per key
# alice now carries the 1.2 MB of the run above; Ziel with one invitation = 2 MB: 1.2 + 1.2 do not fit, with two would (3 MB).
# carol's address changes, so her key of the file finds nobody; the client sends it with bob's user name: still ONE seat.
check(A.patch(B + f"/api/users/{ids['carol']}", json={"email": "carol.neu@example.com"}).ok, "setup: carol's key finds nobody any more")
iid, pv = opened(A, OX, RK)
keys = {x.get("name"): x["key"] for x in pv.get("people") or []}
check("Bob Mitglied" in keys and "Carol Mitglied" in keys, f"bob and carol in the preview {list(keys)}")
r = go(A, iid, ZIEL, {keys["Bob Mitglied"]: {"share": True, "role": "member"},
                      keys["Carol Mitglied"]: {"share": True, "login": "bob", "role": "member"}})
e = r.json() if r.content else {}
check(r.status_code == 409 and e.get("code") == "quota_exceeded",
      f"review F1: two keys with one account are one seat in the pool, the start is refused {r.status_code} {e}")
check(A.patch(B + f"/api/users/{ids['carol']}", json={"email": "carol@example.com"}).ok, "carol's address back")

# ------------------------------------------------------------ P4: a person without an organisation, her own storage
check(A.patch(B + "/api/admin/settings", json={"storage_pool": "user"}).ok, "pool per person again")
FID, Fr = freelancer(B, A, "frida")
HID, Hn = freelancer(B, A, "hanna")
LF = Fr.post(B + "/api/lists", json={"name": "Frida Projekt"}).json()["id"]
TF = Fr.post(B + "/api/tasks", json={"list_id": LF, "title": "Datei"}).json()["id"]
check(Fr.post(B + f"/api/tasks/{TF}/attachments", files={"file": ("f.bin", os.urandom(FILE), "application/octet-stream")}).status_code in (200, 201), "frida's file")
check(Fr.post(B + "/api/account/export").status_code == 202, "frida's export starts")
for _ in range(480):
    if Fr.get(B + "/api/account/export").json().get("state") != "running":
        break
    time.sleep(0.25)
EXP = su_get(Fr, B + "/api/account/export/file").content
LH = Hn.post(B + "/api/lists", json={"name": "Hanna Projekt"}).json()["id"]
TH = Hn.post(B + "/api/tasks", json={"list_id": LH, "title": "Voll"}).json()["id"]
check(Hn.post(B + f"/api/tasks/{TH}/attachments", files={"file": ("h.bin", os.urandom(FILE), "application/octet-stream")}).status_code in (200, 201),
      "hanna's own file: 600 KB of 1 MB")
iid = upload(Hn, EXP, "frida.zip")
j = wait(Hn, iid)
err = str(j.get("error") or "")
check(j.get("state") == "invalid" and "are missing" in err and "operator" in err, f"#6579 P4: too small before the preview, with what is missing {j.get('state')} {err[:300]}")
check(not kt.dbx("SELECT 1 FROM lists WHERE owner_id=? AND name='Frida Projekt'", (HID,)), "#6579 P4: nothing created")

raise SystemExit(kt.done("p21402_b_import_quota"))
