#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1416.0 (#6529): what finalising still misses comes with the draft (GET of the document: missing [{key, text, level}]),
own container (start.sh). Invented companies and people only. freelancer-matrix: office
Played in an organisation's office and in the personal office of a person without an organisation:
 - an invoice draft of an office without company data: GET names the blocks with their fixed keys (company_address,
   company_tax, company_iban, service_period ...), level "block"; finalising is refused (400, the server's check unchanged)
 - the text of each line is the one the refusal names (one check)
 - company data and a period set: no block left, finalising works; the finalised document has no list
usage: p6529_missing_list_test.py <datadir>      (P6529_NOSTART=1: a running server on KALMIDO_TEST_PORT, no start.sh)"""
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
OFF = "/api/office"
D = OFF + "/docs"
FEAT = "cal,comments,collab,office,clients"
COMPANY = {"street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}

if os.environ.get("P6529_NOSTART") != "1":
    subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "collab_all": True})
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Studio Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, "erin")  # freelancer-matrix: office (the personal office, its own admin)


def err(r):
    try:
        return r.json().get("error", "")
    except ValueError:
        return r.text


def keys(doc, level="block"):
    return [m["key"] for m in doc.get("missing") or [] if m.get("level") == level]


def run(who, s, personal):
    check(s.put(B + OFF + "/settings", json={"lang": "en", "currency": "EUR", "payment_days": 14}).ok, f"{who}: office settings")
    r = s.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    cl = r.json()["id"]
    r = s.post(B + D, json={"kind": "invoice", "client_id": cl, "items": [{"title": "Schnitt", "qty": 1, "rate": 1000}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    d = s.get(B + f"{D}/{did}").json()
    ks = keys(d)
    for k in ("service_period", "company_address", "company_tax", "company_iban"):
        check(k in ks, f"{who}: GET names {k} {ks}")
    check(all(m.get("text") and m.get("level") in ("block", "warn") for m in d["missing"]), f"{who}: every line has a text and a level")
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.status_code == 400, f"{who}: finalising is still refused by the server {r.status_code}")
    texts = [m["text"] for m in d["missing"] if m["level"] == "block"]
    check(all(t in err(r) for t in texts), f"{who}: the refusal names the same lines {err(r)[:200]} / {texts}")
    check(s.get(B + f"{D}/{did}").json()["status"] == "draft", f"{who}: still a draft")
    # company data and the period: no block left
    check(s.put(B + OFF + "/settings", json={"company_fields": dict(COMPANY, name=f"Studio {who}")}).ok, f"{who}: company data")
    check(s.patch(B + f"{D}/{did}", json={"service_from": "2026-10-01", "service_to": "2026-10-20"}).ok, f"{who}: the period")
    d = s.get(B + f"{D}/{did}").json()
    check(keys(d) == [], f"{who}: no block left {d.get('missing')}")
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.ok and r.json().get("locked"), f"{who}: finalised {r.status_code} {r.text[:200]}")
    d = s.get(B + f"{D}/{did}").json()
    check(not d.get("missing"), f"{who}: a finalised document has no list {d.get('missing')}")


run("org", A, False)
run("freelancer", Fr, True)
print(f"p6529_missing_list: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
