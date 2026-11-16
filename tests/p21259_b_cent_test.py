#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1259.0 B (#6303, audit #4740 F5a-d) API tests: the cents of the office's exports and the final invoice. Own container
(start.sh). Invented companies and figures only.
freelancer-matrix: office
 - (a) booking export (tax adviser): a USD invoice 10.00 + 1.90 at rate 1.09 -> the invoice row's gross is money(11.90 / 1.09)
   = 10.92 like its payment row (was net and VAT converted one by one: 9.17 + 1.74 = 10.91); the rest cent on the net
 - (b) DATEV batch: a USD invoice of 100.00 (91.74 EUR) paid with 33.33 / 33.33 / 33.34 USD -> the payment that settles it
   carries the rest cent (30.58 / 30.58 / 30.58, was 30.58 / 30.58 / 30.59): the debtor balances; the same with a cash
   discount (12.05 USD, 2 % = 0.24, paid 11.81: the discount line takes 0.23, was 0.22 -> the debtor kept -0.01)
 - (c) an invoice of the second half of 2020 (100.00 at 16 %): the DATEV check names the rate without automatic account,
   the balance sheet books 100.00 revenue + 16.00 VAT (was split at 19 %: 97.48 + 18.52) and names it too
 - (d) a final invoice after a partial credit note on its progress invoice (100.03 net / 19.01 VAT, credit 50.02 / 9.50):
   the deduction takes off the VAT its text names (19.01 - 9.50 = 9.51, gross 59.52), the final invoice 200.00 net is
   149.99 + 28.49 = 178.48 (was 28.50 / 178.49: one cent too much)
 Each flow runs for an organisation's admin and for a person without organisation (personal office).
usage: p21259_b_cent_test.py <datadir>"""
import csv
import io
import os
import re
import subprocess
import sys
from decimal import Decimal

import requests

import dbx as dbxm
import testclock
from freelancer_fixture import freelancer

N = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
from kt import FAILS, OKS, check, sess  # noqa: E402

FEAT = "cal,comments,collab,office,clients,docs"
O = "/api/office"
D = O + "/docs"
TODAY = testclock.today()
Y = TODAY.year
DAY = TODAY.isoformat()
D2 = Decimal


def dbx(sql, args=(), write=False):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        r = c.execute(sql, args).fetchall()
        if write:
            c.commit()
        return r
    finally:
        c.close()


def dd(v):
    return D2(str(v if v not in (None, "") else 0).replace(",", ".")).quantize(D2("0.01"))


def office(s, who):
    r = s.put(B + O + "/settings", json={"lang": "en", "currency": "EUR", "payment_days": 14,
                                         "datev_extf": {"advisor_no": "1234567", "client_no": "12345", "chart": "SKR03"},
                                         "company_fields": {"name": f"{who} Beispiel GmbH", "street": "Teststraße 1", "zip": "20000", "city": "Hamburg",
                                                            "country": "DE", "tax_number": "12/345/67890", "vat_id": "DE999999999",
                                                            "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}})
    check(r.ok, f"{who}: office settings " + r.text[:200])
    r = s.put(B + O + "/books/ledger/settings", json={"method": "balance"})
    check(r.ok, f"{who}: balance sheet chosen " + r.text[:200])
    r = s.post(B + "/api/clients", json={"name": f"{who} Kunde GmbH", "street": "Weg 1", "zip": "10000", "city": "Ort", "country": "DE"})
    assert r.ok, r.text
    return r.json()["id"]


def invoice(s, cl, rate, cur=None, fx=None, extra=None, service_to=None):
    b = {"kind": "invoice", "client_id": cl, "project_title": f"Job {rate}", "service_from": service_to or DAY, "service_to": service_to or DAY,
         "items": [{"title": "Schnitt", "qty": 1, "rate": rate, "unit": "flat", "tax": "standard"}], **(extra or {})}
    if cur:
        b.update(currency=cur, fx_rate=fx)
    r = s.post(B + D, json=b)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.ok, f"invoice {did} finalised " + r.text[:200])
    return s.get(B + f"{D}/{did}").json()


def pay(s, did, amount):
    r = s.post(B + f"{D}/{did}/payments", json={"date": DAY, "amount": amount, "method": "transfer"})
    check(r.ok, f"payment {amount} on {did} " + r.text[:200])


def beleg(number):
    return re.sub(r"[^A-Za-z0-9$&%*+\-/]", "-", number or "").lstrip("+-")[:36]


def extf(s, frm, to):
    r = s.get(B + O + f"/datev/extf?from={frm}&to={to}")
    check(r.ok, "DATEV batch " + r.text[:200])
    rows = r.content.decode("cp1252").split("\r\n")
    cols = [x.strip('"') for x in rows[1].split(";")]
    return [{k: v.strip('"') for k, v in zip(cols, x.split(";"))} for x in rows[2:] if x]


def debtor_balance(rows, number):
    """The debtor's balance of one document in the DATEV batch (+ = still owed by the client)."""
    mine = [x for x in rows if x["Belegfeld 1"] == beleg(number)]
    inv = [x for x in mine if x["Buchungstext"].startswith(number)]
    deb = inv[0]["Konto"] if inv else ""
    bal = D2(0)
    for x in mine:
        a = dd(x["Umsatz (ohne Soll/Haben-Kz)"])
        if x["Konto"] == deb:
            bal += a if x["Soll/Haben-Kennzeichen"] == "S" else -a
        elif x["Gegenkonto (ohne BU-Schlüssel)"] == deb:
            bal += -a if x["Soll/Haben-Kennzeichen"] == "S" else a
    return bal, mine


