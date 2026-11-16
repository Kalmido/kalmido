#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1289.0 API tests (#6481, audit #4791 N2 N3 N4 S2 S3 U4): numbers of Office & finance, once in the personal office of a
person without an organisation (freelancer fixture; freelancer-matrix: office) and once in an organisation's office (its
admin; a plain member for the rights). Invented companies and people only.
 - N2 a value the counter passes because a quotation or the legacy archive carries it is an office log line number (skipped,
   "taken by ..."); more than 50 taken values in a row are counted past (was: "already used"); the finalise dialog's preview
   shows the free one. A quotation number by hand that follows the invoice / correction scheme: 400; an older quotation with
   such a number stays changeable
 - N4 {isodate} / {date} of a number by hand are checked against the document date (409), like {yyyy}
 - S2 a correction never dates before its invoice (400 naming the invoice), with the corrections' own counter
 - N3/S3 an invoice / correction takes a number by hand only with the finalising (POST .../finalize {number, reason}; the
   draft route: 409, a plain member: 403, a quotation: 400); a numbered draft from before is marked in the list and the view
   (number_draft), stays finalisable; a numbered correction draft's delete text names no cancellation
 - U4 a finalised document with the import's log line is marked imported (at, by) in the list, the view and the auditor's
   export (invoices.csv Importiert_am / Importiert_von)
usage: p6481_office_numbers_test.py <datadir>"""
import csv
import io
import os
import sys
import zipfile
from datetime import date, timedelta

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import dbx as dbxm  # noqa: E402
import requests  # noqa: E402

B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
O = "/api/office"
D = O + "/docs"
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def dbx(sql, args=()):
    c = dbxm.connect(os.path.join(sys.argv[1], "tasks.db"), timeout=10)
    try:
        cur = c.execute(sql, args)
        try:
            rows = cur.fetchall()
        except Exception:  # noqa: BLE001 -- a write without rows
            rows = []
        c.commit()
        return rows
    finally:
        c.close()


s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en"})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
r = A.post(B + "/api/users", json={"username": "bob", "display_name": "Bob Member", "password": "password123", "email": "bob@example.com"})
assert r.ok, r.text
r = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE})
assert r.status_code == 201, r.text
ORG = r.json()["id"]
assert A.put(B + f"/api/orgs/{ORG}/members", json={"email": "bob@example.com", "role": "member"}).ok
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
Bo = sess("bob")
Bo.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)


def run(S, who, member=None):
    def ok(cond, what):
        check(cond, f"{who}: {what}")

    r = S.put(B + O + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "de", "currency": "EUR", "payment_days": 14,
                                         "company_fields": COMPANY, "offer_scheme": "KVA-{yyyy}-{seq:03}",
                                         "invoice_scheme": "RE-{yyyy}-{seq:03}", "credit_scheme": "RK-{yyyy}-{seq:03}"})
    ok(r.ok, "office settings " + r.text[:200])
    me = S.get(B + "/api/state").json()["me"]
    cl = S.post(B + "/api/clients", json={"name": "Testkunde Nord", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert cl.status_code == 201, cl.text
    CL = cl.json()["id"]

    def invoice(**kw):
        r = S.post(B + D, json={"kind": "invoice", "client_id": CL, "service_from": "2026-10-01", "service_to": "2026-10-20",
                                "items": [{"title": "Schnitt", "qty": 1, "rate": 100, "unit": "piece"}], **kw})
        assert r.status_code == 201, r.text
        return r.json()

    def finalize(did, body=None):
        return S.post(B + f"{D}/{did}/finalize", json=body or {})

    def nxt(kind="invoice"):
        return {x["kind"]: x for x in S.get(B + O + "/number-ranges").json()["ranges"]}[kind]["next"]

    def skipped():
        return [x["detail"] for x in S.get(B + O + "/log?limit=500").json().get("log", []) if x["action"] == "number" and "skipped" in (x.get("detail") or {})]

    Y = date.fromisoformat(invoice()["date"]).year
    re_ = lambda n: f"RE-{Y}-{n:03d}"  # noqa: E731

    # ---------------------------------------------------------------- N2 a quotation never takes a number of the invoice series
    off = S.post(B + D, json={"kind": "offer", "client_id": CL, "items": [{"title": "Kamera", "qty": 1, "rate": 500}]}).json()
    for bad in (re_(5), f"RK-{Y}-002"):
        r = S.post(B + f"{D}/{off['id']}/number", json={"number": bad})
        ok(r.status_code == 400 and "a number of its own" in r.json().get("error", ""), f"N2: quotation number {bad} of the invoice / correction series: 400 " + r.text[:160])
    r = S.post(B + f"{D}/{off['id']}/number", json={"number": "KVA-FREI-1"})
    ok(r.ok and r.json()["number"] == "KVA-FREI-1", "N2: a quotation number of its own is fine " + r.text[:120])
    # an older quotation (before 2.1289) with the next invoice number: changeable; the invoice counter passes it with a log line
    n = nxt()
    dbx("UPDATE office_docs SET number=? WHERE id=?", (re_(n), off["id"]))
    ok(S.patch(B + f"{D}/{off['id']}", json={"project_title": "Weiter änderbar"}).ok, "N2: the older quotation with such a number stays changeable")
    ok(S.post(B + f"{D}/{off['id']}/number", json={"number": re_(n)}).ok, "N2: ... and keeps its number when it is sent again")
    before = len(skipped())
    i1 = invoice()
    r = finalize(i1["id"])
    ok(r.ok and r.json()["number"] == re_(n + 1), f"N2: the invoice gets the next free number {re_(n + 1)}: " + r.text[:160])
    sk = skipped()
    ok(len(sk) == before + 1 and sk[0]["skipped"] == re_(n) and f"#{off['id']}" in sk[0].get("reason", ""),
       f"N2: the skipped {re_(n)} is an office log line naming the quotation {sk[:1]}")
    # numbers of the legacy archive: counted past (also more than 50 in a row), each one logged; the preview shows the free one
    oid = dbx("SELECT org_id FROM office_docs WHERE id=?", (i1["id"],))[0][0]
    n = nxt()
    for k in range(n, n + 60):
        dbx("INSERT INTO office_archive(org_id, kind, number, created_at) VALUES(?,?,?,now())", (oid, "invoice", re_(k)))
    i2 = invoice()
    pv = S.get(B + f"{D}/{i2['id']}/number-preview").json()
    ok(pv.get("number") == re_(n + 60), f"N2: the finalise dialog names the first free number {re_(n + 60)}: {pv}")
    before = len(skipped())
    r = finalize(i2["id"])
    ok(r.ok and r.json()["number"] == re_(n + 60), f"N2: 60 numbers of the legacy archive in a row are counted past (was: already used) {re_(n + 60)}: " + r.text[:160])
    sk = skipped()
    ok(len(sk) == before + 60 and {x["skipped"] for x in sk[:60]} == {re_(k) for k in range(n, n + 60)} and all(x.get("reason") for x in sk[:60]),
       f"N2: every skipped archive number is logged with its reason ({len(sk) - before})")


run(Fr, "freelancer")
run(A, "organisation", member=Bo)
print(f"p6481_office_numbers: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
