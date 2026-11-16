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
 - #6445 the final invoice's full credit note takes its VAT (178.48, was 178.49 -> 409); a partial credit note keeping the
   deduction (49.99 + 9.49) plus the rest (119.00) credit it in full; a rate billed in full by two progress invoices keeps
   the tax line with base 0 and -0.01 in the final invoice and its credit note (was left out)
 - (d) a final invoice after a partial credit note on its progress invoice (100.03 net / 19.01 VAT, credit 50.02 / 9.50):
   the deduction takes off the VAT its text names (19.01 - 9.50 = 9.51, gross 59.52), the final invoice 200.00 net is
   149.99 + 28.49 = 178.48 (was 28.50 / 178.49: one cent too much)
 Each flow runs for an organisation's admin and for a person without organisation (personal office).
usage: p21259_b_office_cent_test.py <datadir>"""
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
OF = "/api/office"
D = OF + "/docs"
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
    r = s.put(B + OF + "/settings", json={"lang": "en", "currency": "EUR", "payment_days": 14,
                                         "datev_extf": {"advisor_no": "1234567", "client_no": "12345", "chart": "SKR03"},
                                         "company_fields": {"name": f"{who} Beispiel GmbH", "street": "Teststraße 1", "zip": "20000", "city": "Hamburg",
                                                            "country": "DE", "tax_number": "12/345/67890", "vat_id": "DE999999999",
                                                            "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}})
    check(r.ok, f"{who}: office settings " + r.text[:200])
    r = s.put(B + OF + "/books/ledger/settings", json={"method": "balance"})
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
    r = s.get(B + OF + f"/datev/extf?from={frm}&to={to}")
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
    r = s.get(B + OF + f"/books/export?from={Y}-01-01&to={Y}-12-31")
    check(r.ok, "booking export " + r.text[:200])
    txt = r.content.decode("utf-8-sig")
    head = txt.split("\r\n", 1)[0]
    return list(csv.DictReader(io.StringIO(txt), delimiter=";" if ";" in head else ","))


def abs_final(s, cl, who):
    """(d) quotation 200.00, progress invoice 100.03 (+ 19.01), partial credit note 50.02 (+ 9.50), the final invoice finalised
    -> its id (178.48)."""
    r = s.post(B + D, json={"project_title": "Imagefilm", "client_id": cl, "service_from": DAY, "service_to": DAY})
    assert r.status_code == 201, r.text
    q = r.json()["id"]
    assert s.put(B + f"{D}/{q}/items", json={"items": [{"title": "Dreh", "qty": 1, "unit": "flat", "rate": 200, "tax": "standard"}]}).ok
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "progress", "amount": "100.03"})
    check(r.status_code == 201, f"{who} (d): progress 100.03 " + r.text[:200])
    P = r.json()["id"]
    check(s.post(B + f"{D}/{P}/finalize").ok, f"{who} (d): progress finalised")
    p = s.get(B + f"{D}/{P}").json()
    check(p["totals"]["net"] == "100.03" and p["totals"]["tax"] == "19.01", f"{who} (d): progress 100.03 + 19.01 {p['totals'].get('tax')}")
    r = s.post(B + f"{D}/{P}/credit")
    check(r.status_code == 201, f"{who} (d): credit draft " + r.text[:200])
    CR = r.json()["id"]
    check(s.put(B + f"{D}/{CR}/items", json={"items": [{"title": "Teilgutschrift", "qty": 1, "unit": "flat", "rate": "50.02", "tax": "standard"}]}).ok
          and s.post(B + f"{D}/{CR}/finalize").ok, f"{who} (d): partial credit note 50.02 finalised")
    check(s.get(B + f"{D}/{CR}").json()["totals"]["tax"] == "9.50", f"{who} (d): credit 50.02 + 9.50")
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "final"})
    check(r.status_code == 201, f"{who} (d): final draft " + r.text[:200])
    F = r.json()["id"]
    t = s.get(B + f"{D}/{F}").json()["totals"]
    check(t["net"] == "149.99" and t["tax"] == "28.49" and t["gross"] == "178.48",
          f"{who} (d): the deduction takes off 9.51 VAT as its text says: 149.99 + 28.49 = 178.48 (was 28.50 / 178.49) {t.get('net')} {t.get('tax')} {t.get('gross')}")
    ded = [x for x in t["lines"] if x.get("kind") == "discount"]
    check(len(ded) == 1 and ded[0].get("abs_tax") == "9.51" and dd(ded[0].get("net")) == D2("-50.01"),
          f"{who} (d): the deduction line 50.01 carries the billed VAT 9.51 {ded}")
    r = s.post(B + f"{D}/{F}/finalize")
    check(r.ok, f"{who} (d): the final invoice finalises " + r.text[:200])
    t = s.get(B + f"{D}/{F}").json()["totals"]
    check(t["gross"] == "178.48", f"{who} (d): finalised 178.48 {t.get('gross')}")

    return F


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
    # ---- #6456: two rates in USD (10.00 + 1.90 and 10.00 + 0.70 = 22.60 USD at 1.09 = 20.73): the booking export and DATEV
    # follow the rule of the books (books.bk_fx_lines): the rest cent on the base of the largest rate -> 9.18 + 1.74 at 19 %,
    # 9.17 + 0.64 at 7 % (was (a): on the last line, 9.17 + 1.74 and 9.18 + 0.64 -- one cent off the income statement per rate)
    r = s.post(B + D, json={"kind": "invoice", "client_id": cl, "project_title": "Job zwei Sätze", "service_from": DAY, "service_to": DAY,
                            "currency": "USD", "fx_rate": "1.09",
                            "items": [{"title": "Schnitt", "qty": 1, "rate": "9.1743", "unit": "flat", "tax": "standard"},
                                      {"title": "Buch", "qty": 1, "rate": "9.1743", "unit": "flat", "tax": "reduced"}]})
    assert r.status_code == 201, r.text
    check(s.post(B + f"{D}/{r.json()['id']}/finalize").ok, f"{who} #6456: two rates finalised")
    z = s.get(B + f"{D}/{r.json()['id']}").json()
    check(z["totals"]["gross"] == "22.60", f"{who} #6456: USD two rates 22.60 {z['totals'].get('gross')}")
    pay(s, z["id"], "22.60")
    rows = [x for x in bx_rows(s) if x.get("Number") == z["number"]]
    inv = sorted(((dd(x["Net"]), dd(x["VAT"]), dd(x["Gross"])) for x in rows if x.get("Type") == "Invoice"), key=lambda x: x[1])
    pm = sum((dd(x["Gross"]) for x in rows if x.get("Type") == "Payment"), D2(0))
    check(inv == [(D2("9.17"), D2("0.64"), D2("9.81")), (D2("9.18"), D2("1.74"), D2("10.92"))] and pm == D2("20.73"),
          f"{who} #6456: booking export: 9.18 + 1.74 at 19 %, 9.17 + 0.64 at 7 %, together the payment 20.73 {inv} {pm}")
    bal, mine = debtor_balance(extf(s, f"{Y}-01-01", f"{Y}-12-31"), z["number"])
    amounts = sorted(dd(x["Umsatz (ohne Soll/Haben-Kz)"]) for x in mine if x["Buchungstext"].startswith(z["number"]))
    check(bal == 0 and amounts == [D2("9.81"), D2("10.92")],
          f"{who} #6456: DATEV: 10.92 on the 19 % account, 9.81 on the 7 % account, the debtor balances {bal} {amounts}")
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
    check(bal == 0 and sk == [D2("0.23")], f"{who} (b): the discount line takes the rest (0.23, was 0.22), the debtor balances {bal} {sk} {[(x['Buchungstext'], x['Umsatz (ohne Soll/Haben-Kz)'], x['Soll/Haben-Kennzeichen']) for x in mine]}")
    # ---- (c) 16 % in the second half of 2020
    c = invoice(s, cl, 100, service_to="2020-08-15")
    tl = c["totals"]["tax_lines"]
    check(len(tl) == 1 and tl[0]["pct"] == "16" and tl[0]["amount"] == "16.00", f"{who} (c): the invoice of August 2020 carries 16 % {tl}")
    dbx("UPDATE office_docs SET date='2020-08-20' WHERE id=?", (c["id"],), write=True)
    r = s.get(B + OF + "/datev/extf?from=2020-08-01&to=2020-08-31&check=1")
    hints = r.json().get("hints") or [] if r.ok else []
    odd = [h for h in hints if h.get("key") == "odd_rate"]
    check(len(odd) == 1 and c["number"] in odd[0]["text"] and "16" in odd[0]["text"] and "16.00" in odd[0]["text"].replace(",", "."),
          f"{who} (c): the DATEV check names the rate without automatic account {hints}")
    rep = s.get(B + OF + "/books/ledger?year=2020&journal=1").json()
    jr = [x for x in rep.get("journal") or [] if x.get("doc") == beleg(c["number"])]
    vat = [dd(x["amount"]) for x in jr if x.get("kind") == "vat"]
    rev = [dd(x["amount"]) for x in jr if x.get("kind") != "vat"]
    check(vat == [D2("16.00")] and rev == [D2("100.00")], f"{who} (c): the balance sheet books 100.00 + 16.00 (was 97.48 + 18.52) {jr}")
    check(any(h.get("key") == "odd_rate" for h in rep.get("hints") or []), f"{who} (c): the balance sheet names it as well {rep.get('hints')}")
    # ---- (d) the final invoice after a partial credit note
    F = abs_final(s, cl, who)
    # ---- #6445 its full credit note is the final invoice to the cent (was net x rate again: 28.50 / 178.49 -> 409)
    r = s.post(B + f"{D}/{F}/credit")
    check(r.status_code == 201, f"{who} #6445: credit draft of the final invoice " + r.text[:200])
    C1 = r.json()["id"]
    ct = s.get(B + f"{D}/{C1}").json()["totals"]
    check(ct["tax"] == "28.49" and ct["gross"] == "178.48", f"{who} #6445: the full credit note takes the final invoice's VAT {ct.get('tax')} {ct.get('gross')}")
    r = s.post(B + f"{D}/{C1}/finalize")
    check(r.ok and s.get(B + f"{D}/{F}").json()["status"] == "cancelled", f"{who} #6445: full credit note finalised, the final invoice cancelled {r.status_code} " + r.text[:200])
    # ---- #6445 a partial credit note keeping the deduction (service 100.00), then the rest (service 100.00) = the final invoice
    F3 = abs_final(s, cl, who + " 2")
    fi = s.get(B + f"{D}/{F3}").json()["items"]
    keep = [{k: x.get(k) for k in ("kind", "title", "detail", "qty", "unit", "rate", "tax")} for x in fi]
    r = s.post(B + f"{D}/{F3}/credit")
    C2 = r.json()["id"]
    r = s.put(B + f"{D}/{C2}/items", json={"items": [dict(x, rate=100) if x["kind"] == "service" else x for x in keep]})
    check(r.ok, f"{who} #6445: partial credit: service 100.00 and the deduction " + r.text[:200])
    ct = s.get(B + f"{D}/{C2}").json()["totals"]
    check(ct["net"] == "49.99" and ct["tax"] == "9.49" and ct["gross"] == "59.48",
          f"{who} #6445: partial credit 49.99 + (19.00 - 9.51) = 59.48 (was 9.50 / 59.49) {ct.get('net')} {ct.get('tax')} {ct.get('gross')}")
    check(s.post(B + f"{D}/{C2}/finalize").ok and s.get(B + f"{D}/{F3}").json()["status"] != "cancelled", f"{who} #6445: partial credit finalised, the invoice stays")
    C3 = s.post(B + f"{D}/{F3}/credit").json()["id"]
    r = s.put(B + f"{D}/{C3}/items", json={"items": [dict(x, rate=100) for x in keep if x["kind"] == "service"]})
    ct = s.get(B + f"{D}/{C3}").json()["totals"]
    check(r.ok and ct["gross"] == "119.00", f"{who} #6445: the rest 100.00 + 19.00 {ct.get('gross')}")
    r = s.post(B + f"{D}/{C3}/finalize")
    check(r.ok and s.get(B + f"{D}/{F3}").json()["status"] == "cancelled",
          f"{who} #6445: 59.48 + 119.00 = 178.48 credits the final invoice in full (was 409: 59.49 + 119.00 > 178.48) {r.status_code} " + r.text[:200])
    # ---- #6445 a rate billed in full by two progress invoices (1.03 + 0.20, 48.98 + 9.31 = 9.51 VAT of 50.01 x 19 % = 9.50):
    # the final invoice keeps the tax line with base 0 and -0.01 (was left out), its full credit note the same
    r = s.post(B + D, json={"project_title": "Kurzfilm", "client_id": cl, "service_from": DAY, "service_to": DAY})
    q = r.json()["id"]
    assert s.put(B + f"{D}/{q}/items", json={"items": [{"title": "Schnitt", "qty": 1, "unit": "flat", "rate": "50.01", "tax": "standard"}]}).ok
    for amt in ("1.03", "48.98"):
        r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "progress", "amount": amt})
        check(r.status_code == 201 and s.post(B + f"{D}/{r.json()['id']}/finalize").ok, f"{who} #6445: progress {amt} finalised " + r.text[:200])
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "final"})
    check(r.status_code == 201, f"{who} #6445: final draft over a rate billed in full " + r.text[:200])
    F4 = r.json()["id"]
    t = s.get(B + f"{D}/{F4}").json()["totals"]
    tl = t.get("tax_lines") or []
    check(t["net"] == "0.00" and t["tax"] == "-0.01" and len(tl) == 1 and tl[0]["base"] == "0.00" and tl[0]["amount"] == "-0.01",
          f"{who} #6445: base 0, the tax line -0.01 stays (was left out: 0.00) {t.get('tax')} {tl}")
    r = s.post(B + f"{D}/{F4}/finalize")
    check(r.ok, f"{who} #6445: that final invoice finalises " + r.text[:200])
    r = s.post(B + f"{D}/{F4}/credit")
    ct = s.get(B + f"{D}/{r.json()['id']}").json()["totals"] if r.status_code == 201 else {}
    check(ct.get("tax") == "-0.01" and ct.get("gross") == "-0.01", f"{who} #6445: its full credit note the same -0.01 {r.status_code} {ct.get('tax')} {ct.get('gross')}")

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
