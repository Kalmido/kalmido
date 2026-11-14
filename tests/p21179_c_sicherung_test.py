#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1179.0 C (#2898): small gaps of the safety net. Invented names only. Starts its OWN test container (start.sh).
 - same_disk_only of /api/admin/backups: the test server keeps its backups next to its data -> true, also before the first
   backup; an off-site target that is on -> false
 - a failing database update at the start (the unique index fs_nodes_ref of 2.199 cannot be built over two nodes of one
   object): exit code 3, one plain FATAL line naming the version and the cause, no traceback; everything is rolled back
   (the column added by the same step before the index is gone again); with the cause gone the same version starts and
   catches up
 - the start removes reference nodes whose object is gone for good (a way back: an older version deleted it without
   knowing the node) and keeps the node of an object in its area's trash and of a live one; the trashed one comes back
   into its folder
 - no new route; the start and the server's backup page have no organisation in them (a person without one)
usage: p21179_c_sicherung_test.py <datadir>"""
import os
import subprocess
import sys
import time

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import check, sess  # noqa: E402

DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
CT = os.environ.get("KALMIDO_TEST_CONTAINER", "kalmido-test")
H = {"X-Requested-With": "kalmido"}


def psql(sql):
    with open(os.path.join(DATA, ".kalmido-db"), encoding="utf-8") as f:
        dbc, dbn = f.read().split()
    r = subprocess.run(["docker", "exec", dbc, "psql", "-U", "kalmido", "-d", dbn, "-v", "ON_ERROR_STOP=1", "-Atqc", sql],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def docker(*a):
    return subprocess.run(["docker", *a], capture_output=True, text=True)


def stopped():
    """(exit code, logs) once the container stopped by itself."""
    t0 = time.time()
    while time.time() - t0 < 120:
        st = docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", CT).stdout.split()
        if st and st[0] == "false":
            r = docker("logs", CT)
            return int(st[1]), r.stdout + r.stderr
        time.sleep(0.5)
    return None, ""


def up():
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            if requests.get(B + "/api/health", timeout=2).ok:
                return True
        except requests.RequestException:
            pass
        if docker("inspect", "-f", "{{.State.Running}}", CT).stdout.strip() == "false":
            return False
        time.sleep(0.5)
    return False


subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL, env=dict(os.environ))
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": kt.PASSWORD}).ok
A = sess("alice")
A.patch(B + "/api/settings", json={"features": "sheets,files", "lang": "en", "tour": "done"})
check(psql("SELECT COUNT(*) FROM orgs WHERE personal_of IS NULL") == "0", "a person without an organisation")


def table(title, folder):
    r = A.post(B + "/api/sheets", json={"title": title, "space": "private", "folder_id": folder})
    assert r.ok, r.text
    return r.json()["id"]


r = A.post(B + "/api/sheets/folders", json={"name": "Reports", "space": "private"})
assert r.ok, r.text
FOLDER = r.json()["folder"]["id"]
GONE, TRASHED, KEPT = table("Gone", FOLDER), table("Trashed", FOLDER), table("Kept", FOLDER)


def nodes():
    rows = psql(f"SELECT ref_id, name FROM fs_nodes WHERE kind='ref' AND ref_kind='sheet' AND parent_id={FOLDER}").splitlines()
    return dict(x.split("|", 1) for x in rows)


check(set(nodes()) == {str(GONE), str(TRASHED), str(KEPT)}, f"three tables filed: {nodes()}")
check(A.delete(B + f"/api/sheets/{TRASHED}").ok, "a table into its area's trash")

# ---- the backups lie on the same disk as the data, no off-site target
j = A.get(B + "/api/admin/backups").json()
check(j.get("same_disk_only") is True, f"backups next to the data, no off-site target (before the first backup too): {j.get('same_disk_only')}")
r = A.post(B + "/api/admin/backups")
check(r.status_code == 202, f"a backup: {r.status_code}")
kt.until(lambda: (lambda x: not x["running"] and x["items"])(A.get(B + "/api/admin/backups").json()), 60)
check(A.get(B + "/api/admin/backups").json()["same_disk_only"] is True, "after the first backup still on the same disk")
psql("""INSERT INTO settings(key,value) VALUES('bko_conf','{"type": "webdav", "on": true}')
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""")
check(A.get(B + "/api/admin/backups").json()["same_disk_only"] is False, "an off-site target that is on: no note")
psql("""UPDATE settings SET value='{"type": "webdav", "on": false}' WHERE key='bko_conf'""")
check(A.get(B + "/api/admin/backups").json()["same_disk_only"] is True, "an off-site target that is off: the note again")

# ---- a database update that cannot finish: the step of 2.199 again, two nodes of one table block its unique index
docker("stop", "-t", "5", CT)
psql(f"DELETE FROM sheets WHERE id={GONE}")  # an older version deleted it; its node stays
psql(f"""DROP INDEX fs_nodes_ref; ALTER TABLE fs_nodes DROP COLUMN sort_no;
         INSERT INTO fs_nodes(parent_id,kind,name,owner_id,org_id,ref_kind,ref_id,created_by,created_at,updated_at)
         SELECT parent_id,kind,'dup1',owner_id,org_id,ref_kind,ref_id,created_by,created_at,updated_at FROM fs_nodes
         WHERE kind='ref' AND ref_kind='sheet' AND ref_id={KEPT}""")
docker("start", CT)
code, logs = stopped()
check(code == 3, f"a failed update ends with exit code 3: {code}")
fatal = [x for x in logs.splitlines() if x.startswith("FATAL: updating the database to version")]
check(len(fatal) == 1 and "Nothing was changed" in fatal[0] and "fs_nodes_ref" in fatal[0] and "previous version" in fatal[0],
      f"one plain line says what happened: {logs[-800:]}")
check("Traceback" not in logs, f"no traceback: {logs[-800:]}")
check(psql("SELECT COUNT(*) FROM information_schema.columns WHERE table_name='fs_nodes' AND column_name='sort_no'") == "0",
      "the column the same step had added is rolled back too")
check(psql("SELECT COUNT(*) FROM pg_indexes WHERE indexname='fs_nodes_ref'") == "0", "no half-built index")

# ---- the cause gone: it starts, catches up, and the dead entry is removed
psql("DELETE FROM fs_nodes WHERE name='dup1'")
docker("start", CT)
check(up(), "the cause gone: it starts")
check(psql("SELECT COUNT(*) FROM pg_indexes WHERE indexname='fs_nodes_ref'") == "1", "the update caught up")
n = kt.until(lambda: (lambda x: str(GONE) not in x and x)(nodes()), 30) or nodes()
check(str(GONE) not in n, f"the node of the table that is gone went: {n}")
check(str(TRASHED) in n and str(KEPT) in n, f"the nodes of a table in the trash and of a live one stay: {n}")
check("folder entries of deleted objects removed" in docker("logs", CT).stdout, "the start says it cleaned up")
check(psql(f"SELECT COUNT(*) FROM fs_nodes WHERE id={FOLDER} AND deleted_at IS NULL") == "1", "the folder itself stays")
A = sess("alice")
check(A.post(B + f"/api/sheets/{TRASHED}/restore").ok, "the trashed table comes back")
check(psql(f"SELECT COUNT(*) FROM fs_nodes WHERE kind='ref' AND ref_kind='sheet' AND ref_id={TRASHED} AND parent_id={FOLDER} "
           "AND deleted_at IS NULL") == "1", "into its folder")
check(A.get(B + f"/api/sheets/{KEPT}").ok, "the live table still opens")

sys.exit(kt.done("p21179_c_sicherung"))
