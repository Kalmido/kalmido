#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6945 API tests: the PO number of a project (lists.po_number) is the order reference (order_ref) of its documents; once in
an organisation's office (its admin) and once in the personal office of a person without an organisation (freelancer
fixture; freelancer-matrix: office). Invented companies, people and numbers only.
 - PATCH /api/lists/<id> po_number: stored, in the state, in the project's settings history; a draft of the project without
   an own order reference follows; 81 characters are refused (400)
 - a quotation bound to the project (POST /docs/<id>/project) takes the PO; its PDF head names it ("Ihre Bestellnummer")
 - a document with its own different order_ref keeps it, the project keeps its PO (doc project_po for the editor's hint); a
   change of the project's PO changes the drafts that carried the old one, not that one, and never a finalised invoice
 - the way back: a project without a PO gets the order_ref typed into its document
 - the invoice from the quotation carries it; finalised, the suggested mail subject is "Rechnung <no> – Ihre Bestellnummer PO"
 - search: the office search and the document list find a document by its PO number; the hit names "PO ..."
 - API: GET /api/v1/lists/<id> carries po_number, PATCH sets it
usage: p6945_po_nummer_test.py <datadir>"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402

B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Deichweg 5", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 000002", "tax_number": "12/345/67892", "vat_id": "DE999999997",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}

s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
FEAT = FEATURES if "office" in FEATURES else FEATURES + ",office"
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
A.patch(B + "/api/settings", json={"workspace": f"org:{r.json()['id']}"})
FID, Fr = freelancer(B, A)


