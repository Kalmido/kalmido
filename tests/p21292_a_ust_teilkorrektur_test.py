#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1292.0 A (#6478, audit #4791 S1): on the cash basis a payment on an invoice with a finalised partial credit note is split
by the rest per VAT rate (the invoice's frozen tax lines less those of its credit notes, books.bk_credit_rest), was the shares
of the whole invoice. Invented names and figures only.
freelancer-matrix: office
 - the example of the task: 100.00 at 19 % + 100.00 at 7 % = 226.00, a credit note takes the 7 % position back, the client
   pays 119.00: VAT return field 81 = 100, 86 = 0, VAT 19.00 at 19 % and none at 7 % (was 52 / 52, 9.88 + 3.64); the income
   statement 100.00 / 19.00 at 19 %, the key figures 100.00 net
 - the rest paid in two parts (60.00 + 59.00): exactly 100.00 / 19.00, no cent lost
 - paid in full before the credit note (226.00), the credited 107.00 refunded on the credit note: 100.00 / 19.00 at 19 %,
   nothing at 7 % (the overpayment is the credited part, the refund takes back its own lines)
 - a full credit note (cancellation) after the payment, refunded on it: nothing left at any rate, no division by zero
 - a credit note draft (not finalised) does not count: the payment keeps the shares of the invoice
 - a foreign currency (USD at 1.09, books.bk_fx_lines #6456): 10.00 USD at 19 % + 10.00 USD at 7 %, the 7 % credited,
   11.90 USD paid = 9.18 + 1.74 = 10.92 EUR at 19 %, nothing at 7 %
 - the same for a person without an organisation (own office)
usage: p21292_a_ust_teilkorrektur_test.py <datadir>"""
import os
import subprocess
from decimal import Decimal
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
OF = "/api/office"
D = OF + "/docs"
BK = OF + "/books"
TODAY = testclock.today().isoformat()
Y = int(TODAY[:4])
COMPANY = {"name": "Studio Beispiel GmbH", "street": "Teststraße 1", "zip": "20000", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "vat_id": "DE999999999", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
Z3 = (Decimal(0),) * 3

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

STD = {"title": "Schnitt", "qty": 1, "unit": "flat", "rate": "100.00", "tax": "standard"}
RED = {"title": "Buch", "qty": 1, "unit": "flat", "rate": "100.00", "tax": "reduced"}
USD10 = "9.1743"  # a position's rate is typed in the office currency: x 1.09 = 10.00 USD (calc.inv_calc)


def office(s):
    r = s.put(B + OF + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "en", "currency": "EUR", "company_fields": COMPANY,
                                         "payment_days": 14, "vat_basis": "ist"})
    check(r.ok, "office settings " + r.text[:200])


def client(s, name):
    r = s.post(B + "/api/clients", json={"name": name, "street": "Weg 1", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.ok, r.text
    return r.json()["id"]


def doc(s, cl, items, cur=None, fx=None):
    b = {"kind": "invoice", "client_id": cl, "project_title": "Teilkorrektur", "service_from": TODAY, "items": items}
    if cur:
        b.update(currency=cur, fx_rate=fx)
    r = s.post(B + D, json=b)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    check(s.post(B + f"{D}/{did}/finalize").ok, f"invoice {did} finalised")
    return did


def credit(s, inv, items, final=True):
    """A credit note on invoice inv with the given positions (the draft copies all, a partial credit keeps fewer)."""
    r = s.post(B + f"{D}/{inv}/credit")
    check(r.status_code == 201, "credit note draft " + r.text[:200])
    cr = r.json()["id"]
    if items is not None:
        r = s.put(B + f"{D}/{cr}/items", json={"items": items})
        check(r.ok, "credit note positions " + r.text[:200])
    if final:
        r = s.post(B + f"{D}/{cr}/finalize")
        check(r.ok, "credit note finalised " + r.text[:200])
    return cr


def pay(s, did, *amounts):
    for a in amounts:
        r = s.post(B + f"{D}/{did}/payments", json={"date": TODAY, "amount": a, "method": "transfer"})
        check(r.status_code == 201, f"payment {a} on {did} " + r.text[:200])


def euer_rows(s):
    eu = s.get(B + BK + f"/euer?year={Y}").json()
    return {x["key"]: (Decimal(x["net"]), Decimal(x["vat"]), Decimal(x["gross"])) for x in eu["income"]}


def delta(before, after, key):
    return tuple(a - b for a, b in zip(after.get(key, Z3), before.get(key, Z3)))


def ustva(s):
    r = s.get(B + BK + f"/ustva?year={Y}&period=y")
    check(r.ok, "UStVA " + r.text[:200])
    return r.json()


def kpi_month(s):
    return Decimal(next((m["amount"] for m in s.get(B + OF + "/kpi").json()["revenue"]["months"] if m["month"] == TODAY[:7]), None) or 0)


def run(s, who):
    office(s)
    cl = client(s, f"{who} Verlag")
    # the example of the task, first in a fresh office: the VAT return figures absolute
    inv = doc(s, cl, [STD, RED])
    check(s.get(B + f"{D}/{inv}").json()["totals"]["gross"] == "226.00", f"{who}: the invoice is 119.00 + 107.00 = 226.00")
    credit(s, inv, [RED])
    pay(s, inv, "119.00")
    u = ustva(s)
    kz, tax = u.get("kz", {}), u.get("tax", {})
    check(kz.get("81") == "100" and kz.get("86") == "0", f"{who}: field 81 = 100, 86 = 0 after the 7 % position was credited (was 52 / 52) {kz.get('81')} {kz.get('86')}")
    check(tax.get("19") == "19.00" and tax.get("7") == "0.00", f"{who}: VAT 19.00 at 19 %, none at 7 % (was 9.88 + 3.64) {tax}")
    e1 = euer_rows(s)
    check(e1.get("vat19") == (Decimal("100.00"), Decimal("19.00"), Decimal("119.00")) and e1.get("vat7", Z3) == Z3,
          f"{who}: income statement 100.00 / 19.00 at 19 %, nothing at 7 % {e1.get('vat19')} {e1.get('vat7')}")
    check(kpi_month(s) == Decimal("100.00"), f"{who}: key figures 100.00 net, as the income statement {kpi_month(s)}")
    # the rest in two parts: no cent lost
    inv = doc(s, cl, [STD, RED])
    credit(s, inv, [RED])
    pay(s, inv, "60.00", "59.00")
    e2 = euer_rows(s)
    check(delta(e1, e2, "vat19") == (Decimal("100.00"), Decimal("19.00"), Decimal("119.00")) and delta(e1, e2, "vat7") == Z3,
          f"{who}: two parts = exactly 100.00 / 19.00 {delta(e1, e2, 'vat19')} {delta(e1, e2, 'vat7')}")
    # paid in full before the credit note, the credited part refunded on the credit note
    inv = doc(s, cl, [STD, RED])
    pay(s, inv, "226.00")
    cr = credit(s, inv, [RED])
    pay(s, cr, "107.00")
    e3 = euer_rows(s)
    check(delta(e2, e3, "vat19") == (Decimal("100.00"), Decimal("19.00"), Decimal("119.00")) and delta(e2, e3, "vat7") == Z3,
          f"{who}: overpaid and refunded: 100.00 / 19.00 at 19 %, nothing at 7 % {delta(e2, e3, 'vat19')} {delta(e2, e3, 'vat7')}")
    # a full credit note (cancellation) after the payment, refunded: nothing left, rest 0 without a division by zero
    inv = doc(s, cl, [STD, RED])
    pay(s, inv, "226.00")
    cr = credit(s, inv, None)
    e4a = euer_rows(s)
    check(delta(e3, e4a, "vat19") == (Decimal("100.00"), Decimal("19.00"), Decimal("119.00")) and delta(e3, e4a, "vat7") == (Decimal("100.00"), Decimal("7.00"), Decimal("107.00")),
          f"{who}: a payment on a fully credited invoice, not yet refunded: by the invoice's lines {delta(e3, e4a, 'vat19')} {delta(e3, e4a, 'vat7')}")
    pay(s, cr, "226.00")
    e4 = euer_rows(s)
    check(delta(e3, e4, "vat19") == Z3 and delta(e3, e4, "vat7") == Z3, f"{who}: refunded: nothing left {delta(e3, e4, 'vat19')} {delta(e3, e4, 'vat7')}")
    # a credit note draft does not count
    inv = doc(s, cl, [STD, RED])
    credit(s, inv, [RED], final=False)
    pay(s, inv, "113.00")
    e5 = euer_rows(s)
    check(delta(e4, e5, "vat19") == (Decimal("50.00"), Decimal("9.50"), Decimal("59.50")) and delta(e4, e5, "vat7") == (Decimal("50.00"), Decimal("3.50"), Decimal("53.50")),
          f"{who}: a draft credit note does not count: half the invoice by its shares {delta(e4, e5, 'vat19')} {delta(e4, e5, 'vat7')}")
    # a foreign currency
    usd = doc(s, cl, [dict(STD, rate=USD10), dict(RED, rate=USD10)], "USD", "1.09")
    check(s.get(B + f"{D}/{usd}").json()["totals"]["gross"] == "22.60", f"{who}: the USD invoice is 11.90 + 10.70 = 22.60 USD")
    credit(s, usd, [dict(RED, rate=USD10)])
    pay(s, usd, "11.90")
    e6 = euer_rows(s)
    check(delta(e5, e6, "vat19") == (Decimal("9.18"), Decimal("1.74"), Decimal("10.92")) and delta(e5, e6, "vat7") == Z3,
          f"{who}: USD 11.90 / 1.09 = 9.18 + 1.74 at 19 %, nothing at 7 % {delta(e5, e6, 'vat19')} {delta(e5, e6, 'vat7')}")


run(A, "Alpha")
run(Fr, "Frida")

print(f"p21292_a_ust_teilkorrektur: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
