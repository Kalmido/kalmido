#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1309.0 API tests (#6463): progress and final invoices of a quotation in a foreign currency add up to the quotation on the
cent in its currency; the database cases of #6299 live here (a hard suite: *invoice*; they were in p2354_b_abschlag, a soft one).
Once in an organisation's office (its admin) and once in the personal office of a person without an organisation
(freelancer fixture; freelancer-matrix: office). Invented companies, people and figures only.
 - #6463 USD at 0.9139, 2 x 1,250.00 less 10 % = 2,056.27 USD: two progress invoices of 50 % bill 1,028.14 + 1,028.13 (the
   last one takes the rest in USD; it billed 1,028.14 again before) and the final invoice is 0.00 (was -0.01); nothing is left
   to bill afterwards (the home-currency chain alone said 0.01 EUR)
 - #6463 the same by amounts: 1,000.00 USD, then the rest as the amount left in USD (1,056.27; was refused as more than the
   home-currency rest), mixed tax rates (19 % + 7 %): each rate's rest in USD
 - #6299 A (moved from p2354_b): HUF at 395.5, 3 x 333.33 less 10 %: the invoice from the quotation equals it to the cent (the
   rate column keeps 12 places), also after a save of the editor with the positions as read
 - #6299 B (moved): USD at 0.9139: the progress chain bills against the home run's net 2,250.00; a progress invoice of 100 %
   bills 2,250.00 EUR in rates and the quotation's 2,056.27 USD
usage: p6463_fx_abschlag_invoice_test.py <datadir>"""
import os
import sys
from decimal import Decimal

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import FEATURES, freelancer  # noqa: E402
from kt import FAILS, OKS, check, sess  # noqa: E402
import requests  # noqa: E402

B = "http://127.0.0.1:" + os.environ.get("KALMIDO_TEST_PORT", "3048")
H = {"X-Requested-With": "kalmido"}
OFC = "/api/office"
D = OFC + "/docs"
IBAN = "DE02120300000000202051"


def dd(v):
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def company(s, name):
    r = s.put(B + OFC + "/settings", json={"lang": "de", "currency": "EUR", "company_fields": {
        "name": name, "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE", "tax_number": "12/345/67890",
        "iban": IBAN, "bic": "BYLADEM1001", "bank_name": "Beispielbank"}})
    assert r.ok, r.text


def client(s, name):
    r = s.post(B + "/api/clients", json={"name": name, "street": "Kundenweg 5", "zip": "20000", "city": "Beispielstadt", "country": "DE"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def quote(s, cl, cur, fx, items):
    r = s.post(B + D, json={"project_title": "Fremd", "client_id": cl, "service_from": "2026-10-01", "service_to": "2026-10-20"})
    assert r.status_code == 201, r.text
    q = r.json()["id"]
    assert s.put(B + f"{D}/{q}/items", json={"items": items}).ok
    r = s.patch(B + f"{D}/{q}", json={"currency": cur, "fx_rate": fx, "discount_pct": 10})
    assert r.ok, r.text
    return q, r.json()["totals"]


def bases(t):
    """{tax key: net} of a document's totals (its tax lines), in its currency"""
    return {x["rate_key"]: dd(x["base"]) for x in t.get("tax_lines") or []}


def progress(s, q, label, what, **body):
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "progress", **body})
    check(r.status_code == 201, f"{label} {what}: progress draft " + r.text[:200])
    if r.status_code != 201:
        return {}
    did = r.json()["id"]
    r = s.post(B + f"{D}/{did}/finalize")
    check(r.ok, f"{label} {what}: progress finalised " + r.text[:200])
    return s.get(B + f"{D}/{did}").json()


def rest_6463(s, cl, label):
    """#6463: the last progress invoice takes the rest in the quotation's currency."""
    q, qt = quote(s, cl, "USD", "0.9139", [{"title": "Dreh", "qty": 2, "unit": "day", "rate": 1250, "tax": "standard"}])
    check(dd(qt["net"]) == Decimal("2056.27"), f"{label} #6463 A: the quotation 2,056.27 USD {qt['net']}")
    p1 = progress(s, q, label, "#6463 A 50 %", pct=50)
    p2 = progress(s, q, label, "#6463 A 50 %", pct=50)
    n1, n2 = dd((p1.get("totals") or {}).get("net")), dd((p2.get("totals") or {}).get("net"))
    check((n1, n2) == (Decimal("1028.14"), Decimal("1028.13")), f"{label} #6463 A: 1,028.14 + the rest 1,028.13 USD (was 2 x 1,028.14) {n1} {n2}")
    pr = s.get(B + f"{D}/{q}/progress").json()
    check(dd(pr.get("remaining")) == 0, f"{label} #6463 A: nothing left to bill (the home run alone said 0.01) {pr.get('remaining')}")
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "progress", "pct": 1})
    check(r.status_code == 400, f"{label} #6463 A: no further progress invoice {r.status_code}")
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "final"})
    check(r.status_code == 201, f"{label} #6463 A: final draft " + r.text[:200])
    if r.status_code == 201:
        ft = r.json()["totals"]
        check(dd(ft["net"]) == 0 and dd(ft["gross"]) == 0, f"{label} #6463 A: the final invoice is 0.00 / 0.00 (was -0.01) {ft['net']} / {ft['gross']}")
        check(n1 + n2 + dd(ft["net"]) == dd(qt["net"]), f"{label} #6463 A: progress + final = the quotation on the cent")

    # by amounts, two tax rates: 1,000.00 USD, then the amount left in USD
    q, qt = quote(s, cl, "USD", "0.9139", [{"title": "Dreh", "qty": 2, "unit": "day", "rate": 1250, "tax": "standard"},
                                           {"title": "Buch", "qty": 1, "unit": "flat", "rate": 333.33, "tax": "reduced"}])
    want = bases(qt)
    p1 = progress(s, q, label, "#6463 B 1000 USD", amount=1000)
    got1 = bases(p1.get("totals") or {})
    left = dd(qt["net"]) - dd((p1.get("totals") or {}).get("net"))
    p2 = progress(s, q, label, f"#6463 B the rest {left} USD", amount=str(left))
    got2 = bases(p2.get("totals") or {})
    tot = {k: got1.get(k, 0) + got2.get(k, 0) for k in want}
    check(tot == want, f"{label} #6463 B: per rate, the two progress invoices bill the quotation exactly {tot} {want}")
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "final"})
    ft = r.json()["totals"] if r.status_code == 201 else {}
    # the net is 0.00; its VAT is the VAT of the whole less what the progress invoices billed (section 14 (5) UStG, #6303 d),
    # so their rounding cent may stay there: all three together are the quotation's gross on the cent
    gross = dd((p1.get("totals") or {}).get("gross")) + dd((p2.get("totals") or {}).get("gross")) + dd(ft.get("gross"))
    check(r.status_code == 201 and dd(ft.get("net")) == 0 and gross == dd(qt["gross"]),
          f"{label} #6463 B: the final invoice's net 0.00, progress + final gross = the quotation's {gross} {qt['gross']} (final {ft.get('net')} / {ft.get('gross')})")


