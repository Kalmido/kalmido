#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1308.0 (#6476, #6477): what finalising an invoice refuses before the e-invoice is frozen. Invented companies only.
freelancer-matrix: office
 - #6476 XRechnung (the client has a Leitweg ID): without the company's phone / e-mail and without the client's e-mail
   finalising answers 400 and names them in plain words; nothing is half done (no number, still a draft, not locked); with
   them it goes through and the stored XML passes the own check (einvoice.ein_check)
 - #6477 an invoice without a client: the recipient's fixed fields (street, postcode, city, country); without the postcode
   400 "postcode of the recipient"; two free lines that are no address ("attn.", a town) are refused; a plain address in
   free lines is read into the fields; the XML carries street, postcode and city of the fields; the correction of such an
   invoice inherits the fields and is finalised; a quotation without a client keeps its free lines
 - the same as a person without an organisation (personal office)
usage: p6476_einvoice_finalize_test.py      (P6476_NOSTART=1 / KMT_NOSTART=1: a running server)"""
import importlib.util
import os
import sys

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
from freelancer_fixture import freelancer  # noqa: E402
from kt import B, check, done, fresh, setup  # noqa: E402

SRC = os.environ.get("KALMIDO_SRC") or os.path.join(N, "..")
spec = importlib.util.spec_from_file_location("einvoice", os.path.join(SRC, "kalmido", "office", "einvoice.py"))
ein = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ein)
OFF = "/api/office"
D = OFF + "/docs"
BUYER = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty/ram:PostalTradeAddress/"
COMPANY = {"name": "Beispiel Studio GmbH", "street": "Musterweg 1", "zip": "12345", "city": "Musterstadt", "country": "DE",
           "tax_number": "12/345/67890", "vat_id": "DE999999999", "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
ITEMS = [{"title": "Filmherstellung", "qty": 2, "unit": "day", "rate": 1000}]
HEAD = {"kind": "invoice", "project_title": "Imagefilm", "service_from": "2026-05-01", "service_to": "2026-05-31", "date": "2026-05-08", "payment_days": 14}

fresh({"KALMIDO_INSTANCE_MODE": "workspaces"}, prefix="P6476")
A = setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": "cal,comments,collab,office,clients,docs", "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"})
FID, F = freelancer(B, A)


def xml_text(xml, path):
    import xml.etree.ElementTree as ET
    try:
        x = ET.fromstring(xml).find(path, ein.NS)
    except ET.ParseError:
        return None
    return (x.text or "").strip() if x is not None else None


def draft(S, who, items=ITEMS, **head):
    r = S.post(B + D, json={**HEAD, **head})
    check(r.status_code == 201, f"{who}: the draft " + r.text[:160])
    did = r.json().get("id")
    r = S.put(B + f"{D}/{did}/items", json={"items": items})
    check(r.ok, f"{who}: its positions " + r.text[:160])
    return did


def untouched(S, who, did):
    """#6476: a refused finalising leaves no half state: no number, a draft, not locked, no stored XML."""
    d = S.get(B + f"{D}/{did}").json()
    check(not d.get("number") and d.get("status") == "draft" and not d.get("locked"),
          f"{who}: nothing half done (number {d.get('number')!r}, status {d.get('status')}, locked {d.get('locked')})")
    check(S.get(B + f"{D}/{did}/xml").status_code != 200, f"{who}: no e-invoice XML of a draft")


