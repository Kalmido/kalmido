#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6578 (audit #4808 T3): an export says whether another server takes it, an import skips a too large file.
Invented names only (example.com). Own container (kt.fresh) without a server key (plain ZIP archives) and with
KALMIDO_IMPORT_JSON_PART_MAX_MB=1 (a data part above 1 MB is refused by an import here; the export checks against this
server's limits where they are below the standard values); the test containers run with TASKS_MAX_FILE_MB=1, so a file
entry above 4 MB is one the import never reads.
 - a person without an organisation (P4) exports a project with a file: the manifest and the export page say the file fits
   (import_fit ok, import_ok true, no warning)
 - the same archive with the attachment grown to 5 MB (manifest and checksums matching): the preview opens (was: the whole
   file refused as "a part that is too large"), names the file as skipped; the run ends done, the project and its task
   arrive, the result names the file as skipped, nothing of it is stored
 - the task texts grown above 1 MB: the next export names the data part data/tasks.json as too large (manifest import_fit
   ok false, the export page import_ok false with the reason); the import refuses it, as the warning said
 - an organisation export: manifest and export state carry the check (ok); the archive with a stored file named *.json grown
   above the 1 MB data part limit and another file grown above 4 MB opens (was: refused as a data part that is too large),
   the preview names the 5 MB file, the run ends done with both named as skipped and the project arrives
usage: p21442_6578_import_fit_test.py <datadir>"""
# freelancer-matrix: own
import hashlib
import json
import os
import time
import zipfile
from io import BytesIO

import kt
from kt import B, check, sess, su_get
from freelancer_fixture import freelancer

kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_IMPORT_JSON_PART_MAX_MB": "1"})


def ok(r, what):
    check(r.status_code in (200, 201, 202, 204), f"{what}: {r.status_code} {r.text[:200]}")
    return r.json() if r.content else {}


def until_done(s, url):
    j = {}
    for _ in range(960):
        j = s.get(B + url).json()
        if j.get("state") != "running":
            break
        time.sleep(0.25)
    return j


def export_of(s):
    check(s.post(B + "/api/account/export").status_code == 202, "the account export starts")
    j = until_done(s, "/api/account/export")
    check(j.get("state") == "done", f"the account export is done {j}")
    r = su_get(s, B + "/api/account/export/file")
    assert r.ok, r.text[:200]
    return r.content, j


def org_export_of(s, oid):
    check(s.post(B + f"/api/orgs/{oid}/export").status_code == 202, "the organisation export starts")
    j = until_done(s, f"/api/orgs/{oid}/export")
    check(j.get("state") == "done", f"the organisation export is done {j}")
    r = su_get(s, B + f"/api/orgs/{oid}/export/file")
    assert r.ok, r.text[:200]
    return r.content, j


def upload(s, data, name="frida.zip"):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": name})
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


def grown(zdata, repl):
    """The account export with the entries of repl {path: bytes} replaced, manifest and checksums matching."""
    zs = zipfile.ZipFile(BytesIO(zdata))
    files = {n: zs.read(n) for n in zs.namelist() if n not in ("manifest.json", "checksum.sha256")}
    files.update(repl)
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


def org_grown(zdata, repl):
    """The organisation export (plain ZIP) with the entries of repl replaced, its manifest's sizes and checksums matching."""
    zs = zipfile.ZipFile(BytesIO(zdata))
    files = {n: zs.read(n) for n in zs.namelist() if n != "manifest.json"}
    files.update(repl)
    m = json.loads(zs.read("manifest.json"))
    for n, b in repl.items():
        m["files"][n] = {**m["files"][n], "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
        z.writestr("manifest.json", json.dumps(m).encode())
    return out.getvalue()


def stored(name):
    return [f for _d, _s, fs in os.walk(os.path.join(kt.DATA, "attachments")) for f in fs if f.endswith(name)]


def warnings(j):
    return " | ".join(w["text"] for w in (j.get("result") or {}).get("warnings") or [])


# ---------------------------------------------------------------- server, people
kt.setup("alice", "Alice Admin")
A = sess("alice")
ALICE = A.get(B + "/api/state").json()["me"]["id"]
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
check((fit.get("limits") or {}).get("json_part_mb") == 1 and fit["limits"].get("file_mb") == 1, f"checked against this server's lower limits: {fit.get('limits')}")
check(st.get("import_ok") is True and st.get("import_warnings") == [], f"the export page has no warning: {st.get('import_ok')} {st.get('import_warnings')}")

# ---------------------------------------------------------------- one file too large: skipped and named, the rest arrives
path = next(n for n in zipfile.ZipFile(BytesIO(EXP)).namelist() if n.startswith("files/") and n.endswith("riesig.bin"))
iid = upload(G, grown(EXP, {path: os.urandom(5 << 20)}))
j = wait(G, iid)
check(j.get("state") == "preview", f"a too large file no longer refuses the whole file: {j.get('state')} {j.get('error')}")
p = j.get("preview") or {}
check(any("riesig.bin" in x for x in p.get("too_large") or []) and p.get("too_large_mb") == 4, f"the preview names the skipped file: {p.get('too_large')} {p.get('too_large_mb')}")
r = G.post(B + f"/api/account/import/{iid}/run", json={"target": "private", "people": {}, "again": True})
check(r.status_code == 202, f"run starts {r.status_code} {r.text[:200]}")
j = wait(G, iid)
check(j.get("state") == "done", f"the run ends done: {j.get('state')} {j.get('error')}")
warn = warnings(j)
check("riesig.bin" in warn and "too large" in warn, f"the result names the skipped file: {warn}")
row = kt.dbx("SELECT id FROM lists WHERE owner_id=? AND name=? AND deleted_at IS NULL", (GINA, "Gross Projekt"))
check(bool(row), "the project arrived")
if row:
    check(kt.dbx("SELECT COUNT(*) FROM tasks WHERE list_id=? AND title=?", (row[0][0], "Mit Datei"))[0][0] == 1, "its task arrived")
    check(kt.dbx("SELECT COUNT(*) FROM attachments a JOIN tasks t ON t.id=a.task_id WHERE t.list_id=?", (row[0][0],))[0][0] == 0,
          "the too large file is not stored")
check(len(stored("riesig.bin")) == 1, f"only frida's file is on disk: {stored('riesig.bin')}")

# ---------------------------------------------------------------- a data part above the limit: the export warns
for i in range(3):
    t = ok(F.post(B + "/api/tasks", json={"list_id": LP, "title": f"Lang {i}"}), "task")["id"]
    kt.dbx("UPDATE tasks SET content=? WHERE id=?", (os.urandom(250_000).hex(), t))
EXP2, st = export_of(F)
fit = json.loads(zipfile.ZipFile(BytesIO(EXP2)).read("manifest.json")).get("import_fit") or {}
check(fit.get("ok") is False and any(x.get("what") == "json_part" and x.get("path") == "data/tasks.json" for x in fit.get("problems") or []),
      f"the manifest names data/tasks.json as too large: {fit.get('problems')}")
check(st.get("import_ok") is False and any("data/tasks.json" in x and "1 MB" in x for x in st.get("import_warnings") or []),
      f"the export page warns with the reason: {st.get('import_ok')} {st.get('import_warnings')}")
iid = upload(G, EXP2)
j = wait(G, iid)
check(j.get("state") == "invalid" and "tasks.json" in (j.get("error") or ""), f"the import refuses what the export warned of: {j.get('state')} {j.get('error')}")

# ---------------------------------------------------------------- an organisation archive
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha Team", "admin_id": ALICE})
check(r.status_code == 201, f"organisation {r.status_code} {r.text[:160]}")
ORG = r.json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
LO = ok(A.post(B + "/api/lists", json={"name": "Alpha Projekt", "org_id": ORG, "kind": "project"}), "org project")["id"]
TO = ok(A.post(B + "/api/tasks", json={"list_id": LO, "title": "Mit Dateien"}), "org task")["id"]
ok(A.post(B + f"/api/tasks/{TO}/attachments", files={"file": ("notizen.json", b'{"a": 1}', "application/json")}), "a stored file named *.json")
ok(A.post(B + f"/api/tasks/{TO}/attachments", files={"file": ("gross.bin", os.urandom(200 << 10), "application/octet-stream")}), "a file")
OX, st = org_export_of(A, ORG)
ozip = zipfile.ZipFile(BytesIO(OX))
fit = json.loads(ozip.read("manifest.json")).get("import_fit") or {}
check(fit.get("ok") is True, f"the organisation manifest says the file fits: {fit}")
check(st.get("import_ok") is True and st.get("import_warnings") == [], f"the organisation export page has no warning: {st}")
pj = next((n for n in ozip.namelist() if n.startswith("files/") and n.endswith("notizen.json")), None)
pb = next((n for n in ozip.namelist() if n.startswith("files/") and n.endswith("gross.bin")), None)
check(pj and pb, f"both files are in the organisation archive: {pj} {pb}")
if pj and pb:
    iid = upload(A, org_grown(OX, {pj: b'{"x": "' + os.urandom(800 << 10).hex().encode() + b'"}', pb: os.urandom(5 << 20)}), "alpha.zip")
    j = wait(A, iid)
    check(j.get("state") == "preview", f"a stored *.json file above the data part limit and a too large file no longer refuse the archive: {j.get('state')} {j.get('error')}")
    p = j.get("preview") or {}
    check(any("gross.bin" in x for x in p.get("too_large") or []) and not any("notizen.json" in x for x in p.get("too_large") or []),
          f"the preview names only the file above 4 MB: {p.get('too_large')}")
    r = A.post(B + f"/api/account/import/{iid}/run", json={"target": "private", "people": {}, "again": True})
    check(r.status_code == 202, f"organisation archive run starts {r.status_code} {r.text[:200]}")
    j = wait(A, iid)
    check(j.get("state") == "done", f"the organisation archive run ends done: {j.get('state')} {j.get('error')}")
    warn = warnings(j)
    check("gross.bin" in warn and "notizen.json" in warn, f"the result names both skipped files: {warn}")
    check(bool(kt.dbx("SELECT 1 FROM lists WHERE owner_id=? AND org_id IS NULL AND name=? AND deleted_at IS NULL", (ALICE, "Alpha Projekt"))),
          "the organisation's project arrived in the private space")

raise SystemExit(kt.done("p21442_6578_import_fit"))
