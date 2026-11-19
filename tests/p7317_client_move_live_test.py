#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7317): a client does not move into another workspace while its office still has something alive for it. Invented
people only, addresses @example.com.
 - PATCH /api/clients org_id with a quotation draft of the old office: 409, code client_in_use, the text names the drafts
   and points at "Move to another workspace…"; the client stays (was: moved, the draft kept a client nobody found)
 - a request (pipeline deal) holds it the same way; the draft and the deal in the trash: the move goes through
 - an admin of the organisation who did not create the client cannot move it into Private (403): there it would be the
   creator's private client; the creator can (released by the admin, #6607)
 - a member without that right gets the 403 before anything of the office is named; only the client's own office counts
 - an old case (a client moved before this check, SQL): duplicating its draft is 409, the series of its template invoice
   makes no invoice ("Make now" 409, nothing made)
tenant-matrix: clients (the organisation's client never lands in another person's private area)
freelancer-matrix: clients (a person without an organisation: no workspace to move to, nothing changes)
usage: p7317_client_move_live_test.py <datadir>"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check, dbx, done, fresh, proved, sess  # noqa: E402

fresh(prefix="P7317")
D = B + "/api/office/docs"

assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Beispiel", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["comments", "office", "clients"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
r = A.post(B + "/api/users", json={"orgs": [], "username": "bob", "display_name": "Bob Muster", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
BOB = r.json()["id"]
proved()
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES, "workspace": f"org:{ORG}"})


def client(s, name):
    r = s.post(B + "/api/clients", json={"name": name, "org_id": ORG, "street": "Musterweg 1", "zip": "20000", "city": "Hamburg", "country": "DE"})
    check(r.status_code == 201, f"setup: client {name} {r.status_code} {r.text[:160]}")
    return r.json()["id"]


def org_of(cid):
    return dbx("SELECT org_id FROM clients WHERE id=?", (cid,))[0][0]


# ---- a quotation draft keeps the client in its workspace
C1 = client(A, "Kunde Entwurf GmbH")
r = A.post(D, json={"kind": "offer", "client_id": C1, "project_title": "Imagefilm"})
check(r.status_code == 201, f"setup: a quotation draft {r.status_code} {r.text[:160]}")
Q1 = r.json()["id"]
r = A.patch(B + f"/api/clients/{C1}", json={"org_id": None})
j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
check(r.status_code == 409 and j.get("code") == "client_in_use" and "draft quotations or invoices" in (j.get("what") or [])
      and "draft quotations or invoices" in (j.get("error") or "") and "Move to another workspace" in (j.get("error") or ""),
      f"a client with a quotation draft: 409 naming the drafts and the office's move {r.status_code} {r.text[:240]}")
check(org_of(C1) == ORG, "the client stayed in the organisation")
# ---- a request (pipeline deal) too
r = A.post(B + "/api/office/deals", json={"title": "Anfrage Beispiel", "client_id": C1})
check(r.status_code == 201, f"setup: a request {r.status_code} {r.text[:160]}")
DEAL = r.json()["id"]
check(A.delete(D + f"/{Q1}").ok, "the draft into the trash")
r = A.patch(B + f"/api/clients/{C1}", json={"org_id": None})
j = r.json() if r.status_code == 409 else {}
check(r.status_code == 409 and j.get("what") == ["requests"], f"a request alone still holds it {r.status_code} {r.text[:200]}")
check(A.delete(B + f"/api/office/deals/{DEAL}").ok, "the request into the trash")
r = A.patch(B + f"/api/clients/{C1}", json={"org_id": None})
check(r.ok and org_of(C1) is None, f"nothing alive left: the creator moves it into Private {r.status_code} {r.text[:200]}")

# ---- Private is the creator's area: an organisation admin cannot move somebody else's client there
C2 = client(Bo, "Kunde von Bob")
r = A.patch(B + f"/api/clients/{C2}", json={"org_id": None})
check(r.status_code == 403 and org_of(C2) == ORG, f"the admin, not the creator: 403, it stays {r.status_code} {r.text[:200]}")
r = Bo.post(B + f"/api/orgs/{ORG}/out-requests", json={"kind": "clients", "id": C2})  # #6607: out of the organisation only released
check(r.ok and A.post(B + f"/api/orgs/{ORG}/out-requests/{r.json().get('id')}", json={"decision": "approve"}).ok, "setup: bob asks, the admin releases " + r.text[:200])
r = Bo.patch(B + f"/api/clients/{C2}", json={"org_id": None})
check(r.ok and org_of(C2) is None and dbx("SELECT created_by FROM clients WHERE id=?", (C2,))[0][0] == BOB,
      f"the creator moves it into his Private {r.status_code} {r.text[:200]}")

