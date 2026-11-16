#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1259.0 A (#6301, #6302, audit #4740 F3 / F4): the books take the frozen sums of the documents. Invented names and figures only.
freelancer-matrix: office
 - #6301: three invoices of 33.34 / 33.33 / 33.33 net at 19 % (frozen: 100.00 net, 18.99 VAT), each paid in full: the
   income statement shows 100.00 / 18.99 (was 99.99 / 19.00, recomputed from the gross), field 81 of the VAT return on
   the cash basis 100 (was 99), the key figures 100.00 net -- the same figure as the income statement; on the accrual
   basis ("soll") field 81 = 100 too (the frozen bases of the documents)
 - the same for a person without an organisation (own office)
usage: p21259_a_books_test.py <datadir>"""
import os
import subprocess
import sys

import requests

import testclock
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
from kt import FAILS, OKS, check, sess  # noqa: E402

FEAT = "cal,comments,collab,office,clients,docs,travel,time"
O = "/api/office"
D = O + "/docs"
BK = O + "/books"
TODAY = testclock.today().isoformat()
Y = int(TODAY[:4])
COMPANY = {"name": "Studio Beispiel GmbH", "street": "Teststraße 1", "zip": "20000", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "vat_id": "DE999999999", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}

subprocess.run(["bash", os.path.join(N, "start.sh"), DATA], check=True, stdout=subprocess.DEVNULL)
s0 = requests.Session()
s0.headers.update(H)
assert s0.post(B + "/api/auth/setup", json={"username": "alice", "display_name": "Alice Admin", "password": "password123"}).ok
A = sess("alice")
A.post(B + "/api/admin/setup", json={"lang": "en", "modules": ["cal", "comments"]})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A)


def office(s):
    r = s.put(B + O + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "en", "currency": "EUR", "company_fields": COMPANY,
                                         "payment_days": 14, "vat_basis": "ist"})
    check(r.ok, "office settings " + r.text[:200])


def client(s, name):
    r = s.post(B + "/api/clients", json={"name": name, "street": "Weg 1", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.ok, r.text
    return r.json()["id"]


def invoice(s, cl, rate, title="Schnitt"):
    r = s.post(B + D, json={"kind": "invoice", "client_id": cl, "project_title": title, "service_from": TODAY,
                            "items": [{"title": title, "qty": 1, "rate": rate}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    check(s.post(B + f"{D}/{did}/finalize").ok, f"invoice {did} finalised")
    return did


def ustva(s, period):
    r = s.get(B + BK + f"/ustva?year={Y}&period={period}")
    check(r.ok, "UStVA " + r.text[:200])
    return r.json()


def kpi_month(s):
    return next((m["amount"] for m in s.get(B + O + "/kpi").json()["revenue"]["months"] if m["month"] == TODAY[:7]), None)


# ---------------------------------------------------------------- #6301: the frozen tax lines
def frozen_lines(s, who):
    office(s)
    cl = client(s, f"{who} Kunde")
    ids = [invoice(s, cl, x) for x in ("33.34", "33.33", "33.33")]
    tot = [s.get(B + f"{D}/{i}").json()["totals"] for i in ids]
    check([t["tax"] for t in tot] == ["6.33", "6.33", "6.33"], f"{who}: frozen VAT 6.33 each {[t.get('tax') for t in tot]}")
    for i, t in zip(ids, tot):
        r = s.post(B + f"{D}/{i}/payments", json={"date": TODAY, "amount": t["gross"], "method": "transfer"})
        check(r.status_code == 201, f"{who}: invoice {i} paid in full " + r.text[:200])
    eu = s.get(B + BK + f"/euer?year={Y}").json()
    v19 = next((x for x in eu["income"] if x["key"] == "vat19"), {})
    check(v19.get("net") == "100.00" and v19.get("vat") == "18.99" and v19.get("gross") == "118.99",
          f"{who}: income statement = the frozen base and tax 100.00 / 18.99 (was 99.99 / 19.00) {v19}")
    kz = ustva(s, "m" + TODAY[5:7]).get("kz", {})
    check(kz.get("81") == "100", f"{who}: cash basis: field 81 = 100 from the frozen bases (was 99) {kz.get('81')}")
    check(kpi_month(s) == v19.get("net"), f"{who}: key figures and income statement show the same net {kpi_month(s)} {v19.get('net')}")
    r = s.put(B + O + "/settings", json={"vat_basis": "soll"})
    check(r.ok, f"{who}: accrual basis " + r.text[:200])
    kz = ustva(s, "y").get("kz", {})
    check(kz.get("81") == "100" and kz.get("86") == "0", f"{who}: accrual basis: field 81 = 100 from the frozen bases (was 99) {kz}")
    s.put(B + O + "/settings", json={"vat_basis": "ist"})


frozen_lines(A, "Alpha")
frozen_lines(Fr, "Frida")

print(f"p21259_a_books: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
