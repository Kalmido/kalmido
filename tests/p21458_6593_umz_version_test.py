#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1458.0 (#6593, audit #4808 T21): the versions of a move. Invented names only (example.com). Crafted account exports:
 - a file of a newer Kalmido version is refused with the version to update to (an own server; the hosted one lets it through
   and names what it does not know); an older file and one without a readable version come in as before
 - a row whose required field has no valid value (a habit without a name) is counted per area and named in the result
 - the double-import guard follows the fixed key of the server (manifest source.instance), not its address: two own servers
   with the default address and the same account id are two sources; a file of the same server is the same source; a file of
   an older writer (no key) still comes in
 - the guard holds per target organisation: a second admin importing the same file into the same organisation is asked first
 - the server's own export carries its key (32 hex characters)
Starts its OWN container (start.sh) with KALMIDO_SECRET_KEY (P6593_NOSTART=1 = the server already runs like that).
freelancer-matrix: own
usage: p21458_6593_umz_version_test.py <datadir>"""
import base64
import hashlib
import io
import json
import os
import sys
import zipfile

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check, until  # noqa: E402
from freelancer_fixture import freelancer, org_join  # noqa: E402

KEY = base64.b64encode(os.urandom(32)).decode()
TS = "2026-10-20T06:00:00Z"
ME = 1000
HERE = "http://localhost:3040"  # the default address of an own server
INST_A, INST_B = "a" * 32, "b" * 32


def sha(b):
    return hashlib.sha256(b).hexdigest()


def mkzip(tables, version="test", inst=None, url=HERE):
    entries = {f"data/{t}.json": json.dumps(rows).encode() for t, rows in tables.items()}
    flist = [{"path": p, "size": len(b), "sha256": sha(b)} for p, b in entries.items()]
    src = {"url": url, "hosted": False, **({"instance": inst} if inst else {})}
    m = {"format": "kalmido-account", "v": 1, "kalmido_version": version, "created_at": TS, "source": src,
         "user": {"id": ME, "name": "Test Person", "email": "test@example.com"},
         "tables": {t: len(r) for t, r in tables.items()}, "files": flist, "client_encrypted": {}, "export_id": os.urandom(16).hex()}
    mb = json.dumps(m).encode()
    cs = f"{sha(mb)}  manifest.json\n" + "".join(f"{f['sha256']}  {f['path']}\n" for f in flist)
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", mb)
        z.writestr("checksum.sha256", cs.encode())
        for p, b in entries.items():
            z.writestr(p, b)
    return bio.getvalue()


def state_of(s, iid):
    j = s.get(B + f"/api/account/import/{iid}").json()
    return j if j.get("state") not in ("checking", "running", "upload") else None


def upload(s, data):
    r = s.post(B + "/api/account/import", json={"size": len(data), "name": "kalmido-account.zip"})
    assert r.ok, r.text
    iid, off = r.json()["id"], 0
    while off < len(data):
        part = data[off:off + (1 << 20)]
        r = s.put(B + f"/api/account/import/{iid}?offset={off}", data=part, headers={"Content-Type": "application/octet-stream"})
        assert r.ok, r.text
        off += len(part)
    return iid, until(lambda: state_of(s, iid), 300) or {}


def start(s, iid, target="private", again=False):
    return s.post(B + f"/api/account/import/{iid}/run", json={"target": target, "people": {}, **({"again": True} if again else {})})


def run(s, iid, target="private", again=False):
    r = start(s, iid, target, again)
    check(r.status_code == 202, f"the run starts {r.status_code} {r.text[:200]}")
    return until(lambda: state_of(s, iid), 300) or {}


def again(j):
    return bool((j.get("preview") or {}).get("again"))


def one(sql, args=()):
    r = kt.dbx(sql, args)
    return r[0][0] if r else None


HABITS = {"habits": [{"id": 31, "name": "Umzug Laufen", "goal": 1, "created_at": TS},
                     {"id": 32, "name": None, "goal": 1, "created_at": TS}]}  # no valid name: left out, counted

kt.fresh(env={"KALMIDO_SECRET_KEY": KEY, "KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6593")
A = kt.setup()
VER = (A.get(B + "/api/about").json() or {}).get("version") or ""
check(VER.count(".") == 2, f"the server names its version {VER!r}")
major, minor, patch = (int(x) for x in VER.split("."))

# ---------------------------------------------------------------- the version of the file
GID, Gi = freelancer(B, A, "gina")
NEWER = f"{major}.{minor + 1}.0"
iid, j = upload(Gi, mkzip(HABITS, version=NEWER, inst=INST_A))
err = " ".join(str(x) for x in (j.get("error") if isinstance(j.get("error"), list) else [j.get("error") or ""]))
check(j.get("state") == "invalid" and NEWER in err and "Update this server" in err,
      f"a file of a newer version is refused with the version to update to {j.get('state')} {err!r}")
iid, j = upload(Gi, mkzip(HABITS, version="test", inst=INST_A))
check(j.get("state") == "preview", f"a file without a readable version comes in as before {j.get('state')} {j.get('error')}")
iid, j = upload(Gi, mkzip(HABITS, version=f"{major}.{max(minor - 1, 0)}.0", inst=INST_A))  # (one upload per person at a time)
check(j.get("state") == "preview", f"a file of an older version comes in {j.get('state')} {j.get('error')}")

# ---------------------------------------------------------------- the rows left out are counted
j = run(Gi, iid)
check(j.get("state") == "done", f"the import is done {j.get('state')} {j.get('error')}")
TXT = [w.get("text", "") for w in (j.get("result") or {}).get("warnings") or []]
check(one("SELECT COUNT(*) FROM habits WHERE user_id=? AND name='Umzug Laufen'", (GID,)) == 1, "the valid habit came")
check(any(t.startswith("1 entries in Habits have no valid value in a required field") for t in TXT),
      f"the habit without a name is counted and named {TXT}")

# ---------------------------------------------------------------- the source is the server's key, not its address
iid, j = upload(Gi, mkzip(HABITS, version="test", inst=INST_B))
check(j.get("state") == "preview" and not again(j),
      f"another own server with the same address and account id is another source {j.get('state')} {again(j)}")
iid, j = upload(Gi, mkzip(HABITS, version="test", inst=INST_A))
check(again(j), "a newer file of the same server and account is the same source")
check(start(Gi, iid).status_code == 409, "without the confirmation no second run")

# a file of an older writer (no key): comes in; imported before the key, a file of the same server with the key finds it
HID, Hi = freelancer(B, A, "hugo")
iid, j = upload(Hi, mkzip(HABITS, version="test"))
check(j.get("state") == "preview", f"a file without the server's key comes in {j.get('state')} {j.get('error')}")
check(run(Hi, iid).get("state") == "done", "... and is imported")
iid, j = upload(Hi, mkzip(HABITS, version="test", inst=INST_A))
check(again(j), "a file of the same server with its key finds the import made before the key (the address key)")

# ---------------------------------------------------------------- per target organisation, not per person
# alice (the instance admin) creates it and is its first admin; she makes otto admin too
TID, Ot = freelancer(B, A, "otto")
r = A.post(B + "/api/admin/orgs", json={"name": "Umzug Team"})
check(r.ok, f"the organisation {r.status_code} {r.text[:200]}")
ORG = (r.json() or {}).get("id")
r = A.put(B + f"/api/orgs/{ORG}/members", json={"email": "otto@example.com", "role": "admin"})
if one("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, TID)) is None:
    org_join(B, "otto", ORG)
check(one("SELECT role FROM org_members WHERE org_id=? AND user_id=?", (ORG, TID)) == "admin", f"otto is admin too {r.status_code} {r.text[:200]}")
Ol = A
FILE = mkzip(HABITS, version="test", inst=INST_A)
iid, j = upload(Ol, FILE)
check(j.get("state") == "preview" and not again(j), f"alice's first upload is new {j.get('state')}")
check(run(Ol, iid, target=ORG).get("state") == "done", "alice imports into the organisation")
iid, j = upload(Ot, FILE)
check(again(j), "otto, admin of the same organisation, sees the import of the file there")
check(start(Ot, iid, target=ORG).status_code == 409, "into the same organisation only with the confirmation")
j = run(Ot, iid, target="private")
check(j.get("state") == "done", f"into his private space it is a copy, no question {j.get('state')} {j.get('error')}")

# ---------------------------------------------------------------- the server's own export carries its key
ok_ = Gi.post(B + "/api/account/export").ok
st = until(lambda: (lambda x: x if x.get("state") != "running" else None)(Gi.get(B + "/api/account/export").json()), 240) or {}
check(ok_ and st.get("state") == "done", f"the export is done {st.get('state')}")
raw = kt.su_get(Gi, B + "/api/account/export/file").content
man = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("manifest.json"))
inst = (man.get("source") or {}).get("instance") or ""
check(len(inst) == 32 and all(ch in "0123456789abcdef" for ch in inst), f"the manifest carries the server's key {inst!r}")
check(inst == one("SELECT value FROM settings WHERE key='instance_key'"), "... the one the server made once")
sys.exit(kt.done("p21458_6593_umz_version"))
