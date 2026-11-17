#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1259.0 A (#6301, #6302, audit #4740 F3 / F4): the books take the frozen sums of the documents. Invented names and figures only.
freelancer-matrix: office
 - #6301: three invoices of 33.34 / 33.33 / 33.33 net at 19 % (frozen: 100.00 net, 18.99 VAT), each paid in full: the
   income statement shows 100.00 / 18.99 (was 99.99 / 19.00, recomputed from the gross), field 81 of the VAT return on
   the cash basis 100 (was 99), the key figures 100.00 net -- the same figure as the income statement; on the accrual
   basis ("soll") field 81 = 100 too (the frozen bases of the documents)
 - #6301: two rates (10.00 at 19 % + 10.00 at 7 %, EUR) paid in three parts: exactly 10.00 / 1.90 and 10.00 / 0.70; an old
   invoice without frozen tax lines keeps the old way (books: its gross as tax-free revenue, key figures: net / gross)
 - #6456: a foreign currency (USD, rate 1.09) follows one rule (books.bk_fx_lines): gross = money(gross / rate), tax per
   rate converted, the rest cent on the base of the largest rate: 10.00 + 1.90 USD paid in three parts = 9.18 + 1.74 =
   10.92 EUR (was 9.17 + 1.74 = 10.91, the money received is 10.92); two rates 22.60 USD = 9.18 / 1.74 + 9.17 / 0.64 =
   20.73; a credit note refunded in full takes exactly the same back; a cash discount on the accrual basis: 1003.24 USD
   net, 2 % = field 81 901 (base 920.40 less its share of the discount; was 902)
 - #6302: a finalised reminder with fee 5.00, default interest and the flat fee (40 - 5 credited = 35.00) marked "fee paid":
   the income statement (reminder fees), the key figures, the cash flow and the ledger count fee + interest + flat fee
   (was 5.00 alone), the VAT return not; a reminder without a fee (only interest and 40.00 flat fee) shows them open and
   can be marked paid (was 409), it counts the same way
 - #6459: the paid amount is stored on the reminder when it is marked paid; a reminder marked paid before 2.1259 (nothing
   stored) keeps its fee alone; two levels over the same invoice, both paid: the second adds only its fee (interest and
   flat fee were counted with the first)
 - the same for a person without an organisation (own office)
