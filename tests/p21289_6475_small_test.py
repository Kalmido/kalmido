#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1289.0 (#6475): the office switch "Small business" binds the tax at finalising (invoices.inv_missing), own container
(start.sh). Invented companies and people only. freelancer-matrix: office
Played in an organisation's office and in the personal office of a person without an organisation:
 - switch on + a draft with VAT (made before the switch, or set to "with VAT" by PATCH): finalising is refused (400 names
   "as a small business no VAT may be shown"); set to "without VAT" + the section 19 note it finalises
 - switch off + the section 19 note: refused (400 names the switch); with the switch on the same draft finalises
 - a correction (credit note) of an invoice with VAT from before the switch keeps that tax and finalises with the switch on
 - an organisation's switch does not bind the personal office and back
usage: p21289_6475_small_test.py <datadir>      (P21289S_NOSTART=1: a running server on KALMIDO_TEST_PORT, no start.sh)"""
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
OFF_API = "/api/office"
D = OFF_API + "/docs"
FEAT = "cal,comments,collab,office,clients"
NO_VAT = "as a small business no VAT may be shown"
NO_NOTE = "the VAT note small business only with the switch Small business"
COMPANY = {"name": "Studio Beispiel", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}

if os.environ.get("P21289S_NOSTART") != "1":
    subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, "erin")  # freelancer-matrix: office (the personal office, its own admin)


def err(r):
    try:
        return r.json().get("error", "")
    except ValueError:
        return r.text


def run(who, s):
    check(s.put(B + OFF_API + "/settings", json={"small_business": 0, "lang": "de", "currency": "EUR", "payment_days": 14,
                                           "company_fields": dict(COMPANY, name=f"Studio {who}")}).ok, f"{who}: office settings")
    r = s.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    cl = r.json()["id"]

    def invoice(**kw):
        r = s.post(B + D, json=dict({"kind": "invoice", "client_id": cl, "service_from": "2026-10-01", "service_to": "2026-10-20",
                                     "items": [{"title": "Schnitt", "qty": 1, "rate": 1000}]}, **kw))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def fin(did):
        return s.post(B + f"{D}/{did}/finalize")

    old = invoice()
    check(fin(old).ok, f"{who}: an invoice with VAT before the switch")
    dv = invoice()  # a draft with VAT from before the switch
    ds = invoice(vat_mode="novat", vat_note="small")
    r = fin(ds)
    check(r.status_code == 400 and NO_NOTE in err(r), f"{who} (2): switch off + section 19 note: refused " + r.text[:200])
    check(s.get(B + f"{D}/{ds}").json()["status"] == "draft", f"{who} (2): still a draft")

    check(s.put(B + OFF_API + "/settings", json={"small_business": 1}).ok, f"{who}: small business on")
    r = fin(dv)
    check(r.status_code == 400 and NO_VAT in err(r), f"{who} (1): switch on + a draft with VAT: refused " + r.text[:200])
    nd = invoice()
    check(s.get(B + f"{D}/{nd}").json()["vat_mode"] == "novat", f"{who}: a new draft is without VAT (default as before)")
    check(s.patch(B + f"{D}/{nd}", json={"vat_mode": "vat"}).ok, f"{who}: the VAT choice can still be set (PATCH)")
    r = fin(nd)
    check(r.status_code == 400 and NO_VAT in err(r), f"{who} (1): PATCH vat_mode=vat then finalise: refused " + r.text[:200])
    check(s.get(B + f"{D}/{nd}").json()["status"] == "draft" and not s.get(B + f"{D}/{nd}").json().get("number"), f"{who} (1): no number given")
    # set right: without VAT + the note -> finalises
    check(s.patch(B + f"{D}/{dv}", json={"vat_mode": "novat", "vat_note": "small"}).ok, f"{who}: the old draft set to without VAT")
    r = fin(dv)
    check(r.ok, f"{who}: set right, it finalises " + r.text[:200])
    check(fin(ds).ok, f"{who} (2): the section 19 note with the switch on finalises")
    # (3) a correction of the invoice with VAT from before the switch keeps its tax
    r = s.post(B + f"{D}/{old}/credit")
    check(r.status_code == 201, f"{who}: a correction draft " + r.text[:200])
    cr = r.json()["id"]
    c = s.get(B + f"{D}/{cr}").json()
    check(c["vat_mode"] == "vat", f"{who} (3): the correction keeps the invoice's VAT {c['vat_mode']}")
    r = fin(cr)
    check(r.ok, f"{who} (3): the correction with VAT finalises with the switch on " + r.text[:200])
    check(s.put(B + OFF_API + "/settings", json={"small_business": 0}).ok, f"{who}: small business off again")


run("org", A)
# the organisation's switch does not reach the personal office: on in the organisation, off in the personal office
check(A.put(B + OFF_API + "/settings", json={"small_business": 1}).ok, "setup: the organisation is a small business")
run("freelancer", Fr)
check(A.get(B + OFF_API + "/settings").json()["settings"]["small_business"] == 1 and Fr.get(B + OFF_API + "/settings").json()["settings"]["small_business"] == 0,
      "the switch stays per office area")

print(f"p21289_6475_small: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