def fx_cents(s, cl, label):
    """2.1254.0 (#6299, review), moved from p2354_b_abschlag (#6463): a quotation in a foreign currency with a document discount.
    A) HUF at 395.5, 3 x 333.33 less 10 %: the invoice takes the discount as 39,549.61 HUF / 395.5 = 99.99901... per unit; the
       database kept 4 places (99.9990 -> 39,549.60, net 355,946.45 instead of 355,946.44). Now office_doc_items.rate keeps 12
       places: the invoice's net / gross equal the quotation's, also after a save of the editor with the positions as read.
    B) USD at 0.9139, 2 x 1,250 less 10 %: a chain of progress invoices bills against the home-currency net of the run in the
       home currency (2,250.00); the back-converted rates of the invoice gave 2,249.99 (228.48 USD / 0.9139 = 250.01)."""
    q, qt = quote(s, cl, "HUF", "395.5", [{"title": "Dreh", "qty": 3, "unit": "day", "rate": 333.33, "tax": "standard"}])
    want = (dd(qt["net"]), dd(qt["gross"]))
    check(want == (Decimal("355946.44"), Decimal("423576.26")), f"{label} #6299 A: the quotation 355,946.44 / 423,576.26 HUF {want}")
    r = s.post(B + f"{D}/{q}/invoice", json={})
    check(r.status_code == 201, f"{label} #6299 A: invoice from the HUF quotation " + r.text[:200])
    inv = r.json()
    it = inv["totals"]
    check((dd(it["net"]), dd(it["gross"])) == want, f"{label} #6299 A: the invoice equals it (4 places: 355,946.45) {it['net']} / {it['gross']}")
    doc = s.get(B + f"{D}/{inv['id']}").json()
    keep = ("id", "kind", "service_id", "title", "detail", "qty", "unit", "rate", "tax", "intext", "discountable")
    r = s.put(B + f"{D}/{inv['id']}/items", json={"items": [{k: x.get(k) for k in keep} for x in doc["items"]], "expect_updated_at": doc["updated_at"]})
    it = (r.json().get("totals") or {}) if r.ok else {}
    check(r.ok and (dd(it.get("net")), dd(it.get("gross"))) == want, f"{label} #6299 A: saved again as the editor read it: the same {r.status_code} {it.get('net')}")
    q, qt = quote(s, cl, "USD", "0.9139", [{"title": "Dreh", "qty": 2, "unit": "day", "rate": 1250, "tax": "standard"}])
    pr = s.get(B + f"{D}/{q}/progress").json()
    check(pr.get("net") == "2250.00", f"{label} #6299 B: the progress chain's net is the home run's 2,250.00 (was 2,249.99) {pr.get('net')}")
    r = s.post(B + f"{D}/{q}/invoice", json={"inv_type": "progress", "pct": 100})
    # 2.1309.0 (#6463): a progress invoice of 100 % is the last one: it bills the quotation's 2,056.27 USD (its rates in EUR add
    # up to 2,249.99: 2,056.27 / 0.9139); it billed 2,250.00 EUR = 2,056.28 USD before, a cent more than the quotation
    check(r.status_code == 201 and dd(r.json()["totals"]["net"]) == dd(qt["net"]) == Decimal("2056.27"),
          f"{label} #6299 B / #6463: a progress invoice of 100 % bills the quotation's 2,056.27 USD {r.status_code} {r.text[:160] if r.status_code != 201 else r.json()['totals']['net']}")


def flow(s, label):
    cl = client(s, "Fremdkunde " + label + " GmbH")
    rest_6463(s, cl, label)
    fx_cents(s, cl, label)


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
company(A, "Beispiel Studio GmbH")
flow(A, "org")
FID, Fr = freelancer(B, A)
company(Fr, "Frida Film")
flow(Fr, "freelancer")
print(f"p6463_fx_abschlag_invoice: {OKS[0]} ok, {len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