def bx_rows(s):
    """The booking export (tax adviser) of this year as [{column: text}]."""
    r = s.get(B + O + f"/books/export?from={Y}-01-01&to={Y}-12-31")
    check(r.ok, "booking export " + r.text[:200])
    txt = r.content.decode("utf-8-sig")
    head = txt.split("\r\n", 1)[0]
    return list(csv.DictReader(io.StringIO(txt), delimiter=";" if ";" in head else ","))


def flow(s, who):
    cl = office(s, who)
    # ---- (a) the tax adviser's booking export: 10.00 + 1.90 USD at 1.09
    a = invoice(s, cl, "9.1743", "USD", "1.09")
    check(a["totals"]["net"] == "10.00" and a["totals"]["tax"] == "1.90" and a["totals"]["gross"] == "11.90", f"{who} (a): USD 10.00 + 1.90 {a['totals'].get('gross')}")
    pay(s, a["id"], "11.90")
    rows = [x for x in bx_rows(s) if x.get("Number") == a["number"]]
    inv = [x for x in rows if x.get("Type") == "Invoice"]
    pm = [x for x in rows if x.get("Type") == "Payment"]
    check(len(inv) == 1 and len(pm) == 1, f"{who} (a): one invoice row and one payment row {rows}")
    if inv and pm:
        check(dd(inv[0]["Gross"]) == D2("10.92") and dd(pm[0]["Gross"]) == D2("10.92"),
              f"{who} (a): the invoice row's gross = money(11.90 / 1.09) = 10.92 like its payment (was 10.91) {inv[0]} {pm[0]}")
        check(dd(inv[0]["Net"]) + dd(inv[0]["VAT"]) == dd(inv[0]["Gross"]) and dd(inv[0]["VAT"]) == D2("1.74"),
              f"{who} (a): net + VAT = gross, the VAT as converted (1.74), the rest cent on the net {inv[0]}")
    # ---- (b) DATEV: 100.00 USD paid in three parts
    b = invoice(s, cl, "77.0917", "USD", "1.09")
    check(b["totals"]["gross"] == "100.00", f"{who} (b): USD 84.03 + 15.97 = 100.00 {b['totals'].get('gross')}")
    for x in ("33.33", "33.33", "33.34"):
        pay(s, b["id"], x)
    rows = extf(s, f"{Y}-01-01", f"{Y}-12-31")
    bal, mine = debtor_balance(rows, b["number"])
    amounts = sorted(dd(x["Umsatz (ohne Soll/Haben-Kz)"]) for x in mine if x["Buchungstext"].startswith("Zahlung"))
    check(bal == 0 and amounts == [D2("30.58")] * 3, f"{who} (b): the settling payment carries the rest cent, the debtor balances (was -0.01) {bal} {amounts}")
    # ---- (b) the same with a cash discount: 12.05 USD, 2 % = 0.24, paid 11.81 in time
    k = invoice(s, cl, "9.2936", "USD", "1.09", extra={"skonto_pct": 2, "skonto_days": 10, "payment_days": 14})
    check(k["totals"]["gross"] == "12.05", f"{who} (b): USD 10.13 + 1.92 = 12.05 {k['totals'].get('gross')}")
    pay(s, k["id"], "11.81")
    check(s.get(B + f"{D}/{k['id']}").json()["status"] == "paid", f"{who} (b): paid less 2 % = paid")
    rows = extf(s, f"{Y}-01-01", f"{Y}-12-31")
    bal, mine = debtor_balance(rows, k["number"])
    sk = [dd(x["Umsatz (ohne Soll/Haben-Kz)"]) for x in mine if x["Buchungstext"].startswith("Skonto")]
    check(bal == 0 and sk == [D2("0.23")], f"{who} (b): the discount line takes the rest (0.23, was 0.22), the debtor balances {bal} {sk} {mine}")
    # ---- (c) 16 % in the second half of 2020
    c = invoice(s, cl, 100, service_to="2020-08-15")
    tl = c["totals"]["tax_lines"]
    check(len(tl) == 1 and tl[0]["pct"] == "16" and tl[0]["amount"] == "16.00", f"{who} (c): the invoice of August 2020 carries 16 % {tl}")
    dbx("UPDATE office_docs SET date='2020-08-20' WHERE id=?", (c["id"],), write=True)
    r = s.get(B + O + "/datev/extf?from=2020-08-01&to=2020-08-31&check=1")
    hints = r.json().get("hints") or [] if r.ok else []
    odd = [h for h in hints if h.get("key") == "odd_rate"]
    check(len(odd) == 1 and c["number"] in odd[0]["text"] and "16" in odd[0]["text"] and "16.00" in odd[0]["text"].replace(",", "."),
          f"{who} (c): the DATEV check names the rate without automatic account {hints}")
    rep = s.get(B + O + "/books/ledger?year=2020&journal=1").json()
    jr = [x for x in rep.get("journal") or [] if x.get("doc") == beleg(c["number"])]
    vat = [dd(x["amount"]) for x in jr if x.get("kind") == "vat"]
    rev = [dd(x["amount"]) for x in jr if x.get("kind") != "vat"]
    check(vat == [D2("16.00")] and rev == [D2("100.00")], f"{who} (c): the balance sheet books 100.00 + 16.00 (was 97.48 + 18.52) {jr}")
    check(any(h.get("key") == "odd_rate" for h in rep.get("hints") or []), f"{who} (c): the balance sheet names it as well {rep.get('hints')}")


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
flow(A, "Alpha")
FID, Fr = freelancer(B, A)  # freelancer-matrix: office
flow(Fr, "Frida")

print(f"\n{OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
