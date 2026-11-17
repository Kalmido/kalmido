#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1324.0 D (#6589) API tests: the master data import (POST /api/office/import) says what it does before it overwrites and
never cuts silently. Invented names only.
 - ?preview=1: the counts per area (added / updated) and whether the settings would be overwritten, nothing written
 - the import after the preview writes exactly that
 - an area with more than 5000 entries: the whole file is refused with the area, its number and the limit (was rows[:5000],
   cut silently), nothing written
 - rights (tenant-matrix: office): a member of the organisation 403 on the preview too; a person without an organisation
   (freelancer-matrix: office) previews and imports into her personal office
usage: p21324_d_office_import_test.py <datadir>      (P21324D_NOSTART=1: a running server on KALMIDO_TEST_PORT)"""
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
FEAT = "collab,comments,office,clients"
OFC = "/api/office"

if not os.environ.get("P21324D_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
ALICE = A.get(B + "/api/state").json()["me"]["id"]
Bo = sess("bob")
for s in (A, Bo):
    s.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
for s in (A, Bo):
    s.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})


def services(s):
    return {x["name_de"]: x for x in s.get(B + OFC + "/services").json().get("items", [])}


def run(s, who):
    """The preview, the import and the limit for one office (s's current workspace)."""
    r = s.post(B + OFC + "/services", json={"name_de": "Schnitt", "daily_rate": 400})
    check(r.ok, f"{who}: setup service {r.status_code} {r.text[:200]}")
    d = s.get(B + OFC + "/export").json()
    d["services"] = [{"name_de": "Schnitt", "daily_rate": 999}, {"name_de": "Farbe", "daily_rate": 300}]
    r = s.post(B + OFC + "/import", params={"overwrite": "1", "preview": "1"}, json=d)
    j = r.json() if r.ok else {}
    c = j.get("counts") or {}
    check(r.ok and j.get("preview") is True and j.get("overwrite") is True and c.get("services", {}).get("added") == 1
          and c.get("services", {}).get("updated") == 1 and c.get("settings") == "updated",
          f"{who}: the preview counts one new, one overwritten and the settings {r.status_code} {r.text[:300]}")
    sv = services(s)
    check(sv.get("Schnitt", {}).get("daily_rate") == 400 and "Farbe" not in sv, f"{who}: the preview wrote nothing {sv}")
    r = s.post(B + OFC + "/import", params={"overwrite": "1"}, json=d)
    sv = services(s)
    check(r.ok and r.json()["counts"]["services"] == c["services"] and sv.get("Schnitt", {}).get("daily_rate") == 999
          and sv.get("Farbe", {}).get("daily_rate") == 300, f"{who}: the import writes what the preview said {r.text[:200]} {sv}")
    r = s.post(B + OFC + "/import", params={"preview": "1"}, json=d)
    c2 = (r.json() if r.ok else {}).get("counts") or {}
    check(r.ok and c2.get("services", {}).get("skipped") == 2 and c2.get("settings") == "skipped",
          f"{who}: without overwrite the preview says nothing is overwritten {r.text[:300]}")
    big = {"kalmido_office": 1, "equipment": [{"name": f"Gerät {i}"} for i in range(5001)]}
    for q in ({"preview": "1"}, {}):
        r = s.post(B + OFC + "/import", params=q, json=big)
        msg = (r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}).get("error", "")
        check(r.status_code == 400 and "5001" in msg and "5000" in msg and "Equipment" in msg,
              f"{who}: 5001 devices are refused with the numbers {q} {r.status_code} {msg[:200]}")
    eq = {x["name"] for x in s.get(B + OFC + "/equipment").json().get("items", [])}
    check(not any(n.startswith("Gerät ") for n in eq), f"{who}: the refused file wrote nothing ({len(eq)} devices)")


run(A, "admin")
r = Bo.post(B + OFC + "/import", params={"overwrite": "1", "preview": "1"}, json={"kalmido_office": 1, "services": []})
check(r.status_code == 403, f"a member: 403 on the preview too {r.status_code}")
FID, Fr = freelancer(B, A, features=FEAT)
run(Fr, "freelancer")

print(f"{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