usage: p21259_a_office_books_test.py <datadir>"""
import json
import os
import subprocess
from datetime import date, timedelta
from decimal import Decimal
import sys

import requests

import dbx as dbxm
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
    r = s.put(B + OF + "/settings", json={"company": {"name": COMPANY["name"]}, "lang": "en", "currency": "EUR", "company_fields": COMPANY,
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
    return next((m["amount"] for m in s.get(B + OF + "/kpi").json()["revenue"]["months"] if m["month"] == TODAY[:7]), None)


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
    r = s.put(B + OF + "/settings", json={"vat_basis": "soll"})
    check(r.ok, f"{who}: accrual basis " + r.text[:200])
    kz = ustva(s, "y").get("kz", {})
    check(kz.get("81") == "100" and kz.get("86") == "0", f"{who}: accrual basis: field 81 = 100 from the frozen bases (was 99) {kz}")
    s.put(B + OF + "/settings", json={"vat_basis": "ist"})


# ---------------------------------------------------------------- #6301 (several rates, old documents), #6456 (foreign currency)
def euer_rows(s):
    eu = s.get(B + BK + f"/euer?year={Y}").json()
    return {x["key"]: (Decimal(x["net"]), Decimal(x["vat"]), Decimal(x["gross"])) for x in eu["income"]}


def delta(before, after, key):
    z = (Decimal(0),) * 3
    return tuple(a - b for a, b in zip(after.get(key, z), before.get(key, z)))


def doc(s, cl, items, cur=None, fx=None, extra=None):
    b = {"kind": "invoice", "client_id": cl, "project_title": "Fremd", "service_from": TODAY, "items": items, **(extra or {})}
    if cur:
        b.update(currency=cur, fx_rate=fx)
    r = s.post(B + D, json=b)
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    check(s.post(B + f"{D}/{did}/finalize").ok, f"document {did} finalised")
    return did


def pay(s, did, *amounts):
    for a in amounts:
        r = s.post(B + f"{D}/{did}/payments", json={"date": TODAY, "amount": a, "method": "transfer"})
        check(r.status_code == 201, f"payment {a} on {did} " + r.text[:200])


USD10 = "9.1743"  # a position's rate is typed in the office currency: x 1.09 = 10.00 USD (calc.inv_calc)


def rates_and_currency(s, who):
    cl = client(s, f"{who} Studio Übersee")
    two = [{"title": "Schnitt", "qty": 1, "rate": "10.00"}, {"title": "Buch", "qty": 1, "rate": "10.00", "tax": "reduced"}]
    # #6301: two rates in EUR, paid in three parts
    e0 = euer_rows(s)
    pay(s, doc(s, cl, two), "7.53", "7.53", "7.54")
    e1 = euer_rows(s)
    check(delta(e0, e1, "vat19") == (Decimal("10.00"), Decimal("1.90"), Decimal("11.90")) and delta(e0, e1, "vat7") == (Decimal("10.00"), Decimal("0.70"), Decimal("10.70")),
          f"{who}: two rates in three parts: exactly 10.00 / 1.90 and 10.00 / 0.70 {delta(e0, e1, 'vat19')} {delta(e0, e1, 'vat7')}")
    # #6301: an old invoice without frozen tax lines keeps the old way
    old = doc(s, cl, [{"title": "Alt", "qty": 1, "rate": 100}])
    t = json.loads(dbxm.q(DATA, "SELECT totals FROM office_docs WHERE id=?", (old,))[0][0])
    check(t.pop("tax_lines", None), f"{who}: the old invoice had tax lines before")
    dbxm.q(DATA, "UPDATE office_docs SET totals=? WHERE id=?", (json.dumps(t), old))
    k0 = Decimal(kpi_month(s))
    pay(s, old, "119.00")
    e2 = euer_rows(s)
    check(delta(e1, e2, "exempt") == (Decimal("119.00"), Decimal("0.00"), Decimal("119.00")) and delta(e1, e2, "vat19") == (Decimal(0),) * 3,
          f"{who}: an old invoice without tax lines: as before (gross as tax-free revenue) {delta(e1, e2, 'exempt')}")
    check(Decimal(kpi_month(s)) - k0 == Decimal("100.00"), f"{who}: key figures of the old invoice: net / gross as before {Decimal(kpi_month(s)) - k0}")
    # #6456: USD at 1.09, one rate, three parts
    usd = doc(s, cl, [{"title": "Edit", "qty": 1, "rate": USD10}], "USD", "1.09")
    check(json.loads(dbxm.q(DATA, "SELECT totals FROM office_docs WHERE id=?", (usd,))[0][0]).get("gross") == "11.90", f"{who}: the USD invoice is 10.00 + 1.90 = 11.90 USD")
    pay(s, usd, "3.97", "3.97", "3.96")
    e3 = euer_rows(s)
    check(delta(e2, e3, "vat19") == (Decimal("9.18"), Decimal("1.74"), Decimal("10.92")),
          f"{who}: USD 11.90 / 1.09: 9.18 + 1.74 = 10.92 = the money received (was 9.17 + 1.74 = 10.91) {delta(e2, e3, 'vat19')}")
    # #6456: two rates in USD
    two_usd = [dict(x, rate=USD10) for x in two]
    pay(s, doc(s, cl, two_usd, "USD", "1.09"), "22.60")
    e4 = euer_rows(s)
    check(delta(e3, e4, "vat19") == (Decimal("9.18"), Decimal("1.74"), Decimal("10.92")) and delta(e3, e4, "vat7") == (Decimal("9.17"), Decimal("0.64"), Decimal("9.81")),
          f"{who}: USD two rates 22.60 / 1.09 = 20.73: the rest cent on the base at 19 % {delta(e3, e4, 'vat19')} {delta(e3, e4, 'vat7')}")
    # #6456: a credit note on the USD invoice, refunded in full: exactly the same back
    r = s.post(B + f"{D}/{usd}/credit")
    check(r.status_code == 201, f"{who}: credit note draft " + r.text[:200])
    cr = r.json()["id"]
    check(s.post(B + f"{D}/{cr}/finalize").ok, f"{who}: credit note finalised")
    pay(s, cr, "11.90")
    e5 = euer_rows(s)
    check(delta(e4, e5, "vat19") == (Decimal("-9.18"), Decimal("-1.74"), Decimal("-10.92")),
          f"{who}: the refund takes back exactly 9.18 + 1.74 {delta(e4, e5, 'vat19')}")


def skonto_fx():
    """#6456 / #6301: a cash discount on the accrual basis in USD (an office of its own: field 81 in whole euros)."""
    _, G = freelancer(B, A, "gina")
    office(G)
    check(G.put(B + OF + "/settings", json={"vat_basis": "soll"}).ok, "Gina: accrual basis")
    cl = client(G, "Gina Kunde USA")
    # the rate in EUR: 920.4037 x 1.09 = 1003.24 USD
    did = doc(G, cl, [{"title": "Film", "qty": 1, "rate": "920.4037"}], "USD", "1.09", {"skonto_pct": 2, "skonto_days": 10, "payment_days": 14})
    t = G.get(B + f"{D}/{did}").json()["totals"]
    check(t["gross"] == "1193.86", f"Gina: gross 1193.86 USD {t.get('gross')}")
    pay(G, did, "1169.98")
    check(G.get(B + f"{D}/{did}").json()["status"] == "paid", "Gina: paid in time less 2 % = paid")
    kz = ustva(G, "y").get("kz", {})
    check(kz.get("81") == "901", f"Gina: field 81 = 920.40 less 18.41 of the discount = 901 (was 902) {kz.get('81')}")


