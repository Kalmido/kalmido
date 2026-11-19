#!/usr/bin/env python3
# kalmido-suite: fresh
"""2.1435.0 API tests (#6819): the payment block of an invoice chosen when a person finalises it (office/docpay.py) -- "Issue as
paid" and an invoice issuer's bank account with its reference -- on the PDF, in the GiroCode and in the e-invoice. Own container
(start.sh, mode workspaces, KALMIDO_ISSUER_KEYS on). Invented companies, people, accounts and figures only.
tenant-matrix: office  freelancer-matrix: office
 - the draft route: an RF reference with wrong check digits (mod 97) = 400 invalid_field wish.reference; a right one 201
 - an account with the mark "only with the reference": the PDF prints its holder, IBAN and the fixed sentence with the reference
   as sent (with hyphens), not the office's own account; the GiroCode = holder, IBAN, BIC and the reference without hyphens as
   the structured reference (no document number); the e-invoice BT-83 = the reference without hyphens, BT-84 its IBAN, BT-85 its
   holder; the issuer's due_days apply (date + 21)
 - an account without the mark: holder and IBAN of the account, the remittance (GiroCode, BT-83) = the document number
 - a due date less than 7 days after the date: not finalised, the hint in missing; the marked account without a reference: the
   same (missing, 400); an account removed meanwhile: the same
 - "Issue as paid" (the issuer's wish.paid only shown): status paid, one payment of the gross (inv_pay_add, method card); the PDF
   says "Bezahlt am ... per Karte", "Bereits bezahlt" and 0 outstanding, no IBAN, no GiroCode, no due date (also with a marked
   account in the draft: no third-party account on a paid invoice); the e-invoice: code 48, no IBAN, prepaid = gross, due 0
 - as_paid: a wrong method 400, a member without the payment right 403 -- nothing finalised either time
 - the personal office of a person without an organisation: an invoice of her own issued as paid (cash): paid, code 10
 - without a payment block nothing changes: the office's own account and the document number
usage: p6819_office_issuer_payment_test.py <datadir>"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET
import zlib
from datetime import date, timedelta

import requests

N = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, N)
import kt  # noqa: E402
from kt import B, check  # noqa: E402
import dbx as dbxm  # noqa: E402
from freelancer_fixture import FEATURES, PASSWORD, freelancer, login  # noqa: E402

try:
    from pypdf import PdfReader
except ImportError:  # the PDF text checks need pypdf (the Mac's test environment has it)
    PdfReader = None

kt.docker_logs_on_first_fail()
DATA = sys.argv[1] if len(sys.argv) > 1 else kt.DATA
OF = "/api/office"
D = OF + "/docs"
V = B + "/api/v1"
CR = "/issuer/clients/by-ref/"
TODAY = date.today()
COMPANY = {"name": "Studio Nordlicht", "street": "Hafenstraße 12", "zip": "20457", "city": "Hamburg", "country": "DE",
           "email": "hallo@nordlicht.example", "phone": "+49 40 1234567", "tax_number": "12/345/67890", "vat_id": "DE999999999",
           "iban": "DE02120300000000202051", "bic": "BYLADEM1001", "bank_name": "Beispielbank"}
ADDR = {"street": "Marktweg 5", "zip": "50667", "city": "Köln", "country": "DE"}
HOLDER = "Zahlungsdienst Beispiel Stiftung"
P_IBAN, P_BIC = "NL91ABNA0417164300", "ABNANL2A"
P2_HOLDER, P2_IBAN = "Studio Nordlicht Sammelkonto", "DE89370400440532013000"
RF, RF_E = "RF23-2089-7256-3086", "RF23208972563086"
NS = {"rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
      "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
      "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"}
AG = "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeSettlement/"
MS = AG + "ram:SpecifiedTradeSettlementHeaderMonetarySummation/"


def sql(q, args=()):
    c = dbxm.connect(os.path.join(DATA, "tasks.db"), timeout=10)
    try:
        return c.execute(q, args).fetchall()
    finally:
        c.close()


def hk(key):
    return {"Authorization": "Bearer " + key}


def kput(key, ref, b):
    return requests.put(V + CR + ref, headers=hk(key), json=b, timeout=30)


def kpost(key, b):
    return requests.post(V + "/issuer/invoices", headers=hk(key), json=b, timeout=30)


def ecode(r):
    try:
        e = r.json().get("error")
        return (e.get("code"), e.get("field")) if isinstance(e, dict) else (None, None)
    except ValueError:
        return None, None


def body(ref, wish=None):
    return {"client_ref": ref, "client": {"external_ref": "acc:1"}, "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat(),
            "items": [{"text": "Tarif Studio, Dezember", "qty": 1, "unit": "flat", "rate": "150.00", "tax": "standard"}],
            "expect": {"net": "150.00", "tax": "28.50", "gross": "178.50"}, **({"wish": wish} if wish else {})}


def draft(ref, wish=None):
    r = kpost(KEY, body(ref, wish))
    assert r.status_code == 201, r.text
    return r.json()["doc_id"]


def finalize(S, did, extra=None):
    hold = S.get(B + D + f"/{did}/number-preview").json().get("client_hold") or {}
    return S.post(B + D + f"/{did}/finalize", json={**({"client_hold_ok": hold["at"]} if hold.get("at") else {}), **(extra or {})})


def render(S, did):
    return S.get(B + D + f"/{did}/render").json()


def girocode(S, did):
    return ((render(S, did).get("payment") or {}).get("girocode")) or ""


def xml_of(S, did):
    r = S.get(B + D + f"/{did}/xml")
    try:
        return ET.fromstring(r.content) if r.ok else None
    except ET.ParseError:
        return None


def xt(root, path):
    if root is None:
        return None
    x = root.find(path, NS)
    return (x.text or "").strip() if x is not None else None


def pdf_text(S, did):
    if PdfReader is None:
        return None
    r = S.get(B + D + f"/{did}/pdf")
    return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages) if r.ok else ""


def pdf_has_code(S, did):
    raw = S.get(B + D + f"/{did}/pdf").content
    want = b"GiroCode".hex().encode()
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        try:
            data = zlib.decompress(m.group(1))
        except zlib.error:
            data = m.group(1)
        if want in data.lower() or b"GiroCode" in data:
            return True
    return False


def flat(t):
    return re.sub(r"\s+", " ", t or "")


# ---------------------------------------------------------------- the container
kt.fresh({"KALMIDO_INSTANCE_MODE": "workspaces", "KALMIDO_ISSUER_KEYS": "1", "TASKS_WATCHDOG_INTERVAL": "3600"}, data=DATA)
A = kt.setup()
A.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done"})
ALICE = A.get(B + "/api/state").json()["me"]["id"]
ORG = A.post(B + "/api/admin/orgs", json={"name": "Alpha", "admin_id": ALICE}).json()["id"]
assert A.patch(B + "/api/settings", json={"workspace": f"org:{ORG}"}).ok
FID, Fr = freelancer(B, A)
Fr.patch(B + "/api/settings", json={"workspace": "private"})

assert A.put(B + OF + "/settings", json={"lang": "de", "company_fields": COMPANY}).ok
r = A.post(B + OF + "/num-ranges", json={"code": "GT", "scheme": "GT-{yyyy}-{seq:03}"})
assert r.status_code == 201, r.text
RG = r.json()["id"]
r = A.post(B + OF + "/issuers", json={"name": "Shop", "range_id": RG, "password": PASSWORD})
assert r.status_code == 201, r.text
IID, KEY = r.json()["issuer"]["id"], r.json()["key"]
assert kput(KEY, "acc:1", {"name": "Kundin Beispiel", **ADDR, "email_invoice": "rechnung@kunde.example"}).status_code == 201


def payee(label, holder, iban, bic="", ref_only=False):
    r = A.post(B + OF + f"/issuers/{IID}/payees", json={"label": label, "holder": holder, "iban": iban, "bic": bic, "ref_only": ref_only, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["payee"]["id"]


PREF = payee("Zahlungsdienst", HOLDER, P_IBAN, P_BIC, True)
PPLAIN = payee("Sammelkonto", P2_HOLDER, P2_IBAN)
PGONE = payee("Altes Konto", "Altes Konto Beispiel", "DE75512108001245126199", ref_only=False)

# ---------------------------------------------------------------- the RF check digits (draft route)
r = kpost(KEY, body("rf:bad", {"payee": PREF, "payee_check": "4300", "reference": "RF24-2089-7256-3086"}))
check(r.status_code == 400 and ecode(r) == ("invalid_field", "wish.reference") and not sql("SELECT 1 FROM office_issuer_refs WHERE client_ref='rf:bad'"),
      f"an RF reference with wrong check digits: 400 invalid_field wish.reference, nothing made {r.status_code} {r.text[:200]}")
r = kpost(KEY, body("rf:other", {"reference": "GT-4711-ABCD"}))
check(r.status_code == 201, f"a reference that is no RF reference is taken as before {r.status_code} {r.text[:200]}")

# ---------------------------------------------------------------- the account with the mark "only with the reference"
DREF = draft("ref:1", {"payee": PREF, "payee_check": "4300", "reference": RF, "due_days": 21})
d = A.get(B + D + f"/{DREF}").json()
pe = (d.get("issuer_wish") or {}).get("payee") or {}
check(pe.get("label") == "Zahlungsdienst" and pe.get("holder") == HOLDER and pe.get("iban_end") == "4300" and pe.get("ref_only") is True,
      f"the reviewer sees the account's name, holder, IBAN end and mark {pe}")
r = finalize(A, DREF)
check(r.ok and r.json().get("number"), f"a person finalises the draft with the account {r.status_code} {r.text[:200]}")
fd = A.get(B + D + f"/{DREF}").json()
check(fd.get("due_date") == (date.fromisoformat(fd.get("date") or TODAY.isoformat()) + timedelta(days=21)).isoformat(),
      f"the issuer's due_days apply: date + 21 {fd.get('date')} {fd.get('due_date')}")
code = girocode(A, DREF).split("\n")
check(code[:10] == ["BCD", "002", "1", "SCT", P_BIC, HOLDER, P_IBAN, "EUR178.50", "", RF_E] and len(code) == 10,
      f"GiroCode: holder, the account's IBAN / BIC, the reference without hyphens as the structured reference, no document number {code}")
x = xml_of(A, DREF)
check(xt(x, AG + "ram:PaymentReference") == RF_E and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == P_IBAN
      and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:AccountName") == HOLDER
      and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode") == "58",
      f"e-invoice: BT-83 the reference without hyphens, BT-84 the account's IBAN, BT-85 its holder, code 58 {x is not None}")
t = flat(pdf_text(A, DREF))
if t is not None:
    check(RF in t and HOLDER in t and "NL91 ABNA 0417 1643 00" in t and "Bitte geben Sie bei der Überweisung die Referenz" in t
          and "DE02 1203" not in t, f"PDF: the holder, the account, the fixed sentence with the reference as sent; not the office's account {t[-700:]}")
check(pdf_has_code(A, DREF), "PDF: the GiroCode is drawn")

# ---------------------------------------------------------------- an account without the mark
DPL = draft("plain:1", {"payee": PPLAIN, "payee_check": "3000", "reference": "GT-4711-ABCD"})
r = finalize(A, DPL)
num = r.json().get("number") if r.ok else ""
code = girocode(A, DPL).split("\n")
check(r.ok and code[5:7] == [P2_HOLDER, P2_IBAN] and code[-1] == num and code[9] == "", f"without the mark: holder and IBAN of the account, the document number as remittance {code}")
x = xml_of(A, DPL)
check(xt(x, AG + "ram:PaymentReference") == num and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") == P2_IBAN,
      f"without the mark: BT-83 the document number, BT-84 the account {xt(x, AG + 'ram:PaymentReference')}")

# ---------------------------------------------------------------- what stops finalising
DSHORT = draft("short:1", {"due_date": (TODAY + timedelta(days=3)).isoformat()})
miss = " ".join(x.get("text") or "" for x in A.get(B + D + f"/{DSHORT}").json().get("missing") or [])
r = finalize(A, DSHORT)
check(r.status_code == 400 and "7" in miss and sql("SELECT status FROM office_docs WHERE id=?", (DSHORT,))[0][0] == "draft",
      f"a due date in 3 days: the hint in missing, 400, still a draft {r.status_code} {miss[:200]}")
DNOREF = draft("noref:1", {"payee": PREF, "payee_check": "4300"})
miss = [x.get("key") for x in A.get(B + D + f"/{DNOREF}").json().get("missing") or []]
r = finalize(A, DNOREF)
check(r.status_code == 400 and "payee" in miss and sql("SELECT status FROM office_docs WHERE id=?", (DNOREF,))[0][0] == "draft",
      f"the marked account without a reference: missing, 400, still a draft {r.status_code} {miss}")
DGONE = draft("gone:1", {"payee": PGONE, "payee_check": "6199"})
assert A.delete(B + OF + f"/issuers/{IID}/payees/{PGONE}", json={"password": PASSWORD}).ok
miss = [x.get("key") for x in A.get(B + D + f"/{DGONE}").json().get("missing") or []]
r = finalize(A, DGONE)
check(r.status_code == 400 and "payee" in miss, f"an account removed meanwhile: missing, 400 {r.status_code} {miss}")

# ---------------------------------------------------------------- "Issue as paid"
DPAID = draft("paid:1", {"payee": PREF, "payee_check": "4300", "reference": RF,
                         "paid": {"amount": "178.50", "date": TODAY.isoformat(), "method": "card", "provider": "beispiel", "online_ref": "tr_1"}})
r = finalize(A, DPAID, {"as_paid": {"date": TODAY.isoformat(), "method": "bitcoin"}})
check(r.status_code == 400 and sql("SELECT status FROM office_docs WHERE id=?", (DPAID,))[0][0] == "draft", f"as_paid with an unknown method: 400, nothing finalised {r.status_code}")
r = A.post(B + "/api/users", json={"orgs": [{"id": ORG, "role": "member"}], "username": "carl", "display_name": "Carl Staff",
                                   "password": PASSWORD, "email": "carl@example.com"})
assert r.ok, r.text
Ca = login(B, "carl")
Ca.patch(B + "/api/settings", json={"lang": "en", "features": FEATURES, "tour": "done", "workspace": f"org:{ORG}"})
r = finalize(Ca, DPAID, {"as_paid": {"date": TODAY.isoformat(), "method": "card"}})
check(r.status_code == 403 and tuple(sql("SELECT status, number FROM office_docs WHERE id=?", (DPAID,))[0]) == ("draft", ""),
      f"a member without the payment right: 403, nothing finalised {r.status_code} {r.text[:160]}")
check(sql("SELECT COUNT(*) FROM office_payments WHERE doc_id=?", (DPAID,))[0][0] == 0, "the issuer's wish.paid alone books nothing")
r = finalize(A, DPAID, {"as_paid": {"date": TODAY.isoformat(), "method": "card"}})
check(r.ok and r.json().get("number"), f"a person issues it as paid {r.status_code} {r.text[:200]}")
fd = A.get(B + D + f"/{DPAID}").json()
pays = sql("SELECT amount, method, date FROM office_payments WHERE doc_id=? AND reverses_id IS NULL", (DPAID,))
check(fd.get("status") == "paid" and len(pays) == 1 and abs(float(pays[0][0]) - 178.50) < 0.001 and pays[0][1] == "card" and str(pays[0][2])[:10] == TODAY.isoformat(),
      f"status paid, one payment of the gross by card {fd.get('status')} {pays}")
rd = render(A, DPAID)
check(not (rd.get("payment") or {}).get("iban") and not (rd.get("payment") or {}).get("girocode") and not rd.get("due_date"),
      f"the print model: no IBAN, no GiroCode, no due date {rd.get('payment')} {rd.get('due_date')}")
t = flat(pdf_text(A, DPAID))
if t is not None:
    check("Bezahlt am" in t and "per Karte" in t and "Bereits bezahlt" in t and "IBAN" not in t and "Zahlbar bis" not in t and RF not in t and HOLDER not in t,
          f"PDF: paid on ... by card, already paid, no IBAN, no due text, no third-party account {t[-600:]}")
check(not pdf_has_code(A, DPAID), "PDF: no GiroCode")
x = xml_of(A, DPAID)
check(xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode") == "48" and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:IBANID") is None
      and xt(x, MS + "ram:TotalPrepaidAmount") == "178.50" and xt(x, MS + "ram:DuePayableAmount") == "0.00" and xt(x, AG + "ram:PaymentReference") is None
      and xt(x, AG + "ram:SpecifiedTradePaymentTerms/ram:DueDateDateTime/udt:DateTimeString") is None,
      f"e-invoice: code 48, no IBAN, prepaid 178.50, due 0.00, no reference, no due date {x is not None}")

# ---------------------------------------------------------------- without a payment block: as before
DOWN = draft("own:1")
r = finalize(A, DOWN)
num = r.json().get("number") if r.ok else ""
code = girocode(A, DOWN).split("\n")
check(r.ok and code[5:7] == ["Studio Nordlicht", COMPANY["iban"]] and code[-1] == num, f"no account named: the office's own account, the document number {code}")
x = xml_of(A, DOWN)
check(xt(x, AG + "ram:PaymentReference") is None and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:PayeePartyCreditorFinancialAccount/ram:AccountName") == "Beispielbank",
      "no account named: no BT-83, the e-invoice as before")

# ---------------------------------------------------------------- a person without an organisation
assert Fr.put(B + OF + "/settings", json={"lang": "de", "company_fields": {**COMPANY, "name": "Frida Freiberuflich"}}).ok
r = Fr.post(B + "/api/clients", json={"name": "Kunde Beispiel", **ADDR, "email_invoice": "rechnung@kunde.example"})
assert r.status_code == 201, r.text
r = Fr.post(B + D, json={"kind": "invoice", "client_id": r.json()["id"], "service_from": TODAY.isoformat(), "service_to": TODAY.isoformat()})
assert r.status_code == 201, r.text
FD = r.json()["id"]
assert Fr.put(B + D + f"/{FD}/items", json={"items": [{"title": "Fotos", "qty": 1, "unit": "flat", "rate": 100}]}).ok
r = finalize(Fr, FD, {"as_paid": {"date": TODAY.isoformat(), "method": "cash"}})
fd = Fr.get(B + D + f"/{FD}").json()
x = xml_of(Fr, FD)
check(r.ok and fd.get("status") == "paid" and xt(x, AG + "ram:SpecifiedTradeSettlementPaymentMeans/ram:TypeCode") == "10" and xt(x, MS + "ram:DuePayableAmount") == "0.00",
      f"the personal office: her own invoice issued as paid in cash: paid, code 10, due 0 {r.status_code} {fd.get('status')}")

sys.exit(kt.done("p6819_office_issuer_payment"))
