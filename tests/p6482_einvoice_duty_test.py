#!/usr/bin/env python3
# kalmido-suite:
"""2.1359.0 (#6482 P5-4): the e-invoice duty, own container (start.sh). Invented companies and figures only.
freelancer-matrix: office
 - GET /api/office/docs/<id>/number-preview names einvoice_warn when finalising would issue a PDF-only invoice to a domestic
   business: e-invoices switched off (features_off docs.einvoice), a client with a VAT id in Germany, more than 250 EUR
 - no warning: e-invoices on, 250 EUR or less, a client without VAT id / buyer reference (a consumer), a client abroad, the
   office a small business (section 19 UStG), a quotation
 - it is only a warning: the invoice is finalised, without XML (xml_sha256 empty)
 - the procedure documentation names the dates of the duty and what the switch means for this office
 - the German pack offers the built-in text block "retention note section 14b UStG" (GET /api/office/settings: pack.blocks)
 - each for an organisation's admin and for a person without organisation (personal office)
usage: p6482_einvoice_duty_test.py <datadir>      (KMT_NOSTART=1 / P6482_NOSTART=1: a running server)"""
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import dbx as dbxm  # noqa: E402
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, DATA, check, done, fresh, setup  # noqa: E402

fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6482")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": "cal,comments,collab,office,clients,docs", "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, F = freelancer(B, A)
OFF = "/api/office"
D = OFF + "/docs"
COMPANY = {"name": "Beispiel Studio GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE",
           "email": "kontakt@example.com", "phone": "+49 30 000000", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}


def client(S, name, **kw):
    r = S.post(B + "/api/clients", json={"name": name, "street": "Marktstraße 5", "zip": "50667", "city": "Köln", "country": "DE", **kw})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def draft(S, cl, rate, kind="invoice"):
    r = S.post(B + D, json={"kind": kind, "lang": "de", "client_id": cl, "project_title": "Schnitt", "service_from": "2026-05-01",
                            "items": [{"title": "Schnitt", "qty": 1, "rate": rate}]})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def warn(S, did):
    r = S.get(B + f"{D}/{did}/number-preview")
    return r.json().get("einvoice_warn") if r.ok else f"http {r.status_code}"


for who, S in (("org admin", A), ("freelancer", F)):
    check(S.put(B + OFF + "/settings", json={"lang": "de", "currency": "EUR", "company_fields": COMPANY, "features_off": ["docs.einvoice"]}).ok,
          f"{who}: office settings, e-invoices off")
    biz = client(S, f"Firma {who} GmbH", vat_id="DE123456789")
    home = client(S, f"Privat {who}")
    abroad = client(S, f"Firma {who} SARL", vat_id="FR40303265045", street="Rue de la Paix 1", zip="75002", city="Paris", country="FR")

    did = draft(S, biz, 1000)
    w = warn(S, did)
    check(isinstance(w, str) and "2027" in w and "2028" in w, f"{who}: a business in Germany above 250 EUR without e-invoice: the warning {w!r}")
    check(not warn(S, draft(S, biz, 210)), f"{who}: 250 EUR gross or less (210 net + 19 %): no warning")
    check(not warn(S, draft(S, home, 1000)), f"{who}: a client without VAT id (a consumer): no warning")
    check(not warn(S, draft(S, abroad, 1000)), f"{who}: a client abroad: no warning")
    check(not warn(S, draft(S, biz, 1000, kind="offer")), f"{who}: a quotation: no warning")

    # only a warning: finalising goes through, the invoice has no XML
    r = S.post(B + f"{D}/{did}/finalize")
    check(r.ok, f"{who}: finalised despite the warning " + r.text[:200])
    xs = dbxm.q(DATA, "SELECT xml_sha256 FROM office_docs WHERE id=?", (did,))
    check(xs and not xs[0][0], f"{who}: the finalised invoice has no XML (e-invoices off) {xs}")
    check(not warn(S, did), f"{who}: a finalised invoice: no warning")

    pd = S.get(B + OFF + "/procdoc?lang=de").json()
    txt = " ".join(f.get("auto") or "" for sec in pd.get("sections") or [] for f in sec.get("fields") or [])
    check("01.01.2027" in txt and "800.000 EUR" in txt and "ausgeschaltet" in txt, f"{who}: the procedure documentation names the duty and the switch off")

    # the pack's built-in text block for section 14b UStG (the menu "Text" of a document)
    bl = (S.get(B + OFF + "/settings").json().get("pack") or {}).get("blocks") or []
    s14 = next((x for x in bl if x.get("key") == "s14b"), {})
    check("§ 14b" in (s14.get("de") or "") and "two years" in (s14.get("en") or "") and (s14.get("label") or {}).get("de"),
          f"{who}: the German pack offers the retention note section 14b UStG as a text block {bl}")

    check(S.put(B + OFF + "/settings", json={"small_business": 1}).ok, f"{who}: small business on")
    check(not warn(S, draft(S, biz, 1000)), f"{who}: a small business (section 19 UStG): no warning")
    check(S.put(B + OFF + "/settings", json={"small_business": 0, "features_off": []}).ok, f"{who}: small business off, e-invoices on")
    check(not warn(S, draft(S, biz, 1000)), f"{who}: e-invoices on: no warning")
    pd = S.get(B + OFF + "/procdoc?lang=de").json()
    txt = " ".join(f.get("auto") or "" for sec in pd.get("sections") or [] for f in sec.get("fields") or [])
    check("eingeschaltet" in txt, f"{who}: the procedure documentation says the switch is on")

sys.exit(done("p6482_einvoice_duty"))
