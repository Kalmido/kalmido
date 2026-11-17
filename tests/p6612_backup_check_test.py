#!/usr/bin/env python3
# kalmido-suite:
# freelancer-matrix: admin  (the server's backups are the operator's administration; no organisation involved, no new route)
"""2.1338.0 (#6612): the server's own backups and the size limit, the weekly check of the newest backup. Own container
(KALMIDO_BACKUP_MAX_MB=1, attachments of about 1.5 MB, so every own backup is above the limit).
 - an own backup larger than KALMIDO_BACKUP_MAX_MB is checked and downloaded (before: "too large", nothing of it could be
   checked or restored); its downloaded copy uploaded again is still refused, and the text names KALMIDO_BACKUP_MAX_MB
 - the backup page gives the newest backup's unpacked size and the limit (the page warns with them)
 - the button "Check" writes a damaged store file (same size, other bytes) again from its original and says so (repaired)
 - the weekly check (bk_check_at older than 7 days): a damaged store file is written again from the original, the check
   is fine; with the original gone the check fails: the page shows the error and an admin alert "backup:check:hash" goes out
usage: p6612_backup_check_test.py <datadir>        (P6612_NOSTART=1: the server already runs with the settings below)"""
import glob
import hashlib
import io
import os
import sys
import zipfile

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from kt import B, check, docker_logs_on_first_fail, done, fresh, sess, su_get, until  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
BK = os.path.join(DATA, "backups")
ST = os.path.join(BK, ".store")
H = {"X-Requested-With": "kalmido"}
PW = "password123"
docker_logs_on_first_fail(tail=80)

os.environ["KALMIDO_ADMIN_ALERTS"] = "1"  # (start.sh passes it on; its default is 0)
fresh({"KALMIDO_BACKUP_TICK": "1", "KALMIDO_BACKUP_MAX_MB": "1", "KALMIDO_ADMIN_ALERTS": "1", "KALMIDO_ADMIN_ALERT_WINDOW": "3"},
      prefix="P6612", data=DATA)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": PW}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done"})
A.patch(B + "/api/admin/backups", json={"on": False})


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        cur = c.execute(sql, args)
        r = cur.fetchall() if sql.lstrip().upper().startswith("SELECT") else []
        c.commit()
        return r
    finally:
        c.close()


