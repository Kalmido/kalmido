#!/usr/bin/env python3
# kalmido-suite:
# freelancer-matrix: own
"""#6611: a backup on a fresh server (docs/SELF-HOSTING.md "Emergency: restoring a backup on a fresh server").
 1. Old server A (key K_OLD) with an organisation, a sealed file and a private list; a complete backup is downloaded.
    New server B: the first start makes its own key K_NEW, a throwaway admin sets it up. Nothing in its database is sealed
    with a server key (skfp_fresh_blockers is empty). The old key put in place: B starts WITHOUT KALMIDO_SECRET_KEY_CHANGED,
    says so in the log and stores the old key's fingerprint; the restore goes through, the people of the backup sign in
    with their old passwords and the sealed file opens with its bytes.
 2. Now the database holds organisation / account keys: another key (K_NEW) stops the start (FATAL, exit 3) and the
    message names where data lies; nothing changes, the old key starts again.
 3. bkstore.py decrypt: the assembled encrypted backup comes out as the plain zip (passphrase on stdin), the same bytes as
    the download; a wrong passphrase writes nothing, an existing output is never overwritten, a plain zip is refused, a
    format-3 file with shared files says that it has to be assembled first.
usage: p6611_freshkey_test.py <datadir>"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, CT, DATA, OKS, FAILS, PASSWORD, check, sess, su_get, until  # noqa: E402

H = {"X-Requested-With": "kalmido"}
PASSPHRASE = "the passphrase of 6611"
K_OLD, K_NEW = (base64.b64encode(os.urandom(32)).decode() for _ in range(2))
BIG = os.urandom(200 * 1024)   # from 64 KiB on: a shared file of the store
kt.docker_logs_on_first_fail()


def start(key, keep=False):
    """A server through start.sh with the server key in KALMIDO_SECRET_KEY and the fingerprint check on; without keep a NEW
    one (empty data folder and database). -> True when it answered."""
    e = dict(os.environ, EXTRA=f"-e KALMIDO_SECRET_KEY={key} -e TASKS_MAX_FILE_MB=10", KALMIDO_SECRET_KEY_CHANGED="",
             KALMIDO_NO_SECRET_KEY="", START_WAIT_S="120")
    e.pop("KEEP", None)
    if keep:
        e["KEEP"] = "1"
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], env=e, capture_output=True, text=True)
    return r.returncode == 0


def logs():
    r = subprocess.run(["docker", "logs", CT], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return r.stdout


def py(code):
    """A few lines of Python inside the container -> the last JSON line."""
    r = subprocess.run(["docker", "exec", "-i", "-e", "TASKS_WATCHDOG=0", CT, "python", "-c", code], capture_output=True, text=True,
                       timeout=300)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"err": (r.stdout[-300:] + " " + r.stderr[-600:]).strip()}


def fp_of(key_b64):
    return hmac.new(base64.b64decode(key_b64), b"kalmido-server-key-fingerprint-v1", hashlib.sha256).hexdigest()[:32]


DBQ = ("import json\nfrom kalmido.core.config import DATABASE_URL\nfrom kalmido.core.pg import connect_direct\n"
       "from kalmido.core.db import skfp_fresh_blockers\nc = connect_direct(DATABASE_URL)\n"
       "fp = c.execute(\"SELECT value FROM kalmido_meta WHERE key='secret_fp'\").fetchone()\n"
       "print(json.dumps({'fp': fp[0] if fp else None, 'why': skfp_fresh_blockers(c, limit=50)}))")


def new_admin(user):
    s0 = requests.Session()
    s0.headers.update(H)
    assert s0.post(B + "/api/auth/setup", json={"username": user, "display_name": user.title(), "password": PASSWORD}).ok
    s = sess(user)
    s.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
    s.patch(B + "/api/admin/backups", json={"on": False})
    return s


def state(s):
    return s.get(B + "/api/admin/backups").json()


def backup_now(s):
    before = {x["name"] for x in state(s)["items"]}
    r = s.post(B + "/api/admin/backups")
    assert r.status_code == 202, r.text
    new = until(lambda: (lambda j: not j["running"] and [x for x in j["items"] if x["name"] not in before])(state(s)), 90)
    assert new, state(s)
    return new[0]


def bkstore(*args, stdin=None):
    return subprocess.run(["docker", "exec", "-i", CT, "python3", "-I", "/app/kalmido/admin/bkstore.py", *args], input=stdin,
                          capture_output=True, text=True, timeout=300)


# ================================================================== the old server A
check(start(K_OLD), "A: the old server starts with its key")
A = new_admin("alice")
ME = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Altserver", "admin_id": ME}).json()["id"]
LST = A.post(B + "/api/lists", json={"name": "Altserver Projekt", "org_id": ORG, "kind": "project"}).json()["id"]
TASK = A.post(B + "/api/tasks", json={"title": "Schnitt abgeben", "list_id": LST}).json()["id"]
r = A.post(B + f"/api/tasks/{TASK}/attachments", files={"file": ("schnitt.bin", BIG, "application/octet-stream")})
assert r.ok, r.text
ATT = r.json()["attachments"][0]["id"]
PL = A.post(B + "/api/lists", json={"name": "Privat"}).json()["id"]
A.post(B + "/api/tasks", json={"title": "Eigene Notiz", "list_id": PL})
j = py(DBQ)
check(j.get("fp") == fp_of(K_OLD) and "org_keys" in (j.get("why") or []), f"A: its fingerprint, organisation keys sealed with K_OLD {j}")
X = backup_now(A)
DOWN = su_get(A, B + f"/api/admin/backups/{X['name']}/download").content
check(len(DOWN) > len(BIG), f"A: the downloaded backup is complete (holds the shared file) {len(DOWN)}")

# ================================================================== 1. the fresh server B
check(start(K_NEW), "B: the installer's first start with a key of its own")
R = new_admin("setup")
j = py(DBQ)
check(j.get("fp") == fp_of(K_NEW), f"B: the first start stored the fingerprint of its own key {j.get('fp')}")
check(j.get("why") == [], f"B: after the set-up nothing in the database is sealed with a server key {j.get('why')}")
ok = start(K_OLD, keep=True)
lg = logs()
check(ok and "note: the server key (KALMIDO_SECRET_KEY) is another one than at the first start" in lg,
      f"1: the old key on the fresh server: starts without KALMIDO_SECRET_KEY_CHANGED, the log says why ({ok}, {lg[-500:]!r})")
check("FATAL" not in lg, "1: ... no FATAL in the log")
check(py(DBQ).get("fp") == fp_of(K_OLD), "1: ... the old key's fingerprint is stored")
check(start(K_OLD, keep=True) and "another one than at the first start" not in logs(), "1: the next start: the key matches, no note")
R = sess("setup")
r = R.post(B + "/api/admin/backups/upload", data=DOWN, headers={"Content-Type": "application/octet-stream"})
assert r.ok, r.text
up = r.json()["upload"]
r = R.post(B + "/api/admin/backups/restore", json={"password": PASSWORD, "confirm": "RESTORE", "upload": up})
check(r.ok and r.json().get("key_warning") == "", f"1: the backup of the old server is restored without a key warning {r.status_code} {r.text[:240]}")
check(r.ok and r.json().get("relogin") is True, f"1: the throwaway admin is not in the backup: sign in again {r.text[:200]}")
A = sess("alice")
st = A.get(B + "/api/state").json()
names = {x["name"] for x in st["lists"]}
check({"Altserver Projekt", "Privat"} <= names and any(t["title"] == "Schnitt abgeben" for t in st["tasks"]),
      f"1: alice signs in with her old password and sees her lists and tasks {sorted(names)}")
g = A.get(B + f"/api/attachments/{ATT}")
check(g.ok and g.content == BIG, f"1: the sealed file of the organisation opens with its bytes {g.status_code}")
s0 = requests.Session()
s0.headers.update(H)
lr = s0.post(B + "/api/auth/login", json={"username": "setup", "password": PASSWORD})
check(not lr.ok, f"1: the throwaway account is gone {lr.status_code}")

# ================================================================== 2. sealed data: another key stays refused
FP = py(DBQ).get("fp")
ok = start(K_NEW, keep=True)
lg = logs()
check(not ok and "FATAL: the server key (KALMIDO_SECRET_KEY) is not the one this database was used with" in lg
      and "org_keys" in lg, f"2: data sealed with the old key + another key: FATAL as before, naming where ({ok}, {lg[-500:]!r})")
check(start(K_OLD, keep=True), "2: the old key back: starts")
check(py(DBQ).get("fp") == FP == fp_of(K_OLD), "2: the refused start changed nothing (fingerprint)")

# ================================================================== 3. bkstore.py decrypt
A = sess("alice")
check(A.patch(B + "/api/admin/backups", json={"encrypt": True, "passphrase": PASSPHRASE}).ok, "3: encryption on")
E = backup_now(A)
check(E["name"].endswith(".zip.enc") and E.get("shared_files", 0) >= 1, f"3: an encrypted format-3 backup with a shared file {E}")
DOWN3 = su_get(A, B + f"/api/admin/backups/{E['name']}/download").content
a = bkstore("assemble", f"/data/backups/{E['name']}", "/data/backups/.store", "/data/c6611.zip.enc", "--passphrase-file", "-", stdin=PASSPHRASE + "\n")
check(a.returncode == 0, f"3: assemble with the passphrase on stdin {a.returncode} {a.stderr[-300:]}")
d = bkstore("decrypt", "/data/c6611.zip.enc", "/data/p6611.zip", "--passphrase-file", "-", stdin=PASSPHRASE + "\n")
check(d.returncode == 0 and "written: /data/p6611.zip" in d.stdout, f"3: decrypt: the plain zip {d.returncode} {d.stdout[-200:]} {d.stderr[-300:]}")
# the file lies sealed in the data folder (organisation key): the zip holds those very bytes
j = py("import json, zipfile, hashlib, os\nfrom kalmido.core.config import DATABASE_URL\nfrom kalmido.core.pg import connect_direct, system_ctx\n"
       "c = connect_direct(DATABASE_URL)\nwith system_ctx(c):\n"
       f"    p = c.execute('SELECT path FROM attachments WHERE id=?', ({ATT},)).fetchone()[0]\n"
       "z = zipfile.ZipFile('/data/p6611.zip')\nn = z.namelist()\nm = json.loads(z.read('manifest.json'))\n"
       "disk = hashlib.sha256(open('/data/attachments/' + p, 'rb').read()).hexdigest()\n"
       "inzip = hashlib.sha256(z.read('attachments/' + p)).hexdigest() if 'attachments/' + p in n else ''\n"
       "print(json.dumps({'dump': 'kalmido.dump' in n, 'fv': m.get('format_version'), 'same': bool(inzip) and inzip == disk,"
       " 'mode': oct(os.stat('/data/p6611.zip').st_mode & 0o777)}))")
check(j.get("dump") and j.get("fv") == 2 and j.get("same") is True,
      f"3: the plain zip holds the dump and the large file with the bytes of the data folder {j}")
check(j.get("mode") == "0o600", f"3: the plain zip is readable for its owner only {j.get('mode')}")
dl = bkstore("decrypt", "/data/backups/" + E["name"], "/data/q6611.zip", "--passphrase-file", "-", stdin=PASSPHRASE + "\n")
check(dl.returncode == 3 and "assemble" in dl.stderr, f"3: a format-3 file with shared files: says assemble first {dl.returncode} {dl.stderr[-300:]}")
w = bkstore("decrypt", "/data/c6611.zip.enc", "/data/w6611.zip", "--passphrase-file", "-", stdin="not the passphrase\n")
check(w.returncode == 1 and "nothing written" in w.stderr, f"3: a wrong passphrase: refused {w.returncode} {w.stderr[-200:]}")
check(py("import json, os\nprint(json.dumps({'x': os.path.exists('/data/w6611.zip')}))").get("x") is False, "3: ... and no file is left")
again = bkstore("decrypt", "/data/c6611.zip.enc", "/data/p6611.zip", "--passphrase-file", "-", stdin=PASSPHRASE + "\n")
check(again.returncode == 2 and "exists" in again.stderr, f"3: an existing output is never overwritten {again.returncode} {again.stderr[-200:]}")
pl = bkstore("decrypt", "/data/p6611.zip", "/data/r6611.zip", "--passphrase-file", "-", stdin=PASSPHRASE + "\n")
check(pl.returncode == 1 and "not an encrypted" in pl.stderr, f"3: a plain zip is refused {pl.returncode} {pl.stderr[-200:]}")
np = bkstore("decrypt", "/data/c6611.zip.enc", "/data/s6611.zip")
check(np.returncode == 2 and "--passphrase-file" in np.stderr, f"3: without a passphrase file: says what is needed {np.returncode} {np.stderr[-200:]}")
check(len(DOWN3) > len(BIG), "3: (the download of the same backup is complete as well)")

print(f"p6611_freshkey: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
