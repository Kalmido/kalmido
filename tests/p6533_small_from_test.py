#!/usr/bin/env python3
# kalmido-suite: fresh
"""#6533 (decision 16.11.2026, variant A): small business (section 19 UStG) and the VAT basis have no default in a new office,
and small business applies from a day. Invented companies and people only. freelancer-matrix: office
Played in an organisation's office and in the personal office of a person without an organisation:
 - a new office: small_business None (not chosen), vat_basis "" (not chosen); the VAT return figures count by the legal
   rule "soll" (basis soll) until a choice; GET /api/office/settings names the open drafts (open_drafts)
 - small business from a day in the future: an invoice of today with VAT finalises (was: refused, the switch counted for
   every day), the section 19 note is refused before the day; the VAT return of this year has its figures (no "small
   business") and the income statement counts net
 - the same switch without a day (as before): today's invoice with VAT is refused, the VAT return says "small business"
 - small_business_from accepts a day or "" only (400 otherwise); vat_basis "ist" / "soll" saved
usage: p6533_small_from_test.py <datadir>"""
import sys
from datetime import date

from freelancer_fixture import freelancer
from kt import B, check, done, fresh, setup

OF = "/api/office"
D = OF + "/docs"
FEAT = "cal,comments,collab,office,clients"
NO_VAT = "as a small business no VAT may be shown"
NO_NOTE = "the VAT note small business only with the switch Small business"
COMPANY = {"name": "Studio Beispiel", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "tax_number": "12/345/67890", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
YEAR = date.today().year

fresh(prefix="P6533")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEAT, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, Fr = freelancer(B, A, "erin", FEAT)  # freelancer-matrix: office (the personal office, its own admin)


def err(r):
    try:
        return r.json().get("error", "")
    except ValueError:
        return r.text


def run(who, s):
    st = s.get(B + OF + "/settings").json()
    check(st["settings"].get("small_business") is None and st["settings"].get("vat_basis") == "",
          f"{who}: a new office has chosen neither small business nor the VAT basis {st['settings'].get('small_business')!r} {st['settings'].get('vat_basis')!r}")
    r = s.get(B + OF + f"/books/ustva?year={YEAR}&period=y")
    check(r.ok and r.json().get("basis") == "soll", f"{who}: not chosen = the rule, accrual basis (was: cash) {r.text[:160]}")
    check(s.put(B + OF + "/settings", json={"lang": "de", "currency": "EUR", "payment_days": 14,
                                           "company_fields": dict(COMPANY, name=f"Studio {who}")}).ok, f"{who}: company")
    r = s.post(B + "/api/clients", json={"name": "Beispielkunde AG", "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE"})
    assert r.status_code == 201, r.text
    cl = r.json()["id"]

    def invoice(**kw):
        r = s.post(B + D, json=dict({"kind": "invoice", "client_id": cl, "service_from": f"{YEAR}-01-05", "service_to": f"{YEAR}-01-20",
                                     "vat_mode": "vat", "items": [{"title": "Schnitt", "qty": 1, "rate": 1000}]}, **kw))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def fin(did):
        return s.post(B + f"{D}/{did}/finalize")

    for bad in ("tomorrow", "2026-13-01", 5):
        check(s.put(B + OF + "/settings", json={"small_business_from": bad}).status_code == 400, f"{who}: small_business_from {bad!r}: 400")
    # ---- small business from a day in the future: today counts as before
    later = f"{YEAR + 1}-01-01"
    check(s.put(B + OF + "/settings", json={"small_business": 1, "small_business_from": later, "vat_basis": "ist"}).ok, f"{who}: small business from {later}")
    st = s.get(B + OF + "/settings").json()
    check(st["settings"]["small_business_from"] == later and st["settings"]["vat_basis"] == "ist", f"{who}: day and basis saved")
    dv = invoice()
    check(st.get("open_drafts") is not None, f"{who}: the settings name the open drafts")
    check(s.get(B + OF + "/settings").json().get("open_drafts") == 1, f"{who}: one open draft counted")
    r = fin(dv)
    check(r.ok, f"{who}: an invoice of today with VAT finalises before the day small business applies {r.status_code} {r.text[:200]}")
    ds = invoice(vat_mode="novat", vat_note="small")
    r = fin(ds)
    check(r.status_code == 400 and NO_NOTE in err(r), f"{who}: the section 19 note before the day: refused {r.text[:200]}")
    r = s.get(B + OF + f"/books/ustva?year={YEAR}&period=y")
    check(r.ok and not r.json().get("small_business") and r.json().get("basis") == "ist" and "kz" in r.json(),
          f"{who}: this year's VAT return has its figures (small business only from {later}) {r.text[:200]}")
    r = s.get(B + OF + f"/books/euer?year={YEAR}")
    check(r.ok and r.json().get("small_business") is False, f"{who}: this year's income statement counts as before {r.text[:120]}")
    r = s.get(B + OF + f"/books/ustva?year={YEAR + 1}&period=q1")
    check(r.ok and r.json().get("small_business") is True, f"{who}: next year's VAT return: small business {r.text[:120]}")
    # ---- without a day: every period, as before
    check(s.put(B + OF + "/settings", json={"small_business_from": ""}).ok, f"{who}: small business without a day")
    r = fin(invoice())
    check(r.status_code == 400 and NO_VAT in err(r), f"{who}: without a day today's invoice with VAT is refused {r.text[:200]}")
    r = s.get(B + OF + f"/books/ustva?year={YEAR}&period=y")
    check(r.ok and r.json().get("small_business") is True, f"{who}: without a day the VAT return says small business {r.text[:120]}")


run("org", A)
run("freelancer", Fr)
sys.exit(done("p6533_small_from"))
