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
 #6953: folders below the documents folder holding a receipt of the organisation are walkable for accounting (folder only),
   the receipt rule needs the organisation in the single check as in the listing; the figures without the pipeline sum; a
   project's acceptance links follow the quotation's rule
 - a person without organisation (freelancer-matrix: office): the own approval link with its address as before
usage: p21340_a_rollen_test.py <datadir>      (a fresh container; P21340A_NOSTART=1 = the server already runs)"""
import os
import subprocess
import sys

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, dbx, sess  # noqa: E402

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

# ---- #6953 (reader job/5148 F2, F3): folders below the documents folder that hold a receipt are walkable for accounting
# (the folder only), the others and the other files in such a folder stay hidden; listing and single check follow one rule
ROOT = A.get(B + f"/api/files/nodes/{RECEIPT}").json().get("parent_id")


def folder(name):  # bob's folder below the documents folder (a move stays in one owner's tree; the folders straight in the database)
    dbx("INSERT INTO fs_nodes(parent_id, kind, name, owner_id, org_id, created_by, created_at, updated_at) "
        "VALUES(?, 'folder', ?, ?, ?, ?, '2026-11-19T00:00:00Z', '2026-11-19T00:00:00Z')", (ROOT, name, uid["bob"], ORG, uid["bob"]), data=DATA)
    return (dbx("SELECT id FROM fs_nodes WHERE parent_id=? AND name=?", (ROOT, name), data=DATA) or [(None,)])[0][0]


SUB, EMPTY = folder("Receipts 2026"), folder("Staff papers")
check(ROOT and SUB and EMPTY, f"setup: two folders below the documents folder {ROOT} {SUB} {EMPTY}")
for nid in (RECEIPT, CONTRACT):
    r = Bo.patch(B + f"/api/files/nodes/{nid}", json={"parent_id": SUB})
    check(r.ok, f"setup: bob moves {nid} into the receipts folder {r.status_code} {r.text[:120]}")
r = Ax.get(B + f"/api/files/nodes/{SUB}")
check(r.ok and r.json().get("role") == "view", f"F3: accounting opens the folder with a receipt, read only ({r.status_code} {r.text[:120]})")
check(Ax.get(B + f"/api/files/nodes/{EMPTY}").status_code in (403, 404), "F3: a folder without receipts stays closed to accounting")
r = Ax.get(B + "/api/files", params={"parent": SUB})
ids = {x["id"] for x in r.json().get("items", [])} if r.ok else set()
check(r.ok and RECEIPT in ids and CONTRACT not in ids, f"F3: inside it accounting lists the receipt, not the contract ({r.status_code} {ids})")
r = Ax.get(B + "/api/files", params={"parent": ROOT})
ids = {x["id"] for x in r.json().get("items", [])} if r.ok else set()
check(r.ok and SUB in ids and EMPTY not in ids, f"F3: the documents folder lists the receipts folder, not the other ({r.status_code} {ids})")
seen = listed(Ax)
check(RECEIPT in seen and CONTRACT not in seen, "F3: the documents list still has the receipt, not the contract")
check(Ax.get(B + f"/api/files/nodes/{RECEIPT}/content").ok, "F3: accounting reads the receipt in the sub folder")
check(Ax.get(B + f"/api/files/nodes/{CONTRACT}/content").status_code in (403, 404), "F3: ... and not the contract next to it")
check(A.get(B + "/api/files", params={"parent": SUB}).ok and CONTRACT in listed(A), "F3: the admin sees everything as before")
# reader F1 of job/5543 (Festlegung 19.11. 01:27): the API v1 lists a folder's children by the web's rule (fs_children_visible)
r = Ax.post(B + "/api/me/tokens", json={"name": "acc", "scopes": ["read", "files:read"]})
check(r.status_code == 201, f"setup: accounting makes a read token {r.status_code} {r.text[:120]}")
VH = {"Authorization": "Bearer " + (r.json().get("token") or "" if r.status_code == 201 else "")}
r = requests.get(B + "/api/v1/files", params={"parent_id": SUB}, headers=VH)
ids = {x["id"] for x in r.json().get("data", [])} if r.ok else set()
check(r.ok and RECEIPT in ids and CONTRACT not in ids, f"F1 v1: the folder's listing has the receipt, not the contract ({r.status_code} {ids})")
r = requests.get(B + f"/api/v1/files/{SUB}", headers=VH)
ids = {x["id"] for x in r.json().get("children", [])} if r.ok else set()
check(r.ok and RECEIPT in ids and CONTRACT not in ids, f"F1 v1: the folder's children: the receipt, not the contract ({r.status_code} {ids})")
r = requests.get(B + "/api/v1/files", params={"parent_id": ROOT}, headers=VH)
ids = {x["id"] for x in r.json().get("data", [])} if r.ok else set()
check(r.ok and SUB in ids and EMPTY not in ids, f"F1 v1: the documents folder lists the receipts folder only ({r.status_code} {ids})")
# ... and a closed area's root (the organisation's projects folder): the web and the API v1 by the same rule -- a member does
# not list it (404, p2199_c G1), the admin lists the folders with a role of her own (all of them) in both alike
A.post(B + "/api/lists", json={"name": "Alpha project", "org_id": ORG})
PROOT = next((sp.get("root") for sp in A.get(B + "/api/lists/tree").json().get("spaces", []) if sp.get("org_id") == ORG), None)
FA = A.post(B + "/api/lists/folders", json={"parent_id": PROOT, "name": "Alice only"}).json().get("id")
FBO = Bo.post(B + "/api/lists/folders", json={"parent_id": PROOT, "name": "Bob's folder"}).json().get("id")
check(PROOT and FA and FBO, f"setup: the projects folder with a folder of alice and one of bob {PROOT} {FA} {FBO}")


def kids3(s, hdr):  # (status, ids) of the web listing, the API v1 listing and the API v1 folder with its children
    r1 = s.get(B + "/api/files", params={"parent": PROOT})
    r2 = requests.get(B + "/api/v1/files", params={"parent_id": PROOT}, headers=hdr)
    r3 = requests.get(B + f"/api/v1/files/{PROOT}", headers=hdr)
    return [(r.status_code, {x["id"] for x in r.json().get(k, [])} if r.ok else set())
            for r, k in ((r1, "items"), (r2, "data"), (r3, "children"))]


r = Bo.post(B + "/api/me/tokens", json={"name": "bob", "scopes": ["read", "files:read"]})
BH = {"Authorization": "Bearer " + (r.json().get("token") or "" if r.status_code == 201 else "")}
k = kids3(Bo, BH)
check(all(x[0] == 404 for x in k), f"F1 v1: a member lists the area's root neither in the web nor in the API v1 ({k})")
r = A.post(B + "/api/me/tokens", json={"name": "alice", "scopes": ["read", "files:read"]})
AH = {"Authorization": "Bearer " + (r.json().get("token") or "" if r.status_code == 201 else "")}
k = kids3(A, AH)
check(all(x[0] == 200 and {FA, FBO} <= x[1] and x[1] == k[0][1] for x in k), f"F1 v1: the admin lists the area's root alike in the web and the API v1 ({k})")
# F2: a receipt row of no organisation (or another one) opens nothing for accounting; the listing never showed it
dbx("UPDATE rc_receipts SET org_id=NULL WHERE node_id=?", (RECEIPT,), data=DATA)
check(Ax.get(B + f"/api/files/nodes/{RECEIPT}/content").status_code in (403, 404) and RECEIPT not in listed(Ax),
      "F2: a receipt without the organisation is neither readable nor listed for accounting (one rule)")
check(Ax.get(B + f"/api/files/nodes/{SUB}").status_code in (403, 404), "F2/F3: its folder closes again with it")
dbx("UPDATE rc_receipts SET org_id=? WHERE node_id=?", (ORG, RECEIPT), data=DATA)

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

# #6953 (reader job/5148 F1): a project's acceptance links follow the quotation's rule -- the link's address for who may change
# them, the signer's data (here the device) only for an office admin among them
LB = Bo.post(B + "/api/lists", json={"name": "Bob's shoot", "org_id": ORG}).json()["id"]
r = Bo.post(B + f"/api/lists/{LB}/signoffs", json={})
check(r.ok and r.json().get("id"), f"setup: bob makes an acceptance link of his project {r.status_code} {r.text[:150]}")
dbx("UPDATE office_signoffs SET user_agent='TestBrowser/1.0' WHERE list_id=?", (LB,), data=DATA)
r = Bo.get(B + f"/api/lists/{LB}/signoffs")
x = (r.json().get("signoffs") or [{}])[0] if r.ok else {}
check(r.ok and x.get("url") and x.get("user_agent") is None and x.get("ip") is None,
      f"member who owns the project: the link's address, no signer device ({r.status_code} {x})")

# ================================================================ 3 what accounting reads in the office
for path in ("/api/office/books", "/api/office/docs", "/api/office/contracts", "/api/office/cashbooks", "/api/office/settings"):
    r = Ax.get(B + path)
    check(r.ok, f"accounting reads {path} ({r.status_code} {r.text[:100]})")
for path in ("/api/office/deals", "/api/office/gen-docs", "/api/office/doc-templates", "/api/office/privacy-sheets",
             "/api/office/log", "/api/office/log/chain"):
    r = Ax.get(B + path)
    check(r.status_code == 403, f"accounting: {path} refused ({r.status_code} {r.text[:100]})")
    check(A.get(B + path).ok, f"admin: {path} as before")
# #6953 (reader job/5148 #5205 F1): the figures carry the weighted pipeline only for who may see the pipeline
k = Ax.get(B + "/api/office/kpi")
check(k.status_code == 403 or (k.ok and k.json().get("pipeline") is None), f"accounting: no pipeline sum in the figures ({k.status_code} {k.text[:160]})")
k = A.get(B + "/api/office/kpi")
check(k.ok and isinstance(k.json().get("pipeline"), dict), f"admin: the figures with the pipeline as before ({k.status_code})")
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