def gset(k, v):
    dbx("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))


def state():
    return A.get(B + "/api/admin/backups").json()


def backup_now():
    before = {x["name"] for x in state()["items"]}
    r = A.post(B + "/api/admin/backups")
    assert r.status_code == 202, r.text
    new = until(lambda: (lambda j: not j["running"] and [x for x in j["items"] if x["name"] not in before])(state()), 60)
    return new[0] if new else {}


BIG1 = b"\x89PNG\r\n" + os.urandom(800 * 1024)   # two shared files, together above the limit of 1 MB
BIG2 = b"%PDF-1.4\n" + os.urandom(700 * 1024)
S1, S2 = hashlib.sha256(BIG1).hexdigest(), hashlib.sha256(BIG2).hexdigest()
L = A.post(B + "/api/lists", json={"name": "Home"}).json()["id"]
T1 = A.post(B + "/api/tasks", json={"title": "with files", "list_id": L}).json()["id"]
for fn, data, ct in (("pic.png", BIG1, "image/png"), ("doc.pdf", BIG2, "application/pdf")):
    r = A.post(B + f"/api/tasks/{T1}/attachments", files={"file": (fn, data, ct)})
    assert r.ok, r.text

x1 = backup_now()
check(x1.get("shared_files") == 2, f"setup: an own backup with two shared files {x1}")
store = {s: os.path.join(ST, "plain", s[:2], s) for s in (S1, S2)}
check(all(os.path.isfile(p) for p in store.values()), "setup: both files lie in the shared store")

# ============================================================== no size limit for own backups
v = A.post(B + f"/api/admin/backups/{x1['name']}/verify", json={})
check(v.ok and v.json().get("attachment_files") == 2 and v.json().get("repaired") == 0 and v.json().get("app_version") and v.json().get("created_at"),
      f"an own backup above KALMIDO_BACKUP_MAX_MB is checked fine (was: too large) {v.status_code} {v.text[:200]}")
j = state()
top = j["items"][0]
check(j["max_mb"] == 1 and top["name"] == x1["name"] and top["unpacked_bytes"] > 1024 * 1024,
      f"the page gets the newest backup's unpacked size above the limit {j['max_mb']} {top.get('unpacked_bytes')}")
r = su_get(A, B + f"/api/admin/backups/{x1['name']}/download")
check(r.ok and len(r.content) > 1024 * 1024, f"the own backup above the limit is downloaded {r.status_code} {r.text[:200] if not r.ok else ''}")
if r.ok:
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        check(sorted(len(z.read(i)) for i in z.infolist() if i.filename.startswith("attachments/")) == sorted([len(BIG1), len(BIG2)]),
              "the download holds both large files")
    up = A.post(B + "/api/admin/backups/upload", data=r.content, headers={"Content-Type": "application/octet-stream"})
    check(up.status_code in (400, 413) and "KALMIDO_BACKUP_MAX_MB" in up.text,
          f"its copy uploaded again stays refused, the text names KALMIDO_BACKUP_MAX_MB {up.status_code} {up.text[:200]}")

# ============================================================== the button "Check" repairs a damaged store file
good1 = open(store[S1], "rb").read()


def damage(p):
    """Other bytes, the same size (what bks.put never looks at again)."""
    b = bytearray(open(p, "rb").read())
    b[len(b) // 2] ^= 0xFF
    open(p, "wb").write(bytes(b))


damage(store[S1])
v = A.post(B + f"/api/admin/backups/{x1['name']}/verify", json={})
check(v.ok and v.json().get("repaired") == 1, f"the check writes the damaged store file again from the original {v.status_code} {v.text[:200]}")
check(open(store[S1], "rb").read() == good1, "the store file has its bytes again")

# ============================================================== the weekly check
damage(store[S2])
gset("bk_check_at", "2020-01-01T00:00:00Z")   # the last check more than a week ago
j = until(lambda: (lambda s: s if s.get("check_ok") or s.get("check_error") else None)(state()), 60)
check(j and j.get("check_ok") and not j.get("check_error"), f"the weekly check runs and is fine after the repair {j and (j.get('check_ok'), j.get('check_error'))}")
check(open(store[S2], "rb").read() == BIG2, "the weekly check wrote the damaged store file again from its original")
check(until(lambda: [r for r in dbx("SELECT key FROM admin_alerts") if r[0] == "backup:repaired"], 20),
      "an admin alert names the repaired file")

# the original is gone: the damage stays, the check fails, the page and an admin alert say so
orig = [p for p in glob.glob(os.path.join(DATA, "attachments", "**", "*"), recursive=True)
        if os.path.isfile(p) and os.path.getsize(p) == len(BIG2) and open(p, "rb").read() == BIG2]
check(len(orig) == 1, f"setup: the original of the second file {orig}")
for p in orig:
    os.remove(p)
damage(store[S2])
gset("bk_check_at", "2020-01-01T00:00:00Z")
j = until(lambda: (lambda s: s if s.get("check_error") else None)(state()), 60)
check(j and "damaged" in (j.get("check_error") or "") and not j.get("check_ok") and j.get("check_name") == x1["name"],
      f"without the original the weekly check fails and the page says so {j and (j.get('check_ok'), j.get('check_error'))}")
check(until(lambda: [r for r in dbx("SELECT key FROM admin_alerts") if r[0] == "backup:check:hash"], 20),
      "the failed check is an admin alert")
at = dbx("SELECT value FROM settings WHERE key='bk_check_at'")
check(at and at[0][0] > "2020-01-02", f"the failed check is tried again (the next day), not every tick {at}")

sys.exit(done("p6612_backup_check_test"))
