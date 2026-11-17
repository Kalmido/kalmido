#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1340.0 API tests (#6613, audit #4818 F4): the organisation roles accounting / read-only, own container (start.sh).
Invented names only, addresses @example.com. tenant-matrix: org (every check runs inside one organisation).
 1 documents: accounting sees in the organisation's documents folder only the receipts (files with an rc_receipts row) and
   its own uploads -- not a member's contract (list, content, thumbnail, ZIP); a member sees as before
 2 approval links: the link's address and the signer's data only for people who may change the quotation (admin, member);
   read-only and accounting get state and dates, no address (they cannot decide as the customer)
 3 accounting reads bookkeeping, quotations / invoices, contracts, cash -- not the pipeline, the generated documents /
   templates / privacy sheets and the whole office log; its levels in the office's settings say so (menu)
 - a person without organisation (freelancer-matrix: office): the own approval link with its address as before
usage: p21340_a_rollen_test.py <datadir>      (a fresh container; P21340A_NOSTART=1 = the server already runs)"""
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402

DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(N, ".data")
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}


def usess(user, pw="password123"):
    s = sess(user, pw)
    r = s.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
    assert r.ok, (user, r.text)
    return s


if not os.environ.get("P21340A_NOSTART"):
    r = subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": "password123"}).ok
A = usess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Alpha", "lang": "en", "collab_all": True, "modules": ["comments"]})
A = usess("alice")
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
uid = {}
for u, role in (("bob", "member"), ("rita", "readonly"), ("axel", "accounting")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": role}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
Bo, Ri, Ax = usess("bob"), usess("rita"), usess("axel")


def upload(s, name, text):
    r = s.post(B + "/api/docs", data={"ws": f"org:{ORG}"}, files={"files": (name, text.encode(), "text/plain")})
    assert r.status_code == 201, (name, r.status_code, r.text[:200])
    return r.json()["ids"][0]


def listed(s):
    r = s.get(B + "/api/docs", params={"ws": f"org:{ORG}", "limit": 200})
    assert r.ok, r.text[:200]
    return {d.get("id") for d in r.json()["docs"]} | {d.get("node_id") for d in r.json()["docs"]}


# ================================================================ 1 the documents folder
CONTRACT = upload(Bo, "employment-contract.txt", "Employment contract of Bob, salary 4000 EUR")
RECEIPT = upload(Bo, "fuel-receipt.txt", "Fuel receipt 54.20 EUR")
r = A.put(B + f"/api/docs/{RECEIPT}/receipt", json={"category": "Travel", "keep": True})
check(r.ok, f"setup: the admin marks the fuel bill as receipt {r.status_code} {r.text[:150]}")
OWN = upload(Ax, "own-receipt.txt", "Stationery 7.10 EUR")

seen = listed(Ax)
check(CONTRACT not in seen, f"accounting: a member's contract is not in the documents list ({CONTRACT} in {sorted(x for x in seen if x)})")
check(RECEIPT in seen, "accounting: the receipt is in the documents list")
check(OWN in seen, "accounting: its own upload is in the documents list")
check(Ax.get(B + f"/api/files/nodes/{CONTRACT}/content").status_code in (403, 404), "accounting: the contract's content is refused")
check(Ax.get(B + f"/api/files/nodes/{CONTRACT}/thumb").status_code in (403, 404), "accounting: the contract's thumbnail is refused")
z = Ax.get(B + "/api/files/zip", params={"ids": str(CONTRACT), "check": 1})
check(z.status_code in (403, 404) or not (z.ok and z.json().get("files")), f"accounting: no ZIP with the contract ({z.status_code} {z.text[:120]})")
rc = Ax.get(B + f"/api/files/nodes/{RECEIPT}/content")
check(rc.ok and b"Fuel receipt" in rc.content, f"accounting: reads the receipt ({rc.status_code})")
check(Ax.get(B + f"/api/files/nodes/{OWN}/content").ok, "accounting: reads its own upload")
check(CONTRACT in listed(Bo) and CONTRACT in listed(A), "member / admin: the contract stays visible to its owner and the admin")
check(CONTRACT not in listed(Ri), "read-only: no other member's unshared document (as before)")

# ================================================================ 2 the approval link of a quotation
r = A.put(B + "/api/office/settings", json={"company": {"name": "Alpha Studio GmbH", "lines": ["Alpha Studio GmbH"]}, "lang": "de", "currency": "EUR"})
check(r.ok, "setup: office settings " + r.text[:120])
SV = A.post(B + "/api/office/services", json={"name_de": "Schnitt", "daily_rate": 900}).json()["id"]
r = A.post(B + "/api/office/docs", json={"project_title": "Imagefilm", "recipient": {"name": "Beispielkunde AG", "lines": ["Beispielkunde AG"]}})
assert r.status_code == 201, r.text
DOC = r.json()["id"]
A.put(B + f"/api/office/docs/{DOC}/items", json={"items": [{"service_id": SV, "qty": 1}]})
check(A.post(B + f"/api/office/docs/{DOC}/status", json={"status": "sent"}).ok, "setup: the quotation is sent")
r = A.post(B + f"/api/office/docs/{DOC}/signoff", json={})
check(r.ok and r.json().get("url"), f"admin: the new link with its address {r.status_code} {r.text[:150]}")


def link(s):
    r = s.get(B + f"/api/office/docs/{DOC}/signoffs")
    return r.status_code, (r.json().get("signoffs") or [{}])[0] if r.ok else {}


for nm, s in (("admin", A), ("member", Bo)):
    code, x = link(s)
    check(code == 200 and x.get("live") and x.get("url"), f"{nm}: may change the quotation, sees the link's address ({code} {x})")
for nm, s in (("read-only", Ri), ("accounting", Ax)):
    code, x = link(s)
    check(code == 200 and x.get("live") is True and x.get("url") is None and x.get("signer_email") is None
          and x.get("ip") is None and x.get("user_agent") is None, f"{nm}: the link's state, no address, no signer data ({code} {x})")

# ================================================================ 3 what accounting reads in the office
for path in ("/api/office/books", "/api/office/docs", "/api/office/contracts", "/api/office/cashbooks", "/api/office/settings"):
    r = Ax.get(B + path)
    check(r.ok, f"accounting reads {path} ({r.status_code} {r.text[:100]})")
for path in ("/api/office/deals", "/api/office/gen-docs", "/api/office/doc-templates", "/api/office/privacy-sheets",
             "/api/office/log", "/api/office/log/chain"):
    r = Ax.get(B + path)
    check(r.status_code == 403, f"accounting: {path} refused ({r.status_code} {r.text[:100]})")
    check(A.get(B + path).ok, f"admin: {path} as before")
lv = Ax.get(B + "/api/office/settings").json()["rights"]["levels"]
check(all(lv.get(k) == "none" for k in ("pipeline", "gendocs", "letters")) and lv.get("books") == "view" and lv.get("offers") == "view",
      f"accounting: the levels of the menu ({lv})")

# ================================================================ a person without organisation (freelancer-matrix: office)
_fid, F = freelancer(B, A, "fiona")
F.put(B + "/api/office/settings", json={"company": {"name": "Fiona Film", "lines": ["Fiona Film"]}, "lang": "de", "currency": "EUR"})
fs = F.post(B + "/api/office/services", json={"name_de": "Kamera", "daily_rate": 700}).json()["id"]
r = F.post(B + "/api/office/docs", json={"project_title": "Portrait", "recipient": {"name": "Kunde", "lines": ["Kunde"]}})
FD = r.json()["id"] if r.status_code == 201 else None
F.put(B + f"/api/office/docs/{FD}/items", json={"items": [{"service_id": fs, "qty": 1}]})
F.post(B + f"/api/office/docs/{FD}/status", json={"status": "sent"})
check(F.post(B + f"/api/office/docs/{FD}/signoff", json={}).ok, "freelancer: a link for the own quotation")
x = (F.get(B + f"/api/office/docs/{FD}/signoffs").json().get("signoffs") or [{}])[0]
check(x.get("url"), f"freelancer: sees the own link's address {x}")

print(f"\np21340_a_rollen: {OKS[0]} ok, {len(FAILS)} failed", flush=True)
sys.exit(1 if FAILS else 0)
