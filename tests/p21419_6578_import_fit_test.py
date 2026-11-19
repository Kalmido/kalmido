#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1419.0 (#6578, audit #4808 T3): an export says whether another server takes it, an import skips a too large file.
Invented names only (example.com). Own container (start.sh) with KALMIDO_IMPORT_JSON_PART_MAX_MB=1 (a data part above 1 MB
is refused by an import here; the export checks against this server's limits where they are below the standard values);
the test containers run with TASKS_MAX_FILE_MB=1, so a file entry above 4 MB is one the import never reads.
 - a person without an organisation (P4) exports a project with a file: the manifest and the export page say the file fits
   (import_fit ok, import_ok true, no warning)
 - the same file with the attachment grown to 5 MB (manifest and checksums matching): the preview opens (was: the whole
   file refused as "a part that is too large"), names the file as skipped; the run ends done, the project and its task
   arrive, the result names the file as skipped, nothing of it is stored
 - the task texts grown above 1 MB: the next export names the data part data/tasks.json as too large (manifest import_fit
   ok false, the export page import_ok false with the reason)
usage: p21419_6578_import_fit_test.py <datadir>"""
# freelancer-matrix: own
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from io import BytesIO

import requests

import dbx as dbxm
from freelancer_fixture import freelancer
from kt import FAILS, OKS, check, sess, su_get

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}


def ok(r, what):
    check(r.status_code in (200, 201, 202, 204), f"{what}: {r.status_code} {r.text[:200]}")
    return r.json() if r.content else {}


def db():
    return dbxm.connect(DATA)


def export_of(s):
    assert s.post(B + "/api/account/export").status_code == 202
    j = {}
    for _ in range(480):
        j = s.get(B + "/api/account/export").json()
        if j.get("state") != "running":
            break
        time.sleep(0.25)
    assert j.get("state") == "done", j
    r = su_get(s, B + "/api/account/export/file")
    assert r.ok, r.text[:200]
    return r.content, j


def upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "frida.zip"})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return iid


def wait(s, iid):
    j = {}
    for _ in range(960):
        j = s.get(B + f"/api/account/import/{iid}").json()
        if j.get("state") not in ("checking", "running", "upload"):
            return j
        time.sleep(0.25)
    return j


def grown(zdata, path, data):
    """The export with the entry path replaced by data, manifest and checksums matching."""
    zs = zipfile.ZipFile(BytesIO(zdata))
    files = {n: zs.read(n) for n in zs.namelist() if n not in ("manifest.json", "checksum.sha256")}
    files[path] = data
    m = json.loads(zs.read("manifest.json"))
    m["files"] = [{"path": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()]
    mb = json.dumps(m).encode()
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
        z.writestr("manifest.json", mb)
        z.writestr("checksum.sha256", "\n".join(f"{hashlib.sha256(b).hexdigest()}  {n}" for n, b in [("manifest.json", mb), *files.items()]) + "\n")
    return out.getvalue()


def stored(name):
    return [f for d, _s, fs in os.walk(os.path.join(DATA, "attachments")) for f in fs if f.endswith(name)]


# ---------------------------------------------------------------- server, people
env = dict(os.environ, EXTRA=(os.environ.get("EXTRA", "") + " -e KALMIDO_IMPORT_JSON_PART_MAX_MB=1").strip())
r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=env, capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
FRIDA, F = freelancer(B, A, "frida")
GINA, G = freelancer(B, A, "gina")

LP = ok(F.post(B + "/api/lists", json={"name": "Gross Projekt", "kind": "project"}), "project")["id"]
T1 = ok(F.post(B + "/api/tasks", json={"list_id": LP, "title": "Mit Datei"}), "task")["id"]
ok(F.post(B + f"/api/tasks/{T1}/attachments", files={"file": ("riesig.bin", os.urandom(300 << 10), "application/octet-stream")}), "a file")

# ---------------------------------------------------------------- an export that fits
EXP, st = export_of(F)
man = json.loads(zipfile.ZipFile(BytesIO(EXP)).read("manifest.json"))
fit = man.get("import_fit") or {}
check(fit.get("ok") is True and not fit.get("problems") and not fit.get("big_files"), f"the manifest says the file fits: {fit}")
check(fit.get("limits", {}).get("json_part_mb") == 1 and fit["limits"].get("file_mb") == 1, f"checked against this server's lower limits: {fit.get('limits')}")
check(st.get("import_ok") is True and st.get("import_warnings") == [], f"the export page has no warning: {st.get('import_ok')} {st.get('import_warnings')}")

# ---------------------------------------------------------------- one file too large: skipped and named, the rest arrives
path = next(n for n in zipfile.ZipFile(BytesIO(EXP)).namelist() if n.startswith("files/attachments/") and n.endswith("riesig.bin"))
iid = upload(G, grown(EXP, path, os.urandom(5 << 20)))
j = wait(G, iid)
check(j.get("state") == "preview", f"#6578: a too large file no longer refuses the whole file: {j.get('state')} {j.get('error')}")
p = j.get("preview") or {}
check(any("riesig.bin" in x for x in p.get("too_large") or []) and p.get("too_large_mb") == 4, f"the preview names the skipped file: {p.get('too_large')} {p.get('too_large_mb')}")
r = G.post(B + f"/api/account/import/{iid}/run", json={"target": "private", "people": {}, "again": True})
check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
j = wait(G, iid)
check(j.get("state") == "done", f"the run ends done: {j.get('state')} {j.get('error')}")
warn = " | ".join(w["text"] for w in (j.get("result") or {}).get("warnings") or [])
check("riesig.bin" in warn and "too large" in warn, f"the result names the skipped file: {warn}")
row = db().execute("SELECT id FROM lists WHERE owner_id=? AND name=? AND deleted_at IS NULL", (GINA, "Gross Projekt")).fetchone()
check(row is not None, "the project arrived")
if row:
    check(db().execute("SELECT COUNT(*) FROM tasks WHERE list_id=? AND title=?", (row[0], "Mit Datei")).fetchone()[0] == 1, "its task arrived")
    check(db().execute("SELECT COUNT(*) FROM attachments a JOIN tasks t ON t.id=a.task_id WHERE t.list_id=?", (row[0],)).fetchone()[0] == 0,
          "the too large file is not stored")
check(len(stored("riesig.bin")) == 1, f"only frida's file is on disk: {stored('riesig.bin')}")

# ---------------------------------------------------------------- a data part above the limit: the export warns
for i in range(3):
    t = ok(F.post(B + "/api/tasks", json={"list_id": LP, "title": f"Lang {i}"}), "task")["id"]
    db().execute("UPDATE tasks SET content=? WHERE id=?", (os.urandom(250_000).hex(), t))
EXP2, st = export_of(F)
fit = json.loads(zipfile.ZipFile(BytesIO(EXP2)).read("manifest.json")).get("import_fit") or {}
check(fit.get("ok") is False and any(x.get("what") == "json_part" and x.get("path") == "data/tasks.json" for x in fit.get("problems") or []),
      f"the manifest names data/tasks.json as too large: {fit.get('problems')}")
check(st.get("import_ok") is False and any("data/tasks.json" in x and "1 MB" in x for x in st.get("import_warnings") or []),
      f"the export page warns with the reason: {st.get('import_ok')} {st.get('import_warnings')}")
# the same file here: the import refuses it, as the warning said
iid = upload(G, EXP2)
j = wait(G, iid)
check(j.get("state") == "invalid" and "tasks.json" in (j.get("error") or ""), f"the import refuses what the export warned of: {j.get('state')} {j.get('error')}")

print(f"p21419_6578_import_fit: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
