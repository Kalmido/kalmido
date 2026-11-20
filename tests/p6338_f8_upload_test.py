#!/usr/bin/env python3
# kalmido-suite: fresh
# (#6338 F8): an upload of several files to the file store that is refused (one file empty) rolls back its rows AND removes
# the files it already wrote to the disk - before, they stayed until the orphan clean-up (a day later, only with the files
# retention switched on). Checked for a new file and a new version of an existing one, in the private space and in an
# organisation; a good upload afterwards still lands. Invented names only.
import os
import subprocess
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from kt import FAILS, OKS, check, sess, B, DATA  # noqa: E402

if not (os.environ.get("P6338_NOSTART") or os.environ.get("KMT_NOSTART")):
    subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL)


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


ROOT = os.path.join(os.environ.get("TASKS_ATTACHMENTS") or os.path.join(DATA, "attachments"), "files")


def stored():
    """every stored file below <attachments>/files (relative paths)"""
    out = set()
    for d, _, fs in os.walk(ROOT):
        for f in fs:
            out.add(os.path.relpath(os.path.join(d, f), ROOT))
    return out


assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
r = A.post(B + "/api/admin/setup", json={"org_name": "Seed Library Example", "lang": "en", "collab_all": True, "modules": ["comments"]})
check(r.ok, "setup: the organisation " + r.text[:200])
A.patch(B + "/api/settings", json={"features": "files,collab", "lang": "en", "tour": "done"})
ORG = dbx("SELECT id FROM orgs WHERE personal_of IS NULL ORDER BY id LIMIT 1")[0][0]

for space in ("private", f"org:{ORG}"):
    r = A.post(B + "/api/files/folders", json={"name": f"Seed packets {space}", "space": space})
    check(r.status_code == 201, f"{space}: a folder " + r.text[:200])
    F = r.json()["id"]
    r = A.post(B + "/api/files/upload", data={"parent_id": str(F)}, files={"file": ("sowing plan.txt", b"tomatoes in March", "text/plain")})
    check(r.status_code == 201, f"{space}: a first file " + r.text[:200])
    OLD = r.json()["items"][0]["id"]
    before = stored()
    check(len(before) >= 1, f"{space}: the first file is on the disk ({len(before)})")
    # three files in one request: a new version of the existing one, a new file, an empty one (refused: the whole request)
    r = A.post(B + "/api/files/upload", data={"parent_id": str(F)}, files=[
        ("file", ("sowing plan.txt", b"tomatoes in April", "text/plain")),
        ("file", ("harvest list.txt", b"beans, peas", "text/plain")),
        ("file", ("empty.txt", b"", "text/plain"))])
    check(r.status_code == 400, f"{space}: the request with an empty file is refused ({r.status_code} {r.text[:200]})")
    check(not dbx("SELECT 1 FROM fs_nodes WHERE parent_id=? AND name='harvest list.txt'", (F,)), f"{space}: no row of the new file")
    check(dbx("SELECT cur_version FROM fs_nodes WHERE id=?", (OLD,))[0][0] == 1, f"{space}: the existing file keeps its version")
    after = stored()
    check(after == before, f"{space}: no file of the refused request stays on the disk (#6338 F8): {sorted(after - before)}")
    # a good upload afterwards
    r = A.post(B + "/api/files/upload", data={"parent_id": str(F)}, files=[
        ("file", ("harvest list.txt", b"beans, peas", "text/plain")), ("file", ("sowing plan.txt", b"tomatoes in April", "text/plain"))])
    check(r.status_code == 201 and len(r.json().get("items", [])) == 2, f"{space}: a good upload of two files lands " + r.text[:200])
    check(len(stored()) == len(before) + 2 and dbx("SELECT cur_version FROM fs_nodes WHERE id=?", (OLD,))[0][0] == 2,
          f"{space}: its new file and the new version are on the disk")

print(f"p6338_f8_upload_test: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
