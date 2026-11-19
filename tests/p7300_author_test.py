#!/usr/bin/env python3
# kalmido-suite: fresh
"""(#7300): "Created by" of a quotation (office_docs.author_id, kalmido/office/docauthor.py). Invented people only.
 - a new quotation names its maker; the choice = the organisation's active members (no guest, no agent), sent with the draft
 - PATCH author_id: another member is taken, an outsider (a person of another organisation) is 400, null = nobody
 - the PDF model: "Your contact" / "Ihr Ansprechpartner" with the name in the document's language, none without an author
 - the number token {initials} follows the author (fallback: the maker)
 - the list filter: GET /api/office/docs/groups names the authors, ?author_id= narrows the quotations
 - finalising freezes the name (the row stays after a rename); a finalised quotation refuses a change (409)
 - duplicate and the invoice from the quotation keep author_id; the invoice prints no "Your contact"
tenant-matrix: office (another organisation's member cannot be named: 400)
freelancer-matrix: office (a person without an organisation: no choice, no line, no filter)
usage: p7300_author_test.py <datadir>"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import B, check, done, fresh, sess  # noqa: E402

fresh(prefix="P7300")
D = B + "/api/office/docs"

assert sess().post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Beispiel", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"org_name": "Example Studio", "lang": "en", "collab_all": True, "modules": ["comments", "office", "clients"]})
A.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES})
ORG = A.get(B + "/api/state").json()["me"]["workspaces"][0]["id"]
UID = {}
for u in ("bob", "carol", "gus"):
    r = A.post(B + "/api/users", json={"orgs": [], "username": u, "display_name": u.title() + " Muster", "password": "password123", "email": f"{u}@example.com"})
    assert r.ok, r.text
    UID[u] = r.json().get("id")
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
r = A.put(B + f"/api/orgs/{ORG}/members", json={"email": "gus@example.com", "role": "guest"})
GUEST = r.ok
r = A.post(B + "/api/admin/orgs", json={"name": "Other Example", "admin_id": UID["carol"]})
check(r.status_code == 201, f"setup: another organisation {r.status_code}")
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
assert A.put(B + "/api/office/settings", json={"company_fields": {"name": "Studio Beispiel", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE"},
                                               "offer_scheme": "AN-{initials}-{seq:03}"}).ok
ME = A.get(B + "/api/state").json()["me"]["id"]


def new(s, **kw):
    r = s.post(D, json={"project_title": "Imagefilm", "lang": "en", **kw})
    check(r.status_code == 201, f"setup: a quotation {r.status_code} {r.text[:200]}")
    did = r.json()["id"]
    s.put(D + f"/{did}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "day"}]})
    return did


def meta(s, did):
    return {k: v for k, v in s.get(D + f"/{did}/render").json().get("meta") or []}


Q = new(A)
d = A.get(D + f"/{Q}").json()
ids = {p["id"] for p in d.get("author_choices") or []}
check(d.get("author_id") == ME and d.get("author_name") == "Alice Beispiel", f"a new quotation names its maker: {d.get('author_id')} {d.get('author_name')!r}")
check(ME in ids and UID["bob"] in ids and UID["carol"] not in ids and (not GUEST or UID["gus"] not in ids),
      f"the choice: the organisation's members, no guest, no outsider: {d.get('author_choices')}")
check(meta(A, Q).get("Your contact") == "Alice Beispiel", f"the PDF names the contact: {meta(A, Q)}")
check(A.patch(D + f"/{Q}", json={"lang": "de"}).ok and meta(A, Q).get("Ihr Ansprechpartner") == "Alice Beispiel",
      f"German quotation: 'Ihr Ansprechpartner': {meta(A, Q)}")
A.patch(D + f"/{Q}", json={"lang": "en"})

# another member, an outsider, nobody
r = A.patch(D + f"/{Q}", json={"author_id": UID["bob"]})
check(r.ok and A.get(D + f"/{Q}").json().get("author_id") == UID["bob"] and meta(A, Q).get("Your contact") == "Bob Muster",
      f"PATCH author_id: another member is named {r.status_code} {r.text[:160]} {meta(A, Q)}")
pv = A.get(D + f"/{Q}/number-preview").json()
check(str(pv.get("number") or "").startswith("AN-AB-"), f"a number given stays when the author changes later: {pv}")
Q3 = new(A, author_id=UID["bob"])
pv = A.get(D + f"/{Q3}/number-preview").json()
check(str(pv.get("number") or "").startswith("AN-BM-"), f"{{initials}} follows the author named at the start: {pv}")
r = A.patch(D + f"/{Q}", json={"author_id": UID["carol"]})
check(r.status_code == 400 and A.get(D + f"/{Q}").json().get("author_id") == UID["bob"], f"another organisation's person: 400 {r.status_code}")
r = A.patch(D + f"/{Q}", json={"author_id": "x"})
check(r.status_code == 400, f"a wrong value: 400 {r.status_code}")
Q2 = new(A)
r = A.patch(D + f"/{Q2}", json={"author_id": None})
check(r.ok and A.get(D + f"/{Q2}").json().get("author_id") is None and "Your contact" not in meta(A, Q2), f"nobody: no line {meta(A, Q2)}")
Q4 = new(A, author_id=None)
pv = A.get(D + f"/{Q4}/number-preview").json()
check(A.get(D + f"/{Q4}").json().get("author_id") is None and str(pv.get("number") or "").startswith("AN-AB-"), f"{{initials}} without an author: the maker's {pv}")

# the list filter
g = A.get(D + "/groups").json()
au = {x["id"]: x for x in g.get("authors") or []}
check(au.get(UID["bob"], {}).get("n") == 2 and au.get(ME, {}).get("n") == 2, f"groups: the authors with counts (a quotation without one counts for its maker) {g.get('authors')}")
rows = A.get(D + f"?kind=offer&author_id={UID['bob']}").json()["docs"]
check(sorted(x["id"] for x in rows) == sorted([Q, Q3]) and all(x.get("author_id") == UID["bob"] for x in rows), f"?author_id= narrows the quotations: {[x['id'] for x in rows]}")
rows = A.get(D + f"?kind=offer&author_id={ME}").json()["docs"]
check(sorted(x["id"] for x in rows) == sorted([Q2, Q4]), f"?author_id= of the maker finds the ones without an author: {[x['id'] for x in rows]}")

# duplicate and invoice keep it; the invoice prints no contact
r = A.post(D + f"/{Q}/duplicate")
dup = r.json().get("id") if r.ok else None
check(dup and A.get(D + f"/{dup}").json().get("author_id") == UID["bob"], f"a duplicate keeps the author {r.status_code} {r.text[:120]}")
r = A.post(D + f"/{Q}/invoice", json={})
inv = r.json().get("id") if r.ok else None
if inv:
    d = A.get(D + f"/{inv}").json()
    check(d.get("author_id") == UID["bob"] and not any(k in ("Your contact", "Ihr Ansprechpartner") for k in meta(A, inv)),
          f"the invoice from the quotation keeps author_id, prints no contact: {d.get('author_id')} {meta(A, inv)}")
else:
    check(False, f"setup: invoice from the quotation {r.status_code} {r.text[:200]}")

# finalising freezes the name; a finalised one refuses a change
r = A.post(D + f"/{Q}/finalize")
check(r.ok, f"finalise {r.status_code} {r.text[:200]}")
check(meta(A, Q).get("Your contact") == "Bob Muster", f"a finalised quotation keeps the name it was printed with: {meta(A, Q)}")
r = A.patch(D + f"/{Q}", json={"author_id": ME})
check(r.status_code == 409, f"a finalised quotation: no change of the author (409) {r.status_code}")

# a member works with it too; a person without an organisation has no choice and no line
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"tour": "done", "lang": "en", "features": FEATURES, "workspace": f"org:{ORG}"})
r = Bo.get(D + f"/{Q2}")
check(r.ok and {p["id"] for p in r.json().get("author_choices") or []} == ids, f"a member sees the same choice {r.status_code}")
FID, Fr = freelancer(B, A)
Fr.put(B + "/api/office/settings", json={"company_fields": {"name": "Frida Film", "street": "Weg 1", "zip": "10115", "city": "Berlin", "country": "DE"}})
F = new(Fr)
d = Fr.get(D + f"/{F}").json()
check(d.get("author_choices") == [] and not d.get("author_name") and "Your contact" not in meta(Fr, F), f"personal office: no choice, no line {d.get('author_choices')} {meta(Fr, F)}")
r = Fr.patch(D + f"/{F}", json={"author_id": ME})
check(r.status_code == 400, f"personal office: naming somebody else is 400 {r.status_code}")
check(not (Fr.get(D + "/groups").json().get("authors")), "personal office: no author filter")
sys.exit(done("p7300_author"))