def run(S, who):
    r = S.put(B + OFF + "/settings", json={"lang": "de", "currency": "EUR", "company_fields": COMPANY})
    check(r.ok, f"{who}: office settings without phone and e-mail " + r.text[:160])
    r = S.post(B + "/api/clients", json={"name": "Behörde Beispiel", "street": "Amtsweg 3", "zip": "54321", "city": "Beispielort", "country": "DE",
                                        "buyer_reference": "04011000-12345-03"})
    check(r.status_code == 201, f"{who}: a client with a Leitweg ID, no e-mail " + r.text[:160])
    cid = r.json().get("id")

    # ---------------------------------------------------------------- #6476 XRechnung without its mandatory data
    did = draft(S, who, client_id=cid)
    check(S.get(B + f"{D}/{did}").json().get("einvoice_format") == "xrechnung", f"{who}: the Leitweg ID makes it XRechnung")
    r = S.post(B + f"{D}/{did}/finalize")
    msg = r.json().get("error", "") if r.headers.get("content-type", "").startswith("application/json") else r.text
    check(r.status_code == 400, f"{who} #6476: XRechnung without phone / e-mail is refused ({r.status_code}) {msg[:200]}")
    check("phone and e-mail of your company" in msg and "the client's invoice e-mail" in msg,
          f"{who} #6476: the refusal names the company's phone / e-mail and the client's e-mail: {msg[:300]}")
    untouched(S, who, did)
    r = S.put(B + OFF + "/settings", json={"company_fields": {**COMPANY, "phone": "+49 30 000000", "email": "kontakt@example.com"}})
    check(r.ok, f"{who}: the company's phone and e-mail " + r.text[:160])
    r = S.patch(B + f"/api/clients/{cid}", json={"email_invoice": "rechnung@example.com"})
    check(r.ok, f"{who}: the client's invoice e-mail " + r.text[:160])
    r = S.post(B + f"{D}/{did}/finalize")
    check(r.ok and r.json().get("number"), f"{who} #6476: with them it is finalised " + r.text[:200])
    x = S.get(B + f"{D}/{did}/xml")
    check(x.ok and ein.ein_check(x.content) == [], f"{who} #6476: the stored XRechnung passes the own check {ein.ein_check(x.content) if x.ok else x.status_code}")

    # ---------------------------------------------------------------- #6477 an invoice without a client: fixed fields
    did = draft(S, who, recipient={"name": "Musterfirma GmbH", "street": "Weg 2", "extra": "z. Hd. Frau Muster", "zip": "", "city": "Berlin", "country": "DE"})
    rec = S.get(B + f"{D}/{did}").json().get("recipient") or {}
    check(rec.get("street") == "Weg 2" and rec.get("city") == "Berlin" and rec.get("lines") == ["Musterfirma GmbH", "Weg 2", "z. Hd. Frau Muster", "Berlin"],
          f"{who} #6477: the fixed fields are stored and printed as lines {rec}")
    r = S.post(B + f"{D}/{did}/finalize")
    msg = r.json().get("error", "") if r.headers.get("content-type", "").startswith("application/json") else r.text
    check(r.status_code == 400 and "postcode of the recipient" in msg, f"{who} #6477: without a postcode refused with a clear word ({r.status_code}) {msg[:200]}")
    untouched(S, who, did)
    r = S.patch(B + f"{D}/{did}", json={"recipient": {"name": "Musterfirma GmbH", "street": "Weg 2", "extra": "z. Hd. Frau Muster", "zip": "10115", "city": "Berlin", "country": ""}})
    check(r.ok, f"{who} #6477: the postcode added " + r.text[:160])
    r = S.post(B + f"{D}/{did}/finalize")
    check(r.ok and r.json().get("number"), f"{who} #6477: with street, postcode and city it is finalised " + r.text[:200])
    x = S.get(B + f"{D}/{did}/xml")
    xml = x.content if x.ok else b""
    check(xml_text(xml, BUYER + "ram:LineOne") == "Weg 2" and xml_text(xml, BUYER + "ram:PostcodeCode") == "10115"
          and xml_text(xml, BUYER + "ram:CityName") == "Berlin" and xml_text(xml, BUYER + "ram:LineTwo") == "z. Hd. Frau Muster"
          and xml_text(xml, BUYER + "ram:CountryID") == "DE", f"{who} #6477: the XML carries the fields {xml[:0]}")
    check(ein.ein_check(xml) == [], f"{who} #6477: the own check finds nothing {ein.ein_check(xml)}")
    snap = S.get(B + f"{D}/{did}").json()
    check(snap.get("locked"), f"{who} #6477: finalised")
    # the correction inherits the recipient and is finalised
    r = S.post(B + f"{D}/{did}/credit")
    check(r.status_code == 201, f"{who} #6477: a correction draft " + r.text[:160])
    if r.status_code == 201:
        crd = r.json()["id"]
        r = S.post(B + f"{D}/{crd}/finalize")
        check(r.ok and r.json().get("number"), f"{who} #6477: the correction of an invoice without a client is finalised " + r.text[:200])
        x = S.get(B + f"{D}/{crd}/xml")
        check(x.ok and xml_text(x.content, BUYER + "ram:PostcodeCode") == "10115", f"{who} #6477: the correction's XML has the postcode")

    # free lines that are no address: refused; a plain address in free lines: read into the fields
    did = draft(S, who, recipient={"name": "Musterfirma GmbH", "lines": ["z. Hd. X", "Berlin"]})
    r = S.post(B + f"{D}/{did}/finalize")
    msg = r.json().get("error", "") if r.headers.get("content-type", "").startswith("application/json") else r.text
    check(r.status_code == 400 and "postcode of the recipient" in msg and "street of the recipient" in msg,
          f"{who} #6477: two free lines without an address are refused ({r.status_code}) {msg[:200]}")
    untouched(S, who, did)
    did = draft(S, who, recipient={"name": "Musterfirma GmbH", "lines": ["Musterfirma GmbH", "Weg 2", "10115 Berlin"]})
    rec = S.get(B + f"{D}/{did}").json().get("recipient") or {}
    check(rec.get("street") == "Weg 2" and rec.get("zip") == "10115" and rec.get("city") == "Berlin", f"{who} #6477: a plain address read into the fields {rec}")
    r = S.post(B + f"{D}/{did}/finalize")
    check(r.ok, f"{who} #6477: and finalised " + r.text[:200])

    # a quotation without a client keeps its free lines
    r = S.post(B + D, json={"kind": "offer", "project_title": "Angebot", "recipient": {"name": "Musterfirma GmbH", "lines": ["z. Hd. X", "Berlin"]}})
    check(r.status_code == 201, f"{who}: a quotation " + r.text[:160])
    oid_ = r.json().get("id")
    S.put(B + f"{D}/{oid_}/items", json={"items": ITEMS})
    r = S.post(B + f"{D}/{oid_}/finalize")
    check(r.ok, f"{who} #6477: a quotation without a client still finalises with free lines " + r.text[:200])


run(A, "org")
run(F, "freelancer")
sys.exit(done("p6476_einvoice_finalize"))