# ---------------------------------------------------------------- #6302: fee + interest + flat fee of a reminder
def fee_income(s):
    eu = s.get(B + BK + f"/euer?year={Y}").json()
    return Decimal(next((x["net"] for x in eu["income"] if x["key"] == "fee"), "0"))


def reminder(s, cl, who, fee):
    inv = invoice(s, cl, 500, f"Dreh {fee}")
    dbxm.q(DATA, "UPDATE office_docs SET due_date=? WHERE id=?", ((date.fromisoformat(TODAY) - timedelta(days=30)).isoformat(), inv))
    r = s.post(B + D + "/reminder", json={"doc_ids": [inv], "level": 2, "fee": fee})
    check(r.ok, f"{who}: reminder with fee {fee} " + r.text[:200])
    rm = r.json()["id"]
    check(s.post(B + f"{D}/{rm}/finalize").ok, f"{who}: reminder finalised")
    t = s.get(B + f"{D}/{rm}").json()
    claim = Decimal(t["totals"]["fee"]) + Decimal(t["totals"]["interest"]) + Decimal(t["totals"]["flat_fee"])
    return rm, t, claim


def reminder_claims(s, who):
    check(s.put(B + OF + "/settings", json={"dunning_interest": 1, "dunning_flat_fee": 1, "base_rate": "1,52",
                                           "dunning_client_kind": "business"}).ok, f"{who}: default interest + flat fee on")
    cl = client(s, f"{who} Agentur")
    rm, t, claim = reminder(s, cl, who, 5)
    tt = t["totals"]
    check(tt["fee"] == "5.00" and Decimal(tt["interest"]) > 0 and tt["flat_fee"] == "35.00", f"{who}: fee 5.00, interest, flat fee 35.00 {tt.get('interest')} {tt.get('flat_fee')}")
    check(t.get("fee_open") == str(claim), f"{who}: open: fee + interest + flat fee {t.get('fee_open')} {claim}")
    fee0, k0 = fee_income(s), Decimal(kpi_month(s))
    kz0 = ustva(s, "y").get("kz", {})
    r = s.post(B + f"{D}/{rm}/fee", json={"state": "paid"})
    check(r.ok and r.json().get("fee_open") == "0.00", f"{who}: marked paid " + r.text[:200])
    check(fee_income(s) - fee0 == claim, f"{who}: income statement: fee + interest + flat fee {claim} (was 5.00 alone) {fee_income(s) - fee0}")
    check(Decimal(kpi_month(s)) - k0 == claim, f"{who}: key figures: + {claim} {Decimal(kpi_month(s)) - k0}")
    cf = s.get(B + OF + f"/cashflow?from={TODAY[:7]}&months=1").json()
    ent = [e for e in cf.get("entries", []) if e.get("kind") == "fee" and e.get("doc_id") == rm]
    check(ent and Decimal(ent[0]["amount"]) == claim, f"{who}: cash flow: the whole claim came in {ent}")
    led = s.get(B + BK + f"/ledger?year={Y}&journal=1").json()
    fr = [x for x in led.get("journal", []) if x["src"] == "fee"]
    check(sum((Decimal(x["amount"]) for x in fr), Decimal(0)) == claim, f"{who}: ledger: the paid claim as other income {fr}")
    # 2.1352.0 (#6599): the DATEV batch has the paid claim, too (was missing: ledger and batch differed by it), on the day
    # it was marked paid, without VAT key, clearing account 1590 against the fee income 2700 (SKR03) as the ledger
    check(s.put(B + OF + "/settings", json={"datev_extf": {"advisor_no": "1234567", "client_no": "12345", "fy_start": 1, "acct_len": 4,
                                                             "chart": "SKR03"}}).ok, f"{who}: DATEV numbers set")
    r = s.get(B + OF + f"/datev/extf?from={TODAY}&to={TODAY}&in=0")
    num = s.get(B + f"{D}/{rm}").json().get("number") or ""
    rows = [ln.split(";") for ln in r.content.decode("cp1252").splitlines() if f'"Mahnforderung {num}' in ln] if r.ok and num else []
    amt = format(claim, "f").replace(".", ",")
    check(len(rows) == 1 and rows[0][0] == amt and rows[0][1] == '"S"' and rows[0][6] == "1590" and rows[0][7] == "2700"
          and rows[0][8] in ("", '""'), f"{who}: DATEV batch: the paid claim {amt} once, 1590 against 2700, no VAT key {r.status_code} {rows}")
    led_fee = [x for x in fr if x.get("debit") == "1590" and x.get("credit") == "2700"] if fr and "debit" in fr[0] else fr
    check(len(led_fee) == len(fr), f"{who}: ledger and DATEV batch book the claim alike {fr}")
    # #6459: the amount is stored when marked paid; a mark of before 2.1259 (nothing stored) keeps its fee alone
    st_amt = dbxm.q(DATA, "SELECT reminder_fee_paid_amount FROM office_docs WHERE id=?", (rm,))[0][0]
    check(st_amt is not None and Decimal(str(st_amt)) == claim, f"{who}: the paid amount is stored on the reminder {st_amt} {claim}")
    dbxm.q(DATA, "UPDATE office_docs SET reminder_fee_paid_amount=NULL WHERE id=?", (rm,))
    check(fee_income(s) - fee0 == Decimal("5.00"), f"{who}: a reminder marked paid before 2.1259: its fee alone, the old year stays {fee_income(s) - fee0}")
    check(s.get(B + f"{D}/{rm}").json().get("claim") == "5.00", f"{who}: the view of such a reminder shows the 5.00 the books count {s.get(B + f'{D}/{rm}').json().get('claim')}")
    dbxm.q(DATA, "UPDATE office_docs SET reminder_fee_paid_amount=? WHERE id=?", (str(claim), rm))
    kz1 = ustva(s, "y").get("kz", {})
    check(kz1.get("81") == kz0.get("81") and kz1.get("83") == kz0.get("83"), f"{who}: not in the VAT return {kz0.get('81')} {kz1.get('81')}")
    # a reminder without a fee: only interest and the flat fee 40.00
    rm0, t0, claim0 = reminder(s, cl, who, 0)
    check(t0["totals"]["fee"] == "0.00" and t0["totals"]["flat_fee"] == "40.00" and t0.get("fee_open") == str(claim0),
          f"{who}: no fee, interest + 40.00 open {t0['totals'].get('flat_fee')} {t0.get('fee_open')} {claim0}")
    fee1 = fee_income(s)
    r = s.post(B + f"{D}/{rm0}/fee", json={"state": "paid"})
    check(r.ok, f"{who}: a reminder without a fee can be marked paid (was 409) {r.status_code} {r.text[:200]}")
    check(fee_income(s) - fee1 == claim0, f"{who}: income statement: + interest + 40.00 = {claim0} {fee_income(s) - fee1}")
    check(s.post(B + f"{D}/{rm0}/fee", json={"state": ""}).ok and fee_income(s) == fee1, f"{who}: opened again: out of the income statement")
    check(dbxm.q(DATA, "SELECT reminder_fee_paid_amount FROM office_docs WHERE id=?", (rm0,))[0][0] is None, f"{who}: opened again: the stored amount is gone")
    # #6459: two reminder levels over the same invoice, both paid: interest and flat fee count once
    inv = invoice(s, cl, 500, "Zwei Stufen")
    dbxm.q(DATA, "UPDATE office_docs SET due_date=? WHERE id=?", ((date.fromisoformat(TODAY) - timedelta(days=30)).isoformat(), inv))
    lv = []
    for level, fee in ((2, 5), (3, 10)):
        r = s.post(B + D + "/reminder", json={"doc_ids": [inv], "level": level, "fee": fee})
        check(r.ok, f"{who}: reminder level {level} " + r.text[:200])
        check(s.post(B + f"{D}/{r.json()['id']}/finalize").ok, f"{who}: reminder level {level} finalised")
        t = s.get(B + f"{D}/{r.json()['id']}").json()["totals"]
        lv.append((r.json()["id"], Decimal(t["fee"]) + Decimal(t["interest"]) + Decimal(t["flat_fee"])))
    f0 = fee_income(s)
    check(s.post(B + f"{D}/{lv[0][0]}/fee", json={"state": "paid"}).ok and fee_income(s) - f0 == lv[0][1], f"{who}: level 2 paid: + {lv[0][1]} {fee_income(s) - f0}")
    f1 = fee_income(s)
    check(s.post(B + f"{D}/{lv[1][0]}/fee", json={"state": "paid"}).ok, f"{who}: level 3 paid")
    check(s.get(B + f"{D}/{lv[1][0]}").json().get("claim") == "10.00", f"{who}: the paid level 3 shows the 10.00 the books count {s.get(B + f'{D}/{lv[1][0]}').json().get('claim')}")
    check(fee_income(s) - f1 == Decimal("10.00"), f"{who}: level 3 adds its fee 10.00 only, interest and flat fee were counted with level 2 (claim {lv[1][1]}) {fee_income(s) - f1}")


frozen_lines(A, "Alpha")
frozen_lines(Fr, "Frida")
rates_and_currency(A, "Alpha")
rates_and_currency(Fr, "Frida")
skonto_fx()
reminder_claims(A, "Alpha")
reminder_claims(Fr, "Frida")

print(f"p21259_a_office_books: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
