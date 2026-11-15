#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1206.0 (#6161, Stufe 3): the office document's answer carries can_edit with the person's role (office/docs.py
ofd_role_edit), so the client leaves the write entries out without computing the role itself. Invented names only,
addresses @example.com. freelancer-matrix: office
 - an open draft: can_edit true for the admin, a member, a person without an organisation in the own office
 - false for read-only and accounting (organisation role) and for a member whose office group gives only "view" in
   Quotations & invoices; their changes stay 403 (read-only with the read-only text) - nothing was loosened
usage: p21206_d_ro_test.py <datadir>      (P21206D_NOSTART=1: a running server)"""
import sys

from freelancer_fixture import freelancer
import requests

from kt import B, H, PASSWORD, check, docker_logs_on_first_fail, done, fresh, sess

docker_logs_on_first_fail()

fresh(prefix="P21206D")
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice", "password": PASSWORD}).ok
A = sess("alice")
r = A.post(B + "/api/admin/setup", json={"org_name": "Alpha Studio", "lang": "en", "collab_all": True, "modules": ["comments"]})
assert r.ok, "admin setup " + r.text[:300]
A = sess("alice")
FEAT = "office,contacts,files,docs,comments"
A.patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
D, R = "/api/office/docs", "/api/office/rights"
uid, S = {}, {}
for u, role in (("bob", "member"), ("rita", "readonly"), ("axel", "accounting"), ("vera", "member")):
    r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": role}], "username": u, "display_name": u.title(),
                                       "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    uid[u] = r.json()["id"]
    S[u] = sess(u)
    assert S[u].patch(B + "/api/settings", json={"lang": "en", "tour": "done", "features": FEAT, "workspace": f"org:{ORG}"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Bo, Ri, Ax, Ve = S["bob"], S["rita"], S["axel"], S["vera"]

# vera: an office group that only reads Quotations & invoices
r = A.post(B + f"{R}/groups", json={"from": "tpl:none", "name": "Readers of quotations"})
check(r.status_code == 201, "setup: group " + r.text[:200])
GID = r.json()["id"]
check(A.patch(B + f"{R}/groups/{GID}", json={"levels": {"offers": "view"}}).ok, "setup: group level offers view")
check(A.put(B + f"{R}/people/{uid['vera']}", json={"groups": [f"g:{GID}"]}).ok, "setup: vera into the group")

r = A.post(B + D, json={"project_title": "Spring campaign"})
check(r.status_code in (200, 201), "admin: a quotation draft " + r.text[:200])
DID = r.json()["id"]
r = A.put(B + f"{D}/{DID}/items", json={"items": [{"title": "Concept", "qty": 2, "rate": 800}]})
check(r.ok and r.json()["can_edit"] is True, "admin: positions saved, can_edit true " + r.text[:200])


def doc(s):
    r = s.get(B + f"{D}/{DID}")
    assert r.ok, r.text
    return r.json()


check(doc(A)["can_edit"] is True, "admin: can_edit true")
check(doc(Bo)["can_edit"] is True, "member: can_edit true")
for nm, s in (("read-only", Ri), ("accounting", Ax), ("group with offers view", Ve)):
    d = doc(s)
    check(d["can_edit"] is False and not d["locked"] and d["status"] == "draft", f"{nm}: reads the draft, can_edit false {d.get('can_edit')}")
    check([it["title"] for it in d["items"]] == ["Concept"], f"{nm}: sees the positions")
    r = s.patch(B + f"{D}/{DID}", json={"order_ref": "x"})
    check(r.status_code == 403, f"{nm}: a change stays 403 ({r.status_code} {r.text[:150]})")
    r = s.put(B + f"{D}/{DID}/items", json={"items": []})
    check(r.status_code == 403, f"{nm}: positions stay 403 ({r.status_code})")
    check(s.post(B + D, json={"project_title": "x"}).status_code == 403, f"{nm}: no new document")
r = Ri.patch(B + f"{D}/{DID}", json={"order_ref": "x"})
check("read-only" in (r.json().get("error") or ""), "read-only: the read-only text " + r.text[:150])
check(doc(A)["items"][0]["title"] == "Concept" and not doc(A).get("order_ref"), "nothing was written by the readers")

# the member saves: the answer of a write carries the same can_edit
r = Bo.patch(B + f"{D}/{DID}", json={"order_ref": "PO-1"})
check(r.ok and r.json()["can_edit"] is True, "member: the save's answer can_edit true " + r.text[:150])

# freelancer: the own personal office
FID, F = freelancer(B, A, features=FEAT)
r = F.post(B + D, json={"project_title": "Own job"})
check(r.status_code in (200, 201) and r.json()["can_edit"] is True, "freelancer: a draft in the own office, can_edit true " + r.text[:200])
FD = r.json()["id"]
check(F.get(B + f"{D}/{FD}").json()["can_edit"] is True, "freelancer: GET can_edit true")
check(F.patch(B + f"{D}/{FD}", json={"order_ref": "F-1"}).ok, "freelancer: saves")

sys.exit(done("p21206_d_ro"))