def run(S, who):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    def lst(lid):
        return next((x for x in S.get(B + "/api/state").json().get("lists") or [] if x["id"] == lid), {})

    def doc(did):
        return S.get(B + f"{D}/{did}").json()

    r = S.put(B + OFC + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "industry_packs": []})
    ok(r.ok, "office settings " + r.text[:200])
    r = S.post(B + "/api/clients", json={"name": "Beispielkunde GmbH", "street": "Marktstraße 7", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    CL = r.json()["id"]

    def offer(title):
        r = S.post(B + D, json={"client_id": CL, "project_title": title, "raw_mode": "none", "producing_on": 0, "lang": "de",
                                "service_from": "2026-10-01", "service_to": "2026-10-20"})
        assert r.status_code == 201, r.text
        did = r.json()["id"]
        S.put(B + f"{D}/{did}/items", json={"items": [{"title": "Regie", "qty": 1, "rate": 1000, "unit": "flat"}]})
        return did

    # ---------------------------------------------------------------- the project's PO, its draft follows
    OF = offer("Messefilm")
    r = S.post(B + f"{D}/{OF}/project", json={"create": {"name": "Messe 2027"}})
    ok(r.ok and r.json().get("list_id"), "a project from the quotation " + r.text[:200])
    P = r.json()["list_id"]
    ok(not lst(P).get("po_number"), f"a new project has no PO number: {lst(P).get('po_number')!r}")
    r = S.patch(B + f"/api/lists/{P}", json={"po_number": "x" * 81})
    ok(r.status_code == 400, f"81 characters are refused: {r.status_code}")
    r = S.patch(B + f"/api/lists/{P}", json={"po_number": "  PO-4711 "})
    ok(r.ok and lst(P).get("po_number") == "PO-4711", f"PATCH po_number, trimmed: {r.status_code} {lst(P).get('po_number')!r}")
    ok(doc(OF).get("order_ref") == "PO-4711", f"the draft without an own order reference follows: {doc(OF).get('order_ref')!r}")
    h = S.get(B + f"/api/lists/{P}/history").json()
    ok("po_number" in str(h), f"the project's settings history names the change: {str(h)[:300]}")
    rd = S.get(B + f"{D}/{OF}/render").json()
    ok(["Ihre Bestellnummer", "PO-4711"] in [list(x) for x in rd.get("meta") or []], f"the quotation's PDF head: {rd.get('meta')}")
    p = S.get(B + f"{D}/{OF}/pdf")
    ok(p.ok and p.content.startswith(b"%PDF-"), f"the PDF of the quotation {p.status_code}")

    # ---------------------------------------------------------------- a quotation bound later takes it; an own value stays
    OF2 = offer("Messefilm Teaser")
    r = S.post(B + f"{D}/{OF2}/project", json={"list_id": P})
    ok(r.ok and r.json().get("order_ref") == "PO-4711" and r.json().get("project_po") == "PO-4711",
       f"bound to the project: the PO as its order reference {r.status_code} {r.text[:200]}")
    r = S.patch(B + f"{D}/{OF2}", json={"order_ref": "PO-9999"})
    ok(r.ok and r.json().get("order_ref") == "PO-9999" and r.json().get("project_po") == "PO-4711" and lst(P).get("po_number") == "PO-4711",
       f"an own different order reference: the document keeps it, the project its PO (hint data) {r.text[:200]}")
    r = S.patch(B + f"/api/lists/{P}", json={"po_number": "PO-5000"})
    ok(r.ok and doc(OF).get("order_ref") == "PO-5000" and doc(OF2).get("order_ref") == "PO-9999",
       f"a new project PO: the draft with the old one follows, the own one stays {doc(OF).get('order_ref')!r} {doc(OF2).get('order_ref')!r}")

    # ---------------------------------------------------------------- the way back
    OF3 = offer("Imagefilm")
    r = S.post(B + f"{D}/{OF3}/project", json={"create": {"name": "Imagefilm 2027"}})
    P3 = r.json().get("list_id")
    r = S.patch(B + f"{D}/{OF3}", json={"order_ref": "PO-777"})
    ok(r.ok and lst(P3).get("po_number") == "PO-777", f"a project without a PO takes the document's order reference: {lst(P3).get('po_number')!r}")
    ok("po_number" in str(S.get(B + f"/api/lists/{P3}/history").json()), "... in the project's settings history")

    # ---------------------------------------------------------------- the invoice, finalised: its subject; the PO changes no more
    r = S.post(B + f"{D}/{OF}/invoice", json={"force": True})
    ok(r.status_code == 201, "invoice from the quotation " + r.text[:200])
    iv = r.json()
    ok(iv.get("order_ref") == "PO-5000" and iv.get("list_id") == P, f"the invoice carries the PO and the project: {iv.get('order_ref')!r} {iv.get('list_id')}")
    r = S.post(B + f"{D}/{iv['id']}/finalize")
    ok(r.ok, "finalise the invoice " + r.text[:200])
    di = doc(iv["id"])
    ok(di.get("mail_subject") == f"Rechnung {di.get('number')} – Ihre Bestellnummer PO-5000",
       f"the suggested mail subject names the PO in the document's language: {di.get('mail_subject')!r}")
    ok(doc(OF2).get("mail_subject") is None, "a draft has no suggested subject yet")
    r = S.patch(B + f"/api/lists/{P}", json={"po_number": "PO-6000"})
    ok(r.ok and doc(iv["id"]).get("order_ref") == "PO-5000", f"a finalised invoice keeps its PO: {doc(iv['id']).get('order_ref')!r}")
    r = S.patch(B + f"/api/lists/{P}", json={"po_number": None})
    ok(r.ok and lst(P).get("po_number") == "" and doc(OF).get("order_ref") == "", f"null removes it, the following draft too: {doc(OF).get('order_ref')!r}")

    # ---------------------------------------------------------------- search
    r = S.get(B + "/api/search", params={"kind": "office", "q": "PO-9999"})
    hits = (r.json() if r.ok else {}).get("office") or []
    ok(any(x.get("id") == OF2 and "PO PO-9999" in (x.get("sub") or "") for x in hits), f"the office search finds it by its PO: {r.status_code} {hits}")
    r = S.get(B + D, params={"q": "PO-9999"})
    rows = r.json() if r.ok else {}
    rows = rows.get("docs") if isinstance(rows, dict) else rows
    ok(any(x.get("id") == OF2 and x.get("order_ref") == "PO-9999" for x in rows or []), f"the document list finds it by its PO: {str(rows)[:300]}")

    # ---------------------------------------------------------------- the API (tokens, agents)
    tok = S.post(B + "/api/me/tokens", json={"name": "po", "scopes": ["read", "write"]}).json().get("token")
    T = {"Authorization": "Bearer " + (tok or "")}
    r = requests.get(B + f"/api/v1/lists/{P3}", headers=T)
    ok(r.ok and r.json().get("po_number") == "PO-777", f"GET /api/v1/lists carries po_number: {r.status_code} {r.text[:200]}")
    r = requests.patch(B + f"/api/v1/lists/{P3}", headers=T, json={"po_number": "PO-778", "expect_updated_at": r.json().get("updated_at")})
    ok(r.ok and r.json().get("po_number") == "PO-778" and doc(OF3).get("order_ref") == "PO-778",
       f"PATCH /api/v1/lists sets it; the draft with the old one follows: {r.status_code} {r.text[:200]} {doc(OF3).get('order_ref')!r}")


run(A, "organisation")
run(Fr, "freelancer")
print(f"p6945_po_nummer: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