# ---- reader F2 (job/5793): a member without the right to take it out learns nothing of the office - 403 before the 409
C7 = client(Bo, "Kunde mit Entwurf von Bob")
r = A.post(D, json={"kind": "offer", "client_id": C7})
check(r.status_code == 201, f"setup: a draft for bob's client {r.status_code}")
r = Bo.patch(B + f"/api/clients/{C7}", json={"org_id": None})
check(r.status_code == 403 and "client_in_use" not in r.text and org_of(C7) == ORG, f"no right to take it out: 403 without naming the office's things {r.status_code} {r.text[:200]}")
# ---- reader F3 (job/5793): only the client's own office counts - an old reference in another office does not hold it
C5 = A.post(B + "/api/clients", json={"name": "Privater Kunde", "org_id": None}).json()["id"]
C6 = client(A, "Kunde Sechs")
r = A.post(D, json={"kind": "offer", "client_id": C6})
check(r.status_code == 201, "setup: a draft of the organisation")
dbx("UPDATE office_docs SET client_id=? WHERE id=?", (C5, r.json()["id"]))  # an old reference across the boundary (before #7317)
r = A.patch(B + f"/api/clients/{C5}", json={"org_id": ORG})
check(r.ok and org_of(C5) == ORG, f"a draft of ANOTHER office does not hold the private client {r.status_code} {r.text[:200]}")

# ---- an old case: the client left before this check (as the move did before #7317)
C3 = client(A, "Kunde Serie GmbH")
r = A.post(D, json={"kind": "invoice", "client_id": C3, "project_title": "Wartung {month}"})
check(r.status_code == 201, f"setup: an invoice draft {r.status_code} {r.text[:160]}")
INV = r.json()["id"]
A.put(D + f"/{INV}/items", json={"items": [{"title": "Wartung", "qty": 1, "rate": 100}]})
r = A.post(B + "/api/office/series", json={"template_id": INV, "every": "monthly", "start": "2026-01-01"})
check(r.status_code == 201, f"setup: a series {r.status_code} {r.text[:160]}")
SID = r.json()["id"]
dbx("UPDATE clients SET org_id=NULL WHERE id=?", (C3,))  # gone from the office, the draft and the series still point at it
n0 = dbx("SELECT COUNT(*) FROM office_docs WHERE org_id IS NOT NULL")[0][0]
r = A.post(D + f"/{INV}/duplicate")
check(r.status_code == 409 and "not in this office" in r.text, f"duplicate with a client that left: 409 {r.status_code} {r.text[:200]}")
r = A.post(B + f"/api/office/series/{SID}/run")
check(r.status_code == 409 and "not in this office" in r.text, f"the series makes no invoice for a client that left: 409 {r.status_code} {r.text[:200]}")
check(dbx("SELECT COUNT(*) FROM office_docs WHERE org_id IS NOT NULL")[0][0] == n0, "nothing was made")

# ---- a person without an organisation: no workspace to move to, the own client and its draft as before
FID, Fr = freelancer(B, A)
r = Fr.post(B + "/api/clients", json={"name": "Freelance Kunde", "org_id": None})
check(r.status_code == 201, f"freelancer: a private client {r.status_code}")
FC = r.json()["id"]
r = Fr.post(D, json={"kind": "offer", "client_id": FC})
check(r.status_code == 201, f"freelancer: a quotation draft {r.status_code} {r.text[:160]}")
check(Fr.patch(B + f"/api/clients/{FC}", json={"name": "Freelance Kunde 2", "org_id": None}).ok, "freelancer: saving the client (same workspace) works")
check(Fr.post(D + f"/{r.json()['id']}/duplicate").status_code == 201, "freelancer: duplicating the draft works")
sys.exit(done("p7317_client_move_live"))
